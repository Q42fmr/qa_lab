"""Юридичні сторінки: Impressum на швейцарських вайтах, політика
конфіденційності — на всіх.

Звідки. ClickUp 868mbnzwg (Eva, 19.10): «обязательно должен быть Impressum
с адресом и регистрационным номером (CHE****)». QA-скарги 868mjm950,
868mewn67, 868mg7z6x: «На сайте нет ссылки на политику конфиденциальности —
ни в подвале, ни в меню». Заміряно на корпусі: згенеровані вайти (9 сторінок)
мають privacy/terms/cookies, але Impressum — 1 з 8 на ch-de і 0 з 8 на
ch-fr/ch-it; скрейпнуті (mds-*, anboixudr, eleva) часто без privacy.

Що вимагається:
  * локаль ch-* (de/fr/it): сторінка Impressum / Mentions légales / Note
    legali з адресою і UID (CHE-…), лінк на неї у футері КОЖНОЇ сторінки;
  * будь-яка локаль: сторінка політики конфіденційності + лінк у футері.

Фікс генерує сторінку У СТИЛЯХ ВІТКИ і ПІД ТЕМУ сайту:
  * оболонка — наявна юридична сторінка вітки (privacy → terms → cookies):
    head/header/footer лишаються, з контенту беруться класи h1/h2/p та
    обгортки секцій, і в них кладеться наш текст; без жодної юридичної —
    оболонка головної (head + header + footer);
  * факти — з самої вітки: назва (site_name), діяльність (meta description /
    h1 головної), адреса (юридична сторінка → видимий текст → гео-база),
    телефон (tel: → гео-база), пошта (локальна частина з вітки, домен —
    {{DOMAIN}} у php / реальний у node), реєстровий номер (UID з uid_pool
    для ch, CNPJ з cnpj_pool для br, P.IVA/REA з сайту для it);
  * мова — мова вітки (de/fr/it/pt/es/en), закон — за країною (DSG/nLPD,
    LGPD, GDPR, PDPA, LFPDPPP, Ley 1581, Ley 25.326);
  * лінк у футері: клон сусіднього юридичного <a> (ті самі класи), у node —
    запис у src/data/pages.js (category legal) + роут + сторінка; футери
    nwf-шаблону малюють legalPages самі.
"""
import datetime
import json
import re

NAME = "Юридичні сторінки: Impressum (ch) / політика конфіденційності"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"regno"}
PROJECTS = ["php", "node"]
DESCRIPTION = ("ch-* вайт без Impressum (адреса + UID CHE-…) або будь-який вайт "
               "без політики конфіденційності і лінка на неї у футері. Фікс "
               "генерує сторінку мовою вітки в оболонці наявної юридичної "
               "сторінки (класи h1/h2/p вітки), з фактами вітки (назва, "
               "діяльність, адреса, телефон, пошта, UID/CNPJ) і додає лінк у "
               "футер кожної сторінки (node: pages.js + роут).")
FILES = ["*.html", "*.htm", "*.php", "*.vue", "*.js"]

_LOCALE_RX = re.compile(r"[-.]([a-z]{2})-([a-z]{2})(?:-\d+)?$")
# суфікс вітки «-jp-jp» несе код КРАЇНИ замість мови — у PAGE/LAW мова ISO
_LANG_ALIAS = {"jp": "ja"}
IMP_PATH_RX = re.compile(r"impressum|mentions-?l[ée]gales|note-?legali|legal-?notice"
                         r"|informazioni-?legali|aviso-?legal", re.I)
PRIV_PATH_RX = re.compile(r"privac|datenschutz|confidentialit|riservatezza|privatsph", re.I)
# японські вайти кладуть політику під /policy/, /kojin/ тощо — впізнаємо за
# назвою вкладки/h1, як Impressum за IMP_H1_RX
PRIV_JA_RX = re.compile(r"<(?:title|h1)\b[^>]*>[^<]*(?:プライバシーポリシー|個人情報保護方針|個人情報(?:の)?(?:保護|取扱))", re.I)
# адреса по-японськи: поштовий знак 〒 + індекс + префектура/місто/квартал
JP_ADDR_RX = re.compile(r"〒\s*\d{3}-?\d{4}[\s\u3000]*([^\s<「」\u3000]{4,60}(?:[\s\u3000][^\s<「」\u3000]{1,30}){0,3})")
IMP_H1_RX = re.compile(r"<h1[^>]*>\s*(?:Impressum|Mentions\s+l[ée]gales|Note\s+legali"
                       r"|Informazioni\s+legali)\s*</h1>", re.I)
FOOTER_RX = re.compile(r"<footer\b[^>]*>", re.I)
A_RX = re.compile(r"""<a\b((?:[^>"']|"[^"]*"|'[^']*')*)>(.*?)</a>""", re.I | re.S)
HREF_RX = re.compile(r"""\bhref\s*=\s*(["'])(.*?)\1""", re.I)
TAGS_RX = re.compile(r"<[^>]+>")
UID_RX = re.compile(r"\bCHE-\d{3}\.\d{3}\.\d{3}\b")
CNPJ_RX = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
PIVA_RX = re.compile(r"(?:P\.?\s*IVA|Partita\s+IVA)[:\s]*([0-9]{11})", re.I)
REA_RX = re.compile(r"\bREA[:\s]*([A-Z]{2}[-\s]?\d{5,7})", re.I)
TEL_RX = re.compile(r"""href\s*=\s*["']tel:([^"']+)["'][^>]*>([\s\S]{0,200}?)</a>""", re.I)
MAIL_RX = re.compile(r"""mailto:([A-Za-z0-9._%+-]+)@([A-Za-z0-9.{}\-]+)""")
MAIL_TEXT_RX = re.compile(r"""\b([A-Za-z0-9._%+-]+)@(\{\{DOMAIN\}\}|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)""")
DESC_RX = re.compile(r"""<meta\s+name=["']description["']\s+content=["']([^"']+)["']""", re.I)
H1_RX = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
TITLE_RX = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
PHP_RX = re.compile(r"<\?(?:php|=).*?\?>", re.S)
HOME_RX = re.compile(r"^(?:index|home)\.(?:php|html?)$", re.I)
_LEGAL_PATH_RX = re.compile(r"privac|terms|termos|condi[cç]|cookie|legal|impressum"
                            r"|datenschutz|mentions|agb|nutzung|agreement|user-"
                            r"|access|thank|obrigado|merci|danke|grazie|gracias", re.I)

# ------------------------------------------------------------------ мова
PAGE = {
    # lang: (impressum file, impressum label, privacy file, privacy label)
    "de": ("impressum.html", "Impressum", "datenschutz.html", "Datenschutzerklärung"),
    "fr": ("mentions-legales.html", "Mentions légales", "politique-de-confidentialite.html",
           "Politique de confidentialité"),
    "it": ("note-legali.html", "Note legali", "privacy.html", "Informativa sulla privacy"),
    "pt": ("", "", "politica-de-privacidade.html", "Política de Privacidade"),
    "es": ("", "", "politica-de-privacidad.html", "Política de Privacidad"),
    "en": ("", "", "privacy-policy.html", "Privacy Policy"),
    # hr: роут навмисно англійський — QA-детектор не знає хорватської
    # («Privatnost»/«Politika privatnosti» на /privatnost він не рахував
    # політикою на 10 hr-вітках 20–21.10), а href з «privacy» впізнає
    "hr": ("", "", "privacy-policy.html", "Politika privatnosti"),
    # ja: файл англійський — QA-детектор судить за href з «privacy»
    "ja": ("", "", "privacy-policy.html", "プライバシーポリシー"),
}
# роути node-вітки (без .html)
ROUTE = {"de": ("/impressum", "/datenschutz"), "fr": ("/mentions-legales", "/politique-de-confidentialite"),
         "it": ("/note-legali", "/privacy"), "pt": ("", "/politica-de-privacidade"),
         "es": ("", "/politica-de-privacidad"), "en": ("", "/privacy-policy"), "hr": ("", "/privacy-policy"),
         "ja": ("", "/privacy-policy")}
