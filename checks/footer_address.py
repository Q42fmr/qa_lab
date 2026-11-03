"""Футер: пін-іконка без адреси - або адресу, або геть іконку.

Генератор ліпить у футер три контактні рядки: пошта, телефон, адреса. Рядок
телефону має гард (`v-if="hasPhone"`) і зникає, коли телефону немає, а рядок
адреси гарда НЕ має - і лишається на сторінці порожнім:

    <address class="not-italic flex items-start gap-2 text-gray-500">
      <svg …пін…/>
      <span></span>          <!-- порожній У ДЖЕРЕЛІ -->
    </address>

Заміряно рендером (`nwf-cebnbilepot-br-pt`): `innerText` порожній, коробка
258x18 - тобто на живому сайті висить самотній значок мапи, який нічого не
означає. Привʼязки там немає: у `<script setup>` живуть тільки `phone` і
`hasPhone`, отже текст не приходить у рантаймі - його просто немає.

Сигнатура повна: у корпусі 74 пін-рядки, і ВСІ вони лежать у `<address>`;
безтекстових пінів поза `<address>` - нуль. Тому ловимо саме порожній
`<address>`, а не «svg, поруч з яким нічого».

Автофікс має два шляхи, і другий - не вигадування:
  * джерело є -> вписати справжню адресу вітки з її юридичних сторінок
    (privacy/terms/impressum…), де вона зазвичай і лежить;
  * джерела немає -> прибрати рядок цілком, точно як зникає рядок телефону
    без телефону. Порожній `<address>` не несе інформації, а самотній пін
    виглядає поломкою.

Чому не вигадуємо адресу: у 9 віток корпусу з порожнім `<address>` адреси
немає НІДЕ у вітці, і в ClickUp її теж немає (є лише поле GEO з локаллю).
Фальшива адреса у футері й на юридичній сторінці гірша за відсутню.

Джерело мусить бути строгим, бо вписати хибний рядок гірше, ніж прибрати:
вимагаємо і тип вулиці, і поштовий код, і кому. Без цього в кандидати лізли
дати («1º de Agosto, 2026») і обрізки речень («Rio de Janeiro, RJ 22410-003»
без вулиці). Якщо кандидати не сходяться на одній вулиці - не вгадуємо, а
прибираємо рядок.
"""
import os
import re

NAME = "Футер: пін без адреси"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"address", "company", "phone", "regno"}
PROJECTS = ["node"]
DESCRIPTION = ("Рядок адреси у футері лишився з пін-іконкою і порожнім текстом "
               "(гарда, як у телефону, генератор не поставив). Автофікс вписує "
               "адресу з юридичних сторінок вітки, а якщо її там немає - "
               "прибирає рядок, щоб не висів самотній значок мапи.")
FILES = ["*.vue"]

ADDRESS_RX = re.compile(
    r"""<address\b(?:[^>"']|"[^"]*"|'[^']*')*>(?P<body>.*?)</address\s*>""",
    re.S | re.I)
TAGS_RX = re.compile(r"<[^>]*>", re.S)
SPAN_RX = re.compile(r"<span\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>\s*</span\s*>", re.I)
# привʼязка ({{ … }}, :text) означає, що текст приходить у рантаймі - не наша справа
BINDING_RX = re.compile(r"\{\{|\bv-(?:text|html)\b|:(?:text|inner)", re.I)

# сторінки, де адреса за законом мусить бути і де вона реально лежить
LEGAL_RX = re.compile(
    r"privacy|policy|polit|terms|termos|condic|legal|impressum|datenschutz"
    r"|aviso|cookie|disclaimer|haftung|recht", re.I)
# текстовий вузол, який може бути адресою
TEXT_NODE_RX = re.compile(
    r"<(?:address|p|span|li)\b[^>]*>([^<]{12,180})</", re.I)
# тип вулиці різними локалями корпусу (br-pt, ch-de, my-en, mx-es, co-es, ch-it,
# hr-hr: «Ulica Petra Preradovića 12» — homtud-ficemvi 19.10 лишався без адреси)
STREET_RX = re.compile(
    r"\b(?:Rua|Avenida|Av\.|Alameda|Travessa|Rodovia|Pra[çc]a|Estrada"
    r"|Jalan|Lorong|Persiaran|Street|Road|Avenue|Calle|Carrera|Paseo|Bulevar"
    r"|Via|Viale|Corso"
    r"|Ulica|Ul\.|Trg|Avenija|Cesta|Obala|Šetalište|Setaliste"
    r"|[A-Za-zÄÖÜäöüßé]+(?:strasse|straße|gasse|weg|platz))\b", re.I)
# Поштовий код, а не номер будинку: код стоїть ПОРУЧ З НАЗВОЮ МІСТА - або після
# неї (`SP 01310-200`, `Kuala Lumpur 50050`), або перед (`5400 Baden`). Без цієї
# умови у кандидати проходили обрізки без коду взагалі: `Rua Sergipe, 1245,
# sala 802` (де 1245 - номер будинку) і `Rua dos Andradas, 1234, Porto Alegre`.
CITY = r"[A-ZÀ-ÝÄÖÜ][\wÀ-ÿ.]*"
POSTAL_RX = re.compile(
    rf"{CITY}\s+\d{{4,6}}(?:-\d{{3}})?\b|\b\d{{4,6}}(?:-\d{{3}})?\s+{CITY}")
