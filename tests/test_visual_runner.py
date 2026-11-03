"""Візуальні перевірки: склейка дублів, якорі правки, валідація прев'ю.

Кейси з реальних прогонів (вітка auto_br-seguran-a-digital…, tagdocaa-mx-es):
* футерний лінк ламався 6 разів на кожній з 17 сторінок — це ОДИН баг;
* `.mono` з кольором #7e8781 ламався у 20 різних селекторах — теж один
  токен палітри й одна правка;
* заміна #1a73e8 → #0e67dc давала дві однакові картинки в прев'ю.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                              # noqa: E402

sys.path.insert(0, str(ROOT))
import visual_runner as vr                                  # noqa: E402


def _item(**kw):
    base = {"kind": "contrast", "sev": "warn", "sel": "div.a > span",
            "fg_hex": "#7e8781", "bg": "#f5f0e8", "need": 4.5, "r": 2.83,
            "page": "/", "txt": "текст", "msg": "контраст 2.83:1",
            "openTag": '<span class="mono">', "tagIx": 0, "tagTotal": 1,
            "fix": {"to": "#354340", "how": "палітра", "r_after": 7.1}}
    base.update(kw)
    return base


# ---------------------------------------------------------------- склейка
def test_same_color_pair_merges_across_pages_and_selectors():
    items = [
        _item(page="/", sel="footer > a", openTag='<a class="l">', tagIx=0, tagTotal=6),
        _item(page="/", sel="footer > a", openTag='<a class="l">', tagIx=3, tagTotal=6),
        _item(page="/contact.html", sel="div.mono", openTag='<div class="mono">',
              tagIx=1, tagTotal=4, txt="інший текст"),
    ]
    out = vr._merge(items)
    assert len(out) == 1, [i["sel"] for i in out]
    g = out[0]
    assert g["dups"] == 3
    assert g["pages"] == ["/", "/contact.html"]
    assert len(g["anchors"]) == 3            # правка дійде до КОЖНОГО входження
    assert g["samples"] == ["текст", "інший текст"]
    assert sorted(g["sels"]) == ["div.mono", "footer > a"]


def test_different_background_stays_separate():
    """Той самий текстовий колір на іншому фоні вимагає іншої заміни —
    склеювати не можна, бо r_after групи брехав би."""
    out = vr._merge([_item(bg="#f5f0e8"), _item(bg="#1a1a2e", r=3.79)])
    assert len(out) == 2


def test_merge_keeps_worst_ratio_and_severity():
    out = vr._merge([_item(r=3.9, sev="warn", msg="m39"),
                     _item(r=1.4, sev="error", msg="m14")])
    assert len(out) == 1
    assert out[0]["r"] == 1.4 and out[0]["sev"] == "error"
    assert out[0]["msg"] == "m14"


def test_merge_takes_first_available_preview():
    out = vr._merge([_item(), _item(preview={"before": "b", "after": "a"})])
    assert out[0]["preview"] == {"before": "b", "after": "a"}


def test_non_contrast_kinds_group_by_selector_and_message():
    a = {"kind": "empty_block", "sev": "warn", "sel": "div.x",
         "msg": "порожній блок 300×80px", "page": "/"}
    b = {**a, "page": "/about.html"}
    c = {**a, "msg": "порожній блок 300×90px"}
    out = vr._merge([a, b, c])
    assert len(out) == 2
    assert out[0]["dups"] == 2 and out[0]["pages"] == ["/", "/about.html"]


def test_nofix_items_have_no_anchors():
    """::placeholder / svg-текст inline-фіксом color не правляться —
    якорів не даємо, щоб compute_fixes їх не «виправляв» навмання."""
    assert vr._anchors_of(_item(nofix=True)) == []
    assert vr._anchors_of(_item(tagIx=-1)) == []
    assert vr._anchors_of(_item()) == [
        {"openTag": '<span class="mono">', "tagIx": 0, "tagTotal": 1}]


def test_fid_is_stable_per_group_and_differs_per_viewport():
    k = vr._group_key(_item())
    assert vr._fid("desktop", k) == vr._fid("desktop", vr._group_key(_item(page="/x")))
    assert vr._fid("desktop", k) != vr._fid("mobile", k)


# ---------------------------------------------------------------- прев'ю
def _crop(fill, spots=0, spot=(0, 0, 0)):
    import numpy as np
    a = np.full((20, 60, 3), fill, dtype=np.uint8)
    if spots:
        a[5:5 + spots, 5:25] = spot
    return a


def test_preview_rejects_invisible_change():
    """#1a73e8 → #0e67dc: різниця є, але око її не бачить — у UI це були
    два однакові кропи, які люди читали як «порожньо»."""
    before = _crop(245, 6, (26, 115, 232))
    after = _crop(245, 6, (14, 103, 220))     # зсув 12 на канал
    assert vr._preview_shows_change(before, after) is False


def test_preview_rejects_dense_text_with_tiny_shift():
    """Щільний дрібний шрифт: середня різниця по кропу велика, але сама
    зміна кольору — 12/255. Критерій має дивитись на МАКСИМУМ, не середнє."""
    before = _crop(245, 18, (26, 115, 232))
    after = _crop(245, 18, (14, 103, 220))
    assert vr._preview_shows_change(before, after) is False


def test_preview_accepts_visible_change():
    before = _crop(245, 6, (126, 135, 129))   # #7e8781
    after = _crop(245, 6, (53, 67, 64))       # #354340 — зсув ~70 на канал
    assert vr._preview_shows_change(before, after) is True


def test_preview_rejects_when_text_absent_from_crop():
    """Кроп із плоского місця (згорнутий блок): змінювати нічого."""
    assert vr._preview_shows_change(_crop(245), _crop(245)) is False


def test_preview_rejects_missing_or_mismatched_crops():
    assert vr._preview_shows_change(None, _crop(255)) is False
    import numpy as np
    assert vr._preview_shows_change(_crop(255), np.zeros((5, 5, 3), "uint8")) is False

def test_preview_verdict_distinguishes_subtle_from_noop():
    """Дві різні причини «нема картинки» — і кожну треба показати юзеру,
    бо noop означає, що фікс, найпевніше, взагалі не подіє."""
    subtle_b, subtle_a = _crop(245, 6, (194, 172, 133)), _crop(245, 6, (218, 196, 157))
    assert vr._preview_verdict(subtle_b, subtle_a) == "subtle"
    assert vr._preview_verdict(_crop(245), _crop(245)) == "noop"
    assert vr._preview_verdict(_crop(245, 6, (126, 135, 129)),
                               _crop(245, 6, (53, 67, 64))) == "ok"


def test_merge_drops_no_preview_note_when_picture_found():
    out = vr._merge([_item(no_preview="зміна не помітна"),
                     _item(preview={"before": "b", "after": "a"})])
    assert len(out) == 1
    assert out[0]["preview"] and "no_preview" not in out[0]


# ---------------------------------------------------------------- кроп/фон
class _FakeShot(vr._Shot):
    def __init__(self, arr):                  # без PNG-декоду
        self.a = arr
        self.h, self.w = arr.shape[:2]


def test_cut_clamps_to_image_and_rejects_degenerate():
    import numpy as np
    s = _FakeShot(np.zeros((100, 200, 3), dtype=np.uint8))
    assert s.cut([190, 90, 50, 50]).shape == (10, 10, 3)      # обрізано по краю
    assert s.cut([300, 300, 20, 20]) is None                  # повністю поза
    assert s.cut([0, 0, 2, 2]) is None                        # надто малий


def test_bg_from_pixels_ignores_glyph_pixels():
    """Фон під текстом = медіана БЕЗ пікселів шрифту, інакше сам текст
    тягне фон на себе і контраст виходить заниженим."""
    import numpy as np
    a = np.full((30, 80, 3), 240, dtype=np.uint8)
    a[10:20, 10:70] = 20                       # «літери»
    bg = vr._bg_from_pixels(_FakeShot(a), [0, 0, 80, 30], [20, 20, 20])
    assert bg == [240.0, 240.0, 240.0]


# ---------------------------------------------------------------- конфіг
def test_worker_and_tab_counts_come_from_env():
    old = dict(os.environ)
    try:
        os.environ["VISUAL_WORKERS"] = "5"
        os.environ["VISUAL_TABS"] = "2"
        assert vr.branch_workers() == 5 and vr.tabs_per_branch() == 2
        os.environ["VISUAL_WORKERS"] = "0"     # 0/сміття → не менше одного
        os.environ["VISUAL_TABS"] = "junk"
        assert vr.branch_workers() == 1 and vr.tabs_per_branch() == 3
    finally:
        os.environ.clear()
        os.environ.update(old)



# ---------------------------------------------------------------- прогін форми
# Сценарії звірені живим прогоном по фікстурах (headless Chrome):
# submit з preventDefault, ajax-підтвердження, форма без кнопки, action на
# неіснуючу сторінку — кожен дає рівно той вердикт, що нижче.
def _form(**kw):
    base = {"ix": 0, "sel": "form#contact-form", "action": "", "method": "get",
            "novalidate": False, "visible": True, "submit": "Enviar",
            "fields": [
                {"name": "name", "tag": "input", "type": "text", "required": True,
                 "pattern": "", "placeholder": "", "label": "", "visible": True,
                 "honey": False},
                {"name": "email", "tag": "input", "type": "email", "required": True,
                 "pattern": "", "placeholder": "", "label": "", "visible": True,
                 "honey": False},
            ]}
    base.update(kw)
    return base


FILL = {"filled": ["name=Ana Test", "email=qa.lead@example.com"],
        "skipped": ["website (honeypot/прихований)"], "invalid": [],
        "formValid": True}
BASE_URL = "http://127.0.0.1:9100/"


def _verdict(**kw):
    kw.setdefault("page", "/")
    kw.setdefault("form", _form())
    kw.setdefault("fill", FILL)
    kw.setdefault("landed", "")
    kw.setdefault("base_url", BASE_URL)
    kw.setdefault("expect", "thank-you.html")
    kw.setdefault("status", 0)
    kw.setdefault("empty_passed", False)
    return vr._form_findings(**kw)


def test_form_reaching_return_page_is_ok():
    out = _verdict(landed=BASE_URL + "thank-you.html", status=200)
    assert len(out) == 1
    assert out[0]["kind"] == "form_flow" and out[0]["sev"] == "info"
    assert "форма працює" in out[0]["msg"]
    assert out[0]["form"]["filled"] == FILL["filled"]


def test_thanks_page_recognised_by_name_without_expected():
    """Вітка без дефолту $returnPage: 'obrigado' теж сторінка подяки."""
    out = _verdict(landed=BASE_URL + "obrigado.html", status=200, expect="")
    assert out[0]["sev"] == "info"


def test_dead_submit_is_error():
    """Фікстура dead.html: обробник робить preventDefault і більше нічого."""
    out = _verdict(landed="")
    assert out[0]["sev"] == "error" and "не дає реакції" in out[0]["msg"]


def test_ajax_confirmation_without_navigation_is_ok():
    """Фікстура ajax.html: переходу нема, але з'явився блок «Obrigado…».
    Без цієї гілки жива ajax-форма позначалась би як мертва."""
    out = _verdict(landed="", ajax={"thanksAppeared": True, "changed": True})
    assert out[0]["sev"] == "info" and "ajax" in out[0]["msg"]


def test_page_changed_but_no_thanks_text_still_counts_as_reaction():
    out = _verdict(landed="", ajax={"thanksAppeared": False, "changed": True})
    assert out[0]["sev"] == "info"


def test_form_without_submit_button_is_error():
    out = _verdict(form=_form(submit=None))
    assert any("немає кнопки submit" in i["msg"] for i in out)


def test_return_page_404_is_error():
    """Фікстура missing.html: action на сторінку, якої нема в деплої."""
    out = _verdict(landed=BASE_URL + "obrigado.html?name=x", status=404)
    assert out[0]["sev"] == "error" and "404" in out[0]["msg"]


def test_staying_on_same_page_with_query_is_error():
    """Сабміт пройшов, але конверсійний блок не кинув на подяку —
    лід загубився, хоч зовні все «спрацювало»."""
    out = _verdict(page="/", landed=BASE_URL + "?name=Ana&email=a%40b.c", status=200)
    assert out[0]["sev"] == "error" and "не спрацював" in out[0]["msg"]


def test_foreign_domain_is_warn():
    out = _verdict(landed="https://crm.example.net/lead?ok=1", status=200)
    assert out[0]["sev"] == "warn" and "чужий домен" in out[0]["msg"]


def test_unexpected_page_is_warn():
    out = _verdict(landed=BASE_URL + "solutions.html", status=200)
    assert out[0]["sev"] == "warn" and "solutions.html" in out[0]["msg"]


def test_field_rejecting_test_data_is_reported():
    """Маска pattern=[0-9]{10} відкидає «+52 55 1234 5678» — це не привід
    мовчати: користувач має підставити свої FORM_TEST_*."""
    fill = {**FILL, "invalid": [{"name": "phone", "value": "+52 55 1234",
                                 "pattern": "[0-9]{10}", "why": "формат"}]}
    out = _verdict(fill=fill, landed=BASE_URL + "thank-you.html", status=200)
    assert any(i["kind"] == "form_input" and i["sev"] == "error" for i in out)
    assert any("phone" in i["msg"] for i in out)


def test_empty_submit_passing_is_warn():
    out = _verdict(landed=BASE_URL + "thank-you.html", status=200, empty_passed=True)
    assert any(i["kind"] == "form_input" and i["sev"] == "warn"
               and "порожня форма" in i["msg"] for i in out)
    assert any(i["kind"] == "form_flow" and i["sev"] == "info" for i in out)


def test_blocked_empty_submit_produces_no_warning():
    out = _verdict(landed=BASE_URL + "thank-you.html", status=200, empty_passed=False)
    assert [i["kind"] for i in out] == ["form_flow"]


# ---------------------------------------------------------------- вибір форми
def test_picks_form_with_most_live_fields():
    search = _form(sel="form.search", fields=[
        {"name": "q", "tag": "input", "type": "search", "required": False,
         "pattern": "", "placeholder": "", "label": "", "visible": True, "honey": False}])
    contact = _form(sel="form#contact-form")
    assert vr._pick_form([search, contact])["sel"] == "form#contact-form"


def test_honeypot_and_hidden_fields_do_not_count():
    f = _form(fields=[
        {"name": "website", "tag": "input", "type": "text", "required": False,
         "pattern": "", "placeholder": "", "label": "", "visible": False, "honey": True},
        {"name": "utm_source", "tag": "input", "type": "hidden", "required": False,
         "pattern": "", "placeholder": "", "label": "", "visible": False, "honey": False},
        {"name": "name", "tag": "input", "type": "text", "required": True,
         "pattern": "", "placeholder": "", "label": "", "visible": True, "honey": False},
    ])
    assert vr._pick_form([f]) is None          # живе поле лише одне


def test_invisible_form_skipped():
    assert vr._pick_form([_form(visible=False)]) is None


def test_signature_groups_same_form_across_pages():
    a, b = _form(), _form(sel="form.other")     # той самий action/method/поля
    assert vr._form_signature(a) == vr._form_signature(b)
    assert vr._form_signature(a) != vr._form_signature(_form(action="send.php"))


# ---------------------------------------------------------------- дані форми
def test_form_data_defaults_env_and_override():
    old = dict(os.environ)
    try:
        os.environ["FORM_TEST_EMAIL"] = "env@site.dev"
        d = vr.form_test_data()
        assert d["email"] == "env@site.dev"
        assert d["name"] == vr.FORM_TEST_DEFAULTS["name"]
        d2 = vr.form_test_data({"email": "ui@site.dev", "phone": "11987654321"})
        assert d2["email"] == "ui@site.dev"            # запит б'є .env
        assert d2["phone_digits"] == "11987654321"
        assert vr.form_test_data({"email": "  "})["email"] == "env@site.dev"
    finally:
        os.environ.clear()
        os.environ.update(old)


def test_phone_digits_strips_mask_for_pattern_fields():
    """Запасне значення для полів з pattern=[0-9]{…} — тільки цифри."""
    assert vr.form_test_data({"phone": "+52 (55) 1234-5678"})["phone_digits"] \
        == "525512345678"


def test_expected_return_page_read_from_deploy(tmp=None):
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    (d / "index.php").write_text(
        "<?php $returnPage = $_ENV['WHITE_FORM_RETURN_PAGE'] ?? 'obrigado'; ?>",
        encoding="utf-8")
    orig = vr._deploy_docroot
    try:
        vr._deploy_docroot = lambda br: d
        assert vr.expected_return_page("x") == "obrigado.html"
        (d / "index.php").write_text("<?php $x = 1; ?>", encoding="utf-8")
        assert vr.expected_return_page("x") == ""
    finally:
        vr._deploy_docroot = orig


# ---------------------------------------------------------------- профілі / вибір тестів
def _tmp_profiles():
    import tempfile
    from pathlib import Path
    return Path(tempfile.mkdtemp()) / "visual_profiles.json"


def test_profiles_default_to_builtins():
    p = _tmp_profiles()
    orig = vr.profiles_path
    try:
        vr.profiles_path = lambda: p
        names = [x["name"] for x in vr.load_profiles()]
        assert names == [x["name"] for x in vr.DEFAULT_PROFILES]
        assert not p.exists()          # дефолти не пишемо на диск без потреби
    finally:
        vr.profiles_path = orig


def test_profile_save_load_delete_roundtrip():
    p = _tmp_profiles()
    orig = vr.profiles_path
    try:
        vr.profiles_path = lambda: p
        vr.save_profile({"name": "Мій", "tests": ["form"], "threshold": 2.5,
                         "workers": 4, "form_data": {"email": "me@site.dev"}})
        got = [x for x in vr.load_profiles() if x["name"] == "Мій"][0]
        assert got["tests"] == ["form"] and got["threshold"] == 2.5
        assert got["form_data"] == {"email": "me@site.dev"}
        vr.save_profile({"name": "Мій", "tests": ["text"], "threshold": None,
                         "workers": None, "form_data": {}})
        again = [x for x in vr.load_profiles() if x["name"] == "Мій"]
        assert len(again) == 1 and again[0]["tests"] == ["text"]   # перезапис, не дубль
        assert "Мій" not in [x["name"] for x in vr.delete_profile("Мій")]
    finally:
        vr.profiles_path = orig


def test_profile_rejects_empty_name_and_unknown_fields():
    p = _tmp_profiles()
    orig = vr.profiles_path
    try:
        vr.profiles_path = lambda: p
        try:
            vr.save_profile({"name": "  "})
            assert False, "порожня назва мала впасти"
        except ValueError:
            pass
        saved = vr.save_profile({"name": "X", "tests": ["text", "магія"],
                                 "form_data": {"email": "a@b.c", "hack": "1"}})
        got = [x for x in saved if x["name"] == "X"][0]
        assert got["tests"] == ["text"]                 # невідомий тест відкинуто
        assert got["form_data"] == {"email": "a@b.c"}   # чуже поле не зберігається
    finally:
        vr.profiles_path = orig


def test_deleting_last_profile_restores_builtins():
    p = _tmp_profiles()
    orig = vr.profiles_path
    try:
        vr.profiles_path = lambda: p
        vr.save_profile({"name": "Один", "tests": ["form"]})
        for name in [x["name"] for x in vr.load_profiles()]:
            vr.delete_profile(name)
        assert vr.load_profiles(), "список профілів не має лишатись порожнім"
    finally:
        vr.profiles_path = orig


def test_run_rejects_empty_test_selection():
    """Порожній вибір — це помилка запиту, а не «тихий» прогін усього."""
    try:
        vr.run("no-such-branch", tests=["магія"])
        assert False, "мало впасти на порожньому виборі"
    except ValueError as e:
        assert "перевірки" in str(e)


def test_form_page_filter_keeps_index_and_contact_pages():
    """Прогін ТІЛЬКИ форми не вантажить блог — лише індекс і контактні."""
    pages = ["/", "/blog/a.html", "/contact.html", "/contato.html",
             "/solutions.html", "/kontakt/index.html"]
    got = [p for p in pages if p == "/" or vr._FORM_PAGE_RX.search(p)]
    assert got == ["/", "/contact.html", "/contato.html", "/kontakt/index.html"]


# ---------------------------------------------------------------- підсумок прогону
# Головна скарга з практики: «йде перевірка форми, а результатів не видно».
# Причина була в UI-фільтрах, але сам вердикт має бути однозначним і рахуватись
# на бекенді — щоб «що вийшло / що ні» було видно ще у списку віток.
def _flow(sev, msg="ok", landed="http://x/thank-you.html"):
    return {"kind": "form_flow", "sev": sev, "msg": msg, "page": "/",
            "form": {"landed": landed}}


def test_verdict_form_ok():
    v = vr._verdict({"desktop": [_flow("info", "форма працює → /thank-you.html")]},
                    {"form"})
    assert v["form"]["status"] == "ok"
    assert v["form"]["landed"].endswith("thank-you.html")
    assert "text" not in v                      # текст не ганявся — не вигадуємо


def test_verdict_form_fail_wins_over_ok():
    """Дві форми: одна доходить, друга ні — вітка НЕ «в порядку»."""
    v = vr._verdict({"desktop": [_flow("info"), _flow("error", "сабміт не дає реакції")]},
                    {"form"})
    assert v["form"]["status"] == "fail"
    assert "не дає реакції" in v["form"]["msg"]


def test_verdict_form_ok_with_note_is_warn():
    """Доходить до подяки, але приймає порожній сабміт — «працює із
    зауваженнями», а не чистий успіх і не провал."""
    v = vr._verdict({"desktop": [
        _flow("info"),
        {"kind": "form_input", "sev": "warn", "msg": "порожня форма проходить сабміт",
         "page": "/"}]}, {"form"})
    assert v["form"]["status"] == "warn"
    assert v["form"]["notes"] == ["порожня форма проходить сабміт"]


def test_verdict_form_absent():
    v = vr._verdict({"desktop": []}, {"form"})
    assert v["form"]["status"] == "none" and "не знайш" in v["form"]["msg"]


def test_verdict_text_counts_only_non_form_rows():
    rows = {"desktop": [
        _item(sev="error"), _item(sev="warn", bg="#111"), _item(sev="warn", bg="#222"),
        _flow("error", "сабміт не дає реакції"),     # форма не має псувати текст
    ]}
    v = vr._verdict(rows, {"text", "form"})
    assert v["text"]["errors"] == 1 and v["text"]["warns"] == 2
    assert v["text"]["rows"] == 3 and v["text"]["fixable"] == 3
    assert v["text"]["status"] == "fail"
    assert v["form"]["status"] == "fail"


def test_verdict_text_clean():
    v = vr._verdict({"desktop": []}, {"text"})
    assert v["text"] == {"status": "ok", "rows": 0, "errors": 0, "warns": 0,
                         "fixable": 0}


# ------------------------------------------------------- кейс flientb-br-pt
# Клон реального сайту: головна лід-форма — ОДНЕ поле email, а сторінка подяки
# зветься demo-connect/ і за адресою невідрізнима від звичайної. На цьому вітку
# прогін спершу писав «форми не знайдено», потім «привело не туди».
def _f(name, typ, **kw):
    return {"name": name, "tag": kw.get("tag", "input"), "type": typ,
            "required": kw.get("required", False), "pattern": "", "placeholder": "",
            "label": "", "visible": kw.get("visible", True),
            "honey": kw.get("honey", False)}


def test_single_email_field_form_is_picked():
    """Лід-форма з одним email — головна форма вітки, а не «замало полів»."""
    lead = _form(sel="form#consultation-form", fields=[_f("email", "email", required=True)])
    assert vr._pick_form([lead])["sel"] == "form#consultation-form"


def test_newsletter_with_honeypot_counts_as_lead_form():
    """email + прихований honeypot: живе поле одне, але форма справжня."""
    f = _form(fields=[_f("email", "email", required=True),
                      _f("middle_name", "text", visible=False, honey=True)])
    assert vr._pick_form([f]) is not None


def test_search_and_login_forms_are_skipped():
    search = _form(sel="form.search", fields=[_f("q", "text"), _f("cat", "text")])
    search2 = _form(sel="form.s2", fields=[_f("term", "search"), _f("x", "text")])
    login = _form(sel="form.login", fields=[_f("email", "email"), _f("pass", "password")])
    assert vr._pick_form([search]) is None
    assert vr._pick_form([search2]) is None
    assert vr._pick_form([login]) is None


def test_lead_form_wins_over_longer_filter_form():
    filt = _form(sel="form.filters", fields=[_f("a", "text"), _f("b", "text"), _f("c", "text")])
    lead = _form(sel="form#lead", fields=[_f("email", "email")])
    assert vr._pick_form([filt, lead])["sel"] == "form#lead"


def test_thanks_page_recognised_by_page_text_not_url():
    """demo-connect/ у назві нічого не каже — але на сторінці «We'll be in
    touch!». Без цього робоча форма позначалась як «привело не туди»."""
    out = _verdict(landed=BASE_URL + "demo-connect/index.html?email=a%40b.c",
                   status=200, expect="",
                   landed_text="Demo Connect | We'll be in touch! Thank you for requesting")
    assert out[0]["sev"] == "info" and "форма працює" in out[0]["msg"]


def test_unexpected_page_without_thanks_text_stays_warn():
    out = _verdict(landed=BASE_URL + "platform/index.html", status=200, expect="",
                   landed_text="Our Platform | Automate your advertising")
    assert out[0]["sev"] == "warn"


# ------------------------------------------------- багатокрокова форма
# Кейси studio_br-regulamenta… / studio_br-seguran…: «сабміт» на першому
# кроці лише показує другий. Зонд бачив зміну сторінки і зараховував це за
# ajax-відповідь — тест давав ✅, жодного разу не дійшовши до відправки.
def test_step_switch_is_not_an_ajax_answer():
    """Коли кроки перемикались, ajax у вердикт не передається — і без
    переходу це помилка, а не «форма відповідає»."""
    out = _verdict(landed="", ajax=None, steps=1)
    assert len(out) == 1
    assert out[0]["sev"] == "error"
    assert "пройдено кроків: 2" in out[0]["msg"]


def test_success_after_steps_reports_how_many():
    out = _verdict(landed=BASE_URL + "thank-you.html", status=200, steps=1)
    assert out[0]["sev"] == "info"
    assert "форма працює (пройдено кроків: 2)" in out[0]["msg"]


def test_endless_wizard_is_reported_as_never_sent():
    out = _verdict(landed="", steps=vr.MAX_FORM_STEPS - 1)
    assert out[0]["sev"] == "error"
    assert "не відправляється" in out[0]["msg"]


def test_single_step_message_has_no_step_suffix():
    out = _verdict(landed=BASE_URL + "thank-you.html", status=200)
    assert "пройдено кроків" not in out[0]["msg"]


def test_ajax_answer_still_wins_when_there_were_no_steps():
    out = _verdict(landed="", ajax={"thanksAppeared": True}, steps=0)
    assert out[0]["sev"] == "info" and "ajax" in out[0]["msg"]


def test_merge_fill_joins_steps():
    """Звіт має показувати поля ОБОХ кроків, інакше в «заповнено» видно лише
    перший крок."""
    a = {"filled": ["interest=base"], "skipped": [], "invalid": [], "formValid": False}
    b = {"filled": ["name=Ana", "email=a@b.co"], "skipped": ["website (honeypot)"],
         "invalid": [], "formValid": True}
    m = vr._merge_fill(vr._merge_fill({}, a), b)
    assert m["filled"] == ["interest=base", "name=Ana", "email=a@b.co"]
    assert m["skipped"] == ["website (honeypot)"]
    assert m["formValid"] is True


# ------------------------------------------------- хедер накрив hero
def _ov(**kw):
    base = {"kind": "hero_overlap", "sev": "error", "sel": "main > section.hero",
            "page": "/", "txt": "Entendé tu dinero",
            "msg": "хедер (fixed, 64px) накриває текст першої секції на 44px",
            "openTag": '<section class="hero">', "tagIx": 0, "tagTotal": 1,
            "fix": {"padTop": 64, "to": "padding-top:64px"}}
    base.update(kw)
    return base


def test_hero_overlap_merges_across_pages_despite_different_px():
    """Хедер накриває hero на кожній сторінці, але на різну кількість
    пікселів — заголовки різної довжини. Це один баг і одна правка."""
    out = vr._merge([
        _ov(),
        _ov(page="/about.html", msg="хедер (fixed, 64px) накриває текст першої секції на 31px"),
    ])
    assert len(out) == 1
    assert out[0]["dups"] == 2 and out[0]["pages"] == ["/", "/about.html"]


def test_hero_overlap_on_another_section_stays_separate():
    out = vr._merge([_ov(), _ov(sel="main > section.banner")])
    assert len(out) == 2


def test_fix_decl_maps_kind_to_declaration():
    assert vr._fix_decl(_item()) == ("color", "#354340")
    assert vr._fix_decl(_ov()) == ("padding-top", "64px")
    assert vr._fix_decl(_ov(fix=None)) is None
    assert vr._fix_decl({"kind": "empty_block"}) is None


def test_patch_style_adds_and_replaces_declaration():
    assert (vr._patch_style('<section class="hero">', "padding-top", "64px")
            == '<section class="hero" style="padding-top:64px !important">')
    # своє значення перетирається, чуже лишається
    assert (vr._patch_style('<section style="min-height:92vh; padding-top:8px">',
                            "padding-top", "64px")
            == '<section style="min-height:92vh; padding-top:64px !important">')
    assert (vr._patch_style("<img src='a.png'/>", "color", "#fff")
            == '<img src=\'a.png\' style="color:#fff !important"/>')


def test_patch_style_does_not_confuse_prefix_properties():
    """`padding-top` не має вбивати `padding` чи `padding-bottom` поруч."""
    out = vr._patch_style('<div style="padding:10px; padding-bottom:4px">',
                          "padding-top", "64px")
    assert "padding:10px" in out and "padding-bottom:4px" in out
    assert out.count("padding-top") == 1


# ------------------------------------------------- джерело node-вайтів
def test_source_extensions_cover_node_components():
    """Знахідка приходить з DOM зібраної сторінки, а правити треба джерело:
    у Nuxt це `.vue`, у Next — `.tsx`. Без них КОЖНА знахідка node-вітки
    відсіювалась як «елемент не знайдено у джерелі» — 0 правок із ~180
    на 16 наявних прогонах."""
    for ext in (".html", ".htm", ".php", ".vue", ".tsx"):
        assert ext in vr.SRC_EXT, (ext, vr.SRC_EXT)


def test_patch_style_keeps_vue_template_valid():
    """У `.vue` тег правиться так само: атрибут дописується перед `>`,
    класи й прив'язки лишаються цілі."""
    out = vr._patch_style('<span class="block text-emerald-500">', "color", "#00a971")
    assert out == '<span class="block text-emerald-500" style="color:#00a971 !important">', out


