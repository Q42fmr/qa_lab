"""Тести dead_host: лінки на зарезервований (RFC 2606/6761) хост.

Кейси: bralobmgeon.com.br (46× кукі-банер -> store-policy) і
i2jlibitiec.com.br (2× лінк у тілі тексту на сторінку оригінального сайту).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_check, run                        # noqa: E402

mod = load_check("dead_host")


def _page(body):
    return f"<!DOCTYPE html><html><head></head><body>{body}</body></html>"


# Сторінка, яка САМА називає свій хост через canonical — так виглядає кожен
# скрейп цього корпусу: домен оригіналу підмінено на `<бренд>-neu.example`.
SELF = "selzeavbsozom-neu.example"


def _self_page(body, host=SELF):
    return ('<!DOCTYPE html><html><head>'
            f'<link rel="canonical" href="https://{host}/">'
            f'</head><body>{body}</body></html>')


# ------------------------------------------------- самопосилання (внутрішня
# навігація вайта через мертвий хост)
def test_self_link_becomes_home_not_plain_text():
    """Кейс `selzeavbsozom.ch`: 49 лінків, з них 12 — випадайне меню напрямків.
    Розгорнути їх у текст (гілка «ціль невідома») означало б знищити меню."""
    text = _self_page(f'<a href="https://{SELF}/gruppenreisen/">Reisen in Gruppen</a>')
    out = mod.fix("index.html", text)
    assert '<a href="index.html">Reisen in Gruppen</a>' in out, out
    assert SELF not in out.split("</head>")[1]


def test_self_link_keeps_other_attributes():
    text = _self_page(f'<a class="nav" data-x="1" href="https://{SELF}/team/">Team</a>')
    out = mod.fix("index.html", text)
    assert 'class="nav"' in out and 'data-x="1"' in out and 'href="index.html"' in out


def test_self_link_picks_the_page_its_path_names():
    """Ключове слово в шляху вибирає одну з чотирьох сторінок у корені."""
    cases = {
        "impressum": "impressum.html",
        "datenschutz": "privacy.html",
        "agb": "privacy.html",
        "kontakt": "contact.html",
        "gruppenreisen": "index.html",
    }
    for slug, want in cases.items():
        text = _self_page(f'<a href="https://{SELF}/{slug}/">x</a>')
        out = mod.fix("index.html", text)
        assert f'href="{want}"' in out, (slug, out)


def test_self_link_depth_is_corrected():
    text = _self_page(f'<a href="https://{SELF}/team/">Team</a>')
    out = mod.fix("a/b/index.html", text)
    assert 'href="../../index.html"' in out, out


def test_self_link_is_reported_as_self_reference():
    text = _self_page(f'<a href="https://{SELF}/team/">Team</a>')
    iss = mod.run("index.html", text)
    assert len(iss) == 1 and "самопосилання" in iss[0]["message"], iss


def test_self_link_fix_is_idempotent():
    text = _self_page(f'<a href="https://{SELF}/team/">Team</a>')
    once = mod.fix("index.html", text)
    assert mod.fix("index.html", once) == once
    assert mod.run("index.html", once) == []


def test_foreign_reserved_host_still_unwraps_even_with_canonical():
    """Межа: canonical робить своїм лише СВІЙ хост. Чужий мертвий хост на тій
    самій сторінці далі розгортається у текст, як і раніше."""
    text = _self_page('<a href="https://someoneelse-neu.example/x/">чужий</a>')
    out = mod.fix("index.html", text)
    assert "<a" not in out.split("</head>")[1]
    assert "чужий" in out


def test_without_canonical_behaviour_is_unchanged():
    """Немає canonical — немає поняття «свій хост», отже давня поведінка."""
    text = _page(f'<a href="https://{SELF}/gruppenreisen/">Reisen</a>')
    out = mod.fix("index.html", text)
    assert "<a" not in out.split("<body>")[1]
    assert "Reisen" in out

# --------------------------------------------------------------- детект
def test_policy_link_on_reserved_host_is_flagged():
    text = _page('<a href="https://bralobmgeon-neu.example/store-policy">'
                 'Pol\u00edtica de Privacidade</a>')
    issues = mod.run("index.html", text)
    assert len(issues) == 1, issues
    assert "example" in issues[0]["message"]


def test_body_link_on_reserved_host_is_flagged():
    text = _page('<a href="http://i2producoes-neu.example/parceria">Spotify e Botafogo</a>')
    issues = mod.run("parceria-spotify-e-botafogo/index.html", text)
    assert len(issues) == 1, issues


def test_invalid_test_localhost_zones_are_also_reserved():
    for host in ("foo.invalid", "foo.test", "foo.localhost"):
        text = _page(f'<a href="https://{host}/x">x</a>')
        assert len(mod.run("index.html", text)) == 1, host


def test_live_external_link_is_not_touched():
    text = _page('<a href="https://google.com/">Google</a>')
    assert mod.run("index.html", text) == []
    assert mod.fix("index.html", text) == text


def test_placeholder_example_com_email_is_not_reported():
    """`placeholder="ihre@example.com"` - не URL, не href, чек його не бачить."""
    text = _page('<input placeholder="ihre@example.com">')
    assert mod.run("index.html", text) == []


def test_example_com_in_prose_text_is_not_reported():
    text = _page('<p>Contact us at hello@example.com for details.</p>')
    assert mod.run("index.html", text) == []


# --------------------------------------------------------------- глибина
def test_depth_zero_root_page():
    href = mod._rel("index.html", mod.PRIVACY_FILE)
    assert href == "privacy.html", href


def test_depth_one():
    href = mod._rel("contato/index.html", mod.PRIVACY_FILE)
    assert href == "../privacy.html", href


def test_depth_two():
    href = mod._rel("a/b/index.html", mod.PRIVACY_FILE)
    assert href == "../../privacy.html", href


def test_depth_three():
    href = mod._rel("a/b/c/index.html", mod.PRIVACY_FILE)
    assert href == "../../../privacy.html", href


def test_depth_applies_to_every_local_target():
    """Глибина однакова для всіх чотирьох сторінок, які лаба кладе в корінь."""
    for target in (mod.PRIVACY_FILE, mod.IMPRESSUM_FILE, mod.CONTACT_FILE,
                   mod.HOME_FILE):
        assert mod._rel("a/b/index.html", target) == "../../" + target


# ----------------------------------------------------------------- фікс
def test_fix_policy_link_points_to_privacy_html_with_depth():
    text = _page('<span><a target="_blank" id="cst-privacy-link" tabindex="0" '
                 'href="https://bralobmgeon-neu.example/store-policy">Pol\u00edtica'
                 '</a></span>')
    out = mod.fix("contato/index.html", text)
    assert 'href="../privacy.html"' in out, out
    assert "example" not in out
    assert 'id="cst-privacy-link"' in out  # решта атрибутів лишається
    assert mod.run("contato/index.html", out) == []


def test_fix_root_page_policy_link():
    text = _page('<a href="https://bralobmgeon-neu.example/store-policy">Pol.</a>')
    out = mod.fix("index.html", text)
    assert 'href="privacy.html"' in out, out


def test_fix_body_link_unwraps_to_its_own_text():
    text = _page('Criamos um fone com logos do <a href="http://i2producoes-neu.example/'
                 'parceria-spotify-e-botafogo-mais-uma-producao-da-i2/" target="_blank">'
                 'Spotify e do Botafogo</a> e o nome de cada atleta.')
    out = mod.fix("parceria-spotify-e-botafogo/index.html", text)
    assert "<a" not in out, out
    assert "Spotify e do Botafogo" in out
    assert "example" not in out
    assert mod.run("parceria-spotify-e-botafogo/index.html", out) == []


def test_fix_is_idempotent_for_policy_link():
    text = _page('<a href="https://bralobmgeon-neu.example/store-policy">Pol.</a>')
    once = mod.fix("a/index.html", text)
    twice = mod.fix("a/index.html", once)
    assert once == twice


def test_fix_is_idempotent_for_body_link():
    text = _page('see <a href="http://x-neu.example/y">Y</a> here')
    once = mod.fix("index.html", text)
    twice = mod.fix("index.html", once)
    assert once == twice


def test_fix_no_match_returns_text_unchanged():
    text = _page('<a href="https://google.com/">Google</a>')
    assert mod.fix("index.html", text) is text or mod.fix("index.html", text) == text


def test_check_is_php_auto():
    assert mod.PROJECTS == ["php"], mod.PROJECTS
    assert mod.GROUP == "auto"


if __name__ == "__main__":
    run(dict(globals()))
