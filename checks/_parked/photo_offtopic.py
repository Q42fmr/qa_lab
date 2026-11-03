"""Фото не по темі сайту — vision-вердикт Claude, фікс — стокове фото за темою.

ПРИПАРКОВАНО 22.10 (рішення власника: поки не додавати, лишити на потім).
Лаба цей файл НЕ вантажить: runner бере лише `checks/*.py`, без підтек, а CI
ганяє лише `tests/test_*.py`. Тест лежить поруч і запускається звідси ж:
`python checks/_parked/test_photo_offtopic.py`.

Як повернути: перенести цей файл у `checks/`, тест — у `tests/` (там імпорт
`from _harness import … load_check` і `mod = load_check("photo_offtopic")`),
а `SKILL_CARD` нижче — у `ai_skills.SKILLS["photo_offtopic"]`; рядок у
README «Вбудовані перевірки». Працює лише з `ANTHROPIC_API_KEY`.

Клас QA «Картинки не по теме сайта: сайт про «X», а на фото другое» — 16
пунктів на 6 вітках 21.10. Половина з них — хибні (галузеві ілюстрації на
тематичних підсторінках, лого клієнтів, обкладинки постів), тож чек живе
у групі tests (детект + фікс на вимогу, не в черзі), доки не набере статистики.

Детект: до MAX_IMAGES найбільших <img> з видимих сторінок (без лого/іконок/
svg/дрібних), зменшених до 384 px, одним викликом Claude з темою сайту
(title/description/h1 головної, photo_theme) і tool_use-відповіддю
{items:[{i, on_topic, shows}]}. Вердикти кешуються у стані
(photo_offtopic_cache.json, ключ — хеш байтів + тема), тож повторний прогін
безкоштовний. Без ANTHROPIC_API_KEY чек мовчить.

Фікс: для кожного off-topic src — стокове фото за темою (photos.search:
magnific/pexels/pixabay), src міняється на URL стоку (так само хотлінкують
img.magnific.com на вайтах), srcset/sizes знімаються. Різним картинкам —
різні результати пошуку.
"""
import base64
import hashlib
import io
import json
import re

NAME = "Фото не по темі сайту (vision)"
GROUP = "tests"
# branch-code: міняє фото — захищений «media» вимикає (як hero_photo_text)
MODIFIES = {"media"}
PROJECTS = ["php"]
DESCRIPTION = ("Vision-вердикт моделі по найбільших картинках видимих сторінок: чи "
               "пасують вони темі сайту (title/description/h1). Off-topic → warn; "
               "фікс підставляє стокове фото за темою (src на URL стоку, srcset "
               "знімається). Кешується; без ANTHROPIC_API_KEY мовчить.")
FILES = ["*.html", "*.htm", "*.php"]

# картка ШІ-роутера (ai_skills.SKILLS) — повертається разом з чеком
SKILL_CARD = {
    "симптом": "картинки на сторінках не по темі сайту: сайт про X, а на "
               "фото інше (зброя, пляж, медицина на бухгалтерському сайті), "
               "біла заглушка замість фото",
    "слова": ["не по теме", "не по темі", "картинк", "фото", "изображен",
              "зображенн", "главная картинка", "головна картинка", "hero",
              "первый экран", "заглушк", "blank"],
    "не про це": ["не загружа", "не вантаж", "битые", "биті", "403", "404",
                  "логотип", "favicon"],
    "лагодить": "tests-група (на вимогу): vision-вердикт моделі по найбільших "
                "картинках, off-topic → src на стокове фото за темою сайту "
                "(magnific/pexels/pixabay), srcset знімається",
}

