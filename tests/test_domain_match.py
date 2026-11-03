"""Перший чек vue-віток: пошти і доменні назви ↔ підв'язаний домен таски.

Домен береться з ClickUp (Required Domains) і живе в domains.active_for().
Судимо лише вітки, яким домен підв'язано.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, load_check, run                   # noqa: E402

sys.path.insert(0, str(ROOT))

mod = load_check("domain_match")
BRANCH = "apoj-gencaa-br-pt"
DOMAIN = "apojgenc.sbs"


def _with_domain(domain: str | None = DOMAIN):
    mod._domain_for = lambda branch: domain


def _run(files: dict) -> list[dict]:
    return mod.run_branch(dict(files), list(files), BRANCH)


def _fix(files: dict) -> dict:
    """fix_branch → {path: новий вміст} (тільки змінені файли)."""
    return {a["path"]: a["content"]
            for a in mod.fix_branch(dict(files), list(files), BRANCH)}


# ---------------------------------------------------------------- пошта
def test_brace_domain_in_email_is_flagged():
    """`info@{{DOMAIN}}` у .vue — це НЕ плейсхолдер, а інтерполяція Vue:
    змінної DOMAIN немає, і в білді лишається голе `info@`."""
    _with_domain()
    files = {"src/components/ContactFormHome.vue": "<p>info@{{DOMAIN}}</p>"}
    issues = _run(files)
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "error"
    assert "info@apojgenc.sbs" in issues[0]["message"], issues


def test_brace_domain_is_replaced_by_the_bound_domain():
    _with_domain()
    files = {"src/components/ContactFormHome.vue":
             '<a href="mailto:info@{{DOMAIN}}">info@{{DOMAIN}}</a>'}
    out = _fix(files)["src/components/ContactFormHome.vue"]
    assert out == '<a href="mailto:info@apojgenc.sbs">info@apojgenc.sbs</a>', out


def test_foreign_brand_email_is_flagged_and_fixed():
    """Шаблонний хвіст іншого проєкту: kontakt@passobjip.com на apojgenc.sbs."""
    _with_domain()
    files = {"pages/kontakt.vue": "<p>kontakt@passobjip.com</p>"}
    assert len(_run(files)) == 1
    assert _fix(files)["pages/kontakt.vue"] == "<p>kontakt@apojgenc.sbs</p>"


def test_local_part_is_kept():
    _with_domain()
    files = {"pages/faq.vue": "datenschutz@passobjip.com und werbung@passobjip.com"}
    out = _fix(files)["pages/faq.vue"]
    assert out == "datenschutz@apojgenc.sbs und werbung@apojgenc.sbs", out


def test_email_already_on_the_bound_domain_is_silent():
    _with_domain()
    files = {"src/components/Contact.vue": "<p>info@apojgenc.sbs</p>"}
    assert _run(files) == []
    assert _fix(files) == {}


def test_form_placeholder_is_an_example_not_a_contact():
    _with_domain()
    files = {"src/components/Form.vue":
             '<input placeholder="seu@empresa.com.br">'
             "<span>{ placeholder: 'ihre@email.ch' }</span>"}
    assert _run(files) == []
    assert _fix(files) == {}


def test_asset_and_url_authority_are_not_emails():
    _with_domain()
    files = {"src/App.vue": '<img src="hero@2x.png">',
             "src/sentry.ts": "https://key@o18.ingest.sentry.io/128"}
    assert _run(files) == []


# ------------------------------------------------------- самопосилання
def test_sitemap_and_robots_placeholder_domain_is_flagged():
    """`public/` їде у dist як є — https://domain.com/ у сайтмапі це бойовий SEO."""
    _with_domain()
    files = {"public/robots.txt": "Sitemap: https://domain.com/sitemap.xml",
             "public/sitemap.xml": "<url><loc>https://domain.com/</loc></url>"}
    issues = _run(files)
    assert len(issues) == 2, issues
    out = _fix(files)
    assert out["public/robots.txt"] == "Sitemap: https://apojgenc.sbs/sitemap.xml"
    assert out["public/sitemap.xml"] == "<url><loc>https://apojgenc.sbs/</loc></url>"


def test_canonical_og_url_and_site_url_are_checked():
    _with_domain()
    files = {"nuxt.config.ts": "siteUrl: 'https://passobjip.com',",
             "index.html": '<link rel="canonical" href="https://passobjip.com">'
                           '<meta property="og:url" content="https://passobjip.com">'}
    assert len(_run(files)) == 3, _run(files)
    out = _fix(files)
    assert "https://apojgenc.sbs" in out["nuxt.config.ts"]
    assert "passobjip.com" not in out["index.html"]


