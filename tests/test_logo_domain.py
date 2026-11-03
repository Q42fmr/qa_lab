"""Тести logo_domain: лого і всі згадки мають нести НАЗВУ ВІТКИ.

Еталон — site_name.expected(branch) (колонка «Название» у ClickUp), не
домен: домени міняються, назва вайта стабільна. Правила «домен = лого +
хвіст» померли разом з доменним еталоном — назва вітки чиста, рівності
через варіанти написання (site_name.same) вистачає. Фікс, окрім лого
хедера/футера, перейменовує стару назву по всьому сайту.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("logo_domain")

PAGE = """<html><body>
<header class="bg-x">
  <a href="./" class="flex items-center gap-2 font-headers">
    <i class="fa-solid fa-anchor"></i>
    {logo}
  </a>
  <nav><a href="./company.html">Empresa</a></nav>
</header>
<main><h1>Consultoria Tajbojo</h1></main>
<footer>
  <a href="./" class="font-headers"><i class="fa-solid fa-anchor"></i> {flogo}</a>
  <ul><li><a href="./">In\u00edcio</a></li></ul>
</footer>
</body></html>"""


def _files(logo="Tajbojo", flogo="Tajbojo"):
    return {"index.php": PAGE.format(logo=logo, flogo=flogo)}


def _with_name(name):
    """Еталонна назва вітки (None → назва не виводиться, чек мовчить)."""
    mod._expected = lambda branch, files=None: (name or "")


# ------------------------------------------------------------------- run

def test_mismatch_flagged():
    _with_name("Schlusseltx")
    issues = mod.run_branch(_files(), [], "br")
    assert len(issues) == 1
    i = issues[0]
    assert i["severity"] == "error" and i["path"] == "index.php"
    assert "Tajbojo" in i["message"] and "Schlusseltx" in i["message"]
    assert "назва сайту" in i["message"]


def test_match_is_silent_case_and_diacritics():
    _with_name("Tajbojo")
    assert mod.run_branch(_files(), [], "br") == []
    # діакритика, пробіли і двослівна назва не заважають збігу
    _with_name("Anfixu Blurfi")
    assert mod.run_branch(_files(logo="\u00c1nfixu Blurfi"), [], "br") == []


def test_no_name_silent():
    _with_name(None)
    assert mod.run_branch(_files(), [], "br") == []
    assert mod.fix_branch(_files(), [], "br") == []


def test_placeholder_logo_skipped():
    _with_name("Schlusseltx")
    assert mod.run_branch(_files(logo="{{DOMAIN}}"), [], "br") == []
    assert mod.run_branch(_files(logo="{{DOMAIN_NAME}}"), [], "br") == []


def test_image_only_logo_warns():
    _with_name("Schlusseltx")
    issues = mod.run_branch(_files(logo='<img src="logo.png" alt="">'), [], "br")
    assert len(issues) == 1 and issues[0]["severity"] == "warn"
    assert "Schlusseltx" in issues[0]["message"]
    assert mod.fix_branch(_files(logo='<img src="logo.png" alt="">'), [], "br") == []


def test_page_without_header_has_no_logo_verdict():
    _with_name("Schlusseltx")
    files = {"cookie-policy.html": "<html><body><h1>Cookies</h1></body></html>"}
    assert mod.run_branch(files, [], "br") == []


def test_real_branch_name_derives_the_expectation():
    """Без підміни: nwf-префікса тут немає, назва йде з самої вітки."""
    mod._expected = mod.__class__ if False else mod._expected      # no-op guard
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location(
        "ld_fresh", pathlib.Path(__file__).resolve().parent.parent
        / "checks" / "logo_domain.py")
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    issues = fresh.run_branch(_files(logo="Chuzha Nazva"),
                              [], "borhe-ansabu-it-it")
    assert len(issues) == 1 and "Borhe Ansabu" in issues[0]["message"], issues


# ------------------------------------------------------------------- fix

def test_fix_replaces_header_footer_and_renames_sitewide():
    _with_name("Schlusseltx")
    acts = mod.fix_branch(_files(), [], "br")
    assert len(acts) == 1 and acts[0]["type"] == "edit"
    new = acts[0]["content"]
    # хедер + лого футера + згадка у контенті (<h1>Consultoria Tajbojo</h1>)
    assert new.count("Schlusseltx") == 3, new
    assert "Consultoria Schlusseltx" in new         # rename по всьому сайту
    assert 'fa-anchor' in new                       # іконка лишилась
    assert "In\u00edcio" in new                     # нав-лінк футера не зачеплено
    assert "Tajbojo" not in new
    # після фіксу чек чистий
    assert mod.run_branch({"index.php": new}, [], "br") == []
    assert mod.fix_branch({"index.php": new}, [], "br") == []


def test_fix_span_split_logo():
    _with_name("Schlusseltx")
    acts = mod.fix_branch(_files(logo='Tar<span class="text-red">rafa</span>'), [], "br")
    new = acts[0]["content"]
    assert "Schlusseltx" in new and "rafa</span>" not in new
    assert "<span" in new                           # структура збережена
    assert mod.run_branch({"index.php": new}, [], "br") == []


def test_fix_mirrors_caps_and_titles_lowercase():
    _with_name("Schlusseltx")
    up = mod.fix_branch(_files(logo="TAJBOJO", flogo="TAJBOJO"), [], "br")[0]["content"]
    assert "SCHLUSSELTX" in up
    # lowercase-лого отримує канонічний Title-правопис назви: назва — власна
    # назва, писати її з малої не було б чим виправдати
    low = mod.fix_branch(_files(logo="tajbojo", flogo="tajbojo"), [], "br")[0]["content"]
    assert "Schlusseltx" in low, low


def test_fix_noop_when_matches():
    _with_name("Tajbojo")
    assert mod.fix_branch(_files(), [], "br") == []


def test_fix_writes_latin_logo_from_diacritic_name():
    # кейс «Câmera Alves»: напис лого — строгою латиницею, БЕЗ â;
    # прозові згадки (rename по сайту) лишаються з правильною діакритикою
    _with_name("Câmera Alves")
    assert mod.run_branch(_files(logo="Camera Alves", flogo="Camera Alves"),
                          [], "br") == [], "латинське лого — та сама назва"
    new = mod.fix_branch(_files(), [], "br")[0]["content"]
    assert "Camera Alves" in new, new                  # напис лого
    assert "Consultoria Câmera Alves" in new, new      # проза — з діакритикою
    header = new.split("</header>")[0]
    assert "Câmera" not in header, header


def test_footer_logo_with_other_text_untouched():
    # у футері інший текст (не бренд) — лого-фікс чіпає тільки хедер
    _with_name("Schlusseltx")
    acts = mod.fix_branch(_files(flogo="Sobre a empresa"), [], "br")
    new = acts[0]["content"]
    # хедер + rename згадки у <h1>; футерний текст лишився
    assert new.count("Schlusseltx") == 2, new
    assert "Sobre a empresa" in new


def test_multipage_rename_and_idempotent():
    _with_name("Brevonext")
    files = {"index.php": PAGE.format(logo="Tajbojo", flogo="Tajbojo"),
             "company.html": PAGE.format(logo="Tajbojo", flogo="Tajbojo"),
             "privacy.html": "<html><body><p>© Tajbojo. "
                             '<a href="https://fb.com/tajbojo">fb</a></p>'
                             "</body></html>",
             "robots.txt": "User-agent: *"}
    acts = mod.fix_branch(files, [], "br")
    assert {a["path"] for a in acts} == {"index.php", "company.html",
                                         "privacy.html"}
    fixed = dict(files)
    for a in acts:
        fixed[a["path"]] = a["content"]
    # сторінка без хедера теж перейменована, слаг у лінку цілий
    assert "© Brevonext." in fixed["privacy.html"]
    assert "fb.com/tajbojo" in fixed["privacy.html"]
    assert all("Tajbojo" not in fixed[p] for p in
               ("index.php", "company.html", "privacy.html"))
    assert mod.fix_branch(fixed, [], "br") == []    # ідемпотентність
    assert mod.run_branch(fixed, [], "br") == []


# --------------------------------------------- декоративні глифи в лого
def test_numeric_entity_glyph_does_not_break_match():
    """Реальний фолс із neodadu-ar-es: лого «<span>&#9670;</span> Neurovagigab».
    Ентіті не декодувалось, у порівняння затікали цифри."""
    _with_name("Neurovagigab")
    files = {"index.php": PAGE.format(
        logo='<span class="text-lg">&#9670;</span>\n    Neurovagigab',
        flogo='<span>&#9670;</span> Neurovagigab')}
    assert mod.run_branch(files, [], "br") == []
    assert mod.fix_branch(files, [], "br") == [], "правильне лого не чіпаємо"


def test_named_entity_glyph_does_not_break_match():
    _with_name("Anfixu Blurfi")
    files = {"index.php": PAGE.format(logo="&bull; Ánfixu Blurfi",
                                      flogo="&bull; Ánfixu Blurfi")}
    assert mod.run_branch(files, [], "br") == []


def test_entity_glyph_with_wrong_brand_is_still_flagged():
    """Глиф не мусить ставати щитом: назва все одно чужа і фіксається."""
    _with_name("Schlusseltx")
    files = {"index.php": PAGE.format(
        logo='<span class="text-lg">&#9670;</span>\n    Tajbojo',
        flogo='<span>&#9670;</span> Tajbojo')}
    issues = mod.run_branch(files, [], "br")
    assert len(issues) == 1, issues
    acts = mod.fix_branch(files, [], "br")
    assert acts, "чуже лого мусить фіксатись"
    out = acts[0]["content"]
    # хедер + футер + rename у <h1>
    assert out.count("Schlusseltx") == 3, out
    assert "Consultoria Schlusseltx" in out
    assert out.count("&#9670;") == 2, "декоративні глифи лишаються на місці"


# ------------------------------------------- бейдж-монограма (кейс lefxgo-my-en)
BADGE_PAGE = """<html><body>
<header>
  <a href="./" class="flex items-center gap-2 flex-shrink-0">
    <div class="w-8 h-8 rounded-md flex items-center justify-center" style="background:#213A50;">
      <span class="text-white font-headers font-bold text-lg">{mono}</span>
    </div>
    <span class="font-headers font-semibold text-xl" style="color:#213A50;">{word}</span>
  </a>
