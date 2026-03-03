#!/usr/bin/env python3
"""
Generate post-Terraform trigger scripts for GitOps deployment.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


ADDON_META = {
    "name": "terraform_gitops_trigger",
    "version": "1.0",
    "description": "Post-terraform trigger scripts for Flux/Argo",
    "triggers": {"iac_tools": ["terraform"]},
    "priority": 18,
}


def _script_header(project_name: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="{project_name}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[1/3] Running terraform apply..."
cd "$ROOT_DIR/terraform"
terraform init
terraform apply -auto-approve
cd "$ROOT_DIR"

echo "[2/3] Terraform complete. Triggering GitOps reconcile..."
"""


def _flux_tail(project_name: str) -> str:
    return f"""if command -v flux >/dev/null 2>&1; then
  flux reconcile source git "$PROJECT_NAME" -n flux-system || true
  flux reconcile kustomization "$PROJECT_NAME" -n flux-system || true
  flux reconcile kustomization "$PROJECT_NAME-apps" -n flux-system || true
  flux reconcile kustomization "$PROJECT_NAME-infra" -n flux-system || true
else
  echo "Flux CLI not installed; skipped reconcile trigger."
fi

echo "[4/4] Deployment trigger finished."
"""


def _argo_tail(project_name: str) -> str:
    return f"""if command -v argocd >/dev/null 2>&1; then
  argocd app sync "$PROJECT_NAME" || true
  argocd app wait "$PROJECT_NAME" --health || true
else
  echo "ArgoCD CLI not installed; skipped sync trigger."
fi

echo "[4/4] Deployment trigger finished."
"""


def main(project_name: str, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    ctx = context or {}
    iac_tool = (ctx.get("iac_tool") or "").lower()
    if iac_tool != "terraform":
        return {}

    gitops = (ctx.get("gitops_tool") or "").lower()
    repo_url = (ctx.get("repo_url") or "").strip()
    target_revision = (ctx.get("target_revision") or "main").strip() or "main"
    git_push_block = f"""
echo "[2/4] Updating Git repository..."
cd "$ROOT_DIR"
git add .
git commit -m "Post-terraform deployment update for $PROJECT_NAME" || true
if [ -n "{repo_url}" ]; then
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "{repo_url}"
fi
if git remote get-url origin >/dev/null 2>&1; then
  git checkout -B "{target_revision}" || true
  git push -u origin "{target_revision}" || true
else
  echo "No git remote configured; push skipped."
fi
"""
    if gitops not in {"flux", "argo"}:
        return {
            "scripts/post-terraform-deploy.sh": _script_header(project_name)
            + git_push_block
            + 'echo "No GitOps tool selected (flux/argo). Terraform apply completed."'
            + "\n"
        }

    tail = _flux_tail(project_name) if gitops == "flux" else _argo_tail(project_name)
    return {
        "scripts/post-terraform-deploy.sh": _script_header(project_name) + git_push_block + tail,
        "docs/DEPLOYMENT_PIPELINE.md": (
            "# Deployment Pipeline\n\n"
            "Use this sequence to complete deployment:\n\n"
            "1. `terraform apply`\n"
            "2. Commit and push generated changes to Git remote\n"
            "3. Trigger GitOps reconciliation\n\n"
            "Generated helper:\n\n"
            "```bash\n"
            "./scripts/post-terraform-deploy.sh\n"
            "```\n"
        ),
        "docs/DEPLOYMENT_ATTENTION.md": (
            "# Deployment Attention Checklist\n\n"
            "This project requires manual edits before first successful deployment.\n\n"
            "## Required Manual Inputs\n\n"
            "1. Configure Terraform provider credentials in `terraform/terraform.tfvars`:\n"
            "   - `proxmox_api_url`, `proxmox_api_token_id`, `proxmox_api_token_secret`\n"
            "   - `proxmox_node_name`, network CIDRs, SSH key path\n"
            "2. Validate Terraform state/backend approach in `terraform/versions.tf` (local by default).\n"
            "3. Confirm GitOps source in `flux-system/gitrepository.yaml` or Argo app repo URL.\n"
            "4. Verify GitOps kustomization paths:\n"
            "   - `flux-system/kustomization.yaml` -> `./clusters/management`\n"
            "   - `flux-system/kustomization-apps.yaml` -> `./apps`\n"
            "   - `flux-system/kustomization-infra.yaml` -> `./infrastructure`\n"
            "5. Confirm Kubernetes cluster access (`kubeconfig`) for reconcile commands.\n\n"
            "## Execution Order\n\n"
            "1. `cd terraform && terraform init && terraform plan`\n"
            "2. `terraform apply`\n"
            "3. `./scripts/post-terraform-deploy.sh`\n"
            "4. Validate GitOps health (`flux get kustomizations` or `argocd app list`).\n"
        ),
    }
