"""Розбір вердиктів TSM.

Тексти в фікстурах — **дослівні рядки з їхнього `advice.py`** (зріз v0.6.17
від 11.08.2026), а не мій переказ: увесь сенс цього шару в тому, що словник
з того боку фіксований, і будь-яка вільність у тесті зробила б його
безпредметним.

Найважливіші тут два: жовту секцію не можна роутити ніколи, і збій ЇХНЬОЇ
тули не можна плутати з дефектом вайта.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import runner                                                     # noqa: E402
import tsm_verdicts as tv                                         # noqa: E402

PHP = {c["id"] for c in runner.load_checks()
       if not c.get("error") and "php" in (c.get("projects") or [])}
NODE = {c["id"] for c in runner.load_checks()
        if not c.get("error") and "node" in (c.get("projects") or [])}

# Справжній вигляд `advice_text()`: заголовок з доменом, марковані рядки з
# тегом сторінки, потім жовта секція.
SAMPLE = """Что фиксить — example.com
• [главная] Название сайта не совпадает с доменом — привести бренд в шапке/заголовке к корню домена.
• [/kontakt] Заменить почту info@exampl.com на адрес @example.com.
• [главная] Куки-баннер на главной не показывается — проверить, что баннер подключён.
Посмотреть глазами (не дефект, а повод взглянуть):
  [главная] Нечитаемый текст (сливается с фоном): <p> контраст 1.4:1 — поменять цвет.
"""


# --------------------------------------------------------------- конверт

def test_domain_is_taken_from_the_header():
    assert tv.parse(SAMPLE)["domain"] == "example.com"


def test_hard_lines_are_recognised_with_their_page_tag():
    got = tv.parse(SAMPLE)["items"]
    hard = [i for i in got if not i["soft"]]
    assert [i["tsm"] for i in hard] == ["naming", "emails", "cookies"], hard
    assert [i["page"] for i in hard] == ["главная", "/kontakt", "главная"]


def test_the_yellow_section_is_never_routed():
    """`advice_lines()` пише «посмотреть глазами» під окремим заголовком, і
    це прямо позначено як НЕ дефект. Зароутувати ці рядки означало б палити
    коло на вітці за те, що чинити не треба."""
    p = tv.parse(SAMPLE)
    soft = [i for i in p["items"] if i["soft"]]
    assert len(soft) == 1 and soft[0]["tsm"] == "contrast", soft
    assert "contrast" not in str(tv.checks_for(p["items"], PHP))


def test_checks_come_out_mapped_to_ours():
    p = tv.parse(SAMPLE)
    got = tv.checks_for(p["items"], PHP)
    assert got == ["logo_domain", "contacts", "cookie_consent"], got


def test_the_node_side_gets_its_own_checks():
    """Той самий вердикт на node-вітці мапиться в інші чеки, а `cookie_consent`
    там просто немає — і тягнути php-шний ми не маємо."""
    p = tv.parse(SAMPLE)
    got = tv.checks_for(p["items"], NODE)
    assert "logo_brand" in got and "domain_match" in got, got
    assert "cookie_consent" not in got and "logo_domain" not in got, got


def test_all_ok_is_recognised():
    assert tv.parse("Что фиксить — a.co\nВсё ок — фиксить нечего.")["all_ok"]


# ------------------------------------------------------------ категорії

def test_a_tool_failure_is_not_a_defect_of_the_white():
    """У їхньому ж коді: «это сбой инструмента, а не приговор сайту»."""
    for line in ("• [главная] Прогон этого домена сорвался — это сбой инструмента, а не приговор сайту.",
                 "• [главная] Домен снят по времени — это сбой прогона, а не приговор сайту.",
                 "• [главная] Прогон остановлен вами — домен не проверен до конца.",
                 "• [главная] Смысловой движок не ответил — проверки темы и картинок не выполнялись.",
                 "• [главная] Проверка домена оборвалась: клик увёл со страницы."):
        items = tv.parse(line)["items"]
        assert items and items[0].get("tool_failure"), line
        assert tv.checks_for(items, PHP) == [], line


def test_not_ours_verdicts_carry_our_class():
    for line, cls in (("Домен в чёрном списке Google — браузеры покажут красный экран.", "reputation"),
                      ("Убрать рисковый/запрещённый контент: казино", "banned"),
                      ("Проверить цены (похоже на ошибку разряда/валюты): 10$", "prices"),
                      ("Проверить адекватность цен (см. лог).", "prices"),
                      ("Домен не открывается (timeout) — проверить хостинг/DNS.", "health")):
        items = tv.parse(line)["items"]
        assert items and items[0].get("not_ours") == cls, (line, items)


def test_faq_verdict_routes_to_the_accordion_check():
    """До 13.10 `faq` був у «не наше». fettmagv-ch-ch-de-2 довів, що це
    дефект коду вітки (масова заміна вбила site.js цілком), тож тепер
    вердикт веде на faq_accordion з автофіксом."""
    items = tv.parse("FAQ есть, но вопросы не раскрываются по клику — "
                     "починить аккордеон.")["items"]
    assert items and not items[0].get("not_ours"), items
    assert tv.checks_for(items, PHP) == ["faq_accordion"], items


def test_layout_and_contrast_go_to_the_visual_runner_not_to_checks():
    """У нас це не чеки: перекос вёрстки і контраст бачить `visual_runner`.
    Відповідати «зараз полагоджу» на них було б брехнею."""
    for line in ("Вёрстка разъехалась: блок вылезает за край.",
                 "Вёрстка страницы съехала — посмотреть глазами по скриншоту.",
                 "Нечитаемый текст (сливается с фоном): <h1> — поменять цвет.",
                 "Текст сливается с фоном — см. лог, поменять цвета."):
        items = tv.parse(line)["items"]
        assert items and items[0].get("visual"), line
        assert tv.checks_for(items, PHP) == [], line


def test_tsm_health_is_our_checks_not_our_not_ours_class():
    """Пастка збігу імен: у TSM `health` — це биті ассети і JS (наші чеки), а
    в нашому NOT_OURS `health` — це «хостинг лежить». Мапиться навхрест:
    їхній `load` → наш клас, їхній `health` → справжні чеки."""
    got = tv.parse("Починить тех.здоровье страницы (битые ассеты/ошибки JS): см. лог")["items"]
    assert got[0]["tsm"] == "health" and not got[0].get("not_ours"), got
    assert "css_integrity" in tv.checks_for(got, PHP)
    load = tv.parse("Домен не открывается (502) — проверить хостинг/DNS.")["items"]
    assert load[0].get("not_ours") == "health", load


# ---------------------------------------------------- цілісність мапи

def test_every_mapped_check_exists_in_the_tree():
    """Мапа на знятий чек — тиха дірка: вердикт впізнається, а роутити нема
    що. Автор зняв три чеки одним знімком 24.08, тож випадок реальний."""
    alive = PHP | NODE
    bad = [(v["tsm"], v["anchor"], sorted(set((v.get("php") or []) + (v.get("node") or [])) - alive))
           for v in tv.VERDICTS
           if not set((v.get("php") or []) + (v.get("node") or [])) <= alive]
    assert not bad, bad


def test_every_verdict_has_exactly_one_outcome():
    """Якір мусить вести рівно в одне: наші чеки, «не наше», «немає чека»,
    візуальний прогін або збій тули. Два виходи = невизначена поведінка."""
    for v in tv.VERDICTS:
        kinds = [k for k in ("php", "not_ours", "no_check", "visual", "tool_failure")
                 if v.get(k)]
        assert len(kinds) == 1, (v["tsm"], v["anchor"], kinds)


def test_anchors_do_not_shadow_each_other():
    """Три поради починаються з «Убрать …», дві — з «Вёрстка …». Довші
    якорі мусять перевірятись першими, інакше короткий з'їдав би довгий."""
    for v in tv.VERDICTS:
        got = tv.match_line(v["anchor"])
        assert got is v, (v["anchor"], got and got["anchor"])


