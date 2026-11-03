"""Тести aos_hidden: AOS.init() до завантаження aos.js або відсутній зовсім
лишає data-aos елементи з opacity: 0 назавжди (aos.css: [data-aos^=fade]{opacity:0})."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("aos_hidden")

HEAD = '<link href="https://unpkg.com/aos@2.3.4/dist/aos.css" rel="stylesheet">'
LIB_TAG = '<script src="https://unpkg.com/aos@2.3.4/dist/aos.js"></script>'

# кейс rusveve-ar-es: init виконується РАНІШЕ за тег ліби
BROKEN_ORDER = """<html><head>{head}</head><body>
<div data-aos="fade-up">Hero text</div>
<script>
((() => {{
  if (typeof AOS !== 'undefined') {{
    AOS.init({{ once: true }});
  }}
}})());
</script>
{lib}
</body></html>""".format(head=HEAD, lib=LIB_TAG)

# правильний порядок: лібу спершу, init потім — той самий гард, 9 здорових віток
HEALTHY_ORDER = """<html><head>{head}</head><body>
<div data-aos="fade-up">Hero text</div>
{lib}
<script>
((() => {{
  if (typeof AOS !== 'undefined') {{
    AOS.init({{ once: true }});
  }}
}})());
</script>
</body></html>""".format(head=HEAD, lib=LIB_TAG)

# init взагалі відсутній ніде
MISSING_INIT = """<html><head>{head}</head><body>
<div data-aos="fade-up">Hero text</div>
{lib}
</body></html>""".format(head=HEAD, lib=LIB_TAG)

# data-aos без aos.css — правило opacity:0 не діє, нема чого ловити
NO_AOS_CSS = """<html><head></head><body>
<div data-aos="fade-up">Hero text</div>
</body></html>"""

# сторінка без data-aos взагалі
NO_DATA_AOS = """<html><head>{head}</head><body>
<div>Hero text</div>
{lib}
</body></html>""".format(head=HEAD, lib=LIB_TAG)


def test_init_before_lib_is_flagged():
    issues = mod.run_branch({"index.php": BROKEN_ORDER}, [], "br")
    assert len(issues) == 1, issues
    assert issues[0]["path"] == "index.php"
    assert issues[0]["severity"] == "error"
    assert issues[0]["line"] is not None


def test_init_after_lib_is_silent():
    assert mod.run_branch({"index.php": HEALTHY_ORDER}, [], "br") == []


def test_init_in_separate_js_is_silent():
    # cadebok-mesxif-sg-eng: data-aos в html, AOS.init() — в assets/js/main.js
    files = {
        "index.php": '<html><head>{head}</head><body>'
                      '<div data-aos="fade-up">Hero text</div>'
                      '<script src="assets/js/main.js"></script>'
                      '{lib}</body></html>'.format(head=HEAD, lib=LIB_TAG),
        "assets/js/main.js": "AOS.init({ offset: 200 });",
    }
    assert mod.run_branch(files, [], "br") == []


def test_missing_init_anywhere_is_flagged():
    issues = mod.run_branch({"index.php": MISSING_INIT}, [], "br")
    assert len(issues) == 1, issues
    assert "не викликається" in issues[0]["message"]


def test_data_aos_without_aos_css_is_silent():
    assert mod.run_branch({"index.php": NO_AOS_CSS}, [], "br") == []


def test_page_without_data_aos_is_silent():
    assert mod.run_branch({"index.php": NO_DATA_AOS}, [], "br") == []


# ------------------------------------------------------------------- fix

def test_fix_reorders_lib_before_init_and_run_is_clean():
    files = {"index.php": BROKEN_ORDER}
    actions = mod.fix_branch(files, [], "br")
    assert len(actions) == 1, actions
    assert actions[0]["type"] == "edit"
    assert actions[0]["path"] == "index.php"
    new_text = actions[0]["content"]

    lib_pos = new_text.index(LIB_TAG)
    init_pos = new_text.index("AOS.init(")
    assert lib_pos < init_pos, "тег ліби мусить стояти перед init-блоком"
    assert new_text.count(LIB_TAG) == 1, "тег ліби не мусить дублюватись"

    assert mod.run_branch({"index.php": new_text}, [], "br") == []


def test_fix_is_idempotent():
    files = {"index.php": BROKEN_ORDER}
    once = mod.fix_branch(files, [], "br")
    fixed = {"index.php": once[0]["content"]}
    assert mod.fix_branch(fixed, [], "br") == []


def test_fix_missing_init_inserts_call_after_lib_tag():
    files = {"index.php": MISSING_INIT}
    actions = mod.fix_branch(files, [], "br")
    assert len(actions) == 1, actions
    new_text = actions[0]["content"]
    assert "AOS.init(" in new_text
    lib_pos = new_text.index(LIB_TAG)
    init_pos = new_text.index("AOS.init(")
    assert init_pos > lib_pos

    assert mod.run_branch({"index.php": new_text}, [], "br") == []

    fixed = {"index.php": new_text}
    assert mod.fix_branch(fixed, [], "br") == []


def test_every_broken_page_is_reported_and_fixed():
    """Порядок скриптів у цих вайтах лежить копією в кожному файлі — одна
    знахідка на вітку лишила б решту сторінок і без рапорту, і без фікса."""
    files = {"index.php": BROKEN_ORDER, "about.html": BROKEN_ORDER,
             "privacy.html": NO_DATA_AOS}
    issues = mod.run_branch(files, [], "br")
    assert sorted(i["path"] for i in issues) == ["about.html", "index.php"]
    acts = mod.fix_branch(files, [], "br")
    assert sorted(a["path"] for a in acts) == ["about.html", "index.php"]
    fixed = {**files, **{a["path"]: a["content"] for a in acts}}
    assert mod.run_branch(fixed, [], "br") == []


if __name__ == "__main__":
    run(dict(globals()))
