"""Візуальні перевірки проти локального деплою вітки.

run(branch) → піднімає деплой (як скріни/lighthouse), відкриває КОЖНУ
сторінку вітки (html/php з деплою, ліміт MAX_PAGES) в headless-Chrome у двох
в'юпортах і збирає візуальні баги через інжектнутий JS: контраст тексту,
горизонтальний виліт, обрізаний текст, порожні блоки, биті/спотворені
картинки. run_many(branches) сканує кілька віток ОДНОЧАСНО.

Що дає рендер, чого не дає статичний аналіз коду:
* контраст рахується на РЕАЛЬНО відрендереному дереві: успадковані фони,
  Tailwind-класи, НАПІВПРОЗОРІ шари (rgba-оверлеї композитяться між собою),
  прозорість самого тексту (rgba-колір × opacity предків);
* якщо під текстом css-картинка/градієнт або <img>/<video>/<canvas> —
  фон беремо з пікселів скріна (медіана без пікселів шрифту);
* text-shadow / -webkit-text-stroke, що реально відділяють текст від фону,
  знижують знахідку до warn — щоб не фолсити на банерному тексті з обводкою.

Три речі, від яких залежить, чи звіт читабельний (усі виміряні на реальних
вітках, не вгадані):
* МІРЯЄМО ТЕКСТ, а не бокс елемента: block-span на всю ширину контейнера
  давав рект 1164×32, де сам текст займає ~8%, тож кроп прев'ю виходив
  смугою фону, а «фон під текстом» брався з сусідніх блоків;
* ОДИН БАГ — ОДИН РЯДОК: ключ склейки це пара кольорів, а не селектор.
  Футерний лінк ×6 на ×17 сторінках і `.mono` у 20 селекторах — це одна
  правка; усі входження лишаються в anchors, тож фікс іде в кожне;
* ПРЕВ'Ю ЛИШЕ ЯКЩО ВИДНО РІЗНИЦЮ: заміна #1a73e8 → #0e67dc (12/255 на
  канал) давала дві однакові картинки. Кольори показані свотчами — краще
  без картинки, ніж з нечитною.

Текст, якого зараз не видно (згорнутий accordion, оверлей, off-canvas), НЕ
викидається: баг справжній і проявиться, коли блок розгорнуть, — але
позначається і лишається без прев'ю.

Швидкість (17 сторінок × 2 в'юпорти, заміряно): 133с → 12с. Дало це не
розпаралелення саме по собі, а прибрані простої: замість sleep(1.8) на
сторінку — очікування шрифтів/картинок/кадру; повний PNG сторінки
знімається ЛИШЕ якщо потрібні пікселі або кроп (і декодується один раз, а
не на кожну знахідку); прев'ю — один скрін «після» на сторінку замість двох
на знахідку. Паралелізм: VISUAL_TABS табів на вітку (кожен — окреме вікно,
інакше Page.captureScreenshot на фоновому табі не відповідає) і
VISUAL_WORKERS віток разом (3 вітки: 38с → 20с).
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path

import deployer
import projects
from runner import snapshot_dir

# (ширина, висота, мобільна емуляція) — ті самі, що для скрінів
VIEWPORTS = {"desktop": (1366, 900, False), "mobile": (425, 800, True)}

# скільки РІЗНИХ багів (після склейки дублів) отримують пару «до/після»
MAX_PREVIEWS = 24

# скільки сторінок вітки сканувати за прогін (кожна — 2 в'юпорти з навігацією)
MAX_PAGES = 20

# скільки РІЗНИХ форм (за підписом: action+method+поля) проганяти на вітку —
# зазвичай це index + contact, решта сторінок повторює ту саму форму
MAX_FORM_TESTS = 3
# Скільки кроків форми проходимо, поки не дійдемо до справжньої відправки.
# Двокрокові форми у цих шаблонах — норма (крок 1: інтерес, крок 2: контакти);
# 4 — запас, після якого це вже не форма, а майстер, і тест чесно каже про це.
MAX_FORM_STEPS = 4

# Дані, якими заповнюється форма. Значення беруться з .env (FORM_TEST_*) або
# приходять у запиті — щоб можна було підставити свої, під локаль вайта.
FORM_TEST_DEFAULTS = {
    "name": "Ana Test",
    "lastname": "Silva",
    "email": "qa.lead@example.com",
    "phone": "+52 55 1234 5678",
    "company": "QA Lab",
    "city": "Test City",
    "message": "Mensagem de teste automatico (qa_lab). Ignore.",
}


def form_test_data(override: dict | None = None) -> dict:
    d = dict(FORM_TEST_DEFAULTS)
    for k in d:
        env = os.getenv("FORM_TEST_" + k.upper(), "").strip()
        if env:
            d[k] = env
    for k, v in (override or {}).items():
        if k in d and str(v).strip():
            d[k] = str(v).strip()
    # запасний варіант для полів з маскою на кшталт pattern="[0-9]{10}"
    d["phone_digits"] = re.sub(r"\D", "", d["phone"]) or "5512345678"
    return d


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        return default


def tabs_per_branch() -> int:
    """Скільки табів одного Chrome розбирають черги (в'юпорт × сторінка).
    3 — заміряний оптимум: 6 сторінок за 5.9с проти 8.6с в один таб; на 6
    табах уже 9.4с (рендер-потоки б'ються за CPU)."""
    return _env_int("VISUAL_TABS", 3)


def branch_workers() -> int:
    """Скільки віток скануються одночасно (кожна — свій php-деплой і Chrome)."""
    return _env_int("VISUAL_WORKERS", 3)


# ---------------------------------------------------------------- профілі прогону
# Набір «що ганяємо і з якими даними» під різні задачі: швидка перевірка
# форми перед здачею, повний аудит, суворий WCAG. Лежать біля результатів,
# тож переживають рестарт і спільні для всіх вкладок.
DEFAULT_PROFILES = [
    {"name": "Форма (швидко)", "tests": ["form"], "threshold": 3.0,
     "workers": None, "form_data": {}, "builtin": True},
    {"name": "Текст + форма", "tests": ["text", "form"], "threshold": 3.0,
     "workers": None, "form_data": {}, "builtin": True},
    {"name": "Текст, WCAG AA", "tests": ["text"], "threshold": None,
     "workers": None, "form_data": {}, "builtin": True},
]


def profiles_path() -> Path:
    return projects.state_dir() / "visual_profiles.json"


def load_profiles() -> list[dict]:
    p = profiles_path()
    if p.exists():
        try:
            saved = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(saved, list) and saved:
                return saved
        except Exception:
            pass
    return [dict(x) for x in DEFAULT_PROFILES]


def save_profile(prof: dict) -> list[dict]:
    name = (prof.get("name") or "").strip()
    if not name:
        raise ValueError("профіль без назви")
    clean = {
        "name": name[:40],
        "tests": [t for t in (prof.get("tests") or TESTS) if t in TESTS] or list(TESTS),
        "threshold": prof.get("threshold"),
        "workers": prof.get("workers"),
        "form_data": {k: str(v)[:200] for k, v in (prof.get("form_data") or {}).items()
                      if k in FORM_TEST_DEFAULTS and str(v).strip()},
    }
    out = [x for x in load_profiles() if x.get("name") != name]
    out.append(clean)
    _write_profiles(out)
    return out


def delete_profile(name: str) -> list[dict]:
    out = [x for x in load_profiles() if x.get("name") != name]
    _write_profiles(out or [dict(x) for x in DEFAULT_PROFILES])
    return load_profiles()


def _write_profiles(items: list[dict]):
    p = profiles_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def vis_root() -> Path:
    return projects.state_dir() / "visual"


def _stem(branch: str) -> str:
    return branch.replace("/", "__")


def summary_path(branch: str) -> Path:
    return vis_root() / f"{_stem(branch)}.json"


# ---------------------------------------------------------------- контраст
def _lum(c) -> float:
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    l1, l2 = _lum(a), _lum(b)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


def parse_rgb(s: str):
    """rgb()/rgba() з getComputedStyle або #rrggbb/#rgb."""
    s = (s or "").strip()
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            return None
        try:
            return [float(int(h[i:i + 2], 16)) for i in (0, 2, 4)]
        except ValueError:
            return None
    m = re.findall(r"[\d.]+", s)
    if len(m) < 3:
        return None
    return [float(m[0]), float(m[1]), float(m[2])]


def to_hex(c) -> str:
    return "#%02x%02x%02x" % tuple(int(round(x)) for x in c[:3])


def _hsl(c):
    r, g, b = (x / 255.0 for x in c[:3])
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h / 6, s, l


def _shift(a, b) -> float:
    """Наскільки заміна змінює сам колір, а не його світлість.

    Полагодити контраст можна тільки посунувши світлість — тому за неї майже
    не штрафуємо. А от зміна відтінку чи насиченості означає, що ми
    перефарбовуємо сайт, тож вона коштує дорого. Без цього «найближчий за
    RGB» спокійно міняв теплу теракоту на холодний сірий.
    """
    h1, s1, l1 = _hsl(a)
    h2, s2, l2 = _hsl(b)
    dh = abs(h1 - h2)
    dh = min(dh, 1 - dh)                       # відтінок замкнений у коло
    if s1 < 0.12 and s2 < 0.12:                # обидва майже сірі — відтінку нема
        dh = 0.0
    return dh * 3.0 + abs(s1 - s2) * 1.0 + abs(l1 - l2) * 0.15


def _blend(c, a: float, bg):
    """Ефективний колір напівпрозорого тексту поверх фону (alpha-композит)."""
    if a >= 0.999:
        return [float(x) for x in c[:3]]
    return [c[i] * a + bg[i] * (1 - a) for i in range(3)]


def pick_replacement(fg, bg, need: float, section_colors: list, page_colors: list,
                     alpha: float = 1.0):
    """Заміна кольору тексту — тільки з палітри самого сайту.

    Пріоритет: кольори тієї ж секції (щоб не ламати дизайн) → кольори
    сторінки → освітлення/затемнення оригіналу як останній варіант.
    Серед прохідних беремо той, що найменше змінює сам колір (див. _shift),
    а не найконтрастніший: мета — полагодити читабельність, а не
    перефарбувати сайт.

    alpha — прозорість, яку inline-фікс НЕ прибирає (opacity предків):
    кожен кандидат перевіряється вже прозорим, інакше фікс «проходив би»
    на папері і лишався нечитабельним у рендері.
    """
    def rgb_dist(c):
        return sum((c[i] - fg[i]) ** 2 for i in range(3)) ** 0.5

    def passes(c):
        return contrast(_blend(c, alpha, bg), bg) >= need

    # запасний варіант: тягнемо сам оригінал у бік від фону. Відтінок при
    # цьому зберігається точно — тому це краще за чужий колір із палітри,
    # якщо той надто далекий (буває, коли в секції просто нема потрібного
    # за світлістю кольору потрібного відтінку).
    dark_bg = _lum(bg) < 0.5
    shifted = None
    cur = list(fg)
    for _ in range(70):
        cur = [min(255, c + 4) if dark_bg else max(0, c - 4) for c in cur]
        if passes(cur):
            shifted = cur
            break

    MAX_SHIFT = 0.6                    # більше — це вже перефарбовування
    for pool, src in ((section_colors, "секція"), (page_colors, "сторінка")):
        ok = [c for c in pool if passes(c) and rgb_dist(c) > 12]
        if ok:
            best = min(ok, key=lambda c: _shift(fg, c))
            if _shift(fg, best) <= MAX_SHIFT or not shifted:
                return best, f"колір із палітри ({src})"
            break                      # палітра є, але вона змінила б відтінок

    if shifted:
        return shifted, "той самий колір, " + ("світліше" if dark_bg else "темніше")
    return None, ""


# ---------------------------------------------------------------- JS-зонд
PROBE_JS = r"""
(() => {
const VW = window.innerWidth, VH = window.innerHeight;
const out = [];

function path(el){
  const p = [];
  while (el && el.nodeType === 1 && p.length < 4) {
    let s = el.tagName.toLowerCase();
    if (el.id) { p.unshift(s + '#' + el.id); break; }
    const c = ((el.getAttribute && el.getAttribute('class')) || '')
              .trim().split(/\s+/).filter(Boolean)[0];
    if (c) s += '.' + c;
    p.unshift(s); el = el.parentElement;
  }
  return p.join(' > ');
}
const add = (kind, sev, el, msg, extra) => out.push(Object.assign(
  {kind, sev, msg, sel: path(el), tag: el.tagName.toLowerCase(),
   cls: ((el.getAttribute && el.getAttribute('class')) || '').slice(0,80),
   txt: (el.textContent||'').trim().slice(0,80)}, extra||{}));

const rgb = c => { const m = (c||'').match(/[\d.]+/g);
  return m ? [+m[0], +m[1], +m[2], m.length > 3 ? +m[3] : 1] : null; };

// напівпрозорі фони (rgba-оверлеї) КОМПОЗИТЯТЬСЯ, а не вважаються
// непрозорими: шари збираються вгору по дереву, поки не трапиться
// непрозорий; фон-картинка на будь-якому рівні → вимір по пікселях скріна
function compose(layers){              // згори вниз; останній — непрозора база
  let c = layers[layers.length-1].slice(0,3);
  for (let i = layers.length-2; i >= 0; i--) {
    const a = layers[i][3];
    c = [layers[i][0]*a + c[0]*(1-a),
         layers[i][1]*a + c[1]*(1-a),
         layers[i][2]*a + c[2]*(1-a)];
  }
  return c;
}
function bgOf(el){
  let e = el; const layers = [];
  while (e && e.nodeType === 1) {
    const cs = getComputedStyle(e);
    if (cs.backgroundImage && cs.backgroundImage !== 'none') return {img: true, el: e};
    const c = rgb(cs.backgroundColor);
    if (c && c[3] > 0.05) {
      layers.push(c);
      if (c[3] >= 0.95) return {c: compose(layers), el: e, layers: layers.length};
    }
    e = e.parentElement;
  }
  layers.push([255,255,255,1]);
  return {c: compose(layers), el: document.body, layers: layers.length};
}
// сумарна прозорість: opacity самого елемента і всіх предків перемножуються
function opacityOf(el){
  let a = 1, e = el;
  while (e && e.nodeType === 1) { a *= (+getComputedStyle(e).opacity || 1); e = e.parentElement; }
  return a;
}
function visible(el){
  const cs = getComputedStyle(el);
  if (cs.display==='none' || cs.visibility==='hidden' || +cs.opacity === 0) return false;
  const r = el.getBoundingClientRect();
  return r.width > 1 && r.height > 1;
}
function ownText(el){
  let t = ''; for (const n of el.childNodes) if (n.nodeType === 3) t += n.nodeValue;
  return t.trim();
}
// найближчий смисловий предок — щоб брати кольори «своєї» секції
function sectionOf(el){
  let e = el;
  while (e && e !== document.body) {
    if (/^(section|footer|header|nav|main|article|aside)$/i.test(e.tagName)) return e;
    e = e.parentElement;
  }
  return document.body;
}
function palette(root){
  const seen = new Map();
  root.querySelectorAll('*').forEach(el => {
    if (!visible(el)) return;
    const cs = getComputedStyle(el);
    [cs.color, cs.backgroundColor].forEach(c => {
      const p = rgb(c);
      if (p && p[3] > 0.9) { const k = p.slice(0,3).join(',');
        seen.set(k, (seen.get(k)||0) + 1); }
    });
  });
  return [...seen.entries()].sort((a,b) => b[1]-a[1]).slice(0,24)
         .map(([k]) => k.split(',').map(Number));
}

// Текст у ЗГОРНУТОМУ блоці (accordion/FAQ: max-height:0 + overflow:hidden)
// у розкладці існує і має розмір, але його не видно. Це не причина
// викидати знахідку — розгорнуть, і баг проявиться, — але прев'ю з такого
// місця було б порожнім прямокутником.
function clippedBy(el){
  const r = el.getBoundingClientRect();
  let e = el.parentElement;
  while (e && e.nodeType === 1) {
    const cs = getComputedStyle(e);
    if (/hidden|clip/.test(cs.overflow + cs.overflowY + cs.overflowX)) {
      const b = e.getBoundingClientRect();
      if (b.height < 2 || b.width < 2) return true;
      if (r.bottom <= b.top + 1 || r.top >= b.bottom - 1 ||
          r.right <= b.left + 1 || r.left >= b.right - 1) return true;
    }
    e = e.parentElement;
  }
  return false;
}

// Площа НАМАЛЬОВАНОГО тексту, а не бокс елемента. block-span на всю ширину
// контейнера дає рект 1164×32, де сам текст займає ~8% — кроп прев'ю виходив
// смугою фону («порожні місця» в UI), а фон під текстом мірявся по пікселях
// сусідніх блоків. Range.getClientRects() дає line-box'и текстових вузлів.
const _rng = document.createRange();
function textBoxes(el){
  const bs = [];
  for (const n of el.childNodes) {
    if (n.nodeType !== 3 || !n.nodeValue.trim()) continue;
    _rng.selectNodeContents(n);
    const rl = _rng.getClientRects();
    for (let i = 0; i < rl.length; i++)
      if (rl[i].width >= 1 && rl[i].height >= 1) bs.push(rl[i]);
  }
  return bs;
}
function unionOf(bs){
  let l = 1e9, t = 1e9, r = -1e9, b = -1e9;
  for (const x of bs) { l = Math.min(l, x.left); t = Math.min(t, x.top);
                        r = Math.max(r, x.right); b = Math.max(b, x.bottom); }
  return (r > l && b > t) ? {left: l, top: t, width: r - l, height: b - t} : null;
}

// Рект для КРОПА беремо заново перед скріном: хіт-тест прокручує сторінку,
// а скрол може довантажити лейзі-контент і зсунути верстку. Режим ('t' —
// по тексту, 'b' — по боксу) фіксується на момент знахідки.
window.__visMode = [];
window.__visRect = (el, mode) => {
  let tr = mode === 'b' ? null : unionOf(textBoxes(el));
  if (!tr) {
    const r = el.getBoundingClientRect();
    tr = {left: r.left, top: r.top, width: r.width, height: r.height};
  }
  return [Math.round(tr.left + scrollX), Math.round(tr.top + scrollY),
          Math.round(tr.width), Math.round(tr.height)];
};

const pagePal = palette(document.body);
const secPal = new Map();
const allEls = [...document.querySelectorAll('body *')];

// <img>/<video>/<canvas> ПІД текстом: css-фони bgOf бачить, а такі теги —
// ні (hero з <img class="absolute">, відео-фон). Критерій — перекриття
// ПЛОЩІ тексту, а не влучання центру: текст біля краю картинки раніше
// мірявся по css-фону і давав хибний контраст.
const mediaRects = [];
document.querySelectorAll('img,video,canvas').forEach(m => {
  if (!visible(m)) return;
  const r = m.getBoundingClientRect();
  if (r.width >= 48 && r.height >= 48)
    mediaRects.push({l: r.left, t: r.top, r: r.right, b: r.bottom, el: m});
});
function overMedia(el, rc){
  const A = rc.width * rc.height;
  if (A <= 0) return false;
  for (const m of mediaRects) {
    if (m.el.contains(el) || el.contains(m.el)) continue;
    const w = Math.min(rc.left + rc.width, m.r) - Math.max(rc.left, m.l);
    const h = Math.min(rc.top + rc.height, m.b) - Math.max(rc.top, m.t);
    if (w > 0 && h > 0 && (w * h) / A >= 0.5) return true;
  }
  return false;
}

// Індекс однакових відкриваючих тегів: у Tailwind один набір класів
// трапляється десятки разів, тому якір правки — номер серед близнюків +
// їхня кількість (python звірить її з кількістю збігів у файлі).
// cloneNode(false) серіалізує ЛИШЕ тег: раніше outerHTML кожного елемента
// будувався для кожного унікального тега — O(n²) по всьому піддереву.
const _openTag = new WeakMap();
function openTagOf(el){
  let t = _openTag.get(el);
  if (t === undefined) {
    const h = el.cloneNode(false).outerHTML;
    t = h.slice(0, h.indexOf('>') + 1);
    _openTag.set(el, t);
  }
  return t;
}
const twins = new Map();
allEls.forEach(el => {
  const t = openTagOf(el);
  let l = twins.get(t);
  if (!l) twins.set(t, l = []);
  l.push(el);
});

// Елементи для прев'ю тримаємо посиланнями, а не атрибутом: будь-яка
// domiшка в DOM змінила б outerHTML і зламала звірку якорів вище.
window.__visEls = [];
window.__visHit = [];

function record(el, fgStr, boxes, opts){
  opts = opts || {};
  const cs = getComputedStyle(el);
  const fg = rgb(fgStr);
  if (!fg || fg[3] < 0.1) return;
  // градієнтний текст (background-clip:text): сам color прозорий і до
  // контрасту не має стосунку — раніше давало хибні знахідки
  if (!opts.pseudo) {
    const tf = rgb(cs.webkitTextFillColor || '');
    if (tf && tf[3] < 0.1) return;
  }
  const opA = opacityOf(el);
  if (opA < 0.05) return;
  let tr = unionOf(boxes);
  if (!tr) {
    const r = el.getBoundingClientRect();
    tr = {left: r.left, top: r.top, width: r.width, height: r.height};
  }
  if (tr.width < 3 || tr.height < 3) return;
  const bg = bgOf(el);
  const size = parseFloat(cs.fontSize) || 16, fw = parseInt(cs.fontWeight) || 400;
  const large = size >= 24 || (size >= 18.66 && fw >= 700);
  const sec = sectionOf(el);
  if (!secPal.has(sec)) secPal.set(sec, palette(sec));
  let tag = '', ix = -1, tot = 0;
  if (!opts.nofix) {
    tag = openTagOf(el);
    const l = twins.get(tag) || [];
    ix = l.indexOf(el); tot = l.length;
  }
  const vid = window.__visEls.push(el) - 1;
  const first = boxes.length ? boxes[0] : tr;
  window.__visMode[vid] = boxes.length ? 't' : 'b';
  // точка для хіт-тесту: всередині ПЕРШОГО рядка тексту (page-координати)
  window.__visHit[vid] = [
    Math.round(first.left + Math.min(first.width / 2, 40) + scrollX),
    Math.round(first.top + first.height / 2 + scrollY)];
  const common = {
    vid, fg: fgStr, large, openTag: tag, tagIx: ix, tagTotal: tot,
    clip: clippedBy(el) ? 1 : 0,
    fgA: fg[3], opA, nofix: !!opts.nofix, part: opts.part || '',
    shadow: cs.textShadow && cs.textShadow !== 'none' ? cs.textShadow.slice(0,120) : '',
    strokeW: parseFloat(cs.webkitTextStrokeWidth) || 0,
    strokeC: cs.webkitTextStrokeColor || '',
    font: Math.round(size) + 'px/' + fw,
    secPal: secPal.get(sec), pagePal,
    // абсолютні координати сторінки: скрін знімається цілком
    // (captureBeyondViewport), тож crop працює і нижче першого екрана
    rect: [Math.round(tr.left + scrollX), Math.round(tr.top + scrollY),
           Math.round(tr.width), Math.round(tr.height)],
  };
  if (opts.txt) common.txt = opts.txt;
  // фон-картинка АБО media-тег під текстом → міряємо по пікселях у python
  if (bg.img || overMedia(el, tr)) {
    common.bgsrc = bg.img ? getComputedStyle(bg.el).backgroundImage.slice(0,80)
                          : '<img>/<video> під текстом';
    add('contrast_px', 'pending', el, '', common);
    return;
  }
  common.bg = getComputedStyle(bg.el).backgroundColor;
  common.bgArr = bg.c.slice(0,3);
  common.layers = bg.layers || 1;
  common.bgsel = path(bg.el);
  add('contrast_css', 'pending', el, '', common);
}

// ---------- 1. контраст: власний текст елементів
const SVG_NS = 'http://www.w3.org/2000/svg';
allEls.forEach(el => {
  if (ownText(el).length < 3 || !visible(el)) return;
  const isSvg = el.namespaceURI === SVG_NS;
  if (isSvg && el.tagName.toLowerCase() !== 'text') return;   // <title>/<desc> не малюються
  const cs = getComputedStyle(el);
  // svg-текст фарбується fill, а не color — inline-фікс color його не візьме
  record(el, isSvg ? cs.fill : cs.color, textBoxes(el), {nofix: isSvg});
});

// ---------- 1b. placeholder-и: колір ::placeholder не успадковується від input
document.querySelectorAll('input,textarea').forEach(el => {
  const ph = (el.getAttribute('placeholder') || '').trim();
  if (ph.length < 3 || !visible(el)) return;
  record(el, getComputedStyle(el, '::placeholder').color, [],
         {nofix: true, pseudo: true, part: '::placeholder', txt: ph.slice(0,80)});
});

// ---------- 1c. текст із ::before/::after (генерований контент)
allEls.forEach(el => {
  if (!visible(el)) return;
  for (const pe of ['::before', '::after']) {
    const cs = getComputedStyle(el, pe);
    const m = (cs.content || '').trim().match(/^"(.*)"$/);
    if (!m || m[1].replace(/\s/g, '').length < 3) continue;
    record(el, cs.color, [], {nofix: true, pseudo: true, part: pe,
                              txt: m[1].slice(0,80)});
  }
});

// ---------- 2. горизонтальний виліт
const de = document.documentElement;
if (de.scrollWidth > VW + 2) {
  const c = [];
  allEls.forEach(el => {
    if (!visible(el) || getComputedStyle(el).position === 'fixed') return;
    const r = el.getBoundingClientRect();
    if (r.right > VW + 2 && r.width > 8)
      c.push({el, over: Math.round(r.right - VW), w: Math.round(r.width)});
  });
  add('page_overflow', 'error', document.body,
      `сторінка ширша за екран: ${de.scrollWidth}px проти ${VW}px — горизонтальний скрол`,
      {scrollW: de.scrollWidth, vw: VW});
  c.filter(x => !c.some(o => o !== x && x.el.contains(o.el))).slice(0,6)
   .forEach(x => add('overflow_el', 'error', x.el,
      `вилітає за правий край на ${x.over}px (ширина ${x.w}px)`, {over: x.over}));
}

// ---------- 3. обрізаний текст
allEls.forEach(el => {
  if (!visible(el) || !el.textContent.trim()) return;
  const cs = getComputedStyle(el);
  if (!/hidden|clip/.test(cs.overflowY + cs.overflow)) return;
  if (el.scrollHeight > el.clientHeight + 3 && el.clientHeight > 10)
    add('text_clipped', 'warn', el,
        `текст обрізано контейнером: ${el.scrollHeight}px вмісту в ${el.clientHeight}px`,
        {hidden_px: el.scrollHeight - el.clientHeight});
});

// ---------- 4. порожні блоки
const BLOCK = new Set(['section','div','article','aside','header','footer','main','figure']);
allEls.forEach(el => {
  if (!BLOCK.has(el.tagName.toLowerCase()) || !visible(el)) return;
  const r = el.getBoundingClientRect();
  if (r.height < 60 || r.width < 120 || el.textContent.trim()) return;
  if (el.querySelector('img,svg,video,iframe,canvas,input,button,picture')) return;
  const cs = getComputedStyle(el);
  if (cs.backgroundImage !== 'none') return;
  const bc = rgb(cs.backgroundColor);
  if (bc && bc[3] > 0.1) return;
  if (cs.borderTopWidth !== '0px' || cs.borderLeftWidth !== '0px') return;
  add('empty_block', 'warn', el,
      `порожній блок ${Math.round(r.width)}×${Math.round(r.height)}px — нічого не рендерить`,
      {w: Math.round(r.width), h: Math.round(r.height)});
});

// ---------- 5. картинки
document.querySelectorAll('img').forEach(el => {
  if (!el.complete) return;
  if (el.naturalWidth === 0)
    add('img_broken', 'error', el, 'картинка не завантажилась',
        {src: (el.currentSrc||el.src||'').slice(-80)});
  else if (visible(el)) {
    // object-fit: cover/contain НЕ спотворює — воно кадрує або вписує.
    // Без цієї перевірки кожен hero-банер (`w-full object-cover` з
    // фіксованою висотою) світився «пропорція спотворена», хоч виглядає
    // правильно: спотворює лише fill, тобто дефолт.
    const fit = getComputedStyle(el).objectFit || 'fill';
    if (fit !== 'fill') return;
    const r = el.getBoundingClientRect();
    const na = el.naturalWidth/el.naturalHeight, ra = r.width/r.height;
    if (na > 0 && ra > 0 && (ra/na > 1.6 || na/ra > 1.6))
      add('img_aspect', 'warn', el,
          `пропорція спотворена: показ ${ra.toFixed(2)} проти оригіналу ${na.toFixed(2)}`,
          {src: (el.currentSrc||el.src||'').slice(-70)});
  }
});

// ---------- 6. хедер накриває текст першої секції
// Тут перекриття fixed-шаром — САМЕ баг, на відміну від хіт-тесту нижче
// (там кукі-банер чи плавашка накривають випадковий текст на випадковій
// позиції скролу). Зонд працює при scrollY===0 — у стані, який користувач
// бачить першим. Тому критерій геометричний, а не за назвою класу: хедер
// у потоці (sticky) у цьому стані перетину не дає взагалі, а fixed без
// компенсаційного padding у першій секції — дає.
(() => {
  if (window.scrollY !== 0) return;
  const hdr = [...document.querySelectorAll('header,[role="banner"]')]
    .find(h => visible(h) && /fixed|absolute/.test(getComputedStyle(h).position));
  if (!hdr) return;
  const hr = hdr.getBoundingClientRect();
  if (hr.top > 2 || hr.height < 8 || hr.width < VW * 0.5) return;   // не верхня панель

  // Накопичена непрозорість шарів від намальованого елемента до хедера.
  // Прозорий хедер поверх hero-фото — нормальний прийом (меню лягає на
  // картинку, текст крізь нього видно), тож це не дефект. backdrop-filter
  // рахуємо за непрозорий: розмиття робить текст під ним нечитним.
  function coverAlpha(node){
    let a = 0;
    for (let e = node; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage !== 'none' || (cs.backdropFilter || 'none') !== 'none' ||
          (cs.webkitBackdropFilter || 'none') !== 'none') return 1;
      const c = rgb(cs.backgroundColor);
      if (c) a += c[3] * (1 - a);
      if (e === hdr) break;
    }
    return a;
  }

  const root = document.querySelector('main') || document.body;
  const sec = [...root.children].find(el =>
    el.nodeType === 1 && !hdr.contains(el) && !el.contains(hdr) && visible(el) &&
    el.getBoundingClientRect().bottom > hr.bottom + 4);
  if (!sec) return;
  const sr = sec.getBoundingClientRect();
  if (sr.top > hr.bottom - 4) return;              // компенсація вже є

  let worst = 0, sample = '';
  for (const el of sec.querySelectorAll('*')) {
    if (!ownText(el) || !visible(el)) continue;
    for (const b of textBoxes(el)) {
      const ov = Math.min(b.bottom, hr.bottom) - Math.max(b.top, hr.top);
      if (ov < 4 || b.left >= hr.right || b.right <= hr.left) continue;
      const x = (Math.max(b.left, hr.left) + Math.min(b.right, hr.right)) / 2;
      const y = (Math.max(b.top, hr.top) + Math.min(b.bottom, hr.bottom)) / 2;
      if (x < 0 || y < 0 || x > VW - 1 || y > VH - 1) continue;
      const hit = document.elementFromPoint(x, y);
      if (!hit || !hdr.contains(hit) || coverAlpha(hit) < 0.5) continue;
      if (ov > worst) { worst = Math.round(ov); sample = ownText(el).slice(0, 80); }
    }
  }
  if (!worst) return;

  const padTop = Math.round(hr.bottom - sr.top);
  const tag = openTagOf(sec);
  const tw = twins.get(tag) || [];
  add('hero_overlap', 'error', sec,
      `хедер (${getComputedStyle(hdr).position}, ${Math.round(hr.height)}px) накриває ` +
      `текст першої секції на ${worst}px — секції бракує padding-top ${padTop}px`,
      {overlap: worst, headerH: Math.round(hr.height), txt: sample,
       openTag: tag, tagIx: tw.indexOf(sec), tagTotal: tw.length,
       fix: {padTop, to: `padding-top:${padTop}px`}});
})();

return out;
})()
"""

# Хіт-тест: чи видно текст НАСПРАВДІ, чи його накриває інший елемент.
# Оверлей/модалка/декоративний шар поверх тексту давали «знахідку» з
# контрастом, якого користувач не бачить, і плоский кроп у прев'ю.
# elementFromPoint працює лише по в'юпорту, тож точки прокручуємо у вид.
HITTEST_JS = r"""
window.__visHitTest = (vids) => {
  const res = {};
  const maxY = Math.max(0, document.documentElement.scrollHeight - innerHeight);
  const list = vids.map(v => ({v, el: window.__visEls[v], p: window.__visHit[v]}))
                   .filter(x => x.el && x.p);
  list.sort((a, b) => a.p[1] - b.p[1]);
  for (const it of list) {
    let vx = it.p[0] - scrollX, vy = it.p[1] - scrollY;
    if (vy < 0 || vy > innerHeight - 2) {
      scrollTo(0, Math.min(maxY, Math.max(0, it.p[1] - innerHeight * 0.4)));
      vx = it.p[0] - scrollX; vy = it.p[1] - scrollY;
    }
    if (vx < 0 || vx > innerWidth - 1 || vy < 0 || vy > innerHeight - 1) {
      res[it.v] = 2;                       // поза екраном (off-canvas меню)
      continue;
    }
    const hit = document.elementFromPoint(vx, vy);
    // fixed/sticky-шар (кукі-банер, плавашка) — артефакт прогону, а не баг
    // верстки: він накриває випадковий текст на кожній позиції скролу
    let artifact = false;
    for (let h = hit; h && h !== document.body; h = h.parentElement) {
      const pos = getComputedStyle(h).position;
      if (pos === 'fixed' || pos === 'sticky') { artifact = true; break; }
    }
    res[it.v] = (artifact || !hit || it.el.contains(hit) || hit.contains(it.el)) ? 0 : 1;
  }
  scrollTo(0, 0);
  return res;
};
window.__visRects = () => (window.__visEls || []).map(
  (e, i) => e ? window.__visRect(e, window.__visMode[i]) : null);
window.__visApply = (m) => {
  let n = 0;
  for (const k in m) {
    const e = window.__visEls[k];
    if (!e) continue;
    e.__visOld = e.style.getPropertyValue('color');
    e.__visPri = e.style.getPropertyPriority('color');
    e.style.setProperty('color', m[k], 'important');
    n++;
  }
  return n;
};
window.__visRevert = () => {
  (window.__visEls || []).forEach(e => {
    if (!e || e.__visOld === undefined) return;
    if (e.__visOld) e.style.setProperty('color', e.__visOld, e.__visPri);
    else e.style.removeProperty('color');
    delete e.__visOld; delete e.__visPri;
  });
  return 1;
};
1
"""


# ---------------------------------------------------------------- CDP
class _Page:
    """Тонка обгортка над CDP-сесією: те саме, що робить deployer для скрінів,
    але з Runtime.evaluate і покадровими crop-ами."""

    def __init__(self, ws, cmd):
        self.ws, self.cmd = ws, cmd

    def eval(self, expr, await_promise: bool = False):
        r = self.cmd("Runtime.evaluate", expression=expr,
                     returnByValue=True, awaitPromise=await_promise)
        if "exceptionDetails" in r:
            raise RuntimeError(str(r["exceptionDetails"])[:300])
        return r["result"].get("value")

    def shot(self, clip=None):
        p = {"format": "png", "captureBeyondViewport": True}
        if clip:
            p["clip"] = {**clip, "scale": 1}
        return base64.b64decode(self.cmd("Page.captureScreenshot", **p)["data"])


# ---------------------------------------------------------------- форми
# Заповнення й сабміт справжньої форми в браузері. Статичний аналіз бачить
# лише розмітку; чи ЖИВИЙ ланцюжок «ввід → сабміт → сторінка подяки», видно
# тільки якщо натиснути кнопку. Тут же ловляться: мертвий сабміт, поле, що
# відхиляє дані, конверсійний блок, який не спрацював (лишились на тій самій
# сторінці з ?name=…), і return page, що віддає 404.
FORM_JS = r"""
window.__visFormVis = (el) => {
  const cs = getComputedStyle(el);
  if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return false;
  const r = el.getBoundingClientRect();
  return r.width > 2 && r.height > 2;
};
window.__visForms = () => {
  // honeypot проти ботів: заповнити його = провалити тест навмисне
  const HONEY = /^(website|url|honey|honeypot|hp|_gotcha|bot|fax)$/i;
  const labelOf = el => {
    let t = '';
    if (el.id) {
      const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (l) t = l.textContent;
    }
    if (!t && el.closest('label')) t = el.closest('label').textContent;
    return (t || '').trim().slice(0, 60);
  };
  const path = el => {
    const p = [];
    while (el && el.nodeType === 1 && p.length < 3) {
      let s = el.tagName.toLowerCase();
      if (el.id) { p.unshift(s + '#' + el.id); break; }
      const c = ((el.getAttribute('class') || '').trim().split(/\s+/)[0]);
      if (c) s += '.' + c;
      p.unshift(s); el = el.parentElement;
    }
    return p.join(' > ');
  };
  return [...document.forms].map((f, ix) => {
    const fields = [...f.elements]
      .filter(e => /^(input|select|textarea)$/i.test(e.tagName))
      .map(e => ({
        name: e.name || e.id || '', tag: e.tagName.toLowerCase(),
        type: (e.type || '').toLowerCase(),
        required: !!e.required,
        pattern: e.getAttribute('pattern') || '',
        placeholder: e.getAttribute('placeholder') || '',
        label: labelOf(e),
        visible: window.__visFormVis(e),
        honey: HONEY.test(e.name || '') || e.tabIndex === -1
               || !!e.closest('[aria-hidden="true"]'),
      }));
    const sub = f.querySelector(
      'button[type=submit],input[type=submit],input[type=image],button:not([type])');
    return {
      ix, sel: path(f), action: f.getAttribute('action') || '',
      method: (f.getAttribute('method') || 'get').toLowerCase(),
      novalidate: f.hasAttribute('novalidate'),
      visible: window.__visFormVis(f),
      submit: sub ? ((sub.textContent || sub.value || '').trim().slice(0, 40) || '(без тексту)') : null,
      fields,
    };
  });
};
window.__visFillForm = (ix, d) => {
  const f = document.forms[ix];
  if (!f) return {error: 'форма зникла зі сторінки'};
  // нативний сеттер + input/change: інакше слухачі фреймворків не бачать ввід
  const set = (el, v) => {
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement : HTMLInputElement;
    const desc = Object.getOwnPropertyDescriptor(proto.prototype, 'value');
    if (desc && desc.set) desc.set.call(el, v); else el.value = v;
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    el.dispatchEvent(new Event('blur', {bubbles: true}));
  };
  const HONEY = /^(website|url|honey|honeypot|hp|_gotcha|bot|fax)$/i;
  const pick = (el, hay) => {
    const t = (el.type || '').toLowerCase();
    if (t === 'email' || /mail|correo/.test(hay)) return d.email;
    if (t === 'tel' || /phone|tel|fone|telefono|celular|whats|movil/.test(hay)) return d.phone;
    if (el.tagName === 'TEXTAREA' || /message|mensa|comment|coment|duvida|texto|nachricht/.test(hay))
      return d.message;
    if (/last|sobrenome|apellido|surname|nachname/.test(hay)) return d.lastname;
    if (/name|nome|nombre/.test(hay)) return d.name;
    if (/company|empresa|organiza|firma/.test(hay)) return d.company;
    if (/city|cidade|ciudad|stadt/.test(hay)) return d.city;
    if (t === 'number') return '1';
    if (t === 'url') return 'https://example.com';
    if (t === 'date') return new Date().toISOString().slice(0, 10);
    return d.name;
  };
  const filled = [], skipped = [], invalid = [];
  for (const el of f.elements) {
    if (!/^(input|select|textarea)$/i.test(el.tagName)) continue;
    const nm = el.name || el.id || '(без name)';
    const t = (el.type || '').toLowerCase();
    if (t === 'hidden' || el.disabled || el.readOnly) { skipped.push(nm); continue; }
    if (HONEY.test(el.name || '') || el.tabIndex === -1
        || el.closest('[aria-hidden="true"]') || !window.__visFormVis(el)) {
      skipped.push(nm + ' (honeypot/прихований)');
      continue;
    }
    if (t === 'checkbox') { if (!el.checked) { el.click(); } filled.push(nm + '=✓'); continue; }
    if (t === 'radio') {
      const grp = [...f.elements].filter(x => x.name === el.name && x.type === 'radio');
      if (!grp.some(x => x.checked)) { el.click(); filled.push(nm + '=✓'); }
      continue;
    }
    if (el.tagName === 'SELECT') {
      const opt = [...el.options].find(o => o.value && !o.disabled);
      if (opt) { el.value = opt.value; el.dispatchEvent(new Event('change', {bubbles: true}));
                 filled.push(nm + '=' + opt.value.slice(0, 20)); }
      continue;
    }
    const hay = (nm + ' ' + (el.id || '') + ' ' + (el.placeholder || '')).toLowerCase()
                + ' ' + (el.labels && el.labels[0] ? el.labels[0].textContent.toLowerCase() : '');
    let v = pick(el, hay);
    set(el, v);
    // поле з маскою може відхилити «людський» формат — пробуємо запасні
    if (!el.checkValidity()) {
      for (const alt of [d.phone_digits, (el.placeholder || '').trim()]) {
        if (!alt) continue;
        set(el, alt);
        if (el.checkValidity()) { v = alt; break; }
      }
    }
    if (!el.checkValidity()) {
      invalid.push({name: nm, value: String(v).slice(0, 24),
                    pattern: el.getAttribute('pattern') || '',
                    why: (el.validationMessage || '').slice(0, 80)});
    }
    filled.push(nm + '=' + String(v).slice(0, 24));
  }
  return {filled, skipped, invalid, formValid: f.checkValidity()};
};
window.__visSubmitForm = (ix) => {
  const f = document.forms[ix];
  if (!f) return 'gone';
  const sub = f.querySelector(
    'button[type=submit],input[type=submit],input[type=image],button:not([type])');
  // клік, а не requestSubmit: сайти вішають обробник саме на кнопку
  if (sub) { sub.click(); return 'click'; }
  if (f.requestSubmit) { f.requestSubmit(); return 'requestSubmit'; }
  f.submit();
  return 'submit';
};
// Відбиток ВИДИМИХ полів форми. Багатокрокова форма на «сабміт» не
// відправляється, а показує наступний крок — набір видимих полів при цьому
// міняється. Без цієї перевірки крок зараховувався за ajax-відповідь
// («сторінка змінилась») і тест давав зелений статус, жодного разу не
// дійшовши до справжньої відправки.
window.__visFormStep = (ix) => {
  const f = document.forms[ix];
  if (!f) return '';
  return [...f.elements]
    .filter(e => /^(input|select|textarea)$/i.test(e.tagName)
                 && (e.type || '').toLowerCase() !== 'hidden'
                 && window.__visFormVis(e))
    .map(e => e.name || e.id || e.type).join(',');
};
// Зліпок сторінки до/після сабміту: ajax-форма нічого не навігує, а показує
// блок «дякуємо» на місці. Без цього такий сценарій виглядав би як «форма
// не реагує» — тобто хибна помилка.
window.__visFormSnap = (before) => {
  const txt = (document.body.innerText || '');
  const RX = /thank|obrigad|gracias|danke|merci|success|sucesso|enviad|recebemos|entraremos/i;
  const snap = {len: txt.length, forms: document.forms.length, thanks: RX.test(txt)};
  if (!before) return snap;
  return Object.assign(snap, {
    changed: Math.abs(snap.len - before.len) > 40 || snap.forms !== before.forms,
    thanksAppeared: snap.thanks && !before.thanks,
  });
};
1
"""

# Сторінку треба ДОВЕСТИ ДО СПОКОЮ перед виміром: reveal-секції (opacity:0 до
# першого скролу), веб-шрифти (свап шрифту рухає весь текст) і лейзі-картинки
# (довантажились → все нижче з'їхало). Раніше замість цього стояв
# sleep(1.8) — і повільна сторінка мірялась на льоту.
SETTLE_JS = r"""
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  if (!document.getElementById('__vis_instant')) {
    const st = document.createElement('style');
    st.id = '__vis_instant';
    st.textContent = '*{transition-duration:1ms !important;transition-delay:0s !important;' +
                     'animation-duration:1ms !important;animation-delay:0s !important;' +
                     'scroll-behavior:auto !important}';
    document.head.appendChild(st);
  }
  const frame = () => new Promise(r => requestAnimationFrame(() => r()));
  const H = () => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  // крок = повний екран, пауза = один кадр: IntersectionObserver спрацьовує
  // покадрово, тож фіксовані 30мс на крок були чистим простоєм
  const step = Math.max(400, innerHeight);
  for (let y = 0; y <= H(); y += step) { scrollTo(0, y); await frame(); }
  scrollTo(0, H()); await frame(); scrollTo(0, 0);
  try { await Promise.race([document.fonts.ready, sleep(2000)]); } catch (e) {}
  const pend = [...document.images].filter(i => !i.complete);
  if (pend.length) await Promise.race([
    Promise.all(pend.map(i => new Promise(r => {
      i.addEventListener('load', r, {once: true});
      i.addEventListener('error', r, {once: true});
    }))),
    sleep(2500),
  ]);
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  await sleep(80);
  return [H(), innerWidth, innerHeight];
})()
"""

# Прогін ФОРМИ не міряє пікселі, тож чекати на віддалені картинки й шрифти
# нема сенсу: на першій сторінці вітки це коштувало ~7 с холодного
# завантаження pexels/picsum. Лишається тільки розкриття lazy-секцій —
# форма буває нижче першого екрана.
SETTLE_FORM_JS = r"""
(async () => {
  const frame = () => new Promise(r => requestAnimationFrame(() => r()));
  if (!document.getElementById('__vis_instant')) {
    const st = document.createElement('style');
    st.id = '__vis_instant';
    st.textContent = '*{transition-duration:1ms !important;animation-duration:1ms !important;' +
                     'scroll-behavior:auto !important}';
    document.head.appendChild(st);
  }
  const H = () => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  for (let y = 0; y <= H(); y += Math.max(400, innerHeight)) { scrollTo(0, y); await frame(); }
  scrollTo(0, 0); await frame();
  return 1;
})()
"""


def _open(browser: str, base_url: str, viewports: dict, pages: list, work,
          tabs: int | None = None, settle_js: str = SETTLE_JS,
          load_event: str = "Page.loadEventFired", load_timeout: float = 25) -> dict:
    """Один Chrome, N табів паралельно: черга завдань (в'юпорт × сторінка)
    розбирається воркерами, кожен зі своєю CDP-сесією і своїм Emulation-станом.
    Раніше 34 завдання (2 в'юпорти × 17 сторінок) йшли строго по черзі в одному
    табі. Помилка окремої сторінки не валить прогін — вона в page_errors."""
    jobs = [(kind, wh, page) for kind, wh in viewports.items() for page in pages]
    n_tabs = max(1, min(tabs or tabs_per_branch(), len(jobs)))

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--no-first-run", "--no-default-browser-check",
         # без цього фонові таби дроселяться і setTimeout у SETTLE_JS повзе
         "--disable-background-timer-throttling",
         "--disable-renderer-backgrounding",
         "--disable-backgrounding-occluded-windows"]
        + deployer.browser_extra_args()
        + [f"--remote-debugging-port={port}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import requests
        from websockets.sync.client import connect as ws_connect

        ver = None
        for _ in range(60):
            try:
                ver = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2).json()
                break
            except Exception:
                time.sleep(0.2)
        if not ver or not ver.get("webSocketDebuggerUrl"):
            raise RuntimeError("chrome не відкрив debug-порт")

        out: dict[str, list] = {k: [] for k in viewports}
        errors: list[dict] = []
        lock = threading.Lock()
        queue = list(jobs)

        def session(ws):
            mid = [0]

            def cmd(method, **params):
                mid[0] += 1
                ws.send(json.dumps({"id": mid[0], "method": method, "params": params}))
                while True:
                    msg = json.loads(ws.recv(timeout=120))
                    if msg.get("id") == mid[0]:
                        if "error" in msg:
                            raise RuntimeError(f"{method}: {msg['error']}")
                        return msg.get("result", {})
            return cmd

        def tab_url() -> str:
            # newWindow: без окремого вікна фонові таби в headless вважаються
            # закритими іншим вікном — Page.captureScreenshot на них просто
            # не відповідає (перевірено: команда висить до таймауту 120с).
            with ws_connect(ver["webSocketDebuggerUrl"], max_size=8 * 1024 * 1024) as b:
                cmd = session(b)
                tid = cmd("Target.createTarget", url="about:blank",
                          newWindow=True)["targetId"]
            return f"ws://127.0.0.1:{port}/devtools/page/{tid}"

        def worker(url: str):
            with ws_connect(url, max_size=64 * 1024 * 1024) as ws:
                cmd = session(ws)

                def wait_load(t=25):
                    end = time.time() + t
                    while time.time() < end:
                        try:
                            m = json.loads(ws.recv(timeout=max(0.1, end - time.time())))
                        except Exception:
                            return
                        if m.get("method") == load_event:
                            return

                cmd("Page.enable")
                p = _Page(ws, cmd)
                cur = None
                while True:
                    with lock:
                        if not queue:
                            return
                        kind, (w, h, mobile), page_path = queue.pop(0)
                    try:
                        if cur != kind:
                            cmd("Emulation.setDeviceMetricsOverride",
                                width=w, height=h, deviceScaleFactor=1, mobile=mobile)
                            cur = kind
                        cmd("Page.navigate", url=base_url.rstrip("/") + page_path)
                        wait_load(load_timeout)
                        p.eval(settle_js, await_promise=True)
                        found = work(p, kind, page_path)
                    except Exception as e:
                        with lock:
                            errors.append({"page": page_path, "view": kind,
                                           "error": str(e)[:200]})
                        continue
                    with lock:
                        out[kind].extend(found)

        urls = [tab_url() for _ in range(n_tabs)]
        threads = [threading.Thread(target=worker, args=(u,), daemon=True) for u in urls]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        order = {pg: n for n, pg in enumerate(pages)}
        for k in out:
            out[k].sort(key=lambda i: order.get(i.get("page"), 0))
        return {"views": out, "errors": errors}
    finally:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass


class _Shot:
    """Скрін сторінки, декодований ОДИН раз. Раніше кожен crop відкривав
    повний PNG заново — на сторінці 1366×13733 це десятки мегабайт на кожну
    знахідку."""

    def __init__(self, png: bytes):
        import numpy as np
        from PIL import Image
        self.a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.uint8)
        self.h, self.w = self.a.shape[:2]

    def cut(self, rect, pad: int = 0):
        x, y, w, h = rect
        x0, y0 = max(0, int(x) - pad), max(0, int(y) - pad)
        x1 = min(self.w, int(x) + int(w) + pad)
        y1 = min(self.h, int(y) + int(h) + pad)
        if x1 - x0 < 3 or y1 - y0 < 3:
            return None
        return self.a[y0:y1, x0:x1]

    def b64(self, rect, pad: int = 6) -> str:
        c = self.cut(rect, pad)
        if c is None:
            return ""
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(c).save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()


