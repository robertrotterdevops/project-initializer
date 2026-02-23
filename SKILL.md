---
name: project-initializer
description: Platform-agnostic project scaffolding with automatic skill assignment
license: MIT
compatibility:
  - opencode
  - claude
  - chatgpt
  - gemini
  - copilot
  - cursor
  - windsurf
  - aider
  - continue-dev
  - ollama
  - lm-studio
  - llama-cpp
  - any-llm
metadata:
  category: devops
  tags: [project-setup, scaffolding, agent-coordination, terraform, kubernetes, elasticsearch, gitops, fluxcd, argocd, eck, sizing, aks, azure]
  author: robert.rotter
  source: lm-studio-preset
  version: "1.9"
  last_updated: "2026-02-23"
---

# Skill: Project Initializer

## Description

A platform-agnostic project initialisation system that analyses project descriptions, assigns appropriate DevOps skills, and generates standardised project structures. Works from **any AI coding tool**, **any local LLM**, or **directly from the terminal** with zero external dependencies (Python 3.9+ stdlib only).

Supported project types: Elasticsearch, Kubernetes, Terraform, Azure, and GitOps (FluxCD / ArgoCD).

## What's New in v1.9

- **Polished Web UI** - Complete UI overhaul with dark/light theme matching professional DevOps tools
- **Sidebar Navigation** - Create, Analyze, Git Sync, Settings pages
- **Recent Projects** - Quick access to last 5 created projects  
- **Toast Notifications** - Success/error feedback
- **Path Filtering** - Target directory only shows user-accessible paths (excludes /root)
- **Drag-drop Sizing Upload** - Drop .md sizing files directly
- **Keyboard Zoom** - Cmd/Ctrl +/-/0 for zoom controls

### Quick Start (Web UI)

```bash
cd ~/.config/opencode/skills/project-initializer
python3 -m venv .venv
source .venv/bin/activate
pip install -r ui-draft/requirements.txt
uvicorn app:app --app-dir ui-draft/backend --reload --port 8787
```

Then open **http://localhost:8787**

## What's New in v1.8

- **AKS/ECK Deployment Parser** - New `_parse_aks_eck_deployment()` method parses the `## AKS/ECK Deployment` section format from sizing reports
- **Auto Platform Detection** - Sizing parser now sets `platform_detected: "aks"` when AKS/ECK sections are found, automatically triggering the terraform_aks addon
- **End-to-End Sizing Flow** - One sizing file now generates both ECK manifests AND properly-sized Terraform AKS modules automatically
- **Fixed terraform_aks Context** - Addon now correctly reads from `context.get("sizing_context", {}).get("aks")` instead of `context.get("aks")`
- **VM Size Auto-Selection** - Automatic Azure VM size selection based on RAM/vCPU from sizing tables (E-series for memory, D-series for balanced)

### AKS/ECK Section Format Support

The parser now handles this table format from ES sizing reports:

```markdown
## AKS/ECK Deployment

### Node Pools
| Pool | Pods | Nodes | Per Zone | vCPU/node | RAM/node (GB) | Disk/node (GB) |
|---|---:|---:|---|---:|---:|---:|
| Hot Pool | 5 | 3 | 1/1/1 | 16 | 64 | 0 |
| Cold Pool | 8 | 6 | 2/2/2 | 16 | 64 | 0 |
```

## What's New in v1.7

- **Azure/AKS Sizing Integration** - Sizing parser now auto-generates AKS infrastructure recommendations from ES sizing reports
- **Terraform AKS Sizing** - terraform_aks addon uses sizing_context for properly-sized node pools, networking, and storage
- **Auto VM Size Selection** - Automatic Azure VM size selection based on ES tier requirements (E-series for hot, L-series for cold)
- **Frozen Tier Support** - Full frozen tier support in Terraform AKS modules with cache disk sizing
- **Storage Account Sizing** - Storage module selects tier (Hot/Cool) and replication (LRS/ZRS) based on snapshot storage requirements
- **Extended MD Format** - Sizing reports can include explicit `## Azure Infrastructure Recommendations` section for override

## What's New in v1.6

- **FluxCD Default** - FluxCD addon now loads by default for all platforms (not just when explicitly selected)
- **Improved ECK Structure** - Kibana moved to `kibana/` folder, agents to `agents/` folder with fleet-server.yaml, elastic-agent.yaml, rbac.yaml
- **Default Tier Templates** - ES cluster.yaml now includes commented warm/cold/frozen tier examples for easy customization
- **Terraform AKS Modules** - New addon generates complete Terraform module structure for AKS: aks, networking, storage, acr, monitoring
- **RKE2+AKS Pattern** - Platform detection updated to support RKE2 combined with Azure/AKS deployments

