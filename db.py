"""Спільне підключення до MongoDB.

Навіщо окремий модуль, якщо Mongo вже була в `users.py`. Там клієнт
будувався всередині сховища користувачів, і другий споживач (реєстр
ШІ-моста — див. `qa_lab-work/notes/08-AI-BRIDGE-PLAN.md`) завів би **другий**
`MongoClient` у тому ж процесі: другий пул з'єднань, другий таймаут, друге
місце, де правити `appname`, TLS чи ретраї. Тут — одна точка на процес.

Контракт навмисно той самий, що вже перевірений у `users.py`:

  * `MONGO_URI` порожній — бази просто немає, `enabled()` = False. Це
    **робочий режим**, а не поломка: лаба вміє жити на json-файлах і
    нативно/локально так і живе;
  * `MONGO_URI` заданий, але база недоступна — **голосне падіння**, а не
    тихий фолбек на файл. Тихий фолбек гірший за виняток: адмін вважає, що
    дані в базі, а вони в контейнері, який зникне з наступним деплоєм.

`serverSelectionTimeoutMS`: без нього мертва база вішає запит на 30 с
і назовні це виглядає як «лаба зависла», а не як «немає Mongo».

Де що береться:
    MONGO_URI   mongodb://user:pass@host:27017/?authSource=admin
    MONGO_DB    назва бази (дефолт qa_lab)
Локально Mongo піднімає `docker-compose.dev.yml` (сервіс `mongo`), у проді
координати приїжджають CI-змінною — вона вже проходить через
`.env.prod.example` → `sed` у `.gitlab-ci.yml`.
"""
from __future__ import annotations

import os
import threading
import time

# Клієнт кешується ПО URI, а не глобально одинаком: `users.py` історично
# отримує uri аргументом (щоб тест міг підсунути свій), а решта споживачів
# бере його з оточення. Ключ по рядку підключення склеює обидва шляхи в
# один пул, коли рядок той самий, і чесно розводить, коли різний.
_clients: dict[str, object] = {}
_lock = threading.Lock()

# Скільки чекаємо вибору сервера. П'ять секунд — стільки ж, скільки стояло
# в users.py: досить, щоб пережити перевибори реплік, і мало, щоб мертва
# база впала помилкою, а не таймаутом запиту.
SERVER_SELECTION_MS = 5000

APP_NAME = "qa_lab"


def uri() -> str:
    return os.getenv("MONGO_URI", "").strip()


def db_name() -> str:
    return os.getenv("MONGO_DB", "qa_lab").strip() or "qa_lab"


def enabled() -> bool:
    """Чи взагалі налаштована БД. Порожній URI — штатний режим «на файлах»."""
    return bool(uri())


def client_for(connect_uri: str):
    """Клієнт для конкретного рядка підключення. Кешується на процес.

    Перше підключення одразу пінгує базу: інакше про недоступність ми
    дізнавались би з випадкового місця — першої ж операції посеред запиту
    користувача, — і повідомлення було б про неї, а не про Mongo.
    """
    connect_uri = (connect_uri or "").strip()
    if not connect_uri:
        raise ValueError("порожній MONGO_URI")
    cached = _clients.get(connect_uri)
    if cached is not None:
        return cached
    with _lock:
        cached = _clients.get(connect_uri)
        if cached is not None:
            return cached
        from pymongo import MongoClient
        cl = MongoClient(connect_uri, serverSelectionTimeoutMS=SERVER_SELECTION_MS,
                         appname=APP_NAME)
        cl.admin.command("ping")
        _clients[connect_uri] = cl
        # Один рядок у лог: далі за ним видно, на чому саме піднялась лаба.
        # Пароль з рядка підключення сюди не потрапляє — друкуємо лише базу.
        print(f"[db] Mongo підключено, база {db_name()!r}")
        return cl


def client():
    """Клієнт з оточення. None — коли MONGO_URI не заданий."""
    if not enabled():
        return None
    try:
        return client_for(uri())
    except Exception as e:
        raise RuntimeError(
            f"MONGO_URI задано, але підключитись не вдалось: {e}. "
            f"Або полагодь доступ до Mongo, або прибери MONGO_URI, "
            f"щоб дані лежали у файлах стану."
        ) from e


def database(name: str = ""):
    """База з оточення (або задана явно). None — коли БД не налаштована."""
    cl = client()
    return cl[name or db_name()] if cl is not None else None


def collection(name: str):
    """Колекція за назвою. None — коли БД не налаштована.

    Споживач зобов'язаний уміти жити з None: усі реєстри лаби мають
    файловий бекенд, а БД для них — дзеркало, а не єдине місце.
    """
    d = database()
    return d[name] if d is not None else None


def ping() -> dict:
    """Стан БД для сторінок статусу. НІКОЛИ не кидає — його викликають
    звідти, де виняток перетворив би «Mongo моргнула» на «сторінка впала»."""
    if not enabled():
        return {"enabled": False, "ok": False, "reason": "MONGO_URI не заданий"}
    started = time.time()
    try:
        cl = client_for(uri())
        info = cl.admin.command("ping")
        return {"enabled": True, "ok": bool(info.get("ok")),
                "db": db_name(), "ms": int((time.time() - started) * 1000)}
    except Exception as e:
        return {"enabled": True, "ok": False, "db": db_name(),
                "error": f"{type(e).__name__}: {e}",
                "ms": int((time.time() - started) * 1000)}


def reset_for_tests() -> None:
    """Тести міняють MONGO_URI на ходу — кеш клієнтів має це переживати."""
    with _lock:
        for cl in _clients.values():
            try:
                cl.close()
            except Exception:
                pass
        _clients.clear()
