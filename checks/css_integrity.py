"""Стилі сторінок: биті лінки на css-файли і сторінки взагалі без стилів.

Що ловимо:
  * <link rel="stylesheet" href="..."> на локальний css, якого немає у вітці
    (відносні шляхи резолвляться від теки сторінки; ../ і /root-відносні теж);
  * css існує, але з іншим регістром — на Linux-сервері це буде 404;
  * лінк на css, який існує, але порожній (сторінка лишиться без стилів);
  * повна сторінка (є <head>) без жодного джерела стилів: ні stylesheet-лінка,
    ні <style>, ні style=, ні tailwind-cdn. Сторінки з php include/require
    не чіпаємо — стилі можуть приїжджати з інклюда.
Зовнішні лінки (http/https///) не перевіряються — це робить external_links.
"""
import posixpath
import re

NAME = "CSS: биті лінки і сторінки без стилів"
GROUP = "tests"    # звалідовано на 843 вітках: 24 спрацювання, всі реальні (фолсів 0)
PROJECTS = ["php"]
DESCRIPTION = ("Лінки на неіснуючі/порожні css-файли (в т.ч. розбіжність регістру) "
               "і повні сторінки без жодних стилів.")
FILES = ["*.html", "*.php", "*.css"]

LINK_RX = re.compile(r"<link\b[^>]*>", re.I)
HREF_RX = re.compile(r"""\bhref\s*=\s*["']([^"']+)["']""", re.I)
REL_STYLE_RX = re.compile(r"""\brel\s*=\s*["'][^"']*stylesheet""", re.I)
STYLE_TAG_RX = re.compile(r"<style\b", re.I)
STYLE_ATTR_RX = re.compile(r"""\bstyle\s*=\s*["'][^"']+["']""", re.I)
TAILWIND_RX = re.compile(r"""<script\b[^>]*src\s*=\s*["'][^"']*tailwind""", re.I)
HEAD_RX = re.compile(r"<head\b", re.I)
PHP_INCLUDE_RX = re.compile(r"\b(?:include|require)(?:_once)?\b", re.I)


def _resolve(page: str, target: str) -> list[str] | None:
    """Кандидати шляхів css у вітці; None — не локальний файл (не чіпаємо).
    Відносний шлях пробуємо і від теки сторінки, і від кореня вітки —
    сторінки в підпапках часто рендеряться index.php з кореня."""
    t = target.split("?")[0].split("#")[0].strip()
    if not t or t.startswith(("http://", "https://", "//", "data:")) or "{{" in t:
        return None
    if t.startswith("/"):
        return [t.lstrip("/")]
    rel = posixpath.normpath(posixpath.join(posixpath.dirname(page), t))
    root = posixpath.normpath(t)
    return [rel] if root == rel else [rel, root]


def run_branch(files, all_paths):
    fileset = set(all_paths)
    lower_map = {}
    for p in all_paths:
        lower_map.setdefault(p.lower(), p)

    issues = []
    for path, text in files.items():
        if not path.lower().endswith((".html", ".htm", ".php")):
            continue

        has_sheet_link = False
        for m in LINK_RX.finditer(text):
            tag = m.group(0)
            if not REL_STYLE_RX.search(tag):
                continue
            has_sheet_link = True
            href = HREF_RX.search(tag)
            if not href:
                continue
            cands = _resolve(path, href.group(1))
            if cands is None:
                continue
            line = text.count("\n", 0, m.start()) + 1
            hit = next((c for c in cands if c in fileset), None)
            if hit is not None:
                css_text = files.get(hit)
                if css_text is not None and not css_text.strip():
                    issues.append({"path": path, "line": line, "severity": "warn",
                                   "message": f"лінк на порожній css: '{href.group(1)}' — "
                                              f"стилі не застосуються"})
                continue
            case_hit = next((lower_map[c.lower()] for c in cands
                             if c.lower() in lower_map), None)
            if case_hit:
                issues.append({"path": path, "line": line, "severity": "error",
                               "message": f"css '{href.group(1)}' існує як "
                                          f"'{case_hit}' — регістр відрізняється, "
                                          f"на сервері буде 404"})
            else:
                issues.append({"path": path, "line": line, "severity": "error",
                               "message": f"лінк на неіснуючий css: '{href.group(1)}'"})

        # «сторінка без стилів» — лише для повних документів без php-інклюдів
        if (HEAD_RX.search(text) and not has_sheet_link
                and not STYLE_TAG_RX.search(text)
                and not TAILWIND_RX.search(text)
                and not STYLE_ATTR_RX.search(text)
                and not PHP_INCLUDE_RX.search(text)):
            issues.append({"path": path, "line": None, "severity": "error",
                           "message": "сторінка без стилів: немає ні <link rel=\"stylesheet\">, "
                                      "ні <style>, ні inline-стилів, ні tailwind"})
    return issues
