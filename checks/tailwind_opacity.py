"""Tailwind: невалідна/відсутня opacity — суцільний оверлей ховає картинку.

Кейс tajbojo-br-pt: у хедері <img class="hero-img"> накритий
<div class="absolute inset-0 bg-deep-hull bg-opacity-62 ...">.
Play CDN (v3.4) генерує *-opacity-N лише для N, кратних 5 (0–100);
bg-opacity-62 не існує, тож --tw-bg-opacity лишається 1 — оверлей
суцільний і повністю закриває hero-картинку.

Що ловимо (лише сторінки, що підключають cdn.tailwindcss.com):
  * opacity-N та bg-/text-/border-/ring-/divide-/placeholder-/backdrop-
    opacity-N, де N не кратне 5 або N > 100 — клас не буде згенеровано,
    прозорість не застосується (bg-/opacity- — error, решта — warn);
  * оверлей поверх <img> (absolute + inset-0 + суцільний bg-колір) зовсім
    без прозорості: ні *-opacity, ні bg-колір/NN, ні inline style, ні
    кастомного класу з opacity у <style> сторінки;
  * фонове фото hero, яке саме себе гасить до невидимості. Кейс
    romevafu-br-pt: <img class="absolute inset-0" style="opacity:0.22">,
    а зверху скрим linear-gradient(rgba(26,47,75,0.97) → 0.82). Фактична
    видимість фото = 0.22 × (1 − 0.82) ≈ 4% — на рендері картинки просто
    немає. Значення валідне, тому перші дві перевірки його не бачать:
    рахуємо саме ДОБУТОК прозорості картинки і щільності скрима.

Автофікс:
  * заміна N на найближче кратне 5 у межах 0–100 (bg-opacity-62 → bg-opacity-60);
  * додавання bg-opacity-60 у class оверлея без прозорості;
  * зняття власного гасіння з фонового фото (inline opacity або клас
    opacity-N) — скрим лишається недоторканим, тож контраст тексту
    не змінюється.

Arbitrary-синтаксис (bg-opacity-[0.62], bg-deep-hull/60) валідний — не чіпаємо.
Класи, які сторінка сама оголосила у <style> (напр. .opacity-62), теж.
"""
import re

NAME = "Tailwind: opacity, що ховає картинки"
GROUP = "auto"     # opacity-класи: звалідовано на 676 вітках (1/8 кешу) —
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
                   # 31 спрацювання у 10 вітках, усі реальні, фолсів 0.
                   # Фонове фото: 1200 віток / 10421 сторінка — 26 спрацювань
                   # у 6 вітках; 26 знахідок перевірено рендером (скрін hero
                   # з картинкою vs без неї, різниця пікселів): 20 справжніх,
                   # 0 фолсів, 2 свідомі пропуски (там винен скрим, не фото).
PROJECTS = ["php"]
DESCRIPTION = ("Невалідні opacity-класи Tailwind (не кратні 5), суцільні "
               "оверлеї без прозорості поверх <img> і фонові фото hero, "
               "приглушені до невидимості власною opacity під щільним "
               "скримом. Автофікс знімає гасіння з фото.")
FILES = ["*.html", "*.htm", "*.php"]

TAILWIND_CDN_RX = re.compile(r"cdn\.tailwindcss\.com", re.I)
CLASS_ATTR_RX = re.compile(r"""\bclass\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
# hover:/md:-варіанти лишаються зліва від збігу і не чіпаються
OPACITY_UTIL_RX = re.compile(
    r"(?<![\w-])((?:bg|text|border|ring|divide|placeholder|backdrop)-opacity|opacity)"
    r"-(\d{1,3})(?![\w.-])")
STYLE_ATTR_RX = re.compile(r"""\bstyle\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
STYLE_BLOCK_RX = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.S | re.I)
CSS_RULE_RX = re.compile(r"([^{}]+)\{([^{}]*)\}")
CSS_CLASS_RX = re.compile(r"\.([A-Za-z0-9_-]+)")
# будь-яка ознака прозорості у css-декларації
ALPHA_DECL_RX = re.compile(r"\bopacity\s*:|rgba\(|hsla\(|#[0-9a-fA-F]{8}\b", re.I)
IMG_RX = re.compile(r"<img\b", re.I)
IMG_LOOKBACK = 800          # оверлей шукаємо одразу після <img> (hero-патерн)
OVERLAY_ADD = "bg-opacity-60"

# bg-* класи, що НЕ є суцільним кольором тла
NON_COLOR_BG_RX = re.compile(
    r"^bg-(?:gradient-|none$|transparent$|inherit$|current$|opacity-"
    r"|cover$|contain$|auto$|center$|top$|bottom$|left|right|repeat"
    r"|no-repeat$|fixed$|local$|scroll$|clip-|origin-|blend-|\[)")

