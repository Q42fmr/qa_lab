"""Реквізити продавця it-it (checks/seller_requisiti.py).

Кейс epidoc 02.10: на /privacy, /terms, /cookie і impressum.html у блоці
продавця заглушки «ragione sociale/REA/Partita IVA/Telefono: da inserire».
Фікс вписує реальні дані (пул company_req + телефон вітки); без пулу —
прибирає рядки. Діє ЛИШЕ на it-it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                            # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import company_req                                              # noqa: E402

mod = load_check("seller_requisiti")

BR = "mds-x-it-it"

SELLER = ("<footer><div id=\"seller\"><address><b>Chi vende</b>"
          "<strong>Epidoc</strong><br>Noleggio di auto d'epoca · "
          "ragione sociale da inserire · iscrizione al Registro delle "
          "imprese (REA) da inserire<br>Strada Statale 113, Italia<br>"
          "Partita IVA da inserire</address>"
          "<address><b>Contatti</b>Telefono: da inserire<br>"
          "Email: <a href=\"mailto:s@d.x\">s@d.x</a></address>"
          "</div></footer>")

IMPRESSUM = ("<html><body><main><p>Le voci «da inserire» vanno compilate "
             "prima della pubblicazione.</p>"
             "<h2>Venditore</h2><p>ragione sociale da inserire · iscrizione "
             "al Registro delle imprese (REA) da inserire</p>"
             "<h2>Identificativi</h2><p>Partita IVA da inserire</p>"
             "<h2>Contatti</h2><p>Telefono: da inserire</p></main>"
             + SELLER + "</body></html>")

INDEX = ("<html><body><footer><p>"
         "<a href=\"tel:+390272023334\">+39 02 76889932</a></p>"
         "</footer></body></html>")


def _files():
    page = f"<html><body>{SELLER}</body></html>"
    return {"index.php": INDEX, "privacy.html": page, "terms.html": page,
            "cookie.html": page, "impressum.html": IMPRESSUM}


def test_detects_all_pages_with_placeholders():
    issues = mod.run_branch(_files(), list(_files()), BR)
    assert {i["path"] for i in issues} == {"privacy.html", "terms.html",
                                           "cookie.html", "impressum.html"}
    assert all(i["severity"] == "error" for i in issues)
    m = next(i for i in issues if i["path"] == "privacy.html")["message"]
    for label in ("ragione sociale", "REA", "Partita IVA", "Telefono"):
        assert label in m, m


def test_other_locales_are_silent():
    files = {"privacy.html": f"<html><body>{SELLER}</body></html>"}
    assert mod.run_branch(dict(files), list(files), "mds-x-de-de") == []
    assert mod.fix_branch(dict(files), list(files), "mds-x-de-de") == []


def test_fix_writes_real_requisites_and_branch_phone():
    files = _files()
    rec = company_req.pick(BR)
    acts = {a["path"]: a["content"] for a in
            mod.fix_branch(dict(files), list(files), BR)}
    assert set(acts) == {"privacy.html", "terms.html", "cookie.html",
                         "impressum.html"}
    out = acts["privacy.html"]
    assert f"ragione sociale: {rec['name']}" in out
    assert f"(REA): {rec['rea']}" in out
    assert f"Partita IVA {rec['piva']}" in out
    assert 'Telefono: <a href="tel:+390272023334">+39 02 76889932</a>' in out
    assert "da inserire" not in out
    imp = acts["impressum.html"]
    assert "da inserire" not in imp, "преамбула чи поля лишились"
    assert f"Partita IVA {rec['piva']}" in imp
    # після фікса — тихо і нуль дій
    healed = {**files, **acts}
    assert mod.run_branch(dict(healed), list(healed), BR) == []
    assert mod.fix_branch(dict(healed), list(healed), BR) == []


def test_empty_pool_drops_placeholder_lines():
    files = _files()
    old = company_req.rows
    company_req.rows = lambda locale: []
    try:
        issues = mod.run_branch(dict(files), list(files), BR)
        assert issues and "прибере" in issues[0]["message"], issues
        acts = {a["path"]: a["content"] for a in
                mod.fix_branch(dict(files), list(files), BR)}
        out = acts["privacy.html"]
        assert "da inserire" not in out
        assert "Chi vende" in out and "Epidoc" in out, "блок продавця знесено"
        assert "mailto:s@d.x" in out, "пошта мала лишитись"
    finally:
        company_req.rows = old



# ---------------------------------------------------------------- Sede
# Скрін 13.10: блок «SEDE / Sede da inserire» (та сама MDS-партія, вітка ще
# не лагоджена). Адреси в пулі company_req немає, тож вписувати нічого:
# заглушка видаляється ЦІЛКОМ — разом із заголовком, бо осиротілий <h2>Sede
# над порожнім місцем виглядає так само зламано.
SEDE_PAGE = ("<html><body><main>"
             "<h2>Venditore</h2><p>ragione sociale da inserire</p>"
             "<h2>Sede</h2><p>Sede da inserire</p>"
             "<h2>Contatti</h2><p>Email: <a href=\"mailto:s@d.x\">s@d.x</a>"
             "</p></main></body></html>")


def test_sede_placeholder_is_flagged():
    files = {"impressum.html": SEDE_PAGE}
    issues = mod.run_branch(dict(files), list(files), BR)
    assert issues, "Sede-заглушку не видно"
    assert any("Sede" in i["message"] for i in issues), issues


def test_fix_drops_sede_block_with_heading():
    files = {"impressum.html": SEDE_PAGE}
    acts = {a["path"]: a["content"] for a in
            mod.fix_branch(dict(files), list(files), BR)}
    out = acts["impressum.html"]
    assert "Sede da inserire" not in out
    assert "<h2>Sede</h2>" not in out, "осиротілий заголовок лишився"
    assert "mailto:s@d.x" in out, "сусідні контакти знесено"
    assert "<h2>Contatti</h2>" in out
    # після фікса — тихо і нуль дій
    healed = {**files, "impressum.html": out}
    assert mod.fix_branch(dict(healed), list(healed), BR) == []


def test_inline_sede_line_is_dropped_too():
    """Та сама заглушка без власного заголовка — рядок у блоці продавця."""
    page = ("<html><body><div id=\"seller\"><address>"
            "<strong>Epidoc</strong><br>Sede: da inserire<br>"
            "Partita IVA da inserire</address></div></body></html>")
    files = {"privacy.html": page}
    old = company_req.rows
    company_req.rows = lambda locale: []
    try:
        acts = {a["path"]: a["content"] for a in
                mod.fix_branch(dict(files), list(files), BR)}
        out = acts["privacy.html"]
        assert "da inserire" not in out
        assert "Epidoc" in out
    finally:
        company_req.rows = old


def test_real_sede_is_untouched():
    page = ("<html><body><h2>Sede</h2>"
            "<p>Via Solferino 91, 57122 Livorno, Italia</p>"
            "</body></html>")
    files = {"impressum.html": page}
    assert mod.run_branch(dict(files), list(files), BR) == []
    assert mod.fix_branch(dict(files), list(files), BR) == []


def test_living_italian_outside_seller_zone_is_untouched():
    """«niente da inserire» (mds-papluwfu, index.php) — живе речення у
    товарній сітці: «нічого вводити». Поза impressum/privacy/terms/cookie
    і поза #seller/<address> літерал не судиться і не ріжеться."""
    page = ("<html><body><div class=\"inc\">video + PDF · l’esercizio "
            "della lezione 01 · niente da inserire</div>"
            "<footer><div id=\"seller\"><address>"
            "Partita IVA da inserire</address></div></footer>"
            "</body></html>")
    files = {"index.php": page}
    old = company_req.rows
    company_req.rows = lambda locale: []
    try:
        issues = mod.run_branch(dict(files), list(files), BR)
        assert len(issues) == 1, issues
        assert "Partita IVA" in issues[0]["message"]
        acts = {a["path"]: a["content"] for a in
                mod.fix_branch(dict(files), list(files), BR)}
        out = acts["index.php"]
        assert "niente da inserire" in out, "живе речення зрізано"
        assert "Partita IVA da inserire" not in out
    finally:
        company_req.rows = old


