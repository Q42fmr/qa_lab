"""Пул реальних юрреквізитів по локалях (company_req.json).

Кейс 02.10 (mds-epidoc-it-it): у футері «ragione sociale da inserire ·
iscrizione al Registro delle imprese (REA) da inserire · Partita IVA da
inserire» — фіксам нема звідки взяти справжні значення. БД зібрана з
публічних legal/privacy сторінок самих компаній (назва+P.IVA+REA разом,
P.IVA звірені checksum-ом), джерело кожного запису — у полі `src`.

Вибір детермінований по вітці (zlib.crc32, як у geo_phone/cnpj): одна
вітка завжди отримує ті самі реквізити, сусідні — різні.
"""
from __future__ import annotations

import json
import re
import zlib
from pathlib import Path

_DB_FILE = Path(__file__).resolve().parent / "company_req.json"
_LOCALE_RX = re.compile(r"[-.]([a-z]{2}-[a-z]{2})(?:-\d+)?$")
_db_cache: dict | None = None


def _locale(branch: str) -> str:
    m = _LOCALE_RX.search((branch or "").strip().lower())
    return m.group(1) if m else ""


def rows(locale: str) -> list[dict]:
    global _db_cache
    if _db_cache is None:
        try:
            _db_cache = json.loads(_DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            _db_cache = {}
    got = _db_cache.get(locale)
    return [r for r in got if isinstance(r, dict) and r.get("piva")] \
        if isinstance(got, list) else []


def pick(branch: str) -> dict:
    """Запис {name, piva, rea, src} для вітки; {} — локаль без бази."""
    pool = rows(_locale(branch))
    if not pool:
        return {}
    return pool[zlib.crc32((branch or "x").encode("utf-8")) % len(pool)]


def piva_valid(piva: str) -> bool:
    """Checksum Partita IVA (11 цифр, контрольна — остання)."""
    if not re.fullmatch(r"\d{11}", piva or ""):
        return False
    s = 0
    for i, ch in enumerate(piva[:10]):
        d = int(ch)
        if i % 2 == 0:
            s += d
        else:
            s += d * 2 - 9 if d * 2 > 9 else d * 2
    return (10 - s % 10) % 10 == int(piva[10])
