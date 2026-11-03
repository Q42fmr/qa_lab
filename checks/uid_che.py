"""UID (CHE-xxx.xxx.xxx) на ch-de вайті: швейцарський сайт компанії без
номера з реєстру — несправжній (QA: «нет реквизитов/UID»).

Чек діє ЛИШЕ на вітках з локаллю ch-* (-ch-de, -ch-de-2, …). Шукається
канонічний запис CHE-123.456.789 будь-де у видимому тексті (футер,
Impressum). Плейсхолдер генератора («CHE-123.456.789», «[Platzhalter
CHE-Nummer]») або номер із битою контрольною цифрою — фейк, його фікс
міняє НА МІСЦІ.

Фікс бере номер з пулу (вкладка «Журнал → БД по гео → UID», модуль
uid_pool) і дописує рядок «UID: CHE-…» у футер тою ж механікою, що й
CNPJ (клон <p> зі стилями вітки / перед </address>). Порожній пул =
error без фікса: вигаданий номер гірший за відсутній.
"""
import re

import checks.cnpj as _cnpj

NAME = "UID (CHE) на ch-de вайті"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"regno"}
PROJECTS = ["php", "node"]
DESCRIPTION = ("Швейцарська вітка (-ch-de) мусить показувати UID "
               "CHE-xxx.xxx.xxx. Фікс додає номер з пулу (Журнал → БД по "
               "гео → UID) рядком у футер, клонуючи стилі сусіднього <p>; "
               "плейсхолдер/битий номер міняє на місці.")
FILES = ["*.html", "*.htm", "*.php", "*.vue"]

UID_RX = re.compile(r"\bCHE-\d{3}\.\d{3}\.\d{3}\b")
# «[Platzhalter CHE-Nummer]» з шаблону builder/src/content/legal.ts
PLACEHOLDER_RX = re.compile(r"\[\s*Platzhalter\s+CHE-Nummer\s*\]", re.I)
_LOCALE_RX = re.compile(r"[-.]([a-z]{2})-[a-z]{2}(?:-\d+)?$")
LINE_PREFIX = "UID: "


def _is_ch(branch: str) -> bool:
    m = _LOCALE_RX.search((branch or "").strip().lower())
    return bool(m) and m.group(1) == "ch"


def _valid_num(num: str) -> bool:
    try:
        import uid_pool
        return uid_pool.valid(num)
    except Exception:
        return True                      # без пулу не судимо про контрольну


def _numbers(files: dict) -> tuple[set, set]:
    """(валідні, фейкові) номери на сайті. Фейк — форма правильна, а
    контрольна цифра ні, або шаблонний плейсхолдер."""
    good, bad = set(), set()
    for t in files.values():
        for m in UID_RX.findall(t):
            (good if _valid_num(m) else bad).add(m)
        for m in PLACEHOLDER_RX.findall(t):
            bad.add(m)
    return good, bad


def _pool_number(branch: str, files: dict) -> str:
    try:
        import uid_pool
        return uid_pool.pick(branch, _cnpj._site_text(files))
    except Exception:
        return ""


_IMP_PATH_RX = re.compile(r"impressum|imprint|mentions-?legales|note-legali", re.I)
_IMP_H1_RX = re.compile(r"<h1[^>]*>\s*(?:Impressum|Mentions\s+l[ée]gales|Note\s+legali)\s*</h1>", re.I)
_ADDR_P_RX = re.compile(r"<(p|li)\b([^>]*)>(?:(?!</\1>).)*?\b\d{4,5}\s+[A-ZÀ-Ý][\wÀ-ÿ.'-]+(?:(?!</\1>).)*?</\1>", re.S)


def _impressum_without_uid(files: dict, good: set) -> str:
    """Шлях Impressum-сторінки, де немає жодного UID сайту (QA вимагає номер
    саме там — CH-DE 868mnmxpm 27.10, UID стояв лише у політиці)."""
    for p in sorted(files):
        if not p.lower().endswith((".html", ".htm", ".php")):
            continue
        if not (_IMP_PATH_RX.search(p) or _IMP_H1_RX.search(files[p])):
            continue
        if not any(n in files[p] for n in good):
            return p
    return ""


