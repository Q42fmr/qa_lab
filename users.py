"""Користувачі лаби: сховище і паролі.

Два бекенди за одним інтерфейсом:

  * **MongoDB** — коли задано `MONGO_URI`. Та сама база, що вже стоїть у
    кластері й до якої ходять сусідні проєкти;
  * **файл** `users.json` у корені стану — коли `MONGO_URI` порожній.

Файловий потрібен не «про всяк випадок»: розробник запускає лабу нативно на
своїй машині, і вимагати від нього піднятої Mongo означало б зламати щоденний
цикл. Той самий принцип, що з `QA_LAB_STATE_DIR` — дефолт нічого не змінює.

Пароль хешується `hashlib.scrypt` зі стандартної бібліотеки: bcrypt і argon2
тягнуть залежності, а тут вистачає стдліба.

Права: усі однакові, крім `is_admin` — рівно однієї учетки.
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
from pathlib import Path

import db
import projects

# --------------------------------------------------------------------------
# пароль
# --------------------------------------------------------------------------
# Параметри scrypt: n=2^14 — приблизно 100 мс на сучасному CPU. Це навмисно
# повільно (захист від перебору) і водночас непомітно на одному вході.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32


def hash_password(password: str) -> str:
    """`scrypt$n$r$p$<salt>$<hash>`, обидва блоки — base64 без padding."""
    if not password:
        raise ValueError("порожній пароль")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN)
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _b64(salt), _b64(dk))


def verify_password(password: str, stored: str | None) -> bool:
    """Перевірка. Порівняння — `compare_digest`, щоб час відповіді не залежав
    від того, на якому байті хеші розійшлись."""
    if not password or not stored:
        return False
    try:
        kind, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if kind != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt_b64),
                            n=int(n), r=int(r), p=int(p),
                            dklen=len(_unb64(hash_b64)))
    except Exception:
        return False
    return hmac.compare_digest(dk, _unb64(hash_b64))


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --------------------------------------------------------------------------
# нормалізація запису
# --------------------------------------------------------------------------
# `bootstrap_fp` — відбиток значення ADMIN_PASSWORD, яке востаннє ЗАСТОСУВАЛИ
# до цієї учетки (див. `ensure_bootstrap_admin`). Обидва сховища фільтрують
# і `create`, і `update` по цьому кортежу, тож без нього поле просто не
# збереглося б.
# `clickup_token` — ОСОБИСТИЙ токен ClickUp, запечатаний `crypto_box`. Він
# тут, а не в оточенні, бо він у кожного свій: застосунковий акаунт не бачить
# тасок, розшарених людині персонально (заміряно 01.09.2026 — одна така
# таска у воркспейсі), і дістати їх можна лише з-під самої людини.
# `project` — обраний людиною проєкт (php/vue). Живе в записі, а не в процесі:
# доти вибір був один на сервер, і перемикання в одного перемикало всіх
# (задача 21.09.2026). Middleware читає його з того самого рядка, що й сесію,
# тож окремого читання на запит це не коштує.
FIELDS = ("login", "name", "password_hash", "slack_user_id", "slack_team_id",
          "email", "is_admin", "is_active", "created_at", "last_login_at",
          "bootstrap_fp", "clickup_token", "clickup_user", "clickup_checked_at",
          "clickup_error", "project")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def norm_login(login: str) -> str:
    """Логін порівнюється без урахування регістру й пробілів по краях —
    інакше «Nora» і «nora» стали б різними людьми."""
    return (login or "").strip().lower()


def _norm(doc: dict) -> dict:
    """Запис у вигляді, придатному для віддачі назовні (без хеша пароля)."""
    out = {k: doc.get(k) for k in FIELDS}
    out["id"] = str(doc.get("_id") or doc.get("id") or "")
    out["is_admin"] = bool(doc.get("is_admin"))
    out["is_active"] = doc.get("is_active", True) is not False
    out["has_password"] = bool(doc.get("password_hash"))
    out["has_clickup_token"] = bool(doc.get("clickup_token"))
    out.pop("password_hash", None)
    # Токен — секрет того ж роду, що й хеш пароля. `_norm` будується з FIELDS,
    # тож без цього рядка він поїхав би назовні через `/api/users` рівно тому,
    # що ми його туди додали, — і адмін бачив би чужі токени у відповіді API.
    out.pop("clickup_token", None)
    # Відбиток — службове поле того ж роду, що й хеш пароля: назовні йому
    # робити нічого. `_norm` будується з FIELDS, тому нове поле інакше
    # поїхало б у відповідь `/api/users` саме через те, що ми його додали.
    out.pop("bootstrap_fp", None)
    return out


# --------------------------------------------------------------------------
# сховище
# --------------------------------------------------------------------------
class UserStore:
    """Спільний інтерфейс обох бекендів.

    find_by_login / find_by_slack_id / get / list_all / create / update /
    touch_login. Повертають «сирі» документи (з `password_hash`), бо їх
    використовує перевірка пароля; назовні віддається `_norm()`.
    """

    def find_by_login(self, login: str) -> dict | None: raise NotImplementedError
    def find_by_slack_id(self, slack_id: str) -> dict | None: raise NotImplementedError
    def get(self, uid: str) -> dict | None: raise NotImplementedError
    def list_all(self) -> list[dict]: raise NotImplementedError
    def create(self, doc: dict) -> dict: raise NotImplementedError
    def update(self, uid: str, patch: dict) -> dict | None: raise NotImplementedError

    def touch_login(self, uid: str) -> None:
        self.update(uid, {"last_login_at": _now()})

    def count(self) -> int:
        return len(self.list_all())


class FileUserStore(UserStore):
    """`users.json` у корені стану. Один процес, тому вистачає локу в пам'яті
    і атомарного запису через .tmp + os.replace — так само, як решта стану."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    # -- внутрішнє --------------------------------------------------------
    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _write(self, rows: list[dict]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, self.path)

    # -- інтерфейс --------------------------------------------------------
    def find_by_login(self, login: str) -> dict | None:
        login = norm_login(login)
        return next((r for r in self._read() if norm_login(r.get("login", "")) == login), None)

    def find_by_slack_id(self, slack_id: str) -> dict | None:
        if not slack_id:
            return None
        return next((r for r in self._read() if r.get("slack_user_id") == slack_id), None)

    def get(self, uid: str) -> dict | None:
        return next((r for r in self._read() if str(r.get("id")) == str(uid)), None)

    def list_all(self) -> list[dict]:
        return sorted(self._read(), key=lambda r: norm_login(r.get("login", "")))

    def create(self, doc: dict) -> dict:
        with self._lock:
            rows = self._read()
            login = norm_login(doc.get("login", ""))
            if login and any(norm_login(r.get("login", "")) == login for r in rows):
                raise ValueError(f"логін уже зайнятий: {login}")
            sid = doc.get("slack_user_id")
            if sid and any(r.get("slack_user_id") == sid for r in rows):
                raise ValueError(f"slack_user_id уже прив'язаний: {sid}")
            row = {k: doc.get(k) for k in FIELDS}
            row["login"] = login
            row["id"] = secrets.token_hex(12)
            # НЕ setdefault: ключ уже є (зі значенням None), тож setdefault
            # промовчав би і дата створення лишалась порожньою.
            row["created_at"] = doc.get("created_at") or _now()
            row["is_active"] = doc.get("is_active", True) is not False
            row["is_admin"] = bool(doc.get("is_admin"))
            rows.append(row)
            self._write(rows)
            return row

    def update(self, uid: str, patch: dict) -> dict | None:
        with self._lock:
            rows = self._read()
            for row in rows:
                if str(row.get("id")) != str(uid):
                    continue
                for k, v in patch.items():
                    if k in FIELDS:
                        row[k] = norm_login(v) if k == "login" else v
                self._write(rows)
                return row
            return None


