"""Прев'ю вітки на окремому піддомені: одна тимчасова сесія за раз.

Навіщо. `php -S` піднімається на лупбеку ВСЕРЕДИНІ контейнера, а лаба
показувала цей самий `http://127.0.0.1:<порт>/` користувачу в браузер. Прод не
публікує жодного порту (назовні лише Traefik на 8030), тож лінк вів на власну
машину користувача: зсередини контейнера 200, з хоста — connection refused.
Скріни/Візуальні/Lighthouse ходять на той URL із сервера, тому вони працюють;
ламалась рівно кнопка «подивитись руками».

Рішення — другий хост на ТОЙ САМИЙ контейнер. Лаба розводить запити за
заголовком `Host`, і на прев'ю-хості не існує жодного маршруту лаби: там живе
тільки проксі до php -S поточної сесії.

Чому окремий хост, а не шлях `/deploy/<вітка>/` у лаби: вайт мусить сидіти
В КОРЕНІ, інакше root-relative ассети (`/_nuxt/…`, `/assets/…`) ведуть повз
префікс. Nuxt збирається саме такими шляхами, тож path-проксі тут — пастка.

Сесія — ОДНА НА ЛЮДИНУ, а не одна на всіх (з 21.09.2026). Доти слот був один:
прев'ю колеги витісняло твоє і ще й гасило його деплой — «люди заважають одне
одному» з задачі того дня. Піддомен той самий: сесії розрізняє host-only кука,
а в кожного браузера вона своя. Наступне прев'ю ТІЄЇ Ж людини витісняє її
попереднє (старий токен одразу мертвий); чужі сесії не чіпаються. Стеля —
`PREVIEW_MAX`: коли слоти зайняті, нова людина отримує відмову, а не виганяє
колегу.

Вимикається порожнім `PREVIEW_HOST`: це і є єдиний вимикач. Свідомо НЕ в
`app.FEATURES` — та таблиця означає «вирізано з прода», а тут навпаки: фіча
працює лише там, де їй задали хост.
"""

from __future__ import annotations

import hmac
import os
import secrets
import socket
import threading
import time

import projects

# Скільки живе прев'ю. Десять хвилин — щоб встигнути поклацати, але щоб
# забутий деплой не тримав порт і процес до вечора.
TTL_S = 600

# Скільки живе одноразовий токен передачі. Рівно на один перехід: він світиться
# в URL, тобто в логах Traefik і в історії браузера, і нічого більше з ним
# зробити не можна.
HANDOFF_S = 60

COOKIE = "wplab_preview"

# Заголовки, які не можна прокидати далі (RFC 7230 §6.1).
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
})

# Сесії за власником (uid людини; "" — без людини). Під локом, бо сесію
# відкриває запит лаби, а читає проксі прев'ю-хоста з іншого потоку.
_slots: dict[str, dict] = {}
_lock = threading.Lock()

# Гасіння деплою при закритті сесії живе в app.py (там deployer і журнал),
# тож впорскується явно — той самий патерн, що в ai_bridge.wire().
_on_close = None


def wire(on_close=None):
    global _on_close
    _on_close = on_close


class PreviewBusy(Exception):
    """Усі слоти прев'ю зайняті людьми — нову сесію не відкриваємо."""


# ---------------------------------------------------------------- налаштування

def host() -> str:
    return os.getenv("PREVIEW_HOST", "").strip().lower()


def enabled() -> bool:
    return bool(host())


def max_sessions() -> int:
    """Скільки людей дивляться прев'ю одночасно. Кожна сесія — живий php -S,
    а на node ще й зібраний dist, тож стеля потрібна; п'ять — з запасом на
    двох-трьох QA."""
    try:
        return max(1, int(os.getenv("PREVIEW_MAX", "").strip() or 5))
    except ValueError:
        return 5


def is_preview_host(value: str) -> bool:
    """`value` — заголовок Host як прийшов, можливо з портом."""
    h = host()
    return bool(h) and (value or "").split(":")[0].strip().lower() == h


