"""Форма vue-вайта: сабміт має долітати, а сторінка подяки — відкриватись.

Дві поломки одного потоку. Обидві зміряні на живому деплої
(`nwf-premaghou-br-pt`, php-деплой лаби), а не виведені з коду.

1. **`<form method="POST">`.** Інжектований у `dist/index.php` блок ловить
   лід з `$_GET` (`if (isset($_GET['email']) || isset($_GET['name']))`), а
   POST кладе поля в тіло запиту. Заміряно:

       curl -X POST /  --data "name=QA&email=qa@test.dev"   → 0 редіректів
       curl     "/?name=QA&email=qa@test.dev"               → редірект є

   Тобто з `method="POST"` не спрацьовує НІЩО: ні пікселі, ні перехід на
   подяку — лід просто зникає. Форма без `method` шле GET, і все працює.
   Це та сама причина, з якої php-вайтам знімає `action`/`method` чек
   `forms`; тут те саме, але у `.vue`-компонентах.

2. **`$returnPage .= '.html'` у `scripts/inject-php.cjs`.** Після сабміту
   скрипт робить `window.location.href = '/$returnPage'`. Дефолт —
   `'obrigado'`/`'confirmacao'`/`'thanks'`, і блок дописує до нього `.html`.
   Але вайт це SPA: роутер знає `/obrigado`, а файлу `obrigado.html` немає
   **у жодній з 305 віток корпусу**. У браузері `/obrigado.html` — порожня
   сторінка (шапка + футер, `<h1>` немає, 439 символів тексту),
   `/obrigado` — справжня подяка «Obrigado pelo seu interesse!» (682).

   Виправлення — те, що вже стоїть у 135 віток корпусу з 305: суфікс
   зводиться до порожнього рядка, блок стає no-op, а редірект іде на
   чистий роут. Дефолтну назву сторінки не чіпаємо: чи існує вона взагалі —
   це інший чек (`thanks_route`).
"""
import re

import checks.form_stub as _form_stub

NAME = "Форма: сабміт і повернення на подяку"
GROUP = "auto"     # корпус 305 віток з inject-php.cjs: 170 з суфіксом '.html'
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
                   # (у 135 його вже прибрано вручну — це і є цільовий вигляд),
                   # 170 форм з method="POST" у .vue, action= — 0.
                   # Після автофікса не лишається жодного спрацювання
PROJECTS = ["node"]
DESCRIPTION = ("Дві поломки потоку форми: method=\"POST\" (інжектований php "
               "читає $_GET, з POST лід не зараховується взагалі) і суфікс "
               "'.html' у scripts/inject-php.cjs (редірект іде на "
               "/obrigado.html, якого у SPA немає — порожня сторінка). "
               "Автофікс знімає method/action і зводить суфікс до ''.")
FILES = ["scripts/inject-php.cjs", "package.json", "*.vue"]

INJECT_PATH = "scripts/inject-php.cjs"
PKG_PATH = "package.json"

# Чому суфікс зводиться до '' і коли цього робити НЕ можна.
#
# У кожній вітці два білди, і вони дають різне дерево:
#   generate     = vite build && node scripts/inject-php.cjs  → чистий SPA:
#                  один index.html, роути лише клієнтські;
#   build:static = vite-ssg build  (+ ssgOptions.dirStyle='flat' у vite.config)
#                  → ПЛОСКІ файли на роут: obrigado.html, thanks.html.
# Саме тому в одному деплої працює `/obrigado`, а в іншому — `/obrigado.html`:
# різниця не в коді вітки, а в тому, ЯКИЙ білд поїхав.
#
# Вирішальне: `inject-php.cjs` викликається ТІЛЬКИ з `generate` — у
# `build:static` його немає (звірено: 305 з 305 віток). Тобто php-преамбула з
# `$returnPage` фізично існує лише у SPA-білді, де плоских html немає і суфікс
# мусить бути порожній. Тому зведення до '' безпечне — але не «завжди»:
# якщо генератор колись переведе `generate` на `vite-ssg`, плоскі файли
# зʼявляться, і тоді `.html` стане ОБОВʼЯЗКОВИМ. На цей випадок є гард нижче:
# бачимо ssg у `generate` — суфікс не чіпаємо (перевірено на 6 живих сайтах:
# зараз усюди `/slug` показує подяку, а `/slug.html` — порожню шапку з футером).
FLAT_BUILD_RX = re.compile(r"vite-ssg|ssgOptions|dirStyle")

