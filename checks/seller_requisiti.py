"""Реквізити продавця it-it: заглушки «da inserire» (02.10, 13.10).

У даних продавця (блок #seller у подвалі, розділ контактів impressum.html)
стоять заглушки: «ragione sociale da inserire», «(REA) da inserire»,
«Partita IVA da inserire», «Telefono: da inserire» — на /privacy.html,
/terms.html, /cookie.html і impressum.html. Партія 13.10 (17 mds-віток)
додала вільні форми: «Sede da inserire», «codice fiscale da inserire»,
«iscrizione all'Ordine dei giornalisti da inserire», «Bologna — sede da
inserire», «Estremi dell'iscrizione da inserire» — перелік лейблів
незамкнений, тож чек судить САМ ЛІТЕРАЛ «da inserire».

Фікс вписує СПРАВЖНІ дані, де їх має:
  * denominazione + REA + P.IVA — з пулу company_req.json (реальні компанії,
    P.IVA checksum-звірені; вибір детермінований по вітці);
  * телефон — наявний tel:-лінк вітки, інакше з гео-бази (geo_phones.json).
Решту заглушок (sede, codice fiscale, ordine…) вписувати нічим — вони
ВИДАЛЯЮТЬСЯ мінімальним сегментом: речення, «·»-пункт або <br>-рядок;
параграф, що спорожнів, іде геть разом зі своїм заголовком (осиротілий
«SEDE» над порожнім місцем — та сама заглушка на вигляд). Разом із даними
зникає і преамбула impressum «Le voci "da inserire" vanno compilate…».

Лише it-it: заглушки «da inserire» — італійський шаблон продавця.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import company_req                                              # noqa: E402

NAME = "Реквізити продавця: заглушки «da inserire» / «a inserir»"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"company", "phone", "regno"}
PROJECTS = ["php"]
DESCRIPTION = ("Дані продавця (#seller у подвалі, контакти impressum/privacy) "
               "з заглушками «da inserire» (it-it) / «a inserir» (br-pt) — "
               "фікс вписує те, що має (it: реквізити з пулу і телефон вітки; "
               "br: CNAE і дату consulta з сусіднього «Quem vende»), решту "
               "зносить мінімальним сегментом.")
FILES = ["*.html", "*.htm", "*.php"]

# літерал-заглушка за локаллю; португальське «a inserir» — лише окремим
# словом «a» (у «para inserir ferramentas» воно живе, не заглушка)
_LITERALS = {
    "it-it": r"da inserire",
    "br-pt": r"(?<![\wà-ú])a inserir(?![\wà-ú])",
}
_DA_INSERIRE_RX = re.compile("|".join(_LITERALS.values()), re.I)
# для повідомлення: до 4 слів перед літералом — показуємо, ЩО саме не
# заповнене («sede», «codice fiscale», «iscrizione all'ordine…»)
_LABEL_RX = re.compile(
    r"((?:[\w’'()\./-]+\s+){0,4}?[\w’'()\./-]*)\s*:?\s*(?:"
    + "|".join(_LITERALS.values()) + ")", re.I)
_FIELDS = [
    ("ragione sociale",
     re.compile(r"ragione sociale\s*:?\s*da inserire", re.I)),
    ("REA",
     re.compile(r"\(?REA\)?\s*:?\s*da inserire", re.I)),
    ("Partita IVA",
     re.compile(r"Partita IVA\s*:?\s*da inserire", re.I)),
    ("Telefono",
     re.compile(r"Telefono\s*:?\s*da inserire", re.I)),
]
# преамбули impressum/privacy: «Le voci «da inserire» vanno compilate…»,
# «os itens “a inserir” devem ser preenchidos…» — речення до крапки; після
# заповнення даних воно або бреше, або лишає літерал
_PREAMBLE_RX = re.compile(
    r"[^<>.]*[«“\"]?\s*(?:da inserire|a inserir)\s*[»”\"]?[^<>.]*"
    r"(?:vanno|devem|deve)[^<>.]*\.\s*", re.I)
_TEL_HREF_RX = re.compile(r'href="tel:([^"]+)"[^>]*>([^<]+)<', re.I)
_LEGAL_ONLY_RX = re.compile(r"privacy|cookie|terms|impressum", re.I)
_TEL_DROP_RX = re.compile(r"\s*Telefono\s*:?\s*da inserire\s*[·•]?", re.I)
# дужковий фрагмент із заглушкою: «(hospedagem: a inserir)», «(a inserir)»
# — зноситься лише він, речення довкола лишається
_PAREN_RX = re.compile(
    r"\s*\([^()]*?(?:" + "|".join(_LITERALS.values()) + r")[^()]*\)", re.I)

# ---------------------------------------------------- generic-чистка решти
_P_RX = re.compile(
    r"<(?P<tag>p|address|td|li|span|small)\b[^>]*>"
    r"(?P<body>(?:(?!</?(?:p|address|td|li|span|small)\b).)*?)"
    r"</(?P=tag)>\s*", re.I | re.S)

_HEAD_BEFORE_RX = re.compile(r"<h(\d)[^>]*>[^<]*</h\1>\s*$", re.I)
_BR_SPLIT_RX = re.compile(r"<br\s*/?>", re.I)
_SENT_SPLIT_RX = re.compile(r"(?<=[.!?])\s+")


_LEAD_RX = re.compile(r"^\s*<b\b[^>]*>[^<]*</b>\s*", re.I)
_ABBR_TAIL_RX = re.compile(r"(?:^|[\s(])[\wà-ú]{1,4}\.$", re.I)


def _sentences(part: str) -> list[str]:
    """Речення; крапка після скорочення («art. 41», «n. 5») не межа."""
    raw = _SENT_SPLIT_RX.split(part)
    out: list[str] = []
    for s in raw:
        if out and _ABBR_TAIL_RX.search(out[-1]) and (s[:1].isdigit()
                                                      or s[:1].islower()):
            out[-1] = out[-1] + " " + s
        else:
            out.append(s)
    return out


def _clean_segline(line: str) -> str:
    """Рядок (між <br>) без заглушок: пункти «·», речення. Ведучий
    заголовок блоку (<b>Expediente</b>, <b>Contatti</b>) лишається."""
    if not _DA_INSERIRE_RX.search(line):
        return line
    lead = ""
    lm = _LEAD_RX.match(line)
    if lm:
        lead, line = lm.group(0), line[lm.end():]
    parts = re.split(r"\s+[·•]\s+", line)
    kept = []
    for part in parts:
        if not _DA_INSERIRE_RX.search(part):
            kept.append(part.strip())
            continue
        sents = [s for s in _sentences(part)
                 if not _DA_INSERIRE_RX.search(s)]
        if sents:
            kept.append(" ".join(s.strip() for s in sents))
    return lead + " · ".join(k for k in kept if k)


_TAG_RX = re.compile(r"<[^>]+>")


# пара визначень, де значення — заглушка: <dt>Telefone</dt><dd>a inserir</dd>;
# зноситься разом із <div>-обгорткою, якщо та тримає лише цю пару
_DT_DD_RX = re.compile(
    r"(?P<wrap><div\b[^>]*>\s*)?<dt\b[^>]*>(?:(?!</dt>).)*?</dt>\s*"
    r"<dd\b[^>]*>(?P<dd>(?:(?!</dd>).)*?)</dd>(?(wrap)\s*</div>)\s*",
    re.I | re.S)


def _strip_pairs(text: str) -> str:
    def _one(m):
        dd = _TAG_RX.sub("", m.group("dd")).strip()
        if _DA_INSERIRE_RX.fullmatch(dd) or _DA_INSERIRE_RX.search(dd) and \
                len(dd.split()) <= 3:
            return ""
        return m.group(0)
    return _DT_DD_RX.sub(_one, text)


def _strip_leftovers(text: str) -> str:
    """Зносить усі заглушки, що лишились після адресних замін: dt/dd-пару,
    дужковий фрагмент, сегмент, порожній <p>/<address>/<td>/<li>,
    осиротілий заголовок перед ним."""
    text = _strip_pairs(text)
    out = []
    pos = 0
    for m in _P_RX.finditer(text):
        body = m.group("body")
        if not _DA_INSERIRE_RX.search(body):
            continue
        # 1) дужки: «(hospedagem: a inserir)» — геть лише вони
        body = _PAREN_RX.sub("", body)
        # 2) сегменти: <br>-рядки, «·»-пункти, речення
        lines = [_clean_segline(l) for l in _BR_SPLIT_RX.split(body)]
        lines = [l for l in lines if l.strip()]
        # заголовок блоку, що лишився сам у рядку, — назад до наступного
        # рядка (<b>Expediente</b>Editor…<br> було одним рядком)
        if (len(lines) > 1 and _LEAD_RX.match(lines[0])
                and not _TAG_RX.sub("", lines[0]).replace(
                    _TAG_RX.sub("", _LEAD_RX.match(lines[0]).group(0)), "").strip()):
            lines[0:2] = [lines[0].rstrip() + lines[1]]
        # 3) те, що лишилось, — не текст, а огризок: «Modelo.» (одне слово
        #    з крапкою) або сам заголовок блоку без жодного рядка під ним
        joined = "<br>".join(lines)
        plain = _TAG_RX.sub("", joined).strip()
        lead_only = bool(lines) and _LEAD_RX.match(joined) and not \
            _TAG_RX.sub("", joined[_LEAD_RX.match(joined).end():]).strip()
        if (m.group("tag").lower() in ("p", "address")
                and ((len(plain.split()) <= 1 and plain.endswith("."))
                     or lead_only)):
            lines = []
        chunk_start = m.start()
        if lines:
            repl = (text[m.start():m.start("body")]
                    + "<br>".join(lines)
                    + f"</{m.group('tag')}>")
        else:
            repl = ""
            head = _HEAD_BEFORE_RX.search(text, pos, m.start())
            if head:
                chunk_start = head.start()
        out.append(text[pos:chunk_start])
        out.append(repl)
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def _locale(branch: str) -> str:
    loc = company_req._locale(branch)
    return loc if loc in _LITERALS else ""


def _is_it(branch: str) -> bool:
    return _locale(branch) == "it-it"


# ---------------------------------------------------- br-pt: самозаповнення
# «Quem vende» того ж футера вже тримає CNAE і дату consulta — Expediente
# просить те саме; беремо звідти, а не з пулу
_CNAE_RX = re.compile(r"\(CNAE\s+([\d]{4}-\d/\d{2})\)", re.I)
_CONSULTA_RX = re.compile(r"consulta em (\d{2}/\d{2}/\d{4})", re.I)


def _fill_pt(zone: str, source: str) -> str:
    """Заповнює CNAE/дату consulta у зоні даними з усієї сторінки: «Quem
    vende» і «Expediente» — сусідні <address>, кожен своя зона."""
    cnae = _CNAE_RX.search(source)
    if cnae:
        zone = re.sub(r"(CNAE principal\s*:\s*)a inserir(?![\wà-ú])",
                      lambda m: m.group(1) + cnae.group(1), zone, flags=re.I)
    date = _CONSULTA_RX.search(source)
    if date:
        zone = re.sub(r"consulta(?: em)?\s*:?\s*a inserir(?![\wà-ú])",
                      "consulta em " + date.group(1), zone, flags=re.I)
    return zone


def _is_page(path: str) -> bool:
    return path.lower().endswith((".html", ".htm", ".php"))


# Правова зона — вся сторінка; на інших сторінках судимо лише блоки даних
# продавця: #seller, <address>, і <aside> з dl-панеллю реквізитів (veltrixa
# 15.10: «Telefone / Representante legal: a inserir» у ключовій панелі
# поза футером). «niente da inserire» у товарній сітці index.php — живе
# речення («нічого вводити»), не заглушка (mds-papluwfu, 13.10)
_SELLER_BLOCK_RX = re.compile(
    r"<(?:div|section|footer)\b[^>]*\bid\s*=\s*[\"']seller[\"']"
    r"[\s\S]*?</(?:div|section|footer)>", re.I)
_ADDRESS_RX = re.compile(r"<address\b[\s\S]*?</address>", re.I)
_ASIDE_DL_RX = re.compile(r"<aside\b(?:(?!</aside>).)*?<dl\b(?:(?!</aside>).)*?</aside>",
                          re.I | re.S)
# Підпис-примітка з заглушкою поза будь-яким блоком: «Canal de contato: a
# inserir», «…tabela oficial: a inserir.» (cirevo, nexlivo, nao-foi-sorte
# 15.10) — елемент судиться, якщо літерал стоїть у кінці речення/рядка
# («: a inserir», «a inserir.») — жива мова так не закінчується
_STANDALONE_RX = re.compile(
    r"<(?P<tag>p|span|li|dd|small)\b[^>]*>(?:(?!</(?P=tag)>).)*?"
    r"(?::\s*|\b)a inserir\s*(?:[.;](?:(?!</(?P=tag)>).)*?|\s*(?:<[^>]+>\s*)*)"
    r"</(?P=tag)>", re.I | re.S)


def _zones(path: str, text: str) -> list[tuple[int, int]]:
    """[(start, end)] — де на цій сторінці заглушки взагалі судяться."""
    if _LEGAL_ONLY_RX.search(path):
        return [(0, len(text))]
    spans = [m.span() for m in _SELLER_BLOCK_RX.finditer(text)]
    for rx in (_ADDRESS_RX, _ASIDE_DL_RX, _STANDALONE_RX):
        spans += [m.span() for m in rx.finditer(text)
                  if not any(a <= m.start() < b for a, b in spans)]
    return sorted(spans)


def _in_zones(zones, pos: int) -> bool:
    return any(a <= pos < b for a, b in zones)


def _branch_tel(files: dict, branch: str) -> tuple[str, str]:
    """(href, показ) телефону: спершу живий tel:-лінк вітки, тоді гео-база."""
    for p in sorted(files):
        if not _is_page(p):
            continue
        m = _TEL_HREF_RX.search(files[p])
        if m:
            return m.group(1).strip(), " ".join(m.group(2).split())
    try:
        import checks.geo_phone as gp
        num = gp._pick(branch)
        if num:
            return gp._tel_href(num), num
    except Exception:
        pass
    return "", ""


def run_branch(files, all_paths, branch: str = ""):
    loc = _locale(branch)
    if not loc:
        return []
    issues = []
    for path in sorted(files):
        if not _is_page(path):
            continue
        text = files[path]
        zones = _zones(path, text)
        hits = [m for m in _LABEL_RX.finditer(text)
                if _in_zones(zones, m.start())]
        if not hits:
            continue
        found = []
        for m in hits:
            label = " ".join(m.group(1).split())
            if not label:
                # значення у <dd> — лейбл стоїть у парному <dt> перед ним
                dt = re.search(r"<dt\b[^>]*>((?:(?!</dt>).)*?)</dt>\s*<dd\b[^>]*>\s*$",
                               text[max(0, m.start() - 300):m.start()], re.I | re.S)
                label = " ".join(_TAG_RX.sub("", dt.group(1)).split()) if dt \
                    else "(без лейбла)"
            if label not in found:
                found.append(label)
        line = text.count("\n", 0, hits[0].start()) + 1
        if loc == "it-it":
            tail = ("фікс впише реквізити з пулу і телефон вітки, решту "
                    "заглушок прибере" if company_req.pick(branch) else
                    "пулу для локалі немає — фікс прибере ці рядки")
        else:
            tail = ("фікс впише CNAE і дату consulta з «Quem vende», решту "
                    "рядків-заглушок прибере")
        issues.append({"path": path, "line": line, "severity": "error",
                       "message": (f"заглушки продавця: "
                                   f"{', '.join(found[:5])} — {tail}")})
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    loc = _locale(branch)
    if not loc:
        return []
    rec = company_req.pick(branch) if loc == "it-it" else None
    href, shown = _branch_tel(files, branch) if loc == "it-it" else ("", "")
    actions = []
    for path in sorted(files):
        if not _is_page(path):
            continue
        text = files[path]
        zones = _zones(path, text)
        if not any(_DA_INSERIRE_RX.search(text, a, b) for a, b in zones):
            continue
        # фікс працює по зонах і склеює назад: решта сторінки недоторкана
        out_parts = []
        prev = 0
        for a, b in zones:
            out_parts.append(text[prev:a])
            out_parts.append(_fix_zone(text[a:b], rec, href, shown, text))
            prev = b
        out_parts.append(text[prev:])
        new = "".join(out_parts)
        new = _PREAMBLE_RX.sub("", new)
        if new != text:
            actions.append({"type": "edit", "path": path, "content": new})
    return actions


def _fix_zone(zone: str, rec, href: str, shown: str, source: str = "") -> str:
    new = _fill_pt(zone, source or zone)
    if rec:
        new = re.sub(r"ragione sociale\s*:?\s*da inserire",
                     f"ragione sociale: {rec['name']}", new, flags=re.I)
        new = re.sub(r"\(REA\)\s*:?\s*da inserire",
                     f"(REA): {rec['rea']}", new, flags=re.I)
        new = re.sub(r"\bREA\s*:?\s*da inserire",
                     f"REA: {rec['rea']}", new, flags=re.I)
        new = re.sub(r"Partita IVA\s*:?\s*da inserire",
                     f"Partita IVA {rec['piva']}", new, flags=re.I)
        if href:
            new = re.sub(r"Telefono\s*:?\s*da inserire",
                         f'Telefono: <a href="tel:{href}">{shown}</a>',
                         new, flags=re.I)
        else:
            new = _TEL_DROP_RX.sub("", new)
    # все, що вписати нічим (sede, codice fiscale, ordine, і весь
    # перелік без пулу) — геть мінімальним сегментом
    return _strip_leftovers(new)
