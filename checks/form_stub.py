"""Форма-заглушка: лід не перехоплюється, форма «відправляє» вигляду.

Зразок — favojuug.net/contacts (20.10): клік по «Nachricht senden» →
кнопка «Wird gesendet…» disabled ≈1.3 с → форма зникає, на її місці
«✓ Nachricht erfolgreich gesendet / Vielen Dank … zwei Werktagen»; у
мережу не йде нічого.

Що робить фікс на php-вайті:
  1. PHP. З init-блоку прибираються `$returnPage` і `$facebookPixelEventLeadKey`
     (fbpixelevent); body-блок `if (isset($_GET['email']) …) { … exit(); }`
     (лід-пікселі + redirect) вирізається цілком. `$isDev`/dotenv,
     `$trackingConfig` і head-пікселі (fbq init / gtag config = перегляди)
     ЛИШАЮТЬСЯ — сайт і далі рахує відвідування з .env.
  2. Форма. У кожному <form> (крім пошуку/newsletter з одним полем):
     action/method/onsubmit знімаються, додається data-<id>="1"; у кінець
     <body> — один скрипт (без маркерів; id вітки з form_stub_ids.json): submit →
     preventDefault, кнопка disabled з текстом «Enviando…», через 1.4 с
     або redirect на сторінку подяки вітки (thank-you/obrigado/merci/
     danke/grazie/gracias — якщо файл є), або форма ховається і на її
     місці блок «✓ Mensagem enviada» + «Retornaremos em até 2 dias úteis»
     мовою вітки, у стилях форми (клас контейнера форми клонуємо).

Чек ВИМКНЕНИЙ за замовчуванням (група review): він суперечить штатному
флоу (php_scripts / forms / form_flow / thanks_route / form_action /
form_hijack вимагають перехоплення ліда). Увімкнений на вітці — ті чеки
мовчать, впізнавши заглушку за структурою скрипта (is_stubbed).
"""
import re

NAME = "Форма-заглушка (без перехоплення ліда)"
# review, не auto: черга (CU_QUEUE_GROUPS=auto,tests) ганяє ВСІ auto-чеки на
# кожній вітці таски, і «Apply» різав би лід-PHP на кожній php-вітці з формою.
# QA-клас «після відправки нічого не видно / нема подяки» веде сюди (вердикт
# tsm thankyou), окремий чек return_page прибрано 21.10; застосовує людина.
GROUP = "review"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Вирізає з index.php лід-частину PHP ($returnPage, fbpixelevent, "
               "блок isset($_GET['email']) з лід-пікселями і redirect), лишаючи "
               "dotenv/trackingConfig/head-пікселі; форми стають заглушками: "
               "«Enviando…» 1.4 с → redirect на сторінку подяки вітки або inline "
               "«✓ Mensagem enviada» мовою вітки. Група review — застосовує людина.")
FILES = ["*.html", "*.htm", "*.php"]

# Жодного спільного маркера на всіх вайтах: атрибут форми, ім'я dataset і
# підпис скрипта — слово з літер, детерміноване за віткою (crc32) і
# закешоване у form_stub_ids.json (повторний фікс тієї самої вітки дає
# той самий id). Заглушку інші чеки впізнають за СТРУКТУРОЮ скрипта
# (is_stubbed), а не за рядком.
_ID_FILE = "form_stub_ids.json"
_ALPHA = "abcdefghjkmnpqrstuvwxyz"


def _id_path():
    import projects
    return projects.state_root() / _ID_FILE


