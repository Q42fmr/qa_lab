"""Мапа вердиктів: куди веде кожна перевірка того боку. Дані, а не код.

Навіщо переписали. До 27.08 відповідність жила таблицею якорів у
`tsm_verdicts.py` — константних початків їхніх фраз. Апстрім 0.9.26 показав
ціну такого рішення: за 16 днів **22% рядків переписано**, і покриття впало з
85% до 74% (а на новому короткому форматі — до 11%). Кожна їхня правка фрази
означала наш реліз.

Вимір на двох зрізах (`qa_lab-work/tsm-drift/`, дані зняті їхнім же `advice.py`)
назвав правильний ключ:

| що беремо за ключ | покриття 0.9.26 | ціна апгрейду |
|---|---|---|
| проза (наші якорі) | 74% | наш реліз |
| скелет рядка + схожість | 53% | 53 виклики моделі |
| **ім'я перевірки** | **92%** | **3 виклики ≈ $0.03** |

Тому ключ тут — `source:name`, а не фраза. Імена не перейменовують: за ті самі
16 днів жодне зі старих не змінилось, додались лише нові.

**Устрій — накладка, той самий, що в `ai_skills_store`.** Дефолти лежать у
коді (їдуть з релізом, покриті тестами), запис зі сховища кладеться зверху,
видалення запису повертає дефолт. Різниця одна і вона принципова: сюди пише
не лише людина, а й **модель** — на промаху вона розбирає незнайоме ім'я один
раз, і далі це вже таблиця (див. Ф4 в `qa_lab-work/notes/20-VERDICT-INGEST-PHASES.md`).

**Варіант — по ЛОГАХ, не по прозі.** У кількох їхніх перевірок гілки ведуть у
різні місця: `form` каже і «форми немає» (наш `forms`), і «не відправляється»
(`form_hijack`); `hero` — і «тема не розпізнана» (чека немає), і «віддає
заглушку» (не наше). Дискримінатор беремо з тексту логів, який пише сама
перевірка, а не з поради, яку переписує шар подачі.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

import db
import projects
import tsm_verdicts

FILE = "ai_verdicts.json"
COLLECTION_ENV = "MONGO_VERDICTS_COLL"
COLLECTION_DEFAULT = "ai_verdicts"

# Класи відповіді. Рівно ті, якими вже говорить міст, — новий клас тут
# означав би новий кінцевий стан у контракті.
CLASSES = ("ours", "not_ours", "no_check", "visual", "tool_failure", "soft")

MAX_REASON = 400
MAX_WHEN = 12
_KEY_RX = re.compile(r"^[a-z0-9_]{1,40}:[a-z0-9_]{1,40}$")
_lock = threading.Lock()


def key_for(source: str, name: str) -> str:
    src = re.sub(r"[^a-z0-9_]", "", str(source or "tsm").lower())[:40] or "tsm"
    nm = re.sub(r"[^a-z0-9_]", "", str(name or "").lower())[:40]
    return f"{src}:{nm}" if nm else ""


def _norm(s) -> str:
    return tsm_verdicts._norm(s)


# --------------------------------------------------------------------------
# Неоднозначні імена: одна перевірка — різні наслідки
# --------------------------------------------------------------------------
# Слова взяті з ЇХНІХ логів, а не з порад. Перевірено читанням їхнього коду
# (`checks/*.py` + `core/advice.py`, зріз 0.9.26): саме ці рядки пишуть самі
# перевірки, і саме на них `advice.py` розгалужує пораду.
#
# ⚠️ БАЗА ТУТ ЗАДАНА ЯВНО, І ЦЕ НЕ ПЕДАНТИЗМ. Спершу я виводив її зі списку
# якорів «за більшістю гілок» — і на `hero` та `images` дістав рівно
# протилежне тому, що треба: варіант описує ОДНУ гілку, отже база мусить бути
# її доповненням, а не найчастішим значенням. У `images` гілок узагалі
# порівну (2 наші : 2 не-наші), тобто «більшість» там була монеткою.
# Спіймано власним тестом, не на проді.
AMBIGUOUS: dict[str, dict] = {
    "form": {
        # base: форма Є, але сабміт не підтверджується. Список мусить збігатися
        # з якорем «Форма не отправляется» у `tsm_verdicts`: тут він не
        # виводиться з якорів (для неоднозначних імен база задана явно), тож
        # розійтись вони можуть тільки мовчки
        "base": {"class": "ours",
                 "php": ["forms", "form_hijack", "form_action", "form_two_step"],
                 "node": ["form_flow"]},
        "variants": [
            {"when": ["не найден"], "class": "ours",
             "php": ["forms"], "node": ["form_flow", "home_form_cta"],
             "reason": "форми немає взагалі — її треба ДОДАТИ, а не лагодити"},
        ],
    },
    "hero": {
        # base: тема сайта не розпізнана — це зміст hero-тексту, не код вітки
        "base": {"class": "no_check",
                 "reason": "тема сайта — це зміст hero-тексту, а не код вітки"},
        "variants": [
            {"when": ["ошибк", "заглушк", "404", "ответ api"],
             "class": "not_ours", "not_ours": "health",
             "reason": "головна віддає помилку/заглушку — це хостинг, "
                       "не код вітки"},
        ],
    },
    "images": {
        # base: думка vision про доречність кадру — рішення людини
        "base": {"class": "no_check",
                 "reason": "заміна фото за змістом кадру — рішення людини, "
                           "чека немає"},
        "variants": [
            {"when": ["картинок на странице нет", "битые"], "class": "ours",
             "php": ["media_integrity"], "node": [],
             "reason": "биті або відсутні картинки — це наш media_integrity"},
        ],
    },
    "hero_image": {
        "base": {"class": "no_check",
                 "reason": "думка vision про головне фото, не дефект коду"},
        "variants": [
            {"when": ["не проверено"], "class": "soft",
             "reason": "кадр не перевірено (сеть або браузер) — вердикту немає"},
        ],
    },
}

# --------------------------------------------------------------------------
# Імена, яких у зрізі 0.6.17 не було, — розібрані читанням їхнього коду 27.08
# --------------------------------------------------------------------------
# Це НЕ здогад по назві: кожен рядок нижче підпертий тим, що робить сама
# перевірка (`vendor/qa_runner/checks/*.py`).
NEW_NAMES: dict[str, dict] = {
    # links.py: «Только СВОИ ссылки (тот же домен) со статусом 4xx/5xx».
    # Це дослівно наш `link_target` (внутрішній href має вести на наявний
    # файл) плюс `empty_href`. Найцінніше з усього нового.
    "links": {"class": "ours", "php": ["link_target", "empty_href"],
              "node": [], "reason": "свої лінки в 404 — наш link_target"},
    # navdup.py: бургер-меню не ховається на десктопі, підписи повторюються.
    #   ⚠️ ТУТ Я ПОМИЛИВСЯ, А МОДЕЛЬ НІ (живий прогін 27.08). Я поставив був
    # `no_check`, судячи з НАЗВИ нашого чека: «empty_menu» звучить як
    # протилежний дефект — меню немає. Модель прочитала картку і назвала
    # `empty_menu` правильно: його докстрінг прямо описує другий випадок —
    # «мобільна шухляда на десктопі: шухляді дописали md:flex, і вона
    # розкривається стовпчиком поверх нормального меню» (кейси boigavant-br-pt,
    # peharlu-br-pt), і фікс міняє `bp:flex` на `flex`. Тобто це той самий
    # дефект, що їхній navdup, і в нас він АВТОФІКСИТЬСЯ.
    #   Це і є довід за всю конструкцію: модель бачить каталог цілком, а
    # людина — назву чека.
    "navdup": {"class": "ours", "php": ["empty_menu"], "node": [],
               "reason": "бургер-шухляда вивалилась на десктоп — другий "
                         "випадок нашого empty_menu, є автофікс"},
    # Синтезується їхнім core/runner: сервер віддає головну на будь-який шлях.
    # Це маршрутизація хостингу, а не вміст вітки.
    "pages_alias": {"class": "not_ours", "not_ours": "health",
                    "reason": "сервер віддає index на будь-який шлях — "
                              "маршрутизація, не код вітки"},
    # hygiene.py: <title>, іконка, сертифікат. НІКОЛИ не червоніє (жодного
    # `passed: False` у файлі) — усе лягає в warnings.
    # Модель на живому прогоні 27.08 запропонувала `favicon` — і це строго
    # краще за мій `soft`: жовте лишиться жовтим у будь-якому разі (це
    # вирішує `resolve` по прапорцю вердикта), а якщо гігієна колись
    # почервоніє — іконку ми справді ловимо і фіксимо.
    "hygiene": {"class": "ours", "php": ["favicon"], "node": ["favicon_link"],
                "reason": "іконку сайта ловить наш favicon; <title> і "
                          "сертифікат — ні"},
    "spellcheck": {"class": "not_ours", "not_ours": "spellcheck",
                   "reason": "орфографія — зміст, не код вітки"},
    "mobile": {"class": "visual",
               "reason": "сторінка їде вбік на телефоні — це візуальний "
                         "прогін лаби, не чек"},
    #   ДВІ ПОПРАВКИ ВІД МОДЕЛІ, ПЕРЕВІРЕНІ ЧИТАННЯМ НАШИХ ЧЕКІВ (27.08).
    # Обидві успадкувались зі старої таблиці якорів і були неточні:
    #   * `cookie_toggles` — у них це ПОВЗУНКИ КАТЕГОРІЙ на cookie-сторінці,
    #     а наш `cookie_consent` про зовсім інше: банер не ховається після
    #     «Прийняти», бо `.flex` Tailwind б'є `display:none` сторінки. Спільного
    #     лише слово «куки»;
    #   * `faq` — акордеон не розкривається: це справді дефект коду вітки, а
    #     не «не наше». Чека тоді не було; 13.10 з'явився `faq_accordion`
    #     (кейс fettmagv-ch-ch-de-2), і запис перейшов у «ours».
    "cookie_toggles": {"class": "no_check",
                       "reason": "повзунки категорій на cookie-сторінці — це "
                                 "не наш cookie_consent (той про банер, що не "
                                 "ховається після «Прийняти»); чека немає"},
    "faq": {"class": "ours", "php": ["faq_accordion"], "node": [],
            "reason": "акордеон FAQ не розкривається — мертвий JS сторінки; "
                      "ловить і лагодить faq_accordion"},
    "greencheck": {"class": "soft",
                   "reason": "другий погляд на зелений домен — завжди жовте"},
    # В `advice.py` подробиці для `images` і `hero_image` пише СПІЛЬНА гілка
    # (`name in _VISION_CHECKS`), тому в подробицях hero_image приходить під
    # фразою images — і донедавна цього вистачало. Короткий формат 15.08 їх
    # РОЗВІВ («Главная картинка не по теме сайта» окремим рядком), і без
    # власного ключа hero_image став промахом рівно на тому форматі, який
    # копіює саппорт. Спіймано гардою на корпусі, не на проді.
    "hero_image": {"class": "soft",
                   "reason": "думка vision про головне фото — привід глянути "
                             "очима, а не дефект коду"},
}


# --------------------------------------------------------------------------
# Дефолти: збираються з `tsm_verdicts.VERDICTS` + таблиці вище
# --------------------------------------------------------------------------
def _class_of(v: dict) -> str:
    for k in ("tool_failure", "visual"):
        if v.get(k):
            return k
    for k in ("not_ours", "no_check"):
        if v.get(k):
            return k
    return "ours"


def _target(v: dict) -> tuple:
    return (_class_of(v), tuple(v.get("php") or []), tuple(v.get("node") or []),
            v.get("not_ours") or "", v.get("no_check") or "")


_defaults_cache = None


def defaults() -> dict:
    """{ключ: запис}. Джерело — той самий список, що й у прозовому розборі.

    Тримати дві копії відповідності (тут і в `tsm_verdicts`) не можна: одного
    дня вони розійшлись би, і ніхто б не помітив, яка з двох діє. Тому мапа
    ВИВОДИТЬСЯ зі списку якорів, а не дублює його.
    """
    global _defaults_cache
    if _defaults_cache is not None:
        return _defaults_cache
    by_name: dict[str, list[dict]] = {}
    for v in tsm_verdicts.VERDICTS:
        by_name.setdefault(v["tsm"], []).append(v)

    out = {}
    for name, items in by_name.items():
        amb = AMBIGUOUS.get(name)
        if amb:
            b = amb["base"]
            rec = {"key": key_for("tsm", name), "class": b["class"],
                   "php": list(b.get("php") or []),
                   "node": list(b.get("node") or []),
                   "not_ours": b.get("not_ours") or "",
                   "reason": b.get("reason") or "",
                   "variants": [dict(x) for x in amb["variants"]],
                   "by": "seed", "confidence": 1.0}
            out[rec["key"]] = rec
            continue
        # Неоднозначних тут уже немає: гарда в тестах вимагає, щоб кожне ім'я
        # з розбіжними гілками лежало в AMBIGUOUS. Тому будь-який запис годиться.
        base = items[0]
        rec = {"key": key_for("tsm", name), "class": _class_of(base),
               "php": list(base.get("php") or []),
               "node": list(base.get("node") or []),
               "not_ours": base.get("not_ours") or "",
               "reason": base.get("no_check") or "",
               "variants": [], "by": "seed", "confidence": 1.0}
        out[rec["key"]] = rec

    for name, rec in NEW_NAMES.items():
        k = key_for("tsm", name)
        out[k] = {"key": k, "class": rec["class"],
                  "php": list(rec.get("php") or []),
                  "node": list(rec.get("node") or []),
                  "not_ours": rec.get("not_ours") or "",
                  "reason": rec.get("reason") or "",
                  "variants": [dict(x) for x in (AMBIGUOUS.get(name, {}).get("variants") or [])],
                  "by": "seed", "confidence": 1.0}
    _defaults_cache = out
    return out


def reset_defaults_cache() -> None:
    global _defaults_cache
    _defaults_cache = None


# --------------------------------------------------------------------------
# перевірка вводу
# --------------------------------------------------------------------------
def _ids(raw, field: str) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = re.split(r"[\s,;]+", raw)
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"{field}: очікується список id перевірок")
    out, seen = [], set()
    for x in raw:
        x = str(x).strip()
        if not x:
            continue
        if not re.match(r"^[A-Za-z0-9_]{1,64}$", x):
            raise ValueError(f"{field}: «{x[:30]}» не схоже на id перевірки")
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _when(raw) -> list[str]:
    out, seen = [], set()
    for x in (raw if isinstance(raw, (list, tuple)) else []):
        w = _norm(x)
        if w and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:MAX_WHEN]


def normalize(rec: dict) -> dict:
    """Запис, придатний до збереження. ValueError з людським текстом — його
    показує UI, тож формулювання тут частина інтерфейсу."""
    k = str(rec.get("key") or "").strip().lower()
    if not _KEY_RX.match(k):
        raise ValueError("ключ має вигляд «джерело:ім'я», напр. «tsm:links»")
    cls = str(rec.get("class") or "").strip().lower()
    if cls not in CLASSES:
        raise ValueError(f"клас: одне з {', '.join(CLASSES)}")
    php, node = _ids(rec.get("php"), "php"), _ids(rec.get("node"), "node")
    if cls == "ours" and not (php or node):
        raise ValueError("клас «ours» без жодного чека — або чеки, або інший клас")
    if cls != "ours" and (php or node):
        raise ValueError("чеки має лише клас «ours»")
    variants = []
    for v in (rec.get("variants") or []):
        vc = str(v.get("class") or cls).strip().lower()
        if vc not in CLASSES:
            raise ValueError(f"варіант: клас {vc} невідомий")
        w = _when(v.get("when"))
        if not w:
            raise ValueError("варіант без «when» не спрацює ніколи")
        variants.append({"when": w, "class": vc,
                         "php": _ids(v.get("php"), "варіант php"),
                         "node": _ids(v.get("node"), "варіант node"),
                         "not_ours": str(v.get("not_ours") or "").strip(),
                         "reason": " ".join(str(v.get("reason") or "").split())[:MAX_REASON]})
    return {"key": k, "class": cls, "php": php, "node": node,
            "not_ours": str(rec.get("not_ours") or "").strip(),
            "reason": " ".join(str(rec.get("reason") or "").split())[:MAX_REASON],
            "variants": variants,
            "by": str(rec.get("by") or "human").strip().lower(),
            "confidence": float(rec.get("confidence") or 1.0),
            "catalogue": str(rec.get("catalogue") or "").strip()[:64],
            "active": rec.get("active", True) is not False}


# --------------------------------------------------------------------------
# бекенди — той самий вибір, що в users.py і ai_skills_store
# --------------------------------------------------------------------------
def collection_name() -> str:
    return os.getenv(COLLECTION_ENV, COLLECTION_DEFAULT).strip() or COLLECTION_DEFAULT


def store_kind() -> str:
    return "mongo" if db.enabled() else "file"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class _FileStore:
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

    def get(self, k: str):
        return self._read().get(k)

    def put(self, rec: dict) -> dict:
        with _lock:
            data = self._read()
            old = data.get(rec["key"]) or {}
            rec = {**rec, "stats": old.get("stats") or {},
                   "created_at": old.get("created_at") or _now(),
                   "updated_at": _now()}
            data[rec["key"]] = rec
            self._write(data)
            return rec

    def delete(self, k: str) -> bool:
        with _lock:
            data = self._read()
            if k not in data:
                return False
            data.pop(k)
            self._write(data)
            return True

    def bump(self, k: str, field: str, n: int = 1):
        with _lock:
            data = self._read()
            rec = data.get(k)
            if rec is None:
                #   ЗАПИС ЛИШЕ ЗАРАДИ ЛІЧИЛЬНИКА. Дефолти живуть у коді, а не
                # у сховищі, тож до 27.08 `bump` по них мовчки не робив
                # НІЧОГО — і метрика «кликали, а не спрацювало» була порожня
                # рівно для тих записів, якими все й роутиться. Спіймано
                # локальним стендом: 26 сценаріїв, лічильників нуль.
                #   `stats_only` каже, що це не правка мапи: накладати такий
                # запис поверх дефолта не можна, з нього беруться лише
                # лічильники.
                rec = data[k] = {"key": k, "stats_only": True, "stats": {}}
            st = rec.setdefault("stats", {})
            st[field] = int(st.get(field) or 0) + n
            st["last"] = _now()
            self._write(data)
            return rec


class _MongoStore:
    def __init__(self, coll):
        from pymongo import ASCENDING
        self.coll = coll
        self.coll.create_index([("key", ASCENDING)], unique=True)

    def _clean(self, d):
        return {k: v for k, v in d.items() if k != "_id"} if d else None

    def all(self) -> dict:
        return {d["key"]: self._clean(d) for d in self.coll.find()}

    def get(self, k: str):
        return self._clean(self.coll.find_one({"key": k}))

    def put(self, rec: dict) -> dict:
        rec = dict(rec)
        rec["updated_at"] = _now()
        self.coll.update_one({"key": rec["key"]},
                             {"$set": rec, "$setOnInsert": {"created_at": _now()}},
                             upsert=True)
        return self.get(rec["key"]) or rec

    def delete(self, k: str) -> bool:
        return self.coll.delete_one({"key": k}).deleted_count > 0

    def bump(self, k: str, field: str, n: int = 1):
        # upsert — з тієї ж причини, що у файловому сховищі: дефолт лежить у
        # коді, і без створення запису лічильник нікуди б не подівся.
        self.coll.update_one({"key": k},
                             {"$inc": {f"stats.{field}": n},
                              "$set": {"stats.last": _now()},
                              "$setOnInsert": {"stats_only": True}},
                             upsert=True)
        return self.get(k)


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
    reset_defaults_cache()


# --------------------------------------------------------------------------
# API модуля
# --------------------------------------------------------------------------
def overlay() -> dict:
    try:
        return store().all()
    except Exception as e:
        # Сховище не має валити роутинг: без нього мапа працює на дефолтах,
        # тобто рівно як до появи накладки.
        print(f"[ai] мапа вердиктів зі сховища не прочиталась: {e}")
        return {}


def all_entries() -> dict:
    """Дефолти з коду + накладка зі сховища зверху.

    ⚠️ Запис із `stats_only` — НЕ накладка, а лише лічильники: він з'являється
    сам, коли роутер порахував дефолтний запис. Класти його зверху означало б
    стерти дефолт порожнім записом, тобто зламати роутинг рівно тим, що ми
    почали міряти його якість.
    """
    out = {k: dict(v) for k, v in defaults().items()}
    for k, rec in overlay().items():
        if rec.get("stats_only"):
            if k in out:
                out[k]["stats"] = rec.get("stats") or {}
            continue
        if rec.get("active") is False:
            out.pop(k, None)
            continue
        out[k] = dict(rec)
    return out


def get(k: str):
    return all_entries().get(str(k or "").strip().lower())


def save(rec: dict, author: str = "") -> dict:
    clean = normalize(rec)
    clean["stats_only"] = False        # це вже правка мапи, а не лічильник
    if author:
        clean["author"] = author
    return store().put(clean)


def delete(k: str) -> bool:
    """Прибирає ЗАПИС накладки. Для ключа з дефолтом це «скасувати правку»."""
    return store().delete(str(k or "").strip().lower())


def bump(k: str, field: str, n: int = 1):
    """Лічильник на записі: `routed` — скільки разів мапа його обрала,
    `fired` — скільки разів обране справді побачило дефект.

    Це і є найдешевша метрика якості мапи: запис, який роутер кличе
    постійно, а він жодного разу не спрацював, — або хибний, або ім'я
    склеїло два різні дефекти (тоді йому потрібен варіант).
    """
    try:
        return store().bump(str(k or "").strip().lower(), field, n)
    except Exception as e:
        print(f"[ai] лічильник мапи не оновився: {e}")
        return None


def catalogue_hash(cards) -> str:
    """Відбиток каталогу, під який дана відповідь моделі.

    Навіщо. Запис, вивчений моделлю, ЗАМОРОЖУЄ відповідь: додали ми потім
    новий чек — старий запис його ніколи не обере, бо нікого не питає. Це
    класична пастка кешу, і єдиний спосіб її побачити — памʼятати, при якому
    каталозі відповідь дана. Рахуємо по id, не по текстах карток: правка
    формулювання симптому не привід перевчати мапу.
    """
    import hashlib
    ids = sorted(str(c.get("id") or "") for c in (cards or []))
    return hashlib.sha1("|".join(ids).encode("utf-8")).hexdigest()[:16]


def stale(cards) -> list[dict]:
    """Записи, вивчені моделлю при ІНШОМУ каталозі. Показуємо на /ai.

    Автоматично не перевчаємо: буря перезапитів на кожну зміну каталогу
    коштувала б рівно те, від чого ми тікали. Рішення лишається людині,
    а зворотний звʼязок (`routed` без `fired`) сам показує, які записи
    справді зіпсувались.
    """
    now = catalogue_hash(cards)
    return [r for r in all_entries().values()
            if r.get("by") == "model" and r.get("catalogue")
            and r.get("catalogue") != now]


def _pick_variant(rec: dict, haystack: str):
    for v in rec.get("variants") or []:
        for w in v.get("when") or []:
            if w and w in haystack:
                return v
    return None


def resolve(verdict: dict, available=(), source: str = "") -> dict | None:
    """Вердикт → відповідь мапи. None — імені не знаємо (далі прозовий шлях).

    `available` — id з КАТАЛОГУ поточного проєкту, тобто вже відфільтровані і
    за типом (php/node), і за вимкненими скілами. Звужуємо до нього завжди:
    інакше мапа стала б дірою в правилі «вимкнений скіл ховає чек».

    `source` приходить з конверта (`tsm_ingest.ingest`), бо джерело — це
    властивість запиту, а не окремого вердикту. Другий постачальник вердиктів
    заходить сюди зі своїм простором імен і нічого не ламає.
    """
    name = str((verdict or {}).get("name") or "").strip().lower()
    if not name:
        return None
    src = str(source or (verdict or {}).get("source") or "tsm")
    rec = all_entries().get(key_for(src, name))
    if rec is None:
        return None
    hay = _norm(" ".join(list(verdict.get("logs") or []) + [verdict.get("line") or ""]))
    var = _pick_variant(rec, hay)
    src_rec = {**rec, **(var or {})}
    cls = src_rec.get("class") or rec.get("class")
    # Жовте не роутиться ніколи — ні з мапи, ні звідки б то не було.
    if verdict.get("soft"):
        cls = "soft"
    ids = set(available)
    checks = [c for c in (list(src_rec.get("php") or []) + list(src_rec.get("node") or []))
              if c in ids]
    return {"key": rec["key"], "name": name, "class": cls,
            "checks": checks if cls == "ours" else [],
            "not_ours": src_rec.get("not_ours") or "",
            "reason": src_rec.get("reason") or "",
            "variant": bool(var), "by": rec.get("by", "seed"),
            "confidence": rec.get("confidence", 1.0),
            "page": verdict.get("page", ""), "soft": bool(verdict.get("soft"))}


def outcome(verdicts: list, available=(), source: str = "") -> dict:
    """Підсумок по всьому конверту: що запускати і що сказати людині.

    Порядок важливий: **збій їхньої тули б'є все інше.** Якщо прогін TSM
    зірвався, то червоне, що стоїть після нього, стосується недоперевіреної
    сторінки — у їхньому ж коментарі до `page_guard` так і написано:
    «вердикты, идущие после этого места, относятся к ЧУЖОЙ странице».
    """
    seen, checks = set(), []
    hit, unknown = [], []
    for v in (verdicts or []):
        r = resolve(v, available, source)
        if r is None:
            unknown.append(v)
            continue
        hit.append(r)
        if r["class"] == "ours":
            for c in r["checks"]:
                if c not in seen:
                    seen.add(c)
                    checks.append(c)
    return {
        "tool_failure": [r for r in hit if r["class"] == "tool_failure"],
        "checks": checks,
        "hits": hit,
        "not_ours": [r for r in hit if r["class"] == "not_ours"],
        "no_check": [r for r in hit if r["class"] == "no_check"],
        "visual": [r for r in hit if r["class"] == "visual"],
        "soft": [r for r in hit if r["class"] == "soft"],
        "unknown": unknown,
    }
