import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                       # noqa: E402

fav = load_check("favicon")


def test_placeholder_href_is_broken():
    state, msg = fav._link_state("index.php", "{{LOGO}}", None, set(), {})
    assert state == "broken", state
    assert "плейсхолдер" in msg, msg


def test_dollar_placeholder_is_broken():
    state, _ = fav._link_state("index.php", "${LOGO}", None, set(), {})
    assert state == "broken", state


def test_percent_placeholder_is_broken():
    state, _ = fav._link_state("index.php", "%%LOGO%%", None, set(), {})
    assert state == "broken", state


def test_empty_href_is_broken():
    state, msg = fav._link_state("index.php", "   ", None, set(), {})
    assert state == "broken", state
    assert "порожн" in msg, msg


def test_existing_file_is_ok():
    state, _ = fav._link_state("index.php", "/favicon.svg",
                               None, {"favicon.svg"}, {"favicon.svg": "favicon.svg"})
    assert state == "ok", state


def test_missing_file_is_broken():
    state, msg = fav._link_state("index.php", "/favicon.svg", None, set(), {})
    assert state == "broken", state
    assert "неіснуючий" in msg, msg


def test_case_mismatch_is_broken():
    state, msg = fav._link_state("index.php", "/Favicon.SVG",
                                 None, {"favicon.svg"}, {"favicon.svg": "favicon.svg"})
    assert state == "broken", state
    assert "регістр" in msg, msg


def test_external_url_is_ok():
    state, _ = fav._link_state("index.php", "https://cdn.example.com/i.png",
                               None, set(), {})
    assert state == "ok", state


def test_valid_data_uri_is_ok():
    # найменший валідний PNG (1x1), base64
    png = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
           "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    state, msg = fav._link_state("index.php", png, "image/png", set(), {})
    assert state == "ok", msg


def test_broken_base64_is_broken():
    state, msg = fav._link_state("index.php", "data:image/png;base64,!!!!",
                                 "image/png", set(), {})
    assert state == "broken", state
    assert "base64" in msg, msg


def test_no_href_is_skip():
    state, _ = fav._link_state("index.php", None, None, set(), {})
    assert state == "skip", state


PAGE_BROKEN = """<!DOCTYPE html><html><head>
<title>Siftegoba</title>
<link rel="icon" href="{{LOGO}}" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="{{LOGO}}">
<link rel="apple-touch-icon" sizes="180x180" href="{{LOGO}}">
</head><body>Hi</body></html>"""

PAGE_OK = """<!DOCTYPE html><html><head>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
</head><body>Hi</body></html>"""

PAGE_NO_HEAD = """<div class="footer">частковина без head</div>"""

PAGE_PRIVACY = """<!DOCTYPE html><html><head>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
</head><body><p>This may include your name and require verification.</p></body></html>"""


def test_branch_with_placeholders_reports_warning():
    issues = fav.run_branch({"index.php": PAGE_BROKEN}, ["index.php"])
    errors = [i for i in issues if i["severity"] == "warn"]
    assert errors, issues
    assert any("іконк" in i["message"] for i in errors), errors


def test_healthy_branch_is_clean():
    issues = fav.run_branch({"index.php": PAGE_OK}, ["index.php", "favicon.svg"])
    assert issues == [], issues


def test_root_favicon_ico_saves_page_without_links():
    # favicon.ico — єдиний файл, який браузер підхопить БЕЗ <link rel=icon>.
    page = "<!DOCTYPE html><html><head><title>x</title></head><body>y</body></html>"
    issues = fav.run_branch({"index.php": page}, ["index.php", "favicon.ico"])
    assert issues == [], issues


def test_root_svg_favicon_without_link_is_still_warning():
    # Раніше будь-який favicon.* у корені (у т.ч. .svg) вважався «іконка є»
    # і глушив помилку — а браузер favicon.svg без <link> ніколи сам не
    # запитує, тож вкладка лишалась без іконки при "зеленому" чеку.
    page = "<!DOCTYPE html><html><head><title>x</title></head><body>y</body></html>"
    issues = fav.run_branch({"index.php": page}, ["index.php", "favicon.svg"])
    assert any(i["severity"] == "warn" for i in issues), issues


