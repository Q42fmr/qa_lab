"""Двокрокова форма не перемикає крок: розмітка кроків є, обробника немає.

Кейс `auto_br-*` (bruhaladhrz.pro та решта): у формі два кроки — перший з
полями вибору і кнопкою «Próxima etapa / Continuar / Próximo», другий з
контактними полями і справжнім `type="submit"`. Другий крок схований власною
розміткою вітки, а кнопка переходу — `type="button"`, тобто нічого не робить
сама по собі. Обробника, який зняв би приховування, у `js/main.js` немає
взагалі (`is-active` там є, але то таби: `data-tab`/`data-panel`). Наслідок:
відвідувач не може дійти до полів контакту, а сабміт-кнопка недосяжна — форма
мертва на головній і на `contact.html`.

Ховання кроку вітки роблять чотирма способами, і всі чотири трапляються серед
шести названих віток:
  * клас `hidden` на кроці (`.form-step.hidden{display:none}` у style.css);
  * HTML-атрибут `hidden`;
  * клас-«вмикач» `is-active` (видимий лише активний крок);
  * той самий `active`.

Тому і чек, і фікс не зашивають назв: спосіб визначається з самої розмітки.
Фікс дописує у СПІЛЬНИЙ бандл вітки (`js/main.js`, який підключають усі
крокові сторінки) один незалежний від jQuery контролер між маркерами
`[qa_lab:form-steps]` — прибрав маркери, повернув байт-у-байт.

Контролер робить РІВНО перехід між кроками (це і є поломка) і підсвічування
індикатора (`.step-dot`/`.form-step-ind` — класи вітки, стилі вже є у її css).
Валідації він не додає: форми стоять `novalidate`, власну перевірку вітки
робив перехоплювач сабміту, який глушив відправку і законно знятий чеком
`form_hijack` — вигадувати нову тут не наша справа.

Одно­крокові форми не чіпаються взагалі: гейт — «кроків ≥ 2 І є кнопка
переходу». З шести названих віток дві (`…como-ler-dados-abertos…`,
`…seguran-a-digital…`) мають звичайну форму без кроків — там чек мовчить.
"""
import os
import re

NAME = "Форма з 2 кроків не перемикається"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Форма з двома кроками: другий крок схований розміткою, а кнопка "
               "«Próxima etapa / Continuar / Próximo» — `type=\"button\"` без "
               "обробника, тож перейти на крок 2 (де поля контакту й сабміт) "
               "неможливо. Автофікс дописує у спільний js-бандл вітки контролер "
               "переходу між кроками; односкладові форми не чіпає.")
FILES = ["*.html", "*.htm", "*.php", "*.js"]

MARK = "qa_lab:form-steps"
FORM_RX = re.compile(r"<form\b[\s\S]*?</form\s*>", re.I)
# крок: data-step="N" або клас-токен form-step (не form-steps / form-step-ind /
# form-step-indicator — то обгортка й індикатор)
STEP_RX = re.compile(r"""data-step\s*=\s*["']\d+["']|class\s*=\s*["'][^"']*\bform-step\b(?![-\w])""", re.I)
BTN_RX = re.compile(r"""<button\b[^>]*type\s*=\s*["']button["'][^>]*>(?P<txt>[\s\S]{0,80}?)</button\s*>""", re.I)
NEXT_TXT_RX = re.compile(r"pr[oó]xim|continuar|avan[cç]ar|seguinte|next", re.I)
BACK_TXT_RX = re.compile(r"voltar|anterior|back", re.I)
NEXT_CLS_RX = re.compile(r"form-next", re.I)
SCRIPT_SRC_RX = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["'](?P<src>[^"']+)["']""", re.I)
PAGE_EXT = (".html", ".htm", ".php")


def _steps(form: str) -> int:
    return len(STEP_RX.findall(form))


def _has_next(form: str) -> bool:
    """Кнопка переходу вперед: `type="button"` з класом form-next* або текстом
    «Próxima/Continuar/Próximo…». Кнопка «← Voltar» за перехід не рахується."""
    for m in BTN_RX.finditer(form):
        whole, txt = m.group(0), re.sub(r"<[^>]+>", " ", m.group("txt"))
        if BACK_TXT_RX.search(txt):
            continue
        if NEXT_CLS_RX.search(whole) or NEXT_TXT_RX.search(txt):
            return True
    return False


def _local_scripts(page: str, text: str) -> list[str]:
    """Локальні js-файли, які підключає сторінка (шлях у знімку)."""
    base = os.path.dirname(page)
    out = []
    for m in SCRIPT_SRC_RX.finditer(text):
        src = m.group("src").split("?")[0].strip()
        if not src or "://" in src or src.startswith("//") or "<?" in src:
            continue
        p = os.path.normpath(os.path.join(base, src)).replace("\\", "/").lstrip("./")
        if p.endswith(".js"):
            out.append(p)
    return out


def _stepped_pages(files: dict) -> dict:
    """{сторінка: [локальні js]} для сторінок із 2-кроковою формою."""
    out = {}
    for path, text in files.items():
        if not path.lower().endswith(PAGE_EXT):
            continue
        for form in FORM_RX.findall(text):
            if _steps(form) >= 2 and _has_next(form):
                out[path] = _local_scripts(path, text)
                break
    return out


def _wired(files: dict, scripts: list[str]) -> bool:
    """Чи слухає хтось кнопку переходу: наш маркер або власна логіка вітки."""
    for s in scripts:
        t = files.get(s, "")
        if MARK in t or "form-step" in t or NEXT_CLS_RX.search(t):
            return True
    return False


def run_branch(files, all_paths, branch: str = ""):
    pages = _stepped_pages(files)
    if not pages:
        return []
    issues = []
    for page, scripts in sorted(pages.items()):
        if _wired(files, scripts):
            continue
        where = ", ".join(scripts) if scripts else "жодного локального js"
        issues.append({
            "path": page, "line": 1, "severity": "error",
            "message": ("форма з 2 кроків не перемикається: кнопку переходу "
                        "ніхто не слухає, крок 2 (поля контакту й сабміт) "
                        f"недосяжний — у бандлах сторінки ({where}) обробника "
                        "немає; фікс дописує контролер кроків"),
        })
    return issues


CONTROLLER = """
/* [""" + MARK + """] контролер кроків: розмітка 2-крокової форми є, а обробника переходу немає.
   Прибери обидва маркери разом із кодом між ними, щоб повернути як було. */
