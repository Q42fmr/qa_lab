"""faq_accordion: акордеон є, а JS, що знімає hidden, мертвий.

Кейси зняті з реальної вітки fettmagv-ch-ch-de-2 (скарга 13.10: «Вопросы FAQ
не раскрываются по клику. Где: на главной»): масова заміна адреси перетворила
член об'єктного літерала на рядок без двокрапки —

    "flottillenreise-einzelplatz":"p11.jpg" → "flottillenreise-Engelplatz 1.jpg"

SyntaxError вбиває site.js цілком, разом з обробником акордеона.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                       # noqa: E402

fa = load_check("faq_accordion")

# скорочена, але структурно точна копія site.js вітки: обробник акордеона +
# каталоги кошика IMG/HREF; у IMG заміна з'їла межу ключ/значення
HANDLER = (
    "document.querySelectorAll('.cs-acc__b').forEach(function(b){"
    "b.addEventListener('click',function(){"
    "var p=document.getElementById(b.getAttribute('aria-controls')),"
    "e=b.getAttribute('aria-expanded')==='true';"
    "b.setAttribute('aria-expanded',String(!e));"
    "if(p){if(e)p.setAttribute('hidden','');else p.removeAttribute('hidden');}"
    "});});")

BROKEN_IMG = ('var IMG={"skipper-charter-revierwahl":"p8.jpg",'
              '"flottillenreise-westmittelmeer":"p9.jpg",'
              '"flottillenreise-ostmittelmeer":"p10.jpg",'
              '"flottillenreise-Engelplatz 1.jpg",'
              '"flottillenreise-anschlussprogramm":"p12.jpg"}')
HREF_MAP = ('HREF={"skipper-charter-revierwahl":"a.html",'
            '"flottillenreise-westmittelmeer":"b.html",'
            '"flottillenreise-ostmittelmeer":"c.html",'
            '"flottillenreise-einzelplatz":"d.html",'
            '"flottillenreise-anschlussprogramm":"e.html"}')

BROKEN_JS = ("/* kit */\n(function(){'use strict';\n" + HANDLER + "\n})();\n"
             "(function(){'use strict';\n"
             + BROKEN_IMG + "," + HREF_MAP + ";\n})();\n")
FIXED_MEMBER = '"flottillenreise-einzelplatz":"p11.jpg"'


def faq_page(script="./assets/js/site.js", hidden=True, n=2):
    items = "".join(
        f'<h3><button class="cs-acc__b" type="button" aria-expanded="false" '
        f'aria-controls="fh-{i}"><span>Frage {i}?</span></button></h3>'
        f'<div class="cs-acc__p" id="fh-{i}"{" hidden" if hidden else ""}>'
        f'<p>Antwort {i}.</p></div>'
        for i in range(n))
    return ("<!DOCTYPE html><html><head><title>t</title></head><body>\n"
            f'<div class="cs-acc">{items}</div>\n'
            f'<script src="{script}" defer></script>\n'
            "</body></html>\n")


def branch(js=BROKEN_JS, page=None):
    files = {"index.php": page if page is not None else faq_page(),
             "assets/js/site.js": js}
    return files, list(files)


# ---------------------------------------------------------------- детект
def test_fettmagv_pattern_is_flagged_as_error():
    files, ap = branch()
    issues = fa.run_branch(files, ap, "fettmagv-ch-ch-de-2")
    assert len(issues) == 1, issues
    it = issues[0]
    assert it["path"] == "assets/js/site.js", it
    assert it["severity"] == "error", it
    assert "flottillenreise-Engelplatz 1.jpg" in it["message"], it
    assert "index.php" in it["message"], it
    assert it["line"] == 6, it           # рядок з var IMG={...}


def test_healthy_js_is_not_flagged():
    healthy = BROKEN_JS.replace('"flottillenreise-Engelplatz 1.jpg"',
                                FIXED_MEMBER)
    files, ap = branch(js=healthy)
    assert fa.run_branch(files, ap, "x") == []


def test_broken_js_nobody_loads_is_warn():
    files, ap = branch(page=faq_page(script="./assets/js/other.js"))
    files["assets/js/other.js"] = "var x=1;"
    ap = list(files)
    issues = fa.run_branch(files, ap, "x")
    sev = {it["path"]: it["severity"] for it in issues}
    assert sev.get("assets/js/site.js") == "warn", issues


def test_missing_script_on_accordion_page_is_error():
    files = {"faq/index.html": faq_page(script="../assets/js/site.js")}
    issues = fa.run_branch(files, list(files), "x")
    assert len(issues) == 1, issues
    assert issues[0]["path"] == "faq/index.html", issues
    assert issues[0]["severity"] == "error", issues
    assert "assets/js/site.js" in issues[0]["message"], issues


def test_missing_script_without_accordion_is_quiet():
    """Биті src без акордеона — не наш симптом (на те є інші чеки)."""
    page = faq_page(script="./gone.js").replace(' hidden>', '>')
    files = {"index.php": page}
    assert fa.run_branch(files, list(files), "x") == []


def test_external_and_php_src_are_skipped():
    page = faq_page(script="https://cdn.example.com/x.js")
    files = {"index.php": page, "assets/js/site.js": "var a=1;"}
    issues = fa.run_branch(files, list(files), "x")
    assert issues == [], issues


def test_panels_without_hidden_are_not_accordion():
    """Без hidden панелі видимі — «не розкривається» неможливе."""
    files = {"index.php": faq_page(script="./gone.js", hidden=False)}
    assert fa.run_branch(files, list(files), "x") == []


def test_details_faq_needs_no_js():
    page = ("<html><body><details><summary>Frage?</summary>"
            "<p>Antwort.</p></details></body></html>")
    files = {"faq/index.html": page}
    assert fa.run_branch(files, list(files), "x") == []


def test_broken_inline_script_is_flagged_on_page():
    page = faq_page().replace(
        '<script src="./assets/js/site.js" defer></script>',
        "<script>" + BROKEN_IMG + "," + HREF_MAP + ";</script>")
    files = {"index.php": page}
    issues = fa.run_branch(files, list(files), "x")
    assert len(issues) == 1, issues
    assert issues[0]["path"] == "index.php", issues
    assert issues[0]["severity"] == "error", issues


def test_ldjson_is_not_scanned_as_js():
    page = faq_page(script="./a.js") + (
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","name":"x"}</script>')
    files = {"index.php": page, "a.js": "var a=1;"}
    assert fa.run_branch(files, list(files), "x") == []


# ------------------------------------------------------- сканер: не фолсить
def test_scanner_ignores_legal_constructs():
    ok = [
        'var a = ["x", "y", "z"];',                         # масив рядків
        'f("a", "b");',                                     # аргументи
        'var o = {a, b};',                                  # шортхенд
        'switch(x){ case 1: { "use strict"; } }',           # блок після case
        'var o = {"k":"a"+"b","q":c?"x":"y","z":"1"};',     # вирази-значення
        'var s = `hi ${ {"a":"b","c":"d"} } bye`;',         # об\'єкт у шаблоні
        'var r=s.replace(/"/g,"&quot;").replace(/\'/g,"x");',  # лапки в regex
        'var o = {"k1":"v1","k2":"v2"}; // {"lone"}',       # комент
        'return {"a":"1","b":"2"};',
    ]
    for code in ok:
        lones, _ = fa.scan_js(code)
        assert lones == [], (code, lones)


def test_lone_member_needs_data_map_siblings():
    """Один рядок у «об'єкті» без 2+ справних пар — не наш слід."""
    lones, _ = fa.scan_js('var o = {"alone"};')
    assert lones == []


