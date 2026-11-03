"""Механіка fix_branch/create в runner.compute_fixes.

Тест не чіпає реальні вітки: підмінює runner.snapshot_files /
read_snapshot_file / checks_for_active_project / snapshot_dir на фейки.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                              # noqa: E402

sys.path.insert(0, str(ROOT))
import runner                                               # noqa: E402

# Фейкова база знімка для перевірки меж шляху (Знахідка 3). Не мусить
# існувати на диску — Path.resolve() не вимагає існування шляху.
FAKE_BASE = (ROOT / "cache" / "any-branch").resolve()


class FakeModule:
    """Перевірка-пустушка, яка створює файл і правит сторінку."""

    @staticmethod
    def fix_branch(files, all_paths, branch):
        return [
            {"type": "create", "path": "favicon.svg", "content": "<svg/>"},
            {"type": "edit", "path": "index.php", "content": "FIXED"},
        ]


def _install_fakes(module):
    saved = (runner.checks_for_active_project, runner.snapshot_files,
             runner.read_snapshot_file, runner.snapshot_dir)

    runner.checks_for_active_project = lambda: [{
        "id": "fake", "name": "Fake", "files": ["*.php"], "fixable": True,
        "group": "auto", "module": module, "error": None,
        "projects": ["php"], "description": "",
    }]
    runner.snapshot_files = lambda branch: ["index.php"]
    runner.read_snapshot_file = lambda branch, path: b"ORIGINAL"
    # snapshot_dir теж підміняємо: реальний виклик тягне projects.state_dir(),
    # якому потрібен projects.init() — тест лишається герметичним без нього.
    runner.snapshot_dir = lambda branch: FAKE_BASE
    return saved


def _restore(saved):
    (runner.checks_for_active_project, runner.snapshot_files,
     runner.read_snapshot_file, runner.snapshot_dir) = saved


def test_fix_branch_produces_create_action():
    saved = _install_fakes(FakeModule)
    try:
        out = runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    created = [c for c in out if c["type"] == "create"]
    assert len(created) == 1, out
    assert created[0]["path"] == "favicon.svg", created
    assert created[0]["new"] == "<svg/>", created


def test_fix_branch_produces_edit_action():
    saved = _install_fakes(FakeModule)
    try:
        out = runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    edits = [c for c in out if c["type"] == "edit"]
    assert len(edits) == 1, out
    assert edits[0]["new"] == "FIXED", edits
    assert edits[0]["old"] == "ORIGINAL", edits


def test_check_without_fix_branch_still_works():
    class OnlyFix:
        @staticmethod
        def fix(path, text):
            return text.replace("ORIGINAL", "PATCHED")

    saved = _install_fakes(OnlyFix)
    try:
        out = runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    assert len(out) == 1 and out[0]["type"] == "edit", out
    assert out[0]["new"] == "PATCHED", out


def test_load_checks_marks_fix_branch_module_fixable():
    """Без цього compute_fixes відфільтрує перевірку: рядок 270 бере лише
    fixable, а load_checks рахував його без fix_branch. Пробний чек кладемо
    на диск, бо load_checks вантажить саме з checks/."""
    probe = ROOT / "checks" / "zz_probe_fixbranch.py"
    probe.write_text(
        'NAME = "probe"\n'
        'FILES = ["*.php"]\n'
        'def fix_branch(files, all_paths, branch):\n'
        '    return []\n',
        encoding="utf-8")
    try:
        found = [c for c in runner.load_checks()
                 if c["id"] == "zz_probe_fixbranch"]
        assert found, "пробний чек не завантажився"
        assert found[0]["fixable"], "модуль з fix_branch має бути fixable"
        assert found[0]["group"] == "auto", found[0]["group"]
    finally:
        probe.unlink(missing_ok=True)


def test_fix_branch_sees_result_of_fix():
    """fix_branch працює поверх пофайлових fix() — бачить уже змінений текст.

    assert усередині самого хука не годиться: виклик fix_branch у
    compute_fixes обгорнутий у try/except Exception, а AssertionError —
    підклас Exception, тож він мовчки проковтнеться і тест «пройде» навіть
    якщо семантику зламано. Тому отриманий files фіксуємо в замикання і
    звіряємо ПІСЛЯ виклику compute_fixes, поза try/except.
    """
    seen = {}

    class Both:
        @staticmethod
        def fix(path, text):
            return text.replace("ORIGINAL", "PATCHED")

        @staticmethod
        def fix_branch(files, all_paths, branch):
            seen["files"] = dict(files)
            return []

    saved = _install_fakes(Both)
    try:
        runner.compute_fixes("any-branch")
    finally:
        _restore(saved)

    assert seen.get("files", {}).get("index.php") == "PATCHED", seen


def test_fix_branch_overwrites_existing_edit_without_duplicating():
    """Колізійна гілка: fix_branch повертає edit на шлях, який fix() уже
    змінив. Має бути рівно один елемент на цей шлях (без дублю), new — від
    fix_branch (застосовується поверх), а мітка checks не загублена."""
    class Both:
        @staticmethod
        def fix(path, text):
            return text.replace("ORIGINAL", "PATCHED")

        @staticmethod
        def fix_branch(files, all_paths, branch):
            return [{"type": "edit", "path": "index.php",
                     "content": "FROM_BRANCH"}]

    saved = _install_fakes(Both)
    try:
        out = runner.compute_fixes("any-branch")
    finally:
        _restore(saved)

    matches = [c for c in out if c["path"] == "index.php"]
    assert len(matches) == 1, out
    item = matches[0]
    assert item["type"] == "edit", item
    assert item["new"] == "FROM_BRANCH", item
    assert "Fake" in item["checks"], item


def test_fix_branch_rejects_path_outside_branch():
    """Шлях від fix_branch не мусить виходити за межі cache/<branch>/ —
    ні відносним "../", ні абсолютним. Валідна дія поруч має пройти."""
    class Escaper:
        @staticmethod
        def fix_branch(files, all_paths, branch):
            return [
                {"type": "create", "path": "../evil.txt", "content": "PWNED"},
                {"type": "create", "path": "/abs/evil.txt", "content": "PWNED"},
                {"type": "create", "path": "ok.txt", "content": "OK"},
            ]

    saved = _install_fakes(Escaper)
    try:
        out = runner.compute_fixes("any-branch")
    finally:
        _restore(saved)

    paths = [c["path"] for c in out]
    assert "../evil.txt" not in paths, out
    assert "/abs/evil.txt" not in paths, out
    assert "ok.txt" in paths, out
    assert len(out) == 1, out


# ------------------------------------------------- кілька fix_branch на файл
# Симптом з практики: «тест → автофікс → залив → знову ті самі помилки».
# Причина: кожен fix_branch отримував ОДИН І ТОЙ САМИЙ знімок, тож правка
# пізнішого чека перезаписувала правку раннього (а мітка раннього лишалась
# у checks — прев'ю брехало, що застосовано обидві).
def _install_many(modules):
    saved = (runner.checks_for_active_project, runner.snapshot_files,
             runner.read_snapshot_file, runner.snapshot_dir)
    runner.checks_for_active_project = lambda: [{
        "id": f"fake{i}", "name": f"Fake{i}", "files": ["*.php"], "fixable": True,
        "group": "auto", "module": m, "error": None,
        "projects": ["php"], "description": "",
    } for i, m in enumerate(modules)]
    runner.snapshot_files = lambda branch: ["index.php"]
    runner.read_snapshot_file = lambda branch, path: b"AAA\nBBB\n"
    runner.snapshot_dir = lambda branch: FAKE_BASE
    return saved


def _editor(old: str, new: str):
    class Ed:
        @staticmethod
        def fix_branch(files, all_paths, branch):
            return [{"type": "edit", "path": "index.php",
                     "content": files["index.php"].replace(old, new)}]
    return Ed


def test_two_fix_branch_checks_land_both_edits_in_one_pass():
    saved = _install_many([_editor("AAA", "aaa"), _editor("BBB", "bbb")])
    try:
        out = runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    items = [c for c in out if c["path"] == "index.php"]
    assert len(items) == 1, out
    assert items[0]["new"] == "aaa\nbbb\n", items[0]["new"]
    assert sorted(items[0]["checks"]) == ["Fake0", "Fake1"], items[0]["checks"]


def test_later_check_sees_the_text_of_the_earlier_one():
    seen = {}

    class Reader:
        @staticmethod
        def fix_branch(files, all_paths, branch):
            seen["text"] = files["index.php"]
            return []

    saved = _install_many([_editor("AAA", "aaa"), Reader])
    try:
        runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    assert seen.get("text") == "aaa\nBBB\n", seen


def test_file_created_by_one_check_is_visible_to_the_next():
    seen = {}

    class Creator:
        @staticmethod
        def fix_branch(files, all_paths, branch):
            return [{"type": "create", "path": "logo.svg", "content": "<svg/>"}]

    class Reader:
        @staticmethod
        def fix_branch(files, all_paths, branch):
            seen["paths"] = list(all_paths)
            seen["files"] = dict(files)
            return []

    saved = _install_many([Creator, Reader])
    try:
        runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    assert "logo.svg" in seen.get("paths", []), seen.get("paths")
    assert seen.get("files", {}).get("logo.svg") == "<svg/>", seen.get("files")


def test_file_deleted_by_one_check_disappears_for_the_next():
    seen = {}

    class Deleter:
        @staticmethod
        def fix_branch(files, all_paths, branch):
            return [{"type": "delete", "path": "index.php"}]

    class Reader:
        @staticmethod
        def fix_branch(files, all_paths, branch):
            seen["paths"] = list(all_paths)
            return []

    saved = _install_many([Deleter, Reader])
    try:
        runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    assert "index.php" not in seen.get("paths", ["index.php"]), seen.get("paths")

# ------------------------------- create чи update вирішує ВІТКА, а не чек
# Кейс 09.09: GitLab відбиває ЦІЛИЙ коміт з 400 «A file with this name already
# exists», щойно в ньому є create на шлях, який у вітці вже лежить. Разом з ним
# гинуть і всі здорові правки того ж коміту — він атомарний. Наживо це дав
# `logo_brand`: він віддає create на src/assets/images/logo.svg завжди, а той
# файл є у 197 з 246 vue-віток.
def _install_snapshot(module, snapshot: dict):
    saved = (runner.checks_for_active_project, runner.snapshot_files,
             runner.read_snapshot_file, runner.snapshot_dir)
    runner.checks_for_active_project = lambda: [{
        "id": "fake", "name": "Fake", "files": ["*.php"], "fixable": True,
        "group": "auto", "module": module, "error": None,
        "projects": ["php"], "description": "",
    }]
    runner.snapshot_files = lambda branch: sorted(snapshot)
    runner.read_snapshot_file = lambda branch, path: snapshot[path]
    runner.snapshot_dir = lambda branch: FAKE_BASE
    return saved


def _creator(path: str, content: str):
    class C:
        @staticmethod
        def fix_branch(files, all_paths, branch):
            return [{"type": "create", "path": path, "content": content}]
    return C


def test_create_on_a_file_already_in_the_branch_becomes_an_edit():
    snap = {"index.php": b"ORIGINAL", "logo.svg": b"<svg>OLD</svg>"}
    saved = _install_snapshot(_creator("logo.svg", "<svg>NEW</svg>"), snap)
    try:
        out = runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    items = [c for c in out if c["path"] == "logo.svg"]
    assert len(items) == 1, out
    assert items[0]["type"] == "edit", items[0]
    # old береться зі знімка — інакше прев'ю показало б «новий файл» і людина
    # не побачила б, що насправді перезаписує наявний
    assert items[0]["old"] == "<svg>OLD</svg>", items[0]
    assert items[0]["new"] == "<svg>NEW</svg>", items[0]


def test_no_commit_action_creates_a_path_that_is_already_in_the_branch():
    """Те, заради чого правило й існує: саме ця дія відбивала коміт цілком."""
    snap = {"index.php": b"ORIGINAL", "logo.svg": b"<svg>OLD</svg>"}
    saved = _install_snapshot(_creator("logo.svg", "<svg>NEW</svg>"), snap)
    try:
        acts = runner.actions_for(runner.compute_fixes("any-branch"))
    finally:
        _restore(saved)
    assert acts, "правка мусить лишитись, просто іншою дією"
    for a in acts:
        assert not (a["action"] == "create" and a["file_path"] in snap), acts


def test_create_of_a_genuinely_new_file_stays_a_create():
    saved = _install_snapshot(_creator("logo.svg", "<svg/>"), {"index.php": b"ORIGINAL"})
    try:
        out = runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    items = [c for c in out if c["path"] == "logo.svg"]
    assert len(items) == 1 and items[0]["type"] == "create", out


def test_a_byte_identical_rewrite_is_not_a_change_at_all():
    """nwf-bafhuge-colsetfugii-br-pt: чек генерує ТУ САМУ лого-svg, що вже
    лежить у вітці. Такому файлу нема чого їхати ні в прев'ю, ні в коміт."""
    snap = {"index.php": b"ORIGINAL", "logo.svg": b"<svg>SAME</svg>"}
    saved = _install_snapshot(_creator("logo.svg", "<svg>SAME</svg>"), snap)
    try:
        out = runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    assert out == [], out