MAX_IMAGES = 12
THUMB = 384
MIN_BYTES = 12_000                      # іконки/логотипи/плейсхолдери — повз
IMG_RX = re.compile(r"<img\b[^>]*>", re.I)
SRC_RX = re.compile(r"""\bsrc\s*=\s*["']([^"']+)["']""", re.I)
ALT_RX = re.compile(r"""\balt\s*=\s*["']([^"']*)["']""", re.I)
SKIP_RX = re.compile(r"logo|icon|favicon|sprite|avatar|badge|flag|arrow|\.svg(?:\?|$)|data:", re.I)
TITLE_RX = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
DESC_RX = re.compile(r"""<meta\s+name=["']description["']\s+content=["']([^"']+)["']""", re.I)
H1_RX = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
TAGS_RX = re.compile(r"<[^>]+>")
CACHE_FILE = "photo_offtopic_cache.json"
TOOL = {"name": "photo_verdicts", "description": "Verdict for every image: does it fit the site's business theme?",
        "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
            "i": {"type": "integer"}, "on_topic": {"type": "boolean"}, "shows": {"type": "string", "description": "3-6 words: what the image shows"}},
            "required": ["i", "on_topic", "shows"]}}}, "required": ["items"]}}


def _is_page(p: str) -> bool:
    return p.lower().endswith((".html", ".htm", ".php")) and not p.startswith("_meta/")


def _theme(files: dict) -> str:
    home = files.get("index.php") or files.get("index.html") or ""
    bits = []
    for rx in (TITLE_RX, DESC_RX, H1_RX):
        m = rx.search(home)
        if m:
            bits.append(TAGS_RX.sub(" ", m.group(1)).strip())
    return " · ".join(b for b in bits if b)[:400]


def _resolve(page: str, src: str) -> str:
    src = src.split("?")[0].split("#")[0]
    if src.startswith(("http://", "https://", "//")):
        return ""
    if src.startswith("/"):
        return src.lstrip("/")
    base = page.rsplit("/", 1)[0] + "/" if "/" in page else ""
    parts = (base + src).split("/")
    out: list = []
    for seg in parts:
        if seg == "..":
            if out:
                out.pop()
        elif seg not in ("", "."):
            out.append(seg)
    return "/".join(out)


def _candidates(files: dict, all_paths, read_bytes) -> list:
    """[{rel, pages:set, data}] унікальних локальних картинок, найбільші першими."""
    seen: dict = {}
    fileset = set(all_paths or [])
    for p in sorted(files):
        if not _is_page(p):
            continue
        for tag in IMG_RX.findall(files[p]):
            m = SRC_RX.search(tag)
            if not m or SKIP_RX.search(tag):
                continue
            rel = _resolve(p, m.group(1))
            if not rel or rel not in fileset or SKIP_RX.search(rel):
                continue
            rec = seen.setdefault(rel, {"rel": rel, "pages": set(), "alt": ""})
            rec["pages"].add(p)
            am = ALT_RX.search(tag)
            if am and not rec["alt"]:
                rec["alt"] = am.group(1)[:80]
    out = []
    for rec in seen.values():
        try:
            data = read_bytes(rec["rel"])
        except Exception:
            continue
        if not data or len(data) < MIN_BYTES:
            continue
        rec["data"] = data
        out.append(rec)
    out.sort(key=lambda r: -len(r["data"]))
    return out[:MAX_IMAGES]


