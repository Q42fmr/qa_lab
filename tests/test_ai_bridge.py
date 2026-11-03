"""Тести конвеєра ШІ-моста: ідентифікація вітки і виконавець.

Найважливіше тут — **докази**. Роутер працює на повноту і повертає кілька
кандидатів; далі вони РЕАЛЬНО ганяються, і в роботу йдуть тільки ті, що
спрацювали. Саме ця пара тестів («не спрацював нічого → clean», «спрацював,
але автофікса немає → no_fix») закріплює властивість, заради якої міст можна
пускати без нагляду: помилка роутингу коштує зайвий прогін, а не поганий
коміт.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

os.environ["MONGO_URI"] = ""

import ai_bridge                                                  # noqa: E402
import ai_ledger                                                  # noqa: E402


#   СХОВИЩЕ МАПИ — В ПАМʼЯТЬ, ЩЕ ДО ПЕРШОГО ТЕСТУ. Міст рахує лічильники
# записів мапи, а корінь стану за замовчуванням — це корінь репозиторію: без
# ізоляції гейт клав `ai_verdicts.json` у робоче дерево, і наступний прогін
# читав чужу правку замість дефолтів. Той самий клас, що вже ловили в
# test_verdict_map.
import verdict_map as _vm                                         # noqa: E402


class _БезНакладки:
    def all(self): return {}
    def get(self, k): return None
    def put(self, rec): return rec
    def delete(self, k): return False
    def bump(self, k, field, n=1): return None


_vm.reset_for_tests(_БезНакладки())
import ai_skills                                                  # noqa: E402
import db                                                         # noqa: E402
import domains                                                    # noqa: E402
import runner                                                     # noqa: E402

db.reset_for_tests()


class Fake:
    """Підміна залежностей на час одного тесту. Через неї весь конвеєр
    ганяється без GitLab, без ClickUp і без диска вітки."""

    def __init__(self, **over):
        self.root = Path(tempfile.mkdtemp(prefix="ai-bridge-"))
        self.snap = Path(tempfile.mkdtemp(prefix="ai-snap-"))
        self.committed = []
        self.logged = []
        self.problems = []
        self.comments = []
        self.over = over

    def __enter__(self):
        self.saved = {}
        fake_client = type("C", (), {"commit": lambda _s, br, msg, actions: (
            self.committed.append((br, msg, actions)) or {"id": "deadbeef0123"})})()

        def patch(mod, name, value):
            self.saved[(mod, name)] = getattr(mod, name)
            setattr(mod, name, value)

        patch(ai_bridge, "_state_root", lambda: self.root)
        patch(ai_bridge, "known_branches", lambda: ["x-br-pt", "x-br", "other-br"])
        patch(ai_bridge, "clickup_enabled", lambda: False)
        patch(runner, "is_synced", lambda br: True)
        patch(runner, "sync_branch", lambda cl, br: None)
        patch(runner, "snapshot_dir", lambda br: self.snap)
        patch(runner, "run_checks", self.over.get("run_checks", self._checks))
        patch(runner, "compute_fixes", self.over.get("compute_fixes", self._fixes))
        patch(runner, "checks_for_active_project",
              self.over.get("catalog", self._catalog))
        # Каталог для роутера: інакше він лізе в `projects.ptype()`, а реєстр
        # проєктів у тестовому процесі не піднятий. Тести, що ганяють
        # `execute()` напряму, сюди не заходять — це потрібно лише тим, що
        # звертаються до HTTP-входу `ai_request`.
        patch(ai_bridge, "cards_for_project", self.over.get(
            "cards", lambda: ai_skills.catalog(
                [c for c in runner.load_checks() if not c.get("error")], "php")))
        self.saved_deps = dict(ai_bridge._deps)
        ai_bridge.wire(log_commit=lambda *a, **k: self.logged.append((a, k)),
                       add_problems=lambda items: self.problems.extend(items),
                       client=fake_client)
        return self

    def __exit__(self, *exc):
        for (mod, name), value in self.saved.items():
            setattr(mod, name, value)
        ai_bridge._deps.update(self.saved_deps)
        return False

    # дефолти: один чек спрацював з error, автофікс міняє один файл
    def _checks(self, branch, ids=None):
        return {"branch": branch, "files_scanned": 5,
                "totals": {"error": 1, "warn": 0, "info": 0},
                "checks": [{"id": "logo_domain", "name": "Лого",
                            "issues": [{"severity": "error", "message": "x",
                                        "path": "index.php", "line": 1}]},
                           {"id": "favicon", "name": "Favicon", "issues": []}]}

    def _fixes(self, branch, ids=None):
        return [{"type": "edit", "path": "index.php", "old": "a", "new": "b",
                 "checks": ["Лого"]}]

    def _catalog(self):
        return [
            {"id": "logo_domain", "fixable": True, "group": "auto"},
            {"id": "favicon", "fixable": True, "group": "auto"},
            {"id": "map_address", "fixable": True, "group": "review"},
            {"id": "page_language", "fixable": False, "group": "tests"},
        ]


def _job(**kw):
    kw.setdefault("request_id", "req-1")
    kw.setdefault("branch", "x-br-pt")
    kw.setdefault("task_id", "t1")
    kw.setdefault("routed", ["logo_domain", "favicon"])
    kw.setdefault("loop_key", ai_ledger.loop_key(kw["branch"], kw["routed"]))
    kw.setdefault("round", 1)
    kw.setdefault("text", "лого не той")
    return kw


# --------------------------------------------------- ідентифікація вітки

def test_explicit_branch_must_be_one_the_lab_knows():
    """Назву вітки приносить HTTP. Приймати будь-що означало б тягнути з
    GitLab довільний реф на прохання чужої машини."""
    with Fake():
        assert ai_bridge.resolve_branch("", branch="x-br-pt")["branch"] == "x-br-pt"
        bad = ai_bridge.resolve_branch("", branch="сусідська-вітка")
        assert bad["branch"] == "" and "немає ні в списку" in bad["error"]


def test_branch_name_is_case_insensitive():
    with Fake():
        assert ai_bridge.resolve_branch("", branch="X-BR-PT")["branch"] == "x-br-pt"


def test_branch_found_in_the_text_prefers_the_longest_match():
    """`x-br` не має вигравати в `x-br-pt`, коли в тексті друге."""
    with Fake():
        got = ai_bridge.resolve_branch("проблема на вітці x-br-pt, гляньте")
        assert got["branch"] == "x-br-pt"


def test_domain_resolves_to_a_branch():
    with Fake() as f:
        saved = domains.history_for
        domains.history_for = lambda d: [{"branch": "x-br-pt", "domain": d}]
        try:
            got = ai_bridge.resolve_branch("логотип не той", domain="fojfnpiot.pro")
        finally:
            domains.history_for = saved
        assert got["branch"] == "x-br-pt" and "fojfnpiot.pro" in got["how"]
        assert f.root


def test_ambiguous_domain_is_refused_not_guessed():
    with Fake():
        saved = domains.history_for
        domains.history_for = lambda d: [{"branch": "x-br-pt"}, {"branch": "other-br"}]
        try:
            got = ai_bridge.resolve_branch("лого", domain="shared.pro")
        finally:
            domains.history_for = saved
        assert got["branch"] == ""
        assert set(got["candidates"]) == {"x-br-pt", "other-br"}


def test_nothing_to_go_on_is_an_honest_failure():
    with Fake():
        got = ai_bridge.resolve_branch("щось десь зламалось")
        assert got["branch"] == "" and got["error"]


# --------------------------------------------------- докази

def test_evidence_separates_errors_from_warnings():
    res = {"checks": [
        {"id": "a", "issues": [{"severity": "error"}, {"severity": "error"}]},
        {"id": "b", "issues": [{"severity": "warn"}]},
        {"id": "c", "issues": []}]}
    err, warn = ai_bridge._evidence(res)
    assert err == {"a": 2} and warn == {"b": 1}
    assert "c" not in err and "c" not in warn


def test_a_check_from_a_disabled_group_is_never_autofixed():
    """`compute_fixes` фільтрує по fixable і типу проєкту, але НЕ по GROUP.
    Для людини це не проблема — галки ставить вона; для машини це обхід
    конвенції «новий чек живе у review, доки не доведений»."""
    with Fake():
        got = ai_bridge._fixable_now({"logo_domain", "map_address", "page_language"})
        assert got == ["logo_domain"]


def test_widening_the_allowed_groups_is_an_explicit_decision():
    with Fake():
        os.environ["AI_AUTOFIX_GROUPS"] = "auto,review"
        try:
            got = ai_bridge._fixable_now({"logo_domain", "map_address"})
            assert set(got) == {"logo_domain", "map_address"}
        finally:
            os.environ.pop("AI_AUTOFIX_GROUPS", None)


def test_the_keyword_fallback_lets_not_ours_win():
    """Прогін 20 тасок: «сайт отдаёт 502, хостинг лежит?» матчило
    `link_target` через слово «не открыва», і фолбек пішов би лагодити
    посилання на вайті, де проблема в хостингу."""
    routing = {"checks": ["link_target"], "router": "keywords",
               "not_ours": [{"id": "health", "чому": "хостинг"}]}
    assert ai_bridge.scope_checks(routing) == []


def test_with_a_live_model_a_mixed_complaint_keeps_its_fixable_part():
    """Модель бачить і скаргу, і каталог цілком — за неї не вирішуємо."""
    routing = {"checks": ["logo_domain"], "router": "claude",
               "not_ours": [{"id": "prices", "чому": "ціни"}]}
    assert ai_bridge.scope_checks(routing) == ["logo_domain"]


def test_no_not_ours_no_filtering():
    routing = {"checks": ["favicon"], "router": "keywords", "not_ours": []}
    assert ai_bridge.scope_checks(routing) == ["favicon"]


# --------------------------------------------------- виконавець

def test_nothing_fired_means_the_branch_is_clean_not_broken():
    """Головний сигнал розриву «гілка чиста ≠ домен працює»: скарга є,
    а в коді дефекту немає."""
    empty = lambda br, ids=None: {"branch": br, "files_scanned": 3,
                                  "totals": {}, "checks": [
                                      {"id": "logo_domain", "issues": []}]}
    with Fake(run_checks=empty) as f:
        rec = ai_bridge.execute(_job())
        assert rec["status"] == "clean"
        assert not f.committed
        assert "деплої" in rec["note"]


def test_the_snapshot_is_checked_for_freshness_every_time():
    """Найгірша можлива відповідь моста — «у гілці цього дефекту немає», якщо
    вона неправда.

    Раніше вітка синхронізувалась ЛИШЕ коли знімка не було: `is_synced()`
    перевіряє, що знімок є і належить цій вітці, але НЕ звіряє коміт. На
    застарілому знімку чеки не спрацюють — і міст відповість `clean`. Для TSM
    це не теоретично: скарга приходить одразу після деплою, коли вітка щойно
    змінилась.

    Дорого це не коштує: `sync_branch` сам звіряє коміт і не качає нічого,
    якщо той не змінився.
    """
    with Fake() as f:
        calls = []
        real = runner.sync_branch
        runner.sync_branch = lambda cl, br: calls.append(br)
        try:
            ai_bridge.execute(_job())
        finally:
            runner.sync_branch = real
    assert calls == ["x-br-pt"], calls


def test_an_unreachable_gitlab_does_not_kill_a_run_on_an_existing_snapshot():
    """Звірка свіжості не має робити міст залежним від мережі: якщо знімок
    уже є, працюємо по ньому — але кажемо про це в записі."""
    with Fake():
        real = runner.sync_branch

        def boom(cl, br):
            raise RuntimeError("gitlab unreachable")

        runner.sync_branch = boom
        try:
            rec = ai_bridge.execute(_job())
        finally:
            runner.sync_branch = real
    assert rec["status"] != "error", rec
    assert "знімок не оновлено" in rec["note"], rec["note"]


def test_fired_but_nothing_can_fix_it():
    only_diag = lambda: [{"id": "logo_domain", "fixable": False, "group": "tests"}]
    with Fake(catalog=only_diag) as f:
        rec = ai_bridge.execute(_job())
        assert rec["status"] == "no_fix"
        assert not f.committed
        assert f.problems and f.problems[0]["source"] == "ai-bridge"


def test_fired_and_fixable_but_the_fix_changes_nothing():
    with Fake(compute_fixes=lambda br, ids=None: []) as f:
        rec = ai_bridge.execute(_job())
        assert rec["status"] == "no_fix" and not f.committed


def test_dry_run_is_the_default_and_commits_nothing():
    """Система, що пише в git без людини, спершу має заробити довіру."""
    os.environ.pop("AI_BRIDGE_APPLY", None)
    with Fake() as f:
        rec = ai_bridge.execute(_job())
        assert rec["status"] == "dry-run"
        assert rec["files"] == 1
        assert not f.committed and not f.logged


def test_with_apply_on_it_commits_once_and_writes_the_journal():
    os.environ["AI_BRIDGE_APPLY"] = "1"
    try:
        with Fake() as f:
            rec = ai_bridge.execute(_job())
            assert rec["status"] == "fixed"
            assert rec["commit"] == "deadbeef0123" and rec["files"] == 1
            assert len(f.committed) == 1, "коміт мусить бути рівно один"
            branch, msg, actions = f.committed[0]
            assert branch == "x-br-pt"
            assert "logo_domain" in msg and "t1" in msg
            assert actions == [{"action": "update", "file_path": "index.php",
                                "content": "b"}]
            # у журнал — окремим типом, щоб /stats показала його як свій
            assert f.logged[0][1]["action"] == "ai-autofix"
            assert (f.snap / "index.php").read_text(encoding="utf-8") == "b"
    finally:
        os.environ.pop("AI_BRIDGE_APPLY", None)


def test_only_the_checks_that_fired_are_handed_to_the_fixer():
    """Роутер назвав двох кандидатів, спрацював один — лагодити треба саме
    його. Інакше коміт був би про щось інше, ніж скарга."""
    os.environ["AI_BRIDGE_APPLY"] = "1"
    seen = {}
    def spy(branch, ids=None):
        seen["ids"] = list(ids or [])
        return [{"type": "edit", "path": "i.php", "old": "a", "new": "b",
                 "checks": []}]
    try:
        with Fake(compute_fixes=spy):
            ai_bridge.execute(_job(routed=["logo_domain", "favicon"]))
        assert seen["ids"] == ["logo_domain"], seen
    finally:
        os.environ.pop("AI_BRIDGE_APPLY", None)


def test_a_crash_becomes_a_record_not_an_exception():
    def boom(branch, ids=None):
        raise RuntimeError("GitLab прилягла")
    with Fake(run_checks=boom) as f:
        rec = ai_bridge.execute(_job())
        assert rec["status"] == "error" and "GitLab" in rec["note"]
        assert f.problems, "людина має побачити це у вкладці «Проблеми»"


def test_work_in_flight_blocks_an_identical_request():
    """Реєстр дізнається про коло лише коли воно ЗАКІНЧИЛОСЬ, а між
    прийняттям і завершенням минають десятки секунд. Без цієї позначки
    буря ретраїв проходила б гейт цілком — знайдено на наскрізному прогоні."""
    ai_bridge._inflight.clear()
    key = ai_ledger.loop_key("x-br-pt", ["logo_domain"])
    assert ai_bridge._claim(key, "x-br-pt", ["logo_domain"]) is True
    assert ai_bridge._claim(key, "x-br-pt", ["logo_domain"]) is False
    # інший набір, але з тим самим чеком — це та сама робота
    over = ai_ledger.loop_key("x-br-pt", ["logo_domain", "favicon"])
    assert ai_bridge._claim(over, "x-br-pt", ["logo_domain", "favicon"]) is False
    # ІНША поломка того самого вайта чужу роботу не блокує
    other = ai_ledger.loop_key("x-br-pt", ["forms"])
    assert ai_bridge._claim(other, "x-br-pt", ["forms"]) is True
    # чужа вітка теж вільна (ключ у неї свій — він від назви вітки)
    assert ai_bridge._claim(ai_ledger.loop_key("other-br", ["logo_domain"]),
                            "other-br", ["logo_domain"]) is True
    ai_bridge._release(key, "x-br-pt", ["logo_domain"])
    assert ai_bridge._claim(key, "x-br-pt", ["logo_domain"]) is True
    ai_bridge._inflight.clear()


def test_the_mark_is_released_even_when_the_run_blows_up():
    """Інакше ключ лишився б зайнятим назавжди і вітка більше ніколи не
    пройшла б гейт."""
    ai_bridge._inflight.clear()
    def boom(branch, ids=None):
        raise RuntimeError("бабах")
    job = _job()
    ai_bridge._claim(job["loop_key"], job["branch"], job["routed"])
    with Fake(run_checks=boom):
        ai_bridge.execute(job)
    assert ai_bridge.inflight_count() == 0


# ------------------------------------------------- вердикти TSM у мості

def _post(text, **kw):
    kw.setdefault("branch", "x-br-pt")
    kw.setdefault("task_id", "t-tsm")
    return ai_bridge.ai_request(ai_bridge.AIRequest(text=text, **kw))


def test_a_broken_tsm_run_is_skipped_and_costs_no_round():
    """`run_error` та рідня означають «померла їхня тула», а не дефект вайта —
    так написано в їхньому ж рядку. Витрачати на це коло означало б, що дві
    мережеві невдачі в TSM закривають нам вітку."""
    with Fake() as f:
        out = _post("• [главная] Прогон этого домена сорвался — это сбой "
                    "инструмента, а не приговор сайту.")
        assert out["status"] == "skipped", out
        rows = ai_ledger.entries(f.root)
        assert [r["status"] for r in rows] == ["skipped"], rows
        assert rows[0]["round"] == 0, "збій прогону з'їв коло"
        assert ai_ledger.rounds_done(
            f.root, ai_ledger.loop_key("x-br-pt", ["logo_domain"]),
            "x-br-pt", ["logo_domain"]) == 0


def test_a_layout_verdict_answers_visual_instead_of_pretending():
    """Перекос верстки в лабі ловить візуальний прогін, а не чек. Відповідати
    «зараз полагоджу» на це було б брехнею, а мовчати — втратою скарги."""
    with Fake() as f:
        out = _post("• [главная] Вёрстка разъехалась: блок вылезает за край.")
        assert out["status"] == "visual", out
        assert "візуальн" in out["reason"].lower(), out["reason"]
        assert ai_ledger.entries(f.root)[0]["round"] == 0


def test_a_verdict_carries_our_own_explanation_of_why_it_is_not_ours():
    """Класи «не наше» вже мають писане «чому» — вердикт має брати саме його,
    інакше людина в ClickUp отримає порожній рядок."""
    with Fake():
        out = _post("• [главная] Домен в чёрном списке Google — браузеры "
                    "покажут посетителю красный экран.")
        assert out["status"] == "not_ours", out
        assert "чорн" in out["reason"].lower() or "search console" in out["reason"].lower(), \
            out["reason"]


def test_the_same_text_twice_is_a_duplicate_not_a_second_round():
    """На тому кінці один виклик і жодної логіки повторів, тож мережева
    невдача цілком прийде вдруге тим самим текстом."""
    with Fake() as f:
        first = _post("• [главная] Проверить адекватность цен (см. лог).")
        second = _post("• [главная] Проверить адекватность цен (см. лог).")
        assert first["status"] == "not_ours", first
        assert second["status"] == "duplicate", second
        assert second["request_id"] == first["request_id"], (first, second)
        assert len(ai_ledger.entries(f.root)) == 1, "ретрай дописав другий запис"


def test_a_reformatted_retry_is_still_the_same_text():
    """Той самий коментар, перезгорнутий по-іншому, — це той самий коментар."""
    assert ai_ledger.text_hash("а  б\nв") == ai_ledger.text_hash("а б в")


def test_a_mixed_verdict_keeps_the_fixable_half():
    """Найцінніший реальний випадок: у тому самому блоці і «не наше» (ціни),
    і справжній дефект (бренд у шапці). У режимі слів «не наше» перемагає
    кандидатів — і саме тому мапа НЕ повинна проходити через той фільтр:
    вона знає рядок у рядок, що з чого, а не здогадується по словах."""
    with Fake():
        out = _post("Что фиксить — a.co\n"
                    "• [главная] Проверить адекватность цен (см. лог).\n"
                    "• [главная] Название сайта не совпадает с доменом — "
                    "привести бренд в шапке к корню домена.")
        assert out["status"] == "accepted", out
        assert out["routed"] == ["logo_domain"], out
        assert out["router"] == "tsm-map", out


def test_an_unrecognised_verdict_is_counted_so_the_drift_is_visible():
    """Ф7. Якщо в TSM перепишуть текст поради, наші якорі відваляться МОВЧКИ:
    зовні це виглядає лише як «стало дорожче», бо замість безкоштовної мапи
    вмикається платна модель. Тому рахуємо і показуємо на /ai."""
    with Fake() as f:
        _post("• [главная] Совершенно новая формулировка совета, которой мы не знаем")
        rows = ai_ledger.entries(f.root)
        assert rows[0]["tsm_unknown"] == 1, rows
        c = ai_ledger.counters(f.root)
        assert c["tsm_unknown"] == 1 and c["tsm_unknown_last"], c


def test_the_drift_report_names_the_check_that_is_missing():
    """Адресність: на /ai має бути видно не «щось не розібрали», а яку саме
    їхню перевірку бракує в мапі."""
    with Fake() as f:
        _post("• [главная] spellcheck2: найдено 3 опечатки")
        c = ai_ledger.counters(f.root)
        assert c["tsm_new"] == [("spellcheck2", 1)], c["tsm_new"]


def test_the_comment_says_what_we_could_not_read():
    """Без цього рядка людина читає відповідь лаби як повну, хоча частина
    вердикту пройшла повз нас."""
    txt = ai_bridge._comment({"status": "clean", "branch": "x-br", "round": 1,
                              "routed": [], "tsm_unknown": 2,
                              "tsm_new": ["spellcheck2"]})
    assert "не розібрав 2" in txt and "spellcheck2" in txt, txt


def test_the_comment_passes_on_what_tsm_saw_by_eye():
    """Жовте ми не роутимо — але й губити не можна: інакше знахідка, зроблена
    їхньою тулою очима, зникає між двома машинами безслідно."""
    txt = ai_bridge._comment({"status": "clean", "branch": "x-br", "round": 1,
                              "routed": [],
                              "tsm_soft": ["Нечитаемый текст: <p> контраст 1.4:1"]})
    assert "глянути очима" in txt and "контраст 1.4:1" in txt, txt


def test_a_yellow_only_verdict_still_reaches_the_human():
    """Крайній випадок: у вердикті ЛИШЕ жовте. Роутити нема чого, але й
    мовчати не можна — інакше відповідь виглядає як «нічого не знайшли»."""
    with Fake() as f:
        _post("Что фиксить — a.co\n"
              "Посмотреть глазами (не дефект, а повод взглянуть):\n"
              "  [главная] Текст сливается с фоном — см. лог, поменять цвета.")
        rec = ai_ledger.entries(f.root)[0]
        assert rec["tsm_soft"], rec
        assert "глянути очима" in ai_bridge._comment(rec)


def test_a_recognised_verdict_does_not_count_as_drift():
    with Fake() as f:
        _post("• [главная] Вёрстка разъехалась: блок вылезает за край.")
        assert ai_ledger.counters(f.root)["tsm_unknown"] == 0


def test_a_different_task_is_not_a_duplicate():
    """Ключ ідемпотентності — текст ПЛЮС таска: один і той самий вердикт по
    двох різних вайтах приходить з однаковим формулюванням постійно."""
    with Fake():
        _post("• [главная] Проверить адекватность цен (см. лог).", task_id="t-1")
        out = _post("• [главная] Проверить адекватность цен (см. лог).", task_id="t-2")
        assert out["status"] == "not_ours", out


def test_every_run_lands_in_the_registry():
    with Fake() as f:
        ai_bridge.execute(_job(request_id="r-1"))
        rows = ai_ledger.entries(f.root)
        assert [r["request_id"] for r in rows] == ["r-1"]
        assert rows[0]["fired"] == {"logo_domain": 1}
        assert rows[0]["ms"] >= 0


if __name__ == "__main__":
    run(dict(globals()))
