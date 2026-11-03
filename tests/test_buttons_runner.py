"""Видалення мертвих кнопок з джерела (buttons_runner.compute_fixes).

Браузерна частина (клік і вердикт) тут не ганяється — лише те, що потім
комітиться: який шматок джерела вирізається за описом елемента з DOM."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                # noqa: E402

sys.path.insert(0, str(ROOT))
import buttons_runner as br                                   # noqa: E402


def d(tag, text="", cls=(), href=None, aria=None, id_="", type_=None, role=None):
    return {"tag": tag, "id": id_, "cls": list(cls), "href": href, "type": type_,
            "aria": aria, "role": role, "text": text}


def _setup(files: dict, items: list):
    snap = Path(tempfile.mkdtemp(prefix="btn-snap-"))
    state = Path(tempfile.mkdtemp(prefix="btn-state-"))
    for rel, t in files.items():
        (snap / rel).parent.mkdir(parents=True, exist_ok=True)
        (snap / rel).write_text(t, encoding="utf-8")
    br.snapshot_dir = lambda b: snap
    br.root = lambda: state
    br.result_path("x-br-pt").write_text(json.dumps({"branch": "x-br-pt", "items": items}), encoding="utf-8")


def _item(fid, chain, label="x"):
    return {"fid": fid, "label": label, "chain": chain}


SLIDER = ('<div class="dots">\n'
          '  <button aria-label="Ir para slide 1" class="dot active"></button>\n'
          '  <button aria-label="Ir para slide 2" class="dot"></button>\n'
          '</div>\n<div class="other"><button class="dot"></button></div>\n')


def test_dot_without_aria_label_is_not_taken_for_the_labelled_one():
    """aria-label є в DOM, а в джерелі нема — це інша кнопка (сусідній слайдер)."""
    _setup({"index.php": SLIDER}, [_item("a", [d("button", cls=["dot"], aria="Ir para slide 2")])])
    r = br.compute_fixes("x-br-pt")
    new = r["edits"]["index.php"][1]
    assert 'aria-label="Ir para slide 2"' not in new
    assert 'aria-label="Ir para slide 1"' in new and '<div class="other"><button class="dot"></button></div>' in new


def test_state_class_in_source_matches_dom_and_the_whole_line_goes():
    _setup({"index.php": SLIDER}, [_item("a", [d("button", cls=["dot"], aria="Ir para slide 1")])])
    new = br.compute_fixes("x-br-pt")["edits"]["index.php"][1]
    assert "slide 1" not in new and "  \n" not in new and new.startswith('<div class="dots">\n  <button aria-label="Ir para slide 2"')


def test_wrapper_goes_only_if_our_element_is_inside_it_and_on_every_page():
    page = ('<ul class="pagination"><li><a href="/page/2/">2</a></li><li><a href="/page/3/">3</a></li></ul>'
            '<ul class="menu"><li>2</li></ul>')
    chain = [d("li", text="2"), d("a", text="2", href="/page/2/")]
    _setup({"index.html": page, "blog/index.html": page}, [_item("p2", chain)])
    r = br.compute_fixes("x-br-pt")
    assert set(r["edits"]) == {"index.html", "blog/index.html"}
    new = r["edits"]["index.html"][1]
    assert '<ul class="pagination"><li><a href="/page/3/">3</a></li></ul>' in new
    assert '<ul class="menu"><li>2</li></ul>' in new, "чужий <li> з тим самим текстом лишився"


def test_nested_same_tag_and_text_with_entities_are_matched_exactly():
    page = ('<div class="cta"><div class="in"><span>Solicitar&nbsp;Or&ccedil;amento</span></div></div>'
            '<div class="keep">x</div><script>var s = "<div class=\\"cta\\">";</script>')
    _setup({"index.php": page}, [_item("c", [d("div", cls=["cta"], text="Solicitar Orçamento")])])
    new = br.compute_fixes("x-br-pt")["edits"]["index.php"][1]
    assert new == '<div class="keep">x</div><script>var s = "<div class=\\"cta\\">";</script>'


def test_generic_or_script_built_elements_are_skipped_not_guessed():
    _setup({"index.php": "<button>Ok</button>"},
           [_item("g", [d("button")], "[button]"), _item("s", [d("button", cls=["slick-next"], text="Next")], "Next")])
    r = br.compute_fixes("x-br-pt")
    assert r["edits"] == {} and len(r["skipped"]) == 2


def test_forget_drops_only_committed_findings():
    _setup({"index.php": SLIDER}, [_item("a", [d("button", cls=["dot"], aria="Ir para slide 1")]),
                                   _item("b", [d("button", cls=["dot"], aria="Ir para slide 2")])])
    br.forget("x-br-pt", ["a"])
    s = br.load("x-br-pt")
    assert [i["fid"] for i in s["items"]] == ["b"] and s["dead"] == 1


JP_HOME = ('<header><ul class="nav">\n'
           '  <li><a href="#">会社概要</a></li>\n'
           '  <li><a>シャツ</a></li>\n'
           '  <li><a href="#">お問い合わせ</a></li>\n'
           '  <li><a href="#">Facebook</a></li>\n'
           '</ul></header>\n'
           '<p class="mail"><a class="m">info@{{DOMAIN}}</a></p>\n'
           '<footer><a href="company/index.html">会社概要</a></footer>\n')
CONTACT = '<html><head><title>お問い合わせ｜ORTUN SQIOHA</title></head><body><h1>お問い合わせ</h1></body></html>'


def test_dead_anchor_is_retargeted_when_the_same_label_links_somewhere_real():
    """ortun-sqioha / maefur-kabo (26.10): меню з href="#" дублює підвал, де той
    самий пункт веде на справжню сторінку — видаляти меню безглуздо, лінк
    береться з двійника; сторінка за назвою вкладки — другий шлях."""
    _setup({"index.php": JP_HOME, "contact/index.html": CONTACT},
           [_item("c", [d("li", text="会社概要"), d("a", text="会社概要", href="#")], "会社概要"),
            _item("k", [d("li", text="お問い合わせ"), d("a", text="お問い合わせ", href="#")], "お問い合わせ")])
    r = br.compute_fixes("x-br-pt")
    new = r["edits"]["index.php"][1]
    assert '<li><a href="company/index.html">会社概要</a></li>' in new
    assert '<li><a href="contact/index.html">お問い合わせ</a></li>' in new
    assert '<footer><a href="company/index.html">会社概要</a></footer>' in new
    assert {a["how"] for a in r["applied"]} == {"retargeted"}, r["applied"]


def test_label_anchor_without_href_is_unwrapped_and_email_gets_mailto():
    _setup({"index.php": JP_HOME},
           [_item("s", [d("li", text="シャツ"), d("a", text="シャツ")], "シャツ"),
            _item("m", [d("p", cls=["mail"], text="info@{{DOMAIN}}"), d("a", cls=["m"], text="info@{{DOMAIN}}")], "info@{{DOMAIN}}"),
            _item("f", [d("li", text="Facebook"), d("a", text="Facebook", href="#")], "Facebook")])
    r = br.compute_fixes("x-br-pt")
    new = r["edits"]["index.php"][1]
    assert "  <li>シャツ</li>\n" in new, "підпис меню лишається текстом"
    assert '<p class="mail"><a href="mailto:info@{{DOMAIN}}" class="m">info@{{DOMAIN}}</a></p>' in new
    assert "Facebook" not in new, "мертва соцкнопка без двійника — видаляється разом з <li>"
    assert {a["fid"]: a["how"] for a in r["applied"]} == {"s": "unwrapped", "m": "mailto", "f": "removed"}


def test_content_links_are_unwrapped_but_nav_cta_and_home_are_handled():
    """noep-atowoos / resonance / terroir (26.10): data-tpl="[EXTERNAL LINK]"
    href="#" — це колишні зовнішні лінки: назва тканини, ім'я, заголовок
    новини — зміст, лишається текстом; пункт меню без цілі — геть разом з
    <li>; «Accueil» у меню → корінь; «Télécharger …» без файлу — геть."""
    page = ('<nav><ul><li class="nav-item"><a class="nav-link" href="#">Accueil</a></li>\n'
            '<li class="nav-item"><a class="nav-link" href="#">Boutique</a></li></ul></nav>\n'
            '<ul class="fabrics"><li class="li1"><a data-tpl="[EXTERNAL LINK]" href="#"><span class="bir">英国ウール｜梳毛生地</span></a></li></ul>\n'
            '<p><a data-tpl="[EXTERNAL LINK]" href="#">Camille Dupraz</a> juriste</p>\n'
            '<span class="file"><a href="#" type="application/pdf">Télécharger le guide AOC</a></span>\n')
    sub = page.replace("Camille", "Camilla")
    _setup({"index.php": page, "de/downloads/index.html": sub},
           [_item("h", [d("li", cls=["nav-item"], text="Accueil"), d("a", cls=["nav-link"], text="Accueil", href="#")], "Accueil"),
            _item("b", [d("li", cls=["nav-item"], text="Boutique"), d("a", cls=["nav-link"], text="Boutique", href="#")], "Boutique"),
            _item("w", [d("li", cls=["li1"], text="英国ウール｜梳毛生地"), d("a", text="英国ウール｜梳毛生地", href="#")], "英国ウール｜梳毛生地"),
            _item("c", [d("a", text="Camille Dupraz", href="#")], "Camille Dupraz"),
            _item("t", [d("span", cls=["file"], text="Télécharger le guide AOC"), d("a", text="Télécharger le guide AOC", href="#", type_="application/pdf")], "Télécharger le guide AOC")])
    r = br.compute_fixes("x-br-pt")
    new = r["edits"]["index.php"][1]
    assert '<li class="nav-item"><a class="nav-link" href="./">Accueil</a></li>' in new
    assert '<li class="nav-item"><a class="nav-link" href="../../">Accueil</a></li>' in r["edits"]["de/downloads/index.html"][1]
    assert "Boutique" not in new
    assert '<li class="li1"><span class="bir">英国ウール｜梳毛生地</span></li>' in new
    assert "<p>Camille Dupraz juriste</p>" in new
    assert "Télécharger" not in new and '<span class="file">' not in new
    assert {a["fid"]: a["how"] for a in r["applied"]} == {"h": "retargeted", "b": "removed", "w": "unwrapped", "c": "unwrapped", "t": "removed"}


if __name__ == "__main__":
    run(dict(globals()))
