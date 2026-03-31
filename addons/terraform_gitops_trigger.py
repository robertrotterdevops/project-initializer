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


def _kubeconfig_helper_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

pi_resolve_kubeconfig() {
  local target_path="${1:-}"
  local project_name="${PROJECT_NAME:-}"
  local root_dir="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
  local seen=""
  local candidate=""

  while IFS= read -r candidate; do
    [[ -z "$candidate" ]] && continue
    case ":$seen:" in
      *":$candidate:"*) continue ;;
      *) seen="$seen:$candidate" ;;
    esac
    if [[ -f "$candidate" ]]; then
      export KUBECONFIG="$candidate"
      echo ">>> Using existing KUBECONFIG at $KUBECONFIG"
      return 0
    fi
  done < <(
    {
      [[ -n "${PI_ARG_KUBECONFIG_PATH:-}" ]] && echo "${PI_ARG_KUBECONFIG_PATH}"
      [[ -n "${KUBECONFIG:-}" ]] && echo "${KUBECONFIG}"
      [[ -n "$target_path" ]] && echo "$target_path"
      if [[ -n "$project_name" ]]; then
        echo "$root_dir/.kube/$project_name"
        echo "$HOME/.kube/$project_name"
      fi
      echo "$HOME/.kube/config"
      echo "/etc/rancher/rke2/rke2.yaml"
    }
  )

  return 1
}

pi_fetch_rke2_kubeconfig() {
  local inventory_file="${1:-}"
  local target_path="${2:-}"
  [[ -z "$target_path" ]] && return 1

  local server_ip=""
  local ssh_user=""
  local ssh_pass=""
  local ssh_key="${PI_ARG_SSH_KEY_PATH:-${SSH_KEY_PATH:-}}"

  if [[ -n "${PI_ARG_SERVER_IP:-}" ]]; then
    server_ip="${PI_ARG_SERVER_IP}"
  elif [[ -f "$inventory_file" ]]; then
    server_ip=$(grep -A 20 '^\[rke2_servers\]' "$inventory_file" | grep -m1 'ansible_host=' | sed -E 's/.*ansible_host=([^[:space:]]+).*/\1/' || true)
    ssh_user=$(grep -m1 'ansible_user=' "$inventory_file" | sed -E 's/.*ansible_user=([^[:space:]]+).*/\1/' || true)
    ssh_pass=$(grep -m1 'ansible_ssh_pass=' "$inventory_file" | sed -E 's/.*ansible_ssh_pass=([^[:space:]]+).*/\1/' || true)
  fi

  if [[ -z "$server_ip" ]]; then
    echo ">>> WARNING: Could not resolve RKE2 server IP for kubeconfig fetch"
    return 1
  fi

  [[ -z "$ssh_user" ]] && ssh_user="ubuntu"
  mkdir -p "$(dirname "$target_path")"

  local tmp_kube
  tmp_kube=$(mktemp)
  local fetch_ok=0
  local ssh_base=(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)
  [[ -n "$ssh_key" ]] && ssh_base+=( -i "$ssh_key" )
  local ssh_target="$ssh_user@$server_ip"

  echo ">>> Fetching kubeconfig from $ssh_target"
  if [[ -n "$ssh_pass" && "$(command -v sshpass || true)" != "" ]]; then
    if sshpass -p "$ssh_pass" "${ssh_base[@]}" "$ssh_target" "sudo cat /etc/rancher/rke2/rke2.yaml" > "$tmp_kube" 2>/dev/null && [[ -s "$tmp_kube" ]]; then
      fetch_ok=1
    fi
  fi
  if [[ $fetch_ok -eq 0 ]]; then
    if "${ssh_base[@]}" "$ssh_target" "sudo cat /etc/rancher/rke2/rke2.yaml" > "$tmp_kube" 2>/dev/null && [[ -s "$tmp_kube" ]]; then
      fetch_ok=1
    fi
  fi

  if [[ $fetch_ok -eq 1 ]]; then
    sed -i "s|https://127.0.0.1:6443|https://$server_ip:6443|g" "$tmp_kube"
    mv "$tmp_kube" "$target_path"
    chmod 600 "$target_path"
    export KUBECONFIG="$target_path"
    echo ">>> KUBECONFIG set to $KUBECONFIG"
    return 0
  fi

  rm -f "$tmp_kube"
  echo ">>> WARNING: Failed to fetch kubeconfig from $server_ip"
  return 1
}

pi_prepare_kubeconfig() {
  local platform="${1:-}"
  local inventory_file="${2:-}"
  local target_path="${3:-}"

  if pi_resolve_kubeconfig "$target_path"; then
    return 0
  fi

  if [[ "$platform" == "rke2" || "$platform" == "proxmox" ]]; then
    pi_fetch_rke2_kubeconfig "$inventory_file" "$target_path" || true
    pi_resolve_kubeconfig "$target_path" && return 0
  fi

  return 1
}

