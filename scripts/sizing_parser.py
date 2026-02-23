#!/usr/bin/env python3
"""Compatibility wrapper for the canonical sizing parser.

This tree historically had a duplicate `scripts/sizing_parser.py` implementation.
To prevent drift, this module delegates to the canonical parser at:
`<repo-root>/scripts/sizing_parser.py`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_canonical_parser_module() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[2]
    canonical_path = repo_root / "scripts" / "sizing_parser.py"

    spec = importlib.util.spec_from_file_location(
        "canonical_sizing_parser", canonical_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load canonical sizing parser at {canonical_path}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CANONICAL = _load_canonical_parser_module()

SizingReportParser = _CANONICAL.SizingReportParser
parse_sizing_file = _CANONICAL.parse_sizing_file


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 sizing_parser.py <sizing-report.md>")
        sys.exit(1)

    filepath = sys.argv[1]
    parser = SizingReportParser.from_file(filepath)
    data = parser.parse()

    print("=== Parsed Data ===")
    print(json.dumps(data, indent=2))

    print("\n=== Sizing Context ===")
    context = parser.to_sizing_context()
    print(json.dumps(context, indent=2))
