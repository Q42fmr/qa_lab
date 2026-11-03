"""Пошта і доменні назви ↔ домен, підв'язаний до вітки в ClickUp.

Перший чек набору vue-віток. Домен вайта відомий: у тасці ClickUp поле
"Required Domains" йде в тому ж порядку, що й вітки у "Safe Page", і при
імпорті пара пишеться в `domains.json` → `domains.active_for(branch)`.
Усе, що вайт каже про СЕБЕ — пошта у контактах, canonical, og:url, siteUrl,
sitemap, robots — має вести на цей домен. Вітки без підв'язаного домену не
судимо.

Що зловлено на корпусі 65 віток з доменом:

  * `info@{{DOMAIN}}` (427 входжень) — у php-вайтах `{{DOMAIN}}` це
    легітимний плейсхолдер, який підставляє деплой. У Vue це **інтерполяція
    шаблону**: змінної `DOMAIN` у білді немає, тож vite-ssg рендерить
    порожній рядок. У зібраному `dist/index.php` видно рівно це — `info@`
    без домену (8 входжень) і `info@{{DOMAIN}}` там, де текст не потрапив у
    шаблон (4). Тобто на живій сторінці пошти немає взагалі;
  * `kontakt@passobjip.com`, `datenschutz@passobjip.com` (437 входжень у 19
    вітках) — хвіст чужого шаблону (PassoBjip), який приїхав разом з
    деревом `pages/` + `i18n/`. Витік чужого бренду і неробоча пошта;
  * `https://domain.com/` у `public/robots.txt` і `public/sitemap.xml` (638
    входжень) — заготовка, яка їде у dist як є: пошуковик читає сайтмап
    чужого домену;
  * `siteUrl` / `canonical` / `og:url` на `passobjip.com` у залишках
    `nuxt.config.ts`.
  * `https://{{DOMAIN}}/og-image.jpg` — брейс у ролі ХОСТА лінка. Позицій
    самопосилання п'ять, а брейс ламає будь-який URL: у білді лишається
    `https:///og-image.jpg`. На корпусі таких 770 у 147 вітках — og:image
    (167), twitter:image (147) і 356 у видимому тексті юридичних сторінок;
    canonical/og:url (100) ловились і без цього. Ручна заміна брейса на
    «https://домен/» дає подвійну схему (`https://https://дом//og-image.jpg`),
    тому автофікс міняє САМЕ хост.
  * `info@alemoid-praveiv-br-pt` — хостом стоїть НАЗВА СУСІДНЬОЇ ВІТКИ:
    генератор підставляє слаг вітки до мутації (`nwf-alaroovk-praveiv-br-pt`
    -> `alemoid-praveiv-br-pt`, `nwf-sajaej-aujeni-br-pt` ->
    `sadaaaujeni-br-pt`). Домену без зони не існує - пошта не доходить,
    canonical вказує в порожнечу. Заміряно: 4 вітки, 43 позиції (пошти 18,
    canonical/og:url 11, решта - og:image, JSON-LD і видимий текст). Чек їх
    не бачив, бо `_HOST` вимагає крапку; `nwf-sajaej-aujeni-br-pt` у поштах
    чиста і трималась лише на самопосиланнях.

Як не ловимо зайвого — без жодних списків TLD:
  * домен вважається «нашим» тільки якщо він стоїть у САМОПОСИЛЬНІЙ позиції
    (пошта, canonical, og:url, siteUrl, <loc>, Sitemap:). Сторонні лінки
    (`www.sbb.ch`, `images.unsplash.com`, `www.w3.org`, `schema.org`) у ці
    позиції не потрапляють і не чіпаються;
  * решта згадок звіряється ЛИШЕ з доменами, які вже спалились вище: якщо
    `passobjip.com` знайдено у пошті, то і його згадки в i18n-текстах наші.
    Тому `index.ts`, `vue.js`, `nuxt.com/docs` у тексті нікого не хвилюють —
    їх ніхто не оголошував доменом вайта;
  * приклади у полях вводу (`placeholder="seu@empresa.com.br"`),
    зарезервовані example.com/.test, асети з @ у назві (`hero@2x.png`) і
    authority всередині URL (Sentry DSN) — як у php-чеку `contacts`;
  * `package-lock.json` не сканується.

Автофікс міняє тільки доменну частину: локальна частина пошти, шлях URL і
все навколо лишаються.
"""
import fnmatch
import re

