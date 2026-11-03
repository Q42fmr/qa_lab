"""Тести partner_banks: блок довіри з назвами банків.

Детект тримається на ДВОХ ногах: словник назв і форма (кожен банк окремою
короткою карткою). Без словника під роздачу пішли б сітки переваг і цінники,
без форми — проза й FAQ, де банки згадані в реченні.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("partner_banks")

AT = ("Erste Bank", "Raiffeisen", "Bank Austria", "BAWAG P.S.K.",
      "Volksbank", "Sparkasse")
SG = ("DBS Bank", "OCBC Bank", "UOB", "Standard Chartered", "Maybank")


def _cards(names):
    return "".join(f'<div class="c"><p class="n">{n}</p></div>' for n in names)


def _page(inner, before="", after=""):
    return ("<!DOCTYPE html><html><body>\n"
            "<section class=\"hero\"><h1>Reisen</h1></section>\n"
            + before +
            "<!-- Partner Banks Section -->\n"
            "    <section class=\"py-16 bg-secondary\">\n"
            "      <div class=\"container\">\n"
            "        <h2>Vertrauensvolle Partnerschaften</h2>\n"
            "        <p>Wir arbeiten mit führenden Finanzinstituten zusammen</p>\n"
            "        <div class=\"grid\">" + inner + "</div>\n"
            "      </div>\n"
            "    </section>\n"
            + after +
            "<section class=\"faq\"><h2>Ihre Fragen</h2></section>\n"
            "</body></html>\n")


AT_PAGE = _page(_cards(AT))


# --------------------------------------------------------------- детект
def test_austrian_block_is_flagged():
    """Кейс krifhegdtbep-at-de: 6 австрійських банків картками. Раніше зі
    списку матчився лише «Raiffeisen» (він там був як швейцарський), тобто
    1 банк із 6 при порозі 3 — і чек мовчав на 21 вітці at-de."""
    issues = mod.run("index.php", AT_PAGE)
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "error", issues
    for name in ("Erste Bank", "Bank Austria", "Volksbank"):
        assert name in issues[0]["message"], issues[0]["message"]


def test_every_austrian_name_is_recognised():
    """Кожна назва окремо — інакше «6 банків» трималося б на кількох щасливих."""
    for name in AT + ("Oberbank", "Hypo Tirol Bank"):
        assert mod.RX.search(f"<p>{name}</p>"), name


def test_a_name_ending_in_a_dot_is_still_matched():
    """Список розширюється з `.env`, а назва може кінчатись пунктуацією
    («BAWAG P.S.K.», «Testbank A.G.»). Кінцевий `\\b` вимагав би літери ПІСЛЯ
    точки, тож такий запис був би мертвий і в `>Назва<`, і в реченні. Тому
    перевіряємо САМУ побудову регексу в модулі, а не свою копію."""
    os.environ["CHECK_BANKS"] = "Testbank A.G."
    try:
        fresh = load_check("partner_banks")
        assert "Testbank A.G." in fresh.BANKS, fresh.BANKS
        assert fresh.RX.search("<p>Testbank A.G.</p>"), "запис мертвий"
        assert fresh.RX.search("bei Testbank A.G. eröffnet")
    finally:
        os.environ.pop("CHECK_BANKS", None)


def test_bawag_is_matched_inside_its_full_name():
    assert mod.RX.search("<p>BAWAG P.S.K.</p>")


def test_singapore_block_still_flagged():
    """Локаль, яка ловилась і до правки, не мала зламатись."""
    assert len(mod.run("index.php", _page(_cards(SG)))) == 1


def test_two_banks_are_not_enough():
    """Поріг — 3 РІЗНИХ банки: пара згадок це ще не блок довіри. Карток тут
    аж чотири, тож поріг вузлів пройдений — розрізняє саме кількість РІЗНИХ
    назв, а не кількість карток."""
    html = _page(_cards(("Erste Bank", "Raiffeisen", "Erste Bank", "Raiffeisen")))
    assert mod.run("index.php", html) == []


def test_three_banks_in_one_node_are_not_a_block():
    """Проза/FAQ: три банки в одному реченні — не картки."""
    html = _page('<p>Wir arbeiten mit Erste Bank, Bank Austria und Volksbank '
                 'sowie weiteren Instituten zusammen.</p>')
    assert mod.run("index.php", html) == []


def test_three_banks_in_two_short_nodes_are_not_a_block():
    """Потрібні і 3 різні назви, І 3 окремі вузли. Короткий підпис, де два
    банки стоять в одному рядку, - це не сітка карток."""
    html = _page('<p>Erste Bank, Raiffeisen</p><p>Volksbank</p>')
    assert mod.run("index.php", html) == []


def test_prose_spread_over_several_nodes_is_not_a_block():
    """FAQ на три абзаци, у кожному свій банк у реченні: вузлів три, назв три,
    але вузли ДОВГІ - і саме ліміт слів на картку відрізняє їх від сітки."""
    html = _page(
        '<p>Wir arbeiten seit Jahren eng mit der Erste Bank in Wien zusammen.</p>'
        '<p>Auch die Bank Austria begleitet unsere Kunden bei der Finanzierung.</p>'
        '<p>Die Volksbank pruft jede Anfrage individuell und sehr sorgfaltig.</p>')
    assert mod.run("index.php", html) == []


def test_a_feature_grid_is_not_a_bank_block():
    """`facufuostelavb-at-de` і ще 28 віток: та сама форма (короткі картки у
    секції, що згадує Finanzinstitute), але назв банків немає — сітка переваг,
    цінник, модулі курсу. Саме словник їх і береже."""
    html = _page(_cards(("Mehr erfahren", "Unsere Leistungen", "€2.200",
                         "€3.200", "€4.100")))
    assert mod.run("index.php", html) == []


def test_law_firm_price_cards_are_not_a_bank_block():
    """`adkukocin-nem-ch-de`: FINMA й «Geldwäschereibekämpfung» — фінансова
    лексика без жодного банку."""
    html = _page(_cards(("FINMA-Lizenzanträge", "Geldwäschereibekämpfung",
                         "Kantonale Steuerrulings", "Ab CHF 550/Stunde")))
    assert mod.run("index.php", html) == []


def test_bank_name_inside_a_longer_word_is_not_a_hit():
    """Межі слова: «Sparkassenverband» не «Sparkasse»."""
    html = _page(_cards(("Sparkassenverband", "Volksbanken-Gruppe",
                         "Bank Austriaco")))
    assert mod.run("index.php", html) == []


def test_other_files_are_only_a_warning():
    """Автофікс чіпає лише index.php, тож в інших файлах це warn."""
    issues = mod.run("about.html", AT_PAGE)
    assert len(issues) == 1 and issues[0]["severity"] == "warn", issues
    assert "вручну" in issues[0]["message"], issues[0]["message"]


# ----------------------------------------------------------------- фікс
def test_fix_cuts_the_whole_section():
    out = mod.fix("index.php", AT_PAGE)
    assert "Vertrauensvolle Partnerschaften" not in out, out
    for name in AT:
        assert name not in out, name
    assert mod.run("index.php", out) == []


def test_fix_takes_the_heading_comment_with_it():
    out = mod.fix("index.php", AT_PAGE)
    assert "Partner Banks Section" not in out, out


def test_fix_keeps_the_neighbouring_sections():
    out = mod.fix("index.php", AT_PAGE)
    assert "Reisen" in out and "Ihre Fragen" in out, out
    assert out.count("<section") == AT_PAGE.count("<section") - 1, out


def test_fix_removes_every_such_block():
    """Блок трапляється двічі (шапка + низ сторінки) — обидва мусять піти."""
    doubled = _page(_cards(AT), after=_page(_cards(SG)))
    out = mod.fix("index.php", doubled)
    assert mod.run("index.php", out) == []


def test_fix_does_not_touch_other_files():
    assert mod.fix("about.html", AT_PAGE) == AT_PAGE


def test_fix_is_idempotent():
    once = mod.fix("index.php", AT_PAGE)
    assert mod.fix("index.php", once) == once


def test_fix_leaves_a_clean_page_without_a_block():
    clean = _page(_cards(("Mehr erfahren", "Unsere Leistungen", "€2.200")))
    assert mod.fix("index.php", clean) == clean


def test_check_is_php_auto():
    assert mod.PROJECTS == ["php"], mod.PROJECTS
    assert mod.GROUP == "auto"


if __name__ == "__main__":
    run(dict(globals()))
