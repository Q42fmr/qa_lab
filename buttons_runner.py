"""Кнопки: чи працює кожен клікабельний елемент сторінки, і прибрати мертві.

QA 21.10 — окремий клас скарг «кнопка/стрілка/лінк нічого не робить»:
стрілки галереї без JS (piivabmekwok), пагінація на неіснуючі сторінки
(mac-colsetfugii, 27 лінків), «Select Language» без скрипта (picoispaaq),
«Sign Up» без бекенду (apodkoril). Статично це не видно — обробник може
сидіти в будь-якому бандлі; видно лише, якщо натиснути.

run(branch) піднімає той самий деплой, що візуальні перевірки, і на кожній
сторінці (desktop + mobile) перебирає видимі `a`/`button`/`[role=button]`
поза формами (формами володіє прогін форми і `form_hijack`):

* лінк на сторінку цього ж сайту — чи є така сторінка у деплої (файл або
  роут vue); HTTP-статус тут не каже нічого: і `php -S`, і хостинг на
  невідомий шлях віддають головну;
* `#якір` з наявною ціллю — робочий без кліку;
* решта (`href="#"`, `javascript:`, кнопки) — наведення + клік і 0.6 с
  спостереження: зміни DOM, скрол, hash, window.open, перехід, медіа.
  Нічого з цього → мертвий. Навігація кліком перехоплюється (сторінка не
  йде), автоплей слайдерів зупиняється до тестів (інакше його мутації
  виглядали б як реакція на клік), мутації, що йдуть і без кліку, не
  рахуються.

Той самий елемент хедера/футера на 20 сторінках тестується один раз
(підпис: тег + href + класи + текст). Фікс — видалити елемент з джерела в
УСІХ файлах вітки, де він стоїть; якщо елемент — єдиний вміст обгортки
(`<li>` пагінації), іде обгортка, щоб не лишати порожніх пунктів.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import threading
import time
from pathlib import Path

import deployer
import projects
import visual_runner as vr
from runner import snapshot_dir

MAX_PER_PAGE = 60          # нових (ще не тестованих) елементів на сторінку
MAX_RELOADS = 6            # JS-навігацій кліком на сторінку, після яких — далі
WAIT_MS = 600              # спостереження після кліку


def root() -> Path:
    return projects.state_dir() / "buttons"


def result_path(branch: str) -> Path:
    return root() / f"{vr._stem(branch)}.json"


# ---------------------------------------------------------------- браузер
INIT_JS = r"""
(() => {
  const W = window;
  if (!W.__btnSt) {
    const st = W.__btnSt = {nav: null, opened: null, hash: 0};
    W.open = function (u) { st.opened = String(u || ''); return null; };
    W.addEventListener('hashchange', () => { st.hash++; });
    // ОСТАННІЙ у ланцюжку кліку: обробники сайту вже відпрацювали. Перехід
    // на іншу сторінку глушимо (записуємо, куди вів) — інакше таб пішов би.
    W.addEventListener('click', e => {
      const a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
      if (!a) return;
      const raw = (a.getAttribute('href') || '').trim();
      // перехід на «#» — стрибок нагору, а не функція кнопки
      if (raw === '#' || raw === '') { e.preventDefault(); return; }
      if (/^javascript:/i.test(raw)) return;
      if (e.defaultPrevented) return;
      let u; try { u = new URL(a.href, location.href); } catch (_) { return; }
      if (u.origin === location.origin && u.pathname === location.pathname && u.search === location.search) return;
      e.preventDefault(); st.nav = u.href;
    });
    document.addEventListener('submit', e => { e.preventDefault(); st.nav = st.nav || 'submit'; }, true);
    // автоплей слайдерів/лічильники: інакше їхні мутації = «реакція на клік»
    const top = setTimeout(() => {}, 0);
    for (let i = 1; i <= top + 50; i++) { clearTimeout(i); clearInterval(i); }
  }
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const vis = el => {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    for (let e = el; e; e = e.parentElement) {
      const c = getComputedStyle(e);
      if (c.display === 'none' || c.visibility === 'hidden' || +c.opacity === 0) return false;
    }
    return true;
  };
  // стан, а не ідентичність: «активна» точка слайдера, поточний пункт меню
  const STATE = /(^|[-_])(active|current|selected|show|open|opened)$|^(aos-init|aos-animate|animated|focus|hover|in|collapsed|current-menu-item)$/;
  const desc = x => ({
    tag: x.tagName.toLowerCase(), id: x.id || '',
    cls: [...x.classList].filter(c => !STATE.test(c)),
    href: x.getAttribute('href'), type: x.getAttribute('type'),
    aria: x.getAttribute('aria-label'), role: x.getAttribute('role'),
    text: norm(x.textContent).slice(0, 300),
  });
  const SKIP_HREF = /^(tel:|mailto:|sms:|whatsapp:|viber:|skype:|callto:|data:)/i;
  const out = [];
  W.__btnEls = [];
  const els = document.querySelectorAll('a, button, [role="button"], input[type="button"]');
  for (const el of els) {
    if (el.closest('form, [id^="__vis"], .grecaptcha-badge')) continue;
    if (el.tagName !== 'A' && el.closest('a[href]')) continue;
    if (el.tagName === 'A' && el.parentElement && el.parentElement.closest('button')) continue;
    if (!vis(el)) continue;
    if (/history\.(back|go)\b/i.test(el.getAttribute('onclick') || '')) continue;
    const tag = el.tagName.toLowerCase();
    const href = el.getAttribute('href');
    let kind = 'click', url = '';
    if (tag === 'a' && href !== null) {
      const raw = href.trim();
      if (SKIP_HREF.test(raw) || el.hasAttribute('download')) continue;
      // «назад» на щойно відкритій сторінці історії не має — тест збрехав би
      if (/history\.(back|go)\b/i.test(raw)) continue;
      if (raw && !raw.startsWith('#') && !/^javascript:/i.test(raw)) {
        let u; try { u = new URL(el.href, location.href); } catch (e) { continue; }
        if (!/^https?:$/.test(u.protocol) || u.origin !== location.origin) continue;  // чужий сайт — не наш
        if (u.pathname === location.pathname && u.search === location.search) {
          if (u.hash.length <= 1) continue;                                          // лінк на себе
          if (document.getElementById(decodeURIComponent(u.hash.slice(1)))) continue;
        } else { kind = 'link'; url = u.origin + u.pathname + u.search; }
      } else if (raw.length > 1 && raw.startsWith('#')) {
        const id = decodeURIComponent(raw.slice(1));
        if (document.getElementById(id) || document.getElementsByName(id).length) continue;  // якір з ціллю
      }
      // батько випадного меню: працює наведенням, клік нічого не мусить робити
      const li = el.parentElement && el.parentElement.closest('li');
      if (kind !== 'link' && li && li.querySelector(':scope > ul, :scope > .sub-menu, :scope > .dropdown-menu, :scope > div ul')) continue;
    }
    const img = el.querySelector('img');
    let label = norm(el.innerText || el.value || '') || el.getAttribute('aria-label') || el.title || (img && img.alt) || '';
    if (!label) label = '[' + tag + (el.classList.length ? '.' + [...el.classList].slice(0, 3).join('.') : '') + ']';
    // ланцюжок для видалення: сам елемент і обгортки, у яких він — єдиний вміст
    const chain = [desc(el)];
    let x = el;
    for (let k = 0; k < 2; k++) {
      const p = x.parentElement;
      if (!p || !/^(LI|DIV|SPAN|P)$/.test(p.tagName) || p.children.length !== 1) break;
      if (norm(p.textContent) !== norm(x.textContent)) break;
      if (p.matches('body, main, header, footer, nav, section, [id="app"]')) break;
      chain.unshift(desc(p)); x = p;
    }
    const d = chain[chain.length - 1];
    const active = [...el.classList].some(c => STATE.test(c))
      || el.hasAttribute('aria-current') || el.getAttribute('aria-selected') === 'true' || el.getAttribute('aria-pressed') === 'true'
      || (el.parentElement && el.parentElement.tagName === 'LI' && [...el.parentElement.classList].some(c => STATE.test(c)));
    // група — спільний контейнер однотипних контролів (точки слайдера, пагінація)
    let box = x.parentElement;
    const grp = box ? [box.tagName, [...box.classList].filter(c => !STATE.test(c)).slice(0, 3).join('.'),
                       box.parentElement ? box.parentElement.tagName + '.' + [...box.parentElement.classList].slice(0, 2).join('.') : '',
                       tag].join('|') : '';
    const sig = [tag, href || '', d.cls.slice().sort().join('.'), d.aria || '', d.text.slice(0, 120)].join('|');
    const r = el.getBoundingClientRect();
    out.push({i: W.__btnEls.length, kind, url, sig, label: label.slice(0, 90), tag, href, active, grp,
              rect: {x: Math.max(0, r.left + scrollX), y: Math.max(0, r.top + scrollY),
                     width: r.width, height: r.height},
              chain});
    W.__btnEls.push(el);
  }
  W.__btnTest = async (i) => {
    const el = W.__btnEls[i];
    if (!el || !el.isConnected) return {gone: true};
    const st = W.__btnSt, sleep = ms => new Promise(r => setTimeout(r, ms));
    const OPTS = {subtree: true, childList: true, attributes: true, characterData: true};
    const IGN = /^data-(focus-visible-added|what)/;
    const own = n => n && n.nodeType === 1 && (n.id || '').startsWith('__vis');
    const noisy = new Set();
    let mo = new MutationObserver(ms => ms.forEach(m => noisy.add(m.target)));
    mo.observe(document.documentElement, OPTS);
    await sleep(200); mo.disconnect();
    const hits = [];
    mo = new MutationObserver(ms => ms.forEach(m => {
      if (noisy.has(m.target) || own(m.target)) return;
      if (m.type === 'attributes' && IGN.test(m.attributeName || '')) return;
      hits.push(m);
    }));
    mo.observe(document.documentElement, OPTS);
    const y0 = scrollY, x0 = scrollX, h0 = st.hash, href0 = location.href;
    const media = () => [...document.querySelectorAll('video, audio')].map(m => m.paused).join();
    const m0 = media();
    st.nav = null; st.opened = null;
    let err = '';
    const onErr = e => { err = err || String((e && e.message) || e).slice(0, 140); };
    W.addEventListener('error', onErr);
    try {
      const r = el.getBoundingClientRect();
      const o = {bubbles: true, cancelable: true, view: W, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2};
      for (const t of ['pointerover', 'mouseover', 'pointerenter', 'mouseenter', 'pointerdown', 'mousedown', 'pointerup', 'mouseup'])
        el.dispatchEvent(new (t.startsWith('pointer') && W.PointerEvent ? PointerEvent : MouseEvent)(t, o));
      el.click();
    } catch (e) { err = err || String(e).slice(0, 140); }
    let effect = '';
    for (let t = 0; t < 6 && !effect; t++) {
      await sleep(100);
      effect = st.nav ? 'перехід: ' + st.nav
        : st.opened !== null ? 'нове вікно: ' + st.opened
        : hits.length ? 'змінився DOM (' + hits.length + ')'
        : (scrollY !== y0 || scrollX !== x0) ? 'скрол'
        : (st.hash !== h0 || location.href !== href0) ? 'hash'
        : media() !== m0 ? 'медіа' : '';
    }
    mo.disconnect(); W.removeEventListener('error', onErr);
    // відкрите (модалка/меню) закриваємо, щоб не заважало наступним
    if (effect) document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
    return {effect, err};
  };
  return out;
})()
"""


def _target_exists(branch: str, url_path: str, routes: set) -> bool:
    """Чи є на сайті сторінка за цим шляхом. Не HTTP-статус: і `php -S`, і
    хостинг вайтів на невідомий шлях віддають головну (200), тож
    `/page/2/` «працював» би, показуючи не ту сторінку. Звіряємо з файлами
    деплою (і клієнтськими роутами vue-вайта)."""
    from urllib.parse import unquote, urlsplit
    path = unquote(urlsplit(url_path).path) or "/"
    if path in routes or path.rstrip("/") in routes or (path.rstrip("/") + "/") in routes:
        return True
    doc = vr._deploy_docroot(branch)
    rel = path.lstrip("/")
    cands = [rel] if rel else []
    base = rel.rstrip("/")
    cands += [f"{base}/index.html", f"{base}/index.php", f"{base}/index.htm",
              f"{base}.html", f"{base}.php"] if base else ["index.html", "index.php"]
    return any((doc / c).is_file() for c in cands)


def run(branch: str, max_pages: int = vr.MAX_PAGES) -> dict:
    root().mkdir(parents=True, exist_ok=True)
    keep = deployer.is_running(branch)
    d = deployer.deploy(branch, wait=True)
    base = d["url"].rstrip("/")
    all_pages = vr._list_pages(branch)
    pages = all_pages[:max_pages]
    routes = set(vr._router_pages(branch))

    guard = threading.Lock()
    tested: dict = {}           # sig -> {"effect", "err"} | None (у роботі)
    seen: dict = {}             # sig -> запис знахідки (сторінки/в'юпорти)
    stats = {"tested": 0, "ok": 0, "links": 0}

    def note(c: dict, page: str, kind: str):
        with guard:
            rec = seen.setdefault(c["sig"], {"sig": c["sig"], "label": c["label"], "tag": c["tag"],
                                             "href": c["href"], "chain": c["chain"], "kind": c["kind"],
                                             "url": c["url"], "active": c.get("active"), "grp": c.get("grp", ""),
                                             "pages": [], "views": []})
            if page not in rec["pages"]:
                rec["pages"].append(page)
            if kind not in rec["views"]:
                rec["views"].append(kind)

    def work(p: "vr._Page", kind: str, page: str):
        reloads = 0
        while True:
            p.eval("new Promise(r => setTimeout(r, 600))", await_promise=True)
            cands = p.eval(INIT_JS) or []
            for c in cands:
                note(c, page, kind)
            todo = []
            with guard:
                for c in cands:
                    if c["kind"] == "click" and c["sig"] not in tested and len(todo) < MAX_PER_PAGE:
                        tested[c["sig"]] = None
                        todo.append(c)
            navigated = False
            for c in todo:
                try:
                    r = p.eval(f"window.__btnTest({c['i']})", await_promise=True) or {}
                except Exception:
                    # контекст знищено — клік перевів сторінку скриптом: працює
                    r = {"effect": "перехід скриптом", "err": ""}
                    navigated = True
                if r.get("gone"):
                    with guard:
                        tested.pop(c["sig"], None)       # перевіримо на іншій сторінці
                    continue
                if not r.get("effect"):
                    try:
                        png = p.shot({"x": max(0, c["rect"]["x"] - 10), "y": max(0, c["rect"]["y"] - 10),
                                      "width": min(1200, c["rect"]["width"] + 20),
                                      "height": min(400, c["rect"]["height"] + 20)})
                        r["preview"] = base64.b64encode(png).decode()
                    except Exception:
                        pass
                with guard:
                    tested[c["sig"]] = r
                    stats["tested"] += 1
                    stats["ok"] += 1 if r.get("effect") else 0
                if navigated:
                    break
            if not navigated or reloads >= MAX_RELOADS:
                return []
            reloads += 1
            p.cmd("Page.navigate", url=base + page)
            end = time.time() + 20
            while time.time() < end:
                try:
                    if p.eval("document.readyState") == "complete":
                        break
                except Exception:
                    pass
                time.sleep(0.3)
            try:
                p.eval(vr.SETTLE_FORM_JS, await_promise=True)
            except Exception:
                pass

    try:
        res = vr._open(deployer._browser_bin(), base, vr.VIEWPORTS, pages, work,
                       settle_js=vr.SETTLE_JS, load_event="Page.loadEventFired",
                       load_timeout=25)
    finally:
        if not keep:
            deployer.stop(branch)

    # лінки: статус цілі (по одному запиту на адресу)
    link_urls = {r["url"] for r in seen.values() if r["kind"] == "link"}
    exists = {u: _target_exists(branch, u[len(base):] or "/", routes) for u in link_urls}
    stats["links"] = len(link_urls)

    # Активний елемент групи (поточна точка слайдера) клік і в робочому слайдері
    # не міняє — його вердикт беремо від сусідів по групі: хоч один живий →
    # група жива. Без сусідів «активний» (поточний пункт меню) — не чіпаємо.
    grp_alive: dict = {}
    for sig, rec in seen.items():
        r = tested.get(sig)
        if rec["kind"] == "click" and rec.get("grp") and not rec.get("active") and r:
            grp_alive[rec["grp"]] = grp_alive.get(rec["grp"], False) or bool(r.get("effect"))

    items = []
    for sig, rec in seen.items():
        fid = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:12]
        if rec["kind"] == "link":
            if exists.get(rec["url"], True):
                continue
            why = f"веде на {rec['url'][len(base):] or '/'} — такої сторінки на сайті немає (сервер покаже головну або 404)"
            kind = "dead_link"
        else:
            r = tested.get(sig)
            if not r or r.get("effect"):
                continue
            if rec.get("active") and grp_alive.get(rec.get("grp"), True):
                continue
            why = "клік нічого не змінює: ні DOM, ні скролу, ні переходу"
            if r.get("err"):
                why += f" · JS-помилка: {r['err']}"
            kind = "dead_button"
        items.append({"fid": fid, "kind": kind, "sev": "error", "label": rec["label"],
                      "tag": rec["tag"], "href": rec["href"], "why": why,
                      "pages": sorted(rec["pages"], key=lambda u: (u != "/", u)),
                      "views": rec["views"], "chain": rec["chain"],
                      "preview": (tested.get(sig) or {}).get("preview", "")})
    items.sort(key=lambda i: (i["kind"], i["pages"][0] if i["pages"] else "", i["label"]))
    summary = {"branch": branch, "url": base, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
               "pages": pages, "pages_skipped": max(0, len(all_pages) - len(pages)),
               "tested": stats["tested"], "ok": stats["ok"], "links": stats["links"],
               "dead": len(items),
               "page_errors": res["errors"], "items": items}
    result_path(branch).write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    return summary


def _brief(s: dict) -> dict:
    return {**{k: s.get(k) for k in ("branch", "ts", "tested", "ok", "links", "dead")},
            "pages": len(s.get("pages") or []), "page_errors": len(s.get("page_errors") or [])}


def run_many(branches: list[str], workers: int | None = None) -> list[dict]:
    n = max(1, min(workers or vr.branch_workers(), len(branches) or 1))
    out, lock = [], threading.Lock()

    def one(br: str):
        try:
            item = _brief(run(br))
        except Exception as e:
            item = {"branch": br, "error": str(e)[:300]}
        with lock:
            out.append(item)

    with projects.Pool(max_workers=n) as ex:
        list(ex.map(one, branches))
    order = {b: i for i, b in enumerate(branches)}
    return sorted(out, key=lambda x: order.get(x["branch"], 0))


def load(branch: str) -> dict | None:
    p = result_path(branch)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:
        return None


def delete(branch: str) -> bool:
    p = result_path(branch)
    if p.exists():
        p.unlink()
        return True
    return False


def list_results() -> list[dict]:
    if not root().exists():
        return []
    out = []
    for p in root().glob("*.json"):
        try:
            out.append(_brief(json.loads(p.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return sorted(out, key=lambda x: x["branch"])


# ---------------------------------------------------------------- видалення з джерела
_ATTR_RX = re.compile(r"""([^\s=/>"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>"']+)))?""")
_VOID = {"input", "img", "br", "hr"}
_WS = re.compile(r"\s+")


def _attrs(s: str) -> dict:
    out = {}
    for m in _ATTR_RX.finditer(s):
        v = next((g for g in (m.group(2), m.group(3), m.group(4)) if g is not None), "")
        out[m.group(1).lower()] = html.unescape(v)
    return out


def _norm(s: str) -> str:
    return _WS.sub(" ", html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " ")).strip().lower()


_STATE_RX = re.compile(r"(^|[-_])(active|current|selected|show|open|opened)$"
                       r"|^(aos-init|aos-animate|animated|focus|hover|in|collapsed|current-menu-item)$")


def _same(desc: dict, a: dict) -> bool:
    """Тег джерела = елемент DOM. id/href/type/aria-label/role: є в одного —
    мусить бути і в іншого, і рівний (без цього кнопки-точки БЕЗ aria-label
    сусіднього слайдера матчились описом «Ir para depoimento 1»)."""
    for k, dk in (("id", "id"), ("href", "href"), ("type", "type"),
                  ("aria-label", "aria"), ("role", "role")):
        dv = desc.get(dk) or None
        sv = a.get(k) if k in a else None
        if (dv is None) != (sv is None) or (dv is not None and dv != sv):
            return False
    src = {c for c in (a.get("class") or "").split() if not _STATE_RX.search(c)}
    dom = set(desc.get("cls") or [])
    # класи джерела ⊆ класів DOM (скрипти класи ДОДАЮТЬ, не забирають); але
    # елемент з класами в DOM і без жодного в джерелі — інший елемент
    return src <= dom and (bool(src) or not dom)


def _spans(view: str, desc: dict):
    """(start, end) входжень елемента в DOM-виді джерела."""
    tag = desc["tag"]
    open_rx = re.compile(r"<%s\b((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>" % re.escape(tag), re.I)
    tag_rx = re.compile(r"<(/?)%s\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*?(/?)>" % re.escape(tag), re.I)
    want = (desc.get("text") or "").lower()
    for m in open_rx.finditer(view):
        if not _same(desc, _attrs(m.group(1))):
            continue
        if tag in _VOID or m.group(0).endswith("/>"):
            yield m.start(), m.end()
            continue
        depth, end, inner_end = 1, -1, -1
        for t in tag_rx.finditer(view, m.end()):
            if t.group(1):
                depth -= 1
            elif not t.group(2):
                depth += 1
            if depth == 0:
                end, inner_end = t.end(), t.start()
                break
        if end < 0 or _norm(view[m.end():inner_end]) != want:
            continue
        yield m.start(), end


def _specific(desc: dict) -> bool:
    return bool(desc.get("id") or desc.get("cls") or desc.get("href") or desc.get("aria") or desc.get("text"))


def _cut_line(text: str, s: int, e: int) -> tuple:
    ls = text.rfind("\n", 0, s) + 1
    le = text.find("\n", e)
    le = len(text) if le < 0 else le
    if not text[ls:s].strip() and not text[e:le].strip():
        return ls, min(len(text), le + 1)
    return s, e


def _src_files(branch: str) -> dict:
    base = snapshot_dir(branch)
    out = {}
    for p in base.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in vr.SRC_EXT:
            continue
        rel = p.relative_to(base).as_posix()
        if rel.startswith(("_meta/", "node_modules/", "dist/", "vendor/", ".git/")) or rel.endswith(".view.html"):
            continue
        try:
            out[rel] = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    return out


# ------------------------------------------------- не лише видалити: куди вести
# ortun-sqioha / maefur-kabo / taenof-kicoku (26.10): «мертві» — це пункти
# меню з href="#" (їх двійники у підвалі ведуть на справжні сторінки),
# підписи мега-меню <a> без href і пошта без mailto:. Видалення тут калічить
# навігацію; спершу — повернути ціль, видалення лишається для решти.
_A_RX = re.compile(r"""<a\b((?:[^>"']|"[^"]*"|'[^']*')*)>(.*?)</a>""", re.I | re.S)
_TITLE_RX = re.compile(r"<title[^>]*>(.*?)</title>|<h1[^>]*>(.*?)</h1>", re.I | re.S)
_DEAD_HREF_RX = re.compile(r"^\s*(?:#.*|javascript:.*|)\s*$", re.I)
_PROTO_RX = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.I)
_EMAIL_RX = re.compile(r"^[A-Za-z0-9._%+-]+@(?:\{\{DOMAIN\}\}|[A-Za-z0-9.-]+\.[A-Za-z]{2,})$")
_PAGE_EXT = (".html", ".htm", ".php")


