"""QA-нотатки з коментарів ClickUp: блок вітки → міні-фікси для картки.

Сапорт кидає один коментар на кілька віток (кейс 01.10):

    Можешь пофиксить, пожалуйста:

    nwf-paruino-proge-br-pt
    paruinoproge.pro
    - • Название в логотипе «Paruíno Progé» не строгой латиницей: «íé». ...
    - • Главная картинка (первый экран) не по теме: ...

    nwf-padohvae-da-proou-br-pt
    ...

Парсер ріже коментар на блоки за рядками-назвами віток, пункти — за
маркерами «- •»/«•»/«-», а кожному пункту дає коротку назву («фікс лого»,
«фікс фото») за словником формулювань QA — вони вже +- стандартизовані.
"""
from __future__ import annotations

import re

# рядок-назва вітки: слаг мінімум з трьох сегментів; сапорти пишуть і з
# крапкою всередині (bavmejxqul-gepima-semgikja.ch-ch-fr,
# stevbuvp-cletr.ca-ca-en-2) — домен (два сегменти, paruinoproge.pro)
# сюди не влазить
BRANCH_LINE_RX = re.compile(r"^[a-z][a-z0-9]*(?:[-.][a-z0-9]+){2,}$")
# рядок-домен: hostname з крапкою, без пробілів
DOMAIN_LINE_RX = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$", re.I)
# маркер пункту: «- •», «•», «-», «*» на початку рядка
ITEM_RX = re.compile(r"^\s*(?:[-*]\s*)?[•◦▪]\s*|^\s*[-*]\s+")
# @згадки в хвості пункту — шум для картки
MENTION_RX = re.compile(r"@[\w.\- ]+?(?=@|\s*$)")

# Словник міні-назв: ПОРЯДОК ВАЖЛИВИЙ — перший збіг перемагає
# («Домен не совпадает с названием» мусить ловитись раніше за «текст»).
_LABELS = [
    (r"куки|cookie|банн?ер.{0,12}соглас|соглас.{0,12}банн?ер", "фікс cookies"),
    (r"домен[^\n]*назван|назван[^\n]*домен|совпадает с доменом", "фікс домен≠назва"),
    # «Сайт называется Х, а в meta title — Y» / «изменить название на …» /
    # «Название сайта не совпадает с названием вайта» (реальний корпус 01.10)
    (r"сайт называется|назван[ие][^\n]{0,30}не совпада|изменить название"
     r"|поменять название|переименовать", "фікс назви"),
    (r"favicon|фавікон|фавикон|иконк[аи] (?:сайта|вкладк)", "фікс favicon"),
    (r"логотип|лого\b", "фікс лого"),
    (r"телефон|почта|адрес|контакт|реквизит", "фікс контакти"),
    # «СNPJ» у сапортів буває з КИРИЛИЧНОЮ С — ловимо обидві; контакти вище:
    # «добавить адрес, CNPJ» — контактний блок, а чистий «нет СNPJ» падає сюди
    (r"[cс]npj", "фікс CNPJ"),
    (r"\buid\b|\bche-?\d|handelsregister|mwst", "фікс UID"),
    (r"картинк|изображен|фото|hero|баннер|первый экран", "фікс фото"),
    (r"\bfaq\b|вопрос[^\n]{0,20}раскрыв", "фікс FAQ"),
    (r"цен[аы]|price|разделитель тысяч", "фікс цін"),
    (r"меню|навигац", "фікс меню"),
    (r"форм[аыу]|submit|кнопк", "фікс форми"),
    (r"шрифт", "фікс шрифту"),
    (r"перевод|язык|надпис|текст", "фікс тексту"),
    (r"ссылк|битая|404|веде|link", "фікс лінків"),
]
_LABEL_RX = [(re.compile(rx, re.I), label) for rx, label in _LABELS]


def label_for(text: str) -> str:
    """Міні-назва пункту за словником; поза словником — перші два слова."""
    for rx, label in _LABEL_RX:
        if rx.search(text):
            return label
    words = [w for w in re.findall(r"[^\W\d_]{3,}", text)[:2]]
    return ("фікс " + " ".join(words).lower()) if words else "фікс"


def _clean_item(text: str) -> str:
    text = MENTION_RX.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" .;")


def parse_comment(text: str, branch: str) -> dict | None:
    """Блок САМЕ цієї вітки з коментаря → {"domain": ..., "items": [...]}.

    None — у коментарі немає рядка з назвою вітки. items:
    [{label, text}] у порядку появи; рядки-продовження доклеюються до
    попереднього пункту."""
    lines = (text or "").splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip() == branch), None)
    if start is None:
        return None
    domain = ""
    raw_items: list[str] = []
    for ln in lines[start + 1:]:
        s = ln.strip()
        if not s:
            continue
        if BRANCH_LINE_RX.match(s) and s != branch:
            break                                   # почався блок іншої вітки
        if not raw_items and not domain and DOMAIN_LINE_RX.match(s):
            domain = s
            continue
        if ITEM_RX.match(s):
            raw_items.append(ITEM_RX.sub("", s))
        elif raw_items:
            raw_items[-1] += " " + s                # перенесення рядка пункту
        else:
            # короткий формат без маркерів (кейс 01.10): «добавить адрес,
            # CNPJ» одразу під назвою вітки — перший рядок і є пунктом
            raw_items.append(s)
    items = []
    for raw in raw_items:
        clean = _clean_item(raw)
        if clean:
            items.append({"label": label_for(clean), "text": clean})
    return {"domain": domain, "items": items}


def pick_comment(comments: list[dict], branch: str) -> dict | None:
    """Найсвіжіший коментар таски, що містить блок вітки.

    ClickUp віддає коментарі найновішим першим — беремо перший збіг."""
    for c in comments or []:
        parsed = parse_comment(c.get("text", ""), branch)
        if parsed and parsed["items"]:
            return {"user": c.get("user", ""), "date": c.get("date", ""),
                    **parsed}
    return None
