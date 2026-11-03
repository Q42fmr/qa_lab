"""Collects images used across a branch snapshot.

Two kinds:
  * files — image files that live in the branch (git)
  * urls  — external links (http/https/protocol-relative) found in the code

scan_text() is also reused by the media_integrity check.
"""

from __future__ import annotations

import re
from pathlib import Path

from runner import snapshot_dir, snapshot_files, read_snapshot_file, is_text

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".avif", ".bmp"}

# <img>/<source> tags — усе в їхніх src/srcset/poster є картинкою незалежно від
# розширення (CDN на кшталт Unsplash віддають картинку без .jpg у шляху).
IMGTAG_RX = re.compile(r"""<(?:img|source)\b[^>]*>""", re.I)
TAGSRC_RX = re.compile(r"""\b(?:src|data-src|data-lazy-src|poster)\s*=\s*["']([^"']+)["']""", re.I)
SRCSET_RX = re.compile(r"""\bsrcset\s*=\s*["']([^"']+)["']""", re.I)
# href/content — лише якщо розширення справді вказує на картинку, інакше
# зловимо сторінкові лінки й скрипти.
ATTR_RX = re.compile(r"""\b(?:href|content)\s*=\s*["']([^"']+)["']""", re.I)
CSSURL_RX = re.compile(r"""url\(\s*["']?([^"')]+)["']?\s*\)""", re.I)
ALT_RX = re.compile(r"""\balt\s*=\s*["']([^"']*)["']""", re.I)
# og:image/twitter:image — картинка за призначенням тегу, розширення не потрібне
META_IMG_RX = re.compile(
    r"""<meta\b[^>]*(?:property|name)\s*=\s*["'](?:og:image(?::(?:secure_url|url))?"""
    r"""|twitter:image(?::src)?)["'][^>]*>""", re.I)
CONTENT_RX = re.compile(r"""\bcontent\s*=\s*["']([^"']+)["']""", re.I)
# `url()` у CSS - це завжди ресурс фону/маски, а не сторінковий лінк, тому
# ЗОВНІШНІЙ url() рахуємо картинкою навіть без розширення: CDN на кшталт
# picsum/unsplash віддають фото шляхом без суфікса
# (`picsum.photos/1920/1080?grayscale&blur=2` - саме так лежить hero-фон у
# `wilser-chehalm-in-del-ch-de`, і скан його не бачив). Виняток - шрифти й
# медіа: вони теж приходять через url().
NON_IMAGE_EXT = {".woff", ".woff2", ".ttf", ".otf", ".eot", ".css", ".js",
                 ".mjs", ".json", ".mp4", ".webm", ".ogv", ".mp3", ".wav",
                 ".pdf", ".html", ".htm", ".php", ".xml", ".txt", ".zip"}
# url(#gradient) - посилання на svg-вузол у тому ж документі, не файл
SKIP_PREFIX = ("data:", "blob:", "about:", "javascript:", "#")
# `url(` матчиться і в JS: `new URL("https://a#б")` у мініфікованому
# polyfills-*.js (кейс `chafelzibau-br-pt`) - це тестові рядки парсера, а не
# картинки. Тому поза .css вимагаємо, щоб url() стояв у CSS-властивості.
CSS_FILE_EXT = (".css", ".scss", ".sass", ".less")
BG_URL_RX = re.compile(
    r"""(?:background(?:-image)?|mask(?:-image)?|border-image|list-style(?:-image)?"""
    r"""|cursor|content)\s*:\s*[^;"']*?url\(\s*["']?([^"')]+)""", re.I)


def _ext(target: str) -> str:
    return Path(target.split("?")[0].split("#")[0]).suffix.lower()


def is_image_target(t: str) -> bool:
    return _ext(t) in IMAGE_EXT


# ------------------------------------------------------------------ формат
# Заміна картинки має класти у файл саме той формат, що обіцяє розширення:
# вітки на .webp міняли зі стоків, які віддають .jpg, і в гіт лягав jpeg під
# іменем hero.webp. Браузер таке зжує (він сніфає), а от Lighthouse, CDN і
# збірки — ні. Перегін робить Pillow (уже в залежностях, з webp/avif).
KIND_EXT = {"jpeg": ".jpg", "png": ".png", "gif": ".gif", "webp": ".webp",
            "svg": ".svg", "ico": ".ico", "avif": ".avif", "bmp": ".bmp"}
