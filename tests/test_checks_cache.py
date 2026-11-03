"""Каталог чеків перечитується лише тоді, коли змінився файл.

Задача 21.09.2026 («разные пользователи не мешали работе друг друга»).
`load_checks()` exec'ив кожен `checks/*.py` заново на КОЖНУ вітку і щоразу
робив `importlib.reload(menu_rules)` — поки в сусідніх потоках чужого
прогону чеки виконували функції того самого модуля. Тепер каталог
кешується за відбитком (шлях, mtime, розмір) чеків і спільних бібліотек.

Правка на льоту мусить працювати як і раніше — це стережеться тут так само,
як і сам кеш.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

_STATE = Path(tempfile.mkdtemp(prefix="qa_lab-checks-cache-"))
os.environ["QA_LAB_STATE_DIR"] = str(_STATE)

import runner                                                     # noqa: E402

REAL_DIR, REAL_LIBS = runner.CHECKS_DIR, runner._SHARED_LIBS

# Чек-зразок: кожне виконання модуля дописує рядок у лічильник — так видно,
# скільки разів каталог справді перечитувався.
_CHECK = '''NAME = "{name}"
FILES = ["*.html"]
GROUP = "tests"
with open({counter!r}, "a") as _f:
    _f.write("{name}\\n")

def run(path, text):
    return [{{"line": 1, "severity": "warn", "message": "{msg}"}}]
'''


def _sandbox():
    d = Path(tempfile.mkdtemp(dir=_STATE))
    (d / "checks").mkdir()
    lib = d / "shared_lib.py"
    lib.write_text("X = 1\n")
    counter = d / "execs.txt"
    runner.CHECKS_DIR = d / "checks"
    runner._SHARED_LIBS = (str(lib),)
    runner._checks_cache.update(key=None, checks=None)
    return d, lib, counter


def _write(d, name, counter, msg="old"):
    p = d / "checks" / f"{name}.py"
    p.write_text(_CHECK.format(name=name, counter=str(counter), msg=msg))
    return p


def _execs(counter):
    return counter.read_text().split() if counter.exists() else []


def _restore():
    runner.CHECKS_DIR, runner._SHARED_LIBS = REAL_DIR, REAL_LIBS
    runner._checks_cache.update(key=None, checks=None)


def test_nothing_changed_means_nothing_is_reexecuted():
    d, _lib, counter = _sandbox()
    try:
        _write(d, "alpha", counter)
        _write(d, "beta", counter)
        first = {c["id"]: c["module"] for c in runner.load_checks()}
        for _ in range(20):
            again = {c["id"]: c["module"] for c in runner.load_checks()}
            assert all(again[k] is first[k] for k in first)
        assert sorted(_execs(counter)) == ["alpha", "beta"], _execs(counter)
    finally:
        _restore()


def test_an_edited_check_is_picked_up_without_a_restart():
    d, _lib, counter = _sandbox()
    try:
        p = _write(d, "alpha", counter, msg="old")
        old = runner.load_checks()[0]["module"]
        assert old.run("a.html", "")[0]["message"] == "old"
        _write(d, "alpha", counter, msg="brand new")
        os.utime(p, ns=(time.time_ns(), time.time_ns() + 1_000_000))
        new = runner.load_checks()[0]["module"]
        assert new is not old
        assert new.run("a.html", "")[0]["message"] == "brand new"
    finally:
        _restore()


def test_a_new_check_file_shows_up():
    d, _lib, counter = _sandbox()
    try:
        _write(d, "alpha", counter)
        assert [c["id"] for c in runner.load_checks()] == ["alpha"]
        _write(d, "beta", counter)
        assert [c["id"] for c in runner.load_checks()] == ["alpha", "beta"]
    finally:
        _restore()


def test_an_edited_shared_library_rebuilds_the_catalog():
    """Чек, що отримав нову функцію зі спільної бібліотеки, мусить побачити
    її без рестарту — саме для цього `menu_rules` і перезавантажувався."""
    d, lib, counter = _sandbox()
    try:
        _write(d, "alpha", counter)
        old = runner.load_checks()[0]["module"]
        lib.write_text("X = 2\n")
        os.utime(lib, ns=(time.time_ns(), time.time_ns() + 1_000_000))
        assert runner.load_checks()[0]["module"] is not old
        assert _execs(counter) == ["alpha", "alpha"], _execs(counter)
    finally:
        _restore()


def test_the_real_catalog_is_loaded_once():
    _restore()
    a = {c["id"]: c["module"] for c in runner.load_checks()}
    b = {c["id"]: c["module"] for c in runner.load_checks()}
    assert len(a) > 20 and all(b[k] is a[k] for k in a)


def test_callers_cannot_shrink_the_shared_catalog():
    """Викликачі фільтрують список — це не має різати кеш для наступних."""
    _restore()
    got = runner.load_checks()
    n = len(got)
    got.clear()
    assert len(runner.load_checks()) == n


if __name__ == "__main__":
    run(dict(globals()))
