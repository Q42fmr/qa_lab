"""Капча GravityForms: питання локалізоване, а прийняті відповіді — ні
(кейс QA 27.10, chobbiud-cotfaup-ch-fr).

Мігрована WordPress-форма лишає на сторінці французьке питання «Combien
font trois plus quatre ?» (поле input_2_9), а умовна логіка показу кнопки
«Nous écrire» (``window['gf_form_conditional_logic'][2]``) досі тримає
НІМЕЦЬКІ відповіді оригінального сайту: ``8``, ``acht``, ``Acht``. Цифра
не збігається з обчисленим "7" — кнопка відправки ніколи не з'являється,
QA бачить «после отправки не видно, что заявка ушла».

Чек парсить математичну капчу (видимий підпис gfield_label поля) мовою
сторінки (<html lang>), обчислює відповідь і звіряє з числовим правилом
``{"fieldId":"<N>","operator":"is","value":"<цифра>"}`` для цього поля.
Фікс переписує лише значення правил того самого поля: числове — на
цифру відповіді, рядкові — на слово-числівник мовою сторінки (нижній
регістр і з великої літери), порожнє ``value:""`` не чіпає.
"""
import re

NAME = "Капча: питання й прийняті відповіді різними мовами"
GROUP = "auto"
MODIFIES = set()
PROJECTS = ["php"]
DESCRIPTION = ("Математична капча GravityForms локалізована в тексті питання, "
               "але умовна логіка показу кнопки відправки (gf_form_conditional_logic) "
               "досі приймає відповіді мовою оригінального сайту — кнопка ніколи "
               "не з'являється. Фікс переписує значення правил цього поля на цифру, "
               "нижньорегістровий і капіталізований числівник мовою сторінки.")
FILES = ["*.html", "*.htm", "*.php"]

# ------------------------------------------------------------- числівники
NUMBERS = {
    "fr": ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept",
           "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze",
           "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf", "vingt"],
    "de": ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben",
           "acht", "neun", "zehn", "elf", "zwölf", "dreizehn", "vierzehn",
           "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn", "zwanzig"],
    "it": ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette",
           "otto", "nove", "dieci", "undici", "dodici", "tredici", "quattordici",
           "quindici", "sedici", "diciassette", "diciotto", "diciannove", "venti"],
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven",
           "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
           "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"],
    "pt": ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete",
           "oito", "nove", "dez", "onze", "doze", "treze", "catorze",
           "quinze", "dezasseis", "dezassete", "dezoito", "dezanove", "vinte"],
    "es": ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete",
           "ocho", "nueve", "diez", "once", "doce", "trece", "catorce",
           "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte"],
}
WORD_TO_NUM = {lang: {w.casefold(): i for i, w in enumerate(words)}
               for lang, words in NUMBERS.items()}

# (лексема операції регексу) -> функція
_OPS = {
    "plus": lambda a, b: a + b, "moins": lambda a, b: a - b, "fois": lambda a, b: a * b,
    "minus": lambda a, b: a - b, "mal": lambda a, b: a * b,
    "più": lambda a, b: a + b, "meno": lambda a, b: a - b, "per": lambda a, b: a * b,
    "times": lambda a, b: a * b,
    "mais": lambda a, b: a + b, "menos": lambda a, b: a - b, "vezes": lambda a, b: a * b,
    "más": lambda a, b: a + b, "por": lambda a, b: a * b,
}
_OPERAND = r"([\w-]+)"
QUESTIONS = {
    "fr": re.compile(rf"Combien\s+(?:font|fait)\s+{_OPERAND}\s+(plus|moins|fois)\s+{_OPERAND}", re.I),
    "de": re.compile(rf"(?:Wie\s+viel\s+ist|Was\s+ergibt)\s+{_OPERAND}\s+(plus|minus|mal)\s+{_OPERAND}", re.I),
    "it": re.compile(rf"Quanto\s+fa\s+{_OPERAND}\s+(più|meno|per)\s+{_OPERAND}", re.I),
    "en": re.compile(rf"What\s+is\s+{_OPERAND}\s+(plus|minus|times)\s+{_OPERAND}", re.I),
    "pt": re.compile(rf"Quanto\s+[ée]\s+{_OPERAND}\s+(mais|menos|vezes)\s+{_OPERAND}", re.I),
    "es": re.compile(rf"Cu[áa]nto\s+es\s+{_OPERAND}\s+(m[áa]s|menos|por)\s+{_OPERAND}", re.I),
}

