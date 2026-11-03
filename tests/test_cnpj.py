"""CNPJ на br-pt вайтах: пул номерів + чек/автофікс.

Контракти: валідні контрольні цифри на вході в пул; чек діє лише на
-br-pt; фікс клонує <p> футера зі стилями і додає «CNPJ …» з пулу
детерміновано за віткою; порожній пул — error без фікса.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run, load_check                    # noqa: E402

sys.path.insert(0, str(ROOT))

import projects                                               # noqa: E402
import cnpj_pool                                              # noqa: E402

mod = load_check("cnpj")

# реальні за структурою, валідні за контрольними цифрами номери
VALID1 = "11.222.333/0001-81"
VALID2 = "45.723.174/0001-10"

PAGE = """<html><body>
<footer class="bg-zinc-900 py-10">
  <div class="wrap">
    <p class="font-sans text-sm text-gray-400">Remalo Luhiime</p>
    <p class="font-sans text-xs text-gray-500">info@remalo.lat</p>
  </div>
</footer>
</body></html>
"""


def _fresh_pool(seed=False):
    d = Path(tempfile.mkdtemp(prefix="cnpj-"))
    projects.state_root = lambda: d
    if not seed:                                   # тести пулу — без сіда
        cnpj_pool.SEED = d / "no-seed.json"
    else:
        cnpj_pool.SEED = Path(cnpj_pool.__file__).resolve().parent / "cnpj_seed.json"
    return d


def test_seed_fills_empty_state_once():
    _fresh_pool(seed=True)
    rows = cnpj_pool.load()
    assert len(rows) >= 50, "сід з cnpj.biz має заповнити порожній стан"
    assert all(cnpj_pool.valid(r["cnpj"]) for r in rows)
    assert {"Медицина", "IT", "Фармація"} <= {r["sphere"] for r in rows}
    # стан тепер живе своїм життям: видалення не воскресає з сіда
    first = rows[0]["cnpj"]
    assert cnpj_pool.remove(first)
    assert first not in [r["cnpj"] for r in cnpj_pool.load()]


def test_add_keeps_extended_fields():
    _fresh_pool()
    row = cnpj_pool.add("11222333000181", note="n", company="Clinica X LTDA",
                        city="São Paulo/SP", sphere="Медицина", addr="Rua 1")
    assert (row["company"], row["city"], row["sphere"], row["addr"]) == \
        ("Clinica X LTDA", "São Paulo/SP", "Медицина", "Rua 1")


def test_seed_merges_new_numbers_into_existing_state():
    # нова партія сіда доливається у НЕпорожній стан (прод дістає деплоєм),
    # але видалене руками не воскресає (реєстр cnpj_removed.json)
    d = _fresh_pool()
    cnpj_pool.add(VALID1, note="ручний")
    assert [r["cnpj"] for r in cnpj_pool.load()] == [VALID1]
    seed = d / "seed.json"
    seed.write_text(
        '[{"cnpj": "%s", "sphere": "IT", "company": "Nova"}]' % VALID2,
        encoding="utf-8")
    cnpj_pool.SEED = seed
    rows = [r["cnpj"] for r in cnpj_pool.load()]
    assert rows == [VALID1, VALID2], rows            # долито, ручний цілий
    assert cnpj_pool.remove(VALID2)
    rows = [r["cnpj"] for r in cnpj_pool.load()]
    assert VALID2 not in rows, "видалений сід-номер не має воскресати"


def test_new_parser_sectors_are_matched():
    assert cnpj_pool.sphere_for("villas de luxo com piscina, hospedagem") \
        == "Готелі/туризм"
    assert cnpj_pool.sphere_for("locação de veículos e carros") == "Авто"
    assert cnpj_pool.sphere_for("energia solar fotovoltaica") == "Енергетика"
    assert cnpj_pool.sphere_for("advocacia e direito empresarial") \
        == "Юристи/бухгалтерія"
    # стара сфера сіда «Нерухомість/SPE» матчиться базою до «/»
    _fresh_pool()
    cnpj_pool.add(VALID1, sphere="Нерухомість/SPE")
    cnpj_pool.add(VALID2, sphere="Промисловість")
    assert cnpj_pool.pick("nwf-a-br-pt", "imobiliária e imóveis") == VALID1


def test_sphere_narrows_only_while_it_has_unused_numbers():
    _fresh_pool()
    cnpj_pool.add(VALID1, company="Clinica Vida", sphere="Медицина")
    cnpj_pool.add(VALID2, company="Metal Forte", sphere="Промисловість")
    med = "Clínica de saúde e estética — agende sua consulta"
    first = cnpj_pool.pick("nwf-a-br-pt", med)
    assert first == VALID1                    # вільний номер сфери — її
    # сфера вичерпана: друга медична вітка НЕ повторює номер (кейс 01.10:
    # villas-вітки всі отримали той самий Super Porto SPE)
    second = cnpj_pool.pick("nwf-b-br-pt", med)
    assert second == VALID2, second
    assert cnpj_pool.sphere_for("desenvolvimento de software") == "IT"
    assert cnpj_pool.sphere_for("qwerty") == ""


def test_assignment_is_sticky_and_survives_reruns():
    _fresh_pool()
    cnpj_pool.add(VALID1)
    cnpj_pool.add(VALID2)
    a = cnpj_pool.pick("nwf-a-br-pt")
    for _ in range(3):
        assert cnpj_pool.pick("nwf-a-br-pt", "clínica") == a
    assert cnpj_pool.assignments()["nwf-a-br-pt"] == a


def test_removed_number_frees_its_branches():
    _fresh_pool()
    cnpj_pool.add(VALID1)
    cnpj_pool.add(VALID2)
    a = cnpj_pool.pick("nwf-a-br-pt")
    other = VALID2 if a == VALID1 else VALID1
    assert cnpj_pool.remove(a)
    assert "nwf-a-br-pt" not in cnpj_pool.assignments()
    assert cnpj_pool.pick("nwf-a-br-pt") == other


# ------------------------------------------------------------------- пул

def test_pool_validates_check_digits_and_format():
    _fresh_pool()
    assert cnpj_pool.valid(VALID1) and cnpj_pool.valid(VALID2)
    assert not cnpj_pool.valid("11.222.333/0001-80")      # зіпсована контрольна
    assert not cnpj_pool.valid("11.111.111/1111-11")      # всі цифри однакові
    assert cnpj_pool.canonical("11222333000181") == VALID1
    try:
        cnpj_pool.add("12345")
        assert False, "короткий номер мав відбитись"
    except ValueError as e:
        assert "14 цифр" in str(e)
    try:
        cnpj_pool.add("11.222.333/0001-80")
        assert False, "невалідні контрольні мали відбитись"
    except ValueError as e:
        assert "контрольні" in str(e)


def test_pool_add_remove_and_duplicates():
    _fresh_pool()
    cnpj_pool.add("11222333000181", note="юристи")
    try:
        cnpj_pool.add(VALID1)
        assert False, "дубль мав відбитись"
    except ValueError as e:
        assert "уже в пулі" in str(e)
    assert [r["cnpj"] for r in cnpj_pool.load()] == [VALID1]
    assert cnpj_pool.remove(VALID1) and cnpj_pool.load() == []
    assert not cnpj_pool.remove(VALID1)


def test_pick_spreads_unique_numbers_across_branches():
    _fresh_pool()
    cnpj_pool.add(VALID1)
    cnpj_pool.add(VALID2)
    a = cnpj_pool.pick("nwf-remalo-luhiime-br-pt")
    assert a == cnpj_pool.pick("nwf-remalo-luhiime-br-pt")
    [cnpj_pool.pick(f"nwf-x{i}-br-pt") for i in range(5)]
    counts = [list(cnpj_pool.assignments().values()).count(v)
              for v in (VALID1, VALID2)]
    # 6 віток на 2 номери: використання рівне, «всім одне» неможливе
    assert counts == [3, 3], counts


def test_fake_cnpj_is_replaced_in_place():
    # кейс paraiso/residencia 01.10: плейсхолдер генератора
    # 12.345.678/0001-90 закомічений у вітках — контрольні не сходяться
    _fresh_pool()
    cnpj_pool.add(VALID1)
    files = {"privacy.html": ('<footer><p class="text-xs uppercase">CNPJ '
                              '12.345.678/0001-90</p></footer>'),
             "index.html": PAGE}
    issues = mod.run_branch(dict(files), list(files), "nwf-a-br-pt")
    assert len(issues) == 1 and "фейковий CNPJ" in issues[0]["message"]
    assert "12.345.678/0001-90" in issues[0]["message"]
    acts = {a["path"]: a for a in mod.fix_branch(dict(files), list(files),
                                                 "nwf-a-br-pt")}
    assert list(acts) == ["privacy.html"], acts
    new = acts["privacy.html"]["content"]
    # замінено НА МІСЦІ: той самий <p>, той самий підпис, новий номер
    assert f'<p class="text-xs uppercase">CNPJ {VALID1}</p>' in new, new
    fixed = {**files, "privacy.html": new}
    assert mod.run_branch(dict(fixed), list(fixed), "nwf-a-br-pt") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "nwf-a-br-pt") == []


# ------------------------------------------------------------------- чек

def test_only_br_pt_branches_are_judged():
    _fresh_pool()
    files = {"index.html": PAGE}
    assert mod.run_branch(dict(files), list(files), "nwf-cagu-vemme-mx-es") == []
    assert mod.fix_branch(dict(files), list(files), "nwf-cagu-vemme-mx-es") == []


def test_batch_numbered_br_pt_branch_is_judged():
    # choa-nono-br-pt-2 / bukjima-vija-br-pt-2 (28.10): «-2» — номер партії,
    # локаль та сама; доти чек мовчав про відсутній CNPJ
    _fresh_pool()
    cnpj_pool.add(VALID1)
    files = {"index.html": PAGE}
    issues = mod.run_branch(dict(files), list(files), "choa-nono-br-pt-2")
    assert len(issues) == 1 and VALID1 in issues[0]["message"], issues
    acts = mod.fix_branch(dict(files), list(files), "choa-nono-br-pt-2")
    assert len(acts) == 1 and f"CNPJ {VALID1}" in acts[0]["content"], acts


def test_present_cnpj_keeps_the_check_silent():
    _fresh_pool()
    files = {"terms.html": f"<footer><p>CNPJ {VALID1}</p></footer>"}
    assert mod.run_branch(dict(files), list(files), "nwf-a-br-pt") == []


def test_empty_pool_is_an_error_without_fix():
    _fresh_pool()
    files = {"index.html": PAGE}
    issues = mod.run_branch(dict(files), list(files), "nwf-a-br-pt")
    assert len(issues) == 1 and "пул номерів порожній" in issues[0]["message"]
    assert mod.fix_branch(dict(files), list(files), "nwf-a-br-pt") == []


def test_fix_clones_footer_p_with_styles():
    _fresh_pool()
    cnpj_pool.add(VALID1)
    files = {"index.html": PAGE}
    issues = mod.run_branch(dict(files), list(files), "nwf-a-br-pt")
    assert len(issues) == 1 and VALID1 in issues[0]["message"]
    acts = mod.fix_branch(dict(files), list(files), "nwf-a-br-pt")
    assert len(acts) == 1 and acts[0]["path"] == "index.html"
    new = acts[0]["content"]
    assert f'<p class="font-sans text-xs text-gray-500">CNPJ {VALID1}</p>' in new, new
    # ідемпотентність і тиша після фікса
    fixed = {"index.html": new}
    assert mod.fix_branch(dict(fixed), list(fixed), "nwf-a-br-pt") == []
    assert mod.run_branch(dict(fixed), list(fixed), "nwf-a-br-pt") == []


def test_fix_touches_every_page_with_footer():
    _fresh_pool()
    cnpj_pool.add(VALID1)
    files = {"index.html": PAGE, "about.html": PAGE,
             "src/components/Nav.vue": "<template><nav/></template>"}
    acts = mod.fix_branch(dict(files), list(files), "nwf-a-br-pt")
    assert {a["path"] for a in acts} == {"index.html", "about.html"}


# футер корпусу mds-*: <address>/<div>, жодного <p>. Та сама пастка, що
# в address_number: чек обіцяв дописати CNPJ, фікс давав 0 дій.
ADDRESS_FOOTER = (
    '<html><body><main><h1>Consultoria</h1></main>'
    '<footer class="seller"><div class="seller-in">'
    '<address><b>Quem vende</b><strong>Fulano</strong><br>'
    'Rua Curuca, 1111, Vila Maria, São Paulo SP, 02120-002</address>'
    '<address><b>Contatos</b>Telefone: '
    '<a href="tel:+5511999999999">+55 11 99999 9999</a></address>'
    '</div></footer></body></html>')


def test_footer_built_on_address_tags_still_gets_the_number():
    _fresh_pool()
    cnpj_pool.add(VALID1)
    files = {"index.html": ADDRESS_FOOTER}
    issues = mod.run_branch(dict(files), list(files), "nwf-a-br-pt")
    assert len(issues) == 1 and "немає CNPJ" in issues[0]["message"], issues
    acts = mod.fix_branch(dict(files), list(files), "nwf-a-br-pt")
    assert acts, "чек обіцяє дописати CNPJ, а fix_branch повернув 0 дій"
    fixed = {a["path"]: a["content"] for a in acts}
    assert VALID1 in fixed["index.html"], fixed["index.html"][-260:]
    assert mod.run_branch(dict(fixed), list(fixed), "nwf-a-br-pt") == []


def test_check_does_not_promise_what_fix_cannot_do():
    _fresh_pool()
    cnpj_pool.add(VALID1)
    # футер є, але класти нема куди: ні <p>, ні <address>
    page = ADDRESS_FOOTER.replace("address>", "div>")
    files = {"index.html": page}
    issues = mod.run_branch(dict(files), list(files), "nwf-a-br-pt")
    assert len(issues) == 1, issues
    acts = mod.fix_branch(dict(files), list(files), "nwf-a-br-pt")
    promised = "фікс допише" in issues[0]["message"]
    assert promised == bool(acts), f"обіцянка={promised}, дій={len(acts)}"
    if not promised:
        assert "руками" in issues[0]["message"], issues[0]["message"]


def test_footer_without_p_or_address_clones_the_copyright_div():
    """sokkoruuzosnacav 21.10 (Nova-тема): футер — лише
    <div class="footer-text">2025 © …</div>. Доти: «додай руками» на 30
    сторінках. Тепер рядок лягає клоном ©-елемента з його класами."""
    _fresh_pool()
    cnpj_pool.add(VALID1)
    page = ('<html><body><footer class="site-footer"><div class="nova-footer">'
            '<div class="row"><div class="nova-footer__copyright-text">\n'
            '<div class="footer-text">\n2025 © SOS Móveis Antigos. Todos direitos reservados.\t\t</div>\n'
            '</div></div></div></footer></body></html>')
    files = {"index.php": page, "sobre/index.html": page}
    issues = mod.run_branch(dict(files), list(files), "sokkoruuzosnacav-cop-br-pt")
    assert len(issues) == 1 and "фікс допише" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "sokkoruuzosnacav-cop-br-pt")}
    assert set(acts) == set(files)
    new = acts["index.php"]
    assert f'<div class="footer-text">CNPJ {VALID1}</div>' in new, new[-400:]
    assert new.index("direitos reservados") < new.index(f"CNPJ {VALID1}"), "рядок іде ПІСЛЯ ©"
    assert mod.run_branch(dict(acts), list(acts), "sokkoruuzosnacav-cop-br-pt") == []


def test_number_only_in_body_text_is_duplicated_into_every_footer():
    """casenadefekgubn / piivabmekwok 21.10: справжній CNPJ стоїть у тексті
    однієї сторінки, QA: «должен быть в подвале и/или в условиях
    использования». Фікс дублює САМЕ ЦЕЙ номер (не з пулу) у футер."""
    _fresh_pool()
    body = f'<html><body><main><p>Somos a Prates Ltda, CNPJ {VALID1}.</p></main><footer><p class="c">© 2026 Prates</p></footer></body></html>'
    other = '<html><body><main><p>Sobre nós</p></main><footer><p class="c">© 2026 Prates</p></footer></body></html>'
    files = {"restauracao-movel/index.html": body, "index.php": other}
    issues = mod.run_branch(dict(files), list(files), "x-br-pt")
    assert len(issues) == 1 and "лише в тексті" in issues[0]["message"] and VALID1 in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "x-br-pt")}
    assert set(acts) == set(files), acts.keys()
    assert all(f'<p class="c">CNPJ {VALID1}</p>' in c for c in acts.values())
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "x-br-pt") == []
    # номер у юридичній сторінці або у футері — вже «закріплений», тиша
    legal = {"index.php": other, "termos-de-uso.html": f"<html><body><p>CNPJ {VALID1}</p></body></html>"}
    assert mod.run_branch(dict(legal), list(legal), "x-br-pt") == []


def test_french_branch_office_with_rcs_needs_no_cnpj():
    """nwf-leqo-fihqos/confeboa/codho-preduko (br-pt, 20.10): на сайті RCS
    Paris 982 943 508 — французька філія; баєр просив ПРИБРАТИ CNPJ. Чек
    мовчить, фікс не повертає номер з пулу по колу."""
    _fresh_pool()
    cnpj_pool.add(VALID1)
    files = {"src/components/LegalRibbon.vue": "<template><p>RCS Paris 982 943 508 · Sede: Paris</p></template>",
             "index.html": '<html><body><footer><p class="c">© 2026</p></footer></body></html>'}
    assert mod.run_branch(dict(files), list(files), "nwf-confeboa-matkipome-br-pt") == []
    assert mod.fix_branch(dict(files), list(files), "nwf-confeboa-matkipome-br-pt") == []
    files["src/components/LegalRibbon.vue"] = "<template><p>SIREN 820 758 597</p></template>"
    assert mod.run_branch(dict(files), list(files), "x-br-pt") == []


def test_norwegian_operator_with_org_number_needs_no_cnpj():
    """TECH-29349 (arikejabgag/demeduu/lmpisnizatar, 28.10): баєр замінив
    бразильську юрособу на норвезьку — Organisasjonsnummer у Enhetsregisteret.
    CNPJ там зайвий, як і у французької філії: чек мовчить, фікс не повертає
    номер з пулу."""
    _fresh_pool()
    cnpj_pool.add(VALID1)
    footer = '<html><body><footer><p class="c">© 2026</p></footer></body></html>'
    for legal in ("Organisasjonsnummer: 970 408 436 (Enhetsregisteret, Noruega)",
                  "KAJ E. HALBJØRHUS · Org.nr. 970 108 440",
                  "Org.nr.: 829918242 · Foretaksregisteret"):
        files = {"src/components/PageFooter.vue": f"<template><p>{legal}</p></template>",
                 "index.html": footer}
        assert mod.run_branch(dict(files), list(files), "nwf-arike-jabgag-br-pt") == [], legal
        assert mod.fix_branch(dict(files), list(files), "nwf-arike-jabgag-br-pt") == [], legal
    # голе 9-значне число без назви реєстру — не реєстрація
    files = {"index.html": footer.replace("© 2026", "© 2026 · pedido 970 408 436")}
    assert mod.run_branch(dict(files), list(files), "x-br-pt"), "без реєстру чек не мовчить"


def test_number_in_home_footer_only_is_copied_into_every_other_footer():
    """ib-cytis 22.10: CNPJ у футері лише index.php (25 інших сторінок без
    нього, Política теж без) — QA: «стоит только на главной — а должен быть
    в подвале сайта и/или в условиях использования». Регламент BR: завжди в
    політиках І/АБО у футері; є деінде — копіювати у футер."""
    _fresh_pool()
    # як у ib-cytis: у підвалі решти сторінок немає ні <p>, ні <address>,
    # ні © — «дописати рядок» нікуди, тож копіюється сам блок головної
    brasilia = ('<div class="footer-contact-item"><div class="d-flex flex-column">'
                '<a class="link" href="https://goo.gl/maps/Rk">SHC/C EQ 114/115 <br/> Asa Sul - Brasília - DF</a></div></div>')
    block = ('<div class="footer-contact-item"><div class="d-flex flex-column">\n'
             f'<p class="link mt-3" style="color:#c5cbd0 !important">CNPJ {VALID1}</p>\n</div></div>')
    foot = '<footer><div class="footer-contacts-grid">' + brasilia + '{x}</div></footer>'
    home = '<html><body><main>Início</main>' + foot.format(x=block) + '</body></html>'
    page = '<html><body><main>Sobre</main>' + foot.format(x="") + '</body></html>'
    files = {"index.php": home, "sobre/index.html": page, "politica-de-privacidade/index.html": page}
    issues = mod.run_branch(dict(files), list(files), "ib-cytis-sepuvojs-br-pt")
    assert len(issues) == 1, issues
    msg = issues[0]["message"]
    assert "лише 1 з 3" in msg and "фікс скопіює" in msg and VALID1 in msg, msg
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "ib-cytis-sepuvojs-br-pt")}
    assert set(acts) == {"sobre/index.html", "politica-de-privacidade/index.html"}, "головну не чіпаємо: там уже є"
    assert all(brasilia + block in c for c in acts.values()), "той самий блок, у тому самому місці"
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "ib-cytis-sepuvojs-br-pt") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "ib-cytis-sepuvojs-br-pt") == []
    # номер у Política — вже «в условиях использования»: футери решти не потрібні
    legal = {**files, "politica-de-privacidade/index.html": page.replace("Sobre", f"CNPJ {VALID1}")}
    assert mod.run_branch(dict(legal), list(legal), "ib-cytis-sepuvojs-br-pt") == []


def test_quote_and_section_footers_are_not_the_site_footer():
    """Перший <footer> сторінки — не завжди підвал: цитата відгуку
    (<blockquote>…<footer>), CTA-«футер» секції (piivabmekwok), смуга ©
    після віджетів (Avada). Номер у будь-якому підвалі рівня сайту рахується;
    дописується в останній — справжній підвал."""
    _fresh_pool()
    avada = (f'<html><body><main><blockquote><p>Ótimo!</p><footer>— Ana</footer></blockquote></main>'
             f'<footer class="fusion-footer-widget-area"><p class="w">CNPJ {VALID1}</p></footer>'
             '<footer class="fusion-footer-copyright-area"><p class="c">© 2026 Moka</p></footer></body></html>')
    other = avada.replace(f"CNPJ {VALID1}", "Rua X, 10")
    files = {"index.php": avada, "blog/index.html": other}
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "moka-cotvonot-br-pt")}
    assert set(acts) == {"blog/index.html"}, "на головній номер уже у підвалі (віджети)"
    new = acts["blog/index.html"]
    assert '<footer>— Ana</footer>' in new, "цитату не чіпаємо"
    assert new.index(f"CNPJ {VALID1}") > new.index("© 2026 Moka"), "рядок — у справжньому (останньому) підвалі"


def test_vue_global_footer_component_carries_the_number_for_every_page():
    """nwf-*: футер — один компонент на всі сторінки. «Футер» документа
    юридичної сторінки (<main>…<footer>) і <Footer /> в App.vue — не
    підвали, яким бракує номера."""
    _fresh_pool()
    files = {"src/App.vue": "<template><div id=\"app\"><HeaderNav /><router-view /><Footer /></div></template>",
             "src/components/Footer.vue": f'<template><footer class="bg-zinc-900"><p class="t">CNPJ {VALID1}</p></footer></template>',
             "src/components/LegalTermsTerms.vue": '<template><main><p>Termos</p><footer class="mt-20"><p>Atualizado em 2026</p></footer></main></template>',
             "src/components/ClientQuoteHelp.vue": '<template><section><blockquote><p>Top</p><footer>— Rui</footer></blockquote></section></template>'}
    assert mod.run_branch(dict(files), list(files), "nwf-x-br-pt") == []
    assert mod.fix_branch(dict(files), list(files), "nwf-x-br-pt") == []
    # номер лише на сторінці «Contato» — копія йде в компонент-підвал, і тільки туди
    files["src/components/Footer.vue"] = '<template><footer class="bg-zinc-900"><p class="t">© 2026 X</p></footer></template>'
    files["src/components/ContactInfo.vue"] = f'<template><section><p>CNPJ {VALID1}</p></section></template>'
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "nwf-x-br-pt")}
    assert set(acts) == {"src/components/Footer.vue"}, set(acts)
    assert f'<p class="t">CNPJ {VALID1}</p>' in acts["src/components/Footer.vue"]


def test_check_is_registered_for_both_projects_as_auto():
    assert sorted(mod.PROJECTS) == ["node", "php"], mod.PROJECTS
    assert mod.GROUP == "auto"
    assert callable(mod.fix_branch)


if __name__ == "__main__":
    run(dict(globals()))