</header>
<footer>
  <a href="./" class="flex items-center gap-2">
    <div class="w-8 h-8 rounded-md"><span class="text-white font-bold text-lg">{mono}</span></div>
    <span class="font-headers font-semibold text-xl text-white">{word}</span>
  </a>
</footer>
</body></html>"""


def _badge(mono="L", word="Lefxgo"):
    return {"index.php": BADGE_PAGE.format(mono=mono, word=word)}


def test_badge_plus_wordmark_matching_name_is_clean():
    _with_name("Lefxgo")
    assert mod.run_branch(_badge(), [], "br") == []
    assert mod.fix_branch(_badge(), [], "br") == []


def test_badge_is_not_the_wordmark_container():
    """Фікс кладе назву у СЛОВО, а в бейдж — лише першу літеру."""
    _with_name("Lefxgo")
    acts = mod.fix_branch(_badge(word="Sereia"), [], "br")
    out = acts[0]["content"]
    assert ">L</span>" in out, out            # бейдж лишився однолітерним
    assert ">Lefxgo</span>" in out, out       # назва — у своєму контейнері
    assert ">Lefxgo</span>\n    </div>" not in out, "назва потрапила в бейдж"
    assert "Sereia" not in out


def test_badge_letter_is_realigned_when_wordmark_already_right():
    _with_name("Lefxgo")
    issues = mod.run_branch(_badge(mono="X"), [], "br")
    assert len(issues) == 1 and issues[0]["severity"] == "error"
    assert "бейдж" in issues[0]["message"]
    out = mod.fix_branch(_badge(mono="X"), [], "br")[0]["content"]
    assert ">L</span>" in out and "X" not in out
    assert out.count("Lefxgo") == 2, "назва хедера і футера лишились на місці"


def test_badge_fix_touches_footer_logo_too():
    _with_name("Lefxgo")
    out = mod.fix_branch(_badge(word="Sereia"), [], "br")[0]["content"]
    assert out.count(">Lefxgo</span>") == 2, out
    assert out.count(">L</span>") == 2, out


def test_single_letter_logo_without_wordmark_is_not_a_badge():
    """Лого з однієї літери і без слова — це САМЕ лого, а не бейдж."""
    _with_name("Lefxgo")
    files = {"index.php": "<html><body><header>"
                          "<a href=\"./\"><span>S</span></a>"
                          "</header></body></html>"}
    out = mod.fix_branch(files, [], "br")[0]["content"]
    assert ">Lefxgo</span>" in out, out


# --------------------------- зіпсовані назви ловляться і без правил хвоста
def test_prefix_eaten_logo_is_flagged():
    """У лого з'їдена перша літера («uintara» ← «Quintaraa») — чужа назва."""
    _with_name("Quintaraa")
    issues = mod.run_branch(_files(logo="uintara", flogo="uintara"), [], "br")
    assert len(issues) == 1 and issues[0]["severity"] == "error"
    assert "Quintaraa" in issues[0]["message"]


