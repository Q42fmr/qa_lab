"""Внутрішні лінки сторінок мають вести на файли, які справді є у вітці.

Генератор інколи пише в `href` не ім'я файлу, а «слаг»: `<a href="services">`
при наявному `services.html`, або вкорочений префікс довгої назви —
`href="service-dvr"` при файлі
`service-dvr-para-segurança-sistema-de-gravação-de-vídeo-cazatutdc.html`.
Обидва варіанти на `php -S` дають 404: сервер віддає лише наявні файли.

Ціль шукається у два кроки, і жоден із них не вгадує:
  1. ТОЧНО: `href` + `.html`/`.php` — так лагодяться 404 лінки корпусу;
  2. ПРЕФІКС: назви нормалізуються (без діакритики, регістру, розділювачі
     в дефіс), і береться файл, чий стем ПОЧИНАЄТЬСЯ з нормалізованого
     href. Це і є «подібний файл»: `service-cameras-ip` ↔
     `service-câmeras-ip-de-alta-definição-vigilância-remota-247-…`.
     Підходить лише ОДИН кандидат — інакше не чіпаємо.

Коли не розв'язалось — репортимо без фікса. Таких у корпусі 371, і це не
описки, а лінки в нікуди: юридичний шаблон посилається на `services.html`,
`terms.html`, `privacy-policy.html`, яких у вітці немає зовсім
(є `practice.html`, `attorneys.html`). Підставити туди `practice.html` —
це вже здогад про зміст, а не виправлення шляху.

Не чіпаємо: якорі (`#form`), абсолютні URL, `//`, `mailto:`/`tel:`/
`javascript:`, шляхи від кореня (`/about` — так налаштований веб-сервер,
а не вітка) і порожній href (це `empty_href`).
"""
import os
import posixpath
import re
import unicodedata

NAME = "Лінк веде на наявний файл"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"links"}
PROJECTS = ["php"]
DESCRIPTION = ("Внутрішній href має вказувати на файл, який є у вітці. Автофікс "
               "дописує розширення (`services` → `services.html`) або підставляє "
               "єдиний файл, чия назва починається з href "
               "(`service-dvr` → `service-dvr-para-segurança-….html`). Якщо цілі "
               "немає — лише error, бо підставляти інший файл означало б гадати.")
FILES = ["*.html", "*.htm", "*.php"]

# `(?<![:\w\[.-])href` — не `:href`/`v-bind:href`/`x-bind:href`/`[href]`:
# вираз шаблону (Alpine/Vue/Angular), а не адреса (cedko-ia 27.10: «sol.url»)
A_HREF_RX = re.compile(
    r"""(<a\b[^>]*?(?<![:\w\[.-])href\s*=\s*)(["'])([^"']*)\2""", re.I)
PAGE_EXT = (".html", ".htm", ".php")
# зовнішнє або не-навігаційне: чіпати не наша справа
SKIP_PREFIX = ("#", "//", "/", "?", "http:", "https:", "mailto:", "tel:",
               "javascript:", "data:", "sms:", "ftp:", "about:")
# коротший префікс не судимо: «a» чи «go» збігся б із половиною вітки
MIN_PREFIX = 3


