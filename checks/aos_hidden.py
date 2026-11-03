"""AOS: анімований текст лишається невидимим назавжди.

Кейс `rusveve-ar-es/index.php`: `aos.css` (рядок 61) містить
`[data-aos^="fade"]{opacity:0}` — і так для `fade-*`, `zoom-*`, `flip-*`,
`slide-*`. Прозорість знімає лише `AOS.init()`, дописуючи класи
`aos-init aos-animate`. Інлайновий виклик у вітці стоїть на рядку 1063,
а `<script src="…/aos.js">`, що визначає глобал `AOS`, — лише на 1067,
ПІСЛЯ. У момент виконання `typeof AOS === 'undefined'`, гард
`if (typeof AOS !== 'undefined') { AOS.init(...) }` мовчки пропускає
ініціалізацію — і елементи лишаються з `opacity: 0` назавжди (виміряно
в headless Chrome; після ручного `AOS.init()` у консолі — `opacity: 1`,
класи `aos-init aos-animate` з'являються).

Масштаб (скан кешу): такий самий гард `typeof AOS !== 'undefined'` є ще
у 9 вітках — і скрізь, крім `rusveve-ar-es`, порядок правильний, чек
мовчить. Окремо є вітки (`cadebok-mesxif-sg-eng` і інші), де `data-aos`
стоїть у html, а `AOS.init` лежить в `assets/js/main.js` — це нормальна
конвенція, а не дефект; тому `FILES` включає `*.js`, інакше такі вітки
дали б фолс-спрацювання «init немає ніде».

Що ловимо (тільки коли на сторінці є `data-aos="fade…|zoom…|flip…|slide…"`
і підключений `aos.css` — саме ці префікси в aos.css дають `opacity:0`):
  * `AOS.init(` немає в жодному html/js файлі вітки;
  * `AOS.init(` є, але в тому самому файлі стоїть РАНІШЕ за
    `<script src=…aos….js>` — до завантаження ліби `AOS` ще не існує.

Автофікс (fix_branch) мінімальний і оборотний:
  * порядок переплутано — тег `<script src=…aos….js>` вирізається зі
    свого місця і вставляється прямо перед `<script>`-блоком з
    `AOS.init`;
  * init відсутній зовсім — одразу після тегу ліби дописується
    `<script>AOS.init({ once: true });</script>`.
"""
import re

NAME = "AOS: анімований текст лишається невидимим"
GROUP = "tests"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Hero-текст і блоки з data-aos лишаються прозорими назавжди, якщо "
               "AOS.init() виконується до завантаження aos.js або не викликається "
               "взагалі (шукаємо і в html/php, і в підключених .js). Автофікс "
               "переставляє тег бібліотеки перед init або дописує init.")
FILES = ["*.html", "*.htm", "*.php", "*.js"]

# fade-up, fade-down-right, zoom-in, flip-left, slide-up, ... — саме ці
# префікси в aos.css отримують правило opacity:0 до ініціалізації.
DATA_AOS_RX = re.compile(r'data-aos\s*=\s*["\'](fade|zoom|flip|slide)', re.I)
AOS_CSS_LINK_RX = re.compile(r'<link\b[^>]*\baos[^>]*\.css[^>]*>', re.I)
AOS_JS_SCRIPT_RX = re.compile(r'<script\b[^>]*\bsrc\s*=\s*["\'][^"\']*aos[^"\']*\.js[^"\']*["\'][^>]*>\s*</script\s*>', re.I)
AOS_INIT_RX = re.compile(r'AOS\.init\s*\(')
# <script>-блок (без src), що містить AOS.init — ціль для переносу тега ліби.
INIT_SCRIPT_BLOCK_RX = re.compile(r'<script\b(?![^>]*\bsrc\s*=)[^>]*>.*?</script\s*>', re.S | re.I)


def _is_page(path: str) -> bool:
    return path.lower().endswith((".html", ".htm", ".php"))


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _init_anywhere(files: dict) -> bool:
    """AOS.init( хоч десь у вітці — включно з окремим `assets/js/main.js`
    (конвенція старого шаблону: html без init, init у своєму js)."""
    return any(AOS_INIT_RX.search(text) for text in files.values())


def _pages_at_risk(files: dict):
    """Сторінки, де правило `opacity:0` реально діє: є і анімований
    `data-aos`, і підключений aos.css. Судимо ПОСТОРІНКОВО, а не по вітці:
    порядок скриптів у цих вайтах живе копією в кожному файлі, тож дефект
    буває на всіх сторінках одразу — одна знахідка на вітку залишила б
    решту сторінок і без рапорту, і без фікса."""
    for path, text in files.items():
        if not _is_page(path):
            continue
        if DATA_AOS_RX.search(text) and AOS_CSS_LINK_RX.search(text):
            yield path, text


def _defect(text: str, init_anywhere: bool):
    """('order'|'missing', позиція) для сторінки — або (None, None)."""
    m_init = AOS_INIT_RX.search(text)
    m_lib = AOS_JS_SCRIPT_RX.search(text)
    if m_init and m_lib and m_init.start() < m_lib.start():
        return "order", m_init.start()
    if not m_init and not init_anywhere:
        return "missing", DATA_AOS_RX.search(text).start()
    return None, None


def run_branch(files, all_paths, branch: str = ""):
    init_anywhere = _init_anywhere(files)
    issues = []
    for path, text in _pages_at_risk(files):
        kind, pos = _defect(text, init_anywhere)
        if kind is None:
            continue
        msg = ("AOS.init() виконується до завантаження aos.js (typeof AOS === "
               "'undefined'), тому анімовані data-aos лишаються з opacity: 0 назавжди."
               if kind == "order" else
               "AOS.init() не викликається в жодному файлі вітки, тому анімовані "
               "data-aos лишаються з opacity: 0 назавжди.")
        issues.append({"path": path, "line": _line_of(text, pos),
                       "severity": "error", "message": msg})
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    init_anywhere = _init_anywhere(files)
    actions = []
    for path, text in _pages_at_risk(files):
        kind, _pos = _defect(text, init_anywhere)
        if kind is None:
            continue
        new_text = _fixed_order(text) if kind == "order" else _inserted_init(text)
        if new_text and new_text != text:
            actions.append({"type": "edit", "path": path, "content": new_text})
    return actions


def _fixed_order(text: str) -> str | None:
    """Тег ліби переїжджає з свого рядка на позицію перед <script>-блоком з
    AOS.init. Порядок — єдине, що тут зламане, тож і правка рівно про нього."""
    m_lib = AOS_JS_SCRIPT_RX.search(text)
    m_block = next((c for c in INIT_SCRIPT_BLOCK_RX.finditer(text)
                    if AOS_INIT_RX.search(c.group(0))), None)
    if not m_lib or not m_block:
        return None
    lib_tag = m_lib.group(0)
    line_start = text.rfind("\n", 0, m_lib.start()) + 1
    line_end = text.find("\n", m_lib.end())
    line_end = len(text) if line_end == -1 else line_end + 1
    without_lib = text[:line_start] + text[line_end:]
    at = m_block.start()
    if at >= line_end:
        at -= line_end - line_start
    return without_lib[:at] + lib_tag + "\n" + without_lib[at:]


def _inserted_init(text: str) -> str | None:
    """Ліба підключена, а init ніхто не викликає — дописуємо його одразу
    після тега; без тега ліби фіксити нічого (це вже інший дефект)."""
    m_lib = AOS_JS_SCRIPT_RX.search(text)
    if not m_lib:
        return None
    return (text[:m_lib.end()] + "\n<script>AOS.init({ once: true });</script>"
            + text[m_lib.end():])
