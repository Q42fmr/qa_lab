"""Фото замість іконки у лого: `<img>` у home-лінку хедера/футера показує
стокове фото, а не бренд-іконку.

Кейс з практики: `rusveve-ar-es`, `semructi-ar-es` та інші — верстальник
залишив у лого `<img src="https://img.b2bpic.net/premium-photo/…jpg?w=740">`
замість `.svg`/`.png`-іконки. Скан `cache/` (5988 віток, тільки головна
сторінка): у 97 хедер-лого є `<img>`, з них 74 — саме стокове фото
(`img.b2bpic.net/*.jpg`). Решта 23 — легітимні `.svg`/`.png`-лого, їх не
чіпаємо. У `rusveve-ar-es` те саме фото продубльоване і в футер-лого, з
класами `brightness-0 invert` (роблять кольорову картинку білим силуетом —
для фото це просто маскує дефект, а не лагодить).

`checks/logo_domain.py` цей дефект свідомо не бачить: він порівнює лише
ТЕКСТ лого, картинки не чіпає.

Що ловимо: у home-лінку (`href` = `./` | `/` | `index.*`, той самий regexp,
що в `logo_domain`) усередині `<header>`/`<footer>` є `<img>`, чий `src`:
  * має розширення `.jpg`/`.jpeg`/`.webp`/`.avif` (растрові фото-формати —
    легітимні лого у цих вайтах завжди `.svg`/`.png`), або
  * веде на відомий фотосток (`b2bpic`, `pexels`, `unsplash`, `picsum`,
    `freepik`, `shutterstock`, `istockphoto`, `gettyimages`).
`.svg`/`.png`/`.ico`/`.gif`/`data:` не чіпаємо.

Автофікс (fix_branch) веде `src` на ту саму робочу іконку, що й
`checks/favicon.py`: наявний `favicon.*` у корені вітки, інакше генерується
`favicon.svg` (той самий генератор — `favicon.build_svg`, дублювати не
можна). Літера іконки — перша літера ТЕКСТУ лого з того ж `<a>`
(«Rubricakil» → R), фолбек — `favicon._brand_letter` (домен з ClickUp). У
футері додатково знімаються класи `brightness-0`/`invert`: на згенерованій
кольоровій іконці вони дають суцільний білий квадрат без видимої літери.
"""
import html as _html
import re

import checks.favicon as favicon

NAME = "Лого: фото замість іконки"
GROUP = "tests"
PROJECTS = ["php"]
DESCRIPTION = ("У home-лінку хедера/футера <img> веде на стокове фото "
               "(растровий формат або відомий фотосток) замість "
               "бренд-іконки. Лише warn — заміна знака руками: "
               "Медіа → Лого/Favicon (Apply перепише src на знак).")
FILES = ["*.html", "*.htm", "*.php"]

HEADER_RX = re.compile(r"<header\b.*?</header\s*>", re.S | re.I)
FOOTER_RX = re.compile(r"<footer\b.*?</footer\s*>", re.S | re.I)
# home-лінк: href = ./ | / | index.html | ./index.php | ...  (як у logo_domain)
LOGO_A_RX = re.compile(
    r"""<a\b[^>]*\bhref\s*=\s*["'](?:\.?/|\.?/?index\.(?:html?|php))["'][^>]*>.*?</a\s*>""",
    re.S | re.I)
IMG_RX = re.compile(r"<img\b[^>]*>", re.I)
# інлайн-SVG бейдж генератора: <svg> з <text>-монограмою прямо в home-лінку
# (флоу партії 01.10: alnewvad/quuskafs/oriakj — градієнт + літери, а наш
# знак кладеться <img src>, тож цей слот Apply не бачив)
SVG_RX = re.compile(r"<svg\b.*?</svg\s*>", re.S | re.I)

# растрові фото-формати: легітимні лого у цих вайтах завжди .svg/.png
PHOTO_EXT_RX = re.compile(r"\.(?:jpe?g|webp|avif)(?:[?#]|$)", re.I)
# відомі фотостоки — src веде на зовнішнє стокове фото незалежно від розширення
STOCK_HOST_RX = re.compile(
    r"(?:b2bpic|pexels|unsplash|picsum|freepik|shutterstock|istockphoto|gettyimages)",
    re.I)


def _attr(tag: str, name: str) -> str | None:
    """Значення атрибута тегу (лапки будь-якого типу)."""
    m = re.search(rf'\b{name}\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', tag, re.I)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


def _is_photo_src(src: str) -> bool:
    if not src or src.lstrip().lower().startswith("data:"):
        return False
    return bool(PHOTO_EXT_RX.search(src) or STOCK_HOST_RX.search(src))


def _text_of(a_html: str) -> str:
    """Видимий текст лінка: теги геть, ентіті розкодувати, пробіли схлопнути."""
    txt = _html.unescape(re.sub(r"<[^>]+>", " ", a_html))
    return re.sub(r"\s+", " ", txt).strip()


