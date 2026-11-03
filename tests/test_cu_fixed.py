"""«Fixed уже є»: попередження ручній роботі, що таску вже відписали.

Кейс — [878] Microsoft br-pt, 23.09.2026: чотири «fixed» за пів години (три
від колеги, один від «Administrator»), бо кожен працював зі своїм, уже
застарілим списком тасок. Юзер 24.09: «попереджати, але не блокувати роботу…
перевіряти по fixed в ClickUp». Тут закріплено три речі:

* що саме вважається «fixed» і хто його автор (підпис лаби, а не Tech Bot);
* що «таску відкрили знову» — це прохання саппорта, а не будь-який коментар
  (на корпусі 03.09 після «fixed» 87 разів писали «апрув, дякую» і лише 2 —
  «Можешь пофиксить»);
* що попередження нічого не блокує і нічого не пише в ClickUp.

Мережа не смикається: `clickup_client.fetch_by_ids` підмінено.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

# Ізоляція — ДО першого імпорту: дошка лягає в корінь стану.
os.environ["QA_LAB_STATE_DIR"] = tempfile.mkdtemp(prefix="cu-fixed-")
os.environ["CLICKUP_TOKEN"] = "pk_test_placeholder"

import clickup_client                                             # noqa: E402
import cu_fixed                                                   # noqa: E402
import cu_triage                                                  # noqa: E402

HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
LAB = "committed via qa_lab by "


def c(text, user="Tech Bot", date="1790000000000", mentions=()):
    return {"text": text, "user": user, "user_id": 1, "date": date,
            "mentions": list(mentions)}


def task(*comments, tid="t1"):
    return {"id": tid, "name": "[878] - Microsoft - br-pt", "branches": [],
            "domains": [], "comments": list(comments)}


def _reset_board():
    p = cu_fixed._path()
    if p.exists():
        p.unlink()


class _Fetch:
    """Підміна `fetch_by_ids`: віддає заготовлені таски і рахує виклики."""

    def __init__(self, by_id, personal=None):
        self.by_id, self.personal, self.calls = by_id, personal or {}, []

    def __enter__(self):
        self._saved = clickup_client.fetch_by_ids
        clickup_client.fetch_by_ids = self
        return self

    def __exit__(self, *a):
        clickup_client.fetch_by_ids = self._saved

    def __call__(self, items, with_comments=True, token=""):
        self.calls.append(([i["id"] for i in items], token))
        src = self.personal if token else self.by_id
        return [dict(src.get(i["id"]) or {"id": i["id"], "no_access": True})
                for i in items]


# ------------------------------------------------------------ що таке «fixed»

def test_a_fixed_through_the_lab_names_the_person_from_the_signature():
    """Автор у ClickUp — сервісний Tech Bot; людина видна лише з підпису."""
    assert cu_triage.fixed_by(c("fixed — " + LAB + "Liam"), task()) == "Liam"


def test_the_tagged_fixed_names_the_person_not_the_tag():
    """«@Tech Bot fixed … by Administrator» — останній коментар [878]:
    кнопка «✔ fixed → @автор» тегнула саму лабу. Відписав Administrator."""
    got = cu_triage.fixed_by(c("@Tech Bot fixed — " + LAB + "Administrator",
                              mentions=("Tech Bot", "Tech")), task())
    assert got == "Administrator", got


def test_a_plain_fixed_typed_in_clickup_names_its_author():
    assert cu_triage.fixed_by(c("fixed", user="Liam Frontend"), task()) == "Liam Frontend"
    assert cu_triage.fixed_by(c("@Hugo Support fixed", user="Liam Frontend",
                               mentions=("Hugo Support", "Hugo")), task()) == "Liam Frontend"
    assert cu_triage.fixed_by(c("готово", user="Nora Frontend"), task()) == "Nora Frontend"


def test_a_sentence_with_the_word_fixed_is_not_a_fixed():
    """Той самий поріг, що в автоматики: «fixed» закриває таску, а
    «fixed логотип, але форма не шле» — ні."""
    assert cu_triage.fixed_by(c("fixed логотип, но форма всё ещё не шлёт",
                               user="Liam Frontend"), task()) == ""


def test_a_bridge_report_is_signed_but_is_not_a_fixed():
    """Підпис лаби сам по собі ще не «fixed»: звіт ШІ-моста теж підписаний."""
    report = ("Лаба перевірила — у гілці цього дефекту немає · вітка x\n"
              "перевірки: contacts\n" + LAB + "AI bridge (TSM)")
    assert cu_triage.fixed_by(c(report), task()) == ""


def test_the_878_case_counts_four_and_names_the_last():
    """Рівно те, що було на скріні 23.09 (ClickUp віддає найновіший першим)."""
    t = task(c("@Tech Bot fixed — " + LAB + "Administrator", date="4",
               mentions=("Tech Bot", "Tech")),
             c("fixed — " + LAB + "Liam", date="3"),
             c("fixed — " + LAB + "Liam", date="2"),
             c("fixed — " + LAB + "Liam", date="1"))
    n = cu_triage.fixed_note(t)
    assert n["count"] == 4 and n["by"] == "Administrator" and n["date"] == "4", n
    assert n["asked_again"] is None, n
    assert [m["by"] for m in n["marks"]] == ["Administrator", "Liam", "Liam", "Liam"]


def test_a_support_request_after_the_fixed_is_asked_again():
    """Таска законно повернулась у роботу — довідка, а не тривога."""
    t = task(c("Можешь пофиксить, пожалуйста: форма не шлёт", user="Hugo Support"),
             c("fixed — " + LAB + "Liam"))
    n = cu_triage.fixed_note(t)
    assert n["asked_again"] and n["asked_again"]["user"] == "Hugo Support", n


def test_thanks_after_the_fixed_does_not_reopen_the_task():
    """Виміряно на корпусі 03.09: після «fixed» пишуть «апрув, дякую» (87) і
    конфіг деплою (69). Якби це «відкривало» таску, жовте не спалахнуло б
    майже ніколи — а саме ці таски і є ризиком дубля."""
    for said, who in (("апрув, дякую", "Kite MB"), ("все гуд, забрал", "Owen MB"),
                      ("took to deploy", "Hugo Support")):
        n = cu_triage.fixed_note(task(c(said, user=who), c("fixed — " + LAB + "Liam")))
        assert n["asked_again"] is None, (said, n)


def test_a_request_older_than_the_fixed_does_not_count():
    t = task(c("fixed — " + LAB + "Liam"),
             c("Можешь пофиксить, пожалуйста: форма не шлёт", user="Hugo Support"))
    assert cu_triage.fixed_note(t)["asked_again"] is None


def test_no_fixed_means_no_note():
    assert cu_triage.fixed_note({"id": "t1", "comments": None}) is None
    assert cu_triage.fixed_note(task()) is None
    assert cu_triage.fixed_note(task(c("took to deploy", user="Hugo Support"))) is None


# ------------------------------------------------------------ дошка і перевірка

def test_check_reads_clickup_once_and_answers_from_the_board_inside_the_window():
    """Ліміт ClickUp — 100/хв на ОДИН токен лаби для всіх, тож таску,
    перевірену хвилину тому, другий раз не читаємо; нульове вікно читає
    наново."""
    _reset_board()
    hot = task(c("fixed — " + LAB + "Liam"))
    with _Fetch({"t1": hot}) as f:
        r1 = cu_fixed.check(["t1"])
        r2 = cu_fixed.check(["t1"])
        r3 = cu_fixed.check(["t1"], fresh_s=0)
    assert len(f.calls) == 2, f.calls
    assert r1["notes"]["t1"]["by"] == "Liam" and r1["checked"] == 1
    assert r2["notes"]["t1"]["by"] == "Liam" and r2["cached"] == 1 and r2["checked"] == 0
    assert r3["checked"] == 1 and r3["ids"] == ["t1"]


def test_a_task_shared_personally_is_read_with_the_persons_token():
    """Та сама добірка, що в `/api/clickup/by_links`: застосунковий акаунт
    розшареної людині таски не бачить."""
    _reset_board()
    with _Fetch({}, personal={"t1": task(c("fixed", user="Liam Frontend"))}) as f:
        r = cu_fixed.check(["t1"], token="pk_personal")
    assert [tok for _, tok in f.calls] == ["", "pk_personal"], f.calls
    assert r["notes"]["t1"]["by"] == "Liam Frontend" and not r["failed"]


def test_a_failed_read_keeps_what_the_board_knew():
    """429 чи мережа — не привід забути вже відомий «fixed»."""
    _reset_board()
    cu_fixed.remember({"t1": cu_fixed.fixed_note(task(c("fixed — " + LAB + "Liam")))})
    with _Fetch({"t1": {"id": "t1", "enrich_failed": True}}):
        r = cu_fixed.check(["t1"], fresh_s=0)
    assert r["failed"] == ["t1"] and r["notes"]["t1"]["by"] == "Liam", r


def test_no_fixed_is_remembered_too():
    """Видалений у ClickUp дубль не має висіти на дошці вічно."""
    _reset_board()
    with _Fetch({"t1": task(c("fixed — " + LAB + "Liam"))}):
        cu_fixed.check(["t1"], fresh_s=0)
    assert "t1" in cu_fixed.api_board()
    with _Fetch({"t1": task(c("took to deploy", user="Hugo Support"))}):
        r = cu_fixed.check(["t1"], fresh_s=0)
    assert "t1" not in r["notes"] and "t1" not in cu_fixed.api_board()


def test_the_board_and_one_call_are_capped():
    _reset_board()
    saved = cu_fixed.CAP, cu_fixed.CHECK_MAX
    cu_fixed.CAP, cu_fixed.CHECK_MAX = 3, 2
    try:
        for i in range(5):
            cu_fixed.remember({f"t{i}": None})
        assert sorted(cu_fixed.board()) == ["t2", "t3", "t4"], sorted(cu_fixed.board())
        with _Fetch({}) as f:
            r = cu_fixed.check(["a", "b", "c", "d"], fresh_s=0)
        assert f.calls[0][0] == ["a", "b"] and r["over"] == 2 and r["ids"] == ["a", "b"]
    finally:
        cu_fixed.CAP, cu_fixed.CHECK_MAX = saved


def test_my_own_fixed_goes_on_the_board_without_reading_clickup():
    """Свій «fixed» лаба щойно написала сама — читати його назад означало б
    два запити на таску зі спільних 100/хв (масова кнопка на 40 тасок — 80).
    Дошка дізнається про нього одразу, щоб колега не зробив дубль."""
    _reset_board()
    cu_fixed.remember({"t1": cu_fixed.fixed_note(task(
        c("Можешь пофиксить, пожалуйста: форма не шлёт", user="Hugo Support"),
        c("fixed — " + LAB + "Liam", date="1")))})
    with _Fetch({}) as f:
        assert cu_fixed.mark_mine(["t1", "t2", "t1", ""], "Yurii") == 2
    assert not f.calls, f.calls
    n1, n2 = cu_fixed.board()["t1"]["note"], cu_fixed.board()["t2"]["note"]
    assert n1["count"] == 2 and n1["by"] == "Yurii" and n1["asked_again"] is None, n1
    assert [m["by"] for m in n1["marks"]] == ["Yurii", "Liam"], n1["marks"]
    assert n2["count"] == 1 and n2["by"] == "Yurii", n2
    # і всередині вікна свіжості перевірка віддає саме це, без ClickUp
    with _Fetch({}) as f:
        assert cu_fixed.check(["t1"])["notes"]["t1"]["by"] == "Yurii"
    assert not f.calls


def test_learn_takes_only_tasks_whose_comments_were_read():
    """Коментарів не тягнули (None) або таска не дочиталась — це «не знаю»,
    а не «fixed немає»."""
    _reset_board()
    cu_fixed.learn([{"id": "a", "comments": None},
                    {"id": "b", "enrich_failed": True},
                    {"id": "c", "no_access": True, "comments": []},
                    task(c("fixed — " + LAB + "Liam"), tid="d")])
    assert sorted(cu_fixed.board()) == ["d"], sorted(cu_fixed.board())


def test_the_lab_writes_nothing_to_clickup_here():
    """Попередження лише ЧИТАЄ. Жодного запису в ClickUp, жодного
    `complete_task` — пише в таски лише «fixed» (кнопка й автокоміт) і звіти,
    див. `tests/test_clickup_writes.py`."""
    src = (ROOT / "cu_fixed.py").read_text(encoding="utf-8")
    for bad in ("complete_task", "requests.", "post_comment", "checklist_item"):
        assert bad not in src, bad


# ------------------------------------------------------------ підключення

def test_the_endpoints_are_mounted():
    """Підключений роутер лежить у плаському `app.routes` однією обгорткою
    (`original_router`) — розгортаємо, як і підмітальник сесій
    (`test_auth_session._all_routes`), що тримає ці маршрути під входом."""
    import app
    routes = []
    for r in app.app.routes:
        inner = getattr(r, "original_router", None)
        routes += list(inner.routes) if inner is not None else [r]
    paths = {(r.path, m) for r in routes for m in getattr(r, "methods", ()) or ()}
    assert ("/api/clickup/fixed", "GET") in paths
    assert ("/api/clickup/fixed/check", "POST") in paths
    assert ("/api/clickup/fixed/mine", "POST") in paths


def test_by_links_puts_a_fixed_note_on_each_read_task_for_free():
    """Коментарі у вкладці ClickUp уже читаються — нотатка для картки і запис
    на дошку не мають коштувати жодного додаткового запиту."""
    import app
    _reset_board()

    class _Req:
        class state:
            user = {}

    with _Fetch({"t1": task(c("fixed — " + LAB + "Liam"))}) as f:
        got = app.clickup_by_links(app.ClickUpLinksRequest(
            links=["https://app.clickup.com/t/t1"]), _Req())
    assert len(f.calls) == 1, f.calls
    assert got[0]["fixed"]["by"] == "Liam", got[0].get("fixed")
    assert cu_fixed.board()["t1"]["note"]["by"] == "Liam"


# ------------------------------------------------------------ UI

def _fn(name: str) -> str:
    m = re.search(r"(?:async )?function %s\(.*?\n\}\n" % re.escape(name), HTML, re.S)
    assert m, f"у UI більше немає {name}()"
    return m.group(0)


def test_the_warning_never_makes_the_work_wait():
    """«Не блокувати роботу»: у місцях, де людина бере таску, перевірку
    запускають без await і без confirm — прогін, Sync та імпорт ідуть одразу."""
    assert "await cuFixedWarn" not in HTML
    hooks = len(re.findall(r"\bcuFixedWarn\(", HTML)) - 1        # мінус визначення
    assert hooks >= 3, hooks                                      # імпорт, Sync, перевірки
    for name in ("cuFixedWarn", "cuFixedCheck", "renderFixedAlerts", "cuFixedSpan"):
        assert "confirm(" not in _fn(name), name


def test_every_manual_fixed_button_tells_the_board():
    """Одиночна, з тегом і масова — кожна кнопка «fixed» каже дошці про
    себе. Пропущена масова означала б, що колега, який бере ці таски, не
    дізнається про них, доки сам не перечитає ClickUp."""
    for name in ("cuComplete", "cuCompleteTagged"):
        assert "cuFixedMine(t.id)" in _fn(name), name
    bulk = HTML[HTML.index("$('#cuFixAll').onclick"):]
    bulk = bulk[:bulk.index("\n};\n")]
    assert "cuFixedMine(targets.filter(t=>t.checklist_done)" in bulk


def test_the_refresh_keeps_the_branch_selection():
    """`renderBranches()` малює галочки вибору заново — щохвилинне оновлення
    попереджень не має скидати людині вибір віток посеред роботи."""
    body = _fn("fxRepaint")
    assert "renderBranches(" not in body and "loadBranches(" not in body
    assert "data-cub" in body


def test_the_cards_drawn_before_the_board_arrived_get_the_warning_too():
    """На старті сторінки картки ClickUp малюються зі збереженого скану
    незалежно від дошки й часто РАНІШЕ за неї. Якщо після дошки перемалювати
    лише смугу, «fixed» колеги видно в смузі, а на картці — ні, і щохвилинне
    оновлення цього не лікує: дошка ж «не змінилась» (спіймано на стенді)."""
    body = _fn("loadBranches")
    assert body.index("/api/clickup/fixed") < body.index("fxRepaint()"), body


def test_the_clickup_cards_are_repainted_even_on_a_hidden_tab():
    """Перемикання вкладок картки ClickUp не перемальовує. Якби `fxRepaint`
    малював їх лише на відкритій вкладці, попередження, що прийшло, поки
    людина була в «Перевірках», на картці не з'явилось би (спіймано на стенді)."""
    body = _fn("fxRepaint")
    assert "renderCuTasks()" in body
    assert "classList.contains('on')" not in body


