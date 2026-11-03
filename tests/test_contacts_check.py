"""Email-домен вайта мусить бути літералом {{DOMAIN}}.

Кейси зняті з корпусу (150 віток, 1394 файли):
  * реальний витік бренду — info@ceopapltizb.com.my у mailto і в тексті
    (вітка ceepohj-motc-my-en, privacy-policy.html), при семи правильних
    info@{{DOMAIN}} у тій самій вітці;
  * усі 147 не-літеральних пошт корпусу — у placeholder= і всі прикладові
    (ihre@email.ch, su@correo.com, your@email.com, example@company.ae),
    причому у СПРАВНИХ вайтах: це UX-підказка, а не контакт;
  * {{DOMAIN_NAME}} — теж літерал, ним володіє окремий чек wrong_literal.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

c = load_check("contacts")


# ---------------------------------------------------------------- детект
def test_real_domain_in_mailto_and_text_is_flagged():
    src = ('<p>Contact us at <a href="mailto:info@ceopapltizb.com.my">'
           'info@ceopapltizb.com.my</a></p>')
    issues = c.run("privacy-policy.html", src)
    assert len(issues) == 2, issues
    assert all(i["severity"] == "error" for i in issues), issues
    assert "ceopapltizb.com.my" in issues[0]["message"], issues


def test_literal_domain_is_clean():
    src = '<a href="mailto:info@{{DOMAIN}}">info@{{DOMAIN}}</a>'
    assert c.run("index.php", src) == []


def test_domain_name_literal_is_left_to_wrong_literal_check():
    """{{DOMAIN_NAME}} — уже літерал; хост-контекст фіксить wrong_literal."""
    src = '<a href="mailto:info@{{DOMAIN_NAME}}">info@{{DOMAIN_NAME}}</a>'
    assert c.run("index.php", src) == []


def test_js_email_gets_the_bound_domain_not_the_literal():
    """754/1027 br-pt (27.10): пошта живе у polish.js («polish»-скрипт малює
    контакти в рантаймі) — contato.loja@gmail.com, loja@lojadoador.com.br.
    Деплой підставляє {{DOMAIN}} лише в html/php, тож у js — реальний
    домен вітки з ClickUp (так уже зроблено руками на cagu-alejfaq/cluakoje).
    Без підв'язаного домену — лише знахідка, без фіксу."""
    c._domain_for = lambda branch: "lojaexemplo.pro"
    src = ("var html = '<a href=\"mailto:contato.loja@gmail.com\">contato.loja@gmail.com</a>';\n"
           "var ok = 'faleconosco@lojaexemplo.pro';")
    files = {"polish.js": src}
    issues = c.run_branch(dict(files), list(files), "codi-alhu-chelueh-br-pt")
    assert len(issues) == 2 and all(i["path"] == "polish.js" for i in issues), issues
    assert "contato.loja@lojaexemplo.pro" in issues[0]["message"]
    acts = {a["path"]: a["content"] for a in c.fix_branch(dict(files), list(files), "codi-alhu-chelueh-br-pt")}
    assert acts["polish.js"] == src.replace("@gmail.com", "@lojaexemplo.pro"), acts
    fixed = {"polish.js": acts["polish.js"]}
    assert c.run_branch(dict(fixed), list(fixed), "codi-alhu-chelueh-br-pt") == []
    # html у тій самій вітці — як і раніше, літерал
    assert c.fix("index.php", "<p>contato.loja@gmail.com</p>") == "<p>contato.loja@{{DOMAIN}}</p>"
    # домену немає → знахідка «вручну», фіксу немає
    c._domain_for = lambda branch: None
    issues = c.run_branch(dict(files), list(files), "codi-alhu-chelueh-br-pt")
    assert len(issues) == 3 and all("вручну" in i["message"] for i in issues), issues
    assert c.fix_branch(dict(files), list(files), "codi-alhu-chelueh-br-pt") == []
    # мініфіковані/вендорні js не судимо
    assert c.run_branch({"jquery.min.js": src, "_ext/x.js": src}, ["jquery.min.js", "_ext/x.js"], "x-br-pt") == []


def test_placeholder_example_is_not_flagged():
    for src in ('<input type="email" placeholder="ihre@email.ch">',
                "<input type='email' placeholder='su@correo.com'>",
                '<input placeholder="your@email.com" name="email">',
                '<input placeholder="example@company.ae">'):
        assert c.run("index.php", src) == [], src


def test_asset_with_at_sign_is_not_an_email():
    src = ('<img src="images/hero@2x.png" srcset="images/hero@3x.webp 3x">'
           '<style>.a{background:url(img/logo@2x.jpg)}</style>')
    assert c.run("index.php", src) == []


def test_line_numbers_point_at_the_email():
    src = "<html>\n<body>\n<p>write: sales@acme-corp.io</p>\n</body>\n</html>"
    issues = c.run("contact.html", src)
    assert len(issues) == 1 and issues[0]["line"] == 3, issues


def test_several_emails_on_one_line():
    src = '<p>privacy@acme.io and legal@acme.io</p>'
    assert len(c.run("terms.html", src)) == 2


def test_no_emails_is_clean():
    assert c.run("index.php", "<p>no contacts here</p>") == []


# ---------------------------------------------------------------- автофікс

