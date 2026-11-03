"""Вічна історія прогонів перевірок — джерело тренду якості для /analytics.

Навіщо окремо від `checks_state.json`. Той файл тримає лише ОСТАННІЙ прогін
кожної вітки і перезаписується: з нього видно зріз «на сьогодні», але не
видно, стало краще чи гірше. Плюс він змішаний — різні вітки скановані
різними наборами чеків у різні місяці, тож і зріз нерівний.

Реєстр натомість ДОПИСУЄТЬСЯ, шардами по місяцях (`checkruns/<місяць>.jsonl`),
рівно як `stats_ledger` для комітів. Один рядок = один прогін однієї вітки:

    {"ts": "2026-08-07 18:00:00", "branch": "x-br-pt", "files": 12,
     "ran": ["favicon", "wrong_literal"],      # які чеки ганяли
     "err": {"wrong_literal": 3},              # лише ненульові
     "warn": {"favicon": 1}}

`ran` — обов'язковий і найважливіший: без нього «чек не спрацював» не
відрізнити від «чек не ганяли», а саме на цьому тримається відповідь
«чи тримається фікс».
"""
from __future__ import annotations

import json
from pathlib import Path

DIRNAME = "checkruns"
UNKNOWN_SHARD = "unknown"          # записи з битим ts не губимо
SEED_MARK = ".seeded"


def _dir(root: Path) -> Path:
    return Path(root) / DIRNAME


def _shard_name(ts: str) -> str:
    """`2026-07-24 09:58:01` -> `2026-07`; що не схоже на дату — в unknown."""
    ts = (ts or "").strip()
    if len(ts) >= 7 and ts[4] == "-" and ts[:4].isdigit() and ts[5:7].isdigit():
        return ts[:7]
    return UNKNOWN_SHARD


def _counts(d) -> dict:
    """Лишає тільки ненульові цілі: реєстр і так найбільший файл стану."""
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        try:
            v = int(v)
        except (TypeError, ValueError):
            continue
        if v:
            out[str(k)] = v
    return out


def _norm(rec: dict) -> dict:
    ran = rec.get("ran") or []
    if isinstance(ran, (set, tuple)):
        ran = list(ran)
    try:
        files = int(rec.get("files") or 0)
    except (TypeError, ValueError):
        files = 0
    return {"ts": str(rec.get("ts") or ""),
            "branch": str(rec.get("branch") or ""),
            "files": files,
            "ran": sorted(str(x) for x in ran),
            "err": _counts(rec.get("err")),
            "warn": _counts(rec.get("warn"))}


def _key(rec: dict) -> tuple:
    """Тотожність запису. Набір чеків у ключі, бо в одну секунду можна
    прогнати два різні набори по тій самій вітці — це різні прогони."""
    return (rec["branch"], rec["ts"], tuple(rec["ran"]))


def append(root: Path, rec: dict) -> None:
    rec = _norm(rec)
    d = _dir(root)
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{_shard_name(rec['ts'])}.jsonl").open("a", encoding="utf-8",
                                                      newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def append_many(root: Path, recs: list[dict]) -> int:
    """Дописує пачку без дублів. Ідемпотентність обов'язкова: сідинг
    запускається повторно при кожному старті сервера."""
    have = {_key(e) for e in entries(root)}
    added = 0
    for r in recs:
        r = _norm(r)
        k = _key(r)
        if k in have:
            continue
        append(root, r)
        have.add(k)
        added += 1
    return added


def entries(root: Path) -> list[dict]:
    """Уся історія за часом. Битий рядок пропускається — обірваний запис
    не мусить робити історію нечитаною."""
    d = _dir(root)
    if not d.exists():
        return []
    out = []
    for shard in sorted(d.glob("*.jsonl")):
        try:
            text = shard.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and rec.get("branch"):
                out.append(_norm(rec))
    out.sort(key=lambda e: e["ts"])
    return out


def record_run(root: Path, results: list[dict]) -> int:
    """Пише прогін, як його віддає /api/checks/run. Вітки з error-полем
    (недоступна/перейменована) пропускаємо — це не результат перевірки."""
    recs = []
    for r in results:
        if not isinstance(r, dict) or r.get("error") or not r.get("branch"):
            continue
        err, warn, ran = {}, {}, []
        for c in r.get("checks") or []:
            cid = str(c.get("id") or "")
            if not cid:
                continue
            ran.append(cid)
            e = sum(1 for i in (c.get("issues") or [])
                    if (i.get("severity") or "error") == "error")
            w = sum(1 for i in (c.get("issues") or [])
                    if (i.get("severity") or "") == "warn")
            if e:
                err[cid] = e
            if w:
                warn[cid] = w
        if not ran:
            continue
        recs.append({"ts": r.get("ts") or "", "branch": r["branch"],
                     "files": r.get("files_scanned") or 0,
                     "ran": ran, "err": err, "warn": warn})
    return append_many(root, recs)


def seed_from_state(root: Path, state_name: str = "checks_state.json") -> int:
    """Одноразова міграція: у `checks_state.json` лежить останній прогін
    кожної вітки — це вже 7000+ точок історії, і викидати їх шкода."""
    p = Path(root) / state_name
    if not p.exists():
        return 0
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if not isinstance(state, dict):
        return 0
    return record_run(root, [{**v, "branch": v.get("branch") or k}
                             for k, v in state.items() if isinstance(v, dict)])


def ensure_seeded(root: Path, state_name: str = "checks_state.json") -> int:
    """Гейт — маркер на диску, а не порожність реєстру: інакше після
    видалення старих шардів міграція заллє все вдруге."""
    mark = _dir(root) / SEED_MARK
    if mark.exists():
        return 0
    n = seed_from_state(root, state_name)
    _dir(root).mkdir(parents=True, exist_ok=True)
    mark.write_text("seeded\n", encoding="utf-8")
    return n
