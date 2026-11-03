"""Чек/автофікс checks/empty_menu.py — обгортка над menu_rules (логіка
покрита в test_empty_menu.py; тут — контракт run()/fix() для runner-а)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("empty_menu")

BROKEN = """<html><head><style>#mobile-menu { display: none; }</style></head>
<body><header>
  <span>Brand</span>
  <nav id="mobile-menu" class="flex-col md:flex-row"><a href="./a.html">A</a></nav>
</header></body></html>"""

HEALTHY = """<html><head><style>#mobile-menu { display: none; }</style></head>
<body><header>
  <nav class="hidden md:flex"><a href="./a.html">A</a></nav>
  <nav id="mobile-menu" class="flex-col"><a href="./a.html">A</a></nav>
</header></body></html>"""


def test_run_flags_broken_page_as_error():
    issues = mod.run("index.php", BROKEN)
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "error"
    assert issues[0]["path"] == "index.php"
    assert "nav" in issues[0]["message"]


def test_run_silent_on_healthy_page():
    assert mod.run("index.php", HEALTHY) == []


def test_fix_repairs_and_run_goes_clean():
    fixed = mod.fix("index.php", BROKEN)
    assert 'id="mobile-menu"' not in fixed.split("</style>")[1]
    assert mod.run("index.php", fixed) == []


def test_fix_is_noop_on_healthy_page():
    assert mod.fix("index.php", HEALTHY) == HEALTHY


def test_group_is_auto_and_fixable():
    assert mod.GROUP == "auto"
    assert callable(mod.fix)


if __name__ == "__main__":
    run(dict(globals()))
