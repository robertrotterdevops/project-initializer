#!/usr/bin/env python3
"""Sizing parser module.

Parses markdown sizing reports (elastic-sizing-format v1.0) and extracts
platform detection, node pool configurations, storage sizing, and project
metadata for use by addons like terraform_aks.py and platform_manifests.py.

Zero external dependencies -- Python 3.9+ stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Markdown table parser
# ---------------------------------------------------------------------------

def _parse_md_table(lines: list[str]) -> list[dict[str, str]]:
    """Parse a markdown table into a list of dicts keyed by header names.

    Expects the first line to be a header row separated by ``|`` and the
    second line to be a separator row (``|---|---|``).  Remaining lines
    are data rows.
    """
    if len(lines) < 3:
        return []

    # Extract header names
    headers = [h.strip() for h in lines[0].strip().strip("|").split("|")]

    # Skip separator line (line[1])
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        line = line.strip()
        if not line or not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        row = {}
        for idx, header in enumerate(headers):
            row[header] = cells[idx] if idx < len(cells) else ""
        rows.append(row)
    return rows


def _safe_float(val: str) -> float:
    """Extract a float from a string, stripping markdown bold and commas."""
    val = val.replace("**", "").replace(",", "").strip()
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val: str) -> int:
    return int(_safe_float(val))


# ---------------------------------------------------------------------------
# Pool name normalisation
# ---------------------------------------------------------------------------

_POOL_NAME_MAP = {
    "hot pool": "eshot",
    "cold pool": "escold",
    "frozen pool": "esfrozen",
    "warm pool": "eswarm",
    "system pool": "system",
    "ingest pool": "esingest",
    "ml pool": "esml",
}


def _normalize_pool_name(raw: str) -> str:
    """Map human-readable pool names to terraform_aks pool keys."""
    key = raw.lower().strip()
    if key in _POOL_NAME_MAP:
        return _POOL_NAME_MAP[key]
    # Strip trailing " pool" and spaces, lowercase
    return re.sub(r"\s+pool$", "", key).replace(" ", "")


# ---------------------------------------------------------------------------
# Platform detection from section headers
# ---------------------------------------------------------------------------

_PLATFORM_PATTERNS: list[tuple[str, str]] = [
    (r"##\s+AKS", "aks"),
    (r"##\s+.*AKS/ECK", "aks"),
    (r"##\s+.*Azure Kubernetes", "aks"),
    (r"##\s+OpenShift\b", "openshift"),
    (r"##\s+OCP\b", "openshift"),
    (r"##\s+RKE2\b", "rke2"),
    (r"##\s+Rancher\b", "rke2"),
]


def _detect_platform(content: str) -> str | None:
    for pattern, platform in _PLATFORM_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return platform
    return None


# ---------------------------------------------------------------------------
# SizingReportParser
# ---------------------------------------------------------------------------

class SizingReportParser:
    """Parser for elastic-sizing-format v1.0 markdown reports."""

    def __init__(self, content: str, filepath: str | None = None):
        self.content = content
        self.filepath = filepath

    @classmethod
    def from_file(cls, filepath: str) -> SizingReportParser:
        path = Path(filepath)
        return cls(path.read_text(), str(path))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> dict[str, Any]:
        """Parse the full sizing report and return structured data."""
        result: dict[str, Any] = {}

        result["metadata"] = self._extract_metadata()
        result["platform_detected"] = _detect_platform(self.content)

        # Tier calculations (raw data from the report)
        result["tiers"] = self._extract_tier_calculations()

        # AKS-specific node pool and resource data
        aks_data = self._extract_aks_data()
        if aks_data:
            result["aks"] = aks_data

        # OpenShift-specific data
        ocp_data = self._extract_openshift_data()
        if ocp_data:
            result["openshift"] = ocp_data

        # Frozen tier snapshot storage (cross-platform)
        result["frozen_nodes"] = self._extract_frozen_snapshot_storage()

        # Summary data
        result["summary"] = self._extract_summary()

        return result

    def to_sizing_context(self) -> dict[str, Any]:
        """Convert parsed data to sizing context format for addon consumption."""
        data = self.parse()
        # Flatten into the context dict expected by addons
        ctx: dict[str, Any] = {
            "source": "sizing_report",
            "raw": data,
            "platform_detected": data.get("platform_detected"),
            "metadata": data.get("metadata", {}),
            "tiers": data.get("tiers", {}),
            "frozen_nodes": data.get("frozen_nodes", {}),
            "summary": data.get("summary", {}),
        }
        if "aks" in data:
            ctx["aks"] = data["aks"]
        if "openshift" in data:
            ctx["openshift"] = data["openshift"]
        return ctx

    # ------------------------------------------------------------------
    # Metadata extraction  (**Key:** Value lines)
    # ------------------------------------------------------------------

    def _extract_metadata(self) -> dict[str, str]:
        meta: dict[str, str] = {}
        pattern = re.compile(r"^\*\*(.+?):\*\*\s*(.+)$")
        for line in self.content.splitlines():
            m = pattern.match(line.strip())
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                meta[key] = val
        return meta

    # ------------------------------------------------------------------
    # Tier calculations (HOT / COLD / FROZEN / WARM sections)
    # ------------------------------------------------------------------

    def _extract_tier_calculations(self) -> dict[str, dict[str, Any]]:
        tiers: dict[str, dict[str, Any]] = {}
        lines = self.content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            m = re.match(r"^##\s+(HOT|COLD|WARM|FROZEN)\s+Tier\s+Calculation", line, re.IGNORECASE)
            if m:
                tier_name = m.group(1).lower()
                # Find the table that follows
                j = i + 1
                table_lines: list[str] = []
                while j < len(lines):
                    l = lines[j].strip()
                    if l.startswith("|"):
                        table_lines.append(l)
                    elif table_lines:
                        break  # end of table
                    elif l.startswith("##"):
                        break  # next section
                    j += 1
                rows = _parse_md_table(table_lines)
                tier_data: dict[str, Any] = {}
                for row in rows:
                    param = row.get("Parameter", "").strip()
                    val = row.get("Value", "").strip().replace("**", "")
                    if param:
                        tier_data[param] = val
                tiers[tier_name] = tier_data
                i = j
                continue
            i += 1
        return tiers

    # ------------------------------------------------------------------
    # AKS data extraction
    # ------------------------------------------------------------------

    def _extract_aks_data(self) -> dict[str, Any] | None:
        """Extract AKS/ECK Deployment section data."""
        if not re.search(r"##\s+AKS", self.content, re.IGNORECASE):
            return None

        aks: dict[str, Any] = {}

        # Parse Node Configuration table
        node_pools = self._extract_node_config_table()
        if node_pools:
            aks["node_pools"] = node_pools

        # Parse Node Pools table for additional counts
        pool_counts = self._extract_node_pools_table()
        if pool_counts and node_pools:
            # Merge node counts from the Node Pools table
            count_map = {_normalize_pool_name(p["pool"]): p for p in pool_counts}
            for pool in aks["node_pools"]:
                extra = count_map.get(pool["name"], {})
                if "node_count" not in pool or pool["node_count"] == 0:
                    pool["node_count"] = extra.get("nodes", pool.get("node_count", 0))

        # Snapshot storage from Total AKS Resources
        snapshot_gb = self._extract_aks_snapshot_storage()
        if snapshot_gb:
            aks["storage"] = {"snapshot_storage_gb": snapshot_gb}

        # Input parameters (VM SKUs, headroom, etc.)
        aks["input_parameters"] = self._extract_aks_input_params()

        return aks if aks else None

    def _extract_node_config_table(self) -> list[dict[str, Any]]:
        """Parse the ### Node Configuration table."""
        lines = self.content.splitlines()
        pools: list[dict[str, Any]] = []
        i = 0
        while i < len(lines):
            if re.match(r"^###\s+Node Configuration", lines[i].strip(), re.IGNORECASE):
                # Collect table lines
                j = i + 1
                table_lines: list[str] = []
                while j < len(lines):
                    l = lines[j].strip()
                    if l.startswith("|"):
                        table_lines.append(l)
                    elif table_lines:
                        break
                    elif l.startswith("#"):
                        break
                    j += 1
                rows = _parse_md_table(table_lines)
                for row in rows:
                    pool_name_raw = row.get("Pool", "").strip()
                    if not pool_name_raw or pool_name_raw.startswith("**"):
                        continue  # skip total rows
                    name = _normalize_pool_name(pool_name_raw)
                    vm_size = row.get("VM SKU", "").strip()
                    vcpu = _safe_int(row.get("vCPU", "0"))
                    ram_gb = _safe_int(row.get("RAM (GB)", "0"))
                    disk_gb = _safe_int(row.get("Disk (GB)", "0"))
                    pools.append({
                        "name": name,
                        "vm_size": vm_size,
                        "vcpu": vcpu,
                        "ram_gb": ram_gb,
                        "disk_size_gb": disk_gb,
                        "node_count": 0,  # will be filled from Node Pools table
                    })
                break
            i += 1
        return pools

    def _extract_node_pools_table(self) -> list[dict[str, Any]]:
        """Parse the ### Node Pools table (has node counts)."""
        lines = self.content.splitlines()
        pools: list[dict[str, Any]] = []
        i = 0
        while i < len(lines):
            # Match "### Node Pools" but NOT "### Node Pools Configuration"
            if re.match(r"^###\s+Node Pools\s*$", lines[i].strip(), re.IGNORECASE):
                j = i + 1
                table_lines: list[str] = []
                while j < len(lines):
                    l = lines[j].strip()
                    if l.startswith("|"):
                        table_lines.append(l)
                    elif table_lines:
                        break
                    elif l.startswith("#"):
                        break
                    j += 1
                rows = _parse_md_table(table_lines)
                for row in rows:
                    pool_name_raw = row.get("Pool", "").strip()
                    if not pool_name_raw or pool_name_raw.startswith("**"):
                        continue
                    pools.append({
                        "pool": pool_name_raw,
                        "nodes": _safe_int(row.get("Nodes", "0")),
                        "pods": _safe_int(row.get("Pods", "0")),
                        "vcpu_per_node": _safe_int(row.get("vCPU/node", "0")),
                        "ram_per_node_gb": _safe_int(row.get("RAM/node (GB)", "0")),
                        "disk_per_node_gb": _safe_int(row.get("Disk/node (GB)", "0")),
                    })
                break
            i += 1
        return pools

    def _extract_aks_snapshot_storage(self) -> float:
        """Extract snapshot storage from Total AKS Resources section."""
        m = re.search(r"Snapshot Storage:\s*\*\*([0-9.,]+)\s*GB\*\*", self.content)
        if m:
            return _safe_float(m.group(1))
        # Fallback: from Summary section
        m = re.search(r"Total snapshot storage GB:\s*\*\*([0-9.,]+)\*\*", self.content)
        if m:
            return _safe_float(m.group(1))
        return 0.0

    def _extract_aks_input_params(self) -> dict[str, str]:
        """Extract ### Input Parameters table under AKS section."""
        lines = self.content.splitlines()
        params: dict[str, str] = {}
        i = 0
        in_aks = False
        while i < len(lines):
            line = lines[i].strip()
            if re.match(r"^##\s+AKS", line, re.IGNORECASE):
                in_aks = True
            elif line.startswith("## ") and in_aks:
                break  # left AKS section
            elif in_aks and re.match(r"^###\s+Input Parameters", line, re.IGNORECASE):
                j = i + 1
                table_lines: list[str] = []
                while j < len(lines):
                    l = lines[j].strip()
                    if l.startswith("|"):
                        table_lines.append(l)
                    elif table_lines:
                        break
                    elif l.startswith("#"):
                        break
                    j += 1
                rows = _parse_md_table(table_lines)
                for row in rows:
                    param = row.get("Parameter", "").strip()
                    val = row.get("Value", "").strip()
                    if param:
                        params[param] = val
                break
            i += 1
        return params

    # ------------------------------------------------------------------
    # OpenShift data extraction
    # ------------------------------------------------------------------

    def _extract_openshift_data(self) -> dict[str, Any] | None:
        """Extract OpenShift Worker Pools section data."""
        if not re.search(r"##\s+OpenShift", self.content, re.IGNORECASE):
            return None

        ocp: dict[str, Any] = {"worker_pools": [], "worker_config": []}
        lines = self.content.splitlines()
        i = 0
        in_ocp = False
        while i < len(lines):
            line = lines[i].strip()
            if re.match(r"^##\s+OpenShift", line, re.IGNORECASE):
                in_ocp = True
            elif line.startswith("## ") and in_ocp:
                break
            elif in_ocp and line.startswith("|"):
                # Collect table
                table_lines: list[str] = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i].strip())
                    i += 1
                rows = _parse_md_table(table_lines)
                for row in rows:
                    pool_name = row.get("Pool", row.get("Name", "")).strip()
                    if not pool_name or pool_name.startswith("**"):
                        continue
                    workers = _safe_int(row.get("Workers", row.get("Nodes", "0")))
                    vcpu = _safe_float(row.get("vCPU", row.get("vCPU/node", "0")))
                    ram = _safe_float(row.get("RAM (GB)", row.get("RAM/node (GB)", "0")))
                    ocp["worker_pools"].append({"name": pool_name, "workers": workers})
                    ocp["worker_config"].append({
                        "pool_name": pool_name,
                        "vcpu": vcpu,
                        "ram_gb": ram,
                    })
                continue
            i += 1

        return ocp if ocp["worker_pools"] else None

    # ------------------------------------------------------------------
    # Frozen snapshot storage (cross-platform)
    # ------------------------------------------------------------------

    def _extract_frozen_snapshot_storage(self) -> dict[str, float]:
        """Extract total snapshot storage for frozen tier."""
        total = 0.0
        # Sum from tier calculations
        tiers = self._extract_tier_calculations()
        for tier_name in ("frozen", "cold", "hot"):
            tier = tiers.get(tier_name, {})
            val = tier.get("Snapshot repo storage (GB)", "0")
            total += _safe_float(val)

        # Also check summary line
        m = re.search(r"Total snapshot storage GB:\s*\*\*([0-9.,]+)\*\*", self.content)
        if m:
            summary_total = _safe_float(m.group(1))
            if summary_total > total:
                total = summary_total

        return {"snapshot_storage_gb": total}

    # ------------------------------------------------------------------
    # Summary extraction
    # ------------------------------------------------------------------

    def _extract_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        lines = self.content.splitlines()
        in_summary = False
        for line in lines:
            stripped = line.strip()
            if re.match(r"^##\s+Summary", stripped, re.IGNORECASE):
                in_summary = True
                continue
            if in_summary and stripped.startswith("## "):
                break
            if in_summary and stripped.startswith("- "):
                m = re.match(r"^-\s+(.+?):\s*\*\*(.+?)\*\*", stripped)
                if m:
                    key = m.group(1).strip()
                    val = m.group(2).strip()
                    summary[key] = val
        return summary


# ---------------------------------------------------------------------------
# Public convenience function
# ---------------------------------------------------------------------------

def parse_sizing_file(filepath: str) -> dict[str, Any]:
    """Parse a sizing file and return the sizing context dict."""
    parser = SizingReportParser.from_file(filepath)
    return parser.to_sizing_context()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 sizing_parser.py <sizing-report.md>")
        sys.exit(1)

    filepath = sys.argv[1]
    parser = SizingReportParser.from_file(filepath)

    print("=== Parsed Data ===")
    data = parser.parse()
    print(json.dumps(data, indent=2, default=str))

    print("\n=== Sizing Context ===")
    context = parser.to_sizing_context()
    print(json.dumps(context, indent=2, default=str))
