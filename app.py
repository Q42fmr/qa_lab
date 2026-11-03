"""qa_lab — test/QA server for the white-pages GitLab project.

Run:  uvicorn app:app --reload --port 8030
UI:   http://localhost:8030/
"""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel

# override=True — інакше правки .env НЕ ДІЮТЬ, поки лаба не спиниться повністю.
# Причина: uvicorn --reload тримає батьківський процес, `load_dotenv()` кладе
# значення в os.environ, і на кожному перезапуску дочірній процес успадковує вже
# прочитане; з дефолтним override=False наявна змінна перемагає файл. Кейс
# 2026-08-17: у .env дописали два в'ю ClickUp, лаба перезапустилась і далі
# бачила старе одне в'ю — «показано 0 з 324 тасок», хоча таски були.
# .env тут і є джерелом правди (у README він описаний саме так).
load_dotenv(override=True)

import base64
import difflib
import html
import json
import re
import time
from urllib.parse import quote

import attribution
import auth
import checks_ledger
import ai_bridge
import clickup_client
import cu_fixed
import commit_gate
import cu_hook
import cu_queue
import deployer
import domains
import lighthouse_runner
import media
import preview
import photos
import prepare_main
import projects
import replacer
import runner
import slack_oauth
import stats_ledger
import telegram_bot
import tg_watcher
import translate_text
import users
import visual_runner
import buttons_runner

projects.init()
# ClientProxy делегує до клієнта АКТИВНОГО проєкту, SigningClient дописує
# підпис у повідомлення коміту. Обгортка тут одна на всіх: цей самий обʼєкт
# їде в `replacer.apply()` аргументом і в `ai_bridge` через `wire()`, тож
# правити 19 місць коміту не треба.
client = attribution.SigningClient(projects.ClientProxy())

import os
import threading

_state_lock = threading.Lock()


def write_json_state(path, obj):
    """Атомарний запис JSON-стейту: пишемо у .tmp і os.replace (без гонок,
    без напівзаписаних/склеєних файлів). Під локом — паралельні прогони
    перевірок більше не псують checks_state.json."""
    path = __import__("pathlib").Path(path)
    with _state_lock:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)


def read_json_state(path, default):
    """Стійке читання: якщо файл побитий (напр., 'Extra data' від старої гонки),
    беремо перший валідний JSON-префікс замість падіння у 500."""
    path = __import__("pathlib").Path(path)
    if not path.exists():
        return default
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw)
            write_json_state(path, obj)      # одразу лікуємо файл
            return obj
        except Exception:
            return default


# Читання-правка-запис спільного файла — ОДНА операція.
#
# `write_json_state` лочить лише сам запис, а між читанням і записом у
# ендпоінтах минали мілісекунди (прогін — секунди): два одночасні прогони
# людей читали `checks_state.json`, кожен дописував свої вітки, і другий
# запис стирав перший. Так само губились рядки журналу комітів (разом з
# кнопкою Revert для них) і вітки при одночасному імпорті. Лок — на файл: різні
# файли пишуться паралельно.
UNCHANGED = object()          # `fn` повертає це — файл не переписуємо
_mutate_guard = threading.Lock()
_mutate_locks: dict[str, threading.Lock] = {}


def _mutate_lock(path) -> threading.Lock:
    key = str(__import__("pathlib").Path(path).resolve())
    with _mutate_guard:
        return _mutate_locks.setdefault(key, threading.Lock())


def mutate_json_state(path, default, fn):
    """`fn(поточне)` → нове значення (або `None`, якщо правив на місці, або
    `UNCHANGED`). `default` — фабрика (`list`, `dict`): спільний літерал-дефолт
    мутувався б між викликами. Повертає те, що лежить у файлі після виклику."""
    with _mutate_lock(path):
        cur = read_json_state(path, None)
        if cur is None:
            cur = default()
        got = fn(cur)
        if got is UNCHANGED:
            return cur
        new = cur if got is None else got
        write_json_state(path, new)
        return new


# ---- журнал проблем (вітки, що не залилися з ClickUp / не синхронізувались) ----
def load_problems() -> list[dict]:
    return read_json_state(projects.state_file("problems.json"), [])


def add_problems(items: list[dict]):
    """items = [{branch, source: 'sync'|'import', reason, task?}]. Дедуп по
    (branch, source) — свіжий запис витісняє старий; накопичується між сесіями."""
    items = [i for i in items if i.get("branch")]
    if not items:
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    for i in items:
        i.setdefault("ts", ts)
    keep = {(i["branch"], i["source"]) for i in items}
    mutate_json_state(
        projects.state_file("problems.json"), list,
        lambda old: (items + [x for x in old
                              if (x.get("branch"), x.get("source")) not in keep])[:1000])

def drop_problems(pred) -> int:
    """Прибрати рядки журналу проблем за умовою. Повертає, скільки прибрано.

    Потрібне тому, що проблема буває тимчасовою: таска, яку лаба не змогла
    визначити, стає визначеною щойно хтось допише скіл, і лишати її в
    «Проблемах» після успішного перенесення в чергу означало б показувати
    те саме двічі — як помилку і як роботу.
    """
    gone = [0]

    def drop(rows):
        keep = [x for x in rows if not pred(x)]
        gone[0] = len(rows) - len(keep)
        return keep if gone[0] else UNCHANGED
    mutate_json_state(projects.state_file("problems.json"), list, drop)
    return gone[0]


app = FastAPI(title="qa_lab")


@app.on_event("startup")
def _reap_orphan_deploys():
    # гасимо php-деплої, що пережили попередній запуск сервера (тримають deploy/)
    try:
        n = deployer.reap_orphans()
        if n:
            print(f"[deploy] прибрано осиротілих php-деплоїв: {n}")
    except Exception:
        pass


@app.on_event("startup")
def _start_tg_watcher():
    # фоновий аналіз ClickUp → Telegram (мовчить, якщо токен/чат не задані)
    try:
        tg_watcher.start(read_json_state, write_json_state)
        if telegram_bot.enabled():
            print(f"[tg] вотчер запущено, кожні {telegram_bot.poll_minutes()} хв")
    except Exception as e:
        print(f"[tg] не вдалося запустити вотчер: {e}")


@app.on_event("startup")
def _bootstrap_admin():
    """Адмінська учетка з ADMIN_LOGIN/ADMIN_PASSWORD.

    Пароль застосовується лише тоді, коли значення змінної відрізняється від
    застосованого минулого разу, інакше зміна пароля з UI не пережила б
    жодного рестарту (розгорнуто — в `users.ensure_bootstrap_admin`).

    У лог пишемо, що саме сталося. Скид пароля мовчки — це якраз те, через
    що «я міняв пароль, а прилетів старий» неможливо було пояснити: у логу
    рівно так само стояв рядок про адміна.
    """
    try:
        password = os.getenv("ADMIN_PASSWORD", "")
        login = users.norm_login(os.getenv("ADMIN_LOGIN", "admin"))
        before = users.store().find_by_login(login) if (login and password) else None
        row = users.ensure_bootstrap_admin()
        if not row:
            print("[auth] ADMIN_PASSWORD не заданий — bootstrap-адміна немає")
        elif before is None:
            print(f"[auth] адмін: {row.get('login')} — учетку створено")
        elif before.get("bootstrap_fp") != row.get("bootstrap_fp"):
            print(f"[auth] адмін: {row.get('login')} — пароль скинуто зі змінної ADMIN_PASSWORD")
        else:
            print(f"[auth] адмін: {row.get('login')} — пароль не чіпали, у CI те саме значення")
    except Exception as e:
        print(f"[auth] не вдалося створити адміна: {e}")


# ---------------------------------------------------------------- авторизація
@app.middleware("http")
async def _require_session(request, call_next):
    """Єдиний гейт на весь застосунок.

    Саме middleware, а не залежність на кожному ендпоінті: їх тут 142, і один
    забутий декоратор — це дірка, якої не видно ні в код-рев'ю, ні в UI.
    Тут навпаки: закрито все, а виняток треба дописати руками в короткий
    список `auth.PUBLIC_PATHS`.

    Відповідь різна за призначенням: API віддає 401 (UI сам перекине на
    екран входу і не намалює порожню сторінку), навігація — 302 на /login.
    """
    path = request.url.path
    if auth.is_public(path):
        return await call_next(request)

    user = auth.current_user(request)
    if user is None:
        # Другий кінець конвеєра — застосунок, а не людина: куки в нього
        # немає. Токен діє ЛИШЕ на /api/ai/* (див. auth.service_user), тож
        # решта 150 ендпоінтів лишається закритою так само, як була.
        user = auth.service_user(request)
    if user is None and auth.is_hook_path(path):
        # Двері для ClickUp. Пускаємо ДО ендпоінта, бо підпис лежить у тілі, а
        # тіло тут читати не можна (див. auth.HOOK_PATH). Шлях рівно один, і
        # сам ендпоінт відмовляє 401, якщо підпис не збігся або ключа немає.
        user = dict(auth.HOOK_USER)
    if user is None:
        from fastapi.responses import JSONResponse, RedirectResponse
        if path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "потрібен вхід"})
        return RedirectResponse("/login", status_code=302)

    # Далі ендпоінти беруть користувача звідси, не перечитуючи куку.
    request.state.user = user
    # Той самий користувач — у контекстну змінну, звідки його бере підпис
    # коміту. Аргументом його довелось би протягувати через 19 точок запису.
    attribution.set_actor(user)
    # І проєкт — тим самим шляхом: у кожної людини свій php/vue. Доки він був
    # один на процес, перемикання в одного перемикало всіх, і наступний
    # Sync/Apply колеги йшов у чужий проєкт (задача 21.09.2026). Службові
    # користувачі (міст, вебхук) поля не мають — їм лишається дефолт процесу.
    projects.bind_request(user.get("project"))
    return await call_next(request)


# ------------------------------------------------------- прев'ю-піддомен
# Гасіння деплою при закритті сесії — тут, бо deployer живе в цьому шарі.
preview.wire(on_close=deployer.stop)


# ⚠️ ПОРЯДОК. Цей middleware мусить стояти ПІСЛЯ `_require_session` у файлі:
# `add_middleware` вставляє на початок списку, а стек будується `reversed()`,
# тож ДОДАНИЙ ОСТАННІМ стає ЗОВНІШНІМ і виконується ПЕРШИМ. Саме це нам і
# треба: на прев'ю-хості не існує ані маршрутів лаби, ані її авторизації —
# там своя, сесійна. Переставиш блоки місцями — і `/__open` почне отримувати
# 302 на /login, а решта хоста віддасть 401 замість вайта.
@app.middleware("http")
async def _preview_host(request, call_next):
    """Другий хост на тому самому контейнері — і жорсткий тупик для решти.

    Якщо `Host` збігається з PREVIEW_HOST, запит НІКОЛИ не йде далі по стеку:
    обробляється тут або відмовляється. Тобто дірку «дійти до API лаби через
    піддомен» закрито не списком винятків, а тим, що продовження не існує.
    """
    if not preview.is_preview_host(request.headers.get("host", "")):
        return await call_next(request)
    resp = await _preview_serve(request)
    # no-store на ВСЕ, що віддає прев'ю-хост, а не лише на проксі вайта
    # (`preview.response_headers`). Наші 404/410 Cloudflare кешує так само:
    # шлях з розширенням (`.jpg`, `.css`) — MISS, далі HIT, і браузеру він
    # дописує max-age=14400 (заміряно 05.10). Тоді 410 після кінця сесії чи
    # 404 без куки на `images/ph-02.jpg` забирав би це фото в наступного, хто
    # відкриє прев'ю, а в його браузері — ще на 4 години.
    resp.headers["Cache-Control"] = "no-store"
    return resp


async def _preview_serve(request):
    from fastapi.responses import PlainTextResponse, RedirectResponse, StreamingResponse
    from starlette.concurrency import run_in_threadpool

    path = request.url.path

    # 1) обмін одноразового токена на куку
    if path == "/__open":
        sid = preview.redeem(request.query_params.get("k", ""))
        if not sid:
            return PlainTextResponse(
                "посилання вже використане або застаріле — відкрий прев'ю з лаби ще раз",
                status_code=410)
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie(preview.COOKIE, sid, max_age=preview.TTL_S, httponly=True,
                        samesite="strict", secure=preview._secure(), path="/")
        return resp

    # 2) чинна сесія?
    sid = request.cookies.get(preview.COOKIE, "")
    slot = preview.session_for(sid)
    if slot is None:
        if preview.has_expired_cookie(sid):
            preview.close_sid(sid)          # саме цю сесію, не чиюсь іншу
            return PlainTextResponse("прев'ю завершилось — відкрий його з лаби ще раз",
                                     status_code=410)
        # без куки хост мовчить: жодної підказки, що за ним стоїть лаба
        return PlainTextResponse("не знайдено", status_code=404)

    # 3) проксі на php -S цієї сесії. ЦІЛЬ НЕ ПРИХОДИТЬ ІЗЗОВНІ — порт беремо
    # зі слоту на сервері, тож підставити чужу адресу нічим.
    import requests as _rq
    url = f"http://127.0.0.1:{slot['port']}{path}"
    if request.url.query:
        url += "?" + request.url.query
    body = await request.body()
    try:
        r = await run_in_threadpool(
            lambda: _rq.request(request.method, url,
                                headers=preview.request_headers(request.headers,
                                                                preview.host()),
                                data=body or None, stream=True,
                                allow_redirects=False, timeout=30))
    except Exception as e:
        return PlainTextResponse(f"деплой вітки не відповідає: {e}", status_code=502)

    resp = StreamingResponse(r.iter_content(65536), status_code=r.status_code)
    # raw_headers, а не headers=: вайт може поставити КІЛЬКА Set-Cookie, а мапа
    # лишила б один. latin-1 з ignore — щоб кривий заголовок вайта не поклав
    # відповідь цілком.
    resp.raw_headers = [
        (k.lower().encode("latin-1", "ignore"), v.encode("latin-1", "ignore"))
        for k, v in preview.response_headers(r.raw.headers.items())
    ]
    return resp


def current_user(request) -> dict:
    """Користувач поточного запиту (middleware його вже поклав)."""
    return getattr(request.state, "user", None) or {}


def require_admin(request) -> dict:
    user = current_user(request)
    if not auth.is_admin(user):
        raise HTTPException(403, "потрібні права адміністратора")
    return user


class LoginRequest(BaseModel):
    login: str
    password: str


@app.post("/api/auth/login")
def auth_login(req: LoginRequest, request: Request, response: Response):
    """Вхід логіном і паролем.

    Повідомлення про помилку навмисно одне на всі випадки (немає такого
    логіна / невірний пароль / акаунт вимкнено): інакше форма стає засобом
    перевіряти, хто в компанії має доступ.

    Ліміт спроб стоїть ДО перевірки пароля — інакше він не обмежував би
    нічого, крім тексту відповіді: підбір і далі йшов би повним ходом, просто
    з іншим кодом наприкінці. Плата за це — правильний пароль у вікні
    очікування теж не пройде; тому вікно хвилинне (див. `auth.MAX_FAILS`).
    """
    wait = auth.login_retry_after(req.login)
    if wait:
        raise HTTPException(429, f"забагато невдалих спроб — спробуй за {wait} с")
    row = users.authenticate(req.login, req.password)
    if row is None:
        auth.note_login_failure(req.login)
        raise HTTPException(401, "невірний логін або пароль")
    auth.clear_login_failures(req.login)
    uid = auth.uid_of(row)
    users.store().touch_login(uid)
    auth.invalidate(uid)
    auth.set_cookie(response, uid)
    return {"user": users.public(row)}


@app.post("/api/auth/logout")
def auth_logout(response: Response):
    auth.clear_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(request: Request):
    """Хто зайшов. Публічний ендпоінт: без сесії віддає `user: null`, і саме
    за цим UI розуміє, що треба показати екран входу."""
    user = auth.current_user(request)
    return {"user": users.public(user), "slack": slack_oauth.enabled()}


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return _page("login.html")


# ---------------------------------------------------------------- Slack OIDC
@app.get("/api/auth/slack/start")
def slack_start():
    """Кнопка «Увійти через Slack».

    Саме навігація (302), а не fetch: OAuth вимагає справжнього переходу
    браузера — з XHR редірект на slack.com нікуди не приведе.
    """
    from fastapi.responses import RedirectResponse
    if not slack_oauth.enabled():
        raise HTTPException(400, "вхід через Slack не налаштований")
    if not slack_oauth.redirect_uri():
        raise HTTPException(500, "не заданий SLACK_REDIRECT_URI (або DOMAIN_NAME)")
    return RedirectResponse(slack_oauth.authorize_url(slack_oauth.issue_state()),
                            status_code=302)


@app.get("/api/auth/slack/callback")
def slack_callback(request: Request, code: str = "", state: str = "",
                   error: str = ""):
    """Повернення зі Slack.

    Помилки віддаємо не JSON-ом, а редіректом на /login з коротким текстом:
    сюди людина потрапляє НАВІГАЦІЄЮ, і побачити голий json замість екрана
    входу — найгірше з можливого.
    """
    from fastapi.responses import RedirectResponse

    def back(msg: str):
        return RedirectResponse("/login?err=" + quote(msg), status_code=302)

    if error:
        return back(f"Slack відмовив: {error}")
    if not slack_oauth.consume_state(state):
        # Прострочений або підроблений state. Найчастіше — людина відкрила
        # вхід, пішла пити каву і повернулась через годину.
        return back("посилання застаріло, спробуй ще раз")
    if not code:
        return back("Slack не передав код")

    try:
        prof = slack_oauth.login_profile(code)
    except Exception as e:
        return back(str(e))

    try:
        row = users.upsert_slack_user(
            prof["slack_user_id"], prof["team_id"],
            name=prof.get("name", ""), email=prof.get("email", ""))
    except Exception as e:
        return back(f"не вдалося створити акаунт: {e}")

    if row.get("is_active", True) is False:
        return back("акаунт вимкнено адміністратором")

    uid = auth.uid_of(row)
    users.store().touch_login(uid)
    auth.invalidate(uid)
    resp = RedirectResponse("/", status_code=302)
    auth.set_cookie(resp, uid)
    return resp


# ---------------------------------------------------------------- кабінет
class PasswordRequest(BaseModel):
    password: str
    current: str | None = None


@app.post("/api/account/password")
def account_set_password(req: PasswordRequest, request: Request):
    """Задати або змінити СВІЙ пароль.

    Той, хто зайшов через Slack, пароля ще не має — тоді `current` не
    потрібен. У кого пароль уже є, мусить його підтвердити: інакше залишена
    відкритою вкладка дозволяла б перехопити акаунт назавжди.
    """
    me = current_user(request)
    uid = auth.uid_of(me)
    if len(req.password or "") < 8:
        raise HTTPException(400, "пароль коротший за 8 символів")
    row = users.store().get(uid)
    if row is None:
        raise HTTPException(404, "користувача не знайдено")
    if row.get("password_hash"):
        if not users.verify_password(req.current or "", row.get("password_hash")):
            raise HTTPException(403, "поточний пароль невірний")
    users.store().update(uid, {"password_hash": users.hash_password(req.password)})
    auth.invalidate(uid)
    return {"ok": True}


# ------------------------------------------------------------------ кабінет
# Особистий токен ClickUp: у кожного свій, бо застосунковий акаунт не бачить
# тасок, розшарених людині персонально. Значення НЕ повертається жодним
# ендпоінтом — назовні їде тільки `has_clickup_token`, ім'я акаунта ClickUp і
# остання помилка.
class ClickUpTokenRequest(BaseModel):
    token: str


@app.get("/api/account")
def account_me(request: Request):
    return {"user": users.public(users.store().get(auth.uid_of(current_user(request))))}


@app.post("/api/account/clickup_token")
def account_set_clickup_token(req: ClickUpTokenRequest, request: Request):
    """Зберегти свій токен ClickUp. Перевіряємо ДО збереження.

    Перевірка — це один GET `/user`, і вона тут не для краси: без неї
    одруківка в токені виявилась би через тиждень порожнім особистим сканом,
    і виглядало б це як «фіча не працює». Заразом дізнаємось ім'я акаунта —
    щоб кабінет міг сказати, ЧИЙ це токен, не показуючи значення.
    """
    uid = auth.uid_of(current_user(request))
    token = (req.token or "").strip()
    if len(token) < 20:
        raise HTTPException(400, "це не схоже на токен ClickUp "
                                 "(Settings → Apps → API Token, починається з pk_)")
    try:
        who = clickup_client.whoami(token)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"ClickUp недоступний: {e}")
    users.store_clickup_token(uid, token, who.get("username") or "")
    auth.invalidate(uid)
    return {"ok": True, "clickup_user": who.get("username")}


@app.delete("/api/account/clickup_token")
def account_clear_clickup_token(request: Request):
    uid = auth.uid_of(current_user(request))
    users.clear_clickup_token(uid)
    auth.invalidate(uid)
    return {"ok": True}


@app.get("/account", response_class=HTMLResponse)
def account_page():
    return _page("account.html")


# ---------------------------------------------------------------- користувачі
class UserCreateRequest(BaseModel):
    login: str
    name: str | None = ""
    password: str | None = None
    slack_user_id: str | None = None
    is_admin: bool = False


class UserPatchRequest(BaseModel):
    name: str | None = None
    password: str | None = None
    slack_user_id: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None


@app.get("/api/users")
def users_list(request: Request):
    require_admin(request)
    return [users.public(r) for r in users.store().list_all()]


@app.post("/api/users")
def users_create(req: UserCreateRequest, request: Request):
    require_admin(request)
    login = users.norm_login(req.login)
    if not login:
        raise HTTPException(400, "порожній логін")
    if req.password is not None and len(req.password) < 8:
        raise HTTPException(400, "пароль коротший за 8 символів")
    try:
        row = users.store().create({
            "login": login,
            "name": req.name or login,
            "password_hash": users.hash_password(req.password) if req.password else None,
            "slack_user_id": (req.slack_user_id or "").strip() or None,
            "is_admin": bool(req.is_admin),
            "is_active": True,
        })
    except ValueError as e:
        raise HTTPException(409, str(e))
    return users.public(row)


@app.patch("/api/users/{uid}")
def users_patch(uid: str, req: UserPatchRequest, request: Request):
    """Редагування. Адмін не може вимкнути або розжалувати сам себе —
    інакше єдиним рухом можна лишити систему без жодного адміністратора."""
    me = require_admin(request)
    row = users.store().get(uid)
    if row is None:
        raise HTTPException(404, "користувача не знайдено")

    patch: dict = {}
    if req.name is not None:
        patch["name"] = req.name
    if req.slack_user_id is not None:
        patch["slack_user_id"] = req.slack_user_id.strip() or None
    if req.password is not None:
        if len(req.password) < 8:
            raise HTTPException(400, "пароль коротший за 8 символів")
        patch["password_hash"] = users.hash_password(req.password)
    if req.is_admin is not None:
        patch["is_admin"] = bool(req.is_admin)
    if req.is_active is not None:
        patch["is_active"] = bool(req.is_active)

    if uid == auth.uid_of(me):
        if patch.get("is_active") is False:
            raise HTTPException(400, "не можна вимкнути власну учетку")
        if patch.get("is_admin") is False:
            raise HTTPException(400, "не можна зняти адмінство із себе")

    updated = users.store().update(uid, patch)
    auth.invalidate(uid)
    return users.public(updated)


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request):
    require_admin(request)
    return _page("users.html")


