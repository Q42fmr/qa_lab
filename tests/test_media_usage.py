"""«Розбивка по місцях» (app._usage_edits): один old — різні new у різних
місцях одного файла (скарга 13.10: cagu-teobuga, здавалося що всі 3 місця
отримують один url; насправді юзер дивився ЗАГАЛЬНИЙ Preview — але контракт
розбивки має жити у тесті, щоб клас не регреснув).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                        # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MOCK_MODE", "1")
import app as _app                                              # noqa: E402

OLD = "https://img.b2bpic.net/premium-photo/stock.jpg"
PAGE = ("<html>\n"                                             # 1
        f'<img src="{OLD}" alt="Faxina">\n'                    # 2
        "<p>mid</p>\n"                                         # 3
        f'<img src="{OLD}" alt="Limpeza">\n'                   # 4
        f'<img src="{OLD}" alt="Equipe">\n'                    # 5
        "</html>")                                             # 6


def test_three_places_get_three_different_urls():
    targets = [
        {"path": "index.php", "line": 2, "old": OLD, "new": "https://x/A.jpg"},
        {"path": "index.php", "line": 4, "old": OLD, "new": "https://x/B.jpg"},
        {"path": "index.php", "line": 5, "old": OLD, "new": "https://x/C.jpg"},
    ]
    edited, applied, missed = _app._usage_edits({"index.php": PAGE}, targets)
    assert applied == 3 and missed == [], (applied, missed)
    lines = edited["index.php"].split("\n")
    assert "https://x/A.jpg" in lines[1]
    assert "https://x/B.jpg" in lines[3]
    assert "https://x/C.jpg" in lines[4]
    assert OLD not in edited["index.php"]


def test_shifted_line_falls_back_to_first_occurrence():
    targets = [{"path": "index.php", "line": 3, "old": OLD,
                "new": "https://x/D.jpg"}]          # на 3-му рядку лінка немає
    edited, applied, missed = _app._usage_edits({"index.php": PAGE}, targets)
    assert applied == 1 and missed == []
    assert edited["index.php"].count("https://x/D.jpg") == 1
    assert edited["index.php"].count(OLD) == 2, "інші місця не чіпаються"


def test_unknown_link_is_missed_not_applied():
    targets = [{"path": "index.php", "line": 2,
                "old": "https://nope/none.jpg", "new": "https://x/E.jpg"}]
    edited, applied, missed = _app._usage_edits({"index.php": PAGE}, targets)
    assert edited == {} and applied == 0
    assert missed == ["index.php:2"]


def test_same_new_in_two_places_both_applied():
    targets = [
        {"path": "index.php", "line": 2, "old": OLD, "new": "https://x/S.jpg"},
        {"path": "index.php", "line": 4, "old": OLD, "new": "https://x/S.jpg"},
    ]
    edited, applied, _ = _app._usage_edits({"index.php": PAGE}, targets)
    assert applied == 2
    assert edited["index.php"].count("https://x/S.jpg") == 2


if __name__ == "__main__":
    run(dict(globals()))
