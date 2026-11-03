"""Тема для пошуку фото — витягнута з самого вайта.

Навіщо. Заявка на фікс картинок приходить у вигляді «домен + теми», і теми
там — це рівно назви пропозицій вайта, перекладені російською. Звірено на
двох вітках, де тему написав саппорт:

    padzarok-br-pt  (padzarokss.pro)
      Estadia Curta na Península      → «поездка на полуостров»
      Recepção de Pequeno Casamento   → «свадебный банкет»
      Temporada Longa na Costa        → «сезон на побережье»

    quuifa-br-pt    (quuifass.pro)
      Estadia Serrana de Dois Dias    → «поездка в горы»
      Hospedagem de Retiro para Grupos→ «программа для групп»
      Arranjo de Temporada            → «Проживание на месяц»

Тобто джерело теми — **блок пропозицій/тарифів** головної сторінки: у ньому
2-4 картки, у кожної свій заголовок, ціна і кнопка. Заголовки цих карток і є
теми. На вибірці з 300 знімків такий блок має 51% віток; решті лишається
запасне джерело — хвіст `<title>` після роздільника («Hospedagem em Búzios,
RJ»), який дає тип бізнесу і місто.

Що САМЕ вважаємо карткою: секція сторінки з найбільшою кількістю цін, а в
ній — кожен `<h3>` до наступного `<h3>`, у чиєму тілі є ціна. Без цієї межі
у вибірку затікали заголовки сусідніх блоків («Localização na Península»,
«Café da manhã»), бо вони лежать близько до цін просто за відстанню в
символах.
"""
import os
import re

TAG_RX = re.compile(r"<[^>]+>")
WS_RX = re.compile(r"\s+")
# ціна у форматах, що трапляються у вайтах: R$ 1.410 · €90 · 1 090 BRL
PRICE_RX = re.compile(
    r"(?:R\$|US\$|€|£|\$|USD|BRL|EUR|CHF)\s?\d"
    r"|\d[\d.\s]*(?:,\d\d)?\s?(?:R\$|€|£|USD|BRL|EUR|CHF)")
TITLE_SPLIT_RX = re.compile(r"\s[—–|·-]\s")
H3_RX = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
IMG_RX = re.compile(r"<img[^>]*>")
ALT_RX = re.compile(r'alt="([^"]*)"')
SITE_NAME_RX = re.compile(r'og:site_name"\s+content="([^"]*)"', re.I)
TITLE_RX = re.compile(r"<title[^>]*>(.*?)</title>", re.S)
DESC_RX = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)

MAX_OFFERS = 4


def _text(s: str) -> str:
    return WS_RX.sub(" ", TAG_RX.sub(" ", s)).strip()


def brand(page: str) -> str:
    m = SITE_NAME_RX.search(page)
    if m:
        return m.group(1).strip()
    m = TITLE_RX.search(page)
    return TITLE_SPLIT_RX.split(_text(m.group(1)))[0].strip() if m else ""


def base_theme(page: str) -> str:
    """Тип бізнесу і місто — хвіст `<title>` після роздільника.
    «Padzarok — Hospedagem em Búzios, RJ» → «Hospedagem em Búzios, RJ»."""
    m = TITLE_RX.search(page)
    if not m:
        return ""
    parts = [p.strip() for p in TITLE_SPLIT_RX.split(_text(m.group(1))) if p.strip()]
    return parts[-1] if len(parts) > 1 else (parts[0] if parts else "")


def offers(page: str) -> list[dict]:
    """[{title, alt}] карток блоку пропозицій — по одній на тариф."""
    sections = re.split(r"(?=<section\b)", page)
    best = max(sections, key=lambda s: len(PRICE_RX.findall(s)), default="")
    if len(PRICE_RX.findall(best)) < 2:
        return []
    heads = list(H3_RX.finditer(best))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(best)
        card = best[m.start():end]
        if not PRICE_RX.search(card):
            continue
        # картинка картки: у цих шаблонах <img> стоїть ПЕРЕД назвою, тож
        # спершу дивимось шматок від попереднього h3 до цього, і лише потім
        # усередину картки — інакше картці діставався знімок наступної
        pre = best[heads[i - 1].end() if i else 0:m.start()]
        alt = ""
        for chunk in (pre, card):
            found = [a.group(1).strip() for a in
                     (ALT_RX.search(x.group(0)) for x in IMG_RX.finditer(chunk))
                     if a and a.group(1).strip()]
            if found:
                alt = found[-1] if chunk is pre else found[0]
                break
        title = _text(m.group(1))
        if title:
            out.append({"title": title, "alt": alt})
    return out


def _strip_brand(s: str, br: str) -> str:
    if br:
        s = re.sub(r"\s*[—–-]\s*" + re.escape(br) + r"\s*$", "", s, flags=re.I)
        s = re.sub(r"^\s*" + re.escape(br) + r"\s*[—–-]?\s*", "", s, flags=re.I)
    return s.strip(" .·—–-")


def extract(page: str) -> dict:
    """{brand, base, offers, query, source} з тексту головної сторінки."""
    br = brand(page)
    offs = offers(page)
    titles: list[str] = []
    for o in offs:
        t = _strip_brand(o["title"], br)
        if t and t.lower() not in [x.lower() for x in titles]:
            titles.append(t)
    titles = titles[:MAX_OFFERS]
    base = base_theme(page)
    if titles:
        return {"brand": br, "base": base, "offers": offs,
                "query": ", ".join(titles), "source": "offers"}
    if base:
        return {"brand": br, "base": base, "offers": offs,
                "query": base, "source": "title"}
    m = DESC_RX.search(page)
    desc = _strip_brand(_text(m.group(1)), br) if m else ""
    return {"brand": br, "base": base, "offers": offs,
            "query": desc.split(".")[0][:120], "source": "description" if desc else ""}


def for_branch(branch: str) -> dict:
    """Те саме для вітки зі знімка. Порожній query — тему не вгадали."""
    import runner
    page = ""
    for name in ("index.php", "index.html"):
        try:
            page = runner.read_snapshot_file(branch, name).decode("utf-8", "replace")
            break
        except OSError:
            continue
    if not page:
        return {"branch": branch, "brand": "", "base": "", "offers": [],
                "query": "", "source": ""}
    return {"branch": branch, **extract(page)}
