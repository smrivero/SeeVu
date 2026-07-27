#!/usr/bin/env bash
# Levanta / baja back (API + bot) y front (Vite) en local.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="${ROOT}/.dev"
LOG_DIR="${RUN_DIR}/logs"

API_PORT="${API_PORT:-8080}"
BOT_PORT="${BOT_PORT:-7860}"
FRONT_PORT="${FRONT_PORT:-5174}"

API_PID_FILE="${RUN_DIR}/api.pid"
BOT_PID_FILE="${RUN_DIR}/bot.pid"
FRONT_PID_FILE="${RUN_DIR}/front.pid"

mkdir -p "${LOG_DIR}"

# Cargar variables del .env si existe
if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ROOT}/.env"
  set +a
fi

SERVER_VENV="${ROOT}/.venv-server"

# Crea un venv liviano para server.py (evita arrastrar pipecat/llvmlite)
ensure_server_venv() {
  if [[ ! -x "${SERVER_VENV}/bin/python" ]]; then
    echo "Creando venv para server.py..."
    python3 -m venv "${SERVER_VENV}"
    "${SERVER_VENV}/bin/pip" install \
      "fastapi[standard]" "uvicorn[standard]" supabase openai \
      -q --disable-pip-version-check
    echo "  venv listo en ${SERVER_VENV}"
  fi
}

is_running() {
  local pid_file="$1"
  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}")"
    if kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
    rm -f "${pid_file}"
  fi
  return 1
}

kill_pid_file() {
  local name="$1"
  local pid_file="$2"
  if ! is_running "${pid_file}"; then
    echo "  ${name}: ya estaba abajo"
    return 0
  fi
  local pid
  pid="$(cat "${pid_file}")"
  kill "${pid}" 2>/dev/null || true
  # Esperar un poco; si no muere, forzar
  for _ in 1 2 3 4 5; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      break
    fi
    sleep 0.4
  done
  if kill -0 "${pid}" 2>/dev/null; then
    kill -9 "${pid}" 2>/dev/null || true
  fi
  # Matar hijos del process group si quedaron (uv/npm wrappers)
  pkill -P "${pid}" 2>/dev/null || true
  rm -f "${pid_file}"
  echo "  ${name}: detenido (pid ${pid})"
}

free_port() {
  local port="$1"
  local pids
  pids="$(lsof -ti tcp:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo "  Liberando puerto ${port}: ${pids}"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 0.5
    pids="$(lsof -ti tcp:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
    fi
  fi
}

cmd_start() {
  if is_running "${API_PID_FILE}" || is_running "${BOT_PID_FILE}" || is_running "${FRONT_PID_FILE}"; then
    echo "Ya hay procesos corriendo. Usá: ./dev.sh stop  o  ./dev.sh restart"
    cmd_status
    exit 1
  fi

  ensure_server_venv

  echo "Levantando SeeVu (local)..."
  echo "  API  → http://localhost:${API_PORT}"
  echo "  Bot  → ws://localhost:${BOT_PORT}/ws"
  echo "  Front→ http://localhost:${FRONT_PORT}"
  echo

  # API (dashboard / FastAPI) — venv liviano, sin pipecat/llvmlite
  (
    cd "${ROOT}"
    nohup "${SERVER_VENV}/bin/python" server.py --host 127.0.0.1 --port "${API_PORT}" \
      >"${LOG_DIR}/api.log" 2>&1 &
    echo $! >"${API_PID_FILE}"
  )
  echo "  API:  pid $(cat "${API_PID_FILE}")  (log: ${LOG_DIR}/api.log)"

  # Bot de voz — corre en Docker (uv run bot.py falla en Mac por llvmlite/numba)
  echo "  Bot:  verificando Docker..."
  if docker compose ps bot 2>/dev/null | grep -Eq "Up|running"; then
    echo "  Bot:  ya corre en Docker (:${BOT_PORT}) ✓"
  else
    echo "  Bot:  no está corriendo en Docker."
    echo "         Levantalo con:  docker compose up --build -d bot"
    echo "         Logs del build:  docker compose logs -f bot"
  fi

  # Frontend Vite
  (
    cd "${ROOT}/frontend"
    nohup npm run dev -- --host 127.0.0.1 --port "${FRONT_PORT}" \
      >"${LOG_DIR}/front.log" 2>&1 &
    echo $! >"${FRONT_PID_FILE}"
  )
  echo "  Front: pid $(cat "${FRONT_PID_FILE}") (log: ${LOG_DIR}/front.log)"
  echo
  echo "Listo. Abrí http://localhost:${FRONT_PORT}"
  echo "Para bajar todo: ./dev.sh stop"
}

cmd_stop() {
  echo "Bajando SeeVu..."
  kill_pid_file "API" "${API_PID_FILE}"
  kill_pid_file "Front" "${FRONT_PID_FILE}"
  free_port "${API_PORT}"
  free_port "${FRONT_PORT}"
  echo "  Bot: corre en Docker — usá 'docker compose stop bot' si querés bajarlo."
  echo "Todo abajo."
}

cmd_restart() {
  cmd_stop
  sleep 1
  cmd_start
}

cmd_status() {
  echo "Estado:"
  if is_running "${API_PID_FILE}"; then
    echo "  API:   UP  (pid $(cat "${API_PID_FILE}"), :${API_PORT})"
  else
    echo "  API:   DOWN"
  fi
  if docker compose ps bot 2>/dev/null | grep -Eq "Up|running"; then
    echo "  Bot:   UP  (Docker, :${BOT_PORT})"
  else
    echo "  Bot:   DOWN (Docker — corré: docker compose up --build -d bot)"
  fi
  if is_running "${FRONT_PID_FILE}"; then
    echo "  Front: UP  (pid $(cat "${FRONT_PID_FILE}"), :${FRONT_PORT})"
  else
    echo "  Front: DOWN"
  fi
}

cmd_logs() {
  local which="${1:-all}"
  case "${which}" in
    api|back)   tail -n 80 -f "${LOG_DIR}/api.log" ;;
    bot)        tail -n 80 -f "${LOG_DIR}/bot.log" ;;
    front|fe)   tail -n 80 -f "${LOG_DIR}/front.log" ;;
    all|*)
      echo "Logs en ${LOG_DIR}/ (Ctrl+C para salir)"
      tail -n 40 -f "${LOG_DIR}/api.log" "${LOG_DIR}/bot.log" "${LOG_DIR}/front.log"
      ;;
  esac
}

cmd_venv() {
  echo "Recreando venv de server.py..."
  rm -rf "${SERVER_VENV}"
  ensure_server_venv
  echo "Listo."
}

usage() {
  cat <<EOF
Uso: ./dev.sh <comando>

Comandos:
  start     Levanta API (:${API_PORT}), bot (:${BOT_PORT}) y front (:${FRONT_PORT})
  stop      Baja todo
  restart   stop + start
  status    Muestra si están corriendo
  logs      Sigue logs (opcional: api | bot | front)
  venv      Recrea el venv liviano de server.py

Puertos (override con env):
  API_PORT=${API_PORT}  BOT_PORT=${BOT_PORT}  FRONT_PORT=${FRONT_PORT}
EOF
}

case "${1:-}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_restart ;;
  status)  cmd_status ;;
  logs)    cmd_logs "${2:-all}" ;;
  venv)    cmd_venv ;;
  -h|--help|help|"") usage ;;
  *)
    echo "Comando desconocido: $1"
    usage
    exit 1
    ;;
esac
