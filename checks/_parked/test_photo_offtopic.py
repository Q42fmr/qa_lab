"""Фото не по темі (checks/_parked/photo_offtopic): модель і стоковий пошук — підмінені.

Припарковано разом із чеком: CI цей файл не ганяє (лише tests/test_*.py),
руками — `python checks/_parked/test_photo_offtopic.py`."""
import importlib.util
import io
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "tests"))
from _harness import ROOT, run                                # noqa: E402

sys.path.insert(0, str(ROOT))
import ai_router                                              # noqa: E402
import photos                                                 # noqa: E402
import projects                                               # noqa: E402
import runner                                                 # noqa: E402

_spec = importlib.util.spec_from_file_location("checks.photo_offtopic", HERE / "photo_offtopic.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _jpeg(color, size=(640, 400)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG", quality=90)
    data = buf.getvalue()
    return data + b"\0" * max(0, mod.MIN_BYTES + 1 - len(data))   # понад поріг дрібних іконок


HOME = ('<html><head><title>Caça Vazamentos RJ</title><meta name="description" content="Detecção de vazamentos sem quebrar."></head>'
        '<body><h1>Caça vazamento no Rio</h1><img src="img/hero.jpg" alt="praia"><img src="img/logo.png" alt="logo">'
        '<img src="img/tech.jpg" alt="técnico" srcset="img/tech.jpg 1x"></body></html>')


def _setup(verdict_for):
    d = Path(tempfile.mkdtemp(prefix="po-"))
    projects.state_dir = lambda: d
    snap = d / "snap"
    for rel, color in (("img/hero.jpg", (10, 120, 200)), ("img/tech.jpg", (90, 90, 90)), ("img/logo.png", (0, 0, 0))):
        (snap / rel).parent.mkdir(parents=True, exist_ok=True)
        (snap / rel).write_bytes(_jpeg(color))
    runner.snapshot_dir = lambda b: snap
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    calls = {"n": 0}

    def fake_post(body, tool_name, timeout=60):
        calls["n"] += 1
        names = [c["text"] for c in body["messages"][0]["content"] if c["type"] == "text" and c["text"].startswith("Image ")]
        items = []
        for i, line in enumerate(names):
            rel = line.split(": ", 1)[1].split(" alt=")[0]
            items.append({"i": i, "on_topic": verdict_for(rel), "shows": "beach" if "hero" in rel else "plumber"})
        return {"error": ""}, {"items": items}
    ai_router._post = fake_post
    photos.search = lambda q, orientation="", page=1: {"results": [{"url": "https://img.magnific.com/free-photo/plumber_1.jpg?w=740"}, {"url": "https://img.magnific.com/free-photo/plumber_2.jpg?w=740"}]}
    return calls


def test_offtopic_image_is_flagged_once_and_cached_then_replaced_by_stock():
    calls = _setup(lambda rel: "hero" not in rel)
    files = {"index.php": HOME}
    paths = ["index.php", "img/hero.jpg", "img/tech.jpg", "img/logo.png"]
    issues = mod.run_branch(dict(files), paths, "casenadefekgubn-cop-br-pt")
    assert len(issues) == 1 and "img/hero.jpg" in issues[0]["message"] and "beach" in issues[0]["message"], issues
    assert issues[0]["severity"] == "warn"
    assert calls["n"] == 1
    assert mod.run_branch(dict(files), paths, "casenadefekgubn-cop-br-pt") and calls["n"] == 1, "повторний прогін — з кешу"
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), paths, "casenadefekgubn-cop-br-pt")}
    assert set(acts) == {"index.php"}
    new = acts["index.php"]
    assert 'src="https://img.magnific.com/free-photo/plumber_1.jpg?w=740"' in new and 'src="img/hero.jpg"' not in new
    assert 'src="img/tech.jpg"' in new and 'srcset="img/tech.jpg 1x"' in new, "on-topic картинка не чіпається"
    assert 'src="img/logo.png"' in new


def test_logo_small_and_external_images_are_never_sent():
    calls = _setup(lambda rel: True)
    files = {"index.php": HOME.replace('src="img/hero.jpg"', 'src="https://cdn.x/y.jpg"')}
    paths = ["index.php", "img/tech.jpg", "img/logo.png"]
    assert mod.run_branch(dict(files), paths, "x-br-pt") == []
    sent = []
    orig = ai_router._post

    def spy(body, tool_name, timeout=60):
        sent.extend(c["text"] for c in body["messages"][0]["content"] if c["type"] == "text" and c["text"].startswith("Image "))
        return orig(body, tool_name, timeout)
    ai_router._post = spy
    projects.state_dir = lambda d=Path(tempfile.mkdtemp(prefix="po2-")): d   # свіжий кеш
    mod.run_branch(dict(files), paths, "x-br-pt")
    assert sent and all("logo" not in s and "cdn.x" not in s for s in sent), sent


def test_without_api_key_the_check_is_silent():
    _setup(lambda rel: False)
    os.environ["ANTHROPIC_API_KEY"] = ""
    assert mod.run_branch({"index.php": HOME}, ["index.php", "img/hero.jpg"], "x-br-pt") == []
    assert mod.fix_branch({"index.php": HOME}, ["index.php", "img/hero.jpg"], "x-br-pt") == []


if __name__ == "__main__":
    run(dict(globals()))