def test_transposed_letters_are_still_flagged():
    _with_name("Ancorsis")
    issues = mod.run_branch(_files(logo="AncorisLOCAÇÃO DE VEÍCULOS"), [], "br")
    assert len(issues) == 1 and issues[0]["severity"] == "error"


def test_badge_is_realigned_even_when_wordmark_matches():
    """Назва правильна, бейдж чужий — правимо лише бейдж."""
    _with_name("Lefxgo")
    issues = mod.run_branch(_badge(mono="X"), [], "br")
    assert len(issues) == 1 and "бейдж" in issues[0]["message"]
    out = mod.fix_branch(_badge(mono="X"), [], "br")[0]["content"]
    assert ">Lefxgo</span>" in out and ">L</span>" in out


# ------------------------------- багатолітерна монограма (кейс sataa-noku)
SATAA = """<html><body>
<header>
  <a href="./" class="flex items-center gap-2 no-underline">
    <span class="inline-flex items-center justify-center w-9 h-9 rounded bg-teal\
 text-sheet font-bold text-sm">{mono}</span>
    <span class="font-headers font-bold text-teal text-lg">{word}</span>
  </a>
</header>
</body></html>"""


def _sabia(mono="S9", word="Sataá Noku"):
    return {"index.php": SATAA.format(mono=mono, word=word)}


