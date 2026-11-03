"""Черга ClickUp: прийом, гейт, вироки, пауза, межі.

Що тут важливо перевіряти, а не вірити на слово:

* **прийом і виконання — два різні перемикачі.** «Стоп» мусить зупиняти
  роботу, але НЕ прийом: інакше зупинка тихо втрачає таски, які прилетіли
  поки вона діяла;
* **зайва таска не з'являється ніде** — ні рядком, ні в «Проблемах». Замовник
  сказав про це окремо, і це легко зламати назад одним `else`;
* **скіп по коміту** — без нього балакуча таска ганяє ті самі вітки по колу;
* **черга не комітить.** Тест тримає це чесним: `log_commit` не підмінено, а
  залишено таким, що падає, — якщо в прогоні колись з'явиться коміт, це
  впаде тут, а не в проді.

Стан ізольовано на рівні МОДУЛЯ, до першого тесту: інакше перший же запис
поклав би `cu_queue.json` у робоче дерево.
"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="cu-queue-")
os.environ["QA_LAB_STATE_DIR"] = _TMP
os.environ["MOCK_MODE"] = "1"
# Акаунт лаби в ClickUp — як у проді; мережі в тестах немає, тож змінною.
os.environ["CLICKUP_BOT_NAME"] = "Tech Bot"

from _harness import run                                        # noqa: E402

import clickup_client                                           # noqa: E402
import ai_bridge                                                # noqa: E402
import ai_router                                                # noqa: E402
import cu_queue                                                 # noqa: E402
import cu_triage                                                # noqa: E402
import pipeline                                                 # noqa: E402
import projects                                                 # noqa: E402
import runner                                                   # noqa: E402

# Реєстр проєктів будує `app.init()`; сюди його не тягнемо — черга користується
# лише `projects.use()` і `client_for()`.
projects.init()

# Потоків у тестах не піднімаємо. Перевіряємо прийом і прогін, а не життя
# потоку; живий воркер вихоплював би завдання з черги і йшов у СПРАВЖНІЙ
# ClickUp, а тести не сміють торкатись ані мережі, ані чужого стану.
cu_queue.start = lambda: None


def _reset(**switches):
    """Чистий стан і порожня черга перед кожним тестом.

    Спорожнюємо ПУБЛІЧНИМ API (`get_nowait` + `task_done`), а не
    `_q.queue.clear()`: друге лишає лічильник незавершених задач ненульовим,
    і тест, який на нього дивиться, бачить сміття від попереднього тесту.
    """
    while True:
        try:
            cu_queue._q.get_nowait()
        except Exception:
            break
        cu_queue._q.task_done()
    st = dict(cu_queue._default_state)
    st.update(tasks={}, counters={"accepted": 0, "skipped": 0, "events": 0},
              intake=switches.get("intake", True), run=switches.get("run", True),
              autocommit=switches.get("autocommit", False))
    cu_queue.save(st)
    (cu_queue._go.set if st["run"] else cu_queue._go.clear)()
    cu_queue._problems = []
    cu_queue._deps["add_problems"] = lambda rows: cu_queue._problems.extend(rows)
    # Реєстр доменів — теж стан: з 25.09 звіт про зміну доменів читає з нього
    # старий домен, і привʼязка з попереднього тесту стала б «зміною» тут.
    import domains
    domains._save({"active": {}, "history": []}, pid="white-pages")


def _task(**kw):
    # Статус прохідний: з 07.09 `qa` і `domains hold` гейт не проходять
    # (рішення замовника, вимір — у tests/test_cu_qualify.py)
    base = {"id": "t1", "name": "[p-52] whites", "url": "u",
            "status": "in progress", "status_match": True,
            "status_type": "custom", "branches": ["nwf-a", "nwf-b"],
            "domains": ["a.top", "b.top"], "wtype": "1/2 круг",
            "checklist_loaded": True, "checklist_done": False, "assignees": []}
    base.update(kw)
    return base


def _stub(**kw):
    """Підміняє функції модулів і повертає відновлювач."""
    saved = [(mod, name, getattr(mod, name)) for mod, name, _ in kw["items"]]
    for mod, name, val in kw["items"]:
        setattr(mod, name, val)

    def restore():
        for mod, name, val in saved:
            setattr(mod, name, val)
    return restore


def _fake_world(task, *, verdict=pipeline.WOULD_FIX, commit="c1", protected=False):
    """ClickUp, GitLab і прогін — усі підмінені; справжня мережа не смикається."""
    seen = {"ran": 0, "ids": []}

    def run_branch(branch, ids, *, client, groups):
        seen["ran"] += 1
        seen["ids"] = list(ids)
        return {"branch": branch, "verdict": verdict, "fired": {"favicon": 1},
                "fixable": ["favicon"], "files": 1, "files_scanned": 5,
                "changes": [{"type": "edit", "path": "index.php", "new": "x"}],
                "stale": ""}

    restore = _stub(items=[
        (clickup_client, "fetch_by_ids", lambda items, with_comments=True, token="": [task]),
        (projects, "locate_branch", lambda n: {
            "pid": "white-pages", "name": n,
            "info": {"commit": commit, "protected": protected, "can_push": not protected}}),
        (projects, "client_for", lambda pid: object()),
        (pipeline, "run_branch", run_branch),
        (runner, "checks_for_active_project", lambda: [
            {"id": "favicon", "group": "auto", "fixable": True},
            {"id": "external_links", "group": "review", "fixable": True}]),
    ])
    return seen, restore


# ---------------------------------------------------------------- перемикачі

def test_intake_is_off_by_default_and_refuses_tasks():
    _reset(intake=False, run=False)
    got = cu_queue.submit("t1")
    assert got["status"] == "off", got


def test_stopping_the_worker_does_not_stop_intake():
    """Найважливіша вимога замовника: «стоп» гасить виконавця, а вебхук
    продовжує наповнювати чергу."""
    _reset(intake=True, run=False)
    got = cu_queue.submit("t1")
    assert got["status"] == "queued", got
    assert cu_queue._q.qsize() == 1
    assert not cu_queue._go.is_set(), "виконавець мусить стояти"


def test_a_second_event_for_a_queued_task_adds_nothing():
    _reset()
    assert cu_queue.submit("t1")["status"] == "queued"
    assert cu_queue.submit("t1")["status"] == "duplicate"
    assert cu_queue._q.qsize() == 1


def test_the_queue_has_a_ceiling():
    _reset()
    os.environ["CU_QUEUE_MAX"] = "2"
    try:
        cu_queue.submit("a"), cu_queue.submit("b")
        try:
            cu_queue.submit("c")
        except cu_queue.QueueFull as e:
            assert e.depth == 2, e.depth
        else:
            assert False, "черга без межі приймає бурю цілком"
    finally:
        os.environ.pop("CU_QUEUE_MAX")


# ---------------------------------------------------------------- гейт таски

def test_a_task_that_fails_the_gate_is_not_shown_anywhere():
    _reset()
    _, restore = _fake_world(_task(wtype=None))
    try:
        cu_queue.process("t1")
    finally:
        restore()
    st = cu_queue.state()
    assert st["tasks"] == [], "зайва таска не має з'являтись у вкладці"
    assert st["counters"]["skipped"] == 1, st["counters"]
    assert cu_queue._problems == [], "і в «Проблемах» їй теж не місце"


def test_a_task_we_cannot_open_goes_to_problems():
    """Це не «таски немає», а «наш токен її не бачить» — рівно поломка 04.09."""
    _reset()
    _, restore = _fake_world({"id": "t1", "no_access": True, "name": "TECH-27120"})
    try:
        cu_queue.process("t1")
    finally:
        restore()
    assert cu_queue._problems and cu_queue._problems[0]["source"] == "clickup", \
        cu_queue._problems
    assert cu_queue.state()["tasks"][0]["state"] == "no_access"


# ---------------------------------------------------------------- вироки

def test_a_fixable_branch_is_recorded_without_committing():
    _reset()
    seen, restore = _fake_world(_task())
    try:
        rec = cu_queue.process("t1")
    finally:
        restore()
    assert seen["ran"] == 2, "обидві вітки таски мали пройти"
    assert [b["verdict"] for b in rec["branches"]] == ["would_fix"] * 2, rec
    assert rec["branches"][0]["paths"] == ["index.php"]
    assert rec["branches"][0]["domain"] == "a.top", "домен іде за індексом вітки"


def test_a_protected_branch_says_so_instead_of_a_403():
    _reset()
    seen, restore = _fake_world(_task(branches=["main"]), protected=True)
    try:
        rec = cu_queue.process("t1")
    finally:
        restore()
    assert rec["branches"][0]["verdict"] == cu_queue.PROTECTED, rec
    assert seen["ran"] == 0, "захищену вітку не треба навіть ганяти"


def test_the_same_commit_and_the_same_checks_are_skipped():
    _reset()
    seen, restore = _fake_world(_task(branches=["nwf-a"], domains=["a.top"]))
    try:
        cu_queue.process("t1")
        cu_queue._q.queue.clear()
        rec = cu_queue.process("t1")
    finally:
        restore()
    assert seen["ran"] == 1, "друга подія на тому самому коміті — зайвий прогін"
    # «Є що полагодити» лишається собою: фікс ще чекає на коміт. Доти тут
    # ставало «без змін», і вітка тихо випадала з кнопки коміту (21.09.2026).
    assert rec["branches"][0]["verdict"] == pipeline.WOULD_FIX, rec


def test_a_clean_branch_on_the_same_commit_is_unchanged():
    _reset()
    seen, restore = _fake_world(_task(branches=["nwf-a"], domains=["a.top"]),
                                verdict=pipeline.CLEAN)
    try:
        cu_queue.process("t1")
        cu_queue._q.queue.clear()
        rec = cu_queue.process("t1")
    finally:
        restore()
    assert seen["ran"] == 1
    assert rec["branches"][0]["verdict"] == cu_queue.UNCHANGED, rec


def test_a_new_commit_runs_the_branch_again():
    _reset()
    seen, restore = _fake_world(_task(branches=["nwf-a"], domains=["a.top"]))
    try:
        cu_queue.process("t1")
    finally:
        restore()
    seen2, restore2 = _fake_world(_task(branches=["nwf-a"], domains=["a.top"]),
                                  commit="c2")
    try:
        cu_queue.process("t1")
    finally:
        restore2()
    assert seen2["ran"] == 1, "новий коміт мусить переганяти вітку"


def test_a_branch_that_is_nowhere_becomes_a_problem():
    _reset()
    _, restore = _fake_world(_task(branches=["ghost"], domains=["ghost.blog"]))
    projects.locate_branch = lambda n: None
    try:
        rec = cu_queue.process("t1")
    finally:
        restore()
    assert rec["branches"][0]["verdict"] == cu_queue.GONE, rec
    assert cu_queue._problems[0]["branch"] == "ghost", cu_queue._problems


def test_a_missing_branch_is_not_re_probed_every_event():
    """Знайдено живим прогоном 04.09: у частини тасок у `Safe Page` лежать
    домени, а не вітки. Без затримки кожна подія коштувала б п'ять марних
    GET-ів у GitLab і п'ять однакових рядків у «Проблемах»."""
    _reset()
    probes = []
    _, restore = _fake_world(_task(branches=["sad-fsi.ch"], domains=["sad-fsi.ch"]))
    projects.locate_branch = lambda n: probes.append(n)
    try:
        cu_queue.process("t1")
        cu_queue.process("t1")
    finally:
        restore()
    assert probes == ["sad-fsi.ch"], f"перепитали GitLab удруге: {probes}"


