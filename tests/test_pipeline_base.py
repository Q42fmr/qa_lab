"""Спільна основа машинних конвеєрів: лок, дії коміту, накладка проєкту.

Три речі, які до 03.09.2026 лежали копіями або взагалі не існували, а тепер
є фундаментом годинного автофікса:

* `runner.pipeline_lock` — ОДИН лок на процес, спільний з ШІ-мостом.
  Два локи означали б, що два машинні конвеєри не бачать один одного і
  ганяють `run_checks` по одному знімку одночасно;
* `runner.actions_for()` / `apply_to_snapshot()` — три копії того самого
  перетворення `compute_fixes` → коміт; кожна нова правка мусила знайти всі;
* `projects.use()` — проєкт «на цей потік». Фоновий воркер не сміє чіпати
  глобальний активний проєкт: людина побачила б, що UI сам перемкнувся.
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                        # noqa: E402

import ai_bridge                                                # noqa: E402
import projects                                                 # noqa: E402
import runner                                                   # noqa: E402


# ---------------------------------------------------------------- лок
def test_the_bridge_and_autofix_share_one_lock():
    assert ai_bridge._run_lock is runner.pipeline_lock, \
        "ШІ-міст мусить брати той самий лок, що й автофікс"


def test_the_lock_actually_locks():
    got = []

    def other():
        got.append(runner.pipeline_lock.acquire(timeout=0.2))

    with runner.pipeline_lock:
        t = threading.Thread(target=other)
        t.start()
        t.join()
    assert got == [False], "лок пустив другого всередину"


# ---------------------------------------------------------------- дії коміту
def test_actions_carry_all_three_kinds():
    actions = runner.actions_for([
        {"type": "edit", "path": "a.php", "old": "x", "new": "y"},
        {"type": "create", "path": "new.php", "new": "z"},
        {"type": "delete", "path": "old.php"},
    ])
    assert actions == [
        {"action": "update", "file_path": "a.php", "content": "y"},
        {"action": "create", "file_path": "new.php", "content": "z"},
        {"action": "delete", "file_path": "old.php"},
    ], actions


def test_a_change_without_a_type_is_an_edit():
    """`compute_fixes` кладе "type" завжди, але хук чека — не обов'язково."""
    assert runner.actions_for([{"path": "a.php", "new": "y"}]) == [
        {"action": "update", "file_path": "a.php", "content": "y"}]


def test_snapshot_gets_what_was_committed():
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            os.environ.pop("QA_LAB_STATE_DIR", None)
            base = Path(runner.snapshot_dir("br"))
            base.mkdir(parents=True, exist_ok=True)
            (base / ".snapshot.json").write_text('{"branch": "br"}', encoding="utf-8")
            (base / "a.php").write_text("old", encoding="utf-8")
            (base / "gone.php").write_text("bye", encoding="utf-8")

            runner.apply_to_snapshot("br", [
                {"type": "edit", "path": "a.php", "new": "new"},
                {"type": "create", "path": "deep/new.php", "new": "made"},
                {"type": "delete", "path": "gone.php"},
            ])

            assert (base / "a.php").read_text(encoding="utf-8") == "new"
            assert (base / "deep" / "new.php").read_text(encoding="utf-8") == "made"
            assert not (base / "gone.php").exists()
        finally:
            os.chdir(cwd)


def test_deleting_a_file_that_is_already_gone_is_not_an_error():
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            base = Path(runner.snapshot_dir("br"))
            base.mkdir(parents=True, exist_ok=True)
            runner.apply_to_snapshot("br", [{"type": "delete", "path": "nope.php"}])
        finally:
            os.chdir(cwd)


# ---------------------------------------------------------------- проєкт
def _two_projects():
    projects._registry = {
        "white-pages": {"id": "white-pages", "title": "php", "type": "php",
                        "gitlab_path": "x/y", "token": "", "mock": True,
                        "root": Path("."),},
        "vue": {"id": "vue", "title": "node", "type": "node",
                "gitlab_path": "x/z", "token": "t", "mock": True,
                "root": Path("projects/vue")},
    }
    projects._current = "white-pages"


