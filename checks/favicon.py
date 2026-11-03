"""Favicon: битий data-URI, тип не відповідає вмісту, лінк на неіснуючий файл.

Кейс з практики: <link rel="icon" type="image/x-icon"
href="data:image/x-icon;base64,iVBORw0KGgo...">
— заявлено x-icon, а base64 починається з PNG-сигнатури; сам рядок при цьому
битий (нема чанків IDAT/IEND) — браузер мовчки показує порожню іконку.

Що ловимо:
  * base64 у data:-фавіконці не декодується — битий рядок;
  * декодується, але це не картинка (сміття без сигнатури);
  * PNG без обов'язкових чанків IHDR/IDAT/IEND — недокачаний/згенерований;
  * заявлений MIME (data:image/...;) не відповідає реальному вмісту;
  * лінк на локальний favicon-файл, якого немає у вітці (і розбіжність регістру);
  * href на стоковий фотохост (`picsum.photos/seed/.../32/32` і подібні): це не
    знак бренду, а ВИПАДКОВЕ фото, і хост регулярно лежить - тоді іконки немає
    взагалі. Заміряно на корпусі 9126 вайтів: так зроблено у 4459 (picsum 4456,
    loremflickr 3), тобто це найпоширеніший спосіб залишити вайт без іконки;
    браузер на цих URL віддає `EncodingError: source image cannot be decoded`;
  * (error, одна агрегована помилка на вітку) сторінки, у яких немає жодного
    робочого <link rel="icon"> і немає favicon.ico у корені вітки — лише
    favicon.ico браузер підхопить сам; favicon.svg/.png без <link> лишаються
    невидимими, тож рахуються "немає іконки" навіть якщо файл лежить поряд.

Ручний Apply у «Медіа → Лого/Favicon» (link_actions) зводить лінки:
  * розбіжність регістру → шлях вирівнюється на реальний файл (справжня
    іконка вітки цінніша за згенеровану літеру);
  * мертвий лінк, порожній href, плейсхолдер, битий data-URI, стоковий фотохост
    -> ведемо на робочу іконку: наявний favicon.* у корені, інакше генеруємо
    favicon.svg з першої літери домену вітки;
  * якщо робоча іконка на сторінці вже є — зайвий мертвий лінк прибираємо,
    а не додаємо другу іконку поверх справжньої.
Раніше «неіснуючий файл» вважався рішенням людини, і на 34 вітках кешу чек
лаявся, а автофікс мовчав («виправлень не знайдено») — хоча робочої іконки
там не було взагалі, тобто зберігати мертвий лінк не було сенсу.
"""
import base64
import posixpath
import re
import urllib.parse

NAME = "Favicon: битий або відсутній"
# auto з 21.10 (tsapgituequsja, rezmeufiriafkupul — QA: «нет иконки сайта»):
# фікс = той самий link_actions, що й ручний Apply у «Медіа → Лого/Favicon»
# (зводить лінки до робочої іконки; без іконки у вітці — знак brand_mark у
# favicon.svg). Ручний вибір знака в UI лишається авторитарним (force)
GROUP = "auto"
# branch-code: фікс малює знак бренду (favicon.svg) — захищений «brand»
# вимикає його так само, як logo_domain/logo_latin
MODIFIES = {"brand"}
PROJECTS = ["php"]  # vue-вайтами опікується сусідній favicon_link
DESCRIPTION = ("Чи має сторінка робочу іконку: плейсхолдер у href ({{LOGO}}), порожній href, "
               "лінк на неіснуючий файл, стоковий фотохост у href (picsum тощо), "
               "валідність data:-base64, відповідність MIME вмісту, шаблонний "
               "знак (фон + одна літера). Фікс зводить лінки сторінок до робочої "
               "іконки; без іконки у вітці генерує знак brand_mark у favicon.svg "
               "(інший знак — руками у Медіа → Лого/Favicon).")
FILES = ["*.html", "*.htm", "*.php"]

