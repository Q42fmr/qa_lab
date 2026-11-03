"""Мінімальний раннер тестів лаби: без залежностей.

Запуск:  python tests/test_<щось>.py
Exit code 1, якщо хоч один тест впав — щоб було видно в CI/скриптах.
"""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# без цього кирилиця в повідомленнях перетворюється на "????" у cmd
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load_check(name: str):
    """Вантажить checks/<name>.py так само, як це робить runner.load_checks()."""
    import importlib.util
    path = ROOT / "checks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"checks.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(namespace: dict):
    """Проганяє всі test_* з namespace (передавай dict(globals()))."""
    tests = [(n, f) for n, f in sorted(namespace.items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception:
            failed.append(name)
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    sys.exit(1 if failed else 0)


def standard_index(html: str) -> str:
    """Головна «як з деплою»: три еталонні php-блоки (init перед <!DOCTYPE,
    пікселі перед </head>, лід-блок після <body>) з checks/php_scripts —
    фікстура для тестів, що ріжуть або звіряють ці блоки."""
    import re
    by_kind = {"init": [], "head": [], "body": []}
    for label, _anchor, code in load_check("php_scripts")._RAW_FRAGMENTS:
        kind = label.split(":", 1)[0].strip()
        if kind in by_kind:
            by_kind[kind].append(code.strip("\n"))
    init = "<?php\n" + "\n\n".join(by_kind["init"]) + "\n?>\n"
    head = "\n\n".join(by_kind["head"]) + "\n"
    body = "<?php\n" + "\n".join(by_kind["body"]) + "\n?>\n"
    doc = re.search(r"<!DOCTYPE|<html\b", html, re.I)
    html = html[:doc.start()] + init + html[doc.start():]
    hc = re.search(r"</head\s*>", html, re.I)
    html = html[:hc.start()] + head + html[hc.start():]
    bo = re.search(r"<body\b[^>]*>", html, re.I)
    return html[:bo.end()] + "\n" + body + html[bo.end():]
