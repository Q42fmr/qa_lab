"""Шаблонні плейсхолдер-посилання [... LINK]: мертві кнопки (кейс QA 27.10,
доопрацювання 27.10 — корпусний прогін 42 віток).

Скрейпер лишає на сторінці якір-заглушку з атрибутом data-tpl="[FACEBOOK
LINK]" (INSTAGRAM/TWITTER/LINE/YOUTUBE/EXTERNAL…) і мертвим href (#, #!,
порожньо, javascript:void(0)). Клік нічого не робить — QA: «кнопки не
работают». Приклади: taenof-kicoku-jp — футер <li><a data-tpl="[FACEBOOK
LINK]" href="#">…</a></li> (соц-іконка) і банер <a data-tpl="[EXTERNAL
LINK]" href="#"><picture><img alt="ご注文の流れ" …></picture></a> (alt
збігається із заголовком сторінки howtoorder/index.html).

data-tpl соц-типу ≠ соц-іконка: ortun-sqioha (корпус 27.10) — скрейпер
підписав data-tpl="[INSTAGRAM LINK]" за старим href на банерах з контентним
alt («店舗一覧», «オプション・裏地のご案内») — усередині НЕ іконка, а фото/
банер з текстом. Соцмережею вважаємо лише якір, чий ВМІСТ сам виглядає як
іконка (назва мережі в класі fa-*/bi-*/icon-*, у alt/src/aria-label, або
видимий текст == назва/порожній) — незалежно від того, що написано в
data-tpl; і навпаки (remujosra-cotfaup) — data-tpl="[EXTERNAL LINK]" з
<i class="fab fa-twitter"> теж соцмережа, бо вміст — іконка.

Інше (не соцмережа): текст-телефон → tel: (локальний 0 → код країни
вітки), текст-емейл → mailto:; текст = власний домен сайту вітки
(«www.ortun-sqioha.jp» на ortun-sqioha-*) → на головну; текст/alt
збігається з title/h1 іншої сторінки вітки → на неї; інакше — розгортає
(прибирає <a>, лишає вміст).
"""
import re
import posixpath

NAME = "Плейсхолдер-посилання [LINK]"
GROUP = "auto"
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Якір-заглушка скрейпера data-tpl=\"[... LINK]\" з мертвим href "
               "(#, #!, порожньо, javascript:void(0)) — кнопка не працює. Фікс: "
               "соцмережі (визначені за ВМІСТОМ — іконка/клас/alt/текст, а не "
               "лише за назвою в data-tpl) прибирає разом із порожнім <li>/<ul>; "
               "телефон у тексті якоря → tel:, емейл → mailto:; текст = власний "
               "домен вітки → веде на головну; інше посилання на сторінку вітки "
               "(напр. EXTERNAL LINK) веде на сторінку, чий title/h1 збігається з "
               "текстом чи alt якоря; решту розгортає (прибирає <a>, лишає вміст).")
FILES = ["*.html", "*.htm", "*.php"]

_CODE_RX = re.compile(
    r"<script\b[^>]*>.*?</script\s*>|<style\b[^>]*>.*?</style\s*>|<\?(?:php|=).*?\?>|<!--.*?-->",
    re.S | re.I)
_ANCHOR_RX = re.compile(r"<a\b[^>]*>.*?</a\s*>", re.S | re.I)
_OPEN_TAG_RX = re.compile(r"<a\b[^>]*>", re.S | re.I)
_DATA_TPL_RX = re.compile(r'data-tpl\s*=\s*"([^"]*)"|data-tpl\s*=\s*\'([^\']*)\'', re.I)
_HREF_RX = re.compile(r'\bhref\s*=\s*"([^"]*)"|\bhref\s*=\s*\'([^\']*)\'', re.I)
_ARIA_RX = re.compile(r'\baria-label\s*=\s*"([^"]*)"|\baria-label\s*=\s*\'([^\']*)\'', re.I)
_TITLE_ATTR_RX = re.compile(r'\btitle\s*=\s*"([^"]*)"|\btitle\s*=\s*\'([^\']*)\'', re.I)
_IMG_ALT_RX = re.compile(r'<img\b[^>]*\balt\s*=\s*"([^"]*)"|<img\b[^>]*\balt\s*=\s*\'([^\']*)\'', re.I)
_IMG_SRC_RX = re.compile(r'<img\b[^>]*\bsrc\s*=\s*"([^"]*)"|<img\b[^>]*\bsrc\s*=\s*\'([^\']*)\'', re.I)
_TPL_KIND_RX = re.compile(r'^\s*\[\s*(.*?)\s+LINK\s*\]\s*$', re.I)
_DEAD_HREF_RX = re.compile(r'^\s*(?:#!?|javascript:\s*(?:void\(\s*0?\s*\)\s*;?\s*)?)?\s*$', re.I)
_TAG_RX = re.compile(r"<[^>]+>")

