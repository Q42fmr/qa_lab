"""Правила меню хедера (desktop): пусте меню + мобільна шухляда на десктопі.

Ці два правила потрібні у двох місцях, які працюють з тим самим HTML у різний
час: чеку `checks/empty_menu.py` у qa_lab (ганяється по GitLab-вайтах ПІСЛЯ
деплою) і пайплайну локальних вайтів (сервіс local_setter_whites, працює з
локальними файлами ДО деплою). Обидва мусять давати однаковий результат на
однаковому HTML — інакше вайт, який пройшов локальний чек, може впасти на
GitLab-чеку чи навпаки. Раніше код жив прямо в local_whites.py й дублювався
копіпастою; тепер це окремий модуль, який qa_lab імпортує як залежність
чека, а local_setter_whites тримає в себе БАЙТ-У-БАЙТ ІДЕНТИЧНОЮ копією
(два окремих репо, спільного пакета між ними немає). Синхронізуй обидві
копії руками при будь-якій правці цього файлу.
"""
import re

# ------------------------------------------------------------------ пусте меню (desktop)
# Кейс tagdocaa: єдиний <nav id="mobile-menu"> на обидва меню, а базовий CSS
# `#mobile-menu{display:none}` ховає його і на десктопі (id б'є tailwind-класи
# по специфічності) — хедер лишається без меню. Другий варіант — nav (чи його
# контейнер) з md:hidden без десктопного дубля. Фікси відповідно:
# 1) прибрати id, який CSS ховає; 2) md:hidden → hidden md:flex.
_HEADER_BLOCK_RX = re.compile(r"<header\b[\s\S]*?</header\s*>", re.I)
_COMMENT_RX = re.compile(r"<!--[\s\S]*?-->")
_TAG_RX = re.compile(r"""<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>""")
# тіла <script>/<style> при пошуку nav-ів поза хедером глушимо: рядки з JS
# дають фантомні теги, а CSS уже розібраний окремо (_css_visibility)
_SCRIPT_STYLE_RX = re.compile(r"<(script|style)\b[\s\S]*?</\1\s*>", re.I)
# nav у цих контейнерах — не меню сайта, а зміст сторінки / legal-лінки
_NON_CHROME_TAGS = frozenset({"main", "article", "section", "aside", "footer"})
_MAXW_MEDIA_RX = re.compile(r"@media[^{]*\bmax-width\b[^{]*\{(?:[^{}]|\{[^{}]*\})*\}")
_MINW_MEDIA_RX = re.compile(r"@media[^{]*\bmin-width\b[^{]*\{((?:[^{}]|\{[^{}]*\})*)\}")
_HIDDEN_ID_RULE_RX = re.compile(r"(?:^|[\s,{}])#([\w-]+)\s*\{[^{}]*\bdisplay\s*:\s*none\b")
_SHOWN_ID_RULE_RX = re.compile(
    r"(?:^|[\s,{}])#([\w-]+)\s*\{[^{}]*\bdisplay\s*:\s*(?!none\b)[a-z-]+")
# display-стан рахуємо на «десктопі» 1280px: діють base + sm/md/lg/xl (2xl — ні)
_BREAKPOINTS = ("sm", "md", "lg", "xl")
_DISPLAY_TOKENS = ("hidden", "flex", "block", "grid", "inline-flex",
                   "inline-block", "inline", "table", "contents")
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
              "link", "meta", "param", "source", "track", "wbr"}
_STYLE_TAG_RX = re.compile(r"""<style([^>]*)>([\s\S]*?)</style>""", re.I)


def _attr_value(tag: str, name: str) -> str | None:
    m = re.search(r"(?<![\w-])" + name + r"""\s*=\s*("[^"]*"|'[^']*')""", tag, re.I)
    return m.group(1)[1:-1] if m else None


_SHOWN_CLS_RULE_RX = re.compile(
    r"(?:^|[\s,{}])\.([\w-]+)\s*\{[^{}]*\bdisplay\s*:\s*(?!none\b)[a-z-]+\s*!important")
