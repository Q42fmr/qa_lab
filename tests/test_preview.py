"""Прев'ю-піддомен: сесія, межі хоста і стіна перед API лаби.

Навіщо. `php -S` слухає лупбек ВСЕРЕДИНІ контейнера, а лаба показувала цей
самий `http://127.0.0.1:<порт>/` користувачу в браузер. Прод не публікує
жодного порту, тож лінк вів на власну машину користувача. Рішення — другий
хост на тому самому контейнері: лаба розводить запити за `Host`, і на
прев'ю-хості живе ТІЛЬКИ проксі до php -S поточної сесії.

Уся безпека тримається на трьох речах, і кожна тут закріплена:

  1. розвилка виконується ПЕРШОЮ і не має продовження — на прев'ю-хості
     маршрутів лаби не існує взагалі, а не «існують, але заборонені»;
  2. проксі не приймає ціль ззовні — порт лише зі слоту на сервері;
  3. токен передачі одноразовий, кука host-only і протухає на сервері.
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

import preview                                                    # noqa: E402

APP_SRC = (ROOT / "app.py").read_text(encoding="utf-8")
UI_SRC = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
ENV_DEV = (ROOT / ".env.example").read_text(encoding="utf-8")
ENV_PROD = (ROOT / ".env.prod.example").read_text(encoding="utf-8")
CI = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

HOST = "wp-preview.test"


class _env:
    def __init__(self, **vals):
        self.vals = vals

    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in self.vals}
        for k, v in self.vals.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        preview.close_all()
        return self

    def __exit__(self, *exc):
        preview.close_all()
        for k, v in self.old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def _on(**extra):
    return _env(PREVIEW_HOST=HOST, **extra)


# ------------------------------------------------- вимикач

def test_empty_host_disables_everything():
    """Порожній PREVIEW_HOST — єдиний вимикач: лаба поводиться як раніше."""
    with _env(PREVIEW_HOST=""):
        assert preview.enabled() is False
        assert preview.is_preview_host(HOST) is False
        assert preview.is_preview_host("") is False


def test_host_match_ignores_port_and_case():
    with _on():
        assert preview.is_preview_host(HOST)
        assert preview.is_preview_host(HOST + ":8030")
        assert preview.is_preview_host(HOST.upper())
        assert not preview.is_preview_host("lab.example.com")
        # префікс/суфікс не рахуються — інакше сусідній хост «майже збігся б»
        assert not preview.is_preview_host("evil-" + HOST)
        assert not preview.is_preview_host(HOST + ".evil.tld")


# ------------------------------------------------- сесія

def test_open_session_returns_link_without_leaking_secrets():
    with _on():
        s = preview.open_session("br-1", 9100, uid="u1")
        assert s["branch"] == "br-1"
        assert "/__open?k=" in s["url"]
        assert "sid" not in s and "token" not in s


def test_public_never_carries_token_or_sid():
    """Стан сесії віддається в UI, тож секретів у ньому бути не може."""
    with _on():
        preview.open_session("br-1", 9100)
        assert set(preview.public()) == {"branch", "left"}


def test_token_is_single_use():
    with _on():
        token = preview.open_session("br-1", 9100)["url"].split("k=")[1]
        assert preview.redeem(token)          # перший раз — сид
        assert preview.redeem(token) is None  # другий — вже ні


def test_wrong_token_is_refused():
    with _on():
        preview.open_session("br-1", 9100)
        assert preview.redeem("не-той-токен") is None
        assert preview.redeem("") is None


def test_token_expires_before_the_session_does():
    """Токен світиться в URL — у логах Traefik і в історії браузера. Тому він
    живе рівно на перехід, а не всі десять хвилин."""
    assert preview.HANDOFF_S < preview.TTL_S
    with _on():
        token = preview.open_session("br-1", 9100)["url"].split("k=")[1]
        preview._slots[""]["token_until"] = 0        # ніби минула хвилина
        assert preview.redeem(token) is None
        assert preview.public() is not None     # сама сесія при цьому жива


def test_cookie_opens_only_its_own_session():
    with _on():
        token = preview.open_session("br-1", 9100)["url"].split("k=")[1]
        sid = preview.redeem(token)
        assert preview.session_for(sid)["port"] == 9100
        assert preview.session_for("чужий-сид") is None
        assert preview.session_for("") is None


def test_expired_session_is_told_apart_from_absent_one():
    """410 «прев'ю завершилось» проти 404 «не знайдено» — різні відповіді."""
    with _on():
        token = preview.open_session("br-1", 9100)["url"].split("k=")[1]
        sid = preview.redeem(token)
        preview._slots[""]["until"] = 0
        assert preview.session_for(sid) is None
        assert preview.has_expired_cookie(sid) is True
        assert preview.has_expired_cookie("чужий-сид") is False


