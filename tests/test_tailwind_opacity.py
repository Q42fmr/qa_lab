"""Тести tailwind_opacity: невалідні opacity-класи і суцільні оверлеї
поверх <img>. Кейс-джерело — tajbojo-br-pt (bg-opacity-62 у хедерах)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, load_check, run                  # noqa: E402

mod = load_check("tailwind_opacity")

CDN = '<script src="https://cdn.tailwindcss.com"></script>\n'


def _page(body: str, head: str = "") -> str:
    return f"<html><head>{CDN}{head}</head><body>{body}</body></html>"

HERO = ('<section class="relative">\n'
        '<img src="x.jpg" alt="hero" class="hero-img w-full">\n'
        '<div class="absolute inset-0 bg-deep-hull {overlay} flex items-center">'
        '<h1>T</h1></div>\n'
        '</section>')


# ---------------------------------------------------------------- невалідні N

def test_invalid_bg_opacity_flagged_and_fixed():
    src = _page(HERO.format(overlay="bg-opacity-62"))
    issues = mod.run("index.php", src)
    assert len(issues) == 1
    assert issues[0]["severity"] == "error"
    assert "bg-opacity-62" in issues[0]["message"]
    out = mod.fix("index.php", src)
    assert "bg-opacity-60" in out and "bg-opacity-62" not in out
    assert mod.run("index.php", out) == []


def test_nearest_multiple_of_5():
    src = _page('<div class="opacity-8 opacity-63 bg-opacity-72 bg-opacity-92">')
    out = mod.fix("a.html", src)
    assert "opacity-10" in out and "opacity-65" in out
    assert "bg-opacity-70" in out and "bg-opacity-90" in out


def test_over_100_clamped():
    src = _page('<div class="opacity-105">')
    assert len(mod.run("a.html", src)) == 1
    assert 'class="opacity-100"' in mod.fix("a.html", src)


def test_valid_scale_untouched():
    # v3.4: усі кратні 5 валідні, зокрема 15/35/55/65/85
    src = _page('<div class="opacity-0 opacity-15 bg-opacity-85 border-opacity-55 opacity-100">')
    assert mod.run("a.html", src) == []
    assert mod.fix("a.html", src) == src


def test_arbitrary_and_slash_syntax_untouched():
    src = _page('<div class="bg-opacity-[0.62] opacity-[.37] bg-deep-hull/62">')
    assert mod.run("a.html", src) == []
    assert mod.fix("a.html", src) == src


def test_variant_prefix_preserved():
    src = _page('<div class="hover:bg-opacity-62 md:opacity-8">')
    out = mod.fix("a.html", src)
    assert "hover:bg-opacity-60" in out and "md:opacity-10" in out


def test_non_bg_utilities_are_warn():
    src = _page('<div class="border-opacity-62 ring-opacity-8">')
    issues = mod.run("a.html", src)
    assert [i["severity"] for i in issues] == ["warn", "warn"]
    out = mod.fix("a.html", src)
    assert "border-opacity-60" in out and "ring-opacity-10" in out


def test_no_tailwind_cdn_no_issues():
    src = '<html><head></head><body><div class="bg-opacity-62"></div></body></html>'
    assert mod.run("a.html", src) == []
    assert mod.fix("a.html", src) == src


def test_page_defined_class_untouched():
    head = "<style>.opacity-62 { opacity: .62 }</style>"
    src = _page('<div class="opacity-62">', head=head)
    assert mod.run("a.html", src) == []
    assert mod.fix("a.html", src) == src


def test_outside_class_attr_untouched():
    src = _page("<p>напишіть bg-opacity-62 у класі</p>"
                "<script>var s = 'bg-opacity-62';</script>")
    assert mod.run("a.html", src) == []


# ------------------------------------------------------- оверлей без opacity

def test_overlay_without_alpha_flagged_and_fixed():
    src = _page(HERO.format(overlay="").replace("  ", " "))
    issues = mod.run("index.php", src)
    assert len(issues) == 1 and issues[0]["severity"] == "error"
    assert "оверлей" in issues[0]["message"]
    out = mod.fix("index.php", src)
    assert "bg-opacity-60" in out
    assert mod.run("index.php", out) == []


def test_overlay_with_inline_style_opacity_ok():
    # реальний патерн golwbeujr-my-en: прозорість через style=
    src = _page('<img src="x.jpg" class="w-full">\n'
                '<div class="absolute inset-0 bg-ink" style="opacity:0.58;"></div>')
    assert mod.run("index.php", src) == []


def test_overlay_with_slash_alpha_ok():
    src = _page('<img src="x.jpg">\n<div class="absolute inset-0 bg-black/50"></div>')
    assert mod.run("a.html", src) == []


def test_overlay_with_custom_css_class_ok():
    head = "<style>.hero-veil { background: rgba(17,31,37,.6) }</style>"
    src = _page('<img src="x.jpg">\n'
                '<div class="absolute inset-0 hero-veil"></div>', head=head)
    assert mod.run("a.html", src) == []


def test_overlay_without_img_ignored():
    src = _page('<div class="absolute inset-0 bg-deep-hull"></div>')
    assert mod.run("a.html", src) == []


def test_gradient_overlay_ignored():
    src = _page('<img src="x.jpg">\n'
                '<div class="absolute inset-0 bg-gradient-to-b from-black"></div>')
    assert mod.run("a.html", src) == []


# ------------------------------------------- фонове фото, приглушене в нуль

# Форма з romevafu-br-pt: картинка лежить фоновим шаром і сама себе гасить,
# а зверху ще й щільний скрим-градієнт.
PHOTO_HERO = (
    '<section class="w-full relative" style="min-height:480px;">\n'
    '<img src="x.jpg" alt="hero" class="w-full object-cover absolute inset-0 h-full"'
    ' style="z-index:0; opacity:{img};">\n'
    '<div class="relative z-10 w-full" style="background: {scrim};"><h1>T</h1></div>\n'
    '</section>')
DENSE = "linear-gradient(90deg, rgba(26,47,75,0.97) 55%, rgba(26,47,75,0.82) 100%)"


def _photo_issues(src):
    return [i for i in mod.run("index.php", src) if "фонове фото" in i["message"]]


def test_hidden_bg_photo_flagged_and_fixed():
    src = _page(PHOTO_HERO.format(img="0.22", scrim=DENSE))
    issues = _photo_issues(src)
    assert len(issues) == 1 and issues[0]["severity"] == "error"
    assert "4.0%" in issues[0]["message"]        # 0.22 × (1 − 0.82)
    out = mod.fix("index.php", src)
    assert 'style="z-index:0;"' in out           # гасіння зняте, z-index лишився
    assert "opacity:0.22" not in out
    assert DENSE in out                          # скрим недоторканий
    assert mod.run("index.php", out) == []


def test_scrim_with_transparent_stop_is_not_hiding():
    """Градієнт, що сходить у transparent, лишає фото видимим збоку —
    саме на цьому патерні статичний глушник помилково бачив «невидиме
    фото» (tehmezim-br-pt, bamiki-br-pt: на рендері фото добре видно).
    Альфа береться по НАЙПРОЗОРІШОМУ стопу, тому 0.8→transparent нічого
    не ховає; без цього вийшло б 0.2 × (1 − 0.8) = 4% і фолс."""
    src = _page(PHOTO_HERO.format(
        img="0.2",
        scrim="linear-gradient(100deg,rgba(27,58,82,0.8) 55%,transparent 100%)"))
    assert _photo_issues(src) == []
    assert mod.fix("index.php", src) == src


def test_faded_photo_without_scrim_untouched():
    """opacity 0.15–0.30 на hero-фото без скрима — навмисний прийом,
    а не поломка: у кеші так зроблено в сотнях віток."""
    src = _page('<section class="relative">\n'
                '<img src="x.jpg" class="absolute inset-0 w-full" style="opacity:0.2;">\n'
                '<div class="relative z-10"><h1>T</h1></div>\n</section>')
    assert _photo_issues(src) == []


def test_opacity_class_on_photo_fixed():
    src = _page('<img src="x.jpg" class="absolute inset-0 opacity-20 w-full">\n'
                '<div class="absolute inset-0" style="background:rgba(0,0,0,0.8);"></div>')
    assert len(_photo_issues(src)) == 1
    out = mod.fix("index.php", src)
    assert 'class="absolute inset-0 w-full"' in out
    assert _photo_issues(out) == []


def test_variant_opacity_is_not_base_dimming():
    """md:opacity-20 гасить лише на одному брейкпоінті — не наш кейс."""
    src = _page('<img src="x.jpg" class="absolute inset-0 md:opacity-20 w-full">\n'
                '<div class="absolute inset-0" style="background:rgba(0,0,0,0.8);"></div>')
    assert _photo_issues(src) == []


def test_style_attr_removed_when_opacity_was_alone():
    src = _page('<img src="x.jpg" class="absolute inset-0" style="opacity:0.2">\n'
                '<div class="absolute inset-0" style="background:rgba(0,0,0,0.8);"></div>')
    assert len(_photo_issues(src)) == 1
    out = mod.fix("index.php", src)
    assert 'style=""' not in out and "opacity:0.2" not in out
    assert '<img src="x.jpg" class="absolute inset-0">' in out


def test_opaque_scrim_not_reported():
    """Скрим сам глухий -> зняття гасіння з фото нічого не дасть.
    Чужий скрим не чіпаємо (це зіпсує контраст тексту), тож і не репортимо."""
    src = _page(PHOTO_HERO.format(img="0.2", scrim="rgba(20,20,20,0.97)"))
    assert _photo_issues(src) == []


def test_photo_at_full_opacity_ignored():
    src = _page(PHOTO_HERO.format(img="1", scrim=DENSE))
    assert _photo_issues(src) == []


def test_next_section_is_not_a_scrim():
    """Сусіда шукаємо лише в тому ж контейнері: закривний тег зупиняє скан.
    Без цього правила фон НАСТУПНОЇ секції читався як скрим — на цьому
    перша, надто широка версія правила дала 280 фолсів на 403 знахідки.
    Альфа наступної секції тут 0.8, тобто саме та, що дала б 4% і репорт."""
    src = _page('<section class="relative">\n'
                '<img src="x.jpg" class="absolute inset-0" style="opacity:0.2;">\n'
                '</section>\n'
                '<section class="bg-navy bg-opacity-80 py-20"><h2>далі</h2></section>')
    assert _photo_issues(src) == []


def test_tailwind_bg_opacity_scrim_counted():
    src = _page('<img src="x.jpg" class="absolute inset-0" style="opacity:0.2;">\n'
                '<div class="absolute inset-0 bg-navy bg-opacity-90"></div>')
    issues = _photo_issues(src)
    assert len(issues) == 1 and "2.0%" in issues[0]["message"]


def test_photo_line_number_points_at_img():
    src = _page(PHOTO_HERO.format(img="0.22", scrim=DENSE))
    line = src.count("\n", 0, src.index("<img")) + 1
    assert _photo_issues(src)[0]["line"] == line


def test_real_romevafu_snapshot():
    """Живий знімок romevafu-br-pt: якщо гасіння ще у файлі — ловимо і
    знімаємо; якщо вже пофікшено — сторінка чиста."""
    base = ROOT / "cache" / "romevafu-br-pt"
    if not base.exists():
        return
    for name in ("index.php", "company.html", "benefits.html",
                 "solutions.html", "testimonials.html"):
        p = base / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        issues = _photo_issues(text)
        if issues:
            fixed = mod.fix(name, text)
            assert fixed != text, name
            assert _photo_issues(fixed) == [], name
            assert "rgba(26,47,75,0.97)" in fixed, name   # скрим на місці
        else:
            assert mod.fix(name, text) == text, name


# --------------------------------------------------------------------- інше

def test_fix_idempotent():
    src = _page(HERO.format(overlay="bg-opacity-62") +
                '<div class="border-opacity-8">')
    once = mod.fix("index.php", src)
    assert mod.fix("index.php", once) == once


def test_line_numbers():
    src = _page(HERO.format(overlay="bg-opacity-62"))
    line = src.count("\n", 0, src.index("bg-opacity-62")) + 1
    assert mod.run("index.php", src)[0]["line"] == line


def test_real_tajbojo_snapshot():
    """На живому знімку tajbojo-br-pt: якщо bg-opacity-62 ще у файлі —
    ловимо і фіксимо на 60; якщо вже пофікшено — сторінка має бути чистою."""
    base = ROOT / "cache" / "tajbojo-br-pt"
    if not base.exists():                    # знімок є не в кожному середовищі
        return
    for name in ("benefits.html", "solutions.html", "testimonials.html", "index.php"):
        p = base / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if "bg-opacity-62" in text:
            issues = mod.run(name, text)
            assert any("bg-opacity-62" in i["message"] for i in issues), name
            fixed = mod.fix(name, text)
            assert "bg-opacity-62" not in fixed and "bg-opacity-60" in fixed, name
            assert mod.run(name, fixed) == [], name
        else:                                # знімок уже пофікшений автофіксом
            assert mod.run(name, text) == [], name
            assert mod.fix(name, text) == text, name


if __name__ == "__main__":
    run(dict(globals()))
