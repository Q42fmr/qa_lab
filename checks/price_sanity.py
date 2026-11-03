"""Ціни на вайті: очевидна дичина, яку видно без калькулятора (02.10).

Дві QA-скарги одного класу:
  * 868mewn67: «Цены выглядят ошибочными: "R$ 1,83" — подозрительно мало
    (ждём от 20)» — сервісний вайт з ціною за послугу менше за каву;
  * 868mg0ynk: «"CHF 3" и "CHF 1500" — похоже, потерян разделитель тысяч»
    — на одній сторінці ціни рознесені в сотні разів.

Детект-чек (без автофікса): відновити загублений розділювач чи «правильну»
ціну детерміновано не можна — цифри вигадувати заборонено, тож вердикт
«дивитись очима». Нулі («R$ 0,00») і відсотки не судяться.
"""
import re

NAME = "Ціни: підозріло малі / розкид у сотні разів"
GROUP = "tests"
PROJECTS = ["php", "node"]
DESCRIPTION = ("Ловить цінову дичину: ціна з валютою нижча за розумний "
               "мінімум локалі (R$ 1,83 за послугу) або розкид цін на "
               "одній сторінці у ≥200× (CHF 3 поруч із CHF 1'500 — "
               "загублений розділювач тисяч). Фікса немає: цифри "
               "вигадувати не можна, дивитись очима.")
FILES = ["*.html", "*.htm", "*.php", "*.vue"]

# символ/код валюти + число з будь-якими розділювачами ('.', ',', ''', NBSP)
PRICE_RX = re.compile(
    r"(?P<cur>R\$|US\$|S\$|MX\$|CHF|EUR|BRL|USD|GBP|€|£|\$)"
    r"\s*(?P<num>\d(?:[\d.,'’\u00a0\u202f ]{0,13}\d)?)\b")
# мінімальна «нормальна» ціна за валютою: нижче — привід подивитись очима
MIN_BY_CUR = {
    "R$": 20, "BRL": 20,
    "CHF": 5, "EUR": 3, "€": 3, "GBP": 3, "£": 3,
    "USD": 3, "US$": 3, "$": 3, "S$": 3, "MX$": 30,
}
SPREAD_FACTOR = 200       # max/min ≥ 200 на сторінці — підозра на розділювач
PCT_NEAR_RX = re.compile(r"%")
TAGS_RX = re.compile(r"<[^>]*>")
SCRIPT_RX = re.compile(r"<script\b[\s\S]*?</script>|<style\b[\s\S]*?</style>",
                       re.I)


def _to_value(num: str) -> float | None:
    """«1.500,00» → 1500.0; «1'500» → 1500.0; «1,83» → 1.83.
    Остання група з 1-2 цифр після , або . — десяткова; решта
    розділювачів — тисячні."""
    s = num.replace("\u00a0", "").replace("\u202f", "").replace(" ", "") \
           .replace("'", "").replace("’", "")
    if not s:
        return None
    m = re.match(r"^(\d[\d.,]*?)(?:([.,])(\d{1,2}))?$", s)
    if not m:
        return None
    head, _sep, frac = m.group(1), m.group(2), m.group(3)
    head = head.replace(".", "").replace(",", "")
    if not head.isdigit():
        return None
    try:
        return float(head) + (float(f"0.{frac}") if frac else 0.0)
    except ValueError:
        return None


def _is_page(path: str) -> bool:
    return path.lower().endswith((".html", ".htm", ".php", ".vue"))


# Розстрочка — не ціна: «ou em 9x de R$ 10,54 sem juros» (fuxjvik, 02.10:
# QA скаржився на «підозріло малі» 10,54/11,15, які є платежами від 94,90).
# Ловимо «Nx de» перед сумою і «sem juros»/«parcel»/«via Pix» одразу після.
_INSTALLMENT_BEFORE_RX = re.compile(
    r"(?:\b\d{1,2}\s*[xX]\s*(?:de\s*)?|parcel\w*\s*(?:de\s*)?)\s*$")
_INSTALLMENT_AFTER_RX = re.compile(
    r"^[^<{]{0,40}?(?:sem\s+juros|com\s+juros|parcel|via\s+Pix)", re.I)


def _prices(text: str):
    """[(позиція, валюта, показ, значення)] з видимого тексту сторінки."""
    visible = SCRIPT_RX.sub(" ", text)
    out = []
    for m in PRICE_RX.finditer(visible):
        tail = visible[m.end():m.end() + 3]
        if PCT_NEAR_RX.search(tail):
            continue                      # «R$ 5%» — не ціна
        if _INSTALLMENT_BEFORE_RX.search(visible, max(0, m.start() - 24),
                                         m.start()):
            continue                      # «9x de R$ 10,54» — платіж
        if _INSTALLMENT_AFTER_RX.search(visible[m.end():m.end() + 60]):
            continue                      # «R$ 90,16 via Pix» / «… sem juros»
        val = _to_value(m.group("num"))
        if val is None or val == 0:
            continue                      # нулі/сміття не судяться
        shown = f"{m.group('cur')} {m.group('num').strip()}"
        out.append((m.start(), m.group("cur"), shown, val))
    return out


def run_branch(files, all_paths, branch: str = ""):
    issues = []
    for path in sorted(files):
        if not _is_page(path):
            continue
        text = files[path]
        prices = _prices(text)
        if not prices:
            continue
        visible = SCRIPT_RX.sub(" ", text)
        low = [(pos, cur, shown, val) for pos, cur, shown, val in prices
               if val < MIN_BY_CUR.get(cur, 0)]
        for pos, cur, shown, val in low[:3]:
            issues.append({
                "path": path,
                "line": visible.count("\n", 0, pos) + 1,
                "severity": "warn",
                "message": (f"ціна виглядає помилковою: «{shown}» — "
                            f"підозріло мало (для {cur} чекаємо від "
                            f"{MIN_BY_CUR.get(cur)}); подивитись очима"),
            })
        vals = [v for *_x, v in prices]
        vmin, vmax = min(vals), max(vals)
        lo = next(p for p in prices if p[3] == vmin)
        hi = next(p for p in prices if p[3] == vmax)
        # мінімальна ціна мусить бути «людськи малою», інакше 10 проти
        # 2000 — легітимний прайс (дрібничка і великий пакет)
        lo_floor = MIN_BY_CUR.get(lo[1], 0)
        if (len(prices) >= 2 and vmin > 0 and vmax / vmin >= SPREAD_FACTOR
                and vmin < lo_floor * 5):
            issues.append({
                "path": path,
                "line": visible.count("\n", 0, lo[0]) + 1,
                "severity": "warn",
                "message": (f"розкид цін у {int(vmax / vmin)}×: «{lo[2]}» "
                            f"проти «{hi[2]}» на одній сторінці — схоже, "
                            f"десь загублений розділювач тисяч; подивитись "
                            f"очима"),
            })
    return issues