def test_every_anchor_survives_the_real_envelope():
    """Ф6: поріг тут інший, ніж для моделі — **100%**.

    Це таблиця, а не судження: кожен якір мусить упізнатись у тому вигляді, в
    якому рядок реально приходить — з маркером, тегом сторінки і хвостом
    після константної частини. Один промах — дефект, а не складний випадок.
    """
    doc = "Что фиксить — a.co\n" + "\n".join(
        f"• [главная] {v['anchor']} — хвіст, якого ми не знаємо: {i}"
        for i, v in enumerate(tv.VERDICTS))
    got = tv.parse(doc)
    assert got["unknown"] == [], got["unknown"]
    assert len(got["items"]) == len(tv.VERDICTS), (
        len(got["items"]), len(tv.VERDICTS))
    assert [i["anchor"] for i in got["items"]] == [v["anchor"] for v in tv.VERDICTS]


def test_not_ours_classes_are_real_ones():
    import ai_skills
    known = {c["id"] for c in ai_skills.NOT_OURS}
    used = {v["not_ours"] for v in tv.VERDICTS if v.get("not_ours")}
    assert used <= known, used - known


# ------------------------------------------------------------- дрейф

def test_human_prose_is_not_mistaken_for_a_verdict():
    """Сьогоднішній кейс: зауваження друкує людина. Такий рядок має піти в
    `rest`, тобто далі у слова й модель, а не загубитись."""
    p = tv.parse("В шапке логотип не тот, стоит чужой бренд")
    assert p["items"] == [] and p["rest"] == ["В шапке логотип не тот, стоит чужой бренд"]
    assert p["unknown"] == []


