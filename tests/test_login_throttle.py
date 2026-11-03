"""Ліміт спроб входу.

Навіщо. До 26.08 перед лабою стояв BasicAuth Traefik, і форма входу була
другим рубежем. Тепер BasicAuth знято (два гейти на одному origin вибивають
Basic-пароль з кеша браузера на кожному 401 — див. `test_ci_lockstep`), тож
ця форма — весь гейт між доменом і чужими руками.

Тут закріплено три рішення, кожне з яких легко зламати назад:

1. ліміт стоїть ДО перевірки пароля. Після неї він не обмежував би нічого,
   крім тексту відповіді;
2. ключ — логін, а не IP: за Traefik і Cloudflare усі клієнти приходять з
   адреси проксі, і ліміт по IP замкнув би вхід одразу всій команді;
3. успішний вхід стирає лічильник.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import auth                                                       # noqa: E402
import users                                                      # noqa: E402


def _fresh(login: str):
    """Чистий лічильник для цього логіна: тести діляться процесом."""
    auth.clear_login_failures(login)


# ------------------------------------------------------------ сам лічильник

def test_the_first_attempts_pass_and_the_last_one_closes_the_door():
    _fresh("u-limit")
    for i in range(auth.MAX_FAILS):
        assert auth.login_retry_after("u-limit") == 0, f"замкнуло на {i}-й спробі"
        auth.note_login_failure("u-limit")
    assert auth.login_retry_after("u-limit") > 0, "ліміт не спрацював"


def test_the_window_slides_away():
    """Спроби старші за вікно не рахуються — інакше ліміт був би вічним."""
    _fresh("u-window")
    now = 1_000_000.0
    for _ in range(auth.MAX_FAILS):
        auth.note_login_failure("u-window", now=now)
    assert auth.login_retry_after("u-window", now=now) > 0
    later = now + auth.FAIL_WINDOW_S + 1
    assert auth.login_retry_after("u-window", now=later) == 0


def test_the_wait_never_exceeds_the_window():
    """Скільки просимо чекати — це те, що людина побачить у повідомленні."""
    _fresh("u-wait")
    now = 1_000_000.0
    for _ in range(auth.MAX_FAILS):
        auth.note_login_failure("u-wait", now=now)
    wait = auth.login_retry_after("u-wait", now=now)
    assert 0 < wait <= auth.FAIL_WINDOW_S + 1, wait


def test_success_clears_the_counter():
    _fresh("u-clear")
    for _ in range(auth.MAX_FAILS):
        auth.note_login_failure("u-clear")
    assert auth.login_retry_after("u-clear") > 0
    auth.clear_login_failures("u-clear")
    assert auth.login_retry_after("u-clear") == 0


def test_case_does_not_multiply_the_allowance():
    """Логін звіряється без регістру (`users.norm_login`), тож і лічильник
    мусить бути спільний: інакше «Admin», «ADMIN», «admin» дали б утричі
    більше спроб на ту саму учетку."""
    _fresh("u-case")
    for _ in range(auth.MAX_FAILS):
        auth.note_login_failure("U-CASE")
    assert auth.login_retry_after("u-case") > 0
    assert auth.login_retry_after(" U-Case ") > 0


def test_a_neighbour_is_not_locked_out():
    """Ключ — саме логін. Якби лічильник був глобальним, підбір чужого імені
    зачиняв би вхід усім."""
    _fresh("u-victim")
    _fresh("u-neighbour")
    for _ in range(auth.MAX_FAILS):
        auth.note_login_failure("u-victim")
    assert auth.login_retry_after("u-victim") > 0
    assert auth.login_retry_after("u-neighbour") == 0


def test_the_keyring_stays_bounded():
    """Під підбором логіни бувають випадкові — словник не має рости вічно."""
    _fresh("u-cap")
    now = 1_000_000.0
    for i in range(auth.MAX_FAIL_KEYS + 200):
        auth.note_login_failure(f"junk-{i}", now=now)
    assert len(auth._fails) <= auth.MAX_FAIL_KEYS, len(auth._fails)


# ------------------------------------------------------------- через ендпоінт

def _post(application, path: str, payload: dict):
    """POST через справжній ASGI-виклик.

    Свій, а не `starlette.testclient`: той тягне httpx, а правило репозиторію —
    жодних нових залежностей заради тестів (той самий підхід, що в
    `test_auth_session._asgi_call`).
    """
    import asyncio

    body = json.dumps(payload).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "scheme": "http",
        "headers": [(b"host", b"testserver"),
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode())],
        "client": ("127.0.0.1", 12345), "server": ("testserver", 80),
    }
    out = {"status": None, "body": b""}

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            out["status"] = message["status"]
        elif message["type"] == "http.response.body":
            out["body"] += message.get("body", b"") or b""

    asyncio.run(application(scope, receive, send))
    return out["status"], out["body"].decode("utf-8", "replace")


def _app_with_user(login: str, password: str):
    os.environ["MOCK_MODE"] = "1"
    os.environ["QA_LAB_SECRET_KEY"] = "test-secret-key"
    auth.reset_secret_for_tests()
    st = users.FileUserStore(Path(tempfile.mkdtemp(prefix="throttle-")) / "users.json")
    users.reset_store_for_tests(st)
    auth.invalidate()
    st.create({"login": login, "name": "T",
               "password_hash": users.hash_password(password),
               "is_admin": True, "is_active": True})
    import app                                                    # noqa: E402
    return app.app


def test_endpoint_lets_the_right_password_through():
    application = _app_with_user("tester", "s3cret-pw")
    _fresh("tester")
    status, _ = _post(application, "/api/auth/login",
                      {"login": "tester", "password": "s3cret-pw"})
    assert status == 200, status


def test_endpoint_answers_429_after_the_limit():
    """І — свідомо — правильний пароль у вікні очікування теж не проходить.

    Інакше ліміт нічого не обмежував би: підбір ішов би повним ходом, просто
    з іншим кодом наприкінці. Ціна задокументована в `auth.MAX_FAILS`: чекати
    доводиться хвилину, не годину.
    """
    application = _app_with_user("tester2", "s3cret-pw")
    _fresh("tester2")
    for _ in range(auth.MAX_FAILS):
        status, _ = _post(application, "/api/auth/login",
                          {"login": "tester2", "password": "nope"})
        assert status == 401, status
    status, body = _post(application, "/api/auth/login",
                         {"login": "tester2", "password": "nope"})
    assert status == 429, status
    assert "спроб" in body, body
    status, _ = _post(application, "/api/auth/login",
                      {"login": "tester2", "password": "s3cret-pw"})
    assert status == 429, "ліміт стоїть після перевірки пароля — він нічого не обмежує"


def test_endpoint_forgets_failures_after_a_success():
    application = _app_with_user("tester3", "s3cret-pw")
    _fresh("tester3")
    for _ in range(auth.MAX_FAILS - 1):
        _post(application, "/api/auth/login", {"login": "tester3", "password": "nope"})
    status, _ = _post(application, "/api/auth/login",
                      {"login": "tester3", "password": "s3cret-pw"})
    assert status == 200, status
    assert auth.login_retry_after("tester3") == 0
    for _ in range(auth.MAX_FAILS - 1):
        status, _ = _post(application, "/api/auth/login",
                          {"login": "tester3", "password": "nope"})
        assert status == 401, "лічильник не обнулився після успішного входу"


if __name__ == "__main__":
    run(dict(globals()))
