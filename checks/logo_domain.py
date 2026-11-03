"""Назва сайту php-вайта: лого і всі згадки — з голови <title>.

ЕТАЛОН — назва вітки (site_name.expected): колонка «Вайт» у ClickUp
однозначно відповідає колонці «Название» (borhe-ansabu-it-it →
«Borhe Ansabu»). Домен еталоном більше НЕ є: домени міняються
(«Доменные зоны были изменены»), а назва вайта стабільна. Коли назву
почне давати поле таски ClickUp — зміниться рівно site_name.expected.

Що ловимо (вітки, з назви яких виводиться назва):
  * лого — перший home-лінк (<a href="./|/|index.*">) або <h1> у <header>;
    його видимий текст порівнюється з назвою вітки через варіанти
    написання (site_name.same: регістр, діакритика, умляути, «&»),
    тож «Ánfixu Blurfi» ↔ anfixu-blurfi-… — збіг, не помилка;
  * лого без тексту взагалі (картинка/сама іконка) — warn, руками.

Автофікс:
  * у лого замінюється лише ТЕКСТ: перший текстовий вузол → назва вітки
    зі збереженням стилю регістру (TAJBOJO → BORHE ANSABU); іконки/svg
    не чіпаються;
  * бейдж-монограма — окремий контейнер: типова верстка це квадратний
    32×32 бейдж з монограмою поруч зі словом-назвою
    (`<div><span>L</span></div><span>Lefxgo</span>`). Порівняння і фікс
    дивляться саме на слово-назву; монограма НЕ обов'язково
    односимвольна («S9», «AT», «BD», «AND») і впізнається за формою
    (квадратна коробка) або як скорочення сусідньої назви. Поки перша
    літера бейджа збігається з назвою — він лишається як є;
  * ціле слово, затиснуте у квадратний бейдж (слід старої поломки),
    повертається у спорожнілий словознак поруч, у бейджі лишається
    перша літера;
  * той самий старий бренд у home-лінках <footer> замінюється так само;
    навігаційні лінки («Início», «Home») не чіпаються;
  * СТАРА НАЗВА ПО ВСЬОМУ САЙТУ (title, meta, тексти, всі сторінки)
    перейменовується через site_name.rename: повна фраза + перше слово,
    лише капіталізовані входження — слаги, пошти і соцлінки цілі.

Лого з плейсхолдером {{DOMAIN}}/{{DOMAIN_NAME}} валідне за побудовою — скіп.
"""
import html as _html
import re
import unicodedata

import site_name

NAME = "Назва сайту: лого і згадки з title"
GROUP = "auto"     # бейдж-машинерія звалідована на 2185 вітках (див.
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"brand"}
                   # історію); еталон «назва вітки» замінив доменний —
                   # шумні правила хвоста домену (locnowau ↔ lockomaadnpc)
                   # стали непотрібні: назва вітки чиста, рівності через
                   # site_name.same вистачає
PROJECTS = ["php"]
DESCRIPTION = ("Текст лого у хедері має нести назву вітки (колонка "
               "«Название» у ClickUp), а не чужу. Автофікс замінює текст "
               "лого (і той самий бренд у футері) на назву вітки і "
               "перейменовує стару назву ПО ВСЬОМУ САЙТУ; бейдж-монограму "
               "не чіпає, слово із затиснутого бейджа повертає у словознак "
               "поруч; слаги, пошти й соцлінки цілі.")
FILES = ["*.html", "*.htm", "*.php", "*.vue", "*.tsx"]