_SOCIAL_KINDS = {"FACEBOOK", "INSTAGRAM", "TWITTER", "X", "LINKEDIN", "YOUTUBE",
                  "TIKTOK", "PINTEREST", "LINE", "WHATSAPP", "TELEGRAM"}
_SOCIAL_NAMES = ["facebook", "instagram", "twitter", "linkedin", "youtube",
                  "tiktok", "pinterest", "whatsapp", "telegram", "line"]
_ICON_CLASS_RX = re.compile(
    r"\b(?:fa|bi|icon)-(facebook|x-twitter|twitter|instagram|linkedin|youtube|"
    r"tiktok|pinterest|whatsapp|telegram|line)\b", re.I)
_ICON_MARK_RX = re.compile(r"icn_|icon|\bsns\b|social", re.I)
_HOME_WORDS = ["home", "ホーム", "トップ", "accueil", "inicio", "início",
               "startseite", "naslovna"]
_HOME_NORM = {re.sub(r"[\W_]+", "", w.lower()) for w in _HOME_WORDS}
_TITLE_RX = re.compile(r"<title\b[^>]*>(.*?)</title\s*>", re.S | re.I)
_H1_RX = re.compile(r"<h1\b[^>]*>(.*?)</h1\s*>", re.S | re.I)
_INDEX_RX = re.compile(r"^(?:.*/)?index\.(?:html?|php)$", re.I)
_PHONE_RX = re.compile(r"^\+?[\d][\d\-\s().]{5,}\d$")
_EMAIL_RX = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", re.I)
_DOMAIN_TEXT_RX = re.compile(
    r"^(?:https?://)?(?:www\.)?([a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9-]+)+)/?$", re.I)
_DIAL = {"jp": "81", "ch": "41", "it": "39", "br": "55", "hr": "385",
         "de": "49", "fr": "33", "pt": "351", "es": "34"}
_BRANCH_LOCALE_RX = re.compile(r"-([a-z]{2})-[a-z]{2}(?:-\d+)?$")


def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", "", (s or "").lower())


def _code_spans(text: str) -> list:
    return [(m.start(), m.end()) for m in _CODE_RX.finditer(text)]


def _in_spans(pos: int, spans: list) -> bool:
    return any(s <= pos < e for s, e in spans)


def _attr(rx: "re.Pattern", tag: str) -> str:
    m = rx.search(tag)
    if not m:
        return ""
    return (m.group(1) if m.group(1) is not None else m.group(2)) or ""


def _detect_social(kind: str, open_tag: str, inner: str) -> str:
    """Назва мережі, якщо ВМІСТ якоря виглядає як її іконка; інакше ''."""
    cm = _ICON_CLASS_RX.search(open_tag + " " + inner)
    if cm:
        name = cm.group(1).replace("x-twitter", "x")
        return name.upper()
    text = re.sub(r"\s+", " ", _TAG_RX.sub("", inner)).strip()
    text_norm = _norm(text)
    name_by_norm = {_norm(n): n for n in _SOCIAL_NAMES}
    name_by_norm[_norm("x")] = "x"
    if text_norm in name_by_norm:
        return name_by_norm[text_norm].upper()
    if text:
        # непорожній текст, що не є просто назвою мережі — реальний контент
        return ""
    alt = _attr(_IMG_ALT_RX, inner)
    src = _attr(_IMG_SRC_RX, inner)
    aria = _attr(_ARIA_RX, open_tag) or _attr(_ARIA_RX, inner)
    title_attr = _attr(_TITLE_ATTR_RX, open_tag) or _attr(_TITLE_ATTR_RX, inner)
    hay = " ".join([alt, src, aria, title_attr]).lower()
    if _norm(aria) == "x" or _norm(title_attr) == "x":
        return "X"
    for name in _SOCIAL_NAMES:
        if re.search(r"\b" + re.escape(name) + r"\b", hay):
            return name.upper()
    kind_u = kind.strip().upper()
    if kind_u in _SOCIAL_KINDS and not alt.strip() and _ICON_MARK_RX.search(src + " " + open_tag):
        return kind_u
    return ""