_LANG_RX = re.compile(r'<html[^>]+\blang="([a-zA-Z-]{2,5})"', re.I)
_BRANCH_LOCALE_RX = re.compile(r"-([a-z]{2})-([a-z]{2})$")
_LABEL_RX = re.compile(
    r'for="input_(\d+)_(\d+)"[^>]*>\s*<span[^>]*>([^<]{3,160})</span>')


def _page_lang(text: str, branch: str) -> str:
    m = _LANG_RX.search(text)
    if m:
        lang = m.group(1).split("-")[0].lower()
        if lang in QUESTIONS:
            return lang
    m = _BRANCH_LOCALE_RX.search((branch or "").strip().lower())
    if m and m.group(2) in QUESTIONS:
        return m.group(2)
    return ""


def _operand(token: str, lang: str):
    if token.isdigit():
        return int(token)
    return WORD_TO_NUM[lang].get(token.casefold())


def _solve(question: str, lang: str):
    """(answer, digits, word_lower, word_cap) або None — питання не зрозуміле."""
    m = QUESTIONS[lang].search(question)
    if not m:
        return None
    a = _operand(m.group(1), lang)
    b = _operand(m.group(3), lang)
    op = m.group(2).lower()
    if a is None or b is None or op not in _OPS:
        return None
    answer = _OPS[op](a, b)
    words = NUMBERS[lang]
    if not (0 <= answer < len(words)):
        return None
    word_lower = words[answer]
    word_cap = word_lower[:1].upper() + word_lower[1:]
    return answer, str(answer), word_lower, word_cap


def _rule_rx(field_id: str) -> re.Pattern:
    return re.compile(
        r'\{"fieldId":"' + re.escape(field_id) +
        r'","operator":"is","value":"([^"]*)"\}')


def _fields(text: str, branch: str):
    """[(field_id, question, digits, word_lower, word_cap, label_start)]."""
    lang = _page_lang(text, branch)
    if not lang:
        return []
    out = []
    for m in _LABEL_RX.finditer(text):
        field_id, question = m.group(2), m.group(3).strip()
        solved = _solve(question, lang)
        if solved is None:
            continue
        _answer, digits, word_lower, word_cap = solved
        out.append((field_id, question, digits, word_lower, word_cap, m.start()))
    return out


def _mismatch(text: str, field_id: str, digits: str):
    """[(value, start, end)] правил поля; True якщо є цифрове, що різниться."""
    rules = [(mm.group(1), mm.start(), mm.end()) for mm in _rule_rx(field_id).finditer(text)]
    digit_vals = [v for v, _s, _e in rules if v.isdigit()]
    stale = any(v != digits for v in digit_vals)
    return rules, bool(digit_vals) and stale


def run(path, text):
    issues = []
    for field_id, question, digits, word_lower, word_cap, pos in _fields(text, ""):
        rules, stale = _mismatch(text, field_id, digits)
        if not stale:
            continue
        accepted = "/".join(v for v, _s, _e in rules if v)
        line = text.count("\n", 0, pos) + 1
        issues.append({
            "path": path, "line": line, "severity": "error",
            "message": (f'капча «{question}» = {digits}, а форма приймає лише '
                        f'{accepted} — кнопка відправки ніколи не з\'являється; '
                        f'фікс поставить {digits}/{word_lower}/{word_cap}'),
        })
    return issues


def _classify_repl(digits: str, word_lower: str, word_cap: str):
    def repl(mm: re.Match) -> str:
        value = mm.group(1)
        if value == "":
            new = value
        elif value.isdigit():
            new = digits
        elif value.isalpha() and value.islower():
            new = word_lower
        elif value.isalpha() and value[:1].isupper() and value[1:].islower():
            new = word_cap
        else:
            new = value
        return mm.group(0).replace(f'"value":"{value}"', f'"value":"{new}"')
    return repl


def fix(path, text):
    for field_id, _question, digits, word_lower, word_cap, _pos in _fields(text, ""):
        _rules, stale = _mismatch(text, field_id, digits)
        if not stale:
            continue
        text = _rule_rx(field_id).sub(_classify_repl(digits, word_lower, word_cap), text)
    return text
