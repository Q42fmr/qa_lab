"""Перевірка cookie_consent: банер, який неможливо закрити.

Кейси зняті з реальної вітки haofmcanm-ch-de: власне правило сторінки
`.cookie-bar { display: none }` програє Tailwind-утиліті `flex` у class=
того ж елемента, бо стилі Tailwind CDN приїжджають у <head> пізніше.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                       # noqa: E402

cc = load_check("cookie_consent")

TAILWIND = '<script src="https://cdn.tailwindcss.com"></script>'

# як у haofmcanm-ch-de: ховається класом, показується компаунд-правилом
HAOFMCANM_CSS = """    #mobile-menu { display: none; }
    #mobile-menu.open { display: block; }
    .cookie-bar { display: none; }
    .cookie-bar.visible { display: flex; }"""

HAOFMCANM_BAR = (
    '<div id="cookie-bar" class="cookie-bar fixed bottom-0 left-0 right-0 z-50 '
    'bg-primary border-t-2 border-secondary px-4 py-4 flex flex-wrap items-center '
    'justify-between gap-4" role="dialog" aria-label="Cookie-Einwilligung">\n'
    '  <button id="cookie-accept">Akzeptieren</button>\n'
    '</div>')


def page(css, body, tailwind=True):
    return ("<!DOCTYPE html>\n<html><head>\n"
            + (TAILWIND + "\n" if tailwind else "")
            + "<style>\n" + css + "\n</style>\n</head><body>\n"
            + body + "\n</body></html>\n")


# ---------------------------------------------------------------- детект
def test_haofmcanm_pattern_is_flagged_as_error():
    issues = cc.run("index.php", page(HAOFMCANM_CSS, HAOFMCANM_BAR))
    assert len(issues) == 1, issues
    it = issues[0]
    assert it["severity"] == "error", it
    assert "cookie-bar" in it["message"], it
    assert "flex" in it["message"], it
    assert it["line"] > 0, it


def test_important_on_hiding_rule_is_not_flagged():
    """display:none !important перемагає утиліту — банер закривається."""
    css = HAOFMCANM_CSS.replace(".cookie-bar { display: none; }",
                                ".cookie-bar { display: none !important; }")
    assert cc.run("index.php", page(css, HAOFMCANM_BAR)) == []


def test_id_selector_hiding_is_not_flagged():
    """#cookie-bar (1,0,0) перемагає .flex (0,1,0) — конфлікту немає."""
    css = HAOFMCANM_CSS.replace(".cookie-bar { display: none; }",
                                "#cookie-bar { display: none; }")
    assert cc.run("index.php", page(css, HAOFMCANM_BAR)) == []


def test_tag_qualified_selector_is_not_flagged():
    """div.cookie-bar (0,1,1) теж перемагає утиліту."""
    css = HAOFMCANM_CSS.replace(".cookie-bar { display: none; }",
                                "div.cookie-bar { display: none; }")
    assert cc.run("index.php", page(css, HAOFMCANM_BAR)) == []


def test_without_tailwind_cdn_is_not_flagged():
    """Без Tailwind CDN порядок каскаду інший — не наша діагностика."""
    assert cc.run("index.php",
                  page(HAOFMCANM_CSS, HAOFMCANM_BAR, tailwind=False)) == []


def test_banner_without_display_utility_is_not_flagged():
    bar = HAOFMCANM_BAR.replace(" flex flex-wrap", " flex-wrap")
    assert cc.run("index.php", page(HAOFMCANM_CSS, bar)) == []


def test_tailwind_hidden_on_element_is_skipped():
    """Є і flex, і hidden — конфлікт усередині Tailwind, не з правилом сторінки."""
    bar = HAOFMCANM_BAR.replace(" flex flex-wrap", " flex hidden flex-wrap")
    assert cc.run("index.php", page(HAOFMCANM_CSS, bar)) == []


def test_hiding_rule_inside_media_query_is_flagged():
    css = ("@media (min-width: 768px) { .cookie-bar { display: none; } }\n"
           ".cookie-bar.visible { display: flex; }")
    issues = cc.run("index.php", page(css, HAOFMCANM_BAR))
    assert len(issues) == 1, issues


def test_selector_list_is_flagged():
    css = (".promo-bar, .cookie-bar { display: none; }\n"
           ".cookie-bar.visible { display: flex; }")
    issues = cc.run("index.php", page(css, HAOFMCANM_BAR))
    assert len(issues) == 1, issues
    assert "cookie-bar" in issues[0]["message"], issues


def test_non_consent_element_is_warn():
    css = ".promo-bar { display: none; }\n.promo-bar.visible { display: flex; }"
    bar = '<div class="promo-bar fixed bottom-0 flex gap-4">sale</div>'
    issues = cc.run("page.php", page(css, bar))
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "warn", issues