def test_patch_style_does_not_touch_a_bound_style():
    """`:style` — це вираз Vue, і другий, статичний `style` поруч легітимний:
    перетирати треба лише СВІЙ статичний, а прив'язку не чіпати."""
    out = vr._patch_style('<div :style="heroBg" class="hero">', "padding-top", "64px")
    assert ':style="heroBg"' in out, out
    assert out.count("padding-top") == 1, out


def test_patch_style_on_multiline_tag_stays_valid():
    """У Vue-шаблонах атрибути часто в стовпчик — закривна дужка на своєму
    рядку. Патч не сміє її загубити."""
    tag = '<a\n  href="/#form"\n  class="btn"\n>'
    out = vr._patch_style(tag, "color", "#000000")
    assert out.count("<a") == 1 and out.rstrip().endswith(">"), out
    assert 'href="/#form"' in out and 'class="btn"' in out, out
    assert 'style="color:#000000 !important"' in out, out


# ------------------------- запасний матчер по класу (v-for у node-вайтах)
A_SRC = '<a :href="page.route" class="text-white/80 hover:text-orange-600 text-sm">'
A_DOM = '<a href="/a-empresa" class="text-white/80 hover:text-orange-600 text-sm">'


def test_class_rx_matches_the_same_node_with_a_bound_attribute():
    """`v-for` з `:href` рендериться вісьмома `<a href="/…">` з ОДНОГО вузла:
    дослівно такого тега в джерелі немає, спільним лишається клас."""
    assert vr._tag_rx(A_DOM).search(A_SRC) is None
    assert vr._class_rx(A_DOM).search(A_SRC) is not None


