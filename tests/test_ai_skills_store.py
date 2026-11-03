"""Тести сховища скілів — того, що користувач править з вкладки.

Головне, що тут закріплено, — **семантика накладки**: вбудована картка з
коду лишається дефолтом, запис зі сховища кладеться зверху, а видалення
запису повертає дефолт. І окремо — вимога «ШІ працює тільки з активними
скілами»: вимкнений скіл ховає перевірку від моделі.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

os.environ["MONGO_URI"] = ""

import ai_skills                                                  # noqa: E402
import ai_skills_store as store                                   # noqa: E402
import db                                                         # noqa: E402
import runner                                                     # noqa: E402

db.reset_for_tests()
CHECKS = runner.load_checks()


def _file_store():
    d = Path(tempfile.mkdtemp(prefix="skills-"))
    st = store._FileStore(d / "ai_skills.json")
    store.reset_for_tests(st)
    return st


# --------------------------------------------------------------- перевірка вводу

def test_id_must_look_like_a_check_id():
    for bad in ("", "  ", "logo domain", "../etc", "лого", "a" * 65):
        try:
            store.normalize({"check_id": bad, "симптом": "щось"})
        except ValueError:
            continue
        raise AssertionError(f"'{bad}' мав бути відхилений")


def test_symptom_is_required_because_the_model_reads_it():
    try:
        store.normalize({"check_id": "logo_domain", "симптом": "   "})
    except ValueError as e:
        assert "симптом" in str(e)
    else:
        raise AssertionError("картка без симптому нічого не каже моделі")


def test_words_accept_a_plain_string_from_the_form():
    """У формі людині зручніше друкувати рядком, а не масивом."""
    rec = store.normalize({"check_id": "x", "симптом": "s",
                           "слова": "Лого, логотип\nбренд;  "})
    assert rec["слова"] == ["лого", "логотип", "бренд"]


def test_words_are_deduped_and_keep_their_order():
    """Порядок зберігаємо: людина пише спершу головні слова."""
    rec = store.normalize({"check_id": "x", "симптом": "s",
                           "слова": ["бета", "альфа", "бета"]})
    assert rec["слова"] == ["бета", "альфа"]


def test_oversized_input_is_refused():
    for field, value in (("симптом", "я" * 400),
                         ("слова", ["a" * 80]),
                         ("слова", ["w%d" % i for i in range(300)])):
        try:
            store.normalize({"check_id": "x", "симптом": "s", field: value})
        except ValueError:
            continue
        raise AssertionError(f"{field} мав бути відхилений")


def test_group_and_project_cannot_be_set_by_hand():
    """Група і тип проєкту — факти про КОД чека. Правити їх з UI означало б
    видавати думку за факт."""
    rec = store.normalize({"check_id": "x", "симптом": "s",
                           "group": "auto", "projects": ["php"], "fixable": True})
    assert set(rec) == {"check_id", "симптом", "слова", "не про це",
                        "лагодить", "active"}


# --------------------------------------------------------------- файловий бекенд

def test_save_and_read_back():
    _file_store()
    store.save({"check_id": "logo_domain", "симптом": "нове формулювання",
                "слова": ["лого"]}, author="urey")
    got = store.get("logo_domain")
    assert got["симптом"] == "нове формулювання"
    assert got["author"] == "urey" and got["created_at"] and got["updated_at"]


def test_saving_twice_keeps_the_creation_time():
    _file_store()
    first = store.save({"check_id": "x", "симптом": "раз"})
    time.sleep(1.05)
    second = store.save({"check_id": "x", "симптом": "два"})
    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] >= first["updated_at"]
    assert second["симптом"] == "два"


def test_delete_reports_whether_there_was_anything():
    _file_store()
    assert store.delete("logo_domain") is False
    store.save({"check_id": "logo_domain", "симптом": "s"})
    assert store.delete("logo_domain") is True
    assert store.get("logo_domain") is None


def test_a_broken_store_file_does_not_kill_routing():
    """Роутинг мусить пережити зіпсутий файл: без скілів він працює на
    вбудованих картках, тобто рівно як до появи вкладки."""
    st = _file_store()
    st.path.parent.mkdir(parents=True, exist_ok=True)
    st.path.write_text("{це не json", encoding="utf-8")
    assert store.all_skills() == {}


# --------------------------------------------------------------- накладка

def _check(cid):
    return next(c for c in CHECKS if c["id"] == cid)


def test_builtin_card_is_the_default():
    c = ai_skills.card(_check("logo_domain"))
    assert c["source"] == "built-in" and c["слова"]


def test_a_stored_record_lays_on_top_of_the_builtin():
    c = ai_skills.card(_check("logo_domain"),
                       {"симптом": "моє формулювання", "слова": ["моє"]})
    assert c["source"] == "override"
    assert c["симптом"] == "моє формулювання"
    assert c["слова"] == ["моє"], "перекриття замінює список, а не доповнює"
    # поля, яких не чіпали, лишаються від вбудованої картки
    assert c["не про це"]


def test_a_record_for_a_check_without_a_builtin_card_is_custom():
    fake = {"id": "brand_new", "name": "Свіжий", "description": "",
            "group": "review", "projects": ["php"], "fixable": False}
    c = ai_skills.card(fake, {"симптом": "моє", "слова": ["моє"]})
    assert c["source"] == "custom" and c["enriched"] is True


def test_a_check_with_no_skill_at_all_still_gets_an_auto_card():
    fake = {"id": "brand_new", "name": "Свіжий чек", "description": "",
            "group": "review", "projects": ["php"], "fixable": False}
    c = ai_skills.card(fake)
    assert c["source"] == "auto" and c["симптом"] == "Свіжий чек"
    assert c["enriched"] is False


def test_facts_about_the_code_survive_any_override():
    c = ai_skills.card(_check("logo_domain"),
                       {"симптом": "моє", "group": "auto", "fixable": False})
    real = _check("logo_domain")
    assert c["group"] == real["group"] and c["fixable"] is True


# ------------------------------------------- «ШІ працює тільки з активними»

def test_a_switched_off_skill_hides_the_check_from_the_model():
    ov = {"logo_domain": {"симптом": "x", "active": False}}
    ids = {c["id"] for c in ai_skills.catalog(CHECKS, "php", ov)}
    assert "logo_domain" not in ids
    assert "favicon" in ids, "решта каталогу не має постраждати"


def test_switching_it_back_on_returns_it():
    ov = {"logo_domain": {"симптом": "x", "active": True}}
    ids = {c["id"] for c in ai_skills.catalog(CHECKS, "php", ov)}
    assert "logo_domain" in ids


def test_a_switched_off_skill_never_reaches_the_prompt():
    ov = {"logo_domain": {"симптом": "x", "active": False}}
    text = ai_skills.render_for_model(ai_skills.catalog(CHECKS, "php", ov))
    assert "logo_domain" not in text


def test_set_active_needs_a_saved_record_first():
    """Вимикати нічого, поки запису немає: вбудована картка живе в коді."""
    _file_store()
    assert store.set_active("logo_domain", False) is None
    store.save({"check_id": "logo_domain", "симптом": "s"})
    assert store.set_active("logo_domain", False)["active"] is False
    assert store.set_active("logo_domain", True)["active"] is True


def test_coverage_counts_custom_records_and_switched_off_ones():
    ov = {"logo_domain": {"симптом": "x", "active": False},
          "нема_такого": {"симптом": "y"}}
    cov = ai_skills.coverage(CHECKS, ov)
    assert cov["custom"] == 2
    assert cov["inactive"] == ["logo_domain"]
    assert "нема_такого" in cov["stale"], "запис без чека має бути видно"


# --------------------------------------------------- живий бекенд (умовно)

def _live_uri() -> str:
    was = db.SERVER_SELECTION_MS
    db.SERVER_SELECTION_MS = 700
    try:
        for uri in ("mongodb://qa_lab:qa_lab@mongo:27017/?authSource=admin",
                    "mongodb://qa_lab:qa_lab@127.0.0.1:27017/?authSource=admin"):
            try:
                db.client_for(uri)
                return uri
            except Exception:
                continue
        return ""
    finally:
        db.SERVER_SELECTION_MS = was
        db.reset_for_tests()


LIVE = _live_uri()


def test_live_mongo_backend_is_chosen_and_works():
    coll_name = f"selftest_skills_{os.getpid()}_{time.time_ns()}"
    os.environ["MONGO_URI"] = LIVE
    os.environ[store.COLLECTION_ENV] = coll_name
    db.reset_for_tests()
    store.reset_for_tests(None)
    try:
        assert store.store_kind() == "mongo"
        store.save({"check_id": "logo_domain", "симптом": "з бази",
                    "слова": ["база"]}, author="urey")
        assert store.get("logo_domain")["симптом"] == "з бази"
        assert store.all_skills()["logo_domain"]["слова"] == ["база"]
        store.save({"check_id": "logo_domain", "симптом": "оновлено"})
        assert len(store.all_skills()) == 1, "унікальний індекс по check_id"
        assert store.set_active("logo_domain", False)["active"] is False
        assert store.delete("logo_domain") is True
        assert store.all_skills() == {}
        db.collection(coll_name).drop()
    finally:
        os.environ["MONGO_URI"] = ""
        os.environ.pop(store.COLLECTION_ENV, None)
        db.reset_for_tests()
        store.reset_for_tests(None)


NS = dict(globals())
if not LIVE:
    for _n in [n for n in NS if n.startswith("test_live_")]:
        NS.pop(_n)
    print("  SKIP  бекенд Mongo: база не відповідає "
          "(підняти: docker compose -f docker-compose.dev.yml up -d mongo)")

run(NS)
