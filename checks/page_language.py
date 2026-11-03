"""Мова тексту ↔ lang сторінки: текст має бути мовою з <html lang="...">.

Кейс: вайт з <html lang="pt-BR">, а контент сторінки — англійською
(шаблон не переклали). Ловимо це без зовнішніх API:

  * латинські мови (en/de/es/pt/fr/it/nl/pl) — рахунок стоп-слів: службові
    слова кожної мови надто частотні, щоб їх не було у справжньому тексті;
    спільні для es/pt («que», «para», «com/con») підвищують обидві мови
    однаково — вирок виносять слова-розрізнювачі («você», «usted», «und»);
  * th/ar/he/ru/uk — за письмом (частка символів відповідного скрипта).

Вирок консервативний: мінімум 40 слів видимого тексту, переможець мусить
мати ≥10 влучань і ≥3× відриву від заявленої мови — інакше мовчимо.

Далі шукаються неперекладені ФРАГМЕНТИ, і тут два різні за силою докази:
  * ЧУЖЕ ПИСЬМО (кирилиця/арабське/тайське/іврит на латинській сторінці) —
    доказ категоричний: досить ОДНОГО слова, це error. Саме так ловиться
    російський контент, який раніше був невидимий: <a class="btn">Записаться
    на обучение</a> на lang="pt" (STUDIO_br-*), а разом з ним — найпідступніший
    клас, ГОМОГЛІФИ: `info@alpinеjourneys.com` з кириличною `е` (U+0435) чи
    бренд `Сjubucil` з кириличною `С` виглядають нормально, але пошта на таку
    адресу не дійде. Поріг 2 слів їх пропускав, бо зіпсуте слово завжди одне.
    Гіпотезу «одне слово — може бути бренд» корпус спростував: із 22 таких
    знахідок на 7518 сторінках 21 виявилась дефектом, єдиний фолс — тайська
    назва бренду на th-вітці.
  * ТА САМА ПИСЕМНІСТЬ, інша мова (en на pt) — доказ статистичний, і трошки
    англійської у вайті нормально. Warn лишається тільки коли чужа мова
    ЗАЙМАЄ БІЛЬШУ ЧАСТИНУ сторінки (≥50% тексту і ≥25 слів). До цього порогу
    всі 67 таких спрацювань корпусу були одним і тим самим неперекладеним
    кукі-банером (21 слово, максимум 26% тексту) — це шум, не проблема.

Коментарі, <script> і <style> не аналізуються: чек про контент, а не про код,
тож російські службові коментарі тулінгу («// бьёт любой CSS») тут не спливають.
Сторінки без lang= пропускаються (це інша проблема, не цього чека).
Автофікса в чеку нема свідомо: текст не перекладеш регекспом, а міняти lang=
під текст — маскування бага. Переклад і заміна фрагментів — окрема панель
(модуль translate_text), яка бере ті самі фрагменти через foreign_runs().
"""
import functools
import html as _html
import re

NAME = "Мова тексту ↔ lang сторінки"
GROUP = "tests"    # звалідовано на 400 вітках (3781 сторінка): 102 error у
                   # 9 вітках — усі реальний кириличний контент на pt-сторінках;
                   # англійських варнів 0 (67 кукі-банерів пішли під поріг)
PROJECTS = ["php"]      # набір перевірок для vue-віток пишемо з нуля
DESCRIPTION = ("Видимий текст має бути мовою з <html lang=…>. Чуже письмо "
               "(кирилиця/арабське/тайське/іврит) — error від 2 слів; інша мова "
               "тією ж писемністю (en на pt) — warn лише якщо займає ≥50% "
               "тексту, бо трошки англійської допустимо. Коментарі й скрипти "
               "не чіпаються. Переклад — у панелі «Переклад».")
FILES = ["*.html", "*.htm", "*.php"]

LANG_RX = re.compile(r"""<html\b[^>]*\blang\s*=\s*["']([A-Za-z-]+)""", re.I)
STRIP_RX = re.compile(
    r"<(script|style|noscript|template|svg)\b.*?</\1\s*>|<head\b.*?</head\s*>"
    r"|<!--.*?-->|<\?(?:php)?.*?(?:\?>|$)", re.S | re.I)