def test_tailwind_responsive_hidden_variant_is_skipped():
    """Перевірено в браузері: `lg:hidden` перемагає `flex` (обидва — Tailwind,
    порядок усередині його таблиці правильний), тож ховання працює як задумано.
    Кейс із pafeu-muutke-co-es: .burger-btn{display:none} у @media(min-width)
    плюс lg:hidden на елементі — це не баг."""
    css = ("@media (min-width: 1024px) { .burger-btn { display: none; } }")
    bar = ('<button id="burger-btn" class="burger-btn lg:hidden flex flex-col '
           'items-center w-12 h-12" aria-label="menu"></button>')
    assert cc.run("page.php", page(css, bar)) == []


def test_arbitrary_hidden_variant_is_skipped():
    css = ".panel { display: none; }"
    bar = '<div class="panel max-lg:hidden flex gap-2">x</div>'
    assert cc.run("page.php", page(css, bar)) == []


def test_desktop_nav_in_media_query_is_flagged_as_warn():
    """Кейс із revere-co-es: на мобільному десктопне меню мусить зникати, але
    .flex перемагає — меню лишається поряд з бургером. Реальний баг верстки."""
    css = ("@media (max-width: 768px) { .desktop-nav { display: none; } }\n"
           "#burger-btn { display: none; }")
    nav = '<nav class="desktop-nav flex items-center gap-6">links</nav>'
    issues = cc.run("page.php", page(css, nav))
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "warn", issues
    assert "desktop-nav" in issues[0]["message"], issues


def test_fix_leaves_nav_case_untouched():
    """Для меню правило показу відсутнє — прибирати flex означало б зламати
    розкладку (меню стало б display:block). Тільки репорт."""
    css = "@media (max-width: 768px) { .desktop-nav { display: none; } }"
    src = page(css, '<nav class="desktop-nav flex items-center gap-6">l</nav>')
    assert cc.fix("index.php", src) == src


def test_inline_flex_utility_is_flagged():
    bar = HAOFMCANM_BAR.replace(" flex flex-wrap", " inline-flex flex-wrap")
    issues = cc.run("index.php", page(HAOFMCANM_CSS, bar))
    assert len(issues) == 1, issues
    assert "inline-flex" in issues[0]["message"], issues


# ---------------------------------------------------------------- автофікс
def test_fix_removes_conflicting_utility_only():
    src = page(HAOFMCANM_CSS, HAOFMCANM_BAR)
    out = cc.fix("index.php", src)
    assert out != src
    # утиліта display прибрана з class= банера
    assert ' flex flex-wrap' not in out
    assert 'flex-wrap' in out, "решта утиліт мусить лишитись"
    assert 'items-center' in out and 'justify-between' in out and 'gap-4' in out
    assert 'cookie-bar fixed bottom-0' in out
    # css і решта розмітки не змінені
    assert '.cookie-bar { display: none; }' in out
    assert '.cookie-bar.visible { display: flex; }' in out
    assert 'id="cookie-accept"' in out
    assert 'role="dialog"' in out
    # після фіксу перевірка чиста
    assert cc.run("index.php", out) == []


def test_fix_is_idempotent():
    once = cc.fix("index.php", page(HAOFMCANM_CSS, HAOFMCANM_BAR))
    assert cc.fix("index.php", once) == once


def test_fix_skips_element_without_shown_rule():
    """Немає правила показу (.X.Y{display:...}) — прибирати утиліту небезпечно:
    елемент може показуватись зняттям самого класу, і тоді flex ще потрібен."""
    css = ".cookie-bar { display: none; }"
    src = page(css, HAOFMCANM_BAR)
    assert cc.fix("index.php", src) == src        # фікс не чіпає
    assert len(cc.run("index.php", src)) == 1     # але проблему видно


def test_fix_without_tailwind_is_noop():
    src = page(HAOFMCANM_CSS, HAOFMCANM_BAR, tailwind=False)
    assert cc.fix("index.php", src) == src


def test_fix_preserves_single_quoted_class_attr():
    bar = ("<div id='cookie-bar' class='cookie-bar fixed flex gap-4'>"
           "<button id='cookie-accept'>ok</button></div>")
    out = cc.fix("index.php", page(HAOFMCANM_CSS, bar))
    assert "class='cookie-bar fixed gap-4'" in out, out


def test_fix_handles_two_banners_in_one_page():
    css = (".cookie-bar { display: none; }\n.cookie-bar.visible { display: flex; }\n"
           ".gdpr-bar { display: none; }\n.gdpr-bar.on { display: grid; }")
    body = ('<div class="cookie-bar fixed flex gap-4">a</div>\n'
            '<div class="gdpr-bar grid gap-2">b</div>')
    src = page(css, body)
    assert len(cc.run("page.php", src)) == 2
    out = cc.fix("page.php", src)
    assert 'class="cookie-bar fixed gap-4"' in out, out
    assert 'class="gdpr-bar gap-2"' in out, out
    assert cc.run("page.php", out) == []

# ------------------------------------------ правило 2: мертва кнопка згоди
# кейс chafelzibau-br-pt: банер приїхав з Next.js, розмітка у html, обробник
# у React-бандлі. Заміряно в браузері: нуль ключів __react* на кнопці, клік
# не робить нічого, ні кукі, ні localStorage.
NEXT_MARK = '<script>self.__next_f=[];</script>'
LGPD_BANNER = (
    '<div role="region" aria-label="Aviso de uso de cookies" class="style_Consent__x">'
    '<p>Utilizamos cookies para melhorar a experiência</p>'
    '<button type="button" class="style_button__y" style="cursor:pointer">Entendi'
    '<svg style="width:16px;height:16px" viewBox="0 0 24 24"><path d="M1 1"/></svg>'
    '</button></div>')


