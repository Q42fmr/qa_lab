"""Тести входу через Slack.

Мережі в тестах немає, тому HTTP підміняється: `exchange_code` і
`fetch_userinfo` приймають об'єкт `http` з методами `post`/`get`. Перевіряємо
не «чи ходить у Slack», а те, що вирішує все інше: одноразовість `state`,
відсікання чужого воркспейсу і поведінка за порожньої конфігурації.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import slack_oauth                                                # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Http:
    """Фейковий requests: віддає підготовлені відповіді й запам'ятовує виклики."""

    def __init__(self, token_payload, userinfo_payload):
        self.token_payload = token_payload
        self.userinfo_payload = userinfo_payload
        self.posts = []
        self.gets = []

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, data))
        return _Resp(self.token_payload)

    def get(self, url, headers=None, timeout=None):
        self.gets.append((url, headers))
        return _Resp(self.userinfo_payload)


def _configure(team="T_OURS"):
    os.environ["SLACK_CLIENT_ID"] = "cid"
    os.environ["SLACK_CLIENT_SECRET"] = "secret"
    os.environ["SLACK_TEAM_ID"] = team
    os.environ["SLACK_REDIRECT_URI"] = "https://qa-lab.example/api/auth/slack/callback"


def _unconfigure():
    for k in ("SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_TEAM_ID",
              "SLACK_REDIRECT_URI", "DOMAIN_NAME"):
        os.environ.pop(k, None)


def _userinfo(sub="U_ALEX", team="T_OURS"):
    return {
        "ok": True,
        "sub": sub,
        "https://slack.com/team_id": team,
        "name": "Alex",
        "email": "alex@corp.io",
    }


# --------------------------------------------------------------- вмикання

def test_disabled_without_credentials():
    _unconfigure()
    assert slack_oauth.enabled() is False


def test_enabled_with_credentials():
    _configure()
    try:
        assert slack_oauth.enabled() is True
    finally:
        _unconfigure()


def test_disabled_when_team_id_is_missing():
    """Напівзаданий конфіг — теж «вимкнено».

    Змінні заводять частинами, і найлегше забути саме TEAM_ID. Якби кнопка
    з'являлась від самих CLIENT_ID/SECRET, вхід ішов би до Slack і повертався
    відмовою `check_team()` — гірше, ніж просто не показати кнопку.
    """
    _configure()
    os.environ.pop("SLACK_TEAM_ID", None)
    try:
        assert slack_oauth.enabled() is False
    finally:
        _unconfigure()


def test_redirect_uri_is_derived_from_the_domain():
    """Щоб той самий хост не тримати у двох змінних."""
    _unconfigure()
    os.environ["DOMAIN_NAME"] = "lab.example.com"
    try:
        assert slack_oauth.redirect_uri() == \
            "https://lab.example.com/api/auth/slack/callback"
    finally:
        _unconfigure()


def test_explicit_redirect_uri_wins():
    _configure()
    os.environ["DOMAIN_NAME"] = "other.example"
    try:
        assert slack_oauth.redirect_uri().startswith("https://qa-lab.example/")
    finally:
        _unconfigure()


# --------------------------------------------------------------- state

def test_state_is_single_use():
    """Повторне використання того самого state не проходить — інакше
    перехоплене посилання спрацювало б удруге."""
    s = slack_oauth.issue_state()
    assert slack_oauth.consume_state(s) is True
    assert slack_oauth.consume_state(s) is False


def test_unknown_state_is_rejected():
    assert slack_oauth.consume_state("never-issued") is False
    assert slack_oauth.consume_state("") is False
    assert slack_oauth.consume_state(None) is False


def test_expired_state_is_rejected():
    s = slack_oauth.issue_state()
    with _frozen_state_age(s, slack_oauth._STATE_TTL + 5):
        assert slack_oauth.consume_state(s) is False


