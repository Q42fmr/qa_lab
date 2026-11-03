"""Заявка на фікс картинок із коментарів ClickUp.

Еталон — реальний коментар таски [p-52] (id 868kk71xf):

    @Nora Frontend возьмешь пожалуйста на фикс картинок
    padzarokss.pro поездка на полуостров, свадебный банкет, сезон на побережье
    quuifass.pro поездка в горы, программа для групп, Проживание на месяц
    padzarok-br-pt
    quuifa-br-pt
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                # noqa: E402

sys.path.insert(0, str(ROOT))
import comment_themes as ct                                   # noqa: E402

REQUEST = (
    "@Nora Frontend возьмешь пожалуйста на фикс картинок\n"
    "padzarokss.pro поездка на полуостров, свадебный банкет, сезон на побережье\n"
    "quuifass.pro поездка в горы, программа для групп, Проживание на месяц\n"
    "padzarok-br-pt\n"
    "quuifa-br-pt\n"
)
DEPLOY = (
    "project: black-pages\n"
    "deploys:\n"
    "- domain: padzarokss.pro\n"
    "  white: padzarok-br-pt\n"
    "- domain: quuifass.pro\n"
    "  white: quuifa-br-pt\n"
)
BRANCHES = ["onpovou-br-pt", "orgeh-br-pt", "padzarok-br-pt",
            "prudfeko-br-pt", "quuifa-br-pt"]
DOMAINS = ["onpovoufst.pro", "orgehlsr.pro", "padzarokss.pro",
           "prudfekoss.pro", "quuifass.pro"]


def _task(comments, domains=None):
    return {"id": "868kk71xf", "name": "[p-52]", "branches": BRANCHES,
            "domains": DOMAINS if domains is None else domains,
            "comments": [{"text": t, "date": str(1000 + i), "user": "Theo"}
                         for i, t in enumerate(comments)]}


# ------------------------------------------------------------------ розбір
def test_request_lines_become_themes():
    got = ct.parse(REQUEST, BRANCHES)
    themes = {i["domain"]: i["theme"] for i in got if i["domain"]}
    assert themes["padzarokss.pro"] == "поездка на полуостров, свадебный банкет, сезон на побережье"
    assert themes["quuifass.pro"] == "поездка в горы, программа для групп, Проживание на месяц"


def test_branch_only_line_has_no_theme():
    got = {i["branch"]: i["theme"] for i in ct.parse(REQUEST, BRANCHES) if i["branch"]}
    assert got == {"padzarok-br-pt": "", "quuifa-br-pt": ""}


def test_comment_not_about_photos_is_ignored():
    """Проза з доменом — не тема. Без цього гейта будь-яке обговорення
    домену ставало б темою пошуку фото."""
    prose = ("facibi-edumd.club этот до сих пор после отправки формы "
             "нас перекидывает на чужой домен")
    assert ct.parse(prose, BRANCHES) == []


def test_deploy_yaml_is_not_a_theme():
    assert ct.parse("на фикс картинок\n" + DEPLOY, BRANCHES) == []


def test_sentence_tail_is_not_a_theme():
    txt = "фикс картинок\npadzarokss.pro тут не работает. Посмотри пожалуйста!"
    assert [i["theme"] for i in ct.parse(txt, BRANCHES)] == [""]


def test_url_tail_is_not_a_theme():
    txt = "фикс картинок\npadzarokss.pro https://example.com/page"
    assert [i["theme"] for i in ct.parse(txt, BRANCHES)] == [""]


# ------------------------------------------------------- звʼязка домен↔вітка
def test_explicit_pairs_win():
    """Деплой-коментар дає пряму пару — найнадійніше джерело."""
    got = ct.themes_for_task(_task([DEPLOY, REQUEST], domains=[]))
    assert set(got) == {"padzarok-br-pt", "quuifa-br-pt"}
    assert got["padzarok-br-pt"]["domain"] == "padzarokss.pro"


def test_task_fields_pair_by_index():
    got = ct.themes_for_task(_task([REQUEST]))
    assert got["quuifa-br-pt"]["theme"].startswith("поездка в горы")


def test_prefix_match_when_no_pairs_and_no_fields():
    """Ні пар, ні полів — лишається бренд+короткий хвіст."""
    t = _task([REQUEST], domains=[])
    got = ct.themes_for_task(t)
    assert got["padzarok-br-pt"]["domain"] == "padzarokss.pro"


def test_domain_fits_is_a_prefix_not_a_substring():
    assert ct.domain_fits("padzarokss.pro", "padzarok-br-pt")
    assert not ct.domain_fits("quuifass.pro", "padzarok-br-pt")
    # хвіст довший за 5 символів — це вже інше слово
    assert not ct.domain_fits("padzarokvebhhegn.pro", "padzarok-br-pt")


def test_newer_comment_wins():
    old = "фикс картинок\npadzarokss.pro старая тема"
    t = _task([old, REQUEST])
    assert t["comments"][1]["date"] > t["comments"][0]["date"]
    got = ct.themes_for_task(t)
    assert got["padzarok-br-pt"]["theme"].startswith("поездка на полуостров")


def test_unknown_branch_token_is_skipped():
    txt = "фикс картинок\nsome-other-branch тема яка не наша"
    assert ct.parse(txt, BRANCHES) == []


if __name__ == "__main__":
    run(dict(globals()))