def test_multichar_badge_in_square_is_not_the_wordmark():
    """«S9» у w-9 h-9 — монограма, а не початок назви; назва «Sataá Noku»
    збігається з назвою вітки (sataa-noku) попри діакритику."""
    _with_name("Sataa Noku")
    assert mod.run_branch(_sabia(), [], "br") == []
    # а от чужа назва у слові — error, і назва їде у СВІЙ span
    issues = mod.run_branch(_sabia(word="Parra Graf"), [], "br")
    assert len(issues) == 1
    assert "«Parra Graf»" in issues[0]["message"], issues[0]["message"]
    out = mod.fix_branch(_sabia(word="Parra Graf"), [], "br")[0]["content"]
    assert ">S9</span>" in out, out            # бейдж не чіпали
    assert ">Sataa Noku</span>" in out, out
    assert mod.run_branch({"index.php": out}, [], "br") == []
    assert mod.fix_branch({"index.php": out}, [], "br") == []


def test_badge_kept_when_its_first_letter_still_matches():
    _with_name("Sabianov")
    out = mod.fix_branch(_sabia(word="Sabianov"), [], "br")
    assert out == []


def test_multichar_badge_with_wrong_letter_is_realigned():
    _with_name("Zenith")
    out = mod.fix_branch(_sabia(mono="S9", word="Zenith"), [], "br")[0]["content"]
    assert ">Z</span>" in out and ">S9</span>" not in out


