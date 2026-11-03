"""geo_phone: телефону немає ніде — фікс додає з гео-бази номерів.

Кейс bucrung-brailluqr 01.10 («добавить номер к контактам и в футер»).
БД — корпус наших віток + офіційні fiction-діапазони (NANP 555-01XX,
Ofcom 7946/496)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                              # noqa: E402

mod = load_check("geo_phone")

NOPHONE = """<html><body>
<main><h1>x</h1><p>Entre em contato: beleza</p></main>
<footer class="bg-x"><div>
  <p class="text-zinc-400 text-xs">© 2026 Foo Ltda.</p>
</div></footer>
</body></html>"""

CONTACT = """<html><body>
<main>
  <p class="text-sm"><a href="mailto:info@foo.pro">info@foo.pro</a></p>
</main>
<footer><p>© 2026 Foo.</p></footer>
</body></html>"""


def test_missing_phone_is_detected_with_deterministic_number():
    files = {"index.html": NOPHONE}
    issues = mod.run_branch(dict(files), list(files), "nwf-x-br-pt")
    assert len(issues) == 1 and issues[0]["severity"] == "error"
    assert "немає телефону" in issues[0]["message"]
    assert "+55" in issues[0]["message"]
    again = mod.run_branch(dict(files), list(files), "nwf-x-br-pt")
    assert issues == again                       # детермінізм за віткою


def test_fix_adds_tel_link_into_footer_and_contacts():
    BRANCH = "nwf-x-br-pt"
    files = {"index.html": NOPHONE, "contact/index.html": CONTACT}
    acts = {a["path"]: a for a in
            mod.fix_branch(dict(files), list(files), BRANCH)}
    num = mod._pick(BRANCH)
    idx = acts["index.html"]["content"]
    assert f'<a href="tel:{mod._tel_href(num)}">{num}</a>' in idx
    assert '<p class="text-zinc-400 text-xs">' in idx.split("tel:")[1][:200] \
        or 'class="text-zinc-400' in idx            # стилі футера клоновано
    ct = acts["contact/index.html"]["content"]
    assert ct.count(num) == 2                       # футер + mailto-блок
    # після фікса — тихо і нуль дій
    fixed = {p: a["content"] for p, a in acts.items()}
    assert mod.run_branch(dict(fixed), list(fixed), BRANCH) == []
    assert mod.fix_branch(dict(fixed), list(fixed), BRANCH) == []


def test_existing_phone_keeps_check_silent():
    files = {"index.html": NOPHONE.replace(
        "beleza", '<a href="tel:+5511999887766">+55 11 99988-7766</a>')}
    assert mod.run_branch(dict(files), list(files), "nwf-x-br-pt") == []
    assert mod.fix_branch(dict(files), list(files), "nwf-x-br-pt") == []


def test_unicode_range_in_font_css_is_not_a_phone():
    # кейс codleuururekjq 14.10: раннер дає fix_branch УСІ текстові файли,
    # детект — лише FILES; «U+0400-045F, U+0490-0491» у CSS Google Fonts
    # читалось як номер, і фікс мовчав, поки чек лишався червоним
    css = ("@font-face{font-family:'Montserrat';unicode-range:U+0301, "
           "U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116;}")
    files = {"index.html": NOPHONE, "fonts/montserrat.css": css}
    BRANCH = "nwf-x-br-pt"
    assert mod.run_branch(dict(files), list(files), BRANCH)
    acts = mod.fix_branch(dict(files), list(files), BRANCH)
    num = mod._pick(BRANCH)
    assert [a["path"] for a in acts] == ["index.html"]
    assert f'href="tel:{mod._tel_href(num)}"' in acts[0]["content"]
    # той самий CSS ІНЛАЙНОМ у <style> головної (sokkoruuzosnacav 21.10):
    # сторінка — у FILES, і «U+0490-0491» глушило чек на вітці без телефону
    inline = NOPHONE.replace("<body>", "<style>" + css + "</style><body>", 1)
    assert "<style>" in inline
    assert mod.run_branch({"index.html": inline}, ["index.html"], BRANCH)
    assert not mod._branch_has_phone({"index.html": inline})


def test_footer_without_p_or_address_clones_the_copyright_div():
    """sokkoruuzosnacav 21.10: футер з одним <div class="footer-text">© …</div>
    — чек обіцяв телефон, фікс давав 0 дій."""
    page = ('<html><body><main><h1>x</h1></main><footer class="site-footer">'
            '<div class="footer-text">\n2025 © SOS Móveis Antigos. Todos direitos reservados.</div>'
            '</footer></body></html>')
    files = {"index.php": page}
    BRANCH = "sokkoruuzosnacav-cop-br-pt"
    assert mod.run_branch(dict(files), list(files), BRANCH)
    acts = mod.fix_branch(dict(files), list(files), BRANCH)
    num = mod._pick(BRANCH)
    assert acts and f'<div class="footer-text"><a href="tel:{mod._tel_href(num)}">{num}</a></div>' in acts[0]["content"], acts
    fixed = {"index.php": acts[0]["content"]}
    assert mod.run_branch(fixed, list(fixed), BRANCH) == []


def test_labeled_local_number_on_the_site_beats_the_geo_base():
    """sokkoruuzosnacav 21.10: «Telefone: (11) 3034-2469» у кожному пості,
    а фікс поклав у футер чужий номер з гео-бази. Свій номер не рахується
    «телефон є» (QA хоче його у підвалі), але у футер іде саме він."""
    post = ('<html><body><main><p>S.O.S Móveis Antigos. Telefone: (11) 3034-2469 / (11) 3812-0169 '
            'WhatsApp: (11) 97543-9397</p></main><footer><p class="f">© 2026</p></footer></body></html>')
    files = {"index.php": post}
    BRANCH = "sokkoruuzosnacav-cop-br-pt"
    issues = mod.run_branch(dict(files), list(files), BRANCH)
    assert issues and "зі сторінок вайта" in issues[0]["message"] and "+55 (11) 3034-2469" in issues[0]["message"], issues
    acts = mod.fix_branch(dict(files), list(files), BRANCH)
    assert acts and 'href="tel:+551130342469">+55 (11) 3034-2469</a>' in acts[0]["content"], acts[0]["content"][-300:]
    fixed = {"index.php": acts[0]["content"]}
    assert mod.run_branch(fixed, list(fixed), BRANCH) == []
    # без підпису («CEP 04086-900» чи ціна) — не телефон, іде гео-база
    files2 = {"index.php": NOPHONE.replace("beleza", "CEP 04086-900, R$ 1.250,00")}
    assert mod._site_phone(files2, BRANCH) == ""


def test_phone_only_in_legal_page_does_not_count():
    files = {"index.html": NOPHONE,
             "privacy.html": '<footer><p><a href="tel:+5511888">x</a></p></footer>'}
    issues = mod.run_branch(dict(files), list(files), "nwf-x-br-pt")
    assert issues and "немає телефону" in issues[0]["message"]


def test_locale_without_base_stays_silent():
    files = {"index.html": NOPHONE}
    assert mod.run_branch(dict(files), list(files), "nwf-x-de-de") == []
    assert mod.fix_branch(dict(files), list(files), "nwf-x-de-de") == []


def test_dotted_branch_with_batch_tail_resolves_locale():
    assert mod._locale("bucrung-brailluqr-nojimuek.ca-ca-en-2") == "ca-en"
    assert mod._pick("bucrung-brailluqr-nojimuek.ca-ca-en-2").startswith("+1")


def test_dl_facts_contact_block_gets_phone_row():
    # кейс burnaby: контакти списком фактів <dl><div><dt>E-mail</dt>…
    page = ('<html><body><aside><dl class="nw-facts">'
            '<div><dt>E-mail</dt><dd><a href="mailto:x@y.z">x@y.z</a></dd></div>'
            '</dl></aside><footer><p>© 2026.</p></footer></body></html>')
    files = {"contact/index.html": page, "index.html": NOPHONE}
    acts = {a["path"]: a for a in
            mod.fix_branch(dict(files), list(files), "x.ca-ca-en-2")}
    ct = acts["contact/index.html"]["content"]
    num = mod._pick("x.ca-ca-en-2")
    assert f'<div><dt>Phone</dt><dd><a href="tel:{mod._tel_href(num)}">' in ct
    assert ct.index("Phone") < ct.index("E-mail")   # телефон перед поштою


def test_address_footer_placeholder_gets_replaced():
    # кейс epidoc 02.10: футер на <address>, «Telefono: da inserire»
    page = ('<html><body><footer><div>'
            "<address><b>Chi vende</b><strong>Epidoc</strong><br>"
            "Strada Statale 113, Italia</address>"
            "<address><b>Contatti</b>Telefono: da inserire<br>"
            'Email: <a href="mailto:s@d.x">s@d.x</a></address>'
            "</div></footer></body></html>")
    files = {"index.php": page}
    acts = mod.fix_branch(dict(files), list(files), "mds-x-it-it")
    out = acts[0]["content"]
    num = mod._pick("mds-x-it-it")
    assert f'Telefono: <a href="tel:{mod._tel_href(num)}">{num}</a>' in out
    assert "da inserire<br>Email" not in out
    fixed = {"index.php": out}
    assert mod.run_branch(dict(fixed), list(fixed), "mds-x-it-it") == []


def test_address_footer_without_placeholder_gets_br_line():
    page = ('<html><body><footer>'
            "<address><b>Contatti</b>Email: "
            '<a href="mailto:s@d.x">s@d.x</a></address>'
            "</footer></body></html>")
    files = {"index.php": page}
    acts = mod.fix_branch(dict(files), list(files), "mds-x-it-it")
    out = acts[0]["content"]
    num = mod._pick("mds-x-it-it")
    assert f'<br><a href="tel:{mod._tel_href(num)}">{num}</a></address>' in out


def test_japanese_domestic_number_is_linked_in_place_as_the_sites_own_phone():
    """jp-jp p-36 (26.10): QA «Телефоны не найдены», баєр вимагає телефон на
    кожному вайті. Номер на сайті Є — у домашньому записі «TEL：03-5628-3181»
    без tel:-лінка і без +81, тож ні QA, ні чек його не бачили, а гео-бази
    jp-jp нема (і не треба: чужий номер поверх свого — брехня). Японські
    скрейпи часто без <footer>, тож фікс робить tel:-лінк НА МІСЦІ на кожній
    сторінці; FAX, номери в тегах/скриптах і вже залінковані — не чіпає."""
    home = NOPHONE.replace("Entre em contato: beleza", "お問い合わせ TEL：03-5628-3181（平日 10:00–18:00） FAX 03-5628-3182")
    about = ('<html><body><p>工房 048-473-1901</p><img alt="03-1111-2222"><script>var t="03-3333-4444"</script>'
             '<p>FAX：048-473-1900</p></body></html>')
    files = {"index.php": home, "about/index.html": about}
    issues = mod.run_branch(dict(files), list(files), "crifg-reblono-jp-jp")
    assert len(issues) == 1 and "+81 3-5628-3181" in issues[0]["message"] and "tel:-лінк" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "crifg-reblono-jp-jp")}
    assert 'TEL：<a href="tel:+81356283181">03-5628-3181</a>（平日' in acts["index.php"]
    assert "FAX 03-5628-3182" in acts["index.php"], "факс не телефон"
    ab = acts["about/index.html"]
    assert '<p>工房 <a href="tel:+81484731901">048-473-1901</a></p>' in ab
    assert 'alt="03-1111-2222"' in ab and 'var t="03-3333-4444"' in ab and "FAX：048-473-1900" in ab
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "crifg-reblono-jp-jp") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "crifg-reblono-jp-jp") == []
    # розпізнавання: 4-значний код міста, номер без підпису, індекс — не номер
    assert mod._site_phone({"index.php": "<p>TEL 0743-62-1598</p>"}, "yahoge-kokea-jp-jp") == "+81 743-62-1598"
    assert mod._site_phone({"index.php": "<p>FAX 048-473-1900 ／ 048-473-1901 までお電話ください</p>"}, "mohiol-jp-jp") == "+81 48-473-1901"
    assert mod._site_phone({"index.php": "<p>〒150-0001 東京都渋谷区</p>"}, "mohiol-jp-jp") == ""
    # без жодного номера — як і раніше тиша (бази jp-jp нема)
    assert mod.run_branch({"index.php": NOPHONE}, ["index.php"], "mohiol-jp-jp") == []


if __name__ == "__main__":
    run(dict(globals()))
