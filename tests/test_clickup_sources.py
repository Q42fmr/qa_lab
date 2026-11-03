"""Недоступне вʼю не має гасити весь скан ClickUp.

01.09.2026 вкладка ClickUp у проді віддавала помилку замість тасок, і причина
виявилась не в швидкодії й не в мережі: сервісний акаунт `Tech Bot` не бачив
одного вʼю з трьох (`4-90000000002-1` — приватне, створене іншою людиною «для
себе»). ClickUp відповідав `403 ACCESS_132`, `raise_for_status()` у циклі по
вʼю валив увесь виклик, а два інші джерела в ту саму мить давали 444 таски з
445 — тобто гинув скан, якому бракувало однієї таски.

Друга половина тієї ж історії — чому цього не було видно НІДЕ: помилка йшла
кодом 502, а тіло 5xx Cloudflare підміняє власною сторінкою, тож у тості
лишалось голе «Bad Gateway». Тому відмова тепер має код 4xx (`app.py`), а
недоступні вʼю доповідаються окремим списком, а не мовчазним недобором.

У мережу тести не ходять: `_get` і `_team_id` підмінені.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                    # noqa: E402

import requests                                             # noqa: E402

import clickup_client                                       # noqa: E402

TEAM = "9000000001"
OK_VIEW, BAD_VIEW = "6-901109276296-1", "4-90000000002-1"


class Fail:
    """Вʼю, що відповідає помилкою. Окремий тип, а не число: інакше «вʼю з
    трьома тасками» і «вʼю з кодом 403» — обидва int, і підставний ClickUp
    плутає одне з одним (на чому цей тест уже спіймав себе)."""

    def __init__(self, code: int):
        self.code = code


def _resp(status: int, payload: dict) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r.url = "https://api.clickup.com/api/v2/…"
    r._content = json.dumps(payload).encode()
    r.headers["Content-Type"] = "application/json"
    return r


class _ClickUp:
    """Підставний ClickUp: team віддає `team_tasks`, вʼю — за словником."""

    def __init__(self, team_tasks: int = 2, views: dict | None = None):
        self.team_tasks = team_tasks
        self.views = views or {}

    def __enter__(self):
        self._env = {k: os.environ.get(k) for k in ("CLICKUP_TOKEN", "CLICKUP_VIEW_ID")}
        os.environ["CLICKUP_TOKEN"] = "pk_test"
        os.environ["CLICKUP_VIEW_ID"] = ",".join(self.views)
        self._get, self._team = clickup_client._get, clickup_client._team_id
        clickup_client._get = self._fake_get
        clickup_client._team_id = lambda headers: TEAM
        return self

    def __exit__(self, *exc):
        clickup_client._get, clickup_client._team_id = self._get, self._team
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _fake_get(self, url, headers, params=None):
        page = (params or {}).get("page", 0)
        if f"/team/{TEAM}/task" in url:
            got = [{"id": f"team{i}"} for i in range(self.team_tasks)] if page == 0 else []
            return _resp(200, {"tasks": got})
        for vid, behaviour in self.views.items():
            if f"/view/{vid}/task" in url:
                if isinstance(behaviour, Fail):
                    return _resp(behaviour.code,
                                 {"err": "You do not have access to this view",
                                  "ECODE": "ACCESS_132"})
                got = [{"id": f"{vid}-{i}"} for i in range(behaviour)] if page == 0 else []
                return _resp(200, {"tasks": got})
        raise AssertionError(f"несподіваний виклик: {url}")


def test_a_view_without_access_does_not_kill_the_scan():
    """Головне: таски двох інших джерел мають доїхати до людини.

    Саме цього не сталось 01.09 — 444 таски згоріли через одне вʼю."""
    with _ClickUp(team_tasks=2, views={OK_VIEW: 3, BAD_VIEW: Fail(403)}):
        skipped: list[dict] = []
        got = clickup_client.fetch_all(skipped=skipped)
    assert len(got) == 5, [t["id"] for t in got]
    assert len(skipped) == 1, skipped


def test_the_skipped_view_carries_clickups_own_reason():
    """Список пропущених — не прапорець, а текст: без коду `ACCESS_132` і
    слова «access» людина шукатиме проблему в правах воркспейсу, тоді як
    лікується вона шарингом самого вʼю."""
    with _ClickUp(views={BAD_VIEW: Fail(403)}):
        skipped: list[dict] = []
        clickup_client.fetch_all(skipped=skipped)
    assert skipped[0]["view"] == BAD_VIEW, skipped
    assert "ACCESS_132" in skipped[0]["reason"], skipped
    assert "access" in skipped[0]["reason"].lower(), skipped


def test_a_dead_clickup_still_raises():
    """5xx і таймаути — стан ТИМЧАСОВИЙ, і мовчки віддати неполовинений скан
    гірше, ніж не віддати нічого: наступний `cuSave()` затер би повний скан
    недоробленим."""
    with _ClickUp(views={OK_VIEW: Fail(500)}):
        try:
            clickup_client.fetch_all(skipped=[])
        except requests.HTTPError:
            return
    raise AssertionError("500 від вʼю проковтнуто — скан мовчки збіднів")


def test_the_team_source_is_not_optional():
    """Відмова в доступі до team-ендпоінта — це зламаний токен, а не приватне
    вʼю. Тут падати правильно, інакше вкладка показувала б порожнечу як
    норму."""
    with _ClickUp(views={}) as cu:
        cu.team_tasks = 0
        clickup_client._get = lambda url, headers, params=None: _resp(401, {"err": "Token invalid"})
        try:
            clickup_client.fetch_all(skipped=[])
        except requests.HTTPError:
            return
    raise AssertionError("401 на team-ендпоінті проковтнуто")


def test_skipped_is_optional():
    """`tg_watcher` кличе `fetch_all()` без списку — він не має падати на
    цьому."""
    with _ClickUp(views={BAD_VIEW: Fail(403)}):
        got = clickup_client.fetch_all()
    assert len(got) == 2, got


if __name__ == "__main__":
    run(dict(globals()))
