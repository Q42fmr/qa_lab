"""Тести спільного підключення до БД (`db.py`).

Файл влаштований так, щоб **гейт лишався герметичним**. Обов'язкова частина
не торкається мережі взагалі: вона перевіряє те, що й має перевірятись
завжди — «без MONGO_URI бази немає і це штатно» та «з битим MONGO_URI
падаємо голосно, а не тихо з'їжджаємо на файли».

Частина з живою базою РЕЄСТРУЄТЬСЯ ЛИШЕ тоді, коли база справді відповідає:
локально її піднімає `docker-compose.dev.yml`, а в `docker run` (як гейт
ганяється в CI) мережі compose немає — і тоді цих тестів просто не існує,
замість того щоб падати чи мовчки «проходити».

Саме тут закривається дірка, чесно названа в `test_users_store.py`:
mongo-бекенд користувачів має той самий інтерфейс, що файловий, але досі
не ганявся ЖОДНОГО разу.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import db                                                         # noqa: E402
import users                                                      # noqa: E402

# Куди дивитись у пошуках живої бази. Перший, що відповів, — той і береться.
#   * MONGO_URI з оточення — коли тест ганяють з уже налаштованим .env;
#   * `mongo:27017` — зсередини мережі compose (`compose run qa_lab ...`);
#   * петля — нативний запуск поруч із піднятим compose (порт проброшено).
CANDIDATES = [
    os.getenv("MONGO_URI", "").strip(),
    "mongodb://qa_lab:qa_lab@mongo:27017/?authSource=admin",
    "mongodb://qa_lab:qa_lab@127.0.0.1:27017/?authSource=admin",
]

# Пошук живої бази має бути ШВИДКИМ: три кандидати по 5 с дефолтного
# таймауту — це 15 с на старті гейта там, де бази просто немає.
PROBE_MS = 700


def _live_uri() -> str:
    was = db.SERVER_SELECTION_MS
    db.SERVER_SELECTION_MS = PROBE_MS
    try:
        for uri in CANDIDATES:
            if not uri:
                continue
            try:
                db.client_for(uri)
                return uri
            except Exception:
                continue
        return ""
    finally:
        db.SERVER_SELECTION_MS = was
        db.reset_for_tests()


class _env:
    """MONGO_URI на час одного тесту; кеш клієнтів скидається з обох боків."""

    def __init__(self, uri: str = "", dbname: str = ""):
        self.uri, self.dbname = uri, dbname

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in ("MONGO_URI", "MONGO_DB")}
        os.environ["MONGO_URI"] = self.uri
        if self.dbname:
            os.environ["MONGO_DB"] = self.dbname
        db.reset_for_tests()
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        db.reset_for_tests()
        return False


# ------------------------------------------------- без бази (завжди ганяється)

def test_without_uri_there_is_no_database_and_it_is_normal():
    """Порожній MONGO_URI — це РОБОЧИЙ режим, а не помилка: так лаба живе
    нативно і так вона працювала до появи БД взагалі."""
    with _env(""):
        assert db.enabled() is False
        assert db.client() is None
        assert db.database() is None
        assert db.collection("ai_requests") is None


def test_ping_says_disabled_instead_of_pretending_to_be_ok():
    with _env(""):
        p = db.ping()
        assert p["enabled"] is False and p["ok"] is False
        assert "MONGO_URI" in p["reason"]


def test_db_name_has_a_default():
    """Забути MONGO_DB легко; без дефолта колекції поїхали б у базу з
    порожньою назвою, і знайти їх було б нічим."""
    saved = os.environ.pop("MONGO_DB", None)
    try:
        assert db.db_name() == "qa_lab"
        os.environ["MONGO_DB"] = "   "
        assert db.db_name() == "qa_lab", "пробіли — це теж «не задано»"
    finally:
        if saved is None:
            os.environ.pop("MONGO_DB", None)
        else:
            os.environ["MONGO_DB"] = saved


def test_dead_database_fails_loudly_and_names_the_variable():
    """Головна вимога до контракту: тихий фолбек на файли ЗАБОРОНЕНИЙ.
    Інакше адмін вважає, що дані в базі, а вони в контейнері, який зникне
    з наступним деплоєм. Помилка мусить називати змінну, щоб було зрозуміло,
    що саме крутити."""
    was = db.SERVER_SELECTION_MS
    db.SERVER_SELECTION_MS = 300          # порт 1 не слухає ніхто
    try:
        with _env("mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=300"):
            try:
                db.client()
            except RuntimeError as e:
                assert "MONGO_URI" in str(e)
            else:
                raise AssertionError("мертва база мусила впасти голосно")
    finally:
        db.SERVER_SELECTION_MS = was


def test_ping_never_raises_even_on_a_dead_database():
    """`ping()` кличуть зі сторінок статусу: виняток там перетворив би
    «Mongo моргнула» на «сторінка впала»."""
    was = db.SERVER_SELECTION_MS
    db.SERVER_SELECTION_MS = 300
    try:
        with _env("mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=300"):
            p = db.ping()
            assert p["enabled"] is True and p["ok"] is False and p["error"]
    finally:
        db.SERVER_SELECTION_MS = was


def test_empty_uri_is_rejected_by_client_for():
    try:
        db.client_for("   ")
    except ValueError:
        pass
    else:
        raise AssertionError("порожній рядок підключення мав бути відхилений")


# ------------------------------------------------- з живою базою (умовно)

LIVE = _live_uri()


def test_live_ping_is_ok():
    with _env(LIVE):
        p = db.ping()
        assert p["enabled"] and p["ok"], p


def test_live_one_client_per_uri():
    """Другий споживач бази не має заводити другий пул з'єднань — заради
    цього `db.py` і з'явився."""
    with _env(LIVE):
        assert db.client_for(LIVE) is db.client_for(LIVE)
        assert db.client() is db.client_for(LIVE)