# --- фонове фото, приглушене до невидимості --------------------------------
IMG_TAG_RX = re.compile(r"<img\b[^>]*>", re.I)
# власна opacity елемента в inline-стилі; ловимо разом з роздільниками,
# щоб автофікс міг вирізати декларацію без сміття на кшталт ";;"
INLINE_OPACITY_RX = re.compile(
    r"(^|;)\s*opacity\s*:\s*(\d*\.?\d+)\s*(;?)", re.I)
# значення background* — саме з нього беремо щільність скрима
BG_VALUE_RX = re.compile(
    r"\bbackground(?:-color|-image)?\s*:\s*([^;]*)", re.I)
# rgba(r,g,b,a) і сучасне rgb(r g b / a)
RGBA_FN_RX = re.compile(
    r"\brgba?\(\s*[\d.%]+[\s,]+[\d.%]+[\s,]+[\d.%]+\s*(?:[,/]\s*([\d.%]+)\s*)?\)", re.I)
HEX8_RX = re.compile(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})\b")
HEX_SOLID_RX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b")
TRANSPARENT_RX = re.compile(r"\btransparent\b", re.I)
NAMED_COLOR_RX = re.compile(
    r"\b(?:white|black|red|blue|green|gray|grey|navy|teal|silver|maroon"
    r"|olive|purple|fuchsia|lime|aqua|orange|brown|beige|ivory)\b", re.I)
TAG_SCAN_RX = re.compile(r"<(/?)([a-zA-Z][\w-]*)\b[^>]*>")
COMMENT_RX = re.compile(r"<!--.*?-->", re.S)
SIBLING_WINDOW = 4000       # скрим стоїть одразу за <img>, далеко не шукаємо

# Нижче цієї частки фото не читається як фото: зміряно рендером —
# при 5% середня різниця кадрів «з фото / без фото» ≈ 5/255, при 7.5%
# вона стрибає до 12/255 і картинку вже видно. Поріг стоїть у розриві.
VISIBILITY_FLOOR = 0.06


def _nearest(v: int) -> int:
    """Найближче значення зі шкали Tailwind (кратні 5, 0–100)."""
    return min(100, max(0, int(round(v / 5.0)) * 5))


def _css_maps(text: str):
    """(усі класи, оголошені у <style>; класи, чиї правила дають прозорість)."""
    defined, alpha = set(), set()
    for block in STYLE_BLOCK_RX.findall(text):
        for sel, body in CSS_RULE_RX.findall(block):
            names = CSS_CLASS_RX.findall(sel)
            defined.update(names)
            if ALPHA_DECL_RX.search(body):
                alpha.update(names)
    return defined, alpha


def _base(token: str) -> str:
    """Відкидає варіанти (hover:, md:, ...) — лишає саму утиліту."""
    return token.rsplit(":", 1)[-1]


def _class_has_alpha(tokens, alpha_classes) -> bool:
    for t in tokens:
        b = _base(t)
        if b.startswith(("opacity-", "bg-opacity-")):
            return True
        if b.startswith("bg-") and "/" in b:        # bg-deep-hull/60
            return True
        if b in alpha_classes:                      # кастомний клас зі <style>
            return True
    return False


def _solid_bg(tokens):
    """Перший безваріантний bg-клас суцільного кольору (або None)."""
    for t in tokens:
        if ":" in t:
            continue
        if t.startswith("bg-") and not NON_COLOR_BG_RX.match(t):
            return t
    return None


def _attr_pair(tag: str):
    """(class, style) тегу як рядки."""
    cm, sm = CLASS_ATTR_RX.search(tag), STYLE_ATTR_RX.search(tag)
    return ((cm.group(1) or cm.group(2) or "") if cm else "",
            (sm.group(1) or sm.group(2) or "") if sm else "")


def _tw_opacity(cls: str):
    """(значення 0..1, токен) з безваріантного класу opacity-N або None."""
    for m in OPACITY_UTIL_RX.finditer(cls):
        if m.group(1) != "opacity":
            continue
        prev = cls[:m.start()].rsplit(" ", 1)[-1]
        if ":" in prev:                  # hover:/md: — умовний, не базовий стан
            continue
        return int(m.group(2)) / 100.0, m
    return None


def _self_opacity(cls: str, style: str) -> float:
    """Власна opacity елемента (inline має пріоритет над класом)."""
    m = INLINE_OPACITY_RX.search(style)
    if m:
        return float(m.group(2))
    tw = _tw_opacity(cls)
    return tw[0] if tw else 1.0


