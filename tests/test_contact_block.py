"""Контакти біля лід-форми vue-вайта (checks/contact_block.py).

Кейс nwf-arike-jabgag-br-pt: «Нет вкладки контактов с телефоном, почтой,
адресом и названием» — форма є, а поруч жодного контакту. У здорових вітках
сім'ї (nwf-abeburoni-tepbidu-br-pt) секція форми — grid lg:grid-cols-2 з
карткою контактів поруч. Запуск фікса — ЛИШЕ РУЧНИЙ (GROUP="review").
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("contact_block")

BRANCH = "nwf-arike-jabgag-br-pt"

# форма як у aroma: одна колонка, картка формі, жодних контактів
FORM = """<template>
  <section class="bg-orange-50 py-16 px-4" id="form">
    <div class="max-w-xl mx-auto">
      <div class="bg-orange-600 rounded-md shadow-sm p-8 md:p-12">
        <h2 class="font-serif text-white">Mantenha seu jardim</h2>
        <form class="space-y-5">
          <input type="text" name="name">
          <button type="submit" class="w-full bg-teal-600 text-white rounded-md">Enviar</button>
        </form>
      </div>
    </div>
  </section>
</template>
"""

FOOTER = """<template>
  <footer>
    <a href="tel:+55 85 98047-5613">+55 85 98047-5613</a>
    <a href="mailto:info@arikejabgag.world">info@arikejabgag.world</a>
  </footer>
</template>
"""

TERMS = """<template>
  <p>Arike Jabgag, Rua das Orquídeas, Fortaleza, Brasil</p>
