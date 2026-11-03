"""Вимір роутера на розміченому корпусі — герметично, без мережі.

Тут перевіряється не «чи працює код», а **чи не погіршилось розпізнавання**.
Ганяється лише детермінований шлях (слова): він і є те, що лишається, коли
Claude вимкнено, впав або вичерпано бюджет, і саме він мовчки псується від
правки одного стема в картці.

**Дві половини корпусу, і плутати їх не можна.** `tuned` — формулювання, на
яких свого часу підбирали `слова`; recall там 1.00 за побудовою, і це
означає рівно «шпаргалку не зіпсували», а не «розпізнавання добре».
`held_out` — ті самі поломки чужими словами; ось там і видно справжню
цифру, і саме її має рухати робота над каталогом.

Числа в assert'ах — не бажані, а ЗАМІРЯНІ 26.08. Вони стеля знизу: впало
нижче — щось зламали; піднялось вище — підніми поріг разом з виміром.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import ai_corpus                                                  # noqa: E402
import ai_router                                                  # noqa: E402
import ai_skills                                                  # noqa: E402
import runner                                                     # noqa: E402

CHECKS = [c for c in runner.load_checks() if not c.get("error")]
CATS = {"php": ai_skills.catalog(CHECKS, "php"),
        "node": ai_skills.catalog(CHECKS, "node")}
IDS = {c["id"] for c in CHECKS}


def _measure(part: str) -> dict:
    rows = [ai_corpus.score(c, ai_router.by_keywords(c["text"], CATS[c["ptype"]])[0])
            for c in ai_corpus.cases(part=part)]
    return ai_corpus.summary(rows)


# ------------------------------------------------------- цілісність корпусу

def test_every_label_points_at_an_existing_check():
    """Мітка на знятий чек — це тихо зіпсований вимір: кейс стає
    недосяжним, recall падає, і виглядає це як регресія роутера. Автор зняв
    три чеки одним знімком 24.08, тож випадок не гіпотетичний."""
    bad = [(c["text"][:40], sorted((c["must"] | c["ok"]) - IDS))
           for c in ai_corpus.cases() if not (c["must"] | c["ok"]) <= IDS]
    assert not bad, f"мітки на неіснуючі чеки: {bad}"


def test_the_corpus_covers_both_project_types():
    kinds = {c["ptype"] for c in ai_corpus.cases()}
    assert kinds == {"php", "node"}, kinds


def test_held_out_is_really_held_out():
    """Захист від найпростішого способу «поліпшити» вимір — дописати
    формулювання з held_out у слова картки. Тексти двох половин не мають
    збігатись."""
    tuned = {c["text"] for c in ai_corpus.cases(part="tuned")}
    held = {c["text"] for c in ai_corpus.cases(part="held_out")}
    assert not (tuned & held), tuned & held


# --------------------------------------------------------------- сам вимір

def test_tuned_half_stays_at_the_ceiling():
    """Заміряно 26.08: recall 1.00. Це шпаргалка скорера, тож будь-яке
    падіння тут = зіпсована картка, а не складна скарга."""
    s = _measure("tuned")
    assert s["recall"] >= 1.0, s


def test_held_out_half_does_not_regress():
    """Заміряно 26.08: recall 0.50, повних влучань 9 з 16. Оце і є чесна
    цифра розпізнавання словами — і саме її має рухати вгору робота над
    каталогом (опис і приклади для моделі, кроки 1-2)."""
    s = _measure("held_out")
    assert s["recall"] >= 0.5, s
    assert s["full_hits"] >= 9, s


def test_the_router_does_not_drown_the_branch_in_checks():
    """Кожен чек у наборі йде в гейт кіл на вітці, тож шум не безкоштовний.
    Заміряно: у середньому 1.8 чека на скаргу і 0.27 зайвого."""
    s = _measure("tuned")
    assert s["picked_avg"] <= 3.0, s
    assert s["noise_avg"] <= 1.0, s


# ------------------------------------------------------------- «не наше»

def test_every_not_ours_complaint_is_recognised():
    """Не впізнати — залишити людину без відповіді. Дві з цих скарг не
    впізнавались до 26.08: «цены устарели» (фраза `цен ` з пробілом не є
    підрядком «цены»), «куча опечаток» (`опечатк` не є префіксом
    «опечаток» — побіжна голосна)."""
    missed = [c["text"] for c in ai_corpus.cases()
              if c["not_ours"] and not ai_skills.not_ours(c["text"])]
    assert not missed, missed


def test_no_false_not_ours_on_a_real_complaint():
    """Дорожча помилка, ніж попередня: у режимі слів «не наше» ПЕРЕМАГАЄ
    кандидатів (`ai_bridge.scope_checks`), тож хибне спрацювання = міст
    відмовляє в законній скарзі. До 26.08 стем `доход` у класі «ціни» ловив
    «заявки не доходят до почты», а `заработ` — «форма не заработала»."""
    wrong = [(c["text"], [x["id"] for x in ai_skills.not_ours(c["text"])])
             for c in ai_corpus.cases()
             if not c["not_ours"] and ai_skills.not_ours(c["text"])]
    assert not wrong, wrong


# --------------------------------------------- що саме бачить модель

def test_the_catalog_carries_the_check_description():
    """Крок 1 виміру: `опис` (DESCRIPTION чека) і негативні приклади довго
    лежали в картці й НЕ їхали в промпт — модель бачила менш як половину
    того, що ми про чек знаємо. Тест стереже, щоб їх не прибрали назад."""
    text = ai_skills.render_for_model(CATS["php"])
    assert "шукає:" in text and "не плутати з:" in text, text[:300]
    plain = ai_skills.render_for_model(CATS["php"], rich=False)
    assert len(text) > len(plain) * 2, (len(text), len(plain))


def test_examples_never_teach_a_check_that_is_not_in_the_catalog():
    """Приклад із чеком іншого типу проєкту (або знятим) учив би модель
    називати id, який ми потім мовчки викинемо в `dropped`."""
    for ptype, cards in CATS.items():
        ids = {c["id"] for c in cards}
        shown = ai_skills.render_examples(ids)
        for line in shown.splitlines():
            named = line.split("-> ", 1)[1]
            if named.startswith("нічого"):
                continue
            assert set(named.split(", ")) <= ids, (ptype, line)


def test_the_system_prompt_assembles_without_a_key():
    """Промпт збирається `SYSTEM.format(...)` — тобто будь-яка зайва фігурна
    дужка в шаблоні або забутий слот падають KeyError'ом. І ось у чому
    пастка: `ask_model` виходить РАНІШЕ формату, коли ключа немає, тож без
    цього тесту складання промпта не перевіряв ніхто, а зламалось би воно
    лише в проді, на живій скарзі.
    """
    for ptype, cards in CATS.items():
        ids = {c["id"] for c in cards}
        text = ai_router.SYSTEM.format(
            catalog=ai_skills.render_for_model(cards),
            examples=ai_skills.render_examples(ids))
        assert "{catalog}" not in text and "{examples}" not in text, ptype
        assert "Розібрані приклади" in text, ptype
        assert len(text) > 1000, (ptype, len(text))


def test_every_example_is_labelled_with_live_checks():
    """Приклад, чиї чеки зникли з дерева, мовчки випав би з промпта —
    формально не помилка, але каталог прикладів тихо порожнів би."""
    dead = [e for e in ai_skills.EXAMPLES if not set(e["чеки"]) <= IDS]
    assert not dead, dead


if __name__ == "__main__":
    run(dict(globals()))
