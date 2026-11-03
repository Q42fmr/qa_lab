"""Перемикач мови: підпис замінено назвою сайту (кейс QA 27.10,
tefluer-gechaoh-ch-fr). Контракти: мовний підпис — 2-3-літерний код
(опц. з регіоном) або власна назва мови; дефект — не мовний підпис,
що або довший за 20 символів, або містить назву сайту вітки; фікс
відновлює hreflang-код у стилі сусідів (lower/upper/повна назва);
без hreflang і мовного сегмента в href — лише «вручну».
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, load_check, run                     # noqa: E402

mod = load_check("lang_switcher")

BR = "tefluer-gechaoh-ch-fr"

SWITCHER = (
    '<ul class="language-switcher-language-links">'
    '<li><a class="language-link is-active" href="index.html" hreflang="en">{en}</a></li>'
    '<li class="dropdown-item"><a class="language-link" href="../de/index.html" hreflang="de">{de}</a></li>'
    '</ul>'
)


def _page(title, en, de="de"):
    body = SWITCHER.format(en=en, de=de)
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>"


def test_terroir_like_broken_switcher_flagged():
    files = {"a.html": _page("Terroir & Gestion Sàrl — Dossiers",
                              "Terroir & Gestion Sarl & Gestion Sarl")}
    issues = mod.run_branch(files, list(files), BR)
    assert len(issues) == 1, issues
    i = issues[0]
    assert i["path"] == "a.html" and i["severity"] in ("warn", "error")
    assert "Terroir & Gestion Sarl & Gestion Sarl" in i["message"]
    assert "«en»" in i["message"]


def test_fix_restores_en_keeping_attrs_and_siblings():
    files = {"a.html": _page("Terroir & Gestion Sàrl — Dossiers",
                              "Terroir & Gestion Sarl & Gestion Sarl")}
    acts = mod.fix_branch(dict(files), list(files), BR)
    assert len(acts) == 1 and acts[0]["path"] == "a.html"
    new = acts[0]["content"]
    assert ('<a class="language-link is-active" href="index.html" hreflang="en">en</a>'
            in new), new
    assert '<a class="language-link" href="../de/index.html" hreflang="de">de</a>' in new
    # ідемпотентність
    fixed = {"a.html": new}
    assert mod.run_branch(fixed, list(fixed), BR) == []
    assert mod.fix_branch(fixed, list(fixed), BR) == []


def test_fix_follows_uppercase_sibling_style():
    files = {"a.html": _page("Terroir & Gestion Sàrl — Dossiers",
                              "Terroir & Gestion Sarl & Gestion Sarl", de="DE")}
    acts = mod.fix_branch(dict(files), list(files), BR)
    new = acts[0]["content"]
    assert 'hreflang="en">EN</a>' in new, new


def test_fix_follows_full_name_sibling_style():
    files = {"a.html": _page("Terroir & Gestion Sàrl — Dossiers",
                              "Terroir & Gestion Sarl & Gestion Sarl", de="Deutsch")}
    acts = mod.fix_branch(dict(files), list(files), BR)
    new = acts[0]["content"]
    assert 'hreflang="en">English</a>' in new, new


def test_correct_switcher_stays_silent():
    files = {"a.html": _page("Terroir & Gestion Sàrl — Dossiers", "en", de="de")}
    assert mod.run_branch(files, list(files), BR) == []
    assert mod.fix_branch(files, list(files), BR) == []


def test_normal_short_language_label_stays_silent():
    page = ("<html><head><title>Mon Site</title></head><body>"
            '<nav class="lang-menu">'
            '<a hreflang="fr" href="/fr/">Version française</a>'
            '<a hreflang="en" href="/en/">English</a>'
            "</nav></body></html>")
    files = {"a.html": page}
    assert mod.run_branch(files, list(files), BR) == []
    assert mod.fix_branch(files, list(files), BR) == []


def test_no_switcher_no_issues():
    files = {"a.html": "<html><body><p>Terroir & Gestion Sarl & Gestion Sarl</p></body></html>"}
    assert mod.run_branch(files, list(files), BR) == []
    assert mod.fix_branch(files, list(files), BR) == []


def test_unescaped_angle_brackets_in_attrs_stay_silent():
    # cache/tefluer-gechaoh-ch-fr: data-drupal-link-system-path="<front>" —
    # необезпечений «<»/«>» у значенні атрибута ламає наївний [^>]* парсер
    # тега, і хвіст реальних атрибутів потрапляє в «текст» підпису
    page = (
        '<html><head><title>Mon Site</title></head><body>'
        '<ul aria-current="page" class="language-switcher-language-links" '
        'data-drupal-link-system-path="<front>" en"="" '
        'style="display: flex; flex-direction: row;>'
        '<li data-drupal-language="><a aria-current="page" '
        'class="language-link is-active" '
        'data-drupal-link-system-path="<front>" href="./" hreflang="en">en</a>'
        '<li class="dropdown-item" data-drupal-language="de" '
        'data-drupal-link-system-path="<front>">'
        '<a class="language-link" data-drupal-link-system-path="<front>" '
        'href="de/index.html" hreflang="de">de</a></li></ul>'
        '</body></html>'
    )
    files = {"a.html": page}
    assert mod.run_branch(files, list(files), BR) == []
    assert mod.fix_branch(files, list(files), BR) == []


def test_unescaped_angle_brackets_real_label_still_flagged():
    # той самий побитий <ul>/<li>, але підпис «en» таки замінено назвою
    # сайту — попри побиту розмітку довкола, справжня знахідка не губиться
    page = (
        '<html><head><title>Terroir Site</title></head><body>'
        '<ul aria-current="page" class="language-switcher-language-links" '
        'data-drupal-link-system-path="<front>" en"="" '
        'style="display: flex; flex-direction: row;>'
        '<li data-drupal-language="><a aria-current="page" '
        'class="language-link is-active" '
        'data-drupal-link-system-path="<front>" href="./" hreflang="en">'
        'Terroir Site Terroir Site Terroir Site</a>'
        '<li class="dropdown-item" data-drupal-language="de" '
        'data-drupal-link-system-path="<front>">'
        '<a class="language-link" data-drupal-link-system-path="<front>" '
        'href="de/index.html" hreflang="de">de</a></li></ul>'
        '</body></html>'
    )
    files = {"a.html": page}
    issues = mod.run_branch(files, list(files), BR)
    assert len(issues) == 1, issues
    assert "Terroir Site Terroir Site Terroir Site" in issues[0]["message"]
    acts = mod.fix_branch(dict(files), list(files), BR)
    assert len(acts) == 1
    assert 'hreflang="en">en</a>' in acts[0]["content"], acts[0]["content"]


def test_real_terroir_fixture_single_issue_and_matches_hand_fix():
    if not (ROOT / "_work" / "ref").is_dir():
        return      # локальні еталони реальних сторінок (_work/ref не в репо): у CI пропускаємо
    before = (ROOT / "_work/ref/terroir_langswitch_before.html").read_text(encoding="utf-8")
    after = (ROOT / "_work/ref/terroir_langswitch_after.html").read_text(encoding="utf-8")
    files = {"project_stone_roofs/index.html": before}
    issues = mod.run_branch(files, list(files), BR)
    assert len(issues) == 1, issues

    acts = mod.fix_branch(dict(files), list(files), BR)
    assert len(acts) == 1
    fixed = acts[0]["content"]

    def switcher_segment(text):
        s = text.index('<ul aria-current="page" class="language-switcher-language-links"')
        e = text.index("</ul>", s) + len("</ul>")
        return text[s:e]

    assert switcher_segment(fixed) == switcher_segment(after)

    # silent on the hand-fixed reference
    files_after = {"project_stone_roofs/index.html": after}
    assert mod.run_branch(files_after, list(files_after), BR) == []


if __name__ == "__main__":
    run(dict(globals()))
