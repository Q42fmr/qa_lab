"""Дефолт return page в inject-скрипті має вказувати на СПРАВЖНЮ сторінку подяки.

Vue-вайт збирається у статику скриптом `scripts/inject-php.cjs`, який вшиває
у `dist/index.php` php-преамбулу:

    $returnPage = $_ENV['WHITE_FORM_RETURN_PAGE'] ?? 'thank-you';
    if (!str_ends_with($returnPage, '.html')) { $returnPage .= '.html'; }

Цей дефолт — те, куди піде відвідувач після сабміту форми, якщо змінної в
`.env` немає. У генераторі він захардкоджений як `thank-you`, а сторінку
подяки локалізують: у корпусі це `/obrigado` (135 віток) і `/confirmacao`
(80) — жодного `thank-you` немає НІ В ОДНІЙ з 215 віток з inject-скриптом.
Тобто дефолтний редірект веде у 404 скрізь.

Джерело правди — роутер вітки (`src/router/index.js`), а не назва файлу:
компонент зветься `Thanks.vue` в усіх вітках, а URL у кожної свій.

    { path: '/obrigado', name: 'thanks', component: () => import('@/pages/Thanks.vue') }

Роут подяки впізнається за трьома незалежними ознаками, будь-якої досить:
  * `name` — канонічний id (`thanks`/`success`/`confirmation`) або локальна
    назва зі словника (`Obrigado`, `Дякуємо`, `Danke`, …);
  * компонент — файл `Thanks.vue`/`Success.vue`/`Confirmation.vue`;
  * сам `path` — слаг зі словника локалізацій (`obrigado`, `danke`, `merci`, …).

Словник узятий з конфігу генератора сторінок (33 локалі): і слаги (те, що
стоїть в URL), і видимі назви — бо в роутері трапляється і те, і те.

Автофікс міняє РІВНО дефолт у inject-скрипті на слаг з роутера; сам роутер і
сторінку не чіпає — вони джерело правди, а не помилка.
"""
import re
import unicodedata

import checks.form_stub as _form_stub

NAME = "Return page ↔ сторінка подяки"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["node"]
DESCRIPTION = ("Дефолт $returnPage у scripts/inject-php.cjs має збігатися зі "
               "слагом сторінки подяки з роутера вітки. Генератор хардкодить "
               "'thank-you', а сторінку локалізують ('obrigado', 'confirmacao') "
               "— редірект після форми веде у 404. Автофікс підставляє слаг.")
FILES = ["*inject-php.cjs", "*router/index.js", "*router/index.ts",
         "*router.js", "*router.ts"]

# $returnPage = $_ENV['WHITE_FORM_RETURN_PAGE'] ?? 'thank-you';
RETURN_RX = re.compile(
    r"""(WHITE_FORM_RETURN_PAGE['"]\s*\]\s*\?\?\s*)(['"])([^'"]*)\2""")
# один запис роуту: {...path: '/x'...}. Вкладених дужок у записі немає —
# component: () => import('...') дужок у ФІГУРНОМУ сенсі не додає.
ROUTE_RX = re.compile(r"\{[^{}]*?\bpath\s*:\s*['\"]([^'\"]*)['\"][^{}]*?\}", re.S)
ROUTE_NAME_RX = re.compile(r"\bname\s*:\s*['\"]([^'\"]*)['\"]")
ROUTE_COMP_RX = re.compile(r"""import\(\s*['"]([^'"]+)['"]\s*\)""")

# Канонічні id сторінки подяки (поле "names" у конфігу генератора).
CANON = ("thanks", "success", "confirmation", "thank-you", "thankyou")

