"""White page не повинна містити робочих форм: <form> з action / method.

Перевіряємо ЛИШЕ index.php (головний вхідний файл вайта) — на скрейпнутих
сторінках-сателітах форми лишаються від оригіналу і їх ніхто не чіпає.
Автофікс вирізає атрибути action/method з тегів <form> в index.php —
сама форма і її верстка лишаються.
"""
import re

import checks.form_stub as _form_stub

NAME = "Форми з action/method"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Знаходить <form> з action= або method= в index.php (робоча форма "
               "на вайті); автофікс прибирає ці атрибути, лишаючи верстку форми.")
FILES = ["index.php"]

FORM_RX = re.compile(r"<form\b([^>]*)>", re.I)
ATTR_RX = re.compile(r"\b(action|method)\s*=", re.I)
# атрибут з будь-якими лапками або без них: action="..." | method=post
ATTR_STRIP_RX = re.compile(
    r"""\s*\b(?:action|method)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.I)


def run(path, text):
    if _form_stub.is_stubbed(text):
        return []                       # форма-заглушка (form_stub): лід не перехоплюється свідомо
    issues = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in FORM_RX.finditer(line):
            attrs = m.group(1)
            found = {a.lower() for a in ATTR_RX.findall(attrs)}
            if found:
                issues.append({
                    "line": i,
                    "severity": "error",
                    "message": f"<form> містить {', '.join(sorted(found))}= — "
                               f"робоча форма на вайті (є автофікс)",
                })
    return issues


def fix(path, text):
    if _form_stub.is_stubbed(text):
        return text
    """Автофікс: <form action="..." method="post"> -> <form> (інші атрибути лишаються)."""
    return FORM_RX.sub(lambda m: "<form" + ATTR_STRIP_RX.sub("", m.group(1)) + ">", text)
