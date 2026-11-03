import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run, load_check

mod = load_check("tpl_links")


def _apply(files, branch="site-jp-ja-jp-jp"):
    actions = mod.fix_branch(files, list(files), branch)
    out = dict(files)
    for a in actions:
        out[a["path"]] = a["content"]
    return out


def test_social_removes_anchor_and_collapses_li_and_ul():
    html = (
        '<ul class="mainFooter__sns">\n'
        '  <li><a data-tpl="[FACEBOOK LINK]" href="#">\n'
        '      <picture><img alt="" src="assets/icn_facebook.png"/></picture></a></li>\n'
        '  <li><a data-tpl="[INSTAGRAM LINK]" href="#">\n'
        '      <picture><img alt="" src="assets/icn_instagram.png"/></picture></a></li>\n'
        '</ul>\n'
    )
    files = {"index.php": html}
    issues = mod.run_branch(files, list(files), "site-jp-ja-jp-jp")
    assert len(issues) == 1
    assert "соц-іконок-плейсхолдерів прибере: 2" in issues[0]["message"]
    assert issues[0]["severity"] == "error"

    fixed = _apply(files)
    text = fixed["index.php"]
    assert "data-tpl" not in text
    assert "<li>" not in text
    assert "<ul" not in text

    assert mod.run_branch(fixed, list(fixed), "site-jp-ja-jp-jp") == []
    assert mod.fix_branch(fixed, list(fixed), "site-jp-ja-jp-jp") == []


def test_retarget_by_alt_matches_page_at_other_depth():
    index_html = (
        '<title>TAILOR KICOKU｜神戸・北野の仕立て屋</title>\n'
        '<a data-tpl="[EXTERNAL LINK]" href="#" style="color:#363636">\n'
        '  <picture><img alt="ご注文の流れ" src="_photos/x.jpg"/></picture>\n'
        '</a>\n'
    )
    howto_html = '<title>ご注文の流れ｜TAILOR KICOKU</title><h1>ご注文の流れ</h1>\n'
    files = {"index.php": index_html, "howtoorder/index.html": howto_html}

    issues = mod.run_branch(files, list(files), "site-jp-ja-jp-jp")
    assert len(issues) == 1
    assert "howtoorder/index.html" in issues[0]["message"]
    assert "ご注文の流れ" in issues[0]["message"]

    fixed = _apply(files)
    text = fixed["index.php"]
    assert 'href="howtoorder/index.html"' in text
    assert "data-tpl" not in text
    assert 'href="#"' not in text

    assert mod.run_branch(fixed, list(fixed), "site-jp-ja-jp-jp") == []
    assert mod.fix_branch(fixed, list(fixed), "site-jp-ja-jp-jp") == []


def test_unwrap_fallback_when_no_page_matches():
    html = '<p><a data-tpl="[EXTERNAL LINK]" href="javascript:void(0)">Більше інформації</a></p>'
    files = {"about/index.html": html}

    issues = mod.run_branch(files, list(files), "site-jp-ja-jp-jp")
    assert len(issues) == 1
    assert "розгорне в текст" in issues[0]["message"]

    fixed = _apply(files)
    text = fixed["about/index.html"]
    assert "<a " not in text
    assert "data-tpl" not in text
    assert "Більше інформації" in text

    assert mod.run_branch(fixed, list(fixed), "site-jp-ja-jp-jp") == []
    assert mod.fix_branch(fixed, list(fixed), "site-jp-ja-jp-jp") == []


def test_real_href_anchor_untouched():
    html = '<li><a data-tpl="[FACEBOOK LINK]" href="https://facebook.com/page">FB</a></li>'
    files = {"index.php": html}
    assert mod.run_branch(files, list(files), "site-jp-ja-jp-jp") == []
    assert mod.fix_branch(files, list(files), "site-jp-ja-jp-jp") == []


def test_anchor_without_data_tpl_untouched():
    html = '<li><a href="#">placeholder but not scraper-marked</a></li>'
    files = {"index.php": html}
    assert mod.run_branch(files, list(files), "site-jp-ja-jp-jp") == []
    assert mod.fix_branch(files, list(files), "site-jp-ja-jp-jp") == []