# ------------------------------------------------------------ br-pt «a inserir»
# Скрін 13.10 (mds-rakaa-esfihisno-93-1-fm-br-pt) і ще 112 mds-віток br-pt:
# той самий клас заглушок португальською. Дані для CNAE і дати consulta
# вже стоять у сусідньому «Quem vende» того ж футера — їх вписуємо;
# решту (IE/IM, editor, redação, encarregado) вписувати нічим — зносимо.
BRP = "mds-rakaa-x-br-pt"

FOOTER_PT = (
    '<footer class="seller" id="seller" lang="pt-BR"><div class="seller-in">'
    "<address><b>Quem vende</b><strong>Rádio X</strong><br>RADIO X LTDA · "
    "atividades de rádio (CNAE 6010-1/00) · situação cadastral na Receita "
    "Federal: ativa (consulta em 08/10/2026)<br>Rua A, 1<br>CNPJ 98.517.154/0001-50"
    "</address>"
    # між блоками — <div class="legal">: зона #seller обривається на його
    # </div>, тож Expediente — окрема <address>-зона без «Quem vende» поруч
    '<div class="legal"><a href="terms.html">Termos</a> · Modelo: dados do '
    "fornecedor não confirmados.</div>"
    '<address class="exped"><b>Expediente</b>Editor responsável: a inserir<br>'
    "Redação: a inserir<br>Inscrição estadual / municipal: a inserir<br>"
    "CNAE principal: a inserir<br>Fonte dos dados cadastrais: CNPJ (Receita "
    "Federal), consulta a inserir<br>Encarregado (LGPD): a inserir<br>"
    '<a href="terms.html">Política editorial</a> · <a href="terms.html">'
    "Comentários</a></address></div></footer>")