def _real_href(h: str | None) -> bool:
    return bool(h) and not _DEAD_HREF_RX.match(h) and not _PROTO_RX.match(h)


def _abs_path(page: str, href: str) -> str:
    """Шлях цілі в межах сайту (posix), «company/index.html» → той самий файл."""
    import posixpath
    h = href.split("#", 1)[0].split("?", 1)[0]
    base = posixpath.dirname(page)
    p = posixpath.normpath(h.lstrip("/") if h.startswith("/") else posixpath.join(base, h))
    return "" if p.startswith("..") else p.lstrip("./")


def _rel_href(page: str, target: str) -> str:
    import posixpath
    rel = posixpath.relpath(target, posixpath.dirname(page) or ".")
    return rel


def _page_title(text: str) -> list:
    out = []
    for m in _TITLE_RX.finditer(text[:6000]):
        raw = m.group(1) or m.group(2) or ""
        for part in re.split(r"\s*[｜|]\s*|\s[—–·-]\s", _norm(raw)):
            if part:
                out.append(part)
    return out


_HREF_RX = re.compile(r"""\bhref\s*=\s*(["'])(.*?)\1""", re.I)


def _twins(text: str, want: str) -> list:
    """href-и <a> з тим самим видимим текстом, що ведуть на щось справжнє."""
    out = []
    for m in _A_RX.finditer(text):
        if _norm(m.group(2)) != want:
            continue
        hm = _HREF_RX.search(m.group(1))
        if hm and _real_href(hm.group(2)):
            out.append(hm.group(2))
    return out