pi_require_kubeconfig() {
  local platform="${1:-}"
  local inventory_file="${2:-}"
  local target_path="${3:-}"
  if ! pi_prepare_kubeconfig "$platform" "$inventory_file" "$target_path"; then
    echo "ERROR: kubeconfig not available (checked PI_ARG_KUBECONFIG_PATH, project-local .kube, and home .kube)."
    return 1
  fi
  return 0
}
"""


def _script_header(project_name: str, platform: str = "", total_steps: int = 9) -> str:
    platform_value = (platform or "").lower()
    kubeconfig_stage = """
echo "[3/7] Resolving persistent project kubeconfig..."
if [ -f "$ROOT_DIR/scripts/lib/kubeconfig.sh" ]; then
  # shellcheck source=/dev/null
  source "$ROOT_DIR/scripts/lib/kubeconfig.sh"
  if pi_prepare_kubeconfig "$PLATFORM" "$INVENTORY_FILE" "$PROJECT_KUBECONFIG"; then
    export PI_ARG_KUBECONFIG_PATH="$KUBECONFIG"
    echo ">>> Active KUBECONFIG: $KUBECONFIG"
  else
    echo ">>> WARNING: kubeconfig could not be resolved yet; downstream scripts may fetch/bootstrap it."
  fi
else
  echo ">>> WARNING: scripts/lib/kubeconfig.sh not found; kubeconfig resolution fallback only."
  if [[ -f "$PROJECT_KUBECONFIG" ]]; then
    export KUBECONFIG="$PROJECT_KUBECONFIG"
    export PI_ARG_KUBECONFIG_PATH="$PROJECT_KUBECONFIG"
  fi
fi
"""
    if platform_value not in {"rke2", "proxmox"}:
        kubeconfig_stage = """
echo "[3/7] Resolving kubeconfig context..."
if [ -f "$ROOT_DIR/scripts/lib/kubeconfig.sh" ]; then
  # shellcheck source=/dev/null
  source "$ROOT_DIR/scripts/lib/kubeconfig.sh"
  pi_prepare_kubeconfig "$PLATFORM" "$INVENTORY_FILE" "$PROJECT_KUBECONFIG" || true
fi
if [[ -n "${KUBECONFIG:-}" ]]; then
  export PI_ARG_KUBECONFIG_PATH="$KUBECONFIG"
fi
"""
    kubeconfig_stage = kubeconfig_stage.replace("[3/7]", f"[3/{total_steps}]")

    return f"""#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="{project_name}"
PLATFORM="{platform_value}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INVENTORY_FILE="$ROOT_DIR/ansible/inventory.ini"
PROJECT_KUBECONFIG="${{PI_ARG_KUBECONFIG_PATH:-$ROOT_DIR/.kube/$PROJECT_NAME}}"

cd "$ROOT_DIR/terraform"
echo "[1/{total_steps}] Running terraform apply..."
terraform init
terraform apply -auto-approve -parallelism=4
cd "$ROOT_DIR"

if [ -x "$ROOT_DIR/scripts/bootstrap-rke2.sh" ]; then
  echo "[2/{total_steps}] Running RKE2 bootstrap..."
  "$ROOT_DIR/scripts/bootstrap-rke2.sh"
else
  echo "[2/{total_steps}] No RKE2 bootstrap script found; skipping."
fi
{kubeconfig_stage}"""


def _flux_tail(project_name: str, eck_version: str = "3.0.0") -> str:
    eck_major = 3
    try:
        eck_major = int(eck_version.split(".")[0])
    except (ValueError, IndexError):
        pass
    agent_note = "echo \"  Waiting for agent auto-enrollment (ECK 3.x)...\"\n" if eck_major >= 3 else ""
    return f"""run_pi_script() {{
  local script_path="$1"
  shift || true
  if [[ -n "${{PI_ARG_KUBECONFIG_PATH:-}}" ]]; then
    PI_ARG_KUBECONFIG_PATH="${{PI_ARG_KUBECONFIG_PATH}}" KUBECONFIG="${{PI_ARG_KUBECONFIG_PATH}}" "$script_path" "$@"
  else
    "$script_path" "$@"
  fi
}}