def MOCK() -> bool:               # було глобальним прапорцем; тепер — активний проєкт
    return projects.is_mock()


@app.exception_handler(ValueError)
def _value_error_handler(request, exc: ValueError):
    # bad branch names / other input errors -> 400, not a 500 stack trace
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------------------------------------------------------------- models
class ReplaceParams(BaseModel):
    mode: str = "regex"              # regex | literal | script | pairs | insert
    find: str | None = None
    replace: str | None = ""
    ignore_case: bool = False
    file_filter: str | None = "*"
    script: str | None = None
    pairs: list[dict] | None = None  # для mode=pairs: [{"find","replace"}]
    # mode=insert: вставка фрагмента біля якоря (напр. favicon перед </head>)
    snippet: str | None = None
    anchor: str | None = "</head>"
    position: str = "before"         # before | after
    skip_if_present: bool = True


class PreviewRequest(ReplaceParams):
    branch: str


class ApplyRequest(PreviewRequest):
    message: str
    selected_paths: list[str] | None = None


class RunChecksRequest(BaseModel):
    branches: list[str]
    check_ids: list[str] | None = None


# ---------------------------------------------------------------- meta
@app.get("/api/health")
def health():
    """Ліверність для оркестратора — єдиний ендпоінт, який має право
    відповідати без сесії (він уже в `auth.PUBLIC_PATHS`).

    Свідомо порожній: не ходить ні в GitLab, ні в ClickUp, ні на диск.
    Інакше недоступність чужого сервісу читалась би Swarm-ом як «контейнер
    здох», і він перезапускав би цілком живу лабу — разом з прогоном
    візуальних перевірок, що йшов у ту мить.

    Не плутати з `/api/status` нижче: той віддає стан проєктів і закритий
    авторизацією, тому healthcheck на нього отримував би 401 і сервіс
    ніколи не ставав би healthy.
    """
    return {"ok": True}


@app.get("/api/status")
def status():
    return {
        "mock": MOCK(),
        "commit_url_base": ""
        if MOCK() else client.commit_url("").rstrip("/"),
        "projects": projects.list_projects(),
        "project": projects.current_id(),
        "ptype": projects.ptype(),
        # прев'ю вмикається наявністю PREVIEW_HOST: ця фіча працює лише
        # там, де їй задали хост (див. preview.py)
        "preview": preview.enabled(),
        # чи має сервер чим відкрити провідник і IDE НА МАШИНІ ЛЮДИНИ
        "local_fs": can_open_locally(),
    }


class ProjectSelect(BaseModel):
    id: str


@app.post("/api/project")
def select_project(req: ProjectSelect, request: Request):
    """Вибір проєкту — людини, а не сервера.

    Доти тут стояв `set_current()`, тобто перемикач у шапці перемикав УСІХ:
    колега в php-вітках після чийогось переходу на vue синкав і комітив уже у
    vue (задача 21.09.2026). Тепер вибір лягає в запис користувача, а
    middleware кладе його на кожен запит цієї людини. Дефолт процесу
    (`active_project.json`) лишається тим, хто ще нічого не обирав, і фоновій
    роботі.
    """
    if not projects.has(req.id):
        raise HTTPException(400, f"невідомий проєкт: {req.id}")
    uid = auth.uid_of(current_user(request))
    if uid:
        users.store().update(uid, {"project": req.id})
        # Сесія кешує запис користувача (`auth._CACHE_TTL`): без цього
        # наступні запити ще кілька секунд приходили б зі старим вибором, і
        # перемальована вкладка показала б знову попередній проєкт.
        auth.invalidate(uid)
    else:
        projects.set_current(req.id)
    # Відповідь — уже з нового проєкту: UI одразу перемальовується по ній.
    projects.bind_request(req.id)
    return {"project": projects.current_id(), "ptype": projects.ptype(),
            "mock": MOCK()}


# ---------------------------------------------------------------- журнал комітів


JOURNAL_CAP = 2000      # вкладка «Журнал» — вікно останньої активності;
#                         історію для статистики тримає stats_ledger


def load_journal() -> list[dict]:
    return read_json_state(projects.state_file("commits_log.json"), [])


def _reconcile_snapshot_with_gate(branch: str, files: list[str]) -> None:
    """Знімок після коміту = те, що реально пішло в GitLab.

    commit_gate прибирає невідомі {{UPPER}} з контенту коміту (php), а
    кожен шлях коміту далі пише у знімок СВІЙ, ще не очищений текст — знімок
    розходився б з віткою, і «Локальні зміни» показували б токени як правку.
    Тож ті самі файли у знімку чистимо тим самим правилом."""
    if projects.ptype() != "php":
        return
    base = runner.snapshot_dir(branch)
    for p in files:
        if not p.lower().endswith(commit_gate.TEXT_EXT):
            continue
        f = base / p
        try:
            raw = f.read_bytes()
        except OSError:
            continue
        text = raw.decode("utf-8", "replace")
        new, counts = commit_gate.strip_tokens(text)
        if counts:
            f.write_bytes(new.encode("utf-8"))


def log_commit(branch: str, message: str, commit_id: str, files: list[str],
               action: str = "commit", notes: list | None = None):
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "branch": branch,
           "message": message, "commit": commit_id, "files": files,
           "action": action}
    if notes:
        rec["notes"] = list(notes)
    _reconcile_snapshot_with_gate(branch, files)
    # Одною операцією і атомарно: два Apply одночасно (двоє людей, або людина
    # і автокоміт черги) доти губили рядок одне одного, а разом з ним — і
    # кнопку Revert для того коміту. `write_text` поверх живого файла ще й
    # давав читачеві Журналу напівзаписаний json.
    mutate_json_state(projects.state_file("commits_log.json"), list,
                      lambda j: [rec] + j[:JOURNAL_CAP - 1])
    # Журнал обрізається, тож старі дні з нього зникають ФІЗИЧНО. Статистика
    # читає окремий append-only реєстр — дописування без перезапису історії.
    stats_ledger.append(projects.state_dir(), rec)
    # знімок після коміту лаби відповідає новому коміту — пересуваємо базу,
    # щоб «Локальні зміни» не рахували щойно закомічене за локальну правку.
    # Короткий id — щоб skip-логіка sync (порівняння з branch().short_id) працювала.
    if commit_id:
        try:
            runner.set_snapshot_commit(branch, commit_id[:8])
        except Exception:
            pass


# ---------------------------------------------------------------- ШІ-міст
# Модуль приймає скарги від другого застосунку конвеєра (TSM), обирає чеки
# через Claude, ганяє їх і — коли ввімкнено — комітить. Йому потрібні
# `log_commit` і `add_problems`, які живуть тут; щоб не було кільцевого
# імпорту, вони впорскуються явно.
ai_bridge.wire(log_commit=log_commit, add_problems=add_problems, client=client)
app.include_router(ai_bridge.router)


# ------------------------------------------------------------- черга ClickUp
# Той самий конвеєр, тільки вхід — подія ClickUp, а не людина з кнопкою.
# Комітити звідти нікуди: `cu_queue` не має виклику `commit()` взагалі, у git
# і в таску пише лише кнопка пачки нижче.
cu_queue.wire(read_json_state=read_json_state, write_json_state=write_json_state,
              log_commit=log_commit, add_problems=add_problems,
              drop_problems=drop_problems, load_problems=load_problems,
              client=client)
app.include_router(cu_queue.router)
app.include_router(cu_hook.router)

# «Fixed уже є» — попередження ручній роботі, що таску вже відписали. Лише
# читає ClickUp; дошка спільна для всіх, як і сам ClickUp.
cu_fixed.wire(read_json_state=read_json_state, write_json_state=write_json_state)
app.include_router(cu_fixed.router)


@app.on_event("startup")
def _start_cu_queue():
    # Мовчить, доки Авто-QA вимкнене (а вимкнене воно за замовчуванням):
    # жодного потоку, жодного походу в ClickUp.
    try:
        # Кнопка одна (23.09.2026), а в томі стану міг лишитись змішаний
        # набір трьох старих перемикачів — його вважаємо вимкненим.
        if cu_queue.normalize_switches():
            print("[queue] змішаний стан перемикачів — Авто-QA вимкнено, "
                  "увімкнути кнопкою у вкладці")
        # Черга живе в пам'яті, а її стан — на диску. Після рестарту (деплой,
        # падіння) те, що лишилось `queued`, інакше не виконав би ніхто:
        # у файлі воно є, а виконувати нікому.
        back = cu_queue.restore_queue()
        if back:
            print(f"[queue] повернуто у чергу після рестарту: {back}")
        cu_queue.start()
    except Exception as e:
        print(f"[queue] не вдалося підняти чергу: {e}")
    # Вебхук лаба заводить собі сама — у фоні і з повторами: ClickUp може бути
    # недоступний рівно в мить деплою, і старт від цього залежати не має.
    try:
        cu_hook.start_registration()
    except Exception as e:
        print(f"[hook] реєстрацію не запущено: {e}")


@app.get("/api/journal")
def journal():
    return load_journal()


class RevertRequest(BaseModel):
    branch: str
    commit: str


@app.post("/api/revert")
def revert(req: RevertRequest):
    try:
        r = client.revert(req.commit, req.branch)
    except NotImplementedError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"revert failed: {e}")
    try:
        runner.sync_branch(client, req.branch)   # оновлюємо знімок після відкату
    except Exception:
        pass
    log_commit(req.branch, f"revert {req.commit[:10]}", r.get("id", ""), [],
               action="revert")
    return {"reverted": req.commit, "new_commit": r.get("id", "")}


def _udiff(path: str, old: str, new: str, a: str = "a", b: str = "b",
           n: int = 3) -> dict:
    d = list(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"{a}/{path}", tofile=f"{b}/{path}", n=n))
    return {"path": path, "hunks": sum(1 for l in d if l.startswith("@@")),
            "diff": "".join(d)}


# ---------------------------------------------------------------- branch list (branches.<uid>.json)
# Робочий список — у КОЖНОЇ людини свій (задача 21.09.2026). Спільний список
# означав, що «Очистити список», «Закрити чисті» чи імпорт із заміною в одного
# прибирали вітки з-під рук іншого. Файл — `branches.<uid>.json` у теці
# проєкту. Старий спільний `branches.json` лишився в двох ролях:
#   * ОСНОВА для людини, яка ще нічого не правила: вона бачить спільний
#     список, а перша правка кладе його КОПІЮ в особистий файл — після
#     переходу ніхто не прокидається з порожнім списком;
#   * список службових контекстів без людини (міст, вебхук, тести).
# ⚠️ «Архів» = знімок, якого немає в жодному списку, тож архів і його чистка
# рахують ОБ'ЄДНАННЯ всіх списків (`all_listed`). Рахувати лише свій означало б,
# що одна людина чистить архів — і стирає робочі знімки іншої.
_UID_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def _list_owner() -> str:
    """uid людини цього запиту — той самий актор, що підписує коміти. uid
    іде в назву файла, тому лишаємо в ньому тільки безпечні символи."""
    return _UID_SAFE.sub("", auth.uid_of(attribution.actor() or {}))


def branch_list_file(pid: str | None = None) -> Path:
    uid = _list_owner()
    name = f"branches.{uid}.json" if uid else "branches.json"
    return projects.state_file_for(pid, name) if pid else projects.state_file(name)


def _shared_list(path: Path) -> list[str]:
    return read_json_state(path.with_name("branches.json"), [])


def load_branch_list() -> list[str]:
    path = branch_list_file()
    got = read_json_state(path, None)
    return _shared_list(path) if got is None else got


def mutate_branch_list(fn, pid: str | None = None):
    """Правка СВОГО робочого списку однією операцією (див.
    `mutate_json_state`): «прочитав-дописав-записав» кроками губило вітки,
    коли одночасно йшли імпорт з ClickUp і «Закрити чисті». `pid` — список
    людини в ІНШОМУ проєкті (перенос php → vue при імпорті)."""
    path = branch_list_file(pid)
    return mutate_json_state(path, lambda: list(_shared_list(path)), fn)


RETIRED = "retired-2026-09-23"


def retire_rolled_back_lists() -> int:
    """Разово відкладає особисті списки, створені до відкату 23.09.2026.

    Особисті списки жили в проді рівно ~35 хвилин (13:44-14:19): деплой
    `7b8f25d` відкотили, і люди далі правили СПІЛЬНИЙ `branches.json` старою
    версією. Копія, яку тоді зробила перша правка, старша за всю ту роботу,
    а `load_branch_list` віддає саме її — тобто після повторного деплою
    людина побачила б свій список станом на 14:19. Тому один раз, до першого
    читання, такі файли перейменовуються (не видаляються — з них можна
    відновити) і людина знову стартує зі спільного. Мітка в корені стану
    робить це разовим: копії, створені вже після деплою, не чіпаються.
    """
    marker = projects.shared_file(f"branches.{RETIRED}")
    if marker.exists():
        return 0
    n = 0
    for p in projects.list_projects():
        for f in projects.state_dir_for(p["id"]).glob("branches.*.json"):
            f.rename(f.with_name(f"{f.name}.{RETIRED}"))
            n += 1
    marker.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    return n


@app.on_event("startup")
def _retire_rolled_back_lists():
    try:
        n = retire_rolled_back_lists()
        if n:
            print(f"[lists] відкладено особистих списків з відкоченого деплою 23.09: {n}")
    except Exception as e:
        print(f"[lists] старі особисті списки не відкладено: {e}")


def all_listed(pid: str | None = None) -> set[str]:
    """Усе, що лежить у будь-чиєму списку проєкту, і закріплені."""
    root = projects.state_dir_for(pid) if pid else projects.state_dir()
    names: set[str] = set()
    for f in root.glob("branches*.json"):
        names |= {x for x in read_json_state(f, []) if isinstance(x, str)}
    names |= {x for x in read_json_state(root / "pinned.json", [])
              if isinstance(x, str)}
    return names


def _with(name: str):
    """Правка «додати в кінець, якщо ще немає» — для обох списків."""
    return lambda names: UNCHANGED if name in names else names + [name]


def _without(name: str):
    return lambda names: [n for n in names if n != name] if name in names else UNCHANGED


class BranchName(BaseModel):
    name: str


def _branch_info(name: str) -> dict:
    try:
        return client.branch(name)
    except Exception as e:
        return {"name": name, "commit": "?", "updated": "",
                "error": f"не знайдено у GitLab: {e}"}


def _resolve_in(cl, name: str) -> dict:
    """Делегат у `projects.resolve_in` — фолбек регістру живе там, бо ним
    користується і черга ClickUp, якій `app` імпортувати не можна."""
    return projects.resolve_in(cl, name)


def resolve_branch(name: str) -> dict:
    """Те саме для АКТИВНОГО проєкту. Повертає info з РЕАЛЬНОЮ назвою вітки
    (бери info["name"], а не вхідний аргумент)."""
    return _resolve_in(client, name)


@app.get("/api/branches")
def branches():
    if MOCK():
        remote = client.branches()
    else:
        # список може мати сотні віток — питаємо GitLab паралельно
        names = load_branch_list()
        if names:
            with projects.Pool(max_workers=12) as ex:
                remote = list(ex.map(_branch_info, names))
        else:
            remote = []
    for b in remote:
        b["synced"] = runner.is_synced(b["name"])
        b["local_files"] = len(runner.snapshot_files(b["name"])) if b["synced"] else 0
    return remote


@app.post("/api/branches/add")
def add_branch(req: BranchName):
    name = req.name.strip().rstrip("/")
    # accept a full GitLab URL and cut the branch name out of it
    for marker in ("/edit/", "/tree/", "/blob/", "/-/branches/"):
        if marker in name:
            name = name.split(marker, 1)[1].split("/")[0]
    if not name:
        raise HTTPException(400, "порожня назва вітки")
    if MOCK():
        raise HTTPException(400, "MOCK MODE: вітки — це папки у fixtures/, додай папку туди")
    try:
        info = resolve_branch(name)
    except Exception as e:
        raise HTTPException(404, f"вітку '{name}' не знайдено у GitLab: {e}")
    name = info["name"]                # реальна назва (фолбек міг дати lowercase)
    mutate_branch_list(_with(name))
    return info


@app.delete("/api/branches/remove")
def remove_branch(name: str):
    mutate_branch_list(_without(name))
    return {"removed": name}


@app.post("/api/branches/clear")
def clear_branches():
    """Empty the working list; snapshots stay in cache/ and show up in the archive."""
    removed: list[str] = []

    def clear(names):
        removed[:] = names
        return []
    mutate_branch_list(clear)
    return {"removed": removed}


# ---------------------------------------------------------------- pinned branches (окремий персистентний набір)


def load_pinned() -> list[str]:
    return read_json_state(projects.state_file("pinned.json"), [])


def mutate_pinned(fn):
    return mutate_json_state(projects.state_file("pinned.json"), list, fn)


@app.get("/api/pinned")
def pinned():
    names = load_pinned()
    if MOCK():
        remote = [b for b in client.branches() if b["name"] in names]
    elif names:
        with projects.Pool(max_workers=12) as ex:
            remote = list(ex.map(_branch_info, names))
    else:
        remote = []
    for b in remote:
        b["synced"] = runner.is_synced(b["name"])
        b["local_files"] = len(runner.snapshot_files(b["name"])) if b["synced"] else 0
    return remote


@app.post("/api/pinned/add")
def pinned_add(req: BranchName):
    name = req.name.strip().rstrip("/")
    for marker in ("/edit/", "/tree/", "/blob/", "/-/branches/"):
        if marker in name:
            name = name.split(marker, 1)[1].split("/")[0]
    if not name:
        raise HTTPException(400, "порожня назва вітки")
    if not MOCK():
        try:
            name = resolve_branch(name)["name"]    # фолбек регістру → реальна назва
        except Exception as e:
            raise HTTPException(404, f"вітку '{name}' не знайдено у GitLab: {e}")
    mutate_pinned(_with(name))
    # закріплена вітка «переїжджає» вниз — прибираємо її з робочого списку
    mutate_branch_list(_without(name))
    return {"pinned": name}


@app.delete("/api/pinned/remove")
def pinned_remove(name: str):
    mutate_pinned(_without(name))
    return {"removed": name}


@app.post("/api/pinned/to_list")
def pinned_to_list(req: BranchName):
    """Повернути закріплену вітку у робочий список (лишається і в закріплених — ні,
    прибираємо з pinned, додаємо у working)."""
    name = req.name.strip()
    mutate_pinned(_without(name))
    mutate_branch_list(_with(name))
    return {"moved": name}


# ---------------------------------------------------------------- archive (cache w/o list entry)
@app.get("/api/archive")
def archive():
    """Snapshots in cache/ that are not on ANYONE's working list."""
    active = ({b["name"] for b in client.branches()} if MOCK()
              else all_listed())
    out = []
    for d in sorted(runner.cache_root().iterdir() if runner.cache_root().exists() else []):
        if not d.is_dir():
            continue
        name = d.name.replace("__", "/")
        meta = d / ".snapshot.json"
        if meta.exists():
            import json
            name = json.loads(meta.read_text(encoding="utf-8")).get("branch", name)
        if name in active:
            continue
        out.append({"name": name,
                    "files": len(runner.snapshot_files(name))})
    return out


@app.post("/api/archive/restore")
def archive_restore(req: BranchName):
    """Put an archived branch back on the working list (no GitLab round-trip)."""
    name = req.name.strip()
    if not runner.is_synced(name):
        raise HTTPException(404, f"немає знімка для '{name}' у cache/")
    mutate_branch_list(_with(name))
    return {"restored": name}


@app.delete("/api/archive/remove")
def archive_remove(name: str):
    """Delete the cached snapshot of an archived branch."""
    d = runner.snapshot_dir(name)
    # Будь-чий список, не лише свій: знімок у чужому списку — це робота
    # колеги, і стерти його звідси означало б висмикнути вітку з-під рук.
    if name in all_listed():
        raise HTTPException(400, "вітка в активному списку — спершу прибери її звідти")
    if d.exists():
        shutil.rmtree(d)
    return {"deleted": name}


@app.post("/api/branches/{branch:path}/sync")
def sync(branch: str, force: int = 0):
    try:
        return runner.sync_branch(client, branch, force=bool(force))
    except runner.UnsavedEdits as e:
        # Не збій, а відповідь: у знімку чиясь незакомічена робота, і sync її
        # не стер. 4xx — щоб текст дійшов до людини: 5xx у проді Cloudflare
        # підміняє власною сторінкою.
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(502, f"sync failed: {e}")


class SyncMultiRequest(BaseModel):
    branches: list[str]
    force: bool = False


@app.post("/api/branches/sync_multi")
def sync_multi(req: SyncMultiRequest):
    """Паралельний sync кількох віток (по 8 одночасно)."""

    def one(br: str) -> dict:
        try:
            return runner.sync_branch(client, br, force=req.force)
        except Exception as e:
            return {"branch": br, "error": str(e)}

    with projects.Pool(max_workers=8) as ex:
        out = list(ex.map(one, req.branches))
    # биту вітку не валимо весь прогін — записуємо у журнал проблем і йдемо далі
    add_problems([{"branch": r["branch"], "source": "sync", "reason": r["error"]}
                  for r in out if r.get("error")])
    return out


# ---------------------------------------------------------------- локальні зміни
# дерево блобів кешується на (проєкт, ref) — повторні перевірки не ходять у GitLab
_TREE_CACHE: dict[tuple, dict] = {}


def _tree_blobs_cached(ref: str) -> dict:
    key = (projects.current_id(), ref)
    if key not in _TREE_CACHE:
        if len(_TREE_CACHE) > 60:
            _TREE_CACHE.pop(next(iter(_TREE_CACHE)))
        _TREE_CACHE[key] = client.tree_blobs(ref)
    return _TREE_CACHE[key]


def _local_ref(branch: str) -> str:
    return runner.snapshot_meta(branch).get("commit") or branch


@app.get("/api/local_changes")
def local_changes(branch: str, diffs: int = 1):
    """Що змінено локально у папці знімка відносно базового коміту."""
    if not runner.is_synced(branch):
        raise HTTPException(404, "вітка не синхронізована — спершу Sync")
    ref = _local_ref(branch)
    try:
        remote = _tree_blobs_cached(ref)
    except Exception as e:
        raise HTTPException(502, f"не вдалося отримати дерево '{ref}' з GitLab: {e}")
    ch = runner.local_changes(branch, remote)

    MAX = 300 * 1024
    files = []
    for status in ("modified", "added", "deleted"):
        for p in ch[status]:
            item = {"path": p, "status": status, "binary": not runner.is_text(p)}
            if diffs and not item["binary"]:
                try:
                    if status == "modified":
                        old = client.file_raw(ref, p).decode("utf-8", "replace")
                        new = runner.read_snapshot_file(branch, p).decode("utf-8", "replace")
                        if len(old) < MAX and len(new) < MAX:
                            # n=2 — показуємо лише змінені рядки + 2 зверху/знизу
                            item.update(_udiff(p, old, new, n=2))
                    elif status == "added":
                        new = runner.read_snapshot_file(branch, p).decode("utf-8", "replace")
                        if len(new) < MAX:
                            item.update(_udiff(p, "", new, n=2))
                    else:
                        item["diff"] = "(файл видалено локально — commit видалить його з вітки)"
                except Exception as e:
                    item["diff"] = f"(diff недоступний: {e})"
            files.append(item)
    return {"branch": branch, "ref": ref, "files": files}


