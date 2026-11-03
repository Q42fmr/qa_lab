"""ClickUp API v2: pulls tasks whose "Safe Page" custom field lists branch names.

Fetches EVERY task the token can see (team-wide, incl. shared lists). No
server-side filtering — the UI decides what to show via checkboxes.

.env:
    CLICKUP_TOKEN            personal API token (pk_...), Settings -> Apps -> API Token
    CLICKUP_TEAM_ID          optional; auto-detected from the token if empty
    CLICKUP_FIELD            field with branch names          (default: safe page)
    CLICKUP_DOMAINS_FIELD    field with domains, same order    (default: required domains)
    CLICKUP_WTYPE_FIELD      "white type" field to gate on    (default: тип вайта)
    CLICKUP_CHECKLIST        checklist name to inspect         (default: whites)
    CLICKUP_STATUSES         statuses treated as "active"      (default: to do,in progress)
    CLICKUP_STATUSES_EXCLUDE status substrings to reject       (default: content)

Each task is annotated (status_match, wtype, assignees, checklist_done,
branches, ...) so the UI can filter on any combination.
"""

from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "https://api.clickup.com/api/v2"


def _get(url: str, headers: dict, params: dict | None = None, timeout: int = 60):
    """GET з повторами після 429 (rate limit ClickUp — 100 запитів/хв).
    До 3 спроб; сон обмежений 60 с, щоб батч не зависав на довгих Retry-After."""
    r = requests.get(url, headers=headers, params=params, timeout=timeout)
    for _ in range(2):
        if r.status_code != 429:
            break
        time.sleep(min(float(r.headers.get("Retry-After", 30)), 60) + 1)
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
    return r


def _cfg(token: str = "") -> dict:
    """Конфіг джерел. `token` порожній — беремо застосунковий з оточення.

    Явний токен потрібен для ОСОБИСТОГО скану: токен ClickUp завжди належить
    людині («безособових» там немає), тож таски, розшарені комусь персонально,
    видно лише з-під нього.
    """
    return {
        "token": (token or "").strip() or os.getenv("CLICKUP_TOKEN", "").strip(),
        "views": [s.strip() for s in os.getenv("CLICKUP_VIEW_ID", "").split(",") if s.strip()],
        "lists": [s.strip() for s in os.getenv("CLICKUP_LIST_ID", "").split(",") if s.strip()],
        "field": os.getenv("CLICKUP_FIELD", "safe page").strip().lower(),
        "domains_field": os.getenv("CLICKUP_DOMAINS_FIELD", "required domains").strip().lower(),
        "wtype_field": os.getenv("CLICKUP_WTYPE_FIELD", "тип вайта").strip().lower(),
        "checklist": os.getenv("CLICKUP_CHECKLIST", "whites").strip().lower(),
        "statuses": {s.strip().lower() for s in
                     os.getenv("CLICKUP_STATUSES", "to do,in progress").split(",") if s.strip()},
        # статуси, що містять ці підрядки, не матчаться ('content to do' ≠ 'to do')
        "status_exclude": {s.strip().lower() for s in
                           os.getenv("CLICKUP_STATUSES_EXCLUDE", "content").split(",") if s.strip()},
        # теги, які означають «це не вайт»: блек — інша сторінка і інша робота,
        # у неї немає ні Safe Page, ні доменів, і чеки лаби до неї не стосуються
        "tags_exclude": {s.strip().lower() for s in
                         os.getenv("CLICKUP_TAGS_EXCLUDE", "blacks").split(",") if s.strip()},
    }


def _norm(s: str) -> str:
    """'Safe Page' == 'safePage' == 'safe_page' — порівнюємо без регістру і
    розділювачів; кирилиця зберігається ('Тип вайта' -> 'типвайта')."""
    return re.sub(r"[\W_]+", "", (s or "").lower())


def _cf_readable(f: dict) -> str:
    """Читабельне значення dropdown/labels-поля (id опції -> її назва)."""
    val = f.get("value")
    opts = {}
    for o in (f.get("type_config") or {}).get("options") or []:
        label = o.get("label") or o.get("name") or ""
        opts[o.get("id")] = label
        if o.get("orderindex") is not None:
            opts[o.get("orderindex")] = label
    if isinstance(val, list):
        return ", ".join(str(opts.get(v, v)) for v in val)
    return str(opts.get(val, val))


