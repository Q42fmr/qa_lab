"""Назва сайту вітки — ЄДИНЕ джерело для чеків і фіксів.

Джерело (рішення 30.09.2026): ГОЛОВА <title> головної сторінки — частина до
роздільника: «Motor de Classe - Luxo discreto para cada viagem.» → «Motor de
Classe». Саме вона стоїть у колонці «Название» ClickUp, і саме title надійно
несе назву з діакритикою («Chovfuce Eszbuféfaa»), яку назва вітки калічить
(chovfuce-eszbufefaa). Фолбек, коли title немає/порожній/плейсхолдер —
назва вітки: borhe-ansabu-it-it → «Borhe Ansabu» (краще, ніж занімілий чек).
Джерело сховане за `expected(branch, files)`: наступна зміна (поле таски
ClickUp) знову міняє рівно це місце.

Тут же живе і механіка перейменування по сайту (`rename`): вона спільна
для php-чека `logo_domain` і vue-чека `logo_brand`, бо правила однакові:
  * міняються ПОВНА фраза старої назви і її перше слово окремо;
  * лише КАПІТАЛІЗОВАНІ входження («Chovfuce», «CHOVFUCE ESZBUFÉFAA») —
    lowercase лишається, і це автоматично захищає слаги, пошти й
    соцлінки (facebook.com/chovfuceeszbufefaa, @chovfuceesz,
    "name" у package.json);
  * межі — не всередині слова і не поруч із @ / . / - / — тобто
    email-и, домени й дефісні слаги не рвуться;
  * стиль регістру зберігається: UPPER → UPPER, Title → Title.
"""
import html as _html
import re

# суфікс локалі вітки: -br-pt, -ch-fr, -it-it, -my-en, -ar-es, -co-es …;
# «-2» за ним — номер партії (choa-nono-br-pt-2), не слово назви
_LOCALE_RX = re.compile(r"-[a-z]{2}-[a-z]{2}(?:-\d+)?$")
# префікс репозиторію vue-віток
_PREFIX_RX = re.compile(r"^nwf-")
# <title> головної; роздільник — як у photo_theme: пробіл-знак-пробіл;
# японські title ділить повноширинна риска «｜» (і «|») без пробілів
_TITLE_RX = re.compile(r"<title[^>]*>(.*?)</title\s*>", re.S | re.I)
_SPLIT_RX = re.compile(r"\s[—–|·-]\s|\s*[｜|]\s*")
_PLACEHOLDER_RX = re.compile(r"\{\{.*?\}\}")
# без роздільника весь title і є назвою — але лише коли він схожий на назву,
# а не на речення-слоган
MAX_BARE_TITLE = 48

