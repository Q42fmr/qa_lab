"""Хедер має бути клікабельним: лого веде на головну, CTA — це лінк, не кнопка.

Дві поломки, які видно очима, але не бачить жоден чек — і обидві про те, що
елемент хедера виглядає навігаційним, а насправді нікуди не веде.

**(1) Лого без посилання.** `<div class="logo">CazatutDC</div>` — текст є,
клік не працює. Повернення на головну з логотипа — базова навігація, і в
решті вайтів корпусу лого справді загорнуте в `<a href="./">`. Фікс огортає
елемент лінком на index вітки, нічого всередині не чіпаючи.

**(2) CTA-кнопка замість лінка.** `<button class="cta">Solicitar Orçamento
</button>` у хедері: кнопка без форми і без обробника — мертва. Фікс міняє
тег на `<a>` з посиланням на контактну сторінку.

Друге правило навмисно ВУЗЬКЕ, бо `<button>` у хедері здебільшого
легітимний, і на корпусі видно всі його ролі:
  * `☰`, `✕`, `A+` — бургер, закриття, розмір шрифту (гліф або UI-слово);
  * `Search`/`Pesquisar` з `type=submit` усередині `<form>` — справжня форма;
  * ШІСТЬ кнопок у хедері `dihaahihjukiwuw-dpu`: «Атuação», «Internacional»,
    «Ações» — це випадайне меню, а не CTA. Перетворити їх на лінки означало б
    зламати навігацію, тож коли кандидатів більше одного — не чіпаємо взагалі;
  * `aria-expanded`/`data-*-toggle`/`onclick` — теж тогл, а не перехід.
Після цих відсіювань лишаються рівно CTA: «Solicitar Orçamento», «Reservar
Agora», «Agendar» — 4 вітки корпусу, і в кожній є контактна сторінка.

Ціль CTA шукається без вгадування: спершу сторінка-контакт (назва зі
словника локалей), інакше — сторінка з `<form>`, і тоді лінк веде прямо на
форму (`#id`, якщо в неї є id). Немає ні того, ні того — репортимо без фікса.
"""
import posixpath
import re
import unicodedata

NAME = "Хедер: лого і CTA клікабельні"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Лого в хедері має бути посиланням на головну, а CTA — тегом <a>, "
               "а не мертвою <button>. Автофікс огортає лого в <a href=index> і "
               "міняє кнопку на лінк до контактної сторінки (або до сторінки з "
               "формою). Бургери, тогли, кнопки форм і випадайні меню не чіпаються.")
FILES = ["*.html", "*.htm", "*.php"]

HEADER_RX = re.compile(r"<header\b.*?</header\s*>", re.S | re.I)
A_RX = re.compile(r"<a\b[^>]*>.*?</a\s*>", re.S | re.I)
LOGO_RX = re.compile(
    r"""<(?P<tag>div|span|p|h1|h2)\b[^>]*\bclass\s*=\s*["'][^"']*\b(?:logo|brand)\b"""
    r"""[^"']*["'][^>]*>(?P<inner>.*?)</(?P=tag)\s*>""", re.S | re.I)
BUTTON_RX = re.compile(r"<button\b(?P<attrs>[^>]*)>(?P<inner>.*?)</button\s*>",
                       re.S | re.I)
TAG_RX = re.compile(r"<[^>]+>")
FORM_ID_RX = re.compile(r"""<form\b[^>]*\bid\s*=\s*["']([^"']+)["']""", re.I)
FORM_RX = re.compile(r"<form\b", re.I)
LETTER_RX = re.compile(r"[^\W\d_]", re.U)

# тогл, а не перехід: у такої кнопки є стан або обробник
TOGGLE_ATTR_RX = re.compile(
    r"""\b(?:aria-expanded|aria-controls|aria-haspopup|onclick|data-toggle|
        data-bs-toggle|data-target|data-bs-target|data-collapse)\b""", re.I | re.X)
# UI-контрол: гліф або службове слово будь-якою з мов корпусу
UI_WORDS = ("close", "fermer", "cerrar", "fechar", "schliessen", "schließen",
            "search", "pesquisar", "buscar", "recherche", "suche", "menu",
            "menü", "toggle navigation", "abrir", "open")
GLYPH_ONLY_RX = re.compile(r"^[\W\d_]+$", re.U)
MAX_UI_LEN = 2          # «A», «A+» — кнопки розміру шрифту

CONTACT_WORDS = ("contact", "contacts", "contato", "contatos", "contacto",
                 "contactos", "contatti", "kontakt", "kontakte", "kontakty",
                 "contactez", "contactenos", "kapcsolat", "iletisim")
INDEX_NAMES = ("index.html", "index.htm", "index.php")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.casefold() if c.isalnum())


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", TAG_RX.sub(" ", html)).strip()


def _is_ui_button(attrs: str, inner: str) -> bool:
    """Кнопка, яку чіпати НЕ можна: тогл, форма або UI-контрол."""
    if TOGGLE_ATTR_RX.search(attrs) or re.search(r"""type\s*=\s*["']submit""",
                                                 attrs, re.I):
        return True
    txt = _text(inner)
    if not txt or GLYPH_ONLY_RX.match(txt) or len(txt) <= MAX_UI_LEN:
        return True
    return _norm(txt) in {_norm(w) for w in UI_WORDS}


def _in_form(header: str, pos: int) -> bool:
    before = header[:pos].lower()
    return "<form" in before and "</form" not in before.rsplit("<form", 1)[-1]


