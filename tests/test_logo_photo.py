"""Тести logo_photo: <img> у home-лінку хедера/футера не мусить бути
стоковим фото; фікс веде src на робочу іконку (favicon.* з кореня вітки
або згенерований favicon.svg з літерою бренду)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("logo_photo")

HEADER_PHOTO = """<html><head><title>Rusveve — fotografia</title></head><body>
<header class="bg-x">
  <a href="./" class="flex items-center gap-3" aria-label="Rusveve">
    <img src="https://img.b2bpic.net/premium-photo/exec_223582-3036.jpg?w=740" alt="Rusveve" class="h-9 w-auto">
    <span class="font-serif font-700 text-xl">Rubricakil</span>
  </a>
</header>
<main><h1>x</h1></main>
</body></html>"""

FOOTER_PHOTO = """<html><body>
<header class="bg-x"><a href="./" class="flex"><span>Rubricakil</span></a></header>
<main><h1>x</h1></main>
<footer>
  <a href="./" class="flex items-center gap-2.5 mb-4" aria-label="Rusveve">
    <img src="https://img.b2bpic.net/premium-photo/risk_153608-76945.jpg?w=740" alt="Rusveve" class="h-8 w-auto brightness-0 invert">
    <span class="font-serif text-lg font-700">Rubricakil</span>
  </a>
</footer>
</body></html>"""


def _svg_page(src="logo.svg"):
    return f"""<html><body>
<header class="bg-x">
  <a href="./" class="flex"><img src="{src}" alt="Brand" class="h-9 w-auto"><span>Brand</span></a>
</header>
<main><h1>x</h1></main>
</body></html>"""


# ------------------------------------------------------------------- run

def test_header_photo_flagged():
    issues = mod.run_branch({"index.php": HEADER_PHOTO}, [], "br")
    assert len(issues) == 1, issues
    i = issues[0]
    assert i["path"] == "index.php"
    assert i["severity"] == "warn"
    assert "хедер" in i["message"]
    # маркер стоїть на <img>, а не на початку лінка — правити доведеться його
    assert i["line"] == HEADER_PHOTO[:HEADER_PHOTO.index("<img")].count("\n") + 1


def test_footer_photo_flagged():
    issues = mod.run_branch({"index.php": FOOTER_PHOTO}, [], "br")
    assert len(issues) == 1, issues
    assert "футер" in issues[0]["message"]


def test_both_header_and_footer_flagged():
    combo = HEADER_PHOTO.replace("</header>", "</header>") \
        + "<footer>" + FOOTER_PHOTO.split("<footer>", 1)[1]
    issues = mod.run_branch({"index.php": combo}, [], "br")
    zones = {i["message"].split("лого ", 1)[1].split(":", 1)[0] for i in issues}
    assert zones == {"хедер", "футер"}, issues


def test_svg_logo_is_silent():
    assert mod.run_branch({"index.php": _svg_page("logo.svg")}, [], "br") == []


def test_png_logo_is_silent():
    assert mod.run_branch({"index.php": _svg_page("assets/logo.png")}, [], "br") == []


def test_data_uri_logo_is_silent():
    assert mod.run_branch(
        {"index.php": _svg_page("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=")},
        [], "br") == []


def test_logo_without_img_is_silent():
    page = """<html><body><header><a href="./"><span>Brand</span></a></header>
