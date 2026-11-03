"""Активні домени віток + історія використання доменів.

Джерело — поле "Required Domains" у тасках ClickUp: домени там ідуть у тому ж
порядку, що й вітки у "Safe Page" (1-й домен ↔ 1-ша вітка). При імпорті вітки
з ClickUp їй підв'язується активний домен, а в історію пишеться запис
«домен ↔ вітка» — де і коли домен використовувався. Далі це використовують
тести (перевірки): domains.active_for(branch) / domains.history_for(domain).

Стан per-project (projects.state_file("domains.json")):
    {"active":  {"<вітка>": {"domain", "task_id", "task_name", "ts"}},
     "history": [{"domain", "branch", "task_id", "task_name",
                  "first_ts", "last_ts"}]}
"""
import json
import threading
import time

import projects

_FILE = "domains.json"
_lock = threading.Lock()


def _load(pid: str | None = None) -> dict:
    p = projects.state_file(_FILE) if pid is None else projects.state_file_for(pid, _FILE)
    d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    d.setdefault("active", {})
    d.setdefault("history", [])
    return d


def _save(d: dict, pid: str | None = None):
    p = projects.state_file(_FILE) if pid is None else projects.state_file_for(pid, _FILE)
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def bind(branch: str, domain: str, task_id: str = "", task_name: str = "",
         pid: str | None = None) -> dict:
    """Підв'язує активний домен до вітки і додає запис в історію.
    Повторний бінд тієї ж пари домен↔вітка лише оновлює last_ts і таску;
    якщо вітка отримала ІНШИЙ домен — попередній лишається в історії."""
    domain = (domain or "").strip().lower()
    if not domain:
        return {}
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with _lock:
        d = _load(pid)
        d["active"][branch] = {"domain": domain, "task_id": task_id,
                               "task_name": task_name, "ts": ts}
        for rec in d["history"]:
            if rec["domain"] == domain and rec["branch"] == branch:
                rec["last_ts"] = ts
                if task_id:
                    rec["task_id"], rec["task_name"] = task_id, task_name
                break
        else:
            d["history"].append({"domain": domain, "branch": branch,
                                 "task_id": task_id, "task_name": task_name,
                                 "first_ts": ts, "last_ts": ts})
        _save(d, pid)
        return d["active"][branch]


def active_for(branch: str) -> str | None:
    """Активний домен вітки (або None) — для тестів/перевірок."""
    rec = _load()["active"].get(branch)
    return rec["domain"] if rec else None


def bound_anywhere(branch: str) -> str | None:
    """Останній привʼязаний домен вітки в БУДЬ-ЯКОМУ проєкті, або None.

    Потрібен тріажу черги до того, як відомо, у якому репо лежить вітка
    (`projects.locate_branch` — це похід у GitLab): таска ClickUp проєкту не
    каже. Імена віток у двох репо не перетинаються, тож перший збіг і є."""
    for p in projects.list_projects():
        try:
            active = _load(p["id"])["active"]
        except Exception:
            continue
        rec = active.get(branch) or active.get(branch.lower())
        if rec and rec.get("domain"):
            return rec["domain"]
    return None


def history_for(domain: str) -> list[dict]:
    """Де використовувався домен: усі записи історії по ньому."""
    domain = (domain or "").strip().lower()
    return [r for r in _load()["history"] if r["domain"] == domain]


def branch_domains(branch: str) -> list[dict]:
    """Які домени коли-небудь підв'язувались до вітки."""
    return [r for r in _load()["history"] if r["branch"] == branch]


def full() -> dict:
    return _load()
