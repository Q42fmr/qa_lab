"""Кукі-банер, який неможливо закрити: display:none сторінки програє Tailwind.

Симптом (знайдено у вітці haofmcanm-ch-de): тиснеш «Akzeptieren» — банер
лишається на екрані, наче згоду не прийнято. localStorage при цьому пишеться
коректно, клас visible знімається — тобто JS справний.

Корінь. Банер ховається власним правилом сторінки в інлайновому <style>:
    .cookie-bar { display: none; }          /* специфічність 0,1,0 */
    .cookie-bar.visible { display: flex; }  /* 0,2,0 — показ */
але в class= того ж елемента стоїть Tailwind-утиліта flex, тобто
`.flex { display: flex }` — теж 0,1,0. Tailwind Play CDN не віддає готовий
css-файл: він генерує <style> у рантаймі й додає його в КІНЕЦЬ <head>, тобто
ПІСЛЯ інлайнового <style> сторінки. За однакової специфічності перемагає те,
що пізніше в каскаді, тож display:flex виграє завжди:
  * при першому заході банер видно (це правильно, але випадково);
  * після кліку «Прийняти» клас visible знято, а .flex усе одно тримає
    display:flex — банер лишається;
  * на наступних заходах visible уже не додається, а банер усе одно висить.

Чому саме display-утиліта: решта утиліт (fixed, bottom-0, gap-4…) до display
не торкаються і конфлікту не створюють. Правила з !important, id-селектором
(#cookie-bar) чи уточненням тега (div.cookie-bar) мають вищу специфічність за
утиліту — вони перемагають, і такі сторінки чек не чіпає.

Автофікс прибирає зайву display-утиліту з class= елемента: приховування знову
працює, а показаний стан лишається на власному правилі сторінки
(.cookie-bar.visible { display: flex }). Якщо такого правила показу немає,
утиліта може бути єдиним джерелом display для показаного стану — тоді чек
лише репортить, а фікс елемент не чіпає.

Той самий корінь ловиться і поза банером — найчастіше на навігації:
`@media (max-width: 768px) { .desktop-nav { display: none } }` плюс
`class="desktop-nav flex …"` означає, що на мобільному десктопне меню НЕ
зникає і висить поряд з бургером (revere-co-es та ще 7 віток у вибірці).
Там правила показу немає, тож автофікс не застосовується: прибрати flex
означало б зробити меню display:block і поламати розкладку — потрібне
підвищення специфічності власного правила, а це вже рішення верстальника.
Тому такі місця йдуть як warn, банер згоди — як error.

Виняток: якщо в class= є Tailwind-варіант ховання (hidden, lg:hidden,
max-lg:hidden…), ховання віддане самому Tailwind — усередині його таблиці
порядок правильний, варіант перемагає display-утиліту, і все працює як
задумано. Перевірено в браузері на Tailwind CDN: `burger-btn lg:hidden flex`
дає display:none при 1365px і display:flex при 500px.

Обмеження: дивимось лише інлайнові <style> тієї ж сторінки — саме так верстають
ці вайти. Правила з окремих .css-файлів не аналізуються.
"""
import re

NAME = "Кукі-банер не закривається (display:none програє Tailwind-утиліті)"
# звалідовано на 250 свіжих вітках (2294 файли): 10 спрацювань — 1 error
# (кукі-банер haofmcanm-ch-de, автофікс перевірено в браузері) і 56 warn
# (десктопне меню на мобільному), усі реальні; фолсів 0
# Правило 4 (нативний <dialog> без [open]) звалідовано на pefi-noku-br-pt:
# у браузері до фіксу «Aceitar todos» пише згоду, а банер лишається (close()
# знімає open, CSS малює далі) і повертається після перезавантаження; після
# фіксу закривається і зі згодою не з'являється, float-кнопка працює
GROUP = "auto"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Кукі-банер зламаний однією з семи причин: display:none "
               "програє Tailwind-утиліті; кнопка згоди без обробника "
               "(фреймворк не гідратується); зіпсоване ім'я localStorage; "
               "<dialog> показаний CSS безумовно; банера НЕМАЄ взагалі "
               "(головна з privacy-лінком без жодного механізму згоди — "
               "фікс додає банер «Прийняти/Відхилити» мовою сторінки); наш "
               "банер без position:fixed («улетів під футер»); у банера є "
               "лише «Прийняти» без «Відхилити» (фікс клонує кнопку поруч "
               "у тому ж стилі). Автофікс детермінований для всіх семи.")
FILES = ["*.html", "*.htm", "*.php"]

STYLE_TAG_RX = re.compile(r"<style\b[^>]*>([\s\S]*?)</style>", re.I)
TAILWIND_CDN_RX = re.compile(
    r"""<script\b[^>]*\bsrc\s*=\s*["'][^"']*cdn\.tailwindcss\.com""", re.I)
# правило css: селектор { тіло }. Тіло без вкладених дужок, тому обгортки
# @media/@supports у матч не потрапляють — знаходяться саме внутрішні правила.
CSS_RULE_RX = re.compile(r"([^{}]+)\{([^{}]*)\}")
DISPLAY_RX = re.compile(r"(?<![\w-])display\s*:\s*([a-zA-Z-]+)\s*(!\s*important)?", re.I)
BARE_CLASS_RX = re.compile(r"^\.([A-Za-z_][\w-]*)$")
CLASS_TOKEN_RX = re.compile(r"\.([A-Za-z_][\w-]*)")
# остання проста послідовність селектора — саме її елемент і стилізується
LAST_SEQ_RX = re.compile(r"[^\s>+~]+$")
TAG_RX = re.compile(r"""<(\w+)\b[^>]*?\bclass\s*=\s*("[^"]*"|'[^']*')[^>]*>""", re.I)

# display-утиліти Tailwind, які ПОКАЗУЮТЬ елемент. hidden свідомо не тут:
# він теж ховає, тож конфлікту «не можу закрити» не створює.
SHOW_UTILS = {
    "block", "inline-block", "inline", "flex", "inline-flex", "grid",
    "inline-grid", "table", "inline-table", "table-row", "table-cell",
    "table-caption", "table-column", "flow-root", "contents", "list-item",
}
CONSENT_RX = re.compile(r"cookie|consent|gdpr|dsgvo", re.I)
# У ІНЛАЙН-скриптах голе «cookie» нічого не каже: будь-який технічний
# setCookie-хелпер містить і слово, і document.cookie — pitchbar-утиліта
# serralheria так ховала відсутній банер (02.10). Для скриптів вимагаємо
# семантику ЗГОДИ, не роботи з куками.
INLINE_CONSENT_RX = re.compile(
    r"consent|gdpr|dsgvo|lgpd"
    r"|cookie[-_\s]?(?:banner|bar|notice|policy|law|warn|accept|agree)"
    r"|accept[-_]?(?:all[-_]?)?cookies?|cookies?[-_]?accepted?"
    r"|aceitar|akzeptieren|zustimm", re.I)


