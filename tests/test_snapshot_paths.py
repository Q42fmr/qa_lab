"""Тести шляхів знімків і чесності «вітка синхронізована».

Корінь реального інциденту: у GitLab `OURSV_br-…` і `oursv_br-…` — ДВІ різні
вітки, а Windows не розрізняє регістр, тож `snapshot_dir()` віддавав для них
ту саму теку. Сервіс показував чужий вміст і вважав вітку синхронізованою,
хоча Sync для неї не запускався; фікс, застосований у такому стані, записав
би у вітку файли іншого вайта.
"""
import json
import os
import sys
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import projects                                                   # noqa: E402
import runner                                                     # noqa: E402


def _tmp_state():
    """Підміняє теку стану, щоб cache_root() дивився в tempdir."""
    d = Path(tempfile.mkdtemp(prefix="snap-"))
    projects.state_dir = lambda: d
    return d


def _snapshot(branch, files=None, commit="abc12345", meta_branch="__self__"):
    """Створює теку знімка з метаданими. meta_branch=None — легасі без поля."""
    d = runner.snapshot_dir(branch)
    d.mkdir(parents=True, exist_ok=True)
    for name, text in (files or {"index.html": "<html>"}).items():
        (d / name).write_text(text, encoding="utf-8")
    meta = {"files": len(files or {"index.html": ""}), "commit": commit}
    if meta_branch == "__self__":
        meta["branch"] = branch
    elif meta_branch is not None:
        meta["branch"] = meta_branch
    (d / ".snapshot.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


# ------------------------------------------------------------------ шляхи
def test_meta_folder_of_tsm_import_is_not_part_of_the_site():
    """`_meta/` (manifest/check.json/original-знімок донора) — не сторінки
    вайта: sokkoruuzosnacav 21.10 — фікси футера подвоювались на донорських
    копіях (61 файл замість 31)."""
    _tmp_state()
    d = _snapshot("sos-br-pt", {"index.php": "<html>"})
    (d / "sobre").mkdir(); (d / "sobre" / "index.html").write_text("<html>", encoding="utf-8")
    (d / "_meta" / "original").mkdir(parents=True)
    (d / "_meta" / "manifest.json").write_text("{}", encoding="utf-8")
    (d / "_meta" / "original" / "index.html").write_text("<html>", encoding="utf-8")
    assert runner.snapshot_files("sos-br-pt") == ["index.php", "sobre/index.html"]


def test_lowercase_branch_keeps_plain_folder():
    """Наявний кеш (5777 тек, 4.9 ГБ) не мусить знецінитись — для звичайних
    назв у нижньому регістрі шлях лишається точно таким, як був."""
    _tmp_state()
    assert runner.snapshot_dir("haofmcanm-ch-de").name == "haofmcanm-ch-de"
    assert runner.snapshot_dir("auto_br-como-ler-dados-01").name == \
        "auto_br-como-ler-dados-01"


def test_case_variants_get_distinct_folders():
    """Суть фікса: дві вітки, що різняться лише регістром, більше не ділять теку."""
    _tmp_state()
    up = runner.snapshot_dir("OURSV_br-carreiras-01")
    lo = runner.snapshot_dir("oursv_br-carreiras-01")
    assert up.resolve() != lo.resolve()
    assert lo.name == "oursv_br-carreiras-01", "нижній регістр — без суфікса"
    assert up.name.startswith("oursv_br-carreiras-01") is False or up.name != lo.name


def test_three_case_variants_all_distinct():
    _tmp_state()
    names = {runner.snapshot_dir(n).name.lower()
             for n in ("Feature-X", "feature-x", "FEATURE-X")}
    assert len(names) == 3, "усі варіанти мусять мати РІЗНІ теки навіть без регістру"


def test_namespaced_branch_no_longer_collides_with_underscore_name():
    """Фолдинг `/`→`__` зливав `a/b` і `a__b` — той самий клас помилки."""
    _tmp_state()
    assert runner.snapshot_dir("feat/x").resolve() != \
        runner.snapshot_dir("feat__x").resolve()


def test_suffix_is_stable_across_calls():
    _tmp_state()
    a = runner.snapshot_dir("OURSV_br-x")
    b = runner.snapshot_dir("OURSV_br-x")
    assert a == b, "шлях мусить бути детермінованим, інакше знімок «губиться»"


def test_traversal_is_still_blocked():
    _tmp_state()
    for bad in ("..", ".", "", "../../etc/passwd", "/abs/path", "..\\..\\win"):
        try:
            p = runner.snapshot_dir(bad)
        except ValueError:
            continue
        base = runner.cache_root().resolve()
        assert base in p.parents, f"{bad!r} вийшов за cache/: {p}"


# ------------------------------------------------------------- is_synced
def test_not_synced_without_folder():
    _tmp_state()
    assert runner.is_synced("nope-br-pt") is False


def test_synced_for_own_snapshot():
    _tmp_state()
    _snapshot("alfa-br-pt")
    assert runner.is_synced("alfa-br-pt") is True


def test_not_synced_when_folder_holds_another_branch():
    """Ядро гарда: навіть якщо тека є (на Windows — тека двійника за
    регістром), знімок чужий -> вітка НЕ синхронізована."""
    _tmp_state()
    d = runner.snapshot_dir("alfa-br-pt")
    d.mkdir(parents=True, exist_ok=True)
    (d / ".snapshot.json").write_text(
        json.dumps({"branch": "OTHER-br-pt", "files": 3, "commit": "dead"}),
        encoding="utf-8")
    assert runner.is_synced("alfa-br-pt") is False


def test_legacy_snapshot_without_meta_file_is_trusted():
    """Знімки без метаданих не оголошуємо несинхронізованими — інакше
    оновлення коду = ре-синк усього кешу."""
    _tmp_state()
    d = runner.snapshot_dir("legacy-br-pt")
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text("<html>", encoding="utf-8")
    assert runner.is_synced("legacy-br-pt") is True


def test_legacy_meta_without_branch_field_is_trusted():
    _tmp_state()
    _snapshot("legacy2-br-pt", meta_branch=None)
    assert runner.is_synced("legacy2-br-pt") is True


def test_broken_meta_is_trusted_not_crashing():
    _tmp_state()
    d = runner.snapshot_dir("broken-br-pt")
    d.mkdir(parents=True, exist_ok=True)
    (d / ".snapshot.json").write_text("{битий json", encoding="utf-8")
    assert runner.is_synced("broken-br-pt") is True


def test_empty_folder_is_not_synced():
    """Обірваний синк лишає порожню теку: `sync_branch` створює каталог ДО
    завантаження, а `.snapshot.json` пише останнім. Такий каталог раніше
    проходив як «легасі без метаданих» — вітка ніколи не пересинхронізовувалась,
    а чеки бачили нуль файлів і рапортували «чисто»."""
    _tmp_state()
    runner.snapshot_dir("obirvanyi-br-pt").mkdir(parents=True, exist_ok=True)
    assert runner.is_synced("obirvanyi-br-pt") is False


def test_folder_with_only_meta_is_synced():
    """Успішний синк завжди лишає щонайменше `.snapshot.json` — вітка без
    жодного файлу в репо це не збій, і ре-синку не потребує."""
    _tmp_state()
    d = runner.snapshot_dir("porozhnia-br-pt")
    d.mkdir(parents=True, exist_ok=True)
    (d / ".snapshot.json").write_text(
        json.dumps({"branch": "porozhnia-br-pt", "files": 0, "commit": "a1"}),
        encoding="utf-8")
    assert runner.is_synced("porozhnia-br-pt") is True


def test_run_checks_refuses_unsynced_branch():
    """Мовчазний зелений на нулі файлів гірший за помилку."""
    _tmp_state()
    runner.snapshot_dir("obirvanyi2-br-pt").mkdir(parents=True, exist_ok=True)
    try:
        runner.run_checks("obirvanyi2-br-pt")
    except ValueError as e:
        assert "не синхронізована" in str(e), e
    else:
        raise AssertionError("run_checks мовчки повернув результат без знімка")


def test_run_checks_refuses_missing_branch():
    _tmp_state()
    try:
        runner.run_checks("nikoly-ne-bulo-br-pt")
    except ValueError:
        pass
    else:
        raise AssertionError("run_checks не впав на відсутньому знімку")


# ------------------------------------------------------- sync: skip-логіка
class FakeClient:
    def __init__(self, commit="abc12345", files=None):
        self.commit_id = commit
        self.files = files or {"index.html": "<html>fresh"}
        self.archive_calls = 0

    def branch(self, name):
        return {"name": name, "commit": self.commit_id, "updated": ""}

    def archive(self, branch):
        self.archive_calls += 1
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, text in self.files.items():
                z.writestr(f"proj-{self.commit_id}/{name}", text)
        return buf.getvalue()


def test_sync_skips_own_snapshot_at_same_commit():
    _tmp_state()
    _snapshot("alfa-br-pt", commit="abc12345")
    cl = FakeClient(commit="abc12345")
    meta = runner.sync_branch(cl, "alfa-br-pt")
    assert meta.get("skipped") is True
    assert cl.archive_calls == 0, "нічого качати — знімок актуальний"


def test_sync_does_not_skip_when_snapshot_belongs_to_another_branch():
    """Раніше skip-перевірка дивилась ЛИШЕ на sha: чужий знімок із тим самим
    комітом вважався актуальним, і вітка назавжди лишалась із чужим вмістом."""
    _tmp_state()
    d = runner.snapshot_dir("alfa-br-pt")
    d.mkdir(parents=True, exist_ok=True)
    (d / "old.html").write_text("чужий вміст", encoding="utf-8")
    (d / ".snapshot.json").write_text(
        json.dumps({"branch": "OTHER-br-pt", "files": 1, "commit": "abc12345"}),
        encoding="utf-8")
    cl = FakeClient(commit="abc12345")
    meta = runner.sync_branch(cl, "alfa-br-pt")
    assert not meta.get("skipped"), "мусив перекачати, а не повірити sha"
    assert meta["branch"] == "alfa-br-pt"
    assert cl.archive_calls == 1
    assert not (d / "old.html").exists(), "чужі файли мусили піти"


def test_sync_writes_branch_into_meta():
    _tmp_state()
    cl = FakeClient(commit="ff00ff00")
    meta = runner.sync_branch(cl, "beta-br-pt")
    assert meta["branch"] == "beta-br-pt" and meta["commit"] == "ff00ff00"
    assert runner.is_synced("beta-br-pt") is True


if __name__ == "__main__":
    run(dict(globals()))