def _flat(s: str) -> str:
    """Тільки букви й цифри, без діакритики й регістру."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.casefold() if c.isalnum())


def _drop_accented(s: str) -> str:
    """Варіант, де акцентована літера зникає цілком — так її губить назва
    вітки (Gestão → gest-o → gestobra)."""
    import unicodedata
    out = []
    for c in unicodedata.normalize("NFC", s):
        d = unicodedata.normalize("NFKD", c)
        if len(d) > 1 and any(unicodedata.combining(x) for x in d):
            continue
        out.append(c)
    return "".join(out)


# у назві вітки умляут розкладений у дві літери (Müller → mueller)
UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})


# латиниця без діакритики для НАПИСУ ЛОГО: спецлітери, які NFKD не
# розкладає, мапляться руками
_LATIN_MAP = str.maketrans({"ß": "ss", "ẞ": "SS", "æ": "ae", "Æ": "Ae",
                            "œ": "oe", "Œ": "Oe", "ø": "o", "Ø": "O",
                            "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
                            "þ": "th", "Þ": "Th", "ð": "d", "Ð": "D"})


def latin(s: str) -> str:
    """Строга латиниця для напису лого: «Câmera Alves» → «Camera Alves».

    Лого пишеться ТІЛЬКИ латинськими буквами — без символів над буквами,
    арабських/азіатських знаків (вимога 30.09.2026). Діакритика знімається
    (â→a), спецлітери розкладаються (ß→ss), все нелатинське (кирилиця,
    арабська, CJK) випадає. Без жодної латинської літери в результаті —
    '' (той, хто пише, бере фолбек, напр. назву з вітки)."""
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").translate(_LATIN_MAP))
    out = []
    for c in s:
        if unicodedata.combining(c):
            continue
        if c.isascii() and (c.isalnum() or c in " &'.,’-"):
            out.append(c)
        elif c.isspace():
            out.append(" ")
    res = " ".join("".join(out).split())
    return res if re.search(r"[A-Za-z]", res) else ""


def variants(text: str) -> list[str]:
    """Написання, які означають ту саму назву: з/без «&», умляути
    розкладені, діакритика знята або з'їдена."""
    seen, out = set(), []
    for base in (text.replace("&", " "), text.replace("&", " and ")):
        for v in (_flat(base), _flat(base.translate(UMLAUT)),
                  _flat(_drop_accented(base))):
            if v and v not in seen:
                seen.add(v)
                out.append(v)
    return out


def same(shown: str, expected: str) -> bool:
    """Чи «shown» і «expected» — одна назва (правопис сайту виграє)."""
    if not (shown or "").strip() or not (expected or "").strip():
        return False
    return _flat(expected) in set(variants(shown))

def _from_branch(branch: str) -> str:
    """«Borhe Ansabu» з borhe-ansabu-it-it; '' — коли вивести нічого."""
    s = _PREFIX_RX.sub("", (branch or "").strip().lower())
    s = _LOCALE_RX.sub("", s)
    if re.fullmatch(r"[a-z]{2}-[a-z]{2}", s):
        return ""                            # гола локаль — назви немає
    words = [w for w in s.split("-") if w]
    return " ".join(w.capitalize() for w in words)


_META_NAME_RX = re.compile(
    r'<meta\s+(?:name|property)="(?:application-name|og:site_name'
    r'|apple-mobile-web-app-title)"\s+content="([^"]+)"', re.I)


def _title_parts(text: str) -> list[str]:
    """Частини <title> сторінки: розбиті роздільником, чисті, без слоганів."""
    m = _TITLE_RX.search(text)
    if not m:
        return []
    raw = _html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    if not raw or _PLACEHOLDER_RX.search(raw):
        return []
    out = []
    for p in _SPLIT_RX.split(raw):
        p = p.strip().rstrip(".,;:!")
        if p and len(p) <= MAX_BARE_TITLE and re.search(r"\w", p, re.U):
            out.append(p)
    return out


# Сторінкові слова — НЕ назва сайту. 30.09 head-евристика взяла «Accueil»
# («Головна» французькою) за назву і автофікс перейменував «Visee Loum» на
# «Accueil» по всьому вайту; консенсус це виправив для здорових віток, але
# зіпсована («Accueil — Accueil» на кожній сторінці) самоузгоджена — без
# цього гейта вона лишалась би «валідною» навіки.
PAGE_WORDS = frozenset(map(str.lower, (
    "accueil", "home", "homepage", "start", "startseite", "willkommen",
    "início", "inicio", "principal", "главная", "головна",
    "contact", "contacts", "contato", "contatos", "contacto", "contactos",
    "contatti", "kontakt", "about", "about us", "à propos", "sobre",
    "sobre nós", "chi siamo", "über uns", "services", "serviços",
    "servicios", "servizi", "faq", "blog", "menu", "portfolio",
    "merci", "thank you", "obrigado", "gracias", "grazie", "danke",
    # японські сторінкові слова: головна, контакти, про компанію, доступ…
    "ホーム", "トップ", "トップページ", "お問い合わせ", "お問合せ", "会社概要",
    "会社情報", "アクセス", "ブログ", "お知らせ", "よくある質問", "私たちについて",
    "プライバシーポリシー", "個人情報保護方針", "特定商取引法に基づく表記",
)))


