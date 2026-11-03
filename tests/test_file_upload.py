"""Заливка локальних файлів у знімок вітки.

Навіщо. Покласти у вітку СВОЄ фото можна було рівно одним способом: 📂 →
провідник → кинути файл у `cache/<вітка>/` → «Локальні зміни» → закомітити.
Провідник відкривається НА СЕРВЕРІ, тож у контейнері цей вхід зник разом з
робочим столом — а разом з ним і вся можливість (кейс 28.08).

Заливка — другий вхід у ТОЙ САМИЙ конвеєр, і головне тут те, чого вона НЕ
робить: вона не комітить. Файли лягають у знімок, коміт лишається за
«Локальними змінами» і `log_commit()`. Інакше з'явився б другий шлях у git
повз Журнал і revert — пряма заборона з конвенцій репозиторію.
"""
import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ІЗОЛЯЦІЯ ДО ПЕРШОГО ІМПОРТУ: корінь стану за замовчуванням — корінь репо,
# тож знімки тестових віток лягли б у робоче дерево.
_TMP = tempfile.mkdtemp(prefix="qa_lab-upload-")
os.environ["QA_LAB_STATE_DIR"] = _TMP

from _harness import ROOT, run                                    # noqa: E402

import projects                                                   # noqa: E402

projects.init()

import runner                                                     # noqa: E402

APP_SRC = (ROOT / "app.py").read_text(encoding="utf-8")
UI_SRC = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

# 1×1 PNG і 1×1 GIF — щоб перевірити перегін формату справжніми байтами
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


def _branch(name: str = "up-test"):
    """Порожній, але «синхронізований» знімок."""
    d = runner.snapshot_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / ".snapshot.json").write_text('{"branch": "%s"}' % name, encoding="utf-8")
    return d


def _call(**body):
    """Ендпоінт як звичайна корутина — без підняття сервера."""
    import asyncio
    import json as _json

    import app

    class _Req:
        headers = {"content-length": str(len(_json.dumps(body)))}

        async def json(self):
            return body

    return asyncio.get_event_loop().run_until_complete(app.files_upload(_Req()))


def _fails(**body):
    from fastapi import HTTPException
    try:
        _call(**body)
    except HTTPException as e:
        return e.status_code, str(e.detail)
    raise AssertionError("очікувалась відмова, а запит пройшов")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ------------------------------------------------- межі вітки

def test_no_name_can_escape_the_branch_folder():
    """Ім'я файлу приходить з диска користувача, тека — з форми; обидва ведуть
    до шляху, у який ми ПИШЕМО.

    Властивість, яку стережемо, — не «конкретний код відповіді», а те, що
    ЖОДЕН запис не виходить за межі вітки. `../evil.txt` не відхиляється, а
    зводиться до `evil.txt` усередині вітки — це той самий інваріант, тільки
    зручніший для людини, яка тягне файл з довільної теки.
    """
    from fastapi import HTTPException
    d = _branch()
    outside = d.parent / "evil.txt"
    outside.unlink(missing_ok=True)
    for name in ("../evil.txt", "..", ".", "sub/../../evil.txt", "/etc/evil.txt"):
        try:
            r = _call(branch="up-test", dir="",
                      items=[{"name": name, "content_b64": _b64(b"x")}])
        except HTTPException as e:
            assert e.status_code == 400, (name, e.status_code)
            continue
        # не відхилено — значить зведено до безпечного імені ВСЕРЕДИНІ вітки
        got = (d / r["saved"][0]["path"]).resolve()
        assert d.resolve() in got.parents, (name, got)
    assert not outside.exists(), "запис виліз за межі вітки"


def test_a_traversing_dir_is_refused_outright():
    """Теку людина вписує руками, і звести її до «останнього сегмента» не
    можна — вкладеність тут осмислена. Тому просто відмова."""
    _branch()
    for bad in ("../..", "..", "../sibling"):
        code, _ = _fails(branch="up-test", dir=bad,
                         items=[{"name": "ok.txt", "content_b64": _b64(b"x")}])
        assert code == 400, bad
    assert not (runner.snapshot_dir("up-test").parent / "ok.txt").exists()


def test_absolute_name_is_reduced_to_its_last_segment():
    """Браузери віддають лише ім'я, але API відкрите — /etc/passwd має стати
    просто `passwd` усередині вітки, а не шляхом."""
    d = _branch()
    r = _call(branch="up-test", dir="",
              items=[{"name": "/etc/passwd", "content_b64": _b64(b"root")}])
    assert r["saved"][0]["path"] == "passwd"
    assert (d / "passwd").read_bytes() == b"root"


# ------------------------------------------------- межі розміру

def test_one_oversized_file_is_refused():
    import app
    _branch()
    big = b"x" * (app.UPLOAD_MAX_FILE + 1)
    code, detail = _fails(branch="up-test", dir="",
                          items=[{"name": "big.bin", "content_b64": _b64(big)}])
    assert code == 413, (code, detail)
    assert not (runner.snapshot_dir("up-test") / "big.bin").exists(), \
        "файл понад межу все одно записався"


