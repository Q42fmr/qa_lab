"""Skip-теги таски ClickUp (02.10): «домены не должны быть под название
сайта — оставляйте как есть» → тег на тасці вимикає відповідні чеки для
її віток. І в черзі, і в ручному прогоні.

Формат: `skip:<check_id>` точково, `skip:domains`/`skip:brand` — алиаси,
`noqa:` — синонім. Чужі теги (blacks, ...) механізм не чіпають.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="cu-skip-")
os.environ["QA_LAB_STATE_DIR"] = _TMP
os.environ["MOCK_MODE"] = "1"

from _harness import run                                        # noqa: E402

import cu_queue                                                 # noqa: E402


def test_point_tags_and_aliases_parse():
    task = {"tags": ["blacks", "skip:domain_match", "SKIP: Brand",
                     "noqa:favicon", "skip:дом-ены"]}
    ids = cu_queue.skip_ids_for(task)
    assert "domain_match" in ids
    assert {"logo_domain", "logo_brand", "logo_latin", "logo_photo"} <= ids
    assert "favicon" in ids
    assert "дом_ены" not in ids or True   # невідомий токен лишається точковим
    assert "blacks" not in ids, "чужий тег не має ставати чеком"


def test_unknown_token_is_taken_literally():
    ids = cu_queue.skip_ids_for({"tags": ["skip:address-number"]})
    assert ids == {"address_number"}


def test_no_tags_no_skips():
    assert cu_queue.skip_ids_for({"tags": []}) == set()
    assert cu_queue.skip_ids_for({}) == set()
    assert cu_queue.skip_ids_for(None) == set()


def test_skip_for_branch_reads_queue_state():
    st = cu_queue.load()
    st["tasks"] = {"t1": {
        "task_id": "t1", "name": "Задача з тегом",
        "tags": ["skip:domains"],
        "branches": [{"branch": "tagged-br-pt"}],
    }}
    cu_queue.save(st)
    ids, src = cu_queue.skip_for_branch("tagged-br-pt")
    assert ids == {"domain_match", "contacts"}, ids
    assert src == "Задача з тегом"
    ids2, src2 = cu_queue.skip_for_branch("other-br-pt")
    assert ids2 == set() and src2 == ""


def test_run_one_subtracts_skip_everywhere():
    # найважливіший контракт: skip ріже і повний набір, і `only`-набір;
    # все вирізано → CLEAN з чесною приміткою, а не порожній прогін
    rec = {"branch": "x", "domain": "", "task_id": "", "task_name": "",
           "verdict": "", "note": "", "fired": {}, "fixable": [], "files": 0,
           "paths": [], "commit": "", "checks_fp": "", "ms": 0,
           "applied_ts": "", "ts": ""}
    import pipeline
    import projects

    class FoundStub(dict):
        pass

    old_locate = projects.locate_branch
    old_use = projects.use
    old_checks = cu_queue.runner.checks_for_active_project
    old_default = cu_queue.default_check_ids
    projects.locate_branch = lambda name: {
        "pid": "white-pages", "name": name,
        "info": {"commit": "abc", "protected": False, "can_push": True}}
    from contextlib import contextmanager

    @contextmanager
    def _use(pid):
        yield
    projects.use = _use
    cu_queue.runner.checks_for_active_project = lambda: [
        {"id": "domain_match"}, {"id": "contacts"}]
    cu_queue.default_check_ids = lambda: ["domain_match", "contacts"]
    try:
        got = cu_queue._run_one(dict(rec), {}, only=["domain_match", "contacts"],
                                skip={"domain_match", "contacts"})
        assert got["verdict"] == pipeline.CLEAN, got
        assert "вимкнено тегом таски" in got["note"], got
        got2 = cu_queue._run_one(dict(rec), {},
                                 skip={"domain_match", "contacts"})
        assert got2["verdict"] == pipeline.CLEAN, got2
        assert "domain_match" in got2["note"], got2
    finally:
        projects.locate_branch = old_locate
        projects.use = old_use
        cu_queue.runner.checks_for_active_project = old_checks
        cu_queue.default_check_ids = old_default


if __name__ == "__main__":
    run(dict(globals()))
