#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_BIN="$ROOT_DIR/ui-draft/desktop/src-tauri/target/release/project_initializer_ui"

if [ -x "$APP_BIN" ]; then
  exec "$APP_BIN"
fi

echo "Linux desktop binary not found. Starting dev desktop mode..."
exec "$ROOT_DIR/ui-draft/run-desktop-dev.sh"
