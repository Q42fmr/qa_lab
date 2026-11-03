"""Адреса: вулиця без номера будинку (кейс QA 01.10).

ТЗ-приклад: «Адрес на /a-empresa не распознан (улица без номера дома:
"Estrada do Contorno, Angra dos Reis RJ 23900-000")». Генератор інколи
кладе адресу без номера — така адреса «не розпізнається» і виглядає
несправжньою.

Парсер шукає адресо-подібні рядки У ТОМУ Ж МІСЦІ, де вони живуть
(контакти, футер, legal, «про компанію»): рядок починається з вуличного
префікса (Rua/Avenida/Estrada/…) і МУСИТЬ містити бразильський CEP
(XXXXX-XXX) — без CEP не судимо, інакше ловили б згадки вулиць у текстах.

Некоректність: до CEP немає номера будинку — ні в сегменті вулиці
(«Rua Jacarandá 651, …»), ні на початку другого сегмента («Rua A, 25,
…»); «s/n» (sem número) — легітимний запис, не чіпаємо.

Автофікс вставляє правдоподібний номер одразу після назви вулиці:
детерміновано від (вітка, вулиця) — повторний фікс дає той самий номер,
різні вітки/вулиці отримують різні. Адресу без жодної коми фікс не
чіпає: межу «вулиця/місто» там не визначити — ручний шлях.

hr-hr (26.10): замість CEP — поштовий індекс із 5 цифр після коми
(«Ulica Petra Krešimira IV, Šibenik, 22000»); «bb» (bez broja) — як «s/n».
"""
import re
import zlib

NAME = "Адреса: вулиця без номера будинку / немає зовсім"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"address"}
PROJECTS = ["php", "node"]
DESCRIPTION = ("Адресо-подібний рядок (вуличний префікс + CEP XXXXX-XXX; hr — "
               "вулиця + індекс) без номера будинку — фікс вставляє "
               "детермінований номер після назви вулиці («s/n»/«bb» не "
               "чіпаються; без ком межа вулиці підтверджується ViaCEP-каскадом "
               "і розбором службових слів). Адреси немає ВЗАГАЛІ — фікс "
               "дублює юридичну, інакше детерміновану з гео-бази "
               "(geo_addresses.json, ключ — локаль вітки; br-pt зібрано з "
               "CNPJ-сіда, решта гео — OSM) рядком у футер, клонуючи <p> зі "
               "стилями без Vue-умов.")
FILES = ["*.html", "*.htm", "*.php", "*.vue"]

# ---------------------------------------------------- гео-база адрес
_GEO_FILE = None            # ліниво: Path до geo_addresses.json
_geo_cache: dict | None = None
# локаль вітки: «…-br-pt», «…-ch-fr»; сапортові вітки бувають з хвостовим
# номером партії — «burnaby….ca-ca-en-2» → ca-en
_LOCALE_RX = re.compile(r"[-.]([a-z]{2}-[a-z]{2})(?:-\d+)?$")
FOOTER_RX = re.compile(r"<footer\b[^>]*>", re.I)
_P_RX = re.compile(r"<p\b[^>]*>.*?</p>", re.S | re.I)
_TAGS_RX = re.compile(r"<[^>]+>")
# футер без жодного <p>: корпус mds-* будує його з <address>/<div>
_ADDRESS_BLOCK_RX = re.compile(r"<address\b[^>]*>.*?</address>", re.S | re.I)


def _locale(branch: str) -> str:
    m = _LOCALE_RX.search((branch or "").strip().lower())
    return m.group(1) if m else ""


def _geo_rows(locale: str) -> list[str]:
    global _geo_cache
    if _geo_cache is None:
        try:
            import json
            from pathlib import Path
            p = Path(__file__).resolve().parent.parent / "geo_addresses.json"
            _geo_cache = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _geo_cache = {}
    rows = _geo_cache.get(locale)
    return rows if isinstance(rows, list) else []


def _geo_pick(branch: str) -> str:
    rows = _geo_rows(_locale(branch))
    if not rows:
        return ""
    return rows[zlib.crc32((branch or "x").encode("utf-8")) % len(rows)]


def _is_hr(branch: str) -> bool:
    return _locale(branch).startswith("hr-")


# ------------------------------------------------------------- hr-hr (26.10)
# QA hr-партії: «Адрес на / не распознан (улица без номера дома: «Ulica Petra
# Krešimira IV, …»)» і «нет адреса» (stit, surjoke, tvgstadi, zastita). Чек
# мовчав: номери судились лише бразильські (CEP), гео-бази hr-hr не було, а
# хорватських форм адреси детект не знав. Їх три: тип вулиці префіксом з
# великої («Ulica Petra Krešimira IV», «Trg bana Jelačića»), суфіксом з малої
# («Trpinjska ulica», «Biljska cesta») і зовсім без нього («Putine 18, 10090
# Zagreb» — цю розпізнає contact_block._bare_addrs). _ANY_STREET_RX («слово
# … будь-яка цифра») для hr заширокий: «Trg je udaljen 5 minuta hoda» — проза.
_HR_WORD = r"(?:Ulica|Ul\.|Trg|Obala|Cesta|Avenija|Šetalište|Prilaz|Aleja|Vijenac)"
_HR_NAME = r"[^\W\d_]+\.?"
_HR_STREET = (rf"(?:{_HR_WORD}(?:[ \t]+{_HR_NAME}){{1,5}}"
              rf"|[A-ZČĆĐŠŽ][^\W\d_]*(?:[ \t]+{_HR_NAME}){{0,3}}"
              rf"[ \t]+(?:ulica|ul\.|cesta|obala))")