def test_expired_session_disappears_and_stops_the_deploy():
    stopped = []
    with _on():
        preview.wire(on_close=stopped.append)
        try:
            preview.open_session("br-1", 9100)
            preview._slots[""]["until"] = 0
            assert preview.current() is None
            assert stopped == ["br-1"]
        finally:
            preview.wire(on_close=None)


def test_next_preview_evicts_the_previous_one():
    """Сесія одна на ЛЮДИНУ: наступне прев'ю тієї ж людини ставить новий
    вайт, її старий токен мертвий. Чужих сесій це не стосується — див.
    розділ «кілька людей» нижче."""
    stopped = []
    with _on():
        preview.wire(on_close=stopped.append)
        try:
            old = preview.open_session("br-1", 9100)["url"].split("k=")[1]
            preview.open_session("br-2", 9101)
            assert preview.redeem(old) is None
            assert preview.public()["branch"] == "br-2"
            assert stopped == ["br-1"]         # попередню вітку гасимо
        finally:
            preview.wire(on_close=None)


def test_reopening_the_same_branch_does_not_stop_it():
    """Та сама вітка щойно піднята — гасити її було б пострілом у ногу."""
    stopped = []
    with _on():
        preview.wire(on_close=stopped.append)
        try:
            preview.open_session("br-1", 9100)
            preview.open_session("br-1", 9100)
            assert stopped == []
        finally:
            preview.wire(on_close=None)


def test_extend_only_works_on_a_live_session():
    with _on():
        assert preview.extend() is None
        preview.open_session("br-1", 9100)
        preview._slots[""]["until"] = 0
        assert preview.extend() is None


# ------------------------------------------------- кілька людей (21.09.2026)
# Доти слот був один на всіх: прев'ю колеги витісняло твоє і гасило його
# деплой. Тепер сесія — одна на людину, а деплой живе, поки ним користується
# хоч одна сесія.

def test_two_people_preview_at_the_same_time():
    stopped = []
    with _on():
        preview.wire(on_close=stopped.append)
        try:
            a = preview.open_session("br-a", 9100, uid="anna")["url"].split("k=")[1]
            b = preview.open_session("br-b", 9101, uid="bohdan")["url"].split("k=")[1]
            sid_a, sid_b = preview.redeem(a), preview.redeem(b)
            assert preview.session_for(sid_a)["port"] == 9100
            assert preview.session_for(sid_b)["port"] == 9101
            assert preview.public(uid="anna")["branch"] == "br-a"
            assert preview.public(uid="bohdan")["branch"] == "br-b"
            assert stopped == [], "прев'ю колеги погасило моє"
        finally:
            preview.wire(on_close=None)


def test_a_shared_deploy_lives_until_the_last_viewer_leaves():
    stopped = []
    with _on():
        preview.wire(on_close=stopped.append)
        try:
            preview.open_session("br-1", 9100, uid="anna")
            preview.open_session("br-1", 9100, uid="bohdan")
            preview.close("anna")
            assert stopped == [], "деплой погашено з-під колеги"
            preview.close("bohdan")
            assert stopped == ["br-1"]
        finally:
            preview.wire(on_close=None)


