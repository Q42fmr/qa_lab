"""Хедер має бути однаково застилізований на всіх сторінках вітки.

Порівнюємо не сирий текст (він різний: активний пункт меню, переклади),
а «стильовий відбиток» — множину тегів разом з їхніми CSS-класами.
Активний стан пункту меню не заважає: той самий клас присутній у наборі
кожної сторінки (лише на іншому лінку), а множина його дедуплікує.
"""
import math
import re

NAME = "Хедер: однакові стилі"
GROUP = "review"
PROJECTS = ["php"]      # у node-вайтах хедер — один компонент, порівнювати нічого
DESCRIPTION = "Порівнює стилі (теги + CSS-класи) <header> між сторінками; сторінка з іншим набором стилів — error."
FILES = ["*.html", "*.php"]

HEADER_RX = re.compile(r"<header\b.*?</header>", re.S | re.I)
STRIP_RX = re.compile(r"<script.*?</script>|<style.*?</style>", re.S | re.I)
CLASS_RX = re.compile(r"""class\s*=\s*"([^"]*)"|class\s*=\s*'([^']*)'""", re.I)

THRESHOLD = 0.8           # схожість словника класів нижче — стилі різні


def _style_set(header: str) -> set[str]:
    """Словник окремих CSS-класів, використаних у хедері (це і є 'стилі').
    Порівняння по окремих класах стійке до активного стану меню —
    активний клас присутній у наборі кожної сторінки, де є активний пункт."""
    header = STRIP_RX.sub(" ", header)
    tokens = set()
    for m in CLASS_RX.finditer(header):
        for cls in (m.group(1) or m.group(2) or "").split():    # class="" — порожньо, не None
            tokens.add(cls)
    return tokens


def run_branch(files):
    sets = {}
    for path, text in files.items():
        m = HEADER_RX.search(text)
        if m:
            s = _style_set(m.group(0))
            if s:
                sets[path] = s
    if len(sets) < 3:
        return []                       # замало сторінок для висновку

    # консенсус — токени, присутні щонайменше на половині сторінок
    n = len(sets)
    counts = {}
    for s in sets.values():
        for t in s:
            counts[t] = counts.get(t, 0) + 1
    consensus = {t for t, c in counts.items() if c >= math.ceil(n / 2)}
    if not consensus:
        return []

    issues = []
    for path, s in sets.items():
        inter = len(s & consensus)
        union = len(s | consensus)
        sim = inter / union if union else 1.0
        if sim < THRESHOLD:
            extra = sorted(s - consensus)[:4]
            missing = sorted(consensus - s)[:4]
            detail = []
            if missing:
                detail.append("немає: " + ", ".join(missing))
            if extra:
                detail.append("зайве: " + ", ".join(extra))
            issues.append({
                "path": path, "severity": "error",
                "message": f"хедер стилістично відрізняється ({round(sim * 100)}% збігу) — "
                           + "; ".join(detail),
            })
    return issues
