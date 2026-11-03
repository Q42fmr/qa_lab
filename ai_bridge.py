"""ШІ-міст: API для другого застосунку конвеєра (TSM).

З того боку ШІ бачить **живий домен** і шле прозою: «вайт має проблеми з
логотипом». Тут ця проза перетворюється на прогін конкретних тестів, автофікс
і коміт — з захистом від того, що два ШІ ганятимуть таск по колу.

--------------------------------------------------------------------------
ДЕ ШІ, А ДЕ НІ — головне рішення модуля

ШІ робить рівно ОДНЕ: проза → множина id чеків (`ai_router`). Усе інше
детерміноване:

    розв'язання вітки        реєстр віток + domains.py + Safe Page з ClickUp
    фільтр по типу проєкту   PROJECTS у самому чеку
    прогін                   runner.run_checks — наявний код
    підрахунок фіксів        runner.compute_fixes — наявний код
    РІШЕННЯ КОМІТИТИ         тільки якщо чек справді спрацював І фікс дав дифф
    текст коміта             шаблон
    захист від кола          ai_ledger

Звідси властивість, заради якої все й будується:

    найгірше, що дасть помилковий роутинг — ЗМАРНОВАНИЙ ПРОГІН ЧЕКІВ.
    Поганого коміта ШІ зробити не може: коміт народжується лише з реального
    спрацювання чека і реального діффа, а їх рахує старий код лаби.

Роутер працює **на повноту**: краще п'ять кандидатів, ніж проґавлений
потрібний. Точність дає наступний крок — кандидати РЕАЛЬНО ганяються, і далі
йдуть тільки ті, що спрацювали. Це і є «механізм виявлення, який тест
запустити»: не вгадування, а докази.

--------------------------------------------------------------------------
ЧОМУ АСИНХРОННО

Sync знімка з GitLab — десятки секунд. Тримати на цьому HTTP-з'єднання ШІ на
тому кінці не можна, тому `POST` віддає 202 одразу, а працює фоновий воркер.
Черги в лабі немає і не треба: `tg_watcher` уже живе фоновим потоком, беремо
той самий підхід — один воркер під локом.

Один воркер, а не пул, з конкретної причини: `projects._current` — глобальний
мутабельний стан процесу, і `run_checks`/`compute_fixes`/`snapshot_dir`
читають його неявно. Паралельні машинні прогони плюс людина, що перемикає
проєкт у UI, дали б мовчазно неправильний результат.
"""
from __future__ import annotations

import os
import queue
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import ai_ledger
import ai_router
import attribution
import ai_skills
import tsm_ingest
import pipeline
import verdict_map
import ai_skills_store
import checks_ledger
import clickup_client
import domains
import projects
import runner

router = APIRouter()

# --------------------------------------------------------------------------
# налаштування
# --------------------------------------------------------------------------
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def apply_enabled() -> bool:
    """Чи має міст ПРАВО комітити. Дефолт — ні.

    Перші тижні міст лише каже, що зробив би: система, яка пише в git без
    людини, має спершу заробити довіру на сухих прогонах. Вмикається
    `AI_BRIDGE_APPLY=1`, коли видно, що роутинг не блукає.
    """
    return os.getenv("AI_BRIDGE_APPLY", "0").strip() == "1"


def autofix_groups() -> set[str]:
    """З яких груп чеків мосту дозволено ЛАГОДИТИ.

    `compute_fixes` фільтрує по `fixable` і типу проєкту, але НЕ по `GROUP` —
    чек із вимкненої групи `review` застосується, якщо його id прийшов у
    check_ids. Для людини це не проблема (галки ставить вона), для машини —
    обхід конвенції «новий чек живе у review, доки не доведений».
    """
    raw = os.getenv("AI_AUTOFIX_GROUPS", "auto")
    return {g.strip() for g in raw.split(",") if g.strip()}


def budget_usd() -> float:
    """Місячна стеля витрат на Claude. 0 — без обмеження."""
    try:
        return float(os.getenv("AI_BUDGET_USD", "0") or 0)
    except ValueError:
        return 0.0


def clickup_enabled() -> bool:
    return os.getenv("AI_CLICKUP", "1").strip() == "1"


# --------------------------------------------------------------------------
# зв'язування з app.py
# --------------------------------------------------------------------------
# Міст мусить писати в журнал комітів і в журнал проблем, а обидві функції
# живуть в app.py, який імпортує сам міст. Замість кільцевого імпорту —
# явне впорскування: заразом тести підставляють сюди підробки і ганяють
# увесь конвеєр без GitLab.
_deps: dict = {"log_commit": None, "add_problems": None, "client": None}


def wire(*, log_commit, add_problems, client) -> None:
    _deps["log_commit"] = log_commit
    _deps["add_problems"] = add_problems
    _deps["client"] = client


def _state_root():
    return projects.state_dir()


# --------------------------------------------------------------------------
# 1. Ідентифікація вітки
# --------------------------------------------------------------------------
def known_branches() -> list[str]:
    """Усе, що лаба вважає своїми вітками: робочий список, закріплені і
    знімки в кеші (вкладка «Архів» — теж вітки, просто не в списку)."""
    import json
    names: set[str] = set()
    # Списки — у кожної людини свій (`branches.<uid>.json`, з 21.09.2026), і
    # «своя» вітка лаби — у будь-чиєму з них, тому читаємо всі.
    root = projects.state_dir()
    for p in [*sorted(root.glob("branches*.json")), root / "pinned.json"]:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                names |= {str(x) for x in data if isinstance(x, str)}
            except (ValueError, OSError):
                pass
    root = runner.cache_root()
    if root.exists():
        for d in root.iterdir():
            if not d.is_dir():
                continue
            meta = d / ".snapshot.json"
            if meta.exists():
                try:
                    names.add(json.loads(meta.read_text(encoding="utf-8"))["branch"])
                except (ValueError, OSError, KeyError):
                    pass
    # У MOCK-режимі робочого списку немає взагалі: вітки живуть у fixtures/,
    # і без цієї гілки міст офлайн не завести — тобто ним не можна було б
    # ані погратись, ані прогнати повний цикл без живого GitLab.
    if projects.is_mock() and _deps["client"] is not None:
        try:
            names |= {b["name"] for b in _deps["client"].branches()}
        except Exception:
            pass
    return sorted(n for n in names if n)


def _branches_of_task(task_id: str) -> list[str]:
    """Вітки з поля Safe Page таски ClickUp."""
    if not task_id:
        return []
    try:
        tasks = clickup_client.fetch_by_ids([{"id": task_id}], with_comments=False)
    except Exception:
        return []
    out = []
    for t in tasks or []:
        out += [str(b) for b in (t.get("branches") or [])]
    return out


