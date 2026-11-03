"""Контакти біля лід-форми vue-вайта: телефон, пошта, адреса, назва.

Кейс nwf-arike-jabgag-br-pt (скарга QA: «Нет вкладки контактов с телефоном,
почтой, адресом и названием»): секція форми — одна вузька колонка з карткою
форми, і ЖОДНОГО контакту поруч. У здорових вітках цієї ж сім'ї шаблонів
(заміряно на живій вибірці 25 nwf-віток з GitLab: 21 компонент форми БЕЗ
контактів проти 5 З) секція форми зверстана інакше: контейнер —
`grid lg:grid-cols-2`, форма в одній колонці, а поруч картка з контактами
(іконка + tel:/mailto:, адреса).

Що ловимо (run_branch):
  * компонент з `<form>` у `src/`, всередині якого немає ані `tel:`, ані
    `mailto:`, ані адресного рядка — error;
  * блок контактів Є, але неповний (бракує телефону/пошти/адреси/юрномера/
    назви) — error з переліком; назва судиться і в чужому блоці, якщо його
    рядки складаються в список;
  * якщо у ВСІЙ вітці немає ні телефону, ні пошти — репортимо чесно
    «даних не знайшов», і фікс нічого не вигадує.

Автофікс (fix_branch) — ЗАПУСК ЛИШЕ РУЧНИЙ (GROUP="review": автокоміт черги
бере лише auto+tests, тож review він не чіпає ніколи):
  * контейнер секції (`mx-auto`) стає ґридом здорової сім'ї:
    `grid lg:grid-cols-2 gap-8 items-stretch`, вузький `max-w-*` ширшає до
    `max-w-5xl` — наявна картка форми стає першою колонкою сама собою;
  * поруч додається картка контактів у СТИЛЯХ ВІТКИ: скруглення і тінь
    копіюються з картки форми, акцентний колір — з кнопки сабміту
    (`bg-teal-600` → лінки `text-teal-600`), тло картки нейтральне білe
    (як у здорових віток, де картка контрастує з секцією);
  * вміст: назва сайту (site_name.expected — колонка «Название» у ClickUp),
    телефон (перший `tel:` вітки з його видимим підписом), пошта (перший
    `mailto:`), адреса (footer_address._source_address, а без поштового
    індексу — перший адресний рядок з юридичних сторінок; локаль без
    гео-бази — і hr-форма без вуличного слова «Kapucinska 12, Osijek, …»);
  * підписи рядків — мовою вітки (суфікс локалі: -br-pt → Telefone/E-mail/
    Endereço, -co-es → Teléfono/Correo/Dirección, …);
  * блок Є, але не наша картка (кейс nwf-travb-stgicanhu-hr-hr 21.10:
    рядки «іконка в квадраті + h3 + p» у лівій колонці) — бракуюче
    дописується КЛОНОМ рядка цього ж списку (теги, класи, inline-стилі,
    коробка іконки; svg — іконка пункту), назва — h3 над рядками. Блок не
    складається в список (одна пошта під формою) — наша картка після нього.

Ідемпотентність: після фікса у компоненті є mailto/tel → детект мовчить,
повторний фікс — no-op.
"""
import html
import re

import checks.footer_address as footer_address

NAME = "Контакти біля форми"
GROUP = "review"   # ручний запуск: review не їде ні в автокоміт черги
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"address", "company", "email", "hours", "phone", "regno"}
                   # (groups() = auto+tests), ні в жоден автоматичний прогін
PROJECTS = ["node"]
DESCRIPTION = ("Картка контактів біля лід-форми мусить нести ВСЕ: назва "
               "(з title), телефон, пошта, адреса, CNPJ (br). Блока немає — "
               "фікс (РУЧНИЙ) створює grid здорової сім'ї з повною карткою; "
               "блок Є, але неповний — дописує, чого бракує, у стилі блока. "
               "Футерні дані пріоритетні (лишаються і дублюються), решта — "
               "з гео-баз локалі (geo_phones/geo_addresses) і пулу CNPJ.")
FILES = ["*.vue", "*.html", "*.htm"]

FORM_RX = re.compile(r"<form\b", re.I)
CONTACT_RX = re.compile(r"\b(?:tel|mailto):", re.I)
TEL_LINK_RX = re.compile(r'href="(tel:[^"]+)"[^>]*>\s*([^<]*?)\s*<', re.I)
TEL_ANY_RX = re.compile(r'tel:([+\d][\d\s().\-]{6,})', re.I)
MAIL_RX = re.compile(r'mailto:([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+)', re.I)
# контейнер секції: перший div з mx-auto після <section>
CONTAINER_RX = re.compile(r'<div\b[^>]*\bclass\s*=\s*"([^"]*\bmx-auto\b[^"]*)"[^>]*>',
                          re.I)
BTN_ACCENT_RX = re.compile(
    r'<button\b[^>]*\bclass\s*=\s*"[^"]*\bbg-([a-z]+-\d{2,3})\b', re.I)
CARD_RX = re.compile(r'<div\b[^>]*\bclass\s*=\s*"([^"]*\b(?:rounded|shadow)[^"]*)"',
                     re.I)
MAXW_RX = re.compile(r"\bmax-w-(?:xs|sm|md|lg|xl|2xl|3xl|4xl)\b")
ROUND_RX = re.compile(r"\brounded(?:-[a-z0-9]+)?\b")
SHADOW_RX = re.compile(r"\bshadow(?:-[a-z0-9]+)?\b")
DIV_TOKEN_RX = re.compile(r"<(/?)div\b", re.I)
# адресний рядок без вимоги поштового індексу — фолбек для віток, де адреса
# в юридичних сторінках коротка («Rua das Orquídeas, Fortaleza, Brasil»).
# БЕЗ re.I і лише у legal-сторінках: з re.I «Via» ловило «via package.json:
# "generate": …» у тексті про деплой (кейс nwf-enhupse-mazozvo-br-pt) —
# і сміття їхало в картку як «адреса»
# {5,120}: повна hr-адреса з жупанією довша за 80 і різалась на «…, Hrvatsk»
# (quaqbik-papbcapd 21.10); прозовий хвіст далі зрізає _trim_addr
ADDR_LINE_RX = re.compile(footer_address.STREET_RX.pattern + r"[^<>{}\n]{5,120}")
LEGALISH_RX = re.compile(r"(?i)term|privac|legal|polit|impress|datenschutz"
                         r"|aviso|cookie|contact|kontakt|contato")
# код-пунктуація: адреса такого не містить, а рядок з конфіга — завжди
_CODEY_RX = re.compile(r'[:"{}=&\\]|\.(?:json|cjs|mjs|js|ts)\b')
_FOOTERISH_RX = re.compile(r"(?i)footer|bottom|contact|kontakt|contato|contacto")
# хвіст після адреси в одному текстовому вузлі: графік, телефон, роздільники
# «·»/«•» НЕ ріжуть: у nwf-шаблоні це роздільник ПОЛІВ адреси
# («Ulica Slobode 14 · Split · Hrvatska», breza 20.10)
_ADDR_TAIL_RX = re.compile(r"\s*(?:\||–\s|—\s|\bRadno vrijeme\b|\bHor[aá]rio\b|\bÖffnungszeiten\b"
                           r"|\bOpening hours\b|\bHoraires?\b|\bOrari\b|\bTel\.?\b|\bPhone\b|\bE-?mail\b"
                           r"|\bMon(?:day)?\b|\bSeg(?:unda)?\b|\bPonedjeljak\b|\bLun(?:es|edì)?\b)", re.I)


_UP = "A-ZÀ-ÖØ-ÞČĆĐŠŽ"
# адреса БЕЗ вуличного слова — хорватська норма: «Kapucinska 12, Osijek,
# Osječko-baranjska županija 31000, Hrvatska», «Korzo 15 · Rijeka 51000»;
# тип вулиці з малої ПІСЛЯ назви — «Kapucinska ulica 9», «Biljska cesta 37»,
# «Hercegovačka ul. 19». Кейс nwf-travb-stgicanhu-hr-hr 21.10: адреса є в
# terms, STREET_RX її не бачить, гео-бази hr-hr немає — у вітки «адреси
# нема», і чек мовчав (128 з 260 hr-віток). Якір — номер будинку (1–3
# цифри: «Od 2015 ·» — рік, не номер), за яким одразу поле або індекс.
_NAME_WORD = r"[^\W\d_]+(?:-[^\W\d_]+)*\.?"
BARE_ADDR_RX = re.compile(
    rf"(?<![\w.-])[{_UP}][^\W\d_]*(?:-[^\W\d_]+)*\.?(?:[ \t]+{_NAME_WORD}){{0,4}}"
    rf"[ \t]+[1-9]\d{{0,2}}[a-zA-Z]?\b(?=[ \t]*(?:[,·]|\d{{5}}\b))[^<>{{}}\n]{{0,140}}")
_HOUSE_RX = re.compile(r"[ \t]([1-9]\d{0,2}[a-zA-Z]?)\b(?=[ \t]*(?:[,·]|\d{5}\b))")
# проза перед назвою вулиці («Ured se nalazi na Vukovarskoj 42», «Ako ste
# mlađi od 18, …»): назва починається ПІСЛЯ останнього службового слова
_STOP_WORDS = {"a", "i", "u", "na", "je", "su", "se", "smo", "ste", "od", "za",
               "sa", "s", "te", "ili", "mi", "vi", "nas", "vas", "gdje", "koji",
               "koja", "koje", "ovdje", "the", "of", "at", "in", "on", "to",
               "is", "our", "we"}
