"""Фавіконка vue-вайта: лінк мусить вести на файл, який у вітці є.

Корпус: у ВСІХ 230 вітках з підв'язаним доменом `index.html` посилається на
`/favicon.ico`, якого немає ніде — 230 гарантованих 404 на кожне відкриття
сторінки. У 19 вітках поруч лежить справжня `public/favicon.svg` (лінк треба
перевести на неї), у решті 211 іконки немає зовсім (треба згенерувати).
"""
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, load_check, run                   # noqa: E402

sys.path.insert(0, str(ROOT))

mod = load_check("favicon_link")
BRANCH = "nwf-provub-cospubtenp-br-pt"
DOMAIN = "provubco.pro"
GEN = "public/favicon.svg"


def _head(*links: str) -> str:
    return ('<!doctype html><html><head><title>Praxis</title>'
            '<meta name="theme-color" content="#1e40af">'
            + "".join(links) +
            '</head><body><div id="app"></div></body></html>')


def _with_domain(domain: str | None = DOMAIN):
    mod._domain_for = lambda branch: domain


def _run(html: str, paths: list[str]):
    return mod.run_branch({"index.html": html}, ["index.html"] + paths, BRANCH)

# фіксів тут більше немає (рішення 01.10): чек лише детектить warn-и,
# заміна знака — руками у «Медіа → Лого/Favicon»


ICO = '<link rel="icon" href="/favicon.ico">'
SVG = '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
APPLE = '<link rel="apple-touch-icon" href="/apple-touch-icon.png">'


# --------------------------------------------------------------- детект
def test_dead_ico_is_flagged():
    _with_domain()
    issues = _run(_head(ICO), [])
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "warn"
    assert "/favicon.ico" in issues[0]["message"], issues


def test_live_link_is_silent():
    _with_domain()
    assert _run(_head(SVG), ["public/favicon.svg"]) == []


def test_icon_in_branch_root_counts_as_live():
    _with_domain()
    assert _run('<html><head><link rel="icon" href="favicon.ico"></head></html>',
                ["favicon.ico"]) == []


def test_data_uri_icon_is_silent():
    _with_domain()
    html = _head('<link rel="icon" href="data:image/svg+xml,<svg/>">')
    assert _run(html, []) == []


def test_no_icon_link_at_all_is_flagged():
    _with_domain()
    issues = _run(_head(), [])
    assert len(issues) == 1 and "немає лінка" in issues[0]["message"], issues


def test_page_without_index_html_is_skipped():
    _with_domain()
    assert mod.run_branch({}, ["src/App.vue"], BRANCH) == []


# ------------------------------------------------- шаблонність і контракт
TEMPLATE_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
                'width="64" height="64">\n'
                '  <rect width="64" height="64" rx="14" fill="#1a1a1a"/>\n'
                '  <text x="32" y="44" font-family="system-ui, sans-serif" '
                'font-size="34" font-weight="700" text-anchor="middle" '
                'fill="#FFFFFF">P</text>\n</svg>\n')


def test_template_mark_detector_judges_old_style_only():
    import brand_mark
    assert brand_mark.is_template_mark(TEMPLATE_SVG)          # фон + 1 літера
    fancy = brand_mark.pick(
        {"index.html": "<title>Provub Cospubtenp — x</title>"},
        BRANCH, base_color="#1e40af")
    assert not brand_mark.is_template_mark(fancy), fancy
    assert not brand_mark.is_template_mark("")                # немає вмісту


def test_template_favicon_is_a_warning(tmp_style="snapshot"):
    # живий лінк + шаблонний вміст public/favicon.svg → warn
    import runner
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix="favlink-"))
    (d / "public").mkdir(parents=True, exist_ok=True)
    (d / "public" / "favicon.svg").write_text(TEMPLATE_SVG, encoding="utf-8")
    old = runner.snapshot_dir
    runner.snapshot_dir = lambda b: d
    try:
        issues = _run(_head(SVG), ["public/favicon.svg"])
    finally:
        runner.snapshot_dir = old
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "warn"
    assert "шаблонний" in issues[0]["message"], issues


def test_nontemplate_favicon_stays_silent():
    import brand_mark
    import runner
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix="favlink-"))
    (d / "public").mkdir(parents=True, exist_ok=True)
    fancy = brand_mark.pick(
        {"index.html": "<title>Provub Cospubtenp — x</title>"}, BRANCH)
    (d / "public" / "favicon.svg").write_text(fancy, encoding="utf-8")
    old = runner.snapshot_dir
    runner.snapshot_dir = lambda b: d
    try:
        assert _run(_head(SVG), ["public/favicon.svg"]) == []
    finally:
        runner.snapshot_dir = old


def test_check_is_detect_only_for_node():
    assert mod.PROJECTS == ["node"], mod.PROJECTS
    assert mod.GROUP == "tests"
    assert not hasattr(mod, "fix_branch"), "автофіксів favicon більше немає"

if __name__ == "__main__":
    run(dict(globals()))
