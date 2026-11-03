"""Branch snapshots and the pluggable check runner.

Snapshot = full copy of one branch pulled into cache/<branch>/.
Checks   = python modules in ./checks/. Each module defines:

    NAME        = "Human readable name"
    DESCRIPTION = "What it verifies"
    FILES       = ["*.html", "*.php"]        # fnmatch patterns, matched on full path
    GROUP       = "tests"                    # "auto" | "tests" | "review";
                                             # default: "auto" if the check has fix/fix_delete, else "tests"
    PROJECTS    = ["php"]                    # типи проєктів, де перевірка діє:
                                             # "php" (white-pages) | "node" (Nuxt/Next);
                                             # без атрибута — діє скрізь
    def run(path: str, text: str) -> list[dict]:
        # return issues: {"line": int|None, "message": str, "severity": "error"|"warn"|"info"}

    # OR, for checks that need to see the whole branch at once:
    def run_branch(files: dict[str, str]) -> list[dict]:
    def run_branch(files, all_paths: list[str]) -> list[dict]:
    def run_branch(files, all_paths, branch: str) -> list[dict]:
        # files     = {path: text} (only files matching FILES)
        # all_paths = усі файли вітки, включно з бінарниками
        # branch    = назва вітки (для читання знімка / домену з domains.py)
        # return issues: {"path": str, "line": int|None, "message": str, "severity": ...}

    # Автофікси. fix()/fix_delete() — пофайлові; fix_branch() бачить усю вітку
    # і вміє створювати нові файли:
    def fix(path: str, text: str) -> str: ...
    def fix_delete(all_paths: list[str]) -> list[str]: ...
    def fix_branch(files, all_paths, branch) -> list[dict]:
        # [{"type": "edit"|"create"|"delete", "path": str, "content": str}]
        # виконується ПОВЕРХ fix(): у files уже виправлений текст

Drop a new .py file into checks/ and it appears in the UI after "Reload checks".
"""

from __future__ import annotations

import fnmatch
import importlib.util
import inspect
import json
import os
import secrets
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path

CHECKS_DIR = Path("checks")

# Один прогін конвеєра на процес.
#
# Машинних споживачів конвеєра тепер двоє — ШІ-міст (заявка від TSM) і
# годинний автофікс, — а `projects` та знімки в `cache/` спільні. Лок живе
# тут, а не в котромусь із них, бо обидва вже імпортують `runner`, і
# другий лок означав би, що вони не бачать один одного.
#
# Береться ПО ОДНІЙ ВІТЦІ, а не на весь прохід: інакше заявка від TSM чекала
# б, поки автофікс перебере всі 315 віток. Ціна черговості — секунди.
pipeline_lock = threading.Lock()


def cache_root() -> Path:
    """cache/ активного проєкту (white-pages — історично у корені)."""
    import projects
    return projects.state_dir() / "cache"

TEXT_EXT = {
    ".html", ".htm", ".php", ".css", ".js", ".json", ".txt", ".xml", ".md",
    ".env", ".yml", ".yaml", ".svg", ".ini", ".conf", ".sh", ".sql",
    # node-вайти (Nuxt/Vue, Next/React): без цих розширень пошук/заміни/перевірки
    # мовчки пропускали основні файли проєкту
    ".vue", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".scss", ".sass", ".less",
}


def is_text(path: str) -> bool:
    p = Path(path)
    return p.suffix.lower() in TEXT_EXT or p.name.startswith(".env")


# --------------------------------------------------------------------------
# snapshots
# --------------------------------------------------------------------------

def _folder_name(branch: str) -> str:
    """Назва теки знімка — мусить бути ОДНОЗНАЧНОЮ, інакше це тихе псування.

    Дві пастки:
    * Windows не розрізняє регістр, а рефи git — розрізняють. `OURSV_br-x` і
      `oursv_br-x` у GitLab це різні вітки, а тека виходила одна: сервіс
      показував чужий вміст і вважав вітку синхронізованою (реальний інцидент);
    * фолдинг `/`→`__` зливає `feat/x` і `feat__x`.

    Тому пряме ім'я лишається тільки для назв, які вже однозначні — нижній
    регістр і без слешів. Це весь наявний кеш, тож ре-синку не буде. Решта
    отримує суфікс від хеша ТОЧНОЇ назви: різні вітки — різні теки, та сама
    вітка — завжди та сама тека. Розділювач `~` у назвах гілок git заборонений
    (`git check-ref-format`), тож зіткнутися з реальним іменем не може.
    """
    flat = branch.replace("\\", "/")
    if flat == branch and branch == branch.lower() and "/" not in branch:
        return branch.strip()
    import hashlib
    tag = hashlib.sha1(branch.encode("utf-8")).hexdigest()[:8]
    return f"{flat.replace('/', '__').strip()}~{tag}"


def snapshot_dir(branch: str) -> Path:
    # Anything else — "..", "\", absolute paths — must NOT escape CACHE:
    # the branch name comes from HTTP params and is used to build read/write
    # paths, so a traversal here is arbitrary file read/write.
    safe = _folder_name(branch)
    base = cache_root().resolve()
    p = (base / safe).resolve()
    if branch.strip() in ("", ".", "..") or (p != base and base not in p.parents):
        raise ValueError(f"bad branch name: {branch!r}")
    return p


