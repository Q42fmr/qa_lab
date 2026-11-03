"""Мініатюри з js-мапи: файла немає (13.10, ch-de партія).

Кошик/merkliste рендерить мініатюри з js-мапи
`IMG={"slug":"p2.jpg",…}` + `src='../assets/img/'+IMG[slug]`, а на диску
лежать `assets/img/p2.svg` — всі мініатюри доданих у кошик курсів 404
(quugfihcinf, ervgezeaqo, regeqvupolzol, stovksemm, lernatelier).
Статичні чеки картинок (media_integrity) читають html/css і js-мап не
бачать — це їхня сліпа зона.

Детект: рядковий літерал-картинка у js (зовнішньому чи інлайновому),
якого немає серед файлів вітки ні точним шляхом, ні голим ім'ям.
Фікс: якщо той самий stem існує РІВНО з одним іншим розширенням —
літерал переписується на реальне ім'я (p2.jpg -> p2.svg). Кілька
кандидатів чи жодного — лише детект: заміна файла — ручний вибір.
"""
import posixpath
import re

NAME = "Мініатюри з js-мапи: файла немає"
GROUP = "auto"
# branch-code (branch_code.py): клієнтських даних не чіпає — лише імена
# файлів картинок у js
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("JS будує <img src> з мапи імен (кошик, merkliste, «нещодавно "
               "переглянуті»), а файлів з такими іменами у вітці немає — "
               "мініатюри 404. Фікс переписує розширення на реальне, коли "
               "stem існує рівно з одним іншим розширенням.")
FILES = ["*.js", "*.html", "*.htm", "*.php"]

IMG_EXT = ("jpg", "jpeg", "png", "webp", "avif", "svg", "gif")
# цілий рядковий літерал: ім'я або відносний шлях картинки
_LIT_RX = re.compile(
    r"""["']((?:[\w.-]+/)*[\w.-]+\.(?:jpe?g|png|webp|avif|svg|gif))["']""",
    re.I)
_SCRIPT_RX = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>",
                        re.I)


# Чужий код не судимо і не лагодимо: вендорні бандли повні службових
# літералів-привидів (elementor frontend.min.js: «-negative.svg»,
# mercadopago v2.js: «amex.svg», complianz: «placeholder.jpg» — заміряно
# на корпусі 13.10, всі 6 прикладів шуму були звідси)
_VENDOR_RX = re.compile(
    r"^_external/|^wp-content/plugins/|^wp-includes/|/node_modules/"
    r"|/vendor/|\.min\.js$", re.I)


def _is_js(path: str) -> bool:
    return path.lower().endswith(".js")


def _code_regions(path: str, text: str):
    """[(offset, код)] — весь .js або інлайн-скрипти сторінки."""
    if _VENDOR_RX.search(path):
        return []
    if _is_js(path):
        return [(0, text)]
    return [(m.start(1), m.group(1)) for m in _SCRIPT_RX.finditer(text)]


def _candidates(lit: str, by_name: dict, by_stem: dict):
    """(точний існує, [кандидати з іншим розширенням])."""
    name = posixpath.basename(lit)
    if name in by_name:
        return True, []
    stem = name.rsplit(".", 1)[0]
    return False, sorted(by_stem.get(stem.lower(), []))


def _index(all_paths):
    by_name: dict = {}
    by_stem: dict = {}
    for p in all_paths:
        n = posixpath.basename(p)
        if not re.search(r"\.(?:jpe?g|png|webp|avif|svg|gif)$", n, re.I):
            continue
        by_name.setdefault(n, []).append(p)
        by_stem.setdefault(n.rsplit(".", 1)[0].lower(), set()).add(n)
    return by_name, by_stem


def _findings(path: str, text: str, by_name: dict, by_stem: dict):
    """[(offset, літерал, [кандидати])] битих імен у коді файла."""
    out = []
    seen = set()
    for off, code in _code_regions(path, text):
        for m in _LIT_RX.finditer(code):
            lit = m.group(1)
            if lit.lower() in seen:
                continue
            exists, cands = _candidates(lit, by_name, by_stem)
            if exists:
                continue
            seen.add(lit.lower())
            out.append((off + m.start(1), lit, cands))
    return out