def _next_page(body=LGPD_BANNER, head=""):
    return ("<!DOCTYPE html><html><head>" + head + "</head><body>"
            + body + NEXT_MARK + "</body></html>")


def test_dead_accept_button_is_flagged():
    issues = cc.run("index.html", _next_page())
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "error", issues
    assert "Entendi" in issues[0]["message"], issues[0]["message"]


def test_label_with_an_icon_is_still_found():
    """Перший варіант детекту обмежував вміст кнопки 200 символами і саме на
    `<svg>` після тексту й спотикався — кнопку `chafelzibau` не бачив."""
    big = LGPD_BANNER.replace('<path d="M1 1"/>', '<path d="' + "M1 1 " * 80 + '"/>')
    assert len(cc.run("index.html", _next_page(big))) == 1


def test_fix_marks_banner_and_button_and_adds_script():
    out = cc.fix("index.html", _next_page())
    assert 'data-wp-consent="banner"' in out, out
    assert 'data-wp-consent="accept"' in out, out
    assert cc.MARKER in out, out
    assert out.index(cc.MARKER) < out.index("</body>"), "скрипт має бути в body"
    assert cc.run("index.html", out) == []


def test_fix_for_dead_button_is_idempotent():
    once = cc.fix("index.html", _next_page())
    assert cc.fix("index.html", once) == once


def test_inline_consent_script_means_hands_off():
    """Інлайновий скрипт зі ЗГОДОЮ (не просто роботою з куками) виконається
    завжди — там нема що лагодити."""
    head = '<script>if(!localStorage.getItem("cookieConsent"))show()</script>'
    src = _next_page(head=head)
    assert cc.run("index.html", src) == []
    assert cc.fix("index.html", src) == src


def test_technical_cookie_helper_is_not_consent():
    """setCookie-утиліта (pitchbar serralheria, 02.10) містить і слово
    cookie, і document.cookie — але це НЕ механізм згоди: банер на
    головній однаково вимагається."""
    head = ('<script>function setCookie(n,t,i){document.cookie=n+"="+t}'
            '</script>')
    issues = cc.run("index.html",
                    _next_page(body="<p>loja</p>", head=head))
    assert issues and "немає кукі-банера" in issues[0]["message"], issues


# ------------------------------------------------------------ Wix Thunderbolt
# Той самий дефект, інший фреймворк. Кейс `bralobmgeon.com.br`: банер Consentik
# приїхав уже відрендереним (запечений `style="display: flex;"`), а обробник
# кліку лежить у зовнішньому `extensions/index.js`, який вантажиться лише
# всередині `fetchDa().then(...)`; той fetch іде на `/sites/null/data.json`, а
# теки `sites/` у скрейпі немає - проміс реджектиться, обробник не реєструється.
WIX_MARK = ('<script>(()=>{"use strict";'
            'self.webpackJsonp__wix_thunderbolt_app=[];})();</script>')
WIX_BANNER = (
    '<div id="consentik-cookie"><div id="cst-cookie-banner" style="display: flex;">'
    '<p>Utilizamos cookies para melhorar a sua experiência</p>'
    '<button id="cst-cookies-submit" tabindex="0" class="cst-cookies-btn">Concordo</button>'
    '</div></div>')


def _wix_page(body=WIX_BANNER, head=""):
    return ("<!DOCTYPE html><html><head>" + head + "</head><body>"
            + body + WIX_MARK + "</body></html>")


def test_wix_dead_accept_button_is_flagged():
    issues = cc.run("index.html", _wix_page())
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "error"
    assert "Concordo" in issues[0]["message"]


def test_wix_fix_marks_banner_and_button():
    out = cc.fix("index.html", _wix_page())
    assert 'data-wp-consent="banner"' in out
    assert 'data-wp-consent="accept"' in out
    assert cc.MARKER in out
    assert cc.run("index.html", out) == []
    assert cc.fix("index.html", out) == out


def test_banner_mark_lands_on_the_whole_widget_not_the_button_row():
    """Заміряно в браузері на `bralobmgeon.com.br`: над кнопкою три обгортки, і
    видимий банер - НЕ найглибша. Позначивши найглибшу, фікс прибирав лише
    рядок із кнопкою, а банер 238px лишався на екрані вже без кнопки, тобто
    ставав незакривабельним назовсім."""
    nested = (
        '<div id="consentik-cookie">'
        '<div id="cst-cookie-banner" style="display: flex;">'
        '<p>Utilizamos cookies para melhorar a sua experiência</p>'
        '<div class="cst-action-row"><div class="cst-action-decisive">'
        '<button id="cst-cookies-submit">Concordo</button>'
        '</div></div></div></div>')
    out = cc.fix("index.html", _wix_page(nested))
    import re as _re
    marked = _re.search(r'<div[^>]*data-wp-consent="banner"[^>]*>', out)
    assert marked, out[:400]
    # позначено саме віджет згоди, а не флекс-рядок усередині нього
    assert "consentik-cookie" in marked.group(0), marked.group(0)
    assert "cst-action" not in marked.group(0), marked.group(0)