# Лок на знімок ОДНІЄЇ вітки (задача 21.09.2026 — люди не заважають одне
# одному). Доти ручні прогони не брали жодного локу: двоє синкали ту саму
# вітку одночасно (`rmtree` одного посеред розпаковки іншого), а прогін чеків
# колеги читав знімок, який саме перезаливався, — і рахував «чисто» по
# половині файлів. Лок — на пару (проєкт, тека знімка), тож різні вітки
# йдуть паралельно, як і раніше. RLock, бо конвеєр кличе sync → прогін →
# фікси в одному потоці вкладено.
#
# `pipeline_lock` вище лишився: він про ЧЕРГОВІСТЬ машинних споживачів (міст і
# черга не ганяють два конвеєри разом), а цілісність знімка тепер тримає цей.
_branch_locks: dict[tuple, threading.RLock] = {}
_branch_locks_guard = threading.Lock()


def branch_lock(branch: str) -> threading.RLock:
    import projects
    key = (projects.current_id(), _folder_name(branch))
    with _branch_locks_guard:
        lock = _branch_locks.get(key)
        if lock is None:
            lock = _branch_locks[key] = threading.RLock()
        return lock


from contextlib import contextmanager


@contextmanager
def _locked(branch: str, timeout: int = 150):
    """branch_lock з дедлайном: вітку може тримати інший прогін/sync/деплой,
    і БЕЗ таймаута другий клік висів би вічно і мовчки (кейс 02.10:
    «виконую перевірки 0%» назавжди)."""
    lock = branch_lock(branch)
    if not lock.acquire(timeout=timeout):
        raise RuntimeError(
            f"вітка «{branch}» зайнята іншою операцією (sync/прогін/деплой/"
            f"черга) — не дочекався {timeout}с; спробуй ще раз за хвилину")
    try:
        yield
    finally:
        lock.release()


def _progress_path(branch: str) -> Path:
    import projects
    d = projects.state_root() / "checks_progress"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{projects.current_id()}__{_folder_name(branch)}.txt"


def _progress_note(branch: str, text: str) -> None:
    """Маяк «що саме зараз рахується»: при завислому воркері це єдине
    місце, звідки видно ІМ'Я чека."""
    try:
        if text:
            _progress_path(branch).write_text(text, encoding="utf-8")
        else:
            _progress_path(branch).unlink(missing_ok=True)
    except Exception:
        pass


def _progress_read(branch: str) -> str:
    try:
        return _progress_path(branch).read_text(encoding="utf-8").strip()
    except Exception:
        return ""


class UnsavedEdits(ValueError):
    """У знімку є правки людини, яких немає в git, а sync мав би їх стерти."""


def is_synced(branch: str) -> bool:
    """Знімок є, НЕ порожній І належить саме цій вітці.

    `snapshot_dir(...).exists()` для цього не годиться: на Windows тека
    вітки-двійника за регістром відповідає True, тож вітка, яку ніколи не
    синхронізували, виглядала синхронізованою — з чужим вмістом, з якого
    рахувались чеки й фікси.

    Порожня тека — теж не знімок. `sync_branch` створює теку ДО
    завантаження, а `.snapshot.json` пише ОСТАННІМ, тож обірваний синк
    лишає порожній каталог. Без цієї умови він проходив як «легасі-знімок
    без метаданих»: вітка ніколи не пересинхронізовувалась, чеки бачили
    нуль файлів і рапортували «чисто» (у node-кеші так стояли 152 вітки зі
    151 фальшиво-зеленим прогоном). Успішний синк завжди лишає щонайменше
    `.snapshot.json`, тож «жодного файлу» однозначно означає збій.

    Знімки без метаданих, але З файлами, вважаємо своїми: інакше оновлення
    коду означало б ре-синк усього кешу.
    """
    d = snapshot_dir(branch)
    if not d.exists():
        return False
    if not any(d.iterdir()):
        return False
    return snapshot_meta(branch).get("branch", branch) == branch


def _branch_404_hint(branch: str) -> str:
    """404 на архіві вітки: найчастіше це вітка ІНШОГО проєкту в цьому списку
    (nwf-* вайти живуть у new-white-front, а їх додали у список white-pages).
    Пробуємо знайти вітку в решті проєктів і кажемо людині, куди перемкнутись,
    замість сирого «404 Client Error … archive.zip»."""
    import projects
    cur = projects.current()
    homes = []
    for info in projects.list_projects():
        if info["id"] == cur["id"]:
            continue
        try:
            projects.client_for(info["id"]).branch(branch)
            homes.append(info["title"])
        except Exception:
            continue
    hint = (f" — вона є у проєкті «{homes[0]}»: перемкни проєкт у шапці"
            if homes else "")
    return f"вітки «{branch}» немає у проєкті «{cur['title']}»{hint}"


def sync_branch(client, branch: str, force: bool = False) -> dict:
    """Download a full copy of the branch into the local cache.

    * якщо commit вітки не змінився з минулого синхрону — нічого не качаємо
      (обійти можна force=True);
    * якщо клієнт вміє archive() — тягнемо всю вітку одним zip-запитом
      замість запиту на кожен файл;
    * знімок підміняється ЦІЛКОМ: нова копія розпаковується поруч і стає на
      місце одним перейменуванням. Читач ніколи не бачить пів знімка, а
      обірване завантаження лишає старий знімок живим — доти `rmtree` ішов
      ПЕРЕД завантаженням і лишав порожню теку (див. `is_synced`);
    * правок людини, яких немає в git, sync мовчки НЕ стирає: коміт вітки
      змінився, а у знімку є додані чи змінені файли проти базового коміту —
      `UnsavedEdits` (обійти — force=True). Доти чужий Sync після нового
      коміту прибирав залиті колегою файли, і сліду не лишалось ніде.
    """
    with _locked(branch):
        return _sync_locked(client, branch, force)


def _staging_root() -> Path:
    """Тека для нових знімків: на тій самій ФС, що й cache/ (підміна — один
    rename), і ПОЗА cache/, щоб напівготова копія не з'являлась в «Архіві» і
    не потрапляла під «🧹 архів»."""
    return cache_root().parent / ".sync-staging"


