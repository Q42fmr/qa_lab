"""Фото hero-блоку затирає текст: картинка стоїть у потоці й з'їдає всю секцію.

Кейс `mujdova-br-pt` (4 сторінки). Розмітка hero задумана шаровою:

    <section class="relative w-full h-[340px] md:h-[420px] overflow-hidden">
      <img class="w-full h-full object-cover" src="...">        <- у ПОТОЦІ
      <div class="absolute inset-0 bg-[#182220]/55"></div>      <- оверлей, шар
      <div class="relative z-10 ... h-full flex ...">текст</div> <- шар
    </section>

Оверлей і текст — шари (`absolute inset-0`, `relative z-10`), а `<img>` забули
вийняти з потоку. Секція має ВЛАСНУ висоту (340/420px) і `overflow-hidden`,
тож картинка `h-full` займає її цілком, текстовий блок починається рівно на
її нижній межі й обрізається. Заміряно в браузері на `benefits.html`:
секція 420px, `img position:static height:420`, текстовий блок `top:420`,
`<h1>` на `top:501` — поза секцією, тобто hero показує лише фото.

Здорова конвенція тієї ж сім'ї — картинка теж шар: `absolute inset-0 w-full
h-full object-cover`. На вибірці 401 вайта так зроблено у 198; зламана форма -
рідкість (1 у тій же вибірці + `mujdova-br-pt`), тому це саме дефект розмітки,
а не інший стиль верстки.

Автофікс дописує картинці `absolute inset-0` — рівно те, чого їй бракує, щоб
стати шаром під текстом. Решта класів (`w-full h-full object-cover`), розмітка
й порядок вузлів не чіпаються.

Гейт навмисно вузький: секція мусить мати ВЛАСНУ висоту. Інакше витягування
картинки з потоку схлопнуло б блок у нуль - у звичайних секціях, де висоту
задає сама картинка, чек мовчить.
"""
import re

NAME = "Hero: фото затирає текст"
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"media"}
PROJECTS = ["php"]
DESCRIPTION = ("У hero-секції з власною висотою і overflow-hidden картинка "
               "лежить у потоці й займає всю секцію, тому текстовий блок "
               "(`relative z-*`, тобто теж у потоці) виїжджає за її межі й "
               "обрізається — видно лише фото. Автофікс додає картинці "
               "`absolute inset-0`, роблячи її шаром під текстом. Текст, який "
               "сам `absolute inset-0`, не чіпається — він і так накриває фото.")
FILES = ["*.html", "*.htm", "*.php"]

# Контейнер hero — не обов'язково <section>: на головній `mujdova-br-pt` це
# <section class="relative"> ⟶ <div class="… h-[420px] … overflow-hidden">,
# тобто висоту й обрізання тримає внутрішній div. Тому шукаємо будь-який з
# двох тегів, а межі рахуємо по його ж імені.
CONTAINER_RX = re.compile(
    r"""<(?P<tag>section|div)\b[^>]*\bclass\s*=\s*(?P<q>["'])(?P<cls>[^"']*)(?P=q)[^>]*>""", re.I)
IMG_RX = re.compile(r"""<img\b[^>]*>""", re.I)
CLASS_RX = re.compile(r"""\bclass\s*=\s*(?P<q>["'])(?P<v>[^"']*)(?P=q)""", re.I)
# ФІКСОВАНА висота контейнера: h-[340px] / md:h-[420px] / h-screen, або inline
# `style="height:600px"`. `min-h-` тут не рахується НАВМИСНО: з min-height блок
# росте під вміст, текст просто йде під фото й нічого не обрізається.
OWN_HEIGHT_RX = re.compile(r"""(?:^|\s|:)h-(?:\[[^\]]+\]|screen)""", re.I)
STYLE_HEIGHT_RX = re.compile(r"""\bstyle\s*=\s*["'][^"']*(?<!min-)\bheight\s*:""", re.I)
POSITIONED_RX = re.compile(r"\b(?:absolute|fixed|sticky)\b", re.I)
# позицію задають і inline: `style="position:absolute; inset:0"` — так зроблено
# у `pagonrun-muvh-my-en`, і без цієї перевірки чек давав там фолс
STYLE_POS_RX = re.compile(
    r"""\bstyle\s*=\s*["'][^"']*\bposition\s*:\s*(?:absolute|fixed)""", re.I)
COVER_RX = re.compile(r"\bobject-cover\b", re.I)
FULL_H_RX = re.compile(r"\bh-full\b", re.I)
# Текстовий шар у потоці: `relative` (з `z-*` або без). Головне - що він НЕ
# absolute: тоді його положення залежить від картинки перед ним.
TEXT_LAYER_RX = re.compile(
    r"""<div\b[^>]*\bclass\s*=\s*["'][^"']*\brelative\b[^"']*["'][^>]*>""", re.I)


