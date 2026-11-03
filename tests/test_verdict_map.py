"""Мапа вердиктів як дані.

Головне, що стережуть ці тести: мапа ВИВОДИТЬСЯ зі списку якорів, а не
дублює його (дві копії відповідності одного дня розійшлись би, і ніхто б не
помітив, яка діє); варіант розводиться по ЛОГАХ, а не по прозі; жовте не
роутиться ніколи; накладка перекриває дефолт, а видалення запису дефолт
повертає.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import runner                                                     # noqa: E402
import tsm_verdicts as tv                                         # noqa: E402
import verdict_map as vm                                          # noqa: E402

PHP = [c["id"] for c in runner.load_checks()
       if not c.get("error") and "php" in (c.get("projects") or [])]


class _Mem:
    """Сховище в пам'яті — той самий трюк, що в тестах скілів: гейт мусить
    лишатись герметичним і не залежати ні від Mongo, ні від диска."""

    def __init__(self):
        self.data = {}

    def all(self):
        return {k: dict(v) for k, v in self.data.items()}

    def get(self, k):
        return dict(self.data[k]) if k in self.data else None

    def put(self, rec):
        rec = dict(rec)
        rec.setdefault("stats", self.data.get(rec["key"], {}).get("stats", {}))
        self.data[rec["key"]] = rec
        return rec

    def delete(self, k):
        return self.data.pop(k, None) is not None

    def bump(self, k, field, n=1):
        rec = self.data.get(k)
        if rec is None:
            return None
        st = rec.setdefault("stats", {})
        st[field] = int(st.get(field) or 0) + n
        return rec


# Ізоляція ставиться ДО першого тесту, а не лише всередині них: інакше
# `verdict_map.store()` завів би справжній файл у корені стану (а це корінь
# репозиторію) і насмітив би в робочому дереві.
def _fresh():
    """Чисте сховище на кожен тест. Харнес не має setup/teardown, а стан
    накладки протікає між тестами: `active=false` в одному з них інакше
    ховає ім'я від усіх наступних (спіймано на цьому ж файлі)."""
    vm.reset_for_tests(_Mem())


_fresh()


def _v(name, logs=(), line="", soft=False, page=""):
    return {"name": name, "logs": list(logs), "line": line,
            "soft": soft, "page": page}


# ------------------------------------------------------------- дефолти

def test_defaults_are_derived_from_the_anchor_list():
    """Джерело відповідності одне. Кожне ім'я зі списку якорів мусить мати
    ключ у мапі — інакше прозовий і структурний шляхи вели б у різні місця."""
    _fresh()
    keys = vm.defaults()
    for v in tv.VERDICTS:
        assert vm.key_for("tsm", v["tsm"]) in keys, v["tsm"]


def test_every_ambiguous_name_has_a_variant():
    """Гарда від мовчазної втрати гілки.

    Якщо в списку якорів у одного імені гілки ведуть у РІЗНІ місця, ключа-імені
    мало — потрібен варіант по логах. Заміряно 26.08 і підтверджено на корпусі
    27.08: таких імен рівно три (`form`, `hero`, `images`). Додасться четверте
    — цей тест впаде і нагадає завести дискримінатор, а не мовчки склеїть два
    різні дефекти в один.
    """
    _fresh()
    by = {}
    for v in tv.VERDICTS:
        by.setdefault(v["tsm"], set()).add(vm._target(v))
    ambiguous = sorted(n for n, s in by.items() if len(s) > 1)
    assert ambiguous == ["form", "hero", "images"], ambiguous
    for n in ambiguous:
        rec = vm.AMBIGUOUS.get(n)
        assert rec and rec.get("variants"), \
            f"{n}: гілки розходяться, а явної бази з варіантом немає"


def test_new_names_from_0926_are_seeded():
    """Імена, яких у зрізі 0.6.17 не було. Розібрані читанням їхнього коду,
    не здогадом по назві."""
    _fresh()
    for n in ("links", "navdup", "pages_alias", "hygiene", "spellcheck",
              "mobile", "greencheck"):
        assert vm.get(vm.key_for("tsm", n)), n


def test_links_maps_to_our_link_target():
    """Контрольний випадок усього апгрейду: `links` у них — це свої лінки в
    4xx/5xx, тобто дослівно наш `link_target`."""
    _fresh()
    r = vm.resolve(_v("links", ["• 404 — «Servicios» → https://x.pro/s"]), PHP)
    assert r["class"] == "ours" and "link_target" in r["checks"], r


# ------------------------------------------------------------- варіанти

