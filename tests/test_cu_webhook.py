"""Реєстрація вебхука ClickUp самою лабою.

Тут закріплено те, що коштує дорого і мовчки:

* **два джерела ключа не можуть існувати одночасно.** Заданий
  `CLICKUP_WEBHOOK_SECRET` = ручний режим, і тоді ми в ClickUp не ходимо
  взагалі. Інакше одного дня в змінній лежав би ключ від видаленого вебхука,
  а лаба відповідала б 401 на кожну подію без жодної видимої причини;
* **чужі вебхуки недоторканні.** У воркспейсі живуть інші інтеграції; фільтр
  на видалення — точний збіг адреси, а не «все, що не наше»;
* **втрачений секрет лікується лише перевипуском.** ClickUp не віддає його
  вдруге, тож «вебхук є, ключа немає» (стерли том стану) мусить закінчуватись
  видаленням і створенням наново, а не тишею;
* **недоступний ClickUp не стирає вже виданий ключ** — інакше кожен збій
  мережі на старті ламав би робочий вебхук.

Мережі тут немає: підмінений `cu_hook._api` і заданий `CLICKUP_TEAM_ID`
(інакше `clickup_client._team_id` пішов би в ClickUp по-справжньому).
Ізоляція стану — на рівні МОДУЛЯ, до першого тесту.
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="cu-webhook-")
os.environ["QA_LAB_STATE_DIR"] = _TMP
os.environ["MOCK_MODE"] = "1"
os.environ["CLICKUP_TEAM_ID"] = "900111"
os.environ.pop("CLICKUP_WEBHOOK_SECRET", None)

from _harness import run                                        # noqa: E402

import auth                                                     # noqa: E402
import cu_hook                                                  # noqa: E402
import cu_queue                                                 # noqa: E402

cu_queue.start = lambda: None                                   # без потоків

ENDPOINT = "https://lab.example.com/api/hook/clickup"

_calls: list = []
_hooks: list = []
_fail: dict = {}
# Лічильник наскрізний, а не `len(_hooks)`: після видалення список коротшає, і
# наступний вебхук дістав би СТАРИЙ ключ — у ClickUp так не буває, а тест на
# перевипуск саме на різниці ключів і тримається.
_seq = [0]


def _fake_api(method: str, path: str, payload=None) -> dict:
    _calls.append((method, path, payload))
    if _fail.get(method):
        raise RuntimeError(_fail[method])
    if method == "GET":
        return {"webhooks": list(_hooks)}
    if method == "POST":
        _seq[0] += 1
        hook = {"id": f"wh-{_seq[0]}", "endpoint": payload["endpoint"],
                "secret": f"sec-{_seq[0]}", "health": {"status": "active"}}
        _hooks.append({k: v for k, v in hook.items() if k != "secret"})
        return {"webhook": hook}
    if method == "DELETE":
        wid = path.rsplit("/", 1)[-1]
        _hooks[:] = [h for h in _hooks if h["id"] != wid]
        return {}
    raise AssertionError(method)


cu_hook._api = _fake_api


def _fresh(domain: str = "lab.example.com", **env):
    """Чистий старт: порожній ClickUp, порожня реєстрація, задане оточення."""
    _calls.clear()
    _hooks.clear()
    _fail.clear()
    _seq[0] = 0
    os.environ.pop("CLICKUP_WEBHOOK_SECRET", None)
    os.environ.pop("CU_WEBHOOK_AUTO", None)
    os.environ["CLICKUP_TOKEN"] = "pk_test"
    os.environ["CU_QUEUE_ENABLED"] = "1"
    if domain:
        os.environ["DOMAIN_NAME"] = domain
    else:
        os.environ.pop("DOMAIN_NAME", None)
    for k, v in env.items():
        os.environ[k] = v
    cu_hook._save_reg({})


# ------------------------------------------------------------------ режими

def test_the_endpoint_is_built_from_the_domain():
    _fresh()
    assert cu_hook.public_endpoint() == ENDPOINT


def test_a_local_name_is_not_a_public_endpoint():
    """На машині розробника автореєстрація мусить мовчати сама, без прапорця:
    ClickUp ходить лише на публічний https."""
    for bad in ("", "localhost:8030", "qa_lab", "lab.local"):
        _fresh(domain=bad)
        assert cu_hook.public_endpoint() == "", bad
        assert cu_hook.auto_state()["mode"] == "off"


def test_nothing_is_registered_without_a_domain():
    _fresh(domain="")
    got = cu_hook.ensure()
    assert got["mode"] == "off" and not _calls, got


def test_the_env_secret_means_hands_off():
    _fresh()
    os.environ["CLICKUP_WEBHOOK_SECRET"] = "manual-key"
    got = cu_hook.ensure()
    assert got["mode"] == "env" and not _calls, got
    assert auth.hook_secret() == "manual-key"
    os.environ.pop("CLICKUP_WEBHOOK_SECRET")


def test_the_switch_turns_the_whole_thing_off():
    _fresh(CU_WEBHOOK_AUTO="0")
    assert cu_hook.ensure()["mode"] == "off"
    _fresh(CU_QUEUE_ENABLED="0")
    assert cu_hook.ensure()["mode"] == "off"
    assert not _calls


# ------------------------------------------------------------- реєстрація

def test_a_clean_workspace_gets_a_webhook_and_a_key():
    _fresh()
    got = cu_hook.ensure()
    assert got["status"] == "created" and got["changed"], got
    assert [c[0] for c in _calls] == ["GET", "POST"], _calls
    assert _calls[-1][2] == {"endpoint": ENDPOINT, "events": cu_hook.EVENTS}
    assert cu_hook.secret() == "sec-1"
    assert auth.hook_secret() == "sec-1", "ключ мусить дійти до перевірки підпису"


def test_a_second_start_does_not_create_a_second_webhook():
    """Найдорожча помилка тут — вебхук на кожен деплой: події почали б
    приходити пачками, а старий ключ мовчки перестав би підходити."""
    _fresh()
    cu_hook.ensure()
    _calls.clear()
    got = cu_hook.ensure()
    assert got["status"] == "ok" and not got["changed"], got
    assert [c[0] for c in _calls] == ["GET"], _calls
    assert len(_hooks) == 1


def test_a_lost_secret_is_reissued_because_clickup_never_repeats_it():
    _fresh()
    cu_hook.ensure()
    cu_hook._save_reg({})                       # том стану стерли
    _calls.clear()
    got = cu_hook.ensure()
    assert got["status"] == "recreated" and got["replaced"] == 1, got
    assert [c[0] for c in _calls] == ["GET", "DELETE", "POST"], _calls
    assert len(_hooks) == 1 and cu_hook.secret() == "sec-2"


def test_foreign_webhooks_are_never_touched():
    _fresh()
    _hooks.append({"id": "чужий", "endpoint": "https://tsm.example/hook",
                   "health": {"status": "active"}})
    cu_hook.ensure()
    assert not [c for c in _calls if c[0] == "DELETE"], _calls
    assert any(h["id"] == "чужий" for h in _hooks)


def test_force_reissues_and_leaves_exactly_one():
    _fresh()
    cu_hook.ensure()
    _calls.clear()
    got = cu_hook.ensure(force=True)
    assert got["status"] == "recreated" and got["changed"], got
    assert len([h for h in _hooks if h["endpoint"] == ENDPOINT]) == 1
    assert cu_hook.secret() == "sec-2"


# --------------------------------------------------------------- відмови

def test_clickup_being_down_keeps_the_key_and_says_why():
    _fresh()
    cu_hook.ensure()
    _fail["GET"] = "ClickUp 503: down"
    got = cu_hook.ensure()
    assert got.get("error") and not got["changed"], got
    assert cu_hook.secret() == "sec-1", "виданий ключ не можна губити через збій"
    assert "503" in cu_hook.status()["last_error"]


def test_a_failed_create_does_not_pretend_to_have_a_key():
    _fresh()
    _fail["POST"] = "ClickUp 401: OAUTH_027"
    got = cu_hook.ensure()
    assert got.get("error") and not cu_hook.secret(), got
    assert auth.hook_secret() == "", "без ключа двері мусять лишитись зачиненими"


def test_failing_health_is_shown_but_not_fixed_behind_our_back():
    """Перевипуск міняє секрет, а `failing` частіше означає «лаба лежала під
    час деплою». Тому автоматика показує, а вирішує людина кнопкою."""
    _fresh()
    cu_hook.ensure()
    _hooks[0]["health"] = {"status": "failing", "fail_count": 7}
    _calls.clear()
    got = cu_hook.ensure()
    assert not got["changed"], got
    assert cu_hook.status()["health"]["status"] == "failing"
    assert not [c for c in _calls if c[0] in ("POST", "DELETE")], _calls


def test_status_shows_the_key_exists_but_never_the_key():
    _fresh()
    cu_hook.ensure()
    st = cu_hook.status()
    assert st["has_secret"] and st["secret_from"] == "реєстрація лаби"
    assert "sec-1" not in json.dumps(st, ensure_ascii=False), st


# --------------------------------------------------- наскрізь: підпис події

def test_an_event_signed_with_the_registered_key_gets_in():
    """Сенс усієї конструкції: ключ, який видав ClickUp, мусить приймати
    подію без жодної CI-змінної."""
    _fresh()
    cu_hook.ensure()
    raw = json.dumps({"event": "taskUpdated", "task_id": "abc123",
                      "history_items": [{"id": "h1"}]}).encode()
    sig = hmac.new(cu_hook.secret().encode(), raw, hashlib.sha256).hexdigest()

    class _Req:
        def __init__(self, raw, sig):
            self._raw, self.headers = raw, {"x-signature": sig}

        async def body(self):
            return self._raw

    got = asyncio.run(cu_hook.clickup_hook(_Req(raw, sig)))
    assert got["ok"] and got["task_id"] == "abc123", got
    # прийом вимкнено за замовчуванням — подія прийнята, але в чергу не пішла
    assert got.get("status") == "off", got


def test_the_same_event_with_a_stale_key_is_refused():
    _fresh()
    cu_hook.ensure()
    raw = b'{"task_id":"abc123"}'
    old = hmac.new(b"sec-0", raw, hashlib.sha256).hexdigest()

    class _Req:
        def __init__(self, raw, sig):
            self._raw, self.headers = raw, {"x-signature": sig}

        async def body(self):
            return self._raw

    try:
        asyncio.run(cu_hook.clickup_hook(_Req(raw, old)))
        raise AssertionError("чужий підпис мусив дати 401")
    except Exception as e:
        assert getattr(e, "status_code", None) == 401, e


run(globals())
