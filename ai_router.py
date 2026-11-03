"""Роутер: з прози — набір тестів, які варто прогнати.

Механізм навмисно триступеневий, і ступені дають РІЗНЕ.

**1. Детермінований скорер (`rank`)** — слова з карток скілів проти тексту.
Дешевий, офлайновий, пояснюваний: у журнал лягає не «модель так вирішила»,
а конкретні слова, що збіглись. Він же фолбек, коли Claude недоступний, і
він же база для виміру — інакше не відповісти, чи модель узагалі краща за
`if "лого" in text`.

**2. Claude (`ask_model`)** — арбітр. Отримує ВЕСЬ доречний каталог (26
карток для php, ~10 для node — близько тисячі токенів) і текст скарги.
Свідомо не шорт-лист від скорера: шорт-лист міг би відрізати правильний
чек, і модель не мала б шансу це виправити.

**3. Докази (не тут — у `ai_bridge`)** — і це головне. Роутер працює
**на повноту, а не на точність**: його задача — не проґавити потрібний чек,
а не вгадати єдиний. Точність дає наступний крок: кандидати РЕАЛЬНО
ганяються по знімку (чек коштує мілісекунди), і далі в роботу йдуть тільки
ті, що справді спрацювали. Тому найгірша ціна помилки роутингу — зайвий
прогін кількох чеків, а не поганий коміт.

Контракт на збій — той самий, що в клієнта Claude у TSM: **назовні винятків
не кидаємо**. Немає ключа, скінчився бюджет, 429, таймаут, крива відповідь —
міст мусить лишитись робочим на самих словах.

Виклик — звичайний HTTPS POST через `requests`, без SDK `anthropic`:
конвенція репозиторію «жодних нових залежностей», а `requests` тут з
першого дня.
"""
from __future__ import annotations

import json
import os
import threading
import time

import requests

import ai_skills
import tsm_ingest
import tsm_verdicts
import verdict_map


def _merge(first: list, second: list) -> list:
    """Об'єднання зі збереженням порядку: точні вердикти попереду здогадок."""
    out = list(first)
    out += [x for x in second if x not in out]
    return out

# --------------------------------------------------------------------------
# 1. Детермінований скорер
# --------------------------------------------------------------------------
# Ваги підібрані під одну вимогу: НЕ ПРОҐАВИТИ. Тому поріг низький (одне
# влучне слово вже робить чек кандидатом), а негативи важать утричі — саме
# вони розводять пʼять «лого»-чеків, і помилка тут коштує дорожче за зайвий
# кандидат.
W_WORD = 1.0        # одне слово
W_PHRASE = 2.0      # фраза з пробілом — специфічніша за слово
W_ANTI = -3.0       # «не про це»
W_FIXABLE = 0.4     # за інших рівних — той, що вміє лагодити
W_HISTORY = 1.5     # цей чек уже спрацьовував на цій вітці
THRESHOLD = 1.0
MAX_CANDIDATES = 8  # ширше немає сенсу: далі все одно фільтрують докази


def rank(text: str, cards: list[dict], history=()) -> list[dict]:
    """Картки, впорядковані за схожістю на текст скарги.

    `history` — id чеків, що вже давали error на цій вітці (з `checks_ledger`).
    Це не здогадка, а факт: вітка з трьома фіксами `logo_domain` в анамнезі
    імовірніше прийшла з ним же вчетверте.
    """
    hist = set(history or ())
    out = []
    for c in cards:
        hits = ai_skills.match_words(text, c["слова"])
        anti = ai_skills.match_words(text, c["не про це"])
        score = sum(W_PHRASE if " " in h else W_WORD for h in hits)
        score += W_ANTI * len(anti)
        if score > 0:
            if c["fixable"]:
                score += W_FIXABLE
            if c["id"] in hist:
                score += W_HISTORY
        out.append({"id": c["id"], "score": round(score, 2),
                    "hits": hits, "anti": anti,
                    "fixable": c["fixable"], "group": c["group"]})
    out.sort(key=lambda x: (-x["score"], x["id"]))
    return out


def by_keywords(text: str, cards: list[dict], history=()) -> tuple[list[str], list[dict]]:
    """Відповідь самими словами: (id чеків, повний ранг для журналу)."""
    ranked = rank(text, cards, history)
    picked = [r["id"] for r in ranked if r["score"] >= THRESHOLD][:MAX_CANDIDATES]
    return picked, ranked


