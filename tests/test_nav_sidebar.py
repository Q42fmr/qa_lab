"""Тести nav_sidebar: десктопне меню-сайдбар стає горизонтальною смугою вгорі."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("nav_sidebar")

SIDEBAR = (
    '<template><div>'
    '<aside class="hidden lg:flex fixed left-0 top-0 h-full w-auto min-w-20 '
    'bg-orange-50 border-r border-neutral-200 flex-col items-center py-8 px-3 z-40">'
    '<a href="/" class="w-12 h-12 rounded-md flex items-center justify-center mb-8">'
    '<img src="/logo.svg" alt="X"><span>Impulson</span></a>'
    '<nav class="flex-1 flex flex-col items-center gap-6 overflow-y-auto">'
    '<a href="/x" class="px-3 py-2">Início</a></nav>'
    '<a href="/#form" class="w-10 h-10 rounded-full">+</a>'
    '</aside>'
    '</div></template>')

# мобільна шухляда: теж <aside class="fixed">, але lg:hidden + translate-x
DRAWER = (
    '<template><aside :class="[\'fixed top-0 right-0 h-full w-72 z-50 transform '
    'transition-transform duration-300 lg:hidden\', menuOpen ? \'translate-x-0\' '
    ': \'translate-x-full\']"><nav class="flex-1 px-6 flex flex-col">'
    '<a href="/x">Início</a></nav></aside></template>')

# смуга, яку вже перевели у горизонтальну: сайдбара немає, а бокс лого
# лишився квадратом під одну іконку - напис бренду з нього вилазить
TOPBAR = (
    '<template><div>'
    '<aside class="hidden lg:flex bg-orange-50 border-b border-neutral-200 '
    'flex-row items-center py-4 px-4 w-full gap-6 justify-between md:px-8">'
    '<a href="/" class="w-12 h-12 rounded-md flex items-center justify-center">'
    '<img src="/logo.svg" alt="Impulson" class="w-10 h-10 object-cover">'
    '<span class="font-semibold text-lg">Impulson</span></a>'
    '<nav class="flex-1 flex flex-row items-center gap-6">'
    '<a href="/x" class="px-3 py-2">Início</a></nav>'
    '</aside></div></template>')

PATH = "src/components/HeaderNav.vue"


def _run(files):
    return mod.run_branch(dict(files), list(files))


def _fix(files):
    return {a["path"]: a["content"]
            for a in mod.fix_branch(dict(files), list(files), "nwf-x-br-pt")}


def _aside_class(html):
    import re
    return re.search(r'<aside[^>]*class="([^"]*)"', html).group(1).split()


# --------------------------------------------------------------- детект
def test_desktop_sidebar_is_flagged():
    """Кейс nwf-imsopla-nenekeoc-br-pt: `fixed left-0 h-full` без жодного
    `lg:pl-*` у вітці — смуга лежить поверх контенту й обрізає заголовок."""
    issues = _run({PATH: SIDEBAR})
    assert len(issues) == 1 and issues[0]["severity"] == "error", issues
    assert issues[0]["path"] == PATH, issues


def test_mobile_drawer_is_not_touched():
    """Шухляда теж `<aside class="fixed">`, але з `lg:hidden` і `translate-x`:
    у корпусі таких 18 і вони робочі."""
    assert _run({PATH: DRAWER}) == []
    assert _fix({PATH: DRAWER}) == {}


def _sidebar_issues(files):
    return [i for i in _run(files) if "сайдбар" in i["message"]]


def test_horizontal_aside_is_not_a_sidebar():
    """Без `flex-col` це вже не сайдбар. (Тісний бокс лого - окрема поломка,
    і вона тут лишається, тож дивимось саме на правило сайдбара.)"""
    html = SIDEBAR.replace("flex-col", "flex-row")
    assert _sidebar_issues({PATH: html}) == []
    assert "flex-row" in _aside_class(_fix({PATH: html})[PATH])


def test_aside_without_fixed_is_not_a_sidebar():
    html = SIDEBAR.replace("fixed ", "")
    assert _sidebar_issues({PATH: html}) == []
    assert "h-full" in _aside_class(_fix({PATH: html})[PATH])


def test_static_class_drawer_is_not_touched():
    """Шухляди в корпусі мають КЛАС-ПРИВʼЯЗКУ (`:class="[…]"`), і регекс її
    не парсить — тобто вони в безпеці випадково. Але шухляду можна написати
    і статичним класом (тогл через `v-if`), і тоді від сайдбара її відрізняє
    ЛИШЕ `lg:hidden`: та сама `fixed`, `h-full`, `flex flex-col`."""
    html = ('<template><aside v-if="menuOpen" class="fixed top-0 right-0 h-full '
            'w-72 z-50 bg-white lg:hidden flex flex-col items-center py-8 px-3">'
            '<nav class="flex-1 flex flex-col gap-6"><a href="/x">Início</a></nav>'
            '</aside></template>')
    assert _run({PATH: html}) == []
    assert _fix({PATH: html}) == {}


def test_floating_side_widget_is_not_a_sidebar():
    """`fixed` + `flex-col` буває і в плавучого віджета збоку (кнопки шерингу,
    чат). Сайдбар-меню тримається КРАЮ на всю висоту — `left-0` або `h-full`;
    без цього перетворювати елемент у смугу на всю ширину означало б
    зламати чужий блок."""
    html = ('<template><aside class="fixed right-4 bottom-4 flex flex-col gap-2 '
            'bg-white rounded-md p-2 z-50"><a href="/x">Chat</a></aside></template>')
    assert _run({PATH: html}) == []
    assert _fix({PATH: html}) == {}


# ----------------------------------------------------------------- фікс
def test_fix_makes_it_a_row_in_normal_flow():
    """Головне: смуга виходить з `fixed` у потік — тоді перекриття зникає за
    побудовою, і компенсувати зсув не треба (заміряно в браузері: hero
    починається з y=81 замість y=0)."""
    cls = _aside_class(_fix({PATH: SIDEBAR})[PATH])
    for gone in ("fixed", "left-0", "top-0", "h-full", "w-auto", "min-w-20", "z-40"):
        assert gone not in cls, (gone, cls)
    assert "flex-row" in cls and "flex-col" not in cls, cls
    assert "w-full" in cls, cls


def test_fix_keeps_colours_and_visibility():
    """Кольори й адаптивність — не наша справа: лишаються як були."""
    cls = _aside_class(_fix({PATH: SIDEBAR})[PATH])
    for keep in ("hidden", "lg:flex", "bg-orange-50", "border-neutral-200",
                 "items-center"):
        assert keep in cls, (keep, cls)


def test_fix_turns_the_side_border_into_a_bottom_one():
    cls = _aside_class(_fix({PATH: SIDEBAR})[PATH])
    assert "border-b" in cls and "border-r" not in cls, cls


def test_fix_matches_the_house_padding():
    """У 141 вітки звичайний `<header>` це `py-4 px-4 md:px-8`."""
    cls = _aside_class(_fix({PATH: SIDEBAR})[PATH])
    assert "py-4" in cls and "py-8" not in cls, cls
    assert "px-4" in cls and "md:px-8" in cls, cls


def test_fix_makes_the_inner_nav_horizontal():
    out = _fix({PATH: SIDEBAR})[PATH]
    import re
    nav = re.search(r'<nav[^>]*class="([^"]*)"', out).group(1)
    assert "flex-row" in nav and "flex-col" not in nav, nav
    assert "overflow-y-auto" not in nav, nav


def test_fix_drops_the_vertical_gap_under_the_logo():
    """`mb-8` мав сенс лише у стовпчику; у рядку він зсуває лого вгору."""
    out = _fix({PATH: SIDEBAR})[PATH]
    assert "mb-8" not in out, out


def test_fix_keeps_links_and_markup_intact():
    out = _fix({PATH: SIDEBAR})[PATH]
    for keep in ('href="/"', 'href="/x"', 'href="/#form"', "<img", "Impulson",
                 "Início"):
        assert keep in out, (keep, out)
    assert out.count("<aside") == 1 and out.count("</aside>") == 1, out


def test_fix_is_idempotent():
    once = _fix({PATH: SIDEBAR})
    assert mod.fix_branch(dict(once), list(once), "nwf-x-br-pt") == []
    assert _run(once) == []


# ------------------------------------------------- тісний бокс лого у смузі
def _logo_class(html):
    import re
    return re.search(r'<a href="/" class="([^"]*)"', html).group(1).split()


def test_square_logo_box_with_a_label_is_flagged():
    """Кейс nwf-viopa-anp-sogaan-br-pt після переводу смуги вгору: заміряно в
    браузері - коробка лого 48px, напис 85px, тобто вилазить на 38px і лізе на
    перший пункт меню (зазор -14px), хоч `gap-6` між коробками дотриманий."""
    issues = _run({PATH: TOPBAR})
    assert len(issues) == 1, issues
    assert "напис бренду" in issues[0]["message"], issues


def test_fix_lets_the_logo_size_to_its_content():
    """Головне: фіксований бік зникає - і зазор стає справжнім (заміряно:
    -14px -> +24px, вилітання 38px -> 0)."""
    cls = _logo_class(_fix({PATH: TOPBAR})[PATH])
    assert "w-12" not in cls and "h-12" not in cls, cls
    assert "gap-2" in cls and "shrink-0" in cls, cls


def test_fix_keeps_the_icon_its_own_size():
    """Знімаємо розмір з АНКЕРА, а не з картинки: іконка лишається 40px."""
    out = _fix({PATH: TOPBAR})[PATH]
    assert 'class="w-10 h-10 object-cover"' in out, out


def test_fix_keeps_an_existing_gap():
    html = TOPBAR.replace('class="w-12 h-12 rounded-md',
                          'class="w-12 h-12 gap-3 rounded-md')
    cls = _logo_class(_fix({PATH: html})[PATH])
    assert "gap-3" in cls and "gap-2" not in cls, cls


def test_icon_only_square_logo_is_not_touched():
    """Квадрат під саму іконку - доречний, там нічого не вилазить."""
    html = TOPBAR.replace(
        '<span class="font-semibold text-lg">Impulson</span>', "")
    assert _run({PATH: html}) == []
    assert _fix({PATH: html}) == {}


def test_monogram_badge_is_not_touched():
    """Квадрат з літерою і БЕЗ іконки - бейдж-монограма: там нічого не тисне.
    Саме відсутність іконки її й відсіює, а не довжина напису: іконка займає
    квадрат майже цілком (40 з 48px), тож вилазить навіть одна літера поруч."""
    html = TOPBAR.replace(
        '<img src="/logo.svg" alt="Impulson" class="w-10 h-10 object-cover">'
        '<span class="font-semibold text-lg">Impulson</span>',
        '<span class="font-semibold text-lg">I</span>')
    assert _run({PATH: html}) == []
    assert _fix({PATH: html}) == {}


def test_single_letter_next_to_an_icon_still_overflows():
    """Іконка 40px плюс будь-що поруч у 48px не влазить - тож поріг «напис
    щонайменше дві літери» був би хибним."""
    html = TOPBAR.replace(">Impulson</span>", ">I</span>")
    assert len(_run({PATH: html})) == 1, _run({PATH: html})


def test_icon_button_with_a_glyph_is_not_a_logo():
    """Ознака напису - саме ЛІТЕРА, а не «щось непорожнє». Кругла кнопка-іконка
    з глифом (`+`, лічильник) - теж квадрат з іконкою, але бренду в ній немає, а
    зняти їй `w-10 h-10 rounded-full` означало б зламати кнопку. У корпусі
    такого сьогодні нуль (0 з 52 квадратних анкерів з іконкою), тож тримаємо
    ознаку тестом, а не спостереженням."""
    html = TOPBAR.replace(
        '<img src="/logo.svg" alt="Impulson" class="w-10 h-10 object-cover">'
        '<span class="font-semibold text-lg">Impulson</span>',
        '<svg viewBox="0 0 24 24"><path d="M12 5v14"/></svg><span>+</span>')
    assert _run({PATH: html}) == []
    assert _fix({PATH: html}) == {}


def test_rectangular_logo_box_is_not_touched():
    """`w-48 h-12` напис умістить - правило стосується саме КВАДРАТА."""
    html = TOPBAR.replace('class="w-12 h-12 rounded-md',
                          'class="w-48 h-12 rounded-md')
    assert _run({PATH: html}) == []
    assert _fix({PATH: html}) == {}


def test_header_element_is_scanned_too():
    """Смуга буває і `<header>`, не лише `<aside>`."""
    html = TOPBAR.replace("<aside", "<header").replace("</aside>", "</header>")
    assert len(_run({PATH: html})) == 1, _run({PATH: html})
    assert "w-12" not in _fix({PATH: html})[PATH], _fix({PATH: html})[PATH]


def test_mobile_bar_logo_is_not_touched():
    """У мобільній шапці (`lg:hidden`) меню сховане - лізти нема на що."""
    html = TOPBAR.replace("hidden lg:flex", "flex lg:hidden")
    assert _run({PATH: html}) == []


def test_sidebar_conversion_also_frees_the_logo():
    """Обидві поломки лагодяться ОДНИМ проходом: у сайдбарі той самий квадрат,
    і після переводу смуги вгору напис не має лізти на меню."""
    out = _fix({PATH: SIDEBAR})[PATH]
    cls = _logo_class(out)
    assert "w-12" not in cls and "h-12" not in cls, cls
    assert "gap-2" in cls and "shrink-0" in cls, cls
    assert _run({PATH: out}) == []


def test_check_is_node_auto():
    assert mod.PROJECTS == ["node"], mod.PROJECTS
    assert mod.GROUP == "auto"


if __name__ == "__main__":
    run(dict(globals()))