if command -v flux >/dev/null 2>&1; then
  echo "[5/9] Bootstrapping Flux..."
  if [ -x "$ROOT_DIR/scripts/bootstrap-flux.sh" ]; then
    run_pi_script "$ROOT_DIR/scripts/bootstrap-flux.sh"
  else
    echo "bootstrap-flux.sh not found; skipping."
  fi

  echo "[6/9] Waiting for Flux source and root kustomization..."
  kubectl -n flux-system wait gitrepository/"$PROJECT_NAME" --for=condition=Ready --timeout=5m || echo "  GitRepository not ready yet (will reconcile in background)."
  kubectl -n flux-system wait kustomization/"$PROJECT_NAME" --for=condition=Ready --timeout=10m || echo "  Root kustomization not ready yet (will reconcile in background)."

  echo "[7/9] Triggering Flux reconcile..."
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

echo "[8/9] Checking cluster status and ensuring kubeconfig is in place..."
echo "::pi-substep cluster-healthcheck start"
if [ -x "$ROOT_DIR/scripts/cluster-healthcheck.sh" ]; then
  if run_pi_script "$ROOT_DIR/scripts/cluster-healthcheck.sh"; then
    echo "::pi-substep cluster-healthcheck ok"
  else
    echo "::pi-substep cluster-healthcheck warning"
    echo "  Cluster healthcheck reported warnings; continuing with follow-up scripts."
  fi
else
  echo "::pi-substep cluster-healthcheck skipped"
  echo "  cluster-healthcheck.sh not found; skipping."
fi

