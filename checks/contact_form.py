"""На сайті немає жодної контактної форми: додати секцію з формою.

QA-клас «На сайте нет контактной формы. Добавить форму заявки» (28.10,
12 php-веток: br-pt-партія — bahe-folti, arbiidelgiso-navoadaz,
clugseze-rio, prirskawa-tamocu, inpiloew-em-paudu, cuqmuse-mopi-pluj,
ofekire-do-foni, teep-seslamaro-rezom, orrouloi-vija; it-it —
bukjima-itunui; jp — cluakoje, caxe-hycoora). Деякі з цих веток уже
отримують форму вручну паралельно — чек дивиться на `form_stub._is_lead_form`
по ВСІХ сторінках і мовчить, щойно форма з'явилась будь-де (навіть на
/contato, а не тільки на головній).

Правило. Лід-форми на сайті нема взагалі (ні на головній, ні на жодній
іншій сторінці; пошукові/newsletter-форми з одним полем — не рахуються,
той самий фільтр form_stub._is_lead_form) → одна issue на головній.
Фікс вставляє перед футером головної самодостатню `<section>` (унікальний
id-якір мовою сторінки: contato/contacto/kontakt/contatti/contact, клас
`.qa_lab-contact`) з заголовком, одним реченням ліда і формою (ім'я, e-mail,
телефон, повідомлення) у стилях сайту (успадкований шрифт, акцентний
колір кнопки з `--primary`/`.btn{background:…}` вітки, інакше #2563eb;
темний фон сторінки — світлий текст). Форма без action/method, тож одразу
після вставки чек передає сторінку `form_stub.apply(..., stub=True)` —
форма стає заглушкою («Enviando…» → подяка), як і всі лід-форми вітки.

Де футер: перший `<footer`, інакше евристика `legal_pages._footer_span`,
інакше перед `</body>`. Юридичні сторінки й гілки з уже наявною
лід-формою (будь-де) фікс не чіпає.
"""
import re

NAME = "Немає контактної форми на сайті"
GROUP = "auto"
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("На сайті немає жодної лід-форми (ні на головній, ні деінде) — "
               "фікс додасть перед футером головної секцію з формою (ім'я, e-mail, "
               "телефон, повідомлення) у стилях сайту (акцент кнопки з CSS вітки) "
               "і одразу заглушить її (форма «відправляється», подяка без бекенду).")
FILES = ["*.html", "*.htm", "*.php"]

HOME_NAMES = ("index.php", "index.html", "index.htm")
FOOTER_TAG_RX = re.compile(r"<footer\b", re.I)
BODY_CLOSE_RX = re.compile(r"</body\s*>", re.I)

ID_MAP = {
    "pt": "contato", "es": "contacto", "it": "contatti", "de": "kontakt",
    "hr": "kontakt", "fr": "contact", "en": "contact", "nl": "contact",
    "ja": "contact", "ar": "contact",
}

LABELS = {
    "pt": ("Fale conosco", "Preencha o formulário e nossa equipe entrará em contato.",
           "Nome", "E-mail", "Telefone", "Mensagem", "Enviar"),
    "es": ("Contáctanos", "Completa el formulario y nuestro equipo se pondrá en contacto contigo.",
           "Nombre", "Correo electrónico", "Teléfono", "Mensaje", "Enviar"),
    "en": ("Contact us", "Fill out the form and our team will get back to you.",
           "Name", "Email", "Phone", "Message", "Send"),
    "de": ("Kontaktieren Sie uns", "Füllen Sie das Formular aus, unser Team meldet sich bei Ihnen.",
           "Name", "E-Mail", "Telefon", "Nachricht", "Senden"),
    "fr": ("Contactez-nous", "Remplissez le formulaire, notre équipe vous recontactera.",
           "Nom", "E-mail", "Téléphone", "Message", "Envoyer"),
    "it": ("Contattaci", "Compila il modulo, il nostro team ti risponderà.",
           "Nome", "E-mail", "Telefono", "Messaggio", "Invia"),
    "hr": ("Kontaktirajte nas", "Ispunite obrazac, naš tim će vam se javiti.",
           "Ime", "E-mail", "Telefon", "Poruka", "Pošalji"),
    "nl": ("Neem contact op", "Vul het formulier in, ons team neemt contact met u op.",
           "Naam", "E-mail", "Telefoon", "Bericht", "Verzenden"),
    "ja": ("お問い合わせ", "フォームにご記入いただければ、担当者よりご連絡いたします。",
           "お名前", "メールアドレス", "電話番号", "メッセージ", "送信"),
    "ar": ("اتصل بنا", "املأ النموذج وسيتواصل معك فريقنا.",
           "الاسم", "البريد الإلكتروني", "الهاتف", "الرسالة", "إرسال"),
}

_BTN_BG_RX = re.compile(
    r"\.btn\b[^{}]*\{[^{}]*?background(?:-color)?\s*:\s*"
    r"(#[0-9a-fA-F]{3,8}|rgba?\([^;)]*\))", re.I)
_BODY_BG_RX = re.compile(
    r"(?:^|[\s,}])body\b[^{}]*\{[^{}]*?background(?:-color)?\s*:\s*([^;}]+)", re.I)

