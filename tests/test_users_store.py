"""Тести сховища користувачів і паролів.

Перевіряється файловий бекенд — той, на якому лаба працює нативно, без Mongo.
Mongo-бекенд має той самий інтерфейс, але вимагає живої бази, тож тут його
не піднімаємо. Він ганяється в `test_db.py` — але тільки якщо база реально
відповідає (локально її піднімає `docker-compose.dev.yml`); у гейті без
мережі ті тести не реєструються, і герметичність зберігається.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import auth                                                       # noqa: E402
import users                                                      # noqa: E402


def _store():
    d = Path(tempfile.mkdtemp(prefix="users-"))
    st = users.FileUserStore(d / "users.json")
    users.reset_store_for_tests(st)
    # Відбиток ADMIN_PASSWORD рахується на ключі підпису кук. Без фіксованого
    # ключа `auth.secret_key()` полізе створювати `.session_secret` у корені
    # стану, і тести залежали б від того, що там лежить.
    os.environ["QA_LAB_SECRET_KEY"] = "test-secret-key"
    auth.reset_secret_for_tests()
    return st


# --------------------------------------------------------------- паролі

def test_hash_is_salted_so_two_equal_passwords_differ():
    """Однаковий пароль дає різні хеші — інакше по базі було б видно, у кого
    паролі збігаються."""
    a = users.hash_password("correct horse")
    b = users.hash_password("correct horse")
    assert a != b, (a, b)


def test_verify_accepts_the_right_password():
    h = users.hash_password("correct horse")
    assert users.verify_password("correct horse", h)


def test_verify_rejects_the_wrong_one():
    h = users.hash_password("correct horse")
    assert not users.verify_password("correct hors", h)


def test_verify_survives_garbage_instead_of_a_hash():
    """Битий рядок у базі не має валити вхід у 500."""
    for junk in (None, "", "not-a-hash", "scrypt$x$y$z$q$w", "$$$$$"):
        assert not users.verify_password("whatever", junk), junk


def test_empty_password_is_never_valid():
    h = users.hash_password("something")
    assert not users.verify_password("", h)


def test_hashing_an_empty_password_is_refused():
    try:
        users.hash_password("")
    except ValueError:
        return
    raise AssertionError("порожній пароль мав бути відхилений")


# --------------------------------------------------------------- сховище

def test_login_is_case_insensitive():
    st = _store()
    st.create({"login": "Nora", "password_hash": users.hash_password("pw12345678")})
    assert st.find_by_login("NORA") is not None
    assert st.find_by_login("  nora  ") is not None


def test_duplicate_login_is_refused():
    st = _store()
    st.create({"login": "nora"})
    try:
        st.create({"login": "NORA"})
    except ValueError:
        return
    raise AssertionError("дубль логіна мав бути відхилений")


def test_duplicate_slack_id_is_refused():
    st = _store()
    st.create({"login": "a", "slack_user_id": "U1"})
    try:
        st.create({"login": "b", "slack_user_id": "U1"})
    except ValueError:
        return
    raise AssertionError("дубль slack_user_id мав бути відхилений")


def test_created_at_is_filled():
    """Був баг: setdefault мовчав, бо ключ уже існував зі значенням None."""
    st = _store()
    row = st.create({"login": "a"})
    assert row.get("created_at"), row


def test_update_changes_only_known_fields():
    st = _store()
    row = st.create({"login": "a", "name": "A"})
    st.update(row["id"], {"name": "B", "is_admin": True, "junk": "ignored"})
    got = st.get(row["id"])
    assert got["name"] == "B", got
    assert got["is_admin"] is True, got
    assert "junk" not in got, got


def test_state_survives_a_new_store_object():
    """Дані лежать у файлі, а не в пам'яті процесу."""
    d = Path(tempfile.mkdtemp(prefix="users-"))
    users.FileUserStore(d / "users.json").create({"login": "a"})
    assert users.FileUserStore(d / "users.json").find_by_login("a") is not None


# --------------------------------------------------------------- вхід

