"""«Fixed уже є»: попередження для РУЧНОЇ роботи, що таску вже відписали.

Навіщо (задача 24.09.2026). 23.09 у тасці [878] Microsoft br-pt за пів години
лягло чотири «fixed» — три від колеги і один від «Administrator». Список тасок
у вкладці ClickUp живе в браузері кожного, і людина, яка завантажила його
раніше, чужого «fixed» не бачить, доки сама не перечитає ClickUp. Юзер:
«давати попередження, що такий-то таск вже раніше був пофікшений, але при
цьому не блокувати роботу, а просто попереджати про вже наявний fixed
користувача. Це стосується саме ручної роботи. Перевіряти по fixed в ClickUp».

Тому тут НІЧОГО не блокується і нічого не пишеться в ClickUp. Модуль лише
читає коментарі і тримає дошку «хто що вже відписав», спільну для всіх
(`clickup_fixed.json` у корені стану: таски належать воркспейсу, а не
проєкту). Автоматиці ні дошка, ні попередження не потрібні: вебхук і опит
таких тасок не беруть узагалі (рішення юзера 24.09, `cu_triage.fixed_is_last`).

Чотири рішення, які легко зламати назад:

1. **Що таке «fixed», визначає тріаж** (`cu_triage.fixed_by` / `fixed_note`) —
   ОДНЕ визначення на ручну роботу й автоматику, тим самим словником
   `DONE_WORDS`: дві таблиці «що вважати відповіддю» розійшлись би за місяць.
   Сам підпис лаби ще НЕ «fixed»: звіт ШІ-моста теж підписаний, але фіксом
   не є.
2. **Автора беремо з підпису, а не з ClickUp.** Лаба пише одним сервісним
   акаунтом (Tech Bot), тож хто насправді відписав, видно лише з «…by Liam»
   у кінці коментаря.
3. **Два рівні, а не один.** Заміряно на корпусі 03.09 (190 тасок): «fixed»
   є в 178. Попередження на кожну таску з «fixed» в історії було б шумом на
   весь екран. Тому розрізняємо:
   * `fixed` — останнє, що сталось: нового прохання після нього немає. Це і є
     ризик дубля, його видно жовтим;
   * після `fixed` саппорт попросив знову (`asked_again`) — таска законно
     повернулась у роботу, це лише довідка.
   «Попросив знову» визначає рівно те правило, яким автоматика шле таску на
   ручний розбір (`cu_triage.support_request`). Будь-який коментар для цього
   не годиться: зі 159 тасок, де після «fixed» хтось писав, 87 — це «апрув,
   дякую» / «все гуд, забрал» від медіабаєрів, 69 — конфіг деплою, і лише 2 —
   справжнє «Можешь пофиксить, пожалуйста».
4. **Свіжість важливіша за економію, але з межею.** Перевірка ходить у
   ClickUp (два запити на таску, ліміт 100/хв на ОДИН токен лаби для всіх),
   тож таску, перевірену менш ніж `FRESH_S` секунд тому, не перечитуємо:
   відповідь уже лежить на дошці. Вікно коротке навмисно, бо дубль
   народжується саме тоді, коли двоє працюють над таскою в ту саму хвилину.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import attribution
import clickup_client
import projects
import users
# Визначення «fixed» — у тріажі, одне на ручну роботу й автоматику.
from cu_triage import MARKS_MAX, fixed_note

STATE_FILE = "clickup_fixed.json"

# Скільки секунд відповідь дошки вважається свіжою (див. рішення 4).
FRESH_S = 60
# Скільки тасок дошка пам'ятає. Одна таска — кілька сотень байтів, а робочий
# корпус за місяць — сотні тасок, тож стеля лише про те, щоб файл не ріс вічно.
CAP = 3000
# Скільки тасок за один виклик. «Sync обрані» на весь список — це десятки
# тасок, а кожна коштує двох запитів із загальних 100/хв: без стелі одна
# людина могла б на хвилину забрати ClickUp у всіх інших.
CHECK_MAX = 40


# --------------------------------------------------------------------------
# 1. Дошка «хто що вже відписав»
# --------------------------------------------------------------------------
def _plain_read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _plain_write(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


# Дефолти — щоб модуль піднімався сам (тести, консоль). У проді `app`
# підставляє `write_json_state` (`.tmp` + `os.replace`).
_deps: dict = {"read_json_state": _plain_read, "write_json_state": _plain_write}
_lock = threading.Lock()


def wire(*, read_json_state, write_json_state) -> None:
    _deps.update(read_json_state=read_json_state, write_json_state=write_json_state)


def _path() -> Path:
    return projects.shared_file(STATE_FILE)


def board() -> dict:
    """{task_id: {"note": dict|None, "ts": "…", "t": epoch}}."""
    got = _deps["read_json_state"](_path(), {})
    return got if isinstance(got, dict) else {}


def remember(notes: dict) -> None:
    """Записати свіжі відповіді ClickUp. `None` теж запис: «fixed немає» на
    момент перевірки — інакше видалений у ClickUp дубль висів би вічно."""
    if not notes:
        return
    now = time.time()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
    with _lock:
        b = board()
        for tid, note in notes.items():
            b[tid] = {"note": note, "ts": stamp, "t": now}
        _save(b)


def _save(b: dict) -> None:
    """Запис дошки зі стелею (кликати під `_lock`): найстаріші перевірки
    йдуть першими."""
    if len(b) > CAP:
        for tid in sorted(b, key=lambda k: b[k].get("t") or 0)[:len(b) - CAP]:
            b.pop(tid, None)
    _deps["write_json_state"](_path(), b)


def learn(tasks: list) -> None:
    """Задарма підхопити те, що вже прочитано з ClickUp (вкладка ClickUp
    довантажує таски з коментарями — другий запит по них був би зайвим)."""
    notes = {t["id"]: fixed_note(t) for t in tasks or []
             if isinstance(t, dict) and t.get("id") and isinstance(t.get("comments"), list)
             and not t.get("enrich_failed") and not t.get("no_access")}
    remember(notes)


def mark_mine(task_ids: list, who: str) -> int:
    """Свій щойно відписаний «fixed» — на дошку БЕЗ походу в ClickUp.

    Коментар лаба щойно написала сама, тож читати його назад — два запити на
    таску зі спільних 100/хв, а масова кнопка на 40 тасок з'їла б на це
    майже весь ліміт. Лічильник — «що знали + 1»: точне число приїде з
    наступною справжньою перевіркою. `who` — те саме ім'я, що в підписі
    коментаря (`attribution.actor_name`), тож справжня перевірка потім
    побачить рівно того самого автора.
    """
    ids = list(dict.fromkeys(str(i).strip() for i in task_ids or [] if str(i or "").strip()))
    if not ids:
        return 0
    now = time.time()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
    date = str(int(now * 1000))
    with _lock:
        b = board()
        for tid in ids:
            prev = (b.get(tid) or {}).get("note") or {}
            marks = [{"by": who, "date": date}] + list(prev.get("marks") or [])
            b[tid] = {"note": {"count": int(prev.get("count") or 0) + 1, "by": who,
                               "date": date, "asked_again": None,
                               "marks": marks[:MARKS_MAX]},
                      "ts": stamp, "t": now}
        _save(b)
    return len(ids)


def check(task_ids: list, token: str = "", fresh_s: float | None = None) -> dict:
    """Перевірити таски в ClickUp і відповісти дошкою.

    `token` — особистий токен людини: таску, розшарену їй персонально,
    застосунковий акаунт не бачить (той самий добір, що в `/api/clickup/by_links`).
    """
    fresh_s = FRESH_S if fresh_s is None else fresh_s
    ids = list(dict.fromkeys(str(i).strip() for i in task_ids or [] if str(i or "").strip()))
    over = max(0, len(ids) - CHECK_MAX)
    ids = ids[:CHECK_MAX]
    now = time.time()
    known = board()
    # «>=», не «>»: fresh_s=0 означає «перечитати завжди», а на Windows
    # time.time() тікає по ~15 мс — запис і перевірка в одному тіку давали
    # вік 0 і віддавали кеш (флейк test_a_failed_read_keeps_what_the_board_knew)
    todo = [i for i in ids if now - float((known.get(i) or {}).get("t") or 0) >= fresh_s]

    got = clickup_client.fetch_by_ids([{"id": i} for i in todo], with_comments=True) if todo else []
    denied = [k for k, t in enumerate(got) if t.get("no_access")]
    if token and denied:
        retry = clickup_client.fetch_by_ids([{"id": todo[k]} for k in denied],
                                            with_comments=True, token=token)
        for k, t in zip(denied, retry):
            if not t.get("no_access") and not t.get("enrich_failed"):
                got[k] = t

    fresh, failed = {}, []
    for want, t in zip(todo, got):
        if t.get("enrich_failed") or t.get("no_access") or not isinstance(t.get("comments"), list):
            failed.append(want)
            continue
        fresh[want] = fixed_note(t)
    remember(fresh)

    known = board()
    notes = {i: (known.get(i) or {}).get("note") for i in ids}
    # `ids` — що справді розглянуто (після стелі): UI знімає попередження
    # лише з них, а не з усього, про що питав.
    return {"ids": ids, "notes": {k: v for k, v in notes.items() if v},
            "checked": len(fresh), "cached": len(ids) - len(todo),
            "failed": failed, "over": over}


# --------------------------------------------------------------------------
# 2. Ендпоінти (під сесійним гейтом, як і все)
# --------------------------------------------------------------------------
router = APIRouter()


@router.get("/api/clickup/fixed")
def api_board():
    """Лише таски, де «fixed» є: UI малює попередження, а не дошку цілком."""
    return {tid: rec["note"] for tid, rec in board().items()
            if isinstance(rec, dict) and rec.get("note")}


class TasksRequest(BaseModel):
    task_ids: list[str]


@router.post("/api/clickup/fixed/check")
def api_check(req: TasksRequest, request: Request):
    if not os.getenv("CLICKUP_TOKEN", "").strip():
        raise HTTPException(400, "CLICKUP_TOKEN не заданий — перевірити fixed нема чим")
    me = getattr(request.state, "user", None) or {}
    return check(req.task_ids, token=users.clickup_token_of(me))


@router.post("/api/clickup/fixed/mine")
def api_mine(req: TasksRequest, request: Request):
    """UI кличе одразу після СВОГО «✔ … fixed» (одиночного й масового):
    інакше колега, що бере ту саму таску в ту ж хвилину, отримав би з дошки
    відповідь, прочитану ДО цього «fixed», — рівно той дубль, заради якого
    все писалось."""
    me = getattr(request.state, "user", None) or {}
    return {"marked": mark_mine(req.task_ids, attribution.actor_name(me) or "?")}