</template>
"""


def _files(form=FORM):
    return {"src/components/ContactFormHome.vue": form,
            "src/components/BottomSection.vue": FOOTER,
            "src/components/UserTermsTerms.vue": TERMS}


def _run(files, branch=BRANCH):
    return mod.run_branch(dict(files), list(files), branch)


def _fix(files, branch=BRANCH):
    return {a["path"]: a for a in mod.fix_branch(dict(files), list(files), branch)}


# ------------------------------------------------------------------ детект
def test_form_without_contacts_is_flagged():
    issues = _run(_files())
    assert len(issues) == 1, issues
    i = issues[0]
    assert i["path"] == "src/components/ContactFormHome.vue"
    assert i["severity"] == "error"
    assert "контакт" in i["message"], i


def test_partial_nearby_block_is_flagged_and_completed():
    # 02.10: блок біля форми Є (mailto), але неповний — детект перелічує
    # брак, фікс ДОПИСУЄ рядки у блок, не зносячи наявний; адреса — з
    # футера вітки (футерна лишається і дублюється — пріоритет над гео)
    form = FORM.replace("</form>", '</form><a href="mailto:x@y.z">x@y.z</a>')
    files = _files(form)
    data = mod._branch_data(dict(files), BRANCH)
    issues = _run(files)
    assert len(issues) == 1 and "неповний" in issues[0]["message"], issues
    assert "телефон" in issues[0]["message"]
    assert "адреса" in issues[0]["message"]
    assert "CNPJ" in issues[0]["message"]        # br-вітка — пул дає номер
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    assert 'href="mailto:x@y.z"' in out          # наявне не знесено
    assert "tel:+55" in out
    assert data["addr"] in out                    # футерна адреса здубльована
    assert data["regno"] in out                   # «CNPJ …» з пулу
    # після доповнення — повний і тихий, фікс ідемпотентний
    healed = {**files, "src/components/ContactFormHome.vue": out}
    assert mod.run_branch(dict(healed), list(healed), BRANCH) == []
    assert mod.fix_branch(dict(healed), list(healed), BRANCH) == []


def test_swiss_branch_block_carries_uid_from_the_pool():
    """ch-* вітка: замість CNPJ у картці рядок «UID: CHE-…» — з того самого
    пулу, що й чек uid_che; підпис рядка «UID»."""
    form = FORM.replace("</form>", '</form><a href="mailto:x@y.z">x@y.z</a>')
    files = _files(form)
    data = mod._branch_data(dict(files), "nwf-alpen-ch-de")
    assert data["regno"].startswith("UID: CHE-"), data
    issues = mod.run_branch(dict(files), list(files), "nwf-alpen-ch-de")
    assert len(issues) == 1 and "UID" in issues[0]["message"], issues
    out = _fix(files, "nwf-alpen-ch-de")["src/components/ContactFormHome.vue"]["content"]
    assert data["regno"] in out and "CNPJ" not in out, out
    healed = {**files, "src/components/ContactFormHome.vue": out}
    assert mod.run_branch(dict(healed), list(healed), "nwf-alpen-ch-de") == []


def test_batch_numbered_br_branch_keeps_portuguese_and_cnpj():
    """nwf-…-br-pt-2: «-2» — номер партії, локаль та сама (choa-nono 28.10) —
    підписи картки португальські, CNPJ з пулу, як і без нього. Пул — у
    тимчасовій теці: справжній стан лаби тест не чіпає."""
    import tempfile
    from pathlib import Path
    import cnpj_pool
    import projects
    root, seed, state_root = Path(tempfile.mkdtemp(prefix="cb-")), cnpj_pool.SEED, projects.state_root
    projects.state_root, cnpj_pool.SEED = (lambda: root), root / "no-seed.json"
    try:
        cnpj_pool.add("11.222.333/0001-81")
        out = _fix(_files(), BRANCH + "-2")["src/components/ContactFormHome.vue"]["content"]
    finally:
        projects.state_root, cnpj_pool.SEED = state_root, seed
    assert "Telefone" in out and "Endereço" in out, out
    assert "CNPJ 11.222.333/0001-81" in out, out


def test_footer_address_without_postal_code_feeds_the_card():
    """homtud-ficemvi-hr-hr 19.10: у футері «Ulica Petra Preradovića 12, Osijek,
    Hrvatska» (без індексу, hr-вуличне слово), гео-бази hr-hr немає — картка
    лишалась без адреси, QA повертав. Адреса з футера/контактів береться
    після юридичних сторінок, хвіст («Radno vrijeme …») відрізається. Блок
    тут — два голі лінки під формою: адреса стає наступним рядком того ж
    почерку (21.10), а не окремою карткою."""
    form = FORM.replace("</form>", '</form><a href="mailto:x@y.z">x@y.z</a><a href="tel:+38514275693">+385 1 427 5693</a>')
    footer = ("<template><footer><p>Homtud Ficemvi</p><p>Ulica Petra Preradovića 12, Osijek, Hrvatska</p>"
              "<p>Radno vrijeme Ponedjeljak - Petak 09:00–17:00</p></footer></template>")
    files = {"src/components/ContactFormHome.vue": form, "src/components/Footer.vue": footer}
    data = mod._branch_data(dict(files), "nwf-homtud-ficemvi-hr-hr")
    assert data["addr"] == "Ulica Petra Preradovića 12, Osijek, Hrvatska", data["addr"]
    issues = mod.run_branch(dict(files), list(files), "nwf-homtud-ficemvi-hr-hr")
    assert len(issues) == 1 and "адреса" in issues[0]["message"], issues
    out = _fix(files, "nwf-homtud-ficemvi-hr-hr")["src/components/ContactFormHome.vue"]["content"]
    assert out.index("+385 1 427 5693</a>") < \
        out.index("<p>Ulica Petra Preradovića 12, Osijek, Hrvatska</p>"), out
    healed = {**files, "src/components/ContactFormHome.vue": out}
    assert mod.run_branch(dict(healed), list(healed), "nwf-homtud-ficemvi-hr-hr") == []


def test_middot_fields_and_two_paragraph_address_are_kept_whole():
    """broni-cospubtenp-hr-hr 20.10: privacy має «Ulica Slobode 14 &middot;
    Split &middot; Hrvatska» (· — роздільник полів, не хвіст), terms — адресу
    у двох <p> («Ulica Slobode 14» / «Split, … 21000»). Картка отримувала
    лише «Ulica Slobode 14»."""
    form = FORM.replace("</form>", '<a href="mailto:x@y.z">x@y.z</a><a href="tel:+38521384519">+385 21 384 519</a>')
    privacy = "<template><main><p>info@broni.click</p>\n<p>Ulica Slobode 14 &middot; Split &middot; Hrvatska</p>\n</main></template>"
    files = {"src/components/ContactFormHome.vue": form, "src/components/PrivacyPolicyPrivacy.vue": privacy}
    assert mod._branch_data(dict(files), "nwf-breza-hr-hr")["addr"] == "Ulica Slobode 14 · Split · Hrvatska"
    terms = "<template><main>\n<p>Ulica Slobode 14</p>\n<p>Split, Dalmatinska županija 21000</p>\n<p>+385 21 384 519</p></main></template>"
    files = {"src/components/ContactFormHome.vue": form, "src/components/UserTermsTerms.vue": terms}
    assert mod._branch_data(dict(files), "nwf-breza-hr-hr")["addr"] == "Ulica Slobode 14, Split, Dalmatinska županija 21000"

def test_form_with_full_block_nearby_is_clean():
    # повний блок — це й назва сайту (21.10: у чужому блоці вона теж судиться)
    form = FORM.replace("</form>", (
        '</form><p>Arike Jabgag</p><a href="mailto:x@y.z">x@y.z</a>'
        '<a href="tel:+5511999887766">+55 11 99988-7766</a>'
        '<p>Rua das Orquídeas, Fortaleza, Brasil</p>'
        '<p>CNPJ 60.006.171/0001-50</p>'))
    assert _run(_files(form)) == []


def test_branch_without_any_contact_data_reports_without_fix():
    # локаль БЕЗ гео-баз (de-de): даних взяти нізвідки — чесний ручний режим
    files = {"src/components/ContactFormHome.vue": FORM}
    issues = mod.run_branch(dict(files), list(files), "nwf-x-de-de")
    assert len(issues) == 1 and "не знайшов" in issues[0]["message"], issues
    assert mod.fix_branch(dict(files), list(files), "nwf-x-de-de") == []


def test_geo_bases_feed_full_card_when_branch_is_empty():
    # прохання 01.10: картка має нести назву, пошту, телефон І адресу —
    # на порожній вітці телефон/адреса приходять з гео-баз локалі
    files = {"src/components/ContactFormHome.vue": FORM,
             "index.html": "<title>Tele Lab — automação</title>"}
    out = mod.fix_branch(dict(files), list(files), BRANCH)
    card = next(a["content"] for a in out
                if a["path"] == "src/components/ContactFormHome.vue")
    assert "tel:+55" in card, card                     # телефон з гео-бази
    import checks.address_number as _an
    assert _an._geo_pick(BRANCH) in card               # адреса з гео-бази
    assert ">Tele Lab</h3>" in card                    # назва з title


def test_non_form_component_is_ignored():
    files = {"src/components/HeroHome.vue": "<template><section><h1>Oi</h1></section></template>"}
    assert _run(files) == []


# ------------------------------------------------------------------ автофікс
def test_fix_adds_the_contact_card_beside_the_form():
    out = _fix(_files())["src/components/ContactFormHome.vue"]["content"]
    # контейнер стає ґридом і ширшає — картка саме ПОРУЧ, як у здорової сім'ї
    assert "lg:grid-cols-2" in out and "max-w-5xl" in out, out
    assert "max-w-xl" not in out, out
    # всі чотири складові: назва, телефон, пошта, адреса
    assert "Arike Jabgag" in out, out
    assert 'href="tel:+55 85 98047-5613"' in out, out
    assert 'href="mailto:info@arikejabgag.world"' in out, out
    assert "Rua das Orquídeas, Fortaleza, Brasil" in out, out
    # локалізовані підписи (-br-pt → португальська)
    assert "Telefone" in out and "Endereço" in out, out
    # акцент — з кнопки форми (bg-teal-600 → text-teal-600)
    assert "text-teal-600" in out, out
    # форму не чіпали
    assert '<form class="space-y-5">' in out, out


def test_fix_is_idempotent():
    fixed = _fix(_files())["src/components/ContactFormHome.vue"]["content"]
    files = _files(fixed)
    assert _run(files) == []
    assert _fix(files) == {}


def test_labels_follow_the_branch_locale():
    out = _fix(_files(), branch="nwf-arike-jabgag-co-es")[
        "src/components/ContactFormHome.vue"]["content"]
    assert "Teléfono" in out and "Dirección" in out, out


def test_partial_data_renders_partial_card():
    files = {"src/components/ContactFormHome.vue": FORM,
             "src/components/BottomSection.vue":
                 '<template><a href="mailto:oi@x.world">oi@x.world</a></template>'}
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    assert 'href="mailto:oi@x.world"' in out, out
    # телефону/адреси у вітці немає — приходять з гео-баз локалі (01.10),
    # картка завжди повна: пошта + телефон + адреса + назва
    assert "tel:+55" in out, out
    import checks.address_number as _an
    assert _an._geo_pick(BRANCH) in out, out


# кейс nwf-reqeruxsoe-fije / nwf-remalo-luhiime: пошта і телефон у вітці Є,
# але звичайним текстом (без mailto:/tel:) — фікс мусить їх узяти, а
# заглушки макета (placeholder-атрибути, seu@…) — ні
RESIDENCIA = {
    "src/components/MessageFormHome.vue": FORM.replace(
        '<input type="text" id="cf12-name"',
        '<input type="text" placeholder="seu@email.com" id="cf12-name"'),
    "src/components/BottomSection.vue":
        "<template><footer><p>Fale conosco: info@remaloluhiime.digital</p>"
        "<p>+55 38 97326-4189</p></footer></template>",
}


def test_text_contacts_without_links_feed_the_fix():
    out = _fix(dict(RESIDENCIA))["src/components/MessageFormHome.vue"]["content"]
    assert 'href="mailto:info@remaloluhiime.digital"' in out, out
    assert 'href="tel:+5538973264189"' in out, out
    assert "+55 38 97326-4189" in out, out              # видимий підпис — як у вітці
    assert "seu@email.com" not in out, out              # заглушка не контакт


def test_placeholder_junk_alone_is_still_manual():
    # локаль без гео-баз: сміття-заглушки не контакти, фікс чесно пасує
    files = {"src/components/ContactFormHome.vue": FORM,
             "src/components/BottomSection.vue":
                 "<template><p>seu.email@exemplo.com</p>"
                 "<p>CNPJ 12.345.678/0001-90</p></template>"}
    issues = mod.run_branch(dict(files), list(files), "nwf-x-de-de")
    assert len(issues) == 1 and "ні лінком, ні текстом" in issues[0]["message"], issues
    assert mod.fix_branch(dict(files), list(files), "nwf-x-de-de") == []


# кейс nwf-enhupse-mazozvo-br-pt: контакти УЖЕ є, але текстом і байндингом
ENCANTO = """<template>
  <section class="bg-white py-16 px-4" id="form">
    <div class="max-w-2xl mx-auto">
      <div class="text-center mb-10"><h2>Entre em contato</h2></div>
      <div class="flex gap-16 mb-8">
        <div><span>E-MAIL</span><span>info@enhupsemazozvo.lat</span></div>
        <div v-if="hasPhone"><span>TELEFONE</span><span>{{ phone }}</span></div>
      </div>
      <div class="border-t border-neutral-200 mb-10"></div>
      <form class="space-y-6">
        <input type="email" placeholder="seuemail@contato.com">
        <button type="submit" class="bg-orange-600">Enviar</button>
      </form>
    </div>
  </section>
