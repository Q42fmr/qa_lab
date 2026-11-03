"""Перемикання проєкту мусить перемальовувати ВСЕ, що project-scoped.

Стан лаби розділений по проєктах: `cache/`, `deploy/`, `visual/` кожного
живуть під `projects.state_dir()`, а `deployer.list_deploys()` ще й фільтрує
по `projects.current_id()`. Тобто після зміни проєкту КОЖНА панель, що читає
такий ендпоінт, показує чужі дані, поки її не перечитають.

Кейс 25.08: обробник перемикання кликав `loadBranches()` і `loadStorage()`,
але не `loadArchive()` — і в лівій колонці поруч стояли «Кеш: 0 КБ (0 віток)»
свіжого node-проєкту і «Архів (49)» від попереднього. Виглядало як зламані
цифри і двічі збивало з пантелику при розборі інших скарг.

Тест текстовий (як `test_ci_lockstep`): свого раннера для JS у проєкті немає,
а нової залежності заради цього не заводимо. Ловить саме регресію «додали
панель / забули перечитати».
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

UI = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
DEPLOYER = (ROOT / "deployer.py").read_text(encoding="utf-8")

# Обробник `$('#projSel').onchange` — від нього до кінця функції.
_HANDLER_RX = re.compile(r"\$\('#projSel'\)\.onchange\s*=\s*async\(\)=>\{(.*?)\n\};", re.S)

# Завантажувачі лівої колонки і чим саме вони project-scoped на бекенді.
SCOPED_LOADERS = {
    "loadBranches": "/api/branches — список віток проєкту",
    "loadStorage": "/api/storage — cache/deploy/screens активного проєкту",
    "loadArchive": "/api/archive — знімки в cache/ активного проєкту",
    "loadDeploys": "/api/deploys — list_deploys() фільтрує по current_id()",
}

# Кеші результатів у пам'яті сторінки: їх мало перечитати — їх треба СКИНУТИ,
# інакше до наступного кліку по підвкладці видно прогони чужого проєкту.
SCOPED_CACHES = ("lhResults", "visResults")


def _handler() -> str:
    m = _HANDLER_RX.search(UI)
    assert m, "не знайшов обробник $('#projSel').onchange — тест застарів"
    return m.group(1)


# ------------------------------------------------- передумова тесту

def test_the_backend_really_is_project_scoped():
    """Якщо це перестане бути правдою, тест нижче втрачає сенс — і має впасти
    саме тут, з поясненням, а не мовчки перетворитись на формальність."""
    assert "runner.cache_root()" in APP, "/api/archive більше не читає cache проєкту"
    assert 'prefix = f"{projects.current_id()}::"' in DEPLOYER, \
        "list_deploys() більше не фільтрує по активному проєкту"


# ------------------------------------------------- сам контракт

def test_switch_reloads_every_project_scoped_panel():
    body = _handler()
    missing = [f"{fn}() — {why}" for fn, why in SCOPED_LOADERS.items()
               if f"{fn}()" not in body]
    assert not missing, ("перемикання проєкту не перечитує: " + "; ".join(missing))


def test_switch_resets_in_memory_result_caches():
    body = _handler()
    missing = [c for c in SCOPED_CACHES if not re.search(rf"\b{c}\s*=\s*\[\]", body)]
    assert not missing, f"не скидаються після перемикання проєкту: {missing}"


def test_every_scoped_loader_actually_exists():
    """Зворотний бік: назва в таблиці мусить бути справжньою функцією UI."""
    missing = [fn for fn in SCOPED_LOADERS
               if not re.search(rf"(async\s+)?function\s+{fn}\s*\(", UI)]
    assert not missing, f"у static/index.html немає таких функцій: {missing}"


if __name__ == "__main__":
    run(dict(globals()))