def test_moving_on_does_not_stop_a_deploy_a_colleague_still_watches():
    stopped = []
    with _on():
        preview.wire(on_close=stopped.append)
        try:
            preview.open_session("br-1", 9100, uid="anna")
            preview.open_session("br-1", 9100, uid="bohdan")
            preview.open_session("br-2", 9101, uid="anna")   # анна пішла далі
            assert stopped == []
            assert preview.public(uid="bohdan")["branch"] == "br-1"
        finally:
            preview.wire(on_close=None)


def test_the_cap_refuses_a_newcomer_instead_of_evicting_a_colleague():
    with _on(PREVIEW_MAX="2"):
        preview.open_session("br-a", 9100, uid="anna")
        preview.open_session("br-b", 9101, uid="bohdan")
        try:
            preview.open_session("br-c", 9102, uid="carol")
        except preview.PreviewBusy as e:
            assert "2 прев'ю" in str(e), str(e)
        else:
            raise AssertionError("стеля мовчки пропустила третю людину")
        assert preview.public(uid="anna") and preview.public(uid="bohdan")
        # а свою сесію людина при повних слотах міняти може
        preview.open_session("br-a2", 9103, uid="anna")
        assert preview.public(uid="anna")["branch"] == "br-a2"


def test_each_person_extends_and_closes_only_their_own():
    with _on():
        preview.open_session("br-a", 9100, uid="anna")
        preview.open_session("br-b", 9101, uid="bohdan")
        preview._slots["bohdan"]["until"] = time.time() + 5
        assert preview.extend("anna")["left"] > 60
        assert preview.public(uid="bohdan")["left"] <= 5, "продовжило чуже"
        assert preview.close("anna") is True
        assert preview.public(uid="bohdan") is not None, "закрило чуже"


def test_an_expired_cookie_closes_only_its_own_session():
    with _on():
        preview.open_session("br-a", 9100, uid="anna")
        tb = preview.open_session("br-b", 9101, uid="bohdan")["url"].split("k=")[1]
        sid_b = preview.redeem(tb)
        preview._slots["bohdan"]["until"] = 0
        assert preview.close_sid(sid_b) is True
        assert preview.public(uid="anna") is not None


# ------------------------------------------------- заголовки проксі

def test_domain_is_stripped_from_every_set_cookie():
    """`example.com` немає в Public Suffix List, тож вайт міг би поставити
    куку на батьківський домен, і браузер носив би її на сусідні застосунки
    компанії. Без атрибута кука лишається host-only."""
    out = preview.strip_domain("a=1; Path=/; Domain=.example.com; HttpOnly")
    assert "domain" not in out.lower(), out
    assert "a=1" in out and "HttpOnly" in out
    assert preview.strip_domain("a=1; DOMAIN=example.com") == "a=1"


def test_request_headers_drop_what_must_not_reach_the_white():
    with _on():
        got = preview.request_headers({
            "Authorization": "Basic ZXZpbA==",
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip",
            "Content-Length": "7",
            "If-Modified-Since": "Wed, 01 Oct 2026 00:00:00 GMT",
            "If-None-Match": '"abc"',
            "Cookie": f"{preview.COOKIE}=SECRET; consent=yes",
            "Accept": "text/html",
            "Host": "lab.example.com",
        }, HOST)
        low = {k.lower() for k in got}
        assert "authorization" not in low, "BasicAuth лаби протік у вайт"
        assert "connection" not in low and "accept-encoding" not in low
        assert "content-length" not in low
        assert "if-modified-since" not in low and "if-none-match" not in low, \
            "conditional-запит дав би 304 і воскресив картинку чужої вітки"
        assert got["Accept"] == "text/html"          # чуже лишаємо як є
        assert "SECRET" not in got["Cookie"], "наша кука протекла у PHP вайта"
        assert got["Cookie"] == "consent=yes"        # куки вайта живуть
        assert got["Host"] == HOST, "вайт будував би абсолютні лінки на лупбек"
        assert got["X-Forwarded-Proto"] in ("http", "https")