def test_use_switches_only_inside_the_block():
    _two_projects()
    assert projects.current_id() == "white-pages"
    with projects.use("vue"):
        assert projects.current_id() == "vue"
        assert projects.ptype() == "node"
        assert projects.state_dir() == Path("projects/vue")
    assert projects.current_id() == "white-pages"
    assert projects.ptype() == "php"


def test_use_does_not_touch_the_global_or_the_file():
    """Найважливіше: людина в UI не має побачити, що проєкт перемкнувся сам."""
    _two_projects()
    with projects.use("vue"):
        assert projects._current == "white-pages", "глобал зіпсовано"
    assert projects._current == "white-pages"


def test_use_restores_the_project_after_an_exception():
    _two_projects()
    try:
        with projects.use("vue"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert projects.current_id() == "white-pages"


def test_use_nests():
    _two_projects()
    with projects.use("vue"):
        with projects.use("white-pages"):
            assert projects.current_id() == "white-pages"
        assert projects.current_id() == "vue"


def test_use_refuses_an_unknown_project():
    _two_projects()
    try:
        with projects.use("nope"):
            pass
    except ValueError:
        return
    raise AssertionError("невідомий проєкт мусить падати, а не мовчати")


def test_a_worker_thread_does_not_see_the_override():
    """ContextVar не переїжджає в інший потік — і це задокументована межа,
    а не випадковість: пул усередині прогону працював би з чужим проєктом."""
    _two_projects()
    seen = []
    with projects.use("vue"):
        t = threading.Thread(target=lambda: seen.append(projects.current_id()))
        t.start()
        t.join()
    assert seen == ["white-pages"], seen



# ------------------------------------------------- пошук вітки по проєктах
class _Cl:
    """Клієнт, який знає рівно одну вітку і чутливий до регістру, як GitLab."""

    def __init__(self, known, protected=False):
        self.known, self.protected = known, protected

    def branch(self, name):
        if name != self.known:
            raise ValueError(f"404 {name}")
        return {"name": name, "commit": "abc1234",
                "protected": self.protected, "can_push": not self.protected}


def _clients(php=None, vue=None):
    _two_projects()
    projects.client_for = lambda pid: {"white-pages": php, "vue": vue}[pid]


def test_a_branch_is_found_in_the_project_that_has_it():
    """Таска не каже, якого типу вайт, і vue-вайти регулярно заводять у
    php-проєкт: заміряно, 20 з 20 проблемних віток журналу лежали в node-репо."""
    was = projects.client_for
    try:
        _clients(php=_Cl("nope"), vue=_Cl("nwf-a"))
        got = projects.locate_branch("nwf-a")
        assert got and got["pid"] == "vue" and got["name"] == "nwf-a", got
    finally:
        projects.client_for = was


def test_a_branch_that_is_nowhere_is_none_not_an_exception():
    was = projects.client_for
    try:
        _clients(php=_Cl("x"), vue=_Cl("y"))
        assert projects.locate_branch("ghost") is None
    finally:
        projects.client_for = was


def test_the_case_fallback_still_works_through_locate():
    """`AUTO_...` з ClickUp при вітці `auto_...` у репо."""
    was = projects.client_for
    try:
        _clients(php=_Cl("auto_x"), vue=_Cl("nope"))
        got = projects.locate_branch("AUTO_X")
        assert got and got["name"] == "auto_x", got
    finally:
        projects.client_for = was


def test_protection_comes_back_with_the_branch():
    """Без цих полів машинний конвеєр дізнавався б про захист лише з 403."""
    was = projects.client_for
    try:
        _clients(php=_Cl("main", protected=True), vue=_Cl("nope"))
        got = projects.locate_branch("main")
        assert got["info"]["protected"] and got["info"]["can_push"] is False, got
    finally:
        projects.client_for = was


run(dict(globals()))