</template>
"""


def test_plaintext_email_and_phone_binding_count_as_contacts():
    """Кривий кейс encanto: пошта звичайним текстом, телефон — {{ phone }}.
    Жодного tel:/mailto:, але тел/пошта Є — «бракує» лише адреса/CNPJ
    (новий флоу 02.10: блок доводиться до повного)."""
    files = {"src/components/ContactFormHome.vue": ENCANTO,
             "src/components/BottomSection.vue": FOOTER}
    issues = _run(files)
    assert len(issues) == 1 and "неповний" in issues[0]["message"], issues
    assert "телефон" not in issues[0]["message"]      # биндинг = телефон є
    assert "пошта" not in issues[0]["message"]
    assert "адреса" in issues[0]["message"]
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    assert "{{ phone }}" in out                        # биндинг не знесено


def test_placeholder_email_in_attr_is_not_a_contact():
    """placeholder="seuemail@…" — приклад у полі, не контакт: детект працює."""
    issues = _run(_files())          # у FORM лише :placeholder-байндинги
    assert len(issues) == 1, issues


def test_multichild_container_gets_card_appended_not_gridded():
    """Контейнер з кількома дітьми (заголовок + роздільник + форма) — ґрид
    розкидав би потік по комірках (кейс encanto). Картка стає останнім
    блоком, класи контейнера не чіпаються."""
    multi = ENCANTO.replace("info@enhupsemazozvo.lat", "SEM CONTATO") \
                   .replace('<div v-if="hasPhone"><span>TELEFONE</span>'
                            '<span>{{ phone }}</span></div>', "")
    files = {"src/components/ContactFormHome.vue": multi,
             "src/components/BottomSection.vue": FOOTER,
             "src/components/UserTermsTerms.vue": TERMS}
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    assert "lg:grid-cols-2" not in out, out          # ґрид не насаджено
    assert "max-w-2xl mx-auto" in out, out           # класи цілі
    assert 'class="bg-white mt-8' in out, out        # картка під формою
    assert 'href="tel:+55 85 98047-5613"' in out, out
    assert out.index("</form>") < out.index('class="bg-white mt-8'), out


def test_address_fallback_ignores_code_text_and_non_legal_files():
    """«via package.json: "generate": …» — не адреса (кейс encanto):
    lowercase «via», код-пунктуація і не-legal файл ріжуться усі три."""
    files = {"src/components/ContactFormHome.vue": FORM,
             "src/components/BottomSection.vue": FOOTER,
             "src/components/DeployNotes.vue":
                 '<template><p>via package.json: "generate": "vite build && '
                 'node scripts/inject-php.cjs"</p>'
                 "<p>Via Roma, 10, Milano</p></template>"}
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    assert "package.json" not in out, out
    assert "Via Roma" not in out, "адреса не з legal-файла"
    files["src/components/PrivacyPolicy.vue"] = \
        "<template><p>Via Roma, 10, Milano</p></template>"
    out2 = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    assert "Via Roma, 10, Milano" in out2, out2



# ------------------------------------------------- картка space-y-5 (02.10)
_ROW = ('\n        <div class="flex items-start gap-3">\n'
        '          <svg class="w-5 h-5 text-orange-700"></svg>\n'
        '          <div>\n'
        '            <p class="font-sans font-bold text-sm text-gray-900">{label}</p>\n'
        '            {inner}\n'
        '          </div>\n'
        '        </div>')


def _card_form(rows: str) -> str:
    return FORM.replace(
        "</section>",
        '<div class="bg-white mt-8 rounded-md p-8">\n'
        '        <h3 class="font-sans font-bold text-xl">Arike Jabgag</h3>\n'
        '        <div class="space-y-5">' + rows + "\n        </div>\n"
        "      </div>\n    </section>")


_FULL_ROWS = (
    "{tel}{mail}"
    + "{addr}"
    + "{cnpj}").format(
        tel=_ROW.format(label="Telefone",
                        inner='<a href="tel:+5585980475613">+55 85 98047-5613</a>'),
        mail=_ROW.format(label="E-mail",
                         inner='<a href="mailto:x@y.z">x@y.z</a>'),
        addr=_ROW.format(label="Endereço",
                         inner="<p>Rua das Orquídeas, Fortaleza, Brasil</p>"),
        cnpj=_ROW.format(label="CNPJ", inner="<p>CNPJ 54.399.238/0004-03</p>"))


def test_foreign_operator_card_needs_no_cnpj():
    """TECH-29349 (arikejabgag, 28.10): баєр замінив бразильську юрособу на
    норвезьку — у картці «Org.nr. 970 108 440». Як і чек cnpj, картка не
    вимагає CNPJ з пулу (інакше фікс повернув би бразильський номер)."""
    rows = _FULL_ROWS.replace("<p>CNPJ 54.399.238/0004-03</p>",
                              "<p>KAJ E. HALBJØRHUS (Noruega) · Org.nr. 970 108 440</p>").replace(">CNPJ<", ">Empresa responsável<")
    files = {"src/components/ContactFormHome.vue": _card_form(rows),
             "src/components/BottomSection.vue": FOOTER.replace("info@arikejabgag.world", "info@arikejabgag.digital")}
    assert mod._branch_data(dict(files), BRANCH)["regno"] == ""
    assert _run(files) == []
    assert _fix(files) == {}


def test_orphan_rows_under_form_are_removed():
    """Кейс cagunoktu 02.10: слід старого form-end фолбека — контактні
    row-блоки під кнопкою дублюють картку. Детект каже «продубльовані»,
    фікс знімає сироти, картку не чіпає. Фічі-список без контактів живе."""
    feature = ('\n        <div class="flex items-start gap-3">\n'
               "          <svg></svg>\n          <div>\n"
               '            <p class="font-sans font-bold text-sm text-gray-900">Wi-Fi</p>\n'
               "            <p>Internet rápida</p>\n"
               "          </div>\n        </div>")
    orphan = _ROW.format(label="CNPJ", inner="<p>CNPJ 54.399.238/0004-03</p>")
    base = _card_form(_FULL_ROWS).replace("Arike Jabgag</h3>",
                                          "Arike Jabgag</h3>" + feature)
    broken = base.replace("</form>", "</form>" + orphan)
    files = {"src/components/ContactFormHome.vue": broken,
             "src/components/BottomSection.vue": FOOTER,
             "src/components/PrivacyPolicy.vue": TERMS}
    issues = _run(files)
    assert len(issues) == 1 and "продубльовані" in issues[0]["message"], issues
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    assert out.count("CNPJ 54.399.238") == 1, "сирота лишилась"
    assert "Wi-Fi" in out, "фічі-список знесено"
    healed = {**files, "src/components/ContactFormHome.vue": out}
    assert _run(healed) == []


def test_form_space_y5_is_not_the_card():
    """space-y-5 носять і обгортки полів форми — скоп повноти НЕ форма:
    інакше рядки лягали б під кнопку (кейс cagunoktu)."""
    rows = _ROW.format(label="E-mail", inner='<a href="mailto:x@y.z">x@y.z</a>')
    base = _card_form(rows).replace('<form class="space-y-5">',
                                    '<form><div class="space-y-5">') \
                           .replace("</form>", "</div></form>")
    files = {"src/components/ContactFormHome.vue": base,
             "src/components/BottomSection.vue": FOOTER,
             "src/components/PrivacyPolicy.vue": TERMS}
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    form_part = out.split("</form>")[0]
    assert "items-start gap-3" not in form_part.split('<div class="space-y-5">')[1], \
        "рядки впали у форму"
    healed = {**files, "src/components/ContactFormHome.vue": out}
    assert _run(healed) == []


def test_site_name_is_added_inside_card():
    """02.10: картці без назви сайту фікс ставить h3 першим елементом;
    коли назва вже є — не дублює. Перебудова h3 зберігає."""
    base = _card_form(_FULL_ROWS).replace(
        '        <h3 class="font-sans font-bold text-xl">Arike Jabgag</h3>\n', "")
    files = {"src/components/ContactFormHome.vue": base,
             "src/components/BottomSection.vue": FOOTER,
             "src/components/PrivacyPolicy.vue": TERMS,
             "index.html": "<title>Arike Jabgag</title>"}
    issues = _run(files)
    assert issues and "бракує: назва" in issues[0]["message"], issues
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    sp = mod._card_span(out)
    inner = out[sp[0]:sp[1]]
    assert inner.index("<h3") < inner.index("items-start gap-3"), inner[:300]
    assert "Arike Jabgag</h3>" in inner, inner[:300]
    healed = {**files, "src/components/ContactFormHome.vue": out}
    assert _run(healed) == []
    assert out.count("Arike Jabgag</h3>") == 1



def test_frameless_rows_on_dark_panel_are_rebuilt():
    """Кейс inpigkavlipotu 02.10: row-блоки без space-y-5 (злипаються), з
    чужими інлайн-style і акцентними іконками на темній панелі. Фікс зносить
    групи, будує картку з білою палітрою і назвою; зовнішній mailto-лінк —
    уже пошта, mail-рядок не дублюється."""
    rows = (_ROW.format(label="Telefone",
                        inner='<a href="tel:+5585980475613" '
                              'style="color:#aba4ff !important">+55 85 '
                              "98047-5613</a>")
            + _ROW.format(label="Endereço",
                          inner="<p>Rua das Orquídeas, Fortaleza, Brasil</p>"))
    panel = ('<template>\n  <section id="form">\n'
             '    <div class="bg-indigo-700 px-8 py-16">\n'
             '      <a href="mailto:x@y.z" class="underline">x@y.z</a>\n'
             "      " + rows + "\n    </div>\n"
             '    <form class="space-y-5"><input></form>\n'
             "  </section>\n</template>")
    files = {"src/components/ContactFormHome.vue": panel,
             "src/components/BottomSection.vue": FOOTER,
             "src/components/PrivacyPolicy.vue": TERMS,
             "index.html": "<title>Arike Jabgag</title>"}
    issues = _run(files)
    assert len(issues) == 1 and "без каркаса" in issues[0]["message"], issues
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    assert "!important" not in out, "чужі інлайн-стилі лишились"
    assert '<div class="space-y-5 mt-8">' in out, out
    assert out.count("items-start gap-3") >= 2
    assert "text-white" in out.split("space-y-5 mt-8")[1], "палітра не біла"
    assert "Arike Jabgag</h3>" in out, "назви нема"
    assert out.count("mailto:") == 1, "пошта здубльована mail-рядком"
    healed = {**files, "src/components/ContactFormHome.vue": out}
    assert _run(healed) == [], _run(healed)
    assert _fix(healed) == {}



def test_white_card_on_light_panel_is_repainted():
    """Кейс gechaoh-inwodqol 02.10: hover:bg-emerald-600 кнопки зробив
    «темну» панель — картка лягла text-white на білому, невидима. Префікс
    hover: не тло; детект «палітра не під тло», фікс перефарбовує."""
    white_rows = (_ROW.format(label="Teléfono",
                              inner='<a href="tel:+5585980475613">x</a>')
                  .replace("text-gray-900", "text-white opacity-75")
                  .replace("text-orange-700", "white"))
    panel = ('<template>\n  <section id="form">\n'
             '    <div class="bg-white p-8">\n'
             '      <form class="space-y-6"><button class="bg-emerald-500 '
             'hover:bg-emerald-600">Enviar</button></form>\n'
             '      <div class="space-y-5 mt-8">\n'
             '          <h3 class="font-sans font-bold text-xl text-white">Arike Jabgag</h3>'
             + white_rows + "\n      </div>\n    </div>\n"
             "  </section>\n</template>")
    files = {"src/components/ContactFormHome.vue": panel,
             "src/components/BottomSection.vue": FOOTER,
             "src/components/PrivacyPolicy.vue": TERMS,
             "index.html": "<title>Arike Jabgag</title>"}
    issues = _run(files)
    assert len(issues) == 1 and "палітра" in issues[0]["message"], issues
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    sp = mod._card_span(out)
    inner = out[sp[0]:sp[1]]
    assert "text-white opacity-75" not in inner, "лейбли досі білі"
    assert "text-sm text-gray-900" in inner, "темних лейблів нема"
    assert "Arike Jabgag</h3>" in inner and "text-gray-900" in \
        inner.split("</h3>")[0], "h3 не перефарбовано"
    healed = {**files, "src/components/ContactFormHome.vue": out}
    assert _run(healed) == [], _run(healed)



def test_cnpj_digits_do_not_count_as_phone():
    """Кейс padohvae 02.10: «54.399.238» зійшло за телефон — повнота
    судиться по картці, CNPJ-цифри з телефонного матчу вирізаються."""
    rows = (_ROW.format(label="E-mail", inner='<a href="mailto:x@y.z">x@y.z</a>')
            + _ROW.format(label="CNPJ", inner='<p>CNPJ 54.399.238/0004-03</p>')
            + _ROW.format(label="Endereço",
                          inner="<p>Rua das Orquídeas, Fortaleza, Brasil</p>"))
    files = {"src/components/ContactFormHome.vue": _card_form(rows),
             "src/components/BottomSection.vue": FOOTER,
             "src/components/PrivacyPolicy.vue": TERMS}
    issues = _run(files)
    assert len(issues) == 1 and "бракує: телефон" in issues[0]["message"], issues
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    assert 'href="tel:+5585980475613"' in out, out
    # вставлено сиблінгом: вміст картки далі зводиться до цілих row-блоків
    assert not mod._card_broken(out), out
    healed = {**files, "src/components/ContactFormHome.vue": out}
    assert _run(healed) == []


def test_broken_card_is_rebuilt_whole():
    """Слід кривої вставки (сирітські close, рядок поза row) — детект каже
    «структурно бита», фікс перебудовує картку з даних вітки, після — тихо."""
    rows = (_ROW.format(label="E-mail", inner='<a href="mailto:x@y.z">x@y.z</a>')
            .removesuffix("\n          </div>\n        </div>")
            + _ROW.format(label="CNPJ", inner="<p>CNPJ 54.399.238/0004-03</p>")
            + "\n          </div>\n        </div>")
    files = {"src/components/ContactFormHome.vue": _card_form(rows),
             "src/components/BottomSection.vue": FOOTER,
             "src/components/PrivacyPolicy.vue": TERMS}
    issues = _run(files)
    assert len(issues) == 1 and "структурно бита" in issues[0]["message"], issues
    out = _fix(files)["src/components/ContactFormHome.vue"]["content"]
    assert not mod._card_broken(out), out
    for needle in ('href="tel:', 'href="mailto:x@y.z"', "CNPJ 54.399.238"):
        assert needle in out, (needle, out)
    healed = {**files, "src/components/ContactFormHome.vue": out}
    assert _run(healed) == []
    assert _fix(healed) == {}


# ------------------------------- чужий блок + hr-адреса без вуличного слова (21.10)
# кейс nwf-travb-stgicanhu-hr-hr: ліва колонка — пошта текстом, телефон
# байндингом, рядки «іконка в квадраті + h3 + p»; адреса лише в terms
# («Kapucinska 12, Osijek, …» — без Ulica/Trg), у privacy — у трьох <p>
TROST_FORM = """<template>
  <section class="bg-slate-50 py-16 px-4" id="form">
    <div class="max-w-6xl mx-auto">
      <div class="grid md:grid-cols-2 gap-12">
        <div>
          <h2 class="font-sans font-bold text-3xl text-gray-900 mb-4">Razgovarajmo</h2>
          <div class="space-y-6">
            <div class="flex items-start space-x-4">
              <div class="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-width="2" d="M3 8l7.89 5.26"></path>
                </svg>
              </div>
              <div>
                <h3 class="font-sans text-gray-900 font-bold">Email</h3>
                <p class="font-sans text-gray-500 text-sm">info@travbstgicanhu.world</p>
              </div>
            </div>
            <div v-if="hasPhone" class="flex items-start space-x-4">
              <div class="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-width="2" d="M3 5a2 2 0 012-2h3.28"></path>
                </svg>
              </div>
              <div>
                <h3 class="font-sans text-gray-900 font-bold">Telefon</h3>
                <p class="font-sans text-gray-500 text-sm">{{ phone }}</p>
              </div>
            </div>
          </div>
        </div>
        <div class="bg-white rounded-lg p-8">
          <form class="space-y-5">
            <input type="email" name="email" placeholder="your@travbstgicanhu.world">
            <button type="submit" class="w-full bg-blue-600 text-white">Pošalji</button>
          </form>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
