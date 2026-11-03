"""Тести реєстру ШІ-моста: лічильник і захист від кола.

Захист від кола — те, заради чого модуль існує: з одного боку конвеєра ШІ,
з другого ШІ, і без лічильника скарга ходила б по колу вічно. Тут закріплено
рівно ту межу, що в постановці: **два кола працюємо, на третьому зупиняємось
і кличемо людину**.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

# Реєстр дзеркалить записи в Mongo, коли вона налаштована. Тести самого
# реєстру мусять бути про реєстр, тож базу тут вимикаємо явно — інакше
# результат залежав би від того, підняли compose чи ні.
os.environ["MONGO_URI"] = ""

import ai_ledger                                                  # noqa: E402
import db                                                         # noqa: E402

db.reset_for_tests()


def _root():
    return Path(tempfile.mkdtemp(prefix="ai-ledger-"))


def _add(root, **kw):
    kw.setdefault("branch", "x-br-pt")
    kw.setdefault("status", "fixed")
    kw.setdefault("loop_key", ai_ledger.loop_key(kw["branch"], kw.get("routed") or []))
    return ai_ledger.append(root, kw)


# --------------------------------------------------------------- запис

def test_append_and_read_back():
    root = _root()
    _add(root, request_id="r1", routed=["logo_domain"], files=2, usd=0.01)
    rows = ai_ledger.entries(root)
    assert len(rows) == 1
    assert rows[0]["request_id"] == "r1"
    assert rows[0]["routed"] == ["logo_domain"]
    assert rows[0]["files"] == 2


def test_records_go_into_monthly_shards():
    root = _root()
    _add(root, request_id="a", ts="2026-07-01 10:00:00")
    _add(root, request_id="b", ts="2026-08-01 10:00:00")
    names = sorted(p.name for p in (root / ai_ledger.DIRNAME).glob("*.jsonl"))
    assert names == ["2026-07.jsonl", "2026-08.jsonl"]


def test_only_the_head_of_the_complaint_is_stored():
    """Текст приходить ззовні і нічим не обмежений, а реєстр читається
    цілком на кожен запит. Повний текст і так лежить у ClickUp."""
    root = _root()
    rec = _add(root, request_id="r", text_head="я" * 5000)
    assert len(rec["text_head"]) <= 200


def test_a_broken_line_does_not_make_the_registry_unreadable():
    root = _root()
    _add(root, request_id="ok")
    shard = next((root / ai_ledger.DIRNAME).glob("*.jsonl"))
    with shard.open("a", encoding="utf-8") as f:
        f.write("{обірваний рядок\n")
    assert [r["request_id"] for r in ai_ledger.entries(root)] == ["ok"]


# --------------------------------------------------------------- ключ кола

def test_loop_key_ignores_the_order_of_checks():
    a = ai_ledger.loop_key("br", ["logo_domain", "favicon"])
    b = ai_ledger.loop_key("br", ["favicon", "logo_domain"])
    assert a == b


def test_loop_key_separates_branches_and_defect_classes():
    assert ai_ledger.loop_key("a", ["favicon"]) != ai_ledger.loop_key("b", ["favicon"])
    assert ai_ledger.loop_key("a", ["favicon"]) != ai_ledger.loop_key("a", ["forms"])


def test_loop_key_survives_rewording():
    """Ключ навмисно НЕ від тексту: на другому колі та сама поломка приїде
    іншими словами, і порівняння текстів не спіймало б нічого."""
    assert ai_ledger.loop_key("br", ["logo_domain"]) == \
        ai_ledger.loop_key("br", ["logo_domain"])


# --------------------------------------------------------------- кола

def test_first_and_second_rounds_are_allowed_third_is_not():
    root = _root()
    key = ai_ledger.loop_key("x-br-pt", ["logo_domain"])

    v1 = ai_ledger.verdict(root, key, "x-br-pt", ["logo_domain"], "req-1")
    assert v1["allow"] is True and v1["round"] == 1
    _add(root, request_id="req-1", loop_key=key, task_id="t1", round=1,
         routed=["logo_domain"], ts="2026-08-01 10:00:00", status="fixed")

    v2 = ai_ledger.verdict(root, key, "x-br-pt", ["logo_domain"], "req-2")
    assert v2["allow"] is True and v2["round"] == 2
    _add(root, request_id="req-2", loop_key=key, task_id="t1", round=2,
         routed=["logo_domain"], ts="2026-08-01 11:00:00", status="fixed")

    v3 = ai_ledger.verdict(root, key, "x-br-pt", ["logo_domain"], "req-3")
    assert v3["allow"] is False
    assert v3["status"] == "escalated" and v3["round"] == 3
    assert "потрібна людина" in v3["reason"]


def test_a_reroute_on_the_second_round_does_not_reset_the_counter():
    """Роутинг на другому колі дав трохи інший набір — точний ключ
    розійшовся б, і петля пішла б на нове коло під новим ім'ям. Рахунок
    за ПЕРЕТИНОМ чеків саме для цього."""
    root = _root()
    for i, checks in enumerate([["logo_domain"],
                                ["logo_domain", "header_anchor"]], start=1):
        _add(root, request_id=f"r{i}", loop_key=ai_ledger.loop_key("x-br-pt", checks),
             task_id="t9", round=i, routed=checks,
             ts=f"2026-08-0{i} 10:00:00", status="fixed")
    third = ["logo_domain", "logo_photo"]
    v = ai_ledger.verdict(root, ai_ledger.loop_key("x-br-pt", third),
                          "x-br-pt", third, "r3")
    assert v["allow"] is False and v["status"] == "escalated"


def test_a_different_defect_on_the_same_task_has_its_own_counter():
    """Одна таска ClickUp покриває вайт цілком і законно несе кілька РІЗНИХ
    поломок. Спершу грубим ключем була пара (вітка, таска) — і на прогоні
    20 тасок скарга про логотип ескалювалась через те, що та сама таска
    раніше приносила скаргу про форму."""
    root = _root()
    for i in (1, 2):
        _add(root, request_id=f"f{i}", loop_key=ai_ledger.loop_key("x-br-pt", ["forms"]),
             task_id="t9", round=i, routed=["forms"],
             ts=f"2026-08-0{i} 10:00:00", status="fixed")
    logo = ["logo_domain"]
    v = ai_ledger.verdict(root, ai_ledger.loop_key("x-br-pt", logo),
                          "x-br-pt", logo, "new")
    assert v["allow"] is True and v["round"] == 1


def test_the_same_defect_on_another_branch_is_a_fresh_start():
    root = _root()
    for i in (1, 2):
        _add(root, request_id=f"a{i}", branch="x-br-pt", routed=["forms"],
             loop_key=ai_ledger.loop_key("x-br-pt", ["forms"]), round=i,
             ts=f"2026-08-0{i} 10:00:00", status="fixed")
    v = ai_ledger.verdict(root, ai_ledger.loop_key("other-br", ["forms"]),
                          "other-br", ["forms"], "new")
    assert v["allow"] is True and v["round"] == 1


def test_duplicates_and_not_ours_do_not_burn_rounds():
    """Три однакові ретраї за хвилину не мають вичерпувати ліміт, не
    зробивши жодної спроби полагодити."""
    root = _root()
    key = ai_ledger.loop_key("x-br-pt", ["logo_domain"])
    for i, st in enumerate(["duplicate", "not_ours", "unresolved"]):
        _add(root, request_id=f"d{i}", loop_key=key, routed=["logo_domain"],
             status=st, ts="2026-08-01 09:0%d:00" % i)
    assert ai_ledger.rounds_done(root, key, "x-br-pt", ["logo_domain"]) == 0


def test_same_request_id_is_answered_from_the_registry():
    root = _root()
    key = ai_ledger.loop_key("x-br-pt", ["logo_domain"])
    _add(root, request_id="same", loop_key=key, status="fixed")
    v = ai_ledger.verdict(root, key, "x-br-pt", ["logo_domain"], "same")
    assert v["allow"] is False and v["status"] == "duplicate"
    assert "same" in v["reason"]


def test_cooldown_swallows_a_retry_storm():
    root = _root()
    key = ai_ledger.loop_key("x-br-pt", ["logo_domain"])
    _add(root, request_id="first", loop_key=key, status="fixed",
         ts=time.strftime("%Y-%m-%d %H:%M:%S"))
    v = ai_ledger.verdict(root, key, "x-br-pt", ["logo_domain"], "second")
    assert v["allow"] is False and v["status"] == "duplicate"
    assert "кулдаун" in v["reason"]


def test_an_old_round_is_not_a_duplicate():
    root = _root()
    key = ai_ledger.loop_key("x-br-pt", ["logo_domain"])
    old = time.strftime("%Y-%m-%d %H:%M:%S",
                        time.localtime(time.time() - ai_ledger.COOLDOWN_S - 60))
    _add(root, request_id="first", loop_key=key, routed=["logo_domain"],
         status="fixed", ts=old)
    v = ai_ledger.verdict(root, key, "x-br-pt", ["logo_domain"], "second")
    assert v["allow"] is True and v["round"] == 2


# --------------------------------------------------------------- лічильник

def test_counters_split_by_status():
    root = _root()
    _add(root, request_id="1", status="fixed", files=3, usd=0.01)
    _add(root, request_id="2", status="fixed", files=1, usd=0.02)
    _add(root, request_id="3", status="clean", usd=0.01)
    _add(root, request_id="4", status="escalated", branch="other")
    c = ai_ledger.counters(root)
    assert c["total"] == 4
    assert c["fixes"] == 2 and c["files_fixed"] == 4
    assert c["escalations"] == 1
    assert c["branches"] == 2
    assert c["usd"] == 0.04
    assert c["by_status"]["clean"] == 1


def test_spend_is_counted_for_the_budget_guard():
    root = _root()
    _add(root, request_id="1", usd=0.5, ts=time.strftime("%Y-%m-%d %H:%M:%S"))
    assert ai_ledger.spend_usd(root, shards=1) == 0.5


# --------------------------------------------------- дзеркало в БД (умовно)

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


def test_live_record_is_mirrored_into_the_database():
    """«Лічильник вносить автофікси в БД» — власне це й перевіряємо."""
    root = _root()
    coll_name = f"selftest_ai_{os.getpid()}_{time.time_ns()}"
    saved_coll = ai_ledger.COLLECTION
    os.environ["MONGO_URI"] = LIVE
    ai_ledger.COLLECTION = coll_name
    db.reset_for_tests()
    try:
        _add(root, request_id="mirrored", status="fixed", files=2, usd=0.03)
        coll = db.collection(coll_name)
        doc = coll.find_one({"request_id": "mirrored"})
        assert doc and doc["status"] == "fixed" and doc["files"] == 2
        # файл лишається джерелом істини — він теж має запис
        assert [r["request_id"] for r in ai_ledger.entries(root)] == ["mirrored"]
        coll.drop()
    finally:
        ai_ledger.COLLECTION = saved_coll
        os.environ["MONGO_URI"] = ""
        db.reset_for_tests()


def test_live_a_dead_database_does_not_lose_the_file_record():
    """Порядок «спершу файл, потім база» саме тому: падіння Mongo не має
    губити факт того, що міст щойно зробив коміт."""
    root = _root()
    os.environ["MONGO_URI"] = "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200"
    was = db.SERVER_SELECTION_MS
    db.SERVER_SELECTION_MS = 200
    db.reset_for_tests()
    try:
        _add(root, request_id="survives", status="fixed")
        assert [r["request_id"] for r in ai_ledger.entries(root)] == ["survives"]
    finally:
        db.SERVER_SELECTION_MS = was
        os.environ["MONGO_URI"] = ""
        db.reset_for_tests()



def test_the_registry_remembers_who_sent_the_verdict():
    """Дрейф без атрибуції читається як «щось зламалось у вівторок».

    Видно, ЩО пішло повз мапу, але не видно, з якого їхнього релізу це
    почалось — а між двома їхніми зрізами може бути 39 випусків."""
    root = _root()
    ai_ledger.append(root, {"request_id": "a", "status": "clean",
                            "source": "tsm", "source_version": "0.9.26"})
    rec = ai_ledger.entries(root)[0]
    assert rec["source"] == "tsm" and rec["source_version"] == "0.9.26", rec


def test_drift_is_summed_per_source_version():
    """«0.9.26 — 2 запити, 0 повз мапу; 0.9.27 — 1 запит, 5 повз мапу»
    читається як «оновіть мапу під новий реліз», а не як «зламалось»."""
    root = _root()
    for i, (v, drift) in enumerate((("0.9.26", 0), ("0.9.26", 0),
                                    ("0.9.27", 5))):
        ai_ledger.append(root, {"request_id": f"r{i}", "status": "clean",
                                "source": "tsm", "source_version": v,
                                "tsm_unknown": drift})
    по_версіях = {d["version"]: d for d in ai_ledger.counters(root)["sources"]}
    assert по_версіях["0.9.26"]["n"] == 2 and по_версіях["0.9.26"]["drift"] == 0
    assert по_версіях["0.9.27"]["drift"] == 5, по_версіях


def test_records_without_a_source_do_not_invent_one():
    """Прозова скарга від людини джерела не має — і вигадувати його не можна,
    інакше зведення по версіях наповниться порожнім рядком."""
    root = _root()
    ai_ledger.append(root, {"request_id": "a", "status": "clean"})
    assert ai_ledger.counters(root)["sources"] == []


NS = dict(globals())
if not LIVE:
    for _n in [n for n in NS if n.startswith("test_live_")]:
        NS.pop(_n)
    print("  SKIP  дзеркало в БД: Mongo не відповідає "
          "(підняти: docker compose -f docker-compose.dev.yml up -d mongo)")

run(NS)
