"""Назва сайту vue-вайта: лого і всі згадки мають нести назву з вітки.

Що в корпусі. У кожній vue-вітці шапка має `<img>` у home-лінку — і всі 221
такі «лого» це 50×50 PNG з одного пулу випадкових стікерів: динозаври,
дельфіни, VR-окуляри, фен, чужі логотипи Threads і DuckDuckGo. Унікальних
файлів лише 107 на 221 вітку, тобто один і той самий малюнок стоїть
«логотипом» кількох непов'язаних брендів (перевірено по sha1). Тобто лого
у вайта фактично немає — на його місці стокова піктограма.

ЕТАЛОН НАЗВИ — назва вітки (site_name.expected): колонка «Вайт» у ClickUp
однозначно відповідає колонці «Название» (nwf-chovfuce-eszbufefaa-br-pt →
«Chovfuce Eszbufefaa»). Домен еталоном більше НЕ є: домени міняються
(«Доменные зоны были изменены»), а назва вайта стабільна. Джерело сховане
за site_name.expected — коли назву почне давати поле таски ClickUp,
зміниться рівно те одне місце.

Що робимо:
  * растрове лого (`.png`/`.jpg`/`.webp`/…) у home-лінку шапки — error:
    бренд-марка у цих вайтах може бути тільки векторною;
  * `src`, який не резолвиться у знімку — error (лого веде в нікуди);
  * home-лінк без жодного вмісту — error (лого немає взагалі);
  * **знак без назви** — error: сама іконка ще не лого, поруч має стояти
    напис;
  * **чужа назва у написі** — error: порівняння з назвою вітки через
    варіанти написання (_variants: діакритика знята/з'їдена, умляути
    розкладені, «&»→«and»/пропало). «Chovfuce Eszbuféfaa» ↔
    chovfuce-eszbufefaa — збіг, правопис сайту з акцентом лишається;
    «Inonecaestrn» — чужа назва;
  * `<svg>` інлайном, `.svg` у `src` або текстовий напис — це лого, мовчимо.

Автофікс: знак + напис + перейменування по всьому сайту.
  * знак — літерна марка генератором фавіконок (`checks/favicon.build_svg`):
    літера з НАЗВИ сайту, тло — `theme-color` вайта, літера контрастна;
  * файл лягає у `src/assets/images/logo.svg` тим самим абсолютним шляхом,
    що й кліпарт до нього — vite інлайнить її у data-URI, нічого не
    ламається;
  * напис із чужою назвою переписується на назву вітки — міняється лише
    ПЕРШИЙ текстовий вузол слоту; UPPERCASE лишається uppercase; alt
    картинки отримує ту саму назву;
  * ЧУЖА НАЗВА ПО ВСЬОМУ САЙТУ (title, meta, футер, тексти) перейменовується
    через site_name.rename: повна фраза і перше слово, лише капіталізовані
    входження — слаги, пошти і соцлінки (facebook.com/chovfuceeszbufefaa)
    не чіпаються;
  * напис — `<span>` з назвою; колір за тлом контейнера лого: темна шапка
    (`bg-*-600`+ / `bg-black`) → `text-zinc-100`, світла → `text-zinc-900`.
    Якщо напис у слоті вже є — не дублюємо;
  * `<a>` отримує `inline-flex items-center gap-2`, тільки коли додається
    напис і флексу там ще не було; класи розміру `<img>` не чіпаються.

Лого-слотів у вітці буває КІЛЬКА: у 10 вітках десктопне меню — це сайдбар
`<aside class="hidden lg:flex">`, а `<header class="lg:hidden">` — мобільна
смуга; у nwf-cher* другий home-лінк сидить у мобільній шухляді всередині
самого `<header>`. Тому хромом вважаються і `<header>`, і `<aside>` з
навігацією, а слотом — КОЖЕН home-лінк у них.

Судимо ТІЛЬКИ застосунок, який реально збирається (`src/`): у 19 вітках
поруч лежить мертве дерево чужого шаблону (`pages/` + `components/`), і
його шапка нікуди не потрапляє.
"""
import posixpath
import re


import checks.favicon as favicon