def test_a_missing_branch_is_re_probed_after_the_cooldown():
    """Зовсім не перепитувати не можна: вітку могли ще не створити."""
    _reset()
    probes = []
    _, restore = _fake_world(_task(branches=["late-branch"], domains=["late.blog"]))
    projects.locate_branch = lambda n: probes.append(n)
    try:
        cu_queue.process("t1")
        # позначку часу відсуваємо у минуле — так само, як це зробить година
        def age(st):
            st["tasks"]["t1"]["branches"][0]["ts"] = "2020-01-01 00:00:00"
            return None
        cu_queue._update(age)
        cu_queue.process("t1")
    finally:
        restore()
    assert len(probes) == 2, f"після затримки вітку треба пошукати ще раз: {probes}"


def test_no_fix_stays_on_the_card_and_out_of_problems():
    """Етап 1 (21.09.2026): «некоторые фиксы показывают ошибки там где их нет,
    но на них нет автофикса. На первом этапе — это игнорируем»."""
    _reset()
    _, restore = _fake_world(_task(branches=["nwf-a"], domains=["a.blog"]),
                             verdict=pipeline.NO_FIX)
    try:
        rec = cu_queue.process("t1")
    finally:
        restore()
    assert cu_queue._problems == [], cu_queue._problems
    assert rec["branches"][0]["verdict"] == pipeline.NO_FIX, rec


# ---------------------------------------------------------------- пауза

def test_a_task_that_started_is_finished_even_if_the_worker_is_stopped():
    """Замовлена поведінка: «вимкнув» — це «доробить почате і стане», а не
    «кине посеред роботи». Інакше таска лишалась би наполовину пройденою, а
    вітки без вироку нікуди не повертаються самі."""
    _reset(intake=True, run=False)          # виконавця вимкнено
    seen, restore = _fake_world(_task())
    try:
        rec = cu_queue.process("t1")        # але таска вже почалась
    finally:
        restore()
    assert seen["ran"] == 2, "почату таску треба довести до кінця"
    assert all(b["verdict"] for b in rec["branches"]), rec


def test_the_worker_stops_before_the_next_task_and_resumes_where_it_left_off():
    """Пауза гасить РОБОТУ над віткою, але не кваліфікацію.

    З 07.09 це різні речі: «стоп» не має права лишати вкладку зі сміттям —
    таски однаково дотягуються, відсіюються і чекають з іменем та лінкою.
    Тому ▶ вмикається саме перемикачем (як у UI): він і повертає в чергу те,
    що накопичилось у стані.
    """
    _reset(intake=True, run=False)
    done, was = [], cu_queue.process
    was_q = cu_queue.qualify
    cu_queue.process = lambda tid, task=None: done.append(tid)
    cu_queue.qualify = lambda tid: {"id": tid, "name": f"таска {tid}"}
    real_start, cu_queue.start = cu_queue.start, lambda: None
    t = threading.Thread(target=cu_queue._loop, daemon=True)
    try:
        t.start()
        cu_queue.submit("a"), cu_queue.submit("b")
        time.sleep(1.4)                     # довше за такт черги (1 с)
        assert done == [], f"на паузі виконавець узяв роботу: {done}"
        cu_queue.set_switches(run=True)     # ▶ — те саме, що кнопка в UI
        deadline = time.time() + 5
        while len(done) < 2 and time.time() < deadline:
            time.sleep(0.1)
        assert sorted(done) == ["a", "b"], f"після ▶ черга мусить піти далі: {done}"
    finally:
        cu_queue._go.clear()
        cu_queue.process, cu_queue.qualify = was, was_q
        cu_queue.start = real_start


def test_a_restart_does_not_lose_what_was_queued():
    """Черга живе в пам'яті, а стан — на диску. Без цього деплой означав би
    тихо загублену роботу: у файлі `queued`, а виконувати нікому."""
    _reset(intake=True, run=False)
    cu_queue.submit("a")
    cu_queue._q.queue.clear()               # ніби процес перезапустили
    assert cu_queue.restore_queue() == 1
    assert list(cu_queue._q.queue) == ["a"]
    assert cu_queue.restore_queue() == 0, "друге відновлення не має дублювати"


