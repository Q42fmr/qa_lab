"""Перемикач мови: підпис мови замінено назвою сайту/задовгим текстом.

Кейс QA 27.10 (tefluer-gechaoh-ch-fr): раніше глобальне перейменування
зачепило й Drupal language-switcher — замість короткого підпису «en»
пункт отримав «Terroir & Gestion Sarl & Gestion Sarl» (подвоєна назва
сайту), і довгий текст «наїжджав» на сусідній пункт («de») у меню.
QA: «при открытии последнего пункта меню картинка наезжает на текст».
Хенд-фікс повернув текст «en».

Перемикач: будь-яке <a hreflang="xx"> АБО <a> усередині елемента, чий
class/id містить language-switch / lang-switch / language-link /
lang-menu / langs / switcher. Підпис МАЄ бути мовним: 2–3-літерний код
(опційно з регіоном, «en-GB») або власна назва мови («English»,
«Deutsch», «Français», …), можна з іконкою/прапорцем-елементом поруч —
їх фікс не чіпає, ріже лише текстовий вузол.

Дефект: підпис не мовний І (довший за 20 символів АБО збігається/містить
назву сайту вітки — site_name.same/site_name.expected). Короткі
нестандартні підписи («Version française» — мовне слово, ≤20 символів,
не назва сайту) лишаємо як є — не кожен текст у перемикачі мусить бути
голим кодом.

Фікс підставляє hreflang-код (чи код, виведений з href: «/en/»,
«index.en.html», «?lang=en») у СТИЛІ сусідніх пунктів перемикача:
сусід «de» (lowercase) → «en»; «DE» → «EN»; «Deutsch» → «English».
Без hreflang і без мовного сегмента в href код не вивести — лише
попередження, «вручну».
"""
import html as _html
import re

import site_name

NAME = "Перемикач мови: підпис замінено назвою сайту"
GROUP = "auto"
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("У перемикачі мов (hreflang-посилання чи клас language-switch/"
               "lang-switch/language-link/lang-menu/langs/switcher) підпис мови "
               "замінено назвою сайту чи іншим задовгим текстом — пункт меню "
               "наїжджає на сусідній. Фікс повертає мовний підпис (hreflang-код "
               "чи код з href) у стилі сусідніх пунктів перемикача; текстовий "
               "вузол ріжеться, іконки/прапорці лишаються.")
FILES = ["*.html", "*.htm", "*.php"]

LANG_NAMES = {
    "en": "English", "de": "Deutsch", "fr": "Français", "it": "Italiano",
    "pt": "Português", "es": "Español", "hr": "Hrvatski", "ja": "日本語",
    "nl": "Nederlands", "pl": "Polski", "ru": "Русский", "cs": "Čeština",
    "sv": "Svenska", "da": "Dansk", "fi": "Suomi", "no": "Norsk",
    "ro": "Română", "hu": "Magyar", "el": "Ελληνικά", "tr": "Türkçe",
    "zh": "中文", "ko": "한국어", "ar": "العربية", "sk": "Slovenčina",
}
LANG_NAME_LOWER = {v.lower(): k for k, v in LANG_NAMES.items()}

SWITCHER_CLASS_RX = re.compile(
    r"(?:language-switch|lang-switch|language-link|lang-menu|langs|switcher)\w*", re.I)
_OPEN_RX = re.compile(r"""<(\w+)\b((?:[^>"']|"[^"]*"|'[^']*')*)>""")
_CLASS_ID_RX = re.compile(r'\b(?:class|id)\s*=\s*"([^"]*)"|\b(?:class|id)\s*=\s*\'([^\']*)\'', re.I)
# атрибути може нести «побиту» розмітку зі скрейпа: незекрановані «<»/«>»
# усередині значень атрибутів (data-drupal-link-system-path="<front>",
# cache/tefluer-gechaoh-ch-fr) — naïve `[^>]*` там рве тег посеред значення
# і ковтає шматок справжнього тега як текст підпису. Беремо лапки цілими.
A_RX = re.compile(r"""<a\b((?:[^>"']|"[^"]*"|'[^']*')*)>(.*?)</a\s*>""", re.I | re.S)
ATTR_TPL = r"""\b{name}\s*=\s*"([^"]*)"|\b{name}\s*=\s*'([^']*)'"""
TAG_RX = re.compile(r"<[^>]+>")
_WS_RX = re.compile(r"\s+")
_HIDDEN_RX = re.compile(r"<script\b.*?</script\s*>|<style\b.*?</style\s*>|<!--.*?-->|<\?(?:php|=).*?\?>",
                        re.I | re.S)
