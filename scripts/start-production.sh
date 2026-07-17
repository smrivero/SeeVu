#!/bin/sh
set -e

BOT_PORT="${BOT_PORT:-7860}"
DASHBOARD_PORT="${PORT:-8080}"

echo "Starting voice bot on port ${BOT_PORT}..."
uv run bot.py --transport twilio --host 0.0.0.0 --port "${BOT_PORT}" &
BOT_PID=$!

echo "Starting dashboard on port ${DASHBOARD_PORT}..."
uv run server.py --host 0.0.0.0 --port "${DASHBOARD_PORT}" &
SERVER_PID=$!

cleanup() {
  kill "$BOT_PID" "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT TERM INT

wait "$SERVER_PID"
