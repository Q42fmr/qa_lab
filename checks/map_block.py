"""Блок з мапою: прибрати з вайта на вимогу баєра/саппорта.

Кейс cavborel-it-it (23.10, коміт 5e70edf7): баєр попросив прибрати Google-
карту. Руками вирізано <section id="map"> («Dove ci trovi» + iframe) і лінк
«Vedi la mappa →» на contatti.html, що вів на ./#map. Чек робить те саме
детерміновано, по всій вітці.

Що вважається картою:
  * <iframe>/<embed>/<object> з адресою картового сервісу (Google Maps у
    будь-якій формі, OSM, Yandex, Bing, Mapbox, Wix-віджет googleMap) — і в
    src, і в lazy-атрибутах (data-src, data-lazy-src);
  * <iframe> з картовим класом/назвою і порожнім src (Hostinger grid-map);
  * <img> зі статичною картою (staticmap);
  * JS-карта: контейнер, який ініціалізує інлайн-скрипт (L.map, new
    google.maps.Map, new mapboxgl.Map).

Що таке «блок». Від карти йдемо вгору, поки в батьківському елементі, крім
неї, лише підписи карти: заголовки (без адреси в тексті), короткі надписи зі
словника («Localização», «Dove siamo», «Pos. 15 · Standort»), порожні обгортки,
стилі, <noscript>-двійник lazy-iframe, власний лінк «Abrir no Google Maps».
Будь-що інше — абзац з адресою/годинами, форма, картинка, сусідня колонка —
зупиняє підйом: карта йде, текст лишається. Структурні елементи (body, main,
header, footer, nav, form, комірки таблиць, aside) не вирізаються ніколи.
Коментар-заголовок блоку («<!-- MAP -->») іде разом з ним (як у partner_banks).
Tailwind-ґрид на дві колонки, де лишилась одна, стає одноколонковим.

Лінки на вирізаний блок (з будь-якої сторінки вітки):
  * текст про карту («Ver no mapa», «Auf der Karte ansehen») — лінк іде;
  * пункт меню (лінк — єдиний вміст <li>) — пункт іде;
  * лінк у реченні («pagina Home») — веде на ту саму сторінку без якоря, а на
    своїй сторінці розгортається в текст.
Якщо секція з якорем лишилась (у ній адреса), а карти в ній уже немає —
прибираються лише лінки з текстом про карту: вони обіцяють те, чого нема.

Чого фікс НЕ робить (лише warn для людини):
  * JS-карта, чий скрипт ініціалізації робить ще щось (меню, слайдер): вирізати
    скрипт — убити решту, лишити — бібліотека впаде без контейнера;
  * SPA-вайт (React/Vite), у якого та сама карта є в JS-бандлі: після
    гідратації бандл намалює її знову, правка HTML нічого не дасть.
Підключення Google Maps API / Leaflet / Mapbox прибираються лише на сторінці,
де фікс вирізав JS-карту і більше нічого картового не лишилось: iframe-картам
вони не потрібні, а чужий віджет (Divi-модуль карти) міг би на них триматись.

Група review: карта — не дефект, прибирається лише на вимогу.
"""
import html as _html
import posixpath
import re

NAME = "Карта: прибрати блок з мапою"
GROUP = "review"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"map", "links"}
PROJECTS = ["php"]
DESCRIPTION = (
    "Прибирає з вайта блок з картою на вимогу баєра: Google Maps/OSM/Yandex/"
    "Bing/Mapbox-iframe чи <embed>, Wix- і Elementor-віджет, Leaflet/Google JS-"
    "карту. Вирізає найменший елемент, у якому крім карти лише її підписи "
    "(заголовок, «Dove siamo»); абзац з адресою чи години лишаються. Лінки «Ver "
    "no mapa» на вирізаний блок ідуть, пункт меню на нього знімається, лінк у "
    "реченні веде на сторінку без якоря. JS-карту з мішаним скриптом і карту з "
    "SPA-бандла не чіпає (warn). Група review — застосовує людина.")
FILES = ["*.html", "*.htm", "*.php", "*.js"]

PAGE_EXT = (".html", ".htm", ".php")

# ------------------------------------------------------------- розбір HTML
_VOID = frozenset("area base br col embed hr img input link meta param source "
                  "track wbr".split())