def test_variant_splits_form_by_its_own_log():
    """`form` каже дві різні речі, і робота за ними різна: форми немає —
    її треба ДОДАТИ; форма є, але не відправляється — лагодити обробник."""
    _fresh()
    немає = vm.resolve(_v("form", ["Форма не найдена на странице"]), PHP)
    не_шле = vm.resolve(_v("form", ["Сабмит не подтверждается"]), PHP)
    assert немає["variant"] and "forms" in немає["checks"]
    assert not не_шле["variant"]
    assert "form_hijack" in не_шле["checks"], не_шле


def test_variant_sends_dead_hero_to_not_ours():
    """«Главная отдаёт заглушку сервера» — це хостинг, і лагодити з коду
    вітки нічого."""
    _fresh()
    r = vm.resolve(_v("hero", ["Главная отдаёт заглушку сервера"]), PHP)
    assert r["class"] == "not_ours" and r["not_ours"] == "health", r


def test_hero_without_that_log_is_not_a_check():
    _fresh()
    r = vm.resolve(_v("hero", ["Тема не определена по hero-тексту"]), PHP)
    assert r["class"] == "no_check", r


def test_images_broken_files_are_ours_but_content_is_not():
    _fresh()
    биті = vm.resolve(_v("images", ["битые: https://x.pro/a.jpg"]), PHP)
    зміст = vm.resolve(_v("images", ["Картинки из ЧУЖОЙ отрасли: https://x.pro/a.jpg"]), PHP)
    assert "media_integrity" in биті["checks"], биті
    assert зміст["class"] == "no_check", зміст


def test_variant_matches_the_log_not_the_prose():
    """Дискримінатор мусить працювати, коли прози немає взагалі — саме так
    приходить структурований вхід."""
    _fresh()
    r = vm.resolve(_v("form", ["Форма не найдена"], line=""), PHP)
    assert r["variant"], r


# --------------------------------------------------------------- правила

def test_yellow_is_never_routed():
    """Жовте не роутиться ніколи — навіть якщо ім'я веде в наш чек."""
    _fresh()
    r = vm.resolve(_v("links", ["404"], soft=True), PHP)
    assert r["class"] == "soft" and r["checks"] == [], r


def test_unknown_name_returns_none():
    """Незнайоме ім'я — не помилка, а сигнал «далі прозовим шляхом»."""
    _fresh()
    assert vm.resolve(_v("spellcheck2", ["щось нове"]), PHP) is None


def test_checks_are_narrowed_to_the_catalogue():
    """Вимкнений скіл ховає чек від моделі. Мапа не має стати дірою в цьому
    правилі: звужуємо завжди."""
    _fresh()
    r = vm.resolve(_v("links", ["404"]), available=["empty_href"])
    assert r["checks"] == ["empty_href"], r


def test_tool_failure_wins_over_everything():
    """Якщо прогін TSM зірвався, червоне після нього стосується
    недоперевіреної сторінки — у їхньому ж коментарі так і написано."""
    _fresh()
    out = vm.outcome([_v("run_timeout", ["снят по времени"]),
                      _v("links", ["404"])], PHP)
    assert out["tool_failure"] and out["checks"] == ["link_target", "empty_href"]


def test_outcome_keeps_unknown_names_apart():
    _fresh()
    out = vm.outcome([_v("links", ["404"]), _v("spellcheck2", ["?"])], PHP)
    assert [v["name"] for v in out["unknown"]] == ["spellcheck2"]


def test_outcome_dedups_checks_across_verdicts():
    _fresh()
    out = vm.outcome([_v("links", ["404"]), _v("buttons", ["href=#"])], PHP)
    assert len(out["checks"]) == len(set(out["checks"]))


# --------------------------------------------------------------- накладка

def test_overlay_wins_over_the_default():
    _fresh()
    vm.save({"key": "tsm:links", "class": "ours", "php": ["empty_href"],
             "reason": "правка людини", "by": "human"})
    r = vm.resolve(_v("links", ["404"]), PHP)
    assert r["checks"] == ["empty_href"] and r["by"] == "human", r


def test_deleting_the_record_restores_the_default():
    _fresh()
    vm.save({"key": "tsm:links", "class": "ours", "php": ["empty_href"]})
    assert vm.delete("tsm:links")
    r = vm.resolve(_v("links", ["404"]), PHP)
    assert "link_target" in r["checks"], r


def test_inactive_record_hides_the_name_entirely():
    """`active=false` означає «ми більше не знаємо цього імені» — далі воно
    піде прозовим шляхом, а не мовчки зароутиться дефолтом."""
    _fresh()
    vm.save({"key": "tsm:links", "class": "ours", "php": ["empty_href"],
             "active": False})
    assert vm.resolve(_v("links", ["404"]), PHP) is None