# `>` може стояти всередині значення атрибута — у вітках трапляється
# inline-SVG прямо в href (data:image/svg+xml,<svg ...>). Тому матчимо
# посимвольно, пропускаючи лапковані ділянки цілком.
LINK_RX = re.compile(r"""<link\b(?:[^>"']|"[^"]*"|'[^']*')*>""", re.I)


def _attr(tag: str, name: str) -> str | None:
    """Значення атрибута з тегу; лапки іншого типу всередині значення дозволені
    (data:image/svg+xml,<svg xmlns='...'> у href="...")."""
    m = re.search(rf"""\b{name}\s*=\s*("([^"]*)"|'([^']*)')""", tag, re.I)
    if not m:
        return None
    return m.group(2) if m.group(2) is not None else m.group(3)
DATA_RX = re.compile(r"data:([^;,]*)(;base64)?,(.*)$", re.S | re.I)
HEAD_RX = re.compile(r"<head\b", re.I)

# реальний вміст → допустимі MIME у data:/type=
MIME_OK = {
    "png":  {"image/png"},
    "ico":  {"image/x-icon", "image/vnd.microsoft.icon", "image/ico"},
    "jpeg": {"image/jpeg", "image/jpg"},
    "gif":  {"image/gif"},
    "webp": {"image/webp"},
    "svg":  {"image/svg+xml"},
}


