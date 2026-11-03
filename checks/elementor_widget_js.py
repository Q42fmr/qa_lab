"""Elementor-віджети з обробником у webpack-чанку: попап і nested-tabs мертві.

Скрейпер зберігає лише те, що прописано статично в `<script src>`. Elementor
Pro/Elementor вантажать частину логіки віджетів через webpack lazy-чанки, які
`webpack.runtime.min.js` довантажує динамічно через `<script>`, вставлений з
JS - у скрейпленому HTML такого тега немає взагалі, тож чанк не завантажується
НІКОЛИ. Заміряно на `pibmftanum.ch`:

  * `wp-content/plugins/elementor-pro/assets/js/` містить РІВНО 3 файли
    (`webpack-pro.runtime.min.js`, `frontend.min.js`, `elements-handlers.min.js`);
    `wp-content/plugins/elementor/assets/js/` - теж рівно 3. Жодного
    `*.bundle.min.js`.
  * Мапа чанків у `webpack-pro.runtime.min.js:2` називає точні відсутні
    файли: `popup.61d4fcab8891b2e07802.bundle.min.js` (id 887),
    `form.cfd61a9174be80f835c6.bundle.min.js` (325, форму веде інший чек).
    У `webpack.runtime.min.js:1` - `nested-tabs.a2401356d329f179475e.bundle.min.js`
    (215).
  * Найсильніший доказ: `index.html:1417-1424` уже має чужий неробочий
    "фікс" - `$(document).on('mouseenter', '.e-n-tab-title', ...)` синтезує
    клік через `dispatchEvent(new MouseEvent('click'))`. Раз довелось
    підміняти клік наведенням, значить справжнього обробника кліку немає
    взагалі - і цей костиль лишає баг "таб перемикається від самого
    наведення миші", а не від кліку.

Два незалежні віджети:

Правило 1 - popup-тригер (`index.html:262`): `<a class="elementor-icon"
href="#elementor-action:action=popup:open&settings=<base64 {"id":"2357",...}>">`.
Розмітка самого попапа у скрейпі Є (`index.html:1220`,
`data-elementor-type="popup" data-elementor-id="2357"
class="elementor elementor-2357 elementor-location-popup"`), CSS - теж.
Бракує рівно двох речей, і обидві перевірені на диску: **обробника кліку**
(чанк `popup.*.bundle.min.js`) і **геометрії overlay** - її давала
dialog-бібліотека `elementor/assets/lib/dialog/`, теки якої у скрейпі немає
зовсім. Решта на місці: `elementor-pro/assets/css/conditionals/popup.min.css`
Є, і саме вона першим правилом ховає розмітку
(`[data-elementor-type=popup]:not(.elementor-edit-area){display:none}`) та
описує обгортку `.elementor-popup-modal > .dialog-widget-content >
.dialog-message`, яку Elementor будував у рантаймі; вигляд шухляди дає
`post-2357.css`. Тому фікс не вигадує стилів, а будує ту саму обгортку -
див. коментар над `SCRIPT`.

Правило 2 - nested tabs (`index.html:607-632`): `.elementor-widget-n-tabs`
> `.e-n-tabs` > `.e-n-tabs-heading[role=tablist]` з кнопками
`.e-n-tab-title[aria-controls=...]`, і окремо `.e-n-tabs-content` з
панелями `.e-con`. Видимість панелі керує ВИКЛЮЧНО клас `.e-active` -
дослівно з `wp-content/uploads/elementor/css/custom-widget-nested-tabs.min.css:1`:
`.e-n-tabs-content>.e-con:not(.e-active){display:none}`. Без справжнього
обробника кліку цей клас ніколи не переїжджає на іншу панель.

Автофікс не чіпає згенеровані класи білдера (вони міняються з кожним
білдом) - позначає елементи власними `data-wp-elpopup`/`data-wp-eltabs` і
додає один незалежний від jQuery шим на сторінку. Заразом прибирає
чужий неробочий `mouseenter`-шим (`index.html:1417-1424`) - інакше
наведення мишкою продовжувало б перемикати таби без кліку.
"""
import base64
import functools
import html
import json
import re
from urllib.parse import unquote

