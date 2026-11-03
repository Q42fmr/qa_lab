"""Кнопки головної (і CTA у хедері) мають вести на форму, а форма — існувати.

Кейс `nwf-vipi-plegi-co-es` / `nwf-vipne-del-atetzojad-co-es` (vue-вайти):
генератор лишив CTA з літеральним `href="/"` — клік по «Agendar visita» (у
хероʼї, в секціях і в хедері справа) просто перезавантажує головну, а
форм-компонента (`*FormHome.vue`) у вітці немає взагалі. У здорових вайтах
цієї ж сім'ї (`nwf-garcia-…`, `nwf-quacmuoo-…`) на головній стоїть
`<XxxFormHome/>` з `id="form"`, і всі CTA ведуть на `/#form` — роутер сім'ї
має scrollBehavior саме під ці якорі.

Два правила:
  * **мертвий CTA** — літеральний `<a href="/">` (або `href="#"`, порожній)
    у дереві головної чи в хедері, всередині якого немає `<img>`. Лого так не
    ловиться (воно завжди з картинкою), навігація теж — вона на
    `:href="page.route"`;
  * **якір без цілі** — CTA веде на `#x` / `/#x`, а `id="x"` у дереві головної
    немає. Окремий випадок: `#form` без `<form>` — «кнопка на форму є, форми
    немає».

Автофікс (fix_branch) робить те, що зроблено руками у vipi-plegi/villa-del:
  * мертві CTA переадресовує: якщо текст кнопки називає сторінку з
    `data/pages.js` («Nuestro enfoque» → /proceso) — веде туди; решта (усі
    «Agendar/Solicitar/Conocer más…») — на `/#form`, як у всієї сім'ї;
  * якщо `<form>` на головній немає — генерує `LeadFormHome.vue` у
    дизайн-токенах САМОЇ вітки (кнопка = клас реального CTA, палітра
    нейтралі/акцент/радіуси — з компонентів головної, темна/світла тема — з
    фону героя, телефон — з хедера/футера, мова — із суфікса вітки es/pt)
    і вмикає його в Home.vue після CTA-секції.

Дерево головної збирається з роутера (`path: '/'` → сторінка) та імпортів
`@/components/…` цієї сторінки; хедер — компонент з `<header` серед імпортів
App.vue. Тому це run_branch/fix_branch, а не пофайловий run.
"""
import re

NAME = "Головна: кнопки ведуть на форму"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["node"]
DESCRIPTION = ("ЛИШЕ Vue-вайти (vue-router + .vue-сторінки): CTA головної та "
               "хедера не повинні вести на href=\"/\" чи на якір без цілі; "
               "якщо кнопки обіцяють форму — на головній мусить бути <form>. "
               "Автофікс переадресовує CTA (/#form або сторінка, названа в "
               "тексті) і генерує LeadFormHome.vue у токенах вітки. Не-Vue "
               "вітки (Next/React) мовчки пропускаються.")
FILES = ["*.vue", "*.js"]

HOME_ROUTE_RX = re.compile(
    r"path:\s*['\"]/['\"][\s\S]{0,220}?import\(['\"]@/([^'\"]+)['\"]\)")
IMPORT_RX = re.compile(
    r"import\s+\w+\s+from\s+['\"]@/(components/[^'\"]+\.vue)['\"]")
# літеральний <a …> цілком; :href="…" сюди не потрапляє
ANCHOR_RX = re.compile(r"<a\b[^>]*\bhref=\"([^\"]*)\"[^>]*>[\s\S]*?</a\s*>", re.I)
TEXT_RX = re.compile(r"<[^>]+>")
ID_RX = re.compile(r"\bid=\"([^\"]+)\"")
# мова форми — за суфіксом вітки; «-2» за ним — номер партії (…-br-pt-2)
PT_BRANCH_RX = re.compile(r"-pt(?:-\d+)?$")
DEAD = ("/", "#", "")


def _text(anchor_html: str) -> str:
    return re.sub(r"\s+", " ", TEXT_RX.sub(" ", anchor_html)).strip()[:48]


