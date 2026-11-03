import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run, load_check

mod = load_check("captcha_lang")

FORM = (
    '<label class="gfield_label gform-field-label" for="input_2_9">'
    '<span class="gform-field-label__text">{question}</span></label>'
    '<script>window[\'gf_form_conditional_logic\'][2] = {{ logic: {{ 0: {{"field":'
    '{{"rules":[{rules}]}},"section":null}} }} }} }};</script>'
)


def _rules(values):
    return ",".join(f'{{"fieldId":"9","operator":"is","value":"{v}"}}' for v in values)


def _page(lang, question, values):
    body = FORM.format(question=question, rules=_rules(values))
    return f'<!DOCTYPE html><html lang="{lang}"><head></head><body>{body}</body></html>'


def test_fr_question_de_values_flags_and_fixes():
    text = _page("fr", "Combien font trois plus quatre ?", ["8", "acht", "Acht", ""])
    issues = mod.run("kontakt/index.html", text)
    assert len(issues) == 1, issues
    msg = issues[0]["message"]
    assert "Combien font trois plus quatre ?" in msg
    assert "= 7" in msg
    assert "фікс поставить 7/sept/Sept" in msg

    fixed = mod.fix("kontakt/index.html", text)
    assert '"fieldId":"9","operator":"is","value":"7"' in fixed
    assert '"fieldId":"9","operator":"is","value":"sept"' in fixed
    assert '"fieldId":"9","operator":"is","value":"Sept"' in fixed
    assert '"fieldId":"9","operator":"is","value":""' in fixed
    assert "acht" not in fixed and "Acht" not in fixed

    assert mod.run("kontakt/index.html", fixed) == []
    assert mod.fix("kontakt/index.html", fixed) == fixed


def test_already_correct_values_silent():
    text = _page("fr", "Combien font trois plus quatre ?", ["7", "sept", "Sept", ""])
    assert mod.run("kontakt/index.html", text) == []
    assert mod.fix("kontakt/index.html", text) == text


def test_de_question_de_values_silent():
    text = _page("de", "Wie viel ist drei plus vier?", ["7", "sieben", "Sieben", ""])
    assert mod.run("kontakt/index.html", text) == []
    assert mod.fix("kontakt/index.html", text) == text


def test_unparsable_question_silent():
    text = _page("fr", "Combien font le ciel et la terre ?", ["8", "acht", "Acht", ""])
    assert mod.run("kontakt/index.html", text) == []
    assert mod.fix("kontakt/index.html", text) == text


def test_real_kontakt_fixture_matches_reference():
    if not (ROOT / "_work" / "ref").is_dir():
        return      # локальні еталони реальних сторінок (_work/ref не в репо): у CI пропускаємо
    before = (ROOT / "_work" / "ref" / "chantier_kontakt_before.html").read_text(encoding="utf-8")
    after = (ROOT / "_work" / "ref" / "chantier_kontakt_after.html").read_text(encoding="utf-8")
    issues = mod.run("kontakt/index.html", before)
    assert len(issues) == 1, issues
    fixed = mod.fix("kontakt/index.html", before)
    # сторінка в "after" несе ще й незалежні правки інших чеків (CSS
    # background-repeat, рядок адреси у футері) — captcha_lang їх не чіпає;
    # звіряємо саме капча-фрагмент (скрипт gf_form_conditional_logic).
    rules_rx = mod._rule_rx("9")
    assert rules_rx.findall(fixed) == rules_rx.findall(after)
    assert mod.run("kontakt/index.html", fixed) == []
    assert mod.fix("kontakt/index.html", fixed) == fixed


if __name__ == "__main__":
    run(dict(globals()))