def stub_id(branch: str) -> str:
    """6-літерне слово для вітки: з кешу, інакше з crc32 (і в кеш)."""
    import json
    import zlib
    try:
        ids = json.loads(_id_path().read_text(encoding="utf-8"))
    except Exception:
        ids = {}
    key = branch or "x"
    if ids.get(key):
        return ids[key]
    n = zlib.crc32(key.encode("utf-8"))
    word = ""
    for _ in range(6):
        word += _ALPHA[n % len(_ALPHA)]
        n //= len(_ALPHA)
    ids[key] = word
    try:
        _id_path().parent.mkdir(parents=True, exist_ok=True)
        _id_path().write_text(json.dumps(ids, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return word


# структурний відбиток заглушки: inline-скрипт, що бере form[data-<id>],
# глушить submit і через затримку показує подяку/редіректить
# Структурний відбиток заглушки (однаковий для всіх 50 варіантів):
# один inline-скрипт, у якому є ВСІ три маркери в будь-якому порядку —
# querySelectorAll("form[data-<id>]"), preventDefault() і setTimeout(.
STUB_SCRIPT_RX = re.compile(
    r"""<script\b[^>]*>(?=(?:(?!</script>).)*?querySelectorAll\("form\[data-([a-z]{6})\]"\))"""
    r"""(?=(?:(?!</script>).)*?preventDefault\(\))"""
    r"""(?:(?!</script>).)*?setTimeout\((?:(?!</script>).)*?</script>""",
    re.S)
STUB_FORM_RX = re.compile(r"""<form\b[^>]*\sdata-([a-z]{6})(?:=["']?1["']?)?(?=[\s>])""", re.I)


def _form_stubbed(form_html: str, page_text: str) -> bool:
    """Форма заглушена, лише коли її data-<id> ЗБІГАЄТЬСЯ з id скрипта заглушки
    на цій сторінці. Будь-які 6 літер (`data-pccyjz="1"` зі scoped-рендера
    Vue — semence/releve ch-fr 27.10) без скрипта — жива форма."""
    sid = _page_id(page_text)
    if not sid:
        return False
    return any(m.group(1).lower() == sid for m in STUB_FORM_RX.finditer(form_html[:400]))


def is_stubbed(text: str) -> bool:
    """Чи сторінка вже несе заглушку (для гейтів інших чеків)."""
    return bool(STUB_SCRIPT_RX.search(text))


def is_lead_cut(text: str) -> bool:
    """Головна ПІСЛЯ заглушки, коли сама лід-форма на іншій сторінці (контакти):
    $trackingConfig лишився, а $returnPage / isset($_GET['email']) вирізано.
    Штатний шаблон завжди має всі три разом, тож така форма — свідомий зріз."""
    return ("$trackingConfig" in text and "WHITE_FORM_RETURN_PAGE" not in text
            and "isset($_GET['email'])" not in text)


def _page_id(text: str) -> str:
    m = STUB_SCRIPT_RX.search(text)
    return m.group(1) if m else ""

PHP_BLOCK_RX = re.compile(r"<\?php\b[\s\S]*?\?>")
LEAD_BLOCK_RX = re.compile(r"\n?[ \t]*<\?php\s*\n?\s*if\s*\(\s*isset\(\$_GET\['email'\]\)[\s\S]*?exit\(\);\s*\}\s*\?>[ \t]*\n?")
RETURN_PAGE_RX = re.compile(r"\n\$returnPage\s*=\s*\$_ENV\['WHITE_FORM_RETURN_PAGE'\][^\n]*\n(?:if\s*\(!str_ends_with\(\$returnPage[^\n]*\n[^\n]*\n\}\n)?")
FBEVENT_RX = re.compile(r"\n\$facebookPixelEventLeadKey\s*=\s*null;\n(?:if\s*\(!empty\(\$_GET\['fbpixelevent'\]\)[^\n]*\n[^\n]*\n\}\n)?")
FORM_RX = re.compile(r"<form\b((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.I)
FORM_FULL_RX = re.compile(r"<form\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>[\s\S]*?</form>", re.I)
ATTR_STRIP_RX = re.compile(r"""\s+(?:action|method|onsubmit|enctype|target)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.I)
BODY_CLOSE_RX = re.compile(r"</body\s*>", re.I)
LANG_RX = re.compile(r"""<html\b[^>]*\blang\s*=\s*["']([a-zA-Z-]+)""", re.I)
_LOCALE_RX = re.compile(r"[-.]([a-z]{2})-([a-z]{2})(?:-\d+)?$")
THANKS_RX = re.compile(r"(?:^|/)(?:thank-?you|thanks|obrigad[oa]|merci|danke|grazie|gracias|agradecimento|agradecimiento)(?:/index)?\.html?$", re.I)
SEARCHISH_RX = re.compile(r"""type\s*=\s*["']search["']|role\s*=\s*["']search["']|name\s*=\s*["'](?:q|s|search|query)["']""", re.I)

I18N = {
    "pt": ("Enviando…", "Mensagem enviada", "Obrigado pelo contato. Nossa equipe retornará em até 2 dias úteis."),
    "es": ("Enviando…", "Mensaje enviado", "Gracias por contactarnos. Nuestro equipo responderá en un plazo de 2 días hábiles."),
    "en": ("Sending…", "Message sent", "Thank you for your message. Our team will get back to you within 2 business days."),
    "de": ("Wird gesendet…", "Nachricht erfolgreich gesendet", "Vielen Dank für Ihre Nachricht. Unser Team meldet sich innerhalb von zwei Werktagen bei Ihnen."),
    "fr": ("Envoi en cours…", "Message envoyé", "Merci pour votre message. Notre équipe vous répondra sous 2 jours ouvrés."),
    "it": ("Invio in corso…", "Messaggio inviato", "Grazie per averci contattato. Il nostro team risponderà entro 2 giorni lavorativi."),
    "hr": ("Slanje…", "Poruka poslana", "Hvala na poruci. Naš tim će vam se javiti u roku od 2 radna dana."),
    "nl": ("Verzenden…", "Bericht verzonden", "Bedankt voor uw bericht. Ons team neemt binnen 2 werkdagen contact met u op."),
    "ja": ("送信中…", "送信が完了しました", "お問い合わせありがとうございます。2営業日以内にご連絡いたします。"),
    "ar": ("جارٍ الإرسال…", "تم إرسال الرسالة", "شكرًا لتواصلك معنا. سيرد عليك فريقنا خلال يومي عمل."),
}


def _lang(text: str, branch: str) -> str:
    m = LANG_RX.search(text)
    code = (m.group(1) if m else "").lower().split("-")[0]
    if code in I18N and code != "en":
        return code
    lm = _LOCALE_RX.search((branch or "").lower())
    tail = lm.group(2) if lm else ""
    return tail if tail in I18N else (code if code in I18N else "en")


def _thanks_page(all_paths, path: str) -> str:
    """Відносний href сторінки подяки вітки з файлу path; '' — нема."""
    cands = sorted(p for p in (all_paths or []) if THANKS_RX.search(p.replace("\\", "/")))
    if not cands:
        return ""
    target = cands[0]
    depth = path.replace("\\", "/").count("/")
    return "../" * depth + target


def _is_lead_form(form_html: str) -> bool:
    """Форма збору даних, а не пошук/розсилка: ≥2 поля вводу або textarea."""
    if SEARCHISH_RX.search(form_html):
        return False
    fields = re.findall(r"<(?:input|textarea|select)\b[^>]*>", form_html, re.I)
    fields = [f for f in fields if not re.search(r"""type\s*=\s*["'](?:hidden|submit|button|reset|checkbox|radio)["']""", f, re.I)]
    return len(fields) >= 2 or bool(re.search(r"<textarea\b", form_html, re.I))


def variant_index(branch: str) -> int:
    """Детермінований індекс варіанта скрипта (0..49) за назвою вітки.
    Той самий вайт завжди отримує той самий варіант; різні — різні."""
    import zlib
    import checks._form_stub_variants as _v
    return zlib.crc32((branch or "x").encode("utf-8")) % len(_v.VARIANTS)


def _stub_script(lang: str, thanks: str, sid: str, branch: str = "") -> str:
    """Один із 50 варіантів скрипта (checks/form_stub_variants). Варіант
    фіксується за віткою — не вгадаєш з сайту, який саме наступний."""
    import checks._form_stub_variants as _v
    return _v.render(variant_index(branch), sid, I18N[lang], thanks)


# ---------------------------------------------------------------- детект
def _lead_php_present(text: str) -> bool:
    return bool(LEAD_BLOCK_RX.search(text) or RETURN_PAGE_RX.search(text) or FBEVENT_RX.search(text))


def _live_forms(text: str) -> list:
    return [m for m in FORM_FULL_RX.finditer(text)
            if _is_lead_form(m.group(0)) and not _form_stubbed(m.group(0), text)]


def _has_lead_form(files: dict) -> bool:
    """Є хоч одна лід-форма (жива або вже заглушена) на будь-якій сторінці."""
    return any(_is_lead_form(m.group(0))
               for t in files.values() for m in FORM_FULL_RX.finditer(t))


def run_branch(files, all_paths, branch: str = ""):
    if not _has_lead_form(files):
        return []                        # без форми нема що глушити — і PHP не чіпаємо
    issues = []
    for path in sorted(files):
        text = files[path]
        is_index = path.lower() in ("index.php", "index.html")
        php_lead = is_index and _lead_php_present(text)
        live = _live_forms(text)
        if not php_lead and not live:
            continue
        what = []
        if php_lead:
            what.append("PHP перехоплює лід ($_GET → пікселі → redirect)")
        if live:
            what.append(f"{len(live)} форм(и) без заглушки")
        issues.append({"path": path, "line": 1, "severity": "warn",
                       "message": ", ".join(what) + " — фікс виріже лід-PHP і зробить "
                                  "форму заглушкою («Enviando…» → подяка), трекінг переглядів лишиться"})
    return issues


# ---------------------------------------------------------------- фікс
def _strip_lead_php(text: str) -> str:
    new = LEAD_BLOCK_RX.sub("\n", text, count=1)
    new = RETURN_PAGE_RX.sub("\n", new, count=1)
    new = FBEVENT_RX.sub("\n", new, count=1)
    return new


def _stub_forms(text: str, lang: str, thanks: str, sid: str, branch: str = "") -> str:
    changed = False

    def one(m):
        nonlocal changed
        full = m.group(0)
        if not _is_lead_form(full):
            return full
        om = FORM_RX.match(full)
        attrs = om.group(1)
        if _form_stubbed(full, text):
            return full
        cleaned = ATTR_STRIP_RX.sub("", attrs)
        changed = True
        return f'<form{cleaned} data-{sid}="1">' + full[om.end():]

    new = FORM_FULL_RX.sub(one, text)
    if changed and not is_stubbed(new):
        bm = BODY_CLOSE_RX.search(new)
        script = _stub_script(lang, thanks, sid, branch)
        new = (new[:bm.start()] + script + new[bm.start():]) if bm else new + script
    return new


def apply(text: str, path: str, all_paths, branch: str = "",
          strip_php: bool = True, stub: bool = True) -> str:
    """Одна сторінка: вирізати лід-PHP (лише головна) і/або заглушити форми.
    Обидва кроки незалежні — «Головна під форму» вмикає їх окремими прапорцями."""
    new = text
    if strip_php and path.lower() in ("index.php", "index.html"):
        new = _strip_lead_php(new)
    if stub:
        new = _stub_forms(new, _lang(new, branch), _thanks_page(all_paths, path),
                          stub_id(branch), branch)
    return new


def fix_branch(files, all_paths, branch: str = ""):
    if not _has_lead_form(files):
        return []
    actions = []
    for path in sorted(files):
        new = apply(files[path], path, all_paths, branch)
        if new != files[path]:
            actions.append({"type": "edit", "path": path, "content": new})
    return actions
