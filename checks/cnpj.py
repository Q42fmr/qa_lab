"""CNPJ на br-pt вайті: регламент BR — номер завжди в політиках (Termos /
Política) І/АБО в підвалі; QA судить саме за цими місцями.

Чек діє ЛИШЕ на вітках з локаллю -br-pt (решті країн CNPJ не належить;
іноземна юрособа — французька філія з RCS/SIREN, норвезький оператор з
Organisasjonsnummer — виняток). Шукається канонічний запис XX.XXX.XXX/XXXX-XX.

Свій номер на сайті вже є, але не закріплений (лише в тексті поста, або в
підвалі не кожної сторінки — ib-cytis 22.10: «стоит только на главной») —
фікс КОПІЮЄ його у підвал кожної сторінки, де його нема: той самий блок з
підвалу сторінки-донора в те саме місце, інакше рядок «CNPJ …» клоном <p>/©.
Номера немає зовсім — береться з пулу (вкладка «Журнал → CNPJ», модуль
cnpj_pool) і дописується рядком у футер. Порожній пул = error без фікса:
вигаданий номер гірший за відсутній.
"""
import re

NAME = "CNPJ на br-pt вайті"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"regno"}
PROJECTS = ["php", "node"]
DESCRIPTION = ("Бразильська вітка (-br-pt): CNPJ у Termos/Política і/або в "
               "підвалі кожної сторінки. Свій номер деінде — копія у футер "
               "решти сторінок (блок донора або рядок у стилях вітки); "
               "немає — номер з пулу (Журнал → CNPJ). Іноземний реєстр на "
               "сайті (RCS/SIREN, норвезький Org.nr.) — CNPJ не потрібен.")
FILES = ["*.html", "*.htm", "*.php", "*.vue"]

CNPJ_RX = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
_P_RX = re.compile(r"<p\b[^>]*>.*?</p>", re.S | re.I)
_TAGS_RX = re.compile(r"<[^>]+>")
# футер без жодного <p>: корпус mds-* будує його з <address>/<div>
_ADDRESS_BLOCK_RX = re.compile(r"<address\b[^>]*>.*?</address>", re.S | re.I)


# суфікс локалі; «-2» за ним — номер партії (choa-nono-br-pt-2,
# bukjima-vija-br-pt-2, 28.10): той самий бразильський вайт. Доти чек
# порівнював кінець назви з «-br-pt» і такі вітки мовчки пропускав.
_BR_RX = re.compile(r"[-.]br-pt(?:-\d+)?$")


def _is_br(branch: str) -> bool:
    return bool(_BR_RX.search((branch or "").strip().lower()))


# Іноземна юрособа на br-pt вайті: реєстр не бразильський, CNPJ там зайвий і
# його просили ПРИБРАТИ. Без цього винятку автофікс повертав би номер з пулу
# по колу.
#   * французька філія (nwf-leqo-fihqos/confeboa-matkipome/codho-preduko,
#     баєр Kite 20.10) — RCS/SIREN;
#   * норвезький оператор (TECH-29349, arikejabgag/demeduu/lmpisnizatar,
#     28.10) — Organisasjonsnummer / Org.nr. з Enhetsregisteret.
_FOREIGN_REG_RX = re.compile(r"\bRCS\b[^<\n]{0,40}?\d{3}[ .]?\d{3}[ .]?\d{3}\b"
                             r"|\bSIRE[NT]\b[^<\n]{0,12}?\d{3}[ .]?\d{3}[ .]?\d{3}"
                             r"|\b(?:Organisasjonsnummer|Org\.?\s?nr)\b[^<\n\d]{0,20}"
                             r"\d{3}[ .]?\d{3}[ .]?\d{3}\b", re.I)


def _foreign_registered(files: dict) -> bool:
    return any(_FOREIGN_REG_RX.search(t) for p, t in files.items()
               if p.lower().endswith((".html", ".htm", ".php", ".vue")))


def _valid_num(num: str) -> bool:
    try:
        import cnpj_pool
        return cnpj_pool.valid(num)
    except Exception:
        return True                      # без пулу не судимо про контрольні


