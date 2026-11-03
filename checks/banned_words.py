"""Бан-слова QA Whites: те, чим QA судить текст вайта, — до того, як осудить.

Джерело даних: «Бан-слова QA Whites 10.09.2026 (1).xlsx» — знімок движка QA
(modules/qa/vendor/qa_runner/checks/banned.py) від 10.09.2026. Колонка
«Шаблон в коде» — python-регекси движка, запечені сюди без переписування;
генерація лише додає: пробіли -> \\s+ (маска дає подвійні пробіли на місці
тегів), « ?» -> \\s*, межі слова (?<!\\w)…(?!\\w) (легенда: bet != between,
porn != Waraporn), арабським словам — опційні префікси و ب ل ف ك і артикль
ال. Патерни з lookbehind (clinic-правило) не трансформуються; «-bet-» живе
без меж — його межі і є дефіси.

Два яруси, як у QA:
  * RED (error)   — «красное», знахідка ВАЛИТЬ домен, тема не рятує;
  * YELLOW (warn) — «жёлтое, глянуть глазами», не валить.

Жовте знімається двома речами (червоне — нічим):
  * заперечення у <=24 символах перед словом («not guaranteed»,
    «не гарантированный доход», «sin garantía»);
  * профільна тема вітки (вкладка «Исключения по теме»): тема визначається
    з <title> + meta description головної сторінки; тема не впізнана —
    виключення не застосовуються.

Зона пошуку:
  * html/htm/php — ВИДИМИЙ текст: script/style/noscript/template/svg,
    коментарі і php-блоки затерті пробілами, нутрощі тегів теж, лишаються
    значення текст-атрибутів title/alt/placeholder/aria-label/content.
    Довжина і \\n збережені, тому line у репорті точний, а fix править
    оригінал за тими самими оффсетами;
  * vue/js/mjs/ts/jsx/tsx/json/xml/txt — сирий текст: у vue-вайтів контент
    живе в коді. package.json / package-lock.json пропускаються.

Особливі випадки движка (вкладка «Не ловится намеренно») сидять у самих
шаблонах: голі bet/cbd/nude/bullet/explosive/gun ловляться лише в
небезпечних сполуках (bet365, cbd oil, nudes, gun shop…). «puta» мовчить на
сторінках lang="hr" (хорватською це «раз/шляхи», не лайка).

Автофікс (fix_branch бачить ту саму маску, що і run_branch):
  * червоне: заміна з REPLACEMENTS, без запису у словнику — видалення
    входження з чисткою пробілів і пунктуації;
  * жовте: ТІЛЬКИ заміна з REPLACEMENTS (видалення «bitcoin» з «we accept
    bitcoin» калічить текст сильніше за жовту підсвітку) — решта warn
    лишається людині.
Заміна зберігає велику літеру (Guaranteed -> Reliable). Повторний фікс —
no-op: заміни не входять у бан-списки.
"""
import re

NAME = "Бан-слова QA Whites"
GROUP = "tests"    # смоук на кеші прода (3 вітки): 2 спрацювання, обидва —
# branch-code (branch_code.py): класи клієнтських даних, які цей
# чек МОЖЕ переписати — захищена вітка вимикає його цілком
MODIFIES = {"legal"}
                   # X-маска телефону у placeholder (+41 XX XXX XX XX), QA
                   # судить так само. У "auto" — після валідації на великому
                   # кеші qa_lab. ~1 c/вітку (235 патернів по видимій масці)
DESCRIPTION = ("Список бан-слів QA Whites (знімок движка 10.09.2026): червоні "
               "валять домен (error), жовті — «глянуть глазами» (warn). Жовте "
               "знімають заперечення поруч і профільна тема вітки. Автофікс: "
               "червоне міняє зі словника або видаляє, жовте — тільки міняє.")
FILES = ["*.html", "*.htm", "*.php", "*.vue", "*.js", "*.mjs", "*.ts",
         "*.jsx", "*.tsx", "*.json", "*.xml", "*.txt"]

