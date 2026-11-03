"""Телефон: два номери злиплись в одному tel: (13.10, it-it партія).

Кейс vodupiu-it-it (+390950979340+390959596174) і ще 12 віток
(bicabwie, drabio, ismamgo, kevmmodfo, nopdirl, ospeqa, pawmupeqoq,
sawrohedo, soxcudi, sofoxne, vevafdli, veqhehe): контакт-блок мав два
телефони, генератор вклеїв обидва в ОДИН href — «tel:+39...+39...».
Видимий текст здоровий («N1 / N2»), але дзвінок по лінку битий: ОС
відмовляється набирати номер з плюсом усередині.

Фікс:
  * текст тримає обидва номери з роздільником — лінк розділяється на два
    <a> з тими самими атрибутами, кожен зі своїм tel: і своїм шматком
    тексту; роздільник лишається текстом між ними;
  * текст тримає один номер — href звужується до нього (щоб href
    відповідав тому, що бачить людина);
  * інакше — href звужується до першого номера.
"""
import re

NAME = "Телефон: два номери в одному tel:"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"phone"}
PROJECTS = ["php"]
DESCRIPTION = ("href=\"tel:+39...+39...\" — два номери вклеєні в один лінк, "
               "дзвінок не працює. Фікс розділяє лінк на два по роздільнику "
               "видимого тексту або звужує href до показаного номера.")
FILES = ["*.html", "*.htm", "*.php"]

# злиплий tel: ≥2 повних номери (плюс усередині після цифр)
_GLUED_TEL_RX = re.compile(
    r"""<a\b(?P<pre>[^>]*?)href=["']tel:(?P<href>\+?\d[\d]{5,14}"""
    r"""(?:\+\d[\d]{5,14})+)["'](?P<post>[^>]*)>(?P<inner>(?:(?!</a>).)*?)</a>""",
    re.I | re.S)
# те саме БЕЗ плюса (aebneunir-br-pt 20.10: tel:112796370411985783154 =
# «(11) 2796-3704 / (11) 98578-3154»): href довший за будь-який номер
# (>15 цифр), а межі видно лише з видимого тексту — він і ріже
_LONG_TEL_RX = re.compile(
    r"""<a\b(?P<pre>[^>]*?)href=["']tel:(?P<href>\+?\d{16,40})["'](?P<post>[^>]*)>"""
    r"""(?P<inner>(?:(?!</a>).)*?)</a>""", re.I | re.S)
_NUM_RX = re.compile(r"\+?\d[\d]{5,14}")
# третя форма (754 br-pt 27.10): у href вклеєно видимий текст як є —
# «tel:+55 21 2155-4551 / +55 21 2155-4552»: пробіли, дефіси, « / » між
# номерами. Номери — групи з ≥7 цифр, розділені роздільником тексту
_RAW_TEL_RX = re.compile(
    r"""<a\b(?P<pre>[^>]*?)href=["']tel:(?P<href>[^"']*?[\d)]\s*(?:/|·|•|,|\|)\s*\+?[\d(][^"']*)["'](?P<post>[^>]*)>"""
    r"""(?P<inner>(?:(?!</a>).)*?)</a>""", re.I | re.S)
# роздільники видимого тексту між номерами
_SEP_SPLIT_RX = re.compile(r"(\s*(?:/|·|•|,|\|)\s*)")
_TAG_RX = re.compile(r"<[^>]+>")


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _split_href(href: str, inner: str = ""):
    """Номери з href: по плюсах; без плюсів — по видимих номерах тексту,
    якщо їхні цифри підряд дають href (інакше [] — не наш кейс)."""
    if "+" in href.lstrip("+"):
        return _NUM_RX.findall(href)
    plain = _TAG_RX.sub("", inner)
    shown = [_digits(p) for p in _SEP_SPLIT_RX.split(plain) if _digits(p)]
    if len(shown) >= 2 and "".join(shown) == _digits(href):
        return shown
    return []