NAME = "Назва сайту: лого і згадки з title"
GROUP = "auto"     # корпус 220 віток: 180 зі спрацюванням (219 знахідок:
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"brand"}
                   # 189 кліпарт + 30 «немає назви»), 40 чистих — усі з
                   # текстовим лого; фікси й svg перевірені там само.
                   #
                   # Еталон «назва вітки» звалідовано на ЖИВІЙ вибірці 25
                   # nwf-віток з GitLab (25.09, локальний кеш nwf виявився
                   # порожніми заглушками — той замір був вакуумним):
                   # 22 чисті, 3 з чужою назвою — всі три справжні обрізані
                   # доменні бренди (Abacadoracon, Academiaoliv,
                   # Abaiteestrat), фолсів 0; блоків хрому з 2+ лого-слотами
                   # — 11 з 25, тож слот-на-кожен-лінк там не розкіш
PROJECTS = ["node"]
DESCRIPTION = ("У home-лінку шапки замість лого стокова піктограма, битий "
               "src, порожньо, іконка без назви — або назва не збігається з "
               "назвою вітки (колонка «Название» у ClickUp). Автофікс "
               "ставить знак (svg-марка з літерою назви, колір з "
               "theme-color), напис поруч і перейменовує чужу назву ПО "
               "ВСЬОМУ САЙТУ (title, meta, футер, тексти); слаги, пошти й "
               "соцлінки не чіпаються.")
FILES = ["*.vue", "*.html", "*.htm", "*.ts", "*.js", "*.json"]

LOGO_PATH = "src/assets/images/logo.svg"

# Хром сайту: <header> або <aside> з навігацією. У 10 вітках десктопне меню —
# це сайдбар <aside class="hidden lg:flex">, а <header class="lg:hidden"> —
# мобільна смуга; лого там ДВА, і виправляти треба обидва.
CHROME_RX = re.compile(r"<(header|aside)\b.*?</\1\s*>", re.S | re.I)
# home-лінк лого: <a href="/">, href="./", :to="'/'", <RouterLink to="/">
_LINK_TAG = r"a|RouterLink|router-link|NuxtLink|nuxt-link"
HOME_LINK_RX = re.compile(
    rf"""<({_LINK_TAG})\b
         (?:[^>"']|"[^"]*"|'[^']*')*?
         (?<![\w-])(?::|v-bind:)?(?:href|to)\s*=\s*
         (?:["']\.?/["']|["']\s*['"]\.?/['"]\s*["']|\{{\s*['"]\.?/['"]\s*\}})
         (?:[^>"']|"[^"]*"|'[^']*')*>
         (?P<body>.*?)</\1\s*>""",
    re.S | re.I | re.X)
IMG_RX = re.compile(r"<img\b[^>]*/?>", re.I)
ATTR_RX = r"""\b{}\s*=\s*(?:"([^"]*)"|'([^']*)')"""
TAG_RX = re.compile(r"<[^>]+>")
# Обчислений напис — {{ t('nav.brand') }} у Vue, {site.name} у JSX: тексту,
# який побачить користувач, у файлі немає, тож і судити його ні за чим.
INTERP_RX = re.compile(r"\{\{.*?\}\}|\{[^{}]*[A-Za-z_][\w.]*\s*\}", re.S)
# растр = не бренд-марка (у цих вайтах лого може бути лише векторним)
RASTER_RX = re.compile(r"\.(?:png|jpe?g|webp|avif|gif|bmp|ico)(?:[?#]|$)", re.I)
VECTOR_RX = re.compile(r"\.svg(?:[?#]|$)|^data:image/svg", re.I)


def _expected(branch: str, files: dict | None = None) -> str:
    """Очікувана назва сайту. Окремо — щоб підміняти в тестах.
    Джерело — site_name.expected: голова <title>, фолбек — назва вітки."""
    try:
        import site_name
        return site_name.expected(branch, files)
    except Exception:
        return ""


def _attr(tag: str, name: str) -> str | None:
    m = re.search(ATTR_RX.format(name), tag, re.I)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


def _word0(name: str) -> str:
    """Перше слово назви — для бейджів і коротких форм."""
    return (name.split() or [""])[0]


# --- назва в лого ↔ назва вітки ---------------------------------------------
# Раніше еталоном був ДОМЕН, і через його шум (обрізання до 8 символів,
# з'їдена діакритика, випадкові вставки, замінена голова) тут жила ціла
# метрика близькості. Тепер еталон — НАЗВА ВІТКИ (site_name.expected):
# обидві сторони чисті, тож порівняння — рівність через _flat-варіанти
# написання (умляути, діакритика, «&»→«and»). «Chovfuce Eszbuféfaa» ↔
# nwf-chovfuce-eszbufefaa-br-pt — збіг (правопис сайту з акцентом НЕ
# чіпається); «Inonecaestrn» у лого — чужа назва, фікс перейменує її по
# всьому сайту.

