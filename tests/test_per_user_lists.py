"""Робочий список віток — у кожної людини свій.

Задача 21.09.2026 («разные пользователи не мешали работе друг друга»). Список
зліва був один на всіх: «Очистити список», «Закрити чисті» чи імпорт із
заміною в одного прибирали вітки з-під рук іншого.

Тепер у кожного `branches.<uid>.json`. Три речі, які тут стережуться:

* свій список правиться лише свій — через справжній middleware;
* після переходу ніхто не прокидається з порожнім списком: поки людина
  нічого не правила, вона бачить старий спільний, а перша правка кладе його
  КОПІЮ в особистий файл;
* «Архів» — це знімки, яких немає в ЖОДНОМУ списку, тож і його показ, і
  «🧹 архів», і видалення знімка рахують списки всіх людей. Інакше одна
  людина чистить архів — і стирає робочі знімки іншої.
"""
import contextvars
import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

# Ізоляція — до першого імпорту: тест не сміє торкатись справжнього стану.
_STATE = Path(tempfile.mkdtemp(prefix="qa_lab-lists-"))
os.environ["QA_LAB_STATE_DIR"] = str(_STATE)
os.environ.setdefault("MOCK_MODE", "1")
os.environ["QA_LAB_SECRET_KEY"] = "test-secret-key"

import _asgi                                                      # noqa: E402
import ai_bridge                                                  # noqa: E402
import attribution                                                # noqa: E402
import projects                                                   # noqa: E402
import runner                                                     # noqa: E402
import app                                                        # noqa: E402
from fastapi import HTTPException                                 # noqa: E402

PHP, VUE = "white-pages", "vue"


class _GitLab:
    """Знає або будь-яку вітку (`known=None`), або лише перелічені."""

    def __init__(self, known=None):
        self.known = known

    def branch(self, name):
        if self.known is not None and name not in self.known:
            raise RuntimeError(f"404 Client Error: Not Found for url: .../{name}")
        return {"name": name, "commit": "abc1234", "updated": ""}

    def branch_url(self, name):
        return f"https://gl.test/-/tree/{name}"


def _fresh(php=None, vue=None) -> Path:
    """Нова тека стану, php (живий, не mock) і за потреби vue."""
    root = Path(tempfile.mkdtemp(dir=_STATE))
    projects._registry = {PHP: {"id": PHP, "title": "php", "type": "php",
                                "gitlab_path": "t/php", "token": "x",
                                "mock": False, "root": root}}
    projects._clients = {PHP: php or _GitLab()}
    if vue is not None:
        projects._registry[VUE] = {"id": VUE, "title": "node", "type": "node",
                                   "gitlab_path": "t/vue", "token": "x",
                                   "mock": False, "root": root / "projects" / "vue"}
        projects._clients[VUE] = vue
    projects._current = PHP
    return root


def as_person(uid, fn, *args, **kwargs):
    """Виклик так, як його бачить ендпоінт після middleware: актор — людина."""
    def inside():
        attribution.set_actor({"id": uid, "name": uid})
        return fn(*args, **kwargs)
    return contextvars.copy_context().run(inside)


def _list(uid):
    return as_person(uid, app.load_branch_list)


def _add(uid, name):
    return as_person(uid, app.add_branch, app.BranchName(name=name))


def _request(user):
    """Запит, на якому middleware вже поклав людину."""
    return types.SimpleNamespace(state=types.SimpleNamespace(user=user))


def _snapshot(name):
    d = runner.snapshot_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    (d / ".snapshot.json").write_text(json.dumps({"branch": name, "commit": "abc"}),
                                      encoding="utf-8")
    return d


# ------------------------------------------------------ свій список

def test_each_person_edits_only_their_own_list():
    _fresh()
    _add("anna", "anna-br-pt")
    _add("bohdan", "bohdan-br-pt")
    assert _list("anna") == ["anna-br-pt"]
    assert _list("bohdan") == ["bohdan-br-pt"]
    as_person("bohdan", app.clear_branches)
    assert _list("bohdan") == []
    assert _list("anna") == ["anna-br-pt"], "чужа «Очистити список» зачепила мій"


