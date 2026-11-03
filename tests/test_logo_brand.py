"""Назва сайту vue-вайта: лого і всі згадки — з назви вітки.

Еталон — site_name.expected(branch): nwf-provub-cospubtenp-br-pt →
«Provub Cospubtenp» (колонка «Название» у ClickUp). Домен у цьому чеку
більше не бере участі: домени міняються, назва вайта стабільна.
"""
import os
import sys
import xml.etree.ElementTree as ET
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, load_check, run                   # noqa: E402

sys.path.insert(0, str(ROOT))

mod = load_check("logo_brand")
BRANCH = "nwf-provub-cospubtenp-br-pt"          # → «Provub Cospubtenp»
NAME = "Provub Cospubtenp"
LOGO = "src/assets/images/logo.svg"

TITLE = "Provub Cospubtenp — consultoria"


def _index(title: str) -> str:
    return (f'<!doctype html><html><head><title>{title}</title>'
            '<meta name="theme-color" content="#1e40af"></head><body></body></html>')

NAV = """<template>
  <header class="flex">
    <div class="flex-1 bg-zinc-900 py-4 px-4 flex items-center">
      <a href="/">
        {logo}
      </a>
    </div>
    <div class="bg-violet-500 flex items-center gap-6">
      <nav class="hidden lg:flex items-center gap-6"><a href="/sobre">Sobre</a></nav>
    </div>
  </header>
</template>"""

IMG = '<img src="/src/assets/images/77e03d37.png" alt="Provub Cospubtenp" class="h-8 md:h-10 w-auto" />'


def _files(logo_html: str = IMG, nav_path: str = "src/components/MainNavigation.vue",
           title: str = TITLE):
    return {"index.html": _index(title), nav_path: NAV.format(logo=logo_html)}


def _run(files, extra_paths=("src/assets/images/77e03d37.png",), branch=BRANCH):
    return mod.run_branch(dict(files), list(files) + list(extra_paths), branch)


def _fix(files, extra_paths=("src/assets/images/77e03d37.png",), branch=BRANCH):
    return {a["path"]: a for a in
            mod.fix_branch(dict(files), list(files) + list(extra_paths), branch)}


# ------------------------------------------------------------- детект знака
def test_raster_clipart_logo_is_flagged():
    issues = _run(_files())
    marks = [i for i in issues if "піктограма" in i["message"]]
    assert len(marks) == 1, issues
    assert marks[0]["severity"] == "error"
    assert "77e03d37.png" in marks[0]["message"], issues


NAME_SPAN = '<span class="font-bold text-zinc-100">Provub Cospubtenp</span>'


def test_svg_logo_with_branch_name_is_clean():
    logo = f'<img src="/{LOGO}" alt="X" class="h-8" />' + NAME_SPAN
    assert _run(_files(logo), extra_paths=(LOGO,)) == []


def test_inline_svg_logo_is_accepted():
    assert _run(_files('<svg viewBox="0 0 24 24"><path d="M0 0h24"/></svg>'
                       + NAME_SPAN)) == []


def test_text_logo_is_a_logo_too():
    assert _run(_files('<span class="text-white font-bold">Provub Cospubtenp</span>')) == []


def test_empty_home_link_is_flagged():
    issues = _run(_files("<!-- тут мало бути лого -->"))
    assert len(issues) == 1 and "немає" in issues[0]["message"], issues


def test_broken_src_is_flagged():
    issues = _run(_files('<img src="/src/assets/images/nema.png" />' + NAME_SPAN))
    assert [i for i in issues if "nema.png" in i["message"]], issues


def test_article_header_without_nav_is_not_the_site_header():
    files = {"src/pages/Post.vue":
             "<template><header><h1>Стаття</h1></header></template>"}
    assert mod.run_branch(dict(files), list(files), BRANCH) == []


def test_branch_without_a_derivable_name_is_skipped():
    # ні title (немає index), ні назви вітки (гола локаль) — чек мовчить
    files = {"src/components/MainNavigation.vue": NAV.format(logo=IMG)}
    assert _run(files, branch="br-pt") == []
    assert _fix(files, branch="br-pt") == {}


def test_title_head_beats_branch_name():
    # джерело назви — голова <title>, а не вітка (кейс «Motor de Classe»)
    files = _named("Motor de Classe",
                   title="Motor de Classe - Luxo discreto para cada viagem.")
    assert _run(files, extra_paths=(LOGO,), branch=BRANCH) == []
    wrong = _wrong_msgs("Provub Cospubtenp", BRANCH,
                        title="Motor de Classe - Luxo discreto para cada viagem.")
    assert len(wrong) == 1 and "Motor de Classe" in wrong[0]["message"], wrong
    assert _fix(files, branch="br-pt") == {}



