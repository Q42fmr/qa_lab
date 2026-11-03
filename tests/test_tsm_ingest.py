"""Толерантний прийом вердиктів.

Фікстури — **дослівні рядки з обох зрізів TSM** (v0.6.17 від 11.08.2026 і
v0.9.26 від 27.08.2026), знятих машинно їхнім же `advice.py`
(`qa_lab-work/tsm-drift/`). Переказувати їх своїми словами тут не можна: увесь
сенс шару в тому, що форми з того боку різні й міняються, і тест, написаний
«приблизно», не спіймав би саме те, від чого захищаємось.

Головне, що стережуть ці тести:
  * структура б'є прозу — інакше один дефект у трьох форматах став би трьома;
  * `passed=True` з warnings — це ЖОВТЕ, а не зелене (у них так влаштовані
    hygiene / spellcheck / mobile, які не червоніють ніколи);
  * ім'я вітки і «генератор чи викладка» дістаються з тексту, який вони
    вже пишуть, — без жодної правки на їхньому боці.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import tsm_ingest                                                 # noqa: E402

# --- дослівні форми з 0.9.26 ---------------------------------------------
TEXT_0926 = """Что фиксить — fojfnpiot.pro
• [главная] Название сайта не совпадает с доменом — привести бренд в шапке/заголовке к корню домена.
• [главная] Ссылки ведут в никуда (404/500) — поправить адреса в навигации: 404 — «Servicios» → https://fojfnpiot.pro/servicios
• [главная] Убрать рисковые слова из текста: казино
• [главная] hygiene: Нет <title>; Иконка сайта не найдена
Посмотреть глазами (не дефект, а повод взглянуть):
  👁 [главная] Поменять картинку на тему «Строительство»
"""

# Короткий формат саппорта — той, на якому наші якорі дають 11%.
SUMMARY_0926 = """Что фиксить — fojfnpiot.pro
• Название сайта не совпадает с доменом — на главной странице
• Пункты меню «Servicios», «Contacto» ведут в 404 — на главной странице
• Запрещённые слова в тексте — на главной странице
"""

# Блок whitesrc.py, який вони пишуть у звіт кожного червоного домену з 21.08.
WHITESRC = """ИСХОДНИКИ ВАЙТА (ветка «orxqal-stnaker-sg-en», файлов 214):
  • links [/servicios]: этих файлов НЕТ и в исходниках (/servicios) — дефект генератора, чинить шаблон
  (сравнение НЕ меняет вердикт — оно только говорит, куда идти чинить)
"""

# Зріз домену так, як він лежить у них у пам'яті (`runner._запомнить_срез`).
SLICE = {
    "domain": "fojfnpiot.pro",
    "checks": [
        {"name": "links", "page": "", "passed": False,
         "logs": ["• 404 — «Servicios» → https://fojfnpiot.pro/servicios"],
         "warnings": []},
        {"name": "naming", "page": "", "passed": False,
         "logs": ["Бренд «Alpina» не совпадает с доменом"], "warnings": []},
        {"name": "hygiene", "page": "", "passed": True, "logs": [],
         "warnings": ["Нет <title>"]},
        {"name": "form", "page": "/kontakt", "passed": True, "logs": [],
         "warnings": []},
    ],
    "fix": ["• Название сайта не совпадает с доменом — на главной странице"],
    "front": ["• [главная] Ссылки ведут в никуда (404/500) — поправить адреса"],
    "eyes": ["👁 [главная] Поменять картинку на тему «Строительство»"],
    "text": WHITESRC,
}


def _names(env, soft=None):
    return [v["name"] for v in env["verdicts"]
            if soft is None or v["soft"] is soft]


# ------------------------------------------------------- сьогоднішня форма

def test_plain_prose_still_works():
    """Нинішній контракт — проза в `text` — мусить лишитись робочим:
    той бік ще нічого не переписував, і ламати його вхід ми не маємо права."""
    env = tsm_ingest.ingest({"text": TEXT_0926, "domain": "fojfnpiot.pro"})
    assert env["domain"] == "fojfnpiot.pro"
    hard = [v for v in env["verdicts"] if not v["soft"]]
    assert len(hard) == 4, hard
    assert env["shapes"] == ["text"], env["shapes"]


def test_yellow_section_stays_yellow_in_prose():
    """Жовте не роутиться ніколи. Тут воно приходить під їхнім заголовком
    «Посмотреть глазами (не дефект…)» — і мусить лишитись позначеним."""
    env = tsm_ingest.ingest({"text": TEXT_0926})
    soft = [v for v in env["verdicts"] if v["soft"]]
    assert len(soft) == 1 and "Поменять картинку" in soft[0]["line"], soft


def test_self_naming_fallback_gives_us_the_name():
    """`hygiene: Нет <title>` — їхній фолбек для перевірки без гілки поради.
    Ім'я треба забрати: воно точніше за будь-який розбір прози."""
    env = tsm_ingest.ingest({"text": TEXT_0926})
    assert "hygiene" in _names(env)