def test_page_without_links_and_without_root_favicon_is_warning():
    page = "<!DOCTYPE html><html><head><title>x</title></head><body>y</body></html>"
    issues = fav.run_branch({"index.php": page}, ["index.php"])
    assert any(i["severity"] == "warn" for i in issues), issues


def test_partial_without_head_is_ignored():
    issues = fav.run_branch({"footer.php": PAGE_NO_HEAD}, ["footer.php"])
    assert issues == [], issues


def test_word_require_in_text_does_not_silence_check():
    # старий PHP_INCLUDE_RX глушив ГІЛКУ no_icon_pages — той самий шлях, що
    # генерує агреговану помилку — на будь-якій сторінці зі словом
    # "require"/"include" у тексті. Тут сторінка НЕ має жодного
    # <link rel=icon> і favicon.* у корені немає, тож єдина причина, чому
    # перевірка може змовчати, — повернений глушник.
    page = """<!DOCTYPE html><html><head>
<title>Privacy</title>
</head><body><p>This may include your name and require verification.</p></body></html>"""
    issues = fav.run_branch({"privacy.html": page}, ["privacy.html"])
    assert any(i["severity"] == "warn" for i in issues), issues


def test_pages_are_aggregated_into_one_error():
    files = {f"p{i}.html": PAGE_BROKEN for i in range(6)}
    issues = fav.run_branch(files, list(files))
    no_icon = [i for i in issues if "робочої іконки" in i["message"]]
    assert len(no_icon) == 1, [i["message"] for i in issues]
    assert "6" in no_icon[0]["message"], no_icon[0]["message"]
    assert len(issues) == 1, issues   # точкові помилки не мають просочитись поверх агрегованої


def test_autoload_require_does_not_silence_check():
    # аналогічно — сторінка без <link rel=icon> взагалі, з require_once на
    # автозавантажувач у префіксі (типовий index.php); мовчання можливе
    # тільки якщо PHP_INCLUDE_RX повернути назад.
    page = ("<?php require_once __DIR__ . '/../vendor/autoload.php'; ?>"
            "<!DOCTYPE html><html><head><title>x</title></head>"
            "<body>y</body></html>")
    issues = fav.run_branch({"index.php": page}, ["index.php"])
    assert any(i["severity"] == "warn" for i in issues), issues


def test_link_to_non_image_file_is_broken():
    def read_bytes(path):
        return b"<!DOCTYPE html><html>not an image</html>"

    state, msg = fav._link_state("index.php", "/favicon.ico", None,
                                 {"favicon.ico"}, {"favicon.ico": "favicon.ico"},
                                 read_bytes=read_bytes)
    assert state == "broken", state
    assert "не є картинкою" in msg, msg


def test_link_to_real_svg_is_ok():
    def read_bytes(path):
        return b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'

    state, msg = fav._link_state("index.php", "/favicon.svg", None,
                                 {"favicon.svg"}, {"favicon.svg": "favicon.svg"},
                                 read_bytes=read_bytes)
    assert state == "ok", msg


def test_run_branch_accepts_branch_argument():
    issues = fav.run_branch({"index.php": PAGE_OK}, ["index.php", "favicon.svg"],
                            "siftegoba-co-es")
    assert issues == [], issues


PAGE_META = """<!DOCTYPE html><html><head>
<meta name="theme-color" content="#4B535B">
<meta property="og:site_name" content="Siftegoba">
<title>Siftegoba · Taller</title>
</head><body>x</body></html>"""

PAGE_META_PLACEHOLDER = """<!DOCTYPE html><html><head>
<meta property="og:site_name" content="{{DOMAIN}}">
<title>{{DOMAIN}}</title>
</head><body>x</body></html>"""

PAGE_TAILWIND = """<!DOCTYPE html><html><head>
<script>tailwind.config={theme:{extend:{colors:{
  primary: { 50: '#f4f5f6', 600: '#4B535B', 900: '#1f2326' },
}}}}</script>
</head><body>x</body></html>"""


