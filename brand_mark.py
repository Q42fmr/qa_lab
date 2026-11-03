"""Знаки лого/favicon: детерміноване різноманіття замість одного шаблону.

Досі автофікс малював одне й те саме: літера на скругленому квадраті
theme-кольору. Тут знак складається з чотирьох осей:

  * ФОРМА тла     — squircle / коло / щит / гекс / ромб;
  * ПАЛІТРА       — рівне тло, темніше, градієнти (у темніший, у комплемент,
                    в аналог), світле тло з кольоровою літерою;
  * ЛЕЙАУТ        — літера / два ініціали / літера з кільцем / літера з
                    тематичною іконкою зверху / сама іконка (лише ручний
                    вибір в UI — автофікс тримає контракт «знак несе літеру»);
  * ІКОНКА        — з вбудованого набору за тематикою вайта (текст title,
                    description, заголовків) — той самий сигнал, за яким
                    photo-setter шукає фото.

Вибір детермінований: hash(вітка) розкладається по осях, тож автофікс на
різних вітках дає РІЗНІ знаки, а повторний прогін тієї самої вітки — той
самий знак (ідемпотентність фіксів не ламається). `variants()` віддає
розгортку варіантів для вкладки «Медіа → Лого/Favicon».
"""
from __future__ import annotations

import colorsys
import json
import re
import zlib
from pathlib import Path

import site_name

HEX_RX = re.compile(r"^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{3}$")
DEFAULT_BG = "#2E3338"
# скільки перших варіантів — стабільне ядро (не залежить від seed)
STABLE_COUNT = 12

# --------------------------------------------------------------- тематика
# порядок = пріоритет; перший збіг виграє
_THEME_ICONS = [
    (r"imobili|im[oó]ve|inmobil|properti|real\s*estate|resid[eê]nc", "building"),
    (r"constru|engenhar|arquitet|obra\b|reforma", "building"),
    (r"viag|hotel|pousada|retiro|hospeda|turis|travel|resort|estadia", "key"),
    (r"advoc|jur[ií]d|legal|direito|abogad|avvocat|\blaw\b|recht", "scales"),
    (r"financ|invest|capital|cr[eé]dit|contab|fiscal|\bbank|patrim[oô]ni", "chart"),
    (r"gastro|cozinh|restaurante|caf[eé]|comida|sabor|culin[aá]r|chef", "fork"),
    (r"cl[ií]nic|sa[uú]de|dental|odont|m[eé]dic|salud|terapia|fisio|care\b", "heart"),
    (r"tecnolog|digital|software|sistema|dados|inova|\bweb\b|\bapp\b|\bdev\b", "chip"),
    (r"motor|carro\b|\bauto\b|ve[ií]cul|oficina|mec[aâ]nic", "car"),
    (r"belez|est[eé]tic|beauty|sal[aã]o|\bspa\b|cosm[eé]t|barb", "spark"),
    (r"escola|curso|educa|academ|ensino|aprend|treinament", "cap"),
    (r"fotograf|\bphoto\b|est[uú]dio", "camera"),
    (r"jardim|verde\b|\beco\b|sustent|ambient|plant|flor", "leaf"),
    (r"fitness|muscula|\bgym\b|trein[oa]\b", "dumbbell"),
]