def test_submitting_queues_a_task_exactly_once():
    """Відновлення черги живе на старті процесу, а не у `start()`: інакше
    кожен `submit()` повертав би у чергу все попереднє — заміряно живцем,
    три таски дали глибину шість."""
    _reset(intake=True, run=False)
    for tid in ("a", "b", "c"):
        cu_queue.submit(tid)
    assert list(cu_queue._q.queue) == ["a", "b", "c"], list(cu_queue._q.queue)


def test_a_task_waiting_for_qualification_is_counted_not_shown():
    """Поки таску не кваліфікували, це лише id з події чи опиту: карткою її
    не показуємо, лише лічильником `pending`. До 23.09.2026 вона висіла
    карткою «у черзі» — і саме так у вкладку поверталась уже відписана таска
    (звірка з ТЗ). Назву з опиту запис однаково тримає: картка з'явиться з
    нею, а не голим id, щойно таска пройде відбір."""
    _reset(intake=True, run=False)
    cu_queue.submit("a", source="poll", name="[885] - G1 - Globo", url="u")
    st = cu_queue.state()
    assert st["tasks"] == [] and st["pending"] == 1, st
    assert cu_queue.load()["tasks"]["a"]["name"] == "[885] - G1 - Globo"


# ------------------------------------------------------- тріаж перед роботою

def _triage(verdict, checks=(), reason="бо так"):
    """Підміняє вирок тріажу — сам він перевіряється в test_cu_triage.py."""
    was = cu_triage.classify
    cu_triage.classify = lambda task, **kw: {
        "verdict": verdict, "checks": list(checks), "reason": reason,
        "router": "stub", "confidence": 1.0, "text_hash": "h1",
        "skills_fp": "fp1"}
    return lambda: setattr(cu_triage, "classify", was)


def test_a_task_the_bridge_calls_not_ours_never_reaches_the_checks():
    """Замовлене правило: у чергу йде лише те, що визначено ТОЧНО."""
    _reset()
    seen, restore = _fake_world(_task())
    undo = _triage(cu_triage.NOT_OURS, reason="домен у чорному списку")
    try:
        rec = cu_queue.process("t1")
    finally:
        undo(); restore()
    assert seen["ran"] == 0, "не наше — а чеки все одно ганяли"
    assert rec["state"] == cu_triage.NOT_OURS, rec
    assert cu_queue._problems and "чорному списку" in cu_queue._problems[0]["reason"]


def test_an_undetermined_task_is_visible_but_not_processed():
    _reset()
    seen, restore = _fake_world(_task())
    undo = _triage(cu_triage.UNDETERMINED, reason="не вдалось визначити")
    try:
        rec = cu_queue.process("t1")
    finally:
        undo(); restore()
    assert seen["ran"] == 0 and rec["state"] == cu_triage.UNDETERMINED, rec
    assert cu_queue.state()["tasks"][0]["state"] == cu_triage.UNDETERMINED
    assert cu_queue._problems, "«не знаю» мусить бути видно людині"


def test_checks_named_by_the_bridge_are_added_to_the_full_set():
    _reset()
    seen, restore = _fake_world(_task(branches=["nwf-a"], domains=["a.blog"]))
    undo = _triage(cu_triage.OURS, checks=["logo_domain"])
    try:
        cu_queue.process("t1")
    finally:
        undo(); restore()
    assert seen["ran"] == 1
    assert seen["ids"] == ["favicon", "logo_domain"], seen["ids"]


def test_the_same_text_and_the_same_skills_skip_the_triage():
    """Балакуча таска (ClickUp шле `taskUpdated` на кожну дрібницю) інакше
    платила б моделлю на кожну подію."""
    _reset()
    calls = []
    was = cu_triage.classify
    cu_triage.classify = lambda task, **kw: calls.append(1) or {
        "verdict": cu_triage.OURS, "checks": [], "reason": "", "router": "stub",
        "confidence": 1.0, "text_hash": cu_triage.text_hash(""),
        "skills_fp": cu_triage.skills_fingerprint()}
    _, restore = _fake_world(_task(branches=["nwf-a"], domains=["a.blog"]))
    try:
        cu_queue.process("t1")
        cu_queue.process("t1")
    finally:
        cu_triage.classify = was; restore()
    assert len(calls) == 1, f"тріаж перерахували дарма: {len(calls)}"


def test_a_new_skill_makes_the_triage_run_again():
    _reset()
    calls = []
    was_cl, was_fp = cu_triage.classify, cu_triage.skills_fingerprint
    cu_triage.skills_fingerprint = lambda: "fp-old"
    cu_triage.classify = lambda task, **kw: calls.append(1) or {
        "verdict": cu_triage.OURS, "checks": [], "reason": "", "router": "stub",
        "confidence": 1.0, "text_hash": cu_triage.text_hash(""),
        "skills_fp": cu_triage.skills_fingerprint()}
    _, restore = _fake_world(_task(branches=["nwf-a"], domains=["a.blog"]))
    try:
        cu_queue.process("t1")
        cu_triage.skills_fingerprint = lambda: "fp-new"     # хтось дописав скіл
        cu_queue.process("t1")
    finally:
        cu_triage.classify, cu_triage.skills_fingerprint = was_cl, was_fp
        restore()
    assert len(calls) == 2, "новий скіл мусить переганяти вирок"


# --------------------------------------------------- «Актуалізувати» помилки

def _problems(rows):
    """Підміняє журнал проблем: саме він, а не стан черги, — джерело для кнопки."""
    cu_queue._deps["load_problems"] = lambda: list(rows)
    dropped = []
    cu_queue._deps["drop_problems"] = lambda pred: (
        dropped.append(pred) or len([r for r in rows if pred(r)]))
    return dropped


def test_reclassify_moves_a_task_that_became_determined_and_clears_the_error():
    """Уся суть кнопки: новий скіл перетворює «не знаю» на роботу, і таска
    зникає з «Проблем» рівно тоді, коли зʼявляється в черзі."""
    _reset()
    dropped = _problems([{"source": "clickup", "task": "t1",
                          "branch": "[p-52] whites", "reason": "не знаю"}])
    _, restore = _fake_world(_task())
    undo = _triage(cu_triage.UNDETERMINED)
    try:
        cu_queue.process("t1")
        undo(); undo = _triage(cu_triage.OURS)      # скіл дописали
        cu_queue._q.queue.clear()
        rep = cu_queue.reclassify()
    finally:
        undo(); restore()
    assert rep["looked"] == 1 and rep["moved"] == 1, rep
    assert list(cu_queue._q.queue) == ["t1"], "таска мусить поїхати в чергу"
    assert dropped, "рядок помилки мусить зникнути"
    assert cu_queue.load()["tasks"]["t1"]["state"] == "queued"


def test_reclassify_looks_at_the_journal_not_at_the_transient_state():
    """Знайдено живим прогоном 04.09: фоновий опит устигав перевести таску
    назад у `queued`, і кнопка відповідала «дивитись нема на що», хоча рядок
    помилки лежав перед очима людини."""
    _reset()
    _problems([{"source": "clickup", "task": "t1", "branch": "x", "reason": "не знаю"}])
    _, restore = _fake_world(_task())
    undo = _triage(cu_triage.UNDETERMINED)
    try:
        cu_queue.process("t1")
        # ніби опит щойно поставив її назад у чергу
        cu_queue._update(lambda s: s["tasks"]["t1"].update(state="queued"))
        undo(); undo = _triage(cu_triage.OURS)
        rep = cu_queue.reclassify()
    finally:
        undo(); restore()
    assert rep["looked"] == 1 and rep["moved"] == 1, rep


def test_reclassify_keeps_what_is_still_undetermined_and_refreshes_the_reason():
    _reset()
    _problems([{"source": "clickup", "task": "t1", "branch": "x", "reason": "перша"}])
    _, restore = _fake_world(_task())
    undo = _triage(cu_triage.UNDETERMINED, reason="перша причина")
    try:
        cu_queue.process("t1")
        undo(); undo = _triage(cu_triage.NOT_OURS, reason="тепер зрозуміло: не наше")
        rep = cu_queue.reclassify()
    finally:
        undo(); restore()
    assert rep["moved"] == 0 and rep["looked"] == 1, rep
    row = cu_queue.load()["tasks"]["t1"]
    assert row["state"] == cu_triage.NOT_OURS and "не наше" in row["reason"], row


