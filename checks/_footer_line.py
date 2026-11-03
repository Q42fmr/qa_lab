"""Рядок у футер, коли ні <p>, ні <address> там немає: клон ©-елемента.

Кейс sokkoruuzosnacav 21.10 (Nova-тема WP): футер —
`<div class="footer-text">2025 © SOS Móveis Antigos…</div>`, без жодного <p>.
`cnpj` писав «додай руками», `geo_phone` обіцяв телефон і давав 0 дій —
QA повторював обидва зауваження. Той самий підвал із <div>/<span> будують
Elementor- і Astro-білди (legal_pages уже вміє шукати © поза <footer>).

Правило: найглибший елемент (div/span/p/li/small) з © / «direitos» /
«rights» у видимому тексті футера; новий рядок — той самий відкривний тег
(усі класи й стилі) одразу після нього. Повертає текст як був, якщо кандидата
немає — тоді чек чесно каже «додай руками».
"""
import re

COPY_RX = re.compile(r"©|&copy;|\(c\)\s*20\d\d|\b20\d\d\b[^<]{0,40}(?:direitos|rights|droits|diritti|derechos|Rechte)", re.I)
FOOTER_RX = re.compile(r"<footer\b[^>]*>", re.I)
# найглибший елемент: усередині немає інших відкривних тегів того ж роду
_LEAF_RX = re.compile(r"<(div|span|p|li|small)\b[^>]*>(?:(?!<(?:div|span|p|li|small)\b)[\s\S])*?</\1>", re.I)


def append_after_copyright(text: str, content: str, span: tuple | None = None) -> str:
    """Рядок `content` клоном ©-елемента футера; без кандидата — текст як був.

    span — (початок, кінець) вмісту конкретного <footer> (cnpj бере підвал
    рівня сайту, а не перший <footer> сторінки); без нього — перший футер."""
    if span is None:
        if content in text:
            return text
        m = FOOTER_RX.search(text)
        if not m:
            return text
        end = text.lower().find("</footer>", m.end())
        if end < 0:
            return text
        span = (m.end(), end)
    start, end = span
    seg = text[start:end]
    if content in seg:
        return text                     # у тексті сторінки — не рахується, лише у ЦЬОМУ футері
    cand = None
    for b in _LEAF_RX.finditer(seg):
        inner = re.sub(r"<[^>]+>", "", b.group(0))
        if COPY_RX.search(inner):
            cand = b                                  # останній ©-лист
    if cand is None:
        return text
    block = cand.group(0)
    open_tag = block[:block.find(">") + 1]
    tag = cand.group(1)
    clone = f"{open_tag}{content}</{tag}>"
    abs_start = start + cand.start()
    ls = text.rfind("\n", 0, abs_start) + 1
    indent = text[ls:abs_start]
    if indent.strip():
        indent = ""
    nl = "\r\n" if "\r\n" in text else "\n"
    abs_end = start + cand.end()
    return text[:abs_end] + nl + indent + clone + text[abs_end:]
