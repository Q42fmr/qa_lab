"""Тести link_target: внутрішній href має вести на наявний файл вітки."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("link_target")

PAGES = ["index.html", "about.html", "contact.html", "services.html",
         "service-dvr-para-segurança-sistema-de-gravação-cazatutdc.html",
         "service-câmeras-ip-de-alta-definição-cazatutdc.html",
         "styles.css", "logo.png"]


def _run(files, paths=None):
    return mod.run_branch(dict(files), list(paths or PAGES))


def _fix(files, paths=None):
    return {a["path"]: a["content"]
            for a in mod.fix_branch(dict(files), list(paths or PAGES))}


def _page(body):
    return f"<html><body>{body}</body></html>"


# ------------------------------------------------------ дописування розширення
def test_extensionless_link_is_flagged_and_fixed():
    """Кейс cazatutdc-br-pt: <a href="services"> при наявному services.html —
    на `php -S` це 404, бо сервер віддає лише наявні файли."""
    files = {"index.html": _page('<a href="services">Serviços</a>')}
    issues = _run(files)
    assert len(issues) == 1 and issues[0]["severity"] == "error", issues
    assert "services.html" in issues[0]["message"], issues
    assert _fix(files)["index.html"] == _page('<a href="services.html">Serviços</a>')


def test_other_attributes_survive_the_fix():
    files = {"index.html": _page(
        '<a href="about" class="nav" style="color:red" target="_self">Sobre</a>')}
    out = _fix(files)["index.html"]
    assert 'href="about.html"' in out, out
    assert 'class="nav" style="color:red" target="_self"' in out, out


def test_single_quotes_are_kept():
    files = {"index.html": _page("<a href='contact'>x</a>")}
    assert "href='contact.html'" in _fix(files)["index.html"]


def test_anchor_and_query_are_preserved():
    files = {"index.html": _page('<a href="contact#form">x</a>'
                                 '<a href="about?ref=1">y</a>')}
    out = _fix(files)["index.html"]
    assert 'href="contact.html#form"' in out, out
    assert 'href="about.html?ref=1"' in out, out


# --------------------------------------------------------- «подібний файл»
def test_truncated_prefix_resolves_to_the_long_file():
    """`href="service-dvr"` ↔ `service-dvr-para-segurança-….html`: лінк це
    вкорочений префікс без діакритики."""
    files = {"index.html": _page('<a href="service-dvr">DVR</a>')}
    issues = _run(files)
    assert len(issues) == 1, issues
    out = _fix(files)["index.html"]
    assert "service-dvr-para-segurança-sistema-de-gravação-cazatutdc.html" in out, out


def test_prefix_match_folds_diacritics():
    files = {"index.html": _page('<a href="service-cameras-ip">IP</a>')}
    out = _fix(files)["index.html"]
    assert "service-câmeras-ip-de-alta-definição-cazatutdc.html" in out, out


def test_ambiguous_prefix_is_reported_but_not_fixed():
    """Два кандидати — підставити один означало б гадати."""
    paths = PAGES + ["service-x-alpha.html", "service-x-beta.html"]
    files = {"index.html": _page('<a href="service-x">x</a>')}
    issues = _run(files, paths)
    assert len(issues) == 1 and "нікуди" in issues[0]["message"], issues
    assert _fix(files, paths) == {}


def test_prefix_match_folds_case_and_separators():
    """`Service_DVR` і `service-dvr-…` — те саме ім'я, різний запис."""
    for href in ("Service_DVR", "SERVICE-DVR", "service dvr"):
        files = {"index.html": _page(f'<a href="{href}">x</a>')}
        out = _fix(files).get("index.html", "")
        assert "service-dvr-para-segurança" in out, (href, out)


def test_single_letter_prefix_is_not_guessed_even_when_unique():
    """MIN_PREFIX стереже саме цей випадок: `a` однозначно продовжується до
    `about.html`, але лінк «a» — це не вкорочена назва, а щось інше."""
    paths = ["index.html", "about.html"]
    files = {"index.html": _page('<a href="a">x</a>')}
    issues = _run(files, paths)
    assert len(issues) == 1 and "нікуди" in issues[0]["message"], issues
    assert _fix(files, paths) == {}