def resolve_branch(text: str, branch: str = "", domain: str = "",
                   task_id: str = "") -> dict:
    """Драбина ідентифікації. Перша сходинка, що дала ОДНОЗНАЧНУ відповідь,
    виграла. ШІ тут не бере участі взагалі — назву вітки не можна вигадувати.

    Повертає {"branch", "how", "candidates"}; порожній branch = не вийшло.
    """
    known = known_branches()
    lower = {b.lower(): b for b in known}

    # 1. назва вітки прийшла явно
    if branch:
        exact = lower.get(branch.strip().lower())
        if exact:
            return {"branch": exact, "how": "явно вказана", "candidates": []}
        return {"branch": "", "how": "", "candidates": [],
                "error": f"вітки '{branch}' немає ні в списку, ні в кеші лаби"}

    # 2. домен → вітка (поле Required Domains з ClickUp, домени індекс-у-індекс
    #    із Safe Page — прив'язка робиться при імпорті таски)
    dom = (domain or "").strip().lower()
    if dom:
        hits = [r["branch"] for r in domains.history_for(dom)]
        hits = [h for h in dict.fromkeys(hits) if h in known]
        if len(hits) == 1:
            return {"branch": hits[0], "how": f"за доменом {dom}", "candidates": []}
        if len(hits) > 1:
            return {"branch": "", "how": "", "candidates": hits,
                    "error": f"домен {dom} використовувався на кількох вітках"}

    # 3. таска → Safe Page
    cu = [b for b in _branches_of_task(task_id) if b in known]
    if len(cu) == 1:
        return {"branch": cu[0], "how": f"за таскою {task_id}", "candidates": []}

    # 4. назва вітки прямо в тексті. Найдовший збіг — щоб `x-br` не вигравав
    #    у `x-br-pt`, коли в тексті стоїть друге.
    low_text = (text or "").lower()
    found = sorted((b for b in known if b.lower() in low_text), key=len, reverse=True)
    if found:
        return {"branch": found[0], "how": "знайдено в тексті", "candidates": found[1:]}

    if cu:
        return {"branch": "", "how": "", "candidates": cu,
                "error": f"таска {task_id} має кілька віток — незрозуміло, про яку мова"}
    return {"branch": "", "how": "", "candidates": [],
            "error": "не вдалось зрозуміти, про який вайт мова "
                     "(нема ні назви вітки, ні відомого домену, ні таски)"}


def history_for(branch: str) -> list[str]:
    """Чеки, що вже давали error на цій вітці. Не здогадка, а факт із
    реєстру прогонів — вітка з трьома фіксами `logo_domain` в анамнезі
    імовірніше прийшла з ним же вчетверте."""
    out: set[str] = set()
    try:
        for e in checks_ledger.entries(_state_root()):
            if e.get("branch") == branch:
                out |= set(e.get("err") or {})
    except Exception:
        pass
    return sorted(out)


# --------------------------------------------------------------------------
# 2. Роутинг
# --------------------------------------------------------------------------
def cards_for_project() -> list[dict]:
    """Каталог, який побачить модель: тільки доречні для типу проєкту і
    тільки з АКТИВНИМИ скілами (вимкнений скіл ховає чек від моделі)."""
    return ai_skills.catalog(runner.load_checks(), projects.ptype(),
                             ai_skills_store.all_skills())


def do_route(text: str, branch: str, use_model: bool = True,
             env: dict | None = None) -> dict:
    left = None
    if budget_usd() > 0:
        left = budget_usd() - ai_ledger.spend_usd(_state_root(), shards=1)
    return ai_router.route(text, cards_for_project(),
                           history=history_for(branch),
                           use_model=use_model, budget_left_usd=left, env=env)


def scope_checks(routing: dict) -> list[str]:
    """Остаточний набір чеків із результату роутингу.

    Коли Claude недоступний і ми на самих словах — «не наше» ПЕРЕМАГАЄ
    кандидатів. Заміряно на прогоні 20 тасок: «сайт отдаёт 502, хостинг
    лежит?» матчило `link_target` (через слово «не открыва»), і фолбек пішов
    би лагодити посилання на вайті, де проблема в хостингу. Деградований
    режим має помилятись у бік «нічого не робимо і пояснюємо чому».

    З живою моделлю такого відсіву немає: вона бачить і скаргу, і каталог
    цілком, тож змішану скаргу («ціни не ті, і ще лого чуже») розбирає сама.
    """
    routed = list(routing.get("checks") or [])
    if routed and routing.get("router") == "keywords" and routing.get("not_ours"):
        return []
    return routed


# --------------------------------------------------------------------------
# 3. Виконавець
# --------------------------------------------------------------------------
# Лок спільний з годинним автофіксом і живе в `runner`: машинних споживачів
# конвеєра двоє, а знімки й активний проєкт у них одні.
_run_lock = runner.pipeline_lock


def _evidence(result: dict) -> tuple[dict, dict]:
    """Делегат у `pipeline`. Лишився ім'ям, бо міст — не єдиний споживач цих
    двох кроків, а тести звертаються сюди напряму."""
    return pipeline.evidence(result)


def _fixable_now(check_ids) -> list[str]:
    return pipeline.fixable_now(check_ids, autofix_groups())


def _comment(rec: dict, verdict_note: str = "") -> str:
    """Текст коментаря в ClickUp. Коротко і по фактах — його читає людина
    між двома машинами."""
    head = {
        "fixed": "Лаба полагодила автоматично",
        "clean": "Лаба перевірила — у гілці цього дефекту немає",
        "no_fix": "Лаба бачить дефект, але автофікса на нього немає",
        "not_ours": "Це поза зоною лаби",
        # Два стани під вердикти TSM. «skipped» свідомо не схожий на «clean»:
        # там ми перевірили і не знайшли, а тут не перевіряли взагалі, бо
        # прогін з того боку не дійшов до кінця.
        "skipped": "Нічого не робили — прогін TSM зірвався",
        "visual": "Це бачить візуальний прогін, а не чек",
        "escalated": "⚠️ Потрібна людина",
        "dry-run": "Сухий прогін (коміти вимкнені)",
    }.get(rec["status"], rec["status"])
    lines = [f"{head} · вітка {rec['branch']}"]
    if rec.get("routed"):
        lines.append("перевірки: " + ", ".join(rec["routed"]))
    if rec.get("fired"):
        lines.append("спрацювали: " + ", ".join(
            f"{k}({v})" for k, v in sorted(rec["fired"].items())))
    if rec.get("commit"):
        lines.append(f"коміт {rec['commit'][:10]}, файлів {rec['files']}")
    if rec["round"] > 1:
        lines.append(f"це вже {rec['round']}-е коло по цій проблемі")
    # Жовте з вердикту TSM. Ми його свідомо не роутимо — це «повод взглянуть»,
    # а не дефект, — але й губити не можна: інакше знахідка, яку їхня тула
    # зробила очима, зникає між двома машинами безслідно.
    if rec.get("tsm_soft"):
        lines.append("TSM радить глянути очима:")
        lines += [f"  · {s}" for s in rec["tsm_soft"]]
    # Чого ми не зрозуміли. Без цього рядка людина читає відповідь як повну,
    # хоча частина вердикту пройшла повз нас.
    if rec.get("tsm_unknown"):
        named = ", ".join(rec.get("tsm_new") or [])
        lines.append(f"не розібрав {rec['tsm_unknown']} рядок(ів) вердикту"
                     + (f" (перевірки: {named})" if named else "")
                     + " — подивись їх очима")
    if verdict_note:
        lines.append(verdict_note)
    return "\n".join(lines)