## What's New in v1.5

- **`--sizing-file` Flag** - Parse ES sizing report markdown files directly
- **Multi-Tier ECK Manifests** - Generate hot/cold/frozen tier node sets from sizing reports
- **Sizing Report Parser** - `scripts/sizing_parser.py` extracts all tiers from sizing assistant output
- **ILM Policy Selection** - Auto-select `hot-cold-frozen` ILM for multi-tier clusters
- **Enhanced README** - Generated README includes sizing source, health score, and node configuration table

## What's New in v1.4

- **`--git-init` Flag** - Automatically initialize a git repository with initial commit
- **`.opencode/context.md`** - Session bootstrap file with skill load commands and project config
- **Sizing Integration Addon** - Elasticsearch sizing profiles (small/medium/large/enterprise) with capacity planning CSV
- **Improved Sizing Detection** - Auto-detect cluster size from project description keywords

## What's New in v1.3

- **Addon Autodiscovery System** - Addons are now automatically discovered and matched based on project analysis, platform, and GitOps tool selection
- **Platform-Specific Manifests** - Generate RKE2, OpenShift, or AKS configurations
- **ECK 2.x Deployment Generator** - Complete ECK manifests for Elasticsearch 8.x clusters
- **ArgoCD Addon** - Full ArgoCD Application and AppProject generation with app-of-apps pattern
- **Improved GitOps Selection** - Exclusive addon loading based on selected GitOps tool

## CLI Usage

All functionality is exposed through a single CLI script. No Python API to learn -- just run it.

### Interactive Mode (Recommended)

The easiest way to create a new project is interactive mode:

```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py --interactive
# or
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py -i
```

Interactive mode guides you through:
1. **Project name** - kebab-case recommended
2. **Description** - used for type detection
3. **Type confirmation** - accept or override detected type
4. **Platform selection** - RKE2, OpenShift 4.x, or AKS (all with ECK)
5. **GitOps tool** - FluxCD, ArgoCD, or None
6. **ES sizing wizard** - optional, invokes sizing skill
7. **Target directory** - where to create the project

### Standard CLI Mode

```bash
SKILL_DIR=~/.config/opencode/skills/project-initializer

# Full project initialisation (auto-detects type from description)
python3 $SKILL_DIR/scripts/init_project.py \
  --name my-elastic-platform \
  --desc "Elasticsearch cluster on OpenShift with Terraform"

# Force a specific project type
python3 $SKILL_DIR/scripts/init_project.py \
  --name my-gitops-repo \
  --desc "FluxCD GitOps platform for multi-cluster" \
  --type gitops

# Preview skill assignments without creating files
python3 $SKILL_DIR/scripts/init_project.py \
  --name my-project \
  --desc "Kubernetes platform with monitoring" \
  --analyze-only

# Machine-readable JSON output
python3 $SKILL_DIR/scripts/init_project.py \
  --name my-project \
  --desc "Azure AKS infrastructure" \
  --analyze-only --json

# Specify target directory
python3 $SKILL_DIR/scripts/init_project.py \
  --name my-project \
  --desc "Terraform modules for networking" \
  --target /path/to/output

# Force a specific priority chain
python3 $SKILL_DIR/scripts/init_project.py \
  --name my-project \
  --desc "Platform engineering" \
  --chain gitops_focused
```

### CLI Options

| Option | Required | Description |
|--------|----------|-------------|
| `--interactive`, `-i` | No | Run in interactive mode with guided prompts |
| `--name NAME` | Yes* | Project name (kebab-case recommended) |
| `--desc DESC` | Yes* | Short project description |
| `--type TYPE` | No | Force type: elasticsearch, kubernetes, terraform, azure, gitops |
| `--target DIR` | No | Output directory (default: `./<name>`) |
| `--analyze-only` | No | Print assignments without creating files |
| `--chain CHAIN` | No | Force a specific priority chain |
| `--json` | No | Machine-readable JSON output |
| `--git-init` | No | Initialize git repository with initial commit |
| `--sizing-file FILE` | No | Path to ES sizing report markdown file |

*Required in standard mode, not needed in interactive mode.

## Target Platforms

The skill supports Elasticsearch cluster deployment on these platforms:

| Platform | Description |
|----------|-------------|
| **RKE2 + ECK** | Rancher Kubernetes Engine 2 |
| **OpenShift 4.x + ECK** | Red Hat OpenShift Container Platform |
| **AKS + ECK** | Azure Kubernetes Service |