def _is_wrong(name: str, expected: str) -> bool:
    """Назва на сайті ≠ назві вітки. Рівність — site_name.same: варіанти
    написання (діакритика, умляути, «&») означають ту саму назву, правопис
    сайту виграє."""
    if not (name or "").strip() or not expected:
        return False
    import site_name
    return not site_name.same(name, expected)


def _chrome(files: dict) -> tuple[str, str, list] | None:
    """(шлях, текст, усі блоки хрому з лого-слотом) — компонент шапки.
    Дерево `src/` (той застосунок, що збирається) має пріоритет."""
    def rank(path: str) -> tuple:
        return (0 if path.startswith("src/") else 1, path)

    for path in sorted(files, key=rank):
        if not path.endswith(".vue"):
            continue
        text = files[path]
        blocks = []
        for m in CHROME_RX.finditer(text):
            low = m.group(0).lower()
            if "<nav" not in low and "menu" not in low:
                continue            # <header> статті/сторінки, а не хром сайту
            if HOME_LINK_RX.search(m.group(0)):
                blocks.append(m)
        if blocks:
            return path, text, blocks
    return None


def _resolves(src: str, all_paths) -> bool:
    rel = src.split("?")[0].split("#")[0].lstrip("/")
    while rel.startswith("./"):
        rel = rel[2:]
    known = set(all_paths)
    return rel in known or posixpath.join("public", rel) in known


def _mark_verdict(img: str | None, body: str, all_paths) -> str | None:
    """Що не так зі ЗНАКОМ (сама картинка), None — знак у нормі."""
    if img is None:
        if "<svg" in body.lower():
            return None                          # інлайновий знак
        return None if TAG_RX.sub("", body).strip() else "у шапці немає лого"
    src = _attr(img, "src") or ""
    if VECTOR_RX.search(src):
        return None
    if not src:
        return "у лого порожній src"
    if not _resolves(src, all_paths):
        return f"лого веде в нікуди: {src}"
    if RASTER_RX.search(src):
        return (f"замість лого стокова піктограма ({src}) — "
                "растр із спільного пулу, не бренд-марка")
    return None


def _slots(files: dict, all_paths) -> tuple | None:
    """(path, text, [слот]) — по одному лого-слоту на КОЖЕН home-лінк кожного
    блока хрому: мобільна шухляда всередині <header> — теж слот (nwf-cher*
    тримали у ній растровий кліпарт, поки судився лише перший лінк).
    Слот: {block, home, img, verdict, name, has_name, interp, start, end}."""
    found = _chrome(files)
    if not found:
        return None
    path, text, blocks = found
    slots = []
    for blk in blocks:
      for home in HOME_LINK_RX.finditer(blk.group(0)):
        body = home.group("body")
        img = next(iter(IMG_RX.findall(body)), None)
        name = " ".join(TAG_RX.sub(" ", body).split())
        slots.append({
            "block": blk, "home": home, "body": body, "img": img,
            "verdict": _mark_verdict(img, body, all_paths),
            "name": name,
            "has_name": bool(name),
            # Обчислений напис ({{ t('nav.brand') }}, {site.name}) судити ні
            # за чим: у файлі немає тексту, який побачить користувач.
            "interp": bool(INTERP_RX.search(body)),
            "start": blk.start() + home.start(),
            "end": blk.start() + home.end(),
        })
    return (path, text, slots) if slots else None


def _wrong_slot(s: dict, expected: str) -> bool:
    """Слот, у якому стоїть ЧУЖА назва. Обчислений напис і слот без
    напису — не наш випадок (для другого вже є окрема помилка)."""
    if not s["has_name"] or s["interp"]:
        return False
    return _is_wrong(s["name"], expected)


def _nonlatin_chars(s: dict) -> str:
    """Не-ASCII ЛІТЕРИ у написі лого: «Paruíno Progé» → «íé».

    Емодзі/символи (🔒, ★) — декор, не букви: їх не судимо і фікс їх не
    чіпає (кейс revl-seok 01.10). Обчислені написи судити ні за чим, а
    чужа назва — не цей кейс: там rename по всьому сайту."""
    if not s["has_name"] or s["interp"]:
        return ""
    import unicodedata
    return "".join(dict.fromkeys(
        ch for ch in s["name"]
        if ord(ch) > 127 and (ch.isalpha() or unicodedata.combining(ch))))