def test_live_collection_roundtrip():
    """Те, що потрібно реєстру ШІ-моста: записати, знайти, прибрати."""
    name = f"selftest_{os.getpid()}_{time.time_ns()}"
    with _env(LIVE):
        coll = db.collection(name)
        assert coll is not None
        try:
            coll.insert_one({"branch": "x-br-pt", "status": "fixed", "round": 1})
            got = coll.find_one({"branch": "x-br-pt"})
            assert got and got["status"] == "fixed" and got["round"] == 1
            assert coll.count_documents({}) == 1
        finally:
            coll.drop()


def test_live_users_store_actually_works_on_mongo():
    """Mongo-бекенд користувачів існує з 14.08 і до появи локальної бази не
    ганявся жодного разу — перевіряємо повний цикл на викидній колекції."""
    coll_name = f"selftest_users_{os.getpid()}_{time.time_ns()}"
    with _env(LIVE):
        store = users.MongoUserStore(LIVE, db.db_name(), coll_name)
        try:
            row = store.create({"login": "Bot@Example.COM", "name": "bot",
                                "is_admin": False})
            assert row["login"] == users.norm_login("Bot@Example.COM"), \
                "логін мусить нормалізуватись так само, як у файловому сховищі"
            found = store.find_by_login("bot@example.com")
            assert found and found["_id"] == row["_id"]
            assert len(store.list_all()) == 1

            uid = str(row["_id"])
            assert store.get(uid)
            upd = store.update(uid, {"name": "bot-2", "is_active": False})
            assert upd["name"] == "bot-2" and upd["is_active"] is False

            try:
                store.create({"login": "bot@example.com", "name": "дубль"})
            except ValueError:
                pass
            else:
                raise AssertionError("унікальний індекс по логіну не спрацював")
        finally:
            store.coll.drop()
            users.reset_store_for_tests(None)


NS = dict(globals())
if not LIVE:
    # Без бази мережеві тести НЕ реєструються — гейт має лишатись
    # герметичним. Але мовчати теж не можна: інакше зелений результат
    # виглядав би як «БД перевірено», хоч її ніхто не бачив.
    for _n in [n for n in NS if n.startswith("test_live_")]:
        NS.pop(_n)
    print("  SKIP  тести з живою базою: Mongo не відповідає "
          "(підняти: docker compose -f docker-compose.dev.yml up -d mongo)")

run(NS)