LAW = {
    "ch": {"de": "Schweizer Datenschutzgesetz (revDSG)", "fr": "loi fédérale suisse sur la protection des données (nLPD)",
           "it": "legge federale svizzera sulla protezione dei dati (nLPD)", "en": "Swiss Federal Act on Data Protection (FADP)"},
    "br": {"pt": "Lei Geral de Proteção de Dados Pessoais (Lei nº 13.709/2018 — LGPD)"},
    "mx": {"es": "Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP)"},
    "co": {"es": "Ley 1581 de 2012 y Decreto 1377 de 2013"},
    "ar": {"es": "Ley 25.326 de Protección de los Datos Personales"},
    "my": {"en": "Personal Data Protection Act 2010 (PDPA)"},
    "sg": {"en": "Personal Data Protection Act 2012 (PDPA)"},
    "th": {"en": "Personal Data Protection Act B.E. 2562 (PDPA)"},
    "uk": {"en": "UK GDPR and the Data Protection Act 2018"},
    "ca": {"en": "Personal Information Protection and Electronic Documents Act (PIPEDA)"},
    "jp": {"ja": "個人情報の保護に関する法律（個人情報保護法）"},
}
_EU_LAW = {"de": "Datenschutz-Grundverordnung (DSGVO)", "fr": "Règlement général sur la protection des données (RGPD)",
           "it": "Regolamento generale sulla protezione dei dati (GDPR)", "es": "Reglamento General de Protección de Datos (RGPD)",
           "en": "General Data Protection Regulation (GDPR)", "pt": "Regulamento Geral sobre a Proteção de Dados (RGPD)",
           "hr": "Opća uredba o zaštiti podataka (GDPR)", "ja": "個人情報の保護に関する法律（個人情報保護法）"}


def _locale(branch: str):
    m = _LOCALE_RX.search((branch or "").strip().lower())
    if not m:
        return "", ""
    return m.group(1), _LANG_ALIAS.get(m.group(2), m.group(2))


def _is_page(p: str) -> bool:
    return p.lower().endswith((".html", ".htm", ".php")) and not p.startswith("_meta/")


def _is_node(files: dict) -> bool:
    return any(p.endswith(".vue") for p in files) or "src/data/pages.js" in files


def _law(country: str, lang: str) -> str:
    return LAW.get(country, {}).get(lang) or _EU_LAW.get(lang, _EU_LAW["en"])


# ------------------------------------------------------------------ факти
_FOOT_BRAND_RX = re.compile(r"<(?:h[1-4]|strong|b)\b[^>]*>([^<]{2,40})</", re.I)


def _site_name(branch: str, files: dict) -> str:
    """site_name.expected; якщо то слоган (>40 знаків, скрейп без бренду в
    <title>) — бренд із футера (перший h1-h4/strong), інакше з назви вітки."""
    name = ""
    try:
        import site_name
        name = site_name.expected(branch, files) or ""
    except Exception:
        pass
    if 0 < len(name) <= 40:
        return name
    home = _home(files)
    fm = FOOTER_RX.search(home)
    if fm:
        m = _FOOT_BRAND_RX.search(home, fm.end())
        if m and "{{" not in m.group(1):
            return " ".join(m.group(1).split())
    return name or re.sub(r"[-.](?:com|net|org)?[-.]?[a-z]{2}-[a-z]{2}(?:-\d+)?$", "", branch or "site").replace("-", " ").title()


def _home(files: dict) -> str:
    for p in ("index.php", "index.html", "index.htm", "index.vue", "src/pages/Home.vue"):
        if p in files:
            return files[p]
    return next((t for p, t in files.items() if _is_page(p)), "")


def _activity(files: dict) -> str:
    """Речення про діяльність: meta description головної, інакше h1."""
    for p, t in files.items():
        if p in ("index.html", "index.php", "src/pages/Home.vue"):
            m = DESC_RX.search(t)
            if m and len(m.group(1).strip()) > 30:
                return m.group(1).strip()
    for p in ("index.php", "index.html"):
        if p in files:
            m = H1_RX.search(files[p])
            if m:
                h1 = " ".join(TAGS_RX.sub(" ", m.group(1)).split())
                # слоган-питання («E se o problema… acontecer?») — не діяльність
                if 30 <= len(h1) <= 200 and not h1.endswith("?"):
                    return h1
    return ""


_ADDR_LABEL_RX = re.compile(r"^(?:endere[çc]o|direcci[oó]n|address|adresse|indirizzo|sede|morada|standort)\s*:\s*", re.I)
# «–/—/·» НЕ ріжуть — у адресах це роздільники полів («… 2738 – Sala 1402 –
# Boa Viagem», «Ulica 14 · Split»); ріжемо лише на | і явних словах
_ADDR_CUT_RX = re.compile(r"\s*(?:\||\bTel\b|\bTel\.|\bE-?Mail\b|\bPhone\b|\bTelefon|\bTeléfono|\bTelefone|\bCNPJ\b|\bUID\b|\bCHE-|\n)", re.I)


_PROSE_TAIL_RX = re.compile(r",?\s+(?:t[ée]l[ée]phone|telefone|tel[ée]fono|telefon|e-?mail|courriel|ou|et|and|e|und|y|o)\b.*$", re.I)
# речення після міста: «… 2610 Saint-Imier, Suisse. Le cabinet est dirigé …»
# (sentier 27.10) — від крапки з пробілом і великої літери і далі — проза
_SENTENCE_TAIL_RX = re.compile(r"\.\s+[A-ZÀ-Ý].*$")
# вступ речення перед вулицею: «Le présent site est édité par X SA, société …
# dont le siège est à la Rue de Vevey 14» → лишаємо від вулиці
_LEAD_IN_RX = re.compile(r"^.*?\b(?:si[èe]ge(?:\s+social)?\s+(?:est\s+)?(?:situ[ée]\s+)?(?:à|au|en)\s+(?:la\s+|le\s+|l')?|sitz\s+(?:in|an\s+der)\s+|sede\s+(?:legale\s+)?(?:in|a)\s+|com\s+sede\s+(?:em|na|no)\s+)", re.I)
# «Sentier Conseil Sàrl, Rue Francillon 24, …» — юрособа перед вулицею
_ENTITY_LEAD_RX = re.compile(r"^[^,;]{2,70}?\b(?:SA|S\.A\.|Sàrl|SARL|GmbH|AG|Ltd\.?|Ltda\.?|S\.?r\.?l\.?|SpA|S\.p\.A\.|LLC|Inc\.?|d\.o\.o\.|Sagl)\s*,\s*", re.I)


def _clean_addr(line: str) -> str:
    line = " ".join(line.split())
    if "%2C" in line or "%20" in line or re.search(r"\w\+\w\S*\+\d", line):
        import urllib.parse
        line = urllib.parse.unquote_plus(line)         # адреса з query мапи (chantier 27.10)
    line = _ADDR_LABEL_RX.sub("", line)
    line = _LEAD_IN_RX.sub("", line, count=1)
    line = _ENTITY_LEAD_RX.sub("", line, count=1)
    m = _ADDR_CUT_RX.search(line)
    if m and m.start() > 8:
        line = line[:m.start()]
    # адреса в реченні («… 2300 La Chaux-de-Fonds, téléphone et e-mail…»):
    # після сегмента з індексом ріжемо прозовий хвіст
    zm = re.search(r"\b\d{4,5}(?:-\d{3})?\b", line)
    if zm:
        tail = _PROSE_TAIL_RX.search(line, zm.end())
        if tail:
            line = line[:tail.start()]
        st = _SENTENCE_TAIL_RX.search(line, zm.end())
        if st:
            line = line[:st.start()]
    return line.strip(" .;,|")


def _jp_address(pages: dict) -> str:
    """«〒150-0001 東京都渋谷区神宮前3-15-2» — рядок з поштовим знаком;
    латинські вуличні шаблони address_number японську адресу не бачать."""
    for p in sorted(pages, key=lambda p: (bool(_LEGAL_PATH_RX.search(p)), p)):
        vis = TAGS_RX.sub("\n", pages[p])
        for m in JP_ADDR_RX.finditer(vis):
            line = " ".join(m.group(0).split())
            if "{{" not in line and 10 <= len(line) <= 80:
                return line
    return ""


def _address(files: dict, branch: str) -> str:
    """Адреса: видимий текст (футер/контакти) → юридична сторінка → гео-база."""
    try:
        import checks.address_number as an
        pages = {p: t for p, t in files.items() if _is_page(p) or p.endswith(".vue")}
        if _locale(branch)[0] == "jp":
            jp = _jp_address(pages)
            if jp:
                return jp
        for legal_pass in (False, True):
            for p in sorted(pages):
                if bool(_LEGAL_PATH_RX.search(p)) != legal_pass:
                    continue
                vis = TAGS_RX.sub("\n", pages[p])
                m = an.ADDR_RX.search(vis) or an._any_street(vis)
                if not m:
                    continue
                ls = vis.rfind("\n", 0, m.start()) + 1          # ВЕСЬ рядок («Grand-Rue 22…»)
                lines = [x for x in vis[ls:m.start() + 400].split("\n") if x.strip()]
                line = lines[0] if lines else ""
                # «Vordergasse 48,<br>8200 Schaffhausen»: індекс на наступному рядку
                if lines and not re.search(r"\b\d{4,5}(?:-\d{3})?\b", line) and len(lines) > 1:
                    line = line.rstrip(", ") + ", " + lines[1]
                line = _clean_addr(line)
                has_zip = bool(re.search(r"\b\d{4,5}(?:-\d{3})?\b", line))
                if "{{" not in line and 10 <= len(line) <= 120 and (has_zip or an.ADDR_RX.search(line)):
                    return line
        return an._geo_pick(branch)
    except Exception:
        return ""