def _parse_domains(val) -> list[str]:
    """Поле Required Domains: домени через новий рядок/кому, У ТОМУ Ж ПОРЯДКУ,
    що й вітки в Safe Page (1-й домен ↔ 1-ша вітка) — порядок зберігається.
    Схема/шлях відкидаються, невалідні рядки пропускаються."""
    if not isinstance(val, str):
        return []
    out = []
    for s in re.split(r"[\n,;]+", val):
        s = re.sub(r"^https?://", "", s.strip().lower())
        s = s.split("/")[0].strip().rstrip(".")
        if s and re.fullmatch(r"[a-z0-9.\-]+\.[a-z]{2,}", s):
            out.append(s)
    return out


def _team_id(headers: dict) -> str:
    tid = os.getenv("CLICKUP_TEAM_ID", "").strip()
    if tid:
        return tid
    r = requests.get(f"{BASE}/team", headers=headers, timeout=30)
    r.raise_for_status()
    teams = r.json().get("teams", [])
    if not teams:
        raise ValueError("токен не має доступу до жодного workspace")
    return teams[0]["id"]


def _parse(t: dict, cfg: dict) -> dict:
    status = (t.get("status") or {}).get("status", "").lower()

    checklist_found = False
    checklist_done = False
    for cl in t.get("checklists") or []:
        if _norm(cfg["checklist"]) in _norm(cl.get("name")):
            checklist_found = True
            items = cl.get("items") or []
            checklist_done = bool(items) and all(i.get("resolved") for i in items)

    tags = [(x.get("name") or "").strip().lower() for x in (t.get("tags") or [])]

    branches: list[str] = []
    domains: list[str] = []
    wtype = None
    fields_seen: list[str] = []
    for f in t.get("custom_fields") or []:
        fields_seen.append(f.get("name") or "?")
        if _norm(cfg["field"]) in _norm(f.get("name")):
            val = f.get("value")
            if isinstance(val, str):
                # вітка = токен без пробілів/кирилиці; рядки-інструкції відкидаємо
                branches = [s.strip() for s in re.split(r"[\n,]+", val)
                            if s.strip() and re.fullmatch(r"[A-Za-z0-9._/\-]+", s.strip())]
        elif _norm(cfg["domains_field"]) in _norm(f.get("name")):
            domains = _parse_domains(f.get("value"))
        elif _norm(cfg["wtype_field"]) in _norm(f.get("name")):
            if f.get("value") not in (None, "", []):
                wtype = _cf_readable(f)

    return {
        "id": t["id"],
        "name": t.get("name", ""),
        "url": t.get("url", ""),
        # Опис потрібен машині, а не екрану: це єдине місце (поряд з останнім
        # коментарем), де в тасці взагалі буває СКАРГА, а не службова нотатка.
        # Обрізаємо тут, щоб довгий опис не роздував ані стан, ані відповідь.
        "description": (t.get("description") or t.get("text_content") or "")[:4000],
        "status": status,
        "status_type": (t.get("status") or {}).get("type", ""),
        # ms-таймстемп закриття (для статистики закритих тасок)
        "date_closed": t.get("date_closed") or t.get("date_done") or None,
        # кастомні статуси типу 'front to do' матчимо по підрядку,
        # але 'content to do' відсіюється списком винятків
        "status_match": (any(s in status for s in cfg["statuses"])
                         and not any(x in status for x in cfg["status_exclude"])),
        "tags": tags,
        # Тег-виняток рахуємо ТУТ, поруч зі `status_match`, а не в кожного
        # споживача: тоді і сервер, і вкладка судять про таску однаково.
        "tag_excluded": bool(set(tags) & cfg["tags_exclude"]),
        # мітка останньої зміни: за нею черга розуміє, що таску, яку вже
        # відсіяли, перепитувати нема сенсу
        "updated": str(t.get("date_updated") or ""),
        "list_name": (t.get("list") or {}).get("name", ""),
        "assignees": [a.get("username") or a.get("email") or "?"
                      for a in t.get("assignees") or []],
        "wtype": wtype,
        "checklist_found": checklist_found,
        "checklist_done": checklist_done,
        "branches": branches,
        "domains": domains,     # той самий порядок, що й branches (i-й ↔ i-й)
        "fields_seen": fields_seen,
    }


