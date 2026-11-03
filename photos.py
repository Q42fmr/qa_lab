"""Пошук безкоштовних стокових фото за темою — для заміни картинок на вайтах.

Провайдер вмикається наявністю ключа у .env (пріоритет зверху вниз):
  MAGNIFIC_API_KEY  — Stock Content API magnific.com (колишній Freepik API).
                      Ключ видає саппорт (Dashboard → Contact us). URL-и
                      нормалізуються під img.magnific.com/...?w=740 — рівно
                      той формат, що вже стоїть на вайтах.
  PEXELS_API_KEY    — pexels.com/api: миттєвий безкоштовний ключ,
                      200 запитів/год; хотлінк дозволений.
  PIXABAY_API_KEY   — pixabay.com/api/docs: миттєвий безкоштовний ключ.

Всі провайдери повертають однаковий формат:
  {thumb (мініатюра для галереї), url (підставляється у вайт),
   big (більший розмір), title, page (сторінка джерела)}
У magnific `big` (?w=1380) для безкоштовних фото йде з водяним знаком
«Magnific» по діагоналі (cedko-ia 27.10) — у вайт ставиться `url` (?w=740),
він чистий, як і 626px без параметра.
"""

from __future__ import annotations

import os
import time

import requests

_cache: dict[tuple, tuple[float, dict]] = {}
TTL = 15 * 60          # повторний пошук тієї ж теми не палить ліміти


def provider() -> str | None:
    if os.getenv("MAGNIFIC_API_KEY", "").strip():
        return "magnific"
    if os.getenv("PEXELS_API_KEY", "").strip():
        return "pexels"
    if os.getenv("PIXABAY_API_KEY", "").strip():
        return "pixabay"
    # без жодного ключа: скрейп пошукової сторінки magnific headless-Chrome-ом
    # (серверні запити Cloudflare ріже 403, а справжній Chrome проходить)
    try:
        import deployer
        deployer._browser_bin()
        return "magnific-web"
    except Exception:
        return None


def search(q: str, orientation: str = "", page: int = 1) -> dict:
    prov = provider()
    if not prov:
        raise ValueError(
            "не задано ключ фото-провайдера у .env: MAGNIFIC_API_KEY "
            "(magnific.com → Dashboard → Contact us), PEXELS_API_KEY "
            "(pexels.com/api — миттєво) або PIXABAY_API_KEY (pixabay.com/api/docs). "
            "Після додавання ключа рестартни сервер.")
    ckey = (prov, q.lower().strip(), orientation, page)
    hit = _cache.get(ckey)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    results = {"magnific": _magnific, "pexels": _pexels, "pixabay": _pixabay,
               "magnific-web": _magnific_web}[prov](q, orientation, page)
    out = {"provider": prov, "query": q, "page": page, "results": results}
    if len(_cache) > 200:
        _cache.pop(next(iter(_cache)))
    _cache[ckey] = (time.time(), out)
    return out


def _magnific(q: str, orientation: str, page: int) -> list[dict]:
    params = {"term": q, "page": page, "limit": 30, "order": "relevance",
              "filters[content_type][photo]": 1,
              "filters[license][freemium]": 1}       # лише безкоштовні
    if orientation in ("landscape", "portrait", "square"):
        params[f"filters[orientation][{orientation}]"] = 1
    r = requests.get("https://api.magnific.com/v1/resources",
                     headers={"x-magnific-api-key": os.environ["MAGNIFIC_API_KEY"].strip()},
                     params=params, timeout=30)
    r.raise_for_status()
    out = []
    for it in r.json().get("data", []):
        src = ((it.get("image") or {}).get("source") or {}).get("url") or ""
        if not src:
            continue
        # img.freepik.com і img.magnific.com — дзеркала; тримаємось magnific,
        # як у наявних вайтах, і керуємо розміром через ?w=
        base = src.split("?")[0].replace("img.freepik.com", "img.magnific.com")
        out.append({"thumb": base + "?w=360", "url": base + "?w=740",
                    "big": base + "?w=1380", "title": it.get("title", ""),
                    "page": it.get("url", "")})
    return out


def _pexels(q: str, orientation: str, page: int) -> list[dict]:
    params = {"query": q, "per_page": 30, "page": page}
    if orientation in ("landscape", "portrait", "square"):
        params["orientation"] = orientation
    r = requests.get("https://api.pexels.com/v1/search",
                     headers={"Authorization": os.environ["PEXELS_API_KEY"].strip()},
                     params=params, timeout=30)
    r.raise_for_status()
    return [{"thumb": p["src"]["medium"], "url": p["src"]["large"],
             "big": p["src"].get("large2x", p["src"]["large"]),
             "title": p.get("alt") or p.get("photographer", ""),
             "page": p.get("url", "")}
            for p in r.json().get("photos", [])]