def test_fix_writes_logo_wordmark_in_strict_latin():
    # title несе «Câmera Alves» (з â) — напис лого мусить бути «Camera Alves»;
    # латинське лого з тим самим іменем чек НЕ чіпає
    title = "Câmera Alves - fotografia de estúdio"
    ok = _named("Camera Alves", title=title)
    assert _run(ok, extra_paths=(LOGO,), branch=BRANCH) == []
    assert _fix(ok, extra_paths=(LOGO,), branch=BRANCH) == {}
    fixed = _fix(_named("Inonecaestrn", title=title), extra_paths=(LOGO,),
                 branch=BRANCH)["src/components/MainNavigation.vue"]["content"]
    assert "Camera Alves" in fixed, fixed
    assert "Câmera" not in fixed, "у написі лого не місце діакритиці"


def test_dead_template_tree_does_not_win_over_src():
    files = {"index.html": _index(TITLE),
             "pages/Header.vue": NAV.format(logo=IMG),
             "src/components/MainNavigation.vue": NAV.format(logo=IMG)}
    issues = mod.run_branch(dict(files), list(files), BRANCH)
    assert {i["path"] for i in issues} == {"src/components/MainNavigation.vue"}, issues


SIDEBAR = """<template>
  <div>
    <aside class="hidden lg:flex fixed left-0 bg-slate-50 flex-col items-center">
      <a href="/" class="w-12 h-12 rounded-lg flex items-center justify-center">
        <img src="/src/assets/images/671fca2e.png" alt="Silva" class="w-10 h-10" />
      </a>
      <nav class="flex flex-col gap-6"><a href="/sobre">Sobre</a></nav>
    </aside>
    <header class="lg:hidden bg-white flex items-center justify-between">
      <a href="/" class="flex items-center gap-2">
        <img src="/src/assets/images/671fca2e.png" alt="Praxis" class="w-9 h-9" />
        <span class="font-sans font-bold text-gray-900">Provub Cospubtenp</span>
      </a>
      <button aria-label="Menu">menu</button>
    </header>
  </div>
</template>"""


def test_sidebar_and_mobile_bar_are_both_logo_slots():
    files = {"index.html": _index(TITLE), "src/components/TopNav.vue": SIDEBAR}
    paths = list(files) + ["src/assets/images/671fca2e.png"]
    issues = mod.run_branch(dict(files), paths, BRANCH)
    # aside: кліпарт + немає назви; header: тільки кліпарт (назва вже
    # правильна — дорівнює назві вітки)
    assert len(issues) == 3, issues
    out = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), paths, BRANCH)}
    nav = out["src/components/TopNav.vue"]
    assert "671fca2e.png" not in nav, "кліпарт лишився в одному зі слотів"
    assert nav.count(f'src="/{LOGO}"') == 2, nav
    # aside отримав напис, у header він уже був — по одному на слот, без дублів
    assert nav.count(">Provub Cospubtenp<") == 2, nav


# ------------------------------------------------------- напис біля знака
def test_mark_without_name_is_flagged():
    issues = _run(_files(f'<img src="/{LOGO}" alt="X" class="h-8" />'),
                  extra_paths=(LOGO,))
    assert len(issues) == 1, issues
    assert "назв" in issues[0]["message"] and NAME in issues[0]["message"], issues


def test_fix_adds_the_wordmark_next_to_the_mark():
    nav = _fix(_files())["src/components/MainNavigation.vue"]["content"]
    assert f">{NAME}<" in nav, nav
    assert nav.index("<img") < nav.index(f">{NAME}<"), "назва має йти після знака"


def test_wordmark_is_light_on_a_dark_header():
    nav = _fix(_files())["src/components/MainNavigation.vue"]["content"]
    assert "text-zinc-100" in nav, nav          # шапка bg-zinc-900


def test_existing_name_is_not_duplicated():
    nav = _fix(_files(IMG + NAME_SPAN))["src/components/MainNavigation.vue"]["content"]
    assert nav.count(">Provub Cospubtenp<") == 1, nav
    assert f'src="/{LOGO}"' in nav, nav


def test_link_gets_layout_classes_only_when_the_name_is_added():
    nav = _fix(_files())["src/components/MainNavigation.vue"]["content"]
    assert 'href="/" class="inline-flex items-center gap-2"' in nav, nav


# --------------------------------------------------- назва ↔ назва вітки
GOOD_MARK = f'<img src="/{LOGO}" alt="X" class="h-8" />'


def _named(name: str, title: str = TITLE):
    return _files(GOOD_MARK + f'<span class="font-bold">{name}</span>', title=title)