# --- дані: згенеровано з книги «Бан-слова QA Whites 10.09.2026 (1).xlsx
# (вкладки «Запрещено (красное)» і «Рисковое (жёлтое)», колонка «Шаблон в
# коде» — регекси движка). Формат: (патерн, слово/форма з книги, категорія).
# Оновлення списку = перегенерувати ці два блоки з нового знімка книги.
RED = (
    ('(?<!\\w)(?:cannabis)(?!\\w)', 'cannabis', 'наркотики'),
    ('(?<!\\w)(?:marijuana)(?!\\w)', 'marijuana', 'наркотики'),
    ('(?<!\\w)(?:marihuana)(?!\\w)', 'marihuana', 'наркотики'),
    ('(?<!\\w)(?:hashish)(?!\\w)', 'hashish', 'наркотики'),
    ('(?<!\\w)(?:weed)(?!\\w)', 'weed', 'наркотики'),
    ('(?<!\\w)(?:cocaine)(?!\\w)', 'cocaine', 'наркотики'),
    ('(?<!\\w)(?:heroin)(?!\\w)', 'heroin', 'наркотики'),
    ('(?<!\\w)(?:meth)(?!\\w)', 'meth', 'наркотики'),
    ('(?<!\\w)(?:methamphetamine)(?!\\w)', 'methamphetamine', 'наркотики'),
    ('(?<!\\w)(?:amphetamine)(?!\\w)', 'amphetamine', 'наркотики'),
    ('(?<!\\w)(?:lsd)(?!\\w)', 'lsd', 'наркотики'),
    ('(?<!\\w)(?:mdma)(?!\\w)', 'mdma', 'наркотики'),
    ('(?<!\\w)(?:ecstasy)(?!\\w)', 'ecstasy', 'наркотики'),
    ('(?<!\\w)(?:opium)(?!\\w)', 'opium', 'наркотики'),
    ('(?<!\\w)(?:opioids?)(?!\\w)', 'opioid(s)', 'наркотики'),
    ('(?<!\\w)(?:mephedrone)(?!\\w)', 'mephedrone', 'наркотики'),
    ('(?<!\\w)(?:psychedelic)(?!\\w)', 'psychedelic', 'наркотики'),
    ('(?<!\\w)(?:narcotics?)(?!\\w)', 'narcotic(s)', 'наркотики'),
    ('(?<!\\w)(?:drugs?)(?!\\w)', 'drug(s)', 'наркотики'),
    ('(?<!\\w)(?:thc)(?!\\w)', 'thc', 'наркотики'),
    ('(?<!\\w)(?:cbd\\s+oil)(?!\\w)', 'cbd oil', 'наркотики'),
    ('(?<!\\w)(?:cbd\\s+gummies)(?!\\w)', 'cbd gummies', 'наркотики'),
    ('(?<!\\w)(?:наркотик\\w*)(?!\\w)', 'наркотик…', 'наркотики'),
    ('(?<!\\w)(?:конопл\\w*)(?!\\w)', 'конопл…', 'наркотики'),
    ('(?<!\\w)(?:марихуан\\w*)(?!\\w)', 'марихуан…', 'наркотики'),
    ('(?<!\\w)(?:каннабис)(?!\\w)', 'каннабис', 'наркотики'),
    ('(?<!\\w)(?:гашиш)(?!\\w)', 'гашиш', 'наркотики'),
    ('(?<!\\w)(?:кокаин\\w*)(?!\\w)', 'кокаин…', 'наркотики'),
    ('(?<!\\w)(?:героин\\w*)(?!\\w)', 'героин…', 'наркотики'),
    ('(?<!\\w)(?:амфетамин\\w*)(?!\\w)', 'амфетамин…', 'наркотики'),
    ('(?<!\\w)(?:метамфетамин\\w*)(?!\\w)', 'метамфетамин…', 'наркотики'),
    ('(?<!\\w)(?:мефедрон\\w*)(?!\\w)', 'мефедрон…', 'наркотики'),
    ('(?<!\\w)(?:экстази)(?!\\w)', 'экстази', 'наркотики'),
    ('(?<!\\w)(?:спайс)(?!\\w)', 'спайс', 'наркотики'),
    ('(?<!\\w)(?:опиум)(?!\\w)', 'опиум', 'наркотики'),
    ('(?<!\\w)(?:психодел\\w*)(?!\\w)', 'психодел…', 'наркотики'),
    ('(?<!\\w)(?:cocaína)(?!\\w)', 'cocaína', 'наркотики'),
    ('(?<!\\w)(?:cocaina)(?!\\w)', 'cocaina', 'наркотики'),
    ('(?<!\\w)(?:heroína)(?!\\w)', 'heroína', 'наркотики'),
    ('(?<!\\w)(?:drogas?)(?!\\w)', 'droga(s)', 'наркотики'),
    ('(?<!\\w)(?:drogen)(?!\\w)', 'drogen', 'наркотики'),
    ('(?<!\\w)(?:kokain)(?!\\w)', 'kokain', 'наркотики'),
    ('(?<!\\w)(?:drogue)(?!\\w)', 'drogue', 'наркотики'),
    ('(?<!\\w)(?:stupéfiant\\w*)(?!\\w)', 'stupéfiant…', 'наркотики'),
    ('(?<!\\w)(?:cocaïne)(?!\\w)', 'cocaïne', 'наркотики'),
    ('(?<!\\w)(?:héroïne)(?!\\w)', 'héroïne', 'наркотики'),
    ('(?<!\\w)(?:haschisch)(?!\\w)', 'haschisch', 'наркотики'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:مخدرات))(?!\\w)', 'مخدرات', 'наркотики'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:مخدر))(?!\\w)', 'مخدر', 'наркотики'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:حشيش))(?!\\w)', 'حشيش', 'наркотики'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:كوكايين))(?!\\w)', 'كوكايين', 'наркотики'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:هيروين))(?!\\w)', 'هيروين', 'наркотики'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:ماريجوانا))(?!\\w)', 'ماريجوانا', 'наркотики'),
    ('(?<!\\w)(?:steroids?)(?!\\w)', 'steroid(s)', 'допинг / рецептурка'),
    ('(?<!\\w)(?:testosterone)(?!\\w)', 'testosterone', 'допинг / рецептурка'),
    ('(?<!\\w)(?:\\bhgh\\b)(?!\\w)', 'hgh', 'допинг / рецептурка'),
    ('(?<!\\w)(?:modafinil)(?!\\w)', 'modafinil', 'допинг / рецептурка'),
    ('(?<!\\w)(?:nootropics?)(?!\\w)', 'nootropic(s)', 'допинг / рецептурка'),
    ('(?<!\\w)(?:anabolic)(?!\\w)', 'anabolic', 'допинг / рецептурка'),
    ('(?<!\\w)(?:стероид\\w*)(?!\\w)', 'стероид…', 'допинг / рецептурка'),
    ('(?<!\\w)(?:тестостерон)(?!\\w)', 'тестостерон', 'допинг / рецептурка'),
    ('(?<!\\w)(?:допинг)(?!\\w)', 'допинг', 'допинг / рецептурка'),
    ('(?<!\\w)(?:porn)(?!\\w)', 'porn', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:pornograph\\w*)(?!\\w)', 'pornograph…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:xxx)(?!\\w)', 'xxx', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:hentai)(?!\\w)', 'hentai', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:camgirl)(?!\\w)', 'camgirl', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:onlyfans)(?!\\w)', 'onlyfans', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:escorts?)(?!\\w)', 'escort(s)', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:brothel)(?!\\w)', 'brothel', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:prostitut\\w*)(?!\\w)', 'prostitut…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:\\bnudes\\b)(?!\\w)', 'nudes', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:nude\\s+(?:photos?|pics?|models?|girls?))(?!\\w)', 'nude photo(s) / pic(s) / model(s) / girl(s)', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:strip\\s*club)(?!\\w)', 'strip club / stripclub', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:fetish)(?!\\w)', 'fetish', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:erotic\\w*)(?!\\w)', 'erotic…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:sensual)(?!\\w)', 'sensual', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:порно\\w*)(?!\\w)', 'порно…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:порнограф\\w*)(?!\\w)', 'порнограф…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:секс-услуг\\w*)(?!\\w)', 'секс-услуг…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:проститу\\w*)(?!\\w)', 'проститу…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:эскорт)(?!\\w)', 'эскорт', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:интим-услуг\\w*)(?!\\w)', 'интим-услуг…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:вебкам\\w*)(?!\\w)', 'вебкам…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:эроти\\w*)(?!\\w)', 'эроти…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:pornograf\\w*)(?!\\w)', 'pornograf…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:porno)(?!\\w)', 'porno', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:prostituci\\w*)(?!\\w)', 'prostituci…', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:prostituição)(?!\\w)', 'prostituição', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:prostituzione)(?!\\w)', 'prostituzione', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:putas?)(?!\\w)', 'puta(s)', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:إباحية))(?!\\w)', 'إباحية', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:إباحي))(?!\\w)', 'إباحي', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:دعارة))(?!\\w)', 'دعارة', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:عاهرة))(?!\\w)', 'عاهرة', 'порнография / секс-услуги'),
    ('(?<!\\w)(?:bet-?\\d{2,})(?!\\w)', 'bet + цифры', 'азартные игры'),
    ('(?<!\\w)(?:\\d{1,4}-?bet\\b)(?!\\w)', 'цифры + bet', 'азартные игры'),
    ('(?:-bet-)', '«-bet-» внутри имени домена', 'азартные игры'),
    ('(?<!\\w)(?:casino)(?!\\w)', 'casino', 'азартные игры'),
    ('(?<!\\w)(?:казино)(?!\\w)', 'казино', 'азартные игры'),
    ('(?<!\\w)(?:poker)(?!\\w)', 'poker', 'азартные игры'),
    ('(?<!\\w)(?:покер)(?!\\w)', 'покер', 'азартные игры'),
    ('(?<!\\w)(?:betting)(?!\\w)', 'betting', 'азартные игры'),
    ('(?<!\\w)(?:bookmaker)(?!\\w)', 'bookmaker', 'азартные игры'),
    ('(?<!\\w)(?:букмекер\\w*)(?!\\w)', 'букмекер…', 'азартные игры'),
    ('(?<!\\w)(?:ставки\\s+на\\s+спорт)(?!\\w)', 'ставки на спорт', 'азартные игры'),
    ('(?<!\\w)(?:gambling)(?!\\w)', 'gambling', 'азартные игры'),
    ('(?<!\\w)(?:jackpot)(?!\\w)', 'jackpot', 'азартные игры'),
    ('(?<!\\w)(?:джекпот)(?!\\w)', 'джекпот', 'азартные игры'),
    ('(?<!\\w)(?:lotter(?:y|ie|ia))(?!\\w)', 'lottery / lotterie / lotteria', 'азартные игры'),
    ('(?<!\\w)(?:lotto\\s*spiel\\w*)(?!\\w)', 'lotto spiel… / lottospiel…', 'азартные игры'),
    ('(?<!\\w)(?:online\\s*lotto)(?!\\w)', 'online lotto / onlinelotto', 'азартные игры'),
    ('(?<!\\w)(?:лотере\\w*)(?!\\w)', 'лотере…', 'азартные игры'),
    ('(?<!\\w)(?:sportsbook)(?!\\w)', 'sportsbook', 'азартные игры'),
    ('(?<!\\w)(?:blackjack)(?!\\w)', 'blackjack', 'азартные игры'),
    ('(?<!\\w)(?:roulettes?)(?!\\w)', 'roulette(s)', 'азартные игры'),
    ('(?<!\\w)(?:рулетк\\w*)(?!\\w)', 'рулетк…', 'азартные игры'),
    ('(?<!\\w)(?:азартн\\w*\\s+игр\\w*)(?!\\w)', 'азартн… игр…', 'азартные игры'),
    ('(?<!\\w)(?:apuestas)(?!\\w)', 'apuestas', 'азартные игры'),
    ('(?<!\\w)(?:casas?\\s+de\\s+apuestas)(?!\\w)', 'casa(s) de apuestas', 'азартные игры'),
    ('(?<!\\w)(?:paris\\s+sportifs)(?!\\w)', 'paris sportifs', 'азартные игры'),
    ('(?<!\\w)(?:cassinos?)(?!\\w)', 'cassino(s)', 'азартные игры'),
    ('(?<!\\w)(?:casinos)(?!\\w)', 'casinos', 'азартные игры'),
    ('(?<!\\w)(?:apostas?\\s+esportivas?)(?!\\w)', 'aposta(s) esportiva(s)', 'азартные игры'),
    ('(?<!\\w)(?:casas?\\s+de\\s+apostas)(?!\\w)', 'casa(s) de apostas', 'азартные игры'),
    ('(?<!\\w)(?:jackpots)(?!\\w)', 'jackpots', 'азартные игры'),
    ('(?<!\\w)(?:sportsbooks)(?!\\w)', 'sportsbooks', 'азартные игры'),
    ('(?<!\\w)(?:bookmakers)(?!\\w)', 'bookmakers', 'азартные игры'),
    ('(?<!\\w)(?:sportwetten)(?!\\w)', 'sportwetten', 'азартные игры'),
    ('(?<!\\w)(?:wettanbieter)(?!\\w)', 'wettanbieter', 'азартные игры'),
    ('(?<!\\w)(?:wettbüros?)(?!\\w)', 'wettbüro(s)', 'азартные игры'),
    ('(?<!\\w)(?:wettbueros?)(?!\\w)', 'wettbuero(s)', 'азартные игры'),
    ('(?<!\\w)(?:wettquoten)(?!\\w)', 'wettquoten', 'азартные игры'),
    ('(?<!\\w)(?:live-?wetten)(?!\\w)', 'live-wetten / livewetten', 'азартные игры'),
    ('(?<!\\w)(?:online-?wetten)(?!\\w)', 'online-wetten / onlinewetten', 'азартные игры'),
    ('(?<!\\w)(?:buchmacher)(?!\\w)', 'buchmacher', 'азартные игры'),
    ('(?<!\\w)(?:scommesse)(?!\\w)', 'scommesse', 'азартные игры'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:مراهنات))(?!\\w)', 'مراهنات', 'азартные игры'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:كازينو))(?!\\w)', 'كازينو', 'азартные игры'),
    ('(?<!\\w)(?:(?:ال|[وبلفك](?:ال)?)?(?:قمار))(?!\\w)', 'قمار', 'азартные игры'),
    ('(?<!\\w)(?:slot\\s+machines?)(?!\\w)', 'slot machine(s)', 'азартные игры'),
    ('(?<!\\w)(?:игровы\\w*\\s+автомат\\w*)(?!\\w)', 'игровы… автомат…', 'азартные игры'),
    ('(?<!\\w)(?:слот-?машин\\w*)(?!\\w)', 'слот-машин… / слотмашин…', 'азартные игры'),
    ('(?<!\\w)(?:tragamonedas)(?!\\w)', 'tragamonedas', 'азартные игры'),
    ('(?<!\\w)(?:spielautomat\\w*)(?!\\w)', 'spielautomat…', 'азартные игры'),
    ('(?<!\\w)(?:machines?\\s+à\\s+sous)(?!\\w)', 'machine(s) à sous', 'азартные игры'),
    ('(?<!\\w)(?:firearms?)(?!\\w)', 'firearm(s)', 'оружие / насилие'),
    ('(?<!\\w)(?:rifles?)(?!\\w)', 'rifle(s)', 'оружие / насилие'),
    ('(?<!\\w)(?:ammunition)(?!\\w)', 'ammunition', 'оружие / насилие'),
    ('(?<!\\w)(?:\\bammo\\b)(?!\\w)', 'ammo', 'оружие / насилие'),
    ('(?<!\\w)(?:muniç(?:ão|ões))(?!\\w)', 'munição / munições', 'оружие / насилие'),
    ('(?<!\\w)(?:munición)(?!\\w)', 'munición', 'оружие / насилие'),
    ('(?<!\\w)(?:\\bexplosives\\b)(?!\\w)', 'explosives', 'оружие / насилие'),
    ('(?<!\\w)(?:explosive\\s+devices?)(?!\\w)', 'explosive device(s)', 'оружие / насилие'),
    ('(?<!\\w)(?:\\bbombs?\\b)(?!\\w)', 'bomb(s)', 'оружие / насилие'),
    ('(?<!\\w)(?:terrorism)(?!\\w)', 'terrorism', 'оружие / насилие'),
    ('(?<!\\w)(?:terrorist\\w*)(?!\\w)', 'terrorist…', 'оружие / насилие'),
    ('(?<!\\w)(?:\\bnazi\\b)(?!\\w)', 'nazi', 'оружие / насилие'),
    ('(?<!\\w)(?:jihad)(?!\\w)', 'jihad', 'оружие / насилие'),
    ('(?<!\\w)(?:продажа\\s+оружия)(?!\\w)', 'продажа оружия', 'оружие / насилие'),
    ('(?<!\\w)(?:купить\\s+оружие)(?!\\w)', 'купить оружие', 'оружие / насилие'),
    ('(?<!\\w)(?:огнестрел\\w*)(?!\\w)', 'огнестрел…', 'оружие / насилие'),
    ('(?<!\\w)(?:взрывчат\\w*)(?!\\w)', 'взрывчат…', 'оружие / насилие'),
    ('(?<!\\w)(?:оружие)(?!\\w)', 'оружие', 'оружие / насилие'),
    ('(?<!\\w)(?:боеприпас\\w*)(?!\\w)', 'боеприпас…', 'оружие / насилие'),
    ('(?<!\\w)(?:терроризм)(?!\\w)', 'терроризм', 'оружие / насилие'),
    ('(?<!\\w)(?:экстремизм)(?!\\w)', 'экстремизм', 'оружие / насилие'),
    ('(?<!\\w)(?:gun\\s*shop)(?!\\w)', 'gun shop / gunshop', 'оружие / насилие'),
    ('(?<!\\w)(?:buy\\s+(?:a\\s+)?gun)(?!\\w)', 'buy gun / buy a gun', 'оружие / насилие'),
    ('(?<!\\w)(?:assault\\s+rifle)(?!\\w)', 'assault rifle', 'оружие / насилие'),
    ('(?<!\\w)(?:hate\\s+speech)(?!\\w)', 'hate speech', 'оружие / насилие'),
    ('(?<!\\w)(?:vape)(?!\\w)', 'vape', 'табак / алкоголь'),
    ('(?<!\\w)(?:vaping)(?!\\w)', 'vaping', 'табак / алкоголь'),
    ('(?<!\\w)(?:shisha)(?!\\w)', 'shisha', 'табак / алкоголь'),
    ('(?<!\\w)(?:hookah)(?!\\w)', 'hookah', 'табак / алкоголь'),
    ('(?<!\\w)(?:\\bnicotine\\b)(?!\\w)', 'nicotine', 'табак / алкоголь'),
    ('(?<!\\w)(?:cigars?)(?!\\w)', 'cigar(s)', 'табак / алкоголь'),
    ('(?<!\\w)(?:cigarettes?)(?!\\w)', 'cigarette(s)', 'табак / алкоголь'),
    ('(?<!\\w)(?:вейп\\w*)(?!\\w)', 'вейп…', 'табак / алкоголь'),
    ('(?<!\\w)(?:кальян\\w*)(?!\\w)', 'кальян…', 'табак / алкоголь'),
    ('(?<!\\w)(?:никотин)(?!\\w)', 'никотин', 'табак / алкоголь'),
    ('(?<!\\w)(?:сигарет\\w*)(?!\\w)', 'сигарет…', 'табак / алкоголь'),
    ('(?<!\\w)(?:vodka)(?!\\w)', 'vodka', 'табак / алкоголь'),
    ('(?<!\\w)(?:водка)(?!\\w)', 'водка', 'табак / алкоголь'),
)