# вулиця без номера будинку: перше поле без цифр, кома, далі поштовий індекс
HR_NONUM_RX = re.compile(rf"(?<![\w.-]){_HR_STREET}(?=[ \t]*,)[ \t]*,"
                         rf"[^<>{{}}\n]{{0,80}}?\b\d{{5}}\b")
# адреса на сторінці є: вулиця (з номером чи без), за якою поле, індекс або
# кінець рядка — «Ulica Petra Krešimira IV, …» теж адреса, лише неповна
_HR_PRESENT_RX = re.compile(rf"(?<![\w.-]){_HR_STREET}(?:[ \t]+[1-9]\d{{0,2}}[a-zA-Z]?)?"
                            rf"(?=[ \t]*(?:[,·]|$|\d{{5}}\b))", re.M)


def _hr_address_seen(text: str) -> bool:
    if _HR_PRESENT_RX.search(text):
        return True
    try:
        from checks.contact_block import _bare_addrs
        return bool(_bare_addrs(text))
    except Exception:
        return False


def _hr_legal_address(files: dict) -> str:
    """Канонічна hr-адреса з юридичних сторінок — найповніша серед тих, що
    з тієї самої вулиці (той самий добір, що й у картки контактів)."""
    legal = {p: t for p, t in files.items() if _LEGAL_PATH_RX.search(p)}
    if not legal:
        return ""
    try:
        from checks import contact_block as cb
        return cb._pass_addr(legal, lambda vis: cb._line_addrs(vis) + cb._bare_addrs(vis))
    except Exception:
        return ""


def _footer_paths(files: dict) -> list[str]:
    return sorted(p for p, t in files.items() if FOOTER_RX.search(t))


_VUE_ATTR_RX = re.compile(r"""\s(?:v-[\w:.\[\]-]+|[:@#][\w.\[\]-]+)"""
                          r"""(?:\s*=\s*(?:"[^"]*"|'[^']*'))?""")


_ROW_SKIP_RX = re.compile(r"""\b(?:class|id)\s*=\s*["'][^"']*(?:page-?top|pagetop|to-?top|scroll|back-?to|btn|button|icon|opac)""", re.I)


def _append_footer_line(text: str, content: str) -> str:
    """Клон <p> футера зі стилями + рядок content нижче (та сама механіка,
    що в чеку cnpj); без футера/кандидата — текст як був.

    Другий шлях — футер, зібраний на <address>-блоках без жодного <p>
    (корпус mds-*): рядок лягає перед </address> останнього змістовного
    блока, точно як у geo_phone (кейс epidoc 02.10). Без нього чек обіцяв
    фікс, фікс повертав 0 дій, і помилка не зникала ніколи."""
    if content in text:
        return text
    m = FOOTER_RX.search(text)
    if not m:
        return text
    end = text.lower().find("</footer>", m.end())
    if end < 0:
        return text
    seg = text[m.end():end]
    cand = None
    for b in _P_RX.finditer(seg):
        if not _TAGS_RX.sub("", b.group(0)).strip():
            continue
        # «нагору»/кнопка/іконка — не текстовий рядок футера (caxe-hycoora
        # 28.10: <p class="opac" id="page-top">): клон успадкував би id і стиль
        if _ROW_SKIP_RX.search(b.group(0)[:b.group(0).find(">") + 1]):
            continue
        cand = b
    if cand is not None:
        block = cand.group(0)
        # умови й байндинги Vue не клонуються: `v-if="hasWebsite"` ховав би
        # адресу, v-text/v-html підмінили б її текст (tvgstadi 26.10); id —
        # унікальний, у клон не йде
        open_tag = _VUE_ATTR_RX.sub("", block[:block.find(">") + 1])
        open_tag = re.sub(r'\s+id\s*=\s*(?:"[^"]*"|\'[^\']*\')', "", open_tag)
        clone = f"{open_tag}{content}</p>"
        abs_start = m.end() + cand.start()
        ls = text.rfind("\n", 0, abs_start) + 1
        indent = text[ls:abs_start]
        if indent.strip():
            indent = ""
        nl = "\r\n" if "\r\n" in text else "\n"
        abs_end = m.end() + cand.end()
        return text[:abs_end] + nl + indent + clone + text[abs_end:]
    last_addr = None
    for b in _ADDRESS_BLOCK_RX.finditer(seg):
        if _TAGS_RX.sub("", b.group(0)).strip():
            last_addr = b
    if last_addr is None:
        return text
    ins = m.end() + last_addr.end() - len("</address>")
    return text[:ins] + f"<br>{content}" + text[ins:]


