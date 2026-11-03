"""UID (CHE) на ch-de вайті: пул uid_pool + чек/фікс checks/uid_che."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run, load_check                    # noqa: E402

sys.path.insert(0, str(ROOT))

import projects                                               # noqa: E402
import uid_pool                                               # noqa: E402

mod = load_check("uid_che")

# реальні за структурою номери з валідною контрольною цифрою
VALID1 = "CHE-338.199.532"
VALID2 = "CHE-160.239.700"

PAGE = """<html lang="de-CH"><body>
<footer class="bg-zinc-900 py-10">
  <div class="wrap">
    <p class="font-sans text-sm text-gray-400">Praxis am See</p>
    <p class="font-sans text-xs text-gray-500">info@praxis.ch</p>
  </div>
</footer>
</body></html>
"""


def _fresh_pool(seed=False):
    d = Path(tempfile.mkdtemp(prefix="uid-"))
    projects.state_root = lambda: d
    uid_pool.SEED = (Path(uid_pool.__file__).resolve().parent / "uid_seed.json"
                     if seed else d / "no-seed.json")
    return d


# ------------------------------------------------------------------- пул

def test_canonical_accepts_every_common_spelling():
    for raw in ("CHE-338.199.532", "che338199532", "338199532", "CHE 338 199 532"):
        assert uid_pool.canonical(raw) == VALID1, raw
    assert uid_pool.canonical("CHE-334.240.01") == ""
    assert uid_pool.canonical("12.345.678/0001-90") == ""


def test_check_digit_is_mod_11_with_swiss_weights():
    assert uid_pool.valid(VALID1) and uid_pool.valid(VALID2)
    # остання цифра збита
    assert not uid_pool.valid("CHE-334.240.013")
    # плейсхолдер генератора: 1..9 дає остачу 10 → номер неможливий
    assert not uid_pool.valid("CHE-123.456.789")


def test_add_validates_and_rejects_duplicates():
    _fresh_pool()
    for bad in ("CHE-12", "CHE-334.240.013"):
        try:
            uid_pool.add(bad)
            assert False, bad
        except ValueError as e:
            assert "UID" in str(e)
    row = uid_pool.add("che338199532", company="BEISPIEL FIRMA 001 AG", city="Bern",
                       sphere="Медицина")
    assert row["uid"] == VALID1 and row["city"] == "Bern"
    try:
        uid_pool.add(VALID1)
        assert False
    except ValueError as e:
        assert "уже в пулі" in str(e)
    assert uid_pool.remove(VALID1) and not uid_pool.remove(VALID1)


def test_seed_has_500_valid_unique_numbers_by_sphere():
    _fresh_pool(seed=True)
    rows = uid_pool.load()
    nums = [r["uid"] for r in rows]
    assert len(nums) == 500 and len(set(nums)) == 500
    assert all(uid_pool.valid(n) for n in nums)
    spheres = {r["sphere"] for r in rows}
    assert spheres == {name for name, _ in uid_pool.SPHERES}, spheres


def test_sphere_matches_german_site_text():
    assert uid_pool.sphere_for("Zahnarztpraxis Dr. Keller — Zürich") == "Медицина"
    assert uid_pool.sphere_for("Fettmagv Buchhaltung online") == "Освіта"
    assert uid_pool.sphere_for("Treuhand und Steuerberatung Basel") == "Юристи/бухгалтерія"
    assert uid_pool.sphere_for("lorem ipsum") == ""


def test_pick_is_sticky_and_spreads_across_branches():
    _fresh_pool()
    uid_pool.add(VALID1); uid_pool.add(VALID2)
    first = uid_pool.pick("a-ch-de")
    assert first in (VALID1, VALID2) and uid_pool.pick("a-ch-de") == first
    for b in ("b-ch-de", "c-ch-de", "d-ch-de", "e-ch-de", "f-ch-de"):
        uid_pool.pick(b)
    counts = [list(uid_pool.assignments().values()).count(v) for v in (VALID1, VALID2)]
    assert counts == [3, 3], counts


# ------------------------------------------------------------------- чек

def test_only_ch_branches_are_judged_including_batch_suffix():
    _fresh_pool()
    files = {"index.html": PAGE}
    for other in ("nwf-casa-br-pt", "x-mx-es", "y-it-it"):
        assert mod.run_branch(dict(files), list(files), other) == []
        assert mod.fix_branch(dict(files), list(files), other) == []
    for ch in ("haofmcanm-ch-de", "fettmagv-ch-ch-de-2", "alpen.ch-de"):
        assert mod.run_branch(dict(files), list(files), ch), ch


def test_present_uid_keeps_the_check_silent():
    _fresh_pool()
    files = {"impressum.html": f"<footer><p>UID: {VALID1}</p></footer>"}
    assert mod.run_branch(dict(files), list(files), "a-ch-de") == []

def test_impressum_without_the_sites_uid_gets_it_under_the_address():
    """CH-DE 868mnmxpm (5 нумізматичних ch-fr віток, 27.10): UID є лише на
    politique-de-confidentialite.html, а QA вимагає його на Impressum
    («На странице Impressum нет регистрационного номера»). Фікс дописує
    «UID: CHE-…» (той самий номер сайту) після абзацу з адресою в Impressum,
    клонуючи його тег/клас; Impressum з UID — тиша."""
    _fresh_pool()
    priv = f'<html><body><main><h1>Politique</h1><p>Numéro IDE : {VALID1}</p></main></body></html>'
    imp = ('<html><body><main><h1>Impressum</h1><h2>1. Exploitant du site web</h2>'
           '<p class="text-sm">Hevlifup Tasis Guhooc</p>'
           '<p class="text-sm">Bahnhofstrasse 12, 8001 Zürich</p>'
           '<p class="text-sm">info@{{DOMAIN}}</p></main></body></html>')
    files = {"index.php": "<html><body><footer><p>© 2026</p></footer></body></html>",
             "impressum/index.html": imp, "politique-de-confidentialite.html": priv}
    issues = mod.run_branch(dict(files), list(files), "hevlifuptasisguhooc.ch-ch-fr")
    assert len(issues) == 1 and issues[0]["path"] == "impressum/index.html" and VALID1 in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "hevlifuptasisguhooc.ch-ch-fr")}
    assert set(acts) == {"impressum/index.html"}, acts.keys()
    new = acts["impressum/index.html"]
    assert f'<p class="text-sm">Bahnhofstrasse 12, 8001 Zürich</p><p class="text-sm">UID: {VALID1}</p>' in new, new
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "hevlifuptasisguhooc.ch-ch-fr") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "hevlifuptasisguhooc.ch-ch-fr") == []



def test_empty_pool_is_an_error_without_fix():
    _fresh_pool()
    files = {"index.html": PAGE}
    issues = mod.run_branch(dict(files), list(files), "a-ch-de")
    assert len(issues) == 1 and "пул номерів порожній" in issues[0]["message"]
    assert mod.fix_branch(dict(files), list(files), "a-ch-de") == []


def test_fix_clones_footer_p_with_styles_on_every_page():
    _fresh_pool()
    uid_pool.add(VALID1)
    files = {"index.html": PAGE, "about.html": PAGE,
             "src/components/Nav.vue": "<template><nav/></template>"}
    issues = mod.run_branch(dict(files), list(files), "a-ch-de")
    assert len(issues) == 1 and f"UID: {VALID1}" in issues[0]["message"]
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "a-ch-de")}
    assert set(acts) == {"index.html", "about.html"}
    assert f'<p class="font-sans text-xs text-gray-500">UID: {VALID1}</p>' in acts["index.html"]
    fixed = {**files, **acts}
    assert mod.fix_branch(dict(fixed), list(fixed), "a-ch-de") == []
    assert mod.run_branch(dict(fixed), list(fixed), "a-ch-de") == []


def test_placeholder_and_broken_check_digit_are_replaced_in_place():
    """builder-шаблон лишає «[Platzhalter CHE-Nummer]», генератор —
    CHE-123.456.789 (контрольна неможлива): обидва міняються на місці,
    підпис і стилі лишаються."""
    _fresh_pool()
    uid_pool.add(VALID1)
    files = {"impressum.html": ('<footer><p class="text-xs">Handelsregister-Nr.: '
                                '[Platzhalter CHE-Nummer]</p>'
                                '<p>UID CHE-123.456.789</p></footer>'),
             "index.html": PAGE}
    issues = mod.run_branch(dict(files), list(files), "a-ch-de")
    assert len(issues) == 1 and "фейковий UID" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "a-ch-de")}
    assert list(acts) == ["impressum.html"], acts
    new = acts["impressum.html"]
    assert f'<p class="text-xs">Handelsregister-Nr.: {VALID1}</p>' in new, new
    assert f"<p>UID {VALID1}</p>" in new, new
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "a-ch-de") == []


if __name__ == "__main__":
    run(dict(globals()))