def _label(open_tag: str, inner: str) -> str:
    text = re.sub(r"\s+", " ", _TAG_RX.sub("", inner)).strip()
    if text:
        return text
    alt = _attr(_IMG_ALT_RX, inner)
    if alt.strip():
        return alt.strip()
    aria = _attr(_ARIA_RX, open_tag)
    return aria.strip()


def _branch_country(branch: str) -> str:
    m = _BRANCH_LOCALE_RX.search((branch or "").strip().lower())
    return m.group(1) if m else ""


def _phone_e164(digits_plus: str, branch: str) -> str:
    if digits_plus.startswith("+"):
        return digits_plus
    code = _DIAL.get(_branch_country(branch))
    if code and digits_plus.startswith("0"):
        return "+" + code + digits_plus[1:]
    if code:
        return "+" + code + digits_plus
    return "+" + digits_plus


def _to_tel(label: str, branch: str) -> str:
    digits_plus = re.sub(r"[^\d+]", "", label)
    return "tel:" + _phone_e164(digits_plus, branch)


_TEL_HREF_RX = re.compile(r'href\s*=\s*"tel:([^"]+)"|href\s*=\s*\'tel:([^\']+)\'', re.I)
_PHONE_CANDIDATE_RX = re.compile(r"(\+?\d[\d\-\s().]{6,}\d)")


def _find_phone_in_text(text: str) -> str:
    """Перший правдоподібний телефон на сторінці — tel:-посилання в пріоритеті."""
    for m in _TEL_HREF_RX.finditer(text):
        raw = m.group(1) or m.group(2)
        d = re.sub(r"[^\d+]", "", raw)
        if sum(c.isdigit() for c in d) >= 7:
            return d
    best = ""
    for m in _PHONE_CANDIDATE_RX.finditer(text):
        d = re.sub(r"[^\d+]", "", m.group(1))
        digit_count = sum(c.isdigit() for c in d)
        if d.startswith("+") and digit_count >= 10:
            return d
        if digit_count >= 10 and not best:
            best = d
    return best


def _has_whatsapp_signal(kind: str, open_tag: str, inner: str) -> bool:
    text = re.sub(r"\s+", " ", _TAG_RX.sub("", inner)).strip()
    aria = _attr(_ARIA_RX, open_tag) or _attr(_ARIA_RX, inner)
    alt = _attr(_IMG_ALT_RX, inner)
    hay = " ".join([text, aria, alt, kind]).lower()
    return "whatsapp" in hay


_CTA_WORDS = ["ler mais", "leia mais", "saiba mais", "ler a nota", "ver mais",
              "veja mais", "continuar lendo", "read more", "learn more", "more",
              "mehr erfahren", "weiterlesen", "en savoir plus", "lire la suite",
              "scopri di più", "leggi tutto", "詳しく", "もっと見る", "続きを読む", "lire"]
_CTA_NORM = {_norm(w) for w in _CTA_WORDS}
_EDGE_GLYPH_RX = re.compile(r"^[\s→»›>\-–—·•/]+|[\s→»›>\-–—·•/]+$")
_HEADING_RX = re.compile(r"<h[2-6]\b[^>]*>(.*?)</h[2-6]\s*>", re.S | re.I)
_CTA_WINDOW = 1500


def _is_cta(label: str) -> bool:
    t = (label or "").strip()
    if not t:
        return False
    core = _EDGE_GLYPH_RX.sub("", t).strip()
    if not core:
        return True
    return _norm(core) in _CTA_NORM


def _nearby_heading(text: str, anchor_start: int) -> str:
    window = text[max(0, anchor_start - _CTA_WINDOW):anchor_start]
    matches = list(_HEADING_RX.finditer(window))
    if not matches:
        return ""
    return re.sub(r"\s+", " ", _TAG_RX.sub("", matches[-1].group(1))).strip()