# «адреса присутня» для БУДЬ-ЯКОГО гео: вуличне слово будь-якої з наших
# локалей + число поряд в одному рядку. Навмисно ширше за br-ADDR_RX:
# missing-гілка не має брехати «адреси немає» на mx/it/ch/sg-вайтах
_ANY_STREET_RX = re.compile(
    r"(?<!-)\b(?:Rua|Avenida|Av\.|Alameda|Travessa|Rodovia|Estrada|Pra[çc]a|Largo"
    r"|Calle|Carrera|Cra\.|Cl\.|Diagonal|Transversal|Paseo|Boulevard"
    r"|Via|Viale|Piazza|Piazzale|Corso|Vicolo|Contrada|Frazione|Località|Loc\.|Strada"
    # ch-fr (27.10): «Route de Lausanne 12», «Grand-Rue 5», «Place du Marché 3»,
    # «Faubourg de l'Hôpital 19» — французькі вулиці поза Rue/Chemin/Avenue
    r"|Rue|Grand-Rue|Grand-Place|Ruelle|Chemin|Quai|Impasse|All[ée]e|Promenade|Faubourg"
    r"|Route\s+(?:de|du|des|d')|Place\s+(?:de|du|des|d'|[A-ZÀ-Ý])"
    r"|Strasse|Straße|Gasse|Platz|Weg"
    r"|Jalan|Lorong|Soi"
    r"|Road|Street|St\.|Avenue|Lane|Drive)"
    # межа після слова: «enviada» ховає «via», tailwind-клас «via-black/5»
    # теж не вулиця (фолси 01.10: fotoz-de-cowkernorei мовчав)
    r"(?![a-zà-öø-ÿ-])"
    r"[^<>{}\n]{0,80}\d"
    # німецькі вулиці — суфіксом одним словом: Bahnhofstrasse 1, Marktgasse
    r"|\b[\wÀ-ÿ]+(?:strasse|straße|gasse|platz)\b[^<>{}\n]{0,40}\d"
    # зворотна форма «12 Rue X»: вуличне слово з великої, інакше «remoto via
    # app» (PT «via» = «через») і будь-яке «24 road» у прозі ставали адресою
    r"|\d[^<>{}\n\"'=]{0,40}"
    r"\b(?:Road|Street|Jalan|Rue|Strasse|Straße|Via|Calle)(?![a-zà-öø-ÿ-])",
    re.I)
# адреса БЕЗ номера за законом: італійське SNC / s.n.c. (senza numero civico)
# після вуличного/місцевого слова — peliril-it-it (27.10): «Località Brasoli
# SNC, Le Castella, Isola di Capo Rizzuto (KR)» без цифр взагалі
_SNC_ADDR_RX = re.compile(
    r"\b(?:Via|Viale|Piazza|Piazzale|Corso|Vicolo|Contrada|Frazione|Località|Loc\.|Strada)"
    r"(?![a-zà-öø-ÿ-])[^<>{}\n,]{1,60}\b(?:SNC|s\.n\.c\.?)(?![\w])", re.I)


_WORD_NUM_RX = re.compile(r"^[\wÀ-ÿ.]+\s+(?:n[ºo°]\.?\s*)?\d")


def _any_street(text: str):
    """Перший збіг _ANY_STREET_RX, де вуличне слово пишеться з ВЕЛИКОЇ
    («Rua X», «RUA SAO JOSE», «12 Rue Y») або одразу за ним іде номер
    («lane 1 · Padre Eustáquio», mds-peqo-inwikjepex). Регекс навмисно
    re.I заради all-caps адрес гео-бази, але в прозі «em diagonal: …
    45 graus» (avizpuoplovjitao 19.10) чи «remoto via app 24» вулиці
    немає."""
    for m in _ANY_STREET_RX.finditer(text):
        word = re.search(r"[A-Za-zÀ-ÿ]", m.group(0))
        if word and (word.group(0).isupper() or _WORD_NUM_RX.match(m.group(0))):
            return m
    m = _SNC_ADDR_RX.search(text)
    if m and m.group(0)[0].isupper():
        return m
    return None


# юридичні сторінки: генератор завжди пише там якусь адресу компанії, але
# для QA «адреса на сайті» — це футер/контакти, а не закопане у terms
# (кейс crurpowogre-naneqab 01.10: Rua Rio Branco у TermsContent глушила
# missing, хоча на видимих сторінках адреси не було)
_LEGAL_PATH_RX = re.compile(
    r"terms|privacy|cookie|legal|aviso|politi[ck]|mentions|refund"
    r"|shipping|devolu|juridic", re.I)
# звідки брати КАНОН: юридичні + Impressum/Datenschutz (equipage ch-fr 27.10).
# На «видимість» адреси (_branch_has_address) Impressum не впливає — ch-вайти
# з адресою лише на Impressum не отримують зайвого рядка у футер
_CANON_PATH_RX = re.compile(_LEGAL_PATH_RX.pattern + r"|impressum|imprint|datenschutz|confidentialit", re.I)
# сторінки з реквізитами компанії — перед політиками: текст privacy буває
# шаблонним наповненням з випадковою адресою (equipage ch-fr 27.10 —
# «Rue du Léman 12» ×4 у випадкових абзацах datenschutz проти адреси
# Impressum)
_REQUISITES_PATH_RX = re.compile(r"impressum|imprint|mentions|terms|termini|condi[çct]|aviso|legal", re.I)


_BREAK_RX = re.compile(r"<br\s*/?>|</?(?:p|li|div|h[1-6]|td|tr|address|section|article|ul|ol)\b[^>]*>", re.I)
_HIDDEN_RX = re.compile(r"<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->", re.I | re.S)


