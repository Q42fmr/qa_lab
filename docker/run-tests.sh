#!/usr/bin/env sh
# =============================================================================
# Тестовий гейт: усі tests/test_*.py + `import app`.
# =============================================================================
# Запускається ВСЕРЕДИНІ зібраного образу:
#
#   docker run --rm --entrypoint sh <образ> /app/docker/run-tests.sh
#
# Навіщо окремим файлом, а не рядком у .gitlab-ci.yml: інлайн-скрипт у
# YAML-блоці доводиться екранувати тричі (YAML → shell → awk), і зламати
# його правкою легше, ніж помітити. Тут його ще й можна прогнати руками.
#
# Тести — власний харнес проєкту, НЕ pytest: кожен файл сам друкує
# останнім рядком "N/N passed" і повертає 1 при падінні.
set -u

cd "${APP_DIR:-/app}"

fail=0
pass=0
total=0

for t in tests/test_*.py; do
    if out=$(python "$t" 2>&1); then
        status=OK
    else
        status=FAIL
        fail=1
    fi

    line=$(printf '%s\n' "$out" | grep -E '^[0-9]+/[0-9]+ passed' | tail -1)
    p=${line%%/*}
    m=${line#*/}
    m=${m%% *}
    case "$p" in ''|*[!0-9]*) p=0 ;; esac
    case "$m" in ''|*[!0-9]*) m=0 ;; esac
    pass=$((pass + p))
    total=$((total + m))

    if [ "$status" = FAIL ]; then
        printf 'FAIL  %s\n' "$t"
        printf '%s\n' "$out" | tail -25
    fi
done

printf 'РАЗОМ: %s/%s тестів пройдено\n' "$pass" "$total"

# Окремо: імпорт застосунку. Ловить те, чого не бачать юніт-тести —
# биті імпорти, помилки в декораторах ендпоінтів, незадекларовані залежності.
if python -c "import app" >/dev/null 2>&1; then
    echo "import app: ok"
else
    echo "import app: FAILED"
    python -c "import app" 2>&1 | tail -20
    fail=1
fi

exit "$fail"