def _branch_root(branch: str) -> str:
    segs = [s for s in re.split(r"[-.]", (branch or "").lower()) if s]
    while len(segs) > 1 and len(segs[-1]) <= 2:
        segs.pop()
    return "".join(segs)


def _is_own_domain(label: str, branch: str) -> bool:
    m = _DOMAIN_TEXT_RX.match(label.strip())
    if not m:
        return False
    labels = m.group(1).lower().split(".")
    if len(labels) < 2:
        return False
    core = re.sub(r"[^a-z0-9]", "", ".".join(labels[:-1]))
    root = _branch_root(branch)
    return len(root) >= 3 and (root in core or core in root)


def _rel_href(src_path: str, dst_path: str) -> str:
    src_dir = posixpath.dirname(src_path) or "."
    rel = posixpath.relpath(dst_path, src_dir)
    return rel.replace("\\", "/")


def _rel_dir_href(src_path: str, dst_path: str) -> str:
    src_dir = posixpath.dirname(src_path) or "."
    dst_dir = posixpath.dirname(dst_path) or "."
    rel = posixpath.relpath(dst_dir, src_dir).replace("\\", "/")
    return "./" if rel == "." else rel + "/"


def _build_pages(files: dict):
    pages = []
    home_path, home_depth = None, None
    for path, text in files.items():
        tm = _TITLE_RX.search(text)
        hm = _H1_RX.search(text)
        title_n = _norm(_TAG_RX.sub("", tm.group(1))) if tm else ""
        h1_n = _norm(_TAG_RX.sub("", hm.group(1))) if hm else ""
        pages.append((path, title_n, h1_n))
        if _INDEX_RX.match(path):
            depth = path.count("/")
            if home_depth is None or depth < home_depth:
                home_path, home_depth = path, depth
    return pages, home_path


def _match_page(label: str, pages: list, home_path: str, src_path: str):
    ln = _norm(label)
    if not ln:
        return None
    if ln in _HOME_NORM and home_path:
        return "home", home_path
    best = None
    for path, title_n, h1_n in pages:
        if path == src_path:
            continue
        if title_n == ln or h1_n == ln:
            return "exact", path
        if best is None and len(ln) >= 2 and title_n and title_n.startswith(ln):
            best = ("prefix", path)
    return best


def _close_a_start(anchor_html: str) -> int:
    m = re.search(r"</a\s*>\s*$", anchor_html, re.I)
    return m.start() if m else len(anchor_html)


_BTN_CLASS_RX = re.compile(r'class\s*=\s*"[^"]*\b(?:btn|button|cta|fab|float|pill|oferta)[\w-]*', re.I)
_VICON_RX = re.compile(r"<(?:svg|i)\b", re.I)


def _is_button(open_tag: str, inner: str, label: str) -> bool:
    """Якір-кнопка: клас кнопки у відкривному тезі або векторна іконка
    (svg/i) + короткий підпис (≤ 40 знаків). Картинка-банер (<img> з alt) —
    контент, не кнопка: її лишаємо видимою (ortun-sqioha «店舗一覧»)."""
    if _BTN_CLASS_RX.search(open_tag):
        return True
    return bool(_VICON_RX.search(inner)) and len(label) <= 40