def test_anonymous_wrapper_still_falls_back_to_nearest():
    """Межа з іншого боку: якщо кукі-лексики немає ні в однієї обгортки, беремо
    найближчу - інакше такі банери взагалі перестали б позначатися."""
    anon = ('<div class="a1"><div class="b2">'
            '<p>Utilizamos cookies</p>'
            '<button type="button">Concordo</button>'
            '</div></div>')
    out = cc.fix("index.html", _wix_page(anon))
    import re as _re
    marked = _re.search(r'<div[^>]*data-wp-consent="banner"[^>]*>', out)
    assert marked and 'class="b2"' in marked.group(0), marked.group(0) if marked else out[:300]


def test_platform_bundle_does_not_count_as_inline_consent():
    """Головна причина, чому дефект не ловився: платформні бандли Wix згадують
    кукі-лексику й `localStorage` ПОБІЧНО (rspack-рантайм, телеметрія fedops), і
    гард `_has_inline_consent` вважав це власною логікою згоди сторінки."""
    bundle = ('<script>(()=>{"use strict";t.ruid="bundler=rspack@1.6.8";'
              'let c=e=>localStorage.getItem("cookie-consent-fedops");'
              'self.webpackJsonp__wix_thunderbolt_app=[];})();</script>')
    assert cc._has_inline_consent(bundle) is False
    # і сторінка з таким бандлом мусить далі репортитись
    assert len(cc.run("index.html", _wix_page(head=bundle))) == 1


def test_handwritten_inline_consent_still_silences_the_check():
    """Межа з іншого боку: коротка ВЛАСНА логіка згоди - hands off, як і було."""
    own = '<script>if(!localStorage.getItem("cookie"))showCookieBar()</script>'
    assert cc._has_inline_consent(own) is True
    assert cc.run("index.html", _wix_page(head=own)) == []


def test_plain_static_page_is_not_touched():
    """Без ознак React-статики кнопку не чіпаємо: там обробник може бути у
    локальному .js, і він працює."""
    src = "<!DOCTYPE html><html><body>" + LGPD_BANNER + "</body></html>"
    assert cc.run("index.html", src) == []
    assert cc.fix("index.html", src) == src


def test_button_with_own_onclick_is_not_touched():
    src = _next_page(LGPD_BANNER.replace('type="button"', 'onclick="ok()"'))
    assert cc.run("index.html", src) == []


def test_a_link_with_real_href_is_not_a_consent_button():
    body = ('<div aria-label="cookies"><p>cookies</p>'
            '<a href="/politica">Aceitar termos</a></div>')
    assert cc.run("index.html", _next_page(body)) == []


def test_button_far_from_cookie_text_is_not_touched():
    body = ('<div><p>' + "x" * 1200 + '</p></div>'
            '<div><button type="button">Accept</button></div>')
    assert cc.run("page.html", _next_page(body)) == []


# ------------------------------- правило 3: зіпсоване ім'я браузерного API
# кейс ocu-br-pt: у `localStorage` вбито фрагмент назви вітки. Заміряно в
# браузері: `locabrptlStorage.getItem(...)` кидає дослівно
# «ReferenceError: locabrptlStorage is not defined», банер лишається без класу
# `show`, тобто НЕ ПОКАЗУЄТЬСЯ взагалі, а кнопка мертва.
BROKEN_JS = ('<div id="cookie-modal"><button id="cookie-accept">Aceitar</button></div>'
             '<script>(function(){var m=document.getElementById("cookie-modal");'
             'var c=locabrptlStorage.getItem("cookieConsent");'
             'if(!c&&m)m.classList.add("show");})()</script>')


def test_broken_builtin_is_flagged():
    issues = cc.run("index.php", "<html><body>" + BROKEN_JS + "</body></html>")
    assert len(issues) == 1, issues
    assert "locabrptlStorage" in issues[0]["message"], issues[0]["message"]
    assert "localStorage" in issues[0]["message"], issues[0]["message"]


def test_fix_restores_the_builtin_name():
    out = cc.fix("index.php", "<html><body>" + BROKEN_JS + "</body></html>")
    assert "locabrptlStorage" not in out, out
    assert 'localStorage.getItem("cookieConsent")' in out, out
    assert cc.run("index.php", out) == []


def test_real_builtins_are_not_touched():
    """`sessionStorage` не має матчити сам себе: після `sessi` там немає
    зайвих символів. Так само не чіпаємо звичайні хелпери."""
    for good in ("localStorage.getItem('x')", "sessionStorage.setItem('x',1)",
                 "saveToLocalStorage(v)", "useLocalStorage()",
                 "getSessionStorage()", "AsyncLocalStorage"):
        src = "<html><body><p>cookies</p><script>" + good + "</script></body></html>"
        assert cc.run("page.php", src) == [], good
        assert cc.fix("page.php", src) == src, good