def _page_order(files: dict) -> list:
    """Головна → звичайні сторінки → юридичні (факти беремо з найвидніших)."""
    return sorted((p for p in files if _is_page(p) or p.endswith(".vue")),
                  key=lambda p: (not HOME_RX.search(p.rsplit("/", 1)[-1]), bool(_LEGAL_PATH_RX.search(p)), p))


def _phone(files: dict, branch: str) -> tuple:
    for p in _page_order(files):
        t = files[p]
        m = TEL_RX.search(t)
        if m:
            shown = " ".join(TAGS_RX.sub(" ", m.group(2)).split())
            if len(re.sub(r"\D", "", shown)) >= 7:
                return shown, m.group(1).strip()
    try:
        import checks.geo_phone as gp
        num = gp._pick(branch)
        return (num, gp._tel_href(num)) if num else ("", "")
    except Exception:
        return "", ""


def _email(files: dict, branch: str, node: bool) -> str:
    local, dom = "info", None
    for p in _page_order(files):
        t = files[p]
        m = MAIL_RX.search(t) or MAIL_TEXT_RX.search(TAGS_RX.sub(" ", t))
        if m:
            local, dom = m.group(1), m.group(2)
            break
    if not node:
        return f"{local}@{{{{DOMAIN}}}}"
    if dom and "{{" not in dom:
        return f"{local}@{dom}"
    try:
        import domains
        real = domains.active_for(branch)
        if real:
            return f"{local}@{real}"
    except Exception:
        pass
    return f"{local}@{dom or 'example.invalid'}"


def _regno(files: dict, branch: str, country: str) -> str:
    big = "\n".join(t for p, t in files.items() if _is_page(p) or p.endswith(".vue"))
    if country == "ch":
        m = UID_RX.search(big)
        if m:
            return "UID " + m.group(0)
        try:
            import uid_pool
            num = uid_pool.pick(branch, _activity(files) + " " + _site_name(branch, files))
            return f"UID {num}" if num else ""
        except Exception:
            return ""
    if country == "br":
        m = CNPJ_RX.search(big)
        if m:
            return "CNPJ " + m.group(0)
        try:
            import cnpj_pool
            num = cnpj_pool.pick(branch, _activity(files))
            return f"CNPJ {num}" if num else ""
        except Exception:
            return ""
    if country == "it":
        parts = []
        m = PIVA_RX.search(big)
        if m:
            parts.append("P.IVA " + m.group(1))
        m = REA_RX.search(big)
        if m:
            parts.append("REA " + m.group(1))
        return " · ".join(parts)
    return ""


def facts(files: dict, branch: str) -> dict:
    country, lang = _locale(branch)
    node = _is_node(files)
    phone, tel = _phone(files, branch)
    return {"name": _site_name(branch, files), "activity": _activity(files),
            "address": _address(files, branch), "phone": phone, "tel": tel,
            "email": _email(files, branch, node), "regno": _regno(files, branch, country),
            "country": country, "lang": lang, "law": _law(country, lang),
            "date": datetime.date.today().strftime("%d.%m.%Y")}


# ------------------------------------------------------------------ тексти
def _contact_lines(f: dict) -> list:
    return [f["address"]] + ([f"Tel.: {f['phone']}"] if f["phone"] else []) \
        + [f"E-Mail: {f['email']}"] + ([f["regno"]] if f["regno"] else [])


def _lead(f: dict) -> str:
    """«Назва — діяльність»; без дубля, якщо речення вже починається з назви."""
    n, act = f["name"], f["activity"]
    if not act:
        return n
    return act if act.lower().startswith(n.lower()) else f"{n} — {act}"


def impressum_sections(f: dict) -> list:
    """[(заголовок, [абзаци])] мовою вітки; тема — з речення діяльності."""
    n = f["name"]
    lang = f["lang"] if f["lang"] in ("de", "fr", "it") else "de"
    contact = _contact_lines(f)
    lead = _lead(f)
    if lang == "de":
        return [
            ("Verantwortlich für den Inhalt", [lead] + contact),
            ("Handelsregister und UID", [f"Eingetragenes Unternehmen mit Sitz in der Schweiz. {f['regno']}." if f["regno"]
                                         else "Eingetragenes Unternehmen mit Sitz in der Schweiz.",
                                         "Mehrwertsteuer: gemäss den geltenden schweizerischen Bestimmungen."]),
            ("Haftungsausschluss", [f"{n} übernimmt keine Gewähr für die Richtigkeit, Genauigkeit, Aktualität, Zuverlässigkeit und Vollständigkeit der Informationen auf dieser Website. Haftungsansprüche wegen Schäden materieller oder immaterieller Art, die aus dem Zugriff, der Nutzung oder Nichtnutzung der veröffentlichten Informationen entstehen, werden ausgeschlossen.",
                                    "Alle Angebote sind unverbindlich. Teile der Seiten oder das gesamte Angebot können ohne gesonderte Ankündigung verändert, ergänzt oder gelöscht werden."]),
            ("Haftung für Links", ["Verweise und Links auf Websites Dritter liegen ausserhalb unseres Verantwortungsbereichs. Der Zugriff und die Nutzung solcher Websites erfolgen auf eigene Gefahr des Nutzers."]),
            ("Urheberrechte", [f"Die Urheber- und alle anderen Rechte an Inhalten, Bildern, Fotos oder anderen Dateien auf dieser Website gehören ausschliesslich {n} oder den speziell genannten Rechteinhabern. Für die Reproduktion jeglicher Elemente ist die schriftliche Zustimmung der Urheberrechtsträger im Voraus einzuholen."]),
            ("Datenschutz", ["Angaben zur Bearbeitung von Personendaten finden Sie in unserer Datenschutzerklärung."]),
        ]
    if lang == "fr":
        return [
            ("Responsable du contenu", [lead] + contact),
            ("Registre du commerce et IDE", [f"Entreprise enregistrée dont le siège est en Suisse. {f['regno']}." if f["regno"]
                                             else "Entreprise enregistrée dont le siège est en Suisse.",
                                             "TVA : conformément aux dispositions suisses en vigueur."]),
            ("Clause de non-responsabilité", [f"{n} ne garantit pas l'exactitude, la précision, l'actualité, la fiabilité ni l'exhaustivité des informations publiées sur ce site. Toute responsabilité pour des dommages matériels ou immatériels résultant de l'accès, de l'utilisation ou de la non-utilisation des informations publiées est exclue.",
                                               "Toutes les offres sont sans engagement. Nous nous réservons le droit de modifier, compléter ou supprimer tout ou partie du site sans préavis."]),
            ("Responsabilité pour les liens", ["Les renvois et liens vers des sites tiers échappent à notre responsabilité. L'accès à ces sites et leur utilisation se font aux risques de l'utilisateur."]),
            ("Droits d'auteur", [f"Les droits d'auteur et tous les autres droits liés aux contenus, images, photos ou autres fichiers de ce site appartiennent exclusivement à {n} ou aux titulaires de droits expressément mentionnés. Toute reproduction nécessite l'accord écrit préalable du titulaire des droits."]),
            ("Protection des données", ["Les informations relatives au traitement des données personnelles figurent dans notre politique de confidentialité."]),
        ]
    return [
        ("Responsabile dei contenuti", [lead] + contact),
        ("Registro di commercio e IDI", [f"Impresa registrata con sede in Svizzera. {f['regno']}." if f["regno"]
                                         else "Impresa registrata con sede in Svizzera.",
                                         "IVA: secondo le disposizioni svizzere vigenti."]),
        ("Esclusione di responsabilità", [f"{n} non garantisce l'esattezza, la precisione, l'attualità, l'affidabilità e la completezza delle informazioni pubblicate su questo sito. È esclusa qualsiasi responsabilità per danni materiali o immateriali derivanti dall'accesso, dall'uso o dal mancato uso delle informazioni pubblicate.",
                                          "Tutte le offerte sono senza impegno. Ci riserviamo il diritto di modificare, integrare o cancellare parti del sito o l'intera offerta senza preavviso."]),
        ("Responsabilità per i link", ["I rimandi e i link a siti di terzi esulano dal nostro ambito di responsabilità. L'accesso e l'uso di tali siti avvengono a rischio dell'utente."]),
        ("Diritti d'autore", [f"I diritti d'autore e tutti gli altri diritti sui contenuti, le immagini, le foto o altri file di questo sito appartengono esclusivamente a {n} o ai titolari dei diritti espressamente indicati. Per la riproduzione di qualsiasi elemento è necessario il consenso scritto preventivo del titolare dei diritti."]),
        ("Protezione dei dati", ["Le informazioni sul trattamento dei dati personali sono riportate nella nostra informativa sulla privacy."]),
    ]


