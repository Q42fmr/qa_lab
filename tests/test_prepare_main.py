"""Підготовка головної сторінки під скрипт-заміну форми.

Головний контракт: те, що вставляє prepare_main, мусить проходити звірку
checks/php_scripts.py без жодного зауваження — інакше еталон і вставка
розійдуться, і фікс сам створюватиме роботу для review-чека.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, load_check, run, standard_index  # noqa: E402

sys.path.insert(0, str(ROOT))
import prepare_main as pm                                   # noqa: E402

php_scripts = load_check("php_scripts")

RAW_HTML = """<!DOCTYPE html>
<html lang="pt-br"><head>
<meta charset="utf-8">
<title>White</title>
</head>
<body>
<h1>Landing</h1>
<form class="uxsq" action="thank-you.html" method="get" novalidate>
  <input name="name" placeholder="Nome">
  <input name="email" placeholder="E-mail">
  <textarea name="message"></textarea>
</form>
<a href="index.html">Home</a>
<a href="contact.html">Contact</a>
</body></html>
"""


def test_prepared_index_is_a_stub_without_lead_php():
    """Новий контракт (20.10): головна готується у режимі form_stub —
    форма отримує data-<id> і скрипт-варіант, лід-PHP (пікселі+redirect)
    вирізано. php_scripts мовчить, бо впізнає заглушку структурно."""
    import checks.form_stub as fs
    src = standard_index(RAW_HTML)                       # головна «як з деплою»
    out, log = pm.prepare_index(src, branch="aebneunir-br-pt")
    assert fs.is_stubbed(out) and fs.STUB_FORM_RX.search(out)
    assert "isset($_GET['email'])" not in out and "$returnPage" not in out
    assert "$trackingConfig = [" in out and "fbq('init'" in out, "трекінг переглядів лишається"
    assert php_scripts.run("index.php", out) == []
    assert log["php_stripped"] >= 1 and log["forms"] == 1 and log["variant"] in range(50)
    # лише PHP / лише форма — незалежні прапорці
    only_php, lg = pm.prepare_index(src, forms=False, branch="aebneunir-br-pt")
    assert "isset($_GET['email'])" not in only_php and not fs.is_stubbed(only_php) and lg["forms"] == 0
    only_form, lg = pm.prepare_index(src, blocks=False, branch="aebneunir-br-pt")
    assert "isset($_GET['email'])" in only_form and fs.is_stubbed(only_form) and lg["php_stripped"] == 0


# ---------------------------------------------------------------- лінки
def test_home_links_from_root():
    src = ('<a href="index.html">a</a><a href="./index.html">b</a>'
           '<a href="/index.html">c</a>')
    out, n = pm.rewrite_home_links(src, "index.php")
    assert n == 3
    assert 'href="./"' in out and 'href="/"' in out
    assert "index.html" not in out


def test_home_links_keep_anchor_and_query():
    out, n = pm.rewrite_home_links('<a href="index.html#contact">a</a>', "index.php")
    assert n == 1 and 'href="./#contact"' in out, out


def test_subpage_index_html_is_not_touched():
    """./blog/index.html — це підсторінка, не головна."""
    src = '<a href="blog/index.html">b</a><a href="./cursos/index.html">c</a>'
    assert pm.rewrite_home_links(src, "index.php") == (src, 0)


def test_home_links_from_subdir_are_depth_aware():
    src = '<a href="../index.html">home</a><a href="index.html">sibling</a>'
    out, n = pm.rewrite_home_links(src, "blog/post.html")
    assert n == 1, out
    assert 'href="../"' in out
    # 'index.html' з blog/ означає blog/index.html — не чіпаємо
    assert 'href="index.html"' in out


def test_home_links_from_depth_two():
    out, n = pm.rewrite_home_links('<a href="../../index.html">h</a>',
                                   "a/b/page.html")
    assert n == 1 and 'href="../../"' in out, out


def test_og_url_content_is_rewritten_too():
    out, n = pm.rewrite_home_links('<meta property="og:url" content="index.html">',
                                   "index.php")
    assert n == 1 and 'content="./"' in out


def test_prepare_index_options_off_change_nothing():
    out, log = pm.prepare_index(RAW_HTML, blocks=False, forms=False, links=False)
    assert out == RAW_HTML
    assert log == {"php_stripped": 0, "forms": 0, "variant": None, "links": 0}


# ---------------------------------------------------------------- вітка
def test_main_page_prefers_php_over_html():
    main, html = pm._main_page(["index.php", "index.html", "css/a.css"])
    assert main == "index.php" and html is None


def test_main_page_html_only_is_rename_candidate():
    main, html = pm._main_page(["index.html", "contact.html"])
    assert main == "index.html" and html == "index.html"


def test_main_page_ignores_subdir_index():
    main, html = pm._main_page(["blog/index.html", "css/a.css"])
    assert main is None and html is None


def _fake_branch(files: dict, ptype: str = "php"):
    """Підміняє знімок вітки на словник {шлях: текст}, а тип проєкту — на
    `ptype` (реєстр проєктів будує app.py на старті; тут його немає)."""
    saved = (runner.snapshot_files, runner.read_snapshot_file, projects.ptype)
    runner.snapshot_files = lambda br: list(files)
    runner.read_snapshot_file = lambda br, p: files[p].encode("utf-8")
    projects.ptype = lambda: ptype
    return saved


def _restore(saved):
    runner.snapshot_files, runner.read_snapshot_file, projects.ptype = saved


import projects                                             # noqa: E402
import runner                                               # noqa: E402


def test_compute_fixes_renames_and_rewrites_siblings():
    saved = _fake_branch({
        "index.html": RAW_HTML,
        "contact.html": '<a href="index.html">Home</a><form action="x" method="post">',
        "blog/post.html": '<a href="../index.html">Home</a>',
        "css/style.css": "a{color:red}",
    })
    try:
        r = pm.compute_fixes("br")
    finally:
        _restore(saved)

    kinds = {(a["type"], a["path"]) for a in r["actions"]}
    assert ("create", "index.php") in kinds
    assert ("delete", "index.html") in kinds
    assert ("edit", "contact.html") in kinds
    assert ("edit", "blog/post.html") in kinds
    assert not any(p.endswith(".css") for _, p in kinds), "css не чіпаємо"

    created = next(a["new"] for a in r["actions"] if a["path"] == "index.php")
    import checks.form_stub as fs
    assert fs.is_stubbed(created) and fs.STUB_FORM_RX.search(created)
    assert php_scripts.run("index.php", created) == []
    assert "action=" not in created.split("<form", 1)[1].split(">")[0]

    contact = next(a["new"] for a in r["actions"] if a["path"] == "contact.html")
    assert 'href="./"' in contact
    # форму сусідньої сторінки НЕ чіпаємо — наш скрипт лише на головній
    assert 'action="x"' in contact

    post = next(a["new"] for a in r["actions"] if a["path"] == "blog/post.html")
    assert 'href="../"' in post
    assert r["main"] == {"from": "index.html", "to": "index.php", "renamed": True}


def test_compute_fixes_existing_php_only_stubs():
    """index.php уже є — не переіменовуємо; на головній робимо заглушку."""
    saved = _fake_branch({"index.php": RAW_HTML.replace("index.html", "./")})
    try:
        r = pm.compute_fixes("br")
    finally:
        _restore(saved)
    paths = [a["path"] for a in r["actions"] if a["type"] == "edit"]
    assert "index.php" in paths
    assert r["main"]["renamed"] is False


def test_compute_fixes_is_idempotent_on_prepared_branch():
    once = None
    saved = _fake_branch({"index.html": RAW_HTML})
    try:
        r = pm.compute_fixes("br")
        once = next(a["new"] for a in r["actions"] if a["path"] == "index.php")
    finally:
        _restore(saved)
    saved = _fake_branch({"index.php": once})
    try:
        r2 = pm.compute_fixes("br")
    finally:
        _restore(saved)
    assert r2["actions"] == [], r2["applied"]


def test_compute_fixes_rename_disabled_reports_skip():
    saved = _fake_branch({"index.html": RAW_HTML})
    try:
        r = pm.compute_fixes("br", rename=False)
    finally:
        _restore(saved)
    assert not any(a["type"] == "create" for a in r["actions"])
    assert any("перейменування" in s["what"] for s in r["skipped"]), r["skipped"]


def test_compute_fixes_without_index_reports_skip():
    saved = _fake_branch({"blog/index.html": RAW_HTML})
    try:
        r = pm.compute_fixes("br")
    finally:
        _restore(saved)
    assert r["actions"] == [] and r["main"] is None
    assert any("index.php/index.html" in s["why"] for s in r["skipped"])


VUE_INDEX = """<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8"><title>White</title></head>
<body><div id="app"></div><script type="module" src="/src/main.js"></script></body>
</html>
"""


def test_compute_fixes_refuses_on_node_project():
    """Кейс 14.10: на vue-вітках інструмент перейменував вхід vite
    index.html → index.php, і 11 nwf-віток перестали збиратись. На php-проєкті
    з тим самим знімком він готує саме ці дії (create index.php + delete
    index.html), тож відмову дає тип проєкту, а не вміст вітки."""
    files = {"index.html": VUE_INDEX, "vite.config.js": "export default {}",
             "scripts/inject-php.cjs": "// php у dist/index.html"}
    saved = _fake_branch(files, ptype="node")
    try:
        try:
            pm.compute_fixes("br")
        except ValueError as e:
            msg = str(e)
        else:
            raise AssertionError("на node-проєкті compute_fixes мав відмовити")
    finally:
        _restore(saved)
    assert msg == pm.NODE_REFUSAL
    assert "index.html" in msg and "vite" in msg, msg

    saved = _fake_branch(files, ptype="php")
    try:
        r = pm.compute_fixes("br")
    finally:
        _restore(saved)
    kinds = {(a["type"], a["path"]) for a in r["actions"]}
    assert {("create", "index.php"), ("delete", "index.html")} <= kinds, kinds


if __name__ == "__main__":
    run(dict(globals()))
