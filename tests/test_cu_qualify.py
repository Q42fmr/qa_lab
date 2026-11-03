"""Гейт «це наша таска» і його зчеплення з розміткою вкладки.

Правило на сервері (`clickup_client.passes_default_filters`) існує рівно тому,
що черга мусить брати ті самі таски, які бере людина. А «які бере людина»
задано не рішенням, а дефолтами галок у `static/index.html`: вони ніде не
зберігаються, тож кожне відкриття сторінки починає з них.

Тому тут два різні види перевірок:

* поведінкові — що саме правило пропускає і що відсіює;
* **гарда зчеплення** — читає розмітку і падає, щойно дефолт галки змінили, а
  правило на сервері ні. Без неї два правила розійшлися б мовчки, і черга
  почала б тягнути не те, що людина бачить очима.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                        # noqa: E402

import clickup_client                                           # noqa: E402

fits = clickup_client.passes_default_filters
INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"


def _task(**kw):
    base = {"branches": ["nwf-a"], "domains": ["a.blog"],
            "wtype": "1/2 круг", "status": "in progress",
            "status_type": "custom", "status_match": True,
            "checklist_loaded": True, "checklist_done": False}
    base.update(kw)
    return base


def _checked(cid: str) -> bool:
    """Чи стоїть галка `cid` за замовчуванням у розмітці вкладки."""
    m = re.search(r'<input type="checkbox" id="%s"([^>]*)>' % cid, INDEX.read_text(
        encoding="utf-8"))
    assert m, f"у розмітці немає галки {cid} — гарда застаріла"
    return "checked" in m.group(1)


# ------------------------------------------------------------- поведінка

def test_a_normal_deployment_task_fits():
    assert fits(_task())


def test_no_branches_no_pass():
    assert not fits(_task(branches=[]))


def test_no_white_type_no_pass():
    assert not fits(_task(wtype=None))


def test_no_domains_no_pass():
    """Питання команді 07.09 було прямим: «ці два параметри завжди жорстко
    заповнені?» — «завжди, звідти й беруться вітки і домени». Тож таска без
    Required Domains — не вайт-таска, хоч би що лежало в Safe Page.

    Заміряно того ж дня: серед 61, що проходять гейт, без доменів — 0.
    Умова не відсіює сьогодні нічого, вона робить правило точним."""
    assert not fits(_task(domains=[]))
    assert not clickup_client.looks_like_ours(_task(domains=[]))


def test_a_closed_task_never_fits():
    """Закриті вимикає `include_closed=False`, але вʼю віддає що віддає —
    тому умова перевіряється У НАС, а не покладається на джерело."""
    assert not fits(_task(status_type="closed"))


def test_a_task_we_already_closed_does_not_come_back():
    """`checklist_done` — не фільтр статусу, а власна позначка лаби «ми тут
    уже були». Коштує рівно одну таску зі 131 (заміряно 04.09.2026)."""
    assert not fits(_task(checklist_done=True))


def test_a_task_without_a_loaded_checklist_waits():
    """Так само поводиться кнопка імпорту: недовантажену таску не бере,
    бо `checklist_done` у неї ще невідомий."""
    assert not fits(_task(checklist_loaded=False))


def test_nomination_is_a_wider_rule_than_the_decision():
    """Найдорожча деталь цього правила.

    Вʼю не віддає чеклістів узагалі, а 129 зі 130 придатних тасок приходять
    саме з вʼю (заміряно 04.09.2026: зі скану повний гейт проходить ОДНА).
    Тому опит номінує по `looks_like_ours`, а вирішує вже виконавець — після
    того як таску дотягнули поштучно і чекліст відомий. Зведеш ці два
    правила в одне — і черга замовкне, не сказавши жодного слова.
    """
    from_view = _task(checklist_loaded=False)
    assert clickup_client.looks_like_ours(from_view), "опит мусить її номінувати"
    assert not fits(from_view), "а виконавець — дочекатись чекліста"


def test_nomination_still_drops_what_is_obviously_not_ours():
    assert not clickup_client.looks_like_ours(_task(branches=[]))
    assert not clickup_client.looks_like_ours(_task(wtype=None))
    assert not clickup_client.looks_like_ours(_task(status_type="closed"))
    assert not clickup_client.looks_like_ours(_task(checklist_done=True))


def test_the_status_is_a_filter():
    """Рішення замовника 07.09.2026, після першого живого прогону черги.

    Доти статус не перевірявся свідомо — і саме тому в чергу приїхали
    `qa` і `domains hold` («таке не має брати», «в QA теж не надо»).
    Заміряно того ж дня на живому воркспейсі: без статусу номінується 128
    тасок (645 віток), зі статусом — 70 (350); відпадає рівно 58 = `qa` (40)
    і `domains hold` (18), лишається `in progress` (53) і `to do` (17).

    Умова та сама, що показує галка вкладки: `status_match`, тобто підрядок
    з `CLICKUP_STATUSES` мінус `CLICKUP_STATUSES_EXCLUDE` (`content`).
    """
    assert not fits(_task(status="qa", status_match=False))
    assert not fits(_task(status="domains hold", status_match=False))
    assert fits(_task(status="in progress", status_match=True))
    # і номінація теж: статус приходить уже в списку, тож платити за такі
    # таски окремим запитом немає сенсу
    assert not clickup_client.looks_like_ours(_task(status_match=False))


# ------------------------------------------- гарда зчеплення з розміткою

def test_the_rule_matches_the_default_checkboxes():
    assert _checked("fSp"), "дефолт Safe Page змінився — правило теж має"
    assert _checked("fWt"), "дефолт «Тип вайта» змінився — правило теж має"
    assert _checked("fSt"), \
        "галку статусу зняли з дефолтів — тоді і черга має розширитись назад"
    assert _checked("fCl"), \
        "галку чекліста зняли з дефолтів, а правило досі відкидає зроблені"
    assert _checked("fDom"), \
        "галку доменів зняли з дефолтів, а правило їх досі вимагає"
    assert _checked("fBlk"), \
        "галку «без блеків» зняли з дефолтів, а правило досі їх відкидає"
    assert not _checked("fClosed"), "закриті за замовчуванням не тягнемо"


def test_a_black_is_never_ours():
    """Вимога замовника 07.09: блеки не беремо ніколи. Блек — це інша
    сторінка і інша робота: ні Safe Page, ні доменів у неї немає.

    Заміряно того ж дня: у воркспейсі 82 таски з тегом `blacks`, і жодна не
    проходила гейт ще й до цієї умови — їх відсікали порожній «Тип вайта» і
    статус. Тобто умова тут не тому, що щось ловить сьогодні, а тому, що її
    назвали прямо; ловитиме вона блек, якому колись заповнять поля.
    """
    assert not fits(_task(tag_excluded=True))
    assert not clickup_client.looks_like_ours(_task(tag_excluded=True))


def test_the_watchers_rule_stays_separate():
    """`tg_watcher` — код Олександра з ВУЖЧИМ правилом (зі `status_match`).
    Звести їх в одне не можна: його сповіщення у Telegram мовчки поїхали б
    з 74 тасок на 130."""
    import tg_watcher
    assert tg_watcher.passes_filters is not clickup_client.passes_default_filters
    # З 07.09 обидва дивляться на статус, але не збігаються: наше правило ще
    # й чекає на довантажений чекліст (вʼю його не віддає) і відкидає закриті.
    from_view = _task(checklist_loaded=False)
    assert tg_watcher.passes_filters(from_view) and not fits(from_view), \
        "правила зійшлись — вотчер почав бачити те, чого не бачив"


if __name__ == "__main__":
    run(dict(globals()))