def _bg_from_pixels(shot: "_Shot", rect, fg):
    """Справжній фон під текстом: беремо прямокутник ТЕКСТУ зі скріна і
    викидаємо пікселі самого шрифту — медіана решти і є фон."""
    import numpy as np

    c = shot.cut(rect)
    if c is None:
        return None
    crop = c.reshape(-1, 3).astype(np.int16)
    d = np.abs(crop - np.array(fg[:3], dtype=np.int16)).sum(axis=1)
    bgpx = crop[d > 90]
    if len(bgpx) < 20:
        bgpx = crop
    return [float(v) for v in np.median(bgpx, axis=0)]


# наскільки має змінитись канал, щоб різницю було видно оком у кропі
_PREVIEW_DELTA = 40


def _preview_verdict(before, after) -> str:
    """`ok` | `subtle` | `noop` — чи варто показувати пару «до/після».

    Порожні кропи в UI були двох різних сортів, і обидва треба не ховати, а
    ПОЯСНИТИ:
    * `subtle` — заміна на суміжний відтінок (#c2ac85 → #dac49d, 24/255 на
      канал): картинки однакові. Рахуємо МАКСИМАЛЬНУ зміну каналу, а не
      середню по кропу — середня залежить від того, скільки місця займає
      текст, тож щільний дрібний шрифт «проходив» навіть при 12/255.
    * `noop` — перефарбування не змінило НІ ОДНОГО пікселя: фікс, найпевніше,
      не подіє (колір малює не цей елемент). Це вже привід не тиснути
      «виправити» навмання, тож мовчати про такий випадок не можна."""
    if before is None or after is None or before.shape != after.shape:
        return "noop"
    import numpy as np
    diff = np.abs(before.astype(np.int16) - after.astype(np.int16))
    changed = int((diff.sum(axis=2) > 24).sum())
    if changed < max(20, int(0.01 * before.shape[0] * before.shape[1])):
        return "noop"
    return "ok" if int(diff.max()) >= _PREVIEW_DELTA else "subtle"