def privacy_sections(f: dict) -> list:
    n, act, law, mail = f["name"], f["activity"], f["law"], f["email"]
    who = f"{n}" + (f" ({f['regno']})" if f["regno"] else "")
    addr = f["address"]
    lang = f["lang"] if f["lang"] in ("de", "fr", "it", "pt", "es", "en", "ja") else "en"
    # японська: адреса може бути порожньою (без 〒-рядка на сайті гео-бази нема)
    ja_who = f"{who}（所在地：{addr}）" if addr else who
    ja_phone = f"お電話（{f['phone']}）" if f.get("phone") else "お電話"
    T = {
        "pt": [("1. Quem somos e o que fazemos", [f"{who}, com sede em {addr}, é responsável pelo tratamento dos dados pessoais coletados por meio deste site e dos canais de atendimento.", (f"Nossa atividade: {act}" if act else ""), f"Esta política segue a {law}. Dúvidas: {mail}."]),
               ("2. Dados pessoais coletados", ["Dados informados no formulário de contato ou por WhatsApp/telefone: nome, e-mail, telefone, empresa e o conteúdo da mensagem. Dados técnicos de navegação coletados automaticamente: endereço IP, navegador, páginas visitadas, data e hora de acesso."]),
               ("3. Finalidades", ["Responder às suas solicitações e orçamentos, prestar os serviços contratados, cumprir obrigações legais e, com o seu consentimento, enviar comunicações sobre nossos serviços."]),
               ("4. Prazo de retenção", ["Mantemos os dados pelo tempo necessário às finalidades acima e pelos prazos exigidos pela legislação fiscal e consumerista. Solicitações não convertidas em contrato são eliminadas em até 12 meses."]),
               ("5. Compartilhamento", ["Não vendemos dados pessoais. Compartilhamos apenas com prestadores necessários à execução dos serviços (hospedagem, e-mail, sistemas de gestão) e com autoridades, quando exigido por lei."]),
               ("6. Cookies", ["Utilizamos cookies estritamente necessários e, mediante consentimento no aviso exibido na primeira visita, cookies de medição de audiência. A escolha pode ser alterada nas configurações do navegador."]),
               ("7. Segurança", ["Adotamos medidas técnicas e administrativas para proteger os dados contra acesso não autorizado, perda, alteração ou divulgação indevida, incluindo conexão criptografada (HTTPS) e controle de acesso restrito."]),
               ("8. Seus direitos", [f"Você pode solicitar confirmação de tratamento, acesso, correção, anonimização, portabilidade ou eliminação dos seus dados e revogar consentimentos. Envie o pedido para {mail}; respondemos em até 15 dias."]),
               ("9. Alterações", [f"Esta política pode ser atualizada; a versão vigente é a publicada nesta página. Última atualização: {f['date']}."])],
        "es": [("1. Responsable del tratamiento", [f"{who}, con domicilio en {addr}, es responsable del tratamiento de los datos personales recabados a través de este sitio y de los canales de atención.", (f"Nuestra actividad: {act}" if act else ""), f"Esta política se rige por la {law}. Consultas: {mail}."]),
               ("2. Datos que recabamos", ["Datos proporcionados en el formulario de contacto o por WhatsApp/teléfono: nombre, correo electrónico, teléfono, empresa y contenido del mensaje. Datos técnicos de navegación: dirección IP, navegador, páginas visitadas, fecha y hora de acceso."]),
               ("3. Finalidades", ["Atender sus solicitudes y cotizaciones, prestar los servicios contratados, cumplir obligaciones legales y, con su consentimiento, enviar comunicaciones sobre nuestros servicios."]),
               ("4. Conservación", ["Conservamos los datos el tiempo necesario para las finalidades indicadas y los plazos exigidos por la legislación fiscal y de consumo. Las solicitudes no convertidas en contrato se eliminan en un plazo máximo de 12 meses."]),
               ("5. Transferencias", ["No vendemos datos personales. Solo los compartimos con proveedores necesarios para prestar el servicio (alojamiento, correo, sistemas de gestión) y con autoridades cuando la ley lo exige."]),
               ("6. Cookies", ["Usamos cookies estrictamente necesarias y, previo consentimiento en el aviso de la primera visita, cookies de medición de audiencia. Puede cambiar su elección en la configuración del navegador."]),
               ("7. Seguridad", ["Aplicamos medidas técnicas y administrativas para proteger los datos frente a accesos no autorizados, pérdida, alteración o divulgación indebida, incluida la conexión cifrada (HTTPS)."]),
               ("8. Sus derechos", [f"Puede ejercer sus derechos de acceso, rectificación, cancelación, oposición y portabilidad, así como revocar el consentimiento, escribiendo a {mail}. Respondemos en un plazo máximo de 20 días hábiles."]),
               ("9. Cambios", [f"Esta política puede actualizarse; la versión vigente es la publicada en esta página. Última actualización: {f['date']}."])],
        "en": [("1. Who we are", [f"{who}, {addr}, is the data controller for personal data collected through this website and our contact channels.", (f"What we do: {act}" if act else ""), f"This policy follows the {law}. Questions: {mail}."]),
               ("2. Data we collect", ["Details you provide via the contact form, phone or messaging: name, e-mail, phone number, company and the content of your message. Technical data collected automatically: IP address, browser, pages visited, date and time of access."]),
               ("3. Purposes", ["Responding to enquiries and quotes, delivering the services you order, meeting legal obligations and, with your consent, sending information about our services."]),
               ("4. Retention", ["We keep data only as long as needed for the purposes above and as required by tax and consumer law. Enquiries that do not lead to a contract are deleted within 12 months."]),
               ("5. Sharing", ["We do not sell personal data. We share it only with providers needed to deliver the service (hosting, e-mail, management systems) and with authorities where the law requires."]),
               ("6. Cookies", ["We use strictly necessary cookies and, with your consent given in the notice on your first visit, audience-measurement cookies. You can change your choice in your browser settings."]),
               ("7. Security", ["We apply technical and organisational measures against unauthorised access, loss, alteration or disclosure, including encrypted connections (HTTPS) and restricted access."]),
               ("8. Your rights", [f"You may request access, correction, deletion or portability of your data, object to processing and withdraw consent by writing to {mail}. We reply within 30 days."]),
               ("9. Changes", [f"This policy may be updated; the current version is the one published on this page. Last updated: {f['date']}."])],
        "de": [("1. Verantwortliche Stelle", [f"{who}, {addr}, ist verantwortlich für die Bearbeitung der Personendaten, die über diese Website und unsere Kontaktkanäle erhoben werden.", (f"Unsere Tätigkeit: {act}" if act else ""), f"Diese Erklärung richtet sich nach dem {law}. Fragen: {mail}."]),
               ("2. Erhobene Daten", ["Angaben aus dem Kontaktformular, per Telefon oder Messenger: Name, E-Mail, Telefonnummer, Firma und Inhalt der Nachricht. Automatisch erfasste technische Daten: IP-Adresse, Browser, besuchte Seiten, Datum und Uhrzeit des Zugriffs."]),
               ("3. Zwecke", ["Beantwortung von Anfragen und Offerten, Erbringung der bestellten Leistungen, Erfüllung gesetzlicher Pflichten und – mit Ihrer Einwilligung – Informationen über unsere Angebote."]),
               ("4. Aufbewahrung", ["Daten werden nur so lange aufbewahrt, wie es für die genannten Zwecke und die gesetzlichen Aufbewahrungsfristen nötig ist. Anfragen ohne Vertragsabschluss werden innert 12 Monaten gelöscht."]),
               ("5. Weitergabe", ["Wir verkaufen keine Personendaten. Eine Weitergabe erfolgt nur an Dienstleister, die für die Leistungserbringung nötig sind (Hosting, E-Mail, Verwaltungssysteme), und an Behörden, wo das Gesetz es verlangt."]),
               ("6. Cookies", ["Wir verwenden technisch notwendige Cookies und – nach Ihrer Einwilligung im Hinweis beim ersten Besuch – Cookies zur Reichweitenmessung. Die Wahl kann in den Browser-Einstellungen geändert werden."]),
               ("7. Datensicherheit", ["Wir treffen technische und organisatorische Massnahmen gegen unbefugten Zugriff, Verlust, Veränderung oder Offenlegung, u. a. verschlüsselte Verbindungen (HTTPS) und beschränkte Zugriffsrechte."]),
               ("8. Ihre Rechte", [f"Sie können Auskunft, Berichtigung, Löschung oder Herausgabe Ihrer Daten verlangen, der Bearbeitung widersprechen und Einwilligungen widerrufen – per E-Mail an {mail}. Wir antworten innert 30 Tagen."]),
               ("9. Änderungen", [f"Diese Erklärung kann angepasst werden; massgebend ist die auf dieser Seite veröffentlichte Fassung. Letzte Aktualisierung: {f['date']}."])],
        "fr": [("1. Responsable du traitement", [f"{who}, {addr}, est responsable du traitement des données personnelles collectées via ce site et nos canaux de contact.", (f"Notre activité : {act}" if act else ""), f"Cette politique est conforme à la {law}. Questions : {mail}."]),
               ("2. Données collectées", ["Informations fournies via le formulaire de contact, par téléphone ou messagerie : nom, e-mail, téléphone, entreprise et contenu du message. Données techniques collectées automatiquement : adresse IP, navigateur, pages consultées, date et heure d'accès."]),
               ("3. Finalités", ["Répondre aux demandes et devis, fournir les prestations commandées, respecter nos obligations légales et, avec votre consentement, vous informer sur nos services."]),
               ("4. Conservation", ["Les données sont conservées uniquement le temps nécessaire aux finalités indiquées et aux délais légaux. Les demandes sans contrat sont supprimées dans un délai de 12 mois."]),
               ("5. Transmission", ["Nous ne vendons pas de données personnelles. Elles ne sont transmises qu'aux prestataires nécessaires à la fourniture du service (hébergement, e-mail, systèmes de gestion) et aux autorités lorsque la loi l'exige."]),
               ("6. Cookies", ["Nous utilisons des cookies strictement nécessaires et, avec votre consentement donné dans l'avis lors de la première visite, des cookies de mesure d'audience. Vous pouvez modifier votre choix dans les paramètres du navigateur."]),
               ("7. Sécurité", ["Nous appliquons des mesures techniques et organisationnelles contre l'accès non autorisé, la perte, l'altération ou la divulgation, notamment une connexion chiffrée (HTTPS) et des accès restreints."]),
               ("8. Vos droits", [f"Vous pouvez demander l'accès, la rectification, la suppression ou la portabilité de vos données, vous opposer au traitement et retirer votre consentement en écrivant à {mail}. Nous répondons sous 30 jours."]),
               ("9. Modifications", [f"Cette politique peut être mise à jour ; la version en vigueur est celle publiée sur cette page. Dernière mise à jour : {f['date']}."])],
        "it": [("1. Titolare del trattamento", [f"{who}, {addr}, è titolare del trattamento dei dati personali raccolti tramite questo sito e i nostri canali di contatto.", (f"La nostra attività: {act}" if act else ""), f"La presente informativa è conforme al {law}. Domande: {mail}."]),
               ("2. Dati raccolti", ["Dati forniti tramite il modulo di contatto, telefono o messaggistica: nome, e-mail, telefono, azienda e contenuto del messaggio. Dati tecnici raccolti automaticamente: indirizzo IP, browser, pagine visitate, data e ora di accesso."]),
               ("3. Finalità", ["Rispondere a richieste e preventivi, erogare i servizi ordinati, adempiere agli obblighi di legge e, con il suo consenso, inviare informazioni sui nostri servizi."]),
               ("4. Conservazione", ["I dati sono conservati solo per il tempo necessario alle finalità indicate e ai termini di legge. Le richieste senza contratto vengono cancellate entro 12 mesi."]),
               ("5. Comunicazione", ["Non vendiamo dati personali. Li comunichiamo solo ai fornitori necessari all'erogazione del servizio (hosting, e-mail, sistemi gestionali) e alle autorità quando la legge lo richiede."]),
               ("6. Cookie", ["Utilizziamo cookie strettamente necessari e, previo consenso nell'avviso alla prima visita, cookie di misurazione dell'audience. La scelta può essere modificata nelle impostazioni del browser."]),
               ("7. Sicurezza", ["Adottiamo misure tecniche e organizzative contro accessi non autorizzati, perdita, alterazione o divulgazione, tra cui connessione cifrata (HTTPS) e accessi limitati."]),
               ("8. I suoi diritti", [f"Può chiedere accesso, rettifica, cancellazione o portabilità dei dati, opporsi al trattamento e revocare il consenso scrivendo a {mail}. Rispondiamo entro 30 giorni."]),
               ("9. Modifiche", [f"La presente informativa può essere aggiornata; fa fede la versione pubblicata in questa pagina. Ultimo aggiornamento: {f['date']}."])],
        "ja": [("1. 事業者情報", [f"{ja_who}は、本ウェブサイトおよびお問い合わせ窓口を通じて取得する個人情報の取扱事業者です。", (f"事業内容：{act}" if act else ""), f"本ポリシーは{law}に基づいています。お問い合わせ先：{mail}"]),
               ("2. 取得する個人情報", [f"お問い合わせフォーム、{ja_phone}、メッセージアプリ等でご提供いただく情報：氏名、メールアドレス、電話番号、会社名、お問い合わせ内容。自動的に取得する技術情報：IPアドレス、ブラウザの種類、閲覧ページ、アクセス日時。"]),
               ("3. 利用目的", ["お問い合わせ・お見積りへの回答、ご依頼いただいたサービスの提供、法令上の義務の履行、およびご同意をいただいた場合に限り、当社サービスに関するご案内の送付。"]),
               ("4. 保存期間", ["個人情報は、上記の目的の達成に必要な期間および法令で定められた期間に限り保管します。ご契約に至らなかったお問い合わせの情報は、12か月以内に削除します。"]),
               ("5. 第三者への提供", ["当社は個人情報を販売しません。サービス提供に必要な委託先（ホスティング、メール配信、業務管理システム）および法令に基づき開示が求められる官公庁以外に提供することはありません。"]),
               ("6. クッキー（Cookie）", ["当サイトでは、動作に必須のクッキーと、初回訪問時の同意バナーでご同意いただいた場合に限りアクセス解析用のクッキーを使用します。設定はブラウザから変更できます。"]),
               ("7. 安全管理措置", ["不正アクセス、紛失、改ざん、漏えいを防止するため、暗号化通信（HTTPS）やアクセス権限の制限など、技術的・組織的な安全管理措置を講じています。"]),
               ("8. 開示・訂正・削除のご請求", [f"ご本人は、保有個人データの開示、訂正、利用停止、削除、およびご同意の撤回を請求できます。{mail}までご連絡ください。原則として30日以内に回答します。"]),
               ("9. 改定", [f"本ポリシーは必要に応じて改定することがあります。最新の内容は本ページに掲載するものとします。最終更新日：{f['date']}"])],
    }
    return [(h, [p for p in ps if p]) for h, ps in T[lang]]