# --------------------------------------------------------------------------
# 2. Claude
# --------------------------------------------------------------------------
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Ціни $/1M токенів. Тримаємо ТАБЛИЦЕЮ ПО МОДЕЛІ: якщо колись перемкнути
# модель змінною, а ціну лишити константою, лічильник витрат почне брехати —
# і саме він потім пояснює, куди пішли кредити.
PRICES = {
    "claude-opus-5":   (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Схема відповіді. `strict` + `additionalProperties: false` роблять розбір
# передбачуваним: модель не може дописати поле і не може віддати прозу
# замість json.
TOOL = {
    "name": "route_to_checks",
    "description": "Повертає перелік перевірок лаби, які варто прогнати "
                   "по описаній проблемі.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "checks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "id перевірок з каталогу, від найімовірнішої. "
                               "Порожній масив — якщо жодна не підходить.",
            },
            "not_ours": {
                "type": "boolean",
                "description": "true, якщо проблема в принципі не лікується "
                               "з коду гілки (репутація домену, хостинг, "
                               "ціни, орфографія).",
            },
            "confidence": {
                "type": "number",
                "description": "0..1 — наскільки впевнено визначено проблему.",
            },
            "reason": {
                "type": "string",
                "description": "Одне-два речення українською: чому саме ці "
                               "перевірки.",
            },
        },
        "required": ["checks", "not_ours", "confidence", "reason"],
        "additionalProperties": False,
    },
}

SYSTEM = """\
Ти — маршрутизатор технічної підтримки. Тобі приходить скарга на «вайт»
(односторінковий сайт-візитівка) з ЖИВОГО домену, написана прозою і зазвичай
російською або українською. Твоя робота — вибрати з каталогу перевірок ті,
що варто прогнати по коду гілки цього вайта.

Контекст: це внутрішній QA-верстак компанії, якій ці сторінки належать.
Перевірки в каталозі — ДЕТЕКТОРИ дефектів: кожна шукає поломку у власному
коді компанії, щоб лаба її виправила або прибрала. Тому картка описує саме
ту поломку, яку треба знайти і усунути.

Правила:
1. Обирай на ПОВНОТУ, а не на точність. Далі ці перевірки реально
   запустяться по коду, і ті, що не спрацюють, відпадуть самі. Проґавити
   потрібну перевірку дорого, зайва — майже безкоштовна.
2. Але не вивалюй увесь каталог: 1-5 перевірок, які справді пояснюють скаргу.
   Повнота — про ОПИСАНУ проблему, а не про «заразом перевіримо ще й це».
   Кожна перевірка, прогнана на цій вітці, іде в лічильник кіл: два кола по
   одному й тому самому — і лаба зупиниться та покличе людину. Зайвий чек
   «про всяк випадок» витрачає це право за чужу скаргу.
3. Бери id ЛИШЕ з каталогу нижче, дослівно. Нічого не вигадуй.
4. Якщо проблема не лікується з коду гілки — репутація домену в Google,
   недоступний хостинг, ціни, орфографія, зміст текстів — постав
   not_ours=true і лиши checks порожнім.
5. Скарга може описувати кілька різних поломок — тоді бери перевірки під
   кожну.

Каталог перевірок. Кожна: id, симптом людською мовою, «шукає» — що саме
перевірка робить з кодом, і «не плутати з» — сусідні перевірки та випадки,
які цією НЕ ловляться. Останній рядок читай уважно: половина каталогу
описує схожі поломки, і розводить їх саме він.

{catalog}

Розібрані приклади (скарга -> що обрати):
{examples}
"""

# Мертвий Claude не має змушувати кожен виклик платити повний мережевий
# таймаут — той самий клас граблів, що лікували в TSM. Серія збоїв зводить
# кулдаун, успіх його знімає.
_state = {"fails": 0, "until": 0.0}
_lock = threading.Lock()
COOLDOWN_STEPS = [0, 30, 120, 600]     # секунди після 1/2/3+ збоїв
# Скільки НОВИХ імен розбираємо за один запит. Стеля не про ціну, а про
# те, що буря незнайомих імен означає зміну на їхньому боці — її треба
# побачити на /ai, а не мовчки вивчити всю пачку одним махом.
MAX_LEARN_AT_ONCE = 5


def model_name() -> str:
    return os.getenv("AI_MODEL", "claude-opus-5").strip() or "claude-opus-5"


def api_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "").strip()


def available() -> tuple[bool, str]:
    """(чи можна кликати, причина якщо ні). Причину віддаємо назовні —
    «роутер працює на словах» без пояснення виглядає як мовчазна деградація."""
    if not api_key():
        return False, "ANTHROPIC_API_KEY не заданий"
    with _lock:
        left = _state["until"] - time.time()
    if left > 0:
        return False, f"кулдаун після збоїв, ще {int(left)} с"
    return True, ""


