"""Тести wrong_literal: у файлах має бути {{DOMAIN}}, не {{DOMAIN_NAME}}.

Ключове правило, заради якого чек і має винятки: {{DOMAIN_NAME}} — це НАЗВА
бренду, і як текст лого вона легітимна (хедер, футер, лого-лінк). Але у
пошті чи URL потрібен домен ЗІ ЗОНОЮ: info@{{DOMAIN_NAME}} розкривається в
«info@Quenjefvu», а такої адреси не існує. Тому хост-контекст б'є виняток
хедера/футера — і саме це перевіряє більшість тестів нижче.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, load_check, run                    # noqa: E402

mod = load_check("wrong_literal")

DN = "{{DOMAIN_NAME}}"


def _msgs(path, src):
    return [i["message"] for i in mod.run(path, src)]


# ------------------------------------------- бренд-нейм там, де він доречний

def test_brand_in_footer_is_left_alone():
    src = f"<footer><span class='logo'>{DN}</span></footer>"
    assert mod.run("index.php", src) == []
    assert mod.fix("index.php", src) == src


def test_brand_in_header_is_left_alone():
    src = f"<header><a href='./'><span>{DN}</span></a></header>"
    assert mod.run("index.php", src) == []
    assert mod.fix("index.php", src) == src


def test_brand_in_logo_link_outside_header_is_left_alone():
    src = f"<main><a href='./'><span class='font-headers'>{DN}</span></a></main>"
    assert mod.run("index.php", src) == []


def test_brand_in_footer_div_is_left_alone():
    src = f"<div class='site-footer'><p>© 2026 {DN}</p></div>"
    assert mod.run("index.php", src) == []


def test_brand_outside_any_zone_is_an_error():
    src = f"<main><p>{DN}</p></main>"
    issues = mod.run("index.php", src)
    assert len(issues) == 1 and issues[0]["severity"] == "error"
    assert "поза хедером/футером/лого" in issues[0]["message"]
    assert mod.fix("index.php", src) == "<main><p>{{DOMAIN}}</p></main>"


# --------------------------------- пошта: виняток з винятку (кейс quenjefvu)

def test_email_in_footer_is_an_error_despite_the_footer_exception():
    """Головний кейс. Бренд у футері — можна, пошта у футері — ні:
    info@{{DOMAIN_NAME}} стане «info@Quenjefvu», адреси без зони не буває."""
    src = f"<footer><p><i class='fa fa-envelope'></i>info@{DN}</p></footer>"
    issues = mod.run("index.php", src)
    assert len(issues) == 1 and issues[0]["severity"] == "error"
    assert "пошті/URL" in issues[0]["message"], issues[0]["message"]
    assert mod.fix("index.php", src) == src.replace(DN, "{{DOMAIN}}")


def test_email_in_header_is_an_error():
    src = f"<header><a href='mailto:info@{DN}'>info@{DN}</a></header>"
    assert len(mod.run("index.php", src)) == 2          # і href, і видимий текст
    assert DN not in mod.fix("index.php", src)


def test_email_inside_logo_link_is_an_error():
    src = f"<a href='./'><span>{DN}</span><em>info@{DN}</em></a>"
    issues = mod.run("index.php", src)
    assert len(issues) == 1 and "пошті/URL" in issues[0]["message"]
    # бренд у тому ж лого-лінку лишається
    out = mod.fix("index.php", src)
    assert f"<span>{DN}</span>" in out and f"info@{DN}" not in out


def test_email_in_footer_div_is_an_error():
    src = f"<div id='footer-bar'>legal@{DN}</div>"
    assert len(mod.run("index.php", src)) == 1


def test_various_local_parts():
    for local in ("info", "privacy", "legal", "sales", "hello.team", "a+b"):
        src = f"<footer>{local}@{DN}</footer>"
        assert len(mod.run("index.php", src)) == 1, local


# ---------------------------------------------------- URL — той самий клас

def test_url_in_footer_is_an_error():
    src = f"<footer><a href='https://{DN}/privacy'>x</a></footer>"
    issues = mod.run("index.php", src)
    assert len(issues) == 1 and "пошті/URL" in issues[0]["message"]
    assert mod.fix("index.php", src) == src.replace(DN, "{{DOMAIN}}")


def test_www_in_footer_is_an_error():
    src = f"<footer>www.{DN}</footer>"
    assert len(mod.run("index.php", src)) == 1


# ------------------------------------------------------------- межі правила

def test_bare_at_is_a_social_handle_not_an_email():
    """«@{{DOMAIN_NAME}}» без локальної частини — соц-хендл, бренд доречний."""
    src = f"<footer><span>@{DN}</span></footer>"
    assert mod.run("index.php", src) == []
    assert mod.fix("index.php", src) == src


def test_space_between_at_and_placeholder_still_counts():
    src = f"<footer>info@ {DN}</footer>"
    assert len(mod.run("index.php", src)) == 1


# ------------------------------------------------------------ react-вайти

def test_js_brand_is_fine_but_host_is_not():
    src = f'const brand="{DN}"; const mail="info@{DN}";'
    issues = mod.run("assets/index-a1b2.js", src)
    assert len(issues) == 1 and "пошті/URL" in issues[0]["message"]
    out = mod.fix("assets/index-a1b2.js", src)
    assert f'brand="{DN}"' in out and "info@{{DOMAIN}}" in out


def test_vite_shell_title_is_allowed():
    src = ('<html><head><title>' + DN + ' · Home</title>'
           '<script src="assets/index-a1b2.js"></script></head></html>')
    assert mod.run("index.php", src) == []


def test_plain_shell_title_is_not_allowed():
    src = f"<html><head><title>{DN} · Home</title></head></html>"
    assert len(mod.run("index.php", src)) == 1


# ------------------------------------------------------------------- інше

def test_fix_is_idempotent():
    src = (f"<footer>info@{DN} <span>{DN}</span></footer>"
           f"<main><p>{DN}</p></main>")
    once = mod.fix("index.php", src)
    assert mod.fix("index.php", once) == once
    assert mod.run("index.php", once) == []


def test_line_numbers_point_at_the_placeholder():
    src = "<html>\n<footer>\ninfo@" + DN + "\n</footer>\n"
    assert mod.run("index.php", src)[0]["line"] == 3


def test_real_snapshot_has_no_placeholder_email_left():
    """На живих знімках: якщо десь лишилось `щось@{{DOMAIN_NAME}}` — чек
    мусить це бачити, а фікс — прибирати."""
    import re
    base = ROOT / "cache"
    if not base.exists():
        return
    rx = re.compile(r"[A-Za-z0-9._%+\-]+@\{\{\s*DOMAIN_NAME\s*\}\}")
    checked = 0
    for d in sorted(base.iterdir())[:400]:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.html")) + sorted(d.glob("*.php")):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except (PermissionError, OSError):
                continue                     # лаба тримає файл заблокованим — як відсутній
            if not rx.search(text):
                continue
            checked += 1
            assert mod.run(f.name, text), f"{d.name}/{f.name}: пошта не спіймана"
            fixed = mod.fix(f.name, text)
            assert not rx.search(fixed), f"{d.name}/{f.name}: пошта лишилась після фікса"
            if checked >= 20:
                return


if __name__ == "__main__":
    run(dict(globals()))
