# Quick Reference Guide

## CLI Usage

```bash
SKILL=~/.config/opencode/skills/project-initializer/scripts/init_project.py

# Create a project (auto-detect type)
python3 $SKILL --name my-project --desc "Elasticsearch on OpenShift"

# Preview only (no files created)
python3 $SKILL --name my-project --desc "Kubernetes platform" --analyze-only

# JSON output
python3 $SKILL --name my-project --desc "Terraform infra" --analyze-only --json

# Force project type
python3 $SKILL --name my-project --desc "Platform repo" --type gitops

# Custom target directory
python3 $SKILL --name my-project --desc "Azure AKS" --target /tmp/my-project

# Force priority chain
python3 $SKILL --name my-project --desc "GitOps platform" --chain gitops_focused
```

## Project Types and Skill Assignments

| Project Type | Primary Skill | Priority Chain |
|--------------|---------------|----------------|
| Elasticsearch | devops-02-2026 | default |
| Kubernetes | kubernetes-k8s-specialist | kubernetes_first |
| Terraform | devops-general | terraform_first |
| Azure | devops-general | azure_focused |
| GitOps | platform-engineering | gitops_focused |

## Generated Structure

All projects get: `README.md`, `AGENTS.md`, `.gitignore`, `terraform/`, `k8s/`, `scripts/`, `docs/`, `.opencode/context/`

Plus type-specific directories:

| Type | Extra Directories |
|------|-------------------|
| elasticsearch | `observability/`, `elasticsearch/`, `kibana/` |
| kubernetes | `cluster/`, `platform-services/`, `applications/` |
| terraform | `modules/`, `environments/`, `networking/` |
| azure | `azure/`, `aks/`, `monitoring/` |
| gitops | `clusters/`, `infrastructure/`, `apps/`, `flux-system/`, `base/`, `overlays/` |

## Template Variables

Available `{{var}}` placeholders in templates:

| Variable | Description |
|----------|-------------|
| `{{project_name}}` | Project name |
| `{{project_description}}` | Project description |
| `{{primary_skill}}` | Primary skill assigned |
| `{{assigned_skills_list}}` | Comma-separated skill list |
| `{{secondary_skills_list}}` | Markdown list of secondary skills |
| `{{skill_load_commands}}` | Load commands for secondary skills |
| `{{primary_skill_capabilities}}` | Primary skill capabilities |
| `{{project_structure_tree}}` | ASCII tree of structure |
| `{{timestamp}}` | Creation timestamp |
| `{{author}}` | Author string |

## Configuration

Edit `priority_chains.json` to:
- Add new keyword categories
- Define new priority chains
- Register new skills

## Common Examples

### Elasticsearch Observability Stack
```bash
python3 $SKILL --name elastic-observability \
  --desc "Elasticsearch, Kibana, and monitoring on OpenShift"
```

### Kubernetes Platform
```bash
python3 $SKILL --name k8s-platform \
  --desc "Developer platform with GitOps on OpenShift"
```

### Terraform Infrastructure
```bash
python3 $SKILL --name terraform-infra \
  --desc "Cloud infrastructure with Terraform and Azure"
```

### GitOps Platform
```bash
python3 $SKILL --name gitops-platform \
  --desc "FluxCD GitOps for multi-cluster Kubernetes"
```

## Web UI

```bash
# Start UI server
cd ~/.config/opencode/skills/project-initializer
source .venv/bin/activate
uvicorn app:app --app-dir ui-draft/backend --reload --port 8787
```

Open http://localhost:8787

### UI Pages
- **Create**: Project creation form
- **Analyze**: Preview skill assignments
- **Git Sync**: Pull/rebase/push
- **Settings**: Theme, defaults

### Keyboard Shortcuts
| Shortcut | Action |
|----------|--------|
| Cmd/Ctrl + + | Zoom in |
| Cmd/Ctrl + - | Zoom out |
| Cmd/Ctrl + 0 | Reset zoom |