def _wrong_msgs(name: str, branch: str = BRANCH, title: str = TITLE):
    issues = _run(_named(name, title=title), extra_paths=(LOGO,), branch=branch)
    return [i for i in issues if "чужа назва" in i["message"]]


def test_wrong_name_in_the_logo_is_flagged():
    msgs = _wrong_msgs("Inonecaestrn", "nwf-chovfuce-eszbufefaa-br-pt",
                       title="Chovfuce Eszbufefaa — consultoria")
    assert len(msgs) == 1, msgs
    assert "Chovfuce Eszbufefaa" in msgs[0]["message"], msgs
    assert "по всьому сайту" in msgs[0]["message"], msgs


def test_site_spelling_with_diacritics_is_the_same_name():
    # правопис сайту виграє: акцент не привід перейменовувати
    assert _wrong_msgs("Chovfuce Eszbuféfaa", "nwf-chovfuce-eszbufefaa-br-pt",
                       title="Chovfuce Eszbufefaa — consultoria") == []


def test_umlaut_and_ampersand_forms_are_the_same_name():
    title = "Müller & Keller — Treuhand"
    assert _wrong_msgs("Müller & Keller", "nwf-mueller-keller-ch-de",
                       title=title) == []
    assert _wrong_msgs("MÜLLER KELLER", "nwf-mueller-keller-ch-de",
                       title=title) == []


def test_computed_name_is_not_judged():
    assert _wrong_msgs("{{ t('nav.brand') }}") == []


def test_matching_name_is_left_alone_by_the_fix():
    assert _fix(_named(NAME), extra_paths=(LOGO,)) == {}


# --------------------------------------------------------------- автофікс
def test_fix_creates_svg_letter_mark_from_the_name():
    acts = _fix(_files())
    svg = acts[LOGO]["content"]
    ET.fromstring(svg)                                  # валідний XML
    assert "<text" in svg and re.search(r">P(?:C)?<", svg), \
        "знак має нести літеру(и) назви «Provub Cospubtenp»"
    import brand_mark
    assert svg == brand_mark.pick(_files(), BRANCH, base_color="#1e40af"), \
        "знак — детермінований brand_mark від theme-color вайта"


def test_fix_points_the_img_at_the_generated_logo_with_name_alt():
    nav = _fix(_files())["src/components/MainNavigation.vue"]["content"]
    assert f'src="/{LOGO}"' in nav, nav
    assert f'alt="{NAME}"' in nav, nav


def test_fix_is_idempotent():
    acts = _fix(_files())
    fixed = _files()
    fixed["src/components/MainNavigation.vue"] = \
        acts["src/components/MainNavigation.vue"]["content"]
    fixed[LOGO] = acts[LOGO]["content"]
    paths = list(fixed) + ["src/assets/images/77e03d37.png"]
    assert mod.fix_branch(dict(fixed), paths, BRANCH) == []


def test_autofix_rewrites_the_wrong_name_keeping_uppercase():
    files = _named("INONECAESTRN", title="Chovfuce Eszbufefaa — consultoria")
    branch = "nwf-chovfuce-eszbufefaa-br-pt"
    nav = _fix(files, extra_paths=(LOGO,), branch=branch)[
        "src/components/MainNavigation.vue"]["content"]
    assert ">CHOVFUCE ESZBUFEFAA<" in nav, nav


# ------------------------------------------- перейменування по всьому сайту
SITEWIDE = {
    # title несе СПРАВЖНЮ назву (він і є джерелом); чужа — в og і в тілі
    "index.html": ('<!doctype html><html><head><title>Chovfuce Eszbufefaa — '
                   'consultoria</title><meta name="theme-color" content="#1e40af">'
                   '<meta property="og:site_name" content="Inonecaestrn">'
                   '</head><body></body></html>'),
    "src/components/MainNavigation.vue": NAV.format(
        logo=GOOD_MARK + '<span class="font-bold">Inonecaestrn</span>'),
    "src/components/BottomSection.vue": (
        "<template><footer><p>© 2026 Inonecaestrn. Направо.</p>"
        '<a href="https://facebook.com/inonecaestrn">FB</a>'
        "</footer></template>"),
    "src/data/texts.ts": 'export const hero = "Na Inonecaestrn, cada projeto conta";',
}