def _norm(s: str) -> str:
    """Без діакритики й регістру, розділювачі — в дефіс: «Instalação Profissional»
    і «instalacao-profissional» стають однаковими."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.casefold()).strip("-")


def _split(href: str) -> tuple[str, str]:
    """(шлях, хвіст) — ?query і #anchor зберігаються у фіксі як були.
    Шлях одразу без `./`: у вітках так пишуть майже всі лінки, і без цього
    `./solutions.html` не збігався б із наявним `solutions.html`."""
    m = re.match(r"([^?#]*)(.*)", href, re.S)
    path = m.group(1)
    while path.startswith("./"):
        path = path[2:]
    return ("" if path == "." else path), m.group(2)


class _Index:
    """Індекс файлів вітки. Будується РАЗ на вітку: `run_checks` ганяє чек по
    7000+ віток, а перебудова словника на кожен href робила скан квадратичним
    (повний прогін корпусу не вкладався у півгодини)."""

    __slots__ = ("low", "stems")

    def __init__(self, all_paths):
        self.low = {p.lower(): p for p in all_paths}
        self.stems = [(_norm(os.path.splitext(os.path.basename(p))[0]), p)
                      for p in all_paths if p.lower().endswith(PAGE_EXT)]

    def resolve(self, path: str) -> str | None:
        """Реальний файл для href або None. Не вгадує: або точний збіг, або
        ЄДИНИЙ файл-продовження."""
        if not path or path.endswith("/") or path.lower() in self.low:
            return None
        base = os.path.splitext(path)[0] or path
        for ext in PAGE_EXT:
            hit = self.low.get((base + ext).lower())
            if hit:
                return hit
        stem = _norm(os.path.basename(base))
        if len(stem) < MIN_PREFIX:
            return None
        hits = [p for s, p in self.stems if s.startswith(stem)]
        return hits[0] if len(hits) == 1 else None


def _broken(text: str, idx: "_Index", page: str):
    """(match, шлях, ціль|None) для кожного внутрішнього href, що не веде на файл.

    Шлях розв'язується ВІДНОСНО СТОРІНКИ, а не кореня вітки: `../contact.html`
    зі сторінки в `blog/` веде саме на кореневий `contact.html` і є цілком
    правильним. Без цього чек оголосив би такі лінки битими, а фікс переписав
    би їх на `contact.html` — і зламав би для всіх підтек."""
    base = posixpath.dirname(page)
    for m in A_HREF_RX.finditer(text):
        href = m.group(3).strip()
        if not href or href.lower().startswith(SKIP_PREFIX):
            continue
        rel, _tail = _split(href)
        if not rel or rel.endswith("/"):
            continue                     # лінк на теку (`../`) — справа сервера
        # у корпусі співіснують дві конвенції: лінк відносно СТОРІНКИ
        # (`../contact.html` з `blog/`) і відносно КОРЕНЯ вітки
        # (`sub/contacts.html` зі сторінки в тій самій `sub/`). Обидві робочі,
        # тож битим лінк вважається, лише якщо не веде на файл НІ ТАК, НІ ТАК —
        # інакше фікс ламав би одну з конвенцій.
        cands = [posixpath.normpath(posixpath.join(base, rel))] if base else []
        cands.append(posixpath.normpath(rel))
        cands = [c for c in cands if c not in ("", ".")]
        if any(c.lower() in idx.low for c in cands):
            continue
        target = next((t for t in (idx.resolve(c) for c in cands) if t), None)
        yield m, cands[0] if cands else rel, target



def run_branch(files, all_paths):
    idx = _Index(all_paths)
    issues = []
    for page in sorted(files):
        text = files[page]
        for m, path, target in _broken(text, idx, page):
            line = text.count("\n", 0, m.start()) + 1
            if target:
                issues.append({
                    "path": page, "line": line, "severity": "error",
                    "message": f"лінк '{path}' не веде на файл вітки — "
                               f"фікс замінить на '{target}'"})
            else:
                issues.append({
                    "path": page, "line": line, "severity": "error",
                    "message": f"лінк '{path}' веде в нікуди: такого файлу у "
                               f"вітці немає і схожого теж (підставити інший — "
                               f"це вже здогад про зміст, роби руками)"})
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    idx = _Index(all_paths)
    actions = []
    for page in sorted(files):
        text = files[page]
        out, last, changed = [], 0, False
        for m, path, target in _broken(text, idx, page):
            if not target:
                continue
            _p, tail = _split(m.group(3).strip())
            # ціль записуємо ВІДНОСНО сторінки: для `blog/post.html` коренева
            # `contact.html` має лишитись `../contact.html`, а не стати кореневою
            base = posixpath.dirname(page)
            href = posixpath.relpath(target, base) if base else target
            out.append(text[last:m.start()])
            out.append(m.group(1) + m.group(2) + href + tail + m.group(2))
            last = m.end()
            changed = True
        if not changed:
            continue
        out.append(text[last:])
        actions.append({"type": "edit", "path": page, "content": "".join(out)})
    return actions


# ---------------------------------------------------------------- ручний вибір
# Те, що чек розвʼязати не може (371 лінк корпусу), — це не описка шляху, а
# питання «яка сторінка тут мала бути». Відповідає людина, але не руками по
# файлах: однакові биті лінки збираються в ОДИН вибір, і обраний файл
# підставляється у всі входження (вкладка «Тести» → «🔗 Биті лінки»).

def _pages(all_paths) -> list[str]:
    return sorted(p for p in all_paths if p.lower().endswith(PAGE_EXT))


def _suggest(href: str, pages: list[str]) -> str | None:
    """Найближча за назвою сторінка — саме підказка, не автозаміна."""
    import difflib
    stem = _norm(os.path.splitext(os.path.basename(_split(href)[0]))[0])
    if not stem:
        return None
    stems = {_norm(os.path.splitext(os.path.basename(p))[0]): p for p in pages}
    hit = difflib.get_close_matches(stem, list(stems), n=1, cutoff=0.6)
    return stems[hit[0]] if hit else None


def dead_links(files, all_paths) -> list[dict]:
    """Групи нерозвʼязаних лінків: один href — один вибір.

    [{href, count, usages:[{path,line}], candidates:[...], suggest}]
    """
    idx = _Index(all_paths)
    pages = _pages(all_paths)
    groups: dict[str, dict] = {}
    for page in sorted(files):
        text = files[page]
        for m, _path, target in _broken(text, idx, page):
            if target:
                continue                 # це полагодить автофікс
            href = m.group(3).strip()
            g = groups.setdefault(href, {"href": href, "count": 0, "usages": [],
                                         "candidates": pages,
                                         "suggest": _suggest(href, pages)})
            g["count"] += 1
            g["usages"].append({"path": page,
                                "line": text.count("\n", 0, m.start()) + 1})
    return [groups[k] for k in sorted(groups)]


def apply_choices(files, all_paths, choices: dict) -> list[dict]:
    """Підставляє обрані файли у биті лінки. Ключ — href як він у розмітці,
    значення — файл вітки. Шлях пишеться ВІДНОСНО сторінки, ?query і #anchor
    зберігаються — рівно як у fix_branch."""
    picked = {h: t for h, t in (choices or {}).items() if t}
    if not picked:
        return []
    known = {p.lower(): p for p in all_paths}
    for target in set(picked.values()):
        if target.lower() not in known:
            raise ValueError(f"такого файлу у вітці немає: {target}")

    idx = _Index(all_paths)
    actions = []
    for page in sorted(files):
        text = files[page]
        out, last, changed = [], 0, False
        for m, _path, target in _broken(text, idx, page):
            if target:
                continue
            href = m.group(3).strip()
            chosen = picked.get(href)
            if not chosen:
                continue
            _p, tail = _split(href)
            base = posixpath.dirname(page)
            rel = posixpath.relpath(chosen, base) if base else chosen
            out.append(text[last:m.start()])
            out.append(m.group(1) + m.group(2) + rel + tail + m.group(2))
            last = m.end()
            changed = True
        if changed:
            out.append(text[last:])
            actions.append({"type": "edit", "path": page, "content": "".join(out)})
    return actions
