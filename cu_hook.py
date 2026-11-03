"""Вебхук ClickUp — єдині зовнішні двері у чергу.

ClickUp будить нас сам: щойно хтось заповнив `Safe Page`, змінив статус або
написав коментар, сюди прилітає подія з `task_id`. Далі все робить
`cu_queue` — тут лише двері.

Три речі, які визначають цей файл цілком:

1. **Відповідати треба швидко і майже завжди 200.** Серія невдалих доставок
   переводить вебхук у `failing`, і ClickUp глушить підписку — після чого
   тиша виглядає точно так само, як «нових тасок немає». Тому в ендпоінті
   немає жодного походу в GitLab: перевірили підпис, поклали `task_id` у
   чергу, віддали 200. Навіть «черга повна» і «прийом вимкнено» — це 200 з
   поясненням у тілі, а не помилка.
2. **Подія приносить `task_id`, а не таску.** Поля (Safe Page, Тип вайта,
   чекліст) дотягує вже виконавець одним запитом — тут ми не знаємо про
   таску нічого і не намагаємось.
3. **ClickUp повторює доставку.** Ключ дедупу — id запису історії
   (`history_items[].id`), він у події один на подію. Кільце на 5000 ключів
   лежить поруч зі станом черги.

4. **Реєструє вебхук лаба сама** (друга половина файлу). ClickUp віддає
   `secret` рівно один раз — у відповіді на створення. Класти його в
   CI-змінну означає ручний крок між двома деплоями, а джоба, яка створює
   вебхук у пайплайні, або друкує секрет у лог, або потребує токена з
   правами `api`, щоб записати змінну — обидва гірші за файл у томі стану.
   Тому ключ живе поруч зі станом черги, як `.session_secret`, а
   `CLICKUP_WEBHOOK_SECRET` лишається ручним перекриттям.

⚠️ Вебхук бачить рівно те, що бачить його токен. Якщо акаунт не має доступу
до списку, подій по тих тасках не буде ВЗАГАЛІ — і це виглядає як «вебхук не
працює» (розбір — `qa_lab-work/notes/34-CLICKUP-ACCESS.md`).
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException, Request

import auth
import clickup_client
import cu_queue
import projects

SEEN_FILE = "cu_hook_seen.json"
SEEN_CAP = 5000

# Файл реєстрації: id вебхука і його секрет. Лежить у корені стану (том
# `qa_lab-state`), а не поруч з кодом — інакше зникав би з кожним образом і лаба
# перевипускала б вебхук на кожен деплой.
REG_FILE = "cu_webhook.json"

# Підписуємось широко: таска стає «нашою» від заповнення `Safe Page`, а це
# `taskUpdated`, не зміна статусу. Вирішує далі гейт у `clickup_client`,
# не подія.
EVENTS = ["taskCreated", "taskUpdated", "taskStatusUpdated", "taskCommentPosted"]

router = APIRouter()
_seen_lock = threading.Lock()


def _seen_path() -> Path:
    return projects.shared_file(SEEN_FILE)


def _load_seen() -> list:
    try:
        return json.loads(_seen_path().read_text(encoding="utf-8"))
    except Exception:
        return []


def _remember(key: str) -> bool:
    """True — ключ новий. Кільце, а не множина: файл має бути обмеженим."""
    with _seen_lock:
        ring = _load_seen()
        if key in ring:
            return False
        ring.append(key)
        cu_queue._deps["write_json_state"](_seen_path(), ring[-SEEN_CAP:])
        return True


def event_key(body: dict) -> str:
    """Чим відрізняти повтор від нової події.

    `history_items[].id` — найточніше, що є: одна подія в ClickUp це один
    запис історії. Коли його немає (а формат у них не один), падаємо назад до
    трійки «вебхук + таска + подія» разом із хвилиною — так повтор у межах
    доставки відсіється, а справжня наступна подія пройде.
    """
    items = body.get("history_items") or []
    if items and isinstance(items[0], dict) and items[0].get("id"):
        return f"h:{items[0]['id']}"
    return "e:%s:%s:%s:%s" % (body.get("webhook_id", ""), body.get("task_id", ""),
                              body.get("event", ""), time.strftime("%Y%m%d%H%M"))


# --------------------------------------------------------------------------
# Реєстрація вебхука: лаба заводить його собі сама
# --------------------------------------------------------------------------
# Три правила, які тут легко зламати назад:
#
# 1. **Змінна оточення перемагає файл.** Заданий `CLICKUP_WEBHOOK_SECRET`
#    означає «вебхуком керують руками» — тоді ми в ClickUp не лізем узагалі.
#    Інакше було б два джерела ключа, які одного дня розійдуться.
# 2. **Чіпаємо РІВНО свою адресу.** У воркспейсі живуть чужі вебхуки (інші
#    інтеграції, прев'ю-стенд), і видалення «зайвого» тут коштувало б чужої
#    роботи. Фільтр — точний збіг endpoint.
# 3. **`failing` не перестворюємо самі.** Перевипуск міняє секрет, а причина
#    зазвичай тимчасова (лаба лежала під час деплою). Показуємо стан і даємо
#    кнопку — рішення за людиною.
_reg_lock = threading.Lock()
_reg_thread = None


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _reg_path() -> Path:
    return projects.shared_file(REG_FILE)


def load_reg() -> dict:
    return dict(cu_queue._deps["read_json_state"](_reg_path(), {}) or {})


def _save_reg(rec: dict) -> dict:
    cu_queue._deps["write_json_state"](_reg_path(), rec)
    return rec


def secret() -> str:
    """Ключ підпису з нашої реєстрації (порожній — реєстрації немає)."""
    return str(load_reg().get("secret") or "").strip()


def public_endpoint() -> str:
    """Адреса, на яку ClickUp має слати події, — або порожньо.

    Береться з `DOMAIN_NAME`, тієї самої змінної, з якої виводиться
    Slack-redirect. ClickUp приймає лише https і не ходить у локальні імена,
    тож на машині розробника (де домену немає) автореєстрація просто
    не вмикається — і це головна причина, чому вона безпечна за замовчуванням.
    """
    host = os.getenv("DOMAIN_NAME", "").strip().rstrip("/")
    host = host.split("://")[-1].split("/")[0].strip().lower()
    if "." not in host or host.startswith("localhost") or host.endswith(".local"):
        return ""
    return f"https://{host}{auth.HOOK_PATH}"


def auto_state() -> dict:
    """`mode`: `env` — ключ заданий руками; `auto` — реєструємо самі;
    `off` — не реєструємо, і `reason` каже чому."""
    endpoint = public_endpoint()
    if os.getenv("CLICKUP_WEBHOOK_SECRET", "").strip():
        return {"mode": "env", "endpoint": endpoint,
                "reason": "ключ заданий змінною CLICKUP_WEBHOOK_SECRET — "
                          "вебхуком керують руками"}
    if os.getenv("CU_WEBHOOK_AUTO", "1").strip() in ("0", "false", "no"):
        return {"mode": "off", "endpoint": endpoint,
                "reason": "автореєстрацію вимкнено (CU_WEBHOOK_AUTO=0)"}
    if not cu_queue.enabled():
        return {"mode": "off", "endpoint": endpoint,
                "reason": "чергу вимкнено (CU_QUEUE_ENABLED=0)"}
    if not os.getenv("CLICKUP_TOKEN", "").strip():
        return {"mode": "off", "endpoint": endpoint,
                "reason": "немає CLICKUP_TOKEN"}
    if not endpoint:
        return {"mode": "off", "endpoint": "",
                "reason": "немає публічної адреси: DOMAIN_NAME порожній або "
                          "не схожий на домен"}
    return {"mode": "auto", "endpoint": endpoint, "reason": ""}


def _api(method: str, path: str, payload: dict | None = None) -> dict:
    """Один вхід у ClickUp — щоб тести підміняли рівно його, а не мережу."""
    token = os.getenv("CLICKUP_TOKEN", "").strip()
    if not token:
        raise ValueError("CLICKUP_TOKEN не заданий")
    r = requests.request(method, f"{clickup_client.BASE}{path}",
                         headers={"Authorization": token,
                                  "Content-Type": "application/json"},
                         json=payload, timeout=30)
    if r.status_code >= 400:
        # Тіло ClickUp несе причину («team not authorized», «OAUTH_027») —
        # без нього відмова виглядає як «щось пішло не так»
        raise RuntimeError(f"ClickUp {r.status_code}: {r.text[:200]}")
    return r.json() if r.content else {}


def ensure(force: bool = False) -> dict:
    """Звести стан ClickUp з нашим: є наш вебхук — лишити, немає — створити.

    `force` — кнопка «Перереєструвати»: видаляє свій вебхук і випускає новий
    ключ. Потрібна рівно тоді, коли ClickUp заглушив підписку (`failing`).
    """
    with _reg_lock:
        st = auto_state()
        if st["mode"] != "auto":
            return {**st, "changed": False}
        endpoint = st["endpoint"]
        reg = load_reg()
        try:
            token = os.getenv("CLICKUP_TOKEN", "").strip()
            team = clickup_client._team_id({"Authorization": token})
            hooks = (_api("GET", f"/team/{team}/webhook") or {}).get("webhooks") or []
        except Exception as e:
            # Недоступний ClickUp — не привід забути вже виданий ключ:
            # пишемо тільки помилку, реєстрацію лишаємо як є
            reg["last_error"] = str(e)[:300]
            reg["checked_at"] = _now()
            _save_reg(reg)
            return {**st, "changed": False, "error": reg["last_error"]}

        ours = [h for h in hooks
                if (h.get("endpoint") or "").rstrip("/") == endpoint]
        known = next((h for h in ours if h.get("id")
                      and h["id"] == reg.get("id")), None)
        if known and reg.get("secret") and not force:
            reg.update(endpoint=endpoint, team_id=team, checked_at=_now(),
                       health=known.get("health") or {}, last_error="")
            _save_reg(reg)
            return {**st, "changed": False, "status": "ok",
                    "health": reg["health"]}

        # Сюди потрапляємо у двох випадках: вебхука немає взагалі, або він є, а
        # ключа до нього немає (том стану стерли). Друге лікується лише
        # перевипуском: ClickUp не віддає секрет удруге НІКОЛИ.
        dropped, errors = 0, []
        for h in ours:
            try:
                _api("DELETE", f"/webhook/{h['id']}")
                dropped += 1
            except Exception as e:
                errors.append(str(e)[:120])
        try:
            got = _api("POST", f"/team/{team}/webhook",
                       {"endpoint": endpoint, "events": EVENTS})
        except Exception as e:
            reg["last_error"] = str(e)[:300]
            reg["checked_at"] = _now()
            _save_reg(reg)
            return {**st, "changed": False, "error": reg["last_error"]}

        hook = got.get("webhook") or {}
        reg = {"id": hook.get("id") or "", "secret": hook.get("secret") or "",
               "endpoint": endpoint, "team_id": team, "created_at": _now(),
               "checked_at": _now(), "health": hook.get("health") or {},
               "replaced": dropped,
               "last_error": "; ".join(errors)[:300]}
        _save_reg(reg)
        return {**st, "changed": True,
                "status": "recreated" if dropped else "created",
                "replaced": dropped, "health": reg["health"]}


def status() -> dict:
    """Стан для UI. Секрет назовні не віддаємо — лише факт його наявності."""
    st = auto_state()
    reg = load_reg()
    return {"mode": st["mode"], "reason": st["reason"],
            "endpoint": st["endpoint"] or reg.get("endpoint", ""),
            "id": reg.get("id", ""), "health": reg.get("health") or {},
            "created_at": reg.get("created_at", ""),
            "checked_at": reg.get("checked_at", ""),
            "last_error": reg.get("last_error", ""),
            "has_secret": bool(auth.hook_secret()),
            "secret_from": ("змінна оточення" if st["mode"] == "env"
                            else "реєстрація лаби" if reg.get("secret") else "")}


def check_minutes() -> int:
    """Як часто звіряти вебхук з ClickUp після реєстрації (хвилини). Один GET
    на звірку — на ліміті ClickUp (100/хв) непомітно."""
    try:
        return max(5, int(os.getenv("CU_WEBHOOK_CHECK_MIN", "").strip() or 30))
    except ValueError:
        return 30


def start_registration() -> None:
    """Реєстрація у фоні. Старт застосунку від ClickUp залежати не має:
    він може бути недоступний рівно в мить деплою, і тоді єдина правильна
    поведінка — повторити, а не впасти."""
    global _reg_thread
    if auto_state()["mode"] != "auto":
        return
    if _reg_thread and _reg_thread.is_alive():
        return

    tries = max(1, int(os.getenv("CU_WEBHOOK_TRIES", "8") or 8))

    def loop():
        delay = 60
        for _ in range(tries):
            try:
                got = ensure()
                if not got.get("error"):
                    print(f"[hook] вебхук {got.get('status', 'ok')}: "
                          f"{got.get('endpoint')}", flush=True)
                    break
                print(f"[hook] реєстрація не вдалась: {got['error']}", flush=True)
            except Exception as e:
                print(f"[hook] реєстрація впала: {e}", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 1800)
        else:
            print("[hook] реєстрація вебхука не вдалась — лишається кнопка в UI",
                  flush=True)
            return
        # Далі — звірка раз на `check_minutes()`. Стан вебхука («active» /
        # «failing») доти читався РІВНО при старті: 25.09 вкладка показувала
        # FAILING, знятий 24.09 о 14:43 — у мить деплою, коли лаба лежала і
        # доставки справді падали. Що було потім, не знав ніхто. Звірка без
        # `force`: живий вебхук вона не перевипускає (ключ не міняється), лише
        # оновлює стан; зниклий — заводить наново, як на старті.
        while True:
            time.sleep(check_minutes() * 60)
            try:
                got = ensure()
                if got.get("error"):
                    print(f"[hook] звірка не вдалась: {got['error']}", flush=True)
            except Exception as e:
                print(f"[hook] звірка впала: {e}", flush=True)

    _reg_thread = threading.Thread(target=loop, daemon=True, name="cu-webhook-reg")
    _reg_thread.start()


@router.get("/api/queue/webhook")
def api_webhook_status():
    return status()


@router.post("/api/queue/webhook/register")
def api_webhook_register():
    got = ensure(force=True)
    if got.get("mode") != "auto":
        raise HTTPException(400, got.get("reason") or "автореєстрація вимкнена")
    if got.get("error"):
        raise HTTPException(502, got["error"])
    return got


@router.post(auth.HOOK_PATH)
async def clickup_hook(request: Request):
    """Приймає подію ClickUp. Тіло читаємо СИРИМ — підпис рахується по ньому,
    а не по перепакованому json."""
    raw = await request.body()
    if not auth.verify_hook(raw, request.headers.get("x-signature", "")):
        # Єдине місце, де ми відповідаємо не-200. Це не «невдала доставка», а
        # «це не ClickUp», і мовчазне 200 тут ховало б чужі запити.
        raise HTTPException(401, "підпис вебхука не збігається")
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        return {"ok": False, "reason": "тіло не json"}

    task_id = str(body.get("task_id") or "").strip()
    event = str(body.get("event") or "")
    if not task_id:
        return {"ok": False, "reason": "у події немає task_id", "event": event}

    def bump(st):
        st["counters"]["events"] = int(st["counters"].get("events") or 0) + 1
        st["last_event"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return None
    cu_queue._update(bump)

    if not _remember(event_key(body)):
        return {"ok": True, "status": "duplicate", "task_id": task_id}

    try:
        got = cu_queue.submit(task_id, source="hook")
    except cu_queue.QueueFull as e:
        # 200, а не 429: ClickUp не вміє «спробую пізніше» — він рахує це
        # невдачею і врешті глушить підписку. Страхувальник-опит однаково
        # добере цю таску наступним проходом.
        return {"ok": True, "status": "queue_full", "depth": e.depth}
    return {"ok": True, **got, "task_id": task_id, "event": event}