# Скільки сторінок одного джерела читаємо одночасно.
#
# Заміряно 01.09.2026 на робочому воркспейсі (445 тасок): вʼю віддає сторінку за
# ~6.4 с і рівно по 30 тасок, тож вʼю всього воркспейсу `8abcd12-34567`
# (382 таски, 13 сторінок) коштувало 83 с із 99 с усього виклику. Перед лабою
# стоїть Cloudflare, який рве похід до origin на 100 с, — вкладка ClickUp у
# проді віддавала 502 з ЙОГО html-сторінкою, а не нашим json, тож причина не
# була видна ні в логах, ні з коду: локально виклик укладався в 99 с, рівно на
# межі.
#
# Фільтрами це не лікується: `/view/{id}/task` приймає ЛИШЕ `page` — перевірено
# 01.09, з `date_updated_gt`, `statuses[]` і `subtasks` він віддає той самий
# набір до таски. Фільтри розуміє тільки team-ендпоінт, а він і так 11 с.
#
# Перша хвиля навмисно в ОДНУ сторінку: вʼю бувають і на 9 тасок, і на 382, а
# скільки їх — API не каже наперед. Пробна сторінка відрізняє мале вʼю (один
# запит замість шістнадцяти) від великого, після чого решта йде однією
# широкою хвилею.
VIEW_FIRST, VIEW_WAVE = 1, 16
# team-ендпоінт віддає по 100 тасок на сторінку, і воркспейс цілком лягає в
# одну хвилю з п'яти — пробна сторінка тут лише додала б зайвий круг.
TEAM_WAVE = 5


def passes_default_filters(t: dict) -> bool:
    """Чи це «наша» таска — те саме правило, яке бачить людина у вкладці
    ClickUp, коли щойно відкрила її і нічого не чіпала.

    Галки у вкладці не зберігаються ніде, тож кожне відкриття починається з
    дефолтів розмітки (`static/index.html`): Safe Page ✔, «Тип вайта» ✔,
    чекліст не проставлений ✔, статус ✔, закриті ✘. Плюс умова самої кнопки
    імпорту — чекліст довантажено. Гарда, яка тримає правило зчепленим з
    розміткою, — `tests/test_cu_qualify.py`: щойно дефолт галки змінили, а
    правило ні, вона падає.

    **Статус перевіряється з 07.09.2026** — рішення замовника після першого
    живого прогону черги. Доти його свідомо не було, і саме через це в чергу
    приїхали таски у статусах `qa` і `domains hold` («таке не має брати», «в
    QA теж не надо»). Заміряно того ж дня на живому воркспейсі: без статусу
    номінується 128 тасок (645 віток), зі статусом — 70 (350); відпадає рівно
    58 = `qa` (40) + `domains hold` (18), лишається `in progress` (53) і
    `to do` (17). Умова одна — `status_match`, тобто той самий підрядковий
    матч по `CLICKUP_STATUSES` мінус `CLICKUP_STATUSES_EXCLUDE`, що показує
    галка «лише to do / in progress (без content)».

    `checklist_done` — не фільтр статусу, а власна позначка лаби «ми тут уже
    були»; сьогодні вона коштує рівно одну таску зі 131.

    ⚠️ Це НЕ те саме правило, що `tg_watcher.passes_filters`, і зводити їх не
    можна: вотчер — код Олександра, він сповіщає у Telegram про згадки і
    свідомо дивиться вужче (зі `status_match`). Злиття мовчки змінило б його
    сповіщення з 74 тасок на 130.
    """
    return looks_like_ours(t) and t.get("checklist_loaded") is not False