def test_reclassify_ignores_problems_that_are_not_from_the_triage():
    """Зникла вітка чи невдалий фікс — інший рід проблеми; для нього поруч
    уже є «Спробувати sync ще раз»."""
    _reset()
    _problems([{"source": "clickup", "task": "t1", "branch": "nwf-a",
                "reason": "вітки немає в жодному проєкті"},
               {"source": "sync", "task": "t9", "branch": "z", "reason": "404"}])
    _, restore = _fake_world(_task())
    undo = _triage(cu_triage.OURS)
    try:
        cu_queue.process("t1")          # тріаж сказав «наше», проблема — про вітку
        rep = cu_queue.reclassify()
    finally:
        undo(); restore()
    assert rep == {"looked": 0, "moved": 0, "tasks": []}, rep


def test_reclassify_with_nothing_stuck_is_a_no_op():
    _reset()
    _problems([])
    assert cu_queue.reclassify() == {"looked": 0, "moved": 0, "tasks": []}


# ---------------------------------------------------------------- дрібниці

def test_only_allowed_groups_are_run():
    _reset()
    _, restore = _fake_world(_task())
    try:
        assert cu_queue.default_check_ids() == ["favicon"], \
            "review не має потрапляти у прогін"
    finally:
        restore()


def test_the_state_keeps_the_switches_between_restarts():
    _reset(intake=True, run=False)
    assert cu_queue.load()["intake"] is True
    assert cu_queue.load()["run"] is False


def test_qualification_happens_on_intake_even_with_the_worker_stopped():
    """Скарга 07.09: «блеків тягнути сюди не треба». Подія вебхука несе лише
    id, тож відсіяти чуже можна тільки дотягнувши таску — і робити це треба
    на ПРИЙОМІ, інакше з вимкненим виконавцем вкладка повна сміття."""
    _reset(intake=True, run=False)
    alien = _task(id="blk", name="адаптировать блэк", wtype=None, branches=[])
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [alien])])
    try:
        assert cu_queue.qualify("blk") is None, "чужа таска мусить відсіятись"
        st = cu_queue.load()
        assert "blk" not in st["tasks"], "картки не має лишитись зовсім"
        assert st["counters"]["skipped"] >= 1
    finally:
        restore()


def test_a_stopped_queue_does_not_write_into_the_problems_journal():
    """Скарга 09.09: «чистив проблеми — не допомагає». З вимкненим виконавцем
    кваліфікація все одно йде (рішення 07.09), і кожен опит клав ті самі рядки
    про недоступні таски назад у «Проблеми» — журнал людини не спорожнити.
    Картка у вкладці «Черга» при цьому лишається: причина нікуди не дівається.
    """
    _reset(intake=True, run=False)
    blind = {"id": "t9", "no_access": True, "name": "TECH-27120"}
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [blind])])
    try:
        assert cu_queue.qualify("t9") is None
    finally:
        restore()
    assert cu_queue._problems == [], cu_queue._problems
    assert cu_queue.load()["tasks"]["t9"]["state"] == "no_access"


def test_a_running_queue_still_reports_a_task_it_cannot_open():
    """Зворотний бік того самого правила: коли черга працює, недоступна таска
    мусить лишити слід — саме так знайшли брак доступу до списку
    901108810149 (04.09)."""
    _reset(intake=True, run=True)
    blind = {"id": "t9", "no_access": True, "name": "TECH-27120"}
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [blind])])
    try:
        assert cu_queue.qualify("t9") is None
    finally:
        restore()
    assert cu_queue._problems and cu_queue._problems[0]["task"] == "t9", \
        cu_queue._problems


def test_a_qualified_card_gets_its_name_before_any_work():
    """Друга половина тієї ж скарги: у черзі лежали голі id, на які людина
    не могла навіть глянути."""
    _reset(intake=True, run=False)
    mine = _task(id="ok1", name="[865] Uol - Jair", url="https://app.clickup.com/t/ok1")
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [mine])])
    try:
        assert cu_queue.qualify("ok1") is not None
        card = cu_queue.load()["tasks"]["ok1"]
        assert card["name"] == "[865] Uol - Jair" and card["url"].endswith("/ok1")
        assert card["qualified"] is True
    finally:
        restore()


def test_a_qualified_card_shows_branches_with_domains_before_any_work():
    """Задача 21.09.2026: «ветки и домены» на картці — як у вкладці ClickUp,
    а не лише після прогону. Порядок доменів = порядку віток."""
    _reset(intake=True, run=False)
    mine = _task(id="ok2")
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [mine])])
    try:
        assert cu_queue.qualify("ok2") is not None
        brs = cu_queue.load()["tasks"]["ok2"]["branches"]
        assert [(b["branch"], b["domain"]) for b in brs] == [
            ("nwf-a", "a.top"), ("nwf-b", "b.top")], brs
        assert all(b["verdict"] == "" for b in brs), "вирок до прогону"
    finally:
        restore()


def test_a_qualified_card_carries_what_the_clickup_card_shows():
    """Скрін задачі 21.09.2026 обводить на картці ClickUp ще й стан чекліста
    і коментар зі згадкою виконавця — картка «Авто-QA» мусить мати те саме."""
    _reset(intake=True, run=False)
    mine = _task(id="ok3", assignees=["Hugo Support", "Nora Frontend"],
                 checklist_found=True, checklist_done=False,
                 comments=[{"user": "Ella Berg", "text": "project: black-pages", "mentions": []},
                           {"user": "Hugo Support", "mentions": ["Nora Frontend"],
                            "text": "@Nora Frontend Можешь пофиксить, пожалуйста: почта"}])
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [mine])])
    try:
        cu_queue.qualify("ok3")
    finally:
        restore()
    card = cu_queue.load()["tasks"]["ok3"]
    assert card["checklist_found"] is True and card["checklist_done"] is False, card
    assert card["mention"]["user"] == "Hugo Support", card["mention"]
    assert "пофиксить" in card["mention"]["text"]


def test_the_run_replaces_the_planned_rows_with_verdicts():
    """Заплановані рядки — не вирок: прогін переписує їх своїми."""
    _reset(intake=True, run=False)
    task = _task()
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [task])])
    try:
        cu_queue.qualify("t1")
    finally:
        restore()
    seen, restore = _fake_world(task, verdict=pipeline.CLEAN)
    try:
        rec = cu_queue.process("t1")
    finally:
        restore()
    assert [b["verdict"] for b in rec["branches"]] == [pipeline.CLEAN] * 2, rec
    assert seen["ran"] == 2, "заплановані рядки сховали вітки від прогону"


def _told():
    """Підміняє запис у ClickUp: список того, що лаба туди написала —
    (таска, коментар, чи ставився чекліст)."""
    was, calls = clickup_client.complete_task, []
    clickup_client.complete_task = lambda tid, comment="fixed", checklist=True, **kw: \
        calls.append((tid, comment, checklist)) or {"ok": True}
    return calls, lambda: setattr(clickup_client, "complete_task", was)


def test_with_autocommit_a_clean_task_is_answered_and_leaves_the_tab():
    """QA пройдено й без жодного коміту: чисто — теж «пройдено». Автоматика
    відповідає рівно як кнопка «✔ чекліст + fixed»: чекліст + коментар
    `fixed` (29.09.2026; з 23.09 галки не було, і людям лишалось відписувати
    ті самі таски вдруге)."""
    _reset(autocommit=True)
    calls, undo = _told()
    seen, restore = _fake_world(_task(), verdict=pipeline.CLEAN)
    try:
        rec = cu_queue.process("t1")
    finally:
        restore(), undo()
    assert calls == [("t1", "fixed", True)], calls
    assert rec["state"] == "answered" and "t1" not in cu_queue.load()["tasks"], rec


