"""Сховище скілів: те, що користувач править руками через UI.

Навіщо. Спершу картки скілів жили ЛИШЕ у словнику `SKILLS` в `ai_skills.py`.
Це працює, доки набір чеків стабільний, але чеки дописуються, і кожен новий
скіл означав би правку коду, коміт і деплой — заради одного рядка синонімів.
Тут ті самі картки лежать даними, які можна завести з вкладки.

**Накладка, а не заміна.** Вбудовані картки в коді лишаються — вони і є
дефолт. Запис у сховищі кладеться ЗВЕРХУ:

    немає запису        -> вбудована картка (або авто-картка з NAME чека)
    запис active=true   -> перекриває вбудовану
    запис active=false  -> чек НЕ потрапляє в каталог узагалі

Останнє і є вимога «ШІ працює тільки з активними скілами»: вимкнений скіл
не показується моделі, тож вона не може обрати цей чек. Сам чек при цьому
живий — його, як і раніше, запускає людина з вкладки перевірок.

Чому накладка, а не «злити все в базу один раз»: вбудовані картки їдуть
разом з кодом і покращуються разом із чеками, а видалення свого запису
повертає дефолт — тобто «скасувати правку» безкоштовне.

**Де лежить.** Той самий вибір, що в `users.py`: колекція в Mongo, коли
заданий `MONGO_URI`, інакше json у корені стану. Лаба мусить лишатись
робочою без бази — це її давній контракт, і скіли не привід його ламати.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

import db
import projects

FILE = "ai_skills.json"
COLLECTION_ENV = "MONGO_SKILLS_COLL"
COLLECTION_DEFAULT = "ai_skills"

# Поля картки, які користувач може задати. Решта (група, тип проєкту,
# наявність автофікса) береться з САМОГО ЧЕКА і правці не підлягає: це
# факти про код, а не думка про нього.
FIELDS = ("симптом", "слова", "не про це", "лагодить")

# Межі. Не про красу: картка йде в промпт моделі, і нічим не обмежений
# текст з UI роздув би його до непристойного разом з ціною запиту.
MAX_SYMPTOM = 300
MAX_FIX = 300
MAX_WORD = 60
MAX_WORDS = 200

_ID_RX = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_lock = threading.Lock()


def collection_name() -> str:
    return os.getenv(COLLECTION_ENV, COLLECTION_DEFAULT).strip() or COLLECTION_DEFAULT


def store_kind() -> str:
    return "mongo" if db.enabled() else "file"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# перевірка вводу
# --------------------------------------------------------------------------
def _words(raw, field: str) -> list[str]:
    """Список слів: чистить, ріже порожні, знімає дублі зі збереженням порядку.

    Порядок зберігаємо навмисно — людина пише спершу головні слова, і в UI
    вони мають лишитись там, де їх поставили.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = re.split(r"[\n,;]+", raw)
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"{field}: очікується список або текст через кому")
    out, seen = [], set()
    for w in raw:
        w = " ".join(str(w).split()).lower()
        if not w:
            continue
        if len(w) > MAX_WORD:
            raise ValueError(f"{field}: «{w[:30]}…» довше за {MAX_WORD} символів")
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
    if len(out) > MAX_WORDS:
        raise ValueError(f"{field}: більше за {MAX_WORDS} значень")
    return out


def normalize(rec: dict) -> dict:
    """Запис, придатний до збереження. Кидає ValueError з людським текстом —
    його показує UI, тому формулювання тут частина інтерфейсу."""
    cid = str(rec.get("check_id") or "").strip()
    if not _ID_RX.match(cid):
        raise ValueError("id перевірки: лише латиниця, цифри і підкреслення")
    symptom = " ".join(str(rec.get("симптом") or "").split())
    if not symptom:
        raise ValueError("симптом обов'язковий: це те, що модель читає про чек")
    if len(symptom) > MAX_SYMPTOM:
        raise ValueError(f"симптом довший за {MAX_SYMPTOM} символів")
    fix = " ".join(str(rec.get("лагодить") or "").split())[:MAX_FIX]
    return {
        "check_id": cid,
        "симптом": symptom,
        "слова": _words(rec.get("слова"), "слова"),
        "не про це": _words(rec.get("не про це"), "не про це"),
        "лагодить": fix,
        "active": rec.get("active", True) is not False,
    }


# --------------------------------------------------------------------------
# бекенди
# --------------------------------------------------------------------------
class _FileStore:
    """json у корені стану. Запис — під локом, читання — цілим файлом:
    карток десятки, не тисячі."""

    def __init__(self, path):
        self.path = path

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, self.path)

    def all(self) -> dict:
        return self._read()

    def get(self, cid: str):
        return self._read().get(cid)

    def put(self, rec: dict) -> dict:
        with _lock:
            data = self._read()
            old = data.get(rec["check_id"]) or {}
            rec = {**rec, "created_at": old.get("created_at") or _now(),
                   "updated_at": _now()}
            data[rec["check_id"]] = rec
            self._write(data)
            return rec

    def delete(self, cid: str) -> bool:
        with _lock:
            data = self._read()
            if cid not in data:
                return False
            data.pop(cid)
            self._write(data)
            return True


class _MongoStore:
    """Колекція в тій самій базі, що й користувачі. Унікальний індекс по
    check_id: одна картка на чек, інакше «яка з двох діє» стало б лотереєю."""

    def __init__(self, coll):
        from pymongo import ASCENDING
        self.coll = coll
        self.coll.create_index([("check_id", ASCENDING)], unique=True)

    def all(self) -> dict:
        return {d["check_id"]: {k: v for k, v in d.items() if k != "_id"}
                for d in self.coll.find()}

    def get(self, cid: str):
        d = self.coll.find_one({"check_id": cid})
        return {k: v for k, v in d.items() if k != "_id"} if d else None

    def put(self, rec: dict) -> dict:
        rec = dict(rec)
        rec["updated_at"] = _now()
        self.coll.update_one({"check_id": rec["check_id"]},
                             {"$set": rec, "$setOnInsert": {"created_at": _now()}},
                             upsert=True)
        return self.get(rec["check_id"]) or rec

    def delete(self, cid: str) -> bool:
        return self.coll.delete_one({"check_id": cid}).deleted_count > 0


_store = None
_store_lock = threading.Lock()


def store():
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                coll = db.collection(collection_name())
                _store = (_MongoStore(coll) if coll is not None
                          else _FileStore(projects.state_root() / FILE))
    return _store


def reset_for_tests(new=None) -> None:
    global _store
    with _store_lock:
        _store = new


# --------------------------------------------------------------------------
# API модуля
# --------------------------------------------------------------------------
def all_skills() -> dict:
    """{check_id: запис}. Порожньо — працюють самі вбудовані картки."""
    try:
        return store().all()
    except Exception as e:
        # Сховище скілів не має валити роутинг: без нього міст працює на
        # вбудованих картках, тобто рівно як до появи цієї вкладки.
        print(f"[ai] скіли зі сховища не прочитались: {e}")
        return {}


def get(check_id: str):
    return store().get(check_id)


def save(rec: dict, author: str = "") -> dict:
    clean = normalize(rec)
    if author:
        clean["author"] = author
    return store().put(clean)


def delete(check_id: str) -> bool:
    """Прибирає ЗАПИС. Для чека з вбудованою карткою це «скасувати правку»:
    далі знову діє дефолт з коду."""
    return store().delete(str(check_id).strip())


def set_active(check_id: str, active: bool):
    cid = str(check_id).strip()
    rec = get(cid)
    if rec is None:
        return None
    rec["active"] = bool(active)
    return store().put(normalize(rec))
