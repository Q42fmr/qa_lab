"""Формат картинки-заміни: сніфер сигнатур + перегін під розширення цілі.

Кейс: у вітці лежить hero.webp, а зі стоку/диска приходить jpg. Раніше лаба
комітила jpg-байти під іменем .webp — файл брехав про свій формат. Тепер
media.ensure_format() переганяє байти у формат, який обіцяє розширення.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                              # noqa: E402

sys.path.insert(0, str(ROOT))
import media                                                # noqa: E402


def _img(fmt: str, mode: str = "RGB", size=(24, 18)) -> bytes:
    from PIL import Image
    im = Image.new(mode, size, (200, 120, 60, 128) if mode in ("RGBA", "LA") else (200, 120, 60))
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


def test_sniff_knows_every_supported_format():
    assert media.sniff_kind(_img("JPEG")) == "jpeg"
    assert media.sniff_kind(_img("PNG")) == "png"
    assert media.sniff_kind(_img("WEBP")) == "webp"
    assert media.sniff_kind(_img("GIF", "P")) == "gif"
    assert media.sniff_kind(_img("BMP")) == "bmp"
    assert media.sniff_kind(b'<?xml version="1.0"?><svg xmlns="x"></svg>') == "svg"
    assert media.sniff_kind(b'<svg viewBox="0 0 1 1"></svg>') == "svg"


def test_sniff_rejects_non_images():
    assert media.sniff_kind(b"") is None
    assert media.sniff_kind(b"<!DOCTYPE html><html>404</html>") is None
    # RIFF, але не WEBP: старий сніфер приймав будь-який RIFF (wav/avi) за картинку
    assert media.sniff_kind(b"RIFF\x24\x08\x00\x00WAVEfmt ") is None


def test_jpeg_into_webp_target_is_converted():
    data, note = media.ensure_format(_img("JPEG"), "COM_assets/COM_images/hero.webp")
    assert media.sniff_kind(data) == "webp"
    assert note == "jpeg → webp"


def test_matching_format_is_passed_through_untouched():
    src = _img("WEBP")
    data, note = media.ensure_format(src, "img/hero.webp")
    assert data is src and note is None          # без перекодування — байт-у-байт


def test_alpha_png_into_jpeg_target_is_flattened():
    data, note = media.ensure_format(_img("PNG", "RGBA"), "img/hero.jpg")
    assert media.sniff_kind(data) == "jpeg"
    assert note == "png → jpeg"


def test_raster_into_svg_target_is_refused():
    try:
        media.ensure_format(_img("JPEG"), "img/logo.svg")
    except ValueError as e:
        assert "svg" in str(e).lower()
    else:
        raise AssertionError("растр у .svg мусить впасти, а не зіпсувати файл")


def test_non_image_payload_is_refused():
    try:
        media.ensure_format(b"<!DOCTYPE html><html>404 not found</html>", "img/hero.webp")
    except ValueError as e:
        assert "картинк" in str(e).lower()
    else:
        raise AssertionError("не-картинка мусить впасти")


def test_unknown_extension_is_passed_through():
    src = _img("PNG")
    data, note = media.ensure_format(src, "assets/blob.bin")
    assert data is src and note is None


def test_query_string_in_path_does_not_break_extension():
    data, note = media.ensure_format(_img("JPEG"), "img/hero.webp?v=2")
    assert media.sniff_kind(data) == "webp"


# ------------------------------------ хеш-ім'я при заміні вмісту (02.10)
def test_hashed_path_is_stable_and_does_not_grow():
    a = media.hashed_path("images/ph-01.jpg", b"PHOTOBYTES")
    assert a.startswith("images/ph-01-") and a.endswith(".jpg")
    # детермінізм від вмісту
    assert media.hashed_path("images/ph-01.jpg", b"PHOTOBYTES") == a
    # повторна заміна: старий хеш-суфікс знімається, ім'я не росте
    b = media.hashed_path(a, b"OTHERBYTES")
    assert b.startswith("images/ph-01-") and b != a
    assert b.count("-") == a.count("-")
    # різний вміст — різна адреса (кеш/CDN пробивається)
    assert media.hashed_path("x.webp", b"one") != media.hashed_path("x.webp", b"two")


def test_retarget_refs_rewrites_all_link_shapes():
    # перейменування файла (02.10): ./-, /- і голі посилання + зняття ?v=
    texts = {
        "index.php": ('<img src="images/ph-01.jpg">\n'
                      '<img src="./images/ph-01.jpg?v=aa11bb22">\n'
                      "url('/images/ph-01.jpg')\n"
                      '<img src="images/ph-01.jpg.bak">'),   # інший файл
        "style.css": ".x{background:url(images/ph-01.jpg)}",
    }
    out = media.retarget_refs(texts, "images/ph-01.jpg", "images/hero-sea.jpg")
    idx = out["index.php"]
    assert 'src="images/hero-sea.jpg">' in idx
    assert 'src="./images/hero-sea.jpg">' in idx            # префікс і ?v
    assert "'/images/hero-sea.jpg'" in idx
    assert "ph-01.jpg.bak" in idx                           # сусід не зачеплено
    assert "ph-01.jpg" not in idx.replace("ph-01.jpg.bak", "")
    assert "url(images/hero-sea.jpg)" in out["style.css"]
    # повторний прогін — порожньо
    assert media.retarget_refs(dict(out), "images/ph-01.jpg",
                               "images/hero-sea.jpg") == {}


def test_retarget_refs_follows_file_relative_and_bare_names():
    """kamsviizivkakp-ch-de 21.10: заміна в Медіа перейменувала
    assets/img/p7.jpg → p7-<crc>.jpg, а коміт не зачепив жодного тексту:
    вкладені сторінки посилались `../assets/img/p7.jpg`, CSS — `../img/`,
    кошик у JS — голим ім'ям у мапі. Усі вони мусять переїхати на нове ім'я,
    а чужі файли з тим самим ім'ям і зовнішні URL — лишитись."""
    paths = ["index.html", "leistungen/index.html", "leistungen/a/b/index.html",
             "assets/css/site.css", "assets/js/site.js", "assets/img/p7.jpg",
             "promo/index.html", "promo/img/p7.jpg"]
    texts = {
        "index.html": '<img src="assets/img/p7.jpg">',
        "leistungen/index.html": '<img src="../assets/img/p7.jpg" alt="">',
        "leistungen/a/b/index.html": '<img src="../../../assets/img/p7.jpg">',
        "assets/css/site.css": ".x{background:url(../img/p7.jpg)}",
        "assets/js/site.js": 'var IMG={"a":"p7.jpg"};x.src="../assets/img/"+IMG.a;',
        # інший наявний файл з тим самим ім'ям — не наш
        "promo/index.html": ('<img src="img/p7.jpg">'
                             '<img src="https://cdn.x/assets/img/p7.jpg">'),
    }
    new = "assets/img/p7-80c4cef2.jpg"
    out = media.retarget_refs(texts, "assets/img/p7.jpg", new, paths)
    assert out["index.html"] == f'<img src="{new}">'
    assert '"../assets/img/p7-80c4cef2.jpg"' in out["leistungen/index.html"]
    assert '"../../../assets/img/p7-80c4cef2.jpg"' in out["leistungen/a/b/index.html"]
    assert "url(../img/p7-80c4cef2.jpg)" in out["assets/css/site.css"]
    # голе ім'я — лише коли воно у вітці одне: тут є ще promo/img/p7.jpg
    assert "assets/js/site.js" not in out
    assert "promo/index.html" not in out
    unique = [p for p in paths if p != "promo/img/p7.jpg"]
    texts_u = {p: t for p, t in texts.items() if p != "promo/index.html"}
    out_u = media.retarget_refs(texts_u, "assets/img/p7.jpg", new, unique)
    assert '"a":"p7-80c4cef2.jpg"' in out_u["assets/js/site.js"]
    # перенесення в іншу теку (кнопка «Перейменувати») — відносний шлях
    # перераховується від файла, а не лише ім'я
    moved = media.retarget_refs(texts_u, "assets/img/p7.jpg", "media/p7.jpg", unique)
    assert '"../media/p7.jpg"' in moved["leistungen/index.html"]
    assert "url(../../media/p7.jpg)" in moved["assets/css/site.css"]
    # «./» з кореня лишається «./» і після перенесення (sejhfecbf 23.10:
    # ./política-de-entrega/index.html → ./politica-de-entrega/index.html)
    root_dot = media.retarget_refs({"index.html": '<a href="./assets/img/p7.jpg">'},
                                   "assets/img/p7.jpg", "media/p7.jpg", unique)
    assert root_dot["index.html"] == '<a href="./media/p7.jpg">', root_dot
    # повторний прогін — порожньо
    assert media.retarget_refs({**texts_u, **out_u}, "assets/img/p7.jpg", new,
                               unique) == {}


if __name__ == "__main__":
    run(dict(globals()))