const phone = '+385 23 716-3482'
const hasPhone = phone && !phone.startsWith('@@')
</script>
"""
TROST = {
    "src/components/ReachFormHome.vue": TROST_FORM,
    "src/components/PrivacyContentPrivacy.vue":
        "<template><div>\n<p>Osijek</p>\n<p>Kapucinska 12</p>\n"
        "<p>Osječko-baranjska županija 31000, Hrvatska</p>\n</div></template>",
    "src/components/UserTermsTerms.vue":
        "<template><article>\n<p>Trost Stratešni d.o.o.</p>\n"
        "<p>Kapucinska 12, Osijek, Osječko-baranjska županija 31000, Hrvatska</p>\n"
        "</article></template>",
    "src/components/BottomSection.vue":
        '<template><footer><a href="tel:+385237163482">+385 23 716-3482</a>'
        "<p>© Trost Stratešni d.o.o.</p></footer></template>",
    "index.html": "<title>Trost Stratešni</title>",
}
TB = "nwf-travb-stgicanhu-hr-hr"
TROST_ADDR = "Kapucinska 12, Osijek, Osječko-baranjska županija 31000, Hrvatska"


def test_foreign_block_gets_address_and_name_in_its_own_style():
    """Кейс trost 21.10: вітка «не мала адреси» (немає вуличного слова, гео-
    бази hr-hr нема) — чек мовчав, фікс 0 дій. Тепер адреса з terms
    (найповніша з двох форм), блок неповний на адресу й назву; адреса —
    клоном рядка списку (коробка іконки, h3-підпис мовою вітки, p-значення),
    без v-if рядка телефону; назва — h3 над рядками; наша картка під
    кнопкою не з'являється; повторний прогін тихий."""
    files = dict(TROST)
    assert mod._branch_data(dict(files), TB)["addr"] == TROST_ADDR
    issues = mod.run_branch(dict(files), list(files), TB)
    assert len(issues) == 1 and "бракує: адреса, назва;" in issues[0]["message"], issues
    out = _fix(files, TB)["src/components/ReachFormHome.vue"]["content"]
    clone = out[out.index("{{ phone }}"):out.index("<form")]
    assert '<h3 class="font-sans text-gray-900 font-bold">Adresa</h3>' in clone, clone
    assert f'<p class="font-sans text-gray-500 text-sm">{TROST_ADDR}</p>' in clone, clone
    assert clone.count('class="w-10 h-10 bg-blue-600') == 1, clone
    assert "v-if" not in clone, clone
    head = out[out.index('<div class="space-y-6">'):out.index("Email</h3>")]
    assert ">Trost Stratešni</h3>" in head, head
    assert "items-start gap-3" not in out and "space-y-5 mt-8" not in out, out
    healed = {**files, "src/components/ReachFormHome.vue": out}
    assert mod.run_branch(dict(healed), list(healed), TB) == []
    assert mod.fix_branch(dict(healed), list(healed), TB) == []