# 24x24, filled — прості геометричні форми, без зовнішніх залежностей
_ICON_PATHS = {
    "building": "M4 21V5l7-3v19H4zm9 0V9l7 3v9h-7zM6 8h3v2H6V8zm0 4h3v2H6v-2z"
                "m9 2h3v2h-3v-2z",
    "key": "M14 3a7 7 0 1 0 6.3 11H22v3h-3v3h-3v-3h-1.7A7 7 0 0 0 14 3z"
           "m-2 5a2 2 0 1 1 0 4 2 2 0 0 1 0-4z",
    "scales": "M11 3h2v2h4.6l2.9 6.8a3.6 3.6 0 0 1-7.2 0L15.6 7H13v12h4v2H7v-2"
              "h4V7H8.4l2.3 4.8a3.6 3.6 0 0 1-7.2 0L6.4 5H11V3z",
    "chart": "M4 20h3V9H4v11zm6.5 0h3V4h-3v16zM17 20h3v-8h-3v8z",
    "fork": "M7 3v7a2 2 0 0 0 2 2v9h2v-9a2 2 0 0 0 2-2V3h-2v6H9V3H7z"
            "m10 0c-2 0-3 3-3 6v4h2v8h2V3h-1z",
    "heart": "M12 21C5 15 2 11 2 7.5A4.5 4.5 0 0 1 6.5 3C8.5 3 11 5 12 6.5"
             "C13 5 15.5 3 17.5 3A4.5 4.5 0 0 1 22 7.5C22 11 19 15 12 21z",
    "chip": "M9 2h2v3h2V2h2v3h3v2h3v2h-3v2h3v2h-3v2h3v2h-3v3h-2v3h-2v-3h-2v3H9"
            "v-3H6v-3H3v-2h3v-2H3v-2h3V9H3V7h3V4h3V2zm-1 6v8h8V8H8z",
    "car": "M5 11l2-5h10l2 5h2v6h-2v2h-3v-2H8v2H5v-2H3v-6h2zm2.2 0h9.6l-1.2-3"
           "H8.4l-1.2 3zM7 15a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zm10 0"
           "a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z",
    "spark": "M12 2l2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4L12 2z",
    "cap": "M12 3 1 9l11 6 9-4.9V17h2V9L12 3zM5 13.2V17c0 2 3.1 4 7 4s7-2 7-4"
           "v-3.8l-7 3.8-7-3.8z",
    "camera": "M9 4 7.2 6H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8"
              "a2 2 0 0 0-2-2h-3.2L15 4H9zm3 4.5A4.5 4.5 0 1 1 7.5 13"
              "A4.5 4.5 0 0 1 12 8.5z",
    "leaf": "M20 4C9 4 4 9 4 20c11 0 16-5 16-16zM6.5 17.5C8 12 12 8 17.5 6.5"
            "C14 13 13 14 6.5 17.5z",
    "dumbbell": "M2 10h2V7h3v10H4v-3H2v-4zm20 0h-2V7h-3v10h3v-3h2v-4z"
                "M9 11h6v2H9v-2z",
    "star": "M12 2l2.9 6.6 7.1.8-5.3 4.8 1.5 7-6.2-3.7-6.2 3.7 1.5-7L2 9.4"
            "l7.1-.8L12 2z",
}

_TEXTY_RX = re.compile(
    r"<title[^>]*>(.*?)</title>|<h1[^>]*>(.*?)</h1>"
    r'|<meta\s+name="description"\s+content="([^"]*)"', re.S | re.I)
_TAGS_RX = re.compile(r"<[^>]+>")


def theme_icon(files: dict | None) -> str:
    """Ключ іконки за тематикою вайта; 'star' — коли тему не вгадали."""
    blob = []
    for path in sorted(files or {}):
        if path.rsplit("/", 1)[-1].lower().startswith("index."):
            for m in _TEXTY_RX.finditer((files or {})[path]):
                blob.append(_TAGS_RX.sub(" ", next(g for g in m.groups() if g is not None)))
    text = " ".join(blob).lower()
    for rx, key in _THEME_ICONS:
        if re.search(rx, text):
            return key
    return "star"


# --------------------------------------------------------------- кольори
def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    cl = lambda v: max(0, min(255, round(v * 255)))
    return f"#{cl(r):02X}{cl(g):02X}{cl(b):02X}"


def _shift(base: str, dh: float = 0.0, ds: float = 0.0, dl: float = 0.0) -> str:
    h, l, s = colorsys.rgb_to_hls(*_hex_to_rgb(base))
    h = (h + dh) % 1.0
    s = max(0.0, min(1.0, s + ds))
    l = max(0.04, min(0.96, l + dl))
    return _rgb_to_hex(*colorsys.hls_to_rgb(h, l, s))


def _text_on(bg: str) -> str:
    r, g, b = _hex_to_rgb(bg)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return "#111417" if lum > 0.6 else "#FFFFFF"


