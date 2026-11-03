"""Фавіконка vue-вайта: лінк мусить вести на файл, який у вітці справді є.

Що в корпусі (230 віток з підв'язаним доменом):
  * `index.html` **усіх 230** посилається на `/favicon.ico`, якого немає
    ніде — ні в корені, ні в `public/`. Це гарантований 404 на кожне
    відкриття сторінки і порожня іконка у вкладці;
  * у 19 вітках поруч лежить справжня `public/favicon.svg` (лишок шаблону) —
    там достатньо перевести лінк на неї;
  * у решті 211 іконки немає зовсім, тож її треба згенерувати;
  * ще 134 вітки тягнуть мертвий `<link rel="apple-touch-icon"
    href="/apple-touch-icon.png">` — png немає, і підставляти туди svg не
    можна: Apple його не читає, це була б нова поломка замість фікса.

Резолв. `public/` при білді копіюється в корінь dist, тож `/favicon.svg`
живий, якщо у вітці є `public/favicon.svg` АБО `favicon.svg` у корені.
`data:`-іконка валідна за побудовою.

Виправлення — ЛИШЕ руками у «Медіа → Лого/Favicon» (Apply сам ставить
versioned-лінк і, за потреби, генерує знак brand_mark). Стара механіка:
  * ціль — найкраща НАЯВНА іконка вітки: `.svg` → `.png` → `.ico`
    (svg перший, бо саме він у цих вайтах і лежить);
  * немає жодної — генеруємо `public/favicon.svg` тим самим генератором, що
    й фавіконки php-вайтів (`checks/favicon.build_svg`): літера з
    підв'язаного домену, тло з `theme-color` вайта;
  * битий лінк переписується на цю ціль разом з `type=`; якщо живий лінк на
    неї вже є — битий просто прибирається, щоб не було двох однакових;
  * мертвий `apple-touch-icon` без png-цілі прибирається;
  * лінка на іконку немає взагалі — додається у `<head>`.
"""
import posixpath
import re


NAME = "Фавіконка: лінк веде на наявний файл"
GROUP = "tests"    # лише детект (warn); заміна знака — руками у
                   # Медіа → Лого/Favicon (Apply сам ставить versioned-лінк).
                   # Автофікса тут свідомо НЕМАЄ: три механіки, що міняли
                   # favicon (цей чек, php-чек favicon і вкладка), конфліктували
PROJECTS = ["node"]
DESCRIPTION = ("Лінк на іконку в index.html має вести на наявний файл; "
               "шаблонний знак «фон + одна літера» — теж warn. "
               "Виправлення руками: Медіа → Лого/Favicon.")
FILES = ["index.html"]

PAGE = "index.html"

# інлайн-svg у href (`data:image/svg+xml,<svg .../>`) містить '>', тому тег
# читаємо з урахуванням лапок, а не до першого '>'
LINK_RX = re.compile(r"""<link\b(?:[^>"']|"[^"]*"|'[^']*')*>""", re.I)
REL_RX = re.compile(r"""\brel\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
HREF_RX = re.compile(r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)

ICON_EXT = (".svg", ".png", ".ico", ".webp", ".gif", ".jpg", ".jpeg")
# svg перший свідомо: саме він лежить у цих вайтах, і він масштабується
PREFER = (".svg", ".png", ".ico")


def _domain_for(branch: str) -> str | None:
    """Підв'язаний домен вітки. Окремо — щоб підміняти в тестах."""
    if not branch:
        return None
    try:
        import domains
        return domains.active_for(branch)
    except Exception:
        return None


def _attr(tag: str, rx) -> str:
    m = rx.search(tag)
    if not m:
        return ""
    return (m.group(1) if m.group(1) is not None else m.group(2)).strip()


def _icon_links(text: str) -> list[re.Match]:
    return [m for m in LINK_RX.finditer(text)
            if "icon" in _attr(m.group(0), REL_RX).lower()]


def _resolves(href: str, all_paths) -> bool:
    """`/favicon.svg` живий, якщо є public/favicon.svg або favicon.svg у корені
    (public/ їде в корінь dist)."""
    rel = href.split("?")[0].split("#")[0].lstrip("/")
    while rel.startswith("./"):
        rel = rel[2:]
    if not rel:
        return False
    known = {p.lower() for p in all_paths}
    return rel.lower() in known or posixpath.join("public", rel).lower() in known


def _existing_icon(all_paths) -> str | None:
    """Найкраща наявна іконка вітки → href від кореня."""
    cands = []
    for p in all_paths:
        low = p.lower()
        if not low.endswith(ICON_EXT):
            continue
        rel = p[len("public/"):] if low.startswith("public/") else p
        if "/" in rel:                      # іконка живе в корені сайту
            continue
        if "favicon" not in rel.lower() and "icon" not in rel.lower():
            continue
        cands.append(rel)
    if not cands:
        return None
    cands.sort(key=lambda r: (PREFER.index(posixpath.splitext(r)[1].lower())
                              if posixpath.splitext(r)[1].lower() in PREFER
                              else len(PREFER), r))
    return "/" + cands[0]


def _state(files: dict, all_paths):
    """(text, [(match, href, живий?)], наявна ціль|None) або None."""
    text = files.get(PAGE)
    if text is None:
        return None
    links = []
    for m in _icon_links(text):
        href = _attr(m.group(0), HREF_RX)
        alive = href.startswith("data:") or (bool(href) and _resolves(href, all_paths))
        links.append((m, href, alive))
    return text, links, _existing_icon(all_paths)


def run_branch(files, all_paths, branch=""):
    got = _state(files, all_paths)
    if not got:
        return []
    text, links, have = got
    if not links:
        return [{"path": PAGE, "line": 1, "severity": "warn",
                 "message": "у <head> немає лінка на іконку — вкладка без "
                            "фавіконки; підбери знак: Медіа → Лого/Favicon"}]
    issues = []
    for m, href, alive in links:
        if alive:
            continue
        line = text.count("\n", 0, m.start()) + 1
        rel = _attr(m.group(0), REL_RX).lower()
        target = (f"наявна іконка вітки: {have}" if have else
                  f"іконки у вітці немає зовсім")
        if "apple-touch-icon" in rel and (not have or not have.endswith(".png")):
            target = "png-іконки у вітці немає"
        issues.append({"path": PAGE, "line": line, "severity": "warn",
                       "message": f"лінк на іконку '{href}' веде в нікуди: "
                                  f"такого файлу у вітці немає; {target} — "
                                  f"підбери знак: Медіа → Лого/Favicon"})
    if not issues and have and have.endswith(".svg"):
        svg = _icon_text(all_paths, have, branch)
        try:
            import brand_mark
            template = brand_mark.is_template_mark(svg)
        except Exception:
            template = False
        if template:
            issues.append({"path": PAGE, "line": 1, "severity": "warn",
                           "message": ("favicon шаблонний — фон і одна "
                                       "літера; підбери знак: Медіа → "
                                       "Лого/Favicon")})
    return issues


def _icon_text(all_paths, href: str, branch: str) -> str:
    """Вміст іконки з href від кореня сайту: public/<rel> або <rel>."""
    rel = href.lstrip("/")
    path = next((p for p in all_paths
                 if p.lower() in (f"public/{rel}".lower(), rel.lower())), "")
    if not path or not branch:
        return ""
    try:
        import runner
        return (runner.snapshot_dir(branch) / path).read_text(
            encoding="utf-8", errors="replace")
    except Exception:
        return ""