def _is_page_word(part: str) -> bool:
    return part.strip().lower() in PAGE_WORDS


def from_title(files: dict | None, branch: str = "") -> str:
    """Назва сайту з <title>-ів вітки, '' — коли не вивести.

    Title буває обох форматів: «Назва - слоган» І «Сторінка — Назва»
    (кейс tubiepa 30.09: голова index-а — «Início», тобто «Головна», а
    назва стоїть хвостом на кожній сторінці). Тому:
      1. КОНСЕНСУС: частина, що повторюється у titles ≥2 різних сторінок,
         — це і є назва (сторінкові слова не повторюються);
      2. голова title головної; якщо голова не схожа на назву вітки, а
         ХВІСТ схожий — береться хвіст;
      3. meta application-name / og:site_name — лише коли title-ів немає:
         у кейсі підміненої назви og нерідко ще несе чужу, title — істину;
    слогани ріжуться довжиною (> MAX_BARE_TITLE), плейсхолдери — геть."""
    files = files or {}
    pages = [(p, files[p]) for p in sorted(files)
             if p.rsplit(".", 1)[-1].lower() in ("html", "htm", "php", "vue")]
    # 1) консенсус: скільки РІЗНИХ сторінок несуть цю частину в title
    count: dict[str, int] = {}
    spell: dict[str, str] = {}
    for _p, text in pages:
        for part in set(map(_flat, _title_parts(text))):
            count[part] = count.get(part, 0) + 1
    for _p, text in pages:                       # перше написання — канон
        for part in _title_parts(text):
            spell.setdefault(_flat(part), part)
    bvars = set(variants(_from_branch(branch))) if branch else set()
    best = [k for k, n in count.items()
            if n >= 2 and not _is_page_word(spell.get(k, k))]
    if best:
        best.sort(key=lambda k: (-count[k], k not in bvars, len(k)))
        return spell[best[0]]
    # 2) голова title головної; хвіст — якщо саме він схожий на назву вітки
    for path in sorted((p for p, _t in pages
                        if p.rsplit("/", 1)[-1].lower().startswith("index.")),
                       key=lambda p: (p.count("/"), p)):
        parts = [p for p in _title_parts(files[path])
                 if not _is_page_word(p)]
        if not parts:
            continue
        head, tail = parts[0], parts[-1]
        if bvars and _flat(head) not in bvars and _flat(tail) in bvars:
            return tail
        return head
    # 3) явна meta-назва — коли з title-ів не вивелось нічого
    for _p, text in pages:
        m = _META_NAME_RX.search(text)
        if m:
            name = _html.unescape(m.group(1)).strip()
            if name and not _PLACEHOLDER_RX.search(name) \
                    and not _is_page_word(name) \
                    and len(name) <= MAX_BARE_TITLE:
                return name
    return ""


def expected(branch: str, files: dict | None = None) -> str:
    """Очікувана назва сайту: з <title>-ів вітки, фолбек — назва вітки."""
    return from_title(files, branch) or _from_branch(branch)


# перше слово, коротше за це, окремо не перейменовуємо: standalone «DJ» чи
# «La» в тексті — надто ймовірний випадковий збіг
MIN_LONE_WORD = 4


def _rx(old: str) -> re.Pattern:
    words = old.split()
    full = r"\s+".join(re.escape(w) for w in words)
    lone = (re.escape(words[0])
            if len(words) > 1 and len(words[0]) >= MIN_LONE_WORD else None)
    body = f"({full})" + (f"|({lone})" if lone else "|(?!)")
    # межі: не всередині слова/слага/пошти. Крапка і слеш блокують лише
    # коли ПРОДОВЖУЮТЬ ім'я (chovfuce.com, chovfuce/page) — крапка в кінці
    # речення («© 2026 Chovfuce.») назву не ховає
    return re.compile(r"(?<![\w@./\-])(?:" + body + r")"
                      r"(?![\w@\-])(?!\.\w)(?!/\w)",
                      re.I | re.U)


