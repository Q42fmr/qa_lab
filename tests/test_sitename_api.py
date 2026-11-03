"""Ендпоінт планової зміни назви сайту (/api/sitename/rename).

Контракти: old за замовчуванням — поточна назва з title; rename міняє
title і капіталізовані згадки, слаги/пошти цілі; ОДИН коміт; «назви не
знайдено» — чесна 400; знімок оновлюється.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                               # noqa: E402

sys.path.insert(0, str(ROOT))
os.environ.setdefault("MOCK_MODE", "1")

import app                                                   # noqa: E402
import projects                                              # noqa: E402
import runner as rn                                          # noqa: E402

BR = "lulugii-it-it"
FILES = {
    "index.php": ('<html><head><title>Lulugii — orologeria di lusso</title>'
                  '<meta property="og:site_name" content="Lulugii"></head>'
                  '<body><h1>Lulugii</h1>'
                  '<a href="https://instagram.com/lumeriaorologi">IG</a>'
                  '<p>info@lulugii.pro</p></body></html>'),
    "about.html": "<title>Chi siamo — Lulugii</title><p>LULUGII srl</p>",
}


class _Commits:
    def __init__(self):
        self.calls = []

    def commit(self, branch, message, actions):
        self.calls.append({"branch": branch, "message": message,
                           "actions": actions})
        return {"id": "beefcafe"}


def _setup():
    d = Path(tempfile.mkdtemp(prefix="sn-"))
    projects.state_dir = lambda: d
    snap = rn.snapshot_dir(BR)
    for name, text in FILES.items():
        f = snap / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    rn.is_synced = lambda _b: True
    fake = _Commits()
    app.client = fake
    return fake


def test_rename_updates_title_and_mentions_keeping_slugs():
    fake = _setup()
    assert app.sitename_current(BR)["name"] == "Lulugii"
    r = app.sitename_rename(app.SiteRenameRequest(
        branch=BR, new_name="Lulugii Horology"))
    assert r["committed"] and r["old"] == "Lulugii"
    assert r["now"] == "Lulugii Horology", r
    acts = {a["file_path"]: a["content"] for a in fake.calls[0]["actions"]}
    idx = acts["index.php"]
    assert "<title>Lulugii Horology — orologeria" in idx
    assert 'content="Lulugii Horology"' in idx
    assert "<h1>Lulugii Horology</h1>" in idx
    assert "instagram.com/lumeriaorologi" in idx      # слаг цілий
    assert "info@lulugii.pro" in idx                  # пошта ціла
    assert "LULUGII HOROLOGY srl" in acts["about.html"]
    # знімок оновлено — повторний виклик уже без змін
    r2 = app.sitename_rename(app.SiteRenameRequest(
        branch=BR, new_name="Lulugii Horology"))
    assert r2["committed"] is False and "вже така" in r2["reason"], r2


def test_explicit_old_name_and_missing_name_400():
    _setup()
    try:
        app.sitename_rename(app.SiteRenameRequest(
            branch=BR, new_name="X", old_name="Neverwas"))
        assert False
    except Exception as e:
        assert "не знайдено" in str(e)


if __name__ == "__main__":
    run(dict(globals()))