def test_edit_of_a_file_absent_from_the_branch_becomes_a_create():
    """Дзеркальний бік правила: update на шлях, якого у вітці немає, GitLab
    відбиває так само — «A file with this name doesn\'t exist»."""
    class Ed:
        @staticmethod
        def fix_branch(files, all_paths, branch):
            return [{"type": "edit", "path": "new.txt", "content": "HELLO"}]

    saved = _install_snapshot(Ed, {"index.php": b"ORIGINAL"})
    try:
        out = runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    items = [c for c in out if c["path"] == "new.txt"]
    assert len(items) == 1 and items[0]["type"] == "create", out


def test_a_path_deleted_in_this_commit_is_written_back_as_a_create():
    """Наявність рахується на момент КОМІТУ, а не знімка: файл, що його
    видалив попередній чек, для git уже не існує."""
    class Deleter:
        @staticmethod
        def fix_branch(files, all_paths, branch):
            return [{"type": "delete", "path": "index.php"}]

    class Writer:
        @staticmethod
        def fix_branch(files, all_paths, branch):
            return [{"type": "create", "path": "index.php", "content": "BACK"}]

    saved = _install_many([Deleter, Writer])
    try:
        out = runner.compute_fixes("any-branch")
    finally:
        _restore(saved)
    items = [c for c in out if c["path"] == "index.php" and c["type"] != "delete"]
    assert len(items) == 1 and items[0]["type"] == "create", out


if __name__ == "__main__":
    run(dict(globals()))
