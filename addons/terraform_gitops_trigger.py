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
echo "[1/7] Running terraform apply..."
terraform init
terraform apply -auto-approve -parallelism=4
cd "$ROOT_DIR"

if [ -x "$ROOT_DIR/scripts/bootstrap-rke2.sh" ]; then
  echo "[2/7] Running RKE2 bootstrap..."
  "$ROOT_DIR/scripts/bootstrap-rke2.sh"
else
  echo "[2/7] No RKE2 bootstrap script found; skipping."
fi
{rke2_kubeconfig_block}"""


def _flux_tail(project_name: str, eck_version: str = "3.0.0") -> str:
    eck_major = 3
    try:
        eck_major = int(eck_version.split(".")[0])
    except (ValueError, IndexError):
        pass
    agent_note = "echo \"  Waiting for agent auto-enrollment (ECK 3.x)...\"\n" if eck_major >= 3 else ""
    return f"""if command -v flux >/dev/null 2>&1; then
  echo "[4/9] Bootstrapping Flux..."
  if [ -x "$ROOT_DIR/scripts/bootstrap-flux.sh" ]; then
    "$ROOT_DIR/scripts/bootstrap-flux.sh"
  else
    echo "bootstrap-flux.sh not found; skipping."
  fi

  echo "[5/9] Waiting for Flux source and root kustomization..."
  kubectl -n flux-system wait gitrepository/"$PROJECT_NAME" --for=condition=Ready --timeout=5m || echo "  GitRepository not ready yet (will reconcile in background)."
  kubectl -n flux-system wait kustomization/"$PROJECT_NAME" --for=condition=Ready --timeout=10m || echo "  Root kustomization not ready yet (will reconcile in background)."

  echo "[6/9] Triggering Flux reconcile..."
  flux reconcile source git "$PROJECT_NAME" -n flux-system || true
  flux reconcile kustomization "$PROJECT_NAME" -n flux-system || true
  flux reconcile kustomization "$PROJECT_NAME-infra" -n flux-system || true
  flux reconcile kustomization "$PROJECT_NAME-apps" -n flux-system || true
  if flux get kustomizations "$PROJECT_NAME-agents" -n flux-system >/dev/null 2>&1; then
    flux reconcile kustomization "$PROJECT_NAME-agents" -n flux-system || true
  fi
  if flux get kustomizations "$PROJECT_NAME-observability" -n flux-system >/dev/null 2>&1; then
    flux reconcile kustomization "$PROJECT_NAME-observability" -n flux-system || true
  fi
else
  echo "Flux CLI not installed; skipped bootstrap and reconcile."
fi

echo "[7/9] Checking cluster status and ensuring kubeconfig is in place..."
echo "::pi-substep cluster-healthcheck start"
if [ -x "$ROOT_DIR/scripts/cluster-healthcheck.sh" ]; then
  if "$ROOT_DIR/scripts/cluster-healthcheck.sh"; then
    echo "::pi-substep cluster-healthcheck ok"
  else
    echo "::pi-substep cluster-healthcheck warning"
    echo "  Cluster healthcheck reported warnings; continuing with follow-up scripts."
  fi
else
  echo "::pi-substep cluster-healthcheck skipped"
  echo "  cluster-healthcheck.sh not found; skipping."
fi

echo "[8/9] Mirroring secrets after cluster stabilizes..."
echo "::pi-substep mirror-secrets start"
if [ -x "$ROOT_DIR/scripts/mirror-secrets.sh" ]; then
  if "$ROOT_DIR/scripts/mirror-secrets.sh"; then
    echo "::pi-substep mirror-secrets ok"
  else
    echo "::pi-substep mirror-secrets warning"
    echo "  Secret mirroring failed; inspect scripts/mirror-secrets.sh output."
  fi
else
  echo "::pi-substep mirror-secrets skipped"
  echo "  mirror-secrets.sh not found; skipping."
fi

{agent_note}echo "::pi-substep fleet-output start"
if [ -x "$ROOT_DIR/scripts/fleet-output.sh" ]; then
  if "$ROOT_DIR/scripts/fleet-output.sh"; then
    echo "::pi-substep fleet-output ok"
  else
    echo "::pi-substep fleet-output warning"
    echo "  Fleet output configuration failed; inspect scripts/fleet-output.sh output."
  fi
else
  echo "::pi-substep fleet-output skipped"
fi
echo "::pi-substep import-dashboards start"
if [ -x "$ROOT_DIR/scripts/import-dashboards.sh" ]; then
  if "$ROOT_DIR/scripts/import-dashboards.sh"; then
    echo "::pi-substep import-dashboards ok"
  else
    echo "::pi-substep import-dashboards warning"
    echo "  Dashboard import failed; inspect scripts/import-dashboards.sh output."
  fi
else
  echo "::pi-substep import-dashboards skipped"
fi

echo "Deployment trigger finished."
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