def _kind(data: bytes) -> str | None:
    """Тип картинки за сигнатурою (magic bytes)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"\x00\x00\x01\x00":
        return "ico"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"GIF8":
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    head = data[:300].lstrip().lower()
    if head.startswith(b"<?xml") or b"<svg" in head:
        return "svg"
    return None


def _check_data_uri(href: str, link_type: str | None) -> str | None:
    """Повертає текст помилки або None, якщо data:-фавіконка валідна."""
    m = DATA_RX.match(href)
    if not m:
        return "нерозбірливий data:-URI"
    mime = (m.group(1) or "").strip().lower()
    payload = m.group(3) or ""

    if m.group(2):                                   # ;base64
        try:
            data = base64.b64decode(re.sub(r"\s+", "", payload), validate=True)
        except Exception:
            return "битий base64 у data:-фавіконці — браузер покаже порожню іконку"
    else:
        data = urllib.parse.unquote(payload).encode("utf-8", "replace")

    if len(data) < 24:
        return "data:-фавіконка порожня або занадто коротка"

    kind = _kind(data)
    if kind is None:
        return ("вміст data:-фавіконки не є картинкою "
                "(немає сигнатури PNG/ICO/JPEG/GIF/WEBP/SVG)")

    if kind == "png" and (b"IHDR" not in data[:40] or b"IDAT" not in data
                          or b"IEND" not in data):
        return ("PNG у data:-фавіконці битий — немає обов'язкових чанків "
                "IHDR/IDAT/IEND (недокачаний або згенерований рядок)")
    if kind == "ico" and len(data) < 22:
        return "ICO у data:-фавіконці битий (обрізаний заголовок)"

    declared = mime or (link_type or "").strip().lower()
    if declared and declared not in MIME_OK[kind]:
        real = sorted(MIME_OK[kind])[0]
        return (f"тип фавіконки не відповідає вмісту: заявлено '{declared}', "
                f"а всередині {kind.upper()} — постав type=\"{real}\"")
    return None


def _resolve(page: str, target: str) -> list[str] | None:
    """Кандидати шляхів у вітці. Відносний шлях пробуємо ДВІЧІ: від теки
    сторінки і від кореня вітки — у багатьох вайтах сторінки лежать у
    підпапці, але рендеряться index.php з кореня, тож './x' означає корінь."""
    t = target.split("?")[0].split("#")[0].strip()
    if not t or t.startswith(("http://", "https://", "//", "data:")):
        return None
    if t.startswith("/"):
        return [t.lstrip("/")]
    rel = posixpath.normpath(posixpath.join(posixpath.dirname(page), t))
    root = posixpath.normpath(t)
    return [rel] if root == rel else [rel, root]


# нерозв'язані шаблонні токени: {{LOGO}}, ${LOGO}, %%LOGO%%, <?= $logo ?>
PLACEHOLDER_RX = re.compile(r"\{\{[^}]*\}\}|\$\{[^}]*\}|%%[^%]*%%|<\?[^>]*\?>")


def _has_placeholder(s: str | None) -> bool:
    return bool(PLACEHOLDER_RX.search(s or ""))


# Стокові/плейсхолдерні фотохости. Фавіконка з такого хоста — завжди дефект:
# віддається ВИПАДКОВЕ фото (жодного стосунку до бренду), а самі хости
# нестабільні — picsum на замірі відповідав 503/522/timeout, тобто іконки не
# було зовсім. Порівнюємо по суфіксу домену, щоб ловити й `i.picsum.photos`,
# й `images.unsplash.com`.
STOCK_ICON_HOSTS = (
    "picsum.photos", "loremflickr.com", "lorempixel.com", "placeimg.com",
    "placekitten.com", "placehold.co", "placeholder.com", "fakeimg.pl",
    "dummyimage.com", "baconmockup.com", "unsplash.com", "unsplash.it",
    "pexels.com", "img.b2bpic.net", "img.magnific.com",
)


def _stock_host(href: str) -> str | None:
    """Хост стокового фото у href — або None, якщо href не туди веде."""
    h = href.strip()
    if not h.lower().startswith(("http://", "https://", "//")):
        return None
    url = h if "://" in h else "https:" + h      # `//host/x` — protocol-relative
    host = urllib.parse.urlsplit(url).netloc.lower().split("@")[-1].split(":")[0]
    return next((s for s in STOCK_ICON_HOSTS
                 if host == s or host.endswith("." + s)), None)


def _link_state(page: str, target: str | None, ltype: str | None,
                fileset: set, lower_map: dict,
                read_bytes=None) -> tuple[str, str | None]:
    """Чи дає цей <link rel=icon> реально показану іконку.

    Повертає (стан, повідомлення):
      "ok"     — іконка буде; повідомлення None
      "broken" — іконки не буде; повідомлення = текст помилки для звіту
      "skip"   — про лінк нічого сказати (немає href)

    read_bytes(path) -> bytes | None — читач вмісту файлу зі знімка вітки.
    Якщо переданий, вміст файлу-іконки перевіряється за сигнатурою.
    """
    if target is None:
        return "skip", None

    t = target.strip()
    if not t:
        return "broken", "порожній href у <link rel=icon> — іконки не буде"

    if _has_placeholder(t):
        return "broken", (f"плейсхолдер у href фавіконки не замінено: '{t}' — "
                          f"браузер піде за цим іменем і отримає 404")

    if t.lower().startswith("data:"):
        err = _check_data_uri(t, ltype)
        return ("broken", err) if err else ("ok", None)

    stock = _stock_host(t)
    if stock:
        return "broken", (f"фавіконка веде на стокове фото ({stock}), а не на файл "
                          f"вітки: '{t}' — хост віддає випадкову картинку і сам "
                          f"часто лежить, тож у табі іконки не буде")

    cands = _resolve(page, t)
    if cands is None:
        return "ok", None                       # інший зовнішній URL — довіряємо

    hit = next((c for c in cands if c in fileset), None)
    if hit:
        if read_bytes is None:
            return "ok", None
        try:
            data = read_bytes(hit)
        except Exception:
            return "ok", None               # прочитати не вийшло — не вигадуємо помилку
        if not data:
            return "broken", f"файл фавіконки '{hit}' порожній"
        if _kind(data) is None:
            return "broken", (f"файл '{hit}' не є картинкою (немає сигнатури "
                              f"PNG/ICO/JPEG/GIF/WEBP/SVG) — іконка не покажеться")
        return "ok", None

    case_hit = next((lower_map[c.lower()] for c in cands
                     if c.lower() in lower_map), None)
    if case_hit:
        return "broken", (f"favicon '{t}' існує як '{case_hit}' — регістр "
                          f"відрізняється, на сервері буде 404")
    return "broken", f"лінк на неіснуючий favicon: '{t}'"


def _deploy_url(branch: str) -> str | None:
    """Базовий URL запущеного локального деплою вітки (або None)."""
    try:
        import deployer
        for d in deployer.list_deploys():
            if d["branch"] == branch:
                return d["url"]
    except Exception:
        pass
    return None


def _probe(url: str):
    """(status, content-type) або (None, None), якщо смикнути не вдалось."""
    try:
        import requests
        r = requests.get(url, timeout=3)
        return r.status_code, r.headers.get("Content-Type", "")
    except Exception:
        return None, None


def _verify_on_deploy(branch: str, hrefs: list[str]) -> str:
    """Уточнення до повідомлення: що віддає локальний деплой на цих URL.
    Викликається ЛИШЕ коли статичний чек уже знайшов помилку."""
    base = _deploy_url(branch)
    if not base:
        return ""
    parts = []
    for href in hrefs[:3]:
        url = base.rstrip("/") + "/" + href.lstrip("/")
        status, ctype = _probe(url)
        if status is None:
            continue
        short = (ctype or "").split(";")[0]
        parts.append(f"{href} → {status}" + (f" {short}" if short else ""))
    return f"; на деплої: {', '.join(parts)}" if parts else ""


# --- генерація іконки -------------------------------------------------------

# Реальний кеш: атрибути <meta> трапляються і в зворотному порядку —
# `<meta content="#fff" name="theme-color">` (9 файлів проти 32412 у
# звичайному порядку) — тому кожен тег ловимо ДВОМА альтернативами:
# name/property спереду і content спереду. Група-переможець визначається
# через _match_group (перша непорожня з альтернативних груп).
OG_SITE_RX = re.compile(
    r"""<meta\b[^>]*\bproperty\s*=\s*["']og:site_name["'][^>]*\bcontent\s*=\s*["']([^"']*)["']"""
    r"""|<meta\b[^>]*\bcontent\s*=\s*["']([^"']*)["'][^>]*\bproperty\s*=\s*["']og:site_name["']""",
    re.I)
APP_NAME_RX = re.compile(
    r"""<meta\b[^>]*\bname\s*=\s*["']application-name["'][^>]*\bcontent\s*=\s*["']([^"']*)["']"""
    r"""|<meta\b[^>]*\bcontent\s*=\s*["']([^"']*)["'][^>]*\bname\s*=\s*["']application-name["']""",
    re.I)
PAGE_TITLE_RX = re.compile(r"<title[^>]*>([^<]*)</title>", re.I)
THEME_COLOR_RX = re.compile(
    r"""<meta\b[^>]*\bname\s*=\s*["']theme-color["'][^>]*\bcontent\s*=\s*["'](#[0-9a-fA-F]{3,8})["']"""
    r"""|<meta\b[^>]*\bcontent\s*=\s*["'](#[0-9a-fA-F]{3,8})["'][^>]*\bname\s*=\s*["']theme-color["']""",
    re.I)
TW_PRIMARY_RX = re.compile(
    r"""primary\s*:\s*\{[^}]*?\b600\s*:\s*["'](#[0-9a-fA-F]{3,8})["']""", re.S)

DEFAULT_COLOR = "#2E3338"
HEX_COLOR_RX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

# Свідомий вибір: беремо частину ДО роздільника (конвенція "Бренд · Сторінка").
# Для зворотної конвенції "Сторінка | Бренд" літера вийде від сторінки, а не
# від бренду — але title стоїть 4-м, останнім джерелом у ланцюжку, після
# домену й og:site_name, тож сюди потрапляємо рідко; надійного способу
# вгадати, який бік роздільника є брендом, немає.
NAME_SPLIT_RX = re.compile(r"[·—|–\-]")


def _match_group(m) -> str | None:
    """Перша непорожня група з регексу-альтернативи (прямий/зворотний
    порядок атрибутів у тегу)."""
    if m is None:
        return None
    for g in m.groups():
        if g is not None:
            return g
    return None


def _domain_for(branch: str) -> str | None:
    """Активний домен вітки з ClickUp (поле Required Domains). Окрема функція,
    щоб її було легко підмінити в тестах."""
    if not branch:
        return None
    try:
        import domains
        return domains.active_for(branch)
    except Exception:
        return None


def _main_page_text(files: dict) -> str:
    """Текст головної сторінки — з неї беремо мета-теги бренду."""
    for name in ("index.php", "index.html", "index.htm"):
        if name in files:
            return files[name]
    return next(iter(files.values()), "")


def _first_letter(s: str) -> str:
    """Перша буквено-цифрова літера рядка, uppercase. Працює і для кирилиці,
    і для тайської — жодних припущень про латиницю."""
    head = NAME_SPLIT_RX.split(s, 1)[0]
    for ch in head:
        if ch.isalnum():
            return ch.upper()
    return ""


def _brand_letter(files: dict, branch: str) -> str:
    """Літера для іконки. НАЗВА САЙТУ (site_name.expected — колонка
    «Название» у ClickUp) — основне джерело: домен від неї похідний і може
    змінитись, а назва стабільна. Далі старий ланцюжок: домен, og:site_name,
    application-name, title, назва вітки."""
    candidates = []
    try:
        import site_name
        name = site_name.expected(branch, files)
        # літера іконки — латиницею без діакритики (Â→A)
        candidates.append(site_name.latin(name) or name)
    except Exception:
        pass

    domain = _domain_for(branch)
    if domain:
        host = re.sub(r"^www\.", "", domain.strip().lower())
        candidates.append(host.split(".")[0])

    text = _main_page_text(files)
    for rx in (OG_SITE_RX, APP_NAME_RX, PAGE_TITLE_RX):
        m = rx.search(text)
        if m:
            candidates.append(_match_group(m))

    candidates.append(branch)

    for cand in candidates:
        cand = (cand or "").strip()
        if not cand or _has_placeholder(cand):
            continue
        letter = _first_letter(cand)
        if letter:
            return letter
    return "W"                                   # white — останній рубіж


def _brand_color(files: dict) -> str:
    text = _main_page_text(files)
    for rx in (THEME_COLOR_RX, TW_PRIMARY_RX):
        m = rx.search(text)
        if m:
            return _match_group(m)
    return DEFAULT_COLOR


def _text_color(bg: str) -> str:
    """Контрастний колір літери — за відносною яскравістю тла."""
    try:
        h = (bg or "").lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError, TypeError, AttributeError):
        return "#FFFFFF"
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#111417" if lum > 0.6 else "#FFFFFF"


