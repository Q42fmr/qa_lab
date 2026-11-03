"""Проєкт php/vue — у кожної людини свій, а не один на сервер.

Задача 21.09.2026 від колеги-QA: «чтобы разные пользователи не мешали работе
друг друга». Перше, що заважало, — перемикач проєкту в шапці: `/api/project`
кликав `projects.set_current()`, тобто переводив у vue ВЕСЬ процес. Колега в
php-вітках після цього синкав і комітив уже у vue-репо, а пачка, яка йшла в
ту мить, розрізалась між двома проєктами — пули потоків читали глобал на
кожному завданні.

Тепер вибір лежить у записі користувача, middleware кладе його на запит, а
пули й фонові потоки, запущені з запиту, везуть його з собою
(`projects.Pool`, `projects.thread`). Тут стережеться і перше, і друге: одна
людина перемкнулась — у другої нічого не змінилось; пачка у vue-людини не
провалюється в php-дефолт.
"""
import contextvars
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

# Ізоляція — ДО першого імпорту: `projects.ACTIVE_FILE` рахується при імпорті,
# і тест не сміє ні прочитати, ні записати справжній стан лаби.
_STATE = Path(tempfile.mkdtemp(prefix="qa_lab-per-user-"))
os.environ["QA_LAB_STATE_DIR"] = str(_STATE)
os.environ.setdefault("MOCK_MODE", "1")
os.environ["QA_LAB_SECRET_KEY"] = "test-secret-key"

import _asgi                                                      # noqa: E402
import attribution                                                # noqa: E402
import auth                                                       # noqa: E402
import preview                                                    # noqa: E402
import projects                                                   # noqa: E402
import users                                                      # noqa: E402
# `app` — теж до тестів: його імпорт кличе `projects.init()`, який
# перебудовує реєстр з оточення. Імпорт посеред тесту стер би реєстр із
# двома проєктами, який тест щойно поставив.
import app                                                        # noqa: E402

PHP, VUE = "white-pages", "vue"


def _registry():
    """Два проєкти, обидва mock: `/api/status` тоді не ходить у GitLab."""
    projects._registry = {
        PHP: {"id": PHP, "title": "php", "type": "php", "gitlab_path": "t/php",
              "token": "", "mock": True, "root": _STATE},
        VUE: {"id": VUE, "title": "node", "type": "node", "gitlab_path": "t/vue",
              "token": "", "mock": True, "root": _STATE / "projects" / "vue"},
    }
    projects._clients = {}
    projects._current = PHP


def _people():
    """Свіже сховище з двома людьми. Повертає їхні uid."""
    return _asgi.people(_STATE / f"users-{os.urandom(4).hex()}.json", "anna", "bohdan")


def _call(method, path, uid=None, body=None):
    return _asgi.call(app.app, method, path, uid, body)


def _project_of(uid):
    status, data = _call("GET", "/api/status", uid)
    assert status == 200, (status, data)
    return data["project"]


# ------------------------------------------------------ сам контракт

def test_one_person_switching_does_not_move_another():
    _registry()
    anna, bohdan = _people()
    assert _project_of(anna) == PHP and _project_of(bohdan) == PHP

    status, data = _call("POST", "/api/project", anna, {"id": VUE})
    assert status == 200, (status, data)
    assert data["project"] == VUE and data["ptype"] == "node", data

    assert _project_of(anna) == VUE
    assert _project_of(bohdan) == PHP, "перемикач однієї людини перемкнув іншу"


def test_the_process_default_is_not_touched():
    """Саме глобал і був поломкою: його читали всі, включно з фоновою
    роботою. Вибір людини не сміє ні змінити його, ні записати на диск."""
    _registry()
    anna, _ = _people()
    assert _STATE in projects.ACTIVE_FILE.parents, "тест дивиться в справжній стан"
    projects.ACTIVE_FILE.unlink(missing_ok=True)
    _call("POST", "/api/project", anna, {"id": VUE})
    assert projects._current == PHP
    assert not projects.ACTIVE_FILE.exists(), "вибір людини ліг у дефолт процесу"


def test_the_choice_lives_in_the_person_record():
    """Переживає і кеш сесії, і рестарт процесу: лежить у записі
    користувача, а не в пам'яті."""
    _registry()
    anna, _ = _people()
    _call("POST", "/api/project", anna, {"id": VUE})
    assert users.store().get(anna).get("project") == VUE
    auth.invalidate()
    assert _project_of(anna) == VUE