_ADDR_LABEL_RX = re.compile(
    r"^(?:Adresa|Address|Adres|Naslov|Endere[çc]o|Direcci[óo]n|Indirizzo"
    r"|Adresse|Sjedi[šs]te|Lokacija|Sede)\b\s*:?\s*", re.I)
# речення після адреси («…, 21000 Split. Ovdje pružamo usluge…»): крапка,
# за якою ≥3 слова; «Of. B, Caballito» (ar-es) — скорочення, не речення
_SENTENCE_RX = re.compile(r"\.\s+(?=[^\W\d_]{3,}(?:[ \t]+[^\W\d_,·.]+){2,})")
# індекс поруч з містом: «31000 Osijek», «31327, Bilje», «Rijeka 51000»;
# «98765-4321» — телефон, не індекс
_POSTAL_SEEN_RX = re.compile(
    rf"\b\d{{5}}\b(?!-\d)[ \t]*[,·]?[ \t]*[{_UP}]"
    rf"|[{_UP}][^\W\d_]+,?[ \t]+\d{{5}}\b(?!-\d)")


def _cut_prose(rest: str) -> str:
    """Хвіст адреси (текст ПІСЛЯ номера будинку) без прози: речення після
    крапки, поле з малої з ≥2 слів («…, gdje vas čeka…», «…, para una
    asesoría…»; «sala 802» — одне слово, лишається), порожні поля
    («Varaždin, , Hrvatska»)."""
    m = _SENTENCE_RX.search(rest)
    if m:
        rest = rest[:m.start()]
    for m in re.finditer(r"[,·]", rest):
        seg = re.split(r"[,·]", rest[m.end():], 1)[0].strip()
        if seg[:1].islower() and len(re.findall(r"[^\W\d_]{2,}", seg)) >= 2:
            rest = rest[:m.start()]
            break
    return re.sub(r"([,·])(?:\s*[,·])+", r"\1", rest).rstrip(" .,;·|")


def _house_end(s: str) -> int:
    """Звідки починається хвіст адреси: кінець номера будинку, а без номера —
    кінець першого поля («Rua das Orquídeas, Fortaleza»)."""
    d = re.search(r"\d+", s)
    return d.end() if d else len(re.split(r"[,·]", s, 1)[0])


def _trim_addr(s: str) -> str:
    s = html.unescape(" ".join(s.split()))
    m = _ADDR_TAIL_RX.search(s)
    if m and m.start() > 8:
        s = s[:m.start()]
    a = _house_end(s)
    return (s[:a] + _cut_prose(s[a:])).strip(" .,;|")


def _bare_matches(line: str) -> list:
    """[(start, адреса)] безслівних адрес у рядку з нормалізованими пробілами.
    Валідна: після номера поле з великої/індекс, і індекс або ≥2 поля —
    «GDPR član 6, točka 1», «Klauzula 5 · 05» адресами не стають. Уламок
    адреси, що вже почалась номером («SGAS 913 Bloco C, Loja 8, Brasília»),
    адресою не є."""
    out = []
    for m in BARE_ADDR_RX.finditer(line):
        raw = m.group(0)
        hn = _HOUSE_RX.search(raw)
        if not hn:
            continue
        words = list(re.finditer(r"\S+", raw[:hn.start()]))
        stop = [i for i, w in enumerate(words) if w.group(0).lower() in _STOP_WORDS]
        if stop:
            words = words[stop[-1] + 1:]
        if not words:
            continue
        head = raw[words[0].start():hn.start()]
        street = _ADDR_LABEL_RX.sub("", head)
        if not street[:1].isupper():
            continue
        start = m.start() + words[0].start() + len(head) - len(street)
        pre = line[:start].rstrip()
        if pre.endswith((",", "·")) and re.search(r"\d", pre):
            continue
        rest = raw[hn.end():]
        tm = _ADDR_TAIL_RX.search(rest)
        rest = _cut_prose(rest[:tm.start()] if tm else rest)
        segs = [x.strip() for x in re.split(r"[,·]", rest) if x.strip()]
        if not segs or not (segs[0][0].isupper() or segs[0][0].isdigit()):
            continue
        if len(segs) < 2 and not re.search(r"\b\d{5}\b", rest):
            continue
        cand = f"{street} {hn.group(1)}{rest}"
        if not _CODEY_RX.search(cand):
            out.append((start, cand))
    return out


# індекс (4–6 цифр), не рік: «Osječko-baranja 31000», «Meta 500001»
_POSTAL_NUM_RX = re.compile(r"\b(?!(?:19|20)\d\d\b)\d{4,6}(?:-\d{3})?\b")
# рядок, що є лише вулицею з номером («Kapucinska 12», «Korzo 15»)
_BARE_STREET_RX = re.compile(
    rf"[{_UP}][^\W\d_]*(?:-[^\W\d_]+)*\.?(?:[ \t]+{_NAME_WORD}){{0,4}}"
    rf"[ \t]+[1-9]\d{{0,2}}[a-zA-Z]?")


def _bare_addrs(vis: str) -> list:
    """Безслівні адреси видимого тексту — по рядках. Адреса у двох <p>
    («Korzo 15» ⏎ «Rijeka, Primorsko-goranska županija 51000», kabitu-rasid)
    склеюється, коли наступний рядок — місто з індексом."""
    lines = [ln for ln in (" ".join(x.split()) for x in html.unescape(vis).split("\n")) if ln]
    out = []
    for i, ln in enumerate(lines):
        found = _bare_matches(ln)
        if (not found and i + 1 < len(lines) and _BARE_STREET_RX.fullmatch(ln)
                and re.match(rf"[{_UP}]", lines[i + 1])
                and _POSTAL_NUM_RX.search(lines[i + 1])):
            found = _bare_matches(ln + ", " + lines[i + 1])
        out += [c for _, c in found]
    return out


def _street_part(addr: str) -> str:
    """Перше поле адреси — вулиця з номером («Kapucinska 12»)."""
    return re.split(r"\s*[,·]\s*", addr or "", 1)[0].strip()


# індекс поруч з назвою місця («Split, 21000», «Meta 500001», «1003
# Lausanne»); «ažurirano 2023» — рік, не індекс
_POSTAL_CITY_RX = re.compile(
    rf"\b\d{{4,6}}(?:-\d{{3}})?\b,?[ \t]+[{_UP}]"
    rf"|[{_UP}][^\W\d_]+,?[ \t]+\d{{4,6}}(?:-\d{{3}})?\b")
# рядок-місто під адресою: 1–4 слова з великої (сполучники «de/do/na…» —
# з малої), без цифр: «Slavonski Brod», «Rio de Janeiro»
_CITY_LINE_RX = re.compile(
    rf"[{_UP}][^\W\d_]*(?:-[^\W\d_]+)*(?:[ \t]+(?:[{_UP}][^\W\d_]*(?:-[^\W\d_]+)*"
    rf"|[a-z]{{1,3}})){{0,3}}")


def _completeness(addr: str) -> tuple:
    """Ключ «повнішої» адреси: є індекс після вулиці, а з індексом — більше
    полів («Kapucinska 12, Osijek, …» у terms проти «Kapucinska 12, Osječko-
    baranjska županija 31000» з двох <p> privacy). Без індексу — перша
    знайдена («… Sala 402 Paris, França» із сусіднього <p> не «повніша»)."""
    rest = addr[len(_street_part(addr)):]
    postal = bool(_POSTAL_NUM_RX.search(rest))
    return postal, len(re.findall(r"[,·]", rest)) if postal else 0


def _clean_addr(s: str) -> str:
    """Адреса з текстового вузла footer_address._source_address: без підпису
    («Adresa: …»), без прози ДО адреси («Naša kancelarija … na adresi Ulica
    Ivana Zajca 15, 51000 Rijeka, gdje vas čekaju…», momentum-ai 21.10) і
    після неї. Префікс ріжеться, лише коли це проза (службові слова), підпис
    («Siège social:») чи назва фірми через кому — без цифр: «22 Jalan …»,
    «Av. Paseo Tollocan 1425» — це вже сама адреса."""
    s = _ADDR_LABEL_RX.sub("", html.unescape(" ".join((s or "").split())))
    starts = [m.start() for m in [ADDR_LINE_RX.search(s)] if m]
    starts += [st for st, _ in _bare_matches(s)[:1]]
    if starts and min(starts) > 0:
        pre = s[:min(starts)]
        if not re.search(r"\d", pre) and (
                pre.rstrip().endswith((":", ","))
                or any(w.lower() in _STOP_WORDS for w in re.findall(r"[^\W\d_]+", pre))):
            return _trim_addr(s[min(starts):])
    a = _house_end(s)
    return (s[:a] + _cut_prose(s[a:])).strip(" .,;|")


