"""Пул CNPJ-номерів для br-pt вайтів.

Бразильський вайт без CNPJ у футері виглядає несправжнім — чек `cnpj`
ловить це, а фікс бере номер ЗВІДСИ. Пул наповнюють люди у вкладці
«Журнал → БД по гео»; номери валідуються контрольними цифрами ще на
вході, щоб у футери не поїхали одруки. Двигун (стан, сід, видалені,
призначення, вибір) — спільний `regno_pool.Pool`, той самий, що й у
`uid_pool` для ch-de.
"""
from __future__ import annotations

import re
from pathlib import Path

import regno_pool

# 12.345.678/0001-90 — канонічний запис; приймаємо і голі 14 цифр
DIGITS_RX = re.compile(r"\D+")


def canonical(raw: str) -> str:
    """14 цифр → «XX.XXX.XXX/XXXX-XX»; '' — коли це не CNPJ за формою."""
    d = DIGITS_RX.sub("", raw or "")
    if len(d) != 14:
        return ""
    return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"


def valid(raw: str) -> bool:
    """Контрольні цифри CNPJ (класичний модуль-11)."""
    d = DIGITS_RX.sub("", raw or "")
    if len(d) != 14 or d == d[0] * 14:
        return False
    nums = [int(c) for c in d]
    for k in (12, 13):
        weights = list(range(k - 7, 1, -1)) + list(range(9, 1, -1))
        s = sum(n * w for n, w in zip(nums[:k], weights[-k:]))
        dv = s % 11
        dv = 0 if dv < 2 else 11 - dv
        if nums[k] != dv:
            return False
    return True


# сід з репо: 507 записів (58 з cnpj.biz + 449 з парсера cnpj_companies,
# статус ATIVA). Порожній стан наповнюється сідом цілком; у НЕпорожній
# стан нові сід-номери ДОЛИВАЮТЬСЯ (нова партія їде на прод деплоєм),
# але видалене руками не воскресає — реєстр cnpj_removed.json
SEED = Path(__file__).resolve().parent / "cnpj_seed.json"

# сфера пулу ↔ тематика вайта: корені видимого тексту (pt-br передусім).
# Назви = сектори парсера cnpj_companies; старі записи («Нерухомість/SPE»,
# «Фінанси/холдинги») матчаться базою до «/». «Закордон» — лише фолбек.
SPHERES = [
    ("Медицина", r"cl[ií]nic|sa[uú]de|m[eé]dic|dental|odont|terapia|fisio"
                 r"|hospital"),
    ("Фармація", r"farm[aá]c|drogar"),
    ("Харчування", r"restaurante|gastro|cozinh|caf[eé]|lanchonete|comida"
                   r"|sabor|culin[aá]r|chef|padaria"),
    ("Готелі/туризм", r"hotel|pousada|retiro|villa|hospeda|turis|viag"
                      r"|resort|estadia|passeio"),
    ("Ритейл", r"loja|mercado|varej|store|shop|com[eé]rcio"),
    ("Будівництво", r"constru|engenhar|arquitet|obra\b|reforma"),
    ("Нерухомість", r"imobili|im[oó]ve|resid[eê]nc|propriedade|casa\b"),
    ("IT", r"tecnolog|software|digital|sistema|dados|inova|\bweb\b|\bapp\b"
           r"|automa|intelig"),
    ("Логістика", r"transport|log[ií]stic|entrega|frete|frota"),
    ("Освіта", r"escola|curso|educa|academ|ensino|aprend|treinament|coleg"),
    ("Агро", r"\bagro|agr[ií]col|fazenda|pecu[aá]r|cultiv"),
    ("Авто", r"motor\b|carro|ve[ií]cul|oficina|mec[aâ]nic|autope|automotiv"),
    ("Енергетика", r"energia|solar|e[oó]lic|fotovolta|el[eé]tric"),
    ("Краса/фітнес", r"belez|est[eé]tic|sal[aã]o|\bspa\b|barb|fitness"
                     r"|trein[oa]\b|muscula"),
    ("Юристи/бухгалтерія", r"advoc|jur[ií]d|direito|contab|cont[aá]b"
                           r"|advogad"),
    ("Фінанси", r"financ|invest|capital|cr[eé]dit|fiscal|\bbank"
                r"|patrim[oô]ni|consult"),
    ("Промисловість", r"ind[uú]stri|metal|f[aá]bric|manufatur|produ[cç][aã]o"),
]

_POOL = regno_pool.Pool(
    key="cnpj", state_file="cnpj_pool.json", removed_file="cnpj_removed.json",
    assign_file="cnpj_assign.json", seed=lambda: SEED,
    canonical=canonical, valid=valid, spheres=SPHERES,
    errors={"form": "це не CNPJ: треба 14 цифр (XX.XXX.XXX/XXXX-XX)",
            "check": "невалідний CNPJ: контрольні цифри не сходяться",
            "dup": "такий CNPJ уже в пулі"})

load = _POOL.load
add = _POOL.add
remove = _POOL.remove
assignments = _POOL.assignments
sphere_for = _POOL.sphere_for
pick = _POOL.pick
