"""Email вайта: домен мусить бути літералом {{DOMAIN}}, а не реальним.

Навіщо. Домен підставляється при деплої, тож у файлах має стояти плейсхолдер.
Захардкоджений реальний домен — це витік бренду в чужий вайт: у ceepohj-motc-my-en
сім правильних info@{{DOMAIN}}, а в privacy-policy.html лишилось
info@ceopapltizb.com.my (і в mailto, і у видимому тексті).

Автофікс міняє ЛИШЕ частину після @, локальну частину лишає як є:
info@ceopapltizb.com.my -> info@{{DOMAIN}}, privacy@acme.io -> privacy@{{DOMAIN}}.

Три речі свідомо не чіпаємо (виміряно на 150 вітках, 1394 файли):
  * placeholder="…" — усі 147 не-літеральних пошт корпусу сидять саме там і всі
    прикладові (ihre@email.ch, su@correo.com, your@email.com, example@company.ae),
    причому у справних вайтах. Це підказка «як виглядає ТВОЯ пошта», не контакт;
    заміна зробила б з неї домен сайту і зламала сенс форми.
  * {{DOMAIN_NAME}} — це вже літерал, і ним володіє окремий чек wrong_literal:
    у хедері/футері/лого він легітимний (бренд-нейм), а в хост-контексті
    (info@{{DOMAIN_NAME}}) той чек сам його виправляє — хост б'є виняток
    хедера/футера. Два чеки на одному тексті заважали б один одному, тож
    тут ми на будь-який {{…}} після @ просто мовчимо.
  * асети з @ у назві (hero@2x.png, logo@2x.jpg) — формально проходять як пошта,
    бо 'png' виглядає як TLD.
"""
import re

NAME = "Email: домен мусить бути {{DOMAIN}}"
# 12 спрацювань на 150 вітках — усі реальні (витік бренду в privacy-policy);
# 147 прикладових пошт у placeholder свідомо не чіпаються
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"email"}
PROJECTS = ["php"]
DESCRIPTION = ("Частина після @ мусить бути літералом {{DOMAIN}} — реальний домен у "
               "пошті це витік бренду. Автофікс міняє домен, локальну частину лишає. "
               "Не чіпає: приклади в placeholder=, зарезервовані example.com/.test "
               "(RFC 2606), літерал {{DOMAIN_NAME}} (це wrong_literal), логін@хост "
               "усередині URL (Sentry DSN) і асети з @ у назві.")
# Vue-вітки цей чек більше не бачить: там пошта мусить бути не літералом
# {{DOMAIN}}, а справжнім доменом вітки — це окремий чек domain_match.
FILES = ["*.html", "*.php", "*.js"]
# js судиться окремо (run_branch/fix_branch): деплой підставляє {{DOMAIN}}
# лише в html/php, а «polish»-скрипти малюють контакти в рантаймі
# (754/1027 br-pt 27.10: contato.loja@gmail.com у polish.js) — туди йде
# реальний домен вітки з ClickUp (domains.active_for), як уже зроблено руками
# на cagu-alejfaq/cluakoje. Вендорні/мініфіковані js — не наші.
JS_SKIP_RX = re.compile(r"(?:^|/)(?:_ext|vendor|node_modules|wp-includes|wp-content/plugins)/|\.min\.js$|jquery|bootstrap|swiper|slick|gsap|lenis", re.I)

LITERAL = "{{DOMAIN}}"

