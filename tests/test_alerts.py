"""Проблемний домен має ВИСІТИ на очах, а не чекати, поки його знайдуть.

Дві половини однієї вади.

Серверна: у журнал проблем ішла лише ВІТКА. Скарга від TSM приходить на живий
домен, і людина шукає по домену — звʼязувати його з віткою доводилось руками.

Клієнтська: лічильник проблем на вкладці «Журнал» оновлював `loadProblems()`,
а той викликався ЛИШЕ при відкритті під-вкладки «Проблеми». Тобто бейдж, який
мав покликати людину у вкладку, не зʼявлявся, доки вона ту вкладку не
відкриє. Сигналу не було взагалі.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

import ai_bridge                                                  # noqa: E402
from test_ai_bridge import Fake, _job                             # noqa: E402

INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


# ------------------------------------------------------------- сервер

def test_a_problem_carries_the_domain_not_only_the_branch():
    only_diag = lambda: [{"id": "logo_domain", "fixable": False, "group": "tests"}]
    with Fake(catalog=only_diag) as f:
        ai_bridge.execute(_job(domain="grolriv-paloij.ch"))
    assert f.problems, "нічого не потрапило в журнал проблем"
    assert f.problems[0]["domain"] == "grolriv-paloij.ch", f.problems[0]
    assert f.problems[0]["branch"] == "x-br-pt", f.problems[0]


def test_a_problem_without_a_domain_still_records():
    """Sync і import домену не знають — запис має лишатись валідним."""
    only_diag = lambda: [{"id": "logo_domain", "fixable": False, "group": "tests"}]
    with Fake(catalog=only_diag) as f:
        ai_bridge.execute(_job())
    assert f.problems and f.problems[0]["domain"] == "", f.problems[0]


def test_the_store_keeps_the_domain_field():
    """`add_problems` дедупить по (branch, source) і кладе запис як є —
    перевіряємо, що нове поле не губиться дорогою."""
    import app
    import projects
    import tempfile
    from pathlib import Path
    old = projects.state_file
    tmp = Path(tempfile.mkdtemp(prefix="probs-"))
    projects.state_file = lambda name: tmp / name
    try:
        app.add_problems([{"branch": "b1", "domain": "d1.com",
                           "source": "ai-bridge", "reason": "нема автофікса"}])
        got = app.load_problems()
    finally:
        projects.state_file = old
    assert got and got[0]["domain"] == "d1.com", got


# ------------------------------------------------------------- смуга в UI

def test_the_ui_has_a_place_where_a_problem_hangs():
    assert 'id="alerts"' in INDEX, "смуги алертів більше немає"
    assert re.search(r'</header>\s*(<!--[\s\S]*?-->\s*)?<div id="alerts"', INDEX), \
        "смуга має бути одразу під шапкою, а не всередині вкладки"


def test_the_bar_shows_the_domain_first():
    """Людина шукає по домену — з нього рядок і починається."""
    assert "x.domain||x.branch" in INDEX.replace(" ", ""), \
        "у рядку смуги більше не видно домену"


def test_the_counter_does_not_wait_for_the_tab_to_be_opened():
    """Та сама вада, що це правило й породила."""
    assert re.search(r"^refreshProbBadge\(\);", INDEX, re.M), \
        "лічильник проблем більше не оновлюється на старті сторінки"
    assert "setInterval(refreshProbBadge" in INDEX, \
        "лічильник більше не оновлюється сам"


def test_the_bar_survives_a_reload():
    """«Висить» означає «живе на сервері», а не «поки не оновили сторінку»:
    смуга малюється з `/api/problems`, а не з памʼяті вкладки."""
    i = INDEX.index("async function refreshProbBadge")
    body = INDEX[i:i + 700]
    assert "/api/problems" in body and "renderAlerts(p)" in body, body[:200]


def test_the_bar_cannot_eat_the_screen():
    """Заміряно на 100 проблемних доменах: без стелі й без обрізання рядка
    смуга займала 398 px із 493 px екрана — тобто переставала бути сигналом і
    ставала стіною. Зі стелею тих самих 100 дають 128 px."""
    css = INDEX[INDEX.index("#alerts{"):INDEX.index("/* lighthouse */")]
    assert "max-height" in css and "overflow:auto" in css, css[:200]
    assert "white-space:nowrap" in css.replace(" ", ""), "рядок знову переноситься"
    assert "text-overflow:ellipsis" in css.replace(" ", ""), \
        "довга причина більше не обрізається"


def test_a_long_reason_keeps_its_full_text_in_the_title():
    """Обрізаний рядок не має ховати причину — вона лишається під курсором."""
    assert 'class="alwhy" title="${esc(x.reason' in INDEX


def test_many_problems_are_summed_up_by_source():
    """Коли їх десятки, важливо не «які саме пʼять», а скільки і звідки:
    sync — це недоступні вітки, ai-bridge — те, де автоматика безсила. Це
    різна робота для різних людей."""
    assert "function alertsSummary" in INDEX
    i = INDEX.index("function alertsSummary")
    body = INDEX[i:i + 400]
    assert "x.source" in body and "ще " in body, body[:200]


def test_the_bar_shows_only_a_few_rows_however_many_there_are():
    assert "p.slice(0,5)" in INDEX.replace(" ", ""), \
        "смуга більше не обмежує кількість рядків"


def test_the_table_does_not_rename_the_source():
    """Колонка «звідки» каже, ЧИЯ це робота: sync — лаба не дотяглась до вітки,
    ai-bridge — автоматика здалась, visual — впав прогін. Мапа була бінарна
    (`s==='sync' ? sync : import`), тож visual і ai-bridge малювались як
    IMPORT — а смуга над тією ж подією писала правду. Кейс 02.09: вітка
    nwf-rimag-tegn-sojidiihr-co-es, `visual` у смузі й `IMPORT` у таблиці."""
    i = INDEX.index("async function loadProblems()")
    body = INDEX[i:i + 1500]
    assert "SEVSRC" in body, "таблиця знову зводить джерела до двох"
    for name in ("sync", "import", "visual", "ai-bridge"):
        assert name in body, f"джерело {name} таблиця не знає"
    # незнайоме джерело має лишитись собою, а не стати найближчим знайомим
    assert "esc(s||'?')" in body.replace(" ", ""), \
        "невідоме джерело десь перейменовується"


def test_folding_the_bar_is_remembered():
    """Смуга не має перетворитись на те, що закривають щоразу."""
    assert "qa_lab_alerts_folded" in INDEX


if __name__ == "__main__":
    run(dict(globals()))