def test_handwritten_hr_address_counts_as_present():
    """praveiv-pemdeazx, brvoge, mipavow 21.10: у terms адреса з «Ulica …»
    (її вітка знаходила), а в блок адресу вписали руками в іншій формі.
    Без вуличного слова з великої чек її не бачив — «бракує адреси», і
    фікс доклеював другу."""
    terms = ("<template><p>Ulica Matice hrvatske 8, Zaprešić, Zagrebačka "
             "županija 10290, Hrvatska</p></template>")
    for shown in ("Biljska cesta 37, 31000, Osijek, Hrvatska",
                  "Hercegovačka ul. 19, 31220, Višnjevac, Hrvatska",
                  "Šušnjevac 1 51218 Čavle, Hrvatska"):
        form = TROST_FORM.replace(">Razgovarajmo<", ">Trost Stratešni<").replace(
            "{{ phone }}</p>", "{{ phone }}</p>\n<p>" + shown + "</p>")
        files = {**TROST, "src/components/ReachFormHome.vue": form,
                 "src/components/UserTermsTerms.vue": terms}
        assert mod._branch_data(dict(files), TB)["addr"].startswith("Ulica Matice hrvatske 8")
        assert mod.run_branch(dict(files), list(files), TB) == [], shown
        assert mod.fix_branch(dict(files), list(files), TB) == [], shown


