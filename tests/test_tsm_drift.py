"""Гарда від дрейфу TSM: обидва зрізи, усі гілки, усі формати.

Це не юніт-тест окремої функції, а **вимір**, зафіксований тестом. Він
відповідає на єдине питання: чи переживе розбір вердиктів наступний апстрім.
Матеріал — корпус `tests/tsm_corpus.py`, знятий машинно з їхнього ж
`advice.py` (покриття гілок по AST — 100% в обох зрізах).

Історія, заради якої гарда й заведена. Мапа якорів була написана під зріз
v0.6.17 і давала на ньому 85%. Через 16 днів вийшов v0.9.26: **22% рядків
переписано**, додався цілий новий формат для саппорта — і покриття впало до
74% на подробицях і **11% на короткому форматі**, мовчки. Замість
безкоштовної мапи тихо вмикалась платна модель.

Тому тепер ключ — ІМʼЯ перевірки, а проза лише спосіб це ім'я впізнати:
вимір на тих самих двох зрізах дав 92% по імені проти 53% по прозі.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402
import tsm_corpus                                                 # noqa: E402

import runner                                                     # noqa: E402
import tsm_ingest                                                 # noqa: E402
import verdict_map as vm                                          # noqa: E402

PHP = [c["id"] for c in runner.load_checks()
       if not c.get("error") and "php" in (c.get("projects") or [])]


class _NoOverlay:
    """Порожня накладка, поставлена ДО першого тесту.

    Без неї `verdict_map.store()` завів би справжній `_FileStore` у корені
    стану — а корінь за замовчуванням це корінь репозиторію, тож тест
    насмітив би `ai_verdicts.json` у робочому дереві і, гірше, наступні
    прогони читали б чужу правку замість дефолтів. Спіймано рівно так:
    гарда впала, бо бачила запис, залишений сусіднім тестом.
    """

    def all(self):
        return {}

    def get(self, k):
        return None

    def put(self, rec):
        return rec

    def delete(self, k):
        return False

    def bump(self, k, field, n=1):
        return None


vm.reset_for_tests(_NoOverlay())

# Єдине ім'я в корпусі, якого не існує в жодному зрізі: воно навмисне.
# `spellcheck2` — вигадана «наступна їхня перевірка»; на ній видно, що
# незнайоме ім'я не ламає розбір, а чесно лишається незнайомим (і саме воно
# — робота для моделі, а не для таблиці).
SYNTHETIC = {"spellcheck2"}
# Поріг. Нижче — значить дрейф зʼїв розбір і час перечитувати їхній advice.py.
FLOOR = 95


def _resolve(line):
    """Один рядок вердикту → відповідь мапи (або None). Той самий шлях, що
    в роутері: проза → ім'я → мапа."""
    env = tsm_ingest.ingest({"text": line})
    if not env["verdicts"]:
        return None
    v = env["verdicts"][0]
    return vm.resolve({**v, "logs": v.get("logs") or []}, PHP)


def _score(corpus):
    per, missed = {}, set()
    for name, var, fmt, line, soft in corpus:
        if soft:
            continue
        d = per.setdefault(fmt, [0, 0])
        if _resolve(line) is not None:
            d[0] += 1
        else:
            d[1] += 1
            missed.add(name)
    return per, missed


def _pct(per):
    hit = sum(v[0] for v in per.values())
    tot = sum(sum(v) for v in per.values())
    return 100 * hit // max(1, tot), hit, tot


# ------------------------------------------------------------- покриття

def test_old_snapshot_is_still_understood():
    """Зріз, під який усе писалось. Падіння тут означало б, що ми зламали
    сумісність зі старішою версією тули — а вона ще стоїть у людей."""
    per, missed = _score(tsm_corpus.OLD)
    pct, hit, tot = _pct(per)
    assert pct >= FLOOR, f"0.6.17: {hit}/{tot} = {pct}%"
    assert missed <= SYNTHETIC, missed


def test_new_snapshot_survived_the_rewrite():
    """Той самий корпус після 39 їхніх релізів. Саме цей тест і є відповіддю
    на питання «чи переживе конструкція наступний апстрім»."""
    per, missed = _score(tsm_corpus.NEW)
    pct, hit, tot = _pct(per)
    assert pct >= FLOOR, f"0.9.26: {hit}/{tot} = {pct}%"
    assert missed <= SYNTHETIC, missed