def test_too_short_prefix_is_not_guessed():
    """`s` збіглося б із половиною вітки."""
    files = {"index.html": _page('<a href="s">x</a>')}
    issues = _run(files)
    assert len(issues) == 1 and "нікуди" in issues[0]["message"], issues


def test_dead_link_without_any_candidate_is_reported_not_fixed():
    """Юридичний шаблон лінкує на services.html, якого немає (є practice.html)
    — підставляти інший файл означало б гадати про зміст."""
    paths = ["index.html", "practice.html", "attorneys.html"]
    files = {"index.html": _page('<a href="services.html">x</a>')}
    issues = _run(files, paths)
    assert len(issues) == 1 and "нікуди" in issues[0]["message"], issues
    assert _fix(files, paths) == {}


# ------------------------------------------------------------- що не чіпаємо
def test_working_links_are_silent():
    files = {"index.html": _page(
        '<a href="about.html">a</a><a href="./contact.html">b</a>'
        '<a href="index.html">c</a>')}
    assert _run(files) == []
    assert _fix(files) == {}


def test_home_and_directory_links_are_silent():
    files = {"index.html": _page('<a href="./">home</a><a href=".">h</a>'
                                 '<a href="../">up</a>')}
    assert _run(files) == []


def test_external_and_non_navigational_are_silent():
    files = {"index.html": _page(
        '<a href="https://x.com/a">1</a><a href="//cdn.io/b">2</a>'
        '<a href="mailto:a@b.co">3</a><a href="tel:+123">4</a>'
        '<a href="#form">5</a><a href="javascript:void(0)">6</a>'
        '<a href="/absolute">7</a><a href="about:blank">8</a>')}
    assert _run(files) == []


def test_empty_href_is_left_to_its_own_check():
    files = {"index.html": _page('<a href="">x</a>')}
    assert _run(files) == []


def test_bound_href_of_a_js_template_is_not_a_link():
    """cedko-ia br-pt (TECH-29416, 27.10): Alpine `<a :href="sol.url">` у
    `<template x-for>` читалось як лінк на файл «sol.url» — «веде в нікуди».
    `:href`/`v-bind:href`/`x-bind:href`/`[href]` — вираз, не адреса."""
    files = {"index.html": _page('<template x-for="s in items"><a :href="s.url" class="x">a</a></template>'
                                 '<a v-bind:href="u">b</a><a x-bind:href="v">c</a><a [href]="w">d</a>')}
    assert _run(files) == []
    assert mod.fix_branch(dict(files), list(PAGES)) == []


def test_page_relative_parent_link_is_valid():
    """`../contact.html` зі сторінки в blog/ веде саме на кореневий contact.html
    — переписати його на `contact.html` означало б зламати лінк."""
    paths = PAGES + ["blog/post.html"]
    files = {"blog/post.html": _page('<a href="../contact.html">x</a>')}
    assert _run(files, paths) == []
    assert _fix(files, paths) == {}


def test_root_relative_link_from_a_subpage_is_valid():
    """Друга конвенція корпусу: сторінка в підтеці лінкує від КОРЕНЯ вітки."""
    paths = ["sub/index.html", "sub/contacts.html"]
    files = {"sub/index.html": _page('<a href="sub/contacts.html">x</a>')}
    assert _run(files, paths) == []


def test_fix_from_a_subpage_stays_page_relative():
    paths = ["blog/post.html", "contact.html"]
    files = {"blog/post.html": _page('<a href="../contact">x</a>')}
    out = _fix(files, paths)["blog/post.html"]
    assert 'href="../contact.html"' in out, out


def test_non_page_targets_are_not_invented():
    """`styles` не має ставати `styles.css` — чек про сторінки."""
    files = {"index.html": _page('<a href="styles">x</a>')}
    issues = _run(files)
    assert len(issues) == 1 and "нікуди" in issues[0]["message"], issues


def test_fix_is_idempotent():
    files = {"index.html": _page('<a href="services">a</a><a href="about">b</a>')}
    once = dict(files, **_fix(files))
    assert mod.fix_branch(dict(once), list(PAGES)) == []
    assert _run(once) == []


def test_check_is_php_auto():
    assert mod.PROJECTS == ["php"], mod.PROJECTS
    assert mod.GROUP == "auto"


if __name__ == "__main__":
    run(dict(globals()))
