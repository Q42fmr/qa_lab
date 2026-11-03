"""JS-перехоплювач submit: форма виглядає робочою, але лід не відправляється.

Генератор інколи додає до форми власний хендлер:

    form.addEventListener('submit', function(e){
      e.preventDefault();
      ...клієнтська валідація...
      if(ok){ window.location.href='thank-you.html'; }
    });

Зовні все гаразд — валідація працює, після сабміту людина бачить подяку. Але
`preventDefault()` глушить справжню відправку, а редірект просто малює успіх:
дані форми НІКУДИ не йдуть, лід гине. Справжню відправку на вайтах робить
інжектований скрипт форми.

Правило (усі три умови разом, інакше не чіпаємо):
  * у submit-хендлері є `preventDefault()`;
  * є редірект (`location.href=` / `location.assign()` / `location.replace()`);
  * і НЕМАЄ жодної відправки (fetch / XMLHttpRequest / axios / sendBeacon /
    jQuery.ajax / form.submit()) — хендлер із відправкою це легітимний
    AJAX-сабміт, він і мусить лишитись.

Автофікс не видаляє код, а КОМЕНТУЄ хендлер блоковим коментарем із маркерами
OPEN_MARK/CLOSE_MARK: прибрав маркери — отримав байт-у-байт початковий код.
Решта функції (очистка помилок, UTM-поля) лишається робочою.
"""
import re

import checks.form_stub as _form_stub

NAME = "JS глушить форму (submit)"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("submit-хендлер з preventDefault() і редіректом на подяку, але без "
               "жодної відправки даних (fetch/XHR/submit()) — форма виглядає "
               "робочою, а лід не відправляється. Автофікс коментує хендлер "
               "(маркери, зворотно), відправку робить інжектований скрипт форми.")
FILES = ["*.js", "*.html", "*.htm", "*.php"]

OPEN_MARK = "/* [qa_lab:hijack-off] перехоплювач глушив форму; прибери обидва маркери, щоб повернути\n"
CLOSE_MARK = "\n[/qa_lab:hijack-off] */"

SUBMIT_ARG_RX = re.compile(r"\(\s*['\"]submit['\"]\s*,")
PREVENT_RX = re.compile(r"\.\s*preventDefault\s*\(")
REDIRECT_RX = re.compile(
    r"(?:window\s*\.\s*|document\s*\.\s*)?location\s*"
    r"(?:\.\s*href\s*=(?!=)|\.\s*assign\s*\(|\.\s*replace\s*\(|=(?!=))")
SEND_RX = re.compile(
    r"fetch\s*\(|XMLHttpRequest|axios\b|sendBeacon|\$\.(?:ajax|post|get)\b"
    r"|\.\s*submit\s*\(\s*\)")

# після цих символів `/` починає regex-літерал, а не ділення
_REGEX_PREV = set("(,=:[!&|?{};+-*%~^<>\n")
_RECV_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                  "0123456789_$.[]'\"")


def _prev_code_char(text: str, i: int) -> str:
    j = i - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    return text[j] if j >= 0 else "\n"


def _lex_regions(text: str) -> list[tuple[int, int]]:
    """Інтервали рядків/коментарів/regex-літералів — усе, що НЕ код.
    Потрібно двічі: щоб не ловити addEventListener у коментарі (ідемпотентність
    фікса) і щоб баланс дужок не збивався об дужки в літералах."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"`":
            start = i
            q = c
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == q:
                    break
                if q != "`" and text[i] == "\n":   # обірваний рядок
                    break
                i += 1
            out.append((start, min(i, n - 1)))
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            start = i
            j = text.find("\n", i)
            i = n - 1 if j < 0 else j
            out.append((start, i))
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            start = i
            j = text.find("*/", i + 2)
            i = n - 1 if j < 0 else j + 1
            out.append((start, i))
        elif c == "/" and _prev_code_char(text, i) in _REGEX_PREV:
            start = i
            i += 1
            in_class = False
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if in_class:
                    if text[i] == "]":
                        in_class = False
                elif text[i] == "[":
                    in_class = True
                elif text[i] == "/" or text[i] == "\n":
                    break
                i += 1
            out.append((start, min(i, n - 1)))
        i += 1
    return out


def _in_regions(regions, pos: int) -> bool:
    return any(a <= pos <= b for a, b in regions)


def _stmt_start(text: str, i: int) -> int:
    """Від 'addEventListener' назад до початку виразу-приймача (`form.`,
    `forms[f].`, `document.getElementById('x').`)."""
    j = i
    while j > 0:
        ch = text[j - 1]
        if ch in _RECV_CHARS:
            j -= 1
        elif ch == ")":
            depth = 0
            k = j - 1
            while k >= 0:
                if text[k] == ")":
                    depth += 1
                elif text[k] == "(":
                    depth -= 1
                    if depth == 0:
                        break
                k -= 1
            if k < 0:
                break
            j = k
        else:
            break
    return j


def _call_end(text: str, open_paren: int, regions) -> int:
    """Позиція `)` що закриває виклик addEventListener(...)."""
    depth = 0
    i = open_paren
    n = len(text)
    while i < n:
        if _in_regions(regions, i):
            i += 1
            continue
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _hijack_spans(text: str) -> list[tuple[int, int]]:
    """[(start, end)] шкідливих викликів addEventListener('submit', …);
    end — за закривним `;` (або `)`, якщо `;` немає)."""
    regions = _lex_regions(text)
    spans = []
    for m in re.finditer(r"addEventListener", text):
        if _in_regions(regions, m.start()):
            continue
        args = SUBMIT_ARG_RX.match(text, m.end())
        if not args:
            continue
        open_paren = text.find("(", m.end())
        close = _call_end(text, open_paren, regions)
        if close < 0:
            continue
        end = close
        rest = text[close + 1:close + 3]
        if rest[:1] == ";":
            end = close + 1
        call = text[m.start():end + 1]
        if not PREVENT_RX.search(call):
            continue
        if not REDIRECT_RX.search(call):
            continue
        if SEND_RX.search(call):
            continue                       # AJAX-сабміт — легітимний
        spans.append((_stmt_start(text, m.start()), end))
    return spans


def run(path, text):
    if _form_stub.is_stubbed(text):
        return []                       # форма-заглушка (form_stub): лід не перехоплюється свідомо
    issues = []
    for start, _ in _hijack_spans(text):
        issues.append({
            "line": text[:start].count("\n") + 1,
            "severity": "error",
            "message": ("submit-хендлер глушить форму: preventDefault() + "
                        "редірект на подяку БЕЗ відправки даних — лід не "
                        "відправляється"),
        })
    return issues


def fix(path, text):
    if _form_stub.is_stubbed(text):
        return text
    """Коментує кожен шкідливий хендлер маркерами. Зворотно: прибрати
    OPEN_MARK і CLOSE_MARK — код повернеться байт-у-байт."""
    spans = _hijack_spans(text)
    for start, end in reversed(spans):
        text = (text[:start] + OPEN_MARK + text[start:end + 1] +
                CLOSE_MARK + text[end + 1:])
    return text
