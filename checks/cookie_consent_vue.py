"""Кукі-банер на Vue-вайтах (new-white-front): його немає взагалі.

Заміряно 19.10 на корпусі nwf-*: 0 з 6 випадкових віток мають компонент
згоди; є лише сторінка «Política de cookies» (`src/pages/Cookies.vue`), на
яку ніхто не веде, доки банер не з'явиться. QA ту саму скаргу пише і на
php-вайти (868mewn6p, 868mdy83f): «На главной нет баннера куки — добавить
баннер с кнопками Принять/Отклонить». Чек `cookie_consent` — лише php.

Детект: у `src/` немає компонента зі згодою на кукі (ключові слова згоди
+ кнопка), підключеного в `src/App.vue` (інакше він не на всіх сторінках).

Фікс: `src/components/CookieConsentBanner.vue` мовою вітки (`<html lang>`
у index.html → хвіст назви вітки) у стилях вітки — клас кнопки сайту
(той самий підбір, що в php-чеку: _site_button_classes на футері/хедері,
без іконок і без заливки) або акцент із `tailwind.config`/css-змінних;
лінк на сторінку cookies/privacy з `src/data/pages.js`; стан у
localStorage; SSR-safe (жодного window у setup — лише в onMounted), тож
vite-ssg рендерить банер прихованим і показує лише без збереженої згоди.
Монтування — в `src/App.vue` після `<router-view />`.
"""
import re

import checks.cookie_consent as _cc

NAME = "Кукі-банер на Vue-вайті: немає"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["node"]
DESCRIPTION = ("Vue-вайт без банера згоди на кукі (Прийняти/Відхилити). Фікс "
               "додає компонент CookieConsentBanner.vue мовою і в стилях вітки "
               "(клас кнопки сайту або акцент), лінк на сторінку cookies/privacy "
               "з pages.js, localStorage, і монтує його в App.vue — банер на "
               "всіх сторінках.")
FILES = ["*.vue", "*.js", "*.html"]

COMPONENT = "src/components/CookieConsentBanner.vue"
APP = "src/App.vue"
CONSENT_WORDS_RX = re.compile(r"cookie|consent|lgpd|dsgvo|gdpr|kolači|cookies", re.I)
# слова згоди: php-набір + усі «Прийняти» з I18N (hr «Prihvati», nl, sl, ar)
_EXTRA_ACCEPT = ("Prihvati", "Accepteren", "Sprejmi", "قبول", "同意する")
ACCEPT_RX = re.compile(r"(?:" + _cc.ACCEPT_RX.pattern + r"|\b(?:" + "|".join(map(re.escape, _EXTRA_ACCEPT)) + r")\b)", re.I)
BUTTONISH_RX = re.compile(r"<button\b|@click", re.I)
LANG_RX = re.compile(r"""<html\b[^>]*\blang\s*=\s*["']([a-zA-Z-]+)""", re.I)
_LOCALE_RX = re.compile(r"[-.]([a-z]{2})-([a-z]{2})(?:-\d+)?$")
PAGE_ROUTE_RX = re.compile(r'"id":\s*"(cookies|privacy)"[\s\S]*?"route":\s*"([^"]+)"')
IMPORT_LINE_RX = re.compile(r"^import\s+(\w+)\s+from\s+'@/components/(\w+)\.vue'", re.M)
COMPONENTS_RX = re.compile(r"components:\s*\{([^}]*)\}")

I18N = dict(_cc.I18N_BANNER)
I18N.update({
    "hr": ("Koristimo kolačiće kako bismo poboljšali vaše iskustvo. Pogledajte našu",
           "Politiku kolačića", "Prihvati", "Odbij"),
    "nl": ("Wij gebruiken cookies om uw ervaring te verbeteren. Zie ons",
           "Cookiebeleid", "Accepteren", "Weigeren"),
    "sl": ("Piškotke uporabljamo za izboljšanje vaše izkušnje. Oglejte si",
           "Politiko piškotkov", "Sprejmi", "Zavrni"),
    "ar": ("نستخدم ملفات تعريف الارتباط لتحسين تجربتك. راجع",
           "سياسة ملفات تعريف الارتباط", "قبول", "رفض"),
})


def _lang(files: dict, branch: str) -> str:
    m = LANG_RX.search(files.get("index.html", ""))
    code = (m.group(1) if m else "").lower().split("-")[0]
    if code in I18N and code != "en":
        return code
    lm = _LOCALE_RX.search((branch or "").lower())
    tail = lm.group(2) if lm else code
    return tail if tail in I18N else (code if code in I18N else "en")