def test_the_short_support_format_is_no_longer_a_blind_spot():
    """Формат `advice_summary` (з'явився 15.08, зараз перша вкладка в їхньому
    UI) — той, що копіює саппорт. Старі якорі впізнавали на ньому 11%."""
    per, _ = _score([r for r in tsm_corpus.NEW if r[2] == "summary"])
    pct, hit, tot = _pct(per)
    assert pct >= FLOOR, f"summary: {hit}/{tot} = {pct}%"


def test_only_the_deliberately_invented_check_stays_unknown():
    """Незнайоме ім'я — не помилка розбору, а робота для моделі. Але воно
    мусить лишитись ОДНИМ: якщо в цей набір потрапило щось іще, значить
    їхній зріз поїхав і мапу час доповнити."""
    _, missed_old = _score(tsm_corpus.OLD)
    _, missed_new = _score(tsm_corpus.NEW)
    assert missed_old | missed_new == SYNTHETIC, missed_old | missed_new


# ------------------------------------------------- контрольні випадки

def test_links_from_the_new_snapshot_reaches_link_target():
    """Головний приз апгрейду: `links` — це свої лінки в 4xx/5xx, тобто
    дослівно наш `link_target`. Перевіряємо на ЇХНІХ рядках, обох форматів."""
    for line in [l for n, _v, _f, l, s in tsm_corpus.NEW
                 if n == "links" and not s]:
        r = _resolve(line)
        assert r and "link_target" in r["checks"], (line, r)


def test_the_three_rewritten_verdicts_are_understood_again():
    """`bank`, `partners`, `banned` — рівно ті три, які зламались від
    переписування фрази 27.08. Беремо їхні НОВІ формулювання."""
    want = {"bank": "ours", "partners": "ours", "banned": "not_ours"}
    for name, cls in want.items():
        lines = [l for n, _v, f, l, s in tsm_corpus.NEW
                 if n == name and not s and f != "summary"]
        assert lines, name
        for line in lines:
            r = _resolve(line)
            assert r and r["class"] == cls, (name, line, r)


def test_tool_failure_never_routes_a_single_check():
    """Збій ЇХНЬОЇ тули не можна плутати з дефектом вайта: у їхньому ж рядку
    написано «это сбой инструмента, а не приговор сайту»."""
    for name in ("run_error", "run_timeout", "run_stopped", "vision",
                 "page_guard"):
        for line in [l for n, _v, _f, l, s in tsm_corpus.NEW
                     if n == name and not s]:
            r = _resolve(line)
            assert r and r["class"] == "tool_failure", (name, line, r)
            assert r["checks"] == []


def test_yellow_lines_are_never_routed_anywhere():
    """Жовтий ярус їхнього звіту — не дефект, а привід глянути очима."""
    for _n, _v, _f, line, soft in tsm_corpus.NEW:
        if not soft:
            continue
        env = tsm_ingest.ingest({"text": "Посмотреть глазами (не дефект, а "
                                         "повод взглянуть):\n" + line})
        assert all(v["soft"] for v in env["verdicts"]), line


def test_an_all_yellow_slice_routes_nothing():
    """Зріз, у якому ВСЕ жовте, не має зароутити жодного чека.

    Правило «жовте не роутиться ніколи» обходилось з чорного ходу: коли
    жодного червоного вердикта немає, словам віддавався ВЕСЬ текст — а він
    описує жовту знахідку, і слова спокійно піднімали під неї чек. Спіймано
    локальним стендом на домені, де впала лише `hygiene` (у них вона взагалі
    ніколи не червоніє — знахідка лежить у warnings).
    """
    import ai_router
    import ai_skills
    import ai_skills_store
    cards = ai_skills.catalog(runner.load_checks(), "php",
                              ai_skills_store.all_skills())
    env = tsm_ingest.ingest({"checks": [
        {"name": "hygiene", "passed": True, "logs": [],
         "warnings": ["Нет заголовка вкладки, иконки сайта"]}]})
    assert env["verdicts"] and all(v["soft"] for v in env["verdicts"])
    r = ai_router.route(tsm_ingest.as_text(env), cards, use_model=False, env=env)
    assert r["checks"] == [], r["checks"]


if __name__ == "__main__":
    run(dict(globals()))