def _line_addrs(vis: str) -> list:
    """Адреси з вуличним словом у видимому тексті сторінки."""
    out = []
    for m in ADDR_LINE_RX.finditer(vis):
        cand = _trim_addr(m.group(0))
        # адреса у двох <p>: «Ulica Slobode 14» + «Split, … 21000» — без
        # міста/індексу дочіплюємо наступний рядок, якщо він — місто: з
        # індексом, полями через кому чи сама назва («Slavonski Brod», «Rio
        # de Janeiro»). «Posljednja ažuriranja», «Atualizado em 2023» під
        # адресою — дата сторінки, не місто (infucwomavu 21.10)
        if not re.search(r"\d{4,5}(?:-\d{3})?\b|,|·", cand):
            nxt = vis[m.end():m.end() + 160].split("\n")
            nxt = next((x.strip() for x in nxt[1:] if x.strip()), "") if len(nxt) > 1 else ""
            if (nxt and (_POSTAL_CITY_RX.search(nxt)
                         or (re.match(r"[A-ZÀ-Ý]", nxt) and re.search(r"[,·]", nxt))
                         or _CITY_LINE_RX.fullmatch(nxt))
                    and not re.search(r"@|\+\d|tel", nxt, re.I)):
                cand = cand + ", " + _trim_addr(nxt)
        if cand and not _CODEY_RX.search(cand) and ("," in cand or any(c.isdigit() for c in cand)):
            out.append(cand)
    return out


def _street_key(addr: str) -> str:
    """Вулиця без номера будинку: «Ulica Petra Krešimira IV 846» і «Ulica
    Petra Krešimira IV» — та сама вулиця (sakgucnez 26.10: після номера від
    address_number terms і privacy розходились, і картка брала сміття)."""
    return re.sub(r"[ \t]+[1-9]\d{0,3}[a-zA-Z]?$", "", _street_part(addr)).lower()


def _pass_addr(files: dict, finder) -> str:
    """Адреса з юридичних сторінок, далі з футера/контактів. Серед адрес тієї
    самої вулиці, що й перша знайдена, — найповніша: «Ulica Ivana Zajca 12»
    у privacy проти «…, Rijeka, 51000, Hrvatska» у terms (neutub-inegapafi);
    за рівної повноти — та, де є номер будинку."""
    for pass_rx in (LEGALISH_RX, _FOOTERISH_RX):
        cands = [c for path, t in files.items() if pass_rx.search(path)
                 for c in finder(_visible(t))]
        if cands:
            key = _street_key(cands[0])
            return max((c for c in cands if _street_key(c) == key),
                       key=lambda c: (_completeness(c),
                                      bool(re.search(r"\d", _street_part(c)))))
    return ""


# контакти, видимі ТЕКСТОМ у шаблоні (кейс encanto: email звичайним текстом,
# телефон через {{ phone }} — жодного tel:/mailto:)
EMAIL_TEXT_RX = re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", re.I)
PHONE_TEXT_RX = re.compile(r"\+?\d[\d\s().\-]{7,}\d")
PHONE_BIND_RX = re.compile(r"\{\{\s*[\w.]*(?:phone|tel)[\w.]*\s*\}\}", re.I)
# телефон видимим текстом беремо ЛИШЕ міжнародний (+55 …): без плюса
# PHONE_TEXT_RX ловить CNPJ/дати з legal-сторінок
PHONE_PLUS_RX = re.compile(r"\+\d[\d\s().\-]{7,}\d")
TEMPLATE_RX = re.compile(r"<template>(.*)</template>", re.S | re.I)
TAGS_RX = re.compile(r"<[^>]+>")
# прямі діти контейнера: будь-який тег на глибині 0 (void і самозакриті не
# рахуються за вхід у глибину)
_ANY_TAG_RX = re.compile(r"<(/?)([a-zA-Z][\w-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>")
_VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "path", "circle",
              "rect", "line", "polyline", "polygon", "use", "source"}
# сміттєві пошти з макетів: хости-заглушки і local-part «seu…» («ваша
# пошта») — це підказки у формах, не контакти вітки
_JUNK_MAIL_HOST_RX = re.compile(
    r"@(?:ex[ae]mplo?|example|email|e-?mail|dominio|seudominio|mail|contato"
    r"|test)\.[a-z]{2,}$", re.I)
_JUNK_MAIL_LOCAL_RX = re.compile(r"^(?:seu|tu|your|dein|votre)[\w.]*@", re.I)

# підписи картки за мовою вітки (останній сегмент суфікса локалі)
LABELS = {
    "pt": ("Contato", "Telefone", "E-mail", "Endereço"),
    "es": ("Contacto", "Teléfono", "Correo", "Dirección"),
    "de": ("Kontakt", "Telefon", "E-Mail", "Adresse"),
    "fr": ("Contact", "Téléphone", "E-mail", "Adresse"),
    "it": ("Contatti", "Telefono", "Email", "Indirizzo"),
    "en": ("Contact", "Phone", "Email", "Address"),
    "hr": ("Kontakt", "Telefon", "E-mail", "Adresa"),
    "nl": ("Contact", "Telefoon", "E-mail", "Adres"),
    "sl": ("Kontakt", "Telefon", "E-pošta", "Naslov"),
    "ja": ("お問い合わせ", "電話", "メール", "住所"),
    "ar": ("اتصل بنا", "الهاتف", "البريد الإلكتروني", "العنوان"),
}

_ICONS = {
    "tel": ('M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502'
            ' 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0'
            ' 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.7'
            '16 21 3 14.284 3 6V5z'),
    "mail": ('M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 '
             '00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z'),
    "pin": ('M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243'
            'a8 8 0 1111.314 0z M15 11a3 3 0 11-6 0 3 3 0 016 0z'),
    "doc": ('M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 '
            '01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'),
}

CNPJ_NUM_RX = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
UID_NUM_RX = re.compile(r"\bCHE-\d{3}\.\d{3}\.\d{3}\b")
_CH_RX = re.compile(r"[-.]ch-[a-z]{2}(?:-\d+)?$")
_BR_RX = re.compile(r"[-.]br-pt(?:-\d+)?$")
# мова підписів — останній сегмент суфікса локалі; «-2» за ним — номер партії
_LANG_RX = re.compile(r"-([a-z]{2,3})(?:-\d+)?$")


def _expected(branch: str, files: dict | None = None) -> str:
    """Назва сайту — site_name.expected; окремо, щоб підміняти в тестах."""
    try:
        import site_name
        return site_name.expected(branch, files)
    except Exception:
        return ""


def _lang(branch: str) -> tuple:
    m = _LANG_RX.search((branch or "").lower())
    return LABELS.get(m.group(1) if m else "", LABELS["en"])


def _form_components(files: dict):
    for path in sorted(files):
        if path.endswith(".vue") and FORM_RX.search(files[path]):
            yield path, files[path]


def _has_contacts(text: str) -> bool:
    """Чи компонент УЖЕ показує контакти. Не лише tel:/mailto: — у сім'ї
    encanto пошта стоїть звичайним текстом, а телефон — байндингом
    {{ phone }}; судити треба видимий ТЕКСТ шаблону (без тегів і атрибутів),
    інакше placeholder="seuemail@contato.com" рахувався б контактом."""
    if CONTACT_RX.search(text):
        return True
    m = TEMPLATE_RX.search(text)
    if PHONE_BIND_RX.search(m.group(1) if m else text):
        return True
    visible = _visible(text)
    return bool(EMAIL_TEXT_RX.search(visible) or PHONE_TEXT_RX.search(visible)
                or ADDR_LINE_RX.search(visible))


def _children_count(inner: str) -> int:
    """Скільки ПРЯМИХ дітей у контейнера: один — секція «картка форми», і
    ґрид зробить її колонкою; кілька — однcolumнний потік (заголовок, ряди,
    форма), і ґрид його розкидав би по комірках (кейс encanto)."""
    depth, count = 0, 0
    for m in _ANY_TAG_RX.finditer(inner):
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if tag in _VOID_TAGS or attrs.rstrip().endswith("/"):
            if not closing and depth == 0:
                count += 1
            continue
        if closing:
            depth = max(0, depth - 1)
        else:
            if depth == 0:
                count += 1
            depth += 1
    return count


def _visible(text: str) -> str:
    """Видимий текст шаблону: без тегів і атрибутів (плейсхолдери — атрибути,
    вони контактами не є). Для .html — весь файл."""
    m = TEMPLATE_RX.search(text)
    return TAGS_RX.sub(" ", m.group(1) if m else text)


def _text_email(files: dict, branch: str) -> str:
    """Пошта звичайним текстом (сім'ї residencia/retiro: info@домен без
    mailto:). Хост активного домену вітки — поза чергою; заглушки макета
    (seu@email.com, seu.email@exemplo.com) не беремо."""
    own = ""
    try:
        import domains
        own = (domains.active_for(branch) or "").strip().lower()
    except Exception:
        pass
    cands = []
    for t in files.values():
        cands += EMAIL_TEXT_RX.findall(_visible(t))
    for c in cands:
        if own and c.lower().endswith("@" + own):
            return c
    for c in cands:
        if not _JUNK_MAIL_HOST_RX.search(c) and not _JUNK_MAIL_LOCAL_RX.match(c):
            return c
    return ""