def _unsaved_edits(client, branch: str, base: str) -> list[str]:
    """Додані й змінені файли знімка проти дерева базового коміту.

    Видалених не рахуємо: архів GitLab не віддає файлів з export-ignore, і
    вони «зникали» б у кожному знімку — sync не проходив би ніколи. Коли
    дерево дістати не вдалось, не блокуємо: невідомість — не привід зупиняти
    роботу, так sync і поводився досі."""
    if not base or not hasattr(client, "tree_blobs") or not is_synced(branch):
        return []
    try:
        got = local_changes(branch, client.tree_blobs(base))
    except Exception:
        return []
    return got["added"] + got["modified"]


def _swap_in(fresh: Path, dest: Path) -> None:
    """Поставити нову копію знімка на місце старої."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    old = None
    if dest.exists():
        old = fresh.with_name(fresh.name + ".old")
        try:
            os.rename(dest, old)
        except OSError:
            # Windows не перейменовує теку з відкритим файлом — тоді як
            # раніше: прибрати і поставити.
            shutil.rmtree(dest, ignore_errors=True)
            old = None
    os.rename(fresh, dest)
    if old is not None:
        shutil.rmtree(old, ignore_errors=True)


def _sync_locked(client, branch: str, force: bool) -> dict:
    dest = snapshot_dir(branch)
    meta_path = dest / ".snapshot.json"

    commit = None
    if hasattr(client, "branch"):
        try:
            commit = client.branch(branch)["commit"]
        except Exception:
            pass                    # хай впаде нижче зі зрозумілою помилкою

    old: dict = {}
    if meta_path.exists():
        try:
            old = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            old = {}

    if not force and commit and meta_path.exists():
        # Звіряємо не лише коміт, а й ВІТКУ: раніше чужий знімок із тим самим
        # sha вважався актуальним, і вітка назавжди лишалась із чужим вмістом.
        if old.get("commit") == commit and old.get("branch", branch) == branch:
            old.setdefault("branch", branch)
            old["skipped"] = True   # знімок актуальний — качати нічого
            return old

    if not force and old.get("branch", branch) == branch:
        edits = _unsaved_edits(client, branch, str(old.get("commit") or ""))
        if edits:
            shown = ", ".join(edits[:3]) + (" …" if len(edits) > 3 else "")
            raise UnsavedEdits(
                f"у знімку є незакомічені правки ({shown}) — закоміть їх у "
                f"«Локальних змінах» або відкинь: Sync їх не стирає")

    staging = _staging_root()
    staging.mkdir(parents=True, exist_ok=True)
    fresh = staging / f"{dest.name}.{secrets.token_hex(4)}"
    fresh.mkdir()
    try:
        if hasattr(client, "archive"):
            import io
            import zipfile
            try:
                blob = client.archive(branch)
            except Exception as e:
                code = getattr(getattr(e, "response", None), "status_code", None)
                if code == 404:
                    raise ValueError(_branch_404_hint(branch)) from e
                raise
            n = 0
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for m in z.infolist():
                    if m.is_dir():
                        continue
                    # архів GitLab має кореневу папку "<project>-<sha>/" — зрізаємо
                    parts = m.filename.split("/", 1)
                    if len(parts) < 2 or not parts[1]:
                        continue
                    target = fresh / parts[1]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(m))
                    n += 1
            meta = {"branch": branch, "files": n, "commit": commit}
        else:
            paths = client.tree(branch)
            for p in paths:
                raw = client.file_raw(branch, p)
                target = fresh / p
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            meta = {"branch": branch, "files": len(paths), "commit": commit}
        (fresh / ".snapshot.json").write_text(json.dumps(meta), encoding="utf-8")
        _swap_in(fresh, dest)
    except BaseException:
        shutil.rmtree(fresh, ignore_errors=True)
        raise
    return meta


def git_blob_sha(data: bytes) -> str:
    """sha1 у форматі git-блоба — збігається з id блоба у GitLab tree API."""
    import hashlib
    h = hashlib.sha1()
    h.update(b"blob %d\x00" % len(data))
    h.update(data)
    return h.hexdigest()


def snapshot_meta(branch: str) -> dict:
    p = snapshot_dir(branch) / ".snapshot.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def set_snapshot_commit(branch: str, commit: str):
    """Пересуває базовий коміт знімка (після кожного коміту лаби), щоб
    «Локальні зміни» не показували вже закомічене як розбіжність."""
    d = snapshot_dir(branch)
    if not d.exists():
        return
    meta = snapshot_meta(branch)
    meta["commit"] = commit
    meta.setdefault("branch", branch)
    (d / ".snapshot.json").write_text(json.dumps(meta), encoding="utf-8")


def local_changes(branch: str, remote_blobs: dict) -> dict:
    """Порівнює диск (cache/<branch>) з git-деревом базового коміту.

    remote_blobs = {path: git blob sha} з tree_blobs(ref). Хеші локальних
    файлів рахуються тут — вміст із GitLab не тягнеться."""
    if not is_synced(branch):
        raise ValueError("вітка не синхронізована — спершу Sync")
    local = snapshot_files(branch)
    added, modified = [], []
    for p in local:
        if p not in remote_blobs:
            added.append(p)
        elif git_blob_sha(read_snapshot_file(branch, p)) != remote_blobs[p]:
            modified.append(p)
    deleted = [p for p in remote_blobs if p not in set(local)]
    return {"added": sorted(added), "modified": sorted(modified),
            "deleted": sorted(deleted)}


# `_meta/` — службова тека TSM-імпорту (manifest.json, check.json і
# `original/` — знімок донора до уніфікації). Сайт на неї не посилається, у
# деплой вона не йде як сторінки, але чеки й фікси її читали як частину вайта:
# на sokkoruuzosnacav (21.10) кожен фікс футера давав 61 файл замість 31, а
# logo_domain/link_target/media_integrity сипали знахідками з донорських копій.
META_DIR = "_meta/"


def snapshot_files(branch: str) -> list[str]:
    base = snapshot_dir(branch)
    if not base.exists():
        return []
    return sorted(
        rel for p in base.rglob("*")
        if p.is_file() and p.name != ".snapshot.json"
        for rel in (str(p.relative_to(base)).replace("\\", "/"),)
        if not rel.startswith(META_DIR)
    )


def read_snapshot_file(branch: str, path: str) -> bytes:
    return (snapshot_dir(branch) / path).read_bytes()


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

VALID_PTYPES = ("php", "node")


def _check_projects(mod) -> list[str]:
    """Типи проєктів, де діє перевірка. Без PROJECTS (або з порожнім/кривим) —
    діє скрізь, щоб нова перевірка нікуди не зникала мовчки."""
    projs = getattr(mod, "PROJECTS", None)
    if isinstance(projs, str):
        projs = [projs]
    projs = [p for p in (projs or []) if p in VALID_PTYPES]
    return projs or list(VALID_PTYPES)


# Спільні бібліотеки, які чеки імпортують звичайним `import`: їхня правка
# теж мусить перезібрати каталог (див. `_load_checks_now`).
_SHARED_LIBS = ("menu_rules.py",)

_checks_cache: dict = {"key": None, "checks": None}
_checks_lock = threading.Lock()


def _checks_fingerprint() -> tuple:
    """(шлях, mtime, розмір) кожного чека і спільної бібліотеки."""
    out = []
    for f in [*sorted(CHECKS_DIR.glob("*.py")), *map(Path, _SHARED_LIBS)]:
        try:
            st = f.stat()
            out.append((str(f), st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((str(f), None, None))
    return tuple(out)


def load_checks() -> list[dict]:
    """Каталог чеків — перечитується, лише коли змінився якийсь файл.

    Доти кожен `checks/*.py` exec'ився заново на КОЖНУ вітку (65-160 мс, ×8
    потоків на пачку), і кожен такий виклик робив `importlib.reload` спільного
    `menu_rules`, поки в сусідніх потоках — у тому числі чужих прогонах —
    чеки виконували його ж функції: модуль, що саме перевиконується, міг
    віддати їм напівпорожній простір імен (задача 21.09.2026, «люди не
    заважають одне одному»). Правка на льоту працює як і раніше: збережений
    файл міняє mtime, і наступний прогін бере свіжий чек — без рестарту і
    без окремої кнопки.
    """
    key = _checks_fingerprint()
    with _checks_lock:
        if _checks_cache["key"] != key or _checks_cache["checks"] is None:
            _checks_cache["checks"] = _load_checks_now()
            _checks_cache["key"] = key
        return list(_checks_cache["checks"])


def _load_checks_now() -> list[dict]:
    # Кожен checks/*.py exec'иться заново нижче (без рестарту сервера
    # підхоплюються правки одразу) — але спільні бібліотеки типу
    # menu_rules, які чеки імпортують звичайним `import`, кешуються в
    # sys.modules на весь час життя процесу. Без явного reload тут чек, що
    # вже отримав нову функцію (наприклад check_drawer_on_desktop), падає з
    # AttributeError на застарілому menu_rules, поки сервер не перезапустять.
    if "menu_rules" in sys.modules:
        importlib.reload(sys.modules["menu_rules"])
    # те саме для чеків, які інші чеки імпортують звичайним `import
    # checks.form_stub` (php_scripts/forms/form_hijack… гейтяться по ньому):
    # після правки form_stub.py лаба кидала AttributeError на новій функції,
    # поки процес не перезапустять (21.10)
    for name in [n for n in list(sys.modules) if n.startswith("checks.") and sys.modules[n] is not None]:
        try:
            importlib.reload(sys.modules[name])
        except Exception:
            pass
    checks = []
    for f in sorted(CHECKS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"checks.{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            checks.append({
                "id": f.stem, "name": f.stem, "description": "FAILED TO LOAD",
                "files": [], "group": "tests", "projects": list(VALID_PTYPES),
                "error": traceback.format_exc(), "module": None,
            })
            continue
        fixable = (hasattr(mod, "fix") or hasattr(mod, "fix_delete")
                   or hasattr(mod, "fix_branch"))
        group = getattr(mod, "GROUP", None)
        if group not in ("auto", "tests", "review"):
            group = "auto" if fixable else "tests"
        checks.append({
            "id": f.stem,
            "name": getattr(mod, "NAME", f.stem),
            "description": getattr(mod, "DESCRIPTION", ""),
            "files": getattr(mod, "FILES", ["*"]),
            "fixable": fixable,
            "group": group,
            "projects": _check_projects(mod),
            "error": None,
            "module": mod,
        })
    return checks


def checks_for_active_project() -> list[dict]:
    """Перевірки, що діють у АКТИВНОМУ проєкті (php-вайти ≠ node-вайти).
    Перевірки з помилкою завантаження показуємо скрізь — щоб їх було видно."""
    import projects
    ptype = projects.ptype()
    return [c for c in load_checks() if ptype in c["projects"]]


def _match_patterns(path: str, patterns: list[str]) -> bool:
    name = Path(path).name
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in patterns)


# ---------------------------------------------------------------- пул процесів
# Чеки впираються в GIL: заміряно 21.09.2026 у dev-контейнері (8 ядер) на
# пачці з 8 php-віток — одна людина в потоках 29.5 с, дві одночасно — по 55 с
# (кожна рівно вдвічі довше), а в пулі з 8 процесів — 10.6 с і 12.3/22.8 с.
# 59% часу прогону — `banned_words`. Для UI пачка з 8 віток — ОДИН HTTP-запит,
# і Cloudflare рве його на 100 с, тож «двоє ганяють одночасно» впиралось у 524.
#
# Вмикається `CHECK_WORKERS` (0 або порожньо — потоки, як завжди). `spawn`, а
# не `fork`: процес лаби багатопотоковий, і fork посеред чужого локу дає
# дитину, що висить назавжди.
#
# ⚠️ Воркер — окремий процес, тож пам'яті процесу лаби в ньому немає. Єдиний
# чек, що в неї дивиться, — `favicon` (`deployer.list_deploys()`, щоб
# смикнути живий деплой вітки). Тому список деплоїв передається разом із
# завданням, і чек бачить рівно те, що бачив би в процесі лаби.
_pool = None
_pool_lock = threading.Lock()


def check_workers() -> int:
    try:
        return max(0, int(os.getenv("CHECK_WORKERS", "").strip() or 0))
    except ValueError:
        return 0


def _get_pool():
    global _pool
    n = check_workers()
    if n <= 0:
        return None
    with _pool_lock:
        if _pool is None:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor
            _pool = ProcessPoolExecutor(
                max_workers=n, mp_context=multiprocessing.get_context("spawn"))
        return _pool


def drop_pool() -> None:
    """Закрити пул (зупинка процесу або пул, що зламався)."""
    global _pool
    with _pool_lock:
        old, _pool = _pool, None
    if old is not None:
        old.shutdown(wait=False, cancel_futures=True)


def _in_worker(fn_name: str, registry: dict, pid: str, deploys: list,
               *args):
    """Виконується В ПРОЦЕСІ-ВОРКЕРІ: той самий реєстр проєктів і ті самі
    живі деплої, що в процесі лаби на момент запуску."""
    import deployer
    import projects
    real_registry, real_deploys = projects._registry, deployer.list_deploys
    projects._registry = registry
    deployer.list_deploys = lambda: [dict(d) for d in deploys]
    try:
        with projects.use(pid):
            return globals()[fn_name](*args)
    finally:
        # Воркер живе далі й бере наступне завдання — нічого з цього не має
        # перетекти в нього.
        projects._registry, deployer.list_deploys = real_registry, real_deploys


_OFFLOAD_TIMEOUT = int(os.getenv("QA_LAB_CHECKS_TIMEOUT", "600"))
# Гігантські вітки (serralheria: 3587 файлів, 350 МБ сторінок) чесно
# рахуються довше за 600с — дедлайн росте з обсягом, інакше «спробуй ще
# раз» ніколи не допомагав (02.10). Стеля — пів години: довше means завис.
_OFFLOAD_PER_FILE = float(os.getenv("QA_LAB_CHECKS_TIMEOUT_PER_FILE", "0.5"))
_OFFLOAD_CEIL = int(os.getenv("QA_LAB_CHECKS_TIMEOUT_CEIL", "1800"))


def _offload_deadline(branch: str) -> int:
    try:
        n = len(snapshot_files(branch))
    except Exception:
        n = 0
    return int(min(_OFFLOAD_CEIL, max(_OFFLOAD_TIMEOUT, n * _OFFLOAD_PER_FILE)))


def _offload(fn_name: str, branch: str, *args):
    """Порахувати в пулі процесів, якщо він увімкнений, — інакше тут же.

    Лок знімка тримає ВИКЛИКАЧ (у процесі лаби), тож черговість «sync →
    прогін» на одній вітці не змінюється.

    `.result()` — З ДЕДЛАЙНОМ: завислий у воркері чек доти тримав і
    відповідь, і лок вітки вічно (кейс 02.10: «виконую перевірки 0%»
    назавжди). По таймауту пул перезапускається, а маяк прогресу каже,
    який саме чек не повернувся."""
    pool = _get_pool()
    if pool is None:
        return globals()[fn_name](branch, *args)
    import projects
    try:
        import deployer
        deploys = deployer.list_deploys()
    except Exception:
        deploys = []
    # Токени воркеру ні до чого: у прогоні немає жодного походу в GitLab.
    registry = {k: {**v, "token": ""} for k, v in projects._registry.items()}
    from concurrent.futures import TimeoutError as FutureTimeout
    from concurrent.futures.process import BrokenProcessPool
    deadline = _offload_deadline(branch)
    try:
        return pool.submit(_in_worker, fn_name, registry, projects.current_id(),
                           deploys, branch, *args).result(deadline)
    except FutureTimeout:
        stuck = _progress_read(branch)
        try:
            n = len(snapshot_files(branch))
        except Exception:
            n = 0
        drop_pool()
        print(f"[runner] {fn_name}({branch}) не вклався у "
              f"{deadline}с — пул перезапущено"
              + (f", обірвано на «{stuck}»" if stuck else ""), flush=True)
        raise RuntimeError(
            (f"вітка велика ({n} файлів): " if n else "")
            + f"прогін не вклався у {deadline}с"
            + (f" — обірвано на чеку «{stuck}»" if stuck else "")
            + "; пул перезапущено — спробуй ще раз або вимкни найважчі "
              "чеки галками")
    except BrokenProcessPool:
        # Воркер упав (OOM, вбитий процес). Прогін не губимо: цей раз — тут,
        # наступний піде вже в новий пул.
        drop_pool()
        print(f"[runner] пул процесів зламався — {fn_name} у потоці", flush=True)
        return globals()[fn_name](branch, *args)


def compute_fixes(branch: str, check_ids: list[str] | None = None) -> list[dict]:
    """Проганяє fix()/fix_delete()/fix_branch() усіх (обраних) перевірок по
    знімку вітки. Нічого не пише. Повертає елементи трьох типів:
      {"type": "edit",   path, old, new, checks}
      {"type": "create", path, new, checks}
      {"type": "delete", path, checks}"""
    with _locked(branch):
        return _offload("_compute_fixes", branch, check_ids)


def _compute_fixes(branch: str, check_ids: list[str] | None = None) -> list[dict]:
    checks = [c for c in checks_for_active_project() if c["module"] and c["fixable"]]
    if check_ids:
        checks = [c for c in checks if c["id"] in check_ids]
    # branch-code: захищені класи з назви вітки вимикають відповідні фікси
    checks, _code_skipped, code_err = code_gate(branch, checks)
    if code_err:
        # битий код — жодного автофікса; ГОЛОСНО: тихий [] виглядав би як
        # «виправлень не знайдено» (02.10)
        raise RuntimeError(f"{code_err} — автофікси зупинені, виправ назву "
                           f"вітки")
    edit_checks = [c for c in checks if hasattr(c["module"], "fix")]
    del_checks = [c for c in checks if hasattr(c["module"], "fix_delete")]
    branch_checks = [c for c in checks if hasattr(c["module"], "fix_branch")]

    out = []
    _progress_note(branch, "фікс: по-файлові чеки")
    for path in snapshot_files(branch):
        if not is_text(path):
            continue
        orig = read_snapshot_file(branch, path).decode("utf-8", errors="replace")
        cur = orig
        applied = []
        for check in edit_checks:
            if not _match_patterns(path, check["files"]):
                continue
            try:
                new = check["module"].fix(path, cur)
            except Exception:
                continue
            if new != cur:
                applied.append(check["name"])
                cur = new
        if cur != orig:
            out.append({"type": "edit", "path": path, "old": orig,
                        "new": cur, "checks": applied})

    if del_checks:
        all_paths = snapshot_files(branch)
        seen = set()
        for check in del_checks:
            _progress_note(branch, f"фікс: {check['name']}")
            try:
                dels = check["module"].fix_delete(all_paths) or []
            except Exception:
                dels = []
            for p in dels:
                if p not in seen:
                    seen.add(p)
                    out.append({"type": "delete", "path": p,
                                "checks": [check["name"]]})

    # fix_branch бачить усю вітку і вміє створювати файли. Працює ПОВЕРХ
    # пофайлових fix(): у files потрапляє вже виправлений текст, тож два хуки
    # на одному файлі не конфліктують.
    #
    # Чеки з fix_branch так само складаються МІЖ СОБОЮ: після кожного його
    # правки вливаються у files/all_paths, і наступний чек бачить уже
    # виправлену вітку. Доти кожен отримував однаковий вихідний знімок, і
    # правка пізнішого чека затирала правку раннього (мітка раннього при цьому
    # лишалась у checks — прев'ю показувало обидві, а комітилась одна). Симптом
    # був такий: «прогнав тести → автофікс → залив → ті самі помилки знову»,
    # і так по одному чеку за раунд. Реальний кейс: `thanks_route` і
    # `form_flow` обидва правлять `scripts/inject-php.cjs`.
    if branch_checks:
        all_paths = snapshot_files(branch)
        # Чим дія є для git — вирішує ВІТКА, а не чек. GitLab відбиває ЦІЛИЙ
        # коміт з 400 «A file with this name already exists», якщо в ньому є
        # create на наявний шлях; разом з ним гинуть і всі решта правок, бо
        # коміт атомарний. Кейс 09.09: `logo_brand` віддає create на
        # src/assets/images/logo.svg завжди, а той лежить у 197 з 246
        # vue-віток — на nwf-cahtat-asvuktimau-br-pt це поховало п'ять
        # здорових правок і виглядало як «лаба не комітить».
        on_disk = set(all_paths) - {c["path"] for c in out if c["type"] == "delete"}
        edited = {c["path"]: c["new"] for c in out if c["type"] == "edit"}
        files = {}
        for p in all_paths:
            if not is_text(p):
                continue
            files[p] = edited.get(
                p, read_snapshot_file(branch, p).decode("utf-8", errors="replace"))

        # fix_branch повертає довільний рядок path — той самий захист від виходу
        # за межі знімка, що вже стоїть у app.py в чотирьох місцях (".." або
        # абсолютний шлях мовчки відкидають base у pathlib). Автор перевірки —
        # довірений код репозиторію, тож це не проти атаки, а проти помилки
        # в майбутньому чеку.
        base = snapshot_dir(branch).resolve()

        by_path = {c["path"]: c for c in out}
        for check in branch_checks:
            _progress_note(branch, f"фікс: {check['name']}")
            try:
                actions = check["module"].fix_branch(files, all_paths, branch) or []
            except Exception:
                continue
            for act in actions:
                kind = act.get("type")
                path = act.get("path")
                if not path or kind not in ("edit", "create", "delete"):
                    continue
                try:
                    p_resolved = (base / path).resolve()
                except Exception:
                    continue
                if base not in p_resolved.parents:
                    continue
                existing = by_path.get(path)
                if kind == "delete":
                    if existing is None:
                        item = {"type": "delete", "path": path,
                                "checks": [check["name"]]}
                        out.append(item)
                        by_path[path] = item
                    # наступні чеки не мусять бачити видалений файл
                    files.pop(path, None)
                    on_disk.discard(path)
                    if path in all_paths:
                        all_paths = [p for p in all_paths if p != path]
                    continue
                content = act.get("content", "")
                # Чек нічого не змінив — це не правка. Пофайловий fix() так
                # само мовчить (`cur != orig`), а без цього байт-у-байт та
                # сама лого-svg їхала в кожен коміт окремим файлом.
                if content == files.get(path, ""):
                    continue
                if existing is not None and existing["type"] in ("edit", "create"):
                    existing["new"] = content            # поверх попередньої правки
                    if check["name"] not in existing["checks"]:
                        existing["checks"].append(check["name"])
                else:
                    kind = "edit" if path in on_disk else "create"
                    old = files.get(path, "") if kind == "edit" else ""
                    item = {"type": kind, "path": path, "old": old,
                            "new": content, "checks": [check["name"]]}
                    out.append(item)
                    by_path[path] = item
                # вливаємо правку у стан вітки: наступний fix_branch працює
                # ПОВЕРХ неї, а не по вихідному знімку
                files[path] = content
                if path not in all_paths:
                    all_paths = all_paths + [path]

    _progress_note(branch, "")
    return out


def actions_for(changes: list[dict]) -> list[dict]:
    """`compute_fixes()` → дії для `client.commit()`.

    Спільне для всіх, хто комітить автофікси: ручна кнопка в UI, ШІ-міст і
    годинний автофікс. Доки це лежало трьома копіями, кожна нова правка
    (напр., поява типу "create") мусила знайти всі три.
    """
    out = []
    for c in changes:
        if c.get("type") == "delete":
            out.append({"action": "delete", "file_path": c["path"]})
        elif c.get("type") == "create":
            out.append({"action": "create", "file_path": c["path"],
                        "content": c["new"]})
        else:
            out.append({"action": "update", "file_path": c["path"],
                        "content": c["new"]})
    return out


def apply_to_snapshot(branch: str, changes: list[dict]) -> None:
    """Вливає щойно закомічені зміни у знімок.

    Без цього наступний прогін по тій самій вітці побачив би старий текст і
    порахував ті самі фікси вдруге. Викликається ПІСЛЯ успішного коміту.
    """
    with _locked(branch):
        base = snapshot_dir(branch)
        for c in changes:
            target = base / c["path"]
            if c.get("type") == "delete":
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(c["new"], encoding="utf-8", newline="")


_SHARD_MIN_FILES = int(os.getenv("QA_LAB_SHARD_MIN_FILES", "160"))


def run_checks(branch: str, check_ids: list[str] | None = None) -> dict:
    """Run checks against the local snapshot of a branch.

    Великі вітки (500+ файлів) шардяться по файлах: по-файлові чеки
    розкладаються на K воркерів існуючого пулу, branch-рівневі йдуть
    окремою задачею — стіна часу ділиться на K (02.10). Дрібні вітки і
    конфігурація без пулу працюють по-старому, одним шматком."""
    with _locked(branch):
        n_workers = check_workers()
        files = snapshot_files(branch)
        if (_get_pool() is None or n_workers < 2
                or len(files) < _SHARD_MIN_FILES):
            return _offload("_run_checks", branch, check_ids)
        k = min(n_workers, 4)
        shards = [files[i::k] for i in range(k)]
        calls = [("_run_checks", (branch, check_ids, shard, "files"))
                 for shard in shards if shard]
        calls.append(("_run_checks", (branch, check_ids, None, "branch")))
        parts = _offload_many(branch, calls)
        return _merge_runs(branch, len(files), parts)


def _merge_runs(branch: str, n_files: int, parts: list[dict]) -> dict:
    by_id: dict[str, dict] = {}
    order: list[str] = []
    skipped_code: set = set()
    bytes_scanned = 0
    for p in parts:
        bytes_scanned += p.get("bytes_scanned", 0)
        skipped_code.update(p.get("skipped_by_code") or [])
        for c in p["checks"]:
            cur = by_id.get(c["id"])
            if cur is None:
                by_id[c["id"]] = dict(c)
                order.append(c["id"])
            else:
                cur["issues"] = cur["issues"] + c["issues"]
                cur["ms"] = cur.get("ms", 0) + c.get("ms", 0)
    totals = {"error": 0, "warn": 0, "info": 0}
    for c in by_id.values():
        for i in c["issues"]:
            sev = i.get("severity", "warn")
            totals[sev] = totals.get(sev, 0) + 1
    out = {"branch": branch, "files_scanned": n_files, "totals": totals,
           "checks": [by_id[cid] for cid in order],
           "bytes_scanned": bytes_scanned}
    if skipped_code:
        out["skipped_by_code"] = sorted(skipped_code)
    return out


def _offload_many(branch: str, calls: list[tuple]) -> list[dict]:
    """Кілька задач у пул з одним сумарним дедлайном; без пулу —
    послідовно тут же."""
    pool = _get_pool()
    if pool is None:
        return [globals()[fn](*args) for fn, args in calls]
    import projects
    try:
        import deployer
        deploys = deployer.list_deploys()
    except Exception:
        deploys = []
    registry = {k: {**v, "token": ""} for k, v in projects._registry.items()}
    from concurrent.futures import TimeoutError as FutureTimeout
    from concurrent.futures.process import BrokenProcessPool
    futs = [pool.submit(_in_worker, fn, registry, projects.current_id(),
                        deploys, *args) for fn, args in calls]
    limit = _offload_deadline(branch)
    deadline = time.time() + limit
    out = []
    try:
        for f in futs:
            out.append(f.result(max(1.0, deadline - time.time())))
        return out
    except FutureTimeout:
        stuck = _progress_read(branch)
        try:
            n = len(snapshot_files(branch))
        except Exception:
            n = 0
        drop_pool()
        raise RuntimeError(
            (f"вітка велика ({n} файлів): " if n else "")
            + f"прогін не вклався у {limit}с"
            + (f" — обірвано на чеку «{stuck}»" if stuck else "")
            + "; пул перезапущено — спробуй ще раз")
    except BrokenProcessPool:
        drop_pool()
        print(f"[runner] пул зламався — шардований прогін у потоці", flush=True)
        return [globals()[fn](*args) for fn, args in calls]


def code_gate(branch: str, checks: list[dict]):
    """(дозволені, скиплені, помилка) за branch-code вітки.

    Чек, чиї MODIFIES перетинаються з захищеними класами з назви вітки
    (branch_code.decode), не запускається взагалі: і фікс, і детект — у
    захищеній вітці лежать РЕАЛЬНІ дані клієнта, тривога по них лише
    шумить. Чек з фіксом БЕЗ декларації MODIFIES вважається «може чіпати
    все» (branch-code.md, правило 1). Битий чек-символ чи чужа версія —
    стоп для людини: вітка повністю захищена + помилка в результаті."""
    import branch_code
    try:
        protected = branch_code.decode(branch)["protected"]
        err = ""
    except branch_code.BranchCodeError as e:
        protected, err = set(branch_code.DICT), str(e)
    if not protected:
        return checks, [], err
    allowed, skipped = [], []
    for c in checks:
        mod = c["module"]
        mods = getattr(mod, "MODIFIES", None)
        if mods is None:
            fixable = any(hasattr(mod, a)
                          for a in ("fix", "fix_branch", "fix_delete"))
            mods = set(branch_code.DICT) if fixable else set()
        if set(mods) & protected:
            skipped.append(c)
        else:
            allowed.append(c)
    return allowed, skipped, err


def _run_checks(branch: str, check_ids: list[str] | None = None,
                only_paths: list[str] | None = None,
                stage: str = "all") -> dict:
    """stage="files": лише по-файлові чеки (run) по only_paths-шарду;
    stage="branch": лише run_branch-чеки по всій вітці; "all" — все."""
    if not is_synced(branch):
        raise ValueError("вітка не синхронізована — спершу Sync")

    checks = [c for c in checks_for_active_project() if c["module"]]
    if check_ids:
        checks = [c for c in checks if c["id"] in check_ids]
    if stage == "files":
        checks = [c for c in checks
                  if not hasattr(c["module"], "run_branch")]
    elif stage == "branch":
        checks = [c for c in checks if hasattr(c["module"], "run_branch")]
    checks, code_skipped, code_err = code_gate(branch, checks)

    files = snapshot_files(branch)
    if only_paths is not None:
        keep = set(only_paths)
        files = [p for p in files if p in keep]
    results = []
    totals = {"error": 0, "warn": 0, "info": 0}

    # Один файл читався З ДИСКА для КОЖНОГО чека, який його матчить: на
    # `mrmseev.ch` це 7103 читання 426 файлів (16.7× зайвих). Кешуємо на час
    # прогону однієї вітки - той самий текст віддається всім чекам.
    cache: dict[str, str] = {}

    def content(path: str) -> str:
        if path not in cache:
            raw = read_snapshot_file(branch, path)
            cache[path] = (raw or b"").decode("utf-8", errors="replace")
        return cache[path]

    def matched_files(check):
        for path in files:
            if not is_text(path):
                continue
            if any(fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(Path(path).name, pat)
                   for pat in check["files"]):
                yield path

    for check in checks:
        issues = []
        started = time.time()
        _progress_note(branch, check["name"])

        def record(issue, default_path=None):
            sev = issue.get("severity", "warn")
            totals[sev] = totals.get(sev, 0) + 1
            issues.append({
                "path": issue.get("path", default_path),
                "line": issue.get("line"),
                "message": issue.get("message", ""),
                "severity": sev,
            })

        try:
            if hasattr(check["module"], "run_branch"):
                contents = {p: content(p) for p in matched_files(check)}
                fn = check["module"].run_branch
                # run_branch(files) | (files, all_paths) | (files, all_paths, branch):
                # all_paths — повний список файлів вітки (включно з бінарниками),
                # branch — назва вітки (потрібна для читання знімка й домену)
                nparams = len(inspect.signature(fn).parameters)
                if nparams >= 3:
                    result = fn(contents, list(files), branch)
                elif nparams == 2:
                    result = fn(contents, list(files))
                else:
                    result = fn(contents)
                for issue in result or []:
                    record(issue)
            else:
                for path in matched_files(check):
                    for issue in check["module"].run(path, content(path)) or []:
                        record(issue, default_path=path)
        except Exception:
            record({"severity": "error",
                    "message": "check crashed:\n" + traceback.format_exc(limit=3)})
        results.append({
            "id": check["id"], "name": check["name"],
            "description": check["description"], "issues": issues,
            # скільки коштував саме цей чек на цій вітці — щоб важкі було видно
            # в UI і можна було зняти галку, а не гадати, чому прогін довгий
            "ms": int((time.time() - started) * 1000),
        })

    _progress_note(branch, "")
    out = {"branch": branch, "files_scanned": len(files), "totals": totals,
           "checks": results,
           "bytes_scanned": sum(len(v) for v in cache.values())}
    if code_skipped:
        out["skipped_by_code"] = sorted(c["id"] for c in code_skipped)
    if code_err and stage in ("all", "branch"):
        totals["error"] = totals.get("error", 0) + 1
        out["checks"].append({
            "id": "branch_code", "name": "Код вітки",
            "description": "захищені класи у назві вітки", "ms": 0,
            "issues": [{"path": "", "line": 0, "severity": "error",
                        "message": (f"{code_err} — фікси й чеки захищених "
                                    f"класів зупинені, виправ назву вітки")}],
        })
    return out
