#!/usr/bin/env sh
# =============================================================================
# qa_lab — entrypoint
# =============================================================================
# Робить три речі й передає керування:
#   1) створює теки стану, які код очікує знайти;
#   2) засіває fixtures/ зразками, якщо там порожньо (MOCK_MODE без токена);
#   3) exec "$@" — щоб uvicorn став тим самим процесом і отримував сигнали.
#
# Без exec SIGTERM піде цьому скрипту, а не серверу, і зупинка контейнера
# перетвориться на 10-секундний таймаут з kill -9. Той самий патерн, що в
# сусідньому news-parser/docker/php/entrypoint-prod.sh.
set -eu

APP_DIR="${APP_DIR:-/app}"
STATE_DIR="${QA_LAB_STATE_DIR:-$APP_DIR}"

cd "$APP_DIR"

# --- 1. теки стану ---------------------------------------------------------
# Код здебільшого створює їх сам на льоту, але деякі шляхи припускають, що
# тека вже є; дешевше зробити це один раз на старті.
for d in cache deploy screens visual lighthouse stats checkruns logs; do
    mkdir -p "$STATE_DIR/$d"
done

# --- 1-біс. npm-кеш — у стан, а не в шар контейнера ------------------------
# node-вайти збираються `npm install`-ом у builder-теці, і сама вона вже лежить
# у стані (projects/<id>/builder-<hash>/node_modules) — тобто повторний install
# пропускається за маркером. А от HTTP-кеш npm за замовчуванням лягає в
# /root/.npm, тобто в шар контейнера: після кожного оновлення сервісу ПЕРШИЙ
# білд качав би всі пакети наново. Том переживає редеплой — тримаємо його там.
export npm_config_cache="$STATE_DIR/.npm-cache"
mkdir -p "$npm_config_cache"

# --- 2. фікстури для MOCK_MODE --------------------------------------------
# Зразки лежать у docker/seed-fixtures/, а не в fixtures/, бо `fixtures/` у
# .gitignore — там розробник тримає свої знімки, і ми свідомо не чіпаємо той
# файл. Назва саме «seed-fixtures», бо git-патерн `fixtures/` матчить теку з
# такою назвою на БУДЬ-ЯКІЙ глибині: `docker/fixtures/` теж мовчки випадав би
# з комітів.
# Копіюємо ЛИШЕ якщо тека порожня: чужі фікстури не перетираємо ніколи.
if [ -d "$APP_DIR/docker/seed-fixtures" ]; then
    mkdir -p "$APP_DIR/fixtures"
    if [ -z "$(ls -A "$APP_DIR/fixtures" 2>/dev/null)" ]; then
        cp -r "$APP_DIR/docker/seed-fixtures/." "$APP_DIR/fixtures/"
        echo "[entrypoint] fixtures засіяно зразками з docker/seed-fixtures/" >&2
    fi
fi

# --- діагностика -----------------------------------------------------------
# Версії рантаймів у логу: коли вайт рендериться не так, як у розробника,
# перше питання — «а який там php?». npm тут не для версії, а щоб факт його
# наявності було видно ОДРАЗУ: коли його не було, це коштувало пів дня пошуку
# по тосту `[Errno 2] ... 'npm'`, який зникає з екрана.
if [ "${QA_LAB_QUIET_BOOT:-0}" != "1" ]; then
    printf '[entrypoint] python %s | php %s | node %s | npm %s | chromium %s\n' \
        "$(python --version 2>&1 | cut -d' ' -f2)" \
        "$("${PHP_BIN:-php}" -r 'echo PHP_VERSION;' 2>/dev/null || echo '—')" \
        "$("${NODE_BIN:-node}" --version 2>/dev/null || echo '—')" \
        "$("${NPM_BIN:-npm}" --version 2>/dev/null || echo '—')" \
        "$("${BROWSER_BIN:-chromium}" --version 2>/dev/null | awk '{print $2}' || echo '—')" >&2
    printf '[entrypoint] QA_LAB_STATE_DIR=%s | BROWSER_EXTRA_ARGS=%s\n' \
        "$STATE_DIR" "${BROWSER_EXTRA_ARGS:-}" >&2
fi

exec "$@"
