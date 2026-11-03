"""Тести роутера — того самого «який тест краще запустити».

Тут закріплено дві різні речі.

**Таблиця роутингу** — реальні формулювання скарг проти очікуваних чеків.
Вона і є специфікацією механізму: якщо картку скіла зіпсують, впаде саме
цей тест, а не абстрактне «щось не так».

**Поведінка навколо моделі** — що роутер робить, коли Claude недоступний,
бреше або відмовляється. Контракт один: назовні винятків не кидаємо,
з'їжджаємо на слова і кажемо про це в журнал.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import ai_router                                                  # noqa: E402
import ai_skills                                                  # noqa: E402
import runner                                                     # noqa: E402

CHECKS = runner.load_checks()
PHP = ai_skills.catalog(CHECKS, "php")
NODE = ai_skills.catalog(CHECKS, "node")


def _picked(text, cards=None):
    return ai_router.by_keywords(text, cards or PHP)[0]


# ------------------------------------------------- таблиця роутингу (php)

def test_specific_logo_complaints_land_on_the_right_check():
    """П'ять чеків матчать слово «лого». Розводять їх негативні приклади —
    саме заради цього випадку вони в картках і є."""
    assert _picked("В шапке логотип не тот, стоит чужой бренд") == ["logo_domain"]
    assert _picked("В логотипе стоит какая-то фотка вместо иконки") == ["logo_photo"]
    # «не ведет на главную» законно піднімає ще й link_target/empty_href
    # (лого могло вести на неіснуючий файл) — це повнота, а не помилка.
    # Важливо, що правильний чек ПЕРШИЙ: далі відсіє прогін.
    assert _picked("Логотип не кликается, не ведет на главную")[0] == "header_anchor"
    assert _picked("Нет иконки во вкладке браузера") == ["favicon"]


def test_vague_logo_complaint_raises_all_logo_checks():
    """Роутер працює НА ПОВНОТУ: з розмитого «проблеми з логотипом» не можна
    вгадати один чек, тому мають піднятись усі, а відсіє їх реальний прогін."""
    got = set(_picked("Вайт має проблеми з логотипом"))
    assert {"logo_domain", "logo_photo", "header_anchor"} <= got


def test_russian_and_ukrainian_wording_route_the_same():
    """Корпус вхідних текстів російський (TSM), метадані чеків українські —
    без обох форм у словах міст мовчав би на половині скарг."""
    assert _picked("Куки-баннер не закрывается") == ["cookie_consent"]
    assert _picked("Кукі-банер не закривається") == ["cookie_consent"]


def test_form_complaint_raises_the_whole_form_family():
    got = set(_picked("Форма не отправляет заявки, лиды не приходят"))
    assert {"form_hijack", "forms"} <= got


def test_a_lead_lost_only_on_an_inner_page_lands_on_the_satellite_check():
    """`form_action` прийшов зі знімком автора 07.09, і родину форм він не
    дублює: там сабміт ламає js або зайвий action, а тут ламає МІСЦЕ —
    сторінка-сателіт, з якої форма відправляється в статичний html, де
    php-блока ловлі ліда немає. Тому й розводить їх не слово «форма», а
    згадка внутрішньої сторінки."""
    assert _picked("С формы на странице контактов не приходят заявки, "
                   "с главной приходят") == ["form_action"]
    # а на скарзі без місця він стає ще одним кандидатом родини, не єдиним
    assert {"form_hijack", "forms"} <= set(
        _picked("Форма не отправляет заявки, лиды не приходят"))


def test_popup_and_tabs_land_on_the_elementor_check():
    """Чек прийшов зі знімком автора 24.08 замість `elementor_invisible`:
    той ловив назавжди невидимий блок, цей — віджет, чий обробник лишився в
    webpack-чанку, якого скрейпер не зберіг. Скарга звучить інакше («не
    відкривається»), тож і слова в картці інші."""
    assert _picked("Попап не открывается, вкладки не переключаются")[0] \
        == "elementor_widget_js"


def test_reserved_zone_link_is_told_apart_from_an_ordinary_dead_link():
    """`dead_host` не дублює `link_target`/`external_links`: там лінк
    «можливо мертвий» (HEAD-запит може впасти тимчасово), тут — мертвий
    гарантовано, бо зону зарезервовано RFC 2606/6761. Обидва в кандидатах —
    роутер працює на повноту, а розводить їх уже прогін."""
    assert "dead_host" in _picked("Ссылка на политику приватности ведёт в никуда")


def test_dead_cta_on_a_vue_white_lands_on_its_own_check():
    """Чек node-only, тож у php-каталозі його немає взагалі — саме тому
    таблиця роутингу перевіряється окремо на кожному типі проєкту."""
    got = _picked("Кнопки на главной ничего не делают, форма не открывается",
                  NODE)
    assert got[0] == "home_form_cta"
    assert "home_form_cta" not in _picked(
        "Кнопки на главной ничего не делают, форма не открывается", PHP)


def test_broken_link_wordings_survive_russian_inflection():
    """Регресія з прогону 20 тасок: стем «ссылк» НЕ є префіксом «ссылок»
    (побіжна голосна), а «веде» — не префікс «ведут». Через це скарга
    «несколько ссылок ведут в никуда» не матчила жодного чека."""
    for t in ("Несколько ссылок ведут в никуда — и внутренние, и на соцсети",
              "Ссылка в шапке ведёт в никуда",
              "Пункт меню никуда не ведет"):
        got = set(_picked(t))
        assert {"link_target", "empty_href"} & got, (t, got)


def test_placeholder_on_the_page():
    assert _picked("На странице видно {{DOMAIN_NAME}}") == ["wrong_literal"]


def test_project_type_decides_between_sibling_checks():
    """`favicon` живе в php, `favicon_link` — у node. Це детермінований
    фільтр, а не робота моделі."""
    assert _picked("нет иконки во вкладке", PHP) == ["favicon"]
    assert _picked("нет иконки во вкладке", NODE) == ["favicon_link"]


def test_alien_brand_is_told_apart_by_the_project_type_alone():
    """Знімок 07.09 навчив node-чек `logo_brand` бачити чужу назву в написі —
    рівно те, що в php ловить `logo_domain`. Слова в обох картках тепер одні,
    і це не колізія: каталог фільтрується типом проєкту ще до слів."""
    assert _picked("В шапке чужой бренд, не то название что домен",
                   NODE)[0] == "logo_brand"
    assert _picked("В шапке логотип не тот, стоит чужой бренд") == ["logo_domain"]


def test_a_stock_photo_in_the_tab_icon_is_still_a_favicon_complaint():
    """Той самий знімок навчив `favicon` бачити фавіконку з фотостоку
    (4456 віток із 4459 — picsum). Слово «стокове фото» в картку НЕ додане
    навмисно: ним живе `logo_photo`, і голий стем перетягнув би його скарги."""
    assert _picked("Иконка вкладки — случайное фото с picsum, "
                   "а не логотип")[0] == "favicon"
    assert _picked("В логотипе стоит какая-то фотка вместо иконки") \
        == ["logo_photo"]


def test_pictures_are_not_a_map():
    """Знайдено живим прогоном 07.09: стем «карт» у картці `map_address` ловив
    «картинки», і чек про карту приїжджав у кожну скаргу про зображення."""
    got = _picked("много элементов с дырами вместо текста или картинки")
    assert "map_address" not in got, got
    assert "media_integrity" in got, got
    # а справжня скарга на карту як була, так і лишається
    assert "map_address" in _picked("на месте карты пустой белый блок")


def test_not_ours_complaint_selects_nothing():
    assert _picked("Домен в черном списке гугла") == []
    assert [c["id"] for c in ai_skills.not_ours("Домен в черном списке гугла")] \
        == ["reputation"]


def test_candidate_list_is_capped():
    """Ширший набір не має сенсу: далі все одно фільтрують докази, а кожен
    зайвий чек — це час прогону."""
    got = _picked("не работает форма ссылка картинка меню логотип домен адрес "
                  "карта телефон почта куки язык 404 css стили")
    assert len(got) <= ai_router.MAX_CANDIDATES


# ------------------------------------------------- ваги

def test_negative_example_outweighs_a_single_word():
    ranked = ai_router.rank("логотип не кликается", PHP)
    photo = next(r for r in ranked if r["id"] == "logo_photo")
    assert photo["anti"], "мало спрацювати «не про це»"
    assert photo["score"] < 0


def test_history_lifts_a_check_that_already_fired_on_this_branch():
    """Вітка з трьома фіксами logo_domain в анамнезі імовірніше прийшла
    з ним же вчетверте — це факт із реєстру, а не здогадка."""
    plain = {r["id"]: r["score"] for r in ai_router.rank("проблема з лого", PHP)}
    lifted = {r["id"]: r["score"] for r in
              ai_router.rank("проблема з лого", PHP, history=["logo_domain"])}
    assert lifted["logo_domain"] == plain["logo_domain"] + ai_router.W_HISTORY
    assert lifted["logo_photo"] == plain["logo_photo"]


def test_rank_reports_which_words_matched():
    r = next(x for x in ai_router.rank("куки-баннер не закрывается", PHP)
             if x["id"] == "cookie_consent")
    assert r["hits"], "без переліку слів роутинг не розібрати постфактум"


# ------------------------------------------------- поведінка навколо моделі

def _no_key():
    os.environ.pop("ANTHROPIC_API_KEY", None)
    ai_router.reset_for_tests()


def test_without_a_key_the_router_falls_back_to_words_and_says_so():
    _no_key()
    out = ai_router.route("куки-баннер не закрывается", PHP)
    assert out["router"] == "keywords"
    assert out["checks"] == ["cookie_consent"]
    assert "ANTHROPIC_API_KEY" in out["model"]["error"]


def test_model_answer_replaces_the_keyword_answer():
    _no_key()
    saved = ai_router.ask_model
    ai_router.ask_model = lambda text, cards, timeout=60: {
        "checks": ["logo_domain", "header_anchor"], "not_ours": False,
        "confidence": 0.9, "reason": "бо так", "usd": 0.001,
        "tokens": {"in": 10, "out": 5}, "error": ""}
    try:
        out = ai_router.route("щось про лого", PHP)
    finally:
        ai_router.ask_model = saved
    assert out["router"] == "claude"
    assert out["checks"] == ["logo_domain", "header_anchor"]
    assert out["confidence"] == 0.9


def test_invented_check_ids_are_dropped_but_recorded():
    """Модель може назвати чек, якого немає. Викидаємо — але записуємо,
    інакше не видно, що вона фантазує."""
    _no_key()
    saved = ai_router.ask_model
    ai_router.ask_model = lambda text, cards, timeout=60: {
        "checks": ["logo_domain", "logo_perfect", "favicon_link"],
        "not_ours": False, "confidence": 0.5, "reason": "", "usd": 0,
        "tokens": {}, "error": ""}
    try:
        out = ai_router.route("лого", PHP)
    finally:
        ai_router.ask_model = saved
    assert out["checks"] == ["logo_domain"]
    # favicon_link існує, але він node-only — для php-каталогу теж чужий
    assert set(out["model"]["dropped"]) == {"logo_perfect", "favicon_link"}


def test_broken_model_answer_leaves_the_keyword_answer_in_place():
    _no_key()
    saved = ai_router.ask_model
    ai_router.ask_model = lambda text, cards, timeout=60: {
        "error": "HTTP 500: boom", "checks": None}
    try:
        out = ai_router.route("куки-баннер не закрывается", PHP)
    finally:
        ai_router.ask_model = saved
    assert out["router"] == "keywords"
    assert out["checks"] == ["cookie_consent"]
    assert "500" in out["model"]["error"]


def test_exhausted_budget_stops_the_model_but_not_the_router():
    _no_key()
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-не-справжній"
    try:
        out = ai_router.route("куки-баннер не закрывается", PHP,
                              budget_left_usd=0)
        assert out["router"] == "keywords"
        assert "бюджет" in out["model"]["error"]
    finally:
        _no_key()


def test_cooldown_grows_after_repeated_failures():
    """Мертвий Claude не має змушувати кожен виклик платити повний мережевий
    таймаут."""
    _no_key()
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-не-справжній"
    try:
        ai_router.reset_for_tests()
        assert ai_router.available()[0] is True
        ai_router._note_failure()
        ai_router._note_failure()
        ok, why = ai_router.available()
        assert ok is False and "кулдаун" in why
        ai_router._note_success()
        assert ai_router.available()[0] is True
    finally:
        _no_key()


def test_price_table_is_keyed_by_model():
    """Ціна константою замість таблиці почала б брехати при зміні моделі —
    а саме цей лічильник потім пояснює, куди пішли кредити."""
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    assert ai_router._usd("claude-opus-5", usage) == 5.0
    assert ai_router._usd("claude-haiku-4-5", usage) == 1.0


def test_cached_tokens_are_billed_cheaper():
    """Каталог у system однаковий для всіх запитів і з другого запиту
    читається з кешу — без цієї гілки лічильник завищував би."""
    full = ai_router._usd("claude-opus-5", {"input_tokens": 1_000_000})
    cached = ai_router._usd("claude-opus-5", {"cache_read_input_tokens": 1_000_000})
    assert cached < full / 5


# ------------------------------------ що саме летить в API і що з нього чути

class _Resp:
    """Мінімальна відповідь замість requests.Response."""

    def __init__(self, payload, status=200):
        self.status_code = status
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


def _capture(payload, status=200):
    """Підміняє requests.post і віддає (виклик ask_model, спіймані аргументи)."""
    seen = {}

    def fake_post(url, timeout=None, headers=None, json=None):
        seen["url"] = url
        seen["headers"] = headers or {}
        seen["body"] = json or {}
        return _Resp(payload, status)

    return fake_post, seen


def _with_key(payload, status=200):
    saved_post, saved_key = ai_router.requests.post, os.environ.get("ANTHROPIC_API_KEY")
    fake, seen = _capture(payload, status)
    ai_router.requests.post = fake
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-не-справжній"
    ai_router.reset_for_tests()
    try:
        out = ai_router.ask_model("лого зламане", PHP)
    finally:
        ai_router.requests.post = saved_post
        if saved_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = saved_key
        ai_router.reset_for_tests()
    return out, seen


def test_refusal_carries_the_category():
    """Відмова приходить як HTTP 200 зі stop_reason=refusal, і без категорії
    вона невідрізнима від будь-якого іншого збою. На бойовому прогоні 25.08
    відмовляв не текст скарги, а наш власний каталог (картки form_hijack і
    partner_banks читались класифікатором `cyber` як опис атаки) — без цього
    поля пошук причини почався б з ключа й моделі.
    """
    out, _ = _with_key({"stop_reason": "refusal", "content": [],
                        "stop_details": {"type": "refusal", "category": "cyber",
                                         "explanation": "довге пояснення"},
                        "usage": {}})
    assert out["checks"] is None, "відмова не має вдавати відповідь"
    assert "cyber" in out["error"], f"категорії немає в тексті: {out['error']}"
    assert out["refusal"]["category"] == "cyber"


def test_request_asks_for_a_server_side_fallback():
    """Запас до відмови тонкий: вимкнені з UI скіли роблять каталог коротшим,
    а в короткому тема перехоплення форми важить більше. Фолбек перекладає
    такий запит на іншу модель замість того, щоб з'їхати на слова."""
    _, seen = _with_key({"stop_reason": "tool_use", "content": [], "usage": {}})
    assert seen["body"].get("fallbacks") == "default"
    assert seen["headers"].get("anthropic-beta") == ai_router.FALLBACK_BETA


