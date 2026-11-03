"""«Партнерські банки» / блок довіри з логотипами фінустанов не має бути на вайті.

Детектимо не по верстці (вона різна), а по назвах банків: якщо на сторінці
згадано кілька відомих банків — це той самий блок довіри.
Список банків розширюється через .env: CHECK_BANKS=Назва1,Назва2,...
"""
import os
import re

NAME = "Блок з банками"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"links"}
PROJECTS = ["php"]
DESCRIPTION = ("Ловить блок довіри з назвами банків (кожен банк — окремою карткою/"
               "лейблом, не в реченні). У index.php — error з автофіксом (вирізає "
               "<section>); в інших файлах — лише warn (автофікс не чіпає).")
FILES = ["*.html", "*.php", "*.vue"]

_DEFAULT = [
    # CH
    "UBS", "Credit Suisse", "Raiffeisen", "PostFinance", "Zürcher Kantonalbank",
    "ZKB", "Julius Bär", "Julius Baer", "Vontobel", "Pictet", "Lombard Odier",
    "Swissquote", "Migros Bank", "Cler",
    # міжнародні
    "HSBC", "Barclays", "Deutsche Bank", "BNP Paribas", "Santander", "Citibank",
    "JPMorgan", "Goldman Sachs", "Standard Chartered", "Revolut",
    # BR
    "Itaú", "Itau", "Bradesco", "Banco do Brasil", "Caixa", "Nubank", "Banco Inter",
    # MY / SG
    "Maybank", "CIMB", "Public Bank", "Hong Leong", "RHB", "AmBank",
    "DBS", "OCBC", "UOB", "POSB",
    # AE / близький схід
    "Emirates NBD", "Mashreq", "Al Rajhi", "ADCB", "FAB", "Dubai Islamic",
    # CO / ES
    "Bancolombia", "Davivienda", "BBVA", "Banco de Bogotá", "Banco de Bogota",
    "CaixaBank", "Banco Popular",
    # AT - у корпусі це найбільша сімʼя блоку (21 вітка), і жодної назви тут
    # не було: чек бачив лише «Raiffeisen» зі списку CH, тобто 1 банк із 6,
    # а поріг - 3. Кейс `krifhegdtbep-at-de`.
    "Erste Bank", "Bank Austria", "BAWAG", "Volksbank", "Sparkasse",
    "Oberbank", "Hypo Tirol", "Hypo Vorarlberg", "Bank99",
]


def _banks():
    extra = [b.strip() for b in os.getenv("CHECK_BANKS", "").split(",") if b.strip()]
    return _DEFAULT + extra


BANKS = _banks()
# Межі через lookaround, а не \b: список розширюється з .env, а назва може
# кінчатись пунктуацією - «BAWAG P.S.K.». Тоді кінцевий \b вимагає літери
# ПІСЛЯ точки, тож `\bBAWAG P\.S\.K\.\b` не матчиться ні в `>BAWAG P.S.K.<`,
# ні в реченні, тобто запис був би мертвий. `(?<!\w)…(?!\w)` дає ту саму межу
# для звичайних назв і працює для назв із крапкою.
RX = re.compile("|".join(r"(?<!\w)" + re.escape(b) + r"(?!\w)" for b in BANKS),
                re.I)

# текстові вузли (між тегами) — щоб рахувати банки саме як картки/лейбли,
# а не згадки в реченні
_TEXTNODE_RX = re.compile(r">([^<]+)<")
_WORD_RX = re.compile(r"\w+", re.UNICODE)
MAX_CARD_WORDS = 6          # довший вузол = проза (FAQ «...Maybank, CIMB, Public Bank...»)


def _card_hits(text):
    """Банки, що стоять як окремі картки/лейбли: у коротких текст-вузлах
    (≤MAX_CARD_WORDS слів). Повертає (bank_lower -> line, к-ть таких вузлів).
    Проза (довгі речення з переліком банків) сюди не потрапляє."""
    hits = {}
    nodes_with_bank = 0
    for m in _TEXTNODE_RX.finditer(text):
        seg = m.group(1)
        if len(_WORD_RX.findall(seg)) > MAX_CARD_WORDS:
            continue                                   # довгий текст — не картка
        bm = list(RX.finditer(seg))
        if not bm:
            continue
        nodes_with_bank += 1
        line = text.count("\n", 0, m.start(1)) + 1
        for b in bm:
            hits.setdefault(b.group(0).lower(), line)
    return hits, nodes_with_bank


def _is_trust_block(text):
    """Блок довіри = 3+ РІЗНИХ банки, кожен окремою карткою (у ≥3 коротких
    вузлах). Одне речення з трьома банками (проза/FAQ) не рахується."""
    hits, nodes = _card_hits(text)
    return (len(hits) >= 3 and nodes >= 3), hits


def run(path, text):
    from pathlib import Path
    ok, hits = _is_trust_block(text)
    if not ok:
        return []
    line = min(hits.values())
    names = sorted({m.group(0) for m in RX.finditer(text)
                    if m.group(0).lower() in hits})
    is_index = Path(path).name.lower() == "index.php"
    sev = "error" if is_index else "warn"
    tail = ("прибрати з вайту (автофікс видалить <section>)" if is_index
            else "прибрати вручну — автофікс чіпає лише index.php")
    return [{
        "line": line, "severity": sev,
        "message": f"блок з банками ({len(hits)}): {', '.join(names[:8])} — {tail}",
    }]


SECTION_RX = re.compile(r"<section\b.*?</section\s*>", re.S | re.I)
# html-коментар безпосередньо перед секцією (типово «<!-- Partner Banks Section -->»)
_PRE_COMMENT_RX = re.compile(r"(<!--(?:(?!-->).)*-->[ \t]*\r?\n?[ \t]*)\Z", re.S)


def fix(path, text):
    """Автофікс ЛИШЕ у index.php: вирізає <section>…</section>, що є блоком
    довіри (банки як картки, не проза), разом із коментарем-заголовком.
    В інших файлах нічого не чіпаємо (там лише warn)."""
    from pathlib import Path
    if Path(path).name.lower() != "index.php":
        return text
    out = text
    while True:
        for m in SECTION_RX.finditer(out):
            ok, _ = _is_trust_block(m.group(0))
            if not ok:
                continue
            start, end = m.span()
            cm = _PRE_COMMENT_RX.search(out[:start])
            if cm:
                start = cm.start(1)
            out = out[:start] + out[end:]
            break                     # починаємо пошук заново по зміненому тексту
        else:
            break
    return out