def _add_uid_to_impressum(text: str, number: str) -> str:
    """«UID: CHE-…» після абзацу з адресою (індекс + місто), клон тега/класу;
    без такого абзацу — після першого <p> за <h1>."""
    m = _ADDR_P_RX.search(text)
    if not m:
        hm = re.search(r"</h1>", text, re.I)
        m = re.compile(r"<(p)\b([^>]*)>.*?</p>", re.S | re.I).search(text, hm.end() if hm else 0)
        if not m:
            return text
    tag, attrs = m.group(1), m.group(2)
    return text[:m.end()] + f"<{tag}{attrs}>{LINE_PREFIX}{number}</{tag}>" + text[m.end():]


def run_branch(files, all_paths, branch: str = ""):
    if not _is_ch(branch):
        return []
    good, bad = _numbers(files)
    if good and not bad:
        bare = _impressum_without_uid(files, good)
        if not bare:
            return []
        num = sorted(good)[0]
        return [{"path": bare, "line": 1, "severity": "error",
                 "message": (f"на Impressum немає UID сайту ({num}; він стоїть лише на інших сторінках) — "
                             f"QA вимагає номер саме на Impressum; фікс допише «{LINE_PREFIX}{num}» після адреси")}]
    feet = _cnpj._footer_paths(files)
    where = feet[0] if feet else (sorted(files)[0] if files else "")
    if not where:
        return []
    number = _pool_number(branch, files)
    line = f"{LINE_PREFIX}{number}"
    if bad:
        where = next(p for p in sorted(files)
                     if any(b in files[p] for b in bad))
        repl = (f"фікс замінить на «{number}» з пулу" if number
                else "пул порожній — додай номери у «Журнал → БД по гео → UID»")
        msg = (f"на сайті фейковий UID {', '.join(sorted(bad))} "
               f"(плейсхолдер генератора або контрольна цифра не сходиться) — "
               f"{repl}")
    elif not number:
        msg = ("на сайті немає UID, а пул номерів порожній — додай номери "
               "у вкладці «Журнал → БД по гео → UID», фіксу нема звідки взяти")
    elif not feet:
        msg = ("на сайті немає UID і немає <footer>, куди його дописати — "
               "додай руками")
    elif not any(_cnpj._append_line(files[p], line) != files[p] for p in feet):
        msg = (f"на сайті немає UID, а у футер його нема куди покласти "
               f"(ні <p>, ні <address>) — додай руками: «{line}»")
    else:
        msg = (f"на сайті немає UID — фікс допише «{line}» у футер "
               f"рядком у стилях вітки")
    return [{"path": where, "line": 1, "severity": "error", "message": msg}]


def fix_branch(files, all_paths, branch: str = ""):
    if not _is_ch(branch):
        return []
    good, bad = _numbers(files)
    if good and not bad:
        bare = _impressum_without_uid(files, good)
        if not bare:
            return []
        new = _add_uid_to_impressum(files[bare], sorted(good)[0])
        return [{"type": "edit", "path": bare, "content": new}] if new != files[bare] else []
    number = _pool_number(branch, files)
    if not number:
        return []                        # порожній пул — тільки ручний шлях
    actions = []
    if bad:
        # фейк замінюється НА МІСЦІ: позиція, стилі і підпис лишаються
        for path in sorted(files):
            new = files[path]
            for b in bad:
                new = new.replace(b, number)
            if new != files[path]:
                actions.append({"type": "edit", "path": path, "content": new})
        return actions
    line = f"{LINE_PREFIX}{number}"
    for path in _cnpj._footer_paths(files):
        new = _cnpj._append_line(files[path], line)
        if new != files[path]:
            actions.append({"type": "edit", "path": path, "content": new})
    return actions