def _note_failure():
    with _lock:
        _state["fails"] += 1
        step = COOLDOWN_STEPS[min(_state["fails"], len(COOLDOWN_STEPS) - 1)]
        _state["until"] = time.time() + step


def _note_success():
    with _lock:
        _state["fails"] = 0
        _state["until"] = 0.0


def reset_for_tests():
    with _lock:
        _state["fails"] = 0
        _state["until"] = 0.0


def _usd(model: str, usage: dict) -> float:
    inp, out = PRICES.get(model, PRICES["claude-opus-5"])
    # Записані в кеш токени коштують ~1.25×, читані з кешу ~0.1×. Каталог
    # у system однаковий для всіх запитів, тож із другого запиту він
    # читається з кешу — без цих двох доданків лічильник завищував би.
    tin = usage.get("input_tokens", 0)
    tcw = usage.get("cache_creation_input_tokens", 0)
    tcr = usage.get("cache_read_input_tokens", 0)
    tout = usage.get("output_tokens", 0)
    return round((tin * inp + tcw * inp * 1.25 + tcr * inp * 0.1
                  + tout * out) / 1_000_000, 6)


def _post(body: dict, tool_name: str, timeout: int = 60) -> tuple:
    """HTTP до Claude + розбір службової частини відповіді. `(out, payload)`.

    Винесено з `ask_model`, бо викликів тепер два: маршрутизація скарги і
    розбір НЕЗНАЙОМОГО ІМЕНІ перевірки. Мережа, ціна, кулдаун і — головне —
    обробка відмови в них однакові, а дублювати обробку відмови означало б
    одного дня полагодити її в одному місці з двох.
    """
    model = str(body.get("model") or model_name())
    started = time.time()
    try:
        r = requests.post(API_URL, timeout=timeout,
                          headers={"x-api-key": api_key(),
                                   "anthropic-version": API_VERSION,
                                   "anthropic-beta": FALLBACK_BETA,
                                   "content-type": "application/json"},
                          json=body)
        if r.status_code != 200:
            _note_failure()
            # ГОВОРИМО ВГОЛОС. Збій одного виклику зводить кулдаун, і далі
            # мовчки не спрацьовує РОЗБІР НОВОГО ІМЕНІ — а він, на відміну
            # від роутингу, фолбека не має: мапа просто не росте. Локальний
            # стенд показав рівно це: «alt_text бачимо вперше, а розібрати
            # не вдалось (кулдаун після збоїв)» — і причини збою ніде.
            print(f"[ai] Claude відповів HTTP {r.status_code}: {r.text[:200]}")
            return {"error": f"HTTP {r.status_code}: {r.text[:200]}",
                    "checks": None}, None
        data = r.json()
    except Exception as e:
        _note_failure()
        print(f"[ai] Claude не відповів: {type(e).__name__}: {e}")
        return {"error": f"{type(e).__name__}: {e}", "checks": None}, None

    usage = data.get("usage") or {}
    served = str(data.get("model") or model)
    out = {
        "model": served,
        "asked_model": model,
        "usd": _usd(served, usage),
        "tokens": {"in": usage.get("input_tokens", 0),
                   "out": usage.get("output_tokens", 0),
                   "cache_read": usage.get("cache_read_input_tokens", 0)},
        "ms": int((time.time() - started) * 1000),
        "checks": None,
        "error": "",
    }
    # Модель могла відмовитись відповідати — це HTTP 200 зі stop_reason
    # "refusal", а не виняток. Без перевірки нижче ми б розбирали порожній
    # content і рапортували «модель нічого не обрала».
    if data.get("stop_reason") == "refusal":
        _note_failure()
        # Категорію віддаємо назовні дослівно: вона єдина каже, ЩО саме
        # спрацювало, а без неї відмова невідрізнима від будь-якого іншого
        # збою. На першому ж бойовому прогоні 25.08 відмовляв не текст
        # скарги, а наш власний каталог: картки `form_hijack` і
        # `partner_banks` описували дефект з боку атаки, і класифікатор
        # `cyber` читав каталог як інструкцію. Без цього поля пошук
        # причини почався б з ключа й моделі.
        det = data.get("stop_details") or {}
        cat = det.get("category") or "?"
        out["error"] = f"модель відмовилась відповідати (refusal, {cat})"
        out["refusal"] = {"category": cat,
                          "explanation": str(det.get("explanation") or "")[:300]}
        return out, None

    payload = None
    for block in data.get("content") or []:
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            payload = block.get("input") or {}
            break
    if payload is None:
        _note_failure()
        out["error"] = "у відповіді немає блока tool_use"
        return out, None
    _note_success()
    return out, payload