def test_cost_is_priced_by_the_model_that_answered():
    """З фолбеком відповісти може не та модель, яку просили. Лічильник,
    прив'язаний до ЗАПИТАНОЇ, почав би брехати саме тоді, коли по ньому
    найважче здогадатись — тому ціну беремо за тією, що відповіла."""
    out, _ = _with_key({"stop_reason": "tool_use", "content": [],
                        "model": "claude-haiku-4-5",
                        "usage": {"input_tokens": 1_000_000}})
    assert out["model"] == "claude-haiku-4-5"
    assert out["asked_model"] == ai_router.model_name()
    assert out["usd"] == 1.0, "ціна порахована за запитаною моделлю, а не за тією, що відповіла"


def test_an_empty_complaint_never_reaches_the_model():
    """Порожній текст — це наша помилка виклику, а не «модель не змогла».

    API відповідає `400 user messages must have non-empty content`, а будь-який
    збій зводить кулдаун — і слідом мовчки відмовляється РОЗБІР НОВОГО ІМЕНІ,
    у якого фолбека немає: мапа просто перестає рости. Спіймано локальним
    стендом: кожен повністю впізнаний структурований запит палив один такий
    виклик.
    """
    import ai_router
    r = ai_router.ask_model("   ", PHP)
    assert r["checks"] is None and "порожній" in r["error"], r


def test_a_fully_recognised_request_does_not_call_the_model_at_all():
    """Уся економія цього шару: коли мапа впізнала все, питати нема про що."""
    import ai_router
    import tsm_ingest
    calls = []

    def fake(text, cards, **kw):
        calls.append(text)
        return {"checks": [], "error": "", "usd": 0.01}

    env = tsm_ingest.ingest({"checks": [
        {"name": "links", "passed": False, "logs": ["• 404 — «Servicios»"]}]})
    справжній, ai_router.ask_model = ai_router.ask_model, fake
    try:
        r = ai_router.route(tsm_ingest.as_text(env), PHP, use_model=True, env=env)
    finally:
        ai_router.ask_model = справжній
    assert calls == [], calls
    assert r["checks"] and r["router"] == "tsm-map", r


if __name__ == "__main__":
    run(dict(globals()))
