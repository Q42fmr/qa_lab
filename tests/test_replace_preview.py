"""Прев'ю замін мусить відрізняти «не знайшов» від «знайшов, але не міняє».

Корінь інциденту 25.08 (вітка `nwf-rimag-tegn-sojidiihr-co-es`). Вкладкою
«Заміни» користуються ще й як ПОШУКОМ: вписують шукане в обидва поля —
«Знайти» і «Замінити на» — щоб просто побачити, де воно є. Заміна тексту на
себе не міняє жодного файлу, а прев'ю рахує саме ЗМІНИ, тож панель писала
«збігів немає — жоден файл не зміниться». Виглядало як «пошук не працює»,
хоча збіги були: `@` у знімку Nuxt-вітки трапляється в кожному другому файлі.

Той самий текст видавали ще дві геть інші причини — порожній знімок
(вітку не синхронізовано) і фільтр, що нікого не пропустив. Три причини,
одна відповідь, жодного способу зрозуміти, що сталось.

Тому `preview()` тепер повертає розклад: скільки файлів у знімку, скільки
пройшло фільтр, скільки збігів і в яких файлах. Тут це і закріплено.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                          # noqa: E402

import projects                                                   # noqa: E402
import replacer                                                   # noqa: E402
import runner                                                     # noqa: E402

# Знімок навмисно node-подібний (.vue/.ts/.scss): саме на такій вітці все й
# знайшлось, а ці розширення потрапили в `runner.TEXT_EXT` пізніше за решту.
FILES = {
    "nuxt.config.ts": 'export default { mail: "info@rimiktoj.cyou" }\n',
    "components/Footer.vue": '<a href="mailto:soporte@rimiktoj.cyou">soporte@rimiktoj.cyou</a>\n',
    "assets/main.scss": '@import "vars";\n@media (max-width: 768px) { .w { padding: 8px } }\n',
    "package.json": '{"name":"nwf-probe"}\n',
    "logo.png": "not text\n",
}


def _snapshot(branch="nwf-probe", files=FILES):
    d = Path(tempfile.mkdtemp(prefix="repl-"))
    projects.state_dir = lambda: d
    snap = runner.snapshot_dir(branch)
    snap.mkdir(parents=True, exist_ok=True)      # порожній знімок — теж кейс
    for name, text in files.items():
        f = snap / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    (snap / ".snapshot.json").write_text(
        json.dumps({"branch": branch, "files": len(files), "commit": "abc12345"}),
        encoding="utf-8")
    return branch


def _preview(branch, **kw):
    params = {"branch": branch, "mode": "literal", "file_filter": "*",
              "ignore_case": False, "replace": ""}
    params.update(kw)
    return replacer.preview(branch, params)


# --------------------------------------------- головний кейс: пошук через заміну

def test_replacing_text_with_itself_still_reports_the_matches():
    """Те, що робив Олександр: `@` → `@`. Файли не міняються — збіги є."""
    br = _snapshot()
    p = _preview(br, find="@", replace="@")
    assert p["files_changed"] == 0, p["files_changed"]
    assert p["matches"] == 5, p["matches"]
    assert p["files_matched"] == 3, p["files_matched"]


def test_matched_files_are_listed_with_counts():
    """Список — це і є пошукова видача: де саме і скільки разів."""
    br = _snapshot()
    got = {m["path"]: m["count"] for m in _preview(br, find="@", replace="@")["matched"]}
    assert got == {"nuxt.config.ts": 1,          # info@…
                   "components/Footer.vue": 2,  # mailto:soporte@… + текст лінка
                   "assets/main.scss": 2}, got  # @import + @media


def test_a_real_replacement_still_reports_both_numbers():
    """Збіги рахуються завжди, не лише коли заміна порожня."""
    br = _snapshot()
    p = _preview(br, find="@", replace="#")
    assert p["files_changed"] == 3, p["files_changed"]
    assert p["matches"] == 5, p["matches"]


# --------------------------------------------- дві інші причини «нуль змін»

def test_empty_snapshot_is_distinguishable_from_no_matches():
    """Вітку не синхронізовано — це НЕ «збігів немає»."""
    br = _snapshot(files={})
    p = _preview(br, find="@", replace="#")
    assert p["files_total"] == 0, p["files_total"]
    assert p["files_scanned"] == 0, p["files_scanned"]


def test_a_filter_that_matches_nothing_is_distinguishable():
    """У знімку файли Є, але фільтр не пропустив жодного."""
    br = _snapshot()
    p = _preview(br, find="@", replace="#", file_filter="*.php")
    assert p["files_total"] == 5, p["files_total"]
    assert p["files_scanned"] == 0, p["files_scanned"]


def test_genuinely_absent_text_reports_zero_matches_but_files_scanned():
    """Чесний нуль: шукали, переглянули файли, не знайшли."""
    br = _snapshot()
    p = _preview(br, find="zzz-nope", replace="x")
    assert p["matches"] == 0, p["matches"]
    assert p["files_scanned"] == 4, p["files_scanned"]     # logo.png — не текст


# --------------------------------------------- решта режимів

def test_ignore_case_is_honoured_by_the_counter():
    """Лічильник мусить рахувати тим самим regex, що й заміна."""
    br = _snapshot()
    assert _preview(br, find="SOPORTE", replace="SOPORTE")["matches"] == 0
    assert _preview(br, find="SOPORTE", replace="SOPORTE",
                    ignore_case=True)["matches"] == 2   # у mailto: і в тексті лінка


def test_pairs_mode_counts_every_pair():
    br = _snapshot()
    p = _preview(br, mode="pairs", pairs=[{"find": "@", "replace": "@"},
                                          {"find": "rimiktoj", "replace": "rimiktoj"}])
    assert p["matches"] == 5 + 3, p["matches"]   # 5 разів «@» + 3 рази «rimiktoj»


def test_insert_mode_counts_the_anchor():
    """У вставці шукане — це якір: файл без нього не чіпається взагалі."""
    br = _snapshot(files={"index.html": "<head><title>x</title></head>\n"})
    p = _preview(br, mode="insert", snippet='<link rel="icon" href="/f.ico">',
                 anchor="</head>")
    assert p["matches"] == 1, p["matches"]
    assert p["files_changed"] == 1, p["files_changed"]


def test_insert_is_idempotent_and_says_so():
    """Фрагмент уже на місці: якір знайдено, змін нема — саме той випадок,
    заради якого лічильник і відділено від diff'а."""
    br = _snapshot(files={"index.html": '<head><link rel="icon" href="/f.ico"></head>\n'})
    p = _preview(br, mode="insert", snippet='<link rel="icon" href="/f.ico">',
                 anchor="</head>")
    assert p["matches"] == 1, p["matches"]
    assert p["files_changed"] == 0, p["files_changed"]