def build_svg(letter: str, bg: str, fg: str) -> str:
    """Іконка в тому ж стилі, що вже лежить у сотнях здорових віток.

    Шрифт — тільки системний: браузер рендерить фавіконку ізольовано, без CSS
    сторінки, тож веб-шрифт вайта тут не завантажиться."""
    if not HEX_COLOR_RX.match(bg or ""):
        bg = DEFAULT_COLOR                       # захист: не пишемо сміття в атрибут
    if not HEX_COLOR_RX.match(fg or ""):
        fg = "#FFFFFF"
    safe = (letter.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
        'width="64" height="64">\n'
        f'  <rect width="64" height="64" rx="14" fill="{bg}"/>\n'
        '  <text x="32" y="44" font-family="system-ui, sans-serif" '
        'font-size="34" font-weight="700"\n'
        f'        text-anchor="middle" fill="{fg}">{safe}</text>\n'
        '</svg>\n'
    )


def run_branch(files, all_paths, branch: str = ""):
    fileset = set(all_paths)
    lower_map = {}
    for p in all_paths:
        lower_map.setdefault(p.lower(), p)
    # Лише favicon.ico браузер підхоплює НЕЯВНО (без <link rel=icon>) — це
    # єдиний шлях, де можна рахувати «іконка вже є» без лінка. favicon.svg
    # чи .png у корені браузер САМ ніколи не запитує.
    root_favicon = any(posixpath.basename(p).lower() == "favicon.ico"
                       and "/" not in p for p in all_paths)

    read_bytes = None
    if branch:
        try:
            import runner
            base = runner.snapshot_dir(branch)

            def read_bytes(rel_path):                       # noqa: F811
                return (base / rel_path).read_bytes()
        except Exception:
            read_bytes = None

    issues = []
    no_icon_pages = []
    reasons = []              # чому саме сторінка лишилась без іконки

    for path, text in files.items():
        if not HEAD_RX.search(text):
            continue                       # частковина без <head> — не сторінка

        has_working = False
        page_problems = []
        for m in LINK_RX.finditer(text):
            tag = m.group(0)
            rel = _attr(tag, "rel")
            if not rel or "icon" not in rel.lower():
                continue
            state, msg = _link_state(path, _attr(tag, "href"), _attr(tag, "type"),
                                     fileset, lower_map, read_bytes)
            if state == "ok":
                has_working = True
            elif state == "broken":
                line = text.count("\n", 0, m.start()) + 1
                page_problems.append({"path": path, "line": line,
                                      "severity": "warn", "message": msg})

        if has_working or root_favicon:
            # сторінка іконку матиме; точкові дефекти інших лінків усе одно
            # показуємо — вони або мертві, або брешуть про тип
            issues.extend(page_problems)
        else:
            no_icon_pages.append(path)
            # без цього діагноз губився: точкові повідомлення таких сторінок у
            # звіт не йдуть (їх заміняє агрегована помилка), тож причину
            # («стокове фото», «битий data-URI», «немає файлу») переносимо в неї
            for p in page_problems:
                if p["message"] not in reasons:
                    reasons.append(p["message"])

    if no_icon_pages:
        shown = ", ".join(no_icon_pages[:4]) + ("…" if len(no_icon_pages) > 4 else "")
        message = (f"сторінок без робочої іконки: {len(no_icon_pages)} "
                   f"({shown}). Жоден <link rel=icon> не веде на наявний "
                   f"файл, і favicon.ico у корені вітки немає — браузер "
                   f"покаже порожню іконку")
        if reasons:
            message += ". Причина: " + "; ".join(reasons[:2])
        # HTTP смикаємо лише тут — на чистій вітці мережі не торкаємось
        if branch:
            message += _verify_on_deploy(branch, ["/favicon.svg", "/favicon.ico"])
        issues.append({"path": no_icon_pages[0], "line": None,
                       "severity": "warn", "message": message})
    if not issues:
        svg = _linked_svg_text(all_paths, branch)
        try:
            import brand_mark
            template = brand_mark.is_template_mark(svg)
        except Exception:
            template = False
        if template:
            issues.append({"path": sorted(files)[0] if files else "index.php",
                           "line": 1, "severity": "warn",
                           "message": ("favicon шаблонний — фон і одна "
                                       "літера; підбери знак: Медіа → "
                                       "Лого/Favicon")})
    return issues