class LocalCommitRequest(BaseModel):
    branch: str
    message: str
    paths: list[str]


@app.post("/api/local_changes/commit")
def local_changes_commit(req: LocalCommitRequest):
    """Комітить обрані локальні зміни у вітку одним комітом."""
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    ref = _local_ref(req.branch)
    ch = runner.local_changes(req.branch, _tree_blobs_cached(ref))
    status_by = {p: s for s in ("added", "modified", "deleted") for p in ch[s]}
    actions = []
    for p in req.paths:
        st = status_by.get(p)
        if not st:
            raise HTTPException(400, f"'{p}' не має локальних змін (онови список)")
        if st == "deleted":
            actions.append({"action": "delete", "file_path": p})
        else:
            data = runner.read_snapshot_file(req.branch, p)
            actions.append({"action": "create" if st == "added" else "update",
                            "file_path": p,
                            "content": base64.b64encode(data).decode(),
                            "encoding": "base64"})
    if not actions:
        raise HTTPException(400, "не обрано жодного файлу")
    try:
        r = client.commit(req.branch, req.message, actions)
    except Exception as e:
        raise HTTPException(502, f"commit failed: {e}")
    log_commit(req.branch, req.message, r.get("id", ""), req.paths, action="local", notes=r.get("lab_notes"))
    return {"committed": True, "commit": r.get("id", ""), "files": req.paths, "notes": r.get("lab_notes") or []}


class LocalDiscardRequest(BaseModel):
    branch: str
    paths: list[str]


@app.post("/api/local_changes/discard")
def local_changes_discard(req: LocalDiscardRequest):
    """Відкидає локальні зміни: відновлює файли зі стану базового коміту,
    додані локально файли — видаляє."""
    ref = _local_ref(req.branch)
    ch = runner.local_changes(req.branch, _tree_blobs_cached(ref))
    status_by = {p: s for s in ("added", "modified", "deleted") for p in ch[s]}
    base = runner.snapshot_dir(req.branch)
    restored, removed = [], []
    for p in req.paths:
        st = status_by.get(p)
        if not st:
            continue
        target = (base / p).resolve()
        if base.resolve() not in target.parents:
            raise HTTPException(400, f"bad path: {p}")
        if st == "added":
            target.unlink(missing_ok=True)
            removed.append(p)
        else:
            try:
                raw = client.file_raw(ref, p)
            except Exception as e:
                raise HTTPException(502, f"не вдалося відновити '{p}': {e}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            restored.append(p)
    return {"restored": restored, "removed": removed}


def can_open_locally() -> bool:
    """Чи справді сервер може відкрити провідник/IDE на екрані людини.

    Поки лаба була локальною, «сервер» і «моя машина» — те саме, і кнопки
    📂 / PhpStorm / VS Code працювали. У контейнері вони безсилі, але
    МОВЧКИ: `xdg-open` в образі Є, `DISPLAY` порожній, а `subprocess.Popen`
    на це не скаржиться — ендпоінт віддавав `200 {"opened": …}`, людина
    чекала вікна, якого не буде (кейс 28.08). Тому питаємо чесно.
    """
    import os
    import shutil
    import sys
    if os.name == "nt" or sys.platform == "darwin":
        return True
    return bool(shutil.which("xdg-open") and os.getenv("DISPLAY", "").strip())


@app.post("/api/open_folder")
def open_folder(branch: str):
    """Відкриває папку локального знімка вітки у файловому менеджері.
    Працює лише коли сервер і екран людини — та сама машина."""
    if not can_open_locally():
        raise HTTPException(400, "лаба працює в контейнері — провідник відкрити "
                                 "нема де. Клади файли через «Файли → ⬆ Залити»")
    d = runner.snapshot_dir(branch)          # traversal-safe (кидає ValueError → 400)
    if not d.exists():
        raise HTTPException(404, "вітка не синхронізована — папки знімка ще немає")
    import os
    import subprocess
    import sys
    try:
        if os.name == "nt":
            os.startfile(str(d))              # Windows Explorer
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(d)])
        else:
            subprocess.Popen(["xdg-open", str(d)])
    except Exception as e:
        raise HTTPException(500, f"не вдалося відкрити папку: {e}")
    return {"opened": str(d)}


@app.get("/api/files")
def files(branch: str):
    lst = runner.snapshot_files(branch)
    if not lst:
        raise HTTPException(404, "branch not synced — press Sync first")
    return lst


# --------------------------------------------- заливка файлів у знімок вітки
# Другий вхід у конвеєр «Локальні зміни». Перший — 📂 у провіднику: людина
# кидає фото в cache/<вітка>/ і комітить їх звідти. У контейнері провідника
# немає, і той вхід зник разом з ним — а це головний спосіб покласти у вітку
# СВОЄ фото (кейс 28.08).
#
# Заливка СВІДОМО НЕ КОМІТИТЬ. Вона кладе файли у знімок, а коміт лишається
# там, де був: «Локальні зміни» → обрати → закомітити одним комітом через
# `log_commit()`. Інакше з'явився б другий шлях у git повз Журнал і revert,
# а це пряма заборона з конвенцій репозиторію.
UPLOAD_MAX_FILE = 15 * 1024 * 1024        # на один файл, у декодованих байтах
UPLOAD_MAX_TOTAL = 40 * 1024 * 1024       # на весь запит


def _safe_upload_name(name: str) -> str:
    """Ім'я файлу з диска користувача — беремо лише останній сегмент."""
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    if not name or name in (".", ".."):
        raise HTTPException(400, f"погане ім'я файлу: {name!r}")
    return name


@app.post("/api/files/upload")
async def files_upload(request: Request):
    """`{branch, dir, items:[{name, content_b64}]}` → файли у знімку вітки.

    Тіло — base64-json, а не multipart: `UploadFile` тягне `python-multipart`,
    тобто нову залежність, а base64-шлях у репо вже вторований
    (`/api/media/upload`). Ціна — +33% до розміру тіла.
    """
    # Розмір перевіряємо ДО розбору: інакше двохсотмегабайтний json встигне
    # лягти в пам'ять процесу, перш ніж ми скажемо «завелико».
    wire_max = UPLOAD_MAX_TOTAL * 4 // 3 + 64 * 1024      # base64 + конверт
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > wire_max:
        raise HTTPException(413, f"завелико: {declared // (1 << 20)} МБ на запит, "
                                 f"межа {UPLOAD_MAX_TOTAL // (1 << 20)} МБ файлами")
    try:
        req = await request.json()
    except Exception:
        raise HTTPException(400, "тіло не є json")

    branch = (req.get("branch") or "").strip()
    items = req.get("items") or []
    if not runner.is_synced(branch):
        raise HTTPException(400, "вітка не синхронізована — спершу Sync")
    if not items:
        raise HTTPException(400, "не передано жодного файлу")

    base = runner.snapshot_dir(branch)                    # traversal-safe
    root = base.resolve()
    sub = (req.get("dir") or "").strip().strip("/")

    decoded, total = [], 0
    for it in items:
        name = _safe_upload_name(it.get("name"))
        rel = f"{sub}/{name}" if sub else name
        target = (base / rel).resolve()
        if root not in target.parents:
            raise HTTPException(400, f"шлях виходить за межі вітки: {rel}")
        try:
            data = base64.b64decode(it.get("content_b64") or "", validate=True)
        except Exception:
            raise HTTPException(400, f"биті base64-дані: {name}")
        if len(data) > UPLOAD_MAX_FILE:
            raise HTTPException(413, f"{name}: {len(data) // (1 << 20)} МБ, "
                                     f"межа {UPLOAD_MAX_FILE // (1 << 20)} МБ на файл")
        total += len(data)
        if total > UPLOAD_MAX_TOTAL:
            raise HTTPException(413, f"разом більше {UPLOAD_MAX_TOTAL // (1 << 20)} МБ")
        decoded.append((target, rel, data))

    # Перегін формату — ТІЛЬКИ коли кладемо ПОВЕРХ наявної картинки: там
    # розширення вже обіцяне віткою, і jpg під іменем hero.webp — реальний
    # випадок (див. media.ensure_format). Для нового файлу ім'я приносить сам
    # файл, тож обіцянку порушити нічим.
    saved, converted = [], []
    for target, rel, data in decoded:
        existed = target.exists()
        if existed and media.is_image_target(rel):
            try:
                data, note = media.ensure_format(data, rel)
            except ValueError as e:
                raise HTTPException(400, f"{rel}: {e}")
            if note:
                converted.append({"path": rel, "note": note})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        saved.append({"path": rel, "status": "replaced" if existed else "created",
                      "size": len(data)})
    return {"branch": branch, "saved": saved, "converted": converted,
            "committed": False}


@app.get("/api/file", response_class=PlainTextResponse)
def file_content(branch: str, path: str):
    p = (runner.snapshot_dir(branch) / path).resolve()
    if runner.snapshot_dir(branch).resolve() not in p.parents:
        raise HTTPException(400, "bad path")
    if not p.exists():
        raise HTTPException(404, "no such file in snapshot")
    if runner.is_text(str(p)):
        return p.read_text(encoding="utf-8", errors="replace")
    mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    return FileResponse(p, media_type=mime)


class SaveFileRequest(BaseModel):
    branch: str
    path: str
    content: str
    message: str


@app.post("/api/file/save")
def file_save(req: SaveFileRequest):
    """Manual edit of one snapshot file -> single commit to the branch."""
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    base = runner.snapshot_dir(req.branch)
    p = (base / req.path).resolve()
    if base.resolve() not in p.parents:
        raise HTTPException(400, "bad path")
    if not p.exists():
        raise HTTPException(404, "no such file in snapshot")
    try:
        result = client.commit(req.branch, req.message, [
            {"action": "update", "file_path": req.path, "content": req.content},
        ])
    except Exception as e:
        raise HTTPException(502, f"commit failed: {e}")
    p.write_text(req.content, encoding="utf-8", newline="")
    log_commit(req.branch, req.message, result.get("id", ""), [req.path], action="edit")
    return {"committed": True, "commit": result.get("id", ""), "path": req.path}


class RenameFileRequest(BaseModel):
    branch: str
    path: str
    new_path: str
    message: str = ""


@app.post("/api/file/rename")
def file_rename(req: RenameFileRequest):
    """Перейменування файла вітки ОДНИМ комітом: move у GitLab + всі
    посилання на старий шлях у текстових файлах переписуються на новий
    (media.retarget_refs) — інакше перейменована картинка лишає биті src."""
    # Перейменування пише ПОВНИЙ вміст усіх сторінок із посиланнями зі знімка:
    # застарілий знімок відкотив би чужі свіжі коміти (ligjo-mepmri 28.10 —
    # полагоджений хедер зник у коміті «chore(cdn): polish.css → …»).
    _require_fresh_snapshot(req.branch)
    base = runner.snapshot_dir(req.branch)
    old_rel = req.path.strip().strip("/")
    new_rel = req.new_path.strip().strip("/").replace("\\", "/")
    if not new_rel or ".." in new_rel.split("/"):
        raise HTTPException(400, "некоректний новий шлях")
    if new_rel == old_rel:
        raise HTTPException(400, "назва не змінилась")
    p = (base / old_rel).resolve()
    np = (base / new_rel).resolve()
    if base.resolve() not in p.parents or base.resolve() not in np.parents:
        raise HTTPException(400, "bad path")
    if not p.exists():
        raise HTTPException(404, "файла немає у знімку — спершу Sync")
    if np.exists():
        raise HTTPException(400, f"файл «{new_rel}» уже існує")
    raw = p.read_bytes()
    actions = [{"action": "move", "previous_path": old_rel,
                "file_path": new_rel,
                "content": base64.b64encode(raw).decode(),
                "encoding": "base64"}]
    texts = {}
    for fp in runner.snapshot_files(req.branch):
        if fp == old_rel or not fp.lower().endswith(media.REF_EXT):
            continue
        try:
            texts[fp] = runner.read_snapshot_file(req.branch, fp).decode("utf-8")
        except Exception:
            continue
    changed = media.retarget_refs(texts, old_rel, new_rel,
                                  runner.snapshot_files(req.branch))
    actions += [{"action": "update", "file_path": fp, "content": t}
                for fp, t in sorted(changed.items())]
    msg = req.message.strip() or f"chore(files): {old_rel} → {new_rel}"
    try:
        result = client.commit(req.branch, msg, actions)
    except Exception as e:
        raise HTTPException(502, f"commit failed: {e}")
    np.parent.mkdir(parents=True, exist_ok=True)
    p.replace(np)
    for fp, t in changed.items():
        (base / fp).write_text(t, encoding="utf-8", newline="")
    log_commit(req.branch, msg, result.get("id", ""),
               [new_rel] + sorted(changed), action="rename-file")
    return {"committed": True, "commit": result.get("id", ""),
            "old": old_rel, "new": new_rel, "refs": sorted(changed)}


class OpenEditorRequest(BaseModel):
    branch: str
    path: str
    line: int = 1
    app: str = "vscode"


@app.post("/api/open_editor")
def open_editor(req: OpenEditorRequest):
    """Відкриває файл знімка у локальному редакторі на вказаному рядку
    (сервер і браузер — одна машина). Біни перевизначаються у .env:
    VSCODE_BIN (default: code) / PHPSTORM_BIN (default: phpstorm64.exe)."""
    import subprocess
    base = runner.snapshot_dir(req.branch)
    p = (base / req.path).resolve()
    if base.resolve() not in p.parents:
        raise HTTPException(400, "bad path")
    if not p.exists():
        raise HTTPException(404, "файла немає у знімку — спершу Sync")
    line = max(1, req.line)
    if req.app == "phpstorm":
        exe = os.getenv("PHPSTORM_BIN", "phpstorm64.exe").strip()
        cmd = f'"{exe}" --line {line} "{p}"'
    elif req.app == "vscode":
        exe = os.getenv("VSCODE_BIN", "code").strip()
        cmd = f'"{exe}" -g "{p}:{line}"'
    else:
        raise HTTPException(400, "app: phpstorm | vscode")
    try:
        # shell — щоб з PATH підхопились code.cmd / phpstorm64.exe без повного шляху
        subprocess.Popen(cmd, shell=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        raise HTTPException(500, f"не вдалося запустити {exe}: {e}")
    return {"opened": req.path, "line": line, "app": req.app}


# ---------------------------------------------------------------- checks
@app.get("/api/checks")
def list_checks():
    """Перевірки АКТИВНОГО проєкту (PROJECTS у .py розмежовує php/node) —
    UI перечитує список при перемиканні проєкту, тож вкладка перемикається сама."""
    return [
        {k: v for k, v in c.items() if k != "module"}
        for c in runner.checks_for_active_project()
    ]


class SetGroupRequest(BaseModel):
    id: str
    group: str            # auto | tests | review


@app.post("/api/checks/set_group")
def checks_set_group(req: SetGroupRequest):
    """Переносить перевірку між групами: править GROUP = "..." у її .py файлі."""
    if req.group not in ("auto", "tests", "review"):
        raise HTTPException(400, "group: auto | tests | review")
    if not re.fullmatch(r"[A-Za-z0-9_]+", req.id):
        raise HTTPException(400, "погане ім'я перевірки")
    p = runner.CHECKS_DIR / f"{req.id}.py"
    if not p.exists():
        raise HTTPException(404, "немає такої перевірки")
    text = p.read_text(encoding="utf-8")
    new_line = f'GROUP = "{req.group}"'
    if re.search(r"(?m)^GROUP\s*=", text):
        text = re.sub(r"(?m)^GROUP\s*=.*$", new_line, text, count=1)
    elif re.search(r"(?m)^NAME\s*=", text):
        text = re.sub(r"(?m)^(NAME\s*=.*)$", r"\1\n" + new_line, text, count=1)
    else:
        text += f"\n{new_line}\n"
    p.write_text(text, encoding="utf-8", newline="")
    return {"id": req.id, "group": req.group}




def load_checks_state() -> dict:
    return read_json_state(projects.state_file("checks_state.json"), {})


@app.post("/api/checks/run")
def run_checks(req: RunChecksRequest):

    def one(br: str) -> dict:
        try:
            # skip-теги таски (02.10): «оставляйте как есть» діє і на ручний
            # прогін — інакше вкладка «Перевірки» лякала б тим, що черга
            # свідомо не чіпає
            skip, src = set(), ""
            try:
                import cu_queue
                skip, src = cu_queue.skip_for_branch(br)
            except Exception:
                pass
            ids = req.check_ids
            cut = []
            if skip:
                base = ids or [c["id"]
                               for c in runner.checks_for_active_project()]
                cut = sorted(set(base) & skip)
                ids = [i for i in base if i not in skip]
                if not ids:
                    return {"branch": br, "files_scanned": 0,
                            "totals": {"error": 0, "warn": 0, "info": 0},
                            "checks": [], "skipped_by_tag": cut,
                            "skip_src": src}
            if not runner.is_synced(br):
                runner.sync_branch(client, br)
            r = runner.run_checks(br, ids)
            if cut:
                r["skipped_by_tag"], r["skip_src"] = cut, src
            return r
        except Exception as e:
            # одна недоступна/перейменована вітка не має валити весь прогін
            return {"branch": br, "error": str(e), "files_scanned": 0,
                    "totals": {"error": 0, "warn": 0, "info": 0},
                    "checks": []}

    with projects.Pool(max_workers=8) as ex:
        out = list(ex.map(one, req.branches))
    # зберігаємо останній прогін по кожній вітці — переживає рестарти/F5.
    # Одною операцією: двоє людей, що ганяли прогін одночасно, доти стирали
    # результати одне одного (кожен дописував свої вітки у СВОЮ копію файла).
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    def put(state):
        for r in out:
            state[r["branch"]] = {**r, "ts": ts}
    mutate_json_state(projects.state_file("checks_state.json"), dict, put)
    # ...і той самий прогін — у append-only реєстр: стан перезаписується і
    # тренду з нього не побудувати, а реєстр тримає історію якості.
    try:
        checks_ledger.record_run(projects.state_dir(),
                                 [{**r, "ts": ts} for r in out])
    except Exception:
        pass                    # аналітика не має валити прогін перевірок
    return out


@app.get("/api/checks/state")
def checks_state():
    return load_checks_state()


@app.get("/api/checks/progress")
def checks_progress(branches: str = ""):
    """Маяк «що саме рахується» по вітках: UI полить його під час прогону,
    щоб гігантська вітка (10+ хв) не виглядала мертвим полем (02.10)."""
    out = {}
    for br in [b for b in branches.split(",") if b.strip()]:
        note = runner._progress_read(br.strip())
        if note:
            out[br.strip()] = note
    return out


# ---------------------------------------------------------------- автофікс перевірок
class FixPreviewRequest(BaseModel):
    branches: list[str]
    check_ids: list[str] | None = None


@app.post("/api/checks/fix/preview")
def fix_preview(req: FixPreviewRequest):

    def one(br: str) -> dict:
        try:
            if not runner.is_synced(br):
                runner.sync_branch(client, br)
            changes = runner.compute_fixes(br, req.check_ids)
        except Exception as e:
            return {"branch": br, "error": str(e), "files_changed": 0, "diffs": []}
        diffs = []
        for c in changes:
            if c.get("type") == "delete":
                diffs.append({"path": c["path"], "hunks": 0, "delete": True,
                              "diff": "(файл буде ВИДАЛЕНО з вітки)",
                              "checks": c["checks"]})
            elif c.get("type") == "create":
                diffs.append({**_udiff(c["path"], "", c["new"]), "create": True,
                              "checks": c["checks"]})
            else:
                diffs.append({**_udiff(c["path"], c["old"], c["new"]),
                              "checks": c["checks"]})
        return {"branch": br, "files_changed": len(changes), "diffs": diffs}

    with projects.Pool(max_workers=8) as ex:
        return list(ex.map(one, req.branches))


class FixApplyRequest(FixPreviewRequest):
    message: str
    selected: dict[str, list[str]] | None = None    # вітка -> шляхи


@app.post("/api/checks/fix/apply")
def fix_apply(req: FixApplyRequest):
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    results = []
    for br in req.branches:
        changes = runner.compute_fixes(br, req.check_ids)
        if req.selected is not None:
            keep = set(req.selected.get(br, []))
            changes = [c for c in changes if c["path"] in keep]
        if not changes:
            results.append({"branch": br, "committed": False, "reason": "no changes"})
            continue
        try:
            r = client.commit(br, req.message, runner.actions_for(changes))
        except Exception as e:
            # У логи — теж. UI показував лише лічильник, тож 20 відмов на проді
            # виглядали як «коміт не працює», і в контейнері не лишалось ані
            # рядка, за яким це можна було б розібрати (кейс 28.08).
            print(f"[fix_apply] {br}: коміт не пройшов — {e}", flush=True)
            results.append({"branch": br, "committed": False, "reason": str(e)})
            continue
        runner.apply_to_snapshot(br, changes)
        log_commit(br, req.message, r.get("id", ""),
                   [c["path"] for c in changes], action="autofix", notes=r.get("lab_notes"))
        results.append({"branch": br, "committed": True, "notes": r.get("lab_notes") or [],
                        "commit": r.get("id", ""), "files": [c["path"] for c in changes]})
    return results


# ------------------------------------------- биті лінки: вибір цілі руками
# `link_target` лагодить лише однозначне. Решта — питання «яка сторінка тут
# мала бути»; відповідає людина, але одним вибором на ВСІ входження лінка.
def _link_files(branch: str) -> tuple[dict, list[str]]:
    import fnmatch
    import checks.link_target as lt
    all_paths = runner.snapshot_files(branch)
    files = {}
    for p in all_paths:
        if any(fnmatch.fnmatch(p.rsplit("/", 1)[-1], pat) for pat in lt.FILES):
            files[p] = runner.read_snapshot_file(branch, p).decode("utf-8", "replace")
    return files, all_paths


@app.get("/api/links/dead")
def links_dead(branch: str):
    """Групи битих лінків вітки: один href — один вибір на всі входження."""
    import checks.link_target as lt
    if not runner.is_synced(branch):
        raise HTTPException(404, "вітка не синхронізована — спершу Sync")
    files, all_paths = _link_files(branch)
    return {"branch": branch, "groups": lt.dead_links(files, all_paths)}


class LinksFixRequest(BaseModel):
    branch: str
    choices: dict[str, str]        # href у розмітці -> файл вітки
    message: str = "Links"


@app.post("/api/links/fix")
def links_fix(req: LinksFixRequest):
    import checks.link_target as lt
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    if not runner.is_synced(req.branch):
        raise HTTPException(404, "вітка не синхронізована — спершу Sync")
    files, all_paths = _link_files(req.branch)
    try:
        actions = lt.apply_choices(files, all_paths, req.choices)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not actions:
        return {"committed": False, "reason": "нема що міняти", "files": []}
    try:
        r = client.commit(req.branch, req.message,
                          [{"action": "update", "file_path": a["path"],
                            "content": a["content"]} for a in actions])
    except Exception as e:
        raise HTTPException(502, f"commit failed: {e}")
    base = runner.snapshot_dir(req.branch)
    for a in actions:
        (base / a["path"]).write_text(a["content"], encoding="utf-8", newline="")
    paths = [a["path"] for a in actions]
    log_commit(req.branch, req.message, r.get("id", ""), paths, action="links")
    return {"committed": True, "commit": r.get("id", ""), "files": paths,
            "links": len(req.choices)}


# ---------------------------------------------------------------- replace
@app.get("/api/transforms")
def transforms():
    return [
        {k: v for k, v in t.items() if k != "module"}
        for t in replacer.load_transforms()
    ]


@app.post("/api/replace/preview")
def replace_preview(req: PreviewRequest):
    if not runner.is_synced(req.branch):
        runner.sync_branch(client, req.branch)
    try:
        return replacer.preview(req.branch, req.model_dump())
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/replace/apply")
def replace_apply(req: ApplyRequest):
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    try:
        r = replacer.apply(
            client, req.branch, req.model_dump(),
            req.message, req.selected_paths,
        )
    except Exception as e:
        raise HTTPException(400, str(e))
    if r.get("committed"):
        log_commit(req.branch, req.message, r.get("commit", ""), r.get("files", []),
                   action="replace")
    return r


class MultiPreviewRequest(ReplaceParams):
    branches: list[str]


@app.post("/api/replace/preview_multi")
def replace_preview_multi(req: MultiPreviewRequest):
    out = []
    for br in req.branches:
        try:
            if not runner.is_synced(br):
                runner.sync_branch(client, br)
            out.append(replacer.preview(br, req.model_dump()))
        except Exception as e:
            out.append({"branch": br, "error": str(e), "files_changed": 0,
                        "hunks": 0, "diffs": []})
    return out


class MultiApplyRequest(MultiPreviewRequest):
    message: str
    selected: dict[str, list[str]] | None = None    # вітка -> шляхи


@app.post("/api/replace/apply_multi")
def replace_apply_multi(req: MultiApplyRequest):
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    results = []
    for br in req.branches:
        sel = req.selected.get(br) if req.selected is not None else None
        if sel is not None and not sel:
            results.append({"branch": br, "committed": False, "reason": "skipped"})
            continue
        try:
            r = replacer.apply(client, br, req.model_dump(), req.message, sel)
        except Exception as e:
            results.append({"branch": br, "committed": False, "reason": str(e)})
            continue
        if r.get("committed"):
            log_commit(br, req.message, r.get("commit", ""), r.get("files", []),
                       action="replace")
        results.append({"branch": br, **r})
    return results


# ---------------------------------------------------------------- пошук по вітці
@app.get("/api/search")
def search(branch: str, q: str, regex: int = 0, ignore_case: int = 1):
    if not q.strip():
        raise HTTPException(400, "порожній запит")
    if not runner.is_synced(branch):
        raise HTTPException(404, "branch not synced")
    try:
        rx = re.compile(q if regex else re.escape(q),
                        re.IGNORECASE if ignore_case else 0)
    except re.error as e:
        raise HTTPException(400, f"поганий regex: {e}")
    matches = []
    for path in runner.snapshot_files(branch):
        if not runner.is_text(path):
            continue
        text = runner.read_snapshot_file(branch, path).decode("utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                matches.append({"path": path, "line": i, "text": line.strip()[:200]})
                if len(matches) >= 500:
                    return {"matches": matches, "truncated": True}
    return {"matches": matches, "truncated": False}


# ---------------------------------------------------------------- diff віток
@app.get("/api/diff")
def branch_diff(a: str, b: str):
    for br in (a, b):
        if not runner.is_synced(br):
            raise HTTPException(404, f"вітка '{br}' не синхронізована")
    fa, fb = set(runner.snapshot_files(a)), set(runner.snapshot_files(b))
    changed, same = [], 0
    for path in sorted(fa & fb):
        ba = runner.read_snapshot_file(a, path)
        bb = runner.read_snapshot_file(b, path)
        if ba == bb:
            same += 1
            continue
        if runner.is_text(path):
            changed.append(_udiff(path,
                                  ba.decode("utf-8", errors="replace"),
                                  bb.decode("utf-8", errors="replace"), a, b))
        else:
            changed.append({"path": path, "hunks": 0,
                            "diff": "(бінарні файли відрізняються)"})
    return {"a": a, "b": b, "only_a": sorted(fa - fb), "only_b": sorted(fb - fa),
            "changed": changed, "same": same}


# ---------------------------------------------------------------- унікальність текстів
_SCRIPT_RX = re.compile(r"<script.*?</script>|<style.*?</style>", re.S | re.I)
_TAG_RX = re.compile(r"<[^>]+>")
_WORD_RX = re.compile(r"[a-zа-яёіїєґ0-9]+", re.I)


def _branch_shingles(branch: str, k: int = 5) -> set[int]:
    """Множина хешів k-слівних шинглів видимого тексту html/php вітки."""
    words: list[str] = []
    for path in runner.snapshot_files(branch):
        if not path.lower().endswith((".html", ".htm", ".php")):
            continue
        text = runner.read_snapshot_file(branch, path).decode("utf-8", errors="replace")
        text = _TAG_RX.sub(" ", _SCRIPT_RX.sub(" ", text))
        words += _WORD_RX.findall(text.lower())
    return {hash(" ".join(words[i:i + k])) for i in range(max(0, len(words) - k + 1))}


class SimilarityRequest(BaseModel):
    branches: list[str]


@app.post("/api/similarity")
def similarity(req: SimilarityRequest):
    brs = [b for b in req.branches if runner.is_synced(b)]
    skipped = [b for b in req.branches if b not in brs]
    sh = {b: _branch_shingles(b) for b in brs}
    pairs = []
    for i in range(len(brs)):
        for j in range(i + 1, len(brs)):
            a, b = sh[brs[i]], sh[brs[j]]
            union = len(a | b)
            sim = (len(a & b) / union) if union else 0.0
            pairs.append({"a": brs[i], "b": brs[j], "similarity": round(sim, 3)})
    pairs.sort(key=lambda p: -p["similarity"])
    return {"branches": len(brs), "skipped": skipped, "pairs": pairs[:300]}


# ---------------------------------------------------------------- редактор трансформів
TRANSFORMS_DIR = Path("transforms")


@app.get("/api/transform_source", response_class=PlainTextResponse)
def transform_source(id: str):
    if not re.fullmatch(r"[A-Za-z0-9_]+", id):
        raise HTTPException(400, "погане ім'я трансформа")
    p = TRANSFORMS_DIR / f"{id}.py"
    if not p.exists():
        raise HTTPException(404, "немає такого трансформа")
    return p.read_text(encoding="utf-8")


class TransformSaveRequest(BaseModel):
    id: str
    content: str


@app.post("/api/transform_save")
def transform_save(req: TransformSaveRequest):
    tid = req.id.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", tid):
        raise HTTPException(400, "ім'я — лише латиниця/цифри/підкреслення, без .py")
    try:
        compile(req.content, f"{tid}.py", "exec")
    except SyntaxError as e:
        raise HTTPException(400, f"синтаксична помилка: рядок {e.lineno}: {e.msg}")
    if "def transform" not in req.content:
        raise HTTPException(400, "у модулі має бути функція transform(path, text)")
    TRANSFORMS_DIR.mkdir(exist_ok=True)
    (TRANSFORMS_DIR / f"{tid}.py").write_text(req.content, encoding="utf-8")
    return {"saved": tid}


# ---------------------------------------------------------------- диск
def _du(p: Path) -> int:
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _archive_dirs() -> list[Path]:
    # Об'єднання ВСІХ списків: цим користується «🧹 архів», і свій список тут
    # означав би знесення робочих знімків колег.
    active = ({b["name"] for b in client.branches()} if MOCK()
              else all_listed())
    out = []
    for d in (runner.cache_root().iterdir() if runner.cache_root().exists() else []):
        if not d.is_dir():
            continue
        name = d.name.replace("__", "/")
        meta = d / ".snapshot.json"
        if meta.exists():
            name = json.loads(meta.read_text(encoding="utf-8")).get("branch", name)
        if name not in active:
            out.append(d)
    return out


@app.get("/api/storage")
def storage():
    arch = _archive_dirs()
    arch_size = sum(_du(d) for d in arch)
    return {
        "cache_total": _du(runner.cache_root()),
        "cache_archive": arch_size,
        "archive_count": len(arch),
        "deploy": _du(deployer.deploy_root()),
        "screens": _du(deployer.screens_root()),
    }


class CleanRequest(BaseModel):
    deploy: bool = False
    screens: bool = False
    archive: bool = False


@app.post("/api/storage/clean")
def storage_clean(req: CleanRequest, request: Request):
    # deploy/ і screens/ — спільні для всіх: чистка гасить чужі деплої і стирає
    # чужі скріни, тому лише адміну. Архів — ні: він рахує списки ВСІХ людей
    # (`all_listed`) і чужого робочого знімка не зачепить.
    if req.deploy or req.screens:
        require_admin(request)
    removed = []
    if req.deploy:
        deployer.stop_all()
        if deployer.deploy_root().exists():
            shutil.rmtree(deployer.deploy_root(), ignore_errors=True)
        removed.append("deploy")
    if req.screens:
        if deployer.screens_root().exists():
            shutil.rmtree(deployer.screens_root(), ignore_errors=True)
        removed.append("screens")
    if req.archive:
        for d in _archive_dirs():
            shutil.rmtree(d, ignore_errors=True)
        removed.append("archive")
    return {"removed": removed, **storage()}


# ---------------------------------------------------------------- скріншоти
@app.get("/api/screens")
def screens():
    return deployer.list_screens()


@app.post("/api/screens/{branch:path}")
def screen_make(branch: str):
    try:
        return deployer.screenshot(branch)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"screenshot failed: {e}")


@app.delete("/api/screens/{branch:path}")
def screen_delete(branch: str):
    return {"deleted": deployer.delete_screens(branch)}


# ---------------------------------------------------------------- lighthouse
@app.get("/api/lighthouse")
def lighthouse_list():
    return {"available": lighthouse_runner.available(),
            "results": lighthouse_runner.list_results()}


@app.post("/api/lighthouse/{branch:path}")
def lighthouse_run(branch: str, form: str = "mobile"):
    try:
        return lighthouse_runner.run(branch, form)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"lighthouse failed: {e}")