def run_branch(files, all_paths, branch: str = ""):
    by_name, by_stem = _index(all_paths)
    issues = []
    for path in sorted(files):
        text = files[path]
        finds = _findings(path, text, by_name, by_stem)
        if not finds:
            continue
        # судимо лише імена, чий stem РЕАЛЬНО існує з іншим розширенням:
        # це точний слід «мініатюру перейменували/переконвертували», а
        # ghost-літерали без кандидата — службовий шум бандлів
        fixable = [l for _o, l, c in finds if len(c) == 1]
        ambiguous = [l for _o, l, c in finds if len(c) > 1]
        if not fixable and not ambiguous:
            continue
        bits = []
        if fixable:
            bits.append(f"{', '.join(fixable[:4])} — на диску той самий stem "
                        f"з іншим розширенням, фікс перепише")
        if ambiguous:
            bits.append(f"{', '.join(ambiguous[:4])} — неоднозначно "
                        f"(кілька кандидатів), обери файл руками")
        issues.append({
            "path": path,
            "line": text.count("\n", 0, finds[0][0]) + 1,
            "severity": "error",
            "message": ("js будує <img> з імен, яких немає у вітці "
                        "(мініатюри кошика 404): " + "; ".join(bits)),
        })
    return issues


# Кеш домену: site.js лінкується без версії, тож зміна ВМІСТУ без зміни
# АДРЕСИ невидима на проді — браузер/CDN тримає старий js зі старою мапою
# (та сама історія, що sozsazdacg у faq_accordion). Виправлений .js
# отримує hash-ім'я site-<crc8>.js, старе ім'я видаляється, посилання по
# сторінках перетаргечуються (з ../-префіксами).
_HASH_STEM_RX = re.compile(r"-[0-9a-f]{8}$")


def _hashed_name(path: str, content: str) -> str:
    import zlib
    d, name = posixpath.split(path)
    stem, ext = posixpath.splitext(name)
    stem = _HASH_STEM_RX.sub("", stem) or stem
    out = f"{stem}-{zlib.crc32(content.encode('utf-8')) & 0xffffffff:08x}{ext}"
    return posixpath.join(d, out) if d else out


def _retarget(pages: dict, old: str, new: str):
    """{path: new_text} сторінок, що лінкували старий шлях js."""
    rx = re.compile(
        r"""(?P<pre>["'(=\s>])(?P<dots>(?:\.\./)+|\./|/|)"""
        + re.escape(old)
        + r"""(?P<v>\?v=[0-9a-f]+)?(?=["')\s>,#?])""")
    out = {}
    for p, t in pages.items():
        nt = rx.sub(lambda m: m.group("pre") + m.group("dots") + new, t)
        if nt != t:
            out[p] = nt
    return out


def fix_branch(files, all_paths, branch: str = ""):
    by_name, by_stem = _index(all_paths)
    actions = []
    edited_pages = {}
    for path in sorted(files):
        text = edited_pages.get(path, files[path])
        finds = _findings(path, text, by_name, by_stem)
        ren = {lit: cands[0] for _o, lit, cands in finds if len(cands) == 1}
        if not ren:
            continue
        new = text
        for lit, real in ren.items():
            # той самий каталог, нове ім'я: міняємо ЛИШЕ хвіст-ім'я літерала
            new_lit = posixpath.join(posixpath.dirname(lit), real) \
                if "/" in lit else real
            new = re.sub("([\"'])" + re.escape(lit) + "([\"'])",
                         lambda m, nl=new_lit: m.group(1) + nl + m.group(2),
                         new)
        if new == text:
            continue
        if _is_js(path):
            new_path = _hashed_name(path, new)
            actions.append({"type": "create", "path": new_path,
                            "content": new})
            actions.append({"type": "delete", "path": path})
            pages = {p: edited_pages.get(p, files[p]) for p in files
                     if not _is_js(p) and not _VENDOR_RX.search(p)}
            edited_pages.update(_retarget(pages, path, new_path))
        else:
            edited_pages[path] = new
    for p, t in edited_pages.items():
        actions.append({"type": "edit", "path": p, "content": t})
    return actions