def test_class_rx_needs_a_class_to_be_a_signature():
    assert vr._class_rx("<a href=\"/x\">") is None
    assert vr._class_rx('<a class="" href="/x">') is None


def test_class_rx_does_not_match_a_different_class():
    other = '<a :href="page.route" class="text-white/70 text-sm">'
    assert vr._class_rx(A_DOM).search(other) is None


def test_class_rx_keeps_the_tag_name_significant():
    """Той самий клас на іншому тезі — інший елемент; інакше фікс кольору
    посилання поїхав би у `<span>` поруч."""
    same_class_other_tag = '<span class="text-white/80 hover:text-orange-600 text-sm">'
    assert vr._class_rx(A_DOM).search(same_class_other_tag) is None


def test_class_rx_ignores_other_attributes_and_their_order():
    for src in ('<a class="text-white/80 hover:text-orange-600 text-sm" :href="p">',
                "<a :key='p.id' :href='p' class='text-white/80 hover:text-orange-600 text-sm'>",
                '<a\n  :href="p"\n  class="text-white/80 hover:text-orange-600 text-sm"\n>'):
        assert vr._class_rx(A_DOM).search(src) is not None, src


def _fake_snapshot(monkey_src: dict):
    """Підміняє знімок вітки і звіт — без GitLab і без Chrome."""
    class _R:
        @staticmethod
        def snapshot_files(_b):
            return list(monkey_src)

        @staticmethod
        def read_snapshot_file(_b, p):
            return monkey_src[p].encode("utf-8")
    return _R


