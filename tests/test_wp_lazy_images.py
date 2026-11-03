"""WP-Rocket lazyload: svg-заглушки замість картинок (checks/wp_lazy_images)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, load_check                          # noqa: E402

mod = load_check("wp_lazy_images")

PH = "data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%20417%20273'%3E%3C/svg%3E"
LAZY_IMG = (f'<img alt="" class="attachment-full wp-image-357" data-lazy-sizes="(max-width: 417px) 100vw, 417px" '
            f'data-lazy-src="wp-content/uploads/a.webp" data-lazy-srcset="wp-content/uploads/a.webp 417w, '
            f'wp-content/uploads/a-300.webp 300w" decoding="async" height="273" src="{PH}" width="417" />')
PAGE = ('<html><body>\n<div class="elementor-element elementor-invisible" data-settings=\'{"_animation":"fadeIn"}\'>'
        + LAZY_IMG + '</div>\n<script>document.querySelectorAll(".elementor-invisible[data-settings]")</script>'
        '</body></html>')


def test_placeholder_with_lazy_src_is_flagged_and_delazied():
    issues = mod.run("index.php", PAGE)
    assert len(issues) == 1 and issues[0]["severity"] == "error", issues
    assert "1 картинок-заглушок" in issues[0]["message"] and "1 блок(ів) elementor-invisible" in issues[0]["message"]
    out = mod.fix("index.php", PAGE)
    assert 'src="wp-content/uploads/a.webp"' in out, out
    assert 'srcset="wp-content/uploads/a.webp 417w, wp-content/uploads/a-300.webp 300w"' in out
    assert 'sizes="(max-width: 417px) 100vw, 417px"' in out
    assert "data-lazy" not in out.split("<script>")[0] and "data:image/svg" not in out
    # решта атрибутів і самозакриття на місці
    assert 'class="attachment-full wp-image-357"' in out and 'height="273"' in out and out.count(" />") == 1
    # клас знято з ЕЛЕМЕНТА, але не з коду скрипта
    assert '<div class="elementor-element" data-settings' in out, out
    assert 'querySelectorAll(".elementor-invisible[data-settings]")' in out
    assert mod.fix("index.php", out) == out and mod.run("index.php", out) == []


def test_real_src_next_to_lazy_attrs_is_left_alone():
    """Rocket уже підмінив src (lazyloaded) — чіпати нема чого."""
    done = LAZY_IMG.replace(f'src="{PH}"', 'src="wp-content/uploads/a.webp"')
    assert mod.run("index.php", done) == []
    assert mod.fix("index.php", done) == done


def test_iframe_without_src_takes_lazy_src():
    page = '<iframe data-lazy-src="https://www.youtube.com/embed/x" width="560" height="315"></iframe>'
    out = mod.fix("index.php", page)
    assert out == '<iframe width="560" height="315" src="https://www.youtube.com/embed/x"></iframe>', out


def test_single_quoted_attrs_are_handled():
    page = "<img src='data:image/svg+xml,%3Csvg%3E' data-lazy-src='img/x.jpg' alt='x'>"
    assert mod.fix("index.php", page) == "<img alt='x' src='img/x.jpg'>"


if __name__ == "__main__":
    run(dict(globals()))