def _legal_address(files: dict, branch: str = "") -> str:
    """Адресний рядок з юридичних сторінок — КАНОНІЧНА адреса сайту.

    Коли на видимих сторінках адреси немає, а в terms/privacy вона є —
    фікс ДУБЛЮЄ її у футер (прохання 01.10), а не вигадує з гео-бази:
    юридична вже узгоджена з рештою реквізитів."""
    for p in sorted(files, key=lambda q: (not _REQUISITES_PATH_RX.search(q), q)):
        if not _CANON_PATH_RX.search(p):
            continue
        # видимий текст рядками: \n, <br> і межі блокових тегів — переноси;
        # атрибути (meta description з адресою — trehu 27.10) і скрипти
        # не рахуються; перший збіг у файлі може бути не адресою — дивимось усі
        vis = _TAGS_RX.sub(" ", _BREAK_RX.sub("\n", _HIDDEN_RX.sub(" ", files[p])))
        for line in vis.split("\n"):
            m = ADDR_RX.search(line) or _any_street(line)
            if not m:
                continue
            clean = " ".join(line.split()).strip(" .;")
            clean = re.sub(r"^(?:endere[çc]o(?:\s+f[ií]sico)?|direcci[oó]n"
                           r"|address|morada|sede|adresse|indirizzo)\s*:\s*",
                           "", clean, flags=re.I)
            if "{{" in clean or "{" in clean or len(clean) > 140:
                continue
            if clean and any(ch.isdigit() for ch in clean):
                return clean
    # hr: адреса юридичних сторінок буває без вуличного слова чи без номера
    # («Kapucinska 12, Osijek, …», «Ulica Petra Krešimira IV, Šibenik, …») —
    # з гео-базою hr-hr інакше у футер ішла б вигадана адреса замість неї
    return _hr_legal_address(files) if _is_hr(branch) else ""


def _branch_has_address(files: dict, branch: str = "") -> bool:
    """Адреса присутня: вуличний патерн АБО рядок гео-бази локалі вітки —
    на НЕюридичних сторінках.

    Гео-умова — узгодження з фіксом: ar-es адреси пишуться БЕЗ слова
    вулиці («Larrea 1269, Buenos Aires, C1117»), і доданий фіксом рядок
    інакше не розпізнавався — чек кричав вічно, а фікс чесно відповідав
    «вже є» (кейс eskufoo-juhuhugo 01.10)."""
    visible = {p: t for p, t in files.items()
               if not _LEGAL_PATH_RX.search(p)}
    # лише видимий текст: alt="WEG"/класи/base64 в атрибутах не адреса
    # (avizpuoplovjitao 19.10: «Weg» з alt логотипа WEG глушив «адреси
    # немає зовсім», і fale-conosco лишався без адреси)
    if any(ADDR_RX.search(_TAGS_RX.sub(" ", t))
           or _any_street(_TAGS_RX.sub(" ", t))
           or (_is_hr(branch) and _hr_address_seen(_TAGS_RX.sub(" ", t)))
           for t in visible.values()):
        return True
    big = "\n".join(visible.values())
    la = _legal_address(files, branch)
    if la and la in big:
        return True          # продубльована з юридичної — вже на місці
    if not branch:
        return False
    rows = _geo_rows(_locale(branch))
    if not rows:
        return False
    return any(r in big for r in rows)

_STREET = (r"(?:Rua|Avenida|Av\.|Alameda|Travessa|Rodovia|Rod\.|Estrada"
           r"|Pra[çc]a|Largo|Via)")
# адресний рядок: вуличний префікс … CEP, без тегів/шаблонних дужок усередині.
# CEP — рівно 5-3 цифр: «98047-5613» мобільного номера містить «98047-561»
# (arikejabgag 28.10: «Rua das Orquídeas, Fortaleza … +55 85 98047-5613»)
_CEP = r"(?<![\d-])\d{5}-\d{3}(?![\d-])"
ADDR_RX = re.compile(_STREET + r"\b[^<>{}\n]{0,110}?" + _CEP, re.I)
CEP_RX = re.compile(_CEP)
SN_RX = re.compile(r"\bs/n\b", re.I)
# номер на початку сегмента: «25», «nº 25», «no 25», «25-B»
_NUM_HEAD_RX = re.compile(r"(?:n[ºo°]\s*)?\d", re.I)
_UF_CEP_RX = re.compile(r"\b([A-Z]{2})[\s,]+" + _CEP)
# службові слова всередині назв (Angra DOS Reis, Praia DO Rosa)
_SERVICE = {"de", "do", "da", "dos", "das", "e"}
# роздільники сегментів адреси: кома АБО крапка-роздільник « · » (кейс
# padohvae-da-proou 01.10: «Estrada do Contorno · Angra dos Reis · RJ …»)
_SEG_RX = re.compile(r",|\s[·•|]\s")


def _segments(core: str) -> list[str]:
    return [p.strip() for p in _SEG_RX.split(core)]


# --------------------------------------------- підтвердження межі вулиці
# (commaless-адреси). Мережа — ViaCEP, без ключа; кеш на процес, таймаут
# 4 с, будь-який збій каскаду = «не підтверджено» (ручний випадок).
_NET_CACHE: dict = {}
# Бюджет мережі НА ОДИН прогін (run або fix): без нього вітка з багатьма
# адресами множила 4-секундні таймаути і «рахую автофікси…» висіло
# хвилинами (02.10, auduatjinxofoqe: 6 адрес × каскад). Вичерпаний бюджет
# чи мертвий хост = «не підтверджено» — рядок чесно лишається ручним.
_NET = {"left": 0, "fails": 0}
_NET_LIMIT = 8


def _net_reset():
    _NET["left"] = _NET_LIMIT
    _NET["fails"] = 0


def _http_json(url: str):
    if url in _NET_CACHE:
        return _NET_CACHE[url]
    if _NET["left"] <= 0 or _NET["fails"] >= 2:
        return None                  # бюджет/хост вмер: БЕЗ кешування None
    _NET["left"] -= 1
    out = None
    try:
        import json
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "qa_lab"})
        with urllib.request.urlopen(req, timeout=4) as r:
            out = json.loads(r.read())
        _NET["fails"] = 0
    except Exception:
        _NET["fails"] += 1
        return None                  # збій теж не кешуємо: інший прогін спробує
    _NET_CACHE[url] = out
    return out