YELLOW = (
    ('(?<!\\w)(?:crypto\\w*)(?!\\w)', 'crypto…', 'крипто / финансы'),
    ('(?<!\\w)(?:bitcoin)(?!\\w)', 'bitcoin', 'крипто / финансы'),
    ('(?<!\\w)(?:binance)(?!\\w)', 'binance', 'крипто / финансы'),
    ('(?<!\\w)(?:\\bdefi\\b)(?!\\w)', 'defi', 'крипто / финансы'),
    ('(?<!\\w)(?:\\bnft\\b)(?!\\w)', 'nft', 'крипто / финансы'),
    ('(?<!\\w)(?:forex)(?!\\w)', 'forex', 'крипто / финансы'),
    ('(?<!\\w)(?:binary\\s+options?)(?!\\w)', 'binary option(s)', 'крипто / финансы'),
    ('(?<!\\w)(?:arbitrage)(?!\\w)', 'arbitrage', 'крипто / финансы'),
    ('(?<!\\w)(?:hedge\\s*fund)(?!\\w)', 'hedge fund / hedgefund', 'крипто / финансы'),
    ('(?<!\\w)(?:trading\\s+signals?)(?!\\w)', 'trading signal(s)', 'крипто / финансы'),
    ('(?<!\\w)(?:payout)(?!\\w)', 'payout', 'крипто / финансы'),
    ('(?<!\\w)(?:криптовалют\\w*)(?!\\w)', 'криптовалют…', 'крипто / финансы'),
    ('(?<!\\w)(?:биткоин\\w*)(?!\\w)', 'биткоин…', 'крипто / финансы'),
    ('(?<!\\w)(?:форекс)(?!\\w)', 'форекс', 'крипто / финансы'),
    ('(?<!\\w)(?:трейдинг)(?!\\w)', 'трейдинг', 'крипто / финансы'),
    ('(?<!\\w)(?:\\bpharma\\b)(?!\\w)', 'pharma', 'медицина / фарма'),
    ('(?<!\\w)(?:pharmac(?!ist)\\w*)(?!\\w)', 'pharmac…', 'медицина / фарма'),
    ('(?<!\\w)(?:(?:\\b(?:medic|dental|(?<!financial )(?<!business )(?<!company )(?<!corporate )(?<!cash flow )health|doctor|patient|treat|aesthetic|veterinar|derma|surg|therap)\\w*.{0,40}?\\bclinics?\\b|\\bclinics?\\b.{0,40}?\\b(?:medic|dental|(?<!financial )(?<!business )(?<!company )(?<!corporate )(?<!cash flow )health|doctor|patient|treat|aesthetic|veterinar|derma|surg|therap)\\w*))(?!\\w)', 'clinic(s)', 'медицина / фарма'),
    ('(?<!\\w)(?:\\bclinical(?=\\s+(?:trial|study|studies|proof|evidence|treatment|therapy|care|practice|setting)))(?!\\w)', 'clinical + trial / study / studies / proof / evidence / treatment / therapy / care / practice / setting', 'медицина / фарма'),
    ('(?<!\\w)(?:\\bclinically\\b)(?!\\w)', 'clinically', 'медицина / фарма'),
    ('(?<!\\w)(?:surgery)(?!\\w)', 'surgery', 'медицина / фарма'),
    ('(?<!\\w)(?:rehab\\b)(?!\\w)', 'rehab', 'медицина / фарма'),
    ('(?<!\\w)(?:weightloss)(?!\\w)', 'weightloss', 'медицина / фарма'),
    ('(?<!\\w)(?:weight\\s+loss)(?!\\w)', 'weight loss', 'медицина / фарма'),
    ('(?<!\\w)(?:fat\\s*burn\\w*)(?!\\w)', 'fat burn… / fatburn…', 'медицина / фарма'),
    ('(?<!\\w)(?:cure-?all)(?!\\w)', 'cure-all / cureall', 'медицина / фарма'),
    ('(?<!\\w)(?:\\bhgh\\b)(?!\\w)', 'hgh', 'медицина / фарма'),
    ('(?<!\\w)(?:фарм\\w*)(?!\\w)', 'фарм…', 'медицина / фарма'),
    ('(?<!\\w)(?:клиник\\w*)(?!\\w)', 'клиник…', 'медицина / фарма'),
    ('(?<!\\w)(?:похудени\\w*)(?!\\w)', 'похудени…', 'медицина / фарма'),
    ('(?<!\\w)(?:\\bbeer\\b)(?!\\w)', 'beer', 'алкоголь'),
    ('(?<!\\w)(?:\\bwine\\b)(?!\\w)', 'wine', 'алкоголь'),
    ('(?<!\\w)(?:\\bwines\\b)(?!\\w)', 'wines', 'алкоголь'),
    ('(?<!\\w)(?:\\bwinery\\b)(?!\\w)', 'winery', 'алкоголь'),
    ('(?<!\\w)(?:\\bпиво\\b)(?!\\w)', 'пиво', 'алкоголь'),
    ('(?<!\\w)(?:\\bвино\\b)(?!\\w)', 'вино', 'алкоголь'),
    ('(?<!\\w)(?:earn\\s*fast)(?!\\w)', 'earn fast / earnfast', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:get\\s*rich)(?!\\w)', 'get rich / getrich', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:guaranteed)(?!\\w)', 'guaranteed', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:money\\s*back)(?!\\w)', 'money back / moneyback', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:\\bmiracle\\b)(?!\\w)', 'miracle', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:no\\s*effort)(?!\\w)', 'no effort / noeffort', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:passive\\s+income)(?!\\w)', 'passive income', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:free\\s*cash)(?!\\w)', 'free cash / freecash', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:sure\\s*win)(?!\\w)', 'sure win / surewin', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:risk\\s*free)(?!\\w)', 'risk free / riskfree', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:100%\\s+guaranteed)(?!\\w)', '100% guaranteed', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:instant\\s+profit)(?!\\w)', 'instant profit', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:гарантированн\\w*\\s+доход)(?!\\w)', 'гарантированн… доход', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:пассивн\\w*\\s+доход)(?!\\w)', 'пассивн… доход', 'маркетинг-хайп / скам'),
    ('(?<!\\w)(?:быстр\\w*\\s+заработ\\w*)(?!\\w)', 'быстр… заработ…', 'маркетинг-хайп / скам'),
)