EXT_KIND = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".gif": "gif",
            ".webp": "webp", ".svg": "svg", ".ico": "ico", ".avif": "avif",
            ".bmp": "bmp"}
_PIL_FORMAT = {"jpeg": "JPEG", "png": "PNG", "gif": "GIF", "webp": "WEBP",
               "ico": "ICO", "avif": "AVIF", "bmp": "BMP"}
_SAVE_OPTS = {"jpeg": {"quality": 88, "optimize": True, "progressive": True},
              "webp": {"quality": 85, "method": 6},
              "png": {"optimize": True},
              "avif": {"quality": 70}}
_ALPHA_OK = {"png", "webp", "gif", "ico", "avif"}


def sniff_kind(data: bytes) -> str | None:
    """Формат за сигнатурою, а не за розширенням чи Content-Type сервера.
    None — це не картинка. RIFF сам по собі не рахується: wav/avi теж RIFF."""
    if not data:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"GIF8":
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:4] == b"\x00\x00\x01\x00":
        return "ico"
    if data[:2] == b"BM":
        return "bmp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return "avif"
    head = data[:300].lstrip().lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in head:
        return "svg"
    return None


def ensure_format(data: bytes, path: str) -> tuple[bytes, str | None]:
    """Байти під розширення цілі: (bytes, нотатка про перегін | None).

    Формат уже збігається або розширення незнайоме — віддаємо ті самі байти
    (жодного перекодування, webp→webp не втрачає якість). Не картинка або
    неможливий перегін (растр ↔ .svg) — ValueError.
    """
    kind = sniff_kind(data)
    if kind is None:
        raise ValueError("це не картинка (немає сигнатури JPEG/PNG/GIF/WEBP/AVIF/BMP/ICO/SVG)")
    want = EXT_KIND.get(_ext(path))
    if want is None or want == kind:
        return data, None
    if want == "svg":
        raise ValueError(f"{kind} не можна покласти у .svg — потрібен векторний файл")
    if kind == "svg":
        raise ValueError(f"svg не можна покласти у {KIND_EXT[want]} — нема чим растеризувати")

    import io
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.load()                       # анімований gif/webp → перший кадр
        if want in _ALPHA_OK:
            im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
        else:                           # jpeg/bmp без альфи: підкладаємо біле
            if im.mode in ("RGBA", "LA", "P"):
                rgba = im.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.split()[-1])
                im = flat
            else:
                im = im.convert("RGB")
        if want == "ico":
            im.thumbnail((256, 256))
        buf = io.BytesIO()
        im.save(buf, _PIL_FORMAT[want], **_SAVE_OPTS.get(want, {}))
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"не вдалося перегнати {kind} → {want}: {e}") from e
    return buf.getvalue(), f"{kind} → {want}"


def is_external(t: str) -> bool:
    return t.startswith(("http://", "https://", "//"))


def normalize_local(t: str) -> str:
    t = t.split("?")[0].split("#")[0]
    while t.startswith("./"):
        t = t[2:]
    return t.lstrip("/")


