"""Мульти-проєктність: реєстр GitLab-проєктів + активний проєкт.

Кожен проєкт має:
  * власний GitLab-клієнт (свій project path + токен);
  * тип деплою: "php" (білі сторінки — віддаємо як є) або
    "node" (Nuxt/Next-вайти — npm install + npm run generate → віддаємо dist/);
  * власний простір стану: white-pages для сумісності живе у корені
    (cache/, branches.json, ...), решта — у projects/<id>/.

Активний проєкт — у КОЖНОЇ людини свій: поле `project` її запису, яке
auth-middleware кладе на кожен запит (`bind_request`). `active_project.json`
лишився дефолтом процесу — для людини, яка ще нічого не обирала, і для фонової
роботи (вебхук, черга, ШІ-міст), у якої людини немає.
"""

from __future__ import annotations

import contextvars
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from gitlab_client import GitLabClient, MockClient

def state_root() -> Path:
    """Корінь, під яким живе ВЕСЬ стан лаби (кеші, деплої, json-и, реєстри).

    Дефолт "." — тобто стан лежить поруч з кодом, як і завжди: нативний
    запуск не змінюється ні на йоту. QA_LAB_STATE_DIR потрібен там, де код
    незмінний, а стан має пережити перезапуск — у контейнері він вказує на
    змонтований volume.

    Єдине джерело для розкладки стану: решта модулів беруть шляхи звідси,
    щоб не було двох різних уявлень про те, де він лежить.
    """
    return Path(os.getenv("QA_LAB_STATE_DIR", "."))


ACTIVE_FILE = state_root() / "active_project.json"

_registry: dict[str, dict] = {}
_clients: dict[str, object] = {}
_current: str = "white-pages"

# Проєкт «на цей потік», що перекриває глобальний активний.
#
# Потрібен фоновій роботі, яка ходить по ОБОХ проєктах (годинний автофікс:
# 240 з 315 віток лежать у node-репо). Перемикати заради цього глобал не
# можна двічі: він видимий людині в UI — вона побачила б, що проєкт
# змінився сам, — і його читають паралельні HTTP-виклики, тобто чужий запит
# отримав би чужий кеш. Це той самий ідіом, яким їде актор підпису
# (`attribution._actor`).
#
# З 21.09.2026 цим самим механізмом їде й проєкт ЛЮДИНИ (`bind_request`):
# доти вибір php/vue був глобальним, і перемикання в одного перемикало всіх —
# наступний Sync/Apply колеги йшов у чужий проєкт.
#
# ⚠️ ContextVar НЕ переїжджає у потоки сам. Пул і потік, запущені з запиту,
# мусять іти через `Pool` і `thread()` нижче — інакше робота всередині них
# тихо повертається на дефолт процесу, тобто в чужий проєкт.
_override: ContextVar[str | None] = ContextVar("qa_lab_project", default=None)


@contextmanager
def use(pid: str):
    """Тимчасово зробити `pid` активним ДЛЯ ЦЬОГО потоку.

    Дефолт процесу і `active_project.json` не чіпаються — на відміну від
    `set_current()`.
    """
    if pid not in _registry:
        raise ValueError(f"невідомий проєкт: {pid}")
    token = _override.set(pid)
    try:
        yield
    finally:
        _override.reset(token)


def bind_request(pid: str | None) -> None:
    """Проєкт людини — на весь поточний запит.

    Кличе auth-middleware, коли вже знає, хто прийшов. Без `reset`, бо
    контекст запиту живе рівно стільки, скільки запит: кожен запит uvicorn
    обробляє в окремій задачі з власною копією контексту, тож вибір однієї
    людини в сусідній запит не протікає (так само їде актор підпису).

    Невідомий або порожній `pid` — не помилка, а «вибору немає»: проєкт,
    збережений у записі, могли прибрати з реєстру (вимкнули `VUE_GITLAB_*`),
    і людина мусить потрапити в дефолт, а не в 500.
    """
    _override.set(pid if pid in _registry else None)


