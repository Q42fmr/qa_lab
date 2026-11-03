"""Форма-сателіт: сабміт не доходить до index.php.

Кейс — п'ять віток (`mezegabe-br-pt`, `orpuglu-stazoa-br-pt`,
`palallitu-br-pt`, `peluzaj-nolv-br-pt`, `quibtemo-br-pt`): у кожній рівно дві
форми без `action`. Форма в `index.php` без `action` — правильно (сабміт на
себе потрапляє в той самий файл, де стоїть php-блок), а на `contato.html` та
сама відсутність означає сабміт у статичний html: лід зникає без пікселя й без
редіректу на подяку.

Блок ловлі ліда (`cache/mezegabe-br-pt/index.php:578`) читає рівно чотири поля
з `$_GET` — `email`, `name`, `phone`, `lastname` — і спрацьовує на наявності
`email` АБО `name`. Чек вирівнює лише `email` і перше `type=text`: телефон
вбиває переставлений `ltrim('+', $_GET['phone'])` у шаблоні вайтів незалежно
від імені поля, а `lastname` індекс-форма не містить у жодній із п'яти віток.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, load_check, run                   # noqa: E402

sys.path.insert(0, str(ROOT))

mod = load_check("form_action")

# --- фікстури, зняті з cache/orpuglu-stazoa-br-pt (поля португальською) ---
INDEX_FORM = """<form id="contactForm" class="form-card">
  <input type="text" name="name" placeholder="Seu nome completo">
  <input type="email" name="email" placeholder="seu@email.com">
  <input type="tel" name="phone" placeholder="+55 21 99999-9999">
  <textarea name="message" placeholder="Conte brevemente"></textarea>
  <button type="submit">Enviar</button>
