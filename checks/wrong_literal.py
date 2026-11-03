"""Wrong domain literal: files must use {{DOMAIN}}, never {{DOMAIN_NAME}}.

Виняток — місця, де {{DOMAIN_NAME}} легітимний, бо це літерал ЛОГО/бренду:
  * усередині <header>…</header> і <footer>…</footer>;
  * усередині <div class/id="…header…"> або <div class/id="…footer…">;
  * усередині лого-лінка на головну: <a href="./" | "/" | "index.html">…</a>
    (класична верстка: <a href="./"><span class="font-headers …">Brand</span></a>).

ХОСТ-КОНТЕКСТ Б'Є ЦЕЙ ВИНЯТОК. У пошті чи URL потрібен домен зі зоною, а не
назва бренду: info@{{DOMAIN_NAME}} у футері розкривається в «info@Quenjefvu»,
а такої адреси не існує. Тому "info@", "://" і "www." перед плейсхолдером —
помилка навіть усередині хедера/футера/лого. Голий "@{{DOMAIN_NAME}}" (без
локальної частини) не рахується: це соц-хендл, там бренд-нейм доречний.
Кейс quenjefvu-ch-it; у кеші так було 2728 пошт у 352 вітках, і їх не бачив
жоден чек — contacts.py пропускає будь-який {{…}} як «вже літерал».
Виняток для REACT-вайтів (Vite-бандл: index.php-оболонка + assets/index-*.js):
  * у js/ts/jsx/tsx {{DOMAIN_NAME}} — легітимний плейсхолдер НАЗВИ бренду:
    хедер, meta-титули і всі тексти таких вайтів живуть у js-бандлі, а не в
    html-розмітці. Помилка в js — лише ХОСТ-контекст, де потрібен саме домен:
    "info@{{DOMAIN_NAME}}", "https://{{DOMAIN_NAME}}", "www.{{DOMAIN_NAME}}";
  * у react-оболонці (файл підключає assets/index-*.js) дозволений і
    <title>{{DOMAIN_NAME}} · …</title> — титул там теж бренд-нейм.
Такі входження не є помилкою, і автофікс їх не чіпає.
"""
import re

NAME = "Помилка-1: Неправильний літерал"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"domain"}
PROJECTS = ["php"]
DESCRIPTION = ("У файлах має бути {{DOMAIN}}; якщо трапляється {{DOMAIN_NAME}} — це помилка. "
               "Винятки: хедер, футер і лого-лінк на головну (літерал лого); "
               "у react-вайтах — js-бандл (бренд-нейм у js) і <title> оболонки. "
               "Пошта і URL — виняток з винятку: info@/:///www. вимагають домен "
               "зі зоною навіть у хедері й футері.")
FILES = ["*.html", "*.php", "*.xml", "*.txt", "*.js", "*.css", "*.vue", "*.ts",
         "*.jsx", "*.tsx", "*.mjs"]

RX = re.compile(r"\{\{\s*DOMAIN_NAME\s*\}\}")
# <header>…</header> та <footer>…</footer> цілком
HEADER_TAG_RX = re.compile(r"<header\b.*?</header\s*>", re.S | re.I)
FOOTER_TAG_RX = re.compile(r"<footer\b.*?</footer\s*>", re.S | re.I)
# відкриваючий div, що є хедером/футером: class або id містить "header"/"footer"
DIV_HF_RX = re.compile(
    r"""<div\b[^>]*\b(?:class|id)\s*=\s*["'][^"']*(?:header|footer)[^"']*["'][^>]*>""", re.I)
DIV_TOKEN_RX = re.compile(r"<(/?)div\b", re.I)
# лого-лінк: <a href="./" | "/" | "index.html" | "./index.html" | "/index.php">…</a>
LOGO_A_RX = re.compile(
    r"""<a\b[^>]*\bhref\s*=\s*["'](?:\.?/|\.?/?index\.(?:html?|php))["'][^>]*>.*?</a\s*>""",
    re.S | re.I)

