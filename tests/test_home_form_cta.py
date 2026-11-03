"""Тести home_form_cta: CTA головної/хедера ведуть на форму, форма існує.

Фікстура — мінімальна vue-вітка сім'ї nwf: роутер із path:'/', App.vue з
хедером/футером, головна з герой-секцією і форм-компонентом. Кейси зняті з
живих віток: `nwf-vipi-plegi-co-es` (усі CTA href="/", форми немає) проти
донора `nwf-gascau-and-asimietej-abofasiq-ar-es` (CTA /#form, форма з id).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import load_check, run  # noqa: E402

hf = load_check("home_form_cta")

ROUTER = """
import { createRouter, createWebHistory } from 'vue-router'
export const routes = [
  { path: '/', name: 'home', component: () => import('@/pages/Home.vue') },
  { path: '/sobre-nosotros', name: 'about', component: () => import('@/pages/About.vue') }
]
const router = createRouter({ history: createWebHistory(), routes })
export default router
"""

APP = """
<template><div><SiteHeader /><router-view /><SiteFooter /></div></template>
<script>
import SiteHeader from '@/components/SiteHeader.vue'
import SiteFooter from '@/components/SiteFooter.vue'
export default { components: { SiteHeader, SiteFooter } }
</script>
"""

HEADER = """
<template>
  <header>
    <a href="/" class="logo"><img src="/logo.svg" alt="Site"><span>Site</span></a>
    <nav><a v-for="page in mainPages" :key="page.id" :href="page.route">{{ page.name }}</a></nav>
    <a href="/#form" class="bg-violet-500">Agendar visita</a>
  </header>
</template>
"""

FOOTER = """
<template><footer><a href="/">Brand Name</a></footer></template>
"""

HOME = """
<template><div><HeroHome /><LeadFormHome /></div></template>
<script>
import HeroHome from '@/components/HeroHome.vue'
import LeadFormHome from '@/components/LeadFormHome.vue'
export default { components: { HeroHome, LeadFormHome } }
</script>
"""

HERO = """
<template><section><a href="/#form" class="btn">Agendar visita gratuita</a></section></template>
"""

FORM = """
<template>
  <section id="form"><form><input name="name"><button type="submit">Enviar</button></form></section>
</template>
"""


def branch(**over):
    files = {
        "src/router/index.js": ROUTER,
        "src/App.vue": APP,
        "src/components/SiteHeader.vue": HEADER,
        "src/components/SiteFooter.vue": FOOTER,
        "src/pages/Home.vue": HOME,
        "src/components/HeroHome.vue": HERO,
        "src/components/LeadFormHome.vue": FORM,
        "src/pages/About.vue": "<template><div><a href=\"/\">CTA about</a></div></template>",
    }
    files.update(over)
    return files


def _run(files):
    return hf.run_branch(files, list(files), "test-branch")


def test_healthy_family_layout_is_clean():
    assert _run(branch()) == []


def test_dead_hero_cta_is_reported_with_its_file():
    files = branch(**{"src/components/HeroHome.vue":
                      '<template><a href="/" class="btn">Agendar visita</a></template>'})
    iss = _run(files)
    assert len(iss) == 1
    assert iss[0]["path"] == "src/components/HeroHome.vue"
    assert "мертвий CTA" in iss[0]["message"]
    assert "Agendar visita" in iss[0]["message"]


def test_dead_header_cta_is_reported_but_logo_is_not():
    hdr = HEADER.replace('href="/#form"', 'href="/"')
    iss = _run(branch(**{"src/components/SiteHeader.vue": hdr}))
    assert len(iss) == 1, iss
    assert iss[0]["path"] == "src/components/SiteHeader.vue"
    # лого (<a href="/" з <img>) не потрапило у знахідки
    assert "logo" not in iss[0]["message"]


def test_anchor_without_form_is_reported():
    """Кнопки обіцяють #form, а форм-компонента немає — головний кейс."""
    home = ('<template><div><HeroHome /></div></template>\n<script>\n'
            "import HeroHome from '@/components/HeroHome.vue'\n"
            "export default { components: { HeroHome } }\n</script>")
    files = branch(**{"src/pages/Home.vue": home})
    del files["src/components/LeadFormHome.vue"]
    iss = _run(files)
    msgs = " | ".join(i["message"] for i in iss)
    assert "#form" in msgs and "form" in msgs
    assert "<form> на головній відсутня" in msgs