def test_foreign_rows_in_space_y5_card_are_cloned_not_replaced():
    """zebec 21.10: space-y-5 з контактами — «картка», але рядки не нашого
    почерку (<div><span>підпис</span><a>значення</a></div>). Адреса — клоном
    цього рядка (span-підпис, класи значення), а не нашим flex/svg-рядком."""
    form = """<template>
  <section id="form">
    <div class="bg-indigo-50 p-8">
      <div class="space-y-5 mt-10 pt-8 border-t">
        <h3 class="font-sans font-bold text-xl text-gray-900">Trost Stratešni</h3>
        <div v-if="hasPhone">
          <span class="block text-xs uppercase text-slate-900 mb-1">Pozovi nas</span>
          <a :href="'tel:' + phone" class="font-semibold text-slate-900">{{ phone }}</a>
        </div>
        <div v-if="hasEmail">
          <span class="block text-xs uppercase text-slate-900 mb-1">Pošalji email</span>
          <a :href="'mailto:' + email" class="font-semibold text-slate-900 break-all">{{ email }}</a>
        </div>
      </div>
    </div>
    <form><button type="submit" class="bg-indigo-600">Pošalji</button></form>
  </section>
</template>
"""
    files = {**TROST, "src/components/ReachFormHome.vue": form}
    issues = mod.run_branch(dict(files), list(files), TB)
    assert len(issues) == 1 and "бракує: адреса;" in issues[0]["message"], issues
    out = _fix(files, TB)["src/components/ReachFormHome.vue"]["content"]
    assert '<span class="block text-xs uppercase text-slate-900 mb-1">Adresa</span>' in out, out
    assert f'<p class="font-semibold text-slate-900">{TROST_ADDR}</p>' in out, out
    assert out.index("{{ email }}") < out.index(TROST_ADDR), out
    assert "items-start gap-3" not in out, out
    healed = {**files, "src/components/ReachFormHome.vue": out}
    assert mod.run_branch(dict(healed), list(healed), TB) == []