def ask_model(text: str, cards: list[dict], timeout: int = 60,
              rich: bool = True) -> dict:
    """Один виклик Claude. НІКОЛИ не кидає — усе, що пішло не так, лягає
    в поле `error`, а викликач з'їжджає на слова.

    `rich` керує формою каталогу (`ai_skills.render_for_model`). Параметр
    існує рівно заради виміру «до/після» на корпусі: у бойовому шляху він
    завжди дефолтний, перемикає його тільки `qa_lab-work/ai-ab.py`.
    """
    # Порожній текст — це не «модель не змогла», а НАША помилка виклику, і
    # перевіряти її треба ПЕРШОЮ: інакше без ключа ми відрапортуємо «немає
    # ключа» і сховаємо власну ваду. API на такий запит відповідає
    # `400 user messages must have non-empty content`, а 400 зводить кулдаун
    # і глушить сусідні шляхи — зокрема розбір нового імені.
    if not (text or "").strip():
        return {"error": "порожній текст — модель не питаємо", "checks": None}
    ok, why = available()
    if not ok:
        return {"error": why, "checks": None}

    model = model_name()
    body = {
        "model": model,
        "max_tokens": 3000,
        # Мислення на Opus 5 увімкнене за замовчуванням, і вимикати його тут
        # не можна: з вимкненим модель час від часу пише виклик інструмента
        # у видимий текст замість блока tool_use — тобто маршрутизація тихо
        # не відбувається. Дешевше і безпечніше лишити адаптивне мислення
        # і збити глибину через effort.
        "output_config": {"effort": "low"},
        "system": [{
            "type": "text",
            "text": SYSTEM.format(
                catalog=ai_skills.render_for_model(cards, rich=rich),
                # Приклад із чеком, якого немає в ЦЬОМУ каталозі (інший тип
                # проєкту або знятий чек), не показуємо: він учив би модель
                # називати id, який ми потім мовчки викинемо в `dropped`.
                examples=ai_skills.render_examples({c["id"] for c in cards})
                if rich else ""),
            # Каталог однаковий від запиту до запиту, скарга — ні. Саме та
            # форма, під яку зроблено кешування префікса.
            "cache_control": {"type": "ephemeral"},
        }],
        "messages": [{"role": "user", "content": text[:4000]}],
        "tools": [TOOL],
        "tool_choice": {"type": "tool", "name": TOOL["name"]},
        # Страховка від відмови класифікатора. Каталог перевірок описує
        # поломки, які лаба лікує — зокрема перехоплення форми і чужий блок
        # банків, — і на прогоні 25.08 класифікатор `cyber` прочитав дві
        # такі картки як інструкцію до атаки. Повний каталог після
        # переписування карток проходить, але запас тонкий: вимкнені з UI
        # скіли роблять каталог коротшим, а в короткому ця тема важить
        # більше. `"default"` перекладає такий запит на іншу модель за
        # категорією відмови — без списку моделей, який довелось би вести
        # руками. Не спрацювало — нижче все одно є з'їзд на слова.
        "fallbacks": "default",
    }
    out, payload = _post(body, TOOL["name"], timeout)
    if payload is None:
        return out

    out["checks"] = [str(x) for x in (payload.get("checks") or [])]
    out["not_ours"] = bool(payload.get("not_ours"))
    out["confidence"] = float(payload.get("confidence") or 0)
    out["reason"] = str(payload.get("reason") or "")[:500]
    return out


# --------------------------------------------------------------------------
# 2b. Модель добудовує мапу вердиктів
# --------------------------------------------------------------------------
# Це і є та зміна ролей, заради якої все переписувалось: раніше таблицю
# «їхня перевірка -> наші чеки» вела людина, а модель гадала на льоту при
# кожній скарзі. Тепер навпаки — модель розбирає НЕЗНАЙОМЕ ІМʼЯ один раз,
# відповідь лягає в мапу, і далі це звичайна таблиця: мікросекунди і нуль
# доларів.
#
# Ціна питання, заміряна на двох зрізах TSM: апгрейд 0.6.17 -> 0.9.26 дав три
# нових імені, тобто ТРИ виклики на весь реліз (~$0.03) замість 53, якби ми
# кешували прозу, і замість сотень, якби питали модель на кожну скаргу.
LEARN_TOOL = {
    "name": "map_tsm_check",
    "description": "Каже, що лаба може зробити з дефектом, який знайшла "
                   "чужа перевірка.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "entries": {
                "type": "array",
                "description": "По одному запису на кожну названу перевірку.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string",
                                 "description": "ім'я чужої перевірки, "
                                                "дослівно як дано"},
                        "class": {
                            "type": "string",
                            "enum": ["ours", "not_ours", "no_check",
                                     "visual", "tool_failure", "soft"],
                            "description": (
                                "ours — лікується нашими перевірками; "
                                "not_ours — не лікується з коду гілки "
                                "(домен, хостинг, зміст); "
                                "no_check — це дефект коду, але потрібної "
                                "перевірки в лабі немає; "
                                "visual — це бачить візуальний прогін, не чек; "
                                "tool_failure — зламалась їхня тула, а не сайт; "
                                "soft — це не дефект, а привід глянути очима"),
                        },
                        "checks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "id з каталогу, лише для «ours». "
                                           "Дослівно, нічого не вигадувати.",
                        },
                        "not_ours": {
                            "type": "string",
                            "description": "лише для «not_ours»: id класу "
                                           "зі списку «що лаба не вміє».",
                        },
                        "reason": {"type": "string",
                                   "description": "одне речення українською: "
                                                  "чому саме так"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["name", "class", "checks", "not_ours",
                                 "reason", "confidence"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["entries"],
        "additionalProperties": False,
    },
}