def _linked_svg_text(all_paths, branch: str) -> str:
    """Вміст svg-іконки вітки (корінь) — для детекта шаблонності."""
    path = next((p for p in all_paths
                 if "/" not in p and posixpath.basename(p).lower()
                 in ("favicon.svg",)), "")
    if not path or not branch:
        return ""
    try:
        import runner
        return (runner.snapshot_dir(branch) / path).read_text(
            encoding="utf-8", errors="replace")
    except Exception:
        return ""

# --- link_actions (ручний Apply у «Медіа → Лого/Favicon») -------------------

FAVICON_PATH = "favicon.svg"
HEAD_OPEN_RX = re.compile(r"<head\b[^>]*>", re.I)


def _root_favicon(all_paths) -> str | None:
    """Наявний favicon.* у корені вітки (саме шлях, а не «так/ні»): лінк треба
    вести на НЬОГО. Раніше перевірявся лише факт наявності, а лінк усе одно
    писався на favicon.svg — на вітці з favicon.ico це створювало мертвий лінк."""
    for p in all_paths:
        if "/" not in p and posixpath.basename(p).lower().startswith("favicon."):
            return p
    return None


def _href_to(page: str, target: str) -> str:
    """Шлях до target ВІДНОСНО сторінки: '/favicon.svg' живе лише коли вітка
    в корені домену, а сторінки бувають у підпапках."""
    rel = posixpath.relpath(target, posixpath.dirname(page) or ".")
    return rel if rel.startswith("../") else "./" + rel


