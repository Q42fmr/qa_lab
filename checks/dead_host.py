"""Лінки на зарезервований (нерезолвний) хост: `*.example`, `*.invalid`,
`*.test`, `*.localhost`.

RFC 2606 / RFC 6761 резервують ці зони спеціально під приклади й тести —
жоден реєстратор ніколи не видасть у них справжній домен, тож такий хост
гарантовано мертвий, а не «можливо мертвий», як зовнішні лінки в
`external_links.py` (там HEAD-запит може впасти й тимчасово, і check GROUP=review,
без автофіксу — саме тому дублювати його чек не наша справа).

Заміряно на живих вітках:

    bralobmgeon.com.br: банер кукі, ОДИН href на всіх 46 сторінках -
        `https://bralobmgeon-neu.example/store-policy` (index.html:2098).
        Теки `store-policy/` у вітці немає, зате є згенерована лабою
        `privacy.html` у корені - саме туди й веде фікс.
    i2jlibitiec.com.br: 2 лінки в ТІЛІ ТЕКСТУ (не про політику приватності) -
        `parceria-spotify-e-botafogo/index.html:317` і
        `parceria-spotify-e-sao-paulo/index.html:321`, обидва на
        `i2producoes-neu.example/parceria-...` - сторінку оригінального
        сайту, якої в цій вітці НІКОЛИ не було.

Тобто «мертвий лінк на .example» - два різних дефекти, і фікс різний:

    - лінк веде на політику приватності (за ключовими словами в URL) -
      підставляємо наявну `privacy.html` у корені вітки з ГЛИБИНОЮ, виведеною
      з `path`: для `index.html` це `privacy.html`, для `a/b/index.html` -
      `../privacy.html`. Жорстко зашитий `../` ламав би 40 із 46 сторінок
      bralobmgeon (розподіл глибин 1×0, 5×1, 11×2, 29×3).
    - лінк веде кудись-інде (як у i2jlibitiec) - вгадувати ціль не наша
      справа (див. `link_target.py`: «підставляти інший файл означало б
      гадати»), тож розгортаємо `<a>` у його ж текст: мертвий лінк гірший за
      звичайний текст, а зміст фрази лишається читабельним.

Чому не існуючий чек. `link_target.py` свідомо пропускає такі href - вони
абсолютні (`http:`/`https:` у SKIP_PREFIX), і індекс файлів вітки тут
непричетний: хоста в природі не існує, файла шукати нема де. `domain_match.py`
лагодить лише САМОПОСИЛЬНІ позиції (canonical/og:url/siteUrl/email/sitemap) на
ДОМЕН, ПІДВʼЯЗАНИЙ ДО ВІТКИ В CLICKUP - тут інша сторона: лінк веде НА ЧУЖИЙ
резервний хост, підвʼязаного домену для порівняння немає. `external_links.py`
теж не власник: він мережевий (`GROUP = "review"`, ручна HEAD-перевірка, без
`fix`), а `.example` мертвий детерміновано й без єдиного HTTP-запиту.

Що НЕ займаємо. `canonical`/`og:url` на резервний хост власного бренду вітки
(13 сторінок i2jlibitiec) - це `<link>`/`<meta>`, а не `<a href>`, і їхній
власник - механізм підвʼязки домену вітки (`domain_match.py`), не цей чек.
`placeholder="…@example.com"` і приклад-текст на кшталт «email@example.com» в
абзаці - не URL і сюди не потрапляють: чек ловить лише REAL href усередині
`<a>`.
"""
import posixpath
import re
from urllib.parse import urlsplit

NAME = "Лінк на зарезервований хост (.example/.invalid/.test/.localhost)"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"links"}
PROJECTS = ["php"]
DESCRIPTION = ("<a href> веде на хост у зоні, зарезервованій RFC 2606/6761 під "
               "приклади (example/invalid/test/localhost) - такий домен ніколи не "
               "резолвиться. Лінк на політику приватності автофікс веде на наявну "
               "privacy.html у корені вітки (з правильною глибиною ../); будь-який "
               "інший лінк розгортає у власний текст, бо ціль не наша справа гадати.")
FILES = ["*.html", "*.htm", "*.php"]

RESERVED_TLD = ("example", "invalid", "test", "localhost")

A_RX = re.compile(
    r"""<a\b(?P<attrs>(?:[^>"']|"[^"]*"|'[^']*')*?\bhref\s*=\s*(?P<q>["'])"""
    r"""(?P<url>https?://[^"']+)(?P=q)(?:[^>"']|"[^"]*"|'[^']*')*)>"""
    r"""(?P<inner>.*?)</a\s*>""",
    re.I | re.S)

