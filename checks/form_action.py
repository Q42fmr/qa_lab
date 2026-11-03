"""Форма-сателіт: сабміт не доходить до index.php.

Кейс — п'ять віток (`mezegabe-br-pt`, `orpuglu-stazoa-br-pt`,
`palallitu-br-pt`, `peluzaj-nolv-br-pt`, `quibtemo-br-pt`), по 8 сторінок у
кожній. У кожній рівно дві форми, обидві БЕЗ `action`:

  * в `index.php` — і це ПРАВИЛЬНО: форма без `action` відправляється на саму
    себе, тобто в той самий файл, де стоїть php-блок ловлі ліда. Саме тому чек
    `forms` (`FILES = ["index.php"]`) атрибути `action`/`method` там знімає;
  * на `contato.html` — і це поломка: сабміт іде в статичний html, php там
    немає, лід зникає без пікселя й без редіректу на подяку.

Блок ловлі ліда (`cache/mezegabe-br-pt/index.php:578`) читає рівно чотири поля
з `$_GET` — `email`, `name`, `phone`, `lastname` — спрацьовує на наявності
`email` АБО `name`, стріляє fb/gtag/bing і робить
`window.location.href = '/$returnPage'` з `exit()`. Форма відправляється GET,
бо `method` відсутній; тому чек `method` НІКОЛИ не додає.

Фікс дописує `action="./"`: сабміт іде в корінь теки сторінки, сервер віддає
`index.php`, блок ловить `$_GET`.

Друга поломка того ж корпусу: у `orpuglu-stazoa-br-pt` і `peluzaj-nolv-br-pt`
поля названі португальською (`nome`, `sobrenome`, `telefone`, `mensagem`,
`assunto`), тож блок бачить лише `email`, а `fn` у пікселі приїде порожнім.
Вирівнюємо РІВНО два поля, і імена беремо з еталона — форми в `index.php`
ТОГО САМОГО вайта, по `type` поля (замір по всіх 10 формах корпусу: `type`
розводить поля однозначно):

  * `type=email` -> ім'я email-поля еталона (у корпусі вже `email` усюди);
  * перше `type=text` -> ім'я текстового поля еталона (`nome` -> `name`).

`phone` і `lastname` поза скоупом свідомо. Телефон не доходить до пікселя в
ЖОДНОМУ вайті незалежно від імені поля: у шаблоні стоїть
`ltrim('+', $_GET['phone'] ?? '')`, а підпис PHP — `ltrim(string, characters)`,
тобто аргументи переставлені й функція обрізає символи телефону з рядка `'+'`.
`lastname` індекс-форма не містить у жодній із п'яти віток, тож еталон імені не
дає — а вигадати його означало б зламати головну властивість: перейменувати
можна лише в те ім'я, яке ВЖЕ вживає робоча індекс-форма цього ж вайта.

Еталон для сторінки — `index.php` у ТІЙ САМІЙ теці, бо `action="./"`
резолвиться саме в теку сторінки.
"""
import os
import re

import checks.form_stub as _form_stub

NAME = "Форма-сателіт: сабміт не доходить до index.php"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Форма на сторінці-сателіті без action відправляється на "
               "статичний html, а php-блок ловлі ліда живе лише в index.php — "
               "лід зникає. Автофікс дописує action=\"./\" і вирівнює два поля, "
               "які читає блок (email і перше текстове), за іменами з "
               "індекс-форми того ж вайта.")
FILES = ["*.html", "*.htm", "*.php"]

INDEX = "index.php"
PAGE_EXT = (".html", ".htm", ".php")

FORM_RX = re.compile(r"<form\b[\s\S]*?</form\s*>", re.I)
FORM_TAG_RX = re.compile(r"<form\b([^>]*)>", re.I)
ACTION_RX = re.compile(r"\baction\s*=", re.I)
ATTR_RX = re.compile(r"\b(?:action|method)\s*=", re.I)
FIELD_RX = re.compile(r"<(input|textarea|select)\b([^>]*)>", re.I)
NAME_ATTR_RX = re.compile(
    r"""\bname\s*=\s*(?P<q>["'])(?P<val>[^"']*)(?P=q)""", re.I)
