"""Підготовка головної сторінки вайта: форма-заглушка без лід-PHP.

З 20.10 головна готується в режимі «заглушка» (checks/form_stub) замість
старого флоу з лід-перехопленням:
  1. вона мусить бути index.php (php-код у .html не виконається);
  2. з неї вирізається лід-частина PHP: $returnPage, fbpixelevent і блок
     `if (isset($_GET['email'])…) { fbq lead / gtag conversion / bing UET /
     redirect; exit(); }`. $isDev/dotenv, $trackingConfig і head-пікселі
     (fbq init / gtag config — ПЕРЕГЛЯДИ) лишаються;
  3. у <form> знімаються action/method/onsubmit і додається data-<id>="1";
     перед </body> іде інлайн-скрипт-заглушка (один із 50 варіантів з
     checks/_form_stub_variants, вибір фіксований за віткою) — submit глушиться
     клієнтом, кнопка «Enviando…» disabled ~1.4 с, після чого redirect на
     сторінку подяки вітки або inline-подяка мовою вітки.
Плюс наслідок перейменування: лінки на головну (href="index.html") треба звести
до href="./" — саме так лінкуються всі справні вайти корпусу.

Нічого не пише на диск і не комітить: plan()/compute_fixes() лише готують дії,
застосовує їх app.py (create/delete/update у GitLab + оновлення знімка).

Лише для php-проєкту. У vue-вайта головну під форму готує сам білд
(scripts/inject-php.cjs), тож на node-проєкті compute_fixes() відмовляє.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import runner

CHECKS_DIR = Path(__file__).resolve().parent / "checks"
INDEX_HTML_NAMES = ("index.html", "index.htm")
PAGE_EXT = (".html", ".htm", ".php")

NODE_REFUSAL = ("«Головна під форму» — лише для php-вайтів: у vue-вітці index.html — "
                "вхід збірки vite, а php у головну вставляє сам білд "
                "(scripts/inject-php.cjs)")


def _load_check(name: str):
    """checks/<name>.py як модуль — так само, як це робить runner.load_checks()."""
    path = CHECKS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"checks.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _depth(rel_path: str) -> int:
    return rel_path.replace("\\", "/").count("/")


def home_link_rx(rel_path: str) -> re.Pattern:
    """Регекс посилань, що ведуть на КОРЕНЕВИЙ index.html, з файлу rel_path.

    Глибина важлива: з blog/page.html на корінь веде '../index.html', а
    'index.html' там означає сусідній blog/index.html — його не чіпаємо.
    """
    d = _depth(rel_path)
    prefix = "(?:\\./)?" if d == 0 else "(?:\\.\\./){%d}" % d
    return re.compile(
        r"""(?P<attr>\b(?:href|content)\s*=\s*)(?P<q>["'])"""
        r"""(?P<pre>/|%s)index\.html?(?P<tail>[?#][^"']*)?(?P=q)""" % prefix,
        re.I)


def rewrite_home_links(text: str, rel_path: str) -> tuple[str, int]:
    """href="index.html" → href="./" (з blog/: '../index.html' → '../')."""
    n = 0

    def one(m):
        nonlocal n
        n += 1
        pre = m.group("pre")
        target = pre if pre else "./"
        return (m.group("attr") + m.group("q") + target
                + (m.group("tail") or "") + m.group("q"))

    return home_link_rx(rel_path).sub(one, text), n


def prepare_index(text: str, rel_path: str = "index.php",
                  blocks: bool = True, forms: bool = True,
                  links: bool = True, branch: str = "",
                  all_paths: list | None = None) -> tuple[str, dict]:
    """Готує вміст головної.

    blocks — вирізати лід-PHP (dotenv, $trackingConfig і head-пікселі лишаються).
    forms  — зробити лід-форму заглушкою (data-<id> + один із 50 скриптів).
    links  — звести href на головну до «./».
    """
    log: dict = {"php_stripped": 0, "forms": 0, "variant": None, "links": 0}
    if blocks or forms:
        stub = _load_check("form_stub")
        new = stub.apply(text, rel_path, all_paths or [rel_path], branch,
                         strip_php=blocks, stub=forms)
        if new != text:
            log["php_stripped"] = max(0, len(stub.PHP_BLOCK_RX.findall(text))
                                      - len(stub.PHP_BLOCK_RX.findall(new)))
            if forms and stub.STUB_FORM_RX.search(new):
                log["forms"] = len(stub.STUB_FORM_RX.findall(new))
                log["variant"] = stub.variant_index(branch)
            text = new
    if links:
        text, log["links"] = rewrite_home_links(text, rel_path)
    return text, log


# ---------------------------------------------------------------- вітка
def _main_page(all_paths: list[str]) -> tuple[str | None, str | None]:
    """(головна, html-головна що підлягає перейменуванню) у корені вітки."""
    root = {p for p in all_paths if "/" not in p.replace("\\", "/")}
    lower = {p.lower(): p for p in root}
    php = lower.get("index.php")
    html = next((lower[n] for n in INDEX_HTML_NAMES if n in lower), None)
    if php:
        return php, None            # php головна вже є — html не чіпаємо
    return html, html


def compute_fixes(branch: str, blocks: bool = True, forms: bool = True,
                  links: bool = True, rename: bool = True) -> dict:
    """Дії для підготовки головної. Нічого не пише.

    {"actions": [{type: create|delete|edit, path, old, new}],
     "applied": [...], "skipped": [{what, why}], "main": {...}}
    """
    import projects
    # У vue index.html — вхід vite (vite.config не задає rollupOptions.input),
    # а php-блоки вставляє scripts/inject-php.cjs уже в dist після `vite build`.
    # Перейменування в index.php з <?php у джерелі білд не переживає: 14.10
    # так зламалось 11 nwf-віток («Could not resolve entry module
    # "index.html"»), і лікував лише revert. Тому відмова — до читання знімка.
    if projects.ptype() == "node":
        raise ValueError(NODE_REFUSAL)
    all_paths = runner.snapshot_files(branch)
    if not all_paths:
        raise ValueError("вітка не синхронізована — спершу Sync")

    main, html_main = _main_page(all_paths)
    if not main:
        return {"actions": [], "applied": [],
                "skipped": [{"what": "головна", "why": "у корені немає index.php/index.html"}],
                "main": None}

    def read(p: str) -> str:
        return runner.read_snapshot_file(branch, p).decode("utf-8", "replace")

    actions, applied, skipped = [], [], []
    src = read(main)
    will_rename = bool(html_main) and rename
    target = "index.php" if will_rename else main

    new_text, log = prepare_index(src, rel_path=target, blocks=blocks,
                                  forms=forms, links=links, branch=branch,
                                  all_paths=all_paths)

    if will_rename:
        actions.append({"type": "create", "path": "index.php", "old": "", "new": new_text})
        actions.append({"type": "delete", "path": html_main, "old": src, "new": ""})
        applied.append({"what": "головна → php", "detail": f"{html_main} → index.php"})
    elif new_text != src:
        actions.append({"type": "edit", "path": main, "old": src, "new": new_text})
    if html_main and not rename:
        skipped.append({"what": "перейменування", "why": "вимкнено в налаштуваннях"})

    if log["php_stripped"]:
        applied.append({"what": "лід-PHP", "detail": f"вирізано блоків: {log['php_stripped']}"})
    if log["forms"]:
        applied.append({"what": "форма-заглушка", "detail": f"варіант #{log['variant']}"})
    if log["links"]:
        applied.append({"what": "лінки на головну", "detail": f"{main}: {log['links']}"})

    # форма-заглушка на решті сторінок вітки (та сторінка контактів теж
    # має data-<id>-форму + скрипт-варіант)
    if forms:
        stub = _load_check("form_stub")
        pseudo = {main if not will_rename else "index.php": new_text}
        for p in all_paths:
            if p == main or not p.lower().endswith(PAGE_EXT):
                continue
            try:
                pseudo[p] = read(p)
            except OSError:
                continue
        acts = stub.fix_branch(dict(pseudo), list(all_paths), branch)
        touched_main = (main if not will_rename else "index.php")
        for a in acts:
            if a["path"] == touched_main:
                continue                             # головна вже оброблена
            actions.append({"type": "edit", "path": a["path"],
                            "old": pseudo[a["path"]], "new": a["content"]})
            applied.append({"what": "форма-заглушка", "detail": a["path"]})

    # лінки на головну по решті сторінок вітки — склеюю з попередніми edit,
    # щоб не було двох actions на той самий файл
    if links and will_rename:
        by_path = {a["path"]: a for a in actions if a["type"] == "edit"}
        for p in all_paths:
            if p == main or not p.lower().endswith(PAGE_EXT):
                continue
            try:
                orig_t = read(p)
            except OSError:
                continue
            prev = by_path.get(p)
            base = prev["new"] if prev else orig_t
            nt, n = rewrite_home_links(base, p)
            if n:
                applied.append({"what": "лінки на головну", "detail": f"{p}: {n}"})
                if prev:
                    prev["new"] = nt
                else:
                    actions.append({"type": "edit", "path": p, "old": orig_t, "new": nt})

    return {"actions": actions, "applied": applied, "skipped": skipped,
            "main": {"from": main, "to": target, "renamed": will_rename}}


def plan(branch: str) -> dict:
    """Що треба зробити на вітці (без опцій, для списку/бейджів)."""
    r = compute_fixes(branch)
    return {
        "branch": branch,
        "main": r["main"],
        "needs_rename": bool(r["main"] and r["main"]["renamed"]),
        "actions": len(r["actions"]),
        "applied": r["applied"],
        "skipped": r["skipped"],
    }