def _icon_href(page: str) -> str:
    return _href_to(page, FAVICON_PATH)


def _icon_link(page: str, target: str = FAVICON_PATH) -> str:
    ext = posixpath.splitext(target)[1].lower()
    mime = {".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
            ".webp": "image/webp"}.get(ext, "image/svg+xml")
    return f'<link rel="icon" type="{mime}" href="{_href_to(page, target)}">'


def _case_target(page: str, href: str | None, fileset: set, lower_map: dict) -> str | None:
    """Файл існує, але з іншим регістром → повертає РЕАЛЬНИЙ шлях.
    Таке чинимо точково (вирівнюємо регістр), а не підміняємо згенерованою
    іконкою: справжня іконка вітки цінніша за намальовану літеру."""
    if not href:
        return None
    cands = _resolve(page, href.strip())
    if not cands or any(c in fileset for c in cands):
        return None
    return next((lower_map[c.lower()] for c in cands if c.lower() in lower_map), None)


def _fix_page(page: str, text: str, target: str, needs_link: bool,
              fileset: set, lower_map: dict, read_bytes=None) -> str:
    """Приводить icon-лінки сторінки до стану «іконка справді буде».

    target — на що вести лінк: наявний favicon.* у корені або згенерований.
    needs_link — чи вставляти лінк сторінці, у якої його зовсім немає.

    Правило: здорові лінки не чіпаємо; регістр вирівнюємо; мертвий лінк
    (файла нема, порожній href, плейсхолдер, битий data-URI) замінюємо на
    робочий — а якщо на сторінці вже є робоча іконка, просто прибираємо
    мертвий лінк, щоб не плодити другу."""
    good = _icon_link(page, target)

    def state_of(tag):
        return _link_state(page, _attr(tag, "href"), _attr(tag, "type"),
                           fileset, lower_map, read_bytes)[0]

    has_working = any(
        "icon" in ((_attr(m.group(0), "rel") or "").lower())
        and (state_of(m.group(0)) == "ok"
             or _case_target(page, _attr(m.group(0), "href"), fileset, lower_map))
        for m in LINK_RX.finditer(text))

    state = {"placed": False, "kept": 0}

    def repl(m):
        tag = m.group(0)
        rel = (_attr(tag, "rel") or "").lower()
        if "icon" not in rel:
            return tag
        href = _attr(tag, "href")
        if state_of(tag) == "ok":
            state["kept"] += 1
            return tag
        case_hit = _case_target(page, href, fileset, lower_map)
        if case_hit:                            # файл є, помилка лише в регістрі
            state["kept"] += 1
            return tag.replace(href, _href_to(page, case_hit), 1)
        if has_working:
            return ""                           # іконка вже є — прибираємо мертвий
        if not state["placed"] and "apple-touch" not in rel:
            state["placed"] = True
            return good
        return ""                               # зайвий мертвий лінк

    out = LINK_RX.sub(repl, text)

    if needs_link and not state["placed"] and not state["kept"]:
        m = HEAD_OPEN_RX.search(out)
        if m:
            out = out[:m.end()] + "\n" + good + out[m.end():]
            state["placed"] = True
    # чи справді хоч десь послались на target — від цього залежить, чи треба
    # його генерувати (вирівняний регістр і прибраний зайвий лінк не потребують)
    return out, state["placed"]


