"""Пул швейцарських UID (CHE-xxx.xxx.xxx) для ch-de вайтів.

Швейцарський сайт компанії без UID у футері/імпресумі виглядає
несправжнім — чек `uid_che` ловить це, а фікс бере номер ЗВІДСИ. Двигун
той самий, що й у `cnpj_pool` (`regno_pool.Pool`): сід з репо, видалене
не воскресає, вітка тримає свій номер.

Сід: 500 активних (EXISTIEREND) AG/GmbH із Zefix (федеральний реєстр,
публічний пошук), по ~30 на сферу, усі з валідною контрольною цифрою.
"""
from __future__ import annotations

import re
from pathlib import Path

import regno_pool

DIGITS_RX = re.compile(r"\D+")
# UID: 9 цифр з контрольною (модуль-11, ваги 5 4 3 2 7 6 5 4)
_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4)


def canonical(raw: str) -> str:
    """«CHE-123.456.789» / «CHE123456789» / 9 цифр → «CHE-123.456.789»;
    '' — коли це не UID за формою."""
    s = (raw or "").strip().upper()
    if s.startswith("CHE"):
        s = s[3:]
    d = DIGITS_RX.sub("", s)
    if len(d) != 9:
        return ""
    return f"CHE-{d[0:3]}.{d[3:6]}.{d[6:9]}"


def valid(raw: str) -> bool:
    """Контрольна цифра UID: 11 − (Σ dᵢ·wᵢ mod 11); 10 → номер неможливий,
    11 → 0."""
    num = canonical(raw)
    if not num:
        return False
    d = [int(c) for c in DIGITS_RX.sub("", num)]
    r = 11 - sum(a * w for a, w in zip(d[:8], _WEIGHTS)) % 11
    if r == 10:
        return False
    return d[8] == (0 if r == 11 else r)


SEED = Path(__file__).resolve().parent / "uid_seed.json"

# сфера пулу ↔ тематика вайта: корені видимого тексту (de-ch передусім).
# Назви ті самі, що в cnpj_pool — UI показує одну колонку «сфера».
SPHERES = [
    ("Медицина", r"klinik|praxis|arzt|ärzt|zahn|dental|physio|therap"
                 r"|gesundheit|spital|medizin"),
    ("Фармація", r"apothek|pharma|drogerie"),
    ("Харчування", r"restaurant|gastro|bäcker|baeck|konditor|catering|küche"
                   r"|kueche|café|cafe\b|pizzeria|bistro"),
    ("Готелі/туризм", r"hotel|pension|ferien|reise|tourismus|resort|chalet"
                      r"|gasthof|gasthaus"),
    ("Ритейл", r"handel|shop|laden|boutique|markt|verkauf|store"),
    ("Будівництво", r"\bbau\b|bauunternehm|architekt|sanitär|sanitaer"
                    r"|maler|schreiner|dach|renovation|umbau|zimmerei"),
    ("Нерухомість", r"immobilie|liegenschaft|wohnung|hausverwalt|makler"),
    ("IT", r"informatik|software|digital|\bit\b|\bweb\b|\bapp\b|daten"
           r"|technolog|automation|cloud"),
    ("Логістика", r"transport|logistik|spedition|umzug|kurier|lieferung"),
    ("Освіта", r"schule|bildung|akademie|kurs|lernen|ausbildung|fettmagv"
               r"|nachhilfe|seminar"),
    ("Агро", r"agrar|landwirt|garten|bauernhof|hof\b|gärtner|gaertner"),
    ("Авто", r"garage|carrosserie|automobil|\bauto\b|fahrzeug|werkstatt"
             r"|reifen"),
    ("Енергетика", r"solar|energie|elektro|photovoltaik|wärmepumpe|heizung"),
    ("Краса/фітнес", r"coiffeur|kosmetik|fitness|beauty|\bspa\b|massage"
                     r"|nagel|wellness|yoga"),
    ("Юристи/бухгалтерія", r"treuhand|advokat|rechtsanw|anwalt|notar"
                           r"|buchhalt|revision|steuer"),
    ("Фінанси", r"finanz|invest|kapital|kredit|versicherung|vermögen"
                r"|consulting|beratung|\bbank"),
    ("Промисловість", r"industrie|metall|fabrik|produktion|maschinen"
                      r"|werk\b|fertigung"),
]

_POOL = regno_pool.Pool(
    key="uid", state_file="uid_pool.json", removed_file="uid_removed.json",
    assign_file="uid_assign.json", seed=lambda: SEED,
    canonical=canonical, valid=valid, spheres=SPHERES,
    errors={"form": "це не UID: треба CHE- і 9 цифр (CHE-123.456.789)",
            "check": "невалідний UID: контрольна цифра не сходиться",
            "dup": "такий UID уже в пулі"})

load = _POOL.load
add = _POOL.add
remove = _POOL.remove
assignments = _POOL.assignments
sphere_for = _POOL.sphere_for
pick = _POOL.pick
