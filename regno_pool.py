"""Спільний двигун пулів юридичних номерів (CNPJ для br-pt, UID для ch-de).

Один пул = один вид номера: свій файл стану, свій сід з репо, свій реєстр
видалених і свій реєстр призначень «вітка → номер». Логіка однакова для
всіх видів, тому живе тут; `cnpj_pool`/`uid_pool` — тонкі модулі, які дають
канонізацію, чексуму, сфери й імена файлів.

Файли стану ГЛОБАЛЬНІ (projects.state_root), не по-проєктні: вітки однієї
локалі живуть і в php-, і в vue-проєкті, а пул номерів у них один.
"""
from __future__ import annotations

import json
import re
import threading
import time
import zlib
from pathlib import Path
from typing import Callable

_LOCK = threading.RLock()


def _read_json(p: Path, default):
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v, type(default)) else default
    except Exception:
        return default


def _write_json(p: Path, v) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")


def _sphere_base(s: str) -> str:
    return (s or "").split("/")[0].strip().lower()


class Pool:
    """key — назва поля номера в записі («cnpj», «uid»); files — імена
    файлів стану; seed — функція, що повертає шлях до сіда (читається при
    кожному виклику, щоб тести могли його підмінити); errors — тексти
    ValueError для add() українською (letять людині в тост)."""

    def __init__(self, key: str, state_file: str, removed_file: str,
                 assign_file: str, seed: Callable[[], Path],
                 canonical: Callable[[str], str], valid: Callable[[str], bool],
                 spheres: list, errors: dict):
        self.key = key
        self.state_file, self.removed_file, self.assign_file = \
            state_file, removed_file, assign_file
        self.seed, self.canonical, self.valid = seed, canonical, valid
        self.spheres, self.errors = spheres, errors

    # ---------------------------------------------------------- файли
    def _root(self) -> Path:
        import projects
        return projects.state_root()

    def _load_removed(self) -> set:
        return set(_read_json(self._root() / self.removed_file, []))

    def _seed_rows(self) -> list[dict]:
        return [r for r in _read_json(self.seed(), []) if isinstance(r, dict)]

    def load(self) -> list[dict]:
        """Стан + нові сід-записи (видалене руками не воскресає)."""
        p = self._root() / self.state_file
        rows = _read_json(p, [])
        seed = self._seed_rows()
        if seed:
            have = {r.get(self.key) for r in rows} | self._load_removed()
            fresh = [r for r in seed if r.get(self.key) not in have]
            if fresh:
                with _LOCK:
                    rows = rows + fresh
                    _write_json(p, rows)
        return rows

    def _save(self, rows: list[dict]) -> None:
        _write_json(self._root() / self.state_file, rows)

    def _load_assign(self) -> dict:
        return _read_json(self._root() / self.assign_file, {})

    def _save_assign(self, d: dict) -> None:
        _write_json(self._root() / self.assign_file, d)

    def assignments(self) -> dict:
        """вітка -> номер (для таблиці в UI)."""
        return self._load_assign()

    # ---------------------------------------------------------- редагування
    def add(self, raw: str, note: str = "", company: str = "", city: str = "",
            sphere: str = "", addr: str = "") -> dict:
        num = self.canonical(raw)
        if not num:
            raise ValueError(self.errors["form"])
        if not self.valid(num):
            raise ValueError(self.errors["check"])
        with _LOCK:
            rows = self.load()
            if any(r.get(self.key) == num for r in rows):
                raise ValueError(self.errors["dup"])
            rows.append({self.key: num, "company": (company or "").strip(),
                         "city": (city or "").strip(),
                         "sphere": (sphere or "").strip(),
                         "addr": (addr or "").strip(),
                         "note": (note or "").strip(),
                         "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
            self._save(rows)
            return rows[-1]

    def remove(self, raw: str) -> bool:
        num = self.canonical(raw)
        with _LOCK:
            rows = self.load()
            kept = [r for r in rows if r.get(self.key) != num]
            if len(kept) == len(rows):
                return False
            self._save(kept)
            rem = self._load_removed()
            rem.add(num)
            _write_json(self._root() / self.removed_file, sorted(rem))
            # призначення на видалений номер скидаються: вітка при
            # наступному фіксі дістане новий номер, а не мертвий
            a = self._load_assign()
            kept_a = {b: c for b, c in a.items() if c != num}
            if kept_a != a:
                self._save_assign(kept_a)
            return True

    # ---------------------------------------------------------- вибір
    def sphere_for(self, text: str) -> str:
        """Сфера за видимим текстом вайта; '' — не вгадали."""
        low = (text or "").lower()
        for name, rx in self.spheres:
            if re.search(rx, low):
                return name
        return ""

    def pick(self, branch: str, site_text: str = "") -> str:
        """Номер для вітки: закріплюється в реєстрі призначень; '' — пул
        порожній.

        Унікальність ВАЖЛИВІША за сферу — однаковий номер на багатьох
        вайтах є слідом:
          1. вітка вже має призначення і номер ще в пулі — той самий номер
             (повторний фікс/прев'ю стабільні, нічого не «спалюється» двічі);
          2. кандидати — НАЙМЕНШ використані номери; сфера тематики вайта
             звужує вибір, лише поки її мінімум використань не гірший за
             загальний (сфера з одним номером не роздає його всім поспіль);
          3. з кандидатів — детерміновано за hash(вітки); вибір записується."""
        with _LOCK:
            rows = self.load()
            if not rows:
                return ""
            assign = self._load_assign()
            have = {r[self.key] for r in rows}
            cur = assign.get(branch or "")
            if cur in have:
                return cur
            used: dict = {}
            for c in assign.values():
                used[c] = used.get(c, 0) + 1
            min_all = min(used.get(r[self.key], 0) for r in rows)
            cands = [r for r in rows if used.get(r[self.key], 0) == min_all]
            sphere = self.sphere_for(site_text)
            if sphere:
                base = _sphere_base(sphere)
                in_sphere = [r for r in cands
                             if _sphere_base(r.get("sphere", "")) == base]
                if in_sphere:
                    cands = in_sphere
            i = zlib.crc32((branch or "x").encode("utf-8")) % len(cands)
            chosen = cands[i][self.key]
            assign[branch or ""] = chosen
            self._save_assign(assign)
            return chosen