def looks_like_ours(t: dict) -> bool:
    """Те саме правило, але без умови про чекліст — рівно те, що можна
    вирішити ЗІ СПИСКУ.

    Різниця не косметична. Заміряно 04.09.2026 на живому воркспейсі: зі
    скану проходять «схоже на нашу» **130** тасок, а повний гейт — **одна**.
    Причина в тому, що вʼю не віддає чеклістів узагалі (`checklist_loaded`
    там `False`), а 129 зі 130 приходять саме з вʼю. Тобто номінувати по
    повному гейту означало б не побачити майже нічого.

    Тому ролі різні: цим фільтром **номінують** (скан, опит), а вирішує вже
    повний гейт — після того як таску дотягнули поштучно і чекліст відомий.

    Статус тут є (з 07.09.2026), бо він приходить уже в списку: відкидати
    `qa` і `domains hold` після дотягування означало б платити за них
    запитом кожного разу. Заміряно 07.09: 128 номінованих проти 70.

    **Required Domains — умова, а не побажання** (07.09.2026). Питання команді
    було пряме: «ці два параметри завжди жорстко заповнені у ваших тасках?» —
    відповідь: «завжди, звідти й беруться вітки і домени». Тобто таска без
    доменів — це не вайт-таска, хоч би що лежало в Safe Page. Заміряно того ж
    дня: серед тих, що проходять гейт, без доменів **0** з 61, тобто умова
    нічого не відсіює сьогодні — вона робить правило точним і ловить таску,
    яку почали заповнювати й не дозаповнили.

    Тег `blacks` — теж умова, і теж з 07.09. Блек — це інша сторінка і інша
    робота: ні Safe Page, ні доменів у неї немає, чеки лаби до неї не
    стосуються. Заміряно того ж дня: у воркспейсі 82 таски з цим тегом, і
    жодна не проходила гейт і без цієї умови (їх відсікали порожній «Тип
    вайта» і статус). Тобто умова тут не тому, що щось ловить сьогодні, а
    тому, що замовник назвав її прямо: блеки не беремо ніколи.
    """
    return (bool(t.get("branches"))
            and bool(t.get("domains"))
            and bool(t.get("wtype"))
            and bool(t.get("status_match"))
            and not t.get("tag_excluded")
            and (t.get("status_type") or "") != "closed"
            and not t.get("checklist_done"))


def domain_gate(t: dict) -> bool:
    """Вайт-таска, у якій після зміни доменів є що лагодити: вітки, домени й
    «Тип вайта» на місці, не блек і не закрита.

    Навмисно БЕЗ статусу і БЕЗ чекліста. Домени саппорт міняє у вже
    пофікшеній тасці: 25.09.2026 усі сім таких мали проставлений чекліст і
    «fixed», одна вже стояла в `qa`. Гейт вкладки (`looks_like_ours`)
    відкинув би кожну, а пошта на старих доменах пішла б у деплой."""
    return (bool(t.get("branches"))
            and bool(t.get("domains"))
            and bool(t.get("wtype"))
            and not t.get("tag_excluded")
            and (t.get("status_type") or "") not in ("closed", "done"))


def _pages(fetch_page, full: int, first: int, wave: int,
           max_pages: int = 30) -> list[dict]:
    """Сторінки одного джерела хвилями, поки не трапиться неповна.

    Неповна сторінка у ClickUp і означає останню. Хвиля при цьому прихоплює
    кілька сторінок за межею — вони приходять порожніми. Плата свідома: кожна
    сторінка чекала б на попередню, а це ~6 с на вʼю.

    Ознака кінця — саме неповна сторінка, а не поле `last_page` з відповіді:
    у хвилі сторінки приходять урозбрід, і прапорець довелось би тягнути з
    кожної окремо. Звірено 01.09 повним прогоном обох версій — набір тасок
    збігається до поля.

    `max_pages` — той самий запобіжник, що стояв тут раніше: 30 сторінок на
    джерело.
    """
    out: list[dict] = []
    page, step = 0, first
    while page < max_pages:
        batch = list(range(page, min(page + step, max_pages)))
        with ThreadPoolExecutor(max_workers=len(batch)) as ex:
            got = list(ex.map(fetch_page, batch))
        for tasks in got:
            out.extend(tasks)
        if any(len(tasks) < full for tasks in got):
            break
        page += step
        step = wave
    return out