</form>"""

LEAD_BLOCK = """<?php
if (isset($_GET['email']) || isset($_GET['name'])) {
   $email = $_GET['email'] ?? '';
   $name = $_GET['name'] ?? '';
   exit();
}
?>"""


def _index(form=INDEX_FORM, lead=LEAD_BLOCK):
    return f"<html><body>{lead}\n{form}</body></html>"


def test_fields_reads_type_and_name_in_order():
    got = mod._fields(INDEX_FORM)
    assert got == [("text", "name"), ("email", "email"),
                   ("tel", "phone"), ("textarea", "message")], got


def test_fields_skips_inputs_without_name():
    form = '<form><input type="text"><input type="email" name="email"></form>'
    assert mod._fields(form) == [("email", "email")], mod._fields(form)


def test_fields_treats_textarea_and_select_tag_as_type():
    form = '<form><textarea name="m"></textarea><select name="s"></select></form>'
    assert mod._fields(form) == [("textarea", "m"), ("select", "s")]


def test_canon_takes_only_email_and_first_text():
    assert mod._canon(INDEX_FORM) == {"text": "name", "email": "email"}


def test_canon_ignores_second_text_field():
    form = ('<form><input type="text" name="first">'
            '<input type="text" name="second">'
            '<input type="email" name="mail"></form>')
    assert mod._canon(form) == {"text": "first", "email": "mail"}


def test_canon_empty_when_form_has_no_named_fields():
    assert mod._canon("<form><button>go</button></form>") == {}


def test_index_state_reports_lead_block_and_standard_form():
    form, canon, lead, std = mod._index_state(_index())
    assert lead is True and std is True
    assert canon == {"text": "name", "email": "email"}
    assert form.startswith("<form id=\"contactForm\"")


def test_index_state_without_lead_block():
    _, _, lead, std = mod._index_state(_index(lead=""))
    assert lead is False and std is True


def test_index_state_form_with_action_is_not_standard():
    bad = INDEX_FORM.replace("<form ", '<form action="send.php" ', 1)
    _, _, lead, std = mod._index_state(_index(form=bad))
    assert lead is True and std is False


def test_index_state_form_with_method_is_not_standard():
    bad = INDEX_FORM.replace("<form ", '<form method="post" ', 1)
    _, _, _, std = mod._index_state(_index(form=bad))
    assert std is False


def test_index_state_no_form_at_all():
    form, canon, lead, std = mod._index_state(f"<html>{LEAD_BLOCK}</html>")
    assert form is None and canon == {} and lead is True and std is False


def test_index_state_empty_text():
    assert mod._index_state("") == (None, {}, False, False)

def test_index_state_skips_first_form_without_canon():
    search = '<form><input type="text" name="q"></form>'
    text = f"<html><body>{search}\n{LEAD_BLOCK}\n{INDEX_FORM}</body></html>"
    form, canon, lead, std = mod._index_state(text)
    assert canon == {"text": "name", "email": "email"}, canon
    assert form.startswith("<form id=\"contactForm\"")


def test_index_state_skips_nameless_search_form():
    search = '<form><input type="text"><button>Go</button></form>'
    text = f"<html><body>{search}\n{LEAD_BLOCK}\n{INDEX_FORM}</body></html>"
    form, canon, lead, std = mod._index_state(text)
    assert canon == {"text": "name", "email": "email"}, canon


def test_index_state_skips_newsletter_email_only_form():
    newsletter = '<form><input type="email" name="EMAIL"><button>Subscribe</button></form>'
    text = f"<html><body>{newsletter}\n{LEAD_BLOCK}\n{INDEX_FORM}</body></html>"
    form, canon, lead, std = mod._index_state(text)
    assert canon == {"text": "name", "email": "email"}, canon


def test_index_state_no_reference_when_form_has_no_email():
    only_text = '<form><input type="text" name="name"></form>'
    text = f"<html><body>{LEAD_BLOCK}\n{only_text}</body></html>"
    assert mod._index_state(text) == (None, {}, True, False)


def test_lead_rx_catches_and_variant():
    text = ("if (isset($_GET['email']) && isset($_GET['name'])) { exit(); }")
    assert mod.LEAD_RX.search(text), text


def test_lead_rx_catches_or_variant():
    assert mod.LEAD_RX.search(LEAD_BLOCK)


def test_index_for_points_at_the_index_of_the_same_folder():
    assert mod._index_for("contato.html") == "index.php"
    assert mod._index_for("blog/contato.html") == "blog/index.php"


def test_run_branch_exists_and_does_not_crash():
    assert hasattr(mod, "run_branch")
    assert mod.run_branch({}, []) == []



def test_js_submit_rx_catches_three_shapes():
    for s in ("el.addEventListener('submit', fn)", '<form onsubmit="go()">',
              "e.preventDefault()"):
        assert mod.JS_SUBMIT_RX.search(s), s


def test_js_submit_rx_silent_on_plain_page():
    assert not mod.JS_SUBMIT_RX.search(
        '<script src="js/bootstrap.bundle.min.js"></script>')

# --- сателітна форма: та сама розмітка, поля португальською ---
SAT_PT = """<form id="contactPageForm" class="form-card">
  <input type="text" name="nome" placeholder="Seu nome">
  <input type="text" name="sobrenome" placeholder="Seu sobrenome">
  <input type="email" name="email" placeholder="seu@email.com">
  <input type="tel" name="telefone" placeholder="+55 21 99999-9999">
  <select name="assunto"><option>—</option></select>
  <textarea name="mensagem"></textarea>
  <button type="submit">Enviar</button>
