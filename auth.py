"""Сесія: підписана кука і визначення поточного користувача.

Кука — не JWT: підпис HMAC-SHA256 стандартною бібліотекою робить те саме,
не тягнучи залежності. Вміст навмисно мінімальний — id користувача і час
видачі; усе решта (ім'я, права, активність) читається зі сховища.

Чому не «все в куці»: вимкнений адміном акаунт має вилітати ОДРАЗУ, а не
коли протухне кука. Тому активність звіряється при кожному запиті, а щоб не
довбати Mongo сотнями звернень (UI шле їх пачками), поверх стоїть TTL-кеш
на кілька секунд.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

import projects
import users

COOKIE_NAME = "wplab_session"

# Скільки живе кука. Тиждень — компроміс: не логінитись щодня, але й не
# лишати вкрадену куку робочою місяцями.
MAX_AGE = 7 * 24 * 3600

# Скільки секунд віримо кешу «користувач активний». Порядок величини
# підібраний так, щоб вимкнення акаунта спрацьовувало на очах у адміна.
_CACHE_TTL = 5.0

_cache: dict[str, tuple[float, dict | None]] = {}
_cache_lock = threading.Lock()


# --------------------------------------------------------------------------
# ключ підпису
# --------------------------------------------------------------------------
_secret: bytes | None = None
_secret_lock = threading.Lock()


def secret_key() -> bytes:
    """Ключ підпису куки.

    З `QA_LAB_SECRET_KEY`, якщо задано. Інакше генерується один раз і
    ЗБЕРІГАЄТЬСЯ у корені стану: якби він народжувався заново на кожен старт,
    будь-який рестарт розлогінював би всіх — а в контейнері рестарт буває на
    кожен деплой.
    """
    global _secret
    if _secret is not None:
        return _secret
    with _secret_lock:
        if _secret is not None:
            return _secret
        env = os.getenv("QA_LAB_SECRET_KEY", "").strip()
        if env:
            _secret = env.encode("utf-8")
            return _secret
        path = projects.state_root() / ".session_secret"
        try:
            if path.exists():
                raw = path.read_text(encoding="utf-8").strip()
                if raw:
                    _secret = raw.encode("utf-8")
                    return _secret
            raw = secrets.token_urlsafe(48)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw, encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass                      # Windows — ігноруємо
            _secret = raw.encode("utf-8")
        except Exception:
            # Диск недоступний — працюємо з ключем у пам'яті. Сесії не
            # переживуть рестарт, але сервіс лишається робочим.
            _secret = secrets.token_urlsafe(48).encode("utf-8")
        return _secret


def reset_secret_for_tests() -> None:
    global _secret
    _secret = None


# --------------------------------------------------------------------------
# кука
# --------------------------------------------------------------------------
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(uid: str) -> str:
    """`<payload_b64>.<signature_b64>`"""
    payload = json.dumps({"uid": str(uid), "iat": int(time.time())},
                         separators=(",", ":")).encode("utf-8")
    body = _b64(payload)
    sig = hmac.new(secret_key(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def read_token(token: str | None) -> str | None:
    """Повертає uid, якщо підпис валідний і кука не протухла."""
    if not token or "." not in token:
        return None
    body, _, sig = token.partition(".")
    expected = hmac.new(secret_key(), body.encode("ascii"), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expected, _unb64(sig)):
            return None
        data = json.loads(_unb64(body))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    iat = data.get("iat")
    if not isinstance(iat, int) or time.time() - iat > MAX_AGE:
        return None
    uid = data.get("uid")
    return str(uid) if uid else None


def set_cookie(response, uid: str, secure: bool | None = None) -> None:
    """SameSite=Lax обов'язково: Slack повертає користувача НАВІГАЦІЄЮ з
    чужого домену, і при Strict кука на тому переході не поїхала б —
    людина потрапляла б назад на екран входу."""
    if secure is None:
        secure = os.getenv("QA_LAB_COOKIE_SECURE", "").strip() == "1"
    response.set_cookie(
        COOKIE_NAME, make_token(uid),
        max_age=MAX_AGE, httponly=True, samesite="lax",
        secure=secure, path="/",
    )


def clear_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


# --------------------------------------------------------------------------
# поточний користувач
# --------------------------------------------------------------------------
def _load(uid: str) -> dict | None:
    row = users.store().get(uid)
    if row is None:
        return None
    if row.get("is_active", True) is False:
        return None
    return row


def user_by_uid(uid: str) -> dict | None:
    """Запис користувача з коротким TTL-кешем."""
    now = time.time()
    with _cache_lock:
        hit = _cache.get(uid)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]
    row = _load(uid)
    with _cache_lock:
        _cache[uid] = (now, row)
    return row


def invalidate(uid: str | None = None) -> None:
    """Скидання кешу — після зміни пароля, прав чи активності."""
    with _cache_lock:
        if uid is None:
            _cache.clear()
        else:
            _cache.pop(str(uid), None)


def current_user(request) -> dict | None:
    uid = read_token(request.cookies.get(COOKIE_NAME))
    return user_by_uid(uid) if uid else None


def is_admin(row: dict | None) -> bool:
    return bool(row and row.get("is_admin"))


def uid_of(row: dict) -> str:
    return str(row.get("_id") or row.get("id") or "")


# --------------------------------------------------------------------------
# що дозволено без сесії
# --------------------------------------------------------------------------
# Рівно те, без чого неможливо ЗАЙТИ, плюс health для оркестратора.
# Усе інше закриває middleware — саме тому список короткий і лежить поруч
# з ним: 142 ендпоінти неможливо перебрати очима, а цей перелік можна.
# Свідомо БЕЗ префіксів на кшталт "/static/": екран входу самодостатній
# (стилі всередині файлу), а відкритий префікс — це заготовка для дірки,
# щойно хтось змонтує туди щось справжнє.
# `/i18n.js` і `/i18n-dict.js` публічні свідомо: екран входу теж має
# малюватись мовою, яку людина обрала, а він єдина сторінка без сесії. У
# файлах немає даних — лише фрази інтерфейсу; ціна рішення в тому, що
# термінологію лаби видно без входу.
PUBLIC_PATHS = frozenset({
    "/login",
    "/i18n.js",
    "/i18n-dict.js",
    "/api/health",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
    "/api/auth/slack/start",
    "/api/auth/slack/callback",
    "/favicon.ico",
})


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS


# --------------------------------------------------------------------------
# машинний доступ (ШІ-міст)
# --------------------------------------------------------------------------
# З того боку конвеєра стоїть інший застосунок, а не людина: куки в нього
# немає і бути не може. Тому — bearer-токен.
#
# Три рішення, які тут важливі:
#
# 1. Токен НЕ додає шляхи в `PUBLIC_PATHS`. Публічний шлях — це шлях без
#    авторизації взагалі; нам потрібен інший користувач, а не її відсутність.
#    Без токена міст віддає ті самі 401, і тест-підмітальник по всіх
#    GET-маршрутах лишається зеленим.
#
# 2. Токен діє ЛИШЕ на `/api/ai/*`. Якби він автентифікував скрізь, його
#    витік давав би повний доступ до лаби — включно з комітами в будь-яку
#    вітку і правкою користувачів. Машині потрібен рівно її кут.
#
# 3. Службовий запис НЕ підписує дії актором. Фічу «один токен + підпис
#    актора» знесено 18.08 рішенням замовника; тут токен — рівно
#    авторизація машини, а в журналі дії мосту видно за `action`.
BRIDGE_PREFIX = "/api/ai/"

# Коротший токен приймати відмовляємось: 16 символів це не секрет, а
# запрошення перебрати. Мовчазне «не працює» тут гірше за явну відмову,
# тому причина друкується у лог при першій же спробі.
MIN_BRIDGE_TOKEN = 24


def bridge_token() -> str:
    return os.getenv("QA_LAB_BRIDGE_TOKEN", "").strip()


def is_bridge_path(path: str) -> bool:
    return path == BRIDGE_PREFIX.rstrip("/") or path.startswith(BRIDGE_PREFIX)


SERVICE_USER = {
    "_id": "service:ai-bridge",
    "login": "ai-bridge",
    "name": "ШІ-міст",
    "is_admin": False,
    "is_active": True,
    "is_service": True,
}


def service_user(request) -> dict | None:
    """Машина за валідним bearer-токеном — або None.

    Порівняння `compare_digest`: звичайне `==` на рядках виходить із циклу
    на першому розбіжному байті, і за часом відповіді токен добирається
    посимвольно.
    """
    if not is_bridge_path(request.url.path):
        return None
    tok = bridge_token()
    if len(tok) < MIN_BRIDGE_TOKEN:
        return None
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    given = header[7:].strip()
    if not hmac.compare_digest(given, tok):
        return None
    return dict(SERVICE_USER)


def is_service(row: dict | None) -> bool:
    return bool(row and row.get("is_service"))


# --------------------------------------------------------------------------
# машинний вхід №2: вебхук ClickUp
# --------------------------------------------------------------------------
# Тут інша природа автентифікації, ніж у мосту: заголовка з нашим токеном не
# буде — ClickUp шле СВІЙ підпис тіла ключем, який видав при реєстрації
# вебхука. Тому шлях рівно один, він не публічний, і пускає далі не наявність
# заголовка, а `verify_hook()` в самому ендпоінті: тільки він тримає сире
# тіло. Читати тіло в middleware не можна — BaseHTTPMiddleware вичерпує потік,
# і ендпоінт отримав би порожній запит.
HOOK_PATH = "/api/hook/clickup"

# Актор для підпису. Позначаємо машиною, але писати цим користувачем нікуди
# не можна: вебхук лише кладе `task_id` у чергу.
HOOK_USER = {
    "_id": "service:cu-hook",
    "login": "clickup-hook",
    "name": "Вебхук ClickUp",
    "is_admin": False,
    "is_active": True,
    "is_service": True,
}


def hook_secret() -> str:
    """Ключ підпису: змінна оточення, інакше той, що лаба зареєструвала сама.

    Змінна перемагає навмисно. Якщо ключ заданий руками, `cu_hook` у ClickUp
    не лізе взагалі (ручний режим), тож двох джерел ключа не буває — а саме
    вони одного дня розійшлись би, і вебхук почав би віддавати 401 без
    жодної видимої причини.

    Імпорт пізній: `cu_hook` імпортує `auth` зверху файлу.
    """
    env = os.getenv("CLICKUP_WEBHOOK_SECRET", "").strip()
    if env:
        return env
    try:
        import cu_hook
        return cu_hook.secret()
    except Exception:
        return ""


def is_hook_path(path: str) -> bool:
    return path == HOOK_PATH


def verify_hook(raw: bytes, signature: str) -> bool:
    """HMAC-SHA256 сирого тіла ключем з реєстрації вебхука.

    Без ключа — `False` на все: незаданий секрет означає «двері зачинені», а
    не «пускаємо всіх». Порівняння `compare_digest` з тієї ж причини, що й у
    мосту: звичайне `==` виходить із циклу на першому розбіжному байті.
    """
    secret = hook_secret()
    if not secret or not signature:
        return False
    want = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, signature.strip())


# --------------------------------------------------------------------------
# ліміт спроб входу
# --------------------------------------------------------------------------
# Відколи BasicAuth перед лабою знято (26.08, див. docker-compose.prod.yml),
# форма входу — весь гейт між доменом і чужими руками. Без ліміту підбір
# упирається тільки в ціну scrypt.
#
# Ключ — ЛОГІН, а не IP, і це не лінощі. За Traefik і Cloudflare
# `request.client.host` — це адреса проксі: усі користувачі зливаються в один
# ключ, і ліміт по IP замкнув би вхід одразу всій команді. Справжня адреса
# приїжджає в `CF-Connecting-IP`, але це заголовок ЗЗОВНІ: варто лабі колись
# опинитись не за Cloudflare — і його підробить будь-хто.
#
# Плата за вибір: підбором чужого логіна можна тримати ЙОГО в очікуванні.
# Тому вікно коротке — хвилина, а не година: у найгіршому разі свій чекає
# 60 секунд, і це дешевше, ніж необмежений підбір.
MAX_FAILS = 10
FAIL_WINDOW_S = 60

# Стеля на кількість ключів: під час підбору логіни бувають випадкові, і без
# неї словник ріс би необмежено. Витісняємо найдавніший — він і найближчий
# до того, щоб протухнути самому.
MAX_FAIL_KEYS = 4096

_fails: dict[str, list[float]] = {}
_fails_lock = threading.Lock()


def _prune(now: float) -> None:
    """Викидає ключі, у яких у вікні не лишилось жодної спроби. Під локом."""
    for key in [k for k, v in _fails.items() if not v or v[-1] <= now - FAIL_WINDOW_S]:
        _fails.pop(key, None)
    while len(_fails) > MAX_FAIL_KEYS:
        _fails.pop(min(_fails, key=lambda k: _fails[k][-1]), None)


def login_retry_after(login: str, now: float | None = None) -> int:
    """Скільки секунд чекати цьому логіну. 0 — можна пробувати."""
    now = now or time.time()
    key = users.norm_login(login)
    with _fails_lock:
        hits = [t for t in _fails.get(key, []) if t > now - FAIL_WINDOW_S]
        if len(hits) < MAX_FAILS:
            return 0
        return max(1, int(hits[0] + FAIL_WINDOW_S - now) + 1)


def note_login_failure(login: str, now: float | None = None) -> None:
    now = now or time.time()
    key = users.norm_login(login)
    with _fails_lock:
        hits = [t for t in _fails.get(key, []) if t > now - FAIL_WINDOW_S]
        hits.append(now)
        _fails[key] = hits[-MAX_FAILS:]
        _prune(now)


def clear_login_failures(login: str) -> None:
    """Успішний вхід стирає лічильник: свій, хто врешті згадав пароль, не має
    доганяти чужі невдалі спроби."""
    with _fails_lock:
        _fails.pop(users.norm_login(login), None)