class MongoUserStore(UserStore):
    """Колекція в наявній Mongo кластера."""

    def __init__(self, uri: str, db_name: str, coll_name: str):
        from pymongo import ASCENDING
        # Клієнта будує db.py — ОДИН пул на процес для всіх споживачів бази
        # (тут і реєстр ШІ-моста). Раніше клієнт народжувався прямо тут, і
        # другий споживач неминуче завів би другий пул з власним таймаутом.
        # Там же живе `serverSelectionTimeoutMS`: без нього недоступна база
        # вішає запит на 30 с і виглядає як «лаба зависла», а не як «немає
        # Mongo».
        self.client = db.client_for(uri)
        self.coll = self.client[db_name][coll_name]
        # Розріджені унікальні індекси: користувач може не мати slack_user_id
        # (заведений руками) або логіна (теоретично), і null-и не мають
        # конфліктувати між собою.
        self.coll.create_index([("login", ASCENDING)], unique=True, sparse=True)
        self.coll.create_index([("slack_user_id", ASCENDING)], unique=True, sparse=True)

    @staticmethod
    def _oid(uid: str):
        from bson import ObjectId
        try:
            return ObjectId(uid)
        except Exception:
            return None

    def find_by_login(self, login: str) -> dict | None:
        return self.coll.find_one({"login": norm_login(login)})

    def find_by_slack_id(self, slack_id: str) -> dict | None:
        if not slack_id:
            return None
        return self.coll.find_one({"slack_user_id": slack_id})

    def get(self, uid: str) -> dict | None:
        oid = self._oid(uid)
        return self.coll.find_one({"_id": oid}) if oid else None

    def list_all(self) -> list[dict]:
        return list(self.coll.find().sort("login", 1))

    def create(self, doc: dict) -> dict:
        from pymongo.errors import DuplicateKeyError
        row = {k: doc.get(k) for k in FIELDS}
        row["login"] = norm_login(doc.get("login", ""))
        row["created_at"] = doc.get("created_at") or _now()
        row["is_active"] = doc.get("is_active", True) is not False
        row["is_admin"] = bool(doc.get("is_admin"))
        try:
            res = self.coll.insert_one(row)
        except DuplicateKeyError as e:
            raise ValueError(f"логін або slack_user_id уже зайняті: {e}") from e
        row["_id"] = res.inserted_id
        return row

    def update(self, uid: str, patch: dict) -> dict | None:
        oid = self._oid(uid)
        if not oid:
            return None
        clean = {k: (norm_login(v) if k == "login" else v)
                 for k, v in patch.items() if k in FIELDS}
        if not clean:
            return self.get(uid)
        return self.coll.find_one_and_update(
            {"_id": oid}, {"$set": clean}, return_document=True)