def _branch_data(files: dict, branch: str) -> dict:
    """Що вітка знає про себе: телефон (+видимий підпис), пошта, адреса."""
    phone = phone_text = email = ""
    for t in files.values():
        if not phone:
            m = TEL_LINK_RX.search(t)
            if m:
                phone, phone_text = m.group(1), m.group(2).strip()
            else:
                m2 = TEL_ANY_RX.search(t)
                if m2:
                    phone = "tel:" + m2.group(1)
                    phone_text = m2.group(1)
        if not email:
            m = MAIL_RX.search(t)
            if m:
                email = m.group(1)
        if phone and email:
            break
    if not email:
        email = _text_email(files, branch)
    if not phone:
        for t in files.values():
            m = PHONE_PLUS_RX.search(_visible(t))
            if m:
                phone_text = m.group(0).strip()
                phone = "tel:" + re.sub(r"[^\d+]", "", phone_text)
                break
    addr = _clean_addr(footer_address._source_address(files) or "")
    if not addr:
        # спершу юридичні, потім футер/контакти: адреса без індексу
        # («Ulica Petra Preradovića 12, Osijek», homtud-ficemvi 19.10)
        # _source_address не бачить (вимагає поштовий код і legal-сторінку)
        addr = _pass_addr(files, _line_addrs)
    try:
        import checks.address_number as _an
    except Exception:
        _an = None
    hr = bool(_an and _an._is_hr(branch))
    if not addr and hr:
        # hr: справжня адреса вітки без вуличного слова («Kapucinska 12,
        # Osijek, …», trost 21.10) — раніше за гео-базу: та з'явилась 26.10 і
        # перебивала б реальну адресу вигаданою
        addr = _pass_addr(files, _bare_addrs)
    if not addr and _an:
        # гео-фолбек (прохання 01.10: картка без адреси — не картка):
        # ширший legal-екстрактор address_number, далі гео-база локалі
        addr = _an._legal_address(files, branch) or _an._geo_pick(branch)
    if not addr:
        # локаль без гео-бази і без вуличного слова в адресі: там, де гео-база
        # є, порядок вибору адреси не змінюється
        addr = _pass_addr(files, _bare_addrs)
    if addr and hr:
        addr = _with_house_number(addr, branch)
    if not phone:
        # телефону немає ніде — детермінований з гео-бази номерів
        try:
            import checks.geo_phone as _gp
            num = _gp._pick(branch)
            if num:
                phone_text = num
                phone = "tel:" + _gp._tel_href(num)
        except Exception:
            pass
    # юрномер: CNPJ (br-pt) або UID (ch-*) — зі сторінок, інакше з того
    # самого пулу, з якого бере відповідний чек (cnpj / uid_che)
    regno = ""
    is_ch = bool(_CH_RX.search((branch or "").lower()))
    num_rx, label = (UID_NUM_RX, "UID: ") if is_ch else (CNPJ_NUM_RX, "CNPJ ")
    for t in files.values():
        m = num_rx.search(t)
        if m:
            regno = label + m.group(0)
            break
    if not regno and (is_ch or (_BR_RX.search((branch or "").lower())
                                and not _foreign_registered(files))):
        try:
            import cnpj_pool
            import uid_pool
            main = next((files[p] for p in ("index.php", "index.html")
                         if p in files), next(iter(files.values()), ""))
            num = (uid_pool if is_ch else cnpj_pool).pick(branch, main) or ""
            regno = label + num if num else ""
        except Exception:
            pass
    return {"phone": phone, "phone_text": phone_text or phone.replace("tel:", ""),
            "email": email, "addr": addr, "regno": regno,
            "name": _expected(branch, files)}


def _foreign_registered(files: dict) -> bool:
    """Іноземна юрособа на br-pt вайті (RCS/SIREN, норвезький Org.nr.) — те
    саме правило, що й у чеку cnpj: CNPJ з пулу картці не потрібен
    (TECH-29349, arikejabgag 28.10)."""
    try:
        import checks.cnpj as _cn
        return _cn._foreign_registered(files)
    except Exception:
        return False


def _with_house_number(addr: str, branch: str) -> str:
    """hr: адреса без номера будинку («Ulica Petra Krešimira IV, Šibenik,
    22000») QA не розпізнає (sakgucnez 26.10). Номер — той самий, що
    address_number вставить у решту сторінок: детермінований (вітка, вулиця).
    Одне поле без міста — не адреса, номер йому не допоможе."""
    import checks.address_number as _an
    street = _street_part(addr)
    if not street or street == addr.strip() or not _an._hr_missing_number(addr):
        return addr
    return f"{street} {_an._number_for(branch, street)}{addr[len(street):]}"


_ADDR_ROW_LABEL_RX = re.compile(
    r"^(?:Adresa|Address|Adres|Naslov|Endere[çc]o|Direcci[óo]n|Indirizzo"
    r"|Adresse|Sjedi[šs]te|Lokacija|Sede)$", re.I)


def _card_addr(text: str) -> str:
    """Значення адресного рядка НАШОЇ картки ('' — рядка нема): рядок з
    іконкою-піном чи підписом «Adresa/Endereço/…»."""
    span = _card_span(text)
    if not span:
        return ""
    for m in ROW_FULL_RX.finditer(text[span[0]:span[1]]):
        row = m.group(0)
        ps = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", x)).split())
              for x in re.findall(r"<p\b[^>]*>(.*?)</p>", row, re.S)]
        if len(ps) >= 2 and (_ICONS["pin"] in row or _ADDR_ROW_LABEL_RX.match(ps[0])):
            return ps[1]
    return ""


def _card_addr_stale(text: str, data: dict) -> bool:
    """Наша картка несе hr-адресу без номера будинку, а вітка знає повну
    (sakgucnez 26.10: «Ulica Petra Krešimira IV, Posljednje ažurirano 2023» —
    вулиця без номера з датою сторінки, склеєна старою вставкою)."""
    cur, want = _card_addr(text), data.get("addr") or ""
    if not cur or not want or cur == want:
        return False
    import checks.address_number as _an
    return _an._hr_missing_number(cur) and not _an._hr_missing_number(want)


def _div_end(text: str, open_end: int) -> int:
    """Позиція закривного </div> контейнера (з урахуванням вкладеності)."""
    depth = 1
    for m in DIV_TOKEN_RX.finditer(text, open_end):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return m.start()
    return -1


def _row(icon: str, inner: str, label: str, accent: str,
         label_cls: str = "text-gray-900") -> str:
    return (f'\n        <div class="flex items-start gap-3">\n'
            f'          <svg class="w-5 h-5 text-{accent} flex-shrink-0 mt-1" '
            f'fill="none" stroke="currentColor" viewBox="0 0 24 24">'
            f'<path stroke-linecap="round" stroke-linejoin="round" '
            f'stroke-width="2" d="{_ICONS[icon]}"/></svg>\n'
            f'          <div>\n'
            f'            <p class="font-sans font-bold text-sm {label_cls}">{label}</p>\n'
            f'            {inner}\n'
            f'          </div>\n'
            f'        </div>')


def _card(data: dict, labels: tuple, accent: str, shape: str) -> str:
    head, l_tel, l_mail, l_addr = labels
    rows = []
    if data["phone"]:
        rows.append(_row("tel",
                         f'<a href="{data["phone"]}" class="font-sans text-{accent} '
                         f'hover:opacity-80 text-sm">{data["phone_text"]}</a>',
                         l_tel, accent))
    if data["email"]:
        rows.append(_row("mail",
                         f'<a href="mailto:{data["email"]}" class="font-sans '
                         f'text-{accent} hover:opacity-80 text-sm break-all">'
                         f'{data["email"]}</a>',
                         l_mail, accent))
    if data["addr"]:
        rows.append(_row("pin",
                         f'<p class="font-sans text-gray-500 text-sm">{data["addr"]}</p>',
                         l_addr, accent))
    if data.get("regno"):
        rows.append(_row("doc",
                         f'<p class="font-sans text-gray-500 text-sm">'
                         f'{data["regno"]}</p>',
                         data["regno"].split(":")[0].split()[0], accent))
    name_html = (f'\n        <h3 class="font-sans font-bold text-xl text-gray-900 '
                 f'mb-6">{data["name"]}</h3>' if data["name"] else "")
    return (f'\n      <div class="bg-white {shape} p-8 lg:p-10 flex flex-col '
            f'justify-center">\n'
            f'        <span class="inline-block font-sans font-bold text-xs '
            f'uppercase tracking-wide text-{accent} mb-2">{head}</span>'
            f'{name_html}\n        <div class="space-y-5">'
            + "".join(rows) +
            '\n        </div>\n      </div>\n    ')


CARD_OPEN_RX = re.compile(r'<div[^>]*class="[^"]*space-y-5[^"]*"[^>]*>')
ROW_FULL_RX = re.compile(
    r'[ \t]*<div class="flex items-start gap-3">.*?</div>\s*</div>\n?', re.S)


def _is_contactish(s: str) -> bool:
    """Фрагмент несе контакт: tel/mailto, CNPJ або адресний рядок."""
    return bool("tel:" in s.lower() or "mailto:" in s.lower()
                or CNPJ_NUM_RX.search(s) or UID_NUM_RX.search(s)
                or ADDR_LINE_RX.search(_visible(s)))