def test_request_headers_drop_cookie_entirely_when_only_ours():
    with _on():
        got = preview.request_headers({"Cookie": f"{preview.COOKIE}=SECRET"}, HOST)
        assert "Cookie" not in got


def test_response_headers_keep_repeated_set_cookie():
    """`requests.Response.headers` склеює кілька Set-Cookie в один рядок, тому
    app.py передає сюди `r.raw.headers.items()` — пари, а не мапу."""
    out = preview.response_headers([
        ("Content-Type", "text/html"),
        ("Content-Length", "123"),
        ("Content-Encoding", "gzip"),
        ("Transfer-Encoding", "chunked"),
        ("Set-Cookie", "a=1; Domain=.example.com"),
        ("Set-Cookie", "b=2"),
    ])
    keys = [k.lower() for k, _ in out]
    assert keys.count("set-cookie") == 2, out
    assert "content-length" not in keys and "content-encoding" not in keys
    assert "transfer-encoding" not in keys
    assert all("domain" not in v.lower() for k, v in out if k.lower() == "set-cookie")


def test_response_headers_strip_all_caching():
    """Прев'ю-хост один на всі вітки, шляхи картинок у партії однакові —
    кешувати НЕ МОЖНА (02.10: ca-en показував фото попередньої вітки).
    Validators теж зрізаються, інакше 304 лишить стару копію назавжди."""
    out = preview.response_headers([
        ("Content-Type", "image/jpeg"),
        ("Cache-Control", "max-age=86400"),
        ("Expires", "Thu, 01 Jan 2027 00:00:00 GMT"),
        ("ETag", '"abc123"'),
        ("Last-Modified", "Wed, 01 Oct 2026 00:00:00 GMT"),
    ])
    keys = [k.lower() for k, _ in out]
    for gone in ("expires", "etag", "last-modified"):
        assert gone not in keys, out
    cc = [v for k, v in out if k.lower() == "cache-control"]
    assert cc == ["no-store"], out


def test_every_preview_host_answer_is_no_store():
    """Кеш ріжеться не лише на проксі вайта, а на ВСЬОМУ прев'ю-хості. Наші
    404/410 Cloudflare кешує так само (`.jpg` → MISS, далі HIT, браузеру —
    max-age=14400; заміряно 05.10), і 410 після кінця сесії на
    `images/ph-02.jpg` забирав би це фото в наступного, хто відкриє прев'ю."""
    import asyncio
    import app
    from starlette.requests import Request

    async def no_next(_request):
        raise AssertionError("прев'ю-хост пустив запит далі по стеку")

    def ask(path, query=""):
        scope = {"type": "http", "method": "GET", "scheme": "http", "path": path,
                 "raw_path": path.encode(), "query_string": query.encode(),
                 "root_path": "", "server": (HOST, 80),
                 "headers": [(b"host", HOST.encode())]}
        return asyncio.run(app._preview_host(Request(scope), no_next))

    with _on():
        for resp in (ask("/images/ph-02.jpg"), ask("/__open", "k=not-a-token")):
            assert resp.status_code in (404, 410), resp.status_code
            assert resp.headers.getlist("cache-control") == ["no-store"], resp.headers


# ------------------------------------------------- стіна

def test_dispatch_middleware_is_the_outermost_one():
    """`add_middleware` вставляє на початок списку, а стек будується
    `reversed()` — тож доданий ОСТАННІМ виконується ПЕРШИМ. Переставиш блоки
    в app.py місцями, і `/__open` почне отримувати 302 на /login."""
    import app
    names = [m.kwargs["dispatch"].__name__ for m in app.app.user_middleware]
    assert names[0] == "_preview_host", names


