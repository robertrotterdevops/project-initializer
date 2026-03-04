#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
PORT="${PI_UI_PORT:-8787}"
HOST="${PI_UI_HOST:-0.0.0.0}"
AUTO_STOP_EXISTING="true"
STOP_ONLY="false"

while [ $# -gt 0 ]; do
  case "$1" in
    --stop-only)
      STOP_ONLY="true"
      ;;
    --no-stop-existing)
      AUTO_STOP_EXISTING="false"
      ;;
    --stop-existing)
      AUTO_STOP_EXISTING="true"
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: ./start-ui.sh [--stop-only] [--stop-existing|--no-stop-existing]"
      exit 1
      ;;
  esac
  shift
done

find_listener_pids() {
  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi
  lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true
}

stop_existing_listener() {
  local pids
  pids="$(find_listener_pids)"
  if [ -z "$pids" ]; then
    return 0
  fi

  echo "Port $PORT is in use by PID(s): $pids"
  echo "Stopping existing process(es)..."
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  sleep 1

  local remaining
  remaining="$(find_listener_pids)"
  if [ -n "$remaining" ]; then
    echo "Graceful stop did not complete, forcing stop for PID(s): $remaining"
    # shellcheck disable=SC2086
    kill -9 $remaining 2>/dev/null || true
    sleep 1
  fi
}

if [ "$STOP_ONLY" = "true" ]; then
  stop_existing_listener
  echo "Done. Listener on port $PORT is stopped."
  exit 0
fi

if [ "$AUTO_STOP_EXISTING" = "true" ]; then
  stop_existing_listener
else
  if [ -n "$(find_listener_pids)" ]; then
    echo "Error: port $PORT is already in use. Re-run with --stop-existing or --stop-only."
    exit 1
  fi
fi

# Check Python 3.9+
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is not installed."
  exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
  echo "Error: Python 3.9+ required (found $PY_VERSION)"
  exit 1
fi

# Create venv if missing or incomplete
if [ ! -f ".venv/bin/activate" ]; then
  echo "Creating virtual environment..."
  rm -rf .venv
  python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r ui-draft/requirements.txt

# Resolve display address
if [ "$HOST" = "0.0.0.0" ]; then
  if [ "$(uname)" = "Darwin" ]; then
    DISPLAY_IP="$(ipconfig getifaddr en0 2>/dev/null \
      || ipconfig getifaddr en1 2>/dev/null \
      || echo "localhost")"
  else
    DISPLAY_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")"
  fi
  [ -z "$DISPLAY_IP" ] && DISPLAY_IP="localhost"
else
  DISPLAY_IP="$HOST"
fi

# Start web UI
echo ""
echo "Starting project-initializer UI..."
echo "  Local:   http://localhost:$PORT"
echo "  Network: http://$DISPLAY_IP:$PORT"
echo ""
exec uvicorn app:app --app-dir ui-draft/backend --reload --host "$HOST" --port "$PORT"