def _element_end(text: str, start: int, tag: str) -> int:
    """Кінець елемента з урахуванням вкладених тегів того ж імені."""
    depth, pos = 0, start
    rx = re.compile(r"<%s\b|</%s\s*>" % (tag, tag), re.I)
    for m in rx.finditer(text[start:]):
        pos = start + m.end()
        if m.group(0).lower().startswith("</"):
            depth -= 1
            if depth == 0:
                return pos
        else:
            depth += 1
    return pos


VOID_TAGS = {"img", "br", "hr", "input", "meta", "link", "source", "area",
             "base", "col", "embed", "param", "track", "wbr"}
TAG_RX = re.compile(r"<(?P<close>/?)(?P<name>[a-zA-Z][\w-]*)(?P<attrs>[^>]*)>")


def _positioned_ancestor(body: str, at: int) -> bool:
    """Чи лежить картинка у предку, який САМ винесений з потоку.

    Кейс `vizsu-pruxezcn-sg-en`: `<div class="absolute inset-0 z-0">` з
    картинкою й градієнтом усередині — шар уже зроблений обгорткою, текст
    `relative z-10` накриває його нормально, чіпати нічого. Дивитись лише на
    класи самого `<img>` недостатньо: так чек давав фолси на 5 вітках з 251.
    """
    stack: list[tuple[str, str]] = []
    for m in TAG_RX.finditer(body[:at]):
        name = m.group("name").lower()
        if m.group("close"):
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == name:
                    del stack[i:]
                    break
            continue
        if name in VOID_TAGS or m.group("attrs").rstrip().endswith("/"):
            continue
        attrs = m.group("attrs")
        cm = CLASS_RX.search(attrs)
        stack.append((name, (cm.group("v") if cm else "")
                      + (" absolute" if STYLE_POS_RX.search(attrs) else "")))
    return any(POSITIONED_RX.search(cls) for _n, cls in stack)


def _broken_heroes(text: str):
    """(позиція_тега_img, тег_img, класи_контейнера) для кожного зламаного hero."""
    out = []
    seen_img: set[int] = set()
    for sm in CONTAINER_RX.finditer(text):
        whole, cls = sm.group(0), sm.group("cls")
        if "overflow-hidden" not in cls.lower():
            continue
        if not (OWN_HEIGHT_RX.search(cls) or STYLE_HEIGHT_RX.search(whole)):
            continue                      # висоту дає вміст — не наш випадок
        body = text[sm.end():_element_end(text, sm.start(), sm.group("tag"))]
        # Ламається лише коли текст У ПОТОЦІ (`relative z-*`): тоді картинка
        # з потоку виштовхує його за межі секції. Якщо текстовий блок сам
        # `absolute inset-0` (кейс `serige-meixewc-my-en`), він накриває фото
        # незалежно від потоку - і чіпати там нічого.
        if not TEXT_LAYER_RX.search(body):
            continue
        im = IMG_RX.search(body)
        if not im:
            continue
        tag = im.group(0)
        cm = CLASS_RX.search(tag)
        if not cm:
            continue
        icls = cm.group("v")
        if POSITIONED_RX.search(icls) or STYLE_POS_RX.search(tag):
            continue                      # уже шар (класом або inline) — гаразд
        if not (COVER_RX.search(icls) and FULL_H_RX.search(icls)):
            continue                      # не фонове фото на всю секцію
        if _positioned_ancestor(body, im.start()):
            continue                      # шар зроблений обгорткою
        pos = sm.end() + im.start()
        if pos in seen_img:
            continue        # той самий <img> уже зловлений зовнішнім контейнером
        seen_img.add(pos)
        out.append((pos, tag, cls))
    return out


def run(path, text):
    issues = []
    for pos, tag, scls in _broken_heroes(text):
        hm = OWN_HEIGHT_RX.search(scls)
        how = hm.group(0).strip() if hm else "height у style"
        issues.append({
            "line": text.count("\n", 0, pos) + 1, "severity": "error",
            "message": (f"фото hero-блоку затирає текст: <img> лежить у потоці "
                        f"й займає всю секцію ({how}, overflow-hidden), тож "
                        f"текстовий блок виїжджає за її межі й обрізається — "
                        f"на сторінці видно лише фото; фікс додає картинці "
                        f"`absolute inset-0`"),
        })
    return issues


def fix(path, text):
    out, last = [], 0
    for pos, tag, _scls in _broken_heroes(text):
        cm = CLASS_RX.search(tag)
        icls = cm.group("v")
        new_tag = tag[:cm.start("v")] + f"absolute inset-0 {icls}" + tag[cm.end("v"):]
        out.append(text[last:pos])
        out.append(new_tag)
        last = pos + len(tag)
    if not out:
        return text
    out.append(text[last:])
    return "".join(out)