NAME = "Elementor: віджет без webpack-чанка (popup / nested-tabs)"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Скрейпер не зберігає lazy-чанки Elementor (popup.*.bundle.min.js, "
               "nested-tabs.*.bundle.min.js) - тригер popup і кнопки nested-tabs "
               "лишаються без обробника кліку. Автофікс позначає елементи "
               "власними data-атрибутами і додає незалежний шим; заразом прибирає "
               "чужий неробочий mouseenter-костиль nested-tabs.")
FILES = ["*.html", "*.htm", "*.php"]

MARKER = "qa_lab:elementor-widget-js"
POPUP_ATTR = "data-wp-elpopup"
TABS_ATTR = "data-wp-eltabs"
POPUP_LOCATION_CLASS = "elementor-location-popup"

ANY_TAG_RX = re.compile(r"""<(?P<tag>[a-zA-Z][\w-]*)\b(?P<attrs>(?:[^>"']|"[^"]*"|'[^']*')*)>""")
SETTINGS_RX = re.compile(r"settings=([A-Za-z0-9+/=]+)")
BODY_CLOSE_RX = re.compile(r"</body\s*>", re.I)
SCRIPT_RX = re.compile(r"<script\b[^>]*>([\s\S]*?)</script>\s*", re.I)


@functools.lru_cache(maxsize=None)
def _attr_rx(name: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(name) + r"""\s*=\s*(?P<q>["'])(?P<v>[^"']*)(?P=q)""", re.I)


def _attr(attrs: str, name: str) -> str | None:
    m = _attr_rx(name).search(attrs)
    return m.group("v") if m else None


def _b64json(s: str):
    """Base64(URL-декодований)->JSON, або None на будь-якій ваді входу."""
    padded = s + "=" * (-len(s) % 4)
    try:
        return json.loads(base64.b64decode(padded).decode("utf-8"))
    except Exception:
        return None


def _popup_panels(text: str) -> dict:
    """id -> match відкривного тега з `data-elementor-id` + класом-локацією."""
    panels = {}
    for m in ANY_TAG_RX.finditer(text):
        cls = _attr(m.group("attrs"), "class")
        if not cls or POPUP_LOCATION_CLASS not in cls.split():
            continue
        pid = _attr(m.group("attrs"), "data-elementor-id")
        if pid:
            panels.setdefault(pid, m)
    return panels


def _popup_triggers(text: str):
    """(match лінка, id попапа) для кожного `<a href="#elementor-action:...">`."""
    for m in ANY_TAG_RX.finditer(text):
        if m.group("tag").lower() != "a":
            continue
        href = _attr(m.group("attrs"), "href")
        if not href:
            continue
        decoded = unquote(html.unescape(href))
        if "elementor-action" not in decoded or "action=popup:open" not in decoded:
            continue
        sm = SETTINGS_RX.search(decoded)
        if not sm:
            continue
        data = _b64json(sm.group(1))
        if not isinstance(data, dict) or not data.get("id"):
            continue
        yield m, str(data["id"])


def _popup_pairs(text: str):
    """[(лінк, панель, id)] - лише тригери, для яких розмітка попапа Є на
    сторінці. Немає розмітки - нема що показувати, тому не репортимо й не
    фіксимо (інакше шим відкриє порожню панель)."""
    panels = _popup_panels(text)
    return [(m, panels[pid], pid) for m, pid in _popup_triggers(text) if pid in panels]


def _tab_containers(text: str):
    """Контейнери `.e-n-tabs` - саме на них навішується перемикач."""
    out = []
    for m in ANY_TAG_RX.finditer(text):
        if m.group("tag").lower() != "div":
            continue
        cls = _attr(m.group("attrs"), "class")
        if cls and "e-n-tabs" in cls.split():
            out.append(m)
    return out


