"""Local PHP deploys of branch snapshots.

deploy(branch):
  1. copies cache/<branch>/ into deploy/<branch>/
  2. in the copy only, flips $isDev = false -> true in every *.php
     (the git/snapshot version keeps false)
  3. starts the built-in PHP web server on a free port

The deployed copy is disposable — redeploy after every sync/commit to refresh.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import socket
import subprocess
import time
from pathlib import Path

import projects
from runner import snapshot_dir

BASE_PORT = 9100
ISDEV_RX = re.compile(r"\$isDev\s*=\s*false")

_running: dict[str, dict] = {}   # "<project>::<branch>" -> {"proc": Popen, "port": int}
_build_lock = __import__("threading").Lock()   # nuxt-білди — по одному за раз
# Порт вибирається і реєструється НЕ атомарно: два паралельних деплої
# (візуальні перевірки кількох віток) інакше беруть той самий порт і другий
# php падає. Той самий лок захищає спільний vendor-стаб у корені deploy/.
_serve_lock = __import__("threading").Lock()


def deploy_root() -> Path:
    return projects.state_dir() / "deploy"


def screens_root() -> Path:
    return projects.state_dir() / "screens"


# сумісність зі старими зверненнями (storage-ендпоінт тощо)
DEPLOY_DIR = Path("deploy")
SCREENS_DIR = Path("screens")


def _safe_deploy_name(branch: str) -> str:
    """Ім'я теки деплою/скріна: без '/' (namespaces) і ':' (Windows)."""
    return branch.replace("/", "__").replace(":", "_")


def is_node_build(branch: str) -> bool:
    """Чи вітка збирається npm-ом: node-проєкт І package.json у знімку.

    У node-проєкті живуть і не-node вайти: 165 віток new-white-front без
    package.json (160 php з index.php, 5 статичних з index.html) — TSM
    імпортує їх туди так само, як у white-pages. Без package.json npm шукає
    його вгору по теках і на проді бере /app/package.json самої лаби
    (Lighthouse): `npm install` ставить залежності лаби, а `npm run generate`
    падає «Missing script: "generate"» (кейс baggoetiepohsa-rekivo.com.br-br-pt
    26.10). Такі вітки деплояться як php — так само, як у white-pages."""
    return projects.ptype() == "node" and (snapshot_dir(branch) / "package.json").is_file()


def _key(branch: str) -> str:
    return f"{projects.current_id()}::{branch}"


def is_running(branch: str) -> bool:
    return _key(branch) in _running


def running_port(branch: str) -> int | None:
    """Порт уже запущеного деплою або None.

    Потрібен прев'ю: копію тримає свіжою вотчер (`_watch_php` доливає правки
    знімка, `_watch_node` перезбирає dist), тож другий `deploy()` новизни не
    дає — лише зайвий nuxt-білд на 30-60 с у запиті, який чекає людина.
    """
    info = _running.get(_key(branch))
    return info["port"] if info else None


def php_bin() -> str:
    default = r"C:\php\php.exe" if os.name == "nt" else "php"
    return os.getenv("PHP_BIN", default)


# Своя process group для кожного php: на Windows — щоб Ctrl+C сервера не
# валив деплої, на POSIX — щоб _kill_pid міг покласти php разом з дітьми.
_SPAWN_KW = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
             if os.name == "nt" else {"start_new_session": True})


def _php_available() -> bool:
    """PHP_BIN може бути і повним шляхом (Windows), і просто «php» з PATH
    (Linux/macOS) — перевіряємо обидва варіанти."""
    b = php_bin()
    return bool(Path(b).exists() or shutil.which(b))


def npm_bin() -> str:
    return os.getenv("NPM_BIN", "npm.cmd" if os.name == "nt" else "npm")


def _free_port() -> int:
    busy = {i["port"] for i in _running.values()}
    for port in range(BASE_PORT, BASE_PORT + 100):
        if port in busy:
            continue
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free port in 9100..9199")


def _url(port: int) -> str:
    return f"http://127.0.0.1:{port}/"


# --- реєстр pid-ів php на диску: щоб гасити осиротілі деплої після рестарту ---
# Спільний на всі проєкти, тому лежить у корені стану, а не в state_dir().
_PIDS_FILE = projects.state_root() / ".deploy_pids.json"


def _load_pids() -> list[int]:
    if _PIDS_FILE.exists():
        try:
            return __import__("json").loads(_PIDS_FILE.read_text())
        except Exception:
            return []
    return []


_pids_lock = __import__("threading").Lock()   # read-modify-write спільного файла


def _save_pids(pids):
    _PIDS_FILE.write_text(__import__("json").dumps(sorted(set(pids))))


def _record_pid(pid: int):
    with _pids_lock:
        _save_pids(_load_pids() + [pid])


def _forget_pid(pid: int):
    with _pids_lock:
        _save_pids([p for p in _load_pids() if p != pid])