def _numbers(files: dict) -> tuple[set, set]:
    """(валідні, фейкові) номери на сайті. Фейк — форма правильна, а
    контрольні цифри ні: плейсхолдер генератора 12.345.678/0001-90."""
    good, bad = set(), set()
    for t in files.values():
        for m in CNPJ_RX.findall(t):
            (good if _valid_num(m) else bad).add(m)
    return good, bad


_TITLEISH_RX = re.compile(
    r"<title[^>]*>(.*?)</title>|<h1[^>]*>(.*?)</h1>"
    r'|<meta\s+name="description"\s+content="([^"]*)"', re.S | re.I)


def _site_text(files: dict) -> str:
    """Тематичний текст вайта (title/h1/description) — для вибору сфери."""
    out = []
    for p in sorted(files):
        if p.rsplit("/", 1)[-1].lower().startswith("index."):
            for m in _TITLEISH_RX.finditer(files[p]):
                out.append(next(g for g in m.groups() if g is not None))
    return _TAGS_RX.sub(" ", " ".join(out))


def _pool_number(branch: str, files: dict) -> str:
    try:
        import cnpj_pool
        return cnpj_pool.pick(branch, _site_text(files))
    except Exception:
        return ""


# <footer> рівня сайту. Перший <footer> сторінки буває зовсім не підвалом:
# цитата відгуку (<blockquote>…<footer>— Ім'я</footer>), мета коментаря чи
# статті (<article>…<footer class="comment-meta">), підсумок картки — у 21
# вітці корпусу 22.10 саме такий стояв першим. У .vue-компонентах ще й
# «футер» документа юридичної сторінки (<main>…<footer>) і цитат у <section>;
# у php main/section не рахуємо — там бувають два <main> без пари
# (itexiofocu), і справжній підвал вважався б вкладеним.
_CONTENT_TAGS = ("article", "blockquote", "figure", "aside", "dialog")
_VUE_CONTENT_TAGS = _CONTENT_TAGS + ("main", "section")
# регістр важливий: <Footer /> у App.vue — тег компонента, не підвал
_SCAN_RX = re.compile(r"<(/?)(article|blockquote|figure|aside|dialog|main|section)\b"
                      r"|<(?:footer|FOOTER)\b[^>]*>")


def _site_footers(text: str, path: str = "") -> list[tuple[int, int]]:
    """[(початок, кінець)] вмісту кожного <footer> рівня сайту."""
    cont = _VUE_CONTENT_TAGS if path.lower().endswith(".vue") else _CONTENT_TAGS
    out, low, depth = [], text.lower(), {}
    for m in _SCAN_RX.finditer(text):
        tag = m.group(2)
        if tag is None:                                   # <footer …>
            if any(depth.get(c, 0) > 0 for c in cont):
                continue
            end = low.find("</footer>", m.end())
            if end > 0:
                out.append((m.end(), end))
            continue
        depth[tag] = depth.get(tag, 0) + (-1 if m.group(1) else 1)
    return out


def _footer_paths(files: dict) -> list[str]:
    return sorted(p for p, t in files.items() if _site_footers(t, p))


_LEGAL_PATH_RX = re.compile(r"privac|termos|terms|condi[cç]|legal|cookie|politica", re.I)


# Візуальний підвал буває поза <footer>: у Wix-знімку (lehimud) рядок
# «© 2017 Lehimud… / CNPJ …» — це rich-text у <main> ПЕРЕД порожнім
# <footer>. Номер одразу ПІСЛЯ © — теж «у підвалі»; інакше фікс дописав би на
# головній другий CNPJ. Лише після: номер у тексті сторінки над підвалом
# із © — це якраз «лише в тексті».
_AFTER_COPY = 800


def _covered(text: str, path: str, good: set) -> bool:
    """Номер стоїть у будь-якому підвалі сторінки (у Avada підвалів два)
    або одразу після рядка ©."""
    if any(n in text[s:e] for s, e in _site_footers(text, path) for n in good):
        return True
    import checks._footer_line as _fl
    for m in _fl.COPY_RX.finditer(text):
        if any(n in text[m.end():m.end() + _AFTER_COPY] for n in good):
            return True
    return False


def _on_legal_page(files: dict, good: set) -> bool:
    return any(_LEGAL_PATH_RX.search(p) and any(n in t for n in good)
               for p, t in files.items())