def _thumb(data: bytes):
    """(media_type, b64) зменшеної копії або None (не картинка)."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.load()
        im = im.convert("RGB")
        im.thumbnail((THUMB, THUMB))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=70)
        return "image/jpeg", base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def _state_path():
    import projects
    return projects.state_file(CACHE_FILE)


def _cache_load() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cache_save(d: dict) -> None:
    try:
        _state_path().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _key(theme: str, data: bytes) -> str:
    return hashlib.sha1(theme.encode("utf-8") + b"|" + hashlib.sha1(data).digest()).hexdigest()[:20]


def verdicts(theme: str, cands: list) -> dict:
    """{rel: {"on_topic": bool, "shows": str}} — з кешу або одним викликом моделі."""
    import ai_router
    cache = _cache_load()
    out, ask = {}, []
    for rec in cands:
        k = _key(theme, rec["data"])
        if k in cache:
            out[rec["rel"]] = cache[k]
        else:
            ask.append((k, rec))
    if not ask:
        return out
    ok, _why = ai_router.available()
    if not ok:
        return out
    content = [{"type": "text", "text": (
        f"Site theme (title · description · h1): {theme}\n"
        f"For each numbered image decide if it fits this site's business theme. "
        f"On-topic: the business's products/services/premises/team, generic office or "
        f"customer scenes for that trade, industry illustrations on a sub-page about that "
        f"industry, client logos. Off-topic: unrelated trade (weapons, beach, medicine on "
        f"a tax site…), stock placeholders, blank images. Answer with the tool.")}]
    for n, (k, rec) in enumerate(ask):
        th = _thumb(rec["data"])
        if not th:
            continue
        content.append({"type": "text", "text": f"Image {n}: {rec['rel']} alt=«{rec['alt']}»"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": th[0], "data": th[1]}})
    body = {"model": ai_router.model_name(), "max_tokens": 1500, "tools": [TOOL],
            "tool_choice": {"type": "tool", "name": TOOL["name"]},
            "messages": [{"role": "user", "content": content}]}
    _meta, payload = ai_router._post(body, TOOL["name"], timeout=120)
    if not payload:
        return out
    for item in payload.get("items") or []:
        try:
            k, rec = ask[int(item["i"])]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        v = {"on_topic": bool(item.get("on_topic")), "shows": str(item.get("shows") or "")[:80]}
        cache[k] = v
        out[rec["rel"]] = v
    _cache_save(cache)
    return out


def _bytes_reader(branch: str):
    import runner
    base = runner.snapshot_dir(branch)
    return lambda rel: (base / rel).read_bytes()


def _offtopic(files: dict, all_paths, branch: str) -> list:
    if not branch:
        return []
    try:
        import ai_router
        if not ai_router.api_key():
            return []
    except Exception:
        return []
    theme = _theme(files)
    if not theme:
        return []
    cands = _candidates(files, all_paths, _bytes_reader(branch))
    if not cands:
        return []
    vs = verdicts(theme, cands)
    return [{**rec, **vs[rec["rel"]]} for rec in cands if rec["rel"] in vs and not vs[rec["rel"]]["on_topic"]]


def run_branch(files, all_paths, branch: str = ""):
    bad = _offtopic(files, all_paths, branch)
    issues = []
    for rec in bad:
        pages = sorted(rec["pages"])
        issues.append({"path": pages[0], "line": 1, "severity": "warn",
                       "message": (f"фото «{rec['rel']}» не по темі сайту (на знімку: {rec['shows']}) — "
                                   f"{len(pages)} стор.; фікс підставить стокове фото за темою")})
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    bad = _offtopic(files, all_paths, branch)
    if not bad:
        return []
    try:
        import photos
        import photo_theme
    except Exception:
        return []
    home = files.get("index.php") or files.get("index.html") or ""
    q = (photo_theme.extract(home).get("query") or "").strip() or _theme(files)[:80]
    if not q:
        return []
    try:
        results = photos.search(q, "landscape").get("results") or []
        if len(results) < len(bad):
            results += photos.search(q, "landscape", page=2).get("results") or []
    except Exception:
        return []
    if not results:
        return []
    work = dict(files)
    for n, rec in enumerate(bad):
        url = results[n % len(results)]["url"]
        pat = re.compile(r"""(<img\b[^>]*?)\bsrc\s*=\s*(["'])([^"']*?)\2""", re.I)
        for p in rec["pages"]:
            text = work[p]

            def repl(m):
                if _resolve(p, m.group(3)) != rec["rel"]:
                    return m.group(0)
                head = re.sub(r"""\s+(?:srcset|sizes|data-src|data-srcset)\s*=\s*(?:"[^"]*"|'[^']*')""", "", m.group(1))
                return f'{head}src="{url}"'
            work[p] = pat.sub(repl, text)
    return [{"type": "edit", "path": p, "content": t} for p, t in work.items() if t != files[p]]
