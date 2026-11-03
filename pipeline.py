"""Одне коло конвеєра над ОДНІЄЮ віткою — спільне ядро машинних споживачів.

Кроки ті самі, які людина робить кнопками у вкладці «Перевірки»:

    sync → чеки → що спрацювало → що з цього вміємо лагодити → порахувати зміни

**Коміту тут немає, і це не забутий крок, а межа.** Споживачів двоє, і пишуть
вони по-різному: ШІ-міст комітить одразу (за `AI_BRIDGE_APPLY`), а черга
ClickUp не комітить ніколи — там рішення ухвалює людина кнопкою. Доки ці шість
кроків лежали двома копіями, кожна правка мусила знайти обидві; `2f024cc` уже
звів так само `actions_for` і `apply_to_snapshot`.

Текст відповіді теж лишається за викликачем: у мосту він адресований TSM
(«у гілці цього дефекту немає»), у черзі — людині, що дивиться в лабу. Тут
живуть тільки ФАКТИ: що спрацювало, що можна полагодити, скільки файлів
зміниться.
"""
from __future__ import annotations

import runner

# Вироки одного кола — від «нема чого робити» до «є що комітити».
NOT_READY = "not_ready"     # знімок порожній: вітка ще не доїхала
CLEAN = "clean"             # жоден з обраних чеків не спрацював
NO_FIX = "no_fix"           # дефект видно, а автофікса на нього немає
WOULD_FIX = "would_fix"     # є готові зміни; комітити чи ні — вирішує викликач


def evidence(result: dict) -> tuple[dict, dict]:
    """Що з прогнаного СПРАЦЮВАЛО: {id: скільки error}, {id: скільки warn}.

    Це і є перехід від здогадки до факту: роутер назвав кандидатів, а тут
    видно, які з них справді бачать дефект.
    """
    err, warn = {}, {}
    for c in result.get("checks") or []:
        e = sum(1 for i in c["issues"] if i["severity"] == "error")
        w = sum(1 for i in c["issues"] if i["severity"] == "warn")
        if e:
            err[c["id"]] = e
        if w:
            warn[c["id"]] = w
    return err, warn


def fixable_now(check_ids, groups) -> list[str]:
    """З тих, що спрацювали, — ті, яким дозволено лагодити: є fix-хук,
    діють у цьому проєкті і група в дозволених."""
    out = []
    for c in runner.checks_for_active_project():
        if c["id"] in check_ids and c.get("fixable") and c.get("group") in groups:
            out.append(c["id"])
    return out


def run_branch(branch: str, check_ids, *, client, groups, sync: bool = True) -> dict:
    """Прогін однієї вітки. Винятки НЕ ловить — запис про збій робить викликач,
    бо тільки він знає, куди його класти (реєстр мосту чи реєстр черги).

    Повертає:
        verdict        один з чотирьох вище
        fired          {check_id: кількість} — те, що спрацювало
        fixable        [check_id] — з них ті, що вміємо лагодити
        changes        результат `compute_fixes` (порожній, крім `would_fix`)
        files          len(changes)
        files_scanned  скільки файлів було у знімку
        stale          порожньо або пояснення, чому знімок не оновлено
    """
    out = {"branch": branch, "verdict": NOT_READY, "fired": {}, "fixable": [],
           "changes": [], "files": 0, "files_scanned": 0, "stale": ""}

    if sync:
        # Синхронізуємо ЗАВЖДИ, а не лише коли знімка немає. `is_synced()`
        # перевіряє, що знімок є і належить цій вітці, але НЕ звіряє коміт —
        # на застарілому знімку чеки не спрацюють, і відповідь «дефекту немає»
        # буде неправдивою. Ціна: один дешевий GET, бо `sync_branch` сам
        # звіряє коміт і не качає нічого, якщо той не змінився.
        try:
            runner.sync_branch(client, branch)
        except Exception as e:
            # GitLab може бути недоступний. Якщо знімок уже є — працюємо по
            # ньому, як працювали раніше, але кажемо про це вголос.
            if not runner.is_synced(branch):
                raise
            out["stale"] = f"знімок не оновлено ({str(e)[:80]}) — прогін по наявному; "

    result = runner.run_checks(branch, check_ids)
    out["files_scanned"] = int(result.get("files_scanned") or 0)

    # Порожній знімок — це «ще не готово», а НЕ «чисто». Різниця дорога:
    # `clean` виглядає як відповідь («дефектів немає») і закриває вітку до
    # наступної зміни коміту, тобто ховає реальний дефект. Знімок доїжджає не
    # миттєво — це та сама причина, чому кнопка «Автофікс» у UI працює не
    # одразу після імпорту.
    if not out["files_scanned"]:
        return out

    err, warn = evidence(result)
    out["fired"] = err or warn
    if not err and not warn:
        out["verdict"] = CLEAN
        return out

    out["fixable"] = fixable_now(set(err) | set(warn), groups)
    if not out["fixable"]:
        out["verdict"] = NO_FIX
        return out

    out["changes"] = runner.compute_fixes(branch, out["fixable"])
    if not out["changes"]:
        # Чек бачить дефект, а його fix-хук нічого не змінив — це теж «потрібна
        # людина», а не «полагодили».
        out["verdict"] = NO_FIX
        return out

    out["files"] = len(out["changes"])
    out["verdict"] = WOULD_FIX
    return out