def _plan_file(path: str, text: str, pages: list, home_path: str, branch: str,
                branch_phone: str = "") -> list:
    """[{start,end,open_start,open_end,close_start,action,label,new_href}]"""
    code = _code_spans(text)
    out = []
    for m in _ANCHOR_RX.finditer(text):
        if _in_spans(m.start(), code):
            continue
        om = _OPEN_TAG_RX.match(text, m.start())
        open_tag = om.group(0)
        tpl = _attr(_DATA_TPL_RX, open_tag)
        if not tpl:
            continue
        km = _TPL_KIND_RX.match(tpl)
        if not km:
            continue
        href = _attr(_HREF_RX, open_tag)
        if not _DEAD_HREF_RX.match(href):
            continue
        close_start = m.start() + _close_a_start(m.group(0))
        inner = text[om.end():close_start]
        base = {"start": m.start(), "end": m.end(), "open_start": m.start(),
                "open_end": om.end(), "close_start": close_start}

        if _has_whatsapp_signal(km.group(1), open_tag, inner):
            phone = _find_phone_in_text(text) or branch_phone
            if phone:
                wa_href = "https://wa.me/" + _phone_e164(phone, branch).lstrip("+")
                out.append({**base, "action": "whatsapp", "label": "WhatsApp",
                            "new_href": wa_href})
            else:
                out.append({**base, "action": "remove", "label": "", "new_href": ""})
            continue

        social = _detect_social(km.group(1), open_tag, inner)
        if social:
            out.append({**base, "action": "remove", "label": "", "new_href": ""})
            continue

        label = _label(open_tag, inner)
        stripped = label.strip()
        if _PHONE_RX.match(stripped) and sum(c.isdigit() for c in stripped) >= 7:
            out.append({**base, "action": "tel", "label": label,
                        "new_href": _to_tel(stripped, branch)})
            continue
        if _EMAIL_RX.match(stripped):
            out.append({**base, "action": "mail", "label": label,
                        "new_href": "mailto:" + stripped})
            continue
        if _is_own_domain(label, branch) and home_path:
            out.append({**base, "action": "retarget", "label": label,
                        "new_href": _rel_dir_href(path, home_path)})
            continue

        if _is_cta(stripped):
            heading = _nearby_heading(text, m.start())
            match = _match_page(heading, pages, home_path, path) if heading else None
            if match:
                mkind, target = match
                new_href = _rel_dir_href(path, target) if mkind == "home" else _rel_href(path, target)
                out.append({**base, "action": "retarget", "label": heading, "new_href": new_href})
            else:
                out.append({**base, "action": "cta_remove", "label": label, "new_href": ""})
            continue

        match = _match_page(label, pages, home_path, path)
        if match:
            mkind, target = match
            new_href = _rel_dir_href(path, target) if mkind == "home" else _rel_href(path, target)
            out.append({**base, "action": "retarget", "label": label, "new_href": new_href})
        elif _is_button(open_tag, inner, stripped):
            # стилізована кнопка (клас кнопки або іконка + короткий підпис):
            # розгорнута — це голий svg на пів-екрана і підпис без кнопки
            # (tesa-nomu 27.10, float-agenda/hero-oferta) → прибираємо цілком
            out.append({**base, "action": "btn_remove", "label": label, "new_href": ""})
        else:
            out.append({**base, "action": "unwrap", "label": label, "new_href": ""})
    return out


def run_branch(files, all_paths, branch: str = ""):
    pages, home_path = _build_pages(files)
    branch_phone = ""
    for t in files.values():
        branch_phone = _find_phone_in_text(t)
        if branch_phone:
            break
    issues = []
    for path, text in files.items():
        actions = _plan_file(path, text, pages, home_path, branch, branch_phone)
        if not actions:
            continue
        n_remove = sum(1 for a in actions if a["action"] == "remove")
        n_unwrap = sum(1 for a in actions if a["action"] == "unwrap")
        n_cta_remove = sum(1 for a in actions if a["action"] == "cta_remove")
        n_btn_remove = sum(1 for a in actions if a["action"] == "btn_remove")
        n_tel = sum(1 for a in actions if a["action"] == "tel")
        n_mail = sum(1 for a in actions if a["action"] == "mail")
        n_wa = sum(1 for a in actions if a["action"] == "whatsapp")
        retargets = [a for a in actions if a["action"] == "retarget"]
        parts = []
        if n_remove:
            parts.append(f"соц-іконок-плейсхолдерів прибере: {n_remove}")
        if n_unwrap:
            parts.append(f"лінків розгорне в текст: {n_unwrap}")
        if n_cta_remove:
            parts.append(f"CTA без сторінки прибере: {n_cta_remove}")
        if n_btn_remove:
            parts.append(f"кнопок без цілі прибере: {n_btn_remove}")
        for a in retargets:
            parts.append(f"банер «{a['label']}» поведе на {a['new_href']}")
        if n_tel:
            parts.append(f"телефонів зробить tel:-лінками: {n_tel}")
        if n_mail:
            parts.append(f"email зробить mailto:-лінками: {n_mail}")
        if n_wa:
            parts.append(f"WhatsApp поведе на wa.me: {n_wa}")
        line = text.count("\n", 0, actions[0]["start"]) + 1
        issues.append({"path": path, "line": line, "severity": "error",
                        "message": "фікс: " + "; ".join(parts)})
    return issues