def test_with_autocommit_a_committed_task_is_answered_with_the_checklist():
    """Кейс 29.09 (TECH-28500, «не ставит галку»): автокоміт закомітив фікси,
    QA пройдено — у таску йде той самий «fixed» з чеклістом, що й від кнопки.
    Доти `apply()` для автокоміту чекліст вимикав, і таска лишалась у вкладці
    ClickUp у людей: з 28.09 17:15 колега відписав удруге 27 з 29 таких тасок."""
    _reset(autocommit=True)
    seen, restore = _fake_world(_task(), verdict=pipeline.WOULD_FIX)
    written, unwrite = _written()
    try:
        rec = cu_queue.process("t1")
    finally:
        restore(), unwrite()
    assert [c["machine"] for c in written["commits"]] == [True, True], written
    assert [(n["comment"], n["checklist"]) for n in written["clickup"]] == [("fixed", True)], \
        written["clickup"]
    assert rec["state"] == "answered" and "t1" not in cu_queue.load()["tasks"], rec


def test_without_autocommit_nothing_is_written_even_when_clean():
    """Писати в ClickUp без людини — лише з увімкненим автокомітом."""
    _reset()
    calls, undo = _told()
    seen, restore = _fake_world(_task(), verdict=pipeline.CLEAN)
    try:
        cu_queue.process("t1")
    finally:
        restore(), undo()
    assert calls == [] and "t1" in cu_queue.load()["tasks"]


def test_a_protected_branch_keeps_the_task_open():
    _reset(autocommit=True)
    calls, undo = _told()
    seen, restore = _fake_world(_task(), verdict=pipeline.CLEAN, protected=True)
    try:
        cu_queue.process("t1")
    finally:
        restore(), undo()
    assert calls == [], "таску з захищеною віткою закрито як пройдену"


def _answered_then_asked(checklist_done=True, asked=True):
    comments = [{"user": "Tech Bot", "mentions": [],
                 "text": "fixed — committed via qa_lab by Liam"}]
    if asked:
        comments.insert(0, {"user": "Hugo Support", "mentions": [],
                            "text": "не фикс, почта всё ещё на чужом домене"})
    return _task(checklist_done=checklist_done, comments=comments)


def test_a_task_with_a_ticked_checklist_comes_back_when_support_writes_again():
    """Чекліст ставлять люди в ClickUp, і гейт вкладки за ним таску відсікає —
    без винятку вона не повернулась би ніколи, навіть з новим проханням.
    Повертається як ручна."""
    _reset(intake=True, run=False)
    task = _answered_then_asked()
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [task])])
    try:
        assert cu_queue.qualify("t1") is not None, "таска з новим проханням не повернулась"
    finally:
        restore()
    seen, restore = _fake_world(task)
    try:
        rec = cu_queue.process("t1")
    finally:
        restore()
    assert rec["state"] == cu_triage.MANUAL and seen["ran"] == 0, rec


def test_a_ticked_task_without_a_new_request_stays_away():
    _reset(intake=True, run=False)
    task = _answered_then_asked(asked=False)
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [task])])
    try:
        assert cu_queue.qualify("t1") is None
    finally:
        restore()


def test_the_webhook_does_not_take_a_task_that_already_has_a_fixed():
    """Рішення юзера 24.09: «вебхук взагалі не має грузити задачі з вже
    наявним fixed». Доти будь-яке нове слово після «fixed» повертало таску в
    чергу — а на корпусі 03.09 це 87 разів «апрув, дякую» від медіабаєрів і 69
    конфігів деплою. Автоматика ганяла б їх наново і відписувала `fixed` удруге."""
    _reset(intake=True, run=False)
    fixed = {"user": "Tech Bot", "mentions": [],
             "text": "fixed — committed via qa_lab by Liam"}
    for said, who in (("апрув, дякую", "Kite MB"),
                      ("project: black-pages defaults: CREATE_BINOM: 'Yes'", "Ella Berg"),
                      ("fixed", "Nora Frontend")):
        task = _task(updated="1790000000000",
                     comments=[{"user": who, "mentions": [], "text": said}, fixed])
        restore = _stub(items=[
            (clickup_client, "fetch_by_ids",
             lambda items, with_comments=True, token="", _t=task: [_t])])
        try:
            assert cu_queue.qualify("t1") is None, said
        finally:
            restore()
        st = cu_queue.load()
        assert "t1" not in st["tasks"], said                  # у вкладці її немає
        assert cu_queue.rejected_before(task), said           # і опит не платитиме за неї знову
        assert cu_triage.classify(task, use_model=False)["verdict"] == cu_triage.SKIP, said


def test_a_complaint_after_the_fixed_comes_back_only_to_a_person():
    """Виняток з ТЗ колеги-QA 21.09: саппорт пише знову — таска повертається.
    Але лише як ручний розбір, НІКОЛИ в автоматичний QA з автокомітом (той
    поставив би ще один «fixed») — навіть з увімкненим етапом 2."""
    _reset(intake=True, run=False)
    fixed = {"user": "Tech Bot", "mentions": [],
             "text": "fixed — committed via qa_lab by Liam"}
    task = _task(comments=[{"user": "Hugo Support", "mentions": [],
                            "text": "всё равно не работает форма ( контейнеры удалял"}, fixed])
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [task])])
    try:
        assert cu_queue.qualify("t1") is not None
    finally:
        restore()
    saved = os.environ.get("CU_ROUTE_COMMENTS")
    try:
        for stage in ("", "1"):
            os.environ["CU_ROUTE_COMMENTS"] = stage
            got = cu_triage.classify(task, use_model=False)
            assert got["verdict"] == cu_triage.MANUAL, (stage, got)
    finally:
        if saved is None:
            os.environ.pop("CU_ROUTE_COMMENTS", None)
        else:
            os.environ["CU_ROUTE_COMMENTS"] = saved


def test_a_task_answered_by_the_automation_stays_away_until_someone_writes_again():
    """Чекліста whites у тасці може й не бути, тож відписану таску поза
    вкладкою тримає наш підпис у коментарі, а повертає — нове слово в тасці."""
    closed = {"user": "Tech Bot", "mentions": [],
              "text": "fixed — committed via qa_lab by Liam"}
    assert cu_triage.already_answered(_task(comments=[closed]))
    asked = {"user": "Hugo Support", "mentions": [], "text": "не фикс, почта всё ещё чужая"}
    back = _task(comments=[asked, closed])
    assert not cu_triage.already_answered(back)
    assert cu_triage.classify(back, use_model=False)["verdict"] == cu_triage.MANUAL


# ------------------------------------------------ одна кнопка (23.09.2026)

def test_one_switch_turns_everything_on_and_off():
    """«Хай буде кнопка вкл/викл. Все працює автоматично тільки коли вкл,
    інакше ручний режим» — прийом, виконавець і автокоміт ідуть разом."""
    _reset(intake=False, run=False)
    got = cu_queue.set_auto(True)
    st = cu_queue.load()
    assert got["on"] and st["intake"] and st["run"] and st["autocommit"], (got, st)
    assert cu_queue.state()["on"] is True
    cu_queue.set_auto(False)
    st = cu_queue.load()
    assert not (st["intake"] or st["run"] or st["autocommit"]), st
    assert cu_queue.state()["on"] is False


def test_manual_mode_takes_no_tasks():
    _reset(intake=True, run=True)
    cu_queue.set_auto(False)
    assert cu_queue.submit("t1")["status"] == "off"


def test_the_http_switch_is_one_field():
    """Назовні — лише `on`: змішаний стан одна кнопка показати не вміє."""
    assert set(cu_queue.SwitchRequest.model_fields) == {"on"}
    _reset(intake=False, run=False)
    cu_queue.api_switch(cu_queue.SwitchRequest(on=True))
    assert cu_queue.is_on()
    cu_queue.api_switch(cu_queue.SwitchRequest(on=False))
    assert not any(cu_queue.load()[k] for k in ("intake", "run", "autocommit"))


