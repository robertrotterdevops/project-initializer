#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
OS="$(uname -s)"

case "$OS" in
  Darwin)
    exec "$ROOT_DIR/start-ui-macos.sh"
    ;;
  Linux)
    exec "$ROOT_DIR/start-ui-linux.sh"
    ;;
  *)
    echo "Unsupported OS: $OS"
    echo "Supported: macOS (Darwin), Linux"
    exit 1
    ;;
esac