def test_compute_fixes_falls_back_to_class_for_vfor_nodes():
    """Кейс nwf-dol-esclalefote-br-pt: 13 знахідок футера, усі «не знайдено
    у джерелі», бо `href` там прив'язка. По класу правляться всі."""
    src = {"src/components/BottomSection.vue":
           "<template><footer>\n"
           '  <li v-for="p in mainPages"><' + A_SRC[1:] + "Site</a></li>\n"
           '  <li v-for="p in legalPages"><' + A_SRC[1:] + "Legal</a></li>\n"
           "</footer></template>\n"}
    item = {"kind": "contrast", "fix": {"to": "#171717"}, "page": "/",
            "sel": "footer a", "txt": "Vamos conversar",
            "anchors": [{"openTag": A_DOM, "tagIx": 0, "tagTotal": 1}]}
    import sys
    old_mod, old_load = sys.modules.get("runner"), vr.load
    sys.modules["runner"] = _fake_snapshot(src)
    vr.load = lambda _b: {"views": {"desktop": [item]}}
    try:
        res = vr.compute_fixes("nwf-dol-esclalefote-br-pt")
    finally:
        vr.load = old_load
        if old_mod is not None: sys.modules["runner"] = old_mod
        else: sys.modules.pop("runner", None)
    assert res["skipped"] == [], res["skipped"]
    assert len(res["applied"]) == 1, res["applied"]
    out = res["edits"]["src/components/BottomSection.vue"][1]
    # обидва однакові вузли пофікшені, прив'язка ціла
    assert out.count('style="color:#171717 !important"') == 2, out
    assert out.count(':href="page.route"') == 2, out


