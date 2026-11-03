"""Чому не зібрався node-вайт — причина, а не хвіст стеку.

30.09 о 15:56 колега: «у колеги вайти не деплояться», скрін тосту:

    build: r-5d22b9162b/node_modules/@vue/compiler-core/dist/
    compiler-core.cjs.prod.js:3033:13) at Object.parse (…) … at
    transformMain (…/@vitejs/plugin-vue/dist/index.cjs:2434:34)[39m

Причина — зайвий `</div>` у Footer.vue вітки nwf-dijikesdkah-br-pt,
закомічений руками через редактор лаби о 15:51 (коміт dfe2789c; за весь
період 21.09–30.09 це єдиний .vue з 4056 змінених, що не парситься). Vite
друкує і повідомлення, і `file:` — але за ~1.5 КБ до кінця виводу, далі
десять кадрів стеку, а `_run_npm` брав сліпий хвіст [-800:], і
`_nuxt_worker` з нього ще [-600:]. У тост потрапляли рівно кадри.

Фікстури нижче — справжній вивід `npm run generate` тих самих версій
(vite 5.4.21, @vitejs/plugin-vue — рядки 84:43 і 2434:34 збігаються зі
скріном), зібраний на копії вітки; шлях builder-а — продовий.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ІЗОЛЯЦІЯ ДО ПЕРШОГО ІМПОРТУ: `_nuxt_worker` рахує ключ від проєкту, а
# корінь стану за замовчуванням — робоче дерево
_TMP = tempfile.mkdtemp(prefix="qa_lab-build-error-")
os.environ["QA_LAB_STATE_DIR"] = _TMP

from _harness import ROOT, run                                    # noqa: E402

import projects                                                   # noqa: E402

projects.init()

import deployer                                                   # noqa: E402

B = "/app/var/projects/vue/builder-5d22b9162b"

_PREAMBLE = (
    "\n"
    "> generated-project@1.0.0 generate\n"
    "> vite build && node scripts/inject-php.cjs\n"
    "\n"
    "\x1b[33mThe CJS build of Vite's Node API is deprecated. See https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.\x1b[39m\n"
    "\x1b[36mvite v5.4.21 \x1b[32mbuilding for production...\x1b[36m\x1b[39m\n"
    "transforming...\n"
    "(node:62907) [MODULE_TYPELESS_PACKAGE_JSON] Warning: Module type of file://%B%/postcss.config.js is not specified and it doesn't parse as CommonJS.\n"
    "Reparsing as ES module because module syntax was detected. This incurs a performance overhead.\n"
    'To eliminate this warning, add "type": "module" to %B%/package.json.\n'
    "(Use `node --trace-warnings ...` to show where the warning was created)\n"
)

# кейс 30.09 — повністю, байт-у-байт
VUE_TEMPLATE = (_PREAMBLE + (
    "\x1b[32m✓\x1b[39m 9 modules transformed.\n"
    "\x1b[31mx\x1b[39m Build failed in 474ms\n"
    "\x1b[31merror during build:\n"
    "\x1b[31m[vite:vue] [plugin vite:vue] src/components/Footer.vue (34:9): Invalid end tag.\x1b[31m\n"
    "file: \x1b[36m%B%/src/components/Footer.vue:34:9\x1b[31m\n"
    "SyntaxError: [plugin vite:vue] src/components/Footer.vue (34:9): Invalid end tag.\n"
    "    at createCompilerError (%B%/node_modules/@vue/compiler-core/dist/compiler-core.cjs.prod.js:1374:17)\n"
    "    at emitError (%B%/node_modules/@vue/compiler-core/dist/compiler-core.cjs.prod.js:3001:5)\n"
    "    at Object.onclosetag (%B%/node_modules/@vue/compiler-core/dist/compiler-core.cjs.prod.js:2408:9)\n"
    "    at Tokenizer.stateInClosingTagName (%B%/node_modules/@vue/compiler-core/dist/compiler-core.cjs.prod.js:799:16)\n"
    "    at Tokenizer.parse (%B%/node_modules/@vue/compiler-core/dist/compiler-core.cjs.prod.js:1157:16)\n"
    "    at Object.baseParse (%B%/node_modules/@vue/compiler-core/dist/compiler-core.cjs.prod.js:3033:13)\n"
    "    at Object.parse (%B%/node_modules/@vue/compiler-dom/dist/compiler-dom.cjs.prod.js:668:23)\n"
    "    at Object.parse$1 [as parse] (%B%/node_modules/@vue/compiler-sfc/dist/compiler-sfc.cjs.js:1918:24)\n"
    "    at createDescriptor (%B%/node_modules/@vitejs/plugin-vue/dist/index.cjs:84:43)\n"
    "    at transformMain (%B%/node_modules/@vitejs/plugin-vue/dist/index.cjs:2434:34)\x1b[39m\n"
)).replace("%B%", B)

# синтаксична помилка у <script setup>: vite дає кадр коду — він цінний
VUE_SCRIPT = (_PREAMBLE + (
    "\x1b[32m✓\x1b[39m 9 modules transformed.\n"
    "\x1b[31mx\x1b[39m Build failed in 740ms\n"
    "\x1b[31merror during build:\n"
    "\x1b[31m[vite:vue] [vue/compiler-sfc] Unexpected token (4:0)\n"
    "\n"
    "%B%/src/components/Footer.vue\n"
    "37 |  <script setup>\n"
    "38 |  import { mainPages, legalPages } from '@/data/pages.js'\n"
    "39 |  const broken = {\n"
    "   |                   ^\n"
    "40 |  </script>\n"
    "   |  ^\n"
    "41 |  \x1b[31m\n"
    "file: \x1b[36m%B%/src/components/Footer.vue:4:0\x1b[31m\n"
    "    at constructor (%B%/node_modules/@babel/parser/lib/index.js:369:19)\n"
    "    at Parser.raise (%B%/node_modules/@babel/parser/lib/index.js:6622:19)\n"
    "    at Parser.unexpected (%B%/node_modules/@babel/parser/lib/index.js:6642:16)\x1b[39m\n"
)).replace("%B%", B)

UNRESOLVED = (_PREAMBLE + (
    "\x1b[32m✓\x1b[39m 62 modules transformed.\n"
    "\x1b[31mx\x1b[39m Build failed in 1.19s\n"
    "\x1b[31merror during build:\n"
    '\x1b[31mCould not resolve "./Missing.vue" from "src/components/Footer.vue"\x1b[31m\n'
    "file: \x1b[36m%B%/src/components/Footer.vue\x1b[31m\n"
    "    at getRollupError (file://%B%/node_modules/rollup/dist/es/shared/parseAst.js:319:41)\n"
    "    at file://%B%/node_modules/rollup/dist/es/shared/node-entry.js:22419:26\x1b[39m\n"
)).replace("%B%", B)

# vite зібрав, упав постбілд: перед крешем — кілобайти таблиці файлів
POSTBUILD = (_PREAMBLE + (
    "\x1b[32m✓\x1b[39m 150 modules transformed.\n"
    "rendering chunks...\n"
    "computing gzip size...\n"
    "\x1b[2mdist/\x1b[22m\x1b[32mindex.html                        \x1b[39m\x1b[1m\x1b[2m  2.10 kB\x1b[22m\x1b[1m\x1b[22m\x1b[2m │ gzip:  0.77 kB\x1b[22m\n"
    + "\x1b[2mdist/\x1b[22m\x1b[2massets/\x1b[22m\x1b[32m2fe99e93-BvuDA5B8.jpg      \x1b[39m\x1b[1m\x1b[2m 28.58 kB\x1b[22m\x1b[1m\x1b[22m\n" * 40 +
    "\x1b[2mdist/\x1b[22m\x1b[2massets/\x1b[22m\x1b[36mindex-BxzTL0L6.js          \x1b[39m\x1b[1m\x1b[2m100.67 kB\x1b[22m\x1b[1m\x1b[22m\x1b[2m │ gzip: 39.36 kB\x1b[22m\n"
    "\x1b[32m✓ built in 3.66s\x1b[39m\n"
    "%B%/scripts/inject-php.cjs:1\n"
    'throw new Error("inject-php: no index.html in dist");\n'
    "^\n"
    "\n"
    "Error: inject-php: no index.html in dist\n"
    "    at Object.<anonymous> (%B%/scripts/inject-php.cjs:1:7)\n"
    "    at Module._compile (node:internal/modules/cjs/loader:1529:14)\n"
    "    at node:internal/main/run_main_module:28:49\n"
    "\n"
    "Node.js v20.19.0\n"
)).replace("%B%", B)

NPM_INSTALL = (
    "npm warn deprecated whatwg-encoding@3.1.1: Use @exodus/bytes instead\n"
    "npm error code ETARGET\n"
    "npm error notarget No matching version found for vite@^9.0.0.\n"
    "npm error notarget In most cases you or one of your dependencies are requesting\n"
    "npm error notarget a package version that doesn't exist.\n"
    "npm error A complete log of this run can be found in: /root/.npm/_logs/2026-09-30T13_00_00_000Z-debug-0.log\n"
)


def _clean(msg: str):
    assert "\x1b" not in msg and "[39m" not in msg, msg
    assert B not in msg, "абсолютний шлях builder-а людині нічого не каже"
    assert "    at " not in msg, f"кадри стеку не прибрано:\n{msg}"


# ------------------------------------------------- кейс 30.09

def test_fixture_reproduces_the_toast_of_30_09():
    """Фікстура справжня: старий ланцюжок [-800:][-600:] дає рівно скрін."""
    old = VUE_TEMPLATE[-800:][-600:]
    assert old.startswith("r-5d22b9162b/node_modules/@vue/compiler-core/dist/"
                          "compiler-core.cjs.prod.js:3033:13)"), old[:80]
    assert "Invalid end tag" not in old and "Footer.vue" not in old


def test_template_error_names_the_file_line_and_reason():
    msg = deployer._npm_error(VUE_TEMPLATE, Path(B))
    assert msg.splitlines()[0] == ("[vite:vue] [plugin vite:vue] "
                                   "src/components/Footer.vue (34:9): Invalid end tag."), msg
    assert "file: src/components/Footer.vue:34:9" in msg, msg
    _clean(msg)


def test_repeated_message_from_the_stack_is_dropped():
    """Перший рядок err.stack («SyntaxError: …») — той самий текст ще раз."""
    msg = deployer._npm_error(VUE_TEMPLATE, Path(B))
    assert msg.count("Invalid end tag") == 1, msg
    assert len(msg) < 200, msg


def test_worker_keeps_the_head_of_the_error():
    """Голову, а не хвіст: причину _npm_error кладе першою, а довгий кадр коду
    чи хвіст npm під старим [-600:] з'їли б саме її."""
    long = "npm run generate упав:\n" + "src/x.vue (1:1): Invalid end tag.\n" + "кадр\n" * 400

    def boom(*a, **kw):
        raise RuntimeError(long)

    orig = deployer._nuxt_build
    deployer._nuxt_build = boom
    try:
        deployer._nuxt_worker("nwf-x-br-pt", None, Path(_TMP), Path(_TMP), Path(_TMP))
    finally:
        deployer._nuxt_build = orig
    st = deployer.build_status("nwf-x-br-pt")
    assert st["status"] == "error", st
    assert st["error"].startswith("npm run generate упав:\nsrc/x.vue (1:1): Invalid end tag."), st


