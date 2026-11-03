"""50 варіацій скрипта форми-заглушки (checks/form_stub).

Однаковий скрипт на тисячах вайтів — футпринт. Тут 5 осей, що міняють і
текст коду, і поведінку в межах зразка favojuug.net (кнопка «надсилається»,
затримка, подяка або редірект):

  style     — як підвішуємо обробник: IIFE одразу / DOMContentLoaded /
              load / querySelectorAll+forEach / for-цикл / onsubmit-властивість
  delay     — 1100…1900 мс
  thanks    — вигляд inline-подяки: ✓ / ✔ / без іконки / іконка-svg /
              smile; h3+p / strong+p / p+p
  hide      — як ховаємо форму: display:none / hidden / remove / opacity+remove
  names     — імена функцій/змінних (з id вітки, щоб не повторювались)

Варіант = індекс 0..49 → фіксована комбінація осей (таблиця VARIANTS
нижче, детермінована), тож той самий сайт завжди отримує той самий код.
Усі варіанти проходять через один і той самий структурний відбиток
(form_stub.STUB_SCRIPT_RX): `querySelectorAll("form[data-<id>]")`,
`preventDefault()`, `setTimeout` в одному inline-скрипті.
"""
import json

STYLES = ("iife", "domready", "load", "foreach", "forloop", "onsubmit")
DELAYS = (1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900)
THANKS = ("check", "heavy", "plain", "svg", "smile", "strong", "pp")
HIDES = ("none", "hidden", "remove", "fade")

# 50 комбінацій (style, delay, thanks, hide) — підібрані так, щоб кожна вісь
# розкладалась рівномірно і жодна пара не повторювалась
VARIANTS = [
    ("iife", 1400, "check", "none"), ("domready", 1200, "heavy", "hidden"), ("load", 1600, "plain", "remove"),
    ("foreach", 1300, "svg", "fade"), ("forloop", 1500, "smile", "none"), ("onsubmit", 1700, "strong", "hidden"),
    ("iife", 1100, "pp", "remove"), ("domready", 1800, "check", "fade"), ("load", 1200, "heavy", "none"),
    ("foreach", 1900, "plain", "hidden"), ("forloop", 1400, "svg", "remove"), ("onsubmit", 1300, "smile", "fade"),
    ("iife", 1600, "strong", "none"), ("domready", 1500, "pp", "hidden"), ("load", 1100, "check", "remove"),
    ("foreach", 1700, "heavy", "fade"), ("forloop", 1800, "plain", "none"), ("onsubmit", 1200, "svg", "hidden"),
    ("iife", 1900, "smile", "remove"), ("domready", 1300, "strong", "fade"), ("load", 1400, "pp", "none"),
    ("foreach", 1500, "check", "hidden"), ("forloop", 1100, "heavy", "remove"), ("onsubmit", 1600, "plain", "fade"),
    ("iife", 1200, "svg", "none"), ("domready", 1700, "smile", "hidden"), ("load", 1800, "strong", "remove"),
    ("foreach", 1400, "pp", "fade"), ("forloop", 1900, "check", "none"), ("onsubmit", 1500, "heavy", "hidden"),
    ("iife", 1300, "plain", "remove"), ("domready", 1100, "svg", "fade"), ("load", 1500, "smile", "none"),
    ("foreach", 1600, "strong", "hidden"), ("forloop", 1200, "pp", "remove"), ("onsubmit", 1800, "check", "fade"),
    ("iife", 1700, "heavy", "none"), ("domready", 1400, "plain", "hidden"), ("load", 1900, "svg", "remove"),
    ("foreach", 1100, "smile", "fade"), ("forloop", 1600, "strong", "none"), ("onsubmit", 1900, "pp", "hidden"),
    ("iife", 1500, "check", "remove"), ("domready", 1600, "heavy", "fade"), ("load", 1300, "plain", "none"),
    ("foreach", 1800, "svg", "hidden"), ("forloop", 1700, "smile", "remove"), ("onsubmit", 1100, "strong", "fade"),
    ("iife", 1800, "pp", "none"), ("domready", 1900, "check", "hidden"),
]
assert len(VARIANTS) == 50 and len(set(VARIANTS)) == 50

_SVG = ('<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle>'
        '<path d="m9 12 2 2 4-4"></path></svg>')


def _names(sid: str) -> dict:
    """Імена з id вітки: різні на кожному сайті, без спільних токенів."""
    a, b_, c = sid[:3], sid[2:5], sid[3:6]
    return {"fn": f"{a}Send", "done": f"{b_}Done", "msgs": f"{c}Txt", "goto": f"{a}Go",
            "busy": f"{b_}Busy", "box": f"{c}Box", "btn": f"{a}Btn", "list": f"{b_}Forms"}