def _retarget(label: str, page: str, files: dict) -> str | None:
    """href для мертвого <a>LABEL</a> на сторінці page: двійник з тим самим
    текстом у цьому ж файлі → двійник деінде на сайті (ціль існує) →
    сторінка, чий <title>/<h1> і є цим підписом. None — цілі немає."""
    want = _norm(label)
    if not want or len(want) < 2:
        return None
    same = set(_twins(files[page], want))
    if len(same) == 1:
        return next(iter(same))
    targets = set()
    for p, t in files.items():
        if not p.lower().endswith(_PAGE_EXT):
            continue
        for h in _twins(t, want):
            ap = _abs_path(p, h)
            for cand in (ap, ap.rstrip("/") + "/index.html"):
                if cand in files:
                    targets.add(cand)
                    break
    if len(targets) == 1:
        return _rel_href(page, next(iter(targets)))
    by_title = {p for p, t in files.items() if p.lower().endswith(_PAGE_EXT) and p != page
                and want in _page_title(t)}
    if len(by_title) == 1:
        return _rel_href(page, next(iter(by_title)))
    return None


def _set_href(open_tag: str, href: str) -> str:
    if re.search(r"""\bhref\s*=""", open_tag, re.I):
        return re.sub(r"""\bhref\s*=\s*(["'])(.*?)\1""", lambda m: f'href={m.group(1)}{href}{m.group(1)}', open_tag, count=1, flags=re.I)
    return re.sub(r"^(<a\b)", r'\1 href="%s"' % href, open_tag, count=1, flags=re.I)


