"""Тести stats_ledger: вічна історія комітів лаби для статистики.

Ключовий контракт: журнал (`commits_log.json`) — це ВІКНО останньої
активності, тож він обрізається; статистиці потрібна ІСТОРІЯ, тож вона живе
в окремому append-only реєстрі й не залежить від обрізання журналу.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import stats_ledger as sl                                         # noqa: E402


def _tmp():
    return Path(tempfile.mkdtemp(prefix="ledger-"))


def _rec(ts, branch, files, action="autofix", commit="abc123"):
    return {"ts": ts, "branch": branch, "files": files,
            "action": action, "commit": commit}


# ------------------------------------------------------------- запис/читання
def test_append_then_read_roundtrip():
    root = _tmp()
    sl.append(root, _rec("2026-07-24 09:58:01", "alfa-br-pt", 5))
    got = sl.entries(root)
    assert len(got) == 1
    e = got[0]
    assert e["ts"] == "2026-07-24 09:58:01"
    assert e["branch"] == "alfa-br-pt"
    assert e["files"] == 5 and e["action"] == "autofix"


def test_files_list_is_stored_as_count():
    """Журнал тримає список шляхів, реєстру потрібне лише число — інакше
    історія важила б стільки ж, скільки журнал."""
    root = _tmp()
    sl.append(root, _rec("2026-07-24 10:00:00", "a-br-pt",
                         ["index.php", "faq.html", "contact.html"]))
    assert sl.entries(root)[0]["files"] == 3


def test_sharded_by_month():
    root = _tmp()
    sl.append(root, _rec("2026-06-30 23:59:59", "a-br-pt", 1))
    sl.append(root, _rec("2026-07-01 00:00:01", "b-br-pt", 2))
    shards = sorted(p.name for p in (root / "stats").glob("*.jsonl"))
    assert shards == ["2026-06.jsonl", "2026-07.jsonl"]
    assert len(sl.entries(root)) == 2


def test_append_does_not_rewrite_old_shards():
    """Старі шарди незмінні: запис нового місяця не торкається минулого —
    саме це робить вартість запису O(1) замість перезапису всієї історії."""
    root = _tmp()
    sl.append(root, _rec("2026-06-15 12:00:00", "a-br-pt", 1))
    old = root / "stats" / "2026-06.jsonl"
    before = (old.read_bytes(), old.stat().st_mtime_ns)
    for i in range(50):
        sl.append(root, _rec(f"2026-07-01 00:00:{i:02d}", f"b{i}-br-pt", 1))
    assert (old.read_bytes(), old.stat().st_mtime_ns) == before


def test_entries_sorted_by_ts_across_shards():
    root = _tmp()
    sl.append(root, _rec("2026-07-05 10:00:00", "c-br-pt", 1))
    sl.append(root, _rec("2026-06-01 10:00:00", "a-br-pt", 1))
    sl.append(root, _rec("2026-07-01 10:00:00", "b-br-pt", 1))
    assert [e["branch"] for e in sl.entries(root)] == ["a-br-pt", "b-br-pt", "c-br-pt"]


def test_missing_dir_reads_empty():
    assert sl.entries(_tmp()) == []


def test_broken_line_does_not_kill_the_read():
    """Обірваний рядок (напр. падіння під час запису) не мусить робити всю
    історію нечитаною."""
    root = _tmp()
    sl.append(root, _rec("2026-07-01 10:00:00", "a-br-pt", 1))
    shard = root / "stats" / "2026-07.jsonl"
    with shard.open("a", encoding="utf-8") as f:
        f.write('{"ts": "2026-07-02 10:00:00", "bran\n')
    sl.append(root, _rec("2026-07-03 10:00:00", "b-br-pt", 2))
    got = sl.entries(root)
    assert [e["branch"] for e in got] == ["a-br-pt", "b-br-pt"]


# ---------------------------------------------------------------- ідемпотентність
def test_append_many_dedupes_by_commit_identity():
    """Бекфіл і сідинг мусять бути безпечні для повторного запуску."""
    root = _tmp()
    recs = [_rec("2026-07-24 09:58:01", "a-br-pt", 5, commit="c1"),
            _rec("2026-07-24 09:58:02", "b-br-pt", 3, commit="c2")]
    assert sl.append_many(root, recs) == 2
    assert sl.append_many(root, recs) == 0, "повторний запис нічого не додає"
    assert len(sl.entries(root)) == 2


def test_dedupe_uses_ts_branch_when_commit_is_empty():
    root = _tmp()
    r = _rec("2026-07-24 09:58:01", "a-br-pt", 5, commit="")
    assert sl.append_many(root, [r]) == 1
    assert sl.append_many(root, [r]) == 0


def test_same_commit_on_different_branches_is_kept():
    """Дві вітки можуть мати спільний sha (спільний базовий коміт) — це
    різні записи, дедуп не має їх злити."""
    root = _tmp()
    n = sl.append_many(root, [
        _rec("2026-07-24 09:58:01", "a-br-pt", 5, commit="same"),
        _rec("2026-07-24 09:58:01", "b-br-pt", 5, commit="same")])
    assert n == 2
    assert len(sl.entries(root)) == 2


# ---------------------------------------------------------------- міграція
def test_seed_from_journal_folds_existing_entries():
    root = _tmp()
    (root / "commits_log.json").write_text(json.dumps([
        {"ts": "2026-07-29 10:00:00", "branch": "a-br-pt", "commit": "c1",
         "files": ["index.php", "faq.html"], "action": "autofix"},
        {"ts": "2026-07-29 11:00:00", "branch": "b-br-pt", "commit": "c2",
         "files": ["index.php"], "action": "replace"},
    ], ensure_ascii=False), encoding="utf-8")
    assert sl.seed_from_journal(root) == 2
    got = sl.entries(root)
    assert [e["files"] for e in got] == [2, 1]
    assert [e["action"] for e in got] == ["autofix", "replace"]


def test_same_commit_same_branch_dedupes_across_different_ts():
    """Найгостріше для бекфілу: журнал пише ЛОКАЛЬНИЙ час лаби, а GitLab
    віддає UTC. Той самий коміт приходить із двох джерел із різним ts — якщо
    ts у ключі, дедуп не спрацює і бекфіл подвоїть усю історію."""
    root = _tmp()
    sha = "9f2590d5df0011"
    assert sl.append_many(root, [
        _rec("2026-07-29 16:23:42", "a-br-pt", 7, commit=sha)]) == 1
    assert sl.append_many(root, [
        _rec("2026-07-29 13:23:42", "a-br-pt", 7, commit=sha)]) == 0
    assert len(sl.entries(root)) == 1


def test_seed_is_idempotent_and_keeps_ledger_only_records():
    """Сідинг не мусить дублювати вже наявне і не мусить чіпати записи, яких
    у журналі вже немає (саме вони — сенс реєстру)."""
    root = _tmp()
    sl.append(root, _rec("2026-07-20 10:00:00", "old-br-pt", 4, commit="old"))
    (root / "commits_log.json").write_text(json.dumps([
        {"ts": "2026-07-29 10:00:00", "branch": "a-br-pt", "commit": "c1",
         "files": ["index.php"], "action": "autofix"}], ensure_ascii=False),
        encoding="utf-8")
    assert sl.seed_from_journal(root) == 1
    assert sl.seed_from_journal(root) == 0
    got = sl.entries(root)
    assert [e["branch"] for e in got] == ["old-br-pt", "a-br-pt"]


def test_seed_on_missing_journal_is_noop():
    assert sl.seed_from_journal(_tmp()) == 0


def test_ensure_seeded_runs_once_even_if_ledger_already_has_records():
    """Пастка, яку легко проґавити: якщо перший коміт після оновлення стався
    РАНІШЕ за перше читання статистики, реєстр уже не порожній — умова «пусто
    -> сідинг» більше не спрацює і старі записи журналу лишились би назовні.
    Тому міграцію гейтить маркер, а не порожність."""
    root = _tmp()
    sl.append(root, _rec("2026-07-30 12:00:00", "fresh-br-pt", 1, commit="new"))
    (root / "commits_log.json").write_text(json.dumps([
        {"ts": "2026-07-29 10:00:00", "branch": "old-br-pt", "commit": "c1",
         "files": ["index.php"], "action": "autofix"}], ensure_ascii=False),
        encoding="utf-8")
    assert sl.ensure_seeded(root) == 1
    assert {e["branch"] for e in sl.entries(root)} == {"fresh-br-pt", "old-br-pt"}


def test_ensure_seeded_does_not_refold_after_journal_rotates():
    """Другий виклик не мусить нічого робити — навіть якщо журнал уже
    прокрутився і містить зовсім інші записи."""
    root = _tmp()
    (root / "commits_log.json").write_text(json.dumps([
        {"ts": "2026-07-29 10:00:00", "branch": "a-br-pt", "commit": "c1",
         "files": ["index.php"], "action": "autofix"}], ensure_ascii=False),
        encoding="utf-8")
    assert sl.ensure_seeded(root) == 1
    (root / "commits_log.json").write_text(json.dumps([
        {"ts": "2026-07-31 10:00:00", "branch": "z-br-pt", "commit": "c9",
         "files": ["index.php"], "action": "autofix"}], ensure_ascii=False),
        encoding="utf-8")
    assert sl.ensure_seeded(root) == 0
    assert [e["branch"] for e in sl.entries(root)] == ["a-br-pt"]


# ---------------------------------------------------------------- стійкість
def test_bad_ts_goes_to_unknown_shard_not_crash():
    root = _tmp()
    sl.append(root, {"ts": "", "branch": "a-br-pt", "files": 1, "action": "edit"})
    got = sl.entries(root)
    assert len(got) == 1 and got[0]["branch"] == "a-br-pt"


def test_revert_action_is_preserved():
    """Статистика виключає revert з «фіксів», тож дія мусить доїжджати як є."""
    root = _tmp()
    sl.append(root, _rec("2026-07-30 10:00:00", "a-br-pt", 2, action="revert"))
    assert sl.entries(root)[0]["action"] == "revert"


if __name__ == "__main__":
    run(dict(globals()))
