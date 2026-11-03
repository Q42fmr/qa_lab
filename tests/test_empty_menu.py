"""Пусте десктоп-меню (кейс tagdocaa): чек check_empty_menu + фікс fix_empty_menu.

Два фікси з практики:
1) прибрати id (типово id="mobile-menu"), який базовий CSS ховає display:none;
2) md:hidden → hidden md:flex на єдиному nav-і хедера.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                              # noqa: E402

sys.path.insert(0, str(ROOT))
import menu_rules as lw                                     # noqa: E402


# --- як tagdocaa-mx-es: один nav на обидва меню, схований id-правилом ---
TAGDOCAA = """<html><head><style>
    #mobile-menu { display: none; }
    #mobile-menu.open { display: block; }
    @media (min-width: 768px) { #burger-btn { display: none; } }
</style></head><body>
<header class="bg-bgmist sticky top-0 z-50">
  <a href="./" class="flex items-center">Tagdocaa</a>
  <nav id="mobile-menu" class="flex-col md:flex-row items-start" aria-label="Menu">
    <a href="./company.html">Empresa</a>
  </nav>
  <div class="flex items-center gap-3 md:hidden">
    <button id="burger-btn" class="text-primary">=</button>
  </div>
</header></body></html>"""

# --- варіант 2: єдиний nav схований класом md:hidden ---
MD_HIDDEN = """<html><body>
<header>
  <span>Brand</span>
  <nav id="mobile-menu" class="md:hidden flex-col" aria-label="Menu">
    <a href="./a.html">A</a>
  </nav>
</header></body></html>"""

# --- здоровий вайт: mobile-панель схована, але є десктопний nav ---
HEALTHY = """<html><head><style>#mobile-menu { display: none; }</style></head><body>
<header>
  <nav class="hidden md:flex"><a href="./a.html">A</a></nav>
  <nav id="mobile-menu" class="flex-col"><a href="./a.html">A</a></nav>
</header></body></html>"""


def test_check_flags_css_hidden_id():
    assert lw.check_empty_menu(TAGDOCAA) == ["no desktop-visible nav in <header>"]


def test_fix_removes_blocking_id():
    out, counts = lw.fix_empty_menu(TAGDOCAA)
    assert 'id="mobile-menu"' not in out.split("</style>")[1]   # CSS не чіпаємо
    assert '<nav class="flex-col md:flex-row items-start" aria-label="Menu">' in out
    assert counts == {"Empty menu: remove hidden id": 1}
    assert lw.check_empty_menu(out) == []


def test_check_flags_md_hidden_only_nav():
    assert lw.check_empty_menu(MD_HIDDEN)


def test_fix_swaps_md_hidden_for_hidden_md_flex():
    out, counts = lw.fix_empty_menu(MD_HIDDEN)
    assert 'class="hidden md:flex flex-col"' in out
    # id тут CSS не ховає — його лишаємо (може юзатись JS-тоглом)
    assert 'id="mobile-menu"' in out
    assert counts.get("Empty menu: md:hidden → hidden md:flex") == 1
    assert lw.check_empty_menu(out) == []


def test_healthy_header_untouched():
    assert lw.check_empty_menu(HEALTHY) == []
    out, counts = lw.fix_empty_menu(HEALTHY)
    assert out == HEALTHY and counts == {}


def test_hidden_wrapper_around_nav_is_fixed():
    # патерн builder-хедера: nav у схованій панелі <div id="mobile-menu" md:hidden>
    html = """<style>#mobile-menu{display:none}</style>
<header>
  <div id="mobile-menu" class="border-t md:hidden">
    <nav><a href="./a.html">A</a></nav>
  </div>
</header>"""
    assert lw.check_empty_menu(html)
    out, counts = lw.fix_empty_menu(html)
    assert counts == {"Empty menu: remove hidden id": 1,
                      "Empty menu: md:hidden → hidden md:flex": 1}
    assert '<div class="border-t hidden md:flex">' in out
    assert lw.check_empty_menu(out) == []


def test_bare_hidden_class_gets_md_flex():
    html = '<header><nav class="hidden"><a href="./a.html">A</a></nav></header>'
    out, counts = lw.fix_empty_menu(html)
    assert 'class="hidden md:flex"' in out
    assert counts.get("Empty menu: md:hidden → hidden md:flex") == 1


def test_max_width_media_hide_is_not_desktop_hide():
    html = """<style>@media (max-width: 767px) { #mobile-menu { display: none; } }</style>
<header><nav id="mobile-menu"><a href="./a.html">A</a></nav></header>"""
    assert lw.check_empty_menu(html) == []
    out, counts = lw.fix_empty_menu(html)
    assert out == html and counts == {}


def test_hidden_lg_flex_is_desktop_visible():
    # фолс з кешу (arlovjo-br-pt): десктоп-nav показується на lg, не на md
    html = ('<header><nav class="hidden lg:flex items-center">'
            '<a href="./a.html">A</a></nav></header>')
    assert lw.check_empty_menu(html) == []
    out, counts = lw.fix_empty_menu(html)
    assert out == html and counts == {}


def test_lg_hidden_only_nav_is_flagged_and_fixed():
    html = ('<header><nav class="flex lg:hidden">'
            '<a href="./a.html">A</a></nav></header>')
    assert lw.check_empty_menu(html)
    out, counts = lw.fix_empty_menu(html)
    assert 'class="flex hidden md:flex"' in out
    assert lw.check_empty_menu(out) == []


def test_min_width_reshow_of_hidden_id_is_not_desktop_hide():
    # фолс з кешу (matu-lebse-br-pt): mobile-first ховає id, @media повертає
    html = """<style>
    #desktop-nav { display: none; }
    @media (min-width: 768px) { #desktop-nav { display: flex !important; } }
</style>
<header><nav id="desktop-nav" class="items-center"><a href="./a.html">A</a></nav></header>"""
    assert lw.check_empty_menu(html) == []
    out, counts = lw.fix_empty_menu(html)
    assert out == html and counts == {}


def test_important_class_reshow_is_not_desktop_hide():
    # фолс з кешу (bazito-ae-ar): tailwind hidden + `.desktop-nav{display:flex
    # !important}` у min-width @media — !important б'є .hidden, nav видимий
    html = """<style>
    @media (min-width: 768px) { .desktop-nav { display: flex !important; } }
</style>
<header><nav class="desktop-nav hidden items-center"><a href="./a.html">A</a></nav></header>"""
    assert lw.check_empty_menu(html) == []
    out, counts = lw.fix_empty_menu(html)
    assert out == html and counts == {}

def test_inline_display_style_beats_classes_and_id():
    # фолси з кешу: levuqira (style + md:hidden), muvohui (style + hidden id)
    html1 = ('<header><nav style="display:flex; gap:28px;" class="md:hidden">'
             '<a href="./a.html">A</a></nav></header>')
    assert lw.check_empty_menu(html1) == []
    html2 = """<style>#mobile-menu { display: none; }</style>
<header><nav id="mobile-menu" style="display: flex; gap: 32px;">
<a href="./a.html">A</a></nav></header>"""
    assert lw.check_empty_menu(html2) == []
    html3 = ('<header><nav style="display:none">'
             '<a href="./a.html">A</a></nav></header>')
    assert lw.check_empty_menu(html3)

def test_inline_none_reshown_by_important_media_or_width_js():
    # heoxbaug-atgab: inline display:none, але !important-@media показує id
    html1 = """<style>
    @media (min-width: 769px) { #desktop-nav { display: block !important; } }
</style>
<header><nav id="desktop-nav" style="display:none;"><a href="./a.html">A</a></nav></header>"""
    assert lw.check_empty_menu(html1) == []
    # muvohui: inline display:none + width-driven JS
    html2 = """<header><nav id="desktop-nav" style="display: none; gap: 32px;">
<a href="./a.html">A</a></nav></header>
<script>
  const nav = document.getElementById('desktop-nav');
  if (window.innerWidth >= 768) { nav.style.display = 'flex'; }
</script>"""
    assert lw.check_empty_menu(html2) == []
    # клік-тогл без innerWidth id не рятує: inline none лишається схованим
    html3 = """<header><nav id="mobile-menu" style="display:none">
<a href="./a.html">A</a></nav></header>
<script>document.getElementById('mobile-menu').classList.toggle('open');</script>"""
    assert lw.check_empty_menu(html3)


def test_same_breakpoint_hidden_beats_flex_any_order():
    # кейс mevahoksa: md:flex і md:hidden разом — у tailwind .hidden іде
    # останнім у стилях, тож перемагає незалежно від порядку в class=
    for cls in ("hidden md:flex x md:hidden", "hidden md:hidden x md:flex"):
        html = f'<header><nav class="{cls}"><a href="./a.html">A</a></nav></header>'
        assert lw.check_empty_menu(html), cls
        out, counts = lw.fix_empty_menu(html)
        assert lw.check_empty_menu(out) == [], cls


def test_no_header_or_no_nav_is_silent():
    assert lw.check_empty_menu("<body><nav class='md:hidden'></nav></body>") == []
    assert lw.check_empty_menu("<header><span>only brand</span></header>") == []


def test_hidden_img_sibling_does_not_shadow_nav():
    # void-теги не мають закривачки — не мусять ставати "предками" nav-а
    html = ('<header><img src="l.png" class="md:hidden">'
            '<nav><a href="./a.html">A</a></nav></header>')
    assert lw.check_empty_menu(html) == []


def test_desktop_nav_outside_header_is_not_empty_menu():
    # фолс з кешу (gecabhzai-ch-de): сайдбар-лейаут тримає мобільний хедер
    # під lg:hidden, а десктоп-меню виносить окремим <nav class="hidden lg:flex">
    # у колонку контенту. Автофікс розховував мобільний хедер — на десктопі
    # ставало два хедери, на мобільному не лишалося жодного.
    html = ('<body><header class="lg:hidden sticky top-0 z-50">'
            '<div class="flex justify-between"><a href="./">Brand</a>'
            '<button id="burger-btn">b</button></div>'
            '<nav id="mobile-menu" class="hidden"><a href="./company.html">A</a>'
            '<a href="./benefits.html">B</a></nav></header>'
            '<div class="lg:flex"><div class="hidden lg:block">photo</div>'
            '<div class="flex-1"><nav class="hidden lg:flex">'
            '<a href="./company.html">A</a><a href="./benefits.html">B</a></nav>'
            '<main>content</main></div></div></body>')
    assert lw.check_empty_menu(html) == []
    out, counts = lw.fix_empty_menu(html)
    assert out == html and counts == {}


def test_footer_and_toc_navs_do_not_mask_empty_menu():
    # дзеркало: поза хедером nav-и є і видимі на десктопі, але це legal-лінки
    # футера й зміст сторінки в <aside> (кейси namnhozka-ch-de, tefiko-br-pt),
    # а не меню сайта — десктоп-меню все одно пусте, чек мусить спрацювати
    html = ('<body><header><nav class="md:hidden"><a href="./a.html">A</a></nav>'
            '</header><main><section><aside><nav class="space-y-1">'
            '<a href="#p1">1</a><a href="#p2">2</a></nav></aside></section></main>'
            '<footer><nav class="flex flex-wrap gap-5">'
            '<a href="./privacy-policy.html">P</a></nav></footer></body>')
    assert lw.check_empty_menu(html) == ["no desktop-visible nav in <header>"]
    out, counts = lw.fix_empty_menu(html)
    assert 'class="hidden md:flex"' in out and counts


def test_hidden_nav_outside_header_does_not_mask_empty_menu():
    # поза хедером є nav рівня сторінки, але й він схований на десктопі
    html = ('<body><header><nav class="md:hidden"><a href="./a.html">A</a></nav>'
            '</header><div class="lg:hidden"><nav><a href="./a.html">A</a>'
            '</nav></div></body>')
    assert lw.check_empty_menu(html) == ["no desktop-visible nav in <header>"]


def test_commented_nav_ignored():
    html = ('<header><!-- <nav class="hidden"><a href="./x.html">x</a></nav> -->'
            '<nav class="md:hidden"><a href="./a.html">A</a></nav></header>')
    out, counts = lw.fix_empty_menu(html)
    assert counts.get("Empty menu: md:hidden → hidden md:flex") == 1
    assert '<!-- <nav class="hidden">' in out                   # комент не чіпаємо



# ----------------------------------- меню у <div>, а не <nav> (boigavant)
# Форма з boigavant-br-pt: десктоп-меню — <div class="hidden md:flex"> з
# чотирма лінками, а єдиний <nav> — мобільна шухляда. Чек не бачив меню,
# бо дивився лише на <nav>, і фікс розховував шухляду в хедер.
BOORARA = """<html><body>
<header class="bg-warp sticky top-0 z-50">
  <div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
    <a href="./" class="flex items-center"><span>Boorara</span></a>
    <div class="hidden md:flex items-center gap-1 text-sm">
      <a href="./company.html" class="px-3 py-2">Empresa</a>
      <a href="./benefits.html" class="px-3 py-2">Vantagens</a>
      <a href="./solutions.html" class="px-3 py-2">Solucoes</a>
      <a href="./testimonials.html" class="px-3 py-2">Depoimentos</a>
    </div>
    <button id="burger" class="md:hidden p-2">=</button>
  </div>
  <nav  class="{navcls}">
    <a href="./company.html" class="py-2">Empresa</a>
    <a href="./benefits.html" class="py-2">Vantagens</a>
  </nav>
</header></body></html>"""

DRAWER_OK = "hidden flex bg-warp px-4 py-3 flex flex-col gap-2"
DRAWER_ON_DESKTOP = "hidden md:flex flex bg-warp px-4 py-3 flex flex-col gap-2"


def test_menu_in_a_div_is_still_a_desktop_menu():
    """Меню не зобов'язане бути <nav>: чотири видимі лінки у <div> — це меню,
    і розховувати мобільну шухляду не можна."""
    html = BOORARA.format(navcls=DRAWER_OK)
    assert lw.check_empty_menu(html) == []
    assert lw.fix_empty_menu(html) == (html, {})


def test_only_contact_link_visible_is_still_empty_menu():
    """Один лінк на ./#contact — це не меню: чек має спрацювати як і раніше."""
    html = BOORARA.format(navcls=DRAWER_OK).replace(
        '<div class="hidden md:flex items-center gap-1 text-sm">',
        '<div class="hidden md:flex items-center gap-1 text-sm" data-x="1">'
    ).replace('<a href="./company.html" class="px-3 py-2">Empresa</a>', ''
    ).replace('<a href="./benefits.html" class="px-3 py-2">Vantagens</a>', ''
    ).replace('<a href="./solutions.html" class="px-3 py-2">Solucoes</a>', ''
    ).replace('<a href="./testimonials.html" class="px-3 py-2">Depoimentos</a>',
              '<a href="./#contact" class="px-3 py-2">Contato</a>')
    assert lw.check_empty_menu(html) == ["no desktop-visible nav in <header>"]


# --------------------------- мобільна шухляда, вивалена на десктоп

def test_drawer_shown_on_desktop_is_flagged_and_fixed():
    """Головний кейс: шухляді дописали md:flex, вона стала стовпчиком під
    шапкою поверх меню. Фікс міняє md:flex на звичайний flex."""
    html = BOORARA.format(navcls=DRAWER_ON_DESKTOP)
    issues = lw.check_drawer_on_desktop(html)
    assert len(issues) == 1 and "md:flex" in issues[0], issues
    out, counts = lw.fix_drawer_on_desktop(html)
    assert counts == {"Mobile drawer: bp:flex -> flex": 1}
    # md:flex у документі лишається — він є у СПРАВЖНЬОГО десктоп-меню;
    # перевіряємо саме тег шухляди
    assert '<nav  class="hidden flex bg-warp' in out
    assert 'md:flex bg-warp' not in out
    assert lw.check_drawer_on_desktop(out) == []
    assert lw.fix_drawer_on_desktop(out) == (out, {})     # ідемпотентно


def test_responsive_nav_flex_col_md_flex_row_is_untouched():
    """flex-col + md:flex-row — навмисний адаптив (у кеші 30 віток):
    вертикальний на мобільному, горизонтальний на десктопі. Не наш випадок."""
    html = BOORARA.format(navcls="hidden md:flex flex-col md:flex-row gap-6")
    assert lw.check_drawer_on_desktop(html) == []
    assert lw.fix_drawer_on_desktop(html) == (html, {})


def test_drawer_not_stripped_when_it_is_the_only_menu():
    """Якщо іншого меню в хедері немає — прибрати показ означало б лишити
    десктоп зовсім без навігації. Мовчимо."""
    html = ('<header><a href="./"><span>B</span></a>'
            f'<nav class="{DRAWER_ON_DESKTOP}">'
            '<a href="./company.html">A</a><a href="./benefits.html">B</a>'
            '</nav></header>')
    assert lw.check_drawer_on_desktop(html) == []


def test_empty_drawer_is_not_flagged():
    html = BOORARA.format(navcls=DRAWER_ON_DESKTOP).replace(
        '<a href="./company.html" class="py-2">Empresa</a>', ''
    ).replace('<a href="./benefits.html" class="py-2">Vantagens</a>', '')
    assert lw.check_drawer_on_desktop(html) == []


def test_lg_flex_drawer_is_caught_too():
    html = BOORARA.format(navcls="hidden lg:flex flex-col gap-2")
    issues = lw.check_drawer_on_desktop(html)
    assert len(issues) == 1 and "lg:flex" in issues[0], issues
    out, _ = lw.fix_drawer_on_desktop(html)
    assert 'class="hidden flex-col gap-2 flex"' in out, out[out.find('<nav'):][:140]


def test_two_checks_never_fire_together():
    """Умови взаємовиключні: пусте меню = меню немає, шухляда = меню є."""
    for cls in (DRAWER_OK, DRAWER_ON_DESKTOP, "md:hidden flex-col"):
        html = BOORARA.format(navcls=cls)
        both = bool(lw.check_empty_menu(html)) and bool(lw.check_drawer_on_desktop(html))
        assert not both, cls


def test_horizontal_nav_with_md_flex_is_a_real_menu_not_a_drawer():
    """Без flex-col це звичайне горизонтальне десктоп-меню, а не шухляда:
    прибрати md:flex означало б сховати навігацію."""
    html = BOORARA.format(navcls="hidden md:flex items-center gap-6")
    assert lw.check_drawer_on_desktop(html) == []
    assert lw.fix_drawer_on_desktop(html) == (html, {})


def test_bp_flex_becomes_plain_flex_not_just_removed():
    """Ключове: саме ЗАМІНА, а не видалення. `hidden` б'є `flex` (у Tailwind
    .hidden іде у стилях пізніше), тож на десктопі шухляди немає. Але коли
    бургер зніме `hidden`, має лишитись `display:flex` — з голим `hidden`
    елемент відкрився б як `block` і верстка меню поїхала б."""
    html = BOORARA.format(navcls="md:flex flex-col gap-2")
    out, counts = lw.fix_drawer_on_desktop(html)
    assert counts, "фікс мав спрацювати"
    assert 'class="hidden flex-col gap-2 flex"' in out, out[out.find('<nav'):][:140]
    assert lw.check_drawer_on_desktop(out) == []


# ------------------- шухляда — <div>, а flex-col лише в нащадку (peharlu)
# peharlu-br-pt: <div class="border-t … hidden flex"> з <nav class="flex
# flex-col"> усередині. Ні <nav> на самому елементі, ні flex-col на ньому —
# перша версія правила такий кейс не бачила зовсім.
PEHARLU = """<html><body>
<header class="paper-sheet sticky top-0">
  <div class="max-w-7xl mx-auto px-4">
    <div class="hidden md:flex items-end pt-3 gap-1">
      <a href="./" class="nav-tab active">Peharlu</a>
      <a href="./company.html" class="nav-tab">Empresa</a>
      <a href="./benefits.html" class="nav-tab">Vantagens</a>
      <a href="./solutions.html" class="nav-tab">Solucoes</a>
    </div>
    <button id="burger-btn" class="md:hidden flex flex-col gap-1.5 p-2">=</button>
  </div>
  <!-- Mobile menu -->
  <div class="border-t border-card-grey bg-sheet-white {drawer}">
    <nav class="flex flex-col px-4 py-3 gap-1">
      <a href="./" class="nav-tab">Inicio</a>
      <a href="./company.html" class="nav-tab">Empresa</a>
      <a href="./benefits.html" class="nav-tab">Vantagens</a>
    </nav>
  </div>
</header></body></html>"""


def test_div_drawer_with_flex_col_in_child_is_caught():
    html = PEHARLU.format(drawer="hidden md:flex")
    issues = lw.check_drawer_on_desktop(html)
    assert len(issues) == 1, issues
    out, counts = lw.fix_drawer_on_desktop(html)
    assert counts, "фікс мав спрацювати"
    assert 'bg-sheet-white hidden flex"' in out, out[out.find('<!-- Mobile'):][:160]
    assert lw.check_drawer_on_desktop(out) == []


def test_healthy_div_drawer_is_untouched():
    """До поломки шухляда вже правильна — hidden flex, без bp:."""
    html = PEHARLU.format(drawer="hidden flex")
    assert lw.check_drawer_on_desktop(html) == []
    assert lw.fix_drawer_on_desktop(html) == (html, {})


def test_desktop_menu_itself_is_never_taken_for_a_drawer():
    """У peharlu `hidden md:flex` мають ОБИДВА блоки. Розрізняє flex-col:
    у справжнього десктоп-меню його немає ні на собі, ні в нащадках
    (на 55 вітках корпусу ця ознака розділила їх зі 100% точністю)."""
    html = PEHARLU.format(drawer="hidden md:flex")
    out, _ = lw.fix_drawer_on_desktop(html)
    assert '<div class="hidden md:flex items-end pt-3 gap-1">' in out, "чіпнули меню"


def test_div_drawer_without_flex_col_anywhere_is_not_a_drawer():
    html = PEHARLU.format(drawer="hidden md:flex").replace(
        '<nav class="flex flex-col px-4 py-3 gap-1">', '<nav class="flex gap-1">')
    assert lw.check_drawer_on_desktop(html) == []


if __name__ == "__main__":
    run(dict(globals()))
