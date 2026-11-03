"""Project-wide replacements: regex, plain literal, or custom python transforms.

Two-step flow:
  1. preview(...) -> list of per-file unified diffs (nothing is written anywhere)
  2. apply(...)   -> builds GitLab commit actions from the same parameters and
                     pushes ONE commit to the branch; the local snapshot is
                     updated to match.

Custom transforms live in ./transforms/*.py and define:

    NAME        = "Human readable name"
    DESCRIPTION = "..."
    FILES       = ["*.html"]            # default file filter (optional)
    def transform(path: str, text: str) -> str:   # return new content
"""

from __future__ import annotations

import difflib
import fnmatch
import importlib.util
import re
import traceback
from pathlib import Path

from runner import snapshot_dir, snapshot_files, read_snapshot_file, is_text

TRANSFORMS_DIR = Path("transforms")


# --------------------------------------------------------------------------
# transforms discovery
# --------------------------------------------------------------------------

def load_transforms() -> list[dict]:
    out = []
    for f in sorted(TRANSFORMS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"transforms.{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            out.append({
                "id": f.stem,
                "name": getattr(mod, "NAME", f.stem),
                "description": getattr(mod, "DESCRIPTION", ""),
                "files": getattr(mod, "FILES", ["*"]),
                "module": mod,
                "error": None,
            })
        except Exception:
            out.append({"id": f.stem, "name": f.stem, "description": "FAILED TO LOAD",
                        "files": [], "module": None, "error": traceback.format_exc()})
    return out


# --------------------------------------------------------------------------
# core
# --------------------------------------------------------------------------

# Скільки файлів зі збігами показувати списком. Далі це вже не «де воно є»,
# а «воно всюди» — і на широкому шаблоні (напр. `.`) список був би всією віткою.
MAX_MATCHED = 200


def _match(path: str, patterns: list[str]) -> bool:
    name = Path(path).name
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in patterns)


# режим «футер»: <footer> і <p>-блоки в ньому (вкладених <p> у html не буває)
FOOTER_RX = re.compile(r"<footer\b[^>]*>", re.I)
_FOOTER_P_RX = re.compile(r"<p\b[^>]*>.*?</p>", re.S | re.I)
_STRIP_TAGS_RX = re.compile(r"<[^>]+>")


def _footer_append(content: str, marker: str):
    """Клонує <p> з футера зі ВСІМА стилями і ставить копію нижче.

    marker заданий і знайдений у блоці — клон = блок з заміною marker→content
    (href="mailto:стара" теж міняється — саме так додається друга пошта);
    інакше клонується лише зовнішній тег (класи цілі), вміст = content.
    Ідемпотентність: файл, що вже містить content, не чіпається."""
    def transform(path, text):
        if content in text:
            return text
        m = FOOTER_RX.search(text)
        if not m:
            return text                              # без футера — не чіпаємо
        end = text.lower().find("</footer>", m.end())
        if end < 0:
            return text
        seg = text[m.end():end]
        blocks = list(_FOOTER_P_RX.finditer(seg))
        cand = None
        if marker:
            for b in blocks:
                if marker in b.group(0):
                    cand = b
                    break
        if cand is None:
            for b in blocks:                          # останній <p> з текстом
                if _STRIP_TAGS_RX.sub("", b.group(0)).strip():
                    cand = b
        if cand is None:
            return text
        block = cand.group(0)
        if marker and marker in block:
            clone = block.replace(marker, content)
        else:
            open_tag = block[:block.find(">") + 1]
            clone = f"{open_tag}{content}</p>"
        if clone == block:
            return text
        abs_start = m.end() + cand.start()
        ls = text.rfind("\n", 0, abs_start) + 1
        indent = text[ls:abs_start]
        if indent.strip():
            indent = ""                               # блок не на своєму рядку
        nl = "\r\n" if "\r\n" in text else "\n"
        abs_end = m.end() + cand.end()
        return text[:abs_end] + nl + indent + clone + text[abs_end:]
    return transform