def fetch_all(include_closed: bool = False,
              skipped: list | None = None,
              token: str = "") -> list[dict]:
    """Усі таски, які бачить власник токена. Два джерела, злиті без дублікатів:

    1. в'ю з CLICKUP_VIEW_ID — ЄДИНИЙ спосіб дістати таски з прихованих
       папок і списків (team-ендпоінт їх не віддає, list-ендпоінт 401);
    2. team-ендпоінт — все інше у воркспейсі.

    Обидва — застосунковим токеном з `CLICKUP_TOKEN`. Таски, розшарені комусь
    ПЕРСОНАЛЬНО, сюди не входять узагалі: їх видно лише власнику, і тягне їх
    `fetch_shared()` особистим токеном з кабінету.

    Жодних фільтрів — фільтрує UI."""
    cfg = _cfg(token)
    if not cfg["token"]:
        raise ValueError("CLICKUP_TOKEN не заданий у .env (Settings → Apps → API Token)")
    headers = {"Authorization": cfg["token"]}

    team = _team_id(headers)

    def team_page(p: int) -> list[dict]:
        r = _get(f"{BASE}/team/{team}/task", headers,
                 {"page": p, "subtasks": "true",
                  "include_closed": "true" if include_closed else "false"})
        r.raise_for_status()
        return r.json().get("tasks", [])

    def view_pages(vid: str) -> tuple[str, list[dict], str]:
        """Сторінки одного вʼю. Відмову в ДОСТУПІ повертаємо, а не кидаємо.

        Вʼю — джерело необовʼязкове, і приватне вʼю однієї людини не має
        гасити скан цілком. 01.09.2026 сталось саме це: сервісний акаунт
        Tech Bot не бачив `4-90000000002-1` (ACCESS_132, вʼю створене іншою
        людиною «для себе»), і вкладка ClickUp у проді віддавала помилку
        замість 444 тасок з двох інших джерел. Причини не було видно ніде:
        помилка йшла кодом 502, а тіло 502 Cloudflare підміняє власною
        сторінкою.

        Решта помилок (5xx, обрив, таймаут) кидається як була: то стан
        тимчасовий, і мовчки віддавати неповний скан — гірше, ніж не віддати
        нічого."""
        def page(p: int) -> list[dict]:
            r = _get(f"{BASE}/view/{vid}/task", headers, {"page": p})
            r.raise_for_status()
            return r.json().get("tasks", [])
        try:
            return vid, _pages(page, 30, VIEW_FIRST, VIEW_WAVE), ""
        except requests.HTTPError as e:
            resp = e.response
            if resp is None or resp.status_code not in (401, 403):
                raise
            try:
                j = resp.json()
                why = f"{j.get('err') or resp.reason} ({j.get('ECODE') or resp.status_code})"
            except ValueError:
                why = f"HTTP {resp.status_code}"
            return vid, [], why

    # Джерела незалежні, а найдовше вʼю довше за весь team-ендпоінт, тож
    # читаємо їх ОДНОЧАСНО: загальний час = час найповільнішого джерела, а не
    # сума. Разом із хвилями всередині це 99 с → ~13 с на тому ж воркспейсі.
    with ThreadPoolExecutor(max_workers=1 + len(cfg["views"])) as ex:
        f_team = ex.submit(_pages, team_page, 100, TEAM_WAVE, TEAM_WAVE)
        f_views = [ex.submit(view_pages, vid) for vid in cfg["views"]]
        team_tasks = f_team.result()
        view_tasks = [f.result() for f in f_views]

    # Порядок злиття той самий, що був, і він не косметичний: таска з
    # team-ендпоінта приходить З чеклістом, а з вʼю — без, тож team має
    # виграти в кожного вʼю, а не навпаки.
    seen: dict[str, dict] = {}
    for t in team_tasks:
        p = _parse(t, cfg)
        p["checklist_loaded"] = True        # team-таски приходять з чеклістами
        p["enriched"] = False               # але без коментарів — довантажить UI
        p["last_comment"] = None
        p["comment_mentions"] = None        # None = ще не відомо (довантажується)
        seen[t["id"]] = p

    # вʼю: додаємо лише відсутні таски; вʼю НЕ віддає чеклісти —
    # UI довантажить їх окремо для видимих тасок (/api/clickup/by_links)
    for vid, tasks, why in view_tasks:
        if why:
            if skipped is not None:
                skipped.append({"view": vid, "reason": why})
            continue
        for t in tasks:
            if t["id"] in seen:
                continue
            p = _parse(t, cfg)
            p["checklist_loaded"] = False
            p["enriched"] = False
            p["last_comment"] = None
            p["comment_mentions"] = None
            seen[t["id"]] = p

    return list(seen.values())


