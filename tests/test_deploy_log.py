"""Чому сторінка вайта порожня — і де це взагалі побачити.

28.08 колега відкрив php-вайт на прев'ю-хості й отримав БІЛИЙ АРКУШ. Vue-вайт
поруч рендерився нормально. Причина класу «мовчазна деградація»:

  * в образі `display_errors = Off`, а `log_errors = On` з порожнім
    `error_log` — тобто фатальна помилка php не потрапляє НІ в тіло
    відповіді, ні у файл. Вона йде в stderr процесу `php -S`;
  * `_serve()` віддавав цей stderr у `subprocess.DEVNULL`.

Разом: 500 з тілом на 0 байт і жодного пояснення ніде. Заміряно на стенді —
вайт з `require vendor/autoload.php` і класом, якого в стабі немає (у стабі
лише Dotenv), віддає рівно це.
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ІЗОЛЯЦІЯ ДО ПЕРШОГО ІМПОРТУ. Корінь стану за замовчуванням — корінь
# репозиторію, тож `deploy_root()` без цього дивився б у робоче дерево, а
# `log_path()` створював би там теки. Ставиться на рівні МОДУЛЯ навмисно:
# `projects` фіксує частину шляхів на імпорті.
_TMP = tempfile.mkdtemp(prefix="qa_lab-deploy-log-")
os.environ["QA_LAB_STATE_DIR"] = _TMP

from _harness import ROOT, run                                    # noqa: E402

import projects                                                   # noqa: E402

projects.init()          # реєстр проєктів будує app.py на старті; тут — самі

import deployer                                                   # noqa: E402

DEPLOYER_SRC = (ROOT / "deployer.py").read_text(encoding="utf-8")
APP_SRC = (ROOT / "app.py").read_text(encoding="utf-8")
UI_SRC = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


# ------------------------------------------------- сам лог

def test_stderr_of_php_is_no_longer_thrown_away():
    """Головна гарда. Один `DEVNULL` тут повертає нас у стан, де «біла
    сторінка» не має пояснення взагалі."""
    body = DEPLOYER_SRC[DEPLOYER_SRC.index("def _serve("):]
    body = body[:body.index("\ndef _deploy_php")]
    # саме виклик, а не згадку: слово DEVNULL є в коментарі поруч навмисно
    assert "stderr=subprocess.DEVNULL" not in body, "stderr php -S знову йде в нікуди"
    assert "stdout=subprocess.DEVNULL" not in body, body
    assert "stderr=fh" in body and "stdout=fh" in body, body


def test_log_lands_next_to_the_deploy():
    p = deployer.log_path("feature/x")
    assert p.parent == deployer.deploy_root().resolve()
    assert p.name.endswith(".log")
    # те саме ім'я, що й у теки деплою — щоб їх було видно поруч
    assert p.stem == deployer._safe_deploy_name("feature/x")


def test_branch_name_cannot_escape_the_deploy_folder():
    """Назва вітки приходить з HTTP — той самий гард, що в snapshot_dir."""
    for bad in ("../../etc/passwd", "..", "/etc/passwd", "a/../../b"):
        p = deployer.log_path(bad)
        assert p.parent == deployer.deploy_root().resolve(), (bad, p)


def test_missing_log_reads_as_empty_not_as_an_error():
    assert deployer.read_log("ніколи-не-піднімали") == ""


def test_read_log_returns_the_tail():
    """Лог росте журналом запитів, тож цікавий саме хвіст."""
    p = deployer.log_path("tail-test")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(f"рядок {i}" for i in range(500)), encoding="utf-8")
    out = deployer.read_log("tail-test", limit=3).splitlines()
    assert out == ["рядок 497", "рядок 498", "рядок 499"], out
    assert len(deployer.read_log("tail-test").splitlines()) == 200   # дефолт


def test_limit_is_never_zero_or_negative():
    """`?limit=0` з URL не має віддавати порожнечу замість логу."""
    p = deployer.log_path("limit-test")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("a\nb\nc", encoding="utf-8")
    assert deployer.read_log("limit-test", limit=0) == "c"
    assert deployer.read_log("limit-test", limit=-5) == "c"


# ------------------------------------------------- чи є куди подивитись

def test_endpoint_exists_and_refuses_a_bad_name():
    assert '@app.get("/api/deploy/log")' in APP_SRC
    body = APP_SRC[APP_SRC.index('@app.get("/api/deploy/log")'):]
    body = body[:body.index("\n@app.")]
    assert "deployer.read_log" in body
    assert "HTTPException(400" in body, "гард імені вітки не перетворюється на 400"


def test_ui_has_a_way_to_open_the_log():
    assert "data-log=" in UI_SRC, "у рядку деплою немає кнопки логу"
    assert "showDeployLog" in UI_SRC
    assert 'id="logModal"' in UI_SRC, "лог нікуди показувати"
    # у бічній колонці 230px лог нечитний — тому саме модалка, як у сусідів
    assert re.search(r'id="logModal" class="ovl"', UI_SRC), UI_SRC[:0]


def test_empty_log_says_what_it_means():
    """Порожній лог — це не «нічого не знайшли», а відповідь: помилки php
    немає, отже сторінка порожня з іншої причини (напр. $isDev або сама
    логіка вайта). Мовчазна відповідь тут повертала б нас на початок."""
    body = UI_SRC[UI_SRC.index("async function showDeployLog"):]
    body = body[:body.index("\n}")]
    assert "$isDev" in body, body


# ------------------------------------------------- тека з іменем *.php

def test_php_patch_pass_skips_directories_named_like_php():
    """Скрейпи тягнуть чужі асети разом зі шляхами, і серед них трапляється
    ТЕКА з іменем на `.php` — у macgowuiqbg це
    `_external/static.xx.fbcdn.net/images/emoji.php/v9`. Прохід патчингу
    `$isDev` ходить по `rglob('*.php')`, і без перевірки на файл падав на
    такій теці з PermissionError, роблячи вітку недеплойною взагалі."""
    import pathlib
    import tempfile

    d = pathlib.Path(tempfile.mkdtemp(prefix="qa_lab-phpdir-"))
    (d / "emoji.php").mkdir()                    # тека, не файл
    (d / "emoji.php" / "v9").write_text("x", encoding="utf-8")
    (d / "index.php").write_text("<?php $isDev = false; ?>", encoding="utf-8")

    patched = 0
    for php in d.rglob("*.php"):                 # та сама механіка, що в _deploy_php
        if not php.is_file():
            continue
        text = php.read_text(encoding="utf-8", errors="replace")
        new = deployer.ISDEV_RX.sub("$isDev = true", text)
        if new != text:
            php.write_text(new, encoding="utf-8")
            patched += 1
    assert patched == 1, patched

    # і головне: сам деплоєр теж мусить мати цю гарду
    body = DEPLOYER_SRC[DEPLOYER_SRC.index("def _deploy_php"):]
    body = body[:body.index("return _serve")]
    loop = body[body.index('rglob("*.php")'):]
    # гарда стоїть одразу в тілі циклу — до першого читання файла
    assert "is_file()" in loop[:loop.index("php.read_text(")], loop[:400]


if __name__ == "__main__":
    run(dict(globals()))
