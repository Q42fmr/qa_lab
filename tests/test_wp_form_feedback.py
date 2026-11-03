"""wp_form_feedback: CF7 на знятому з WordPress вайті — подяка без wp-json.

Кейс exniclovalsejojzm 02.10: дві wpcf7-форми на contato, api.root вказує
на старий домен; сабміт мовчки вмирає. Фікс: перехоплювач submit (capture)
до CF7-скрипта, подяка мовою сторінки, ідемпотентність за маркером.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run

mod = load_check("wp_form_feedback")

CF7_PAGE = (
    '<!DOCTYPE html><html lang="pt-BR"><head></head><body>'
    '<form action="./index.html#wpcf7-f207-p12-o1" method="post" '
    'class="wpcf7-form init" novalidate="novalidate" data-status="init">'
    '<input type="text" name="your-name"><button type="submit">Enviar'
    '</button></form>'
    '<script id="contact-form-7-js-before">var wpcf7 = {"api":{"root":'
    '"https:\\/\\/www.exniclovalsejojzm.com.br\\/wp-json\\/"}};</script>'
    '</body></html>')

PLAIN_PAGE = ('<!DOCTYPE html><html lang="pt-BR"><body>'
              '<form action="./obrigado.html" method="get">'
              '<button type="submit">Enviar</button></form></body></html>')


def test_cf7_form_is_flagged():
    issues = mod.run("contato/index.html", CF7_PAGE)
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "error"
    assert "wp-json" in issues[0]["message"]


def test_plain_form_is_silent():
    assert mod.run("contato/index.html", PLAIN_PAGE) == []


def test_fix_injects_interceptor_before_body_close():
    out = mod.fix("contato/index.html", CF7_PAGE)
    assert mod.MARKER in out
    assert "stopImmediatePropagation" in out
    assert out.index(mod.MARKER) < out.lower().rindex("</body>")
    # подяка португальською — мовою сторінки
    assert "Obrigado! Sua mensagem foi enviada" in out


def test_fix_is_idempotent_and_silences_run():
    out = mod.fix("contato/index.html", CF7_PAGE)
    assert mod.fix("contato/index.html", out) == out
    assert mod.run("contato/index.html", out) == []


def test_fix_leaves_plain_pages_alone():
    assert mod.fix("contato/index.html", PLAIN_PAGE) == PLAIN_PAGE


def test_language_fallback_is_english():
    page = CF7_PAGE.replace('lang="pt-BR"', 'lang="xx"')
    out = mod.fix("contato/index.html", page)
    assert "Thank you! Your message has been sent" in out


if __name__ == "__main__":
    run(dict(globals()))
