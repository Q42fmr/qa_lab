"""Юридичні сторінки: Impressum на ch-*, політика конфіденційності всюди
(checks/legal_pages)."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run, load_check                    # noqa: E402

sys.path.insert(0, str(ROOT))

import projects                                               # noqa: E402
import uid_pool                                               # noqa: E402
import cnpj_pool                                              # noqa: E402

mod = load_check("legal_pages")

HEAD = ('<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>Erscurab – Nachfolgeplanung</title>'
        '<meta name="description" content="Erscurab bietet Bildungsangebote rund um persönliche Nachfolgeplanung in Schaffhausen.">'
        '</head><body>')
HEADER = '<header class="top"><a href="./">Erscurab</a></header>'
FOOTER = ('<footer class="ft"><div class="cols"><ul class="legal">'
          '<li><a href="./privacy-policy.html" class="lnk">Datenschutzerklärung</a></li>'
          '<li><a href="./terms-conditions.html" class="lnk">Nutzungsbedingungen</a></li></ul>'
          '<p class="addr">Vordergasse 48, 8200 Schaffhausen</p>'
          '<a href="tel:+41526310974"><i class="ic"></i> +41 52 631 09 74</a>'
          '<a href="mailto:info@{{DOMAIN}}">info@{{DOMAIN}}</a></div></footer></body></html>')
HOME = HEAD + HEADER + "<main><h1>Nachfolge ohne Druck</h1><p>Text</p></main>" + FOOTER
PRIVACY = (HEAD.replace("Erscurab – Nachfolgeplanung", "Datenschutz – Erscurab") + HEADER
           + '<main class="legal-main"><div class="intro"><span class="lbl">Rechtliches</span>'
           '<h1 class="title">Datenschutzerklärung</h1><p class="meta">Letzte Aktualisierung: 15. Mai 2025</p></div>'
           '<div class="card"><div class="policy-section"><h2 class="section-title">1. Einleitung</h2>'
           '<p class="body-text">Erscurab, Vordergasse 48, 8200 Schaffhausen, ist verantwortlich.</p></div>'
           '<div class="policy-section"><h2 class="section-title">2. Daten</h2><p class="body-text">x</p></div></div></main>'
           + FOOTER)


def _fresh_pools():
    d = Path(tempfile.mkdtemp(prefix="lp-"))
    projects.state_root = lambda: d
    uid_pool.SEED = Path(uid_pool.__file__).resolve().parent / "uid_seed.json"
    cnpj_pool.SEED = Path(cnpj_pool.__file__).resolve().parent / "cnpj_seed.json"


def _ch_files():
    return {"index.php": HOME, "privacy-policy.html": PRIVACY,
            "terms-conditions.html": PRIVACY.replace("Datenschutzerklärung", "Nutzungsbedingungen")}


def test_ch_branch_without_impressum_is_flagged_and_generated_in_donor_shell():
    _fresh_pools()
    files = _ch_files()
    issues = mod.run_branch(dict(files), list(files), "erscurab-ch-de")
    assert len(issues) == 1 and "Impressum" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "erscurab-ch-de")}
    assert "impressum.html" in acts, acts.keys()
    page = acts["impressum.html"]
    # оболонка донора: head/header/footer і класи секцій — як у privacy
    assert "<title>Impressum – Erscurab</title>" in page
    assert HEADER in page and '<footer class="ft">' in page
    assert '<h1 class="title">Impressum</h1>' in page
    assert '<div class="policy-section">' in page and '<h2 class="section-title">Verantwortlich für den Inhalt</h2>' in page
    assert "Letzte Aktualisierung" not in page
    # факти вітки: адреса, телефон з головної, пошта з {{DOMAIN}}, UID з пулу
    assert "Vordergasse 48, 8200 Schaffhausen" in page and "+41 52 631 09 74" in page
    assert "info@{{DOMAIN}}" in page and "UID CHE-" in page
    assert "Erscurab bietet Bildungsangebote" in page and "Erscurab — Erscurab" not in page
    # лінк у футері КОЖНОЇ сторінки, клон сусіднього <li><a class="lnk">
    for p in ("index.php", "privacy-policy.html", "terms-conditions.html", "impressum.html"):
        assert '<li><a href="./impressum.html" class="lnk">Impressum</a></li>' in acts[p], p
    # після фікса — тиша та ідемпотентність
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "erscurab-ch-de") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "erscurab-ch-de") == []


def test_labels_and_laws_follow_the_branch_language():
    _fresh_pools()
    fr = {k: v.replace('lang="de"', 'lang="fr"') for k, v in _ch_files().items()}
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(fr), list(fr), "nekpi-ch-fr")}
    assert "mentions-legales.html" in acts and "Responsable du contenu" in acts["mentions-legales.html"]
    assert ">Mentions légales</a>" in acts["index.php"]
    it = {k: v for k, v in _ch_files().items()}
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(it), list(it), "lubixutne-ch-it")}
    assert "note-legali.html" in acts and "Responsabile dei contenuti" in acts["note-legali.html"]


def test_non_ch_branch_needs_no_impressum_but_needs_privacy():
    _fresh_pools()
    files = _ch_files()
    assert mod.run_branch(dict(files), list(files), "x-de-de") == []
    # скрейп без privacy і без <header>: оболонка головної, LGPD, CNPJ з пулу
    home = ('<html lang="pt-BR"><head><title>Eleva</title></head><body><nav><a href="#x">Home</a></nav>'
            '<section><h1>E se o problema no seu elevador não avisar antes de acontecer?</h1></section>'
            '<footer><h3>Eleva Elevadores</h3><p><a href="#hero">Home</a> | <a href="#contato">Contato</a></p>'
            '<p>Endereço: Rua das Flores, 10, Centro, Brasília DF, 70712-903</p><p>Email: contato@{{DOMAIN}}</p></footer></body></html>')
    files = {"index.php": home}
    issues = mod.run_branch(dict(files), list(files), "eleva-br-pt")
    assert len(issues) == 1 and "Política de Privacidade" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "eleva-br-pt")}
    page = acts["politica-de-privacidade.html"]
    assert "<title>Política de Privacidade – " in page
    assert "LGPD" in page and "CNPJ " in page and "contato@{{DOMAIN}}" in page
    assert "Rua das Flores, 10" in page
    assert "acontecer?" not in page, "слоган-питання не є описом діяльності"
    assert "<nav>" in page and "<footer>" in page and "<h1>E se o problema" not in page
    assert 'href="politica-de-privacidade.html">Política de Privacidade</a>' in acts["index.php"]
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "eleva-br-pt") == []


def test_existing_privacy_without_footer_link_only_gets_the_link():
    _fresh_pools()
    files = _ch_files()
    files["index.php"] = HOME.replace('<li><a href="./privacy-policy.html" class="lnk">Datenschutzerklärung</a></li>',
                                      '<li><a href="./impressum.html" class="lnk">Impressum</a></li>')
    files["impressum.html"] = PRIVACY.replace("Datenschutzerklärung", "Impressum")
    issues = mod.run_branch(dict(files), list(files), "erscurab-ch-de")
    assert len(issues) == 1 and "немає лінка" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "erscurab-ch-de")}
    assert set(acts) == {"index.php"}, acts.keys()
    assert 'href="./privacy-policy.html"' in acts["index.php"]


def test_builder_footer_without_footer_tag_still_gets_page_and_link():
    """caixadagua/ngrestauracao 19.10 (Astro/Elementor): підвал — <div> з
    © і CNPJ, тега <footer> немає; чек бачив «немає політики», а фікс давав
    0 дій. Зона футера — останній блок із copyright/CNPJ: лінк клонує
    сусідній юридичний <a>, сторінка будується в оболонці головної з цим
    блоком як футером."""
    _fresh_pools()
    home = ('<html lang="pt-BR"><head><title>NG</title></head><body><header><nav><a href="#x">Home</a></nav></header>'
            '<section><h1>Restauração</h1></section>'
            '<div class="elementor-element e-con"><div class="elementor-widget-container">'
            '<p>© 2026 NG Restauração. Todos os direitos reservados.</p><p>CNPJ 11.222.333/0001-81</p>'
            '<p><a class="elementor-item" href="termos.html">Termos de uso</a></p></div></div></body></html>')
    files = {"index.php": home, "termos.html": home.replace("<h1>Restauração</h1>", "<h1>Termos</h1>")}
    assert len(mod.run_branch(dict(files), list(files), "ng-br-pt")) == 1
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "ng-br-pt")}
    assert set(acts) == {"index.php", "termos.html", "politica-de-privacidade.html"}, acts.keys()
    assert '<a class="elementor-item" href="politica-de-privacidade.html">Política de Privacidade</a>' in acts["index.php"]
    page = acts["politica-de-privacidade.html"]
    assert "<header>" in page and "© 2026 NG" in page and "Restauração</h1>" not in page and "CNPJ 11.222.333/0001-81" in page
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "ng-br-pt") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "ng-br-pt") == []


def test_dir_style_links_and_menu_placement_are_recognised_and_not_duplicated():
    """repira-pagcajoonu (локальна партія 20.10): «Mentions légales» лінкується
    як mentions-legales/index.html у МЕНЮ, підвал — <div id="CopyRight"> без
    <footer>, юридичні <p><a> стоять після нього. Чек вважав «не залінковано»
    і фікс тричі дописував ті самі 26 лінків. Лінк у меню рахується; зона
    підвалу тягнеться до </body>; повторний фікс — 0 дій."""
    _fresh_pools()
    home = ('<html lang="fr"><head><title>Relève</title></head><body><ul class="menu"><li><a href="index.html">Accueil</a></li>'
            '<li><a href="mentions-legales/index.html">Mentions légales</a></li></ul>'
            '<div id="CopyRight">© 2026 Relève SA. Tous droits réservés.</div>'
            '<p><a href="politique-de-confidentialite.html">Politique de confidentialité</a></p>'
            '<script>var x=1</script></body></html>')
    legal = home.replace("<title>Relève</title>", "<title>Mentions légales – Relève</title>").replace(
        '<div id="CopyRight">', '<h1>Mentions légales</h1><p>Relève SA, Rue du Lac 12, 1700 Fribourg</p><div id="CopyRight">')
    files = {"index.html": home, "mentions-legales/index.html": legal, "politique-de-confidentialite.html": legal}
    assert mod.run_branch(dict(files), list(files), "releve-ch-fr") == []
    assert mod.fix_branch(dict(files), list(files), "releve-ch-fr") == []
    # без лінка на privacy ніде — додається один раз, у зону після ©
    files["index.html"] = home.replace('<p><a href="politique-de-confidentialite.html">Politique de confidentialité</a></p>', "")
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "releve-ch-fr")}
    assert acts["index.html"].count('politique-de-confidentialite.html') == 1
    fixed = {**files, **acts}
    assert mod.fix_branch(dict(fixed), list(fixed), "releve-ch-fr") == []


NODE = {
    "index.html": '<html><head><title>Aca Coozlc</title><meta name="description" content="Stundenweise buchbare Tennisplätze in Lugano."></head><body><div id="app"></div></body></html>',
    "src/data/pages.js": ('export const pages = [\n  {\n    "id": "home",\n    "name": "Start",\n    "route": "/",\n    "category": "main",\n    "nav": true\n  },\n'
                          '  {\n    "id": "privacy",\n    "name": "Datenschutz",\n    "route": "/datenschutz",\n    "category": "legal",\n    "nav": true\n  }\n]\n\n'
                          "export const legalPages = pages.filter(p => p.category === 'legal')\n"),
    "src/router/index.js": ("export const routes = [\n  {\n    path: '/',\n    name: 'home',\n    component: () => import('@/pages/Home.vue')\n  },\n"
                            "  {\n    path: '/datenschutz',\n    name: 'privacy',\n    component: () => import('@/pages/Privacy.vue')\n  }\n]\n"),
    "src/pages/Privacy.vue": "<template><div><DataPolicy /></div></template>\n<script>\nimport DataPolicy from '@/components/DataPolicy.vue'\nexport default { components: { DataPolicy } }\n</script>\n",
    "src/components/DataPolicy.vue": ('<template>\n  <main class="max-w-4xl mx-auto px-4 py-12">\n    <h1 class="font-sans text-4xl text-stone-900">Datenschutz</h1>\n'
                                      '    <p class="intro text-center">Wie wir Daten schützen.</p>\n    <section class="mb-8"><h2 class="font-sans text-2xl">Einführung</h2>'
                                      '<p class="font-sans text-stone-500 leading-relaxed">Aca Coozlc, Via Cattori 12, 6900 Lugano.</p></section>\n  </main>\n</template>\n'),
    "src/components/Footer.vue": '<template><footer><a href="mailto:info@acacoozlc.ch">info@acacoozlc.ch</a><a href="tel:+41916234857">+41 91 623 48 57</a></footer></template>\n',
}


def test_node_branch_gets_impressum_page_route_and_pages_entry():
    _fresh_pools()
    files = dict(NODE)
    issues = mod.run_branch(dict(files), list(files), "nwf-aca-coozlc-ch-de")
    assert len(issues) == 1 and "Impressum" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "nwf-aca-coozlc-ch-de")}
    assert set(acts) == {"src/data/pages.js", "src/router/index.js", "src/pages/Impressum.vue"}, acts.keys()
    pj = acts["src/data/pages.js"]
    assert '"route": "/impressum"' in pj and '"category": "legal"' in pj and pj.index('"id": "privacy"') < pj.index('"id": "impressum"')
    assert "path: '/impressum'" in acts["src/router/index.js"] and "import('@/pages/Impressum.vue')" in acts["src/router/index.js"]
    vue = acts["src/pages/Impressum.vue"]
    # класи — з privacy-компонента вітки; p — секційний, не вступний
    assert '<main class="max-w-4xl mx-auto px-4 py-12">' in vue and '<h1 class="font-sans text-4xl text-stone-900">Impressum</h1>' in vue
    assert '<p class="font-sans text-stone-500 leading-relaxed">' in vue and 'class="intro' not in vue
    assert "Via Cattori 12, 6900 Lugano" in vue and "info@acacoozlc.ch" in vue and "+41 91 623 48 57" in vue and "UID CHE-" in vue
    assert "{{DOMAIN}}" not in vue
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "nwf-aca-coozlc-ch-de") == []


def test_hr_privacy_route_without_privacy_in_href_is_renamed_with_alias():
    """nwf-kalem/homtud/kriz… (hr, 20–21.10): сторінка «Privatnost» на
    /privatnost є і в футері, а QA 10 віток поспіль пише «нет ссылки на
    политику» — його детектор судить за href без хорватської. Роут стає
    /privacy-policy по всьому src/, старий path лишається alias-ом."""
    _fresh_pools()
    hr = dict(NODE)
    hr["src/data/pages.js"] = NODE["src/data/pages.js"].replace('"name": "Datenschutz"', '"name": "Privatnost"').replace('"/datenschutz"', '"/privatnost"')
    hr["src/router/index.js"] = NODE["src/router/index.js"].replace("'/datenschutz'", "'/privatnost'")
    hr["src/components/CookieBanner.vue"] = '<template><a href="/privatnost">Privatnost</a> <a href="/privatnost-x">x</a></template>\n'
    issues = mod.run_branch(dict(hr), list(hr), "nwf-kamiv-cospubtenp-hr-hr")
    assert len(issues) == 1 and "/privatnost" in issues[0]["message"] and "/privacy-policy" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(hr), list(hr), "nwf-kamiv-cospubtenp-hr-hr")}
    assert set(acts) == {"src/data/pages.js", "src/router/index.js", "src/components/CookieBanner.vue"}, acts.keys()
    assert '"route": "/privacy-policy"' in acts["src/data/pages.js"] and '"name": "Politika privatnosti"' in acts["src/data/pages.js"]
    assert "path: '/privacy-policy',\n    alias: '/privatnost'" in acts["src/router/index.js"]
    assert 'href="/privacy-policy">Privatnost' in acts["src/components/CookieBanner.vue"]
    assert 'href="/privatnost-x"' in acts["src/components/CookieBanner.vue"], "інший роут з тим самим префіксом не чіпаємо"
    fixed = {**hr, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "nwf-kamiv-cospubtenp-hr-hr") == []
    # de-вітка з /datenschutz — як і була, тихо
    assert mod.run_branch(dict(NODE), list(NODE), "nwf-aca-coozlc-de-de") == []


def test_jp_branch_gets_japanese_privacy_page_and_recognises_existing_one():
    """jp-jp p-36 / [1258] (26.10): 7 вайтів без політики, чек мовчав — «jp»
    не було в PAGE. Локаль -jp-jp (і -jp-ja-jp-jp) → мова ja: сторінка
    privacy-policy.html з h1 «プライバシーポリシー», закон — 個人情報保護法,
    адреса — з 〒-рядка сайту, лінк у підвалі без <footer> (після ©). Наявна
    «個人情報保護方針» за назвою вкладки — політика, навіть без privac у шляху."""
    _fresh_pools()
    home = ('<html lang="ja"><head><title>桐乃屋｜家具の修理・修復</title>'
            '<meta name="description" content="桐乃屋は東京で家具の修理・修復を行う工房です。"></head><body>'
            '<header><h1 id="logo"><a href="./"><img alt="桐乃屋" src="logo.svg"/></a></h1><nav><a href="./">ホーム</a></nav></header><main><h1>家具の修復</h1></main>'
            '<div class="foot"><p>〒150-0001 東京都渋谷区神宮前3-15-2</p><p><a href="tel:0368052203">03-6805-2203</a></p>'
            '<p>© 2026 桐乃屋 All rights reserved.</p></div></body></html>')
    files = {"index.php": home, "pages/about/index.html": home.replace("<h1>家具の修復</h1>", "<h1>桐乃屋について</h1>")}
    issues = mod.run_branch(dict(files), list(files), "kicotego-jp-jp")
    assert len(issues) == 1 and "プライバシーポリシー" in issues[0]["message"], issues
    assert mod.run_branch(dict(files), list(files), "ortun-sqioha-jp-ja-jp-jp") == issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "kicotego-jp-jp")}
    assert set(acts) == {"index.php", "pages/about/index.html", "privacy-policy.html"}, acts.keys()
    page = acts["privacy-policy.html"]
    assert "<title>プライバシーポリシー – 桐乃屋</title>" in page and "<h1>プライバシーポリシー</h1>" in page
    # лого-h1 шапки лишається лого (fugruxoge-atowoos 27.10: підмінялось заголовком)
    assert '<h1 id="logo"><a href="./"><img alt="桐乃屋" src="logo.svg"/></a></h1>' in page, page[:600]
    # Wix: текстовий <h1 class="font_6"> з назвою всередині <header> (hajipo-kabe 27.10) — теж лишається
    wix = {p: t.replace('<h1 id="logo"><a href="./"><img alt="桐乃屋" src="logo.svg"/></a></h1>', '<h1 class="font_6">桐乃屋</h1>') for p, t in files.items()}
    wpage = {a["path"]: a["content"] for a in mod.fix_branch(dict(wix), list(wix), "kicotego-jp-jp")}["privacy-policy.html"]
    assert '<header><h1 class="font_6">桐乃屋</h1>' in wpage and "<h1>プライバシーポリシー</h1>" in wpage, wpage[:600]
    assert "個人情報保護法" in page and "東京都渋谷区神宮前3-15-2" in page and "03-6805-2203" in page
    assert "info@{{DOMAIN}}" in page and "桐乃屋は東京で家具の修理・修復を行う工房です" in page
    assert "Impressum" not in page and "UID" not in page, "jp — без Impressum і реєстрових номерів"
    for p, pre in (("index.php", ""), ("pages/about/index.html", "../../")):
        assert f'<p><a href="{pre}privacy-policy.html">プライバシーポリシー</a></p>' in acts[p], p
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "kicotego-jp-jp") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "kicotego-jp-jp") == []
    # наявна політика під японською назвою і шляхом без privac — уже є
    pol = home.replace("<title>桐乃屋｜家具の修理・修復</title>", "<title>個人情報保護方針｜桐乃屋</title>")
    has = {"index.php": home.replace("<p>© 2026", '<p><a href="policies/kojin/index.html">個人情報保護方針</a></p><p>© 2026'),
           "policies/kojin/index.html": pol}
    assert mod.run_branch(dict(has), list(has), "kicotego-jp-jp") == []


def test_jp_site_without_footer_or_copyright_anchors_on_company_block():
    """yahoge-kokea / mohiol (26.10): ні <footer>, ні ©, останній видимий блок —
    назва юрособи «株式会社…» або пошта, далі лише кукі-банер лаби. Чек
    скаржився, фікс давав 0 дій (оболонці нема за що зачепитись). Якорем
    підвалу стає блок з японським юр-суфіксом / mailto:, банер — не підвал."""
    _fresh_pools()
    banner = ('<div data-wp-consent-bar="1" style="position:fixed;bottom:0"><span>当サイトではクッキーを使用しています。</span>'
              '<button type="button" data-wp-consent="accept">同意する</button></div>')
    home = ('<html lang="ja"><head><title>大和古材工房｜古民家建具の修復</title></head><body>'
            '<header><nav><a href="./">ホーム</a></nav></header><main><h1>古材の修復</h1></main>'
            '<div class="info"><p>奈良県天理市を拠点に建具を修復しています。</p><p class="corp">株式会社大和古材工房</p></div>'
            + banner + '<script>var k=1</script></body></html>')
    files = {"index.php": home, "company/index.html": home.replace("<h1>古材の修復</h1>", "<h1>会社概要</h1>")}
    assert len(mod.run_branch(dict(files), list(files), "yahoge-kokea-jp-jp")) == 1
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "yahoge-kokea-jp-jp")}
    assert set(acts) == {"index.php", "company/index.html", "privacy-policy.html"}, acts.keys()
    assert '<p class="corp">株式会社大和古材工房</p>\n<p class="corp"><a href="privacy-policy.html">プライバシーポリシー</a></p>' in acts["index.php"]
    assert '<a href="../privacy-policy.html">プライバシーポリシー</a>' in acts["company/index.html"]
    page = acts["privacy-policy.html"]
    assert "<h1>プライバシーポリシー</h1>" in page and "株式会社大和古材工房" in page and "古材の修復</h1>" not in page
    assert "data-wp-consent" in page, "кукі-банер лишається у оболонці як частина підвалу"
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "yahoge-kokea-jp-jp") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "yahoge-kokea-jp-jp") == []
    # пошта як якір (mohiol): останній блок — <p> з mailto
    mail = home.replace('<p class="corp">株式会社大和古材工房</p>', '<p><a href="mailto:satohy@{{DOMAIN}}">satohy@{{DOMAIN}}</a></p>')
    acts = {a["path"]: a["content"] for a in mod.fix_branch({"index.php": mail}, ["index.php"], "mohiol-jp-jp")}
    assert '<p><a href="mailto:satohy@{{DOMAIN}}">satohy@{{DOMAIN}}</a></p>\n<p><a href="privacy-policy.html">プライバシーポリシー</a></p>' in acts["index.php"]


def test_ch_impressum_without_address_gets_the_contact_block():
    """resonance / cap-hokajup / equipage ch-fr (26.10): QA «На Impressum
    регномер CHE-… есть, но нет адреса компании. В Impressum должны стоять
    регномер, адрес и телефон или почта». Сторінка є і залінкована — чек
    мовчав. Тепер Impressum без адреси — знахідка; фікс дописує блок
    реквізитів (назва, адреса, телефон, пошта, UID) одразу під h1 у стилі
    першого абзацу сторінки; Impressum з адресою — як і був."""
    _fresh_pools()
    files = _ch_files()
    imp = (HEAD.replace("Erscurab – Nachfolgeplanung", "Impressum – Erscurab") + HEADER
           + '<main class="legal-main"><h1 class="title">Impressum</h1>'
           '<div class="card"><p class="body-text">N° IDE CHE-346.650.747</p>'
           '<p class="body-text">Tous droits réservés.</p></div></main>' + FOOTER)
    files["impressum.html"] = imp
    for p in ("index.php", "privacy-policy.html", "terms-conditions.html"):
        files[p] = files[p].replace('<li><a href="./terms-conditions.html" class="lnk">Nutzungsbedingungen</a></li>',
                                    '<li><a href="./terms-conditions.html" class="lnk">Nutzungsbedingungen</a></li>'
                                    '<li><a href="./impressum.html" class="lnk">Impressum</a></li>')
    issues = mod.run_branch(dict(files), list(files), "erscurab-ch-de")
    assert len(issues) == 1 and "без адреси" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "erscurab-ch-de")}
    assert set(acts) == {"impressum.html"}, acts.keys()
    page = acts["impressum.html"]
    block = page[page.index("</h1>"):page.index("N° IDE CHE-346.650.747")]
    assert "Vordergasse 48, 8200 Schaffhausen" in block and "+41 52 631 09 74" in block and "info@{{DOMAIN}}" in block
    assert "UID CHE-346.650.747" in block and 'class="body-text"' in block, block
    assert page.count("CHE-346.650.747") == 2 and "UID CHE-" in page
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "erscurab-ch-de") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "erscurab-ch-de") == []
    # Impressum з адресою — тиша
    ok = dict(files); ok["impressum.html"] = imp.replace("Tous droits réservés.", "Vordergasse 48, 8200 Schaffhausen")
    assert mod.run_branch(dict(ok), list(ok), "erscurab-ch-de") == []


def test_node_ch_impressum_component_without_address_gets_the_contact_block():
    """QA «В Impressum должны стоять регномер, адрес и телефон». Node: готовий
    Impressum-компонент вітки теж буває без адреси (повний блок генерує лише
    _node_actions для НОВОЇ сторінки; наявний компонент фікс лише дописує)."""
    _fresh_pools()
    files = dict(NODE)
    files["src/pages/Impressum.vue"] = ("<template><div><ImpressumDetails /></div></template>\n"
        "<script>\nimport ImpressumDetails from '@/components/ImpressumDetails.vue'\n"
        "export default { components: { ImpressumDetails } }\n</script>\n")
    files["src/components/ImpressumDetails.vue"] = (
        '<template>\n  <main class="max-w-4xl mx-auto px-4 py-12">\n'
        '    <h1 class="font-sans text-4xl text-stone-900">Impressum</h1>\n'
        '    <p class="intro text-center">Angaben gemäss Schweizer Recht.</p>\n'
        '    <section class="mb-8"><h2 class="font-sans text-2xl">Firma</h2>\n'
        '    <p class="font-sans text-stone-500 leading-relaxed">UID CHE-123.456.789</p></section>\n'
        '  </main>\n</template>\n')
    branch = "nwf-aca-coozlc-ch-de"
    issues = mod.run_branch(dict(files), list(files), branch)
    assert len(issues) == 1 and issues[0]["path"] == "src/components/ImpressumDetails.vue" \
        and "без адреси" in issues[0]["message"], issues
    f = mod.facts(files, branch)
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), branch)}
    assert set(acts) == {"src/components/ImpressumDetails.vue"}, acts.keys()
    vue = acts["src/components/ImpressumDetails.vue"]
    block = vue[vue.index("</h1>"):vue.index("Angaben gemäss")]
    assert f["address"] in block and f["phone"] in block and f["email"] in block and "UID CHE-123.456.789" in block
    assert block.count('class="intro text-center"') == 6, block
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), branch) == []
    assert mod.fix_branch(dict(fixed), list(fixed), branch) == []
    # компонент з адресою — тиша
    ok = dict(files)
    ok["src/components/ImpressumDetails.vue"] = files["src/components/ImpressumDetails.vue"].replace(
        "Angaben gemäss Schweizer Recht.", "Via Cattori 12, 6900 Lugano")
    assert mod.run_branch(dict(ok), list(ok), branch) == []


if __name__ == "__main__":
    run(dict(globals()))