def test_hr_address_extraction_skips_prose_labels_and_page_meta():
    """hr-партія 21.10: адреса з прози terms — без речення навколо
    (momentum-ai), підпис «Adresa:» — не частина адреси; «Od 2015 · …»,
    «GDPR član 6, točka 1», «Klauzula 5 · 05» — не адреси."""
    for text, want in (
            ("Naša glavna kancelarija smještena je na adresi Ulica Ivana Zajca 15, "
             "51000 Rijeka, gdje vas čekaju stručni timovi za neposrednu podršku.",
             "Ulica Ivana Zajca 15, 51000 Rijeka"),
            ("Adresa: Obala Lazareta 12, Split 21000, Hrvatska",
             "Obala Lazareta 12, Split 21000, Hrvatska")):
        files = {"src/components/ContactFormHome.vue": FORM,
                 "src/components/UserTermsTerms.vue": f"<template><p>{text}</p></template>"}
        assert mod._branch_data(dict(files), "nwf-x-hr-hr")["addr"] == want, text
    files = {"src/components/ContactFormHome.vue": FORM,
             "src/components/UserTermsTerms.vue":
                 "<template><p>Od 2015 · Zadnja izmjena 2024</p>\n<p>GDPR član 6, točka 1</p>"
                 "\n<p>Klauzula 5 · 05</p></template>"}
    # сміття адресою не стає: вітка без адреси падає на гео-базу hr-hr
    import checks.address_number as _an
    assert mod._branch_data(dict(files), "nwf-x-hr-hr")["addr"] == _an._geo_pick("nwf-x-hr-hr")


# ------------------------------------- hr-hr партія 26.10 (sakgucnez, stit, tvgstadi…)
# Картки вже стояли (автофікс 26.10), але: у sakgucnez адреса без номера
# будинку з хвостом-датою сторінки, у решти адреси не було взагалі — гео-бази
# hr-hr не існувало, і чек мовчав («бракує» судилось лише з даних, що є).
HRB = "nwf-stefziv-sakgucnez-hr-hr"
_HR_ROWS = (
    _ROW.format(label="Telefon", inner='<a href="tel:+38522614289">+385 22 614 289</a>')
    + _ROW.replace('<svg class="w-5 h-5 text-orange-700"></svg>',
                   '<svg class="w-5 h-5 text-orange-700"><path d="{pin}"/></svg>'.format(pin=mod._ICONS["pin"]))
    .format(label="Adresa", inner="<p>Ulica Petra Krešimira IV, Posljednje ažurirano 2023</p>")
    + _ROW.format(label="E-mail", inner='<a href="mailto:info@sakgucnez.pro">info@sakgucnez.pro</a>'))
HR_TERMS = "<template><p>Ulica Petra Krešimira IV, Šibenik, 22000, Hrvatska</p></template>"


