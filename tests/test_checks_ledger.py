"""Тести checks_ledger: вічна історія прогонів перевірок.

Ключовий контракт: `checks_state.json` тримає лише ОСТАННІЙ прогін і
перезаписується, тож тренду якості з нього не побудувати. Реєстр
дописується шардами по місяцях і зберігає, ЯКІ чеки ганяли (`ran`) —
без цього «чек не спрацював» не відрізнити від «чек не ганяли», а на
цьому тримається вся відповідь «чи тримається фікс».
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import checks_ledger as cl                                        # noqa: E402


def _tmp():
    return Path(tempfile.mkdtemp(prefix="chkledger-"))


def _run_result(branch, checks, ts="2026-08-01 10:00:00", files=9):
    """checks: {id: [severity, ...]} — як віддає /api/checks/run."""
    return {"branch": branch, "ts": ts, "files_scanned": files,
            "checks": [{"id": cid, "issues": [{"severity": s} for s in sev]}
                       for cid, sev in checks.items()]}


# ------------------------------------------------------------- запис/читання
def test_append_then_read_roundtrip():
    root = _tmp()
    cl.append(root, {"ts": "2026-08-01 10:00:00", "branch": "a-br-pt",
                     "files": 9, "ran": ["favicon"], "err": {"favicon": 2}})
    got = cl.entries(root)
    assert len(got) == 1
    assert got[0]["branch"] == "a-br-pt" and got[0]["err"] == {"favicon": 2}
    assert got[0]["ran"] == ["favicon"]


def test_sharded_by_month():
    root = _tmp()
    cl.append(root, {"ts": "2026-07-31 23:59:59", "branch": "a", "ran": ["x"]})
    cl.append(root, {"ts": "2026-08-01 00:00:01", "branch": "b", "ran": ["x"]})
    names = sorted(p.name for p in (root / cl.DIRNAME).glob("*.jsonl"))
    assert names == ["2026-07.jsonl", "2026-08.jsonl"]


def test_bad_ts_goes_to_unknown_shard_not_lost():
    root = _tmp()
    cl.append(root, {"ts": "хтозна", "branch": "a", "ran": ["x"]})
    assert (root / cl.DIRNAME / "unknown.jsonl").exists()
    assert len(cl.entries(root)) == 1


def test_entries_sorted_and_broken_line_skipped():
    root = _tmp()
    cl.append(root, {"ts": "2026-08-02 10:00:00", "branch": "b", "ran": ["x"]})
    cl.append(root, {"ts": "2026-08-01 10:00:00", "branch": "a", "ran": ["x"]})
    with (root / cl.DIRNAME / "2026-08.jsonl").open("a", encoding="utf-8") as f:
        f.write("{обірваний рядок\n")
    got = cl.entries(root)
    assert [e["branch"] for e in got] == ["a", "b"]      # одна бита не валить решту


def test_zero_counts_are_not_stored():
    """Реєстр і так найбільший файл стану — нулі в ньому зайві."""
    root = _tmp()
    cl.append(root, {"ts": "2026-08-01 10:00:00", "branch": "a",
                     "ran": ["favicon"], "err": {"favicon": 0}, "warn": {}})
    assert cl.entries(root)[0]["err"] == {}


# ------------------------------------------------------------------ дедуп
def test_append_many_is_idempotent():
    root = _tmp()
    recs = [{"ts": "2026-08-01 10:00:00", "branch": "a", "ran": ["x"]}]
    assert cl.append_many(root, recs) == 1
    assert cl.append_many(root, recs) == 0
    assert len(cl.entries(root)) == 1


def test_same_branch_same_ts_different_checkset_is_a_separate_run():
    """Два різні набори чеків в одну секунду — це два прогони, не дубль."""
    root = _tmp()
    ts = "2026-08-01 10:00:00"
    n = cl.append_many(root, [{"ts": ts, "branch": "a", "ran": ["favicon"]},
                              {"ts": ts, "branch": "a", "ran": ["forms"]}])
    assert n == 2 and len(cl.entries(root)) == 2


# --------------------------------------------------------------- record_run
def test_record_run_counts_severities():
    root = _tmp()
    cl.record_run(root, [_run_result("a", {"favicon": ["error", "error", "warn"],
                                           "forms": ["warn"]})])
    e = cl.entries(root)[0]
    assert e["err"] == {"favicon": 2}
    assert e["warn"] == {"favicon": 1, "forms": 1}
    assert e["files"] == 9


def test_ran_includes_checks_with_no_findings():
    """Найважливіше: чистий чек мусить лишитись у `ran`, інакше пізніше
    не відрізнити «полагодили» від «не ганяли»."""
    root = _tmp()
    cl.record_run(root, [_run_result("a", {"favicon": [], "forms": ["error"]})])
    e = cl.entries(root)[0]
    assert e["ran"] == ["favicon", "forms"]
    assert e["err"] == {"forms": 1}


def test_issue_without_severity_counts_as_error():
    root = _tmp()
    cl.record_run(root, [{"branch": "a", "ts": "2026-08-01 10:00:00",
                          "checks": [{"id": "x", "issues": [{}]}]}])
    assert cl.entries(root)[0]["err"] == {"x": 1}


def test_failed_branch_is_not_recorded():
    """Недоступна/перейменована вітка — це не результат перевірки."""
    root = _tmp()
    # checks НЕ порожній — інакше запис відсіявся б через «немає ran»,
    # і гард на error лишився б неперевіреним
    n = cl.record_run(root, [{"branch": "a", "error": "no such branch",
                              "ts": "2026-08-01 10:00:00",
                              "checks": [{"id": "favicon", "issues": []}]}])
    assert n == 0 and cl.entries(root) == []


def test_run_without_checks_is_not_recorded():
    root = _tmp()
    assert cl.record_run(root, [_run_result("a", {})]) == 0


# ------------------------------------------------------------------ сідинг
def _state(root, data):
    (root / "checks_state.json").write_text(json.dumps(data), encoding="utf-8")


def test_seed_from_state():
    root = _tmp()
    _state(root, {"a-br-pt": {"branch": "a-br-pt", "ts": "2026-07-01 10:00:00",
                              "files_scanned": 4,
                              "checks": [{"id": "favicon",
                                          "issues": [{"severity": "error"}]}]}})
    assert cl.seed_from_state(root) == 1
    e = cl.entries(root)[0]
    assert e["branch"] == "a-br-pt" and e["err"] == {"favicon": 1}


def test_seed_uses_dict_key_when_record_has_no_branch():
    root = _tmp()
    _state(root, {"b-br-pt": {"ts": "2026-07-01 10:00:00",
                              "checks": [{"id": "forms", "issues": []}]}})
    cl.seed_from_state(root)
    assert cl.entries(root)[0]["branch"] == "b-br-pt"


def test_ensure_seeded_runs_once_even_if_shards_deleted():
    """Гейт — маркер, а не порожність: інакше після чистки старих шардів
    міграція заллє все вдруге і подвоїть історію."""
    root = _tmp()
    _state(root, {"a": {"branch": "a", "ts": "2026-07-01 10:00:00",
                        "checks": [{"id": "x", "issues": []}]}})
    assert cl.ensure_seeded(root) == 1
    assert cl.ensure_seeded(root) == 0
    for p in (root / cl.DIRNAME).glob("*.jsonl"):
        p.unlink()
    assert cl.ensure_seeded(root) == 0          # маркер лишився
    assert cl.entries(root) == []


def test_missing_state_file_is_not_an_error():
    root = _tmp()
    assert cl.seed_from_state(root) == 0
    assert cl.ensure_seeded(root) == 0


def test_seed_then_live_run_accumulate():
    """Сід дає точку відліку, живі прогони нарощують історію поверх неї."""
    root = _tmp()
    _state(root, {"a": {"branch": "a", "ts": "2026-07-01 10:00:00",
                        "checks": [{"id": "x", "issues": [{"severity": "error"}]}]}})
    cl.ensure_seeded(root)
    cl.record_run(root, [_run_result("a", {"x": []}, ts="2026-08-01 10:00:00")])
    got = cl.entries(root)
    assert len(got) == 2
    assert got[0]["err"] == {"x": 1} and got[1]["err"] == {}   # полагодили


if __name__ == "__main__":
    run(dict(globals()))