def _rules(text):
    """[(селектор, значення display, important)] з усіх інлайнових <style>."""
    out = []
    for block in STYLE_TAG_RX.findall(text):
        for sel_raw, body in CSS_RULE_RX.findall(block):
            decls = DISPLAY_RX.findall(body)
            if not decls:
                continue
            value, important = decls[-1]        # у межах правила виграє остання
            for part in sel_raw.split(","):
                part = part.strip()
                if part:
                    out.append((part, value.lower(), bool(important)))
    return out


def _analyze(text):
    """(класи, приховані правилом 0,1,0; класи, що мають правило показу)."""
    hidden, shown = set(), set()
    for part, value, important in _rules(text):
        bare = BARE_CLASS_RX.match(part)
        if value == "none":
            # !important і будь-яка вища специфічність перемагають утиліту
            if bare and not important:
                hidden.add(bare.group(1))
            continue
        if bare:
            continue                            # .X{display:flex} — не «показ у парі»
        seq = LAST_SEQ_RX.search(part)
        if seq:
            shown.update(CLASS_TOKEN_RX.findall(seq.group(0)))
    return hidden, shown


def _conflicts(text, hidden):
    """Елементи з конфліктом: (match, класи, приховані класи, display-утиліти)."""
    for m in TAG_RX.finditer(text):
        classes = m.group(2)[1:-1].split()
        if any(c == "hidden" or c.endswith(":hidden") for c in classes):
            # ховання віддане самому Tailwind (hidden, lg:hidden, max-lg:hidden…):
            # усередині його таблиці порядок правильний і варіант перемагає
            # display-утиліту — перевірено в браузері, це не баг
            continue
        hits = [c for c in classes if c in hidden]
        utils = [c for c in classes if c in SHOW_UTILS]
        if hits and utils:
            yield m, classes, hits, utils


# ---------------------------------------------------------------- правило 2
# Та сама поломка очима («банер не закривається»), але інша причина: кнопка
# «Прийняти» взагалі нічого не робить. Кейс `chafelzibau-br-pt` - банер
# приїхав з Next.js як `LgpdBanner`, розмітка відрендерена у html, а обробник
# лишився у React-бандлі. Заміряно в браузері: клік по «Entendi» не міняє
# нічого (банер видимий, ні кукі, ні localStorage не пишеться), при цьому на
# кнопці й на <body> НУЛЬ ключів `__react*` і немає `__NEXT_DATA__` - тобто
# React у статиці не гідратується взагалі, і код обробника не запускається
# ніколи. Тому «файл з обробником існує» ще не означає, що він працює.
#
# Фікс не чіпає чужий js, а дає банеру власний, незалежний від фреймворка:
# позначає банер і кнопку `data-wp-consent`, і додає короткий скрипт, який
# ховає банер за збереженою згодою і пише її на клік.
CONSENT_ATTR = "data-wp-consent"
MARKER = "qa_lab:cookie-consent"
ACCEPT_RX = re.compile(
    r"\b(?:Aceitar|Aceito|Entendi|Concordo|Accept|Accetta|Aceptar|Akzeptieren"
    r"|Verstanden|Zustimmen|Got it|Accepter|Terima)\b", re.I)
DECLINE_RX = re.compile(
    r"\b(?:Recusar|Rejeitar|N[ãa]o\s+aceito|Decline|Reject|Rifiuta|Rechazar"
    r"|Refuser|Ablehnen|Nur\s+notwendige|Only\s+necessary"
    r"|Apenas\s+necess[aá]rios|Solo\s+necesarios|Ne\s+pas\s+accepter)\b"
    r"|拒否|必要なクッキーのみ", re.I)
OPEN_TAG_RX = re.compile(r"""<(?P<tag>button|a)\b(?P<attrs>(?:[^>"']|"[^"]*"|'[^']*')*)>""",
                         re.I)
TAGS_RX = re.compile(r"<[^>]*>")
BANNER_RX = re.compile(
    r"""<(?P<tag>div|section|aside|footer)\b(?P<attrs>(?:[^>"']|"[^"]*"|'[^']*')*)>""",
    re.I)
HANDLER_RX = re.compile(r"\bonclick\s*=", re.I)
REAL_HREF_RX = re.compile(r"""\bhref\s*=\s*["'][^"'#]""", re.I)
STORE_RX = re.compile(r"localStorage|sessionStorage|document\.cookie")
INLINE_SCRIPT_RX = re.compile(
    r"<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", re.I)
# Статика, де розмітка відрендерена, а код фреймворка не виконується.
# React/Next - `self.__next_f`/`__NEXT_DATA__` (кейс `chafelzibau-br-pt`).
# Wix Thunderbolt - те саме за суттю, інший фреймворк: у `bralobmgeon.com.br`
# інлайнові бандли починаються з `self.webpackJsonp__wix_thunderbolt_app`, а
# банер приїхав уже відрендереним, з запеченим `style="display: flex;"`.
NO_HYDRATE_RX = re.compile(
    r"self\.__next_f|__NEXT_DATA__|/_next/|static/chunks/"
    r"|webpackJsonp__wix_thunderbolt_app|wix-thunderbolt")
# Бандл складальника - НЕ рукописна логіка згоди сторінки. Кукі-лексика й
# `localStorage` трапляються в ньому побічно: у `bralobmgeon.com.br` це
# rspack-рантайм і телеметрія fedops (`sendBeat`), 4 скрипти по 4-7 КБ. Саме
# вони й глушили правило 2, хоча обробник кнопки лежить у ЗОВНІШНЬОМУ
# `extensions/index.js`, який вантажиться лише з `fetchDa().then(...)`, а той
# fetch іде на `/sites/null/data.json` - теки `sites/` у скрейпі немає взагалі.
# Тобто бандл на сторінці є, а обробник не реєструється ніколи.
BUNDLE_RX = re.compile(r"webpackJsonp|webpackChunk|__webpack_require__|rspack")


def _closing(text: str, tag: str, at: int) -> int:
    """Кінець елемента: перший `</tag>` після `at`. Вкладені однойменні теги у
    кнопках не трапляються, а іконку всередині так не обрізає - саме на цьому
    спіткнувся перший варіант детекту (`<svg>` довший за ліміт вмісту)."""
    m = re.compile(r"</\s*" + tag + r"\s*>", re.I).search(text, at)
    return m.end() if m else -1


def _element_end(text: str, tag: str, at: int) -> int:
    """Кінець елемента З УРАХУВАННЯМ вкладеності однойменних тегів.

    `_closing` для контейнерів не годиться: він віддає ПЕРШИЙ `</div>`, а в
    банера всередині свої div-и, тож їхнє закриття стоїть раніше за кнопку - і
    зовнішня обгортка помилково виглядала «закритою до кнопки». Саме через це на
    `bralobmgeon.com.br` позначався `div.cst-action-decisive` (висота 0) замість
    віджета згоди, і банер 238px лишався на екрані після «Concordo».
    """
    rx = re.compile(r"<(/?)" + tag + r"\b", re.I)
    depth, pos = 1, at
    while depth:
        m = rx.search(text, pos)
        if m is None:
            return -1
        depth += -1 if m.group(1) else 1
        pos = m.end()
    return pos


