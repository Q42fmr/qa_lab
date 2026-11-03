"""Тести каталогу скілів.

Головне, що тут закріплено: **картка є в КОЖНОГО чека**. Чек без картки —
це чек, якого міст майже напевно не знайде в прозі, тобто мовчазна діра в
покритті: скарга приїде, роутер поверне порожньо, і зовні це виглядатиме
як «лаба не вміє», хоча вміє.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import ai_skills                                                  # noqa: E402
import runner                                                     # noqa: E402

CHECKS = runner.load_checks()


# --------------------------------------------------------------- покриття

def test_every_check_has_a_skill_card():
    cov = ai_skills.coverage(CHECKS)
    assert cov["total"] >= 30, f"чеків підозріло мало: {cov['total']}"
    assert not cov["missing"], f"чеки без картки скіла: {cov['missing']}"


def test_no_cards_for_checks_that_no_longer_exist():
    """Картка без чека — слід від видаленого чека: модель бачитиме в
    каталозі id, якого не існує, і роутинг у цю картку буде відкинуто мовчки."""
    cov = ai_skills.coverage(CHECKS)
    assert not cov["stale"], f"картка є, чека немає: {cov['stale']}"


def test_card_is_built_even_without_an_entry_in_skills():
    """Новий чек від автора мусить потрапляти в каталог одразу, ще до того,
    як ми напишемо йому слова — інакше кожен апстрім ламав би міст."""
    fake = {"id": "brand_new", "name": "Свіжий чек", "description": "щось ловить",
            "group": "review", "projects": ["php"], "fixable": True}
    c = ai_skills.card(fake)
    assert c["enriched"] is False
    assert c["симптом"] == "Свіжий чек", "симптом мусить впасти на NAME чека"
    assert c["слова"] == [] and c["fixable"] is True


def test_card_takes_metadata_from_the_check_not_from_us():
    real = next(c for c in CHECKS if c["id"] == "logo_domain")
    card = ai_skills.card(real)
    assert card["group"] == real["group"]
    assert card["projects"] == real["projects"]
    assert card["fixable"] is True
    assert card["enriched"] is True


# --------------------------------------------------------------- матчинг

def test_prefix_match_survives_inflection():
    """«логотипом», «логотипа», «логотипу» — одна й та сама скарга."""
    for form in ("логотипом", "логотипа", "логотипу", "логотип"):
        assert ai_skills.match_words(f"проблема з {form}", ["логотип"])


def test_short_tokens_are_matched_exactly_not_by_prefix():
    """«js» не має матчити «json», інакше будь-яка згадка джейсона тягла б
    чеки про скрипти."""
    assert not ai_skills.match_words("прислали json", ["js"])
    assert ai_skills.match_words("не працює js", ["js"])


def test_phrase_needs_all_its_words_but_not_their_order():
    """Порядок слів у слов'янських мовах вільний. Спершу фраза шукалась
    підрядком — і «черн список» не ловив живого «в черном списке» ні
    буквою; це ловив саме цей тест."""
    assert ai_skills.match_words("тут чужий бренд у шапці", ["чужий бренд"])
    assert ai_skills.match_words("бренд тут геть чужий", ["чужий бренд"])
    assert ai_skills.match_words("домен в черном списке", ["черн списк"])
    assert not ai_skills.match_words("просто бренд", ["чужий бренд"])


def test_non_letter_words_are_matched_as_is():
    assert ai_skills.match_words("видно {{DOMAIN_NAME}}", ["{{"])
    assert ai_skills.match_words("віддає 404", ["404"])


def test_normalize_folds_case_and_yo():
    assert ai_skills.normalize("  Ещё   ТУТ ") == "еще тут"


def test_match_returns_which_words_hit_not_just_true():
    """У журнал має лягати причина: без переліку слів на питання «чому цей
    чек узагалі потрапив у кандидати» відповісти нічим."""
    hits = ai_skills.match_words("логотип і бренд", ["логотип", "бренд", "форма"])
    assert set(hits) == {"логотип", "бренд"}


# --------------------------------------------------------------- «не наше»

def test_reputation_complaint_is_recognised_as_not_ours():
    got = ai_skills.not_ours("Домен в черном списке гугла, красный экран")
    assert [g["id"] for g in got] == ["reputation"]
    assert got[0]["чому"]


def test_ordinary_complaint_is_not_flagged_as_not_ours():
    assert ai_skills.not_ours("в шапке логотип не тот") == []


def test_not_ours_classes_all_have_a_reason():
    """Без пояснення відповідь «це не наше» неможливо ані перевірити, ані
    оскаржити — а її читає людина на тому кінці."""
    for cls in ai_skills.NOT_OURS:
        assert cls["чому"] and cls["слова"], cls["id"]


# --------------------------------------------------------------- каталог

def test_catalog_filters_by_project_type():
    php = {c["id"] for c in ai_skills.catalog(CHECKS, "php")}
    node = {c["id"] for c in ai_skills.catalog(CHECKS, "node")}
    assert "logo_domain" in php and "logo_domain" not in node
    assert "logo_brand" in node and "logo_brand" not in php
    assert php and node


def test_catalog_drops_checks_that_failed_to_load():
    broken = {"id": "boom", "name": "boom", "description": "", "group": "tests",
              "projects": ["php"], "error": "traceback", "module": None}
    ids = {c["id"] for c in ai_skills.catalog(CHECKS + [broken], "php")}
    assert "boom" not in ids, "битий чек не можна пропонувати мосту"


def test_prompt_lists_every_card_with_its_id():
    cards = ai_skills.catalog(CHECKS, "php")
    text = ai_skills.render_for_model(cards)
    for c in cards:
        assert c["id"] in text
    assert "автофікс" in text and "діагностика" in text


if __name__ == "__main__":
    run(dict(globals()))
