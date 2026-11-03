"""Напис лого php-вайта — строгою латиницею.

QA 01.10 (vemsitzhii, nokihaq): «Название в логотипе „Início Books" не
строгой латиницей: „í". Логотип пишется только латинскими буквами — без
символов над буквами, арабских и азиатских знаков».

Судиться ЛИШЕ напис, що є назвою сайту (site_name.same — порівняння без
діакритики): пункт меню «Início» («Головна» португальською) у home-лінку
навігації — контентне слово, його чек не чіпає. Title/meta теж не
чіпаються — вимога QA стосується самого логотипа.

Vue-вайти цим не ходять: там те саме робить logo_brand.
"""
import re

import site_name

NAME = "Лого: напис строгою латиницею"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"brand"}
PROJECTS = ["php"]
DESCRIPTION = ("Напис лого (текст home-лінка шапки/футера, що збігається з "
               "назвою сайту) містить діакритику чи нелатинські знаки — "
               "«Início Books», «Mediação». Автофікс переписує напис і alt "
               "строгою латиницею (site_name.latin); title і меню не "
               "чіпаються.")
FILES = ["*.html", "*.htm", "*.php"]

CHROME_RX = re.compile(r"<(header|footer)\b.*?</\1\s*>", re.S | re.I)
HOME_A_RX = re.compile(
    r"""<a\b[^>]*\bhref\s*=\s*["'](?:\.?/|\.?/?index\.(?:html?|php))["'][^>]*>"""
    r"""(?P<body>.*?)</a\s*>""",
    re.S | re.I)
TAG_RX = re.compile(r"<[^>]+>")
ALT_RX = re.compile(r'(\balt\s*=\s*")([^"]*)(")', re.I)


def _is_page(path: str) -> bool:
    return path.lower().endswith((".html", ".htm", ".php"))


def _slot_name(body: str) -> str:
    return " ".join(TAG_RX.sub(" ", body).split())


def _bad_chars(s: str) -> str:
    """Не-ASCII ЛІТЕРИ і діакритичні знаки — емодзі/символи (🔒, ★, →) не
    судяться: вимога QA про букви, а не про декор (кейс revl-seok 01.10)."""
    import unicodedata
    return "".join(dict.fromkeys(
        ch for ch in s
        if ord(ch) > 127 and (ch.isalpha() or unicodedata.combining(ch))))


_WORD_RX = re.compile(r"[^\W\d_]+", re.UNICODE)


def _latinize_text(s: str) -> str:
    """Латинізує ЛИШЕ слова, лишаючи емодзі/цифри/пунктуацію на місці:
    «🔒 Café Notary» → «🔒 Cafe Notary». Слово без латинського сліду
    (кирилиця/CJK) випадає, як у site_name.latin."""
    out = _WORD_RX.sub(
        lambda m: (site_name.latin(m.group(0)) or "")
        if _bad_chars(m.group(0)) else m.group(0), s)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def _brand_slots(text: str, expected: str):
    """[(abs_start, body, name)] — home-лінки шапки/футера, чий видимий
    текст Є назвою сайту. «<?» у тілі — обчислюваний напис, не судимо."""
    out = []
    for blk in CHROME_RX.finditer(text):
        for m in HOME_A_RX.finditer(blk.group(0)):
            body = m.group("body")
            if "<?" in body:
                continue
            name = _slot_name(body)
            if name and site_name.same(name, expected):
                out.append((blk.start() + m.start(), body, name))
    return out


def _expected(branch: str, files: dict) -> str:
    try:
        return site_name.expected(branch, files) or ""
    except Exception:
        return ""


_CJK_RX = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
_TITLE_RX = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_SEG_RX = re.compile(r"\s*[｜|–—:：·・-]\s*")


def _title_segments(files: dict) -> set:
    out = set()
    for p, t in files.items():
        if not _is_page(p):
            continue
        m = _TITLE_RX.search(t)
        if m:
            out.update(s.strip() for s in _SEG_RX.split(TAG_RX.sub("", m.group(1))) if s.strip())
    return out


def run_branch(files, all_paths, branch: str = ""):
    expected = _expected(branch, files)
    if not expected:
        return []
    segs = _title_segments(files)
    issues = []
    for path in sorted(files):
        if not _is_page(path):
            continue
        text = files[path]
        for start, _body, name in _brand_slots(text, expected):
            bad = _bad_chars(name)
            if not bad:
                continue
            if _CJK_RX.search(name):
                # японський/китайський вордмарк латинізувати нема чим; QA
                # приймає його, коли він = сегмент title (jp 1step 28.10:
                # «Sotododua｜コドモテラス｜…»); інакше — лише вручну
                if name.strip() in segs:
                    continue
                issues.append({"path": path, "line": text.count("\n", 0, start) + 1, "severity": "warn",
                               "message": (f"лого «{name}» не латиницею і не збігається з жодним сегментом <title> — "
                                           f"QA приймає японський напис лише як перше слово title «Домен｜{name}｜…»; "
                                           f"виправ title або лого вручну")})
                continue
            shown = _latinize_text(name) or site_name.latin(name) or name
            issues.append({"path": path,
                           "line": text.count("\n", 0, start) + 1,
                           "severity": "error",
                           "message": (f"назва в лого «{name}» не строгою "
                                       f"латиницею: «{bad}» — логотип "
                                       f"пишеться лише латинськими: "
                                       f"«{shown}»")})
    return issues


def _latinize_body(body: str) -> str:
    """Латинізує текстові вузли і alt слота; теги, порядок і емодзі —
    недоторкані."""
    parts = re.split(r"(<[^>]+>)", body)
    for i, p in enumerate(parts):
        if i % 2:
            parts[i] = ALT_RX.sub(
                lambda m: m.group(1) + (_latinize_text(m.group(2))
                                        or m.group(2)) + m.group(3), p)
        elif p.strip() and _bad_chars(p):
            parts[i] = p.replace(p.strip(), _latinize_text(p.strip())
                                 or p.strip())
    return "".join(parts)


def fix_branch(files, all_paths, branch: str = ""):
    expected = _expected(branch, files)
    if not expected:
        return []
    actions = []
    for path in sorted(files):
        if not _is_page(path):
            continue
        text = files[path]
        new = text
        for _start, body, name in _brand_slots(text, expected):
            if not _bad_chars(name) or _CJK_RX.search(name):
                continue                     # CJK — лише вручну (див. run_branch)
            new = new.replace(body, _latinize_body(body))
        if new != text:
            actions.append({"type": "edit", "path": path, "content": new})
    return actions
