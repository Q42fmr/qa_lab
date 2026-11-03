"""Прибирає alert() з обробника помилки ajax-запиту до бекенду, якого у вайті немає.

Кейс `abhuoaveguof-br-pt`: на завантаженні беззастережно виконується

    updateCurrentFilters($("#property-status"));

яка кличе

    $.ajax({method:"POST", url:"/u-sf.php", …,
            error:function(xhr){alert("An error occured: "+xhr.status+" "+xhr.statusText);}, …})

`u-sf.php` у вітці немає (це бекенд оригінального сайту), тож запит завжди 404 —
і відвідувач на КОЖНІЙ сторінці бачить модалку «An error occured: 404 error».

Чому трансформ, а не перевірка. Заміряно по всьому кешу: `alert()` у
error-обробнику ajax є рівно в **1 вітці з 7990**. Автоматичний чек на один
випадок — зайва механіка; тут доречна разова правка через «Заміни -> Скрипт».

Чому глушимо не всі alert у error-обробниках. У тому ж файлі є
`alert("Ocorreu um erro ao enviar, pedimos que por gentileza tente novamente.")`
— теж в error-обробнику, але це ЖИВИЙ фідбек користувачу на його ж дію
(сабміт форми), і без нього людина не дізнається, що лід не пішов. Тому
трансформ прив'язаний до КОНКРЕТНИХ мертвих ендпоінтів: під свій кейс
допиши шлях у DEAD_ENDPOINTS.
"""
import re

NAME = "Прибрати alert мертвого ajax-ендпоінта"
DESCRIPTION = ("Глушить alert() лише в ajax-запитах до ендпоінтів зі списку "
               "DEAD_ENDPOINTS, яких у вайті немає (кейс abhuoaveguof-br-pt: "
               "/u-sf.php -> 404-модалка на кожній сторінці). Alert-и форм і "
               "будь-яку іншу валідацію не чіпає.")
FILES = ["*.html", "*.php", "*.js"]

# бекенди оригінального сайту, яких у вайті немає — правити під свій випадок
DEAD_ENDPOINTS = ["/u-sf.php"]

ERROR_HANDLER_RX = re.compile(
    r"(error\s*:\s*function\s*\([^)]*\)\s*\{)(?P<body>[^{}]*)(\})", re.I)
ALERT_RX = re.compile(r"\balert\s*\(")
# url ajax-виклику, у якому сидить цей обробник: шукаємо назад по тому ж об'єкту
URL_RX = re.compile(r"""url\s*:\s*["']([^"']+)["']""", re.I)
LOOKBACK = 400


def _dead_call(text: str, at: int) -> bool:
    """Чи належить обробник виклику до мертвого ендпоінта."""
    window = text[max(0, at - LOOKBACK):at]
    urls = URL_RX.findall(window)
    if not urls:
        return False
    return urls[-1].split("?")[0] in DEAD_ENDPOINTS


def transform(path, text):
    def repl(m):
        body = m.group("body")
        if not ALERT_RX.search(body) or not _dead_call(text, m.start()):
            return m.group(0)
        return m.group(1) + ALERT_RX.sub("console.warn(", body) + m.group(3)

    return ERROR_HANDLER_RX.sub(repl, text)