# ключові слова політики приватності/кукі/умов у самому URL - інакше не
# вгадати, куди мав вести лінк, і чіпати ціль не наша справа. `datenschutz` і
# `agb` тут бо корпус німецькомовний: без них `selzeavbsozom.ch` віддавав
# юридичні лінки у гілку «ціль невідома» і вони розгорталися в текст.
POLICY_RX = re.compile(
    r"privac|priva[cç]idade|pol[ií]tica|policy|cookie|termos|terms|legal"
    r"|datenschutz|\bagb\b", re.I)
IMPRESSUM_RX = re.compile(r"impressum|imprint", re.I)
CONTACT_RX = re.compile(r"contact|kontakt|contato", re.I)

PRIVACY_FILE = "privacy.html"
IMPRESSUM_FILE = "impressum.html"
CONTACT_FILE = "contact.html"
HOME_FILE = "index.html"

# Хост, який вайт називає СВОЇМ. Скрейпер підміняє домен оригіналу на
# нерезолвний `<бренд>-neu.example`, і тоді ВСЯ внутрішня навігація стає
# «лінками на мертвий хост» - хоча це не сторонній сайт, а сам вайт.
# Розгортати їх у текст (гілка «ціль невідома») означало б знищити меню: у
# `selzeavbsozom.ch` це 49 лінків, з них 12 - випадайне меню напрямків.
#
# Самопосилання впізнається без жодної евристики за іменем: власний
# `<link rel="canonical">` сторінки і означає «цей хост - я». Немає canonical -
# лишається давня поведінка, тобто нічого не ламається.
CANONICAL_RX = re.compile(
    r"""<link\b[^>]*\brel\s*=\s*["']canonical["'][^>]*\bhref\s*=\s*["']([^"']+)["']""",
    re.I)


def _host(url: str) -> str | None:
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def _is_reserved(host: str | None) -> bool:
    if not host:
        return False
    return host.rsplit(".", 1)[-1].lower() in RESERVED_TLD


def _matches(text: str):
    """Матчі <a href="..."> на зарезервований хост."""
    for m in A_RX.finditer(text):
        if _is_reserved(_host(m.group("url"))):
            yield m


def _self_host(text: str) -> str | None:
    """Хост, який сторінка називає своїм (з власного canonical)."""
    m = CANONICAL_RX.search(text)
    return _host(m.group(1)) if m else None


def _local_target(url: str) -> str:
    """Локальна сторінка, на яку має вести САМОПОСИЛАННЯ. Вгадування тут нема:
    ключове слово в шляху вибирає одну з чотирьох сторінок, які лаба генерує в
    корені кожної вітки; усе інше веде на головну, бо цільової сторінки у вайті
    просто не існує (у `selzeavbsozom.ch` це 34 різні шляхи оригіналу проти
    чотирьох реальних файлів)."""
    if IMPRESSUM_RX.search(url):
        return IMPRESSUM_FILE
    if POLICY_RX.search(url):
        return PRIVACY_FILE
    if CONTACT_RX.search(url):
        return CONTACT_FILE
    return HOME_FILE


def _rel(path: str, target: str) -> str:
    """Шлях до файла в корені вітки, з глибиною за `path`."""
    d = posixpath.dirname(path.replace("\\", "/"))
    depth = 0 if not d else d.count("/") + 1
    return "../" * depth + target


def run(path, text):
    issues = []
    mine = _self_host(text)
    for m in _matches(text):
        url = m.group("url")
        line = text.count("\n", 0, m.start()) + 1
        if mine and _host(url) == mine:
            kind = "самопосилання"
            what = f"вайт посилається на себе через мертвий хост, ціль → {_local_target(url)}"
        elif POLICY_RX.search(url):
            kind = "політику приватності"
            what = f"ціль → {PRIVACY_FILE}"
        else:
            kind = "стороннє"
            what = "ціль невідома, лінк розгорнеться у власний текст"
        issues.append({
            "line": line,
            "severity": "error",
            "message": f"лінк на зарезервований хост ({kind}): {url} — {what}",
        })
    return issues


def fix(path, text):
    matches = list(_matches(text))
    if not matches:
        return text
    mine = _self_host(text)
    out = []
    pos = 0
    for m in matches:
        url = m.group("url")
        out.append(text[pos:m.start()])
        target = None
        if mine and _host(url) == mine:
            target = _local_target(url)      # внутрішня навігація вайта
        elif POLICY_RX.search(url):
            target = PRIVACY_FILE
        if target:
            # той самий тег, лише href замінено на локальний файл
            new_attrs = m.group("attrs").replace(url, _rel(path, target), 1)
            out.append(f"<a{new_attrs}>{m.group('inner')}</a>")
        else:
            # ціль невідома - мертвий лінк гірший за звичайний текст
            out.append(m.group("inner"))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)
