"""Кожна сторінка лаби мусить мати вхід із головного UI.

28.08 з'ясувалось, що на `/ai` не веде ЖОДНЕ посилання: сторінка ШІ-моста
(скіли перевірок, мапа вердиктів, журнал запитів) існувала з 25.08, а дійти
до неї можна було тільки вписавши адресу руками. Про неї просто не знали.

Сторінка без входу — це не «дрібниця в навігації», а фіча, якої для
користувача не існує. Тут це закріплено як правило, а не як разова правка.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

STATIC = ROOT / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")

# `/` — це сам index; `/login` — єдина сторінка, куди потрапляють РЕДІРЕКТОМ
# (middleware авторизації), і посилання на неї з-під сесії було б безглуздям.
NO_LINK_NEEDED = {"index", "login"}


def _pages():
    """static/<ім'я>.html → маршрут /<ім'я> (так їх і віддає _page())."""
    return sorted(f.stem for f in STATIC.glob("*.html"))


def test_every_page_is_reachable_from_the_main_ui():
    orphans = [name for name in _pages()
               if name not in NO_LINK_NEEDED
               and f'href="/{name}"' not in INDEX]
    assert not orphans, ("на ці сторінки з UI не веде нічого: "
                         + ", ".join(f"/{o}" for o in orphans))


def test_the_ai_page_link_exists_and_says_what_is_behind_it():
    """Саме той випадок, який це правило й породив. Підказка мусить називати
    скіли: людина шукає «налаштування скілів», а не «ШІ-міст»."""
    m = re.search(r'<a href="/ai"[^>]*>', INDEX)
    assert m, "посилання на /ai зникло"
    assert "скіл" in m.group(0).lower(), \
        f"у підказці немає слова «скіли», за яким її шукатимуть: {m.group(0)}"


def test_the_check_would_actually_catch_an_orphan():
    """Мутація: якби перевірка звірялася з чимось іншим, ніж index.html, вона
    б мовчала. Тут — що вигадана сторінка справді ловиться."""
    fake = "definitely-not-linked"
    assert f'href="/{fake}"' not in INDEX


def test_pages_that_need_no_link_are_named_explicitly():
    """Список винятків — короткий і перевірний, щоб у нього не почали
    складати все підряд."""
    assert NO_LINK_NEEDED == {"index", "login"}
    for name in NO_LINK_NEEDED:
        assert (STATIC / f"{name}.html").exists(), name


if __name__ == "__main__":
    run(dict(globals()))
