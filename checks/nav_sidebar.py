"""Десктопне меню-сайдбар накриває контент: ставимо його смугою вгорі.

У частині node-вайтів навігація зроблена не шапкою, а вертикальним
сайдбаром:

    <aside class="hidden lg:flex fixed left-0 top-0 h-full w-auto min-w-20
                  bg-orange-50 border-r border-neutral-200 flex-col
                  items-center py-8 px-3 z-40">

Сам по собі вертикальний нав — не поломка. Поломка в тому, що він `fixed`, а
**компенсації зсуву немає**: у жодній з 16 віток корпусу немає ні `lg:pl-*`,
ні `lg:ml-*` — ні в `App.vue`, ні в сторінках. Тобто смуга шириною ~80px
лежить ПОВЕРХ контенту й обрізає його: на `nwf-imsopla-nenekeoc-br-pt` у
hero видно «Tra… Ne… Est…» замість заголовка.

Лагодити можна двома шляхами, і другий надійніший:
  1. дописати контенту `lg:pl-20` — але єдиної обгортки немає: `App.vue` це
     `<HeaderNav/><router-view/><GlobalFooter/>`, тож зсув довелося б
     розносити по всіх сторінках;
  2. зробити з сайдбара звичайну горизонтальну смугу В ПОТОЦІ — тоді
     перекриття зникає за побудовою, нічого компенсувати не треба, і це
     збігається з будинковим стилем: у 141 вітки `<header>` узагалі без
     позиціювання (`bg-… py-4 px-4 md:px-8`, часто `border-b`).

Мобільну шухляду НЕ чіпаємо: вона теж `<aside class="fixed">`, але з
`lg:hidden`, `right-0` і `translate-x` — таких у корпусі 9, і вони робочі.
Розрізняє їх `lg:flex` (видима саме на десктопі) плюс `flex-col`.
"""
import re

NAME = "Меню-сайдбар накриває контент"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["node"]
DESCRIPTION = ("Десктопне меню зроблене `fixed`-сайдбаром без компенсації зсуву, "
               "тож лежить поверх контенту й обрізає його. Автофікс переводить "
               "його у звичайну горизонтальну смугу вгорі (як у решти вайтів). "
               "Мобільна шухляда (`lg:hidden` + `translate-x`) не чіпається. "
               "Друге правило: напис бренду в лого не вміщається у квадрат під "
               "іконку й лізе на перший пункт меню — фікс дає лого міритись за "
               "вмістом.")
FILES = ["*.vue"]

ASIDE_RX = re.compile(
    r"""<aside\b(?P<attrs>(?:[^>"']|"[^"]*"|'[^']*')*)>(?P<body>.*?)</aside\s*>""",
    re.S | re.I)
HEADER_RX = re.compile(
    r"""<header\b(?P<attrs>(?:[^>"']|"[^"]*"|'[^']*')*)>(?P<body>.*?)</header\s*>""",
    re.S | re.I)
CLASS_RX = re.compile(r"""\bclass\s*=\s*(?P<q>["'])(?P<v>[^"']*)(?P=q)""", re.I)
NAV_RX = re.compile(r"""<nav\b(?:[^>"']|"[^"]*"|'[^']*')*>""", re.I)
A_RX = re.compile(r"""<a\b(?:[^>"']|"[^"]*"|'[^']*')*>""", re.I)

# позиціювання й вертикальна геометрія, які тримають смугу збоку
DROP_EXACT = {"fixed", "absolute", "left-0", "right-0", "top-0", "bottom-0",
              "h-full", "h-screen", "w-auto", "overflow-y-auto", "inset-0"}
DROP_PREFIX = ("min-w-", "max-w-", "z-", "w-1/", "w-2/", "w-7", "w-8", "w-9")


def _tokens(v: str) -> list[str]:
    return v.split()


def _is_desktop_sidebar(cls: str) -> bool:
    """Саме десктопний сайдбар, а не мобільна шухляда."""
    t = set(_tokens(cls))
    if "lg:hidden" in t or "fixed" not in t:
        return False
    if "lg:flex" not in t and "flex" not in t:
        return False
    if "flex-col" not in t:
        return False
    return bool(t & {"left-0", "h-full", "h-screen"})


def _to_topbar(cls: str) -> str:
    """Класи горизонтальної смуги в потоці з тих самих кольорів і рамок."""
    out = []
    for tok in _tokens(cls):
        if tok in DROP_EXACT or tok.startswith(DROP_PREFIX):
            continue
        if tok == "flex-col":
            out.append("flex-row")
        elif tok in ("border-r", "border-l"):
            out.append("border-b")
        elif tok == "py-8":
            out.append("py-4")
        elif tok == "px-3":
            out.append("px-4")
        else:
            out.append(tok)
    have = set(out)
    if "flex-row" not in have:
        out.append("flex-row")
    if "w-full" not in have:
        out.append("w-full")
    if not any(x.startswith("gap-") for x in have):
        out.append("gap-6")
    if not any(x.startswith("justify-") for x in have):
        out.append("justify-between")
    if not any(x.startswith("md:px-") for x in have):
        out.append("md:px-8")
    return " ".join(out)


def _sub_class(tag: str, fn) -> str:
    """Замінює значення class у тегу, решту атрибутів лишає як є."""
    m = CLASS_RX.search(tag)
    if not m:
        return tag
    new = fn(m.group("v"))
    if new == m.group("v"):
        return tag
    return tag[:m.start("v")] + new + tag[m.end("v"):]