class _frozen_state_age:
    """Зістарює конкретний state, не чекаючи п'ять хвилин."""

    def __init__(self, token, seconds):
        self.token, self.seconds = token, seconds

    def __enter__(self):
        with slack_oauth._states_lock:
            slack_oauth._states[self.token] = time.time() - self.seconds

    def __exit__(self, *a):
        with slack_oauth._states_lock:
            slack_oauth._states.pop(self.token, None)


def test_authorize_url_carries_state_and_redirect():
    _configure()
    try:
        url = slack_oauth.authorize_url("ST8")
        assert url.startswith(slack_oauth.AUTHORIZE_URL + "?")
        assert "state=ST8" in url
        assert "client_id=cid" in url
        assert "openid" in url
        assert "team=T_OURS" in url
    finally:
        _unconfigure()


# --------------------------------------------------------------- воркспейс

def test_foreign_workspace_is_refused():
    """Головна перевірка «наш чи не наш»."""
    _configure(team="T_OURS")
    try:
        slack_oauth.check_team("T_SOMEONE_ELSE")
    except ValueError as e:
        assert "не наш" in str(e), e
        return
    finally:
        _unconfigure()
    raise AssertionError("чужий воркспейс мав бути відхилений")


def test_empty_team_setting_refuses_everyone():
    """Порожній SLACK_TEAM_ID — це відкриті двері для будь-якого Slack-акаунта
    в інтернеті, тому відмовляємо, а не пускаємо «про всяк випадок»."""
    _configure(team="")
    os.environ.pop("SLACK_TEAM_ID", None)
    try:
        slack_oauth.check_team("T_ANY")
    except ValueError as e:
        assert "SLACK_TEAM_ID" in str(e), e
        return
    finally:
        _unconfigure()
    raise AssertionError("без SLACK_TEAM_ID вхід мав бути відхилений")


# --------------------------------------------------------------- повний потік

def test_login_profile_happy_path():
    _configure()
    http = _Http({"ok": True, "access_token": "xoxp-test"}, _userinfo())
    try:
        prof = slack_oauth.login_profile("CODE", http=http)
        assert prof["slack_user_id"] == "U_ALEX", prof
        assert prof["team_id"] == "T_OURS", prof
        assert prof["email"] == "alex@corp.io", prof
        assert http.posts[0][0] == slack_oauth.TOKEN_URL
        assert http.gets[0][1]["Authorization"] == "Bearer xoxp-test"
    finally:
        _unconfigure()


def test_login_profile_rejects_foreign_team():
    _configure(team="T_OURS")
    http = _Http({"ok": True, "access_token": "t"}, _userinfo(team="T_OTHER"))
    try:
        slack_oauth.login_profile("CODE", http=http)
    except ValueError as e:
        assert "не наш" in str(e), e
        return
    finally:
        _unconfigure()
    raise AssertionError("чужий воркспейс мав бути відхилений")


def test_slack_error_on_token_exchange_is_raised():
    _configure()
    http = _Http({"ok": False, "error": "invalid_code"}, {})
    try:
        slack_oauth.login_profile("BAD", http=http)
    except ValueError as e:
        assert "invalid_code" in str(e), e
        return
    finally:
        _unconfigure()
    raise AssertionError("помилка Slack мала піднятись")


def test_missing_access_token_is_raised():
    _configure()
    http = _Http({"ok": True}, _userinfo())
    try:
        slack_oauth.login_profile("CODE", http=http)
    except ValueError as e:
        assert "access_token" in str(e), e
        return
    finally:
        _unconfigure()
    raise AssertionError("відсутній токен мав дати помилку")


def test_userinfo_without_subject_is_raised():
    _configure()
    bad = _userinfo()
    bad.pop("sub")
    http = _Http({"ok": True, "access_token": "t"}, bad)
    try:
        slack_oauth.login_profile("CODE", http=http)
    except ValueError as e:
        assert "ідентифікатор" in str(e), e
        return
    finally:
        _unconfigure()
    raise AssertionError("профіль без sub мав дати помилку")


if __name__ == "__main__":
    run(dict(globals()))
