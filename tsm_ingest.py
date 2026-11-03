"""Толерантний прийом вердиктів: будь-що з того боку → канонічний список.

Навіщо окремий шар. До 27.08 міст приймав рівно одну форму — прозу в полі
`text`, — і розбирав її якорями (`tsm_verdicts`). Апстрім TSM 0.9.26 показав,
чого це варте: за 16 днів **22% рядків переписано**, і додався ЦІЛИЙ новий
формат (`advice_summary`, короткі підписи саппорту). Вимір на двох зрізах
(`qa_lab-work/tsm-drift/`): ручні якорі 74% на подробицях і **11% на короткому
форматі**, кеш по скелету прози — 53%, а ключ по **імені перевірки** — 92%.

Звідси правило цього модуля: **структура б'є прозу**. Якщо в запиті є імена
перевірок — беремо їх, а прозу читаємо лише заради того, чого в іменах немає
(вітка, «генератор чи викладка», жовте). Проза лишається повноцінним входом,
але як запасний, а не основний.

**Чому це і є «мінімум правок на їхньому боці».** Свого кінця мосту в TSM
немає взагалі — жодної згадки лаби ні в коді, ні в 369 КБ їхнього changelog.
Тобто інтеграція в будь-якому разі починається з одного нового виклику, і
маргінальна ціна зайвих полів у ньому — нуль. А зріз домену в них УЖЕ зібраний
(`runner._запомнить_срез` → `domain`, `checks[]`, `fix`, `eyes`, `front`,
`text`) і рівно в такому вигляді віддається їхнім `GET /qa/domain`. Отже
найдешевша для них правка — переслати цю структуру як є, нічого не
перепаковуючи. Саме її ми тут і вміємо прийняти — разом з усіма проміжними
формами, аж до голого списку імен.

Модуль НІЧОГО не роутить і не знає про наші чеки: його справа — привести
різношерсті форми до одного вигляду. Куди веде кожен вердикт — питання
`verdict_map`.
"""
from __future__ import annotations

import re

import tsm_verdicts

# Межі. Дані приходять по HTTP від чужого застосунку — без стелі один
# зациклений прогін з тисячею сторінок роздув би і журнал, і промпт моделі.
MAX_VERDICTS = 200
MAX_LOGS = 20
MAX_LINE = 1000
MAX_PROSE = 200

# Поля, у яких може приїхати структура перевірок. `checks` — так зветься зріз
# у них; `checks_failed` — так це поле названо в нашому контракті.
CHECK_FIELDS = ("checks", "checks_failed", "failed", "checks_list")
# Поля з прозою. Порядок ВАЖЛИВИЙ: багатший формат перемагає. `front` — уся
# техніка (це найдетальніше, що вони роблять), `text` — повний розбір,
# `fix` — короткі підписи саппорта, на яких ми впізнаємо 11%.
PROSE_FIELDS = ("front", "advice_front", "text", "advice", "advice_text",
                "fix", "advice_summary")
SOFT_FIELDS = ("eyes", "soft", "advice_eyes")

# «ИСХОДНИКИ ВАЙТА (ветка «orxqal-stnaker-sg-en», файлов 214):» — рядок, який
# whitesrc.py пише у звіт кожного червоного домену з 21.08. Це найдешевше
# джерело імені вітки з усіх наявних: точне, від їхньої ж бази заливки, і
# не потребує від них ЖОДНОЇ правки — рядок уже в тексті.
_BRANCH_RX = re.compile(r"ветк[аи]\s+[«\"']([^»\"']{2,120})[»\"']", re.I)
# Їхній же висновок «чий дефект». Ключові шматки взяті з `whitesrc._по_проверке`
# дослівно; шукаємо корені, бо форма змінюється («дефект генератора, чинить
# шаблон» / «приехало из генератора»).
_ORIGIN_GEN = ("дефект генератора", "из генератора", "приехало из генератора")
_ORIGIN_DEP = ("при выкладке", "смотреть деплой", "уникализации")