def _consent_components(files: dict) -> list:
    """Компоненти, що виглядають як банер згоди: слова згоди + кнопка;
    сторінки політик (src/pages/*, *Cookies*.vue контент-блоки) — не банер."""
    out = []
    for p, t in files.items():
        if not p.startswith("src/components/") or not p.endswith(".vue"):
            continue
        tm = re.search(r"<template>([\s\S]*)</template>", t)
        tpl = tm.group(1) if tm else t
        if (CONSENT_WORDS_RX.search(tpl) and ACCEPT_RX.search(tpl) and BUTTONISH_RX.search(tpl)
                and ("localStorage" in t or "cookie" in t.lower())):
            out.append(p)
    return out


def _mounted_in_app(files: dict, comps: list) -> bool:
    app = files.get(APP, "")
    names = {p.rsplit("/", 1)[-1][:-4] for p in comps}
    return any(re.search(rf"<{n}\b", app) for n in names)


def run_branch(files, all_paths, branch: str = ""):
    if APP not in files:
        return []
    comps = _consent_components(files)
    if comps and _mounted_in_app(files, comps):
        return []
    if comps:
        msg = (f"компонент згоди на кукі є ({comps[0]}), але не підключений у "
               f"src/App.vue — на сторінках банера немає; фікс додасть власний "
               f"банер у App.vue")
    else:
        msg = ("на Vue-вайті немає кукі-банера — фікс додасть CookieConsentBanner.vue "
               "(Прийняти/Відхилити мовою вітки, у стилях вітки, лінк на політику) "
               "і підключить його в App.vue на всіх сторінках")
    return [{"path": APP, "line": 1, "severity": "error", "message": msg}]


# ---------------------------------------------------------------- стилі
def _policy_route(files: dict) -> str:
    pj = files.get("src/data/pages.js", "")
    found = dict((k, v) for k, v in PAGE_ROUTE_RX.findall(pj))
    return found.get("cookies") or found.get("privacy") or ""


_TW_BTN_RX = re.compile(r'<(?:a|button)\b[^>]*class="([^"]*)"')
_TW_FILL_RX = re.compile(r"\bbg-[a-z]+-\d{3}\b")
_TW_SHAPE_RX = re.compile(r"\bp[xy]-\d|\brounded")
_TW_DROP_RX = re.compile(r"\b(?:w-full|inline-block|block|hidden|md:[\w-]+|lg:[\w-]+|sm:[\w-]+|mt-\d+|mb-\d+|shadow[\w-]*)\b")


def _button_class(files: dict) -> tuple:
    """(клас «Прийняти», клас «Відхилити»). Спершу іменовані класи сайту
    (btn/…-btn через php-чек), інакше найчастіший Tailwind-набір CTA
    (заливка bg-*-NNN + падінг/радіус) по всіх .vue — це і є «кнопка
    сайту» у nwf-шаблоні; «Відхилити» — ті самі класи без заливки."""
    for p in sorted(files, key=lambda p: (not re.search(r"(?i)footer|header|nav", p), p)):
        if p.endswith(".vue"):
            cls, line = _cc._site_button_classes(files[p], files)
            if cls:
                return cls, (line or cls)
    counts = {}
    for p, t in files.items():
        if not p.endswith(".vue"):
            continue
        for m in _TW_BTN_RX.finditer(t):
            c = " ".join(m.group(1).split())
            if _TW_FILL_RX.search(c) and _TW_SHAPE_RX.search(c) and "hover:text" not in c.split("bg-")[0]:
                counts[c] = counts.get(c, 0) + 1
    if not counts:
        return "", ""
    best = max(counts, key=lambda c: (counts[c], -len(c)))
    acc = " ".join(t for t in best.split() if not _TW_DROP_RX.match(t))
    # банер компактний: падінг CTA (px-8 py-4) у нижньому барі завеликий
    acc = re.sub(r"\bpx-\d+\b", "px-4", acc)
    acc = re.sub(r"\bpy-\d+(?:\.\d+)?\b", "py-2", acc)
    dec = " ".join(t for t in acc.split() if not t.startswith(("bg-", "hover:bg-", "text-white")))
    dec = dec + " border border-white/60 text-white"
    return acc, dec