def _is_php(pid: int) -> bool:
    """Чи цей pid — досі php (захист від reuse pid іншим процесом).

    Вивід НЕ декодуємо через text=True: `tasklist` віддає його в кодуванні
    консолі (на локалізованій Windows це cp866), і UnicodeDecodeError у
    рідерському потоці валив перевірку в except — функція завжди повертала
    False, а reap_orphans через це не гасив жодного осиротілого php.
    """
    try:
        if os.name == "nt":
            raw = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FI", "IMAGENAME eq php.exe", "/NH"],
                capture_output=True, timeout=10).stdout
            return "php.exe" in raw.decode("utf-8", "replace").lower()
        # POSIX: ім'я процесу з /proc (Linux) або ps (macOS/BSD)
        comm = Path(f"/proc/{pid}/comm")
        if comm.exists():
            return "php" in comm.read_text(errors="replace").strip().lower()
        raw = subprocess.run(["ps", "-p", str(pid), "-o", "comm="],
                             capture_output=True, timeout=10).stdout
        return "php" in raw.decode("utf-8", "replace").strip().lower()
    except Exception:
        return False


def _kill_pid(pid: int) -> bool:
    """Гасить процес разом з дітьми. На POSIX б'ємо по групі: php кладемо
    у власну process group (start_new_session нижче), тож воркери не
    лишаються сиротами."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=10)
            return True
        import signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGKILL)
        return True
    except Exception:
        return False


def reap_orphans() -> int:
    """Гасить php-деплої, що лишились від попереднього запуску сервера
    (після рестарту вони тримають теки deploy/ і ламають redeploy).
    Викликається на старті app.py."""
    killed = 0
    for pid in _load_pids():
        if pid in {i["proc"].pid for i in _running.values()}:
            continue                          # живий у поточній сесії — не чіпаємо
        if _is_php(pid) and _kill_pid(pid):
            killed += 1
    _save_pids([i["proc"].pid for i in _running.values()])
    return killed


def _reset_dir(dest: Path):
    """Надійно чистить теку деплою (з ретраями — Windows звільняє хендли з лагом)."""
    for _ in range(6):
        if not dest.exists():
            return
        shutil.rmtree(dest, ignore_errors=True)
        if not dest.exists():
            return
        time.sleep(0.4)


# стаб composer-autoload: заглушка Dotenv, щоб require й createImmutable()->safeLoad()
# не падали, коли реального vendor/ немає (safe-сторінки його не тримають у гіті)
_VENDOR_STUB = """<?php
// qa_lab deploy stub — фейковий Dotenv, щоб сторінка рендерилась без composer.
namespace Dotenv {
    class Dotenv {
        public static function createImmutable($paths, $names = null) { return new self(); }
        public static function createUnsafeImmutable($paths, $names = null) { return new self(); }
        public static function createMutable($paths, $names = null) { return new self(); }
        public static function createUnsafeMutable($paths, $names = null) { return new self(); }
        public function load() { return []; }
        public function safeLoad() { return []; }
        public function required($name) { return $this; }
        public function ifPresent($name) { return $this; }
    }
}
"""


def _write_vendor_stub(vendor_dir: Path):
    vendor_dir.mkdir(parents=True, exist_ok=True)
    (vendor_dir / "autoload.php").write_text(_VENDOR_STUB, encoding="utf-8")


def deploy(branch: str, wait: bool = False) -> dict:
    """Деплой за вмістом вітки: node-вайт (is_node_build) — build → dist/;
    решта — як є через php -S.

    wait=False (кнопка в UI): nuxt-білд іде у ФОНІ, повертається status=building,
    UI опитує /api/deploy/status. wait=True (скріни/lighthouse): блокуємось до
    кінця білду, бо їм потрібен URL одразу.
    """
    if not _php_available():
        raise ValueError(f"php не знайдено: {php_bin()} (задай PHP_BIN у .env)")
    src = snapshot_dir(branch)
    if not src.exists():
        raise ValueError("вітка не синхронізована — спершу Sync")
    if is_node_build(branch):
        return _deploy_nuxt(branch, wait=wait)
    return _deploy_php(branch)


def log_path(branch: str) -> Path:
    """Лог `php -S` однієї вітки — поруч із текою деплою, тим самим ім'ям.

    Traversal-гард той самий, що в `runner.snapshot_dir`: назва вітки
    приходить з HTTP.
    """
    base = deploy_root().resolve()
    p = (base / (_safe_deploy_name(branch) + ".log")).resolve()
    if p.parent != base:
        raise ValueError(f"bad branch name: {branch!r}")
    return p


def read_log(branch: str, limit: int = 200) -> str:
    """Хвіст логу деплою. Порожньо — якщо вітку ще не піднімали."""
    p = log_path(branch)
    if not p.exists():
        return ""
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max(1, limit):])


def _serve(branch: str, docroot: Path, router: Path | None = None, **extra) -> dict:
    cmd = [php_bin(), "-S", "", "-t", str(docroot.resolve())]
    if router:
        cmd.append(str(router.resolve()))
    # stderr php -S — ЄДИНЕ місце, де видно, чому сторінка порожня. У образі
    # `display_errors = Off`, а `log_errors = On` з порожнім `error_log`, тобто
    # фатальна помилка вайта не потрапляє ні в тіло відповіді, ні у файл — вона
    # йде саме сюди. Доки цей потік ішов у DEVNULL, «біла сторінка» не мала
    # жодного пояснення ніде (кейс 28.08: php-вайти на прев'ю-хості).
    # Туди ж і stdout: php -S пише в stderr і журнал запитів, тобто видно ще й
    # код відповіді на кожен запит.
    log = log_path(branch)
    log.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log, "wb")                 # свіжий лог на кожен підйом
    try:
        with _serve_lock:
            port = _free_port()
            cmd[2] = f"127.0.0.1:{port}"
            proc = subprocess.Popen(cmd, stdout=fh, stderr=fh, **_SPAWN_KW)
            _running[_key(branch)] = {"proc": proc, "port": port}
    finally:
        fh.close()                       # дескриптор уже продубльовано дитині
    _record_pid(proc.pid)
    _start_watcher(branch)
    return {"branch": branch, "port": port, "url": _url(port), **extra}


def _deploy_php(branch: str) -> dict:
    src = snapshot_dir(branch)
    stop(branch)
    dest = deploy_root() / _safe_deploy_name(branch)
    _reset_dir(dest)
    shutil.copytree(src, dest, dirs_exist_ok=True)
    (dest / ".snapshot.json").unlink(missing_ok=True)

    patched = 0
    for php in dest.rglob("*.php"):
        # скрейпи приносять чужі асети разом зі шляхами, і серед них бувають
        # ТЕКИ з іменем на .php (macgowuiqbg: `…/images/emoji.php/v9`).
        # read_text по теці — PermissionError, і вітка переставала деплоїтись.
        if not php.is_file():
            continue
        text = php.read_text(encoding="utf-8", errors="replace")
        new = ISDEV_RX.sub("$isDev = true", text)
        if new != text:
            php.write_text(new, encoding="utf-8")
            patched += 1

    # багато шаблонів тягнуть composer-autoload/Dotenv БЕЗУМОВНО (без гарду
    # $isDev) — його немає у знімку вітки, тож підкладаємо стаб. Шляхи бувають
    # і '../vendor', і './vendor' → кладемо обидва.
    with _serve_lock:                             # спільний файл на всі вітки
        _write_vendor_stub(deploy_root() / "vendor")  # для __DIR__ . '/../vendor'
    _write_vendor_stub(dest / "vendor")           # для __DIR__ . '/vendor'

    return _serve(branch, dest, isdev_patched=patched)


# Точка входу зібраного вайта. Nuxt/Next кладуть у dist/ index.html, а вайти
# на vite-ssg проганяють постбілдом scripts/inject-php.cjs: він інжектить
# трекінг/форму і ПЕРЕЙМЕНОВУЄ index.html → index.php (у Vite не можна
# тримати <?php у джерелі index.html — parse5 його не приймає). Тому точка
# входу шукається, а не припускається.
DIST_ENTRIES = ("index.html", "index.php")


def dist_entry(dist: Path) -> Path | None:
    for name in DIST_ENTRIES:
        p = dist / name
        if p.is_file():
            return p
    return None


def require_dist_entry(dist: Path) -> Path:
    entry = dist_entry(dist)
    if entry is None:
        raise RuntimeError("білд не створив точку входу: немає ні "
                           "dist/index.html, ні dist/index.php")
    return entry


# SPA-fallback для node-статики: файл є — віддати, нема — точка входу.
# DOCUMENT_ROOT = docroot з `php -S -t`, тобто dist/ (router.php лежить поза ним).
# index.php саме INCLUDE, а не readfile: інакше php -S віддав би вихідний код
# сторінки разом з інжектованим трекінгом.
_SPA_ROUTER = """<?php
$root = $_SERVER['DOCUMENT_ROOT'];
$path = urldecode(parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH));
$file = $root . str_replace('/', DIRECTORY_SEPARATOR, $path);
if ($path !== '/' && is_file($file)) return false;   // існує -> нехай php -S віддасть
$php = $root . DIRECTORY_SEPARATOR . 'index.php';
if (is_file($php)) {
    include $php;
} else {
    header('Content-Type: text/html; charset=utf-8');
    readfile($root . DIRECTORY_SEPARATOR . 'index.html');
}
"""


# кольори vite/npm: у тості вони лишались сміттям «[39m» у кінці рядка
_ANSI_RX = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# кадр стеку node: «    at createDescriptor (/app/…/plugin-vue/dist/index.cjs:84:43)»
_STACK_RX = re.compile(r"^\s+at\s")
# таблиця зібраних файлів vite: «dist/assets/Home-CnGMiEE5.js  15.62 kB │ gzip: …»
_ASSET_RX = re.compile(r"^dist/\S+\s+[\d.,]+\s+kB\b")
# заголовок неперехопленого винятку node: «scripts/inject-php.cjs:1», далі
# рядок коду, «^» і сам «Error: …»
_CRASH_RX = re.compile(r"^\S+\.[cm]?[jt]s:\d+$")
# «SyntaxError: [plugin vite:vue] …» — перший рядок err.stack, повтор
# повідомлення, яке vite уже надрукував рядком вище
_ERR_PREFIX_RX = re.compile(r"^[A-Za-z]*Error:\s+")


def _npm_error(output: str, cwd: Path, limit: int = 800) -> str:
    """ПРИЧИНА з виводу впалого npm, а не його хвіст.

    Кейс 30.09 («у колеги вайти не деплояться»): у тості був лише стек —
    `…at createDescriptor (…) at transformMain (…index.cjs:2434:34)[39m`.
    Vite друкує повідомлення і `file:` за ~1.5 КБ до кінця виводу, а далі —
    десять кадрів стеку; тут брався сліпий хвіст [-800:], і з нього ще раз
    [-600:] — людині діставались рівно кадри. Причина — зайвий `</div>` у
    Footer.vue, закомічений руками, — з повідомлення
    «src/components/Footer.vue (34:9): Invalid end tag.» видна одразу.

    Кольори й кадри стеку — геть, абсолютний шлях builder-а — у шлях вітки.
    Блок vite «error during build:» (повідомлення, кадр коду, file:) і креш
    node (постбілд inject-php.cjs) віддаються З ПОЧАТКУ; решта (npm install) —
    хвостом, як і було."""
    text = _ANSI_RX.sub("", output)
    root = str(cwd)
    # vite на Windows пише шлях через «/», а cwd тут може бути заданий «\»
    for r in (root, root.replace("\\", "/")):
        for prefix in ("file:///" + r.lstrip("/") + "/", r + "/", r + "\\"):
            text = text.replace(prefix, "")
    lines = [l.rstrip() for l in text.splitlines()
             if not _STACK_RX.match(l) and not _ASSET_RX.match(l)]
    start = next((i + 1 for i, l in enumerate(lines)
                  if l.startswith("error during build")), None)
    if start is None:
        start = next((i for i in range(len(lines) - 1, -1, -1)
                      if _CRASH_RX.match(lines[i])), None)
    kept = []
    for l in lines[start or 0:]:
        rest = _ERR_PREFIX_RX.sub("", l)
        if rest != l and any(k.endswith(rest) for k in kept):
            continue
        if not l.strip() and (not kept or not kept[-1].strip()):
            continue                     # порожні рядки — не більше одного підряд
        kept.append(l)
    msg = "\n".join(kept).strip()
    if start is None or not msg:
        return (msg or "\n".join(lines).strip())[-limit:]
    return msg[:limit]


def _run_npm(args: list[str], cwd: Path, timeout: int) -> None:
    env = {**os.environ, "NUXT_TELEMETRY_DISABLED": "1", "CI": "1"}
    proc = subprocess.run([npm_bin()] + args, cwd=str(cwd), env=env, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        why = _npm_error(proc.stdout.decode("utf-8", "replace"), cwd)
        raise RuntimeError(f"npm {' '.join(args)} упав:\n{why}")


import threading as _threading

_builds: dict[str, dict] = {}   # key -> {status: building|ready|error, ...}


def _nuxt_paths(branch: str):
    src = snapshot_dir(branch)
    commit = None
    meta_path = src / ".snapshot.json"
    if meta_path.exists():
        try:
            commit = __import__("json").loads(meta_path.read_text(encoding="utf-8")).get("commit")
        except Exception:
            pass
    out_dir = deploy_root() / _safe_deploy_name(branch)
    return src, commit, out_dir, out_dir / "dist", out_dir / ".build.json"


def _builder_for(src: Path) -> Path:
    """Окремий builder на набір залежностей (хеш package-lock/package.json).

    Проєкт може містити гілки на РІЗНИХ фреймворках (Nuxt, Next.js, …) — їх
    node_modules несумісні, тож ділити один каталог не можна. Гілки з
    однаковими залежностями природно ділять builder+node_modules."""
    import hashlib
    key = src / "package-lock.json"
    if not key.exists():
        key = src / "package.json"
    h = hashlib.sha1(key.read_bytes()).hexdigest()[:10] if key.exists() else "default"
    return projects.state_dir() / f"builder-{h}"


# маркер вдалого install у builder: builder і так окремий на кожен хеш
# залежностей (див. _builder_for), тож поки маркер на місці — node_modules
# гарантовано відповідає package.json і повторний npm install зайвий
_INSTALL_OK = ".install.ok"

# що переживає чистку builder між білдами:
# node_modules — кеш залежностей, .next — кеш компіляції Next (10 с → 2 с),
# маркер install
_BUILDER_KEEP = ("node_modules", ".next", _INSTALL_OK)


def _nuxt_compile(branch: str) -> Path:
    """Важка частина: знімок → builder (per-deps) → npm install (кешовано) →
    generate. Повертає ЗАБРАНИЙ під локом dist. Кидає на помилці.

    Забирати треба саме під локом: builder спільний на набір залежностей, і
    коли UI жене кілька віток паралельно, наступний білд першим ділом чистить
    builder — якщо віддати голий `builder/dist`, він встигає зникнути до
    `shutil.move` у викликача («No such file or directory: …builder-…/dist»,
    2 з 4 віток у прогоні). Тому dist під локом перейменовується в унікальний
    `dist-<вітка>` — далі ним володіє лише свій викликач."""
    src = snapshot_dir(branch)
    if not (src / "package.json").is_file():
        # npm без package.json у cwd пішов би вгору по теках — до
        # /app/package.json лаби (див. is_node_build)
        raise RuntimeError("у вітці немає package.json — це не node-вайт, "
                           "npm-білд неможливий")
    with _build_lock:                         # білди — по одному
        builder = _builder_for(src)
        builder.mkdir(parents=True, exist_ok=True)
        for item in builder.iterdir():        # чистимо все, крім кешів
            # dist-<вітка> — забраний білд, який його викликач ще не встиг
            # перенести (див. хвіст функції); чужі не чіпаємо, свій
            # пересоздається через rmtree перед rename
            if item.name in _BUILDER_KEEP or item.name.startswith("dist-"):
                continue
            shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink(missing_ok=True)
        for item in src.iterdir():
            if item.name in (".snapshot.json", "node_modules"):
                continue
            if item.is_dir():
                shutil.copytree(item, builder / item.name)
            else:
                shutil.copy2(item, builder / item.name)

        # install пропускається, поки в builder лежить маркер вдалого install
        if not ((builder / "node_modules").exists() and (builder / _INSTALL_OK).exists()):
            try:
                _run_npm(["install", "--no-audit", "--no-fund", "--prefer-offline"], builder, timeout=600)
            except RuntimeError:
                # --prefer-offline вірить кешу npm без ревалідації: коли метадані
                # пакета в кеші застаріли, а свіжа залежність вимагає новішу версію,
                # інсталл падає з ETARGET («No matching version found»), хоча реєстр
                # версію має. Повтор із --prefer-online оновлює метадані примусово.
                _run_npm(["install", "--no-audit", "--no-fund", "--prefer-online"], builder, timeout=600)
            (builder / _INSTALL_OK).write_text("ok", encoding="utf-8")
        try:
            _run_npm(["run", "generate"], builder, timeout=600)
        except RuntimeError:
            # у шаблонах без package-lock кешований node_modules з часом
            # «роз'їжджається»: частковий апдейт лишає, напр., react 19.2.7
            # поруч із react-dom 19.2.0 — і білд падає на version-mismatch.
            # Важливо: npm при кожному install ПИШЕ package-lock.json з
            # поточного (зламаного) дерева — якщо його не знести разом з
            # node_modules, фреш-інсталл чесно відтворить зламаний стан з лока.
            # Лок видаляємо лише згенерований: якщо він Є у знімку вітки —
            # він авторитетний, і чіпати його не можна.
            (builder / _INSTALL_OK).unlink(missing_ok=True)
            _reset_dir(builder / "node_modules")
            _reset_dir(builder / ".next")
            if not (src / "package-lock.json").exists():
                (builder / "package-lock.json").unlink(missing_ok=True)
            _run_npm(["install", "--no-audit", "--no-fund", "--prefer-online"], builder, timeout=600)
            (builder / _INSTALL_OK).write_text("ok", encoding="utf-8")
            _run_npm(["run", "generate"], builder, timeout=600)

        b_dist = builder / "dist"
        require_dist_entry(b_dist)
        claimed = builder / f"dist-{_safe_deploy_name(branch)}"
        shutil.rmtree(claimed, ignore_errors=True)
        os.rename(b_dist, claimed)     # та сама ФС — миттєво; ще під локом
        return claimed


def _write_build_meta(build_meta: Path, commit, branch: str):
    """commit + зліпок знімка: fresh-check бачить і нові коміти, і локальні правки."""
    build_meta.write_text(__import__("json").dumps(
        {"commit": commit, "state": _snap_digest(snapshot_dir(branch))}),
        encoding="utf-8")


def _nuxt_build(branch: str, commit, out_dir: Path, dist: Path, build_meta: Path):
    b_dist = _nuxt_compile(branch)
    _reset_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # move замість copytree: та сама файлова система, тож це миттєвий
    # rename; builder/dist однаково пересоздається наступним білдом
    shutil.move(str(b_dist), str(dist))
    _write_build_meta(build_meta, commit, branch)


def _serve_nuxt(branch: str, out_dir: Path, dist: Path, built: bool) -> dict:
    router = out_dir / "router.php"
    router.write_text(_SPA_ROUTER, encoding="utf-8")
    return _serve(branch, dist, router=router, built=built)


def _nuxt_worker(branch: str, commit, out_dir: Path, dist: Path, build_meta: Path):
    key = _key(branch)
    try:
        _nuxt_build(branch, commit, out_dir, dist, build_meta)
        info = _serve_nuxt(branch, out_dir, dist, built=True)
        _builds[key] = {"status": "ready", "branch": branch, **info}
    except Exception as e:
        # голова, а не хвіст: причину _npm_error уже кладе першою
        _builds[key] = {"status": "error", "branch": branch, "error": str(e)[:1000]}


def _deploy_nuxt(branch: str, wait: bool = False) -> dict:
    """npm install (спільний builder на проєкт) → nuxt generate → віддати dist/.

    node_modules живе у projects/<id>/builder/ і перевикористовується всіма
    вітками. Ребілд пропускається, якщо commit вітки не змінився з минулого.
    Якщо білд потрібен: wait=False → у фоні (status=building), wait=True → блокуємось.
    """
    src, commit, out_dir, dist, build_meta = _nuxt_paths(branch)
    stop(branch)

    fresh = False
    if dist_entry(dist) and commit and build_meta.exists():
        try:
            meta = __import__("json").loads(build_meta.read_text(encoding="utf-8"))
            # той самий commit І жодних локальних правок знімка після білда —
            # інакше деплой віддавав би dist без свіжих змін
            fresh = meta.get("commit") == commit and \
                meta.get("state") == _snap_digest(src)
        except Exception:
            fresh = False

    key = _key(branch)
    if fresh:
        info = _serve_nuxt(branch, out_dir, dist, built=False)
        _builds[key] = {"status": "ready", "branch": branch, **info}
        return {**info, "status": "ready"}

    if wait:                                   # скріни/lighthouse — треба URL зараз
        _nuxt_build(branch, commit, out_dir, dist, build_meta)
        info = _serve_nuxt(branch, out_dir, dist, built=True)
        _builds[key] = {"status": "ready", "branch": branch, **info}
        return {**info, "status": "ready"}

    # фоновий білд — HTTP-запит повертається миттєво
    if _builds.get(key, {}).get("status") == "building":
        return {"branch": branch, "status": "building"}
    _builds[key] = {"status": "building", "branch": branch}
    # Потік — через `projects.thread`: воркер рахує ключ деплою, builder і
    # теку dist від проєкту, а голий потік стартує в дефолтному проєкті
    # процесу. З проєктом на людину vue-білд, запущений з php-дефолтом,
    # зареєструвався б під чужим ключем і вічно висів би «building».
    projects.thread(_nuxt_worker, branch, commit, out_dir, dist, build_meta,
                    name=f"nuxt-build-{key}")
    return {"branch": branch, "status": "building"}


def build_status(branch: str) -> dict:
    key = _key(branch)
    st = _builds.get(key)
    if st:
        return st
    if is_running(branch):
        info = _running[key]
        return {"branch": branch, "status": "ready", "port": info["port"],
                "url": _url(info["port"])}
    return {"branch": branch, "status": "none"}


def stop(branch: str) -> bool:
    _stop_watcher(_key(branch))
    info = _running.pop(_key(branch), None)
    if not info:
        return False
    if info["proc"].poll() is None:
        info["proc"].kill()
        info["proc"].wait(timeout=10)
    _forget_pid(info["proc"].pid)
    return True


def stop_all():
    """Зупиняє ВСІ деплої всіх проєктів (shutdown, очистка диска)."""
    for key in list(_watchers):
        _stop_watcher(key)
    for key, info in list(_running.items()):
        if info["proc"].poll() is None:
            info["proc"].kill()
            try:
                info["proc"].wait(timeout=10)
            except Exception:
                pass
        _running.pop(key, None)
    _save_pids([])


# ---------------- live-sync: правки знімка підхоплюються запущеним деплоєм ----
# Вотчер стартує разом із деплоєм (_serve) і живе, поки деплой запущений.
# Раз на ~1.5 с знімається зліпок mtime/size файлів знімка; будь-яка зміна
# (редактор «Файли», Заміни, автофікси, правка через провідник у «Локальних»,
# ресинк) підхоплюється сама, без передеплою:
#   php  — змінені файли одразу копіюються в deploy/ (з тим самим патчем
#          $isDev), видалені — прибираються; порт і URL не змінюються;
#   node — після паузи-«затишшя» білд перезапускається і dist підміняється
#          на льоту; php -S не рестартує, URL живе.
_watchers: dict[str, "_threading.Event"] = {}


def _snap_state(src: Path) -> dict:
    """Зліпок знімка: {rel: (mtime_ns, size)} — дешево і достатньо для дифа."""
    out = {}
    try:
        for p in src.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(src).as_posix()
            if rel == ".snapshot.json" or rel.startswith("node_modules/"):
                continue
            st = p.stat()
            out[rel] = (st.st_mtime_ns, st.st_size)
    except OSError:
        pass
    return out


def _snap_digest(src: Path) -> str:
    import hashlib
    h = hashlib.sha1()
    for rel, meta in sorted(_snap_state(src).items()):
        h.update(f"{rel}|{meta[0]}|{meta[1]};".encode())
    return h.hexdigest()[:16]


def _copy_patched(src_file: Path, dest_file: Path):
    """Файл знімка → у деплой; .php дорогою отримує той самий патч $isDev."""
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    if src_file.suffix.lower() == ".php":
        text = src_file.read_text(encoding="utf-8", errors="replace")
        dest_file.write_text(ISDEV_RX.sub("$isDev = true", text), encoding="utf-8")
    else:
        shutil.copy2(src_file, dest_file)


def _watch_php(branch: str, stop_ev):
    src = snapshot_dir(branch)
    dest = deploy_root() / _safe_deploy_name(branch)
    state = _snap_state(src)
    while not stop_ev.wait(1.5):
        new = _snap_state(src)
        if not new or new == state:
            continue
        try:
            for rel in state.keys() - new.keys():
                (dest / rel).unlink(missing_ok=True)
            for rel, meta in new.items():
                if state.get(rel) != meta:
                    _copy_patched(src / rel, dest / rel)
        except OSError:
            continue                     # ретрай на наступному тику
        state = new


def _watch_node(branch: str, stop_ev):
    src = snapshot_dir(branch)
    state = _snap_state(src)
    while not stop_ev.wait(1.5):
        new = _snap_state(src)
        if not new or new == state:
            continue
        while not stop_ev.wait(1.2):     # debounce: чекаємо «затишшя» правок
            cur = _snap_state(src)
            if cur == new:
                break
            new = cur
        if stop_ev.is_set():
            return
        try:
            _, commit, out_dir, dist, build_meta = _nuxt_paths(branch)
            b_dist = _nuxt_compile(branch)
            # підміна dist на льоту: rename старого → move нового → прибрати;
            # php -S не рестартує, тож порт/URL живуть далі
            old = out_dir / ".dist.old"
            shutil.rmtree(old, ignore_errors=True)
            for _ in range(6):           # php -S може тримати хендл — ретраї
                try:
                    os.rename(dist, old)
                    break
                except OSError:
                    time.sleep(0.4)
            shutil.move(str(b_dist), str(dist))
            shutil.rmtree(old, ignore_errors=True)
            _write_build_meta(build_meta, commit, branch)
        except Exception:
            pass                         # невдалий ребілд не вбиває вотчер
        state = _snap_state(src)


def _start_watcher(branch: str):
    key = _key(branch)
    _stop_watcher(key)
    ev = _threading.Event()
    fn = _watch_node if is_node_build(branch) else _watch_php
    _watchers[key] = ev
    # Вотчер живе, поки живе деплой, і шляхи знімка/деплою рахує вже в
    # СВОЄМУ потоці — тому контекст (проєкт людини) мусить їхати з ним.
    projects.thread(fn, branch, ev, name=f"deploy-watch-{key}")


def _stop_watcher(key: str):
    ev = _watchers.pop(key, None)
    if ev:
        ev.set()


# Кандидати на headless-браузер. BROWSER_BIN з .env завжди перший; далі —
# типові розкладки Windows / Linux / macOS. На Linux бінарник зазвичай
# лежить у PATH під різними іменами (пакет chromium у Debian/Ubuntu,
# chromium-browser у старих, google-chrome зі своїм репозиторієм), тому
# спершу пробуємо PATH і лише потім абсолютні шляхи.
_BROWSER_NAMES = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge", "microsoft-edge-stable", "brave-browser",
]
_BROWSER_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge", "/snap/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def _browser_bin() -> str:
    env = os.getenv("BROWSER_BIN", "").strip()
    if env:
        if Path(env).exists() or shutil.which(env):
            return env
        raise ValueError(f"BROWSER_BIN з .env не знайдено: {env}")
    if os.name != "nt":
        for name in _BROWSER_NAMES:
            found = shutil.which(name)
            if found:
                return found
    for c in _BROWSER_PATHS:
        if Path(c).exists():
            return c
    raise ValueError("не знайдено Chrome/Chromium/Edge для скріншотів — "
                     "задай BROWSER_BIN у .env "
                     "(Debian/Ubuntu: sudo apt install chromium)")


def browser_extra_args() -> list[str]:
    """Додаткові прапорці запуску Chrome з BROWSER_EXTRA_ARGS у .env.

    Порожньо за замовчуванням — на робочій станції нічого не змінюється.
    У контейнері сюди йдуть два прапорці, без яких браузер не працює:
      --no-sandbox             пісочниця вимагає привілеїв, яких там немає;
      --disable-dev-shm-usage  /dev/shm у docker за замовчуванням 64 МБ, і на
                               довгій сторінці (вайти бувають 9000 px) Chrome
                               падає. Штатне лікування — shm_size у compose,
                               але Swarm його ІГНОРУЄ, тож лишається прапорець.

    Спільний для всіх трьох місць, де піднімається браузер: тут (скріни),
    visual_runner (візуальні перевірки) і photos (пошук фото без ключа).
    """
    return shlex.split(os.getenv("BROWSER_EXTRA_ARGS", ""))


# (width, max_height, mobile-емуляція). mobile: true — Chrome емулює мобільний
# пристрій як DevTools (viewport meta, мобільні media queries), а не просто
# вузьке десктопне вікно, у якому верстка вилазила за край скріна.
VIEWPORTS = {"desktop": (1366, 2200, False), "mobile": (425, 2000, True)}


def _cdp_shots(browser: str, url: str, viewports: dict) -> dict[str, bytes]:
    """Скріншоти через Chrome DevTools Protocol: справжня мобільна емуляція +
    повна висота сторінки (captureBeyondViewport)."""
    import base64
    import json

    import requests
    from websockets.sync.client import connect as ws_connect

    # вільний порт для дебагера
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dbg_port = s.getsockname()[1]

    proc = subprocess.Popen(
        [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--no-first-run", "--no-default-browser-check"]
        + browser_extra_args()
        + [f"--remote-debugging-port={dbg_port}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        page = None
        for _ in range(50):                   # чекаємо, поки підніметься дебаг-порт
            try:
                targets = requests.get(f"http://127.0.0.1:{dbg_port}/json", timeout=2).json()
                page = next(t for t in targets if t.get("type") == "page")
                break
            except Exception:
                time.sleep(0.2)
        if not page:
            raise RuntimeError("chrome не відкрив debug-порт")

        out: dict[str, bytes] = {}
        with ws_connect(page["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024) as ws:
            mid = [0]

            def cmd(method: str, **params):
                mid[0] += 1
                ws.send(json.dumps({"id": mid[0], "method": method, "params": params}))
                while True:                    # події можуть перемішуватись з відповіддю
                    msg = json.loads(ws.recv(timeout=90))
                    if msg.get("id") == mid[0]:
                        if "error" in msg:
                            raise RuntimeError(f"{method}: {msg['error']}")
                        return msg.get("result", {})

            def wait_load(timeout_s: float = 30):
                end = time.time() + timeout_s
                while time.time() < end:
                    try:
                        msg = json.loads(ws.recv(timeout=max(0.1, end - time.time())))
                    except Exception:
                        return
                    if msg.get("method") == "Page.loadEventFired":
                        return

            cmd("Page.enable")
            for kind, (w, h, mobile) in viewports.items():
                cmd("Emulation.setDeviceMetricsOverride",
                    width=w, height=min(h, 1000), deviceScaleFactor=1, mobile=mobile)
                cmd("Page.navigate", url=url)
                wait_load()
                time.sleep(1.5)               # шрифти, lazy-картинки, анімації появи
                metrics = cmd("Page.getLayoutMetrics")
                content = metrics.get("cssContentSize") or metrics.get("contentSize") or {}
                ch = int(content.get("height") or h)
                shot = cmd("Page.captureScreenshot", format="png",
                           captureBeyondViewport=True,
                           clip={"x": 0, "y": 0, "width": w,
                                 "height": min(ch, h), "scale": 1})
                out[kind] = base64.b64decode(shot["data"])
        return out
    finally:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass


def screenshot(branch: str) -> dict:
    """Піднімає php-деплой вітки, знімає головну у двох в'юпортах
    (desktop + mobile з мобільною емуляцією), гасить деплой (якщо не був
    запущений до того)."""
    browser = _browser_bin()
    screens_root().mkdir(parents=True, exist_ok=True)
    keep = is_running(branch)
    d = deploy(branch, wait=True)              # чекаємо nuxt-білд, потрібен URL
    files = {}
    try:
        time.sleep(1.0)                       # php-серверу треба мить на старт
        shots = _cdp_shots(browser, d["url"], VIEWPORTS)
        for kind, png in shots.items():
            out = screenshot_path(branch, kind)
            out.write_bytes(png)
            files[kind] = out.name
    finally:
        if not keep:
            stop(branch)
    if not files:
        raise RuntimeError("браузер не створив жодного скріншота")
    return {"branch": branch, "files": files}


def screenshot_path(branch: str, kind: str = "desktop") -> Path:
    p = screens_root() / f"{_safe_deploy_name(branch)}__{kind}.png"
    if kind == "desktop" and not p.exists():
        legacy = screens_root() / (_safe_deploy_name(branch) + ".png")
        if legacy.exists():                   # скріни зі старої версії
            return legacy
    return p


def delete_screens(branch: str) -> list[str]:
    """Видаляє всі PNG-скріни вітки (desktop + mobile + legacy)."""
    stem = _safe_deploy_name(branch)
    removed = []
    for name in (f"{stem}__desktop.png", f"{stem}__mobile.png", f"{stem}.png"):
        p = screens_root() / name
        if p.exists():
            p.unlink()
            removed.append(name)
    return removed


def list_screens() -> list[dict]:
    if not screens_root().exists():
        return []
    out: dict[str, dict] = {}
    for p in screens_root().glob("*.png"):
        stem, kind = p.stem, "desktop"
        if stem.endswith("__mobile"):
            stem, kind = stem[:-8], "mobile"
        elif stem.endswith("__desktop"):
            stem = stem[:-9]
        br = stem.replace("__", "/")
        out.setdefault(br, {"branch": br})[kind] = p.stat().st_mtime
    return sorted(out.values(), key=lambda x: x["branch"])


def list_deploys() -> list[dict]:
    """Запущені деплої АКТИВНОГО проєкту."""
    prefix = f"{projects.current_id()}::"
    out = []
    for key, info in list(_running.items()):
        if info["proc"].poll() is not None:      # died on its own
            _running.pop(key)
            continue
        if not key.startswith(prefix):
            continue
        out.append({"branch": key[len(prefix):], "port": info["port"],
                    "url": _url(info["port"])})
    return out