def _accept_controls(text: str):
    """(match відкривного тега, підпис) кнопок «Прийняти» без жодної дії."""
    for m in OPEN_TAG_RX.finditer(text):
        end = _closing(text, m.group("tag"), m.end())
        if end < 0:
            continue
        label = " ".join(TAGS_RX.sub(" ", text[m.end():end]).split())
        if not label or len(label) > 34 or not ACCEPT_RX.search(label):
            continue
        attrs = m.group("attrs")
        if HANDLER_RX.search(attrs):
            continue                            # свій обробник - не наша справа
        if m.group("tag").lower() == "a" and REAL_HREF_RX.search(attrs):
            continue                            # це лінк, а не кнопка згоди
        if not CONSENT_RX.search(text[max(0, m.start() - 900):end]):
            continue                            # поруч немає кукі-лексики
        yield m, label


# Enfold (Avia) кладе на кожну сторінку інлайн-перевірку веб-шрифтів з
# «aviaCookieConsent» і document.cookie — лексика згоди є, банера нема, коли
# згода в темі вимкнена: клас <html> av-cookies-no-cookie-consent
# (eqeudoha-cotfaup-ch-fr, 26.10). З увімкненою (needs-opt-in / can-opt-out)
# тема малює власний банер — тоді скрипт рахується, як і раніше.
ENFOLD_OFF_RX = re.compile(r"""<html\b[^>]*\bclass\s*=\s*["'][^"']*\bav-cookies-no-cookie-consent\b""", re.I)
ENFOLD_SCRIPT_RX = re.compile(r"aviaCookieConsent|av-cookies-needs-opt-in", re.I)


def _has_inline_consent(text: str) -> bool:
    """Чи є на сторінці ВЛАСНА інлайнова логіка згоди - така виконається завжди,
    і лагодити там нічого. Бандли складальника з підрахунку виключені: їхня
    згадка кукі й стореджу побічна (див. BUNDLE_RX)."""
    enfold_off = bool(ENFOLD_OFF_RX.search(text))
    return any(INLINE_CONSENT_RX.search(s.group(1)) and STORE_RX.search(s.group(1))
               and not BUNDLE_RX.search(s.group(1))
               and not (enfold_off and ENFOLD_SCRIPT_RX.search(s.group(1)))
               for s in INLINE_SCRIPT_RX.finditer(text))


def _dead_accept(text: str):
    """Кнопки згоди, які точно нічого не роблять.

    Наявність обробника у ЛОКАЛЬНОМУ .js сама по собі нічого не гарантує:
    у React/Next-статиці код у бандлі є, але не виконується (заміряно на
    `chafelzibau-br-pt`: нуль ключів `__react*` на кнопці й на <body>). Тому
    мовчимо лише коли згода зашита інлайново - такий скрипт виконається
    завжди.
    """
    if MARKER in text or _has_inline_consent(text):
        return []
    return list(_accept_controls(text))


# ---------------------------------------------------------------- правило 3
# Той самий дефект очима, третя причина: обробник згоди Є і виконався б, але в
# ньому зіпсовано ім'я браузерного API. Кейс `ocu-br-pt`: у `localStorage`
# вбито фрагмент назви вітки - `locabrptlStorage` (3 входження). Скрипт падає
# з ReferenceError на першому ж рядку, тож банер не ховається і кнопка
# «Aceitar» мертва. Слід масової заміни, яка потрапила в ідентифікатор.
#
# Ремонт детермінований: правильне ім'я відоме, і матч приймається лише коли
# склеєні краї дають РІВНО білтін - тому `sessionStorage` сам себе не матчить
# (після `sessi` там немає двох зайвих символів).
BROKEN_BUILTIN_RX = re.compile(
    r"\b(?P<head>loca|sessi)(?P<junk>[A-Za-z0-9]{1,10})(?P<tail>lStorage|onStorage)\b")


def _broken_builtins(text: str):
    """(match, зіпсоване, правильне) для кожного зіпсованого імені API."""
    for m in BROKEN_BUILTIN_RX.finditer(text):
        good = m.group("head") + m.group("tail")
        if good not in ("localStorage", "sessionStorage"):
            continue
        yield m, m.group(0), good


def _rule3(text: str):
    """Зіпсовані імена лише там, де вони справді ламають згоду."""
    if not CONSENT_RX.search(text):
        return []
    return list(_broken_builtins(text))


def _rule2(text: str):
    """(match, підпис) - лише для сторінок, де фреймворк не оживить кнопку."""
    if not NO_HYDRATE_RX.search(text):
        return []
    return _dead_accept(text)


# ---------------------------------------------------------------- правило 4
# Той самий дефект очима, четверта причина: банер — нативний <dialog>, а CSS
# показує його БЕЗУМОВНО. Кейс `pefi-noku-br-pt`: `#cookie-dialog{display:flex}`
# перемагає UA-правило `dialog:not([open]){display:none}` (авторський стиль
# сильніший за UA), тож діалог намальований з моменту завантаження, ще до
# всякого showModal(). close() знімає open, але авторське правило діє далі —
# «Aceitar todos» пише згоду, а банер лишається на екрані; зі збереженою
# згодою він знову видимий після кожного перезавантаження. Fallback-гілка
# `dialog.close ? ... : setAttribute('hidden')` мертва: `dialog.close` існує
# в усіх сучасних браузерах. Ремонт детермінований: правило показу скоупиться
# на `[open]` — showModal() ставить атрибут, close() знімає, закритий діалог
# ховає сам UA.
DIALOG_RX = re.compile(
    r"""<dialog\b(?P<attrs>(?:[^>"']|"[^"]*"|'[^']*')*)>""", re.I)