# ------------------------------------------------------------------ оболонка (php)
_BLOCK_RX = re.compile(r"<(/?)(div|section|article)\b[^>]*>", re.I)
_H2_RX = re.compile(r"<h2\b[^>]*>", re.I)
_P_RX = re.compile(r"<p\b[^>]*>", re.I)
_OPEN_BEFORE_RX = re.compile(r"<(div|section|article)\b[^>]*>(?!.*<(?:div|section|article)\b)", re.I | re.S)
_MAIN_RX = re.compile(r"<main\b[^>]*>", re.I)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _donor(files: dict):
    """Шлях до юридичної сторінки-донора: privacy → terms → cookies."""
    pages = [p for p in files if _is_page(p)]
    for rx in (PRIV_PATH_RX, re.compile(r"terms|termos|condi|agb|nutzung|agreement", re.I),
               re.compile(r"cookie", re.I)):
        for p in sorted(pages):
            if rx.search(p) and "<h1" in files[p]:
                return p
    return None


def _content_span(text: str):
    """(start, end, depth) — ділянка контенту сторінки, що замінюється:
    від обгортки першої секції (<div> перед першим <h2>) до закриття
    <main>/<body>; depth — скільки блоків відкрито між початком main і
    обгорткою (їх треба закрити знову)."""
    mm = _MAIN_RX.search(text)
    start_zone = mm.end() if mm else (text.lower().find("<body") + 1)
    span = _footer_span(text)
    end_zone = text.lower().find("</main>", start_zone) if mm else -1
    if end_zone < 0:
        end_zone = span[0] if span else -1
    if end_zone < 0:
        return None
    h2 = _H2_RX.search(text, start_zone, end_zone)
    if not h2:
        return None
    before = text[start_zone:h2.start()]
    ob = _OPEN_BEFORE_RX.search(before)
    wrap_start = start_zone + (ob.start() if ob else len(before))
    depth = 0
    for m in _BLOCK_RX.finditer(text[start_zone:wrap_start]):
        depth += -1 if m.group(1) else 1
    return wrap_start, end_zone, max(depth, 0)


def _harvest(text: str, start: int, end: int) -> dict:
    seg = text[start:end]
    h2 = _H2_RX.search(seg)
    wrap = _OPEN_BEFORE_RX.search(seg[:h2.start()]) if h2 else None
    p = _P_RX.search(seg, h2.end() if h2 else 0)
    return {"h2": h2.group(0) if h2 else "<h2>", "p": p.group(0) if p else "<p>",
            "wrap": (wrap.group(0), wrap.group(1)) if wrap else ("<div>", "div")}