# Лого-анкер у вертикальному сайдбарі був КВАДРАТОМ під одну іконку
# (`w-12 h-12`). Коли поруч зʼявився напис бренду, текст перестав уміщатись у
# 48px: заміряно в браузері — коробка 48px, напис 85px, тобто вилазить на 38px
# і перекриває перший пункт меню на 14px, хоч `gap-6` між коробками дотриманий.
#
# Ознака - саме КВАДРАТ (`w-N h-N`, однакове N), у якому лежить іконка І текст:
# такий бокс завідомо замалий, бо іконка займає його майже цілком (40 з 48px),
# і будь-який напис поруч вилазить. Прямокутник (`w-48 h-12`) напис умістив би,
# тож його не чіпаємо. Квадрат із самою іконкою - доречний. Квадрат з літерою
# без іконки - монограма-бейдж, теж доречна.
SIZE_RX = re.compile(r"^(?P<axis>w|h)-(?P<n>\d+)$")
ICON_RX = re.compile(r"<(?:img|svg)\b", re.I)
LABEL_RX = re.compile(r">[^<>]*[^\W\d_][^<>]*<", re.U)


def _square(tokens: list[str]) -> int | None:
    """Сторона квадрата або None, якщо бокс не квадратний."""
    dims: dict[str, set[str]] = {"w": set(), "h": set()}
    for x in tokens:
        m = SIZE_RX.match(x)
        if m:
            dims[m.group("axis")].add(m.group("n"))
    if len(dims["w"]) != 1 or dims["w"] != dims["h"]:
        return None
    return int(next(iter(dims["w"])))


def _logo_needs_room(tag: str, inner: str) -> bool:
    """Квадратний бокс тримає іконку І напис - напис туди не влазить."""
    cm = CLASS_RX.search(tag)
    if not cm or _square(_tokens(cm.group("v"))) is None:
        return False
    return bool(ICON_RX.search(inner) and LABEL_RX.search(inner))


def _fix_logo(tag: str) -> str:
    """Знімає фіксований розмір, дає проміжок іконка↔напис і забороняє стиск."""
    def rewrite(v):
        out = [x for x in _tokens(v)
               if not SIZE_RX.match(x) and not x.startswith("mb-")]
        if not any(x.startswith("gap-") for x in out):
            out.append("gap-2")
        if "shrink-0" not in out:
            out.append("shrink-0")
        return " ".join(out)
    return _sub_class(tag, rewrite)


def _fix_body(body: str) -> str:
    """Всередині смуги: нав стає горизонтальним, а лого перестає бути
    квадратом під іконку — інакше напис бренду лізе на перший пункт меню."""
    def nav(tag):
        return _sub_class(tag, lambda v: " ".join(
            ("flex-row" if x == "flex-col" else x)
            for x in _tokens(v) if x != "overflow-y-auto"))

    out = NAV_RX.sub(lambda m: nav(m.group(0)), body, count=1)
    first = A_RX.search(out)
    if first:
        end = out.find("</a", first.end())
        inner = out[first.end():end if end > 0 else len(out)]
        tag = first.group(0)
        tag = _fix_logo(tag) if _logo_needs_room(tag, inner) else _sub_class(
            tag, lambda v: " ".join(x for x in _tokens(v)
                                    if not x.startswith("mb-")))
        out = out[:first.start()] + tag + out[first.end():]
    return out


def _bars(text: str):
    """(match, tag, class) кожної смуги хрому: <aside> або <header>."""
    for rx, tag in ((ASIDE_RX, "aside"), (HEADER_RX, "header")):
        for m in rx.finditer(text):
            cm = CLASS_RX.search(m.group("attrs"))
            yield m, tag, (cm.group("v") if cm else "")


def _hits(text: str):
    """Дві незалежні поломки смуги.

    'sidebar' — вертикальний `fixed`-сайдбар поверх контенту;
    'logo'    — напис бренду в лого не вміщається у квадрат під іконку.
    Друге стосується і смуг, які вже перевели у горизонтальні: там сайдбара
    вже немає, а тісне лого лишилось.
    """
    for m, tag, cls in _bars(text):
        if tag == "aside" and _is_desktop_sidebar(cls):
            yield m, tag, "sidebar"
            continue
        if "lg:hidden" in cls.split():
            continue                     # мобільна смуга/шухляда — не наша
        first = A_RX.search(m.group("body"))
        if not first:
            continue
        end = m.group("body").find("</a", first.end())
        inner = m.group("body")[first.end():end if end > 0 else None]
        if _logo_needs_room(first.group(0), inner):
            yield m, tag, "logo"


MSG = {
    "sidebar": ("десктопне меню — `fixed`-сайдбар без компенсації зсуву, тож "
                "лежить поверх контенту й обрізає його; фікс зробить із нього "
                "горизонтальну смугу вгорі"),
    "logo": ("напис бренду в лого не вміщається у квадрат під іконку — текст "
             "вилазить за коробку й лізе на перший пункт меню (заміряно: "
             "коробка 48px, текст 85px, перекриття 14px); фікс дасть лого "
             "міритись за вмістом"),
}


def run_branch(files, all_paths):
    issues = []
    for path in sorted(files):
        text = files[path]
        for m, _tag, kind in _hits(text):
            issues.append({
                "path": path, "line": text.count("\n", 0, m.start()) + 1,
                "severity": "error", "message": MSG[kind]})
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    actions = []
    for path in sorted(files):
        text = files[path]
        out, last, changed = [], 0, False
        for m, tag, kind in _hits(text):
            attrs = (_sub_class(m.group("attrs"), _to_topbar)
                     if kind == "sidebar" else m.group("attrs"))
            body = _fix_body(m.group("body"))
            out.append(text[last:m.start()])
            out.append(f"<{tag}{attrs}>{body}</{tag}>")
            last = m.end()
            changed = True
        if not changed:
            continue
        out.append(text[last:])
        actions.append({"type": "edit", "path": path, "content": "".join(out)})
    return actions