def test_fix_renames_the_wrong_name_across_the_whole_site():
    branch = "nwf-chovfuce-eszbufefaa-br-pt"
    paths = list(SITEWIDE) + [LOGO]
    acts = {a["path"]: a for a in
            mod.fix_branch(dict(SITEWIDE), paths, branch)}
    assert "index.html" in acts and "src/data/texts.ts" in acts, sorted(acts)
    idx = acts["index.html"]["content"]
    assert "<title>Chovfuce Eszbufefaa — consultoria</title>" in idx, idx
    assert 'content="Chovfuce Eszbufefaa"' in idx, idx
    foot = acts["src/components/BottomSection.vue"]["content"]
    assert "© 2026 Chovfuce Eszbufefaa." in foot, foot
    assert "facebook.com/inonecaestrn" in foot, "соцлінк зіпсовано"
    ts = acts["src/data/texts.ts"]["content"]
    assert "Na Chovfuce Eszbufefaa, cada projeto" in ts, ts
    nav = acts["src/components/MainNavigation.vue"]["content"]
    assert nav.count(">Chovfuce Eszbufefaa<") == 1 and "Inonecaestrn" not in nav, nav


def test_sitewide_rename_is_idempotent():
    branch = "nwf-chovfuce-eszbufefaa-br-pt"
    paths = list(SITEWIDE) + [LOGO]
    acts = {a["path"]: a for a in mod.fix_branch(dict(SITEWIDE), paths, branch)}
    fixed = dict(SITEWIDE)
    for p, a in acts.items():
        if a["type"] == "edit":
            fixed[p] = a["content"]
    assert mod.fix_branch(dict(fixed), paths, branch) == []
    assert mod.run_branch(dict(fixed), paths, branch) == []


def test_check_is_registered_for_node_only():
    assert mod.PROJECTS == ["node"], mod.PROJECTS
    assert mod.GROUP == "auto"


# -------------------------------------- строго латинський напис (01.10)
ACC_BRANCH = "nwf-paruino-proge-br-pt"           # → «Paruíno Progé» у title
ACC_TITLE = "Paruíno Progé — reservas"
ACC_SLOT = ('<img src="/src/assets/images/logo.svg" alt="Paruíno Progé" '
            'class="h-9 w-auto" /><span class="font-bold">Paruíno Progé</span>')


def test_diacritics_in_logo_name_are_flagged():
    files = _files(ACC_SLOT, title=ACC_TITLE)
    issues = _run(files, extra_paths=("src/assets/images/logo.svg",),
                  branch=ACC_BRANCH)
    assert len(issues) == 1, issues
    m = issues[0]["message"]
    assert "не строгою латиницею" in m and "íé" in m, m
    assert "Paruino Proge" in m, m
    assert issues[0]["severity"] == "error"


def test_fix_latinizes_logo_name_but_not_title():
    files = _files(ACC_SLOT, title=ACC_TITLE)
    paths = list(files) + ["src/assets/images/logo.svg"]
    acts = {a["path"]: a for a in
            mod.fix_branch(dict(files), paths, ACC_BRANCH)}
    nav = acts["src/components/MainNavigation.vue"]["content"]
    assert ">Paruino Proge</span>" in nav, nav
    assert 'alt="Paruino Proge"' in nav
    # title сайту НЕ чіпається — латинізується лише напис лого
    assert "index.html" not in acts
    # ідемпотентність: після фікса — тиша
    fixed = dict(files); fixed["src/components/MainNavigation.vue"] = nav
    assert mod.run_branch(dict(fixed), paths, ACC_BRANCH) == []
    assert mod.fix_branch(dict(fixed), paths, ACC_BRANCH) == []


def test_plain_ascii_name_is_not_flagged_as_nonlatin():
    files = _files('<img src="/src/assets/images/logo.svg" alt="Praxis" '
                   'class="h-8" /><span>Provub Cospubtenp</span>')
    issues = _run(files, extra_paths=("src/assets/images/logo.svg",))
    assert issues == [], issues


def test_emoji_decor_survives_and_is_not_flagged():
    # кейс revl-seok 01.10: емодзі в написі — декор, не «нелатинська буква»
    clean = _files('<img src="/src/assets/images/logo.svg" alt="x" '
                   'class="h-8" /><span>🔒 Provub Cospubtenp</span>')
    assert _run(clean, extra_paths=("src/assets/images/logo.svg",)) == []
    # а діакритика ПОРЯД з емодзі ловиться, фікс лишає емодзі на місці
    files = _files('<img src="/src/assets/images/logo.svg" alt="Paruíno Progé" '
                   'class="h-9" /><span>🔒 Paruíno Progé</span>',
                   title=ACC_TITLE)
    paths = list(files) + ["src/assets/images/logo.svg"]
    issues = mod.run_branch(dict(files), paths, ACC_BRANCH)
    assert len(issues) == 1 and "íé" in issues[0]["message"]
    assert "🔒" not in issues[0]["message"].split("«")[2]
    acts = {a["path"]: a for a in mod.fix_branch(dict(files), paths, ACC_BRANCH)}
    nav = acts["src/components/MainNavigation.vue"]["content"]
    assert ">🔒 Paruino Proge</span>" in nav, nav


if __name__ == "__main__":
    run(dict(globals()))