def _preview_shows_change(before, after) -> bool:
    return _preview_verdict(before, after) == "ok"


# ---------------------------------------------------------------- прогін форми
# дефолт $returnPage у шаблоні; статичний двійник — checks/return_page.py,
# який перевіряє лише існування файлу, а не те, чи туди реально доводить
_RETURN_PAGE_RX = re.compile(
    r"""WHITE_FORM_RETURN_PAGE['"]\s*\]\s*\?\?\s*['"]([^'"]+)['"]""", re.I)
# «подяка» і за URL, і за текстом сторінки: у fluency вона зветься
# demo-connect/, зате в заголовку «We'll be in touch!»
_THANKS_RX = re.compile(
    r"thank|thanks|obrigad|gracias|danke|merci|grazie|success|sucesso|exito|"
    r"spasibo|dyakuyu|confirm|in touch|received|recebemos|entraremos", re.I)


def expected_return_page(branch: str) -> str:
    """Куди має привести сабміт: дефолт з index.php деплою ('' — невідомо)."""
    doc = _deploy_docroot(branch)
    for name in ("index.php", "index.html"):
        f = doc / name
        if not f.exists():
            continue
        m = _RETURN_PAGE_RX.search(f.read_text(encoding="utf-8", errors="replace"))
        if m:
            page = m.group(1).strip()
            return page if page.lower().endswith(".html") else page + ".html"
    return ""