DIALOG_ID_RX = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""", re.I)
DIALOG_CLASS_RX = re.compile(r"""\bclass\s*=\s*["']([^"']+)["']""", re.I)


def _seq_has_token(seq: str, tok: str) -> bool:
    """Токен у простій послідовності, з межею імені: `#cookie-dialog` не
    матчить `#cookie-dialog-note`."""
    i = seq.find(tok)
    while i != -1:
        nxt = seq[i + len(tok):i + len(tok) + 1]
        if not nxt or not (nxt.isalnum() or nxt in "_-"):
            return True
        i = seq.find(tok, i + 1)
    return False


def _sel_shows_token(sel_part: str, tok: str) -> bool:
    """Варіант селектора стилізує САМЕ елемент tok і не скоуплений [open].
    Токен мусить сидіти в останній простій послідовності: `#x .box`
    стилізує .box, а не діалог."""
    core = sel_part.rstrip()
    if "[open]" in core:
        return False
    last = LAST_SEQ_RX.search(core)
    return bool(last) and _seq_has_token(last.group(0), tok)


def _dialog_tokens(text: str):
    """[(match відкривного <dialog>, {'#id', '.class', ...})]"""
    out = []
    for dm in DIALOG_RX.finditer(text):
        toks = set()
        m = DIALOG_ID_RX.search(dm.group("attrs"))
        if m:
            toks.add("#" + m.group(1).strip())
        m = DIALOG_CLASS_RX.search(dm.group("attrs"))
        if m:
            toks |= {"." + c for c in m.group(1).split()}
        if toks:
            out.append((dm, toks))
    return out


def _rule4(text: str):
    """(span селектора, селектор, токен, match діалога, display) для кожного
    інлайнового правила показу, що діє на <dialog> без умови [open]."""
    dialogs = _dialog_tokens(text)
    if not dialogs:
        return []
    out = []
    for sm in STYLE_TAG_RX.finditer(text):
        css, base = sm.group(1), sm.start(1)
        for rm in CSS_RULE_RX.finditer(css):
            sel, body = rm.group(1), rm.group(2)
            d = DISPLAY_RX.search(body)
            if not d or d.group(1).lower() == "none":
                continue
            for dm, toks in dialogs:
                tok = next((t for t in toks
                            if any(_sel_shows_token(p, t)
                                   for p in sel.split(","))), None)
                if tok:
                    sel_disp = re.sub(r"/\*.*?\*/", "", sel, flags=re.S)
                    out.append(((base + rm.start(1), base + rm.end(1)),
                                sel_disp.strip(), tok, dm, d.group(1).lower()))
                    break
    return out


def _dialog_is_consent(text: str, dm) -> bool:
    end = text.find("</dialog", dm.end())
    scope = text[dm.start():end if end != -1 else dm.end() + 1500]
    return bool(CONSENT_RX.search(scope))


def run(path, text):
    issues = [{
        "line": text.count("\n", 0, m.start()) + 1, "severity": "error",
        "message": (f"кнопка згоди «{label}» нічого не робить: розмітка банера "
                    f"відрендерена у html, а обробник лишився у бандлі "
                    f"фреймворка, який у статиці не виконується (React/Next не "
                    f"гідратується; Wix Thunderbolt не добирає свій зовнішній "
                    f"бандл) — банер не закрити; фікс дасть банеру власний "
                    f"скрипт згоди"),
    } for m, label in _rule2(text)]
    seen = set()
    for m, broken, good in _rule3(text):
        if broken in seen:
            continue                            # одне повідомлення на ім'я
        seen.add(broken)
        issues.append({
            "line": text.count("\n", 0, m.start()) + 1, "severity": "error",
            "message": (f"у скрипті згоди зіпсовано ім'я API: «{broken}» замість "
                        f"«{good}» — у білтін вбито фрагмент назви вітки, скрипт "
                        f"падає з ReferenceError на першому рядку, тож банер не "
                        f"ховається і кнопка мертва; фікс повертає правильне ім'я"),
        })
    for m, _end, _label, _b in _rule7(text):
        decline_label = _banner_lang(text)[3]
        issues.append({
            "line": text.count("\n", 0, m.start()) + 1, "severity": "error",
            "message": (f"кукі-банер має лише «Прийняти» — QA вимагає й "
                        f"«Відхилити»; фікс додасть кнопку «{decline_label}» "
                        f"поруч у тому ж стилі, яка ховає банер і "
                        f"запам'ятовує відмову"),
        })
    for (s, _e), sel, tok, dm, val in _rule4(text):
        consent = _dialog_is_consent(text, dm)
        what = "кукі-банер" if consent else "діалог"
        issues.append({
            "line": text.count("\n", 0, s) + 1,
            "severity": "error" if consent else "warn",
            "message": (
                f"нативний <dialog> ({tok}) показаний CSS безумовно: правило "
                f"«{sel} {{ display:{val} }}» діє і без [open], перемагаючи "
                f"UA-правило dialog:not([open]){{display:none}} — close() знімає "
                f"open, а {what} однаково намальований і не закривається; фікс "
                f"скоупить правило показу на [open]"),
        })
    for m, _end in _flow_banners(text):
        issues.append({
            "line": text.count("\n", 0, m.start()) + 1, "severity": "error",
            "message": ("кукі-банер стоїть у ПОТОЦІ документа без "
                        "position:fixed — малюється останнім блоком «під "
                        "футером», а не поверх сторінки; фікс прибʼє його "
                        "до низу екрана інлайн-стилем"),
        })
    if _missing_banner(path, text):
        issues.append({
            "line": 1, "severity": "error",
            "message": ("на головній немає кукі-банера (ні контейнера згоди, "
                        "ні CMP-скрипта, ні інлайн-логіки) — фікс додасть "
                        "банер «Прийняти/Відхилити» мовою сторінки зі своїм "
                        "скриптом згоди"),
        })
    if not TAILWIND_CDN_RX.search(text):
        return issues                           # без CDN порядок каскаду інший
    hidden, _ = _analyze(text)
    if not hidden:
        return issues
    for m, _classes, hits, utils in _conflicts(text, hidden):
        cls, util = hits[0], utils[0]
        consent = bool(CONSENT_RX.search(m.group(0)))
        what = "кукі-банер" if consent else "елемент"
        issues.append({
            "line": text.count("\n", 0, m.start()) + 1,
            "severity": "error" if consent else "warn",
            "message": (
                f"«.{cls} {{display:none}}» ховає {what}, але в class= стоїть "
                f"Tailwind-утиліта «{util}» ({', '.join(utils)}) — стилі Tailwind CDN "
                f"додаються в <head> пізніше, за однакової специфічності (0,1,0) "
                f"перемагає утиліта, тож {what} не ховається: після «Прийняти» "
                f"localStorage пишеться, а банер лишається на екрані; є автофікс"),
        })
    return issues


# Власний скрипт згоди: короткий, без залежностей, ідемпотентний. Банер і
# кнопку позначаємо атрибутом, щоб скрипт не залежав від згенерованих
# класів (`style_Consent__cE_Gj` міняється з кожним білдом).
CONSENT_SCRIPT = (
    '<script data-qa_lab="' + MARKER + '">/* ' + MARKER + ' */\n'
    '(function(){var K="wp-cookie-consent";\n'
    '  function hide(){var b=document.querySelector(\'[%(a)s="banner"]\');\n'
    '    if(b&&b.parentNode)b.parentNode.removeChild(b);}\n'
    '  try{if(localStorage.getItem(K)){hide();return}}catch(e){}\n'
    '  document.addEventListener("click",function(e){\n'
    '    var c=e.target&&e.target.closest;\n'
    '    var ok=c?e.target.closest(\'[%(a)s="accept"]\'):null;\n'
    '    var no=c?e.target.closest(\'[%(a)s="decline"]\'):null;\n'
    '    if(!ok&&!no)return;\n'
    '    e.preventDefault();\n'
    '    var v=ok?"1":"0";\n'
    '    try{localStorage.setItem(K,v)}catch(e2){}\n'
    '    document.cookie=K+"="+v+";path=/;max-age=31536000";\n'
    '    hide();\n'
    '  },true);\n'
    '})();</script>\n') % {"a": CONSENT_ATTR}

BODY_CLOSE_RX = re.compile(r"</body\s*>", re.I)


def _mark(tag: str, value: str) -> str:
    """Дописує data-атрибут у відкривний тег, не чіпаючи решти."""
    if CONSENT_ATTR in tag.lower():
        return tag
    return tag[:-1].rstrip() + f' {CONSENT_ATTR}="{value}"' + tag[-1]


def _banner_start(text: str, at: int) -> re.Match | None:
    """Контейнер банера, який має зникнути після згоди.

    Найглибша обгортка кнопки для цього не годиться, і це заміряно в браузері на
    `bralobmgeon.com.br`: ланцюжок над кнопкою - `div.cst-action-decisive`
    (`display:contents`, висота 0) -> `div.cst-action-row` (32px) ->
    `div#cst-cookie-banner` (238px, і саме його видно) -> `div#consentik-cookie`.
    Позначивши найглибший, фікс прибирав рядок із кнопкою, а сам банер лишався
    на екрані - гірше за початковий стан, бо банер ставав ще й без кнопки.

    Тому серед обгорток беремо НАЙЗОВНІШНІШУ, чиї власні атрибути містять
    кукі-лексику (`id="consentik-cookie"`, `class="style_Consent__x"`): це і є
    межа віджета згоди, а не випадковий флекс-рядок усередині нього. Якщо
    лексики немає ні в кого - лишаємо давню поведінку (найглибша обгортка), щоб
    не втратити випадки з анонімною розміткою.
    """
    inner = named = None
    for m in BANNER_RX.finditer(text, max(0, at - 4000), at):
        if _element_end(text, m.group("tag"), m.end()) <= at:
            continue                            # закрився до кнопки - не обгортка
        inner = m
        if named is None and CONSENT_RX.search(m.group("attrs")):
            named = m                           # перший за текстом = найзовнішніший
    return named or inner


# ---------------------------------------------------------------- правило 5
# Найпростіша причина «кукі не працюють»: банера НЕМАЄ ВЗАГАЛІ. Скарги QA
# 02.10 (868mewn6p, 868mdy83f, 868mfb3zt): «На главной нет баннера куки —
# добавить баннер с кнопками "Принять" и "Отклонить"». Фікс додає власний
# бар: fixed до низу, текст мовою сторінки (<html lang>), кнопки
# Прийняти/Відхилити на нашому CONSENT_SCRIPT (без залежностей).
# ЛИШЕ коренева головна: index.html у підпапках — внутрішні сторінки
# (02.10: банер розлізся по saele/index.html усіх ch-de-2 віток)
HOME_RX = re.compile(r"^(?:index|home)\.(?:php|html?)$", re.I)
LANG_RX = re.compile(r"""<html\b[^>]*\blang\s*=\s*["']([a-zA-Z-]+)""", re.I)
# Голе «cookie» у src — фолс: WooCommerce тягне js-cookie (бібліотеку
# роботи з куками) на кожному магазині, CMP там немає (fuxjvik, 02.10).
# Матчимо або відомі CMP-вендори, або cookie-СЕМАНТИКУ згоди в імені.
COOKIE_SRC_RX = re.compile(
    r"""<script\b[^>]*\bsrc\s*=\s*["'][^"']*(?:consent|cmp|onetrust|
    cookiebot|iubenda|usercentrics|quantcast|didomi|klaro|complianz|
    cookie[-_]?(?:law|notice|banner|bar|policy|yes)|cookieconsent
    )[^"']*["']""", re.I | re.X)