def _magnific_web(q: str, orientation: str, page: int) -> list[dict]:
    """Без API-ключа: headless-Chrome відкриває пошук magnific (фото + free),
    чекає рендер і збирає лінки мініатюр — та сама логіка, що й userscript
    (figure[data-cy="resource-thumbnail"] img → src без query + ?w=)."""
    import json as _json
    import socket
    import subprocess
    import time as _time
    import urllib.parse

    import deployer
    from websockets.sync.client import connect as ws_connect

    url = ("https://www.magnific.com/search?query="
           + urllib.parse.quote_plus(q) + "&type=photo&license=free")
    if orientation in ("landscape", "portrait", "square"):
        url += "&orientation=" + orientation
    if page > 1:
        url += f"&page={page}"

    browser = deployer._browser_bin()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dbg = s.getsockname()[1]
    proc = subprocess.Popen(
        [browser, "--headless=new", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", "--window-size=1500,1200",
         "--disable-blink-features=AutomationControlled"]   # інакше security-фільтр ріже 403
        + deployer.browser_extra_args()
        + [f"--remote-debugging-port={dbg}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        page_ws = None
        for _ in range(50):
            try:
                targets = requests.get(f"http://127.0.0.1:{dbg}/json", timeout=2).json()
                page_ws = next(t for t in targets if t.get("type") == "page")
                break
            except Exception:
                _time.sleep(0.2)
        if not page_ws:
            raise RuntimeError("chrome не відкрив debug-порт")

        with ws_connect(page_ws["webSocketDebuggerUrl"], max_size=32 * 1024 * 1024) as ws:
            mid = [0]

            def cmd(method, **params):
                mid[0] += 1
                ws.send(_json.dumps({"id": mid[0], "method": method, "params": params}))
                while True:
                    msg = _json.loads(ws.recv(timeout=45))
                    if msg.get("id") == mid[0]:
                        if "error" in msg:
                            raise RuntimeError(f"{method}: {msg['error']}")
                        return msg.get("result", {})

            def thumbs():
                # усі мініатюри стоків на сторінці (стійкіше за data-cy селектор)
                r = cmd("Runtime.evaluate", returnByValue=True, expression="""
                    [...document.querySelectorAll('img')].map(i=>i.src)
                      .filter(s=>/img\\.(magnific|freepik)\\.com\\/free-/.test(s))""")
                return r.get("result", {}).get("value") or []

            # маскування headless: стандартний UA (без "HeadlessChrome") і без navigator.webdriver
            cmd("Network.enable")
            cmd("Network.setUserAgentOverride",
                userAgent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                platform="Win32", acceptLanguage="en-US,en")
            cmd("Page.enable")
            cmd("Page.addScriptToEvaluateOnNewDocument",
                source="Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
            cmd("Page.navigate", url=url)
            # чекаємо, поки JS відрендерить сітку (Cloudflare-челендж = порожньо)
            urls, deadline = [], _time.time() + 25
            while _time.time() < deadline:
                _time.sleep(1.2)
                try:
                    urls = thumbs()
                except Exception:
                    urls = []
                if len(urls) >= 12:
                    break
            if urls and len(urls) < 30:           # догортаємо за другою порцією
                try:
                    cmd("Runtime.evaluate", expression="window.scrollBy(0, 2500)")
                    _time.sleep(1.5)
                    urls = thumbs() or urls
                except Exception:
                    pass
        if not urls:
            raise RuntimeError("сторінка пошуку не віддала мініатюр "
                               "(можливо, Cloudflare-челендж) — спробуй ще раз "
                               "або відкрий пошук у своєму браузері з вкладки «Фото БД»")
        out, seen = [], set()
        for src in urls:
            base = src.split("?")[0].replace("img.freepik.com", "img.magnific.com")
            if base in seen:
                continue
            seen.add(base)
            out.append({"thumb": base + "?w=360", "url": base + "?w=740",
                        "big": base + "?w=1380", "title": base.rsplit("/", 1)[-1],
                        "page": ""})
        return out
    finally:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass


def _pixabay(q: str, orientation: str, page: int) -> list[dict]:
    orient = {"landscape": "horizontal", "portrait": "vertical"}.get(orientation, "all")
    r = requests.get("https://pixabay.com/api/",
                     params={"key": os.environ["PIXABAY_API_KEY"].strip(), "q": q,
                             "image_type": "photo", "orientation": orient,
                             "per_page": 30, "page": page, "safesearch": "true"},
                     timeout=30)
    r.raise_for_status()
    return [{"thumb": h["previewURL"], "url": h["webformatURL"],
             "big": h.get("largeImageURL", h["webformatURL"]),
             "title": h.get("tags", ""), "page": h.get("pageURL", "")}
            for h in r.json().get("hits", [])]
