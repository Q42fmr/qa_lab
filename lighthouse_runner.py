"""Lighthouse CI проти локального php-деплою вітки.

run(branch, form) → піднімає деплой (як і скріншоти), ганяє lighthouse
headless-Chrome-ом по URL, зберігає повний html-звіт + короткий підсумок
(4 категорії + провалені аудити) у lighthouse/.

Потрібні: node + локально встановлений lighthouse (npm i lighthouse),
Chrome/Edge (той самий, що для скріншотів).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import deployer
import projects

# Шлях до cli лишається відносним (npm install кладе node_modules у корінь
# сервісу), але перевизначається через LIGHTHOUSE_CLI. Це потрібно в docker:
# образ несе lighthouse у /opt, бо bind-mount робочої теки в /app накрив би
# вбудований node_modules — і lighthouse зник би, хоча в контейнері він є.
CLI = Path(os.getenv("LIGHTHOUSE_CLI", "node_modules/lighthouse/cli/index.js"))
CATEGORIES = ["performance", "accessibility", "best-practices", "seo"]


def lh_root() -> Path:
    return projects.state_dir() / "lighthouse"


def _node() -> str:
    return os.getenv("NODE_BIN", "node")


def available() -> bool:
    return CLI.exists()


def _stem(branch: str, form: str) -> str:
    return f"{branch.replace('/', '__')}__{form}"


def summary_path(branch: str, form: str) -> Path:
    return lh_root() / f"{_stem(branch, form)}.summary.json"


def report_path(branch: str, form: str) -> Path:
    return lh_root() / f"{_stem(branch, form)}.report.html"


def _parse(report: dict) -> dict:
    cats = report.get("categories", {})
    scores = {}
    for c in CATEGORIES:
        s = (cats.get(c) or {}).get("score")
        scores[c.replace("-", "_")] = round(s * 100) if isinstance(s, (int, float)) else None

    audits = report.get("audits", {})
    failed = []
    for c in CATEGORIES:
        for ref in (cats.get(c) or {}).get("auditRefs", []):
            a = audits.get(ref["id"])
            if not a:
                continue
            sc = a.get("score")
            if sc is None or sc >= 0.9:           # None = інформаційний, ≥0.9 = ок
                continue
            failed.append({
                "id": ref["id"], "category": c,
                "title": a.get("title", ref["id"]),
                "score": round(sc * 100),
                "display": a.get("displayValue", ""),
            })
    # найгірші зверху, без дублів між категоріями
    seen, uniq = set(), []
    for a in sorted(failed, key=lambda x: x["score"]):
        if a["id"] in seen:
            continue
        seen.add(a["id"])
        uniq.append(a)
    return {"scores": scores, "audits": uniq[:25]}


def run(branch: str, form: str = "mobile") -> dict:
    if not available():
        raise ValueError("lighthouse не встановлено — виконай: npm install lighthouse")
    if form not in ("mobile", "desktop"):
        raise ValueError("form: mobile | desktop")

    lh_root().mkdir(parents=True, exist_ok=True)
    keep = deployer.is_running(branch)
    d = deployer.deploy(branch, wait=True)     # чекаємо nuxt-білд, потрібен URL
    base = lh_root() / _stem(branch, form)          # lighthouse додасть .report.json/.html
    env = {**os.environ, "CHROME_PATH": deployer._browser_bin()}

    # BROWSER_EXTRA_ARGS — те саме, що для решти запусків Chrome: у контейнері
    # сюди приходить --disable-dev-shm-usage (--no-sandbox тут і так уже є,
    # тому дедуп — щоб той самий прапорець не пішов двічі).
    flags = ["--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars"]
    for extra in deployer.browser_extra_args():
        if extra not in flags:
            flags.append(extra)
    chrome_flags = " ".join(flags)

    cmd = [
        _node(), str(CLI), d["url"],
        "--quiet",
        "--chrome-flags=" + chrome_flags,
        "--only-categories=" + ",".join(CATEGORIES),
        "--output=json", "--output=html",
        "--output-path=" + str(base.resolve()),
        "--max-wait-for-load=45000",
    ]
    if form == "desktop":
        cmd.append("--preset=desktop")

    try:
        time.sleep(1.0)
        proc = subprocess.run(cmd, env=env, timeout=180,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    finally:
        if not keep:
            deployer.stop(branch)

    json_out = Path(str(base) + ".report.json")
    if not json_out.exists():
        err = proc.stderr.decode("utf-8", "replace")[-600:]
        raise RuntimeError(f"lighthouse не створив звіт: {err}")

    report = json.loads(json_out.read_text(encoding="utf-8"))
    parsed = _parse(report)
    json_out.unlink(missing_ok=True)             # повний json не тримаємо, лише html + summary

    summary = {"branch": branch, "form": form,
               "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
               "url": report.get("finalDisplayedUrl") or d["url"], **parsed}
    summary_path(branch, form).write_text(
        json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    return summary


def delete(branch: str, form: str) -> list[str]:
    removed = []
    for p in (summary_path(branch, form), report_path(branch, form)):
        if p.exists():
            p.unlink()
            removed.append(p.name)
    return removed


def list_results() -> list[dict]:
    if not lh_root().exists():
        return []
    out = []
    for p in lh_root().glob("*.summary.json"):
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
            s["has_report"] = report_path(s["branch"], s["form"]).exists()
            out.append(s)
        except Exception:
            continue
    return sorted(out, key=lambda x: (x["branch"], x["form"]))