def test_letter_prefers_domain_over_markup():
    # _domain_for — окрема функція саме для того, щоб її можна було підмінити
    saved = fav._domain_for
    fav._domain_for = lambda branch: "silleteh.blog"
    try:
        letter = fav._brand_letter({"index.php": PAGE_META}, "siftegoba-co-es")
    finally:
        fav._domain_for = saved
    assert letter == "S", letter


def test_letter_strips_www_and_tld():
    saved = fav._domain_for
    fav._domain_for = lambda branch: "www.vueltia.blog"
    try:
        letter = fav._brand_letter({}, "vueltiao-co-es")
    finally:
        fav._domain_for = saved
    assert letter == "V", letter


def test_letter_falls_back_to_og_site_name():
    saved = fav._domain_for
    fav._domain_for = lambda branch: None
    try:
        letter = fav._brand_letter({"index.php": PAGE_META}, "br-pt")
    finally:
        fav._domain_for = saved
    assert letter == "S", letter


def test_letter_skips_placeholder_sources_and_uses_branch():
    saved = fav._domain_for
    fav._domain_for = lambda branch: None
    try:
        letter = fav._brand_letter({"index.php": PAGE_META_PLACEHOLDER},
                                   "yakogoz-co-es")
    finally:
        fav._domain_for = saved
    assert letter == "Y", letter


def test_letter_supports_non_latin():
    saved = fav._domain_for
    fav._domain_for = lambda branch: None
    try:
        cyr = fav._brand_letter(
            {"index.php": '<html><head><meta property="og:site_name" '
                          'content="Джерело"></head></html>'}, "br-pt")
        thai = fav._brand_letter(
            {"index.php": '<html><head><meta property="og:site_name" '
                          'content="ไทยดี"></head></html>'}, "br-pt")
    finally:
        fav._domain_for = saved
    assert cyr == "Д", cyr
    assert thai == "ไ", thai          # тайська не має регістру — лишається як є


def test_build_svg_with_non_latin_letter():
    svg = fav.build_svg("Д", "#4B535B", "#FFFFFF")
    assert ">Д</text>" in svg, svg


def test_color_from_theme_color():
    assert fav._brand_color({"index.php": PAGE_META}) == "#4B535B"


def test_color_from_tailwind_primary_600():
    assert fav._brand_color({"index.php": PAGE_TAILWIND}) == "#4B535B"


def test_color_default_when_nothing_found():
    assert fav._brand_color({"index.php": "<html><head></head></html>"}) == "#2E3338"


def test_text_color_contrast():
    assert fav._text_color("#111417") == "#FFFFFF"
    assert fav._text_color("#FFFFFF") == "#111417"


def test_build_svg_shape():
    svg = fav.build_svg("S", "#4B535B", "#FFFFFF")
    assert svg.startswith("<svg xmlns=") and svg.rstrip().endswith("</svg>"), svg
    assert 'fill="#4B535B"' in svg and ">S</text>" in svg, svg
    assert "system-ui" in svg, svg


def test_build_svg_escapes_letter():
    svg = fav.build_svg("&", "#000000", "#FFFFFF")
    assert "&amp;" in svg and ">&<" not in svg, svg


# --- раунд 1 рев'ю: зворотний порядок атрибутів у <meta> ---------------------

def test_letter_og_site_name_matches_reversed_attribute_order():
    saved = fav._domain_for
    fav._domain_for = lambda branch: None
    try:
        letter = fav._brand_letter(
            {"index.php": '<html><head><meta content="Siftegoba" '
                          'property="og:site_name"></head></html>'},
            "br-pt")
    finally:
        fav._domain_for = saved
    assert letter == "S", letter


def test_letter_application_name_matches_reversed_attribute_order():
    saved = fav._domain_for
    fav._domain_for = lambda branch: None
    try:
        letter = fav._brand_letter(
            {"index.php": '<html><head><meta content="Vueltia" '
                          'name="application-name"></head></html>'},
            "br-pt")
    finally:
        fav._domain_for = saved
    assert letter == "V", letter


def test_color_theme_color_matches_reversed_attribute_order():
    text = '<html><head><meta content="#4B535B" name="theme-color"></head></html>'
    assert fav._brand_color({"index.php": text}) == "#4B535B"