def test_broken_builtin_outside_a_cookie_page_is_ignored():
    src = "<html><body><script>var x=locabrptlStorage;</script></body></html>"
    assert cc.run("page.php", src) == []


def test_every_occurrence_is_repaired():
    js = ('<p>cookie</p><script>locabrptlStorage.getItem("a");'
          'locabrptlStorage.setItem("a",1);</script>')
    out = cc.fix("index.php", "<html><body>" + js + "</body></html>")
    assert out.count("localStorage") == 2 and "locabrptlStorage" not in out, out


def test_marker_alone_stops_a_second_pass():
    """Ідемпотентність тримає МАРКЕР, а не те, що вставлений скрипт випадково
    схожий на «свій обробник згоди»: інакше зміна тексту скрипта тихо
    поламала б захист і фікс дописував би його щоразу."""
    marked = _next_page(
        LGPD_BANNER.replace('type="button"', 'type="button" data-wp-consent="accept"')
        + '<script>/* ' + cc.MARKER + ' */var q=1;</script>')
    assert cc.run("index.html", marked) == []
    assert cc.fix("index.html", marked) == marked


def test_a_long_label_is_not_a_consent_button():
    """Слово «Aceitar» трапляється і в довгому тексті, обгорнутому в <a>/<button>.
    Позначити такий елемент кнопкою означало б причепити скрипт не туди."""
    body = ('<div aria-label="cookies"><p>cookies</p><button type="button">'
            'Aceitar todos os cookies, incluindo os de marketing e analytics, '
            'conforme a nossa politica</button></div>')
    assert cc.run("index.html", _next_page(body)) == []


def test_mismatched_head_and_tail_is_not_repaired():
    """Склейка країв мусить давати РІВНО білтін: `loca…onStorage` це не
    `localStorage`, і «ремонтувати» його означало б вигадати ім'я."""
    src = ("<html><body><p>cookie</p><script>var x=locabrptonStorage;"
           "var y=locaonStorage;</script></body></html>")
    assert cc.run("page.php", src) == []
    assert cc.fix("page.php", src) == src


def test_a_one_character_corruption_is_also_repaired():
    """Поріг «вбито щонайменше 2 символи» був би вигаданим: однолітерна псута
    ламає скрипт так само."""
    src = "<html><body><p>cookie</p><script>locaXlStorage.getItem('a')</script></body></html>"
    assert len(cc.run("page.php", src)) == 1
    assert "localStorage.getItem" in cc.fix("page.php", src)


# ------------- правило 4: нативний <dialog>, який CSS показує безумовно
# кейс pefi-noku-br-pt: `#cookie-dialog { display:flex }` без [open] перемагає
# UA-правило `dialog:not([open]){display:none}` — діалог намальований завжди.
# close() знімає open, але авторське правило діє далі, тож «Aceitar todos» не
# ховає банер, і зі збереженою згодою він знову видимий після перезавантаження.
# Fallback `setAttribute('hidden')` — мертва гілка: dialog.close існує всюди.
DIALOG_CSS = ("#cookie-dialog { position: fixed; inset: 0; display: flex; "
              "align-items: flex-end; z-index: 9999; }\n"
              "    #cookie-dialog[hidden] { display: none; }")
DIALOG_BODY = (
    '<dialog id="cookie-dialog" aria-label="Preferências de cookies">'
    '<div id="cookie-banner"><h2>Este site utiliza cookies</h2>'
    '<button id="cookie-accept">Aceitar todos</button></div></dialog>'
    "<script>(function(){var dialog=document.getElementById('cookie-dialog');"
    "if(!localStorage.getItem('pn'))dialog.showModal();"
    "document.getElementById('cookie-accept').addEventListener('click',"
    "function(){dialog.close?dialog.close():dialog.setAttribute('hidden','');});"
    "})();</script>")


def _dialog_page(css=DIALOG_CSS, body=DIALOG_BODY):
    return page(css, body, tailwind=False)


def test_unconditional_dialog_rule_is_flagged():
    issues = cc.run("index.php", _dialog_page())
    assert len(issues) == 1, issues
    it = issues[0]
    assert it["severity"] == "error", it
    assert "cookie-dialog" in it["message"] and "[open]" in it["message"], it
    assert it["line"] > 0, it


def test_dialog_rule_scoped_to_open_is_fine():
    css = DIALOG_CSS.replace("#cookie-dialog {", "#cookie-dialog[open] {")
    assert cc.run("index.php", _dialog_page(css=css)) == []


def test_dialog_hiding_rule_alone_is_fine():
    assert cc.run("index.php",
                  _dialog_page(css="#cookie-dialog { display: none; }")) == []


def test_dialog_child_rule_is_not_flagged():
    css = "#cookie-dialog .box { display: flex; }"
    assert cc.run("index.php", _dialog_page(css=css)) == []