def test_badge_recognised_by_initials_without_square():
    """«BD» + «Bacatá Digital»: квадрата немає, але бейдж — ініціали."""
    _with_name("Bacata Digital")
    page = ("<html><body><header><a href=\"./\">"
            "<span class=\"font-mono text-lg\">BD</span>"
            "<span class=\"text-xl\">Bacatá Digital</span>"
            "</a></header></body></html>")
    assert mod.run_branch({"index.php": page}, [], "br") == []


def test_badge_recognised_by_short_prefix_without_square():
    _with_name("Aubahbu")
    page = ("<html><body><header><a href=\"./\">"
            "<span class=\"mono-tag text-lg\">AU</span>"
            "<span class=\"text-xl\">Aubahbu</span>"
            "</a></header></body></html>")
    assert mod.run_branch({"index.php": page}, [], "br") == []


def test_two_span_name_is_joined_with_a_space():
    """«BS» + «Bashaóp»/«Secisi» у двох окремих span: частини склеюються
    ЧЕРЕЗ ПРОБІЛ, інакше ініціали не збігаються і бейдж їде у коробку."""
    _with_name("Bashaop Secisi")
    page = ("<html><body><header><a href=\"./\">"
            "<span class=\"font-mono\">BS</span>"
            "<span class=\"text-xl\">Bashaóp</span>"
            "<span class=\"text-xl\">Secisi</span>"
            "</a></header></body></html>")
    assert mod.run_branch({"index.php": page}, [], "br") == []
    # і в тексті вердикту назва читається як назва, а не злиплим словом
    _with_name("Zenithx")
    msg = mod.run_branch({"index.php": page}, [], "br")[0]["message"]
    assert "«Bashaóp Secisi»" in msg, msg


def test_split_wordmark_is_not_a_badge():
    """«Advo»+«cta» і «Alto»+«Nest» складаються у назву — це НЕ монограма."""
    for a, b in (("Advo", "cta"), ("Alto", "Nest")):
        _with_name("Zenithx")
        page = ("<html><body><header><a href=\"./\">"
                f"<span class=\"text-2xl\">{a}</span>"
                f"<span class=\"text-2xl\">{b}</span>"
                "</a></header></body></html>")
        issues = mod.run_branch({"index.php": page}, [], "br")
        assert len(issues) == 1, (a, b, issues)
        out = mod.fix_branch({"index.php": page}, [], "br")[0]["content"]
        assert ">Zenithx</span>" in out, out       # назва у першому вузлі
        assert f">{a}</span>" not in out, out      # старий шматок затерто
        assert f">{b}</span>" not in out, out


# ----------------------------- ремонт лого, вже покаліченого старим фіксом
CRAMPED = """<html><body>
<header>
  <a href="./" class="flex items-center gap-3">
    <span class="w-8 h-8 bg-amber flex items-center justify-center font-bold">{mono}</span>
    <span style="font-size: 20px; font-weight: 600;">{word}</span>
  </a>
</header>
</body></html>"""


def test_word_crammed_into_square_badge_is_reported_and_moved_back():
    _with_name("Almadeirk")
    files = {"index.php": CRAMPED.format(mono="Almadeirk", word="")}
    issues = mod.run_branch(files, [], "br")
    assert len(issues) == 1 and issues[0]["severity"] == "error"
    assert "обрізається" in issues[0]["message"]
    out = mod.fix_branch(files, [], "br")[0]["content"]
    assert ">A</span>" in out, out                       # у бейджі — літера
    assert ">Almadeirk</span>" in out, out               # назва повернулась
    assert mod.run_branch({"index.php": out}, [], "br") == []
    assert mod.fix_branch({"index.php": out}, [], "br") == []