def _thanks_html(kind: str, n: dict) -> str:
    """JS-вираз (рядок) з innerHTML подяки; T.title/T.body підставляються."""
    T = n["msgs"]
    icon = {"check": '<div style="font-size:40px;line-height:1;margin-bottom:12px">&#10003;</div>',
            "heavy": '<div style="font-size:36px;line-height:1;margin-bottom:10px">&#10004;</div>',
            "smile": '<div style="font-size:38px;line-height:1;margin-bottom:10px">&#128578;</div>',
            "svg": f'<div style="display:flex;justify-content:center;margin-bottom:12px">{_SVG}</div>',
            "plain": "", "strong": "", "pp": ""}[kind]
    if kind == "strong":
        body = f"'<p style=\"margin:0 0 6px\"><strong>'+{T}.title+'</strong></p><p style=\"margin:0;opacity:.85\">'+{T}.body+'</p>'"
    elif kind == "pp":
        body = f"'<p style=\"margin:0 0 6px;font-weight:600\">'+{T}.title+'</p><p style=\"margin:0\">'+{T}.body+'</p>'"
    else:
        body = f"'{icon}<h3 style=\"margin:0 0 8px;font-size:1.25rem\">'+{T}.title+'</h3><p style=\"margin:0;opacity:.85\">'+{T}.body+'</p>'"
    return body


def _hide_js(kind: str, f: str) -> str:
    return {"none": f'{f}.style.display="none";',
            "hidden": f'{f}.hidden=true;{f}.setAttribute("aria-hidden","true");',
            "remove": f'{f}.parentNode.removeChild({f});',
            "fade": f'{f}.style.transition="opacity .25s";{f}.style.opacity="0";setTimeout(function(){{if({f}.parentNode){f}.parentNode.removeChild({f})}},260);'}[kind]


def render(idx: int, sid: str, lang_texts: tuple, thanks_href: str) -> str:
    """Скрипт варіанта idx (0..49) для вітки з id `sid`."""
    style, delay, thanks, hide = VARIANTS[idx % len(VARIANTS)]
    n = _names(sid)
    sending, title, body = lang_texts
    t = json.dumps({"sending": sending, "title": title, "body": body}, ensure_ascii=False)
    T, done, goto, busy, box, btn, fn, lst = (n["msgs"], n["done"], n["goto"], n["busy"], n["box"], n["btn"], n["fn"], n["list"])
    sel = f'"form[data-{sid}]"'
    done_fn = (
        f"function {done}(f){{\n"
        f"  if({goto}){{window.location.href={goto};return}}\n"
        f"  var {box}=document.createElement(\"div\");{box}.setAttribute(\"role\",\"status\");{box}.className=f.className;\n"
        f"  {box}.style.cssText=\"padding:28px 24px;text-align:center\";\n"
        f"  {box}.innerHTML={_thanks_html(thanks, n)};\n"
        f"  f.parentNode.insertBefore({box},f);{_hide_js(hide, 'f')}\n"
        f"}}\n")
    handler = (
        f"function {fn}(e){{\n"
        f"  var f=e.currentTarget||this;e.preventDefault();e.stopImmediatePropagation();\n"
        f"  if(f.dataset.{busy})return;f.dataset.{busy}=\"1\";\n"
        f"  var {btn}=f.querySelector('button[type=\"submit\"],input[type=\"submit\"],button:not([type])');\n"
        f"  if({btn}){{{btn}.disabled=true;if({btn}.tagName===\"INPUT\"){btn}.value={T}.sending;else {btn}.textContent={T}.sending}}\n"
        f"  setTimeout(function(){{{done}(f)}},{delay});\n"
        f"}}\n")
    if style == "foreach":
        bind = f"Array.prototype.forEach.call(document.querySelectorAll({sel}),function(f){{f.addEventListener(\"submit\",{fn},true)}});\n"
    elif style == "forloop":
        bind = f"var {lst}=document.querySelectorAll({sel});for(var i=0;i<{lst}.length;i++){{{lst}[i].addEventListener(\"submit\",{fn},true)}}\n"
    elif style == "onsubmit":
        bind = f"var {lst}=document.querySelectorAll({sel});for(var i=0;i<{lst}.length;i++){{{lst}[i].onsubmit={fn}}}\n"
    else:
        bind = f"document.querySelectorAll({sel}).forEach(function(f){{f.addEventListener(\"submit\",{fn},true)}});\n"
    core = f"var {T}={t};var {goto}={json.dumps(thanks_href)};\n{done_fn}{handler}{bind}"
    if style == "domready":
        wrapped = f"document.addEventListener(\"DOMContentLoaded\",function(){{\n{core}}});\n"
    elif style == "load":
        wrapped = f"window.addEventListener(\"load\",function(){{\n{core}}});\n"
    else:
        wrapped = f"(function(){{\n{core}}})();\n"
    return "<script>\n" + wrapped + "</script>\n"