def test_authenticate_accepts_valid_pair():
    st = _store()
    st.create({"login": "nora", "password_hash": users.hash_password("pw12345678")})
    assert users.authenticate("nora", "pw12345678") is not None


def test_authenticate_rejects_disabled_account():
    """Головна властивість вимкнення: пароль правильний, а входу немає."""
    st = _store()
    st.create({"login": "nora", "password_hash": users.hash_password("pw12345678"),
               "is_active": False})
    assert users.authenticate("nora", "pw12345678") is None


def test_authenticate_rejects_user_without_password():
    """Заведений через Slack пароля не має — і не може зайти першим полем,
    поки сам його не задасть."""
    st = _store()
    st.create({"login": "slacker", "slack_user_id": "U1", "password_hash": None})
    assert users.authenticate("slacker", "") is None
    assert users.authenticate("slacker", "anything") is None


def test_public_never_leaks_the_hash():
    st = _store()
    row = st.create({"login": "a", "password_hash": users.hash_password("pw12345678")})
    pub = users.public(row)
    assert "password_hash" not in pub, pub
    assert pub["has_password"] is True, pub


# --------------------------------------------------------------- Slack

def test_slack_login_creates_the_account():
    _store()
    row = users.upsert_slack_user("U1", "T1", name="Alex", email="alex@corp.io")
    assert row["slack_user_id"] == "U1", row
    assert row["is_admin"] is False, row
    assert row["password_hash"] is None, row


def test_slack_login_is_idempotent():
    """Другий вхід не плодить другий акаунт."""
    st = _store()
    users.upsert_slack_user("U1", "T1", email="alex@corp.io")
    users.upsert_slack_user("U1", "T1", email="alex@corp.io")
    assert len(st.list_all()) == 1, st.list_all()


def test_slack_login_derives_login_from_email():
    _store()
    row = users.upsert_slack_user("U1", "T1", email="alex@corp.io")
    assert row["login"] == "alex", row


def test_slack_login_avoids_colliding_with_an_existing_login():
    st = _store()
    st.create({"login": "alex"})
    row = users.upsert_slack_user("U9", "T1", email="alex@corp.io")
    assert row["login"] != "alex", row
    assert st.find_by_login(row["login"])["slack_user_id"] == "U9"


# --------------------------------------------------------------- bootstrap

def test_bootstrap_admin_is_created_from_env():
    _store()
    os.environ["ADMIN_LOGIN"] = "root"
    os.environ["ADMIN_PASSWORD"] = "root-pass-123"
    try:
        row = users.ensure_bootstrap_admin()
        assert row["is_admin"] is True, row
        assert users.authenticate("root", "root-pass-123") is not None
    finally:
        os.environ.pop("ADMIN_LOGIN", None)
        os.environ.pop("ADMIN_PASSWORD", None)


def test_bootstrap_admin_resets_the_password_and_reenables():
    """Спосіб повернути доступ: змінити ADMIN_PASSWORD і перезапустити.

    Тут запис БЕЗ відбитка — такі лишились від версій до 26.08, і для них
    значення в оточенні вважається незастосованим. Тому скид відпрацьовує.
    """
    st = _store()
    st.create({"login": "root", "password_hash": users.hash_password("old-pass-123"),
               "is_admin": False, "is_active": False})
    os.environ["ADMIN_LOGIN"] = "root"
    os.environ["ADMIN_PASSWORD"] = "new-pass-123"
    try:
        users.ensure_bootstrap_admin()
        assert users.authenticate("root", "old-pass-123") is None
        row = users.authenticate("root", "new-pass-123")
        assert row is not None and row["is_admin"] is True, row
    finally:
        os.environ.pop("ADMIN_LOGIN", None)
        os.environ.pop("ADMIN_PASSWORD", None)


# ------------------------------------------ пароль, заданий у UI, і рестарти

def _restart():
    """Рівно те, що робить `@app.on_event("startup")`."""
    return users.ensure_bootstrap_admin()


def _set_ui_password(st, login: str, password: str):
    """Те саме, що робить `POST /api/account/password`."""
    row = st.find_by_login(login)
    uid = str(row.get("_id") or row.get("id") or "")
    st.update(uid, {"password_hash": users.hash_password(password)})