def test_non_consent_dialog_is_warn():
    css = "#promo-modal { display: flex; }"
    body = ('<dialog id="promo-modal"><p>Assine a newsletter!</p>'
            '<button id="promo-close">Fechar</button></dialog>')
    issues = cc.run("page.php", _dialog_page(css=css, body=body))
    assert len(issues) == 1 and issues[0]["severity"] == "warn", issues


def test_class_based_dialog_is_flagged_and_fixed():
    css = ".cookie-modal { display: grid; }"
    body = ('<dialog class="cookie-modal"><p>cookies</p>'
            '<button>Aceitar</button></dialog>')
    src = _dialog_page(css=css, body=body)
    assert len(cc.run("index.php", src)) == 1
    out = cc.fix("index.php", src)
    assert ".cookie-modal[open] { display: grid; }" in out, out
    assert cc.run("index.php", out) == []


def test_fix_scopes_the_show_rule_to_open():
    out = cc.fix("index.php", _dialog_page())
    assert "#cookie-dialog[open] { position: fixed;" in out, out
    assert "#cookie-dialog[hidden] { display: none; }" in out, out
    assert cc.run("index.php", out) == []


def test_fix_dialog_is_idempotent():
    once = cc.fix("index.php", _dialog_page())
    assert cc.fix("index.php", once) == once


def test_fix_selector_list_only_touches_the_dialog_part():
    css = ".promo, #cookie-dialog { display: flex; }"
    out = cc.fix("index.php", _dialog_page(css=css))
    assert ".promo, #cookie-dialog[open] { display: flex; }" in out, out


# ------------------------------------------------- правило 5: банера немає
NOBANNER = ('<!DOCTYPE html><html lang="pt-BR"><head></head><body>'
            "<header><h1>Marco Tempo</h1></header>"
            '<footer><a href="./politica-de-privacidade.html">Política de '
            "Privacidade (LGPD)</a></footer></body></html>")


def _fb(files):
    acts = cc.fix_branch(dict(files), list(files), "x-br-pt")
    return {a["path"]: a["content"] for a in acts}


def test_missing_banner_on_home_is_flagged_and_added():
    issues = cc.run("index.php", NOBANNER)
    assert len(issues) == 1 and issues[0]["severity"] == "error", issues
    assert "немає кукі-банера" in issues[0]["message"], issues
    out = _fb({"index.php": NOBANNER})["index.php"]
    assert f'{cc.CONSENT_ATTR}="banner"' in out
    assert "position:fixed" in out
    assert "Aceitar" in out and "Recusar" in out, "мова не pt"
    assert 'href="./politica-de-privacidade.html"' in out.split("banner")[1], \
        "лінк на політику не підхоплено"
    assert cc.MARKER in out
    # після фікса — тихо та ідемпотентно
    assert cc.run("index.php", out) == []
    assert _fb({"index.php": out}) == {}


def test_missing_banner_flagged_without_privacy_link_too():
    """02.10 (br-pt партія: aure, extermine, evidence, serralheria): QA
    вимагає банер і на вайтах без жодної privacy-сторінки — лінк більше
    не умова."""
    bare = NOBANNER.replace(
        '<a href="./politica-de-privacidade.html">Política de '
        "Privacidade (LGPD)</a>", "")
    issues = cc.run("index.php", bare)
    assert issues and "немає кукі-банера" in issues[0]["message"], issues


def test_enfold_font_optin_script_with_consent_disabled_is_not_a_banner():
    """eqeudoha-cotfaup-ch-fr (26.10, QA «на главной нет баннера куки»):
    Enfold кладе на кожну сторінку інлайн-перевірку веб-шрифтів з
    «aviaCookieConsent» і document.cookie, але клас <html>
    `av-cookies-no-cookie-consent` каже, що згода в темі ВИМКНЕНА — банера
    нема. Гард «власна логіка згоди» це приймав за банер."""
    enfold = ('<!DOCTYPE html><html class="html_stretched av-cookies-no-cookie-consent av-default-lightbox" lang="fr">'
              '<head><script type="text/javascript">(function() { var html = document.getElementsByTagName("html")[0];'
              ' var cookie_check = html.className.indexOf("av-cookies-needs-opt-in") >= 0;'
              ' if( cookie_check && ! document.cookie.match(/aviaCookieConsent/) ) { allow_continue = false; } })();</script>'
              '</head><body><header><h1>Equipage</h1></header><footer><a href="./impressum/index.html">Impressum</a></footer></body></html>')
    issues = cc.run("index.php", enfold)
    assert issues and "немає кукі-банера" in issues[0]["message"], issues
    out = _fb({"index.php": enfold})["index.php"]
    assert f'{cc.CONSENT_ATTR}="banner"' in out and "Accepter" in out
    assert cc.run("index.php", out) == []
    # тема зі ВВІМКНЕНОЮ згодою (needs-opt-in) малює власний банер — не чіпаємо
    on = enfold.replace("av-cookies-no-cookie-consent", "av-cookies-needs-opt-in")
    assert cc.run("index.php", on) == []


