"""Три мови інтерфейсу: цілість словника і підключення на кожній сторінці.

Механіка i18n тут навмисно без ключів: msgid — САМ український рядок, як у
gettext. Тому найдорожча помилка не «немає перекладу» (тоді просто лишиться
українська), а **зіпсований переклад**: шаблон, відкритий з обох боків і з
куцою літеральною частиною, — це регулярка на кшталт `^(.+?) з (.+?)$`, і
одного такого ключа досить, щоб покришити пів-екрана. Саме це тут і
стережеться.

Словник читає node — той самий парсер, що й у браузері, тож розбіжність між
тестом і живим екраном виключена.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

STATIC = ROOT / "static"
ENGINE = STATIC / "i18n.js"
DICT = STATIC / "i18n-dict.js"
HOLE = re.compile(r"\{(\d)\}")


def _node():
    return shutil.which("node")


def _dict() -> dict:
    """`{ключ: {"ru": ..., "en": ...}}` — прочитано так само, як браузером."""
    n = _node()
    if not n:
        return {}
    src = ("global.window={};" + DICT.read_text(encoding="utf-8")
           + "console.log(JSON.stringify(window.I18N_DICT));")
    f = tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False)
    f.write(src)
    f.close()
    try:
        r = subprocess.run([n, f.name], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        d = json.loads(r.stdout)
    finally:
        os.unlink(f.name)
    return {k: {"ru": d["ru"][k], "en": d["en"].get(k)} for k in d["ru"]}


def _t(lang: str, dictionary: dict, strings: list) -> list:
    """Ганяє СПРАВЖНІЙ рушій у node з підставним словником і заглушкою DOM.

    Так перевіряється саме те, що виконає браузер, а не переказ логіки на
    Python. `document.readyState = "loading"` тримає рушій до `start()`, тож
    жодного обходу DOM не відбувається — лишається чиста функція `t()`.
    """
    n = _node()
    if not n:
        return []
    src = ("""
global.window = { I18N_DICT: %s, console: console };
global.localStorage = { getItem: function () { return %s; }, setItem: function () {} };
global.document = { readyState: "loading", addEventListener: function () {},
                    documentElement: {}, title: "" };