# --------------------------------------------------------------------------
# фабрика
# --------------------------------------------------------------------------
_store: UserStore | None = None
_store_lock = threading.Lock()


def store() -> UserStore:
    """Сховище користувачів. Обирається один раз за наявністю MONGO_URI."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = _build_store()
    return _store


def _build_store() -> UserStore:
    uri = os.getenv("MONGO_URI", "").strip()
    if not uri:
        return FileUserStore(projects.state_root() / "users.json")
    db = os.getenv("MONGO_DB", "qa_lab").strip() or "qa_lab"
    coll = os.getenv("MONGO_USERS_COLL", "users").strip() or "users"
    try:
        return MongoUserStore(uri, db, coll)
    except Exception as e:
        # Голосно і зрозуміло. Мовчазний фолбек на файл був би гірший за
        # падіння: адмін думав би, що користувачі в Mongo, а вони в контейнері.
        raise RuntimeError(
            f"MONGO_URI задано, але підключитись не вдалось: {e}. "
            f"Або полагодь доступ до Mongo, або прибери MONGO_URI, "
            f"щоб користувачі лежали у файлі."
        ) from e


def reset_store_for_tests(new: UserStore | None = None) -> None:
    """Тести підміняють сховище напряму — фабрика кешує його на процес."""
    global _store
    _store = new


# --------------------------------------------------------------------------
# операції рівня застосунку
# --------------------------------------------------------------------------
def authenticate(login: str, password: str) -> dict | None:
    """Логін+пароль. Повертає сирий запис або None.

    Хеш звіряється навіть для неіснуючого користувача — інакше час відповіді
    видавав би, які логіни існують.
    """
    row = store().find_by_login(login)
    ok = verify_password(password, (row or {}).get("password_hash"))
    if not row or not ok:
        return None
    if row.get("is_active", True) is False:
        return None
    return row


def _bootstrap_fp(password: str) -> str:
    """Відбиток значення ADMIN_PASSWORD — щоб упізнати, що воно змінилось.

    Відбиток рахується від значення, яке прийшло З ОТОЧЕННЯ, а не від
    поточного `password_hash`. Це і є вся суть: пароль можна змінити з UI, і
    тоді хеш у записі вже не має нічого спільного зі змінною — звіряй ми хеш,
    кожна така зміна читалась би як «розійшлось» і її затирало б наступним
    рестартом. Рівно так і було до 26.08.

    HMAC, а не голий sha256: інакше поруч зі scrypt-хешем у базі лежав би
    швидкий хеш того самого пароля, придатний для словникового підбору.
    Ключ — той самий, яким підписуються куки; він переживає рестарт (лежить
    у корені стану). Якщо його колись поміняють, відбитки перестануть
    збігатись і пароль один раз скинеться до значення з CI — не страшно:
    зміна цього ключа й так розлогінює геть усіх.
    """
    import auth              # ліниво: auth імпортує users, на рівні модуля це
    return hmac.new(auth.secret_key(),        # був би цикл
                    ("bootstrap:" + password).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def ensure_bootstrap_admin() -> dict | None:
    """Адмін з env — щоб завжди лишався вхід, навіть якщо Slack ліг.

    Пароль застосовується ЛИШЕ тоді, коли значення в оточенні відрізняється
    від того, яке до цієї учетки застосували минулого разу. Тобто:

      * змінив ADMIN_PASSWORD у CI і задеплоїв → пароль скинуто (це і є
        спосіб повернути доступ, коли не заходить ніхто);
      * змінив пароль у UI → він переживе будь-яку кількість рестартів, бо
        значення в CI лишилось те саме.

    До 26.08 хук переписував пароль на КОЖНОМУ старті — а старт буває не лише
    на деплої: `restart_policy: condition: any`, три невдалі healthcheck-и,
    переїзд таски на іншу ноду. Тому пароль, заданий у UI, зникав сам собою,
    і зрозуміти чому було нізвідки.

    Наслідок, про який варто знати: вимкнену або розжалувану учетку хук
    більше не «лікує» сам. Це та сама ціна — без неї учеткою неможливо
    керувати з UI. Повернути доступ = змінити ADMIN_PASSWORD і задеплоїти.

    Запис без відбитка (усі, що існували до цієї зміни) вважається
    незастосованим: пароль скинеться рівно один раз, відбиток запишеться, і
    далі учетка стане керованою з UI.
    """
    login = norm_login(os.getenv("ADMIN_LOGIN", "admin"))
    password = os.getenv("ADMIN_PASSWORD", "")
    if not login or not password:
        return None
    st = store()
    row = st.find_by_login(login)
    fp = _bootstrap_fp(password)
    if row is None:
        return st.create({
            "login": login,
            "name": os.getenv("ADMIN_NAME", "Administrator"),
            "password_hash": hash_password(password),
            "is_admin": True,
            "is_active": True,
            "bootstrap_fp": fp,
        })
    if row.get("bootstrap_fp") == fp:
        return row                     # у CI те саме значення — не чіпаємо
    uid = str(row.get("_id") or row.get("id") or "")
    return st.update(uid, {
        "password_hash": hash_password(password),
        "is_admin": True,
        "is_active": True,
        "bootstrap_fp": fp,
    })


def upsert_slack_user(slack_id: str, team_id: str, name: str = "",
                      email: str = "") -> dict:
    """Вхід через Slack: знайти або створити.

    Автостворення — свідоме рішення: будь-хто з нашого воркспейсу отримує
    акаунт. Чужий воркспейс відсікається раніше,
    перевіркою team_id у slack_oauth.
    """
    st = store()
    row = st.find_by_slack_id(slack_id)
    if row is not None:
        uid = str(row.get("_id") or row.get("id") or "")
        patch = {"slack_team_id": team_id}
        if name and not row.get("name"):
            patch["name"] = name
        if email and not row.get("email"):
            patch["email"] = email
        return st.update(uid, patch) or row

    # Логін виводимо з пошти або зі slack-id; за зайнятості додаємо суфікс.
    base = norm_login((email.split("@")[0] if email else "") or slack_id)
    login = base
    for n in range(2, 50):
        if st.find_by_login(login) is None:
            break
        login = f"{base}{n}"
    return st.create({
        "login": login,
        "name": name or login,
        "slack_user_id": slack_id,
        "slack_team_id": team_id,
        "email": email,
        "password_hash": None,          # задасть сам у кабінеті
        "is_admin": False,
        "is_active": True,
    })


def public(row: dict | None) -> dict | None:
    return _norm(row) if row else None


# --------------------------------------------------------------------------
# особистий токен ClickUp
# --------------------------------------------------------------------------
def store_clickup_token(uid: str, token: str, cu_user: str = "") -> dict | None:
    """Запечатати і покласти. `cu_user` — ім'я акаунта ClickUp, якому токен
    належить: воно потрібне, щоб кабінет міг сказати ЧИЙ це токен, не
    показуючи значення."""
    import crypto_box
    return store().update(uid, {
        "clickup_token": crypto_box.seal(token.strip()),
        "clickup_user": cu_user,
        "clickup_checked_at": _now(),
        "clickup_error": None,
    })


def clear_clickup_token(uid: str) -> dict | None:
    return store().update(uid, {"clickup_token": None, "clickup_user": None,
                                "clickup_checked_at": None, "clickup_error": None})


def note_clickup_error(uid: str, why: str) -> None:
    """Чому токен не спрацював — у запис, а не лише в тост.

    Тост живе шість секунд, а мертвий токен — тижнями: без цього рядка людина
    бачила б просто «тасок менше», і причини не було б ніде.
    """
    try:
        store().update(uid, {"clickup_error": (why or "")[:200]})
    except Exception:
        pass


def clickup_token_of(row: dict | None) -> str:
    """Розпечатаний токен або порожній рядок.

    Ключ сесій могли змінити — тоді значення не читається. Це не аварія:
    повертаємо порожньо, а кабінет попросить ввести токен ще раз.
    """
    import crypto_box
    sealed = (row or {}).get("clickup_token")
    if not sealed:
        return ""
    try:
        return crypto_box.unseal(sealed)
    except ValueError:
        return ""
