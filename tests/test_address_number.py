"""Адреса без номера будинку: парсер + автофікс (ТЗ QA 01.10).

Еталонний кейс: «Estrada do Contorno, Angra dos Reis RJ 23900-000» на
/a-empresa — вулиця без номера. Контракти: судимо лише адресо-подібні
рядки з CEP; «s/n» і номер у будь-якому з двох перших сегментів —
валідні; фікс вставляє стабільний для (вітка, вулиця) номер; адреса без
ком — ручний випадок.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                          # noqa: E402

mod = load_check("address_number")

QA = "Estrada do Contorno, Angra dos Reis RJ 23900-000"
PAGE = f'<html><body><p class="text-sm text-gray-500">{QA}</p></body></html>'
BR = "nwf-angra-villas-br-pt"


def test_qa_case_is_flagged_with_fix_preview():
    issues = mod.run_branch({"a-empresa.html": PAGE}, ["a-empresa.html"], BR)
    assert len(issues) == 1, issues
    i = issues[0]
    assert i["severity"] == "error" and i["path"] == "a-empresa.html"
    assert QA in i["message"] and "без номера будинку" in i["message"]
    assert "фікс вставить «Estrada do Contorno " in i["message"], i


def test_valid_addresses_stay_silent():
    ok = [
        "Rua Jacarandá 651, Pq dos Pinheiros, 13184-570",       # номер у вулиці
        "Rua das Orquídeas, 324, Fortaleza, 60000-000",         # номер 2-м сегментом
        "Avenida Paulista, nº 1000, São Paulo SP 01310-100",    # nº-форма
        "Estrada Velha, s/n, Angra dos Reis RJ 23900-000",      # s/n легітимний
    ]
    for a in ok:
        files = {"contact.html": f"<p>{a}</p>"}
        assert mod.run_branch(files, list(files), BR) == [], a


def test_street_mention_without_cep_is_not_judged():
    files = {"about.html": "<p>Ficamos na Estrada do Contorno, perto do porto.</p>"}
    assert mod.run_branch(files, list(files), BR) == []
    assert mod.fix_branch(files, list(files), BR) == []


def test_mobile_phone_after_street_is_not_a_cep():
    """arikejabgag (TECH-29349, 28.10): «Rua das Orquídeas, Fortaleza, e o
    atendimento é feito pelo +55 85 98047-5613» — «98047-561» з мобільного
    номера читався як CEP, і фікс вставив би номер будинку в текст FAQ."""
    for line in ("Rua das Orquídeas, Fortaleza, e o atendimento é feito pelo +55 85 98047-5613",
                 "Rua das Orquídeas, Fortaleza. Fale conosco pelo (85) 98047-5613"):
        files = {"suporte.html": f"<p>{line}</p>"}
        assert mod.run_branch(dict(files), list(files), BR) == [], line
        assert mod.fix_branch(dict(files), list(files), BR) == [], line
    # справжній CEP поруч із телефоном лишається адресою без номера
    files = {"suporte.html": "<p>Rua das Orquídeas, Fortaleza - CE, 60000-000 · +55 85 98047-5613</p>"}
    issues = mod.run_branch(dict(files), list(files), BR)
    assert len(issues) == 1 and "60000-000" in issues[0]["message"], issues
    # звід адрес: «98047» з телефону не індекс — дві фрази з тією самою
    # вулицею не «дві різні адреси» (інакше фікс переписав би текст FAQ)
    files = {"suporte.html": "<p>Atendimento na Rua das Orquídeas, Fortaleza. Fale conosco pelo +55 85 98047-5613.</p>",
             "faq.html": "<p>Prestamos serviços na Rua das Orquídeas, Fortaleza, e o atendimento é feito pelo +55 85 98047-5613.</p>"}
    assert mod.run_branch(dict(files), list(files), BR) == []
    assert mod.fix_branch(dict(files), list(files), BR) == []


def test_fix_inserts_deterministic_number_after_street():
    files = {"a-empresa.html": PAGE}
    acts = mod.fix_branch(dict(files), list(files), BR)
    assert len(acts) == 1 and acts[0]["path"] == "a-empresa.html"
    new = acts[0]["content"]
    n = mod._number_for(BR, "Estrada do Contorno")
    assert f"Estrada do Contorno {n}, Angra dos Reis RJ 23900-000" in new, new
    assert 100 <= n <= 999
    # стилі/розмітка довкола цілі
    assert '<p class="text-sm text-gray-500">' in new
    # ідемпотентність: після фікса тихо, повторний фікс порожній
    fixed = {"a-empresa.html": new}
    assert mod.run_branch(fixed, list(fixed), BR) == []
    assert mod.fix_branch(fixed, list(fixed), BR) == []
    # стабільність і спред
    assert mod._number_for(BR, "Estrada do Contorno") == n
    others = {mod._number_for(f"nwf-x{i}-br-pt", "Estrada do Contorno")
              for i in range(8)}
    assert len(others) > 1, "різні вітки мають діставати різні номери"


def test_fix_never_touches_scripts_detect_cannot_see():
    # кейс mds-peqo-inwikjepex 15.10: раннер дає fix_branch УСІ текстові
    # файли, детект бачить лише сторінки. На сторінці «lane 1» — єдина
    # адреса, а в main.js «lane = 0», «lane + 1 : 0» читались як ще адреси;
    # звід до однієї переписав їх на «lane 1» → SyntaxError, мертві кнопки
    page = ("<html><body><footer><address>Peqo Inwikjepex<br>lane 1 · "
            "Padre Eustáquio · Belo Horizonte – MG<br>CNPJ 60.238.403/0001-03"
            "</address></footer></body></html>")
    js = ("function draw(){ let xx = start2, lane = 0;\n"
          "  if (gi && xx > W) { lane++; xx = start2; }\n"
          "  const nL2 = groups.length ? lane + 1 : 0; }\n")
    files = {"index.php": page, "main.js": js}
    assert mod.run_branch({"index.php": page}, ["index.php"], BR) == []
    assert mod.fix_branch(dict(files), list(files), BR) == []


def test_prose_street_word_and_alt_attribute_are_not_an_address():
    """avizpuoplovjitao 19.10: alt="WEG" (логотип) і «em diagonal: … 45
    graus» у блозі глушили «адреси немає зовсім» — fale-conosco лишався
    без адреси, QA повертав таску. Вуличне слово в атрибуті або з малої
    в прозі без номера — не адреса; «lane 1» з номером — адреса."""
    files = {"index.php": '<html><body><img alt="WEG" width="315"><footer><p>CNPJ 20.284.967/0001-50</p></footer></body></html>',
             "blog/index.html": "<html><body><p>Rachaduras em diagonal: trincas em ângulo de 45 graus.</p></body></html>"}
    assert not mod._branch_has_address(files, BR)
    issues = mod.run_branch(dict(files), list(files), BR)
    assert len(issues) == 1 and "немає адреси" in issues[0]["message"], issues
    assert mod.fix_branch(dict(files), list(files), BR), "обіцяно адресу — фікс мусить її додати"
    assert mod._branch_has_address({"index.php": "<footer>lane 1 · Padre Eustáquio</footer>"}, BR)

def test_hyphenated_street_and_dotted_registry_number_are_not_an_address_span():
    """atowoos-des-chavclod (локальна партія 20.10): «Grand-Rue 22» матчилось
    з «Rue» (вулиця без назви), а «(UID CHE-128.456.790), Rue» — як зворотна
    форма «число … Rue», і звід переписав UID на адресу."""
    m = mod._any_street("Grand-Rue 22, 2034 Peseux")
    assert m is None or not m.group(0).startswith("Rue"), m and m.group(0)
    page = ('<html><body><p>Atelier Sàrl (UID CHE-128.456.790), Grand-Rue 22, 2034 Peseux, est responsable.</p>'
            '<footer><p>Grand-Rue 22, 2034 Peseux</p></footer></body></html>')
    spans = mod._address_spans({"index.html": page})
    assert all("CHE-" not in s and "128.456" not in s for *_, s in spans), spans
    assert mod.fix_branch({"index.html": page}, ["index.html"], "atelier-ch-fr") == []

def test_common_noun_street_word_is_never_unified_into():
    # кейс argeehiheoqapi 15.10: блог «…nível da rua. Num lote com 1,50 m»
    # (двічі: сторінка + її копія) переважив справжню адресу контактів, і
    # звід замінив би «Rua Alceu Amoroso Lima, 172 … 41820-770» на уривок
    real = ("Rua Alceu Amoroso Lima, 172, Caminho das Árvores, "
            "Salvador, BA — CEP 41820-770")
    blog = "<p>O acesso fica no nível da rua. Num lote com 1,50 m de desnível.</p>"
    files = {"contato/index.html": f"<html><body><p>{real}</p></body></html>",
             "blog/a/index.html": f"<html><body>{blog}</body></html>",
             "blog/b/index.html": f"<html><body>{blog}</body></html>"}
    assert mod.run_branch(dict(files), list(files), BR) == []
    assert mod.fix_branch(dict(files), list(files), BR) == []


def test_dot_separator_counts_as_segment_break():
    # кейс padohvae-da-proou 01.10: роздільник « · » замість ком — адреса
    # сегментована, фікс працює і зберігає стиль роздільника
    addr = "Estrada do Contorno · Angra dos Reis · RJ 23900-000"
    files = {"c.html": f"<p>{addr}</p>"}
    issues = mod.run_branch(dict(files), list(files), BR)
    assert len(issues) == 1 and "фікс вставить" in issues[0]["message"], issues
    new = mod.fix_branch(dict(files), list(files), BR)[0]["content"]
    n = mod._number_for(BR, "Estrada do Contorno")
    assert f"Estrada do Contorno {n} · Angra dos Reis · RJ 23900-000" in new, new
    fixed = {"c.html": new}
    assert mod.run_branch(fixed, list(fixed), BR) == []
    # номер другим сегментом через « · » — валідна адреса
    ok = {"c.html": "<p>Rua das Dunas · 238 · São Miguel · AL 57940-000</p>"}
    assert mod.run_branch(dict(ok), list(ok), BR) == []



# ----------------------------------------------- адреси немає ВЗАГАЛІ (гео)
NOADDR = ('<html><body><footer class="bg-x">'
          '<p class="text-xs font-mono">© 2026 Crescimento Ltda.</p>'
          '</footer></body></html>')


def test_branch_without_any_address_gets_geo_one():
    files = {"index.html": NOADDR, "about.html": NOADDR}
    issues = mod.run_branch(dict(files), list(files), BR)
    assert len(issues) == 1 and "немає адреси" in issues[0]["message"]
    assert "(br-pt)" in issues[0]["message"], issues
    acts = {a["path"]: a for a in mod.fix_branch(dict(files), list(files), BR)}
    assert set(acts) == {"index.html", "about.html"}
    new = acts["index.html"]["content"]
    geo = mod._geo_pick(BR)
    assert f'<p class="text-xs font-mono">{geo}</p>' in new, new
    # адреса з бази валідна за нашим же парсером і гасить missing
    fixed = {"index.html": new, "about.html": acts["about.html"]["content"]}
    assert mod.run_branch(dict(fixed), list(fixed), BR) == []
    assert mod.fix_branch(dict(fixed), list(fixed), BR) == []
    # детермінізм за віткою і спред між вітками
    assert mod._geo_pick(BR) == geo
    assert len({mod._geo_pick(f"nwf-x{i}-br-pt") for i in range(8)}) > 3


def test_filled_locales_offer_geo_and_empty_stay_silent():
    files = {"index.html": NOADDR}
    # mx-es тепер має базу (OSM) — missing пропонує адресу їхнього формату
    issues = mod.run_branch(dict(files), list(files), "nwf-casa-mx-es")
    assert len(issues) == 1 and "(mx-es)" in issues[0]["message"], issues
    acts = mod.fix_branch(dict(files), list(files), "nwf-casa-mx-es")
    assert acts and mod._geo_pick("nwf-casa-mx-es") in acts[0]["content"]
    # локаль без бази (de-de відсутня у файлі) — тихо
    assert mod.run_branch(dict(files), list(files), "nwf-haus-de-de") == []
    assert mod.fix_branch(dict(files), list(files), "nwf-haus-de-de") == []


def test_any_geo_address_counts_as_present():
    # mx/it/sg-формати адрес мають гасити missing-гілку (детект ширший за br)
    for line in ("Calle Madero 12, Ciudad de México, 06000",
                 "Via Roma 10, 20121 Milano",
                 "7 Maxwell Road, Singapore 069111",
                 "Bahnhofstrasse 1, 8001 Zürich"):
        files = {"index.html": NOADDR.replace("</footer>",
                                              f"<p>{line}</p></footer>")}
        assert mod.run_branch(dict(files), list(files), "nwf-x-mx-es") == [], line


def test_italian_snc_and_locality_addresses_count_as_present():
    """peliril-it-it (27.10): юридична адреса баєра «Località Brasoli SNC, Le
    Castella, Isola di Capo Rizzuto (KR)» — без вуличного слова зі списку,
    без номера (SNC = senza numero civico) і без CAP; чек вважав, що адреси
    нема, і фікс дописував би у футер другу, вигадану з гео-бази Рима."""
    for line in ("Località Brasoli SNC, Le Castella, Isola di Capo Rizzuto (KR), Italia",
                 "Via Dante Alighieri SNC, 87028 Praia a Mare (CS)",
                 "Contrada Serra s.n.c., 88841 Isola di Capo Rizzuto",
                 "Frazione Molini 4, 12020 Vinadio"):
        files = {"index.html": NOADDR.replace("</footer>", f"<p>{line}</p></footer>")}
        assert mod.run_branch(dict(files), list(files), "peliril-it-it") == [], line
        assert mod.fix_branch(dict(files), list(files), "peliril-it-it") == [], line


def test_unification_replaces_the_whole_address_and_leaves_urls_and_prose_alone():
    """isacubo-it-it (27.10): звід «Via della Spiga 46, 20121 Milano» → канон
    давав «CONTRADA … 28, 91025 Milano» (спан кінчався на індексі, місто
    старої адреси лишалось), ламав iframe-запит мапи (%20-кодований
    канон) і речення в termini («…91025 MARSALA TP, Italia, telefono +39…»
    різалось до індексу). Спан — до міста включно; URL і прозу не чіпаємо."""
    foot = ('<footer><p class="addr">CONTRADA ETTORE INFERSA 28, 91025 MARSALA TP, Italia</p>'
            '<iframe src="https://www.google.com/maps?q=CONTRADA%20ETTORE%20INFERSA%2028%2C%2091025%20MARSALA%20TP%2C%20Italia&output=embed"></iframe>'
            '<p class="mt-4 text-sm">Via della Spiga 46, 20121 Milano</p></footer>')
    home = "<html><body><h1>Isacubo</h1>" + foot + "</body></html>"
    terms = ("<html><body><h1>Termini</h1><p>KRIVAMAR DI OTTOVEGGIO MARIO, CONTRADA ETTORE INFERSA 28, 91025 MARSALA TP, Italia, "
             "telefono +39 339 490 4090, email info@{{DOMAIN}}.</p>" + foot + "</body></html>")
    files = {"index.php": home, "chi-siamo.html": home, "termini-condizioni.html": terms}
    issues = mod.run_branch(dict(files), list(files), "isacubo-it-it")
    assert len(issues) == 1 and "2 різні адреси" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "isacubo-it-it")}
    assert set(acts) == {"index.php", "chi-siamo.html", "termini-condizioni.html"}, acts.keys()
    for p, new in acts.items():
        assert "Milano" not in new and "Spiga" not in new, p
        assert '<p class="mt-4 text-sm">CONTRADA ETTORE INFERSA 28, 91025 MARSALA TP</p>' in new, p
        assert 'maps?q=CONTRADA%20ETTORE%20INFERSA%2028%2C%2091025%20MARSALA%20TP%2C%20Italia&output=embed' in new, "URL не чіпаємо"
    assert "91025 MARSALA TP, Italia, telefono +39 339 490 4090, email" in acts["termini-condizioni.html"], "речення цілe"
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "isacubo-it-it") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "isacubo-it-it") == []

def test_unify_drops_the_stray_line_when_the_canon_is_its_neighbour():
    """isacubo-it-it (27.10, коміт 9d2a4bd3 іншого інстансу лаби): старий
    address_number не знав «Contrada», вважав, що адреси нема, і доклеїв у
    футер гео-рядок «Via della Spiga 46, 20121 Milano» ОДРАЗУ ПІД юридичною.
    Звід підміною тексту дав би два однакові рядки поспіль — якщо сусідній
    елемент уже несе канон, зайвий елемент прибираємо цілком."""
    foot = ('<footer><p class="mt-4 text-sm">Brijowwa è gestito da KRIVAMAR.</p>\n'
            '      <p class="mt-4 text-sm">CONTRADA ETTORE INFERSA 28, 91025 MARSALA TP</p>\n'
            '      <p class="mt-4 text-sm">Via della Spiga 46, 20121 Milano</p>\n    </footer>')
    home = "<html><body><h1>Isacubo</h1>" + foot + "</body></html>"
    terms = ("<html><body><h1>Termini</h1><p>KRIVAMAR DI OTTOVEGGIO MARIO, CONTRADA ETTORE INFERSA 28, 91025 MARSALA TP, Italia.</p>"
             + foot + "</body></html>")
    files = {"index.php": home, "chi-siamo.html": home, "termini-condizioni.html": terms}
    issues = mod.run_branch(dict(files), list(files), "isacubo-it-it")
    assert len(issues) == 1 and "2 різні адреси" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "isacubo-it-it")}
    assert set(acts) == {"index.php", "chi-siamo.html", "termini-condizioni.html"}
    for p, new in acts.items():
        assert "Milano" not in new and new.count("CONTRADA ETTORE INFERSA 28") == (2 if p.startswith("termini") else 1), new
        assert '<p class="mt-4 text-sm">CONTRADA ETTORE INFERSA 28, 91025 MARSALA TP</p>\n    </footer>' in new, new
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), "isacubo-it-it") == []

def test_city_less_mention_of_the_same_address_is_not_a_second_address():
    """naekune / majuvaji / semence (27.10): у прозі адреса без міста
    («…14, 95062, a Motta Sant'Anastasia (CT)», «sede legale in VIA BORGO
    ITALIA 12, 91017, email …», «Rue de Lausanne 17, 1530, Payerne») —
    та сама адреса, коротший запис. Звід вставляв канон у речення («95062
    MOTTA SANT, a Motta Sant'Anastasia») — місто з апострофом ще й різалось.
    Варіант-префікс канону — не друга адреса; місто з апострофом — ціле."""
    foot = "<footer><p>VIA CADUTI DI TUTTE LE GUERRE 14, 95062 MOTTA SANT'ANASTASIA CT</p></footer>"
    prose = ("<main><p>La sede legale si trova in VIA CADUTI DI TUTTE LE GUERRE 14, 95062, a Motta Sant'Anastasia (CT), "
             "raggiungibile in pochi minuti.</p></main>")
    files = {"index.php": "<html><body>" + foot + "</body></html>", "contatti.html": "<html><body>" + prose + foot + "</body></html>",
             "termini-condizioni.html": "<html><body><p>NAEKUNE SRL, VIA CADUTI DI TUTTE LE GUERRE 14, 95062 MOTTA SANT'ANASTASIA CT, Italia.</p>" + foot + "</body></html>"}
    sp = mod._address_spans(files)
    assert any(s.endswith("SANT'ANASTASIA CT") for *_, s in sp), [s for *_, s in sp]
    assert mod.run_branch(dict(files), list(files), "naekune-it-it") == []
    assert mod.fix_branch(dict(files), list(files), "naekune-it-it") == []
    # а справді інша адреса поруч — як і раніше, зводиться
    files["faq.html"] = "<html><body><p>Via Roma 10, 20121 Milano</p>" + foot + "</body></html>"
    issues = mod.run_branch(dict(files), list(files), "naekune-it-it")
    assert len(issues) == 1 and "Via Roma 10, 20121 Milano" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "naekune-it-it")}
    assert set(acts) == {"faq.html"} and "Via Roma" not in acts["faq.html"], acts.keys()

def test_impressum_address_beats_privacy_filler_as_the_canon():
    """equipage ch-fr (27.10): datenschutzerklarung несе шаблонний рядок
    «Rue du Léman 12, 1920 Martigny» у 4 випадкових абзацах, kontakt — той
    самий; Impressum і головна — реальну «Av. de la Gare 66, 1904 Martigny»
    (додано людиною після QA). Канон — з Impressum, не найчастіший."""
    imp = "<html><body><h1>Impressum</h1><p>Éqeudoha Cotfaup SA</p><p>Av. de la Gare 66, 1904 Martigny, Suisse</p><p>UID CHE-391.795.406</p></body></html>"
    ds = ("<html><body><h1>Protection des données</h1><h3>Mesures techniques</h3><p>Rue du Léman 12, 1920 Martigny</p>"
          "<h3>Données de tiers</h3><p>Rue du Léman 12, 1920 Martigny</p><h3>Réseaux sociaux</h3><p>Rue du Léman 12, 1920 Martigny</p></body></html>")
    home = "<html><body><p>Nos bureaux : Av. de la Gare 66, 1904 Martigny, Suisse.</p></body></html>"
    kontakt = "<html><body><p>Éqeudoha Cotfaup SA, Rue du Léman 12, 1920 Martigny</p></body></html>"
    files = {"index.php": home, "kontakt/index.html": kontakt, "impressum/index.html": imp, "datenschutzerklarung/index.html": ds}
    assert mod._legal_address(files, "equipage-ch-fr").startswith("Av. de la Gare 66, 1904 Martigny")
    issues = mod.run_branch(dict(files), list(files), "equipage-ch-fr")
    assert len(issues) == 1 and "зведе всі до «Av. de la Gare 66, 1904 Martigny" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "equipage-ch-fr")}
    assert "kontakt/index.html" in acts and "Av. de la Gare 66, 1904 Martigny" in acts["kontakt/index.html"]
    assert "Rue du Léman" not in "".join(acts.values())





def test_geo_base_rows_are_parser_valid():
    rows = mod._geo_rows("br-pt")
    assert len(rows) >= 300, len(rows)
    import random
    for a in random.Random(1).sample(rows, 25):
        recs = mod.parse(f"<p>{a}</p>")
        assert len(recs) == 1 and recs[0]["ok"], a



def test_geo_base_row_counts_as_address_even_without_street_word():
    # узгодження детект↔фікс (кейс eskufoo-juhuhugo 01.10): ar-es адреса
    # «Larrea 1269, …» без слова вулиці; доданий фіксом рядок мусить
    # глушити missing, інакше чек кричить вічно, а фікс каже «вже є»
    row = mod._geo_rows("ar-es")[0]
    files = {"index.html": NOADDR.replace("</footer>",
                                          f"<p>{row}</p></footer>")}
    assert mod.run_branch(dict(files), list(files), "nwf-x-ar-es") == [], row
    assert mod.fix_branch(dict(files), list(files), "nwf-x-ar-es") == []
    # а для вітки ІНШОЇ локалі цей же рядок адресою не вважається
    issues = mod.run_branch(dict(files), list(files), "nwf-x-th-en")
    assert issues and "немає адреси" in issues[0]["message"]


def test_legal_address_is_duplicated_into_footer():
    # кейс crescimento + прохання 01.10: адреса з terms — канонічна; якщо
    # на видимих сторінках її немає, фікс ДУБЛЮЄ її у футер (не гео-базу)
    files = {"index.html": NOADDR,
             "src/components/TermsContentTerms.vue":
                 "<footer><p>Rua Rio Branco 850, Manaus, AM 69057-002"
                 "</p></footer>"}
    issues = mod.run_branch(dict(files), list(files), "nwf-x-br-pt")
    assert issues and "немає адреси" in issues[0]["message"]
    assert "продублює адресу з юридичної" in issues[0]["message"]
    assert "Rua Rio Branco 850" in issues[0]["message"]
    assert "Terms" not in issues[0]["path"]
    acts = mod.fix_branch(dict(files), list(files), "nwf-x-br-pt")
    assert acts and all("Terms" not in a["path"] for a in acts), acts
    out = next(a for a in acts if a["path"] == "index.html")["content"]
    assert "Rua Rio Branco 850, Manaus, AM 69057-002" in out
    # після дублю — тихо і нуль дій (узгодженість детект↔фікс)
    fixed = dict(files); fixed["index.html"] = out
    assert mod.run_branch(dict(fixed), list(fixed), "nwf-x-br-pt") == []
    assert mod.fix_branch(dict(fixed), list(fixed), "nwf-x-br-pt") == []


def test_no_address_anywhere_falls_back_to_geo_base():
    files = {"index.html": NOADDR,
             "src/components/TermsContentTerms.vue":
                 "<footer><p>Sem endereço aqui</p></footer>"}
    issues = mod.run_branch(dict(files), list(files), "nwf-x-br-pt")
    assert issues and "додасть з гео-бази" in issues[0]["message"]


def test_network_budget_caps_requests_per_run():
    """02.10 (auduatjinxofoqe): вітка з багатьма адресами множила 4с-таймаути
    і «рахую автофікси…» висіло хвилинами. Бюджет: ≤ _NET_LIMIT нових
    HTTP за прогін; 2 збої поспіль глушать хост; збої не кешуються."""
    calls = []
    import urllib.request as _u
    old_open, old_cache = _u.urlopen, dict(mod._NET_CACHE)

    def fake(req, timeout=0):
        calls.append(req.full_url)
        raise OSError("timeout")
    _u.urlopen = fake
    mod._NET_CACHE.clear()
    try:
        mod._net_reset()
        for i in range(20):
            assert mod._http_json(f"https://viacep.com.br/ws/0{i}/json/") is None
        assert len(calls) == 2, f"2 збої мали заглушити хост, було {len(calls)}"
        assert not mod._NET_CACHE, "збої не можна кешувати"
        # бюджет: 20 здорових відповідей упираються у ліміт
        calls.clear()
        def ok200(req, timeout=0):
            calls.append(1)
            import io
            class R(io.BytesIO):
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return R(b"[]")
        _u.urlopen = ok200
        mod._net_reset()
        for i in range(20):
            mod._http_json(f"https://viacep.com.br/ws/1{i}/json/")
        assert len(calls) == mod._NET_LIMIT, calls
    finally:
        _u.urlopen = old_open
        mod._NET_CACHE.clear()
        mod._NET_CACHE.update(old_cache)
        mod._net_reset()


def test_two_distinct_addresses_are_unified_to_one():
    # 02.10: дві РІЗНІ адреси на вітці — лишається одна; канон — юридична
    legal = "Rua Rio Branco 850, Manaus, AM 69057-002"
    other = "Avenida Paulista 1000, São Paulo, SP 01310-100"
    files = {"index.html": NOADDR.replace(
                 "</footer>", f"<p>{other}</p></footer>"),
             "about.html": f"<main><p>{legal}</p></main>",
             "src/components/TermsContentTerms.vue":
                 f"<footer><p>{legal}</p></footer>"}
    issues = mod.run_branch(dict(files), list(files), "nwf-x-br-pt")
    assert len(issues) == 1 and "різні адреси" in issues[0]["message"], issues
    assert legal in issues[0]["message"]           # канон названо
    acts = mod.fix_branch(dict(files), list(files), "nwf-x-br-pt")
    out = {a["path"]: a["content"] for a in acts}
    assert "index.html" in out and other not in out["index.html"]
    assert legal in out["index.html"]
    # після зводу — тихо і нуль дій
    healed = {**files, **out}
    assert mod.run_branch(dict(healed), list(healed), "nwf-x-br-pt") == []
    assert mod.fix_branch(dict(healed), list(healed), "nwf-x-br-pt") == []


def test_office_list_in_different_states_is_not_unified():
    """ib-cytis 21.10: футер — три офіси (São Paulo / Curitiba / Brasília).
    20.10 звід переписав офісу в Сан-Паулу вулицю курітібського; ще одна
    сторінка з «чужою» адресою все одно зводиться, але не філії."""
    foot = ('<footer><div><h4>São Paulo</h4><a>Av. Ibirapuera, 2033 Moema <br/> - São Paulo - SP</a></div>'
            '<div><h4>Curitiba</h4><a>Av. Manoel Ribas, 985 - SL 38/39 <br/> Mercês - Curitiba - PR</a></div></footer>')
    files = {"index.html": f"<html><body><main></main>{foot}</body></html>",
             "sobre/index.html": f"<html><body><main></main>{foot}</body></html>"}
    issues = mod.run_branch(dict(files), list(files), "x-br-pt")
    assert all("різні адреси" not in i["message"] for i in issues), issues
    assert mod.fix_branch(dict(files), list(files), "x-br-pt") == []
    # а третя адреса на іншій сторінці (не філія) — зводиться до найчастішої
    files["contato/index.html"] = "<html><body><p>Rua Augusta, 100, Consolação, São Paulo SP 01305-000</p></body></html>"
    files["termos/index.html"] = "<html><body><p>Rua Augusta, 200, Consolação, São Paulo SP 01305-000</p></body></html>"
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "x-br-pt")}
    assert "index.html" not in acts and "sobre/index.html" not in acts, "філії лишились як були"


def test_same_address_in_two_spellings_is_not_two():
    a1 = "Rua Rio Branco 850, Manaus, AM 69057-002"
    a2 = "Rua  Rio Branco, 850 — Manaus AM, 69057-002"   # та сама, інший запис
    files = {"index.html": NOADDR.replace("</footer>",
                                          f"<p>{a1}</p><p>{a2}</p></footer>")}
    issues = mod.run_branch(dict(files), list(files), "nwf-x-br-pt")
    assert all("різні адреси" not in i["message"] for i in issues), issues
# --------------------------------------------- commaless: каскад межі вулиці
def _mock_net(cep=None, street_hits=None):
    """Мокаємо мережу каскаду; повертає функцію відновлення."""
    old_cep, old_street = mod._viacep, mod._viastreet
    mod._viacep = lambda c: cep
    mod._viastreet = lambda uf, city, st: (street_hits or {}).get((city, st))
    def restore():
        mod._viacep, mod._viastreet = old_cep, old_street
    return restore


def test_commaless_unconfirmed_is_manual_only():
    # мережа лежить, UF-токена немає — межа не підтверджена
    r = _mock_net(cep=None)
    try:
        files = {"contact.html":
                 "<p>Estrada do Contorno Angra dos Reis 23900-000</p>"}
        issues = mod.run_branch(dict(files), list(files), BR)
        assert len(issues) == 1 and "додай номер руками" in issues[0]["message"]
        assert mod.fix_branch(dict(files), list(files), BR) == []
    finally:
        r()


def test_commaless_resolved_by_registry_logradouro():
    # крок 1: точковий CEP знає вулицю (регістр/діакритика не заважають)
    r = _mock_net(cep={"logradouro": "Rua Siqueira Campos",
                       "localidade": "Rio de Janeiro", "uf": "RJ"})
    try:
        files = {"c.html": "<p>RUA SIQUEIRA CAMPOS Copacabana RJ 22031-071</p>"}
        issues = mod.run_branch(dict(files), list(files), BR)
        assert "підтверджено CEP-реєстром" in issues[0]["message"], issues
        new = mod.fix_branch(dict(files), list(files), BR)[0]["content"]
        n = mod._number_for(BR, "RUA SIQUEIRA CAMPOS")
        assert f"RUA SIQUEIRA CAMPOS {n}, Copacabana RJ 22031-071" in new, new
    finally:
        r()


def test_commaless_resolved_by_registry_city():
    # крок 2: загальний CEP без вулиці, але місто з реєстру є в рядку
    r = _mock_net(cep={"logradouro": "", "localidade": "Imbituba", "uf": "SC"})
    try:
        files = {"c.html": "<p>Estrada Geral da Praia Imbituba SC 88780-000</p>"}
        new = mod.fix_branch(dict(files), list(files), BR)[0]["content"]
        n = mod._number_for(BR, "Estrada Geral da Praia")
        assert f"Estrada Geral da Praia {n}, Imbituba SC 88780-000" in new, new
    finally:
        r()


def test_commaless_resolved_by_street_search_iteration():
    # крок 3: реєстр CEP порожній; пошук вулиці підтверджує ПРАВИЛЬНЕ розбиття
    hits = {("Niteroi", "Rua Mem"): None,
            ("Centro Niteroi", "Rua"): None}
    hits[("Niteroi", "Rua Mem Centro")] = None
    r = _mock_net(cep={},
                  street_hits={("Niteroi", "Rua Mem de Sa"):
                               [{"logradouro": "Rua Mem de Sá"}]})
    try:
        files = {"c.html": "<p>Rua Mem de Sa Niteroi RJ 24220-261</p>"}
        new = mod.fix_branch(dict(files), list(files), BR)[0]["content"]
        n = mod._number_for(BR, "Rua Mem de Sa")
        assert f"Rua Mem de Sa {n}, Niteroi RJ 24220-261" in new, new
    finally:
        r()


def test_commaless_resolved_by_service_word_heuristic():
    # крок 4 (без мережі): «Angra DOS Reis» — службове слово тримає місто вкупі
    r = _mock_net(cep=None)
    try:
        files = {"c.html": "<p>Estrada do Contorno Angra dos Reis RJ 23900-000</p>"}
        issues = mod.run_branch(dict(files), list(files), BR)
        assert "підтверджено CEP-реєстром/розбором" in issues[0]["message"], issues
        new = mod.fix_branch(dict(files), list(files), BR)[0]["content"]
        n = mod._number_for(BR, "Estrada do Contorno")
        assert f"Estrada do Contorno {n}, Angra dos Reis RJ 23900-000" in new, new
        fixed = {"c.html": new}
        assert mod.run_branch(fixed, list(fixed), BR) == []
    finally:
        r()


def test_two_capitalized_city_words_stay_manual():
    # «Belo Horizonte» без службових — межу так не відрізнити: ручний випадок
    r = _mock_net(cep=None)
    try:
        files = {"c.html": "<p>Rua Sapucai Belo Horizonte MG 30150-904</p>"}
        issues = mod.run_branch(dict(files), list(files), BR)
        assert "додай номер руками" in issues[0]["message"], issues
        assert mod.fix_branch(dict(files), list(files), BR) == []
    finally:
        r()


def test_multiple_addresses_in_one_file_all_fixed():
    two = (f"<p>{QA}</p>"
           "<p>Avenida Atlântica, Copacabana RJ 22010-000</p>")
    files = {"index.php": two}
    acts = mod.fix_branch(dict(files), list(files), BR)
    new = acts[0]["content"]
    assert f"Estrada do Contorno {mod._number_for(BR, 'Estrada do Contorno')}," in new
    assert f"Avenida Atlântica {mod._number_for(BR, 'Avenida Atlântica')}," in new
    # крок 2 (02.10): номери чисті, але адреси ДВІ РІЗНІ — звід до однієї
    fixed = {"index.php": new}
    issues = mod.run_branch(dict(fixed), list(fixed), BR)
    assert len(issues) == 1 and "різні адреси" in issues[0]["message"], issues
    acts2 = mod.fix_branch(dict(fixed), list(fixed), BR)
    final = {"index.php": acts2[0]["content"]}
    assert mod.run_branch(dict(final), list(final), BR) == []
    assert mod.fix_branch(dict(final), list(final), BR) == []


# футер корпусу mds-*: зібраний з <address>/<div>, жодного <p>. Саме на
# ньому фікс мовчки повертав 0 дій, а чек рапортував помилку щопрогону.
ADDRESS_FOOTER = (
    '<html><body><main><h1>Consultoria</h1></main>'
    '<footer class="seller" id="seller" lang="pt-BR"><div class="seller-in">'
    '<address><b>Quem vende</b><strong>Nestor Luiz Breda</strong><br>'
    'Educador financeiro e consultor<br>'
    'Florianópolis – SC (endereço: a inserir)<br>'
    'CNPJ 36.772.368/0001-15</address>'
    '<address><b>Contatos</b>Telefone: '
    '<a href="tel:+5548998464680">+55 48 99846 4680</a></address>'
    '</div></footer></body></html>')


def test_footer_built_on_address_tags_still_gets_the_line():
    files = {"index.html": ADDRESS_FOOTER}
    issues = mod.run_branch(dict(files), list(files), BR)
    assert len(issues) == 1, issues
    assert "немає адреси" in issues[0]["message"], issues
    # чек пообіцяв фікс - фікс мусить його дати, інакше помилка вічна
    acts = mod.fix_branch(dict(files), list(files), BR)
    assert acts, "чек обіцяє фікс, а fix_branch повернув 0 дій"
    fixed = {a["path"]: a["content"] for a in acts}
    assert mod._geo_pick(BR) in fixed["index.html"], fixed["index.html"][-300:]
    # і найголовніше: після фікса чек мовчить
    assert mod.run_branch(dict(fixed), list(fixed), BR) == []


def test_check_never_promises_a_fix_it_cannot_make():
    """Інваріант: або чек обіцяє фікс і фікс дає дію, або чек чесно
    відправляє до людини. Дефект видно в обох випадках."""
    for name, page in (("address-футер", ADDRESS_FOOTER),
                       ("div-футер", ADDRESS_FOOTER.replace("address>", "div>"))):
        files = {"index.html": page}
        issues = mod.run_branch(dict(files), list(files), BR)
        assert len(issues) == 1, f"{name}: дефект мусить бути видно — {issues}"
        msg = issues[0]["message"]
        promised = "фікс додасть" in msg or "фікс продублює" in msg
        acts = mod.fix_branch(dict(files), list(files), BR)
        assert promised == bool(acts), f"{name}: обіцянка={promised}, дій={len(acts)}"
        if not promised:
            assert "руками" in msg, f"{name}: {msg}"


def test_contract_auto_for_both_projects():
    assert sorted(mod.PROJECTS) == ["node", "php"], mod.PROJECTS
    assert mod.GROUP == "auto"
    assert callable(mod.fix_branch)


def test_unify_never_rewrites_inside_img_attributes():
    """nwf-ledmi-ingakisihde 16.10: звід адрес прийняв «06.jpg" alt="Controle
    remoto via» (src+alt картинки, PT «via» = «через») за адресу і переписав
    ім'я файла на канонічну адресу. Спан мусить лежати в одному текстовому
    вузлі — атрибути тегів не адреса."""
    gallery = ('<figure><img src="/src/assets/images/bdceef06.jpg" '
               'alt="Controle remoto via app" class="w-full" />'
               "<figcaption>Monitoramento remoto</figcaption></figure>")
    contact = ("<footer><p>Rua Tibúrcio Cavalcante 304, Fortaleza 60125-130, "
               "Brasil</p><p>Av. Beira Mar 1000, Fortaleza 60165-121</p></footer>")
    files = {"src/components/Gallery.vue": gallery,
             "src/components/Contact.vue": contact}
    spans = mod._address_spans(dict(files))
    assert all(p != "src/components/Gallery.vue" for p, *_ in spans), spans
    acts = mod.fix_branch(dict(files), list(files), "nwf-x-br-pt")
    for a in acts:
        if a["path"] == "src/components/Gallery.vue":
            assert "bdceef06.jpg" in a["content"], a["content"]
            assert 'alt="Controle remoto via app"' in a["content"]


# ------------------------------------------------ hr-hr (26.10, партія sakgucnez)
# QA: «Адрес на / не распознан (улица без номера дома: «Ulica Petra
# Krešimira IV, …»)» і «нет адреса» на stit/surjoke/tvgstadi/zastita. Чек
# мовчав: вулиці без номера судились лише бразильські (CEP), гео-бази hr-hr
# не було, hr-вуличних слів детект не знав.
HR = "nwf-stefziv-sakgucnez-hr-hr"


def test_hr_street_without_house_number_gets_one():
    page = "<template><p>Ulica Petra Krešimira IV, Šibenik, 22000, Hrvatska</p></template>"
    # картка на головній несе ту саму вулицю без номера (і без індексу —
    # її переписує contact_block); номер ставиться в terms, де є індекс
    card = "<template><p>Ulica Petra Krešimira IV, Posljednje ažurirano 2023</p></template>"
    files = {"src/components/TermsOfServiceTerms.vue": page,
             "src/components/ContactUsHome.vue": card}
    issues = mod.run_branch(dict(files), list(files), HR)
    assert len(issues) == 1 and "без номера будинку" in issues[0]["message"], issues
    assert issues[0]["path"] == "src/components/TermsOfServiceTerms.vue", issues
    n = mod._number_for(HR, "Ulica Petra Krešimira IV")
    acts = mod.fix_branch(dict(files), list(files), HR)
    assert [a["path"] for a in acts] == ["src/components/TermsOfServiceTerms.vue"], acts
    out = acts[0]["content"]
    assert f"<p>Ulica Petra Krešimira IV {n}, Šibenik, 22000, Hrvatska</p>" in out, out
    fixed = {**files, "src/components/TermsOfServiceTerms.vue": out}
    assert mod.run_branch(dict(fixed), list(fixed), HR) == []
    assert mod.fix_branch(dict(fixed), list(fixed), HR) == []
    # суфіксна форма вулиці: «Trpinjska ulica, 10000 Zagreb»
    files = {"src/components/Footer.vue": "<p>Trpinjska ulica, 10000 Zagreb</p>"}
    out = mod.fix_branch(dict(files), list(files), HR)[0]["content"]
    m = mod._number_for(HR, "Trpinjska ulica")
    assert f"<p>Trpinjska ulica {m}, 10000 Zagreb</p>" in out, out


def test_hr_branch_without_address_gets_hr_geo_row():
    files = {"index.html": NOADDR}
    issues = mod.run_branch(dict(files), list(files), "nwf-tvgstadi-hr-hr")
    assert len(issues) == 1 and "(hr-hr)" in issues[0]["message"], issues
    out = mod.fix_branch(dict(files), list(files), "nwf-tvgstadi-hr-hr")[0]["content"]
    assert mod._geo_pick("nwf-tvgstadi-hr-hr") in out, out
    fixed = {"index.html": out}
    assert mod.run_branch(dict(fixed), list(fixed), "nwf-tvgstadi-hr-hr") == []


def test_hr_addresses_in_any_form_count_as_present():
    """Гео-база hr-hr вмикає missing-гілку для 260 hr-віток: адреса без
    вуличного слова («Putine 18», «Korzo 15») мусить гасити її — інакше фікс
    доклеїв би у футер другу, вигадану адресу."""
    for line in ("Putine 18, 10090 Zagreb, Hrvatska",
                 "Trpinjska ulica 3, 10000 Zagreb",
                 "Ulica kneza Branimira 17, 10000 Zagreb",
                 "Korzo 15, 51000 Rijeka",
                 "Kapucinska 12, Osijek, Osječko-baranjska županija 31000, Hrvatska"):
        files = {"index.html": NOADDR.replace("</footer>", f"<p>{line}</p></footer>")}
        assert mod.run_branch(dict(files), list(files), "nwf-x-hr-hr") == [], line


def test_croatian_prose_is_not_an_address():
    for line in ("Trgovina radi od 8 do 16 sati", "Javite nam se putem telefona 24 sata",
                 "Trg je udaljen 5 minuta hoda"):
        files = {"index.html": NOADDR.replace("</footer>", f"<p>{line}</p></footer>")}
        issues = mod.run_branch(dict(files), list(files), "nwf-x-hr-hr")
        assert issues and "немає адреси" in issues[0]["message"], (line, issues)


def test_hr_geo_base_rows_count_as_address():
    rows = mod._geo_rows("hr-hr")
    assert len(rows) >= 50, len(rows)
    for a in rows:
        files = {"index.html": NOADDR.replace("</footer>", f"<p>{a}</p></footer>")}
        assert mod.run_branch(dict(files), list(files), "nwf-x-hr-hr") == [], a


def test_footer_clone_drops_vue_directives():
    """tvgstadi 26.10: останній <p> футера — `<p v-if="hasWebsite">`; клон з
    тією ж умовою ховав би адресу, а v-text/v-html підмінили б її текст."""
    footer = ('<template><footer><p class="a">© 2026 Tvrđava d.o.o.</p>'
              '<p v-if="hasWebsite" :title="site" class="text-xs">{{ website }}</p>'
              '</footer></template>')
    files = {"src/components/FooterSection.vue": footer}
    out = mod.fix_branch(dict(files), list(files), "nwf-tvgstadi-hr-hr")[0]["content"]
    geo = mod._geo_pick("nwf-tvgstadi-hr-hr")
    assert f'<p class="text-xs">{geo}</p>' in out, out


if __name__ == "__main__":
    run(dict(globals()))
