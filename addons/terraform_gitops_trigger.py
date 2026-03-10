#!/usr/bin/env python3
"""
Generate post-Terraform trigger scripts for GitOps deployment.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


ADDON_META = {
    "name": "terraform_gitops_trigger",
    "version": "1.1",
    "description": "Post-terraform trigger scripts for Flux/Argo",
    "triggers": {"iac_tools": ["terraform"]},
    "priority": 18,
}


def _script_header(project_name: str, platform: str = "") -> str:
    rke2_kubeconfig_block = ""
    if platform in ("rke2", "proxmox"):
        rke2_kubeconfig_block = """
# Fetch kubeconfig from the RKE2 server node — used by bootstrap-flux and reconcile
SERVER_IP=$(cd "$ROOT_DIR/terraform" && terraform output -json vm_ips | \\
  python3 -c "import sys,json; ips=json.load(sys.stdin); \\
  print(next(v for k,v in ips.items() if 'system' in k))")

KUBECONFIG_TMP=$(mktemp /tmp/rke2-kubeconfig.XXXXXX)
trap "rm -f $KUBECONFIG_TMP" EXIT

sshpass -p "${ANSIBLE_SSH_PASS:-ubuntu}" ssh -o StrictHostKeyChecking=no ubuntu@"$SERVER_IP" \\
  "sudo cat /etc/rancher/rke2/rke2.yaml" > "$KUBECONFIG_TMP"

sed -i "s|https://127.0.0.1:6443|https://${SERVER_IP}:6443|g" "$KUBECONFIG_TMP"
export KUBECONFIG="$KUBECONFIG_TMP"
"""
    return f"""#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="{project_name}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR/terraform"
echo "[1/6] Running terraform apply..."
terraform init
terraform apply -auto-approve -parallelism=4
cd "$ROOT_DIR"

if [ -x "$ROOT_DIR/scripts/bootstrap-rke2.sh" ]; then
  echo "[2/6] Running RKE2 bootstrap..."
  "$ROOT_DIR/scripts/bootstrap-rke2.sh"
else
  echo "[2/6] No RKE2 bootstrap script found; skipping."
fi
{rke2_kubeconfig_block}"""


def _flux_tail(project_name: str) -> str:
    return f"""if command -v flux >/dev/null 2>&1; then
  echo "[4/6] Bootstrapping Flux..."
  if [ -x "$ROOT_DIR/scripts/bootstrap-flux.sh" ]; then
    "$ROOT_DIR/scripts/bootstrap-flux.sh"
  else
    echo "bootstrap-flux.sh not found; skipping."
  fi

  echo "[5/6] Waiting for Flux source and root kustomization..."
  kubectl -n flux-system wait gitrepository/"$PROJECT_NAME" --for=condition=Ready --timeout=5m
  kubectl -n flux-system wait kustomization/"$PROJECT_NAME" --for=condition=Ready --timeout=10m

  echo "[5/6] Triggering Flux reconcile..."
  flux reconcile source git "$PROJECT_NAME" -n flux-system || true
  flux reconcile kustomization "$PROJECT_NAME" -n flux-system || true
  flux reconcile kustomization "$PROJECT_NAME-infra" -n flux-system || true
  flux reconcile kustomization "$PROJECT_NAME-apps" -n flux-system || true
else
  echo "Flux CLI not installed; skipped bootstrap and reconcile."
fi

echo "[6/6] Deployment trigger finished."
"""


def _argo_tail(project_name: str) -> str:
    return f"""if command -v argocd >/dev/null 2>&1; then
  echo "[4/5] Triggering ArgoCD sync..."
  argocd app sync "$PROJECT_NAME" || true
  argocd app wait "$PROJECT_NAME" --health || true
else
  echo "ArgoCD CLI not installed; skipped sync trigger."
fi

echo "[5/5] Deployment trigger finished."
"""


def main(project_name: str, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    ctx = context or {}
    iac_tool = (ctx.get("iac_tool") or "").lower()
    if iac_tool != "terraform":
        return {}

    gitops = (ctx.get("gitops_tool") or "").lower()
    platform = (ctx.get("platform") or "").lower()
    repo_url = (ctx.get("repo_url") or "").strip()
    git_token = (ctx.get("git_token") or "").strip()
    target_revision = (ctx.get("target_revision") or "main").strip() or "main"
    remote_with_token = repo_url
    if git_token and repo_url.startswith("https://"):
        remote_with_token = "https://oauth2:" + git_token + "@" + repo_url[len("https://"):]

    git_push_block = f"""
echo "[3/6] Updating Git repository..."
cd "$ROOT_DIR"
git add .
git commit -m "Post-terraform deployment update for $PROJECT_NAME" || true
if [ -n "{repo_url}" ]; then
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "{repo_url}"
fi
if git remote get-url origin >/dev/null 2>&1; then
  if [ -n "{git_token}" ] && [ -n "{repo_url}" ]; then
    git remote set-url origin "{remote_with_token}"
  fi
  git checkout -B "{target_revision}" || true
  git push -u origin "{target_revision}" || true
  if [ -n "{git_token}" ] && [ -n "{repo_url}" ]; then
    git remote set-url origin "{repo_url}"
  fi
else
  echo "No git remote configured; push skipped."
fi
"""

    if gitops not in {"flux", "argo"}:
        return {
            "scripts/post-terraform-deploy.sh": _script_header(project_name, platform)
            + git_push_block
            + 'echo "No GitOps tool selected (flux/argo). Terraform/bootstrap completed."\n',
            "docs/DEPLOYMENT_PIPELINE.md": (
                "# Deployment Pipeline\n\n"
                "1. Terraform creates infrastructure and VMs.\n"
                "2. Optional RKE2 bootstrap (when script exists).\n"
                "3. Commit and push generated artifacts to remote Git.\n"
            ),
        }

    tail = _flux_tail(project_name) if gitops == "flux" else _argo_tail(project_name)
    return {
        "scripts/post-terraform-deploy.sh": _script_header(project_name, platform) + git_push_block + tail,
        "docs/DEPLOYMENT_PIPELINE.md": (
            "# Deployment Pipeline\n\n"
            "Use this sequence to complete deployment:\n\n"
            "1. `terraform apply`\n"
            "2. `scripts/bootstrap-rke2.sh` (if present for RKE2/Proxmox projects)\n"
            "3. Commit and push generated changes to Git remote\n"
            "4. Trigger GitOps reconciliation\n\n"
            "Generated helper:\n\n"
            "```bash\n"
            "./scripts/post-terraform-deploy.sh\n"
            "```\n"
        ),
        "docs/DEPLOYMENT_ATTENTION.md": (
            "# Deployment Attention Checklist\n\n"
            "This project requires manual edits before first successful deployment.\n\n"
            "## Required Manual Inputs\n\n"
            "1. Configure Terraform provider credentials in `terraform/terraform.tfvars`.\n"
            "2. Validate Terraform backend/state strategy for your environment.\n"
            "3. Confirm GitOps source in `flux-system/gitrepository.yaml` or Argo app repo URL.\n"
            "4. Verify GitOps paths (`clusters/management`, `apps`, `infrastructure`).\n"
            "5. Ensure cluster access and kubeconfig context are valid for reconcile commands.\n"
            "6. For RKE2/proxmox flows, validate SSH access used by `scripts/bootstrap-rke2.sh`.\n\n"
            "## Execution Order\n\n"
            "1. `cd terraform && terraform init && terraform plan`\n"
            "2. `terraform apply`\n"
            "3. `./scripts/bootstrap-rke2.sh` (if generated)\n"
            "4. `./scripts/post-terraform-deploy.sh`\n"
            "5. Validate GitOps health (`flux get kustomizations` or `argocd app list`).\n"
        ),
    }
