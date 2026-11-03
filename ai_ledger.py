"""Реєстр запитів ШІ-моста: лічильник автофіксів і захист від кола.

Навіщо окремо від `stats_ledger`. Той знає лише про **коміти** — а мосту
треба рахувати і те, що комітом НЕ закінчилось: скарги «не наше», прогони,
де чеки нічого не знайшли, ескалації, гроші за виклики Claude. Саме ці
записи потім і відповідають на питання «чому міст мовчить».

Формат — той самий ідіом, що в `stats_ledger`/`checks_ledger`: append-only
шарди по місяцях (`ai_requests/<місяць>.jsonl`), один рядок = один запит.
Дописування O(1), минулі шарди байт-у-байт незмінні.

**Дзеркало в Mongo.** Файл лишається джерелом істини (переживає падіння
бази, працює в MOCK і нативно), а коли `MONGO_URI` заданий — той самий
запис лягає в колекцію. Схема вибору сховища взята з `users.py`, точка
підключення — спільний `db.py`.

--------------------------------------------------------------------------
ЗАХИСТ ВІД КОЛА

Ризик прямий: на тому кінці ШІ, на цьому ШІ, і скарга може ходити по колу
вічно. Ключ кола — НЕ текст: на другому колі та сама поломка приїде іншими
словами («логотип не той» → «бренд у шапці не відповідає домену»), і
порівняння текстів не спіймало б нічого.

    loop_key = sha1(вітка + "|" + відсортовані id чеків)

Тобто **та сама вітка + той самий клас дефекту, як його розуміє лаба**.
Стійко до перефразування і не склеює різні дефекти однієї вітки.

Другим, грубішим ключем тримаємо **вітку + перетин наборів чеків**: якщо
роутинг на другому колі дав трохи інший набір (`[logo_domain]` → потім
`[logo_domain, header_anchor]`), точний ключ розійдеться, а перетин — ні.

Спершу грубим ключем була пара `(вітка, таска)` — і це виявилось надто
грубо: одна таска ClickUp покриває вайт цілком і законно несе кілька РІЗНИХ
дефектів. На прогоні 20 тасок скарга про логотип ескалювалась через те, що
та сама таска раніше приносила скаргу про форму. Перетин чеків розводить
«те саме, інакше зароутоване» і «інша поломка того самого вайта».
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import db

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


DIRNAME = "ai_requests"
UNKNOWN_SHARD = "unknown"
COLLECTION = "ai_requests"

# Скільки кіл дозволено. Третє — вже не робота, а ескалація.
MAX_ROUNDS = _env_int("AI_MAX_ROUNDS", 2)

# Той самий ключ протягом цього часу — дубль, а не нове коло. Ловить бурю
# ретраїв на тому кінці, не витрачаючи кола. Читається при виклику, тож
# налаштовується оточенням.
COOLDOWN_S = _env_int("AI_COOLDOWN_S", 15 * 60)

# Статуси, що рахуються КОЛОМ. «Дубль» і «не наше» кола не витрачають:
# інакше три однакові ретраї за хвилину вичерпали б ліміт, не зробивши
# жодної спроби полагодити.
ROUND_STATUSES = ("fixed", "clean", "no_fix", "error")


def _dir(root: Path) -> Path:
    return Path(root) / DIRNAME


def _shard_name(ts: str) -> str:
    ts = (ts or "").strip()
    if len(ts) >= 7 and ts[4] == "-" and ts[:4].isdigit() and ts[5:7].isdigit():
        return ts[:7]
    return UNKNOWN_SHARD


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def loop_key(branch: str, check_ids) -> str:
    """Ключ кола. Порожній набір чеків теж має ключ — «нічого не зматчилось»
    саме на цій вітці це теж повторюваний стан, і він теж може зациклитись."""
    ids = ",".join(sorted(str(c) for c in (check_ids or [])))
    raw = f"{branch}|{ids}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def _norm(rec: dict) -> dict:
    """Нормалізація і — важливо — ОБРІЗАННЯ тексту скарги.

    У реєстр іде лише голова тексту: він приходить ззовні, довжина його не
    обмежена нічим, а реєстр читається цілком на кожен запит. Повний текст
    і так лежить у ClickUp, звідки приїхав.
    """
    out = {
        "ts": str(rec.get("ts") or now()),
        "request_id": str(rec.get("request_id") or ""),
        "branch": str(rec.get("branch") or ""),
        "domain": str(rec.get("domain") or ""),
        "task_id": str(rec.get("task_id") or ""),
        # Пачка, з якою приїхав запит (`/api/ai/requests`). Порожньо —
        # одиничний запит. Потрібне, щоб алерт людині був ОДИН на пачку, а не
        # пʼять поспіль, і щоб у журналі було видно, що це один прогін TSM.
        "batch_id": str(rec.get("batch_id") or ""),
        "loop_key": str(rec.get("loop_key") or ""),
        "round": int(rec.get("round") or 0),
        "status": str(rec.get("status") or ""),
        "router": str(rec.get("router") or ""),
        "routed": [str(x) for x in (rec.get("routed") or [])],
        "fired": {str(k): int(v) for k, v in (rec.get("fired") or {}).items()},
        "commit": str(rec.get("commit") or ""),
        "files": int(rec.get("files") or 0),
        "usd": round(float(rec.get("usd") or 0), 6),
        "ms": int(rec.get("ms") or 0),
        "text_head": " ".join(str(rec.get("text_head") or "").split())[:200],
        # Відбиток ПОВНОГО тексту — саме тому, що `text_head` обрізаний до 200
        # символів: два різні вердикти по одному вайту легко збігаються
        # головою і розходяться хвостом. Потрібен для ідемпотентності
        # (див. `same_text`), а не для пошуку очима.
        "text_hash": str(rec.get("text_hash") or ""),
        # ХТО І ЯКОЇ ВЕРСІЇ ПРИСЛАВ. Без цих двох полів дрейф формулювань
        # виглядає як «щось зламалось у вівторок»: видно ЩО повз мапу, але не
        # видно, з якого їхнього релізу воно почалось. Один рядок у їхньому
        # запиті — і атрибуція є (пункт 8 зі спільного розбору 26.08).
        "source": str(rec.get("source") or ""),
        "source_version": str(rec.get("source_version") or ""),
        # Скільки рядків СХОЖИХ на вердикт TSM ми не впізнали (див.
        # `tsm_verdicts.parse`). Ненульове означає, що їхній `advice.py`
        # розійшовся з нашими якорями — і поломка ця мовчазна: замість
        # безкоштовної мапи тихо вмикається платна модель.
        "tsm_unknown": int(rec.get("tsm_unknown") or 0),
        # Імена їхніх перевірок з нерозібраних рядків і жовті поради. Обидва
        # списки короткі навмисно: реєстр читається ЦІЛКОМ на кожен запит, і
        # рости йому нема за чим — повний текст лежить у ClickUp.
        "tsm_new": [str(x)[:32] for x in (rec.get("tsm_new") or [])][:5],
        "tsm_soft": [str(x)[:160] for x in (rec.get("tsm_soft") or [])][:3],
        "note": str(rec.get("note") or "")[:300],
    }
    return out


def text_hash(text: str) -> str:
    """Стабільний відбиток тексту скарги. Пробіли схлопнуті: той самий
    коментар, перезгорнутий по-іншому, — це той самий коментар."""
    normed = " ".join((text or "").split())
    return hashlib.sha256(normed.encode("utf-8")).hexdigest()[:32]


def same_text(root: Path, task_id: str, h: str,
              within_s: int | None = None) -> dict | None:
    """Той самий текст по тій самій тасці, і недавно — тобто ретрай.

    Навіщо окремо від `recent()`: той звіряє КЛЮЧ КОЛА (вітка + набір чеків),
    а він відомий лише ПІСЛЯ роутингу. Ретрай же треба впізнати ДО нього —
    інакше повтор мережевої помилки на їхньому боці проходить ідентифікацію,
    роутинг і платний виклик моделі ще раз, перш ніж ми помітимо дубль.
    """
    if within_s is None:
        within_s = COOLDOWN_S
    if not h:
        return None
    cutoff = time.time() - within_s
    for e in reversed(entries(root, shards=2)):
        if e.get("text_hash") != h or e.get("task_id", "") != str(task_id or ""):
            continue
        try:
            ts = time.mktime(time.strptime(e["ts"], "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        return e if ts >= cutoff else None
    return None


def append(root: Path, rec: dict) -> dict:
    """Дописує запис у шард його місяця і дзеркалить у базу.

    Збій бази НЕ валить запит: файл уже записаний, а дзеркало — зручність.
    Протилежний порядок (спершу база) означав би, що падіння Mongo губить
    факт того, що міст щойно зробив коміт.
    """
    rec = _norm(rec)
    d = _dir(root)
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{_shard_name(rec['ts'])}.jsonl").open("a", encoding="utf-8",
                                                      newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    try:
        coll = db.collection(COLLECTION)
        if coll is not None:
            coll.insert_one(dict(rec))
    except Exception as e:
        print(f"[ai] запис у Mongo не вдався (файл записано): {e}")
    return rec


def entries(root: Path, shards: int = 0) -> list[dict]:
    """Записи, відсортовані за часом.

    `shards` — скільки ОСТАННІХ місяців читати (0 = всі). Захист від кола
    дивиться на два останні: коло, що триває понад місяць, — це вже не коло,
    а нова історія.
    """
    d = _dir(root)
    if not d.exists():
        return []
    files = sorted(d.glob("*.jsonl"))
    if shards > 0:
        files = files[-shards:]
    out = []
    for shard in files:
        try:
            text = shard.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(_norm(rec))
    out.sort(key=lambda e: e["ts"])
    return out


# --------------------------------------------------------------------------
# захист від кола
# --------------------------------------------------------------------------
def by_request_id(root: Path, request_id: str) -> dict | None:
    """Ідемпотентність: той самий request_id уже оброблявся."""
    if not request_id:
        return None
    for e in reversed(entries(root, shards=2)):
        if e["request_id"] == request_id:
            return e
    return None


def rounds_done(root: Path, key: str, branch: str = "", routed=()) -> int:
    """Скільки КІЛ уже відпрацьовано по ЦІЙ САМІЙ проблемі.

    Максимум із двох рахунків — точного (той самий набір чеків) і за
    перетином (та сама вітка, і хоч один спільний чек). Другий існує тому,
    що роутинг на другому колі може дати трохи інший набір: точний ключ
    тоді розійдеться, і петля пішла б на нове коло під новим ім'ям.

    Перетин, а не таска: одна таска несе кілька різних дефектів вайта, і
    рахувати їх спільним лічильником означає глушити роботу на рівному
    місці — див. коментар у шапці модуля.
    """
    exact = overlap = 0
    want = {str(c) for c in (routed or [])}
    for e in entries(root, shards=2):
        if e["status"] not in ROUND_STATUSES:
            continue
        if key and e["loop_key"] == key:
            exact += 1
        if branch and want and e["branch"] == branch and want & set(e["routed"]):
            overlap += 1
    return max(exact, overlap)


def recent(root: Path, key: str, within_s: int | None = None) -> dict | None:
    """Останній запит із тим самим ключем, якщо він свіжіший за `within_s`.

    Вікно читається ПРИ ВИКЛИКУ, а не в дефолті параметра: дефолт прив'язався
    б до значення на момент визначення функції, і `COOLDOWN_S` став би
    константою, яку неможливо змінити ні з тесту, ні з оточення.
    """
    if within_s is None:
        within_s = COOLDOWN_S
    if not key:
        return None
    cutoff = time.time() - within_s
    for e in reversed(entries(root, shards=2)):
        if e["loop_key"] != key:
            continue
        try:
            ts = time.mktime(time.strptime(e["ts"], "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        return e if ts >= cutoff else None
    return None


def verdict(root: Path, key: str, branch: str = "", routed=(),
            request_id: str = "") -> dict:
    """Чи можна працювати над цим запитом. Єдина точка ухвалення рішення —
    щоб «максимум два кола» не було розмазане по трьох місцях.

    Повертає {"allow", "reason", "round", "status"}:
      duplicate — ідемпотентність або кулдаун; нічого не запускаємо;
      escalated — кіл вичерпано, потрібна людина;
      ""        — працюємо, це коло номер `round`.
    """
    was = by_request_id(root, request_id)
    if was:
        return {"allow": False, "status": "duplicate", "round": was["round"],
                "reason": f"request_id {request_id} уже оброблявся "
                          f"({was['ts']}, статус {was['status']})"}
    dup = recent(root, key)
    if dup:
        return {"allow": False, "status": "duplicate", "round": dup["round"],
                "reason": f"той самий дефект на цій вітці приходив {dup['ts']} — "
                          f"кулдаун {COOLDOWN_S // 60} хв"}
    done = rounds_done(root, key, branch, routed)
    if done >= MAX_ROUNDS:
        return {"allow": False, "status": "escalated", "round": done + 1,
                "reason": f"це вже {done + 1}-й раз. Лаба відпрацювала "
                          f"{done} кола і дефект лишився — потрібна людина"}
    return {"allow": True, "status": "", "round": done + 1, "reason": ""}


# --------------------------------------------------------------------------
# лічильник
# --------------------------------------------------------------------------
def spend_usd(root: Path, shards: int = 1) -> float:
    """Скільки витрачено на Claude за останні `shards` місяців."""
    return round(sum(e["usd"] for e in entries(root, shards=shards)), 4)


def _count(it) -> dict:
    out: dict = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


def _по_джерелах(rows: list) -> list:
    """[{"source", "version", "n", "drift", "last"}] — свіжіші перші."""
    зведення: dict = {}
    for e in rows:
        ключ = (e.get("source") or "", e.get("source_version") or "")
        if not any(ключ):
            continue
        d = зведення.setdefault(ключ, {"source": ключ[0], "version": ключ[1],
                                       "n": 0, "drift": 0, "last": ""})
        d["n"] += 1
        d["drift"] += int(e.get("tsm_unknown") or 0)
        d["last"] = max(d["last"], e.get("ts", ""))
    return sorted(зведення.values(), key=lambda x: x["last"], reverse=True)


def counters(root: Path, shards: int = 0) -> dict:
    """Зведення для сторінки і для тесту: скільки запитів, скільки фіксів,
    скільки ескалацій, скільки грошей."""
    rows = entries(root, shards=shards)
    by_status: dict[str, int] = {}
    for e in rows:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
    fixed = [e for e in rows if e["status"] == "fixed"]
    return {
        "total": len(rows),
        "by_status": by_status,
        "fixes": len(fixed),
        "files_fixed": sum(e["files"] for e in fixed),
        "branches": len({e["branch"] for e in rows if e["branch"]}),
        "tasks": len({e["task_id"] for e in rows if e["task_id"]}),
        "escalations": by_status.get("escalated", 0),
        # Дрейф формулювань TSM. Показуємо і суму, і останній випадок: сума
        # каже «оновіть якорі», дата — «відколи саме», і без неї незрозуміло,
        # це стара разова аномалія чи вже тиждень усе повз мапу.
        # Дрейф У РОЗРІЗІ ВЕРСІЇ ДЖЕРЕЛА. Саме тут атрибуція окупається:
        # «0.9.26 — 40 запитів, 0 повз мапу; 0.9.27 — 9 запитів, 7 повз мапу»
        # читається як «оновіть мапу під новий реліз», а не як «зламалось».
        "sources": _по_джерелах(rows),
        "tsm_unknown": sum(e.get("tsm_unknown", 0) for e in rows),
        "tsm_unknown_last": next((e["ts"] for e in reversed(rows)
                                  if e.get("tsm_unknown")), ""),
        # Які саме їхні перевірки повз мапу — і скільки разів. Це і є різниця
        # між «щось зламалось» і «допиши два рядки в tsm_verdicts».
        "tsm_new": sorted(
            _count(n for e in rows for n in (e.get("tsm_new") or [])).items(),
            key=lambda kv: (-kv[1], kv[0]))[:5],
        "usd": round(sum(e["usd"] for e in rows), 4),
        "db": db.enabled(),
    }
