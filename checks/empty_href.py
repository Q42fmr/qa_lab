"""Flags <a> tags with an empty href attribute."""
import re

NAME = "Порожні href у тегах <a>"
GROUP = "tests"
PROJECTS = ["php"]
DESCRIPTION = "Шукає <a> з href=\"\" (порожнім або з самих пробілів) — лінк нікуди не веде."
FILES = ["*.html", "*.php", "*.vue"]

RX = re.compile(r"<a\b[^>]*\bhref\s*=\s*([\"'])\s*\1", re.IGNORECASE)

def run(path, text):
    issues = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in RX.finditer(line):
            issues.append({
                "line": i,
                "severity": "error",
                "message": "порожній href=\"\" у тегу <a>",
            })
    return issues