<main><h1>x</h1></main></body></html>"""
    assert mod.run_branch({"index.php": page}, [], "br") == []


# ------------------------------------------------------------------- fix

def test_fix_targets_existing_root_favicon():
    files = {"index.php": HEADER_PHOTO}
    all_paths = ["index.php", "favicon.svg"]
    actions = mod.replace_actions(files, all_paths, "br")
    edits = [a for a in actions if a["type"] == "edit"]
    creates = [a for a in actions if a["type"] == "create"]
    assert len(edits) == 1 and not creates
    assert 'src="./favicon.svg"' in edits[0]["content"]
    assert "img.b2bpic.net" not in edits[0]["content"]
    assert mod.run_branch({"index.php": edits[0]["content"]}, all_paths, "br") == []


def test_fix_generates_favicon_with_brand_letter():
    files = {"index.php": HEADER_PHOTO}
    all_paths = ["index.php"]
    actions = mod.replace_actions(files, all_paths, "br")
    edits = [a for a in actions if a["type"] == "edit"]
    creates = [a for a in actions if a["type"] == "create"]
    assert len(edits) == 1 and len(creates) == 1
    assert creates[0]["path"] == "favicon.svg"
    assert ">R<" in creates[0]["content"], creates[0]["content"]
    assert 'src="./favicon.svg"' in edits[0]["content"]


def test_fix_strips_invert_classes_in_footer():
    files = {"index.php": FOOTER_PHOTO}
    all_paths = ["index.php", "favicon.svg"]
    actions = mod.replace_actions(files, all_paths, "br")
    edit = next(a for a in actions if a["type"] == "edit")
    assert "brightness-0" not in edit["content"]
    assert "invert" not in edit["content"]
    assert "h-8 w-auto" in edit["content"]


def test_fix_noop_on_svg_logo():
    assert mod.replace_actions({"index.php": _svg_page()}, ["index.php"], "br") == []


def test_fix_idempotent():
    files = {"index.php": HEADER_PHOTO}
    all_paths = ["index.php"]
    actions = mod.replace_actions(files, all_paths, "br")
    edit = next(a for a in actions if a["type"] == "edit")
    create = next(a for a in actions if a["type"] == "create")
    fixed_files = {"index.php": edit["content"], "favicon.svg": create["content"]}
    fixed_paths = ["index.php", "favicon.svg"]
    assert mod.run_branch(fixed_files, fixed_paths, "br") == []
    assert mod.replace_actions(fixed_files, fixed_paths, "br") == []


# ------------------------------------------------- інлайн-SVG бейдж (01.10)
BADGE_HEADER = """<html><head><title>Alnewvad Cinco</title>
<link rel="icon" type="image/svg+xml" href="./favicon.svg"></head><body>
<header class="bg-x">
  <a class="flex items-center gap-3" href="./">
    <svg viewBox="0 0 48 48" width="40" height="40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs><linearGradient id="badge-grad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#1B2A52"/><stop offset="1" stop-color="#E8B84B"/>
      </linearGradient></defs>
      <rect x="4" y="4" width="40" height="40" rx="10" fill="url(#badge-grad)"/>
      <text x="24" y="32" font-family="Anton" fill="#F0F4FF" text-anchor="middle">AC</text>
    </svg>
    <span class="font-display text-xl">Alnewvad Cinco</span>
  </a>
</header>
<main><h1>x</h1></main>
</body></html>"""


def test_generator_badge_is_flagged():
    issues = mod.run_branch({"index.php": BADGE_HEADER}, ["index.php"], "br")
    assert len(issues) == 1
    assert issues[0]["severity"] == "warn"
    assert "інлайн-SVG бейдж" in issues[0]["message"]


def test_fix_swaps_badge_for_img_and_keeps_name():
    files = {"index.php": BADGE_HEADER}
    actions = mod.replace_actions(files, ["index.php"], "br", version="abc123")
    edit = next(a for a in actions if a["type"] == "edit")
    create = next(a for a in actions if a["type"] == "create")
    assert create["path"] == "favicon.svg"
    out = edit["content"]
    assert "<svg" not in out.split("<main")[0]          # бейджа в хедері немає
    assert '<img src="./favicon.svg?v=abc123" alt="" width="40" height="40">' in out
    assert "Alnewvad Cinco</span>" in out               # назва-спан не чіпається


def test_badge_fix_is_idempotent():
    files = {"index.php": BADGE_HEADER}
    actions = mod.replace_actions(files, ["index.php"], "br")
    edit = next(a for a in actions if a["type"] == "edit")
    create = next(a for a in actions if a["type"] == "create")
    fixed = {"index.php": edit["content"], "favicon.svg": create["content"]}
    paths = ["index.php", "favicon.svg"]
    assert mod.run_branch(fixed, paths, "br") == []
    assert mod.replace_actions(fixed, paths, "br") == []


# ----------------------------------- назва жила у <text> бейджа (01.10)
NAME_IN_BADGE = """<html><head><title>Vermomao Madpa — consultoria</title></head><body>
<header class="bg-white">
  <a href="./" aria-label="Vermomao Madpa — página inicial" class="flex items-center gap-3">
    <svg viewBox="0 0 48 48" width="40" height="40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs><linearGradient id="hbg"><stop offset="0" stop-color="#1A6E9E"/></linearGradient></defs>
      <circle cx="24" cy="24" r="24" fill="url(#hbg)"/>
      <text x="24" y="30" font-family="Georgia, serif" font-size="18" fill="#F7FAFA">Vermomao Madpa</text>
    </svg>
    <span class="font-heading font-bold text-lg text-primary-900"></span>
  </a>
