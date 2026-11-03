"""Панель перекладу: витяг чужомовних фрагментів і точна заміна.

Мережі в тестах немає — MyMemory інжектується фейком.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                              # noqa: E402

sys.path.insert(0, str(ROOT))
import runner                                               # noqa: E402
import translate_text as tt                                 # noqa: E402

PT = ("Oferecemos os melhores serviços de consultoria para o seu negócio. "
      "A nossa equipa vai ajudar você com todas as questões que tem sobre "
      "estratégia, e temos certeza de que isso é mais do que você pode "
      "esperar de qualquer outra empresa no mercado. ") * 3


def _page(body_extra=""):
    return ('<!DOCTYPE html>\n<html lang="pt-BR">\n<head><title>X</title></head>\n'
            f'<body><main><p>{PT}</p>{body_extra}</main></body></html>')


class FakeResp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttp:
    """Лічильник викликів — щоб перевірити кеш однакових фрагментів."""
    def __init__(self, table=None, status=200):
        self.table = table or {}
        self.calls = []
        self.status = status

    def get(self, url, params=None, timeout=None, headers=None):
        q = (params or {}).get("q", "")
        self.calls.append(q)
        out = self.table.get(q, "TRADUZIDO: " + q)
        return FakeResp({"responseData": {"translatedText": out},
                         "responseStatus": self.status}, self.status)


def _fake_branch(files: dict):
    saved = (runner.snapshot_files, runner.read_snapshot_file)
    runner.snapshot_files = lambda br: list(files)
    runner.read_snapshot_file = lambda br, p: files[p].encode("utf-8")
    return saved


def _restore(saved):
    runner.snapshot_files, runner.read_snapshot_file = saved


# ---------------------------------------------------------------- переклад
def test_translate_returns_text_without_note():
    http = FakeHttp({"Записаться на обучение": "Inscreva-se no curso"})
    out, note = tt.translate("Записаться на обучение", "pt", http=http,
                             sleep=lambda s: None)
    assert out == "Inscreva-se no curso" and note == ""


def test_translate_reports_api_failure_instead_of_raising():
    class Boom:
        def get(self, *a, **k):
            raise RuntimeError("no network")
    out, note = tt.translate("текст", "pt", http=Boom(), sleep=lambda s: None)
    assert out == "" and "недоступний" in note


def test_translate_flags_echo_as_untranslated():
    http = FakeHttp({"Ok": "ok"})
    out, note = tt.translate("Ok", "pt", http=http, sleep=lambda s: None)
    assert out == "" and "вручну" in note


def test_translate_refuses_too_long_fragment():
    out, note = tt.translate("x" * 600, "pt", http=FakeHttp(),
                             sleep=lambda s: None)
    assert out == "" and "завеликий" in note


def test_translate_empty_is_noop():
    out, note = tt.translate("   ", "pt", http=FakeHttp(), sleep=lambda s: None)
    assert out == "" and note == "порожній фрагмент"


# ---------------------------------------------------------------- скан
def test_scan_finds_cyrillic_fragment_with_draft():
    saved = _fake_branch({"index.html": _page(
        '<a class="btn">Записаться на обучение</a>')})
    http = FakeHttp({"Записаться на обучение": "Inscreva-se no curso"})
    try:
        r = tt.scan("br", http=http, sleep=lambda s: None)
    finally:
        _restore(saved)
    assert len(r["items"]) == 1, r
    it = r["items"][0]
    assert it["text"] == "Записаться на обучение"
    assert it["kind"] == "script" and it["lang"] == "cyrl"
    assert it["target"] == "pt" and it["line"] == 4
    assert it["draft"] == "Inscreva-se no curso" and it["note"] == ""


def test_scan_translates_repeated_fragment_once():
    """Та сама кнопка на кількох сторінках — один виклик API."""
    body = '<a class="btn">Записаться на обучение</a>'
    saved = _fake_branch({"index.html": _page(body), "faq.html": _page(body),
                          "contact.html": _page(body)})
    http = FakeHttp()
    try:
        r = tt.scan("br", http=http, sleep=lambda s: None)
    finally:
        _restore(saved)
    assert len(r["items"]) == 3, r
    assert len(http.calls) == 1, http.calls


def test_scan_skips_page_without_lang():
    saved = _fake_branch({"x.html": "<html><body><p>Записаться на обучение</p></body></html>"})
    try:
        r = tt.scan("br", translate_drafts=False)
    finally:
        _restore(saved)
    assert r["items"] == []
    assert any("lang" in s["why"] for s in r["skipped"]), r["skipped"]


def test_scan_ignores_non_page_files():
    saved = _fake_branch({"css/style.css": "/* авто-страховка баннера */",
                          "js/main.js": "// бьёт любой CSS"})
    try:
        r = tt.scan("br", translate_drafts=False)
    finally:
        _restore(saved)
    assert r["items"] == [] and r["skipped"] == []


def test_scan_without_drafts_leaves_them_empty():
    saved = _fake_branch({"index.html": _page('<a>Записаться на обучение</a>')})
    try:
        r = tt.scan("br", translate_drafts=False)
    finally:
        _restore(saved)
    assert r["items"][0]["draft"] == ""


def test_scan_requires_synced_branch():
    saved = _fake_branch({})
    try:
        tt.scan("br")
        assert False, "мав кинути ValueError"
    except ValueError as e:
        assert "синхронізована" in str(e)
    finally:
        _restore(saved)


# ---------------------------------------------------------------- заміна
def test_apply_replaces_fragment_in_place():
    page = _page('<a class="btn">Записаться на обучение</a>')
    saved = _fake_branch({"index.html": page})
    try:
        r = tt.apply_edits("br", [{"path": "index.html",
                                   "text": "Записаться на обучение",
                                   "replacement": "Inscreva-se no curso"}])
    finally:
        _restore(saved)
    assert r["applied"] == 1 and r["skipped"] == []
    new = r["actions"][0]["new"]
    assert '<a class="btn">Inscreva-se no curso</a>' in new
    assert "Записаться" not in new
    assert new.count(PT.strip()[:40]) == page.count(PT.strip()[:40])


def test_apply_matches_fragment_with_different_whitespace():
    """У файлі фрагмент з переносами, а в панелі — схлопнутий рядок."""
    saved = _fake_branch({"index.html": _page(
        '<a class="btn">Записаться\n          на обучение</a>')})
    try:
        r = tt.apply_edits("br", [{"path": "index.html",
                                   "text": "Записаться на обучение",
                                   "replacement": "Inscreva-se"}])
    finally:
        _restore(saved)
    assert r["applied"] == 1, r
    assert "Inscreva-se" in r["actions"][0]["new"]


def test_apply_skips_missing_fragment_honestly():
    saved = _fake_branch({"index.html": _page()})
    try:
        r = tt.apply_edits("br", [{"path": "index.html", "text": "чогось нема",
                                   "replacement": "x"}])
    finally:
        _restore(saved)
    assert r["actions"] == [] and r["applied"] == 0
    assert "не знайдено" in r["skipped"][0]["why"]


def test_apply_ignores_empty_replacement():
    saved = _fake_branch({"index.html": _page('<a>Записаться на обучение</a>')})
    try:
        r = tt.apply_edits("br", [{"path": "index.html",
                                   "text": "Записаться на обучение",
                                   "replacement": "   "}])
    finally:
        _restore(saved)
    assert r["actions"] == [] and r["applied"] == 0


def test_apply_groups_several_edits_per_file_into_one_action():
    saved = _fake_branch({"index.html": _page(
        '<a>Записаться на обучение</a><span>Оплата не онлайн</span>')})
    try:
        r = tt.apply_edits("br", [
            {"path": "index.html", "text": "Записаться на обучение",
             "replacement": "Inscreva-se"},
            {"path": "index.html", "text": "Оплата не онлайн",
             "replacement": "Pagamento offline"}])
    finally:
        _restore(saved)
    assert len(r["actions"]) == 1 and r["applied"] == 2
    new = r["actions"][0]["new"]
    assert "Inscreva-se" in new and "Pagamento offline" in new


def test_apply_replaces_every_occurrence_in_file():
    saved = _fake_branch({"index.html": _page(
        '<a>Записаться на обучение</a><a>Записаться на обучение</a>')})
    try:
        r = tt.apply_edits("br", [{"path": "index.html",
                                   "text": "Записаться на обучение",
                                   "replacement": "Inscreva-se"}])
    finally:
        _restore(saved)
    assert r["actions"][0]["new"].count("Inscreva-se") == 2


if __name__ == "__main__":
    run(dict(globals()))