</form>"""


def _page(form=SAT_PT, extra=""):
    return f"<html><body>{extra}\n{form}</body></html>"


def _branch(sat=None, idx=None):
    """Мінімальна вітка: index.php + contato.html."""
    return {INDEX_PATH: idx if idx is not None else _index(),
            SAT_PATH: sat if sat is not None else _page()}


INDEX_PATH, SAT_PATH = "index.php", "contato.html"


def _run(files):
    return mod.run_branch(dict(files), list(files))


def test_targets_finds_satellite_form_without_action():
    got = mod._targets(_branch())
    assert list(got) == [SAT_PATH], got
    assert len(got[SAT_PATH]) == 1
    line, form = got[SAT_PATH][0]
    assert line == 2 and form.startswith('<form id="contactPageForm"')


def test_targets_never_returns_index_php():
    files = {INDEX_PATH: _index()}
    assert mod._targets(files) == {}


def test_targets_skips_form_that_already_has_action():
    sat = SAT_PT.replace("<form ", '<form action="send.php" ', 1)
    assert mod._targets(_branch(sat=sat)) == {}


def test_targets_skips_non_page_files():
    files = dict(_branch())
    files["js/main.js"] = "<form></form>"
    assert list(mod._targets(files)) == [SAT_PATH]


def test_targets_skips_form_without_both_aligned_fields():
    """Пошуковий бокс без name-полів — не лід-форма, чек мовчить."""
    search = '<form id="search"><input id="search" type="text"></form>'
    files = dict(_branch(sat=_page(form=search)))
    assert mod._targets(files) == {}


def test_targets_skips_form_with_only_email_field():
    """Підписка на новини (лише email, без text) — не лід-форма."""
    sub = '<form id="subscribe-form"><input type="email" name="subscribe-email"></form>'
    files = dict(_branch(sat=_page(form=sub)))
    assert mod._targets(files) == {}


def test_run_reports_error_when_all_three_gates_pass():
    iss = _run(_branch())
    assert len(iss) == 1, iss
    assert iss[0]["path"] == SAT_PATH and iss[0]["severity"] == "error"
    assert "автофікс" in iss[0]["message"]


def test_run_silent_on_search_box_without_named_fields():
    search = '<form id="search"><input id="search" type="text"></form>'
    assert _run(_branch(sat=_page(form=search))) == []


def test_run_silent_on_newsletter_form_with_only_email():
    sub = '<form id="subscribe-form"><input type="email" name="subscribe-email"></form>'
    assert _run(_branch(sat=_page(form=sub))) == []


def test_run_warns_when_index_has_no_lead_block():
    iss = _run(_branch(idx=_index(lead="")))
    assert len(iss) == 1 and iss[0]["severity"] == "warn"
    assert "php-блока" in iss[0]["message"]


def test_verdict_gives_canon_only_in_the_error_branch():
    """Task 3 вирівнює поля лише там, де гейт дозволив автофікс."""
    sev, _msg, canon = mod._verdict(_branch(), SAT_PATH)
    assert sev == "error" and canon == {"text": "name", "email": "email"}
    bad = INDEX_FORM.replace("<form ", '<form method="post" ', 1)
    js = _page(extra="<script>f.addEventListener('submit', go)</script>")
    for files in (_branch(idx=_index(lead="")), _branch(idx=_index(form=bad)),
                  _branch(sat=js)):
        sev, _msg, canon = mod._verdict(files, SAT_PATH)
        assert sev == "warn" and canon == {}, (sev, canon)
    assert mod._verdict({SAT_PATH: _page()}, SAT_PATH) == (None, "", {})


def test_run_warns_when_index_form_is_not_standard():
    bad = INDEX_FORM.replace("<form ", '<form method="post" ', 1)
    iss = _run(_branch(idx=_index(form=bad)))
    assert len(iss) == 1 and iss[0]["severity"] == "warn"
    assert "не стандартна" in iss[0]["message"]


def test_run_reports_missing_lead_block_before_unusable_reference():
    """Впали й G1, й G2 -> каже про php-блок: порядок той самий, що в fix_branch."""
    idx = f"<html><body>{INDEX_FORM}</body></html>".replace(
        "<form ", '<form method="post" ', 1)
    iss = _run(_branch(idx=idx))
    assert len(iss) == 1 and iss[0]["severity"] == "warn"
    assert "php-блока" in iss[0]["message"], iss[0]["message"]


def test_run_warns_when_index_has_no_form_at_all():
    iss = _run(_branch(idx=f"<html>{LEAD_BLOCK}</html>"))
    assert len(iss) == 1 and iss[0]["severity"] == "warn"
    assert "не стандартна" in iss[0]["message"]


def test_run_warns_when_index_has_no_valid_reference_form():
    """index.php має php-блок і форму, але без email-поля — немає еталона."""
    only_text = '<form><input type="text" name="name"></form>'
    idx = f"<html><body>{LEAD_BLOCK}\n{only_text}</body></html>"
    iss = _run(_branch(idx=idx))
    assert len(iss) == 1 and iss[0]["severity"] == "warn"
    assert "не стандартна" in iss[0]["message"]


def test_run_warns_when_page_has_js_submit_handler():
    sat = _page(extra="<script>f.addEventListener('submit', go)</script>")
    iss = _run(_branch(sat=sat))
    assert len(iss) == 1 and iss[0]["severity"] == "warn"
    assert "js" in iss[0]["message"]


def test_run_silent_without_index_php_in_the_folder():
    assert _run({SAT_PATH: _page()}) == []


def test_run_silent_when_form_already_has_action():
    sat = SAT_PT.replace("<form ", '<form action="./" ', 1)
    assert _run(_branch(sat=sat)) == []


def test_run_uses_index_of_the_same_folder():
    files = {"index.php": _index(), "sub/index.php": _index(lead=""),
             "sub/contato.html": _page()}
    iss = _run(files)
    assert len(iss) == 1 and iss[0]["path"] == "sub/contato.html"
    assert iss[0]["severity"] == "warn", iss      # у sub/index.php блока немає


def test_run_reports_every_form_of_the_page():
    sat = _page(form=SAT_PT + "\n" + SAT_PT)
    assert len(_run(_branch(sat=sat))) == 2


def _fix(files):
    acts = mod.fix_branch(dict(files), list(files))
    for a in acts:
        assert a["type"] == "edit", a          # ніколи не create/delete
    return {a["path"]: a["content"] for a in acts}


def test_fix_adds_action_to_satellite_form():
    out = _fix(_branch())
    assert list(out) == [SAT_PATH], out
    assert '<form action="./" id="contactPageForm"' in out[SAT_PATH]


def test_fix_renames_portuguese_name_to_reference_name():
    out = _fix(_branch())[SAT_PATH]
    assert 'name="name" placeholder="Seu nome"' in out
    assert 'name="nome"' not in out


def test_fix_leaves_out_of_scope_fields_byte_for_byte():
    out = _fix(_branch())[SAT_PATH]
    for keep in ('name="sobrenome"', 'name="telefone"',
                 'name="assunto"', 'name="mensagem"'):
        assert keep in out, keep


def test_fix_never_touches_index_php():
    out = _fix(_branch())
    assert INDEX_PATH not in out


def test_fix_is_idempotent():
    once = _fix(_branch())[SAT_PATH]
    twice = _fix({INDEX_PATH: _index(), SAT_PATH: once})
    assert twice == {}, twice


def test_fix_english_fields_get_action_only():
    sat_en = SAT_PT.replace('name="nome"', 'name="name"')
    out = _fix(_branch(sat=_page(form=sat_en)))[SAT_PATH]
    assert '<form action="./"' in out
    assert out.replace('<form action="./"', "<form") == _page(form=sat_en)


def test_fix_does_nothing_without_lead_block():
    assert _fix(_branch(idx=_index(lead=""))) == {}


def test_fix_does_nothing_when_index_form_not_standard():
    bad = INDEX_FORM.replace("<form ", '<form action="x" ', 1)
    assert _fix(_branch(idx=_index(form=bad))) == {}


def test_fix_does_nothing_with_js_submit_handler():
    sat = _page(extra="<script>f.addEventListener('submit', go)</script>")
    assert _fix(_branch(sat=sat)) == {}


def test_fix_skips_rename_when_target_name_is_taken():
    """`nome` -> `name` не робиться, якщо `name` у формі вже зайняте."""
    sat = SAT_PT.replace('name="sobrenome"', 'name="name"')
    out = _fix(_branch(sat=_page(form=sat)))[SAT_PATH]
    assert 'name="nome"' in out          # перейменування скасовано
    assert out.count('name="name"') == 1
    assert '<form action="./"' in out    # action усе одно додано


def test_fix_renames_only_first_text_field():
    sat = ('<form><input type="text" name="a"><input type="text" name="b">'
           '<input type="text" name="c"><input type="email" name="email">'
           '</form>')
    out = _fix(_branch(sat=_page(form=sat)))[SAT_PATH]
    assert 'name="name"' in out and 'name="b"' in out and 'name="c"' in out


def test_fix_leaves_a_form_without_email_field_untouched():
    """Форма без email не лід-форма (P0 Task 2) — фікс її не чіпає."""
    sat = '<form><input type="text" name="nome"></form>'
    assert _fix(_branch(sat=_page(form=sat))) == {}


def test_fix_keeps_single_quotes_of_the_original_attribute():
    sat = ("<form><input type='text' name='nome'>"
           "<input type='email' name='email'></form>")
    out = _fix(_branch(sat=_page(form=sat)))[SAT_PATH]
    assert "name='name'" in out


def test_fix_touches_every_form_of_the_page():
    sat = _page(form=SAT_PT + "\n" + SAT_PT)
    out = _fix(_branch(sat=sat))[SAT_PATH]
    assert out.count('<form action="./"') == 2


def test_fix_adds_action_once_per_form_match():
    """Незакрита форма заганяє два `<form`-теги в ОДИН збіг FORM_RX:
    `count=1` мусить торкнутись лише зовнішнього."""
    sat = ('<form id="outer"><form id="inner">'
           '<input type="text" name="nome">'
           '<input type="email" name="email"></form>')
    out = mod._apply(sat, {"text": "name", "email": "email"})
    assert out.count('<form action="./"') == 1, out


def test_fix_leaves_a_sibling_form_that_already_has_action():
    paid = ('<form action="https://list-manage.com/subscribe" method="post">'
            '<input type="text" name="fname">'
            '<input type="email" name="EMAIL"></form>')
    sat = _page(form=paid + "\n" + SAT_PT)
    out = _fix(_branch(sat=sat))[SAT_PATH]
    assert out.count('action=') == 2, out       # чужий + дописаний
    assert 'name="EMAIL"' in out and 'name="fname"' in out


def test_fix_leaves_non_lead_form_without_action_untouched():
    """`nugevilcar-my-en/contact.html`: лід-форма і футерна підписка без
    `action` на одній сторінці — фікс мутує ЛИШЕ лід-форму."""
    subscribe = ('<form id="subscribe-form">'
                 '<input type="email" name="subscribe-email"></form>')
    sat = _page(form=SAT_PT + "\n" + subscribe)
    out = _fix(_branch(sat=sat))[SAT_PATH]
    assert '<form id="subscribe-form">' in out
    assert 'name="subscribe-email"' in out


def test_fix_does_not_rename_lastname_into_the_first_name_slot():
    """`lastname` іде першим `type=text` позиційно, але php-блок читає його
    сам (BLOCK_FIELDS) — позиційне правило не має його чіпати."""
    sat = ('<form id="contactPageForm" class="form-card">'
           '<input type="text" name="lastname" placeholder="Nom de famille">'
           '<input type="text" name="firstname" placeholder="Prenom">'
           '<input type="email" name="email">'
           '</form>')
    out = _fix(_branch(sat=_page(form=sat)))[SAT_PATH]
    assert 'name="lastname"' in out
    assert 'name="firstname"' not in out
    assert 'name="name"' in out


if __name__ == "__main__":
    run(dict(globals()))