I18N_BANNER = {
    "pt": ("Usamos cookies para melhorar a sua experiência. Veja a nossa",
           "Política de Cookies", "Aceitar", "Recusar"),
    "it": ("Utilizziamo i cookie per migliorare la tua esperienza. Leggi la",
           "Cookie Policy", "Accetta", "Rifiuta"),
    "de": ("Wir verwenden Cookies, um Ihr Erlebnis zu verbessern. Siehe",
           "Cookie-Richtlinie", "Akzeptieren", "Ablehnen"),
    "es": ("Usamos cookies para mejorar tu experiencia. Consulta la",
           "Política de Cookies", "Aceptar", "Rechazar"),
    "fr": ("Nous utilisons des cookies pour améliorer votre expérience. Voir la",
           "Politique de Cookies", "Accepter", "Refuser"),
    "ja": ("当サイトでは体験向上のためクッキーを使用しています。",
           "クッキーポリシー", "同意する", "拒否する"),
    "en": ("We use cookies to improve your experience. See our",
           "Cookie Policy", "Accept", "Decline"),
}
COOKIE_PAGE_RX = re.compile(
    r"""\bhref\s*=\s*["']([^"']*cookie[^"']*\.(?:html?|php))["']""", re.I)


def _is_home(path: str) -> bool:
    return bool(HOME_RX.search(path or ""))


def _has_banner(text: str) -> bool:
    """Чи є на сторінці БУДЬ-ЯКИЙ механізм згоди: наш маркер, інлайн-логіка,
    зовнішній CMP-скрипт або consent-контейнер з інтерактивом."""
    if MARKER in text or COOKIE_SRC_RX.search(text):
        return True
    if _has_inline_consent(text):
        return True
    for m in list(BANNER_RX.finditer(text)) + list(DIALOG_RX.finditer(text)):
        attrs = m.group("attrs")
        if not CONSENT_RX.search(attrs):
            continue
        end = _element_end(text, m.group("tag") if "tag" in m.groupdict()
                           and m.groupdict().get("tag") else "dialog", m.end())
        scope = text[m.end():end if end > 0 else m.end() + 2500]
        if re.search(r"<(?:button|a)\b", scope, re.I):
            return True
    return False


def _banner_lang(text: str) -> tuple:
    m = LANG_RX.search(text)
    code = (m.group(1) if m else "en").lower().split("-")[0]
    return I18N_BANNER.get(code, I18N_BANNER["en"])


def _missing_banner(path: str, text: str) -> bool:
    """Банера немає там, де він ОЧІКУЄТЬСЯ: на головній. Privacy-лінк
    більше НЕ умова: QA 02.10 (br-pt партія: aure, extermine, evidence,
    serralheria) вимагає банер і на вайтах без жодної privacy-сторінки.

    Заява «сайт не ставить кук» НЕ звільняє (02.10, hakrebqefozr і решта
    ch-de-2: QA вимагає банер попри шаблонний текст) — фікс разом із
    банером чистить і саму заяву, бо вона стає брехнею."""
    return (_is_home(path) and "<body" in text.lower()
            and not _has_banner(text))