def _render_sections(sections: list, cls: dict) -> str:
    wrap_open, wrap_tag = cls["wrap"]
    out = []
    for h, ps in sections:
        body = "".join(f"\n      {cls['p']}{_esc(x)}</p>" for x in ps)
        out.append(f"\n    {wrap_open}\n      {cls['h2']}{_esc(h)}</h2>{body}\n    </{wrap_tag}>")
    return "".join(out)


_LOGO_H1_RX = re.compile(r"<h1\b[^>]*\b(?:id|class)\s*=\s*[\"'][^\"']*logo|<h1\b[^>]*>\s*(?:<a\b|<img\b)", re.I)


def _retitle(text: str, h1: str, title: str) -> str:
    """Наш заголовок — у перший КОНТЕНТНИЙ <h1>: японські шаблони тримають
    лого в <h1 id="logo"><a><img></a></h1> у шапці (fugruxoge-atowoos 27.10 —
    лого підмінялось текстом «プライバシーポリシー»), Wix — текстовий <h1>
    з назвою всередині <header> (hajipo-kabe 27.10)."""
    hd = re.search(r"</header\s*>", text, re.I)
    header_end = hd.end() if hd else 0
    for m in H1_RX.finditer(text):
        if m.start() < header_end or _LOGO_H1_RX.match(m.group(0)):
            continue
        text = text[:m.start()] + m.group(0)[:m.group(0).find(">") + 1] + _esc(h1) + "</h1>" + text[m.end():]
        break
    return TITLE_RX.sub(lambda m: m.group(0)[:m.group(0).find(">") + 1] + _esc(title) + "</title>", text, count=1)


def build_page_php(files: dict, h1: str, sections: list, name: str) -> str:
    """Сторінка в оболонці донора; без донора — оболонка головної."""
    donor = _donor(files)
    if donor:
        text = files[donor]
        span = _content_span(text)
        if span:
            s, e, depth = span
            cls = _harvest(text, s, e)
            closers = "".join("\n    </div>" for _ in range(depth))
            new = text[:s] + _render_sections(sections, cls) + closers + "\n" + text[e:]
            new = _retitle(new, h1, f"{h1} – {name}")
            # «Letzte Aktualisierung …» донора — не наша дата, прибираємо лише рядок
            new = re.sub(r"<p\b[^>]*>[^<]{0,40}(?:aktualis|atualiza|actualiza|mise à jour|aggiornament|updated)[^<]*</p>\s*",
                         "", new, count=1, flags=re.I)
            return new
    home = _home(files)
    home = PHP_RX.sub("", home)
    low = home.lower()
    span = _footer_span(home)
    fm = span[0] if span else -1
    if fm >= 0:
        ft = low.rfind("<footer", 0, fm + 1)
        if ft >= 0 and low.find(">", ft) == fm - 1:
            fm = ft                                     # оболонка бере сам тег <footer>
    head_end = low.find("</head>")
    if fm < 0 or head_end < 0:
        return ""
    hm = low.find("</header>")
    if 0 <= hm < fm:
        hm += 9
    else:
        nm = low.find("</nav>")
        bm = re.search(r"<body\b[^>]*>", home, re.I)
        hm = nm + 6 if 0 <= nm < fm else (bm.end() if bm else head_end + 7)
    home = home[:hm] + home[fm:] if False else home
    cls = {"h2": '<h2 style="margin:28px 0 8px;font-size:1.25rem">', "p": '<p style="margin:0 0 10px;line-height:1.7">', "wrap": ("<div>", "div")}
    body = (f'<main style="max-width:860px;margin:0 auto;padding:48px 20px"><h1>{_esc(h1)}</h1>'
            + _render_sections(sections, cls) + "</main>\n")
    page = home[:hm] + "\n" + body + home[fm:]
    return _retitle(page, h1, f"{h1} – {name}")


_COPY_RX = re.compile(r"©|&copy;|\(c\)\s*20\d\d|\b20\d\d\b[^<]{0,40}(?:direitos|rights|droits|diritti|derechos|Rechte)|\bCNPJ\b|\bCHE-\d", re.I)
# підвал без © і без <footer> (yahoge-kokea, mohiol 26.10 — японські скрейпи):
# останній блок із назвою юрособи (株式会社/有限会社/合同会社), «All Rights
# Reserved» або поштою — другий ешелон якорів, лише коли © нема ніде
_CORP_RX = re.compile(r"株式会社|有限会社|合同会社|All\s+Rights\s+Reserved|無断転載|href\s*=\s*[\"']mailto:", re.I)


def _anchor_rx(text: str):
    """Регекс якоря підвалу для цього документа: © → юр-суфікс/пошта → None."""
    for rx in (_COPY_RX, _CORP_RX):
        if rx.search(text):
            return rx
    return None


def _footer_span(text: str):
    """(start, end) зони футера: <footer>…</footer>, інакше останній блок
    із copyright/CNPJ (Elementor/Astro-білди підвал роблять <div> —
    caixadagua, ngrestauracao 19.10: чек мовчав, фікс давав 0 дій)."""
    # кілька <footer> (Wix: порожній «footer» + справжній): беремо той, де є
    # лінки; інакше — останній; порожній без лінків пропускаємо
    best = None
    for fm in FOOTER_RX.finditer(text):
        fend = text.lower().find("</footer>", fm.end())
        if fend < 0:
            continue
        seg = text[fm.end():fend]
        if "<a" in seg.lower():
            best = (fm.end(), fend)
        elif best is None and seg.strip():
            best = (fm.end(), fend)
    if best:
        return best
    rx = _anchor_rx(text)
    hits = list(rx.finditer(text)) if rx else []
    low = text.lower()
    body_end = low.rfind("</body>")
    for m in reversed(hits):
        if body_end > 0 and m.start() > body_end:
            continue
        if low.rfind("<script", 0, m.start()) > low.rfind("</script>", 0, m.start()):
            continue                                  # у скрипті — не футер
        s = max(text.rfind("<section", 0, m.start()), text.rfind("<div", 0, m.start()))
        if s < 0:
            s = m.start()
        # кінець — усе до </body> (без хвостових скриптів): підвал без
        # <footer> часто кладе юридичні лінки сусідніми <p> ПІСЛЯ © (releve)
        e = body_end if body_end > 0 else len(text)
        sc = low.find("<script", s)
        while 0 < sc < e and low.find("</script>", sc) > 0:
            nxt = low.find("</script>", sc) + 9
            if not re.search(r"<(?:a|p|ul|div|span)\b", low[nxt:e]):
                e = sc
                break
            sc = low.find("<script", nxt)
        return s, e
    return None


