"""Вебхук ClickUp: підпис, дедуп і чому тут майже завжди 200.

Дві речі, які легко зламати назад і які коштують дорого:

* **фейл-клоуз.** Незаданий `CLICKUP_WEBHOOK_SECRET` мусить означати «двері
  зачинені», а не «пускаємо всіх». Шлях відкритий для машини і не має ані
  куки, ані нашого токена — крім підпису, тут не перевіряє ніщо;
* **невдала доставка глушить підписку.** ClickUp після серії невдач переводить
  вебхук у `failing` і перестає слати, а тиша виглядає точно так само, як
  «нових тасок немає». Тому «черга повна» і «прийом вимкнено» — це 200 з
  поясненням, а не 429 і не 503.

Стан ізольовано на рівні МОДУЛЯ: інакше кільце дедупу лягло б у робоче дерево.
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="cu-hook-")
os.environ["QA_LAB_STATE_DIR"] = _TMP
os.environ["MOCK_MODE"] = "1"
os.environ["CLICKUP_WEBHOOK_SECRET"] = "s3cret-for-tests-only"

from _harness import run                                        # noqa: E402

from fastapi import HTTPException                               # noqa: E402

import auth                                                     # noqa: E402
import cu_hook                                                  # noqa: E402
import cu_queue                                                 # noqa: E402

cu_queue.start = lambda: None                                   # без потоків


class _Req:
    """Мінімальний запит: ендпоінт бере лише сире тіло і заголовок підпису."""

    def __init__(self, raw: bytes, sig: str):
        self._raw, self.headers = raw, {"x-signature": sig}

    async def body(self):
        return self._raw


def _sign(raw: bytes, secret: str = "") -> str:
    key = secret or os.environ["CLICKUP_WEBHOOK_SECRET"]
    return hmac.new(key.encode(), raw, hashlib.sha256).hexdigest()


def _post(body: dict, sig=None, secret=""):
    raw = json.dumps(body).encode()
    return asyncio.run(cu_hook.clickup_hook(
        _Req(raw, sig if sig is not None else _sign(raw, secret))))


def _reset(intake=True):
    cu_queue._q.queue.clear()
    st = dict(cu_queue._default_state)
    st.update(tasks={}, counters={"accepted": 0, "skipped": 0, "events": 0},
              intake=intake, run=False)
    cu_queue.save(st)
    cu_hook._seen_path().unlink(missing_ok=True)


def _event(task_id="t1", hid="h1", event="taskUpdated"):
    return {"webhook_id": "w1", "event": event, "task_id": task_id,
            "history_items": [{"id": hid, "field": "custom_field"}]}


# ---------------------------------------------------------------- підпис

def test_a_wrong_signature_is_refused():
    _reset()
    try:
        _post(_event(), sig="00" * 32)
    except HTTPException as e:
        assert e.status_code == 401, e.status_code
    else:
        assert False, "чужий підпис пройшов"


def test_a_signature_from_another_secret_is_refused():
    _reset()
    try:
        _post(_event(), secret="not-our-secret")
    except HTTPException as e:
        assert e.status_code == 401, e.status_code
    else:
        assert False, "підпис чужим ключем пройшов"


def test_without_a_secret_the_door_is_shut():
    """Фейл-клоуз: незаданий ключ — це «зачинено», а не «вимкнена перевірка»."""
    _reset()
    was = os.environ.pop("CLICKUP_WEBHOOK_SECRET")
    try:
        assert not auth.verify_hook(b"{}", "abc")
    finally:
        os.environ["CLICKUP_WEBHOOK_SECRET"] = was


def test_only_one_path_is_a_door():
    assert auth.is_hook_path("/api/hook/clickup")
    assert not auth.is_hook_path("/api/hook/clickup/extra")
    assert not auth.is_hook_path("/api/hook/anything")
    assert "/api/hook/clickup" not in auth.PUBLIC_PATHS, \
        "двері для машини — це інший користувач, а не відсутність авторизації"


# ---------------------------------------------------------------- прийом

def test_a_valid_event_reaches_the_queue():
    _reset()
    got = _post(_event())
    assert got["ok"] and got["status"] == "queued", got
    assert cu_queue._q.qsize() == 1
    assert cu_queue.load()["counters"]["events"] == 1


def test_the_same_delivery_twice_queues_once():
    """ClickUp повторює доставку; ключ — id запису історії."""
    _reset()
    _post(_event())
    got = _post(_event())
    assert got["status"] == "duplicate", got
    assert cu_queue._q.qsize() == 1


def test_a_different_event_for_the_same_task_is_not_a_duplicate():
    _reset()
    _post(_event(hid="h1"))
    cu_queue._q.queue.clear()
    cu_queue._update(lambda st: st["tasks"].pop("t1", None))
    got = _post(_event(hid="h2"))
    assert got["status"] == "queued", got


def test_an_event_without_a_task_id_is_answered_not_thrown():
    _reset()
    got = _post({"webhook_id": "w1", "event": "taskUpdated"})
    assert got["ok"] is False and "task_id" in got["reason"], got


def test_a_full_queue_still_answers_200():
    """429 тут коштував би підписки: ClickUp рахує це невдалою доставкою."""
    _reset()
    os.environ["CU_QUEUE_MAX"] = "0"
    try:
        got = _post(_event(hid="hz"))
    finally:
        os.environ.pop("CU_QUEUE_MAX")
    assert got["ok"] and got["status"] == "queue_full", got


def test_intake_off_is_reported_not_refused():
    _reset(intake=False)
    got = _post(_event(hid="hoff"))
    assert got["ok"] and got["status"] == "off", got
    assert cu_queue._q.qsize() == 0


# ---------------------------------------------------------------- дедуп

def test_the_key_falls_back_when_there_is_no_history():
    """Формат у них не один; без `history_items` ключ збирається з трійки."""
    k = cu_hook.event_key({"webhook_id": "w", "task_id": "t", "event": "e"})
    assert k.startswith("e:w:t:e:"), k
    assert cu_hook.event_key(_event()) == "h:h1"


def test_the_ring_does_not_grow_without_end():
    _reset()
    cu_hook.SEEN_CAP, was = 3, cu_hook.SEEN_CAP
    try:
        for i in range(5):
            cu_hook._remember(f"k{i}")
        assert cu_hook._load_seen() == ["k2", "k3", "k4"], cu_hook._load_seen()
    finally:
        cu_hook.SEEN_CAP = was


def test_a_task_from_the_hook_still_gets_a_link():
    """Подія несе тільки id, а картка без лінки марна: людина бачить
    `868kzn90p` і не може відкрити таску (скарга 07.09)."""
    cu_queue.set_switches(intake=True)
    try:
        _post({"event": "taskUpdated", "task_id": "868kzn90p",
               "history_items": [{"id": "h-link"}]})
        card = cu_queue.load()["tasks"]["868kzn90p"]
        assert card["url"] == "https://app.clickup.com/t/868kzn90p", card
    finally:
        cu_queue.set_switches(intake=False)


if __name__ == "__main__":
    run(dict(globals()))
