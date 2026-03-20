#!/usr/bin/env python3
"""Typed sizing parse result models.

Lightweight stdlib-only dataclasses used by sizing_parser to expose
warnings/errors and a stable normalized view for downstream callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SizingMessage:
    code: str
    severity: str
    message: str
    field_path: Optional[str] = None


@dataclass(frozen=True)
class CanonicalSizingModel:
    schema_version: str
    source_format: str
    platform_detected: Optional[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    tiers: dict[str, dict[str, Any]] = field(default_factory=dict)
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    pools: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    platform_details: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


@dataclass(frozen=True)
class SizingParseResult:
    model: Optional[CanonicalSizingModel]
    addon_context: Optional[dict[str, Any]]
    warnings: tuple[SizingMessage, ...] = field(default_factory=tuple)
    fatal_error: Optional[SizingMessage] = None