# Заголовок блоку whitesrc. Усе від нього і до кінця тексту — їхня СЛУЖБОВА
# метаінформація («що каже гілка про цей дефект»), а не скарга. Вона стоїть
# останньою секцією їхнього звіту.
_WHITESRC_RX = re.compile(r"исходники\s+вайта", re.I)

_PAGE_RX = re.compile(r"^[•👁\-\s]*\[([^\]]{1,60})\]\s*(.+)$")
_BULLET_RX = re.compile(r"^[•👁\-\s]+")
# Фолбек самого TSM для перевірки без гілки поради: «имя: логи». Той самий
# регексп, що в `tsm_verdicts` — тут він потрібен, щоб дістати ІМʼЯ з прози,
# коли структури не прислали.
_NAME_RX = re.compile(r"^([a-z_][a-z0-9_]{2,23}):\s")


def _lines(raw) -> list[str]:
    """Список рядків з будь-чого: рядок, список, список списків."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [x.strip() for x in raw.splitlines() if x.strip()]
    if isinstance(raw, (list, tuple)):
        out = []
        for x in raw:
            out += _lines(x)
        return out
    return [str(raw).strip()] if str(raw).strip() else []


def _clip(s, n=MAX_LINE) -> str:
    return " ".join(str(s or "").split())[:n]


def branch_from_text(text: str) -> str:
    """Ім'я вітки з їхнього ж рядка «ИСХОДНИКИ ВАЙТА (ветка «X», файлов N)».

    Свідомо шукаємо по всьому тексту, а не лише в тому рядку: whitesrc пише
    ще й «ветка «X» найдена в базе, но исходники прочитать не удалось» —
    вітка там теж названа, і вона так само придатна для ідентифікації.
    """
    m = _BRANCH_RX.search(text or "")
    return m.group(1).strip() if m else ""


def origin_from_text(text: str) -> str:
    """«генератор чи викладка» — висновок ЇХНЬОГО whitesrc, не наш здогад.

    Це і є відповідь на питання «чи може лаба це полагодити»: дефект
    викладки з коду вітки не лікується взагалі, і прогін чеків по ньому —
    витрачений знімок і витрачене коло.
    """
    low = (text or "").lower()
    gen = any(k in low for k in _ORIGIN_GEN)
    dep = any(k in low for k in _ORIGIN_DEP)
    if gen and dep:
        return "mixed"
    if gen:
        return "generator"
    if dep:
        return "deploy"
    return ""


def _verdict(name="", page="", logs=(), line="", soft=False, kind="check"):
    return {"name": str(name or "").strip().lower(),
            "page": _clip(page, 60),
            "logs": [_clip(x) for x in list(logs)[:MAX_LOGS]],
            "line": _clip(line),
            "soft": bool(soft),
            "kind": kind}


def _from_checks(raw) -> list[dict]:
    """Структурований вхід: список перевірок їхнього зрізу.

    Приймаємо і повний запис (`{"name", "passed", "logs", "warnings"}`), і
    голе ім'я рядком — бо «список імен» це теж законна форма запиту, і
    змушувати той бік загортати її в об'єкти було б рівно тією правкою, якої
    ми домовились уникати.

    ⚠️ `passed=True` з непорожніми `warnings` — це ЖОВТЕ, а не зелене. У них
    так влаштовані `hygiene`, `spellcheck` і `mobile`: вони НІКОЛИ не
    червоніють (перевірено по їхньому коду — жодного `"passed": False`), і
    вся їхня знахідка лежить у `warnings`. Прийняти їх як пройдені означало б
    мовчки загубити цілий ярус їхньої роботи.
    """
    out = []
    for item in (raw if isinstance(raw, (list, tuple)) else []):
        if isinstance(item, str):
            if item.strip():
                out.append(_verdict(name=item))
            continue
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("check") or item.get("id") or ""
        if not str(name).strip():
            continue
        page = item.get("page") or item.get("path") or item.get("url") or ""
        logs = item.get("logs") or item.get("log") or []
        warns = item.get("warnings") or item.get("warn") or []
        passed = item.get("passed")
        if passed is False or (passed is None and (logs or not warns)):
            out.append(_verdict(name=name, page=page, logs=_lines(logs),
                                soft=False))
        if warns:
            out.append(_verdict(name=name, page=page, logs=_lines(warns),
                                soft=True))
    return out


def _from_prose(lines, soft=False) -> tuple[list[dict], list[str]]:
    """Проза → вердикти + залишок людського тексту.

    Вердиктом вважаємо рядок з маркером («•», «👁») або з їхнім фолбеком
    «имя: логи». Решта — проза, яку далі розбирають слова і модель: саме там
    живе те, що написала людина, а не таблиця.
    """
    verdicts, rest = [], []
    below_soft = soft
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        #   БЛОК `ИСХОДНИКИ ВАЙТА` — НЕ СКАРГА, А МЕТАІНФОРМАЦІЯ. Вітку і
        # «генератор чи викладка» ми з нього вже взяли (`branch_from_text`,
        # `origin_from_text`) по всьому тексту, окремо. Далі він тільки
        # шкодить: його рядки виглядають як вердикти («• links [/servicios]:
        # …»), а незрозумілі частини їхали в модель — тобто ми платили за
        # розбір їхньої ж службової довідки. Спіймано на живому прогоні 27.08.
        #   Він завжди останній у їхньому звіті (`разбор` збирається як
        # format_text + advice_text + whitesrc), тому обриваємо на ньому.
        if _WHITESRC_RX.search(line):
            break
        n = tsm_verdicts._norm(line)
        if n.startswith(tsm_verdicts.ALL_OK):
            continue
        if tsm_verdicts.SOFT_HEADER in n:
            below_soft = True            # усе нижче — «глянути очима»
            continue
        if n.startswith("что фиксить"):
            continue
        m = _PAGE_RX.match(line)
        page, body = (m.group(1), m.group(2)) if m else ("", _BULLET_RX.sub("", line))
        marked = bool(raw.lstrip().startswith(("•", "👁", "-")))
        mn = _NAME_RX.match(tsm_verdicts._norm(body))
        # ІМʼЯ ПЕРЕВІРКИ З ФРАЗИ, а не «фраза → одразу наші чеки». Так проза
        # і структура сходяться в одній точці: далі роутить `verdict_map`, і
        # відповідність живе в одному місці. Плюс це єдиний спосіб зрозуміти
        # їхній короткий формат (`advice_summary`), на якому старі якорі
        # впізнавали 11%.
        name = mn.group(1) if mn else tsm_verdicts.name_of_line(body)
        if marked or mn or name:
            verdicts.append(_verdict(name=name, page=page, line=body,
                                     soft=below_soft or raw.lstrip().startswith("👁"),
                                     kind="prose"))
        else:
            rest.append(line)
    return verdicts, rest


def _dedup(verdicts: list[dict]) -> list[dict]:
    """Один дефект — один вердикт.

    Той бік шле ОДИН І ТОЙ САМИЙ дефект у трьох форматах відразу (`fix`,
    `text`, `front` — це три аудиторії однієї знахідки). Без цього кроку
    домен з п'ятьма дефектами перетворився б на п'ятнадцять вердиктів, а
    захист від кола рахує коло по набору чеків — тобто роздутий набір
    ламав би саме його.
    """
    seen, out = set(), []
    for v in verdicts:
        key = (v["name"], v["page"], v["soft"],
               tsm_verdicts._norm(v["line"])[:80] if not v["name"] else "")
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out[:MAX_VERDICTS]


def ingest(payload: dict) -> dict:
    """Будь-який вигляд запиту → канонічний конверт.

    Правило пріоритету, і воно тут головне: **структура б'є прозу.** Коли
    прийшли імена перевірок, прозу вже не розбираємо на вердикти — вона
    описує ТІ САМІ дефекти іншими словами, і другий розбір лише подвоїв би
    набір. Проза при цьому не викидається: з неї беруться вітка, висновок
    «генератор чи викладка» і людський залишок.
    """
    p = payload if isinstance(payload, dict) else {}
    env = {"source": _clip(p.get("source") or p.get("app") or "tsm", 40).lower(),
           "source_version": _clip(p.get("source_version")
                                   or (p.get("source") or {}).get("version")
                                   if isinstance(p.get("source"), dict)
                                   else p.get("source_version"), 40),
           "domain": _clip(p.get("domain"), 200).lower(),
           "branch": _clip(p.get("branch"), 200),
           "task_id": _clip(p.get("task_id") or p.get("task"), 60),
           "origin": _clip(p.get("origin"), 20).lower(),
           "verdicts": [], "prose": [], "all_ok": False, "shapes": []}
    if isinstance(p.get("source"), dict):
        env["source"] = _clip(p["source"].get("app") or "tsm", 40).lower()

    # --- увесь текст, який приїхав, в одному місці -------------------------
    # Вітку і «чий дефект» шукаємо ПО ВСЬОМУ тексту, з якого поля б він не
    # прийшов: whitesrc-блок вони кладуть у `text`, але нічого не заважає
    # тому боку переслати лише `front`.
    everything = []
    for f in PROSE_FIELDS + SOFT_FIELDS + ("note", "report"):
        everything += _lines(p.get(f))
    blob = "\n".join(everything)
    if not env["branch"]:
        env["branch"] = branch_from_text(blob)
    if not env["origin"]:
        env["origin"] = origin_from_text(blob)

    # --- структура -------------------------------------------------------
    structured = []
    for f in CHECK_FIELDS:
        if p.get(f):
            structured += _from_checks(p[f])
            env["shapes"].append(f)
    # Голий список імен у `text` («links, emails») теж законний вхід.
    if not structured and isinstance(p.get("text"), (list, tuple)):
        structured += _from_checks(p["text"])
        if structured:
            env["shapes"].append("text[]")

    # --- проза -----------------------------------------------------------
    prose_v, rest = [], []
    if not structured:
        for f in PROSE_FIELDS:
            got = _lines(p.get(f))
            if not got:
                continue
            v, r = _from_prose(got)
            if v or r:
                prose_v += v
                rest += r
                env["shapes"].append(f)
                break                 # багатший формат уже взято, далі не треба
        for f in SOFT_FIELDS:
            if p.get(f):
                v, r = _from_prose(_lines(p[f]), soft=True)
                prose_v += v
                rest += r
                env["shapes"].append(f)
    else:
        # Жовте зі структури вже є; з прози беремо лише людський залишок —
        # він єдиний, чого в іменах перевірок немає.
        for f in PROSE_FIELDS:
            if p.get(f):
                _v, r = _from_prose(_lines(p[f]))
                rest += r
        if not env["shapes"]:
            env["shapes"].append("checks")

    env["verdicts"] = _dedup(structured + prose_v)
    env["prose"] = [_clip(x) for x in rest][:MAX_PROSE]

    # --- «фіксити нема чого» ---------------------------------------------
    n = tsm_verdicts._norm(blob)
    env["all_ok"] = bool(
        (tsm_verdicts.ALL_OK in n and not env["verdicts"])
        or (env["shapes"] and not env["verdicts"] and not env["prose"]))
    return env


def as_text(env: dict) -> str:
    """Канонічний конверт назад у текст — для журналу, підказки моделі і
    для тих шляхів, що досі працюють з прозою (`tsm_verdicts`, слова).

    Рядок вердикту зі структури збираємо у ЇХНЬОМУ ж фолбек-вигляді
    «имя: логи»: так його впізнає і наш прозовий розбір, і людина, що
    відкриє журнал.
    """
    out = []
    for v in env.get("verdicts") or []:
        if v.get("line"):
            body = v["line"]
        elif v.get("logs"):
            body = f"{v['name']}: " + "; ".join(v["logs"])
        else:
            body = f"{v['name']}: см. лог"
        mark = "👁" if v.get("soft") else "•"
        page = f" [{v['page']}]" if v.get("page") else ""
        out.append(f"{mark}{page} {body}")
    out += list(env.get("prose") or [])
    return "\n".join(out)