TAG_RX = re.compile(r"<[^>]+>")
WORD_RX = re.compile(r"[^\W\d_]+", re.U)

# службові слова; en-колізії прибрані з інших мов (as/do/in/son…)
STOP = {
    "en": {"the", "and", "of", "to", "is", "are", "you", "that", "for",
           "with", "this", "have", "from", "your", "our", "not", "will",
           "can", "about", "more", "we", "all", "how", "what", "when"},
    "de": {"der", "die", "das", "und", "nicht", "mit", "für", "ist", "von",
           "auf", "dem", "den", "ein", "eine", "wir", "sie", "ihre", "werden",
           "oder", "bei", "aus", "nach", "über", "auch", "sind", "wird",
           "einen", "unsere", "durch", "können", "haben", "sich"},
    "es": {"el", "la", "los", "las", "que", "para", "con", "por", "una", "de",
           "como", "más", "pero", "sus", "nuestro", "nuestra", "usted",
           "también", "puede", "sobre", "entre", "desde", "hasta", "cuando",
           "esta", "este", "servicios", "nosotros", "aquí", "según", "cada"},
    "pt": {"não", "você", "uma", "para", "com", "por", "mais", "dos", "das",
           "seu", "sua", "nossa", "nosso", "são", "também", "pode", "sobre",
           "entre", "quando", "muito", "já", "ser", "foi", "é", "da", "em",
           "um", "os", "que", "como", "ou", "à", "ao", "pelo", "pela", "de"},
    "fr": {"le", "les", "des", "une", "pour", "avec", "par", "sur", "est",
           "sont", "vous", "nous", "votre", "nos", "dans", "qui", "que", "de",
           "pas", "plus", "cette", "leur", "être", "aux", "du", "au"},
    "it": {"il", "lo", "gli", "che", "per", "con", "una", "sono", "come",
           "più", "anche", "nel", "della", "delle", "degli", "questo",
           "questa", "loro", "essere", "sulla", "nostra", "nostro"},
    "nl": {"de", "het", "een", "van", "voor", "met", "dat", "zijn", "niet",
           "aan", "ook", "onze", "deze", "wordt", "worden", "bij", "naar",
           "uit", "wij", "hebben"},
    "pl": {"nie", "się", "jest", "na", "do", "że", "dla", "jak", "przez",
           "oraz", "które", "być", "tym", "jego", "ich", "przy", "nasze",
           "można", "aby"},
}

# мови, які визначаємо за письмом: діапазони юнікоду
SCRIPTS = {
    "th": [(0x0E00, 0x0E7F)],
    "ar": [(0x0600, 0x06FF), (0x0750, 0x077F)],
    "he": [(0x0590, 0x05FF)],
    "ru": [(0x0400, 0x04FF)],
    "uk": [(0x0400, 0x04FF)],
}

# письма, чужі для латинських мов: (назва, код ISO 15924, діапазони, мови,
# де це письмо СВОЄ). Раніше як чужі перевірялись лише th і ar, тому російський
# текст на pt-сторінці («Записаться на обучение» у STUDIO_br-*) не ловився.
FOREIGN_SCRIPTS = (
    ("кирилиця", "cyrl", [(0x0400, 0x04FF)],
     ("ru", "uk", "be", "bg", "sr", "mk", "kk")),
    ("арабське", "arab", [(0x0600, 0x06FF), (0x0750, 0x077F)],
     ("ar", "fa", "ur", "ps")),
    ("тайське", "thai", [(0x0E00, 0x0E7F)], ("th",)),
    ("іврит", "hebr", [(0x0590, 0x05FF)], ("he", "yi")),
)

MIN_WORDS = 40      # менше тексту — не беремося судити
MIN_HITS = 10       # мінімум влучань мови-переможця
MARGIN = 3          # переможець мусить мати ≥3× відриву від заявленої


def _visible_text(page: str) -> str:
    t = STRIP_RX.sub(" ", page)
    t = TAG_RX.sub(" ", t)
    return _html.unescape(t)


def _declared(page: str) -> str | None:
    m = LANG_RX.search(page)
    return m.group(1).split("-")[0].lower() if m else None


