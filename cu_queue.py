"""Черга ClickUp: те саме, що людина робить кнопками, тільки саме.

Вхід — `task_id`. Приходить він з вебхука (прод) або з фонового опиту (дев і
страхувальник на проді), а далі йдуть рівно ті кроки, які людина проходить у
вкладці ClickUp:

    дотягнути таску → гейт «це наша?» → розкласти на вітки → по одній вітці:
    sync → чеки → порахувати фікси

**КОМІТУ ТУТ НЕМАЄ, і в ClickUp ми теж нічого не пишемо.** Результат лягає у
вкладку «Черга», а в git і в таску пише рівно одне місце — кнопка людини
(`apply()`). Це не налаштування, яке можна ввімкнути: у прогоні просто немає
виклику `commit()`.

П'ять рішень, які легко зламати назад:

1. **Два незалежні перемикачі.** `intake` — приймати нові таски, `run` —
   виконувати. «Стоп» гасить ДРУГИЙ: черга далі наповнюється з вебхука, і
   видно, скільки накопичилось. Обидва за замовчуванням ВИМКНЕНІ: увімкнена
   черга починає качати знімки (615 віток ≈ 2 ГБ), і це має бути свідомим
   натисканням, а не наслідком деплою.
2. **Один виконавець, лок береться по вітці** (`runner.pipeline_lock`, спільний
   з ШІ-мостом) — заявка мосту чекає секунди, а не весь прохід.
3. **Проєкт — накладка на потік** (`projects.use`): 240 з 315 віток лежать у
   node-репо, а глобальний активний проєкт видно людині в UI.
4. **Скіп по парі «коміт вітки + відбиток набору чеків».** Без нього балакуча
   таска (ClickUp шле `taskUpdated` на кожну дрібницю) ганяла б ті самі вітки
   по колу. Відбиток чеків у ключі — щоб правка чека переганяла корпус.
5. **Порожній знімок — `not_ready`, а не `clean`** (див. `pipeline`): знімок
   доїжджає не миттєво, і «чисто» закрило б вітку до наступної зміни коміту.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import threading
import time
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import clickup_client
import domains
import cu_triage
import pipeline
import projects
import runner

# --------------------------------------------------------------------------
# 1. Налаштування
# --------------------------------------------------------------------------
STATE_FILE = "cu_queue.json"

# Канонічна адреса таски в ClickUp. Подія вебхука адреси не несе, а картка без
# лінки марна: людина бачить id і не може відкрити таску.
TASK_URL = "https://app.clickup.com/t/{}"

# Вироки вітки. `applied` дописує кнопка, решту — виконавець.
UNCHANGED, GONE, PROTECTED, DIRTY, ERROR, APPLIED = (
    "unchanged", "gone", "protected", "dirty", "error", "applied")
# Що людина мусить побачити очима — вкладка «Проблеми».
#
# `no_fix` (дефект видно, автофікса немає) сюди НЕ входить з 21.09.2026 —
# правило колеги-QA для етапу 1: «некоторые фиксы показывают ошибки там где их
# нет, но на них нет автофикса. На первом этапе — это игнорируем». Вітка з
# таким вироком лишається у вкладці з переліком чеків, але не шумить і не
# блокує завершення таски.
PROBLEM = {GONE, DIRTY, ERROR}
# Стани, у яких вітку можна не чіпати до зміни коміту.
SETTLED = {pipeline.CLEAN, pipeline.NO_FIX, pipeline.WOULD_FIX, PROTECTED, APPLIED}
# «QA цієї вітки пройдено» (етап 1, 21.09.2026): чисто, закомічено, без змін
# від чистого, або дефект без автофікса — його на етапі 1 ігноруємо.
PASSED = {pipeline.CLEAN, pipeline.NO_FIX, UNCHANGED, APPLIED}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def enabled() -> bool:
    """Вето стенда. `CU_QUEUE_ENABLED=0` ховає перемикачі взагалі — деплой
    повільний, тож «вимкнути зараз» мусить працювати з браузера, а «увімкнути
    те, чого прод не дозволив» — ні."""
    return os.getenv("CU_QUEUE_ENABLED", "1").strip() not in ("0", "false", "no")


def queue_max() -> int:
    """Межа черги у ТАСКАХ. Прийом дешевий, виконання — ні: одна таска це в
    середньому 4.7 вітки по ~2 с, тобто сотня тасок це вже пів години."""
    return _int("CU_QUEUE_MAX", 100)


def branch_max() -> int:
    """Стеля віток на таску. Рекорд корпусу — десятки; таска на сотню вітою
    означала б, що виконавець стоїть на ній годину."""
    return _int("CU_BRANCH_MAX", 30)


def tasks_cap() -> int:
    """Скільки тасок тримаємо у стані вкладки."""
    return _int("CU_TASKS_CAP", 300)


def gone_retry_min() -> int:
    """Як часто перепитувати GitLab про вітку, якої немає.

    Знайдено живим прогоном 04.09.2026: у частини тасок у полі `Safe Page`
    лежать ДОМЕНИ, а не вітки (`sad-fsi.ch`, `www.moghenmidbhik.com`) — вони
    проходять розбір як валідні токени і дають `gone` назавжди. Без затримки
    кожна подія по такій тасці означала б п'ять марних GET-ів у GitLab і
    п'ять однакових рядків у «Проблемах».

    Зовсім не перепитувати теж не можна: вітку могли ще не створити на момент
    події, і за годину вона з'явиться.
    """
    return max(1, _int("CU_GONE_RETRY_MIN", 60))


def poll_minutes() -> int:
    """Період страхувального опиту. Вебхук ClickUp глушить себе сам після
    серії невдалих доставок, і тоді тиша виглядає як «нових тасок немає»."""
    return max(1, _int("CU_POLL_MIN", 30))


def autocommit_max() -> int:
    """Скільки віток одна таска має право закомітити без людини.

    Межа є тому, що помилка в чеку однакова на всіх вітках: якщо фікс поганий,
    він поганий скрізь, і без стелі один прогін розкладе його на всю таску.
    Решта лишається людині кнопкою — вона нікуди не зникає.
    """
    return max(1, _int("CU_AUTOCOMMIT_MAX", 10))


def groups() -> set:
    """Які групи чеків ганяємо. `review` немає навмисно: `external_links` дає
    error на 100% прогонів, `header_style` — на 94%, як сигнал вони марні."""
    raw = os.getenv("CU_QUEUE_GROUPS", "auto,tests")
    return {g.strip() for g in raw.split(",") if g.strip()}


# --------------------------------------------------------------------------
# 2. Звʼязки з app (щоб не імпортувати його і не вийшло кола)
# --------------------------------------------------------------------------
def _plain_read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _plain_write(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _unwired(*_a, **_kw):
    raise RuntimeError("cu_queue.wire() не викликано")


# Читання й запис мають дефолти, щоб модуль піднімався сам (тести, разова
# перевірка з консолі). А от ті двоє, що ПИШУТЬ назовні, дефолту не мають
# навмисно: мовчазний no-op у журналі комітів був би найгіршим із можливих.
_deps: dict = {"read_json_state": _plain_read, "write_json_state": _plain_write,
               "log_commit": _unwired, "add_problems": _unwired,
               "drop_problems": _unwired, "load_problems": _unwired,
               "client": None}


def wire(*, read_json_state, write_json_state, log_commit, add_problems,
         drop_problems, load_problems, client) -> None:
    _deps.update(read_json_state=read_json_state, write_json_state=write_json_state,
                 log_commit=log_commit, add_problems=add_problems,
                 drop_problems=drop_problems, load_problems=load_problems,
                 client=client)


def _path():
    return projects.shared_file(STATE_FILE)


_lock = threading.Lock()
# Скільки відсіяних тасок памʼятаємо. Живий прогін 07.09: зі 34 номінованих
# гейт відсіює 32, і кожна коштує запиту в ClickUp — а опит повторюється раз на
# півгодини вічно. Памʼять про відсів робить цю ціну разовою.
REJECTED_CAP = 2000

_default_state = {"intake": False, "run": False, "autocommit": False,
                  "rejected": {}, "tasks": {},
                  "counters": {"accepted": 0, "skipped": 0, "events": 0,
                               "committed": 0},
                  "last_event": "", "last_poll": ""}


def load() -> dict:
    """Стан з диска поверх дефолтів.

    Копія дефолтів МУСИТЬ бути глибокою: `dict(_default_state)` віддає ті самі
    вкладені словники (`tasks`, `rejected`, `counters`), і на порожньому стані
    перший же запис мутував би сам дефолт — після чого «чистий стан» уже не
    чистий до кінця процесу. Спіймано soak-прогоном 07.09: памʼять про відсів
    жила між прогонами, які мали починатись з нуля.
    """
    st = {k: (dict(v) if isinstance(v, dict) else v)
          for k, v in _default_state.items()}
    st.update(_deps["read_json_state"](_path(), {}) or {})
    st.setdefault("tasks", {})
    st.setdefault("rejected", {})
    st.setdefault("counters", dict(_default_state["counters"]))
    return st


def save(st: dict) -> None:
    _deps["write_json_state"](_path(), st)


def _update(fn):
    """Читання-правка-запис під локом: виконавець і HTTP-виклики пишуть у той
    самий файл."""
    with _lock:
        st = load()
        out = fn(st)
        # Обрізаємо найстаріші ЗАВЕРШЕНІ таски: те, що в роботі, не чіпаємо.
        tasks = st.get("tasks") or {}
        if len(tasks) > tasks_cap():
            done = sorted((t for t in tasks.values() if t.get("state") == "done"),
                          key=lambda t: t.get("done_ts") or "")
            for t in done[:len(tasks) - tasks_cap()]:
                tasks.pop(t["task_id"], None)
        save(st)
        return out


# --------------------------------------------------------------------------
# 3. Черга і перемикачі
# --------------------------------------------------------------------------
_q: "queue.Queue[str]" = queue.Queue()
_go = threading.Event()          # виставлений = виконавець працює
_worker: threading.Thread | None = None
_poller: threading.Thread | None = None
_threads_lock = threading.Lock()


class QueueFull(Exception):
    def __init__(self, depth: int):
        super().__init__(f"черга повна: {depth}")
        self.depth = depth


def switches() -> dict:
    st = load()
    return {"intake": bool(st.get("intake")), "run": bool(st.get("run")),
            "autocommit": bool(st.get("autocommit"))}


def set_switches(intake=None, run=None, autocommit=None) -> dict:
    def apply_(st):
        if intake is not None:
            st["intake"] = bool(intake)
        if run is not None:
            st["run"] = bool(run)
        if autocommit is not None:
            st["autocommit"] = bool(autocommit)
        return {"intake": st["intake"], "run": st["run"],
                "autocommit": st["autocommit"]}
    got = _update(apply_)
    _go.set() if got["run"] else _go.clear()
    if got["intake"] or got["run"]:
        start()
    if got["run"]:
        # Кваліфіковані таски чекають на ▶ у СТАНІ, а не в черзі в пам'яті
        # (інакше цикл крутився б навхолосту навколо них). Тому вмикання
        # виконавця мусить повернути їх у чергу — тим самим кодом, що й
        # рестарт процесу.
        restore_queue()
    return got


def is_on(st: dict | None = None) -> bool:
    """Авто-QA увімкнене — усі три перемикачі разом."""
    st = st if st is not None else load()
    return all(bool(st.get(k)) for k in ("intake", "run", "autocommit"))


def set_auto(on: bool) -> dict:
    """Одна кнопка «Авто-QA вкл/викл» — рішення 23.09.2026: «усе працює
    автоматично лише коли вкл, інакше ручний режим».

    Увімкнено — лаба сама бере таски, ганяє QA, комітить фікси і відписує
    `fixed` коментарем. Вимкнено — не робить нічого з цього: таски не
    приймаються, прогони не йдуть, у git і в ClickUp не пишеться ні рядка.
    Три прапорці всередині лишились (прийом, виконавець, автокоміт — на них
    тримаються черга, опит і тести), але людина бачить і перемикає їх лише
    разом."""
    return {**set_switches(intake=on, run=on, autocommit=on), "on": bool(on)}


def normalize_switches() -> bool:
    """Змішаний стан перемикачів → вимкнено. Кличеться на старті процесу.

    До 23.09.2026 перемикачів у вкладці було три, і в томі стану міг лишитись
    будь-який їхній набір — скажімо, прийом і виконавець увімкнені, а
    автокоміт ні. Одна кнопка такого стану показати не вміє. Добудовувати його
    до «увімкнено» не можна: увімкнене — це ще й коміти у вітки, і воно мусить
    бути свідомим натисканням, а не наслідком деплою. Тому — вимкнено.
    Повертає True, якщо стан довелось виправити."""
    st = load()
    flags = [bool(st.get(k)) for k in ("intake", "run", "autocommit")]
    if all(flags) or not any(flags):
        return False
    set_switches(intake=False, run=False, autocommit=False)
    return True


def submit(task_id: str, source: str = "hook", name: str = "",
           url: str = "", force: bool = False) -> dict:
    """Ставить таску в чергу. Повертає долю — приймати рішення має викликач
    (вебхук відповідає 200 у будь-якому разі, щоб ClickUp не глушив підписку).
    """
    task_id = (task_id or "").strip()
    if not task_id:
        return {"status": "bad_request", "reason": "порожній task_id"}
    # Вебхук приносить ЛИШЕ id: ні імені, ні адреси в події немає, а дотягувати
    # таску в дверях не можна (ClickUp глушить підписку за повільну відповідь).
    # Тому адресу збираємо з id — інакше в черзі лежить голий `868kzn90p`, на
    # який людина не може навіть глянути (скарга 07.09).
    url = (url or "").strip() or TASK_URL.format(task_id)
    st = load()
    # `force` — ручна дія людини («Актуалізувати» у «Проблемах»). Вона не
    # питає перемикача прийому: людина натиснула саме зараз і саме на це.
    if not force and not st.get("intake"):
        return {"status": "off", "reason": "прийом вимкнено"}

    depth = _q.qsize()
    if depth >= queue_max():
        raise QueueFull(depth)

    def add(s):
        rec = (s["tasks"] or {}).get(task_id)
        # Уже в черзі або в роботі — друга подія по тій самій тасці нічого не
        # додає. ClickUp шле кілька подій на одну правку.
        if rec and rec.get("state") in ("queued", "running"):
            return False
        s["tasks"][task_id] = {**(rec or {}), "task_id": task_id,
                               "state": "queued", "source": source,
                               # Назву кладемо одразу, коли викликач її знає:
                               # інакше таска висить у таблиці голим id, доки
                               # до неї не дійде черга.
                               "name": name or (rec or {}).get("name") or "",
                               "url": url or (rec or {}).get("url") or "",
                               "ts": _now(), "done_ts": "", "reason": "",
                               "branches": (rec or {}).get("branches") or []}
        s["counters"]["accepted"] = int(s["counters"].get("accepted") or 0) + 1
        s["last_event"] = _now()
        return True

    if not _update(add):
        return {"status": "duplicate", "reason": "уже в черзі"}
    _q.put(task_id)
    start()
    return {"status": "queued", "depth": _q.qsize()}


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# 4. Виконавець
# --------------------------------------------------------------------------
def _checks_fp(ids) -> str:
    """Відбиток набору чеків: правка складу мусить переганяти корпус."""
    return hashlib.sha1(",".join(sorted(ids)).encode()).hexdigest()[:8]


def default_check_ids() -> list[str]:
    return sorted(c["id"] for c in runner.checks_for_active_project()
                  if c.get("group") in groups())


def triage_of(task: dict, was: dict) -> dict:
    """Вирок тріажу з кешем.

    Повторюємо розбір лише коли змінилось те, що на нього впливає: ТЕКСТ
    скарги або набір активних скілів. Інакше балакуча таска (ClickUp шле
    `taskUpdated` на кожну дрібницю) платила б моделлю на кожну подію, а
    кнопка «Актуалізувати» не мала б чого міняти.
    """
    prev = was.get("triage") or {}
    # Прогін після зміни доменів — не вирок тріажу, а окремий шлях
    # (`_process_domains`); підхопити його як кеш означало б лишити таску без
    # розбору прохань саппорта.
    if prev.get("verdict") and prev.get("verdict") != cu_triage.DOMAINS:
        # Ключ — той текст, від якого залежить вирок (на етапі 1 — прохання
        # саппорта, на етапі 2 — скарга): інакше коротке «@Nora не фикс»
        # (менше порогу скарги) не скидало б кеш, і таска лишалась би «авто».
        same_text = prev.get("text_hash") == cu_triage.text_hash(
            cu_triage.decision_text(task))
        same_skills = prev.get("skills_fp") == cu_triage.skills_fingerprint()
        if same_text and same_skills:
            return dict(prev, cached=True)
    return cu_triage.classify(task)


# ------------------------------------------------- skip-теги таски (02.10)
# Саппорт пише «домены не должны быть под название сайта — оставляйте как
# есть»: тег на тасці вимикає відповідні чеки для ЇЇ віток. Формат:
#   skip:<check_id>   — точково (skip:domain_match, skip:favicon)
#   skip:domains      — алиас: чеки, що вирівнюють пошту/домени
#   skip:brand        — алиас: чеки назви у лого
# Регістр байдужий (клієнт лоуеркейсить), дефіси = підкреслення,
# `noqa:` — синонім `skip:`.
SKIP_TAG_RX = re.compile(r"^(?:skip|noqa)[:\-]\s*(.+)$")
SKIP_ALIASES = {
    "domains": {"domain_match", "contacts"},
    "domain": {"domain_match", "contacts"},
    "домени": {"domain_match", "contacts"},
    "домены": {"domain_match", "contacts"},
    "brand": {"logo_domain", "logo_brand", "logo_latin", "logo_photo"},
    "name": {"logo_domain", "logo_brand", "logo_latin", "logo_photo"},
    "назва": {"logo_domain", "logo_brand", "logo_latin", "logo_photo"},
    "название": {"logo_domain", "logo_brand", "logo_latin", "logo_photo"},
}


def skip_ids_for(task: dict | None) -> set[str]:
    """id чеків, вимкнених тегами таски."""
    out: set[str] = set()
    for tag in (task or {}).get("tags") or []:
        m = SKIP_TAG_RX.match(str(tag).strip().lower())
        if not m:
            continue
        token = m.group(1).strip().replace("-", "_").replace(" ", "_")
        out |= SKIP_ALIASES.get(token, {token})
    return out


def skip_for_branch(branch: str) -> tuple[set[str], str]:
    """(вимкнені чеки, назва таски) для РУЧНОГО прогону вітки: вітка живе
    у тасці зі skip-тегами — вкладка «Перевірки» поважає ті самі межі."""
    for t in (load().get("tasks") or {}).values():
        if any(b.get("branch") == branch for b in (t.get("branches") or [])):
            ids = skip_ids_for(t)
            if ids:
                return ids, t.get("name") or t.get("task_id") or ""
    return set(), ""


def _branch_record(name: str, domain: str, task_id: str = "",
                   task_name: str = "") -> dict:
    return {"branch": name, "domain": domain,
            "task_id": task_id, "task_name": task_name,
            "project": "", "verdict": "",
            "fired": {}, "fixable": [], "files": 0, "paths": [], "note": "",
            "commit": "", "checks_fp": "", "ms": 0, "applied_ts": "", "ts": ""}


def _fresh(ts: str, minutes: int) -> bool:
    """Чи молодша позначка часу за вказану кількість хвилин."""
    try:
        return (time.time() - time.mktime(
            time.strptime(ts, "%Y-%m-%d %H:%M:%S"))) < minutes * 60
    except Exception:
        return False


def _run_one(rec: dict, prev: dict, extra: list | None = None,
             only: list | None = None,
             skip: frozenset | set = frozenset()) -> dict:
    """Одна вітка від пошуку до вироку. Виняток не пускає назовні.

    `only` — прогнати РІВНО ці чеки замість повного набору (зміна доменів:
    лише пошта й домени). `skip` — чеки, вимкнені тегом таски (02.10:
    «оставляйте как есть»): віднімаються і від повного набору, і від
    `only`."""
    t0 = time.time()
    name = rec["branch"]
    try:
        # Вітки, якої немає, ми вже шукали. Перепитуємо не частіше ніж раз на
        # годину: інакше таска з доменами у `Safe Page` коштувала б п'ять
        # марних GET-ів на кожну подію ClickUp.
        if (prev.get("verdict") == GONE
                and _fresh(prev.get("ts", ""), gone_retry_min())):
            rec.update(verdict=GONE, note=prev.get("note") or "",
                       ts=prev.get("ts", ""))
            return rec
        found = projects.locate_branch(name)
        if not found:
            rec["verdict"], rec["note"] = GONE, "вітки немає в жодному проєкті"
            return rec
        rec["project"], rec["branch"] = found["pid"], found["name"]
        info = found["info"]
        commit = str(info.get("commit") or "")

        # Захищена вітка: коміт усе одно впав би 403, і краще сказати це
        # словами, ніж показати відмову GitLab.
        if info.get("protected") or info.get("can_push") is False:
            rec["verdict"], rec["commit"] = PROTECTED, commit
            rec["note"] = "вітка захищена — комітити не можна"
            return rec

        with projects.use(found["pid"]):
            # ДОМЕН ПІДВʼЯЗУЄМО ТУТ, і без цього рядка половина конвеєра німа.
            # `logo_domain`, `logo_brand`, `domain_match`, `favicon_link` беруть
            # домен з `domains.active_for(branch)` і мовчки повертають ПОРОЖНЬО,
            # якщо його немає. Досі домени бив лише імпорт з вкладки ClickUp,
            # тож черга ганяла ці чеки в порожнечу: скарга «лого не під доменне
            # ім'я» давала «чисто» (07.09, таски 868m1bf3n і 868m24rtn).
            if rec.get("domain"):
                try:
                    domains.bind(rec["branch"], rec["domain"],
                                 rec.get("task_id", ""), rec.get("task_name", ""))
                except Exception:
                    traceback.print_exc()
            if only is not None:
                # Порожній список `run_checks` читає як «усі чеки», тож чеків
                # поза проєктом тут просто не ганяємо, а не передаємо [].
                have = {c["id"] for c in runner.checks_for_active_project()}
                base = set(only) & have
            else:
                base = set(default_check_ids()) | set(extra or [])
            cut = sorted(base & set(skip))
            ids = sorted(base - set(skip))
            if cut:
                rec["note"] = "⏭ вимкнено тегом таски: " + ", ".join(cut)
            if not ids:
                rec["verdict"], rec["commit"] = pipeline.CLEAN, commit
                rec["note"] = rec["note"] or (
                    "у цьому проєкті немає чеків пошти й доменів")
                return rec
            fp = _checks_fp(ids)
            # Скіп: та сама вітка на тому самому коміті тим самим набором
            # чеків і з ТИМ САМИМ доменом уже проходила і осіла. Домен у ключі
            # з 25.09.2026: саппорт міняє домени без жодного коміту у вітці, і
            # без нього вітка «без змін» так і лишалась би з поштою на старому.
            if (prev.get("commit") == commit and prev.get("checks_fp") == fp
                    and (prev.get("domain") or "") == (rec.get("domain") or "")
                    and prev.get("verdict") in SETTLED and commit):
                rec.update({k: prev.get(k) for k in
                            ("fired", "fixable", "files", "paths", "note")})
                # «Є що полагодити» і «захищена» — не «без змін»: перше чекає
                # на коміт, друге не пройде QA ніколи. Доти повторний прогін
                # на тому самому коміті робив з would_fix «без змін», і фікс
                # тихо випадав із кнопки коміту (знайдено 21.09.2026).
                keep = prev.get("verdict") in (pipeline.WOULD_FIX, PROTECTED)
                rec["verdict"] = prev["verdict"] if keep else UNCHANGED
                rec["commit"], rec["checks_fp"] = commit, fp
                return rec

            with runner.pipeline_lock:
                got = pipeline.run_branch(name, ids,
                                          client=projects.client_for(found["pid"]),
                                          groups=groups())
            rec["verdict"] = got["verdict"]
            rec["fired"] = got["fired"]
            rec["fixable"] = got["fixable"]
            rec["files"] = got["files"]
            rec["paths"] = [c["path"] for c in got["changes"]]
            rec["commit"] = commit
            rec["checks_fp"] = fp
            if got["stale"]:
                rec["note"] = (rec["note"] + "; " if rec["note"] else "") \
                    + got["stale"]
    except Exception as e:
        rec["verdict"] = ERROR
        rec["note"] = f"{type(e).__name__}: {str(e)[:200]}"
        traceback.print_exc()
    finally:
        rec["ms"] = int((time.time() - t0) * 1000)
        rec["ts"] = rec.get("ts") or _now()
    return rec


def _card_extras(task: dict) -> dict:
    """Те, що вкладка ClickUp показує на картці, крім останнього коментаря:
    стан чекліста whites і коментар зі згадкою виконавця (на скріні задачі
    21.09.2026 обидва обведені). Беремо з уже дотягнутої таски — запиту це
    не коштує. Коментар зі згадкою — той самий, що рахує `cuMentionComment`:
    найновіший, де згадано когось із виконавців таски."""
    def norm(x):
        return "".join(ch for ch in (x or "").lower() if ch.isalnum())
    who = [norm(a) for a in task.get("assignees") or [] if norm(a)]
    mention = None
    for c in task.get("comments") or []:
        if not isinstance(c, dict):
            continue
        ms = [norm(m) for m in c.get("mentions") or []]
        if any(m and w and (m == w or m in w or w in m) for m in ms for w in who):
            mention = {"text": (c.get("text") or "")[:600], "user": c.get("user") or ""}
            break
    out = {"mention": mention}
    if task.get("checklist_loaded") is not False:
        out["checklist_found"] = bool(task.get("checklist_found"))
        out["checklist_done"] = bool(task.get("checklist_done"))
    return out


def qualify(task_id: str):
    """Дотягнути таску і вирішити, чи їй тут місце. Повертає таску або None.

    **Чому це окремий крок і чому він іде на ПРИЙОМІ, а не на прогоні.**
    Подія вебхука несе тільки `task_id`: ні полів, ні статусу, ні тегів. Тому
    опит фільтрує, а вебхук — ні, і з вимкненим виконавцем у вкладці
    накопичувалось усе підряд: чужі таски, блеки, вже пофіксені, голі id без
    імені (скарга 07.09 — «блеків тягнути сюди не треба»).

    Ціна кваліфікації — РІВНО ОДИН запит у ClickUp на таску, без моделі:
    поля + наш підпис в останньому коментарі. Повний тріаж (роутинг скарги,
    можлива модель) лишається у виконавця, бо він коштує дорожче і потрібен
    лише тому, що справді піде в роботу.
    """
    got = clickup_client.fetch_by_ids([{"id": task_id}], with_comments=True)
    task = (got or [{}])[0]
    task.setdefault("id", task_id)

    # «Проблеми» — робоче місце ЛЮДИНИ, і зупинена черга не має права в нього
    # писати. Кваліфікація навмисно йде і з вимкненим виконавцем (рішення
    # 07.09, розд. 18), але разом з нею туди щопівгодини лягали ті самі рядки
    # про недоступні таски, а «Очистити проблеми» нічого не давало: опит
    # приносив їх наново (скарга 09.09). У вкладці «Черга» таска з причиною
    # видно в обох випадках — нічого не губиться.
    to_problems = bool(load().get("run"))

    if task.get("no_access"):
        _finish(task_id, task, "no_access",
                "ClickUp не дає доступу до таски цим токеном", problem=to_problems)
        return None
    if task.get("enrich_failed"):
        _finish(task_id, task, "error", task.get("error", "")[:200],
                problem=to_problems)
        return None
    # Зміна доменів (25.09.2026) — окремий шлях, і він іде ПЕРЕД гейтом
    # вкладки: домени міняють якраз у вже пофікшених тасках (чекліст ✓,
    # «fixed»), які гейт і правило «fixed уже є» відсікають. Саме такими були
    # всі сім тасок того дня. Імʼя акаунта лаби (тег `@Tech Bot`) — з токена,
    # раз на пів доби: тріаж сам у мережу не ходить.
    try:
        clickup_client.refresh_lab_account()
    except Exception:
        traceback.print_exc()
    notice = domain_notice_of(task)
    if not notice:
        if not cu_triage.gate_ok(task):
            _remember_rejected(task_id, task)
            _finish(task_id, task, "skipped", "не проходить фільтри вкладки")
            return None
        if cu_triage.already_answered(task):
            _remember_rejected(task_id, task)
            _finish(task_id, task, "skipped",
                    "лаба вже відповіла в цій тасці, нового після того не було")
            return None
        # Рішення юзера 24.09: «вебхук взагалі не має грузити задачі з вже
        # наявним fixed». Попередження про такі таски — справа РУЧНОЇ роботи
        # (`cu_fixed`), а черзі їх просто не видно. Виняток — прохання
        # саппорта після «fixed»: така таска доходить до `classify` і стає
        # ручним розбором.
        if cu_triage.fixed_is_last(task):
            _remember_rejected(task_id, task)
            _finish(task_id, task, "skipped",
                    "у тасці вже є fixed, нового прохання після нього немає")
            return None

    # Пройшла — картка нарешті отримує ім'я, адресу і статус. Доти вона
    # виглядала як `868kzn90p`, на що людині нема чого дивитись.
    # Разом з іменем кладемо те, заради чого людина інакше йшла б у ClickUp:
    # останній коментар і скільки їх усього. Вимога 07.09: «у вкладці ClickUp
    # видно коментарі, вітки й домени, а в черзі просто написано, що щось не
    # так». Другого запиту це не коштує — таска вже в руках.
    lc = task.get("last_comment") or {}
    # Вітки з доменами — одразу, а не після прогону (задача 21.09.2026: «ветки
    # и домены» мають бути на картці, як у вкладці ClickUp). Таска вже в
    # руках, тож другого запиту це не коштує. Записи — ті самі, що кладе
    # виконавець, просто без вироку: він їх перепише своїми.
    doms = list(task.get("domains") or [])
    planned = [_branch_record(b, doms[i] if i < len(doms) else "", task_id,
                              task.get("name") or "")
               for i, b in enumerate(list(task.get("branches") or [])[:branch_max()])]

    def name_it(st):
        t = st["tasks"].get(task_id) or {"task_id": task_id}
        t.update(name=task.get("name") or task_id, url=task.get("url") or t.get("url", ""),
                 status=task.get("status") or "", wtype=task.get("wtype") or "",
                 assignees=task.get("assignees") or [], qualified=True,
                 list_name=task.get("list_name") or "",
                 comment=(lc.get("text") or "")[:600],
                 comment_user=lc.get("user") or "",
                 comments_n=len(task.get("comments") or []),
                 domain_notice=notice,
                 **_card_extras(task))
        if not t.get("branches"):
            t["branches"] = planned
        else:
            # Рядки з минулого прогону лишаються (там вироки), але домен на
            # них — зі СВІЖОЇ таски: після зміни доменів картка інакше
            # показувала б старі, доки до неї не дійде виконавець.
            fresh = {p["branch"]: p["domain"] for p in planned if p["domain"]}
            for row in t["branches"]:
                if fresh.get(row.get("branch")):
                    row["domain"] = fresh[row["branch"]]
        st["tasks"][task_id] = t
        return None
    _update(name_it)
    return task


def domain_notice_of(task: dict) -> dict | None:
    """Свіже повідомлення «домени змінено» у вайт-тасці, де є що лагодити.

    Гейт тут свій (`domain_gate`): без статусу і без чекліста — таска вже
    пофікшена і може стояти будь-де, — але з вітками, доменами й «Типом
    вайта», не закрита і не блек."""
    if not clickup_client.domain_gate(task):
        return None
    return cu_triage.domain_change(task)


def domain_check_ids() -> list[str]:
    """Що ганяємо після зміни доменів: пошта і самопосилання. `domain_match`
    (vue) переписує їх на домен вітки — рівно те, що 25.09 на TECH-28368
    зробила людина автофіксом; `contacts` (php) тримає `{{DOMAIN}}`, тож для
    php зміна зони правок не вимагає, але захардкоджену пошту він поверне на
    плейсхолдер. Чеки поза проєктом вітки відсіює `_run_one`."""
    raw = os.getenv("CU_DOMAIN_CHECKS", "domain_match,contacts")
    return [c.strip() for c in raw.split(",") if c.strip()] or ["domain_match"]


def _remember_rejected(task_id: str, task: dict) -> None:
    """Запамʼятати відсів разом з міткою зміни таски.

    Ключ — саме `date_updated`, а не сам факт відсіву: таска, яку хтось
    поправив, мусить пройти гейт наново. Без цієї памʼяті опит щопівгодини
    платив би тим самим тридцяти двом тасками по запиту (заміряно 07.09).
    """
    stamp = str(task.get("updated") or "")
    if not stamp:
        return

    def write(st):
        rej = st.setdefault("rejected", {})
        rej[task_id] = stamp
        if len(rej) > REJECTED_CAP:
            for k in list(rej)[:len(rej) - REJECTED_CAP]:
                rej.pop(k, None)
        return None
    _update(write)


def rejected_before(task: dict) -> bool:
    """Чи цю таску вже відсіювали, і відтоді вона не мінялась."""
    stamp = str(task.get("updated") or "")
    if not stamp:
        return False
    return (load().get("rejected") or {}).get(task.get("id")) == stamp


def process(task_id: str, task: dict | None = None) -> dict:
    """Одна таска цілком. Публічна, щоб її можна було смикнути з тесту.

    `task` — уже дотягнута кваліфікацією: другий запит по ту саму таску був
    би платою ні за що (ліміт ClickUp — 100 запитів на хвилину).
    """
    def mark_running(st):
        t = st["tasks"].get(task_id) or {"task_id": task_id}
        t["state"] = "running"
        st["tasks"][task_id] = t
        return dict(t)
    was = _update(mark_running)

    # З коментарями: опису в цих тасках немає (0 з 12 заміряно 04.09), тож
    # єдине місце, де взагалі може бути скарга, — останній коментар.
    if task is None:
        got = clickup_client.fetch_by_ids([{"id": task_id}], with_comments=True)
        task = (got or [{}])[0]

    if task.get("no_access"):
        # Це не «немає таски», а «наш токен її не бачить» — рівно та поломка,
        # яку розбирали 04.09 (доступ до списку, не до таски). Мовчати не
        # можна: подія прийшла, отже таска існує.
        return _finish(task_id, task, "no_access",
                       "ClickUp не дає доступу до таски цим токеном", problem=True)
    if task.get("enrich_failed"):
        return _finish(task_id, task, "error", task.get("error", "")[:200],
                       problem=True)

    notice = domain_notice_of(task)
    if notice:
        return _process_domains(task_id, task, was, notice)

    # ТРІАЖ — між подією і роботою. Чеки ганяються лише по тому, що визначено
    # ТОЧНО; решта видна людині у «Проблемах» і чекає там на «Актуалізувати».
    # Один раз на таску, а не на вітку: скарга в тасці одна, а віток у неї в
    # середньому 4.7 — питати по кожній означало б платити уп'ятеро за ту саму
    # відповідь.
    tri = triage_of(task, was)
    if tri["verdict"] == cu_triage.SKIP:
        # Не наша за полями — показувати її не треба взагалі: лічильник.
        return _finish(task_id, task, "skipped", tri["reason"], triage=tri)
    if tri["verdict"] == cu_triage.MANUAL:
        # Прохання саппорта про фікс — людині, не автомату (етап 1, задача
        # 21.09.2026: «фикс идет на ручное изменение к QA-шнику»). Це не
        # помилка, тож у «Проблеми» не йде: картка у вкладці з коментарем —
        # і є робоче місце QA.
        return _finish(task_id, task, cu_triage.MANUAL, tri["reason"], triage=tri)
    if tri["verdict"] in (cu_triage.NOT_OURS, cu_triage.UNDETERMINED):
        return _finish(task_id, task, tri["verdict"], tri["reason"],
                       problem=True, triage=tri)

    branches = list(task.get("branches") or [])[:branch_max()]
    domains = list(task.get("domains") or [])
    prev = {b.get("branch"): b for b in (was.get("branches") or [])}
    extra = tri["checks"]
    # Пауза сюди НЕ заглядає: таска, яка почалась, доводиться до кінця, а
    # виконавець зупиняється перед наступною (`_loop`). Інакше вимкнення
    # лишало б таску наполовину пройденою — вітки без вироку, які нікуди не
    # повертаються самі, і «система знає, де зупинилась» перестало б бути
    # правдою.
    out = []
    for i, name in enumerate(branches):
        rec = _branch_record(name, domains[i] if i < len(domains) else "",
                             task_id, task.get("name") or "")
        out.append(_run_one(rec, prev.get(name) or {}, extra,
                            skip=skip_ids_for(task)))

    # Скарга є, а чеки мовчать — це НЕ «чисто». Кейс 07.09: у тасці лежить
    # «nwf-clomdue-alhu-br-pt не фикс, там футтер слитый», прогін дає п'ять
    # `clean`, і людина бачить зелене там, де дефект їй щойно описали словами.
    # Такий результат означає рівно одне: у лаби немає чека на цю скаргу —
    # і сказати це треба вголос, а не сховати за «чисто».
    tail = ""
    if (tri.get("router") not in ("", "fields") and out
            and all(b.get("verdict") == pipeline.CLEAN for b in out)):
        txt = " ".join((cu_triage.complaint_text(task) or "").split())
        tail = ("скарга є, а жоден чек не спрацював — дивитись очима"
                + (f": «{txt[:160]}»" if txt else ""))
    rec = _finish(task_id, task, "done", tail, branches=out, triage=tri,
                  problem=bool(tail))

    # Автокоміт — ПІСЛЯ того, як вироки записані. Порядок не косметичний:
    # якщо коміт упаде посеред пачки, у стані вже лежить, що саме лаба
    # збиралась зробити, і людина бачить це у вкладці, а не порожню картку.
    if load().get("autocommit"):
        try:
            autocommit_task(task_id)
            # Чиста таска без жодного коміту — теж «QA пройдено»: відписуємо
            # і їй. Закомічену `apply()` уже відписав сам, тож другого
            # коментаря не буде — картки просто немає.
            answer_if_passed(task_id)
            # Відписати могли й тут, і ще в `apply()` (закомічена таска) —
            # відповідь одна: картки у стані більше немає.
            cur = (load().get("tasks") or {}).get(task_id)
            rec = cur if cur else {**rec, "state": "answered"}
        except Exception:
            traceback.print_exc()
    return rec


def _process_domains(task_id: str, task: dict, was: dict, notice: dict) -> dict:
    """Саппорт змінив домени: пошта й самопосилання кожної вітки таски — на
    домени, що стоять у тасці ЗАРАЗ.

    Те саме, що людина робить руками (TECH-28368, 25.09): перепривʼязати домен
    вітки і прогнати автофікс. Але не повний QA — таска вже пофікшена, і все,
    крім пошти й доменів, у ній уже вирішили люди. Тріажу теж немає: прохань
    тут не розбираємо, повідомлення — лише подія. Прохання саппорта, якщо воно
    є поруч, звіт не закриває (`cu_triage._is_closing`), і таска прийде до
    людини наступним проходом."""
    branches = list(task.get("branches") or [])[:branch_max()]
    doms = list(task.get("domains") or [])
    prev = {b.get("branch"): b for b in (was.get("branches") or [])}
    only = domain_check_ids()
    out = []
    for i, name in enumerate(branches):
        rec = _branch_record(name, doms[i] if i < len(doms) else "",
                             task_id, task.get("name") or "")
        if not rec["domain"]:
            # Без домену фіксити нема на що: вітка лишилась би на старому, а
            # звіт сказав би «готово».
            rec.update(verdict=ERROR, ts=_now(),
                       note="у Required Domains немає домену для цієї вітки")
            out.append(rec)
            continue
        out.append(_run_one(rec, prev.get(name) or {}, only=only,
                            skip=skip_ids_for(task)))
    tri = {"verdict": cu_triage.DOMAINS, "router": "domains", "confidence": 1.0,
           "checks": [], "notice": notice,
           "reason": f"домени змінено — {notice['user']}: «{notice['text'][:160]}»"}
    rec = _finish(task_id, task, "done", "", branches=out, triage=tri)
    # Автоматика — лише з увімкненим Авто-QA (одна кнопка, 23.09.2026).
    # Вимкнене — картка лишається у вкладці, і людина комітить кнопкою; звіт
    # тоді напише `apply()`.
    if load().get("autocommit"):
        try:
            answer_domains(task_id)
            cur = (load().get("tasks") or {}).get(task_id)
            rec = cur if cur else {**rec, "state": "answered"}
        except Exception:
            traceback.print_exc()
    return rec


def _finish(task_id, task, state, reason, branches=None, problem=False,
            triage=None) -> dict:
    def write(st):
        t = st["tasks"].get(task_id) or {"task_id": task_id}
        t.update({"task_id": task_id, "state": "done" if state == "done" else state,
                  "reason": reason, "done_ts": _now(),
                  "name": task.get("name") or t.get("name") or task_id,
                  "url": task.get("url") or t.get("url") or "",
                  "status": task.get("status") or "",
                  "wtype": task.get("wtype") or "",
                  "assignees": task.get("assignees") or [],
                  "list_name": task.get("list_name") or t.get("list_name") or "",
                  "comment": ((task.get("last_comment") or {}).get("text")
                              or t.get("comment") or "")[:600],
                  "comment_user": ((task.get("last_comment") or {}).get("user")
                                   or t.get("comment_user") or ""),
                  "comments_n": len(task.get("comments") or []) or t.get("comments_n") or 0,
                  **(_card_extras(task) if task.get("comments") is not None
                     or task.get("checklist_loaded") is not None else {}),
                  "tags": task.get("tags") or t.get("tags") or [],
                  "triage": triage or t.get("triage") or {}})
        if branches is not None:
            t["branches"] = branches
        if state == "skipped":
            # Зайві таски у вкладці не показуємо ВЗАГАЛІ — лише лічильник.
            st["tasks"].pop(task_id, None)
            st["counters"]["skipped"] = int(st["counters"].get("skipped") or 0) + 1
        else:
            st["tasks"][task_id] = t
        return dict(t)
    rec = _update(write)

    rows = [{"branch": b["branch"], "domain": b.get("domain", ""),
             "source": "clickup", "reason": b.get("note") or b["verdict"],
             "task": task_id}
            for b in (branches or []) if b.get("verdict") in PROBLEM]
    if problem:
        # Рядок ПРО ТАСКУ, а не про вітку: у `not_ours` віток немає взагалі, і
        # в колонку «вітка» тут лягає назва таски. Без цієї позначки UI пропонує
        # «до вітки» і чесно не знаходить вітку з назвою таски — скарга 07.09.
        rows.append({"branch": task.get("name") or task_id, "source": "clickup",
                     "reason": reason, "task": task_id, "kind": "task",
                     "url": task.get("url") or ""})
    if rows:
        try:
            _deps["add_problems"](rows)
        except Exception:
            traceback.print_exc()
    return rec


def _loop():
    """Один виконавець. Пауза перевіряється РІВНО тут — перед тим, як узяти
    наступну таску з черги. Тобто «вимкнув» означає «доробить почате і стане»,
    а не «кине посеред роботи»."""
    while True:
        try:
            task_id = _q.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            # Кваліфікація йде НЕЗАЛЕЖНО від перемикача виконавця: «стоп»
            # гасить роботу над віткою, а не право черги знати, що в ній
            # лежить. Інакше з вимкненим виконавцем вкладка показує все
            # підряд і людина не може нею користуватись.
            task = qualify(task_id)
            if task is not None and _go.is_set():
                process(task_id, task)
        except Exception:
            traceback.print_exc()
        finally:
            _q.task_done()


def restore_queue() -> int:
    """Повертає у чергу таски, які лишились без вироку. Кличеться РІВНО на
    старті процесу (`app`), а не зі `start()`: `start()` смикає кожен
    `submit()`, і відновлення звідти повертало б у чергу все попереднє —
    заміряно живцем, три таски дали глибину шість.

    Черга в пам'яті, а стан на диску — тож рестарт процесу (деплой, падіння)
    інакше означав би тихо загублену роботу: у файлі `queued`, а виконувати
    нікому. `running` теж повертаємо: якщо процес перервали посеред таски,
    вона не дійшла до `_finish`.
    """
    back = 0
    with _q.mutex:
        waiting = set(_q.queue)
    for tid, t in (load().get("tasks") or {}).items():
        if t.get("state") in ("queued", "running") and tid not in waiting:
            _q.put(tid)
            back += 1
    return back


def start() -> None:
    """Піднімає потоки один раз на процес. Нічого не робить, доки обидва
    перемикачі вимкнені."""
    global _worker, _poller
    with _threads_lock:
        st = load()
        if st.get("run"):
            _go.set()
        if (st.get("run") or st.get("intake")) and not (_worker and _worker.is_alive()):
            _worker = threading.Thread(target=_loop, name="cu-queue", daemon=True)
            _worker.start()
        if st.get("intake") and not (_poller and _poller.is_alive()):
            _poller = threading.Thread(target=_poll_loop, name="cu-poll", daemon=True)
            _poller.start()


# --------------------------------------------------------------------------
# 5. Опит — страхувальник вебхука і єдиний вхід на деві
# --------------------------------------------------------------------------
def poll_once(limit: int = 0) -> dict:
    """Скан воркспейсу тим самим викликом, що й вкладка, і в чергу — те, що
    проходить гейт. Дорого (десятки секунд), тому раз на `CU_POLL_MIN`."""
    skipped: list = []
    tasks = clickup_client.fetch_all(include_closed=False, skipped=skipped)
    # НОМІНУЄМО по неповному правилу, а вирішує вже виконавець після
    # `fetch_by_ids`. Вʼю не віддає чеклістів, і повний гейт тут відсіяв би
    # 129 тасок зі 130 (заміряно 04.09) — опит став би порожнім.
    fit = [t for t in tasks
           if (clickup_client.looks_like_ours(t) or _domain_candidate(t))
           and not rejected_before(t)]
    if limit:
        fit = fit[:limit]
    queued = 0
    for t in fit:
        try:
            if submit(t["id"], source="poll", name=t.get("name", ""),
                      url=t.get("url", "")).get("status") == "queued":
                queued += 1
        except QueueFull:
            break

    def stamp(st):
        st["last_poll"] = _now()
        return None
    _update(stamp)
    return {"seen": len(tasks), "fit": len(fit), "queued": queued,
            "skipped_views": skipped}


def _domain_candidate(t: dict) -> bool:
    """Таска, у якій могли змінити домени: вайт-таска (`domain_gate`), що
    змінювалась за останні `CU_DOMAIN_HOURS`.

    Без цього опит такої таски не номінував би НІКОЛИ: домени міняють у вже
    пофікшених тасках, а `looks_like_ours` відкидає проставлений чекліст (з
    team-ендпоінта він відомий). Лишався б тільки вебхук — а той буває в
    `failing`, і тоді повідомлення тихо губилось би. Ціна — по запиту на
    таску, яка змінилась за добу, і то раз: відсіяну памʼятає `rejected`."""
    return (clickup_client.domain_gate(t)
            and cu_triage.fresh_ms(t.get("updated"), cu_triage.domain_hours()))


def _poll_loop():
    time.sleep(25)                       # даємо серверу піднятись
    while True:
        try:
            if load().get("intake"):
                poll_once()
        except Exception:
            traceback.print_exc()
        time.sleep(poll_minutes() * 60)


# --------------------------------------------------------------------------
# 6. Стан для вкладки
# --------------------------------------------------------------------------
def _visible(t: dict) -> bool:
    """Чи показувати таску у вкладці.

    Таска, яку ще не кваліфікували, — це поки що лише id з події чи опиту:
    ми не знаємо, чи вона наша. Показувати її не можна, і не з естетики.
    Відписана таска зникає з вкладки («чтобы не засорять вид и буфер»), але
    наш же коментар `fixed` — теж подія ClickUp, а опит раз на півгодини
    номінує її знову: «Тип вайта» таску не відсікає, а вʼю не віддає
    чеклістів. Без цієї умови вона верталась карткою «у черзі» і висіла, доки
    виконавець не дійде до неї й не відкине як уже відповідену (знайдено
    звіркою з ТЗ 23.09.2026). Лічильник `pending` каже, скільки таких чекає."""
    return t.get("state") != "queued" or bool(t.get("qualified"))


def state() -> dict:
    st = load()
    every = list((st.get("tasks") or {}).values())
    tasks = [t for t in every if _visible(t)]
    tasks.sort(key=lambda t: t.get("ts") or "", reverse=True)
    counts: dict = {}
    for t in tasks:
        for b in t.get("branches") or []:
            v = b.get("verdict") or "queued"
            counts[v] = counts.get(v, 0) + 1
    return {"enabled": enabled(), "on": is_on(st),
            "intake": bool(st.get("intake")),
            "run": bool(st.get("run")),
            "autocommit": bool(st.get("autocommit")),
            "autocommit_max": autocommit_max(), "depth": _q.qsize(),
            "pending": len(every) - len(tasks),
            "tasks": tasks, "counts": counts,
            "counters": st.get("counters") or {},
            "last_event": st.get("last_event") or "",
            "last_poll": st.get("last_poll") or "",
            "poll_min": poll_minutes(), "max": queue_max()}


def reclassify() -> dict:
    """«Актуалізувати помилкові таски» — перебрати те, що ЛЕЖИТЬ У ПРОБЛЕМАХ,
    і перекласти в чергу все, що тепер визначено точно.

    Джерело правди тут — саме журнал проблем, а не стан таски у черзі. Це не
    дрібниця: стан минущий. Знайдено живим прогоном 04.09 — фоновий опит
    устиг перевести таску назад у `queued`, і кнопка чесно відповіла
    «дивитись нема на що», хоча рядок помилки лежав перед очима людини.

    Навіщо кнопка, а не фон: вирок міняє не час, а людина — новий скіл,
    правка слів у картці, заведений `ANTHROPIC_API_KEY`. Фоновий перебір
    платив би моделлю за ті самі таски щогодини і нічого не міняв.

    Беремо лише те, що поставив ТРІАЖ (`not_ours` / `undetermined`). Рядки
    про зниклу вітку чи невдалий фікс — інший рід проблеми, і для них поруч
    уже є «Спробувати sync ще раз».

    Успішне перенесення прибирає рядок з «Проблем»: інакше та сама таска
    висіла б одночасно як помилка і як робота.
    """
    try:
        rows = _deps["load_problems"]()
    except Exception:
        traceback.print_exc()
        return {"looked": 0, "moved": 0, "tasks": []}

    tasks_state = load().get("tasks") or {}
    ids, seen = [], set()
    for r in rows:
        tid = (r.get("task") or "").strip()
        if r.get("source") != "clickup" or not tid or tid in seen:
            continue
        was = (tasks_state.get(tid) or {}).get("triage") or {}
        # Без запису тріажу теж беремо: рядок міг пережити рестарт.
        if was.get("verdict") in (cu_triage.NOT_OURS, cu_triage.UNDETERMINED, None):
            seen.add(tid)
            ids.append(tid)
    if not ids:
        return {"looked": 0, "moved": 0, "tasks": []}

    got = clickup_client.fetch_by_ids([{"id": i} for i in ids], with_comments=True)
    by_id = {t.get("id"): t for t in got if t.get("id")}
    moved, out = 0, []
    for tid in ids:
        task = by_id.get(tid) or {}
        if not task or task.get("no_access") or task.get("enrich_failed"):
            out.append({"task_id": tid, "verdict": "error",
                        "reason": "таску не вдалось перечитати"})
            continue
        tri = cu_triage.classify(task)
        if tri["verdict"] != cu_triage.OURS:
            # Лишається помилкою — але зі СВІЖОЮ причиною: вона могла
            # змінитись («не знаю» -> «не наше»), і людині це видно.
            def keep(s, _tid=tid, _tri=tri, _task=task):
                t = (s.get("tasks") or {}).setdefault(_tid, {"task_id": _tid})
                t.update(state=_tri["verdict"], reason=_tri["reason"],
                         triage=_tri, done_ts=_now(),
                         name=_task.get("name") or t.get("name") or _tid,
                         url=_task.get("url") or t.get("url") or "")
                return None
            _update(keep)
            out.append({"task_id": tid, "verdict": tri["verdict"],
                        "reason": tri["reason"]})
            continue

        def promote(s, _tid=tid, _tri=tri):
            t = (s.get("tasks") or {}).get(_tid)
            if t:
                t["triage"] = _tri
            return None
        _update(promote)
        try:
            _deps["drop_problems"](lambda x, _tid=tid: (
                x.get("source") == "clickup" and x.get("task") == _tid))
        except Exception:
            traceback.print_exc()
        submit(tid, source="reclassify", name=task.get("name", ""),
               url=task.get("url", ""), force=True)
        moved += 1
        out.append({"task_id": tid, "verdict": cu_triage.OURS,
                    "reason": tri["reason"]})
    return {"looked": len(ids), "moved": moved, "tasks": out}


# --------------------------------------------------------------------------
# 6b. Пачка: єдине місце, яке пише назовні
# --------------------------------------------------------------------------
DEFAULT_MESSAGE = "fix: автовиправлення перевірок"


def apply(items: list, message: str = "", comment: bool = True,
          checklist: bool = True, machine: bool = False) -> dict:
    """Закомітити обране і сказати про це в ClickUp.

    `items` — [{"task_id": ..., "branches": [...]}]; порожній список віток
    означає «усі, яким є що комітити».

    Три правила, які тут головні:

    1. **Фікси рахуються НАНОВО.** Між прогоном і натисканням вітка могла
       поїхати, і класти в коміт вчорашній результат означало б обіцяти одне,
       а зробити інше. Це і є контракт Preview → Apply, а не оптимізація.
    2. **Відмова однієї вітки не валить пачку** — рядок з причиною, решта йде
       далі. Причину показуємо повністю: `717c322` уже навчив відмову коміту
       казати ЧОМУ.
    3. **У ClickUp — один коментар на таску і лише про успіх.** Про
       `no_fix`, `error`, `gone` фронтам не пишемо нічого: для них це шум,
       діяти по цьому нам, а ми дивимось у лабу.
    """
    msg = (message or "").strip() or DEFAULT_MESSAGE
    report = []
    for item in items:
        task_id = (item.get("task_id") or "").strip()
        st = load()
        task = (st.get("tasks") or {}).get(task_id)
        if not task:
            report.append({"task_id": task_id, "error": "таски немає у черзі"})
            continue
        want = set(item.get("branches") or [])
        rows, committed = [], 0
        for b in task.get("branches") or []:
            if want and b["branch"] not in want:
                continue
            if b.get("verdict") != pipeline.WOULD_FIX:
                continue
            rows.append(_apply_branch(b, msg, machine=machine))
            committed += 1 if rows[-1].get("commit") else 0

        def write(s, _tid=task_id, _rows=rows):
            t = (s.get("tasks") or {}).get(_tid)
            if not t:
                return None
            done = {r["branch"]: r for r in _rows if r.get("commit")}
            for b in t.get("branches") or []:
                r = done.get(b["branch"])
                if r:
                    b.update(verdict=APPLIED, commit=r["commit"],
                             applied_ts=_now(), files=len(r.get("files") or []))
            return None
        _update(write)
        if (task.get("triage") or {}).get("verdict") == cu_triage.DOMAINS:
            # Після зміни доменів відповідь — звіт про домени, а не «fixed»:
            # таску вже пофікшено раніше, і чекліст тут ні до чого, навіть
            # коли комітить людина.
            told = report_domains(task_id, rows) if comment else ""
        else:
            # У ClickUp пишемо, лише коли QA ВСІЄЇ таски пройдено (етап 1,
            # 21.09.2026: «когда QA по всем вайтам пройдено … пишется
            # коммент»). Коміт частини віток таску не завершує. Невдалий запис
            # коміту не відкочує — кажемо про нього в звіті. Відповідь та сама,
            # що в кнопки «✔ чекліст + fixed», — і в людини, і в автокоміту
            # (`machine`): див. `answer_if_passed`.
            told = (answer_if_passed(task_id, checklist=checklist)
                    if comment and committed else "")
        report.append({"task_id": task_id, "committed": committed,
                       "branches": rows, "clickup": told})
    return {"message": msg, "tasks": report}


def qa_passed(t: dict) -> bool:
    """QA кожної вітки таски пройдено (див. `PASSED`)."""
    brs = t.get("branches") or []
    return bool(brs) and all(b.get("verdict") in PASSED for b in brs)


def _answered(task_id: str) -> None:
    """Картка зникає з вкладки («чтобы не засорять вид и буфер»)."""
    def drop(st):
        st["tasks"].pop(task_id, None)
        c = st.setdefault("counters", {})
        c["answered"] = int(c.get("answered") or 0) + 1
    _update(drop)


def answer_if_passed(task_id: str, checklist: bool = True) -> str:
    """QA по всіх вітках пройдено → чекліст whites і коментар `fixed` у
    таску, картка зникає з вкладки — до нового коментаря
    (`cu_triage.already_answered`).

    Відповідь одна — і в людини («Закомітити обране»), і в автоматики
    (автокоміт, «Авто-QA» увімкнене): рівно те, що кнопка «✔ чекліст + fixed»
    у вкладці ClickUp. Розрізняє їх лише підпис: «… by Ім'я» — це людина.

    Чому автоматика ставить чекліст (рішення юзера 29.09.2026). З 23.09 вона
    писала ЛИШЕ коментар, а галку лишала людям — і люди відписували ті самі
    таски вдруге: вкладка ClickUp показує таску, доки чекліст не стоїть, тож
    «fixed» автоматики там нічого не закривав. Заміряно 29.09 на вʼю: з 28.09
    17:15 автоматика відписала 29 тасок, у 27 з них колега поставив «fixed»
    удруге (19 — одним натиском масової кнопки о 11:52), у двох (TECH-28500,
    -28501) галку поставили руками в самому ClickUp («не ставит галку» —
    скарга того ж дня). «Тип вайта» і статус лаба, як і досі, не чіпає
    ніколи; звіт про зміну доменів і ШІ-міст — лише коментар.

    Повертає "ok" (відписано), "" (ще не пройдено — нічого не писали) або
    причину, з якою ClickUp не прийняв запис; картка тоді лишається, щоб
    людина бачила, що відповіді в тасці немає.

    Таску зі скаргою, на яку жоден чек не спрацював (`reason` у картці), не
    відписуємо ніколи: «чисто» там — це «лабі нема чим», а не «пройдено».
    """
    t = (load().get("tasks") or {}).get(task_id)
    if not t or t.get("state") != "done" or t.get("reason") or not qa_passed(t):
        return ""
    try:
        clickup_client.complete_task(task_id, comment="fixed", checklist=checklist)
    except Exception as e:
        return f"коментар не пройшов: {str(e)[:160]}"
    _answered(task_id)
    return "ok"


# --------------------------------------------------------------------------
# 6c. Зміна доменів: коміт і звіт (25.09.2026)
# --------------------------------------------------------------------------
# Повідомлення коміту. Початок — той самий, що в автофікса: за ним
# `stats_backfill.ACTIONS` відносить коміт до `autofix`; хвіст каже, чому.
DOMAINS_MESSAGE = "fix: автовиправлення перевірок — пошта на нові домени"
# Прогін після зміни доменів пройдено. `no_fix` тут НЕ «пройдено», на відміну
# від повного QA: пошта на старому домені — рівно той дефект, заради якого
# прогін, і чек, що його бачить і не лагодить, — привід для людини.
DOMAINS_PASSED = {pipeline.CLEAN, UNCHANGED, APPLIED}
# Чому вітку не виправлено — словами для таски (звіт іде в ClickUp
# російською, як і все, що там пишуть саппорт і фронти).
_WHY_RU = {GONE: "ветки нет в GitLab", PROTECTED: "ветка защищена",
           DIRTY: "в снимке чужие локальные правки", ERROR: "сбой",
           pipeline.NO_FIX: "автофикса нет", pipeline.NOT_READY: "снимок ещё не готов",
           pipeline.WOULD_FIX: "не закоммичено"}


def answer_domains(task_id: str) -> str:
    """Автоматика після зміни доменів: закомітити фікси і написати звіт.

    Коміт — тим самим `apply()`, що кнопка й автокоміт (підпис, Журнал,
    групи, стеля `CU_AUTOCOMMIT_MAX`); звіт після коміту пише вже він. Коли
    комітити нічого, звіт однаково пишемо — «уже на нових доменах» теж
    відповідь: без неї саппорт не знає, чи лаба взагалі бачила повідомлення."""
    t = (load().get("tasks") or {}).get(task_id) or {}
    ready = [b["branch"] for b in (t.get("branches") or [])
             if b.get("verdict") == pipeline.WOULD_FIX]
    if not ready:
        return report_domains(task_id, [])
    got = apply([{"task_id": task_id, "branches": ready[:autocommit_max()]}],
                message=DOMAINS_MESSAGE, machine=True)
    return (got.get("tasks") or [{}])[0].get("clickup", "")


def domains_report(branches: list, rows: list, moved: list | None = None) -> str:
    """Текст звіту в таску — чиста функція, щоб формат перевірявся без мережі.

    `branches` — рядки картки (вироки прогону), `rows` — що дав коміт
    (`_apply_branch`), `moved` — старий домен вітки, коли лаба його знала
    (`cu_triage.moved_domains`). Перше слово — `cu_triage.DOMAIN_REPORT_HEAD`:
    за ним тріаж упізнає звіт і не приймає повідомлення про домени вдруге."""
    done = {r["branch"]: r for r in rows if r.get("commit")}
    same = {r["branch"] for r in rows if r.get("nothing")}
    failed = {r["branch"]: r for r in rows
              if r.get("error") and not r.get("nothing")}
    # Ключ без регістру: у тасці вітку вписує людина, а в рядку картки стоїть
    # справжня назва з GitLab (`resolve_in`).
    was = {m["branch"].lower(): m["old"] for m in moved or []}
    lines, fixed, bad = [], 0, 0
    for b in branches:
        name, dom, v = b.get("branch", ""), b.get("domain", ""), b.get("verdict", "")
        old = was.get(name.lower())
        head = (f"{name}: {old} → {dom}" if old and dom
                else f"{name} → {dom}" if dom else name)
        if name in done or v == APPLIED:
            n = (len((done.get(name) or {}).get("files") or [])
                 or int(b.get("files") or 0))
            lines.append(f"{head}: исправлено (файлов: {n})")
            fixed += 1
        elif name in same or v in (pipeline.CLEAN, UNCHANGED):
            lines.append(f"{head}: уже на новом домене")
        else:
            bad += 1
            err = (failed.get(name) or {}).get("error") or ""
            why = ("нет домена в Required Domains" if not dom
                   else _WHY_RU.get(v, v or "не проверено"))
            lines.append(f"{head}: не исправлено — {why}"
                         + (f" ({err[:120]})" if err else ""))
    if bad:
        first = "не все ветки удалось перевести на новые домены — нужен человек."
    elif fixed:
        first = "почты и ссылки вайтов переведены на новые домены."
    else:
        first = "почты и ссылки вайтов уже на новых доменах, правки не понадобились."
    return "\n".join([f"{cu_triage.DOMAIN_REPORT_HEAD} {first}"] + lines)


def report_domains(task_id: str, rows: list) -> str:
    """Звіт у таску після зміни доменів — ЛИШЕ коментар («лаба в ClickUp лише
    коментує», 23.09.2026): ні чекліста, ні «fixed», ні статусу. Тегаємо
    автора повідомлення — він спитав, йому й відповідь. Крім бот-акаунта:
    автоматизація саппорта може постити фразу від бота (`ClickBot`), а тег
    бота не сповіщає нікого — тоді звіт без тегу, його бачать усі в тасці.

    Усе виправлено — картка зникає з вкладки, як після «fixed». Ні — звіт
    однаково йде (у ньому сказано, що саме лишилось), а картка й рядки у
    «Проблемах» лишаються людині."""
    t = (load().get("tasks") or {}).get(task_id) or {}
    notice = (t.get("triage") or {}).get("notice") or {}
    branches = t.get("branches") or []
    who = notice.get("user") or ""
    person = bool(who) and "bot" not in who.lower()
    try:
        clickup_client.complete_task(task_id,
                                     comment=domains_report(branches, rows,
                                                            notice.get("moved")),
                                     checklist=False,
                                     tag_user_id=(notice.get("user_id") or None) if person else None,
                                     tag_username=who if person else "")
    except Exception as e:
        why = f"звіт про зміну доменів не пройшов: {str(e)[:160]}"
        try:
            _deps["add_problems"]([{"branch": t.get("name") or task_id,
                                    "source": "clickup", "reason": why,
                                    "task": task_id, "kind": "task",
                                    "url": t.get("url") or ""}])
        except Exception:
            traceback.print_exc()
        return why
    same = {r["branch"] for r in rows if r.get("nothing")}
    if all(b.get("verdict") in DOMAINS_PASSED or b.get("branch") in same
           for b in branches):
        _answered(task_id)
        return "ok"
    problems = [{"branch": r["branch"], "source": "clickup", "task": task_id,
                 "reason": f"коміт після зміни доменів не пройшов: {r['error']}"}
                for r in rows if r.get("error") and not r.get("nothing")]
    if problems:
        try:
            _deps["add_problems"](problems)
        except Exception:
            traceback.print_exc()

    def mark(st, _tid=task_id):
        cur = (st.get("tasks") or {}).get(_tid)
        if cur:
            cur["reason"] = "домени змінено: частину віток не виправлено — див. рядки нижче"
        return None
    _update(mark)
    return "ok"


def autocommit_task(task_id: str) -> dict:
    """Коміт без людини — тим самим шляхом, що й кнопка.

    Свідомо НЕ окремий конвеєр: коміт, підпис, коментар у ClickUp і запис у
    Журнал мусять бути буква в букву тими самими, що й у ручному Apply.
    Інакше «автоматом» і «руками» з часом розійдуться, і в історії вітки
    буде видно, чим саме її правили — а це не має значення ні для кого.

    Обмежень рівно три, і кожне має причину:

    * **лише групи, що ганялись** (`auto`+`tests`, ніколи `review`) — див.
      `_apply_branch`;
    * **стеля на таску** (`CU_AUTOCOMMIT_MAX`) — поганий фікс однаково поганий
      на всіх вітках, і без стелі один прогін розкладе його на всю таску;
    * **усе, що не вийшло, іде в «Проблеми»** — автомат мовчить лише про
      успіх. Тиша про відмову і є те, через що потім не знайти, коли саме
      зламалось.
    """
    st = load()
    t = (st.get("tasks") or {}).get(task_id) or {}
    ready = [b["branch"] for b in (t.get("branches") or [])
             if b.get("verdict") == pipeline.WOULD_FIX]
    if not ready:
        return {"committed": 0, "left": 0}

    cap = autocommit_max()
    picked, left = ready[:cap], ready[cap:]
    got = apply([{"task_id": task_id, "branches": picked}], machine=True)
    rows = ((got.get("tasks") or [{}])[0].get("branches") or [])
    done = [r for r in rows if r.get("commit")]

    problems = [{"branch": r["branch"], "source": "clickup", "task": task_id,
                 "reason": f"автокоміт не пройшов: {r['error']}"}
                for r in rows if r.get("error")]
    if left:
        problems.append({"branch": t.get("name") or task_id, "source": "clickup",
                         "task": task_id, "kind": "task", "url": t.get("url") or "",
                         "reason": f"автокоміт узяв {cap} віток зі стелі, "
                                   f"лишилось {len(left)} — доробити кнопкою"})
    if problems:
        try:
            _deps["add_problems"](problems)
        except Exception:
            traceback.print_exc()

    if done:
        def bump(s):
            c = s.setdefault("counters", {})
            c["committed"] = int(c.get("committed") or 0) + len(done)
            return None
        _update(bump)
        print(f"[queue] автокоміт {task_id}: {len(done)} віток", flush=True)
    return {"committed": len(done), "left": len(left),
            "clickup": (got.get("tasks") or [{}])[0].get("clickup", "")}


def _apply_branch(b: dict, msg: str, machine: bool = False) -> dict:
    """Одна вітка. `machine` — коміт без людини: тоді беремо фікси лише тих
    груп, що ганялись (`groups()`: `auto`+`tests`), і ніколи `review`.

    До 21.09.2026 автомат брав ЛИШЕ `auto` (рішення 07.09). Колега-QA того дня
    сказала прямо: «QA проходится автоматически, по всем тестам. И заливается
    в гит фиксы», — і на скріні кроку QA галки Автотести ✓ Тести ✓, а
    «🔧 Автофікс» бере ВСІ відмічені чеки. Тобто людина цими кнопками заливає
    фікси обох груп, і автомат робить рівно те саме. `review` лишається поза
    ним: там два чеки дають error на 100% і 94% прогонів.
    """
    branch, pid = b["branch"], b.get("project") or projects.current_id()
    out = {"branch": branch, "commit": "", "files": [], "error": ""}
    try:
        with projects.use(pid), runner.pipeline_lock:
            # Клієнт беремо ЗАГАЛЬНИЙ (`app.client`): він проксі до активного
            # проєкту — а активний тут задає `projects.use` — і він же
            # дописує підпис лаби у повідомлення коміту.
            cl = _deps["client"]
            try:
                runner.sync_branch(cl, branch)
            except Exception:
                if not runner.is_synced(branch):
                    raise
            fixable = b.get("fixable") or None
            if machine:
                # Групи питаємо в контексті ПРОЄКТА вітки: набір чеків у php і
                # node різний, і глобальний список тут збрехав би.
                by_id = {c["id"]: c.get("group")
                         for c in runner.checks_for_active_project()}
                fixable = [f for f in (b.get("fixable") or [])
                           if by_id.get(f) in groups()]
                if not fixable:
                    out["error"] = ("автокоміт не бере: фікси цієї вітки поза "
                                    "групами, що ганялись")
                    return out
            changes = runner.compute_fixes(branch, fixable)
            if not changes:
                out["error"] = "перерахунок нічого не змінив — коміту немає"
                # Між прогоном і комітом вітку вже виправили (людина встигла
                # раніше) — для звіту про домени це «уже на новому», а не збій.
                out["nothing"] = True
                return out
            r = cl.commit(branch, msg, runner.actions_for(changes))
            runner.apply_to_snapshot(branch, changes)
            out["commit"] = r.get("id", "")
            out["files"] = [c["path"] for c in changes]
            _deps["log_commit"](branch, msg, out["commit"], out["files"],
                                action="autofix")
    except Exception as e:
        out["error"] = str(e)[:300]
        print(f"[queue] {branch}: коміт не пройшов — {e}", flush=True)
    return out


# --------------------------------------------------------------------------
# 7. Ендпоінти (усі під сесійним гейтом — окремого винятку тут немає)
# --------------------------------------------------------------------------
router = APIRouter()


@router.get("/api/queue")
def api_state():
    return state()


class SwitchRequest(BaseModel):
    # Одна кнопка — одне поле (`set_auto`). Окремих прийому, виконавця й
    # автокоміту назовні більше немає: змішаний стан UI показати не вміє.
    on: bool


@router.post("/api/queue/switch")
def api_switch(req: SwitchRequest):
    if not enabled():
        raise HTTPException(400, "чергу вимкнено змінною CU_QUEUE_ENABLED")
    return set_auto(req.on)


@router.post("/api/queue/run")
def api_run(limit: int = 0):
    """«Прогнати зараз» — той самий опит, що й фоновий, але руками.

    Межа є навмисно: перший прохід по всьому корпусу тягне 615 знімків, і
    натиснути це випадково не має коштувати два гігабайти.
    """
    if not load().get("intake"):
        raise HTTPException(400, "прийом вимкнено — увімкни його кнопкою")
    return poll_once(limit=limit)


@router.post("/api/queue/clear")
def api_clear():
    """Прибрати з черги все, крім таски, що виконується просто зараз.

    Потрібна після зміни правила відбору: у черзі лишаються таски,
    номіновані СТАРИМ правилом, і без цієї кнопки їх довелось би або
    видаляти поштучно, або чекати, поки виконавець дотягне кожну і відкине
    (це запит у ClickUp на кожну — 100 запитів при ліміті 100/хв).

    Чергу в пам'яті спорожнюємо ПУБЛІЧНИМ API (`get_nowait` + `task_done`),
    а не правкою `_q.queue`: інакше лічильник незавершених піде в мінус і
    наступний `task_done()` кине виняток у потоці виконавця.
    """
    dropped_q = 0
    while True:
        try:
            _q.get_nowait()
        except queue.Empty:
            break
        _q.task_done()
        dropped_q += 1

    def drop(st):
        tasks = st.get("tasks") or {}
        keep = {k: v for k, v in tasks.items() if v.get("state") == "running"}
        n = len(tasks) - len(keep)
        st["tasks"] = keep
        return n
    return {"dropped": _update(drop), "from_queue": dropped_q}


@router.delete("/api/queue/{task_id}")
def api_drop(task_id: str):
    def drop(st):
        return bool(st["tasks"].pop(task_id, None))
    return {"dropped": _update(drop)}


class ApplyItem(BaseModel):
    task_id: str
    branches: list[str] = []


class ApplyRequest(BaseModel):
    items: list[ApplyItem]
    message: str = ""
    comment: bool = True
    checklist: bool = True


@router.post("/api/queue/apply")
def api_apply(req: ApplyRequest):
    if not req.items:
        raise HTTPException(400, "не обрано жодної таски")
    return apply([i.model_dump() for i in req.items], message=req.message,
                 comment=req.comment, checklist=req.checklist)


@router.post("/api/queue/reclassify")
def api_reclassify():
    return reclassify()