def _tell_clickup(rec: dict, task_id: str, note: str = "",
                  tag_user_id=None, tag_username: str = ""):
    if not (clickup_enabled() and task_id):
        return
    try:
        clickup_client.complete_task(
            task_id, _comment(rec, note),
            # Чекліст `whites` — людський гейт («фронт пройшовся»), і його
            # знайдено в 1 таски з 479. Машина його не ставить: тихо
            # закривати чужий гейт гірше, ніж не закрити.
            checklist=False,
            tag_user_id=tag_user_id, tag_username=tag_username,
            actor=attribution.SERVICE_ACTOR)
    except Exception as e:
        print(f"[ai] коментар у ClickUp не пішов: {e}")


def execute(job: dict) -> dict:
    """Один запит від початку до кінця. Виняток назовні не пускає —
    будь-який збій стає записом зі статусом `error`."""
    # Актор — явно, а не з контексту: черга виконується у власному потоці
    # (`_loop`), куди контекст запиту не доїжджає, і без цього рядка коміт
    # моста лишився б без підпису.
    attribution.set_actor(attribution.SERVICE_ACTOR)
    t0 = time.time()
    branch, task_id = job["branch"], job.get("task_id", "")
    rec = {
        "ts": ai_ledger.now(),
        "request_id": job["request_id"],
        "branch": branch,
        "domain": job.get("domain", ""),
        "batch_id": job.get("batch_id", ""),
        "task_id": task_id,
        "loop_key": job["loop_key"],
        "round": job["round"],
        "routed": job["routed"],
        "router": job.get("router", ""),
        "usd": job.get("usd", 0.0),
        "text_head": job.get("text", ""), "text_hash": job.get("text_hash", ""),
        "tsm_unknown": int(job.get("tsm_unknown") or 0),
        "tsm_new": job.get("tsm_new") or [],
        "tsm_soft": job.get("tsm_soft") or [],
        "source": job.get("source", ""),
        "source_version": job.get("source_version", ""),
        "status": "error",
        "fired": {},
        "commit": "",
        "files": 0,
        "note": "",
    }
    try:
        with _run_lock:
            run = pipeline.run_branch(branch, job["routed"],
                                      client=_deps["client"],
                                      groups=autofix_groups())
            # Окремим полем, а не в `note`: далі кожна гілка ПРИСВОЮЄ свій
            # note, і попередження просто зникло б. Склеює їх `_finish`.
            if run["stale"]:
                rec["_stale"] = run["stale"]
            rec["fired"] = run["fired"]

            if run["verdict"] == pipeline.NOT_READY:
                # Порожній знімок — не «чисто». Відповісти «у гілці цього
                # дефекту немає» на нулі прочитаних файлів означало б збрехати
                # найгіршим зі способів: скаргу закрито, дефект лишився.
                rec["status"] = "error"
                rec["note"] = ("знімок вітки порожній — вона ще не доїхала; "
                               "повторіть запит")
                return _finish(rec, t0, task_id, job)

            if run["verdict"] == pipeline.CLEAN:
                rec["status"] = "clean"
                rec["note"] = ("жоден з обраних чеків не спрацював — у гілці "
                               "цього дефекту немає. Імовірно, він з'являється "
                               "на деплої (підстановка домену/ENV) або вже "
                               "полагоджений")
                return _finish(rec, t0, task_id, job)

            can_fix = run["fixable"]
            if run["verdict"] == pipeline.NO_FIX:
                rec["status"] = "no_fix"
                rec["note"] = ("дефект видно, але автофікса на нього немає "
                               "(або чек у вимкненій групі) — потрібна людина"
                               if not can_fix
                               else "чек спрацював, але автофікс нічого не змінив")
                return _finish(rec, t0, task_id, job)

            changes = run["changes"]
            rec["files"] = len(changes)
            if not apply_enabled():
                rec["status"] = "dry-run"
                rec["note"] = ("коміти вимкнені (AI_BRIDGE_APPLY=0); "
                               f"полагодив би {len(changes)} файл(ів) "
                               f"чеками: {', '.join(can_fix)}")
                return _finish(rec, t0, task_id, job)

            msg = (f"AI fix: {', '.join(can_fix)}"
                   + (f" (TSM task {task_id})" if task_id else ""))
            r = _deps["client"].commit(branch, msg, runner.actions_for(changes))
            runner.apply_to_snapshot(branch, changes)

            rec["commit"] = r.get("id", "")
            rec["status"] = "fixed"
            # Той самий журнал, що й у ручних фіксів, окремим `action`:
            # сторінка /stats будує фільтр типів динамічно, тож новий тип
            # з'явиться там сам.
            _deps["log_commit"](branch, msg, rec["commit"],
                                [c["path"] for c in changes], action="ai-autofix")
            return _finish(rec, t0, task_id, job)
    except Exception as e:
        rec["status"] = "error"
        rec["note"] = f"{type(e).__name__}: {e}"
        return _finish(rec, t0, task_id, job)


def _finish(rec: dict, t0: float, task_id: str, job: dict) -> dict:
    rec["ms"] = int((time.time() - t0) * 1000)
    # Попередження про несвіжий знімок дописуємо тут: гілки вище присвоюють
    # `note` кожна свій, і склеїти їх можна лише в одному місці — цьому.
    stale = rec.pop("_stale", "")
    if stale:
        rec["note"] = stale + (rec.get("note") or "")
    # `fired` рахуємо ТУТ, а не в момент роутингу: тільки прогін відрізняє
    # здогадку від факту. Саме ця пара і робить мапу самовиправною —
    # запис, вивчений моделлю і жодного разу не підтверджений, видно на /ai.
    fired = set((rec.get("fired") or {}).keys())
    for key, ids in (job.get("map_keys") or {}).items():
        if fired & set(ids or []):
            verdict_map.bump(key, "fired")
    saved = ai_ledger.append(_state_root(), rec)
    _tell_clickup(rec, task_id,
                  tag_user_id=job.get("tag_user_id"),
                  tag_username=job.get("tag_username", ""))
    # Те, що людині треба побачити очима, — у журнал проблем: вкладка вже є.
    if rec["status"] in ("no_fix", "error"):
        try:
            # Домен — те, чим людина шукає: скарга приїхала на живий домен,
            # а не на вітку. Без нього смуга алертів показує лише вітку, і
            # звʼязати її з листом від TSM доводиться руками.
            _deps["add_problems"]([{"branch": rec["branch"],
                                    "domain": rec.get("domain", ""),
                                    "source": "ai-bridge",
                                    "reason": rec["note"] or rec["status"],
                                    "task": task_id}])
        except Exception:
            pass
    _jobs[rec["request_id"]] = {"state": "done", "result": saved}
    _release(rec["loop_key"], rec["branch"], rec["routed"])
    return saved


# --------------------------------------------------------------------------
# 4. Воркер
# --------------------------------------------------------------------------
_queue: "queue.Queue[dict]" = queue.Queue()
_jobs: dict[str, dict] = {}
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()

# Робота «в польоті». Реєстр дізнається про коло лише коли воно ЗАКІНЧИЛОСЬ,
# а між прийняттям і завершенням минають десятки секунд (sync знімка). Буря
# ретраїв з того боку за цей час проходила б гейт цілком: у журналі порожньо,
# отже «це перше коло» — і так тричі поспіль. Знайдено на наскрізному прогоні.
# Тримати це в пам'яті достатньо: лаба за задумом один процес.
_inflight: set = set()
_inflight_lock = threading.Lock()