LEARN_SYSTEM = """\
Ти розбираєш стик двох інструментів якості, що належать одній компанії.

ІНШИЙ інструмент (TSM) перевіряє ЖИВИЙ домен зовні: відкриває сторінки
браузером і пише вердикти. НАША лаба працює з ВИХІДНИМ КОДОМ гілки, з якої
цей сайт зібрано, — і вміє не тільки знайти, а й полагодити та закомітити.

Тобі дають ім'я їхньої перевірки і рядки її логу. Скажи, що з цим може
зробити лаба.

Правила:
1. `ours` — лише коли дефект видно В КОДІ ГІЛКИ і в каталозі є перевірка,
   що його ловить. Бери id ЛИШЕ з каталогу, дослівно.
2. `not_ours` — коли лікується не з коду: стан домену (чорний список),
   хостинг і 5xx, ціни, орфографія, зміст текстів, дефект зроблений
   ВИКЛАДКОЮ. Постав id класу зі списку нижче.
3. `no_check` — дефект справді в коді, але потрібної перевірки в лабі
   НЕМАЄ. Це чесна і корисна відповідь: не тягни сюди схожий чек, бо він
   прогониться і нічого не знайде.
4. `visual` — перекоси верстки, контраст, мобільна ширина: у лабі це
   окремий візуальний прогін, а не перевірка коду.
5. `tool_failure` — з логу видно, що зірвався ЇХНІЙ прогін (таймаут,
   зупинка, впав браузер, не відповів рушій). Це не дефект сайта.
6. `soft` — їхня знахідка «на глаз», привід подивитись, а не чинити.
7. Відповідь має бути на КЛАС дефекту, а не на конкретний домен: вона
   збережеться і застосовуватиметься до всіх наступних таких вердиктів.
8. СУДИ ПО ЛОГАХ, А НЕ ПО ІМЕНІ. Імена їхніх перевірок збігаються з нашими
   поняттями випадково і збивають з пантелику. Живий приклад: їхній `health`
   — це БИТІ АССЕТИ І ПОМИЛКИ JS, тобто файли, яких немає в коді гілки
   (наші css_integrity / media_integrity / asset_base), а зовсім не «хостинг
   лежить», хоч у нашому списку «не наше» клас з таким самим іменем означає
   саме хостинг. Так само їхній `bank` — це реквізити в тексті, а не блок
   довіри з логотипами банків. Читай рядки логу: вони кажуть, що саме
   знайдено.

Каталог перевірок лаби:
{catalog}

Що лаба не вміє в принципі (id класу -> чому):
{not_ours}
"""


def ask_verdicts(items: list[dict], cards: list[dict],
                 timeout: int = 60) -> dict:
    """Розібрати незнайомі імена перевірок. НІКОЛИ не кидає.

    `items` — [{"name", "logs"}]. Один виклик на всі імена одразу: каталог у
    промпті важить у рази більше за самі імена, тож питати по одному означало
    б платити за нього щоразу.
    """
    ok, why = available()
    if not ok:
        return {"error": why, "entries": None}
    lines = []
    for it in items:
        logs = "; ".join(str(x) for x in (it.get("logs") or []))[:600]
        lines.append(f"- {it.get('name')}: {logs or '(логів немає)'}")
    body = {
        "model": model_name(),
        "max_tokens": 2000,
        "output_config": {"effort": "low"},
        "system": [{
            "type": "text",
            "text": LEARN_SYSTEM.format(
                catalog=ai_skills.render_for_model(cards, rich=True),
                not_ours="\n".join(f"{c['id']} — {c['чому']}"
                                    for c in ai_skills.NOT_OURS)),
            "cache_control": {"type": "ephemeral"},
        }],
        "messages": [{"role": "user",
                      "content": "Перевірки чужого інструмента:\n"
                                 + "\n".join(lines)}],
        "tools": [LEARN_TOOL],
        "tool_choice": {"type": "tool", "name": LEARN_TOOL["name"]},
        "fallbacks": "default",
    }
    out, payload = _post(body, LEARN_TOOL["name"], timeout)
    out.pop("checks", None)
    out["entries"] = None
    if payload is None:
        return out
    out["entries"] = list(payload.get("entries") or [])
    return out