# Чим міняє автофікс. Ключ — «слово/форма» як у RED/YELLOW вище. Червоне без
# запису тут видаляється; жовте без запису лишається людині. Поповнюється
# руками — це продуктове рішення, не код.
REPLACEMENTS = {
    "guaranteed": "reliable",
    "100% guaranteed": "reliable",
    "miracle": "remarkable",
    "earn fast / earnfast": "earn steadily",
    "get rich / getrich": "build savings",
    "money back / moneyback": "refund",
    "no effort / noeffort": "minimal effort",
    "passive income": "steady income",
    "free cash / freecash": "extra funds",
    "sure win / surewin": "strong result",
    "risk free / riskfree": "low-risk",
    "instant profit": "real results",
    "гарантированн… доход": "стабильный доход",
    "пассивн… доход": "дополнительный доход",
    "быстр… заработ…": "стабильный заработок",
}

# «Исключения по теме»: жовта категорія -> теми, де вона не ризик (1:1 з
# вкладки). Ключі категорій — як у колонці «Категорія» YELLOW.
THEME_EXEMPT = {
    "алкоголь": {"медиа_студия_новости", "недвижимость_дома", "пансионаты",
                 "питание", "путешествия", "семья_быт"},
    "медицина / фарма": {"здоровье", "клиника", "медицина", "пансионаты",
                         "питание", "семья_быт"},
    "крипто / финансы": {"банк", "бизнес", "букмекерские_конторы",
                         "документация", "инвестиции", "крипто",
                         "образование", "семейное_право", "финансы",
                         "юриспруденция"},
}

