"""Особистий токен ClickUp: розшарені таски і фоллбеки.

Токен ClickUp завжди належить людині — «безособових» там немає. Тому таску,
віддану комусь персонально, застосунковий акаунт не бачить НІЯК: заміряно
01.09.2026, у робочому воркспейсі така таска одна, і сервісний `Tech Bot` не
дістає її за будь-якої конфігурації вʼю (вʼю — це збережений фільтр, а не
доступ).

Головне, що тут закріплено: особистий токен — ДОВАЖОК. Хоч би що з ним
сталось — протух, немає доступу, одруківка — видача застосункового акаунта
має доїхати цілою. «Менше тасок» погано, «жодної таски і незрозуміло чому» —
гірше.

У мережу тести не ходять.
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
APP_TOKEN, MY_TOKEN = "pk_app", "pk_mine"


def _resp(status: int, payload: dict) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r.url = "https://api.clickup.com/api/v2/…"
    r._content = json.dumps(payload).encode()
    r.headers["Content-Type"] = "application/json"
    return r


class _ClickUp:
    """Підставний ClickUp, який РОЗРІЗНЯЄ токени.

    Саме в цьому вся суть фічі: одна й та сама адреса віддає різне залежно
    від того, чий токен у заголовку.
    """

    def __init__(self, team_tasks=2, shared=("shared1",), shared_fails=False,
                 shared_for=None):
        self.team_tasks = team_tasks
        self.shared = list(shared)
        self.shared_fails = shared_fails
        # Кому саме віддається «Shared with me». За замовчуванням людині:
        # сервісний акаунт не бачить розшареного їй нічого.
        self.shared_for = shared_for or MY_TOKEN
        self.calls: list[tuple] = []

    def __enter__(self):
        self._env = {k: os.environ.get(k) for k in ("CLICKUP_TOKEN", "CLICKUP_VIEW_ID")}
        os.environ["CLICKUP_TOKEN"] = APP_TOKEN
        os.environ["CLICKUP_VIEW_ID"] = ""
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

    def _fake_get(self, url, headers, params=None, timeout=None):
        who = headers.get("Authorization")
        self.calls.append((url, who))
        page = (params or {}).get("page", 0)
        if f"/team/{TEAM}/shared" in url:
            if who != self.shared_for:     # чужого розшареного не видно
                return _resp(200, {"shared": {"tasks": []}})
            if self.shared_fails:
                return _resp(401, {"err": "Token invalid", "ECODE": "OAUTH_025"})
            # Ієрархія віддає таски ПОВНИМИ (заміряно 02.09.2026: `custom_fields`
            # і `checklists` на місці), тому підставний ClickUp теж має віддавати
            # їх повними — інакше тест дозволив би регресію в бік 173 запитів.
            return _resp(200, {"shared": {"tasks": [
                {"id": t, "name": f"таска {t}",
                 "status": {"status": "closed" if t.startswith("closed") else "to do",
                            "type": "closed" if t.startswith("closed") else "custom"},
                 "checklists": [], "custom_fields": []} for t in self.shared]}})
        if f"/team/{TEAM}/task" in url:
            got = [{"id": f"team{i}"} for i in range(self.team_tasks)] if page == 0 else []
            return _resp(200, {"tasks": got})
        if "/task/" in url:
            tid = url.rsplit("/", 1)[-1]
            if who != MY_TOKEN:
                return _resp(401, {"err": "no access"})
            return _resp(200, {"id": tid, "name": f"таска {tid}",
                               "status": {"status": "to do"}, "custom_fields": []})
        raise AssertionError(f"несподіваний виклик: {url}")


# ------------------------------------------------------------ токен-аргумент

def test_without_a_token_nothing_changes():
    """Дефолт лишається байт-у-байт тим самим: `tg_watcher`, статистика і
    ШІ-міст кличуть ці ж функції без токена."""
    with _ClickUp() as cu:
        got = clickup_client.fetch_all()
    assert sorted(t["id"] for t in got) == ["team0", "team1"], got
    assert all(who == APP_TOKEN for _, who in cu.calls), cu.calls


def test_an_explicit_token_wins_over_the_environment():
    with _ClickUp() as cu:
        clickup_client.fetch_all(token=MY_TOKEN)
    assert all(who == MY_TOKEN for _, who in cu.calls), cu.calls


# ------------------------------------------------------------ розшарені таски

def test_the_app_scan_never_touches_the_shared_source():
    """Вʼю і team — застосунковим токеном з CI, і тільки вони. Зайвий запит
    на кожен скан коштує 6 с, а персонально сервісному акаунту нічого не
    шарять."""
    with _ClickUp() as cu:
        base = clickup_client.fetch_all()
    assert not any("/shared" in url for url, _ in cu.calls), cu.calls
    assert "shared1" not in [t["id"] for t in base]


def test_shared_tasks_come_with_the_personal_token():
    with _ClickUp():
        mine = clickup_client.fetch_shared(MY_TOKEN)
    assert [t["id"] for t in mine] == ["shared1"], mine


def test_a_shared_task_arrives_parsed_not_as_a_stub():
    with _ClickUp():
        t = clickup_client.fetch_shared(MY_TOKEN)[0]
    assert t["name"] == "таска shared1", t
    assert "branches" in t and t["checklist_loaded"] is True, t


def test_shared_tasks_cost_exactly_one_request():
    """Ієрархія віддає таски з повними полями, тож довантажувати їх по одній
    не треба. Заміряно 02.09.2026: таких тасок 173 — по запиту на кожну це
    вилетіло б за ліміт ClickUp (100/хв) і зробило б доважок найдорожчим
    джерелом скану."""
    with _ClickUp(shared=("s1", "s2", "s3")) as cu:
        got = clickup_client.fetch_shared(MY_TOKEN)
    assert len(got) == 3, got
    assert sum(1 for url, _ in cu.calls if "/shared" in url) == 1, cu.calls
    assert not any("/task/" in url for url, _ in cu.calls), cu.calls





# ------------------------------------------------------------------ фоллбеки

def test_a_broken_personal_token_leaves_the_app_scan_whole():
    """Головне правило фічі: доважок не має гасити видачу. Особистий токен
    протух — вʼю і team все одно приїхали."""
    with _ClickUp(shared_fails=True):
        base = clickup_client.fetch_all()
        try:
            clickup_client.fetch_shared(MY_TOKEN)
        except Exception:
            pass
        else:
            raise AssertionError("відмову проковтнули замість доповісти")
    assert sorted(t["id"] for t in base) == ["team0", "team1"], base


def test_no_shared_tasks_is_not_an_error():
    with _ClickUp(shared=()):
        assert clickup_client.fetch_shared(MY_TOKEN) == []


def test_fetch_by_ids_of_nothing_makes_no_calls():
    """Порожній батч трапляється щоразу, коли розшарених тасок немає."""
    with _ClickUp() as cu:
        assert clickup_client.fetch_by_ids([]) == []
    assert cu.calls == []


def test_a_closed_shared_task_does_not_ignore_the_checkbox():  # noqa: D401
    """`/team/{id}/shared` не приймає параметрів узагалі, отже й
    `include_closed` не знає. Заміряно 02.09.2026: із 173 розшарених тасок 171
    закрита — без фільтра вони їхали б у вкладку зі знятою галкою «включно з
    закритими», бо UI на неї не дивиться, він покладається на сервер."""
    with _ClickUp(shared=("closed1", "open1")):
        open_only = clickup_client.fetch_shared(MY_TOKEN)
        with_closed = clickup_client.fetch_shared(MY_TOKEN, include_closed=True)
    assert "closed1" not in [t["id"] for t in open_only], open_only
    assert "open1" in [t["id"] for t in open_only], open_only
    assert "closed1" in [t["id"] for t in with_closed], with_closed


# -------------------------------------------------------------------- whoami

class _User:
    def __init__(self, status, payload):
        self.status, self.payload = status, payload

    def __enter__(self):
        self._real = clickup_client.requests.get
        clickup_client.requests.get = lambda *a, **k: _resp(self.status, self.payload)
        return self

    def __exit__(self, *exc):
        clickup_client.requests.get = self._real


def test_whoami_names_the_account():
    """Кабінет має сказати, ЧИЙ це токен, не показуючи значення."""
    with _User(200, {"user": {"id": 7, "username": "Yurii S."}}):
        assert clickup_client.whoami("pk_x")["username"] == "Yurii S."


def test_whoami_passes_clickup_own_words_on():
    """Одруківку видно одразу, а не через тиждень порожнім сканом."""
    with _User(401, {"err": "Token invalid", "ECODE": "OAUTH_025"}):
        try:
            clickup_client.whoami("pk_x")
        except ValueError as e:
            assert "Token invalid" in str(e) and "OAUTH_025" in str(e), e
            return
    raise AssertionError("невірний токен прийнято")


# ------------------------------------------------------------------- коментар

def test_the_comment_is_signed():
    body = clickup_client.comment_body("fixed", {"name": "Yurii Spodarenko"})
    assert body["comment_text"] == \
        "fixed — committed via qa_lab by Yurii Spodarenko", body


def test_the_signature_tags_nobody():
    """Підпис — текст. Тег лишається рівно там, де його свідомо передали."""
    body = clickup_client.comment_body("fixed", {"name": "Yurii"})
    assert body["notify_all"] is False and "comment" not in body, body


def test_an_explicit_tag_survives_the_signature():
    """На тегу тримається ШІ-міст: TSM віддає, кого сповістити про фікс."""
    body = clickup_client.comment_body("fixed", {"name": "Yurii"}, 42, "Eva")
    assert body["comment"][0] == {"type": "tag", "user": {"id": 42}, "text": "@Eva"}
    assert body["comment"][1]["text"].endswith("by Yurii"), body
    assert body["notify_all"] is True


run(dict(globals()))