def _compute_changes(branch: str, params: dict, stats: dict | None = None) -> list[dict]:
    """Returns [{path, old, new}] for every file the operation would change.

    `stats` (необов'язковий) заповнюється розкладом прогону: скільки файлів у
    знімку, скільки пройшло фільтр і ДЕ САМЕ трапилось шукане.

    Навіщо. Прев'ю рахує ЗМІНИ, а вкладкою користуються ще й як пошуком:
    вписують шукане в обидва поля, щоб просто побачити, де воно є. Заміна
    тексту на себе не міняє нічого — і панель писала «збігів немає», хоча
    збіги були. Той самий текст виходив і коли вітку не синхронізовано, і
    коли фільтр не пропустив жодного файлу: три різні причини, одна відповідь,
    і жодного способу зрозуміти, що сталось (кейс 25.08, вітка nwf-*).
    """
    mode = params.get("mode", "regex")   # regex|literal|script|pairs|insert|footer
    patterns = [p.strip() for p in (params.get("file_filter") or "*").split(",") if p.strip()]

    transform = None
    # «скільки разів шукане трапляється в тексті»; None — режим без шуканого
    # (script: що саме він шукає, знає лише сам трансформ)
    counter = None
    if mode == "pairs":
        # список незалежних літеральних замін: [{"find": ..., "replace": ...}]
        pairs = [p for p in (params.get("pairs") or []) if p.get("find")]
        if not pairs:
            raise ValueError("empty pairs list")

        def transform(path, text):
            for pr in pairs:
                text = text.replace(pr["find"], pr.get("replace", ""))
            return text

        def counter(text):
            return sum(text.count(pr["find"]) for pr in pairs)
    elif mode == "footer":
        # дописати рядок у футер: клонуємо наявний <p> З УСІМА стилями і
        # ставимо нижче (кейс «додати другу пошту»). `find` — необов'язковий
        # маркер: який блок клонувати і що в клоні замінити; без нього
        # береться останній <p> з видимим текстом, а вміст заміщується.
        content = (params.get("replace") or "").strip()
        marker = (params.get("find") or "").strip()
        if not content:
            raise ValueError("порожній текст для футера")
        transform = _footer_append(content, marker)

        def counter(text):
            return len(FOOTER_RX.findall(text))

    elif mode == "insert":
        # вставка фрагмента (напр. <link rel="icon" ...>) біля якоря (напр. </head>)
        snippet = (params.get("snippet") or "").strip("\n")
        anchor = params.get("anchor") or "</head>"
        position = params.get("position", "before")        # before | after
        skip_present = params.get("skip_if_present", True)
        if not snippet.strip():
            raise ValueError("порожній фрагмент для вставки")

        def transform(path, text):
            # ідемпотентність: якщо фрагмент уже є — не дублюємо
            if skip_present and snippet.strip() in text:
                return text
            low, alow = text.lower(), anchor.lower()
            i = low.find(alow)
            if i < 0:
                return text                                # немає якоря — файл не чіпаємо
            # відступ рядка з якорем — щоб вставка стала рівно
            ls = text.rfind("\n", 0, i) + 1
            indent = ""
            for ch in text[ls:i]:
                if ch in " \t":
                    indent += ch
                else:
                    indent = ""
                    break
            nl = "\r\n" if "\r\n" in text else "\n"        # зберігаємо стиль переносів
            block = "".join(indent + ln + nl for ln in snippet.split("\n"))
            if position == "after":
                j = i + len(anchor)
                return text[:j] + nl + block.rstrip(nl) + text[j:]
            return text[:ls] + block + text[ls:]

        def counter(text):
            # шукане тут — ЯКІР: файл без нього не чіпається взагалі
            return text.lower().count(anchor.lower())

    elif mode == "script":
        wanted = params.get("script")
        for t in load_transforms():
            if t["id"] == wanted:
                if not t["module"]:
                    raise ValueError(f"transform '{wanted}' failed to load:\n{t['error']}")
                transform = t["module"].transform
                if params.get("file_filter") in (None, "", "*"):
                    patterns = t["files"]
                break
        if transform is None:
            raise ValueError(f"unknown transform: {wanted}")
    else:
        find = params.get("find", "")
        if not find:
            raise ValueError("empty search pattern")
        repl = params.get("replace", "")
        if mode == "literal":
            find = re.escape(find)
            repl = repl.replace("\\", "\\\\")
        flags = re.MULTILINE
        if params.get("ignore_case"):
            flags |= re.IGNORECASE
        rx = re.compile(find, flags)
        transform = lambda path, text: rx.sub(repl, text)
        counter = lambda text: sum(1 for _ in rx.finditer(text))

    changes = []
    all_paths = snapshot_files(branch)
    scanned = 0
    matched: list[dict] = []
    hits = 0
    for path in all_paths:
        if not _match(path, patterns) or not is_text(path):
            continue
        scanned += 1
        old = read_snapshot_file(branch, path).decode("utf-8", errors="replace")
        # рахуємо ЛИШЕ для прев'ю: apply() ходить тим самим кодом, і зайвий
        # прохід regex по кожному файлу вітки йому ні до чого
        if stats is not None and counter is not None:
            n = counter(old)
            if n:
                hits += n
                matched.append({"path": path, "count": n})
        new = transform(path, old)
        if new != old:
            changes.append({"path": path, "old": old, "new": new})
    if stats is not None:
        stats.update({
            "files_total": len(all_paths),      # усе, що є у знімку
            "files_scanned": scanned,           # з них пройшло фільтр і is_text
            "matches": None if counter is None else hits,
            "files_matched": None if counter is None else len(matched),
            # список для пошуку: обрізаємо, бо на широкому шаблоні це вся вітка
            "matched": matched[:MAX_MATCHED],
            "matched_truncated": len(matched) > MAX_MATCHED,
        })
    return changes