def test_calibration_tailor_reference():
    if not (ROOT / "_work" / "ref").is_dir():
        return      # локальні еталони реальних сторінок (_work/ref не в репо): у CI пропускаємо
    before_path = ROOT / "_work" / "ref" / "tailor_index_before_tpl.php"
    text = before_path.read_text(encoding="utf-8")
    howto_html = '<title>ご注文の流れ｜TAILOR KICOKU</title><h1>ご注文の流れ</h1>\n'
    files = {"index.php": text, "howtoorder/index.html": howto_html}
    issues = mod.run_branch(files, list(files), "taenof-kicoku-jp-ja-jp-jp")
    assert len(issues) == 1
    msg = issues[0]["message"]
    assert "соц-іконок-плейсхолдерів прибере: 2" in msg
    assert "howtoorder/index.html" in msg


def test_calibration_hahuli_reference():
    if not (ROOT / "_work" / "ref").is_dir():
        return      # локальні еталони реальних сторінок (_work/ref не в репо): у CI пропускаємо
    before_path = ROOT / "_work" / "ref" / "hahuli_blog_before_tpl.html"
    text = before_path.read_text(encoding="utf-8")
    files = {"blog/post/index.html": text}
    issues = mod.run_branch(files, list(files), "hahuli-jp-ja-jp-jp")
    assert len(issues) == 1
    assert "соц-іконок-плейсхолдерів прибере: 3" in issues[0]["message"]


def test_social_kind_with_content_banner_is_not_removed():
    # ortun-sqioha 27.10: data-tpl="[INSTAGRAM LINK]", але всередині не
    # іконка, а банер з контентним alt — не соцмережа, лишає контент видимим
    html = ('<a data-tpl="[INSTAGRAM LINK]" href="#">'
            '<img alt="店舗一覧" src="_photos/3d6825ea2a96abc4.png"/></a>')
    files = {"abouts/index.html": html}
    issues = mod.run_branch(files, list(files), "ortun-sqioha-jp-ja-jp-jp")
    assert len(issues) == 1
    assert "лінків розгорне в текст: 1" in issues[0]["message"]

    fixed = _apply(files, "ortun-sqioha-jp-ja-jp-jp")
    text = fixed["abouts/index.html"]
    assert "<a " not in text
    assert 'alt="店舗一覧"' in text
    assert mod.run_branch(fixed, list(fixed), "ortun-sqioha-jp-ja-jp-jp") == []


def test_real_social_icon_with_matching_alt_still_removed():
    html = ('<li><a data-tpl="[FACEBOOK LINK]" href="#" ontouchstart="">'
            '<img alt="facebook" src="images/icon/facebook_white.png"/></a></li>')
    files = {"index.php": html}
    issues = mod.run_branch(files, list(files), "ortun-sqioha-jp-ja-jp-jp")
    assert "соц-іконок-плейсхолдерів прибере: 1" in issues[0]["message"]
    fixed = _apply(files, "ortun-sqioha-jp-ja-jp-jp")
    assert "<a " not in fixed["index.php"]


def test_non_social_kind_with_icon_class_is_removed_as_social():
    # remujosra-cotfaup 27.10: data-tpl="[EXTERNAL LINK]", але вміст — клас
    # fa-twitter: справжня соц-іконка, прибирається
    html = ('<a class="btn btn-square btn-secondary rounded-circle m-1" '
            'data-tpl="[EXTERNAL LINK]" href="#"><i class="fab fa-twitter"></i></a>')
    files = {"index.php": html}
    issues = mod.run_branch(files, list(files), "remujosra-cotfaup-ch-fr")
    assert "соц-іконок-плейсхолдерів прибере: 1" in issues[0]["message"]
    fixed = _apply(files, "remujosra-cotfaup-ch-fr")
    assert "fa-twitter" not in fixed["index.php"]
    assert mod.run_branch(fixed, list(fixed), "remujosra-cotfaup-ch-fr") == []


def test_phone_text_becomes_tel_link():
    html = '<a data-tpl="[EXTERNAL LINK]" href="#">092-736-5311</a>'
    files = {"company.html": html}
    issues = mod.run_branch(files, list(files), "agon-woid-jp-jp")
    assert len(issues) == 1
    assert "телефонів зробить tel:-лінками: 1" in issues[0]["message"]

    fixed = _apply(files, "agon-woid-jp-jp")
    text = fixed["company.html"]
    assert 'href="tel:+81927365311"' in text
    assert ">092-736-5311</a>" in text
    assert mod.run_branch(fixed, list(fixed), "agon-woid-jp-jp") == []
    assert mod.fix_branch(fixed, list(fixed), "agon-woid-jp-jp") == []