# палітра: (назва, fn(base) -> (fill_або_None, stop1, stop2, fg))
def _palettes():
    return [
        ("solid", lambda c: (c, None, None, _text_on(c))),
        ("deep", lambda c: (_shift(c, dl=-0.14, ds=0.08), None, None,
                            _text_on(_shift(c, dl=-0.14)))),
        ("grad-dark", lambda c: (None, _shift(c, dl=0.06), _shift(c, dl=-0.22),
                                 _text_on(c))),
        ("grad-comp", lambda c: (None, c, _shift(c, dh=0.5, dl=-0.08),
                                 _text_on(c))),
        ("grad-analog", lambda c: (None, _shift(c, dh=-0.09), _shift(c, dh=0.09, dl=-0.1),
                                   _text_on(c))),
        ("paper", lambda c: (_shift(c, ds=-0.25, dl=0.42), None, None,
                             _shift(c, dl=-0.18, ds=0.1))),
    ]


# --------------------------------------------------------------- форми тла
_SHAPES = {
    "squircle": '<rect width="64" height="64" rx="14" fill="{f}"/>',
    "circle": '<circle cx="32" cy="32" r="31" fill="{f}"/>',
    "shield": '<path d="M32 2 58 10v20c0 16-11 27-26 32C17 57 6 46 6 30V10z" fill="{f}"/>',
    "hex": '<path d="M32 2 57 17v30L32 62 7 47V17z" fill="{f}"/>',
    "diamond": '<rect x="9.4" y="9.4" width="45.2" height="45.2" rx="9" '
               'fill="{f}" transform="rotate(45 32 32)"/>',
}
_SHAPE_ORDER = ["squircle", "circle", "shield", "hex", "diamond"]
_LAYOUTS = ["mono", "duo", "ring", "icon-letter", "icon",
            "icon-left", "icon-right", "letter-icon", "icon-badge", "nested"]
AUTOFIX_LAYOUTS = ("mono", "duo", "ring", "icon-letter", "icon-left",
                   "icon-right", "letter-icon", "icon-badge",
                   "nested")                        # знак несе літеру

# Шрифти літер — ТІЛЬКИ системні стеки: svg-favicon не підвантажує
# webfont-и (браузери ріжуть зовнішні ресурси в іконках), тож різноманіття
# будується на родинах, які вже стоять у відвідувача. Порядок — вісь
# розгортки, як _SHAPE_ORDER.
_FONTS = [
    ("system-ui, sans-serif", 700, ""),
    ("Georgia, 'Times New Roman', serif", 700, ""),
    ("'Arial Black', Arial, sans-serif", 900, ""),
    ("Consolas, 'Courier New', monospace", 700, ""),
    ("Georgia, 'Times New Roman', serif", 700, ' font-style="italic"'),
    ("Impact, 'Arial Narrow', sans-serif", 400, ""),
    ("'Trebuchet MS', Verdana, sans-serif", 700, ""),
    ("'Segoe UI', Tahoma, sans-serif", 400, ""),
]


def _font_attrs(fi: int) -> str:
    fam, weight, extra = _FONTS[fi % len(_FONTS)]
    return f'font-family="{fam}" font-weight="{weight}"{extra}'


def _inner_for(shape: str, inner: str = "") -> str:
    """Внутрішня форма nested: задана, якщо валідна і НЕ збігається із
    зовнішньою; інакше — детерміновано відмінна (два однакові контури
    зливаються в один товстий)."""
    if inner in _SHAPES and inner != shape:
        return inner
    if shape in _SHAPE_ORDER:
        return _SHAPE_ORDER[(_SHAPE_ORDER.index(shape) + 2) % len(_SHAPE_ORDER)]
    return "circle"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def initials(name: str) -> str:
    """Ініціали для знака — строгою латиницею (Â→A); нелатинське випадає."""
    name = site_name.latin(name or "") or (name or "")
    words = [w for w in re.split(r"[\s\-]+", name) if w and w[0].isalnum()]
    return "".join(w[0].upper() for w in words[:2] if w[0].isascii())


def _icon_el(key: str, fill: str, x: float, y: float, scale: float) -> str:
    return (f'<path transform="translate({x:g} {y:g}) scale({scale:g})" '
            f'd="{_ICON_PATHS[key]}" fill="{fill}"/>')


# ------------------------------------------------- зовнішній пул знаків
# logo_icons.json: 790+ stroke-іконок Lucide (ISC) — «сирі лого» для
# розширених варіантів. Вбудовані 14 тематичних лишаються стабільним ядром.
_DB_FILE = Path(__file__).resolve().parent / "logo_icons.json"
_db_cache: dict | None = None


