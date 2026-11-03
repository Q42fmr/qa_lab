"""brand_mark: знак лого/favicon — різноманіття замість одного шаблону.

Контракти: детермінізм за віткою (ідемпотентність фіксів), автофіксний знак
несе літеру, варіанти для UI не повторюються, кольори виводяться з
theme-color, тематична іконка вгадується з текстів вайта.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run                                     # noqa: E402

import brand_mark                                            # noqa: E402

FILES = {"index.html": ("<html><head><title>Provub Cospubtenp — consultoria"
                        "</title><meta name=\"description\" content=\"advocacia "
                        "e direito empresarial\"></head></html>")}


def test_pick_is_deterministic_and_letterful():
    a = brand_mark.pick(FILES, "nwf-provub-cospubtenp-br-pt", base_color="#1e40af")
    b = brand_mark.pick(FILES, "nwf-provub-cospubtenp-br-pt", base_color="#1e40af")
    assert a == b
    ET.fromstring(a)
    assert a.startswith("<svg xmlns=")           # контракт favicon-фікса
    assert "<text" in a and re.search(r">P(?:C)?<", a), a


def test_different_branches_get_different_marks():
    marks = {brand_mark.pick(FILES, br, base_color="#1e40af")
             for br in ("nwf-a-br-pt", "nwf-b-br-pt", "nwf-c-br-pt",
                        "nwf-d-br-pt", "nwf-e-br-pt", "nwf-f-br-pt")}
    assert len(marks) >= 4, "шість віток мають давати різні знаки"


def test_variants_are_unique_and_valid():
    vs = brand_mark.variants(FILES, "nwf-provub-cospubtenp-br-pt",
                             count=12, base_color="#1e40af")
    assert len(vs) == 12
    combos = {(v["shape"], v["layout"], v["palette_i"]) for v in vs}
    assert len(combos) == 12, "комбінації не повторюються"
    shapes = {v["shape"] for v in vs}
    assert len(shapes) >= 3, "форми мають варіюватися"
    for v in vs:
        ET.fromstring(v["svg"])


def test_theme_icon_from_site_texts():
    assert brand_mark.theme_icon(FILES) == "scales"          # advocacia/direito
    hotel = {"index.html": "<title>Remalo Luhiime — villas de luxo, "
                           "experiências de viagem</title>"}
    assert brand_mark.theme_icon(hotel) == "key"
    assert brand_mark.theme_icon({"index.html": "<title>Olá</title>"}) == "star"


def test_initials_are_strict_latin():
    assert brand_mark.initials("Câmera Alves") == "CA"
    assert brand_mark.initials("Águia Ótica") == "AO"
    assert brand_mark.initials("Años Dorados") == "AD"


def test_bad_base_color_falls_back():
    svg = brand_mark.build("S", base='red" onload="alert(1)')
    assert 'onload' not in svg
    assert brand_mark.DEFAULT_BG in svg or "url(#g)" in svg


def test_icon_db_is_loaded_and_large():
    db = brand_mark.icon_db()
    assert len(db) >= 200, len(db)
    assert all("name" in r and "body" in r for r in db[:20])


def test_seeded_pool_extension_is_reproducible():
    v1 = brand_mark.variants(FILES, "nwf-a-br-pt", count=24, seed=7)
    v2 = brand_mark.variants(FILES, "nwf-a-br-pt", count=24, seed=7)
    v3 = brand_mark.variants(FILES, "nwf-a-br-pt", count=24, seed=8)
    assert [x["svg"] for x in v1] == [x["svg"] for x in v2]
    # стабільне ядро (12) не залежить від seed, розширення — залежить
    assert [x["svg"] for x in v1[:12]] == [x["svg"] for x in v3[:12]]
    assert [x["svg"] for x in v1[12:]] != [x["svg"] for x in v3[12:]]
    assert all(v.get("pool") for v in v1[12:]), "розширення — з пулу"
    import xml.etree.ElementTree as ET
    for v in v1:
        ET.fromstring(v["svg"])


def test_icon_layout_is_never_autofixed():
    for br in [f"nwf-x{i}-br-pt" for i in range(30)]:
        svg = brand_mark.pick(FILES, br)
        assert "<text" in svg, f"{br}: автофіксний знак без літери"


# -------------------------------------------- nested і шрифти (01.10)
def test_nested_mark_has_three_levels():
    svg = brand_mark.build("A", shape="squircle", layout="nested",
                           palette=3, base="#1e40af")
    ET.fromstring(svg)
    assert 'rx="14"' in svg                           # зовнішня форма
    assert "<g transform=" in svg and "scale(0.58)" in svg  # вписаний об'єкт
    assert "<text" in svg and ">A<" in svg            # літера всередині
    # літера на градієнті — кольором темного стопа, не кольором об'єкта
    assert not brand_mark.is_template_mark(svg)


def test_nested_inner_never_equals_outer():
    svg = brand_mark.build("A", shape="circle", layout="nested",
                           inner="circle", base="#1e40af")
    # inner == shape — підміняється відмінною формою: два кола зіллялись би
    assert svg.count("<circle") <= 1, svg


def test_fonts_axis_changes_mark():
    a = brand_mark.build("A", font=0, base="#1e40af")
    b = brand_mark.build("A", font=1, base="#1e40af")
    c = brand_mark.build("A", font=5, base="#1e40af")
    assert a != b != c
    assert "system-ui" in a and "Georgia" in b and "Impact" in c


def test_variants_spread_fonts_and_nested():
    vs = brand_mark.variants(FILES, "nwf-fontmix-br-pt", count=60, seed=3)
    fonts = {v["font"] for v in vs}
    assert len(fonts) >= 3, f"шрифтова вісь не крутиться: {fonts}"
    nested = [v for v in vs if v["layout"] == "nested"]
    assert nested, "nested немає у розгортці"
    for v in nested:
        assert v["inner"] != v["shape"]
        ET.fromstring(v["svg"])

if __name__ == "__main__":
    run(dict(globals()))