def test_pt_placeholders_are_flagged():
    files = {"index.php": f"<html><body>{FOOTER_PT}</body></html>"}
    issues = mod.run_branch(dict(files), list(files), BRP)
    assert issues, "заглушки «a inserir» не видно"
    assert "CNAE" in issues[0]["message"] or "Editor" in issues[0]["message"]


def test_pt_fix_fills_from_quem_vende_and_drops_the_rest():
    files = {"index.php": f"<html><body>{FOOTER_PT}</body></html>"}
    acts = {a["path"]: a["content"] for a in
            mod.fix_branch(dict(files), list(files), BRP)}
    out = acts["index.php"]
    assert "a inserir" not in out
    assert "CNAE principal: 6010-1/00" in out, "CNAE не взято з «Quem vende»"
    assert "consulta em 08/10/2026" in out.split("Expediente")[1], \
        "дата consulta не взята з «Quem vende»"
    for gone in ("Editor responsável", "Redação:", "Inscrição estadual",
                 "Encarregado"):
        assert gone not in out, f"{gone} лишилось без даних"
    # лінки блоку і «Quem vende» цілі, тихо та ідемпотентно
    assert "Política editorial" in out and "CNPJ 98.517.154/0001-50" in out
    healed = {"index.php": out}
    assert mod.run_branch(dict(healed), list(healed), BRP) == []
    assert mod.fix_branch(dict(healed), list(healed), BRP) == []


def test_pt_parenthesised_and_sentence_forms_in_legal_pages():
    page = ("<html><body><p><strong>Modelo.</strong> Este é um site de "
            "demonstração: os dados do fornecedor ainda não foram confirmados "
            "por ele, e os itens “a inserir” devem ser preenchidos antes da "
            "publicação.</p>"
            "<h2>Site</h2><p>Site estático sem servidor. Hospedagem: a inserir. "
            "Fontes: Google Fonts.</p>"
            "<table><tr><td>Provedor de hospedagem do site (a inserir)</td>"
            "<td>registrados pelo provedor (hospedagem: a inserir) e enviados "
            "ao Google</td></tr></table>"
            "<p>Encarregado pelo tratamento de dados pessoais (art. 41 da LGPD): "
            "a inserir.</p></body></html>")
    files = {"privacy.html": page}
    acts = {a["path"]: a["content"] for a in
            mod.fix_branch(dict(files), list(files), BRP)}
    out = acts["privacy.html"]
    assert "a inserir" not in out
    assert "Modelo." not in out, "осиротілий «Modelo.» лишився"
    assert "Site estático sem servidor." in out and "Fontes: Google Fonts." in out
    assert "<td>Provedor de hospedagem do site</td>" in out
    assert "registrados pelo provedor e enviados ao Google" in out
    assert "Encarregado" not in out


