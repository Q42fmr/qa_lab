"""Вічна історія фікс-комітів лаби — джерело для сторінки /stats.

Чому окремо від журналу. `commits_log.json` за задумом **вікно останньої
активності**: він цілком перезаписується на кожен коміт і тому обрізається.
Статистиці ж потрібна **історія** — і коли лаба робить сотні комітів на день,
вікно з'їдає старі дні фізично (не «ховає»: записи зникають із файлу).

Тому історія лежить тут, і формат вибраний під один-єдиний профіль запису:
**один рядок на коміт, дописуванням у кінець шарда поточного місяця**.
* запис — O(1) `append`, старі шарди байт-у-байт незмінні. Це ДЕШЕВШЕ за
  теперішній журнал, який перезаписує ~240 КБ на кожен коміт;
* історія не потребує стиснення в добові суми: сторінка показує ще й
  «унікальних тасок/віток» за період, а такі числа з добових сум не
  порахуєш (вітка, зачеплена три дні, дала б 3). Тож зберігаємо рядки, але
  лише те, що статистика справді читає: `files` — число, не список шляхів;
* шардинг по місяцях тримає читання обмеженим, а минуле — незмінним.

Обсяг на реальних даних: ~400 комітів/день ≈ 45 КБ/день ≈ 1.3 МБ/місяць.
"""
from __future__ import annotations

import json
from pathlib import Path

DIRNAME = "stats"
UNKNOWN_SHARD = "unknown"          # записи з битим ts не губимо


def _dir(root: Path) -> Path:
    return Path(root) / DIRNAME


def _shard_name(ts: str) -> str:
    """`2026-07-24 09:58:01` -> `2026-07`; що не схоже на дату — в unknown."""
    ts = (ts or "").strip()
    if len(ts) >= 7 and ts[4] == "-" and ts[:4].isdigit() and ts[5:7].isdigit():
        return ts[:7]
    return UNKNOWN_SHARD


def _norm(rec: dict) -> dict:
    """Нормалізує запис: files може прийти списком шляхів (як у журналі)."""
    files = rec.get("files")
    if isinstance(files, (list, tuple, set)):
        files = len(files)
    try:
        files = int(files or 0)
    except (TypeError, ValueError):
        files = 0
    return {"ts": str(rec.get("ts") or ""),
            "branch": str(rec.get("branch") or ""),
            "action": str(rec.get("action") or "commit"),
            "files": files,
            "commit": str(rec.get("commit") or "")}


def _key(rec: dict) -> tuple:
    """Тотожність запису для дедупу.

    * вітка — частина ключа: один sha може лежати у двох вітках (спільний
      базовий коміт), і це різні записи;
    * ts у ключі БУТИ НЕ МОЖЕ, коли є sha: журнал пише локальний час лаби, а
      бекфіл бере `committed_date` (UTC) — той самий коміт із двох джерел мав
      би різний ts і продублювався б;
    * коміта немає (локальні правки без sha) — тоді розрізняє саме час.
    """
    return (rec["branch"], rec["commit"]) if rec["commit"] \
        else (rec["branch"], "", rec["ts"])


def append(root: Path, rec: dict) -> None:
    """Дописує один запис у шард його місяця. Без читання файлу."""
    rec = _norm(rec)
    d = _dir(root)
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{_shard_name(rec['ts'])}.jsonl").open("a", encoding="utf-8",
                                                      newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def append_many(root: Path, recs: list[dict]) -> int:
    """Дописує пачку, пропускаючи вже наявні записи. Повертає скільки додано.
    Ідемпотентність тут обов'язкова: сідинг і бекфіл можна запускати повторно."""
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
    """Уся історія, відсортована за часом. Битий рядок пропускається — одна
    обірвана запись не мусить робити історію нечитаною."""
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
            if isinstance(rec, dict):
                out.append(_norm(rec))
    out.sort(key=lambda e: e["ts"])
    return out


def seed_from_journal(root: Path, journal_name: str = "commits_log.json") -> int:
    """Одноразова міграція: складає в реєстр те, що ще лежить у журналі.
    Записи, яких у журналі вже немає, не чіпаються — вони і є сенс реєстру."""
    jf = Path(root) / journal_name
    if not jf.exists():
        return 0
    try:
        journal = json.loads(jf.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    if not isinstance(journal, list):
        return 0
    return append_many(root, list(reversed(journal)))      # журнал новішим уперед


def ensure_seeded(root: Path, journal_name: str = "commits_log.json") -> int:
    """Міграцію гейтить маркер, а НЕ порожність реєстру: якщо перший коміт
    після оновлення стався раніше за перше читання статистики, реєстр уже не
    порожній — і умова «пусто -> сідинг» назавжди проґавила б старий журнал."""
    mark = _dir(root) / ".seeded"
    if mark.exists():
        return 0
    n = seed_from_journal(root, journal_name)
    _dir(root).mkdir(parents=True, exist_ok=True)
    mark.write_text("", encoding="utf-8")
    return n