def _secure() -> bool:
    return os.getenv("QA_LAB_COOKIE_SECURE", "").strip() == "1"


def base_url() -> str:
    return ("https://" if _secure() else "http://") + host()


# ---------------------------------------------------------------- сесії

def _same(a: str, b: str) -> bool:
    """Порівняння за сталий час для значень, що приходять ЗЗОВНІ.

    Через bytes, а не рядки: `hmac.compare_digest` на не-ASCII кидає
    TypeError, тобто токен з кирилицею давав би 500 замість чистої відмови.
    Спіймано тестом, не в проді.
    """
    try:
        return hmac.compare_digest(str(a).encode("utf-8"), str(b).encode("utf-8"))
    except Exception:
        return False


def _alive(slot: dict | None, now: float | None = None) -> bool:
    return bool(slot) and (now or time.time()) < slot["until"]


def _in_use(pid, branch, slots) -> bool:
    return any(x.get("pid") == pid and x["branch"] == branch for x in slots)


def _purge_locked() -> list[dict]:
    """Прибрати протухлі сесії. Повертає ті, чий деплой треба погасити."""
    now = time.time()
    dead = [k for k, v in _slots.items() if not _alive(v, now)]
    gone = [_slots.pop(k) for k in dead]
    return [g for g in gone
            if not _in_use(g.get("pid"), g["branch"], _slots.values())]


def _fire_close(slot: dict | None):
    """Погасити деплой сесії — у ЇЇ проєкті.

    Гасить не той, хто відкривав: сесію витісняє або прибирає по TTL чужий
    запит, а ключ деплою рахується від проєкту поточного контексту. З проєктом
    на людину це давало б `deployer.stop()` не в тому проєкті — vue-деплой
    лишався б жити сиротою, поки не перезапустять процес.

    Викликач уже переконався, що деплоєм не користується ЖОДНА інша жива
    сесія: та сама вітка у двох людей — один деплой."""
    if slot and _on_close:
        try:
            pid = slot.get("pid")
            if pid and projects.has(pid):
                with projects.use(pid):
                    _on_close(slot["branch"])
            else:                     # проєкт прибрали з реєстру — як було
                _on_close(slot["branch"])
        except Exception:
            pass                      # гасіння деплою не має валити запит


def _fire_all(slots: list[dict]):
    for x in slots:
        _fire_close(x)


def current(uid: str = "") -> dict | None:
    """Жива сесія цієї людини або None. Протухлі прибираємо тут же."""
    with _lock:
        gone = _purge_locked()
        s = _slots.get(uid)
        got = dict(s) if s else None
    _fire_all(gone)
    return got