def _marks(loop_key: str, branch: str, routed) -> list:
    """Позначки по ТИХ САМИХ вимірах, що й лічильник кіл: точний ключ і
    пара «вітка + чек». Інша поломка того самого вайта чужу роботу не
    блокує — так само, як не додає їй кола."""
    marks = [("key", loop_key)]
    if branch:
        marks += [("check", branch, str(c)) for c in (routed or [])]
    return marks


def _claim(loop_key: str, branch: str, routed) -> bool:
    """Займає ключі кола. False — така робота вже в польоті."""
    marks = _marks(loop_key, branch, routed)
    with _inflight_lock:
        if any(m in _inflight for m in marks):
            return False
        _inflight.update(marks)
        return True


def _release(loop_key: str, branch: str, routed) -> None:
    with _inflight_lock:
        _inflight.difference_update(_marks(loop_key, branch, routed))


def inflight_count() -> int:
    with _inflight_lock:
        return len(_inflight)


def _loop():
    while True:
        job = _queue.get()
        try:
            execute(job)
        except Exception as e:                      # останній бар'єр
            print(f"[ai] воркер: {e}")
            _jobs[job.get("request_id", "?")] = {"state": "done",
                                                 "result": {"status": "error",
                                                            "note": str(e)}}
            # Інакше ключ лишився б зайнятим назавжди і вітка більше ніколи
            # не пройшла б гейт.
            _release(job.get("loop_key", ""), job.get("branch", ""),
                     job.get("routed", []))
        finally:
            _queue.task_done()


def start_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(target=_loop, name="ai-bridge", daemon=True)
        _worker.start()


class QueueFull(Exception):
    """Черга переповнена. Окремий тип, бо викликач має відповісти 429 з
    `Retry-After`, а не 500."""

    def __init__(self, depth: int, retry_after: int):
        super().__init__(f"черга моста повна: {depth}")
        self.depth = depth
        self.retry_after = retry_after


def queue_max() -> int:
    return _env_int("QA_LAB_BRIDGE_QUEUE_MAX", 50)


def batch_max() -> int:
    """Скільки доменів приймаємо одним запитом. Стеля жорстка: воркер один,
    і пачка на сотню означала б годину черги під видом «прийнято»."""
    return max(1, min(_env_int("QA_LAB_BRIDGE_BATCH_MAX", 5), 20))


