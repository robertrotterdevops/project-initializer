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

from sizing_model import CanonicalSizingModel, SizingMessage, SizingParseResult


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


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        return value
    return None


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
# Context normalisation helpers
# ---------------------------------------------------------------------------

def _fmt_gi(value: float) -> str:
    v = int(round(value or 0))
    return f"{max(v, 0)}Gi"


def _fmt_cpu(value: float) -> str:
    v = value or 0
    iv = int(round(v))
    return str(max(iv, 0))


def _extract_health_score_markdown(content: str, summary: dict[str, Any]) -> int:
    m = re.search(r"Health Score:\s*([0-9]+)\s*/\s*100", content, re.IGNORECASE)
    if m:
        return int(m.group(1))
    for k, v in summary.items():
        if "health" in k.lower():
            m2 = re.search(r"([0-9]+)", str(v))
            if m2:
                return int(m2.group(1))
    return 0


def _extract_inputs_markdown(content: str) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    patterns = {
        "ingest_gb_per_day": r"Ingest per day:\s*\*\*([0-9.,]+)",
        "compression_factor": r"Compression factor:\s*\*\*([0-9.,]+)",
        "indexed_gb_per_day": r"Indexed per day:\s*\*\*([0-9.,]+)",
        "reserve_pct": r"Reserve:\s*\*\*([0-9.,]+)%",
        "total_retention_days": r"Total retention:\s*\*\*([0-9.,]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, content, re.IGNORECASE)
        if not m:
            continue
        val = _safe_float(m.group(1))
        if key == "reserve_pct":
            val = val / 100.0
        inputs[key] = val

    m = re.search(r"Workload type:\s*\*\*([^*]+)\*\*", content, re.IGNORECASE)
    if m:
        inputs["workload_type"] = m.group(1).strip().lower()
    return inputs


def _node_profile_from_tier_table(tier: dict[str, Any], snapshot_fallback: float = 0.0) -> dict[str, Any]:
    count = _safe_int(str(tier.get("Nr of nodes", "0")))
    memory = _safe_float(str(tier.get("RAM per node", tier.get("RAM per node (GB)", tier.get("RAM needed per node (GB)", "0")))))
    cpu = _safe_float(str(tier.get("vCPU per node", "0")))
    storage = _safe_float(str(tier.get("Disk per node", tier.get("Cache disk per node (GB)", "0"))))
    snapshot = _safe_float(str(tier.get("Snapshot repo storage (GB)", "0"))) or snapshot_fallback
    return {
        "count": count,
        "memory": _fmt_gi(memory),
        "cpu": _fmt_cpu(cpu),
        "storage": _fmt_gi(storage),
        "storage_class": "premium",
        "snapshot_storage_gb": snapshot,
    }


def _extract_rke2_markdown(content: str) -> dict[str, Any] | None:
    sec = re.search(r"##\s+RKE2/Kubernetes Deployment(.*?)(?:\n##\s+|\Z)", content, re.IGNORECASE | re.DOTALL)
    if not sec:
        return None
    chunk = sec.group(1)

    cluster: dict[str, Any] = {}
    for key, pat in {
        "worker_nodes_total": r"Worker nodes:\s*\*\*([0-9.,]+)",
        "control_plane_nodes_total": r"Control plane nodes:\s*\*\*([0-9.,]+)",
        "cluster_total_nodes": r"Total nodes:\s*\*\*([0-9.,]+)",
        "cluster_total_vcpu": r"Total vCPU:\s*\*\*([0-9.,]+)",
        "cluster_total_ram_gb": r"Total RAM:\s*\*\*([0-9.,]+)",
    }.items():
        m = re.search(pat, chunk, re.IGNORECASE)
        if m:
            cluster[key] = _safe_float(m.group(1))

    pools: list[dict[str, Any]] = []
    table_match = re.search(r"\|\s*Pool\s*\|.*?(?:\n\|.*)+", chunk, re.IGNORECASE)
    if table_match:
        table_lines = [ln.strip() for ln in table_match.group(0).splitlines() if ln.strip().startswith("|")]
        rows = _parse_md_table(table_lines)
        for row in rows:
            name = row.get("Pool", "").strip().lower().replace(" ", "_")
            pools.append({
                "name": name,
                "nodes": _safe_int(row.get("Nodes", "0")),
                "per_zone": [x for x in row.get("Per Zone", "").split("/") if x.strip()],
                "vcpu_per_node": _safe_float(row.get("vCPU/Node", "0")),
                "ram_gb_per_node": _safe_float(row.get("RAM/Node (GB)", "0")),
                "unschedulable_pods": _safe_int(row.get("Unschedulable Pods", "0")),
            })

    return {
        "cluster": {
            "distribution": "RKE2",
            "zones": 3,
            "control_plane_nodes": int(cluster.get("control_plane_nodes_total", 3) or 3),
            "ha_min_control_plane_nodes": 3,
        },
        "cluster_totals": cluster,
        "pools": pools,
    }


def _normalize_markdown_context(parser: SizingReportParser) -> dict[str, Any]:
    ctx = parser.to_sizing_context()
    raw = ctx.get("raw", {})
    tiers = raw.get("tiers", {})
    summary = raw.get("summary", {})

    hot = _node_profile_from_tier_table(tiers.get("hot", {}))
    cold = _node_profile_from_tier_table(tiers.get("cold", {}))
    frozen_snapshot = ctx.get("frozen_nodes", {}).get("snapshot_storage_gb", 0.0)
    frozen = _node_profile_from_tier_table(tiers.get("frozen", {}), snapshot_fallback=frozen_snapshot)

    ctx["source"] = "sizing_report"
    ctx["source_format"] = "markdown"
    ctx["health_score"] = _extract_health_score_markdown(parser.content, summary)
    ctx["inputs"] = _extract_inputs_markdown(parser.content)
    ctx["data_nodes"] = hot
    ctx["cold_nodes"] = cold
    ctx["frozen_nodes"] = frozen
    ctx.setdefault("master_nodes", {})
    ctx.setdefault("kibana", {})
    ctx.setdefault("fleet_server", {})
    ctx.setdefault("profile", "custom")

    rke2 = _extract_rke2_markdown(parser.content)
    if rke2:
        ctx["rke2"] = rke2
        if not ctx.get("platform_detected"):
            ctx["platform_detected"] = "rke2"

    return ctx


def _node_profile_from_contract_tier(tier: dict[str, Any]) -> dict[str, Any]:
    return {
        "count": int(tier.get("nodes", 0) or 0),
        "memory": _fmt_gi(float(tier.get("ram_gb_per_node") or 0)),
        "cpu": _fmt_cpu(float(tier.get("vcpu_per_node") or 0)),
        "storage": _fmt_gi(float(tier.get("disk_gb_per_node") or 0)),
        "storage_class": "premium",
        "snapshot_storage_gb": float(tier.get("snapshot_repo_total_gb") or 0),
    }


def _storage_class_for_platform(platform: str, rke2: dict[str, Any] | None = None) -> str:
    if platform == "rke2":
        profile = str(((rke2 or {}).get("storage") or {}).get("profile", "")).strip().lower().replace("_", "-")
        if profile in {"local-nvme", "local-ssd", "local-path"}:
            return "local-path"
    if platform == "openshift":
        return "standard"
    return "premium"


def _normalize_component(count: int, memory_gb: float, cpu: float) -> dict[str, Any]:
    return {
        "count": max(int(count or 0), 0),
        "memory": _fmt_gi(memory_gb),
        "cpu": _fmt_cpu(cpu),
    }


def _selector_tier_from_pool_name(pool_name: Any) -> str | None:
    raw = str(pool_name or "").strip().lower().replace("-", "_")
    if not raw:
        return None
    # System pool keeps an explicit "system" tier so Kibana/Fleet can target
    # dedicated system nodes independently from Elasticsearch master role.
    if "system" in raw:
        return "system"
    if raw.startswith("master") or "_master" in raw:
        return "master"
    if "infra" in raw:
        return "infra"
    if "hot" in raw:
        return "hot"
    if "cold" in raw:
        return "cold"
    if "frozen" in raw:
        return "frozen"
    return None


def _selector_for_tier_name(tier_name: str | None) -> dict[str, str] | None:
    if not tier_name:
        return None
    return {"elasticsearch.k8s.elastic.co/tier": tier_name}


def _choose_component_tier(candidates: list[str]) -> str | None:
    if not candidates:
        return None
    priority = {"system": 0, "master": 1, "infra": 2, "hot": 3, "cold": 4, "frozen": 5}
    ranked = [tier for tier in candidates if tier in priority]
    if not ranked:
        return None
    return sorted(ranked, key=lambda item: priority[item])[0]


def _enrich_rke2_pools_from_tiers(
    rke2_data: dict[str, Any], tier_map: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    pools = []
    disk_by_pool: dict[str, float] = {}
    for mapping in rke2_data.get("elastic_tier_to_pool", []) or []:
        tier_name = mapping.get("tier")
        pool_name = str(mapping.get("pool") or "").lower()
        tier = tier_map.get(str(tier_name or "").lower(), {})
        if not pool_name or not tier:
            continue
        disk_gb = float(tier.get("disk_gb_per_node") or 0)
        if disk_gb > 0:
            disk_by_pool[pool_name] = max(disk_by_pool.get(pool_name, 0.0), disk_gb)

    for pool in rke2_data.get("pools", []) or []:
        normalized = dict(pool)
        if not normalized.get("disk_gb_per_node"):
            pool_name = str(normalized.get("name", "")).lower()
            for tier_name, tier in tier_map.items():
                if tier_name and tier_name in pool_name:
                    inferred_disk = float(tier.get("disk_gb_per_node") or 0)
                    if inferred_disk > 0:
                        disk_by_pool[pool_name] = max(disk_by_pool.get(pool_name, 0.0), inferred_disk)
            inferred_disk = disk_by_pool.get(pool_name, 0.0)
            if inferred_disk > 0:
                normalized["disk_gb_per_node"] = int(round(inferred_disk))
        pools.append(normalized)

    enriched = dict(rke2_data)
    enriched["pools"] = pools
    return enriched


def _normalize_elastic_calc(
    calc: dict[str, Any], platform_value: str, platform_details: dict[str, Any] | None = None
) -> dict[str, Any]:
    tier_map = {
        str(t.get("name", "")).lower(): t
        for t in calc.get("tiers", []) or []
        if isinstance(t, dict)
    }
    summary_raw = dict(calc.get("summary", {}) or {})
    totals = summary_raw.get("totals", {}) or {}
    summary_raw.setdefault("total_nodes", summary_raw.get("total_nodes", totals.get("nodes", 0)))
    summary_raw.setdefault("total_data_nodes", summary_raw.get("total_data_nodes", totals.get("data_nodes", 0)))
    summary_raw["total_vcpu"] = _first_present(summary_raw.get("total_vcpu"), summary_raw.get("total_vcpu_selected"), totals.get("vcpu"), 0)
    summary_raw["total_ram_gb"] = _first_present(summary_raw.get("total_ram_gb"), summary_raw.get("total_ram_gb_selected"), totals.get("ram_gb"), 0)
    summary_raw["total_disk_gb"] = _first_present(summary_raw.get("total_disk_gb"), summary_raw.get("total_local_disk_gb_selected"), totals.get("local_disk_gb"), 0)
    summary_raw["total_snapshot_storage_gb"] = _first_present(summary_raw.get("total_snapshot_storage_gb"), totals.get("snapshot_storage_gb"), 0)

    inputs_raw = dict(calc.get("inputs", {}) or {})
    inputs_raw["ingest_per_day_gb"] = _first_present(inputs_raw.get("ingest_per_day_gb"), inputs_raw.get("ingest_gb_per_day"))
    inputs_raw["retention_days"] = _first_present(inputs_raw.get("retention_days"), inputs_raw.get("total_retention_days"))

    storage_class = _storage_class_for_platform(platform_value, platform_details)
    data_nodes = _node_profile_from_contract_tier(tier_map.get("hot", {}))
    cold_nodes = _node_profile_from_contract_tier(tier_map.get("cold", {}))
    frozen_nodes = _node_profile_from_contract_tier(tier_map.get("frozen", {}))
    for node_group in (data_nodes, cold_nodes, frozen_nodes):
        node_group["storage_class"] = storage_class

    return {
        "summary": summary_raw,
        "inputs": inputs_raw,
        "tier_map": tier_map,
        "data_nodes": data_nodes,
        "cold_nodes": cold_nodes,
        "frozen_nodes": frozen_nodes,
    }


def _normalize_platform_component_counts(platform_details: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], int]:
    def _component_count(value: Any) -> int:
        if isinstance(value, dict):
            return int(value.get("count") or value.get("pods") or value.get("replicas") or 0)
        return int(value or 0)

    stack_components = (platform_details.get("stack_components") or {}) or (
        (platform_details.get("overhead_breakdown") or {}).get("stack_components") or {}
    )
    pools = platform_details.get("pools", []) or []
    root_composition = platform_details.get("composition") or {}

    kibana_count = (
        _component_count(root_composition.get("kibana_pods"))
        or _component_count(root_composition.get("kibana"))
        or _component_count(root_composition.get("count"))
    )
    fleet_count = (
        _component_count(root_composition.get("fleet_pods"))
        or _component_count(root_composition.get("fleet"))
        or _component_count(root_composition.get("fleet_server"))
    )

    kibana_tier_candidates: list[str] = []
    fleet_tier_candidates: list[str] = []

    for pool in pools:
        comp = pool.get("composition") or {}
        pool_tier = _selector_tier_from_pool_name(pool.get("name"))
        kibana_in_pool = _component_count(comp.get("kibana_pods")) or _component_count(comp.get("kibana"))
        fleet_in_pool = (
            _component_count(comp.get("fleet_pods"))
            or _component_count(comp.get("fleet"))
            or _component_count(comp.get("fleet_server"))
        )

        if kibana_count == 0 and fleet_count == 0:
            kibana_count += kibana_in_pool
            fleet_count += fleet_in_pool

        if pool_tier and kibana_in_pool > 0:
            kibana_tier_candidates.append(pool_tier)
        if pool_tier and fleet_in_pool > 0:
            fleet_tier_candidates.append(pool_tier)

    shared_stack_cpu = float(stack_components.get("vcpu") or 0)
    shared_stack_ram = float(stack_components.get("ram_gb") or 0)
    total_components = max(kibana_count + fleet_count, 1)
    per_component_cpu = shared_stack_cpu / total_components if shared_stack_cpu else 2.0
    per_component_ram = shared_stack_ram / total_components if shared_stack_ram else 4.0

    kibana = _normalize_component(kibana_count, per_component_ram, per_component_cpu) if kibana_count > 0 else {}
    fleet = _normalize_component(fleet_count, per_component_ram, per_component_cpu) if fleet_count > 0 else {}

    kibana_selector = _selector_for_tier_name(_choose_component_tier(kibana_tier_candidates))
    if kibana and kibana_selector:
        kibana["node_selector"] = kibana_selector

    fleet_selector = _selector_for_tier_name(_choose_component_tier(fleet_tier_candidates))
    if fleet and fleet_selector:
        fleet["node_selector"] = fleet_selector

    return kibana, fleet, kibana_count + fleet_count


def _parse_json_contract(content: str) -> dict[str, Any]:
    data = json.loads(content)
    schema_version = data.get("schema_version")

    if schema_version == "es-sizing.v1":
        calc = data.get("calculation", {})
        tiers = {t.get("name"): t for t in calc.get("tiers", []) if isinstance(t, dict)}

        platform_value = (data.get("platform") or "").strip().lower()
        if platform_value in {"", "all"}:
            details = data.get("platform_details", {}) or {}
            for candidate in ("rke2", "openshift", "aks"):
                if details.get(candidate):
                    platform_value = candidate
                    break

        ctx: dict[str, Any] = {
            "source": "sizing_report",
            "source_format": "json_contract_v1",
            "raw": data,
            "platform_detected": platform_value or None,
            "metadata": data.get("project", {}) or {},
            "summary": calc.get("summary", {}) or {},
            "inputs": calc.get("inputs", {}) or {},
            "health_score": int((calc.get("summary", {}) or {}).get("cluster_health_score", 0) or 0),
            "profile": "custom",
            "data_nodes": _node_profile_from_contract_tier(tiers.get("hot", {})),
            "cold_nodes": _node_profile_from_contract_tier(tiers.get("cold", {})),
            "frozen_nodes": _node_profile_from_contract_tier(tiers.get("frozen", {})),
            "master_nodes": {},
            "kibana": {},
            "fleet_server": {},
        }

        platform_details = data.get("platform_details", {}) or {}
        if platform_details.get("aks"):
            ctx["aks"] = platform_details["aks"]
        if platform_details.get("openshift"):
            ctx["openshift"] = platform_details["openshift"]
        if platform_details.get("rke2"):
            ctx["rke2"] = platform_details["rke2"]

        return ctx

    if schema_version == "es-sizing-platform.v1":
        platform_value = (data.get("platform") or "").strip().lower() or None
        calc = data.get("calculation", {}) or {}
        platform_details = data.get("platform_details", {}) or {}
        elastic_ctx = _normalize_elastic_calc(calc, platform_value or "kubernetes", platform_details)
        kibana, fleet_server, _ = _normalize_platform_component_counts(platform_details)
        master_count = int((elastic_ctx["summary"].get("total_master_nodes") or 0))

        pools_source = platform_details.get("pools", []) or data.get("pool_composition", []) or []
        enriched_platform = _enrich_rke2_pools_from_tiers(
            {"pools": pools_source, **platform_details},
            elastic_ctx["tier_map"],
        )

        ctx = {
            "source": "sizing_report",
            "source_format": "json_contract_platform_v1",
            "raw": data,
            "platform_detected": platform_value,
            "metadata": data.get("project", {}) or {},
            "summary": elastic_ctx["summary"],
            "inputs": elastic_ctx["inputs"],
            "health_score": int(elastic_ctx["summary"].get("cluster_health_score", 0) or 0),
            "profile": "custom",
            "data_nodes": elastic_ctx["data_nodes"],
            "cold_nodes": elastic_ctx["cold_nodes"],
            "frozen_nodes": elastic_ctx["frozen_nodes"],
            "master_nodes": _normalize_component(master_count, 4.0, 2.0) if master_count > 0 else {},
            "kibana": kibana,
            "fleet_server": fleet_server,
        }

        if platform_value == "openshift":
            ctx["openshift"] = enriched_platform
            # Also expose generic pool composition for proxmox/rke2-style consumers.
            ctx["rke2"] = {"pools": enriched_platform.get("pools", [])}
        elif platform_value == "rke2":
            ctx["rke2"] = enriched_platform
        elif platform_value == "aks":
            ctx["aks"] = enriched_platform
        else:
            ctx["platform_details"] = enriched_platform

        return ctx

    if schema_version == "es-sizing-rke2.v1":
        platform_value = (data.get("platform") or "").strip().lower() or "rke2"
        elastic = data.get("elasticsearch", {}) or {}
        rke2_data = data.get("rke2", {}) or {}
        elastic_ctx = _normalize_elastic_calc(elastic, platform_value, rke2_data)
        enriched_rke2 = _enrich_rke2_pools_from_tiers(rke2_data, elastic_ctx["tier_map"])
        kibana, fleet_server, _ = _normalize_platform_component_counts(enriched_rke2)
        master_count = int(elastic_ctx["summary"].get("total_master_nodes", 0) or 0)

        ctx = {
            "source": "sizing_report",
            "source_format": "json_contract_rke2_v1",
            "raw": data,
            "platform_detected": platform_value,
            "metadata": data.get("project", {}) or {},
            "summary": elastic_ctx["summary"],
            "inputs": elastic_ctx["inputs"],
            "health_score": int(elastic_ctx["summary"].get("cluster_health_score", 0) or 0),
            "profile": "custom",
            "data_nodes": elastic_ctx["data_nodes"],
            "cold_nodes": elastic_ctx["cold_nodes"],
            "frozen_nodes": elastic_ctx["frozen_nodes"],
            "master_nodes": _normalize_component(master_count, 4.0, 2.0) if master_count > 0 else {},
            "kibana": kibana,
            "fleet_server": fleet_server,
            "rke2": enriched_rke2,
        }
        return ctx

    raise ValueError("Unsupported sizing contract schema_version")


# ---------------------------------------------------------------------------
# Public convenience function
# ---------------------------------------------------------------------------

def _canonical_model_from_context(
    ctx: dict[str, Any], schema_version: str, source_format: str
) -> CanonicalSizingModel:
    return CanonicalSizingModel(
        schema_version=schema_version,
        source_format=source_format,
        platform_detected=ctx.get("platform_detected"),
        metadata=ctx.get("metadata", {}) or {},
        inputs=ctx.get("inputs", {}) or {},
        summary=ctx.get("summary", {}) or {},
        tiers={
            "hot": ctx.get("data_nodes", {}) or {},
            "cold": ctx.get("cold_nodes", {}) or {},
            "frozen": ctx.get("frozen_nodes", {}) or {},
        },
        components={
            "master_nodes": ctx.get("master_nodes", {}) or {},
            "kibana": ctx.get("kibana", {}) or {},
            "fleet_server": ctx.get("fleet_server", {}) or {},
        },
        pools=tuple(((ctx.get("rke2") or {}).get("pools") or ((ctx.get("openshift") or {}).get("pools") or []))),
        platform_details=(
            ctx.get("rke2")
            or ctx.get("openshift")
            or ctx.get("aks")
            or ctx.get("platform_details")
            or {}
        ),
        raw=ctx.get("raw"),
    )


def _collect_parse_warnings(
    ctx: dict[str, Any], schema_version: str, source_format: str
) -> tuple[SizingMessage, ...]:
    warnings: list[SizingMessage] = []
    if source_format == "markdown":
        warnings.append(
            SizingMessage(
                code="legacy_markdown",
                severity="warning",
                message="Markdown sizing input is legacy. JSON contracts are preferred for more reliable scaffolding.",
            )
        )
    if not ctx.get("platform_detected"):
        warnings.append(
            SizingMessage(
                code="platform_missing",
                severity="warning",
                message="Could not confidently detect platform from sizing input.",
                field_path="platform_detected",
            )
        )
    if not (ctx.get("summary") or {}).get("total_nodes"):
        warnings.append(
            SizingMessage(
                code="summary_missing",
                severity="warning",
                message="Sizing summary is incomplete; downstream generators may rely on defaults.",
                field_path="summary.total_nodes",
            )
        )
    if not (ctx.get("data_nodes") or {}).get("count") and not (ctx.get("cold_nodes") or {}).get("count"):
        warnings.append(
            SizingMessage(
                code="tier_counts_empty",
                severity="warning",
                message="No hot/cold tier node counts were extracted from sizing input.",
                field_path="tiers",
            )
        )
    if schema_version == "es-sizing-platform.v1" and not (
        ((ctx.get("openshift") or {}).get("pools") or ((ctx.get("rke2") or {}).get("pools") or []))
    ):
        warnings.append(
            SizingMessage(
                code="pool_data_missing",
                severity="warning",
                message="Platform pool sizing was not extracted; Terraform may fall back to generic worker pools.",
                field_path="platform_details.pools",
            )
        )
    return tuple(warnings)


def parse_sizing_file_detailed(filepath: str) -> SizingParseResult:
    path = Path(filepath)
    try:
        content = path.read_text()
    except Exception as exc:
        return SizingParseResult(
            model=None,
            addon_context=None,
            fatal_error=SizingMessage("file_read_error", "error", f"Failed to read sizing file: {exc}", str(path)),
        )

    is_json_candidate = path.suffix.lower() == ".json" or content.lstrip().startswith("{")
    if is_json_candidate:
        try:
            raw = json.loads(content)
        except Exception as exc:
            return SizingParseResult(
                model=None,
                addon_context=None,
                fatal_error=SizingMessage("invalid_json", "error", f"Invalid sizing JSON: {exc}", str(path)),
            )
        schema_version = str(raw.get("schema_version") or "unknown")
        try:
            ctx = _parse_json_contract(content)
        except Exception as exc:
            return SizingParseResult(
                model=None,
                addon_context=None,
                fatal_error=SizingMessage(
                    "unsupported_schema",
                    "error",
                    f"Unsupported sizing contract: {schema_version} ({exc})",
                    "schema_version",
                ),
            )
        return SizingParseResult(
            model=_canonical_model_from_context(ctx, schema_version, "json"),
            addon_context=ctx,
            warnings=_collect_parse_warnings(ctx, schema_version, "json"),
        )

    parser = SizingReportParser(content, str(path))
    ctx = _normalize_markdown_context(parser)
    return SizingParseResult(
        model=_canonical_model_from_context(ctx, "markdown", "markdown"),
        addon_context=ctx,
        warnings=_collect_parse_warnings(ctx, "markdown", "markdown"),
    )

def parse_sizing_file(filepath: str) -> dict[str, Any]:
    """Parse a sizing file and return normalized sizing context for addons."""
    result = parse_sizing_file_detailed(filepath)
    if result.fatal_error is not None:
        raise ValueError(result.fatal_error.message)
    return result.addon_context or {}


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
