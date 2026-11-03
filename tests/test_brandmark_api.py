"""Ендпоінти знаку бренду: /api/brandmark/variants і /apply.

Контракти: variants — детермінована розгортка з theme-color вітки; apply
збирає ОДИН коміт (logo.svg лише для node-проєкту, favicon.svg + лінки
сторінок через favicon.fix_branch) і оновлює локальний знімок.
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

BR = "nwf-provub-cospubtenp-br-pt"
FILES = {
    "index.html": ('<!DOCTYPE html><html><head><title>Provub Cospubtenp — '
                   'consultoria</title><meta name="theme-color" content="#1e40af">'
                   '</head><body>x</body></html>'),
    "src/components/MainNavigation.vue": "<template><header/></template>",
    # vue-вітка: серветься САМЕ public/ (кейс groriboa-praveiv 30.09);
    # мертвий кореневий favicon лишився від старого apply
    "public/favicon.svg": "<svg>old</svg>",
    "favicon.svg": "<svg>stray</svg>",
}


class _Commits:
    def __init__(self):
        self.calls = []

    def commit(self, branch, message, actions):
        self.calls.append({"branch": branch, "message": message,
                           "actions": actions})
        return {"id": "deadbeef"}


def _setup():
    d = Path(tempfile.mkdtemp(prefix="bm-"))
    projects.state_dir = lambda: d
    snap = rn.snapshot_dir(BR)
    for name, text in FILES.items():
        f = snap / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    rn.is_synced = lambda _b: True
    projects.ptype = lambda: "node"
    fake = _Commits()
    app.client = fake
    return fake


def test_variants_derive_from_branch_and_theme_color():
    _setup()
    out = app.brandmark_variants(BR, count=12)
    assert out["name"] == "Provub Cospubtenp"
    assert out["letters"] == "PC"
    assert len(out["variants"]) == 12
    assert out["base_color"].startswith("#")
    again = app.brandmark_variants(BR, count=12)
    assert [v["svg"] for v in out["variants"]] == \
        [v["svg"] for v in again["variants"]], "розгортка мусить бути детермінованою"


def test_apply_targets_public_favicon_and_purges_root_stray():
    fake = _setup()
    out = app.brandmark_variants(BR, count=12)
    r = app.brandmark_apply(app.BrandmarkApplyRequest(
        branch=BR, variant=3, targets=["logo", "favicon"]))
    assert r["committed"] and r["commit"] == "deadbeef"
    assert len(fake.calls) == 1, "має бути ОДИН коміт"
    acts = {a["file_path"]: a for a in fake.calls[0]["actions"]}
    assert "src/assets/images/logo.svg" in acts
    # node: знак їде у public/ — корінь репо Vite не серве
    assert acts["public/favicon.svg"]["action"] == "update"
    assert acts["public/favicon.svg"]["content"] == out["variants"][3]["svg"]
    assert acts["favicon.svg"]["action"] == "delete"
    # index.html вже має <link rel="icon"> — не чіпаємо
    assert "index.html" not in acts or "icon" in acts["index.html"]["content"]
    # локальний знімок: public оновлено, кореневий видалено
    assert (rn.snapshot_dir(BR) / "public/favicon.svg").read_text(
        encoding="utf-8") == out["variants"][3]["svg"]
    assert not (rn.snapshot_dir(BR) / "favicon.svg").exists()


def test_apply_inserts_versioned_icon_link_when_index_lacks_one():
    fake = _setup()
    app.brandmark_apply(app.BrandmarkApplyRequest(
        branch=BR, variant=0, targets=["favicon"]))
    acts = {a["file_path"]: a for a in fake.calls[0]["actions"]}
    import re
    m = re.search(r'rel="icon" href="/favicon\.svg\?v=([0-9a-f]{8})"',
                  acts["index.html"]["content"])
    assert m, acts["index.html"]["content"]


def test_apply_rebusts_existing_icon_link():
    # лінк уже є — отримує нову версію ?v= (кеш спільного прев'ю-хоста)
    fake = _setup()
    FILES["index.html"] = FILES["index.html"].replace(
        "</head>", '<link rel="icon" href="/favicon.svg" type="image/svg+xml"></head>')
    try:
        out = app.brandmark_variants(BR, count=12)
        app.brandmark_apply(app.BrandmarkApplyRequest(
            branch=BR, variant=2, targets=["favicon"]))
    finally:
        FILES["index.html"] = FILES["index.html"].replace(
            '<link rel="icon" href="/favicon.svg" type="image/svg+xml"></head>',
            "</head>")
    acts = {a["file_path"]: a for a in fake.calls[0]["actions"]}
    import re, zlib
    ver = f"{zlib.crc32(out['variants'][2]['svg'].encode('utf-8')) & 0xffffffff:08x}"
    assert f'href="/favicon.svg?v={ver}"' in acts["index.html"]["content"]


def test_variants_seed_roundtrip_into_apply():
    fake = _setup()
    out = app.brandmark_variants(BR, count=24, seed=42)
    assert out["seed"] == 42 and len(out["variants"]) == 24
    assert out["pool"] >= 200
    # варіант з розширення пулу: apply з тим САМИМ seed комітить саме його
    app.brandmark_apply(app.BrandmarkApplyRequest(
        branch=BR, variant=20, seed=42, targets=["favicon"]))
    acts = {a["file_path"]: a for a in fake.calls[0]["actions"]}
    assert acts["public/favicon.svg"]["content"] == out["variants"][20]["svg"]


def test_apply_php_replaces_photo_logo_slot():
    # php-сторінка: стокове фото в home-лінку хедера — Apply з target logo
    # має переписати src на знак (кейс anezo-br-pt 01.10)
    FILES["index.php"] = ('<html><head><title>Provub Cospubtenp — x</title>'
                          '</head><body><header>'
                          '<a href="./" class="flex"><img '
                          'src="https://img.b2bpic.net/premium-photo/x.jpg" '
                          'alt="Praxis" class="h-8"></a></header></body></html>')
    fake = _setup()
    projects.ptype = lambda: "php"
    try:
        out = app.brandmark_variants(BR, count=12, seed=5)
        r = app.brandmark_apply(app.BrandmarkApplyRequest(
            branch=BR, variant=1, seed=5, targets=["logo", "favicon"]))
    finally:
        FILES.pop("index.php", None)
    acts = {a["file_path"]: a for a in fake.calls[0]["actions"]}
    assert "src/assets/images/logo.svg" not in acts, acts.keys()
    assert acts["favicon.svg"]["action"] == "update"
    assert acts["favicon.svg"]["content"] == out["variants"][1]["svg"]
    page = acts["index.php"]["content"]
    assert 'src="./favicon.svg?v=' in page, page      # фото-лого → знак (з версією)
    assert "b2bpic" not in page
    assert "public/favicon.svg" not in acts
    assert all(a["action"] != "delete" for a in acts.values())


def test_apply_php_swaps_generator_badge_and_versions_links():
    # кейс alnewvad/quuskafs 01.10: лінк ./favicon.svg БЕЗ файла + інлайн-SVG
    # бейдж у home-лінку. Apply: лінк версіонується force-ом, бейдж → <img>
    FILES["index.php"] = ('<html><head><title>Alnewvad Cinco — x</title>\n'
                          '<link rel="icon" type="image/svg+xml" '
                          'href="./favicon.svg">\n'
                          '</head><body><header>'
                          '<a class="flex" href="./">'
                          '<svg viewBox="0 0 48 48" width="40" height="40">'
                          '<defs><linearGradient id="badge-grad">'
                          '<stop offset="0" stop-color="#1B2A52"/>'
                          '</linearGradient></defs>'
                          '<rect x="4" y="4" width="40" height="40" rx="10" '
                          'fill="url(#badge-grad)"/>'
                          '<text x="24" y="32">AC</text></svg>'
                          '<span>Alnewvad Cinco</span></a>'
                          '</header></body></html>')
    fake = _setup()
    projects.ptype = lambda: "php"
    try:
        app.brandmark_variants(BR, count=12, seed=5)
        app.brandmark_apply(app.BrandmarkApplyRequest(
            branch=BR, variant=1, seed=5, targets=["logo", "favicon"]))
    finally:
        FILES.pop("index.php", None)
    acts = {a["file_path"]: a for a in fake.calls[0]["actions"]}
    page = acts["index.php"]["content"]
    assert '<link rel="icon" type="image/svg+xml" href="./favicon.svg?v=' \
        in page, page
    assert "<text" not in page                        # бейдж-монограми немає
    assert '<img src="./favicon.svg?v=' in page       # лого — знак
    assert 'width="40" height="40">' in page          # розмір перенесено
    assert "Alnewvad Cinco</span>" in page

if __name__ == "__main__":
    run(dict(globals()))
