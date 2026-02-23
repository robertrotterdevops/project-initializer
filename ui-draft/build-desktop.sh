#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UI_DIR="$ROOT_DIR/ui-draft"

cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r "$UI_DIR/requirements.txt"

if [ -f "$HOME/.cargo/env" ]; then
  source "$HOME/.cargo/env"
fi

cd "$UI_DIR/desktop"
npm install
npm run prepare:backend
npm run build