def test_short_support_format_is_accepted_too():
    """Формат `advice_summary`, на якому якорі дають 11%. Прийняти його
    ми зобов'язані: саме він тепер перша вкладка в їхньому UI."""
    env = tsm_ingest.ingest({"fix": SUMMARY_0926})
    assert len([v for v in env["verdicts"] if not v["soft"]]) == 3
    assert env["shapes"] == ["fix"]


# ------------------------------------------------------------- структура

def test_structured_checks_are_taken_as_is():
    env = tsm_ingest.ingest({"checks": SLICE["checks"], "domain": "x.pro"})
    assert "links" in _names(env) and "naming" in _names(env)


def test_passed_check_with_warnings_is_yellow_not_green():
    """hygiene у них НІКОЛИ не червоніє (жодного `passed: False` у файлі) —
    уся знахідка лежить у warnings. Прийняти її як пройдену означало б
    мовчки загубити цілий ярус їхньої роботи."""
    env = tsm_ingest.ingest({"checks": SLICE["checks"]})
    assert "hygiene" in _names(env, soft=True), env["verdicts"]
    assert "hygiene" not in _names(env, soft=False)


def test_fully_passed_check_is_ignored():
    """`form` пройдена і без warnings — її в вердиктах бути не повинно."""
    env = tsm_ingest.ingest({"checks": SLICE["checks"]})
    assert "form" not in _names(env)


def test_bare_list_of_names_is_a_valid_request():
    """«Список імен» — теж законна форма. Змушувати той бік загортати її
    в об'єкти було б рівно тією правкою, якої ми домовились уникати."""
    env = tsm_ingest.ingest({"checks": ["links", "emails"]})
    assert _names(env) == ["links", "emails"]


def test_structure_beats_prose():
    """Один дефект у трьох форматах — це ОДИН дефект.

    Той бік шле `fix`, `front` і `text` одночасно: це три аудиторії однієї
    знахідки. Без цього правила домен із чотирма дефектами перетворився б на
    дюжину вердиктів, а захист від кола рахує коло по НАБОРУ чеків — тобто
    роздутий набір ламав би саме його.
    """
    env = tsm_ingest.ingest(SLICE)
    hard = [v for v in env["verdicts"] if not v["soft"]]
    assert sorted(v["name"] for v in hard) == ["links", "naming"], hard
    assert all(v["kind"] == "check" for v in hard), hard


# --------------------------------------------- вітка і «чий це дефект»

def test_branch_is_recovered_from_their_own_report_line():
    """`ИСХОДНИКИ ВАЙТА (ветка «X», файлов N)` — рядок, який whitesrc пише
    сам з 21.08. Це найдешевше джерело імені вітки: точне, з їхньої ж бази
    заливки, і не потребує від них жодної правки."""
    env = tsm_ingest.ingest({"text": WHITESRC})
    assert env["branch"] == "orxqal-stnaker-sg-en", env["branch"]