def test_preview_branch_has_no_continuation():
    """Головна гарантія: на прев'ю-хості запит НЕ йде далі по стеку. Не список
    винятків, а відсутність продовження — тому дірку «дійти до API лаби через
    піддомен» не можна відкрити, забувши щось у списку."""
    body = APP_SRC[APP_SRC.index("async def _preview_host"):]
    body = body[:body.index("async def _preview_serve")]
    calls = re.findall(r"call_next\(request\)", body)
    assert len(calls) == 1, f"call_next зустрічається {len(calls)} разів, очікується 1"
    # і він стоїть у гілці «це НЕ прев'ю-хост»
    assert re.search(r"if not preview\.is_preview_host\([\s\S]*?\):\s*\n\s*return await call_next",
                     body), body

    serve = APP_SRC[APP_SRC.index("async def _preview_serve"):]
    serve = serve[:serve.index("\ndef current_user")]
    assert "call_next" not in serve, "обробник прев'ю вміє пропустити запит далі"


def test_proxy_target_is_not_taken_from_the_request():
    """SSRF: порт береться зі слоту на сервері. Якби ціль приходила
    параметром, проксі перетворився б на «сходи» всередину кластера."""
    serve = APP_SRC[APP_SRC.index("async def _preview_serve"):]
    serve = serve[:serve.index("\ndef current_user")]
    assert 'f"http://127.0.0.1:{slot[\'port\']}{path}"' in serve, serve
    for src in ("query_params.get(\"url\"", "query_params.get(\"target\"",
                "query_params.get(\"port\"", "headers.get(\"x-target"):
        assert src not in serve, f"ціль проксі приходить ззовні: {src}"


def test_open_waits_until_php_actually_listens():
    """`_serve()` віддає порт одразу після Popen. Без очікування людина
    відкриє вкладку швидше, ніж php займе сокет, і побачить 502 (спіймано
    на першому ж наскрізному прогоні)."""
    assert "preview.wait_ready(port)" in APP_SRC


# ------------------------------------------------- куди веде кнопка «відкрити»
# Прев'ю приробили рівно до однієї кнопки 👁 на картці вітки, а решта місць
# далі роздавала лупбек. На проді 28.08 колега натиснув велику «▶ Deploy» і
# отримав «не вдалося з'єднатися» на 127.0.0.1:9100 — php працював, мертвою
# була адреса. Нижче закріплено, що ЖОДЕН шлях «відкрити вітку» не веде на
# лупбек, поки заведено піддомен.

def test_running_port_is_reported_for_a_live_deploy():
    """Прев'ю мусить упізнавати вже запущений деплой: інакше «▶ Deploy» піднімає
    вітку двічі поспіль, а на node другий білд ще й чекає у HTTP-запиті."""
    import deployer
    old_key, old_running = deployer._key, dict(deployer._running)
    deployer._key = lambda b: "p::" + b            # без читання стану проєкту
    try:
        deployer._running.clear()
        assert deployer.running_port("br-x") is None
        deployer._running["p::br-x"] = {"proc": None, "port": 9137}
        assert deployer.running_port("br-x") == 9137
    finally:
        deployer._key = old_key
        deployer._running.clear()
        deployer._running.update(old_running)


def test_preview_does_not_redeploy_what_already_runs():
    """`deploy()` лишається ЛИШЕ в гілці «ще не запущено». Свіжість копії
    тримає вотчер деплою, а не повторний підйом."""
    body = APP_SRC[APP_SRC.index("def preview_open("):]
    body = body[:body.index("@app.on_event")]
    assert "deployer.running_port(branch)" in body
    head, sep, tail = body.partition("if port is None:")
    assert sep, "зникла розвилка «вже запущено / піднімаємо»"
    assert "deployer.deploy(" not in head, "деплой стартує до перевірки"
    assert "deployer.deploy(" in tail