def _home_tree(files: dict) -> tuple[list, str | None]:
    """([шляхи компонентів головної], шлях хедера або None).

    Vue-гейт. Тип проєкту «node» у лабі покриває і Nuxt/Next, а правила цього
    чека (structure `@/pages/*.vue`, літеральні href у SFC-шаблонах) мають
    сенс лише для Vue: роутер мусить бути vue-router'івським `createRouter(`
    (`createBrowserRouter` з react-router сюди не матчиться — це інший
    рядок), а головна — `.vue`-файлом. Усе інше — не наш стек, мовчимо.
    """
    router = next((t for p, t in files.items()
                   if p.endswith(".js") and "createRouter(" in t), None)
    m = HOME_ROUTE_RX.search(router or "")
    if not m:
        return [], None
    home = "src/" + m.group(1)
    if not home.endswith(".vue") or home not in files:
        return [], None
    tree = [home] + ["src/" + rel for rel in IMPORT_RX.findall(files[home])
                     if "src/" + rel in files]
    header = None
    app = files.get("src/App.vue", "")
    for rel in IMPORT_RX.findall(app):
        p = "src/" + rel
        if p in files and "<header" in files[p].lower():
            header = p
            break
    return tree, header


def run_branch(files, all_paths, branch: str = ""):
    tree, header = _home_tree(files)
    if not tree:
        return []
    scan = tree + ([header] if header and header not in tree else [])
    ids = {i for p in tree for i in ID_RX.findall(files[p])}
    has_form = any("<form" in files[p] for p in tree)

    issues = []
    for p in scan:
        text = files[p]
        for m in ANCHOR_RX.finditer(text):
            href, whole = m.group(1).strip(), m.group(0)
            line = text.count("\n", 0, m.start()) + 1
            if href in DEAD:
                if "<img" in whole:
                    continue                      # лого — пропускаємо
                issues.append({
                    "path": p, "line": line, "severity": "error",
                    "message": (f"мертвий CTA «{_text(whole)}»: href=\"{href}\" "
                                f"веде на головну/нікуди — має вести на форму "
                                f"(/#form) або на свою сторінку"),
                })
                continue
            hm = re.fullmatch(r"/?#([\w-]+)", href)
            if hm and hm.group(1) not in ids:
                tid = hm.group(1)
                extra = " — і <form> на головній відсутня" \
                    if tid == "form" and not has_form else ""
                issues.append({
                    "path": p, "line": line, "severity": "error",
                    "message": (f"CTA «{_text(whole)}» веде на #{tid}, але "
                                f"id=\"{tid}\" на головній немає{extra}"),
                })
    return issues


# ------------------------------------------------------------------ автофікс
PAGES_RX = re.compile(r'"name":\s*"([^"]+)"[\s\S]{0,240}?"route":\s*"([^"]+)"')
BTN_RX = re.compile(r'<a\b[^>]*class="([^"]*\bbg-[a-z]+-\d{2,3}\b[^"]*'
                    r'\btext-white\b[^"]*)"')
SECTION_RX = re.compile(r'<section[^>]*class="([^"]*)"')
H2_RX = re.compile(r'<h2[^>]*class="([^"]*)"')
PHONE_RX = re.compile(r"\+\d[\d\s().-]{7,18}\d")
NEUTRALS = ("zinc", "slate", "neutral", "gray", "stone")
FORM_COMPONENT = "src/components/LeadFormHome.vue"

TEXTS = {
    "es": dict(eyebrow="Formulario de contacto", head="Envíanos tu consulta",
               sub="Completa el formulario y nuestro equipo te contactará a la brevedad.",
               name="Nombre", name_ph="Tu nombre completo",
               email="Correo electrónico", email_ph="tu@correo.com",
               phone="Teléfono", msg="Mensaje",
               msg_ph="Cuéntanos cómo podemos ayudarte",
               submit="Enviar consulta"),
    "pt": dict(eyebrow="Formulário de contato", head="Envie sua mensagem",
               sub="Preencha o formulário e nossa equipe entrará em contato em breve.",
               name="Nome", name_ph="Seu nome completo",
               email="E-mail", email_ph="seu@email.com",
               phone="Telefone", msg="Mensagem",
               msg_ph="Conte-nos como podemos ajudar",
               submit="Enviar mensagem"),
}


