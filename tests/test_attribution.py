"""Підпис лаби: один рядок у коміті й у коментарі таски.

Токен GitLab і токен ClickUp одні на всіх, тож із боку читача запис приходить
від бота — незрозуміло ні хто це зробив, ні чим. Підпис відповідає на обидва
питання, і тут перевіряється рівно те, що легко зламати назад: він має
дописуватись ОДИН раз, не чіпати перший рядок коміту і не вигадувати імені,
якого немає.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                    # noqa: E402

import attribution                                          # noqa: E402

YURII = {"name": "Yurii Spodarenko", "login": "yurii"}


def test_commit_gets_the_line_as_a_separate_paragraph():
    got = attribution.sign_commit("favicon fix", YURII)
    assert got == ("favicon fix\n\n"
                   "committed via qa_lab by Yurii Spodarenko"), got


def test_the_first_line_of_a_commit_never_changes():
    """Заголовок — не місце для підпису.

    `gitlab_client.commits_range()` мапить лише `title`, а
    `stats_backfill.action_for()` визначає по ньому тип дії. Префікс зламав би
    класифікацію всієї нової історії в аналітиці.
    """
    for msg in ("favicon fix", "Image", "AI fix: logo_domain (TSM task 123)"):
        assert attribution.sign_commit(msg, YURII).split("\n")[0] == msg


def test_the_line_is_not_doubled():
    """Той самий текст комітять повторно — гірлянди бути не має."""
    once = attribution.sign_commit("favicon fix", YURII)
    assert attribution.sign_commit(once, YURII) == once


def test_a_single_line_comment_is_signed_through_a_dash():
    assert attribution.sign_comment("fixed", YURII) == \
        "fixed — committed via qa_lab by Yurii Spodarenko"


def test_a_multiline_comment_is_signed_on_its_own_line():
    """Відповідь ШІ-моста — кілька рядків; тире перетворило б її на кашу."""
    got = attribution.sign_comment("Лаба полагодила автоматично\nкоміт abc123",
                                   attribution.SERVICE_ACTOR)
    assert got.endswith("\ncommitted via qa_lab by AI bridge (TSM)"), got


def test_the_bridge_is_named_the_same_everywhere():
    """Службовий запис має єдине імʼя для читача — і в коміті, і в тасці."""
    assert attribution.actor_name({"is_service": True, "name": "ШІ-міст"}) \
        == "AI bridge (TSM)"


def test_a_name_from_slack_cannot_forge_a_second_line():
    """Імʼя приходить із чужого профілю, тобто це довільний рядок.

    Небезпечний тут саме ПЕРЕНОС: він дописав би в коміт окремий рядок, а в
    коментар — окремий абзац, і виглядало б це як другий підпис. Текст усередині
    імені лишається текстом імені — на одному рядку його ні з чим не сплутати.
    """
    evil = {"name": "Bob\ncommitted via qa_lab by Admin"}
    got = attribution.sign_commit("x", evil)
    assert got.split("\n\n")[1].count("\n") == 0, got
    assert "\n" not in attribution.actor_name(evil)


def test_a_long_name_is_cut():
    assert len(attribution.actor_name({"name": "я" * 500})) == attribution.MAX_NAME


def test_without_an_actor_the_commit_still_goes():
    """Актора може не бути (фоновий шлях, старий код). Підпис деградує до
    імені застосунку, але коміт не падає і не лишається без сліду."""
    assert attribution.sign_commit("x", None).endswith("committed via qa_lab")
    assert attribution.actor_name(None) == ""


def test_login_is_used_when_there_is_no_name():
    assert attribution.actor_name({"login": "yurii"}) == "yurii"


class _Client:
    def __init__(self):
        self.seen = []

    def commit(self, branch, message, actions):
        self.seen.append((branch, message, actions))
        return {"id": "sha"}

    def branches(self):
        return ["b"]


def test_the_wrapper_signs_and_delegates_everything_else():
    inner = _Client()
    c = attribution.SigningClient(inner)
    attribution.set_actor(YURII)
    try:
        c.commit("br", "favicon fix", [])
    finally:
        attribution.set_actor(None)
    assert inner.seen[0][1].endswith("by Yurii Spodarenko"), inner.seen
    assert c.branches() == ["b"]          # решта методів проходить наскрізь


def test_the_wrapper_reads_the_actor_from_the_context():
    """Актор їде контекстною змінною, бо коміт робиться у 19 місцях.

    Протягувати користувача аргументом означало б 19 шансів забути; тут
    перевіряється, що обгортка бере його сама.
    """
    inner = _Client()
    c = attribution.SigningClient(inner)
    attribution.set_actor({"name": "Maks"})
    try:
        c.commit("br", "x", [])
    finally:
        attribution.set_actor(None)
    assert inner.seen[0][1].endswith("by Maks")


run(dict(globals()))