def test_the_sum_is_capped_too():
    """Десять файлів по 5 МБ поодинці проходять — разом ні."""
    import app
    _branch()
    chunk = b"y" * (app.UPLOAD_MAX_FILE // 3)
    items = [{"name": f"f{i}.bin", "content_b64": _b64(chunk)} for i in range(20)]
    code, _ = _fails(branch="up-test", dir="", items=items)
    assert code == 413


def test_size_is_checked_before_the_body_is_parsed():
    """Інакше двохсотмегабайтний json встигає лягти в пам'ять процесу."""
    body = APP_SRC[APP_SRC.index("async def files_upload("):]
    body = body[:body.index("\n@app.")]
    assert body.index("content-length") < body.index("await request.json()"), body


# ------------------------------------------------- що саме кладеться

def test_new_file_lands_and_is_reported_as_created():
    d = _branch()
    r = _call(branch="up-test", dir="assets/img",
              items=[{"name": "hero.png", "content_b64": _b64(PNG)}])
    assert r["saved"] == [{"path": "assets/img/hero.png", "status": "created",
                           "size": len(PNG)}]
    assert (d / "assets" / "img" / "hero.png").read_bytes() == PNG


def test_binary_survives_byte_for_byte():
    """Фото — бінарник; base64 не має його зіпсувати ні на байт."""
    d = _branch()
    blob = bytes(range(256)) * 40
    _call(branch="up-test", dir="", items=[{"name": "b.bin", "content_b64": _b64(blob)}])
    assert (d / "b.bin").read_bytes() == blob


def test_replacing_an_image_converts_it_to_the_promised_format():
    """Урок `media.ensure_format`: gif під іменем .png — реальний випадок.
    Для НОВОГО файлу перегону немає, бо ім'я приносить сам файл."""
    d = _branch()
    _call(branch="up-test", dir="", items=[{"name": "pic.png", "content_b64": _b64(PNG)}])
    r = _call(branch="up-test", dir="", items=[{"name": "pic.png", "content_b64": _b64(GIF)}])
    assert r["saved"][0]["status"] == "replaced"
    assert r["converted"], "gif ліг під іменем .png без перегону"
    assert (d / "pic.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_unsynced_branch_is_refused():
    code, detail = _fails(branch="ніколи-не-синкали", dir="",
                          items=[{"name": "a.txt", "content_b64": _b64(b"x")}])
    assert code == 400 and "Sync" in detail


# ------------------------------------------------- головне: НЕ комітить

def test_upload_never_commits():
    """Конвенція репозиторію: жодних шляхів у git повз `log_commit()`.
    Заливка кладе файли у знімок, коміт — окремий крок у «Локальних змінах»."""
    _branch()
    r = _call(branch="up-test", dir="",
              items=[{"name": "n.txt", "content_b64": _b64(b"hi")}])
    assert r["committed"] is False
    body = APP_SRC[APP_SRC.index("async def files_upload("):]
    body = body[:body.index("\n@app.")]
    for forbidden in ("client.commit", "log_commit"):
        assert forbidden not in body, f"заливка сама комітить ({forbidden})"


# ------------------------------------------------- кнопки, яким нема куди

def test_local_only_buttons_are_gated_by_local_fs():
    """📂 і IDE відкриваються НА СЕРВЕРІ. У контейнері `xdg-open` є, а
    `DISPLAY` порожній — Popen не скаржиться, і кнопка мовчки бреше."""
    import app
    assert "local_fs" in APP_SRC[APP_SRC.index("def status()"):][:900]
    body = APP_SRC[APP_SRC.index("def open_folder("):]
    body = body[:body.index("\n@app.")]
    assert "can_open_locally()" in body, "/api/open_folder досі вдає успіх"
    # у контейнері (без DISPLAY) — саме false
    old = os.environ.pop("DISPLAY", None)
    try:
        if os.name != "nt" and sys.platform != "darwin":
            assert app.can_open_locally() is False
    finally:
        if old is not None:
            os.environ["DISPLAY"] = old
    for marker in ("b.synced&&localFs", "${localFs?"):
        assert marker in UI_SRC, f"кнопка 📂 не під localFs: {marker}"
    assert "localFs&&currentFile" in UI_SRC, "IDE-кнопки не під localFs"


def test_ui_uploads_and_then_shows_local_changes():
    """Після заливки людина не має згадувати про сусідню підвкладку сама."""
    body = UI_SRC[UI_SRC.index("async function uploadFiles"):]
    body = body[:body.index("\n$('#upFiles')")]
    assert "/api/files/upload" in body
    assert "lcLoad()" in body, "не веде до «Локальних змін»"
    assert "dataTransfer" in UI_SRC, "немає перетягування файлів"


if __name__ == "__main__":
    run(dict(globals()))