(function () {
  var NEXT = /pr[o\\u00f3]xim|continuar|avan[c\\u00e7]ar|seguinte|next/i;
  var BACK = /voltar|anterior|back/i;

  function isInd(el) {
    return /(indicator|step-ind|step-dot|dots|progress)/i.test(el.className || '');
  }
  function steps(form) {
    var all = form.querySelectorAll('[data-step], .form-step'), out = [], i, el;
    for (i = 0; i < all.length; i++) {
      el = all[i];
      if (isInd(el)) continue;
      if (!el.querySelector('input, select, textarea, button')) continue;
      out.push(el);
    }
    return out;
  }
  /* спосіб ховання визначаємо з розмітки вітки, а не зашиваємо */
  function mech(list) {
    var i;
    for (i = 0; i < list.length; i++) {
      if (list[i].hasAttribute('hidden')) return { kind: 'attr' };
      if (list[i].classList.contains('hidden')) return { kind: 'off', token: 'hidden' };
    }
    for (i = 0; i < list.length; i++) {
      if (list[i].classList.contains('is-active')) return { kind: 'on', token: 'is-active' };
      if (list[i].classList.contains('active')) return { kind: 'on', token: 'active' };
    }
    return { kind: 'style' };
  }
  function visible(el, m) {
    if (m.kind === 'attr') return !el.hasAttribute('hidden');
    if (m.kind === 'off') return !el.classList.contains(m.token);
    if (m.kind === 'on') return el.classList.contains(m.token);
    return el.style.display !== 'none';
  }
  function apply(list, m, ix) {
    for (var i = 0; i < list.length; i++) {
      var on = i === ix, el = list[i];
      if (m.kind === 'attr') { if (on) { el.removeAttribute('hidden'); } else { el.setAttribute('hidden', ''); } }
      else if (m.kind === 'off') { el.classList.toggle(m.token, !on); }
      else if (m.kind === 'on') { el.classList.toggle(m.token, on); }
      else { el.style.display = on ? '' : 'none'; }
    }
  }
  function bind(form) {
    if (form.getAttribute('data-wp-steps')) return;
    var list = steps(form);
    if (list.length < 2) return;                 /* односкладову форму не чіпаємо */
    var m = mech(list), ix = 0, i;
    for (i = 0; i < list.length; i++) { if (visible(list[i], m)) { ix = i; break; } }
    var dots = form.querySelectorAll('.step-dot, .form-step-ind');
    var btns = form.querySelectorAll('button[type="button"]');
    var bound = 0;
    for (i = 0; i < btns.length; i++) {
      (function (btn) {
        var txt = (btn.textContent || '');
        var back = BACK.test(txt);
        var next = /form-next/i.test(btn.className || '') || NEXT.test(txt);
        if (!back && !next) return;
        bound++;
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          var to = back ? ix - 1 : ix + 1;
          if (to < 0 || to >= list.length) return;
          ix = to;
          apply(list, m, ix);
          for (var k = 0; k < dots.length; k++) { dots[k].classList.toggle('active', k === ix); }
          if (typeof btn.blur === 'function') { btn.blur(); }
        });
      })(btns[i]);
    }
    if (bound) { form.setAttribute('data-wp-steps', String(list.length)); }
  }
  function init() {
    var fs = document.querySelectorAll('form');
    for (var i = 0; i < fs.length; i++) { bind(fs[i]); }
  }
  if (document.readyState !== 'loading') { init(); }
  else { document.addEventListener('DOMContentLoaded', init); }
})();
/* [/""" + MARK + """] */
"""


def fix_branch(files, all_paths, branch: str = ""):
    pages = _stepped_pages(files)
    if not pages:
        return []
    todo = {p: s for p, s in pages.items() if not _wired(files, s)}
    if not todo:
        return []

    # бандл, який підключають ВСІ крокові сторінки: одна правка лагодить усі.
    # Немає спільного — не вигадуємо місця, чек лишається червоним.
    common = None
    for scripts in todo.values():
        s = set(scripts)
        common = s if common is None else (common & s)
    if not common:
        return []
    target = max(sorted(common), key=lambda p: len(files.get(p, "")))
    text = files.get(target, "")
    if MARK in text:
        return []
    return [{"type": "edit", "path": target,
             "content": text.rstrip("\n") + "\n" + CONTROLLER}]
