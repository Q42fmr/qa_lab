"""site_name: назва з вітки і перейменування по сайту.

Позитиви взяті з ClickUp (колонки «Вайт» ↔ «Название» групи TECH-28476) і
з живої вітки nwf-chovfuce-eszbufefaa-br-pt: 18 повних форм, 21 коротка,
плюс соцлінки/хендли, які чіпати не можна.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                               # noqa: E402

sys.path.insert(0, str(ROOT))

import site_name                                             # noqa: E402


def test_expected_matches_the_clickup_table():
    # TECH-28476: колонка «Вайт» ↔ колонка «Название», 1:1
    for br, name in [("borhe-ansabu-it-it", "Borhe Ansabu"),
                     ("madu-esratpu-it-it", "Madu Esratpu"),
                     ("megecue-vija-it-it", "Megecue Vija"),
                     ("orahine-cupoku-it-it", "Orahine Cupoku"),
                     ("tatoto-vija-it-it", "Tatoto Vija")]:
        assert site_name.expected(br) == name, br


def test_expected_strips_the_nwf_prefix():
    assert site_name.expected("nwf-chovfuce-eszbufefaa-br-pt") == "Chovfuce Eszbufefaa"


def test_expected_drops_the_batch_number():
    # choa-nono-br-pt-2 (28.10): «-2» — номер партії, не слово назви
    assert site_name.expected("choa-nono-br-pt-2") == "Choa Nono"


def test_expected_survives_odd_input():
    assert site_name.expected("") == ""
    assert site_name.expected("solo") == "Solo"
    assert site_name.expected("br-pt") == ""          # сама локаль — назви немає


def _idx(title: str) -> dict:
    return {"index.html": f"<html><head><title>{title}</title></head></html>"}


def test_title_head_is_the_name():
    # кейс зі скріна: «Название» ClickUp = голова title, не назва вітки
    files = _idx("Motor de Classe - Luxo discreto para cada viagem.")
    assert site_name.expected("nwf-corleone-motori-it-it", files) == "Motor de Classe"


def test_title_splitters_and_entities():
    assert site_name.from_title(_idx("Sataá Noku — estúdio")) == "Sataá Noku"
    assert site_name.from_title(_idx("Cagu Vemme | Imóveis")) == "Cagu Vemme"
    assert site_name.from_title(_idx("Atelier N&amp;B – photo")) == "Atelier N&B"
    # роздільник без пробілів — не роздільник (дефісні назви цілі)
    assert site_name.from_title(_idx("Al-Waha")) == "Al-Waha"


def test_japanese_titles_split_on_fullwidth_bar_and_skip_page_words():
    """jp-jp (26.10): «桐乃屋｜家具の修理・修復» — роздільник ｜ без пробілів, тож
    назвою ставав увесь title; «ホーム｜…» — «Головна» по-японськи."""
    assert site_name.from_title(_idx("桐乃屋｜家具の修理・修復")) == "桐乃屋"
    assert site_name.from_title(_idx("個人情報保護方針｜ORTUN SQIOHA | ORTUN SQIOHA")) == "ORTUN SQIOHA"
    assert site_name.from_title({"index.php": "<title>ホーム｜木庵</title>"}, "mohiol-jp-jp") == "木庵"


def test_title_falls_back_to_branch():
    long = "Luxo discreto para cada viagem que a sua família merece fazer"
    for files in (None, {}, _idx(""), _idx("{{ site.title }}"), _idx(long)):
        assert site_name.expected("borhe-ansabu-it-it", files) == "Borhe Ansabu", files


def test_title_of_shallowest_index_wins():
    files = {"dist/index.html": "<title>Stale Build — x</title>",
             "index.php": "<html><head><title>Borhe Ansabu — cucina</title></head>"}
    assert site_name.from_title(files) == "Borhe Ansabu"


def test_page_dash_site_titles_resolve_to_the_repeating_part():
    # кейс tubiepa 30.09: «Сторінка — Сайт» на кожній сторінці; голова
    # index-а — «Início» («Головна»), і саме її фікс ледь не вписав у лого
    files = {
        "index.php": "<title>Início — Locação de Veículos de Luxo | Tubiepa</title>",
        "about.html": "<title>Sobre Nós — Tubiepa</title>",
        "contact.html": "<title>Contato — Tubiepa</title>",
    }
    assert site_name.expected("tubiepa-br-pt", files) == "Tubiepa"
    # навіть без збігу з назвою вітки консенсус перемагає
    assert site_name.from_title(files) == "Tubiepa"


def test_single_page_tail_matching_branch_beats_head():
    files = {"index.php": "<title>Início — Tubiepa</title>"}
    assert site_name.expected("tubiepa-br-pt", files) == "Tubiepa"
    # і без підказки вітки: «Início» — сторінкове слово, не кандидат
    assert site_name.from_title(files) == "Tubiepa"


def test_meta_name_is_a_fallback_when_titles_are_useless():
    files = {"index.html": ('<head><title>{{ title }}</title>'
                            '<meta name="application-name" content="Tubiepa">'
                            '</head>')}
    assert site_name.expected("some-other-br-pt", files) == "Tubiepa"



def test_rename_never_doubles_when_new_contains_old():
    # кейс quuskafs-ch-fr 01.10: «Quumvuv» → «Quumvuv Sàrl», а вже повні
    # входження роздувались до «Quumvuv Sàrl Sàrl»
    src = ('<title>À propos — Quumvuv, monnaies</title>\n'
           '<meta name="author" content="Quumvuv Sàrl">\n'
           '<meta name="description" content="Quumvuv Sàrl, basée à Sion">\n'
           '<p>© 2026 Quumvuv</p>')
    out = site_name.rename(src, "Quumvuv", "Quumvuv Sàrl")
    assert "À propos — Quumvuv Sàrl, monnaies" in out, out
    assert 'content="Quumvuv Sàrl"' in out, out
    assert "Sàrl Sàrl" not in out, out
    assert "© 2026 Quumvuv Sàrl" in out, out
    # ідемпотентність: другий прогін нічого не міняє
    assert site_name.rename(out, "Quumvuv", "Quumvuv Sàrl") == out


def test_latin_strips_diacritics_for_logo_writing():
    # кейс 30.09: лого пишеться ТІЛЬКИ латиницею, без символів над буквами
    assert site_name.latin("Câmera Alves") == "Camera Alves"
    assert site_name.latin("Reqerûxsoe Fije") == "Reqeruxsoe Fije"
    assert site_name.latin("Müller & Keller") == "Muller & Keller"
    assert site_name.latin("São João Imóveis") == "Sao Joao Imoveis"
    assert site_name.latin("Straße Nørd") == "Strasse Nord"


def test_latin_drops_non_latin_scripts_entirely():
    assert site_name.latin("مكتب المحاماة") == ""        # арабська
    assert site_name.latin("東京スタジオ") == ""           # азійські знаки
    assert site_name.latin("Юрист Плюс") == ""           # кирилиця
    assert site_name.latin("Дім Deluxe") == "Deluxe"     # лишається латинська частина


def test_latin_logo_spelling_equals_diacritic_title():
    # симетрія: латинське лого проти діакритичного еталона — та сама назва,
    # фікс НЕ сміє переписувати «Camera Alves» на «Câmera Alves»
    assert site_name.same("Camera Alves", "Câmera Alves")
    assert site_name.same("Câmera Alves", "Camera Alves")


def test_rename_replaces_full_and_lone_forms_keeping_case():
    src = ("<title>Chovfuce Eszbuféfaa — consultoria</title>\n"
           "<p>Na Chovfuce, cada projeto…</p>\n"
           "<h2>CHOVFUCE ESZBUFÉFAA</h2>\n")
    out = site_name.rename(src, "Chovfuce Eszbuféfaa", "Borhe Ansabu")
    assert "<title>Borhe Ansabu — consultoria</title>" in out, out
    assert "Na Borhe, cada projeto" in out, out
    assert "<h2>BORHE ANSABU</h2>" in out, out
    assert "Chovfuce" not in out, out


def test_rename_never_touches_slugs_handles_and_emails():
    src = ("https://facebook.com/chovfuceeszbufefaa\n"
           "https://linkedin.com/company/chovfuce-eszbufefaa\n"
           "@chovfuceesz contato@chovfuce.com.br\n"
           '"name": "chovfuce-eszbufefaa"\n')
    assert site_name.rename(src, "Chovfuce Eszbuféfaa", "Borhe Ansabu") == src


def test_rename_respects_word_boundaries():
    src = "AChovfuceB Chovfuce-Eszbufefaa post-Chovfuce"
    out = site_name.rename(src, "Chovfuce Eszbuféfaa", "Borhe Ansabu")
    assert out == src, out                     # приклеєні форми — не назва


def test_rename_multiline_phrase_is_still_one_name():
    src = "<span>\n  Chovfuce\n  Eszbuféfaa\n</span>"
    out = site_name.rename(src, "Chovfuce Eszbuféfaa", "Borhe Ansabu")
    assert "Borhe Ansabu" in out and "Chovfuce" not in out, out


def test_short_lone_word_is_not_renamed_alone():
    # standalone «DJ» — надто ймовірний випадковий збіг; повна фраза — так
    src = "DJ set à noite. DJ Momento é a casa."
    out = site_name.rename(src, "DJ Momento", "Casa Nova")
    assert out == "DJ set à noite. Casa Nova é a casa.", out


def test_lone_brand_of_legal_suffixed_name_takes_the_whole_new_name():
    """baggoetiepohsa 20.10: консенсус дав «Laovalerie Ltda» (legal-сторінки),
    а в title головної — голе «Laovalerie». Lone-гілка підставляла перше
    слово нової назви → «Barbearia | …». Коли бренд старої — одне слово
    (решта юр. хвіст), lone-форма = весь новий бренд."""
    src = ("<title>Laovalerie | Tesoura e navalha na Torre, Recife</title>\n"
           "<p>© 2026 Laovalerie Ltda</p><p>Na Laovalerie você…</p>")
    out = site_name.rename(src, "Laovalerie Ltda", "Baggoetie Pohsa")
    assert "<title>Baggoetie Pohsa | Tesoura" in out, out
    assert "© 2026 Baggoetie Pohsa</p>" in out and "Na Baggoetie Pohsa você" in out, out
    # нова назва теж з юр. хвостом — одиночне старе отримує бренд без хвоста
    out = site_name.rename(src, "Laovalerie Ltda", "Baggoetie Pohsa Ltda")
    assert "<title>Baggoetie Pohsa | Tesoura" in out and "© 2026 Baggoetie Pohsa Ltda</p>" in out, out
    # багатослівний бренд — поведінка як була: lone = перше слово
    assert "Na Borhe, cada" in site_name.rename("<p>Na Chovfuce, cada</p>", "Chovfuce Eszbuféfaa", "Borhe Ansabu")

def test_rename_files_returns_only_changed():
    files = {"a.html": "<p>Chovfuce Eszbuféfaa</p>", "b.html": "<p>чисто</p>"}
    out = site_name.rename_files(files, "Chovfuce Eszbuféfaa", "Borhe Ansabu")
    assert set(out) == {"a.html"} and "Borhe Ansabu" in out["a.html"], out


def test_caseless_scripts_are_renamed_too():
    """Арабська/тайська не мають регістру — гард lowercase їх не блокує
    (кейс qagek-adtijuleg-ae-ar: «قرار للمحاماة» по всьому сайту)."""
    src = "<p>مكتب قرار للمحاماة يقدم الخدمات</p>"
    out = site_name.rename(src, "قرار للمحاماة", "Qagek Adtijuleg")
    assert "Qagek Adtijuleg" in out and "قرار" not in out, out


# ------------------------------------------- сторінкові слова ≠ назва (01.10)
def test_page_word_head_never_becomes_the_name():
    """Кейс visee-loum: head-евристика 30.09 взяла «Accueil» («Головна»)
    за назву, і автофікс перейменував «Visee Loum» на «Accueil» по всьому
    вайту. Сторінкові слова — не кандидати ні в head, ні в консенсус."""
    files = {"index.php": "<title>Accueil — Visee Loum</title>"}
    assert site_name.from_title(files, "visee-loum-ch-fr") == "Visee Loum"


def test_poisoned_branch_self_heals_via_branch_name():
    # зіпсований стан «Accueil — Accueil» всюди — самоузгоджений; гейт
    # мусить відкинути його і впасти у назву вітки
    files = {p: f"<title>{h} — Accueil</title>"
             for p, h in [("index.php", "Accueil"), ("about.html", "À propos"),
                          ("contact.html", "Contact")]}
    assert site_name.expected("visee-loum-ch-fr", files) == "Visee Loum"


def test_consensus_still_wins_for_real_names():
    files = {p: f"<title>{h} — SwissAI Betrieb</title>"
             for p, h in [("index.php", "Accueil"), ("about.html", "À propos"),
                          ("faq.html", "FAQ")]}
    assert site_name.from_title(files, "visee-loum-ch-fr") == "SwissAI Betrieb"


def test_brand_starting_with_page_word_is_kept():
    # «Início Books» — бренд, а не сторінкове слово: фільтр точного збігу
    files = {"index.php": "<title>Início Books — Início Books</title>",
             "about.html": "<title>Sobre — Início Books</title>"}
    assert site_name.from_title(files, "vemsitzhii-br-pt") == "Início Books"


if __name__ == "__main__":
    run(dict(globals()))
