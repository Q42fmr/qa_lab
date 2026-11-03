"""WP-вайт: Contact Form 7 шле у wp-json, якого на вайті не існує.

Кейс exniclovalsejojzm (02.10): сторінки зняті з живого WordPress разом із
CF7-розміткою і його js. Сабміт у CF7 — fetch на
`<api.root>/contact-form-7/v1/contact-forms/<id>/feedback`; на вайті
WordPress-бекенда немає (а api.root узагалі лишився на СТАРИЙ домен), тож
клік по «Enviar» мовчки вмирає: ні повідомлення, ні помилки. QA бачить
«форма не відправляється».

Фікс не воскрешає WordPress: він перехоплює submit ДО CF7 (capture +
stopImmediatePropagation), показує подяку мовою сторінки і чистить поля.
Лід на вайті нікуди не шлеться свідомо — так само працюють решта наших
форм-фіксів (form_action, form_flow).
"""
import re

NAME = "WP-форма шле у мертвий wp-json"
GROUP = "auto"
# branch-code (branch_code.py): форма не чіпає клієнтських даних — лише
# додає перехоплювач-скрипт
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Contact Form 7 на знятому з WordPress вайті: сабміт іде у "
               "wp-json, якого тут немає (часто ще й на старий домен) — "
               "форма мовчки не відправляється. Фікс перехоплює submit і "
               "показує подяку мовою сторінки, без мережі.")
FILES = ["*.html", "*.htm", "*.php"]

MARKER = "qa_lab:cf7-feedback"
CF7_FORM_RX = re.compile(r"""<form\b[^>]*class\s*=\s*["'][^"']*\bwpcf7-form\b""",
                         re.I)
LANG_RX = re.compile(r"""<html\b[^>]*\blang\s*=\s*["']?([A-Za-z-]+)""", re.I)

# подяка мовою сторінки; ключ — первинна підмова
I18N_THANKS = {
    "pt": ("Obrigado! Sua mensagem foi enviada com sucesso. "
           "Em breve entraremos em contato."),
    "es": ("¡Gracias! Su mensaje ha sido enviado correctamente. "
           "En breve nos pondremos en contacto."),
    "de": ("Vielen Dank! Ihre Nachricht wurde erfolgreich gesendet. "
           "Wir melden uns in Kürze."),
    "it": ("Grazie! Il suo messaggio è stato inviato con successo. "
           "La contatteremo a breve."),
    "fr": ("Merci ! Votre message a bien été envoyé. "
           "Nous vous recontacterons rapidement."),
    "en": ("Thank you! Your message has been sent successfully. "
           "We will get back to you shortly."),
}


def _thanks(text: str) -> str:
    m = LANG_RX.search(text)
    code = (m.group(1) if m else "en").lower().split("-")[0]
    return I18N_THANKS.get(code, I18N_THANKS["en"])


def _script(text: str) -> str:
    msg = _thanks(text).replace("'", "\\'")
    return (
        "<script>/* " + MARKER + ": CF7-бекенда на вайті немає — подяка "
        "локально */\n"
        "(function(){\n"
        "  document.addEventListener('submit', function(e){\n"
        "    var f = e.target && e.target.closest && "
        "e.target.closest('form.wpcf7-form');\n"
        "    if (!f) return;\n"
        "    e.preventDefault();\n"
        "    e.stopImmediatePropagation();\n"
        "    var out = f.querySelector('.wpcf7-response-output');\n"
        "    if (!out) {\n"
        "      out = document.createElement('div');\n"
        "      out.className = 'wpcf7-response-output';\n"
        "      f.appendChild(out);\n"
        "    }\n"
        "    out.textContent = '" + msg + "';\n"
        "    out.style.cssText = 'display:block;border:2px solid #46b450;"
        "padding:12px 16px;margin:16px 0;color:#1a7a2e;font-weight:600';\n"
        "    f.reset();\n"
        "    out.scrollIntoView({block:'nearest',behavior:'smooth'});\n"
        "  }, true);\n"
        "})();</script>")


def run(path, text):
    if MARKER in text:
        return []
    if not CF7_FORM_RX.search(text):
        return []
    m = CF7_FORM_RX.search(text)
    return [{
        "line": text.count("\n", 0, m.start()) + 1,
        "severity": "error",
        "message": ("Contact Form 7 шле у wp-json, якого на вайті немає — "
                    "сабміт мовчки вмирає, «після нажатия ничего не "
                    "происходит»; фікс перехопить submit і покаже подяку"),
    }]


def fix(path, text):
    if MARKER in text or not CF7_FORM_RX.search(text):
        return text
    i = text.lower().rfind("</body>")
    block = _script(text) + "\n"
    if i < 0:
        return text + "\n" + block
    return text[:i] + block + text[i:]
