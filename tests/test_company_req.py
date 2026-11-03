"""Пул юрреквізитів (company_req.json + company_req.py).

Контракти:
  * кожен запис it-it повний і чесний: назва з орг-формою, REA формату
    ПРОВІНЦІЯ-НОМЕР, P.IVA проходить checksum, джерело вказане;
  * вибір по вітці детермінований (та сама вітка — ті самі реквізити);
  * локаль без бази — порожньо, без винятків.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                        # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import company_req                                              # noqa: E402


def test_it_rows_are_complete_and_valid():
    rows = company_req.rows("it-it")
    assert len(rows) >= 5, "пул замалий"
    for r in rows:
        assert re.search(r"\b(S\.?\s?r\.?\s?l|S\.?\s?p\.?\s?A|SRLS?|SPA)",
                         r["name"]), r
        assert re.fullmatch(r"[A-Z]{2}-\d{5,7}", r["rea"]), r
        assert company_req.piva_valid(r["piva"]), r
        assert r["src"].startswith("http"), r
    assert len({r["piva"] for r in rows}) == len(rows), "дублікати P.IVA"


def test_pick_is_deterministic_and_locale_bound():
    a = company_req.pick("mds-epidoc-it-it")
    b = company_req.pick("mds-epidoc-it-it")
    assert a and a == b
    assert company_req.pick("nwf-x-br-pt") in ({},) or \
        company_req.pick("nwf-x-br-pt").get("piva"), "br без бази → {}"
    assert company_req.pick("mds-x-de-de") == {}
    assert company_req.pick("") == {}


def test_neighbor_branches_spread_over_pool():
    picks = {company_req.pick(f"mds-x{i}-it-it")["piva"] for i in range(12)}
    assert len(picks) >= 2, "усі вітки отримали один запис"


if __name__ == "__main__":
    run(dict(globals()))