def _viacep(cep: str):
    d = re.sub(r"\D", "", cep)
    return _http_json(f"https://viacep.com.br/ws/{d}/json/")


def _viastreet(uf: str, city: str, street: str):
    import urllib.parse
    q = urllib.parse.quote
    return _http_json(f"https://viacep.com.br/ws/{q(uf)}/{q(city)}/"
                      f"{q(street)}/json/")


def _norm(s: str) -> str:
    """Та сама довжина, без діакритики й регістру — щоб індекси збігались."""
    import unicodedata
    out = []
    for ch in s:
        d = unicodedata.normalize("NFKD", ch)
        out.append(d[0].lower() if d else ch.lower())
    return "".join(out)


def _find_norm(hay: str, needle: str) -> int:
    """Індекс needle у hay без регістру/діакритики; -1 — немає."""
    n = _norm(needle).strip()
    return _norm(hay).find(n) if n else -1


def _uf_split(tokens: list[str]) -> int | None:
    """Безмережева межа: місто = суфікс токенів за службовими словами.

    Приймаємо ЛИШЕ міста зі службовим словом усередині («Angra DOS Reis»,
    «Praia DO Rosa») — воно однозначно групує назву. Місто без службових
    («Imbituba», «Belo Horizonte») так не відрізнити від хвоста вулиці —
    відмовляємось (None): хай підтверджує реєстр."""
    i = len(tokens) - 1
    if i < 1:
        return None
    i -= 1                                       # останнє слово — місто
    while i > 0 and tokens[i].lower() in _SERVICE:
        i -= 2                                   # службове + його слово
    city_tokens = tokens[i + 1:]
    if not city_tokens or i < 1:
        return None
    if not any(t.lower() in _SERVICE for t in city_tokens):
        return None                              # без службових — не беремось
    if tokens[i].lower() in _SERVICE:
        return None                              # вулиця не кінчається службовим
    return i + 1                                 # індекс першого слова міста


def resolve_commaless(addr: str) -> int | None:
    """Кінець назви вулиці в commaless-адресі; None — не підтверджено.

    Каскад (ідея 01.10: «бери частину, шукай вулицю, підтверджуй»):
      1. точковий CEP → logradouro з реєстру знайдено в рядку;
      2. CEP → localidade (місто) знайдено в рядку — вулиця все до нього;
      3. пошук вулиці /ws/UF/місто/вулиця по розбиттях (місто 1..4 слова
         з хвоста) — реєстр підтверджує кандидата;
      4. UF-евристика службових слів (без мережі)."""
    cep_m = CEP_RX.search(addr)
    if not cep_m:
        return None
    core = addr[:cep_m.start()]
    uf_m = _UF_CEP_RX.search(addr)
    if uf_m:
        core = addr[:uf_m.start(1)]
    data = _viacep(cep_m.group(0)) or {}
    logr = (data.get("logradouro") or "").strip()
    if logr:
        i = _find_norm(addr, logr)
        if i == 0:
            return len(logr)                      # 1) вулиця з реєстру
    city = (data.get("localidade") or "").strip()
    if city:
        i = _find_norm(core, city)
        if i > 0:
            return i                              # 2) місто з реєстру
    tokens = core.split()
    uf = uf_m.group(1) if uf_m else (data.get("uf") or "")
    if uf and len(tokens) >= 3:
        for ncity in (1, 2, 3, 4):                # 3) пошук вулиці по розбиттях
            if ncity >= len(tokens):
                break
            street_c = " ".join(tokens[:-ncity])
            city_c = " ".join(tokens[-ncity:])
            if len(street_c) < 4 or city_c.split()[0].lower() in _SERVICE:
                continue
            hits = _viastreet(uf, city_c, street_c)
            if isinstance(hits, list) and hits and isinstance(hits[0], dict):
                found = (hits[0].get("logradouro") or "")
                if _find_norm(found, street_c) >= 0 \
                        or _find_norm(street_c, found) >= 0:
                    return len(street_c)
    split = _uf_split(tokens) if uf_m else None   # 4) службові слова
    if split is not None:
        return len(" ".join(tokens[:split]))
    return None


def _missing_number(addr: str) -> bool:
    """Чи в адресі немає номера будинку (до CEP)."""
    if SN_RX.search(addr):
        return False
    cep = CEP_RX.search(addr)
    core = addr[:cep.start()] if cep else addr
    parts = _segments(core)
    if re.search(r"\d", parts[0]):
        return False                     # «Rua Jacarandá 651, …»
    if len(parts) > 1 and _NUM_HEAD_RX.match(parts[1]):
        return False                     # «Rua A, 25, …» / «Rua X · 25 · …»
    return True


def parse(text: str, hr: bool = False) -> list[dict]:
    """Адресо-подібні рядки файла: [{addr, start, end, street, ok, fixable}].

    fixable=False — межу вулиці не визначити (жодної коми до CEP): фікс
    не вгадує, де закінчується вулиця і починається місто. hr=True —
    додатково hr-адреси з індексом, де перше поле — вулиця без номера."""
    out = []
    for m in ADDR_RX.finditer(text):
        addr = m.group(0)
        cep = CEP_RX.search(addr)
        core = addr[:cep.start()] if cep else addr
        street = _segments(core)[0]
        out.append({"addr": addr, "start": m.start(), "end": m.end(),
                    "street": street, "ok": not _missing_number(addr),
                    "fixable": bool(_SEG_RX.search(core))})
    if hr:
        for m in HR_NONUM_RX.finditer(text):
            addr = m.group(0)
            out.append({"addr": addr, "start": m.start(), "end": m.end(),
                        "street": _segments(addr)[0],
                        "ok": not _hr_missing_number(addr), "fixable": True})
    return out


