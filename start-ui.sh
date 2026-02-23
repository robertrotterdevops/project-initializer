#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

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

# Create venv if missing
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r ui-draft/requirements.txt

# Start web UI
echo ""
echo "Starting project-initializer UI..."
echo "Open http://localhost:8787 in your browser"
echo ""
exec uvicorn app:app --app-dir ui-draft/backend --reload --port 8787