def _index_of(all_paths) -> str | None:
    low = {p.lower(): p for p in all_paths}
    return next((low[n] for n in INDEX_NAMES if n in low), None)


def _contact_target(all_paths, files: dict) -> str | None:
    """Сторінка-контакт, інакше сторінка з формою (+ якір на саму форму)."""
    pages = [p for p in all_paths if p.lower().endswith((".html", ".htm", ".php"))]
    for p in sorted(pages):
        stem = posixpath.basename(p).rsplit(".", 1)[0]
        if _norm(stem) in {_norm(w) for w in CONTACT_WORDS}:
            return p
    for p in sorted(pages):
        text = files.get(p)
        if not text or not FORM_RX.search(text):
            continue
        fid = FORM_ID_RX.search(text)
        return f"{p}#{fid.group(1)}" if fid else p
    return None


def _rel(target: str, page: str) -> str:
    base = posixpath.dirname(page)
    if not base:
        return target
    path, _, frag = target.partition("#")
    out = posixpath.relpath(path, base)
    return f"{out}#{frag}" if frag else out


def _unlinked_logo(header: str):
    """(match) лого, з якого НЕ можна клікнути на головну, або None.

    Не клікабельне означає дві різні речі, і обидві треба відсіяти:
    лого лежить усередині `<a>` (нормальний випадок) або САМЕ МІСТИТЬ `<a>`
    (`<div class="site-logo"><a href="/">Бренд</a></div>` — теж робоче).
    Без другої умови фікс огортав би лінк лінком і давав `<a><div><a>…`,
    тобто невалідний HTML замість виправлення."""
    spans = [m.span() for m in A_RX.finditer(header)]
    for m in LOGO_RX.finditer(header):
        if any(a <= m.start() < b for a, b in spans):
            continue
        inner = m.group("inner")
        if re.search(r"<a\b[^>]*\bhref\s*=", inner, re.I):
            continue                     # лого вже саме є посиланням
        if not LETTER_RX.search(_text(inner)):
            continue                     # порожній контейнер — не лого
        return m
    return None


def _cta_button(header: str):
    """Єдина кнопка-CTA у хедері, або None. Кілька кандидатів — це випадайне
    меню, і його не чіпаємо."""
    hits = [m for m in BUTTON_RX.finditer(header)
            if not _is_ui_button(m.group("attrs"), m.group("inner"))
            and not _in_form(header, m.start())]
    return hits[0] if len(hits) == 1 else None


def run_branch(files, all_paths, branch: str = ""):
    index = _index_of(all_paths)
    contact = _contact_target(all_paths, files)
    issues = []
    for page in sorted(files):
        text = files[page]
        hm = HEADER_RX.search(text)
        if not hm:
            continue
        header, off = hm.group(0), hm.start()
        logo = _unlinked_logo(header)
        if logo and index:
            issues.append({
                "path": page, "line": text.count("\n", 0, off + logo.start()) + 1,
                "severity": "error",
                "message": (f"лого «{_text(logo.group('inner'))[:40]}» не є "
                            f"посиланням — з нього не повернутись на головну; "
                            f"фікс огорне в <a href=\"{_rel(index, page)}\">")})
        btn = _cta_button(header)
        if btn:
            label = _text(btn.group("inner"))[:40]
            if contact:
                issues.append({
                    "path": page,
                    "line": text.count("\n", 0, off + btn.start()) + 1,
                    "severity": "error",
                    "message": (f"CTA «{label}» — <button> без форми й обробника, "
                                f"тобто мертва; фікс зробить з неї "
                                f"<a href=\"{_rel(contact, page)}\">")})
            else:
                issues.append({
                    "path": page,
                    "line": text.count("\n", 0, off + btn.start()) + 1,
                    "severity": "error",
                    "message": (f"CTA «{label}» — <button> без форми й обробника; "
                                f"у вітці немає ні контактної сторінки, ні форми, "
                                f"тож куди вести — вирішувати руками")})
    return issues


def _swap_button(btn: re.Match, href: str) -> str:
    """<button …>x</button> → <a href="…" …>x</a>; атрибути лишаються, крім
    button-специфічного type."""
    attrs = re.sub(r"""\s*\btype\s*=\s*(?:"[^"]*"|'[^']*'|\S+)""", "",
                   btn.group("attrs"), flags=re.I).strip()
    attrs = (" " + attrs) if attrs else ""
    return f'<a href="{href}"{attrs}>{btn.group("inner")}</a>'


def fix_branch(files, all_paths, branch: str = ""):
    index = _index_of(all_paths)
    contact = _contact_target(all_paths, files)
    actions = []
    for page in sorted(files):
        text = files[page]
        hm = HEADER_RX.search(text)
        if not hm:
            continue
        header, off = hm.group(0), hm.start()
        edits = []
        logo = _unlinked_logo(header)
        if logo and index:
            edits.append((logo.start(), logo.end(),
                          f'<a href="{_rel(index, page)}">{logo.group(0)}</a>'))
        btn = _cta_button(header)
        if btn and contact:
            edits.append((btn.start(), btn.end(),
                          _swap_button(btn, _rel(contact, page))))
        if not edits:
            continue
        out, last = [], 0
        for start, end, repl in sorted(edits):
            out.append(header[last:start])
            out.append(repl)
            last = end
        out.append(header[last:])
        new_header = "".join(out)
        actions.append({"type": "edit", "path": page,
                        "content": text[:off] + new_header + text[hm.end():]})
    return actions