def link_actions(files, all_paths, branch: str = "", force: bool = False,
                 version: str = ""):
    """Зводить лінки сторінок до однієї робочої іконки; якщо у вітці її
    немає — генерує знак brand_mark у favicon.svg. Викликається і ручним
    Apply з «Медіа → Лого/Favicon», і автофіксом (fix_branch, з 21.10; до
    того з 01.10 автофікса не було — два фікси конфліктували між собою, тепер
    він один).

    force=True — вибір людини АВТОРИТАРНИЙ: усі icon-лінки (крім apple)
    переписуються на target з ?v=<version> і дедупляться до одного, навіть
    якщо старий лінк «робочий» (data:, чужа іконка, лінк на файл, якого
    немає — кейс alnewvad/quuskafs 01.10: href=./favicon.svg без файла,
    вкладка тримала кеш прев'ю-хоста)."""
    if force:
        return _force_link_actions(files, all_paths, branch, version)
    fileset = set(all_paths)
    lower_map = {}
    for p in all_paths:
        lower_map.setdefault(p.lower(), p)
    root = _root_favicon(all_paths)
    target = root or FAVICON_PATH
    # Явний <link> потрібен для будь-якого target, крім favicon.ico — його
    # єдиного браузер підхоплює без лінка (те саме правило, що в run_branch).
    implicit = bool(root) and posixpath.basename(root).lower() == "favicon.ico"

    read_bytes = None
    if branch:
        try:
            import runner
            base = runner.snapshot_dir(branch)

            def read_bytes(rel_path):                       # noqa: F811
                return (base / rel_path).read_bytes()
        except Exception:
            read_bytes = None

    actions = []
    used_target = False
    for path, text in files.items():
        if not HEAD_RX.search(text):
            continue                            # частковина без <head>
        new, used = _fix_page(path, text, target, not implicit,
                              fileset, lower_map, read_bytes)
        if new != text:
            actions.append({"type": "edit", "path": path, "content": new})
        used_target = used_target or used

    if used_target and not root:
        bg = _brand_color(files)
        try:
            import brand_mark
            svg = brand_mark.pick(files, branch, base_color=bg)
        except Exception:
            svg = build_svg(_brand_letter(files, branch), bg, _text_color(bg))
        actions.append({"type": "create", "path": FAVICON_PATH, "content": svg})
    return actions