def fetch_shared(token: str, include_closed: bool = False) -> list[dict]:
    """Таски з «Shared with me» власника токена.

    Заміряно 02.09.2026: акаунт автора дістає звідси 173 таски одним запитом,
    сервісний `Tech Bot` — жодної, і ЗА БУДЬ-ЯКОЇ конфігурації вʼю теж жодної:
    вʼю це збережений фільтр, а не доступ. Тому окреме джерело і окремий
    токен.

    Токен тут ЗАВЖДИ особистий (з кабінету): застосунковому акаунту сюди
    ходити нема сенсу — йому персонально нічого не шарять, а один зайвий
    запит на кожен скан коштує 6 с.

    Ієрархія віддає таски з повними полями (`custom_fields`, `checklists`),
    тож парсимо тут же: довантаження по одній коштувало б 173 запити і
    вилетіло б за ліміт ClickUp у 100/хв.

    Параметрів цей ендпоінт не приймає ВЗАГАЛІ, отже й `include_closed` не
    знає. Заміряно 02.09.2026: із 173 тасок 171 закрита, тож без фільтра нижче
    вони їхали б у вкладку навіть зі знятою галкою «включно з закритими» — UI
    на неї не дивиться, він покладається на сервер.

    Відмову НЕ ковтає: її ловить викликач і доповідає в `skipped`. Розшарені
    таски — доважок до основної видачі, а не сама видача.
    """
    cfg = _cfg(token)
    headers = {"Authorization": cfg["token"]}
    r = _get(f"{BASE}/team/{_team_id(headers)}/shared", headers)
    r.raise_for_status()
    out = []
    for t in (r.json() or {}).get("shared", {}).get("tasks") or []:
        if not t.get("id"):
            continue
        if not include_closed and (t.get("status") or {}).get("type") == "closed":
            continue
        p = _parse(t, cfg)
        p["checklist_loaded"] = t.get("checklists") is not None
        p["enriched"] = False
        p["last_comment"] = None
        p["comment_mentions"] = None
        out.append(p)
    return out


def whoami(token: str) -> dict:
    """Чий це токен. Потрібне на збереженні в кабінеті: одруківку видно
    одразу, а не через тиждень порожнім сканом."""
    r = requests.get(f"{BASE}/user", headers={"Authorization": token}, timeout=20)
    if r.status_code != 200:
        try:
            j = r.json()
            why = j.get("err") or j.get("error") or r.reason
            code = j.get("ECODE") or r.status_code
        except ValueError:
            why, code = r.reason, r.status_code
        raise ValueError(f"ClickUp відмовив: {why} ({code})")
    u = (r.json() or {}).get("user") or {}
    return {"id": u.get("id"), "username": u.get("username") or u.get("email") or "?"}


# Імʼя акаунта, яким лаба ходить у ClickUp (у проді — `Tech Bot`). Саппорт
# тегає його, коли звертається до автоматики, а не до чергового фронта
# (25.09.2026: «завязать на тег именно вашего Tech Bot, чтобы вне зависимости
# от того, кто сегодня фиксами занимается»).
_LAB_ACCOUNT = {"name": "", "until": 0.0}


def lab_account() -> str:
    """Імʼя акаунта лаби — БЕЗ походу в мережу: або `CLICKUP_BOT_NAME`, або
    те, що востаннє дізнався `refresh_lab_account()`. Тріаж кличуть і з
    тестів, і з ручних ендпоінтів — мережа там не потрібна й не дозволена."""
    return os.getenv("CLICKUP_BOT_NAME", "").strip() or _LAB_ACCOUNT["name"]