# --- раунд 1 рев'ю: build_svg не пише невалідні кольори в атрибут -----------

def test_build_svg_rejects_invalid_bg_color():
    svg = fav.build_svg("S", 'red" onload="alert(1)', "#fff")
    assert "onload" not in svg, svg
    assert f'fill="{fav.DEFAULT_COLOR}"' in svg, svg


def test_build_svg_rejects_invalid_fg_color():
    svg = fav.build_svg("S", "#4B535B", 'red" onload="alert(1)')
    assert "onload" not in svg, svg
    assert 'fill="#FFFFFF">S</text>' in svg, svg


# --- раунд 1 рев'ю: title "Сторінка | Бренд" — задокументована поведінка ----

def test_letter_title_page_pipe_brand_documents_current_behavior():
    # Свідомий вибір (див. коментар біля NAME_SPLIT_RX): title завжди дає
    # літеру ДО роздільника. Для конвенції "Сторінка | Бренд" це літера
    # сторінки, а не бренду — тут це "S" від "Servicios" (збігається з "S" від
    # "Siftegoba" суто випадково, тест фіксує саме факт "перша частина").
    saved = fav._domain_for
    fav._domain_for = lambda branch: None
    try:
        letter = fav._brand_letter(
            {"index.php": "<html><head><title>Servicios | Siftegoba</title>"
                          "</head></html>"},
            "br-pt")
    finally:
        fav._domain_for = saved
    assert letter == "S", letter


# --- раунд 1 рев'ю: _text_color — захисні гілки та ширше покриття -----------

def test_text_color_none_does_not_raise():
    assert fav._text_color(None) == "#FFFFFF"


def test_text_color_short_hex():
    assert fav._text_color("#fff") == "#111417"


def test_text_color_alpha_hex():
    assert fav._text_color("#4B535Bff") == "#FFFFFF"


def test_text_color_invalid_input():
    assert fav._text_color("not-a-color") == "#FFFFFF"


# --- Task 6: автофікс -------------------------------------------------------

def test_fix_replaces_first_placeholder_link():
    out = fav.link_actions({"index.php": PAGE_BROKEN}, ["index.php"], "siftegoba-co-es")
    edits = [a for a in out if a["type"] == "edit"]
    assert len(edits) == 1, out
    text = edits[0]["content"]
    assert text.count('href="./favicon.svg"') == 1, text
    assert "{{LOGO}}" not in text, text


def test_fix_removes_extra_broken_links():
    out = fav.link_actions({"index.php": PAGE_BROKEN}, ["index.php"], "siftegoba-co-es")
    text = [a for a in out if a["type"] == "edit"][0]["content"]
    assert text.count("<link") == 1, text        # було 3, лишається один робочий
    assert "apple-touch-icon" not in text, text


def test_fix_creates_favicon_file():
    out = fav.link_actions({"index.php": PAGE_BROKEN}, ["index.php"], "siftegoba-co-es")
    created = [a for a in out if a["type"] == "create"]
    assert len(created) == 1, out
    assert created[0]["path"] == "favicon.svg", created
    assert created[0]["content"].startswith("<svg xmlns="), created


def test_fix_does_not_recreate_existing_favicon():
    out = fav.link_actions({"index.php": PAGE_BROKEN},
                         ["index.php", "favicon.svg"], "siftegoba-co-es")
    assert not [a for a in out if a["type"] == "create"], out


def test_fix_leaves_healthy_page_alone():
    out = fav.link_actions({"index.php": PAGE_OK},
                         ["index.php", "favicon.svg"], "aboxox-co-es")
    assert out == [], out


def test_fix_repoints_link_to_missing_file():
    """Кейс 17-stxaqharc-lejov-adzojuhw-sg-en і ще 33 віток: усі сторінки
    лінкують favicon, якого у вітці немає. Чек лаявся, а автофікс мовчав —
    «неіснуючий файл лишаємо людині». Але коли робочої іконки немає ЗОВСІМ,
    мертвий лінк не цінність: ведемо його на згенеровану favicon.svg."""
    page = ('<!DOCTYPE html><html><head>'
            '<link rel="icon" href="./img/7b00fb4ae5.svg">'
            '</head><body>x</body></html>')
    out = fav.link_actions({"index.php": page}, ["index.php"], "any-co-es")
    text = [a for a in out if a["type"] == "edit"][0]["content"]
    assert 'href="./favicon.svg"' in text, text
    assert "7b00fb4ae5" not in text, text
    assert [a for a in out if a["type"] == "create"][0]["path"] == "favicon.svg"