def _raw_numbers(href: str) -> list:
    """Номери з сирого href «+55 21 2155-4551 / +55 21 2155-4552» → ['+552121554551', …];
    [] якщо шматків з ≥7 цифрами менше двох."""
    parts = [p for p in _SEP_SPLIT_RX.split(href) if _digits(p) and not _SEP_SPLIT_RX.fullmatch(p)]
    nums = [("+" if p.strip().startswith("+") else "") + _digits(p) for p in parts if len(_digits(p)) >= 7]
    return nums if len(nums) >= 2 else []


def _glued(text: str):
    """[(match, номери)] для трьох форм склейки."""
    out = []
    for m in _GLUED_TEL_RX.finditer(text):
        out.append((m, _split_href(m.group("href"))))
    for m in _LONG_TEL_RX.finditer(text):
        nums = _split_href(m.group("href"), m.group("inner"))
        if nums:
            out.append((m, nums))
    for m in _RAW_TEL_RX.finditer(text):
        nums = _raw_numbers(m.group("href"))
        if nums:
            out.append((m, nums))
    out.sort(key=lambda x: x[0].start())
    return out


def run(path, text):
    issues = []
    for m, nums in _glued(text):
        issues.append({
            "line": text.count("\n", 0, m.start()) + 1,
            "severity": "error",
            "message": (f"у tel: злиплись {len(nums)} "
                        f"номери («tel:{m.group('href')[:34]}…») — дзвінок по "
                        f"такому лінку не працює; фікс розділить лінк або "
                        f"звузить href до показаного номера"),
        })
    return issues


def _rebuild(m: re.Match, nums: list | None = None) -> str:
    nums = nums or _split_href(m.group("href"), m.group("inner"))
    inner = m.group("inner")
    pre, post = m.group("pre"), m.group("post")
    plain = _TAG_RX.sub("", inner)
    parts = _SEP_SPLIT_RX.split(plain)
    # шматки тексту, що виглядають як номери — по порядку
    text_nums = [p for p in parts if _digits(p)]

    def links(parts, pre, post):
        out, k = [], 0
        for p in parts:
            if _digits(p):
                num = nums[k] if _digits(nums[k]) == _digits(p) else "+" + _digits(p)
                if not num.startswith("+") and p.strip().startswith("+"):
                    num = "+" + num
                out.append(f'<a{pre}href="tel:{num}"{post}>{p}</a>')
                k += 1
            else:
                out.append(p)
        return "".join(out)

    if _TAG_RX.search(inner) is None and len(text_nums) == len(nums) > 1:
        # «N1 / N2 [/ N3]» — розбираємо на окремі лінки, роздільники лишаються
        return links(parts, pre, post)
    # іконка + <span>N1 / N2</span> (754 br-pt 27.10): іконка лишається в
    # першому лінку, span розбирається на два
    sm = re.fullmatch(r"(?P<lead>\s*(?:<svg\b.*?</svg>|<i\b[^>]*>.*?</i>|<img\b[^>]*/?>)\s*)?"
                      r"<span\b(?P<sattr>[^>]*)>(?P<stext>[^<]*)</span>\s*", inner, re.S | re.I)
    if sm and len([p for p in _SEP_SPLIT_RX.split(sm.group("stext")) if _digits(p)]) == len(nums) > 1:
        sparts = _SEP_SPLIT_RX.split(sm.group("stext"))
        out, k = [], 0
        for p in sparts:
            if _digits(p):
                num = nums[k] if _digits(nums[k]) == _digits(p) else "+" + _digits(p)
                if not num.startswith("+") and p.strip().startswith("+"):
                    num = "+" + num
                lead = sm.group("lead") or "" if k == 0 else ""
                out.append(f'<a{pre}href="tel:{num}"{post}>{lead}<span{sm.group("sattr")}>{p}</span></a>')
                k += 1
            else:
                out.append(p)
        return "".join(out)
    # один видимий номер — href звужується до нього
    shown = _digits(plain)
    pick = next((n for n in nums if _digits(n) == shown), nums[0])
    if not pick.startswith("+"):
        pick = "+" + pick
    return f'<a{pre}href="tel:{pick}"{post}>{inner}</a>'


def fix(path, text):
    out, last = [], 0
    for m, nums in _glued(text):
        if m.start() < last:
            continue
        out.append(text[last:m.start()])
        out.append(_rebuild(m, nums))
        last = m.end()
    out.append(text[last:])
    return "".join(out)
