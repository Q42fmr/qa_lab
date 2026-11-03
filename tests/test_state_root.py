"""Тести кореня стану (QA_LAB_STATE_DIR).

Навіщо він узагалі. Увесь стан лаби — кеші віток, деплої, скріни, журнали і
десяток json-ів — лежить поруч з кодом. У контейнері це шар образу, тобто все
напрацьоване зникає при кожному оновленні. QA_LAB_STATE_DIR дозволяє винести
стан на змонтований volume, не чіпаючи жодного шляху в коді.

Головна вимога, яку тут і перевіряємо: **без цієї змінної не змінюється
рівно нічого**. Розробник запускає лабу нативно, як завжди, і стан лишається
там, де був.
"""
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import projects                                                   # noqa: E402


def _with_env(value):
    """Перезавантажує projects із заданим QA_LAB_STATE_DIR. Повертає модуль."""
    if value is None:
        os.environ.pop("QA_LAB_STATE_DIR", None)
    else:
        os.environ["QA_LAB_STATE_DIR"] = value
    return importlib.reload(projects)


def _restore():
    os.environ.pop("QA_LAB_STATE_DIR", None)
    importlib.reload(projects)


# --------------------------------------------------------------- дефолт

def test_default_state_root_is_cwd():
    """Без змінної — корінь ".", тобто поточна поведінка байт-у-байт."""
    p = _with_env(None)
    try:
        assert p.state_root() == Path("."), p.state_root()
    finally:
        _restore()


def test_default_keeps_active_file_in_place():
    p = _with_env(None)
    try:
        assert p.ACTIVE_FILE == Path("active_project.json"), p.ACTIVE_FILE
    finally:
        _restore()


def test_default_project_roots_are_unchanged():
    """white-pages historically живе в корені, vue — у projects/vue."""
    p = _with_env(None)
    try:
        os.environ.pop("GITLAB_TOKEN", None)
        os.environ["VUE_GITLAB_PROJECT"] = "development/new-white-front"
        os.environ["VUE_GITLAB_TOKEN"] = "glpat-test"
        p.init()
        roots = {x["id"]: x["root"] for x in p.all_state_dirs()}
        assert roots["white-pages"] == Path("."), roots
        assert roots["vue"] == Path("projects") / "vue", roots
    finally:
        os.environ.pop("VUE_GITLAB_PROJECT", None)
        os.environ.pop("VUE_GITLAB_TOKEN", None)
        _restore()


# --------------------------------------------------------------- зі змінною

def test_state_root_follows_the_env():
    p = _with_env("/srv/state")
    try:
        assert p.state_root() == Path("/srv/state"), p.state_root()
    finally:
        _restore()


def test_active_file_moves_with_the_root():
    p = _with_env("/srv/state")
    try:
        assert p.ACTIVE_FILE == Path("/srv/state/active_project.json"), p.ACTIVE_FILE
    finally:
        _restore()


def test_project_roots_move_with_the_root():
    p = _with_env("/srv/state")
    try:
        os.environ.pop("GITLAB_TOKEN", None)
        os.environ["VUE_GITLAB_PROJECT"] = "development/new-white-front"
        os.environ["VUE_GITLAB_TOKEN"] = "glpat-test"
        p.init()
        roots = {x["id"]: x["root"] for x in p.all_state_dirs()}
        assert roots["white-pages"] == Path("/srv/state"), roots
        assert roots["vue"] == Path("/srv/state/projects/vue"), roots
    finally:
        os.environ.pop("VUE_GITLAB_PROJECT", None)
        os.environ.pop("VUE_GITLAB_TOKEN", None)
        _restore()


def test_state_file_lands_under_the_root():
    """state_file() — через нього ходять усі json-и стану проєкту."""
    p = _with_env("/srv/state")
    try:
        os.environ.pop("GITLAB_TOKEN", None)
        p.init()
        assert p.state_file("branches.json") == Path("/srv/state/branches.json"), \
            p.state_file("branches.json")
    finally:
        _restore()


# --------------------------- модулі, що тримають власні константи стану

def test_photo_db_lives_under_the_state_root():
    """«Фото БД» пише в корінь стану, а не в CWD.

    Константа переїхала у `app.py`, коли автор зніс `local_whites` (знімок
    31.08): у нього вона стоїть як `Path("photo_db.json")`, у нас — від
    `state_root()`. Рядок наш і лежить у файлі, який автор править щознімка,
    тож при кожному наступному злитті він у зоні ризику. Ціна втрати: у проді
    корінь стану — том `qa_lab-state`, а CWD — `/app`, тобто база фото поїхала б
    у шар контейнера і зникла б з першим же оновленням образу.
    """
    import app
    assert app.PHOTO_DB_FILE == projects.state_root() / "photo_db.json", \
        app.PHOTO_DB_FILE


def test_shared_state_lives_under_the_root():
    """Стан рівня воркспейсу (скан ClickUp, теми коментарів, черга) - у корені
    стану, а не в CWD.

    До 04.09.2026 `shared_file()` віддавав `Path(name)`, тобто відносний шлях.
    Нативно це те саме місце, а в проді - шар контейнера замість тому: файл
    жив рівно до наступного образу. Помітити це можна було тільки за наслідком
    («скан щоразу порожній після деплою»), бо жодної помилки тут не виникає.
    """
    p = _with_env("/srv/state")
    try:
        assert p.shared_file("clickup_tasks.json") == Path("/srv/state/clickup_tasks.json"), \
            p.shared_file("clickup_tasks.json")
    finally:
        _restore()


def test_shared_state_defaults_to_cwd():
    """Без змінної - поведінка байт-у-байт та сама, що була."""
    p = _with_env(None)
    assert p.shared_file("clickup_tasks.json") == Path("clickup_tasks.json"), \
        p.shared_file("clickup_tasks.json")


def test_deploy_pids_file_follows_the_root():
    """Реєстр pid-ів спільний на всі проєкти — тому саме в КОРЕНІ стану."""
    _with_env("/srv/state")
    try:
        import deployer
        d = importlib.reload(deployer)
        assert d._PIDS_FILE == Path("/srv/state/.deploy_pids.json"), d._PIDS_FILE
    finally:
        _restore()
        importlib.reload(sys.modules["deployer"])


def test_deploy_pids_file_defaults_to_cwd():
    _with_env(None)
    import deployer
    d = importlib.reload(deployer)
    assert d._PIDS_FILE == Path(".deploy_pids.json"), d._PIDS_FILE


if __name__ == "__main__":
    run(dict(globals()))