_BTN_CLASS_RX = re.compile(
    r"""<(?:a|button)\b[^>]*\bclass\s*=\s*["']([^"']*\bbtn\b[^"']*|"""
    r"""[^"']*\b[\w-]+-btn\b[^"']*|[^"']*\bbutton\b[^"']*)["']""", re.I)
_CSS_ACCENT_RX = re.compile(
    r"--[\w-]*(?:primary|accent|brand|main)[\w-]*\s*:\s*"
    r"(#[0-9a-fA-F]{3,8}|rgba?\([^;)]*\))")
# Кнопки-іконки (пошук, бургер, стрілки слайдера): клас є, а заливки нема —
# incejuitkoufokidi (15.10): перший `*-btn` на сторінці був `.srch-btn
# {background:none;color:var(--grafite)}`, і «Aceitar» стало темним текстом
# на темному барі банера. QA: «текст зливається з фоном».
_ICONISH_RX = re.compile(
    r"(?:^|[-_])(?:srch|search|menu|burger|hamburger|close|toggle|icon|nav"
    r"|scroll|slider|arrow|prev|next|play|share)(?:$|[-_])", re.I)
# Клас-набір із утилітами розкладки (w-100, accordion/acordion, collapse,
# dropdown, btn-link, nav-link) — це кнопка-тогл, а не CTA: ligjo-mepmri
# (28.10) взяла `btn btn-link btn-acordion … w-100` з акордеона, і «Recusar»
# став рамкою на всю ширину банера, «Aceitar» — голим текстом.
_LAYOUT_CLS_RX = re.compile(
    r"(?:^|\s)(?:w-100|w-full|block|btn-block|btn-link|nav-link|navbar-[\w-]+"
    r"|accordion[\w-]*|acordion[\w-]*|collapse[\w-]*|dropdown[\w-]*"
    r"|justify-content-between)(?=\s|$)", re.I)
_BG_DECL_RX = re.compile(r"(?<![\w-])background(?:-color)?\s*:\s*([^;}]+)", re.I)
_NO_FILL_RX = re.compile(r"^(?:none|transparent|inherit|unset|initial)\b", re.I)


def _css_corpus(text: str, files: dict | None) -> str:
    return "\n".join(STYLE_TAG_RX.findall(text)) + "\n" + "\n".join(
        v for p, v in (files or {}).items() if p.lower().endswith(".css"))


def _class_fill(cls: str, css: str):
    """True — якийсь із класів кнопки має заливку; False — правила є, але
    заливки немає або вона прозора; None — правил не знайдено (css не в
    нас — класу довіряємо, як і раніше)."""
    seen = False
    for tok in cls.split():
        rx = re.compile(r"(?<![\w-])\." + re.escape(tok)
                        + r"(?![\w-])\s*(?:,[^{}]*)?\{([^{}]*)\}")
        for m in rx.finditer(css):
            seen = True
            for d in _BG_DECL_RX.finditer(m.group(1)):
                if not _NO_FILL_RX.match(d.group(1).strip()):
                    return True
    return False if seen else None


def _site_button_classes(text: str, files: dict | None = None) -> tuple:
    """(клас кнопки сайту, клас її line/outline-варіанта) або ("", "").
    Кнопки-іконки і класи без заливки пропускаються."""
    css = _css_corpus(text, files)
    for m in _BTN_CLASS_RX.finditer(text):
        cls = m.group(1).strip()
        base = cls.split()[0]
        if _ICONISH_RX.search(base) or _LAYOUT_CLS_RX.search(cls) \
                or _class_fill(cls, css) is False:
            continue
        vm = re.search(rf"""class\s*=\s*["']({re.escape(base)}\s+"""
                       rf"""{re.escape(base)}--?(?:line|outline|ghost|secondary)"""
                       rf""")["']""", text)
        return cls, (vm.group(1) if vm else "")
    return "", ""


def _site_accent(files: dict | None) -> str:
    """Акцентний колір з CSS-змінних вітки (--*primary/accent/brand)."""
    for p in sorted(files or {}):
        if not p.lower().endswith(".css"):
            continue
        m = _CSS_ACCENT_RX.search(files[p])
        if m:
            return m.group(1)
    return ""


def _consent_banner_html(text: str, files: dict | None = None) -> str:
    intro, policy, accept, decline = _banner_lang(text)
    pm = COOKIE_PAGE_RX.search(text)
    href = pm.group(1) if pm else None
    if not href:
        pv = re.search(r"""\bhref\s*=\s*["']([^"']*(?:privac|datenschutz|
                       privacidade)[^"']*\.(?:html?|php))["']""",
                       text, re.I | re.X)
        href = pv.group(1) if pv else None
    link = (f' <a href="{href}" style="color:inherit;text-decoration:'
            f'underline">{policy}</a>.') if href else ""
    bar = ('position:fixed;left:0;right:0;bottom:0;z-index:2147483000;'
           'display:flex;flex-wrap:wrap;gap:10px;align-items:center;'
           'justify-content:center;padding:14px 16px;'
           'background:rgba(17,24,39,.96);color:#fff;'
           'font:14px/1.45 system-ui,sans-serif')
    cls, cls_line = _site_button_classes(text, files)
    if cls:
        # кнопки у стилях ВІТКИ: клас сайту несе шрифт/колір/ховер
        acc_btn = (f'<button type="button" {CONSENT_ATTR}="accept" '
                   f'class="{cls}">{accept}</button>')
        dec_cls = cls_line or cls
        dec_extra = "" if cls_line else \
            ' style="background:transparent;color:#fff;border-color:#fff"'
        dec_btn = (f'<button type="button" {CONSENT_ATTR}="decline" '
                   f'class="{dec_cls}"{dec_extra}>{decline}</button>')
    else:
        btn = ("display:inline-block;padding:8px 18px;border-radius:6px;"
               "border:0;cursor:pointer;font:600 14px/1 system-ui,sans-serif")
        accent = _site_accent(files) or "#10b981"
        acc_btn = (f'<button type="button" {CONSENT_ATTR}="accept" '
                   f'style="{btn};background:{accent};color:#fff">'
                   f'{accept}</button>')
        dec_btn = (f'<button type="button" {CONSENT_ATTR}="decline" '
                   f'style="{btn};background:transparent;color:#fff;'
                   f'border:1px solid #6b7280">{decline}</button>')
    return (f'<div {CONSENT_ATTR}="banner" style="{bar}">'
            f'<span>{intro}{link}</span>{acc_btn}{dec_btn}</div>\n')


_NO_COOKIES_PHRASE_RX = re.compile(
    r"(?:\s*(?:und|and|et|e|y)\s+)?(?:(?:sie|it|ela|el)\s+)?"
    r"(?:setzt\s+keine\s+Cookies|does\s+not\s+use\s+cookies"
    r"|n[aã]o\s+(?:usa(?:mos)?|utiliza)\s+cookies"
    r"|no\s+(?:usa(?:mos)?|utilizamos)\s+cookies"
    r"|non\s+utilizza\s+(?:i\s+)?cookie|without\s+cookies"
    r"|keine\s+Cookies)", re.I)
