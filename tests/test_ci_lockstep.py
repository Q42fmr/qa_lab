"""Lockstep `.env.prod.example` ⇄ `.gitlab-ci.yml`.

Навіщо цей тест узагалі. Шаблон прода — це файл з плейсхолдерами, які
пайплайн підставляє рядками `sed`. Два файли, один контракт, і ламається він
мовчки: додав змінну в шаблон, забув `sed` — guard у CI впаде на
нерозв'язаному плейсхолдері вже під час деплою, тобто найдорожчим способом.
Зворотний бік гірший: `sed` без `:-` дефолту підставляє порожнє значення
тільки якщо змінна ВИЗНАЧЕНА, а незаведена CI-змінна лишає літерал.

Друге, що тут закріплено: **`build` не залежить від жодного секрета**.
Гейти на DOMAIN_NAME/паролі живуть у `script:` деплою, а не в спільному
`before_script` — інакше репозиторій без заведених змінних не збереться
взагалі, і не буде як прогнати тести в образі до першого деплою.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import ROOT, run                                    # noqa: E402

ENV = (ROOT / ".env.prod.example").read_text(encoding="utf-8")
CI = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")

# Коментарі викидаємо ДО розбору. У шапці пайплайна той самий вигляд
# підстановки трапляється як ПРИКЛАД у коментарі, і без цього кроку приклад
# читався б як справжній рядок: тест падав на «sed є, а плейсхолдера немає»
# і показував пальцем на коментар. Кейс 19.08 — саме так і сталося.
CI_CODE = "\n".join(l for l in CI.splitlines() if not l.lstrip().startswith("#"))

# Те саме для двох інших файлів, і з тієї ж причини: у compose і в шаблоні
# прода коментарі докладно пояснюють, ЧОГО там більше немає (BasicAuth), тож
# пошук по всьому тексту знаходив би слово в поясненні і падав на ньому.
COMPOSE_CODE = "\n".join(l for l in COMPOSE.splitlines() if not l.lstrip().startswith("#"))
ENV_CODE = "\n".join(l for l in ENV.splitlines() if not l.lstrip().startswith("#"))

# Розділювач `|` навмисно заборонений у значеннях (у пайплайні на це є guard,
# бо sed мовчки обрізає значення по ньому), тому значення його не містить.
SEDS = dict(re.findall(r"s\|\{\{(\w+)\}\}\|([^|]*)\|g", CI_CODE))
PLACEHOLDERS = set(re.findall(r"\{\{(\w+)\}\}", ENV))


def _default(name: str) -> str:
    """Дефолт із `${NAME:-щось}`. Порожній рядок — теж дефолт."""
    val = SEDS[name]
    return val[len("${%s:-" % name):-1]


# --------------------------------------------------------------- lockstep

def test_every_placeholder_has_a_sed():
    missing = sorted(PLACEHOLDERS - set(SEDS))
    assert not missing, f"у .gitlab-ci.yml немає sed для: {missing}"


def test_no_orphan_seds():
    """Зайвий sed — слід від видаленої змінної; сам по собі не шкодить,
    але створює враження, що змінна ще працює."""
    orphans = sorted(set(SEDS) - PLACEHOLDERS)
    assert not orphans, f"sed є, а плейсхолдера в шаблоні немає: {orphans}"


def test_each_sed_substitutes_its_own_variable():
    """Ловить копіпаст: рядок для A підставляє значення B."""
    wrong = [n for n, v in SEDS.items() if not v.startswith("${%s:-" % n)]
    assert not wrong, f"sed підставляє чужу змінну: {sorted(wrong)}"


def test_each_sed_has_a_default():
    """Без `:-` незаведена CI-змінна лишає в .env літерал `${NAME}`, і це
    доїде в прод: guard шукає `{{`, а не `${`."""
    nodefault = [n for n, v in SEDS.items() if ":-" not in v]
    assert not nodefault, f"sed без дефолту: {sorted(nodefault)}"


def test_nested_variables_also_have_defaults():
    """Дефолт може сам посилатись на змінну — `SLACK_REDIRECT_URI` виводиться
    з `DOMAIN_NAME`. Така вкладена підстановка теж мусить мати `:-`: у шелі,
    запущеному з `set -u`, гола `${DOMAIN_NAME}` кладе весь рендер, і причина
    виглядає як «зламався sed для Slack», хоч Slack тут ні до чого.
    """
    bad = []
    for name in SEDS:
        for ref in re.findall(r"\$\{(\w+)(:-)?", _default(name)):
            if not ref[1]:
                bad.append(f"{name} -> ${{{ref[0]}}}")
    assert not bad, f"вкладена змінна без дефолту: {sorted(bad)}"


def test_render_with_no_variables_leaves_no_placeholder():
    """Головний сценарій: репозиторій, де ще не заведено ЖОДНОЇ CI-змінної.
    Саме так виглядає перший білд, і саме тут пайплайн падав би."""
    rendered = ENV
    for name in SEDS:
        rendered = rendered.replace("{{%s}}" % name, _default(name))
    left = re.findall(r"\{\{\w+\}\}", rendered)
    assert not left, f"після рендеру лишились плейсхолдери: {left}"


# ------------------------------------------------- білд без CI-змінних

def _auto_deploy_before_script() -> str:
    """Текст before_script спільного `.auto-deploy` — той, що виконується і
    в `build`, і в деплої."""
    block = CI[CI.index(".auto-deploy:"):]
    return block[block.index("before_script:"):block.index("\n  script:")]


def test_build_needs_no_secrets():
    """`build` успадковує before_script, тому гейтів на секрети там бути не
    може — інакше образ не збереться, поки не заведено весь набір змінних."""
    before = _auto_deploy_before_script()
    for guard in ("$DOMAIN_NAME", "$ADMIN_PASSWORD"):
        assert f'test -n "{guard}"' not in before, \
            f"гейт на {guard} у before_script — він зупинить і build"


def test_deploy_guards_are_in_place():
    """Але в деплої вони мусять бути: порожній ADMIN_PASSWORD лишає інстанс без
    єдиної гарантованої учетки — а відколи BasicAuth перед лабою знято, форма
    входу застосунку є всім гейтом, що стоїть між доменом і чужими руками."""
    script = CI[CI.index("\n  script:", CI.index(".auto-deploy:")):]
    script = script[:script.index("docker stack deploy")]
    assert 'test -n "$DOMAIN_NAME"' in script
    assert 'test -n "$ADMIN_PASSWORD"' in script


# ------------------------------------------------------ Slack: трійка змінних

def _deploy_script() -> str:
    """Текст `script:` деплою — до самої команди деплою."""
    script = CI[CI.index("\n  script:", CI.index(".auto-deploy:")):]
    return script[:script.index("docker stack deploy")]


SLACK_TRIO = ("SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_TEAM_ID")


def test_slack_trio_is_all_or_nothing():
    """Дві заповнені змінні з трьох — найтихіша поломка входу.

    `slack_oauth.enabled()` вимагає ВСІ ТРИ (коміт 6d20f15), тож на неповній
    трійці модуль вимикається цілком: кнопки на екрані входу немає, у логах
    застосунку порожньо, сам він здоровий. Причину в лабі не видно НІЯК —
    єдине місце, де стан ще відомий, це джоба деплою. Тому вона й зупиняється.

    Найчастіший шлях сюди — галка *Protected* на змінній при non-protected
    гілці: значення приїжджає порожнім і мовчки.
    """
    script = _deploy_script()
    missing = [n for n in SLACK_TRIO if n not in script]
    assert not missing, f"guard на неповну трійку Slack не бачить: {missing}"
    assert "exit 1" in script[script.index("SLACK_CLIENT_ID"):], \
        "guard знайшов неповну трійку, але не зупиняє деплой"


def test_slack_guard_stays_out_of_the_shared_before_script():
    """Той самий контракт, що з DOMAIN_NAME і ADMIN_PASSWORD: `build`
    успадковує `before_script` і мусить збиратись на репозиторії, де не
    заведено жодної CI-змінної."""
    before = _auto_deploy_before_script()
    assert "all three variables or none" not in before, \
        "guard на трійку Slack у before_script — він зупинить і build"


def test_deploy_log_shows_the_slack_redirect_uri():
    """Redirect URL мусить збігатися з тим, що вписано в застосунку Slack,
    символ у символ: розбіжність Slack повертає як `bad_redirect_uri` на
    СВОЄМУ боці, до нашого коду запит не доходить і в логах лаби не лишається
    нічого. Тому рядок друкується в лог деплою — звірити очима дешевше, ніж
    шукати це вдруге."""
    assert "redirect_uri:" in CI_CODE, \
        "блок «== інтеграції ==» більше не друкує redirect_uri Slack"


# ------------------------------------------------------ healthcheck

def _healthcheck_path() -> str:
    m = re.search(r"urlopen\('http://127\.0\.0\.1:\d+([^']+)'", COMPOSE)
    assert m, "у docker-compose.prod.yml не видно URL healthcheck"
    return m.group(1)


def test_healthcheck_path_is_public():
    """Реальний інцидент, знайдений до першого деплою: healthcheck стукав у
    `/api/status`, який закриває auth-middleware. Відповідь 401 —
    `urlopen` кидає HTTPError, команда виходить з 1, таска НІКОЛИ не стає
    healthy, і `update_config.failure_action: rollback` відкочує цілком
    робочий деплой. Ззовні це виглядає як «стек не піднімається».
    """
    import auth
    path = _healthcheck_path()
    assert path in auth.PUBLIC_PATHS, \
        f"healthcheck ходить на {path}, а він не в PUBLIC_PATHS"


def test_healthcheck_path_exists_as_a_route():
    """Другий бік тієї ж помилки: шлях був у PUBLIC_PATHS, а ендпоінта не
    існувало — 404 валить healthcheck так само надійно, як 401."""
    path = _healthcheck_path()
    assert f'@app.get("{path}")' in APP, \
        f"{path} дозволений і використовується healthcheck, але маршруту немає"


# ------------------------------------------------- `|` у значеннях секретів

# Секрети з вільним текстом: значення вибирає людина, тому `|` у ньому цілком
# можливий. Токени GitLab/ClickUp/Slack і bcrypt-хеш сюди не входять — там
# алфавіт фіксований і цього символу не буває.
FREE_TEXT_SECRETS = {
    "ADMIN_PASSWORD", "ADMIN_LOGIN", "ADMIN_NAME",
    "MONGO_URI", "QA_LAB_SECRET_KEY",
}


# Символи, які sed у рядку заміни трактує як синтаксис, а не як себе.
SED_META = ("|", "&", "\\")


def test_sed_metacharacters_in_free_text_secrets_are_guarded():
    """Заміряно 19.08 на реальному рендері, усі три мовчки:

        'p@ss|word'  ->  'p@ss'                      (| — розділювач)
        'ab&cd'      ->  'ab{{ADMIN_PASSWORD}}cd'    (& — весь збіг)
        'ab\\cd'      ->  'ab'                        (\\ — екранування)

    Помилки немає в жодному випадку: команда для sed лишається коректною.
    Далі це виглядає як «адмін не може зайти правильним паролем», і зв'язати
    одне з одним нема з чого — саме на цьому згорів перший деплой. Тому
    пайплайн зупиняється ДО підстановки, а тест стереже і список символів,
    і список змінних, щоб вони не відстали від шаблону.
    """
    lines = [l.strip() for l in CI_CODE.splitlines()]
    guard = [l for l in lines if "sed treats them as syntax" in l]
    assert guard, "у .gitlab-ci.yml немає guard'а на спецсимволи sed"

    # Беремо саме рядок цього guard'а, а не перший-ліпший `case`: у
    # before_script є ще одна case-гілка (форма bcrypt), і вона стоїть вище.
    # Шукаємо сам символ, а не його лапки: у YAML зворотний слеш записаний
    # подвоєним, і звірка з `"\\"` дала б хибне падіння.
    unguarded = [c for c in SED_META if c not in guard[0]]
    assert not unguarded, f"guard не ловить символи: {unguarded}"

    loop = [l for l in lines if l.startswith("for n in ")]
    assert loop, "guard є, але не видно списку змінних, які він перевіряє"
    names = set(loop[0][len("for n in "):].split(";")[0].split())
    missing = sorted(FREE_TEXT_SECRETS - names)
    assert not missing, f"guard не покриває змінні: {missing}"


# ------------------------------------------- один гейт, а не два на origin

def test_no_basic_auth_middleware_in_front_of_the_app():
    """Traefik-BasicAuth перед лабою і власний вхід лаби несумісні.

    Chrome шле збережений Basic-пароль превентивно на КОЖЕН запит хоста.
    Наш застосунок відповідає 401 без `WWW-Authenticate` — і на невдалий
    вхід, і на протухлу сесію, — а браузер читає такий 401 як «пароль
    відхилено» і викидає його з кеша. Наступний запит іде голим, Traefik
    питає пароль знову.

    Заміряно 26.08 на копії бутерброда (проксі, що відповідає як Traefik,
    справжній Chrome через CDP): жодного 401 від застосунку — навігація несе
    `Authorization`, вікна немає; один 401 — наступний запит без пароля і
    вікно щоразу. Кейс: користувач вводить логін у лабу і отримує вікно
    BasicAuth утретє.

    Тому гейт має лишатись ОДИН. Якщо BasicAuth колись знадобиться — не на
    цьому origin і не Basic.
    """
    assert "basicauth" not in COMPOSE_CODE.lower(), \
        "у docker-compose.prod.yml знову з'явився basicauth-middleware"
    assert "BASIC_AUTH_USERS" not in ENV_CODE, \
        "у шаблоні прода лишився BASIC_AUTH_USERS — значить лейбл десь чекає на нього"


def test_app_answers_api_with_a_bare_401():
    """Другий бік того самого контракту: саме «голий» 401 і робить BasicAuth
    попереду отруйним. Якщо колись з'явиться `WWW-Authenticate`, застосунок
    почне САМ малювати нативне вікно браузера замість свого екрана входу —
    і тест вище стане неактуальним разом із цим рядком."""
    assert "WWW-Authenticate" not in APP, \
        "застосунок став віддавати WWW-Authenticate — перечитай test_no_basic_auth_middleware…"


if __name__ == "__main__":
    run(dict(globals()))