## GitOps Tools

| Tool | Description |
|------|-------------|
| **FluxCD** | Recommended - GitOps with Flux controllers |
| **ArgoCD** | Alternative - GitOps with Argo Application CRDs |
| **None** | Raw Kubernetes manifests only |

## ES Sizing Integration

The skill supports two modes of ES sizing:

### 1. Sizing Report File (Recommended)

Pass a sizing report markdown file from `elasticsearch-openshift-sizing-assistant-legacy`:

```bash
python3 $SKILL_DIR/scripts/init_project.py \
  --name skane-es-cluster \
  --desc "Production ES cluster for Skane region" \
  --sizing-file /path/to/es-sizing-report.md \
  --git-init
```

The parser extracts:
- **Hot tier**: Node count, RAM, CPU, storage
- **Cold tier**: Node count, RAM, CPU, storage  
- **Frozen tier**: Node count, RAM, CPU, cache storage
- **Master nodes**: Node count, RAM, CPU
- **Kibana**: Instance count, RAM, CPU
- **Fleet Server**: Instance count, RAM, CPU
- **Health score**: Overall sizing validation score
- **AKS/ECK pools**: Node pools with vCPU, RAM, and zone distribution (v1.8)

### Supported Sizing Report Formats

The parser supports multiple section formats:

| Section | Format | Version |
|---------|--------|---------|
| `### Hot Tier` | Standard ES tier table | v1.5+ |
| `### Cold Tier` | Standard ES tier table | v1.5+ |
| `### Frozen Tier` | Standard ES tier table | v1.5+ |
| `## Azure Infrastructure Recommendations` | Explicit AKS config | v1.7+ |
| `## AKS/ECK Deployment` | Node pools table | v1.8+ |

### Auto Platform Detection (v1.8)

When using `--sizing-file`, the parser automatically detects the target platform:

```bash
# This command auto-detects platform=aks from the sizing file
python3 $SKILL_DIR/scripts/init_project.py \
  --name skane-es-cluster \
  --desc "Production ES cluster" \
  --sizing-file /path/to/sizing-with-aks-section.md
```

Output:
```
Sizing file: /path/to/sizing-with-aks-section.md
Platform detected: AKS
Generating project structure...
```

This generates **multi-tier ECK manifests** with:
- Separate node sets for hot/cold/frozen tiers
- Correct `node.roles` and `node.attr.data` attributes
- Tier-appropriate storage classes (premium for hot, standard for cold/frozen)
- `hot-cold-frozen` ILM policy for searchable snapshots

### 2. Interactive Sizing Wizard

In interactive mode, the skill can invoke the `elasticsearch-openshift-sizing-assistant-legacy` skill to:
- Calculate cluster sizing based on ingestion rate and retention
- Generate resource requests/limits for ECK manifests
- Recommend node counts and storage configurations

### 3. Azure/AKS Infrastructure from Sizing (v1.7)

When using `--sizing-file`, the parser also generates Azure/AKS infrastructure recommendations:

```python
# The sizing_context["aks"] structure:
{
    "node_pools": [
        {"name": "system", "vm_size": "Standard_D2s_v5", "node_count": 3, "disk_size_gb": 128},
        {"name": "eshot", "vm_size": "Standard_E8s_v5", "node_count": 11, "disk_size_gb": 256},
        {"name": "escold", "vm_size": "Standard_E4s_v5", "node_count": 23, "disk_size_gb": 256},
        {"name": "esfrozen", "vm_size": "Standard_E8s_v5", "node_count": 5, "disk_size_gb": 2400},
    ],
    "storage": {
        "snapshot_storage_gb": 303000,
        "storage_tier": "hot",
    },
    "networking": {
        "vnet_cidr": "10.0.0.0/16",
        "aks_subnet_cidr": "10.0.0.0/17",
    },
    "generated": True,  # True if auto-generated, False if from explicit section
}
```

This enables **ONE sizing report** to generate **BOTH**:
- **ECK manifests** (sized correctly with multi-tier node sets)
- **Terraform AKS modules** (sized correctly with proper VM sizes and node counts)

### Extended Sizing Report Format (Optional)

You can add an explicit Azure section to your sizing report for full control:

