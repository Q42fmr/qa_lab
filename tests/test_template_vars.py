"""Змінні шаблону у видимому тексті (checks/template_vars)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, load_check                          # noqa: E402

mod = load_check("template_vars")

PAGE = ('<html><head><title>{{White}} · Loja</title>'
        '<link rel="icon" href="{{LOGO}}"><style>.a{content:"{{x}}"}</style></head><body>'
        '<p>O ${BRAND} atende só em Porto Alegre? Escreva para info@{{DOMAIN}} ou {{DOMAIN_NAME}}.</p>'
        '<script>const s = `${BRAND}-${x}`; const t = "{{x}}";</script>'
        '<?php echo "{{PHPVAR}}"; ?><!-- {{comment}} --></body></html>')


def test_disallowed_tokens_outside_code_are_reported_and_removed():
    issues = mod.run("index.php", PAGE)
    assert len(issues) == 1 and "${BRAND}" in issues[0]["message"] and "{{White}}" in issues[0]["message"], issues
    fixed = mod.fix("index.php", PAGE)
    assert "<title> · Loja</title>" in fixed
    assert 'href=""' in fixed, "токен в атрибуті прибрано (іконку далі підбирає favicon)"
    assert "<p>O atende só em Porto Alegre?" in fixed, fixed[:300]
    # дозволені і код — як були
    assert "info@{{DOMAIN}}" in fixed and "{{DOMAIN_NAME}}" in fixed
    assert "const s = `${BRAND}-${x}`" in fixed and 'const t = "{{x}}"' in fixed
    assert '.a{content:"{{x}}"}' in fixed and '<?php echo "{{PHPVAR}}"; ?>' in fixed and "<!-- {{comment}} -->" in fixed
    assert mod.run("index.php", fixed) == []


def test_clean_page_and_runtime_templates_are_left_alone():
    assert mod.run("a.html", "<p>info@{{DOMAIN}} · {{DOMAIN_NAME}}</p>") == []
    vue = '<script src="/js/vue.min.js"></script><div id="app"><p>{{ message }}</p></div>'
    assert mod.run("a.html", vue) == [] and mod.fix("a.html", vue) == vue
    alpine = '<div x-data="{open:false}"><span>{{open}}</span></div>'
    assert mod.run("a.html", alpine) == []
    # синтаксис як тема тексту і JS-шаблони — не залишки генератора
    blog = '<p>Use</p><pre><code>{{ user.name }}</code></pre><template id="t"><b>{{x}}</b></template><textarea>${A}</textarea>'
    assert mod.run("a.html", blog) == [] and mod.fix("a.html", blog) == blog


def test_js_template_literal_inside_inline_handler_is_untouched():
    # ${…} лише з ідентифікатором-іменем: вираз `${a + b}` не є змінною шаблону
    page = '<a onclick="go(`${a + b}`)">x</a><p>${TITLE}</p>'
    fixed = mod.fix("a.html", page)
    assert "`${a + b}`" in fixed and "<p></p>" in fixed


if __name__ == "__main__":
    run(dict(globals()))
