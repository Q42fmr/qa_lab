"""Telegram-бот лаби: сповіщення про нові ClickUp-таски + основа для команд.

.env:
    TELEGRAM_BOT_TOKEN   токен від @BotFather
    TELEGRAM_CHAT_ID     куди слати (дізнатись: /api/telegram/discover_chat
                         після того, як напишеш боту будь-що)
    TELEGRAM_POLL_MIN    період фонового аналізу, хв (дефолт 30)
    CLICKUP_ME           твій username у ClickUp (напр. "Nora Frontend") —
                         за ним шукаємо згадки у коментарях

Архітектура під майбутнє: send() — вихід, get_updates()/dispatch() — вхід.
Команди реєструються у COMMANDS: {"/done": handler(args, chat_id) -> str}.
Так пізніше можна завершати/змінювати таски прямо з телеграма.
"""

from __future__ import annotations

import os

import requests

API = "https://api.telegram.org/bot{token}/{method}"


def token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "").strip()


def me() -> str:
    return os.getenv("CLICKUP_ME", "").strip()


def poll_minutes() -> int:
    try:
        return max(1, int(os.getenv("TELEGRAM_POLL_MIN", "30")))
    except ValueError:
        return 30


def enabled() -> bool:
    return bool(token() and chat_id())


def _call(method: str, **params):
    t = token()
    if not t:
        raise ValueError("TELEGRAM_BOT_TOKEN не заданий у .env")
    r = requests.post(API.format(token=t, method=method), json=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram {method} → {r.status_code}: {r.text[:200]}")
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description')}")
    return data.get("result")


def send(text: str, to: str = "", preview: bool = False):
    """Надіслати повідомлення. HTML-розмітка; лінки без прев'ю за замовчуванням."""
    target = to or chat_id()
    if not target:
        raise ValueError("TELEGRAM_CHAT_ID не заданий у .env")
    # телеграм ріже >4096 символів — б'ємо на частини по рядках
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > 3800:
            chunks.append(cur)
            cur = line
        else:
            cur = (cur + "\n" + line) if cur else line
    if cur:
        chunks.append(cur)
    out = []
    for c in chunks:
        out.append(_call("sendMessage", chat_id=target, text=c, parse_mode="HTML",
                         disable_web_page_preview=not preview))
    return out


def get_updates(offset: int | None = None, timeout: int = 0):
    """Вхідні апдейти (для discover_chat і майбутніх команд)."""
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    return _call("getUpdates", **params)


def discover_chat() -> dict:
    """Знайти chat_id: напиши боту будь-що і виклич це."""
    ups = get_updates() or []
    chats = []
    for u in ups:
        msg = u.get("message") or u.get("channel_post") or {}
        ch = msg.get("chat") or {}
        if ch.get("id") and not any(c["id"] == ch["id"] for c in chats):
            chats.append({"id": ch["id"], "type": ch.get("type"),
                          "title": ch.get("title") or ch.get("username")
                          or ch.get("first_name") or ""})
    return {"chats": chats,
            "hint": "додай TELEGRAM_CHAT_ID=<id> у .env і перезапусти сервер"}


# ---------------------------------------------------------------- команди (заділ)
# handler(args: str, chat_id: str) -> str (текст відповіді).
# Реєструй тут — dispatch() сам розбере "/cmd аргументи".
COMMANDS: dict = {}


def command(name: str):
    def deco(fn):
        COMMANDS[name] = fn
        return fn
    return deco


def dispatch(text: str, from_chat: str) -> str | None:
    """Розбирає '/cmd args' і кличе зареєстрований handler."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return None
    parts = text.split(None, 1)
    cmd = parts[0].split("@")[0].lower()      # /done@MyBot → /done
    args = parts[1] if len(parts) > 1 else ""
    fn = COMMANDS.get(cmd)
    if not fn:
        return f"Невідома команда {cmd}. Доступні: {', '.join(sorted(COMMANDS)) or '—'}"
    try:
        return fn(args, from_chat)
    except Exception as e:
        return f"Помилка {cmd}: {e}"