def _hr_missing_number(addr: str) -> bool:
    """hr-адреса без номера будинку. «Ulica X, 25, 10000 Zagreb» — номер
    другим полем; «Ulica X, 10000 Zagreb» — п'ять цифр там індекс, не номер
    (бразильське правило «номер у 2-му сегменті» тут хибило б); «bb» (bez
    broja) — хорватське «s/n», легітимне."""
    parts = _segments(addr)
    if re.search(r"\d", parts[0]) or re.search(r"\bbb\b", parts[0]):
        return False
    return not (len(parts) > 1 and re.fullmatch(r"\d{1,3}[a-zA-Z]?", parts[1]))


def _number_for(branch: str, street: str) -> int:
    """Правдоподібний номер будинку: 100–999, стабільний для (вітка, вулиця)."""
    return 100 + zlib.crc32(f"{branch}|{street}".encode("utf-8")) % 900


def _plan(rec: dict) -> tuple[str, str] | None:
    """(street, rest) для фікса; None — межа не підтверджена.

    З комою street відомий з parse; commaless — через resolve_commaless."""
    if rec["fixable"]:
        street = rec["street"]
        return street, rec["addr"][len(street):]
    end = resolve_commaless(rec["addr"])
    if end is None:
        return None
    street = rec["addr"][:end].rstrip().rstrip(",")
    rest = rec["addr"][end:].lstrip()
    return street, ", " + rest                   # канонізуємо: кома після номера


def _norm_addr(s: str) -> str:
    return re.sub(r"[^0-9a-zà-öø-ÿ]+", "", s.lower())


# Адреси живуть у видимому тексті; гігантські інлайн <script>/<style>
# (каталоги e-commerce по 400 КБ) ганяли вуличні регекси вхолосту —
# 771 сторінка serralheria коштувала 6 хв CPU і прогін вітки не влазив
# у ліміт пулу (02.10). Сегменти зберігають глобальні offset-и, тож
# фікси ріжуть сирий текст як і раніше.
_SKIP_BLOCK_RX = re.compile(r"<script\b.*?</script\s*>|<style\b.*?</style\s*>",
                            re.I | re.S)


def _visible_segments(t: str):
    pos = 0
    for m in _SKIP_BLOCK_RX.finditer(t):
        if m.start() > pos:
            yield pos, t[pos:m.start()]
        pos = m.end()
    if pos < len(t):
        yield pos, t[pos:]


# індекс (CEP / CAP / PLZ / HR / UK-like) усередині спану — лише з ним спан
# є повною адресою, яку безпечно переписувати; після індексу — місто.
# Група цифр телефону — не індекс: «98047-5613», «3876-0064» (4-5 цифр, за
# якими ще «-цифри»), «+55 85 98047» (arikejabgag 28.10: дві фрази FAQ з тією
# самою вулицею й телефоном читались як «дві різні адреси» для зводу)
_POSTCODE_RX = re.compile(r"(?<![+\d])(?<!\d-)\b\d{4,5}(?:-\d{3})?\b(?![-\d])"
                          r"(?<!\+\d\d \d\d \d{5})(?<!\+\d\d \d\d \d{4})")
_CITY_TAIL_RX = re.compile(r"[ \t]+[A-ZÀ-Ý][^,;.|·<>\n\"]{0,40}?(?=\s*(?:[,;.|·<\n\"]|$))")


def _address_spans(files: dict):
    """[(path, start, end, shown)] адресних входжень на видимих сторінках.

    ADDR_RX і _ANY_STREET_RX часто матчать ТУ САМУ адресу з різними межами —
    перекривні спани зливаються у найширший, інакше звід замінював би те
    саме місце двічі (CI-фейл 02.10).

    Спан мусить починатися з великої літери чи цифри: звід ПЕРЕПИСУЄ текст,
    а «nível da rua. Num lote com 1,50» (блог argeehiheoqapi) чи «lane = 0»
    (JS peqo-inwikjepex) — загальні іменники, не адреса. Адреса з малої
    літери просто не зводиться — помилка в безпечний бік.

    isacubo-it-it (27.10): спан _ANY_STREET_RX кінчався на ОСТАННІЙ цифрі в
    80 знаках — на індексі («Via della Spiga 46, 20121»), і звід лишав місто
    старої адреси («…91025 Milano»), або тягнувся крізь речення до телефону
    і зрізав його. Тепер спан — до індексу й міста включно і обрізається на
    розділовому знаку; %-кодований текст (query мапи) і вміст атрибутів —
    не спан."""
    out = []
    for p in sorted(files):
        if _LEGAL_PATH_RX.search(p):
            continue
        t = files[p]
        raw = []
        for off, seg in _visible_segments(t):
            for rx in (ADDR_RX, _ANY_STREET_RX):
                for m in rx.finditer(seg):
                    g = m.group(0)
                    if not (g[0].isupper() or g[0].isdigit()):
                        continue
                    # звід ПЕРЕПИСУЄ спан, тож він мусить лежати в одному
                    # текстовому вузлі: «06.jpg" alt="Controle remoto via»
                    # (nwf-lente 16.10) — це src+alt картинки, зворотна
                    # форма «число … via» пройшла крізь атрибути і звід
                    # переписав ім'я файла на адресу
                    if '"' in g or "'" in g or "=" in g or "(" in g or ")" in g or "%" in g:
                        continue
                    # усередині тега (атрибут, URL) — не видимий текст
                    lt, gt = seg.rfind("<", 0, m.start()), seg.rfind(">", 0, m.start())
                    if lt > gt:
                        continue
                    # зворотна форма «число … Rue»: число з крапковими групами
                    # (UID CHE-128.456.790, CNPJ, IP) — не номер будинку
                    if g[0].isdigit() and re.match(r"\d{1,3}(?:\.\d{3}){2,}", g):
                        continue
                    s, e = m.start(), m.end()
                    if rx is _ANY_STREET_RX:
                        # до індексу (перший у спані) і міста за ним; без
                        # індексу спан — фрагмент прози, не адреса для зводу
                        pm = _POSTCODE_RX.search(seg, s, e + 1)
                        if not pm or pm.start() > e:
                            continue
                        e = pm.end()
                        cm = _CITY_TAIL_RX.match(seg, e)
                        if cm:
                            e = cm.end()
                    raw.append((off + s, off + e))
        raw.sort()
        merged: list[list[int]] = []
        for s, e in raw:
            if merged and s < merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
                continue
            merged.append([s, e])
        for s, e in merged:
            shown = " ".join(t[s:e].split())
            out.append((p, s, e, shown))
    return out