def job_seconds() -> float:
    """Скільки триває одне завдання — за фактом, а не за здогадом.

    Медіана `ms` останніх записів реєстру. Порожній реєстр (першого дня саме
    так) дає консервативні 60 с: краще пообіцяти більше і віддати раніше.
    """
    try:
        got = sorted(int(e.get("ms") or 0) for e in ai_ledger.entries(_state_root(), shards=1)
                     if int(e.get("ms") or 0) > 0)[-50:]
        if got:
            return max(1.0, got[len(got) // 2] / 1000.0)
    except Exception:
        pass
    return 60.0


def queue_state() -> dict:
    depth = _queue.qsize()
    return {"depth": depth, "inflight": inflight_count(),
            "worker_alive": bool(_worker and _worker.is_alive()),
            "max": queue_max(),
            "eta_s": int(round((depth + 1) * job_seconds()))}


def submit(job: dict) -> None:
    """Ставить завдання в чергу. Кидає `QueueFull`, коли вона повна.

    Межа потрібна саме тому, що прийом дешевий, а виконання — ні: воркер
    один, і без межі буря з того боку приймалась би ЦІЛКОМ. Ми відповідали б
    «прийнято» на кожен запит, а розгрібалось би це годинами — тобто
    брехали б, не помічаючи цього.
    """
    depth = _queue.qsize()
    if depth >= queue_max():
        raise QueueFull(depth, int(round(depth * job_seconds())) or 60)
    start_worker()
    _jobs[job["request_id"]] = {"state": "queued", "result": None}
    _queue.put(job)


# --------------------------------------------------------------------------
# 5. Ендпоінти
# --------------------------------------------------------------------------
class AIRequest(BaseModel):
    """Запит мосту. Форму навмисно тримаємо ШИРОКОЮ.

    Свого кінця мосту в TSM немає взагалі — отже інтеграція в будь-якому разі
    починається з одного нового виклику, і маргінальна ціна зайвих полів у
    ньому нульова. Найдешевша для них правка — переслати зріз домену, який у
    них УЖЕ зібраний (`runner._запомнить_срез`: `checks`, `fix`, `eyes`,
    `front`, `text`), нічого не перепаковуючи. Тому приймаємо і його, і голу
    прозу, і просто список імен перевірок — розбирається все це в
    `tsm_ingest.ingest()`.

    `text` більше не обов'язковий: коли приїхала структура, проза не потрібна.
    """
    text: str | list | None = None  # проза АБО список імен перевірок
    request_id: str = ""            # ідемпотентність; порожньо — згенеруємо
    branch: str = ""
    domain: str = ""
    task_id: str = ""
    tag_user_id: int | None = None  # кого тегнути в коментарі ClickUp
    tag_username: str = ""
    # --- усе нижче необов'язкове: рівно те, що в них уже лежить у зрізі ---
    checks: list | None = None          # [{"name","page","passed","logs",...}]
    checks_failed: list | None = None   # те саме під іменем з нашого контракту
    fix: list | str | None = None       # їхнє «Точно фиксить» (короткий формат)
    front: list | str | None = None     # їхнє «Frontend» (уся техніка)
    eyes: list | str | None = None      # їхнє «Посмотреть глазами» — жовте
    origin: str = ""                    # generator | deploy | mixed (whitesrc)
    source: str | dict | None = None    # {"app": "tsm", "version": "0.9.26"}
    source_version: str = ""


def _new_request_id(req: AIRequest) -> str:
    import hashlib
    raw = f"{req.text!r}|{req.branch}|{req.domain}|{req.task_id}|{time.time()}"
    return "auto-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _accept(req: AIRequest, batch_id: str = "") -> dict:
    """Приймає ОДНУ скаргу, ставить у чергу, повертає долю запиту.

    Винесено з ендпоінта, щоб пачка (`/api/ai/requests`) і одиничний запит
    ходили РІВНО тим самим кодом: два прийоми з різною логікою розійшлися б
    на першому ж виправленні, і розбіжність побачив би той бік, а не ми.

    HTTPException звідси не летить НІКОЛИ: у пачці відмова одного елемента не
    має валити решту. Коди статусів у HTTP перекладає вже ендпоінт.

    Синхронно тут робиться лише те, що дешеве і має дати негайну відповідь:
    ідентифікація вітки, захист від кола і роутинг. Прогін чеків і коміт —
    у фоні, бо самий лише sync знімка триває десятки секунд.
    """
    env = tsm_ingest.ingest(req.model_dump() if hasattr(req, "model_dump")
                            else req.dict())
    # Текст лишається наскрізним ключем усього моста (журнал, відбиток,
    # слова, модель). Коли приїхала структура — збираємо його з неї в
    # ЇХНЬОМУ ж вигляді «имя: логи»: так рядок упізнає і прозовий розбір, і
    # людина, що відкриє журнал.
    text = (req.text if isinstance(req.text, str) else "").strip()
    if not text:
        text = tsm_ingest.as_text(env).strip()
    if not text:
        return {"status": "bad_request",
                "reason": "порожній запит: ні тексту, ні перевірок"}
    rid = req.request_id.strip() or _new_request_id(req)
    root = _state_root()

    was = ai_ledger.by_request_id(root, rid)
    if was:
        return {"request_id": rid, "status": "duplicate", "result": was,
                "reason": "цей request_id уже оброблявся"}

    # Ретрай без `request_id`. На тому кінці один виклик і жодної логіки
    # повторів, тож мережева невдача цілком може прийти вдруге тим самим
    # текстом. Ловимо ДО ідентифікації й роутингу: інакше повтор устигає
    # коштувати грошей за модель, перш ніж ми помітимо, що це те саме.
    th = ai_ledger.text_hash(text)
    twin = ai_ledger.same_text(root, req.task_id, th)
    if twin:
        return {"request_id": twin.get("request_id", rid), "status": "duplicate",
                "result": twin, "reason": "той самий текст по цій тасці вже "
                                          "оброблявся щойно"}

    # Вітку конверт міг дістати з їхнього ж рядка «ИСХОДНИКИ ВАЙТА
    # (ветка «X», файлов N)» — whitesrc пише його в звіт кожного червоного
    # домену з 21.08. Це точне значення з їхньої бази заливки, а не наш
    # здогад по домену, і воно не коштує їм жодної правки.
    _дж0 = {"source": env.get("source") or "",
            "source_version": env.get("source_version") or ""}
    ident = resolve_branch(text, env.get("branch") or req.branch,
                           env.get("domain") or req.domain, req.task_id)
    if not ident["branch"]:
        rec = ai_ledger.append(root, {
            "request_id": rid, "domain": req.domain, "batch_id": batch_id, "task_id": req.task_id,
            **_дж0, "status": "unresolved", "text_head": text, "text_hash": th,
            "note": ident.get("error", ""), "loop_key": ""})
        try:
            _deps["add_problems"]([{"branch": req.branch or req.domain or "?",
                                    "domain": req.domain, "source": "ai-bridge",
                                    "reason": ident.get("error", ""),
                                    "task": req.task_id}])
        except Exception:
            pass
        return {"request_id": rid, "status": "unresolved",
                "reason": ident.get("error", ""),
                "candidates": ident.get("candidates", []),
                "record": rec["ts"]}
    branch = ident["branch"]

    routing = do_route(text, branch, env=env)
    routed = scope_checks(routing)
    # Рядки, схожі на вердикт TSM, але не впізнані: їхній `advice.py`
    # оновлюється разом з тулою, і переписане формулювання відвалиться
    # МОВЧКИ — замість безкоштовної мапи тихо ввімкнеться платна модель.
    # Тому лічимо і кладемо в реєстр; сума видно на /ai.
    #   ДРЕЙФ РАХУЄМО ПО КОНВЕРТУ, А НЕ ПО ЯКОРЯХ. Якорі більше не роутять —
    # вони лише один із способів упізнати ІМʼЯ, і рядок, який чудово впізнано
    # новою таблицею `NAMES`, для старого списку якорів однаково «невідомий».
    # Через це лічильник показував 14 нерозібраних рядків там, де не
    # розібрали рівно один. Спіймано локальним стендом.
    #   Чесний дрейф — це дві речі: рядок, схожий на вердикт, у якого не
    # вийшло дістати ім'я; і ім'я, якого не знає мапа.
    _env = routing.get("env") or {}
    # Джерело кладемо в КОЖЕН запис, включно з тим, що допише воркер: інакше
    # атрибуція була б лише в половини записів, і зведення по версіях брехало б.
    _дж = {"source": _env.get("source") or env.get("source") or "",
           "source_version": _env.get("source_version")
           or env.get("source_version") or ""}
    _карта = routing.get("map") or {}
    tsm_unknown = ([{"line": v.get("line", ""), "tsm": ""}
                    for v in (_env.get("verdicts") or [])
                    if not v.get("name") and not v.get("soft")]
                   # тільки ІМЕНОВАНІ: безіменні вже пораховані вище, а
                   # `outcome` кладе в `unknown` і тих, і тих
                   + [{"line": v.get("line", ""), "tsm": v.get("name", "")}
                      for v in (_карта.get("unknown") or [])
                      if v.get("name") and not v.get("soft")])
    tsm_new = sorted({u.get("tsm") for u in tsm_unknown if u.get("tsm")})[:5]
    # Жовте не роутимо — але й губити не можна: TSM побачив це очима, і
    # людина в ClickUp мусить про це прочитати, інакше знахідка зникає.
    tsm_soft = [str(i.get("line") or "")[:160]
                for i in ((routing.get("tsm") or {}).get("items") or [])
                if i.get("soft")][:3]

    # ВИКЛАДКА, А НЕ ВИХІДНИКИ — відповідаємо, не запускаючи нічого.
    # Це висновок ЇХНЬОГО `whitesrc.py`, а не наш здогад: він звірив домен з
    # архівом тієї самої вітки і побачив потрібне в ній на місці. Прогін по
    # такому — витрачений знімок, витрачений прогін і витрачене коло, а
    # відповідь усе одно була б `clean`, тобто гірша за правду.
    #   Тільки чистий `deploy`: коли в тексті названі й генератор, і викладка
    # (`mixed`), частина дефектів усе-таки в гілці, і роутинг лишається.
    if routed and env.get("origin") == "deploy":
        routing["not_ours"] = [w for w in ai_skills.NOT_OURS
                               if w["id"] == "deploy"] or routing["not_ours"]
        routed = []

    # «Не наше» — відповідь, а не мовчання: чверть класів дефектів TSM ми не
    # вміємо в принципі, і без цієї гілки кожен такий запит з'їдав би коло.
    if not routed:
        status, note = nothing_to_run(routing)
        rec = ai_ledger.append(root, {
            **_дж, "request_id": rid, "branch": branch, "domain": req.domain,
            "batch_id": batch_id,
            "task_id": req.task_id, "status": status, "text_head": text,
            "text_hash": th, "tsm_unknown": len(tsm_unknown),
            "tsm_new": tsm_new, "tsm_soft": tsm_soft,
            "router": routing["router"], "usd": _цiна(routing),
            "note": note, "loop_key": ai_ledger.loop_key(branch, [])})
        _tell_clickup(rec, req.task_id, tag_user_id=req.tag_user_id,
                      tag_username=req.tag_username)
        return {"request_id": rid, "status": status, "branch": branch,
                "reason": note, "routed": []}

    key = ai_ledger.loop_key(branch, routed)
    v = ai_ledger.verdict(root, key, branch, routed, rid)
    if not v["allow"]:
        rec = ai_ledger.append(root, {
            **_дж, "request_id": rid, "branch": branch, "domain": req.domain,
            "batch_id": batch_id,
            "task_id": req.task_id, "loop_key": key, "round": v["round"],
            "status": v["status"], "routed": routed, "router": routing["router"],
            "usd": _цiна(routing),
            "text_head": text, "text_hash": th, "tsm_unknown": len(tsm_unknown),
            "tsm_new": tsm_new, "tsm_soft": tsm_soft, "note": v["reason"]})
        if v["status"] == "escalated":
            _escalate(rec, req, routing)
        return {"request_id": rid, "status": v["status"], "branch": branch,
                "round": v["round"], "reason": v["reason"], "routed": routed}

    if not _claim(key, branch, routed):
        return {"request_id": rid, "status": "duplicate", "branch": branch,
                "round": v["round"], "routed": routed,
                "reason": "така сама робота вже виконується просто зараз"}

    # ЯКІ ЗАПИСИ МАПИ ПРИВЕЛИ СЮДИ. Пара `routed`/`fired` на записі — це
    # найдешевша метрика якості: запис, який роутер кличе постійно, а він
    # жодного разу не спрацював, або хибний, або ім'я склеїло два різні
    # дефекти (тоді йому потрібен варіант по логах). Дані для цього лежали в
    # реєстрі з 26.08 і ніким не рахувались.
    # Ціна ВСЬОГО запиту: і роутинг моделі, і розбір нового імені. Друге
    # писалось у відповідь, але не в реєстр — тобто бюджетний гейт його не
    # бачив, а `/ai` показував менше, ніж витрачено насправді.
    map_keys = {h["key"]: h["checks"]
                for h in ((routing.get("map") or {}).get("hits") or [])
                if h.get("class") == "ours" and h.get("checks")}
    for k in map_keys:
        verdict_map.bump(k, "routed")

    try:
        submit({
            **_дж,
            "map_keys": map_keys,
            "request_id": rid, "branch": branch, "domain": req.domain,
            "task_id": req.task_id, "loop_key": key, "round": v["round"],
            "routed": routed, "router": routing["router"],
            "usd": _цiна(routing), "text": text, "text_hash": th,
            "tsm_unknown": len(tsm_unknown), "tsm_new": tsm_new,
            "tsm_soft": tsm_soft,
            "tag_user_id": req.tag_user_id, "tag_username": req.tag_username,
            "batch_id": batch_id,
        })
    except QueueFull as full:
        # Ключі кола вже зайняті `_claim` — звільняємо, інакше вітка більше
        # ніколи не пройде гейт через роботу, яка так і не почалась.
        _release(key, branch, routed)
        return {"request_id": rid, "status": "busy", "branch": branch,
                "retry_after": full.retry_after, "queue": queue_state(),
                "reason": f"черга моста повна ({full.depth}) — повтори пізніше"}
    return {"request_id": rid, "status": "accepted", "branch": branch,
            "how": ident["how"], "round": v["round"], "routed": routed,
            "router": routing["router"], "confidence": routing["confidence"],
            "reason": routing["reason"], "apply": apply_enabled()}


@router.post("/api/ai/request", status_code=202)
def ai_request(req: AIRequest):
    """Один домен. Контракт не змінився: 202 при прийомі, 409 на
    нерозпізнану вітку, 400 на порожній запит.

    Сигнатура навмисно лишається однією моделлю: ендпоінт кличуть напряму і
    тести, і локальний стенд. Тому 429 віддається винятком із заголовком, а
    не мутацією `Response` — інакше довелось би тягнути його аргументом у
    кожного викликача.
    """
    out = _accept(req)
    if out.get("status") == "bad_request":
        raise HTTPException(400, out["reason"])
    if out.get("status") == "unresolved":
        raise HTTPException(409, {k: v for k, v in out.items()
                                  if k != "request_id"})
    if out.get("status") == "busy":
        raise HTTPException(429, out,
                            headers={"Retry-After": str(out["retry_after"])})
    return out


class AIBatch(BaseModel):
    """Пачка доменів одним запитом.

    Просив бік TSM: після прогону в них назбирується кілька червоних доменів
    одразу, і слати їх по одному — це стільки ж кругів HTTP, скільки доменів.
    """
    batch_id: str = ""
    items: list[AIRequest] = Field(default_factory=list)


@router.post("/api/ai/requests", status_code=202)
def ai_requests(req: AIBatch):
    """До `QA_LAB_BRIDGE_BATCH_MAX` доменів (дефолт 5, стеля 20).

    Код відповіді ЗАВЖДИ 202, навіть якщо частина елементів відхилена. Це не
    недбалість: 4xx на всю пачку змусив би їхній бік переслати і те, що вже
    прийнято, — тобто повтор роботи там, де ми якраз від повторів боронимось.
    Долю кожного елемента видно в `items[]`.
    """
    if not req.items:
        raise HTTPException(400, "порожня пачка: немає жодного елемента")
    cap = batch_max()
    if len(req.items) > cap:
        raise HTTPException(413, f"у пачці {len(req.items)} елементів, межа {cap} "
                                 f"(QA_LAB_BRIDGE_BATCH_MAX)")
    bid = req.batch_id.strip() or ("batch-" + str(int(time.time())))
    out = []
    for i, item in enumerate(req.items):
        try:
            got = _accept(item, batch_id=bid)
        except Exception as e:                    # елемент не валить пачку
            got = {"status": "error", "reason": str(e)[:200]}
        out.append({"i": i, **got})
    accepted = sum(1 for o in out if o.get("status") == "accepted")
    return {"batch_id": bid, "accepted": accepted, "items": out,
            "queue": queue_state()}


@router.get("/api/ai/queue")
def ai_queue():
    """Скільки роботи в мосту просто зараз — щоб той бік не слав наосліп."""
    return queue_state()


def _цiна(routing: dict) -> float:
    """Скільки коштував ЦЕЙ запит: роутинг плюс розбір нового імені.

    Друге доти не рахувалось ніде: `learn_unknown` повертав свою ціну в
    відповідь, але в реєстр ішла лише ціна `ask_model`. Отже бюджетний гейт
    не бачив половини витрат, а `/ai` показував менше, ніж списано.
    """
    return (float((routing.get("model") or {}).get("usd", 0) or 0)
            + float((routing.get("learned") or {}).get("usd", 0) or 0))


def nothing_to_run(routing: dict) -> tuple:
    """Що відповісти, коли запускати нема чого. `(status, note)`.

    Винесено окремо не заради краси: це ПРАВИЛО, а правило має бути
    перевірним. Поки воно жило всередині ендпоінта, туди непомітно закралась
    діра — розвилка читала лише рядки, впізнані ЯКОРЯМИ, і клас, що прийшов
    з МАПИ по імені перевірки, у неї не потрапляв. `visual` і `no_check`
    тихо ставали `clean`, тобто «жодна перевірка не підійшла» замість
    чесного «це бачить візуальний прогін» або «такого чека в лабі немає».
    Спіймано локальним стендом на новому імені `alt_text`.

    Порядок гілок важливий: збій ЇХНЬОЇ тули б'є все інше.
    """
    why = routing.get("not_ours") or []
    hard = [i for i in ((routing.get("tsm") or {}).get("items") or [])
            if not i.get("soft")]
    mhits = [h for h in ((routing.get("map") or {}).get("hits") or [])
             if not h.get("soft")]
    m_visual = [h for h in mhits if h.get("class") == "visual"]
    m_nocheck = [h for h in mhits if h.get("class") == "no_check"]
    if routing.get("tool_failure"):
        # Зламалась тула TSM, а не вайт. Це НЕ скарга, тому коло не
        # витрачається (гілка `not routed` до `verdict` не доходить) —
        # інакше дві мережеві невдачі в них закривали б нам вітку.
        return "skipped", ("прогін TSM зірвався — це збій їхнього "
                           "інструмента, а не дефект вайта. Перепрогнати "
                           "домен у TSM окремо.")
    if [i for i in hard if i.get("visual")] or m_visual:
        return "visual", ("перекос верстки і контраст у лабі ловить не чек, "
                          "а візуальний прогін — запусти вкладку «Візуальні» "
                          "на цій вітці, автофіксу тут немає")
    if [i for i in hard if i.get("no_check")] or m_nocheck:
        return "not_ours", "; ".join(sorted(
            {i["no_check"] for i in hard if i.get("no_check")}
            | {h["reason"] for h in m_nocheck if h.get("reason")}))
    #   ЗБІЙ РОЗБОРУ НОВОГО ІМЕНІ — НЕ «нічого не підійшло». Якщо модель не
    # відповіла, ми не знаємо, наше це чи ні, і відповідати `clean` означає
    # сказати «у вітці цього немає» там, де ми просто не питали. Спіймано
    # локальним стендом: на одному з 26 сценаріїв виклик не пройшов, і нова
    # перевірка TSM мовчки стала «чисто».
    збій = (routing.get("learned") or {}).get("error")
    невідомі = [v.get("name") for v in
                ((routing.get("map") or {}).get("unknown") or []) if v.get("name")]
    if збій and невідомі:
        return "clean", (f"перевірку {', '.join(sorted(set(невідомі)))} лаба "
                         f"бачить уперше, а розібрати її не вдалось ({збій}) — "
                         f"спробуйте ще раз або допишіть мапу вручну на /ai")
    if why or routing.get("model_says_not_ours"):
        return "not_ours", (("; ".join(w["чому"] for w in why))
                            or routing.get("reason")
                            or "лаба тут безсила")
    return "clean", (routing.get("reason")
                     or "жодна перевірка лаби під цей опис не підходить")


def _escalate(rec: dict, req: AIRequest, routing: dict):
    """Третє коло. Алерт має бути ВИДИМИМ у трьох місцях одразу — інакше
    його побачать тоді ж, коли й проблему: ніколи."""
    note = ("Лаба вже двічі відпрацювала цю саму проблему на цій вітці, "
            "а вона приходить знову. Автоматика зупинена — далі руками.")
    _tell_clickup(rec, req.task_id, note,
                  tag_user_id=req.tag_user_id, tag_username=req.tag_username)
    try:
        _deps["add_problems"]([{
            "branch": rec["branch"], "source": "ai-bridge",
            "reason": f"ЕСКАЛАЦІЯ: {rec['reason'] if 'reason' in rec else rec['note']}",
            "task": req.task_id}])
    except Exception:
        pass
    try:
        import telegram_bot
        if telegram_bot.enabled():
            telegram_bot.send(
                f"⚠️ ШІ-міст: {rec['branch']} — третє коло по тій самій "
                f"проблемі, потрібна людина.\n{rec['note']}")
    except Exception:
        pass


@router.get("/api/ai/request/{request_id}")
def ai_request_status(request_id: str):
    job = _jobs.get(request_id)
    if job and job["state"] != "done":
        return {"request_id": request_id, "status": "running"}
    if job and job.get("result"):
        return {"request_id": request_id, "status": "done",
                "result": job["result"]}
    rec = ai_ledger.by_request_id(_state_root(), request_id)
    if rec:
        return {"request_id": request_id, "status": "done", "result": rec}
    raise HTTPException(404, "такого запиту не було")


class DryRunRequest(BaseModel):
    """Той самий гнучкий вхід, що й у бойового запиту.

    Проба мусить приймати рівно те, що прийме `/api/ai/request`, інакше
    налагоджувати нею формат з того боку неможливо: людина перевірила б
    прозу, а приїхала б структура.
    """
    text: str | list | None = None
    branch: str = ""
    domain: str = ""
    task_id: str = ""
    use_model: bool = True
    checks: list | None = None
    checks_failed: list | None = None
    fix: list | str | None = None
    front: list | str | None = None
    eyes: list | str | None = None
    origin: str = ""
    source: str | dict | None = None
    source_version: str = ""


@router.post("/api/ai/dry-run")
def ai_dry_run(req: DryRunRequest):
    """Тільки роутинг: що б міст запустив і чому. Нічого не пише і не
    рахує колом. Це основний інструмент, щоб дивитись на механізм вибору
    тестів очима — і щоб міряти модель проти простих слів."""
    env = tsm_ingest.ingest(req.model_dump() if hasattr(req, "model_dump")
                            else req.dict())
    text = (req.text if isinstance(req.text, str) else "").strip()
    if not text:
        text = tsm_ingest.as_text(env).strip()
    if not text:
        raise HTTPException(400, "порожній запит: ні тексту, ні перевірок")
    # Вітку конверт міг дістати з їхнього ж рядка «ИСХОДНИКИ ВАЙТА
    # (ветка «X», файлов N)» — whitesrc пише його в звіт кожного червоного
    # домену з 21.08. Це точне значення з їхньої бази заливки, а не наш
    # здогад по домену, і воно не коштує їм жодної правки.
    _дж0 = {"source": env.get("source") or "",
            "source_version": env.get("source_version") or ""}
    ident = resolve_branch(text, env.get("branch") or req.branch,
                           env.get("domain") or req.domain, req.task_id)
    branch = ident["branch"]
    routing = do_route(text, branch, use_model=req.use_model, env=env)
    return {"branch": branch, "identified": ident, "routing": routing,
            "envelope": env,
            "history": history_for(branch) if branch else [],
            "loop_key": ai_ledger.loop_key(branch, routing["checks"])}


# --------------------------------------------------------------- скіли
def _require_human(request) -> dict:
    """Правити скіли може ЛЮДИНА з сесією, не машина.

    Токен мосту автентифікує на всьому `/api/ai/*`, а редагування скілів —
    це зміна того, які чеки взагалі бачить модель. Витік токена не має
    давати права переписати каталог: машина шле скарги, а не налаштовує
    лабу.
    """
    user = getattr(request.state, "user", None) or {}
    if user.get("is_service"):
        raise HTTPException(403, "скіли править людина з вкладки, не машина")
    return user


@router.get("/api/ai/skills")
def ai_skills_list():
    """Усі картки поточного проєкту — включно з вимкненими, щоб вкладка
    могла їх показати і повернути в стрій. `prompt` — те, що реально
    побачить модель, тобто вже без вимкнених."""
    checks = runner.load_checks()
    ptype = projects.ptype()
    ov = ai_skills_store.all_skills()
    known = {c["id"] for c in checks}
    mine = [c for c in checks
            if not c.get("error") and ptype in (c.get("projects") or [])]
    cards = sorted((ai_skills.card(c, ov.get(c["id"])) for c in mine),
                   key=lambda x: x["id"])
    return {
        "ptype": ptype,
        "cards": cards,
        # Записи без свого чека: слід від видаленого чека або заготовка під
        # той, якого ще не написали. І те, і те треба бачити очима.
        "orphans": sorted(({"id": k, **v} for k, v in ov.items()
                           if k not in known), key=lambda x: x["id"]),
        "coverage": ai_skills.coverage(checks, ov),
        "not_ours": ai_skills.NOT_OURS,
        "store": ai_skills_store.store_kind(),
        "fields": list(ai_skills_store.FIELDS),
        "prompt": ai_skills.render_for_model(
            ai_skills.catalog(checks, ptype, ov)),
    }


class SkillIn(BaseModel):
    """Ключі на дроті — ТІ САМІ, що віддає GET (`симптом`, `слова`,
    `не про це`, `лагодить`), щоб UI не мусив нічого перекладати туди-сюди;
    імена атрибутів латиницею, бо «не про це» неможливо назвати полем.

    Слова приймаємо і списком, і текстом через кому/новий рядок — у формі
    людині зручніше друкувати рядком, а сховище саме поріже й почистить.
    """
    model_config = {"populate_by_name": True}

    check_id: str
    # Порожній рядок — теж значення (скинути «лагодить»), тому не None.
    symptom: str = Field("", alias="симптом")
    words: list[str] | str = Field("", alias="слова")
    not_about: list[str] | str = Field("", alias="не про це")
    fixes: str = Field("", alias="лагодить")
    active: bool = True


@router.post("/api/ai/skills")
def ai_skill_save(req: SkillIn, request: Request):
    """Створити або перезаписати скіл. Той самий ендпоінт для обох дій:
    картка на чек рівно одна, тож «створити» і «змінити» — це те саме
    upsert-а, і два різні шляхи лише розходились би у валідації."""
    user = _require_human(request)
    try:
        rec = ai_skills_store.save({
            "check_id": req.check_id, "симптом": req.symptom,
            "слова": req.words, "не про це": req.not_about,
            "лагодить": req.fixes, "active": req.active,
        }, author=str(user.get("login") or ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return rec


@router.delete("/api/ai/skills/{check_id}")
def ai_skill_delete(check_id: str, request: Request):
    """Прибирає ЗАПИС. Для чека з вбудованою карткою це «скасувати правку»:
    далі знову діє дефолт з коду — саме тому окремої кнопки «повернути як
    було» не потрібно."""
    _require_human(request)
    if not ai_skills_store.delete(check_id):
        raise HTTPException(404, "такого скіла в сховищі немає")
    return {"deleted": check_id}


class SkillActive(BaseModel):
    active: bool


@router.post("/api/ai/skills/{check_id}/active")
def ai_skill_active(check_id: str, req: SkillActive, request: Request):
    """Вимкнути/увімкнути скіл.

    Вимкнений чек зникає з каталогу, який бачить модель, — тобто ШІ
    фізично не може його обрати. Сам чек лишається живим: його, як і
    раніше, запускає людина з вкладки перевірок.

    Щоб вимкнути чек із ВБУДОВАНОЮ карткою, спершу треба її зберегти —
    інакше вимикати нічого: запису у сховищі ще немає.
    """
    _require_human(request)
    rec = ai_skills_store.set_active(check_id, req.active)
    if rec is None:
        raise HTTPException(404, "спершу збережи скіл, потім вимикай")
    return rec


# ------------------------------------------------------- мапа вердиктів
@router.get("/api/ai/verdicts")
def ai_verdicts_list():
    """Мапа «їхня перевірка → що з цим робить лаба», як вона діє зараз.

    Читати можна і машині: це та сама відкритість, що й у скілів — той бік
    має бачити, чого від нас чекати. Правити — лише людині.
    """
    cards = cards_for_project()
    entries = verdict_map.all_entries()
    seed = set(verdict_map.defaults())
    over = verdict_map.overlay()
    rows = []
    for k, rec in sorted(entries.items()):
        rows.append({**rec,
                     "source": k.split(":", 1)[0],
                     "name": k.split(":", 1)[-1],
                     # Звідки взявся запис, який ДІЄ: дефолт з коду, правка
                     # людини чи відповідь моделі. Без цього рядка мапа
                     # виглядає однорідною, а довіра до неї — ні.
                     "origin": ("накладка" if k in over else "дефолт"),
                     "stats": rec.get("stats") or {}})
    # Записи, вивчені моделлю при ІНШОМУ каталозі: додали чек — стара
    # відповідь його ніколи не обере, бо нікого не питає.
    stale = [r["key"] for r in verdict_map.stale(cards)]
    # Найдешевша метрика якості: кликали, а воно жодного разу не спрацювало.
    quiet = [{"key": r["key"], "routed": (r.get("stats") or {}).get("routed", 0)}
             for r in rows
             if (r.get("stats") or {}).get("routed", 0) >= 3
             and not (r.get("stats") or {}).get("fired")]
    return {"store": verdict_map.store_kind(), "count": len(rows),
            "seeded": len(seed), "overlaid": len(over),
            "entries": rows, "stale": stale, "quiet": quiet,
            "catalogue": verdict_map.catalogue_hash(cards)}


class VerdictIn(BaseModel):
    key: str
    cls: str = ""                    # `class` — зарезервоване слово
    php: list | str | None = None
    node: list | str | None = None
    not_ours: str = ""
    reason: str = ""
    variants: list | None = None
    active: bool = True


@router.post("/api/ai/verdicts")
def ai_verdict_save(req: VerdictIn, request: Request):
    """Правка мапи людиною. Кладеться НАКЛАДКОЮ поверх дефолту."""
    user = _require_human(request)
    try:
        return verdict_map.save({"key": req.key, "class": req.cls,
                                 "php": req.php, "node": req.node,
                                 "not_ours": req.not_ours,
                                 "reason": req.reason,
                                 "variants": req.variants or [],
                                 "active": req.active, "by": "human"},
                                author=user.get("login", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/api/ai/verdicts/{key}")
def ai_verdict_delete(key: str, request: Request):
    """Прибирає ЗАПИС накладки. Для ключа з дефолтом це «скасувати правку»:
    далі знову діє те, що їде з кодом."""
    _require_human(request)
    if not verdict_map.delete(key):
        raise HTTPException(404, "такого запису в накладці немає")
    return {"ok": True, "key": key}


@router.get("/ai", response_class=HTMLResponse)
def ai_page():
    """Сторінка для користувача лаби: журнал запитів, лічильники, каталог
    скілів і — головне — «проба роутингу».

    Окремим файлом, а не вкладкою в index.html: за рамкою замовника наше в
    цьому дереві — авторизація і білд, а решта UI лишається як задумав автор.
    Так само свого часу з'явились login.html і users.html.

    Шлях БЕЗ префікса /api/, тому машинний токен сюди не діє: сторінку
    відкриває людина з кукою, як і решту лаби.
    """
    from pathlib import Path
    return HTMLResponse((Path(__file__).parent / "static" / "ai.html")
                        .read_text(encoding="utf-8"))


@router.get("/api/ai/log")
def ai_log(limit: int = 100):
    rows = ai_ledger.entries(_state_root(), shards=2)
    ok, why = ai_router.available()
    return {"counters": ai_ledger.counters(_state_root()),
            "rows": list(reversed(rows))[:max(1, limit)],
            "apply": apply_enabled(),
            "autofix_groups": sorted(autofix_groups()),
            "model": {"name": ai_router.model_name(), "ready": ok, "why": why},
            "budget_usd": budget_usd(),
            "spent_month_usd": ai_ledger.spend_usd(_state_root(), shards=1)}