def test_url_authority_is_not_an_email():
    """Sentry DSN з ifipor-br-pt: ключ@хост усередині URL — не пошта.
    Заміна зламала б збір помилок."""
    src = ('"SENTRY_DSN_JS":"https:\\/\\/5552835e822c4c8db5070306b2535ef3'
           '@o186239.ingest.sentry.io\\/1281569"')
    assert c.run("index.php", src) == []
    assert c.fix("index.php", src) == src


def test_plain_url_with_basic_auth_is_not_an_email():
    src = '<a href="https://user@internal.host.com/path">x</a>'
    assert c.run("index.php", src) == []


def test_sentence_in_placeholder_is_still_checked():
    """Приклад — це САМЕ адреса. Генератор запхав у placeholder ціле речення
    з живим контактом (bupvfiz-rectem-ch-de), і виняток ковтав витік."""
    src = ('<input class="form-control" name="email" placeholder="Bei Fragen '
           'erreichen Sie uns jederzeit unter info@SkiVentureBundlesRental'
           '@support.com. Wir freuen uns auf Ihre Nachricht.">')
    issues = c.run("contacts.html", src)
    assert issues, "речення в placeholder — не приклад адреси"
    assert "support.com" in issues[0]["message"], issues


def test_brand_name_as_url_login_is_an_email_leak():
    """`<meta content="https://PensionEaseResolutionService@support.com/…">`
    (retohozoev-segsihe-ch-de): у позиції логіна стоїть назва вайта, тобто
    той самий витік бренду. Ключ DSN натомість завжди має цифри."""
    src = ('<meta content="https://PensionEaseResolutionService@support.com'
           '/og_image.png" property="og:image"/>')
    issues = c.run("about.html", src)
    assert issues, "бренд у логіні URL мусить ловитись"
    assert "support.com" in issues[0]["message"], issues


def test_short_login_in_url_is_still_skipped():
    """Поріг у 8 літер лишає звичайний basic-auth поза підозрою."""
    assert c.run("index.php", '<a href="https://user@internal.host.com/p">x</a>') == []


def test_reserved_example_domains_are_not_flagged():
    """RFC 2606: example.com/.net/.org і TLD .test/.invalid/.localhost
    зарезервовані під приклади — реальним брендом бути не можуть.
    Кейс wapluk-sevno-my-en: <p class="form-helper">e.g. razif@example.com</p>."""
    for src in ('<p class="form-helper">e.g. razif@example.com</p>',
                "<p>you@example.org</p>",
                "<p>a@example.net</p>",
                "<p>b@foo.test</p>",
                "<p>c@bar.invalid</p>"):
        assert c.run("index.php", src) == [], src
        assert c.fix("index.php", src) == src, src


def test_real_domain_next_to_reserved_one_is_still_fixed():
    src = "<p>e.g. you@example.com but write to info@real-brand.de</p>"
    out = c.fix("index.php", src)
    assert "you@example.com" in out, out
    assert "info@{{DOMAIN}}" in out, out


# ---------------------------------------------------------------- автофікс
def test_fix_rewrites_domain_keeps_local_part():
    src = ('<a href="mailto:info@ceopapltizb.com.my">info@ceopapltizb.com.my</a>')
    out = c.fix("privacy-policy.html", src)
    assert out == ('<a href="mailto:info@{{DOMAIN}}">info@{{DOMAIN}}</a>'), out
    assert c.run("privacy-policy.html", out) == []


def test_fix_keeps_different_local_parts():
    out = c.fix("terms.html", "<p>privacy@acme.io, legal@acme.io, info@acme.io</p>")
    assert out == "<p>privacy@{{DOMAIN}}, legal@{{DOMAIN}}, info@{{DOMAIN}}</p>", out


def test_fix_handles_subdomains_and_long_tld():
    out = c.fix("index.php", "<p>hello@mail.corp.example.co.uk</p>")
    assert out == "<p>hello@{{DOMAIN}}</p>", out


def test_fix_preserves_local_part_case():
    out = c.fix("index.php", "<p>Info.Sales@Acme-Corp.IO</p>")
    assert out == "<p>Info.Sales@{{DOMAIN}}</p>", out


def test_fix_does_not_touch_placeholder():
    src = ('<input placeholder="ihre@email.ch">'
           '<a href="mailto:info@real-brand.de">info@real-brand.de</a>')
    out = c.fix("index.php", src)
    assert 'placeholder="ihre@email.ch"' in out, out
    assert out.count("info@{{DOMAIN}}") == 2, out


def test_fix_does_not_touch_literals():
    src = '<p>info@{{DOMAIN}} and legal@{{DOMAIN_NAME}}</p>'
    assert c.fix("index.php", src) == src


def test_fix_is_idempotent():
    once = c.fix("index.php", "<p>info@example.com</p>")
    assert c.fix("index.php", once) == once


def test_fix_in_json_ld():
    src = '<script type="application/ld+json">{"email": "info@acme.com"}</script>'
    out = c.fix("index.php", src)
    assert '"email": "info@{{DOMAIN}}"' in out, out


def test_fix_noop_without_emails():
    src = "<p>@media and @apply and npm i @babel/core</p>"
    assert c.fix("index.php", src) == src
    assert c.run("index.php", src) == []


# ---------------------------------------------------------------- метадані
def test_check_is_autofix_group_without_phone_logic():
    assert c.GROUP == "auto"
    assert hasattr(c, "fix")
    src = '<a href="tel:+41715198326">call</a>'
    assert c.run("index.php", src) == [], "телефон більше не перевіряється"


if __name__ == "__main__":
    run(dict(globals()))
