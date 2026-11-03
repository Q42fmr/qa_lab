"""Збережений скан ClickUp: спільне окремо, особисте окремо.

Скан лежить одним файлом на всіх і перезаписується цілком. Щойно з'явились
особисті токени, це стало щоденною втратою даних: у Петра токен є, у Марії
немає — і кожен її скан витирав би Петрові розшарені таски. Це рівно та
пастка, через яку 01.09.2026 писався `683c305` (біднішим сканом затирався
багатший), тільки тут вона спрацьовувала б не раз, а постійно.

Друге, що це закриває: таска, віддана персонально Петрові, не має з'являтись
у Марії тільки тому, що Петро натиснув «Сканувати».

Стан ізольовано на рівні МОДУЛЯ, до першого тесту: інакше перший же запис
ліг би `clickup_tasks.json` у робоче дерево. `QA_LAB_STATE_DIR` тут головний
(з 04.09 `shared_file()` рахується від нього), chdir лишається для шляхів,
які все ще відносні.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="cu-saved-")
os.environ["QA_LAB_STATE_DIR"] = _TMP
os.environ["MOCK_MODE"] = "1"
os.chdir(_TMP)

from _harness import run                                    # noqa: E402

import app                                                  # noqa: E402


class _Req:
    """Мінімальний запит: ендпоінти беруть користувача з `request.state`."""

    class _State:
        pass

    def __init__(self, uid=""):
        self.state = _Req._State()
        self.state.user = {"id": uid} if uid else {}


PETRO, MARIA = "uid-petro", "uid-maria"


def _task(tid, uid=""):
    t = {"id": tid, "name": tid}
    if uid:
        t["via"], t["via_user"] = "personal", uid
    return t


def _save(uid, tasks):
    app.clickup_save(app.ClickUpSaveRequest(tasks=tasks), _Req(uid))


def _ids(uid):
    return sorted(t["id"] for t in app.clickup_saved(_Req(uid))["tasks"])


def _reset():
    for p in [app.projects.shared_file(app.CU_TASKS),
              app._cu_personal_file(PETRO), app._cu_personal_file(MARIA)]:
        if p.exists():
            p.unlink()


def test_a_personal_task_goes_to_its_own_file():
    _reset()
    _save(PETRO, [_task("common"), _task("shared", PETRO)])
    shared = app._read_cu(app.projects.shared_file(app.CU_TASKS))
    assert [t["id"] for t in shared["tasks"]] == ["common"], shared
    mine = app._read_cu(app._cu_personal_file(PETRO))
    assert [t["id"] for t in mine["tasks"]] == ["shared"], mine


def test_the_owner_sees_both():
    _reset()
    _save(PETRO, [_task("common"), _task("shared", PETRO)])
    assert _ids(PETRO) == ["common", "shared"]


def test_nobody_else_sees_a_task_shared_to_a_person():
    _reset()
    _save(PETRO, [_task("common"), _task("shared", PETRO)])
    assert _ids(MARIA) == ["common"]


def test_a_scan_without_a_token_does_not_erase_someone_elses_tasks():
    """Головний тест файлу: саме тут була б щоденна втрата."""
    _reset()
    _save(PETRO, [_task("common"), _task("shared", PETRO)])
    _save(MARIA, [_task("common")])          # у Марії токена немає
    assert _ids(PETRO) == ["common", "shared"], "особисті таски Петра зникли"
    assert _ids(MARIA) == ["common"]


def test_one_person_cannot_write_into_anothers_file():
    """Штамп ставить сам скан; підроблений у запиті не має відкривати
    чужий файл."""
    _reset()
    _save(MARIA, [_task("forged", PETRO)])
    assert not app._cu_personal_file(PETRO).exists(), "запис поїхав у чужий файл"


def test_an_anonymous_call_keeps_working():
    """`_cu_saved()` без uid кличе, зокрема, оновлення тем фото."""
    _reset()
    _save(PETRO, [_task("common"), _task("shared", PETRO)])
    assert [t["id"] for t in app._cu_saved()["tasks"]] == ["common"]


def test_a_broken_file_does_not_take_the_tab_down():
    _reset()
    app.projects.shared_file(app.CU_TASKS).write_text("{ це не json",
                                                      encoding="utf-8")
    assert app._cu_saved(PETRO)["tasks"] == []


# ------------------------------------------- фоллбек особистого токена

def test_a_dead_personal_token_returns_a_reason_not_an_exception():
    """Те, заради чого весь фоллбек: вʼю і team ходять застосунковим токеном і
    мають приїхати цілими, хоч би що сталось з особистим. Виняток звідси
    поклав би вкладку цілком."""
    real = app.clickup_client.fetch_shared

    def boom(token, include_closed=False):
        raise RuntimeError("401 Token invalid (OAUTH_025)")

    app.clickup_client.fetch_shared = boom
    try:
        tasks, err = app._personal_cu_scan("pk_dead", False)
    finally:
        app.clickup_client.fetch_shared = real
    assert tasks == [] and "OAUTH_025" in err, (tasks, err)


def test_a_working_personal_token_returns_its_tasks():
    real = app.clickup_client.fetch_shared
    app.clickup_client.fetch_shared = lambda token, include_closed=False: [{"id": "s1"}]
    try:
        tasks, err = app._personal_cu_scan("pk_ok", False)
    finally:
        app.clickup_client.fetch_shared = real
    assert [t["id"] for t in tasks] == ["s1"] and err == "", (tasks, err)


run(dict(globals()))