def _page_routes(files: dict) -> dict:
    """name.lower() -> route з data/pages.js; головну ('/') не пропонуємо."""
    src = next((t for p, t in files.items() if p.endswith("data/pages.js")), "")
    return {n.lower(): r for n, r in PAGES_RX.findall(src)
            if r != "/" and len(n) >= 4}


def _retarget(whole: str, href: str, text: str, routes: dict) -> str:
    """Куди має вести мертвий CTA. Текст, що називає сторінку, — на неї
    (беремо найдовшу назву, щоб «Nuestro enfoque completo» не з'їв коротший
    збіг); усе інше — на /#form, як у здорових вайтів сім'ї."""
    low = text.lower()
    target = "/#form"
    for name in sorted(routes, key=len, reverse=True):
        if name in low:
            target = routes[name]
            break
    return whole.replace(f'href="{href}"', f'href="{target}"', 1)


def _tokens(files: dict, tree: list, header: str | None) -> dict:
    """Дизайн-токени вітки: усе береться з її ж компонентів, нічого не
    вигадується. Кнопка форми — ДОСЛІВНО клас реального CTA."""
    blob = "".join(files[p] for p in tree)
    btn = next((m.group(1) for p in tree + ([header] if header else [])
                for m in BTN_RX.finditer(files[p])), None) \
        or "inline-block px-8 py-3 bg-indigo-700 hover:bg-indigo-800 text-white rounded-lg transition-colors font-sans"
    accent = (re.search(r"\bbg-([a-z]+-\d{2,3})\b", btn) or [None, "indigo-700"])[1]
    rounded = (re.search(r"\brounded(?:-\w+)?\b", btn) or [None])[0] or "rounded-lg"
    neutral = max(NEUTRALS, key=lambda n: blob.count(n))
    hero_cls = next((m.group(1) for p in tree[1:] + tree[:1]
                     for m in SECTION_RX.finditer(files[p])), "")
    dark = bool(re.search(r"bg-(?:[a-z]+)-(?:8|9)\d\d\b|bg-black\b", hero_cls))
    sect_bg = (re.search(r"\bbg-[a-z]+(?:-\d{2,3})?\b", hero_cls) or [None])[0] \
        or ("bg-%s-900" % neutral if dark else "bg-white")
    fonts = " ".join(re.findall(r"\bfont-[a-z]+\b", next(
        (m.group(1) for p in tree for m in H2_RX.finditer(files[p])), ""))) \
        or "font-sans font-bold"
    submit = re.sub(r"\binline-(?:block|flex)\b", "", btn).strip()
    submit = re.sub(r"\s{2,}", " ", submit)
    if "w-full" not in submit:
        submit = "w-full " + submit
    n = neutral
    if dark:
        pal = dict(card=f"bg-{n}-800 border border-{n}-700 {rounded} shadow-xl",
                   input=f"bg-{n}-900 border border-{n}-700 text-{n}-100 placeholder-{n}-500",
                   head=f"text-{n}-100", sub=f"text-{n}-400", label=f"text-{n}-100")
    else:
        pal = dict(card=f"bg-{n}-50 border border-{n}-200 {rounded}",
                   input=f"bg-white border border-{n}-200 text-{n}-900 placeholder-{n}-400",
                   head=f"text-{n}-900", sub=f"text-{n}-600", label=f"text-{n}-900")
    return dict(btn=submit, accent=accent, rounded=rounded, fonts=fonts,
                sect=f"{sect_bg} py-16 md:py-24 px-4", **pal)


def _find_phone(files: dict, tree: list, header: str | None) -> str:
    order = ([header] if header else []) \
        + [p for p in files if "<footer" in files.get(p, "").lower()] + tree
    for p in order:
        m = PHONE_RX.search(files.get(p, ""))
        if m:
            return m.group(0).strip()
    return ""