_WORD_RX = re.compile(r"[^\W\d_]+", re.UNICODE)


def _latinize_keep(s: str) -> str:
    """Латинізує слова, лишаючи емодзі/цифри на місці: «🔒 Café» → «🔒 Cafe»."""
    import site_name
    out = _WORD_RX.sub(
        lambda m: (site_name.latin(m.group(0)) or "")
        if any(ord(c) > 127 and c.isalpha() for c in m.group(0))
        else m.group(0), s)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def run_branch(files, all_paths, branch):
    expected = _expected(branch, files)
    if not expected:
        return []
    got = _slots(files, all_paths)
    if not got:
        return []
    path, text, slots = got
    issues = []
    for s in slots:
        line = text.count("\n", 0, s["start"]) + 1
        msgs = []
        if s["verdict"]:
            msgs.append(f"{s['verdict']}; має бути знак назви «{expected}»")
        if not s["has_name"] and s["verdict"] != "у шапці немає лого":
            msgs.append(f"біля знака немає назви сайту — має бути «{expected}» "
                        f"(з title)")
        if _wrong_slot(s, expected):
            msgs.append(f"у лого чужа назва «{s['name']}» — має бути "
                        f"«{expected}» (з title); фікс перейменує її "
                        f"по всьому сайту")
        else:
            bad = _nonlatin_chars(s)
            if bad:
                import site_name
                shown = (_latinize_keep(s["name"])
                         or site_name.latin(s["name"])
                         or site_name.expected(branch))
                msgs.append(f"назва в лого «{s['name']}» не строгою "
                            f"латиницею: «{bad}» — логотип пишеться лише "
                            f"латинськими: «{shown}»")
        issues += [{"path": path, "line": line, "severity": "error", "message": m}
                   for m in msgs]
    return issues


def _svg(files: dict, branch: str) -> str:
    """Знак-марка: той самий генератор, що й favicon (brand_mark) — лого і
    іконка вітки виходять з ОДНОГО знака; форма/палітра — за віткою."""
    bg = favicon._brand_color(files)
    try:
        import brand_mark
        return brand_mark.pick(files, branch, base_color=bg)
    except Exception:
        name = _expected(branch, files)
        letter = (name[:1].upper() if name
                  else favicon._brand_letter(files, branch))
        return favicon.build_svg(letter, bg, favicon._text_color(bg))


def _img_tag(name: str, cls: str) -> str:
    return (f'<img src="/{LOGO_PATH}" alt="{name}" '
            f'class="{cls}" />')


# Колір напису — за тлом контейнера лого: у корпусі шапка або світла
# (bg-white, 17 з 19 віток без назви), або темна (bg-zinc-900). Дивимось
# найближчий bg-* ПЕРЕД home-лінком у самій шапці.
BG_RX = re.compile(r"\bbg-(?:(black)|(white)|([a-z]+)-(\d{2,3}))\b")
DARK_SHADE = 600


def _name_color(header: str, upto: int) -> str:
    hits = list(BG_RX.finditer(header[:upto]))
    if not hits:
        return "text-zinc-900"
    m = hits[-1]
    if m.group(1):
        return "text-zinc-100"
    if m.group(2):
        return "text-zinc-900"
    return "text-zinc-100" if int(m.group(4)) >= DARK_SHADE else "text-zinc-900"


def _name_tag(name: str, color: str) -> str:
    return (f'<span class="font-sans font-semibold text-lg md:text-xl {color}">'
            f'{name}</span>')


def _with_layout(open_tag: str) -> str:
    """Знак і напис поруч: додаємо флекс-класи, нічого не прибираючи."""
    cls = _attr(open_tag, "class")
    if cls is None:
        return open_tag[:-1].rstrip() + ' class="inline-flex items-center gap-2">'
    if "flex" in cls:
        return open_tag
    return re.sub(ATTR_RX.format("class"),
                  lambda m: f'class="{cls} inline-flex items-center gap-2"',
                  open_tag, count=1, flags=re.I)


