"""Немає e-mail на видимих сторінках (кейс QA tefluer-gechaoh-ch-fr 27.10):
«Нет почты» — на сайті не було жодної адреси e-mail; ручний фікс додав
info@{{DOMAIN}} (mailto) у футер index.php у стилі сусіднього рядка.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run, load_check                     # noqa: E402

mod = load_check("footer_email")
BR = "tefluer-gechaoh-ch-fr"

FOOTER_PAGE = (
    '<html><body><footer class="site-footer">'
    '<p class="text-xs">© 2026 Acme Sàrl</p>'
    '<p class="text-xs">CHE-509.624.333</p>'
    '</footer></body></html>')


def test_branch_without_any_email_is_flagged():
    files = {"index.html": FOOTER_PAGE, "about.html": FOOTER_PAGE}
    issues = mod.run_branch(files, list(files), BR)
    assert len(issues) == 1, issues
    msg = issues[0]["message"]
    assert "немає e-mail" in msg and "info@{{DOMAIN}}" in msg, msg
    assert issues[0]["severity"] == "error"


def test_fix_appends_mailto_row_cloned_in_footer_style_to_every_page():
    files = {"index.html": FOOTER_PAGE, "about.html": FOOTER_PAGE}
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), BR)}
    assert set(acts) == {"index.html", "about.html"}, acts.keys()
    for content in acts.values():
        assert '<p class="text-xs"><a href="mailto:info@{{DOMAIN}}">info@{{DOMAIN}}</a></p>' in content, content
    # idempotent
    fixed = dict(files)
    for p, c in acts.items():
        fixed[p] = c
    assert mod.run_branch(dict(fixed), list(fixed), BR) == []
    assert mod.fix_branch(dict(fixed), list(fixed), BR) == []


def test_local_part_is_reused_from_a_legal_page_only_email():
    files = {
        "index.html": FOOTER_PAGE,
        "privacy-policy.html": (
            '<html><body><p>Contactez-nous: '
            '<a href="mailto:contact@{{DOMAIN}}">contact@{{DOMAIN}}</a></p></body></html>'),
    }
    issues = mod.run_branch(dict(files), list(files), BR)
    assert issues and "contact@{{DOMAIN}}" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), BR)}
    assert "index.html" in acts
    assert "mailto:contact@{{DOMAIN}}" in acts["index.html"], acts["index.html"]
    assert "privacy-policy.html" not in acts            # юридична сторінка не видима — не чіпаємо


def test_placeholder_example_email_does_not_count_as_present():
    page = (
        '<html><body><form><input type="email" placeholder="you@example.com"></form>'
        '<footer class="site-footer"><p class="text-xs">© 2026</p></footer>'
        '</body></html>')
    files = {"index.html": page}
    issues = mod.run_branch(dict(files), list(files), BR)
    assert issues, "placeholder не має рахуватись як наявний e-mail"
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), BR)}
    assert "index.html" in acts
    assert "info@{{DOMAIN}}" in acts["index.html"]


def test_branch_with_visible_email_stays_silent():
    page = (
        '<html><body><footer class="site-footer">'
        '<p class="text-xs"><a href="mailto:info@{{DOMAIN}}">info@{{DOMAIN}}</a></p>'
        '</footer></body></html>')
    files = {"index.html": page}
    assert mod.run_branch(dict(files), list(files), BR) == []
    assert mod.fix_branch(dict(files), list(files), BR) == []


def test_email_only_on_a_secondary_page_is_not_an_email_on_the_site():
    """tesa-nomu br-pt (TECH-29416, 27.10): пошта лише на /garantia (і в
    privacy/termos) — головна і /contato без неї; QA: «на странице не найдено
    ни одной почты, где: на главной». Судить головна; фікс додає рядок на
    всі видимі сторінки, де пошти ще немає, а /garantia не чіпає; локальна
    частина — з наявної пошти сайту."""
    gar = FOOTER_PAGE.replace("</footer>", '<p class="text-xs">Suporte: slziphonesbr@{{DOMAIN}}</p></footer>')
    files = {"index.php": FOOTER_PAGE, "contato/index.html": FOOTER_PAGE, "garantia/index.html": gar,
             "impressum/index.html": FOOTER_PAGE}                 # Impressum — юридична: не чіпається
    issues = mod.run_branch(dict(files), list(files), "tesa-nomu-br-pt")
    assert len(issues) == 1 and "slziphonesbr@{{DOMAIN}}" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "tesa-nomu-br-pt")}
    assert set(acts) == {"index.php", "contato/index.html"}, acts.keys()
    assert all('href="mailto:slziphonesbr@{{DOMAIN}}"' in v for v in acts.values())
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "tesa-nomu-br-pt") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "tesa-nomu-br-pt") == []
    # пошта є на головній, а на /contato немає — тихо: правило про сайт, не про кожну сторінку
    ok = {"index.php": gar, "contato/index.html": FOOTER_PAGE}
    assert mod.run_branch(dict(ok), list(ok), "tesa-nomu-br-pt") == []

def test_pages_without_a_footer_are_skipped_and_message_says_so():
    files = {
        "index.html": FOOTER_PAGE,
        "no-footer.html": "<html><body><p>Текст без футера.</p></body></html>",
    }
    issues = mod.run_branch(dict(files), list(files), BR)
    assert issues and "фікс не чіпає" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), BR)}
    assert set(acts) == {"index.html"}, acts.keys()      # без футера фікс не зачепив


def test_no_footer_anywhere_is_a_manual_only_issue():
    files = {"index.html": "<html><body><p>Текст без футера.</p></body></html>"}
    issues = mod.run_branch(dict(files), list(files), BR)
    assert issues and "руками" in issues[0]["message"], issues
    assert mod.fix_branch(dict(files), list(files), BR) == []


def test_contract_php_only():
    assert mod.PROJECTS == ["php"], mod.PROJECTS
    assert mod.GROUP == "auto"
    assert callable(mod.fix_branch)


def test_real_terroir_before_and_after_case():
    if not (ROOT / "_work" / "ref").is_dir():
        return      # локальні еталони реальних сторінок (_work/ref не в репо): у CI пропускаємо
    before = (ROOT / "_work/ref/terroir_index_before_email.php").read_text(encoding="utf-8")
    after = (ROOT / "_work/ref/terroir_index_after_email.php").read_text(encoding="utf-8")
    before_files = {"index.php": before}
    issues = mod.run_branch(dict(before_files), list(before_files), BR)
    assert len(issues) == 1, issues
    acts = mod.fix_branch(dict(before_files), list(before_files), BR)
    assert len(acts) == 1 and acts[0]["path"] == "index.php"
    fixed = acts[0]["content"]
    assert fixed.count("mailto:info@{{DOMAIN}}") == 1, fixed.count("mailto:info@{{DOMAIN}}")
    assert mod.run_branch({"index.php": fixed}, ["index.php"], BR) == []

    after_files = {"index.php": after}
    assert mod.run_branch(dict(after_files), list(after_files), BR) == []
    assert mod.fix_branch(dict(after_files), list(after_files), BR) == []


if __name__ == "__main__":
    run(dict(globals()))