_LANG_CODE_LABEL_RX = re.compile(r"[A-Za-zÀ-ʯ]{2,3}(-[A-Za-z]{2})?")
# «мітка», що несе лапку/дужку тега/«=» — не текст, а недопарсений шматок
# сусіднього тега (найчастіше з побитою вихідною розміткою, де значення
# атрибута саме містить «<»/«>» без екранування): судити нема сенсу
_GARBLED_RX = re.compile(r'[<>"=]')


def _attr(attrs: str, name: str) -> str:
    m = re.search(ATTR_TPL.format(name=re.escape(name)), attrs, re.I)
    if not m:
        return ""
    return m.group(1) if m.group(1) is not None else m.group(2)


def _spans(rx: re.Pattern, text: str) -> list:
    return [(m.start(), m.end()) for m in rx.finditer(text)]


def _in_any(pos: int, spans: list) -> bool:
    return any(s <= pos < e for s, e in spans)


def _balanced_end(text: str, pos: int, tag: str):
    depth = 1
    for m in re.finditer(rf"</?{tag}\b[^>]*>", text[pos:], re.I):
        token = m.group(0)
        if token.startswith("</"):
            depth -= 1
            if depth == 0:
                return pos + m.end()
        elif not token.rstrip().endswith("/>"):
            depth += 1
    return None


def _switcher_spans(text: str) -> list:
    spans = []
    for m in _OPEN_RX.finditer(text):
        tag = m.group(1).lower()
        if tag in ("script", "style", "a"):
            continue
        attrs = m.group(2)
        if attrs.rstrip().endswith("/"):
            continue
        cm = _CLASS_ID_RX.search(attrs)
        if not cm:
            continue
        value = cm.group(1) if cm.group(1) is not None else cm.group(2)
        if not SWITCHER_CLASS_RX.search(value or ""):
            continue
        end = _balanced_end(text, m.end(), tag)
        if end:
            spans.append((m.start(), end))
    return spans


def _visible_label(inner: str) -> str:
    return _WS_RX.sub(" ", _html.unescape(TAG_RX.sub(" ", inner))).strip()


def _code_from_href(href: str) -> str:
    for pat in (r"/([a-z]{2})/", r"\.([a-z]{2})\.html?(?:$|[?#])",
                r"[?&]lang=([a-z]{2})\b", r"[/._-]([a-z]{2})(?:/index)?\.html?$"):
        m = re.search(pat, href, re.I)
        if m and m.group(1).lower() in LANG_NAMES:
            return m.group(1).lower()
    return ""


def _lang_code(attrs: str, href: str) -> str:
    hl = _attr(attrs, "hreflang")
    if hl:
        return hl.split("-")[0].lower()
    return _code_from_href(href)


def _is_lang_label(label: str) -> bool:
    t = label.strip()
    if not t:
        return False
    if _LANG_CODE_LABEL_RX.fullmatch(t):
        return True
    return t.lower() in LANG_NAME_LOWER


def _is_defect(label: str, expected: str) -> bool:
    if len(label) > 20:
        return True
    if expected:
        if site_name.same(label, expected):
            return True
        if expected.lower() in label.lower():
            return True
    return False


def _style(valid: list):
    """(kind, code_seen) зі стилю ПЕРШОГО придатного сусіда; kind — lower/upper/name."""
    for label, code in valid:
        if not code:
            continue
        t = label.strip()
        if t == code and t == t.lower():
            return ("lower", code)
        if t == code.upper() and t == t.upper():
            return ("upper", code)
        if t.lower() in LANG_NAME_LOWER:
            return ("name", code)
    return ("lower", None)