def test_whitespace_only_slot_also_counts_as_emptied():
    _with_name("Cadencia")
    files = {"index.php": CRAMPED.format(mono="Cadencia", word=" ")}
    out = mod.fix_branch(files, [], "br")[0]["content"]
    assert ">C</span>" in out and ">Cadencia</span>" in out


def test_short_badge_in_square_is_not_treated_as_damage():
    _with_name("Anzakuz")
    files = {"index.php": CRAMPED.format(mono="AND", word="Anzakuz")}
    assert mod.run_branch(files, [], "br") == []


def test_long_word_without_square_is_not_damage():
    _with_name("Almadeirk")
    page = ("<html><body><header><a href=\"./\">"
            "<span class=\"text-xl\">Almadeirk</span>"
            "<span class=\"text-xl\"></span>"
            "</a></header></body></html>")
    assert mod.run_branch({"index.php": page}, [], "br") == []


# --------------------------------- лого без посилання (<h1> у хедері)
H1_PAGE = """<html><body>
<header class="bg-white shadow-lg sticky top-0">
  <div class="flex items-center space-x-3">
    <svg class="w-10 h-10"><path d="M18 2"/></svg>
    <div><h1 class="text-2xl font-bold">{logo}</h1>
         <p class="text-sm">Autovermietung</p></div>
  </div>
  <nav class="hidden md:flex">
    <a href="./" class="font-semibold">{nav}</a>
    <a href="./services.html">Dienstleistungen</a>
  </nav>
</header>
<main><h2>Hallo</h2></main>
</body></html>"""


def test_unlinked_h1_beats_nav_home_link():
    """Бренд стоїть у <h1> без посилання, а перший `href="./"` — пункт
    МЕНЮ, чий текст якраз збігається з назвою."""
    _with_name("Familycarre")
    files = {"index.php": H1_PAGE.format(logo="AlpenFamilie", nav="Familycarre")}
    issues = mod.run_branch(files, list(files), "fazikg-cag-rectem-ch-de")
    assert len(issues) == 1, issues
    assert "AlpenFamilie" in issues[0]["message"], issues


def test_unlinked_h1_matching_name_is_silent():
    _with_name("Familycarre")
    files = {"index.php": H1_PAGE.format(logo="Familycarre", nav="Familycarre")}
    assert mod.run_branch(files, list(files), "fazikg-cag-rectem-ch-de") == []


def test_h1_inside_home_link_keeps_the_link_and_its_badge():
    _with_name("Lefxgo")
    src = ('<header><a href="./"><span class="w-9 h-9">L</span>'
           '<h1>Wrongbrand</h1></a></header>')
    files = {"index.php": src}
    issues = mod.run_branch(files, list(files), "lefxgo-my-en")
    assert len(issues) == 1, issues
    acts = mod.fix_branch(files, list(files), "lefxgo-my-en")
    out = acts[0]["content"]
    assert ">L</span>" in out, "бейдж затерли: " + out
    assert "Lefxgo" in out, out


def test_h1_inside_link_still_sees_the_wrong_badge_letter():
    _with_name("Lefxgo")
    src = ('<header><a href="./"><span class="w-9 h-9">X</span>'
           '<h1>Lefxgo</h1></a></header>')
    files = {"index.php": src}
    issues = mod.run_branch(files, list(files), "lefxgo-my-en")
    assert len(issues) == 1, issues
    assert "бейдж" in issues[0]["message"], issues


def test_placeholder_h1_is_still_skipped():
    _with_name("Familycarre")
    files = {"index.php": H1_PAGE.format(logo="{{DOMAIN_NAME}}", nav="Familycarre")}
    assert mod.run_branch(files, list(files), "fazikg-cag-rectem-ch-de") == []


# ------------------------------------ home-лінк як компонент роутера
NUXT = """<template>
<header class="navigation">
  <NuxtLink :to="localePath('/')" class="navigation__logo">
    <span class="navigation__logo-text">{logo}</span>
  </NuxtLink>
  <nav><NuxtLink :to="localePath('/blog')">Blog</NuxtLink></nav>
</header>
</template>"""


