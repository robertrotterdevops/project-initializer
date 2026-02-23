#!/usr/bin/env python3
"""
Elasticsearch sizing skill integration addon for project-initializer.
Invokes the elasticsearch-openshift-sizing-assistant-legacy skill to generate
resource limits and capacity planning for ECK manifests.

This addon is designed to be run in interactive mode, as it may prompt for
sizing parameters if not provided in context.

Zero external dependencies -- Python 3.9+ stdlib only.
"""

import json
from typing import Any, Dict, Optional


ADDON_META = {
    "name": "sizing_integration",
    "version": "1.0",
    "description": "Elasticsearch sizing skill integration",
    "triggers": {"categories": ["elasticsearch"], "interactive_only": True},
    "priority": 5,  # Run early to provide sizing context to other addons
}


# Platform-to-skill mapping for platform-aware skill guide generation
PLATFORM_SKILL_MAP = {
    "aks": {
        "skill": "devops-02-2026",
        "platform_name": "Azure AKS",
        "note": "Includes Terraform/IaC patterns for AKS deployments with ECK operator",
    },
    "azure": {
        "skill": "devops-02-2026",
        "platform_name": "Azure AKS",
        "note": "Includes Terraform/IaC patterns for AKS deployments with ECK operator",
    },
    "openshift": {
        "skill": "elasticsearch-openshift-sizing-assistant-legacy",
        "platform_name": "OpenShift",
        "note": "OpenShift-specific sizing with Context7 MCP integration",
    },
    "ocp": {
        "skill": "elasticsearch-openshift-sizing-assistant-legacy",
        "platform_name": "OpenShift",
        "note": "OpenShift-specific sizing with Context7 MCP integration",
    },
    "rke2": {
        "skill": "devops-02-2026",
        "platform_name": "RKE2",
        "note": "RKE2-compatible deployment patterns",
    },
    "kubernetes": {
        "skill": "kubernetes-k8s-specialist",
        "platform_name": "Kubernetes",
        "note": "Generic Kubernetes deployment patterns",
    },
}


# Default sizing profiles for different cluster sizes (fallback when no sizing report)
SIZING_PROFILES = {
    "small": {
        "description": "Dev/test clusters (<50GB/day)",
        "data_nodes": {
            "count": 3,
            "memory": "4Gi",
            "cpu": "2",
            "storage": "50Gi",
            "storage_class": "standard",
        },
        "master_nodes": {
            "count": 3,
            "memory": "2Gi",
            "cpu": "1",
        },
        "ingest_nodes": {
            "count": 0,
        },
        "coordinating_nodes": {
            "count": 0,
        },
        "kibana": {
            "count": 1,
            "memory": "1Gi",
            "cpu": "0.5",
        },
    },
    "medium": {
        "description": "Production clusters (50-500GB/day)",
        "data_nodes": {
            "count": 6,
            "memory": "16Gi",
            "cpu": "4",
            "storage": "500Gi",
            "storage_class": "premium",
        },
        "master_nodes": {
            "count": 3,
            "memory": "4Gi",
            "cpu": "2",
        },
        "ingest_nodes": {
            "count": 2,
            "memory": "4Gi",
            "cpu": "2",
        },
        "coordinating_nodes": {
            "count": 2,
            "memory": "4Gi",
            "cpu": "2",
        },
        "kibana": {
            "count": 2,
            "memory": "2Gi",
            "cpu": "1",
        },
    },
    "large": {
        "description": "High-volume clusters (500GB-5TB/day)",
        "data_nodes": {
            "count": 12,
            "memory": "32Gi",
            "cpu": "8",
            "storage": "2Ti",
            "storage_class": "premium",
        },
        "master_nodes": {
            "count": 3,
            "memory": "8Gi",
            "cpu": "4",
        },
        "ingest_nodes": {
            "count": 4,
            "memory": "8Gi",
            "cpu": "4",
        },
        "coordinating_nodes": {
            "count": 4,
            "memory": "8Gi",
            "cpu": "4",
        },
        "kibana": {
            "count": 3,
            "memory": "4Gi",
            "cpu": "2",
        },
    },
    "enterprise": {
        "description": "Enterprise clusters (5TB+/day)",
        "data_nodes": {
            "count": 24,
            "memory": "64Gi",
            "cpu": "16",
            "storage": "4Ti",
            "storage_class": "premium",
        },
        "master_nodes": {
            "count": 3,
            "memory": "16Gi",
            "cpu": "8",
        },
        "ingest_nodes": {
            "count": 6,
            "memory": "16Gi",
            "cpu": "8",
        },
        "coordinating_nodes": {
            "count": 6,
            "memory": "16Gi",
            "cpu": "8",
        },
        "kibana": {
            "count": 3,
            "memory": "8Gi",
            "cpu": "4",
        },
    },
}