def scan_text(path: str, text: str) -> list[dict]:
    """All image references in one file: [{target, line, external, alt}].

    `alt` береться з ТОГО САМОГО тегу, звідки взявся src: у вкладці «Медіа»
    це єдина підказка, що на картинці мало бути зображено, — інакше добирати
    заміну доводиться по голому URL. У `<source>` alt не буває, там порожньо.
    """
    refs = []
    for i, line in enumerate(text.splitlines(), 1):
        # картинки з <img>/<source> — беззастережно (навіть без розширення)
        forced = []
        for tag in IMGTAG_RX.findall(line):
            am = ALT_RX.search(tag)
            alt = (am.group(1).strip() if am else "")
            srcs = list(TAGSRC_RX.findall(tag))
            for ss in SRCSET_RX.findall(tag):
                srcs += [c.strip().split()[0] for c in ss.split(",") if c.strip()]
            forced += [(s, alt) for s in srcs]
        # og:image / twitter:image — за призначенням тегу це картинка. Форсуємо
        # лише ЗОВНІШНІ: локальний шлях без розширення інакше поїхав би у
        # `media_integrity` як «картинки немає у вітці»
        for tag in META_IMG_RX.findall(line):
            cm = CONTENT_RX.search(tag)
            if cm and is_external(cm.group(1).strip()):
                forced.append((cm.group(1), ""))
        # CSS url(): зовнішній — картинка й без розширення (CDN віддають фото
        # шляхом без суфікса); локальний лишається під правилом розширення, щоб
        # `media_integrity` не почав звітувати про «биті» нефайлові цілі.
        # У .css беремо будь-який url(), поза ним — лише у CSS-властивості
        # (інакше ловимо `new URL(...)` з мініфікованого JS).
        css_hits = (CSSURL_RX.findall(line)
                    if path.lower().endswith(CSS_FILE_EXT)
                    else BG_URL_RX.findall(line))
        for t in css_hits:
            u = t.strip()
            if not u or u.startswith(SKIP_PREFIX):
                continue
            if is_external(u) and _ext(u) not in NON_IMAGE_EXT:
                forced.append((u, ""))
        # решта кандидатів (href/content) — лише з розширенням картинки
        maybe = ATTR_RX.findall(line) + CSSURL_RX.findall(line)

        seen = set()
        for t, alt in forced:
            t = t.strip()
            if not t or t.startswith(SKIP_PREFIX) or t in seen:
                continue
            seen.add(t)
            refs.append({"target": t, "line": i, "external": is_external(t), "alt": alt})
        for t in maybe:
            t = t.strip()
            if not t or t.startswith(SKIP_PREFIX) or t in seen:
                continue
            if not is_image_target(t):
                continue
            seen.add(t)
            refs.append({"target": t, "line": i, "external": is_external(t), "alt": ""})
    return refs


def scan_branch(branch: str) -> dict:
    paths = snapshot_files(branch)
    fileset = set(paths)
    base = snapshot_dir(branch)

    images = {
        p: {"path": p, "size": (base / p).stat().st_size, "used_in": []}
        for p in paths if _ext(p) in IMAGE_EXT
    }
    basenames = {}
    for p in images:
        basenames.setdefault(Path(p).name, p)

    urls: dict[str, dict] = {}
    for p in paths:
        if not is_text(p):
            continue
        text = read_snapshot_file(branch, p).decode("utf-8", errors="replace")
        for ref in scan_text(p, text):
            where = {"path": p, "line": ref["line"], "alt": ref.get("alt", "")}
            if ref["external"]:
                u = urls.setdefault(ref["target"], {"url": ref["target"], "used_in": []})
                u["used_in"].append(where)
            else:
                tgt = normalize_local(ref["target"])
                match = tgt if tgt in fileset else basenames.get(Path(tgt).name)
                if match and match in images:
                    images[match]["used_in"].append(where)

    # alt картки — перший непорожній серед її використань: та сама картинка
    # трапляється на кількох сторінках, і десь alt буває порожній
    for item in list(images.values()) + list(urls.values()):
        item["alt"] = next((w["alt"] for w in item["used_in"] if w.get("alt")), "")

    # .svg — це зазвичай спрайти/іконки (не контентні фото), заміна їх стоком
    # ламає верстку; у вкладці Медіа їх не показуємо
    def not_svg(x):
        return _ext(x.get("path") or x.get("url") or "") != ".svg"

    return {
        "files": sorted(filter(not_svg, images.values()), key=lambda x: x["path"]),
        "urls": sorted(filter(not_svg, urls.values()), key=lambda x: x["url"]),
    }


REF_EXT = (".html", ".htm", ".php", ".vue", ".css", ".js")


import zlib as _zlib
import posixpath as _pp
_HASH_STEM_RX = re.compile(r"-[0-9a-f]{8}$")


