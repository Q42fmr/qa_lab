"""Тріаж таски ClickUp: наш це клієнт чи ні, і що саме з ним робити.

Стоїть між вебхуком і роботою. Черга приймає `task_id` від кого завгодно, але
**чеки запускаються лише по тасках, які тріаж визначив ТОЧНО**. Усе, чого він
визначити не зміг, їде у «Проблеми» — видно людині, не оброблюється — і чекає
там на кнопку «Актуалізувати»: щойно хтось допише скіл, та сама таска може
поїхати в чергу без жодної нової події ClickUp.

Три рівні рішення, від найдешевшого до найдорожчого. Порядок не випадковий:
кожен наступний потрібен рівно для того, чого не вміє попередній.

1. **Поля таски.** `Safe Page`, «Тип вайта», статус, чекліст — це і є
   визначення «наш клієнт»: таска без віток не має до чого застосувати чек.
   Тут же відповідь для 100% звичайних deployment-тасок, і вона безкоштовна.
2. **Текст скарги, якщо він є.** Заміряно 04.09.2026: опис має **0 з 12**
   придатних тасок, а коментарі там — `cf ns done`, `fixed`. Тому текст
   вважається скаргою лише від `COMPLAINT_MIN` символів, і саме тому третій
   рівень майже ніколи не вмикається.
3. **Роутер мосту** (`ai_bridge.do_route`) — мапа імен, слова по скіл-картках
   і, якщо є ключ, модель. Він відповідає на два різні питання одразу: «чи є
   в лаби скіл під це» і «чи це взагалі не наша робота» (`ai_skills.NOT_OURS`
   — репутація домену, заборонена лексика, ціни).

Чотири вироки і що з ними робить черга:

    ours          → у чергу; `checks` = повний набір + те, що назвав роутер
    not_ours      → у «Проблеми» з поясненням ЧОМУ; чеки не ганяємо
    undetermined  → у «Проблеми»; це «не знаю», а не «не наше»
    skip          → тихо, лише лічильник (таска не наша за полями)

**`not_ours` і `undetermined` розділені навмисно.** Перше — це відповідь
(«домен у чорному списку, з гілки не лікується»), друге — її відсутність.
Злити їх в одне означало б, що кнопка «Актуалізувати» перебирає і те, для
чого нового скіла ніколи не буде.

**Каталог береться БЕЗ фільтра за типом проєкту.** Питання тріажу — «чи є в
лаби скіл під це взагалі», а вітки однієї таски можуть лежати і в php-, і в
node-репо. Звузити до активного проєкту означало б відповісти «не наше» на
скаргу, під яку скіл є, просто в іншому проєкті. Сам прогін фільтрує чеки за
проєктом і без нас (`runner.run_checks`).
"""
from __future__ import annotations

import hashlib
import os
import re
import time

import ai_bridge
import ai_router
import attribution
import ai_skills
import ai_skills_store
import clickup_client
import domains
import runner

OURS, NOT_OURS, UNDETERMINED, SKIP = "ours", "not_ours", "undetermined", "skip"
# Прохання саппорта про фікс — на ручний розбір QA (етап 1, задача 21.09.2026).
MANUAL = "manual"

# Скільки символів тексту вважаємо скаргою. Нижче порогу лежить не скарга, а
# службовий шум («fixed», «cf ns done»), і платити за нього моделлю нема за що.
COMPLAINT_MIN = 40


# Назва вітки в тексті — не скарга, а адреса роботи. Живий прогін 07.09:
# «Можешь пофиксить, пожалуйста: nwf-alvef-anp-papbcapd-br-pt …» дало
# `partner_banks` — роутер прочитав слово «partners» З НАЗВИ ВІТКИ. Тому перед
# роутингом вітки й домени з тексту прибираємо: вони в тасці вже є окремим
# полем, і другий раз як слова нам не потрібні.
_BRANCHY_RX = re.compile(r"\b[a-z0-9]+(?:-[a-z0-9]+){2,}\b", re.I)