# Ключові слова тем у <title>/description (підстрока, без регістру).
# Мови вайтів: pt/es/en/de/fr/it.
THEMES = {
    "питание": ("restaurant", "ristorante", "gastronom", "culinar", "cozinha",
                "cocina", "cuisine", "küche", "kueche", "catering", "padaria",
                "bakery", "pizzer", "café", "cafeteria", "food"),
    "недвижимость_дома": ("imóve", "imove", "imobili", "inmobili", "immobili",
                          "real estate", "propert", "wohnung", "apartament",
                          "apartment", "nekretnin"),
    "пансионаты": ("senioren", "sênior", "senior resid", "retirement",
                   "nursing", "repouso", "geriatr", "pflegeheim", "asilo",
                   "residencia de mayores"),
    "путешествия": ("travel", "viagem", "viaje", "voyage", "reise", "turis",
                    "tourism", "excurs", "férias", "vacacion", "urlaub"),
    "медиа_студия_новости": ("notícia", "noticia", "news", "jornal", "revista",
                             "magazine", "studio", "estúdio", "estudio",
                             "produtora", "editora", "blog", "fotograf",
                             "photograph", "media"),
    "семья_быт": ("família", "familia", "family", "famille", "familie",
                  "doméstic", "domestic", "hogar", "household", "limpeza",
                  "cleaning", "reinigung"),
    "здоровье": ("saúde", "saude", "salud", "health", "santé", "gesundheit",
                 "salute", "wellness", "bem-estar", "bienestar"),
    "клиника": ("clínica", "clinica", "clinic", "klinik", "clinique"),
    "медицина": ("medicin", "médic", "medic", "dental", "odontol", "fisioter",
                 "physiother", "veterinár", "veterinar", "terapeut", "therap",
                 "dermatol"),
    "банк": ("banco", "bank", "banque", "banca"),
    "бизнес": ("business", "negócio", "negocio", "empresa", "consultor",
               "consulting", "beratung", "unternehmen", "corporate", "gestão",
               "gestión", "gestion", "management"),
    "букмекерские_конторы": ("bookmaker", "букмекер"),
    "документация": ("document", "cartório", "cartorio", "notar", "dokument"),
    "инвестиции": ("invest", "inversión", "inversion", "investimento",
                   "anlage"),
    "крипто": ("crypto", "cripto", "blockchain", "krypto"),
    "образование": ("educação", "educacao", "educación", "educacion",
                    "education", "escola", "school", "universi", "faculdade",
                    "curso", "formation", "bildung", "akademi", "academy",
                    "instituto"),
    "семейное_право": ("direito de família", "family law", "derecho de familia",
                       "erbrecht", "herança", "heranca", "inheritance",
                       "sucessõ", "sucesion", "succession"),
    "финансы": ("finanç", "financ", "finanz", "contabil", "accounting",
                "buchhalt", "fiscal", "tribut", "imposto", "seguro",
                "insurance", "versicherung", "crédito", "credito",
                "empréstimo", "emprestimo", "loan", "hipotec", "mortgage"),
    "юриспруденция": ("advocacia", "advogad", "abogad", "lawyer", "attorney",
                      "jurídic", "juridic", "legal", "anwalt", "avocat",
                      "avvocato", "direito", "derecho"),
}