def _expand_whole_lines(text: str, s: int, e: int):
    ls = text.rfind("\n", 0, s) + 1
    line_start = ls if text[ls:s].strip() == "" else s
    ne = text.find("\n", e)
    line_end_candidate = ne + 1 if ne != -1 else len(text)
    line_end = line_end_candidate if text[e:line_end_candidate].strip() == "" else e
    if line_start < s and line_end > e:
        return line_start, line_end
    return s, e


def _collapse_li(text: str, s: int, e: int):
    before = text[:s]
    m1 = re.search(r"<li\b[^>]*>(\s*)\Z", before, re.I)
    if not m1:
        return s, e
    after = text[e:]
    m2 = re.match(r"\s*</li\s*>", after, re.I)
    if not m2:
        return s, e
    return m1.start(), e + m2.end()


def _remove_empty_lists(text: str) -> str:
    changed = True
    while changed:
        changed = False
        m = re.search(r"<ul\b[^>]*>\s*</ul\s*>", text, re.I)
        if m:
            s, e = _expand_whole_lines(text, m.start(), m.end())
            text = text[:s] + text[e:]
            changed = True
    return text


def fix_branch(files, all_paths, branch: str = ""):
    files = {p: t for p, t in files.items()
             if any(__import__("fnmatch").fnmatch(p.rsplit("/", 1)[-1], pat) for pat in FILES)}
    pages, home_path = _build_pages(files)
    branch_phone = ""
    for t in files.values():
        branch_phone = _find_phone_in_text(t)
        if branch_phone:
            break
    actions = []
    for path, text in files.items():
        plan = _plan_file(path, text, pages, home_path, branch, branch_phone)
        if not plan:
            continue
        spans = []
        for a in plan:
            if a["action"] == "remove":
                s, e = _collapse_li(text, a["start"], a["end"])
                s, e = _expand_whole_lines(text, s, e)
                spans.append((s, e, ""))
            elif a["action"] in ("cta_remove", "btn_remove"):
                s, e = _expand_whole_lines(text, a["start"], a["end"])
                spans.append((s, e, ""))
            elif a["action"] == "unwrap":
                inner = text[a["open_end"]:a["close_start"]]
                spans.append((a["start"], a["end"], inner))
            elif a["action"] == "whatsapp":
                open_tag = text[a["open_start"]:a["open_end"]]
                new_tag = re.sub(r'\s*data-tpl\s*=\s*(?:"[^"]*"|\'[^\']*\')', "", open_tag, flags=re.I)
                if _HREF_RX.search(new_tag):
                    new_tag = _HREF_RX.sub(f'href="{a["new_href"]}"', new_tag, count=1)
                else:
                    new_tag = new_tag[:-1].rstrip() + f' href="{a["new_href"]}">'
                if not re.search(r'\btarget\s*=', new_tag, re.I):
                    new_tag = new_tag[:-1].rstrip() + ' target="_blank">'
                if not re.search(r'\brel\s*=', new_tag, re.I):
                    new_tag = new_tag[:-1].rstrip() + ' rel="noopener">'
                spans.append((a["open_start"], a["open_end"], new_tag))
            else:  # retarget / tel / mail
                open_tag = text[a["open_start"]:a["open_end"]]
                new_tag = re.sub(r'\s*data-tpl\s*=\s*(?:"[^"]*"|\'[^\']*\')', "", open_tag, flags=re.I)
                if _HREF_RX.search(new_tag):
                    new_tag = _HREF_RX.sub(f'href="{a["new_href"]}"', new_tag, count=1)
                else:
                    new_tag = new_tag[:-1].rstrip() + f' href="{a["new_href"]}">'
                spans.append((a["open_start"], a["open_end"], new_tag))
        spans.sort(key=lambda sp: sp[0], reverse=True)
        new_text = text
        for s, e, repl in spans:
            new_text = new_text[:s] + repl + new_text[e:]
        new_text = _remove_empty_lists(new_text)
        if new_text != text:
            actions.append({"type": "edit", "path": path, "content": new_text})
    return actions
