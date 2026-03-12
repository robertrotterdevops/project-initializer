# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Platform-agnostic DevOps project scaffolding tool with automatic skill assignment. Analyzes project descriptions via keyword matching, selects priority chains, and generates complete project structures with infrastructure-as-code templates. Supports Elasticsearch/ECK, Kubernetes/OpenShift, Terraform, Azure/AKS, and GitOps (FluxCD/ArgoCD).

Three interfaces: CLI (zero dependencies, Python stdlib only), Web UI (FastAPI + vanilla JS at localhost:8787), Desktop (Tauri).

## Commands

```bash
# CLI - analyze only (no files created)
python3 scripts/init_project.py --name my-project --desc "Elasticsearch on OpenShift" --analyze-only

# CLI - full project creation
python3 scripts/init_project.py --name my-project --desc "Elasticsearch on OpenShift" --type elasticsearch

# CLI - interactive mode
python3 scripts/init_project.py --interactive

# Web UI (creates venv, installs deps, launches on :8787)
./start-ui.sh

# Web UI manual start
uvicorn app:app --app-dir ui-draft/backend --reload --host 0.0.0.0 --port 8787

# Tests
python3 -m pytest tests/test_iac_hardening.py -v
```

No linter is configured.

## Architecture

### Data Flow

```
User Input (CLI args or Web API request)
  → scripts/init_project.py (entry point, arg parsing)
  → scripts/project_analyzer.py (keyword analysis → category + skill assignment)
  → scripts/generate_structure.py (scaffold dirs/files, render {{var}} templates)
  → scripts/addon_loader.py (discover → match by triggers → execute in priority order)
  → addons/*.py (each returns {filepath: content} dict, written to disk)
```

### Core Modules (scripts/)

- **init_project.py** — CLI entry point. Routes to analyze-only, full init, or interactive mode.
- **project_analyzer.py** — `ProjectAnalyzer` class. Keyword-based category detection (elasticsearch, kubernetes, terraform, azure, gitops), confidence scoring, priority chain selection, skill assignment.
- **generate_structure.py** — Creates project filesystem. Simple `{{var}}` template rendering (not Jinja2). Coordinates addon execution.
- **addon_loader.py** — Dynamic addon discovery via `importlib.util`. Trigger-based matching (category, platform, gitops_tool, iac_tool). Priority-ordered execution.
- **sizing_parser.py** — Parses Elasticsearch sizing reports (markdown v1.0 format or JSON contract). Extracts node pools, storage, platform-specific configs.
- **interactive.py** — Guided CLI prompts for platform, GitOps tool, and IaC tool selection.

### Addon System (addons/)

Addons are Python modules triggered by project type/platform/tool combinations. Each implements either a `main(project_name, description, context)` function or an `AddonGenerator` class with a `generate()` method returning `{filepath: content}`.

Addon configuration (triggers, priority, supported types) lives in `priority_chains.json` under the `"addons"` key.

Key addons: `eck_deployment.py` (ECK/ES clusters), `flux_deployment.py` (FluxCD), `argo_deployment.py` (ArgoCD), `terraform_aks.py` (AKS IaC), `platform_manifests.py` (K8s manifests), `rke2_bootstrap.py` (Ansible playbooks).

### Web UI

- **Backend**: `ui-draft/backend/backend_api.py` — FastAPI app with git operations, file upload, deployment history, preferences store, GitHub/GitLab repo creation.
- **Frontend**: `ui-draft/frontend/index.html` — Single-page vanilla JS app.
- **Desktop**: `ui-draft/desktop/` — Tauri shell wrapping the web UI.

### Master Configuration

`priority_chains.json` is the single source of truth for:
- Keyword → category mappings
- Priority chains (ordered skill lists)
- Platform definitions (RKE2, OpenShift, AKS)
- GitOps tool metadata
- Addon specifications (triggers, priorities)
- Skill mappings

## Key Data Structures

**Analysis Result**: `{project_name, description, primary_category, category_scores, priority_chain, assigned_skills, analysis_confidence}`

**Context Dict** (passed to addons): `{platform, gitops_tool, iac_tool, repo_url, git_token, target_revision, sizing_context, fallback_storage_class}`

## Conventions

- Core CLI has zero external dependencies (Python stdlib only). Web UI requires FastAPI/uvicorn.
- Templates use simple `{{var}}` substitution, not Jinja2.
- Addons return file dictionaries; they don't write to disk directly.
- Tests use `unittest` framework via pytest runner.

---

# project-initializer

Platform-agnostic project scaffolding with automatic skill assignment. Generate DevOps project structures (Terraform, ArgoCD, OpenShift, ECK) via a web UI or CLI.

## Quick Start

```bash
git clone <repo-url> && cd project-initializer
./start-ui.sh
# Open http://localhost:8787
```

The script creates a Python venv, installs dependencies, and launches the web UI.

## CLI Usage

No setup required beyond Python 3.9+:

```bash
python3 scripts/init_project.py --name my-project --desc "Elasticsearch on OpenShift"
python3 scripts/init_project.py --analyze-only --name my-project --desc "Elasticsearch on OpenShift"
```

## Desktop Mode (optional)

Tauri-based desktop app for macOS/Linux:

```bash
./start-ui-macos.sh   # macOS
./start-ui-linux.sh   # Linux
```

See `START-HERE-UI.md` for details.