@app.get("/api/lighthouse/report", response_class=HTMLResponse)
def lighthouse_report(branch: str, form: str = "mobile"):
    p = lighthouse_runner.report_path(branch, form)
    if not p.exists():
        raise HTTPException(404, "звіту ще немає — спершу прогони Lighthouse")
    return p.read_text(encoding="utf-8")


@app.delete("/api/lighthouse/{branch:path}")
def lighthouse_delete(branch: str, form: str = "mobile"):
    return {"deleted": lighthouse_runner.delete(branch, form)}


# ---------------------------------------------------------------- візуальні перевірки
class VisualRunRequest(BaseModel):
    branches: list[str]
    threshold: float | None = 3.0     # None — стандарт WCAG (4.5 / 3 для великого)
    workers: int | None = None        # скільки віток одночасно (None — VISUAL_WORKERS)
    tests: list[str] | None = None    # ['text','form'] — які перевірки ганяти
    form_data: dict | None = None     # свої дані для форми (інакше FORM_TEST_* з .env)


class VisualProfile(BaseModel):
    name: str
    tests: list[str] | None = None
    threshold: float | None = None
    workers: int | None = None
    form_data: dict | None = None


@app.get("/api/visual")
def visual_list():
    return {"results": visual_runner.list_results()}


@app.get("/api/visual/result")
def visual_result(branch: str):
    """Повний результат з прев'ю «до/після» — важкий, тому окремо від списку."""
    r = visual_runner.load(branch)
    if not r:
        raise HTTPException(404, "прогону ще не було")
    return r


@app.post("/api/visual/run")
def visual_run(req: VisualRunRequest):
    """Вітки скануються ПАРАЛЕЛЬНО: у кожної свій php-порт (вибір порту під
    локом) і свій headless-Chrome, а всередині вітки сторінки розбирають
    кілька табів. Кількість — workers / VISUAL_WORKERS."""
    out = visual_runner.run_many(req.branches, req.threshold, workers=req.workers,
                                 form_data=req.form_data, tests=req.tests)
    bad = [o for o in out if o.get("error")]
    if bad:
        add_problems([{"branch": o["branch"], "source": "visual",
                       "reason": o["error"]} for o in bad])
    return out


@app.get("/api/visual/form-data")
def visual_form_data():
    """Дані, якими заповнюватиметься форма (дефолти + FORM_TEST_* з .env)."""
    return visual_runner.form_test_data()


@app.get("/api/visual/profiles")
def visual_profiles():
    """Профілі прогону: що ганяти, з яким порогом і якими даними форми."""
    return {"profiles": visual_runner.load_profiles(),
            "form_defaults": visual_runner.form_test_data()}


@app.put("/api/visual/profiles")
def visual_profile_save(p: VisualProfile):
    try:
        return {"profiles": visual_runner.save_profile(p.model_dump())}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/visual/profiles/{name}")
def visual_profile_delete(name: str):
    return {"profiles": visual_runner.delete_profile(name)}


# ------------------------------------------------------- підготовка головної під форму
class PrepareRequest(BaseModel):
    branches: list[str]
    blocks: bool = True
    forms: bool = True
    links: bool = True
    rename: bool = True


class PrepareApplyRequest(PrepareRequest):
    message: str = "Prepare main page for form script"
    selected: dict[str, list[str]] | None = None    # вітка -> шляхи


@app.post("/api/prepare/preview")
def prepare_preview(req: PrepareRequest):

    def one(br: str) -> dict:
        try:
            if not runner.is_synced(br):
                runner.sync_branch(client, br)
            r = prepare_main.compute_fixes(br, req.blocks, req.forms, req.links, req.rename)
        except Exception as e:
            return {"branch": br, "error": str(e)[:300], "files_changed": 0, "diffs": []}
        diffs = []
        for a in r["actions"]:
            if a["type"] == "delete":
                diffs.append({"path": a["path"], "hunks": 0, "delete": True,
                              "diff": "(файл буде ВИДАЛЕНО з вітки)"})
            elif a["type"] == "create":
                diffs.append({**_udiff(a["path"], "", a["new"]), "create": True})
            else:
                diffs.append({**_udiff(a["path"], a["old"], a["new"])})
        return {"branch": br, "main": r["main"], "files_changed": len(r["actions"]),
                "diffs": diffs, "applied": r["applied"], "skipped": r["skipped"]}

    with projects.Pool(max_workers=8) as ex:
        return list(ex.map(one, req.branches))


@app.post("/api/prepare/apply")
def prepare_apply(req: PrepareApplyRequest):
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    results = []
    for br in req.branches:
        try:
            r = prepare_main.compute_fixes(br, req.blocks, req.forms, req.links, req.rename)
        except Exception as e:
            results.append({"branch": br, "committed": False, "reason": str(e)[:300]})
            continue
        actions_src = r["actions"]
        if req.selected is not None:
            keep = set(req.selected.get(br, []))
            actions_src = [a for a in actions_src if a["path"] in keep]
        if not actions_src:
            results.append({"branch": br, "committed": False, "reason": "no changes"})
            continue
        actions = []
        for a in actions_src:
            if a["type"] == "delete":
                actions.append({"action": "delete", "file_path": a["path"]})
            elif a["type"] == "create":
                actions.append({"action": "create", "file_path": a["path"],
                                "content": a["new"]})
            else:
                actions.append({"action": "update", "file_path": a["path"],
                                "content": a["new"]})
        try:
            c = client.commit(br, req.message, actions)
        except Exception as e:
            results.append({"branch": br, "committed": False, "reason": str(e)})
            continue
        base = runner.snapshot_dir(br)
        for a in actions_src:
            target = base / a["path"]
            if a["type"] == "delete":
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(a["new"], encoding="utf-8", newline="")
        log_commit(br, req.message, c.get("id", ""),
                   [a["path"] for a in actions_src], action="prepare-main")
        try:
            runner.set_snapshot_commit(br, c.get("id", "")[:8])
        except Exception:
            pass
        results.append({"branch": br, "committed": True,
                        "commit": c.get("id", ""), "files": [a["path"] for a in actions_src]})
    return results


# ------------------------------------------------------- переклад чужомовних фрагментів
class TranslateScanRequest(BaseModel):
    branches: list[str]
    drafts: bool = True


class TranslateApplyRequest(BaseModel):
    branch: str
    edits: list[dict]
    message: str = "Translate foreign fragments"


@app.post("/api/translate/scan")
def translate_scan(req: TranslateScanRequest):
    """Послідовно, а не паралельно: scan ходить у зовнішній API перекладу
    (MyMemory) — паралельні запити по вітках можуть впертися в rate limit."""
    out = []
    for br in req.branches:
        try:
            out.append(translate_text.scan(br, req.drafts))
        except Exception as e:
            out.append({"branch": br, "error": str(e)[:300], "items": [], "skipped": []})
    return out


@app.post("/api/translate/apply")
def translate_apply(req: TranslateApplyRequest):
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    r = translate_text.apply_edits(req.branch, req.edits)
    actions_src = r["actions"]
    if not actions_src:
        return {"committed": False, "applied": 0, "reason": "no changes", "skipped": r["skipped"]}
    actions = [{"action": "update", "file_path": a["path"], "content": a["new"]}
               for a in actions_src]
    c = client.commit(req.branch, req.message, actions)
    base = runner.snapshot_dir(req.branch)
    for a in actions_src:
        target = base / a["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(a["new"], encoding="utf-8", newline="")
    log_commit(req.branch, req.message, c.get("id", ""),
               [a["path"] for a in actions_src], action="translate")
    try:
        runner.set_snapshot_commit(req.branch, c.get("id", "")[:8])
    except Exception:
        pass
    return {"committed": True, "commit": c.get("id", ""), "applied": len(actions_src),
            "files": [a["path"] for a in actions_src], "skipped": r["skipped"]}


class VisualFixRequest(BaseModel):
    branches: list[str]
    fids: list[str] | None = None      # None — усі знахідки з готовим фіксом


class VisualFixApplyRequest(VisualFixRequest):
    message: str = "Fix text contrast"


def _visual_fix(branch: str, fids: list[str] | None) -> dict:
    r = visual_runner.compute_fixes(branch, fids)
    diffs = [_udiff(p, old, new, n=2) for p, (old, new) in r["edits"].items()]
    return {"branch": branch, "files_changed": len(r["edits"]), "diffs": diffs,
            "applied": r["applied"], "skipped": r["skipped"]}


@app.post("/api/visual/fix/preview")
def visual_fix_preview(req: VisualFixRequest):
    out = []
    for br in req.branches:
        try:
            out.append(_visual_fix(br, req.fids))
        except Exception as e:
            out.append({"branch": br, "error": str(e)[:300],
                        "files_changed": 0, "diffs": []})
    return out


@app.post("/api/visual/fix/apply")
def visual_fix_apply(req: VisualFixApplyRequest):
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    results = []
    for br in req.branches:
        try:
            r = visual_runner.compute_fixes(br, req.fids)
        except Exception as e:
            results.append({"branch": br, "committed": False, "reason": str(e)[:200]})
            continue
        if not r["edits"]:
            results.append({"branch": br, "committed": False,
                            "reason": "нема що правити", "skipped": r["skipped"]})
            continue
        actions = [{"action": "update", "file_path": p, "content": new}
                   for p, (_old, new) in r["edits"].items()]
        try:
            c = client.commit(br, req.message, actions)
        except Exception as e:
            results.append({"branch": br, "committed": False, "reason": str(e)[:200]})
            continue
        base = runner.snapshot_dir(br)
        for p, (_old, new) in r["edits"].items():
            (base / p).write_text(new, encoding="utf-8", newline="")
        paths = sorted(r["edits"])
        log_commit(br, req.message, c.get("id", ""), paths, action="visual-fix", notes=c.get("lab_notes"))
        # результат застарів — кольори у знімку вже інші
        visual_runner.delete(br)
        results.append({"branch": br, "committed": True, "commit": c.get("id", ""),
                        "files": paths, "fixed": len(r["applied"]), "notes": c.get("lab_notes") or [],
                        "skipped": r["skipped"]})
    return results


@app.delete("/api/visual/{branch:path}")
def visual_delete(branch: str):
    return {"deleted": visual_runner.delete(branch)}


# ---------------------------------------------------------------- кнопки: мертві → видалити
class ButtonsRunRequest(BaseModel):
    branches: list[str]
    workers: int | None = None


class ButtonsFixApplyRequest(VisualFixRequest):
    message: str = "Remove dead buttons"


@app.get("/api/buttons")
def buttons_list():
    return {"results": buttons_runner.list_results()}


@app.get("/api/buttons/result")
def buttons_result(branch: str):
    r = buttons_runner.load(branch)
    if not r:
        raise HTTPException(404, "прогону ще не було")
    return r


@app.post("/api/buttons/run")
def buttons_run(req: ButtonsRunRequest):
    out = buttons_runner.run_many(req.branches, workers=req.workers)
    bad = [o for o in out if o.get("error")]
    if bad:
        add_problems([{"branch": o["branch"], "source": "buttons",
                       "reason": o["error"]} for o in bad])
    return out


@app.post("/api/buttons/fix/preview")
def buttons_fix_preview(req: VisualFixRequest):
    out = []
    for br in req.branches:
        try:
            r = buttons_runner.compute_fixes(br, req.fids)
            out.append({"branch": br, "files_changed": len(r["edits"]),
                        "diffs": [_udiff(p, old, new, n=2) for p, (old, new) in r["edits"].items()],
                        "applied": r["applied"], "skipped": r["skipped"]})
        except Exception as e:
            out.append({"branch": br, "error": str(e)[:300], "files_changed": 0, "diffs": []})
    return out


@app.post("/api/buttons/fix/apply")
def buttons_fix_apply(req: ButtonsFixApplyRequest):
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    results = []
    for br in req.branches:
        try:
            r = buttons_runner.compute_fixes(br, req.fids)
        except Exception as e:
            results.append({"branch": br, "committed": False, "reason": str(e)[:200]})
            continue
        if not r["edits"]:
            results.append({"branch": br, "committed": False,
                            "reason": "нема що правити", "skipped": r["skipped"]})
            continue
        actions = [{"action": "update", "file_path": p, "content": new}
                   for p, (_old, new) in r["edits"].items()]
        try:
            c = client.commit(br, req.message, actions)
        except Exception as e:
            results.append({"branch": br, "committed": False, "reason": str(e)[:200]})
            continue
        base = runner.snapshot_dir(br)
        for p, (_old, new) in r["edits"].items():
            (base / p).write_text(new, encoding="utf-8", newline="")
        paths = sorted(r["edits"])
        log_commit(br, req.message, c.get("id", ""), paths, action="buttons-fix", notes=c.get("lab_notes"))
        try:
            runner.set_snapshot_commit(br, c.get("id", "")[:8])
        except Exception:
            pass
        buttons_runner.forget(br, [a["fid"] for a in r["applied"]])
        results.append({"branch": br, "committed": True, "commit": c.get("id", ""),
                        "files": paths, "fixed": len(r["applied"]), "notes": c.get("lab_notes") or [],
                        "skipped": r["skipped"]})
    return results


@app.delete("/api/buttons/{branch:path}")
def buttons_delete(branch: str):
    return {"deleted": buttons_runner.delete(branch)}



@app.get("/api/screens/file")
def screen_file(branch: str, kind: str = "desktop"):
    if kind not in ("desktop", "mobile"):
        raise HTTPException(400, "kind: desktop | mobile")
    p = deployer.screenshot_path(branch, kind)
    if not p.exists():
        raise HTTPException(404, "скріншота ще немає")
    return FileResponse(p, media_type="image/png")


# ---------------------------------------------------------------- історія комітів / відкат файлу
@app.get("/api/commits")
def commits(branch: str, limit: int = 20):
    try:
        return client.commits(branch, limit)
    except Exception as e:
        raise HTTPException(502, f"GitLab error: {e}")


@app.get("/api/commit_diff")
def commit_diff(sha: str):
    try:
        return client.commit_diff(sha)
    except Exception as e:
        raise HTTPException(502, f"GitLab error: {e}")


class RollbackFileRequest(BaseModel):
    branch: str
    path: str
    ref: str            # sha коміту, до стану якого повертаємо файл


@app.post("/api/file/rollback")
def file_rollback(req: RollbackFileRequest):
    try:
        raw = client.file_raw(req.ref, req.path)
    except Exception as e:
        raise HTTPException(404, f"файла '{req.path}' немає у коміті {req.ref[:10]}: {e}")
    msg = f"restore {req.path} from {req.ref[:10]}"
    try:
        result = client.commit(req.branch, msg, [
            {"action": "update", "file_path": req.path,
             "content": base64.b64encode(raw).decode(), "encoding": "base64"},
        ])
    except Exception as e:
        raise HTTPException(502, f"commit failed: {e}")
    base = runner.snapshot_dir(req.branch)
    if base.exists():
        target = base / req.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    log_commit(req.branch, msg, result.get("id", ""), [req.path], action="rollback")
    return {"committed": True, "commit": result.get("id", ""), "path": req.path}


# ---------------------------------------------------------------- пошук по кількох вітках
class SearchMultiRequest(BaseModel):
    branches: list[str]
    q: str
    regex: bool = False
    ignore_case: bool = True


@app.post("/api/search_multi")
def search_multi(req: SearchMultiRequest):
    if not req.q.strip():
        raise HTTPException(400, "порожній запит")
    try:
        rx = re.compile(req.q if req.regex else re.escape(req.q),
                        re.IGNORECASE if req.ignore_case else 0)
    except re.error as e:
        raise HTTPException(400, f"поганий regex: {e}")
    matches, skipped = [], []
    for br in req.branches:
        if not runner.is_synced(br):
            skipped.append(br)
            continue
        for path in runner.snapshot_files(br):
            if not runner.is_text(path):
                continue
            text = runner.read_snapshot_file(br, path).decode("utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    matches.append({"branch": br, "path": path, "line": i,
                                    "text": line.strip()[:200]})
                    if len(matches) >= 1000:
                        return {"matches": matches, "truncated": True, "skipped": skipped}
    return {"matches": matches, "truncated": False, "skipped": skipped}


