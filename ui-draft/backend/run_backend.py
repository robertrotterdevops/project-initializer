#!/usr/bin/env python3
"""Backend launcher for desktop packaging.

Starts the FastAPI app on localhost for Tauri frontend usage.
"""

from __future__ import annotations

import os

import uvicorn

from backend_api import app


def main() -> None:
    host = os.environ.get("PI_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("PI_UI_PORT", "8787"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