_SHOWN_ID_IMP_RULE_RX = re.compile(
    r"(?:^|[\s,{}])#([\w-]+)\s*\{[^{}]*\bdisplay\s*:\s*(?!none\b)[a-z-]+\s*!important")
_JS_ID_RX = re.compile(r"""getElementById\(\s*['"]([\w-]+)['"]""")


def _css_visibility(text: str) -> dict:
    """Контекст видимості на десктопі.

    hidden_ids — id з базовим display:none (max-width @media не рахуємо) БЕЗ
    display-повернення у min-width @media (патерн `#desktop-nav{display:none}`
    + `@media(min-width){#desktop-nav{display:flex}}`).
    shown_cls / shown_ids — класи/id, які min-width @media показує
    display:<non-none> !important: б'є і tailwind-утиліту .hidden, і inline
    style="display:none" (кейси bazito / heoxbaug-atgab).
    js_ids — id, які показує width-driven JS (кейс muvohui: getElementById +
    innerWidth + .style.display='flex'); перебиває лише inline display:none."""
    css = "\n".join(m.group(2) for m in _STYLE_TAG_RX.finditer(text))
    css = _MAXW_MEDIA_RX.sub(" ", css)
    reshown_ids: set[str] = set()
    shown_cls: set[str] = set()
    shown_ids: set[str] = set()
    for m in _MINW_MEDIA_RX.finditer(css):
        reshown_ids.update(_SHOWN_ID_RULE_RX.findall(m.group(1)))
        shown_cls.update(_SHOWN_CLS_RULE_RX.findall(m.group(1)))
        shown_ids.update(_SHOWN_ID_IMP_RULE_RX.findall(m.group(1)))
    js_ids: set[str] = set()
    if re.search(r"innerWidth|matchMedia", text) and ".style.display" in text:
        js_ids = set(_JS_ID_RX.findall(text))
    return {"hidden_ids": set(_HIDDEN_ID_RULE_RX.findall(css)) - reshown_ids,
            "shown_cls": shown_cls, "shown_ids": shown_ids, "js_ids": js_ids}


def _class_hidden_desktop(cls: str, shown_cls: set[str] = frozenset()) -> bool:
    """Каскад tailwind-display на 1280px: base, потім sm→md→lg→xl (більший
    брейкпоінт перекриває). На одному рівні hidden б'є решту display-токенів
    незалежно від порядку в атрибуті — у стилях tailwind .hidden іде останнім
    (кейс `md:flex … md:hidden`). Без display-токенів — елемент видимий;
    клас із shown_cls повертає видимість через !important-@media."""
    tokens = cls.split()
    if shown_cls and any(t in shown_cls for t in tokens):
        return False

    def level(prefix: str):
        found = [t[len(prefix):] for t in tokens
                 if t.startswith(prefix) and t[len(prefix):] in _DISPLAY_TOKENS]
        if not found:
            return None
        return "hidden" if "hidden" in found else found[-1]

    state = None
    for pref in ("",) + tuple(bp + ":" for bp in _BREAKPOINTS):
        got = level(pref)
        if got is not None:
            state = got
    return state == "hidden"


_STYLE_DISPLAY_RX = re.compile(r"display\s*:\s*([a-zA-Z-]+)")


def _desktop_hidden(attrs: str, vis: dict) -> bool:
    el_id = _attr_value(attrs, "id")
    cls = _attr_value(attrs, "class") or ""
    disp = _STYLE_DISPLAY_RX.findall(_attr_value(attrs, "style") or "")
    if disp:                    # inline style б'є і #id-правила, і класи
        if disp[-1].lower() != "none":
            return False
        if el_id and (el_id in vis["shown_ids"] or el_id in vis["js_ids"]):
            return False        # !important-@media або width-JS розховує
        return not any(t in vis["shown_cls"] for t in cls.split())
    if el_id and el_id in vis["hidden_ids"]:
        return True
    return _class_hidden_desktop(cls, vis["shown_cls"])