def test_class_fallback_is_not_used_when_the_literal_tag_exists():
    """Коли дослівний тег у джерелі є, індекс DOM лишається значущим —
    по класу не збиваємось."""
    src = {"page.html": "<p class=\"a\">x</p><p class=\"a\">y</p>"}
    item = {"kind": "contrast", "fix": {"to": "#111"}, "page": "/",
            "sel": "p.a", "txt": "y",
            "anchors": [{"openTag": '<p class="a">', "tagIx": 1, "tagTotal": 2}]}
    import sys
    old_mod, old_load = sys.modules.get("runner"), vr.load
    sys.modules["runner"] = _fake_snapshot(src)
    vr.load = lambda _b: {"views": {"desktop": [item]}}
    try:
        res = vr.compute_fixes("b")
    finally:
        vr.load = old_load
        if old_mod is not None: sys.modules["runner"] = old_mod
        else: sys.modules.pop("runner", None)
    out = res["edits"]["page.html"][1]
    assert out.count("style=") == 1, out          # тільки другий <p>
    assert out.startswith('<p class="a">x</p>'), out


def _fixes_for(src: dict, items: list, branch: str = "b"):
    import sys
    old_mod, old_load = sys.modules.get("runner"), vr.load
    sys.modules["runner"] = _fake_snapshot(src)
    vr.load = lambda _b: {"views": {"desktop": items}}
    try:
        return vr.compute_fixes(branch)
    finally:
        vr.load = old_load
        if old_mod is not None: sys.modules["runner"] = old_mod
        else: sys.modules.pop("runner", None)


