"""Відновлення історії статистики з GitLab.

Потрібне після того, як журнал (`commits_log.json`) прокрутився: він тримає
лише вікно останніх комітів, тож при сотнях комітів на день старі дні
зникають із нього ФІЗИЧНО. Кожен фікс лаби — реальний коміт у GitLab, тож
історію можна відновити звідти й скласти у `stats_ledger`.

Як розпізнаються коміти лаби: **автором**. Токен лаби комітить від свого
користувача (`/user` -> name), тоді як генератор і люди мають власні імена
(`Auto-import code for…` від `Hugo Support`, `Update N files` від
`dean-support`). Меседжі для цього не годяться: половину пише користувач
руками.

Запуск (разово, для активного проєкту):
    py stats_backfill.py --since 2026-07-01
    py stats_backfill.py --since 2026-07-01 --dry
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import stats_ledger

# меседж -> дія журналу. Тільки ті, які лаба пише САМА; усе інше — людський
# текст (масові заміни, ручні правки), і вгадувати його не можна.
ACTIONS = (
    ("автовиправлення перевірок", "autofix"),
    ("Translate foreign fragments", "translate"),
    ("Fix text contrast", "visual-fix"),
)


def local_ts(iso: str) -> str:
    """`2026-07-30T12:34:35.000+00:00` (UTC) -> `2026-07-30 15:34:35` (локальний).

    Журнал пише локальний час машини, тож без конверсії коміти з'їхали б на
    зсув зони, а на межі доби потрапили б у чужий день графіка.
    """
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return d.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def action_for(title: str) -> str:
    for needle, action in ACTIONS:
        if needle.lower() in (title or "").lower():
            return action
    return "commit"


def collect(client, branches: list[str], since: str, until: str = "",
            workers: int = 8, on_progress=None) -> list[dict]:
    """Коміти лаби по вітках -> записи для реєстру.

    Вітка, що впала (404, таймаут), не валить прогін — інакше один битий
    рядок у clickup_map коштував би всього бекфілу.
    """
    author = (client.me() or {}).get("name", "")
    if not author:
        raise RuntimeError("не вдалось визначити автора токена (/user)")

    def one(branch: str) -> list[dict]:
        try:
            commits = client.commits_range(branch, since, until)
        except Exception:
            return []
        out = []
        for c in commits:
            if c.get("author") != author:
                continue
            try:
                files = client.commit_file_count(c["id"])
            except Exception:
                continue
            out.append({"ts": local_ts(c.get("date", "")), "branch": branch,
                        "action": action_for(c.get("title", "")),
                        "files": files, "commit": c["id"]})
        return out

    recs: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for i, part in enumerate(ex.map(one, branches), 1):
            recs += part
            if on_progress and i % 200 == 0:
                on_progress(i, len(branches), len(recs))
    recs.sort(key=lambda r: r["ts"])
    return recs


def branches_of(root: Path) -> list[str]:
    """Вітки проєкту, які варто перевіряти: ті, що мають прив'язку до ClickUp
    (решта — архівні чернетки, фіксів лаби там не було)."""
    f = Path(root) / "clickup_map.json"
    if not f.exists():
        return []
    try:
        return sorted(json.loads(f.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", default="2026-07-01",
                    help="дата початку вікна (YYYY-MM-DD)")
    ap.add_argument("--until", default="", help="дата кінця (порожньо = зараз)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry", action="store_true", help="лише порахувати")
    a = ap.parse_args(argv)

    import projects
    projects.init()
    if projects.is_mock():
        print("MOCK_MODE — бекфіл нічого не відновить, потрібен GitLab-токен")
        return 1
    root = projects.state_dir()
    client = projects.client()
    brs = branches_of(root)
    if not brs:
        print(f"у {root}/clickup_map.json немає віток — нічого перевіряти")
        return 1

    since = a.since if "T" in a.since else a.since + "T00:00:00Z"
    until = (a.until + "T00:00:00Z") if a.until and "T" not in a.until else a.until
    print(f"проєкт {projects.current_id()} · віток {len(brs)} · вікно {since}..{until or 'зараз'}")
    t = time.time()

    def prog(i, n, found):
        print(f"  {i}/{n} віток, знайдено {found} комітів "
              f"({time.time() - t:.0f}с)", flush=True)

    recs = collect(client, brs, since, until, a.workers, prog)
    print(f"знайдено комітів лаби: {len(recs)} за {time.time() - t:.0f}с")
    days: dict[str, int] = {}
    for r in recs:
        days[r["ts"][:10]] = days.get(r["ts"][:10], 0) + 1
    for d in sorted(days):
        print(f"  {d}  {days[d]}")
    if a.dry:
        print("--dry: у реєстр не писав")
        return 0
    added = stats_ledger.append_many(root, recs)
    print(f"додано в реєстр: {added} (решта вже була — дедуп по вітка+sha)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