def test_dead_link_only_removed_when_page_already_has_icon():
    """Робоча іконка вже є — мертвий лінк просто прибираємо, а не додаємо
    другу (згенеровану) іконку поверх справжньої."""
    page = ('<!DOCTYPE html><html><head>'
            '<link rel="icon" href="./real.svg">'
            '<link rel="icon" href="./gone.png">'
            '</head><body>x</body></html>')
    out = fav.link_actions({"index.php": page}, ["index.php", "real.svg"], "any-co-es")
    text = [a for a in out if a["type"] == "edit"][0]["content"]
    assert 'href="./real.svg"' in text, text
    assert "gone.png" not in text, text
    assert not [a for a in out if a["type"] == "create"], out


def test_case_mismatch_is_repointed_not_replaced():
    """Файл існує, помилка лише в регістрі — вирівнюємо шлях; справжня іконка
    вітки цінніша за намальовану літеру."""
    page = ('<!DOCTYPE html><html><head>'
            '<link rel="icon" href="./img/Favicon.PNG">'
            '</head><body>x</body></html>')
    out = fav.link_actions({"index.php": page}, ["index.php", "img/favicon.png"],
                         "any-co-es")
    text = [a for a in out if a["type"] == "edit"][0]["content"]
    assert 'href="./img/favicon.png"' in text, text
    assert not [a for a in out if a["type"] == "create"], out


def test_link_points_to_existing_root_favicon_not_generated_svg():
    """У вітці лежить favicon.ico — лінк має вести на НЬОГО. Раніше href
    писався на favicon.svg, якого немає, тобто фікс робив мертвий лінк."""
    page = ('<!DOCTYPE html><html><head>'
            '<link rel="icon" href="{{LOGO}}">'
            '</head><body>x</body></html>')
    out = fav.link_actions({"index.php": page}, ["index.php", "favicon.ico"],
                         "any-co-es")
    text = [a for a in out if a["type"] == "edit"][0]["content"]
    assert 'href="./favicon.ico"' in text, text
    assert 'type="image/x-icon"' in text, text
    assert not [a for a in out if a["type"] == "create"], out


def test_fix_inserts_link_when_page_has_none():
    page = "<!DOCTYPE html><html><head><title>x</title></head><body>y</body></html>"
    out = fav.link_actions({"index.php": page}, ["index.php"], "any-co-es")
    text = [a for a in out if a["type"] == "edit"][0]["content"]
    assert 'href="./favicon.svg"' in text, text


def test_fix_inserts_link_when_page_has_none_despite_existing_root_svg():
    """Реальний баг: favicon.svg уже лежить у корені (з попереднього
    автофіксу), а сторінка не має ЖОДНОГО <link rel=icon> — needs_link
    рахувався як `not root`, тож наявність будь-якого favicon.* (у т.ч.
    .svg) назавжди глушила вставку лінка, і браузер favicon.svg без <link>
    не підхоплює. needs_link має орієнтуватись саме на favicon.ico."""
    page = "<!DOCTYPE html><html><head><title>x</title></head><body>y</body></html>"
    out = fav.link_actions({"index.php": page}, ["index.php", "favicon.svg"], "any-co-es")
    edits = [a for a in out if a["type"] == "edit"]
    assert edits, out
    assert 'rel="icon"' in edits[0]["content"], edits[0]["content"]
    assert 'href="./favicon.svg"' in edits[0]["content"], edits[0]["content"]
    assert not [a for a in out if a["type"] == "create"], out


def test_fix_does_not_insert_link_when_root_favicon_ico_present():
    # favicon.ico — справжній implicit-кейс: лінк вставляти не треба.
    page = "<!DOCTYPE html><html><head><title>x</title></head><body>y</body></html>"
    out = fav.link_actions({"index.php": page}, ["index.php", "favicon.ico"], "any-co-es")
    assert not [a for a in out if a["type"] == "edit"], out


