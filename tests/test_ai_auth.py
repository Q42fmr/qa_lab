"""Тести машинного доступу до ШІ-моста.

З того боку конвеєра — застосунок, а не людина: куки в нього немає і бути не
може. Тут закріплено три рішення, кожне з яких — про те, ЧОГО токен не дає.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import auth                                                       # noqa: E402

GOOD = "x" * 40


class Req:
    def __init__(self, path, header=None):
        self.url = type("U", (), {"path": path})()
        self.headers = {"authorization": header} if header else {}


def _set(tok):
    if tok is None:
        os.environ.pop("QA_LAB_BRIDGE_TOKEN", None)
    else:
        os.environ["QA_LAB_BRIDGE_TOKEN"] = tok


def test_valid_token_authenticates_a_machine():
    _set(GOOD)
    u = auth.service_user(Req("/api/ai/request", f"Bearer {GOOD}"))
    assert u and u["login"] == "ai-bridge"
    assert auth.is_service(u) is True
    assert u["is_admin"] is False, "машині права адміністратора не потрібні"


def test_the_token_does_not_open_the_rest_of_the_lab():
    """Найважливіше обмеження: витік токена не має давати доступ до комітів
    у будь-яку вітку і до правки користувачів."""
    _set(GOOD)
    for path in ("/api/branches", "/api/checks/fix/apply", "/api/users", "/"):
        assert auth.service_user(Req(path, f"Bearer {GOOD}")) is None, path


def test_no_token_no_machine():
    _set(GOOD)
    assert auth.service_user(Req("/api/ai/request")) is None
    assert auth.service_user(Req("/api/ai/request", "Bearer ")) is None
    assert auth.service_user(Req("/api/ai/request", f"Basic {GOOD}")) is None


def test_a_wrong_token_is_rejected():
    _set(GOOD)
    assert auth.service_user(Req("/api/ai/request", "Bearer " + "y" * 40)) is None
    assert auth.service_user(Req("/api/ai/request", f"Bearer {GOOD[:-1]}")) is None


def test_an_unset_token_does_not_open_the_bridge():
    """Порожня змінна не має ставати порожнім паролем — рівно та граблина,
    що зʼїла перший деплой з порожнім BASIC_AUTH_USERS."""
    _set(None)
    assert auth.service_user(Req("/api/ai/request", "Bearer ")) is None
    assert auth.service_user(Req("/api/ai/request", "Bearer щось")) is None
    _set("")
    assert auth.service_user(Req("/api/ai/request", "Bearer ")) is None


def test_a_short_token_is_refused_outright():
    short = "a" * 8
    _set(short)
    assert auth.service_user(Req("/api/ai/request", f"Bearer {short}")) is None


def test_bridge_paths_are_not_public():
    """Токен дає ІНШОГО користувача, а не відсутність авторизації. Якби
    шляхи мосту поїхали в PUBLIC_PATHS, вони відкрились би всім."""
    for p in ("/api/ai/request", "/api/ai/log", "/api/ai/skills"):
        assert not auth.is_public(p)


# ------------------------------------------------- через сам застосунок

def _call(path, headers=None, method="GET", body=None):
    import asyncio, json
    hdrs = [(b"host", b"testserver")]
    for k, v in (headers or {}).items():
        hdrs.append((k.lower().encode(), v.encode()))
    raw = json.dumps(body).encode() if body is not None else b""
    if body is not None:
        hdrs += [(b"content-type", b"application/json"),
                 (b"content-length", str(len(raw)).encode())]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": method, "path": path, "raw_path": path.encode(),
             "query_string": b"", "root_path": "", "scheme": "http",
             "headers": hdrs, "client": ("127.0.0.1", 1), "server": ("t", 80)}
    got = {"status": None}

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            got["status"] = msg["status"]

    import app
    asyncio.run(app.app(scope, receive, send))
    return got["status"]


def test_bridge_endpoint_needs_the_token_end_to_end():
    _set(GOOD)
    assert _call("/api/ai/log") == 401
    assert _call("/api/ai/log", {"authorization": "Bearer " + "y" * 40}) == 401
    assert _call("/api/ai/log", {"authorization": f"Bearer {GOOD}"}) == 200


def test_the_token_does_not_open_another_endpoint_end_to_end():
    _set(GOOD)
    assert _call("/api/branches", {"authorization": f"Bearer {GOOD}"}) == 401


def _human_cookie():
    """Кука живого користувача — щоб перевірити, що людині МОЖНА те, чого
    не можна машині."""
    import tempfile
    from pathlib import Path
    import users
    os.environ["QA_LAB_SECRET_KEY"] = "test-secret-key"
    auth.reset_secret_for_tests()
    st = users.FileUserStore(Path(tempfile.mkdtemp(prefix="ai-auth-")) / "u.json")
    users.reset_store_for_tests(st)
    auth.invalidate()
    row = st.create({"login": "human@example.com", "name": "Людина"})
    return f"{auth.COOKIE_NAME}={auth.make_token(auth.uid_of(row))}"


def test_a_machine_cannot_edit_the_skills():
    """Токен автентифікує на всьому /api/ai/*, а правка скілів — це зміна
    того, які перевірки взагалі бачить модель. Витік токена не має давати
    права переписати каталог."""
    _set(GOOD)
    tok = {"authorization": f"Bearer {GOOD}"}
    body = {"check_id": "logo_domain", "симптом": "підмінено машиною"}
    assert _call("/api/ai/skills", tok, "POST", body) == 403
    assert _call("/api/ai/skills/logo_domain", tok, "DELETE") == 403
    assert _call("/api/ai/skills/logo_domain/active", tok, "POST",
                 {"active": False}) == 403
    # читати каталог машині можна: він потрібен їй для роботи
    assert _call("/api/ai/skills", tok) == 200


def test_a_human_with_a_session_can_edit_the_skills():
    import ai_skills_store
    import tempfile
    from pathlib import Path
    ai_skills_store.reset_for_tests(
        ai_skills_store._FileStore(
            Path(tempfile.mkdtemp(prefix="sk-")) / "ai_skills.json"))
    ck = {"cookie": _human_cookie()}
    try:
        assert _call("/api/ai/skills", ck, "POST",
                     {"check_id": "logo_domain", "симптом": "правка людини"}) == 200
        assert ai_skills_store.get("logo_domain")["author"] == "human@example.com"
        assert _call("/api/ai/skills/logo_domain", ck, "DELETE") == 200
    finally:
        ai_skills_store.reset_for_tests(None)


def test_a_bad_skill_is_refused_with_a_readable_reason():
    import ai_skills_store
    import tempfile
    from pathlib import Path
    ai_skills_store.reset_for_tests(
        ai_skills_store._FileStore(
            Path(tempfile.mkdtemp(prefix="sk-")) / "ai_skills.json"))
    ck = {"cookie": _human_cookie()}
    try:
        assert _call("/api/ai/skills", ck, "POST",
                     {"check_id": "logo_domain", "симптом": ""}) == 400
    finally:
        ai_skills_store.reset_for_tests(None)


def test_a_machine_cannot_edit_the_verdict_map():
    """Те саме правило, що й для скілів, і з тієї самої причини: мапа
    вердиктів вирішує, ЯКІ перевірки взагалі запустяться по скарзі. Витік
    токена не має давати права її переписати — машина шле вердикти, а не
    налаштовує лабу.

    Читати мапу машині можна і треба: той бік має бачити, чого від нас
    чекати по кожній своїй перевірці."""
    _set(GOOD)
    tok = {"authorization": f"Bearer {GOOD}"}
    assert _call("/api/ai/verdicts", tok, "POST",
                 {"key": "tsm:links", "cls": "ours", "php": ["forms"]}) == 403
    assert _call("/api/ai/verdicts/tsm:links", tok, "DELETE") == 403
    assert _call("/api/ai/verdicts", tok) == 200


def test_a_human_can_edit_the_verdict_map():
    import tempfile
    from pathlib import Path

    import verdict_map
    verdict_map.reset_for_tests(
        verdict_map._FileStore(
            Path(tempfile.mkdtemp(prefix="vm-")) / "ai_verdicts.json"))
    ck = {"cookie": _human_cookie()}
    try:
        assert _call("/api/ai/verdicts", ck, "POST",
                     {"key": "tsm:links", "cls": "ours",
                      "php": ["link_target"]}) == 200
        assert verdict_map.get("tsm:links")["by"] == "human"
        assert _call("/api/ai/verdicts/tsm:links", ck, "DELETE") == 200
    finally:
        verdict_map.reset_for_tests(None)


def test_a_bad_verdict_record_is_refused_with_a_readable_reason():
    import tempfile
    from pathlib import Path

    import verdict_map
    verdict_map.reset_for_tests(
        verdict_map._FileStore(
            Path(tempfile.mkdtemp(prefix="vm-")) / "ai_verdicts.json"))
    ck = {"cookie": _human_cookie()}
    try:
        # клас «ours» без жодного чека — це не запис, а побажання
        assert _call("/api/ai/verdicts", ck, "POST",
                     {"key": "tsm:links", "cls": "ours"}) == 400
    finally:
        verdict_map.reset_for_tests(None)


if __name__ == "__main__":
    run(dict(globals()))