def test_deploys_page_hands_the_browser_no_loopback_link():
    """Сторінка /deploys рендериться на сервері, тож лупбек їде в браузер
    готовим лінком — жодного JS, який міг би його підмінити."""
    import app
    rows = [{"branch": "feature/x", "port": 9100, "url": "http://127.0.0.1:9100/"}]
    old = app.deployer.list_deploys
    app.deployer.list_deploys = lambda: rows
    try:
        with _on():
            on = app.deploy_index()
        with _env(PREVIEW_HOST=""):
            off = app.deploy_index()
    finally:
        app.deployer.list_deploys = old
    assert "127.0.0.1" not in on, "піддомен заведено, а сторінка веде на лупбек"
    assert "/api/preview/" in on, "рядок мусить відкривати вітку через піддомен"
    assert "http://127.0.0.1:9100/" in off, \
        "без піддомена лупбек — єдиний спосіб відкрити деплой, і він лишається"


def test_the_deploys_page_ships_parsable_js():
    """JS сторінки /deploys живе всередині f-рядка Python, тож екранування
    там подвійне: зворотний слеш з апострофом у потрійних лапках згортається
    в голий апостроф — і скрипт мовчки перестає парситися, а кнопки просто
    нічого не роблять. У HTML і в логах цього не видно; ловить лише
    синтаксис. Спіймано 28.08 на `node --check`, а не очима."""
    import shutil
    import tempfile
    import app
    node = shutil.which("node")
    if not node:
        print("    (node немає — перевірка синтаксису пропущена)")
        return
    rows = [{"branch": "feature/x", "port": 9100, "url": "http://127.0.0.1:9100/"}]
    old = app.deployer.list_deploys
    app.deployer.list_deploys = lambda: rows
    try:
        with _on():
            page = app.deploy_index()
    finally:
        app.deployer.list_deploys = old
    js = re.search(r"<script>([\s\S]*?)</script>", page)
    assert js, "на сторінці більше немає скрипта — перевірка нічого не стереже"
    f = tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False)
    f.write(js.group(1))
    f.close()
    try:
        r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    finally:
        os.unlink(f.name)


def test_every_open_path_in_the_ui_asks_previewon_first():
    """Місця в UI, що роздають адресу деплою людині: кнопка «▶ Deploy» і
    панель деплоїв. Кожне під розвилкою.

    Було три — третім була вкладка локальних вайтів, але 31.08 автор виніс
    увесь той пайплайн в окремий сервіс, і вкладки в лабі немає. Поріг
    опущено до двох свідомо: він стереже не кількість, а те, що перевірка
    взагалі щось знаходить (нуль означав би, що змінилась форма рядка)."""
    lines = UI_SRC.splitlines()
    uses = [i for i, l in enumerate(lines)
            if re.search(r"href=\"\$\{[dr]\.url\}|window\.open\([dr]\.url", l)]
    assert len(uses) >= 2, f"змінилась форма — перевірка вже нічого не стереже: {uses}"
    for i in uses:
        ctx = "\n".join(lines[max(0, i - 2):i + 1])
        assert "previewOn" in ctx, f"лупбек без розвилки, рядок {i + 1}: {lines[i].strip()}"


def test_deploy_button_opens_its_tab_before_the_first_await():
    """Вкладку відкриває сам обробник кліка. Після await браузер більше не
    вважає window.open() дією користувача і глушить вікно блокувальником —
    саме тому previewTab() винесено окремо від openPreview()."""
    body = UI_SRC[UI_SRC.index("$('#deployBtn').onclick"):]
    body = body[:body.index("\n};")]
    assert "previewTab(activeBranch)" in body, "кнопка не готує вкладку сама"
    assert body.index("previewTab(activeBranch)") < body.index("await "), \
        "вкладка відкривається після await — блокувальник її з'їсть"


# ------------------------------------------------- lockstep з шаблонами

def test_preview_host_is_wired_into_both_env_templates():
    assert re.search(r"^PREVIEW_HOST=$", ENV_DEV, re.M), \
        ".env.example мусить мати порожній PREVIEW_HOST (локально вимкнено)"
    assert re.search(r"^PREVIEW_HOST=\{\{PREVIEW_HOST\}\}$", ENV_PROD, re.M), \
        ".env.prod.example мусить брати PREVIEW_HOST з CI-змінної"


# --------------------------------------------------- ім'я піддомену в CI