def test_footer_and_other_pages_are_out_of_scope():
    """Футер (без <header>) і CTA на інших сторінках чек не чіпає."""
    assert _run(branch()) == []           # About.vue має href="/" — і тиша


def test_dynamic_nav_links_are_ignored():
    """Навігація на :href="page.route" — не літеральний href, не матчиться."""
    iss = _run(branch())
    assert all("page.route" not in i["message"] for i in iss) and iss == []


def test_hash_target_present_elsewhere_in_tree_is_clean():
    hero = '<template><a href="#servicios">Programas</a></template>'
    svc = '<template><section id="servicios">…</section></template>'
    home = HOME.replace("<LeadFormHome />", "<LeadFormHome /><ServiciosHome />") \
               .replace("import LeadFormHome from '@/components/LeadFormHome.vue'",
                        "import LeadFormHome from '@/components/LeadFormHome.vue'\n"
                        "import ServiciosHome from '@/components/ServiciosHome.vue'")
    files = branch(**{"src/components/HeroHome.vue": hero,
                      "src/pages/Home.vue": home,
                      "src/components/ServiciosHome.vue": svc})
    assert _run(files) == []


def test_hash_target_missing_is_reported():
    hero = '<template><a href="#servicios">Programas</a></template>'
    iss = _run(branch(**{"src/components/HeroHome.vue": hero}))
    assert len(iss) == 1
    assert '#servicios' in iss[0]["message"]



def test_next_react_branch_is_silent():
    """Тип «node» покриває і Next/React — там наші правила не діють.
    `createBrowserRouter` react-router'а НЕ матчиться на `createRouter(`,
    jsx-сторінки — не .vue; чек мусить мовчати, а не вигадувати знахідки."""
    files = {
        "src/router/index.js": (
            "import { createBrowserRouter } from 'react-router-dom'\n"
            "export const router = createBrowserRouter([\n"
            "  { path: '/', element: <Home /> },\n"
            "])"),
        "src/pages/Home.jsx": '<a href="/">Agendar visita</a>',
        "src/App.jsx": "export default function App() {}",
    }
    assert hf.run_branch(files, list(files), "next-branch") == []


def test_vue_router_but_non_vue_home_is_silent():
    """Роутер є, але головна не .vue — гейт мусить закритись."""
    files = {
        "src/router/index.js": (
            "import { createRouter } from 'vue-router'\n"
            "const r = createRouter({})\n"
            "export const routes = [{ path: '/', component: () => "
            "import('@/pages/Home.jsx') }]"),
        "src/pages/Home.jsx": '<a href="/">CTA</a>',
    }
    assert hf.run_branch(files, list(files), "hybrid-branch") == []


def test_cta_inside_home_page_itself_is_scanned():
    home = HOME.replace("<HeroHome />", '<a href="/">Solicitar cita</a><HeroHome />')
    iss = _run(branch(**{"src/pages/Home.vue": home}))
    assert len(iss) == 1 and iss[0]["path"] == "src/pages/Home.vue"


def test_branch_without_router_is_silent():
    assert hf.run_branch({"src/x.vue": "<template/>"}, ["src/x.vue"], "b") == []



# ------------------------------------------------------------------ автофікс
PAGES_JS = """
export const pages = [
  { "id": "home", "name": "Inicio", "route": "/", "nav": true },
  { "id": "about", "name": "Sobre nosotros", "route": "/sobre-nosotros", "nav": true },
  { "id": "process", "name": "Nuestro enfoque", "route": "/proceso", "nav": true }
]
"""

BROKEN_HERO = """
<template>
  <section class="bg-zinc-900 py-24 px-4">
    <h2 class="font-sans font-bold text-4xl text-zinc-100">Título</h2>
    <a href="/" class="inline-block px-10 py-4 bg-violet-500 hover:bg-violet-400 text-white rounded-xl transition-colors font-sans">Agendar visita gratuita</a>
    <a href="/" class="text-violet-500">Nuestro enfoque</a>
  </section>
</template>
"""

