"""Відносні шляхи до асетів на вайті, який віддає дочірні URL.

Вайт розгортається у корінь домену, а сервер віддає ту саму сторінку на будь-який
шлях. Тоді відносний `href="css/style.css"` резолвиться не від кореня, а від
БАЗИ поточного URL, і на дочірній адресі перетворюється у 404 - сторінка
лишається без стилів, без скриптів і без картинок.

Заміряно на живому `cheripge.sbs`:

    /                              -> css/…  ->  /css/…                      200
    /imoveis/brasil/               -> css/…  ->  /imoveis/brasil/css/…        404

І на `abzuiefe.sbs`, де видно, що ламає саме база URL, а не наявність файлу:

    /administradora-de-condominios   (без слеша) -> база `/`    -> /css/…     200
    /administradora-de-condominios/  (зі слешем) -> база того ж -> …/css/…    404

Тобто база лишається коренем лише для ОДНОСЕГМЕНТНОГО шляху без слеша. Усе, що
кінчається слешем або має 2+ сегменти, зсуває базу - і всі відносні асети
падають. Саме тому дефект видно «на всіх дочірніх сторінках».

Коли правило НЕ діє. Якщо вітка не має дочірніх URL (усі її лінки ведуть на
реальні файли), відносні шляхи коректні й нічого не чіпаємо: це звичайний
багатофайловий вайт, де сторінка й асети лежать поруч. Ознака дочірнього URL -
root-абсолютний лінк, який зсуває базу і якому НЕ відповідає файл у вітці:
значить, його віддає catch-all сервера.

Автофікс робить шляхи root-абсолютними (`css/x.css` -> `/css/x.css`), і лише
коли файл справді існує за резолвом від сторінки. Битих лінків не чіпаємо -
ними володіють `css_integrity` і `media_integrity`.
"""
import posixpath
import re

NAME = "Асети: відносні шляхи на вайті з дочірніми URL"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"domain"}
PROJECTS = ["php"]
DESCRIPTION = ("Вітка віддає дочірні URL (catch-all), а асети прописані відносно "
               "сторінки - на дочірній адресі база зсувається і css/js/картинки "
               "дають 404. Автофікс робить шляхи root-абсолютними.")
FILES = ["*.html", "*.php"]

# теги, чиї шляхи резолвить БРАУЗЕР від бази URL (саме вони й ламаються)
ASSET_RX = re.compile(
    r"""<(?P<tag>link|script|img|source|video|audio|iframe)\b"""
    r"""(?P<attrs>(?:[^>"']|"[^"]*"|'[^']*')*)>""", re.I)
ATTR_RX = re.compile(
    r"""\b(?P<name>src|href|poster)\s*=\s*(?P<q>["'])(?P<v>[^"']*)(?P=q)""", re.I)
A_RX = re.compile(
    r"""<a\b[^>]*?\bhref\s*=\s*["'](?P<v>/[^"'#]*)["']""", re.I)

SKIP_PREFIX = ("http://", "https://", "//", "data:", "mailto:", "tel:",
               "javascript:", "#", "{{", "<?")


def _is_relative(v: str) -> bool:
    v = v.strip()
    if not v or v.startswith("/"):
        return False
    return not v.lower().startswith(SKIP_PREFIX)


def _shifts_base(url: str) -> bool:
    """Чи зсуває цей URL базу для відносних шляхів.

    База лишається коренем тільки в односегментного шляху без слеша:
    `/kontakt` -> база `/`. А `/kontakt/` і `/a/b` -> база вже не корінь.
    """
    path = url.split("?")[0]
    body = path.strip("/")
    if not body:
        return False
    return path.endswith("/") or "/" in body


def _child_urls(files: dict, all_paths) -> list[str]:
    """URL-и, які віддає catch-all: зсувають базу і файлу під них немає."""
    have = set(all_paths or files)
    out = []
    for text in files.values():
        for m in A_RX.finditer(text):
            url = m.group("v").split("?")[0]
            if not _shifts_base(url):
                continue
            body = url.strip("/")
            if body in have or f"{body}/index.html" in have or \
                    f"{body}/index.php" in have:
                continue                       # це справжня сторінка вітки
            out.append(url)
    return sorted(set(out))


def _resolved(page: str, ref: str) -> str:
    """Шлях від кореня вітки, як його бачив би сервер для сторінки в корені."""
    base = posixpath.dirname(page)
    return posixpath.normpath(posixpath.join(base, ref.split("?")[0].split("#")[0]))


def _refs(text: str):
    """(абс_початок_значення, значення) кожного відносного асет-шляху."""
    for m in ASSET_RX.finditer(text):
        for a in ATTR_RX.finditer(m.group("attrs")):
            v = a.group("v")
            if _is_relative(v):
                yield m.start("attrs") + a.start("v"), v


# Catch-all віддає рівно ОДНУ сторінку - точку входу вітки. Справжні сторінки
# сервер віддає за їхнім власним шляхом, де відносні посилання коректні, тож
# чіпати їх нема за що: у `augifetoub-hocornejn-br-pt` це була б правка 43410
# посилань у 299 файлах замість 16 в одному, з тим самим результатом для
# користувача.
ENTRY = ("index.html", "index.php")


def _entry(files: dict) -> str | None:
    return next((n for n in ENTRY if n in files), None)


def run_branch(files, all_paths):
    page = _entry(files)
    if page is None:
        return []
    children = _child_urls(files, all_paths)
    if not children:
        return []                              # дочірніх URL немає - шляхи коректні
    have = set(all_paths or files)
    text = files[page]
    hits = {}
    for pos, ref in _refs(text):
        if _resolved(page, ref) in have:
            hits.setdefault(ref, text.count("\n", 0, pos) + 1)
    if not hits:
        return []
    return [{
        "path": page, "line": min(hits.values()), "severity": "error",
        "message": (f"{len(hits)} асетів точки входу прописані відносно сторінки, "
                    f"а вітка віддає дочірні URL ({len(children)}, напр. "
                    f"{children[0]}) - там база зсувається і вони дають 404 "
                    f"(сторінка без стилів); фікс зробить шляхи від кореня"),
    }]


def fix_branch(files, all_paths, branch: str = ""):
    page = _entry(files)
    if page is None or not _child_urls(files, all_paths):
        return []
    have = set(all_paths or files)
    text = files[page]
    out, last, changed = [], 0, False
    for pos, ref in _refs(text):
        target = _resolved(page, ref)
        if target not in have:
            continue                           # битий лінк - не наша справа
        out.append(text[last:pos])
        out.append("/" + target)
        last = pos + len(ref)
        changed = True
    if not changed:
        return []
    out.append(text[last:])
    return [{"type": "edit", "path": page, "content": "".join(out)}]
