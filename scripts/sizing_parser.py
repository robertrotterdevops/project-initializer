#!/usr/bin/env python3
"""Sizing parser module.

This module provides parsing functionality for sizing reports.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


class SizingReportParser:
    """Parser for sizing report files."""

    def __init__(self, content: str, filepath: str | None = None):
        self.content = content
        self.filepath = filepath

    @classmethod
    def from_file(cls, filepath: str) -> SizingReportParser:
        path = Path(filepath)
        return cls(path.read_text(), str(path))

    def parse(self) -> dict[str, Any]:
        """Parse the sizing report content."""
        result: dict[str, Any] = {}
        lines = self.content.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                result[key.strip()] = value.strip()

        return result

    def to_sizing_context(self) -> dict[str, Any]:
        """Convert parsed data to sizing context format."""
        data = self.parse()
        return {
            "raw": data,
            "source": self.filepath,
        }


def parse_sizing_file(filepath: str) -> dict[str, Any]:
    """Parse a sizing file and return the result."""
    parser = SizingReportParser.from_file(filepath)
    return parser.to_sizing_context()


if __name__ == "__main__":
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