def _scan_navs(block: str, base: int, vis: dict) -> list[dict]:
    """nav-и в межах block: span open-тега, чи прихований на десктопі
    (сам або через предка), span-и тегів, які його ховають, чи є лінки.
    base — зсув block у документі, щоб span-и лишались абсолютними."""
    comments = [c.span() for c in _COMMENT_RX.finditer(block)]
    stack: list[tuple[str, bool, tuple[int, int]]] = []
    navs: list[dict] = []
    for tm in _TAG_RX.finditer(block):
        if any(a <= tm.start() < b for a, b in comments):
            continue
        closing, tag, attrs = tm.group(1), tm.group(2).lower(), tm.group(3)
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    del stack[i:]
                    break
            continue
        if tag in _VOID_TAGS or attrs.rstrip().endswith("/"):
            continue
        hidden = _desktop_hidden(attrs, vis)
        span = (base + tm.start(), base + tm.end())
        if tag == "nav":
            hidden_tags = [s for _, h, s in stack if h]
            if hidden:
                hidden_tags.append(span)
            inner = block[tm.end():]
            close = inner.find("</nav")
            if close >= 0:
                inner = inner[:close]
            navs.append({"span": span, "hidden": bool(hidden_tags),
                         "hidden_tags": hidden_tags,
                         "anc": frozenset(t for t, _, _ in stack),
                         "links": re.search(r"<a[\s>]", inner, re.I) is not None})
        stack.append((tag, hidden, span))
    return navs


_HREF_RX = re.compile(r"""href\s*=\s*("[^"]*"|'[^']*')""", re.I)
# лого-лінк на головну: він є завжди і меню не робить
_BRAND_HREF_RX = re.compile(r"^(?:\.?/|\.?/?index\.(?:html?|php))$", re.I)
# скільки видимих пунктів уже вважаємо меню (у корпусі справжні меню мають 4+,
# а хедери без меню — рівно один лінк на ./#contact)
_MENU_MIN_LINKS = 2


def _desktop_menu_links(header: str, vis: dict) -> list[str]:
    """Пункти меню, ВИДИМІ на десктопі: лінки на сторінки, не сховані ні
    самі, ні через предка. Відкидаємо лого-хом, tel:/mailto: і чисті якорі —
    вони є і там, де меню немає зовсім.

    Потрібно, бо меню далеко не завжди <nav>: у половини шаблонів це
    <div class="hidden md:flex"> з лінками (boigavant-br-pt та ще 4 вітки).
    Без цієї перевірки чек вважав, що десктоп-меню немає, і «фікс»
    розховував мобільну шухляду просто в хедер.
    """
    out: list[str] = []
    stack: list[tuple[str, bool]] = []
    for tm in _TAG_RX.finditer(header):
        closing, tag, attrs = tm.group(1), tm.group(2).lower(), tm.group(3)
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    del stack[i:]
                    break
            continue
        void = tag in _VOID_TAGS or attrs.rstrip().endswith("/")
        hidden = _desktop_hidden(attrs, vis) or any(h for _, h in stack)
        if tag == "a" and not hidden:
            hm = _HREF_RX.search(attrs)
            if hm:
                href = hm.group(1)[1:-1].strip()
                low = href.lower()
                if (href and not low.startswith(("tel:", "mailto:", "javascript:", "#"))
                        and "#" not in href and not _BRAND_HREF_RX.match(href)):
                    out.append(href)
        if not void:
            stack.append((tag, hidden))
    return out


def _header_nav_scan(text: str) -> tuple[list[dict], dict]:
    """nav-и першого <header> + контекст видимості документа."""
    hm = _HEADER_BLOCK_RX.search(text)
    if not hm:
        return [], {}
    vis = _css_visibility(text)
    return _scan_navs(hm.group(0), hm.start(), vis), vis