def check_capacity(uid: str = "") -> None:
    """Кинути `PreviewBusy`, якщо ця людина не отримає сесії.

    Питаємо ДО деплою: інакше при зайнятих слотах лаба піднімала б вітку
    (на node — з білдом) лише для того, щоб відмовити."""
    with _lock:
        gone = _purge_locked()
        full = uid not in _slots and len(_slots) >= max_sessions()
        soonest = min((v["until"] for v in _slots.values()), default=0)
    _fire_all(gone)
    if full:
        mins = max(1, int((soonest - time.time()) // 60) + 1)
        raise PreviewBusy(
            f"зараз відкрито {max_sessions()} прев'ю — найближче звільниться "
            f"за {mins} хв (або хтось закриє своє)")


def open_session(branch: str, port: int, uid: str = "") -> dict:
    """Створює сесію людини, витісняючи лише ЇЇ попередню. Повертає посилання."""
    check_capacity(uid)
    now = time.time()
    slot = {
        "branch": branch, "port": int(port), "uid": uid,
        "pid": projects.current_id(),            # у якому проєкті гасити деплой
        "token": secrets.token_urlsafe(32),      # одноразовий, HANDOFF_S
        "token_until": now + HANDOFF_S,
        "sid": secrets.token_urlsafe(32),        # значення куки, TTL_S
        "until": now + TTL_S,
        "started": now,
    }
    with _lock:
        if uid not in _slots and len(_slots) >= max_sessions():
            raise PreviewBusy(f"зараз відкрито {max_sessions()} прев'ю — спробуй за хвилину")
        old, _slots[uid] = _slots.get(uid), slot
        stop = (old if old and not _in_use(old.get("pid"), old["branch"],
                                           _slots.values()) else None)
    _fire_close(stop)                  # ту саму вітку не гасимо — вона ж і піднята
    return public(slot, with_url=True)


def close(uid: str = "") -> bool:
    """Закрити сесію ЦІЄЇ людини."""
    with _lock:
        old = _slots.pop(uid, None)
        stop = (old if old and not _in_use(old.get("pid"), old["branch"],
                                           _slots.values()) else None)
    if not old:
        return False
    _fire_close(stop)
    return True


def close_sid(sid: str) -> bool:
    """Закрити сесію, якій належить кука (протухла сесія на прев'ю-хості)."""
    with _lock:
        owner = next((k for k, v in _slots.items()
                      if sid and _same(v.get("sid", ""), sid)), None)
    return close(owner) if owner is not None else False


def close_all() -> None:
    """Закрити всі сесії (зупинка процесу, тести)."""
    with _lock:
        gone = list(_slots.values())
        _slots.clear()
    seen = set()
    for x in gone:
        key = (x.get("pid"), x["branch"])
        if key not in seen:
            seen.add(key)
            _fire_close(x)


def extend(uid: str = "") -> dict | None:
    """Продовжити живу сесію цієї людини ще на TTL_S (кнопка «продовжити»)."""
    with _lock:
        s = _slots.get(uid)
        if not _alive(s):
            return None
        s["until"] = time.time() + TTL_S
        return public(s)


def public(slot: dict | None = None, with_url: bool = False,
           uid: str = "") -> dict | None:
    """Те, що можна віддати назовні: без token і sid."""
    s = slot if slot is not None else current(uid)
    if not s:
        return None
    out = {"branch": s["branch"], "left": max(0, int(s["until"] - time.time()))}
    if with_url:
        out["url"] = f"{base_url()}/__open?k={s['token']}"
    return out


def redeem(token: str) -> str | None:
    """Обмін одноразового токена на значення куки. Токен згорає тут же."""
    if not token:
        return None
    with _lock:
        now = time.time()
        for s in _slots.values():
            if not _alive(s, now) or s.get("token") is None:
                continue
            if now > s["token_until"]:
                continue
            # constant-time: токен приходить ззовні
            if _same(s["token"], token):
                s["token"] = None          # одноразовість
                return s["sid"]
    return None


def session_for(sid: str) -> dict | None:
    """Сесія, якій належить кука. None — куки немає, чужа або протухла."""
    if not sid:
        return None
    with _lock:
        for s in _slots.values():
            if s.get("sid") and _same(s["sid"], sid):
                return dict(s) if _alive(s) else None
    return None


def has_expired_cookie(sid: str) -> bool:
    """Кука ВІД сесії, яка ще лежить, але час вийшов — щоб сказати 410, а не 404."""
    if not sid:
        return False
    with _lock:
        return any(s.get("sid") and _same(s["sid"], sid) and not _alive(s)
                   for s in _slots.values())


# ---------------------------------------------------------------- проксі

def wait_ready(port: int, timeout: float = 12.0) -> bool:
    """Чекає, поки php -S справді почне слухати.

    `deployer._serve()` віддає порт одразу після `Popen`, а процес ще стартує.
    Скріни обходять це `sleep(1.0)` наосліп; для прев'ю так не можна — ми
    видаємо людині посилання, і якщо воно відкриється на 200 мс раніше, ніж
    php встигне зайняти сокет, вона побачить 502 замість вайта. Спіймано на
    першому ж наскрізному прогоні 25.08.
    """
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.4)
            try:
                s.connect(("127.0.0.1", int(port)))
                return True
            except OSError:
                pass
        time.sleep(0.15)
    return False


def strip_domain(set_cookie: str) -> str:
    """Зрізає `Domain=` з Set-Cookie вайта.

    Не теорія: `example.com` немає в Public Suffix List, тож вайт міг би
    поставити куку на батьківський домен, і браузер носив би її на сусідні
    застосунки компанії (parser-ui.example.com тощо). Без атрибута
    кука лишається host-only, тобто живе тільки на прев'ю-хості.
    """
    keep = [p for p in set_cookie.split(";")
            if p.strip().split("=")[0].strip().lower() != "domain"]
    return ";".join(keep)


def request_headers(incoming, target_host: str) -> dict:
    """Заголовки для php -S: без hop-by-hop, без наших секретів.

    * `Authorization` не прокидаємо — це BasicAuth лаби, вайту він ні до чого;
    * `Accept-Encoding` знімаємо, щоб вайт не віддав gzip: тіло ми стрімимо
      як є, і подвійне кодування зламало б відповідь;
    * `If-Modified-Since`/`If-None-Match` ріжемо: кеш на прев'ю заборонений
      (див. response_headers), а отруєний ДО заборони кеш браузера шле
      conditional — 304 від вайта воскресив би стару картинку чужої вітки;
    * `Host` ставимо прев'юшний, а не 127.0.0.1 — інакше вайти, що будують
      абсолютні лінки з $_SERVER['HTTP_HOST'], вели б на лупбек;
    * свою куку вирізаємо: у PHP вайта їй робити нічого.
    """
    out = {}
    for k, v in incoming.items():
        low = k.lower()
        if low in HOP_BY_HOP or low in ("host", "authorization", "accept-encoding",
                                        "content-length", "if-modified-since",
                                        "if-none-match"):
            continue
        if low == "cookie":
            v = _drop_own_cookie(v)
            if not v:
                continue
        out[k] = v
    out["Host"] = target_host
    out["X-Forwarded-Proto"] = "https" if _secure() else "http"
    out["X-Forwarded-Host"] = target_host
    return out


def _drop_own_cookie(header: str) -> str:
    keep = [c for c in header.split(";")
            if c.strip().split("=")[0].strip() != COOKIE]
    return "; ".join(p.strip() for p in keep if p.strip())


def response_headers(incoming) -> list[tuple[str, str]]:
    """Заголовки назад у браузер: без hop-by-hop, з обрізаним Domain,
    і БЕЗ кешу взагалі.

    `Content-Length` знімаємо свідомо — тіло йде стрімом, і чуже число тут
    зробило б відповідь битою.

    Кеш ріжеться з причини: прев'ю-хост ОДИН на всі вітки, а шляхи картинок
    у вітках партії однакові (images/ph-02.jpg). php -S шле Last-Modified,
    браузер евристично кешує — і після перемикання вітки показує фото
    ПОПЕРЕДНЬОЇ (02.10, пул ca-en). Validators (ETag/Last-Modified) теж
    зрізаються: інакше conditional запит отримає 304 і браузер лишить стару
    копію в кеші назавжди.

    Приймає і мапу, і послідовність пар. Пари потрібні для `Set-Cookie`:
    вайт може поставити кілька, а `requests.Response.headers` склеює їх в один
    рядок через кому — тобто app.py передає сюди `r.raw.headers.items()`.
    """
    out = []
    pairs = incoming.items() if hasattr(incoming, "items") else incoming
    for k, v in pairs:
        low = k.lower()
        if low in HOP_BY_HOP or low in ("content-length", "content-encoding",
                                        "cache-control", "expires", "etag",
                                        "last-modified"):
            continue
        if low == "set-cookie":
            v = strip_domain(v)
        out.append((k, v))
    out.append(("Cache-Control", "no-store"))
    return out
