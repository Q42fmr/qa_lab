"""Тести asset_base: відносні асети на вайті, який віддає дочірні URL.

Правило тримається на двох ногах: вітка МУСИТЬ віддавати дочірні URL (інакше
відносні шляхи коректні), і асет МУСИТЬ існувати за резолвом (інакше це битий
лінк, ним володіють css_integrity / media_integrity).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("asset_base")

ENTRY = "index.html"
ASSETS = ["css/style.css", "js/app.js", "images/logo.png"]


def _page(assets=None, links=("/imoveis/brasil/",)):
    assets = ASSETS if assets is None else assets
    head = "".join(
        (f'<link rel="stylesheet" href="{a}">' if a.endswith(".css") else
         f'<script src="{a}"></script>' if a.endswith(".js") else
         f'<img src="{a}">')
        for a in assets)
    nav = "".join(f'<a href="{h}">x</a>' for h in links)
    return f"<!DOCTYPE html><html><head>{head}</head><body>{nav}</body></html>"


def _branch(page=None, assets=None, extra=()):
    """files + all_paths: асети існують на диску, сторінка одна."""
    files = {ENTRY: _page() if page is None else page}
    paths = list(files) + list(ASSETS if assets is None else assets) + list(extra)
    return files, paths


def _run(files, paths):
    return mod.run_branch(dict(files), list(paths))


def _fix(files, paths):
    return {a["path"]: a["content"]
            for a in mod.fix_branch(dict(files), list(paths), "x-br-pt")}


# --------------------------------------------------------------- детект
def test_relative_assets_are_flagged_when_child_urls_exist():
    """Кейс chafelzibau-br-pt: заміряно рендером на `/imoveis/brasil/` —
    застосовано 0 з 12 таблиць стилів, шрифт браузерний Times New Roman."""
    files, paths = _branch()
    issues = _run(files, paths)
    assert len(issues) == 1, issues
    assert issues[0]["path"] == ENTRY and issues[0]["severity"] == "error", issues
    assert "/imoveis/brasil/" in issues[0]["message"], issues[0]["message"]


def test_root_absolute_assets_are_fine():
    files, paths = _branch(page=_page(assets=["/" + a for a in ASSETS]))
    assert _run(files, paths) == []
    assert _fix(files, paths) == {}


def test_a_real_subdirectory_page_is_not_a_child_url():
    """Лінк зсуває базу, АЛЕ файл під нього у вітці є - значить його віддає не
    catch-all, а сам сервер, і на тій сторінці відносні шляхи правильні.
    Ознака catch-all саме у відсутності файлу."""
    files, paths = _branch(page=_page(links=("/sub/page.html",)),
                           extra=("sub/page.html",))
    assert _run(files, paths) == []
    assert _fix(files, paths) == {}


def test_directory_index_counts_as_a_real_page():
    files, paths = _branch(page=_page(links=("/sub/",)),
                           extra=("sub/index.html",))
    assert _run(files, paths) == []


def test_only_relative_refs_are_candidates():
    """Контракт `_is_relative`: root-абсолютні, зовнішні, протокольні й
    data:-посилання браузер не резолвить від бази сторінки, тож вони не наша
    справа навіть до перевірки наявності файлу."""
    for v in ("css/x.css", "./css/x.css", "../css/x.css"):
        assert mod._is_relative(v) is True, v
    for v in ("/css/x.css", "https://cdn/x.css", "http://cdn/x.css",
              "//cdn/x.css", "data:text/css,body{}", "#anchor",
              "mailto:a@b.c", "tel:+1", "javascript:void(0)", ""):
        assert mod._is_relative(v) is False, v


def test_no_child_urls_means_no_issue():
    """Звичайний багатофайловий вайт: усі лінки ведуть на реальні файли, тож
    відносні шляхи коректні й чіпати їх нема за що."""
    files, paths = _branch(page=_page(links=("/about.html",)), extra=("about.html",))
    assert _run(files, paths) == []
    assert _fix(files, paths) == {}


def test_single_segment_url_without_slash_does_not_shift_the_base():
    """Заміряно на abzuiefe.sbs: `/administradora-de-condominios` (без слеша)
    лишає базу коренем і асети приїжджають (200), а `…/` (зі слешем) — ні."""
    files, paths = _branch(page=_page(links=("/kontakt",)))
    assert _run(files, paths) == []
    assert mod._shifts_base("/kontakt") is False
    assert mod._shifts_base("/kontakt/") is True
    assert mod._shifts_base("/a/b") is True


def test_multi_segment_url_shifts_the_base_even_without_a_slash():
    files, paths = _branch(page=_page(links=("/au/en/home",)))
    assert len(_run(files, paths)) == 1


def test_missing_asset_is_not_our_business():
    """Битий лінк лагодять css_integrity / media_integrity: якщо файлу немає,
    root-абсолютний шлях його не воскресить."""
    files, paths = _branch(page=_page(assets=["css/nope.css"]), assets=[])
    assert _run(files, paths) == []
    assert _fix(files, paths) == {}


def test_external_and_data_refs_are_left_alone():
    outside = ["https://cdn.example.com/a.css", "//cdn.example.com/b.js",
               "data:text/css,body{}"]
    files, paths = _branch(page=_page(assets=outside))
    assert _run(files, paths) == []


def test_only_the_entry_page_is_examined():
    """Catch-all віддає ЛИШЕ точку входу; справжня сторінка живе за своїм
    шляхом, де відносні посилання правильні. Інакше у 299-сторінковій вітці
    правка була б на 43410 посилань замість 114."""
    files, paths = _branch()
    files["sub/page.html"] = _page(assets=["../css/style.css"])
    paths.append("sub/page.html")
    issues = _run(files, paths)
    assert [i["path"] for i in issues] == [ENTRY], issues
    assert list(_fix(files, paths)) == [ENTRY]


def test_branch_without_an_entry_page_is_skipped():
    files = {"about.html": _page()}
    paths = list(files) + ASSETS
    assert _run(files, paths) == []
    assert _fix(files, paths) == {}


# ----------------------------------------------------------------- фікс
def test_fix_makes_paths_root_absolute():
    files, paths = _branch()
    out = _fix(files, paths)[ENTRY]
    for a in ASSETS:
        assert f'"/{a}"' in out, (a, out)
    assert _run({ENTRY: out}, paths) == []


def test_fix_covers_css_js_and_images():
    """У всіх 7 віток корпусу відносні і стилі, і скрипти, і картинки (до 129
    на сторінку) — полагодити лише css означало б лишити побиті картинки."""
    out = _fix(*_branch())[ENTRY]
    assert '"/css/style.css"' in out and '"/js/app.js"' in out
    assert '"/images/logo.png"' in out


def test_fix_normalises_dot_and_parent_segments():
    files, paths = _branch(page=_page(assets=["./css/style.css"]))
    out = _fix(files, paths)[ENTRY]
    assert '"/css/style.css"' in out, out


def test_fix_keeps_the_rest_of_the_markup():
    files, paths = _branch()
    out = _fix(files, paths)[ENTRY]
    assert out.count("<link") == 1 and out.count("<script") == 1
    assert 'href="/imoveis/brasil/"' in out or '<a href="/imoveis/brasil/"' in out


def test_fix_is_idempotent():
    files, paths = _branch()
    once = _fix(files, paths)
    assert mod.fix_branch(dict(once), list(paths), "x-br-pt") == []


def test_check_is_php_auto():
    assert mod.PROJECTS == ["php"], mod.PROJECTS
    assert mod.GROUP == "auto"


if __name__ == "__main__":
    run(dict(globals()))