def _accent(files: dict) -> str:
    tw = files.get("tailwind.config.js", "") or files.get("tailwind.config.cjs", "")
    m = re.search(r"(?:primary|accent|brand)\s*:\s*['\"](#[0-9a-fA-F]{3,8})['\"]", tw)
    if m:
        return m.group(1)
    return _cc._site_accent(files) or "#10b981"


def banner_vue(files: dict, branch: str) -> str:
    lang = _lang(files, branch)
    intro, policy, accept, decline = I18N[lang]
    route = _policy_route(files)
    link = (f'\n        <a :href="policy" class="underline hover:no-underline">{policy}</a>.'
            if route else "")
    cls, cls_dec = _button_class(files)
    if cls:
        acc = f'<button type="button" class="{cls}" @click="choose(true)">{accept}</button>'
        dec = f'<button type="button" class="{cls_dec}" @click="choose(false)">{decline}</button>'
    else:
        acc = (f'<button type="button" class="px-4 py-2 rounded-lg text-white font-semibold" '
               f'style="background:{_accent(files)}" @click="choose(true)">{accept}</button>')
        dec = ('<button type="button" class="px-4 py-2 rounded-lg text-white border border-white/60" '
               f'@click="choose(false)">{decline}</button>')
    return f'''<template>
  <div
    v-if="show"
    data-wp-consent="banner"
    role="dialog"
    aria-live="polite"
    class="fixed inset-x-0 bottom-0 z-[2147483000] flex flex-wrap items-center justify-center gap-3 px-4 py-3 text-sm text-white"
    style="background:rgba(17,24,39,.96)"
  >
    <span>
      {intro}{link}
    </span>
    {acc}
    {dec}
  </div>
</template>

<script>
const KEY = 'wp-cookie-consent'

export default {{
  name: 'CookieConsentBanner',
  data() {{
    return {{ show: false, policy: '{route}' }}
  }},
  mounted() {{
    // лише на клієнті: під vite-ssg window/localStorage немає
    try {{
      this.show = !window.localStorage.getItem(KEY)
    }} catch (e) {{
      this.show = true
    }}
  }},
  methods: {{
    choose(ok) {{
      const v = ok ? '1' : '0'
      try {{ window.localStorage.setItem(KEY, v) }} catch (e) {{}}
      document.cookie = KEY + '=' + v + ';path=/;max-age=31536000'
      this.show = false
    }}
  }}
}}
</script>
'''


def _mount_in_app(app: str) -> str:
    if "<CookieConsentBanner" in app:
        return app
    new = app
    # 1) тег після <router-view /> (або перед закриттям кореневого div)
    if re.search(r"<router-view\s*/>", new):
        new = re.sub(r"(<router-view\s*/>)", r"\1\n    <CookieConsentBanner />", new, count=1)
    else:
        new = new.replace("</template>", "    <CookieConsentBanner />\n</template>", 1)
    # 2) імпорт + реєстрація
    if "<script setup" in new:
        new = re.sub(r"(<script setup[^>]*>\n)", r"\1import CookieConsentBanner from '@/components/CookieConsentBanner.vue'\n", new, count=1)
        return new
    imports = list(IMPORT_LINE_RX.finditer(new))
    imp = "import CookieConsentBanner from '@/components/CookieConsentBanner.vue'\n"
    if imports:
        last = imports[-1]
        new = new[:last.end()] + "\n" + imp.rstrip("\n") + new[last.end():]
    else:
        new = re.sub(r"(<script>\n)", r"\1" + imp, new, count=1)
    cm = COMPONENTS_RX.search(new)
    if cm:
        inner = cm.group(1).strip()
        inner = (inner + ", CookieConsentBanner") if inner else "CookieConsentBanner"
        new = new[:cm.start()] + "components: { " + inner + " }" + new[cm.end():]
    else:
        new = re.sub(r"(export default \{\n)", r"\1  components: { CookieConsentBanner },\n", new, count=1)
    return new


def fix_branch(files, all_paths, branch: str = ""):
    if APP not in files:
        return []
    comps = _consent_components(files)
    if comps and _mounted_in_app(files, comps):
        return []
    actions = []
    if COMPONENT not in files:
        actions.append({"type": "edit", "path": COMPONENT, "content": banner_vue(files, branch)})
    new_app = _mount_in_app(files[APP])
    if new_app != files[APP]:
        actions.append({"type": "edit", "path": APP, "content": new_app})
    return actions