# ---------------------------------------------------------------- clickup


def load_cu_map() -> dict:
    return read_json_state(projects.state_file("clickup_map.json"), {})


def _personal_cu_scan(token: str, closed: bool) -> tuple:
    """Розшарені персонально таски — особистим токеном. Тільки вони.

    Вʼю і team ходять застосунковим токеном з CI і без цього кроку: особистий
    токен потрібен рівно там, де застосунковий безсилий за конструкцією —
    таску, віддану людині персонально, не показує ні team, ні вʼю нікому,
    крім неї самої.

    Помилку НЕ піднімає — повертає її рядком.

    Це і є весь фоллбек: особистий токен може протухнути, втратити доступ або
    просто бути з одруківкою, і жоден з цих випадків не має гасити видачу
    застосункового акаунта. Гірше за «менше тасок» лише «жодної таски і
    незрозуміло чому».
    """
    try:
        return clickup_client.fetch_shared(token, include_closed=closed), ""
    except Exception as e:
        return [], str(e)[-200:]


@app.get("/api/clickup/tasks")
def clickup_tasks(request: Request, closed: int = 0):
    """Скан воркспейсу: `{"tasks": [...], "skipped": [...]}`.

    `skipped` — вʼю, до яких у токена немає доступу. Вони не валять скан
    (див. `clickup_client.fetch_all`), але й не мовчать: UI показує їх
    тостом, інакше вкладка просто збідніла б без жодного пояснення.

    Код помилки — 400, а не 502, і це не педантизм. Заміряно 01.09.2026:
    502 від нас доїжджає до браузера ВЛАСНОЮ сторінкою Cloudflare, тіло з
    поясненням гине по дорозі, і в тості лишається голе «Bad Gateway».
    Тобто єдиний рядок, заради якого варто дивитись, з'їдався саме тоді,
    коли він потрібен."""

    me = current_user(request)
    uid = auth.uid_of(me) if me else ""
    my_token = users.clickup_token_of(me)

    skipped: list[dict] = []
    # Два скани йдуть ОДНОЧАСНО, і це не оптимізація заради оптимізації:
    # ліміт ClickUp (100 запитів/хв) рахується на токен, тож у двох токенів
    # два кошики, а загальний час лишається часом найповільнішого джерела.
    with projects.Pool(max_workers=2) as ex:
        f_mine = ex.submit(_personal_cu_scan, my_token, bool(closed)) if my_token else None
        try:
            tasks = clickup_client.fetch_all(include_closed=bool(closed),
                                             skipped=skipped)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"ClickUp error: {e}")
        mine, mine_err = f_mine.result() if f_mine else ([], "")

    personal = {"used": bool(my_token), "added": 0, "error": mine_err}
    if my_token:
        seen = {t["id"] for t in tasks}
        for t in mine:
            if t["id"] in seen:
                continue
            # Штамп потрібен не для показу, а для збереження: за ним
            # `/api/clickup/saved` кладе таску в особистий файл, а не в
            # спільний (див. _cu_saved).
            t["via"], t["via_user"] = "personal", uid
            tasks.append(t)
            personal["added"] += 1
        if mine_err:
            skipped.append({"view": "особистий токен", "reason": mine_err})
            users.note_clickup_error(uid, mine_err)
        elif (me or {}).get("clickup_error"):
            users.store().update(uid, {"clickup_error": None})
            auth.invalidate(uid)
    return {"tasks": tasks, "skipped": skipped, "personal": personal}


@app.get("/api/clickup/map")
def clickup_map():
    return load_cu_map()


# -------------------------------------------- QA-нотатки з коментарів тасок
class QaNotesRequest(BaseModel):
    branches: list[str]


QA_NOTES = "qa_notes.json"


@app.get("/api/cu/qa_notes")
def qa_notes_state():
    """Кеш розпарсених QA-коментарів: {вітка: {task_id, task_url, user,
    date, domain, items:[{label,text}], fetched}}. Рендер карток читає
    тільки звідси — у ClickUp ходить лише кнопка оновлення."""
    return read_json_state(projects.state_file(QA_NOTES), {})


@app.post("/api/cu/qa_notes")
def qa_notes_fetch(req: QaNotesRequest):
    """Тягне коментарі тасок для віток і парсить блоки фіксів (cu_qa).

    Вітка без таски у мапі або без блоку в коментарях пише запис-пустушку
    з причиною — щоб кнопка чесно казала «нема що парсити», а не мовчала."""
    import cu_qa
    cu = load_cu_map()
    headers = {"Authorization": clickup_client._cfg("")["token"]}
    out = {}
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    for br in req.branches[:40]:
        row = cu.get(br) or {}
        task_id = row.get("task_id")
        if not task_id:
            out[br] = {"error": "вітка не прив'язана до таски ClickUp"}
            continue
        try:
            _, _, comments = clickup_client._comments_info(task_id, headers)
        except Exception as e:
            out[br] = {"error": f"коментарі не читаються: {str(e)[-120:]}"}
            continue
        note = cu_qa.pick_comment(comments, br)
        if not note:
            out[br] = {"error": "у коментарях таски немає блоку цієї вітки"}
            continue
        out[br] = {"task_id": task_id, "task_url": row.get("task_url", ""),
                   "fetched": ts, **note}
    mutate_json_state(projects.state_file(QA_NOTES), dict,
                      lambda old: {**old, **out})
    return out


@app.get("/api/geo_db")
def geo_db():
    """Гео-бази лаби одним махом: адреси (geo_addresses.json) і телефони
    (geo_phones.json) по локалях — вкладка «Журнал → БД по гео». CNPJ-пул
    br-pt живе окремо (/api/cnpj) і рендериться поряд."""
    import json as _json
    from pathlib import Path as _Path
    root = _Path(__file__).resolve().parent
    def _load(name):
        try:
            d = _json.loads((root / name).read_text(encoding="utf-8"))
            return {k: v for k, v in d.items()
                    if not k.startswith("_") and isinstance(v, list)}
        except Exception:
            return {}
    addresses = _load("geo_addresses.json")
    phones = _load("geo_phones.json")
    locales = sorted(set(addresses) | set(phones))
    return {"locales": locales, "addresses": addresses, "phones": phones}



@app.get("/api/domain_drift")
def domain_drift(branch: str, domain: str = ""):
    """Чи збігається живий домен з віткою: 01.10 фото «не мінялись на
    домені», бо домен тримав реліз 22.09 — вітки передеплоюються на прод
    зовнішнім процесом, і без такої перевірки дрейф видно лише оком.

    Порівнюємо по якорях: img-src і заголовок головної вітки мають бути
    на домені. Повертає verdict + розбіжності, нічого не кешує."""
    row = load_cu_map().get(branch) or {}
    domain = (domain or row.get("domain") or "").strip()
    if not domain:
        import domains as _doms
        domain = (_doms.active_for(branch) or "").strip()
    if not domain:
        raise HTTPException(400, "у вітки немає домену в мапі ClickUp")
    if not runner.is_synced(branch):
        runner.sync_branch(client, branch)
    idx_name = next((n for n in ("index.html", "index.php", "index.htm")
                     if n in set(runner.snapshot_files(branch))), None)
    if not idx_name:
        raise HTTPException(400, "у знімку вітки немає index-сторінки")
    body = runner.read_snapshot_file(branch, idx_name).decode("utf-8", "replace")
    import requests as _rq
    try:
        r = _rq.get(f"https://{domain}/", timeout=12,
                    headers={"User-Agent": "Mozilla/5.0 (qa_lab drift)"})
        live = r.text
    except Exception as e:
        return {"branch": branch, "domain": domain, "status": "unreachable",
                "error": str(e)[:160]}
    anchors = []
    for m in re.finditer(r'src="([^"]+\.(?:jpe?g|webp|png|svg)[^"]*)"', body):
        anchors.append(("img", m.group(1)))
        if len(anchors) >= 6:
            break
    m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
    if m:
        h1 = re.sub(r"<[^>]+>|\s+", " ", m.group(1)).strip()[:60]
        if h1:
            anchors.append(("h1", h1))
    # текст лого-лінка хедера: фікси напису (латинізація, назва) живуть у
    # span — img/h1 їх не бачать, і стара назва на домені давала б «fresh»
    m = re.search(r'<a\b[^>]*href="\.?/"[^>]*>(.*?)</a\s*>', body, re.S | re.I)
    if m:
        logo = re.sub(r"<[^>]+>|\s+", " ", m.group(1)).strip()[:50]
        if len(logo) >= 3:
            anchors.append(("logo", logo))
    missing = [{"kind": k, "value": v} for k, v in anchors if v not in live]
    fresh = not missing
    return {"branch": branch, "domain": domain,
            "status": "fresh" if fresh else "stale",
            "checked": len(anchors), "missing": missing}

# Останній скан тасок — переживає рестарти сервера і F5 у браузері, і НЕ
# залежить від активного проєкту: `clickup_client.fetch_all()` читає той самий
# токен і те саме вʼю незалежно від того, php-вайти зараз відкриті чи vue.
CU_TASKS = "clickup_tasks.json"


def _adopt_cu_scan():
    """Переїзд скану з тек проєктів у спільний файл.

    Доки скан лежав у теці проєкту, кожне перемикання показувало інший скан і
    змушувало парсити ClickUp заново. Переносимо НАЙСВІЖІШИЙ за `ts` і
    прибираємо проєктні копії, щоб не лишалось із чого дрейфувати. Окремого
    прапорця «уже переїхали» не тримаємо: після переїзду копій немає, і виклик
    виходить на першій перевірці.
    """
    shared = projects.shared_file(CU_TASKS)
    copies = projects.project_copies(CU_TASKS)
    if not copies:
        return

    def read(p):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) and d.get("tasks") else None
        except Exception:
            return None

    cands = [(d, p) for d, p in ((read(p), p) for p in [shared] + copies) if d]
    if cands:
        best = max(cands, key=lambda dp: dp[0].get("ts") or "")[0]
        shared.write_text(json.dumps(best, ensure_ascii=False), encoding="utf-8")
    for p in copies:
        try:
            p.unlink()
        except OSError:
            pass


# Особисті таски (розшарені персонально) лежать ОКРЕМО від спільного скану,
# по файлу на людину. Дві причини, обидві практичні:
#   * приватність: таска, віддана персонально Петрові, не має з'являтись у
#     Марії тільки тому, що Петро натиснув «Сканувати»;
#   * збереження: спільний файл перезаписується цілком, тож скан Марії (без
#     особистого токена) стер би Петрові таски. Це рівно та пастка, через яку
#     01.09 писався `683c305`, — тільки тут вона спрацьовувала б щодня.
def _cu_personal_file(uid: str):
    return projects.shared_file(f"clickup_tasks.{uid}.json")


def _read_cu(path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"ts": None, "tasks": []}


def _cu_saved(uid: str = "") -> dict:
    """Спільний скан + власні особисті таски. Спільний виграє за збігом id —
    той самий порядок, що й у злитті джерел усередині `fetch_all`."""
    _adopt_cu_scan()
    data = _read_cu(projects.shared_file(CU_TASKS))
    if not uid:
        return data
    mine = _read_cu(_cu_personal_file(uid))
    if not mine["tasks"]:
        return data
    seen = {t.get("id") for t in data["tasks"]}
    data = {"ts": max(x for x in (data["ts"], mine["ts"]) if x) if (data["ts"] or mine["ts"]) else None,
            "tasks": data["tasks"] + [t for t in mine["tasks"] if t.get("id") not in seen]}
    return data


@app.get("/api/clickup/saved")
def clickup_saved(request: Request):
    return _cu_saved(auth.uid_of(current_user(request)))


class ClickUpSaveRequest(BaseModel):
    tasks: list[dict]


@app.post("/api/clickup/saved")
def clickup_save(req: ClickUpSaveRequest, request: Request):
    import comment_themes
    _adopt_cu_scan()
    uid = auth.uid_of(current_user(request))
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    # Розкладаємо за штампом, який поставив сам скан (`clickup_tasks`).
    # Чужі особисті файли не чіпаються ніколи: сюди потрапляє лише те, що
    # позначене цим самим uid.
    mine = [t for t in req.tasks if t.get("via_user") and t.get("via_user") == uid]
    shared = [t for t in req.tasks if not t.get("via_user")]
    if uid:
        _cu_personal_file(uid).write_text(
            json.dumps({"ts": ts, "tasks": mine}, ensure_ascii=False), encoding="utf-8")
    data = {"ts": ts, "tasks": shared}
    projects.shared_file(CU_TASKS).write_text(json.dumps(data, ensure_ascii=False),
                                              encoding="utf-8")
    # заявки на фікс картинок живуть у коментарях цих же тасок — оновлюємо
    # кеш «вітка → тема» тут, щоб «Медіа» не ходило в ClickUp на кожен скан
    try:
        themes = comment_themes.refresh(req.tasks)
    except Exception:
        themes = {}
    return {"saved": len(req.tasks), "personal": len(mine),
            "ts": ts, "themes": len(themes)}


class ClickUpLinksRequest(BaseModel):
    links: list[str]
    comments: bool = True     # False = без коментарів (удвічі менше запитів до ClickUp)


@app.post("/api/clickup/by_links")
def clickup_by_links(req: ClickUpLinksRequest, request: Request):
    import re as _re
    items = []
    for l in req.links:
        l = l.strip()
        if not l:
            continue
        # /t/<team>/<CUSTOM-ID> (кастомні id) або /t/<id> (звичайні)
        m = _re.search(r"/t/(\d+)/([A-Za-z0-9\-_]+)", l)
        if m:
            items.append({"id": m.group(2), "team": m.group(1)})
            continue
        m = _re.search(r"/t/([A-Za-z0-9\-_]+)", l)
        items.append({"id": m.group(1) if m else l})
    if not items:
        raise HTTPException(400, "порожній список лінків")
    try:
        got = clickup_client.fetch_by_ids(items, with_comments=req.comments)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"ClickUp error: {e}")

    # Таска, розшарена людині персонально, застосунковому акаунту віддає 401 —
    # і в картці замість вмісту з'являється «не знайдено або немає доступу».
    # Добираємо саме такі і саме особистим токеном: без цього кроку розшарені
    # таски було б видно у списку, але не можна було б розгорнути.
    my_token = users.clickup_token_of(current_user(request))
    denied = [i for i, t in enumerate(got) if t.get("no_access")]
    if my_token and denied:
        retry = clickup_client.fetch_by_ids(
            [{"id": got[i]["id"]} for i in denied],
            with_comments=req.comments, token=my_token)
        for i, t in zip(denied, retry):
            if not t.get("no_access") and not t.get("enrich_failed"):
                got[i] = {**t, "via": "personal"}
    # «Fixed уже є» (24.09.2026): коментарі вже прочитано, тож нотатка для
    # картки і запис на спільну дошку не коштують жодного запиту в ClickUp.
    # Збій тут не має валити довантаження тасок — це лише підказка.
    try:
        for t in got:
            if isinstance(t.get("comments"), list):
                t["fixed"] = cu_fixed.fixed_note(t)
        cu_fixed.learn(got)
    except Exception as e:
        print(f"[fixed] нотатки не пораховано: {e}", flush=True)
    return got


class ClickUpCompleteRequest(BaseModel):
    task_id: str
    comment: str = "fixed"
    checklist: bool = True          # чи проставляти чекліст whites
    tag_user_id: int | None = None  # якщо задано — @тег автора у коментарі
    tag_username: str = ""


@app.post("/api/clickup/complete")
def clickup_complete(req: ClickUpCompleteRequest, request: Request):
    """Коментар (+ чекліст) у таску. Підпис дописує `comment_body()`.

    Пишемо застосунковим акаунтом — щоб «fixed» у тасках виглядав однаково від
    усіх. Але таску, розшарену людині персонально, він не бачить і дістає 401,
    тож на відмову доступу пробуємо ще раз її токеном: інакше кнопка на такій
    картці мовчки не працює.
    """
    me = current_user(request)
    kw = dict(checklist=req.checklist, tag_user_id=req.tag_user_id,
              tag_username=req.tag_username, actor=me)
    try:
        return {**clickup_client.complete_task(req.task_id, req.comment, **kw),
                "as": "app"}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        my_token = users.clickup_token_of(me)
        denied = getattr(getattr(e, "response", None), "status_code", 0) in (401, 403)
        if not (my_token and denied):
            raise HTTPException(400, f"ClickUp error: {e}")
        try:
            return {**clickup_client.complete_task(req.task_id, req.comment,
                                                   token=my_token, **kw),
                    "as": "personal"}
        except Exception as e2:
            raise HTTPException(400, f"ClickUp error: {e2}")

# ---------------------------------------------------------------- telegram-бот
@app.get("/api/telegram/status")
def telegram_status():
    return tg_watcher.status()


@app.get("/api/telegram/discover_chat")
def telegram_discover_chat():
    """Напиши боту будь-що і виклич це — покаже chat_id для .env."""
    try:
        return telegram_bot.discover_chat()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Telegram error: {e}")


class TelegramTestRequest(BaseModel):
    text: str = "qa_lab: тест зв'язку ✅"


@app.post("/api/telegram/test")
def telegram_test(req: TelegramTestRequest):
    try:
        telegram_bot.send(req.text)
        return {"sent": True}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Telegram error: {e}")


@app.post("/api/telegram/run_now")
def telegram_run_now(force: int = 1):
    """Прогнати аналіз зараз (force=1 — надіслати, навіть якщо нових нема)."""
    try:
        return tg_watcher.run_once(read_json_state, write_json_state, force=bool(force))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"помилка прогону: {e}")


class ClickUpImportRequest(BaseModel):
    tasks: list[dict]        # [{id, name, url, branches: [...]}]
    replace: bool = False    # True = спершу очистити список віток


def _adopt_elsewhere(failed: list[dict]) -> list[dict]:
    """Вітки, яких немає в АКТИВНОМУ проєкті, шукає в інших і заводить туди —
    у список тієї самої людини, з таскою ClickUp і доменом.

    Причина: таска не каже, якого типу вайт. Vue-вайти регулярно заводять у
    php-проєкт, і весь батч падав у «Проблеми» з 404, хоча гілки існують —
    просто в іншому репо (заміряно: 20 з 20 проблемних віток журналу лежали
    у development/new-white-front). До 21.09.2026 перенос ішов лише php → vue,
    тож людина у vue отримувала php-вітки таски в «Проблеми»: «Когда импорт
    идет на обычных вайтах, оно закидывает во VUE, но наоборот нет» (задача
    колеги-QA того дня). Тепер кожна вітка шукається в усіх інших проєктах у
    порядку реєстру, і перша знахідка перемагає.

    Пишемо через projects.*_for(): вибір проєкту в людини свій, і перемикати
    його заради імпорту не можна. Повертає перенесені записи; вхідний список
    не мутує.
    """
    here = projects.current_id()
    others = [(p["id"], p["title"]) for p in projects.list_projects()
              if p["id"] != here]
    if not failed or not others:
        return []

    def probe(f):
        for pid, title in others:
            cl = projects.client_for(pid)
            try:
                return f, pid, title, cl, _resolve_in(cl, f["branch"])["name"]
            except Exception:
                continue
        return f, None, None, None, None

    with projects.Pool(max_workers=12) as ex:
        hits = [h for h in ex.map(probe, failed) if h[1]]
    if not hits:
        return []

    by_pid: dict[str, dict[str, dict]] = {}
    moved = []
    for f, pid, title, cl, real in hits:
        rec = {"task_id": f.get("task_id", ""), "task_name": f.get("task", ""),
               "task_url": f.get("task_url", "")}
        if f.get("domain"):
            rec["domain"] = f["domain"]
            domains.bind(real, f["domain"], f.get("task_id", ""), f.get("task", ""),
                         pid=pid)
        by_pid.setdefault(pid, {})[real] = rec
        moved.append({"branch": real, "src": f["branch"], "task": f.get("task", ""),
                      "task_url": f.get("task_url", ""),
                      "domain": f.get("domain") or "",
                      "project": pid, "project_title": title,
                      "url": cl.branch_url(real)})
    # У список ТІЄЇ САМОЇ людини в тому проєкті — однією операцією: у нього
    # пише і вона сама звідти, і цей перенос з імпорту в іншому.
    for pid, recs in by_pid.items():
        mutate_branch_list(lambda names, recs=recs: names + [
            n for n in dict.fromkeys(recs) if n not in names], pid=pid)
        mutate_json_state(projects.state_file_for(pid, "clickup_map.json"), dict,
                          lambda m, recs=recs: m.update(recs))
    return moved