# юридичні форми в хвості назви: «Laovalerie Ltda», «Quumvuv Sàrl», «Acme
# GmbH» — бренд тут ОДНЕ слово, і одиночне «Laovalerie» у title головної
# означає весь бренд, а не його перше слово (baggoetiepohsa 20.10: rename
# «Laovalerie Ltda» → «Baggoetie Pohsa» дав «Barbearia | …» у title)
LEGAL_SUFFIX_RX = re.compile(
    r"^(?:ltda\.?|lda\.?|ltd\.?|llc|inc\.?|s\.?a\.?|s\.?r\.?l\.?|sàrl|sarl|gmbh|ag"
    r"|sas|sasu|eurl|eireli|me|mei|pty|plc|oy|ab|as|bv|nv|kft|sp\. z o\.o\.|d\.o\.o\.|s\.?p\.?a\.?)$",
    re.I)


def _brand(name: str) -> str:
    """Назва без юридичного хвоста: «Laovalerie Ltda» → «Laovalerie»."""
    words = name.split()
    while len(words) > 1 and LEGAL_SUFFIX_RX.match(words[-1]):
        words.pop()
    return " ".join(words)


def rename(text: str, old: str, new: str) -> str:
    """Всі капіталізовані входження старої назви → нова, стиль регістру
    зберігається. Повертає текст (той самий обʼєкт, якщо міняти нічого).

    Уже ПОВНІ входження нової назви захищені маскою: коли нова назва
    містить стару («Quumvuv» → «Quumvuv Sàrl»), заміна без маски роздувала
    б «Quumvuv Sàrl» до «Quumvuv Sàrl Sàrl» (кейс quuskafs-ch-fr 01.10)."""
    old, new = (old or "").strip(), (new or "").strip()
    if not old or not new or old == new:
        return text
    # одиночне перше слово старої назви: перше слово нової — або весь бренд
    # нової, коли стара без юр. хвоста і є одним словом
    new_word = _brand(new) if _brand(old) == old.split()[0] else new.split()[0]

    masked: list[str] = []
    if _flat(old) != _flat(new) and _rx(old).search(new):
        # маскуємо ЛИШЕ повну фразу нової назви: лоне-гілка _rx(new)
        # замаскувала б і голі «Quumvuv», яким заміна якраз потрібна
        full_new = re.compile(
            r"(?<![\w@./\-])" + r"\s+".join(map(re.escape, new.split()))
            + r"(?![\w@\-])(?!\.\w)(?!/\w)", re.I | re.U)

        def mask(m: re.Match) -> str:
            masked.append(m.group(0))
            return f"\x00{len(masked) - 1}\x00"
        text = full_new.sub(mask, text)

    def sub(m: re.Match) -> str:
        src = m.group(0)
        if src[:1].islower():
            return src              # слаг/пошта/lowercase — не назва.
                                    # Безрегістрові письмена (арабська, тай)
                                    # не мають lowercase — вони проходять
        out = new if m.group(1) is not None else new_word
        letters = [c for c in src if c.isalpha()]
        if len(letters) > 1 and all(c.isupper() for c in letters):
            return out.upper()
        return out

    text = _rx(old).sub(sub, text)
    for i, orig in enumerate(masked):
        text = text.replace(f"\x00{i}\x00", orig)
    return text


def rename_files(files: dict, old: str, new: str) -> dict:
    """{path: новий текст} лише для файлів, де щось змінилось."""
    out = {}
    for path, text in files.items():
        cur = rename(text, old, new)
        if cur != text:
            out[path] = cur
    return out
