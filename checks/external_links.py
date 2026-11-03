"""HEAD-перевірка зовнішніх http(s)-лінків на биті адреси."""
import re
from concurrent.futures import ThreadPoolExecutor

import requests

NAME = "Биті зовнішні лінки"
GROUP = "review"
PROJECTS = ["php"]
DESCRIPTION = ("HEAD-запит до кожного унікального http(s)-лінка (href/src/srcset/url()). "
               "4xx/5xx або таймаут — error; 403 — warn (може бути захист від ботів).")
FILES = ["*.html", "*.php", "*.css", "*.xml", "*.vue"]

URL_RX = re.compile(
    r"""(?:href|src|content|data-src|poster)\s*=\s*["'](https?://[^"']+)["']"""
    r"""|url\(\s*["']?(https?://[^"')]+)""", re.I)
SRCSET_RX = re.compile(r"""\bsrcset\s*=\s*["']([^"']+)["']""", re.I)
MAX_URLS = 80
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) qa_lab-checker"}


def run_branch(files):
    first: dict[str, tuple] = {}          # url -> (path, line) першого входження
    for path, text in files.items():
        for i, line in enumerate(text.splitlines(), 1):
            cands = [m.group(1) or m.group(2) for m in URL_RX.finditer(line)]
            for ss in SRCSET_RX.findall(line):
                cands += [c.strip().split()[0] for c in ss.split(",")
                          if c.strip().startswith("http")]
            for u in cands:
                u = u.strip().rstrip(",")
                if "{{" in u or "%7B" in u:   # плейсхолдери домену не чіпаємо
                    continue
                first.setdefault(u, (path, i))

    urls = list(first)[:MAX_URLS]

    def probe(u):
        try:
            r = requests.head(u, timeout=8, allow_redirects=True, headers=HEADERS)
            if r.status_code in (405, 501):   # сервер не любить HEAD — пробуємо GET
                r = requests.get(u, timeout=8, stream=True, headers=HEADERS)
            return u, r.status_code
        except Exception as e:
            return u, f"{type(e).__name__}"

    issues = []
    with ThreadPoolExecutor(8) as ex:
        for u, st in ex.map(probe, urls):
            path, line = first[u]
            if isinstance(st, str):
                issues.append({"path": path, "line": line, "severity": "error",
                               "message": f"{u} → {st} (не відповідає)"})
            elif st == 403:
                issues.append({"path": path, "line": line, "severity": "warn",
                               "message": f"{u} → 403 (можливо, захист від ботів)"})
            elif st >= 400:
                issues.append({"path": path, "line": line, "severity": "error",
                               "message": f"{u} → HTTP {st}"})
    if len(first) > MAX_URLS:
        issues.append({"severity": "info",
                       "message": f"перевірено перші {MAX_URLS} з {len(first)} унікальних лінків"})
    return issues