def _missing(files: dict, good: set) -> list[str]:
    """Сторінки, у підвалі яких номера немає. Правило — «у підвалі сайту»:
    php-сторінка несе свій футер, тож номер мусить бути в кожному
    (ib-cytis 22.10: CNPJ у футері лише головної, QA — «стоит только на
    главной»). У vue футер — один глобальний компонент на всі сторінки:
    номер у будь-якому компоненті-підвалі = на кожній сторінці."""
    feet = _footer_paths(files)
    if any(p.lower().endswith(".vue") for p in feet):
        return [] if any(_covered(files[p], p, good) for p in feet) else feet
    return [p for p in feet if not _covered(files[p], p, good)]


def _own_number(files: dict, good: set) -> str:
    """Який із власних номерів копіювати: той, що вже в підвалах, далі —
    з юридичної сторінки, далі — найчастіший."""
    feet = _footer_paths(files)

    def rank(n):
        return (sum(1 for p in feet if _covered(files[p], p, {n})),
                _on_legal_page(files, {n}),
                sum(t.count(n) for t in files.values()))
    return max(sorted(good), key=rank)


def _anchored(files: dict, good: set) -> bool:
    """QA судить не «є десь», а «у підвалі та/або в Termos/Política»
    (регламент: BR — завжди в політиках І/АБО у футері). Номер лише в тексті
    одного поста (casenadefekgubn, piivabmekwok 21.10) або у футері однієї
    головної (ib-cytis 22.10) — не закріплений."""
    return _on_legal_page(files, good) or not _missing(files, good)


def _append_line(text: str, content: str, path: str = "") -> str:
    """Клон <p> з футера зі всіма стилями + рядок content нижче (механіка
    режиму «Футер» у Замінах); без футера/кандидата — текст як був.

    Футер — ОСТАННІЙ підвал рівня сайту: у корпусі це завжди справжній
    підвал (Avada: смуга ©; piivabmekwok: після CTA-«футера» секції;
    itexiofocu: master-footer після футера сторінки).

    Другий шлях — футер на <address>-блоках без жодного <p> (корпус
    mds-*): рядок лягає перед </address> останнього змістовного блока,
    як у geo_phone і address_number. Без нього чек обіцяв дописати
    номер, фікс повертав 0 дій, і помилка не зникала ніколи."""
    spans = _site_footers(text, path)
    if not spans:
        return text
    start, end = spans[-1]
    seg = text[start:end]
    if content in seg:
        return text                      # у ЦЬОМУ футері вже стоїть (у тексті сторінки — не рахується)
    cand = None
    for b in _P_RX.finditer(seg):
        if _TAGS_RX.sub("", b.group(0)).strip():
            cand = b                              # останній <p> з текстом
    if cand is not None:
        block = cand.group(0)
        open_tag = block[:block.find(">") + 1]
        clone = f"{open_tag}{content}</p>"
        abs_start = start + cand.start()
        ls = text.rfind("\n", 0, abs_start) + 1
        indent = text[ls:abs_start]
        if indent.strip():
            indent = ""
        nl = "\r\n" if "\r\n" in text else "\n"
        abs_end = start + cand.end()
        return text[:abs_end] + nl + indent + clone + text[abs_end:]
    last_addr = None
    for b in _ADDRESS_BLOCK_RX.finditer(seg):
        if _TAGS_RX.sub("", b.group(0)).strip():
            last_addr = b
    if last_addr is None:
        # третій шлях: ні <p>, ні <address> — клон ©-елемента (div/span;
        # sokkoruuzosnacav 21.10: «додай руками» на 30 сторінках)
        import checks._footer_line as _fl
        return _fl.append_after_copyright(text, content, span=(start, end))
    ins = start + last_addr.end() - len("</address>")
    return text[:ins] + f"<br>{content}" + text[ins:]