def test_a_password_set_in_the_ui_survives_restarts():
    """Головне, заради чого відбиток і заводився.

    До 26.08 хук переписував пароль на КОЖНОМУ старті, а старт буває не лише
    на деплої (`restart_policy: condition: any`, три невдалі healthcheck-и,
    переїзд таски). Пароль, заданий у UI, зникав сам собою.
    """
    st = _store()
    os.environ["ADMIN_LOGIN"] = "root"
    os.environ["ADMIN_PASSWORD"] = "from-ci-123"
    try:
        _restart()
        _set_ui_password(st, "root", "my-own-pass-77")
        for _ in range(3):
            _restart()
        assert users.authenticate("root", "my-own-pass-77") is not None, \
            "пароль з UI знову затерто значенням із CI"
        assert users.authenticate("root", "from-ci-123") is None
    finally:
        os.environ.pop("ADMIN_LOGIN", None)
        os.environ.pop("ADMIN_PASSWORD", None)


def test_changing_the_ci_value_still_resets_the_password():
    """Друга гарантія, яку не можна втратити: коли не заходить НІХТО, доступ
    повертають через CI. Значить нове значення мусить перебивати те, що
    задали в UI."""
    st = _store()
    os.environ["ADMIN_LOGIN"] = "root"
    os.environ["ADMIN_PASSWORD"] = "from-ci-123"
    try:
        _restart()
        _set_ui_password(st, "root", "my-own-pass-77")
        os.environ["ADMIN_PASSWORD"] = "rescue-pass-999"
        _restart()
        assert users.authenticate("root", "rescue-pass-999") is not None
        assert users.authenticate("root", "my-own-pass-77") is None
    finally:
        os.environ.pop("ADMIN_LOGIN", None)
        os.environ.pop("ADMIN_PASSWORD", None)


def test_the_same_value_no_longer_reenables_a_disabled_account():
    """Ціна рішення, названа вголос: вимкнену учетку хук більше не «лікує»
    сам. Без цього нею неможливо було керувати з UI — будь-яке вимкнення
    скасовував наступний рестарт. Повернути = змінити ADMIN_PASSWORD."""
    st = _store()
    os.environ["ADMIN_LOGIN"] = "root"
    os.environ["ADMIN_PASSWORD"] = "from-ci-123"
    try:
        _restart()
        row = st.find_by_login("root")
        st.update(str(row.get("id")), {"is_active": False, "is_admin": False})
        _restart()
        after = st.find_by_login("root")
        assert after["is_active"] is False, "рестарт знову ввімкнув учетку"
        assert after["is_admin"] is False, "рестарт знову видав адмінство"
        os.environ["ADMIN_PASSWORD"] = "rescue-pass-999"
        _restart()
        back = st.find_by_login("root")
        assert back["is_active"] is True and back["is_admin"] is True, back
    finally:
        os.environ.pop("ADMIN_LOGIN", None)
        os.environ.pop("ADMIN_PASSWORD", None)


def test_an_old_record_is_reset_exactly_once():
    """Міграція: запис без відбитка скидається один раз, відбиток лягає, і
    далі учетка керована з UI. Один скид, а не жоден — бо запис без відбитка
    може мати пароль, якого не знає ніхто."""
    st = _store()
    st.create({"login": "root", "password_hash": users.hash_password("who-knows"),
               "is_admin": True, "is_active": True})
    os.environ["ADMIN_LOGIN"] = "root"
    os.environ["ADMIN_PASSWORD"] = "from-ci-123"
    try:
        _restart()
        assert users.authenticate("root", "from-ci-123") is not None, "скиду не сталося"
        _set_ui_password(st, "root", "my-own-pass-77")
        _restart()
        assert users.authenticate("root", "my-own-pass-77") is not None, \
            "після міграції учетка все ще переписується щостарту"
    finally:
        os.environ.pop("ADMIN_LOGIN", None)
        os.environ.pop("ADMIN_PASSWORD", None)


