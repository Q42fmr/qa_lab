"""Lockstep «код шеліться в бінарник» ⇄ `docker/Dockerfile`.

Навіщо цей тест. Лаба ПОРОДЖУЄ ПРОЦЕСИ: `php -S` на кожну вітку, chromium
під CDP, node під Lighthouse, npm під білд node-вайтів. Кожен такий виклик
іде через `os.getenv("<ЩОСЬ>_BIN", ...)` — і якщо бінарника в образі немає,
падає воно НЕ там, де видно. Кейс 25.08: у образі не було npm, і на вітках
`nwf-*` мовчки лягли ОДРАЗУ ЧОТИРИ вкладки — Deploy, Скріни, Візуальні,
Lighthouse (усі троє кличуть `deployer.deploy(wait=True)`, а той першою дією
йде в npm). У UI це виглядало як `[Errno 2] No such file or directory: 'npm'`
одним тостом, що зникає, — і як «візуальний тест просто не працює».

Тому список «у що ми шелимося» береться З КОДУ, а не з голови: новий
`FOO_BIN` у будь-якому модулі провалить тест, поки про нього не ухвалять
рішення — покласти в образ чи явно записати в десктопні.

Тест ГЕРМЕТИЧНИЙ: читає тексти файлів, нічого не запускає і не вимагає,
щоб бінарники були на машині розробника (нативний Windows-запуск лаби —
теж легальний сценарій, і там частина цього стоїть в інших місцях).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

DOCKERFILE = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
ENTRYPOINT = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")

# Коментарі геть: у шапці Dockerfile ті самі назви трапляються як пояснення,
# і без цього кроку «згадали в коментарі» читалось би як «поклали в образ».
DF_CODE = "\n".join(l for l in DOCKERFILE.splitlines()
                    if not l.lstrip().startswith("#"))

# Рантайми, які сервер запускає САМ, і без яких вкладка лягає.
# Значення — чим саме бінарник потрапляє в образ (підрядок рядка Dockerfile).
SERVER_RUNTIMES = {
    "PHP_BIN": "php-cli",                              # apt: `php -S` на вітку
    "BROWSER_BIN": "chromium",                         # apt: CDP-скріни і візуальні
    "NODE_BIN": "/usr/local/bin/node",                 # COPY з lhdeps: Lighthouse
    "NPM_BIN": "/usr/local/lib/node_modules/npm",      # COPY з lhdeps: білд node-вайтів
}

# Свідомо НЕ в образі: це десктопні зручності «відкрити теку в IDE» з
# app.py — вони мають сенс лише на машині розробника, у контейнері їх нема
# кому показати. Запис тут = ухвалене рішення, а не забутий бінарник.
DESKTOP_ONLY = {"PHPSTORM_BIN", "VSCODE_BIN"}

_BIN_RX = re.compile(r'os\.getenv\(\s*["\']([A-Z][A-Z0-9_]*_BIN)["\']')


def _bins_used_in_code() -> dict[str, list[str]]:
    """{ім'я змінної: [файли, де шеляться]} по всьому коду лаби, крім тестів."""
    out: dict[str, list[str]] = {}
    for py in sorted(ROOT.glob("*.py")):
        for name in set(_BIN_RX.findall(py.read_text(encoding="utf-8"))):
            out.setdefault(name, []).append(py.name)
    return out


# ------------------------------------------------- код ⇄ образ

def test_every_server_binary_is_declared_in_the_image_env():
    """`ENV ..._BIN=` в образі — щоб шлях був явним, а не «як пощастить у PATH».

    Той самий патерн, що вже стоїть для PHP_BIN/BROWSER_BIN/NODE_BIN.
    """
    # перший у блоці стоїть як `ENV NAME=`, решта — продовженням рядка
    missing = [n for n in SERVER_RUNTIMES
               if not re.search(rf"^\s*(?:ENV\s+)?{n}=", DF_CODE, re.M)]
    assert not missing, f"у Dockerfile немає ENV для: {sorted(missing)}"


def test_every_server_binary_is_actually_put_into_the_image():
    """ENV мало оголосити — треба ще й покласти файл.

    Саме тут ловиться кейс 25.08: NPM_BIN можна було б оголосити, а npm у
    образі не мати, і падало б рівно так само.
    """
    missing = [n for n, marker in SERVER_RUNTIMES.items() if marker not in DF_CODE]
    assert not missing, f"оголошено, але не покладено в образ: {sorted(missing)}"


def test_no_unclassified_binary_appears_in_the_code():
    """Новий шелл-аут або кладеться в образ, або явно визнається десктопним."""
    known = set(SERVER_RUNTIMES) | DESKTOP_ONLY
    used = _bins_used_in_code()
    unknown = {n: v for n, v in used.items() if n not in known}
    assert not unknown, (
        "у коді з'явився новий бінарник — вирішіть, чи їде він у образ, і "
        f"допишіть його в SERVER_RUNTIMES або DESKTOP_ONLY: {unknown}")


def test_server_runtimes_are_really_used_by_the_code():
    """Зворотний бік: рантайм, якого код більше не кличе, — зайві МБ у образі."""
    used = set(_bins_used_in_code())
    orphans = sorted(set(SERVER_RUNTIMES) - used)
    assert not orphans, f"образ несе бінарник, якого код не кличе: {orphans}"


# ------------------------------------------------- npm: симлінк і кеш

def test_npm_symlink_is_created_not_copied():
    """В офіційному образі node `/usr/local/bin/npm` — ВІДНОСНИЙ симлінк.

    Скопіювати його недостатньо: посилання переїхало б раніше за теку, на
    яку вказує, і `npm` був би битим. Тому теку копіюємо, а лінк робимо самі.
    """
    assert "ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm" in DF_CODE, \
        "npm має отримувати симлінк через `ln -s`, а не COPY"


def test_npm_cache_lives_in_the_state_dir():
    """Дефолтний кеш npm (/root/.npm) — це шар контейнера, тобто він зникає
    при кожному оновленні сервісу, і перший білд після редеплою качав би всі
    пакети наново. Том переживає редеплой."""
    assert "npm_config_cache" in ENTRYPOINT, "entrypoint не переносить кеш npm"
    assert re.search(r'npm_config_cache="\$STATE_DIR', ENTRYPOINT), \
        "кеш npm має лежати під $STATE_DIR (том), а не в шарі контейнера"


def test_boot_diagnostics_report_npm():
    """Рядок версій у логу старту — найдешевший спосіб побачити, що рантайму
    немає. Коли npm бракувало, його відсутність не було видно НІДЕ."""
    assert "NPM_BIN:-npm" in ENTRYPOINT, \
        "у діагностичному рядку entrypoint немає npm"


if __name__ == "__main__":
    run(dict(globals()))