# Діапазони кодпоінтів -> символьний клас регексу. Раніше і `_script_ratio`, і
# `_script_words` перебирали КОЖЕН символ проти КОЖНОГО діапазону через
# `any(...)` на Python. На `mrmseev.ch` (426 файлів, 128 МБ html) це давало
# 4.8 млн викликів `any` і 53 с на одну вітку - третину всього прогону
# перевірок. Клас робить те саме в С, семантика не змінюється.
@functools.lru_cache(maxsize=None)
def _script_rx(ranges: tuple) -> re.Pattern:
    cls = "".join(f"\\U{a:08x}-\\U{b:08x}" for a, b in ranges)
    return re.compile(f"[{cls}]")


def _script_ratio(text: str, ranges) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    rx = _script_rx(tuple(map(tuple, ranges)))
    hit = len(rx.findall("".join(letters)))
    return hit / len(letters)


def _detect(words: list[str]):
    """(мова-переможець, влучання переможця, {мова: влучання})."""
    scores = {lang: 0 for lang in STOP}
    for w in words:
        for lang, stop in STOP.items():
            if w in stop:
                scores[lang] += 1
    best = max(scores, key=scores.get)
    return best, scores[best], scores


def run(path, text):
    declared = _declared(text)
    if not declared:
        return []
    line = text.count("\n", 0, LANG_RX.search(text).start()) + 1
    visible = _visible_text(text)
    words = [w.casefold() for w in WORD_RX.findall(visible)]
    if len(words) < MIN_WORDS:
        return []

    # мови з нелатинським письмом — за скриптом
    if declared in SCRIPTS:
        ratio = _script_ratio(visible, SCRIPTS[declared])
        if ratio < 0.2:
            best, hits, _ = _detect(words)
            guess = f", схоже на {best} ({hits} стоп-слів)" if hits >= MIN_HITS else ""
            return [{"line": line, "severity": "error",
                     "message": (f"lang=\"{declared}\", але лише {ratio:.0%} "
                                 f"літер відповідного письма — текст іншою "
                                 f"мовою{guess}")}]
        return []

    # латинська заявлена мова, а текст нелатинським письмом — усі письма,
    # не лише th/ar (інакше кирилиця на pt-сторінці лишалась невидимою)
    for sname, scode, ranges, natives in FOREIGN_SCRIPTS:
        if declared in natives:
            continue
        r = _script_ratio(visible, ranges)
        if r > 0.5:
            return [{"line": line, "severity": "error",
                     "message": (f"lang=\"{declared}\", а {r:.0%} літер — "
                                 f"{sname} письмо ({scode}) — мова не відповідає")}]

    if declared not in STOP:
        return []                       # незнайома мова — не судимо
    best, hits, scores = _detect(words)
    own = scores.get(declared, 0)
    if best != declared and hits >= MIN_HITS and hits >= MARGIN * (own + 1):
        return [{"line": line, "severity": "error",
                 "message": (f"текст схожий на «{best}» ({hits} стоп-слів "
                             f"проти {own} у «{declared}») — не відповідає "
                             f"lang=\"{declared}\"")}]

    # сторінка в цілому ок — шукаємо неперекладені ФРАГМЕНТИ (кукі-банер
    # англійською на pt-сторінці тощо): кожен текстовий ран між тегами
    return _foreign_fragments(text, declared)


FRAG_MIN_WORDS = 8      # коротші рани не судимо (навігація, бренд)
FRAG_MIN_HITS = 6       # впевненість у чужій мові
FRAG_MAX = 5            # більше на сторінку не сиплемо
# Чуже ПИСЬМО — доказ категоричний, а не статистичний, тож вистачає ОДНОГО
# слова: кирилиця на pt-сторінці не буває легітимною ні в якій кількості,
# тоді як два англійських слова цілком можуть бути назвою бренду. Поріг 2
# пропускав саме найтиповіший вигляд дефекту — одне чуже слово, вставлене
# в речення або в підпис кнопки: «Como proходит o aprendizado»,
# «Oixa заявку». На 694 сторінках корпусу зниження з 2 до 1 дало рівно
# одну нову знахідку, і та справжня — фолсів нуль.
FRAG_SCRIPT_MIN_WORDS = 1
# та сама писемність (en на pt) — «трошки можна»: варн лише коли чужий текст
# займає більшу частину сторінки. На корпусі всі 67 таких варнів були одним і
# тим самим неперекладеним кукі-банером (21 слово, максимум 26% тексту)
FRAG_DOMINANT_SHARE = 0.5
FRAG_DOMINANT_WORDS = 25