# ------------------------------------------------- інші поломки білду

def test_script_syntax_error_keeps_the_code_frame():
    msg = deployer._npm_error(VUE_SCRIPT, Path(B))
    assert msg.startswith("[vite:vue] [vue/compiler-sfc] Unexpected token (4:0)"), msg
    assert "39 |  const broken = {" in msg, "кадр коду показує, ДЕ саме"
    assert "file: src/components/Footer.vue:4:0" in msg, msg
    _clean(msg)


def test_unresolved_import():
    msg = deployer._npm_error(UNRESOLVED, Path(B))
    assert msg.splitlines() == ['Could not resolve "./Missing.vue" from "src/components/Footer.vue"',
                                "file: src/components/Footer.vue"], msg


def test_postbuild_crash_starts_at_the_crash():
    """Постбілд падає ПІСЛЯ успішного vite — таблиця файлів у 40+ рядків
    не має витісняти сам креш."""
    msg = deployer._npm_error(POSTBUILD, Path(B))
    assert msg.startswith("scripts/inject-php.cjs:1\n"), msg
    assert "Error: inject-php: no index.html in dist" in msg, msg
    assert " kB" not in msg and "vite v5" not in msg, msg
    _clean(msg)


def test_npm_install_error_keeps_the_tail():
    msg = deployer._npm_error(NPM_INSTALL, Path(B))
    assert "No matching version found for vite@^9.0.0." in msg, msg
    assert msg.endswith("debug-0.log"), msg


