"""Тріаж: хто наш клієнт, що з ним робити і що робити з «не знаю».

Найдорожче тут — різниця між ТРЬОМА відповідями, які легко злити в одну:

* `skip` — не наша за полями (немає віток). Не показуємо ніде;
* `not_ours` — визначено ТОЧНО, що це не наша робота (домен у чорному списку,
  ціни, заборонена лексика). Показуємо з поясненням, не оброблюємо;
* `undetermined` — «не знаю». Теж показуємо, але це інша річ: саме її ловить
  кнопка «Актуалізувати», бо новий скіл може перетворити її на `ours`.

Злити `not_ours` з `undetermined` означало б, що кнопка щоразу перебирає й те,
для чого нового скіла ніколи не буде.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["QA_LAB_STATE_DIR"] = tempfile.mkdtemp(prefix="cu-triage-")
os.environ["MOCK_MODE"] = "1"

from _harness import run                                        # noqa: E402

import ai_bridge                                                # noqa: E402
import ai_router                                                # noqa: E402
import cu_triage                                                # noqa: E402


def _task(**kw):
    # Статус прохідний: з 07.09 `qa` і `domains hold` не проходять гейт
    # вкладки, а тріаж стоїть уже ЗА ним (вимір — tests/test_cu_qualify.py)
    base = {"id": "t1", "name": "[p-52] whites", "branches": ["nwf-a"],
            "domains": ["a.blog"],
            "wtype": "1/2 круг", "status": "in progress", "status_match": True,
            "status_type": "custom",
            "checklist_loaded": True, "checklist_done": False,
            "description": "", "last_comment": None}
    base.update(kw)
    return base


def _routing(**kw):
    base = {"checks": [], "router": "keywords", "confidence": 0.0,
            "not_ours": [], "reason": ""}
    base.update(kw)
    return base


def _with_route(routing, *, available=True):
    """Підміняє роутер мосту і вмикає розбір коментарів роутером — це етап 2
    (з 21.09.2026 за замовчуванням вимкнений, див. «етап 1» нижче). Мережу
    тести не смикають ніколи."""
    saved = (ai_bridge.do_route, ai_bridge.scope_checks, ai_router.available,
             cu_triage.skills_fingerprint, os.environ.get("CU_ROUTE_COMMENTS"))
    ai_bridge.do_route = lambda text, branch, **kw: routing
    ai_bridge.scope_checks = lambda r: list(r.get("checks") or [])
    ai_router.available = lambda: (available, "" if available
                                   else "ANTHROPIC_API_KEY не заданий")
    cu_triage.skills_fingerprint = lambda: "fp1"
    os.environ["CU_ROUTE_COMMENTS"] = "1"

    def restore():
        (ai_bridge.do_route, ai_bridge.scope_checks, ai_router.available,
         cu_triage.skills_fingerprint, env) = saved
        if env is None:
            os.environ.pop("CU_ROUTE_COMMENTS", None)
        else:
            os.environ["CU_ROUTE_COMMENTS"] = env
    return restore


COMPLAINT = "На вайті чуже лого і телефон іншої країни, подивіться будь ласка"


# ------------------------------------------------------------ поля таски

def test_a_task_without_branches_is_skipped_silently():
    restore = _with_route(_routing())
    try:
        got = cu_triage.classify(_task(branches=[]))
    finally:
        restore()
    assert got["verdict"] == cu_triage.SKIP, got


def test_a_plain_deployment_task_is_ours_without_the_model():
    """Заміряно 04.09: опис має 0 з 12 придатних тасок. Для них процедура
    відома без жодної моделі — повний прогін."""
    called = []
    restore = _with_route(_routing())
    ai_bridge.do_route = lambda *a, **k: called.append(1) or _routing()
    try:
        got = cu_triage.classify(_task())
    finally:
        restore()
    assert got["verdict"] == cu_triage.OURS, got
    assert got["router"] == "fields" and got["confidence"] == 1.0
    assert got["checks"] == [], "зайвих чеків звичайній тасці не треба"
    assert called == [], "модель покликали там, де скарги немає"


def test_service_chatter_is_not_a_complaint():
    """«cf ns done» — це не скарга, а крок деплою (клоака й NS).

    Межа тонка і тримається саме тут: `fixed` означає «зроблено, більше нема
    чого робити» і таску закриває (`already_answered`), а `cf ns done` —
    службова відмітка процесу, після якої вайт якраз і треба перевірити.
    """
    restore = _with_route(_routing())
    try:
        got = cu_triage.classify(_task(last_comment={"text": "cf ns done"}))
    finally:
        restore()
    assert got["verdict"] == cu_triage.OURS and got["router"] == "fields", got


# ------------------------------------------------------------ скарга

def test_a_complaint_the_router_understands_is_ours_with_extra_checks():
    restore = _with_route(_routing(checks=["logo_domain"], router="claude",
                                   confidence=0.9))
    try:
        got = cu_triage.classify(_task(description=COMPLAINT))
    finally:
        restore()
    assert got["verdict"] == cu_triage.OURS, got
    assert got["checks"] == ["logo_domain"], got
    assert got["text_hash"], "відбиток тексту потрібен кешу тріажу"


def test_a_complaint_the_lab_cannot_fix_is_not_ours_with_a_reason():
    """`NOT_OURS` каже не «не знаю», а «ось чому це не лікується з гілки»."""
    restore = _with_route(_routing(not_ours=[
        {"id": "reputation", "чому": "домен у чорному списку Google"}]))
    try:
        got = cu_triage.classify(_task(description="Домен у чорному списку " * 3))
    finally:
        restore()
    assert got["verdict"] == cu_triage.NOT_OURS, got
    assert "чорному списку" in got["reason"], got


def test_a_complaint_nobody_could_route_is_undetermined():
    restore = _with_route(_routing())
    try:
        got = cu_triage.classify(_task(description=COMPLAINT))
    finally:
        restore()
    assert got["verdict"] == cu_triage.UNDETERMINED, got
    assert got["checks"] == []


def test_no_model_says_so_in_the_reason():
    """Без ключа тріаж не мовчить: людина мусить бачити, ЧОМУ «не знаю»."""
    restore = _with_route(_routing(), available=False)
    try:
        got = cu_triage.classify(_task(description=COMPLAINT))
    finally:
        restore()
    assert got["verdict"] == cu_triage.UNDETERMINED, got
    assert "ANTHROPIC_API_KEY" in got["reason"], got


def test_a_broken_tool_is_not_our_defect():
    restore = _with_route(_routing(tool_failure=True,
                                   reason="збій прогону TSM — це не дефект вайта"))
    try:
        got = cu_triage.classify(_task(description=COMPLAINT))
    finally:
        restore()
    assert got["verdict"] == cu_triage.NOT_OURS, got


# ------------------------------------------------------------ етап 1: саппорт
# Правило колеги-QA від 21.09.2026: немає прохання саппорта — повний
# автоматичний QA; є — людині. Роутер при цьому не смикається зовсім.

def _c(user, text, mentions=()):
    return {"user": user, "text": text, "mentions": list(mentions)}


def _no_router():
    """Етап 1 не має права кликати роутер — ні ключ, ні мережа не потрібні."""
    saved = ai_bridge.do_route

    def boom(*a, **kw):
        raise AssertionError("етап 1 покликав роутер")
    ai_bridge.do_route = boom
    return lambda: setattr(ai_bridge, "do_route", saved)


def test_stage_one_a_support_fix_request_goes_to_a_person():
    restore = _no_router()
    try:
        got = cu_triage.classify(_task(comments=[
            _c("Hugo Support", "Можешь пофиксить, пожалуйста: nwf-a a.blog - "
               "• Почта для связи только на чужом домене")]))
    finally:
        restore()
    assert got["verdict"] == cu_triage.MANUAL, got
    assert "Почта для связи" in got["reason"], got


def test_stage_one_service_notes_of_support_are_not_requests():
    """Заміряно на корпусі 03.09: це кроки процесу, не прохання про фікс."""
    notes = ["Took to deploy", "took", "after tech pause - took to redeploy",
             "cf + ns done", "a.blog b.blog all done, check",
             "gitlab.example.com/development/mass-deploy/-/pipelines/130997",
             "https://gitlab.example.com/development/mass-deploy/-/pipelines/1",
             "deploy+env"]
    restore = _no_router()
    try:
        for note in notes:
            got = cu_triage.classify(_task(comments=[_c("Rita Support", note)]))
            assert got["verdict"] == cu_triage.OURS, (note, got)
        got = cu_triage.classify(_task(comments=[
            _c("Toby Support", "@Shadow MB done, check", mentions=["Shadow MB"])]))
        assert got["verdict"] == cu_triage.OURS, got
    finally:
        restore()


def test_stage_one_only_support_counts():
    """«Коммент от саппорта»: байєри й автоматика — не саппорт."""
    restore = _no_router()
    try:
        for user, text in (("Ella Berg", "project: black-pages defaults: CREATE_BINOM"),
                           ("ClickBot", "cf ns done"),
                           ("Kite MB", "можно что-то решить с этой задачей")):
            got = cu_triage.classify(_task(comments=[_c(user, text)]))
            assert got["verdict"] == cu_triage.OURS, (user, got)
    finally:
        restore()


def test_stage_one_a_status_note_is_not_a_request():
    """Живий прогін 21.09: «ленд на фиксе» від саппорта (лендинг у роботі в
    іншої команди) повернуло закриту таску як ручну. Прохання — це те, що
    звернене до фронта або має форму прохання, а не «усе, що не службове»."""
    for note in ("ленд на фиксе", "Подскажи пожалуйста, эта задача должна упасть сразу фронтам"):
        got = cu_triage.support_request(_task(comments=[_c("Dean Support", note)]))
        assert got is None, (note, got)


def test_stage_one_a_question_addressed_to_a_frontend_is_a_request():
    got = cu_triage.support_request(_task(comments=[
        _c("Theo Support", "@Nora Frontend а партнеры были удалены?",
           mentions=["Nora Frontend"])]))
    assert got and "партнеры" in got["text"], got


def test_stage_one_a_request_after_our_answer_brings_the_task_to_a_person():
    got = cu_triage.support_request(_task(comments=[
        _c("Hugo Support", "не фикс, почта всё ещё на чужом домене"),
        _c("Tech Bot", "fixed — committed via qa_lab by Liam"),
        _c("Hugo Support", "Можешь пофиксить, пожалуйста: старое")]))
    assert got and "не фикс" in got["text"], got


def test_stage_one_an_answered_request_is_not_a_request():
    """Наша відповідь або людське `fixed` (навіть з @тегом) — межа: старіше за
    неї вже зроблено."""
    for closing in (_c("Tech Bot", "fixed — committed via qa_lab by Liam"),
                    _c("Nora Frontend", "@Toby Support fixed", mentions=["Toby Support"])):
        got = cu_triage.support_request(_task(comments=[
            closing, _c("Hugo Support", "Можешь пофиксить, пожалуйста: лого")]))
        assert got is None, (closing, got)


def test_stage_one_a_short_request_still_resets_the_triage_cache():
    """«@Nora Frontend не фикс» коротше порогу скарги — але вирок від нього
    змінюється, тож і ключ кешу мусить."""
    before = _task(comments=[_c("Tech Bot", "fixed — committed via qa_lab")])
    after = _task(comments=[_c("Hugo Support", "@Nora Frontend не фикс",
                               mentions=["Nora Frontend"])] + before["comments"])
    assert cu_triage.decision_text(before) != cu_triage.decision_text(after)


# ------------------------------------------------------------ відбитки

def test_the_skills_fingerprint_changes_with_the_skills():
    """Відбиток — це і є відповідь на «чи змінилось щось відтоді, як ми
    сказали «не знаю»». Без нього кнопка «Актуалізувати» або платила б
    моделлю щоразу, або не помічала б нового скіла."""
    # Підміняємо САМ каталог тріажу, а не `ai_skills.catalog`: інакше
    # аргументи виклику обчислились би раніше за підміну і тест поліз би у
    # справжнє сховище скілів (Mongo).
    saved = cu_triage.catalog
    cu_triage.catalog = lambda: [{"id": "a", "enriched": True}]
    try:
        one = cu_triage.skills_fingerprint()
        cu_triage.catalog = lambda: [{"id": "a", "enriched": True},
                                     {"id": "b", "enriched": True}]
        two = cu_triage.skills_fingerprint()
    finally:
        cu_triage.catalog = saved
    assert one != two, "новий скіл не змінив відбиток"


def test_the_text_hash_ignores_nothing_but_the_text():
    a = cu_triage.text_hash("одне")
    assert a == cu_triage.text_hash("одне") and a != cu_triage.text_hash("інше")


def test_branch_names_in_the_text_are_not_the_complaint():
    """Знайдено живим прогоном 07.09. Таска «Можешь пофиксить, пожалуйста:
    nwf-alvef-anp-papbcapd-br-pt …» дала `partner_banks` — роутер прочитав
    слово «partners» З НАЗВИ ВІТКИ. Вітки в тасці вже є окремим полем, тож у
    тексті вони лише шум."""
    task = _task(branches=["nwf-alvef-anp-papbcapd-br-pt"],
                 last_comment={"text": "Можешь пофиксить, пожалуйста: "
                                       "nwf-alvef-anp-papbcapd-br-pt"})
    assert cu_triage.complaint_text(task) == "", cu_triage.complaint_text(task)


def test_a_real_complaint_survives_the_branch_names_around_it():
    """Зворотний бік: вітки в тексті часто стоять ПЕРЕД справжньою скаргою,
    і викидати треба саме їх, а не весь текст."""
    task = _task(branches=["nwf-bafhuge-colsetfugii-br-pt"],
                 last_comment={"text": "nwf-bafhuge-colsetfugii-br-pt\n"
                                       "Сайты полупустые, много элементов "
                                       "с дырами вместо текста или картинки"})
    got = cu_triage.complaint_text(task)
    assert "полупустые" in got and "nwf-" not in got, got


def test_a_neighbouring_branch_slug_is_stripped_too():
    """У скаргах трапляються вітки, яких у полі Safe Page цієї таски немає."""
    got = cu_triage.strip_targets("глянь nwf-codho-demizvetfaradco-br-pt тут дірки",
                                  _task(branches=[]))
    assert "nwf-" not in got and "дірки" in got, got


def test_a_bare_fixed_from_a_person_closes_the_task_too():
    """Вимога замовника 07.09: «якщо просто Fixed — то не треба».

    Наш підпис тут не потрібен: людина закриває таску словом, і це та сама
    відповідь. А от «fixed логотип, но форма всё ещё не шлёт» — не закриває,
    тому порівнюється ЦІЛИЙ коментар, а не підрядок.
    """
    assert cu_triage.already_answered(_task(last_comment={"text": "Fixed"}))
    assert cu_triage.already_answered(_task(last_comment={"text": "готово"}))
    assert not cu_triage.already_answered(
        _task(last_comment={"text": "fixed логотип, но форма всё ещё не шлёт"}))
    assert not cu_triage.already_answered(_task(last_comment={"text": "cf ns done"}))


def test_a_task_we_already_answered_is_not_taken_again():
    """Скарга 07.09: у чергу приїхали таски, під якими вже стояв наш «fixed».

    Чекліст `whites` тут не помічник — він є в однієї таски з 479, тож
    єдиний надійний слід нашої роботи це власний підпис у коментарі.
    """
    got = cu_triage.classify(_task(comments=[
        {"text": "@Hugo Support fixed — committed via qa_lab by Liam",
         "user": "Tech Bot"}]), use_model=False)
    assert got["verdict"] == cu_triage.SKIP, got
    assert "вже відповіла" in got["reason"], got


def test_a_new_complaint_after_our_answer_brings_the_task_back():
    """Інакше одна відповідь закрила б таску назавжди: людина пише ще раз
    саме тоді, коли перший фікс не допоміг."""
    got = cu_triage.classify(_task(comments=[
        {"text": "не помогло, лого всё ещё чужое", "user": "Hugo Support"},
        {"text": "fixed — committed via qa_lab", "user": "Tech Bot"}]),
        use_model=False)
    assert got["verdict"] != cu_triage.SKIP, got


def test_our_answer_deeper_in_the_thread_does_not_close_the_task():
    """«Є десь у стрічці» — не те саме, що «останнє слово наше»."""
    assert not cu_triage.already_answered(_task(comments=[
        {"text": "а ещё вот тут поправьте", "user": "Hugo Support"},
        {"text": "fixed — committed via qa_lab", "user": "Tech Bot"}]))


def test_a_service_mark_after_our_answer_keeps_the_task_away():
    """З 23.09.2026 лаба чекліста не ставить, і поза вкладкою таску тримає
    лише наш коментар. Службова відмітка після нього — не нове слово: інакше
    кожне `took to redeploy` гнало б таску в авто-QA ще раз, і лаба
    відписувала б `fixed` удруге й утретє."""
    ours = {"text": "fixed — committed via qa_lab", "user": "Tech Bot"}
    for mark in ("took to redeploy", "took", "@Hugo Support MB done, check",
                 "https://gitlab.example.com/development/mass-deploy/-/pipelines/130997",
                 "tech pause", "cf ns done"):
        assert cu_triage.already_answered(_task(comments=[
            {"text": mark, "user": "Toby Support", "mentions": ["Hugo Support"]},
            ours])), mark


def test_a_service_mark_alone_is_not_an_answer():
    """Без нашої відповіді службова відмітка нічого не закриває: `cf ns done`
    — крок деплою, таска звичайна робоча."""
    assert not cu_triage.already_answered(_task(comments=[
        {"text": "took to deploy", "user": "Toby Support"}]))


def test_a_task_with_a_fixed_and_nothing_asked_after_it_is_skipped():
    """«Вебхук взагалі не має грузити задачі з вже наявним fixed» (24.09).
    `already_answered` тут безсилий: «апрув, дякую» після «fixed» для нього —
    нове слово, і таска поверталась у чергу."""
    task = _task(comments=[{"text": "апрув, дякую", "user": "Kite MB"},
                           {"text": "fixed", "user": "Liam Frontend"}])
    assert not cu_triage.already_answered(task)
    assert cu_triage.fixed_is_last(task)
    got = cu_triage.classify(task, use_model=False)
    assert got["verdict"] == cu_triage.SKIP and "вже є fixed" in got["reason"], got


def test_a_complaint_after_the_fix_counts_as_a_request():
    """Відколи вебхук не бере таски з «fixed», саме цей шаблон вирішує, чи
    скарга «після фіксу» повернеться до людини. Фрази — з корпусу 03.09: зі 59
    змістовних коментарів саппорта старий шаблон ловив 42, доповнений — 49,
    і всі 7 нових — справжні скарги."""
    for said in ("всё равно не работает форма ( контейнеры удалял",
                 "Не работает форма 😓 Когда заполнил и нажимаешь отправить",
                 "окно куки не закрывается и ведет на несуществующие страницы",
                 "есть 2 проблемы на фикс: Не переходит на страницу thank-you",
                 "не отображается доменная часть в емейле",
                 "не помогло, лого всё ещё чужое"):
        t = _task(comments=[{"text": said, "user": "Hugo Support", "mentions": []}])
        assert cu_triage.support_request(t), said
    # «ленд на фиксе» (живий прогін 21.09) і службові відмітки — як і було, ні
    for said in ("ленд на фиксе", "took to deploy", "@Hugo Support MB done, check"):
        t = _task(comments=[{"text": said, "user": "Toby Support",
                             "mentions": ["Hugo Support"]}])
        assert not cu_triage.support_request(t), said


# ------------------------------------------------ зміна доменів (25.09.2026)
# Сім тасок за годину: «@Liam Frontend Доменные зоны были изменены» після
# «fixed» колеги. Лаба рахувала це проханням (звернене до Frontend) і вертала
# пофікшені таски у вкладку; а пошти у вітках тим часом стояли на старих зонах.

NOW = 1790340000000                        # 25.09.2026, ~14:40 за Києвом
LAB_FIXED = {"user": "Tech Bot", "mentions": [], "date": str(NOW - 5_000_000),
             "text": "fixed — committed via qa_lab by Liam"}


def _notice(text="@Liam Frontend Доменные зоны были изменены", user="Victor Support",
            mentions=("Liam Frontend",), ago_ms=3_000_000):
    return {"user": user, "user_id": 42, "mentions": list(mentions),
            "date": str(NOW - ago_ms), "text": text}


def _domains_task(*newer, notice=None):
    """Як TECH-28367: чекліст ✓, «fixed» лаби, повідомлення, далі службове."""
    return _task(checklist_done=True, checklist_found=True, comments=[
        *newer, notice or _notice(), LAB_FIXED])


def test_the_domain_notices_seen_live_are_recognised():
    """Обидві фрази 25.09 (7 з 7 тасок), з будь-яким тегом — `@Tech Bot` саппорт
    пообіцяв ставити замість чергового фронта, — і природні варіації."""
    yes = [("@Liam Frontend Доменные зоны были изменены", ["Liam Frontend"]),
           ("@Liam Frontend Домены были изменены", ["Liam Frontend"]),
           ("@Tech Bot Доменные зоны были изменены", ["Tech Bot"]),
           ("Доменные зоны изменены.", []), ("Изменили доменные зоны", []),
           ("Доменные зоны были изменены на .lat", []),
           ("Доменні зони змінено", []), ("домены поменяли", [])]
    for said, mentions in yes:
        c = _notice(said, mentions=mentions)
        assert cu_triage.domain_notice(c, _task()), said
    no = [("Доменные зоны были изменены, поправь почту", "Victor Support"),
          ("а партнеры были удалены?", "Theo Support"),
          ("фикс емейлов пж", "Toby Support"),
          ("Можешь пофиксить, пожалуйста: nwf-a - • Почта для связи только на "
           "чужом домене", "Vince Support"),
          ("Доменные зоны были изменены", "Ella Berg")]      # не саппорт
    for said, who in no:
        assert not cu_triage.domain_notice(_notice(said, user=who, mentions=()),
                                           _task()), said


def test_a_domain_notice_after_the_fix_does_not_bring_the_task_to_a_person():
    """Рівно скрін 25.09: таска пофікшена, після «fixed» — повідомлення і
    службове. Людині її не віддаємо: це робота автоматики, не прохання."""
    task = _domains_task(
        {"user": "Ella Berg", "mentions": [], "text": "title: '[785]' project: black-pages"},
        {"user": "ClickBot", "mentions": [], "text": "cf ns done"})
    assert cu_triage.support_request(task) is None
    assert not cu_triage.asks_again(task) and not cu_triage.gate_ok(task)
    assert cu_triage.fixed_is_last(task)
    assert cu_triage.classify(task, use_model=False)["verdict"] == cu_triage.SKIP


KEY = "@Tech Bot Доменные зоны были изменены"


def test_a_fresh_notice_waits_until_the_lab_or_a_person_answers_it():
    restore = _as_bot()
    try:
        task = _domains_task({"user": "ClickBot", "mentions": [], "text": "cf ns done"},
                             notice=_to_bot(KEY))
        got = cu_triage.domain_change(task, now_ms=NOW)
        assert got and got["user"] == "Victor Support" and got["user_id"] == 42, got
        assert got["text"] == "Доменные зоны были изменены", got
        report = {"user": "Tech Bot", "mentions": [], "date": str(NOW - 1000),
                  "text": f"{cu_triage.DOMAIN_REPORT_HEAD} почты и ссылки вайтов переведены "
                          "на новые домены.\nnwf-a → a.lat: исправлено (файлов: 3)\n"
                          "committed via qa_lab"}
        for answer in (report, LAB_FIXED,
                       {"user": "Liam Frontend", "mentions": [], "text": "fixed"}):
            done = _domains_task(answer, notice=_to_bot(KEY))
            assert cu_triage.domain_change(done, now_ms=NOW) is None, answer["text"]
    finally:
        restore()


def test_a_stale_or_undated_notice_is_left_alone():
    """Межа — для першого ж запуску: інакше лаба пройшлась би по всіх колись
    змінених доменах і писала б звіти в давно задеплоєні таски."""
    restore = _as_bot()
    try:
        old = _domains_task(notice=_notice(KEY, mentions=("Tech Bot",),
                                           ago_ms=25 * 3_600_000))
        assert cu_triage.domain_change(old, now_ms=NOW) is None
        assert cu_triage.domain_change(old, now_ms=NOW, hours=48)
        undated = _domains_task(notice={**_to_bot(KEY), "date": ""})
        assert cu_triage.domain_change(undated, now_ms=NOW) is None
        # і коментарі не дочитані — рішення «діяти» було б здогадкою
        assert cu_triage.domain_change(_task(comments=None), now_ms=NOW) is None
    finally:
        restore()


def test_our_domain_report_answers_the_notice_but_not_the_task():
    """Звіт про домени — не «fixed»: прохання саппорта поруч лишається
    проханням (іде людині), а ще не пофікшена таска далі йде в QA."""
    report = {"user": "Tech Bot", "mentions": [],
              "text": f"@Victor Support {cu_triage.DOMAIN_REPORT_HEAD} почты уже на "
                      "новых доменах\ncommitted via qa_lab"}
    ask = {"user": "Hugo Support", "mentions": [], "text": "не фикс, хедер съехал"}
    task = _domains_task(report, ask)
    assert not cu_triage._is_closing(report, task)
    assert cu_triage.domain_change(task, now_ms=NOW) is None
    got = cu_triage.support_request(task)
    assert got and "хедер" in got["text"], got
    open_task = _task(comments=[report, _notice()])
    assert not cu_triage.already_answered(open_task)
    assert cu_triage.classify(open_task, use_model=False)["verdict"] == cu_triage.OURS
    assert not cu_triage.fixed_by(report, task), "звіт про домени — не «fixed»"


def test_a_notice_mixed_with_a_request_still_goes_to_a_person():
    """Повідомленням вважаємо лише коментар, що ЦІЛКОМ ним є: решта — прохання."""
    task = _domains_task(notice=_notice("@Liam Frontend Домены были изменены, "
                                        "поправь хедер"))
    assert cu_triage.domain_change(task, now_ms=NOW) is None
    assert cu_triage.support_request(task)
    assert cu_triage.classify(task, use_model=False)["verdict"] == cu_triage.MANUAL


# --- тег @Tech Bot (задача Олександра «по тегу», прохання Victor 25.09) ---

def _as_bot(name="Tech Bot"):
    """Імʼя акаунта лаби — змінною, як на стенді: у тестах мережі немає."""
    import clickup_client
    saved = os.environ.get("CLICKUP_BOT_NAME")
    if name:
        os.environ["CLICKUP_BOT_NAME"] = name
    else:
        os.environ.pop("CLICKUP_BOT_NAME", None)
    clickup_client._LAB_ACCOUNT.update(name="", until=0.0)

    def restore():
        if saved is None:
            os.environ.pop("CLICKUP_BOT_NAME", None)
        else:
            os.environ["CLICKUP_BOT_NAME"] = saved
    return restore


def _to_bot(text):
    return _notice(text, mentions=("Tech Bot",))


def test_the_tag_and_the_key_phrase_together_trigger():
    """Домовленість 25.09: тег `@Tech Bot` І фраза «Доменные зоны были
    изменены». Фраза — будь-де в коментарі й у близьких формах; тег — згадкою
    або простим текстом; автор — будь-хто, крім самої лаби (автоматизація
    саппорта може постити від бота)."""
    restore = _as_bot()
    try:
        yes = [_to_bot(KEY), _to_bot("@Tech Bot доменные зоны были изменены."),
               _to_bot("@Tech Bot Домены были изменены"),
               _to_bot("@Tech Bot Доменные зоны были изменены\nnwf-a a.blog"),
               _notice(KEY, mentions=()),                              # тег текстом
               _notice(KEY, user="ClickBot", mentions=("Tech Bot",))]  # від бота
        for c in yes:
            got = cu_triage.domain_change(_domains_task(notice=c), now_ms=NOW)
            assert got and got["via"] == "tag", c["text"]
        no = [_to_bot("@Tech Bot домены"),                       # без дієслова
              _to_bot("@Tech Bot почты на новые домены плиз"),
              _notice("Доменные зоны были изменены", mentions=()),   # без тегу
              _notice(),                                            # тег людині
              _notice(KEY, user="Tech Bot", mentions=("Tech Bot",))]  # сама лаба
        for c in no:
            task = _domains_task(notice=c)
            assert cu_triage.domain_change(task, now_ms=NOW) is None, c["text"]
        # фраза без тегу Tech Bot — не тригер, але й не прохання людині
        for c in (_notice(), _notice("Доменные зоны были изменены", mentions=())):
            assert cu_triage.support_request(_domains_task(notice=c)) is None, c["text"]
    finally:
        restore()


def test_the_registry_gives_the_report_the_old_domain_but_triggers_nothing():
    """Реєстр `domains.json` (під який домен лаба востаннє лагодила вітку)
    потрібен звіту — «з якого на який». Тригером він не є: без фрази тег
    Tech Bot — звичайне звернення до фронта."""
    import domains
    import projects
    projects.init()
    domains.bind("nwf-a", "a.buzz", pid="white-pages")
    restore = _as_bot()
    try:
        got = cu_triage.domain_change(_domains_task(notice=_to_bot(KEY)), now_ms=NOW)
        assert got["moved"] == [{"branch": "nwf-a", "old": "a.buzz", "new": "a.blog"}], got
        other = _domains_task(notice=_to_bot("@Tech Bot глянь, пожалуйста"))
        assert cu_triage.domain_change(other, now_ms=NOW) is None
        assert cu_triage.support_request(other), "звернення до Tech Bot загубилось"
    finally:
        domains.bind("nwf-a", "a.blog", pid="white-pages")
        restore()


def test_a_tag_of_the_lab_about_something_else_goes_to_a_person():
    """Не домени — звернення до фронта, як `@… Frontend`: людині, а не в нікуди."""
    restore = _as_bot()
    try:
        task = _domains_task(notice=_to_bot("@Tech Bot хедер съехал на мобилке"))
        assert cu_triage.domain_change(task, now_ms=NOW) is None
        assert cu_triage.support_request(task)
        assert cu_triage.classify(task, use_model=False)["verdict"] == cu_triage.MANUAL
    finally:
        restore()


def test_without_a_known_lab_account_a_tag_is_only_a_mention():
    restore = _as_bot(name="")
    try:
        task = _domains_task(notice=_to_bot(KEY))
        assert cu_triage.domain_change(task, now_ms=NOW) is None
    finally:
        restore()


def test_a_tag_about_domains_with_another_request_reaches_a_person_too():
    """Домени лагодить лаба, а те, про що попросили окрім них, — людина."""
    restore = _as_bot()
    try:
        task = _domains_task(notice=_to_bot("@Tech Bot домены изменены, и хедер поправь"))
        assert cu_triage.domain_change(task, now_ms=NOW)["via"] == "tag"
        got = cu_triage.support_request(task)
        assert got and "хедер" in got["text"], got
        only = _domains_task(notice=_to_bot("@Tech Bot поменяли зоны на .lat, проверь почты"))
        assert cu_triage.support_request(only) is None, "доменне звернення пішло людині"
    finally:
        restore()


if __name__ == "__main__":
    run(dict(globals()))
