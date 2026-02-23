#!/usr/bin/env python3
"""Build backend executable for Tauri external bin.

Requires pyinstaller in active environment.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PI_ROOT = ROOT.parent
BACKEND = ROOT / "backend" / "run_backend.py"
TAURI_BIN_DIR = ROOT / "desktop" / "src-tauri" / "binaries"


def _target_suffix() -> str:
    if sys.platform == "darwin":
        return "aarch64-apple-darwin"
    if sys.platform.startswith("linux"):
        return "x86_64-unknown-linux-gnu"
    raise RuntimeError(f"Unsupported platform for packaging: {sys.platform}")


def main() -> None:
    TAURI_BIN_DIR.mkdir(parents=True, exist_ok=True)

    data_sep = os.pathsep
    add_data = [
        f"{PI_ROOT / 'scripts'}{data_sep}scripts",
        f"{PI_ROOT / 'addons'}{data_sep}addons",
        f"{PI_ROOT / 'templates'}{data_sep}templates",
        f"{PI_ROOT / 'priority_chains.json'}{data_sep}.",
        f"{PI_ROOT / 'priority_chains.yaml'}{data_sep}.",
        f"{ROOT / 'frontend'}{data_sep}ui-draft/frontend",
    ]

    hidden_imports = [
        "backend_api",
        "project_analyzer",
        "generate_structure",
        "sizing_parser",
        "addon_loader",
        "interactive",
    ]

    cmd = [
        "pyinstaller",
        "--onefile",
        "--name",
        "pi-backend",
        "--paths",
        str(PI_ROOT / "scripts"),
    ]

    for item in add_data:
        cmd.extend(["--add-data", item])

    for mod in hidden_imports:
        cmd.extend(["--hidden-import", mod])

    cmd.append(str(BACKEND))

    subprocess.run(cmd, cwd=str(ROOT), check=True)

    built = ROOT / "dist" / "pi-backend"
    if not built.exists():
        raise RuntimeError("Expected backend binary not found in dist/pi-backend")

    target = TAURI_BIN_DIR / f"pi-backend-{_target_suffix()}"
    shutil.copy2(built, target)
    print(f"Backend binary prepared: {target}")


if __name__ == "__main__":
    main()