def test_correct_canonical_is_silent():
    _with_domain()
    files = {"index.html": '<link rel="canonical" href="https://apojgenc.sbs">'}
    assert _run(files) == []


def test_www_of_the_bound_domain_counts_as_its_own():
    _with_domain()
    files = {"index.html": '<link rel="canonical" href="https://www.apojgenc.sbs/">'}
    assert _run(files) == []


def test_third_party_links_are_not_touched():
    """Сторонні лінки не в самопосильній позиції — не наша справа."""
    _with_domain()
    files = {"src/pages/Home.vue":
             '<a href="https://www.sbb.ch">SBB</a>'
             '<img src="https://images.unsplash.com/photo-1.jpg">'
             '<svg xmlns="http://www.w3.org/2000/svg"></svg>'}
    assert _run(files) == []
    assert _fix(files) == {}


# ------------------------------------------------- згадки того ж бренду
def test_bare_mention_of_the_leaked_domain_is_flagged():
    """Домен спалився у пошті → його згадки у текстах теж наші."""
    _with_domain()
    files = {"pages/kontakt.vue": "<p>kontakt@passobjip.com</p>",
             "i18n/locales/de.json": '{"seo": "PassoBjip auf passobjip.com: News"}'}
    issues = _run(files)
    paths = {i["path"] for i in issues}
    assert paths == {"pages/kontakt.vue", "i18n/locales/de.json"}, issues
    out = _fix(files)
    assert out["i18n/locales/de.json"] == '{"seo": "PassoBjip auf apojgenc.sbs: News"}'


def test_bare_word_without_tld_is_not_a_domain():
    """`parragraf-theme` — ключ localStorage, а не домен."""
    _with_domain()
    files = {"pages/kontakt.vue": "<p>kontakt@passobjip.com</p>",
             "app.vue": "const THEME_KEY = 'parragraf-theme'"}
    assert {i["path"] for i in _run(files)} == {"pages/kontakt.vue"}
    assert "app.vue" not in _fix(files)


def test_unknown_domain_in_plain_text_is_not_invented():
    """Ніяких TLD-списків: домен ловиться лише через пошту/самопосилання."""
    _with_domain()
    files = {"src/data/posts.ts": "const url = 'nuxt.com/docs'; // index.ts, vue.js"}
    assert _run(files) == []


# ------------------------------------------------------------- скіпи
def test_branch_without_bound_domain_is_skipped():
    _with_domain(None)
    files = {"src/App.vue": "<p>kontakt@passobjip.com</p>"}
    assert _run(files) == []
    assert _fix(files) == {}


def test_reserved_example_domains_are_skipped():
    _with_domain()
    files = {"src/pages/Terms.vue": "<p>legal@example.com</p>"}
    assert _run(files) == []


def test_lockfile_is_not_scanned():
    _with_domain()
    files = {"package-lock.json": '{"resolved": "https://kontakt@passobjip.com/x"}'}
    assert _run(files) == []


# ------------------------------------------- {{DOMAIN}} як хост лінка
def test_brace_domain_in_og_image_is_flagged_and_fixed():
    """og:image/twitter:image не входять у список самопосилань, а брейс ламає
    їх так само: у білді лишається `https:///og-image.jpg`."""
    _with_domain()
    files = {"index.html": (
        '<meta property="og:image" content="https://{{DOMAIN}}/og-image.jpg">\n'
        '<meta name="twitter:image" content="https://{{DOMAIN}}/twitter-card.jpg">')}
    issues = _run(files)
    assert len(issues) == 2, issues
    out = _fix(files)["index.html"]
    assert out.count(f"https://{DOMAIN}/") == 2, out
    assert "{{DOMAIN}}" not in out, out


def test_fix_replaces_only_the_host_not_the_whole_url():
    """Ручна заміна брейса на «https://домен/» давала подвійну схему —
    `https://https://vivhurti.cyou//og-image.jpg`. Міняється САМЕ хост."""
    _with_domain()
    files = {"index.html": '<meta content="https://{{DOMAIN}}/og-image.jpg">'}
    out = _fix(files)["index.html"]
    assert out == f'<meta content="https://{DOMAIN}/og-image.jpg">', out
    assert "https://https://" not in out and "//og-image" not in out, out


