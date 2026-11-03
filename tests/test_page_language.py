"""Тести page_language: текст сторінки має відповідати <html lang=…>."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("page_language")

EN = ("We provide the best consulting services for your business. "
      "Our team will help you with all the questions that you have about "
      "strategy, and we are sure that this is more than you can expect "
      "from any other company in the market today. ") * 3
PT = ("Oferecemos os melhores serviços de consultoria para o seu negócio. "
      "A nossa equipa vai ajudar você com todas as questões que tem sobre "
      "estratégia, e temos certeza de que isso é mais do que você pode "
      "esperar de qualquer outra empresa no mercado. ") * 3
DE = ("Wir bieten die besten Beratungsdienste für Ihr Unternehmen. Unser "
      "Team wird Ihnen bei allen Fragen helfen, die Sie über die Strategie "
      "haben, und wir sind sicher, dass dies mehr ist, als Sie von einem "
      "anderen Unternehmen erwarten können. ") * 3
ES = ("Ofrecemos los mejores servicios de consultoría para su negocio. "
      "Nuestro equipo le ayudará con todas las preguntas que usted tiene "
      "sobre la estrategia, y estamos seguros de que esto es más de lo que "
      "puede esperar de cualquier otra empresa del mercado. ") * 3
TH = ("เราให้บริการที่ปรึกษาที่ดีที่สุดสำหรับธุรกิจของคุณ ทีมงานของเราจะช่วยคุณ "
      "ในทุกคำถามเกี่ยวกับกลยุทธ์ และเรามั่นใจว่านี่คือสิ่งที่ดีที่สุดในตลาด ") * 5


def _page(lang, body):
    return (f'<!DOCTYPE html>\n<html lang="{lang}">\n<head><title>X</title>'
            f'<style>.a{{color:red}}</style>'
            f'<script>var the_and_of = "to is are that with";</script></head>'
            f'<body><main><p>{body}</p></main></body></html>')


def test_english_on_pt_page_flagged():
    issues = mod.run("index.php", _page("pt-BR", EN))
    assert len(issues) == 1 and issues[0]["severity"] == "error"
    assert "en" in issues[0]["message"] and 'pt' in issues[0]["message"]
    assert issues[0]["line"] == 2                # рядок з <html lang=…>


def test_matching_languages_silent():
    assert mod.run("a.html", _page("pt-BR", PT)) == []
    assert mod.run("a.html", _page("de-CH", DE)) == []
    assert mod.run("a.html", _page("es", ES)) == []
    assert mod.run("a.html", _page("en", EN)) == []


def test_es_pt_not_confused():
    # близькі мови зі спільними стоп-словами — не фолсити в обидва боки
    assert mod.run("a.html", _page("pt-BR", PT)) == []
    assert mod.run("a.html", _page("es-MX", ES)) == []


def test_german_on_english_page_flagged():
    issues = mod.run("a.html", _page("en", DE))
    assert len(issues) == 1 and "de" in issues[0]["message"]


def test_thai_lang_with_thai_text_ok_and_latin_flagged():
    assert mod.run("a.html", _page("th", TH)) == []
    issues = mod.run("a.html", _page("th", EN))
    assert len(issues) == 1 and "письм" in issues[0]["message"]


def test_thai_text_on_latin_page_flagged():
    issues = mod.run("a.html", _page("pt-BR", TH))
    assert len(issues) == 1 and "th" in issues[0]["message"]


def test_short_text_not_judged():
    assert mod.run("a.html", _page("pt-BR", "Hello world, welcome!")) == []


def test_no_lang_attr_skipped():
    page = f"<html><body><p>{EN}</p></body></html>"
    assert mod.run("a.html", page) == []


def test_unknown_lang_skipped():
    assert mod.run("a.html", _page("vi", EN)) == []


def test_script_and_style_ignored():
    # стоп-слова в <script>/<style>/коментарях не мають впливати
    page = _page("pt-BR", PT).replace("</body>",
        '<script>the and of to is are you that for with this from your</script>'
        '<!-- the and of to is are you that for with -->'
        "</body>")
    assert mod.run("a.html", page) == []


def test_small_english_banner_is_tolerated():
    """Трошки англійської можна, якщо це не вся сторінка.
    Реальні дані: 67 сторінок корпусу мали саме цей варн — неперекладений
    кукі-банер (21 слово) на 404/thank-you, максимум 26% тексту."""
    banner = ("We use cookies to operate this site and, with your consent, "
              "for analytics and marketing purposes today.")
    page = _page("pt-BR", PT).replace("</main>", f"<div>{banner}</div></main>")
    assert mod.run("index.php", page) == []


def test_dominant_english_fragment_flagged():
    """А ось коли англійська — більша частина сторінки, це вже не «трошки»."""
    banner = ("We use cookies to operate this site and, with your consent, "
              "for analytics and marketing purposes today. ") * 6
    short_pt = ("Oferecemos os melhores serviços de consultoria para o seu "
                "negócio hoje, com toda a nossa equipa e mais sobre isso. ")
    page = _page("pt-BR", short_pt).replace("</main>", f"<div>{banner}</div></main>")
    issues = mod.run("index.php", page)
    assert issues and any("en" in i["message"] for i in issues), issues


def test_embedded_english_name_in_own_sentence_ok():
    # англійська власна назва всередині pt-речення — не фрагмент
    page = _page("pt-BR", PT).replace("</main>",
        "<p>Instale a extensão Google Analytics Opt-out Browser Add-on "
        "disponível para o seu navegador em nossa página.</p></main>")
    assert mod.run("a.html", page) == []


def test_short_english_nav_ok():
    page = _page("pt-BR", PT).replace("</main>",
        "<nav><a>Home</a><a>About us</a><a>Contact</a></nav></main>")
    assert mod.run("a.html", page) == []


def test_php_blocks_ignored():
    page = ('<?php $the = "and of to is are that with from your our"; ?>\n'
            + _page("pt-BR", PT))
    assert mod.run("index.php", page) == []


# ---------------------------------------------------------------- чуже письмо
RU_PAGE = ("Мы предлагаем лучшие консультационные услуги для вашего бизнеса. "
           "Наша команда поможет вам со всеми вопросами о стратегии, и мы "
           "уверены, что это больше, чем вы можете ожидать от любой другой "
           "компании на рынке сегодня. ") * 3


def test_russian_cta_on_pt_page_flagged():
    """Реальний кейс STUDIO_br-*: <a class="btn btn-primary">Записаться на
    обучение</a> на lang="pt" — чек давав 0. Три кириличні слова на
    латинській сторінці однозначні, тож поріг тут низький, а severity — error."""
    page = _page("pt-BR", PT).replace(
        "</main>",
        '<a href="#contact" class="btn btn-primary">Записаться на обучение</a></main>')
    issues = mod.run("index.php", page)
    assert issues, "кирилиця на pt-сторінці мусить ловитись"
    assert any(i["severity"] == "error" for i in issues), issues
    assert any("Записаться" in i["message"] for i in issues), issues


def test_russian_page_level_on_pt_flagged():
    issues = mod.run("index.php", _page("pt-BR", RU_PAGE))
    assert len(issues) == 1 and issues[0]["severity"] == "error", issues


def test_cyrillic_page_with_ru_lang_is_clean():
    assert mod.run("index.php", _page("ru", RU_PAGE)) == []


def test_cyrillic_page_with_uk_lang_is_clean():
    uk = ("Ми пропонуємо найкращі консультаційні послуги для вашого бізнесу. "
          "Наша команда допоможе вам з усіма питаннями щодо стратегії. ") * 4
    assert mod.run("index.php", _page("uk", uk)) == []


def test_single_cyrillic_word_is_flagged():
    """Раніше одне слово прощали як «може бути бренд». Корпус (7518 сторінок)
    показав протилежне: з 22 таких знахідок 21 — справжній дефект, тож поріг
    опущено до одного слова. Кирилиця на pt-вітці не буває легітимною."""
    page = _page("pt-BR", PT).replace("</main>", "<span>Яндекс</span></main>")
    issues = mod.run("a.html", page)
    assert issues and any("Яндекс" in i["message"] for i in issues), issues


def test_cyrillic_homoglyph_in_email_is_flagged():
    """Найкоштовніший клас: `info@alpinеjourneys.com` з кириличною `е`
    (U+0435) виглядає нормально, але пошта на нього не дійде. Одне «слово» —
    старий поріг 2 його не бачив."""
    page = _page("pt-BR", PT).replace(
        "</main>", '<a href="#">info@alpin\u0435journeys.com</a></main>')
    issues = mod.run("a.html", page)
    assert issues, "гомогліф у пошті мусить ловитись"
    assert any("journeys" in i["message"] for i in issues), issues


def test_cyrillic_glued_inside_latin_word_is_flagged():
    """Реальний кейс auto_br-*: «Como proходит o aprendizado» — кирилиця
    всередині португальського речення, одним словом."""
    page = _page("pt-BR", PT).replace(
        "</main>", "<h2>Como pro\u0445одит o aprendizado</h2></main>")
    issues = mod.run("a.html", page)
    assert issues and any(i["severity"] == "error" for i in issues), issues


def test_clean_pt_page_stays_clean():
    """Захист від протилежного зсуву: чиста сторінка мовчить."""
    assert mod.run("index.php", _page("pt-BR", PT)) == []


def test_hebrew_fragment_on_pt_flagged():
    page = _page("pt-BR", PT).replace(
        "</main>", "<p>אנחנו מספקים שירותי ייעוץ מעולים</p></main>")
    issues = mod.run("a.html", page)
    assert issues and any(i["severity"] == "error" for i in issues), issues


def test_arabic_fragment_on_pt_still_flagged():
    page = _page("pt-BR", PT).replace(
        "</main>", "<p>نحن نقدم أفضل خدمات الاستشارات لعملك</p></main>")
    assert mod.run("a.html", page), "арабський фрагмент мусить ловитись"


def test_cyrillic_inside_script_and_comment_ignored():
    """Коментарі й скрипти — не контент: '// бьёт любой CSS' не є проблемою."""
    page = _page("pt-BR", PT).replace(
        "</main>",
        "<!-- авто-страховка кукі-банера і контрасту -->"
        "<script>var x = 'бьёт любой CSS без important';</script></main>")
    assert mod.run("a.html", page) == []


if __name__ == "__main__":
    run(dict(globals()))