NAME = "Пошта і домени ↔ домен вітки"
GROUP = "auto"     # звалідовано на 65 vue-вітках з підв'язаним доменом:
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"domain", "email"}
                   # 3032 знахідки, після автофікса не лишається жодної,
                   # правиться 704 файли. Дискримінація перевірена на парі
                   # apoj-gencaa-br-pt (121 знахідка: {{DOMAIN}}, чужий
                   # passobjip.com, domain.com) ↔ nwf-apoj-gencaa-br-pt
                   # (та сама вітка вже з правильною поштою: рівно 10 —
                   # тільки sitemap/robots, жодного фолсу на 12 коректних
                   # info@apojgenc.sbs). json/xml лишаються валідними.
                   # Правило «брейс як хост лінка» доміряно на 215 вітках з
                   # доменом: 3322 -> 3997 знахідок (+675 у 166 вітках),
                   # 1008 файлів під правку; після фікса не лишається жодного
                   # URL з брейсом, повторний прогін не змінює нічого,
                   # подвійних схем/слешів нема, json/xml валідні.
PROJECTS = ["node"]
DESCRIPTION = ("Усе, що вайт каже про себе — пошта, canonical, og:url, siteUrl, "
               "og:image, sitemap, robots і будь-який лінк — має вести на домен, "
               "підв'язаний до вітки в ClickUp. Ловить `{{DOMAIN}}` (у Vue це "
               "інтерполяція, у білді порожньо), чужий бренд, заготовку "
               "domain.com і хост без зони, що є назвою сусідньої вітки "
               "(`info@alemoid-praveiv-br-pt`). Автофікс міняє саме хост.")
# лише те, що їде до відвідувача: README та інша репозиторна проза — не вайт
FILES = ["*.vue", "*.ts", "*.tsx", "*.js", "*.mjs", "*.cjs", "*.json",
         "*.html", "*.htm", "*.xml", "*.txt"]

SKIP_FILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml")

# пошта: домен або справжній (з крапкою і зоною), або брейс-літерал
_HOST = r"[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
_BRACE = r"\{\{\s*DOMAIN(?:_NAME)?\s*\}\}"
# Хост БЕЗ крапки, що має суфікс вітки корпусу `-<країна>-<мова>`: генератор
# інколи ставить хостом назву СУСІДНЬОЇ вітки. Кейс
# nwf-alaroovk-praveiv-br-pt: `info@alemoid-praveiv-br-pt` у футері, кукі-банері
# й політиці (7 входжень) плюс той самий рядок хостом canonical, og:url,
# twitter:url, og:image, JSON-LD url/logo і видимим текстом (ще 9) - при
# підв'язаному `alaroovkprav.live`, який у тій же вітці стоїть у
# ServiceAgreementTerms.vue. Домену без зони не існує: пошта не доходить,
# canonical вказує в порожнечу. `_HOST` вимагає крапку, тому чек не бачив
# жодної з 16 позицій.
# Чому саме суфікс, а не «будь-який хост без крапки». Пошти: на 1597 вітках
# рядків `x@y` з хостом без крапки 14 (49 входжень), і лише три з них -
# хости-вітки (18 входжень: alemoid-praveiv-br-pt 7, devafibiro-rofa-br-pt 6,
# nozulaavupa-gencaa-br-pt 5). Решта - НЕ пошти, і контекст це доводить:
# `Pick@Post` (21) - сервіс Swiss Post у німецькому тексті `services-data.ts`,
# `rigor@ai:~$ 404.error` - шел-промпт на сторінці 404, `obrigado@residencia` -
# декор у блоці подяки, `info@vikqeNenekeoc com` - з'їдена крапка (це інший
# дефект, не наш). Наївне правило переписало б усі чотири.
# Самопосилання: тих самих хостів у canonical/og:url на корпусі 11 у 4 вітках
# (canonical 4, og/twitter:url 7). Четверта - `nwf-sajaej-aujeni-br-pt`
# (`sadaaaujeni-br-pt` x3): у поштах вона чиста, дефект лише в самопосиланнях,
# тож без цього правила у SELF_URL_RX вона б лишилась невидимою.
# Кінцева межа обов'язкова: без неї `info@foo-br-ptx` дав би хост `foo-br-pt`,
# і фікс зліпив би `info@домен` плюс осиротілий `x`.
_BRANCHISH = r"[A-Za-z0-9\-]+-[a-z]{2}-[a-z]{2}(?![\w\-.])"
_ANY_HOST = rf"{_HOST}|{_BRACE}|{_BRANCHISH}"
EMAIL_RX = re.compile(rf"[A-Za-z0-9._%+\-]+@(?:{_BRACE}|{_HOST}|{_BRANCHISH})")
BRACE_RX = re.compile(_BRACE)
# приклад у полі вводу, а не контакт: атрибут HTML і властивість обʼєкта в TS
PLACEHOLDER_RX = re.compile(
    r"""placeholder\s*[=:]\s*(?:"[^"]*"|'[^']*'|`[^`]*`)""", re.I)