def test_card_address_without_house_number_is_rewritten():
    files = {"src/components/ContactFormHome.vue": _card_form(_HR_ROWS),
             "src/components/TermsOfServiceTerms.vue": HR_TERMS,
             "index.html": "<title>Arike Jabgag</title>"}
    issues = mod.run_branch(dict(files), list(files), HRB)
    assert len(issues) == 1 and "без номера будинку" in issues[0]["message"], issues
    import checks.address_number as _an
    n = _an._number_for(HRB, "Ulica Petra Krešimira IV")
    out = _fix(files, HRB)["src/components/ContactFormHome.vue"]["content"]
    assert f"Ulica Petra Krešimira IV {n}, Šibenik, 22000, Hrvatska" in out, out
    assert "Posljednje ažurirano" not in out, out
    for needle in ('href="tel:+38522614289"', 'href="mailto:info@sakgucnez.pro"', "Arike Jabgag</h3>"):
        assert needle in out, (needle, out)
    healed = {**files, "src/components/ContactFormHome.vue": out}
    assert mod.run_branch(dict(healed), list(healed), HRB) == []
    assert _fix(healed, HRB) == {}


def test_card_rewrite_takes_terms_already_numbered_in_the_same_run():
    """Автофікс ганяє address_number раніше: terms уже з номером, а картка
    ще з «Ulica Petra Krešimira IV, Posljednje ažurirano 2023». Ключ вулиці
    без номера — інакше «…IV 846» і «…IV» ставали різними вулицями, і
    картка брала власне сміття за адресу вітки."""
    import checks.address_number as _an
    n = _an._number_for(HRB, "Ulica Petra Krešimira IV")
    files = {"src/components/ContactFormHome.vue": _card_form(_HR_ROWS),
             "src/components/TermsOfServiceTerms.vue": HR_TERMS.replace("IV,", f"IV {n},"),
             "src/components/DataPolicyPrivacy.vue": "<template><p>Ulica Petra Krešimira IV</p>\n<p>Posljednje ažurirano 2023</p></template>",
             "index.html": "<title>Arike Jabgag</title>"}
    out = _fix(files, HRB)["src/components/ContactFormHome.vue"]["content"]
    assert f">Ulica Petra Krešimira IV {n}, Šibenik, 22000, Hrvatska</p>" in out, out
    assert "Posljednje" not in out, out


def test_hr_card_without_any_address_gets_one_from_hr_geo_base():
    rows = (_ROW.format(label="Telefon", inner='<a href="tel:+385479156382">+385 47 915 6382</a>')
            + _ROW.format(label="E-mail", inner='<a href="mailto:info@tvtulu.pro">info@tvtulu.pro</a>'))
    files = {"src/components/InquiryFormHome.vue": _card_form(rows),
             "index.html": "<title>Arike Jabgag</title>"}
    issues = mod.run_branch(dict(files), list(files), "nwf-tvgstadi-hr-hr")
    assert len(issues) == 1 and "бракує: адреса" in issues[0]["message"], issues
    import checks.address_number as _an
    geo = _an._geo_pick("nwf-tvgstadi-hr-hr")
    assert geo, "гео-база hr-hr порожня"
    out = _fix(files, "nwf-tvgstadi-hr-hr")["src/components/InquiryFormHome.vue"]["content"]
    assert f">{geo}</p>" in out, out
    healed = {**files, "src/components/InquiryFormHome.vue": out}
    assert mod.run_branch(dict(healed), list(healed), "nwf-tvgstadi-hr-hr") == []


def test_row_appended_to_card_on_dark_panel_keeps_white_palette():
    """surjoke-badga 26.10: картка на bg-orange-600 з білими рядками; рядок
    адреси дописувався темними лейблами — наступний прогін бачив «палітра не
    під тло» і перебудовував картку вдруге."""
    white = ('\n        <div class="flex items-start gap-3">\n'
             '          <svg class="w-5 h-5 text-white flex-shrink-0 mt-1"></svg>\n'
             '          <div>\n'
             '            <p class="font-sans font-bold text-sm text-white opacity-75">Telefon</p>\n'
             '            <a href="tel:+385524237896" class="font-sans text-white text-sm">+385 52 423 7896</a>\n'
             '          </div>\n'
             '        </div>')
    panel = ('<template>\n  <section class="py-16">\n'
             '    <div class="md:w-2/5 bg-orange-600 px-8 py-16">\n'
             '      <form><input name="email"><button type="submit" class="bg-white">Pošalji</button></form>\n'
             '      <a href="mailto:info@surjokebadga.pro" class="text-white">info@surjokebadga.pro</a>\n'
             '      <div class="space-y-5 mt-8">\n'
             '          <h3 class="font-sans font-bold text-xl text-white">Arike Jabgag</h3>'
             + white + "\n        </div>\n    </div>\n  </section>\n</template>")
    files = {"src/components/ReachFormHome.vue": panel, "index.html": "<title>Arike Jabgag</title>"}
    br = "nwf-surjoke-badga-hr-hr"
    out = _fix(files, br)["src/components/ReachFormHome.vue"]["content"]
    import checks.address_number as _an
    assert _an._geo_pick(br) in out, out
    assert "text-sm text-gray-900" not in out, out
    healed = {**files, "src/components/ReachFormHome.vue": out}
    assert mod.run_branch(dict(healed), list(healed), br) == []


def test_hr_site_address_beats_the_geo_base():
    """Гео-база hr-hr не має перебивати справжню адресу вітки, навіть
    безслівну («Putine 18, 10090 Zagreb» у footer)."""
    files = {"src/components/ContactFormHome.vue": FORM,
             "src/components/Footer.vue": "<template><footer><p>Putine 18, 10090 Zagreb, Hrvatska</p></footer></template>"}
    assert mod._branch_data(dict(files), "nwf-kriz-hr-hr")["addr"] == "Putine 18, 10090 Zagreb, Hrvatska"



def test_manual_only_contract():
    assert mod.GROUP == "review", mod.GROUP           # ніколи не в автокоміт
    assert mod.PROJECTS == ["node"], mod.PROJECTS
    assert callable(mod.fix_branch)


if __name__ == "__main__":
    run(dict(globals()))