def _card_span(text: str):
    """(inner_start, close_start) картки КОНТАКТІВ space-y-5; None — немає.

    space-y-5 носять і обгортки форм (кейс cagunoktu 02.10: фікс цілився у
    форму і клав рядки під кнопку) — карткою вважається лише div з
    контактним маркером усередині."""
    for m in CARD_OPEN_RX.finditer(text):
        end = _div_end(text, m.end())
        if end < 0:
            continue
        if _is_contactish(text[m.end():end]):
            return m.end(), end
    return None


def _orphan_rows(text: str) -> list:
    """Контактні row-блоки ПОЗА карткою — дублі від старих form-end вставок
    (кейс cagunoktu 02.10). Фічі-списки без tel/CNPJ/адреси не чіпаються."""
    span = _card_span(text)
    if not span:
        return []
    out = []
    for m in ROW_FULL_RX.finditer(text):
        if span[0] <= m.start() < span[1]:
            continue
        if _is_contactish(m.group(0)):
            out.append((m.start(), m.end()))
    return out


REGNO_NUM_RX = re.compile(CNPJ_NUM_RX.pattern + "|" + UID_NUM_RX.pattern)


def _regno_label(data: dict) -> str:
    """«CNPJ» / «UID» — перше слово рядка юрномера."""
    return (data.get("regno") or "").split(":")[0].split()[0] if data.get("regno") else ""


def _no_cnpj(s: str) -> str:
    """Текст без юрномерів (CNPJ/UID): їх цифри не можна рахувати телефоном
    (кейс padohvae 02.10: «54.399.238» зійшло за номер)."""
    return REGNO_NUM_RX.sub("", s)



H3_ROW_RX = re.compile(r'[ \t]*<h3[^>]*>.*?</h3>\n?', re.S)


def _card_broken(text: str) -> bool:
    """Картка є, але її вміст не зводиться до цілих row-блоків — слід
    кривої вставки (кейс padohvae 02.10): сирітські close, незагорнуті
    рядки. _div_end сам балансує, тому лічба div тут не ловить.
    h3-назва всередині картки — легітимний перший елемент (02.10)."""
    span = _card_span(text)
    if not span:
        return False
    inner = text[span[0]:span[1]]
    if not ROW_FULL_RX.search(inner):
        return False          # не наш почерк рядків — не судимо
    return bool(ROW_FULL_RX.sub("", H3_ROW_RX.sub("", inner)).strip())


def _name_seen(text: str, start: int, end: int, name: str) -> bool:
    """Чи видно назву сайту у вікні [start:end). Email-адреси вирізаються:
    «Inpigkavlipotu» всередині info@inpigkavlipotu.digital — не назва
    (02.10), а підрядковий збіг. Сутності й переноси нормалізуються:
    «Dorić &amp; Partneri», «Stošić⏎Partneri» — та сама назва."""
    window = _visible(text[max(0, start):max(0, end)])
    window = " ".join(html.unescape(re.sub(r"\S+@\S+", " ", window)).split())
    return " ".join(name.split()).lower() in window.lower()


def _addr_seen(visible: str, data: dict) -> bool:
    """Адреса вже є у видимому тексті блоку: вуличне слово, безслівна
    hr-адреса («Vatrogasna ul. 5, 31327, Bilje»), індекс поруч з містом
    («Šušnjevac 1 51218 Čavle»), чи вулиця адреси вітки («Korzo 15» при
    «Korzo 15 · Rijeka 51000 · Hrvatska»). Інакше вписана руками адреса
    іншого формату (brvoge, stodvqe, premium 21.10) дублювалась би."""
    flat = " ".join(html.unescape(visible).split())
    addr = data.get("addr") or ""
    street = _street_part(addr)
    if (ADDR_LINE_RX.search(visible) or _POSTAL_SEEN_RX.search(flat)
            or (addr and addr in flat) or (len(street) >= 6 and street in flat)
            or _bare_addrs(visible)):
        return True
    try:
        import checks.address_number as _an
        return bool(_an._any_street(visible))
    except Exception:
        return False


def _palette_wrong(text: str):
    """Картка є, та її палітра не відповідає тлу панелі: білі лейбли на
    світлому (кейс gechaoh-inwodqol 02.10 — картку не видно) чи темні на
    темному. Судимо по наших почерках лейблів."""
    span = _card_span(text)
    if not span:
        return False
    om = CARD_OPEN_RX.search(text)
    dark = _dark_panel(text, om.start())
    inner = text[span[0]:span[1]]
    if not ROW_FULL_RX.search(inner):
        return False
    white_marks = "text-white opacity-75" in inner or \
        'text-xl text-white"' in inner
    dark_marks = "text-sm text-gray-900" in inner
    return (white_marks and not dark) or (dark_marks and dark)


def _block_missing(text: str, data: dict, branch: str) -> list:
    """Чого бракує ІСНУЮЧОМУ контакт-блоку (02.10: картка мусить нести все —
    телефон, пошту, адресу, CNPJ на br). Якщо є наша картка space-y-5 —
    ТЕКСТОВІ евристики судяться по ній: форма з type="tel" чи CNPJ-цифри
    інакше маскують діри. href-сигнали (tel:/mailto:) — по всьому файлу:
    клікабельний контакт поруч із формою вже є контактом (кейс
    inpigkavlipotu: пошта живе дизайнерським лінком над карткою)."""
    span = _card_span(text)
    scope = text[span[0]:span[1]] if span else text
    visible = _visible(scope)
    tm = TEMPLATE_RX.search(text)
    missing = []
    if data["phone"] and not ("tel:" in text.lower()
                              or PHONE_TEXT_RX.search(_no_cnpj(visible))
                              or (not span and PHONE_BIND_RX.search(
                                  tm.group(1) if tm else text))):
        missing.append(("телефон", "tel"))
    if data["email"] and not ("mailto:" in text.lower()
                              or EMAIL_TEXT_RX.search(visible)):
        missing.append(("пошта", "mail"))
    if data["addr"] and not _addr_seen(visible, data):
        missing.append(("адреса", "pin"))
    if data.get("regno") and not REGNO_NUM_RX.search(scope):
        missing.append((_regno_label(data), "doc"))
    if data["name"]:
        # назва сайту над карткою (кейс cagunoktu 02.10): шукаємо і в
        # картці, і в заголовку перед нею. Чужий блок списком рядків — по
        # всьому компоненту (trost 21.10: Email/Telefon у лівій колонці,
        # назви ніде; футер з формою підписки несе назву в ©). Список не
        # визначився — назву не судимо
        if span:
            win = (span[0] - 600, span[1])
        else:
            win = (0, len(text)) if _contact_list(text) else None
        if win and not _name_seen(text, win[0], win[1], data["name"]):
            missing.append(("назва", "name"))
    return missing


def run_branch(files, all_paths, branch=""):
    issues = []
    data = None
    for path, text in _form_components(files):
        if data is None:
            data = _branch_data(files, branch)
        line = text.count("\n", 0, FORM_RX.search(text).start()) + 1
        if _has_contacts(text):
            # блок Є — але чи цілий і повний? (02.10)
            if _card_span(text) is None and _row_groups(text):
                g0 = _row_groups(text)[0]
                issues.append({"path": path,
                               "line": text.count("\n", 0, g0[0]) + 1,
                               "severity": "error",
                               "message": ("контактні рядки без каркаса "
                                           "картки (злипаються, стилі не під "
                                           "тло панелі) — фікс перебудує їх "
                                           "у картку space-y-5")})
                continue
            if _card_broken(text):
                issues.append({"path": path, "line": line,
                               "severity": "error",
                               "message": ("картка контактів структурно бита "
                                           "(рядки не зводяться до цілих "
                                           "блоків) — фікс перебудує картку "
                                           "з даних вітки")})
                continue
            if _palette_wrong(text):
                issues.append({"path": path, "line": line,
                               "severity": "error",
                               "message": ("палітра картки не під тло панелі "
                                           "(білі рядки на світлому або темні "
                                           "на темному — картка невидима) — "
                                           "фікс перебудує у правильних "
                                           "кольорах")})
                continue
            if _card_addr_stale(text, data):
                issues.append({"path": path, "line": line,
                               "severity": "error",
                               "message": (f"адреса в картці без номера "
                                           f"будинку («{_card_addr(text)}») — "
                                           f"QA її не розпізнає; фікс "
                                           f"перепише на «{data['addr']}»")})
                continue
            orph = _orphan_rows(text)
            if orph:
                issues.append({"path": path,
                               "line": text.count("\n", 0, orph[0][0]) + 1,
                               "severity": "error",
                               "message": (f"контактні рядки продубльовані "
                                           f"поза карткою ({len(orph)} шт., "
                                           f"слід старої вставки під формою) "
                                           f"— фікс прибере дублі")})
                continue
            missing = _block_missing(text, data, branch)
            if missing:
                issues.append({"path": path, "line": line,
                               "severity": "error",
                               "message": (f"блок контактів біля форми "
                                           f"неповний — бракує: "
                                           f"{', '.join(m for m, _ in missing)}"
                                           f"; фікс допише у блок")})
            continue
        if not data["phone"] and not data["email"]:
            issues.append({"path": path, "line": line, "severity": "error",
                           "message": ("біля форми немає контактів, і у вітці "
                                       "я їх не знайшов (ні лінком, ні текстом) "
                                       "— додай руками, фіксу нема з чого "
                                       "будувати")})
            continue
        got = [x for x, ok in (("телефон", data["phone"]), ("пошта", data["email"]),
                               ("адреса", data["addr"]), (_regno_label(data), data.get("regno")),
                               ("назва", data["name"])) if ok]
        issues.append({"path": path, "line": line, "severity": "error",
                       "message": (f"біля форми немає блоку контактів — фікс "
                                   f"(ручний) додасть картку поруч у стилях "
                                   f"вітки: {', '.join(got)}")})
    return issues