def test_a_mixed_state_left_by_three_switches_starts_as_off():
    """У томі стану від трьох старих перемикачів міг лишитись будь-який набір.
    Добудовувати його до «увімкнено» не можна — це ще й коміти у вітки."""
    _reset(intake=True, run=True, autocommit=False)
    assert cu_queue.normalize_switches() is True
    assert not any(cu_queue.load()[k] for k in ("intake", "run", "autocommit"))
    _reset(intake=True, run=True, autocommit=True)
    assert cu_queue.normalize_switches() is False and cu_queue.is_on()
    _reset(intake=False, run=False)
    assert cu_queue.normalize_switches() is False and not cu_queue.is_on()


# ------------------------------------- не кваліфікована таска не видна

def test_an_answered_task_nominated_again_does_not_come_back_as_queued():
    """Звірка з ТЗ 23.09.2026: відписана таска зникала з вкладки, а наш же
    коментар (подія ClickUp) або опит номінували її знову — і вона висіла
    карткою «у черзі», доки виконавець не відкине її як уже відповідену."""
    _reset(intake=True, run=False)
    cu_queue.save({**cu_queue.load(), "tasks": {"t1": {
        "task_id": "t1", "state": "done", "name": "T", "qualified": True,
        "branches": [{"branch": "nwf-a", "verdict": pipeline.CLEAN}]}}})
    calls, undo = _told()
    try:
        assert cu_queue.answer_if_passed("t1") == "ok"
    finally:
        undo()
    assert calls == [("t1", "fixed", True)], calls
    cu_queue.submit("t1", source="hook")
    assert [t["task_id"] for t in cu_queue.state()["tasks"]] == [], cu_queue.state()
    answered = _task(comments=[{"user": "Tech Bot", "mentions": [],
                                "text": "fixed — committed via qa_lab"}])
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [answered])])
    try:
        assert cu_queue.qualify("t1") is None
    finally:
        restore()
    assert "t1" not in cu_queue.load()["tasks"]


def test_a_qualified_task_is_shown_even_while_queued():
    """Кваліфікована таска в черзі — це робота, яку людина має бачити."""
    _reset(intake=True, run=False)
    cu_queue.submit("t1", source="poll")
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [_task()])])
    try:
        cu_queue.qualify("t1")
    finally:
        restore()
    st = cu_queue.state()
    assert [t["task_id"] for t in st["tasks"]] == ["t1"] and st["pending"] == 0, st


def test_a_complaint_with_no_findings_is_not_a_success():
    """Кейс 07.09: у тасці «nwf-clomdue-alhu-br-pt не фикс, там футтер слитый»,
    прогін дав п'ять `clean`, і людина побачила зелене там, де дефект їй щойно
    описали словами. «Чисто» після скарги означає рівно одне: чека на це в лаби
    немає — і сказати це треба вголос."""
    _reset()
    rows = []
    cu_queue._deps["add_problems"] = lambda r: rows.extend(r)
    # Скарга, яку роутер РОЗБИРАЄ (інакше таска впала б у «не зміг визначити»
    # ще до прогону): важливо саме те, що чеки після цього мовчать. Розбір
    # тексту роутером — етап 2, тож вмикаємо його явно.
    task = _task(last_comment={"text": "Кукі-банер не закривається, хрестик його не прибирає"})
    seen, restore = _fake_world(task, verdict=pipeline.CLEAN)
    os.environ["CU_ROUTE_COMMENTS"] = "1"
    try:
        rec = cu_queue.process("t1")
    finally:
        os.environ.pop("CU_ROUTE_COMMENTS", None)
        restore()
    assert "жоден чек не спрацював" in rec["reason"], rec
    assert rows and rows[0]["kind"] == "task", rows


def test_a_support_request_is_parked_for_a_person_and_not_run():
    """Етап 1 (21.09.2026): прохання саппорта — людині. Чеки не ганяються,
    у «Проблеми» нічого не пишеться — картка у вкладці і є робоче місце QA."""
    _reset()
    rows = []
    cu_queue._deps["add_problems"] = lambda r: rows.extend(r)
    task = _task(comments=[{"user": "Hugo Support", "mentions": [],
                            "text": "Можешь пофиксить, пожалуйста: почта на чужом домене"}])
    seen, restore = _fake_world(task, verdict=pipeline.WOULD_FIX)
    try:
        rec = cu_queue.process("t1")
    finally:
        restore()
    assert rec["state"] == cu_triage.MANUAL, rec
    assert seen["ran"] == 0, "прохання саппорта пішло в автомат"
    assert rows == [], rows


def test_a_plain_deployment_task_that_is_clean_stays_quiet():
    """Зворотний бік: у звичайної таски скарги немає, і «чисто» там — це
    відповідь, а не привід смикати людину."""
    _reset()
    rows = []
    cu_queue._deps["add_problems"] = lambda r: rows.extend(r)
    seen, restore = _fake_world(_task(), verdict=pipeline.CLEAN)
    try:
        rec = cu_queue.process("t1")
    finally:
        restore()
    assert not rec["reason"], rec
    assert not rows, rows


def test_a_task_level_problem_says_it_has_no_branch():
    """Скарга 07.09: у рядку «не наше» в колонці «вітка» лежить назва ТАСКИ, і
    кнопка «до вітки» чесно шукала вітку з такою назвою. Такий рядок мусить
    сам казати, що він про таску, і нести лінк у ClickUp."""
    _reset(intake=True, run=False)
    rows = []
    cu_queue._deps["add_problems"] = lambda r: rows.extend(r)
    task = _task(name="[754] - Oul - Neymar", url="https://app.clickup.com/t/t1")
    cu_queue._finish("t1", task, "not_ours", "це питання дизайну", problem=True)
    assert rows and rows[0]["kind"] == "task", rows
    assert rows[0]["url"].endswith("/t1") and rows[0]["branch"].startswith("[754]")


def test_a_branch_problem_stays_a_branch_problem():
    """Зворотний бік тієї ж межі: рядок про вітку кнопку «до вітки» мусить
    лишити — інакше з проблем зникне єдиний швидкий шлях у файли."""
    _reset(intake=True, run=False)
    rows = []
    cu_queue._deps["add_problems"] = lambda r: rows.extend(r)
    cu_queue._finish("t1", _task(), "done", "", branches=[
        {"branch": "nwf-a", "verdict": cu_queue.GONE, "note": "вітки немає"}])
    assert rows and rows[0]["branch"] == "nwf-a", rows
    assert "kind" not in rows[0], rows


def test_a_fresh_state_is_really_fresh():
    """`dict(_default_state)` віддає ті самі вкладені словники, тож перший же
    запис у порожній стан мутував би сам дефолт — і наступний «чистий» стан
    приходив би з чужими даними. Спіймано soak-прогоном 07.09."""
    _reset(intake=True, run=False)
    cu_queue._update(lambda st: st["rejected"].setdefault("ghost", "1"))
    assert "ghost" not in cu_queue._default_state["rejected"], \
        "дефолт стану мутували — свіжий стан більше не свіжий"
    assert not cu_queue._default_state["tasks"], "те саме з тасками"


def test_the_domain_is_bound_before_the_checks_run():
    """Знайдено 07.09 по скарзі «лого сайта под доменное имя».

    `logo_domain`, `logo_brand`, `domain_match` і `favicon_link` беруть домен з
    `domains.active_for(branch)` і мовчки повертають ПОРОЖНЬО, якщо його немає.
    Досі домени бив лише імпорт з вкладки ClickUp, тож черга ганяла цю
    четвірку в порожнечу — і скарга про лого чесно отримувала «чисто».
    """
    _reset()
    import domains
    bound = []
    was = domains.bind
    domains.bind = lambda br, dom, tid="", tname="", pid=None: bound.append((br, dom, tid))
    seen, restore = _fake_world(_task(branches=["nwf-a"], domains=["a.blog"]))
    try:
        cu_queue.process("t1")
    finally:
        restore()
        domains.bind = was
    assert bound == [("nwf-a", "a.blog", "t1")], bound