def _is_page(path: str) -> bool:
    return path.lower().endswith((".html", ".htm", ".php"))


def _photo_imgs(a_html: str):
    """[(img_tag, src)] для кожного <img> у лінку з фото-src."""
    out = []
    for m in IMG_RX.finditer(a_html):
        tag = m.group(0)
        src = _attr(tag, "src")
        if src and _is_photo_src(src):
            out.append((tag, src))
    return out


def _badge_svgs(a_html: str):
    """Інлайн-SVG бейджі з літерами у home-лінку: монограма = <text>."""
    return [m.group(0) for m in SVG_RX.finditer(a_html)
            if re.search(r"<text\b", m.group(0), re.I)]


EMPTY_SPAN_RX = re.compile(r"(<span\b[^>]*>)\s*(</span\s*>)", re.I)
TEXT_RX = re.compile(r"<text\b[^>]*>(.*?)</text\s*>", re.S | re.I)


def _esc_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _badge_name(svg: str) -> str:
    """Назва сайту З БЕЙДЖА: генератор 01.10 клав повну назву у <text>
    (span поряд лишав порожнім). Монограми (≤2 символів) — не назва."""
    cands = [re.sub(r"\s+", " ", t).strip() for t in TEXT_RX.findall(svg)]
    cands = [c for c in cands if len(c) > 2]
    return max(cands, key=len) if cands else ""


def _aria_name(a_html: str) -> str:
    """Назва з aria-label home-лінка: 'Vermomao Madpa — página inicial'."""
    m = re.search(r'aria-label\s*=\s*"([^"]+)"', a_html, re.I)
    if not m:
        return ""
    return re.split(r"\s+[—–-]\s+", m.group(1))[0].strip()


def _site_name_for(branch: str, files: dict) -> str:
    try:
        import site_name
        return site_name.expected(branch, files) or ""
    except Exception:
        return ""


def _fill_span(a_html: str, name: str) -> str:
    """Вписує назву в перший порожній <span> лінка; span-а немає — додає
    простий після <img> (класи порожнього span уже тематичні — колір
    підібраний генератором під фон хедера, тож текст «співпадає по фону»).
    Напис — строгою латиницею (вимога QA: «Leituras de Mediação» →
    «Leituras de Mediacao»)."""
    if not name:
        return a_html
    try:
        import site_name
        name = site_name.latin(name) or name
    except Exception:
        pass
    esc = _esc_html(name)
    new, n = EMPTY_SPAN_RX.subn(lambda m: m.group(1) + esc + m.group(2),
                                a_html, count=1)
    if n:
        return new
    m = IMG_RX.search(a_html)
    if m and name not in a_html:
        return a_html[:m.end()] + f"<span>{esc}</span>" + a_html[m.end():]
    return a_html


def _logo_spots(text: str):
    """[(zone, abs_start, abs_end, a_html)] для home-лінків у header/footer.

    zone — "хедер" або "футер", для повідомлень і фікса футера окремо."""
    spots = []
    hm = HEADER_RX.search(text)
    if hm:
        lm = LOGO_A_RX.search(hm.group(0))
        if lm:
            spots.append(("хедер", hm.start() + lm.start(),
                          hm.start() + lm.end(), lm.group(0)))
    for fm in FOOTER_RX.finditer(text):
        for lm in LOGO_A_RX.finditer(fm.group(0)):
            spots.append(("футер", fm.start() + lm.start(),
                          fm.start() + lm.end(), lm.group(0)))
    return spots


def run_branch(files, all_paths, branch: str = ""):
    issues = []
    for path in sorted(files):
        if not _is_page(path):
            continue
        text = files[path]
        for zone, start, _end, a in _logo_spots(text):
            photos = _photo_imgs(a)
            if photos:
                # рядок самого <img>, а не початку лінка: у «Файлах» маркер
                # має стояти на теґу, який доведеться правити
                img_at = start + a.find(photos[0][0])
                src = photos[0][1]
                shown = src if len(src) <= 90 else src[:87] + "…"
                issues.append({"path": path,
                               "line": text.count("\n", 0, img_at) + 1,
                               "severity": "warn",
                               "message": (f"лого {zone}: <img> веде на "
                                           f"стокове фото замість іконки "
                                           f"бренду — '{shown}'")})
                continue
            badges = _badge_svgs(a)
            if badges:
                svg_at = start + a.find(badges[0])
                issues.append({"path": path,
                               "line": text.count("\n", 0, svg_at) + 1,
                               "severity": "warn",
                               "message": (f"лого {zone}: інлайн-SVG бейдж "
                                           f"генератора замість іконки "
                                           f"бренду — Apply замінить на "
                                           f"<img> зі знаком і перенесе "
                                           f"назву в текст")})
                continue
            if IMG_RX.search(a) and EMPTY_SPAN_RX.search(a):
                # слід старого фікса 01.10: бейдж знесли РАЗОМ з назвою, що
                # жила в його <text>; лишився знак і порожній span
                name = (_aria_name(a) or _site_name_for(branch, files)
                        or "назва вітки")
                sp_at = start + a.find(EMPTY_SPAN_RX.search(a).group(0))
                issues.append({"path": path,
                               "line": text.count("\n", 0, sp_at) + 1,
                               "severity": "warn",
                               "message": (f"лого {zone}: поряд зі знаком "
                                           f"порожній span — назва сайту "
                                           f"зникла з тексту; Apply впише "
                                           f"«{name}»")})
    return issues