_FORM_TMPL = """<section id="{anchor}" class="qa_lab-contact">
  <style>
    .qa_lab-contact {{ font: inherit; max-width: 720px; margin: 40px auto; padding: 0 16px; {txt_color} }}
    .qa_lab-contact h2 {{ font: inherit; font-size: 1.6em; margin: 0 0 8px; }}
    .qa_lab-contact p {{ font: inherit; margin: 0 0 20px; opacity: .85; }}
    .qa_lab-contact form {{ display: flex; flex-direction: column; gap: 12px; }}
    .qa_lab-contact label {{ font: inherit; font-size: .9em; display: block; margin-bottom: 4px; }}
    .qa_lab-contact input, .qa_lab-contact textarea {{ font: inherit; width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid {border}; border-radius: 8px; background: {field_bg}; color: {field_color}; }}
    .qa_lab-contact textarea {{ min-height: 120px; resize: vertical; }}
    .qa_lab-contact button {{ font: inherit; align-self: flex-start; padding: 10px 24px; border: 0; border-radius: 8px; background: {accent}; color: #fff; cursor: pointer; }}
  </style>
  <h2>{heading}</h2>
  <p>{lead}</p>
  <form>
    <div>
      <label for="qa_lab-name">{lbl_name}</label>
      <input id="qa_lab-name" type="text" name="name" required>
    </div>
    <div>
      <label for="qa_lab-email">{lbl_email}</label>
      <input id="qa_lab-email" type="email" name="email" required>
    </div>
    <div>
      <label for="qa_lab-phone">{lbl_phone}</label>
      <input id="qa_lab-phone" type="tel" name="phone">
    </div>
    <div>
      <label for="qa_lab-message">{lbl_message}</label>
      <textarea id="qa_lab-message" name="message"></textarea>
    </div>
    <button type="submit">{lbl_submit}</button>
  </form>
</section>
"""


def _home_path(files: dict):
    for p in HOME_NAMES:
        if p in files:
            return p
    return None


def _accent(text: str, files: dict) -> str:
    import checks.cookie_consent as cc
    acc = cc._site_accent(files)
    if acc:
        return acc
    css = cc._css_corpus(text, files)
    m = _BTN_BG_RX.search(css)
    if m:
        return m.group(1)
    return "#2563eb"


def _is_dark_bg(text: str, files: dict) -> bool:
    import checks.cookie_consent as cc
    css = cc._css_corpus(text, files)
    m = _BODY_BG_RX.search(css)
    if not m:
        return False
    val = m.group(1).strip()
    hm = re.match(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", val)
    if hm:
        h = hm.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) < 100
    return "black" in val.lower()


def _build_section(text: str, files: dict, branch: str) -> str:
    import checks.form_stub as fs
    lang = fs._lang(text, branch)
    heading, lead, lbl_name, lbl_email, lbl_phone, lbl_message, lbl_submit = \
        LABELS.get(lang, LABELS["en"])
    anchor = ID_MAP.get(lang, "contact")
    accent = _accent(text, files)
    dark = _is_dark_bg(text, files)
    if dark:
        txt_color = "color:#fff;"
        border, field_bg, field_color = "rgba(255,255,255,.25)", "rgba(255,255,255,.08)", "#fff"
    else:
        txt_color = ""
        border, field_bg, field_color = "rgba(0,0,0,.15)", "#fff", "#111"
    return _FORM_TMPL.format(
        anchor=anchor, txt_color=txt_color, border=border, field_bg=field_bg,
        field_color=field_color, accent=accent, heading=heading, lead=lead,
        lbl_name=lbl_name, lbl_email=lbl_email, lbl_phone=lbl_phone,
        lbl_message=lbl_message, lbl_submit=lbl_submit)


def _insert_pos(text: str) -> int:
    import checks.legal_pages as lp
    m = FOOTER_TAG_RX.search(text)
    if m:
        return m.start()
    span = lp._footer_span(text)
    if span:
        return span[0]
    bm = BODY_CLOSE_RX.search(text)
    if bm:
        return bm.start()
    return len(text)


def run_branch(files, all_paths, branch: str = ""):
    import checks.form_stub as fs
    if not files or fs._has_lead_form(files):
        return []
    home = _home_path(files)
    if not home or "<body" not in files[home].lower():
        return []
    return [{"path": home, "line": 1, "severity": "error",
             "message": "на сайті немає жодної контактної форми — фікс додасть секцію "
                        "з формою (ім'я, e-mail, телефон, повідомлення) перед футером "
                        "головної у стилях сайту і заглушку-подяку"}]


def fix_branch(files, all_paths, branch: str = ""):
    import checks.form_stub as fs
    if not files or fs._has_lead_form(files):
        return []
    home = _home_path(files)
    if not home:
        return []
    text = files[home]
    if "<body" not in text.lower():
        return []
    section = _build_section(text, files, branch)
    pos = _insert_pos(text)
    new = text[:pos] + section + text[pos:]
    new = fs.apply(new, home, all_paths, branch, strip_php=False, stub=True)
    if new == text:
        return []
    return [{"type": "edit", "path": home, "content": new}]