echo "[9/9] Mirroring secrets after cluster stabilizes..."
echo "::pi-substep mirror-secrets start"
if [ -x "$ROOT_DIR/scripts/mirror-secrets.sh" ]; then
  if run_pi_script "$ROOT_DIR/scripts/mirror-secrets.sh"; then
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
  if run_pi_script "$ROOT_DIR/scripts/fleet-output.sh"; then
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
  if run_pi_script "$ROOT_DIR/scripts/import-dashboards.sh"; then
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
    return f"""run_pi_script() {{
  local script_path="$1"
  shift || true
  if [[ -n "${{PI_ARG_KUBECONFIG_PATH:-}}" ]]; then
    PI_ARG_KUBECONFIG_PATH="${{PI_ARG_KUBECONFIG_PATH}}" KUBECONFIG="${{PI_ARG_KUBECONFIG_PATH}}" "$script_path" "$@"
  else
    "$script_path" "$@"
  fi
}}

echo "[5/10] Bootstrapping ArgoCD..."
if [ -x "$ROOT_DIR/scripts/bootstrap-argocd.sh" ]; then
  run_pi_script "$ROOT_DIR/scripts/bootstrap-argocd.sh"
else
  echo "bootstrap-argocd.sh not found; skipping."
fi

echo "[6/10] Waiting for ArgoCD control plane..."
kubectl -n argocd wait deployment/argocd-server --for=condition=Available --timeout=10m || \
  echo "  argocd-server not Available yet (will continue in background)."
kubectl -n argocd wait pods -l app.kubernetes.io/part-of=argocd --for=condition=Ready --timeout=10m || \
  echo "  Some ArgoCD pods are not Ready yet (continuing)."

echo "[7/10] Applying ArgoCD project and root application..."
kubectl apply -f "$ROOT_DIR/argocd/appproject.yaml" || true
kubectl apply -f "$ROOT_DIR/argocd/apps/root-app.yaml" || true

echo "[8/10] Waiting for ArgoCD application health..."
if command -v argocd >/dev/null 2>&1; then
  argocd app sync "$PROJECT_NAME-root" || true
  argocd app wait "$PROJECT_NAME-root" --health --timeout 600 || true
else
  kubectl -n argocd wait application/"$PROJECT_NAME-root" --for=jsonpath='{{.status.health.status}}'=Healthy --timeout=10m || true
fi

echo "[9/10] Checking cluster status..."
if [ -x "$ROOT_DIR/scripts/cluster-healthcheck.sh" ]; then
  run_pi_script "$ROOT_DIR/scripts/cluster-healthcheck.sh" || true
else
  echo "cluster-healthcheck.sh not found; skipping."
fi

echo "[10/10] Mirroring secrets after cluster stabilizes..."
echo "::pi-substep mirror-secrets start"
if [ -x "$ROOT_DIR/scripts/mirror-secrets.sh" ]; then
  if run_pi_script "$ROOT_DIR/scripts/mirror-secrets.sh"; then
    echo "::pi-substep mirror-secrets ok"
  else
    echo "::pi-substep mirror-secrets warning"
    echo "  Secret mirroring failed; inspect scripts/mirror-secrets.sh output."
  fi
else
  echo "::pi-substep mirror-secrets skipped"
  echo "  mirror-secrets.sh not found; skipping."
fi

echo "::pi-substep fleet-output start"
if [ -x "$ROOT_DIR/scripts/fleet-output.sh" ]; then
  if run_pi_script "$ROOT_DIR/scripts/fleet-output.sh"; then
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
  if run_pi_script "$ROOT_DIR/scripts/import-dashboards.sh"; then
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


def _cluster_healthcheck_script(project_name: str, platform: str = "", gitops: str = "") -> str:
    platform = (platform or "").lower()
    kubeconfig_bootstrap = """if [[ -f "$ROOT_DIR/scripts/lib/kubeconfig.sh" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT_DIR/scripts/lib/kubeconfig.sh"
  if pi_prepare_kubeconfig "$PLATFORM" "$INVENTORY_FILE" "$PROJECT_KUBECONFIG"; then
    export PI_ARG_KUBECONFIG_PATH="${KUBECONFIG:-$PROJECT_KUBECONFIG}"
  else
    echo ">>> WARNING: kubeconfig is not currently available; health checks may be partial."
  fi
elif [[ -n "${PI_ARG_KUBECONFIG_PATH:-}" && -f "${PI_ARG_KUBECONFIG_PATH}" ]]; then
  export KUBECONFIG="${PI_ARG_KUBECONFIG_PATH}"
  echo ">>> Using PI_ARG_KUBECONFIG_PATH at $KUBECONFIG"
elif [[ -n "${KUBECONFIG:-}" && -f "${KUBECONFIG}" ]]; then
  echo ">>> Using exported KUBECONFIG at $KUBECONFIG"
elif [[ -f "$PROJECT_KUBECONFIG" ]]; then
  export KUBECONFIG="$PROJECT_KUBECONFIG"
  export PI_ARG_KUBECONFIG_PATH="$PROJECT_KUBECONFIG"
  echo ">>> Using existing KUBECONFIG at $PROJECT_KUBECONFIG"
else
  echo ">>> WARNING: KUBECONFIG is not set. For managed or externally delivered clusters, export kubeconfig before running this health check."
fi
"""

    return f"""#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="{project_name}"
ES_NAME="{project_name}"
PLATFORM="{platform}"
GITOPS_TOOL="{gitops}"
KIBANA_INGRESS="{project_name}-kibana"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INVENTORY_FILE="$ROOT_DIR/ansible/inventory.ini"
PROJECT_KUBECONFIG="${{PI_ARG_KUBECONFIG_PATH:-$ROOT_DIR/.kube/{project_name}}}"

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

if [[ "${{GITOPS_TOOL}}" == "argo" ]]; then
sep "ARGOCD"
ARGO_HOST=$(kubectl get ingress -n argocd argocd-server -o jsonpath='{{.spec.rules[0].host}}' 2>/dev/null || true)
if [[ -n "$ARGO_HOST" ]]; then
  echo "  URL      : https://${{ARGO_HOST}}"
else
  echo "  URL      : ingress host not found (argocd/argocd-server)"
fi
ARGO_PASS=$(kubectl get secret argocd-initial-admin-secret -n argocd -o go-template='{{{{.data.password | base64decode}}}}' 2>/dev/null || true)
if [[ -n "$ARGO_PASS" ]]; then
  echo "  Username : admin"
  echo "  Password : $ARGO_PASS"
else
  echo "  Password : argocd-initial-admin-secret not found (password may already be rotated)"
fi

sep "ARGOCD APPLICATIONS"
kubectl -n argocd get applications.argoproj.io 2>/dev/null || echo "No ArgoCD Application resources found"
if command -v argocd >/dev/null 2>&1; then
  argocd app list 2>/dev/null || true
fi
else
sep "FLUX KUSTOMIZATIONS"
flux get kustomizations 2>/dev/null || echo "flux CLI not available or not configured"
fi

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

    # Total steps depends on gitops tool; must be defined before git_push_block
    if gitops == "flux":
        total_steps = 9
    elif gitops == "argo":
        total_steps = 10
    else:
        total_steps = 4

    git_push_block = f"""
echo "[4/{total_steps}] Updating Git repository..."
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
            "scripts/lib/kubeconfig.sh": _kubeconfig_helper_script(),
            "scripts/post-terraform-deploy.sh": _script_header(project_name, platform, total_steps)
            + git_push_block
            + 'echo "No GitOps tool selected (flux/argo). Terraform/bootstrap completed."\n',
            "scripts/cluster-healthcheck.sh": _cluster_healthcheck_script(project_name, platform, gitops),
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
        "scripts/lib/kubeconfig.sh": _kubeconfig_helper_script(),
        "scripts/post-terraform-deploy.sh": _script_header(project_name, platform, total_steps) + git_push_block + tail,
        "scripts/cluster-healthcheck.sh": _cluster_healthcheck_script(project_name, platform, gitops),
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