LABEL_RX = re.compile(
    r"^\s*(?:Endere[çc]o|Address|Adresse|Direcci[óo]n|Indirizzo|Kontakt"
    r"|Contato|Contacto|Contact|Sede|Escrit[óo]rio|Office)\s*:\s*", re.I)


def _text(body: str) -> str:
    """Видимий текст елемента: без теґів, з нормалізованими пробілами."""
    return " ".join(TAGS_RX.sub(" ", body).split())


def _is_empty(body: str) -> bool:
    """Порожній рядок адреси: тексту немає і привʼязки, яка його дасть, теж."""
    return not _text(body) and not BINDING_RX.search(body)


def _candidates(files: dict) -> list[str]:
    """Адресо-подібні рядки з юридичних сторінок вітки.

    Розділювач полів НЕ вимагаємо: спершу тут стояла умова «мусить бути кома»,
    і вона відсікала 4 справжні адреси корпусу, писані через `·`
    (`Bahnhofstrasse 42 · Zürich · Zürich 8001 · Schweiz`), а сміття не
    відсіювала жодного - усе тримають тип вулиці й поштовий код.
    """
    out = []
    for path in sorted(files):
        if not LEGAL_RX.search(os.path.basename(path)):
            continue
        for m in TEXT_NODE_RX.finditer(files[path]):
            txt = " ".join(m.group(1).split())
            if "{{" in txt:
                continue
            if STREET_RX.search(txt) and POSTAL_RX.search(txt):
                out.append(LABEL_RX.sub("", txt))
    return out


def _street_key(addr: str) -> str:
    """Тип+назва вулиці - за нею звіряємо, чи кандидати про одне й те саме."""
    m = STREET_RX.search(addr)
    if not m:
        return ""
    tail = addr[m.end():]
    name = re.split(r"[,;·|\d]", tail, 1)[0]
    return (m.group(0) + " " + name).lower().strip()


def _source_address(files: dict) -> str | None:
    """Адреса вітки або None. Кандидати мусять зійтись на одній вулиці -
    інакше не вгадуємо (у корпусі всі 33 багатоваріантні вітки сходяться:
    це той самий адрес різної повноти, тож беремо найповніший)."""
    cands = _candidates(files)
    if not cands:
        return None
    if len({_street_key(c) for c in cands}) != 1:
        return None
    return max(cands, key=len)


def _hits(text: str):
    for m in ADDRESS_RX.finditer(text):
        if _is_empty(m.group("body")):
            yield m


def run_branch(files, all_paths):
    issues = []
    known = _source_address(files)
    for path in sorted(files):
        text = files[path]
        for m in _hits(text):
            issues.append({
                "path": path, "line": text.count("\n", 0, m.start()) + 1,
                "severity": "error",
                "message": ("рядок адреси у футері порожній - на сторінці висить "
                            "самотній пін; фікс "
                            + (f"впише адресу вітки «{known}»" if known
                               else "прибере рядок (адреси немає ніде у вітці)"))})
    return issues


def _fill(body: str, addr: str) -> str:
    """Кладе адресу у порожній `<span>`, а якщо спана немає - текстом у кінець."""
    m = SPAN_RX.search(body)
    if m:
        close = m.group(0).rfind("</span")
        return body[:m.start()] + m.group(0)[:close] + addr + \
            m.group(0)[close:] + body[m.end():]
    return body.rstrip() + "\n      " + addr + "\n    "


def _cut(text: str, m) -> tuple[int, int]:
    """Межі вирізання разом з відступом рядка і кінцевим переносом - щоб не
    лишалось порожнього рядка з пробілами."""
    start = text.rfind("\n", 0, m.start())
    start = m.start() if start < 0 else start + 1
    if text[start:m.start()].strip():
        start = m.start()                 # у рядку є ще щось - ріжемо лише тег
    end = m.end()
    nl = text.find("\n", end)
    if nl >= 0 and not text[end:nl].strip():
        end = nl + 1
    return start, end


def fix_branch(files, all_paths, branch: str = ""):
    addr = _source_address(files)
    actions = []
    for path in sorted(files):
        text = files[path]
        out, last, changed = [], 0, False
        for m in _hits(text):
            if addr:
                out.append(text[last:m.start()])
                head = m.group(0)[:m.start("body") - m.start()]
                tail = m.group(0)[m.end("body") - m.start():]
                out.append(head + _fill(m.group("body"), addr) + tail)
                last = m.end()
            else:
                cut_from, cut_to = _cut(text, m)
                out.append(text[last:cut_from])
                last = cut_to
            changed = True
        if not changed:
            continue
        out.append(text[last:])
        actions.append({"type": "edit", "path": path, "content": "".join(out)})
    return actions