def run(path, text):
    if MARKER in text:
        return []
    issues = []
    pairs = _popup_pairs(text)
    if pairs:
        ids = sorted({pid for _, _, pid in pairs})
        issues.append({
            "line": text.count("\n", 0, pairs[0][0].start()) + 1,
            "severity": "error",
            "message": (f"{len(pairs)} лінк(ів) відкривають Elementor-попап "
                        f"(id {', '.join(ids)}) через "
                        f"`#elementor-action:action=popup:open`, але скрейпер не "
                        f"зберіг чанк `popup.*.bundle.min.js` - обробника кліку "
                        f"немає, попап не відкриється; розмітка попапа в файлі є, "
                        f"фікс дає власний незалежний шим"),
        })
    tabs = _tab_containers(text)
    if tabs:
        issues.append({
            "line": text.count("\n", 0, tabs[0].start()) + 1,
            "severity": "error",
            "message": (f"{len(tabs)} блок(ів) nested-tabs (`.e-n-tabs`): перемикання "
                        f"керує чанк `nested-tabs.*.bundle.min.js`, якого немає в "
                        f"скрейпі; видимість панелі лише через клас `.e-active` "
                        f"(custom-widget-nested-tabs.min.css:1), клікати нема кому - "
                        f"фікс дає власний шим перемикання"),
        })
    return issues


def _mark(tag: str, attr: str, value: str) -> str:
    """Дописує data-атрибут у відкривний тег, не чіпаючи решти."""
    if f"{attr}=" in tag.lower():
        return tag
    return tag[:-1].rstrip() + f' {attr}="{value}"' + tag[-1]


def _strip_broken_mouseenter_shim(text: str) -> str:
    """Прибирає чужий `$(...).on('mouseenter', '.e-n-tab-title', ...
    dispatchEvent(new MouseEvent('click')))` - синтезований клік від
    наведення, а не від справжнього кліку (index.html:1417-1424)."""
    def repl(m: re.Match) -> str:
        body = m.group(1)
        if ("mouseenter" in body and "e-n-tab-title" in body and
                "dispatchEvent" in body and "MouseEvent" in body):
            return ""
        return m.group(0)
    return SCRIPT_RX.sub(repl, text)