def fix_branch(files, all_paths, branch: str = ""):
    """Автофікс = link_actions без force (вибір людини в UI сильніший)."""
    return link_actions(files, all_paths, branch)


def _force_link_actions(files, all_paths, branch: str, version: str):
    """Авторитарний режим Apply: один robочий icon-лінк на сторінку.

    target завжди FAVICON_PATH (Apply щойно записав туди обраний знак);
    href — відносний до сторінки, з ?v= для пробиття кешу прев'ю-хоста."""
    actions = []
    ver = f"?v={version}" if version else ""
    for path, text in files.items():
        if not HEAD_RX.search(text):
            continue
        href = _href_to(path, FAVICON_PATH) + ver
        good = f'<link rel="icon" type="image/svg+xml" href="{href}">'
        seen = {"n": 0}

        def repl(m):
            tag = m.group(0)
            rel = (_attr(tag, "rel") or "").lower()
            if "icon" not in rel or "apple" in rel:
                return tag
            seen["n"] += 1
            return good if seen["n"] == 1 else ""

        new = LINK_RX.sub(repl, text)
        if seen["n"] == 0:
            m = HEAD_OPEN_RX.search(new)
            if m:
                new = new[:m.end()] + "\n  " + good + new[m.end():]
        if new != text:
            actions.append({"type": "edit", "path": path, "content": new})
    return actions