_RED_C = [(re.compile(p, re.I | re.U), w, c) for p, w, c in RED]
_YEL_C = [(re.compile(p, re.I | re.U), w, c) for p, w, c in YELLOW]


# --- тригер-індекс: 235 патернів на файл → ~26 ------------------------------
# 235 окремих finditer по КОЖНОМУ файлу — 84% часу прогону великої вітки
# (02.10: 182 файли → 39 с). Alternation-скрин не допоміг (бектрекінг
# з'їдає стільки ж), тож інвертований індекс: з патерна беруться його
# ЛІТЕРАЛЬНІ фрагменти (≥3 літер, поза класами), і файл ганяє лише
# патерни, чиї фрагменти в ньому Є підрядком (дешевий str-in у C).
# Пропуск неможливий: будь-який матч патерна містить його обов'язкові
# літерали; патерни з альтернаціями поза класами (гілка може оминути
# літерал) і зовсім без літералів ганяються ЗАВЖДИ.
_LIT_RX = re.compile(
    r"[A-Za-zА-Яа-яёЁіІїЇєЄàâãáäåçèéêëìíîïñòóôõöùúûüß"
    r"\u0600-\u06FF\u0E00-\u0E7F]{3,}")
_OPT_GROUP_RX = re.compile(r"\((?:\?[:!=<P]*)?[^()]*\)(?:[?*]|\{0[^}]*\})")


