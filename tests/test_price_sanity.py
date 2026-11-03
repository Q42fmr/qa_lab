"""Ціни: підозріло малі / розкид у сотні разів (checks/price_sanity.py).

Кейси 02.10: «R$ 1,83 — подозрительно мало (ждём от 20)» (868mewn67) і
«CHF 3 и CHF 1500 — потерян разделитель тысяч» (868mg0ynk). Детект-чек:
фікса немає — цифри вигадувати не можна.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                            # noqa: E402

mod = load_check("price_sanity")


def _run(page, path="precos/index.html"):
    files = {path: page}
    return mod.run_branch(dict(files), list(files), "nwf-x-br-pt")


def test_suspiciously_low_brl_price_is_flagged():
    issues = _run("<html><body><p>Plano base: R$ 1,83 por consulta</p>"
                  "<p>Plano top: R$ 9,90</p></body></html>")
    assert issues and all(i["severity"] == "warn" for i in issues)
    assert "R$ 1,83" in issues[0]["message"]
    assert "від 20" in issues[0]["message"]


def test_thousands_separator_loss_spread_is_flagged():
    issues = _run("<html><body><p>Ab CHF 3</p><p>Komplett: CHF 1'500</p>"
                  "</body></html>")
    msgs = " | ".join(i["message"] for i in issues)
    assert "розкид цін у 500×" in msgs, msgs
    assert "CHF 3" in msgs and "CHF 1'500" in msgs


def test_normal_prices_stay_silent():
    assert _run("<html><body><p>R$ 150,00</p><p>R$ 1.500,00</p>"
                "<p>CHF 2'000</p></body></html>") == []


def test_legit_wide_catalog_is_not_spread():
    # 10 проти 2000 — легітимний прайс (дрібничка і великий пакет):
    # мінімум не «людськи малий»
    assert _run("<html><body><p>EUR 16</p><p>EUR 3.400</p></body></html>") == []


def test_zero_and_percent_are_ignored():
    assert _run("<html><body><p>R$ 0,00</p><p>R$ 5%</p>"
                "<p>R$ 250,00</p></body></html>") == []


def test_scripts_do_not_feed_prices():
    assert _run("<html><body><script>var p='R$ 1,83'</script>"
                "<p>R$ 99,00</p></body></html>") == []


def test_number_normalization():
    assert mod._to_value("1.500,00") == 1500.0
    assert mod._to_value("1'500") == 1500.0
    assert mod._to_value("1,83") == 1.83
    assert mod._to_value("1500") == 1500.0
    assert mod._to_value("1.500") == 1500.0


def test_contract_shape():
    assert mod.GROUP == "tests"
    assert sorted(mod.PROJECTS) == ["node", "php"]
    assert not hasattr(mod, "fix_branch") and not hasattr(mod, "fix")


if __name__ == "__main__":
    run(dict(globals()))