class Pool(ThreadPoolExecutor):
    """`ThreadPoolExecutor`, який везе в кожне завдання контекст того, хто його
    подав: проєкт людини і актора підпису.

    Навіщо. Ендпоінти ганяють вітки пачками в потоках (`sync_multi`,
    `run_checks`, прев'ю фіксів…), а голий пул стартує кожне завдання з
    ПОРОЖНІМ контекстом — тобто в дефолтному проєкті процесу. Поки проєкт був
    глобальним, це збігалось; з проєктом на людину пачка vue-віток синкалась
    би в php-кеш.

    Контекст копіюється на КОЖНЕ завдання окремо: один `Context` не можна
    увійти з двох потоків одночасно (`RuntimeError`), а `map()` подає всі
    завдання з потоку викликача — тобто копія береться саме там, де треба.
    """

    def submit(self, fn, /, *args, **kwargs):
        return super().submit(contextvars.copy_context().run, fn, *args, **kwargs)


def thread(target, *args, name: str | None = None,
           daemon: bool = True) -> threading.Thread:
    """Запустити потік у копії контексту викликача (проєкт + актор).

    Для довгих фонових потоків, які стартують із запиту: live-sync деплою і
    фоновий nuxt-білд. Без цього вотчер vue-деплою дивився б у php-знімок з
    тією самою назвою вітки."""
    ctx = contextvars.copy_context()
    t = threading.Thread(target=ctx.run, args=(target, *args),
                         name=name, daemon=daemon)
    t.start()
    return t


def _env(k: str, d: str = "") -> str:
    return os.getenv(k, d).strip()


def init():
    """Будує реєстр з .env. Викликається один раз при старті app.py."""
    global _registry, _current
    _registry = {}

    tok = _env("GITLAB_TOKEN")
    mock = not tok or os.getenv("MOCK_MODE") == "1"
    _registry["white-pages"] = {
        "id": "white-pages", "title": "White-Pages (php)", "type": "php",
        "gitlab_path": _env("GITLAB_PROJECT", "development/white-pages"),
        "token": tok, "mock": mock,
        # історичне розташування стану — у корені (за замовчуванням "." )
        "root": state_root(),
    }

    vproj, vtok = _env("VUE_GITLAB_PROJECT"), _env("VUE_GITLAB_TOKEN")
    if vproj and vtok:
        _registry["vue"] = {
            "id": "vue", "title": "Node-вайти (Nuxt/Next)", "type": "node",
            "gitlab_path": vproj, "token": vtok, "mock": False,
            "root": state_root() / "projects" / "vue",
        }

    _current = "white-pages"
    if ACTIVE_FILE.exists():
        try:
            saved = json.loads(ACTIVE_FILE.read_text(encoding="utf-8")).get("id")
            if saved in _registry:
                _current = saved
        except Exception:
            pass


def list_projects() -> list[dict]:
    return [{"id": p["id"], "title": p["title"], "type": p["type"],
             "gitlab_path": p["gitlab_path"], "mock": p["mock"]}
            for p in _registry.values()]


def all_state_dirs() -> list[dict]:
    """[{id, title, root}] усіх проєктів — для крос-проєктної статистики,
    що читає commits_log.json/clickup_map.json кожної теки стану."""
    return [{"id": p["id"], "title": p["title"], "root": p["root"]}
            for p in _registry.values()]


def current() -> dict:
    return _registry[current_id()]


def current_id() -> str:
    """Активний проєкт: накладка (вибір людини на цей запит або
    `use()` фонової роботи), а якщо її немає — дефолт процесу."""
    return _override.get() or _current


def set_current(pid: str):
    """Змінити ДЕФОЛТ процесу. Не для кнопки в UI: людина свій вибір пише в
    запис користувача (`/api/project`), інакше перемикала б усіх."""
    global _current
    if pid not in _registry:
        raise ValueError(f"невідомий проєкт: {pid}")
    _current = pid
    ACTIVE_FILE.write_text(json.dumps({"id": pid}), encoding="utf-8")


def has(pid: str) -> bool:
    """Чи налаштований проєкт (vue існує лише коли задані VUE_GITLAB_*)."""
    return pid in _registry