def test_nuxt_component_home_link_is_a_logo():
    _with_name("Apojgenc")
    files = {"components/Navigation.vue": NUXT.format(logo="PassoBjip")}
    issues = mod.run_branch(files, list(files), "apoj-gencaa-br-pt")
    assert len(issues) == 1 and "PassoBjip" in issues[0]["message"], issues


def test_next_component_home_link_is_a_logo():
    _with_name("Blitsxeqq")
    src = ('<header><Link href="/" className="font-display">'
           '<span>PARRA</span><span>GRAF</span></Link></header>')
    files = {"src/components/Header.tsx": src}
    assert len(mod.run_branch(files, list(files), "blitsxeqq-ch-de")) == 1


def test_interpolated_logo_is_not_judged_or_fixed():
    _with_name("Apojgenc")
    files = {"components/Navigation.vue": NUXT.format(logo="{{ t('nav.brand') }}")}
    assert mod.run_branch(files, list(files), "apoj-gencaa-br-pt") == []
    assert mod.fix_branch(files, list(files), "apoj-gencaa-br-pt") == []


def test_non_home_component_link_is_not_a_logo():
    _with_name("Apojgenc")
    src = '<header><NuxtLink :to="localePath(\'/blog\')">PassoBjip</NuxtLink></header>'
    files = {"components/Nav.vue": src}
    assert mod.run_branch(files, list(files), "apoj-gencaa-br-pt") == []



# ------------------------------------------- машинні мітки (LogoLoom-кейс)

def test_pathified_svg_logo_with_matching_aria_label_is_silent():
    """Кейс epidoc 02.10: wordmark text→path — видимого тексту нема, але
    aria-label SVG несе назву. Збіг (навіть зі слоганом-хвостом) — тихо."""
    _with_name("Epidoc")
    files = _files(logo='<img data-logo src="logo-dark.svg" '
                        'alt="Epidoc - Auto d\u2019epoca">',
                   flogo="Epidoc")
    files["logo-dark.svg"] = ('<svg xmlns="http://www.w3.org/2000/svg" '
                              'aria-label="Epidoc" viewBox="0 0 357 100">'
                              '<path d="M0 0h10"/></svg>')
    assert mod.run_branch(dict(files), list(files)) == []


def test_pathified_svg_logo_with_foreign_label_is_error():
    _with_name("Epidoc")
    files = _files(logo='<img data-logo src="logo-dark.svg" alt="Milanese">',
                   flogo="Epidoc")
    files["logo-dark.svg"] = ('<svg aria-label="Milanese Motors">'
                              '<path d="M0 0h10"/></svg>')
    issues = mod.run_branch(dict(files), list(files))
    assert len(issues) == 1 and issues[0]["severity"] == "error", issues
    assert "aria-label/alt" in issues[0]["message"], issues


def test_unlabeled_image_logo_still_warns():
    _with_name("Epidoc")
    files = _files(logo='<img data-logo src="logo-dark.png">',
                   flogo="Epidoc")
    issues = mod.run_branch(dict(files), list(files))
    assert len(issues) == 1 and issues[0]["severity"] == "warn", issues
    assert "вручну" in issues[0]["message"]

def test_alt_with_html_entity_matches_the_name():
    """semence ch-fr (27.10): alt="Semence Formations &amp; Conseil Sàrl" ≠
    «Semence Formations & Conseil Sàrl» — 10 помилок через нерозкодований
    ентіті. Машинний напис порівнюється розкодованим."""
    _with_name("Semence Formations & Conseil Sàrl")
    files = _files(logo='<img data-logo src="logo.png" alt="Semence Formations &amp; Conseil S&agrave;rl">', flogo="Semence")
    assert mod.run_branch(dict(files), list(files)) == []


