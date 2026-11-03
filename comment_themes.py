"""Тема для фікса картинок — з коментарів ClickUp.

Заявка приходить у коментарі таски і виглядає так:

    @Nora Frontend возьмешь пожалуйста на фикс картинок
    padzarokss.pro поездка на полуостров, свадебный банкет, сезон на побережье
    quuifass.pro поездка в горы, программа для групп, Проживание на месяц
    padzarok-br-pt
    quuifa-br-pt

Три сутності — домен, тема, вітка — лежать окремими токенами у довільному
порядку: тема може стояти в рядку з доменом, а може з віткою; вітки інколи
перелічені окремо. Тому парсер не покладається на порядок рядків.

**Домен ↔ вітка** матчиться трьома способами, у порядку надійності:

1. явні пари з деплой-коментаря тієї ж таски
   (`- domain: padzarokss.pro` / `  white: padzarok-br-pt`);
2. поля таски `domains[i] ↔ branches[i]` — вони індекс-у-індекс, так само
   як їх читає `domains.py` при імпорті;
3. префікс: домен = бренд вітки плюс короткий хвіст
   (`padzarok-br-pt` → `padzarokss.pro`) — те саме правило, що в
   `checks/logo_domain._fits_domain`.

Чому потрібен гейт. У коментарях повно рядків із доменом, які темою не є:
YAML деплою (`- domain: x.pro`) і звичайна проза («этот до сих пор после
отправки формы…»). Тому тема береться ЛИШЕ якщо: коментар загалом про фікс
картинок, домен/вітка стоять НА ПОЧАТКУ рядка, а хвіст — короткий перелік
без URL і без ознак речення.
"""
import json
import re
import threading
import time

import projects

_FILE = "comment_themes.json"
_lock = threading.Lock()

DOMAIN_RX = re.compile(r"^([a-z0-9][a-z0-9-]{2,}(?:\.[a-z0-9-]+)*\.[a-z]{2,})\b", re.I)
BRANCH_RX = re.compile(r"^([a-z0-9][a-z0-9_-]{4,})\b", re.I)
YAML_RX = re.compile(r"^-?\s*(?:domain|white|project|defaults|deploys)\s*:", re.I)
PAIR_DOMAIN_RX = re.compile(r"^-?\s*domain\s*:\s*(\S+)", re.I | re.M)
PAIR_WHITE_RX = re.compile(r"^-?\s*white\s*:\s*(\S+)", re.I | re.M)
# коментар загалом про картинки: без цього будь-яка проза з доменом ставала б темою
PHOTO_RX = re.compile(r"картинк|картинок|фотк|фото|photo|image|изображени", re.I)
FIX_RX = re.compile(r"фикс|фікс|\bfix\b|замен|помін|постав", re.I)
SENTENCE_RX = re.compile(r"[.!?]\s|\bhttp|/{2,}")

MAX_THEME = 160
MAX_DOMAIN_TAIL = 5      # як у checks/logo_domain


# Кеш похідний від того самого скану ClickUp, що й `clickup_tasks.json`, тож і
# він рівня воркспейсу, а не проєкту: `refresh()` перечитує ВСІ таски токена,
# тому з-під будь-якого проєкту виходить той самий результат. Доки файл лежав у
# теці проєкту, копії розходились - заміряно 12 ключів у white-pages проти 8 у
# vue, і всі 8 спільних з різним `comment_ts`.