class SizingIntegrationGenerator:
    """Generates sizing configuration and capacity planning documentation."""
    
    def __init__(
        self,
        project_name: str,
        project_description: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.project_name = project_name
        self.description = project_description
        self.context = context or {}
        
        # Extract sizing context if already provided
        self.sizing_context = self.context.get("sizing_context") or {}
        
        # Detect platform from sizing_context (parsed from report) or context
        self.platform_detected = self.sizing_context.get("platform_detected")
        self.platform = self.platform_detected or self.context.get("platform", "kubernetes")
        
        # Check if we have actual sizing data from a sizing report
        self.has_sizing_report = self.sizing_context.get("source") == "sizing_report"
        
        if self.has_sizing_report:
            # Use actual data from sizing report
            self.profile_name = "custom"
            self.profile = self._build_profile_from_sizing_context()
        else:
            # Fall back to detected profile from description keywords
            self.profile_name = self._detect_profile()
            self.profile = SIZING_PROFILES.get(self.profile_name, SIZING_PROFILES["medium"])
    
    def _detect_profile(self) -> str:
        """Detect sizing profile from description keywords."""
        desc_lower = self.description.lower()
        
        # Check for explicit profile in context
        if self.sizing_context.get("profile"):
            return self.sizing_context["profile"]
        
        # Detect from description
        if any(kw in desc_lower for kw in ["enterprise", "5tb", "10tb", "large-scale"]):
            return "enterprise"
        elif any(kw in desc_lower for kw in ["large", "1tb", "2tb", "high-volume"]):
            return "large"
        elif any(kw in desc_lower for kw in ["medium", "production", "prod"]):
            return "medium"
        elif any(kw in desc_lower for kw in ["small", "dev", "test", "poc", "demo"]):
            return "small"
        
        return "medium"  # Default
    
    def _build_profile_from_sizing_context(self) -> Dict[str, Any]:
        """Build profile dict from actual sizing report data."""
        ctx = self.sizing_context
        
        # Build profile compatible with existing generators but with tier-based data
        profile = {
            "description": f"Custom sizing from report (Health: {ctx.get('health_score', 0)}/100)",
            "source": "sizing_report",
            "health_score": ctx.get("health_score", 0),
            "inputs": ctx.get("inputs", {}),
            # Tier-specific data
            "hot_tier": ctx.get("data_nodes", {}),
            "cold_tier": ctx.get("cold_nodes", {}),
            "frozen_tier": ctx.get("frozen_nodes", {}),
            # Stack components
            "fleet_server": ctx.get("fleet_server", {}),
            "summary": ctx.get("summary", {}),
            # Legacy fields for backward compatibility
            "data_nodes": {},
            "master_nodes": {},
            "ingest_nodes": {"count": 0},
            "coordinating_nodes": {"count": 0},
            "kibana": {},
        }
        
        # Map hot tier to data_nodes for backward compatibility
        hot = ctx.get("data_nodes", {})
        if hot:
            profile["data_nodes"] = {
                "count": hot.get("count", 3),
                "memory": hot.get("memory", "32Gi"),
                "cpu": hot.get("cpu", "8"),
                "storage": hot.get("storage", "1000Gi"),
                "storage_class": hot.get("storage_class", "premium"),
            }
        
        # Kibana
        kibana = ctx.get("kibana", {})
        if kibana:
            profile["kibana"] = {
                "count": kibana.get("count", 1),
                "memory": kibana.get("memory", "2Gi"),
                "cpu": kibana.get("cpu", "1"),
            }
        
        # Master nodes (if present, otherwise empty)
        master = ctx.get("master_nodes", {})
        if master and master.get("count", 0) > 0:
            profile["master_nodes"] = {
                "count": master.get("count", 3),
                "memory": master.get("memory", "4Gi"),
                "cpu": master.get("cpu", "2"),
            }
        else:
            # No dedicated masters
            profile["master_nodes"] = {"count": 0, "memory": "0Gi", "cpu": "0"}
        
        return profile
    
    def generate(self) -> Dict[str, str]:
        """Generate sizing configuration files."""
        files = {}
        
        # Sizing configuration
        files["sizing/config.json"] = self._generate_sizing_config()
        files["sizing/README.md"] = self._generate_sizing_readme()
        
        # Capacity planning Excel-compatible CSV
        files["sizing/capacity-planning.csv"] = self._generate_capacity_csv()
        
        # Platform-specific resource calculations
        files["sizing/resource-requirements.yaml"] = self._generate_resource_requirements()
        
        # Skill invocation guide
        files["sizing/SIZING_SKILL.md"] = self._generate_skill_guide()
        
        return files
    
    def _generate_sizing_config(self) -> str:
        """Generate sizing configuration JSON."""
        # Get platform-specific skill info for notes
        platform_key = self.platform.lower() if self.platform else "kubernetes"
        platform_info = PLATFORM_SKILL_MAP.get(platform_key, PLATFORM_SKILL_MAP["kubernetes"])
        skill_name = platform_info["skill"]
        
        if self.has_sizing_report:
            # Use actual data from sizing report - tier-based structure
            config = {
                "project": self.project_name,
                "profile": "custom",
                "source": "sizing_report",
                "health_score": self.sizing_context.get("health_score", 0),
                "platform": self.platform,
                "inputs": self.sizing_context.get("inputs", {}),
                "tiers": {
                    "hot": self.sizing_context.get("data_nodes", {}),
                    "cold": self.sizing_context.get("cold_nodes", {}),
                    "frozen": self.sizing_context.get("frozen_nodes", {}),
                },
                "kibana": self.sizing_context.get("kibana", {}),
                "fleet_server": self.sizing_context.get("fleet_server", {}),
                "summary": self.sizing_context.get("summary", {}),
                "generated_by": "project-initializer/sizing_integration",
                "notes": [
                    "Configuration derived from sizing report",
                    f"Use '{skill_name}' skill for re-sizing or adjustments",
                    "Memory: Allocate 50% of node memory to JVM heap (max 31GB)",
                    "Storage: Values include replicas and overhead calculations",
                ],
            }
        else:
            # Use profile-based config (fallback)
            config = {
                "project": self.project_name,
                "profile": self.profile_name,
                "profile_description": self.profile["description"],
                "platform": self.platform,
                "sizing": self.profile,
                "generated_by": "project-initializer/sizing_integration",
                "notes": [
                    "This is a baseline configuration - adjust based on actual workload",
                    f"Use '{skill_name}' skill for detailed sizing",
                    "Memory: Allocate 50% of node memory to JVM heap (max 31GB)",
                    "Storage: Plan for 2-3x data volume for replicas and overhead",
                ],
            }
        return json.dumps(config, indent=2)
    
    def _generate_sizing_readme(self) -> str:
        """Generate sizing documentation."""
        if self.has_sizing_report:
            return self._generate_tier_based_readme()
        else:
            return self._generate_profile_based_readme()
    
    def _generate_tier_based_readme(self) -> str:
        """Generate README from tier-based sizing data (from sizing report)."""
        ctx = self.sizing_context
        profile = self.profile
        summary = ctx.get("summary", {})
        inputs = ctx.get("inputs", {})
        
        # Platform info
        platform_info = PLATFORM_SKILL_MAP.get(self.platform, PLATFORM_SKILL_MAP["kubernetes"])
        platform_name = platform_info["platform_name"]
        recommended_skill = platform_info["skill"]
        
        # Helper to extract numeric value
        def extract_num(val, default=0):
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, str):
                return int(val.rstrip("GiTiBMK") or default)
            return default
        
        readme = f"""# Elasticsearch Cluster Sizing

## Profile: Custom (from Sizing Report)

{profile['description']}

## Source Data

| Metric | Value |
|--------|-------|
| Daily Ingestion | {inputs.get('ingest_per_day_gb', 'N/A')} GB/day |
| Retention Period | {inputs.get('retention_days', 'N/A')} days |
| Workload Type | {inputs.get('workload_type', 'mixed')} |
| Health Score | {ctx.get('health_score', 'N/A')}/100 |

## Platform: {platform_name}

This configuration is optimized for **{platform_name}** deployment.

## Tier Architecture

"""
        # Hot tier
        hot = ctx.get("data_nodes", {})
        if hot and hot.get("count", 0) > 0:
            mem = hot.get("memory", "32Gi")
            storage = hot.get("storage", "1000Gi")
            readme += f"""### Hot Tier (Primary Indexing)
- **Nodes**: {hot.get('count', 3)}
- **Memory**: {mem} per node
- **CPU**: {hot.get('cpu', '8')} cores per node
- **Storage**: {storage} per node ({hot.get('storage_class', 'premium')})
- **Role**: Active indexing, recent data queries

"""
        
        # Cold tier
        cold = ctx.get("cold_nodes", {})
        if cold and cold.get("count", 0) > 0:
            mem = cold.get("memory", "16Gi")
            storage = cold.get("storage", "2000Gi")
            readme += f"""### Cold Tier (Long-term Storage)
- **Nodes**: {cold.get('count', 3)}
- **Memory**: {mem} per node
- **CPU**: {cold.get('cpu', '4')} cores per node
- **Storage**: {storage} per node ({cold.get('storage_class', 'standard')})
- **Role**: Historical data, infrequent queries

"""
        
        # Frozen tier
        frozen = ctx.get("frozen_nodes", {})
        if frozen and frozen.get("count", 0) > 0:
            mem = frozen.get("memory", "32Gi")
            cache = frozen.get("cache_storage", "2400Gi")
            snapshot = frozen.get("snapshot_storage_gb", 0)
            readme += f"""### Frozen Tier (Searchable Snapshots)
- **Nodes**: {frozen.get('count', 1)}
- **Memory**: {mem} per node
- **CPU**: {frozen.get('cpu', '8')} cores per node
- **Cache Storage**: {cache} per node (local SSD)
- **Snapshot Repository**: {snapshot:,.0f} GB (remote object storage)
- **Role**: Archive data, on-demand queries via snapshots

"""
        
        # Stack components
        readme += """## Stack Components

"""
        # Kibana
        kibana = ctx.get("kibana", {})
        if kibana and kibana.get("count", 0) > 0:
            readme += f"""### Kibana
- **Instances**: {kibana.get('count', 1)}
- **Memory**: {kibana.get('memory', '4Gi')} per instance
- **CPU**: {kibana.get('cpu', '2')} cores per instance

"""
        
        # Fleet Server
        fleet = ctx.get("fleet_server", {})
        if fleet and fleet.get("count", 0) > 0:
            readme += f"""### Fleet Server
- **Instances**: {fleet.get('count', 1)}
- **Memory**: {fleet.get('memory', '4Gi')} per instance
- **CPU**: {fleet.get('cpu', '2')} cores per instance

"""
        
        # Summary totals
        readme += f"""## Resource Totals

| Resource | Total |
|----------|-------|
| Nodes | {summary.get('total_nodes', 'N/A')} |
| vCPU | {summary.get('total_vcpu', 'N/A')} cores |
| RAM | {summary.get('total_ram_gb', 'N/A')} GB |
| Local Disk | {summary.get('total_disk_gb', 'N/A')} GB |
"""
        
        # Add snapshot storage if frozen tier exists
        if frozen and frozen.get("snapshot_storage_gb", 0) > 0:
            readme += f"| Snapshot Storage | {frozen.get('snapshot_storage_gb', 0):,.0f} GB |\n"
        
        readme += f"""
## Re-sizing with AI Assistant

For adjustments or re-sizing, use the recommended skill:

```bash
# Load the sizing skill
load skill {recommended_skill}

# Example prompt:
# "Adjust sizing for increased ingestion to 400 GB/day"
```

## Capacity Planning Guidelines

### Tier Strategy
- **Hot**: 7-14 days of data, fastest queries
- **Cold**: 30-90 days, reduced resources, slower queries
- **Frozen**: 90+ days, minimal local storage, uses snapshots

### Memory Sizing
- JVM heap should be 50% of container memory (max 31GB heap)
- Hot tier: Higher memory for indexing performance
- Frozen tier: Memory for cache, not full dataset

### Storage Strategy
- Hot: Premium/SSD for write throughput
- Cold: Standard storage, larger capacity
- Frozen: Local cache + object storage (S3/Azure Blob/GCS)

---

*Generated by project-initializer sizing integration addon*
*Source: Sizing Report (Health Score: {ctx.get('health_score', 'N/A')}/100)*
"""
        return readme
    
    def _generate_profile_based_readme(self) -> str:
        """Generate README from profile-based sizing (fallback when no sizing report)."""
        profile = self.profile
        
        total_data_memory = int(profile["data_nodes"]["memory"].rstrip("Gi")) * profile["data_nodes"]["count"]
        total_master_memory = int(profile["master_nodes"]["memory"].rstrip("Gi")) * profile["master_nodes"]["count"]
        
        readme = f"""# Elasticsearch Cluster Sizing

## Profile: {self.profile_name.title()}

{profile['description']}

## Resource Summary

### Data Nodes
- **Count**: {profile['data_nodes']['count']} nodes
- **Memory**: {profile['data_nodes']['memory']} per node ({total_data_memory}Gi total)
- **CPU**: {profile['data_nodes']['cpu']} cores per node
- **Storage**: {profile['data_nodes']['storage']} per node
- **Storage Class**: {profile['data_nodes']['storage_class']}

### Master Nodes
- **Count**: {profile['master_nodes']['count']} nodes
- **Memory**: {profile['master_nodes']['memory']} per node ({total_master_memory}Gi total)
- **CPU**: {profile['master_nodes']['cpu']} cores per node

### Ingest Nodes
- **Count**: {profile['ingest_nodes']['count']} nodes
{self._format_node_resources(profile['ingest_nodes']) if profile['ingest_nodes']['count'] > 0 else '- *(Combined with data nodes for this profile)*'}

### Coordinating Nodes
- **Count**: {profile['coordinating_nodes']['count']} nodes
{self._format_node_resources(profile['coordinating_nodes']) if profile['coordinating_nodes']['count'] > 0 else '- *(Combined with data nodes for this profile)*'}

### Kibana
- **Count**: {profile['kibana']['count']} instances
- **Memory**: {profile['kibana']['memory']} per instance
- **CPU**: {profile['kibana']['cpu']} cores per instance

## Platform: {self.platform.upper()}

This configuration is optimized for **{self.platform}** deployment.

## Detailed Sizing with AI Assistant

For more detailed sizing based on specific workload requirements, use:

```bash
# Load the sizing skill in your AI assistant
load skill elasticsearch-openshift-sizing-assistant-legacy

# Provide your requirements:
# - Daily ingestion rate (GB/day)
# - Retention period (days)
# - Number of replicas
# - Query workload characteristics
```

## Capacity Planning Guidelines

### Memory Sizing
- JVM heap should be 50% of container memory (max 31GB heap)
- Leave headroom for OS caches and Lucene segments
- Data nodes: 32-64GB RAM typical for production

### Storage Sizing
- Raw data + replicas + 20% overhead
- Formula: `daily_rate * retention * (1 + replicas) * 1.2`
- Use premium/SSD storage for data nodes

### CPU Sizing
- Indexing-heavy: 4-8 cores per data node
- Query-heavy: 8-16 cores per data node
- Master nodes: 2-4 cores sufficient

---

*Generated by project-initializer sizing integration addon*
"""
        return readme
    
    def _format_node_resources(self, node: Dict[str, Any]) -> str:
        """Format node resources as markdown."""
        if "memory" not in node:
            return ""
        return f"- **Memory**: {node.get('memory', 'N/A')} per node\n- **CPU**: {node.get('cpu', 'N/A')} cores per node"
    
    def _generate_capacity_csv(self) -> str:
        """Generate capacity planning CSV."""
        if self.has_sizing_report:
            return self._generate_tier_based_csv()
        else:
            return self._generate_profile_based_csv()
    
    def _generate_tier_based_csv(self) -> str:
        """Generate CSV from tier-based sizing data (from sizing report)."""
        lines = ["Component,Count,Memory (Gi),CPU (cores),Storage (Gi),Notes"]
        
        # Helper to safely extract numeric value from string like "32Gi"
        def extract_num(val: str, default: int = 0) -> int:
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, str):
                return int(val.rstrip("GiTiBMK") or default)
            return default
        
        # Hot tier (data nodes)
        hot = self.sizing_context.get("data_nodes", {})
        if hot and hot.get("count", 0) > 0:
            mem = extract_num(hot.get("memory", "32Gi"), 32)
            storage = extract_num(hot.get("storage", "1000Gi"), 1000)
            cpu = hot.get("cpu", "8")
            lines.append(f"Hot Tier Nodes,{hot.get('count', 3)},{mem},{cpu},{storage},Primary indexing (hot tier)")
        
        # Cold tier
        cold = self.sizing_context.get("cold_nodes", {})
        if cold and cold.get("count", 0) > 0:
            mem = extract_num(cold.get("memory", "16Gi"), 16)
            storage = extract_num(cold.get("storage", "2000Gi"), 2000)
            cpu = cold.get("cpu", "4")
            lines.append(f"Cold Tier Nodes,{cold.get('count', 0)},{mem},{cpu},{storage},Long-term storage (cold tier)")
        
        # Frozen tier
        frozen = self.sizing_context.get("frozen_nodes", {})
        if frozen and frozen.get("count", 0) > 0:
            mem = extract_num(frozen.get("memory", "32Gi"), 32)
            cache = extract_num(frozen.get("cache_storage", "2400Gi"), 2400)
            cpu = frozen.get("cpu", "8")
            snapshot_gb = frozen.get("snapshot_storage_gb", 0)
            lines.append(f"Frozen Tier Nodes,{frozen.get('count', 0)},{mem},{cpu},{cache},Searchable snapshots (cache); snapshot repo: {snapshot_gb}GB")
        
        # Master nodes (if dedicated)
        master = self.sizing_context.get("master_nodes", {})
        if master and master.get("count", 0) > 0:
            mem = extract_num(master.get("memory", "4Gi"), 4)
            cpu = master.get("cpu", "2")
            lines.append(f"Master Nodes,{master.get('count', 0)},{mem},{cpu},10,Cluster coordination")
        
        # Kibana
        kibana = self.sizing_context.get("kibana", {})
        if kibana and kibana.get("count", 0) > 0:
            mem = extract_num(kibana.get("memory", "2Gi"), 2)
            cpu = kibana.get("cpu", "1")
            lines.append(f"Kibana,{kibana.get('count', 1)},{mem},{cpu},1,UI and visualization")
        
        # Fleet Server
        fleet = self.sizing_context.get("fleet_server", {})
        if fleet and fleet.get("count", 0) > 0:
            mem = extract_num(fleet.get("memory", "4Gi"), 4)
            cpu = fleet.get("cpu", "2")
            lines.append(f"Fleet Server,{fleet.get('count', 1)},{mem},{cpu},10,Agent management")
        
        # Totals row from summary
        summary = self.sizing_context.get("summary", {})
        if summary:
            lines.append(f"TOTAL,{summary.get('total_nodes', 0)},{summary.get('total_ram_gb', 0)},{summary.get('total_vcpu', 0)},{summary.get('total_disk_gb', 0)},Elasticsearch cluster totals")
        
        return "\n".join(lines)
    
    def _generate_profile_based_csv(self) -> str:
        """Generate CSV from profile-based sizing (fallback)."""
        profile = self.profile
        
        csv_lines = [
            "Component,Count,Memory (Gi),CPU (cores),Storage (Gi),Notes",
            f"Data Nodes,{profile['data_nodes']['count']},{profile['data_nodes']['memory'].rstrip('Gi')},{profile['data_nodes']['cpu']},{profile['data_nodes']['storage'].rstrip('GiTi')},Primary storage",
            f"Master Nodes,{profile['master_nodes']['count']},{profile['master_nodes']['memory'].rstrip('Gi')},{profile['master_nodes']['cpu']},10,Cluster coordination",
        ]
        
        if profile['ingest_nodes']['count'] > 0:
            csv_lines.append(
                f"Ingest Nodes,{profile['ingest_nodes']['count']},{profile['ingest_nodes']['memory'].rstrip('Gi')},{profile['ingest_nodes']['cpu']},10,Pipeline processing"
            )
        
        if profile['coordinating_nodes']['count'] > 0:
            csv_lines.append(
                f"Coordinating Nodes,{profile['coordinating_nodes']['count']},{profile['coordinating_nodes']['memory'].rstrip('Gi')},{profile['coordinating_nodes']['cpu']},10,Query routing"
            )
        
        csv_lines.append(
            f"Kibana,{profile['kibana']['count']},{profile['kibana']['memory'].rstrip('Gi')},{profile['kibana']['cpu']},1,UI and visualization"
        )
        
        return "\n".join(csv_lines)
    
    def _generate_resource_requirements(self) -> str:
        """Generate resource requirements YAML."""
        if self.has_sizing_report:
            return self._generate_tier_based_requirements()
        else:
            return self._generate_profile_based_requirements()
    
    def _generate_tier_based_requirements(self) -> str:
        """Generate resource requirements from tier-based sizing data."""
        summary = self.sizing_context.get("summary", {})
        hot = self.sizing_context.get("data_nodes", {})
        cold = self.sizing_context.get("cold_nodes", {})
        frozen = self.sizing_context.get("frozen_nodes", {})
        kibana = self.sizing_context.get("kibana", {})
        fleet = self.sizing_context.get("fleet_server", {})
        
        # Get platform info
        platform_key = self.platform.lower() if self.platform else "kubernetes"
        platform_info = PLATFORM_SKILL_MAP.get(platform_key, PLATFORM_SKILL_MAP["kubernetes"])
        
        yaml_content = f"""# Elasticsearch Cluster Resource Requirements
# Source: Sizing Report (Custom)
# Platform: {platform_info['platform_name']}
# Health Score: {self.sizing_context.get('health_score', 0)}/100

apiVersion: v1
kind: ConfigMap
metadata:
  name: es-sizing-config
  namespace: {self.project_name}
data:
  profile: "custom"
  source: "sizing_report"
  platform: "{self.platform}"
  
---
# Resource Totals (from sizing report)
#
# Total Nodes: {summary.get('total_nodes', 0)}
# Total vCPU: {summary.get('total_vcpu', 0)}
# Total RAM: {summary.get('total_ram_gb', 0)} GB
# Total Local Disk: {summary.get('total_disk_gb', 0)} GB
# Snapshot Storage: {frozen.get('snapshot_storage_gb', 0)} GB
#
# ============================================================
# Tier Breakdown
# ============================================================
#
# HOT TIER (primary indexing):
#   Nodes: {hot.get('count', 0)}
#   Memory: {hot.get('memory', 'N/A')} per node
#   CPU: {hot.get('cpu', 'N/A')} cores per node
#   Storage: {hot.get('storage', 'N/A')} per node
#
"""
        if cold and cold.get("count", 0) > 0:
            yaml_content += f"""# COLD TIER (long-term storage):
#   Nodes: {cold.get('count', 0)}
#   Memory: {cold.get('memory', 'N/A')} per node
#   CPU: {cold.get('cpu', 'N/A')} cores per node
#   Storage: {cold.get('storage', 'N/A')} per node
#
"""
        if frozen and frozen.get("count", 0) > 0:
            yaml_content += f"""# FROZEN TIER (searchable snapshots):
#   Nodes: {frozen.get('count', 0)}
#   Memory: {frozen.get('memory', 'N/A')} per node
#   CPU: {frozen.get('cpu', 'N/A')} cores per node
#   Cache Storage: {frozen.get('cache_storage', 'N/A')} per node
#   Snapshot Repository: {frozen.get('snapshot_storage_gb', 0)} GB (remote storage)
#
"""
        if kibana and kibana.get("count", 0) > 0:
            yaml_content += f"""# KIBANA:
#   Instances: {kibana.get('count', 1)}
#   Memory: {kibana.get('memory', 'N/A')} per instance
#   CPU: {kibana.get('cpu', 'N/A')} cores per instance
#
"""
        if fleet and fleet.get("count", 0) > 0:
            yaml_content += f"""# FLEET SERVER:
#   Instances: {fleet.get('count', 1)}
#   Memory: {fleet.get('memory', 'N/A')} per instance
#   CPU: {fleet.get('cpu', 'N/A')} cores per instance
#
"""
        yaml_content += """# ============================================================
# Use these values to request cluster resources from infrastructure team
# ============================================================
"""
        return yaml_content
    
    def _generate_profile_based_requirements(self) -> str:
        """Generate resource requirements from profile-based sizing (fallback)."""
        profile = self.profile
        
        yaml_content = f"""# Elasticsearch Cluster Resource Requirements
# Profile: {self.profile_name}
# Platform: {self.platform}

apiVersion: v1
kind: ConfigMap
metadata:
  name: es-sizing-config
  namespace: {self.project_name}
data:
  profile: "{self.profile_name}"
  
---
# Resource totals for capacity planning
# 
# Data Nodes:
#   Total Memory: {int(profile['data_nodes']['memory'].rstrip('Gi')) * profile['data_nodes']['count']}Gi
#   Total CPU: {int(profile['data_nodes']['cpu']) * profile['data_nodes']['count']} cores
#   Total Storage: {profile['data_nodes']['storage']} x {profile['data_nodes']['count']} nodes
#
# Master Nodes:
#   Total Memory: {int(profile['master_nodes']['memory'].rstrip('Gi')) * profile['master_nodes']['count']}Gi
#   Total CPU: {int(profile['master_nodes']['cpu']) * profile['master_nodes']['count']} cores
#
"""
        
        if profile['ingest_nodes']['count'] > 0:
            yaml_content += f"""# Ingest Nodes:
#   Total Memory: {int(profile['ingest_nodes']['memory'].rstrip('Gi')) * profile['ingest_nodes']['count']}Gi
#   Total CPU: {int(profile['ingest_nodes']['cpu']) * profile['ingest_nodes']['count']} cores
#
"""
        
        if profile['coordinating_nodes']['count'] > 0:
            yaml_content += f"""# Coordinating Nodes:
#   Total Memory: {int(profile['coordinating_nodes']['memory'].rstrip('Gi')) * profile['coordinating_nodes']['count']}Gi
#   Total CPU: {int(profile['coordinating_nodes']['cpu']) * profile['coordinating_nodes']['count']} cores
#
"""
        
        yaml_content += f"""# Kibana:
#   Total Memory: {int(profile['kibana']['memory'].rstrip('Gi')) * profile['kibana']['count']}Gi
#   Total CPU: {float(profile['kibana']['cpu']) * profile['kibana']['count']} cores

# Use these values to request cluster resources from infrastructure team
"""
        
        return yaml_content
    
    def _generate_skill_guide(self) -> str:
        """Generate guide for using the sizing skill (platform-aware)."""
        # Get platform-specific skill info
        platform_key = self.platform.lower() if self.platform else "kubernetes"
        platform_info = PLATFORM_SKILL_MAP.get(platform_key, PLATFORM_SKILL_MAP["kubernetes"])
        
        skill_name = platform_info["skill"]
        platform_name = platform_info["platform_name"]
        platform_note = platform_info["note"]
        
        # Build sizing status section if we have sizing report data
        sizing_status = ""
        if self.has_sizing_report:
            health = self.sizing_context.get("health_score", 0)
            inputs = self.sizing_context.get("inputs", {})
            sizing_status = f"""
## Current Sizing Status

This project was initialized with sizing data from a **sizing report**.

- **Health Score**: {health}/100
- **Detected Platform**: {platform_name}
- **Daily Ingestion**: {inputs.get('ingest_per_day_gb', 'N/A')} GB/day
- **Retention**: {inputs.get('retention_days', 'N/A')} days
- **Workload Type**: {inputs.get('workload_type', 'N/A')}

The sizing files in this directory reflect the calculated sizing from the report.
"""
        
        return f"""# Using the Elasticsearch Sizing Skill

This project was initialized with the **{self.profile_name}** sizing profile.
**Platform**: {platform_name}
{sizing_status}
For detailed, workload-specific sizing, invoke the sizing skill in your AI assistant.

## Recommended Skill: {skill_name}

> {platform_note}

### Load the Skill

```
load skill {skill_name}
```

### Provide Your Requirements

The skill needs these inputs:

1. **Daily Ingestion Rate**: How much data per day (GB/day)
2. **Retention Period**: How long to keep data (days)
3. **Number of Replicas**: Usually 1 for production (data x 2)
4. **Query Workload**: Light, moderate, or heavy
5. **Platform**: {platform_name}

### Example Prompt

```
I need sizing for an Elasticsearch cluster on {platform_name}:
- Ingestion: 200 GB/day
- Retention: 30 days
- Replicas: 1
- Query load: Moderate (10 concurrent users, dashboards)
- Use case: Application logs and APM data
```

### What You'll Get

- Node count and specifications per tier (hot/cold/frozen)
- Memory/CPU/storage per node
- JVM heap settings
- Storage class recommendations
- Resource requests/limits for ECK
- Capacity planning spreadsheet values
- Platform-specific infrastructure recommendations

## Current Configuration

The sizing files in this directory provide a starting point:

| File | Description |
|------|-------------|
| `config.json` | Machine-readable sizing config (tier-based) |
| `capacity-planning.csv` | Import into Excel for planning |
| `resource-requirements.yaml` | Kubernetes resource totals |

Adjust these values based on the sizing skill's recommendations.

---

*Generated by project-initializer*
*Platform: {platform_name}*
"""


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main(
    project_name: str,
    description: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Main entry point for the addon loader.
    
    Args:
        project_name: Name of the project
        description: Project description
        context: Additional context (platform, sizing_context, etc.)
    
    Returns:
        Dict of {filepath: content} for generated files
    """
    generator = SizingIntegrationGenerator(project_name, description, context)
    return generator.generate()


if __name__ == "__main__":
    # Test the generator
    files = main(
        "test-sizing-project",
        "Production Elasticsearch cluster for application logs",
        {"platform": "openshift"},
    )
    
    print("Generated files:")
    for filepath in sorted(files.keys()):
        print(f"  - {filepath}")
