"""Ручний вибір цілі для лінків, які чек не може розвʼязати сам.

`link_target` лагодить лише те, де ціль однозначна. Решта — 371 лінк корпусу
на кшталт `services.html` у юридичному шаблоні — це не описка шляху, а
питання «а яка сторінка тут мала бути». Відповідь дає людина, але не руками
по файлах: групуємо ОДНАКОВІ биті лінки в один вибір і підставляємо
обраний файл у всі його входження.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, load_check, run                   # noqa: E402

sys.path.insert(0, str(ROOT))

mod = load_check("link_target")

PAGES = ["index.html", "contact.html", "practice.html", "attorneys.html",
         "blog/post.html"]


def _files(**pages):
    return dict(pages)


def _dead(files, all_paths=None):
    return mod.dead_links(files, all_paths or (list(files) + PAGES))


# ------------------------------------------------------------ групування
def test_same_dead_link_from_many_places_is_one_choice():
    files = {
        "index.html": '<a href="services.html">A</a>\n<a href="services.html">B</a>',
        "contact.html": '<a href="services.html">C</a>',
    }
    groups = _dead(files)
    assert [g["href"] for g in groups] == ["services.html"], groups
    g = groups[0]
    assert g["count"] == 3, g
    assert {u["path"] for u in g["usages"]} == {"index.html", "contact.html"}
    assert sorted(u["line"] for u in g["usages"] if u["path"] == "index.html") == [1, 2]


def test_different_dead_links_are_separate_choices():
    files = {"index.html": '<a href="servicos">A</a><a href="contato">B</a>'}
    assert sorted(g["href"] for g in _dead(files)) == ["contato", "servicos"]


def test_resolvable_link_is_not_offered_for_a_choice():
    """`practice` → practice.html чек лагодить сам, питати нема про що."""
    files = {"index.html": '<a href="practice">A</a>'}
    assert _dead(files) == []


def test_healthy_and_external_links_are_ignored():
    files = {"index.html": '<a href="contact.html">ok</a>'
                           '<a href="https://x.dev/a">ext</a>'
                           '<a href="#form">anchor</a>'
                           '<a href="/about">root</a>'}
    assert _dead(files) == []


def test_candidates_are_the_pages_of_the_branch():
    files = {"index.html": '<a href="services.html">A</a>'}
    groups = _dead(files, list({"index.html"}) + PAGES + ["assets/app.js"])
    assert "practice.html" in groups[0]["candidates"]
    assert "assets/app.js" not in groups[0]["candidates"], "js не сторінка"


def test_suggestion_points_at_the_closest_page():
    """`atorneys` — не префікс `attorneys`, автофікс мовчить; підказка є."""
    files = {"index.html": '<a href="atorneys.html">A</a>'}
    assert _dead(files)[0]["suggest"] == "attorneys.html"


def test_no_suggestion_when_nothing_is_close():
    files = {"index.html": '<a href="zzzzzz.html">A</a>'}
    assert _dead(files)[0]["suggest"] is None


# --------------------------------------------------------------- заміна
def test_choice_is_applied_to_every_usage():
    files = {
        "index.html": '<a href="services.html">A</a>\n<a href="services.html">B</a>',
        "contact.html": '<a href="services.html">C</a>',
    }
    acts = mod.apply_choices(files, list(files) + PAGES,
                             {"services.html": "practice.html"})
    out = {a["path"]: a["content"] for a in acts}
    assert out["index.html"].count('href="practice.html"') == 2
    assert out["contact.html"].count('href="practice.html"') == 1
    assert "services.html" not in out["index.html"]


def test_query_and_anchor_survive():
    files = {"index.html": '<a href="servicos?a=1#top">A</a>'}
    acts = mod.apply_choices(files, list(files) + PAGES, {"servicos?a=1#top": "practice.html"})
    assert 'href="practice.html?a=1#top"' in acts[0]["content"]


def test_path_is_relative_to_the_page():
    """Зі сторінки в підтеці коренева ціль має лишитись `../`."""
    files = {"blog/post.html": '<a href="servicos">A</a>'}
    acts = mod.apply_choices(files, list(files) + PAGES, {"servicos": "contact.html"})
    assert 'href="../contact.html"' in acts[0]["content"], acts[0]["content"]


def test_other_links_and_plain_text_are_untouched():
    files = {"index.html": '<p>servicos</p><a href="contact.html">ok</a>'
                           '<a href="servicos">bad</a>'}
    acts = mod.apply_choices(files, list(files) + PAGES, {"servicos": "practice.html"})
    out = acts[0]["content"]
    assert "<p>servicos</p>" in out, "текст сторінки не чіпаємо"
    assert 'href="contact.html"' in out
    assert out.count('href="practice.html"') == 1


def test_unknown_target_is_refused():
    files = {"index.html": '<a href="servicos">A</a>'}
    try:
        mod.apply_choices(files, list(files) + PAGES, {"servicos": "nema.html"})
    except ValueError as e:
        assert "nema.html" in str(e)
    else:
        raise AssertionError("ціль, якої немає у вітці, приймати не можна")


def test_empty_choice_changes_nothing():
    files = {"index.html": '<a href="servicos">A</a>'}
    assert mod.apply_choices(files, list(files) + PAGES, {"servicos": ""}) == []
    assert mod.apply_choices(files, list(files) + PAGES, {}) == []


def test_applied_choice_clears_the_check():
    files = {"index.html": '<a href="servicos">A</a>'}
    paths = list(files) + PAGES
    acts = mod.apply_choices(files, paths, {"servicos": "practice.html"})
    fixed = {**files, **{a["path"]: a["content"] for a in acts}}
    assert mod.dead_links(fixed, paths) == []
    assert mod.run_branch(fixed, paths) == []


# ------------------------------------------------- ендпоінт /api/links/fix
# Тест не чіпає ні GitLab, ні реальні вітки: підмінює client і шляхи знімка.
def _app_with_fakes(files: dict, all_paths: list[str], tmp):
    os.environ.setdefault("MOCK_MODE", "1")
    import app
    import runner as rn

    saved = (app.client, rn.snapshot_files, rn.read_snapshot_file,
             rn.snapshot_dir, rn.is_synced, app.log_commit)
    box = {"commit": None}

    class FakeClient:
        def commit(self, branch, message, actions):
            box["commit"] = {"branch": branch, "message": message, "actions": actions}
            return {"id": "c0ffee"}

    app.client = FakeClient()
    rn.snapshot_files = lambda branch: all_paths
    rn.read_snapshot_file = lambda branch, path: files.get(path, "").encode()
    rn.snapshot_dir = lambda branch: tmp
    rn.is_synced = lambda branch: True
    app.log_commit = lambda *a, **k: None
    return app, saved, box


def _restore(saved):
    import app
    import runner as rn
    (app.client, rn.snapshot_files, rn.read_snapshot_file,
     rn.snapshot_dir, rn.is_synced, app.log_commit) = saved


def test_endpoint_commits_one_choice_into_every_page():
    import shutil
    import tempfile
    files = {"index.html": '<a href="servicos">A</a>',
             "contact.html": '<a href="servicos">B</a>'}
    paths = list(files) + PAGES
    tmp = ROOT / "tests" / "_tmp_links"
    shutil.rmtree(tmp, ignore_errors=True)
    for p in files:
        (tmp / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp / p).write_text(files[p], encoding="utf-8")
    app, saved, box = _app_with_fakes(files, paths, tmp)
    try:
        groups = app.links_dead("br")["groups"]
        assert [g["href"] for g in groups] == ["servicos"], groups
        r = app.links_fix(app.LinksFixRequest(
            branch="br", choices={"servicos": "practice.html"}, message="fix: links"))
        assert r["committed"] and r["links"] == 1, r
        assert sorted(r["files"]) == ["contact.html", "index.html"], r
        # у коміт пішли обидві сторінки з підставленою ціллю
        acts = {a["file_path"]: a["content"] for a in box["commit"]["actions"]}
        assert all('href="practice.html"' in c for c in acts.values()), acts
        # знімок на диску теж оновлено — інакше чек далі бачив би старе
        assert 'href="practice.html"' in (tmp / "index.html").read_text(encoding="utf-8")
    finally:
        _restore(saved)
        shutil.rmtree(tmp, ignore_errors=True)


def test_endpoint_refuses_a_target_that_is_not_in_the_branch():
    from fastapi import HTTPException
    files = {"index.html": '<a href="servicos">A</a>'}
    app, saved, box = _app_with_fakes(files, list(files) + PAGES, ROOT / "tests")
    try:
        app.links_fix(app.LinksFixRequest(branch="br", choices={"servicos": "nema.html"},
                                          message="m"))
    except HTTPException as e:
        assert e.status_code == 400 and "nema.html" in e.detail
    else:
        raise AssertionError("мусило впасти 400")
    finally:
        _restore(saved)
    assert box["commit"] is None, "коміт не мав відбутись"


def test_endpoint_says_nothing_to_do_on_empty_choices():
    files = {"index.html": '<a href="servicos">A</a>'}
    app, saved, box = _app_with_fakes(files, list(files) + PAGES, ROOT / "tests")
    try:
        r = app.links_fix(app.LinksFixRequest(branch="br", choices={}, message="m"))
        assert r == {"committed": False, "reason": "нема що міняти", "files": []}, r
    finally:
        _restore(saved)
    assert box["commit"] is None


if __name__ == "__main__":
    run(dict(globals()))