def test_label_that_starts_with_the_name_plus_a_descriptor_matches():
    """lamubde-viopa br-pt (TECH-29416, 27.10): alt="Lamubde Viopa Adgugenae",
    назва вітки «Lamubde Viopa» — бренд + рід діяльності без роздільника;
    7 хибних «виправ лого вручну». Голова з такої ж кількості слів = збіг."""
    _with_name("Lamubde Viopa")
    files = _files(logo='<img data-logo src="logo.png" alt="Lamubde Viopa Adgugenae">', flogo="Lamubde Viopa")
    assert mod.run_branch(dict(files), list(files), "lamubde-viopa-adgugenae-br-pt") == []
    # а чужий бренд з таким самим хвостом — ні
    files = _files(logo='<img data-logo src="logo.png" alt="Souza Viopa Advocacia">', flogo="Lamubde Viopa")
    assert mod.run_branch(dict(files), list(files), "lamubde-viopa-adgugenae-br-pt")[0]["severity"] == "error"

def test_label_head_before_fullwidth_bar_matches_the_name():
    """antepiu-nerg jp (27.10): alt «ANTEPIU NERG｜杉並のアンティーク家具の修復とお手入れ»
    — назва + слоган за японською рискою; голова до «｜» — збіг."""
    _with_name("ANTEPIU NERG")
    files = _files(logo='<img data-logo src="logo.png" alt="ANTEPIU NERG｜杉並のアンティーク家具の修復とお手入れ">', flogo="ANTEPIU NERG")
    assert mod.run_branch(dict(files), list(files)) == []



def test_text_logo_with_tagline_after_the_bar_matches_the_name():
    """hajipo-kabe jp (27.10): текстове лого (Wix h1) «ハルノ家具修理店｜江戸川区の
    アンティーク家具の修理・修復» — назва + слоган; голова до «｜» = назва — тихо,
    без перейменування по сайту."""
    _with_name("ハルノ家具修理店")
    files = _files(logo="ハルノ家具修理店｜江戸川区のアンティーク家具の修理・修復", flogo="ハルノ家具修理店")
    assert mod.run_branch(dict(files), list(files), "hajipo-kabe-jp-jp") == []
    assert mod.fix_branch(dict(files), list(files), "hajipo-kabe-jp-jp") == []
    # а чужа назва зі слоганом — як і була, помилка
    _with_name("Zenithx")
    assert mod.run_branch(_files(logo="Tajbojo | Loja de Pianos", flogo="Tajbojo"), [], "br")[0]["severity"] == "error"


def test_latin_logo_against_cjk_name_is_a_manual_warning_not_a_rename():
    """hahuli-koce jp (27.10): текстове лого «Hahuli Koce», назва вітки
    «葉月工房» — одне й те саме різними письмами; «фікс перейменує по всьому
    сайту» затер би латинське лого. Різні системи письма — лише warn, фікс
    порожній."""
    _with_name("葉月工房")
    files = _files(logo="Hahuli Koce", flogo="Hahuli Koce")
    issues = mod.run_branch(dict(files), list(files), "hahuli-koce-jp-jp")
    assert len(issues) == 1 and issues[0]["severity"] == "warn" and "вручну" in issues[0]["message"], issues
    assert mod.fix_branch(dict(files), list(files), "hahuli-koce-jp-jp") == []



def test_subpage_logo_link_to_parent_root_is_the_logo_not_the_menu_item():
    """rezmeufiriafkupul /about 21.10: лого веде на «../», а перший «home-лінк»
    за старим регексом — пункт меню href="index.html" (сама сторінка)."""
    page = ('<html><head><title>Sobre – Rezmeufiría Fkupul</title></head><body><header>'
            '<a href="../" class="custom-logo-link"><img alt="Rezmeufiría Fkupul" src="../logo.png"></a>'
            '<nav><a class="menu-link" href="index.html">Sobre</a><a href="../services/index.html">Serviços</a></nav>'
            '</header><main></main></body></html>')
    s_, e_, html = mod._page_logo(page)
    assert 'class="custom-logo-link"' in html and "menu-link" not in html


if __name__ == "__main__":
    run(dict(globals()))