```markdown
## Azure Infrastructure Recommendations

### AKS Node Pools
| Pool | VM Size | Node Count | Disk Size | Purpose |
|------|---------|------------|-----------|---------|
| system | Standard_D2s_v5 | 3 | 128 GB | System workloads |
| eshot | Standard_E8s_v5 | 11 | 256 GB | ES Hot tier |
| escold | Standard_E4s_v5 | 23 | 256 GB | ES Cold tier |
| esfrozen | Standard_E8s_v5 | 5 | 2400 GB | ES Frozen tier |

### Storage
- Snapshot Storage Account: **303 TB** (ZRS recommended)
- Storage Tier: **Hot**

### Networking
- VNet CIDR: **10.0.0.0/16**
- AKS Subnet: **10.0.0.0/17**

### Estimated Monthly Cost
- AKS Node Pools: **$8,500**
- Storage: **$2,000**
- Total: **$10,500**
```

If this section exists, the parser uses it directly. Otherwise, it auto-generates from ES sizing.

## Project Type Detection

The tool scans the project name and description for keywords and selects the best-matching category:

| Category | Keywords |
|----------|----------|
| **elasticsearch** | elasticsearch, es, eck, elastic, kibana, logstash, beats, observability, logging, metrics, apm |
| **kubernetes** | kubernetes, k8s, openshift, container, pod, deployment, service, ingress, helm, operator |
| **terraform** | terraform, iac, infrastructure, provisioning, cloud |
| **azure** | azure, aks, azurekubernetesservice, microsoft |
| **gitops** | fluxcd, flux, gitops, kustomize, helmrelease, argocd, gitrepository, kustomization |

## Priority Chains

Each detected category maps to a priority chain that determines skill assignment order:

| Chain | Skill Order |
|-------|-------------|
| `default` (elasticsearch) | devops-02-2026 > kubernetes-k8s-specialist > platform-engineering > devops-general |
| `kubernetes_first` | kubernetes-k8s-specialist > platform-engineering > devops-02-2026 > devops-general |
| `terraform_first` | devops-general > kubernetes-k8s-specialist > platform-engineering > devops-02-2026 |
| `azure_focused` | devops-general > kubernetes-k8s-specialist > platform-engineering > devops-02-2026 |
| `openshift_focused` | kubernetes-k8s-specialist > platform-engineering > devops-02-2026 > devops-general |
| `gitops_focused` | platform-engineering > devops-general > kubernetes-k8s-specialist > devops-02-2026 |

## Generated Project Structure

Each project type generates a tailored directory layout:

### Elasticsearch
```
project/
├── README.md, AGENTS.md, .gitignore
├── terraform/          # IaC (includes AKS modules if platform=aks)
├── k8s/                # Kubernetes manifests
├── observability/      # Monitoring and logging
├── elasticsearch/      # ECK cluster manifests
│   ├── namespace.yaml
│   ├── cluster.yaml    # With commented warm/cold/frozen tiers
│   ├── kustomization.yaml
│   ├── ilm-policies/
│   └── index-templates/
├── kibana/             # Kibana manifests
│   ├── kibana.yaml
│   └── kustomization.yaml
└── agents/             # Elastic Agent manifests
    ├── fleet-server.yaml
    ├── elastic-agent.yaml
    ├── rbac.yaml
    └── kustomization.yaml
```

### Kubernetes
```
project/
├── terraform/, k8s/
├── cluster/            # Cluster provisioning
├── platform-services/  # Monitoring, logging, security
└── applications/       # Application deployments
```

### GitOps (FluxCD / ArgoCD)
```
project/
├── clusters/           # Per-cluster FluxCD config
├── infrastructure/     # Shared infra components
├── apps/               # Application definitions
├── flux-system/        # FluxCD bootstrap
├── base/               # Kustomize bases
└── overlays/           # Per-env overlays
```

### Terraform
```
project/
├── terraform/, modules/, environments/, networking/
```

### Azure / AKS
```
project/
├── terraform/
│   ├── main.tf, variables.tf, outputs.tf, providers.tf
│   └── modules/
│       ├── aks/           # AKS cluster with ES-optimized node pools
│       ├── networking/    # VNet, subnets, NSGs
│       ├── storage/       # Storage account for ES snapshots
│       ├── acr/           # Azure Container Registry
│       └── monitoring/    # Log Analytics, Azure Monitor
```

## Template Variables

Templates use simple `{{var}}` placeholders (no Jinja2 required):

| Variable | Description |
|----------|-------------|
| `{{project_name}}` | Project name |
| `{{project_description}}` | Project description |
| `{{primary_skill}}` | Primary assigned skill |
| `{{assigned_skills_list}}` | Comma-separated skill list |
| `{{secondary_skills_list}}` | Markdown list of secondary skills |
| `{{skill_load_commands}}` | Pre-rendered load commands (secondary) |
| `{{skill_load_commands_full}}` | Pre-rendered load commands (all) |
| `{{primary_skill_capabilities}}` | Capabilities of the primary skill |
| `{{primary_category}}` | Detected project category |
| `{{priority_chain}}` | Selected priority chain name |
| `{{analysis_confidence}}` | Keyword match confidence score |
| `{{project_structure_tree}}` | ASCII tree of project structure |
| `{{timestamp}}` | Generation timestamp |
| `{{author}}` | Author string |