# Локалізації: слаги (в URL) і видимі назви — з конфігу генератора, 33 локалі.
LOCALE_WORDS = (
    "merci", "confirmation", "Merci", "Confirmation",
    "danke", "bestaetigung", "Danke", "Bestätigung",
    "gracias", "confirmacion", "Gracias", "Confirmación",
    "shukran", "taqdir", "شكراً", "تأكيد",
    "arigatou", "kanryou", "ありがとうございます", "送信完了",
    "dziekujemy", "potwierdzenie", "Dziękujemy", "Potwierdzenie",
    "hvala", "potvrda", "Hvala", "Potvrda",
    "obrigado", "confirmacao", "Obrigado", "Confirmação",
    "grazie", "conferma", "Grazie", "Conferma",
    "bedankt", "bevestiging", "Bedankt", "Bevestiging",
    "spasibo", "podtverzhdenie", "Спасибо", "Подтверждение",
    "dyakuyemo", "pidtverdzhennya", "Дякуємо", "Підтвердження",
    "blagodarim", "potvarzhdenie", "Благодарим", "Потвърждение",
    "Хвала", "Потврда",
    "dekujeme", "potvrzeni", "Děkujeme", "Potvrzení",
    "multumim", "confirmare", "Mulțumim", "Confirmare",
    "koszonjuk", "visszaigazolas", "Köszönjük", "Visszaigazolás",
    "tack", "bekraftelse", "Tack", "Bekräftelse",
    "takk", "bekreftelse", "Takk", "Bekreftelse",
    "tak", "bekraeftelse", "Tak", "Bekræftelse",
    "kiitos", "vahvistus", "Kiitos", "Vahvistus",
    "efcharistoume", "epivevaiosi", "Ευχαριστούμε", "Επιβεβαίωση",
    "tesekkurler", "onay", "Teşekkürler", "Onay",
    "toda", "ishur", "תודה", "אישור",
    "moteshakerim", "tayid", "متشکریم", "تایید",
    "shukriya", "tasdeeq", "شکریہ", "تصدیق",
    "dhanyavad", "pushti", "धन्यवाद", "पुष्टि",
    "khopkhun", "yuenyan", "ขอบคุณ", "ยืนยัน",
    "cam-on", "xac-nhan", "Cảm ơn", "Xác nhận",
    "terima-kasih", "konfirmasi", "Terima Kasih", "Konfirmasi",
    "gamsahamnida", "hwagin", "감사합니다", "확인",
    "ganxie", "queren", "感谢", "确认",
)


def _norm(s: str) -> str:
    """Порівняння без діакритики, регістру й розділювачів: «Confirmação» і
    «confirmacao» — те саме слово, «Terima Kasih» і «terima-kasih» теж."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.casefold() if c.isalnum())


VOCAB = {_norm(w) for w in CANON + LOCALE_WORDS if _norm(w)}


def _inject_path(files: dict) -> str | None:
    return next((p for p in sorted(files) if p.endswith("inject-php.cjs")), None)


def _router_paths(files: dict) -> list[str]:
    return [p for p in sorted(files) if not p.endswith("inject-php.cjs")]


def _thanks_slug(text: str) -> str | None:
    """Слаг роуту сторінки подяки або None."""
    for m in ROUTE_RX.finditer(text):
        block, path = m.group(0), m.group(1)
        nm = ROUTE_NAME_RX.search(block)
        comp = ROUTE_COMP_RX.search(block)
        stem = comp.group(1).rsplit("/", 1)[-1].split(".")[0] if comp else ""
        if (_norm(path.strip("/")) in VOCAB
                or (nm and _norm(nm.group(1)) in VOCAB)
                or (stem and _norm(stem) in VOCAB)):
            return path.strip("/")
    return None


def _default_return(text: str) -> tuple[str, int] | None:
    m = RETURN_RX.search(text)
    if not m:
        return None
    return m.group(3), text.count("\n", 0, m.start(3)) + 1


def run_branch(files, all_paths, branch: str = ""):
    if any(_form_stub.is_stubbed(t) for p, t in files.items() if p.lower() in ("index.php", "index.html")):
        return []                       # форма-заглушка (form_stub): штатний флоу вимкнено свідомо
    inject = _inject_path(files)
    if not inject:
        return []                       # не той стек — нема що судити
    got = _default_return(files[inject])
    if not got:
        return []                       # inject без дефолту — не наша справа
    current, line = got
    issues = []

    slug = next((s for s in (_thanks_slug(files[p]) for p in _router_paths(files))
                 if s), None)
    if slug is None:
        issues.append({"path": inject, "line": line, "severity": "error",
                       "message": ("у роутері вітки немає сторінки подяки — "
                                   f"дефолт '{current}' вести нікуди")})
    elif _norm(current) != _norm(slug):
        issues.append({"path": inject, "line": line, "severity": "error",
                       "message": (f"дефолт return page '{current}' ≠ сторінка "
                                   f"подяки вітки '{slug}' — після сабміту форми "
                                   f"буде 404; фікс підставить '{slug}'")})
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    if any(_form_stub.is_stubbed(t) for p, t in files.items() if p.lower() in ("index.php", "index.html")):
        return []                       # форма-заглушка (form_stub)
    inject = _inject_path(files)
    if not inject:
        return []
    got = _default_return(files[inject])
    if not got:
        return []
    current, _line = got
    text = files[inject]

    new = text

    slug = next((s for s in (_thanks_slug(files[p]) for p in _router_paths(files))
                 if s), None)
    if slug is not None and _norm(current) != _norm(slug):
        # без count: якщо преамбула у файлі продубльована, обидва дефолти
        # мусять поїхати разом — інакше фікс лишив би половину вітки з 404
        new = RETURN_RX.sub(lambda m: m.group(1) + m.group(2) + slug + m.group(2),
                            new)
    if new == text:
        return []
    return [{"type": "edit", "path": inject, "content": new}]
