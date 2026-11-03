"""Телефон на вайті: немає ніде — фікс додає з гео-бази номерів.

Кейс bucrung-brailluqr 01.10: «добавить номер к контактам и в футер».
БД geo_phones.json зібрана з корпусу наших же віток (tel:-лінки, звірені
за країновим префіксом) + офіційні fiction-діапазони там, де вони є
(NANP «555-01XX» для ca-en, Ofcom «7946 0XXX» для uk-en). Локаль без
бази — чек мовчить: вигадувати номери з повітря не можна.

Фікс: рядок tel:-лінком у футер (клон <p> у стилях вітки — та сама
механіка, що адреса/CNPJ) і, якщо на сторінці контактів є mailto-блок —
телефонний рядок поряд, за зразком сусіднього.
"""
import json
import re
import zlib
from pathlib import Path

NAME = "Телефон: немає на вайті"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"phone"}
PROJECTS = ["php", "node"]
DESCRIPTION = ("На видимих сторінках немає жодного телефону (ні tel:-лінка, "
               "ні номера текстом) — фікс додає детермінований номер з "
               "гео-бази вітки у футер і до контактів. Юридичні сторінки "
               "телефоном не рахуються.")
FILES = ["*.html", "*.htm", "*.php", "*.vue"]

_DB_FILE = Path(__file__).resolve().parent.parent / "geo_phones.json"
_db_cache: dict | None = None

_LOCALE_RX = re.compile(r"[-.]([a-z]{2}-[a-z]{2})(?:-\d+)?$")
_LEGAL_PATH_RX = re.compile(
    r"terms|privacy|cookie|legal|aviso|politi[ck]|mentions|refund"
    r"|shipping|devolu|juridic", re.I)
TEL_HREF_RX = re.compile(r"""href\s*=\s*["']tel:[^"']{6,25}["']""", re.I)
# телефон текстом: +код і 8..14 цифр з розділювачами — вузько, щоб
# ціни/CEP/роки не фолсили. `(?<![\w])` — щоб «U+0490-0491» з inline
# @font-face unicode-range (Google Fonts CSS у <style> головної;
# sokkoruuzosnacav 21.10) не читалось як номер і чек не мовчав на вітці
# без жодного телефону
TEL_TEXT_RX = re.compile(r"(?<![\w])\+\d[\d\s().-]{7,18}\d")
FOOTER_RX = re.compile(r"<footer\b[^>]*>", re.I)
_P_RX = re.compile(r"<p\b[^>]*>.*?</p>", re.S | re.I)
_TAGS_RX = re.compile(r"<[^>]+>")
MAILTO_P_RX = re.compile(r"<p\b[^>]*>(?:(?!</p>).)*mailto:(?:(?!</p>).)*</p>",
                         re.S | re.I)
CONTACT_PATH_RX = re.compile(r"contact|kontakt|contato|contatti", re.I)
MAILTO_DD_RX = re.compile(
    r"<div\b[^>]*>\s*<dt>[^<]*</dt>\s*<dd>(?:(?!</div>).)*mailto:"
    r"(?:(?!</div>).)*</div>", re.S | re.I)


def _locale(branch: str) -> str:
    m = _LOCALE_RX.search((branch or "").strip().lower())
    return m.group(1) if m else ""


