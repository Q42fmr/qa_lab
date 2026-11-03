"""Тести header_anchor: лого в хедері має бути посиланням, а CTA — <a>, не
мертвою <button>."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("header_anchor")

PATHS = ["index.html", "about.html", "contact.html", "services.html"]


def _page(header_inner, extra=""):
    return (f"<html><body><header>{header_inner}</header>"
            f"<main>{extra}</main></body></html>")


def _files(header_inner, extra=""):
    return {"index.html": _page(header_inner, extra),
            "contact.html": "<html><body><form id='lead'></form></body></html>"}


def _run(files, paths=None):
    return mod.run_branch(dict(files), list(paths or PATHS))


def _fix(files, paths=None):
    return {a["path"]: a["content"]
            for a in mod.fix_branch(dict(files), list(paths or PATHS))}


# --------------------------------------------------------------- лого
def test_unlinked_logo_is_flagged_and_wrapped():
    """Кейс cazatutdc-br-pt: <div class="logo">CazatutDC</div> — з лого не
    повернутись на головну."""
    files = _files('<div class="logo">CazatutDC</div>')
    issues = [i for i in _run(files) if "лого" in i["message"]]
    assert len(issues) == 1 and issues[0]["severity"] == "error", issues
    out = _fix(files)["index.html"]
    assert '<a href="index.html"><div class="logo">CazatutDC</div></a>' in out, out


def test_logo_inside_a_link_is_silent():
    files = _files('<a href="./"><div class="logo">CazatutDC</div></a>')
    assert [i for i in _run(files) if "лого" in i["message"]] == []


def test_logo_that_contains_a_link_is_silent():
    """`<div class="site-logo"><a href="/">Бренд</a></div>` теж робочий —
    без цієї умови фікс давав би вкладене <a><div><a>…, тобто битий HTML."""
    files = _files('<div class="site-logo"><a href="/">Eldersphere</a></div>')
    assert [i for i in _run(files) if "лого" in i["message"]] == []
    assert _fix(files) == {}


def test_empty_logo_container_is_not_a_logo():
    files = _files('<div class="logo"><img src="logo.png"></div>')
    assert [i for i in _run(files) if "лого" in i["message"]] == []


def test_logo_fix_keeps_inner_markup():
    files = _files('<div class="logo"><span class="a">Cam</span>erasBR</div>')
    out = _fix(files)["index.html"]
    assert '<span class="a">Cam</span>erasBR' in out, out


def test_logo_link_is_page_relative():
    paths = PATHS + ["blog/post.html"]
    files = {"blog/post.html": _page('<div class="logo">Brand</div>')}
    out = _fix(files, paths)["blog/post.html"]
    assert 'href="../index.html"' in out, out


# ---------------------------------------------------------------- CTA
def test_dead_cta_button_becomes_a_link_to_contact():
    files = _files('<div class="logo"><a href="./">B</a></div>'
                   '<button class="cta">Solicitar Orçamento</button>')
    issues = [i for i in _run(files) if "CTA" in i["message"]]
    assert len(issues) == 1, issues
    out = _fix(files)["index.html"]
    assert '<a href="contact.html" class="cta">Solicitar Orçamento</a>' in out, out
    assert "<button" not in out, out


def test_button_type_attribute_is_dropped_on_conversion():
    files = _files('<button type="button" class="cta">Agendar</button>')
    out = _fix(files)["index.html"]
    assert 'type=' not in out.split("<header>")[1].split("</header>")[0], out


def test_submit_button_in_a_form_is_left_alone():
    """Search/Pesquisar у справжній формі пошуку — не CTA."""
    files = _files('<form><input><button type="submit">Search</button></form>')
    assert [i for i in _run(files) if "CTA" in i["message"]] == []


def test_any_button_inside_a_form_is_left_alone():
    """Навіть без type=submit кнопка всередині <form> керує формою, а не
    веде на сторінку — робити з неї лінк означало б зламати форму."""
    files = _files('<form action="/s"><input>'
                   '<button class="cta">Enviar Pedido</button></form>')
    assert [i for i in _run(files) if "CTA" in i["message"]] == []
    assert _fix(files) == {}


def test_toggle_button_is_left_alone():
    for attrs in ('aria-expanded="false"', 'data-bs-toggle="dropdown"',
                  'onclick="openMenu()"', 'aria-controls="menu"'):
        files = _files(f'<button {attrs}>Soluções</button>')
        assert [i for i in _run(files) if "CTA" in i["message"]] == [], attrs


def test_glyph_and_ui_words_are_left_alone():
    for label in ("☰", "✕", "×", "A+", "A", "Close", "Fechar", "Pesquisar", "Menu"):
        files = _files(f"<button>{label}</button>")
        assert [i for i in _run(files) if "CTA" in i["message"]] == [], label


def test_several_buttons_are_a_dropdown_menu_not_a_cta():
    """dihaahihjukiwuw-dpu: шість кнопок у хедері — це випадайне меню.
    Перетворити їх на лінки означало б зламати навігацію."""
    files = _files("<button>Atuação</button><button>Internacional</button>"
                   "<button>Ações</button>")
    assert [i for i in _run(files) if "CTA" in i["message"]] == []
    assert _fix(files) == {}


def test_cta_without_any_target_is_reported_but_not_fixed():
    paths = ["index.html", "about.html"]
    files = {"index.html": _page('<button class="cta">Agendar</button>')}
    issues = [i for i in _run(files, paths) if "CTA" in i["message"]]
    assert len(issues) == 1 and "руками" in issues[0]["message"], issues
    assert _fix(files, paths) == {}


def test_form_page_is_the_fallback_target_with_anchor():
    """Контактної сторінки немає — ведемо на сторінку з формою, прямо на форму."""
    paths = ["index.html", "solutions.html"]
    files = {"index.html": _page('<button class="cta">Agendar</button>'),
             "solutions.html": "<html><form id='lead'></form></html>"}
    out = _fix(files, paths)["index.html"]
    assert 'href="solutions.html#lead"' in out, out


def test_form_page_without_id_links_to_the_page():
    paths = ["index.html", "solutions.html"]
    files = {"index.html": _page('<button class="cta">Agendar</button>'),
             "solutions.html": "<html><form></form></html>"}
    out = _fix(files, paths)["index.html"]
    assert 'href="solutions.html"' in out, out


# --------------------------------------------------------------- межі
def test_page_without_header_is_skipped():
    files = {"index.html": "<html><body><div class='logo'>X</div></body></html>"}
    assert _run(files) == []


def test_both_defects_are_fixed_in_one_pass():
    files = _files('<div class="logo">CazatutDC</div>'
                   '<button class="cta">Solicitar Orçamento</button>')
    out = _fix(files)["index.html"]
    assert '<a href="index.html"><div class="logo">' in out, out
    assert '<a href="contact.html" class="cta">' in out, out


def test_fix_is_idempotent():
    files = _files('<div class="logo">CazatutDC</div>'
                   '<button class="cta">Solicitar Orçamento</button>')
    once = dict(files, **_fix(files))
    assert mod.fix_branch(dict(once), list(PATHS)) == []
    assert [i for i in _run(once) if "руками" not in i["message"]] == []


def test_fix_does_not_touch_anything_outside_the_header():
    files = _files('<div class="logo">Brand</div>',
                   extra='<div class="logo">Brand</div><button>Enviar</button>')
    out = _fix(files)["index.html"]
    body = out.split("</header>")[1]
    assert '<div class="logo">Brand</div><button>Enviar</button>' in body, body


def test_check_is_php_auto():
    assert mod.PROJECTS == ["php"], mod.PROJECTS
    assert mod.GROUP == "auto"


if __name__ == "__main__":
    run(dict(globals()))