def _form_signature(form: dict) -> tuple:
    """Та сама форма на 17 сторінках — один прогін."""
    return (form.get("action", ""), form.get("method", ""),
            tuple(f["name"] for f in form.get("fields", []) if f.get("name")))


_SEARCH_NAME_RX = re.compile(r"^(q|s|query|search|keyword|kw)$", re.I)


def _pick_form(forms: list[dict]) -> dict | None:
    """Контактна форма сторінки.

    Не «та, де ≥2 поля»: у вітці fluency головна лід-форма — це ОДНЕ поле
    email + кнопка, і за кількістю полів вона програвала фільтру, тобто
    прогін звітував «форми не знайдено» на сторінці, де форма є. Тому
    критерій змістовний: пошук і логін пропускаємо явно, а лід-форму
    впізнаємо за email/tel-полем навіть якщо воно одне."""
    best, best_n = None, 0
    for f in forms:
        if not f.get("visible"):
            continue
        live = [x for x in f["fields"]
                if x["visible"] and not x["honey"] and x["type"] != "hidden"]
        if not live:
            continue
        types = {x["type"] for x in live}
        if "password" in types:
            continue                                  # логін/реєстрація
        if any(x["type"] == "search" or _SEARCH_NAME_RX.match(x["name"] or "")
               for x in live):
            continue                                  # пошук по сайту
        lead = types & {"email", "tel"}
        if len(live) < 2 and not lead:
            continue
        # лід-форма з email важливіша за довгий фільтр із трьох селектів
        score = len(live) + (10 if lead else 0)
        if score > best_n:
            best, best_n = f, score
    return best