def test_the_fingerprint_is_not_the_password_and_never_leaves_the_server():
    """Поле службове: у базі це HMAC, а не пароль, і в `/api/users` його
    бути не може — `_norm` будується з FIELDS, тож нове поле поїхало б
    назовні саме тому, що ми його додали."""
    st = _store()
    os.environ["ADMIN_LOGIN"] = "root"
    os.environ["ADMIN_PASSWORD"] = "from-ci-123"
    try:
        _restart()
        raw = st.find_by_login("root")
        fp = raw.get("bootstrap_fp")
        assert fp and len(fp) == 64, fp
        assert "from-ci-123" not in fp
        assert "bootstrap_fp" not in users.public(raw)
        assert "password_hash" not in users.public(raw)
    finally:
        os.environ.pop("ADMIN_LOGIN", None)
        os.environ.pop("ADMIN_PASSWORD", None)


def test_bootstrap_is_skipped_without_a_password():
    """Порожній ADMIN_PASSWORD не має створювати учетку без пароля."""
    st = _store()
    os.environ["ADMIN_LOGIN"] = "root"
    os.environ.pop("ADMIN_PASSWORD", None)
    try:
        assert users.ensure_bootstrap_admin() is None
        assert st.list_all() == []
    finally:
        os.environ.pop("ADMIN_LOGIN", None)


# ------------------------------------------------- особистий токен ClickUp

def _with_token(st):
    row = st.create({"login": "petro", "name": "Petro"})
    uid = str(row["id"])
    users.store_clickup_token(uid, "pk_TEST_not_a_real_token", "Petro K.")
    return uid, st.get(uid)


def test_the_token_is_stored_sealed_not_as_it_came():
    """У сховищі не має лежати робочий токен колеги відкритим текстом."""
    st = _store()
    _uid, raw = _with_token(st)
    assert "pk_TEST_not_a_real_token" not in str(raw), raw
    assert users.clickup_token_of(raw) == "pk_TEST_not_a_real_token"


def test_the_token_never_leaves_through_the_api():
    """`_norm` будується з FIELDS, тож без явного pop токен поїхав би у
    відповідь `/api/users` рівно тому, що ми його туди додали — і адмін бачив
    би чужі токени. Та сама пастка, що з `bootstrap_fp`."""
    st = _store()
    _uid, raw = _with_token(st)
    pub = users.public(raw)
    assert "clickup_token" not in pub, pub
    assert pub["has_clickup_token"] is True
    assert pub["clickup_user"] == "Petro K."


def test_the_field_survives_the_store():
    """Обидва сховища фільтрують патчі по FIELDS: поле, не вписане туди,
    не збереглося б мовчки."""
    st = _store()
    uid, _ = _with_token(st)
    assert st.get(uid).get("clickup_token"), st.get(uid)


def test_a_changed_session_key_does_not_crash_anything():
    """Ключ сесій могли поміняти — тоді токен не читається. Це не аварія:
    порожньо, і кабінет попросить ввести заново."""
    st = _store()
    _uid, raw = _with_token(st)
    os.environ["QA_LAB_SECRET_KEY"] = "another-key"
    auth.reset_secret_for_tests()
    try:
        assert users.clickup_token_of(raw) == ""
    finally:
        os.environ["QA_LAB_SECRET_KEY"] = "test-secret-key"
        auth.reset_secret_for_tests()


def test_clearing_removes_the_token_and_its_traces():
    st = _store()
    uid, _ = _with_token(st)
    users.clear_clickup_token(uid)
    pub = users.public(st.get(uid))
    assert pub["has_clickup_token"] is False and not pub["clickup_user"], pub


def test_the_last_error_is_remembered():
    """Тост живе шість секунд, мертвий токен — тижнями."""
    st = _store()
    uid, _ = _with_token(st)
    users.note_clickup_error(uid, "Token invalid (OAUTH_025)")
    assert "OAUTH_025" in st.get(uid)["clickup_error"]


def test_a_user_without_a_token_reads_as_empty():
    st = _store()
    row = st.create({"login": "maria"})
    assert users.clickup_token_of(row) == ""
    assert users.public(row)["has_clickup_token"] is False



if __name__ == "__main__":
    run(dict(globals()))