def _rows_for(items, data, branch, accent, dark=False) -> list:
    """_row-рядки для пунктів (name, icon) з даних вітки.

    dark=True — панель з темним тлом (bg-*-600+): text-gray-900 там
    нечитабельний, а акцентні іконки зливаються (кейс inpigkavlipotu
    02.10) — уся палітра переходить на білу."""
    l_tel, l_mail, l_addr = _lang(branch)[1:4]
    if dark:
        accent = "white"
        label_cls = "text-white opacity-75"
        val_cls = "text-white opacity-90"
    else:
        label_cls = "text-gray-900"
        val_cls = "text-gray-500"
    rows = []
    for _name, icon in items:
        if icon == "tel":
            clean_tel = re.sub(r"[^\d+]", "", data["phone_text"] or
                               data["phone"].replace("tel:", ""))
            rows.append(_row("tel", f'<a href="tel:{clean_tel}" '
                        f'class="font-sans text-{accent} text-sm">'
                        f'{data["phone_text"]}</a>', l_tel, accent, label_cls))
        elif icon == "mail":
            rows.append(_row("mail", f'<a href="mailto:{data["email"]}" '
                        f'class="font-sans text-{accent} text-sm break-all">'
                        f'{data["email"]}</a>', l_mail, accent, label_cls))
        elif icon == "pin":
            rows.append(_row("pin", f'<p class="font-sans {val_cls} '
                        f'text-sm">{data["addr"]}</p>', l_addr, accent,
                        label_cls))
        elif icon == "doc":
            rows.append(_row("doc", f'<p class="font-sans {val_cls} '
                        f'text-sm">{data["regno"]}</p>', _regno_label(data),
                        accent, label_cls))
    return rows


_BG_ANY_RX = re.compile(r'(?<![:\w-])bg-(white|black|(?:[a-z]+)-(\d{2,3}))\b')
_PANEL_TAG_RX = re.compile(
    r'<(div|section|main|aside|form|footer|header)\b[^>]*>'
    r'|</(div|section|main|aside|form|footer|header)>')


def _dark_panel(text: str, at: int) -> bool:
    """Чи стоїть позиція на темному тлі: найближчий ОХОПЛЮЮЧИЙ контейнер
    з bg-класом — black чи відтінок 600+. Стек контейнерів, а не «останній
    bg у тексті»: bg-orange-600 КНОПКИ над карткою — не тло (кейс valores
    02.10), hover:/md:-префікси — тим паче (кейс gechaoh-inwodqol)."""
    stack = []
    for m in _PANEL_TAG_RX.finditer(text, 0, at):
        if m.group(0).startswith("</"):
            if stack:
                stack.pop()
        else:
            bg = None
            for bm in _BG_ANY_RX.finditer(m.group(0)):
                bg = bm
            stack.append(bg)
    for bm in reversed(stack):
        if bm:
            if bm.group(1) in ("white", "black"):
                return bm.group(1) == "black"
            return int(bm.group(2)) >= 600
    return False


def _row_groups(text: str) -> list:
    """Групи сусідніх row-блоків (між ними лише пробіли): [(start, end)]."""
    groups = []
    for m in ROW_FULL_RX.finditer(text):
        if groups and not text[groups[-1][1]:m.start()].strip():
            groups[-1] = (groups[-1][0], m.end())
        else:
            groups.append((m.start(), m.end()))
    return groups


# ------------------------------------------- чужий блок: дописати клоном рядка
# Блок контактів біля форми — НЕ наша картка (trost 21.10: ліва колонка,
# рядки «іконка в квадраті + h3 Email + p пошта»). Бракуюче дописується
# КЛОНОМ рядка того самого списку: ті самі теги, класи, inline-стилі
# (контраст-фікси), коробка іконки. Доти фікс клав нашу картку під кнопку
# форми — контакти розпадались на дві частини в різних стилях.
_EMAIL_BIND_RX = re.compile(r"\{\{\s*[\w.]*mail[\w.]*\s*\}\}", re.I)
_LINK_MARK_RX = re.compile(r"\b(tel|mailto):", re.I)
_ATTR_RX = re.compile(r"""\s+([^\s=>/"']+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?""")
# атрибути, що не їдуть у клон значення: лінк, умови показу, ідентичність
_DROP_ATTR_RX = re.compile(
    r"(?:v-bind)?:?(?:href|key)|target|rel|id"
    r"|v-(?:if|else-if|else|show|for|html|text)|@.*|v-on:.*", re.I)
# умови показу й ідентичність — геть з усього клону: «v-if="hasPhone"»
# рядка телефону ховав би адресу без телефону
_VUE_ATTR_RX = re.compile(
    r"""\s(?:v-if|v-else-if|v-show|v-for|:key|key|id)\s*=\s*(?:"[^"]*"|'[^']*')"""
    r"""|\sv-else\b(?![-\w])""")
_SVG_RX = re.compile(r"(<svg\b[^>]*>)(.*?)(</svg\s*>)", re.S | re.I)


def _elements(text: str, lo: int, hi: int) -> list:
    """Елементи розмітки між lo і hi: [start, open_end, close_start, end,
    tag, parent] у порядку відкриття; незакриті теги толеруються."""
    els, stack = [], []
    for m in _ANY_TAG_RX.finditer(text, lo, hi):
        tag = m.group(2).lower()
        if m.group(1):
            for k in range(len(stack) - 1, -1, -1):
                if els[stack[k]][4] == tag:
                    for j in stack[k + 1:]:
                        els[j][2] = els[j][3] = m.start()
                    els[stack[k]][2], els[stack[k]][3] = m.start(), m.end()
                    del stack[k:]
                    break
            continue
        parent = stack[-1] if stack else -1
        if tag in _VOID_TAGS or m.group(3).rstrip().endswith("/"):
            els.append([m.start(), m.end(), m.end(), m.end(), tag, parent])
        else:
            els.append([m.start(), m.end(), -1, -1, tag, parent])
            stack.append(len(els) - 1)
    for j in stack:
        els[j][2] = els[j][3] = hi
    return els


def _text_gaps(text: str, lo: int, hi: int) -> list:
    """[(start, end)] тексту між тегами."""
    out, pos = [], lo
    for m in _ANY_TAG_RX.finditer(text, lo, hi):
        if m.start() > pos:
            out.append((pos, m.start()))
        pos = m.end()
    if pos < hi:
        out.append((pos, hi))
    return out


def _markers(text: str, lo: int, hi: int, els: list) -> list:
    """[(pos, вид)] контактів шаблону поза <form>: tel / mail / pin / doc —
    з атрибутів (:href="'tel:' + phone") і видимого тексту ({{ phone }},
    пошта текстом, адреса, CNPJ/UID). «Tel:» текстом — підпис, не лінк:
    рахувався б окремим носієм і клон переписав би підпис замість значення."""
    out = [(m.start(), "tel" if m.group(1).lower() == "tel" else "mail")
           for m in _LINK_MARK_RX.finditer(text, lo, hi)
           if text.rfind("<", 0, m.start()) > text.rfind(">", 0, m.start())]
    for a, b in _text_gaps(text, lo, hi):
        chunk = text[a:b]
        if not chunk.strip():
            continue
        for rx, kind in ((EMAIL_TEXT_RX, "mail"), (_EMAIL_BIND_RX, "mail"),
                         (PHONE_BIND_RX, "tel"), (REGNO_NUM_RX, "doc")):
            out += [(a + m.start(), kind) for m in rx.finditer(chunk)]
        blank = REGNO_NUM_RX.sub(lambda m: " " * len(m.group(0)), chunk)
        out += [(a + m.start(), "tel") for m in PHONE_PLUS_RX.finditer(blank)]
        flat = " ".join(html.unescape(chunk).split())
        if (ADDR_LINE_RX.search(chunk) or _POSTAL_SEEN_RX.search(flat)
                or _bare_matches(flat)):
            out.append((a + len(chunk) - len(chunk.lstrip()), "pin"))
    forms = [(e[0], e[3]) for e in els if e[4] == "form"]
    return [(p, k) for p, k in out if not any(x <= p < y for x, y in forms)]


def _owner(els: list, pos: int) -> int:
    """Найглибший елемент, що містить позицію; −1 — жоден."""
    best = -1
    for i, e in enumerate(els):
        if e[0] > pos:
            break
        if pos < e[3]:
            best = i
    return best


def _chain(els: list, i: int) -> list:
    """Предки елемента від кореня до нього самого."""
    out = []
    while i >= 0:
        out.append(i)
        i = els[i][5]
    return out[::-1]