TEL = '<a href="tel:+41219219720" style="color:#f7eaee !important">'


def test_noscript_copy_does_not_break_the_page_equals_file_rule():
    """Кейс zipleh-coiqanu.ch-ch-fr: 9-й tel-лінк лежить у <noscript>, браузер
    не створює з нього елемента, тож на сторінці близнюків 8, а в джерелі 9 —
    і КОЖЕН фікс телефону відмовлявся «відповідність неоднозначна». Рахунок і
    індекси мусять іти по DOM-виду джерела: без noscript/коментарів/скриптів.
    Фікси близнюків тут РІЗНІ (два різні фони), тож фолбек «однакові
    декларації» не рятує — рятує лише правильний рахунок."""
    src = {"index.html":
           "<p>" + TEL + "a</a></p>\n"
           "<dd>" + TEL + "b</a></dd>\n"
           "<noscript><p>" + TEL + "c</a></p></noscript>\n"
           "<!-- " + TEL + "d</a> -->\n"
           "<script>var tpl = '" + TEL + "e</a>';</script>\n"}
    items = [
        {"kind": "contrast", "fix": {"to": "#5c4a42"}, "page": "/", "sel": "p a",
         "txt": "a", "anchors": [{"openTag": TEL, "tagIx": 0, "tagTotal": 2}]},
        {"kind": "contrast", "fix": {"to": "#354340"}, "page": "/", "sel": "dd a",
         "txt": "b", "anchors": [{"openTag": TEL, "tagIx": 1, "tagTotal": 2}]},
    ]
    res = _fixes_for(src, items)
    assert res["skipped"] == [], res["skipped"]
    out = res["edits"]["index.html"][1]
    assert "#5c4a42" in out.split("<dd>")[0], out       # перший близнюк
    assert "#354340" in out.split("<dd>")[1], out       # другий близнюк
    # копії у noscript, коменті і скрипті лишаються як були
    assert out.count("#f7eaee") == 3, out