# @ всередині URL — це логін@хост (Sentry DSN), а не пошта
URL_AUTHORITY_RX = re.compile(r"(?:\\?/){2}$")
# 'домени', що насправді файли: hero@2x.png
ASSET_TLD = ("png", "jpg", "jpeg", "webp", "svg", "gif", "ico", "avif", "bmp",
             "css", "js", "json", "html", "htm", "php", "xml", "txt",
             "woff", "woff2", "ttf", "eot", "mp4", "webm", "pdf", "zip")
RESERVED_DOMAINS = ("example.com", "example.net", "example.org", "example.edu")
RESERVED_TLD = ("example", "test", "invalid", "localhost")

# самопосильні позиції: тут може стояти лише власний домен вайта
SELF_URL_RX = re.compile(
    rf"""(?:
        rel\s*=\s*["']canonical["'][^>]{{0,120}}?https?://(?P<a>{_ANY_HOST})
      | (?:og|twitter):url["'][^>]{{0,120}}?https?://(?P<b>{_ANY_HOST})
      | site_?[Uu]rl\s*[:=]\s*["'`]https?://(?P<c>{_ANY_HOST})
      | <loc>\s*https?://(?P<d>{_ANY_HOST})
      | Sitemap\s*:\s*https?://(?P<e>{_ANY_HOST})
    )""", re.X)
KIND_LABEL = {"a": "canonical", "b": "og:url", "c": "siteUrl",
              "d": "sitemap <loc>", "e": "robots Sitemap"}
# {{DOMAIN}} у ролі ХОСТА абсолютного URL. SELF_URL_RX знає лише п'ять
# самопосильних позицій, але брейс у лінку ламає будь-яку: у білді від
# `https://{{DOMAIN}}/og-image.jpg` лишається `https:///og-image.jpg`.
# На корпусі таких URL 770 у 147 вітках — og:image (167), twitter:image (147)
# і 356 у видимому тексті юридичних сторінок; canonical/og:url (100) вже
# ловились. Ручна заміна брейса на «https://домен/» дає подвійну схему
# (`https://https://vivhurti.cyou//og-image.jpg`), тому міняємо САМЕ хост.
URL_BRACE_RX = re.compile(rf"(?:https?:)?//(?P<host>{_BRACE})")


def _domain_for(branch: str) -> str | None:
    """Підв'язаний домен вітки. Окремою функцією — щоб підміняти в тестах."""
    if not branch:
        return None
    try:
        import domains
        return domains.active_for(branch)
    except Exception:
        return None