def test_fix_href_is_relative_to_page_in_subdir():
    """У кеші 64 вітки мають сторінки в підпапках. Абсолютний /favicon.svg
    для них мертвий, якщо вітка не в корені домену — тому href рахується
    відносно теки самої сторінки."""
    pages = {"index.php": PAGE_BROKEN, "sub/about.html": PAGE_BROKEN}
    out = fav.link_actions(pages, list(pages), "any-co-es")
    by_path = {a["path"]: a["content"] for a in out if a["type"] == "edit"}
    assert 'href="./favicon.svg"' in by_path["index.php"], by_path["index.php"]
    assert 'href="../favicon.svg"' in by_path["sub/about.html"], by_path["sub/about.html"]


def test_icon_href_depths():
    assert fav._icon_href("index.php") == "./favicon.svg"
    assert fav._icon_href("sub/about.html") == "../favicon.svg"
    assert fav._icon_href("a/b/c/page.html") == "../../../favicon.svg"


def test_fix_inserts_link_when_only_apple_touch_was_broken():
    page = ('<!DOCTYPE html><html><head>'
            '<link rel="apple-touch-icon" sizes="180x180" href="{{LOGO}}">'
            '</head><body>x</body></html>')
    out = fav.link_actions({"index.php": page}, ["index.php"], "any-co-es")
    text = [a for a in out if a["type"] == "edit"][0]["content"]
    assert 'rel="icon" type="image/svg+xml" href="./favicon.svg"' in text, text
    assert "apple-touch-icon" not in text, text


def test_fix_skips_partial_without_head():
    out = fav.link_actions({"footer.php": PAGE_NO_HEAD}, ["footer.php"], "any-co-es")
    assert not [a for a in out if a["type"] == "edit"], out


def test_verify_on_deploy_returns_empty_when_not_deployed():
    saved = fav._deploy_url
    fav._deploy_url = lambda branch: None
    try:
        assert fav._verify_on_deploy("nope-co-es", ["/favicon.svg"]) == ""
    finally:
        fav._deploy_url = saved


def test_verify_on_deploy_reports_status():
    saved_url, saved_probe = fav._deploy_url, fav._probe
    fav._deploy_url = lambda branch: "http://127.0.0.1:9100/"
    fav._probe = lambda url: (404, "text/html")
    try:
        msg = fav._verify_on_deploy("siftegoba-co-es", ["/favicon.svg"])
    finally:
        fav._deploy_url, fav._probe = saved_url, saved_probe
    assert "404" in msg, msg
    assert "деплої" in msg, msg


def test_clean_branch_never_touches_http():
    calls = []
    saved = fav._verify_on_deploy
    fav._verify_on_deploy = lambda branch, hrefs: calls.append(branch) or ""
    try:
        fav.run_branch({"index.php": PAGE_OK}, ["index.php", "favicon.svg"],
                       "aboxox-co-es")
    finally:
        fav._verify_on_deploy = saved
    assert calls == [], calls


# --- раунд 1 фікс: '>' усередині лапкованого атрибута обриває LINK_RX ------

PAGE_INLINE_SVG_FAVICON = """<!DOCTYPE html><html><head>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle r='40'/></svg>">
</head><body>Hi</body></html>"""


def test_inline_svg_data_uri_favicon_is_healthy():
    # inline-SVG прямо в href містить '>' усередині лапок — старий LINK_RX
    # ([^>]*) обривав тег на цьому символі, _attr(tag, "href") повертав
    # порожній рядок, _link_state давав "skip", і робоча іконка потрапляла в
    # no_icon_pages. У кеші такий патерн — на 2177 вітках.
    issues = fav.run_branch({"index.php": PAGE_INLINE_SVG_FAVICON}, ["index.php"])
    assert issues == [], issues


