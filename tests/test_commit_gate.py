"""Гейт коміту (commit_gate): невідомі {{UPPER}}-токени не доїжджають до
GitLab, а правка ассетів «на місці» попереджає про 30-денний кеш Cloudflare."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

sys.path.insert(0, str(ROOT))
import commit_gate                                                # noqa: E402
from gitlab_client import MockClient                              # noqa: E402


def _act(path, content, action="update", **kw):
    return {"action": action, "file_path": path, "content": content, **kw}


def test_unknown_upper_tokens_are_removed_but_domain_literals_stay():
    """Деплой (placeholders_sed.sh) падає на будь-якому невідомому {{UPPER}}
    у html/php/xml/txt/json; підставляються лише {{DOMAIN}} і {{DOMAIN_NAME}}.
    Гейт прибирає зайві токени з контенту коміту і каже, що саме прибрав."""
    acts = [_act("index.php", '<p>O {{BRAND}} atende {{CITY}} — <a href="mailto:info@{{DOMAIN}}">info@{{DOMAIN}}</a> {{DOMAIN_NAME}}</p>'),
            _act("feed.xml", "<title>{{BRAND}} news</title>"),
            _act("data.json", '{"name": "{{BRAND}}", "n": "{{COUNT}}"}')]
    out, notes = commit_gate.apply(acts)
    assert out[0]["content"] == '<p>O atende — <a href="mailto:info@{{DOMAIN}}">info@{{DOMAIN}}</a> {{DOMAIN_NAME}}</p>', out[0]["content"]
    assert out[1]["content"] == "<title>news</title>"
    assert out[2]["content"] == '{"name": "", "n": ""}'
    assert any("{{BRAND}}" in n and "index.php" in n for n in notes), notes
    assert any("feed.xml" in n for n in notes) and any("data.json" in n for n in notes)


def test_base64_text_files_from_local_changes_are_cleaned_too():
    """«Локальні зміни» шлють файли base64 — html з токеном чиститься, бінарник ні."""
    import base64
    enc = lambda s: base64.b64encode(s.encode("utf-8")).decode()
    acts = [_act("about.html", enc("<p>{{BRAND}} tel</p>"), encoding="base64"),
            _act("img.png", base64.b64encode(b"\x89PNG\x00\xff").decode(), action="create", encoding="base64")]
    out, notes = commit_gate.apply(acts)
    assert base64.b64decode(out[0]["content"]).decode("utf-8") == "<p>tel</p>"
    assert out[1] == acts[1] and len(notes) == 1 and "about.html" in notes[0]


def test_lowercase_spaced_and_code_tokens_are_not_the_gate_s_business():
    """{{ title }} у Vue-шаблоні, {{x}} маленькими, ${BRAND} — не те, що ламає
    деплой; css/js/vue/md гейт не читає взагалі; base64-ассети — тим паче."""
    acts = [_act("index.html", "<h1>{{ title }}</h1><p>{{x}} ${BRAND}</p>"),
            _act("app.css", ".a{content:'{{BRAND}}'}", action="create"),
            _act("logo.png", "AAAA", action="create", encoding="base64"),
            {"action": "delete", "file_path": "old.html"}]
    out, notes = commit_gate.apply(acts)
    assert [a.get("content") for a in out] == [a.get("content") for a in acts]
    assert notes == []


def test_in_place_asset_update_warns_about_the_cdn_cache_but_creation_does_not():
    """Cloudflare тримає CSS/JS/картинки 30 днів immutable: змінений файл під
    тією самою назвою відвідувач не побачить. Update ассета — попередження з
    переліком файлів; create (нове ім'я) — ні; html не ассет."""
    acts = [_act("assets/site.css", "body{}"), _act("assets/app.js", "1"),
            _act("img/hero.jpg", "AAAA", encoding="base64"),
            _act("assets/site.abc123.css", "body{}", action="create"),
            _act("index.html", "<p>x</p>")]
    out, notes = commit_gate.apply(acts)
    cache = [n for n in notes if "Cloudflare" in n]
    assert len(cache) == 1 and "assets/site.css" in cache[0] and "assets/app.js" in cache[0] and "img/hero.jpg" in cache[0], notes
    assert "site.abc123.css" not in cache[0] and "index.html" not in cache[0]
    assert out == acts, "попередження нічого не змінює"


def test_mock_client_runs_the_gate_only_for_php_and_returns_the_notes(tmp_path=None):
    import tempfile
    from pathlib import Path
    root = Path(tempfile.mkdtemp(prefix="cg-"))
    (root / "b1").mkdir()
    php = MockClient(root=root, gate=True)
    r = php.commit("b1", "m", [_act("index.php", "<p>{{BRAND}} {{DOMAIN}}</p>", action="create"), _act("site.css", "a{}", action="create")])
    assert (root / "b1" / "index.php").read_text(encoding="utf-8") == "<p>{{DOMAIN}}</p>"
    assert r["lab_notes"] and any("{{BRAND}}" in n for n in r["lab_notes"]), r
    r2 = php.commit("b1", "m", [_act("site.css", "b{}")])
    assert any("Cloudflare" in n for n in r2["lab_notes"]), r2
    node = MockClient(root=root, gate=False)
    r3 = node.commit("b1", "m", [_act("x.html", "<p>{{BRAND}}</p>", action="create")])
    assert (root / "b1" / "x.html").read_text(encoding="utf-8") == "<p>{{BRAND}}</p>" and r3.get("lab_notes") == []


if __name__ == "__main__":
    run(dict(globals()))
