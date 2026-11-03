"""Кукі-банер на Vue-вайтах (checks/cookie_consent_vue)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, load_check                          # noqa: E402

mod = load_check("cookie_consent_vue")

APP = ("<template>\n  <div id=\"app\">\n    <MainNavigation />\n    <router-view />\n    <Footer />\n  </div>\n</template>\n\n"
       "<script>\nimport MainNavigation from '@/components/MainNavigation.vue'\nimport Footer from '@/components/Footer.vue'\n\n"
       "export default {\n  name: 'App',\n  components: { MainNavigation, Footer }\n}\n</script>\n")
FOOTER = ('<template><footer><a href="/" class="font-sans text-2xl">Homtud</a>'
          '<a href="/#form" class="inline-block px-8 py-4 bg-emerald-500 hover:bg-emerald-600 text-white rounded-2xl transition-colors font-sans">CTA</a>'
          '<a href="/#form" class="inline-block px-8 py-4 bg-emerald-500 hover:bg-emerald-600 text-white rounded-2xl transition-colors font-sans">CTA2</a>'
          '</footer></template>\n')
PAGES = ('export const pages = [\n  {\n    "id": "home",\n    "route": "/",\n    "category": "main"\n  },\n'
         '  {\n    "id": "cookies",\n    "name": "Politika kolačića",\n    "route": "/politika-kolacica",\n    "category": "legal"\n  }\n]\n')
BASE = {"index.html": '<html lang="hr"><head><title>Homtud</title></head><body><div id="app"></div></body></html>',
        "src/App.vue": APP, "src/components/Footer.vue": FOOTER, "src/data/pages.js": PAGES,
        "src/pages/Cookies.vue": "<template><div><CookiePolicy/></div></template>",
        "src/components/CookiePolicy.vue": "<template><main><h1>Politika kolačića</h1><button @click=\"save\">Spremi</button></main></template>\n<script setup>\nconst save = () => localStorage.setItem('cookie_consent', '1')\n</script>\n"}
BR = "nwf-homtud-ficemvi-hr-hr"


def test_missing_banner_is_flagged_and_added_in_branch_style_and_language():
    files = dict(BASE)
    issues = mod.run_branch(dict(files), list(files), BR)
    assert len(issues) == 1 and issues[0]["path"] == "src/App.vue" and "кукі-банера" in issues[0]["message"], issues
    acts = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), BR)}
    assert set(acts) == {"src/components/CookieConsentBanner.vue", "src/App.vue"}, acts.keys()
    vue = acts["src/components/CookieConsentBanner.vue"]
    # мова вітки (hr з <html lang>), лінк на сторінку cookies з pages.js
    assert "Koristimo kolačiće" in vue and ">Prihvati</button>" in vue and ">Odbij</button>" in vue
    assert "policy: '/politika-kolacica'" in vue
    # кнопка — у стилях вітки (Tailwind CTA футера), падінг компактний; «Відхилити» без заливки
    assert 'class="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-2xl transition-colors font-sans" @click="choose(true)"' in vue
    assert 'bg-emerald-500' not in vue.split('choose(false)')[0].rsplit("<button", 1)[1]
    # SSR-safe: window лише в mounted, v-if по стану, localStorage
    assert 'v-if="show"' in vue and "mounted()" in vue and "localStorage" in vue and "data-wp-consent=\"banner\"" in vue
    assert "window" not in vue.split("mounted()")[0]
    app = acts["src/App.vue"]
    assert "<router-view />\n    <CookieConsentBanner />" in app
    assert "import CookieConsentBanner from '@/components/CookieConsentBanner.vue'" in app
    assert "components: { MainNavigation, Footer, CookieConsentBanner }" in app
    fixed = {**files, **acts}
    assert mod.run_branch(dict(fixed), list(fixed), BR) == []
    assert mod.fix_branch(dict(fixed), list(fixed), BR) == []


def test_language_falls_back_to_branch_locale_and_named_button_class_wins():
    files = dict(BASE)
    files["index.html"] = '<html><head></head><body><div id="app"></div></body></html>'
    files["src/components/Footer.vue"] = '<template><footer><a href="/x" class="av-btn">Mais</a><a class="av-btn av-btn--line" href="/y">Ver</a></footer></template>\n'
    vue = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), "nwf-x-br-pt")}["src/components/CookieConsentBanner.vue"]
    assert "Usamos cookies" in vue and ">Aceitar</button>" in vue
    assert 'class="av-btn" @click="choose(true)"' in vue and 'class="av-btn av-btn--line" @click="choose(false)"' in vue


def test_existing_banner_not_mounted_in_app_is_flagged_but_policy_page_alone_is_not_a_banner():
    files = dict(BASE)
    # сторінка політики з кнопкою «Spremi» — не банер → все ще error про відсутність
    assert len(mod.run_branch(dict(files), list(files), BR)) == 1
    files["src/components/LgpdBar.vue"] = ('<template><div v-if="open" class="fixed bottom-0">Koristimo kolačiće. '
                                           '<button @click="ok">Prihvati</button></div></template>\n<script>\nexport default { methods: { ok() { localStorage.setItem("c", "1") } } }\n</script>\n')
    issues = mod.run_branch(dict(files), list(files), BR)
    assert len(issues) == 1 and "не підключений у src/App.vue" in issues[0]["message"], issues
    files["src/App.vue"] = APP.replace("<router-view />", "<router-view />\n    <LgpdBar />")
    assert mod.run_branch(dict(files), list(files), BR) == []
    assert mod.fix_branch(dict(files), list(files), BR) == []


def test_script_setup_app_gets_import_without_components_block():
    files = dict(BASE)
    files["src/App.vue"] = ("<template>\n  <div>\n    <router-view />\n  </div>\n</template>\n\n"
                            "<script setup>\nimport Footer from '@/components/Footer.vue'\n</script>\n")
    app = {a["path"]: a["content"] for a in mod.fix_branch(dict(files), list(files), BR)}["src/App.vue"]
    assert app.startswith("<template>\n  <div>\n    <router-view />\n    <CookieConsentBanner />")
    assert "<script setup>\nimport CookieConsentBanner from '@/components/CookieConsentBanner.vue'\nimport Footer" in app
    assert "components:" not in app


if __name__ == "__main__":
    run(dict(globals()))
