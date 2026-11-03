"""Branch code: захищені класи елементів, закодовані в НАЗВІ вітки.

Специфікація: Whites_maker/branch-code.md (словник тут — дзеркало
авторитетної таблиці; append-only, біти не перевикористовуються).

Формат: `<name>-p<version><mask36><check>-<geo>-<lang>`
(`irecnuwvw-p1f4-ca-en`). Сегмента немає → нічого не захищено — усі
легасі-вітки чинні. v1 без префікса (`irecnuwvw-1f-ca-en`) читається з
позначкою legacy, але ТІЛЬКИ для версії «1» — тому числові слова назв
(`eskufoo-bog-406-br-pt`, `rerhouko-360-ch-fr`) падають у «коду немає»,
а не в хибний захист.

Контракт для динамічної популяції чеків (branch-code.md §Contract):
  * чек, що модифікує контент, декларує `MODIFIES = {"phone", ...}`;
  * runner перед прогоном/фіксами віднімає чеки, чиї MODIFIES
    перетинаються з decode(branch)["protected"];
  * битий чек-символ або невідома версія — СТОП для людини (вітка
    вважається повністю захищеною), вгадувати гірше, ніж зупинитись;
  * невідомі біти (код новіший за словник) — попередження, не падіння.
"""
from __future__ import annotations

import re

# append-only: біт, одного разу виданий, не перевикористовується ніколи
DICT = ["email", "phone", "address", "regno", "company", "hours",
        "brand", "map", "domain", "links", "legal", "media"]
WEIGHTS = [1, 5, 7, 11, 13, 17, 19, 23, 25, 29, 31, 35]  # взаємно прості з 36
_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"

TAIL = re.compile(r"^[a-z]{2,3}$")
SEGMENT = re.compile(r"^p([1-9])([0-9a-z]{1,7})([0-9a-z])$")
LEGACY = re.compile(r"^([1-9])([0-9a-z]{1,7})$")


class BranchCodeError(ValueError):
    """Битий чек-символ або невідома версія: лагодить людина, не декодер."""


def _check(payload: str) -> str:
    total = sum(int(c, 36) * WEIGHTS[i % len(WEIGHTS)]
                for i, c in enumerate(payload))
    return _B36[total % 36]


def _split_tail(branch: str):
    parts = branch.split("-")
    start = len(parts)
    while start > 0 and TAIL.match(parts[start - 1]):
        start -= 1
    count = len(parts) - start
    if count % 2:                       # непарний хвіст → голова = слово назви
        count -= 1
    if count < 2:
        return parts, []
    return parts[: len(parts) - count], parts[len(parts) - count:]


def _bits(mask: int):
    protected = {DICT[b] for b in range(len(DICT)) if mask >> b & 1}
    return protected, mask >> len(DICT) << len(DICT)


def decode(branch: str) -> dict:
    """{"version", "protected": set, "unknown_bits": int, "legacy": bool}.

    Кидає BranchCodeError на битому чек-символі чи чужій версії."""
    none = {"version": None, "protected": set(), "unknown_bits": 0,
            "legacy": False}
    name, tail = _split_tail((branch or "").strip().lower())
    if not tail or not name:
        return none
    seg = name[-1]

    m = SEGMENT.match(seg)
    if m:
        version, mask36, check = m.groups()
        if _check(version + mask36) != check:
            raise BranchCodeError(
                f"код вітки {seg!r} не проходить контрольний символ")
        if version != "1":
            raise BranchCodeError(f"невідома версія коду вітки {version!r}")
        protected, unknown = _bits(int(mask36, 36))
        return {"version": version, "protected": protected,
                "unknown_bits": unknown, "legacy": False}

    m = LEGACY.match(seg)
    if m and m.group(1) == "1":          # v1: заморожений, без чек-символа
        protected, unknown = _bits(int(m.group(2), 36))
        return {"version": "1", "protected": protected,
                "unknown_bits": unknown, "legacy": True}
    return none


def encode(classes) -> str:
    """Сегмент коду для набору класів; порожній набір → '' (чисте ім'я)."""
    mask = 0
    for cls in classes:
        try:
            mask |= 1 << DICT.index(cls)
        except ValueError:
            raise BranchCodeError(f"невідомий клас {cls!r}")
    if not mask:
        return ""
    mask36 = ""
    n = mask
    while n:
        mask36 = _B36[n % 36] + mask36
        n //= 36
    payload = "1" + mask36
    return "p" + payload + _check(payload)


def strip(branch: str) -> str:
    """Ім'я без кодового сегмента (чисте ім'я доставки)."""
    name, tail = _split_tail((branch or "").strip())
    if not tail or not name:
        return branch
    seg = name[-1].lower()
    if SEGMENT.match(seg) or (LEGACY.match(seg) and seg[0] == "1"):
        try:
            decode(branch)
        except BranchCodeError:
            pass                        # битий код теж зрізається: ім'я чистять
        name = name[:-1]
    return "-".join(name + tail)


def protected_of(branch: str) -> set:
    """Безпечна обгортка для гейтів: битий/чужий код → ВСЕ захищено."""
    try:
        return decode(branch)["protected"]
    except BranchCodeError:
        return set(DICT)