# хвіст речення одразу після вирізаної фрази: «  , und» / « .» — лише тут
# і прибираємо зайвий пробіл/подвійний розділовий знак
_TAIL_RX = re.compile(r"\s*([,;.])(?:\s*([,;.]))?")


def _strip_no_cookies(text: str) -> str:
    """Вирізає фразу «не ставить кук» (разом зі сполучником перед нею):
    після вставки банера вона бреше. Решта речення лишається цілою.

    Чистка розділових знаків — ТІЛЬКИ на місці вирізу. До 19.10 вона
    бігла по всьому документу (`\\s+([,;.])` → `\\1`) і склеювала CSS
    descendant-селектори у <style>: `.nav .brand` → `.nav.brand`
    (incejuitkoufokidi, ladehavdpafnacesia, nesrrgifaj — «верстка
    поїхала» після кукі-фікса)."""
    out, last = [], 0
    for m in _NO_COOKIES_PHRASE_RX.finditer(text):
        out.append(text[last:m.start()])
        tail = _TAIL_RX.match(text, m.end())
        if tail:
            out.append(tail.group(2) or tail.group(1))
            last = tail.end()
        else:
            last = m.end()
    out.append(text[last:])
    return "".join(out)


def _fix_missing_banner(path: str, text: str,
                        files: dict | None = None) -> str:
    if not _missing_banner(path, text):
        return text
    bm = BODY_CLOSE_RX.search(text)
    if not bm:
        return text
    text = _strip_no_cookies(text)
    bm = BODY_CLOSE_RX.search(text)
    ins = _consent_banner_html(text, files) + CONSENT_SCRIPT
    return text[:bm.start()] + ins + text[bm.start():]


# ---------------------------------------------------------------- правило 6
# «Баннер куки улетел под футер» (868mdy83f): банер у ПОТОЦІ документа при
# кінці <body> — без position:fixed він малюється ПІСЛЯ футера як звичайний
# блок. Фікс прибиває його до низу екрана інлайн-стилем (перемагає класи).
FIXEDISH_RX = re.compile(r"position\s*:\s*(?:fixed|sticky)|\b(?:fixed|sticky)\b")
STYLE_ATTR_RX = re.compile(r"""\bstyle\s*=\s*(["'])(.*?)\1""", re.I | re.S)


_POS_RX = re.compile(r"position\s*:\s*(fixed|sticky)", re.I)
_NONE_RX = re.compile(r"display\s*:\s*none", re.I)
# банер вимагається лише там, де сайт тему заявив: лінк на cookie- або
# privacy-сторінку. Сайт із прямою заявою «кук не ставимо» — не чіпаємо.
PRIVACY_PAGE_RX = re.compile(
    r"""\bhref\s*=\s*["'][^"']*(?:cookie|privac|datenschutz|privacidade|
    politica-de-privacidade)[^"']*\.(?:html?|php)["']""", re.I | re.X)
NO_COOKIES_RX = re.compile(
    r"keine\s+Cookies|n[aã]o\s+(?:usa(?:mos)?|utiliza)\s+cookies"
    r"|no\s+(?:usa(?:mos)?|utilizamos)\s+cookies|non\s+utilizza\s+(?:i\s+)?cookie"
    r"|does\s+not\s+use\s+cookies|without\s+cookies", re.I)


def _flow_banners(text: str):
    """[(match, 0)] НАШИХ банерів (data-wp-consent="banner") без
    position:fixed в інлайн-стилі — страховка від «улетів під футер»
    (868mdy83f). Чужі банери стилізуються зовнішнім CSS, якого сторінка не
    показує, — їх не судимо, щоб не фолсити."""
    out = []
    for m in re.finditer(
            rf"""<div\b[^>]*{CONSENT_ATTR}\s*=\s*["']banner["'][^>]*>""",
            text, re.I):
        tag = m.group(0)
        if _POS_RX.search(tag):
            continue
        out.append((m, 0))
    return out


def _fix_flow_banner(text: str) -> str:
    out, last = [], 0
    for m, _end in _flow_banners(text):
        tag = m.group(0)
        sm = STYLE_ATTR_RX.search(tag)
        pin = "position:fixed;left:0;right:0;bottom:0;z-index:2147483000;"
        if sm:
            new_tag = tag[:sm.start(2)] + pin + tag[sm.start(2):]
        else:
            new_tag = tag[:-1].rstrip() + f' style="{pin}"' + tag[-1]
        out.append(text[last:m.start()])
        out.append(new_tag)
        last = m.end()
    out.append(text[last:])
    return "".join(out)


# ---------------------------------------------------------------- правило 7
# «Нет "отклонить"» (QA 27.10, br-pt партія: fia-de-sevga-marrat-br-pt,
# soba-lezo-picazos-br-pt): банер згоди робочий і закривається, але на ньому
# ОДНА кнопка - «Aceitar»/«Entendi». QA вимагає рівноправну «Отклонить».
# Фікс не чіпає чужий обробник accept: поруч клонується друга кнопка в
# тому самому стилі, позначена data-wp-consent="decline" - наш CONSENT_SCRIPT
# (уже вміє ховати банер і писати localStorage/cookie і для accept, і для
# decline) ховає банер і запам'ятовує відмову так само, як запам'ятовує згоду.
DECLINE_ATTR_RX = re.compile(rf'{CONSENT_ATTR}\s*=\s*["\']decline["\']', re.I)
_DROP_ATTR_RX = re.compile(
    r'\s+(?:id|onclick|href|aria-label|title|name|value'
    r'|data-[\w-]*(?:accept|agree|consent|cookie|allow|yes|ok)[\w-]*)'
    r'(?:\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+))?(?=[\s>])', re.I)


def _has_decline(scope: str) -> bool:
    """Чи є в межах банера decline-контроль: наш атрибут або підпис мовою
    DECLINE_RX на <button>/<a>."""
    if DECLINE_ATTR_RX.search(scope):
        return True
    for m in OPEN_TAG_RX.finditer(scope):
        end = _closing(scope, m.group("tag"), m.end())
        if end < 0:
            continue
        label = " ".join(TAGS_RX.sub(" ", scope[m.end():end]).split())
        if label and len(label) <= 34 and DECLINE_RX.search(label):
            return True
    return False