%s
console.log(JSON.stringify(%s.map(function (s) { return window.I18N.t(s); })));
""" % (json.dumps(dictionary, ensure_ascii=False), json.dumps(lang),
       ENGINE.read_text(encoding="utf-8"), json.dumps(strings, ensure_ascii=False)))
    f = tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False)
    f.write(src)
    f.close()
    try:
        r = subprocess.run([n, f.name], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)
    finally:
        os.unlink(f.name)


# ------------------------------------------------------------------ фолбек

def test_a_missing_translation_falls_back_to_another_language():
    """Рядок, у якого є лише російський переклад, англійцю показується
    російською. «Хоч щось знайоме» краще за третю мову поспіль — і незмірно
    краще за порожнє місце."""
    got = _t("en", {"ru": {"Вітки": "Ветки"}, "en": {}}, ["Вітки"])
    assert got == ["Ветки"], got


def test_an_empty_translation_is_treated_as_missing():
    """Порожній рядок у словнику — це забутий переклад, а не «показати
    нічого»."""
    got = _t("en", {"ru": {"Вітки": "Ветки"}, "en": {"Вітки": ""}}, ["Вітки"])
    assert got == ["Ветки"], got


def test_the_chosen_language_still_wins():
    got = _t("en", {"ru": {"Вітки": "Ветки"}, "en": {"Вітки": "Branches"}}, ["Вітки"])
    assert got == ["Branches"], got


def test_nothing_anywhere_leaves_the_source():
    """Останній рубіж: жодного перекладу — лишається українська, і екран
    цілий."""
    got = _t("en", {"ru": {}, "en": {}}, ["Незнайомий рядок"])
    assert got == ["Незнайомий рядок"], got


def test_an_empty_dictionary_does_not_crash():
    got = _t("ru", {}, ["Вітки"])
    assert got == ["Вітки"], got


def test_a_broken_pattern_does_not_kill_the_rest():
    """Один кривий ключ не має гасити переклад усього застосунку."""
    d = {"ru": {"{0} ((( {1} зламаний": "х", "Вітки": "Ветки"}, "en": {}}
    assert _t("ru", d, ["Вітки"]) == ["Ветки"]


def test_patterns_work_through_the_fallback_too():
    d = {"ru": {"Закомічено у {0} віток": "Закоммичено в {0} веток"}, "en": {}}
    assert _t("en", d, ["Закомічено у 12 віток"]) == ["Закоммичено в 12 веток"]


def test_inner_whitespace_is_collapsed_before_lookup():
    """У розмітці довгий текст переноситься з відступами, а HTML показує його
    одним пробілом — без схлопування ключ не збігався саме на підказках."""
    d = {"ru": {"довга підказка тут": "длинная подсказка"}, "en": {}}
    assert _t("ru", d, ["  довга\n     підказка   тут  "]) == ["  длинная подсказка  "]


# ------------------------------------------------------------- підключення

def test_every_page_loads_the_dictionary_before_the_engine():
    """Порядок не косметичний: рушій читає `window.I18N_DICT` одразу на
    старті. Асинхронно вантажити теж не можна — сторінка встигне
    намалюватись українською і людина побачить блимання."""
    for f in sorted(STATIC.glob("*.html")):
        src = f.read_text(encoding="utf-8")
        d, e = src.find('src="/i18n-dict.js"'), src.find('src="/i18n.js"')
        assert d >= 0 and e >= 0, f"{f.name}: i18n не підключено"
        assert d < e, f"{f.name}: словник має йти ПЕРЕД рушієм"
        assert d < src.find("</head>"), f"{f.name}: скрипти мають бути в <head>"


def test_every_page_has_a_place_for_the_language_selector():
    """Без слота селектор падає у фіксований кут і накриває вміст."""
    orphans = [f.name for f in sorted(STATIC.glob("*.html"))
               if "data-i18n-slot" not in f.read_text(encoding="utf-8")]
    assert not orphans, f"немає місця під селектор мови: {orphans}"


def test_the_engine_and_the_dictionary_are_public():
    """Екран входу — єдина сторінка без сесії, і він теж має малюватись
    обраною мовою."""
    import auth
    assert "/i18n.js" in auth.PUBLIC_PATHS
    assert "/i18n-dict.js" in auth.PUBLIC_PATHS


def test_both_files_parse():
    n = _node()
    if not n:
        print("    (node немає — перевірка синтаксису пропущена)")
        return
    for path in (ENGINE, DICT):
        r = subprocess.run([n, "--check", str(path)], capture_output=True, text=True)
        assert r.returncode == 0, f"{path.name}: {r.stderr}"


# ------------------------------------------------------------------ словник

def test_every_key_has_both_languages():
    d = _dict()
    if not d:
        return
    bad = [k for k, v in d.items() if not v["ru"] or not v["en"]]
    assert not bad, f"без перекладу: {bad[:5]}"


def test_translations_keep_every_placeholder():
    """Загублена дірка — це загублене число на екрані, і мовчки."""
    d = _dict()
    for key, v in d.items():
        holes = set(HOLE.findall(key))
        if not holes:
            continue
        for lang in ("ru", "en"):
            assert set(HOLE.findall(v[lang])) == holes, \
                f"{lang}: дірки розійшлись у {key!r} → {v[lang]!r}"


def test_a_translation_never_invents_a_placeholder():
    d = _dict()
    for key, v in d.items():
        if HOLE.search(key):
            continue
        for lang in ("ru", "en"):
            assert not HOLE.search(v[lang]), f"{lang}: зайва дірка у {key!r}"


def test_no_pattern_is_open_at_both_ends_without_a_real_word():
    """Головна гарда файлу.

    `{0} з {1}` — це `^(.+?) з (.+?)$`, тобто БУДЬ-ЯКИЙ рядок зі словом «з»
    усередині. Спіймано на живому екрані: «, а не фраза з поради» ставало
    «, а не фраза of поради». Рушій такі ключі ігнорує, але лежати їм у
    словнику однаково нема чого — він обіцяв би те, чого не робить.
    """
    d = _dict()
    bad = []
    for key in d:
        if not (key.startswith("{") and key.endswith("}")):
            continue
        words = re.findall(r"[^\W\d_]+", HOLE.sub(" ", key), re.UNICODE)
        if max((len(w) for w in words), default=0) < 4:
            bad.append(key)
    assert not bad, f"надто загальні шаблони: {bad}"


def test_keys_are_trimmed_and_collapsed():
    """Рушій шукає по схлопнутих пробілах — ключ з подвійним пробілом або з
    краєм ніколи не збіжиться і мовчки нічого не перекладе."""
    d = _dict()
    bad = [k for k in d if k != re.sub(r"\s+", " ", k).strip()]
    assert not bad, f"ключі з зайвими пробілами: {bad[:5]}"


def test_the_dictionary_is_not_empty():
    d = _dict()
    if not _node():
        return
    assert len(d) > 500, f"у словнику лише {len(d)} ключів — щось загубилось"


def test_the_dictionary_is_revalidated_not_resent():
    """Словник — 200 КБ, і він у `<head>` СИНХРОННО на кожній сторінці.

    `FileResponse` віддає ETag, але `If-None-Match` не читає (це вміє лише
    `StaticFiles`), тож заміряно 02.09: файл приїжджав цілком на кожне
    завантаження будь-якої сторінки і затримував першу відмальовку. Тут
    закріплено, що повторний запит коштує 304 і нуль байтів.
    """
    import app

    class _Req:
        def __init__(self, tag=None):
            self.headers = {"if-none-match": tag} if tag else {}

    full = app._js("i18n-dict.js", _Req())
    assert full.status_code == 200 and len(full.body) > 10000, full.status_code
    tag = full.headers["etag"]
    again = app._js("i18n-dict.js", _Req(tag))
    assert again.status_code == 304, again.status_code
    assert not again.body, "304 не має нести тіла"
    assert app._js("i18n-dict.js", _Req('"чужа-мітка"')).status_code == 200


# ------------------------------------------------------- серверні рядки

CYR = re.compile(r"[А-Яа-яЇїІіЄєҐґ]")
# Поля відповіді, які UI показує людині як текст.
SHOWN = {"reason", "error", "detail", "message", "note", "why", "status_text", "err"}


def _server_messages() -> dict:
    """Українські рядки, які сервер віддає ЛЮДИНІ: тіло HTTPException і
    значення полів, що UI малює як текст. f-рядок стає шаблоном з дірками —
    саме таким його побачить перекладач у DOM."""
    import ast
    out = {}

    def template(node):
        parts, n = [], 0
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            else:
                parts.append("{%d}" % n)
                n += 1
        return "".join(parts)

    for f in sorted(ROOT.glob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            vals = []
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "HTTPException":
                vals = node.args[1:2]
            elif isinstance(node, ast.Dict):
                vals = [v for k, v in zip(node.keys, node.values)
                        if isinstance(k, ast.Constant) and k.value in SHOWN]
            elif isinstance(node, ast.Assign):
                # `rec["note"] = "…"` — так пише міст, і саме ці рядки людина
                # читає у смузі алертів і в коментарі ClickUp. Літералом
                # словника вони не є, тож гілка вище їх не бачила.
                for tgt in node.targets:
                    if (isinstance(tgt, ast.Subscript)
                            and isinstance(tgt.slice, ast.Constant)
                            and tgt.slice.value in SHOWN):
                        vals.append(node.value)
            for v in vals:
                if isinstance(v, ast.Constant) and isinstance(v.value, str) and CYR.search(v.value):
                    out[v.value] = f.name
                elif isinstance(v, ast.JoinedStr):
                    t = template(v)
                    if CYR.search(t):
                        out[t] = f.name
    return out


def test_every_message_the_server_shows_a_person_is_translated():
    """Тости з сервера — теж інтерфейс.

    Вони приходять текстом у відповіді й потрапляють у DOM, тобто
    перекладаються тим самим механізмом, що й розмітка, — але тільки якщо
    рядок є у словнику. Заміряно 02.09: таких рядків 120, і спершу з них не
    було перекладено ЖОДНОГО, хоча екран виглядав повністю перекладеним.
    Тому перевірка тут, а не на око.

    Впало? Додай рядок у `qa_lab-work/i18n/parts/12-server.json` (або 13) і
    перезбери словник: `python3 qa_lab-work/i18n/build.py`.
    """
    d = _dict()
    if not d:
        return
    miss = sorted(s for s in _server_messages() if s not in d)
    assert not miss, ("серверні повідомлення без перекладу (%d): %s"
                      % (len(miss), miss[:5]))


def test_the_sweep_actually_finds_something():
    """Гарда на гарду: якщо розбір колись перестане щось знаходити, тест
    вище стане зеленим і безкорисним."""
    assert len(_server_messages()) > 80, len(_server_messages())


# --------------------------------------------------------------- дані

def test_the_engine_never_touches_content():
    """Найгірше, що може зробити перекладач DOM, — «перекласти» вміст вітки.

    Диф, файл під підсвіткою, редактор і лог php — усе це текст З РЕПОЗИТОРІЮ,
    і рядок у ньому цілком може збігтися з фразою інтерфейсу. Тому рушій
    обходить `pre`, `code`, `textarea`, `script`, `style` — а тут перевірено,
    що саме в ці теги UI і кладе вміст.
    """
    engine = ENGINE.read_text(encoding="utf-8")
    skip = re.search(r"SKIP_TAGS = \{([^}]*)\}", engine)
    assert skip, "у рушії більше немає списку винятків"
    for tag in ("SCRIPT", "STYLE", "TEXTAREA", "PRE", "CODE"):
        assert tag in skip.group(1), f"{tag} зник зі списку винятків"

    index = (STATIC / "index.html").read_text(encoding="utf-8")
    for needle in ('<pre class="diff">', '<pre class="code hljs">',
                   '<textarea id="fEdit"', '<pre id="logOut"'):
        assert needle in index, f"вміст більше не в <pre>/<textarea>: {needle}"


run(dict(globals()))