def _build_form(tok: dict, txt: dict, phone: str) -> str:
    inp = f"w-full px-4 py-3 {tok['input']} {tok['rounded']} font-sans " \
          f"focus:outline-none focus:border-{tok['accent']} transition-colors"
    return f"""<template>
  <section class="{tok['sect']}" id="form">
    <div class="max-w-2xl mx-auto {tok['card']} p-8 md:p-12">
      <div class="text-center mb-10">
        <p class="font-sans uppercase tracking-widest text-{tok['accent']} text-xs md:text-sm mb-3">
          {txt['eyebrow']}
        </p>
        <h2 class="{tok['fonts']} text-3xl md:text-4xl {tok['head']} mb-4">
          {txt['head']}
        </h2>
        <p class="font-sans {tok['sub']}">
          {txt['sub']}
        </p>
      </div>

      <form class="space-y-6">
        <div>
          <label for="lf-name" class="block font-sans text-sm {tok['label']} mb-2">{txt['name']}</label>
          <input id="lf-name" type="text" name="name" required
            class="{inp}" placeholder="{txt['name_ph']}">
        </div>
        <div>
          <label for="lf-email" class="block font-sans text-sm {tok['label']} mb-2">{txt['email']}</label>
          <input id="lf-email" type="email" name="email" required
            class="{inp}" placeholder="{txt['email_ph']}">
        </div>
        <div v-if="hasPhone">
          <label for="lf-phone" class="block font-sans text-sm {tok['label']} mb-2">{txt['phone']}</label>
          <input id="lf-phone" type="tel" name="phone"
            class="{inp}" :placeholder="phone">
        </div>
        <div>
          <label for="lf-message" class="block font-sans text-sm {tok['label']} mb-2">{txt['msg']}</label>
          <textarea id="lf-message" name="message" required rows="5"
            class="{inp} resize-none" placeholder="{txt['msg_ph']}"></textarea>
        </div>
        <button type="submit" class="{tok['btn']}">
          {txt['submit']}
        </button>
      </form>
    </div>
  </section>
</template>

<script setup>
const phone = '{phone}'
const hasPhone = phone && !phone.startsWith('@@')
</script>
"""


def _wire_home(home_text: str) -> str | None:
    """Вмикає <LeadFormHome /> у Home.vue: тег після CTA-секції (або першої
    секції), import після останнього import-компонента, реєстрація у
    components. Не знайшли якогось із трьох місць — None, нічого не ламаємо."""
    tags = list(re.finditer(r"^([ \t]+)<(\w+)\s*/>\s*$", home_text, re.M))
    if not tags:
        return None
    after = next((t for t in tags if re.search(r"CallToAction|Cta", t.group(2))),
                 tags[0])
    out = home_text[:after.end()] \
        + f"\n{after.group(1)}<LeadFormHome />" + home_text[after.end():]
    imports = list(re.finditer(
        r"^import\s+\w+\s+from\s+'@/components/[^']+\.vue'\s*$", out, re.M))
    if not imports:
        return None
    li = imports[-1]
    out = out[:li.end()] \
        + "\nimport LeadFormHome from '@/components/LeadFormHome.vue'" \
        + out[li.end():]
    cm = re.search(r"components:\s*\{([^}]*)\}", out)
    if not cm:
        return None
    inner = cm.group(1).rstrip()
    return out[:cm.start(1)] + inner + ", LeadFormHome " + out[cm.end(1):]


def fix_branch(files, all_paths, branch: str = ""):
    tree, header = _home_tree(files)
    if not tree:
        return []
    scan = tree + ([header] if header and header not in tree else [])
    routes = _page_routes(files)
    edits = {}

    for p in scan:
        text = files[p]

        def repl(m):
            href, whole = m.group(1).strip(), m.group(0)
            if href not in DEAD or "<img" in whole:
                return whole
            return _retarget(whole, m.group(1), _text(whole), routes)

        new = ANCHOR_RX.sub(repl, text)
        if new != text:
            edits[p] = new

    actions = [{"type": "edit", "path": p, "content": t}
               for p, t in edits.items()]

    if not any("<form" in edits.get(p, files[p]) for p in tree):
        home = tree[0]
        wired = _wire_home(edits.get(home, files[home]))
        if wired is not None and FORM_COMPONENT not in files:
            lang = "pt" if PT_BRANCH_RX.search(branch) else "es"
            comp = _build_form(_tokens(files, tree, header), TEXTS[lang],
                               _find_phone(files, tree, header))
            actions.append({"type": "create", "path": FORM_COMPONENT,
                            "content": comp})
            edits[home] = wired
            actions = [a for a in actions if a["path"] != home]
            actions.append({"type": "edit", "path": home, "content": wired})
    return actions