def test_no_cookies_statement_does_not_silence_and_gets_cleaned():
    """02.10 (hakrebqefozr та ще 4 ch-de-2): шаблонна заява «сайт не ставить
    кук» більше не глушить — QA вимагає банер; фікс чистить і заяву,
    лишаючи решту речення цілою."""
    says_no = NOBANNER.replace(
        "<header>",
        "<p>Über diese Website wird nicht bezahlt; sie zeigt keine Werbung "
        "und setzt keine Cookies.</p><header>")
    issues = cc.run("index.php", says_no)
    assert issues and "немає кукі-банера" in issues[0]["message"], issues
    out = _fb({"index.php": says_no})["index.php"]
    assert f'{cc.CONSENT_ATTR}="banner"' in out
    assert "keine Cookies" not in out, "брехлива заява лишилась"
    assert "zeigt keine Werbung." in out, "решту речення знесено"
    assert cc.run("index.php", out) == []

def test_missing_banner_fix_never_touches_css_outside_the_phrase():
    """19.10: чистка розділових знаків після вирізу «не ставить кук» бігла
    по ВСЬОМУ документу і склеювала descendant-селектори у <style>
    (`.nav .brand`→`.nav.brand`, 66 правил на ladehavdpafnacesia,
    «INSIDE» зливався з фоном на incejuitkoufokidi). Стилі й текст поза
    фразою — байт у байт як були."""
    css = "<style>.nav .brand .name{color:#fff} .a , .b{x:1}</style>"
    says_no = NOBANNER.replace("<header>", css + "<p>Schnell, ehrlich und setzt keine Cookies , versprochen.</p><header>")
    out = _fb({"index.php": says_no})["index.php"]
    assert css in out, "CSS-селектори склеєно"
    assert "<p>Schnell, ehrlich, versprochen.</p>" in out, out
    # без фрази взагалі — документ поза банером незмінний
    out2 = _fb({"index.php": NOBANNER.replace("<header>", css + "<header>")})["index.php"]
    assert css in out2


def test_inner_page_is_not_judged_for_banner():
    assert cc.run("about.html", NOBANNER) == []


def test_existing_cmp_script_counts_as_banner():
    with_cmp = NOBANNER.replace(
        "</body>", '<script src="https://cdn.cookiebot.com/uc.js"></script></body>')
    assert cc.run("index.php", with_cmp) == []


def test_banner_buttons_take_site_class():
    """Кнопки банера — у стилях ВІТКИ: клас кнопки сайту (av-btn) і його
    line-варіант для «Відхилити»; без класу — css-акцент з змінних."""
    styled = NOBANNER.replace(
        "<header>",
        '<a class="av-btn" href="./contact.html">Kontakt</a>'
        '<a class="av-btn av-btn--line" href="./x.html">Mehr</a><header>')
    out = _fb({"index.php": styled})["index.php"]
    bn = out.split('data-wp-consent="banner"')[1]
    assert 'class="av-btn"' in bn, "accept не в класі сайту"
    assert 'class="av-btn av-btn--line"' in bn, "decline не line-варіант"
    # без класу: акцент тягнеться з css-змінної вітки
    out2 = _fb({"index.php": NOBANNER,
                "assets/site.css": ":root{--av-primary:#0F6E5C;}"})["index.php"]
    assert "background:#0F6E5C" in out2, out2.split("banner")[1][:200]


def test_icon_or_fill_less_site_class_is_not_used_for_banner_buttons():
    """incejuitkoufokidi (15.10): перший `*-btn` на сторінці — кнопка-іконка
    пошуку `.srch-btn{background:none;color:var(--grafite)}`; «Aceitar» у
    цьому класі став темним текстом на темному барі. Клас-іконка і клас без
    заливки пропускаються, кнопки лишаються у власних стилях."""
    iconish = NOBANNER.replace(
        "<header>",
        '<style>.srch-btn{background:none;color:#221D18}</style>'
        '<button class="srch-btn">🔍</button><header>')
    bn = _fb({"index.php": iconish})["index.php"].split('data-wp-consent="banner"')[1]
    assert 'class="srch-btn"' not in bn
    assert 'data-wp-consent="accept" style="' in bn
    # не іконка, але CSS вітки каже: заливка прозора
    ghost = NOBANNER.replace(
        "<header>", '<a class="cta-btn" href="./x.html">Mehr</a><header>')
    out = _fb({"index.php": ghost,
               "assets/site.css": ".cta-btn{background:transparent;color:#111}"})["index.php"]
    assert 'class="cta-btn"' not in out.split('data-wp-consent="banner"')[1]
    # заливку дає другий клас — пара класів береться
    pair = NOBANNER.replace(
        "<header>", '<a class="btn btn-primary" href="./x.html">Mehr</a><header>')
    out = _fb({"index.php": pair,
               "assets/site.css": ".btn{background:none}.btn-primary{background:#0F6E5C}"})["index.php"]
    assert 'class="btn btn-primary"' in out.split('data-wp-consent="banner"')[1]

