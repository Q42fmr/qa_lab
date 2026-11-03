"""Форма-заглушка (checks/form_stub): лід-PHP вирізано, форма «відправляє»
вигляду, штатні form-чеки на такій вітці мовчать."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run, load_check, standard_index    # noqa: E402

sys.path.insert(0, str(ROOT))
import projects                                               # noqa: E402

mod = load_check("form_stub")


def _fresh_state():
    import tempfile
    from pathlib import Path
    projects.state_root = lambda d=Path(tempfile.mkdtemp(prefix="fs-")): d

FORM = ('<form id="orcamentoForm" class="card p-7" action="https://crm.example/lead" method="post">'
        '<input name="name" type="text" required><input name="email" type="email" required>'
        '<textarea name="message"></textarea><button type="submit">Enviar</button></form>')
SEARCH = '<form role="search"><input name="q" type="search"><button>OK</button></form>'
HTML = ('<!DOCTYPE html><html lang="pt-BR"><head><title>Aem Pianos</title></head><body>'
        f'<header><a href="./">Home</a></header>{SEARCH}<main>{FORM}</main><footer>© 2026</footer></body></html>')


def _index_php():
    """Головна з трьома еталонними блоками (як з деплою)."""
    return standard_index(HTML)


def _php_blocks(text):
    return re.findall(r"<\?(?:php|=)[\s\S]*?\?>", text)


def test_lead_php_is_cut_but_tracking_stays_and_php_is_balanced():
    _fresh_state()
    files = {"index.php": _index_php(), "thank-you.html": "<html><body>Obrigado</body></html>"}
    issues = mod.run_branch(dict(files), list(files), "aebneunir-br-pt")
    assert len(issues) == 1 and "PHP перехоплює лід" in issues[0]["message"] and "1 форм(и)" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "aebneunir-br-pt")}
    assert list(acts) == ["index.php"], acts.keys()
    new = acts["index.php"]
    # лід-частина зникла…
    for gone in ("isset($_GET['email'])", "$returnPage", "WHITE_FORM_RETURN_PAGE", "fbpixelevent",
                 "$facebookPixelEventLeadKey", "gtag('event', 'conversion'", "new UET(", "exit();"):
        assert gone not in new, gone
    # …а трекінг переглядів і dotenv лишились
    for kept in ("$isDev", "Dotenv\\Dotenv::createImmutable", "$trackingConfig = [", "GA4_MEASUREMENT_ID",
                 "fbq('init'", "gtag('config'", "<?php if(!empty($trackingConfig['fbPixelId'])): ?>", "<?php endif; ?>"):
        assert kept in new, kept
    # кожен <?php … ?> закритий, heredoc-ів (EOL) не лишилось відкритих
    assert new.count("<?php") + new.count("<?=") == new.count("?>"), "незбалансовані php-теги"
    assert "<<<EOL" not in new and "\nEOL;" not in new
    assert "$_GET" not in new
    # форма: action/method зняті, маркер, пошукова форма не чіпалась
    sid = mod.stub_id("aebneunir-br-pt")
    assert re.fullmatch(r"[a-z]{6}", sid) and sid == mod.stub_id("aebneunir-br-pt"), "id детермінований і кешований"
    assert f'<form id="orcamentoForm" class="card p-7" data-{sid}="1">' in new, new[new.find("<form"):new.find("<form") + 120]
    assert '<form role="search"><input name="q"' in new
    # жодного спільного маркера: ні qa_lab, ні wp-stub; скрипт один, перед </body>
    assert "qa_lab" not in new and "wp-stub" not in new
    assert new.count(f'form[data-{sid}]') == 1 and "</body>" in new.split(f'form[data-{sid}]')[-1]
    assert mod.is_stubbed(new) and not mod.is_stubbed(files["index.php"])
    # редірект на наявну сторінку подяки вітки
    assert '"thank-you.html"' in new and ("thank-you.html" in new.rsplit("<script>", 1)[1])
    # ідемпотентно й тихо
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "aebneunir-br-pt") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "aebneunir-br-pt") == []


def test_without_thanks_page_inline_message_in_branch_language():
    _fresh_state()
    files = {"index.php": _index_php(), "contato/index.html": HTML.replace('lang="pt-BR"', 'lang="de"')}
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "x-ch-de")}
    assert '""' in acts["index.php"].rsplit("<script>", 1)[1].split("</script>")[0] and "Mensagem enviada" in acts["index.php"]
    sub = acts["contato/index.html"]
    assert '"sending": "Wird gesendet…"' in sub and "Nachricht erfolgreich gesendet" in sub
    assert mod.STUB_FORM_RX.search(sub) and "$returnPage" not in sub


def test_thanks_page_href_is_relative_to_the_page_depth():
    _fresh_state()
    files = {"index.php": _index_php(), "contato/index.html": HTML, "obrigado/index.html": "<html></html>"}
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "x-br-pt")}
    assert '"obrigado/index.html"' in acts["index.php"].rsplit("<script>", 1)[1].split("</script>")[0]
    assert '"../obrigado/index.html"' in acts["contato/index.html"].rsplit("<script>", 1)[1].split("</script>")[0]


def test_plain_html_without_php_only_gets_the_stub():
    _fresh_state()
    files = {"index.html": HTML}
    issues = mod.run_branch(dict(files), list(files), "x-br-pt")
    assert len(issues) == 1 and not issues[0]["message"].startswith("PHP"), issues
    new = mod.fix_branch(dict(files), list(files), "x-br-pt")[0]["content"]
    assert "<?php" not in new and mod.STUB_FORM_RX.search(new) and "action=" not in new.split("<form", 2)[2].split(">")[0]


def test_random_six_letter_data_attribute_is_not_a_stub_marker():
    """semence / releve ch-fr (27.10): Vue-форма несла випадковий
    `data-pccyjz="1"`, і чек вважав її вже заглушеною (скрипта заглушки на
    сторінці нема) — QA: «форма не відправляється». Маркер заглушки — це
    атрибут ІЗ скриптом під той самий id, а не будь-які 6 літер."""
    _fresh_state()
    page = HTML.replace('<form id="orcamentoForm" class="card p-7"', '<form id="orcamentoForm" class="card p-7" data-pccyjz="1"')
    files = {"index.html": page}
    issues = mod.run_branch(dict(files), list(files), "x-ch-fr")
    assert len(issues) == 1, issues
    new = mod.fix_branch(dict(files), list(files), "x-ch-fr")[0]["content"]
    sid = mod.stub_id("x-ch-fr")
    assert f'data-{sid}="1"' in new and mod.is_stubbed(new) and f'querySelectorAll("form[data-{sid}]")' in new
    fixed = {"index.html": new}
    assert mod.run_branch(dict(fixed), list(fixed), "x-ch-fr") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "x-ch-fr") == []


def test_standard_form_checks_go_silent_on_a_stubbed_branch():
    _fresh_state()
    """forms / php_scripts / form_hijack / form_flow / thanks_route / form_action
    вимагають перехоплення ліда — на вітці зі stub-маркером вони мовчать і
    нічого не фіксять, інакше ганяли б вітку по колу."""
    files = {"index.php": _index_php(), "thank-you.html": "<html></html>"}
    stubbed = {**files, **{a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "x-br-pt")}}
    text = stubbed["index.php"]
    for name in ("forms", "php_scripts", "form_hijack"):
        m = load_check(name)
        assert m.run("index.php", text) == [], name
        if hasattr(m, "fix"):
            assert m.fix("index.php", text) == text, name
    for name in ("form_flow", "thanks_route", "form_action"):
        m = load_check(name)
        try:
            issues = m.run_branch(dict(stubbed), list(stubbed), "x-br-pt")
        except TypeError:
            issues = m.run_branch(dict(stubbed), list(stubbed))
        assert issues == [], name
        assert m.fix_branch(dict(stubbed), list(stubbed), "x-br-pt") == [], name
    # без скрипта заглушки гейт тримає сам зріз PHP (is_lead_cut); а на
    # штатному шаблоні з усіма трьома блоками php_scripts працює як і раніше
    plain = mod.STUB_SCRIPT_RX.sub("", text)
    assert not mod.is_stubbed(plain) and mod.is_lead_cut(plain)
    assert load_check("php_scripts").run("index.php", plain) == []
    assert load_check("php_scripts").run("index.php", _index_php().replace("fbevents.js", "x")), "гейт не має глушити штатний шаблон"


def test_ids_differ_between_branches_and_survive_in_the_cache():
    _fresh_state()
    a, b = mod.stub_id("alpha-br-pt"), mod.stub_id("beta-ch-de")
    assert a != b and re.fullmatch(r"[a-z]{6}", a)
    # кеш: записане значення переживає навіть зміну алгоритму — читаємо файл
    import json
    ids = json.loads(mod._id_path().read_text(encoding="utf-8"))
    ids["alpha-br-pt"] = "zzzzzz"
    mod._id_path().write_text(json.dumps(ids), encoding="utf-8")
    assert mod.stub_id("alpha-br-pt") == "zzzzzz"



def test_branch_without_a_lead_form_is_left_completely_alone():
    """Нема лід-форми (лише пошук/розсилка або взагалі нічого) — ні скрипта,
    ні вирізання PHP: чек мовчить, фікс порожній."""
    _fresh_state()
    no_form = _index_php().replace(FORM, "")
    files = {"index.php": no_form, "sobre.html": "<html><body><p>x</p></body></html>"}
    assert mod.run_branch(dict(files), list(files), "x-br-pt") == []
    assert mod.fix_branch(dict(files), list(files), "x-br-pt") == []
    assert "isset($_GET['email'])" in files["index.php"], "PHP не чіпався"
    # сторінка без форми у вітці З формою: скрипт лише там, де форма
    files = {"index.php": _index_php(), "sobre.html": "<html><body><p>x</p></body></html>"}
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "x-br-pt")}
    assert set(acts) == {"index.php"} and "setTimeout" not in files["sobre.html"]


def test_home_without_a_form_but_with_lead_php_cut_keeps_php_scripts_silent():
    """feqevrov/rezmeufiriafkupul/argiwovmozoi 21.10: лід-форма лише на
    /contato, головна без форми. form_stub зрізав лід-PHP на index.php, а
    php_scripts (пофайловий) не бачив скрипта заглушки і кричав «блок
    returnPage відсутній» ×7."""
    _fresh_state()
    home = _index_php().replace(FORM, "")              # головна без форми
    files = {"index.php": home, "contato/index.html": HTML}
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "x-br-pt")}
    assert set(acts) == {"index.php", "contato/index.html"}
    cut = acts["index.php"]
    assert mod.is_lead_cut(cut) and not mod.is_stubbed(cut)
    ps = load_check("php_scripts")
    assert ps.run("index.php", cut) == []
    assert not mod.is_lead_cut(_index_php()), "штатний шаблон (усі три блоки) — не зріз"


def test_all_50_variants_are_structurally_a_stub_and_choice_is_deterministic():
    """Усі 50 варіантів у form_stub_variants дають скрипт, який is_stubbed
    упізнає; variant_index детермінований за віткою і покриває весь діапазон."""
    import sys, importlib
    sys.path.insert(0, str(ROOT))
    import checks._form_stub_variants as fv
    importlib.reload(fv)
    for i in range(50):
        sc = fv.render(i, "abcdef", mod.I18N["pt"], "thank-you.html")
        assert mod.STUB_SCRIPT_RX.search(sc), f"варіант #{i} провалив fingerprint"
        assert "<script>" in sc and "</script>" in sc
    # той самий branch → той самий index; різні → покривають >5 варіантів
    assert mod.variant_index("x") == mod.variant_index("x")
    seen = {mod.variant_index(f"br-{i:03d}-br-pt") for i in range(200)}
    assert len(seen) >= 20, seen


if __name__ == "__main__":
    run(dict(globals()))
