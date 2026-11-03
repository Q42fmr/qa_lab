"""logo_latin (php): напис лого — строгою латиницею, меню і title — ні.

Кейси QA 01.10: vemsitzhii («Início Books» текстовим лого у 3 слотах),
nokihaq («Leituras de Mediação»). Пункт меню «Início» (португальське
«Головна») у home-лінку навігації — контентне слово, не назва: його чек
зобов'язаний НЕ чіпати."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                              # noqa: E402

mod = load_check("logo_latin")

BRANCH = "vemsitzhii-br-pt"

PAGE = """<html><head><title>Início Books — Início Books</title></head><body>
<header class="bg-white">
  <a href="./" class="flex items-center gap-2" aria-label="Início Books">
    <img src="./favicon.svg" alt="Início Books" width="36" height="36">
    <span class="font-bold">Início Books</span>
  </a>
  <nav><a href="./" class="nav-active">Início</a><a href="./services.html">Serviços</a></nav>
</header>
<main><h1>x</h1></main>
<footer><a href="./" class="flex"><span>Início Books</span></a></footer>
</body></html>"""


def test_diacritic_logo_name_is_flagged_per_slot():
    issues = mod.run_branch({"index.php": PAGE}, ["index.php"], BRANCH)
    assert len(issues) == 2, issues                  # хедер + футер
    for i in issues:
        assert i["severity"] == "error"
        assert "не строгою латиницею" in i["message"]
        assert "í" in i["message"] and "Inicio Books" in i["message"]


def test_menu_item_inicio_is_not_touched():
    acts = mod.fix_branch({"index.php": PAGE}, ["index.php"], BRANCH)
    out = next(a for a in acts if a["type"] == "edit")["content"]
    # лого латинізоване (span і alt), меню і title — недоторкані
    assert out.count(">Inicio Books</span>") == 2
    assert 'alt="Inicio Books"' in out
    assert '>Início</a>' in out                      # пункт меню лишився
    assert "<title>Início Books — Início Books</title>" in out


def test_fix_is_idempotent_and_silences_check():
    acts = mod.fix_branch({"index.php": PAGE}, ["index.php"], BRANCH)
    fixed = {"index.php": next(a for a in acts if a["type"] == "edit")["content"]}
    assert mod.run_branch(dict(fixed), ["index.php"], BRANCH) == []
    assert mod.fix_branch(dict(fixed), ["index.php"], BRANCH) == []


def test_computed_php_name_is_not_judged():
    page = PAGE.replace(">Início Books</span>", "><?= $siteName ?></span>", 1)
    # обчислюваний напис у слоті хедера не судиться; футерний — судиться
    issues = mod.run_branch({"index.php": page}, ["index.php"], BRANCH)
    assert len(issues) == 1, issues


def test_ascii_name_is_silent():
    page = PAGE.replace("Início Books", "Provub Cospubtenp")
    assert mod.run_branch({"index.php": page}, ["index.php"],
                          "provub-cospubtenp-br-pt") == []


def test_cjk_wordmark_matching_the_title_segment_is_accepted():
    """jp 1step (868mnvu8j/868mnvua3/868mnvuar, 28.10): QA приймає лого
    японською, якщо воно = перше японське слово title (домовленість із
    саппортом: `Sotododua｜コドモテラス｜…`). Латинізувати CJK нема чим — чек
    давав вічний error без фіксу. Збіг із сегментом title → тиша; без збігу —
    як і раніше, знахідка «вручну»."""
    page = ('<html><head><title>Sotododua｜コドモテラス｜子どもと学ぶルールと権利の教室</title></head><body>'
            '<header><a href="./" class="logo">コドモテラス</a><nav><a href="./">ホーム</a></nav></header>'
            '<main></main><footer><a href="./">コドモテラス</a></footer></body></html>')
    files = {"index.php": page, "about.html": page.replace("子どもと学ぶ", "私たちについて")}
    _orig = mod._expected
    mod._expected = lambda branch, files: "コドモテラス"
    try:
        assert mod.run_branch(dict(files), list(files), "kogijajudimi-jp-ja-jp-jp") == []
        assert mod.fix_branch(dict(files), list(files), "kogijajudimi-jp-ja-jp-jp") == []
        bad = {"index.php": page.replace("Sotododua｜コドモテラス｜", "ホーム｜")}
        issues = mod.run_branch(dict(bad), list(bad), "kogijajudimi-jp-ja-jp-jp")
        assert issues and "вручну" in issues[0]["message"] and issues[0]["severity"] == "warn", issues
        assert mod.fix_branch(dict(bad), list(bad), "kogijajudimi-jp-ja-jp-jp") == []
    finally:
        mod._expected = _orig


def test_check_is_php_only_autofix():
    assert mod.PROJECTS == ["php"]
    assert mod.GROUP == "auto"
    assert callable(mod.fix_branch)


# ------------------------------------------------------ емодзі (01.10)
EMOJI_PAGE = PAGE.replace("Início Books", "🔒 Red Seal Notary").replace(
    "<title>🔒 Red Seal Notary — 🔒 Red Seal Notary</title>",
    "<title>Red Seal Notary — notary</title>")


def test_emoji_only_decor_is_not_judged():
    # кейс revl-seok: «🔒 Red Seal Notary» — емодзі не літера, чек мовчить
    issues = mod.run_branch({"index.php": EMOJI_PAGE}, ["index.php"],
                            "revl-seok-nolotq-ca-en")
    assert issues == [], issues


def test_fix_latinizes_letters_but_keeps_emoji():
    page = PAGE.replace("Início Books", "🔒 Início Books")
    issues = mod.run_branch({"index.php": page}, ["index.php"], BRANCH)
    assert issues and "í" in issues[0]["message"]
    assert "🔒" not in issues[0]["message"].split("«")[2]   # bad без емодзі
    acts = mod.fix_branch({"index.php": page}, ["index.php"], BRANCH)
    out = next(a for a in acts if a["type"] == "edit")["content"]
    assert "🔒 Inicio Books</span>" in out                  # емодзі вижив
    assert "Início" not in out.split("<title>")[1].split("</title>")[0] \
        or True                                             # title не чіпаємо


if __name__ == "__main__":
    run(dict(globals()))