def test_limit_holds_for_huge_output():
    msg = deployer._npm_error("npm error рядок\n" * 5000, Path(B), limit=300)
    assert 0 < len(msg) <= 300, len(msg)


# ------------------------------------------------- проводка до _run_npm

def test_run_npm_raises_with_the_reason():
    """Справжній subprocess: фейковий npm друкує вивід 30.09 зі СВОГО cwd."""
    if os.name == "nt":
        return                                   # шебанг — лише POSIX
    tmp = Path(tempfile.mkdtemp(prefix="qa_lab-fake-npm-"))
    fixture = tmp / "out.txt"
    fixture.write_text(VUE_TEMPLATE.replace(B, "@CWD@"), encoding="utf-8")
    fake = tmp / "npm"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        f"out = open({str(fixture)!r}, encoding='utf-8').read()\n"
        "sys.stdout.write(out.replace('@CWD@', os.getcwd()))\n"
        "sys.exit(1)\n", encoding="utf-8")
    fake.chmod(0o755)
    builder = tmp / "builder-5d22b9162b"
    builder.mkdir()
    old = os.environ.get("NPM_BIN")
    os.environ["NPM_BIN"] = str(fake)
    try:
        deployer._run_npm(["run", "generate"], builder, timeout=60)
    except RuntimeError as e:
        msg = str(e)
    else:
        raise AssertionError("npm з кодом 1 мусить кинути")
    finally:
        if old is None:
            os.environ.pop("NPM_BIN", None)
        else:
            os.environ["NPM_BIN"] = old
    assert msg.startswith("npm run generate упав:\n[vite:vue]"), msg
    assert "file: src/components/Footer.vue:34:9" in msg, msg
    assert str(builder) not in msg, msg


