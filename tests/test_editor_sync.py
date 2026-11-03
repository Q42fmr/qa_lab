"""Редактор файлів: прозорий textarea поверх підсвіченого pre.

Каретка і підсвітка — ДВА шари, які зобов'язані збігатись піксель у
піксель. 01.10 після пошуку підсвітка з'їжджала відносно карета («курсор
трошки вище рядка»): у textarea є скролбари, у pre (overflow:hidden) —
немає, тож maxScroll pre МЕНШИЙ на їхню товщину, і біля дна файла
hl.scrollTop=ta.scrollTop клампився. Другий механізм того ж симптому —
CRLF: textarea мовчки нормалізує \r\n у \n, і рядкова математика по
сирому тексту з'їжджала б на символ за кожен рядок.

Тести тримають обидва контракти як правило, а не разову правку.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def _css_rule(selector: str) -> str:
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", INDEX)
    assert m, f"css-правило {selector} зникло"
    return m.group(1)


def test_editor_layers_share_font_and_padding():
    """Базовий інваріант вирівнювання: обидва шари в ОДНОМУ правилі — їх
    неможливо розсинхронізувати, поправивши тільки один."""
    for sel in ("#editHl,#fEdit", "#tHl,#tTa"):
        rule = _css_rule(sel)
        assert "padding:10px 14px" in rule, (sel, rule)
        assert "white-space:pre" in rule, (sel, rule)
        mono = re.search(r"font:12px/(\d+)px", rule)
        assert mono, f"{sel}: line-height має бути ЦІЛИМ у пікселях " \
                     f"(субпіксельний 1.55em накопичував зсув на зумі): {rule}"


def test_scrollbar_compensation_is_wired():
    """Кламп скролу: pre мусить отримувати padding на товщину скролбарів
    textarea — в ОБОХ редакторах (файли і трансформи)."""
    assert INDEX.count("ta.offsetHeight-ta.clientHeight") >= 2, \
        "компенсація скролбарів зникла з enterEdit або tUpd"
    assert INDEX.count("ta.offsetWidth-ta.clientWidth") >= 2


def test_scroll_sync_handlers_exist():
    assert re.search(r"hl\.scrollTop=ta\.scrollTop;hl\.scrollLeft=ta\.scrollLeft",
                     INDEX), "scroll-синхронізація редактора файлів зникла"
    assert "$('#tHl').scrollTop=$('#tTa').scrollTop" in INDEX


def test_crlf_normalized_on_open_and_restored_on_save():
    """rawText живе БЕЗ \r (як .value textarea), а коміт повертає рідні
    закінчення — інакше CRLF-файл приїхав би «переліненим» у LF."""
    assert re.search(r"fileEol=t0\.includes\('\\r\\n'\)", INDEX), \
        "визначення стилю EOL при відкритті зникло"
    assert re.search(r"rawText=t0\.replace\(/\\r\\n\?/g,'\\n'\)", INDEX), \
        "нормалізація \\r\\n при відкритті зникла"
    assert re.search(
        r"fileEol==='\\r\\n'\?\$\('#fEdit'\)\.value\.replace\(/\\n/g,'\\r\\n'\)",
        INDEX), "відновлення рідного EOL при коміті зникло"


def test_selection_math_uses_normalized_text():
    """enterEdit рахує позицію курсора по rawText — тест ловить повернення
    сирого тексту з \r у цю математику."""
    m = re.search(r"function enterEdit\(.*?\n\}", INDEX, re.S)
    assert m, "enterEdit зник"
    body = m.group(0)
    assert "ta.value=rawText" in body
    assert "rawText.split('\\n')" in body


if __name__ == "__main__":
    run(dict(globals()))