# Блок суфікса: пробіли, лапки й переноси в корпусі різні, тому все гнучке.
# Групи 1/3 — самі літерали (їх і зануляємо), щоб решта рядка лишилась як є.
SUFFIX_RX = re.compile(
    r"""(?P<head>if\s*\(\s*!\s*str_ends_with\s*\(\s*\$returnPage\s*,\s*)
        (?P<q1>['"])(?P<s1>[^'"]*)(?P=q1)
        (?P<mid>\s*\)\s*\)\s*\{\s*\$returnPage\s*\.=\s*)
        (?P<q2>['"])(?P<s2>[^'"]*)(?P=q2)""",
    re.X)

FORM_RX = re.compile(r"""<form\b(?:[^>"']|"[^"]*"|'[^']*')*>""", re.I)
# атрибут разом із пробілом ПЕРЕД ним — щоб не лишалось подвійних пробілів
ATTR_RX = re.compile(r"""\s+(?:method|action)\s*=\s*(?:"[^"]*"|'[^']*')""", re.I)
ATTR_NAME_RX = re.compile(r"""\b(method|action)\s*=""", re.I)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _suffix_hits(text: str):
    for m in SUFFIX_RX.finditer(text):
        if m.group("s1") or m.group("s2"):
            yield m


def _flat_build(files: dict) -> bool:
    """Чи `generate` збирає ПЛОСКІ html на роут (тоді `.html` обовʼязковий).

    Дивимось саме на скрипт `generate`, бо лише він запускає inject-php.cjs.
    Наявність `build:static` поруч ні до чого: той білд php-преамбули не
    створює взагалі, тож суфікс у ній йому не належить."""
    import json
    raw = files.get(PKG_PATH)
    if not raw:
        return False
    try:
        gen = ((json.loads(raw).get("scripts") or {}).get("generate") or "")
    except Exception:
        return False
    return bool(FLAT_BUILD_RX.search(gen))


def _form_hits(text: str):
    for m in FORM_RX.finditer(text):
        names = [n.lower() for n in ATTR_NAME_RX.findall(m.group(0))]
        if names:
            yield m, names


def run_branch(files, all_paths):
    if any(_form_stub.is_stubbed(t) for p, t in files.items() if p.lower() in ("index.php", "index.html")):
        return []                       # форма-заглушка (form_stub): штатний флоу вимкнено свідомо
    flat = _flat_build(files)
    issues = []
    for path in sorted(files):
        text = files[path]
        if path == INJECT_PATH and not flat:
            for m in _suffix_hits(text):
                issues.append({
                    "path": path, "line": _line(text, m.start()), "severity": "error",
                    "message": f"після сабміту редірект іде на "
                               f"'<сторінка>{m.group('s2') or m.group('s1')}' — "
                               f"у SPA такої сторінки немає (роутер знає чистий "
                               f"шлях), відкриється порожня; фікс зведе суфікс до ''"})
        elif path.endswith(".vue"):
            for m, names in _form_hits(text):
                issues.append({
                    "path": path, "line": _line(text, m.start()), "severity": "error",
                    "message": f"у <form> стоїть {'/'.join(sorted(set(names)))}= — "
                               f"інжектований php читає лід з $_GET, а POST кладе "
                               f"поля в тіло: ні пікселів, ні переходу на подяку; "
                               f"фікс прибере атрибут"})
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    if any(_form_stub.is_stubbed(t) for p, t in files.items() if p.lower() in ("index.php", "index.html")):
        return []                       # форма-заглушка (form_stub)
    flat = _flat_build(files)
    actions = []
    for path in sorted(files):
        text = files[path]
        if path == INJECT_PATH:
            if flat:
                continue                   # плоскі html на роут — '.html' потрібен
            new = SUFFIX_RX.sub(
                lambda m: (m.group("head") + m.group("q1") + m.group("q1")
                           + m.group("mid") + m.group("q2") + m.group("q2")), text)
        elif path.endswith(".vue"):
            new = FORM_RX.sub(lambda m: ATTR_RX.sub("", m.group(0)), text)
        else:
            continue
        if new != text:
            actions.append({"type": "edit", "path": path, "content": new})
    return actions
