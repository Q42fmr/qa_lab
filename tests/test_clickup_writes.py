"""Що лаба пише в ClickUp: два варіанти, і обидва мусять жити.

23.09.2026 правило «лаба нічого не закриває — тільки коментар» я застосував
до ВСЬОГО, і вкладка ClickUp — щоденне робоче місце QA — лишилась без
ручного фіксу: кнопка перестала ставити чекліст (відписані таски не зникали
зі списку, їх відписували вдруге), а на тасках, де лаба вже відповіла,
зникли «✔ fixed», масова кнопка й галочки вибору. Деплой відкочено в ту ж
годину.

29.09.2026 межу посунуто рішенням юзера: «fixed» автокоміту без галки люди
відписували вдруге (з 28.09 17:15 — 27 з 29 тасок), бо вкладка ClickUp
показує таску, доки чекліст не стоїть. Межа тепер така:

* **«fixed» після QA** — і ручний (людина тисне кнопку), і автоматичний
  (автокоміт «Авто-QA»): чекліст whites + коментар, рівно як
  «✔ чекліст + fixed»; ручні кнопки — як у вкладці ClickUp: «✔ чекліст +
  fixed», «✔ fixed → @автор», масова кнопка, галочки;
* **звіт про зміну доменів і ШІ-міст** — ЛИШЕ коментар: таску там уже
  відписано раніше або це відповідь на запит TSM, а не пройдений QA;
* **«Тип вайта» і статус** — ніколи і ніде.

Гарда тримає всі три: хто ставить чекліст, а хто ні (поведінка), ручні
кнопки на місці і не ховаються (розмітка), полів і статусу таски лаба не
чіпає ніде (код). Мережа не смикається — `requests` у клієнті підмінено.
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

os.environ["QA_LAB_STATE_DIR"] = tempfile.mkdtemp(prefix="cu-writes-")
os.environ["CLICKUP_TOKEN"] = "pk_test_placeholder"

import clickup_client                                             # noqa: E402

METHODS = ("get", "post", "put", "patch", "delete", "request")
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


class _Resp:
    status_code = 200

    def __init__(self, payload=None):
        self.payload = payload or {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class _Net:
    """Підміняє `requests` у клієнті й записує КОЖЕН вихід назовні. GET
    таски віддає чекліст whites з одним непроставленим пунктом."""

    TASK = {"id": "t1", "checklists": [
        {"id": "cl1", "name": "Whites check",
         "items": [{"id": "it1", "resolved": False}]}]}

    def __enter__(self):
        self.calls = []
        req = clickup_client.requests
        self._saved = {m: getattr(req, m) for m in METHODS}
        for m in METHODS:
            setattr(req, m, self._rec(m))
        return self

    def _rec(self, method):
        def call(*a, **kw):
            url = a[1] if method == "request" else a[0]
            self.calls.append((method, url))
            return _Resp(self.TASK if method == "get" else {})
        return call

    def __exit__(self, *exc):
        for m, f in self._saved.items():
            setattr(clickup_client.requests, m, f)


# ------------------------------------------------------------ поведінка

def test_the_manual_button_ticks_the_checklist_and_comments():
    """Те, що робить «✔ чекліст + fixed»: чекліст whites + коментар."""
    with _Net() as net:
        got = clickup_client.complete_task("t1", "fixed")
    base = clickup_client.BASE
    assert ("put", f"{base}/checklist/cl1/checklist_item/it1") in net.calls, net.calls
    assert net.calls[-1] == ("post", f"{base}/task/t1/comment"), net.calls
    assert got["items_resolved"] == 1 and got["commented"], got


def test_a_comment_only_write_is_exactly_one_post():
    """Звіт про домени і ШІ-міст (`checklist=False`): рівно один POST
    коментаря — і нічого більше."""
    with _Net() as net:
        clickup_client.complete_task("t1", "fixed", checklist=False)
    assert net.calls == [("post", f"{clickup_client.BASE}/task/t1/comment")], net.calls


def test_the_auto_qa_fixed_ticks_the_checklist_like_the_button():
    """29.09.2026: відповідь на пройдений QA за замовчуванням ставить
    чекліст, і `apply()` для автокоміту (`machine`) його більше не вимикає.
    Поведінку — «fixed» автокоміту з галкою — тримає `tests/test_cu_queue.py`."""
    src = (ROOT / "cu_queue.py").read_text(encoding="utf-8")
    assert "def answer_if_passed(task_id: str, checklist: bool = True)" in src
    assert "answer_if_passed(task_id, checklist=checklist)" in src
    assert "checklist=checklist and not machine" not in src


def test_the_domain_report_is_only_a_comment():
    """Звіт після зміни доменів (25.09.2026) — автоматика: чекліст не ставить
    навіть тоді, коли коміт натиснула людина (таска вже пофікшена раніше)."""
    src = (ROOT / "cu_queue.py").read_text(encoding="utf-8")
    body = src[src.index("def report_domains("):]
    body = body[:body.index("\ndef ")]
    call = body[body.index("clickup_client.complete_task("):]
    call = call[:call.index(")\n")]
    assert "checklist=False" in call, call
    with _Net() as net:
        clickup_client.complete_task("t1", "Смена доменов: …", checklist=False,
                                     tag_user_id=42, tag_username="Victor Support")
    assert net.calls == [("post", f"{clickup_client.BASE}/task/t1/comment")], net.calls


def test_the_ai_bridge_never_ticks_the_checklist():
    src = (ROOT / "ai_bridge.py").read_text(encoding="utf-8")
    call = src[src.index("clickup_client.complete_task("):]
    call = call[:call.index(")\n")]
    assert "checklist=False" in call, call


# ------------------------------------------------------------ код

def test_the_lab_touches_no_field_and_no_status_of_a_task():
    """«Тип вайта» (white fixed) і статус — лише люди в самому ClickUp.
    Єдиний PUT клієнта — пункт чекліста («fixed» кнопки й автокоміту),
    єдиний POST — коментар."""
    src = (ROOT / "clickup_client.py").read_text(encoding="utf-8")
    assert "/field/" not in src and not hasattr(clickup_client, "set_wtype_fixed")
    # URL — f-рядок у подвійних лапках, всередині бувають одинарні ({cl['id']})
    puts = re.findall(r'requests\.put\(\s*f?"([^"]+)"', src)
    assert puts and all("/checklist_item/" in p for p in puts), puts
    posts = re.findall(r'requests\.post\(\s*f?"([^"]+)"', src)
    assert posts and all(p.endswith("/comment") for p in posts), posts
    assert "requests.patch(" not in src and "requests.delete(" not in src


# ------------------------------------------------------------ розмітка

def test_the_clickup_tab_keeps_every_manual_control():
    """Рівно те, що 23.09 «пропало» у людей: кнопка без тегу, кнопка з тегом,
    масова кнопка зверху і галочки вибору тасок."""
    for piece in ('data-done="${ix}"', "✔ чекліст + fixed</button>",
                  'data-doneat="${ix}"', 'id="cuFixAll"', 'id="cuImportSel"',
                  'data-selcb="${ix}"'):
        assert piece in HTML, piece


def test_the_manual_controls_hide_behind_nothing_but_the_checklist():
    """Придатність до «fixed» — лише чекліст, як у Олександра. Ховати кнопки
    за коментарем лаби (23.09) означало забрати в людини її інструмент."""
    assert ("const cuFixEligible=t=>t.checklist_loaded!==false"
            "&&!(t.checklist_found&&t.checklist_done);") in HTML
    assert "cuAnswered" not in HTML


def test_the_auto_qa_card_offers_the_same_manual_buttons_and_no_closing():
    """Картка «Авто-QA» — ті самі ручні дії, що й вкладка ClickUp; «Закрити
    таску» (white fixed) прибрано: лаба нічого не закриває."""
    assert 'data-qdone="${esc(t.task_id)}"' in HTML and 'data-qfix="${esc(t.task_id)}"' in HTML
    for gone in ("data-qclose", "data-qans", "/api/queue/close/", "/api/queue/answer/"):
        assert gone not in HTML, gone


def test_the_manual_endpoint_still_takes_the_checklist():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    model = re.search(r"class ClickUpCompleteRequest\(BaseModel\):(.*?)\n\n", src, re.S)
    assert model and "checklist: bool = True" in model.group(1), model and model.group(1)


if __name__ == "__main__":
    run(dict(globals()))