def _retitle(body: str, brand: str) -> str:
    """Міняє видимий напис лого на brand, не чіпаючи ні теги, ні їхній
    порядок: переписується ПЕРШИЙ непорожній текстовий вузол (у корпусі
    таких у слоті рівно один — заміряно на 1935 вітках, слотів із двома
    текстовими вузлами немає жодного, тобто бейджа-монограми тут не буває).
    Регістр напису зберігається: UPPERCASE лишається uppercase."""
    parts = re.split(r"(<[^>]+>)", body)
    for i, p in enumerate(parts):
        if i % 2 or not p.strip():
            continue
        word = brand.upper() if p.strip().isupper() else brand
        lead = p[:len(p) - len(p.lstrip())]
        trail = p[len(p.rstrip()):]
        parts[i] = lead + word + trail
        break
    return "".join(parts)


def _rewrite_slot(s: dict, name: str) -> str:
    """Новий home-лінк: знак + напис з назви сайту (чого не вистачає)."""
    body, img = s["body"], s["img"]
    whole = s["home"].group(0)
    open_tag = whole[:whole.index(body)] if body else whole
    tail = whole[len(open_tag) + len(body):]
    new_body, new_open = body, open_tag
    if s["verdict"]:
        cls = (_attr(img, "class") if img else None) or "h-8 md:h-10 w-auto"
        new_img = _img_tag(name, cls)
        new_body = (new_body.replace(img, new_img, 1) if img
                    else new_body.rstrip() + f"\n        {new_img}\n      ")
    if not s["has_name"]:
        color = _name_color(s["block"].group(0), s["home"].start())
        new_body = new_body.rstrip() + f"\n        {_name_tag(name, color)}\n      "
        new_open = _with_layout(open_tag)
    elif s.get("wrong") or s.get("nonlatin"):
        new_body = _retitle(new_body, name)
        if img and not s["verdict"]:
            # напис чужий/нелатинський — alt на картинці той самий витік
            new_img = re.sub(ATTR_RX.format("alt"), f'alt="{name}"',
                             img, count=1, flags=re.I)
            new_body = new_body.replace(img, new_img, 1)
    return new_open + new_body + tail


def fix_branch(files, all_paths, branch):
    expected = _expected(branch, files)
    if not expected:
        return []
    got = _slots(files, all_paths)
    if not got:
        return []
    path, text, slots = got
    for s in slots:
        s["wrong"] = _wrong_slot(s, expected)
        s["nonlatin"] = not s["wrong"] and bool(_nonlatin_chars(s))
    todo = [s for s in slots
            if s["verdict"] or not s["has_name"] or s["wrong"]
            or s["nonlatin"]]
    if not todo:
        return []

    # НАПИС лого — строгою латиницею («Câmera Alves» → «Camera Alves»);
    # порівнянню це не заважає: same() знімає діакритику з обох боків.
    # Нелатинська назва цілком → напис з назви вітки (вона ASCII).
    import site_name
    display = site_name.latin(expected) or site_name.expected(branch)
    # правки з кінця тексту — щоб зсуви попередніх слотів не з'їхали
    new_text = text
    for s in sorted(todo, key=lambda s: s["start"], reverse=True):
        # nonlatin-слот: латинізуємо ЙОГО напис, зберігаючи емодзі; решта
        # кейсів пише display (чужа назва/немає напису)
        disp = (_latinize_keep(s["name"])
                if s.get("nonlatin") and not s.get("wrong") else display)
        new_text = (new_text[:s["start"]] + _rewrite_slot(s, disp or display)
                    + new_text[s["end"]:])

    # чужа назва живе не лише в лого: перейменовуємо її по ВСЬОМУ сайту
    # (title, meta, футер, тексти) — капіталізовані входження повної фрази
    # і першого слова; слаги/пошти/соцлінки site_name.rename не чіпає
    edited = {path: new_text}
    old = next((s["name"] for s in todo if s.get("wrong")), "")
    if old:
        import site_name
        rest = dict(files)
        rest[path] = new_text
        for p, t in site_name.rename_files(rest, old, expected).items():
            edited[p] = t

    actions = []
    if any(s["verdict"] for s in todo):
        actions.append({"type": "create", "path": LOGO_PATH,
                        "content": _svg(files, branch)})
    if edited.get(path) == text:
        edited.pop(path, None)
    actions += [{"type": "edit", "path": p, "content": t}
                for p, t in sorted(edited.items())]
    return actions