def strip_targets(text: str, task: dict) -> str:
    """Текст без назв віток і доменів цієї таски."""
    out = text or ""
    for name in sorted((task.get("branches") or []) + (task.get("domains") or []),
                       key=len, reverse=True):
        if name:
            out = re.sub(re.escape(name), " ", out, flags=re.I)
    # і будь-що ще, що виглядає як slug вітки: у скаргах трапляються сусідні
    # вітки, яких у полі Safe Page цієї таски немає
    out = _BRANCHY_RX.sub(" ", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def complaint_text(task: dict) -> str:
    """Текст таски, який СХОЖИЙ на скаргу, або порожньо.

    Опис важить більше за коментар: коментарі в цьому воркспейсі майже завжди
    службові. Обрізаємо до 2000 символів — далі модель однаково читає перші
    абзаци, а ціна росте.

    Назви віток і доменів вирізаємо (`strip_targets`) — і поріг у 40 символів
    рахується ВЖЕ без них: «Можешь пофиксить: <п'ять віток>» це не скарга, а
    список цілей, і вважати його скаргою означає гнати роутер по чужих словах.
    """
    d = strip_targets((task.get("description") or "").strip(), task)
    if len(d) >= COMPLAINT_MIN:
        return d[:2000]
    last = task.get("last_comment")
    if isinstance(last, dict):
        last = last.get("text") or last.get("comment_text") or ""
    last = strip_targets((last or "").strip(), task)
    return last[:2000] if len(last) >= COMPLAINT_MIN else ""


# Коротка позначка «зроблено» в останньому коментарі. Не наш підпис, а те, що
# пише ЛЮДИНА: у цьому воркспейсі коментарі в тасках і є `fixed`, `cf ns done`
# (заміряно 04.09 на корпусі). Порівнюємо ЦІЛИЙ коментар, а не підрядок:
# «fixed» закриває таску, а «fixed логотип, но форма всё ещё не шлёт» — ні.
#
# ⚠️ `cf ns done` сюди НЕ входить, і це не недогляд: у цьому воркспейсі так
# позначають крок деплою (клоака й NS), а не зроблену роботу над вайтом.
# Таска з таким останнім коментарем — звичайна робоча, її треба брати.
DONE_WORDS = {"fixed", "fix", "fixed!", "done",
              "готово", "сделано", "исправлено", "пофиксил", "пофиксили",
              "пофикшено", "пофикшено автоматически",
              "виправлено", "полагоджено"}


def already_answered(task: dict) -> bool:
    """Чи в тасці вже стоїть відповідь «тут зроблено», після якої ніхто не
    сказав нічого нового.

    Відповідь — це один із двох коментарів, і обидва потрібні:

    * **наш підпис** («committed via qa_lab», його додає
      `attribution.sign_comment`) — і в автоматики, і в ручних кнопок
      «✔ чекліст + fixed» / «✔ fixed → @автор». Чекліст з 29.09.2026 ставить і
      автоматика, але свою роботу лаба все одно впізнає за підписом: чекліста
      whites у тасці може й не бути, а коментар є завжди;
    * **просто «fixed»** — так закриває таску людина, і це рівно та сама
      відповідь: робити тут більше нічого (вимога замовника 07.09).

    Дивимось від найновішого коментаря, ПРОПУСКАЮЧИ службові відмітки
    (`took to deploy`, `done, check`, лінк на пайплайн — `SERVICE_RX`).
    Відписану таску без чекліста whites поза вкладкою тримає лише коментар,
    і кожна така відмітка після нашого `fixed` повертала б її в авто-QA —
    лаба відписувала б `fixed` удруге й утретє. Будь-яке ІНШЕ нове слово — скарга, прохання, питання — таску
    повертає: людина пише ще раз саме тоді, коли перший фікс не допоміг.
    """
    comments = task.get("comments")
    if not isinstance(comments, list) or not comments:
        last = task.get("last_comment")
        comments = [last] if isinstance(last, dict) else []
    for c in comments:                  # ClickUp віддає найновіший першим
        if not isinstance(c, dict):
            continue
        if _is_closing(c, task):
            return True
        said = _bare(c, task)
        if said and not SERVICE_RX.search(said):
            return False
    return False


# ------------------------------------------------------------ етап 1: саппорт
# Правило колеги-QA від 21.09.2026: «Если нет коммента от саппорта, то QA
# проходится автоматически, по всем тестам. И заливается в гит фиксы. Если
# есть коммент — то фикс идет на ручное изменение к QA-шнику». Автоматичний
# розбір самих коментарів — «2 этап», поки що вимкнений (`route_comments`).
#
# «Коментар від саппорта» — НЕ будь-який коментар саппорта. Заміряно на
# корпусі 03.09 (190 тасок): переважно це кроки процесу — `took to deploy`
# (148), `took` (17), лінк на пайплайн (13), `took to redeploy` (8),
# `@… MB done, check` (50+), `tech pause` (5). Прохання про фікс — десь 20:
# «Можешь пофиксить, пожалуйста: …» (формат TSM), «@Nora Frontend не фикс»,
# «нужен фикс», «ждем фикса». Акаунти саппорту у воркспейсі звуться
# «Hugo Support», «Toby Support»…
SUPPORT_MARK = "support"
# Прохання — це те, що ЗВЕРНЕНЕ до фронта або має форму прохання. Живий прогін
# 21.09 показав, чому не навпаки («усе, що не службове»): «ленд на фиксе» від
# саппорта (лендинг у роботі в іншої команди) повернуло закриту таску як
# ручну, а службових формулювань у людей безліч. Формулювання прохань — з
# корпусу 03.09: «Можешь пофиксить, пожалуйста» (TSM), «фиксани плиз», «нужен
# фикс», «не фикс», «ждем фикса».
#
# 24.09.2026 додано скарги «після фіксу» («не помогло», «всё равно не
# работает», «окно куки не закрывается»). Відтоді, як вебхук не бере таски з
# уже наявним «fixed» (`fixed_is_last`), саме цей шаблон вирішує, чи таска
# повернеться до людини, — і стара версія мовчки губила б скаргу. Заміряно на
# корпусі 03.09: зі 59 змістовних коментарів саппорта старий шаблон ловив 42,
# доповнений — 49; усі 7 нових — справжні скарги, хибних нуль. «Ленд на
# фиксе» (див. вище) під жодну нову ознаку не підпадає.
REQUEST_RX = re.compile(
    r"пофикс|фиксан|нужен фикс|нужно пофикс|не фикс|жд[её]м фикс|исправ|поправ"
    r"|можешь|можете|fix (?:it|please)|please fix"
    r"|не помог|не помога|вс[её] ещ[её]|вс[её] равно|до сих пор|опять|снова"
    r"|не работа|не закрыва|не переход|не отображ"
    r"|не допомог|досі|все ще|знову|не працю", re.I)
FRONT_MARK = "frontend"
SERVICE_RX = re.compile(
    r"^(?:took|deploy ?\+ ?env|cf ?\+? ?ns done|(?:all )?done)\b"
    r"|\btook to (?:re)?deploy\b|\btech pause\b"
    r"|done,? *(?:pls |please )?check|\ball done\b", re.I)


def route_comments() -> bool:
    """Етап 2: розбирати текст коментаря ШІ-мостом (роутер, модель).
    Вимкнено, доки колега не скаже інакше — на етапі 1 таска з проханням
    саппорта йде людині, а не роутеру."""
    return os.getenv("CU_ROUTE_COMMENTS", "").strip() == "1"


def _bare(comment: dict, task: dict) -> str:
    """Текст коментаря без згадок, віток і доменів — те, що людина СКАЗАЛА."""
    text = (comment.get("text") or comment.get("comment_text") or "")
    # Лінки — першими і ЦІЛКОМ, з доменом і шляхом: ClickUp віддає їх і без
    # схеми, і від лінка на пайплайн лишався б шлях
    # (`/development/mass-deploy/-/pipelines/130997`) — службова відмітка
    # саппорта виглядала б проханням про фікс (13 таких на корпусі 03.09).
    text = re.sub(r"(?:https?://)?\b[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}(?:/\S*)?",
                  " ", text, flags=re.I)
    for name in sorted(comment.get("mentions") or [], key=len, reverse=True):
        text = text.replace("@" + name, " ")
    # Імʼя акаунта лаби з пробілом («@Tech Bot») — і тоді, коли тег прийшов
    # простим текстом, а не згадкою: інакше від нього лишалось би «Bot».
    me = clickup_client.lab_account()
    if me:
        text = re.sub("@" + re.escape(me), " ", text, flags=re.I)
    text = re.sub(r"@\S+", " ", text)
    text = strip_targets(text, task)
    return re.sub(r"\s+", " ", text).strip(" ,.:;!—-–")


def _is_closing(comment: dict, task: dict) -> bool:
    """«Тут уже зроблено»: наш підпис або людське `fixed` (можна з @тегом).

    Звіт лаби про зміну доменів — виняток: він відповідає лише на
    повідомлення «домени змінено» (`domain_change`), а не на таску. Інакше
    прохання саппорта, написане поруч із таким повідомленням, губилось би під
    звітом, а ще не пофікшена таска більше не йшла б у QA."""
    text = comment.get("text") or comment.get("comment_text") or ""
    if attribution.LAB.lower() in text.lower():
        return not _is_domain_report(comment)
    return _bare(comment, task).lower() in DONE_WORDS


def support_request(task: dict) -> dict | None:
    """Прохання саппорта про фікс, що прийшло ПІСЛЯ нашої останньої відповіді
    (або `fixed` людини). None — просити нема про що: таска йде в автоматичний
    QA. Коментарі ClickUp віддає найновішим першим.

    Прохання — коментар акаунта `… Support`, який після вирізання згадок,
    лінків, віток і доменів не є службовою відміткою і або звернений до фронта
    (`@… Frontend` чи сама лаба — `@Tech Bot`), або має форму прохання
    (`REQUEST_RX`)."""
    comments = task.get("comments")
    if not isinstance(comments, list):
        last = task.get("last_comment")
        comments = [last] if isinstance(last, dict) else []
    for c in comments:
        if not isinstance(c, dict):
            continue
        if _is_closing(c, task):
            return None
        if SUPPORT_MARK not in (c.get("user") or "").lower():
            continue
        # «Домени змінено» людині у вкладку не віддаємо: з тегом Tech Bot це
        # робота автоматики (`domain_change`), без нього — сповіщення тому,
        # кого тегнули, а не прохання. Людині лишається лише те, про що в
        # тому самому коментарі попросили ОКРІМ доменів.
        if ((domain_trigger(c, task) or domain_notice(c, task))
                and not _asks_more(c, task)):
            continue
        said = _bare(c, task)
        if not said or SERVICE_RX.search(said):
            continue
        raw = c.get("text") or c.get("comment_text") or ""
        to_front = (any(FRONT_MARK in (m or "").lower() for m in c.get("mentions") or [])
                    or re.search(r"@\S+ " + FRONT_MARK, raw, re.I)
                    # Tech Bot — теж фронт: до нього звертаються замість
                    # чергового, і звернення не про домени не має загубитись
                    or bot_tagged(c))
        if to_front or REQUEST_RX.search(said):
            return {"user": c.get("user") or "", "text": said}
    return None


def asks_again(task: dict) -> bool:
    """Таска з проставленим чеклістом whites, а саппорт після того просить знову.

    Чекліст ставить людина — у самому ClickUp або кнопкою «✔ чекліст + fixed»
    (автоматика лаби його не чіпає, з 23.09.2026). Гейт вкладки за чеклістом
    таску відсікає, тож без цього винятку таска з новим проханням не
    повернулась би НІКОЛИ. Повертається лише з проханням саппорта, тобто як
    ручна (етап 1)."""
    return bool(task.get("checklist_done")
                and clickup_client.passes_default_filters({**task, "checklist_done": False})
                and support_request(task))


def gate_ok(task: dict) -> bool:
    """Гейт вкладки — або повернення закритої таски з новим проханням."""
    return clickup_client.passes_default_filters(task) or asks_again(task)


# ------------------------------------------------ зміна доменів (25.09.2026)
# «@Liam Frontend Доменные зоны были изменены» — не прохання до людини, а
# подія: саппорт поміняв зони доменів таски (поле Required Domains), а пошти й
# самопосилання вайтів лишились на старих. 25.09 так прийшло сім тасок за
# годину, і всі вже були пофікшені. Лаба рахувала повідомлення проханням
# (звернене до `… Frontend`) і повертала таски у вкладку «ручним розбором», а
# в 26 з 30 їхніх віток пошти тим часом стояли на старих зонах
# (`info@banhekepa.buzz` при домені `banhekepa.digital`) — і о 13:43 пішли в
# деплой. На сусідній TECH-28368 те саме лагодили руками після скарги TSM
# «почта на чужом домене»: перепривʼязали домени й прогнали автофікс лаби.
# Задача Олександра того ж дня — щоб на таке повідомлення лаба робила це сама.
#
# Тригер — ТЕГ І ТЕКСТ разом (домовленість 25.09 з саппортом): коментар тегає
# `@Tech Bot` і каже ключову фразу «Доменные зоны были изменены»; постить її
# автоматизація саппорта. Лише тег («сугубо по тегу») — небезпечно: будь-яке
# звернення до бота запускало б коміти. Лише текст — теж ні: так сьогодні
# пишуть черговому фронту («@Liam Frontend …»), і тоді це його робота —
# ClickUp сповістить його сам.
#
# * Фраза може бути в будь-якому місці коментаря і в близьких формах
#   (`DOMAIN_NOTICE_RX`: «Домены были изменены», «Изменили доменные зоны»,
#   хвіст «на .lat»; вітки й домени поруч вирізає `_bare`). Ні «домены»
#   без дієслова, ні «почты на новые домены» тригером не є.
# * Автор — будь-хто, крім самої лаби: автоматизація саппорта може постити
#   від бот-акаунта (так `ClickBot` пише «cf ns done»).
# * Тег — справжня згадка або просто текст «@Tech Bot».
# * Фраза БЕЗ тегу Tech Bot — не тригер, але й не прохання: людині у вкладку
#   «Авто-QA» вона не йде (саме так 25.09 туди потрапили пофікшені таски).
# * Що в коментарі попросили ОКРІМ доменів («…изменены, поправь хедер»),
#   іде людині, як і раніше (`_asks_more`).
# * `@Tech Bot` без фрази — звернення до фронта, як `@… Frontend`: людині.
#
# ШІ тут не потрібен: фраза фіксована, збіг детермінований, а модель у
# гарячому шляху черги — правило, яке ми не порушуємо (див. CLAUDE.md, міст).
# Заміряно: живцем 25.09 — фраза в 7 з 7 повідомлень; корпус 03.09 (190
# тасок, 1146 коментарів) — жодного збігу і жодного тегу Tech Bot: крок у
# процесі саппорта з'явився лише зараз.
_ZONE = r"(?:доменн\w* )?(?:зон\w*|домен\w*)"
_PAST = r"(?:был[иао]?|були|було|уже|вже)"
_CHANGED = r"(?:измен|замен|поменя|смен|обнов|змін|замін|онов)\w*"
# «…изменены на .lat», «на .digital и .lat» — хвіст із самих зон
_TO_ZONES = r"(?: на \.?[a-z]{2,}(?:(?:, ?| и | і | та |/)\.?[a-z]{2,})*)?"
DOMAIN_NOTICE_RX = re.compile(
    rf"(?:{_ZONE}(?: {_PAST})? {_CHANGED}|{_CHANGED} {_ZONE}){_TO_ZONES}", re.I)
# Вирок тріажу для таски зі свіжою зміною доменів: лише чеки пошти й доменів.
DOMAINS = "domains"
# Перше слово звіту лаби в тасці. За ним звіт упізнається (`_is_domain_report`):
# відповідає він лише на повідомлення про домени, не на таску.
DOMAIN_REPORT_HEAD = "Смена доменов:"


def domain_hours() -> int:
    """Скільки годин повідомлення «домени змінено» лишається приводом діяти.

    Межа потрібна для першого ж запуску: без неї лаба пройшлась би по всіх
    колись змінених доменах і писала б звіти в давно задеплоєні таски.
    Повідомлення → деплой 25.09 розділяли ~50 хв, тож доба — із запасом на
    вимкнену ніч чи впалий вебхук."""
    try:
        return max(1, int(os.getenv("CU_DOMAIN_HOURS", "").strip() or 24))
    except ValueError:
        return 24


def fresh_ms(stamp, hours: int, now_ms: float | None = None) -> bool:
    """Чи мітка ClickUp (мс) молодша за `hours`. Без мітки — не свіжа:
    писати в таску, не знаючи, коли сталась подія, ми не будемо."""
    try:
        ms = int(str(stamp).strip())
    except (TypeError, ValueError):
        return False
    now = time.time() * 1000 if now_ms is None else now_ms
    # 10 хв наперед — на розбіжність годинників ClickUp і нашого
    return -600_000 <= now - ms <= hours * 3_600_000


def _is_domain_report(comment: dict) -> bool:
    """Звіт лаби про зміну доменів (наш підпис + перше слово звіту)."""
    low = (comment.get("text") or comment.get("comment_text") or "").lower()
    return attribution.LAB.lower() in low and DOMAIN_REPORT_HEAD.lower() in low


def domain_notice(comment: dict, task: dict) -> bool:
    """Коментар саппорта, який цілком є повідомленням «домени змінено» (з
    будь-яким тегом або без). Не тригер — лише «це не прохання людині»."""
    if SUPPORT_MARK not in (comment.get("user") or "").lower():
        return False
    return bool(DOMAIN_NOTICE_RX.fullmatch(_bare(comment, task)))


def bot_tagged(comment: dict) -> bool:
    """У коментарі тегнуто акаунт лаби (`@Tech Bot`) — згадкою або текстом."""
    me = clickup_client.lab_account().strip().lower()
    if not me:
        return False
    if any((m or "").strip().lower() == me for m in comment.get("mentions") or []):
        return True
    raw = comment.get("text") or comment.get("comment_text") or ""
    return bool(re.search(r"@" + re.escape(me) + r"(?!\w)", raw, re.I))


def moved_domains(task: dict) -> list[dict]:
    """Вітки, у яких домен таски вже НЕ той, під який лаба востаннє їх
    лагодила: `[{branch, old, new}]`.

    «Під який лагодила» — реєстр `domains.json`: домен туди пише імпорт із
    вкладки ClickUp і прогін черги. 25.09 у всіх шести тасках там стояли старі
    зони (`banhekepa.buzz`), а в тасці — нові (`banhekepa.digital`). Вітки,
    яких лаба ще не бачила, сюди не потрапляють: порівнювати нема з чим."""
    doms = task.get("domains") or []
    out = []
    for i, br in enumerate(task.get("branches") or []):
        new = (doms[i] if i < len(doms) else "").strip().lower()
        old = (domains.bound_anywhere(br) or "").lower()
        if new and old and new != old:
            out.append({"branch": br, "old": old, "new": new})
    return out


def domain_trigger(comment: dict, task: dict) -> str:
    """`tag` — коментар тегає `@Tech Bot` і каже «Доменные зоны были
    изменены»; інакше порожньо. Автор — будь-хто, крім самої лаби."""
    me = clickup_client.lab_account().strip().lower()
    if not me or (comment.get("user") or "").strip().lower() == me:
        return ""
    if bot_tagged(comment) and DOMAIN_NOTICE_RX.search(_bare(comment, task)):
        return "tag"
    return ""


def _asks_more(comment: dict, task: dict) -> bool:
    """Чи просить коментар про щось ОКРІМ доменів: без фрази «домени
    змінено» в ньому лишається форма прохання («…, поправь хедер»)."""
    return bool(REQUEST_RX.search(DOMAIN_NOTICE_RX.sub(" ", _bare(comment, task))))


def domain_change(task: dict, *, hours: int | None = None,
                  now_ms: float | None = None) -> dict | None:
    """Свіжий привід для фіксу доменів (`domain_trigger`), на який ще ніхто не
    відповів, або None.

    Відповідь — наш звіт про домени, наш підпис на будь-чому іншому або
    людське «fixed»: після TECH-28368, де людина пройшлась автофіксом сама,
    лаба вдруге не піде. Коментарі мусять бути дочитані — інакше відповіді не
    видно, і рішення «діяти» було б здогадкою.

    `moved` — вітки, де домен таски змінився проти реєстру (старий → новий):
    потрібні звіту, і рахуються ДО прогону, бо прогін привʼязує нові."""
    comments = task.get("comments")
    if not isinstance(comments, list):
        return None
    for c in comments:                  # ClickUp віддає найновіший першим
        if not isinstance(c, dict):
            continue
        if _is_closing(c, task) or _is_domain_report(c):
            return None
        via = domain_trigger(c, task)
        if via:
            if not fresh_ms(c.get("date"), hours or domain_hours(), now_ms):
                return None
            return {"user": c.get("user") or "", "user_id": c.get("user_id"),
                    "text": _bare(c, task), "date": str(c.get("date") or ""),
                    "via": via, "moved": moved_domains(task)}
    return None


# ------------------------------------------------------ «fixed» уже є (24.09)
# Одне визначення на дві речі, і тому воно тут, а не в `cu_fixed`:
#   * ручна робота бачить попередження, що таску вже відписали (`cu_fixed`);
#   * вебхук і опит таких тасок не беруть узагалі — рішення юзера 24.09:
#     «логічно, що вебхук взагалі не має грузити задачі з вже наявним fixed».
# `already_answered` для цього замало: там будь-яке нове слово повертає
# таску. Заміряно на корпусі 03.09 (190 тасок): «fixed» є в 178, після
# останнього «fixed» писали в 159 — але 87 з них це «апрув, дякую» / «все
# гуд, забрал» від медіабаєрів, 69 — конфіг деплою, і лише 2 — справжнє
# прохання саппорта. Автоматика ганяла б ці 156 тасок наново і відписувала б
# `fixed` удруге.
_SIG = f"committed via {attribution.LAB}".lower()
# Скільки «fixed» однієї таски віддаємо в UI — для підказки більше не треба.
MARKS_MAX = 10


def fixed_by(comment: dict, task: dict) -> str:
    """Хто відписав цей «fixed», або "" — якщо коментар не «fixed».

    Словник — той самий `DONE_WORDS`, що в `_is_closing`. Два види, і обидва
    — «fixed користувача»:
    * через лабу: «fixed — committed via qa_lab by Liam», зокрема
      «@Tech Bot fixed — …» з кнопки «✔ fixed → @автор». Людину беремо з
      підпису: автор у ClickUp тут завжди сервісний акаунт;
    * руками в ClickUp: «fixed», «@Liam fixed», «готово» — автор коментаря.
    Сам підпис лаби ще НЕ «fixed»: звіт ШІ-моста («Лаба перевірила — дефекту
    немає») теж підписаний, але фіксом не є.
    """
    text = comment.get("text") or comment.get("comment_text") or ""
    i = text.lower().find(_SIG)
    if i >= 0:
        body = text[:i].rstrip(" \t\r\n—–-")
        tail = text[i + len(_SIG):].strip()
        who = tail[3:].strip() if tail.lower().startswith("by ") else attribution.LAB
    else:
        body, who = text, (comment.get("user") or "").strip()
    if not body:
        return ""
    said = _bare({**comment, "text": body}, task).lower()
    return (who or "?") if said in DONE_WORDS else ""


def fixed_note(task: dict) -> dict | None:
    """Усе про «fixed» у тасці, або None — якщо їх немає чи коментарі не
    дочитані.

    `count`, `by`, `date` — скільки «fixed» і хто/коли написав ОСТАННІЙ;
    `asked_again` — прохання саппорта, що прийшло ПІСЛЯ нього;
    `marks` — усі «fixed», найновіший першим (ClickUp так і віддає).
    """
    comments = task.get("comments")
    if not isinstance(comments, list):
        return None
    marks, newest = [], None
    for idx, c in enumerate(comments):
        if not isinstance(c, dict):
            continue
        who = fixed_by(c, task)
        if not who:
            continue
        if newest is None:
            newest = idx
        marks.append({"by": who, "date": str(c.get("date") or "")})
    if not marks:
        return None
    # Лише коментарі, НОВІШІ за останній «fixed». Порожній список, а не None:
    # на None `support_request` підставив би останній коментар таски.
    req = support_request({**task, "comments": comments[:newest]})
    return {"count": len(marks), "by": marks[0]["by"], "date": marks[0]["date"],
            "asked_again": ({"user": req["user"], "text": req["text"][:160]}
                            if req else None),
            "marks": marks[:MARKS_MAX]}


def fixed_is_last(task: dict) -> bool:
    """«Fixed» у тасці є, і після нього саппорт нічого нового не просив —
    таку таску вже зробили, і вебхук її не бере.

    Прохання саппорта після «fixed» — єдиний виняток, і він з ТЗ колеги-QA
    від 21.09: таска з галкою чекліста інакше не повернулась би в лабу
    НІКОЛИ (вкладка ClickUp її ховає, див. `asks_again`). Повертається вона
    лише людині — див. `classify`."""
    note = fixed_note(task)
    return bool(note and not note["asked_again"])


def decision_text(task: dict) -> str:
    """Текст, від якого залежить вирок, — ключ кешу тріажу в черзі. На етапі 1
    це прохання саппорта; на етапі 2 — скарга для роутера."""
    if route_comments():
        return complaint_text(task)
    req = support_request(task)
    return f"{req['user']}: {req['text']}" if req else ""


def text_hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:12]


