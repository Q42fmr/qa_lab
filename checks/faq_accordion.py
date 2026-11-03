"""FAQ не розкривається: акордеон на сторінці є, а JS, що його відкриває, мертвий.

Кейс fettmagv-ch-ch-de-2 (скарга 13.10: «Вопросы FAQ не раскрываются по
клику. Починить раскрытие ответов. Где: на главной»). Розмітка справна:
кнопки з aria-expanded/aria-controls, панелі з hidden, обробник у
assets/js/site.js теж справний. Але масова заміна адреси в'їхала в
об'єктний літерал каталогу картинок кошика:

    "flottillenreise-einzelplatz":"p11.jpg"  →  "flottillenreise-Engelplatz 1.jpg"

Рядковий літерал ЧЛЕНОМ об'єкта без двокрапки — гарантований SyntaxError
(шортхенд дозволений лише ідентифікаторам, не рядкам). Файл не парситься
ЦІЛКОМ, тож мертвий не лише акордеон, а й мобільне меню, кошик і валідація
форми; QA бачить найпомітніше — FAQ на головній. Звірено node --check:
"SyntaxError: Unexpected string" саме на цьому члені.

Правила (обидва — лише для сторінок, де акордеон справді є):
 1. сторінка тягне локальний <script src>, якого у вітці немає
    → error: обробник не завантажиться ніколи;
 2. у js-файлі сторінки (або в її інлайн-скрипті) рядковий член об'єктного
    літерала без двокрапки → error + автофікс. Битий js, на який не
    посилається жодна сторінка, — warn (дефект є, симптому немає).

Акордеон упізнається ЛИШЕ по hidden-панелях (aria-controls → id з hidden):
такі панелі без JS не відкриються ніяк. <details>/<summary> працюють без
JS і правил не чіпають. Класові стани (Bootstrap collapse, Alpine) свідомо
поза правилами — там розкриттям керує фреймворк, статично це не довести.

Автофікс правила 2 детермінований, двоступеневий:
 * відновлення члена, коли доказів вистачає: значення — єдина прогалина в
   числовій послідовності сусідніх значень тієї ж мапи (p1..p12 без p11 →
   "p11.jpg", суфікс звірено з уламком); ключ — єдиний ключ СУСІДНЬОГО
   об'єкта цього ж файла, якого немає серед ключів ураженої мапи і який
   ділить з уламком найдовший префікс (HREF містить
   flottillenreise-einzelplatz, IMG — ні);
 * коли доказів бракує — член видаляється: мапа втрачає один запис, але
   файл знову парситься і ВСІ обробники сторінки оживають.

Звалідовано: відновлення на fettmagv-ch-ch-de-2 дає байт-у-байт
"flottillenreise-einzelplatz":"p11.jpg", обидві гілки фікса проходять
node --check; скан — 0 фолсів на 451 js-файлі кешу і деплоїв лаби (12
віток + вендорні бандли) та на static/*.js лаби (включно з i18n-dict.js
на 236 КБ словникових літералів).
"""
import posixpath
import re

NAME = "FAQ-акордеон не розкривається (мертвий JS)"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Сторінка має акордеон (кнопки aria-expanded/aria-controls і "
               "hidden-панелі), а JS, що знімає hidden, мертвий: або "
               "<script src> вказує на відсутній у вітці файл, або масова "
               "заміна перетворила член об'єктного літерала на рядок без "
               "двокрапки — SyntaxError вбиває файл цілком. Автофікс "
               "відновлює член (значення з числової прогалини мапи, ключ із "
               "сусідньої мапи файла), а без достатніх доказів — видаляє "
               "його: файл знову парситься, обробники оживають.")
FILES = ["*.html", "*.htm", "*.php", "*.js"]