def _script_words(words: list[str], ranges) -> list[str]:
    rx = _script_rx(tuple(map(tuple, ranges)))
    return [w for w in words if rx.search(w)]


def foreign_runs(text: str, declared: str):
    """Текстові рани чужою мовою: {start, end, text, lang, kind, hits}.

    kind="script" — чуже письмо (вирок категоричний);
    kind="stopwords" — та сама писемність, інша мова (потребує домінування).
    Використовується і чеком, і панеллю перекладу — щоб «чужий фрагмент»
    означав одне й те саме в обох місцях.
    """
    # маска зберігає довжини і переноси — офсети/рядки лишаються чесними
    masked = STRIP_RX.sub(
        lambda m: "".join(c if c == "\n" else " " for c in m.group(0)), text)
    for m in re.finditer(r">([^<>]+)<", masked):
        raw = m.group(1)
        run_text = _html.unescape(raw)
        words = WORD_RX.findall(run_text)
        if not words:
            continue

        for sname, scode, ranges, natives in FOREIGN_SCRIPTS:
            if declared in natives:
                continue
            hit = _script_words(words, ranges)
            if len(hit) >= FRAG_SCRIPT_MIN_WORDS:
                yield {"start": m.start(1), "end": m.end(1), "text": run_text,
                       "lang": scode, "script_name": sname, "word": hit[0],
                       "kind": "script", "hits": len(hit)}
                break
        else:
            low = [w.casefold() for w in words]
            if len(low) < FRAG_MIN_WORDS:
                continue
            # для коротких ранів рахуємо РІЗНІ стоп-слова: одне «de»×6 — не доказ
            distinct = {lang: len(set(low) & stop) for lang, stop in STOP.items()}
            best = max(distinct, key=distinct.get)
            if (best == declared or distinct[best] < FRAG_MIN_HITS
                    or distinct.get(declared, 0)):
                continue                 # хоч одне слово своєї мови — мовчимо
            yield {"start": m.start(1), "end": m.end(1), "text": run_text,
                   "lang": best, "kind": "stopwords", "hits": distinct[best]}


def _quote(run_text: str, around: str = "") -> str:
    """Цитата рану. Для чужого письма центруємо на самому чужому слові:
    інакше в довгому рані видно лише його португальський початок, і спрацювання
    виглядає хибним (реальний кейс: «Oплата не онлайн» посеред pt-речення)."""
    frag = " ".join(run_text.split())
    if around and len(frag) > 80:
        i = frag.find(around)
        if i > 40:
            start = i - 30
            return f"«…{frag[start:start + 80]}{'…' if start + 80 < len(frag) else ''}»"
    return f"«{frag[:80]}{'…' if len(frag) > 80 else ''}»"


def _foreign_fragments(text: str, declared: str) -> list[dict]:
    runs = list(foreign_runs(text, declared))
    if not runs:
        return []
    total_words = len(WORD_RX.findall(_visible_text(text))) or 1

    issues = []
    same_script = [r for r in runs if r["kind"] == "stopwords"]
    foreign_words = sum(len(WORD_RX.findall(r["text"])) for r in same_script)
    dominant = (foreign_words >= FRAG_DOMINANT_WORDS
                and foreign_words / total_words >= FRAG_DOMINANT_SHARE)

    for r in runs:
        if r["kind"] == "stopwords" and not dominant:
            continue                     # трошки чужої мови — не проблема
        line = text.count("\n", 0, r["start"]) + 1
        if r["kind"] == "script":
            msg = (f"фрагмент чужим письмом ({r['script_name']}, {r['lang']}, "
                   f"{r['hits']} слів): {_quote(r['text'], r['word'])}")
            sev = "error"
        else:
            msg = (f"чужа мова займає {foreign_words / total_words:.0%} тексту "
                   f"(«{r['lang']}», {r['hits']} стоп-слів): {_quote(r['text'])}")
            sev = "warn"
        issues.append({"line": line, "severity": sev, "message": msg})
        if len(issues) >= FRAG_MAX:
            break
    return issues