def test_script_mode_reports_unknown_instead_of_zero():
    """Що саме шукає трансформ — знає лише він сам. Прикинутись, що збігів
    нуль, було б брехнею того самого штибу, від якої тут лікуємось."""
    br = _snapshot()
    transforms = [t for t in replacer.load_transforms() if t.get("module")]
    if not transforms:
        return                                    # у дереві без transforms/ — нема що ганяти
    p = _preview(br, mode="script", script=transforms[0]["id"])
    assert p["matches"] is None, p["matches"]
    assert p["files_scanned"] >= 0


# --------------------------------------------- обрізання довгого списку

def test_matched_list_is_capped_and_says_so():
    """На широкому шаблоні список зі збігами — це вся вітка."""
    many = {f"p{i}.html": "<b>@</b>\n" for i in range(replacer.MAX_MATCHED + 5)}
    br = _snapshot(files=many)
    p = _preview(br, find="@", replace="@")
    assert p["files_matched"] == len(many), p["files_matched"]
    assert len(p["matched"]) == replacer.MAX_MATCHED, len(p["matched"])
    assert p["matched_truncated"] is True


# --------------------------------------------- режим «футер»: клон <p> зі стилями
FOOTER_PAGE = """<html><body>
<footer class="bg-zinc-900">
  <div class="wrap">
    <p class="font-sans text-sm text-gray-400">Remalo Luhiime</p>
    <p class="font-sans text-xs text-gray-500"><a href="mailto:info@old.com" class="hover:underline">info@old.com</a></p>
  </div>
</footer>
</body></html>
"""


def _footer_preview(branch, **kw):
    params = {"branch": branch, "mode": "footer", "file_filter": "*.html",
              "find": "", "replace": ""}
    params.update(kw)
    return replacer.preview(branch, params)


def test_footer_clones_marked_p_with_styles_and_href():
    br = _snapshot(files={"index.html": FOOTER_PAGE})
    p = _footer_preview(br, find="info@old.com", replace="info2@new.com")
    assert p["files_changed"] == 1, p
    new = [l for l in p["diffs"][0]["diff"].splitlines() if l.startswith("+")]
    added = "\n".join(new)
    # клон успадкував ВСІ стилі і став лінком на нову пошту
    assert 'class="font-sans text-xs text-gray-500"' in added, added
    assert 'href="mailto:info2@new.com"' in added, added
    assert ">info2@new.com<" in added, added


def test_footer_without_marker_clones_last_p_tag_only():
    br = _snapshot(files={"index.html": FOOTER_PAGE})
    p = _footer_preview(br, replace="CNPJ 12.345.678/0001-90")
    added = "\n".join(l for l in p["diffs"][0]["diff"].splitlines()
                      if l.startswith("+") and not l.startswith("+++"))
    assert '<p class="font-sans text-xs text-gray-500">CNPJ 12.345.678/0001-90</p>' \
        in added, added


def test_footer_is_idempotent_and_skips_files_without_footer():
    files = {"index.html": FOOTER_PAGE,
             "about.html": "<html><body><p>про нас</p></body></html>"}
    br = _snapshot(files=files)
    p = _footer_preview(br, find="info@old.com", replace="info2@new.com")
    assert {d["path"] for d in p["diffs"]} == {"index.html"}, p
    # другий прохід по вже зміненому файлу — нуль правок
    changed = replacer._compute_changes(
        br, {"mode": "footer", "file_filter": "*.html",
             "find": "info@old.com", "replace": "info2@new.com"})
    twice = replacer._footer_append("info2@new.com", "info@old.com")(
        "index.html", changed[0]["new"])
    assert twice == changed[0]["new"]


def test_footer_empty_text_is_an_error():
    br = _snapshot(files={"index.html": FOOTER_PAGE})
    try:
        _footer_preview(br, replace="")
        assert False, "порожній текст мав дати помилку"
    except ValueError as e:
        assert "порожній" in str(e)


if __name__ == "__main__":
    run(dict(globals()))