def test_attr_reads_full_tag_with_gt_inside_quotes():
    # Сам тег має зчитуватись ЦІЛКОМ (до закриваючого '>' тега, а не до
    # першого '>' усередині href) — інакше _attr не знайде закриваючу лапку.
    m = fav.LINK_RX.search(PAGE_INLINE_SVG_FAVICON)
    assert m is not None, "LINK_RX має знайти тег"
    tag = m.group(0)
    href = fav._attr(tag, "href")
    assert href is not None and href.endswith("</svg>"), href


# --- фавіконка зі стокового фотохоста ---------------------------------------

PAGE_STOCK_FAVICON = """<!DOCTYPE html><html><head>
<title>Betoeva</title>
<link rel="icon" href="https://picsum.photos/seed/betoeva-ico/32/32" type="image/png">
</head><body>Hi</body></html>"""


def test_stock_photo_host_is_broken():
    # Заміряно: 4456 віток кешу ведуть фавіконку на picsum.photos. Хост віддає
    # ВИПАДКОВЕ фото (а на замірі — 503/522), у браузері це
    # `EncodingError: source image cannot be decoded`, тобто іконки немає.
    state, msg = fav._link_state("index.php",
                                 "https://picsum.photos/seed/x/32/32",
                                 "image/png", set(), {})
    assert state == "broken", state
    assert "стокове фото" in msg, msg
    assert "picsum.photos" in msg, msg


def test_stock_host_matches_subdomain_and_protocol_relative():
    assert fav._stock_host("https://i.picsum.photos/id/1/32/32.jpg") == "picsum.photos"
    assert fav._stock_host("//picsum.photos/32/32") == "picsum.photos"
    assert fav._stock_host("https://images.unsplash.com/photo-1") == "unsplash.com"


def test_non_stock_external_host_stays_ok():
    # Звужувати правило до «будь-який зовнішній URL» не можна: у корпусі є
    # вітки з іконкою на власному сайті-джерелі (puc-cawkamev.edu.br,
    # static.wixstatic.com) — вона рендериться, ламати її нічим.
    assert fav._stock_host("https://www.puc-cawkamev.edu.br/favicon.ico") is None
    state, _ = fav._link_state("index.php",
                               "https://static.wixstatic.com/media/ico.png",
                               None, set(), {})
    assert state == "ok", state


def test_stock_favicon_reports_reason_in_aggregated_error():
    # Точкові повідомлення сторінок без робочої іконки в звіт не йдуть (їх
    # заміняє агрегована помилка), тому причина мусить бути в ній — інакше
    # у UI видно лише «браузер покаже порожню іконку» без діагнозу.
    issues = fav.run_branch({"index.php": PAGE_STOCK_FAVICON}, ["index.php"])
    assert len(issues) == 1, issues
    assert "стокове фото" in issues[0]["message"], issues[0]["message"]


def test_autofix_replaces_stock_favicon_and_generates_icon():
    files = {"index.php": PAGE_STOCK_FAVICON, "company.html": PAGE_STOCK_FAVICON}
    actions = fav.link_actions(files, list(files), "betoeva-br-pt")
    edits = {a["path"]: a["content"] for a in actions if a["type"] == "edit"}
    created = [a for a in actions if a["type"] == "create"]
    assert set(edits) == set(files), sorted(edits)
    assert all("picsum" not in c for c in edits.values()), edits
    assert all('href="./favicon.svg"' in c for c in edits.values()), edits
    assert [a["path"] for a in created] == ["favicon.svg"], created
    assert "<svg" in created[0]["content"], created[0]["content"]


def test_autofix_of_stock_favicon_is_idempotent():
    files = {"index.php": PAGE_STOCK_FAVICON}
    actions = fav.link_actions(files, list(files), "betoeva-br-pt")
    fixed = {a["path"]: a["content"] for a in actions if a["type"] == "edit"}
    paths = sorted(set(files) | {"favicon.svg"})
    assert fav.run_branch(fixed, paths, "") == [], fav.run_branch(fixed, paths, "")
    assert fav.link_actions(fixed, paths, "") == [], fav.link_actions(fixed, paths, "")