def _wait_nav(p: "_Page", from_url: str, timeout: float = 8.0) -> str:
    """Чекає зміну URL і ще трохи — на другий крок ланцюжка.

    Шаблон робить саме два кроки: сабміт веде на ту саму сторінку з ?name=…,
    php віддає конверсійні пікселі й через setTimeout(500) кидає на
    $returnPage. Якщо повернути перший URL, тест звітував би про провал там,
    де все працює."""
    end = time.time() + timeout
    url, changed_at = from_url, None
    while time.time() < end:
        time.sleep(0.2)
        try:
            now = p.eval("location.href")
        except Exception:
            continue                       # контекст знищено навігацією
        if not now:
            continue
        if now != url:
            url, changed_at = now, time.time()
        elif changed_at and time.time() - changed_at > 1.1:
            break                          # URL устоявся
    return url if url != from_url else ""


def _page_status(p: "_Page") -> int:
    """Реальний http-статус сторінки, на якій опинились (php -S віддає 404
    звичайною сторінкою, візуально від успіху не відрізниш)."""
    try:
        return int(p.eval("fetch(location.href, {method:'GET'}).then(r => r.status)",
                          await_promise=True) or 0)
    except Exception:
        return 0


def _merge_fill(acc: dict, got: dict) -> dict:
    """Склеює результати заповнення кількох кроків в один звіт."""
    if not acc:
        return dict(got)
    out = dict(acc)
    for k in ("filled", "skipped", "invalid"):
        out[k] = list(acc.get(k) or []) + list(got.get(k) or [])
    out["formValid"] = got.get("formValid")
    return out


def _form_findings(page: str, form: dict, fill: dict, landed: str,
                   base_url: str, expect: str, status: int,
                   empty_passed: bool | None, ajax: dict | None = None,
                   landed_text: str = "", steps: int = 0) -> list[dict]:
    """Вердикт по одному прогону форми."""
    sel = form.get("sel") or "form"
    out = []
    add = lambda kind, sev, msg, **kw: out.append(         # noqa: E731
        {"kind": kind, "sev": sev, "sel": sel, "page": page, "msg": msg,
         "form": {"action": form.get("action"), "method": form.get("method"),
                  "submit": form.get("submit"),
                  "filled": fill.get("filled", []),
                  "skipped": fill.get("skipped", []),
                  "landed": landed, "status": status}, **kw})

    if fill.get("invalid"):
        bad = ", ".join(
            f"{i['name']}={i['value']!r}" + (f" (pattern {i['pattern']})" if i["pattern"] else "")
            + (f" — {i['why']}" if i["why"] else "")
            for i in fill["invalid"][:3])
        add("form_input", "error",
            f"поле не приймає тестові дані: {bad} · заміни FORM_TEST_* у .env, "
            f"якщо формат локальний")
    if not form.get("submit"):
        add("form_flow", "error", "у формі немає кнопки submit — надіслати нічим")
        return out

    if empty_passed:
        add("form_input", "warn",
            "порожня форма проходить сабміт: обов'язкові поля не перевіряються "
            "(у ліди сипатиметься порожнеча)")

    filled = ", ".join(fill.get("filled", [])[:6])
    thru = f" (пройдено кроків: {steps + 1})" if steps else ""
    if not landed:
        # ajax-форма: переходу нема, але на місці з'явилось підтвердження.
        # Коли кроки перемикались, ajax сюди не приходить — зміна сторінки
        # там пояснюється саме кроком, а не відповіддю сервера.
        if ajax and (ajax.get("thanksAppeared") or ajax.get("changed")):
            add("form_flow", "info",
                f"форма відповідає без переходу (ajax): {filled} → "
                + ("на сторінці з'явилось підтвердження"
                   if ajax.get("thanksAppeared") else "сторінка змінилась"))
            return out
        if steps >= MAX_FORM_STEPS - 1:
            add("form_flow", "error",
                f"форма перемикає кроки і не відправляється: пройдено "
                f"{MAX_FORM_STEPS} кроків, сабміту так і не сталося "
                f"(заповнено: {filled})")
            return out
        add("form_flow", "error",
            f"сабміт не дає реакції: ні переходу, ні змін на сторінці за 8 с"
            f"{thru} (заповнено: {filled})")
        return out

    from urllib.parse import urlparse
    lp, bp = urlparse(landed), urlparse(base_url)
    if lp.netloc and lp.netloc != bp.netloc:
        add("form_flow", "warn", f"форма веде на чужий домен: {landed[:90]}")
        return out

    path = lp.path or "/"
    same_page = path.rstrip("/") == (page.rstrip("/") or "") and bool(lp.query)
    if same_page:
        add("form_flow", "error",
            f"залишились на тій самій сторінці з параметрами ({lp.query[:60]}…) — "
            f"конверсійний блок не спрацював і на сторінку подяки не перекинуло")
        return out
    if status and status != 200:
        add("form_flow", "error",
            f"сторінка після сабміту віддає {status}: {path}")
        return out

    # Сторінку подяки впізнаємо і за URL, і за ВМІСТОМ: у fluency вона зветься
    # demo-connect/ і за адресою невідрізнима від звичайної, хоча на ній
    # великим шрифтом «We'll be in touch!».
    hit_expect = expect and path.lower().endswith(expect.lower().lstrip("/"))
    if hit_expect or _THANKS_RX.search(path) or _THANKS_RX.search(landed_text or ""):
        add("form_flow", "info",
            f"форма працює{thru}: {filled} → {path} ({status or '200'})")
        return out
    add("form_flow", "warn",
        f"сабміт привів на {path}" + (f", а очікувалась {expect}" if expect else "")
        + f" ({status or '?'})")
    return out


def run_form_test(p: "_Page", page: str, base_url: str, expect: str,
                  data: dict) -> tuple[list[dict], tuple | None]:
    """Заповнює форму сторінки, тисне submit і йде за редіректами.

    Виконується ОСТАННІМ на сторінці: сабміт неминуче забирає таб на іншу
    адресу. Повертає (знахідки, підпис форми) — підпис, щоб не ганяти ту
    саму форму на кожній сторінці вітки."""
    p.eval(FORM_JS)
    forms = p.eval("window.__visForms()") or []
    form = _pick_form(forms)
    if not form:
        return [], None
    sig = _form_signature(form)
    page_url = p.eval("location.href")

    # 1) порожній сабміт: чи взагалі перевіряються обов'язкові поля
    empty_passed = None
    has_required = any(f["required"] and f["visible"] and not f["honey"]
                       for f in form["fields"])
    if has_required and form.get("submit"):
        p.eval(f"window.__visSubmitForm({form['ix']})")
        moved = _wait_nav(p, page_url, timeout=1.6)
        empty_passed = bool(moved)
        if moved:                                  # форма пропустила порожнє —
            p.cmd("Page.navigate", url=page_url)   # вертаємось і тестуємо далі
            time.sleep(1.0)
            p.eval(FORM_JS)
            forms = p.eval("window.__visForms()") or []
            form = _pick_form(forms) or form

    # 2) справжній прогін з даними. Форма може бути БАГАТОКРОКОВОЮ: «сабміт»
    # на проміжному кроці лише показує наступний, а не відправляє. Тоді
    # заповнюємо новий крок і тиснемо ще раз — інакше тест зараховував
    # перемикання кроку за ajax-відповідь і давав зелений статус, ні разу не
    # дійшовши до відправки.
    fill: dict = {}
    landed, steps = "", 0
    snap = p.eval("window.__visFormSnap()")
    for _ in range(MAX_FORM_STEPS):
        before = p.eval(f"window.__visFormStep({form['ix']})")
        got = p.eval(f"window.__visFillForm({form['ix']}, {json.dumps(data)})") or {}
        if got.get("error"):
            return ([], sig) if not fill else (
                _form_findings(page, form, fill, "", base_url, expect, 0,
                               empty_passed, None, "", steps), sig)
        fill = _merge_fill(fill, got)
        if not form.get("submit"):
            return _form_findings(page, form, fill, "", base_url, expect, 0,
                                  empty_passed, None, "", steps), sig
        p.eval(f"window.__visSubmitForm({form['ix']})")
        landed = _wait_nav(p, page_url)
        if landed:
            break
        after = p.eval(f"window.__visFormStep({form['ix']})")
        if not after or after == before:
            break                       # набір полів той самий — це не крок
        steps += 1                      # показався наступний крок, продовжуємо
    status = _page_status(p) if landed else 0
    # Текст сторінки, куди привело — по ньому впізнаємо подяку, коли адреса
    # про це не каже (demo-connect/ → «We'll be in touch!»). Читаємо innerText,
    # бо перший <h1> у Webflow-шаблоні буває порожнім плейсхолдером; і з
    # ретраєм, бо одразу після навігації document.body ще null.
    landed_text = ""
    if landed:
        for _ in range(10):
            try:
                landed_text = p.eval(
                    "document.body ? document.title + ' | ' + "
                    "(document.body.innerText||'').slice(0, 400) : ''") or ""
            except Exception:
                landed_text = ""
            if landed_text.strip(" |"):
                break
            time.sleep(0.2)
    # без переходу — форма могла відповісти на місці (ajax + блок «дякуємо»).
    # Але якщо ми перед цим перемикали кроки, зміна сторінки — це вони, а не
    # відповідь сервера: тоді ajax не рахуємо.
    ajax = None
    if not landed and not steps:
        try:
            ajax = p.eval(f"window.__visFormSnap({json.dumps(snap)})")
        except Exception:
            ajax = None
    return (_form_findings(page, form, fill, landed, base_url, expect, status,
                           empty_passed, ajax, landed_text, steps), sig)


