"""Прогін перевірок не має вміти висіти вічно (кейс 02.10: «виконую
перевірки (1/1) 0%» назавжди).

Три запобіжники в runner.py:
  * `_locked` — branch_lock з дедлайном: вітку тримає інший прогін/sync/
    деплой → чесна помилка, а не мовчазне вічне очікування;
  * `_offload` — `.result(timeout)`: завислий у воркері чек перестає
    тримати відповідь і лок; пул перезапускається;
  * маяк `_progress_note` — ім'я чека, що рахується зараз: при таймауті
    видно, ХТО завис.
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                     # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import runner                                                # noqa: E402


def test_locked_raises_instead_of_hanging():
    br = "guard-test-branch"
    lock = runner.branch_lock(br)
    held = threading.Event()
    release = threading.Event()

    def holder():
        lock.acquire()          # RLock реентрантний — тримаємо з ЧУЖОГО потоку
        held.set()
        release.wait(10)
        lock.release()

    th = threading.Thread(target=holder, daemon=True)
    th.start()
    held.wait(5)
    try:
        try:
            with runner._locked(br, timeout=1):
                raise AssertionError("лок не мав дістатись")
        except RuntimeError as e:
            assert "зайнята" in str(e), e
    finally:
        release.set()
        th.join(5)
    with runner._locked(br, timeout=1):
        pass


def test_offload_timeout_restarts_pool_and_names_stuck_check():
    import concurrent.futures as cf

    class FakeFuture:
        def result(self, timeout=None):
            raise cf.TimeoutError()

    class FakePool:
        def submit(self, *a, **k):
            return FakeFuture()

    br = "guard-test-branch"
    old_get, old_drop = runner._get_pool, runner.drop_pool
    dropped = []
    runner._get_pool = lambda: FakePool()
    runner.drop_pool = lambda: dropped.append(1)
    runner._progress_note(br, "Бан-слова")
    try:
        try:
            runner._offload("_run_checks", br)
            raise AssertionError("мав бути таймаут")
        except RuntimeError as e:
            assert "не вклався" in str(e), e
            assert "Бан-слова" in str(e), "маяк не потрапив у повідомлення"
        assert dropped, "пул не перезапущено"
    finally:
        runner._get_pool, runner.drop_pool = old_get, old_drop
        runner._progress_note(br, "")


def test_progress_beacon_roundtrip():
    br = "guard-test-branch"
    runner._progress_note(br, "Телефон: немає на вайті")
    assert runner._progress_read(br) == "Телефон: немає на вайті"
    runner._progress_note(br, "")
    assert runner._progress_read(br) == ""


if __name__ == "__main__":
    run(dict(globals()))