EMAIL_RX = re.compile(
    r"[A-Za-z0-9._%+\-]+@(?:\{\{[A-Za-z0-9_]+\}\}|[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
# placeholder з будь-якими лапками — приклад пошти, а не контакт. Форми дві:
# HTML-атрибут `placeholder="ihre@email.ch"` і властивість обʼєкта у TS-контенті
# `placeholder: "deine@e-mail.ch"` — та сама сутність, інший синтаксис. Друга
# форма дає 44 приклади на node-корпусі, і без неї автофікс переписав би
# підказку у полі вводу на «твоя@{{DOMAIN}}».
#
# Але приклад — це САМЕ АДРЕСА, а не текст із адресою. Генератор інколи
# запихає у placeholder ціле речення разом із реальним контактом:
# `placeholder="Bei Fragen erreichen Sie uns unter info@SkiVenture…@support.com."`
# (bupvfiz-rectem-ch-de) — і виняток мовчки ковтав витік. На 1200 вітках усі
# 1042 законні приклади — чисті адреси, речень немає жодного, тож поріг
# у кілька слів розділяє їх без фолсів.
PLACEHOLDER_RX = re.compile(
    r"""placeholder\s*[=:]\s*(?:"([^"]*)"|'([^']*)'|`([^`]*)`)""", re.I)
PLACEHOLDER_MAX_WORDS = 3
# 'домени', що насправді є файлами: hero@2x.png, logo@2x.jpg
ASSET_TLD = ("png", "jpg", "jpeg", "webp", "svg", "gif", "ico", "avif", "bmp",
             "css", "js", "json", "html", "htm", "php", "xml", "txt",
             "woff", "woff2", "ttf", "eot", "mp4", "webm", "pdf", "zip")
# @ усередині URL — це authority (логін@хост), а не пошта. Реальний кейс:
# Sentry DSN "https:\/\/<ключ>@o186239.ingest.sentry.io\/1281569" у ifipor-br-pt —
# заміна хоста зламала б збір помилок. Слеші бувають екранованими (JSON).
#
# Виняток мусить бути ВУЗЬКИМ: у корпусі трапляється
# `<meta content="https://PensionEaseResolutionService@support.com/og_image.png">`
# — назва вайта в позиції логіна, тобто той самий витік бренду, і правило його
# ковтало. На 1200 вітках воно пропустило 14 збігів, і ВСІ 14 були цим
# дефектом; жодного справжнього DSN. Розрізняє їх сам логін: ключ завжди має
# цифри (`5552835e822c4c8db5070306b2535ef3`), а бренд — це чисте слово
# (`PensionEaseResolutionService`). Тож логін-слово судимо як пошту, а все
# інше (ключі, токени, шляхи) лишається пропущеним.
URL_AUTHORITY_RX = re.compile(r"(?:\\?/){2}$")
BRAND_USER_RX = re.compile(r"^[A-Za-z]{8,}$")
# RFC 2606: зарезервовані під приклади й тести, реальним брендом бути не можуть
RESERVED_DOMAINS = ("example.com", "example.net", "example.org", "example.edu", "domain.com", "email.com")
RESERVED_TLD = ("example", "test", "invalid", "localhost")


def _domain(email: str) -> str:
    return email.split("@", 1)[1]


def _skip(email: str) -> bool:
    dom = _domain(email).lower()
    if dom.startswith("{{"):
        return True                      # уже літерал (в т.ч. {{DOMAIN_NAME}})
    if dom in RESERVED_DOMAINS or dom.rsplit(".", 1)[-1] in RESERVED_TLD:
        return True                      # приклад за стандартом, не витік
    return dom.rsplit(".", 1)[-1] in ASSET_TLD


def _example_spans(text: str) -> list[tuple[int, int]]:
    """Ділянки placeholder-ів, які СПРАВДІ є прикладом адреси.

    Речення з живим контактом усередині placeholder прикладом не є —
    інакше виняток ковтає витік бренду."""
    out = []
    for m in PLACEHOLDER_RX.finditer(text):
        val = next((g for g in m.groups() if g is not None), "")
        if len(val.split()) <= PLACEHOLDER_MAX_WORDS:
            out.append(m.span())
    return out


def _bad_matches(text: str):
    """Пошти, домен яких треба замінити (спільне для run і fix)."""
    skip_spans = _example_spans(text)
    for m in EMAIL_RX.finditer(text):
        if _skip(m.group(0)):
            continue
        if any(a <= m.start() < b for a, b in skip_spans):
            continue                     # приклад у placeholder
        if (URL_AUTHORITY_RX.search(text[:m.start()])
                and not BRAND_USER_RX.match(m.group(0).split("@", 1)[0])):
            continue                     # ключ@хост у URL (Sentry DSN), не пошта
        yield m



def _domain_hint(email: str) -> str:
    return email.split("@", 1)[0] + "@" + LITERAL


def fix(path, text):
    """Домен після @ -> {{DOMAIN}}; локальна частина, placeholder і літерали цілі.
    js — у fix_branch (реальний домен вітки)."""
    if _is_js(path):
        return text
    out, last = [], 0
    for m in _bad_matches(text):
        out.append(text[last:m.start()])
        out.append(_domain_hint(m.group(0)))
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def _domain_for(branch: str):
    try:
        import domains
        return domains.active_for(branch)
    except Exception:
        return None


def _is_js(path: str) -> bool:
    return path.lower().endswith(".js")


def _js_files(files: dict) -> dict:
    return {p: t for p, t in files.items() if _is_js(p) and not JS_SKIP_RX.search(p)}


def run(path, text):
    if _is_js(path):
        return []                             # js — у run_branch, з доменом вітки
    issues = []
    for m in _bad_matches(text):
        issues.append({
            "line": text.count("\n", 0, m.start()) + 1,
            "severity": "error",
            "message": f"реальний домен у пошті: {m.group(0)} — "
                       f"має бути {_domain_hint(m.group(0))} (є автофікс)",
        })
    return issues


def run_branch(files, all_paths, branch: str = ""):
    dom = _domain_for(branch)
    issues = []
    for p, text in sorted(_js_files(files).items()):
        for m in _bad_matches(text):
            email = m.group(0)
            if dom and _domain(email).lower() == dom.lower():
                continue
            local = email.split("@", 1)[0]
            if dom:
                msg = f"реальний чужий домен у пошті в js: {email} — має бути {local}@{dom} (домен вітки з ClickUp; є автофікс)"
            else:
                msg = f"чужий домен у пошті в js: {email} — вітці не підв'язано домен (імпортуй таску з ClickUp), заміни вручну"
            issues.append({"path": p, "line": text.count("\n", 0, m.start()) + 1,
                           "severity": "error", "message": msg})
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    dom = _domain_for(branch)
    if not dom:
        return []
    actions = []
    for p, text in sorted(_js_files(files).items()):
        out, last = [], 0
        for m in _bad_matches(text):
            email = m.group(0)
            if _domain(email).lower() == dom.lower():
                continue
            out.append(text[last:m.start()])
            out.append(email.split("@", 1)[0] + "@" + dom)
            last = m.end()
        out.append(text[last:])
        new = "".join(out)
        if new != text:
            actions.append({"type": "edit", "path": p, "content": new})
    return actions