def _row_label(text: str, els: list, r: int, v: int):
    """Підпис рядка: перший листовий елемент рядка з текстом — не носій
    значення (ні його предок, ні нащадок) і не частина іконки."""
    rs, rend = els[r][0], els[r][3]
    vs, ve = els[v][0], els[v][3]
    parents = {e[5] for e in els}
    svgs = [(e[0], e[3]) for e in els if e[4] == "svg"]
    for i, e in enumerate(els):
        if not (rs < e[0] < rend) or i in parents:
            continue
        if vs <= e[0] < ve or (e[0] <= vs and ve <= e[3]):
            continue
        if any(a <= e[0] < b for a, b in svgs):
            continue
        inner = text[e[1]:e[2]]
        if (inner.strip() and "{{" not in inner and not EMAIL_TEXT_RX.search(inner)
                and not PHONE_PLUS_RX.search(inner)):
            return i
    return None


def _contact_list(text: str):
    """Список контактних рядків чужого блоку: найглибший контейнер, чиї
    прямі діти несуть по ОДНОМУ виду контакту, і таких дітей одного тегу
    ≥2. None — блок не списком (одна пошта під формою, усе в одному <p>):
    тоді фікс іде старим шляхом."""
    tm = TEMPLATE_RX.search(text)
    lo, hi = (tm.start(1), tm.end(1)) if tm else (0, len(text))
    els = _elements(text, lo, hi)
    marks = []
    for p, kind in _markers(text, lo, hi, els):
        o = _owner(els, p)
        if o >= 0:
            marks.append((kind, o, _chain(els, o)))
    while len(marks) >= 2:
        n = min(len(c) for _, _, c in marks)
        d = 0
        while d < n and len({c[d] for _, _, c in marks}) == 1:
            d += 1
        if d == 0 or any(len(c) <= d for _, _, c in marks):
            return None        # без спільного предка / контакт у тексті контейнера
        rows = {}
        for kind, _o, c in marks:
            rows.setdefault(c[d], set()).add(kind)
        multi = [r for r, kinds in rows.items() if len(kinds) > 1]
        if multi:
            # дитина з кількома видами — сам список глибше в ній (вступний
            # абзац з поштою над списком не рядок)
            r = max(multi, key=lambda r: len(rows[r]))
            marks = [x for x in marks if r in x[2]]
            continue
        order = sorted(rows, key=lambda r: els[r][0])
        tags = {}
        for r in order:
            tags[els[r][4]] = tags.get(els[r][4], 0) + 1
        tag = max(tags, key=tags.get)
        if tags[tag] < 2 or any(
                e[4] == "form" and els[r][0] <= e[0] < els[r][3]
                for r in order for e in els):
            return None
        info = []
        for r in order:
            if els[r][4] != tag:
                continue
            v = min((o for _k, o, c in marks if c[d] == r),
                    key=lambda o: len(_chain(els, o)))
            info.append({"row": r, "value": v, "label": _row_label(text, els, r, v)})
        box = marks[0][2][d - 1]
        return {"els": els, "box": box, "rows": info, "start": els[box][0],
                "end": els[box][3], "first": els[order[0]][0],
                "last": max(els[r][3] for r in order)}
    return None


def _value_html(text: str, els: list, vi: int, value: str, href: str) -> str:
    """Носій значення клону: той самий тег (<a> лише для tel/mail, під
    текст стає <p>), ті самі класи/стиль; дочірні теги (іконка в лінку)
    лишаються, текст — новий."""
    e = els[vi]
    head, tag = text[e[0]:e[1]], e[4]
    attrs = "".join(m.group(0) for m in _ATTR_RX.finditer(head, 1 + len(tag), len(head) - 1)
                    if not _DROP_ATTR_RX.fullmatch(m.group(1)))
    new_tag = "a" if href else ("p" if tag == "a" else tag)
    if href:
        attrs = f' href="{href}"' + attrs
    inner = text[e[1]:e[2]]
    gaps = [(a, b) for a, b in _text_gaps(inner, 0, len(inner)) if inner[a:b].strip()]
    if gaps:
        a, b = gaps[-1]
        m = re.search(r"\S(?:.*\S)?", inner[a:b], re.S)
        inner = inner[:a + m.start()] + value + inner[a + m.end():]
    else:
        inner += value
    return f"<{new_tag}{attrs}>{inner}</{new_tag}>"


def _swap_icon(s: str, kind: str) -> str:
    """Перша svg клону малює іконку пункту (кадр 24×24, як у _ICONS)."""
    m = _SVG_RX.search(s)
    if not m:
        return s
    head = m.group(1)
    if re.search(r"\bviewBox\s*=", head):
        head = re.sub(r"""\bviewBox\s*=\s*(?:"[^"]*"|'[^']*')""", 'viewBox="0 0 24 24"', head)
    else:
        head = head[:-1] + ' viewBox="0 0 24 24">'
    inner = m.group(2)
    lead, trail = inner[:len(inner) - len(inner.lstrip())], inner[len(inner.rstrip()):]
    path = (f'<path fill="none" stroke="currentColor" stroke-linecap="round" '
            f'stroke-linejoin="round" stroke-width="2" d="{_ICONS[kind]}"/>')
    return s[:m.start()] + head + lead + path + trail + m.group(3) + s[m.end():]


def _clone_row(text: str, lst: dict, tpl: dict, kind: str, label: str,
               value: str, href: str) -> str:
    """Рядок-клон: підпис і значення нові, решта (обгортки, класи, коробка
    іконки) — як у шаблонного рядка; умови показу знято."""
    els = lst["els"]
    r, v = els[tpl["row"]], els[tpl["value"]]
    edits = [(v[0], v[3], _value_html(text, els, tpl["value"], value, href))]
    if tpl["label"] is not None:
        e = els[tpl["label"]]
        m = re.search(r"\S(?:.*\S)?", text[e[1]:e[2]], re.S)
        if m:
            edits.append((e[1] + m.start(), e[1] + m.end(),
                          label.upper() if m.group(0).isupper() else label))
    s = text[r[0]:r[3]]
    for a, b, rep in sorted(edits, reverse=True):
        s = s[:a - r[0]] + rep + s[b - r[0]:]
    return _swap_icon(_VUE_ATTR_RX.sub("", s), kind)


def _line_sep(text: str, pos: int) -> str:
    """Перенос + відступ рядка, з якого починається pos, у стилі переносів
    файла (CRLF лишається CRLF); "" — перед pos на рядку є текст."""
    pre = text[text.rfind("\n", 0, pos) + 1:pos]
    return "" if pre.strip() else ("\r\n" if "\r\n" in text else "\n") + pre


# список рядків горизонтальний хоч на якомусь брейкпоінті: «flex» без
# «flex-col», «sm:flex-row», «md:grid-cols-2» (luco-chuwter: flex-col
# sm:flex-row — назва першою дитиною стала б колонкою ряду)
_ROW_LAYOUT_RX = re.compile(r"(?:^|\s)(?:[\w-]+:)?(?:flex-row|grid-cols-[2-9])\b")


def _insert_name(new: str, text: str, lst: dict, name: str) -> str:
    """h3-назва сайту: у вертикальному списку (space-y, flex-col) — перед
    першим контактним рядком, над горизонтальним — перед самим списком.
    Шрифт — як у заголовків компонента, колір — під тло панелі."""
    els = lst["els"]
    box = els[lst["box"]]
    cm = re.search(r'\bclass\s*=\s*"([^"]*)"', text[box[0]:box[1]])
    cls = cm.group(1) if cm else ""
    fm = re.search(r'<h[1-4]\b[^>]*\bclass\s*=\s*"[^"]*?'
                   r'\b(font-(?:sans|serif|mono|display|heading)\b[\w-]*)', text)
    font = fm.group(1) if fm else "font-sans"
    color = "text-white" if _dark_panel(text, box[1]) else "text-gray-900"
    if (_ROW_LAYOUT_RX.search(cls)
            or (re.search(r"(?<![\w:-])flex(?![\w-])", cls) and "flex-col" not in cls)):
        at, h3 = box[0], f'<h3 class="{font} font-bold text-xl {color} mb-4">{name}</h3>'
    else:
        at, h3 = lst["first"], f'<h3 class="{font} font-bold text-xl {color}">{name}</h3>'
    return new[:at] + h3 + _line_sep(text, at) + new[at:]


def _complete_list(text: str, lst: dict, missing: list, data: dict,
                   branch: str) -> str:
    """Дописати чужому списку бракуюче: рядки-клони після останнього рядка
    (шаблон для лінка — рядок з <a>, для тексту — без), назву — h3."""
    els = lst["els"]
    l_tel, l_mail, l_addr = _lang(branch)[1:4]
    labels = {"tel": l_tel, "mail": l_mail, "pin": l_addr,
              "doc": _regno_label(data)}
    clones = []
    for _name, kind in missing:
        if kind == "name":
            continue
        link = kind in ("tel", "mail")
        tpl = next((t for t in lst["rows"] if (els[t["value"]][4] == "a") == link),
                   lst["rows"][0])
        if kind == "tel":
            value = data["phone_text"]
            href = "tel:" + re.sub(r"[^\d+]", "", value or data["phone"].replace("tel:", ""))
        elif kind == "mail":
            value, href = data["email"], "mailto:" + data["email"]
        else:
            value, href = (data["addr"] if kind == "pin" else data["regno"]), ""
        clones.append(_line_sep(text, els[tpl["row"]][0])
                      + _clone_row(text, lst, tpl, kind, labels[kind], value, href))
    new = text[:lst["last"]] + "".join(clones) + text[lst["last"]:]
    if ("назва", "name") in missing:
        new = _insert_name(new, text, lst, data["name"])
    return new


