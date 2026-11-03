"""Знімок вітки не ламається, коли з ним працюють кілька людей одночасно.

Задача 21.09.2026 («разные пользователи не мешали работе друг друга»).
До неї `sync_branch` робив `rmtree` і розпаковував архів на місці, без
жодного локу, а ручні прогони чеків локу не брали взагалі. Тому:

* двоє синкали ту саму вітку — один видаляв теку посеред розпаковки іншого;
* прогін колеги читав знімок, який саме перезаливався, — і казав
  «вітка не синхронізована» або «чисто» по половині файлів;
* обірване завантаження лишало ПОРОЖНЮ теку замість живого знімка;
* Sync після нового коміту мовчки стирав файли, які колега залив у знімок і
  ще не закомітив.

Тепер: лок на знімок вітки, нова копія розпаковується поруч і стає на місце
одним перейменуванням, а незакомічені правки sync відмовляється стирати.
"""
import io
import os
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

# Ізоляція — до першого імпорту: тест не сміє торкатись справжнього стану.
_STATE = Path(tempfile.mkdtemp(prefix="qa_lab-snap-races-"))
os.environ["QA_LAB_STATE_DIR"] = str(_STATE)
os.environ.setdefault("MOCK_MODE", "1")

import app                                                        # noqa: E402
import projects                                                   # noqa: E402
import runner                                                     # noqa: E402
from fastapi import HTTPException                                 # noqa: E402

PHP = "white-pages"
BR = "anna-br-pt"


class _Repo:
    """GitLab у мініатюрі: коміти → файли; `archive` і `tree_blobs` — як у
    справжнього клієнта."""

    def __init__(self):
        self.commits: dict[str, dict[str, bytes]] = {}
        self.head = None
        self.slow = 0.0
        self.fail = False
        self.during = None             # що зробити в мить завантаження

    def push(self, sha, files):
        self.commits[sha] = {k: v.encode() for k, v in files.items()}
        self.head = sha

    def branch(self, name):
        return {"name": name, "commit": self.head}

    def archive(self, name):
        if self.during:
            self.during()
        if self.slow:
            time.sleep(self.slow)
        if self.fail:
            raise RuntimeError("connection reset by peer")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for path, data in self.commits[self.head].items():
                z.writestr(f"proj-{self.head}/{path}", data)
        return buf.getvalue()

    def tree_blobs(self, ref):
        return {p: runner.git_blob_sha(d) for p, d in self.commits[ref].items()}


def _fresh() -> _Repo:
    root = Path(tempfile.mkdtemp(dir=_STATE))
    projects._registry = {PHP: {"id": PHP, "title": "php", "type": "php",
                                "gitlab_path": "t/php", "token": "",
                                "mock": False, "root": root}}
    repo = _Repo()
    projects._clients = {PHP: repo}
    projects._current = PHP
    repo.push("c1", {"index.html": "<h1>one</h1>", "about.html": "<p>a</p>"})
    runner.sync_branch(repo, BR)
    return repo


def _read(path):
    return runner.read_snapshot_file(BR, path).decode()


# ------------------------------------------------------ підміна цілком

def test_the_old_snapshot_is_whole_while_the_new_one_downloads():
    """У мить завантаження старий знімок на місці — доти його вже стерли."""
    repo = _fresh()
    repo.push("c2", {"index.html": "<h1>two</h1>", "about.html": "<p>a</p>"})
    seen = {}
    repo.during = lambda: seen.update(files=runner.snapshot_files(BR),
                                      synced=runner.is_synced(BR))
    runner.sync_branch(repo, BR)
    assert seen == {"files": ["about.html", "index.html"], "synced": True}, seen
    assert _read("index.html") == "<h1>two</h1>"


def test_a_failed_download_keeps_the_old_snapshot_alive():
    repo = _fresh()
    repo.push("c2", {"index.html": "<h1>two</h1>"})
    repo.fail = True
    try:
        runner.sync_branch(repo, BR)
    except RuntimeError:
        pass
    else:
        raise AssertionError("збій завантаження проковтнуто")
    assert runner.is_synced(BR), "обірваний sync лишив порожню теку"
    assert _read("index.html") == "<h1>one</h1>"
    assert runner.snapshot_meta(BR)["commit"] == "c1"


def test_nothing_half_done_is_left_in_the_cache():
    """Напівготова копія живе поза cache/: в «Архіві» її не видно, і «🧹 архів»
    її не зачепить."""
    repo = _fresh()
    repo.push("c2", {"index.html": "<h1>two</h1>"})
    repo.fail = True
    try:
        runner.sync_branch(repo, BR)
    except RuntimeError:
        pass
    names = sorted(p.name for p in runner.cache_root().iterdir())
    assert names == [runner.snapshot_dir(BR).name], names


# ------------------------------------------------------ одночасність