@app.post("/api/clickup/import")
def clickup_import(req: ClickUpImportRequest):
    if MOCK():
        raise HTTPException(400, "MOCK MODE: імпорт з ClickUp працює тільки з живим GitLab")

    # перевіряємо існування віток у GitLab паралельно — це найдовша частина;
    # домен з Required Domains підв'язується до вітки ПО ІНДЕКСУ (1-й ↔ 1-ша)
    pairs = []
    for t in req.tasks:
        doms = t.get("domains") or []
        for i, br in enumerate(t.get("branches", [])):
            pairs.append((t, br, doms[i] if i < len(doms) else None))

    def probe(pair):
        t, br, dom = pair
        try:
            # фолбек регістру: AUTO_... з ClickUp ↔ auto_... у GitLab
            return t, resolve_branch(br)["name"], dom, None
        except Exception as e:
            return t, br, dom, str(e)

    with projects.Pool(max_workers=12) as ex:
        results = list(ex.map(probe, pairs))

    added, failed, bound = [], [], 0
    recs: dict[str, dict] = {}
    for t, br, dom, err in results:
        if err:
            failed.append({"branch": br, "task": t.get("name", ""),
                           "task_id": t.get("id", ""), "task_url": t.get("url", ""),
                           "domain": dom, "err": err})
            continue
        recs[br] = {"task_id": t.get("id", ""), "task_name": t.get("name", ""),
                    "task_url": t.get("url", "")}
        if dom:
            recs[br]["domain"] = dom
            domains.bind(br, dom, t.get("id", ""), t.get("name", ""))
            bound += 1
        added.append(br)

    # Список і мапу читаємо ПІСЛЯ походу в GitLab і правимо однією операцією.
    # Доти вони читались до перевірки віток (секунди), а писались після — і
    # усе, що людина за цей час прибрала чи додала, імпорт мовчки повертав.
    def put_names(names):
        names = [] if req.replace else names
        return names + [n for n in dict.fromkeys(added) if n not in names]

    def put_map(m):
        m = {} if req.replace else m
        m.update(recs)
        return m
    mutate_branch_list(put_names)
    mutate_json_state(projects.state_file("clickup_map.json"), dict, put_map)

    # 404 в активному репо ще не означає, що вітки немає: вона може лежати в
    # іншому проєкті (vue ↔ php). Що знайшлось там — заводимо туди, а не в
    # журнал проблем.
    moved = _adopt_elsewhere(failed)
    # звіряємо по ВХІДНІЙ назві: у node-репо вітка може лежати в іншому регістрі
    gone = {m["src"] for m in moved}
    failed = [f for f in failed if f["branch"] not in gone]
    add_problems([{"branch": f["branch"], "source": "import",
                   "reason": f["err"], "task": f.get("task", "")} for f in failed])
    # перенесена вітка більше не проблема — знімаємо і старий запис журналу
    if moved:
        stale = gone | {m["branch"] for m in moved}
        drop_problems(lambda x: x.get("source") == "import"
                      and x.get("branch") in stale)
    return {"added": added, "failed": failed, "replace": req.replace,
            "domains_bound": bound, "moved": moved}


# ---------------------------------------------------------------- domains
# активні домени віток (з Required Domains у ClickUp) + історія використання


@app.get("/api/domains")
def domains_full():
    """{"active": {вітка: {domain, task_id, task_name, ts}}, "history": [...]}"""
    return domains.full()


@app.get("/api/domains/history")
def domains_history(domain: str = "", branch: str = ""):
    """Історія: ?domain= — де використовувався домен;
    ?branch= — які домени підв'язувались до вітки; без параметрів — уся."""
    if domain:
        return domains.history_for(domain)
    if branch:
        return domains.branch_domains(branch)
    return domains.full()["history"]


@app.get("/api/problems")
def problems_list():
    return load_problems()


@app.delete("/api/problems")
def problems_clear():
    mutate_json_state(projects.state_file("problems.json"), list, lambda _: [])
    return {"cleared": True}


@app.delete("/api/problems/one")
def problems_remove_one(branch: str, source: str = ""):
    left = mutate_json_state(
        projects.state_file("problems.json"), list,
        lambda rows: [x for x in rows
                      if not (x.get("branch") == branch
                              and (not source or x.get("source") == source))])
    return {"total": len(left)}


# ---------------------------------------------------------------- знак бренду (лого/favicon)
class BrandmarkApplyRequest(BaseModel):
    branch: str
    variant: int
    targets: list[str] = ["logo", "favicon"]
    seed: int | None = None
    message: str = ""


def _brandmark_project(branch: str):
    """Контекст-менеджер проєкту, де вітка РЕАЛЬНО живе.

    Вкладка «Лого/Favicon» працює по вітках обох проєктів, а проєкт
    прив'язаний до СЕСІЇ людини (спільний admin — спільний вибір): коли
    хтось перемикав проєкт, vue-вітки читались у php-контексті, знімок
    виходив порожнім, і база кольору падала в DEFAULT — всі рядки панелі
    ставали однією сірою гамою (кейс 01.10 «постійно змінює дизайн»)."""
    import contextlib
    if runner.is_synced(branch):
        return contextlib.nullcontext()
    for pid in [p["id"] for p in projects.list_projects()]:
        if pid == projects.current_id():
            continue
        with projects.use(pid):
            if runner.is_synced(branch):
                return projects.use(pid)
    return contextlib.nullcontext()


def _brandmark_ctx(branch: str):
    """Знімок вітки + базовий колір з theme-color (через модуль favicon)."""
    import brand_mark
    if not runner.is_synced(branch):
        runner.sync_branch(client, branch)
    paths = runner.snapshot_files(branch)
    files = {}
    for p in paths:
        if p.lower().endswith((".html", ".htm", ".php", ".vue")):
            files[p] = runner.read_snapshot_file(branch, p).decode("utf-8", "replace")
    if not files:
        # порожній знімок = сіра DEFAULT-гама на всю панель; чесна помилка
        # краща за мовчазну підміну кольорів
        raise HTTPException(400, f"знімок вітки «{branch}» порожній — "
                                 f"спершу Sync")
    fav = next((c["module"] for c in runner.load_checks()
                if c["id"] == "favicon"), None)
    base = brand_mark.DEFAULT_BG
    if fav is not None:
        try:
            base = fav._brand_color(files)
        except Exception:
            pass
    return brand_mark, files, paths, base, fav

# ---------------------------------------------------------------- назва сайту
class SiteRenameRequest(BaseModel):
    branch: str
    new_name: str
    old_name: str = ""          # порожньо = поточна назва з title/вітки


_RENAME_EXT = (".html", ".htm", ".php", ".vue", ".ts", ".tsx", ".js",
               ".jsx", ".json", ".txt", ".xml")


def _sitename_ctx(branch: str):
    import site_name
    if not runner.is_synced(branch):
        runner.sync_branch(client, branch)
    paths = runner.snapshot_files(branch)
    files = {}
    for p in paths:
        if p.lower().endswith(_RENAME_EXT) and runner.is_text(p):
            files[p] = runner.read_snapshot_file(branch, p).decode(
                "utf-8", "replace")
    return site_name, files


@app.get("/api/sitename")
def sitename_current(branch: str):
    sn, files = _sitename_ctx(branch)
    return {"branch": branch, "name": sn.expected(branch, files)}


@app.post("/api/sitename/rename")
def sitename_rename(req: SiteRenameRequest):
    """Планова зміна назви сайту: title і всі капіталізовані згадки по
    вітці (site_name.rename: слаги/пошти/соцлінки цілі, повні входження
    нової назви не роздуваються). ОДИН коміт."""
    sn, files = _sitename_ctx(req.branch)
    new = (req.new_name or "").strip()
    if not new:
        raise HTTPException(400, "порожня нова назва")
    old = (req.old_name or "").strip() or sn.expected(req.branch, files)
    if not old:
        raise HTTPException(400, "не вдалось визначити поточну назву вітки")
    if sn.same(old, new) and old == new:
        return {"committed": False, "reason": "назва вже така", "old": old}
    changed = sn.rename_files(files, old, new)
    if not changed:
        raise HTTPException(400, f"«{old}» у вітці не знайдено — нема що міняти")
    actions = [{"action": "update", "file_path": p, "content": t}
               for p, t in sorted(changed.items())]
    msg = f"chore(rename): «{old}» → «{new}» (зміна назви сайту)"
    try:
        result = client.commit(req.branch, msg, actions)
    except Exception as e:
        raise HTTPException(400, f"коміт не пройшов: {e}")
    base_dir = runner.snapshot_dir(req.branch)
    for p, t in changed.items():
        fp = base_dir / p
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(t, encoding="utf-8", newline="")
    log_commit(req.branch, msg, result.get("id", ""), sorted(changed),
               action="rename")
    now = sn.expected(req.branch, {p: (changed.get(p) or files[p])
                                   for p in files})
    return {"committed": True, "commit": result.get("id", ""),
            "old": old, "new": new, "now": now,
            "files": sorted(changed)}



# ------------------------------------- пули юрномерів: CNPJ (br-pt), UID (ch-de)
class RegnoAddRequest(BaseModel):
    number: str
    note: str = ""
    company: str = ""
    city: str = ""
    sphere: str = ""
    addr: str = ""


def _regno_pool(kind: str):
    if kind == "cnpj":
        import cnpj_pool
        return cnpj_pool
    if kind == "uid":
        import uid_pool
        return uid_pool
    raise HTTPException(404, f"невідомий вид номера: {kind}")


def _regno_state(pool) -> dict:
    return {"rows": pool.load(), "assign": pool.assignments()}


@app.get("/api/regno/{kind}")
def regno_list(kind: str):
    return _regno_state(_regno_pool(kind))


@app.post("/api/regno/{kind}")
def regno_add(kind: str, req: RegnoAddRequest):
    pool = _regno_pool(kind)
    try:
        row = pool.add(req.number, req.note, company=req.company,
                       city=req.city, sphere=req.sphere, addr=req.addr)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"added": row, **_regno_state(pool)}


@app.delete("/api/regno/{kind}")
def regno_remove(kind: str, number: str):
    pool = _regno_pool(kind)
    if not pool.remove(number):
        raise HTTPException(404, "такого номера немає в пулі")
    return _regno_state(pool)


@app.get("/api/brandmark/variants")
def brandmark_variants(branch: str, count: int = 12, seed: int | None = None):
    with _brandmark_project(branch):
        return _brandmark_variants_impl(branch, count, seed)


def _brandmark_variants_impl(branch: str, count: int, seed: int | None):
    bm, files, _, base, _ = _brandmark_ctx(branch)
    if seed is None:
        # Детермінований дефолт від вітки: панель warnings пересканується
        # після кожного Apply, і random-дефолт перетасовував хвіст розгортки
        # у ВСІХ рядках одразу («замінив один знак — дизайн усіх змінився»,
        # кейс 01.10). Інші варіанти — кнопка ⟳: фронт шле випадковий seed.
        import zlib as _zl
        seed = _zl.crc32(branch.encode("utf-8")) % 1_000_000_000 or 1
    vs = bm.variants(files, branch, count=max(4, min(48, count)),
                     base_color=base, seed=seed)
    head = vs[0] if vs else {}
    return {"branch": branch, "base_color": base, "ptype": projects.ptype(),
            "seed": seed, "pool": len(bm.icon_db()),
            "name": head.get("name", ""), "letters": head.get("letters", ""),
            "icon": head.get("icon", "star"), "variants": vs}


@app.post("/api/brandmark/apply")
def brandmark_apply(req: BrandmarkApplyRequest):
    """ОДИН коміт: знак у logo.svg і/або favicon.svg + лінки сторінок на
    іконку (їх дотягує favicon.fix_branch по знімку з уже доданою іконкою).
    Працює у проєкті, де вітка реально живе (_brandmark_project) — і знімок,
    і client коміту беруться з того контексту."""
    with _brandmark_project(req.branch):
        return _brandmark_apply_impl(req)


def _brandmark_apply_impl(req: BrandmarkApplyRequest):
    bm, files, paths, base, fav = _brandmark_ctx(req.branch)
    vs = bm.variants(files, req.branch, count=max(24, req.variant + 1),
                     base_color=base, seed=req.seed)
    if not (0 <= req.variant < len(vs)):
        raise HTTPException(400, "невідомий варіант знаку")
    chosen = vs[req.variant]
    svg = chosen["svg"]
    fileset = set(paths)
    actions, written = [], []
    if "logo" in req.targets and projects.ptype() == "node":
        logo_path = "src/assets/images/logo.svg"
        actions.append({"action": "update" if logo_path in fileset else "create",
                        "file_path": logo_path, "content": svg})
        written.append(logo_path)
    if "favicon" in req.targets and fav is not None:
        import zlib as _zlib
        # версія вмісту знака: прев'ю-хост один на всі вітки, браузер липко
        # кешує favicon/logo попередньої вітки — нова адреса = перефетч
        ver = f"{_zlib.crc32(svg.encode('utf-8')) & 0xffffffff:08x}"
        is_node = projects.ptype() == "node"
        if is_node:
            # Vite/Nuxt віддають статику з public/: файл у КОРЕНІ репо в білд
            # не потрапляє взагалі (кейс groriboa-praveiv 30.09: знак ліг у
            # корінь, сайт і далі серв старий public/favicon.svg)
            fav_path = next((p for p in paths
                             if p.lower() == "public/favicon.svg"),
                            "public/favicon.svg")
        else:
            root = fav._root_favicon(paths)
            fav_path = (root if root and root.lower().endswith(".svg")
                        else fav.FAVICON_PATH)
        actions.append({"action": "update" if fav_path in fileset else "create",
                        "file_path": fav_path, "content": svg})
        written.append(fav_path)
        if is_node:
            # мертві favicon-и реповго кореня: не сервляться, лише плутають
            for p in paths:
                if (p.lower().startswith("favicon.") and "/" not in p
                        and p != fav_path):
                    actions.append({"action": "delete", "file_path": p})
                    written.append(p)
            # Лінк — З ВЕРСІЄЮ вмісту: прев'ю-хост один на всі вітки, і
            # браузер липко кешує /favicon.svg попередньої вітки (кейс
            # paruino-proge 30.09: у вкладці чужий знак при правильному
            # файлі). Нова адреса = примусовий перефетч.
            href = f"/favicon.svg?v={ver}"
            link_rx = re.compile(
                r'(<link\b[^>]*rel="[^"]*icon[^"]*"[^>]*href=")([^"]*favicon[^"]*)(")',
                re.I)
            for p in paths:
                if not p.lower().endswith(".html") or p.lower().startswith("public/"):
                    continue
                txt = files.get(p)
                if txt is None:
                    continue
                new_txt, n = link_rx.subn(lambda m: m.group(1) + href + m.group(3),
                                          txt)
                if n == 0 and p.lower() == "index.html" \
                        and not re.search(r'<link[^>]+rel="[^"]*icon', txt, re.I):
                    new_txt = re.sub(
                        r"(<head[^>]*>)",
                        rf'\1\n  <link rel="icon" href="{href}" '
                        r'type="image/svg+xml">',
                        txt, count=1, flags=re.I)
                if new_txt != txt:
                    actions.append({"action": "update", "file_path": p,
                                    "content": new_txt})
                    written.append(p)
        else:
            # php: спершу лінки на іконку, зверху — заміна фото-лого у
            # home-лінках (logo_photo.replace_actions працює по ВЖЕ
            # оновлених текстах, щоб правки одного файла не з'їли одна одну)
            files2 = dict(files)
            for a in fav.link_actions(dict(files2),
                                      sorted(fileset | {fav_path}), req.branch,
                                      force=True, version=ver):
                if a["type"] == "edit":
                    files2[a["path"]] = a["content"]
            if "logo" in req.targets:
                lp = next((c["module"] for c in runner.load_checks()
                           if c["id"] == "logo_photo"), None)
                if lp is not None:
                    for a in lp.replace_actions(dict(files2),
                                                sorted(fileset | {fav_path}),
                                                req.branch, version=ver):
                        if a["type"] == "edit":
                            files2[a["path"]] = a["content"]
            for p in sorted(files2):
                if files2[p] != files.get(p):
                    actions.append({"action": "update", "file_path": p,
                                    "content": files2[p]})
                    written.append(p)
    if not actions:
        raise HTTPException(400, "не обрано жодної цілі (logo/favicon)")
    msg = (req.message.strip()
           or f"feat(brand): знак {chosen['shape']}/{chosen['layout']} "
              f"({chosen['palette']}) для лого і favicon")
    try:
        result = client.commit(req.branch, msg, actions)
    except Exception as e:
        raise HTTPException(400, f"коміт не пройшов: {e}")
    base_dir = runner.snapshot_dir(req.branch)
    for a in actions:
        p = base_dir / a["file_path"]
        if a["action"] == "delete":
            p.unlink(missing_ok=True)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a["content"], encoding="utf-8", newline="")
    log_commit(req.branch, msg, result.get("id", ""), written, action="brandmark")
    return {"committed": True, "commit": result.get("id", ""),
            "files": written, "variant": chosen}


# ---------------------------------------------------------------- фото-пошук (заміни картинок)
@app.get("/api/photos/provider")
def photos_provider():
    return {"provider": photos.provider()}


@app.get("/api/photos/search")
def photos_search(q: str, orientation: str = "", page: int = 1):
    if not q.strip():
        raise HTTPException(400, "порожня тема пошуку")
    try:
        return photos.search(q.strip(), orientation, page)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"фото-провайдер не відповів: {e}")


@app.get("/api/photos/theme")
def photos_theme(branch: str):
    """Тема для пошуку фото. Пріоритет: заявка саппорта в коментарі ClickUp
    (`comment_themes.py`) → розбір самого вайта (`photo_theme.py`) → порожньо.
    Тема з коментаря точніша: це те, що людина справді просила поставити."""
    import comment_themes
    import photo_theme
    if not runner.is_synced(branch):
        raise HTTPException(404, "вітка не синхронізована — спершу Sync")
    site = photo_theme.for_branch(branch)
    rec = comment_themes.theme_for(branch)
    if rec and rec.get("theme"):
        return {**site, "query": rec["theme"], "source": "comment",
                "comment": rec}
    return site


@app.post("/api/photos/theme/refresh")
def photos_theme_refresh():
    """Перечитує збережені таски ClickUp і оновлює кеш «вітка → тема».
    Окремою кнопкою, а не на кожен скан: коментарі приходять пачкою і
    рідко."""
    import comment_themes
    tasks = (_cu_saved() or {}).get("tasks") or []
    found = comment_themes.refresh(tasks)
    return {"tasks": len(tasks), "branches": len(found),
            "themes": {b: r["theme"] for b, r in found.items()}}


# ---------------------------------------------------------------- фото-БД (ручний збір лінків без API)
# Флоу: «Відкрити magnific» → системний браузер із залогіненим профілем
# (+ Tampermonkey-скрипт з кнопками Copy) → накопичені лінки вставляються
# пачкою у вкладку «Фото БД» → «🎲 з БД по порожніх» у Медіа.
PHOTO_DB_FILE = projects.state_root() / "photo_db.json"


_photo_db_cache: dict = {}          # {"key": (mtime, size), "items": [...]}


def _ts_str(v) -> str:
    """Мітка часу фото у єдиному вигляді «YYYY-MM-DD HH:MM».

    У базі два формати: рядок (1837 записів, так пише photodb_add) і
    epoch-число (34 923 — від старішого імпорту). Через це `max()` по ts
    падав на порівнянні str з int, а в картці UI показувалось «1785310561».
    """
    if isinstance(v, (int, float)) and v > 0:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(v))
    return str(v or "")


def load_photo_db() -> list[dict]:
    """Кожне фото: {url, themes:[...], ts, used}. Міграції старих форматів:
    одиночне поле theme → themes і epoch-число у ts → «YYYY-MM-DD HH:MM».

    Тримаємо розпарсений список у пам'яті, ключ — (mtime, розмір) файлу:
    на 36 760 фото це 6.8 МБ і 115 мс парсингу на КОЖЕН запит, а списком
    тем цікавляться три різні місця UI (вкладка БД, селект у «Медіа»,
    datalist у «Локальних вайтах»). Запис міняє mtime, тож кеш
    самоскидається — окремої інвалідації не треба."""
    try:
        st = PHOTO_DB_FILE.stat()
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    if key is not None and _photo_db_cache.get("key") == key:
        return _photo_db_cache["items"]
    items = read_json_state(PHOTO_DB_FILE, [])
    for i in items:
        if "themes" not in i:
            th = (i.pop("theme", "") or "").strip()
            i["themes"] = [th] if th else []
        i["themes"] = sorted({t for t in i.get("themes", []) if t})
        i["ts"] = _ts_str(i.get("ts"))
    _photo_db_cache.update(key=key, items=items)
    return items


def save_photo_db(items: list[dict]):
    # скидаємо ДО запису: мутації вже в тих самих об'єктах, тож навіть якщо
    # запис упаде, у кеші не лишиться незбереженого стану
    _photo_db_cache.clear()
    write_json_state(PHOTO_DB_FILE, items)


NO_THEME = "без теми"      # ярлик фото без жодної теми; на бекенді це ""


def _theme_of(item: dict) -> list[str]:
    return item.get("themes") or [""]


@app.get("/api/photodb/themes")
def photodb_themes():
    """Тільки перелік тем з лічильниками — без жодного фото.

    Вкладка «Фото БД» раніше тягнула всю базу одним шматком (6.8 МБ JSON і
    36 760 карток у DOM) лише щоб показати список тем; на цьому UI і
    підвисав. Фото приходять окремо, коли тему обрали."""
    counts: dict[str, int] = {}
    total = 0
    for i in load_photo_db():
        total += 1
        for t in _theme_of(i):
            counts[t] = counts.get(t, 0) + 1
    themes = [{"name": n or NO_THEME, "count": c}
              for n, c in sorted(counts.items(), key=lambda kv: kv[0].lower())]
    return {"themes": themes, "total": total}


@app.get("/api/photodb")
def photodb_list(theme: str | None = None):
    """Фото ОДНІЄЇ теми. `theme` обов'язковий — раніше цей ендпоінт віддавав
    усю базу, і будь-який його виклик коштував 6.8 МБ трафіку; без параметра
    чесно відмовляємо, щоб такий виклик не завівся знову непомітно.
    `theme=""` — фото без жодної теми."""
    if theme is None:
        raise HTTPException(400, "потрібен параметр theme (список тем — /api/photodb/themes)")
    want = "" if theme in ("", NO_THEME) else theme
    photos = [i for i in load_photo_db() if want in _theme_of(i)]
    return {"theme": theme, "photos": photos, "count": len(photos)}


@app.get("/api/photodb/pick")
def photodb_pick(theme: str = "", n: int = 50):
    """N фото для «🎲 з БД по порожніх»: найменш використані першими, у межах
    однакового `used` — випадково. Раніше фронт для цього вантажив усю базу
    і сортував її у браузері.

    `theme` тут читається як у селекті «Медіа»: порожній рядок — БУДЬ-ЯКА
    тема (не «без теми», для цього є ярлик NO_THEME)."""
    import random
    pool = ([i for i in load_photo_db()] if not theme else
            [i for i in load_photo_db()
             if ("" if theme == NO_THEME else theme) in _theme_of(i)])
    random.shuffle(pool)
    pool.sort(key=lambda i: i.get("used", 0))
    return {"photos": pool[:max(1, min(500, n))], "pool": len(pool)}