# вміст цих елементів — не розмітка (або інертна розмітка): тег до тегу
_RAW = frozenset("script style textarea noscript template iframe title xmp".split())
# ці елементи не вирізаються ніколи — підйом блоку зупиняється під ними
_NEVER = frozenset("html head body main header footer nav form aside table "
                   "thead tbody tfoot tr td th".split())
_TOKEN_RX = re.compile(
    r"<!--.*?(?:-->|\Z)|<\?.*?(?:\?>|\Z)|<![^>]*>"
    r"|<(/?)([A-Za-z][\w:.-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.S)
# (?<![\w-]) — саме атрибут, а не його хвіст: `data-id`/`data-href`/`data-src`
# (Elementor, Wix) інакше читались би як id/href/src елемента
_ID_RX = re.compile(r"""(?<![\w-])id\s*=\s*["']([^"']+)["']""", re.I)
_CLASS_RX = re.compile(r"""((?<![\w-])class\s*=\s*)(["'])([^"']*)\2""", re.I)
_HREF_RX = re.compile(r"""(?<![\w-])href\s*=\s*(["'])(.*?)\1""", re.I | re.S)


class _El:
    __slots__ = ("tag", "start", "oend", "cstart", "end", "parent")

    def __init__(self, tag, start, oend, parent):
        self.tag, self.start, self.oend, self.parent = tag, start, oend, parent
        self.cstart = self.end = oend


def _parse(text: str) -> tuple[list, dict]:
    """Плаский список елементів зі спанами + діти кожного в порядку документа.
    Незакритий елемент (<p> без </p>) закривається там, де закрився батько."""
    els, stack, i, n = [], [], 0, len(text)
    while True:
        m = _TOKEN_RX.search(text, i)
        if not m:
            break
        i = m.end()
        if m.group(2) is None:
            continue                                   # коментар, php, doctype
        tag = m.group(2).lower()
        if m.group(1):                                 # закривний тег
            for k in range(len(stack) - 1, -1, -1):
                if els[stack[k]].tag == tag:
                    for j in stack[k + 1:]:
                        els[j].cstart = els[j].end = m.start()
                    els[stack[k]].cstart, els[stack[k]].end = m.start(), m.end()
                    del stack[k:]
                    break
            continue
        el = _El(tag, m.start(), m.end(), stack[-1] if stack else -1)
        els.append(el)
        if tag in _VOID or m.group(3).rstrip().endswith("/"):
            continue
        if tag in _RAW:
            cm = re.compile(r"</%s\s*>" % re.escape(tag), re.I).search(text, m.end())
            el.cstart, el.end = (cm.start(), cm.end()) if cm else (n, n)
            i = el.end
            continue
        stack.append(len(els) - 1)
    for j in stack:
        els[j].cstart = els[j].end = n
    kids: dict[int, list] = {}
    for idx, el in enumerate(els):
        kids.setdefault(el.parent, []).append(idx)
    return els, kids


def _open_tag(text, el) -> str:
    return text[el.start:el.oend]


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


# ------------------------------------------------------------- що є картою
MAP_URL_RX = re.compile(
    r"//(?:www\.)?google\.[a-z]{2,3}(?:\.[a-z]{2})?/maps\b"
    r"|//maps\.google\.[a-z]{2,3}(?:\.[a-z]{2})?\b"
    r"|//maps\.googleapis\.com/maps/(?:embed|api/staticmap)"
    r"|//(?:www\.)?openstreetmap\.org/export/embed"
    r"|//yandex\.[a-z]{2,3}/map-widget"
    r"|//(?:www\.)?bing\.com/maps/embed"
    r"|//api\.mapbox\.com/styles/"
    r"|//static\.parastorage\.com/[^\s\"']*googleMap", re.I)
MAP_LINK_RX = re.compile(MAP_URL_RX.pattern + r"|//maps\.app\.goo\.gl/|//goo\.gl/maps/",
                         re.I)
_STATIC_MAP_RX = re.compile(r"maps/api/staticmap|staticmap\.openstreetmap", re.I)
# iframe-карта, яку заповнює JS конструктора сайту (src порожній)
_MAPISH_ATTR_RX = re.compile(
    r"""\b(?:class|id|data-qa|title|aria-label)\s*=\s*["'][^"']*"""
    r"""(?:\bmaps?\b|[-_]map\b|\bmap[-_]|gmap|google-?map|\bmapa\b|\bmappa\b|\bkarte\b)""",
    re.I)
_EMPTY_SRC_RX = re.compile(r"""(?<![\w-])src\s*=\s*["']\s*(?:about:blank)?\s*["']""", re.I)
_ANY_SRC_RX = re.compile(r"""(?<![\w-])src\s*=""", re.I)

_CTOR_RX = re.compile(r"\bL\.map\s*\(|\bnew\s+google\.maps\.Map\s*\(|\bnew\s+mapboxgl\.Map\s*\(")
_LOOKUP_RX = re.compile(
    r"""(?:getElementById|getElementsByClassName|getElementsByTagName|getElementsByName)"""
    r"""\s*\(\s*["']([^"']*)["']"""
    r"""|querySelector(?:All)?\s*\(\s*["']([^"']*)["']"""
    r"""|(?:\$|jQuery)\s*\(\s*["']([^"']*)["']""")
_EVENT_RX = re.compile(r"""\baddEventListener\s*\(\s*["'](\w+)["']""")
_DOC_LOOKUP = (r"""document\s*\.\s*(?:getElementById\s*\(\s*["']([\w-]+)["']\s*\)"""
               r"""|querySelector\s*\(\s*["']#([\w-]+)["']\s*\))""")
_MAP_USE_RX = re.compile(r"\bgoogle\.maps\b|\bL\.(?:map|tileLayer|marker)\s*\(|\bmapboxgl\.")
# віджети тем, що самі вантажать карту через підключену бібліотеку
_WIDGET_HINT_RX = re.compile(r"fusion-google-map|et_pb_map|wpgmza|wpgmp|leaflet-container",
                             re.I)
_MAP_ASSET_RX = re.compile(
    r"""<script\b[^>]*\bsrc\s*=\s*["'][^"']*(?:/maps/api/js|leaflet(?:-src)?(?:\.min)?\.js"""
    r"""|mapbox-gl(?:\.min)?\.js)[^"']*["'][^>]*>\s*</script\s*>"""
    r"""|<link\b[^>]*\bhref\s*=\s*["'][^"']*(?:leaflet(?:\.min)?\.css|mapbox-gl(?:\.min)?\.css)"""
    r"""[^"']*["'][^>]*>""", re.I)
_IFRAME_MAP_RX = re.compile(r"<iframe\b[^>]*map", re.I)
# дешеві підрядки перед регекспами: гігантські вітки (hywoxgar — 990 сторінок,
# 1 ГБ html) інакше сканувались би хвилинами. Підрядки — з адрес, а не слово
# «maps»: те сидить у CSS-класах теми (Avada `fusion-maps-js-type` на 816
# сторінках hywoxgar). Регекспи — окремо: одна спільна альтернація з re.I
# втрачає швидкий пошук за літералом і була в 50 разів повільнішою.
_HINTS = ("/maps", "maps.google", "openstreetmap", "googleMap", "map-widget",
          "api.mapbox", "L.map(", ".Map(", "<iframe", "<IFRAME")


def _maybe_map(text: str) -> bool:
    return any(h in text for h in _HINTS) and bool(
        MAP_URL_RX.search(text) or _CTOR_RX.search(text) or _IFRAME_MAP_RX.search(text))


_SPA_ROOT_RX = re.compile(r"""<div\b[^>]*(?<![\w-])id\s*=\s*["'](?:root|app|__next|__nuxt)["']""",
                          re.I)
# будь-який локальний <script src>: Vite кладе бандл як type="module", а
# CRA (`static/js/main.*.js`) — звичайним defer-скриптом
_SCRIPT_SRC_RX = re.compile(r"""<script\b[^>]*(?<![\w-])src\s*=\s*["']([^"'?#]+)""", re.I)

# ------------------------------------------------------------- підписи карти
_CAPTION_RX = re.compile(
    r"\b(?:maps?|mapa|mapas|mappa|mappe|karte|carte|kaart|kart[ae]"
    r"|locali[zs]a[cç][aã]o|localiza[cç]i[oó]n|localisation|localizzazione|location|"
    r"ubicaci[oó]n|posizione|lokacija|lokalizacja|standort(?:e)?|lage|anfahrt|"
    r"wegbeschreibung|access|acesso|accesso|acc[eè]s|directions|dojazd|"
    r"onde estamos|onde nos encontrar|como chegar|venha nos visitar|"
    r"dove siamo|dove (?:ci )?trov\w*|dove ci troviamo|come raggiungerci|come arrivare|"
    r"vieni a trovarci|c[oó]mo llegar|d[oó]nde estamos|nous trouver|o[uù] nous trouver|"
    r"plan d['’]acc[eè]s|venez nous voir|so finden sie uns|hier finden sie uns|"
    r"find us|where (?:we are|to find us)|how to (?:find|reach|get to) us|visit us|"
    r"kako do nas|gdje smo)\b|アクセス|地図|所在地", re.I)
# адреса/контакт у тексті: такий «підпис» — уже зміст, його не вирізаємо
_ADDR_RX = re.compile(
    r"@|\d{3,}|\b(?:rua|r\.|av\.?|avenida|alameda|travessa|rodovia|estrada|pra[cç]a|"
    r"via|viale|piazza|piazzale|corso|largo|vicolo|strasse|straße|str\.|gasse|weg|"
    r"platz|allee|rue|avenue|boulevard|chemin|place|quai|calle|carrer|avda|plaza|"
    r"paseo|street|st\.|road|rd\.|lane|ulica|cesta|trg)(?!\w)[^<>\n]{0,40}?\d", re.I)
_DECOR_RX = re.compile(r"^[\s\W\d_]{0,6}$")            # «07», «·», «→», «—»
_CONTENT_TAGS = frozenset("img picture video audio canvas form input select textarea "
                          "button object embed iframe".split())
_HEADINGS = frozenset("h1 h2 h3 h4 h5 h6".split())
_COMMENT_RX = re.compile(r"<!--.*?-->", re.S)
_TAGS_RX = re.compile(r"<[^>]+>")
_MAP_COMMENT_RX = re.compile(
    r"map|mapa|mappa|karte|standort|locali[zs]|location|ubicaci|access|onde|dove", re.I)
# текст лінка «про карту»
_MAP_WORD_RX = re.compile(
    r"\b(?:maps?|mapa|mapas|mappa|mappe|karte|carte|kaart|kart[ae]|lageplan|"
    r"plan d['’]acc[eè]s)\b|地図", re.I)
_GRID_COLS_RX = re.compile(r"\s*\b(?:sm|md|lg|xl|2xl):grid-cols-\d+\b")


def _plain(seg: str) -> str:
    seg = _COMMENT_RX.sub(" ", seg)
    return " ".join(_html.unescape(_TAGS_RX.sub(" ", seg)).split())


def _text_ok(seg: str, mode: str) -> bool:
    """Текст між елементами: «caption» пускає підписи карти, «empty» — лише
    порожнечу й декоративні знаки."""
    if "<?" in _COMMENT_RX.sub("", seg):
        return False                                   # php — не наш вміст
    t = _plain(seg)
    if not t or _DECOR_RX.match(t):
        return True
    return (mode == "caption" and len(t) <= 60 and bool(_CAPTION_RX.search(t))
            and not _ADDR_RX.search(t))


class _Page:
    """Сторінка з розбором — один на сторінку на прогін."""

    def __init__(self, path: str, text: str):
        self.path, self.text = path, text
        self.els, self.kids = _parse(text)
        self.ids = {}
        for idx, el in enumerate(self.els):
            m = _ID_RX.search(_open_tag(text, el))
            if m:
                self.ids.setdefault(m.group(1), idx)

    # ----- що вважати вмістом
    def is_map(self, idx: int) -> bool:
        el = self.els[idx]
        tag = _open_tag(self.text, el)
        if el.tag in ("iframe", "embed", "object"):
            if MAP_URL_RX.search(tag):
                return True
            return (el.tag == "iframe" and bool(_MAPISH_ATTR_RX.search(tag))
                    and (not _ANY_SRC_RX.search(tag) or bool(_EMPTY_SRC_RX.search(tag))))
        return el.tag == "img" and bool(_STATIC_MAP_RX.search(tag))

    def sub_ok(self, idx: int, mode: str, map_scripts: set) -> bool:
        el = self.els[idx]
        if el.tag in ("style", "noscript", "template", "br", "wbr", "svg"):
            return True
        if el.tag == "script":
            return idx in map_scripts
        if el.tag in _CONTENT_TAGS:
            return mode == "caption" and self.is_map(idx)
        if el.tag == "a":
            href = _HREF_RX.search(_open_tag(self.text, el))
            if href and href.group(2).strip():
                return mode == "caption" and bool(MAP_LINK_RX.search(href.group(2)))
        if el.tag in _HEADINGS:
            if mode != "caption":
                return False
            t = _plain(self.text[el.oend:el.cstart])
            return len(t) <= 120 and not _ADDR_RX.search(t)
        return self.rest_ok(idx, None, mode, map_scripts)

    def rest_ok(self, p: int, skip, mode: str, map_scripts: set) -> bool:
        """Чи в елементі p (без дитини skip) немає нічого вартісного."""
        el, pos = self.els[p], self.els[p].oend
        for c in self.kids.get(p, ()):
            ch = self.els[c]
            if not _text_ok(self.text[pos:ch.start], mode):
                return False
            if c != skip and not self.sub_ok(c, mode, map_scripts):
                return False
            pos = ch.end
        return _text_ok(self.text[pos:el.cstart], mode)

    def climb(self, idx: int, mode: str, map_scripts: set) -> int:
        while True:
            p = self.els[idx].parent
            if p < 0 or self.els[p].tag in _NEVER:
                return idx
            if not self.rest_ok(p, idx, mode, map_scripts):
                return idx
            idx = p

    def scripts(self):
        for idx, el in enumerate(self.els):
            if el.tag == "script" and not _ANY_SRC_RX.search(_open_tag(self.text, el)):
                yield idx, self.text[el.oend:el.cstart]


# ------------------------------------------------------------- JS-карти
def _ctor_ids(js: str) -> set:
    """Id контейнерів, які отримує конструктор карти (рядком, через document.*
    або змінною, якій той контейнер присвоєно)."""
    ids = set()
    for m in _CTOR_RX.finditer(js):
        arg = js[m.end():m.end() + 300]
        s = re.match(r"""\s*["']([\w-]+)["']""", arg)
        d = re.match(r"\s*" + _DOC_LOOKUP, arg)
        c = re.match(r"""\s*\{[^}]*?\bcontainer\s*:\s*["']([\w-]+)["']""", arg, re.S)
        v = re.match(r"\s*([A-Za-z_$][\w$]*)\s*[,)]", arg)
        if s:
            ids.add(s.group(1))
        elif d:
            ids.add(d.group(1) or d.group(2))
        elif c:
            ids.add(c.group(1))
        elif v:
            a = re.search(r"\b%s\s*=\s*%s" % (re.escape(v.group(1)), _DOC_LOOKUP), js)
            if a:
                ids.add(a.group(1) or a.group(2))
    return ids


def _map_only(js: str, ids: set) -> bool:
    """Скрипт робить лише карту: усі його DOM-звернення — до її контейнерів,
    подій, окрім завантаження сторінки, він не слухає."""
    allowed = ids | {"#" + i for i in ids}
    for m in _LOOKUP_RX.finditer(js):
        if (m.group(1) or m.group(2) or m.group(3) or "").strip() not in allowed:
            return False
    return all(e in ("load", "DOMContentLoaded") for e in _EVENT_RX.findall(js)) \
        and "document.write" not in js


# ------------------------------------------------------------- шляхи
def _resolve(page: str, path: str, pageset: set) -> str | None:
    """Сторінка вітки, на яку веде шлях лінка (без якоря); None — не наша."""
    path = _html.unescape(path).split("?", 1)[0].strip()
    m = re.match(r"(?i)^(?:https?:)?//(?:www\.)?\{\{DOMAIN\}\}(/.*)?$", path)
    if m:
        path = m.group(1) or "/"
    elif re.match(r"(?i)^(?:[a-z][\w+.-]*:|//)", path):
        return None
    if not path:
        return page
    base = "" if path.startswith("/") else posixpath.dirname(page)
    rel = posixpath.normpath(posixpath.join(base, path.lstrip("/")))
    rel = "" if rel in (".", "/") else rel.lstrip("/")
    if rel in pageset:
        return rel
    d = rel
    if posixpath.basename(rel).lower() in ("index.html", "index.htm", "index.php"):
        d = posixpath.dirname(rel)
    elif posixpath.splitext(rel)[1]:
        return None
    for name in ("index.php", "index.html", "index.htm"):
        cand = posixpath.join(d, name) if d else name
        if cand in pageset:
            return cand
    return None


# ------------------------------------------------------------- план правок
def _cut(text: str, s: int, e: int) -> tuple[int, int]:
    """Спан вирізання: блок на власних рядках іде з рядками; дві порожні
    лінії, що зійшлися після вирізання, стають однією."""
    ls = text.rfind("\n", 0, s) + 1
    le = text.find("\n", e)
    le = len(text) if le < 0 else le
    if text[ls:s].strip() or text[e:le].strip():
        # у рядку є ще щось: беремо лише пробіли ПЕРЕД блоком, коли за ним
        # одразу тег, що закривається («Zürich <a…>…</a></p>»)
        while s > ls and text[s - 1] in " \t" and text.startswith("</", e):
            s -= 1
        return s, e
    s, e = ls, min(le + 1, len(text))
    prev_blank = ls > 0 and not text[text.rfind("\n", 0, ls - 1) + 1:ls].strip()
    nle = text.find("\n", e)
    if prev_blank and nle >= 0 and not text[e:nle].strip():
        e = nle + 1
    return s, e


def _describe(pg: _Page, idx: int) -> str:
    el = pg.els[idx]
    tag = _open_tag(pg.text, el)
    attrs = []
    m = _ID_RX.search(tag)
    if m:
        attrs.append(f'id="{m.group(1)}"')
    c = _CLASS_RX.search(tag)
    if c and not m:
        attrs.append(f'class="{" ".join(c.group(3).split()[:3])}"')
    head = next((_plain(pg.text[pg.els[k].oend:pg.els[k].cstart])
                 for k in range(idx + 1, len(pg.els))
                 if pg.els[k].start < el.end and pg.els[k].tag in _HEADINGS), "")
    return f"<{el.tag}{' ' + ' '.join(attrs) if attrs else ''}>" + (f" «{head[:50]}»" if head else "")


def _kind(pg: _Page, idx: int) -> str:
    tag = _open_tag(pg.text, pg.els[idx])
    if "parastorage" in tag:
        return "Wix-віджет Google Maps"
    if pg.els[idx].tag == "img":
        return "статична карта-картинка"
    if pg.els[idx].tag in ("iframe", "embed", "object"):
        host = MAP_URL_RX.search(tag)
        return f"{pg.els[idx].tag} {host.group(0).lstrip('/')[:40]}" if host else f"{pg.els[idx].tag}-карта"
    return "JS-карта"


def _spa_bundle(page: str, text: str, files: dict) -> str:
    """Шлях JS-бандла SPA, що сам малює карту; '' — не SPA або карти в ньому нема."""
    if not _SPA_ROOT_RX.search(text):
        return ""
    for m in _SCRIPT_SRC_RX.finditer(text):
        src = m.group(1).strip()
        if re.match(r"(?i)^(?:[a-z][\w+.-]*:|//)", src):
            continue                                   # чужий хост — не бандл вайта
        base = "" if src.startswith("/") else posixpath.dirname(page)
        rel = posixpath.normpath(posixpath.join(base, src.lstrip("/"))).lstrip("/")
        if MAP_URL_RX.search(files.get(rel, "")):
            return rel
    return ""


def _plan_page(page: str, text: str, files: dict) -> dict:
    plan = {"edits": [], "issues": [], "removed": set(), "lost": set(), "spans": []}
    pg = _Page(page, text)
    maps = [i for i in range(len(pg.els)) if pg.is_map(i)]

    js_maps, map_scripts = [], set()
    for sidx, js in pg.scripts():
        if not _CTOR_RX.search(js):
            continue
        ids = _ctor_ids(js)
        conts = [pg.ids[i] for i in ids if i in pg.ids]
        line = _line(text, pg.els[sidx].start)
        if not conts:
            plan["issues"].append({"path": page, "line": line, "severity": "warn",
                                   "message": "JS-карта: не знайшов її контейнер у розмітці — "
                                              "прибирай руками"})
        elif not _map_only(js, ids):
            plan["issues"].append({"path": page, "line": line, "severity": "warn",
                                   "message": "JS-карта: скрипт ініціалізації робить ще щось "
                                              "(меню/інші блоки) — вирізати скрипт означало б "
                                              "зламати решту, прибирай руками"})
        else:
            map_scripts.add(sidx)
            js_maps.extend((c, sidx) for c in conts)
    if not maps and not js_maps:
        return plan

    bundle = _spa_bundle(page, text, files)
    if bundle:
        first = (maps or [c for c, _ in js_maps])[0]
        plan["issues"].append({"path": page, "line": _line(text, pg.els[first].start),
                               "severity": "warn",
                               "message": f"карту малює JS-бандл SPA ({bundle}) — правка "
                                          f"HTML нічого не дасть, прибирай у бандлі руками"})
        return plan

    blocks = []                                        # (idx блоку, idx карти)
    for m in maps:
        blocks.append((pg.climb(m, "caption", map_scripts), m))
    for c, _s in js_maps:
        blocks.append((pg.climb(c, "caption", map_scripts), c))
    blocks.sort(key=lambda b: (pg.els[b[0]].start, -pg.els[b[0]].end))
    kept = []
    for b, m in blocks:
        if kept and pg.els[b].start < pg.els[kept[-1][0]].end:
            continue                                   # уже всередині вирізаного
        kept.append((b, m))

    spans = []
    for b, m in kept:
        el = pg.els[b]
        s, e = el.start, el.end
        head = text[:s].rstrip()
        if head.endswith("-->"):
            cs = head.rfind("<!--")
            if cs >= 0 and _MAP_COMMENT_RX.search(head[cs:]):
                s = cs
        spans.append((s, e))
        seg = text[el.start:el.end]
        plan["removed"].update(_ID_RX.findall(seg))
        p = el.parent
        while p >= 0:
            mm = _ID_RX.search(_open_tag(text, pg.els[p]))
            if mm:
                plan["lost"].add(mm.group(1))
            p = pg.els[p].parent
        plan["issues"].append({"path": page, "line": _line(text, pg.els[m].start),
                               "severity": "info",
                               "message": f"мапа ({_kind(pg, m)}) — автофікс прибере "
                                          f"{_describe(pg, b)}"})
    for sidx in map_scripts:
        el = pg.els[sidx]
        if not any(s <= el.start < e for s, e in spans):
            spans.append((el.start, el.end))

    # ґрид на дві колонки, де лишилась одна, — одноколонковий
    removed = {b for b, _ in kept}
    for p in {pg.els[b].parent for b in removed if pg.els[b].parent >= 0}:
        left = [k for k in pg.kids.get(p, ()) if k not in removed
                and pg.els[k].tag not in ("script", "style", "noscript", "template")]
        tag = _open_tag(text, pg.els[p])
        cm = _CLASS_RX.search(tag)
        if len(left) == 1 and cm and re.search(r"\bgrid\b", cm.group(3)) \
                and _GRID_COLS_RX.search(cm.group(3)):
            cls = _GRID_COLS_RX.sub("", cm.group(3)).strip()
            st = pg.els[p].start
            plan["edits"].append((st + cm.start(3), st + cm.end(3), cls))

    # підключення API/Leaflet/Mapbox ішли лише за JS-картою: прибираємо, коли
    # вирізали саму JS-карту і на сторінці не лишилось ні JS-використання
    # бібліотеки, ні віджета теми, що міг би на неї триматись. Лінки «Como
    # chegar» на maps.google.com бібліотеки не потребують і рішення не міняють
    js_removed = bool(js_maps) and all(
        any(s <= pg.els[c].start < e for s, e in spans) for c, _ in js_maps)
    if js_removed:
        rest = text
        for s, e in sorted(spans, reverse=True):
            rest = rest[:s] + rest[e:]
        rest = _MAP_ASSET_RX.sub("", rest)
        if not (_MAP_USE_RX.search(rest) or _CTOR_RX.search(rest)
                or _WIDGET_HINT_RX.search(rest)):
            spans.extend(m.span() for m in _MAP_ASSET_RX.finditer(text))

    for s, e in spans:
        s, e = _cut(text, s, e)
        plan["edits"].append((s, e, ""))
        plan["spans"].append((s, e))
    return plan


def _plan_links(page: str, text: str, plans: dict, pageset: set,
                frag_rx: re.Pattern) -> tuple[list, list]:
    edits, issues = [], []
    if not frag_rx.search(text):
        return edits, issues                           # дешево: 99% сторінок
    own = plans.get(page, {}).get("spans", [])
    pg = _Page(page, text)
    for idx, el in enumerate(pg.els):
        if el.tag != "a" or any(s <= el.start < e for s, e in own):
            continue                                   # не лінк / іде разом з блоком
        hm = _HREF_RX.search(_open_tag(text, el))
        if not hm or "#" not in hm.group(2):
            continue
        path, frag = hm.group(2).split("#", 1)
        target = _resolve(page, path, pageset)
        plan = plans.get(target)
        if not plan or not frag:
            continue
        label = _plain(text[el.oend:el.cstart]) or frag
        about_map = bool(_MAP_WORD_RX.search(label))
        if frag in plan["removed"]:
            p = el.parent
            if about_map:
                b, what = pg.climb(idx, "empty", set()), "прибере лінк"
                s, e = _cut(text, pg.els[b].start, pg.els[b].end)
                edits.append((s, e, ""))
            elif p >= 0 and pg.els[p].tag == "li" and pg.rest_ok(p, idx, "empty", set()):
                s, e = _cut(text, pg.els[p].start, pg.els[p].end)
                edits.append((s, e, ""))
                what = "зніме пункт меню"
            elif path.strip():
                st = el.start + hm.start(2)
                edits.append((st, st + len(hm.group(2)), path))
                what = "поведе на сторінку без якоря"
            else:
                edits.append((el.start, el.oend, ""))
                edits.append((el.cstart, el.end, ""))
                what = "лишить текст без лінка"
        elif frag in plan["lost"] and about_map:
            b = pg.climb(idx, "empty", set())
            s, e = _cut(text, pg.els[b].start, pg.els[b].end)
            edits.append((s, e, ""))
            what = "прибере лінк (карти в секції вже нема)"
        else:
            continue
        issues.append({"path": page, "line": _line(text, el.start), "severity": "info",
                       "message": f"лінк «{label[:40]}» веде на блок з мапою "
                                  f"({target}#{frag}) — автофікс {what}"})
    return edits, issues


def _plan(files: dict) -> tuple[dict, dict, list]:
    pages = {p: t for p, t in files.items() if p.lower().endswith(PAGE_EXT)}
    plans = {p: _plan_page(p, t, files) for p, t in sorted(pages.items()) if _maybe_map(t)}
    plans = {p: pl for p, pl in plans.items() if pl["edits"] or pl["issues"]}
    edits = {p: list(pl["edits"]) for p, pl in plans.items()}
    issues = [i for pl in plans.values() for i in pl["issues"]]
    live = {p: pl for p, pl in plans.items() if pl["spans"]}
    if live:
        pageset = set(pages)
        frags = set().union(*(pl["removed"] | pl["lost"] for pl in live.values()))
        frag_rx = re.compile(r"""href\s*=\s*["'][^"'#]*#(?:%s)["']"""
                             % "|".join(map(re.escape, sorted(frags))), re.I) if frags \
            else re.compile(r"(?!)")
        for page in sorted(pages):
            le, li = _plan_links(page, pages[page], live, pageset, frag_rx)
            if le:
                edits.setdefault(page, []).extend(le)
                issues.extend(li)
    return pages, edits, issues


def _apply(text: str, edits: list) -> str:
    out, last = [], len(text)
    for s, e, repl in sorted(set(edits), key=lambda x: (x[0], x[1]), reverse=True):
        if e > last:
            continue                                   # вкладене в більше вирізання
        out.append(text[e:last])
        out.append(repl)
        last = s
    out.append(text[:last])
    return "".join(reversed(out))


# ------------------------------------------------------------- точки входу
def run_branch(files, all_paths, branch: str = ""):
    _pages, _edits, issues = _plan(files)
    return sorted(issues, key=lambda i: (i["path"], i["line"]))


def fix_branch(files, all_paths, branch: str = ""):
    pages, edits, _issues = _plan(files)
    actions = []
    for page in sorted(edits):
        if not edits[page]:
            continue
        new = _apply(pages[page], edits[page])
        if new != pages[page]:
            actions.append({"type": "edit", "path": page, "content": new})
    return actions
