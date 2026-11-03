"""Тести сесійної куки і — головне — того, що застосунок справді закритий.

Найважливіший тест тут останній: він перебирає ВСІ маршрути застосунку і
вимагає, щоб кожен, крім короткого списку публічних, був за сесією. Ендпоінтів
понад півтори сотні, очима їх не переглянути, а один забутий — це дірка, якої
не видно ні в UI, ні в код-рев'ю.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import auth                                                       # noqa: E402
import users                                                      # noqa: E402


def _store():
    d = Path(tempfile.mkdtemp(prefix="auth-"))
    st = users.FileUserStore(d / "users.json")
    users.reset_store_for_tests(st)
    auth.invalidate()
    return st


def _fixed_secret():
    os.environ["QA_LAB_SECRET_KEY"] = "test-secret-key"
    auth.reset_secret_for_tests()


# --------------------------------------------------------------- кука

def test_token_roundtrip():
    _fixed_secret()
    assert auth.read_token(auth.make_token("abc123")) == "abc123"


def test_tampered_payload_is_rejected():
    """Підміна uid у відкритій частині ламає підпис."""
    _fixed_secret()
    token = auth.make_token("abc123")
    body, _, sig = token.partition(".")
    forged = auth._b64(b'{"uid":"root","iat":9999999999}') + "." + sig
    assert auth.read_token(forged) is None
    assert body                                    # sanity


def test_token_signed_with_another_key_is_rejected():
    """Саме тому ключ і зберігається: чужий ключ = чужі куки не діють."""
    _fixed_secret()
    token = auth.make_token("abc123")
    os.environ["QA_LAB_SECRET_KEY"] = "another-secret"
    auth.reset_secret_for_tests()
    try:
        assert auth.read_token(token) is None
    finally:
        _fixed_secret()


def test_expired_token_is_rejected():
    _fixed_secret()
    import json
    payload = json.dumps({"uid": "u", "iat": int(time.time()) - auth.MAX_AGE - 10},
                         separators=(",", ":")).encode()
    body = auth._b64(payload)
    import hashlib
    import hmac
    sig = hmac.new(auth.secret_key(), body.encode(), hashlib.sha256).digest()
    assert auth.read_token(f"{body}.{auth._b64(sig)}") is None


def test_garbage_tokens_do_not_crash():
    _fixed_secret()
    for junk in (None, "", "no-dot", "a.b", "....", "x." * 50):
        assert auth.read_token(junk) is None, junk


# --------------------------------------------------------------- користувач

def test_disabled_user_is_not_returned():
    """Вимкнення має вибивати ЖИВУ сесію, а не чекати, доки протухне кука."""
    st = _store()
    _fixed_secret()
    row = st.create({"login": "a"})
    uid = row["id"]
    assert auth.user_by_uid(uid) is not None
    st.update(uid, {"is_active": False})
    auth.invalidate(uid)
    assert auth.user_by_uid(uid) is None


def test_cache_is_dropped_on_invalidate():
    st = _store()
    _fixed_secret()
    uid = st.create({"login": "a"})["id"]
    auth.user_by_uid(uid)
    st.update(uid, {"name": "changed"})
    auth.invalidate(uid)
    assert auth.user_by_uid(uid)["name"] == "changed"


def test_unknown_uid_is_none():
    _store()
    _fixed_secret()
    assert auth.user_by_uid("no-such-id") is None


# --------------------------------------------------------------- allowlist

def test_public_paths_are_only_what_is_needed_to_get_in():
    """Список публічних маршрутів має лишатись коротким і усвідомленим.

    Якщо сюди щось додали — це має бути видно в дифі й вимагати пояснення,
    тому перелік зафіксовано тестом.
    """
    assert auth.PUBLIC_PATHS == frozenset({
        "/login",
        # словник і рушій i18n: екран входу — єдина сторінка без сесії, і він
        # теж має бути тією мовою, яку обрали. Даних у файлах немає.
        "/i18n.js",
        "/i18n-dict.js",
        "/api/health",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/me",
        "/api/auth/slack/start",
        "/api/auth/slack/callback",
        "/favicon.ico",
    }), sorted(auth.PUBLIC_PATHS)


def test_is_public_does_not_match_by_prefix():
    """Ніяких «усе під /api/auth/» — інакше майбутній /api/auth/promote
    виявився б відкритим сам собою."""
    assert not auth.is_public("/api/auth/login/extra")
    assert not auth.is_public("/api/status")
    assert not auth.is_public("/static/index.html")
    assert not auth.is_public("/")


def _all_routes(application):
    """Усі маршрути, включно з тими, що прийшли через `include_router`.

    Плаский `app.routes` їх НЕ показує: підключений роутер лежить там одним
    об'єктом-обгорткою без `path`, і підмітальник нижче мовчки проходив би
    повз цілу групу ендпоінтів. Саме так виглядала б дірка, якої цей тест
    і має не допускати — тому розгортаємо.
    """
    out = []
    for r in application.routes:
        inner = getattr(r, "original_router", None)
        if inner is not None:
            out += list(getattr(inner, "routes", []))
        else:
            out.append(r)
    return out


def _asgi_call(application, path, method="GET"):
    """Мінімальний виклик ASGI-застосунку без сесії.

    Свій, а не `starlette.testclient`: той тягне httpx, а правило репозиторію —
    жодних нових залежностей заради тестів.
    """
    import asyncio

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "scheme": "http",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 12345), "server": ("testserver", 80),
    }
    got = {"status": None}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            got["status"] = message["status"]

    asyncio.run(application(scope, receive, send))
    return got["status"]


def test_every_route_is_closed_unless_explicitly_public():
    """Перебір УСІХ маршрутів застосунку через справжній ASGI-виклик.

    Це і є страховка від забутого ендпоінта: новий маршрут закритий за
    замовчуванням, а щоб відкрити — треба явно вписати його в PUBLIC_PATHS,
    і тест вище покаже це в дифі.

    Перевіряємо не список, а поведінку: без куки кожен непублічний маршрут
    мусить віддати 401 (API) або 302 на /login (сторінка), і в жодному разі
    не 200.
    """
    os.environ["MOCK_MODE"] = "1"
    _store()
    _fixed_secret()
    import app                                                    # noqa: E402

    checked = 0
    leaks = []
    for route in _all_routes(app.app):
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if not path or "{" in path or "GET" not in methods:
            continue                       # параметризовані й не-GET тут не проженеш
        if auth.is_public(path):
            continue
        status = _asgi_call(app.app, path)
        checked += 1
        expected = 401 if path.startswith("/api/") else 302
        if status != expected:
            leaks.append((path, status, expected))

    assert checked > 50, f"перевірено лише {checked} маршрутів — тест зламався"
    assert not leaks, f"маршрути без сесії віддали не те, що мали: {leaks}"


if __name__ == "__main__":
    run(dict(globals()))