# ---- копія з підвалу іншої сторінки ---------------------------------------
# ib-cytis 22.10: номер стоїть у підвалі головної окремим блоком
# (<div class="footer-contact-item">…<p class="link mt-3">CNPJ …</p>…</div>),
# а підвали решти сторінок — ті самі, лише без цього блока, і в них немає ні
# <p>, ні <address>, ні ©: «дописати рядок» не було куди. Тож копіюємо САМ
# блок (та сама розмітка й стилі) у те саме місце — після того самого
# попереднього фрагмента підвалу.
_OPEN_RX = re.compile(r"<([a-zA-Z][\w-]*)\b[^>]*>")
_VOID = {"br", "img", "input", "hr", "meta", "link", "source", "wbr", "col", "area", "embed", "track", "param", "base"}
_JUST_CNPJ_RX = re.compile(r"^(?:c\.?n\.?p\.?j\.?)?[\s:.\-–—nº°o]*$", re.I)


def _element_end(seg: str, start: int, tag: str) -> int:
    """Кінець збалансованого елемента <tag>, що починається в start; -1 — нема."""
    rx = re.compile(r"<(/?)%s\b[^>]*?(/?)>" % re.escape(tag), re.I)
    depth = 0
    for t in rx.finditer(seg, start):
        if t.group(1):
            depth -= 1
        elif not t.group(2):
            depth += 1
        if depth == 0:
            return t.end()
    return -1


def _plain(html_: str) -> str:
    return " ".join(_TAGS_RX.sub(" ", html_).split())


def _carrier(seg: str, num: str):
    """(start, end) блока підвалу, що несе лише рядок «CNPJ …», разом з
    обгортками, у яких більше нічого немає. None — номер ділить елемент з
    іншим текстом («© 2026 X · CNPJ …»): копіювати весь елемент не можна."""
    i = seg.find(num)
    if i < 0:
        return None
    s = e = -1
    for m in reversed(list(_OPEN_RX.finditer(seg, 0, i))):
        tag = m.group(1).lower()
        if tag in _VOID or m.group(0).endswith("/>"):
            continue
        end = _element_end(seg, m.start(), tag)
        if end >= i + len(num):
            s, e = m.start(), end
            break
    if s < 0 or not _JUST_CNPJ_RX.match(_plain(seg[s:e]).replace(num, "")):
        return None
    while True:                     # підйом крізь обгортки, де наш блок — єдиний вміст
        parent = None
        for m in reversed(list(_OPEN_RX.finditer(seg, 0, s))):
            tag = m.group(1).lower()
            if tag in _VOID or m.group(0).endswith("/>"):
                continue
            end = _element_end(seg, m.start(), tag)
            if end >= e:
                parent = (m.start(), m.end(), end)
                break
        if not parent:
            return s, e
        inner = seg[parent[1]:seg.rfind("<", 0, parent[2])]
        if re.sub(r"<!--.*?-->|\s+", "", inner, flags=re.S) != re.sub(r"\s+", "", seg[s:e]):
            return s, e             # у батька є інші діти (іконки, iframe, ©) — копіюємо лише блок
        s, e = parent[0], parent[2]


def _donor(files: dict, num: str):
    """(блок, контекст до, контекст після) з першої сторінки, де номер — у
    підвалі окремим блоком."""
    for p in sorted(files):
        t = files[p]
        for fs, fe in _site_footers(t, p):
            seg = t[fs:fe]
            c = _carrier(seg, num)
            if c:
                return seg[c[0]:c[1]], seg[:c[0]], seg[c[1]:]
    return None


def _copy_block(text: str, path: str, donor) -> str:
    """Вставити блок донора в останній підвал сторінки — після того самого
    фрагмента, що стоїть перед ним у донора (або перед тим, що йде після).
    Якір мусить бути в підвалі рівно один раз; інакше — текст як був."""
    block, before, after = donor
    spans = _site_footers(text, path)
    if not spans:
        return text
    fs, fe = spans[-1]
    seg = text[fs:fe]
    for n in (240, 160, 100, 60, 40, 24):
        a = before[-n:]
        if len(a) >= min(n, 24) and seg.count(a) == 1:
            pos = fs + seg.find(a) + len(a)
            return text[:pos] + block + text[pos:]
        b = after[:n]
        if len(b) >= min(n, 24) and seg.count(b) == 1:
            pos = fs + seg.find(b)
            return text[:pos] + block + text[pos:]
    return text


def _place(text: str, path: str, line: str, donor) -> str:
    """Номер у підвал сторінки: копією блока донора, інакше — рядком."""
    if donor:
        new = _copy_block(text, path, donor)
        if new != text:
            return new
    return _append_line(text, line, path)