def test_the_list_follows_the_session_through_the_middleware():
    """Той самий контракт, але як його бачить браузер: хто сесія — того й
    список. Ловить випадок, коли middleware перестане класти актора."""
    root = _fresh()
    anna, bohdan = _asgi.people(root / "users.json", "anna", "bohdan")
    status, _ = _asgi.call(app.app, "POST", "/api/branches/add", anna,
                           {"name": "anna-br-pt"})
    assert status == 200, status
    _s, mine = _asgi.call(app.app, "GET", "/api/branches", anna)
    _s, theirs = _asgi.call(app.app, "GET", "/api/branches", bohdan)
    assert [b["name"] for b in mine] == ["anna-br-pt"], mine
    assert theirs == [], theirs


def test_the_first_edit_starts_from_the_shared_list_not_from_empty():
    root = _fresh()
    app.write_json_state(root / "branches.json", ["old-1-br", "old-2-br"])
    assert _list("anna") == ["old-1-br", "old-2-br"], "після переходу список зник"
    as_person("anna", app.remove_branch, "old-1-br")
    assert _list("anna") == ["old-2-br"]
    assert _list("bohdan") == ["old-1-br", "old-2-br"], "моя правка зачепила колегу"
    assert app.read_json_state(root / "branches.json", None) == ["old-1-br", "old-2-br"]


def test_a_call_without_a_person_keeps_the_shared_list():
    """Міст і вебхук людини не мають — у них лишається спільний файл."""
    root = _fresh()
    app.mutate_branch_list(app._with("svc-br"))
    assert app.read_json_state(root / "branches.json", None) == ["svc-br"]


def test_a_hostile_uid_cannot_leave_the_project_dir():
    root = _fresh()
    path = as_person("../../etc/evil", app.branch_list_file)
    assert path.parent == root, path
    assert "/" not in path.name and ".." not in path.name, path


# ------------------------------------------------------ архів: списки ВСІХ

def test_the_archive_does_not_show_what_a_colleague_is_working_on():
    _fresh()
    _snapshot("anna-br-pt")
    _snapshot("nobody-br-pt")
    _add("anna", "anna-br-pt")
    names = {a["name"] for a in as_person("bohdan", app.archive)}
    assert names == {"nobody-br-pt"}, names


def test_cleaning_the_archive_does_not_delete_a_colleague_s_snapshot():
    _fresh()
    mine, orphan = _snapshot("anna-br-pt"), _snapshot("nobody-br-pt")
    _add("anna", "anna-br-pt")
    as_person("bohdan", app.storage_clean, app.CleanRequest(archive=True),
              _request({"id": "bohdan"}))
    assert mine.exists(), "«🧹 архів» колеги стер мій робочий знімок"
    assert not orphan.exists()


def test_deleting_a_snapshot_on_a_colleague_s_list_is_refused():
    _fresh()
    d = _snapshot("anna-br-pt")
    _add("anna", "anna-br-pt")
    try:
        as_person("bohdan", app.archive_remove, "anna-br-pt")
    except HTTPException as e:
        assert e.status_code == 400
    else:
        raise AssertionError("знімок з чужого списку видалено")
    assert d.exists()


def test_cleaning_deploys_and_screens_is_for_the_admin_only():
    """deploy/ і screens/ — спільні: чистка гасить чужі деплої і стирає чужі
    скріни. Архів чистити може кожен — він рахує списки всіх."""
    _fresh()
    for req in (app.CleanRequest(deploy=True), app.CleanRequest(screens=True)):
        try:
            as_person("bohdan", app.storage_clean, req, _request({"id": "bohdan"}))
        except HTTPException as e:
            assert e.status_code == 403
        else:
            raise AssertionError(f"не-адмін почистив {req}")
    got = as_person("root", app.storage_clean, app.CleanRequest(screens=True),
                    _request({"id": "root", "is_admin": True}))
    assert got["removed"] == ["screens"], got


