"""Карта на вайті: адреса має реально геокодитись, інакше блок порожній.

Типовий блок: <div id="map"> + Leaflet, адреса з mapConfig.address
геокодиться через nominatim.openstreetmap.org на льоту. Якщо Nominatim
повертає [] — скрипт мовчки виходить і карта лишається ПОРОЖНІМ білим
блоком (класика: номер офісу «#17-21 DUO Tower» у рядку адреси — Nominatim
такого не знаходить).

Що ловимо:
  * адреса-плейсхолдер ({{...}}) або порожня;
  * адреса не геокодиться, але спрощений варіант (без #юніта) геокодиться —
    у повідомленні одразу підказка, що прибрати;
  * адреса не геокодиться взагалі;
  * є контейнер #map, але немає ініціалізації карти (L.map / iframe);
  * <iframe> карти з порожнім src або плейсхолдером.

Мережева (1 запит на унікальну адресу, пауза 1.1 с — політика Nominatim),
тому живе у групі «На перевірці», як і external_links.
"""
import re
import time

import requests

NAME = "Карта: адреса геокодиться"
GROUP = "review"
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"address", "map"}
PROJECTS = ["php"]
DESCRIPTION = ("Перевіряє, що адреса Leaflet-карти (address у mapConfig або const → "
               "Nominatim) реально геокодиться — інакше порожній білий блок; підказує "
               "спрощений варіант без №офісу/назви будівлі. Google-iframe карти "
               "перевіряються лише на порожній/плейсхолдер src (вони не ламаються від "
               "неточної адреси).")
FILES = ["*.html", "*.php", "*.vue"]

# і 'address: "..."' (ключ у mapConfig), і 'const address = "..."' (проста змінна)
ADDR_RX = re.compile(r"""\baddress\s*[:=]\s*["']([^"']*)["']""")
LEAFLET_RX = re.compile(r"\bL\.map\s*\(|nominatim\.openstreetmap\.org", re.I)
MAP_DIV_RX = re.compile(r"""<div\b[^>]*\bid\s*=\s*["']map["']""", re.I)
MAP_IFRAME_RX = re.compile(
    r"""<iframe\b[^>]*\bsrc\s*=\s*["']([^"']*)["'][^>]*>""", re.I)
MAP_HOST_RX = re.compile(r"google\.[a-z.]+/maps|maps\.google|openstreetmap\.org", re.I)
UA = {"User-Agent": "qa_lab-map-checker/1.0"}


