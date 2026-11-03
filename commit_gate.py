"""Гейт коміту: те, що гарантовано ламає деплой або обманює відвідувача,
не доїжджає до GitLab мовчки.

1. {{UPPER}}-токени. Деплой php-вайтів (`black-pages/script/placeholders_sed.sh`)
   підставляє лише {{DOMAIN}} і {{DOMAIN_NAME}} і ПАДАЄ на будь-якому іншому
   `{{UPPER}}` у html/php/xml/txt/json. Такий токен — завжди сміття генератора
   («O {{BRAND}} atende…», `{{LOGO}}` у href), тож гейт його прибирає з
   контенту коміту й повертає нотатку, що саме прибрав (рішення 27.10: не
   блокувати, а видаляти). Маленькі літери, `{{ x }}` з пробілами, `${X}` —
   не його справа (Vue-інтерполяції, js template literals, див. template_vars).
2. Ассети «на місці». Cloudflare тримає CSS/JS/картинки/шрифти 30 днів
   immutable: файл, змінений під тією самою назвою, відвідувач не побачить до
   місяця. Update такого файла — попередження з переліком; create (нове ім'я,
   хеш) — ні. Нічого не змінює, лише каже.

Підключається у `GitLabClient.commit`/`MockClient.commit` прапорцем `gate`
(лише php-проєкт: у node деплой інший, а `{{COUNT}}` в i18n-json легітимний).
Нотатки повертаються у відповіді коміту ключем `lab_notes` — їх показує UI і
`commits_log`.
"""
import re

ALLOWED = {"DOMAIN", "DOMAIN_NAME"}
TOKEN_RX = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
TEXT_EXT = (".html", ".htm", ".php", ".xml", ".txt", ".json")
ASSET_EXT = (".css", ".js", ".mjs", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
             ".ico", ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".webm")
CDN_NOTE = ("Cloudflare кешує CSS/JS/картинки 30 днів immutable — змінені на місці файли "
            "відвідувач побачить лише після перейменування (хеш у назві) або purge: ")


def strip_tokens(text: str) -> tuple[str, dict]:
    """(текст без невідомих {{UPPER}}, {токен: кількість}). Токен з пробілами
    обабіч забирає один пробіл, щоб не лишати подвійних."""
    counts: dict = {}

    def one(m):
        tok = m.group(1)
        if tok in ALLOWED:
            return m.group(0)
        counts[m.group(0)] = counts.get(m.group(0), 0) + 1
        return "\x00"

    out = TOKEN_RX.sub(one, text)
    if not counts:
        return text, {}
    out = re.sub(r"\x00 ", "", out)               # «{{X}} news» → «news»
    out = re.sub(r" \x00", "", out)               # «foo {{X}}.» → «foo.»
    out = out.replace("\x00", "")
    return out, counts


def apply(actions: list) -> tuple[list, list]:
    """Гейт над діями коміту GitLab ({action, file_path, content, encoding?}).
    Повертає (дії з прибраними токенами, нотатки)."""
    import base64
    out, notes, cdn = [], [], []
    for a in actions:
        path = (a.get("file_path") or "").lower()
        act = a.get("action")
        if act in ("create", "update") and path.endswith(TEXT_EXT) and isinstance(a.get("content"), str):
            b64 = a.get("encoding") == "base64"
            text = None
            if b64:
                try:
                    text = base64.b64decode(a["content"]).decode("utf-8")
                except (ValueError, UnicodeDecodeError):
                    text = None                      # не utf-8 текст — не чіпаємо
            else:
                text = a["content"]
            counts = {}
            if text is not None:
                new, counts = strip_tokens(text)
            if counts:
                a = {**a, "content": base64.b64encode(new.encode("utf-8")).decode() if b64 else new}
                toks = ", ".join(f"{t}×{n}" if n > 1 else t for t, n in sorted(counts.items()))
                notes.append(f"{a['file_path']}: прибрано невідомі плейсхолдери {toks} — "
                             f"деплой підставляє лише {{{{DOMAIN}}}}")
        if act == "update" and path.endswith(ASSET_EXT):
            cdn.append(a["file_path"])
        out.append(a)
    if cdn:
        notes.append(CDN_NOTE + ", ".join(cdn))
    return out, notes