# ---------------------------------------------------------------- автофікс
def _fb_js(js, pages=None):
    """fix_branch над js + сторінками: (новий js-шлях, вміст, дії)."""
    files = {"assets/js/site.js": js}
    files.update(pages or {})
    acts = fa.fix_branch(dict(files), list(files), "x-ch-de")
    created = next((a for a in acts if a["type"] == "create"), None)
    return created, acts


def test_fix_reconstructs_member_exactly():
    created, acts = _fb_js(BROKEN_JS)
    assert created, acts
    fixed = created["content"]
    assert FIXED_MEMBER in fixed, fixed
    assert "Engelplatz 1.jpg" not in fixed
    lones, _ = fa.scan_js(fixed)
    assert lones == []
    # ідемпотентність: полагоджений js під новим ім'ям дій не породжує
    healed = {created["path"]: fixed}
    assert fa.fix_branch(dict(healed), list(healed), "x-ch-de") == []


def test_repaired_js_gets_hashed_name_and_refs_retarget():
    """02.10 (sozsazdacg): фікс пройшов, а домен показує стару поведінку —
    битий site.js сидить у браузер/CDN-кеші. Полагоджений js мусить
    змінити АДРЕСУ (site-<crc8>.js) і перетягнути всі посилання."""
    page = ('<html><body><h3>FAQ</h3>'
            '<script src="../assets/js/site.js" defer></script>'
            "</body></html>")
    created, acts = _fb_js(BROKEN_JS, {"faq/index.html": page})
    assert created and re.fullmatch(r"assets/js/site-[0-9a-f]{8}\.js",
                                    created["path"]), created
    kinds = {(a["type"], a["path"]) for a in acts}
    assert ("delete", "assets/js/site.js") in kinds, acts
    edited = next(a for a in acts if a["type"] == "edit"
                  and a["path"] == "faq/index.html")
    assert f'src="../{created["path"]}"' in edited["content"], \
        edited["content"]
    assert "site.js" not in edited["content"].replace(created["path"], "")


def test_fix_falls_back_to_deletion_without_evidence():
    """Немає сусідньої мапи з ключем — член видаляється разом з комою."""
    js = 'var IMG={"a":"p1.jpg","b":"p2.jpg","broken x.jpg","c":"p4.jpg"};'
    created, _ = _fb_js(js)
    assert created["content"] == \
        'var IMG={"a":"p1.jpg","b":"p2.jpg","c":"p4.jpg"};', created


def test_fix_deletes_when_value_gap_is_ambiguous():
    js = ('var IMG={"a":"p1.jpg","b":"p5.jpg","broken x.jpg","c":"p12.jpg"},'
          'HREF={"a":"1.html","b":"2.html","broken-key":"3.html",'
          '"c":"4.html"};')
    created, _ = _fb_js(js)
    fixed = created["content"]
    assert '"broken x.jpg"' not in fixed, fixed
    assert '"broken-key":"3.html"' in fixed            # сусідню мапу не чіпає
    lones, _ = fa.scan_js(fixed)
    assert lones == []


def test_fix_repairs_inline_script_in_page():
    page = faq_page().replace(
        '<script src="./assets/js/site.js" defer></script>',
        "<script>" + BROKEN_IMG + "," + HREF_MAP + ";</script>")
    fixed = fa.fix("index.php", page)
    assert FIXED_MEMBER in fixed, fixed
    assert "<h3>" in fixed and "</body>" in fixed      # розмітка неторкана


def test_fix_leaves_healthy_files_alone():
    healthy = BROKEN_JS.replace('"flottillenreise-Engelplatz 1.jpg"',
                                FIXED_MEMBER)
    assert fa.fix("assets/js/site.js", healthy) == healthy
    page = faq_page()
    assert fa.fix("index.php", page) == page


if __name__ == "__main__":
    run(dict(globals()))