def _scanned(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name in SKIP_FILES:
        return False
    return any(fnmatch.fnmatch(name, pat) for pat in FILES)


def _own(host: str, domain: str) -> bool:
    h = host.lower().lstrip(".")
    return h == domain or h == "www." + domain


def _skip_host(host: str) -> bool:
    """Не бренд вайта: приклади зі стандарту і файли з @ у назві."""
    h = host.lower()
    if h in RESERVED_DOMAINS or h.rsplit(".", 1)[-1] in RESERVED_TLD:
        return True
    return h.rsplit(".", 1)[-1] in ASSET_TLD


def _protected(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in PLACEHOLDER_RX.finditer(text)]


def _inside(spans, pos: int) -> bool:
    return any(a <= pos < b for a, b in spans)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _self_refs(text: str):
    """(позиція, хост, підпис позиції) для кожного самопосилання."""
    for m in SELF_URL_RX.finditer(text):
        for key, host in m.groupdict().items():
            if host:
                yield m.start(key), host, KIND_LABEL[key]
                break


def _brace_urls(text: str):
    """(позиція, початок URL) для {{DOMAIN}} у ролі хоста лінка."""
    spans = _protected(text)
    taken = {pos for pos, _host, _kind in _self_refs(text)}
    for m in URL_BRACE_RX.finditer(text):
        pos = m.start("host")
        if pos in taken or _inside(spans, pos):
            continue
        yield pos, m.group(0)


def _emails(text: str):
    """(позиція, хост, ціла пошта) для кожної справжньої пошти файлу."""
    spans = _protected(text)
    for m in EMAIL_RX.finditer(text):
        if _inside(spans, m.start()) or URL_AUTHORITY_RX.search(text[:m.start()]):
            continue
        host = m.group(0).split("@", 1)[1]
        if not BRACE_RX.fullmatch(host) and _skip_host(host):
            continue
        yield m.start(), host, m.group(0)


def _collect(files: dict, domain: str) -> tuple[list[dict], set[str]]:
    """Знахідки у самопосильних позиціях + домени, які там спалились."""
    issues, leaked = [], set()
    for path in sorted(files):
        if not _scanned(path):
            continue
        text = files[path]
        for pos, host, email in _emails(text):
            if _own(host, domain):
                continue
            local = email.split("@", 1)[0]
            why = ("це інтерполяція Vue — у білді лишається голе "
                   f"'{local}@'" if BRACE_RX.fullmatch(host)
                   else "чужий домен")
            issues.append({"path": path, "line": _line(text, pos),
                           "severity": "error",
                           "message": f"пошта {email} — {why}; "
                                      f"має бути {local}@{domain}"})
            if not BRACE_RX.fullmatch(host):
                leaked.add(host.lower().lstrip("."))
        for pos, host, kind in _self_refs(text):
            if _own(host, domain):
                continue
            issues.append({"path": path, "line": _line(text, pos),
                           "severity": "error",
                           "message": f"{kind}: https://{host} — "
                                      f"має бути https://{domain}"})
            if not BRACE_RX.fullmatch(host):
                leaked.add(host.lower().lstrip("."))
        for pos, url in _brace_urls(text):
            issues.append({"path": path, "line": _line(text, pos),
                           "severity": "error",
                           "message": f"лінк {url} — це інтерполяція Vue, у "
                                      f"білді лишиться схема без хоста; "
                                      f"має бути https://{domain}"})
    return issues, leaked


def _mention_rx(hosts: set[str]) -> re.Pattern | None:
    """Згадки спаленого домену будь-де, включно з www. і без схеми."""
    if not hosts:
        return None
    body = "|".join(re.escape(h) for h in sorted(hosts, key=len, reverse=True))
    return re.compile(rf"(?<![\w.-])(?:www\.)?(?:{body})(?![\w-])", re.I)


def run_branch(files, all_paths, branch):
    domain = _domain_for(branch)
    if not domain:
        return []
    issues, leaked = _collect(files, domain)
    leaked = {h for h in leaked if not _own(h, domain)}
    rx = _mention_rx(leaked)
    if rx:
        seen = {(i["path"], i["line"]) for i in issues}
        for path in sorted(files):
            if not _scanned(path):
                continue
            text = files[path]
            for m in rx.finditer(text):
                key = (path, _line(text, m.start()))
                if key in seen:
                    continue
                seen.add(key)
                issues.append({"path": path, "line": key[1], "severity": "error",
                               "message": f"згадка {m.group(0)} — "
                                          f"домен вітки {domain}"})
    return sorted(issues, key=lambda i: (i["path"], i["line"]))


def _rewrite(text: str, domain: str, rx: re.Pattern | None) -> str:
    spans = _protected(text)

    def sub_email(m):
        if _inside(spans, m.start()):
            return m.group(0)
        local, host = m.group(0).split("@", 1)
        if _own(host, domain) or (not BRACE_RX.fullmatch(host) and _skip_host(host)):
            return m.group(0)
        return f"{local}@{domain}"

    out = EMAIL_RX.sub(sub_email, text)

    def sub_self(m):
        for key, host in m.groupdict().items():
            if host and not _own(host, domain):
                s, e = m.span(key)
                return m.group(0)[:s - m.start()] + domain + m.group(0)[e - m.start():]
        return m.group(0)

    out = SELF_URL_RX.sub(sub_self, out)

    def sub_brace_url(m):
        if _inside(prot_url, m.start()):
            return m.group(0)
        s, e = m.span("host")
        return m.group(0)[:s - m.start()] + domain + m.group(0)[e - m.start():]

    prot_url = _protected(out)
    out = URL_BRACE_RX.sub(sub_brace_url, out)
    if rx:
        prot = _protected(out)
        out = rx.sub(lambda m: m.group(0) if _inside(prot, m.start()) else domain, out)
    return out


def fix_branch(files, all_paths, branch):
    domain = _domain_for(branch)
    if not domain:
        return []
    _, leaked = _collect(files, domain)
    rx = _mention_rx({h for h in leaked if not _own(h, domain)})
    actions = []
    for path in sorted(files):
        if not _scanned(path):
            continue
        new = _rewrite(files[path], domain, rx)
        if new != files[path]:
            actions.append({"type": "edit", "path": path, "content": new})
    return actions
