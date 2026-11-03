"""Виклик лаби від імені людини — через справжній middleware, а не повз нього.

Потрібен тестам «кілька людей одночасно» (задача 21.09.2026): те, що людина
бачить свій проєкт і свій список, вирішує саме middleware, і тест, який кличе
ендпоінт напряму, цього не перевіряє.

Свій, а не `starlette.testclient`: той тягне httpx, а правило репозиторію —
жодних нових залежностей заради тестів.

⚠️ Імпортувати ПІСЛЯ того, як тест поставив `QA_LAB_STATE_DIR`: `auth` тягне
`projects`, а той рахує `ACTIVE_FILE` у момент імпорту — раніше означало б
справжній стан лаби.
"""
import asyncio
import json

import auth
import users


def people(store_path, *logins) -> list[str]:
    """Свіже файлове сховище з цими людьми. Повертає їхні uid.

    Оточення має вже містити `QA_LAB_SECRET_KEY` — ним підписується кука."""
    st = users.FileUserStore(store_path)
    users.reset_store_for_tests(st)
    auth.reset_secret_for_tests()
    auth.invalidate()
    return [str(st.create({"login": x, "name": x.title()})["id"]) for x in logins]


def call(application, method, path, uid=None, body=None, query=""):
    """(статус, json-відповідь або None)."""
    headers = [(b"host", b"testserver")]
    if uid:
        cookie = f"{auth.COOKIE_NAME}={auth.make_token(uid)}"
        headers.append((b"cookie", cookie.encode()))
    raw = b""
    if body is not None:
        raw = json.dumps(body).encode()
        headers.append((b"content-type", b"application/json"))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "path": path, "raw_path": path.encode(),
        "query_string": query.encode(), "root_path": "", "scheme": "http",
        "headers": headers, "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    got = {"status": None, "body": b""}

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            got["status"] = message["status"]
        elif message["type"] == "http.response.body":
            got["body"] += message.get("body", b"")

    asyncio.run(application(scope, receive, send))
    try:
        data = json.loads(got["body"]) if got["body"] else None
    except ValueError:
        data = got["body"].decode("utf-8", "replace")
    return got["status"], data