def _paint_alpha(cls: str, style: str):
    """Щільність, з якою елемент замальовує шар під собою: 0 — не ховає
    нічого, 1 — глухо. None — визначити не вдалось (напр. кастомний клас).

    Береться МІНІМАЛЬНА альфа по стопах градієнта: саме у найпрозорішій
    точці фото ще може проглядати. Через це градієнти зі стопом
    `transparent` (дуже поширений хват — скрим тільки під текстом зліва)
    не вважаються такими, що ховають картинку."""
    alphas = []
    for bm in BG_VALUE_RX.finditer(style):
        val = bm.group(1)
        if TRANSPARENT_RX.search(val):
            alphas.append(0.0)
        for m in RGBA_FN_RX.finditer(val):
            raw = m.group(1)
            if raw is None:                       # rgb() без альфи — глухий
                alphas.append(1.0)
            elif raw.endswith("%"):
                alphas.append(float(raw[:-1]) / 100.0)
            else:
                alphas.append(float(raw))
        for m in HEX8_RX.finditer(val):
            alphas.append(int(m.group(1), 16) / 255.0)
        rest = HEX8_RX.sub("", val)
        if HEX_SOLID_RX.search(rest) or NAMED_COLOR_RX.search(rest):
            alphas.append(1.0)

    tokens = cls.split()
    solid = _solid_bg(tokens)
    if solid:
        a = 1.0
        if "/" in solid:                          # bg-navy/80
            frac = solid.rsplit("/", 1)[1]
            a = int(frac) / 100.0 if frac.isdigit() else 1.0
        for t in tokens:
            om = re.fullmatch(r"bg-opacity-(\d{1,3})", t)
            if om:
                a = min(a, int(om.group(1)) / 100.0)
        alphas.append(a)

    if not alphas:
        return None
    return min(alphas) * _self_opacity(cls, style)


def _next_sibling(text: str, pos: int):
    """Перший тег-елемент після pos у ТОМУ Ж контейнері.

    Закривний тег означає, що контейнер вичерпався і накривати картинку
    вже нічому — саме це відсікає «наступну секцію» від hero-скрима."""
    chunk = text[pos:pos + SIBLING_WINDOW]
    chunk = COMMENT_RX.sub(lambda m: " " * len(m.group(0)), chunk)
    for m in TAG_SCAN_RX.finditer(chunk):
        if m.group(2).lower() in ("script", "style", "noscript", "template"):
            continue
        if m.group(1):                   # </...> — контейнер закрився
            return None
        return m.group(0)
    return None


def _problems(text: str) -> list[dict]:
    """Спільне для run() і fix(): знахідки зі спанами правок.
    start/end — абсолютні позиції в text; replacement — що туди поставити
    (start == end — вставка)."""
    if not TAILWIND_CDN_RX.search(text):
        return []
    defined, alpha_classes = _css_maps(text)
    probs = []

    for cm in CLASS_ATTR_RX.finditer(text):
        dq = cm.group(1) is not None
        val = cm.group(1) if dq else cm.group(2)
        vstart = cm.start(1) if dq else cm.start(2)

        # 1) невалідні значення *-opacity-N — заміна на найближче кратне 5
        for m in OPACITY_UTIL_RX.finditer(val):
            util, v = m.group(1), int(m.group(2))
            if v <= 100 and v % 5 == 0:
                continue
            if m.group(0) in defined:       # сторінка сама оголосила такий клас
                continue
            new = f"{util}-{_nearest(v)}"
            sev = "error" if util in ("opacity", "bg-opacity") else "warn"
            probs.append({
                "line": text.count("\n", 0, vstart + m.start()) + 1,
                "severity": sev,
                "message": (f"{m.group(0)}: у Tailwind нема такого класу "
                            f"(шкала — кратні 5, 0–100), прозорість не "
                            f"застосується — заміна на {new}"),
                "start": vstart + m.start(), "end": vstart + m.end(),
                "replacement": new,
            })

        # 2) суцільний оверлей поверх <img> без жодної прозорості
        tokens = val.split()
        if "absolute" not in tokens or "inset-0" not in tokens:
            continue
        bg = _solid_bg(tokens)
        if not bg or _class_has_alpha(tokens, alpha_classes):
            continue
        tag_start = text.rfind("<", 0, cm.start())
        tag_end = text.find(">", cm.end())
        if tag_start == -1 or tag_end == -1:
            continue
        tag = text[tag_start:tag_end + 1]
        sm = STYLE_ATTR_RX.search(tag)
        if sm and ALPHA_DECL_RX.search(sm.group(1) or sm.group(2) or ""):
            continue                        # прозорість дає inline style
        if not IMG_RX.search(text, max(0, tag_start - IMG_LOOKBACK), tag_start):
            continue                        # не над картинкою — не чіпаємо
        probs.append({
            "line": text.count("\n", 0, vstart) + 1,
            "severity": "error",
            "message": (f"оверлей ({bg}) поверх <img> без прозорості — "
                        f"суцільний фон повністю закриває картинку; "
                        f"додається {OVERLAY_ADD}"),
            "start": vstart + len(val), "end": vstart + len(val),
            "replacement": " " + OVERLAY_ADD,
        })

    probs.extend(_hidden_photos(text))
    return probs


