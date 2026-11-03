"""Чому саме не пройшов коміт — і чи це взагалі видно.

28.08 колега натиснув «Закомітити фікси» на проді й отримав рівно один рядок:
«Закомічено у 0 віток; помилки: 20». З'ясувати причину не було з чого:

  * `requests.raise_for_status()` каже «403 Client Error: Forbidden for url…»
    і ВИКИДАЄ тіло — а GitLab пише сенс саме туди («You are not allowed to
    push into this branch», «insufficient_scope», ім'я захищеної вітки);
  * UI показував лічильник і мовчав про `reason`, який сервер уже повертав;
  * «no changes» (нема чого комітити — нормальний стан) лічилось як помилка;
  * у логах контейнера не лишалось жодного рядка.

Тут закріплені всі чотири.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

import requests                                                   # noqa: E402

from gitlab_client import GitLabClient                             # noqa: E402

APP_SRC = (ROOT / "app.py").read_text(encoding="utf-8")
UI_SRC = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


class _Resp:
    """Рівно те, що читає `_check`."""

    def __init__(self, code, reason, payload=None, text=""):
        self.status_code = code
        self.reason = reason
        self.ok = code < 400
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _boom(resp):
    try:
        GitLabClient._check(resp)
    except requests.HTTPError as e:
        return str(e)
    raise AssertionError("не кинуто HTTPError")


# ------------------------------------------------- тіло відповіді

def test_gitlab_message_survives_into_the_error():
    """Головне: пояснення GitLab мусить дійти до людини дослівно. Саме воно
    відрізняє «токен без прав» від «вітка захищена»."""
    msg = _boom(_Resp(403, "Forbidden",
                      {"message": "You are not allowed to push into this branch"}))
    assert "You are not allowed to push into this branch" in msg, msg
    assert "403" in msg


def test_error_key_is_read_too():
    """Частина відповідей GitLab кладе текст під `error`, а не `message`
    (наприклад, відмова за скоупом токена)."""
    msg = _boom(_Resp(401, "Unauthorized", {"error": "insufficient_scope"}))
    assert "insufficient_scope" in msg, msg


def test_non_json_body_is_not_lost():
    """502 від проксі приходить html-сторінкою. Хай краще буде обрізаний
    текст, ніж порожньо."""
    msg = _boom(_Resp(502, "Bad Gateway", None, "<html>bad gateway</html>"))
    assert "bad gateway" in msg.lower(), msg


def test_silent_body_still_says_something():
    """Порожнє тіло — теж відповідь. Рядок не має вироджуватись у код без слів."""
    msg = _boom(_Resp(500, "Internal Server Error", None, ""))
    assert "500" in msg and "не пояснив" in msg, msg


def test_ok_passes_through():
    r = _Resp(200, "OK", {"id": "abc"})
    assert GitLabClient._check(r) is r


def test_no_bare_raise_for_status_is_left():
    """Один голий виклик повертає нас у вихідну точку: помилка знову без тіла.
    Рядок у docstring не рахуємо — він там навмисно."""
    src = (ROOT / "gitlab_client.py").read_text(encoding="utf-8")
    assert "r.raise_for_status()" not in src, \
        "лишився виклик, що з'їдає пояснення GitLab"


# ------------------------------------------------- чи це видно людині

def test_failed_commit_reaches_the_log():
    """Прод не має UI перед очима — лишається лог контейнера. До 28.08 там не
    було нічого."""
    body = APP_SRC[APP_SRC.index("def fix_apply("):]
    body = body[:body.index("\n@app.")]
    assert "[fix_apply]" in body, "відмова коміту нікуди не пишеться"
    assert re.search(r"print\(f\"\[fix_apply\][^\"]*\{e\}", body), body


def test_ui_shows_the_reason_and_not_just_a_count():
    """`reason` сервер повертав завжди — UI його викидав."""
    body = UI_SRC[UI_SRC.index("$('#fixApply').onclick"):]
    body = body[:body.index("\n};")]
    assert "r.reason" in body, "UI досі не читає reason"
    assert "fixErr" in body, "немає місця, де відмова лишається на екрані"


def test_nothing_to_commit_is_not_counted_as_an_error():
    """«no changes» — нормальний стан (повторний Apply, знятий вибір). Поки він
    лічився помилкою, «помилки: 20» не означало нічого."""
    body = UI_SRC[UI_SRC.index("$('#fixApply').onclick"):]
    body = body[:body.index("\n};")]
    assert "'no changes'" in body, "«нема чого комітити» знову в одному кошику з відмовами"
    idle = body.index("const idle=")
    bad = body.index("const bad=")
    assert "r.reason==='no changes'" in body[idle:bad]
    assert "r.reason!=='no changes'" in body[bad:]


def test_the_toast_no_longer_derives_errors_by_subtraction():
    """`res.length-ok.length` і був тим лічильником, що зліпив докупи відмову
    прав і «нема чого робити»."""
    body = UI_SRC[UI_SRC.index("$('#fixApply').onclick"):]
    body = body[:body.index("\n};")]
    assert "res.length-ok.length" not in body, body


if __name__ == "__main__":
    run(dict(globals()))