HEADER_RX = re.compile(r"<header\b.*?</header\s*>", re.S | re.I)
FOOTER_RX = re.compile(r"<footer\b.*?</footer\s*>", re.S | re.I)
# <h1> у хедері — назва сайта; бренд не завжди загорнутий у посилання
H1_RX = re.compile(r"<h1\b[^>]*>.*?</h1\s*>", re.S | re.I)
# home-лінк: href = ./ | / | index.html | ./index.php | ...  (як у wrong_literal).
# У node-вайтах то не <a>, а компонент роутера, і адреса буває обчисленою:
#   Nuxt  <NuxtLink :to="localePath('/')" class="navigation__logo">
#   Next  <Link href="/" className="...">
# Тег закривається собою ж (зворотне посилання \1), тому вкладені <span>
# усередині лого не рвуть матч.
_LINK_TAG = r"a|NuxtLink|nuxt-link|RouterLink|router-link|Link"
# на підсторінках лого веде на корінь через «../» (rezmeufiriafkupul 21.10:
# без цього перший home-лінк у хедері /about/ — пункт меню href="index.html",
# і чек звіряв з доменом напис меню, а не лого)
_HOME = r"""(?:\.\./)+|\.?/|(?:\.\./)*\.?/?index\.(?:html?|php)"""
LOGO_A_RX = re.compile(
    rf"""<({_LINK_TAG})\b
         (?:[^>"']|"[^"]*"|'[^']*')*?          # атрибути до потрібного
         (?<![\w-])(?::|v-bind:)?(?:href|to)\s*=\s*
         (?: ["'](?:{_HOME})["']                                  # href="./"
           | ["']\s*localePath\(\s*['"](?:{_HOME})['"]\s*\)\s*["'] # :to="localePath('/')"
           | \{{\s*['"](?:{_HOME})['"]\s*\}}                      # href={{"/"}}
         )
         (?:[^>"']|"[^"]*"|'[^']*')*>
         .*?</\1\s*>""",
    re.S | re.I | re.X)
# Обчислений напис — {{ t('nav.brand') }} у Vue, {site.name} у JSX. Ні судити,
# ні переписувати його не можна: у файлі немає тексту, який бачить користувач.
INTERP_RX = re.compile(r"\{\{.*?\}\}|\{[^{}]*[A-Za-z_][\w.]*\s*\}", re.S)
PLACEHOLDER_RX = re.compile(r"\{\{\s*DOMAIN(?:_NAME)?\s*\}\}")
TAG_SPLIT_RX = re.compile(r"(<[^>]+>)")
LETTER_RX = re.compile(r"[^\W\d_]", re.U)