# «Головна» різними мовами корпусу → корінь сайту (href="./", як у всіх
# справних вайтах), навіть коли двійника з лінком нема (лого — картинка)
_HOME_WORDS = {"accueil", "home", "homepage", "start", "startseite", "início", "inicio",
               "principal", "početna", "naslovnica", "ホーム", "トップ", "トップページ", "top"}
# підпис-дія: висить без цілі — безглуздий, видаляється; підпис-зміст
# (назва тканини, ім'я, заголовок новини) лишається текстом
_CTA_RX = re.compile(r"^(?:t[ée]l[ée]charger|lire|voir|d[ée]couvrir|demander|s'inscrire|se renseigner|s'informer|nous [ée]crire|prendre rendez|en savoir"
                     r"|download|read|see|view|learn more|book|sign up|subscribe|contact us"
                     r"|baixar|ler|ver|saiba|solicitar|agendar|descargar|leer|más|scarica|leggi|scopri|prenota"
                     r"|herunterladen|lesen|mehr|jetzt|anfragen|preuzmi|saznaj|pročitaj"
                     r"|もっと見る|詳しく|詳細|予約|問合せ|問い合わせ|お申し込み|ダウンロード|一覧を見る|すべて見る|.*を見る$|.*する$)", re.I)
_SOCIAL_RX = re.compile(r"^(?:facebook|instagram|twitter|x|linkedin|youtube|tiktok|pinterest|whatsapp|telegram|line)\b", re.I)
# «нагору» без скролу і голий старий домен («www.trehu-cotfaup.ch») — ні
# зміст, ні ціль: текстом лишати нема чого
_NOISE_RX = re.compile(r"^(?:www\.[\w.-]+\.[a-z]{2,}|[\w-]+\.(?:ch|jp|de|fr|it|com|net|org|hr|br)"
                       r"|ページの先頭へ|トップへ戻る|先頭へ|back to top|retour en haut|nach oben|voltar ao topo|torna su|na vrh)$", re.I)
