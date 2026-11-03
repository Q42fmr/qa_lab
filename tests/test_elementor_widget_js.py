"""Тести elementor_widget_js: popup-тригер і nested-tabs без webpack-чанка.

Скрейпер не зберігає lazy-чанки Elementor (`popup.*.bundle.min.js`,
`nested-tabs.*.bundle.min.js`), тож клік по popup-тригеру і по табі нічого не
робить. Фікс позначає елементи власними data-атрибутами (не чіпаючи класи
білдера) і додає один незалежний шим; заразом прибирає чужий неробочий
`mouseenter`->`click` костиль nested-tabs.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import load_check, run  # noqa: E402

ew = load_check("elementor_widget_js")

POPUP_SETTINGS = "eyJpZCI6IjIzNTciLCJ0b2dnbGUiOmZhbHNlfQ%3D%3D"  # {"id":"2357","toggle":false}
POPUP_TRIGGER = (
    '<a class="elementor-icon" '
    'href="#elementor-action%3Aaction%3Dpopup%3Aopen%26settings%3D' + POPUP_SETTINGS + '">'
    '<svg></svg></a>'
)
POPUP_PANEL = (
    '<div data-elementor-type="popup" data-elementor-id="2357" '
    'class="elementor elementor-2357 elementor-location-popup">'
    '<p>popup content</p></div>'
)

TABS_WIDGET = (
    '<div class="elementor-widget elementor-widget-n-tabs" data-widget_type="nested-tabs.default">'
    '<div class="e-n-tabs" data-widget-number="1">'
    '<div class="e-n-tabs-heading" role="tablist">'
    '<button class="e-n-tab-title" aria-selected="true" aria-controls="e-n-tab-content-1" role="tab">A</button>'
    '<button class="e-n-tab-title" aria-selected="false" aria-controls="e-n-tab-content-2" role="tab">B</button>'
    '</div>'
    '<div class="e-n-tabs-content">'
    '<div id="e-n-tab-content-1" class="e-active elementor-element e-con">panel A</div>'
    '<div id="e-n-tab-content-2" class="elementor-element e-con">panel B</div>'
    '</div>'
    '</div>'
    '</div>'
)

BROKEN_SHIM = (
    '<script>\n'
    "jQuery(function($){\n"
    "  $(document).on('mouseenter', '.e-n-tab-title', function(){\n"
    "    this.dispatchEvent(new MouseEvent('click', { bubbles: true }));\n"
    "  });\n"
    "});\n"
    '</script>\n'
)


def _page(*parts):
    return "<html><body>" + "".join(parts) + "</body></html>"


def test_popup_trigger_with_panel_is_reported():
    page = _page(POPUP_TRIGGER, POPUP_PANEL)
    iss = ew.run("index.html", page)
    assert len(iss) == 1, iss
    assert iss[0]["severity"] == "error"
    assert "2357" in iss[0]["message"]


def test_popup_trigger_without_panel_is_not_reported():
    """Розмітки попапа немає на сторінці - показувати нічого, тож не чіпаємо."""
    page = _page(POPUP_TRIGGER)
    assert ew.run("index.html", page) == []
    assert ew.fix("index.html", page) == page


def test_plain_hash_link_is_not_reported():
    page = _page('<a class="elementor-icon" href="#">x</a>', POPUP_PANEL)
    assert ew.run("index.html", page) == []


def test_page_without_elementor_is_not_reported():
    page = "<html><body><p>Hello</p><a href='/contact.html'>Contact</a></body></html>"
    assert ew.run("index.html", page) == []
    assert ew.fix("index.html", page) == page


def test_nested_tabs_widget_is_reported():
    page = _page(TABS_WIDGET)
    iss = ew.run("index.html", page)
    assert len(iss) == 1, iss
    assert "e-n-tabs" in iss[0]["message"] or "nested-tabs" in iss[0]["message"]


def test_both_widgets_on_one_page_yield_two_findings():
    page = _page(POPUP_TRIGGER, POPUP_PANEL, TABS_WIDGET)
    iss = ew.run("index.html", page)
    assert len(iss) == 2, iss


def test_fix_marks_trigger_and_panel_without_losing_attributes():
    page = _page(POPUP_TRIGGER, POPUP_PANEL)
    out = ew.fix("index.html", page)
    assert 'data-wp-elpopup="2357"' in out
    assert 'data-wp-elpopup="panel-2357"' in out
    # розмітка білдера лишається недоторканою
    assert 'class="elementor-icon"' in out
    assert 'data-elementor-id="2357"' in out
    assert 'elementor-location-popup' in out
    assert '<svg></svg>' in out
    assert '<p>popup content</p>' in out


def test_fix_marks_tabs_container_without_losing_attributes():
    page = _page(TABS_WIDGET)
    out = ew.fix("index.html", page)
    assert 'data-wp-eltabs="1"' in out
    for kept in ('e-n-tabs-heading', 'aria-controls="e-n-tab-content-1"',
                 'e-n-tab-title', 'e-n-tabs-content', 'e-active'):
        assert kept in out, kept


def test_fix_removes_broken_mouseenter_shim():
    page = _page(TABS_WIDGET, BROKEN_SHIM)
    out = ew.fix("index.html", page)
    assert "mouseenter" not in out
    assert "dispatchEvent" not in out
    # своя таб-розмітка лишається
    assert 'data-wp-eltabs="1"' in out


def test_fix_adds_single_script_before_body_close():
    page = _page(POPUP_TRIGGER, POPUP_PANEL, TABS_WIDGET)
    out = ew.fix("index.html", page)
    assert out.count('data-qa_lab="' + ew.MARKER + '"') == 1
    assert out.index(ew.MARKER) < out.index("</body>")
    assert "jQuery" not in out and "$(" not in out


def test_fix_appends_script_when_body_close_is_missing():
    page = POPUP_TRIGGER + POPUP_PANEL  # без <html>/<body>
    out = ew.fix("index.html", page)
    assert ew.MARKER in out
    assert out.startswith(POPUP_TRIGGER) or 'data-wp-elpopup' in out


def test_fix_is_idempotent():
    page = _page(POPUP_TRIGGER, POPUP_PANEL, TABS_WIDGET, BROKEN_SHIM)
    once = ew.fix("index.html", page)
    twice = ew.fix("index.html", once)
    assert once == twice
    assert ew.run("index.html", once) == []


def test_clean_page_fix_is_noop():
    page = "<html><body><p>ok</p></body></html>"
    assert ew.fix("index.html", page) == page


def test_shim_does_not_use_jquery():
    assert "jQuery" not in ew.SCRIPT
    assert "$(" not in ew.SCRIPT


def test_shim_builds_the_modal_wrapper_the_branch_css_expects():
    """Показати попап `display:block` на самій розмітці НЕ можна: панель лежить у
    звичайному потоці, і на деплої `pibmftanum.ch` вона зʼявлялась на
    absoluteTop 6822 при вікні 900 - тобто за екраном. Власна css вітки
    (`conditionals/popup.min.css`) описує обгортку, і шим мусить будувати саме
    її, інакше `#elementor-popup-modal-<id>` з `post-2357.css` (скрим,
    вирівнювання, розмір шухляди) не застосується ні до чого."""
    for token in ('elementor-popup-modal-" + id', "elementor-popup-modal",
                  "dialog-widget-content", "dialog-message"):
        assert token in ew.SCRIPT, token


def test_shim_supplies_only_the_missing_geometry():
    """Геометрію overlay давала dialog-бібліотека, якої у скрейпі немає зовсім.
    Її шим підставляє сам - але СКРИМ, ВИРІВНЮВАННЯ Й РОЗМІРИ лишає вітці, бо
    вони в неї вже є. Вигадані кольори тут були б регресією вигляду."""
    assert "position:fixed" in ew.SCRIPT
    assert "z-index:9999" in ew.SCRIPT
    for invented in ("background-color:", "background:", "justify-content:",
                     "width:25vw", "height:100vh"):
        assert invented not in ew.SCRIPT, invented


def test_shim_opens_as_flex_because_that_is_what_the_css_needs():
    """`.elementor-popup-modal.dialog-type-lightbox{display:flex}` - модалка
    мусить відкриватись саме flex-ом, інакше вирівнювання шухляди праворуч
    (`justify-content:flex-end`) не працює."""
    assert 'var OPEN = "flex"' in ew.SCRIPT
    assert 'display:none' in ew.SCRIPT      # закрита за замовчуванням


def test_shim_closes_on_escape_and_on_scrim_click():
    assert "Escape" in ew.SCRIPT
    assert "shutAll" in ew.SCRIPT
    assert 'contains("elementor-popup-modal")' in ew.SCRIPT


if __name__ == "__main__":
    run(dict(globals()))
