"""Переклад і заміна чужомовних фрагментів у вайті.

Джерело фрагментів — той самий foreign_runs() з checks/page_language.py, яким
чек їх і знаходить: «чужий фрагмент» мусить означати одне й те саме в чеку і в
панелі, інакше вони розійдуться. Модуль підтягує чек тим самим importlib-
механізмом, що й runner.load_checks() (як це робить prepare_main).

Переклад — MyMemory (api.mymemory.translated.net): безкоштовно, без ключа,
~1000 слів/добу анонімно. Чернетка потрібна лише щоб не набирати руками —
остаточний текст завжди правиться людиною в панелі перед застосуванням.

Нічого не пише на диск і не комітить: scan() готує пропозиції, apply_edits()
рахує новий вміст файлів, а комітить app.py (як у решті флоу).
"""

from __future__ import annotations

import html as _html
import importlib.util
import re
import time
from pathlib import Path

import runner

CHECKS_DIR = Path(__file__).resolve().parent / "checks"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
PAGE_EXT = (".html", ".htm", ".php")
# MyMemory ріже довгі рядки; фрагменти вайтів (банер, кнопка) значно коротші
MAX_CHARS = 500


def _load_check(name: str):
    path = CHECKS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"checks.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pl():
    return _load_check("page_language")


# ---------------------------------------------------------------- переклад
def translate(text: str, target: str, source: str = "autodetect",
              http=None, sleep=None) -> tuple[str, str]:
    """(переклад, примітка). Помилка мережі не кидається вгору: панель мусить
    відкритись і без перекладача, з порожньою чернеткою і причиною."""
    if http is None:
        import requests as http
    if sleep is None:
        sleep = time.sleep
    src = (text or "").strip()
    if not src:
        return "", "порожній фрагмент"
    if len(src) > MAX_CHARS:
        return "", f"завеликий фрагмент ({len(src)} символів) — переклади вручну"
    try:
        r = http.get(MYMEMORY_URL, params={
            "q": src, "langpair": f"{source}|{target}"}, timeout=20,
            headers={"User-Agent": "qa_lab"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return "", f"MyMemory недоступний: {str(e)[:120]}"
    out = (data.get("responseData") or {}).get("translatedText") or ""
    out = _html.unescape(out).strip()
    status = data.get("responseStatus")
    if status and str(status) != "200":
        note = str((data.get("responseDetails") or "")).strip()[:120]
        return out, f"MyMemory: {note or status}"
    if not out or out.casefold() == src.casefold():
        return "", "MyMemory повернув той самий текст — переклади вручну"
    sleep(0.4)                       # анонімний ліміт: не молотимо API поспіль
    return out, ""


# ---------------------------------------------------------------- скан вітки
def scan(branch: str, translate_drafts: bool = True, http=None,
         sleep=None) -> dict:
    """Чужомовні фрагменти вітки з чернетками перекладу.

    {"branch", "items": [{path, line, lang, kind, text, draft, note}],
     "skipped": [{path, why}]}
    """
    paths = runner.snapshot_files(branch)
    if not paths:
        raise ValueError("вітка не синхронізована — спершу Sync")
    pl = _pl()

    items, skipped = [], []
    seen: set[tuple[str, str]] = set()      # (шлях, текст) — дублі в межах файлу
    for p in paths:
        if not p.lower().endswith(PAGE_EXT):
            continue
        try:
            text = runner.read_snapshot_file(branch, p).decode("utf-8", "replace")
        except OSError as e:
            skipped.append({"path": p, "why": str(e)[:120]})
            continue
        declared = pl._declared(text)
        if not declared:
            skipped.append({"path": p, "why": "немає <html lang=…> — нема на що перекладати"})
            continue
        for r in pl.foreign_runs(text, declared):
            frag = " ".join(r["text"].split())
            key = (p, frag)
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "path": p,
                "line": text.count("\n", 0, r["start"]) + 1,
                "lang": r["lang"],
                "kind": r["kind"],
                "target": declared,
                "text": frag,
                "draft": "",
                "note": "",
            })

    if translate_drafts:
        # однакові фрагменти (кнопка на 8 сторінках) перекладаємо ОДИН раз
        cache: dict[tuple[str, str], tuple[str, str]] = {}
        for it in items:
            ck = (it["text"], it["target"])
            if ck not in cache:
                cache[ck] = translate(it["text"], it["target"], http=http, sleep=sleep)
            it["draft"], it["note"] = cache[ck]

    return {"branch": branch, "items": items, "skipped": skipped}


# ---------------------------------------------------------------- заміна
def apply_edits(branch: str, edits: list[dict]) -> dict:
    """edits: [{path, text, replacement}] → {"actions": [...], "skipped": [...]}.

    Заміна текстова і точна: шукаємо фрагмент у файлі як є. Якщо не знайшли
    (файл змінився під нами) — чесно пропускаємо, а не вгадуємо місце.
    """
    by_path: dict[str, list[dict]] = {}
    for e in edits:
        repl = (e.get("replacement") or "").strip()
        if not repl or not (e.get("text") or "").strip():
            continue
        by_path.setdefault(e["path"], []).append(e)

    actions, skipped, applied = [], [], 0
    for path, group in by_path.items():
        try:
            old = runner.read_snapshot_file(branch, path).decode("utf-8", "replace")
        except OSError as ex:
            skipped.append({"path": path, "why": str(ex)[:120]})
            continue
        new = old
        for e in group:
            frag, repl = e["text"], e["replacement"].strip()
            if frag in new:
                new = new.replace(frag, repl)
                applied += 1
                continue
            # у файлі фрагмент може бути з іншими переносами/відступами, ніж
            # схлопнута цитата з scan() — шукаємо по гнучкому пробілу
            flex = re.compile(r"\s+".join(map(re.escape, frag.split())))
            m = flex.search(new)
            if m:
                new = new[:m.start()] + repl + new[m.end():]
                applied += 1
            else:
                skipped.append({"path": path, "why": f"фрагмент не знайдено: {frag[:60]}"})
        if new != old:
            actions.append({"type": "edit", "path": path, "old": old, "new": new})

    return {"actions": actions, "applied": applied, "skipped": skipped}
