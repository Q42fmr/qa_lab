"""Точка входу зібраного node-вайта: index.html АБО index.php.

Nuxt/Next кладуть у dist/ index.html. Вайти на vite-ssg збираються через
`vite build && node scripts/inject-php.cjs`, і цей постбілд-скрипт ВИДАЛЯЄ
dist/index.html, лишаючи dist/index.php (у Vite не можна тримати <?php у
джерелі index.html — parse5 його не приймає). Деплой, який вимагав саме
index.html, падав на успішному білді з «nuxt generate не створив
dist/index.html», а SPA-роутер віддав би index.php як ТЕКСТ — з голим
кодом трекінгу назовні.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                               # noqa: E402

sys.path.insert(0, str(ROOT))
import deployer                                              # noqa: E402


def _dist(*names: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix="wp-dist-"))
    for n in names:
        (d / n).write_text(f"<!-- {n} -->", encoding="utf-8")
    return d


def test_html_entry_is_found():
    d = _dist("index.html")
    try:
        assert deployer.dist_entry(d).name == "index.html"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_php_entry_is_found_when_inject_php_renamed_it():
    d = _dist("index.php")
    try:
        assert deployer.dist_entry(d).name == "index.php"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_html_wins_when_both_exist():
    d = _dist("index.php", "index.html")
    try:
        assert deployer.dist_entry(d).name == "index.html"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_no_entry_at_all():
    d = _dist("robots.txt")
    try:
        assert deployer.dist_entry(d) is None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_error_message_names_both_entries():
    """Повідомлення мусить казати правду: чекали будь-яку з двох точок входу."""
    d = _dist("robots.txt")
    try:
        deployer.require_dist_entry(d)
    except RuntimeError as e:
        assert "index.html" in str(e) and "index.php" in str(e), e
    else:
        raise AssertionError("порожній dist мусить впасти")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_require_returns_entry_for_php_only_dist():
    d = _dist("index.php")
    try:
        assert deployer.require_dist_entry(d).name == "index.php"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------- живий php-роутер
PHP_ENTRY = "<?php $x = 'секрет'; ?>\n<html><body>ЗІБРАНО</body></html>\n"


def _serve(dist: Path, router: Path):
    port = deployer._free_port()
    proc = subprocess.Popen(
        [deployer.php_bin(), "-S", f"127.0.0.1:{port}", "-t", str(dist), str(router)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1).read()
            return proc, port
        except urllib.error.HTTPError:
            return proc, port
        except Exception:
            time.sleep(0.15)
    proc.kill()
    raise AssertionError("php -S не піднявся")


def _router_case(entry_name: str, entry_text: str, paths=("/", "/planos")):
    """Піднімає dist з однією точкою входу і повертає {path: тіло відповіді}."""
    if not deployer._php_available():
        return None                              # без php тест просто мовчить
    dist = Path(tempfile.mkdtemp(prefix="wp-dist-"))
    router = dist.parent / f"router-{dist.name}.php"
    try:
        (dist / entry_name).write_text(entry_text, encoding="utf-8")
        (dist / "assets").mkdir()
        (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
        router.write_text(deployer._SPA_ROUTER, encoding="utf-8")
        proc, port = _serve(dist, router)
        try:
            out = {}
            for p in paths:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{p}", timeout=5) as r:
                    out[p] = r.read().decode("utf-8", "replace")
            return out
        finally:
            proc.kill()
    finally:
        shutil.rmtree(dist, ignore_errors=True)
        router.unlink(missing_ok=True)


def test_router_executes_php_entry_and_does_not_leak_source():
    got = _router_case("index.php", PHP_ENTRY)
    if got is None:
        return
    for path, body in got.items():
        assert "ЗІБРАНО" in body, (path, body)
        assert "<?php" not in body, f"{path}: віддано ВИХІДНИЙ код php"
        assert "секрет" not in body, f"{path}: витік коду сторінки"


def test_router_still_serves_html_entry():
    got = _router_case("index.html", "<html><body>СТАТИКА</body></html>")
    if got is None:
        return
    for path, body in got.items():
        assert "СТАТИКА" in body, (path, body)


def test_router_serves_real_files_as_is():
    if not deployer._php_available():
        return
    dist = Path(tempfile.mkdtemp(prefix="wp-dist-"))
    router = dist.parent / f"router-{dist.name}.php"
    try:
        (dist / "index.php").write_text(PHP_ENTRY, encoding="utf-8")
        (dist / "robots.txt").write_text("User-agent: *", encoding="utf-8")
        router.write_text(deployer._SPA_ROUTER, encoding="utf-8")
        proc, port = _serve(dist, router)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/robots.txt", timeout=5) as r:
                assert r.read().decode() == "User-agent: *"
        finally:
            proc.kill()
    finally:
        shutil.rmtree(dist, ignore_errors=True)
        router.unlink(missing_ok=True)


if __name__ == "__main__":
    run(dict(globals()))