def _strip_invert_classes(tag: str) -> str:
    """Знімає brightness-0/invert зі значення class — на кольоровій
    згенерованій іконці вони дають суцільний білий квадрат без літери."""
    cls = _attr(tag, "class")
    if cls is None:
        return tag
    classes = [c for c in cls.split() if c not in ("brightness-0", "invert")]
    new_cls = " ".join(classes)
    return re.sub(r'\bclass\s*=\s*(?:"[^"]*"|\'[^\']*\')',
                  f'class="{new_cls}"', tag, count=1, flags=re.I)


def replace_actions(files, all_paths, branch: str = "", version: str = ""):
    """Заміна фото-лого на знак. НЕ автофікс: викликається лише ручним
    Apply з «Медіа → Лого/Favicon» (рішення 01.10 — усі заміни
    лого/favicon ідуть через вкладку, автофікси конфліктували).

    Ціль — наявний favicon.* у корені вітки; немає — favicon.svg
    генерується через brand_mark (favicon.build_svg — фолбек). У <img>
    міняється лише src (решта атрибутів — байт-у-байт); у футері
    додатково знімаються класи brightness-0/invert. Інлайн-SVG бейдж
    генератора (svg+<text> у home-лінку) замінюється на <img> зі знаком —
    розмір переноситься з width/height бейджа, а НАЗВА з його <text>
    (генератор клав її туди, span лишав порожнім) вписується в сусідній
    порожній span: його класи вже дають колір під фон хедера. Порожній
    span поряд з уже заміненим знаком (слід старого фікса) наповнюється
    назвою з aria-label/назви вітки. version — ?v= у src, щоб прев'ю-хост
    не показував старе лого з кешу."""
    root = favicon._root_favicon(all_paths)
    target = root or favicon.FAVICON_PATH

    actions = []
    used_target = False
    letter = None
    for path in sorted(files):
        if not _is_page(path):
            continue
        text = files[path]
        spots = _logo_spots(text)
        if not spots:
            continue
        edits = []
        for zone, start, end, a in spots:
            href = favicon._href_to(path, target)
            if version:
                href += f"?v={version}"
            new_a = a
            photos = _photo_imgs(a)
            for tag, _src in photos:
                new_tag = re.sub(r'\bsrc\s*=\s*(?:"[^"]*"|\'[^\']*\')',
                                 f'src="{href}"', tag, count=1, flags=re.I)
                if zone == "футер":
                    new_tag = _strip_invert_classes(new_tag)
                new_a = new_a.replace(tag, new_tag, 1)
            name = ""
            for svg in _badge_svgs(new_a):
                size = ""
                m = re.search(r'\bwidth\s*=\s*["\'](\d+)["\']', svg)
                h = re.search(r'\bheight\s*=\s*["\'](\d+)["\']', svg)
                if m and h:
                    size = f' width="{m.group(1)}" height="{h.group(1)}"'
                name = name or _badge_name(svg)
                new_a = new_a.replace(
                    svg, f'<img src="{href}" alt=""{size}>', 1)
            if IMG_RX.search(new_a) and EMPTY_SPAN_RX.search(new_a):
                new_a = _fill_span(new_a, name or _aria_name(new_a)
                                   or _site_name_for(branch, files))
            if new_a != a:
                edits.append((start, end, new_a))
                used_target = True
                if letter is None:
                    # перша БУКВЕНО-ЦИФРОВА літера: декоративний глиф на
                    # початку лого (◆, ▸) інакше поїхав би в іконку
                    letter = favicon._first_letter(_text_of(a)) or None
        if not edits:
            continue
        new = text
        for s, e, repl in sorted(edits, key=lambda x: -x[0]):
            new = new[:s] + repl + new[e:]
        if new != text:
            actions.append({"type": "edit", "path": path, "content": new})

    if used_target and not root:
        bg = favicon._brand_color(files)
        try:
            import brand_mark
            svg = brand_mark.pick(files, branch, base_color=bg)
        except Exception:
            if not letter:
                letter = favicon._brand_letter(files, branch)
            svg = favicon.build_svg(letter, bg, favicon._text_color(bg))
        actions.append({"type": "create", "path": favicon.FAVICON_PATH,
                        "content": svg})
    return actions
