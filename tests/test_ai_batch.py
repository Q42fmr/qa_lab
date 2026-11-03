"""Пачка доменів від TSM, межі черги і чесна відповідь про завантаженість.

Просив бік TSM: після їхнього прогону назбирується кілька червоних доменів
одразу, і слати їх по одному — це стільки ж кругів HTTP, скільки доменів.

Головне, що тут закріплено, — **пачка не змінює правил для одного домену**.
Обидва входи ходять одним і тим самим `_accept()`: два прийоми з різною
логікою розійшлися б на першому ж виправленні, і розбіжність побачив би той
бік, а не ми.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

from fastapi import HTTPException                                 # noqa: E402

import ai_bridge                                                  # noqa: E402
from test_ai_bridge import Fake                                   # noqa: E402


# Текст, який мапа впізнає іменем і роутить у `logo_domain` — той самий, що
# в `test_ai_bridge`. Тут важливо не «що написано», а що запит доходить до
# черги: інакше тест міряв би роутинг, а не пачку.
ROUTES = ("Что фиксить — a.co\n"
          "• [главная] Название сайта не совпадает с доменом — "
          "привести бренд в шапке к корню домена.")


def _item(text=ROUTES, **kw):
    kw.setdefault("branch", "x-br-pt")
    kw.setdefault("task_id", "t-batch")
    return ai_bridge.AIRequest(text=text, **kw)


class _NoWorker:
    """Ловить `submit`, щоб тест не піднімав фоновий потік.

    Заразом чистить `_inflight`: у бойовому коді ключі звільняє воркер, якого
    тут немає, — і без цього другий тест бачив би роботу першого «в польоті»
    і чесно відповідав `duplicate`.
    """

    def __enter__(self):
        self.sent = []
        self.real = ai_bridge.submit
        ai_bridge.submit = self.sent.append
        _clear_inflight()
        return self

    def __exit__(self, *exc):
        ai_bridge.submit = self.real
        _clear_inflight()
        return False


def _clear_inflight():
    with ai_bridge._inflight_lock:
        ai_bridge._inflight.clear()


def _batch(items, batch_id=""):
    return ai_bridge.ai_requests(ai_bridge.AIBatch(batch_id=batch_id, items=items))


# ------------------------------------------------------------------ пачка

def test_a_batch_is_accepted_and_each_item_gets_its_own_id():
    with Fake(), _NoWorker() as w:
        out = _batch([_item(branch="x-br-pt", task_id="t-1"),
                      _item(branch="x-br", task_id="t-2"),
                      _item(branch="other-br", task_id="t-3")])
    assert out["accepted"] == 3, out
    ids = {i["request_id"] for i in out["items"]}
    assert len(ids) == 3, out["items"]
    assert [i["i"] for i in out["items"]] == [0, 1, 2]
    assert len(w.sent) == 3


def test_the_same_work_twice_in_one_batch_is_a_duplicate():
    """Та сама вітка і ті самі чеки двічі — це одна робота, скільки б разів
    вона не приїхала. Захист від кола не слабшає від того, що запити
    приїхали пачкою."""
    with Fake(), _NoWorker() as w:
        out = _batch([_item(branch="x-br-pt", task_id="t-1"),
                      _item(branch="x-br-pt", task_id="t-2")])
    kinds = [i["status"] for i in out["items"]]
    assert kinds[0] == "accepted" and kinds[1] == "duplicate", kinds
    assert len(w.sent) == 1


def test_the_batch_id_travels_into_every_record():
    """Щоб алерт людині був ОДИН на пачку, а не пʼять поспіль."""
    with Fake(), _NoWorker() as w:
        _batch([_item(branch="x-br-pt", task_id="t-1"),
                _item(branch="x-br", task_id="t-2")], batch_id="tsm-01")
    assert {j["batch_id"] for j in w.sent} == {"tsm-01"}


def test_a_batch_over_the_limit_is_refused_whole():
    """Мовчазне обрізання було б гіршим за відмову: той бік вважав би, що
    прийнято все."""
    with Fake(), _NoWorker():
        try:
            _batch([_item(task_id=f"t-{i}") for i in range(ai_bridge.batch_max() + 1)])
        except HTTPException as e:
            assert e.status_code == 413 and "межа" in str(e.detail), e.detail
            return
    raise AssertionError("пачку понад межу прийнято")


def test_an_empty_batch_is_a_bad_request():
    with Fake(), _NoWorker():
        try:
            _batch([])
        except HTTPException as e:
            assert e.status_code == 400
            return
    raise AssertionError("порожню пачку прийнято")


def test_one_bad_item_does_not_take_the_batch_down():
    """Порожній елемент — відмова ЕЛЕМЕНТА. Інакше їхній ретрай переслав би
    і те, що вже прийнято."""
    with Fake(), _NoWorker() as w:
        out = _batch([_item(branch="x-br-pt", task_id="t-1"),
                      ai_bridge.AIRequest(text=""),
                      _item(branch="x-br", task_id="t-3")])
    kinds = [i["status"] for i in out["items"]]
    assert kinds[1] == "bad_request", kinds
    assert out["accepted"] == 2 and len(w.sent) == 2, kinds


def test_the_batch_answers_202_even_when_items_are_refused():
    """Код відповіді на пачку не залежить від долі окремих елементів —
    вона вся в `items[]`."""
    with Fake(), _NoWorker():
        out = _batch([ai_bridge.AIRequest(text="")])
    assert out["accepted"] == 0
    assert out["items"][0]["status"] == "bad_request"
    assert "queue" in out


# ------------------------------------------------------------------ черга

def test_a_full_queue_answers_busy_with_a_retry_after():
    """Прийом дешевий, виконання — ні. Без межі буря з того боку прийнялась
    би ЦІЛКОМ: ми відповідали б «прийнято» на кожен запит, а розгрібалось би
    це годинами."""
    with Fake():
        _clear_inflight()
        real_max = ai_bridge.queue_max
        ai_bridge.queue_max = lambda: 0          # черга «повна» одразу
        try:
            out = _batch([_item(task_id="t-busy")])
        finally:
            ai_bridge.queue_max = real_max
    got = out["items"][0]
    assert got["status"] == "busy", got
    assert got["retry_after"] > 0 and got["queue"]["max"] == 0, got


def test_busy_releases_the_loop_keys():
    """Робота, яка не почалась, не має тримати ключі кола — інакше вітка
    більше ніколи не пройде гейт."""
    with Fake():
        _clear_inflight()
        real_max = ai_bridge.queue_max
        ai_bridge.queue_max = lambda: 0
        try:
            _batch([_item(task_id="t-busy")])
        finally:
            ai_bridge.queue_max = real_max
        assert ai_bridge.inflight_count() == 0


def test_the_queue_endpoint_does_not_lie():
    with Fake():
        st = ai_bridge.ai_queue()
    assert set(st) == {"depth", "inflight", "worker_alive", "max", "eta_s"}, st
    assert st["max"] == ai_bridge.queue_max()
    assert st["eta_s"] > 0


def test_the_batch_limit_has_a_hard_ceiling():
    """Змінна оточення не має відкривати пачку на сотню: воркер один, і сотня
    означала б годину черги під виглядом «прийнято»."""
    os.environ["QA_LAB_BRIDGE_BATCH_MAX"] = "500"
    try:
        assert ai_bridge.batch_max() == 20
    finally:
        os.environ.pop("QA_LAB_BRIDGE_BATCH_MAX", None)


# ------------------------------------------------ одиничний вхід не змінився

def test_a_single_request_still_behaves_exactly_as_before():
    with Fake(), _NoWorker():
        out = ai_bridge.ai_request(_item(task_id="t-solo"))
    assert out["status"] == "accepted" and out["branch"] == "x-br-pt", out


def test_an_unknown_branch_is_still_a_409():
    with Fake(), _NoWorker():
        try:
            ai_bridge.ai_request(ai_bridge.AIRequest(
                text="щось зламалось", branch="", domain="", task_id=""))
        except HTTPException as e:
            assert e.status_code == 409, e.status_code
            return
    raise AssertionError("нерозпізнану вітку прийнято")


if __name__ == "__main__":
    run(dict(globals()))