def test_stopping_every_deploy_is_for_the_admin_only():
    _fresh()
    try:
        app.deploys_stop_all(_request({"id": "bohdan"}))
    except HTTPException as e:
        assert e.status_code == 403
    else:
        raise AssertionError("не-адмін погасив деплої всіх")


# ------------------------------------------------------ імпорт

def test_an_import_lands_in_the_importer_s_list():
    _fresh()
    req = app.ClickUpImportRequest(tasks=[{"id": "t1", "name": "T", "url": "",
                                           "branches": ["imp-br-pt"]}])
    as_person("anna", app.clickup_import, req)
    assert _list("anna") == ["imp-br-pt"]
    assert _list("bohdan") == []


def test_a_vue_branch_lands_in_the_importer_s_vue_list():
    """Перенос php → vue при імпорті — теж у список ТІЄЇ людини, у vue."""
    root = _fresh(php=_GitLab(known=set()), vue=_GitLab(known={"nwf-x-br-pt"}))
    req = app.ClickUpImportRequest(tasks=[{"id": "t1", "name": "T", "url": "",
                                           "branches": ["nwf-x-br-pt"]}])
    got = as_person("anna", app.clickup_import, req)
    assert [m["branch"] for m in got["moved"]] == ["nwf-x-br-pt"], got
    vue_dir = root / "projects" / "vue"
    assert app.read_json_state(vue_dir / "branches.anna.json", None) == ["nwf-x-br-pt"]
    assert not (vue_dir / "branches.bohdan.json").exists()
    assert not (vue_dir / "branches.json").exists(), "перенос ліг у спільний список"


def test_the_bridge_still_knows_everyone_s_branches():
    _fresh()
    _add("anna", "anna-br-pt")
    _add("bohdan", "bohdan-br-pt")
    known = set(ai_bridge.known_branches())
    assert {"anna-br-pt", "bohdan-br-pt"} <= known, known



# ------------------------------------------------ відкат 23.09.2026

def test_lists_made_before_the_rollback_are_set_aside_once():
    """Особисті списки жили в проді ~35 хв (13:44-14:19 23.09), потім деплой
    відкотили, і люди правили СПІЛЬНИЙ список старою версією. Копія тих 35
    хвилин старша за всю ту роботу — після повторного деплою людина бачила б
    свій список станом на 14:19. Тому такі копії разово відкладаються (не
    видаляються), і людина знову стартує зі спільного."""
    root = _fresh(vue=_GitLab())
    marker = projects.shared_file(f"branches.{app.RETIRED}")
    marker.unlink(missing_ok=True)
    _add("anna", "stale-br-pt")                           # копія до відкату
    vue_copy = projects.state_dir_for(VUE) / "branches.bohdan.json"
    vue_copy.write_text(json.dumps(["nwf-stale-br-pt"]), encoding="utf-8")
    (root / "branches.json").write_text(json.dumps(["after-rollback-br-pt"]),
                                        encoding="utf-8")  # робота після відкату
    assert _list("anna") == ["stale-br-pt"]

    assert app.retire_rolled_back_lists() == 2
    assert _list("anna") == ["after-rollback-br-pt"], "лишилась копія до відкату"
    assert (root / f"branches.anna.json.{app.RETIRED}").exists(), "копію стерто, а не відкладено"
    assert not vue_copy.exists()
    assert "stale-br-pt" not in app.all_listed(), "відкладена копія досі тримає знімки"

    # Разово: копія, зроблена вже ПІСЛЯ деплою, — жива робота людини.
    _add("anna", "fresh-br-pt")
    assert app.retire_rolled_back_lists() == 0
    assert "fresh-br-pt" in _list("anna")

if __name__ == "__main__":
    run(dict(globals()))