def _adopt():
    """Обʼєднання проєктних копій у спільну: по кожній вітці виграє свіжіший
    коментар, тож нічого не губиться. Прапорця «уже переїхали» не тримаємо -
    після переїзду копій немає, і виклик виходить на першій перевірці."""
    copies = projects.project_copies(_FILE)
    if not copies:
        return
    shared = projects.shared_file(_FILE)
    merged: dict = {}
    for p in [shared] + copies:
        try:
            d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except Exception:
            continue
        for br, rec in (d or {}).items():
            old = merged.get(br)
            if old is None or (rec.get("comment_ts") or "") >= (old.get("comment_ts") or ""):
                merged[br] = rec
    if merged:
        shared.write_text(json.dumps(merged, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    for p in copies:
        try:
            p.unlink()
        except OSError:
            pass


def _load() -> dict:
    _adopt()
    p = projects.shared_file(_FILE)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save(d: dict):
    _adopt()
    projects.shared_file(_FILE).write_text(
        json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def _label(domain: str) -> str:
    return re.sub(r"^www\.", "", (domain or "").strip().lower()).split(".")[0]


def _brand(branch: str) -> str:
    """Бренд вітки: padzarok-br-pt → padzarok (гео-хвіст відкидаємо)."""
    return re.split(r"[-_]", (branch or "").strip().lower())[0]


def domain_fits(domain: str, branch: str) -> bool:
    """Чи цей домен зроблено під цю вітку: лейбл домену починається з бренду
    вітки і дописаного не більше MAX_DOMAIN_TAIL символів."""
    lab, br = _label(domain), _brand(branch)
    if not lab or not br:
        return False
    return lab.startswith(br) and len(lab) - len(br) <= MAX_DOMAIN_TAIL


def explicit_pairs(comments) -> dict:
    """{домен: вітка} з деплой-коментаря — найнадійніше джерело зв'язки."""
    out = {}
    for c in comments or []:
        text = c.get("text") or ""
        doms = PAIR_DOMAIN_RX.findall(text)
        whites = PAIR_WHITE_RX.findall(text)
        for d, w in zip(doms, whites):
            out[d.strip().lower()] = w.strip()
    return out


def _theme_of(line: str, token_end: int) -> str:
    tail = line[token_end:].strip(" \t-–—:,;|")
    if not (2 < len(tail) <= MAX_THEME):
        return ""
    if SENTENCE_RX.search(tail) or not re.search(r"[^\W\d_]", tail, re.U):
        return ""
    return tail


def parse(text: str, branches=()) -> list[dict]:
    """[{domain, branch, theme}] з ОДНОГО коментаря. Порожній список, якщо
    коментар не про фікс картинок."""
    if not (PHOTO_RX.search(text or "") and FIX_RX.search(text or "")):
        return []
    known = {b.lower() for b in branches or ()}
    out = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("@").strip()
        if not line or YAML_RX.match(line):
            continue
        m = DOMAIN_RX.match(line)
        if m:
            out.append({"domain": m.group(1).lower(), "branch": "",
                        "theme": _theme_of(line, m.end())})
            continue
        m = BRANCH_RX.match(line)
        if m and m.group(1).lower() in known:
            out.append({"domain": "", "branch": m.group(1).lower(),
                        "theme": _theme_of(line, m.end())})
    return out


def themes_for_task(task: dict) -> dict:
    """{вітка: {theme, domain, comment_ts}} для однієї таски."""
    branches = task.get("branches") or []
    domains = [d.lower() for d in (task.get("domains") or [])]
    pairs = explicit_pairs(task.get("comments"))
    by_index = {d: b for d, b in zip(domains, branches)}

    def branch_of(domain: str) -> str:
        d = domain.lower()
        if d in pairs:
            return pairs[d]
        if d in by_index:
            return by_index[d]
        return next((b for b in branches if domain_fits(d, b)), "")

    out: dict = {}
    for c in sorted(task.get("comments") or [], key=lambda x: str(x.get("date") or "")):
        for item in parse(c.get("text") or "", branches):
            branch = item["branch"] or branch_of(item["domain"])
            if not branch or not item["theme"]:
                continue
            out[branch] = {"theme": item["theme"],
                           "domain": item["domain"] or "",
                           "comment_ts": str(c.get("date") or ""),
                           "task_id": task.get("id", ""),
                           "task_name": task.get("name", "")}
    return out


def refresh(tasks) -> dict:
    """Перечитує всі таски і зберігає {вітка: {...}}. Свіжіший коментар
    витісняє старіший."""
    found: dict = {}
    for t in tasks or []:
        for branch, rec in themes_for_task(t).items():
            old = found.get(branch)
            if not old or str(rec["comment_ts"]) >= str(old["comment_ts"]):
                found[branch] = rec
    with _lock:
        cur = _load()
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        for branch, rec in found.items():
            cur[branch] = {**rec, "ts": ts}
        _save(cur)
    return found


def theme_for(branch: str) -> dict | None:
    return _load().get(branch)


def full() -> dict:
    return _load()