_UF_NEAR_RX = re.compile(
    r"(?:^|[\s,/–—-])(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)"
    r"(?=$|[\s,.;:)]|\d)")


def _uf_near(text: str, s: int, e: int) -> str:
    """UF адреси: у самому спані або в найближчому видимому тексті після нього
    («Av. Ibirapuera, 2033 Moema <br/> - São Paulo - SP»)."""
    tail = _TAGS_RX.sub(" ", text[s:e + 160])
    m = _UF_NEAR_RX.search(tail)
    return m.group(1) if m else ""


def _office_norms(files: dict, spans) -> set:
    """Адреси-ОФІСИ: на одній сторінці стоять ≥2 різні адреси з різними UF
    (ib-cytis 21.10: футер «São Paulo / Curitiba / Brasília»). Це не суперечність
    генератора, а список філій — зводити їх до однієї не можна (20.10 автофікс
    переписав офісу в Сан-Паулу вулицю курітібського)."""
    by_page: dict = {}
    for p, s, e, shown in spans:
        uf = _uf_near(files[p], s, e)
        if uf:
            by_page.setdefault(p, {}).setdefault(_norm_addr(shown), set()).add(uf)
    offices = set()
    for addrs in by_page.values():
        ufs = {u for us in addrs.values() for u in us}
        if len(addrs) >= 2 and len(ufs) >= 2:
            offices |= set(addrs)
    return offices


def _distinct_addresses(files: dict, spans=None):
    """(канон, [(норм, показ)]) — різні адреси вітки; канон: юридична,
    інакше найчастіша (02.10: «дві різні адреси — лишати одну»). Адреси
    філій (_office_norms) у звід не беруться."""
    if spans is None:
        spans = _address_spans(files)
    from collections import Counter
    offices = _office_norms(files, spans)
    spans = [sp for sp in spans if _norm_addr(sp[3]) not in offices]
    cnt = Counter(_norm_addr(s) for *_, s in spans)
    shown_by = {}
    for *_, s in spans:
        shown_by.setdefault(_norm_addr(s), s)
    # коротший запис тієї самої адреси (без міста: «…14, 95062, a Motta
    # Sant'Anastasia» у прозі, naekune 27.10) — не друга адреса: злиття в
    # довший варіант, якого він є префіксом
    for n in sorted(cnt, key=len):
        longer = [m for m in cnt if m != n and m.startswith(n)]
        if longer and cnt[n]:
            cnt[max(longer, key=lambda m: (cnt[m], m))] += cnt.pop(n)
    uniq = [(n, shown_by[n]) for n in cnt]
    if len(uniq) < 2:
        return "", []
    legal = _legal_address(files)
    ln = _norm_addr(legal) if legal else ""
    if ln and ln in cnt:
        canon = legal
    elif ln and any(ln.startswith(n) for n in cnt):
        # юридичний рядок з хвостом («Av. de la Gare 66, 1904 Martigny,
        # Suisse») — канон у записі видимих сторінок
        canon = shown_by[max((n for n in cnt if ln.startswith(n)), key=len)]
    else:
        canon = shown_by[max(cnt, key=lambda n: (cnt[n], n))]
    return canon, uniq