# --- react-вайти (Vite) ---
JS_EXT = (".js", ".mjs", ".jsx", ".ts", ".tsx")
# маркер react-оболонки: сторінка, що підключає vite-бандл
VITE_SHELL_RX = re.compile(
    r"""<script\b[^>]*\bsrc\s*=\s*["'][^"']*assets/index-[^"']*\.js["']""", re.I)
TITLE_RX = re.compile(r"<title\b[^>]*>.*?</title\s*>", re.S | re.I)
# Хост-контекст перед плейсхолдером: тут потрібен ДОМЕН, а не назва бренду.
# @ рахуємо лише з локальною частиною (info@…): голий «@{{DOMAIN_NAME}}» —
# це соц-хендл, там бренд-нейм якраз доречний (у кеші таких 0, але правило
# має лишатись правильним і на майбутнє).
HOST_MISUSE_RX = re.compile(r"(?:[A-Za-z0-9._%+\-]@|://|\bwww\.)\s*$")


def _is_js(path: str) -> bool:
    return str(path).lower().endswith(JS_EXT)


def _allowed_spans(path: str, text: str) -> list[tuple[int, int]]:
    """Діапазони (start, end), у яких {{DOMAIN_NAME}} дозволений."""
    spans = [m.span() for m in HEADER_TAG_RX.finditer(text)]
    spans += [m.span() for m in FOOTER_TAG_RX.finditer(text)]
    spans += [m.span() for m in LOGO_A_RX.finditer(text)]
    if VITE_SHELL_RX.search(text):         # react-оболонка → титул = бренд-нейм
        spans += [m.span() for m in TITLE_RX.finditer(text)]
    for m in DIV_HF_RX.finditer(text):
        depth, end = 1, len(text)
        for t in DIV_TOKEN_RX.finditer(text, m.end()):
            depth += -1 if t.group(1) else 1
            if depth == 0:                     # знайшли парний </div>
                end = t.end()
                break
        # незакритий div-хедер/футер → консервативно до кінця файлу
        spans.append((m.start(), end))
    return spans


def _allowed(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in spans)


def _host_misuse(text: str, m) -> bool:
    """Перед плейсхолдером стоїть пошта або URL."""
    return bool(HOST_MISUSE_RX.search(text[max(0, m.start() - 12):m.start()]))


def _bad_matches(path: str, text: str) -> list:
    """Входження {{DOMAIN_NAME}}, які Є помилкою (спільне для run і fix)."""
    if _is_js(path):
        # js react-вайта: бренд-нейм легітимний скрізь, помилка — лише хост
        return [m for m in RX.finditer(text) if _host_misuse(text, m)]
    spans = _allowed_spans(path, text)
    # Хост-контекст б'є виняток хедера/футера: info@{{DOMAIN_NAME}} у футері
    # розкриється в «info@Quenjefvu» — адреси без зони не існує. Бренд-нейм
    # доречний як ТЕКСТ лого, але не як хост пошти чи URL.
    return [m for m in RX.finditer(text)
            if _host_misuse(text, m) or not _allowed(m.start(), spans)]


def run(path, text):
    issues = []
    for m in _bad_matches(path, text):
        line = text.count("\n", 0, m.start()) + 1
        if _host_misuse(text, m):
            msg = (f"{m.group(0)} у пошті/URL — там потрібен домен зі зоною, "
                   f"а не назва бренду; має бути {{{{DOMAIN}}}}")
        else:
            msg = (f"неправильний літерал {m.group(0)} поза хедером/футером/лого — "
                   f"має бути {{{{DOMAIN}}}}")
        issues.append({"line": line, "severity": "error", "message": msg})
    return issues


def fix(path, text):
    """Автофікс: {{DOMAIN_NAME}} -> {{DOMAIN}} лише там, де run бачить помилку:
    хедер/футер/лого і бренд-нейм у js react-вайтів НЕ чіпаються."""
    out, last = [], 0
    for m in _bad_matches(path, text):
        out.append(text[last:m.start()])
        out.append("{{DOMAIN}}")
        last = m.end()
    out.append(text[last:])
    return "".join(out)