def hashed_path(rel: str, data: bytes) -> str:
    """Нове ім'я файла при заміні вмісту: <stem>-<crc8><ext> (02.10:
    «хешування назви» — кеш пробивається навіть на CDN, бо адреса нова).
    Попередній хеш-суфікс знімається — ім'я не росте при повторних замінах:
    ph-01.jpg → ph-01-a1b2c3d4.jpg → ph-01-e5f6a7b8.jpg."""
    d, name = _pp.split(rel.strip("/"))
    stem, ext = _pp.splitext(name)
    stem = _HASH_STEM_RX.sub("", stem) or stem
    out = f"{stem}-{_zlib.crc32(data) & 0xffffffff:08x}{ext}"
    return f"{d}/{out}" if d else out


def retarget_refs(texts: dict, old_rel: str, new_rel: str,
                  paths=None) -> dict:
    """Посилання на перейменований файл → новий шлях (кнопка «Перейменувати»
    у Файлах; заміна в Медіа = нове хеш-ім'я, 02.10). Кожне посилання
    лишається в своєму вигляді:
      * від кореня вітки — `images/x.jpg`, `./images/x.jpg`, `/images/x.jpg`;
      * відносно файла, де стоїть, — `../assets/img/x.jpg` у
        leistungen/index.html, `../img/x.jpg` у assets/css/site.css (кейс
        kamsviizivkakp-ch-de 21.10: заміна в Медіа перейменувала p5–p8.jpg,
        а вкладені сторінки лишились на старих іменах — биті картинки);
      * голе ім'я, що нікуди не резолвиться, — JS-мапа `IMG={"slug":"x.jpg"}`
        з базою шляху в коді. Лише коли дано `paths` (усі файли вітки) і
        таке ім'я у вітці одне: той самий збіг за ім'ям, яким Медіа-скан
        показує «де використано».
    Посилання, що відносно свого файла веде на ІНШИЙ наявний файл, не
    чіпається. Хвіст ?v= знімається — нова адреса свіжа сама собою.
    Повертає {path: new_text} лише для змінених."""
    old_rel = old_rel.strip("/")
    new_rel = new_rel.strip("/")
    if not old_rel or old_rel == new_rel:
        return {}
    old_dir, old_name = _pp.split(old_rel)
    new_dir, new_name = _pp.split(new_rel)
    fileset = set(paths) if paths is not None else None
    by_name = fileset is not None and sum(
        1 for p in fileset if _pp.basename(p) == old_name) <= 1
    pat = re.compile(r"(^|[\"'(=,\s>])((?:[^\"'()\s<>,#?=]*/)?)" + re.escape(old_name)
                     + r"(\?v=[0-9a-f]+)?(?=$|[\"')\s>,#?])", re.M)

    def target(here: str, ref_dir: str):
        """Новий текст посилання; None — посилання не на цей файл."""
        if ":" in ref_dir or ref_dir.startswith("//"):
            return None                                  # URL, схема
        ref = ref_dir + old_name
        lead = "/" if ref.startswith("/") else "./" if ref.startswith("./") else ""
        rel = None if lead == "/" else _pp.normpath(_pp.join(here, ref))
        if rel == old_rel:
            if new_dir == old_dir:
                return ref_dir + new_name
            # перенесення в іншу теку: шлях від файла заново, «./» лишається
            # «./» (корінь: ./política-de-entrega/ → ./politica-de-entrega/)
            out = _pp.relpath(new_rel, here or ".")
            return "./" + out if lead == "./" and not out.startswith("../") else out
        if fileset is not None and rel in fileset:
            return None                                  # інший наявний файл
        if ref[len(lead):] == old_rel:
            return lead + new_rel                        # від кореня вітки
        if by_name and new_dir == old_dir and ref[len(lead):] not in fileset:
            return ref_dir + new_name                    # голе ім'я / база в коді
        return None

    out = {}
    for path, text in texts.items():
        if not path.lower().endswith(REF_EXT):
            continue
        here = _pp.dirname(path)

        def sub(m, here=here):
            new_ref = target(here, m.group(2))
            return m.group(0) if new_ref is None else m.group(1) + new_ref

        new = pat.sub(sub, text)
        if new != text:
            out[path] = new
    return out