def icon_db() -> list[dict]:
    global _db_cache
    if _db_cache is None:
        try:
            _db_cache = json.loads(_DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            _db_cache = {"icons": []}
    return _db_cache.get("icons", [])


def _stroke_icon_el(body: str, stroke: str, x: float, y: float,
                    scale: float, width: float = 2.0) -> str:
    return (f'<g transform="translate({x:g} {y:g}) scale({scale:g})" '
            f'fill="none" stroke="{stroke}" stroke-width="{width:g}" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</g>')


def build(letter: str, *, shape: str = "squircle", layout: str = "mono",
          palette: int = 0, base: str = DEFAULT_BG, icon: str = "star",
          icon_body: str = "", font: int = 0, inner: str = "") -> str:
    """Збирає svg-знак 64x64. Кольори валідуються — сміття в атрибут не їде.
    icon_body — markup stroke-іконки з пулу logo_icons.json (має пріоритет
    над вбудованою icon у лейаутах icon / icon-letter). font — індекс у
    _FONTS; inner — внутрішня форма лейаута nested (дефолт — наступна
    відмінна від shape)."""
    if not HEX_RX.match(base or ""):
        base = DEFAULT_BG
    pname, pfn = _palettes()[palette % len(_palettes())]
    fill, s1, s2, fg = pfn(base)
    defs = ""
    if fill is None:
        defs = (f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
                f'<stop offset="0" stop-color="{s1}"/>'
                f'<stop offset="1" stop-color="{s2}"/></linearGradient></defs>\n  ')
        fill = "url(#g)"
    bg_el = _SHAPES.get(shape, _SHAPES["squircle"]).format(f=fill)
    txt = _esc((letter or "•")[:2])
    body = ""
    tight = shape in ("diamond", "hex", "shield")   # форми з вужчим центром
    if layout == "duo" and len(txt) > 1:
        fs = 24 if tight else 27
        body = (f'<text x="32" y="{41 if tight else 42}" {_font_attrs(font)} '
                f'font-size="{fs}" letter-spacing="1" '
                f'text-anchor="middle" fill="{fg}">{txt}</text>')
    elif layout == "ring":
        r = 20 if tight else 23
        body = (f'<circle cx="32" cy="32" r="{r}" fill="none" stroke="{fg}" '
                f'stroke-width="2.5" opacity="0.9"/>\n  '
                f'<text x="32" y="{32 + (r * 0.42):g}" {_font_attrs(font)} '
                f'font-size="{round(r * 1.1)}" '
                f'text-anchor="middle" fill="{fg}">{txt[:1]}</text>')
    elif layout == "icon-letter":
        if icon_body:
            ic = _stroke_icon_el(icon_body, fg, 23.5, 8 if tight else 6,
                                 0.72, width=2.6)
        else:
            ic = _icon_el(icon, fg, 23.5, 8 if tight else 6, 0.72)
        body = (ic + "\n  "
                f'<text x="32" y="{48 if tight else 50}" {_font_attrs(font)} '
                f'font-size="{22 if tight else 25}" '
                f'text-anchor="middle" fill="{fg}">{txt[:1]}</text>')
    elif layout in ("icon-left", "icon-right"):
        # іконка збоку від літери (прохання 01.10: не тільки зверху)
        left = layout == "icon-left"
        ix = (10 if left else 36) + (3 if tight else 0) * (1 if left else -1)
        tx = 43 if left else 21
        if icon_body:
            ic = _stroke_icon_el(icon_body, fg, ix, 23, 0.75, width=2.6)
        else:
            ic = _icon_el(icon, fg, ix, 23, 0.75)
        body = (ic + "\n  "
                f'<text x="{tx}" y="41" {_font_attrs(font)} '
                f'font-size="{22 if tight else 25}" '
                f'text-anchor="middle" fill="{fg}">{txt[:1]}</text>')
    elif layout == "letter-icon":
        # літера зверху, іконка знизу — дзеркало icon-letter
        if icon_body:
            ic = _stroke_icon_el(icon_body, fg, 23.5, 36 if tight else 38,
                                 0.72, width=2.6)
        else:
            ic = _icon_el(icon, fg, 23.5, 36 if tight else 38, 0.72)
        body = (f'<text x="32" y="{30 if tight else 31}" '
                f'{_font_attrs(font)} '
                f'font-size="{22 if tight else 25}" '
                f'text-anchor="middle" fill="{fg}">{txt[:1]}</text>\n  ' + ic)
    elif layout == "icon-badge":
        # велика літера + іконка-бейдж у правому нижньому куті; іконка в
        # колі кольору ТЛА (на градієнті — темний стоп), інакше біле-на-білому
        br_x, br_y = (40, 40) if tight else (42, 42)
        badge_ic = fill if defs == "" else s2
        if icon_body:
            ic = _stroke_icon_el(icon_body, badge_ic,
                                 br_x + 2.5, br_y + 2.5, 0.45, width=3.2)
        else:
            ic = _icon_el(icon, badge_ic, br_x + 2.5, br_y + 2.5, 0.45)
        body = (f'<text x="{28 if tight else 29}" y="{42 if tight else 44}" '
                f'{_font_attrs(font)} '
                f'font-size="{26 if tight else 30}" '
                f'text-anchor="middle" fill="{fg}">{txt[:1]}</text>\n  '
                f'<circle cx="{br_x + 8}" cy="{br_y + 8}" r="9" fill="{fg}"/>'
                "\n  " + ic)
    elif layout == "nested":
        # основна форма -> вписаний контрастний об'єкт -> літера кольором
        # тла (прохання 01.10: трирівнева композиція)
        inner_shape = _inner_for(shape, inner)
        isc = 0.5 if tight else 0.58
        letter_fill = fill if defs == "" else s2
        body = (f'<g transform="translate(32 32) scale({isc:g}) '
                f'translate(-32 -32)">'
                f'{_SHAPES[inner_shape].format(f=fg)}</g>\n  '
                f'<text x="32" y="{38 if tight else 39}" {_font_attrs(font)} '
                f'font-size="{18 if tight else 20}" '
                f'text-anchor="middle" fill="{letter_fill}">{txt[:1]}</text>')
    elif layout == "icon":
        sc = 1.35 if tight else 1.6
        off = 32 - 12 * sc
        if icon_body:
            body = _stroke_icon_el(icon_body, fg, off, off, sc,
                                   width=2.2 / sc)
        else:
            body = _icon_el(icon, fg, off, off, sc)
    else:                                            # mono
        fs = 30 if tight else 34
        body = (f'<text x="32" y="{42 if tight else 44}" {_font_attrs(font)} '
                f'font-size="{fs}" '
                f'text-anchor="middle" fill="{fg}">{txt[:1]}</text>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
            'width="64" height="64">\n  '
            f'{defs}{bg_el}\n  {body}\n</svg>\n')


# --------------------------------------------------------------- підбір
def _axes(files: dict | None, branch: str):
    name = ""
    try:
        name = site_name.expected(branch, files)
    except Exception:
        pass
    ini = initials(name) or "W"
    return name, ini, theme_icon(files), zlib.crc32((branch or "x").encode("utf-8"))


def describe(variant_meta: dict) -> str:
    return (f'{variant_meta["shape"]} · {variant_meta["palette"]} · '
            f'{variant_meta["layout"]}'
            + (f' ({variant_meta["inner"]})'
               if variant_meta.get("inner") else "")
            + (f' · {variant_meta["icon"]}' if "icon" in variant_meta["layout"]
               or variant_meta["layout"] == "icon" else ""))


def variants(files: dict | None, branch: str, count: int = 12,
             base_color: str = DEFAULT_BG, seed: int | None = None) -> list[dict]:
    """Розгортка варіантів для UI.

    Перші STABLE_COUNT — стабільне ядро (детерміновані осі, вбудовані
    тематичні іконки): те саме за будь-якого seed. Далі — розширення з
    пулу logo_icons.json (790+ знаків): іконки тягнуться ВИПАДКОВО, але
    відтворювано від seed — Apply перерахує ту саму розгортку і закомітить
    саме показаний знак."""
    name, ini, icon, bseed = _axes(files, branch)
    pal_n = len(_palettes())
    out, seen = [], set()
    i = 0
    stable_target = min(count, STABLE_COUNT)
    while len(out) < stable_target and i < STABLE_COUNT * 6:
        shape = _SHAPE_ORDER[(bseed + i) % len(_SHAPE_ORDER)]
        layout = _LAYOUTS[(bseed // 7 + i * 3) % len(_LAYOUTS)]
        palette = (bseed // 31 + i * 5) % pal_n
        font = (bseed // 13 + i * 2) % len(_FONTS)
        inner = _inner_for(shape,
                           _SHAPE_ORDER[(bseed // 3 + i) % len(_SHAPE_ORDER)])
        if layout == "duo" and len(ini) < 2:
            layout = "mono"
        key = (shape, layout, palette, font)
        i += 1
        if key in seen:
            continue
        seen.add(key)
        svg = build(ini, shape=shape, layout=layout, palette=palette,
                    base=base_color, icon=icon, font=font, inner=inner)
        out.append({"variant": len(out), "shape": shape, "layout": layout,
                    "palette": _palettes()[palette][0], "palette_i": palette,
                    "icon": icon, "letters": ini, "name": name, "svg": svg,
                    "font": font,
                    **({"inner": inner} if layout == "nested" else {})})
    db = icon_db()
    if count > len(out) and db:
        import random
        rng = random.Random(f"{branch}:{seed if seed is not None else 0}")
        ext_layouts = ("icon", "icon-letter", "icon-left", "icon-right",
                       "letter-icon", "icon-badge", "nested")
        j = 0
        while len(out) < count and j < count * 8:
            j += 1
            row = db[rng.randrange(len(db))]
            shape = _SHAPE_ORDER[rng.randrange(len(_SHAPE_ORDER))]
            palette = rng.randrange(pal_n)
            layout = ext_layouts[rng.randrange(len(ext_layouts))]
            font = rng.randrange(len(_FONTS))
            inner = _inner_for(shape,
                               _SHAPE_ORDER[rng.randrange(len(_SHAPE_ORDER))])
            key = (("db", row["name"]) if layout != "nested" else ("nested", inner),
                   shape, layout, palette, font)
            if key in seen:
                continue
            seen.add(key)
            svg = build(ini, shape=shape, layout=layout, palette=palette,
                        base=base_color, icon=icon, icon_body=row["body"],
                        font=font, inner=inner)
            out.append({"variant": len(out), "shape": shape, "layout": layout,
                        "palette": _palettes()[palette][0], "palette_i": palette,
                        "icon": row["name"], "letters": ini, "name": name,
                        "svg": svg, "pool": True, "font": font,
                        **({"inner": inner} if layout == "nested" else {})})
    return out


def pick(files: dict | None, branch: str, base_color: str = DEFAULT_BG) -> str:
    """Знак для АВТОФІКСА: перший варіант розгортки з літерним лейаутом.

    Детерміновано за віткою — різні вітки отримують різні форми/палітри,
    повторний фікс тієї самої вітки віддає той самий svg."""
    for v in variants(files, branch, count=10, base_color=base_color):
        if v["layout"] in AUTOFIX_LAYOUTS and not is_template_mark(v["svg"]):
            return v["svg"]
    name, ini, icon, _ = _axes(files, branch)
    return build(ini, base=base_color, icon=icon)


_SVG_EL_RX = re.compile(r"<(rect|circle|ellipse|polygon|path|text|defs|image|use)\b")
_SVG_TEXT_RX = re.compile(r"<text\b[^>]*>(.*?)</text>", re.S | re.I)


def is_template_mark(svg: str) -> bool:
    """Чи це шаблонний знак «фон + одна літера» (старий build_svg і йому
    подібні): одна проста фонова фігура (rect/circle), один <text> з однією
    видимою літерою, без path/градієнтів/картинок. Такі іконки на сотнях
    віток однакові до нудьги — чек позначає їх warn, заміна: Медіа →
    Лого/Favicon."""
    if not svg or "<svg" not in svg:
        return False
    tags = [m.group(1).lower() for m in _SVG_EL_RX.finditer(svg)]
    texts = _SVG_TEXT_RX.findall(svg)
    if len(texts) != 1 or tags.count("text") != 1:
        return False
    visible = re.sub(r"\s+|&[a-z]+;|&#\d+;", "", texts[0])
    if len(visible) > 1:
        return False
    if any(t in tags for t in ("path", "defs", "image", "use", "polygon")):
        return False
    backgrounds = sum(tags.count(t) for t in ("rect", "circle", "ellipse"))
    return backgrounds <= 1