def check_empty_menu(text: str) -> list[str]:
    """Пусте десктоп-меню: у <header> є nav-и, але жоден не видимий на десктопі
    — і поза хедером десктопного меню теж немає."""
    navs, vis = _header_nav_scan(text)
    if not navs or any(not n["hidden"] for n in navs):
        return []
    # Меню далеко не завжди <nav>: у боїтати та ще 4 віток це
    # <div class="hidden md:flex"> з чотирма лінками. Якщо на десктопі
    # видно пункти меню — хедер робочий, розховувати нічого.
    hm = _HEADER_BLOCK_RX.search(text)
    if hm and len(set(_desktop_menu_links(hm.group(0), vis))) >= _MENU_MIN_LINKS:
        return []
    # сайдбар-лейаути (gecabhzai-ch-de, sumewab-seqxolioh-co-es) тримають
    # мобільний хедер під lg:hidden, а головне меню виносять окремим
    # <nav class="hidden lg:flex"> у колонку контенту: на десктопі меню є,
    # розховувати хедер не треба — інакше «фікс» дає два хедери на десктопі
    # й жодного на мобільному. Nav-и всередині main/aside/footer/section —
    # це зміст сторінки чи legal-лінки, а не меню сайта: вони не рахуються.
    body = _SCRIPT_STYLE_RX.sub(lambda m: " " * len(m.group(0)), text)
    if any(not n["hidden"] and n["links"] and not (n["anc"] & _NON_CHROME_TAGS)
           for n in _scan_navs(body, 0, vis)):
        return []
    return ["no desktop-visible nav in <header>"]


def _unhide_tag(tag: str, vis: dict, counts: dict) -> str:
    el_id = _attr_value(tag, "id")
    if el_id and el_id in vis["hidden_ids"]:
        tag = re.sub(r"""\s+id\s*=\s*("[^"]*"|'[^']*')""", "", tag, count=1)
        counts["Empty menu: remove hidden id"] = \
            counts.get("Empty menu: remove hidden id", 0) + 1

    def _cls(m):
        cls = m.group(2)
        if not _class_hidden_desktop(cls, vis["shown_cls"]):
            return m.group(0)
        bp_hidden = tuple(bp + ":hidden" for bp in _BREAKPOINTS)
        classes = m.group(2).split()
        if any(c in bp_hidden for c in classes):
            classes = ["hidden md:flex" if c in bp_hidden else c for c in classes]
        else:                                   # голий hidden без re-show
            classes = ["hidden md:flex" if c == "hidden" else c for c in classes]
        counts["Empty menu: md:hidden → hidden md:flex"] = \
            counts.get("Empty menu: md:hidden → hidden md:flex", 0) + 1
        return m.group(1) + " ".join(classes) + m.group(3)

    return re.sub(r'((?<![\w-])class\s*=\s*")([^"]*)(")', _cls, tag, count=1)


def fix_empty_menu(text: str) -> tuple[str, dict]:
    """Розховує головний nav хедера, коли десктоп-меню пусте. Умовний фікс:
    нічого не чіпає, поки check_empty_menu не спрацював (нормальні вайти
    з окремим mobile-menu лишаються як є)."""
    if not check_empty_menu(text):
        return text, {}
    navs, vis = _header_nav_scan(text)
    target = next((n for n in navs if n["links"]), navs[0])
    counts: dict[str, int] = {}
    for start, end in sorted(set(target["hidden_tags"]), reverse=True):
        new_tag = _unhide_tag(text[start:end], vis, counts)
        text = text[:start] + new_tag + text[end:]
    return text, counts


