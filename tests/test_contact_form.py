"""Перевірка contact_form: сайт без жодної лід-форми отримує секцію з формою."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                       # noqa: E402

cf = load_check("contact_form")

CSS = """    :root { --color-primary: #ff6600; }
    .btn { background: #ff6600; color: #fff; }
    body { background: #ffffff; }"""

DARK_CSS = """    body { background: #0a0a0a; }
    .btn { background: #e91e63; }"""


def page(lang, body, css=CSS, extra_head=""):
    return (f'<!DOCTYPE html>\n<html lang="{lang}"><head>{extra_head}\n'
            f"<style>\n{css}\n</style>\n</head><body>\n"
            f"{body}\n</body></html>\n")


SEARCH_FORM = '<form role="search"><input type="search" name="q"></form>'
LEAD_FORM = ('<form><input type="text" name="name"><input type="email" name="email">'
             "<textarea name=\"message\"></textarea><button>Send</button></form>")
FOOTER = '<footer><p>&copy; 2026 Site</p></footer>'


def files_for(home_body, extra=None, lang="en"):
    files = {"index.php": page(lang, home_body + "\n" + FOOTER)}
    if extra:
        files.update(extra)
    return files


# ---------------------------------------------------------------- детект
def test_branch_without_any_form_is_flagged_on_home():
    files = files_for("<h1>Welcome</h1>")
    issues = cf.run_branch(files, list(files))
    assert len(issues) == 1, issues
    assert issues[0]["path"] == "index.php", issues
    assert "форм" in issues[0]["message"], issues


def test_search_form_only_is_still_flagged():
    files = files_for("<h1>Welcome</h1>\n" + SEARCH_FORM)
    issues = cf.run_branch(files, list(files))
    assert len(issues) == 1, issues


def test_lead_form_on_other_page_is_silent():
    files = files_for("<h1>Welcome</h1>",
                       extra={"contato.php": page("pt", LEAD_FORM)})
    assert cf.run_branch(files, list(files)) == []


def test_home_missing_is_silent():
    files = {"about.php": page("en", "<h1>About</h1>")}
    assert cf.run_branch(files, list(files)) == []


# ---------------------------------------------------------------- фікс
def test_fix_inserts_section_before_footer():
    files = files_for("<h1>Welcome</h1>")
    actions = cf.fix_branch(files, list(files), branch="site-en-us")
    assert len(actions) == 1, actions
    new = actions[0]["content"]
    assert actions[0]["path"] == "index.php"
    sec_pos = new.find('class="qa_lab-contact"')
    foot_pos = new.find("<footer")
    assert 0 < sec_pos < foot_pos, (sec_pos, foot_pos)
    assert "<form" in new


def test_fix_labels_are_portuguese_for_br_pt_branch():
    files = files_for("<h1>Bem-vindo</h1>", lang="pt")
    actions = cf.fix_branch(files, list(files), branch="bahe-folti-br-pt")
    new = actions[0]["content"]
    assert 'id="contato"' in new, new
    assert "Fale conosco" in new
    assert "Nome" in new and "Telefone" in new and "Mensagem" in new


def test_fix_labels_are_japanese_for_jp_branch():
    files = files_for('<h1>\u3088\u3046\u3053\u305d</h1>', lang="ja")
    actions = cf.fix_branch(files, list(files), branch="cluakoje-jp-ja-jp-jp")
    new = actions[0]["content"]
    assert "\u304a\u554f\u3044\u5408\u308f\u305b" in new   # heading
    assert "\u9001\u4fe1" in new                             # submit button


def test_fix_picks_accent_from_css_variable():
    files = files_for("<h1>Welcome</h1>")
    actions = cf.fix_branch(files, list(files))
    assert "#ff6600" in actions[0]["content"]


def test_fix_picks_accent_from_btn_rule_without_css_var():
    css = ".btn { background: #112233; }\nbody { background: #fff; }"
    files = files_for("<h1>Welcome</h1>", lang="en")
    files["index.php"] = page("en", "<h1>Welcome</h1>\n" + FOOTER, css=css)
    actions = cf.fix_branch(files, list(files))
    assert "#112233" in actions[0]["content"]


def test_fix_falls_back_to_default_accent():
    css = "body { background: #fff; }"
    files = {"index.php": page("en", "<h1>Welcome</h1>\n" + FOOTER, css=css)}
    actions = cf.fix_branch(files, list(files))
    assert "#2563eb" in actions[0]["content"]


def test_fix_uses_light_text_on_dark_background():
    files = {"index.php": page("en", "<h1>Welcome</h1>\n" + FOOTER, css=DARK_CSS)}
    actions = cf.fix_branch(files, list(files))
    new = actions[0]["content"]
    sec = new[new.find('id="contact"'):new.find("</section>")]
    assert "color:#fff" in sec, sec


def test_fix_stubs_the_new_form():
    files = files_for("<h1>Welcome</h1>")
    actions = cf.fix_branch(files, list(files), branch="bahe-folti-br-pt")
    new = actions[0]["content"]
    assert 'querySelectorAll("form[data-' in new, new
    import re
    assert re.search(r'data-[a-z]{6}="1"', new), new


def test_fix_is_idempotent():
    files = files_for("<h1>Welcome</h1>")
    actions = cf.fix_branch(files, list(files), branch="bahe-folti-br-pt")
    files2 = dict(files)
    files2["index.php"] = actions[0]["content"]
    assert cf.run_branch(files2, list(files2)) == []
    assert cf.fix_branch(files2, list(files2), branch="bahe-folti-br-pt") == []


def test_fix_without_lead_form_anywhere_leaves_other_pages_untouched():
    files = files_for("<h1>Welcome</h1>",
                       extra={"legal/privacy.php": page("en", "<p>Privacy policy</p>")})
    actions = cf.fix_branch(files, list(files))
    paths = [a["path"] for a in actions]
    assert paths == ["index.php"], paths


if __name__ == "__main__":
    run(dict(globals()))
