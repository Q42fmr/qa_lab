"""«Увійти через Slack» — OpenID Connect.

Це auth-режим Slack (окремий від бот-скоупів): звичайний OAuth 2.0 з
редіректом. Ендпоінти:

    authorize  https://slack.com/openid/connect/authorize
    token      https://slack.com/api/openid.connect.token
    userinfo   https://slack.com/api/openid.connect.userInfo

З відповіді беремо три речі:
    sub                              → Slack-id користувача (`U…`), ключ входу
    "https://slack.com/team_id"      → воркспейс; звіряється з SLACK_TEAM_ID
    name / email                     → лише для відображення

`id_token` навмисно не верифікуємо через JWKS: код обмінюється на токен
запитом сервер-до-сервера по TLS, і `userInfo` тягнеться так само. Підпис
додав би третю бібліотеку, не додавши гарантії — джерело даних те саме.

Без заданих SLACK_CLIENT_ID/SECRET/TEAM_ID модуль просто вимкнений:
`enabled()` віддає False, кнопка на екрані входу не показується.
"""
from __future__ import annotations

import os
import secrets
import threading
import time
import urllib.parse

import requests

AUTHORIZE_URL = "https://slack.com/openid/connect/authorize"
TOKEN_URL = "https://slack.com/api/openid.connect.token"
USERINFO_URL = "https://slack.com/api/openid.connect.userInfo"

SCOPES = "openid profile email"

# Скільки живе `state`. Це вікно між натисканням кнопки і поверненням зі
# Slack — хвилин п'яти вистачає з запасом навіть на ручний логін у браузері.
_STATE_TTL = 300

_states: dict[str, float] = {}
_states_lock = threading.Lock()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def enabled() -> bool:
    """Увімкнено лише коли задані ВСІ ТРИ значення.

    `SLACK_TEAM_ID` у цій трійці не для повноти: без нього `check_team()`
    відмовляє в самому кінці потоку — людина побачила б кнопку, сходила у
    Slack і повернулась на «цей Slack-воркспейс не наш». Напівзаданий конфіг
    трапляється саме тоді, коли CI-змінні заводять частинами, тому кнопку
    краще не показувати взагалі, поки трійка неповна.
    """
    return bool(_env("SLACK_CLIENT_ID") and _env("SLACK_CLIENT_SECRET")
                and _env("SLACK_TEAM_ID"))


def redirect_uri() -> str:
    """Куди Slack повертає. Явний SLACK_REDIRECT_URI, інакше виводимо з
    домену — щоб не тримати одне й те саме у двох змінних."""
    explicit = _env("SLACK_REDIRECT_URI")
    if explicit:
        return explicit
    domain = _env("DOMAIN_NAME")
    if domain:
        return f"https://{domain}/api/auth/slack/callback"
    return ""


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------
def issue_state() -> str:
    """Одноразовий `state` — захист від CSRF на редіректі.

    Зберігається в пам'яті процесу: реплік рівно одна (стан лаби у файлах,
    масштабування виключене за конструкцією), тож зовнішнє сховище тут було б
    зайвою деталлю.
    """
    token = secrets.token_urlsafe(24)
    now = time.time()
    with _states_lock:
        for old, born in list(_states.items()):
            if now - born > _STATE_TTL:
                _states.pop(old, None)
        _states[token] = now
    return token


def consume_state(token: str | None) -> bool:
    """Перевіряє і ОДРАЗУ гасить — повторно той самий state не пройде."""
    if not token:
        return False
    with _states_lock:
        born = _states.pop(token, None)
    return born is not None and time.time() - born <= _STATE_TTL


# --------------------------------------------------------------------------
# потік
# --------------------------------------------------------------------------
def authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": _env("SLACK_CLIENT_ID"),
        "scope": SCOPES,
        "redirect_uri": redirect_uri(),
        "state": state,
    }
    team = _env("SLACK_TEAM_ID")
    if team:
        # Підказка Slack-у, у якому воркспейсі логінитись. Це зручність, а не
        # захист: справжня перевірка team_id — після обміну коду.
        params["team"] = team
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)


def exchange_code(code: str, http=None) -> dict:
    """Код → токени. `http` підміняється в тестах."""
    http = http or requests
    r = http.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": _env("SLACK_CLIENT_ID"),
        "client_secret": _env("SLACK_CLIENT_SECRET"),
        "redirect_uri": redirect_uri(),
    }, timeout=20)
    data = r.json()
    if not data.get("ok", False):
        raise ValueError(f"Slack відмовив на обміні коду: {data.get('error')}")
    return data


def fetch_userinfo(access_token: str, http=None) -> dict:
    http = http or requests
    r = http.get(USERINFO_URL,
                 headers={"Authorization": f"Bearer {access_token}"},
                 timeout=20)
    data = r.json()
    if not data.get("ok", False):
        raise ValueError(f"Slack відмовив на userInfo: {data.get('error')}")
    return data


def profile_from_userinfo(info: dict) -> dict:
    """Витягує три поля, які нам потрібні, з характерних для Slack ключів
    вигляду `https://slack.com/team_id`."""
    return {
        "slack_user_id": info.get("sub") or info.get("https://slack.com/user_id") or "",
        "team_id": info.get("https://slack.com/team_id") or "",
        "name": info.get("name") or "",
        "email": info.get("email") or "",
    }


def check_team(team_id: str) -> None:
    """Головна перевірка «наш чи не наш».

    Порожній SLACK_TEAM_ID — це відкриті двері для будь-якого Slack-акаунта
    в інтернеті, тож відмовляємо голосно, а не «про всяк випадок пускаємо».
    """
    expected = _env("SLACK_TEAM_ID")
    if not expected:
        raise ValueError(
            "SLACK_TEAM_ID не заданий — вхід через Slack вимкнено, "
            "інакше зайти міг би будь-який Slack-акаунт")
    if team_id != expected:
        raise ValueError("цей Slack-воркспейс не наш")


def login_profile(code: str, http=None) -> dict:
    """Повний шлях: код → токен → профіль → перевірка воркспейсу."""
    tokens = exchange_code(code, http=http)
    access = tokens.get("access_token") or ""
    if not access:
        raise ValueError("Slack не повернув access_token")
    prof = profile_from_userinfo(fetch_userinfo(access, http=http))
    if not prof["slack_user_id"]:
        raise ValueError("Slack не повернув ідентифікатор користувача")
    check_team(prof["team_id"])
    return prof