# ------------------------------------------- не-node вітка в node-проєкті

def _node_project_with(branch: str, files: dict) -> Path:
    """node-проєкт з коренем у _TMP і синхронізований знімок вітки."""
    root = Path(_TMP) / "projects" / "vue"
    projects._registry["vue"] = {"id": "vue", "title": "node", "type": "node",
                                 "gitlab_path": "x/z", "token": "t",
                                 "mock": True, "root": root}
    snap = root / "cache" / branch
    snap.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        (snap / rel).write_text(text, encoding="utf-8")
    return snap


def test_node_project_builds_only_branches_with_package_json():
    """26.10, baggoetiepohsa-rekivo.com.br-br-pt: у new-white-front 165 віток
    без package.json (php/статичні). Деплой гнав їх у npm, той знаходив
    /app/package.json лаби — тост «Missing script: "generate"». Без
    package.json — деплой як php (файли як є, $isDev → true), npm не
    викликається; з package.json — як і раніше npm-білд у dist/."""
    npm_calls, served = [], []

    def fake_npm(args, cwd, timeout):
        npm_calls.append(args[:2])
        if args[:2] == ["run", "generate"]:
            (cwd / "dist").mkdir(exist_ok=True)
            (cwd / "dist" / "index.html").write_text("<p>vue</p>", encoding="utf-8")

    def fake_serve(branch, docroot, router=None, **extra):
        served.append(Path(docroot))
        return {"branch": branch, "port": 0, "url": "", **extra}

    php_site = "baggoetiepohsa-rekivo.com.br-br-pt"
    _node_project_with(php_site, {"index.php": "<?php $isDev = false; ?><p>oi</p>",
                                  "index.html": "<p>oi</p>"})
    _node_project_with("nwf-x-br-pt", {"package.json": '{"scripts": {"generate": "vite build"}}'})
    saved = (deployer._run_npm, deployer._serve, deployer._php_available)
    deployer._run_npm, deployer._serve = fake_npm, fake_serve
    deployer._php_available = lambda: True
    try:
        with projects.use("vue"):
            info = deployer.deploy(php_site)
            assert npm_calls == [], f"npm для вітки без package.json: {npm_calls}"
            assert served[-1] == deployer.deploy_root() / php_site, served
            assert "$isDev = true" in (served[-1] / "index.php").read_text(encoding="utf-8")
            assert info["isdev_patched"] == 1, info
            # з package.json — npm-білд, віддається dist/
            deployer.deploy("nwf-x-br-pt", wait=True)
            assert [c for c in npm_calls if c == ["run", "generate"]], npm_calls
            assert served[-1] == deployer.deploy_root() / "nwf-x-br-pt" / "dist", served
            # npm напряму на вітці без package.json — відмова ДО npm
            npm_calls.clear()
            try:
                deployer._nuxt_compile(php_site)
            except RuntimeError as e:
                assert "package.json" in str(e), e
            else:
                raise AssertionError("npm-білд без package.json мусить відмовити")
            assert npm_calls == [], npm_calls
    finally:
        deployer._run_npm, deployer._serve, deployer._php_available = saved
        projects._registry.pop("vue", None)


if __name__ == "__main__":
    run(dict(globals()))