def _hidden_photos(text: str) -> list[dict]:
    """Фонове фото hero, яке саме себе гасить під щільним скримом.

    Рахуємо фактичну видимість = opacity(картинки) × (1 − щільність скрима).
    Репортимо лише те, що автофікс справді вилікує: якщо сам скрим щільніший
    за поріг, зняття гасіння з фото нічого не дасть — це вже інша поломка
    (проблема оверлея), і чіпати чужий скрим ми не будемо, бо це зіпсує
    контраст тексту."""
    probs = []
    for im in IMG_TAG_RX.finditer(text):
        tag = im.group(0)
        cls, style = _attr_pair(tag)
        tokens = cls.split()
        # фоновий шар: картинка розтягнута на весь контейнер під контентом
        if "absolute" not in tokens or "inset-0" not in tokens:
            continue
        img_a = _self_opacity(cls, style)
        if img_a >= 1.0:
            # Швидкий вихід: картинка себе не гасить. Поведінково це вже
            # гарантує перевірка through нижче (при img_a == 1 видимість
            # дорівнює through), але так ми не парсимо сусіда для кожного
            # <img> на сторінці — а таких переважна більшість.
            continue

        sib = _next_sibling(text, im.end())
        scrim = 0.0
        if sib:
            a = _paint_alpha(*_attr_pair(sib))
            if a is not None:           # не розібрали скрим — вважаємо, що не ховає
                scrim = a
        through = 1.0 - scrim
        visible = img_a * through
        if visible >= VISIBILITY_FLOOR:
            continue
        if through < VISIBILITY_FLOOR:
            continue                    # винен скрим, не картинка — фікс не поможе

        span = _undim_span(tag, im.start(), cls, style)
        if span is None:
            continue
        start, end, repl = span
        probs.append({
            "line": text.count("\n", 0, im.start()) + 1,
            "severity": "error",
            "message": (
                f"фонове фото hero фактично не видно: власна opacity "
                f"{_fmt(img_a)} під скримом щільністю {_fmt(scrim)} лишає "
                f"{visible * 100:.1f}% видимості — знімається гасіння "
                f"з картинки (скрим не чіпаємо, контраст тексту той самий)"),
            "start": start, "end": end, "replacement": repl,
        })
    return probs


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _undim_span(tag: str, tag_start: int, cls: str, style: str):
    """(start, end, replacement) — що вирізати, щоб картинка перестала
    гасити саму себе. Inline-декларація має пріоритет: саме вона перебиває
    клас."""
    sm = STYLE_ATTR_RX.search(tag)
    if sm:
        val_start = sm.start(1) if sm.group(1) is not None else sm.start(2)
        m = INLINE_OPACITY_RX.search(style)
        if m:
            rest = (style[:m.start()] + style[m.end():]).strip(" ;\t\n")
            if not rest:                # opacity була єдиною — прибираємо атрибут
                pre = tag[:sm.start()]
                cut = len(pre) - len(pre.rstrip(" \t\n"))
                return (tag_start + sm.start() - cut, tag_start + sm.end(), "")
            keep = ";" if m.group(1) == ";" and m.group(3) else m.group(1)
            return (tag_start + val_start + m.start(),
                    tag_start + val_start + m.end(), keep)

    cm = CLASS_ATTR_RX.search(tag)
    tw = _tw_opacity(cls)
    if cm and tw:
        val_start = cm.start(1) if cm.group(1) is not None else cm.start(2)
        m = tw[1]
        start, end = m.start(), m.end()
        if start and cls[start - 1] == " ":         # з'їдаємо один пробіл зліва
            start -= 1
        elif end < len(cls) and cls[end] == " ":
            end += 1
        return (tag_start + val_start + start, tag_start + val_start + end, "")
    return None


def run(path, text):
    return [{"line": p["line"], "message": p["message"], "severity": p["severity"]}
            for p in _problems(text)]


def fix(path, text):
    """Автофікс рівно того, що бачить run(): невалідні *-opacity-N →
    найближче кратне 5; оверлей без прозорості отримує bg-opacity-60."""
    for p in sorted(_problems(text), key=lambda p: p["start"], reverse=True):
        text = text[:p["start"]] + p["replacement"] + text[p["end"]:]
    return text