def test_email_text_becomes_mailto_link():
    html = '<a data-tpl="[EXTERNAL LINK]" href="javascript:void(0)">info@example.com</a>'
    files = {"contact.html": html}
    issues = mod.run_branch(files, list(files), "agon-woid-jp-jp")
    assert "email зробить mailto:-лінками: 1" in issues[0]["message"]
    fixed = _apply(files, "agon-woid-jp-jp")
    assert 'href="mailto:info@example.com"' in fixed["contact.html"]
    assert mod.run_branch(fixed, list(fixed), "agon-woid-jp-jp") == []


def test_own_domain_text_retargets_to_home_not_unwrap():
    html = ('<h5>オンラインショップ・相談 '
            '<a data-tpl="[EXTERNAL LINK]" href="#">www.ortun-sqioha.jp</a></h5>')
    files = {"group/index.html": html, "index.php": "<title>ORTUN SQIOHA</title>"}
    issues = mod.run_branch(files, list(files), "ortun-sqioha-jp-ja-jp-jp")
    assert len(issues) == 1
    assert "банер «www.ortun-sqioha.jp» поведе на ../" in issues[0]["message"]

    fixed = _apply(files, "ortun-sqioha-jp-ja-jp-jp")
    text = fixed["group/index.html"]
    assert 'href="../"' in text
    assert "www.ortun-sqioha.jp</a>" in text
    assert mod.run_branch(fixed, list(fixed), "ortun-sqioha-jp-ja-jp-jp") == []
    assert mod.fix_branch(fixed, list(fixed), "ortun-sqioha-jp-ja-jp-jp") == []


def test_cta_label_uses_nearest_preceding_heading_to_retarget():
    # lamubde-viopa 27.10: картка з CTA «Ler a nota →» шукає сторінку за
    # заголовком картки, а не за текстом кнопки
    html = (
        '<article><h3>Planejamento sucessório em vida</h3>'
        '<p>...</p>'
        '<a data-tpl="[EXTERNAL LINK]" href="#">Ler a nota<span aria-hidden="true">→</span></a>'
        '</article>'
    )
    target_html = '<title>Planejamento sucessório em vida | Site</title><h1>Planejamento sucessório em vida</h1>'
    files = {"biblioteca/index.html": html,
              "biblioteca/planejamento/index.html": target_html}
    issues = mod.run_branch(files, list(files), "lamubde-viopa-adgugenae-br-pt")
    assert len(issues) == 1
    assert "банер «Planejamento sucessório em vida» поведе на" in issues[0]["message"]
    assert "planejamento/index.html" in issues[0]["message"]

    fixed = _apply(files, "lamubde-viopa-adgugenae-br-pt")
    text = fixed["biblioteca/index.html"]
    assert 'href="planejamento/index.html"' in text
    assert "Ler a nota" in text
    assert "data-tpl" not in text
    assert mod.run_branch(fixed, list(fixed), "lamubde-viopa-adgugenae-br-pt") == []


def test_cta_label_without_matching_page_deletes_anchor_not_unwrap():
    html = (
        '<article><h3>Reclamação formal: como registrar</h3>'
        '<p>Um texto qualquer explicando o tema sem link.</p>'
        '<a class="btn" data-tpl="[EXTERNAL LINK]" href="#">Ler a nota<span>→</span></a>'
        '</article>'
    )
    files = {"biblioteca/index.html": html}
    issues = mod.run_branch(files, list(files), "lamubde-viopa-adgugenae-br-pt")
    assert len(issues) == 1
    assert "CTA без сторінки прибере: 1" in issues[0]["message"]

    fixed = _apply(files, "lamubde-viopa-adgugenae-br-pt")
    text = fixed["biblioteca/index.html"]
    assert "Ler a nota" not in text
    assert "<article>" in text and "Um texto qualquer" in text
    assert mod.run_branch(fixed, list(fixed), "lamubde-viopa-adgugenae-br-pt") == []
    assert mod.fix_branch(fixed, list(fixed), "lamubde-viopa-adgugenae-br-pt") == []


