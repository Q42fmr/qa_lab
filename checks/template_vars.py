"""Недозволені змінні шаблону у видимій розмітці: прибрати.

Кейси 21.10: larza-cepvi — «O ${BRAND} atende só em Porto Alegre?» на
/faq.html; корпус — «{{LOGO}}» у href іконки, «{{White}}», «{{x}}» у тексті.
Деплой підставляє ЛИШЕ {{DOMAIN}} (і {{DOMAIN_NAME}} — ним володіє
wrong_literal); усе інше лишається на сторінці як є, і QA бачить «вместо
текста видны переменные шаблона».

Фікс саме ПРИБИРАЄ токен (не міняє на {{DOMAIN}}: «O {{DOMAIN}} atende» —
не краще). Де: лише у видимій розмітці — поза <script>, <style> і <?php ?>
(у js `${x}` — легітимний template literal, у php — змінні). Сторінки, що
самі є шаблонами рантайму (Vue/Alpine/Handlebars/Mustache/Angular у
<script src> або x-data/createApp), не чіпаємо: там «{{ x }}» — код.
"""
import re

NAME = "Змінні шаблону у видимому тексті"
GROUP = "auto"
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("У розмітці лишились токени генератора (${BRAND}, {{LOGO}}, "
               "{{White}}, {{x}}…), яких деплой не підставляє — відвідувач бачить "
               "їх текстом. Фікс прибирає токени поза <script>/<style>/<?php ?>; "
               "{{DOMAIN}} і {{DOMAIN_NAME}} не чіпає.")
FILES = ["*.html", "*.htm", "*.php"]

ALLOWED = {"DOMAIN", "DOMAIN_NAME"}
TOKEN_RX = re.compile(r"\{\{\s*([^{}\n]{1,40}?)\s*\}\}|\$\{\s*([A-Za-z_][A-Za-z0-9_]{0,39})\s*\}")
# зони, де фігурні дужки — код, а не текст
# <code>/<pre> — синтаксис шаблонів буває темою статті (техблог-вайти);
# <template>/<textarea> — розмітка для JS або значення поля, не текст сторінки
CODE_RX = re.compile(r"<script\b[^>]*>.*?</script\s*>|<style\b[^>]*>.*?</style\s*>|<\?(?:php|=).*?\?>|<!--.*?-->"
                     r"|<(code|pre|template|textarea)\b[^>]*>.*?</\1\s*>", re.S | re.I)
RUNTIME_RX = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["'][^"']*(?:\bvue\b|alpine|handlebars|mustache|angular|knockout)[^"']*["']"""
                        r"""|\bx-data\s*=|createApp\(|new Vue\(|ng-app""", re.I)


def _code_spans(text: str) -> list:
    return [(m.start(), m.end()) for m in CODE_RX.finditer(text)]


def _in_code(pos: int, spans: list) -> bool:
    return any(s <= pos < e for s, e in spans)


def _tokens(text: str) -> list:
    """[(start, end, token)] недозволених токенів поза кодом."""
    if RUNTIME_RX.search(text):
        return []
    spans = _code_spans(text)
    out = []
    for m in TOKEN_RX.finditer(text):
        if _in_code(m.start(), spans):
            continue
        name = (m.group(1) or m.group(2) or "").strip()
        if m.group(1) is not None and name.upper() in ALLOWED:
            continue
        out.append((m.start(), m.end(), m.group(0)))
    return out


def run(path, text):
    toks = _tokens(text)
    if not toks:
        return []
    seen = {}
    for s, e, tok in toks:
        seen.setdefault(tok, text.count("\n", 0, s) + 1)
    names = ", ".join(f"«{t}»" for t in list(seen)[:4]) + (" …" if len(seen) > 4 else "")
    return [{"line": min(seen.values()), "severity": "error",
             "message": f"змінні шаблону у видимому тексті: {names} ({len(toks)} вход.) — "
                        f"деплой їх не підставляє; фікс прибере"}]


def fix(path, text):
    toks = _tokens(text)
    if not toks:
        return text
    out, last = [], 0
    for s, e, _tok in toks:
        chunk = text[last:s]
        # «O ${BRAND} atende» → «O atende»: прибираємо і один із суміжних пробілів
        if chunk.endswith(" ") and text[e:e + 1] == " ":
            chunk = chunk[:-1]
        out.append(chunk)
        last = e
    out.append(text[last:])
    return "".join(out)