def _missing_decline(text: str):
    """(match accept-тега, кінець accept-елемента, підпис, match банера) для
    банерів, де є «Прийняти», але немає жодного «Відхилити».

    Вимагаємо лінк на cookie-/privacy-сторінку (PRIVACY_PAGE_RX) - так само,
    як правило 6: це межа між ПОВНИМ банером сайту (сторінка-політика є,
    текст описує збір даних) і мінімальним технічним фрагментом з інших
    правил (мертва кнопка, dialog, display-конфлікт), де самого банера як
    завершеного UI-блока ще нема і «Відхилити» дописувати нема куди."""
    if not PRIVACY_PAGE_RX.search(text):
        return
    seen = set()
    for m, label in _accept_controls(text):
        end = _closing(text, m.group("tag"), m.end())
        if end < 0:
            continue
        b = _banner_start(text, m.start())
        if b is None:
            continue                            # немає контейнера - нема куди клонувати
        key = (b.start(), b.end())
        if key in seen:
            continue
        bend = _element_end(text, b.group("tag"), b.end())
        scope = text[b.start():bend if bend != -1 else len(text)]
        if _has_decline(scope):
            continue
        seen.add(key)
        yield m, end, label, b


def _rule7(text: str):
    return list(_missing_decline(text))


def _clone_decline_tag(tag_text: str, decline_label: str) -> str:
    """Клонує відкривний тег accept-кнопки: той самий тег і class=, без
    id/onclick/href, з decline-атрибутом; інлайновий фон (якщо був)
    замінюється на прозорий контур, щоб не повторювати акцентний колір."""
    tm = re.match(r"<(\w+)\b", tag_text)
    tag_name = tm.group(1)
    attrs = _DROP_ATTR_RX.sub("", tag_text[tm.end():-1])
    sm = STYLE_ATTR_RX.search(attrs)
    if sm and "background" in sm.group(2).lower():
        q = sm.group(1)
        override = (f'style={q}background:transparent;color:inherit;'
                    f'border:1px solid currentColor{q}')
        attrs = attrs[:sm.start()] + override + attrs[sm.end():]
    return (f'<{tag_name}{attrs} {CONSENT_ATTR}="decline">'
            f'{decline_label}</{tag_name}>')


def _fix_missing_decline(text: str) -> str:
    hits = _rule7(text)
    if not hits:
        return text
    decline_label = _banner_lang(text)[3]
    edits = {}
    for m, end, _label, b in hits:
        edits[(end, end)] = _clone_decline_tag(m.group(0), decline_label)
        edits.setdefault((b.start(), b.end()), _mark(b.group(0), "banner"))
    out, last = [], 0
    for (s, e), rep in sorted(edits.items()):
        out.append(text[last:s])
        out.append(rep)
        last = e
    out.append(text[last:])
    new = "".join(out)
    if MARKER in new:
        return new
    bm = BODY_CLOSE_RX.search(new)
    if bm:
        return new[:bm.start()] + CONSENT_SCRIPT + new[bm.start():]
    return new + CONSENT_SCRIPT



def _fix_dead_accept(text: str) -> str:
    hits = _rule2(text)
    if not hits:
        return text
    edits = {}                                  # позиція тега -> новий тег
    for m, _label in hits:
        edits[(m.start(), m.end())] = _mark(m.group(0), "accept")
        b = _banner_start(text, m.start())
        if b is not None:
            edits.setdefault((b.start(), b.end()), _mark(b.group(0), "banner"))
    out, last = [], 0
    for (s, e), tag in sorted(edits.items()):
        out.append(text[last:s])
        out.append(tag)
        last = e
    out.append(text[last:])
    new = "".join(out)
    m = BODY_CLOSE_RX.search(new)
    if m:
        return new[:m.start()] + CONSENT_SCRIPT + new[m.start():]
    return new + CONSENT_SCRIPT


def _fix_broken_builtin(text: str) -> str:
    """Повертає правильні імена API. Ремонт точковий: міняється лише сам
    ідентифікатор, решта скрипта не чіпається."""
    out, last = [], 0
    for m, _broken, good in _rule3(text):
        out.append(text[last:m.start()])
        out.append(good)
        last = m.end()
    if not out:
        return text
    out.append(text[last:])
    return "".join(out)


def _scope_part(part: str, tok: str) -> str:
    """Дописує [open] до токена в останній простій послідовності варіанта
    селектора; хвостові пробіли частини лишаються на місці."""
    core = part.rstrip()
    tail = part[len(core):]
    last = LAST_SEQ_RX.search(core)
    if not last or "[open]" in core:
        return part
    seq = last.group(0)
    i = seq.find(tok)
    while i != -1:
        nxt = seq[i + len(tok):i + len(tok) + 1]
        if not nxt or not (nxt.isalnum() or nxt in "_-"):
            seq = seq[:i + len(tok)] + "[open]" + seq[i + len(tok):]
            return core[:last.start()] + seq + core[last.end():] + tail
        i = seq.find(tok, i + 1)
    return part


def _fix_unconditional_dialog(text: str) -> str:
    """Скоупить правила показу діалога на [open]: міняється лише селектор,
    тіло правила і решта CSS не чіпаються."""
    out, last = [], 0
    for (s, e), _sel, tok, _dm, _val in _rule4(text):
        raw = text[s:e]
        out.append(text[last:s])
        out.append(",".join(_scope_part(p, tok) for p in raw.split(",")))
        last = e
    if not out:
        return text
    out.append(text[last:])
    return "".join(out)


def fix(path, text):
    """По-файлові фікси: повернути ім'я API (правило 3), скоупити правило
    показу <dialog> на [open] (правило 4), дати банеру власний скрипт
    згоди (правило 2), додати відсутню кнопку «Відхилити» поруч з
    «Прийняти» (правило 7), прибити банер-у-потоці до низу (правило 6),
    прибрати display-утиліту (правило 1). Вставка відсутнього банера
    (правило 5) живе у fix_branch: їй потрібні css-файли вітки для
    стилів сайту."""
    text = _fix_broken_builtin(text)
    text = _fix_unconditional_dialog(text)
    text = _fix_dead_accept(text)
    text = _fix_missing_decline(text)
    text = _fix_flow_banner(text)
    if not TAILWIND_CDN_RX.search(text):
        return text
    hidden, shown = _analyze(text)
    if not hidden:
        return text
    out, last = [], 0
    for m, classes, hits, _utils in _conflicts(text, hidden):
        # немає правила показу (.X.Y{display:…}) — утиліта може бути єдиним
        # джерелом display для показаного стану, прибирати її небезпечно
        if not any(c in shown for c in hits):
            continue
        quote = m.group(2)[0]
        kept = " ".join(c for c in classes if c not in SHOW_UTILS)
        out.append(text[last:m.start(2)])
        out.append(quote + kept + quote)
        last = m.end(2)
    out.append(text[last:])
    return "".join(out)


def fix_branch(files, all_paths, branch=""):
    """Правило 5: банер, якого немає, стає на головну У СТИЛЯХ вітки —
    кнопковий клас сайту (av-btn тощо) або акцент з css-змінних."""
    actions = []
    for path in sorted(files):
        if not _is_home(path):
            continue
        text = files[path]
        new = _fix_missing_banner(path, text, files)
        if new != text:
            actions.append({"type": "edit", "path": path, "content": new})
    return actions