# Один незалежний від jQuery шим на всі знахідки сторінки.
#
# Попап НЕ можна просто показати `display:block` на самій розмітці, і це
# заміряно в браузері на деплої `pibmftanum.ch`: панель лежить у звичайному
# потоці документа (12-та з 42 дітей `<body>`), тож після такого показу вона
# з'являлась на `absoluteTop: 6822` при вікні 900px - тобто далеко за екраном.
# Клік «працював», а очима не відбувалось нічого.
#
# Правильна структура відома з самої вітки. `conditionals/popup.min.css` ховає
# розмітку (`[data-elementor-type=popup]:not(.elementor-edit-area){display:none}`)
# і описує ОБГОРТКУ, яку в рантаймі будував Elementor:
# `.elementor-popup-modal` > `.dialog-widget-content` > `.dialog-message`.
# Вигляд теж уже у вітці: `post-2357.css` дає `#elementor-popup-modal-2357`
# скрим `rgba(0,0,0,.8)`, `justify-content:flex-end`, а `.dialog-message` -
# шухляду `25vw x 100vh`. Немає рівно ОДНОГО: геометрії overlay - її давала
# dialog-бібліотека (`elementor/assets/lib/dialog/`), якої у скрейпі немає
# зовсім. Тому шим будує цю обгортку і додає САМЕ І ТІЛЬКИ `position:fixed`
# з z-index, а колір, вирівнювання й розміри лишає власній css вітки.
SCRIPT = (
    '<script data-qa_lab="' + MARKER + '">/* ' + MARKER + ' */\n'
    '(function(){\n'
    '  var OPEN = "flex", SHUT = "none";\n'
    '  function modalOf(id){ return document.getElementById("elementor-popup-modal-" + id); }\n'
    '  document.querySelectorAll(\'[%(p)s^="panel-"]\').forEach(function(panel){\n'
    '    var id = panel.getAttribute("%(p)s").slice(6);\n'
    '    if (modalOf(id) || !panel.parentNode) return;\n'
    '    var modal = document.createElement("div");\n'
    '    modal.id = "elementor-popup-modal-" + id;\n'
    '    modal.className = "elementor-popup-modal dialog-widget dialog-lightbox-widget'
    ' dialog-type-lightbox";\n'
    '    modal.style.cssText = "position:fixed;top:0;left:0;right:0;bottom:0;'
    'z-index:9999;display:none";\n'
    '    var content = document.createElement("div");\n'
    '    content.className = "dialog-widget-content dialog-lightbox-widget-content";\n'
    '    var msg = document.createElement("div");\n'
    '    msg.className = "dialog-message dialog-lightbox-message";\n'
    '    panel.parentNode.insertBefore(modal, panel);\n'
    '    modal.appendChild(content); content.appendChild(msg); msg.appendChild(panel);\n'
    '    panel.style.display = "block";\n'
    '  });\n'
    '  function shutAll(){\n'
    '    document.querySelectorAll(".elementor-popup-modal").forEach(function(m){\n'
    '      m.style.display = SHUT;\n'
    '    });\n'
    '  }\n'
    '  document.addEventListener("click", function(e){\n'
    '    var t = e.target && e.target.closest ? e.target : null;\n'
    '    if (!t) return;\n'
    '    var trig = t.closest("[%(p)s]");\n'
    '    if (trig && trig.getAttribute("%(p)s").indexOf("panel-") !== 0) {\n'
    '      e.preventDefault();\n'
    '      var m = modalOf(trig.getAttribute("%(p)s"));\n'
    '      if (m) { var on = m.style.display === OPEN; shutAll(); m.style.display = on ? SHUT : OPEN; }\n'
    '      return;\n'
    '    }\n'
    '    var tab = t.closest(".e-n-tab-title");\n'
    '    if (tab) {\n'
    '      var box = tab.closest("[%(t)s]");\n'
    '      if (box) {\n'
    '        box.classList.add("e-activated");\n'
    '        var titles = box.querySelectorAll(".e-n-tab-title");\n'
    '        for (var i = 0; i < titles.length; i++) {\n'
    '          titles[i].setAttribute("aria-selected", titles[i] === tab ? "true" : "false");\n'
    '        }\n'
    '        var panels = box.querySelectorAll(".e-n-tabs-content > .e-con");\n'
    '        for (var j = 0; j < panels.length; j++) { panels[j].classList.remove("e-active"); }\n'
    '        var id = tab.getAttribute("aria-controls");\n'
    '        var target = id && document.getElementById(id);\n'
    '        if (target) target.classList.add("e-active");\n'
    '      }\n'
    '      return;\n'
    '    }\n'
    '    // клік по скриму (сама модалка, поза білим вмістом) закриває\n'
    '    if (t.classList && t.classList.contains("elementor-popup-modal")) { shutAll(); return; }\n'
    '    if (!t.closest(".elementor-popup-modal")) shutAll();\n'
    '  });\n'
    '  document.addEventListener("keydown", function(e){\n'
    '    if (e.key === "Escape") shutAll();\n'
    '  });\n'
    '})();</script>\n'
) % {"p": POPUP_ATTR, "t": TABS_ATTR}


def fix(path, text):
    if MARKER in text:
        return text
    pairs = _popup_pairs(text)
    tabs = _tab_containers(text)
    if not pairs and not tabs:
        return text
    edits = {}
    for trig, panel, pid in pairs:
        edits[(trig.start(), trig.end())] = _mark(trig.group(0), POPUP_ATTR, pid)
        edits[(panel.start(), panel.end())] = _mark(panel.group(0), POPUP_ATTR, "panel-" + pid)
    for t in tabs:
        edits[(t.start(), t.end())] = _mark(t.group(0), TABS_ATTR, "1")
    out, last = [], 0
    for (s, e), new_tag in sorted(edits.items()):
        out.append(text[last:s])
        out.append(new_tag)
        last = e
    out.append(text[last:])
    new_text = "".join(out)
    new_text = _strip_broken_mouseenter_shim(new_text)
    m = BODY_CLOSE_RX.search(new_text)
    if m:
        return new_text[:m.start()] + SCRIPT + new_text[m.start():]
    return new_text + SCRIPT
