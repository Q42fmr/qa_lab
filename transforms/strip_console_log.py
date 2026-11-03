"""Прибирає рядки, що складаються лише з console.log(...)."""
import re

NAME = "Видалити console.log"
DESCRIPTION = "Видаляє рядки, які містять тільки console.log(...); у js/html/php."
FILES = ["*.js", "*.html", "*.php"]

RX = re.compile(r"^\s*console\.log\([^;]*\);?\s*\n", re.MULTILINE)

def transform(path, text):
    return RX.sub("", text)
