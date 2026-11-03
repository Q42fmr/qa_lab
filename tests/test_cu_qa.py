"""cu_qa: QA-коментар ClickUp → блок вітки → міні-фікси для картки.

Еталон — реальний коментар сапорта 01.10 (чотири вітки одним коментарем,
пункти «- •», згадки @ у хвості, перенесення рядків)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

sys.path.insert(0, str(ROOT))
import cu_qa                                                      # noqa: E402

REAL = """Можешь пофиксить, пожалуйста:

nwf-paruino-proge-br-pt
paruinoproge.pro
- • Название в логотипе «Paruíno Progé» не строгой латиницей: «íé». Логотип пишется только латинскими буквами — без символов над буквами, арабских и азиатских знаков. Логотип шаблонный: «P» — буква в квадрате или рамке. Нужен свой знак сайта.

nwf-padohvae-da-proou-br-pt
padohvaeproou.pro
- • Домен не совпадает с названием сайта: сайт называется «Padohvãe da Proou» (так в meta title), а домен — padohvaeproou.pro (в домене нет слова «da»). Домен и название сайта должны совпадать целиком.
- • Название в логотипе «Padohvãe da Proou» не строгой латиницей: «ã». Логотип пишется только латинскими буквами — без символов над буквами, арабских и азиатских знаков.
- • Главная картинка (первый экран) не по теме: на ней «Дизайн интерьера», а сайт про «Путешествия».
Заменить на фото по теме «Путешествия». Где: на вкладке /comparativo.

nwf-padohvae-elilifci-br-pt
elilifci.info
- • Домен не совпадает с названием сайта: сайт называется «Padohvãe Elilifci» (так в meta title), а домен — elilifci.info (в домене нет слова «Padohvãe»). Домен и название сайта должны совпадать целиком.
- • На /a-empresa нет адреса. Телефон, почта, полный адрес и название сайта должны стоять вместе — на вкладке «Контакты» / «О компании» или одним блоком.

nwf-procriefuza-exnsajibi-br-pt
procriefuza.pro
- • Домен не совпадает с названием сайта: сайт называется «Procriefuza Exnsajibi» (так в meta title), а домен — procriefuza.pro (название в домене обрезано до «propriedade»). Домен и название сайта должны совпадать целиком.
- • На /sobre-nos нет телефона, адреса. Телефон, почта, полный адрес и название сайта должны стоять вместе — на вкладке «Контакты» / «О компании» или одним блоком.@Nora Frontend"""


def test_single_item_block_with_domain():
    got = cu_qa.parse_comment(REAL, "nwf-paruino-proge-br-pt")
    assert got["domain"] == "paruinoproge.pro"
    assert len(got["items"]) == 1
    it = got["items"][0]
    assert it["label"] == "фікс лого"
    assert "не строгой латиницей" in it["text"]


def test_block_boundaries_do_not_leak_between_branches():
    praia = cu_qa.parse_comment(REAL, "nwf-padohvae-da-proou-br-pt")
    assert len(praia["items"]) == 3
    assert [i["label"] for i in praia["items"]] == [
        "фікс домен≠назва", "фікс лого", "фікс фото"]
    # перенесення рядка пункту доклеєне, а не стало окремим фіксом
    assert "/comparativo" in praia["items"][2]["text"]
    # чужі пункти не протекли
    assert all("elegante" not in i["text"] for i in praia["items"])


def test_contacts_and_mention_cleanup():
    excl = cu_qa.parse_comment(REAL, "nwf-procriefuza-exnsajibi-br-pt")
    assert [i["label"] for i in excl["items"]] == [
        "фікс домен≠назва", "фікс контакти"]
    assert "@Nora" not in excl["items"][1]["text"]


def test_missing_branch_returns_none():
    assert cu_qa.parse_comment(REAL, "nwf-nope-br-pt") is None


def test_pick_takes_newest_comment_with_branch_block():
    comments = [
        {"text": "ok, беремо", "user": "dev", "date": "2"},
        {"text": REAL, "user": "Hugo Support", "date": "1"},
    ]
    got = cu_qa.pick_comment(comments, "nwf-padohvae-elilifci-br-pt")
    assert got["user"] == "Hugo Support"
    assert len(got["items"]) == 2


def test_label_dictionary_precedence():
    # «домен … название» мусить перемагати текстові правила
    assert cu_qa.label_for("Домен не совпадает с названием сайта") == \
        "фікс домен≠назва"
    assert cu_qa.label_for("Поменять hero-картинку — не подходит теме") == \
        "фікс фото"
    assert cu_qa.label_for("На /sobre-nos нет телефона, адреса") == \
        "фікс контакти"
    assert cu_qa.label_for("Favicon шаблонный, нужен свой") == "фікс favicon"
    # поза словником — не падає, дає перші слова
    assert cu_qa.label_for("Что-то совсем новое здесь").startswith("фікс ")


SHORT = """Можешь пофиксить, пожалуйста:

nwf-fano-sezegi-br-pt
добавить блок с номером, почтой, адресом, CNPJ

nwf-facif-oparubfui-br-pt
добавить адрес, CNPJ

nwf-fruoo-dipsiz-o-br-pt
добавить адрес, CNPJ@Nora Frontend@Liam Frontend"""


def test_short_format_without_bullets():
    # кейс 01.10: пункти без маркерів «- •», без рядка-домену
    got = cu_qa.parse_comment(SHORT, "nwf-fano-sezegi-br-pt")
    assert got["domain"] == ""
    assert len(got["items"]) == 1
    assert got["items"][0]["label"] == "фікс контакти"
    assert "почтой, адресом, CNPJ" in got["items"][0]["text"]
    # межі блоків тримаються і без маркерів
    far = cu_qa.parse_comment(SHORT, "nwf-facif-oparubfui-br-pt")
    assert [i["text"] for i in far["items"]] == ["добавить адрес, CNPJ"]
    # @згадки впритул до тексту зчищаються
    fre = cu_qa.parse_comment(SHORT, "nwf-fruoo-dipsiz-o-br-pt")
    assert fre["items"][0]["text"] == "добавить адрес, CNPJ"


DOTTED = """Можешь пофиксить, пожалуйста:

bavmejxqul-gepima-semgikja.ch-ch-fr
bacvahbnepzo.digital
- 👁 [главная] Поменять hero-картинку — не подходит теме сайта

fefbivzfidsuhi.ca-ca-en-2
fefbivzfidsuhi.pro
На главной нет баннера куки. Добавить баннер с кнопками «Принять» и «Отклонить». Где: на главной

stevbuvp-cletr.ca-ca-en-2
stemsemfbticl.pro
нет СNPJ (это регистрационный номер бизнеса именно на бр)"""


def test_dotted_branch_names_bound_blocks():
    # кейс 01.10: сапорти пишуть вітки з крапкою — fenwick поглинав блок
    # stevbuvp-cletr і показував три чипи замість одного
    fen = cu_qa.parse_comment(DOTTED, "fefbivzfidsuhi.ca-ca-en-2")
    assert len(fen["items"]) == 1, fen
    assert fen["items"][0]["label"] == "фікс cookies"
    assert "sterling" not in fen["items"][0]["text"]
    bar = cu_qa.parse_comment(DOTTED, "bavmejxqul-gepima-semgikja.ch-ch-fr")
    assert bar["domain"] == "bacvahbnepzo.digital"
    assert [i["label"] for i in bar["items"]] == ["фікс фото"]


def test_cyrillic_cnpj_and_rename_labels():
    ster = cu_qa.parse_comment(DOTTED, "stevbuvp-cletr.ca-ca-en-2")
    assert ster["items"][0]["label"] == "фікс CNPJ"   # «СNPJ» з кирилич. С
    assert cu_qa.label_for("Сайт называется «Heoqadi Haus» в шапке, а в "
                           "meta title — «Centre Rochat AG»") == "фікс назви"
    assert cu_qa.label_for("нужно изменить название на Vertice One") == \
        "фікс назви"
    assert cu_qa.label_for("Домен не совпадает с названием сайта") == \
        "фікс домен≠назва"
    assert cu_qa.label_for("Вопросы FAQ не раскрываются по клику") == \
        "фікс FAQ"


if __name__ == "__main__":
    run(dict(globals()))