def run_branch(files, all_paths, branch: str = ""):
    if not _is_br(branch) or _foreign_registered(files):
        return []
    good, bad = _numbers(files)
    feet = _footer_paths(files)
    if good and not bad:
        if not feet or _anchored(files, good):
            return []
        n = _own_number(files, good)
        line = f"CNPJ {n}"
        missing = _missing(files, good)
        donor = _donor(files, n)
        doable = [p for p in missing if _place(files[p], p, line, donor) != files[p]]
        have = [p for p in feet if p not in missing]
        if have:
            where = (f"у підвалі лише {len(have)} з {len(feet)} сторінок ({have[0]}), "
                     f"на решті {len(missing)} його нема (напр. {missing[0]})")
            src = missing[0]
        else:
            src = next(p for p in sorted(files) if n in files[p])
            where = f"є лише в тексті ({src}), а не у підвалі"
        if not doable:
            tail = "у футер його нема куди покласти — додай руками"
        else:
            how = "блоком з підвалу " + have[0] if donor else f"рядком «{line}»"
            tail = f"фікс скопіює номер у футер {len(doable)} сторінок ({how})"
            if len(doable) < len(missing):
                tail += f"; ще {len(missing) - len(doable)} — нема куди покласти, додай руками"
        msg = f"CNPJ {n} {where} і нема в Termos/Política — {tail}"
        return [{"path": src, "line": 1, "severity": "error", "message": msg}]
    where = feet[0] if feet else (sorted(files)[0] if files else "")
    if not where:
        return []
    number = _pool_number(branch, files)
    if bad:
        where = next(p for p in sorted(files)
                     if any(b in files[p] for b in bad))
        repl = (f"фікс замінить на «{number}» з пулу" if number
                else "пул порожній — додай номери у «Журнал → CNPJ»")
        msg = (f"на сайті фейковий CNPJ {', '.join(sorted(bad))} "
               f"(контрольні цифри не сходяться — плейсхолдер генератора) — "
               f"{repl}")
    elif not number:
        msg = ("на сайті немає CNPJ, а пул номерів порожній — додай номери "
               "у вкладці «Журнал → CNPJ», фіксу нема звідки взяти")
    elif not feet:
        msg = ("на сайті немає CNPJ і немає <footer>, куди його дописати — "
               "додай руками")
    elif not any(_append_line(files[p], f"CNPJ {number}", p) != files[p]
                 for p in feet):
        # футер є, та класти нема куди (ні <p>, ні <address>): не обіцяємо
        # того, чого фікс не зробить - інакше помилка висить вічно
        msg = (f"на сайті немає CNPJ, а у футер його нема куди покласти "
               f"(ні <p>, ні <address>) — додай руками: «CNPJ {number}»")
    else:
        msg = (f"на сайті немає CNPJ — фікс допише «CNPJ {number}» у футер "
               f"рядком у стилях вітки")
    return [{"path": where, "line": 1, "severity": "error", "message": msg}]


def fix_branch(files, all_paths, branch: str = ""):
    if not _is_br(branch) or _foreign_registered(files):
        return []
    good, bad = _numbers(files)
    if good and not bad:
        if _anchored(files, good):
            return []
        n = _own_number(files, good)
        content = f"CNPJ {n}"                          # свій номер, не з пулу
        donor = _donor(files, n)
        actions = []
        for path in _missing(files, good):
            new = _place(files[path], path, content, donor)
            if new != files[path]:
                actions.append({"type": "edit", "path": path, "content": new})
        return actions
    number = _pool_number(branch, files)
    if not number:
        return []                        # порожній пул — тільки ручний шлях
    actions = []
    if bad:
        # фейк замінюється НА МІСЦІ: позиція, стилі і підпис лишаються
        for path in sorted(files):
            new = files[path]
            for b in bad:
                new = new.replace(b, number)
            if new != files[path]:
                actions.append({"type": "edit", "path": path, "content": new})
        return actions
    content = f"CNPJ {number}"
    for path in _footer_paths(files):
        new = _append_line(files[path], content, path)
        if new != files[path]:
            actions.append({"type": "edit", "path": path, "content": new})
    return actions