def test_an_unknown_project_is_refused_and_changes_nothing():
    _registry()
    anna, _ = _people()
    status, _data = _call("POST", "/api/project", anna, {"id": "nope"})
    assert status == 400, status
    assert _project_of(anna) == PHP
    assert not users.store().get(anna).get("project")


def test_a_stale_choice_falls_back_to_the_default():
    """У записі може лежати проєкт, якого вже немає в реєстрі (вимкнули
    `VUE_GITLAB_*`). Людина мусить потрапити в дефолт, а не в 500."""
    _registry()
    anna, _ = _people()
    users.store().update(anna, {"project": "gone"})
    auth.invalidate()
    assert _project_of(anna) == PHP


# ------------------------------------------------------ пули й потоки

def test_the_pool_carries_the_project_into_every_task():
    _registry()
    with projects.use(VUE):
        with projects.Pool(max_workers=4) as ex:
            seen = list(ex.map(lambda _: projects.current_id(), range(16)))
    assert seen == [VUE] * 16, seen


def test_a_bare_pool_falls_back_to_the_default():
    """Документує, чому `Pool` існує: голий пул не несе контексту, і пачка
    vue-людини пішла б у php-кеш."""
    _registry()
    with projects.use(VUE):
        with ThreadPoolExecutor(max_workers=2) as ex:
            seen = set(ex.map(lambda _: projects.current_id(), range(4)))
    assert seen == {PHP}, seen


def test_the_pool_carries_the_signing_actor_too():
    """Той самий контекст везе й актора підпису — коміт з пулу не втратить
    імені людини."""
    def inside():
        attribution.set_actor({"name": "Anna"})
        with projects.Pool(max_workers=2) as ex:
            return set(ex.map(lambda _: attribution.actor_name(), range(4)))
    assert contextvars.copy_context().run(inside) == {"Anna"}


def test_a_thread_started_from_a_request_keeps_the_project():
    _registry()
    seen = []
    with projects.use(VUE):
        t = projects.thread(lambda: seen.append(projects.current_id()))
    t.join(5)
    assert seen == [VUE], seen


def test_the_preview_stops_a_deploy_in_its_own_project():
    """Сесію закриває не обов'язково той, хто її відкривав, і не з того
    проєкту: TTL спрацьовує на чужому запиті, а ключ деплою рахується від
    проєкту поточного контексту. Гасити треба в проєкті СЕСІЇ — інакше
    vue-деплой лишається сиротою."""
    _registry()
    stopped = []
    preview.wire(on_close=lambda br: stopped.append((br, projects.current_id())))
    try:
        with projects.use(VUE):
            preview.open_session("nwf-anna-br-pt", 9100, uid="anna")
        with projects.use(PHP):
            preview.close("anna")
        assert stopped == [("nwf-anna-br-pt", VUE)], list(stopped)
    finally:
        preview.close_all()
        preview.wire(on_close=None)


# ------------------------------------------------------ гарда

def _func_body(src: str, name: str) -> str:
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", src, re.S | re.M)
    assert m, f"не знайшов def {name} — тест застарів"
    return m.group(0)


def test_nothing_serving_a_person_starts_a_bare_pool_or_thread():
    """Новий пул у ендпоінті, зроблений «як завжди», тихо повертає роботу в
    дефолтний проєкт. Ловимо це тут, а не в проді."""
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "ThreadPoolExecutor" not in app_src, \
        "app.py: пул — лише через projects.Pool"
    assert not re.search(r"threading\.Thread\(", app_src), \
        "app.py: потік із запиту — лише через projects.thread"

    dep_src = (ROOT / "deployer.py").read_text(encoding="utf-8")
    assert not re.search(r"\bThread\(", dep_src), \
        "deployer.py: вотчер і nuxt-білд — лише через projects.thread"

    vis_src = (ROOT / "visual_runner.py").read_text(encoding="utf-8")
    body = _func_body(vis_src, "run_many")
    assert "projects.Pool(" in body and "ThreadPoolExecutor" not in body, \
        "visual_runner.run_many: вітки мусять ганятись у проєкті людини"


if __name__ == "__main__":
    run(dict(globals()))