def learn_unknown(unknown: list[dict], cards: list[dict],
                  source: str = "tsm") -> dict:
    """Незнайомі вердикти -> записи в мапі. Повертає підсумок для журналу.

    Валідація тут не косметична: модель могла назвати чек, якого немає (або
    який знято з каталогу), і мовчки записати такий рядок у мапу означало б
    зробити помилку ПОСТІЙНОЮ — на відміну від разової здогадки, яку
    відсіє прогін.
    """
    valid = {c["id"] for c in cards}
    ours_classes = {c["id"] for c in ai_skills.NOT_OURS}
    by_name = {}
    for v in unknown:
        n = str(v.get("name") or "").strip().lower()
        if not n or v.get("soft"):
            continue
        by_name.setdefault(n, [])
        by_name[n] += list(v.get("logs") or [])[:3]
    names = sorted(by_name)[:MAX_LEARN_AT_ONCE]
    if not names:
        return {"learned": [], "usd": 0.0, "error": ""}

    got = ask_verdicts([{"name": n, "logs": by_name[n]} for n in names], cards)
    res = {"learned": [], "dropped": [], "unanswered": [],
           "usd": got.get("usd", 0.0), "error": got.get("error", ""),
           "ms": got.get("ms", 0)}
    if got.get("error"):
        # Мережа, відмова, порожня відповідь: доспроба тут не поможе, а
        # кулдаун уже зведено в `_note_failure`. Імена лишаються видними.
        res["unanswered"] = names
        return res
    got["entries"] = list(got.get("entries") or [])

    #   МОДЕЛЬ МОЖЕ ВІДПОВІСТИ НЕ ПРО ВСІ ІМЕНА, І ЦЕ НЕ ГІПОТЕЗА. На живому
    # прогоні 27.08 у першій пачці з п'яти вона повернула ОДИН запис, а ми
    # проковтнули це мовчки: чотири імені лишились незнайомими, і ніде
    # жодного сліду. Одна доспроба рівно про пропущені — і те, що не
    # відповіло вдруге, лягає в `unanswered` та видно на /ai.
    answered = {str(e.get("name") or "").strip().lower()
                for e in got["entries"]}
    missed = [n for n in names if n not in answered]
    if missed:
        again = ask_verdicts([{"name": n, "logs": by_name[n]} for n in missed],
                             cards)
        res["usd"] += again.get("usd", 0.0)
        res["ms"] += again.get("ms", 0)
        got["entries"] = list(got["entries"]) + list(again.get("entries") or [])
        answered |= {str(e.get("name") or "").strip().lower()
                     for e in (again.get("entries") or [])}
    res["unanswered"] = [n for n in names if n not in answered]
    cat = verdict_map.catalogue_hash(cards)
    for e in got["entries"]:
        name = str(e.get("name") or "").strip().lower()
        if name not in by_name:
            res["dropped"].append(name or "?")   # вигадала ім'я, якого не давали
            continue
        cls = str(e.get("class") or "").strip()
        picked = [c for c in (e.get("checks") or []) if c in valid]
        rec = {"key": verdict_map.key_for(source, name), "class": cls,
               "reason": str(e.get("reason") or "")[:400],
               "by": "model", "confidence": float(e.get("confidence") or 0),
               "catalogue": cat}
        if cls == "ours":
            if not picked:
                # Сказала «наше», але не назвала жодного чека з каталогу —
                # це не відповідь, а здогадка. Не записуємо: хай наступного
                # разу спитають знову, ніж таблиця вчить нас неправді.
                res["dropped"].append(name)
                continue
            rec["php"] = picked
        elif cls == "not_ours":
            nid = str(e.get("not_ours") or "").strip()
            rec["not_ours"] = nid if nid in ours_classes else ""
        try:
            verdict_map.save(rec, author="claude")
            res["learned"].append({"name": name, "class": cls,
                                   "checks": picked})
        except ValueError as err:
            res["dropped"].append(f"{name}: {err}")
    return res


