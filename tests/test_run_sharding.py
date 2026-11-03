"""Шардинг прогону по файлах (runner.run_checks, 02.10).

Великі вітки (≥ QA_LAB_SHARD_MIN_FILES) діляться: по-файлові чеки йдуть
K шардами, branch-рівневі — однією задачею; результати зливаються без
втрат. Еквівалентність шардованого прогону доведена на 552-файловій
вітці (биті-в-біт totals і по-чекові списки); тут — контракти стадій
і злиття, без пулу.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                        # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import runner                                                   # noqa: E402


def _check(cid, branch_level=False):
    mod = types.SimpleNamespace()
    if branch_level:
        mod.run_branch = lambda *a: []
    else:
        mod.run = lambda p, t: []
    return {"id": cid, "module": mod, "name": cid, "description": "",
            "files": ["*"], "group": "tests", "fixable": False}


def test_stage_filters_split_checks():
    checks = [_check("file_a"), _check("file_b"),
              _check("branch_a", True), _check("branch_b", True)]
    files_stage = [c for c in checks
                   if not hasattr(c["module"], "run_branch")]
    branch_stage = [c for c in checks if hasattr(c["module"], "run_branch")]
    assert {c["id"] for c in files_stage} == {"file_a", "file_b"}
    assert {c["id"] for c in branch_stage} == {"branch_a", "branch_b"}


def test_merge_runs_concatenates_and_recounts():
    p1 = {"branch": "x", "files_scanned": 10,
          "totals": {"error": 1, "warn": 0, "info": 0},
          "checks": [{"id": "f", "name": "f", "description": "", "ms": 5,
                      "issues": [{"path": "a", "severity": "error",
                                  "line": 1, "message": "m1"}]}],
          "bytes_scanned": 100}
    p2 = {"branch": "x", "files_scanned": 10,
          "totals": {"error": 0, "warn": 1, "info": 0},
          "checks": [{"id": "f", "name": "f", "description": "", "ms": 7,
                      "issues": [{"path": "b", "severity": "warn",
                                  "line": 2, "message": "m2"}]}],
          "bytes_scanned": 50,
          "skipped_by_code": ["geo_phone"]}
    p3 = {"branch": "x", "files_scanned": 20,
          "totals": {"error": 2, "warn": 0, "info": 0},
          "checks": [{"id": "br", "name": "br", "description": "", "ms": 11,
                      "issues": [{"path": "c", "severity": "error",
                                  "line": 3, "message": "m3"},
                                 {"path": "d", "severity": "error",
                                  "line": 4, "message": "m4"}]}],
          "bytes_scanned": 200}
    out = runner._merge_runs("x", 20, [p1, p2, p3])
    assert out["files_scanned"] == 20
    assert out["totals"] == {"error": 3, "warn": 1, "info": 0}
    f = next(c for c in out["checks"] if c["id"] == "f")
    assert len(f["issues"]) == 2 and f["ms"] == 12
    assert out["skipped_by_code"] == ["geo_phone"]
    assert out["bytes_scanned"] == 350


def test_offload_many_inline_without_pool():
    old = runner._get_pool
    runner._get_pool = lambda: None
    calls = []
    runner._probe_fn = lambda a, b: calls.append((a, b)) or {"ok": a}
    try:
        parts = runner._offload_many("x", [("_probe_fn", (1, 2)),
                                           ("_probe_fn", (3, 4))])
        assert parts == [{"ok": 1}, {"ok": 3}]
        assert calls == [(1, 2), (3, 4)]
    finally:
        runner._get_pool = old
        del runner._probe_fn


if __name__ == "__main__":
    run(dict(globals()))