TYPE_ATTR_RX = re.compile(r"""\btype\s*=\s*["']([^"']+)["']""", re.I)
# php-блок ловлі ліда: саме та умова, на якій він спрацьовує
LEAD_RX = re.compile(
    r"""isset\s*\(\s*\$_GET\s*\[\s*['"]email['"]\s*\]\s*\)\s*(?:\|\||&&)"""
    r"""\s*isset\s*\(\s*\$_GET\s*\[\s*['"]name['"]\s*\]\s*\)""")
# js, який володіє сабмітом: атрибут додавати марно
JS_SUBMIT_RX = re.compile(
    r"""addEventListener\s*\(\s*['"]submit['"]|\bonsubmit\s*=|preventDefault\s*\(""",
    re.I)
# два типи, які вирівнюємо (див. докстрінг)
ALIGNED = ("email", "text")
# імена, які php-блок читає сам (докстрінг) — позиційне правило їх не чіпає
BLOCK_FIELDS = ("email", "name", "phone", "lastname")


def _tag(form: str) -> str:
    """Атрибути відкриваючого <form …>."""
    m = FORM_TAG_RX.search(form)
    return m.group(1) if m else ""


def _fields(form: str) -> list[tuple[str, str]]:
    """`[(type, name)]` у порядку появи. Для textarea/select тип — сам тег."""
    out = []
    for tag, attrs in FIELD_RX.findall(form):
        nm = NAME_ATTR_RX.search(attrs)
        if not nm:
            continue
        ty = TYPE_ATTR_RX.search(attrs)
        out.append(((ty.group(1) if ty else tag).lower(), nm.group("val")))
    return out


def _canon(form: str) -> dict[str, str]:
    """Еталонні імена: `{"email": …, "text": …}` — перше поле кожного типу."""
    out: dict[str, str] = {}
    for ty, nm in _fields(form):
        if ty in ALIGNED and ty not in out:
            out[ty] = nm
    return out


def _index_state(itext: str):
    """`(форма, канон, є_php_блок, форма_стандартна)` для тексту index.php."""
    if not itext:
        return None, {}, False, False
    lead = bool(LEAD_RX.search(itext))
    # еталон — ПЕРША форма з обома полями, які вирівнюємо: у корпусі над
    # контактною формою часто стоїть пошук (`<input type="text" name="q">`,
    # без email) або підписка на новини (лише email, без текстового поля) —
    # жоден із них не годиться як джерело правди для ОБОХ полів.
    for m in FORM_RX.finditer(itext):
        form = m.group(0)
        canon = _canon(form)
        if "email" in canon and "text" in canon:
            return form, canon, lead, not ATTR_RX.search(_tag(form))
    return None, {}, lead, False


def _index_for(page: str) -> str:
    """Еталон сторінки — index.php у ТІЙ САМІЙ теці (`action="./"`)."""
    d = os.path.dirname(page)
    return f"{d}/{INDEX}" if d else INDEX


def _targets(files: dict) -> dict[str, list[tuple[int, str]]]:
    """`{сторінка: [(рядок, форма)]}` — форми без `action` поза index.php."""
    out: dict[str, list[tuple[int, str]]] = {}
    for path, text in files.items():
        low = path.lower()
        if not low.endswith(PAGE_EXT) or os.path.basename(low) == INDEX:
            continue
        bad = [(text[:m.start()].count("\n") + 1, m.group(0))
               for m in FORM_RX.finditer(text)
               if not ACTION_RX.search(_tag(m.group(0)))
               and _canon(m.group(0)).keys() >= set(ALIGNED)]
        if bad:
            out[path] = bad
    return dict(sorted(out.items()))