def _top_hosts(hosts: dict, top: int = 12) -> list[dict]:
    """Джерела фото: помітні хости окремо, довгий хвіст одноразових —
    рядком «інші». Без цього таблиця з 30 хостів по 1 фото була б шумом."""
    rows = sorted(hosts.items(), key=lambda kv: -kv[1])
    out = [{"name": h, "photos": n} for h, n in rows[:top]]
    tail = sum(n for _h, n in rows[top:])
    if tail:
        out.append({"name": f"інші ({len(rows) - top})", "photos": tail})
    return out


@app.get("/api/photodb/stats")
def photodb_stats():
    """Агрегати для вкладки «Фото і теми» на /stats: усе рахується тут, щоб
    у браузер не їхали 36 тисяч записів заради кількох цифр."""
    items = load_photo_db()
    per: dict[str, dict] = {}
    hosts: dict[str, int] = {}
    by_day: dict[str, int] = {}
    used_total = unused = multi = 0
    for i in items:
        u = i.get("used", 0)
        used_total += u
        unused += not u
        themes = i.get("themes", [])
        multi += len(themes) > 1
        host = i["url"].split("/")[2] if "//" in i["url"] else "—"
        hosts[host] = hosts.get(host, 0) + 1
        day = (i.get("ts") or "")[:10]
        if day:
            by_day[day] = by_day.get(day, 0) + 1
        for t in _theme_of(i):
            s = per.setdefault(t or NO_THEME,
                               {"name": t or NO_THEME, "photos": 0, "used": 0,
                                "unused": 0, "last": ""})
            s["photos"] += 1
            s["used"] += u
            s["unused"] += not u
            s["last"] = max(s["last"], i.get("ts") or "")
    return {
        "total": len(items),
        "themes": len(per),
        "used_total": used_total,
        "unused": unused,
        "multi_theme": multi,
        "per_theme": sorted(per.values(), key=lambda s: -s["photos"]),
        "hosts": _top_hosts(hosts),
        "by_day": [{"day": d, "photos": n} for d, n in sorted(by_day.items())],
    }


class PhotoDbAddRequest(BaseModel):
    urls: list[str]
    theme: str = ""


@app.post("/api/photodb/add")
def photodb_add(req: PhotoDbAddRequest):
    """Додає фото у тему. Дедуп по URL: якщо фото вже є — просто дописуємо
    тему (багатотемність), повтори не заливаються двічі."""
    items = load_photo_db()
    by_url = {i["url"]: i for i in items}
    theme = req.theme.strip()
    added = updated = skipped = 0
    for u in req.urls:
        u = u.strip()
        if not u or not u.startswith(("http://", "https://")):
            continue
        cur = by_url.get(u)
        if cur:                                   # фото вже в БД
            if theme and theme not in cur["themes"]:
                cur["themes"] = sorted(set(cur["themes"]) | {theme})
                updated += 1
            else:
                skipped += 1
            continue
        rec = {"url": u, "themes": [theme] if theme else [],
               "ts": time.strftime("%Y-%m-%d %H:%M"), "used": 0}
        items.append(rec)
        by_url[u] = rec
        added += 1
    save_photo_db(items)
    return {"added": added, "updated": updated, "skipped": skipped, "total": len(items)}


class PhotoDbMergeRequest(BaseModel):
    sources: list[str]            # теми, які зливаємо ("" = псевдотема «без теми»)
    target: str                   # у цю тему (може бути нова)
    keep_sources: bool = False    # копія: лишити фото і в старих темах
    dry_run: bool = False         # тільки порахувати, нічого не писати


@app.post("/api/photodb/merge")
def photodb_merge(req: PhotoDbMergeRequest):
    """Злиття тем: фото зі sources переходять у target (з дедупом тем).

    keep_sources=True — фото лишаються і в старих темах (копія, а не перенос).
    dry_run=True — нічого не пише, лише повертає цифри для прев'ю.
    "" серед sources означає фото взагалі без тем."""
    target = req.target.strip()
    if not target:
        raise HTTPException(400, "порожня цільова тема")
    src = {s.strip() for s in req.sources} - {target}
    if not src:
        raise HTTPException(400, "нема тем-джерел (окрім самої цільової)")
    items = load_photo_db()
    before = sum(1 for i in items if target in i.get("themes", []))
    moved = already = 0
    for i in items:
        th = set(i.get("themes", []))
        # "" у src ловить фото без жодної теми
        if not (th & src or ("" in src and not th)):
            continue
        if target in th:
            already += 1                      # вже там, лише чистимо джерела
        else:
            moved += 1
        if not req.dry_run:
            keep = th if req.keep_sources else (th - src)
            i["themes"] = sorted(keep | {target})
    if not req.dry_run:
        save_photo_db(items)
    # при переносі теми-джерела спустошуються повністю (беремо всі їхні фото)
    cleared = [] if req.keep_sources else sorted(s for s in src if s)
    return {"merged_into": target, "photos_moved": moved,
            "already_in_target": already, "total_in_target": before + moved,
            "sources_cleared": cleared, "dry_run": req.dry_run}


class PhotoDbRenameRequest(BaseModel):
    old: str                  # "" = псевдотема «без теми»
    new: str


@app.post("/api/photodb/rename")
def photodb_rename(req: PhotoDbRenameRequest):
    """Перейменування теми. old="" — фото без тем отримують назву.
    Якщо new вже існує, це фактично злиття — фронт про це попереджає."""
    old, new = req.old.strip(), req.new.strip()
    if not new:
        raise HTTPException(400, "порожня нова назва")
    if old == new:
        return {"renamed": 0, "merged_into_existing": False, "new": new}
    items = load_photo_db()
    existed = any(new in i.get("themes", []) for i in items)
    renamed = 0
    for i in items:
        th = set(i.get("themes", []))
        if not ((old in th) if old else (not th)):
            continue
        i["themes"] = sorted((th - {old}) | {new})
        renamed += 1
    save_photo_db(items)
    return {"renamed": renamed, "new": new, "merged_into_existing": existed,
            "total_in_theme": sum(1 for i in items if new in i.get("themes", []))}


@app.delete("/api/photodb")
def photodb_remove(url: str):
    items = [i for i in load_photo_db() if i["url"] != url]
    save_photo_db(items)
    return {"total": len(items)}


@app.delete("/api/photodb/theme")
def photodb_theme_remove(name: str):
    """Прибирає тему: фото, що лишились без тем, видаляються; фото з іншими
    темами лишаються (багатотемність)."""
    out = []
    for i in load_photo_db():
        th = [t for t in i.get("themes", []) if t != name]
        if th:
            i["themes"] = th
            out.append(i)
        elif not i.get("themes"):        # фото взагалі без тем — лишаємо як є
            out.append(i)
    save_photo_db(out)
    return {"total": len(out)}


class PhotoDbUsedRequest(BaseModel):
    urls: list[str]


@app.post("/api/photodb/used")
def photodb_used(req: PhotoDbUsedRequest):
    items = load_photo_db()
    su = set(req.urls)
    for i in items:
        if i["url"] in su:
            i["used"] = i.get("used", 0) + 1
    save_photo_db(items)
    return {"ok": True}


class PhotoSearchOpenRequest(BaseModel):
    q: str
    orientation: str = ""


@app.post("/api/photos/open_browser")
def photos_open_browser(req: PhotoSearchOpenRequest):
    """Відкриває стоковий пошук magnific у СИСТЕМНОМУ браузері користувача
    (де він залогінений) з темою і фільтрами «фото + безкоштовні»."""
    if not req.q.strip():
        raise HTTPException(400, "порожня тема пошуку")
    import urllib.parse
    import webbrowser
    url = ("https://www.magnific.com/search?query="
           + urllib.parse.quote_plus(req.q.strip()) + "&type=photo&license=free")
    if req.orientation in ("landscape", "portrait", "square"):
        url += "&orientation=" + req.orientation
    webbrowser.open(url)
    return {"opened": url}


# ---------------------------------------------------------------- media
def _require_fresh_snapshot(branch: str):
    """Медіа-коміти шлють GitLab `update` ПО ШЛЯХАХ зі знімка. Якщо вітка в
    GitLab поїхала вперед повз лабу — кейс bavmejxqul-gepima-semgikja: людина
    перейменувала jpg-файли, знімок лишився старий, і кожен «Завантажити з URL
    і закомітити» падав у GitLab на «A file with this name doesn't exist», а
    людині діставався глухий «commit failed» і ті самі фото після пересканування
    (скан — не Sync, знімок він не оновлює). Кажемо чесно і ДО роботи: вітка
    поїхала — натисни Sync. Легасі-знімок без sha чи недоступний GitLab гейт
    не блокують: перевірити нема з чим, а помилку коміту скаже сам коміт."""
    local = runner.snapshot_meta(branch).get("commit")
    if not local:
        return
    try:
        head = client.branch(branch)["commit"]
    except Exception:
        return
    if head and head != local:
        raise HTTPException(409, f"вітка поїхала вперед: у GitLab нові коміти "
                                 f"(HEAD {str(head)[:8]}, знімок {str(local)[:8]}) — "
                                 f"натисни Sync і повтори, список файлів міг змінитись")


@app.get("/api/media")
def media_list(branch: str):
    if not runner.is_synced(branch):
        raise HTTPException(404, "branch not synced — press Sync first")
    return media.scan_branch(branch)


class UploadImageRequest(BaseModel):
    branch: str
    path: str
    content_b64: str
    message: str


def _media_move_plan(branch: str, pairs: list[tuple[str, str]]):
    """План «заміна = нове хеш-ім'я»: retarget-дії для всіх посилань на
    перейменовані файли (02.10 — замість ?v-версіонування: нова адреса
    пробиває і браузерний кеш, і CDN). pairs: [(old_rel, new_rel)].
    Повертає (actions, changed_texts)."""
    paths = runner.snapshot_files(branch)
    texts = {}
    for p in paths:
        if p.lower().endswith(media.REF_EXT):
            try:
                texts[p] = runner.read_snapshot_file(branch, p).decode("utf-8")
            except Exception:
                continue
    changed: dict = {}
    for old_rel, new_rel in pairs:
        src = {**texts, **changed}
        for p, t in media.retarget_refs(src, old_rel, new_rel, paths).items():
            changed[p] = t
    actions = [{"action": "update", "file_path": p, "content": t}
               for p, t in sorted(changed.items())]
    return actions, changed


@app.post("/api/media/upload")
def media_upload(req: UploadImageRequest):
    """Replace an image file (same path) with uploaded content -> one commit."""
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    _require_fresh_snapshot(req.branch)
    base = runner.snapshot_dir(req.branch)
    p = (base / req.path).resolve()
    if base.resolve() not in p.parents:
        raise HTTPException(400, "bad path")
    if not p.exists():
        raise HTTPException(404, "no such file in snapshot")
    try:
        data = base64.b64decode(req.content_b64, validate=True)
    except Exception:
        raise HTTPException(400, "bad base64 payload")
    # байти мусять збігатися з розширенням цілі: .webp у гіті + jpg з диска
    # раніше давали jpeg під іменем hero.webp
    try:
        data, note = media.ensure_format(data, req.path)
    except ValueError as e:
        raise HTTPException(400, f"{req.path}: {e}")
    content_b64 = base64.b64encode(data).decode() if note else req.content_b64
    new_rel = media.hashed_path(req.path, data)
    ref_acts, changed = _media_move_plan(req.branch, [(req.path, new_rel)])
    try:
        result = client.commit(req.branch, req.message, [
            {"action": "move", "previous_path": req.path,
             "file_path": new_rel, "content": content_b64,
             "encoding": "base64"},
        ] + ref_acts)
    except Exception as e:
        raise HTTPException(502, f"commit failed: {e}")
    np = (base / new_rel)
    np.parent.mkdir(parents=True, exist_ok=True)
    p.unlink(missing_ok=True)
    np.write_bytes(data)
    for fp, t in changed.items():
        (base / fp).write_text(t, encoding="utf-8", newline="")
    touched = [new_rel] + sorted(changed)
    log_commit(req.branch, req.message, result.get("id", ""), touched,
               action="image")
    return {"committed": True, "commit": result.get("id", ""),
            "path": new_rel, "old_path": req.path, "size": len(data),
            "refs": sorted(changed),
            "converted": [{"path": new_rel, "note": note}] if note else []}


class UploadManyRequest(BaseModel):
    branch: str
    message: str
    items: list[dict]        # [{path, content_b64}]


@app.post("/api/media/upload_many")
def media_upload_many(req: UploadManyRequest):
    """Mass image replace: all files in ONE commit."""
    if not req.message.strip():
        raise HTTPException(400, "commit message required")
    _require_fresh_snapshot(req.branch)
    if not req.items:
        raise HTTPException(400, "empty items")
    base = runner.snapshot_dir(req.branch)
    decoded, converted = [], []
    for it in req.items:
        p = (base / it["path"]).resolve()
        if base.resolve() not in p.parents:
            raise HTTPException(400, f"bad path: {it['path']}")
        if not p.exists():
            raise HTTPException(404, f"no such file in snapshot: {it['path']}")
        try:
            data = base64.b64decode(it["content_b64"], validate=True)
        except Exception:
            raise HTTPException(400, f"bad base64 for {it['path']}")
        try:
            data, note = media.ensure_format(data, it["path"])
        except ValueError as e:
            raise HTTPException(400, f"{it['path']}: {e}")
        b64 = base64.b64encode(data).decode() if note else it["content_b64"]
        new_rel = media.hashed_path(it["path"], data)
        if note:
            converted.append({"path": new_rel, "note": note})
        decoded.append((p, it["path"], new_rel, b64, data))
    ref_acts, changed = _media_move_plan(
        req.branch, [(old, new) for _, old, new, _, _ in decoded])
    try:
        result = client.commit(req.branch, req.message, [
            {"action": "move", "previous_path": old, "file_path": new,
             "content": b64, "encoding": "base64"}
            for _, old, new, b64, _ in decoded
        ] + ref_acts)
    except Exception as e:
        raise HTTPException(502, f"commit failed: {e}")
    for p, _, new, _, data in decoded:
        np = base / new
        np.parent.mkdir(parents=True, exist_ok=True)
        p.unlink(missing_ok=True)
        np.write_bytes(data)
    for fp, t in changed.items():
        (base / fp).write_text(t, encoding="utf-8", newline="")
    log_commit(req.branch, req.message, result.get("id", ""),
               [new for _, _, new, _, _ in decoded] + sorted(changed),
               action="image")
    return {"committed": True, "commit": result.get("id", ""),
            "paths": [new for _, _, new, _, _ in decoded],
            "renames": {old: new for _, old, new, _, _ in decoded},
            "refs": sorted(changed), "converted": converted}


class ReplaceFromUrlRequest(BaseModel):
    branch: str
    items: list[dict]        # [{path, url}]
    message: str = "Image"


@app.post("/api/media/replace_from_url")
def media_replace_from_url(req: ReplaceFromUrlRequest):
    """Замінює файли-картинки у гіті вмістом за URL: сервер САМ завантажує
    кожен URL і комітить байти під ТИМ САМИМ шляхом (ім'я/розширення як у гіті).
    Один атомарний коміт для всіх."""
    if not req.items:
        raise HTTPException(400, "порожній список")
    _require_fresh_snapshot(req.branch)
    import requests as _rq
    base = runner.snapshot_dir(req.branch)
    fetched, failed, converted = [], [], []
    for it in req.items:
        path, url = it.get("path", ""), (it.get("url") or "").strip()
        p = (base / path).resolve()
        if base.resolve() not in p.parents:
            raise HTTPException(400, f"bad path: {path}")
        if not p.exists():
            raise HTTPException(404, f"немає такого файлу у знімку: {path}")
        if not url.startswith(("http://", "https://")):
            failed.append({"path": path, "err": "не URL"})
            continue
        try:
            r = _rq.get(url, timeout=30, headers={"User-Agent": "qa_lab"})
            r.raise_for_status()
            data = r.content
            if not data or len(data) < 64:
                raise ValueError("порожня/замала відповідь")
            # формат — за сигнатурою і під розширення цілі: у вітці .webp,
            # а стоки віддають .jpg (Content-Type сервера тут не авторитет)
            data, note = media.ensure_format(data, path)
            new_rel = media.hashed_path(path, data)
            if note:
                converted.append({"path": new_rel, "note": note})
            fetched.append((p, path, new_rel, data))
        except Exception as e:
            failed.append({"path": path, "err": str(e)[:120]})
    if not fetched:
        raise HTTPException(400, f"жодного файлу не завантажено. Помилки: {failed}")
    ref_acts, changed = _media_move_plan(
        req.branch, [(old, new) for _, old, new, _ in fetched])
    try:
        result = client.commit(req.branch, req.message or "Image", [
            {"action": "move", "previous_path": old, "file_path": new,
             "content": base64.b64encode(data).decode(), "encoding": "base64"}
            for _, old, new, data in fetched] + ref_acts)
    except Exception as e:
        raise HTTPException(502, f"commit failed: {e}")
    for p, _, new, data in fetched:
        np = base / new
        np.parent.mkdir(parents=True, exist_ok=True)
        p.unlink(missing_ok=True)
        np.write_bytes(data)
    for fp, t in changed.items():
        (base / fp).write_text(t, encoding="utf-8", newline="")
    log_commit(req.branch, req.message or "Image", result.get("id", ""),
               [new for _, _, new, _ in fetched] + sorted(changed),
               action="image")
    return {"committed": True, "commit": result.get("id", ""),
            "paths": [new for _, _, new, _ in fetched],
            "renames": {old: new for _, old, new, _ in fetched},
            "refs": sorted(changed), "failed": failed,
            "converted": converted}


# ---------------------------------------------------------------- A: заміна по конкретних використаннях (зовнішні лінки)
class ReplaceByUsageRequest(BaseModel):
    branch: str
    targets: list[dict]        # [{path, line, old, new}]
    message: str = "Image"


def _usage_edits(texts: dict, targets: list) -> tuple:
    """(edited, applied, missed) — заміна лінка ТІЛЬКИ у вказаних місцях
    (файл+рядок). Один old може отримувати РІЗНІ new у різних місцях —
    саме це «розбивка по місцях» (скарга 13.10: здавалося, що всі місця
    отримують один url; вкладка діфів показувала ЗАГАЛЬНУ заміну, а не
    розбивку). Чиста функція — без снапшота і мережі, щоб контракт жив
    у тестах."""
    by_path: dict[str, list] = {}
    for t in targets:
        by_path.setdefault(t["path"], []).append(
            (int(t["line"]), t["old"], (t.get("new") or "").strip()))
    edited, applied, missed = {}, 0, []
    for path, edits in by_path.items():
        text = texts[path]
        lines = text.split("\n")
        # на кожному рядку заміняємо по одному входженню (зліва направо)
        for line, old, new in sorted(edits, key=lambda e: e[0]):
            i = line - 1
            if 0 <= i < len(lines) and old in lines[i]:
                lines[i] = lines[i].replace(old, new, 1)
                applied += 1
            elif old in text:                 # рядок зсунувся — fallback нижче
                pass
            else:
                missed.append(f"{path}:{line}")
        new_text = "\n".join(lines)
        # fallback для тих, що не знайшлись на своєму рядку
        for line, old, new in edits:
            if 0 <= line - 1 < len(lines) and new in lines[line - 1]:
                continue
            if old in new_text:
                new_text = new_text.replace(old, new, 1)
                applied += 1
        if new_text != text:
            edited[path] = new_text
    return edited, applied, missed


@app.post("/api/media/replace_by_usage")
def media_replace_by_usage(req: ReplaceByUsageRequest):
    """Заміна лінка ТІЛЬКИ у вказаних місцях (файл+рядок), не глобально.
    Дає різні фото у різних використаннях того самого лінка."""
    if not req.targets:
        raise HTTPException(400, "порожній список")
    _require_fresh_snapshot(req.branch)
    base = runner.snapshot_dir(req.branch)
    texts = {}
    for t in req.targets:
        p = (base / t["path"]).resolve()
        if base.resolve() not in p.parents:
            raise HTTPException(400, f"bad path: {t.get('path')}")
        if not p.exists():
            raise HTTPException(404, f"немає файлу: {t.get('path')}")
        if t["path"] not in texts:
            texts[t["path"]] = runner.read_snapshot_file(
                req.branch, t["path"]).decode("utf-8", "replace")
    edited, applied, missed = _usage_edits(texts, req.targets)
    if not edited:
        raise HTTPException(400, f"нічого не змінилось (не знайдено: {missed})")
    try:
        r = client.commit(req.branch, req.message or "Image", [
            {"action": "update", "file_path": p, "content": t} for p, t in edited.items()])
    except Exception as e:
        raise HTTPException(502, f"commit failed: {e}")
    for p, t in edited.items():
        (base / p).write_text(t, encoding="utf-8", newline="")
    log_commit(req.branch, req.message or "Image", r.get("id", ""),
               list(edited), action="image")
    return {"committed": True, "commit": r.get("id", ""),
            "files": list(edited), "applied": applied, "missed": missed}


# ---------------------------------------------------------------- Б: розмноження git-файлу на копії з новим фото
class SplitFileRequest(BaseModel):
    branch: str
    items: list[dict]          # [{file, path, line, url}] file=оригінальний git-файл
    message: str = "Image"


def _uniq_name(orig: str, taken: set) -> str:
    """images/hero.jpg → images/hero-2.jpg (унікальне у вітці)."""
    import posixpath
    d = posixpath.dirname(orig)
    base, ext = posixpath.splitext(posixpath.basename(orig))
    n = 2
    while True:
        cand = posixpath.join(d, f"{base}-{n}{ext}") if d else f"{base}-{n}{ext}"
        if cand not in taken:
            taken.add(cand)
            return cand
        n += 1