def test_brace_url_in_visible_text_is_flagged():
    """356 таких на корпусі — юридичні сторінки з «Web: https://{{DOMAIN}}»."""
    _with_domain()
    files = {"src/components/PrivacyNotice.vue":
             '<p class="break-all">https://{{DOMAIN}}</p>'}
    assert len(_run(files)) == 1
    assert _fix(files)["src/components/PrivacyNotice.vue"] == \
        f'<p class="break-all">https://{DOMAIN}</p>'


def test_protocol_relative_brace_url_is_fixed():
    _with_domain()
    files = {"index.html": '<link href="//{{DOMAIN}}/style.css">'}
    assert _fix(files)["index.html"] == f'<link href="//{DOMAIN}/style.css">'


def test_canonical_is_not_reported_twice():
    """canonical ловиться старим правилом; нове не сміє дублювати рядок."""
    _with_domain()
    files = {"index.html": '<link rel="canonical" href="https://{{DOMAIN}}/">'}
    issues = _run(files)
    assert len(issues) == 1, issues
    assert "canonical" in issues[0]["message"], issues


def test_brace_url_inside_placeholder_is_left_alone():
    _with_domain()
    files = {"index.html": '<input placeholder="https://{{DOMAIN}}/приклад">'}
    assert _run(files) == []
    assert _fix(files) == {}


def test_brace_url_fix_is_idempotent():
    _with_domain()
    files = {"index.html": '<meta content="https://{{DOMAIN}}/og.jpg">'}
    once = _fix(files)
    assert mod.fix_branch(dict(once), list(once), BRANCH) == []


# ------------------------------------------- хост БЕЗ зони = назва вітки
# Кейс nwf-alaroovk-praveiv-br-pt: генератор поставив хостом назву СУСІДНЬОЇ
# вітки - `info@alemoid-praveiv-br-pt` (7 входжень) плюс той самий рядок у
# canonical/og:url/twitter:url/og:image/JSON-LD і видимим текстом (ще 9).
# Домену без крапки не існує, тож і пошта, і всі самопосилання мертві, а чек
# їх не бачив: `_HOST` вимагає крапку і зону. На корпусі 1597 віток таких
# рядків 14 (49 входжень), і рівно три з них - хости-вітки (18 входжень):
# alemoid-praveiv-br-pt, devafibiro-rofa-br-pt, nozulaavupa-gencaa-br-pt.
def test_branch_name_as_email_host_is_flagged():
    _with_domain()
    files = {"src/components/GlobalFooter.vue":
             '<a href="mailto:info@alemoid-praveiv-br-pt">пошта</a>'}
    issues = _run(files)
    assert len(issues) == 1, issues
    assert f"info@{DOMAIN}" in issues[0]["message"], issues


def test_branch_name_as_email_host_is_fixed_in_href_and_text():
    _with_domain()
    p = "src/components/GlobalFooter.vue"
    files = {p: '<a href="mailto:info@alemoid-praveiv-br-pt">'
                'info@alemoid-praveiv-br-pt</a>'}
    assert _fix(files)[p] == (f'<a href="mailto:info@{DOMAIN}">'
                             f'info@{DOMAIN}</a>')


def test_branch_name_as_canonical_host_is_fixed():
    """Той самий рядок стоїть хостом canonical - `https://alemoid-praveiv-br-pt`."""
    _with_domain()
    files = {"index.html":
             '<link rel="canonical" href="https://alemoid-praveiv-br-pt">'}
    issues = _run(files)
    assert len(issues) == 1, issues
    assert "canonical" in issues[0]["message"], issues
    assert _fix(files)["index.html"] == \
        f'<link rel="canonical" href="https://{DOMAIN}">'


def test_brand_name_with_at_sign_is_not_an_email():
    """«Pick@Post» - сервіс Swiss Post, 21 входження на корпусі. Не пошта:
    хост без крапки судимо лише тоді, коли він має суфікс вітки -<кк>-<мм>."""
    _with_domain()
    files = {"src/components/DeliveryInfo.vue": "<p>Pick@Post</p>"}
    assert _run(files) == []
    assert _fix(files) == {}


def test_dotless_word_host_is_not_an_email():
    """`console@server`, `rigor@ai`, `obrigado@residencia` - по одному на
    корпусі, це проза й код, а не контакти."""
    _with_domain()
    files = {"src/components/Log.vue": "<p>console@server rigor@ai</p>"}
    assert _run(files) == []
    assert _fix(files) == {}



def test_check_is_registered_for_node_only():
    assert mod.PROJECTS == ["node"], mod.PROJECTS
    assert mod.GROUP == "auto"


if __name__ == "__main__":
    run(dict(globals()))
