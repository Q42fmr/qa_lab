"""Скан ClickUp - стан ВОРКСПЕЙСУ, не проєкту.

`clickup_client.fetch_all()` не має параметра проєкту: він читає той самий
токен і те саме вʼю, отже скан для php- і vue-вайтів однаковий. Доки файл
лежав у теці проєкту, перемикання показувало інший скан і змушувало парсити
ClickUp заново (заміряно: 460 тасок у white-pages проти 401 у vue, причому
vue-скан - строга підмножина; `comment_themes` розійшлись на 12 проти 8).

Тести ганяються в тимчасовій теці з підміненим реєстром проєктів, щоб не
торкатись робочого стану лаби.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                    # noqa: E402

import projects                                             # noqa: E402


class _Anon:
    """Запит без користувача: ці тести про СПІЛЬНИЙ скан, а він однаковий для
    всіх. Ендпоінти беруть людину з `request.state`, щоб додати їй її ж
    розшарені таски (`test_cu_saved_split.py`) — тут її просто немає."""

    class _State:
        user = {}

    def __init__(self):
        self.state = _Anon._State()


class _Sandbox:
    """Тимчасовий cwd + реєстр із двох проєктів: корінь і projects/vue."""

    def __enter__(self):
        self._cwd = os.getcwd()
        self._reg = dict(projects._registry)
        self._cur = projects._current
        self.dir = Path(tempfile.mkdtemp(prefix="qa_lab-shared-"))
        os.chdir(self.dir)
        (self.dir / "projects" / "vue").mkdir(parents=True, exist_ok=True)
        projects._registry.clear()
        projects._registry.update(_REG)
        projects._current = "white-pages"
        return self

    def __exit__(self, *exc):
        os.chdir(self._cwd)
        projects._registry.clear()
        projects._registry.update(self._reg)
        projects._current = self._cur
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)


def _scan(ts, ids):
    return json.dumps({"ts": ts, "tasks": [{"id": i} for i in ids]},
                      ensure_ascii=False)


def _write(pid, name, text):
    p = projects.state_file_for(pid, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


_REG = {
    "white-pages": {"id": "white-pages", "root": Path(".")},
    "vue": {"id": "vue", "root": Path("projects/vue")},
}


def _fresh_app():
    """app з нуля - прапорець одноразової міграції має бути незнятий."""
    for m in ("app", "comment_themes"):
        sys.modules.pop(m, None)
    import app
    # Імпорт app кличе projects.init() (app.py:56), а той будує реєстр з .env
    # і РЕБІНДИТЬ _registry: підміна пісочниці зникає разом з проєктом vue
    # (він реєструється лише за VUE_GITLAB_PROJECT+TOKEN). Без цього рядка
    # project_copies() віддає порожньо, міграція виходить на першій перевірці,
    # і тест «найсвіжіший виграє» мовчки перевіряв би, що нічого не сталось.
    projects._registry.clear()
    projects._registry.update(_REG)
    return app


# ------------------------------------------------- спільне місце
def test_shared_file_is_the_same_path_for_every_project():
    with _Sandbox():
        projects._current = "white-pages"
        a = projects.shared_file("clickup_tasks.json").resolve()
        projects._current = "vue"
        b = projects.shared_file("clickup_tasks.json").resolve()
        assert a == b, (a, b)


def test_project_state_stays_per_project():
    """Спільним стає САМЕ скан; решта стану проєктів не змішується."""
    with _Sandbox():
        projects._current = "white-pages"
        a = projects.state_file("branches.json").resolve()
        projects._current = "vue"
        b = projects.state_file("branches.json").resolve()
        assert a != b, (a, b)


def test_project_copies_skips_the_shared_root():
    """Корінь - це і тека white-pages, і спільне місце. Він не має потрапляти
    у список копій на переїзд, інакше міграція видалила б цільовий файл."""
    with _Sandbox():
        _write("white-pages", "clickup_tasks.json", _scan("2026-01-01", ["a"]))
        _write("vue", "clickup_tasks.json", _scan("2026-01-02", ["b"]))
        copies = [p.resolve() for p in projects.project_copies("clickup_tasks.json")]
        assert projects.shared_file("clickup_tasks.json").resolve() not in copies
        assert len(copies) == 1, copies


# ------------------------------------------------- переїзд скану
def test_migration_keeps_the_freshest_scan():
    """У проєктах лежали різні скани; виграє найсвіжіший за ts - саме те, що
    дав би новий прогін. Зливати їх не можна: 59 «зайвих» тасок старого скану
    мали статуси qa/approved, тобто вийшли з фільтра."""
    with _Sandbox():
        _write("white-pages", "clickup_tasks.json",
               _scan("2026-08-14 13:18:46", ["old", "gone1", "gone2"]))
        _write("vue", "clickup_tasks.json",
               _scan("2026-08-14 14:52:56", ["old"]))
        app = _fresh_app()
        got = app.clickup_saved(_Anon())
        assert got["ts"] == "2026-08-14 14:52:56", got["ts"]
        assert [t["id"] for t in got["tasks"]] == ["old"], got["tasks"]


def test_the_root_scan_wins_when_it_is_the_freshest():
    """Корінь - теж кандидат, а не лише ціль. Якщо останній скан робили з-під
    white-pages (його файл і є спільним), він мусить вижити: інакше переїзд
    відкотив би стан до старішого vue-скану."""
    with _Sandbox():
        _write("white-pages", "clickup_tasks.json",
               _scan("2026-08-14 16:00:00", ["new1", "new2"]))
        _write("vue", "clickup_tasks.json",
               _scan("2026-08-14 09:00:00", ["stale"]))
        got = _fresh_app().clickup_saved(_Anon())
        assert got["ts"] == "2026-08-14 16:00:00", got["ts"]
        assert [t["id"] for t in got["tasks"]] == ["new1", "new2"], got["tasks"]


def test_migration_removes_the_project_copies():
    """Копії прибираються, інакше лишається з чого дрейфувати далі."""
    with _Sandbox():
        _write("white-pages", "clickup_tasks.json", _scan("2026-01-01", ["a"]))
        _write("vue", "clickup_tasks.json", _scan("2026-01-02", ["b"]))
        _fresh_app().clickup_saved(_Anon())
        assert projects.project_copies("clickup_tasks.json") == []
        assert projects.shared_file("clickup_tasks.json").exists()


def test_both_projects_read_the_same_scan_after_migration():
    """Головний контракт: перемикання проєкту не міняє список тасок."""
    with _Sandbox():
        _write("white-pages", "clickup_tasks.json", _scan("2026-01-01", ["a", "b"]))
        _write("vue", "clickup_tasks.json", _scan("2026-01-02", ["c"]))
        app = _fresh_app()
        projects._current = "white-pages"
        first = app.clickup_saved(_Anon())
        projects._current = "vue"
        second = app.clickup_saved(_Anon())
        assert first == second, (first, second)


def test_scan_saved_under_one_project_is_visible_from_the_other():
    with _Sandbox():
        app = _fresh_app()
        projects._current = "vue"
        app.clickup_save(app.ClickUpSaveRequest(tasks=[{"id": "x"}, {"id": "y"}]), _Anon())
        projects._current = "white-pages"
        got = app.clickup_saved(_Anon())
        assert [t["id"] for t in got["tasks"]] == ["x", "y"], got


def test_missing_scan_is_reported_as_empty():
    with _Sandbox():
        got = _fresh_app().clickup_saved(_Anon())
        assert got == {"ts": None, "tasks": []}, got


def test_broken_project_copy_does_not_lose_the_good_scan():
    """Битий json в одній теці не має знищувати робочий скан у другій."""
    with _Sandbox():
        _write("white-pages", "clickup_tasks.json", _scan("2026-01-01", ["good"]))
        _write("vue", "clickup_tasks.json", "{ це не json")
        got = _fresh_app().clickup_saved(_Anon())
        assert [t["id"] for t in got["tasks"]] == ["good"], got


def test_empty_copy_does_not_win_over_a_real_scan():
    """Порожній скан із новішим ts не має витісняти справжній: у ньому нема
    тасок, тобто нема чого показувати."""
    with _Sandbox():
        _write("white-pages", "clickup_tasks.json", _scan("2026-01-01", ["good"]))
        _write("vue", "clickup_tasks.json",
               json.dumps({"ts": "2026-09-09", "tasks": []}))
        got = _fresh_app().clickup_saved(_Anon())
        assert [t["id"] for t in got["tasks"]] == ["good"], got


# ------------------------------------------------- переїзд тем коментарів
def test_themes_are_merged_not_replaced():
    """Теми - похідне того ж скану, тож теж спільні. При переїзді ключі
    ОБʼЄДНУЮТЬСЯ: у корпусі було 12 у white-pages і 8 у vue, і губити чотири
    зайві не за що."""
    with _Sandbox():
        _write("white-pages", "comment_themes.json", json.dumps(
            {"a-br-pt": {"theme": "лого", "comment_ts": "1"},
             "only-wp": {"theme": "пошта", "comment_ts": "1"}}))
        _write("vue", "comment_themes.json", json.dumps(
            {"a-br-pt": {"theme": "лого новіше", "comment_ts": "2"},
             "only-vue": {"theme": "форма", "comment_ts": "1"}}))
        sys.modules.pop("comment_themes", None)
        import comment_themes
        got = comment_themes._load()
        assert set(got) == {"a-br-pt", "only-wp", "only-vue"}, got
        assert got["a-br-pt"]["theme"] == "лого новіше", got["a-br-pt"]


def test_themes_copies_are_removed():
    with _Sandbox():
        _write("vue", "comment_themes.json", json.dumps({"b": {"theme": "x"}}))
        sys.modules.pop("comment_themes", None)
        import comment_themes
        comment_themes._load()
        assert projects.project_copies("comment_themes.json") == []


def test_theme_saved_under_one_project_is_visible_from_the_other():
    with _Sandbox():
        sys.modules.pop("comment_themes", None)
        import comment_themes
        projects._current = "vue"
        comment_themes._save({"z-br-pt": {"theme": "адреса"}})
        projects._current = "white-pages"
        assert comment_themes.theme_for("z-br-pt") == {"theme": "адреса"}


def test_themes_are_read_from_the_shared_file_under_every_project():
    """Читати треба спільний файл, а не файл активного проєкту. Для
    white-pages ці шляхи випадково збігаються (його тека - корінь), тож
    розрізняє саме читання з-під vue."""
    with _Sandbox():
        sys.modules.pop("comment_themes", None)
        import comment_themes
        projects._current = "white-pages"
        comment_themes._save({"q-br-pt": {"theme": "пін без адреси"}})
        projects._current = "vue"
        assert comment_themes.theme_for("q-br-pt") == {"theme": "пін без адреси"}


def test_an_older_copy_does_not_overwrite_a_newer_theme():
    """Злиття йде ЗА СВІЖІСТЮ коментаря, а не за порядком файлів: коли новіший
    запис лежить у корені, а старіший у теці проєкту, сліпе перезаписування
    відкотило б тему назад."""
    with _Sandbox():
        _write("white-pages", "comment_themes.json", json.dumps(
            {"a-br-pt": {"theme": "свіже", "comment_ts": "2026-08-14 15:00"}}))
        _write("vue", "comment_themes.json", json.dumps(
            {"a-br-pt": {"theme": "старе", "comment_ts": "2026-08-01 10:00"}}))
        sys.modules.pop("comment_themes", None)
        import comment_themes
        got = comment_themes._load()
        assert got["a-br-pt"]["theme"] == "свіже", got["a-br-pt"]


if __name__ == "__main__":
    run(dict(globals()))