def test_layout_utility_site_class_is_not_used_for_banner_buttons():
    """ligjo-mepmri (28.10): перший `.btn` на сторінці — тогл акордеона
    `btn btn-link btn-acordion … d-flex justify-content-between w-100`; банер
    узяв його, і «Recusar» став рамкою на всю ширину, «Aceitar» — голим текстом.
    Клас-набір з утилітами розкладки пропускається, береться наступна кнопка."""
    toggle = NOBANNER.replace(
        "<header>",
        '<button class="btn btn-link btn-acordion text-white p-0 d-flex '
        'justify-content-between w-100 align-items-center">Entrega</button>'
        '<a class="btn btn-primary" href="./x.html">Comprar</a><header>')
    bn = _fb({"index.php": toggle,
              "assets/site.css": ".btn-link{background:none}.btn-primary{background:#0F6E5C}"}
             )["index.php"].split('data-wp-consent="banner"')[1]
    assert "btn-acordion" not in bn and "w-100" not in bn, bn[:300]
    assert 'class="btn btn-primary"' in bn

def test_our_banner_without_fixed_is_pinned_back():
    out = _fb({"index.php": NOBANNER})["index.php"]
    broken = out.replace("position:fixed;left:0;right:0;bottom:0;"
                         "z-index:2147483000;", "")
    issues = cc.run("index.php", broken)
    assert any("ПОТОЦІ" in i["message"] for i in issues), issues
    healed = cc.fix("index.php", broken)
    assert "position:fixed" in healed
    assert cc.run("index.php", healed) == []


# ------------------------------------------------- правило 7: нема decline
# 27.10 QA (br-pt партія 1027: fia-de-sevga-marrat-br-pt, soba-lezo-picazos-br-pt):
# на головній РОБОЧИЙ банер згоди з однією кнопкою — «Accept»/«Entendi», QA:
# «Нет "отклонить"». Вимагаємо лінк на cookie-/privacy-сторінку (PRIVACY_PAGE_RX),
# щоб не чіпати мінімальні фрагменти з інших правил (мертва кнопка, dialog,
# display-конфлікт), де банер ще не завершений UI-блок.
DECLINE_SRC = (
    '<div class="cookie-bar" role="dialog">'
    '<p>We use cookies to improve your experience. See our '
    '<a href="/privacy-policy.html">Privacy Policy</a>.</p>'
    '<button type="button" class="btn-accept">Accept</button>'
    '</div>')


def _decline_page(lang="en", src=DECLINE_SRC):
    return (f'<!DOCTYPE html><html lang="{lang}"><head></head><body>'
            + src + '</body></html>')


def test_missing_decline_button_is_flagged():
    issues = cc.run("index.php", _decline_page())
    assert len(issues) == 1, issues
    it = issues[0]
    assert it["severity"] == "error", it
    assert "Відхилити" in it["message"] and "Decline" in it["message"], it["message"]


def test_fix_adds_decline_button_in_same_style():
    out = cc.fix("index.php", _decline_page())
    assert 'data-wp-consent="decline"' in out, out
    assert '>Decline</button>' in out, out
    assert 'data-wp-consent="banner"' in out, out
    assert cc.run("index.php", out) == []


def test_fix_for_missing_decline_is_idempotent():
    once = cc.fix("index.php", _decline_page())
    assert cc.fix("index.php", once) == once


def test_decline_label_follows_page_language_it():
    out = cc.fix("index.php", _decline_page(lang="it"))
    assert ">Rifiuta</button>" in out, out


def test_decline_label_follows_page_language_ja():
    out = cc.fix("index.php", _decline_page(lang="ja"))
    assert "拒否する" in out, out


BG_SRC = (
    '<div class="cookie-bar">We use cookies. See our '
    '<a href="/privacy-policy.html">Privacy Policy</a>.'
    '<button type="button" style="background:#10b981;color:#fff">Accept</button>'
    '</div>')


def test_fix_overrides_inline_background_on_cloned_decline():
    out = cc.fix("index.php", _decline_page(src=BG_SRC))
    assert ('style="background:transparent;color:inherit;'
            'border:1px solid currentColor"') in out, out


BOTH_BTNS = (
    '<div class="cookie-bar">We use cookies. See our '
    '<a href="/privacy-policy.html">Privacy Policy</a>.'
    '<button type="button">Accept</button>'
    '<button type="button">Decline</button></div>')


def test_banner_with_both_buttons_is_not_flagged():
    assert cc.run("index.php", _decline_page(src=BOTH_BTNS)) == []


def test_generated_banner_is_not_flagged_for_missing_decline():
    """Наш же згенерований банер (правило 5) вже має й accept, і decline."""
    src = ('<!DOCTYPE html><html lang="pt-BR"><head></head><body>'
           '<footer><a href="/politica-de-privacidade.html">Privacidade</a>'
           '</footer></body></html>')
    out = _fb({"index.php": src})["index.php"]
    assert cc.run("index.php", out) == []


REAL_LINK_SRC = (
    '<div class="cookie-bar">We use cookies. See our '
    '<a href="/privacy-policy.html">Privacy Policy</a> '
    '<a href="/terms">Accept terms</a></div>')


def test_accept_control_with_real_href_is_not_a_consent_button_for_rule7():
    assert cc.run("index.php", _decline_page(src=REAL_LINK_SRC)) == []

if __name__ == "__main__":
    run(dict(globals()))