# --- розпізнавання бейджа-монограми ---------------------------------------
# Бейдж — квадратна коробка фіксованого розміру: w-9 h-9, size-10,
# style="width:36px;height:36px". У неї слово фізично не влазить.
TW_W_RX = re.compile(r"^w-(\d+|\[[^\]]+\])$")
TW_H_RX = re.compile(r"^h-(\d+|\[[^\]]+\])$")
TW_SIZE_RX = re.compile(r"^size-(?:\d+|\[[^\]]+\])$")
CSS_W_RX = re.compile(r"(?:^|;)\s*width\s*:\s*([\d.]+)px", re.I)
CSS_H_RX = re.compile(r"(?:^|;)\s*height\s*:\s*([\d.]+)px", re.I)
CLASS_ATTR_RX = re.compile(r"""\bclass\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
STYLE_ATTR_RX = re.compile(r"""\bstyle\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
VOID_TAG_RX = re.compile(
    r"<(?:img|br|hr|input|source|meta|link|path|circle|rect|use|polygon)\b", re.I)
WORD_RX = re.compile(r"[^\W\d_]+", re.U)
# Довші за це — вже не монограма, а слово (найдовший реальний бейдж у
# корпусі — «AND», 3 символи).
MAX_BADGE_LEN = 4


def _expected(branch: str, files: dict | None = None) -> str:
    """Очікувана назва сайту. Окремо — щоб підміняти в тестах.
    Джерело — site_name.expected: голова <title>, фолбек — назва вітки."""
    try:
        return site_name.expected(branch, files)
    except Exception:
        return ""


def _norm(s: str) -> str:
    """Нормалізація для порівняння: без діакритики, регістру і не-алфавітних."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.casefold() if c.isalnum())


def _same(logo_text: str, expected: str) -> bool:
    """Чи несе лого ту саму назву, що й вітка (варіанти написання —
    site_name.same: діакритика, умляути, «&»)."""
    return site_name.same(logo_text, expected)


def _text_of(a_html: str) -> str:
    """Видимий текст лінка: теги геть, ентіті розкодувати, пробіли схлопнути.

    Розкодування обов'язкове: декоративний глиф у лого часто стоїть як ентіті
    (<span>&#9670;</span> Neurovagigab), і без unescape у порівняння затікали
    ЦИФРИ номера символу — «9670neurovagigab» проти домену neurovagigab, тобто
    чек вимагав «виправити» правильне лого (фолс на neodadu-ar-es).
    """
    txt = _html.unescape(re.sub(r"<[^>]+>", " ", a_html))
    return re.sub(r"\s+", " ", txt).strip()


def _machine_label(a_html: str, files: dict) -> str:
    """Машинний напис безтекстового лого: aria-label або <title> SVG-файла
    з вітки, фолбек — alt картинки. LogoLoom-стиль wordmark конвертує текст
    у контури (кейс epidoc 02.10) — видимого тексту нема, але aria-label
    лишається, і його можна звірити замість «вручну»."""
    im = re.search(r'<img[^>]+src="([^"?#]+\.svg)[^"]*"', a_html, re.I)
    if im:
        rel = im.group(1).lstrip("./")
        svg = files.get(rel)
        if svg is None:
            svg = next((files[p] for p in files
                        if p == rel or p.endswith("/" + rel)), None)
        if svg:
            m = (re.search(r'aria-label="([^"]+)"', svg)
                 or re.search(r"<title[^>]*>([^<]+)</title>", svg))
            if m and m.group(1).strip():
                return m.group(1).strip()
    am = re.search(r'alt="([^"]+)"', a_html, re.I)
    return _html.unescape(am.group(1)).strip() if am else ""


def _label_matches(label: str, expected: str) -> bool:
    """Збіг машинного напису з назвою: цілком, головою до розділювача
    («Epidoc - Auto d'epoca…» → «Epidoc», «ANTEPIU NERG｜杉並の…» → «ANTIQUE
    NEST»; ентіті в alt розкодовано — semence 27.10) або головою з такої ж
    кількості слів («Lamubde Viopa Adgugenae» → «Lamubde Viopa», бренд + рід
    діяльності без роздільника — lamubde-viopa br-pt 27.10)."""
    label = _html.unescape(label)
    if _same(label, expected):
        return True
    head = re.split(r"\s*[-–—|｜·:：]\s*", label)[0].strip()
    if head and _same(head, expected):
        return True
    n = len(expected.split())
    words = head.split()
    return 0 < n < len(words) and _same(" ".join(words[:n]), expected)


_CJK_RX = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def _other_script(a: str, b: str) -> bool:
    """Лого латиницею, а назва — ієрогліфами (чи навпаки): «Hahuli Koce» ↔
    «葉月工房» (hahuli-koce jp 27.10) — одна назва різними письмами; звіряти
    може лише людина, перейменування по сайту затерло б латинське лого."""
    return bool(_CJK_RX.search(a)) != bool(_CJK_RX.search(b))


def _tagline_match(txt: str, expected: str) -> bool:
    """Текстове лого «назва｜слоган» (Wix/японські шапки — hajipo-kabe 27.10):
    голова до риски/тире збігається з назвою — лого правильне."""
    if not re.search(r"[|｜–—]", txt):
        return False
    head = re.split(r"\s*[|｜–—]\s*", txt)[0].strip()
    return bool(head) and _same(head, expected)


def _styled(label: str, sample: str) -> str:
    """Лейбл у стилі регістру старого лого.

    «Усе великими» вирішуємо лише коли літер БІЛЬШЕ однієї: єдина велика
    літера (лого-монограма «S») — це не CAPS-стиль, і назва з неї виходила
    «LEFXGO» замість «Lefxgo»."""
    letters = [c for c in sample if c.isalpha()]
    if len(letters) > 1 and all(c.isupper() for c in letters):
        return label.upper()
    if letters and letters[0].isupper():
        return label[:1].upper() + label[1:]
    return label


def _open_tags(parts, i) -> list[str]:
    """Теги, відкриті на момент текстового вузла parts[i]."""
    stack = []
    for p in parts[:i]:
        if not p.startswith("<"):
            continue
        if p.startswith("</"):
            if stack:
                stack.pop()
        elif not p.endswith("/>") and not VOID_TAG_RX.match(p):
            stack.append(p)
    return stack


def _is_square(tag: str) -> bool:
    """Тег задає квадрат фіксованого розміру — у нього слово не влізе."""
    cm = CLASS_ATTR_RX.search(tag)
    toks = ((cm.group(1) or cm.group(2) or "") if cm else "").split()
    if any(TW_SIZE_RX.match(t) for t in toks):
        return True
    w = next((TW_W_RX.match(t).group(1) for t in toks if TW_W_RX.match(t)), None)
    h = next((TW_H_RX.match(t).group(1) for t in toks if TW_H_RX.match(t)), None)
    if w and h and w == h:
        return True
    sm = STYLE_ATTR_RX.search(tag)
    st = (sm.group(1) or sm.group(2) or "") if sm else ""
    mw, mh = CSS_W_RX.search(st), CSS_H_RX.search(st)
    return bool(mw and mh and mw.group(1) == mh.group(1))


def _is_abbrev(badge: str, name: str) -> bool:
    """Бейдж — скорочення назви: ініціали слів («BD» ← «Bacatá Digital»)
    або короткий префікс («AU» ← «Aubahbu»).

    Саме це відрізняє монограму від РОЗРІЗАНОГО словознака: у «Advo»+«cta»
    чи «Alto»+«Nest» перша частина не є скороченням другої — вони
    складаються у назву, і чіпати їх не можна.
    """
    b, n = _norm(badge), _norm(name)
    if not b or not n or len(b) > MAX_BADGE_LEN or len(b) >= len(n):
        return False
    if b == _norm("".join(w[0] for w in WORD_RX.findall(name))):
        return True
    return n.startswith(b)


def _split_logo(a_html: str):
    """(parts, mono_i, word_idx) — окремо бейдж-монограма й окремо назва.

    Типова верстка лого у цих шаблонах — квадратний бейдж з монограмою
    плюс слово поруч:
        <div class="w-8 h-8 rounded-md"><span>L</span></div>
        <span class="text-xl">Lefxgo</span>
    Монограма — це декор, похідний від назви, а не сама назва. Без цього
    поділу чек склеював їх у «L Lefxgo» (тобто «lledgra» ≠ «lefxgo» —
    хибна помилка на здоровому лого), а фікс писав повну назву у бейдж
    32×32 і занулював справжнє слово.

    Монограма НЕ завжди односимвольна: у корпусі це «S9» (sataa-noku-br-pt),
    «AT», «BD», «AND». Одного правила «рівно один символ» мало — воно
    пропускало 56 віток, і на них фікс робив рівно ту саму поломку, від
    якої це правило й ставили. Тому бейдж упізнаємо ще й за формою:
      * квадратний контейнер фіксованого розміру (слово не влізе), або
      * текст є скороченням сусідньої назви (ініціали чи короткий префікс).
    """
    parts = TAG_SPLIT_RX.split(a_html)
    idx = [i for i, p in enumerate(parts)
           if not p.startswith("<") and LETTER_RX.search(p)]
    if len(idx) < 2:
        return parts, None, idx
    head = parts[idx[0]].strip()
    rest = _text_of(" ".join(parts[i] for i in idx[1:]))
    if (len(head) == 1
            or any(_is_square(t) for t in _open_tags(parts, idx[0]))
            or _is_abbrev(head, rest)):
        return parts, idx[0], idx[1:]
    return parts, None, idx


def _logo_parts(a_html: str) -> tuple[str, str]:
    """(текст бейджа або '', текст назви) — видимий текст, розкладений.

    Частини назви склеюються через пробіл: без нього «Bashaóp»+«Secisi»
    зліплювались у «BashaópSecisi» — і в повідомленні чека, і при
    обчисленні ініціалів.
    """
    parts, mono_i, word_idx = _split_logo(a_html)
    mono = parts[mono_i].strip() if mono_i is not None else ""
    word = _text_of(" ".join(parts[i] for i in word_idx))
    return mono, word


def _clipped_badge(a_html: str):
    """(parts, badge_i, slot_i) — у квадратний бейдж вписане ціле слово,
    а сусідній напис спорожнів. Це слід САМЕ цієї поломки автофікса: до
    того, як бейдж почали впізнавати за формою, фікс писав повну назву в
    коробку 32×32 і затирав справжній словознак. У кеші так покалічено
    64 вітки; лагодиться структурно, без домену — слово просто
    повертається на своє місце, а в бейджі лишається перша літера.
    """
    parts = TAG_SPLIT_RX.split(a_html)
    idx = [i for i, p in enumerate(parts)
           if not p.startswith("<") and LETTER_RX.search(p)]
    if len(idx) != 1:
        return None
    i = idx[0]
    if len(parts[i].strip()) <= MAX_BADGE_LEN:
        return None
    if not any(_is_square(t) for t in _open_tags(parts, i)):
        return None
    for j in range(i + 1, len(parts) - 1):
        if parts[j].startswith("<") or parts[j].strip():
            continue
        # текстовий слот саме ВСЕРЕДИНІ елемента: <span>|тут|</span>
        if (parts[j - 1].startswith("<") and not parts[j - 1].startswith("</")
                and parts[j + 1].startswith("</")):
            return parts, i, j
    return None


def _uncramp(a_html: str) -> str:
    """Повертає слово з бейджа у спорожнілий напис поруч."""
    got = _clipped_badge(a_html)
    if not got:
        return a_html
    parts, i, j = got
    word = parts[i].strip()
    lead = re.match(r"\s*", parts[i]).group(0)
    trail = re.search(r"\s*$", parts[i]).group(0)
    parts[i] = lead + _styled(word[0], word) + trail
    parts[j] = word
    return "".join(parts)


def _badge_ok(mono: str, label: str) -> bool:
    """Бейдж годиться, якщо починається з тієї ж літери, що й домен.

    Багатолітерна монограма — свідомий декор («S9» ← «Sataá Noku», «AT» ←
    «Algoritmo Tayrona»), і поки перша літера збігається з новою назвою,
    переписувати її нема сенсу: це зайвий шум у диффі на 56 вітках.
    """
    return not mono or _norm(mono)[:1] == _norm(label)[:1]


def _replace_text(a_html: str, new_text: str) -> str:
    """Міняє текстові вузли всередині <a>: назва → new_text, решта з
    літерами → порожньо; бейдж-монограма → ПЕРША ЛІТЕРА нової назви
    (у бейдж не влазить слово, та й змісту в ньому немає), і лише якщо
    його теперішня перша літера вже не та."""
    parts, mono_i, word_idx = _split_logo(a_html)
    if (mono_i is not None and new_text.strip()
            and not _badge_ok(parts[mono_i].strip(), new_text)):
        old = parts[mono_i]
        lead = re.match(r"\s*", old).group(0)
        trail = re.search(r"\s*$", old).group(0)
        # бейдж — латинська літера без діакритики (Á→A)
        letter = (site_name.latin(new_text) or new_text).strip()[:1]
        parts[mono_i] = lead + _styled(letter, old.strip()) + trail
    first = True
    for i in word_idx:
        p = parts[i]
        if first:
            lead = re.match(r"\s*", p).group(0)
            trail = re.search(r"\s*$", p).group(0)
            parts[i] = lead + new_text + trail
            first = False
        else:
            parts[i] = re.sub(r"\S", "", p)
    return "".join(parts)


def _page_logo(text: str):
    """(abs_start, abs_end, html) лого у <header> або None.

    Зазвичай лого — це перший home-лінк. Але бренд не завжди загорнутий у
    посилання: у частині вайтів у хедері стоїть `<h1>Назва</h1>` всередині
    звичайного `<div>`, а найперший `href="./"` у тому ж хедері — це пункт
    МЕНЮ. Тоді чек звіряв із доменом текст навпункту (він якраз збігався) і
    рапортував «чисто», а справжнє лого не дивився взагалі
    (кейс fazikg-cag-rectem-ch-de: меню «Familycarre» ✓, лого — інший бренд).
    Тож `<h1>` ПОЗА home-лінком має пріоритет: заголовок у хедері — це назва
    сайта. Коли ж `<h1>` лежить усередині лінка, беремо лінк цілком — інакше
    загубився б бейдж-монограма, що стоїть сусіднім вузлом.

    Лого з ОБЧИСЛЕНИМ написом пропускаємо: у `{{ t('nav.brand') }}` чи
    `{site.name}` тексту, який побачить користувач, у файлі просто немає —
    судити його не можна, а фікс перетворив би виклик на рядок і зламав
    збірку. Гард стоїть тут, а не в run_branch, щоб фікс і чек ніколи не
    розійшлись у тому, що вважають лого.
    """
    hm = HEADER_RX.search(text)
    if not hm:
        return None
    head = hm.group(0)
    lm = LOGO_A_RX.search(head)
    h1 = H1_RX.search(head)
    if h1 and not (lm and lm.start() <= h1.start() < lm.end()):
        cand = h1
    elif lm:
        cand = lm
    else:
        return None
    inner = cand.group(0)[cand.group(0).find(">") + 1:]
    if INTERP_RX.search(inner):
        return None
    return hm.start() + cand.start(), hm.start() + cand.end(), cand.group(0)


def _is_page(path: str) -> bool:
    return path.lower().endswith((".html", ".htm", ".php", ".vue", ".tsx"))


def run_branch(files, all_paths, branch: str = ""):
    expected = _expected(branch, files)
    if not expected:
        return []
    issues = []
    for path in sorted(files):
        if not _is_page(path):
            continue
        text = files[path]
        logo = _page_logo(text)
        if not logo:
            continue
        start, _end, a = logo
        line = text.count("\n", 0, start) + 1
        if PLACEHOLDER_RX.search(a):
            continue                       # {{DOMAIN}} підставиться при деплої
        cramped = _clipped_badge(a)
        if cramped:
            word = cramped[0][cramped[1]].strip()
            issues.append({"path": path, "line": line, "severity": "error",
                           "message": (f"у квадратний бейдж лого вписане ціле "
                                       f"слово «{word}» — воно обрізається, а "
                                       f"напис поруч порожній; фікс поверне "
                                       f"назву на місце, у бейджі лишиться "
                                       f"«{_styled(word[0], word)}»")})
            continue
        mono, word = _logo_parts(a)
        txt = word or _text_of(a)
        if not LETTER_RX.search(txt):
            label = _machine_label(a, files)
            if label and _label_matches(label, expected):
                continue        # aria-label/alt несе назву — збіг, тихо
            if label:
                issues.append({"path": path, "line": line,
                               "severity": "error",
                               "message": (f"напис лого у aria-label/alt "
                                           f"«{label}» ≠ назва сайту "
                                           f"«{expected}» — виправ лого або "
                                           f"його мітки вручну")})
                continue
            issues.append({"path": path, "line": line, "severity": "warn",
                           "message": (f"лого без тексту (картинка/іконка) — "
                                       f"звір з назвою «{expected}» вручну")})
            continue
        if not _same(txt, expected) and not _tagline_match(txt, expected):
            if _other_script(txt, expected):
                issues.append({"path": path, "line": line, "severity": "warn",
                               "message": (f"лого «{txt}» і назва сайту «{expected}» — різними "
                                           f"письмами; звір вручну (автозаміни немає)")})
                continue
            issues.append({"path": path, "line": line, "severity": "error",
                           "message": (f"лого «{txt}» ≠ назва сайту "
                                       f"«{expected}» — фікс замінить і "
                                       f"перейменує стару назву по всьому "
                                       f"сайту")})
        elif not _badge_ok(mono, expected):
            # назва вже правильна, а бейдж показує чужу літеру
            letter = (site_name.latin(expected) or expected)[:1]
            issues.append({"path": path, "line": line, "severity": "error",
                           "message": (f"бейдж лого «{mono}» ≠ перша літера "
                                       f"назви «{expected}» — фікс замінить "
                                       f"на «{_styled(letter, mono)}»")})
    return issues


def fix_branch(files, all_paths, branch: str = ""):
    """Замінює текст лого на назву вітки там, де run_branch бачить error:
    у <header> — перший home-лінк, у <footer> — home-лінки з тим самим
    старим брендом; далі стара назва перейменовується ПО ВСЬОМУ САЙТУ
    (site_name.rename: слаги/пошти/соцлінки цілі)."""
    expected = _expected(branch, files)
    if not expected:
        return []
    edited: dict[str, str] = {}
    old_brand = ""                          # канонічна стара назва вітки
    for path in sorted(files):
        if not _is_page(path):
            continue
        text = files[path]
        logo = _page_logo(text)
        if not logo:
            continue
        start, end, a = logo
        if PLACEHOLDER_RX.search(a):
            continue
        # Слово, затиснуте в бейдж, повертаємо на місце ЛОКАЛЬНО: text
        # лишається оригіналом, інакше нижче не буде видно різниці і
        # правка мовчки загубиться.
        cramped = bool(_clipped_badge(a))
        if cramped:
            a = _uncramp(a)
        mono, word = _logo_parts(a)
        old_txt = word or _text_of(a)
        if not LETTER_RX.search(old_txt):
            continue
        mono_ok = _badge_ok(mono, expected)
        fits = _same(old_txt, expected) or _tagline_match(old_txt, expected) or _other_script(old_txt, expected)
        if fits and mono_ok and not cramped:
            continue                       # і назва, і бейдж уже правильні
        # лого, що вже несе назву (хай і з іншим правописом), не
        # перейменовуємо — лишається як є, правиться лише бейдж.
        # НАПИС лого — строгою латиницею (â→a; нелатинське → назва вітки)
        display = site_name.latin(expected) or site_name.expected(branch)
        new_text = old_txt if fits else _styled(display, old_txt)
        brand = _norm(old_txt)
        if not fits and not old_brand:
            old_brand = old_txt.strip()

        edits = [(start, end, _replace_text(a, new_text))]
        # лого футера: home-лінки з тим САМИМ старим брендом
        for fm in FOOTER_RX.finditer(text):
            for lm in LOGO_A_RX.finditer(fm.group(0)):
                if PLACEHOLDER_RX.search(lm.group(0)):
                    continue
                fa = _uncramp(lm.group(0))
                _fm_mono, fm_word = _logo_parts(fa)
                if _norm(fm_word or _text_of(fa)) != brand:
                    continue               # «Início» тощо — не чіпаємо
                edits.append((fm.start() + lm.start(), fm.start() + lm.end(),
                              _replace_text(fa, new_text)))
        new = text
        for s, e, repl in sorted(edits, key=lambda x: -x[0]):
            new = new[:s] + repl + new[e:]
        if new != text:
            edited[path] = new

    # стара назва живе не лише в лого: title, meta, тексти, всі сторінки
    if old_brand:
        for path in sorted(files):
            if not _is_page(path):
                continue
            base = edited.get(path, files[path])
            renamed = site_name.rename(base, old_brand, expected)
            if renamed != files[path]:
                edited[path] = renamed
    return [{"type": "edit", "path": p, "content": t}
            for p, t in sorted(edited.items())]
