# syntax=docker/dockerfile:1
#
# =============================================================================
# qa_lab — образ
# =============================================================================
# Лаба не просто веб-застосунок: вона ПОРОДЖУЄ ПРОЦЕСИ — піднімає `php -S` на
# кожну вітку, керує headless-Chrome власним CDP-драйвером, кличе node для
# Lighthouse і npm для білду node-вайтів. Тому в образі живуть три рантайми
# поруч з python.
#
# Стадії:
#   lhdeps  — node_modules для Lighthouse (ставляться під час білду, не старту);
#             звідси ж беруться самі бінарники node і npm
#   base    — важкий спільний шар: apt + pip + env. Кешується; правка коду
#             його не перезбирає
#   dev     — код приїжджає bind-mount'ом, uvicorn --reload
#   prod    — код запечений у шар, uvicorn без reload
#
# Збірка:
#   docker build -f docker/Dockerfile --target dev  -t qa_lab:dev  .
#   docker build -f docker/Dockerfile --target prod -t qa_lab:prod .
# =============================================================================


# -----------------------------------------------------------------------------
# lhdeps — залежності Lighthouse
# -----------------------------------------------------------------------------
# Окрема стадія з двох причин:
#   1) `npm install` під час СТАРТУ контейнера — це мережа і хвилини на кожен
#      запуск, а в проді ще й недетермінізм;
#   2) node з Debian bookworm — 18.19, а Lighthouse 12 вимагає >= 18.20.
#      Тому і сам node беремо звідси, а не з apt.
# `npm ci` (а не `install`) ставить рівно те, що в lock-файлі, і падає при
# розсинхроні з package.json — білд відтворюваний, розсинхрон помітний одразу.
FROM node:20-bookworm-slim AS lhdeps
WORKDIR /opt/lighthouse
COPY package.json package-lock.json ./
RUN npm ci --omit=dev


# -----------------------------------------------------------------------------
# base — спільний важкий шар
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS base

# Чому 3.12: проєкту потрібен >= 3.10 (PEP 604 у pydantic-моделях app.py
# резолвиться в рантаймі, а не лише в анотаціях). 3.12 — зріла версія з
# готовими колесами для всіх шести залежностей.

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Europe/Kyiv

# Системні пакети. Кожен — з причиною; ставимо одним шаром і одразу чистимо
# списки apt, інакше вони лишаються в шарі назавжди.
#
#   chromium      — скріни (deployer), візуальні перевірки (visual_runner),
#                   пошук фото без API-ключа (photos._magnific_web)
#   php-cli       — `php -S`, тобто деплой кожної вітки. Без нього одразу
#                   падають Скріни / Візуальні / Lighthouse / Локальні вайти
#   tini          — init-процес №1: лаба плодить php- і chrome-дітей, без
#                   reaper'а вони лишаються зомбі
#   tzdata        — під TZ вище: журнал і stats/*.jsonl пишуться через
#                   time.strftime у ЛОКАЛЬНОМУ часі; у UTC-контейнері вся
#                   історія зсунулась би на 3 години
#   ca-certificates — https до GitLab / ClickUp / фотостоків
#   fonts-*       — НЕ косметика. Вайти рендеряться португальською, іспанською,
#                   арабською, тайською. Без шрифта Chrome не дає помилки — він
#                   мовчки малює порожні прямокутники, і чеки контрасту й
#                   «обрізаного тексту» починають масово фолсити
#
# Свідомо НЕ ставимо:
#   procps (ps) — deployer._is_php() на Linux читає /proc/<pid>/comm, а ps
#                 лишається фолбеком лише для macOS/BSD
#   git         — синхрон віток іде через GitLab API і zipfile
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        chromium \
        php-cli \
        tini \
        tzdata \
        ca-certificates \
        fonts-dejavu-core \
        fonts-liberation \
        fonts-noto-core \
        fonts-noto-cjk \
    ; \
    rm -rf /var/lib/apt/lists/*

# node — бінарник з офіційного образу (та сама база bookworm, та сама glibc).
# Ним ганяється Lighthouse, ним же npm збирає node-вайти.
COPY --from=lhdeps /usr/local/bin/node /usr/local/bin/node
COPY --from=lhdeps /opt/lighthouse/node_modules /opt/lighthouse/node_modules

# npm — деплой node-вайтів (проєкт `vue`, вітки nwf-*): `_nuxt_compile()`
# робить `npm install` + `npm run generate`, і БЕЗ npm мовчки лягають одразу
# чотири вкладки — Deploy, Скріни, Візуальні, Lighthouse. Усі троє кличуть
# `deployer.deploy(wait=True)`, а той першою ж дією йде в npm і падає
# `[Errno 2] No such file or directory: 'npm'`. У UI це один тост, що зникає,
# тому шукали довго (кейс 25.08, вітка nwf-rimag-tegn-sojidiihr-co-es).
#
# Тут раніше стояло «~150 МБ, рішення відкладене» — це ціна apt-пакета `npm`,
# який тягне ДРУГИЙ рантайм nodejs поруч із нашим. Копія з lhdeps коштує
# 19 МБ: node (119 МБ) в образі вже є, а npm — просто js-пакет під нього.
#
# Симлінк робимо самі, а не копіюємо: в офіційному образі це ВІДНОСНЕ
# посилання, і COPY переніс би його раніше за теку, на яку воно вказує.
# npx — з того самого пакета, тобто безкоштовно; без нього падали б шаблони,
# у яких скрипт білду написаний через `npx <щось>`.
COPY --from=lhdeps /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# pip — ДО копіювання коду, щоб шар кешувався і правка app.py не запускала
# перевстановлення залежностей.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

ENV BROWSER_BIN=/usr/bin/chromium \
    NODE_BIN=/usr/local/bin/node \
    NPM_BIN=/usr/local/bin/npm \
    PHP_BIN=/usr/bin/php \
    LIGHTHOUSE_CLI=/opt/lighthouse/node_modules/lighthouse/cli/index.js \
    BROWSER_EXTRA_ARGS="--no-sandbox --disable-dev-shm-usage"

# BROWSER_EXTRA_ARGS — два прапорці, без яких Chrome у контейнері не працює:
#   --no-sandbox            пісочниця вимагає привілеїв, яких у контейнері немає
#   --disable-dev-shm-usage /dev/shm у docker за замовчуванням 64 МБ, і на
#                           довгій сторінці (вайти бувають 9000 px) Chrome падає.
#                           Штатне лікування — shm_size у compose, але SWARM ЙОГО
#                           ІГНОРУЄ, тож прапорець — єдиний робочий шлях.
# Локально змінна порожня, тобто нативний запуск не змінюється.

WORKDIR /app

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8030

# tini як PID 1 — див. вище про зомбі.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]

# --host 0.0.0.0 всередині контейнера — не дірка: назовні порт віддає docker
# (у деві) або Traefik (у проді). Слухати 127.0.0.1 означало б, що до сервісу
# не достукається ніхто.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8030", \
     "--timeout-graceful-shutdown", "3"]


# -----------------------------------------------------------------------------
# dev — код приїжджає bind-mount'ом
# -----------------------------------------------------------------------------
# Образ навмисно БЕЗ коду: docker-compose.dev.yml монтує теку розробника в
# /app, тож правка файлу діє одразу, без перезбирання.
FROM base AS dev
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8030", \
     "--reload", "--timeout-graceful-shutdown", "3"]


# -----------------------------------------------------------------------------
# prod — код запечений у шар
# -----------------------------------------------------------------------------
FROM base AS prod
COPY . /app