## Instructions for AI Assistants

If you are an AI assistant (Claude, ChatGPT, Gemini, Copilot, Cursor, Windsurf, Aider, or any other LLM) and a user asks you to scaffold or initialise a new DevOps project, follow these steps:

1. **Detect intent**: The user wants to create a new project with appropriate skill assignments and directory structure.

2. **Preview** (optional): Run the CLI in analyze-only mode to show the user what will be created:
   ```bash
   python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
     --name "<project-name>" --desc "<description>" --analyze-only
   ```

3. **Generate**: Run the CLI to create the project:
   ```bash
   python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
     --name "<project-name>" --desc "<description>" --target "<target-dir>"
   ```

4. **Report**: Show the user the generated structure and assigned skills.

That's it. No Python API, no imports, no special functions. Just shell commands.

## Configuration Files

| File | Format | Purpose |
|------|--------|---------|
| `priority_chains.json` | JSON | Chains, keywords, skill mapping (used by scripts) |
| `priority_chains.yaml` | YAML | Human-readable reference (not parsed by scripts) |

## Troubleshooting

**No skills detected?** The description may not contain recognised keywords. Use `--type` to force a category, or `--chain` to force a priority chain.

**Want to add a new project type?** Edit `priority_chains.json`: add keywords to `keyword_mapping`, a chain to `priority_chains`, and update `scripts/project_analyzer.py` `_select_chain()` and `get_project_structure()`.

## Addon System (v1.3+)

The skill uses an autodiscovery addon system to generate platform and tool-specific files. Addons are Python modules in the `addons/` directory that implement a standard interface.

### Available Addons

| Addon | Trigger | Description |
|-------|---------|-------------|
| `flux_deployment` | `default: True` | FluxCD GitOps manifests (always loaded) |
| `argo_deployment` | `gitops_tool: argo` | ArgoCD Application/AppProject with app-of-apps pattern |
| `eck_deployment` | `category: elasticsearch` | ECK 2.x manifests for Elasticsearch 8.x clusters (multi-tier support) |
| `terraform_aks` | `platform: aks` or `platform_detected: aks` | Terraform AKS module structure (aks, networking, storage, acr, monitoring) |
| `platform_manifests` | `platform: rke2/openshift/aks` | Platform-specific configs (storage, security, ingress) |
| `sizing_integration` | `interactive_only` | ES sizing skill integration for interactive mode |
| `sizing_parser` | CLI `--sizing-file` | Parse sizing report markdown files (v1.5, enhanced v1.8) |

### Addon Matching Logic

1. **GitOps Tool** (highest priority): If `gitops_tool` is set, only the matching GitOps addon loads
2. **Platform**: If `platform` is set, platform-specific addons load
3. **Category**: Addons matching the detected project category load
4. **Keywords**: Addons can trigger on project name/description keywords

### Creating Custom Addons

Create a Python file in `addons/` with this interface:

```python
#!/usr/bin/env python3
from typing import Any, Dict, Optional

ADDON_META = {
    "name": "my_addon",
    "version": "1.0",
    "description": "My custom addon",
    "triggers": {"categories": ["kubernetes"]},
    "priority": 10,
}

def main(
    project_name: str,
    description: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Return dict of {filepath: content} for generated files."""
    context = context or {}
    return {
        "my-addon/example.yaml": f"# Generated for {project_name}\\n",
    }
```

Register the addon in `priority_chains.json` under `addons`:

```json
{
  "addons": {
    "my_addon": {
      "path": "addons/my_addon.py",
      "description": "My custom addon",
      "triggers": {"categories": ["kubernetes"]},
      "priority": 10
    }
  }
}
```

## Session Bootstrap (.opencode/context.md)

Every generated project includes `.opencode/context.md` with:

- **Skill load commands** - Ready-to-paste commands to load all assigned skills
- **Project configuration** - Platform, GitOps tool, and category
- **Primary skill capabilities** - What the primary skill can help with
- **Project structure tree** - Visual overview of generated directories
- **Session notes section** - Space for session-specific notes

This file is designed to be loaded at the start of an OpenCode session to quickly configure the environment for the project.

---

**Version**: 1.9
**Author**: robert.rotter
