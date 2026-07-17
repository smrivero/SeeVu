#!/bin/sh
set -e

BOT_PORT="${BOT_PORT:-7860}"
DASHBOARD_PORT="${PORT:-8080}"

echo "Dashboard will listen on 0.0.0.0:${DASHBOARD_PORT}"
echo "Bot will listen on 0.0.0.0:${BOT_PORT}"

# Dashboard primero: Railway healthcheck pasa antes de que el bot termine de cargar
echo "Starting dashboard..."
uv run server.py --host 0.0.0.0 --port "${DASHBOARD_PORT}" &
SERVER_PID=$!

sleep 2

echo "Starting voice bot..."
uv run bot.py --transport twilio --host 0.0.0.0 --port "${BOT_PORT}" &
BOT_PID=$!

cleanup() {
  kill "$SERVER_PID" "$BOT_PID" 2>/dev/null || true
}
trap cleanup EXIT TERM INT

wait "$SERVER_PID"
