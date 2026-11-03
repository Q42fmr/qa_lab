"""js_img_map: мініатюри з js-мапи вказують на файли, яких немає (13.10).

Партія ch-de (quugfihcinf, ervgezeaqo, regeqvupolzol, stovksemm,
lernatelier): кошик/merkliste рендерить мініатюри з js-мапи
`IMG={"slug":"p2.jpg",…}` + `src='../assets/img/'+IMG[slug]`, а на диску
лежать `assets/img/p2.svg` — усі мініатюри корзини 404. Статичні чеки
(media_integrity) js не читають, тож клас був сліпою зоною.

Фікс: якщо точного файла немає, а той самий stem існує РІВНО з одним іншим
розширенням — літерал у js переписується на реальне ім'я. Неоднозначність
чи повна відсутність — детект без фікса (замінити файл руками).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run

mod = load_check("js_img_map")

JS = ('(function(){var IMG={"kurs-a":"p1.jpg","kurs-b":"p2.jpg",'
      '"kurs-c":"p3.jpg"};\n'
      'ul.innerHTML=items.map(function(x){return \'<li><img src="../assets/'
      'img/\'+(IMG[x.slug]||"")+\'" alt=""></li>\'}).join("");})();')

PATHS = ["assets/js/site.js", "assets/img/p1.svg", "assets/img/p2.svg",
         "assets/img/p3.svg", "assets/img/logo.png", "merkliste/index.html"]


def _files():
    return {"assets/js/site.js": JS, "merkliste/index.html": "<html></html>"}


def test_missing_thumbs_are_flagged():
    issues = mod.run_branch(_files(), list(PATHS), "x-ch-de")
    assert issues, "биті мініатюри не видно"
    assert issues[0]["path"] == "assets/js/site.js"
    assert "p1.jpg" in issues[0]["message"]
    assert issues[0]["severity"] == "error"


def test_fix_bumps_js_name_and_retargets_pages():
    """Зміна вмісту js без зміни адреси невидима на проді (кеш домену,
    кейс lernatelier 13.10): виправлений js отримує hash-ім'я, старе
    видаляється, сторінки перетаргечуються з ../-префіксом."""
    files = {**_files(),
             "merkliste/index.html":
                 '<html><script src="../assets/js/site.js"></script></html>'}
    acts = mod.fix_branch(dict(files), list(PATHS), "x-ch-de")
    kinds = {a["type"]: a for a in acts}
    assert set(kinds) == {"create", "delete", "edit"}, acts
    import re as _re2
    new_path = kinds["create"]["path"]
    assert _re2.fullmatch(r"assets/js/site-[0-9a-f]{8}\.js", new_path), new_path
    out = kinds["create"]["content"]
    assert '"p1.svg"' in out and '"p2.svg"' in out and '"p3.svg"' in out
    assert ".jpg" not in out
    assert kinds["delete"]["path"] == "assets/js/site.js"
    page = kinds["edit"]["content"]
    assert f'src="../{new_path}"' in page, page
    # після фікса — тихо і нуль дій (нове дерево: js під новим ім'ям)
    healed_paths = [p for p in PATHS if p != "assets/js/site.js"] + [new_path]
    healed = {new_path: out, "merkliste/index.html": page}
    assert mod.run_branch(dict(healed), healed_paths, "x-ch-de") == []
    assert mod.fix_branch(dict(healed), healed_paths, "x-ch-de") == []


def test_existing_file_is_untouched():
    js = 'var a="logo.png";var b="assets/img/p1.svg";'
    files = {"assets/js/site.js": js}
    assert mod.run_branch(dict(files), list(PATHS), "x-ch-de") == []
    assert mod.fix_branch(dict(files), list(PATHS), "x-ch-de") == []


def test_ambiguous_stem_is_reported_not_fixed():
    paths = list(PATHS) + ["img/p2.webp"]          # p2 існує і .svg, і .webp
    js = 'var IMG={"kurs-b":"p2.jpg"};'
    files = {"assets/js/site.js": js}
    issues = mod.run_branch(dict(files), list(paths), "x-ch-de")
    assert issues and "неоднознач" in issues[0]["message"], issues
    assert mod.fix_branch(dict(files), list(paths), "x-ch-de") == []


def test_ghost_name_is_silent_vendor_noise():
    """Літерал без жодного кандидата — службовий шум бандлів (elementor,
    mercadopago, complianz на корпусі 13.10): не судиться і не чіпається."""
    js = 'var IMG={"kurs-x":"ghost.jpg"};'
    files = {"assets/js/site.js": js}
    assert mod.run_branch(dict(files), list(PATHS), "x-ch-de") == []
    assert mod.fix_branch(dict(files), list(PATHS), "x-ch-de") == []


def test_vendor_paths_are_skipped():
    paths = list(PATHS) + ["wp-content/plugins/x/y.js", "_external/cdn/z.js",
                           "assets/js/app.min.js"]
    js = 'var IMG={"kurs-b":"p2.jpg"};'
    files = {"wp-content/plugins/x/y.js": js, "_external/cdn/z.js": js,
             "assets/js/app.min.js": js}
    assert mod.run_branch(dict(files), list(paths), "x-ch-de") == []
    assert mod.fix_branch(dict(files), list(paths), "x-ch-de") == []


def test_urls_and_data_are_silent():
    js = ('var a="https://cdn.example.com/p9.jpg";'
          'var b="data:image/png;base64,AAAA";')
    files = {"assets/js/site.js": js}
    assert mod.run_branch(dict(files), list(PATHS), "x-ch-de") == []


def test_inline_script_in_html_is_covered():
    page = ('<html><body><script>var IMG={"kurs-b":"p2.jpg"};</script>'
            "</body></html>")
    files = {"merkliste/index.html": page}
    issues = mod.run_branch(dict(files), list(PATHS), "x-ch-de")
    assert issues and issues[0]["path"] == "merkliste/index.html"
    acts = mod.fix_branch(dict(files), list(PATHS), "x-ch-de")
    assert acts and '"p2.svg"' in acts[0]["content"]


if __name__ == "__main__":
    run(dict(globals()))