def test_autofix_drops_stock_link_when_real_icon_exists():
    # Якщо поряд зі стоковим лінком є робоча іконка — стоковий прибираємо,
    # а другу іконку поверх справжньої не додаємо.
    page = ("""<!DOCTYPE html><html><head>
<link rel="icon" href="https://picsum.photos/seed/x/32/32" type="image/png">
<link rel="icon" type="image/svg+xml" href="./favicon.svg">
</head><body>Hi</body></html>""")
    actions = fav.link_actions({"index.php": page}, ["index.php", "favicon.svg"], "")
    edits = [a for a in actions if a["type"] == "edit"]
    assert len(edits) == 1, actions
    new = edits[0]["content"]
    assert "picsum" not in new, new
    assert new.count('href="./favicon.svg"') == 1, new
    assert not [a for a in actions if a["type"] == "create"], actions


def test_template_root_favicon_is_flagged_as_warn():
    # фон + одна літера (старий build_svg) — шаблонний знак: warn з
    # відсилкою у Медіа → Лого/Favicon
    import runner
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix="fav-"))
    (d / "favicon.svg").write_text(
        fav.build_svg("P", "#1a1a1a", "#FFFFFF"), encoding="utf-8")
    old = runner.snapshot_dir
    runner.snapshot_dir = lambda b: d
    try:
        issues = fav.run_branch({"index.php": PAGE_OK},
                                ["index.php", "favicon.svg"], "any-co-es")
    finally:
        runner.snapshot_dir = old
    assert len(issues) == 1 and issues[0]["severity"] == "warn", issues
    assert "шаблонний" in issues[0]["message"], issues


# ------------------------------------------------ force-лінки Apply (01.10)
def test_force_rewrites_any_icon_link_with_version():
    # кейс alnewvad/quuskafs: лінк ./favicon.svg є, файла немає, вкладка
    # тримає кеш — force переписує href на версіонований БЕЗУМОВНО
    page = ('<html><head><title>x</title>\n'
            '<link rel="icon" type="image/svg+xml" href="./favicon.svg">\n'
            '<link rel="shortcut icon" href="data:image/png;base64,AAAA">\n'
            '<link rel="apple-touch-icon" href="./apple.png">\n'
            '</head><body><h1>x</h1></body></html>')
    acts = fav.link_actions({"index.php": page}, ["index.php"], "br",
                            force=True, version="deadbeef")
    assert len(acts) == 1 and acts[0]["type"] == "edit"
    out = acts[0]["content"]
    assert out.count('rel="icon"') == 1                      # дедуп до одного
    assert './favicon.svg?v=deadbeef' in out
    assert "data:image/png" not in out                       # data: знесено
    assert 'rel="apple-touch-icon"' in out                   # apple не чіпаємо


def test_force_inserts_link_when_head_has_none():
    page = "<html><head><title>x</title></head><body><h1>x</h1></body></html>"
    acts = fav.link_actions({"index.php": page}, ["index.php"], "br",
                            force=True, version="0ff")
    assert len(acts) == 1
    assert '<link rel="icon" type="image/svg+xml" href="./favicon.svg?v=0ff">' \
        in acts[0]["content"]

def test_autofix_is_link_actions_without_force():
    """21.10: QA «нет иконки сайта» на tsapgituequsja/rezmeufiriafkupul — фікс
    той самий, що ручний Apply; вибір знака людиною (force) лишається сильнішим."""
    assert fav.GROUP == "auto" and callable(fav.fix_branch)
    page = "<html><head><title>Cagu Vemme</title></head><body></body></html>"
    acts = {a["path"]: a for a in fav.fix_branch({"index.php": page}, ["index.php"], "cagu-vemme-br-pt")}
    assert fav.FAVICON_PATH in acts and acts[fav.FAVICON_PATH]["type"] == "create"
    assert "<svg" in acts[fav.FAVICON_PATH]["content"]
    assert 'rel="icon"' in acts["index.php"]["content"] and "favicon.svg" in acts["index.php"]["content"]
    fixed = {"index.php": acts["index.php"]["content"], fav.FAVICON_PATH: acts[fav.FAVICON_PATH]["content"]}
    assert fav.run_branch(dict(fixed), list(fixed), "cagu-vemme-br-pt") == []
    assert fav.fix_branch(dict(fixed), list(fixed), "cagu-vemme-br-pt") == []


if __name__ == "__main__":
    run(dict(globals()))
