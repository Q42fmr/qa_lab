"""Немає e-mail на видимих сторінках (кейс QA tefluer-gechaoh-ch-fr 27.10).

Навіщо. QA-скарга «Нет почты»: на всьому сайті не було жодної адреси
електронної пошти — ні mailto, ні текстом. Ручний фікс поклав у футер
index.php рядок із `info@{{DOMAIN}}` (mailto) у стилях існуючого рядка
футера — поряд із номером IDE/CHE. Buyer-правило для jp p-36 і QA-практика
по всіх локалях: кожна біла сторінка мусить показувати e-mail на домені.

Правило. «Видимі» сторінки — усі, крім юридичних (terms/privacy/cookie/
impressum/mentions/…, той самий `address_number._LEGAL_PATH_RX`). E-mail
«є на сайті», коли його показує ГОЛОВНА (QA судить саме її — tesa-nomu
27.10: пошта лише на /garantia і в політиках, «на главной не найдено ни
одной почты»); без головної — будь-яка видима сторінка. Рахується mailto: або
текстова адреса `local@домен` поза `<script>`/`<style>`/php-блоками і поза
`placeholder="…"` (приклад у полі вводу — не контакт, той самий виняток,
що й у `contacts.py`). Локальну частину для фікса беремо з БУДЬ-ЯКОЇ пошти
вітки (юридичні сторінки рахуються — e-mail у приватній політиці теж
підказка, яку адресу очікує власник), домен завжди літерал `{{DOMAIN}}`
(php-чек); без жодної знайденої пошти — `info`.

Автофікс клонує стиль останнього текстового рядка футера (`<p>`/`<div>`/
`<li>`, та сама механіка, що в `address_number._append_footer_line`) і
додає туди `<a href="mailto:LOCAL@{{DOMAIN}}">LOCAL@{{DOMAIN}}</a>` —
окремим рядком під останнім. Сторінки без розпізнаваного футера фікс не
чіпає — чек сам каже про це в повідомленні («додай руками»), а issue не
створюється для сторінки, яку фікс не вміє полагодити.
"""
import re

NAME = "Email: немає на видимих сторінках"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("На видимих (не юридичних) сторінках немає жодної адреси e-mail — "
               "ні mailto, ні текстом. Автофікс додає у футер кожної сторінки з "
               "розпізнаваним футером рядок `info@{{DOMAIN}}` (mailto) у стилях "
               "сусідніх рядків футера; локальну частину бере з будь-якої пошти, "
               "що вже є на вітці (інакше — `info`). Сторінки без футера лишаються "
               "ручними.")
FILES = ["*.html", "*.htm", "*.php"]

DOMAIN = "{{DOMAIN}}"
# script/style/коментарі/php-блоки — e-mail усередині них не контакт
_HIDDEN_RX = re.compile(
    r"<script\b.*?</script\s*>|<style\b.*?</style\s*>|<!--.*?-->|<\?php.*?\?>",
    re.I | re.S)


def _mask(text: str, rx: re.Pattern) -> str:
    return rx.sub(lambda m: " " * len(m.group(0)), text)


def _visible_text(text: str, contacts):
    t = _mask(text, _HIDDEN_RX)
    for s, e in contacts._example_spans(t):
        t = t[:s] + " " * (e - s) + t[e:]
    return t


def _visible_pages(files: dict, an) -> list:
    # юридичні + Impressum/Datenschutz (address_number._CANON_PATH_RX): на них
    # пошта не рахується і туди фікс не пише (trehu 27.10: datenschutz-сторінка)
    return sorted(p for p in files if not an._CANON_PATH_RX.search(p))


def _page_has_email(text: str, contacts) -> bool:
    return bool(contacts.EMAIL_RX.search(_visible_text(text, contacts)))


def _home(files: dict):
    return next((p for p in ("index.php", "index.html", "index.htm") if p in files), None)


def _has_visible_email(files: dict, an, contacts) -> bool:
    """Пошта «є на сайті» = є на ГОЛОВНІЙ (QA судить саме її: «на главной
    не найдено ни одной почты» — tesa-nomu 27.10, пошта лише на /garantia).
    Без головної — будь-яка видима сторінка."""
    home = _home(files)
    if home:
        return _page_has_email(files[home], contacts)
    for p in _visible_pages(files, an):
        if _page_has_email(files[p], contacts):
            return True
    return False


def _local_part(files: dict, contacts) -> str:
    """Локальна частина БУДЬ-ЯКОЇ пошти вітки (юридичні сторінки рахуються,
    php-блоки/script/style/placeholder — ні); немає жодної — «info»."""
    for p in sorted(files):
        m = contacts.EMAIL_RX.search(_visible_text(files[p], contacts))
        if m:
            return m.group(0).split("@", 1)[0]
    return "info"


def _mailto(local: str) -> str:
    addr = f"{local}@{DOMAIN}"
    return f'<a href="mailto:{addr}">{addr}</a>'


def run_branch(files, all_paths, branch: str = ""):
    import checks.address_number as an
    import checks.contacts as contacts
    if not files or _has_visible_email(files, an, contacts):
        return []
    visible = _visible_pages(files, an)
    if not visible:
        return []
    local = _local_part(files, contacts)
    content = _mailto(local)
    feet = [p for p in visible if an.FOOTER_RX.search(files[p]) and not _page_has_email(files[p], contacts)]
    doable = [p for p in feet if an._append_footer_line(files[p], content) != files[p]]
    if doable:
        msg = ("на видимих сторінках немає e-mail — фікс додасть у футер кожної "
               f"сторінки «{local}@{DOMAIN}» (mailto) у стилі рядків футера")
        if len(doable) < len(visible):
            msg += ("; сторінки без розпізнаваного футера фікс не чіпає — "
                    "додай туди руками")
        path0 = doable[0]
    else:
        msg = (f"на видимих сторінках немає e-mail, а у футер її нема куди "
               f"покласти (немає <p>/<div>/<li>) — додай руками: "
               f"«{local}@{DOMAIN}»")
        path0 = visible[0]
    return [{"path": path0, "line": 1, "severity": "error", "message": msg}]


def fix_branch(files, all_paths, branch: str = ""):
    import checks.address_number as an
    import checks.contacts as contacts
    files = {p: t for p, t in files.items()
             if p.lower().endswith((".html", ".htm", ".php"))}
    if not files or _has_visible_email(files, an, contacts):
        return []
    visible = _visible_pages(files, an)
    if not visible:
        return []
    local = _local_part(files, contacts)
    content = _mailto(local)
    actions = []
    for p in visible:
        if _page_has_email(files[p], contacts):
            continue                      # сторінка вже показує пошту
        new = an._append_footer_line(files[p], content)
        if new != files[p]:
            actions.append({"type": "edit", "path": p, "content": new})
    return actions