</header>
<main><h1>x</h1></main>
</body></html>"""


def test_badge_swap_moves_name_into_empty_span():
    files = {"index.php": NAME_IN_BADGE}
    actions = mod.replace_actions(files, ["index.php"], "br")
    out = next(a for a in actions if a["type"] == "edit")["content"]
    # назва з <text> бейджа переїхала у span з класами генератора — його
    # колір (text-primary-900) уже підібраний під фон хедера
    assert ('<span class="font-heading font-bold text-lg text-primary-900">'
            'Vermomao Madpa</span>') in out
    assert "<text" not in out.split("<main")[0]


def test_orphan_empty_span_is_flagged_and_healed():
    # слід СТАРОГО фікса: бейдж уже знесено разом з назвою, span порожній
    broken = """<html><head><title>Vermomao Madpa — x</title></head><body>
<header class="bg-white">
  <a href="./" aria-label="Vermomao Madpa — página inicial" class="flex">
    <img src="./favicon.svg?v=53f2ef1e" alt="" width="40" height="40">
    <span class="font-heading text-primary-900"></span>
  </a>
</header>
<main><h1>x</h1></main>
</body></html>"""
    files = {"index.php": broken}
    paths = ["index.php", "favicon.svg"]
    issues = mod.run_branch(dict(files), paths, "br")
    assert len(issues) == 1 and "порожній span" in issues[0]["message"]
    assert "Vermomao Madpa" in issues[0]["message"]
    actions = mod.replace_actions(dict(files), paths, "br")
    out = next(a for a in actions if a["type"] == "edit")["content"]
    assert ('<span class="font-heading text-primary-900">Vermomao Madpa'
            '</span>') in out
    # і більше нічого не мінялось: src як був
    assert 'src="./favicon.svg?v=53f2ef1e"' in out
    # після лікування — тиша і нуль дій
    healed = {"index.php": out}
    assert mod.run_branch(dict(healed), paths, "br") == []
    assert mod.replace_actions(dict(healed), paths, "br") == []


def test_monogram_badge_name_comes_from_aria():
    # у <text> лише монограма (≤2 символів) — назва береться з aria-label
    files = {"index.php": BADGE_HEADER.replace(
        '<a class="flex items-center gap-3" href="./">',
        '<a class="flex items-center gap-3" href="./" '
        'aria-label="Alnewvad Cinco — página inicial">').replace(
        '<span class="font-display text-xl">Alnewvad Cinco</span>',
        '<span class="font-display text-xl"></span>')}
    actions = mod.replace_actions(files, ["index.php"], "br")
    out = next(a for a in actions if a["type"] == "edit")["content"]
    assert ('<span class="font-display text-xl">Alnewvad Cinco</span>'
            in out), out

if __name__ == "__main__":
    run(dict(globals()))
