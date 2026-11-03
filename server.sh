#!/usr/bin/env bash
# qa_lab server — Linux/macOS відповідник server.bat.
#   ./server.sh                  меню: запустити / рестарт / зупинити / статус
#   ./server.sh start|restart|stop|status|log
#
# Порт і прапорці перевизначаються з оточення:
#   PORT=8030 RELOAD=0 ./server.sh start
set -uo pipefail

APPDIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$APPDIR" || exit 1

PORT="${PORT:-8030}"
RELOAD="${RELOAD:-1}"
LOG="${LOG:-$APPDIR/logs/server.log}"
ARGS=(app:app --port "$PORT" --timeout-graceful-shutdown 3)
[ "$RELOAD" = "1" ] && ARGS=(app:app --reload --port "$PORT" --timeout-graceful-shutdown 3)

# uvicorn: спершу venv поруч із проєктом, далі PATH, далі модулем python
pick_runner() {
  for v in "$APPDIR/.venv/bin/uvicorn" "$APPDIR/venv/bin/uvicorn"; do
    [ -x "$v" ] && { RUNNER=("$v"); return; }
  done
  if command -v uvicorn >/dev/null 2>&1; then RUNNER=(uvicorn); return; fi
  for p in "$APPDIR/.venv/bin/python" "$APPDIR/venv/bin/python" python3 python; do
    command -v "$p" >/dev/null 2>&1 && { RUNNER=("$p" -m uvicorn); return; }
  done
  echo "не знайшов uvicorn — активуй venv або: pip install -r requirements.txt" >&2
  exit 1
}

# --- хто слухає порт -------------------------------------------------------
# ss є майже скрізь; lsof і fuser — запасні варіанти для мінімальних образів
# і macOS. Повертає pid-и через пробіл (може бути кілька — reload тримає
# і батька, і воркера).
port_pids() {
  local pids=""
  if command -v ss >/dev/null 2>&1; then
    pids=$(ss -ltnpH "sport = :$PORT" 2>/dev/null |
           grep -o 'pid=[0-9]*' | cut -d= -f2)
  fi
  if [ -z "$pids" ] && command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null)
  fi
  if [ -z "$pids" ] && command -v fuser >/dev/null 2>&1; then
    pids=$(fuser -n tcp "$PORT" 2>/dev/null | tr -d ' ')
  fi
  # grep відсіює порожній рядок: інакше на вільному порту з конвеєра
  # виходив один пробіл, is_up вважав його «є pid» і сервер ніколи не
  # стартував, вічно рапортуючи «ПРАЦЮЄ  PID» без номера.
  printf '%s\n' $pids | grep -E '^[0-9]+$' | sort -u | tr '\n' ' '
}

is_up() { [ -n "$(port_pids)" ]; }

# --- зупинка ---------------------------------------------------------------
# Трьома заходами, як у server.bat: 1) uvicorn САМЕ цього застосунку
# (app:app + --port), 2) його діти (--reload тримає воркера окремим процесом),
# 3) живий власник порту. Потім чекаємо, поки порт реально звільниться —
# інакше наступний start впаде в «address already in use».
killall_server() {
  echo "Зупиняю все на порту $PORT..."
  local pids owner child
  pids=$(pgrep -f "uvicorn.*app:app.*--port[= ]$PORT" 2>/dev/null | tr '\n' ' ')
  for p in $pids; do
    child=$(pgrep -P "$p" 2>/dev/null | tr '\n' ' ')
    pids="$pids $child"
  done
  pids="$pids $(port_pids)"

  local uniq
  uniq=$(echo $pids | tr ' ' '\n' | grep -E '^[0-9]+$' | sort -u)
  [ -z "$uniq" ] && { echo "  нічого не знайшов"; return 0; }

  for p in $uniq; do kill -TERM "$p" 2>/dev/null; done
  for _ in $(seq 1 20); do
    is_up || break
    sleep 0.25
  done
  if is_up; then
    for p in $(port_pids); do kill -KILL "$p" 2>/dev/null; done
    sleep 0.5
  fi
  is_up && echo "  !! порт $PORT досі зайнятий: $(port_pids)" || echo "  готово"
}

launch() {
  pick_runner
  mkdir -p "$(dirname "$LOG")"
  echo "Запускаю: ${RUNNER[*]} ${ARGS[*]}"
  # setsid — щоб сервер пережив закриття термінала і мав власну групу
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup "${RUNNER[@]}" "${ARGS[@]}" >>"$LOG" 2>&1 < /dev/null &
  else
    nohup "${RUNNER[@]}" "${ARGS[@]}" >>"$LOG" 2>&1 < /dev/null &
  fi
  for _ in $(seq 1 40); do
    is_up && break
    sleep 0.25
  done
  if is_up; then
    echo "OK  PID $(port_pids) http://127.0.0.1:$PORT/"
  else
    echo "НЕ піднявся — останні рядки $LOG:"
    tail -n 15 "$LOG" 2>/dev/null
    return 1
  fi
}

cmd_start()   { if is_up; then echo "Вже працює  PID $(port_pids)  http://127.0.0.1:$PORT/"; else launch; fi; }
cmd_restart() { killall_server; launch; }
cmd_stop()    { killall_server; echo "Зупинено."; }
cmd_status()  { if is_up; then echo "ПРАЦЮЄ  PID $(port_pids)"; else echo "зупинено"; fi; }
cmd_log()     { tail -n "${1:-50}" -f "$LOG"; }

menu() {
  while true; do
    clear
    echo "=============================="
    echo "  qa_lab server (порт $PORT)"
    echo "=============================="
    cmd_status | sed 's/^/  статус: /'
    echo
    echo "  [1] Запустити"
    echo "  [2] Рестарт"
    echo "  [3] Зупинити"
    echo "  [4] Оновити статус"
    echo "  [5] Лог (Ctrl+C — вийти)"
    echo "  [0] Вийти"
    echo
    read -rp "Вибір: " choice
    case "$choice" in
      1) cmd_start;   read -rp "Enter..." _ ;;
      2) cmd_restart; read -rp "Enter..." _ ;;
      3) cmd_stop;    read -rp "Enter..." _ ;;
      4) : ;;
      5) cmd_log 50 || true ;;
      0) exit 0 ;;
    esac
  done
}

case "${1:-}" in
  start)   cmd_start ;;
  restart) cmd_restart ;;
  stop)    cmd_stop ;;
  status)  cmd_status ;;
  log)     cmd_log "${2:-50}" ;;
  "")      menu ;;
  *) echo "вживання: $0 [start|restart|stop|status|log]" >&2; exit 2 ;;
esac
