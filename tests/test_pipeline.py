"""Спільне ядро прогону однієї вітки (`pipeline.run_branch`).

Ядро дає ФАКТИ, а текст відповіді лишається за викликачем: у мосту він
адресований TSM, у черзі ClickUp — людині, що дивиться в лабу. Тому тут
перевіряються рівно вироки і те, що в них покладено.

Найдорожчий з них — `not_ready`. Знімок доїжджає не миттєво, і нуль
прочитаних файлів раніше давав `clean`, тобто відповідь «дефектів немає» там,
де ніхто нічого не відкривав. Ціна брехні висока: `clean` закриває вітку до
наступної зміни коміту й ховає реальний дефект.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                        # noqa: E402

import pipeline                                                 # noqa: E402
import runner                                                   # noqa: E402


class _Client:
    """Клієнт GitLab, який нічого не робить (sync підмінено)."""


def _stub(monkey: dict):
    """Підміняє функції `runner`, які смикає ядро, і повертає відновлювач."""
    saved = {k: getattr(runner, k) for k in monkey}
    for k, v in monkey.items():
        setattr(runner, k, v)

    def restore():
        for k, v in saved.items():
            setattr(runner, k, v)
    return restore


def _result(checks=(), files_scanned=3):
    return {"files_scanned": files_scanned,
            "checks": [{"id": cid, "issues": issues} for cid, issues in checks]}


def _issue(sev="error"):
    return {"severity": sev, "message": "x", "path": "a.php", "line": 1}


def _run(*, result, changes=(), fixable=("favicon",), sync=None):
    """Прогін з підміненими кроками. `fixable` — що дозволено лагодити."""
    calls = {"synced": 0, "fixes_for": None}

    def _sync(client, branch):
        calls["synced"] += 1
        if sync:
            sync()

    def _checks_for_active_project():
        return [{"id": cid, "fixable": True, "group": "auto"} for cid in fixable]

    def _compute(branch, ids):
        calls["fixes_for"] = ids
        return list(changes)

    restore = _stub({"sync_branch": _sync,
                     "run_checks": lambda b, ids: result,
                     "checks_for_active_project": _checks_for_active_project,
                     "compute_fixes": _compute,
                     "is_synced": lambda b: True})
    try:
        got = pipeline.run_branch("br", ["favicon"], client=_Client(),
                                  groups={"auto", "tests"})
    finally:
        restore()
    return got, calls


# ------------------------------------------------------------------ вироки

def test_empty_snapshot_is_not_ready_not_clean():
    got, _ = _run(result=_result(files_scanned=0))
    assert got["verdict"] == pipeline.NOT_READY, got
    assert got["files_scanned"] == 0


def test_nothing_fired_is_clean():
    got, _ = _run(result=_result([("favicon", [])]))
    assert got["verdict"] == pipeline.CLEAN, got
    assert got["fired"] == {}


def test_fired_without_a_fix_hook_is_no_fix():
    got, _ = _run(result=_result([("favicon", [_issue()])]), fixable=())
    assert got["verdict"] == pipeline.NO_FIX, got
    assert got["fired"] == {"favicon": 1}
    assert got["fixable"] == []


def test_a_fix_that_changes_nothing_is_also_no_fix():
    """Чек бачить дефект, його fix-хук нічого не змінив — це «потрібна
    людина», а не «полагоджено»."""
    got, _ = _run(result=_result([("favicon", [_issue()])]), changes=())
    assert got["verdict"] == pipeline.NO_FIX, got
    assert got["fixable"] == ["favicon"]


def test_changes_make_would_fix():
    got, calls = _run(result=_result([("favicon", [_issue()])]),
                      changes=[{"type": "edit", "path": "a.php", "new": "y"}])
    assert got["verdict"] == pipeline.WOULD_FIX, got
    assert got["files"] == 1 and len(got["changes"]) == 1
    assert calls["fixes_for"] == ["favicon"], "лагодимо лише те, що спрацювало"


def test_warnings_count_as_evidence_too():
    """Жовте теж веде до фіксу: інакше половина чеків не лагодилась би."""
    got, _ = _run(result=_result([("favicon", [_issue("warn")])]),
                  changes=[{"type": "edit", "path": "a.php", "new": "y"}])
    assert got["verdict"] == pipeline.WOULD_FIX, got
    assert got["fired"] == {"favicon": 1}


# ------------------------------------------------------------------ sync

def test_sync_failure_on_an_existing_snapshot_only_warns():
    def boom():
        raise RuntimeError("gitlab down")
    got, _ = _run(result=_result([("favicon", [])]), sync=boom)
    assert got["verdict"] == pipeline.CLEAN, got
    assert "gitlab down" in got["stale"], got["stale"]


def test_sync_failure_without_a_snapshot_raises():
    """Без знімка мовчазний «чистий» результат був би вигадкою — падаємо."""
    def boom():
        raise RuntimeError("gitlab down")

    restore = _stub({"sync_branch": lambda c, b: boom(),
                     "is_synced": lambda b: False})
    try:
        pipeline.run_branch("br", None, client=_Client(), groups={"auto"})
    except RuntimeError:
        ok = True
    else:
        ok = False
    finally:
        restore()
    assert ok, "збій sync без знімка мусить летіти назовні"


# ------------------------------------------------------------------ деталі

def test_evidence_separates_errors_from_warnings():
    err, warn = pipeline.evidence(_result([("a", [_issue(), _issue("warn")]),
                                           ("b", [_issue("warn")])]))
    assert err == {"a": 1}, err
    assert warn == {"a": 1, "b": 1}, warn


def test_fixable_respects_the_allowed_groups():
    restore = _stub({"checks_for_active_project": lambda: [
        {"id": "auto_one", "fixable": True, "group": "auto"},
        {"id": "review_one", "fixable": True, "group": "review"},
        {"id": "no_hook", "fixable": False, "group": "auto"},
    ]})
    try:
        got = pipeline.fixable_now({"auto_one", "review_one", "no_hook"}, {"auto"})
    finally:
        restore()
    assert got == ["auto_one"], got


if __name__ == "__main__":
    run(dict(globals()))