def test_commented_out_markup_is_not_counted_as_a_twin():
    src = {"page.html": "<p class=\"a\">x</p>\n<!-- <p class=\"a\">старе</p> -->\n"}
    item = {"kind": "contrast", "fix": {"to": "#111111"}, "page": "/",
            "sel": "p.a", "txt": "x",
            "anchors": [{"openTag": '<p class="a">', "tagIx": 0, "tagTotal": 1}]}
    res = _fixes_for(src, [item])
    assert res["skipped"] == [], res["skipped"]
    out = res["edits"]["page.html"][1]
    assert out.count("style=") == 1 and "старе" in out, out
    assert "<!-- <p class=\"a\">старе</p> -->" in out, out


# ------------------------------------------------- сторінки vue-вайта
# `_list_pages` перебирає ФАЙЛИ деплою, а vite-ssg складає весь сайт в один
# `dist/index.php` — тож на `nwf-zuontfug-befelur-ch-de` він віддавав `['/']`
# при 11 роутах, і зонд ніколи не заходив на /sektoren та /hilfe, де ВЕСЬ текст
# статті стояв `text-white/80` на секції `bg-white` (контраст 1.00).
ROUTER_JS = """
import { createRouter } from 'vue-router'
const routes = [
  { path: '/', name: 'home', component: () => import('../pages/Home.vue') },
  { path: '/sektoren', name: 'industries', component: () => import('../pages/Industries.vue') },
  { path: '/hilfe', name: 'help', component: () => import('../pages/Help.vue') },
  { path: '/danke', name: 'thanks', component: () => import('../pages/Thanks.vue') },
  { path: '/blog/:slug', name: 'post', component: () => import('../pages/Post.vue') },
  { path: '/:pathMatch(.*)*', name: 'fehler', component: () => import('../pages/Error.vue') },
]
"""