def test_pt_living_para_inserir_is_untouched():
    page = ("<html><body><h2>Serviços</h2><p>Três caminhos para inserir "
            "ferramentas assistidas na rotina do seu negócio.</p></body></html>")
    files = {"impressum.html": page}
    assert mod.run_branch(dict(files), list(files), BRP) == []
    assert mod.fix_branch(dict(files), list(files), BRP) == []

def test_pt_key_panel_dl_pairs_are_dropped():
    """veltrixa 15.10: заглушки не у футері, а в <aside>-панелі реквізитів
    (dl з dt/dd) та її підписі — зона має їх бачити, пара dt/dd зноситься
    разом з обгорткою, сусідні пари цілі."""
    page = ('<html><body><main><p>Três caminhos para inserir ferramentas.</p>'
            '<aside class="kp"><dl>'
            '<div><dt>E-mail</dt><dd><a href="mailto:info@{{DOMAIN}}">'
            'info@{{DOMAIN}}</a></dd></div> '
            '<div><dt>Telefone</dt><dd class="tbc">a inserir</dd></div> '
            '<div><dt>Representante legal</dt><dd class="tbc">a inserir</dd></div>'
            '</dl><p class="kp-src">Dados cadastrais. O que o portal publica: '
            'a inserir.</p></aside></main></body></html>')
    files = {"index.php": page}
    issues = mod.run_branch(dict(files), list(files), BRP)
    assert issues and "Telefone" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in
            mod.fix_branch(dict(files), list(files), BRP)}
    out = acts["index.php"]
    assert not mod._DA_INSERIRE_RX.search(out), "заглушка лишилась"
    assert "<dt>Telefone</dt>" not in out and "Representante legal" not in out
    assert "mailto:info@{{DOMAIN}}" in out, "сусідня пара знесена"
    assert "para inserir ferramentas" in out, "живе речення зрізано"
    assert "O que o portal publica" not in out
    healed = {"index.php": out}
    assert mod.run_branch(dict(healed), list(healed), BRP) == []
    assert mod.fix_branch(dict(healed), list(healed), BRP) == []


def test_pt_standalone_note_outside_blocks_is_dropped():
    """cirevo/nexlivo/nao-foi-sorte 15.10: примітка з заглушкою поза
    будь-яким блоком — «Canal de contato: a inserir», «…: a inserir.».
    Літерал у кінці речення судиться скрізь; живе «para inserir» — ні."""
    page = ('<html><body><div class="chan"><p class="chan-t">Canal de contato: '
            'a inserir</p><p>Pedido de orçamento, nada mais.</p></div>'
            '<p class="f-note">Nomes de eventos, datas e tabela oficial: a '
            'inserir. Tudo o que esta planta mostra é exemplo.</p>'
            '<span>segunda a sexta <em>a confirmar</em></span> '
            '<span data-i18n="fin.msg">canal de mensagens a inserir</span>'
            '<p>Três caminhos para inserir ferramentas.</p></body></html>')
    files = {"index.php": page}
    assert mod.run_branch(dict(files), list(files), BRP)
    out = mod.fix_branch(dict(files), list(files), BRP)[0]["content"]
    assert not mod._DA_INSERIRE_RX.search(out), out
    assert "Pedido de orçamento, nada mais." in out
    assert "Tudo o que esta planta mostra é exemplo." in out
    assert "a confirmar" in out and "para inserir ferramentas" in out
    assert "canal de mensagens" not in out and "Canal de contato" not in out


def test_contract_shape():
    assert mod.GROUP == "auto"
    assert mod.PROJECTS == ["php"]
    assert callable(mod.run_branch) and callable(mod.fix_branch)


if __name__ == "__main__":
    run(dict(globals()))
