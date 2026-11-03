"""Тести map_block: прибрати з вайта блок з мапою (на вимогу баєра).

Кейс cavborel-it-it (коміт 5e70edf7): баєр попросив прибрати Google-карту —
вирізано <section id="map"> («Dove ci trovi» + iframe) і лінк «Vedi la mappa →»
на contatti.html. «Блок» — найменший елемент, у якому крім карти лише її
підписи; текст з адресою/годинами лишається.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                            # noqa: E402

mod = load_check("map_block")

BR = "cavborel-it-it"
GMAP = '<iframe src="https://www.google.com/maps?q=VIALE PARIOLI 112, 00197" allowfullscreen loading="lazy" title="Mappa della sede"></iframe>'

CONTACTS = ('    <section id="contacts" class="py-14">\n'
            '      <div class="max-w-7xl mx-auto"><h2>Contatti</h2>'
            '<form><input name="email"><button type="submit">Invia</button></form></div>\n'
            '    </section>\n')
FAQ = '    <section id="faq" class="py-14"><h2>FAQ</h2><p>Domande frequenti</p></section>\n'

# головна згенерованого вайта: секція карти = заголовок + карта
INDEX = ('<html><body>\n'
         '<nav><ul><li><a href="#contacts">Contatti</a></li><li><a href="#map">Dove siamo</a></li></ul></nav>\n'
         '<main>\n'
         + CONTACTS +
         '\n'
         '    <!-- MAP -->\n'
         '    <section id="map" class="py-14 bg-[#F7F0E0]">\n'
         '      <div class="max-w-7xl mx-auto px-4">\n'
         '        <h2 class="font-display text-3xl">Dove ci trovi</h2>\n'
         '        <div class="rounded-tile overflow-hidden shadow h-[400px]">\n'
         '          ' + GMAP + '\n'
         '        </div>\n'
         '      </div>\n'
         '    </section>\n'
         '\n'
         + FAQ +
         '</main>\n'
         '</body></html>\n')

INDEX_AFTER = ('<html><body>\n'
               '<nav><ul><li><a href="#contacts">Contatti</a></li></ul></nav>\n'
               '<main>\n'
               + CONTACTS +
               '\n'
               + FAQ +
               '</main>\n'
               '</body></html>\n')

CONTATTI = ('<html><body><main>\n'
            '  <div class="flex items-center gap-4">\n'
            '    <p>VIALE PARIOLI 112, 00197 ROMA RM, Italia</p>\n'
            '    <a href="./#map" class="text-sm font-semibold underline">Vedi la mappa →</a>\n'
            '  </div>\n'
            '  <p>L\'indirizzo è anche nella <a href="./#map" class="underline">pagina Home</a>.</p>\n'
            '</main></body></html>\n')

# секція карти з адресою й годинами: текст лишається, іде лише карта
STANDORT = ('<html><body>\n'
            '<!-- map-embed -->\n'
            '<section class="sec" id="map" aria-labelledby="map-h">\n'
            '  <div class="wrap">\n'
            '    <h2 id="map-h">Standort</h2>\n'
            '    <p class="lead">Hardturmstrasse 161, 8005 Zürich. Besuche nach Vereinbarung.</p>\n'
            '    <div class="map">\n'
            '      <iframe src="https://www.google.com/maps?q=Hardturmstrasse 161, 8005&amp;output=embed" title="Karte"></iframe>\n'
            '    </div>\n'
            '  </div>\n'
            '</section>\n'
            '</body></html>\n')

KONTAKT = ('<html><body>\n'
           '<p>Hardturmstrasse 161, 8005 Zürich <a class="lnk" href="./#map">Auf der Karte ansehen</a></p>\n'
           '<p>Mehr auf der <a href="./#map">Startseite</a>.</p>\n'
           '</body></html>\n')


def _fix(files, branch=BR):
    out = dict(files)
    for a in mod.fix_branch(dict(files), list(files), branch):
        assert a["type"] == "edit", a
        out[a["path"]] = a["content"]
    return out


def test_generated_map_section_goes_whole_with_its_comment_and_menu_item():
    out = _fix({"index.php": INDEX})["index.php"]
    assert out == INDEX_AFTER, out


def test_links_to_the_removed_section_from_other_pages():
    """«Vedi la mappa →» веде на вирізану секцію — лінк іде (разом з рядком);
    «pagina Home» — звичайний текст у реченні: лінк лишається, але вже на
    головну без мертвого якоря."""
    out = _fix({"index.php": INDEX, "contatti.html": CONTATTI})["contatti.html"]
    assert "Vedi la mappa" not in out and "#map" not in out, out
    assert '<p>VIALE PARIOLI 112, 00197 ROMA RM, Italia</p>\n  </div>' in out, out
    assert '<a href="./" class="underline">pagina Home</a>' in out, out


def test_location_text_stays_only_the_map_goes():
    map_lines = STANDORT[STANDORT.find('    <div class="map">'):STANDORT.find('  </div>\n</section>')]
    out = _fix({"index.php": STANDORT})["index.php"]
    assert out == STANDORT.replace(map_lines, ""), out


def test_map_link_to_a_kept_section_goes_other_links_stay():
    """Секція #map лишилась (у ній адреса), але карти в ній уже немає:
    «Auf der Karte ansehen» бреше — прибираємо; «Startseite» веде на живий
    якір — не чіпаємо."""
    out = _fix({"index.php": STANDORT, "kontakt.html": KONTAKT})["kontakt.html"]
    assert "<p>Hardturmstrasse 161, 8005 Zürich</p>" in out, out
    assert '<p>Mehr auf der <a href="./#map">Startseite</a>.</p>' in out, out


def test_address_heading_is_not_a_caption():
    """Elementor 50/50: ліворуч заголовок з адресою, праворуч віджет карти.
    Колонка карти йде цілком, колонка адреси — ні (адреса в <h3> не підпис)."""
    left = ('<div class="elementor-column elementor-col-50"><div class="elementor-widget-wrap">'
            '<div class="elementor-widget elementor-widget-heading"><div class="elementor-widget-container">'
            '<h3 class="elementor-heading-title">R. Tenente Helin, 35 - Santa Cruz, Belo Horizonte/MG</h3>'
            '</div></div></div></div>')
    right = ('<div class="elementor-column elementor-col-50"><div class="elementor-widget-wrap elementor-element-populated">'
             '<div class="elementor-element elementor-widget elementor-widget-google_maps" data-widget_type="google_maps.default">'
             '<div class="elementor-widget-container"><div class="elementor-custom-embed">'
             '<iframe loading="lazy" src="https://maps.google.com/maps?q=RUA%20TENENTE%20HELIN&amp;t=m&amp;z=14&amp;output=embed&amp;iwloc=near" '
             'title="RUA TENENTE HELIN,35" aria-label="RUA TENENTE HELIN,35"></iframe>'
             '</div></div></div></div></div>')
    page = ('<html><body><section class="elementor-section"><div class="elementor-container">'
            + left + right + '</div></section></body></html>')
    out = _fix({"contato/index.html": page})["contato/index.html"]
    assert out == page.replace(right, ""), out


def test_two_column_grid_collapses_to_one():
    page = ('<html><body><section id="localizacao"><div class="container"><h2>Onde Estamos</h2>'
            '<div class="grid grid-cols-1 lg:grid-cols-2 gap-8">'
            '<div class="rounded-lg h-[400px]"><iframe src="https://www.google.com/maps/embed?pb=!1m18!1m12"></iframe></div>'
            '<div class="card"><p>Rua Padre Eustáquio, 1200 - Belo Horizonte</p></div>'
            '</div></div></section></body></html>')
    out = _fix({"index.php": page})["index.php"]
    assert "<iframe" not in out, out
    assert '<div class="grid grid-cols-1 gap-8"><div class="card">' in out, out
    assert "<h2>Onde Estamos</h2>" in out, out


def test_lazy_iframe_and_its_noscript_twin_go_together():
    page = ('<html><body><section><h2>Contato</h2><p>Av. Brasil, 500 - Centro</p>'
            '<div class="map"><iframe src="about:blank" data-lazy-src="https://www.google.com/maps/embed?pb=!1m14"></iframe>'
            '<noscript><iframe src="https://www.google.com/maps/embed?pb=!1m14"></iframe></noscript></div>'
            '</section></body></html>')
    block = page[page.find('<div class="map">'):page.find('</section>')]
    out = _fix({"index.php": page})["index.php"]
    assert out == page.replace(block, ""), out


def test_wix_map_component_goes():
    wix = ('<div class="DDi8v8 comp-iz3253wc wixui-google-map" id="comp-iz3253wc"><wix-iframe data-src="">'
           '<div class="oD_vT7" id="mapContainer_comp-iz3253wc"><iframe allowfullscreen="" data-src="" '
           'src="https://static.parastorage.com/services/editor-elements-library/dist/thunderbolt/media/'
           'googleMap.f3347ff6.html?defaultLocation=0&amp;language=pt"></iframe></div></wix-iframe></div>')
    page = ('<html><body><div data-mesh-id="comp-lfh0y4sl4inlineContent-gridContainer">'
            '<div class="wixui-rich-text" id="comp-txt"><p>Rua João de Deus, 75 - Contagem/MG</p></div>'
            + wix + '</div></body></html>')
    out = _fix({"index.php": page})["index.php"]
    assert out == page.replace(wix, ""), out


GJS_PAGE = ('<html><head></head><body><main>\n'
            '<script src="../../_ext/maps.googleapis.com/maps/api/js__q7f9f49ba.js"></script>\n'
            '<div class="panel-body">\n'
            '  <div class="col-sm-6"><b>Endereço</b><br/>Av. Vinte e Um de Janeiro, 4151</div>\n'
            '  <div id="map-canvas-2" style="width: 100%; height: 400px"></div>\n'
            '</div>\n'
            '<script>\n'
            ' function initialize_2 () {\n'
            '  var map = new google.maps.Map(document.getElementById(\'map-canvas-2\'), {zoom: 15});\n'
            '  var marker = new google.maps.Marker({map: map, position: map.getCenter()});\n'
            ' }\n'
            ' google.maps.event.addDomListener(window, \'load\', initialize_2);\n'
            '</script>\n'
            '</main>\n'
            '<footer><a href="http://maps.google.com/?q=Av.+Vinte+e+Um+de+Janeiro,+4151">Como chegar</a></footer>\n'
            '</body></html>\n')


def test_google_js_map_goes_with_its_init_script_and_api_include():
    """miwhuetqivi: лінк «Como chegar» на maps.google.com у футері бібліотеки
    не потребує — підключення API однаково йде разом з JS-картою."""
    out = _fix({"localizacao/593/index.html": GJS_PAGE})["localizacao/593/index.html"]
    assert "map-canvas-2" not in out and "google.maps" not in out, out
    assert "maps.googleapis.com" not in out, out
    assert "Av. Vinte e Um de Janeiro, 4151" in out and ">Como chegar</a>" in out, out


LEAFLET_PAGE = ('<html><head>\n'
                '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>\n'
                '</head><body>\n'
                '<section id="mappa"><h2>Dove siamo</h2><div id="map" class="h-96"></div></section>\n'
                '<section id="faq"><h2>FAQ</h2></section>\n'
                '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>\n'
                '<script>\n'
                'var mapConfig = { address: "Via Roma 10, Milano" };\n'
                'fetch("https://nominatim.openstreetmap.org/search?format=json&q=" + encodeURIComponent(mapConfig.address))\n'
                '  .then(function (r) { return r.json(); }).then(function (d) {\n'
                '    var map = L.map(\'map\').setView([d[0].lat, d[0].lon], 15);\n'
                '    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(map);\n'
                '  });\n'
                '</script>\n'
                '</body></html>\n')


def test_leaflet_map_goes_with_its_script_and_assets():
    out = _fix({"index.php": LEAFLET_PAGE})["index.php"]
    assert out == ('<html><head>\n'
                   '</head><body>\n'
                   '<section id="faq"><h2>FAQ</h2></section>\n'
                   '</body></html>\n'), out


def test_js_map_inside_a_mixed_script_is_left_for_a_human():
    """Ініціалізація карти в одному скрипті з меню: вирізати скрипт — убити
    меню, лишити — Leaflet упаде без контейнера і потягне меню за собою."""
    page = LEAFLET_PAGE.replace(
        "var mapConfig",
        "document.getElementById('burger').addEventListener('click', function () {});\nvar mapConfig")
    files = {"index.php": page}
    assert mod.fix_branch(dict(files), list(files), BR) == []
    issues = mod.run_branch(files, list(files), BR)
    assert issues and all(i["severity"] == "warn" for i in issues), issues


def test_spa_bundle_map_is_left_for_a_human():
    """React/Vite-вайт: карта є і в статичному HTML, і в бандлі — після
    гідратації бандл намалює її знову, тож правка HTML нічого не дає."""
    page = ('<html><body><div id="root"><section><h2>Onde Estamos</h2>'
            '<div class="h-[400px]"><iframe src="https://www.google.com/maps/embed?pb=!1m18"></iframe></div>'
            '</section></div><script type="module" crossorigin src="./assets/index-BWgAp7hM.js?v=2"></script>'
            '</body></html>')
    files = {"index.php": page,
             "assets/index-BWgAp7hM.js": 'c.jsx("iframe",{src:"https://www.google.com/maps/embed?pb=!1m18"})'}
    assert mod.fix_branch(dict(files), list(files), BR) == []
    issues = mod.run_branch(files, list(files), BR)
    assert len(issues) == 1 and issues[0]["severity"] == "warn", issues
    assert "assets/index-BWgAp7hM.js" in issues[0]["message"], issues


def test_external_map_link_alone_is_not_a_map_block():
    page = ('<html><body><address>Rua Visconde de Pirajá, 414</address>'
            '<a href="https://www.google.com/maps/search/?api=1&amp;query=Rua%20Visconde" target="_blank">'
            'Abrir no Google Maps</a></body></html>')
    files = {"index.php": page}
    assert mod.run_branch(files, list(files), BR) == []
    assert mod.fix_branch(dict(files), list(files), BR) == []


def test_second_pass_changes_nothing():
    files = {"index.php": INDEX, "contatti.html": CONTATTI, "standort.html": STANDORT,
             "kontakt.html": KONTAKT}
    once = _fix(files)
    assert mod.fix_branch(dict(once), list(once), BR) == []
    assert mod.run_branch(once, list(once), BR) == []


def test_report_names_every_page_the_fix_will_touch():
    """Карти — на index.php і standort.html; contatti.html — лінк на секцію,
    що зникне. Людина бачить усе це ДО застосування."""
    files = {"index.php": INDEX, "contatti.html": CONTATTI, "standort.html": STANDORT}
    issues = mod.run_branch(files, list(files), BR)
    assert {i["path"] for i in issues} == {"index.php", "contatti.html", "standort.html"}, issues
    assert all(i["severity"] == "info" and i.get("line") for i in issues), issues


if __name__ == "__main__":
    run(dict(globals()))