def _verdict(files: dict, page: str):
    """`(severity, повідомлення, канон)` для сторінки. `severity=None` — тиша.

    Порядок перевірок той самий, що у `fix_branch`: спершу наявність еталона,
    далі G1, G2, G3. Кожна умова окремо блокує автофікс.
    """
    itext = files.get(_index_for(page))
    if itext is None:
        return None, "", {}                 # немає індексу — сабміту нікуди йти
    _, canon, lead, std = _index_state(itext)
    if not lead:
        return ("warn", "форма без action, але й php-блока ловлі ліда на "
                        "індексі немає — сабміт нікуди не веде", {})
    if not std:
        return ("warn", "форма без action, а індекс-форма не стандартна (має "
                        "action/method або її немає) — еталон ненадійний, "
                        "правити руками", {})
    if JS_SUBMIT_RX.search(files.get(page, "")):
        return ("warn", "форма без action, але сабміт перехоплює js — атрибут "
                        "його не полагодить", {})
    return ("error", "форма без action: сабміт іде в статичний html, лід не "
                     "доходить до php-блока в index.php (є автофікс)", canon)


def run_branch(files, all_paths, branch: str = ""):
    if any(_form_stub.is_stubbed(t) for p, t in files.items() if p.lower() in ("index.php", "index.html")):
        return []                       # форма-заглушка (form_stub): штатний флоу вимкнено свідомо
    issues = []
    for page, forms in _targets(files).items():
        sev, msg, _ = _verdict(files, page)
        if not sev:
            continue
        for line, _form in forms:
            issues.append({"path": page, "line": line,
                           "severity": sev, "message": msg})
    return issues


def _rename(form: str, canon: dict) -> str:
    """`type=email` і ПЕРШЕ `type=text` -> імена еталона.

    Перейменування скасовується, якщо цільове ім'я у формі вже зайняте іншим
    полем: інакше вийшло б два поля з одним `name`, і блок прочитав би не те.
    Лапки оригінального атрибута зберігаються.
    """
    taken = {nm for _, nm in _fields(form)}
    done: set[str] = set()

    def one(m):
        tag, attrs = m.group(1), m.group(2)
        nm = NAME_ATTR_RX.search(attrs)
        if not nm:
            return m.group(0)
        ty = TYPE_ATTR_RX.search(attrs)
        ty = (ty.group(1) if ty else tag).lower()
        want = canon.get(ty)
        if ty not in ALIGNED or ty in done or not want:
            return m.group(0)
        if nm.group("val") in BLOCK_FIELDS:
            return m.group(0)
        done.add(ty)
        if nm.group("val") == want or want in taken:
            return m.group(0)
        q = nm.group("q")
        return (f"<{tag}" + attrs[:nm.start()] + f"name={q}{want}{q}"
                + attrs[nm.end():] + ">")

    return FIELD_RX.sub(one, form)


def _apply(text: str, canon: dict) -> str:
    """Кожній формі без `action` дописує `action="./"` і вирівнює поля."""
    def one(m):
        form = m.group(0)
        if ACTION_RX.search(_tag(form)):
            return form
        if not _canon(form).keys() >= set(ALIGNED):
            return form          # не лід-форма: пошук, підписка, фільтр
        form = _rename(form, canon)
        return FORM_TAG_RX.sub(
            lambda t: '<form action="./"' + t.group(1) + ">", form, count=1)

    return FORM_RX.sub(one, text)


def fix_branch(files, all_paths, branch: str = ""):
    if any(_form_stub.is_stubbed(t) for p, t in files.items() if p.lower() in ("index.php", "index.html")):
        return []                       # форма-заглушка (form_stub)
    actions = []
    for page in sorted(_targets(files)):
        sev, _msg, canon = _verdict(files, page)
        if sev != "error":
            continue                      # гейт не пройдено — не чіпаємо
        text = files.get(page, "")
        new = _apply(text, canon)
        if new != text:
            actions.append({"type": "edit", "path": page, "content": new})
    return actions