def _rows(locale: str) -> list[str]:
    global _db_cache
    if _db_cache is None:
        try:
            _db_cache = json.loads(_DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            _db_cache = {}
    rows = _db_cache.get(locale)
    return [r for r in rows if isinstance(r, str)] if isinstance(rows, list) \
        else []


# Номер у ЛОКАЛЬНОМУ записі без «+», підписаний словом (у пості/на сторінці
# контактів): «Telefone: (11) 3034-2469», «WhatsApp: (11) 97543-9397»
# (sokkoruuzosnacav 21.10 — свій номер був у кожному пості, а фікс поклав
# у футер чужий з гео-бази). Такий номер не рахується «є телефон» (QA хоче
# його в контактах/підвалі), але кладеться у футер замість гео-номера.
_LABELED_RX = re.compile(
    r"(?:telefone|tel[ée]fono|t[ée]l[ée]phone|telephone|telefon|whatsapp|phone|tel|fone)"
    r"\s*[:.]?\s*((?:\(\d{2,3}\)\s?|\d{2,3}[\s.-])\d{3,5}[\s.-]\d{3,4}(?:[\s.-]\d{2,4})?)", re.I)
_CC = {"br-pt": "+55", "mx-es": "+52", "ar-es": "+54", "co-es": "+57", "it-it": "+39", "ch-fr": "+41",
       "ch-de": "+41", "ch-it": "+41", "de-de": "+49", "fr-fr": "+33", "es-es": "+34", "pt-pt": "+351", "hr-hr": "+385",
       "jp-jp": "+81"}
# Японія (jp-jp p-36, 26.10): номер на сайті пишеться по-домашньому
# «TEL：03-5628-3181» / «0743-62-1598» — код міста 2–5 цифр, без «+81», часто
# без tel:-лінка; QA і чек його не бачили. Підпис — TEL/電話/☎, двокрапка буває
# повноширинна; без підпису приймаємо домашній формат, якщо перед ним не FAX.
# Поштовий індекс 〒123-4567 — дві групи, під формат не підпадає.
_JP_LABELED_RX = re.compile(r"(?:TEL|Tel|電話|お電話|☎|℡)\s*[:：.]?\s*(0\d{1,4}[-−‐]\d{1,4}[-−‐]\d{4})(?!\d)")
_JP_BARE_RX = re.compile(r"(?<![\d-])(0\d{1,4}[-−‐]\d{1,4}[-−‐]\d{4})(?!\d)")
_JP_FAX_RX = re.compile(r"fax", re.I)


def _jp_site_phone(text: str, labeled_only: bool = False) -> str:
    """Домашній jp-номер з видимого тексту → «+81 3-5628-3181» (без нуля
    міжміського виходу), '' — немає."""
    m = _JP_LABELED_RX.search(text)
    if not m and not labeled_only:
        for cand in _JP_BARE_RX.finditer(text):
            if not _JP_FAX_RX.search(text[max(0, cand.start() - 8):cand.start()]):
                m = cand
                break
    if not m:
        return ""
    raw = re.sub(r"[−‐]", "-", m.group(1))
    return "+81 " + raw[1:]


def _page_order(files: dict) -> list:
    """Головна → решта за іменем: номер головної — канонічний для вітки."""
    return sorted((p for p in files if _is_page(p) and not _LEGAL_PATH_RX.search(p)),
                  key=lambda p: (not re.match(r"^(?:index|home)\.(?:php|html?)$", p.rsplit("/", 1)[-1], re.I) or "/" in p, p))


def _site_phone(files: dict, branch: str) -> str:
    """Перший підписаний локальний номер на видимих сторінках — у міжнародному
    записі для tel: і як на сайті для тексту; '' — немає."""
    loc = _locale(branch)
    cc = _CC.get(loc, "")
    pages = _page_order(files)
    if loc == "jp-jp":
        for labeled_only in (True, False):            # підписаний номер будь-де > голий
            for p in pages:
                own = _jp_site_phone(_TAGS_RX.sub(" ", files[p]), labeled_only)
                if own:
                    return own
        return ""
    for p in pages:
        text = _TAGS_RX.sub(" ", files[p])
        m = _LABELED_RX.search(text)
        if m:
            raw = m.group(1).strip()
            digits = re.sub(r"\D", "", raw)
            if 8 <= len(digits) <= 12:
                return f"{cc} {raw}".strip() if cc else raw
    return ""


def _pick(branch: str, files: dict | None = None) -> str:
    own = _site_phone(files, branch) if files else ""
    if own:
        return own
    rows = _rows(_locale(branch))
    if not rows:
        return ""
    return rows[zlib.crc32((branch or "x").encode("utf-8")) % len(rows)]


def _is_page(path: str) -> bool:
    return path.lower().endswith((".html", ".htm", ".php", ".vue"))


def _branch_has_phone(files: dict) -> bool:
    # лише сторінки, як FILES детекту: раннер дає fix_branch усі текстові
    # файли, а «U+0400-045F» у CSS шрифту читається як номер
    for p, t in files.items():
        if not _is_page(p) or _LEGAL_PATH_RX.search(p):
            continue
        if TEL_HREF_RX.search(t) or TEL_TEXT_RX.search(t):
            return True
    return False


def _tel_href(num: str) -> str:
    return "+" + re.sub(r"\D", "", num) if num.strip().startswith("+") \
        else re.sub(r"[^\d+]", "", num)


def _footer_paths(files: dict) -> list[str]:
    return sorted(p for p, t in files.items()
                  if _is_page(p) and FOOTER_RX.search(t)
                  and not _LEGAL_PATH_RX.search(p))


_PHONE_PH_RX = re.compile(
    r"((?:telefono|telefon|t[ée]l[ée]phone|telephone|phone|tel)\s*:?\s*)"
    r"(da inserire|a inserire|tbd|n/?a|—|–|-)(?=\s*(?:<|$))", re.I)
_ADDRESS_RX = re.compile(r"<address\b[^>]*>.*?</address>", re.S | re.I)


def _append_footer_line(text: str, num: str) -> str:
    """Телефон у футер. Чотири шляхи (кейс epidoc 02.10):
    1) «Telefono: da inserire» — плейсхолдер замінюється tel:-лінком;
    2) клон останнього змістовного <p>;
    3) футер на <address>-блоках — рядок перед </address> останнього;
    4) ні <p>, ні <address> — клон ©-елемента (div/span; sokkoruuzosnacav
       21.10, спільний _footer_line)."""
    m = FOOTER_RX.search(text)
    if not m:
        return text
    end = text.lower().find("</footer>", m.end())
    if end < 0:
        return text
    seg = text[m.end():end]
    if num in seg:
        return text              # у ЦЬОМУ футері вже стоїть
    link = f'<a href="tel:{_tel_href(num)}">{num}</a>'
    ph = _PHONE_PH_RX.search(seg)
    if ph:
        abs_s, abs_e = m.end() + ph.start(), m.end() + ph.end()
        return text[:abs_s] + ph.group(1) + link + text[abs_e:]
    cand = None
    for b in _P_RX.finditer(seg):
        if _TAGS_RX.sub("", b.group(0)).strip():
            cand = b
    if cand is not None:
        block = cand.group(0)
        open_tag = block[:block.find(">") + 1]
        clone = f"{open_tag}{link}</p>"
        abs_start = m.end() + cand.start()
        ls = text.rfind("\n", 0, abs_start) + 1
        indent = text[ls:abs_start]
        if indent.strip():
            indent = ""
        nl = "\r\n" if "\r\n" in text else "\n"
        abs_end = m.end() + cand.end()
        return text[:abs_end] + nl + indent + clone + text[abs_end:]
    last_addr = None
    for b in _ADDRESS_RX.finditer(seg):
        if _TAGS_RX.sub("", b.group(0)).strip():
            last_addr = b
    if last_addr is None:
        import checks._footer_line as _fl
        return _fl.append_after_copyright(text, link)
    ins = m.end() + last_addr.end() - len("</address>")
    return text[:ins] + f"<br>{link}" + text[ins:]


def _append_contact_line(text: str, num: str, label: str = "Phone") -> str:
    """Поряд з mailto контактів — телефонний рядок за зразком сусіднього:
    <p>-блок або <dt>/<dd>-факт (кейс burnaby: <dl class="nw-facts">)."""
    dd = MAILTO_DD_RX.search(text)
    if dd:
        block = dd.group(0)
        if "tel:" in block.lower() or num in block:
            return text
        clone = (f'<div><dt>{label}</dt><dd><a href="tel:{_tel_href(num)}">'
                 f'{num}</a></dd></div>')
        return text[:dd.start()] + clone + text[dd.start():]
    m = MAILTO_P_RX.search(text)
    if not m:
        return text
    block = m.group(0)
    if num in block or "tel:" in block.lower():
        return text              # у mailto-блоці телефон уже є
    open_tag = block[:block.find(">") + 1]
    clone = f'{open_tag}<a href="tel:{_tel_href(num)}">{num}</a></p>'
    ls = text.rfind("\n", 0, m.start()) + 1
    indent = text[ls:m.start()]
    if indent.strip():
        indent = ""
    nl = "\r\n" if "\r\n" in text else "\n"
    return text[:m.end()] + nl + indent + clone + text[m.end():]


def _jp_link_in_place(text: str) -> str:
    """Домашні jp-номери у видимому тексті → tel:-лінки на місці («TEL：
    03-5628-3181» → «TEL：<a href="tel:+81356283181">03-5628-3181</a>»).
    Японські скрейпи часто без <footer> (yahoge, mohiol 26.10) — рядок у
    підвал покласти нема куди, а номер на сторінці Є; номер усередині <a>
    або всередині тега не чіпається."""
    out, last = [], 0
    low = text.lower()
    for m in _JP_BARE_RX.finditer(text):
        s = m.start(1)
        if low.rfind("<", 0, s) > low.rfind(">", 0, s):
            continue                                  # усередині тега
        a_open, a_close = low.rfind("<a", 0, s), low.rfind("</a>", 0, s)
        if a_open > a_close:
            continue                                  # уже в <a>
        if low.rfind("<script", 0, s) > low.rfind("</script>", 0, s) or low.rfind("<style", 0, s) > low.rfind("</style>", 0, s):
            continue
        if _JP_FAX_RX.search(text[max(0, s - 8):s]):
            continue
        raw = m.group(1)
        href = "+81" + re.sub(r"\D", "", raw)[1:]
        out.append(text[last:s]); out.append(f'<a href="tel:{href}">{raw}</a>')
        last = m.end(1)
    out.append(text[last:])
    return "".join(out)


def run_branch(files, all_paths, branch: str = ""):
    if not files or _branch_has_phone(files):
        return []
    num = _pick(branch, files)
    if _locale(branch) == "jp-jp":
        if not num:
            return []
        where = next((p for p in sorted(files) if _is_page(p) and not _LEGAL_PATH_RX.search(p)
                      and _jp_site_phone(_TAGS_RX.sub(" ", files[p]))), None)
        return [{"path": where or "index.php", "line": 1, "severity": "error",
                 "message": (f"телефон на сайті лише текстом у домашньому записі — QA його не "
                             f"бачить; фікс зробить tel:-лінк «{num}» на місці на кожній сторінці")}]
    feet = _footer_paths(files)
    if not num or not feet:
        return []
    src = ("зі сторінок вайта (підписаний номер у тексті)" if _site_phone(files, branch)
           else f"з гео-бази ({_locale(branch)})")
    return [{"path": feet[0], "line": 1, "severity": "error",
             "message": (f"у контактах/підвалі немає телефону — фікс додасть "
                         f"{src}: «{num}» tel:-лінком у футер і до контактів")}]


def fix_branch(files, all_paths, branch: str = ""):
    if not files or _branch_has_phone(files):
        return []
    num = _pick(branch, files)
    if not num:
        return []
    actions = []
    if _locale(branch) == "jp-jp":
        for path in sorted(files):
            if not _is_page(path) or _LEGAL_PATH_RX.search(path):
                continue
            new = _jp_link_in_place(files[path])
            if new != files[path]:
                actions.append({"type": "edit", "path": path, "content": new})
        return actions
    for path in _footer_paths(files):
        new = _append_footer_line(files[path], num)
        if CONTACT_PATH_RX.search(path):
            new = _append_contact_line(new, num)
        if new != files[path]:
            actions.append({"type": "edit", "path": path, "content": new})
    # контакт-сторінка без футера: телефонний рядок все одно додається
    for path, text in files.items():
        if (_is_page(path) and CONTACT_PATH_RX.search(path)
                and not _LEGAL_PATH_RX.search(path)
                and all(a["path"] != path for a in actions)):
            new = _append_contact_line(text, num)
            if new != text:
                actions.append({"type": "edit", "path": path, "content": new})
    return actions
