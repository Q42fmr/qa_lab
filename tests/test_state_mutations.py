"""Спільні json-файли стану не гублять записів, коли пишуть кілька людей.

Задача 21.09.2026 («разные пользователи не мешали работе друг друга»).
`write_json_state` лочив лише сам запис, а в ендпоінтах між читанням і
записом минав час:

* два одночасні прогони перевірок — кожен дописував свої вітки у СВОЮ копію
  `checks_state.json`, і другий запис стирав результати першого;
* два одночасні Apply — губився рядок журналу комітів, а з ним і Revert;
* імпорт з ClickUp читав список віток ДО походу в GitLab (секунди), а писав
  після — і повертав вітку, яку людина за цей час прибрала.

Тепер кожна така правка — `mutate_json_state`: читання, правка і запис під
одним локом на файл.
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

# Ізоляція — до першого імпорту: тест не сміє торкатись справжнього стану.
_STATE = Path(tempfile.mkdtemp(prefix="qa_lab-mutations-"))
os.environ["QA_LAB_STATE_DIR"] = str(_STATE)
os.environ.setdefault("MOCK_MODE", "1")

import app                                                        # noqa: E402
import projects                                                   # noqa: E402

PHP = "white-pages"


def _fresh(mock=True, client=None) -> Path:
    """Окрема тека стану на тест і реєстр з одним проєктом."""
    root = Path(tempfile.mkdtemp(dir=_STATE))
    projects._registry = {PHP: {"id": PHP, "title": "php", "type": "php",
                                "gitlab_path": "t/php", "token": "",
                                "mock": mock, "root": root}}
    projects._clients = {PHP: client} if client else {}
    projects._current = PHP
    return root


def _together(fns):
    """Запустити всі функції так, щоб вони справді перетнулись."""
    gate = threading.Barrier(len(fns))

    def go(fn):
        gate.wait()
        fn()
    ts = [threading.Thread(target=go, args=(f,)) for f in fns]
    [t.start() for t in ts]
    [t.join(10) for t in ts]


# ------------------------------------------------------ сам механізм

def test_concurrent_edits_of_one_file_all_land():
    """Кожен писач тримає файл «на руках» 20 мс — без локу на весь цикл
    виживав би лише останній."""
    path = _fresh() / "checks_state.json"

    def writer(i):
        def put(state):
            time.sleep(0.02)
            state[f"br-{i}"] = {"n": i}
        return lambda: app.mutate_json_state(path, dict, put)
    _together([writer(i) for i in range(12)])
    got = app.read_json_state(path, {})
    assert sorted(got) == sorted(f"br-{i}" for i in range(12)), sorted(got)


def test_unchanged_does_not_rewrite_the_file():
    path = _fresh() / "problems.json"
    app.write_json_state(path, [{"branch": "a", "source": "sync"}])
    before = path.stat().st_mtime_ns
    time.sleep(0.01)
    app.mutate_json_state(path, list, lambda rows: app.UNCHANGED)
    assert path.stat().st_mtime_ns == before


def test_a_default_is_never_shared_between_calls():
    """Дефолт — фабрика: спільний літерал мутувався б від виклику до виклику."""
    root = _fresh()
    app.mutate_json_state(root / "a.json", list, lambda rows: rows.append(1))
    got = app.mutate_json_state(root / "b.json", list, lambda rows: None)
    assert got == [], got


# ------------------------------------------------------ ендпоінти і журнали

def test_every_concurrent_commit_stays_in_the_journal():
    _fresh()
    _together([lambda i=i: app.log_commit(f"br-{i}", "fix", f"c{i}", ["a.php"])
               for i in range(10)])
    journal = app.load_journal()
    assert sorted(r["branch"] for r in journal) == sorted(f"br-{i}" for i in range(10))


def test_the_journal_still_keeps_newest_first_and_is_capped():
    _fresh()
    old_cap = app.JOURNAL_CAP
    app.JOURNAL_CAP = 3
    try:
        for i in range(5):
            app.log_commit(f"br-{i}", "fix", f"c{i}", [])
        assert [r["branch"] for r in app.load_journal()] == ["br-4", "br-3", "br-2"]
    finally:
        app.JOURNAL_CAP = old_cap


def test_concurrent_problems_all_land():
    _fresh()
    _together([lambda i=i: app.add_problems([{"branch": f"br-{i}", "source": "sync",
                                               "reason": "x"}])
               for i in range(10)])
    assert len(app.load_problems()) == 10


def test_branch_list_edits_keep_their_meaning():
    _fresh()
    app.mutate_branch_list(lambda _: ["a", "b"])
    app.remove_branch("a")
    app.mutate_branch_list(app._with("c"))
    app.mutate_branch_list(app._with("c"))          # другий раз — без дубля
    assert app.load_branch_list() == ["b", "c"]
    assert app.clear_branches() == {"removed": ["b", "c"]}
    assert app.load_branch_list() == []


class _SlowGitLab:
    """Відповідає не одразу — як справжній GitLab на пачці віток."""

    def branch(self, name):
        time.sleep(0.3)
        return {"name": name, "commit": "abc1234"}


def test_import_does_not_bring_back_a_branch_removed_meanwhile():
    """Кейс, з якого все почалось: поки імпорт ходить у GitLab, людина
    прибирає вітку зі списку. Раніше імпорт писав список, прочитаний ДО
    походу, і вітка поверталась."""
    _fresh(mock=False, client=_SlowGitLab())
    app.mutate_branch_list(lambda _: ["keep-me", "remove-me"])
    req = app.ClickUpImportRequest(tasks=[{"id": "t1", "name": "T", "url": "",
                                           "branches": ["new-one"]}])
    t = threading.Thread(target=lambda: app.clickup_import(req))
    t.start()
    time.sleep(0.1)
    app.remove_branch("remove-me")
    t.join(10)
    assert app.load_branch_list() == ["keep-me", "new-one"], app.load_branch_list()
    assert app.load_cu_map()["new-one"]["task_id"] == "t1"


if __name__ == "__main__":
    run(dict(globals()))
