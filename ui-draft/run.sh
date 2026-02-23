#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r ui-draft/requirements.txt

exec uvicorn app:app --app-dir ui-draft/backend --reload --host 0.0.0.0 --port 8787