def test_a_branch_without_a_domain_binds_nothing():
    """Порожній домен у `bind` створив би запис-привид в історії доменів."""
    _reset()
    import domains
    bound = []
    was = domains.bind
    domains.bind = lambda br, dom, tid="", tname="", pid=None: bound.append(br)
    seen, restore = _fake_world(_task(branches=["nwf-a"], domains=[]))
    try:
        cu_queue.process("t1")
    finally:
        restore()
        domains.bind = was
    assert bound == [], bound


def test_a_rejected_task_is_not_re_fetched_until_it_changes():
    """Живий прогін 07.09: зі 34 номінованих гейт відсіює 32, і кожна коштує
    запиту в ClickUp — а опит повторюється щопівгодини вічно."""
    _reset(intake=True, run=False)
    alien = _task(id="a1", wtype=None, branches=[], updated="111")
    restore = _stub(items=[
        (clickup_client, "fetch_by_ids",
         lambda items, with_comments=True, token="": [alien])])
    try:
        assert cu_queue.qualify("a1") is None
        assert cu_queue.rejected_before(alien), "відсів мусить памʼятатись"
        # таску поправили — мітка інша, отже питаємо наново
        assert not cu_queue.rejected_before(dict(alien, updated="222"))
    finally:
        restore()


def test_a_task_without_an_update_stamp_is_always_re_checked():
    """Без мітки памʼятати нічого: інакше таска зависла б у відсіяних
    назавжди, і жодна її зміна нас би не розбудила."""
    _reset(intake=True, run=False)
    assert not cu_queue.rejected_before(_task(id="b1", updated=""))


def test_clearing_drops_the_waiting_tasks_but_not_the_running_one():
    """Кнопка потрібна після зміни правила відбору: у черзі лишаються таски,
    номіновані СТАРИМ правилом, і кожна з них інакше коштує запиту в ClickUp
    (100 запитів при ліміті 100/хв)."""
    _reset(intake=True, run=False)
    cu_queue.submit("a"), cu_queue.submit("b")

    def mark(st):
        st["tasks"]["a"]["state"] = "running"
        return None
    cu_queue._update(mark)

    got = cu_queue.api_clear()
    assert got["dropped"] == 1, got
    assert list(cu_queue.load()["tasks"]) == ["a"], "почате не чіпаємо"
    assert cu_queue._q.qsize() == 0


def test_clearing_leaves_the_counter_of_unfinished_tasks_sane():
    """Спорожнення через `_q.queue.clear()` лишило б лічильник незавершених
    ненульовим, і наступний `task_done()` у виконавці кинув би виняток.

    Дивимось на РІЗНИЦЮ, а не на нуль: у файлі тестів поруч живуть справжні
    потоки виконавця, і таска, яку хтось із них тримає просто зараз, теж
    рахується незавершеною — до цієї кнопки вона стосунку не має.
    """
    _reset(intake=True, run=False)
    before = cu_queue._q.unfinished_tasks
    cu_queue.submit("a")
    cu_queue.api_clear()
    assert cu_queue._q.unfinished_tasks == before


# ------------------------------------------------ зміна доменів (25.09.2026)
# Задача Олександра: на «Доменные зоны были изменены» від саппорта лаба сама
# проганяє фікс пошт по всіх вітках таски і пише звіт у ClickUp. Таски при
# цьому вже пофікшені (чекліст ✓, «fixed») — гейт вкладки їх не бере.

def _ms_ago(ms: int) -> str:
    return str(int(time.time() * 1000) - ms)


LAB_FIXED = {"user": "Tech Bot", "mentions": [], "date": _ms_ago(9_000_000),
             "text": "fixed — committed via qa_lab by Liam"}


def _notice(**kw):
    base = {"user": "Victor Support", "user_id": 42, "mentions": ["Tech Bot"],
            "date": _ms_ago(600_000),
            "text": "@Tech Bot Доменные зоны были изменены"}
    base.update(kw)
    return base


def _moved_task(*newer, **kw):
    """TECH-28367 25.09: пофікшена, потім повідомлення, потім службове."""
    return _task(checklist_done=True, checklist_found=True, updated=_ms_ago(60_000),
                 comments=[*newer, _notice(), LAB_FIXED], **kw)


def _domain_world(task, *, verdict=pipeline.WOULD_FIX, protected=False,
                  checks=("favicon", "domain_match")):
    """`_fake_world`, але з чеками пошти й доменів у проєкті."""
    seen, restore = _fake_world(task, verdict=verdict, protected=protected)
    was = runner.checks_for_active_project
    runner.checks_for_active_project = lambda: [
        {"id": c, "group": "auto", "fixable": True} for c in checks]

    def undo():
        runner.checks_for_active_project = was
        restore()
    return seen, undo


def _written():
    """Підміняє запис у ClickUp і коміт; повертає, що лаба написала й закомітила."""
    out = {"clickup": [], "commits": []}
    was_ct, was_ab = clickup_client.complete_task, cu_queue._apply_branch

    def complete(tid, comment="fixed", checklist=True, **kw):
        out["clickup"].append({"task": tid, "comment": comment,
                               "checklist": checklist, **kw})
        return {"ok": True}

    def commit(b, msg, machine=False):
        out["commits"].append({"branch": b["branch"], "msg": msg, "machine": machine})
        return {"branch": b["branch"], "commit": "c0ffee", "files": ["src/a.vue"],
                "error": ""}
    clickup_client.complete_task, cu_queue._apply_branch = complete, commit

    def undo():
        clickup_client.complete_task, cu_queue._apply_branch = was_ct, was_ab
    return out, undo


def test_a_fixed_task_whose_domains_changed_is_taken_and_runs_only_domain_checks():
    _reset(intake=True, run=False)
    task = _moved_task({"user": "ClickBot", "mentions": [], "text": "cf ns done"})
    restore = _stub(items=[(clickup_client, "fetch_by_ids",
                            lambda items, with_comments=True, token="": [task])])
    try:
        assert cu_queue.qualify("t1") is not None, "пофікшену таску зі зміною доменів відсіяно"
    finally:
        restore()
    card = cu_queue.load()["tasks"]["t1"]
    assert card["domain_notice"]["user"] == "Victor Support", card
    seen, undo = _domain_world(task)
    written, unwrite = _written()
    try:
        rec = cu_queue.process("t1", task)
    finally:
        undo(), unwrite()
    assert seen["ran"] == 2 and seen["ids"] == ["domain_match"], seen
    assert rec["triage"]["verdict"] == cu_triage.DOMAINS, rec
    assert [b["verdict"] for b in rec["branches"]] == [pipeline.WOULD_FIX] * 2
    assert written == {"clickup": [], "commits": []}, "без Авто-QA лаба нічого не пише"


def test_with_auto_qa_on_the_domain_fix_is_committed_and_reported_instead_of_fixed():
    _reset(autocommit=True)
    task = _moved_task()
    seen, undo = _domain_world(task)
    written, unwrite = _written()
    try:
        rec = cu_queue.process("t1", task)
    finally:
        undo(), unwrite()
    assert [c["msg"] for c in written["commits"]] == [cu_queue.DOMAINS_MESSAGE] * 2
    assert all(c["machine"] for c in written["commits"]), written
    assert len(written["clickup"]) == 1, written["clickup"]
    note = written["clickup"][0]
    assert note["checklist"] is False, "автоматика ставить чекліст"
    assert note["comment"].startswith(cu_triage.DOMAIN_REPORT_HEAD), note
    assert "nwf-a → a.top: исправлено (файлов: 1)" in note["comment"], note
    assert (note["tag_user_id"], note["tag_username"]) == (42, "Victor Support"), note
    assert rec["state"] == "answered" and "t1" not in cu_queue.load()["tasks"], rec