def test_two_syncs_of_one_branch_do_not_trample_each_other():
    repo = _fresh()
    repo.push("c2", {"index.html": "<h1>two</h1>", "new.html": "<p>n</p>"})
    repo.slow = 0.2
    errors = []

    def go():
        try:
            runner.sync_branch(repo, BR, force=True)
        except Exception as e:                        # pragma: no cover
            errors.append(repr(e))
    ts = [threading.Thread(target=go) for _ in range(3)]
    [t.start() for t in ts]
    [t.join(10) for t in ts]
    assert not errors, errors
    assert runner.snapshot_files(BR) == ["index.html", "new.html"]
    assert runner.snapshot_meta(BR)["commit"] == "c2"


class _Probe:
    """Чек-зонд: запам'ятовує, які файли бачив прогін."""
    seen: list = []

    @staticmethod
    def run_branch(files, all_paths):
        _Probe.seen.append(sorted(all_paths))
        return []


def test_checks_wait_for_a_running_sync_and_see_the_new_snapshot():
    repo = _fresh()
    repo.push("c2", {"index.html": "<h1>two</h1>", "new.html": "<p>n</p>"})
    repo.slow = 0.3
    _Probe.seen = []
    real = runner.load_checks
    runner.load_checks = lambda: [{
        "id": "probe", "name": "probe", "description": "", "files": ["*"],
        "fixable": False, "group": "tests", "projects": ["php", "node"],
        "error": None, "module": _Probe}]
    try:
        t = threading.Thread(target=lambda: runner.sync_branch(repo, BR))
        t.start()
        time.sleep(0.1)                     # sync уже качає під локом
        runner.run_checks(BR)
        t.join(10)
    finally:
        runner.load_checks = real
    assert _Probe.seen == [["index.html", "new.html"]], _Probe.seen


def test_different_branches_still_sync_in_parallel():
    """Лок — на вітку, а не на процес: інакше пачка з восьми віток знову
    йшла б по одній."""
    repo = _fresh()
    repo.slow = 0.3
    t0 = time.time()
    ts = [threading.Thread(target=runner.sync_branch, args=(repo, f"br-{i}-pt"))
          for i in range(4)]
    [t.start() for t in ts]
    [t.join(10) for t in ts]
    assert time.time() - t0 < 1.0, "синки різних віток пішли по черзі"


# ------------------------------------------------------ незакомічене

def test_sync_does_not_wipe_uncommitted_edits():
    repo = _fresh()
    (runner.snapshot_dir(BR) / "index.html").write_text("<h1>my edit</h1>")
    (runner.snapshot_dir(BR) / "logo.svg").write_text("<svg/>")
    repo.push("c2", {"index.html": "<h1>two</h1>", "about.html": "<p>a</p>"})
    try:
        runner.sync_branch(repo, BR)
    except runner.UnsavedEdits as e:
        assert "index.html" in str(e) and "logo.svg" in str(e), str(e)
    else:
        raise AssertionError("sync стер незакомічені правки")
    assert _read("index.html") == "<h1>my edit</h1>"


def test_force_still_overwrites_on_purpose():
    repo = _fresh()
    (runner.snapshot_dir(BR) / "index.html").write_text("<h1>my edit</h1>")
    repo.push("c2", {"index.html": "<h1>two</h1>"})
    runner.sync_branch(repo, BR, force=True)
    assert _read("index.html") == "<h1>two</h1>"


def test_a_clean_snapshot_follows_a_new_commit_as_before():
    repo = _fresh()
    repo.push("c2", {"index.html": "<h1>two</h1>"})
    runner.sync_branch(repo, BR)
    assert _read("index.html") == "<h1>two</h1>"


def test_an_unknown_base_tree_does_not_block_the_sync():
    """Дерево базового коміту не дістали — не блокуємо: так sync і
    поводився досі, а невідомість не привід зупиняти роботу."""
    repo = _fresh()
    (runner.snapshot_dir(BR) / "index.html").write_text("<h1>my edit</h1>")
    repo.push("c2", {"index.html": "<h1>two</h1>"})

    def broken(_ref):
        raise RuntimeError("502")
    repo.tree_blobs = broken
    runner.sync_branch(repo, BR)
    assert _read("index.html") == "<h1>two</h1>"


def test_the_sync_button_explains_instead_of_a_502():
    """Відмова — не збій: у проді 5xx Cloudflare підміняє своєю сторінкою,
    і людина не побачила б, чому."""
    repo = _fresh()
    (runner.snapshot_dir(BR) / "index.html").write_text("<h1>my edit</h1>")
    repo.push("c2", {"index.html": "<h1>two</h1>"})
    try:
        app.sync(BR)
    except HTTPException as e:
        assert e.status_code == 409, e.status_code
        assert "незакомічені правки" in e.detail, e.detail
    else:
        raise AssertionError("sync пройшов поверх незакомічених правок")


if __name__ == "__main__":
    run(dict(globals()))
