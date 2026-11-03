"""Форма vue-вайта: сабміт має долітати, а подяка — відкриватись.

Дві поломки одного потоку, обидві зміряні на живому деплої
(`nwf-premaghou-br-pt`, порт php-деплою лаби):

1. `<form method="POST">` — інжектований php ловить лід з `$_GET`, а POST
   кладе поля в тіло запиту. `curl -X POST /` → у відповіді **0** редіректів
   і жодного пікселя; `curl "/?name=…&email=…"` → редірект є. Тобто з
   method="POST" лід не зараховується взагалі.
2. `$returnPage .= '.html'` у `scripts/inject-php.cjs` — редірект іде на
   `/obrigado.html`, а у вітці такої сторінки немає: роутер знає `/obrigado`,
   файлу `obrigado.html` немає в жодній з 305 віток. У браузері
   `/obrigado.html` — порожня сторінка (шапка + футер, `<h1>` немає),
   `/obrigado` — справжня подяка «Obrigado pelo seu interesse!».
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, load_check, run                   # noqa: E402

sys.path.insert(0, str(ROOT))

mod = load_check("form_flow")
INJ = "scripts/inject-php.cjs"

SUFFIX_BAD = """const PHP_BEFORE_DOCTYPE = `<?php
$isDev = true;
$returnPage = $_ENV['WHITE_FORM_RETURN_PAGE'] ?? 'obrigado';
if (!str_ends_with($returnPage, '.html')) {
    $returnPage .= '.html';
}
$trackingConfig = [
`;
"""
SUFFIX_OK = SUFFIX_BAD.replace("'.html'", "''")


def _run(files):
    return mod.run_branch(dict(files), list(files))


def _fix(files):
    return {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files))}


# ------------------------------------------------- 1. суфікс .html
def test_html_suffix_is_flagged():
    issues = _run({INJ: SUFFIX_BAD})
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "error"
    assert ".html" in issues[0]["message"], issues


def test_html_suffix_is_stripped():
    out = _fix({INJ: SUFFIX_BAD})[INJ]
    assert "str_ends_with($returnPage, '')" in out, out
    assert "$returnPage .= '';" in out, out
    assert ".html" not in out, out


def test_only_the_suffix_block_is_touched():
    out = _fix({INJ: SUFFIX_BAD})[INJ]
    assert "$isDev = true;" in out
    assert "'obrigado'" in out, "дефолт сторінки чіпати не можна"
    assert out.count("\n") == SUFFIX_BAD.count("\n"), "структура файлу поїхала"


def test_already_stripped_is_silent():
    assert _run({INJ: SUFFIX_OK}) == []
    assert _fix({INJ: SUFFIX_OK}) == {}


def test_any_suffix_counts_not_only_html():
    src = SUFFIX_BAD.replace(".html", ".php")
    assert len(_run({INJ: src})) == 1
    assert "$returnPage .= '';" in _fix({INJ: src})[INJ]


def test_formatting_variants_are_matched():
    for src in (
        'if (!str_ends_with($returnPage, ".html")) {\n  $returnPage .= ".html";\n}',
        "if(!str_ends_with($returnPage,'.html')){\n$returnPage.='.html';\n}",
        "if ( ! str_ends_with( $returnPage , '.html' ) ) {\n\t$returnPage .= '.html' ;\n}",
    ):
        assert len(_run({INJ: src})) == 1, src
        assert ".html" not in _fix({INJ: src})[INJ], src


def test_file_without_the_block_is_silent():
    assert _run({INJ: "const x = 1;\n"}) == []


def test_block_outside_the_inject_script_is_not_our_business():
    assert _run({"src/pages/Home.vue": SUFFIX_BAD}) == []


# ---------------- гард: плоский білд, де '.html' потрібен
# У кожній вітці два білди. `generate` = `vite build` дає чистий SPA (один
# index.html, роути клієнтські) — там суфікс мусить бути порожній. А
# `vite-ssg build` з `ssgOptions.dirStyle:'flat'` кладе ПЛОСКІ obrigado.html —
# і тоді '.html' обовʼязковий. Вирішує саме `generate`, бо лише він запускає
# inject-php.cjs (звірено: 305 з 305 віток корпусу).
PKG_SPA = '{"scripts": {"generate": "vite build && node scripts/inject-php.cjs",' \
          ' "build:static": "vite-ssg build"}}'
PKG_FLAT = '{"scripts": {"generate": "vite-ssg build && node scripts/inject-php.cjs"}}'


def test_spa_build_still_strips_the_suffix():
    """Наявність `build:static` поруч нічого не міняє: той білд php-преамбули
    не створює взагалі, тож суфікс у ній йому не належить."""
    files = {INJ: SUFFIX_BAD, "package.json": PKG_SPA}
    assert len(_run(files)) == 1, _run(files)
    assert INJ in _fix(files)


def test_flat_build_keeps_the_suffix():
    """Якщо `generate` переведуть на vite-ssg — плоскі html зʼявляться, і
    прибирати '.html' стане поломкою. Тоді чек мовчить і не чіпає файл."""
    files = {INJ: SUFFIX_BAD, "package.json": PKG_FLAT}
    assert _run(files) == []
    assert _fix(files) == {}


def test_flat_build_does_not_disable_the_form_rule():
    """Гард стосується ЛИШЕ суфікса: method=\"POST\" ламає лід за будь-якого
    білда."""
    form = '<template><form method="POST"><input name="a"></form></template>'
    files = {INJ: SUFFIX_BAD, "package.json": PKG_FLAT,
             "src/components/Form.vue": form}
    issues = _run(files)
    assert len(issues) == 1 and "method" in issues[0]["message"], issues
    assert "src/components/Form.vue" in _fix(files)


def test_broken_package_json_falls_back_to_stripping():
    """Битий/відсутній package.json не має вимикати правило — інакше одна
    зіпсована кома тихо знімала б перевірку."""
    for pkg in ('{not json', '{}', '{"scripts": {}}'):
        files = {INJ: SUFFIX_BAD, "package.json": pkg}
        assert len(_run(files)) == 1, pkg
    assert len(_run({INJ: SUFFIX_BAD})) == 1


def test_package_json_is_actually_scanned():
    """Гард читає `generate` з package.json — без маски у FILES раннер його
    просто не передасть, і гард тихо перестане існувати."""
    assert "package.json" in mod.FILES, mod.FILES


# ------------------------------------------------- 2. method у формі
FORM = ('<template><section>'
        '<form method="POST" class="space-y-6">'
        '<input name="email"><button type="submit">Go</button>'
        '</form></section></template>')


def test_form_method_is_flagged():
    issues = _run({"src/components/InquiryFormHome.vue": FORM})
    assert len(issues) == 1, issues
    assert "method" in issues[0]["message"], issues


def test_form_method_is_removed_and_the_rest_survives():
    out = _fix({"src/components/InquiryFormHome.vue": FORM})["src/components/InquiryFormHome.vue"]
    assert "method=" not in out, out
    assert '<form class="space-y-6">' in out, out
    assert '<button type="submit">Go</button>' in out, "кнопку зачепило"


def test_lowercase_and_single_quotes():
    src = "<template><form method='post'><input></form></template>"
    assert len(_run({"src/A.vue": src})) == 1
    assert "method" not in _fix({"src/A.vue": src})["src/A.vue"]


def test_action_is_removed_too():
    src = '<template><form action="/send" method="POST"><input></form></template>'
    issues = _run({"src/A.vue": src})
    assert len(issues) == 1 and "action" in issues[0]["message"], issues
    out = _fix({"src/A.vue": src})["src/A.vue"]
    assert "action=" not in out and "method=" not in out, out
    assert "<form><input></form>" in out, out


def test_clean_form_is_silent():
    src = '<template><form class="grid" @submit.prevent="send"><input></form></template>'
    assert _run({"src/A.vue": src}) == []
    assert _fix({"src/A.vue": src}) == {}


def test_prevented_submit_still_loses_the_lead_with_method():
    """@submit.prevent не рятує: інжектований php читає $_GET, а не тіло POST."""
    src = '<template><form method="POST" @submit.prevent="send"><input></form></template>'
    assert len(_run({"src/A.vue": src})) == 1
    out = _fix({"src/A.vue": src})["src/A.vue"]
    assert '@submit.prevent="send"' in out and "method=" not in out, out


def test_several_forms_in_several_files():
    files = {"src/A.vue": FORM, "src/B.vue": FORM + FORM,
             "src/C.vue": "<template><form><input></form></template>"}
    assert len(_run(files)) == 3, _run(files)
    out = _fix(files)
    assert set(out) == {"src/A.vue", "src/B.vue"}, out.keys()
    assert "method" not in out["src/B.vue"]


# ------------------------------------------------------------- разом
def test_both_rules_in_one_branch_and_idempotent():
    files = {INJ: SUFFIX_BAD, "src/components/Form.vue": FORM}
    assert len(_run(files)) == 2, _run(files)
    fixed = {**files, **_fix(files)}
    assert mod.run_branch(dict(fixed), list(fixed)) == []
    assert mod.fix_branch(dict(fixed), list(fixed)) == []


def test_check_is_registered_for_node_only():
    assert mod.PROJECTS == ["node"], mod.PROJECTS
    assert mod.GROUP == "auto"


if __name__ == "__main__":
    run(dict(globals()))