# ---------------------------------------------------------------- склейка дублів
def _group_key(i: dict) -> tuple:
    """Один баг = один рядок.

    Для контрасту ключ — ПАРА КОЛЬОРІВ, а не селектор: `.mono` з кольором
    #7e8781 ламається у 20 різних місцях, але це один токен палітри і одна
    правка. Селектор у ключі давав 20 рядків з ідентичним «→ #354340».
    Фон у ключі точний: однаковий fg на іншому фоні вимагає іншої заміни,
    інакше r_after групи брехав би для частини входжень.

    Хедер накриває hero однаково на кожній сторінці вітки, але на різну
    кількість пікселів (заголовки різної довжини) — msg у ключі дав би 17
    рядків замість одного, тож для нього ключ лише по селектору секції."""
    if i.get("kind") == "contrast":
        return ("contrast", i.get("fg_hex"), i.get("bg"),
                i.get("need"), i.get("part") or "")
    if i.get("kind") == "hero_overlap":
        return ("hero_overlap", i.get("sel"))
    return (i.get("kind"), i.get("sel"), i.get("msg"))


def _anchors_of(i: dict) -> list[dict]:
    if i.get("nofix") or not i.get("openTag") or i.get("tagIx", -1) < 0:
        return []
    return [{"openTag": i["openTag"], "tagIx": i["tagIx"],
             "tagTotal": i.get("tagTotal", 0)}]


_SEV_RANK = {"error": 2, "warn": 1, "info": 0}


def _merge(items: list[dict]) -> list[dict]:
    """Однакові знахідки з різних місць — один рядок (див. `_group_key`).

    Крім лічильника `dups` рядок несе `by_page`: {сторінка: [тексти]}. Без
    цього склеєний рядок був приписаний ОДНІЙ сторінці (першій, де його
    побачили), а UI групує саме по ній - і на решті сторінок дефект ставав
    невидимим. Кейс `nwf-teuseune-mibuo-br-pt`: білий текст на білому тлі над
    і під сіткою фото є і на /avaliacao, і на /segmentos (4 входження), але у
    вкладці «Візуальні» /segmentos показувалась чистою.
    """
    out: list[dict] = []
    index: dict[tuple, dict] = {}
    for i in items:
        key = _group_key(i)
        g = index.get(key)
        page, txt = i.get("page") or "", (i.get("txt") or "").strip()
        if g is None:
            i["dups"] = 1
            i["pages"] = [page] if page else []
            i["anchors"] = _anchors_of(i)
            i["samples"] = [i["txt"]] if i.get("txt") else []
            i["sels"] = [i["sel"]] if i.get("sel") else []
            i["by_page"] = {page: [txt]} if page and txt else {}
            index[key] = i
            out.append(i)
            continue
        g["dups"] += 1
        if page and page not in g["pages"]:
            g["pages"].append(page)
        if page and txt:
            lst = g.setdefault("by_page", {}).setdefault(page, [])
            if txt not in lst and len(lst) < 5:
                lst.append(txt)
        for a in _anchors_of(i):
            if a not in g["anchors"]:
                g["anchors"].append(a)
        if txt and txt not in g["samples"] and len(g["samples"]) < 5:
            g["samples"].append(txt)
        if i.get("sel") and i["sel"] not in g["sels"] and len(g["sels"]) < 5:
            g["sels"].append(i["sel"])
        if not g.get("preview") and i.get("preview"):
            g["preview"] = i["preview"]
            g.pop("no_preview", None)     # картинка знайшлась — пояснення зайве
        if _SEV_RANK.get(i.get("sev"), 0) > _SEV_RANK.get(g.get("sev"), 0):
            g["sev"] = i["sev"]
        # у групі лишається НАЙГІРШЕ співвідношення — по ньому і сортують
        if (i.get("r") or 99) < (g.get("r") or 99):
            g["r"] = i["r"]
            g["msg"] = i["msg"]
    return out


TESTS = ("text", "form")
# сторінки, де форма буває, коли ганяємо ТІЛЬКИ форму (решту не вантажимо)
_FORM_PAGE_RX = re.compile(
    r"contact|contato|contacto|kontakt|feedback|quote|orcamento|presupuesto", re.I)