# Стеля прев'ю: на вітках-гігантах (fuxjvik 2418 файлів) повні дифи всіх
# файлів давали JSON на десятки МБ — проксі рвав відповідь, фронт бачив
# «Unexpected end of JSON input» і ПОРОЖНЄ поле (02.10). Дифи віддаються
# першим файлам до бюджету; решта — шляхи без тексту (apply по них працює,
# чекбокси будуються).
_DIFF_FILES_CAP = 150
_DIFF_BYTES_CAP = 1_500_000


def preview(branch: str, params: dict, context: int = 3) -> dict:
    stats: dict = {}
    changes = _compute_changes(branch, params, stats)
    diffs = []
    total_hunks = 0
    spent = 0
    truncated = 0
    for ch in changes:
        diff = list(difflib.unified_diff(
            ch["old"].splitlines(keepends=True),
            ch["new"].splitlines(keepends=True),
            fromfile=f"a/{ch['path']}", tofile=f"b/{ch['path']}", n=context,
        ))
        hunks = sum(1 for l in diff if l.startswith("@@"))
        total_hunks += hunks
        text = "".join(diff)
        if len(diffs) >= _DIFF_FILES_CAP or spent >= _DIFF_BYTES_CAP:
            truncated += 1
            diffs.append({"path": ch["path"], "hunks": hunks, "diff": ""})
            continue
        spent += len(text)
        diffs.append({"path": ch["path"], "hunks": hunks, "diff": text})
    out = {"branch": branch, "files_changed": len(diffs),
           "hunks": total_hunks, "diffs": diffs, **stats}
    if truncated:
        out["diffs_truncated"] = truncated
    return out


def apply(client, branch: str, params: dict, message: str, selected_paths: list[str] | None = None) -> dict:
    changes = _compute_changes(branch, params)
    if selected_paths is not None:
        changes = [c for c in changes if c["path"] in selected_paths]
    if not changes:
        return {"committed": False, "reason": "no changes"}

    actions = [{"action": "update", "file_path": c["path"], "content": c["new"]} for c in changes]
    result = client.commit(branch, message, actions)

    # keep the local snapshot in sync with what we just pushed
    base = snapshot_dir(branch)
    for c in changes:
        # newline="" — інакше Windows перетворює \n на \r\n, а у файлах з CRLF
        # виходить \r\r\n і весь файл починає числитись зміненим
        (base / c["path"]).write_text(c["new"], encoding="utf-8", newline="")

    return {
        "committed": True,
        "commit": result.get("id", ""),
        "files": [c["path"] for c in changes],
    }