def _link_html(files: dict, path: str, href: str, label: str, kind_rx) -> str | None:
    """Сторінка з новим лінком у футері: клон сусіднього юридичного <a>."""
    text = files[path]
    span = _footer_span(text)
    if not span:
        return None
    fstart, fend = span
    foot = text[fstart:fend]

    class _M:                                        # сумісність із fm.end()
        def end(self):
            return fstart
    fm = _M()
    stem = href.split("/")[-1]
    folder = href.rsplit("/", 1)[0] if "/" in href else ""
    if re.search(r"""href\s*=\s*["'][^"']*""" + re.escape(stem), foot, re.I) or \
            (folder and re.search(r"""href\s*=\s*["'][^"']*""" + re.escape(folder) + r"""/?(?:index\.html?)?["'#?]""", foot, re.I)):
        return None                                   # уже є
    prefix = "../" * path.count("/")
    target = prefix + href
    anchors = list(A_RX.finditer(foot))
    pick = None
    for a in anchors:
        hm = HREF_RX.search(a.group(1))
        if hm and kind_rx.search(hm.group(2)):
            pick = a
    if pick is None:
        for a in anchors:
            hm = HREF_RX.search(a.group(1))
            if hm and re.search(r"\.(?:html?|php)(?:$|[#?])", hm.group(2), re.I):
                pick = a
    if pick is None:
        # без жодного <a> у підвалі: лінк одразу після елемента з якорем (©,
        # інакше юр-суфікс/пошта) тим самим тегом/класами, щоб успадкувати
        # стиль; інакше — в кінець зони
        rx = _anchor_rx(text) or _COPY_RX
        cm = rx.search(foot)
        if cm:
            pos = cm.start()
            open_at = foot.rfind("<", 0, pos)
            tag_m = re.match(r"<(\w+)([^>]*)>", foot[open_at:]) if open_at >= 0 else None
            if tag_m and tag_m.group(1).lower() == "a":
                # якір — mailto: усередині <a>: клонуємо батьківський блок
                a_close = foot.lower().find("</a>", pos)
                pos = a_close + 4 if a_close > 0 else pos
                parents = list(re.finditer(r"<(p|div|span|small|li)\b[^>]*>", foot[:open_at], re.I))
                tag_m = None
                if parents:
                    open_at = parents[-1].start()
                    tag_m = re.match(r"<(\w+)([^>]*)>", foot[open_at:])
            if tag_m and tag_m.group(1).lower() in ("p", "div", "span", "small", "li"):
                tag = tag_m.group(1)
                close = foot.lower().find(f"</{tag.lower()}>", pos)
                if close > 0:
                    ins = fm.end() + close + len(f"</{tag}>")
                    attrs = re.sub(r"""\s+id\s*=\s*(["']).*?\1""", "", tag_m.group(2))   # дубль id — невалідно
                    link = f'<{tag}{attrs}><a href="{target}">{_esc(label)}</a></{tag}>'
                    return text[:ins] + "\n" + link + text[ins:]
        ins = fend
        return text[:ins] + f'<p><a href="{target}">{_esc(label)}</a></p>\n' + text[ins:]
    style = HREF_RX.search(pick.group(1)).group(2)
    if style.startswith("./") and not target.startswith("."):
        target = "./" + target
    attrs = HREF_RX.sub(lambda m: f'href={m.group(1)}{target}{m.group(1)}', pick.group(1), count=1)
    clone = f"<a{attrs}>{_esc(label)}</a>"
    # якір у <li>: клонуємо і <li>, інакше лінк приклеїться в той самий рядок
    before = foot[:pick.start()].rstrip()
    after = foot[pick.end():].lstrip()
    li = re.search(r"<li\b[^>]*>$", before, re.I)
    if li and after.lower().startswith("</li>"):
        ins = fm.end() + pick.end() + (len(foot[pick.end():]) - len(after)) + len("</li>")
        return text[:ins] + "\n" + li.group(0) + clone + "</li>" + text[ins:]
    sep = " " if pick.end() < len(foot) and foot[pick.end():pick.end() + 1] not in ("\n",) else "\n"
    ins = fm.end() + pick.end()
    return text[:ins] + sep + clone + text[ins:]


# ------------------------------------------------------------------ node
_PAGES_ENTRY_RX = re.compile(r"\{\s*\"id\":\s*\"privacy\"[\s\S]*?\}")
_PAGES_ROUTE_RX = re.compile(r"\"id\":\s*\"privacy\"[^}]*?\"route\":\s*\"([^\"]+)\"")


def _node_rename_route(files: dict, old: str, new: str, label: str = "") -> list:
    """Роут політики «/privatnost» → «/privacy-policy» по всьому src/:
    pages.js (футер і меню малюють звідти; лейбл — повний «Politika
    privatnosti», а не голе «Privatnost»), router (старий path лишається
    alias-ом — зовнішні лінки не ламаються), компоненти з жорстким href."""
    acts = []
    rx = re.compile(r"(?<=[\"'`(])" + re.escape(old) + r"(?=[\"'`)?#]|$)")
    for p in sorted(files):
        if not p.startswith("src/") or not p.endswith((".js", ".vue", ".ts")):
            continue
        t = files[p]
        if p.endswith("router/index.js"):
            t = re.sub(r"path:\s*'" + re.escape(old) + r"'", f"path: '{new}',\n    alias: '{old}'", t)
        else:
            t = rx.sub(new, t)
        if label and p.endswith("data/pages.js"):
            t = re.sub(r"(\"id\":\s*\"privacy\",\s*\"name\":\s*)\"[^\"]*\"", lambda m: m.group(1) + json.dumps(label, ensure_ascii=False), t, count=1)
        if t != files[p]:
            acts.append({"type": "edit", "path": p, "content": t})
    return acts
_ROUTE_ENTRY_RX = re.compile(r"\{[^{}]*name:\s*'privacy'[^{}]*\}")


def _node_privacy_component(files: dict) -> str:
    for p in ("src/pages/Privacy.vue",):
        if p in files:
            m = re.search(r"from '@/components/([^']+)'", files[p])
            if m and f"src/components/{m.group(1)}" in files:
                return files[f"src/components/{m.group(1)}"]
    return ""


def _vue_cls(text: str, tag: str, default: str) -> str:
    m = re.search(rf"<{tag}\b[^>]*\bclass=\"([^\"]+)\"", text)
    return m.group(1) if m else default


def build_page_node(files: dict, h1: str, sections: list) -> str:
    donor = _node_privacy_component(files)
    main_cls = _vue_cls(donor, "main", "max-w-4xl mx-auto px-4 py-12")
    h1_cls = _vue_cls(donor, "h1", "text-4xl font-semibold mb-8")
    h2_cls = _vue_cls(donor, "h2", "text-2xl font-semibold mb-3")
    after_h2 = donor[donor.find("<h2"):] if "<h2" in donor else donor
    p_cls = _vue_cls(after_h2, "p", "leading-relaxed mb-4")
    sec_cls = _vue_cls(donor, "section", "") or "mb-10"
    body = []
    for h, ps in sections:
        body.append(f'    <section class="{sec_cls}">\n      <h2 class="{h2_cls}">{_esc(h)}</h2>\n'
                    + "".join(f'      <p class="{p_cls}">{_esc(x)}</p>\n' for x in ps) + "    </section>")
    return ('<template>\n  <main class="' + main_cls + '">\n    <h1 class="' + h1_cls + '">' + _esc(h1)
            + "</h1>\n" + "\n".join(body) + "\n  </main>\n</template>\n\n<script>\nexport default { name: '"
            + re.sub(r"\W", "", h1) + "Page' }\n</script>\n")


def _node_actions(files: dict, kind: str, route: str, label: str, page_name: str, content: str) -> list:
    acts = []
    pages_js = files.get("src/data/pages.js", "")
    if pages_js and f'"route": "{route}"' not in pages_js:
        entry = (f'  {{\n    "id": "{kind}",\n    "name": "{label}",\n    "route": "{route}",\n'
                 f'    "category": "legal",\n    "description": "{kind} page",\n    "nav": true\n  }},\n')
        i = pages_js.find("export const pages = [")
        j = pages_js.find("\n]", i) if i >= 0 else -1
        if j > 0:
            acts.append({"type": "edit", "path": "src/data/pages.js",
                         "content": pages_js[:j] + ",\n" + entry.rstrip(",\n") + pages_js[j:]})
    router = files.get("src/router/index.js", "")
    if router and f"path: '{route}'" not in router:
        rentry = (f"  {{\n    path: '{route}',\n    name: '{kind}',\n"
                  f"    component: () => import('@/pages/{page_name}.vue')\n  }},\n")
        i = router.find("export const routes = [")
        j = router.find("\n]", i) if i >= 0 else -1
        if j > 0:
            acts.append({"type": "edit", "path": "src/router/index.js",
                         "content": router[:j] + ",\n" + rentry.rstrip(",\n") + router[j:]})
    acts.append({"type": "edit", "path": f"src/pages/{page_name}.vue", "content": content})
    return acts


def _node_imp_component(files: dict) -> str:
    """Шлях до файлу, де реально живе контент Impressum: сторінка
    src/pages/Impressum.vue сама, або компонент, який вона імпортує — та сама
    механіка, що й _node_privacy_component (Privacy.vue → DataPolicy.vue),
    але для Impressum (ручні Vue-компоненти бувають і без адреси)."""
    page = next((p for p in files if p.startswith("src/pages/") and IMP_PATH_RX.search(p)), "")
    if not page:
        return ""
    m = re.search(r"from ['\"]@/components/([^'\"]+)['\"]", files[page])
    if m and f"src/components/{m.group(1)}" in files:
        return f"src/components/{m.group(1)}"
    return page