def _render(code: str, style: tuple) -> str:
    kind = style[0]
    if kind == "upper":
        return code.upper()
    if kind == "name":
        return LANG_NAMES.get(code, code)
    return code


def _groups(text: str) -> list:
    """Один «перемикач» на сторінку: усі hreflang-посилання та посилання
    всередині елементів зі switcher-класом зведені в одну групу."""
    switcher_spans = _switcher_spans(text)
    hidden = _spans(_HIDDEN_RX, text)
    anchors = []
    for m in A_RX.finditer(text):
        if _in_any(m.start(), hidden):
            continue
        attrs, inner = m.group(1), m.group(2)
        hreflang = _attr(attrs, "hreflang")
        if not hreflang and not _in_any(m.start(), switcher_spans):
            continue
        label = _visible_label(inner)
        if not label or _GARBLED_RX.search(label):
            # побита розмітка (незбалансовані лапки/теги у джерелі) могла
            # лишити шматок сусіднього тега у «тексті» — не мітка, мовчимо
            continue
        href = _attr(attrs, "href")
        anchors.append({
            "start": m.start(2), "end": m.end(2),
            "attrs": attrs, "inner": inner,
            "label": label, "code": _lang_code(attrs, href),
        })
    return [anchors] if anchors else []


def _fix_inner(inner: str, new_label: str) -> str:
    parts = re.split(r"(<[^>]+>)", inner)
    text_idxs = [i for i, p in enumerate(parts) if not p.startswith("<") and p.strip()]
    if not text_idxs:
        return inner
    best = max(text_idxs, key=lambda i: len(parts[i].strip()))
    parts[best] = new_label
    for i in text_idxs:
        if i != best:
            parts[i] = ""
    return "".join(parts)


def _page_issues(path: str, text: str, expected: str) -> list:
    issues = []
    for group in _groups(text):
        valid = [(a["label"], a["code"]) for a in group if _is_lang_label(a["label"])]
        broken = [a for a in group
                  if not _is_lang_label(a["label"]) and _is_defect(a["label"], expected)]
        if not broken:
            continue
        style = _style(valid)
        for a in broken:
            short = a["label"] if len(a["label"]) <= 40 else a["label"][:37] + "…"
            line = text.count("\n", 0, a["start"]) + 1
            if a["code"]:
                new_label = _render(a["code"], style)
                msg = (f'у перемикачі мов підпис «{short}» — це назва сайту/задовгий '
                       f'текст, не мова — фікс поверне «{new_label}» (hreflang={a["code"]})')
            else:
                msg = (f'у перемикачі мов підпис «{short}» — це назва сайту/задовгий '
                       f'текст, не мова, а код мови не визначити (немає hreflang, href без '
                       f'мовного сегмента) — виправ вручну')
            issues.append({"path": path, "line": line, "severity": "warn", "message": msg})
    return issues


def _fix_page(text: str, expected: str) -> str:
    for group in _groups(text):
        valid = [(a["label"], a["code"]) for a in group if _is_lang_label(a["label"])]
        broken = [a for a in group
                  if not _is_lang_label(a["label"]) and _is_defect(a["label"], expected) and a["code"]]
        if not broken:
            continue
        style = _style(valid)
        edits = sorted(broken, key=lambda a: -a["start"])
        for a in edits:
            new_label = _render(a["code"], style)
            new_inner = _fix_inner(a["inner"], new_label)
            text = text[:a["start"]] + new_inner + text[a["end"]:]
    return text


def run_branch(files, all_paths, branch: str = ""):
    expected = site_name.expected(branch, files)
    issues = []
    for path in sorted(files):
        issues.extend(_page_issues(path, files[path], expected))
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    expected = site_name.expected(branch, files)
    actions = []
    for path in sorted(files):
        text = files[path]
        new_text = _fix_page(text, expected)
        if new_text != text:
            actions.append({"type": "edit", "path": path, "content": new_text})
    return actions