def test_an_unrecognised_verdict_line_is_counted_as_drift():
    """`advice.py` у них оновлюється разом з тулою. Якщо формулювання
    перепишуть, якорі мовчки перестануть матчити — і замість мапи запрацює
    модель, що ззовні виглядає просто як «стало дорожче». Тому рядок, схожий
    на вердикт, але не впізнаний, лічимо окремо."""
    p = tv.parse("• [главная] Совершенно новая формулировка совета от тулы")
    assert p["unknown"] and not p["items"], p
    raw = tv.parse("some_new_check: сырой лог, которого мы не знаем")
    assert raw["unknown"], raw


def test_an_unknown_check_names_itself():
    """`_advise_check` віддає `f"{name}: логи"` для перевірки, у якої гілки
    поради немає, — тобто ЇХНЯ нова перевірка сама себе називає. Це різниця
    між «щось не розібрали» і «допиши мапу для spellcheck2»."""
    p = tv.parse("• [главная] spellcheck2: найдено 3 опечатки на странице")
    assert p["unknown"] and p["unknown"][0]["tsm"] == "spellcheck2", p["unknown"]


def test_a_rewritten_phrasing_has_no_name_but_is_still_counted():
    """Другий вид дрейфу: формулювання переписали, імені в рядку немає.
    Впізнати нічого, але змовчати не можна."""
    p = tv.parse("• [главная] Совершенно новая формулировка совета")
    assert p["unknown"] and p["unknown"][0]["tsm"] == "", p["unknown"]


def test_mixed_comment_splits_into_verdicts_and_prose():
    """Найімовірніший реальний вигляд: блок від тули плюс дописане людиною."""
    p = tv.parse(SAMPLE + "\nи ещё логотип не кликается, посмотри")
    assert [i["tsm"] for i in p["items"] if not i["soft"]] == ["naming", "emails", "cookies"]
    assert p["rest"] == ["и ещё логотип не кликается, посмотри"]


# ------------------------------------------------------- через роутер

import ai_router                                                  # noqa: E402
import ai_skills                                                  # noqa: E402

CARDS = ai_skills.catalog([c for c in runner.load_checks() if not c.get("error")], "php")


def _spy():
    """Підміняє виклик моделі й запам'ятовує, з ЧИМ її покликали."""
    calls = []

    def fake(text, cards, timeout=60, rich=True):
        calls.append(text)
        return {"checks": ["favicon"], "confidence": 0.5, "reason": "spy",
                "not_ours": False, "usd": 0.0}
    return calls, fake


def _routed(text, use_model=True):
    calls, fake = _spy()
    real, ai_router.ask_model = ai_router.ask_model, fake
    try:
        return ai_router.route(text, CARDS, use_model=use_model), calls
    finally:
        ai_router.ask_model = real


def test_a_pure_verdict_block_never_calls_the_model():
    """Уся економія цього шару тут: словник з того боку фіксований, тож
    платити за вгадування нема за що."""
    r, calls = _routed(SAMPLE)
    assert r["router"] == "tsm-map", r["router"]
    assert calls == [], calls
    assert r["checks"] == ["logo_domain", "contacts", "cookie_consent"], r["checks"]
    assert r["confidence"] == 1.0


def test_a_tool_failure_stops_before_everything():
    """Решта червоного в тому самому тексті стосується недоперевіреної
    сторінки — так написано в їхньому ж коментарі до `page_guard`."""
    r, calls = _routed("• [главная] Прогон этого домена сорвался — сбой инструмента.\n"
                       "• [главная] Название сайта не совпадает с доменом — привести бренд.")
    assert r.get("tool_failure") and r["checks"] == [], r
    assert calls == [], calls


def test_prose_after_the_block_still_reaches_the_model_and_only_it():
    """Змішаний коментар: блок від тули + дописане людиною. Моделі йде
    ЛИШЕ залишок — інакше платили б за токени вердиктів двічі."""
    r, calls = _routed(SAMPLE + "\nи ещё попап не открывается")
    assert r["router"] == "tsm-map+claude", r["router"]
    assert len(calls) == 1 and calls[0].strip() == "и ещё попап не открывается", calls
    assert r["checks"][:3] == ["logo_domain", "contacts", "cookie_consent"], r["checks"]
    assert "favicon" in r["checks"], "відповідь моделі загубилась"


def test_a_word_inside_a_verdict_does_not_trigger_not_ours():
    """`advice.py` вклеює шматки логів у рядки `bank`/`partners`/`banned` —
    там цілком може трапитись «цены». Якби ми сканували весь текст, скарга
    на чужі торгові марки стала б «не наше: ціни», а в режимі слів «не наше»
    перемагає кандидатів. Тому слова застосовуються лише до залишку."""
    r, _ = _routed("• [главная] Убрать заявленное партнёрство/чужие торговые "
                   "марки: Visa; цены партнёров", use_model=False)
    assert r["checks"] == ["partner_banks"], r["checks"]
    assert r["not_ours"] == [], r["not_ours"]


def test_verdicts_work_with_the_model_switched_off():
    r, calls = _routed(SAMPLE, use_model=False)
    assert r["checks"] and calls == []


if __name__ == "__main__":
    run(dict(globals()))