@app.post("/api/media/split_file")
def media_split_file(req: SplitFileRequest):
    """Для git-файлу, що використовується в кількох місцях: створює НОВИЙ файл
    (ім'я схоже на оригінал) з фото за url і переписує посилання у вказаному
    місці (файл+рядок) на новий файл. Один коміт."""
    if not req.items:
        raise HTTPException(400, "порожній список")
    _require_fresh_snapshot(req.branch)
    import os as _os

    import requests as _rq
    base = runner.snapshot_dir(req.branch)
    taken = set(runner.snapshot_files(req.branch))
    actions, disk, failed, made, converted = [], [], [], [], []
    edited_text: dict[str, str] = {}

    for it in req.items:
        orig, path, line = it.get("file", ""), it.get("path", ""), int(it.get("line", 0))
        url = (it.get("url") or "").strip()
        oldbase = _os.path.basename(orig)
        try:
            if not url.startswith(("http://", "https://")):
                raise ValueError("не URL")
            data = _rq.get(url, timeout=30, headers={"User-Agent": "qa_lab"}).content
            if len(data) < 64:
                raise ValueError("порожня/замала відповідь")
            newname = _uniq_name(orig, taken)
            # новий файл успадковує розширення оригіналу — байти під нього
            data, note = media.ensure_format(data, newname)
            if note:
                converted.append({"file": newname, "note": note})
            newbase = _os.path.basename(newname)
            # рядок з посиланням: замінюємо лише basename оригіналу на новий
            pp = (base / path).resolve()
            if base.resolve() not in pp.parents or not pp.exists():
                raise ValueError(f"немає файлу {path}")
            text = edited_text.get(path) or runner.read_snapshot_file(
                req.branch, path).decode("utf-8", "replace")
            lines = text.split("\n")
            i = line - 1
            if 0 <= i < len(lines) and oldbase in lines[i]:
                lines[i] = lines[i].replace(oldbase, newbase, 1)
            elif oldbase in text:
                text2 = text.replace(oldbase, newbase, 1)
                edited_text[path] = text2
                actions.append({"action": "create", "file_path": newname,
                                "content": base64.b64encode(data).decode(), "encoding": "base64"})
                disk.append((newname, data))
                made.append({"file": newname, "at": f"{path}:{line}"})
                continue
            else:
                raise ValueError(f"'{oldbase}' не знайдено у {path}:{line}")
            edited_text[path] = "\n".join(lines)
            actions.append({"action": "create", "file_path": newname,
                            "content": base64.b64encode(data).decode(), "encoding": "base64"})
            disk.append((newname, data))
            made.append({"file": newname, "at": f"{path}:{line}"})
        except Exception as e:
            failed.append({"at": f"{path}:{line}", "err": str(e)[:120]})

    for path, text in edited_text.items():
        actions.append({"action": "update", "file_path": path, "content": text})
    if not made:
        raise HTTPException(400, f"жодного файлу не створено. Помилки: {failed}")
    try:
        r = client.commit(req.branch, req.message or "Image", actions)
    except Exception as e:
        raise HTTPException(502, f"commit failed: {e}")
    for name, data in disk:
        (base / name).parent.mkdir(parents=True, exist_ok=True)
        (base / name).write_bytes(data)
    for path, text in edited_text.items():
        (base / path).write_text(text, encoding="utf-8", newline="")
    log_commit(req.branch, req.message or "Image", r.get("id", ""),
               [m["file"] for m in made], action="image")
    return {"committed": True, "commit": r.get("id", ""), "made": made,
            "failed": failed, "converted": converted}


# ---------------------------------------------------------------- deploy (local PHP server)
@app.get("/api/deploys")
def deploys():
    return deployer.list_deploys()


@app.delete("/api/deploys")
def deploys_stop_all(request: Request):
    # Гасить деплої ВСІХ людей і всіх проєктів — разом з їхніми прев'ю і
    # скрінами, що саме знімаються. Тому лише адміну (задача 21.09.2026);
    # свій деплой людина гасить кнопкою в його рядку.
    require_admin(request)
    deployer.stop_all()
    return {"stopped": True}


class DeployMultiRequest(BaseModel):
    branches: list[str]


@app.post("/api/deploy_multi")
def deploy_multi(req: DeployMultiRequest):
    out = []
    for br in req.branches:
        try:
            out.append(deployer.deploy(br))
        except Exception as e:
            out.append({"branch": br, "error": str(e)})
    return out


@app.get("/deploys", response_class=HTMLResponse)
def deploy_index():
    """Індексна сторінка з запущеними деплоями.

    `url` деплою — це лупбек ВСЕРЕДИНІ контейнера. Скріни, візуальні прогони
    і lighthouse ходять на нього з сервера і тому працюють; браузер людини
    туди не достукається — контейнер публікує лише порт лаби. Тож коли
    заведено прев'ю-хост, рядок стає КНОПКОЮ, що відкриває вітку через нього,
    а сирий лінк лишається тільки для запуску на машині самої людини.
    """
    rows = deployer.list_deploys()
    esc = html.escape
    if preview.enabled():
        items = "".join(
            f'<li><button data-b="{esc(d["branch"])}">{esc(d["branch"])}</button>'
            f' <span class="p">:{d["port"]}</span></li>' for d in rows)
    else:
        items = "".join(
            f'<li><a href="{esc(d["url"])}" target="_blank">{esc(d["branch"])}</a>'
            f' <span class="p">:{d["port"]}</span></li>' for d in rows)
    items = items or "<li class='p'>нічого не запущено</li>"
    return f"""<!DOCTYPE html><html lang="uk"><head><meta charset="UTF-8">
<title>qa_lab deploys</title>
<style>body{{background:#14171c;color:#d8dce3;font:15px/1.9 system-ui;padding:40px}}
h1{{font-size:17px;letter-spacing:.15em;text-transform:uppercase}}h1 b{{color:#c9974a}}
a,button{{color:#7dbf7d;text-decoration:none;font-family:Consolas,monospace;font-size:15px}}
button{{background:none;border:0;padding:0;cursor:pointer}}
a:hover,button:hover{{text-decoration:underline}}
.p{{color:#8a93a3;font-size:12px}}li{{list-style:none;padding:3px 0}}</style></head>
<body><h1><span style="text-transform:none">qa<b>_lab</b></span> — запущені деплої ({len(rows)})</h1>
<ul>{items}</ul><p class="p">сторінка оновлюється кожні 10 с</p>
<script>
// Оновлення сторінки — таймером, а не <meta refresh>: воно вміє чекати.
// Перезавантаження посеред відкриття прев'ю обірвало б POST, і людина
// отримала б порожню вкладку замість вайта.
let timer=setTimeout(()=>location.reload(),10000);
document.querySelectorAll('button[data-b]').forEach(b=>b.onclick=async()=>{{
  clearTimeout(timer);
  // Вкладку відкриваємо СИНХРОННО, ще до await: після нього браузер уже не
  // вважає window.open() дією користувача і глушить його блокувальником.
  const w=window.open('','_blank');
  if(w)w.document.write('<!doctype html><meta charset="utf-8"><body '
    +'style="font:14px system-ui;background:#14171c;color:#8a93a3;padding:32px">'
    +"готуємо прев'ю…");
  try{{
    const r=await fetch('/api/preview/'+encodeURIComponent(b.dataset.b),{{method:'POST'}});
    const s=await r.json();
    if(!r.ok)throw new Error(s.detail||('HTTP '+r.status));
    if(w)w.location=s.url; else alert('дозволь спливаючі вікна: '+s.url);
  }}catch(e){{
    if(w)w.close();
    alert(b.dataset.b+': '+e.message);
  }}finally{{timer=setTimeout(()=>location.reload(),10000)}}
}});
</script></body></html>"""


@app.get("/api/deploy/status")
def deploy_status(branch: str):
    return deployer.build_status(branch)


@app.get("/api/deploy/log")
def deploy_log(branch: str, limit: int = 200):
    """Хвіст логу `php -S` вітки.

    Навіщо окремо: у контейнері `display_errors = Off`, тож фатальна помилка
    вайта віддає ПОРОЖНЮ сторінку, а текст іде в stderr процесу. Без цього
    ендпоінта «біла сторінка» не має пояснення ніде — ні в браузері, ні в
    логах лаби (кейс 28.08).
    """
    try:
        return {"branch": branch, "log": deployer.read_log(branch, limit)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/deploy/{branch:path}")
def deploy_start(branch: str):
    try:
        return deployer.deploy(branch)        # nuxt-білд іде у фоні (status=building)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"deploy failed: {e}")


@app.delete("/api/deploy/{branch:path}")
def deploy_stop(branch: str):
    return {"stopped": deployer.stop(branch)}


# ---------------------------------------------------------------- прев'ю вітки
# Керування сесією живе на ХОСТІ ЛАБИ (тут працює звичайна авторизація), а сам
# вайт віддається з прев'ю-хоста. Розводить їх `_preview_host` вище.
# Сесія прев'ю — у кожної людини своя (з 21.09.2026), тож і стан, і
# «продовжити», і «закрити» питають саме її, а не «ту одну на всіх».
def _preview_owner(request) -> str:
    return auth.uid_of(current_user(request)) or ""


@app.get("/api/preview")
def preview_state(request: Request):
    return {"enabled": preview.enabled(), "host": preview.host(),
            "ttl": preview.TTL_S,
            "session": preview.public(uid=_preview_owner(request))}


@app.patch("/api/preview")
def preview_extend(request: Request):
    s = preview.extend(_preview_owner(request))
    if not s:
        raise HTTPException(404, "активної сесії немає")
    return s


@app.delete("/api/preview")
def preview_close(request: Request):
    return {"closed": preview.close(_preview_owner(request))}


@app.post("/api/preview/{branch:path}")
def preview_open(branch: str, request: Request):
    """Підняти вітку і видати одноразове посилання на прев'ю-хост."""
    if not preview.enabled():
        raise HTTPException(400, "прев'ю вимкнене: не заданий PREVIEW_HOST")
    if not runner.is_synced(branch):
        raise HTTPException(400, "вітка не синхронізована — спершу Sync")
    owner = _preview_owner(request)
    # Слоти питаємо ДО деплою: при зайнятих лаба інакше піднімала б вітку (на
    # node — з білдом) лише для того, щоб відмовити. 409 — щоб причину було
    # видно: 5xx у проді Cloudflare підміняє власною сторінкою.
    try:
        preview.check_capacity(owner)
    except preview.PreviewBusy as e:
        raise HTTPException(409, str(e))
    # Уже запущений деплой ПЕРЕВИКОРИСТОВУЄМО. Інакше кнопка «▶ Deploy», яка
    # тепер відкриває вітку через прев'ю, піднімала б її двічі поспіль, а на
    # node — ще й другий білд, і той чекав би у HTTP-запиті (за Cloudflare це
    # 524 після ~100 с). Свіжість тримає вотчер деплою, не повторний підйом.
    port = deployer.running_port(branch)
    if port is None:
        try:
            port = deployer.deploy(branch, wait=True)["port"]   # node-білд чекаємо: URL потрібен зараз
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"деплой не піднявся: {e}")
    # посилання видаємо лише коли php -S РЕАЛЬНО відповідає — інакше людина
    # відкриє вкладку швидше, ніж процес займе сокет, і побачить 502
    if not preview.wait_ready(port):
        raise HTTPException(504, "деплой піднявся, але не почав відповідати")
    try:
        return preview.open_session(branch, port, owner)
    except preview.PreviewBusy as e:        # слот зайняли, поки піднімався деплой
        raise HTTPException(409, str(e))


@app.on_event("shutdown")
def _shutdown():
    deployer.stop_all()
    runner.drop_pool()          # процеси-воркери прогонів (CHECK_WORKERS)

# ---------------------------------------------------------------- статистика
def _stats_entries() -> list[dict]:
    """Історія фікс-комітів УСІХ проєктів (php + node) з прив'язкою вітка→таска
    з clickup_map.

    Джерело — `stats_ledger`, а не журнал: журнал обрізається до JOURNAL_CAP,
    і при сотнях комітів на день старі дні зникають із нього фізично, через що
    графік і плашки «цей тиждень/місяць» показували вікно, а не історію.
    """
    entries = []
    for p in projects.all_state_dirs():
        root = p["root"]
        stats_ledger.ensure_seeded(root)      # разова міграція наявного журналу
        cu = {}
        cf = root / "clickup_map.json"
        if cf.exists():
            try:
                cu = json.loads(cf.read_text(encoding="utf-8"))
            except Exception:
                pass
        for e in stats_ledger.entries(root):
            t = cu.get(e["branch"]) or {}
            entries.append({
                "ts": e["ts"],
                "branch": e["branch"],
                "action": e["action"] or "edit",
                "files": e["files"],
                "project": p["id"],
                "task_id": t.get("task_id", ""),
                "task_name": t.get("task_name", ""),
            })
    entries.sort(key=lambda e: e["ts"])
    return entries


@app.get("/api/stats")
def stats():
    """Сира стрічка для сторінки /stats."""
    return {"entries": _stats_entries(), "minutes_per_fix": 1,
            "journal_cap": JOURNAL_CAP}


# ---------------------------------------------------------------- аналітика
def _quality_entries() -> list[dict]:
    """Історія прогонів перевірок усіх проєктів."""
    out = []
    for p in projects.all_state_dirs():
        root = p["root"]
        checks_ledger.ensure_seeded(root)     # разова міграція checks_state
        for e in checks_ledger.entries(root):
            out.append({**e, "project": p["id"]})
    out.sort(key=lambda e: e["ts"])
    return out


@app.get("/api/analytics/quality")
def analytics_quality():
    """Тренд якості по чеках: за кожен день — на скількох вітках чек ганяли
    і на скількох знайшов error. Частка (hit rate) важливіша за абсолют:
    прогони нерівні, сьогодні 30 віток, завтра 2000."""
    by_day: dict[str, dict] = {}
    per_check: dict[str, dict] = {}
    for e in _quality_entries():
        day = e["ts"][:10]
        for cid in e["ran"]:
            d = by_day.setdefault(day, {}).setdefault(cid, {"ran": 0, "hit": 0, "err": 0})
            d["ran"] += 1
            n = e["err"].get(cid, 0)
            if n:
                d["hit"] += 1
                d["err"] += n
            t = per_check.setdefault(cid, {"ran": 0, "hit": 0, "err": 0, "branches": set()})
            t["ran"] += 1
            if n:
                t["hit"] += 1
                t["err"] += n
                t["branches"].add(e["branch"])
    checks = [{"id": k, "ran": v["ran"], "hit": v["hit"], "err": v["err"],
               "branches": len(v["branches"]),
               "rate": round(100 * v["hit"] / v["ran"], 1) if v["ran"] else 0}
              for k, v in per_check.items()]
    checks.sort(key=lambda c: -c["err"])
    return {"checks": checks,
            "days": [{"day": d, "checks": v} for d, v in sorted(by_day.items())]}


@app.get("/api/analytics/repeat_fixes")
def analytics_repeat_fixes(limit: int = 40):
    """Вітки, які лагодили не один раз. Сам по собі повтор — не біда
    (різні дефекти), тому поруч рахуємо, чи це той САМИЙ чек знову: беремо
    з реєстру перевірок, які чеки давали error до і після кожного фікса."""
    fixes: dict[str, list] = {}
    for e in _stats_entries():
        if e["action"] in ("revert",):
            continue
        fixes.setdefault(e["branch"], []).append(e)
    runs: dict[str, list] = {}
    for e in _quality_entries():
        runs.setdefault(e["branch"], []).append(e)

    rows = []
    multi_run = 0
    for br, fx in fixes.items():
        if len(fx) < 2:
            continue
        rs = sorted(runs.get(br) or [], key=lambda r: r["ts"])
        if len(rs) > 1:
            multi_run += 1
        fx.sort(key=lambda f: f["ts"])
        # Чек ПОВЕРНУВСЯ, якщо був error у прогоні r1, потім між r1 і r2
        # лежить фікс-коміт, і в r2 той самий чек знову дає error. Саме
        # «між», а не «колись пізніше»: інакше будь-який давній фікс
        # зараховував би кожне повторне спрацювання.
        returned = set()
        for a, b in zip(rs, rs[1:]):
            if not any(a["ts"] < f["ts"] <= b["ts"] for f in fx):
                continue
            returned |= set(a["err"]) & set(b["err"])
        rows.append({"branch": br, "fixes": len(fx),
                     "files": sum(f["files"] for f in fx),
                     "first": fx[0]["ts"], "last": fx[-1]["ts"],
                     "actions": sorted({f["action"] for f in fx}),
                     "task": fx[-1].get("task_name", ""),
                     "runs": len(rs),
                     "returned": sorted(returned)})
    rows.sort(key=lambda r: (-len(r["returned"]), -r["fixes"], -r["files"]))
    return {"total_branches_with_repeats": len(rows),
            "rows": rows[:max(1, limit)],
            # скільки віток узагалі мають ≥2 прогони — без цього колонка
            # «повернулось» порожня не тому, що все добре, а тому що
            # порівнювати ще нема з чим
            "branches_with_history": multi_run,
            "returned_total": sum(1 for r in rows if r["returned"])}


@app.get("/api/analytics/domains")
def analytics_domains():
    """Burn rate доменів: скільки віток міняли домен, як швидко, які зони."""
    import collections as _c
    import datetime as _dt
    hist, active = [], {}
    for p in projects.all_state_dirs():
        f = p["root"] / "domains.json"
        if not f.exists():
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        hist += [h for h in (d.get("history") or []) if isinstance(h, dict)]
        active.update(d.get("active") or {})

    per_branch = _c.Counter(h.get("branch", "") for h in hist)
    changed = {b: n for b, n in per_branch.items() if b and n > 1}
    zones = _c.Counter((h.get("domain") or "").rsplit(".", 1)[-1] for h in hist)
    # скільки живе домен, якщо його вже замінили: від first_ts запису до
    # first_ts наступного домену тієї ж вітки
    lifespans = []
    by_branch: dict[str, list] = {}
    for h in hist:
        by_branch.setdefault(h.get("branch", ""), []).append(h)
    for b, hs in by_branch.items():
        hs.sort(key=lambda x: x.get("first_ts") or "")
        for a, nxt in zip(hs, hs[1:]):
            try:
                d0 = _dt.datetime.fromisoformat((a.get("first_ts") or "")[:19])
                d1 = _dt.datetime.fromisoformat((nxt.get("first_ts") or "")[:19])
            except ValueError:
                continue
            days = (d1 - d0).total_seconds() / 86400
            if days >= 0:
                lifespans.append(round(days, 2))
    lifespans.sort()
    reused = {d: n for d, n in _c.Counter(h.get("domain") for h in hist).items() if n > 1}
    return {
        "history": len(hist), "branches": len(per_branch), "active": len(active),
        "changed_branches": len(changed),
        "max_changes": max(per_branch.values()) if per_branch else 0,
        "change_hist": dict(sorted(_c.Counter(per_branch.values()).items())),
        "zones": [{"zone": z, "n": n} for z, n in zones.most_common(15)],
        "median_lifespan_days": lifespans[len(lifespans) // 2] if lifespans else None,
        "lifespans": len(lifespans),
        "reused_domains": [{"domain": d, "n": n}
                           for d, n in sorted(reused.items(), key=lambda x: -x[1])[:10]],
        "top_changed": [{"branch": b, "n": n}
                        for b, n in sorted(changed.items(), key=lambda x: -x[1])[:15]],
    }


STATS_CU_CACHE = projects.state_root() / "stats_clickup_cache.json"
STATS_CU_TTL = 15 * 60          # прямі фетчі по id повільні — кешуємо на диск


@app.get("/api/stats/clickup")
def stats_clickup(refresh: int = 0):
    """Статуси ClickUp-тасок, чиї вітки отримали фікс-коміти лаби: скільки
    з них уже закрито. ?refresh=1 — примусово перечитати з ClickUp."""
    per_task: dict[str, dict] = {}
    for e in _stats_entries():
        if not e["task_id"] or e["action"] == "revert":
            continue
        t = per_task.setdefault(e["task_id"], {
            "id": e["task_id"], "name": e["task_name"], "project": e["project"],
            "branches": set(), "commits": 0, "fixes": 0, "last_fix": ""})
        t["branches"].add(e["branch"])
        t["commits"] += 1
        t["fixes"] += e["files"]
        t["last_fix"] = max(t["last_fix"], e["ts"])
    if not per_task:
        return {"generated": "", "total": 0, "closed": 0, "tasks": []}

    cache = {}
    if STATS_CU_CACHE.exists():
        try:
            cache = json.loads(STATS_CU_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    fresh = (not refresh and cache.get("ids") == sorted(per_task)
             and time.time() - cache.get("at", 0) < STATS_CU_TTL)
    if not fresh:
        got = clickup_client.fetch_by_ids([{"id": tid} for tid in sorted(per_task)],
                                          with_comments=False)
        cache = {"at": time.time(), "ids": sorted(per_task), "statuses": {
            p["id"]: {"status": p.get("status", "?"),
                      "status_type": p.get("status_type", ""),
                      "date_closed": p.get("date_closed"),
                      "url": p.get("url", ""),
                      "failed": bool(p.get("enrich_failed"))}
            for p in got}}
        STATS_CU_CACHE.write_text(json.dumps(cache, ensure_ascii=False),
                                  encoding="utf-8")

    tasks = []
    for tid, t in per_task.items():
        s = cache["statuses"].get(tid) or {}
        closed = (s.get("status_type") in ("closed", "done")
                  or any(k in (s.get("status") or "")
                         for k in ("closed", "complete", "done")))
        dc = s.get("date_closed")
        tasks.append({
            "id": tid, "name": t["name"], "project": t["project"],
            "url": s.get("url", ""),
            "branches": len(t["branches"]), "commits": t["commits"],
            "fixes": t["fixes"], "last_fix": t["last_fix"],
            "status": s.get("status", "?"), "closed": closed,
            "date_closed": (time.strftime("%Y-%m-%d",
                                          time.localtime(int(dc) / 1000))
                            if dc else None),
            "failed": s.get("failed", False),
        })
    tasks.sort(key=lambda x: (not x["closed"], x["name"]))
    return {"generated": time.strftime("%Y-%m-%d %H:%M:%S",
                                       time.localtime(cache.get("at", time.time()))),
            "cached": fresh, "total": len(tasks),
            "closed": sum(1 for x in tasks if x["closed"]),
            "tasks": tasks}


def _page(name: str) -> FileResponse:
    """HTML-сторінка UI з обов'язковою ревалідацією.

    Без `Cache-Control` браузер кешує 200 евристично (за `Last-Modified`) і
    після правки файлу показує СТАРУ сторінку, поки не натиснеш Ctrl+F5 —
    саме так вкладка «Фото і теми» на /stats не з'являлась. `no-cache`
    змушує перепитувати сервер щоразу. Умовних 304 `FileResponse` не вміє
    (це вміє лише `StaticFiles`), тож сторінка щоразу приїжджає цілком —
    на локальному сервері це десятки кілобайт і не варте окремої машинерії.
    """
    return FileResponse(Path("static") / name,
                        headers={"Cache-Control": "no-cache"})


# --------------------------------------------------------------------- i18n
# Два файли, обидва синхронні в <head>: словник, а потім рушій. Асинхронно
# вантажити не можна — інакше сторінка встигає намалюватись українською і
# людина бачить блимання перед перекладом.
def _js(name: str, request: Request) -> Response:
    """Статичний js з РОБОЧОЮ ревалідацією.

    `FileResponse` кладе ETag у відповідь, але `If-None-Match` не читає — це
    вміє лише `StaticFiles`. Заміряно 02.09: словник (201 КБ) приїжджав
    ЦІЛКОМ на кожне завантаження будь-якої сторінки, і синхронно в `<head>`,
    тобто затримував першу відмальовку. Тому 304 обробляємо тут.

    Мітка — з mtime і розміру файлу: деплой кладе новий шар, mtime міняється,
    і кеш скидається сам, без версій у шляху.
    """
    path = Path("static") / name
    st = path.stat()
    tag = '"%d-%d"' % (int(st.st_mtime), st.st_size)
    head = {"Cache-Control": "no-cache", "ETag": tag}
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=head)
    return Response(path.read_bytes(), media_type="application/javascript",
                    headers=head)


@app.get("/i18n.js")
def i18n_engine(request: Request):
    return _js("i18n.js", request)


@app.get("/i18n-dict.js")
def i18n_dictionary(request: Request):
    return _js("i18n-dict.js", request)


@app.get("/stats")
def stats_page():
    return _page("stats.html")


@app.get("/analytics")
def analytics_page():
    return _page("analytics.html")


# ---------------------------------------------------------------- UI
@app.get("/")
def index():
    return _page("index.html")
