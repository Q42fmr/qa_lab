"""Чек checks/banned_words.py — бан-слова QA Whites.

Позитиви/негативи взяті з самого джерела: вкладки «Запрещено (красное)»,
«Рисковое (жёлтое)», «Не ловится намеренно» книги «Бан-слова QA Whites
10.09.2026». Негативи — це живі фолси движка, які він обходить свідомо;
чек мусить обходити їх так само.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("banned_words")


def _page(body, title="Serviços de Tecnologia — Oficina Digital", lang="pt"):
    return (f'<html lang="{lang}"><head><title>{title}</title></head>'
            f"<body>{body}</body></html>")


def _run(files):
    return mod.run_branch(files, list(files), "test-branch")


def _fix(files):
    acts = mod.fix_branch(files, list(files), "test-branch") or []
    return {a["path"]: a["content"] for a in acts if a["type"] == "edit"}


def _msgs(issues):
    return " | ".join(i["message"] for i in issues)


# ---------------------------------------------------------------- виявлення

def test_red_word_is_error_with_path_and_line():
    files = {"index.html": _page("<p>linha um</p>\n<p>melhor cassino do brasil</p>")}
    issues = _run(files)
    assert len(issues) == 1, issues
    i = issues[0]
    assert i["severity"] == "error", i
    assert i["path"] == "index.html"
    assert i["line"] == 2, i
    assert "cassino" in i["message"].lower()


def test_yellow_word_is_warn():
    files = {"index.html": _page("<p>resultados guaranteed para todos</p>")}
    issues = _run(files)
    assert len(issues) == 1 and issues[0]["severity"] == "warn", issues


def test_bet_with_digits_and_digits_with_bet():
    files = {"index.html": _page("<p>bet365 e 22bet e bet-365 aqui</p>")}
    issues = _run(files)
    assert len(issues) == 3, issues
    # шаблон движка \d{1,4}-?bet НЕ ловить 1xbet (x — не дефіс); зеркалимо
    # движок, а не виправляємо його — QA судить саме так
    files = {"index.html": _page(
        "<p>your best bet is patience, we bet on 1xbet quality</p>")}
    assert _run(files) == []


def test_word_boundaries_from_engine_legend():
    # bet ≠ between, sex ≠ sexta-feira, porn ≠ Waraporn, meth ≠ method
    files = {"index.html": _page(
        "<p>between us, sexta-feira with Waraporn explains the method</p>")}
    assert _run(files) == []


def test_intentionally_not_caught():
    # вкладка «Не ловится намеренно»: голі слова, які движок свідомо обходить
    files = {"index.html": _page(
        "<p>Singapore CBD district offers nude tones for interiors. "
        "Bullet points show explosive growth. Uma aposta no futuro. "
        "Wetten ablegen? Das grosse Lotto! Our pharmacist recommends "
        "the Cash Flow Clinic approach with silver bullet ideas.</p>")}
    assert _run(files) == [], _msgs(_run(files))


def test_caught_forms_of_the_same_stems():
    files = {"index.html": _page(
        "<p>cbd oil e nudes e gun shop e assault rifle e apostas esportivas</p>")}
    sevs = {i["severity"] for i in _run(files)}
    assert len(_run(files)) == 5, _msgs(_run(files))
    assert sevs == {"error"}


def test_pharmacy_yellow_but_pharmacist_clean():
    files = {"index.html": _page("<p>pharmacy delivery</p>")}
    assert [i["severity"] for i in _run(files)] == ["warn"]
    files = {"index.html": _page("<p>the pharmacist writes columns</p>")}
    assert _run(files) == []


def test_clinic_needs_a_medical_word_nearby():
    files = {"index.html": _page("<p>agende na dental clinic hoje</p>")}
    assert [i["severity"] for i in _run(files)] == ["warn"]
    files = {"index.html": _page("<p>join the business clinic workshop</p>")}
    assert _run(files) == []


def test_negation_lifts_yellow_only():
    files = {"index.html": _page("<p>results are not guaranteed here</p>")}
    assert _run(files) == []
    files = {"index.html": _page("<p>не гарантированный доход обещаем</p>")}
    assert _run(files) == []
    # червоне заперечення НЕ знімає
    files = {"index.html": _page("<p>não é um cassino</p>")}
    assert len(_run(files)) == 1


def test_russian_stems():
    files = {"index.html": _page("<p>лучшие наркотики и казино города</p>")}
    assert len(_run(files)) == 2, _msgs(_run(files))


def test_theme_exemption_silences_yellow():
    # тема «питание» знімає категорію «алкоголь»
    rest = _page("<p>carta de wine e beer</p>",
                 title="Bella Tavola — Restaurante Italiano")
    assert _run({"index.html": rest}) == []
    # на непрофільній темі те саме — warn
    tech = _page("<p>carta de wine e beer</p>")
    assert len(_run({"index.html": tech})) == 2


def test_theme_exemption_never_touches_red():
    rest = _page("<p>cassino do hotel</p>",
                 title="Bella Tavola — Restaurante Italiano")
    assert [i["severity"] for i in _run({"index.html": rest})] == ["error"]


def test_croatian_puta_is_exempt():
    files = {"index.html": _page("<p>tri puta dnevno</p>", lang="hr")}
    assert _run(files) == []
    files = {"index.html": _page("<p>tri puta dnevno</p>", lang="pt")}
    assert len(_run(files)) == 1


def test_mask_hides_code_but_keeps_text_attrs():
    body = ('<script src="jquery.roulette.min.js">var casino=1;</script>'
            '<div class="casino-strip"><img alt="melhor cassino"></div>'
            "<!-- poker draft --><p>texto limpo</p>")
    issues = _run({"index.html": _page(body)})
    assert len(issues) == 1, _msgs(issues)
    assert "cassino" in issues[0]["message"].lower()


def test_vue_and_ts_scan_raw_code():
    files = {
        "src/pages/index.vue": "<script>const promo = 'казино онлайн'</script>",
        "src/data/texts.ts": 'export const hero = "instant profit today";',
    }
    got = {(i["path"], i["severity"]) for i in _run(files)}
    assert got == {("src/pages/index.vue", "error"),
                   ("src/data/texts.ts", "warn")}, got


def test_lockfiles_are_skipped():
    files = {"package.json": '{"name": "casino-web"}',
             "package-lock.json": '{"casino": "1.0.0"}'}
    assert _run(files) == []


# ---------------------------------------------------------------- автофікс

def test_fix_deletes_red_and_cleans_spaces():
    files = {"index.html": _page("<p>Visite nosso cassino hoje.</p>")}
    fixed = _fix(files)["index.html"]
    assert "cassino" not in fixed
    assert "nosso hoje." in fixed, fixed
    assert _run({"index.html": fixed}) == []


def test_fix_replaces_yellow_from_map_keeping_case():
    files = {"index.html": _page("<p>Guaranteed results, guaranteed daily</p>")}
    fixed = _fix(files)["index.html"]
    assert "Reliable results" in fixed, fixed
    assert "reliable daily" in fixed, fixed
    assert _run({"index.html": fixed}) == []


def test_fix_leaves_unmapped_yellow_alone():
    files = {"index.html": _page("<p>we accept bitcoin</p>")}
    assert _fix(files) == {}
    assert len(_run(files)) == 1        # warn лишається людині


def test_fix_respects_theme_exemption():
    rest = _page("<p>carta de wine</p>",
                 title="Bella Tavola — Restaurante Italiano")
    assert _fix({"index.html": rest}) == {}


def test_fix_does_not_touch_masked_code():
    body = "<script>var s='casino';</script><p>sem problemas</p>"
    assert _fix({"index.html": _page(body)}) == {}


def test_fix_is_idempotent():
    files = {"index.html": _page(
        "<p>Guaranteed cassino: пассивный доход весь день</p>")}
    fixed = _fix(files)["index.html"]
    again = _fix({"index.html": fixed})
    assert again == {}, again


def test_contract_for_runner():
    assert mod.GROUP == "tests"
    assert not hasattr(mod, "PROJECTS")     # діє і на php, і на node
    assert callable(mod.run_branch) and callable(mod.fix_branch)


# ------------------------------------------- тригер-індекс (перф, 02.10)

def test_pattern_literals_respect_optional_tails():
    """«cassinos?» мусить дати тригер «cassino»: опціональна літера не
    входить у гарантований підрядок матчу."""
    assert mod._pattern_literals(r"(?<!\w)(?:cassinos?)(?!\w)") == ["cassino"]


def test_optional_group_alternation_still_indexed():
    """Арабський префікс `(?:ال|[وبلفك](?:ال)?)?` опціональний — його `|`
    не жене патерн у always: ядро-літерал гарантоване."""
    pat = r"(?<!\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:مراهنات))(?!\w)"
    lits = mod._pattern_literals(pat)
    assert "مراهنات" in lits, lits
    assert "|" not in mod._mandatory(pat).replace("[وبلفك]", " "), \
        mod._mandatory(pat)


def test_always_set_is_tiny():
    """Сенс індексу: на файл ганяється ~26 патернів замість 235. Більшає
    always — повертається стара стіна часу."""
    assert len(mod._ALWAYS) <= 12, (len(mod._ALWAYS), mod._ALWAYS)


def test_candidates_find_each_dictionary_word():
    """Еквівалентність індексу: для КОЖНОГО патерна будується простий
    текст-приманка (з його літералів) — патерн зобов'язаний потрапити у
    кандидати цього тексту. Пропуск = німе бан-слово на проді."""
    n_red = len(mod._RED_C)
    missing = []
    for i, (p, w, c) in enumerate(list(mod.RED) + list(mod.YELLOW)):
        lits = mod._pattern_literals(p)
        if not lits:
            continue                      # такі в always — завжди ганяються
        bait = " ".join(lits)
        if i not in mod._candidates(bait):
            missing.append((i, w))
    assert not missing, missing[:8]


if __name__ == "__main__":
    run(dict(globals()))