BROKEN_HEADER = HEADER.replace('href="/#form"', 'href="/"')

FOOTER_PHONE = """
<template><footer><a href="/">Brand</a><p>+57 3 5847 291</p></footer></template>
"""


def broken_branch(**over):
    home = ("<template>\n  <div>\n    <HeroHome />\n  </div>\n</template>\n"
            "<script>\n"
            "import HeroHome from '@/components/HeroHome.vue'\n"
            "export default {\n  name: 'HomePage',\n"
            "  components: { HeroHome }\n}\n</script>")
    files = branch(**{"src/pages/Home.vue": home,
                      "src/components/HeroHome.vue": BROKEN_HERO,
                      "src/components/SiteHeader.vue": BROKEN_HEADER,
                      "src/components/SiteFooter.vue": FOOTER_PHONE,
                      "src/data/pages.js": PAGES_JS})
    del files["src/components/LeadFormHome.vue"]
    files.update(over)
    return files


def _apply(files, actions):
    out = dict(files)
    for a in actions:
        out[a["path"]] = a["content"]
    return out


def test_fix_retargets_ctas_and_creates_the_form():
    files = broken_branch()
    actions = hf.fix_branch(files, list(files), "nwf-cagu-fedod-co-es")
    fixed = _apply(files, actions)
    # після фікса чек мовчить
    assert hf.run_branch(fixed, list(fixed), "nwf-cagu-fedod-co-es") == []
    hero = fixed["src/components/HeroHome.vue"]
    # форм-інтент — на /#form; текст, що називає сторінку, — на її роут
    assert 'href="/#form"' in hero and "Agendar visita gratuita" in hero
    assert 'href="/proceso"' in hero
    # хедер: CTA переадресовано, лого недоторкане
    hdr = fixed["src/components/SiteHeader.vue"]
    assert hdr.count('href="/#form"') == 1
    assert '<a href="/" class="logo">' in hdr


def test_generated_form_uses_the_branch_tokens():
    files = broken_branch()
    actions = hf.fix_branch(files, list(files), "nwf-cagu-fedod-co-es")
    comp = next(a for a in actions if a["type"] == "create")
    assert comp["path"] == "src/components/LeadFormHome.vue"
    t = comp["content"]
    assert 'id="form"' in t and "<form" in t
    # кнопка — дослівно клас CTA вітки (+ w-full), тема темна (zinc-800 картка)
    assert "bg-violet-500 hover:bg-violet-400" in t and "w-full" in t
    assert "rounded-xl" in t and "bg-zinc-800" in t
    # телефон підхоплено з футера, тексти іспанські
    assert "+57 3 5847 291" in t
    assert "Envíanos tu consulta" in t
    # Home.vue отримав імпорт і тег
    home = next(a for a in actions if a["path"] == "src/pages/Home.vue")
    assert "<LeadFormHome />" in home["content"]
    assert "import LeadFormHome from '@/components/LeadFormHome.vue'" in home["content"]
    assert re.search(r"components:\s*\{[^}]*LeadFormHome", home["content"])


def test_pt_branch_gets_pt_texts():
    for branch in ("nwf-quinta-br-pt", "nwf-quinta-br-pt-2"):   # -2 — номер партії
        files = broken_branch()
        actions = hf.fix_branch(files, list(files), branch)
        t = next(a for a in actions if a["type"] == "create")["content"]
        assert "Envie sua mensagem" in t and "Preencha o formulário" in t, branch


def test_fix_is_idempotent():
    files = broken_branch()
    fixed = _apply(files, hf.fix_branch(files, list(files), "b-co-es"))
    assert hf.fix_branch(fixed, list(fixed), "b-co-es") == []


def test_fix_on_healthy_branch_returns_nothing():
    assert hf.fix_branch(branch(), list(branch()), "ok-co-es") == []


if __name__ == "__main__":
    run(dict(globals()))