_NAV_CLS_RX = re.compile(r"nav|menu|navbar|breadcrumb|pagination|pager|tabs?$", re.I)


def _in_nav(chain: list) -> bool:
    for desc in chain:
        if any(_NAV_CLS_RX.search(c) for c in (desc.get("cls") or [])) or (desc.get("id") and _NAV_CLS_RX.search(desc["id"])):
            return True
    return False


def _strategy(it: dict, inner: dict, page: str, files: dict) -> tuple:
    """(how, href): mailto / retargeted / unwrapped / removed."""
    if inner.get("tag") != "a":
        return "removed", None
    label = (it.get("label") or "").strip()
    if _EMAIL_RX.match(label):
        return "mailto", "mailto:" + label
    if _norm(label) in _HOME_WORDS:
        depth = page.count("/")
        return "retargeted", ("../" * depth) if depth else "./"
    href = _retarget(label, page, files)
    if href:
        return "retargeted", href
    if (not label or label.startswith("[") or _SOCIAL_RX.match(label) or _NOISE_RX.match(label) or _CTA_RX.match(label)
            or _in_nav(it.get("chain") or [])):
        return "removed", None
    return "unwrapped", None


def compute_fixes(branch: str, fids: list[str] | None = None) -> dict:
    """{"edits": {path: (old, new)}, "applied": [{fid, txt, files, how, …}], "skipped": [{txt, why}]}.

    Для <a> спершу шукається ціль (_strategy); видаляється лише те, що нема
    куди вести. Ціль може різнитись по сторінках (відносний шлях), тому
    рішення — на кожен файл окремо."""
    s = load(branch)
    if not s:
        raise ValueError("прогону кнопок ще не було")
    items = [i for i in s.get("items") or [] if fids is None or i["fid"] in fids]
    files = _src_files(branch)
    work = dict(files)
    views: dict = {}                            # DOM-вид файлу, доки файл не змінено

    def view_of(path: str) -> str:
        if path not in views:
            views[path] = vr._dom_view(work[path])
        return views[path]

    def find(desc: dict, inner: dict) -> dict:
        hits = {}
        needle = (desc.get("href") or desc.get("id") or (desc.get("cls") or [""])[0]
                  or desc.get("aria") or "")
        for path, text in work.items():
            if ("<" + desc["tag"]) not in text.lower() or (needle and html.escape(needle, quote=False) not in text and needle not in text):
                continue
            view = view_of(path)
            sp = []
            for st, en in _spans(view, desc):
                # обгортка рахується, лише якщо всередині справді наш елемент
                if desc is not inner and not any(True for _ in _spans(view[st:en], inner)):
                    continue
                sp.append((st, en))
            # вкладені входження (обгортка в обгортці) — лише зовнішнє
            outer = []
            for st, en in sorted(sp):
                if outer and st < outer[-1][1]:
                    continue
                outer.append((st, en))
            if outer:
                hits[path] = outer
        return hits

    applied, skipped = [], []
    for it in items:
        chain = it.get("chain") or []
        inner = chain[-1] if chain else None
        if not inner or not _specific(inner):
            skipped.append({"txt": it["label"], "why": "елемент без id/класу/href/тексту — надто загальний, щоб шукати в джерелі"})
            continue
        done = False
        # 1) сам елемент: ціль / mailto / розгортання — без обгорток
        if inner.get("tag") == "a":
            hits = find(inner, inner)
            hows = {}
            for path, sp in hits.items():
                how, href = _strategy(it, inner, path, files)
                if how == "removed":
                    continue
                text = work[path]
                for st, en in sorted(sp, reverse=True):
                    seg = text[st:en]
                    om = re.match(r"<a\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", seg, re.I)
                    if not om:
                        continue
                    if how == "unwrapped":
                        body = seg[om.end():]
                        body = body[:body.lower().rfind("</a>")] if "</a>" in body.lower() else body
                        text = text[:st] + body + text[en:]
                    else:
                        text = text[:st] + _set_href(om.group(0), href) + seg[om.end():] + text[en:]
                work[path] = text
                views.pop(path, None)
                hows[path] = how
            if hows:
                how = sorted(set(hows.values()))[0] if len(set(hows.values())) == 1 else "retargeted"
                applied.append({"fid": it["fid"], "txt": it["label"], "files": sorted(hows), "how": how,
                                "removed": ""})
                done = True
                rest = [p for p in hits if p not in hows]
                if not rest:
                    continue
                # на решті сторінок цілі нема — там видалення (нижче)
        # 2) видалення — від найширшої обгортки до самого елемента
        for desc in chain:
            hits = find(desc, inner)
            if not hits:
                continue
            for path, sp in hits.items():
                text = work[path]
                for st, en in sorted(sp, reverse=True):
                    a, b = _cut_line(text, st, en)
                    text = text[:a] + text[b:]
                work[path] = text
                views.pop(path, None)
            applied.append({"fid": it["fid"], "txt": it["label"], "files": sorted(hits), "how": "removed",
                            "removed": desc["tag"] + (("." + ".".join(desc["cls"][:2])) if desc.get("cls") else "")})
            done = True
            break
        if not done:
            skipped.append({"txt": it["label"], "why": "не знайдено в джерелі (елемент створює скрипт або розмітка інша)"})
    edits = {p: (files[p], t) for p, t in work.items() if t != files[p]}
    return {"edits": edits, "applied": applied, "skipped": skipped}


def forget(branch: str, fids: list[str]) -> None:
    """Прибрати з результату знахідки, які щойно видалено комітом."""
    s = load(branch)
    if not s:
        return
    s["items"] = [i for i in s.get("items") or [] if i["fid"] not in set(fids)]
    s["dead"] = len(s["items"])
    result_path(branch).write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
