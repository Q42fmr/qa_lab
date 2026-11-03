"""Тема для пошуку фото, витягнута з вайта.

Еталон — дві вітки, де тему написав саппорт вручну; парсер має віддати рівно
ті самі три пропозиції (мовою вайта):

  padzarok-br-pt: Estadia Curta na Península / Recepção de Pequeno Casamento /
                  Temporada Longa na Costa
  quuifa-br-pt:   Estadia Serrana de Dois Dias / Hospedagem de Retiro para
                  Grupos / Arranjo de Temporada
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                # noqa: E402

sys.path.insert(0, str(ROOT))
import photo_theme as pt                                      # noqa: E402


def _page(title="Padzarok — Hospedagem em Búzios, RJ", cards=(), extra=""):
    body = ""
    for img, h3, price in cards:
        body += (f'<div class="card"><img src="a.jpg" alt="{img}">'
                 f'<h3 class="t">{h3}</h3><p>texto</p>'
                 f'<span class="price">{price}</span>'
                 f'<a class="btn">Consultar</a></div>')
    return (f"<html><head><title>{title}</title>"
            f'<meta property="og:site_name" content="Padzarok">'
            f'<meta name="description" content="Padzarok — hospedagem à beira-mar.">'
            f"</head><body><header><h3>Menu</h3></header>"
            f'<section class="offers"><h2>Três formas de ficar</h2>{body}</section>'
            f"{extra}</body></html>")


CARDS = [("Estadia curta na península", "Estadia Curta na Península", "R$ 1.410"),
         ("Recepção de casamento no jardim", "Recepção de Pequeno Casamento", "R$ 8.900"),
         ("Temporada longa à beira-mar", "Temporada Longa na Costa", "R$ 4.200")]


# ------------------------------------------------------------- розбір сторінки
def test_offers_are_the_theme():
    r = pt.extract(_page(cards=CARDS))
    assert r["source"] == "offers"
    assert r["query"] == ("Estadia Curta na Península, Recepção de Pequeno "
                          "Casamento, Temporada Longa na Costa")


def test_card_keeps_its_own_image():
    """alt має належати САМЕ цій картці: <img> у цих шаблонах стоїть перед
    назвою, тож наївний пошук уперед віддавав знімок наступного тарифу."""
    offs = pt.extract(_page(cards=CARDS))["offers"]
    assert [o["alt"] for o in offs] == [c[0] for c in CARDS]


def test_headings_outside_the_price_block_are_ignored():
    """«Localização na Península» лежить поруч із цінами лише за відстанню в
    символах — у тему потрапляти не має."""
    extra = ('<section class="features"><h3>Localização na Península</h3>'
             '<h3>Café da manhã na varanda</h3></section>')
    r = pt.extract(_page(cards=CARDS, extra=extra))
    assert "Localização" not in r["query"] and "Café" not in r["query"]


def test_falls_back_to_title_tail_without_offers():
    r = pt.extract(_page(cards=[]))
    assert r["source"] == "title"
    assert r["query"] == "Hospedagem em Búzios, RJ"


def test_single_price_is_not_an_offer_block():
    """Одна ціна — це не блок тарифів (може бути згадка у тексті)."""
    r = pt.extract(_page(cards=CARDS[:1]))
    assert r["source"] == "title"


def test_brand_is_stripped_from_offer_title():
    cards = [("a", "Padzarok — Estadia Curta", "R$ 1"),
             ("b", "Temporada Longa — Padzarok", "R$ 2")]
    r = pt.extract(_page(cards=cards))
    assert r["query"] == "Estadia Curta, Temporada Longa"


def test_duplicate_offer_titles_collapse():
    cards = CARDS + [("x", "estadia curta na península", "R$ 9")]
    assert pt.extract(_page(cards=cards))["query"].count("Estadia Curta") == 1


def test_no_title_no_offers_uses_description():
    p = ('<html><head><meta name="description" content="Aulas de violão em '
         'Lisboa. Turmas pequenas."></head><body></body></html>')
    r = pt.extract(p)
    assert r["source"] == "description"
    assert r["query"] == "Aulas de violão em Lisboa"


def test_prices_in_other_currencies():
    cards = [("a", "Kurzaufenthalt", "€ 90"), ("b", "Monatsmiete", "1 200 CHF")]
    assert pt.extract(_page(cards=cards))["source"] == "offers"


def test_empty_page_gives_empty_query():
    assert pt.extract("")["query"] == ""


if __name__ == "__main__":
    run(dict(globals()))
