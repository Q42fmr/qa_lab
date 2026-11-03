"""WP-Rocket lazyload: картинки лишаються svg-заглушками назавжди.

Кейс ladehavdpafnacesia-cop-br-pt (868mjm950, 19.10): «Главная пустая, все
картинки отдают белым экраном». Скрейп зняв сторінку в проміжному стані
WP Rocket: у `<img>` стоїть `src="data:image/svg+xml,…"` (прозора
заглушка потрібного розміру), а справжній файл лежить у `data-lazy-src`
/ `data-lazy-srcset` / `data-lazy-sizes`. Підміну робить lazyload.min.js
за селектором `img[data-lazy-src].rocket-lazyload` — а клас
`rocket-lazyload` скрейпер зрізав (0 входжень на 30 заглушок), тож
скрипт не бачить жодної картинки і заглушки лишаються. Заміряно в
браузері: після DOMContentLoaded, скролу й mousemove — 0 завантажених
картинок із 13.

Другий шар того самого «білого екрана» — Elementor: віджети з класом
`elementor-invisible` сидять у visibility:hidden до entrance-анімації,
яку запускає frontend.min.js лише за waypoint; на вайті без живого WP
частина так і не прокидається (22 → 19 після скролу).

Фікс детермінований і статичний: справжні src/srcset/sizes переїжджають
на місце заглушки, lazy-атрибути зникають, `elementor-invisible`
знімається (втрачається лише анімація появи). Той самий патерн у
`<iframe data-lazy-src>` і `<source data-lazy-srcset>`.
"""
import re

NAME = "Картинки-заглушки WP-Rocket lazyload"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("<img src=\"data:image/svg+xml…\" data-lazy-src=\"…\"> — скрейп "
               "WP Rocket без класу rocket-lazyload: заглушки ніколи не "
               "міняються на картинки, сторінка біла. Фікс переносить "
               "data-lazy-src/srcset/sizes у src/srcset/sizes і знімає "
               "elementor-invisible.")
FILES = ["*.html", "*.htm", "*.php"]

TAG_RX = re.compile(r"<(img|iframe|source)\b((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.I)
ATTR_RX = re.compile(r"""\s+(data-lazy-src|data-lazy-srcset|data-lazy-sizes|src|srcset|sizes)\s*=\s*("[^"]*"|'[^']*')""", re.I)
PLACEHOLDER_RX = re.compile(r"""\bsrc\s*=\s*["']data:image/svg\+xml""", re.I)
INVISIBLE_RX = re.compile(r"""(class\s*=\s*["'][^"']*?)\s*\belementor-invisible\b""", re.I)


def _lazy_tags(text: str):
    """Теги, де є data-lazy-src/-srcset і src — заглушка або відсутній."""
    for m in TAG_RX.finditer(text):
        attrs = m.group(2)
        if "data-lazy-src" not in attrs.lower():
            continue
        has_src = re.search(r"""(?<![\w-])src\s*=""", attrs, re.I)
        if has_src and not PLACEHOLDER_RX.search(attrs):
            continue                      # справжній src уже на місці
        yield m


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def run(path, text):
    tags = list(_lazy_tags(text))
    if not tags:
        return []
    n_inv = len(INVISIBLE_RX.findall(text))
    extra = f" і {n_inv} блок(ів) elementor-invisible" if n_inv else ""
    return [{"path": path, "line": _line_of(text, tags[0].start()),
             "severity": "error",
             "message": (f"{len(tags)} картинок-заглушок WP-Rocket (src=data:svg, "
                         f"справжній файл у data-lazy-src; клас rocket-lazyload "
                         f"зрізано — lazyload.js їх не бачить){extra} — фікс "
                         f"поверне справжні src/srcset/sizes і зніме "
                         f"elementor-invisible")}]


def _delazy(tag_attrs: str) -> str:
    """Атрибути тега: data-lazy-* → src/srcset/sizes; старі src/srcset/sizes
    (заглушки) викидаються; решта атрибутів лишається на місці."""
    lazy = {}
    for a in ATTR_RX.finditer(tag_attrs):
        name = a.group(1).lower()
        if name.startswith("data-lazy-"):
            lazy[name[len("data-lazy-"):]] = a.group(2)
    out = ATTR_RX.sub("", tag_attrs)
    real = "".join(f' {k}={v}' for k, v in lazy.items() if k in ("src", "srcset", "sizes"))
    return out.rstrip("/ ") + real + (" /" if tag_attrs.rstrip().endswith("/") else "")


def fix(path, text):
    tags = list(_lazy_tags(text))
    if not tags:
        return text
    out, last = [], 0
    for m in tags:
        out.append(text[last:m.start()])
        out.append(f"<{m.group(1)}{_delazy(m.group(2))}>")
        last = m.end()
    out.append(text[last:])
    new = "".join(out)
    return INVISIBLE_RX.sub(r"\1", new)