def _derive_snippet() -> str:
    """Шматок шелу, що виводить ім'я, — витягнутий ПРЯМО з пайплайна.

    Копіювати його в тест не можна: копія розійдеться з оригіналом, і тест
    стерегтиме вже не те, що поїде в прод.
    """
    lines = CI.splitlines()
    i = next(n for n, l in enumerate(lines)
             if "export PREVIEW_HOST=" in l and not l.lstrip().startswith("#"))
    start = i
    while not lines[start].strip().startswith("- >"):
        start -= 1
        assert start > 0, "рядок export PREVIEW_HOST не всередині блока `- >`"
    return "\n".join(l.strip() for l in lines[start + 1:i + 1])


def _derive(domain: str, preview=None) -> str:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "DOMAIN_NAME": domain}
    if preview is not None:
        env["PREVIEW_HOST"] = preview
    r = subprocess.run(["/bin/sh", "-c",
                        _derive_snippet() + '\nprintf "%s" "$PREVIEW_HOST"'],
                       env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8")


def test_preview_host_is_derived_from_the_domain():
    """Незаведена змінна має дати робочий піддомен, а не порожнечу: інакше
    прев'ю в проді вимкнене доти, доки хтось не згадає завести змінну."""
    if not os.path.exists("/bin/sh"):
        return                               # шебанг — лише POSIX
    assert _derive("lab.example.com") == "lab-preview.example.com"


def test_derived_name_stays_one_label_deep():
    """Головна вимога, з якої взялось саме таке ім'я: wildcard і в DNS, і в
    TLS (RFC 6125) матчить РІВНО ОДИН лейбл. `preview.lab.…` під
    `*.example.com` уже не підпадає, і це коштувало б окремого DNS-запису
    та окремого серта. Тому лейблів у виведеному імені мусить бути стільки ж,
    скільки в самому домені.
    """
    if not os.path.exists("/bin/sh"):
        return                               # шебанг — лише POSIX
    for domain in ("lab.example.com", "wp.lab.example.com", "a.b"):
        got = _derive(domain)
        assert got.count(".") == domain.count("."), \
            f"{domain} -> {got}: у прев'ю-імені зайвий рівень, wildcard його не покриє"


def test_empty_variable_still_turns_preview_off():
    """Дефіс у `${PREVIEW_HOST-$d}` один саме заради цього: заведена порожньою
    змінна — єдиний спосіб вимкнути прев'ю в проді. З `:-` вона отримала б
    виведене ім'я, і вимикача не лишилось би взагалі."""
    if not os.path.exists("/bin/sh"):
        return                               # шебанг — лише POSIX
    assert _derive("lab.example.com", preview="") == ""


def test_explicit_value_wins_over_the_derived_one():
    if not os.path.exists("/bin/sh"):
        return                               # шебанг — лише POSIX
    assert _derive("lab.example.com", preview="my.example.com") == "my.example.com"


def test_domain_without_a_dot_derives_nothing():
    """Порожній або однолейбловий DOMAIN_NAME не має народжувати `-preview`
    без домену: Traefik отримав би сміттєвий `Host()` замість вимкненої фічі."""
    if not os.path.exists("/bin/sh"):
        return                               # шебанг — лише POSIX
    assert _derive("localhost") == ""
    assert _derive("") == ""


def test_preview_host_reaches_the_traefik_label():
    """Значення потрібне ДВІЧІ: у `.env` для застосунку і в ЛЕЙБЛІ Traefik.
    Друге бере тільки оточення процесу (`docker stack deploy` не читає `.env`
    для інтерполяції), тому без export лейбл поїхав би порожнім — рівно ті
    граблі, на яких 19.08 згорів BasicAuth."""
    assert "export PREVIEW_HOST=" in CI
    assert "${PREVIEW_HOST:-preview.disabled.invalid}" in COMPOSE, \
        "у лейблі роутера немає дефолту — порожній Host() Traefik відкидає з помилкою"


if __name__ == "__main__":
    run(dict(globals()))