def _geocode(addr: str) -> list | None:
    """Список результатів Nominatim або None, якщо сервіс недоступний."""
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"format": "json", "limit": 1, "q": addr},
                         headers=UA, timeout=12)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _simplify(addr: str) -> str:
    """Прибирає юніт-частини ('#17-21 DUO Tower', 'Unit 5', 'Suite 300') і
    сегменти-назви будівель ('Suntec Tower 5', 'Raffles City Tower') —
    Nominatim зазвичай знає лише вулицю+номер+місто/індекс."""
    parts = [p.strip() for p in addr.split(",")]
    kept = [p for p in parts
            if p and "#" not in p
            and not re.match(r"(?i)^(unit|suite|office|level|floor|apt)\b", p)
            and not re.search(r"(?i)\b(tower|building|centre|center|plaza|block|house)\b", p)]
    # якщо викинули все, крім одного сегмента — лишаємо хоча б перший+останній
    if len(kept) < 2 and len(parts) >= 2:
        kept = [parts[0], parts[-1]]
    return ", ".join(kept)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def run_branch(files):
    issues = []
    checked: dict[str, str | None] = {}   # адреса -> текст помилки (None = ок)

    for path, text in files.items():
        has_leaflet = bool(LEAFLET_RX.search(text))
        map_div = MAP_DIV_RX.search(text)

        # iframe-карти: порожній src або плейсхолдер
        has_map_iframe = False
        for m in MAP_IFRAME_RX.finditer(text):
            src = m.group(1).strip()
            if not MAP_HOST_RX.search(src) and src not in ("", "#"):
                continue
            has_map_iframe = MAP_HOST_RX.search(src) is not None
            if not src or src == "#" or "{{" in src:
                issues.append({"path": path, "line": _line_of(text, m.start()),
                               "severity": "error",
                               "message": f"iframe карти з порожнім/плейсхолдер src: '{src[:60]}'"})

        # контейнер є, а ініціалізації немає — карта не з'явиться
        if map_div and not has_leaflet and not has_map_iframe:
            issues.append({"path": path, "line": _line_of(text, map_div.start()),
                           "severity": "error",
                           "message": "є контейнер <div id=\"map\">, але немає ні "
                                      "L.map(...), ні iframe-карти — блок буде порожній"})

        if not has_leaflet:
            continue

        for m in ADDR_RX.finditer(text):
            addr = m.group(1).strip()
            line = _line_of(text, m.start())
            if not addr:
                issues.append({"path": path, "line": line, "severity": "error",
                               "message": "порожня адреса карти (mapConfig.address)"})
                continue
            if "{{" in addr:
                issues.append({"path": path, "line": line, "severity": "error",
                               "message": f"адреса карти — незаповнений плейсхолдер: '{addr}'"})
                continue

            if addr not in checked:               # 1 запит на унікальну адресу
                res = _geocode(addr)
                if res is None:
                    checked[addr] = "__net__"
                elif res:
                    checked[addr] = None          # геокодиться — ок
                else:
                    simple = _simplify(addr)
                    hint = ""
                    if simple and simple != addr:
                        time.sleep(1.1)           # політика Nominatim: ≤1 запит/с
                        res2 = _geocode(simple)
                        if res2:
                            hint = (f"; спрощений варіант знаходиться — прибери "
                                    f"юніт-частину, лиши: '{simple}'")
                    checked[addr] = (f"адреса не геокодиться (Nominatim → []), "
                                     f"карта буде порожнім блоком: '{addr}'{hint}")
                time.sleep(1.1)

            verdict = checked[addr]
            if verdict == "__net__":
                issues.append({"path": path, "line": line, "severity": "warn",
                               "message": f"не вдалося перевірити адресу (Nominatim "
                                          f"недоступний): '{addr[:70]}'"})
            elif verdict:
                issues.append({"path": path, "line": line, "severity": "error",
                               "message": verdict})
    return issues


def _branch_address(files: dict, branch: str) -> str:
    """Кандидат заміни: видима юридична адреса вітки, інакше гео-база
    локалі (той самий пул, що в address_number)."""
    try:
        import checks.address_number as an
        legal = an._legal_address(files)
        if legal:
            return legal
        return an._geo_pick(branch) or ""
    except Exception:
        return ""


def fix_branch(files, all_paths, branch: str = ""):
    """Лагодить адресу карти, з якою блок лишався б порожнім (02.10,
    868mg0ynk): плейсхолдер/порожня/негеокодована адреса замінюється на
    1) спрощений варіант без юніт-частини, якщо він геокодиться, інакше
    2) адресу вітки (юридична або гео-база), звірену Nominatim-ом.
    Nominatim недоступний — жодних дій: вгадувати адреси не можна."""
    cache: dict[str, bool | None] = {}

    def ok(addr: str):
        if addr not in cache:
            res = _geocode(addr)
            time.sleep(1.1)                  # політика Nominatim: ≤1 запит/с
            cache[addr] = bool(res) if res is not None else None
        return cache[addr]

    fallback: str | None = None              # ліниво: 1 добір на вітку
    actions = []
    for path in sorted(files):
        text = files[path]
        if not LEAFLET_RX.search(text):
            continue
        repls = []
        for m in ADDR_RX.finditer(text):
            addr = m.group(1).strip()
            bad = not addr or "{{" in addr
            if not bad:
                known = ok(addr)
                if known is None:
                    continue                 # мережі немає — не вгадуємо
                bad = not known
            if not bad:
                continue
            cand = ""
            if addr and "{{" not in addr:
                simple = _simplify(addr)
                if simple and simple != addr and ok(simple):
                    cand = simple
            if not cand:
                if fallback is None:
                    fb = _branch_address(files, branch)
                    fallback = fb if fb and ok(fb) else ""
                cand = fallback
            if cand and cand != addr:
                repls.append((m.start(1), m.end(1), cand))
        if not repls:
            continue
        new = text
        for s, e, cand in sorted(repls, key=lambda r: -r[0]):
            new = new[:s] + cand + new[e:]
        actions.append({"type": "edit", "path": path, "content": new})
    return actions
