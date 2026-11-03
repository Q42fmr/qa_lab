"""Приклад кастомного трансформу: замінити email по всьому проєкту.

Відредагуй OLD/NEW і застосуй через вкладку Replace -> режим Script.
Можна писати будь-яку логіку у transform(path, text) -> str.
"""
import re

NAME = "Заміна email (приклад)"
DESCRIPTION = "Міняє OLD email на NEW у html/php/js/txt. Відредагуй константи у файлі transforms/change_email.py."
FILES = ["*.html", "*.php", "*.js", "*.txt"]

OLD = "info@old-domain.com"
NEW = "info@new-domain.com"

def transform(path, text):
    return re.sub(re.escape(OLD), NEW, text, flags=re.IGNORECASE)