def refresh_lab_account() -> str:
    """Дізнатись імʼя акаунта лаби з токена (`/user`). Кличе виконавець черги
    перед рішенням про таску; удача памʼятається 6 год, невдача — 5 хв, тож
    це один запит на пів доби. Хардкодом «Tech Bot» не пишемо: акаунт уже
    мінявся (01.09 — з автора на Tech Bot)."""
    if os.getenv("CLICKUP_BOT_NAME", "").strip():
        return lab_account()
    now = time.time()
    if now < _LAB_ACCOUNT["until"]:
        return _LAB_ACCOUNT["name"]
    token = os.getenv("CLICKUP_TOKEN", "").strip()
    name = ""
    if token:
        try:
            name = whoami(token).get("username") or ""
        except Exception:
            name = ""
    _LAB_ACCOUNT.update(name=name or _LAB_ACCOUNT["name"],
                        until=now + (6 * 3600 if name else 300))
    return _LAB_ACCOUNT["name"]


def _comments_info(task_id: str, headers: dict) -> tuple[dict | None, list[str], list[dict]]:
    """Один запит коментарів таски → (останній коментар, згадані користувачі,
    повний список коментарів).

    Кожен коментар у списку: {text, user, date, mentions:[...]} — mentions
    зібрані з структурованих сегментів (тег несе user всередині) + токенів
    @ім'я з plain-тексту. Автор коментаря згадкою не є."""
    r = _get(f"{BASE}/task/{task_id}/comment", headers, timeout=30)
    if r.status_code != 200:
        return None, [], []
    raw = r.json().get("comments") or []

    def node_mentions(node, acc):
        if isinstance(node, dict):
            u = node.get("username") or node.get("email")
            if u:
                acc.add(str(u))
            for v in node.values():
                node_mentions(v, acc)
        elif isinstance(node, list):
            for v in node:
                node_mentions(v, acc)

    comments, all_mentions = [], set()
    for c in raw:
        ms = set()
        node_mentions(c.get("comment"), ms)
        for tok in re.findall(r"@([\w.\-]+)", c.get("comment_text") or ""):
            ms.add(tok)
        all_mentions |= ms
        u = c.get("user") or {}
        comments.append({
            "text": c.get("comment_text", ""),
            "user": u.get("username", ""),
            "user_id": u.get("id"),              # id автора — для тегу у відповіді
            "date": c.get("date", ""),
            "mentions": sorted(ms),
        })
    last = ({"text": comments[0]["text"], "user": comments[0]["user"]}
            if comments else None)      # ClickUp віддає найновіший першим
    return last, sorted(all_mentions), comments


def comment_body(text: str, actor: dict | None = None,
                 tag_user_id=None, tag_username: str = "") -> dict:
    """Тіло коментаря — чиста функція, щоб формат перевірявся без мережі.

    Підпис дописується завжди (`attribution.sign_comment`): токен один на
    всіх, тож без нього з таски не видно ні хто попросив фікс, ні чим його
    зробили.

    Тег — окрема річ і НЕ частина підпису: він лишається рівно там, де його
    свідомо передали (кнопка «@автор fixed» і ШІ-міст, якому TSM віддає, кого
    сповістити). Підпис нікого не тегає і не вмикає `notify_all`.
    """
    import attribution
    signed = attribution.sign_comment(text, actor)
    if tag_user_id:
        name = (tag_username or "").lstrip("@").strip() or "user"
        return {"comment": [
            {"type": "tag", "user": {"id": tag_user_id}, "text": "@" + name},
            {"text": " " + signed}], "notify_all": True}
    return {"comment_text": signed, "notify_all": False}