def _mandatory(pat: str) -> str:
    """Патерн без ОПЦІОНАЛЬНИХ груп: їхні альтернації не ламають
    обов'язковість ядра (арабський префікс `(?:ال|[وبلفك](?:ال)?)?`
    опціональний — літерал «مراهنات» гарантований у кожному матчі)."""
    prev = None
    body = pat
    while prev != body:
        prev = body
        body = _OPT_GROUP_RX.sub(" ", body)
    return body


def _pattern_literals(pat: str) -> list:
    body = _mandatory(pat)
    body = re.sub(r"\\[wbBdDsSAZn]", " ", body)
    body = re.sub(r"\[[^\]]*\]", " ", body)   # класи не гарантують вмісту
    # літера з опціональним квантифікатором (s?, a*, x{0,2}) НЕ обов'язкова
    # у матчі — ламає підрядковий тригер («cassinos?» мусить дати «cassino»)
    body = re.sub(r"(?<!\()([A-Za-zА-Яа-яёЁіІїЇєЄàâãáäåçèéêëìíîïñòóôõöùúûüß"
                  r"\u0600-\u06FF\u0E00-\u0E7F])"
                  r"(?:[?*]|\{0[^}]*\})", " ", body)
    return [t.lower() for t in _LIT_RX.findall(body)]


def _build_index():
    all_pats = [p for p, _w, _c in RED] + [p for p, _w, _c in YELLOW]
    idx: dict[str, list[int]] = {}
    always: list[int] = []
    for i, p in enumerate(all_pats):
        lits = _pattern_literals(p)
        mand = re.sub(r"\[[^\]]*\]", " ", _mandatory(p))
        if not lits or "|" in mand:
            always.append(i)
            continue
        for t in set(lits):
            idx.setdefault(t, []).append(i)
    return idx, always

_TRIG_IDX, _ALWAYS = _build_index()


def _candidates(scan: str) -> list:
    """Індекси патернів (у порядку RED+YELLOW), які варто ганяти на файлі."""
    low = scan.lower()
    cand = set(_ALWAYS)
    for t, ids in _TRIG_IDX.items():
        if t in low:
            cand.update(ids)
    return sorted(cand)

# Мовчить на хорватських сторінках (ключ — «слово/форма» з книги).
HR_EXEMPT = {"puta(s)"}
SKIP_FILES = {"package.json", "package-lock.json"}
_MARKUP = (".html", ".htm", ".php")

LANG_RX = re.compile(r"""<html\b[^>]*\blang\s*=\s*["']?([A-Za-z-]+)""", re.I)
# заперечення перед жовтим словом: легенда «Отрицание рядом … снимает»
NEG_RX = re.compile(
    r"""(?<!\w)(?:not|no|never|without|non|sin|sem|ohne|sans|senza|nicht"""
    r"""|kein|keine|não|nao|не|нет|без)["'«»\s,;:()\-\u2013\u2014]{1,12}$""",
    re.I | re.U)