def _cluster_healthcheck_script(project_name: str, platform: str = "") -> str:
    platform = (platform or "").lower()
    kubeconfig_bootstrap = """
if [[ -n "${PI_ARG_KUBECONFIG_PATH:-}" && -f "${PI_ARG_KUBECONFIG_PATH}" ]]; then
  export KUBECONFIG="${PI_ARG_KUBECONFIG_PATH}"
  echo ">>> Using PI_ARG_KUBECONFIG_PATH at $KUBECONFIG"
elif [[ -n "${KUBECONFIG:-}" && -f "${KUBECONFIG}" ]]; then
  echo ">>> Using exported KUBECONFIG at $KUBECONFIG"
elif [[ -f "$KUBECONFIG_FILE" ]]; then
  export KUBECONFIG="$KUBECONFIG_FILE"
  echo ">>> Using existing KUBECONFIG at $KUBECONFIG_FILE"
"""
    if platform in {"rke2", "proxmox"}:
        kubeconfig_bootstrap += """elif [[ -f "$INVENTORY_FILE" ]]; then
  SERVER_IP=$(grep -A 20 '^\\[rke2_servers\\]' "$INVENTORY_FILE" | grep -m1 'ansible_host=' | sed -E 's/.*ansible_host=([^[:space:]]+).*/\\1/' || true)
  SSH_USER=$(grep -m1 'ansible_user=' "$INVENTORY_FILE" | sed -E 's/.*ansible_user=([^[:space:]]+).*/\\1/' || true)
  SSH_PASS=$(grep -m1 'ansible_ssh_pass=' "$INVENTORY_FILE" | sed -E 's/.*ansible_ssh_pass=([^[:space:]]+).*/\\1/' || true)
  SSH_KEY="${PI_ARG_SSH_KEY_PATH:-${SSH_KEY_PATH:-}}"
  if [[ -n "$SERVER_IP" ]]; then
    mkdir -p "$(dirname "$KUBECONFIG_FILE")"
    TMPKUBE=$(mktemp)
    echo ">>> Fetching kubeconfig from ${SSH_USER:-ubuntu}@$SERVER_IP"
    SSH_BASE=(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)
    [[ -n "$SSH_KEY" ]] && SSH_BASE+=( -i "$SSH_KEY" )
    SSH_TARGET="${SSH_USER:-ubuntu}@$SERVER_IP"
    FETCH_OK=0
    if [[ -n "$SSH_PASS" && "$(command -v sshpass || true)" != "" ]]; then
      if sshpass -p "$SSH_PASS" "${SSH_BASE[@]}" "$SSH_TARGET" "sudo cat /etc/rancher/rke2/rke2.yaml" > "$TMPKUBE" 2>/dev/null && [[ -s "$TMPKUBE" ]]; then
        FETCH_OK=1
      fi
    fi
    if [[ $FETCH_OK -eq 0 ]]; then
      if "${SSH_BASE[@]}" "$SSH_TARGET" "sudo cat /etc/rancher/rke2/rke2.yaml" > "$TMPKUBE" 2>/dev/null && [[ -s "$TMPKUBE" ]]; then
        FETCH_OK=1
      fi
    fi
    if [[ $FETCH_OK -eq 1 ]]; then
      sed -i "s|https://127.0.0.1:6443|https://$SERVER_IP:6443|g" "$TMPKUBE"
      mv "$TMPKUBE" "$KUBECONFIG_FILE"
      chmod 600 "$KUBECONFIG_FILE"
      export KUBECONFIG="$KUBECONFIG_FILE"
      echo ">>> KUBECONFIG set to $KUBECONFIG"
    else
      rm -f "$TMPKUBE"
      echo ">>> WARNING: Failed to fetch kubeconfig from $SERVER_IP"
    fi
  fi
fi
"""
    else:
        kubeconfig_bootstrap += """elif [[ -z "${KUBECONFIG:-}" ]]; then
  echo ">>> KUBECONFIG is not set. For managed or externally delivered clusters, export kubeconfig before running this health check."
fi
"""

    return f"""#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="{project_name}"
ES_NAME="{project_name}"
KIBANA_INGRESS="{project_name}-kibana"
INVENTORY_FILE="$(cd "$(dirname "$0")/.." && pwd)/ansible/inventory.ini"
KUBECONFIG_FILE="$HOME/.kube/{project_name}"
[[ -n "${{PI_ARG_KUBECONFIG_PATH:-}}" ]] && KUBECONFIG_FILE="${{PI_ARG_KUBECONFIG_PATH}}"

{kubeconfig_bootstrap}

sep() {{ echo; echo "=== $* ==="; echo; }}

sep "NODES"
kubectl get nodes -o wide || echo "Failed to get nodes"

sep "PODS ($NAMESPACE)"
kubectl get pods -n "$NAMESPACE" -o wide \\
  --sort-by='.status.phase' 2>/dev/null \\
  | awk 'NR==1 || /[0-9]+\\/[0-9]+/' || echo "Failed to get pods"

sep "ELASTICSEARCH STATUS"
kubectl get elasticsearch -n "$NAMESPACE" 2>/dev/null || echo "No Elasticsearch resources found"

sep "KIBANA STATUS"
kubectl get kibana -n "$NAMESPACE" 2>/dev/null || echo "No Kibana resources found"

sep "ELASTICSEARCH CLUSTER HEALTH"
ES_POD=$(kubectl get pod -n "$NAMESPACE" -l "elasticsearch.k8s.elastic.co/cluster-name=${{ES_NAME}}" \\
  --field-selector=status.phase=Running -o jsonpath='{{.items[0].metadata.name}}' 2>/dev/null || true)
if [[ -n "$ES_POD" ]]; then
  kubectl exec -n "$NAMESPACE" "$ES_POD" -- \\
    curl -sk -u "elastic:$(kubectl get secret "${{ES_NAME}}-es-elastic-user" -n "$NAMESPACE" -o go-template='{{{{.data.elastic | base64decode}}}}')" \\
    "https://localhost:9200/_cluster/health?pretty" 2>/dev/null || echo "Could not reach ES cluster health API"
else
  echo "No running Elasticsearch pod found"
fi

sep "INGRESS / ROUTES ($NAMESPACE)"
kubectl get ingress -n "$NAMESPACE" 2>/dev/null || echo "No ingress resources found"
kubectl get route -n "$NAMESPACE" 2>/dev/null || echo "No OpenShift routes found"
KIBANA_HOST=$(kubectl get ingress -n "$NAMESPACE" "$KIBANA_INGRESS" \\
  -o jsonpath='{{.spec.rules[0].host}}' 2>/dev/null || true)
KIBANA_ADDR=$(kubectl get ingress -n "$NAMESPACE" "$KIBANA_INGRESS" \\
  -o jsonpath='{{.status.loadBalancer.ingress[0].ip}}{{.status.loadBalancer.ingress[0].hostname}}' 2>/dev/null || true)
if [[ -z "$KIBANA_HOST" ]]; then
  KIBANA_HOST=$(kubectl get route -n "$NAMESPACE" "$KIBANA_INGRESS" \\
    -o jsonpath='{{.spec.host}}' 2>/dev/null || true)
fi
if [[ -n "$KIBANA_HOST" ]]; then
  echo
  echo "  Kibana URL : https://${{KIBANA_HOST}}"
  if [[ -n "$KIBANA_ADDR" ]]; then echo "  LB address : ${{KIBANA_ADDR}}"; fi
fi

sep "NETWORK POLICIES ($NAMESPACE)"
kubectl get networkpolicies -n "$NAMESPACE" 2>/dev/null || echo "No network policies found"

sep "ELASTIC CREDENTIALS"
ELASTIC_PASS=$(kubectl get secret "${{ES_NAME}}-es-elastic-user" -n "$NAMESPACE" \\
  -o go-template='{{{{.data.elastic | base64decode}}}}' 2>/dev/null || true)
if [[ -n "$ELASTIC_PASS" ]]; then
  echo "  Username : elastic"
  echo "  Password : ${{ELASTIC_PASS}}"
  if [[ -n "$KIBANA_HOST" ]]; then echo "  Login URL: https://${{KIBANA_HOST}}"; fi
else
  echo "Secret ${{ES_NAME}}-es-elastic-user not found"
fi

sep "ELASTIC AGENTS"
kubectl get agents -n "$NAMESPACE" 2>/dev/null || echo "No Agent resources"
kubectl get pods -n "$NAMESPACE" -l agent.k8s.elastic.co/name -o wide 2>/dev/null || true

sep "OTEL COLLECTOR"
kubectl get pods -n observability -l app.kubernetes.io/name=otel-collector -o wide 2>/dev/null || echo "No OTEL pods"

sep "FLUX KUSTOMIZATIONS"
flux get kustomizations 2>/dev/null || echo "flux CLI not available or not configured"

sep "DONE"
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
echo "[3/7] Updating Git repository..."
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
            "scripts/cluster-healthcheck.sh": _cluster_healthcheck_script(project_name, platform),
            "docs/DEPLOYMENT_PIPELINE.md": (
                "# Deployment Pipeline\n\n"
                "1. Terraform creates infrastructure and VMs.\n"
                "2. Optional RKE2 bootstrap (when script exists).\n"
                "3. Commit and push generated artifacts to remote Git.\n"
            ),
        }

    eck_version = ctx.get("eck_version", "3.0.0")
    tail = _flux_tail(project_name, eck_version=eck_version) if gitops == "flux" else _argo_tail(project_name)
    return {
        "scripts/post-terraform-deploy.sh": _script_header(project_name, platform) + git_push_block + tail,
        "scripts/cluster-healthcheck.sh": _cluster_healthcheck_script(project_name, platform),
        "docs/DEPLOYMENT_PIPELINE.md": (
            "# Deployment Pipeline\n\n"
            "Use this sequence to complete deployment:\n\n"
            "1. `terraform apply`\n"
            "2. `scripts/bootstrap-rke2.sh` (if present for RKE2/Proxmox projects)\n"
            "3. Commit and push generated changes to Git remote\n"
            "4. Trigger GitOps reconciliation\n\n"
            "After the first reconcile completes, run:\n\n"
            "```bash\n"
            "./scripts/cluster-healthcheck.sh\n"
            "```\n\n"
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
            "6. Verify minimum cluster health with `./scripts/cluster-healthcheck.sh`.\n"
        ),
    }