def test_domains_already_right_are_still_reported():
    """«Уже на нових доменах» — теж відповідь: без неї саппорт не знає, чи
    лаба взагалі бачила повідомлення."""
    _reset(autocommit=True)
    task = _moved_task()
    seen, undo = _domain_world(task, verdict=pipeline.CLEAN)
    written, unwrite = _written()
    try:
        cu_queue.process("t1", task)
    finally:
        undo(), unwrite()
    assert written["commits"] == [], written
    assert "уже на новых доменах" in written["clickup"][0]["comment"], written
    assert "t1" not in cu_queue.load()["tasks"]


def test_a_branch_that_could_not_be_fixed_is_named_and_keeps_the_card():
    _reset(autocommit=True)
    task = _moved_task()
    seen, undo = _domain_world(task, protected=True)
    written, unwrite = _written()
    try:
        cu_queue.process("t1", task)
    finally:
        undo(), unwrite()
    text = written["clickup"][0]["comment"]
    assert "нужен человек" in text and "ветка защищена" in text, text
    card = cu_queue.load()["tasks"]["t1"]
    assert "частину віток не виправлено" in card["reason"], card


def test_a_branch_without_a_domain_is_not_reported_as_fixed():
    _reset(autocommit=True)
    task = _moved_task(domains=["a.top"])            # друга вітка без домену
    seen, undo = _domain_world(task)
    written, unwrite = _written()
    try:
        cu_queue.process("t1", task)
    finally:
        undo(), unwrite()
    assert seen["ran"] == 1, "вітку без домену ганяли"
    assert ("nwf-b: не исправлено — нет домена в Required Domains"
            in written["clickup"][0]["comment"]), written
    assert "t1" in cu_queue.load()["tasks"]


def test_a_person_committing_a_domains_card_sends_the_report_not_a_fixed():
    """Авто-QA вимкнене — картка чекає на людину; її коміт відповідає тим
    самим звітом про домени, а не «fixed» із чеклістом."""
    _reset()
    task = _moved_task()
    seen, undo = _domain_world(task)
    try:
        cu_queue.process("t1", task)
    finally:
        undo()
    written, unwrite = _written()
    try:
        cu_queue.apply([{"task_id": "t1", "branches": []}])
    finally:
        unwrite()
    assert len(written["commits"]) == 2, written
    note = written["clickup"][0]
    assert note["comment"].startswith(cu_triage.DOMAIN_REPORT_HEAD) and not note["checklist"]


def test_after_the_report_the_task_does_not_come_back():
    _reset(intake=True, run=False)
    report = {"user": "Tech Bot", "mentions": [], "date": _ms_ago(1000),
              "text": f"@Victor Support {cu_triage.DOMAIN_REPORT_HEAD} почты и ссылки "
                      "вайтов переведены на новые домены.\ncommitted via qa_lab"}
    task = _moved_task(report)
    restore = _stub(items=[(clickup_client, "fetch_by_ids",
                            lambda items, with_comments=True, token="": [task])])
    try:
        assert cu_queue.qualify("t1") is None
    finally:
        restore()
    assert "t1" not in cu_queue.load()["tasks"]


def test_a_project_without_domain_checks_runs_nothing_rather_than_everything():
    """Порожній список `run_checks` читає як «усі чеки» — прогін після зміни
    доменів у такому проєкті мусить не ганяти нічого, а не все."""
    _reset()
    task = _moved_task()
    seen, undo = _domain_world(task, checks=("favicon",))
    try:
        rec = cu_queue.process("t1", task)
    finally:
        undo()
    assert seen["ran"] == 0, seen
    assert [b["verdict"] for b in rec["branches"]] == [pipeline.CLEAN] * 2, rec


def test_a_new_domain_on_the_same_commit_runs_the_branch_again():
    """Саппорт міняє домени без коміту у вітці: скіп «той самий коміт і ті
    самі чеки» лишав би вітку з поштою на старому домені."""
    _reset()
    seen, undo = _fake_world(_task(), verdict=pipeline.CLEAN)
    try:
        cu_queue.process("t1")
    finally:
        undo()
    moved = _task(domains=["a.lat", "b.lat"])
    seen, undo = _fake_world(moved, verdict=pipeline.CLEAN)
    try:
        rec = cu_queue.process("t1")
    finally:
        undo()
    assert seen["ran"] == 2, "нові домени на тому самому коміті скіпнуто"
    assert [b["domain"] for b in rec["branches"]] == ["a.lat", "b.lat"], rec


def test_a_tag_of_tech_bot_runs_the_domain_fix_and_names_old_and_new_domains():
    """`@Tech Bot Доменные зоны были изменены` на пофікшеній тасці: лаба
    лагодить і пише в звіті, з якого домену на який (реєстр `domains.json`)."""
    import domains
    _reset(autocommit=True)
    domains.bind("nwf-a", "a.buzz", pid="white-pages")     # змінено: buzz → top
    domains.bind("nwf-b", "b.top", pid="white-pages")      # той самий
    task = _task(checklist_done=True, checklist_found=True, comments=[_notice(), LAB_FIXED])
    restore = _stub(items=[(clickup_client, "fetch_by_ids",
                            lambda items, with_comments=True, token="": [task])])
    try:
        got = cu_queue.qualify("t1")
    finally:
        restore()
    seen, undo = _domain_world(task)
    written, unwrite = _written()
    try:
        assert got is not None, "тег Tech Bot про домени відсіяно"
        cu_queue.process("t1", got)
    finally:
        undo(), unwrite()
    text = written["clickup"][0]["comment"]
    assert "nwf-a: a.buzz → a.top: исправлено (файлов: 1)" in text, text
    assert "nwf-b → b.top: исправлено" in text, text
    assert domains.bound_anywhere("nwf-a") == "a.top", "прогін не перепривʼязав домен"


def test_the_phrase_tagged_to_a_person_leaves_a_fixed_task_alone():
    """Сьогоднішній формат («@Liam Frontend …») — сповіщення черговому, а не
    лабі: ні автофіксу, ні картки «ручний розбір» (баг 25.09)."""
    _reset(intake=True, run=False)
    task = _task(checklist_done=True, checklist_found=True, updated=_ms_ago(60_000),
                 comments=[_notice(mentions=["Liam Frontend"],
                                   text="@Liam Frontend Доменные зоны были изменены"),
                           LAB_FIXED])
    restore = _stub(items=[(clickup_client, "fetch_by_ids",
                            lambda items, with_comments=True, token="": [task])])
    try:
        assert cu_queue.qualify("t1") is None
    finally:
        restore()
    assert "t1" not in cu_queue.load()["tasks"]


def test_a_phrase_posted_by_a_bot_gets_a_report_without_a_tag():
    """Автоматизація саппорта може постити від бот-акаунта — тегати бота
    нема сенсу: звіт іде без тегу, його бачать усі в тасці."""
    _reset(autocommit=True)
    task = _task(checklist_done=True, checklist_found=True,
                 comments=[_notice(user="ClickBot", user_id=7), LAB_FIXED])
    seen, undo = _domain_world(task, verdict=pipeline.CLEAN)
    written, unwrite = _written()
    try:
        cu_queue.process("t1", task)
    finally:
        undo(), unwrite()
    note = written["clickup"][0]
    assert note["tag_user_id"] is None and note["tag_username"] == "", note


def test_the_poll_nominates_a_ticked_task_that_changed_within_a_day():
    """Вебхук буває у `failing` — опит мусить сам помітити таску, де могли
    змінити домени, хоч чекліст у неї проставлений."""
    _reset(intake=True, run=False)
    fresh = _task(id="fresh", checklist_done=True, updated=_ms_ago(3_600_000))
    old = _task(id="old", checklist_done=True, updated=_ms_ago(3 * 86_400_000))
    black = _task(id="black", checklist_done=True, updated=_ms_ago(1000),
                  tag_excluded=True)
    restore = _stub(items=[(clickup_client, "fetch_all",
                            lambda include_closed=False, skipped=None: [fresh, old, black])])
    try:
        got = cu_queue.poll_once()
    finally:
        restore()
    assert got["queued"] == 1 and "fresh" in cu_queue.load()["tasks"], got


if __name__ == "__main__":
    run(dict(globals()))
