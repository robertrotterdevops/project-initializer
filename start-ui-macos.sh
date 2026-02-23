#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_BIN="$ROOT_DIR/ui-draft/desktop/src-tauri/target/release/bundle/macos/Project Initializer.app/Contents/MacOS/project_initializer_ui"

needs_build="false"
if [ ! -x "$APP_BIN" ]; then
  needs_build="true"
else
  if ! ROOT_DIR="$ROOT_DIR" python3 - <<'PY'
import os
import pathlib
import sys

root = pathlib.Path(os.environ["ROOT_DIR"]).resolve()
app_bin = root / "ui-draft/desktop/src-tauri/target/release/bundle/macos/Project Initializer.app/Contents/MacOS/project_initializer_ui"

watch_roots = [
    root / "ui-draft/backend",
    root / "ui-draft/frontend",
    root / "ui-draft/desktop/src-tauri",
    root / "scripts",
]

if not app_bin.exists():
    sys.exit(1)

app_mtime = app_bin.stat().st_mtime
for watch_root in watch_roots:
    if not watch_root.exists():
        continue
    for p in watch_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix in {".py", ".rs", ".json", ".html", ".css", ".js", ".md"}:
            if p.stat().st_mtime > app_mtime:
                sys.exit(1)

sys.exit(0)
PY
  then
    needs_build="true"
  fi
fi

if [ "$needs_build" = "true" ]; then
  echo "Changes detected. Rebuilding desktop app..."
  "$ROOT_DIR/ui-draft/build-desktop.sh"
fi

# Avoid stale sidecar from previous runs.
pkill -f pi-backend >/dev/null 2>&1 || true

exec "$APP_BIN"
