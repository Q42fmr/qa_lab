"""Пачка: єдине місце черги, яке пише назовні.

Три властивості, за які тут відповідаємо:

* **фікси рахуються наново.** Між прогоном і натисканням вітка могла поїхати;
  класти в коміт учорашній результат означало б обіцяти одне, а зробити інше;
* **відмова однієї вітки не валить пачку** — у проді 28.08 двадцять відмов
  виглядали як «коміт не працює», і причини не було ніде;
* **у ClickUp — один коментар на таску і лише про успіх.** Таску читають
  фронти, і «лаба не змогла» для них не дія, а шум.

Стан ізольовано на рівні МОДУЛЯ; жодна справжня мережа тут не смикається.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="cu-apply-")
os.environ["QA_LAB_STATE_DIR"] = _TMP
os.environ["MOCK_MODE"] = "1"

from _harness import run                                        # noqa: E402

import clickup_client                                           # noqa: E402
import cu_queue                                                 # noqa: E402
import pipeline                                                 # noqa: E402
import projects                                                 # noqa: E402
import runner                                                   # noqa: E402

projects.init()
cu_queue.start = lambda: None


class _Client:
    def __init__(self, fail=None):
        self.fail, self.commits = fail, []

    def commit(self, branch, message, actions):
        if self.fail and branch in self.fail:
            raise RuntimeError(self.fail[branch])
        self.commits.append((branch, message, actions))
        return {"id": f"sha-{branch}"}


def _seed(verdict=pipeline.WOULD_FIX, branches=("nwf-a", "nwf-b")):
    """Кладе в стан таску, ніби її щойно прогнала черга."""
    st = dict(cu_queue._default_state)
    st.update(intake=True, run=True, counters={"accepted": 0, "skipped": 0, "events": 0},
              tasks={"t1": {
                  "task_id": "t1", "name": "[p-52] whites", "state": "done",
                  "branches": [{"branch": b, "project": "white-pages",
                                "verdict": verdict, "fixable": ["favicon"],
                                "files": 1, "paths": ["index.php"], "commit": "c1",
                                "domain": "", "note": "", "checks_fp": "f1",
                                "applied_ts": ""} for b in branches]}})
    cu_queue.save(st)


def _world(client, *, changes=(("edit", "index.php"),), told=None):
    """Підміняє все, що виходить назовні. Повертає журнал і відновлювач."""
    seen = {"log": [], "clickup": [], "synced": []}
    saved = [(runner, "sync_branch", runner.sync_branch),
             (runner, "compute_fixes", runner.compute_fixes),
             (runner, "apply_to_snapshot", runner.apply_to_snapshot),
             (clickup_client, "complete_task", clickup_client.complete_task)]

    runner.sync_branch = lambda cl, br: seen["synced"].append(br)
    runner.compute_fixes = lambda br, ids: [
        {"type": k, "path": p, "new": "x"} for k, p in changes]
    runner.apply_to_snapshot = lambda br, ch: None

    def complete(task_id, comment="fixed", checklist=True, **kw):
        if told:
            raise RuntimeError(told)
        seen["clickup"].append((task_id, comment, checklist))
        return {"ok": True}
    clickup_client.complete_task = complete

    cu_queue._deps["client"] = client
    cu_queue._deps["log_commit"] = lambda *a, **k: seen["log"].append((a, k))
    cu_queue._deps["add_problems"] = lambda rows: None

    def restore():
        for mod, name, val in saved:
            setattr(mod, name, val)
    return seen, restore


# ------------------------------------------------------------------ коміт

def test_the_button_commits_every_chosen_branch_once():
    _seed()
    cl = _Client()
    seen, restore = _world(cl)
    try:
        rep = cu_queue.apply([{"task_id": "t1"}])
    finally:
        restore()
    assert [c[0] for c in cl.commits] == ["nwf-a", "nwf-b"], cl.commits
    assert rep["tasks"][0]["committed"] == 2, rep
    assert [a[0][0] for a in seen["log"]] == ["nwf-a", "nwf-b"], "журнал не заповнено"


def test_the_message_defaults_to_the_one_from_the_manual_button():
    _seed()
    cl = _Client()
    _, restore = _world(cl)
    try:
        rep = cu_queue.apply([{"task_id": "t1", "branches": ["nwf-a"]}])
    finally:
        restore()
    assert rep["message"] == cu_queue.DEFAULT_MESSAGE == "fix: автовиправлення перевірок"
    assert cl.commits[0][1] == cu_queue.DEFAULT_MESSAGE


def test_only_the_chosen_branches_are_committed():
    _seed()
    cl = _Client()
    _, restore = _world(cl)
    try:
        cu_queue.apply([{"task_id": "t1", "branches": ["nwf-b"]}])
    finally:
        restore()
    assert [c[0] for c in cl.commits] == ["nwf-b"], cl.commits


def test_a_branch_that_has_nothing_to_fix_is_not_committed():
    _seed(verdict=pipeline.CLEAN)
    cl = _Client()
    _, restore = _world(cl)
    try:
        rep = cu_queue.apply([{"task_id": "t1"}])
    finally:
        restore()
    assert cl.commits == [], "чиста вітка не має потрапляти в коміт"
    assert rep["tasks"][0]["committed"] == 0


def test_fixes_are_recomputed_and_an_empty_result_skips_the_commit():
    """Вітка поїхала між прогоном і кнопкою — коміту немає, є рядок причини."""
    _seed(branches=("nwf-a",))
    cl = _Client()
    _, restore = _world(cl, changes=())
    try:
        rep = cu_queue.apply([{"task_id": "t1"}])
    finally:
        restore()
    assert cl.commits == []
    assert "нічого не змінив" in rep["tasks"][0]["branches"][0]["error"], rep


def test_one_refusal_does_not_kill_the_batch():
    _seed()
    cl = _Client(fail={"nwf-a": "You are not allowed to push into this branch"})
    _, restore = _world(cl)
    try:
        rep = cu_queue.apply([{"task_id": "t1"}])
    finally:
        restore()
    rows = rep["tasks"][0]["branches"]
    assert "not allowed to push" in rows[0]["error"], rows[0]
    assert rows[1]["commit"] == "sha-nwf-b", rows[1]
    assert rep["tasks"][0]["committed"] == 1


def test_an_applied_branch_is_marked_in_the_state():
    """Без запису в ClickUp таска не закривається — і видно, що закомічено."""
    _seed(branches=("nwf-a",))
    cl = _Client()
    _, restore = _world(cl)
    try:
        cu_queue.apply([{"task_id": "t1"}], comment=False)
    finally:
        restore()
    b = cu_queue.load()["tasks"]["t1"]["branches"][0]
    assert b["verdict"] == cu_queue.APPLIED and b["commit"] == "sha-nwf-a", b
    assert b["applied_ts"], "мітка часу мусить лишитись — інакше не видно, коли"


# ---------------------------------------------------------------- ClickUp

def test_clickup_hears_once_per_task_and_only_about_success():
    _seed()
    cl = _Client()
    seen, restore = _world(cl)
    try:
        cu_queue.apply([{"task_id": "t1"}])
    finally:
        restore()
    assert seen["clickup"] == [("t1", "fixed", True)], seen["clickup"]


def test_nothing_committed_means_nothing_written_to_the_task():
    _seed(verdict=pipeline.NO_FIX)
    cl = _Client()
    seen, restore = _world(cl)
    try:
        cu_queue.apply([{"task_id": "t1"}])
    finally:
        restore()
    assert seen["clickup"] == [], "про невдачу фронтам не пишемо нічого"


def test_a_failed_comment_does_not_undo_the_commit():
    _seed(branches=("nwf-a",))
    cl = _Client()
    _, restore = _world(cl, told="429 rate limit")
    try:
        rep = cu_queue.apply([{"task_id": "t1"}])
    finally:
        restore()
    assert cl.commits, "коміт мусить лишитись"
    assert "429" in rep["tasks"][0]["clickup"], rep["tasks"][0]


def test_the_comment_can_be_switched_off():
    _seed(branches=("nwf-a",))
    cl = _Client()
    seen, restore = _world(cl)
    try:
        cu_queue.apply([{"task_id": "t1"}], comment=False)
    finally:
        restore()
    assert cl.commits and seen["clickup"] == []


def test_an_unknown_task_is_reported_not_thrown():
    _seed()
    cl = _Client()
    _, restore = _world(cl)
    try:
        rep = cu_queue.apply([{"task_id": "ghost"}])
    finally:
        restore()
    assert rep["tasks"][0]["error"], rep


# ------------------------------------------------------------- завершення
# Етап 1 (21.09.2026): «когда QA по всем вайтам пройдено — … пишется коммент,
# и эта таска со списка исчезает». Два варіанти (23.09.2026): людина кнопкою
# «Закомітити обране» — чекліст + fixed, як «✔ чекліст + fixed» у вкладці
# ClickUp; автокоміт — лише коментар.

def test_a_fully_applied_task_is_answered_and_leaves_the_tab():
    _seed()
    cl = _Client()
    seen, restore = _world(cl)
    try:
        rep = cu_queue.apply([{"task_id": "t1"}])
    finally:
        restore()
    assert seen["clickup"] == [("t1", "fixed", True)], seen["clickup"]
    assert rep["tasks"][0]["clickup"] == "ok", rep
    assert "t1" not in cu_queue.load()["tasks"], "відписана таска лишилась у вкладці"
    assert cu_queue.load()["counters"].get("answered") == 1


def test_a_partly_applied_task_stays_and_writes_nothing():
    """Коміт частини віток таску не закриває: QA ще не пройдено."""
    _seed()
    cl = _Client()
    seen, restore = _world(cl)
    try:
        cu_queue.apply([{"task_id": "t1", "branches": ["nwf-a"]}])
    finally:
        restore()
    assert [c[0] for c in cl.commits] == ["nwf-a"]
    assert seen["clickup"] == [], seen["clickup"]
    assert "t1" in cu_queue.load()["tasks"]


def test_a_refused_write_keeps_the_card_so_a_person_sees_it():
    _seed()
    cl = _Client()
    seen, restore = _world(cl, told="401 Team not authorized")
    try:
        rep = cu_queue.apply([{"task_id": "t1"}])
    finally:
        restore()
    assert "коментар не пройшов" in rep["tasks"][0]["clickup"], rep
    assert "t1" in cu_queue.load()["tasks"], "у таску не відписано — картка мусить лишитись"


# ------------------------------------------------------------- автокоміт

def _checks(groups):
    """Підміняє реєстр чеків активного проєкту: id -> група."""
    was = runner.checks_for_active_project
    runner.checks_for_active_project = lambda: [
        {"id": i, "group": g, "fixable": True} for i, g in groups.items()]

    def restore():
        runner.checks_for_active_project = was
    return restore


def test_autocommit_goes_through_the_very_same_door_as_the_button():
    """Коміт, підпис, коментар, чекліст і Журнал мусять бути буква в букву
    тими самими: інакше в історії вітки було б видно, чим саме її правили.
    З 23.09 до 29.09.2026 різниця була одна — автомат не ставив чекліст, і
    люди відписували ті самі таски вдруге; тепер немає й її."""
    _seed()
    cu_queue.set_switches(autocommit=True)
    cl = _Client()
    seen, restore = _world(cl)
    back = _checks({"favicon": "auto"})
    try:
        got = cu_queue.autocommit_task("t1")
    finally:
        back(), restore()
        cu_queue.set_switches(autocommit=False)
    assert got["committed"] == 2, got
    assert [c[0] for c in cl.commits] == ["nwf-a", "nwf-b"], cl.commits
    assert cl.commits[0][1] == cu_queue.DEFAULT_MESSAGE
    assert seen["clickup"] == [("t1", "fixed", True)], seen["clickup"]


def test_autocommit_takes_the_tests_group_too():
    """21.09.2026: «QA по всем тестам — и заливается в гит фиксы». Людина
    кнопкою «🔧 Автофікс» з дефолтними галками (Автотести ✓ Тести ✓) заливає
    фікси обох груп — автомат робить те саме."""
    _seed()
    cl = _Client()
    seen, restore = _world(cl)
    back = _checks({"favicon": "tests"})
    try:
        got = cu_queue.autocommit_task("t1")
    finally:
        back(), restore()
    assert got["committed"] == 2, (got, cl.commits)


def test_autocommit_never_takes_review():
    """`review` не ганяється і не комітиться автоматом: там два чеки дають
    error на 100% і 94% прогонів."""
    _seed()
    cl = _Client()
    seen, restore = _world(cl)
    back = _checks({"favicon": "review"})
    try:
        got = cu_queue.autocommit_task("t1")
    finally:
        back(), restore()
    assert got["committed"] == 0 and not cl.commits, (got, cl.commits)
    assert seen["clickup"] == [], "у ClickUp писати нема про що"


def test_autocommit_stops_at_its_ceiling_and_says_so():
    """Поганий фікс однаково поганий на всіх вітках, тому стеля є завжди, а
    решта лишається людині — і вона мусить це побачити."""
    _seed(branches=("a", "b", "c"))
    os.environ["CU_AUTOCOMMIT_MAX"] = "2"
    cl = _Client()
    seen, restore = _world(cl)
    back = _checks({"favicon": "auto"})
    rows = []
    cu_queue._deps["add_problems"] = lambda r: rows.extend(r)
    try:
        got = cu_queue.autocommit_task("t1")
    finally:
        back(), restore()
        os.environ.pop("CU_AUTOCOMMIT_MAX")
    assert got["committed"] == 2 and got["left"] == 1, got
    assert any("стелі" in r["reason"] for r in rows), rows


def test_a_failed_autocommit_lands_in_problems():
    """Автомат мовчить лише про успіх: тиша про відмову і є те, через що
    потім не знайти, коли зламалось."""
    _seed(branches=("nwf-a",))
    cl = _Client(fail={"nwf-a": "403 protected"})
    seen, restore = _world(cl)
    back = _checks({"favicon": "auto"})
    rows = []
    cu_queue._deps["add_problems"] = lambda r: rows.extend(r)
    try:
        got = cu_queue.autocommit_task("t1")
    finally:
        back(), restore()
    assert got["committed"] == 0, got
    assert rows and "403" in rows[0]["reason"], rows


def test_autocommit_is_off_by_default():
    assert cu_queue._default_state["autocommit"] is False


if __name__ == "__main__":
    run(dict(globals()))
