"""Модель добудовує мапу вердиктів.

Це головна зміна ролей у мості: раніше таблицю «їхня перевірка → наші чеки»
вела людина, а модель гадала на льоту при КОЖНІЙ скарзі. Тепер навпаки —
модель відповідає на питання «що це за перевірка» ОДИН раз, відповідь лягає
в мапу, і далі це звичайна таблиця.

Модель тут підроблена: гейт лишається герметичним, а перевіряти треба не її
кмітливість, а нашу обробку — валідацію, запис і те, що промах не ламає
роутинг.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import ai_router                                                  # noqa: E402
import ai_skills                                                  # noqa: E402
import ai_skills_store                                            # noqa: E402
import runner                                                     # noqa: E402
import verdict_map as vm                                          # noqa: E402

CARDS = ai_skills.catalog(runner.load_checks(), "php",
                          ai_skills_store.all_skills())
VALID = {c["id"] for c in CARDS}


class _Mem:
    def __init__(self):
        self.data = {}

    def all(self):
        return {k: dict(v) for k, v in self.data.items()}

    def get(self, k):
        return dict(self.data[k]) if k in self.data else None

    def put(self, rec):
        rec = dict(rec)
        rec.setdefault("stats", {})
        self.data[rec["key"]] = rec
        return rec

    def delete(self, k):
        return self.data.pop(k, None) is not None

    def bump(self, k, field, n=1):
        rec = self.data.get(k)
        if rec is None:
            return None
        rec.setdefault("stats", {})[field] = \
            int(rec["stats"].get(field) or 0) + n
        return rec


def _fresh():
    vm.reset_for_tests(_Mem())


_fresh()


def _with_model(entries, error=""):
    """Підміна одного виклику: повертає готові записи, як їх дала б модель."""
    calls = []

    def fake(items, cards, timeout=60):
        calls.append([i["name"] for i in items])
        return {"entries": entries, "usd": 0.004, "ms": 1200, "error": error}

    return calls, fake


def _learn(unknown, entries, error=""):
    calls, fake = _with_model(entries, error)
    real, ai_router.ask_verdicts = ai_router.ask_verdicts, fake
    try:
        return ai_router.learn_unknown(unknown, CARDS), calls
    finally:
        ai_router.ask_verdicts = real


def _learn_scripted(unknown, scripted):
    """Модель відповідає по черзі різними наборами — щоб перевірити доспробу."""
    calls = []

    def fake(items, cards, timeout=60):
        calls.append([i["name"] for i in items])
        got = scripted[min(len(calls) - 1, len(scripted) - 1)]
        return {"entries": got, "usd": 0.004, "ms": 900, "error": ""}

    real, ai_router.ask_verdicts = ai_router.ask_verdicts, fake
    try:
        return ai_router.learn_unknown(unknown, CARDS), calls
    finally:
        ai_router.ask_verdicts = real


def _u(name, logs=("щось",)):
    return {"name": name, "logs": list(logs), "soft": False}


# --------------------------------------------------------- запис у мапу

def test_a_new_name_is_learned_once_and_becomes_a_table():
    """Після розбору незнайоме ім'я більше не незнайоме: наступний такий
    вердикт іде таблицею, без моделі й без грошей."""
    _fresh()
    assert vm.resolve(_u("spellcheck2"), VALID) is None
    res, calls = _learn([_u("spellcheck2", ["сервис → сервіс"])], [
        {"name": "spellcheck2", "class": "not_ours", "checks": [],
         "not_ours": "spellcheck", "reason": "орфографія — зміст",
         "confidence": 0.9}])
    assert calls == [["spellcheck2"]], calls
    assert res["learned"] and not res["dropped"], res
    got = vm.resolve(_u("spellcheck2"), VALID)
    assert got and got["class"] == "not_ours" and got["by"] == "model", got


def test_ours_needs_a_real_check_id():
    """«Наше» без жодного чека з каталогу — це не відповідь, а здогадка.
    Записати її означало б зробити помилку ПОСТІЙНОЮ, на відміну від разової
    здогадки, яку відсіє прогін."""
    _fresh()
    res, _ = _learn([_u("newcheck")], [
        {"name": "newcheck", "class": "ours", "checks": [], "not_ours": "",
         "reason": "щось наше", "confidence": 0.8}])
    assert res["learned"] == [] and res["dropped"] == ["newcheck"], res
    assert vm.resolve(_u("newcheck"), VALID) is None


def test_invented_check_ids_are_dropped_not_stored():
    """Модель могла назвати чек, якого немає або який знято з каталогу."""
    _fresh()
    res, _ = _learn([_u("newcheck")], [
        {"name": "newcheck", "class": "ours",
         "checks": ["link_target", "вигаданий_чек"], "not_ours": "",
         "reason": "", "confidence": 0.7}])
    assert res["learned"][0]["checks"] == ["link_target"], res
    assert vm.get("tsm:newcheck")["php"] == ["link_target"]


def test_a_name_we_never_asked_about_is_refused():
    """Відповідь не на те питання — не відповідь."""
    _fresh()
    res, _ = _learn([_u("newcheck")], [
        {"name": "щось_своє", "class": "not_ours", "checks": [],
         "not_ours": "health", "reason": "", "confidence": 1.0}])
    assert res["learned"] == [] and "щось_своє" in res["dropped"], res


def test_unknown_not_ours_class_is_cleared():
    """Клас «не наше» має бути з НАШОГО списку, інакше в коментар людині
    поїде вигадана категорія."""
    _fresh()
    res, _ = _learn([_u("newcheck")], [
        {"name": "newcheck", "class": "not_ours", "checks": [],
         "not_ours": "вигаданий_клас", "reason": "", "confidence": 1.0}])
    assert res["learned"], res
    assert vm.get("tsm:newcheck")["not_ours"] == ""


def test_yellow_verdicts_are_never_sent_to_the_model():
    """Жовте не роутиться ніколи — отже й вчити по ньому нема чого."""
    _fresh()
    res, calls = _learn([{"name": "greencheck2", "logs": ["?"], "soft": True}], [])
    assert calls == [] and res["learned"] == [], (calls, res)


def test_a_storm_of_new_names_is_capped():
    """Буря незнайомих імен означає зміну на їхньому боці — її треба
    побачити на /ai, а не мовчки вивчити всю пачку одним махом."""
    _fresh()
    many = [_u(f"check{i}") for i in range(20)]
    _res, calls = _learn(many, [])
    assert len(calls[0]) == ai_router.MAX_LEARN_AT_ONCE, calls


def test_a_model_failure_leaves_the_map_untouched():
    """Збій моделі не має ламати роутинг: без неї міст працює рівно як
    працював — прозою, словами і дефолтами мапи."""
    _fresh()
    res, _ = _learn([_u("newcheck")], None, error="HTTP 500")
    assert res["error"] == "HTTP 500" and res["learned"] == []
    assert vm.resolve(_u("newcheck"), VALID) is None


def test_names_the_model_skipped_are_asked_once_more():
    """Модель може відповісти не про всі імена, і це не гіпотеза: на живому
    прогоні 27.08 у пачці з п'яти вона повернула ОДИН запис, а ми проковтнули
    це мовчки — чотири імені лишились незнайомими без жодного сліду."""
    _fresh()
    один = [{"name": "a1", "class": "not_ours", "checks": [],
             "not_ours": "health", "reason": "", "confidence": 0.9}]
    решта = [{"name": n, "class": "not_ours", "checks": [], "not_ours": "health",
              "reason": "", "confidence": 0.9} for n in ("a2", "a3")]
    res, calls = _learn_scripted([_u("a1"), _u("a2"), _u("a3")], [один, решта])
    assert calls == [["a1", "a2", "a3"], ["a2", "a3"]], calls
    assert len(res["learned"]) == 3, res
    assert res["unanswered"] == [], res


def test_what_stays_unanswered_is_reported_not_swallowed():
    """Доспроба теж може нічого не дати. Тоді ім'я мусить бути ВИДНИМ:
    мовчазна деградація тут виглядає як «стало дорожче» — найгірший вид
    поломки, бо не болить, доки не рахуєш гроші."""
    _fresh()
    res, calls = _learn_scripted([_u("a1"), _u("a2")], [[], []])
    assert len(calls) == 2, calls
    assert res["unanswered"] == ["a1", "a2"], res


# ------------------------------------------------- інвалідація каталогу

def test_the_answer_remembers_which_catalogue_it_was_given_for():
    """Запис, вивчений моделлю, ЗАМОРОЖУЄ відповідь: додали новий чек — старий
    запис його ніколи не обере, бо нікого не питає. Єдиний спосіб це
    побачити — памʼятати, при якому каталозі відповідь дана."""
    _fresh()
    _learn([_u("newcheck")], [
        {"name": "newcheck", "class": "ours", "checks": ["link_target"],
         "not_ours": "", "reason": "", "confidence": 0.9}])
    assert vm.get("tsm:newcheck")["catalogue"] == vm.catalogue_hash(CARDS)
    assert vm.stale(CARDS) == []
    # каталог змінився — запис стає підозрілим і видним на /ai
    інший = CARDS + [{"id": "новий_чек"}]
    assert [r["key"] for r in vm.stale(інший)] == ["tsm:newcheck"]


def test_seeded_entries_are_never_called_stale():
    """Дефолти їдуть разом з кодом і покриті тестами — перевчати їх нема за
    чим, скільки б каталог не мінявся."""
    _fresh()
    assert vm.stale(CARDS + [{"id": "новий_чек"}]) == []


# ------------------------------------------- знайдено локальним стендом

def test_a_class_that_came_from_the_map_reaches_the_answer():
    """`visual` і `no_check` з МАПИ мусять доходити до людини.

    Поки правило жило всередині ендпоінта, розвилка читала лише рядки,
    впізнані ЯКОРЯМИ, і клас по імені перевірки в неї не потрапляв: відповідь
    ставала `clean` — «жодна перевірка не підійшла» — замість чесного «це
    бачить візуальний прогін» або «такого чека в лабі немає». Спіймано
    локальним стендом на новому імені `alt_text`.
    """
    import ai_bridge
    вiзуально = {"map": {"hits": [{"class": "visual", "soft": False}]}}
    немає_чека = {"map": {"hits": [{"class": "no_check", "soft": False,
                                    "reason": "перевірки alt у лабі немає"}]}}
    assert ai_bridge.nothing_to_run(вiзуально)[0] == "visual"
    статус, чому = ai_bridge.nothing_to_run(немає_чека)
    assert статус == "not_ours" and "alt" in чому, (статус, чому)


def test_tool_failure_still_beats_everything_else():
    import ai_bridge
    r = {"tool_failure": True,
         "map": {"hits": [{"class": "no_check", "soft": False, "reason": "x"}]}}
    assert ai_bridge.nothing_to_run(r)[0] == "skipped"


def test_yellow_map_hits_never_change_the_answer():
    import ai_bridge
    r = {"map": {"hits": [{"class": "visual", "soft": True},
                          {"class": "no_check", "soft": True, "reason": "x"}]}}
    assert ai_bridge.nothing_to_run(r)[0] == "clean"


def test_the_price_of_learning_is_counted():
    """Розбір нового імені коштує грошей, і вони мусять бути видні.

    Ціна `learn_unknown` поверталась у відповідь, але в реєстр ішла лише
    ціна `ask_model` — тобто бюджетний гейт не бачив половини витрат, а /ai
    показував менше, ніж списано."""
    import ai_bridge
    r = {"model": {"usd": 0.01}, "learned": {"usd": 0.05}}
    assert abs(ai_bridge._цiна(r) - 0.06) < 1e-9, ai_bridge._цiна(r)
    assert ai_bridge._цiна({}) == 0.0


def test_a_failed_learn_is_not_reported_as_clean():
    """Якщо модель не відповіла про нове ім'я, ми не знаємо, наше воно чи ні.

    Відповідати `clean` означає сказати «у вітці цього немає» там, де ми
    просто не питали. Спіймано локальним стендом: на одному з 26 сценаріїв
    виклик не пройшов, і нова перевірка TSM мовчки стала «чисто».
    """
    import ai_bridge
    статус, чому = ai_bridge.nothing_to_run({
        "learned": {"error": "HTTP 529"},
        "map": {"hits": [], "unknown": [{"name": "alt_text"}]}})
    assert статус == "clean"
    assert "alt_text" in чому and "529" in чому, чому
    # а без збою — звичайна відповідь
    статус2, _ = ai_bridge.nothing_to_run(
        {"map": {"hits": [], "unknown": [{"name": "alt_text"}]}})
    assert статус2 == "clean"


if __name__ == "__main__":
    run(dict(globals()))