def run_branch(files, all_paths, branch: str = ""):
    _net_reset()
    issues = []
    # адреси немає ВЗАГАЛІ: судимо лише локалі, для яких гео-база непорожня
    if files and not _branch_has_address(files, branch):
        legal = _legal_address(files, branch)
        geo = legal or _geo_pick(branch)
        feet = [p for p in _footer_paths(files)
                if not _LEGAL_PATH_RX.search(p)]
        if geo and feet:
            # обіцяємо рівно те, що фікс справді зробить. Інакше помилка
            # висить вічно: чек каже «фікс додасть», fix_branch повертає
            # 0 дій, і наступний прогін рапортує те саме (кейс mds-* 03.10)
            doable = [p for p in feet
                      if _append_footer_line(files[p], geo) != files[p]]
            if doable:
                src = ("продублює адресу з юридичної сторінки"
                       if legal else f"додасть з гео-бази ({_locale(branch)})")
                msg = (f"на видимих сторінках немає адреси — фікс {src}: "
                       f"«{geo}» рядком у футер у стилях вітки")
            else:
                msg = (f"на видимих сторінках немає адреси, а у футер її "
                       f"нема куди покласти (ні <p>, ні <address>) — "
                       f"додай руками: «{geo}»")
            issues.append({"path": (doable or feet)[0], "line": 1,
                           "severity": "error", "message": msg})
        return issues
    for path in sorted(files):
        text = files[path]
        for rec in parse(text, hr=_is_hr(branch)):
            if rec["ok"]:
                continue
            line = text.count("\n", 0, rec["start"]) + 1
            plan = _plan(rec)
            if plan:
                street = plan[0]
                src = "" if rec["fixable"] else \
                    " (межу вулиці підтверджено CEP-реєстром/розбором)"
                tail = (f"фікс вставить «{street} "
                        f"{_number_for(branch, street)} …»{src}")
            else:
                tail = ("де закінчується вулиця — не підтвердилось ні "
                        "CEP-реєстром, ні розбором (немає ком) — додай "
                        "номер руками")
            issues.append({"path": path, "line": line, "severity": "error",
                           "message": (f"вулиця без номера будинку: "
                                       f"«{rec['addr']}» — адреса не "
                                       f"розпізнається; {tail}")})
    if not issues:
        # номери чисті — тепер звід різних адрес до однієї (02.10);
        # інакше повідомлення плутали б два різні фікси
        sp = _address_spans(files)
        canon, uniq = _distinct_addresses(files, sp)
        if canon:
            others = [s for n, s in uniq
                      if _norm_addr(s) != _norm_addr(canon)]
            first = next(((p, st) for p, st, _e, s in sp
                          if _norm_addr(s) != _norm_addr(canon)), None)
            path0, at = first if first else (sorted(files)[0], 0)
            issues.append({"path": path0,
                           "line": files[path0].count("\n", 0, at) + 1,
                           "severity": "error",
                           "message": (f"на вітці {len(uniq)} різні адреси "
                                       f"({'; '.join('«'+s+'»' for s in others[:2])}"
                                       f") — фікс зведе всі до «{canon}»")})
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    # лише FILES, як бачить детект: раннер дає fix_branch УСІ текстові файли,
    # а «lane = 0» у JS для звіду — ще одна «адреса» (кейс peqo-inwikjepex)
    files = {p: t for p, t in files.items()
             if p.lower().endswith((".html", ".htm", ".php", ".vue"))}
    _net_reset()
    actions = []
    if files and not _branch_has_address(files, branch):
        geo = _legal_address(files, branch) or _geo_pick(branch)
        if not geo:
            return []
        for path in (p for p in _footer_paths(files)
                     if not _LEGAL_PATH_RX.search(p)):
            new = _append_footer_line(files[path], geo)
            if new != files[path]:
                actions.append({"type": "edit", "path": path, "content": new})
        return actions
    for path in sorted(files):
        text = files[path]
        todo = []
        for rec in parse(text, hr=_is_hr(branch)):
            if rec["ok"]:
                continue
            plan = _plan(rec)
            if plan:
                todo.append((rec, plan))
        if not todo:
            continue
        new = text
        for rec, (street, rest) in sorted(todo, key=lambda t: -t[0]["start"]):
            fixed = street + f" {_number_for(branch, street)}" + rest
            new = new[:rec["start"]] + fixed + new[rec["end"]:]
        if new != text:
            actions.append({"type": "edit", "path": path, "content": new})
    if not actions:
        # номери чисті — звід різних адрес до однієї (02.10)
        all_sp = _address_spans(files)
        canon, uniq = _distinct_addresses(files, all_sp)
        if canon:
            offices = _office_norms(files, all_sp)        # філії не чіпаємо
            for path in sorted({p for p, *_ in all_sp}):
                text = files[path]
                spans = [(st, e, s) for p, st, e, s in all_sp
                         if p == path and _norm_addr(s) != _norm_addr(canon)
                         and not _norm_addr(canon).startswith(_norm_addr(s))
                         and _norm_addr(s) not in offices]
                if not spans:
                    continue
                new = text
                for st, e, _s in sorted(spans, key=lambda x: -x[0]):
                    cut = _redundant_element(new, st, e, canon)
                    if cut:
                        new = new[:cut[0]] + new[cut[1]:]
                    else:
                        new = new[:st] + canon + new[e:]
                if new != text:
                    actions.append({"type": "edit", "path": path,
                                    "content": new})
    return actions


_ELEM_RX = re.compile(r"<(p|li|span|div|address)\b[^>]*>\s*$", re.I)


def _redundant_element(text: str, st: int, e: int, canon: str):
    """Спан — увесь текст елемента, а сусідній елемент (попередній чи
    наступний) уже несе канон → повертає (start, end) елемента з
    відступом перед ним для вирізання; інакше None. Кейс isacubo 27.10:
    гео-рядок, доклеєний старим кодом під юридичною адресою."""
    om = _ELEM_RX.search(text, max(0, st - 160), st)
    if not om:
        return None
    tag = om.group(1)
    cm = re.compile(rf"\s*</{tag}\s*>", re.I).match(text, e)
    if not cm:
        return None
    el_start, el_end = om.start(), cm.end()
    canon_n = _norm_addr(canon)
    before = text[max(0, el_start - 400):el_start]
    after = text[el_end:el_end + 400]
    prev_el = re.search(rf"<{tag}\b[^>]*>([^<]*)</{tag}\s*>\s*$", before, re.I)
    next_el = re.match(rf"\s*<{tag}\b[^>]*>([^<]*)</{tag}\s*>", after, re.I)
    if not any(x and _norm_addr(x.group(1)) == canon_n for x in (prev_el, next_el)):
        return None
    ws = re.search(r"\s*$", text[:el_start])          # відступ/перенос перед елементом
    return ws.start(), el_end