def fix_branch(files, all_paths, branch=""):
    data = _branch_data(files, branch)
    if not data["phone"] and not data["email"]:
        return []
    labels = _lang(branch)
    actions = []
    for path, text in _form_components(files):
        if _has_contacts(text):
            am = BTN_ACCENT_RX.search(text)
            accent = am.group(1) if am else "gray-900"
            if _card_span(text) is None and _row_groups(text):
                # рядки без каркаса (кейс inpigkavlipotu 02.10): усі групи
                # зносяться, на місці першої постає канонічна картка; темна
                # панель отримує білу палітру, чужі інлайн-style зникають
                groups = _row_groups(text)
                first = groups[0][0]
                dark = _dark_panel(text, first)
                rest = text
                for st, e in sorted(groups, key=lambda t: -t[0]):
                    rest = rest[:st] + rest[e:]
                # пункт потрапляє в картку, якщо його нема ПОЗА групами:
                # дизайнерський mailto-лінк над карткою — вже пошта
                items = []
                if data["phone"] and "tel:" not in rest.lower():
                    items.append(("телефон", "tel"))
                if data["email"] and "mailto:" not in rest.lower():
                    items.append(("пошта", "mail"))
                if data["addr"] and not _addr_seen(_visible(rest), data):
                    items.append(("адреса", "pin"))
                if data.get("regno") and not REGNO_NUM_RX.search(rest):
                    items.append((_regno_label(data), "doc"))
                rows = _rows_for(items, data, branch, accent, dark=dark)
                name_cls = "text-white" if dark else "text-gray-900"
                head = ""
                if data["name"] and not _name_seen(text, first - 600, first,
                                                   data["name"]):
                    head = (f'\n          <h3 class="font-sans font-bold '
                            f'text-xl {name_cls}">{data["name"]}</h3>')
                indent = re.match(r"[ \t]*", text[first:]).group(0)
                card = (f'{indent}<div class="space-y-5 mt-8">{head}'
                        + "".join(rows) + f"\n{indent}</div>")
                new = text
                for st, e in sorted(groups, key=lambda t: -t[0]):
                    new = new[:st] + new[e:]
                new = new[:first] + card + "\n" + new[first:]
                actions.append({"type": "edit", "path": path, "content": new})
                continue
            if _card_broken(text) or _palette_wrong(text) \
                    or _card_addr_stale(text, data):
                # слід кривої вставки, невидима палітра чи адреса без номера —
                # блок перебудовується цілком у кольорах під тло
                span = _card_span(text)
                om = CARD_OPEN_RX.search(text)
                dark = _dark_panel(text, om.start())
                items = [("телефон", "tel")] if data["phone"] else []
                items += [("пошта", "mail")] if data["email"] else []
                items += [("адреса", "pin")] if data["addr"] else []
                items += [(_regno_label(data), "doc")] if data.get("regno") else []
                rows = _rows_for(items, data, branch, accent, dark=dark)
                hm = H3_ROW_RX.search(text[span[0]:span[1]])
                keep = ""
                if hm:
                    nm = re.search(r">([^<]*)</h3>", hm.group(0))
                    name_cls = "text-white" if dark else "text-gray-900"
                    keep = (f'\n          <h3 class="font-sans font-bold '
                            f'text-xl {name_cls}">{nm.group(1)}</h3>')
                new = text[:span[0]] + keep + "".join(rows) + "\n        " \
                    + text[span[1]:]
                actions.append({"type": "edit", "path": path, "content": new})
                continue
            orph = _orphan_rows(text)
            if orph:
                # дублі поза карткою знімаються окремою дією; доповнення
                # картки — наступним прогоном, уже на чистому тексті
                new = text
                for st, e in sorted(orph, key=lambda t: -t[0]):
                    new = new[:st] + new[e:]
                actions.append({"type": "edit", "path": path, "content": new})
                continue
            missing = _block_missing(text, data, branch)
            if not missing:
                continue
            span = _card_span(text)
            # чужий блок списком рядків (у т.ч. space-y-5 не нашого почерку,
            # кейс zebec): бракуюче — клоном його ж рядка, назва — h3 у списку
            lst = None if span and ROW_FULL_RX.search(text[span[0]:span[1]]) \
                else _contact_list(text)
            if lst:
                actions.append({"type": "edit", "path": path,
                                "content": _complete_list(text, lst, missing,
                                                          data, branch)})
                continue
            head = ""
            # палітра — як у картки: на темній панелі білі рядки (surjoke
            # 26.10: темні лейбли поруч з білими — «палітра не під тло»)
            om = CARD_OPEN_RX.search(text) if span else None
            dark = bool(om) and _dark_panel(text, om.start())
            if span and ("назва", "name") in missing:
                # h3-назва — першим елементом КАРТКИ (над рядками, під
                # розділювачем: саме там її очікують у стилях віток)
                head = (f'\n          <h3 class="font-sans font-bold text-xl '
                        f'{"text-white" if dark else "text-gray-900"}">{data["name"]}</h3>')
                text = text[:span[0]] + head + text[span[0]:]
                span = _card_span(text)
            missing = [mi for mi in missing if mi[1] != "name"]
            rows = _rows_for(missing, data, branch, accent, dark=dark)
            if not rows and not head:
                continue
            if span:
                # у нашу картку — сиблінгом, перед її закривним </div>
                ins, tail = span[1], "\n        "
            else:
                # чужий блок: після останнього контактного елемента
                anchor = -1
                for rx in (re.compile(r'href="tel:[^"]*"[^>]*>[^<]*</a>', re.I),
                           re.compile(r'href="mailto:[^"]*"[^>]*>[^<]*</a>',
                                      re.I)):
                    for m in rx.finditer(text):
                        anchor = max(anchor, m.end())
                if anchor < 0:
                    vm = ADDR_LINE_RX.search(_visible(text))
                    anchor = text.find("</p>", text.find(vm.group(0))) + 4 \
                        if vm and vm.group(0) in text else -1
                if anchor < 0:
                    # текстова пошта/биндинг без лінків (кейс encanto):
                    # рядки стають одразу після форми
                    fe = text.find("</form>")
                    anchor = fe + len("</form>") if fe >= 0 else -1
                if anchor < 0:
                    continue
                close = text.find("</div>", anchor)
                ins, tail = (close, "\n      ") if close >= 0 \
                    else (anchor, "\n      ")
                if rows:
                    # теж у каркас: інакше наступний прогін бачив би
                    # «рядки без каркаса» і перебудовував щойно вставлене
                    dark = _dark_panel(text, ins)
                    rows = _rows_for(missing, data, branch, accent, dark=dark)
                    head = ""
                    if data["name"] and not _name_seen(text, ins - 600, ins,
                                                       data["name"]):
                        name_cls = "text-white" if dark else "text-gray-900"
                        head = (f'\n          <h3 class="font-sans '
                                f'font-bold text-xl {name_cls}">'
                                f'{data["name"]}</h3>')
                    rows = ['<div class="space-y-5 mt-8">' + head
                            + "".join(rows) + "\n        </div>"]
            new = text[:ins] + "".join(rows) + (tail if rows else "") \
                + text[ins:]
            actions.append({"type": "edit", "path": path, "content": new})
            continue
        cm = CONTAINER_RX.search(text)
        if not cm:
            continue
        end = _div_end(text, cm.end())
        if end < 0:
            continue
        # стилі вітки: скруглення/тінь — з картки форми, акцент — з кнопки
        card_m = CARD_RX.search(text, cm.end())
        shape_src = card_m.group(1) if card_m else ""
        shape = " ".join(filter(None, [
            (ROUND_RX.search(shape_src) or ROUND_RX.search("rounded-md")).group(0),
            (SHADOW_RX.search(shape_src) or SHADOW_RX.search("shadow-sm")).group(0),
        ]))
        am = BTN_ACCENT_RX.search(text)
        accent = am.group(1) if am else "gray-900"
        inner = text[cm.end():end]
        if _children_count(inner) == 1 and "grid" not in cm.group(1).split():
            # одна дитина (картка форми) — ґрид здорової сім'ї: форма стає
            # лівою колонкою, картка контактів — правою
            cls = cm.group(1)
            new_cls = MAXW_RX.sub("max-w-5xl", cls)
            if "max-w-5xl" not in new_cls:
                new_cls = "max-w-5xl " + new_cls
            new_cls += " grid lg:grid-cols-2 gap-8 items-stretch"
            new_open = cm.group(0).replace(f'"{cls}"', f'"{new_cls}"', 1)
            new = (text[:cm.start()] + new_open + inner
                   + _card(data, labels, accent, shape)
                   + text[end:])
        else:
            # багатодітний однcolumнний потік (кейс encanto) або вже ґрид:
            # класи не чіпаємо, картка стає останнім блоком під формою
            card = _card(data, labels, accent, shape)
            card = card.replace('<div class="bg-white ',
                                '<div class="bg-white mt-8 ', 1)
            new = text[:end] + card + text[end:]
        actions.append({"type": "edit", "path": path, "content": new})
    return actions