# --------------------------------------------- мобільна шухляда на десктопі
# Зворотний бік попереднього фікса. Мобільне меню в цих шаблонах — вертикальна
# шухляда під хедером. Якщо їй дописати `bp:flex`, на десктопі вона
# розкривається стовпчиком під шапкою поверх нормального меню (кейси
# boigavant-br-pt і peharlu-br-pt: саме це зробив фікс «голий hidden →
# hidden md:flex», не побачивши меню у <div>).
#
# Шухляда — НЕ обов'язково <nav> і не обов'язково `flex-col` на самому тегу:
# у peharlu це <div class="border-t … hidden flex"> з <nav class="flex
# flex-col"> усередині. Ознака — вертикальний стек НА СОБІ АБО В НАЩАДКУ;
# на 55 вітках, де в хедері є і шухляда, і десктоп-меню, вона розділила їх
# зі 100% точністю (у справжнього десктоп-меню flex-col немає ніде).
#
# Адаптивний `flex-col md:flex-row` — НЕ цей випадок: він навмисно
# вертикальний на мобільному і горизонтальний на десктопі (у кеші таких 30).
_BP_FLEX_RX = re.compile(r"(?<![\w-])(?:sm|md|lg|xl|2xl):flex(?![\w-])")
_BP_ROW_RX = re.compile(r"(?<![\w-])(?:sm|md|lg|xl|2xl):flex-row(?![\w-])")


def _drawer_on_desktop(text: str):
    """(span тега, класи) вертикальної шухляди, показаної на десктопі, або None.

    Репортимо лише коли в хедері Є справжнє десктоп-меню: інакше прибрати
    показ означало б лишити десктоп зовсім без навігації."""
    hm = _HEADER_BLOCK_RX.search(text)
    if not hm:
        return None
    header, base = hm.group(0), hm.start()
    vis = _css_visibility(text)
    stack: list[tuple[str, int, int, str]] = []
    for tm in _TAG_RX.finditer(header):
        closing, tag, attrs = tm.group(1), tm.group(2).lower(), tm.group(3)
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] != tag:
                    continue
                _t, open_s, inner_s, cls = stack[i]
                del stack[i:]
                inner = header[inner_s:tm.start()]
                block = header[open_s:tm.end()]
                # вертикальний стек на собі або в нащадку
                if "flex-col" not in cls and "flex-col" not in inner:
                    break
                if not _BP_FLEX_RX.search(cls) or _BP_ROW_RX.search(cls):
                    break                 # адаптивний — не чіпаємо
                if not re.search(r"<a[\s>]", block, re.I):
                    break                 # порожня шухляда нікому не заважає
                rest = header[:open_s] + header[tm.end():]
                if len(set(_desktop_menu_links(rest, vis))) < _MENU_MIN_LINKS:
                    break                 # іншого меню немає — лишаємо як є
                return (base + open_s, base + inner_s), cls
            continue
        if tag in _VOID_TAGS or attrs.rstrip().endswith("/"):
            continue
        stack.append((tag, tm.start(), tm.end(),
                      _attr_value(tm.group(0), "class") or ""))
    return None


def check_drawer_on_desktop(text: str) -> list[str]:
    got = _drawer_on_desktop(text)
    if not got:
        return []
    bp = _BP_FLEX_RX.findall(got[1]) or ["md:flex"]
    return [f"mobile drawer shown on desktop ({bp[0]}) — vertical menu over the header"]


def fix_drawer_on_desktop(text: str) -> tuple[str, dict]:
    """`bp:flex` -> звичайний `flex`, `hidden` лишається.

    Саме заміна, а не видалення: `hidden` б'є `flex` (у Tailwind `.hidden`
    йде у стилях пізніше), тож на десктопі шухляди немає. А коли бургер зніме
    `hidden`, лишиться `display:flex` — з голим `hidden` елемент відкрився б
    як `block` і верстка меню поїхала б (перевірено в браузері)."""
    got = _drawer_on_desktop(text)
    if not got:
        return text, {}
    (start, end), _cls = got
    tag = text[start:end]

    def _swap(m):
        kept = [c for c in m.group(2).split() if not _BP_FLEX_RX.fullmatch(c)]
        if "flex" not in kept:          # був лише bp:flex — ставимо звичайний
            kept.append("flex")
        if "hidden" not in kept:
            kept.insert(0, "hidden")
        return m.group(1) + " ".join(kept) + m.group(3)

    new_tag = re.sub(r'((?<![\w-])class\s*=\s*")([^"]*)(")', _swap, tag, count=1)
    if new_tag == tag:
        return text, {}
    return (text[:start] + new_tag + text[end:],
            {"Mobile drawer: bp:flex -> flex": 1})