def test_whatsapp_text_with_phone_on_page_becomes_wa_me_link():
    # donza-cecno-ennafoket 27.10: іконка fa-instagram, aria-label Instagram,
    # але видимий текст — WhatsApp, і на сторінці є номер
    html = (
        '<li><a aria-label="Instagram" class="soc" data-tpl="[INSTAGRAM LINK]" href="#">'
        '<i class="fa-brands fa-instagram"></i> WhatsApp </a></li>'
        '<span>Telefone: +55 11 2651-4647</span>'
    )
    files = {"gofragem/index.html": html}
    issues = mod.run_branch(files, list(files), "donza-cecno-ennafoket-br-pt")
    assert len(issues) == 1
    assert "WhatsApp поведе на wa.me: 1" in issues[0]["message"]

    fixed = _apply(files, "donza-cecno-ennafoket-br-pt")
    text = fixed["gofragem/index.html"]
    assert 'href="https://wa.me/551126514647"' in text
    assert 'target="_blank"' in text
    assert 'rel="noopener"' in text
    assert "data-tpl" not in text
    assert "fa-instagram" in text  # іконка/текст лишаються, міняється лише href
    assert mod.run_branch(fixed, list(fixed), "donza-cecno-ennafoket-br-pt") == []
    assert mod.fix_branch(fixed, list(fixed), "donza-cecno-ennafoket-br-pt") == []


def test_whatsapp_text_without_any_phone_is_removed_as_social():
    html = '<li><a data-tpl="[INSTAGRAM LINK]" href="#">WhatsApp</a></li>'
    files = {"contato/index.html": html}
    issues = mod.run_branch(files, list(files), "donza-cecno-ennafoket-br-pt")
    assert "соц-іконок-плейсхолдерів прибере: 1" in issues[0]["message"]
    fixed = _apply(files, "donza-cecno-ennafoket-br-pt")
    assert "<a " not in fixed["contato/index.html"]


def test_styled_button_anchor_without_target_is_removed_not_unwrapped():
    """tesa-nomu br-pt (TECH-29416, 27.10): `<a class="float-btn float-agenda"
    data-tpl="[EXTERNAL LINK]" href="#"><svg…/> <span>Agende seu reparo</span></a>`
    і `<a class="hero-oferta" …>` розгорнулись у текст — лишились голий svg
    574px («чорний квадрат») і підписи без кнопки на 22 сторінках. Якір з
    класом кнопки (btn/button/cta/fab/float/pill/oferta) або з іконкою + коротким
    підписом без цілі — прибирається цілком, не розгортається."""
    html = ('<div class="floating-actions">'
            '<a class="float-btn float-call" href="tel:+5598984092916"><svg viewBox="0 0 24 24"><use href="#i-phone"></use></svg><span>Ligar</span></a>'
            '<a class="float-btn float-agenda" data-tpl="[EXTERNAL LINK]" href="#"><svg aria-hidden="true" viewBox="0 0 24 24"><rect/></svg> <span class="ag-longo">Agende seu reparo</span></a>'
            '</div><div class="hero-cta"><a class="hero-oferta" data-tpl="[EXTERNAL LINK]" href="#"><svg viewBox="0 0 24 24"><rect/></svg> <span>Agende seu reparo na loja</span></a></div>'
            '<p><a data-tpl="[EXTERNAL LINK]" href="#">Leia a política completa da loja</a></p>')
    files = {"index.php": html}
    issues = mod.run_branch(files, list(files), "tesa-nomu-br-pt")
    assert len(issues) == 1 and "кнопок без цілі прибере: 2" in issues[0]["message"], issues
    fixed = _apply(files, "tesa-nomu-br-pt")["index.php"]
    assert "float-agenda" not in fixed and "hero-oferta" not in fixed and "Agende seu reparo" not in fixed
    assert 'class="float-btn float-call"' in fixed                      # робоча кнопка ціла
    assert "<p>Leia a política completa da loja</p>" in fixed           # звичайний текстовий лінк — як і раніше, unwrap
    assert mod.run_branch({"index.php": fixed}, ["index.php"], "tesa-nomu-br-pt") == []


if __name__ == "__main__":
    run(dict(globals()))