def catalog() -> list[dict]:
    """Скіл-картки всіх живих чеків — без фільтра за проєктом (див. модуль)."""
    return ai_skills.catalog(runner.load_checks(), "", ai_skills_store.all_skills())


def skills_fingerprint() -> str:
    """Відбиток набору активних скілів.

    Потрібен кнопці «Актуалізувати»: він відповідає на питання «чи змінилось
    щось із того часу, як ми сказали «не знаю»». Без нього перебір помилкових
    тасок або платив би моделлю щоразу, або не помічав би нового скіла.
    """
    ids = sorted(c["id"] for c in catalog() if c.get("enriched"))
    return hashlib.sha1(",".join(ids).encode("utf-8")).hexdigest()[:12]


def classify(task: dict, *, use_model: bool = True) -> dict:
    """Вирок по одній тасці. Мережу смикає лише через роутер, і лише коли є
    текст скарги.

    Повертає: `{verdict, checks, reason, router, confidence, text_hash,
    skills_fp}`. `checks` — те, що роутер назвав ПОНАД повний набір; вирішує,
    що з цим робити, викликач.
    """
    out = {"verdict": SKIP, "checks": [], "reason": "", "router": "",
           "confidence": 0.0, "text_hash": "", "skills_fp": skills_fingerprint()}

    if not gate_ok(task):
        out["reason"] = "не проходить фільтри вкладки"
        return out

    if already_answered(task):
        out["reason"] = "лаба вже відповіла в цій тасці, нового після того не було"
        return out

    fixed = fixed_note(task)
    if fixed and not fixed["asked_again"]:
        out["reason"] = "у тасці вже є fixed, нового прохання після нього немає"
        return out

    # Таска з уже наявним «fixed» сюди доходить лише з проханням саппорта
    # після нього — і йде ТІЛЬКИ людині, навіть коли колись увімкнуть етап 2:
    # автоматичний QA з автокомітом поставив би в неї ще один «fixed».
    if not route_comments() or fixed:
        req = support_request(task)
        out["text_hash"] = text_hash(decision_text(task))
        if req:
            out.update(verdict=MANUAL, router="support", confidence=1.0,
                       reason=f"прохання саппорта — на ручний розбір QA: «{req['text'][:160]}»")
            return out
        out.update(verdict=OURS, router="fields", confidence=1.0,
                   reason="прохань саппорта про фікс немає — повний автоматичний QA")
        return out

    text = complaint_text(task)
    out["text_hash"] = text_hash(text)
    if not text:
        # Звичайна deployment-таска: вітки є, тип вайта є, скарги немає.
        # Процедура для неї відома без жодної моделі — повний прогін.
        out.update(verdict=OURS, router="fields", confidence=1.0,
                   reason="звичайна таска вайтів: вітки і тип вайта на місці")
        return out

    ok, why = ai_router.available()
    routing = ai_bridge.do_route(text, "", use_model=use_model and ok)
    out["router"] = routing.get("router", "")
    out["confidence"] = float(routing.get("confidence") or 0.0)

    if routing.get("tool_failure"):
        out.update(verdict=NOT_OURS,
                   reason=routing.get("reason") or "збій чужого прогону")
        return out

    named = ai_bridge.scope_checks(routing)
    if named:
        out.update(verdict=OURS, checks=named,
                   reason="скарга розібрана: " + ", ".join(named[:5]))
        return out

    # Чеків не назвали. Далі важливо не злити «не наше» з «не знаю».
    not_ours = routing.get("not_ours") or []
    if not_ours or routing.get("model_says_not_ours"):
        out.update(verdict=NOT_OURS,
                   reason=("; ".join(w.get("чому", "") for w in not_ours)
                           or routing.get("reason") or "лаба тут безсила"))
        return out

    out.update(verdict=UNDETERMINED,
               reason=("не вдалось визначити, що робити зі скаргою"
                       + ("" if ok else f" ({why})")))
    return out