def complete_task(task_id: str, comment: str = "fixed",
                  checklist: bool = True,
                  tag_user_id=None, tag_username: str = "",
                  token: str = "", actor: dict | None = None) -> dict:
    """Додає коментар у таску (і, якщо checklist=True, проставляє чекліст whites).

    Якщо задано tag_user_id — коментар поститься з РЕАЛЬНОЮ згадкою автора
    (@username fixed), тобто ClickUp сповіщає ту людину, що просила фікс."""
    cfg = _cfg(token)
    if not cfg["token"]:
        raise ValueError("CLICKUP_TOKEN не заданий у .env")
    headers = {"Authorization": cfg["token"]}

    resolved = 0
    checklist_found = False
    if checklist:
        r = requests.get(f"{BASE}/task/{task_id}", headers=headers, timeout=30)
        r.raise_for_status()
        t = r.json()
        for cl in t.get("checklists") or []:
            if _norm(cfg["checklist"]) not in _norm(cl.get("name")):
                continue
            checklist_found = True
            for item in cl.get("items") or []:
                if item.get("resolved"):
                    continue
                rr = requests.put(
                    f"{BASE}/checklist/{cl['id']}/checklist_item/{item['id']}",
                    headers=headers, json={"resolved": True}, timeout=30)
                rr.raise_for_status()
                resolved += 1

    commented = False
    if comment:
        body = comment_body(comment, actor, tag_user_id, tag_username)
        rr = requests.post(f"{BASE}/task/{task_id}/comment", headers=headers,
                           json=body, timeout=30)
        rr.raise_for_status()
        commented = True

    return {"task_id": task_id, "checklist_found": checklist_found,
            "items_resolved": resolved, "commented": commented}


def fetch_by_ids(items: list[dict], with_comments: bool = True,
                 token: str = "") -> list[dict]:
    """Прямий фетч по id, паралельно у 3 потоки. item = {"id": ..., "team": optional}.
    Кастомні id (TECH-21676) потребують custom_task_ids=true + team_id.

    with_comments=False — не тягнути коментарі (удвічі менше запитів; для
    перевірки чеклістів коментарі не потрібні).
    Збій однієї таски (429/5xx/мережа) НЕ валить батч — вона повертається
    зі stub-поміткою enrich_failed, решта тасок обробляється нормально."""
    cfg = _cfg(token)
    if not cfg["token"]:
        raise ValueError("CLICKUP_TOKEN не заданий у .env (Settings → Apps → API Token)")
    headers = {"Authorization": cfg["token"]}

    # team_id визначаємо один раз ДО пулу, щоб потоки не робили це навперебій
    team_default = None
    if any(it.get("team") or not re.fullmatch(r"[a-z0-9]+", it["id"]) for it in items):
        team_default = _team_id(headers)

    def one(it: dict) -> dict:
        tid = it["id"]
        try:
            params = {}
            if it.get("team") or not re.fullmatch(r"[a-z0-9]+", tid):
                params = {"custom_task_ids": "true",
                          "team_id": it.get("team") or team_default}
            r = _get(f"{BASE}/task/{tid}", headers, params, timeout=30)
            if r.status_code in (401, 404):
                return {"id": tid, "no_access": True,
                        "name": f"{tid} — не знайдено або немає доступу",
                        "url": "", "status": "?", "status_match": False,
                        "tags": [], "tag_excluded": False, "updated": "",
                        "list_name": "",
                        "assignees": [], "wtype": None,
                        "checklist_found": False, "checklist_done": False,
                        "checklist_loaded": True, "enriched": True,
                        "last_comment": None, "comment_mentions": [], "comments": [],
                        "branches": [], "domains": [], "fields_seen": []}
            r.raise_for_status()
            p = _parse(r.json(), cfg)
            p["checklist_loaded"] = True
            p["enriched"] = True
            if with_comments:
                p["last_comment"], p["comment_mentions"], p["comments"] = _comments_info(tid, headers)
            else:
                p["last_comment"] = None
                p["comment_mentions"] = None      # невідомо — довантажиться при потребі
                p["comments"] = None
            return p
        except Exception as e:                    # 429 після ретраїв / 5xx / мережа
            return {"id": tid, "enrich_failed": True, "error": str(e)[-200:]}

    if not items:
        return []
    with ThreadPoolExecutor(max_workers=3) as ex:
        return list(ex.map(one, items))