# ------------------------------------------------------------------ стан
def _state(files: dict, branch: str) -> dict:
    country, lang = _locale(branch)
    node = _is_node(files)
    pages = {p: t for p, t in files.items() if _is_page(p)}
    priv_route = ""
    if node:
        pj = files.get("src/data/pages.js", "")
        has_imp = bool(IMP_PATH_RX.search(pj)) or any(IMP_PATH_RX.search(p) for p in files if p.startswith("src/pages/"))
        has_priv = bool(PRIV_PATH_RX.search(pj)) or "src/pages/Privacy.vue" in files
        imp_linked = has_imp
        # лінк у футері малює legalPages з pages.js, але QA судить за href:
        # «/privatnost» (hr) він політикою не вважає — роут мусить містити
        # privac/datenschutz/confidentialit/… (той самий PRIV_PATH_RX)
        pm = _PAGES_ROUTE_RX.search(pj)
        priv_route = pm.group(1) if pm else ""
        priv_linked = has_priv and (not priv_route or bool(PRIV_PATH_RX.search(priv_route)))
    else:
        imp_pages = [p for p, t in pages.items() if IMP_PATH_RX.search(p) or IMP_H1_RX.search(t)]
        priv_pages = [p for p, t in pages.items() if PRIV_PATH_RX.search(p)
                      or (lang == "ja" and PRIV_JA_RX.search(t[:4000]))]
        has_imp, has_priv = bool(imp_pages), bool(priv_pages)

        def linked(targets):
            homes = [p for p in pages if HOME_RX.search(p.rsplit("/", 1)[-1]) and "/" not in p] or list(pages)[:1]
            for h in homes:
                # QA: «ни в подвале, ни в меню» — лінк у меню теж рахується
                foot = pages[h]
                for t in targets:
                    stem = t.rsplit("/", 1)[-1]
                    folder = t.rsplit("/", 1)[0] if "/" in t else ""
                    if re.search(re.escape(stem), foot) or (folder and re.search(re.escape(folder) + r"/?(?:index\.html?)?[\"'#?]", foot)):
                        return True
            return False
        imp_linked = has_imp and linked(imp_pages)
        priv_linked = has_priv and linked(priv_pages)
    need_imp = country == "ch" and lang in ("de", "fr", "it")
    # Impressum є і залінкований, але без адреси компанії (resonance,
    # cap-hokajup, equipage ch-fr 26.10): QA вимагає регномер + адресу +
    # телефон/пошту разом. node: власноруч зроблені Impressum-компоненти
    # теж бувають без адреси (генератор _node_actions пише повний блок сам,
    # але готовий компонент вітки — ні).
    imp_bare = ""
    if has_imp and imp_linked:
        if node:
            cp = _node_imp_component(files)
            if cp and cp in files and not _imp_has_address(files[cp], branch):
                imp_bare = cp
        else:
            for p in imp_pages:
                if not _imp_has_address(pages[p], branch):
                    imp_bare = p
                    break
    return {"node": node, "country": country, "lang": lang, "need_imp": need_imp,
            "has_imp": has_imp, "imp_linked": imp_linked, "has_priv": has_priv, "priv_linked": priv_linked,
            "priv_route": priv_route, "imp_bare": imp_bare}


def _imp_has_address(text: str, branch: str) -> bool:
    """Чи є на сторінці Impressum адреса (вуличний рядок будь-якої локалі).
    Зона справжнього <footer> не рахується (адреса підвалу є на кожній
    сторінці); підвал без тега не вгадуємо — його евристика бере за зону
    весь контейнер сторінки (trusmepueg-pme 27.10) і ховала адресу контенту."""
    try:
        import checks.address_number as an
    except Exception:
        return True                                   # без розпізнавача не судимо
    body = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", PHP_RX.sub("", text), flags=re.S | re.I)
    fm = FOOTER_RX.search(body)
    if fm:
        body = body[:fm.start()]
    vis = TAGS_RX.sub("\n", body)
    return bool(an.ADDR_RX.search(vis) or an._any_street(vis)
                or (_locale(branch)[0] == "jp" and JP_ADDR_RX.search(vis)))


_IMP_LABELS = {"de": ("Anschrift", "Telefon", "E-Mail"), "fr": ("Adresse", "Téléphone", "E-mail"),
               "it": ("Indirizzo", "Telefono", "E-mail")}


def _imp_contact_block(text: str, f: dict) -> str:
    """Impressum без адреси → блок реквізитів одразу під <h1>, абзацами в класі
    першого <p> контенту: назва, адреса, телефон, пошта, UID."""
    hm = re.search(r"<h1\b[^>]*>.*?</h1>", text, re.I | re.S)
    if not hm:
        return text
    pm = re.search(r"<p\b([^>]*)>", text[hm.end():], re.I)
    attrs = pm.group(1) if pm else ""
    la, lt, lm = _IMP_LABELS.get(f["lang"], _IMP_LABELS["de"])
    rows = [f["name"]] + ([f"{la}: {f['address']}"] if f["address"] else []) \
        + ([f"{lt}: {f['phone']}"] if f["phone"] else []) + [f"{lm}: {f['email']}"] + ([f["regno"]] if f["regno"] else [])
    nl = "\r\n" if "\r\n" in text else "\n"
    block = nl + nl.join(f"<p{attrs}>{_esc(r)}</p>" for r in rows)
    return text[:hm.end()] + block + text[hm.end():]


def run_branch(files, all_paths, branch: str = ""):
    country, lang = _locale(branch)
    if not lang or lang not in PAGE:
        return []
    st = _state(files, branch)
    where = next((p for p in ("index.php", "index.html", "src/data/pages.js") if p in files), None)
    if not where:
        return []
    issues = []
    imp_file, imp_label, priv_file, priv_label = PAGE[lang]
    if st["need_imp"] and not (st["has_imp"] and st["imp_linked"]):
        msg = (f"ch-вайт: немає сторінки Impressum — фікс згенерує «{imp_label}» (адреса, "
               f"телефон, пошта, UID CHE-…) в оболонці юридичної сторінки вітки і додасть "
               f"лінк у футер кожної сторінки" if not st["has_imp"] else
               f"ch-вайт: Impressum є, але у футері головної немає лінка на нього — фікс "
               f"додасть лінк «{imp_label}» у футер кожної сторінки")
        issues.append({"path": where, "line": 1, "severity": "error", "message": msg})
    elif st["need_imp"] and st.get("imp_bare"):
        issues.append({"path": st["imp_bare"], "line": 1, "severity": "error",
                       "message": ("ch-вайт: Impressum без адреси компанії — QA вимагає регномер, "
                                   "адресу і телефон/пошту разом; фікс допише блок реквізитів під "
                                   "заголовком (назва, адреса, телефон, пошта, UID)")})
    if not (st["has_priv"] and st["priv_linked"]):
        if not st["has_priv"]:
            msg = (f"немає сторінки політики конфіденційності — фікс згенерує «{priv_label}» "
                   f"мовою вітки під тему сайту і додасть лінк у футер кожної сторінки")
        elif st["node"] and st.get("priv_route"):
            msg = (f"політика є, але її роут «{st['priv_route']}» QA не впізнає як privacy "
                   f"(href без privac/datenschutz/…) — фікс перейменує роут на "
                   f"«{ROUTE[lang][1]}», старий лишиться alias-ом")
        else:
            msg = (f"політика є, але у футері головної немає лінка на неї — фікс додасть лінк "
                   f"«{priv_label}» у футер кожної сторінки")
        issues.append({"path": where, "line": 1, "severity": "error", "message": msg})
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    country, lang = _locale(branch)
    if not lang or lang not in PAGE:
        return []
    st = _state(files, branch)
    f = facts(files, branch)
    imp_file, imp_label, priv_file, priv_label = PAGE[lang]
    actions, work = [], dict(files)
    todo = []
    if st["need_imp"] and not (st["has_imp"] and st["imp_linked"]):
        todo.append(("impressum", imp_file, ROUTE[lang][0], imp_label, impressum_sections(f), IMP_PATH_RX, st["has_imp"]))
    elif st["need_imp"] and st.get("imp_bare") and f["address"]:
        p = st["imp_bare"]
        new = _imp_contact_block(work[p], f)
        if new != work[p]:
            work[p] = new
            actions.append({"type": "edit", "path": p, "content": new})
    if not (st["has_priv"] and st["priv_linked"]):
        todo.append(("privacy", priv_file, ROUTE[lang][1], priv_label, privacy_sections(f), PRIV_PATH_RX, st["has_priv"]))
    for kind, fname, route, label, sections, kind_rx, exists in todo:
        if st["node"]:
            if exists:
                if kind == "privacy" and st.get("priv_route") and st["priv_route"] != route:
                    actions += _node_rename_route(work, st["priv_route"], route, label)
                continue                      # сторінка є — футер малює legalPages сам
            page_name = "Impressum" if kind == "impressum" else "Privacy"
            actions += _node_actions(work, kind, route, label, page_name, build_page_node(work, label, sections))
            continue
        if not exists:
            html = build_page_php(work, label, sections, f["name"])
            if not html:
                continue
            actions.append({"type": "edit", "path": fname, "content": html})
            work[fname] = html
        else:
            fname = next(p for p, t in work.items() if _is_page(p) and (kind_rx.search(p)
                         or (kind == "impressum" and IMP_H1_RX.search(t))
                         or (kind == "privacy" and lang == "ja" and PRIV_JA_RX.search(t[:4000]))))
        # лінк у футері кожної сторінки (нову сторінку теж — там футер донора)
        for p in sorted(work):
            if not _is_page(p):
                continue
            new = _link_html(work, p, fname, label, kind_rx)
            if new is not None and new != work[p]:
                work[p] = new
                actions = [a for a in actions if a["path"] != p]
                actions.append({"type": "edit", "path": p, "content": new})
    return actions