# --------------------------------------------------------------------------
# 3. Оркестрація
# --------------------------------------------------------------------------
def route(text: str, cards: list[dict], history=(), use_model: bool = True,
          budget_left_usd: float | None = None, env: dict | None = None) -> dict:
    """Повний роутинг однієї скарги.

    `budget_left_usd` рахує викликач (по реєстру, який переживає рестарт) —
    сам роутер стану на диску не тримає. None = без обмеження.

    `env` — конверт з `tsm_ingest.ingest()`, коли запит прийшов структурою
    (імена перевірок, а не проза). Не передали — збираємо його з тексту, тож
    обидва входи йдуть одним шляхом і поводяться однаково.
    """
    valid = {c["id"] for c in cards}
    if env is None:
        env = tsm_ingest.ingest({"text": text})

    # --- мапа по ІМЕНІ перевірки: найдешевший і найстійкіший шар ----------
    # Вимір на двох зрізах TSM (`qa_lab-work/tsm-drift/`): ключ по імені дає 92%
    # на новому зрізі проти 74% у якорів по прозі, бо імена не перейменовують,
    # а фрази переписують (22% рядків за 16 днів). Тому мапа йде ПЕРШОЮ, а
    # якорі лишаються для того, у чого імені немає — тобто для чистої прози.
    src = env.get("source") or "tsm"
    mapped = verdict_map.outcome(env.get("verdicts") or [], valid, src)

    # --- промах мапи: модель розбирає НОВЕ ІМʼЯ один раз ------------------
    # Саме тут міняються ролі. Модель не гадає при кожній скарзі — вона
    # відповідає на питання «що це за перевірка» і відповідь лягає в мапу,
    # тож наступного разу це вже таблиця. Апгрейд TSM 0.6.17 -> 0.9.26 коштував
    # би за цією схемою три виклики на весь реліз.
    learned = {}
    named_unknown = [v for v in mapped["unknown"]
                     if v.get("name") and not v.get("soft")]
    if named_unknown and use_model and not (budget_left_usd is not None
                                            and budget_left_usd <= 0):
        learned = learn_unknown(named_unknown, cards, src)
        if learned.get("learned"):
            mapped = verdict_map.outcome(env.get("verdicts") or [], valid, src)
    map_checks = list(mapped["checks"])
    map_hard = [h for h in mapped["hits"] if not h["soft"]]

    # --- вердикти TSM ідуть ПОПЕРЕДУ всього -------------------------------
    # З того боку текст складає не модель, а таблиця готових рядків
    # (`tsm_verdicts`), тож там, де рядок упізнано якорем, вгадувати нема чого:
    # відповідність точна, ціна нульова. Модель лишається на те, що написала
    # людина.
    parsed = tsm_verdicts.parse(text)
    hard = [i for i in parsed["items"] if not i.get("soft")]
    rest = "\n".join(parsed["rest"])
    #   ⚠️ ЯКОРІ БІЛЬШЕ НЕ РОУТЯТЬ — вони лише дають ІМʼЯ (`name_of_line`),
    # а куди воно веде, вирішує мапа. Доти було дві таблиці відповідності, і
    # 27.08 вони розійшлись: я виправив у мапі `cookie_toggles` на «чека
    # немає» (їхні повзунки категорій — це не наш `cookie_consent`, той про
    # банер, що не ховається), а в списку якорів лишився старий id — і він
    # переміг, бо результати зливались. Спіймано локальним стендом.
    #   Дублювати нічого й не треба: `tsm_ingest` проставляє рядку ім'я тим
    # самим розпізнавачем, тож кожен упізнаний якорем рядок і так приходить
    # у мапу іменем.

    if mapped["tool_failure"] or any(i.get("tool_failure") for i in hard):
        # Зламалась ЇХНЯ тула, а не вайт — у їхньому ж рядку так і написано.
        # Далі не йдемо взагалі: решта червоного в тому самому тексті
        # стосується недоперевіреної сторінки.
        return {"checks": [], "router": "tsm-map", "confidence": 1.0,
                "reason": "збій прогону TSM — це не дефект вайта",
                "not_ours": [], "candidates": [], "keywords_checks": [],
                "model": {}, "tsm": parsed, "map": mapped, "env": env,
                "learned": learned, "tool_failure": True}

    # `not_ours` рахуємо ТІЛЬКИ по залишку, якщо вердикти впізнані. Заміряно
    # 26.08: одного стема в чужому тексті досить, щоб законна скарга стала
    # «не наше» — а в режимі слів «не наше» перемагає кандидатів. Рядок,
    # упізнаний якорем, уже має точну відповідь, і слова до нього застосовувати
    # нема за чим.
    hard_any = bool(hard or map_hard)
    #   СЛОВА І МОДЕЛЬ БАЧАТЬ ЛИШЕ ЗАЛИШОК, ЯКЩО ВЕРДИКТИ ВПІЗНАНІ — і
    # «впізнані» включає ЖОВТІ. Інакше зріз, у якому все жовте, потрапляв
    # словам цілим текстом, і вони роутили чек по опису знахідки «на глаз»:
    # правило «жовте не роутиться ніколи» обходилось з чорного ходу.
    # Спіймано локальним стендом на домені лише з `hygiene` у warnings.
    впізнано = bool(hard or (env.get("verdicts") or []))
    scan = rest if впізнано else text
    kw_ids, ranked = by_keywords(scan, cards, history)
    result = {
        "checks": kw_ids,
        "router": "keywords",
        "confidence": 0.0,
        "reason": "",
        "not_ours": ai_skills.not_ours(scan),
        "candidates": [r for r in ranked if r["score"] > 0][:MAX_CANDIDATES],
        "keywords_checks": kw_ids,
        "model": {},
        "tsm": parsed,
        "map": mapped,
        "env": env,
        "learned": learned,
    }
    if hard_any:
        result["checks"] = _merge(map_checks, kw_ids)
        result["router"] = "tsm-map"
        result["confidence"] = 1.0
        result["reason"] = "вердикти TSM: " + ", ".join(
            sorted({i["tsm"] for i in hard} | {h["name"] for h in map_hard}))
        # «Чому» беремо з нашого ж класу — там уже написано людською мовою,
        # чому це не лікується з коду гілки. Дублювати текст у мапі вердиктів
        # означало б, що одного дня вони розійдуться.
        by_id = {c["id"]: c for c in ai_skills.NOT_OURS}
        seen_cls = set()
        for cls, hit, why in ([(i.get("not_ours"), i["tsm"], i["line"]) for i in hard]
                              + [(h.get("not_ours"), h["name"], h["reason"])
                                 for h in map_hard]):
            if not cls or cls in seen_cls:
                continue
            seen_cls.add(cls)
            base = by_id.get(cls) or {"id": cls, "чому": why}
            result["not_ours"].append({**base, "hits": [hit]})
        # Немає прози — немає й приводу питати модель. Це і є та економія,
        # заради якої розбір робився.
        #   ⚠️ УМОВА ЧИТАЄ `hard_any`, А НЕ `hard`. Відколи якорі перестали
        # роутити, `hard` буває порожнім там, де мапа все впізнала, — і ця
        # відсічка не спрацьовувала. Наслідок був не «зайвий виклик»: ми
        # слали моделі ПОРОЖНЄ повідомлення, API відповідав
        # `400 user messages must have non-empty content`, збій зводив
        # кулдаун — і наступний РОЗБІР НОВОГО ІМЕНІ відмовлявся локально,
        # тобто мапа тихо переставала рости. Спіймано локальним стендом.
        if not rest.strip():
            return result

    if not use_model:
        return result
    if budget_left_usd is not None and budget_left_usd <= 0:
        result["model"] = {"error": "бюджет на Claude вичерпано"}
        return result

    # Моделі віддаємо ЗАЛИШОК, а не весь текст: вердикти вже розібрані точно,
    # і показувати їх моделі означало б платити за токени двічі й дати їй
    # шанс переграти точну відповідь на здогадку.
    m = ask_model(scan, cards)
    result["model"] = {k: v for k, v in m.items() if k != "checks"}
    if m.get("error") or m.get("checks") is None:
        return result                       # лишаємось на словах

    # Модель могла назвати чек, якого немає або який не діє в цьому проєкті.
    # Мовчки викидаємо, але ЗАПИСУЄМО — інакше не видно, що вона фантазує.
    picked, dropped = [], []
    for cid in m["checks"]:
        (picked if cid in valid else dropped).append(cid)
    result["model"]["dropped"] = dropped

    # Вердикти TSM модель НЕ переграє: вони точні, а вона працює на повноту.
    # Тому об'єднання, і першими йдуть саме вони.
    result["checks"] = (_merge(map_checks, picked)[:MAX_CANDIDATES]
                        if hard_any else picked[:MAX_CANDIDATES])
    result["router"] = "tsm-map+claude" if hard_any else "claude"
    result["confidence"] = 1.0 if hard_any else m.get("confidence", 0.0)
    result["reason"] = ((result["reason"] + "; " if hard_any else "")
                        + m.get("reason", ""))
    if m.get("not_ours") and not result["checks"]:
        result["model_says_not_ours"] = True
    # Згода зі скорером — не гейт, а вимір: по ньому потім видно, чи
    # виправдовує модель свою ціну проти простих слів.
    result["agreement"] = round(
        len(set(picked) & set(kw_ids)) / max(1, len(set(picked) | set(kw_ids))), 2)
    return result