def run(branch: str, threshold: float | None = None,
        max_pages: int = MAX_PAGES, form_data: dict | None = None,
        tests: list[str] | tuple | set | None = None) -> dict:
    """threshold=None — стандарт WCAG (4.5 звичайний текст / 3 великий).
    Число — єдиний поріг для всього тексту.

    tests — які перевірки ганяти:
      'text' — контраст, виліт, обрізаний текст, порожні блоки, картинки
               (усі сторінки × desktop + mobile);
      'form' — заповнити контактну форму (дані: form_data або FORM_TEST_*
               з .env), натиснути submit і перевірити шлях до подяки.
    Тільки 'form' — це швидкий прогін: один в'юпорт і лише сторінки, де
    форма реально буває, без зонда і скрінів."""
    tests = {t for t in (tests or TESTS) if t in TESTS}
    if not tests:
        raise ValueError("нема жодної обраної перевірки (очікується text / form)")
    do_text, do_form = "text" in tests, "form" in tests

    vis_root().mkdir(parents=True, exist_ok=True)
    keep = deployer.is_running(branch)
    d = deployer.deploy(branch, wait=True)

    all_pages = _list_pages(branch)
    pages = all_pages[:max_pages]
    viewports = VIEWPORTS if do_text else {"desktop": VIEWPORTS["desktop"]}
    if not do_text:
        likely = [p for p in pages if p == "/" or _FORM_PAGE_RX.search(p)]
        pages = (likely or pages)[:MAX_FORM_TESTS + 1]
    seen_keys: set[tuple] = set()          # прев'ю — по одному на РІЗНИЙ баг
    budget = {k: MAX_PREVIEWS for k in VIEWPORTS}
    guard = threading.Lock()
    raw = {"total": 0, "hidden": 0, "flat": 0}
    fdata = form_test_data(form_data)
    expect = expected_return_page(branch) if do_form else ""
    seen_forms: set[tuple] = set()

    def work(p: _Page, kind: str, page: str):
        if not do_text:
            return _form_pass(p, kind, page)
        items = p.eval(PROBE_JS)
        con = [i for i in items if i["kind"] in ("contrast_css", "contrast_px")]
        p.eval(HITTEST_JS)
        covered = p.eval(f"window.__visHitTest({json.dumps([i['vid'] for i in con])})") or {}
        # рект — ЩОЙНО перед скріном (хіт-тест скролив сторінку), інакше кроп
        # ріжеться за старими координатами і показує сусідній блок
        fresh = p.eval("window.__visRects()") or []
        # Скрін — ЛИШЕ якщо реально потрібні пікселі (текст поверх картинки)
        # або кроп прев'ю. На сторінці без таких знахідок повний PNG
        # (1366×13733) не знімається і не декодується взагалі.
        cache: list = []

        def shot():
            if not cache:
                cache.append(_Shot(p.shot()))
            return cache[0]

        found, wanted = [], []

        for it in items:
            if it["kind"] not in ("contrast_css", "contrast_px"):
                it["page"] = page
                found.append(it)
                continue
            with guard:
                raw["total"] += 1
            vid = it["vid"]
            # Не видно ЗАРАЗ ≠ не баг: у згорнутому accordion/FAQ або під
            # оверлеєм текст лишається зламаним і проявиться, коли блок
            # розгорнуть. Тому знахідку ЛИШАЄМО, але прев'ю з такого місця
            # не робимо (був би порожній прямокутник) і не піднімаємо до error.
            hidden = ""
            if it.get("clip"):
                hidden = "у згорнутому/обрізаному блоці"
            v = covered.get(str(vid), covered.get(vid, 0))
            if v == 2:
                hidden = hidden or "за межами екрана (off-canvas)"
            elif v == 1:
                hidden = hidden or "накрито іншим елементом"
            if hidden:
                with guard:
                    raw["hidden"] += 1
            if vid < len(fresh) and fresh[vid]:
                it["rect"] = fresh[vid]
            fg = parse_rgb(it["fg"])
            if not fg:
                continue
            if it["kind"] == "contrast_px":
                bg = _bg_from_pixels(shot(), it["rect"], fg)
                if not bg:
                    continue
                origin = it.get("bgsrc") or "поверх картинки/градієнта"
            else:
                bg = it["bgArr"]
                origin = it.get("bgsel", "")
                if it.get("layers", 1) > 1:
                    origin += f" · композит {it['layers']} шарів"
            # ефективний колір тексту: rgba-альфа × opacity предків поверх фону
            fga = max(0.0, min(1.0, float(it.get("fgA") or 1)))
            opa = max(0.0, min(1.0, float(it.get("opA") or 1)))
            fg_eff = _blend(fg, fga * opa, bg)
            need = threshold if threshold else (3.0 if it["large"] else 4.5)
            r = contrast(fg_eff, bg)
            if r >= need:
                continue

            halo = _halo_note(fg_eff, it)
            new, how = ("", "") if it.get("nofix") else pick_replacement(
                fg, bg, need, it.get("secPal") or [], it.get("pagePal") or [],
                alpha=opa)
            drop = ("secPal", "pagePal", "bgArr", "vid",
                    "fgA", "opA", "shadow", "strokeW", "strokeC", "layers")
            rec = {k: v for k, v in it.items() if k not in drop}
            sev = "error" if r < 2.0 else "warn"
            msg = (f"контраст {r:.2f}:1 (треба {need}:1) — "
                   f"{to_hex(fg_eff)} на {to_hex(bg)}")
            if it.get("part"):
                msg += f" · {it['part']}"
            if fga * opa < 0.999:
                msg += f" · текст напівпрозорий (α={fga * opa:.2f})"
            if halo:
                sev = "warn"                 # обводка робить текст читабельним
                msg += " · " + halo
            if hidden:
                sev = "warn"
                msg += " · " + hidden
            rec.update({
                "page": page, "kind": "contrast", "sev": sev,
                "r": round(r, 2), "need": need,
                "bg": to_hex(bg), "fg_hex": to_hex(fg), "origin": origin,
                "msg": msg, "hidden": hidden,
            })
            if new:
                rec["fix"] = {"to": to_hex(new), "how": how,
                              "r_after": round(contrast(_blend(new, opa, bg), bg), 2)}
                key = (kind,) + _group_key(rec)
                with guard:
                    take = (not hidden and key not in seen_keys
                            and budget[kind] > 0)
                    if take:
                        seen_keys.add(key)
                        budget[kind] -= 1
                if take:
                    wanted.append((rec, vid, rec["fix"]["to"]))
            found.append(rec)

        # прев'ю: ОДИН скрін «після» на всю сторінку замість двох на знахідку
        if wanted:
            try:
                before = shot()                # знімається тут, якщо ще не був
                p.eval("window.__visApply(%s)" % json.dumps(
                    {str(vid): color for _rec, vid, color in wanted}))
                after = _Shot(p.shot())
                p.eval("window.__visRevert()")
                for rec, _vid, _color in wanted:
                    b, a = before.cut(rec["rect"], 6), after.cut(rec["rect"], 6)
                    verdict = _preview_verdict(b, a)
                    if verdict == "ok":
                        rec["preview"] = {"before": before.b64(rec["rect"]),
                                          "after": after.b64(rec["rect"])}
                        continue
                    # без картинки — але з причиною, а не молча
                    rec["no_preview"] = (
                        "зміна кольору не помітна на кропі"
                        if verdict == "subtle" else
                        "перефарбування не змінило рендер — фікс може не подіяти")
                    with guard:
                        raw["flat"] += 1
            except Exception:
                pass

        return found + _form_pass(p, kind, page)

    def _form_pass(p: _Page, kind: str, page: str) -> list[dict]:
        """Сабміт забирає таб на іншу адресу, тому це ЗАВЖДИ останній крок на
        сторінці. Тільки desktop і поки не набрали ліміт РІЗНИХ форм — та
        сама форма на 17 сторінках нічого нового не покаже."""
        if not do_form or kind != "desktop":
            return []
        with guard:
            if len(seen_forms) >= MAX_FORM_TESTS:
                return []
        try:
            got, sig = run_form_test(p, page, d["url"], expect, fdata)
        except Exception as e:
            return [{"kind": "form_flow", "sev": "warn", "page": page, "sel": "form",
                     "msg": f"прогін форми впав: {str(e)[:120]}"}]
        if sig is None:
            return []
        with guard:
            if sig in seen_forms:
                return []
            seen_forms.add(sig)
        return got

    try:
        res = _open(deployer._browser_bin(), d["url"], viewports, pages, work,
                    settle_js=SETTLE_JS if do_text else SETTLE_FORM_JS,
                    load_event=("Page.loadEventFired" if do_text
                                else "Page.domContentEventFired"),
                    # сторінка може тягнути десятки сторонніх скриптів (typekit,
                    # gtm, hubspot): для прогону форми DOM уже придатний, чекати
                    # на них до 25с немає сенсу
                    load_timeout=25 if do_text else 8)
    finally:
        if not keep:
            deployer.stop(branch)

    views = {}
    raw_rows = 0
    for kind, items in res["views"].items():
        raw_rows += len(items)
        merged = _merge(items)
        for i in merged:
            i["fid"] = _fid(kind, _group_key(i))
        views[kind] = merged

    counts: dict[str, int] = {}
    for items in views.values():
        for i in items:
            counts[i["kind"]] = counts.get(i["kind"], 0) + 1
    verdict = _verdict(views, tests)
    summary = {
        "branch": branch, "url": d["url"],
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "threshold": threshold, "counts": counts, "tests": sorted(tests),
        "pages": pages,
        "pages_skipped": max(0, len(all_pages) - len(pages)),
        "total": sum(counts.values()),
        "raw_total": raw_rows,
        "errors": sum(1 for v in views.values() for i in v if i["sev"] == "error"),
        "hidden": raw["hidden"], "no_preview": raw["flat"],
        "page_errors": res["errors"],
        "verdict": verdict,
        "views": views,
    }
    summary_path(branch).write_text(
        json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    return summary


# ---------------------------------------------------------------- підсумок
# Головне питання після прогону — «що вийшло, а що ні». Раніше відповідь
# доводилось збирати очима зі списку знахідок, ще й фільтри «тільки з фіксом /
# тільки помилки» ховали результат форми (вона без фікса і часто info).
# Тому вердикт рахується на бекенді й лежить у короткому підсумку — видно
# одразу в списку, до розгортання і незалежно від фільтрів.
_FORM_KINDS = ("form_flow", "form_input")


def _verdict(views: dict, tests) -> dict:
    out: dict = {}
    items = [i for v in views.values() for i in v]

    if "form" in tests:
        flows = [i for i in items if i["kind"] == "form_flow"]
        notes = [i for i in items if i["kind"] == "form_input"]
        if not flows and not notes:
            out["form"] = {"status": "none",
                           "msg": "контактної форми на сканованих сторінках не знайшлось"}
        else:
            rank = {"error": 2, "warn": 1, "info": 0}
            worst = max(flows or notes, key=lambda i: rank.get(i["sev"], 0))
            ok = [i for i in flows if i["sev"] == "info"]
            status = {"error": "fail", "warn": "warn", "info": "ok"}[worst["sev"]]
            # форма може дійти до подяки і ВОДНОЧАС приймати порожній сабміт —
            # тоді це «працює, але є зауваження», а не провал
            if status == "ok" and notes:
                status = "warn"
            out["form"] = {
                "status": status,
                "msg": worst["msg"],
                "landed": ((worst.get("form") or {}).get("landed")
                           or ((ok[0].get("form") or {}).get("landed") if ok else "")),
                "forms": len(flows),
                "notes": [i["msg"] for i in notes][:3],
            }

    if "text" in tests:
        rows = [i for i in items if i["kind"] not in _FORM_KINDS]
        errs = sum(1 for i in rows if i["sev"] == "error")
        warns = sum(1 for i in rows if i["sev"] == "warn")
        fixable = sum(1 for i in rows if i.get("fix"))
        out["text"] = {
            "status": "fail" if errs else ("warn" if warns else "ok"),
            "rows": len(rows), "errors": errs, "warns": warns, "fixable": fixable,
        }
    return out


def _brief_summary(s: dict) -> dict:
    return {**{k: s[k] for k in ("branch", "ts", "threshold", "counts", "total",
                                 "errors", "raw_total", "tests", "verdict")
               if k in s},
            "pages": len(s.get("pages") or []),
            "page_errors": len(s.get("page_errors") or [])}


def run_many(branches: list[str], threshold: float | None = None,
             max_pages: int = MAX_PAGES, workers: int | None = None,
             form_data: dict | None = None,
             tests: list[str] | tuple | set | None = None) -> list[dict]:
    """Кілька віток ОДНОЧАСНО: у кожної свій php-порт і свій Chrome, тож
    вузьке місце — процесор, а не послідовність. Помилка однієї вітки не
    зупиняє решту.

    Пул — `projects.Pool`: кожна вітка деплоїться і читає знімок у проєкті
    людини, яка запустила прогін, а голий пул стартує в дефолтному."""
    n = max(1, min(workers or branch_workers(), len(branches) or 1))
    out: list[dict] = []
    lock = threading.Lock()

    def one(br: str):
        try:
            s = run(br, threshold, max_pages, form_data=form_data, tests=tests)
            item = _brief_summary(s)
        except Exception as e:
            item = {"branch": br, "error": str(e)[:300]}
        with lock:
            out.append(item)

    with projects.Pool(max_workers=n) as ex:
        list(ex.map(one, branches))
    order = {b: i for i, b in enumerate(branches)}
    return sorted(out, key=lambda x: order.get(x["branch"], 0))


# ---------------------------------------------------------------- правка джерела
# Знахідка приходить з DOM ЗІБРАНОЇ сторінки, а правити треба джерело у знімку.
# У php-вайті це той самий html/php, у node — компонент: розмітку Nuxt пише в
# `.vue`, Next — у `.tsx`, і в `dist/` вони вже скомпільовані. Без цих масок
# `files` лишався порожнім, і КОЖНА знахідка node-вітки відсіювалась з
# «елемент не знайдено у джерелі» — на 16 наявних прогонах 0 застосованих
# правок із ~180. З ними — 16-17 на вітку, решта відсівається чесно
# (компонент один, а на сторінці два його інстанси — відповідність
# неоднозначна, і чіпати не можна).
SRC_EXT = (".html", ".htm", ".php", ".vue", ".tsx")

# Вміст, з якого браузер НЕ створює елементів: <noscript> (при увімкненому
# JS), коментарі, <script> (рядки-шаблони всередині). Тег у такому блоці є
# в ДЖЕРЕЛІ, але відсутній серед DOM-близнюків — через це правило
# «файл = сторінка» бачило 9 проти 8 і відмовлялось КОЖНОМУ фіксу телефону:
# кейс zipleh-coiqanu.ch-ch-fr, де 9-й tel-лінк лежить у <noscript>.
# Рахуємо і нумеруємо по DOM-виду джерела; заміна пробілами зберігає
# довжину, тож оффсети збігаються з оригіналом і правка лягає в те саме
# місце. <template> тут НЕМАЄ свідомо: у .vue це корінь усього джерела.
_NON_DOM_RX = re.compile(
    r"<noscript\b.*?(?:</noscript\s*>|$)"
    r"|<script\b.*?(?:</script\s*>|$)"
    r"|<!--.*?(?:-->|$)", re.S | re.I)


def _dom_view(text: str) -> str:
    return _NON_DOM_RX.sub(lambda m: " " * len(m.group(0)), text)


def _fid(viewport: str, key: tuple) -> str:
    """Стабільний id ГРУПИ знахідок — щоб UI міг попросити фікс саме її.
    Один id = один баг, навіть якщо він трапляється на 17 сторінках."""
    raw = viewport + "|" + "|".join(str(x) for x in key)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


def _halo_note(fg_eff, it: dict) -> str:
    """text-shadow / -webkit-text-stroke, що реально відділяє текст від фону.

    Критерій: колір тіні/обводки контрастує з САМИМ текстом ≥3:1 — тоді
    навколо літер є читабельний край незалежно від фону (банерний текст
    з обводкою). Така знахідка не error, а warn."""
    cands = []
    sh = it.get("shadow") or ""
    if sh:
        cands += re.findall(r"rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}", sh)
    if float(it.get("strokeW") or 0) >= 0.5 and it.get("strokeC"):
        cands.append(it["strokeC"])
    for c in cands:
        p = parse_rgb(c)
        if p and contrast(fg_eff, p) >= 3.0:
            return "тінь/обводка компенсує"
    return ""


def _deploy_docroot(branch: str) -> Path:
    root = deployer.deploy_root() / branch.replace("/", "__")
    # php/статичний вайт у node-проєкті деплоїться як є, без dist/
    return (root / "dist") if deployer.is_node_build(branch) else root


# Клієнтські роути vue-вайта. `_list_pages` перебирає ФАЙЛИ деплою, а
# vite-ssg/SPA складає весь сайт в ОДИН `dist/index.php` — тож обхід файлів
# бачить рівно «/», і візуальні перевірки міряли 1 сторінку з 11. Заміряно на
# `nwf-zuontfug-befelur-ch-de`: `_list_pages` віддавав `['/']`, а роутер
# оголошує 11 роутів. Саме через це «на VUE вайтах не все знаходить»: у
# `ArticleBodyIndustries.vue` і `ArticleBodyHelp.vue` увесь текст статті стояв
# класами `text-white/80` на секції `bg-white` (контраст 1.00, тобто нічого не
# видно), а зонд на /sektoren і /hilfe жодного разу не заходив.
#
# Джерело правди — той самий файл роутера, з якого читає чек `thanks_route`.
ROUTER_FILES = ("src/router/index.js", "src/router/index.ts",
                "src/router.js", "src/router.ts")
# Беремо значення `path:` БУДЬ-ДЕ у файлі, а не «обʼєкт роуту цілком»: матчер
# `thanks_route` вимагає обʼєкт без вкладених дужок, тож роут із `children`
# губить БАТЬКА (`{path:'/eltern', children:[{path:'kinder'}]}` віддавав лише
# `kinder`). Структура тут і не потрібна - потрібні самі адреси.
_ROUTE_RX = re.compile(r"\bpath\s*:\s*['\"]([^'\"]*)['\"]")
# Динамічні й catch-all роути пропускаємо: `/:id` без значення не відкрити, а
# `/:pathMatch(.*)*` — це ловець 404, а не сторінка. Відносні шляхи вкладених
# роутів (`kinder`) теж поза списком: сама по собі це не адреса, а повну треба
# складати з батьком - цього тут свідомо не робимо.
_DYNAMIC_RX = re.compile(r"[:*(]")


def _router_pages(branch: str) -> list[str]:
    """Роути з джерела роутера вітки. Порожньо — якщо роутера немає."""
    d = snapshot_dir(branch)
    for rel in ROUTER_FILES:
        p = d / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out = []
        for m in _ROUTE_RX.finditer(text):
            path = m.group(1).strip()
            if not path.startswith("/") or _DYNAMIC_RX.search(path):
                continue
            if path not in out:
                out.append(path)
        return out
    return []


def _list_pages(branch: str) -> list[str]:
    """Сторінки вітки для сканування — з готового деплою (він 1:1 те, що
    віддає php -S, включно зі збілдженим dist/ для node-вайтів) ПЛЮС клієнтські
    роути з роутера, яких у деплої немає жодним файлом (див. `_router_pages`).

    Повна сторінка = файл з <html>/<!doctype — партіали, vendor-стаб і
    php-хелпери відсіюються. index → «/», nuxt-роути about/index.html →
    «/about/». 200/404.html у node-вайтах — SPA-фолбеки-копії index,
    їх пропускаємо."""
    # Роути з роутера додаються НЕЗАЛЕЖНО від деплою: вони живуть у знімку, а
    # не у dist. Раніше тут стояв ранній `return ["/"]` на відсутній теці
    # деплою — і клієнтські роути в цьому разі не додавались ніколи. Саме так
    # `nwf-corwenwonoui-judibame-co-es` просканувався по одній сторінці («/»),
    # а `text-white/80` на `bg-white` у `ArticleBodyProcess.vue` (контраст
    # 1.00, текст статті на /proceso не видно взагалі) зонд не побачив.
    doc = _deploy_docroot(branch)
    pages = []
    if doc.exists():
        for p in sorted(doc.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in (".html", ".htm", ".php"):
                continue
            rel = p.relative_to(doc).as_posix()
            if rel.startswith(("vendor/", "node_modules/", "_")):
                continue
            if projects.ptype() == "node" and p.name in ("200.html", "404.html"):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace").lower()
            except Exception:
                continue
            if "<html" not in text and "<!doctype" not in text:
                continue
            if rel in ("index.php", "index.html", "index.htm"):
                url = "/"
            elif rel.endswith("/index.html"):
                url = "/" + rel[: -len("index.html")]
            else:
                url = "/" + rel
            if url not in pages:
                pages.append(url)
    for url in _router_pages(branch):
        if url not in pages:
            pages.append(url)
    pages.sort(key=lambda u: (u != "/", u))
    return pages or ["/"]


def _patch_style(tag: str, prop: str, value: str) -> str:
    """Дописує у відкриваючий тег inline-декларацію з !important.

    Сам inline виграє над класами й правилами, але НЕ над css-правилом з
    !important (кейс: .uuqr p {color:#1a1a1a !important} у <style> вайта
    глушив попередній фікс). Inline + !important — найвищий пріоритет
    каскаду, тож фікс не залежить від того, звідки значення узялось, і
    зачіпає рівно один елемент, а не весь токен палітри.

    Однакова механіка для двох правок: `color` для контрасту і
    `padding-top` для секції, яку накрив фіксований хедер.
    """
    same = re.compile(r"\s*" + re.escape(prop) + r"\s*:", re.I)
    # СТАТИЧНИЙ style, а не прив'язка: у Vue-шаблоні `:style="heroBg"` і
    # `v-bind:style` — це вираз JS, дописати туди «padding-top:64px» означає
    # зламати білд. Тому перед `style` не має бути ні `:`, ні `-`, ні літери.
    m = re.search(r"""(?<![-:\w])style\s*=\s*(?:"([^"]*)"|'([^']*)')""", tag, re.I)
    if m:
        val = m.group(1) if m.group(1) is not None else m.group(2)
        span = m.span(1) if m.group(1) is not None else m.span(2)
        decls = [d.strip() for d in val.split(";") if d.strip() and not same.match(d)]
        decls.append(f"{prop}:{value} !important")
        return tag[:span[0]] + "; ".join(decls) + tag[span[1]:]
    close = "/>" if tag.rstrip().endswith("/>") else ">"
    return (tag[: tag.rfind(close)].rstrip()
            + f' style="{prop}:{value} !important"' + close)


_ATTR_RX = re.compile(r'([a-zA-Z_:][-\w:.]*)(?:="([^"]*)")?')


def _tag_rx(tag: str):
    """Регекс пошуку DOM-нормалізованого відкриваючого тега у джерелі.

    Зонд віддає openTag з outerHTML, а браузер серіалізує не так, як
    написано у файлі: безлапковий атрибут (data-cookie-reject) стає
    data-cookie-reject="", лапки зводяться до подвійних, пробіли — до
    одного. Тому точний find() у джерелі промахується (кейс: кнопки
    кукі-банера). Матчимо структурно: той самий порядок атрибутів, але
    з довільними пробілами, обома типами лапок і опційним ="" у
    порожніх значень.
    """
    m = re.match(r"<([a-zA-Z][-\w]*)(.*?)\s*/?>\s*$", tag.strip(), re.S)
    if not m:
        return re.compile(re.escape(tag))
    name, attrs_s = m.group(1), m.group(2)
    pat = ["<", re.escape(name)]
    for am in _ATTR_RX.finditer(attrs_s):
        n, v = am.group(1), am.group(2)
        pat.append(r"\s+" + re.escape(n))
        if not v:                              # порожнє/безлапкове значення
            pat.append(r"(?:\s*=\s*(?:\"\"|''))?")
        else:
            alts = [f'"{re.escape(v)}"', f"'{re.escape(v)}'"]
            if re.fullmatch(r"""[^\s"'=<>`]+""", v):
                alts.append(re.escape(v))      # безлапкове у джерелі
            pat.append(r"\s*=\s*(?:" + "|".join(alts) + ")")
    pat.append(r"\s*/?>")
    return re.compile("".join(pat))


def _class_rx(tag: str):
    """Запасний матчер: тег + САМЕ значення class, решта атрибутів довільна.

    У node-вайті розмітку пише шаблон, і в DOM приїжджає те, чого в джерелі
    немає дослівно: `<li v-for="p in mainPages"><a :href="p.to" class="…">`
    рендериться вісьмома `<a href="/a-empresa" …>`, `<a href="/referencias" …>`
    і т.д. Точний `_tag_rx` тут промахується завжди, бо `href` у джерелі —
    прив'язка, а не літерал.

    Спільним лишається клас: усі інстанси приходять з ОДНОГО вузла шаблону,
    тож і колір у них спільний, і правити треба саме той вузол — одна правка
    лагодить усі вісім. Тому сигнатура — ім'я тега + точний рядок class.
    Повертає None, якщо класу немає: без нього сигнатура надто широка.
    """
    m = re.match(r"<([a-zA-Z][-\w]*)(.*?)\s*/?>\s*$", tag.strip(), re.S)
    if not m:
        return None
    name, attrs_s = m.group(1), m.group(2)
    cls = None
    for am in _ATTR_RX.finditer(attrs_s):
        if am.group(1).lower() == "class" and am.group(2):
            cls = am.group(2)
            break
    if not cls or not cls.strip():
        return None
    return re.compile(
        r"<" + re.escape(name) + r"(?:\s+[^>]*?)?\s+class\s*=\s*"
        r"(?:\"" + re.escape(cls) + r"\"|'" + re.escape(cls) + r"')"
        r"(?:\s+[^>]*?)?\s*/?>")


def _fix_decl(i: dict) -> tuple[str, str] | None:
    """(css-властивість, значення) inline-правки знахідки — або None, якщо
    готового фікса в неї немає. Єдине місце, де вид знахідки перетворюється
    на конкретну декларацію: далі механіка пошуку елемента в коді спільна.
    """
    fix = i.get("fix") or {}
    if i.get("kind") == "contrast" and fix.get("to"):
        return ("color", fix["to"])
    if i.get("kind") == "hero_overlap" and fix.get("padTop"):
        return ("padding-top", f"{int(fix['padTop'])}px")
    return None


def compute_fixes(branch: str, fids: list[str] | None = None) -> dict:
    """Знаходить у файлах знімка елементи знахідок і готує правки.

    Нічого не пише. Повертає {"edits": {path: (old, new)}, "applied": [...],
    "skipped": [...]} — те, що не знайшлося однозначно, чесно пропускаємо,
    а не вгадуємо.
    """
    import runner

    data = load(branch)
    if not data:
        raise ValueError("спершу прогони візуальні перевірки на цій вітці")

    want = set(fids) if fids else None
    applied, skipped = [], []

    # Групуємо по відкриваючому тегу: близнюки (ідентичні теги — 6 кнопок
    # квіза, кукі-банер на кожній сторінці) правляться ОДНИМ проходом по
    # файлу, кожен — за своїм tagIx. Знахідка після склейки несе anchors —
    # усі свої входження (у т.ч. з інших сторінок і в'юпортів).
    # ключ мапи — (властивість, значення): у контрасту це color, у
    # перекритого хедером hero — padding-top; далі механіка спільна
    groups: dict = {}                  # (openTag, tagTotal) -> {ix: ((prop, val), item)}
    for items in data.get("views", {}).values():
        for i in items:
            decl = _fix_decl(i)
            if not decl:
                continue
            if want is not None and i.get("fid") not in want:
                continue
            anchors = i.get("anchors")
            if anchors is None:            # звіт зі старого формату
                anchors = _anchors_of(i)
            if not anchors:
                skipped.append({**_brief(i), "why": "не вдалося визначити позицію елемента"})
                continue
            for a in anchors:
                g = groups.setdefault((a["openTag"], a.get("tagTotal", 0)), {})
                g.setdefault(a["tagIx"], (decl, i))

    files = {p: runner.read_snapshot_file(branch, p).decode("utf-8", errors="replace")
             for p in runner.snapshot_files(branch)
             if p.lower().endswith(SRC_EXT)}
    # рахунок і нумерація — по DOM-виду (без noscript/коментарів/скриптів),
    # правки — в оригінал за тими самими оффсетами (довжина збережена)
    views = {p: _dom_view(t) for p, t in files.items()}

    edits: dict[str, str] = {}                 # path -> поточний текст
    for (tag, total_dom), ixmap in groups.items():
        # Файли, де кількість збігів = кількості таких елементів на сторінці:
        # тоді N-й у файлі і є N-й у DOM. Таких файлів зазвичай кілька —
        # у цих вайтах хедер/футер/банери лежать копією на кожній сторінці,
        # тобто це той самий баг, і правити його треба скрізь.
        rx = _tag_rx(tag)
        hits = []
        for p, text in views.items():
            n = sum(1 for _ in rx.finditer(text))
            if n:
                hits.append((p, n))
        by_class = False
        if not hits:
            # Шаблон рендерить те, чого в джерелі немає дослівно: `v-for` з
            # прив'язаним href дає вісім `<a href="/a-empresa" …>` з ОДНОГО
            # вузла. Спільним лишається клас — а він і визначає колір, тож
            # правка по класовій сигнатурі лагодить рівно те, що зламане.
            # Однакових вузлів у файлі буває кілька (у цьому футері `mainPages`
            # і `legalPages` — два ідентичні `<a>`), і правити треба ВСІ: клас
            # той самий, значить і дефект той самий.
            crx = _class_rx(tag)
            if crx is not None:
                hits = [(p, n) for p, n in
                        ((p, sum(1 for _ in crx.finditer(t))) for p, t in views.items())
                        if n]
                by_class = bool(hits)
                if by_class:
                    rx = crx
        if not hits:
            for _c, it in ixmap.values():
                skipped.append({**_brief(it), "why": "елемент не знайдено у джерелі "
                                "(ймовірно, генерується php/js)"})
            continue
        # по класу індекс у DOM ні до чого: у джерелі вузол один
        exact = [p for p, _n in hits] if by_class else [p for p, n in hits if n == total_dom]
        if not exact:
            # Vue-вайти: сторінка зшита з КОМПОНЕНТІВ, тож 3 однакові елементи
            # на сторінці — це 3 файли по 1 входженню (або 1 вузол, відрендерений
            # кілька разів через v-for/props). Жоден файл не дає n == total_dom,
            # і php-правило «файл = сторінка» тут не працює. Але якщо ФІКС для
            # всіх інстансів той самий — джерело стилю сам тег, і за прецедентом
            # класового фолбека («сигнатура та сама → дефект той самий») правимо
            # всі входження в усіх файлах, де тег є. Розбіжні фікси (той самий
            # тег на різних тлах вимагає різних кольорів) чесно скіпаються.
            if len({d for d, _ in ixmap.values()}) == 1:
                exact = [p for p, _n in hits]
                by_class = True          # той самий index-free механізм патча
        if not exact:
            got = ", ".join(f"{p}:{n}" for p, n in hits[:3])
            for _c, it in ixmap.values():
                skipped.append({**_brief(it), "why": f"на сторінці таких елементів "
                                f"{total_dom}, а в коді — {got}; відповідність неоднозначна"})
            continue

        done = []
        for path in sorted(exact):
            cur = edits.get(path, files[path])
            # один прохід: n-те входження тега → якщо n у ixmap, патчимо його;
            # _patch_style отримує тег У ФОРМІ ДЖЕРЕЛА (m.group(0)), тож
            # оригінальне форматування зберігається
            parts, last, changed = [], 0, False
            for n, tm in enumerate(rx.finditer(_dom_view(cur))):
                # по класу у джерелі вузол один, а DOM-індекс належить
                # інстансу — беремо першу-ліпшу декларацію групи (вони
                # однакові: інстанси родом з того самого вузла)
                decl = ixmap[n][0] if n in ixmap else (
                    sorted(ixmap.items())[0][1][0] if by_class else None)
                if decl:
                    parts.append(cur[last:tm.start()])
                    parts.append(_patch_style(cur[tm.start():tm.end()], *decl))
                    last = tm.end()
                    changed = True
            if changed:
                parts.append(cur[last:])
                edits[path] = "".join(parts)
                done.append(path)
        for _ix, ((prop, val), it) in sorted(ixmap.items()):
            if done:
                applied.append({**_brief(it), "paths": done, "to": f"{prop}:{val}"})
            else:
                skipped.append({**_brief(it), "why": "входження вже змінене іншим фіксом"})

    # Та сама знахідка живе у кількох інстансах (desktop + mobile, кілька
    # anchors) — без дедупу «не змогло виправити» показує один рядок тричі.
    def _dedup(rows, key):
        seen, out = set(), []
        for r in rows:
            k = key(r)
            if k not in seen:
                seen.add(k)
                out.append(r)
        return out

    applied = _dedup(applied, lambda r: (r.get("fid"), r.get("to"),
                                         tuple(r.get("paths") or [])))
    skipped = _dedup(skipped, lambda r: (r.get("fid"), r.get("why")))
    return {"edits": {p: (files[p], t) for p, t in edits.items()},
            "applied": applied, "skipped": skipped}


def _brief(i: dict) -> dict:
    return {"fid": i.get("fid"), "sel": i.get("sel"), "page": i.get("page"),
            "txt": (i.get("txt") or "")[:60],
            "from": i.get("fg_hex"), "r": i.get("r"),
            "r_after": (i.get("fix") or {}).get("r_after")}


def load(branch: str) -> dict | None:
    p = summary_path(branch)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def delete(branch: str) -> bool:
    p = summary_path(branch)
    if p.exists():
        p.unlink()
        return True
    return False


def list_results() -> list[dict]:
    """Короткі підсумки без важких прев'ю — для списку у вкладці."""
    if not vis_root().exists():
        return []
    out = []
    for p in vis_root().glob("*.json"):
        try:
            out.append(_brief_summary(json.loads(p.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return sorted(out, key=lambda x: x["branch"])
