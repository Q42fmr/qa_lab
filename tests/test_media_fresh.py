"""Гейт свіжості знімка для медіа-комітів (/api/media/*).

Кейс bavmejxqul-gepima-semgikja.ch-ch-fr: людина перейменувала jpg-файли
прямим комітом у GitLab, знімок лаби лишився старий, і «Завантажити з URL і
закомітити» слав update по шляхах, яких у HEAD вже немає — GitLab відкидав
коміт, людині діставався глухий «commit failed» і ті самі фото після
пересканування (скан знімок не оновлює). Тепер розбіжність ловиться ДО
роботи і каже, що робити: Sync.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                               # noqa: E402

sys.path.insert(0, str(ROOT))
os.environ.setdefault("MOCK_MODE", "1")

import app                                                   # noqa: E402
import runner as rn                                          # noqa: E402
from fastapi import HTTPException                            # noqa: E402


class _Client:
    def __init__(self, head):
        self.head = head

    def branch(self, _name):
        if isinstance(self.head, Exception):
            raise self.head
        return {"commit": self.head}


def _with(local, head):
    old = (rn.snapshot_meta, app.client)
    rn.snapshot_meta = lambda _b: ({"commit": local} if local else {})
    app.client = _Client(head)
    return old


def _restore(old):
    rn.snapshot_meta, app.client = old


def _gate(local, head):
    old = _with(local, head)
    try:
        app._require_fresh_snapshot("b")
        return None
    except HTTPException as e:
        return e
    finally:
        _restore(old)


def test_stale_snapshot_is_refused_with_sync_hint():
    e = _gate("aaaa1111", "bbbb2222")
    assert e is not None and e.status_code == 409, e
    assert "Sync" in e.detail and "поїхала вперед" in e.detail, e.detail
    assert "bbbb2222"[:8] in e.detail and "aaaa1111"[:8] in e.detail, e.detail


def test_fresh_snapshot_passes():
    assert _gate("aaaa1111", "aaaa1111") is None


def test_legacy_snapshot_without_sha_is_not_blocked():
    assert _gate(None, "bbbb2222") is None


def test_unreachable_gitlab_does_not_block():
    """Гейт — підказка, а не нова точка відмови: помилку коміту скаже коміт."""
    assert _gate("aaaa1111", RuntimeError("нема мережі")) is None


def test_replace_from_url_refuses_before_touching_anything():
    old = _with("aaaa1111", "bbbb2222")
    try:
        app.media_replace_from_url(app.ReplaceFromUrlRequest(
            branch="b", items=[{"path": "a.jpg", "url": "https://x/y.jpg"}],
            message="Image"))
        raise AssertionError("мав відмовити 409")
    except HTTPException as e:
        assert e.status_code == 409, e
    finally:
        _restore(old)


def test_all_five_media_mutations_are_gated():
    src = open(os.path.join(str(ROOT), "app.py"), encoding="utf-8").read()
    for fn in ["def media_upload(", "def media_upload_many(",
               "def media_replace_from_url(", "def media_replace_by_usage(",
               "def media_split_file("]:
        body = src[src.index(fn):]
        body = body[:body.index("\n@app.")]
        assert "_require_fresh_snapshot(req.branch)" in body, fn


if __name__ == "__main__":
    run(dict(globals()))