def test_the_whitesrc_block_is_metadata_not_a_complaint():
    """З блоку ми беремо вітку і origin, але самі його рядки — не скарга.

    Живий прогін 27.08: заголовок блоку доїжджав у «прозу», а звідти в
    модель — тобто ми платили за розбір їхньої ж службової довідки. Гірше,
    його рядки виглядають як вердикти («• links [/servicios]: …») і
    подвоювали б набір чеків, а по набору рахується коло.
    """
    env = tsm_ingest.ingest({"text": TEXT_0926 + "\n" + WHITESRC})
    assert env["branch"] == "orxqal-stnaker-sg-en"
    assert env["origin"] == "generator"
    assert not any("ИСХОДНИКИ" in p for p in env["prose"]), env["prose"]
    assert not any("исходниках" in (v["line"] or "").lower()
                   for v in env["verdicts"]), env["verdicts"]
    # а самі вердикти зі звіту лишились на місці
    assert len([v for v in env["verdicts"] if not v["soft"]]) == 4


def test_branch_from_payload_wins_over_text():
    env = tsm_ingest.ingest({"text": WHITESRC, "branch": "explicit-branch"})
    assert env["branch"] == "explicit-branch"


def test_origin_generator_is_read_from_their_verdict():
    """«дефект генератора» = лікується з коду вітки, тобто це наша робота."""
    assert tsm_ingest.ingest({"text": WHITESRC})["origin"] == "generator"


def test_origin_deploy_is_read_too():
    """«потерялись при выкладке» = з коду вітки не лікується взагалі.
    Прогін чеків по такому — витрачений знімок і витрачене коло."""
    txt = ("ИСХОДНИКИ ВАЙТА (ветка «b», файлов 10):\n"
           "  • health: файлы в исходниках ЕСТЬ — значит потерялись при "
           "выкладке, смотреть деплой и хостинг")
    assert tsm_ingest.ingest({"text": txt})["origin"] == "deploy"


def test_origin_mixed_when_both_are_named():
    txt = ("• links: этих файлов НЕТ и в исходниках — дефект генератора\n"
           "• health: файлы есть — потерялись при выкладке")
    assert tsm_ingest.ingest({"text": txt})["origin"] == "mixed"


# ------------------------------------------------------------- дрібниці

def test_all_ok_is_recognised():
    assert tsm_ingest.ingest({"text": "Всё ок — фиксить нечего."})["all_ok"]


def test_human_prose_survives_as_rest():
    """Те, що написала людина, не мусить зникнути: саме воно далі йде
    в слова і в модель."""
    env = tsm_ingest.ingest({"text": "в подвале почта на чужом домене"})
    assert env["prose"] == ["в подвале почта на чужом домене"]
    assert env["verdicts"] == []


def test_empty_payload_does_not_crash():
    env = tsm_ingest.ingest({})
    assert env["verdicts"] == [] and env["prose"] == []
    assert tsm_ingest.ingest(None)["verdicts"] == []


def test_as_text_round_trips_into_a_readable_line():
    """Структуру треба вміти показати текстом — і в журналі, і моделі.
    Збираємо в ЇХНЬОМУ ж вигляді «имя: логи», щоб рядок був упізнаваним."""
    env = tsm_ingest.ingest({"checks": SLICE["checks"]})
    txt = tsm_ingest.as_text(env)
    assert "links: • 404" in txt, txt
    assert "👁" in txt                       # жовте лишилось позначеним


def test_limits_hold_against_a_runaway_payload():
    """Дані приходять по HTTP від чужого застосунку: без стелі один
    зациклений прогін роздув би і журнал, і промпт моделі."""
    many = [{"name": f"c{i}", "passed": False, "logs": ["x" * 5000]}
            for i in range(500)]
    env = tsm_ingest.ingest({"checks": many})
    assert len(env["verdicts"]) == tsm_ingest.MAX_VERDICTS
    assert all(len(l) <= tsm_ingest.MAX_LINE
               for v in env["verdicts"] for l in v["logs"])


if __name__ == "__main__":
    run(dict(globals()))
