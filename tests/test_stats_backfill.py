"""Тести stats_backfill: відновлення втраченої історії статистики з GitLab.

Мережі в тестах немає — клієнт підмінюється фейком. Перевіряємо саме те, від
чого залежить правильність графіка: годинний пояс, розпізнавання комітів лаби,
кількість файлів і безпечність повторного запуску.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import stats_backfill as bf                                       # noqa: E402
import stats_ledger as sl                                         # noqa: E402


def _tmp():
    return Path(tempfile.mkdtemp(prefix="backfill-"))


class FakeClient:
    """Мінімум, що потрібен бекфілу: автор токена, коміти вітки, к-ть файлів."""

    def __init__(self, per_branch, author="qa_lab_token"):
        self.per_branch = per_branch
        self.author = author
        self.diff_calls = 0

    def me(self):
        return {"name": self.author, "username": "project_bot"}

    def commits_range(self, ref, since="", until=""):
        return list(self.per_branch.get(ref, []))

    def commit_file_count(self, sha):
        self.diff_calls += 1
        return {"c1": 5, "c2": 3, "c3": 12}.get(sha, 1)


def _c(sha, date, title, author="qa_lab_token"):
    return {"id": sha, "short": sha[:8], "title": title,
            "author": author, "date": date}


# ------------------------------------------------------------------ час
def test_utc_iso_becomes_local_journal_format():
    """GitLab віддає UTC, журнал лаби пише локальний час. Без конверсії коміти
    з'їжджали б на кілька годин і на межі доби падали б у чужий день графіка."""
    got = bf.local_ts("2026-07-30T12:34:35.000+00:00")
    assert len(got) == 19 and got[10] == " "
    assert got[:10] == "2026-07-30"
    # рівність із локальною зоною машини, без прив'язки до конкретного зсуву
    from datetime import datetime
    exp = datetime.fromisoformat("2026-07-30T12:34:35.000+00:00").astimezone()
    assert got == exp.strftime("%Y-%m-%d %H:%M:%S")


def test_local_ts_survives_offsetless_and_garbage_input():
    assert bf.local_ts("2026-07-30T12:34:35Z")[:10] == "2026-07-30"
    assert bf.local_ts("") == ""
    assert bf.local_ts("не дата") == "не дата"


# ------------------------------------------------------------------ дії
def test_known_lab_messages_map_to_actions():
    assert bf.action_for("fix: автовиправлення перевірок") == "autofix"
    assert bf.action_for("Translate foreign fragments") == "translate"
    assert bf.action_for("Fix text contrast") == "visual-fix"


def test_unknown_message_falls_back_to_commit_not_autofix():
    """Меседж масової заміни чи ручної правки пише людина — вгадувати не можна,
    інакше фільтр «автофікс» показував би чуже."""
    assert bf.action_for("прибрав зайвий блок") == "commit"
    assert bf.action_for("") == "commit"


# ------------------------------------------------------------------ збір
def test_collect_takes_only_lab_authored_commits():
    """Генераторські (`Auto-import`, `Update N files`) і людські коміти —
    не фікси лаби, вони не мусять попасти у статистику."""
    cl = FakeClient({"a-br-pt": [
        _c("c1", "2026-07-24T09:58:01.000+00:00", "fix: автовиправлення перевірок"),
        _c("x1", "2026-07-24T10:00:00.000+00:00", "Update 9 files", author="dean-support"),
        _c("x2", "2026-07-24T10:05:00.000+00:00", "Auto-import code for a-br-pt", author="Hugo Support"),
    ]})
    recs = bf.collect(cl, ["a-br-pt"], "2026-07-01T00:00:00Z", "", workers=1)
    assert [r["commit"] for r in recs] == ["c1"]
    assert recs[0]["files"] == 5 and recs[0]["action"] == "autofix"
    assert recs[0]["branch"] == "a-br-pt"


def test_collect_asks_for_file_count_once_per_matched_commit():
    cl = FakeClient({"a-br-pt": [
        _c("c1", "2026-07-24T09:58:01.000+00:00", "fix: автовиправлення перевірок"),
        _c("x1", "2026-07-24T10:00:00.000+00:00", "Update 9 files", author="human"),
    ]})
    bf.collect(cl, ["a-br-pt"], "2026-07-01T00:00:00Z", "", workers=1)
    assert cl.diff_calls == 1, "diff на чужі коміти — марні тисячі запитів"


def test_collect_walks_every_branch():
    cl = FakeClient({
        "a-br-pt": [_c("c1", "2026-07-24T09:00:00.000+00:00", "Fix text contrast")],
        "b-br-pt": [_c("c2", "2026-07-27T09:00:00.000+00:00", "Translate foreign fragments")],
        "c-br-pt": [],
    })
    recs = bf.collect(cl, ["a-br-pt", "b-br-pt", "c-br-pt"], "2026-07-01T00:00:00Z", "")
    assert {r["branch"] for r in recs} == {"a-br-pt", "b-br-pt"}
    assert {r["action"] for r in recs} == {"visual-fix", "translate"}


def test_collect_survives_a_broken_branch():
    """Одна вітка, що впала (404/таймаут), не мусить валити весь бекфіл."""
    class Boom(FakeClient):
        def commits_range(self, ref, since="", until=""):
            if ref == "bad-br-pt":
                raise RuntimeError("404")
            return super().commits_range(ref, since, until)
    cl = Boom({"ok-br-pt": [_c("c1", "2026-07-24T09:00:00.000+00:00",
                              "fix: автовиправлення перевірок")]})
    recs = bf.collect(cl, ["bad-br-pt", "ok-br-pt"], "2026-07-01T00:00:00Z", "", workers=1)
    assert [r["branch"] for r in recs] == ["ok-br-pt"]


# ------------------------------------------------------------------ запис
def test_apply_is_idempotent_against_existing_ledger():
    root = _tmp()
    cl = FakeClient({"a-br-pt": [
        _c("c1", "2026-07-24T09:58:01.000+00:00", "fix: автовиправлення перевірок")]})
    recs = bf.collect(cl, ["a-br-pt"], "2026-07-01T00:00:00Z", "", workers=1)
    assert sl.append_many(root, recs) == 1
    assert sl.append_many(root, recs) == 0
    assert len(sl.entries(root)) == 1


def test_apply_does_not_duplicate_what_journal_already_seeded():
    """Головний ризик бекфілу: журнал уже дав цей коміт (локальним часом), а
    GitLab дає його ж (UTC). Дублю бути не повинно."""
    root = _tmp()
    sl.append(root, {"ts": "2026-07-24 12:58:01", "branch": "a-br-pt",
                     "commit": "c1", "files": ["a", "b", "c", "d", "e"],
                     "action": "autofix"})
    cl = FakeClient({"a-br-pt": [
        _c("c1", "2026-07-24T09:58:01.000+00:00", "fix: автовиправлення перевірок")]})
    recs = bf.collect(cl, ["a-br-pt"], "2026-07-01T00:00:00Z", "", workers=1)
    assert sl.append_many(root, recs) == 0
    assert len(sl.entries(root)) == 1


if __name__ == "__main__":
    run(dict(globals()))
