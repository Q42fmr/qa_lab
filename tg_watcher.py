"""Фоновий аналіз ClickUp-тасок → сповіщення в Telegram кожні N хвилин.

Фільтри ті самі, що дефолтні у вкладці ClickUp:
  Safe Page заповнене · «Тип вайта» заповнений · чекліст whites не проставлений
  · статус to do / in progress (без content).

Що шле:
  Нових тасок — N, з них з коментарями — M
  Коментарі до тасок
  <лінка> — коментар, де @тегнутий CLICKUP_ME

Стан (які таски вже показані) — tg_state.json, переживає рестарти.
"""

from __future__ import annotations

import html
import re
import threading
import time
import traceback

import clickup_client
import telegram_bot

STATE_FILE = "tg_state.json"
_thread = None
_last = {"ts": None, "new": 0, "with_comments": 0, "error": None, "sent": False}


def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", "", (s or "").lower())


def _load_state(read_json_state):
    st = read_json_state(STATE_FILE, {})
    if not isinstance(st, dict):
        st = {}
    st.setdefault("seen", [])
    return st


def passes_filters(t: dict) -> bool:
    """Дефолтні фільтри вкладки ClickUp."""
    return bool(t.get("branches")) and bool(t.get("wtype")) \
        and t.get("status_match") and not t.get("checklist_done")


def mentions_me(comment: dict, my: str) -> bool:
    if not my:
        return False
    n = _norm(my)
    for m in comment.get("mentions") or []:
        mn = _norm(m)
        if mn and (mn == n or n in mn or mn in n):
            return True
    return False


def build_message(new_tasks: list[dict], my: str) -> str:
    """Повідомлення у форматі: лічильники + коментарі зі згадкою мене."""
    with_c = [t for t in new_tasks
              if any(mentions_me(c, my) for c in (t.get("comments") or []))]
    lines = [f"<b>Нових тасок — {len(new_tasks)}</b>, з них з коментарями — "
             f"<b>{len(with_c)}</b>"]
    if with_c:
        lines.append("")
        lines.append("<b>Коментарі до тасок</b>")
        for t in with_c:
            cm = next((c for c in (t.get("comments") or []) if mentions_me(c, my)), None)
            if not cm:
                continue
            name = html.escape((t.get("name") or "")[:70])
            url = t.get("url") or ""
            txt = html.escape(re.sub(r"\s+", " ", cm.get("text") or "").strip()[:300])
            who = html.escape(cm.get("user") or "")
            link = f'<a href="{html.escape(url)}">{name}</a>' if url else name
            lines.append("")
            lines.append(f"{link}\n<i>{who}:</i> {txt}")
    elif new_tasks:
        lines.append("")
        lines.append("<i>коментарів зі згадкою немає</i>")
    return "\n".join(lines)


def run_once(read_json_state, write_json_state, force: bool = False) -> dict:
    """Один прогін: витягти таски, знайти нові, дозбирати коментарі, надіслати."""
    my = telegram_bot.me()
    st = _load_state(read_json_state)
    seen = set(st.get("seen") or [])

    tasks = [t for t in clickup_client.fetch_all(include_closed=False)
             if passes_filters(t)]
    new_tasks = [t for t in tasks if t["id"] not in seen]

    # коментарі тягнемо ТІЛЬКИ для нових тасок (1-2 запити на таску)
    if new_tasks:
        ids = [{"id": t["id"]} for t in new_tasks[:60]]     # запобіжник на rate limit
        full = clickup_client.fetch_by_ids(ids, with_comments=True)
        by_id = {f["id"]: f for f in full if not f.get("enrich_failed")}
        for t in new_tasks:
            f = by_id.get(t["id"])
            if f:
                t["comments"] = f.get("comments") or []
                t["url"] = f.get("url") or t.get("url")

    sent = False
    if new_tasks or force:
        telegram_bot.send(build_message(new_tasks, my))
        sent = True

    st["seen"] = sorted(seen | {t["id"] for t in tasks})[-5000:]
    st["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json_state(STATE_FILE, st)

    with_c = sum(1 for t in new_tasks
                 if any(mentions_me(c, my) for c in (t.get("comments") or [])))
    _last.update({"ts": st["last_run"], "new": len(new_tasks),
                  "with_comments": with_c, "error": None, "sent": sent})
    return dict(_last)


def start(read_json_state, write_json_state):
    """Піднімає фоновий потік (раз на процес). Мовчить, якщо телеграм не налаштований."""
    global _thread
    if _thread and _thread.is_alive():
        return
    if not telegram_bot.enabled():
        return

    def loop():
        time.sleep(20)                       # даємо серверу стартувати
        while True:
            try:
                run_once(read_json_state, write_json_state)
            except Exception as e:
                _last.update({"error": str(e)[:300], "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
                traceback.print_exc()
            wait = telegram_bot.poll_minutes() * 60
            _last["next_epoch"] = time.time() + wait   # для зворотного відліку в UI
            time.sleep(wait)

    _thread = threading.Thread(target=loop, daemon=True, name="tg-watcher")
    _thread.start()


def status() -> dict:
    nxt = _last.get("next_epoch")
    return {**_last, "enabled": telegram_bot.enabled(),
            "every_min": telegram_bot.poll_minutes(),
            "me": telegram_bot.me(),
            "running": bool(_thread and _thread.is_alive()),
            "next_in_sec": (max(0, int(nxt - time.time())) if nxt else None),
            "server_epoch": time.time()}
