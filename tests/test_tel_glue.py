"""tel_glue: два номери злиплись в одному tel: (13.10, it-it партія).

vodupiu-it-it і ще 12 віток: генератор вклеїв обидва телефони контакт-блока
в один href — `tel:+390950979340+390959596174`. Видимий текст при цьому
нормальний («+39 095 097 9340 / +39 095 959 6174»), але дзвінок по лінку
битий. Фікс розділяє лінк на два по роздільнику тексту; якщо текст тримає
лише один номер — href звужується до нього.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run

mod = load_check("tel_glue")

SEP = ('<p>Telefono: <a href="tel:+390950979340+390959596174" '
       'class="underline hover:text-sienna">+39 095 097 9340 / '
       '+39 095 959 6174</a><br>Sede: Roma</p>')

ONE = ('<a href="tel:+393343508623+390171291587" class="btn">'
       '+39 334 350 8623</a>')

HEALTHY = ('<div class="flex gap-1">'
           '<a href="tel:+393425040881">+39 342 504 0881</a> '
           '<a href="tel:+393470080564">+39 347 008 0564</a></div>')


def test_glued_href_is_flagged():
    issues = mod.run("index.php", f"<html><body>{SEP}</body></html>")
    assert len(issues) == 1, issues
    assert issues[0]["severity"] == "error"
    assert "tel:" in issues[0]["message"]


def test_fix_splits_into_two_links_by_text_separator():
    src = f"<html><body>{SEP}</body></html>"
    out = mod.fix("index.php", src)
    assert 'href="tel:+390950979340"' in out
    assert 'href="tel:+390959596174"' in out
    assert "tel:+390950979340+390959596174" not in out
    # текст номерів і роздільник збережені, клас лінка теж
    assert ">+39 095 097 9340</a>" in out
    assert ">+39 095 959 6174</a>" in out
    assert " / " in out
    assert out.count('class="underline hover:text-sienna"') == 2
    # ідемпотентність і тиша після
    assert mod.fix("index.php", out) == out
    assert mod.run("index.php", out) == []


def test_single_visible_number_narrows_href_to_it():
    out = mod.fix("index.php", f"<html><body>{ONE}</body></html>")
    assert 'href="tel:+393343508623"' in out
    assert "+390171291587" not in out
    assert ">+39 334 350 8623</a>" in out


def test_healthy_adjacent_links_untouched():
    src = f"<html><body>{HEALTHY}</body></html>"
    assert mod.run("index.php", src) == []
    assert mod.fix("index.php", src) == src


def test_spaces_and_dashes_in_tel_are_not_glue():
    src = '<a href="tel:+39 095 097-93-40">+39 095 097 9340</a>'
    assert mod.run("index.php", f"<html><body>{src}</body></html>") == []


def test_three_glued_numbers_split_cleanly():
    src = ('<a href="tel:+390111111+390222222+390333333" class="x">'
           "+39 011 1111 / +39 022 2222 / +39 033 3333</a>")
    out = mod.fix("index.php", f"<html><body>{src}</body></html>")
    assert 'href="tel:+390111111"' in out
    assert 'href="tel:+390222222"' in out
    assert 'href="tel:+390333333"' in out


def test_plusless_glue_is_split_by_visible_numbers():
    """aebneunir-br-pt 20.10: tel:112796370411985783154 — два місцеві номери
    без плюса між ними; межу дає лише видимий текст «N1 / N2». Довгий href,
    чиї цифри — конкатенація показаних номерів, ріжеться на два лінки."""
    src = ('<a href="tel:112796370411985783154" class="hover:text-gold">'
           "(11) 2796-3704 / (11) 98578-3154</a>")
    page = f"<html><body>{src}</body></html>"
    issues = mod.run("index.php", page)
    assert len(issues) == 1 and "2 номери" in issues[0]["message"], issues
    out = mod.fix("index.php", page)
    assert ('<a href="tel:1127963704" class="hover:text-gold">(11) 2796-3704</a> / '
            '<a href="tel:11985783154" class="hover:text-gold">(11) 98578-3154</a>') in out, out
    assert mod.fix("index.php", out) == out and mod.run("index.php", out) == []



def test_raw_text_href_with_separator_is_split_into_two_links():
    """prancheta/inpiloew-em-paudu/nordeste/noacu-de-jole br-pt (754, 27.10):
    href="tel:+55 21 2155-4551 / +55 21 2155-4552" — генератор вклеїв у tel:
    видимий текст як є, з пробілами, дефісами і « / ». Дзвінок набирає сміття.
    Фікс: два <a> з тими самими атрибутами, кожен зі своїм tel:+55…"""
    src = ('<a href="tel:+55 21 2155-4551 / +55 21 2155-4552" class="foot-tel">'
           "+55 21 2155-4551 / +55 21 2155-4552</a>")
    page = f"<html><body>{src}</body></html>"
    issues = mod.run("index.php", page)
    assert len(issues) == 1 and "2" in issues[0]["message"], issues
    out = mod.fix("index.php", page)
    assert '<a href="tel:+552121554551" class="foot-tel">+55 21 2155-4551</a> / ' in out, out
    assert '<a href="tel:+552121554552" class="foot-tel">+55 21 2155-4552</a>' in out
    assert mod.run("index.php", out) == [] and mod.fix("index.php", out) == out
    # один номер з пробілами — не склейка (як і було)
    assert mod.run("index.php", '<a href="tel:+55 21 2155-4551">+55 21 2155-4551</a>') == []
    # іконка + <span>N1 / N2</span> (так у 754-вайтах): два лінки, іконка в першому
    src2 = ('<a href="tel:+55 21 2155-4551 / +55 21 2155-4552" class="ft"><svg class="lucide"><path d="M1"/></svg>'
            '<span>+55 21 2155-4551 / +55 21 2155-4552</span></a>')
    out2 = mod.fix("index.php", f"<html><body>{src2}</body></html>")
    assert '<a href="tel:+552121554551" class="ft"><svg class="lucide"><path d="M1"/></svg><span>+55 21 2155-4551</span></a> / ' in out2, out2
    assert '<a href="tel:+552121554552" class="ft"><span>+55 21 2155-4552</span></a>' in out2
    assert mod.run("index.php", out2) == []

def test_long_href_that_is_not_the_shown_numbers_is_left_alone():
    """Довгий tel: з одним показаним номером або з текстом, що не складає
    href, — не склейка (ID, трекінг-номер): не чіпаємо."""
    for src in ('<a href="tel:112796370411985783154">(11) 2796-3704</a>',
                '<a href="tel:112796370411985783154">Ligue agora</a>',
                '<a href="tel:112796370411985783154">(11) 2796-3704 / (11) 1111-1111</a>'):
        page = f"<html><body>{src}</body></html>"
        assert mod.run("index.php", page) == [], src
        assert mod.fix("index.php", page) == page, src


if __name__ == "__main__":
    run(dict(globals()))