def test_the_warning_is_yellow_and_separate_from_problems():
    """Червона смуга — журнал проблем, спільний для всіх; «fixed уже є» —
    попередження про СВІЙ список. Змішати їх означало б «проблему» там, де
    нічого не зламано."""
    assert '<div id="fixedAlerts" hidden></div>' in HTML
    assert re.search(r"#fixedAlerts\{[^}]*var\(--warn\)", HTML)
    assert "/api/problems" not in _fn("renderFixedAlerts")


def test_every_new_ui_string_is_translated():
    d = (ROOT / "static" / "i18n-dict.js").read_text(encoding="utf-8")
    for s in ("⚠ fixed уже є", "↺ fixed був", "{0} · саппорт просить знову",
              "⚠ fixed уже є: {0} — {1}", "усі fixed у тасці ({0}): {1}",
              "CLICKUP_TOKEN не заданий — перевірити fixed нема чим",
              "таски з твого списку вже відписали в ClickUp — роботу це не блокує, "
              "лише попереджає, щоб не зробити її вдруге"):
        assert f'"{s}":' in d, s


def test_the_page_script_still_parses():
    """Один синтаксичний промах в інлайн-скрипті — і вся лаба не відповідає
    на жодну кнопку, а в HTML і логах цього не видно (див. `/deploys`, 28.08)."""
    node = shutil.which("node")
    if not node:
        print("    (node немає — перевірка синтаксису пропущена)")
        return
    js = [s for s in re.findall(r"<script>([\s\S]*?)</script>", HTML) if s.strip()]
    assert js, "у сторінці більше немає інлайн-скрипта"
    f = tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False)
    f.write("\n;\n".join(js))
    f.close()
    try:
        r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-800:]
    finally:
        os.unlink(f.name)


if __name__ == "__main__":
    run(dict(globals()))