# ---------------------------------------------------------------- розмітка
TAG_RX = re.compile(r"""<(?P<tag>\w+)\b(?P<attrs>(?:[^>"']|"[^"]*"|'[^']*')*)>""")
CTRL_RX = re.compile(r"""\baria-controls\s*=\s*["']([^"']+)["']""", re.I)
EXPANDED_RX = re.compile(r"""\baria-expanded\s*=\s*["']""", re.I)
ID_RX = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""", re.I)
HIDDEN_RX = re.compile(r"""(?:^|\s)hidden(?:[\s=]|$)""", re.I)
SRC_RX = re.compile(r"""\bsrc\s*=\s*["']([^"']+)["']""", re.I)
TYPE_RX = re.compile(r"""\btype\s*=\s*["']([^"']*)["']""", re.I)
SCRIPT_RX = re.compile(
    r"""<script\b(?P<attrs>(?:[^>"']|"[^"]*"|'[^']*')*)>(?P<body>[\s\S]*?)</script""",
    re.I)


def _accordion_pairs(text: str) -> int:
    """Скільки на сторінці пар «кнопка aria-expanded+aria-controls →
    hidden-панель з тим самим id». Лише такі панелі без JS мертві."""
    hidden_ids, want = set(), []
    for m in TAG_RX.finditer(text):
        attrs = m.group("attrs")
        im = ID_RX.search(attrs)
        if im and HIDDEN_RX.search(attrs):
            hidden_ids.add(im.group(1))
        if m.group("tag").lower() in ("button", "a") and EXPANDED_RX.search(attrs):
            cm = CTRL_RX.search(attrs)
            if cm:
                want.append(cm.group(1))
    return sum(1 for cid in want if cid in hidden_ids)


def _page_scripts(path: str, text: str):
    """(локальні src як шляхи вітки, [span інлайн-тіл]) сторінки.

    Пропускаються: зовнішні URL, src з php-вставками, інлайн з php-вставками
    та не-JS типи (application/ld+json — це дані, не код)."""
    srcs, inline = [], []
    base = posixpath.dirname(path)
    for m in SCRIPT_RX.finditer(text):
        attrs = m.group("attrs")
        tm = TYPE_RX.search(attrs)
        if tm and not re.search(r"javascript|module", tm.group(1), re.I):
            continue
        sm = SRC_RX.search(attrs)
        if sm:
            src = sm.group(1).split("?")[0].split("#")[0]
            if src.startswith(("http:", "https:", "//")) or "<?" in src or not src:
                continue
            if src.startswith("/"):
                resolved = src.lstrip("/")
            else:
                resolved = posixpath.normpath(posixpath.join(base, src))
            srcs.append((resolved, sm.group(1), m.start()))
        else:
            body = m.group("body")
            if body.strip() and "<?" not in body:
                inline.append((m.start("body"), m.end("body")))
    return srcs, inline


# ------------------------------------------------------------- JS-сканер
# Односпрямований прохід із стеком дужок: рядки/шаблони/коменти/regex
# пропускаються, об'єктний літерал відрізняється від блока за символом перед
# «{». Член об'єкта — «рівно один рядковий літерал, без двокрапки» — і є
# слідом масової заміни (шортхенд для рядка в JS неможливий).
_OBJ_BEFORE = set("=([,:?")
_OBJ_WORDS = {"return"}
_RX_BEFORE = set("=([{,:;!&|?+-*%~^<>")
_RX_WORDS = {"return", "case", "in", "of", "typeof", "void", "delete",
             "new", "do", "else", "instanceof", "yield", "await"}
_OPS = set("+-*%!~^&|<>=?;.")
_WORD_RX = re.compile(r"[\w$]+")


def _consume_string(js: str, i: int) -> int:
    q = js[i]
    i += 1
    n = len(js)
    while i < n:
        c = js[i]
        if c == "\\":
            i += 2
            continue
        if c == q:
            return i + 1
        if c == "\n":            # битий рядок — не з'їдати решту файла
            return i
        i += 1
    return n


def _consume_tpl(js: str, i: int):
    """Текст шаблонного літерала від i. (next_i, увійшли у ${вираз})."""
    n = len(js)
    while i < n:
        c = js[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return i + 1, False
        if c == "$" and i + 1 < n and js[i + 1] == "{":
            return i + 2, True
        i += 1
    return n, False


def _consume_regex(js: str, i: int) -> int:
    n = len(js)
    i += 1
    in_cls = False
    while i < n:
        c = js[i]
        if c == "\\":
            i += 2
            continue
        if c == "\n":            # не regex або битий — вийти
            return i
        if c == "[":
            in_cls = True
        elif c == "]":
            in_cls = False
        elif c == "/" and not in_cls:
            i += 1
            while i < n and js[i].isalpha():
                i += 1
            return i
        i += 1
    return n


def _new_member(fr):
    fr["pre_n"] = 0
    fr["pre_str"] = None
    fr["colon"] = False
    fr["post_n"] = 0
    fr["post_str"] = None


def _end_member(fr):
    if fr["kind"] != "obj":
        return
    pre_n, pre_str = fr["pre_n"], fr["pre_str"]
    if fr["colon"]:
        if pre_n == 1 and pre_str:
            fr["keys"].append(pre_str[2])
            if fr["post_n"] == 1 and fr["post_str"]:
                fr["pairs"].append((pre_str[2], fr["post_str"][2]))
    elif pre_n == 1 and pre_str:
        fr["lones"].append(pre_str)
    _new_member(fr)


def _tok(fr, entry=None):
    """Значущий токен на рівні члена об'єкта."""
    if fr is None or fr["kind"] != "obj":
        return
    if fr["colon"]:
        fr["post_n"] += 1
        fr["post_str"] = entry if fr["post_n"] == 1 else None
    else:
        fr["pre_n"] += 1
        fr["pre_str"] = entry if fr["pre_n"] == 1 else None


def scan_js(js: str):
    """(lone-члени, об'єкти файла).

    lone: {"span": (s, e), "val": str, "obj": int}  — span разом з лапками;
    objects: {"keys": [...], "pairs": [(k, v)...], "span": (s, e)}."""
    n = len(js)
    i = 0
    last_sig = ""      # останній значущий символ коду
    last_word = ""     # останній токен-слово (для return /regex/ тощо)
    stack = []
    objects = []
    lones = []

    def top():
        return stack[-1] if stack else None

    while i < n:
        c = js[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "/" and i + 1 < n and js[i + 1] == "/":
            j = js.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and js[i + 1] == "*":
            j = js.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c in "\"'":
            s = i
            i = _consume_string(js, i)
            _tok(top(), (s, i, js[s + 1:i - 1]))
            last_sig, last_word = c, ""
            continue
        if c == "`":
            _tok(top())
            i, entered = _consume_tpl(js, i + 1)
            if entered:
                stack.append({"kind": "tpl"})
            last_sig, last_word = "`", ""
            continue
        if c == "/":
            if last_sig in _RX_BEFORE or last_sig == "" or last_word in _RX_WORDS:
                i = _consume_regex(js, i)
                _tok(top())
                last_sig, last_word = "/", ""
            else:
                _tok(top())
                i += 1
                last_sig, last_word = "/", ""
            continue
        if c == "{":
            is_obj = last_sig in _OBJ_BEFORE or last_word in _OBJ_WORDS
            _tok(top())
            fr = {"kind": "obj" if is_obj else "block", "start": i}
            if is_obj:
                fr.update({"keys": [], "pairs": [], "lones": []})
                _new_member(fr)
            stack.append(fr)
            last_sig, last_word = "{", ""
            i += 1
            continue
        if c == "}":
            fr = top()
            if fr and fr["kind"] == "tpl":
                stack.pop()
                i, entered = _consume_tpl(js, i + 1)
                if entered:
                    stack.append({"kind": "tpl"})
                last_sig, last_word = "`", ""
                continue
            if fr and fr["kind"] in ("obj", "block"):
                stack.pop()
                if fr["kind"] == "obj":
                    _end_member(fr)
                    oi = len(objects)
                    objects.append({"keys": fr["keys"], "pairs": fr["pairs"],
                                    "span": (fr["start"], i + 1)})
                    for s, e, val in fr["lones"]:
                        lones.append({"span": (s, e), "val": val, "obj": oi})
            last_sig, last_word = "}", ""
            i += 1
            continue
        if c in "([":
            _tok(top())
            stack.append({"kind": "par"})
            last_sig, last_word = c, ""
            i += 1
            continue
        if c in ")]":
            if stack and top()["kind"] == "par":
                stack.pop()
            last_sig, last_word = c, ""
            i += 1
            continue
        fr = top()
        if c == "," and fr and fr["kind"] == "obj":
            _end_member(fr)
            last_sig, last_word = ",", ""
            i += 1
            continue
        if c == ":" and fr and fr["kind"] == "obj" and not fr["colon"]:
            fr["colon"] = True
            last_sig, last_word = ":", ""
            i += 1
            continue
        m = _WORD_RX.match(js, i)
        if m:
            _tok(fr)
            last_sig = m.group(0)[-1]
            last_word = m.group(0)
            i = m.end()
            continue
        _tok(fr)
        last_sig, last_word = c, ""
        i += 1

    # лише мапи даних: 2+ справні пари "ключ":"значення" поруч. Без цього
    # блок, помилково взятий за об'єкт, міг би фолсити на самотньому рядку.
    good = [ln for ln in lones if len(objects[ln["obj"]]["pairs"]) >= 2]
    return good, objects


# ------------------------------------------------------------- відновлення
_VAL_SHAPE_RX = re.compile(r"^(\D*?)(\d+)(\D*)$", re.S)


def _common_prefix(a: str, b: str) -> int:
    k = 0
    while k < len(a) and k < len(b) and a[k] == b[k]:
        k += 1
    return k


def _recover(lone: dict, objects: list) -> str | None:
    """'"ключ":"значення"' або None, коли доказів не вистачає.

    Значення: усі сусідні значення мапи однієї форми <prefix><N><suffix>,
    у послідовності N рівно одна прогалина, уламок закінчується тим самим
    suffix. Ключ: єдиний ключ іншої мапи файла, відсутній серед ключів
    ураженої, з найдовшим спільним префіксом з уламком (≥6 символів)."""
    obj = objects[lone["obj"]]
    vals = [v for _, v in obj["pairs"]]
    if len(vals) < 3:
        return None
    shapes = [_VAL_SHAPE_RX.match(v) for v in vals]
    if not all(shapes):
        return None
    prefixes = {s.group(1) for s in shapes}
    suffixes = {s.group(3) for s in shapes}
    if len(prefixes) != 1 or len(suffixes) != 1:
        return None
    suffix = suffixes.pop()
    if not suffix or not lone["val"].endswith(suffix):
        return None
    nums = sorted(int(s.group(2)) for s in shapes)
    gaps = [x for x in range(nums[0], nums[-1]) if x not in set(nums)]
    if len(gaps) != 1:
        return None
    value = f"{prefixes.pop()}{gaps[0]}{suffix}"
    if value in vals:
        return None

    own = set(obj["keys"])
    cand = {}
    for oi, other in enumerate(objects):
        if oi == lone["obj"] or len(other["pairs"]) < 2:
            continue
        for k in other["keys"]:
            if k not in own:
                cand[k] = max(cand.get(k, 0), _common_prefix(k, lone["val"]))
    if not cand:
        return None
    best = max(cand.values())
    keys = [k for k, sc in cand.items() if sc == best]
    if best < 6 or len(keys) != 1:
        return None
    return f'"{keys[0]}":"{value}"'


def _drop_member(js: str, s: int, e: int) -> tuple:
    """Межі видалення члена разом з ОДНІЄЮ сусідньою комою."""
    j = e
    while j < len(js) and js[j] in " \t\r\n":
        j += 1
    if j < len(js) and js[j] == ",":
        return s, j + 1
    j = s
    while j > 0 and js[j - 1] in " \t\r\n":
        j -= 1
    if j > 0 and js[j - 1] == ",":
        return j - 1, e
    return s, e


def _fix_js(js: str) -> str:
    lones, objects = scan_js(js)
    if not lones:
        return js
    out = js
    for lone in sorted(lones, key=lambda x: x["span"][0], reverse=True):
        s, e = lone["span"]
        member = _recover(lone, objects)
        if member is None:
            s, e = _drop_member(out, s, e)
            out = out[:s] + out[e:]
        else:
            out = out[:s] + member + out[e:]
    return out


# ----------------------------------------------------------------- правила
def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _clip(s: str, limit: int = 60) -> str:
    return s if len(s) <= limit else s[:limit - 1] + "…"


def run_branch(files: dict, all_paths: list, branch: str = "") -> list:
    issues = []
    present = set(all_paths) | set(files)
    pages = {p: t for p, t in files.items() if not p.endswith(".js")}
    acc_pages = {p: _accordion_pairs(t) for p, t in pages.items()}
    # js → сторінки, що його тягнуть (окремо — сторінки з акордеоном)
    used_by, acc_by = {}, {}
    for path, text in pages.items():
        srcs, inline = _page_scripts(path, text)
        for resolved, raw, at in srcs:
            used_by.setdefault(resolved, []).append(path)
            if acc_pages[path]:
                acc_by.setdefault(resolved, []).append(path)
                if resolved not in present:
                    issues.append({
                        "path": path, "line": _line(text, at),
                        "severity": "error",
                        "message": (f"сторінка з FAQ-акордеоном "
                                    f"({acc_pages[path]} питань) тягне "
                                    f"відсутній у вітці скрипт {raw!r} — "
                                    f"відповіді не відкриються ніколи"),
                    })
        for s, e in inline:
            lones, _ = scan_js(text[s:e])
            for lone in lones:
                at = s + lone["span"][0]
                issues.append({
                    "path": path, "line": _line(text, at),
                    "severity": "error",
                    "message": (f"інлайн-скрипт зламаний масовою заміною: "
                                f"рядок \"{_clip(lone['val'])}\" став членом "
                                f"об'єкта без двокрапки — SyntaxError, "
                                f"скрипт сторінки мертвий цілком"),
                })

    for path, text in files.items():
        if not path.endswith(".js"):
            continue
        lones, _ = scan_js(text)
        for lone in lones:
            dead = sorted(set(acc_by.get(path, [])))
            users = sorted(set(used_by.get(path, [])))
            if dead:
                tail = (f" FAQ-акордеон лишився без обробника на: "
                        f"{', '.join(dead)}")
            elif users:
                tail = f" Увесь JS мертвий на: {', '.join(users[:4])}"
            else:
                tail = " Жодна сторінка файл не тягне."
            issues.append({
                "path": path, "line": _line(text, lone["span"][0]),
                "severity": "error" if users else "warn",
                "message": (f"масова заміна зламала синтаксис: рядок "
                            f"\"{_clip(lone['val'])}\" став членом об'єкта "
                            f"без двокрапки (SyntaxError — файл не "
                            f"виконується цілком).{tail}"),
            })
    return issues


def fix(path: str, text: str) -> str:
    """Пофайлово лагодяться лише ІНЛАЙН-скрипти сторінок: сторінка сама
    змінюється, кеш її не тримає. Ремонт .js-файлів живе у fix_branch —
    разом із хеш-перейменуванням, що пробиває кеш домену."""
    if path.endswith(".js"):
        return text
    out, shift = text, 0
    _, inline = _page_scripts(path, text)
    for s, e in inline:
        body = out[s + shift:e + shift]
        new = _fix_js(body)
        if new != body:
            out = out[:s + shift] + new + out[e + shift:]
            shift += len(new) - len(body)
    return out


def fix_branch(files, all_paths, branch: str = ""):
    """Лагодить .js-файли і пробиває кеш домену (02.10, sozsazdacg): битий
    site.js живе у браузер/CDN-кеші, бо адреса не змінилась — прев'ю з
    no-store показує фікс, живий домен ні. Полагоджений js отримує
    ХЕШ-ім'я (site-<crc8>.js, конвенція media.hashed_path), посилання
    перетаргечуються, старе ім'я видаляється."""
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
    import media as _media
    actions = []
    for path in sorted(files):
        if not path.endswith(".js"):
            continue
        cur = files[path]
        repaired = _fix_js(cur)
        if repaired == cur:
            continue
        content = repaired
        new_rel = _media.hashed_path(path, content.encode("utf-8"))
        if new_rel == path:
            continue
        actions.append({"type": "create", "path": new_rel,
                        "content": content})
        actions.append({"type": "delete", "path": path})
        ref_rx = re.compile(
            r"""(?P<pre>["'(=\s>])(?P<dots>(?:\.\./)+|\./|/|)"""
            + re.escape(path)
            + r"""(?P<v>\?v=[0-9a-f]+)?(?=["')\s>,#?])""")
        for p, t in files.items():
            if p.endswith(".js"):
                continue
            nt = ref_rx.sub(lambda m: m.group("pre") + m.group("dots")
                            + new_rel, t)
            if nt != t:
                actions.append({"type": "edit", "path": p, "content": nt})
    return actions