def test_bad_records_are_refused_with_a_human_message():
    _fresh()
    bad = [
        ({"key": "links", "class": "ours", "php": ["x"]}, "ключ"),
        ({"key": "tsm:links", "class": "выдумка"}, "клас"),
        ({"key": "tsm:links", "class": "ours"}, "ours"),
        ({"key": "tsm:links", "class": "not_ours", "php": ["forms"]}, "чеки"),
        ({"key": "tsm:links", "class": "ours", "php": ["forms"],
          "variants": [{"class": "ours", "php": ["forms"]}]}, "when"),
    ]
    for rec, hint in bad:
        try:
            vm.save(rec)
        except ValueError as e:
            assert hint in str(e), (rec, str(e))
        else:
            raise AssertionError(f"прийняли негодящий запис: {rec}")


def test_counters_are_kept_per_record():
    """`routed` без `fired` — найдешевша метрика якості мапи."""
    _fresh()
    vm.save({"key": "tsm:links", "class": "ours", "php": ["empty_href"]})
    vm.bump("tsm:links", "routed")
    vm.bump("tsm:links", "routed")
    vm.bump("tsm:links", "fired")
    st = vm.get("tsm:links")["stats"]
    assert st["routed"] == 2 and st["fired"] == 1, st


# ------------------------------------------- знайдено локальним стендом

def test_counters_work_for_a_record_that_lives_only_in_code():
    """Лічильники мусять рахуватись і для ДЕФОЛТІВ.

    Дефолти живуть у коді, а не у сховищі, тож `bump` по них мовчки не робив
    нічого — і метрика «кликали, а не спрацювало» була порожня рівно для тих
    записів, якими все й роутиться. Спіймано локальним стендом: 26 сценаріїв,
    лічильників нуль.
    """
    import tempfile
    from pathlib import Path
    vm.reset_for_tests(vm._FileStore(
        Path(tempfile.mkdtemp(prefix="vm-")) / "ai_verdicts.json"))
    assert vm.get("tsm:links")["by"] == "seed"          # запису в сховищі немає
    vm.bump("tsm:links", "routed")
    vm.bump("tsm:links", "routed")
    vm.bump("tsm:links", "fired")
    st = vm.get("tsm:links")["stats"]
    assert st["routed"] == 2 and st["fired"] == 1, st


def test_a_counter_record_never_overwrites_the_default():
    """Запис, що з'явився заради лічильника, — не накладка.

    Класти його зверху означало б стерти дефолт порожнім записом, тобто
    зламати роутинг рівно тим, що ми почали міряти його якість.
    """
    import tempfile
    from pathlib import Path
    vm.reset_for_tests(vm._FileStore(
        Path(tempfile.mkdtemp(prefix="vm-")) / "ai_verdicts.json"))
    vm.bump("tsm:links", "routed")
    rec = vm.get("tsm:links")
    assert rec["class"] == "ours" and "link_target" in rec["php"], rec
    assert vm.resolve(_v("links", ["404"]), PHP)["checks"], "дефолт стерто"


def test_a_real_edit_stops_being_a_counter_record():
    import tempfile
    from pathlib import Path
    vm.reset_for_tests(vm._FileStore(
        Path(tempfile.mkdtemp(prefix="vm-")) / "ai_verdicts.json"))
    vm.bump("tsm:links", "routed")
    vm.save({"key": "tsm:links", "class": "ours", "php": ["empty_href"]})
    assert vm.get("tsm:links")["php"] == ["empty_href"]


def test_a_verdict_the_map_understood_is_not_counted_as_drift():
    """Структурований вхід ми показуємо текстом у ЇХНЬОМУ фолбек-вигляді
    «имя: логи», а якорі такий рядок не знають за побудовою. Через це кожен
    успішно зароутований вердикт лічився ще й «нерозібраним», і на /ai це
    виглядало як «19 рядків не зрозуміли» там, де не зрозуміли жодного."""
    _fresh()
    import ai_router
    import ai_skills
    import ai_skills_store
    import tsm_ingest
    cards = ai_skills.catalog(runner.load_checks(), "php",
                              ai_skills_store.all_skills())
    env = tsm_ingest.ingest({"checks": [
        {"name": "links", "passed": False, "logs": ["• 404 — «Servicios»"]}]})
    r = ai_router.route(tsm_ingest.as_text(env), cards, use_model=False, env=env)
    впізнані = {h["name"] for h in r["map"]["hits"]}
    дрейф = [u for u in r["tsm"]["unknown"]
             if (u.get("tsm") or "") not in впізнані]
    assert "links" in впізнані and дрейф == [], (впізнані, дрейф)


if __name__ == "__main__":
    run(dict(globals()))