# --- маска видимого тексту: довжина і переводи рядків зберігаються ---------
_BLANK_RX = re.compile(
    r"<(script|style|noscript|template|svg)\b.*?(?:</\1\s*>|$)"
    r"|<!--.*?(?:-->|$)"
    r"|<\?(?:php\b)?.*?(?:\?>|$)", re.S | re.I)
_TAG_RX = re.compile(r"<[^>]+>")
_KEEP_ATTR_RX = re.compile(
    r"""\b(?:title|alt|placeholder|aria-label|content)\s*=\s*"""
    r"""("([^"]*)"|'([^']*)')""", re.I)


def _spaced(m):
    return "".join("\n" if ch == "\n" else " " for ch in m.group(0))


def _masked_tag(m):
    tag = m.group(0)
    out = ["\n" if ch == "\n" else " " for ch in tag]
    for am in _KEEP_ATTR_RX.finditer(tag):
        g = 2 if am.group(2) is not None else 3
        out[am.start(g):am.end(g)] = tag[am.start(g):am.end(g)]
    return "".join(out)


def _visible(text):
    return _TAG_RX.sub(_masked_tag, _BLANK_RX.sub(_spaced, text))


def _scan_view(path, text):
    """(текст для пошуку, мова сторінки). Оффсети збігаються з оригіналом."""
    if path.lower().endswith(_MARKUP):
        m = LANG_RX.search(text)
        return _visible(text), (m.group(1).lower() if m else "")
    return text, ""


# --- тема вітки ------------------------------------------------------------
_TITLE_RX = re.compile(r"<title[^>]*>(.*?)</title\s*>", re.S | re.I)
_DESC_RX = re.compile(
    r"""<meta\s[^>]*(?:name|property)\s*=\s*["']"""
    r"""(?:description|og:description|og:site_name)["']"""
    r"""[^>]*\bcontent\s*=\s*["']([^"']*)""", re.I)


def _exempt_cats(files):
    """Жовті категорії, які мовчать на цій вітці («Исключения по теме»)."""
    for path in sorted((p for p in files
                        if p.rsplit("/", 1)[-1].lower().startswith("index.")),
                       key=lambda p: (p.count("/"), p)):
        text = files[path]
        bits = [m.group(1) for m in [_TITLE_RX.search(text)] if m]
        bits += [m.group(1) for m in [_DESC_RX.search(text)] if m]
        blob = " ".join(bits).lower()
        if blob.strip():
            themes = {t for t, kws in THEMES.items()
                      if any(k in blob for k in kws)}
            return {cat for cat, ts in THEME_EXEMPT.items() if ts & themes}
    return set()


def _negated(scan, start):
    return bool(NEG_RX.search(scan[max(0, start - 24):start]))


def _findings(files):
    """{path: (спани, маска)}; спани відсортовані, перекриття злиті
    (assault rifle поглинає rifle: червоне і довше мають пріоритет)."""
    exempt = _exempt_cats(files)
    out = {}
    n_red = len(_RED_C)
    for path, text in files.items():
        if path.rsplit("/", 1)[-1].lower() in SKIP_FILES:
            continue
        scan, lang = _scan_view(path, text)
        found = []
        for i in _candidates(scan):
            if i < n_red:
                rx, w, c = _RED_C[i]
                if w in HR_EXEMPT and lang.startswith("hr"):
                    continue
                for m in rx.finditer(scan):
                    found.append((m.start(), m.end(), "red", w, c))
            else:
                rx, w, c = _YEL_C[i - n_red]
                if c in exempt:
                    continue
                for m in rx.finditer(scan):
                    if not _negated(scan, m.start()):
                        found.append((m.start(), m.end(), "yellow", w, c))
        found.sort(key=lambda f: (f[0], 0 if f[2] == "red" else 1,
                                  -(f[1] - f[0])))
        merged, last_end = [], -1
        for f in found:
            if f[0] < last_end:
                continue
            merged.append(f)
            last_end = f[1]
        if merged:
            out[path] = (merged, scan)
    return out


def run_branch(files, all_paths, branch=""):
    issues = []
    for path, (found, scan) in sorted(_findings(files).items()):
        for start, end, tier, w, c in found:
            frag = files[path][start:end]
            line = scan.count("\n", 0, start) + 1
            if tier == "red":
                sev, note = "error", "червоне, валить домен"
            else:
                sev, note = "warn", "жовте, глянути очима"
            issues.append({
                "path": path, "line": line, "severity": sev,
                "message": f"бан-слово QA ({note}): «{frag}» — {c} [{w}]",
            })
    return issues


# --- автофікс ---------------------------------------------------------------
_PUNCT = ".,;:!?"


def _delete_span(text, start, end):
    before, after = text[:start], text[end:]
    if after[:1] == " " and before[-1:] in ("", " ", ">", "\n"):
        after = after.lstrip(" ")
    if after[:1] in _PUNCT and before[-1:] == " ":
        before = before.rstrip(" ")
    return before + after


def fix_branch(files, all_paths, branch=""):
    actions = []
    for path, (found, scan) in sorted(_findings(files).items()):
        text = files[path]
        edits = []
        for start, end, tier, w, c in found:
            rep = REPLACEMENTS.get(w)
            if rep is None and tier != "red":
                continue                     # жовте без словника — людині
            edits.append((start, end, rep))
        new = text
        for start, end, rep in sorted(edits, reverse=True):
            if rep is None:
                new = _delete_span(new, start, end)
            else:
                src = new[start:end]
                if src[:1].isupper():
                    rep = rep[:1].upper() + rep[1:]
                new = new[:start] + rep + new[end:]
        if new != text:
            actions.append({"type": "edit", "path": path, "content": new})
    return actions
