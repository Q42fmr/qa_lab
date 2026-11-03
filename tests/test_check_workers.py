"""Прогони перевірок у пулі процесів — ті самі відповіді, що й у потоці.

Задача 21.09.2026 («запараллелить процессы»). Чеки впираються в GIL: дві
людини одночасно в потоках чекають удвічі довше кожна (заміряно: 55 с проти
12-23 с у процесах на пачці з 8 php-віток). `CHECK_WORKERS` переносить
`run_checks` і `compute_fixes` у процеси-воркери.

Головне, що тут стережеться, — що відповідь НЕ змінилась: той самий чек,
той самий знімок, ті самі знахідки і ті самі фікси. Плюс єдиний чек, який
дивиться в пам'ять процесу лаби (`favicon` → `deployer.list_deploys()`), —
у воркері він мусить бачити ті самі деплої.
"""
import os
import sys
import tempfile
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

# Ізоляція — до першого імпорту: тест не сміє торкатись справжнього стану.
_STATE = Path(tempfile.mkdtemp(prefix="qa_lab-workers-"))
os.environ["QA_LAB_STATE_DIR"] = str(_STATE)
os.environ.pop("CHECK_WORKERS", None)

import deployer                                                   # noqa: E402
import projects                                                   # noqa: E402
import runner                                                     # noqa: E402

PHP = "white-pages"
BR = "pool-br-pt"

_PAGE = """<!doctype html><html lang="pt"><head><meta charset="utf-8">
<title>Pool</title><link rel="icon" href="favicon-missing.ico"></head>
<body><header><a href="index.html"><img src="logo.png" alt="logo"></a>
<nav><a href="#">Início</a><a href="contato.html">Contato</a></nav></header>
<form action="send.php" method="post"><input name="email"><button>Enviar</button></form>
<p>Garantia de lucro 100% e dinheiro fácil!</p>
<footer>Rua Exemplo, 1 — São Paulo</footer></body></html>
"""


def _fresh():
    root = Path(tempfile.mkdtemp(dir=_STATE))
    projects._registry = {PHP: {"id": PHP, "title": "php", "type": "php",
                                "gitlab_path": "t/php", "token": "secret-token",
                                "mock": True, "root": root}}
    projects._clients = {}
    projects._current = PHP
    d = runner.snapshot_dir(BR)
    d.mkdir(parents=True)
    (d / "index.html").write_text(_PAGE, encoding="utf-8")
    (d / "contato.html").write_text(_PAGE.replace("Pool", "Contato"), encoding="utf-8")
    (d / "app.exe").write_bytes(b"MZ\x00\x00")               # dev_files: видалити
    (d / ".snapshot.json").write_text('{"branch": "%s", "commit": "c1"}' % BR)


def _shape(result):
    """Прогін без часу: що знайдено і де."""
    return {c["id"]: sorted((i["path"] or "", i["line"] or 0, i["severity"],
                             i["message"]) for i in c["issues"])
            for c in result["checks"]}, result["totals"], result["files_scanned"]


def _with_workers(n, fn):
    os.environ["CHECK_WORKERS"] = str(n)
    try:
        return fn()
    finally:
        os.environ.pop("CHECK_WORKERS", None)
        runner.drop_pool()


# ------------------------------------------------------ та сама відповідь

def test_a_run_in_a_worker_finds_exactly_what_a_thread_finds():
    _fresh()
    here = runner.run_checks(BR)
    there = _with_workers(2, lambda: runner.run_checks(BR))
    assert _shape(there) == _shape(here)
    assert any(c["issues"] for c in here["checks"]), "зразок нічого не спрацював"


def test_fixes_from_a_worker_are_the_same_fixes():
    _fresh()
    here = runner.compute_fixes(BR)
    there = _with_workers(2, lambda: runner.compute_fixes(BR))
    assert there == here
    assert any(c["path"] == "app.exe" and c["type"] == "delete" for c in here), here


def test_a_worker_answers_in_the_person_s_project():
    """Проєкт іде у воркер разом із завданням: інакше vue-людина рахувала б
    по php-знімку з тією самою назвою."""
    _fresh()
    projects._registry["vue"] = {**projects._registry[PHP], "id": "vue",
                                 "type": "node",
                                 "root": Path(tempfile.mkdtemp(dir=_STATE))}
    with projects.use("vue"):
        try:
            _with_workers(1, lambda: runner.run_checks(BR))
        except ValueError as e:
            assert "не синхронізована" in str(e)
        else:
            raise AssertionError("воркер рахував у чужому проєкті")


# ------------------------------------------------------ пам'ять процесу

def _probe_deploys(_branch):
    return deployer.list_deploys()


def test_the_worker_sees_the_same_live_deploys():
    """`favicon` смикає живий деплой вітки через `deployer.list_deploys()`,
    а у воркера своєї пам'яті деплоїв немає — список приїжджає з завданням."""
    _fresh()
    runner._probe_deploys = _probe_deploys
    try:
        live = [{"branch": BR, "port": 9100, "url": "http://127.0.0.1:9100/"}]
        got = runner._in_worker("_probe_deploys", dict(projects._registry), PHP,
                                live, BR)
        assert got == live, got
        assert deployer.list_deploys is not None
        assert runner._in_worker.__module__ == "runner"
    finally:
        del runner._probe_deploys
    # і після виклику справжній deployer.list_deploys на місці
    assert deployer.list_deploys.__module__ == "deployer"


class _Capture:
    """Пул, що запам'ятовує, що йому передали, і рахує на місці."""

    def __init__(self):
        self.seen = None

    def submit(self, fn, *args):
        self.seen = args
        f = Future()
        f.set_result(fn(*args))
        return f


def test_tokens_never_travel_to_a_worker():
    _fresh()
    cap = _Capture()
    runner._pool = cap
    os.environ["CHECK_WORKERS"] = "2"
    try:
        runner.run_checks(BR)
    finally:
        os.environ.pop("CHECK_WORKERS", None)
        runner._pool = None
    registry = cap.seen[1]
    assert all(v["token"] == "" for v in registry.values()), registry
    assert projects._registry[PHP]["token"] == "secret-token", "зіпсовано оригінал"


class _Broken:
    def submit(self, *a, **kw):
        raise BrokenProcessPool("a worker died")

    def shutdown(self, *a, **kw):
        pass


def test_a_broken_pool_does_not_lose_the_run():
    _fresh()
    here = runner.run_checks(BR)
    runner._pool = _Broken()
    os.environ["CHECK_WORKERS"] = "2"
    try:
        again = runner.run_checks(BR)
    finally:
        os.environ.pop("CHECK_WORKERS", None)
    assert _shape(again) == _shape(here)
    assert runner._pool is None, "зламаний пул лишився на місці"


def test_zero_workers_means_threads_as_before():
    _fresh()
    os.environ["CHECK_WORKERS"] = "0"
    try:
        assert runner._get_pool() is None
    finally:
        os.environ.pop("CHECK_WORKERS", None)


if __name__ == "__main__":
    run(dict(globals()))
