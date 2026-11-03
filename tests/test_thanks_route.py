"""Тести thanks_route: дефолт return page в inject-скрипті має вести на
справжню сторінку подяки вітки (слаг береться з роутера, не з назви файлу)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("thanks_route")

BRANCH = "apoj-gencaa-br-pt"
INJECT = "scripts/inject-php.cjs"
ROUTER = "src/router/index.js"

CJS = """const PHP_BEFORE_DOCTYPE = `<?php
$isDev = true;
$returnPage = $_ENV['WHITE_FORM_RETURN_PAGE'] ?? '{default}';
if (!str_ends_with($returnPage, '.html')) {{
    $returnPage .= '.html';
}}
`;
"""

ROUTES = """import {{ createRouter }} from 'vue-router'
const routes = [
  {{ path: '/', name: 'home', component: () => import('@/pages/Home.vue') }},
  {{ path: '/privacidade', name: 'privacy', component: () => import('@/pages/Privacy.vue') }},
  {{ path: '{path}', name: '{name}', component: () => import('@/pages/{comp}.vue') }}
]
export default routes
"""


def _files(default="thank-you", path="/obrigado", name="thanks", comp="Thanks"):
    return {INJECT: CJS.format(default=default),
            ROUTER: ROUTES.format(path=path, name=name, comp=comp)}


def _run(files):
    return mod.run_branch(dict(files), list(files), BRANCH)


def _fix(files):
    return {a["path"]: a["content"]
            for a in mod.fix_branch(dict(files), list(files), BRANCH)}


# ------------------------------------------------------------- ядро
def test_hardcoded_thank_you_against_localised_page_is_flagged():
    """Генератор хардкодить 'thank-you', а сторінку локалізують: у корпусі
    215 віток з inject-скриптом і в ЖОДНІЙ немає роуту 'thank-you'."""
    issues = _run(_files())
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "error"
    assert "obrigado" in issues[0]["message"], issues
    assert issues[0]["path"] == INJECT, issues


def test_matching_default_is_silent():
    assert _run(_files(default="obrigado")) == []


def test_fix_puts_the_route_slug_into_the_default():
    out = _fix(_files())[INJECT]
    assert "?? 'obrigado';" in out, out
    assert "thank-you" not in out, out


def test_fix_touches_only_the_inject_file():
    files = _files()
    acts = mod.fix_branch(dict(files), list(files), BRANCH)
    assert [a["path"] for a in acts] == [INJECT], acts


def test_fix_keeps_everything_else_byte_for_byte():
    files = _files()
    out = _fix(files)[INJECT]
    assert out == files[INJECT].replace("'thank-you'", "'obrigado'"), out


def test_fix_is_idempotent():
    files = _files()
    once = dict(files, **_fix(files))
    assert mod.fix_branch(dict(once), list(once), BRANCH) == []
    assert _run(once) == []


def test_every_default_in_the_file_is_fixed():
    """У корпусі преамбула одна, але якщо її продублюють — половина вітки не
    сміє лишитись із 404."""
    files = _files()
    files[INJECT] += CJS.format(default="thank-you")
    out = _fix(files)[INJECT]
    assert out.count("'obrigado'") == 2, out
    assert "thank-you" not in out, out


# --------------------------------------------- як упізнається роут подяки
def test_route_found_by_canonical_name():
    """Слаг екзотичний, але name — канонічний id."""
    issues = _run(_files(path="/zzz", name="thanks", comp="Zzz"))
    assert len(issues) == 1 and "zzz" in issues[0]["message"], issues


def test_route_found_by_component_file():
    issues = _run(_files(path="/zzz", name="whatever", comp="Thanks"))
    assert len(issues) == 1 and "zzz" in issues[0]["message"], issues


def test_route_found_by_localised_slug():
    """Ні name, ні компонент не підказують — але слаг є у словнику локалей."""
    issues = _run(_files(path="/danke", name="page7", comp="Page7"))
    assert len(issues) == 1 and "danke" in issues[0]["message"], issues


def test_route_found_by_localised_display_name():
    issues = _run(_files(path="/p", name="Дякуємо", comp="Page"))
    assert len(issues) == 1, issues


def test_non_latin_slug_is_supported():
    for slug in ("dyakuyemo", "terima-kasih", "gamsahamnida", "tesekkurler"):
        issues = _run(_files(path="/" + slug, name="x", comp="X"))
        assert len(issues) == 1 and slug in issues[0]["message"], slug


def test_diacritics_and_case_do_not_create_a_false_mismatch():
    """`Confirmação` у дефолті і `confirmacao` у роуті — те саме слово."""
    assert _run(_files(default="Confirmação", path="/confirmacao",
                       name="thanks", comp="Thanks")) == []


def test_separator_difference_is_not_a_mismatch():
    assert _run(_files(default="terima kasih", path="/terima-kasih",
                       name="thanks", comp="Thanks")) == []


def test_home_route_is_not_mistaken_for_thanks():
    """`/` стоїть у роутері першим — він не сторінка подяки."""
    files = {INJECT: CJS.format(default="thank-you"),
             ROUTER: ("const routes = [\n"
                      "  { path: '/', name: 'home', component: () => import('@/pages/Home.vue') }\n"
                      "]\n")}
    issues = _run(files)
    assert len(issues) == 1, issues
    assert "немає сторінки подяки" in issues[0]["message"], issues
    assert mod.fix_branch(dict(files), list(files), BRANCH) == []


# ------------------------------------------------------------- межі
def test_branch_without_inject_script_is_skipped():
    """Next-вайти й інші стеки inject-скрипта не мають — судити нема що."""
    files = {ROUTER: ROUTES.format(path="/obrigado", name="thanks", comp="Thanks")}
    assert _run(files) == []
    assert mod.fix_branch(dict(files), list(files), BRANCH) == []
    # інʼєкт-файл шукається за іменем, а не «перший-ліпший»: інакше фікс
    # писав би у роутер, який ми правити не маємо права
    assert mod._inject_path(files) is None, files
    assert mod._inject_path(_files()) == INJECT


def test_inject_without_the_default_is_skipped():
    files = {INJECT: "const PHP = `<?php $isDev = true; `;\n",
             ROUTER: ROUTES.format(path="/obrigado", name="thanks", comp="Thanks")}
    assert _run(files) == []


def test_double_quoted_default_is_handled():
    files = _files()
    files[INJECT] = files[INJECT].replace("'thank-you'", '"thank-you"')
    out = _fix(files)[INJECT]
    assert '?? "obrigado";' in out, out


def test_env_driven_value_is_not_touched():
    """Міняється лише дефолт після `??`, сама змінна оточення — ні."""
    out = _fix(_files())[INJECT]
    assert "$_ENV['WHITE_FORM_RETURN_PAGE']" in out, out


def test_check_is_registered_for_node_only():
    assert mod.PROJECTS == ["node"], mod.PROJECTS
    assert mod.GROUP == "auto"


if __name__ == "__main__":
    run(dict(globals()))