def client_for(pid: str):
    """GitLab-клієнт КОНКРЕТНОГО проєкту, без перемикання активного.

    Потрібен там, де один запит працює одразу з двома проєктами (імпорт
    з ClickUp: вітки, яких немає у php-репо, шукаються у node-репо).
    Через set_current цього робити НЕ можна: активний проєкт глобальний,
    а запити ходять у GitLab пулом потоків — перемикання зіпсувало б
    паралельні виклики й лишило б лабу в чужому проєкті після винятку.
    """
    p = _registry[pid]
    if pid not in _clients:
        gate = p.get("type") == "php"      # commit_gate: лише php-деплой має placeholders_sed
        if p["mock"]:
            _clients[pid] = MockClient(gate=gate)
        else:
            _clients[pid] = GitLabClient(
                _env("GITLAB_URL", "https://gitlab.example.com"),
                p["gitlab_path"], p["token"], gate=gate)
    return _clients[pid]


def client():
    """GitLab-клієнт активного проєкту (кешується)."""
    return client_for(current_id())


def is_mock() -> bool:
    return current()["mock"]


def ptype() -> str:
    return current()["type"]


def state_dir_for(pid: str) -> Path:
    d = _registry[pid]["root"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_dir() -> Path:
    return state_dir_for(current_id())


def state_file_for(pid: str, name: str) -> Path:
    """Файл стану чужого проєкту — пара до client_for (та сама причина)."""
    return state_dir_for(pid) / name


def state_file(name: str) -> Path:
    return state_dir() / name


# Стан, який належить не проєкту, а ВОРКСПЕЙСУ ClickUp: скан тасок один і той
# самий для php- і vue-вайтів, бо `clickup_client.fetch_all()` не знає про
# проєкти взагалі - він читає той самий токен і те саме вʼю. Доки такі файли
# лежали в теці проєкту, перемикання проєкту показувало ІНШИЙ скан і змушувало
# парсити ClickUp заново: заміряно 460 тасок (13:18) у white-pages проти 401
# (14:48) у vue, причому vue-скан - строга підмножина. Тому вони живуть у
# корені, як уже живе `stats_clickup_cache.json`.
def shared_file(name: str) -> Path:
    """Файл стану рівня воркспейсу - спільний для всіх проєктів.

    Від КОРЕНЯ СТАНУ, а не від поточної теки. Різниця видна лише в проді і
    там вона фатальна: корінь стану - том `qa_lab-state`, а CWD контейнера -
    `/app`, тобто скан ClickUp і теми коментарів лягали б у шар образу і
    зникали з кожним оновленням. Це та сама вада, що була у `photo_db.json`
    (гарда - `test_state_root.py`).
    """
    return state_root() / name


def resolve_in(cl, name: str) -> dict:
    """`branch()` з фолбеком регістру для ВКАЗАНОГО клієнта.

    GitLab чутливий до регістру, а назви приходять з ClickUp як їх набрала
    людина (`AUTO_...` при вітці `auto_...`). Живе тут, а не в `app`, бо
    машинним споживачам (черга ClickUp) `app` імпортувати не можна.
    """
    try:
        return cl.branch(name)
    except Exception as first:
        low = name.lower()
        if low == name:
            raise
        try:
            return cl.branch(low)
        except Exception:
            raise first


def locate_branch(name: str) -> dict | None:
    """У ЯКОМУ проєкті лежить вітка: {"pid", "name", "info"} або None.

    Таска ClickUp не каже, якого типу вайт, і vue-вайти регулярно заводять у
    php-проєкт (заміряно: 20 з 20 проблемних віток журналу лежали в
    `development/new-white-front`). Тому шукаємо по черзі в усіх проєктах, у
    порядку реєстру — php, далі node.

    Це серверний двійник того, що робить `_adopt_into_node` для ручного
    імпорту: там результат кладеться у списки віток, тут — у чергу.
    """
    for pid in _registry:
        try:
            info = resolve_in(client_for(pid), name)
        except Exception:
            continue
        return {"pid": pid, "name": info.get("name") or name, "info": info}
    return None


def project_copies(name: str) -> list[Path]:
    """Проєктні копії того самого файла - для одноразового переїзду у спільний.
    Корінь пропускаємо: він і є спільним місцем."""
    shared = shared_file(name).resolve()
    out = []
    for p in _registry.values():
        f = p["root"] / name
        if f.exists() and f.resolve() != shared:
            out.append(f)
    return out


class ClientProxy:
    """Дозволяє тримати в app.py звичну змінну `client`, яка завжди
    делегує до клієнта АКТИВНОГО проєкту."""

    def __getattr__(self, name):
        return getattr(client(), name)
