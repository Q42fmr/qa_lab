"""Тести footer_address: порожній рядок адреси у футері.

Фікс має два шляхи, і тести тримають обидва: є джерело у юридичних сторінках
вітки - адресу вписуємо; немає - рядок прибираємо, як зникає рядок телефону
без телефону.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("footer_address")

PIN = ('<svg class="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" '
       'viewBox="0 0 24 24" aria-hidden="true"><path d="M17.657 16.657L13.414 20.9"/>'
       '</svg>')

FOOTER = (
    '<template>\n'
    '  <footer class="bg-white py-14">\n'
    '    <div class="flex flex-col gap-3 text-sm">\n'
    '      <a href="mailto:info@x.sbs" class="flex items-center gap-2">\n'
    '        <svg viewBox="0 0 24 24"><path d="M3 8l7.89 5.26"/></svg>\n'
    '        info@x.sbs\n'
    '      </a>\n'
    '      <a v-if="hasPhone" :href="\'tel:\' + phone" class="flex items-center gap-2">\n'
    '        <svg viewBox="0 0 24 24"><path d="M3 5a2 2 0 012-2"/></svg>\n'
    '        {{ phone }}\n'
    '      </a>\n'
    '      <address class="not-italic flex items-start gap-2 text-gray-500">\n'
    '        ' + PIN + '\n'
    '        <span></span>\n'
    '      </address>\n'
    '    </div>\n'
    '  </footer>\n'
    '</template>\n')

FOOTER_PATH = "src/components/GlobalFooter.vue"
LEGAL_PATH = "src/components/PrivacyInfoPrivacy.vue"

ADDR = "Rua das Palmeiras, 245, Sala 7, Joinville, SC 89201-400, Brasil"


def _legal(text):
    return "<template><section><p>" + text + "</p></section></template>"


def _run(files):
    return mod.run_branch(dict(files), list(files))


def _fix(files):
    return {a["path"]: a["content"]
            for a in mod.fix_branch(dict(files), list(files), "nwf-x-br-pt")}


# --------------------------------------------------------------- детект
def test_empty_address_is_flagged():
    """Кейс nwf-cebnbilepot-br-pt: `<span></span>` порожній У ДЖЕРЕЛІ, тож на
    сторінці висить самотній пін (заміряно рендером: innerText порожній,
    коробка 258x18)."""
    issues = _run({FOOTER_PATH: FOOTER})
    assert len(issues) == 1, issues
    assert issues[0]["path"] == FOOTER_PATH, issues
    assert issues[0]["severity"] == "error", issues


def test_filled_address_is_not_touched():
    html = FOOTER.replace("<span></span>", "<span>" + ADDR + "</span>")
    assert _run({FOOTER_PATH: html}) == []
    assert _fix({FOOTER_PATH: html}) == {}


def test_bound_address_is_not_touched():
    """`{{ address }}` означає, що текст приходить у рантаймі - тоді порожнього
    рядка у DOM не буде, і це не наша поломка."""
    html = FOOTER.replace("<span></span>", "<span>{{ address }}</span>")
    assert _run({FOOTER_PATH: html}) == []
    assert _fix({FOOTER_PATH: html}) == {}


def test_email_and_phone_rows_are_not_flagged():
    """Ловимо саме `<address>`: у корпусі всі 74 пін-рядки лежать у ньому, а
    безтекстових пінів поза `<address>` - нуль."""
    issues = _run({FOOTER_PATH: FOOTER})
    assert len(issues) == 1, issues
    assert "адрес" in issues[0]["message"], issues


# ------------------------------------------------- фікс: джерела немає
def test_attribute_bound_address_is_not_touched():
    """`v-text` теж наповнює рядок у рантаймі, а видимого тексту у джерелі не
    лишає - і тоді фікс ВИДАЛИВ би робочий рядок. У корпусі такої форми нуль
    (усі 685 віток), але гард дешевий, а ціна помилки - знищений контент."""
    html = FOOTER.replace('<span></span>', '<span v-text="address"></span>')
    assert _run({FOOTER_PATH: html}) == []
    assert _fix({FOOTER_PATH: html}) == {}


def test_row_is_removed_when_there_is_no_source():
    """У 9 віток корпусу адреси немає НІДЕ, тож вигадувати нічого - рядок
    зникає, як зникає телефон при `v-if="hasPhone"`."""
    out = _fix({FOOTER_PATH: FOOTER})[FOOTER_PATH]
    assert "<address" not in out, out
    assert "17.657 16.657" not in out, out


def test_removal_keeps_the_other_contact_rows():
    out = _fix({FOOTER_PATH: FOOTER})[FOOTER_PATH]
    for keep in ("mailto:info@x.sbs", "{{ phone }}", "hasPhone", "</footer>"):
        assert keep in out, (keep, out)


def test_removal_leaves_no_blank_line():
    """Вирізаємо разом з відступом і переносом - інакше лишався б рядок
    з пробілами."""
    out = _fix({FOOTER_PATH: FOOTER})[FOOTER_PATH]
    assert not [ln for ln in out.splitlines() if ln.strip() == ""], out
    assert "\n      \n" not in out, out


def test_removal_keeps_the_indentation_of_what_follows():
    """Ріжемо ВІД початку рядка, інакше відступ вирізаного зростається з
    наступним рядком і той зʼїжджає вправо."""
    out = _fix({FOOTER_PATH: FOOTER})[FOOTER_PATH]
    assert "\n    </div>\n" in out, out
    assert "\n  </footer>" in out, out


def test_removal_is_idempotent():
    once = _fix({FOOTER_PATH: FOOTER})
    assert mod.fix_branch(dict(once), list(once), "nwf-x-br-pt") == []
    assert _run(once) == []


# ------------------------------------------------- фікс: джерело є
def test_address_from_a_legal_page_is_written_in():
    files = {FOOTER_PATH: FOOTER, LEGAL_PATH: _legal(ADDR)}
    out = _fix(files)[FOOTER_PATH]
    assert "<span>" + ADDR + "</span>" in out, out
    assert "<address" in out, out          # рядок лишається, він тепер осмислений


def test_only_the_footer_file_is_edited():
    files = {FOOTER_PATH: FOOTER, LEGAL_PATH: _legal(ADDR)}
    assert list(_fix(files)) == [FOOTER_PATH]


def test_label_is_stripped():
    files = {FOOTER_PATH: FOOTER, LEGAL_PATH: _legal("Endereço: " + ADDR)}
    out = _fix(files)[FOOTER_PATH]
    assert "<span>" + ADDR + "</span>" in out, out


def test_the_most_complete_variant_wins():
    """У 33 віток корпусу кілька варіантів однієї адреси різної повноти -
    беремо найповніший (усі 33 сходяться на одній вулиці)."""
    short = "Rua das Palmeiras, 245, Joinville, SC 89201-400"
    files = {FOOTER_PATH: FOOTER,
             LEGAL_PATH: _legal(short),
             "src/components/TermsContentTerms.vue": _legal(ADDR)}
    out = _fix(files)[FOOTER_PATH]
    assert "<span>" + ADDR + "</span>" in out, out


def test_same_street_type_different_name_is_still_a_conflict():
    """Звіряємо тип І назву: дві `Rua` з різними назвами - це різні адреси, і
    вибір між ними був би вгадуванням. Порівняння лише за типом («rua») злило б
    їх в одну й дало найдовшу навмання."""
    other = "Rua Sergipe, 1245, Sala 3, Belo Horizonte, MG 30130-010, Brasil"
    files = {FOOTER_PATH: FOOTER,
             LEGAL_PATH: _legal(ADDR),
             "src/components/TermsContentTerms.vue": _legal(other)}
    assert "<address" not in _fix(files)[FOOTER_PATH]


def test_conflicting_streets_are_not_guessed():
    """Кандидати про різні вулиці - не вгадуємо, а прибираємо рядок. У корпусі
    сьогодні таких нуль (усі 33 багатоваріантні сходяться), тож умову тримає
    тест, а не спостереження."""
    other = "Avenida Beira Mar, 100, Florianópolis, SC 88010-000, Brasil"
    files = {FOOTER_PATH: FOOTER,
             LEGAL_PATH: _legal(ADDR),
             "src/components/TermsContentTerms.vue": _legal(other)}
    out = _fix(files)[FOOTER_PATH]
    assert "<address" not in out, out


def test_address_outside_legal_pages_is_not_a_source():
    """Джерело - юридичні сторінки, де адреса мусить бути за законом. Вулиця
    у відгуку клієнта чи в тексті послуги нею не є."""
    files = {FOOTER_PATH: FOOTER,
             "src/components/TestimonialsBlock.vue": _legal(ADDR)}
    out = _fix(files)[FOOTER_PATH]
    assert "<address" not in out, out


def test_address_without_a_span_gets_the_text_appended():
    html = FOOTER.replace("        <span></span>\n", "")
    files = {FOOTER_PATH: html, LEGAL_PATH: _legal(ADDR)}
    out = _fix(files)[FOOTER_PATH]
    assert ADDR in out, out
    assert "<address" in out, out


# ------------------------------------------- що адресою НЕ вважається
def test_a_date_is_not_an_address():
    """`1º de Agosto, 2026` — реальний рядок з PrivacyInfoPrivacy.vue корпусу."""
    files = {FOOTER_PATH: FOOTER, LEGAL_PATH: _legal("1º de Agosto, 2026")}
    assert "<address" not in _fix(files)[FOOTER_PATH]


def test_a_fragment_without_a_street_is_not_an_address():
    """`Rio de Janeiro, RJ 22410-003` — обрізок речення з корпусу: місто й CEP
    є, вулиці немає."""
    files = {FOOTER_PATH: FOOTER,
             LEGAL_PATH: _legal("Rio de Janeiro, RJ 22410-003")}
    assert "<address" not in _fix(files)[FOOTER_PATH]


def test_a_house_number_is_not_a_postal_code():
    """`Rua Sergipe, 1245, sala 802` — вулиця є, коду немає: 1245 це номер
    будинку. Код мусить стояти поруч із назвою міста."""
    files = {FOOTER_PATH: FOOTER,
             LEGAL_PATH: _legal("Rua Sergipe, 1245, sala 802")}
    assert "<address" not in _fix(files)[FOOTER_PATH]


def test_middot_separated_address_is_accepted():
    """Кома НЕ обовʼязкова: у корпусі 4 справжні адреси писані через `·`
    (`nwf-zuontfug-befelur-ch-de`, `nwf-bivhewz-dinisep-my-en`,
    `nwf-alaavwa-nenekeoc-mx-es`, `nwf-nepjnacl-sojidiihr-ch-de`). Спершу тут
    стояла вимога коми - вона їх усіх втрачала, а сміття не відсіювала."""
    dots = "Bahnhofstrasse 42 · Zürich · Zürich 8001 · Schweiz"
    files = {FOOTER_PATH: FOOTER,
             "src/components/ImpressumLegal.vue": _legal(dots)}
    assert "<span>" + dots + "</span>" in _fix(files)[FOOTER_PATH]


def test_swiss_postal_code_before_the_city_is_accepted():
    """`8001 Zürich` — ch-de пише код ПЕРЕД містом, і код там чотиризначний."""
    ch = "Bahnhofstrasse 24, 8001 Zürich, Schweiz"
    files = {FOOTER_PATH: FOOTER,
             "src/components/ImpressumLegal.vue": _legal(ch)}
    assert "<span>" + ch + "</span>" in _fix(files)[FOOTER_PATH]


def test_check_is_node_auto():
    assert mod.PROJECTS == ["node"], mod.PROJECTS
    assert mod.GROUP == "auto"


if __name__ == "__main__":
    run(dict(globals()))