def _with_router(body, rel="src/router/index.js"):
    """Тимчасовий знімок вітки з файлом роутера; повертає (шлях, відкат)."""
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix="qa_lab-router-"))
    if body is not None:
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    old = vr.snapshot_dir
    vr.snapshot_dir = lambda _b: d
    return d, (lambda: setattr(vr, "snapshot_dir", old))


def test_router_pages_reads_client_routes():
    _d, undo = _with_router(ROUTER_JS)
    try:
        got = vr._router_pages("nwf-x")
    finally:
        undo()
    assert got == ["/", "/sektoren", "/hilfe", "/danke"], got


def test_router_pages_skips_dynamic_and_catch_all():
    """`/blog/:slug` без значення не відкрити, а `/:pathMatch(.*)*` — це ловець
    404, не сторінка. Обидва мусять лишитися поза списком."""
    _d, undo = _with_router(ROUTER_JS)
    try:
        got = vr._router_pages("nwf-x")
    finally:
        undo()
    assert not [p for p in got if ":" in p or "*" in p or "(" in p], got


def test_router_pages_empty_without_router():
    _d, undo = _with_router(None)
    try:
        assert vr._router_pages("nwf-x") == []
    finally:
        undo()


def test_router_pages_accepts_typescript_router():
    _d, undo = _with_router(ROUTER_JS, rel="src/router/index.ts")
    try:
        assert "/sektoren" in vr._router_pages("nwf-x")
    finally:
        undo()


def test_router_pages_ignores_relative_paths():
    """Вкладені роути пишуть `path: 'kinder'` без слеша — це НЕ адреса
    сторінки сама по собі, тож у список вона не потрапляє."""
    body = "const routes = [{ path: '/eltern', children: [{ path: 'kinder' }] }]"
    _d, undo = _with_router(body)
    try:
        got = vr._router_pages("nwf-x")
    finally:
        undo()
    assert got == ["/eltern"], got


if __name__ == "__main__":
    run(dict(globals()))
