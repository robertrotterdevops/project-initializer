#!/usr/bin/env python3
"""
Deployment lifecycle addon for project-initializer.

Generates post-deploy automation scripts and a pre-flight check script
for Kubernetes/GitOps projects.

Scripts generated:
  scripts/mirror-secrets.sh     — Mirror ECK elastic-user secret to observability namespace
  scripts/fleet-output.sh       — Configure Fleet default output via Kibana API
  scripts/import-dashboards.sh  — Import OTEL infrastructure dashboard into Kibana
  scripts/preflight-check.sh    — Pre-flight cluster/Flux/CRD validation
"""

from __future__ import annotations

from typing import Any, Dict, Optional


ADDON_META = {
    "name": "deployment_lifecycle",
    "version": "1.0",
    "description": "Deployment lifecycle scripts: post-deploy automation, pre-flight checks",
    "triggers": {"default": True},
    "priority": 20,
}


class DeploymentLifecycleGenerator:
    """Generates deployment lifecycle shell scripts for Kubernetes/GitOps projects."""

    def __init__(
        self,
        project_name: str,
        description: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.project_name = project_name
        self.description = description
        self.context = context or {}
        self.platform = (self.context.get("platform") or "").lower()
        self.gitops_tool = (self.context.get("gitops_tool") or "").lower()
        self.sizing_context = self.context.get("sizing_context") or {}
        self.eck_enabled = bool(
            self.sizing_context
            and (
                self.sizing_context.get("eck_operator")
                or self.sizing_context.get("source") == "sizing_report"
            )
        )

    def _script_header(self) -> str:
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "\n"
            f'PROJECT_NAME=\"{self.project_name}\"\n'
            f'PLATFORM=\"{self.platform}\"\n'
            'ROOT_DIR=\"$(cd \"$(dirname \"$0\")/..\" && pwd)\"\n'
            'INVENTORY_FILE=\"$ROOT_DIR/ansible/inventory.ini\"\n'
            'PROJECT_KUBECONFIG=\"${PI_ARG_KUBECONFIG_PATH:-$ROOT_DIR/.kube/$PROJECT_NAME}\"\n'
            "\n"
            'if [[ -f \"$ROOT_DIR/scripts/lib/kubeconfig.sh\" ]]; then\n'
            '  # shellcheck source=/dev/null\n'
            '  source \"$ROOT_DIR/scripts/lib/kubeconfig.sh\"\n'
            'fi\n'
            "\n"
            'pi_prepare_script_kubeconfig() {\n'
            '  if declare -F pi_require_kubeconfig >/dev/null 2>&1; then\n'
            '    if pi_require_kubeconfig \"$PLATFORM\" \"$INVENTORY_FILE\" \"$PROJECT_KUBECONFIG\"; then\n'
            '      export PI_ARG_KUBECONFIG_PATH=\"${KUBECONFIG:-$PROJECT_KUBECONFIG}\"\n'
            '      return 0\n'
            '    fi\n'
            '    return 1\n'
            '  fi\n'
            '  if [[ -n \"${PI_ARG_KUBECONFIG_PATH:-}\" && -f \"${PI_ARG_KUBECONFIG_PATH}\" ]]; then\n'
            '    export KUBECONFIG=\"${PI_ARG_KUBECONFIG_PATH}\"\n'
            '    return 0\n'
            '  fi\n'
            '  if [[ -n \"${KUBECONFIG:-}\" && -f \"${KUBECONFIG}\" ]]; then\n'
            '    return 0\n'
            '  fi\n'
            '  if [[ -f \"$PROJECT_KUBECONFIG\" ]]; then\n'
            '    export KUBECONFIG=\"$PROJECT_KUBECONFIG\"\n'
            '    export PI_ARG_KUBECONFIG_PATH=\"$PROJECT_KUBECONFIG\"\n'
            '    return 0\n'
            '  fi\n'
            '  return 1\n'
            '}\n'
            "\n"
        )

    def _kubeconfig_helper_script(self) -> str:
        try:
            from addons.terraform_gitops_trigger import _kubeconfig_helper_script as shared_helper

            return shared_helper()
        except Exception:
            return """#!/usr/bin/env bash
set -euo pipefail

pi_resolve_kubeconfig() {
  local target_path="${1:-}"
  local candidate
  for candidate in \
    "${PI_ARG_KUBECONFIG_PATH:-}" \
    "${KUBECONFIG:-}" \
    "$target_path" \
    "$HOME/.kube/config" \
    "/etc/rancher/rke2/rke2.yaml"; do
    [[ -z "$candidate" ]] && continue
    if [[ -f "$candidate" ]]; then
      export KUBECONFIG="$candidate"
      return 0
    fi
  done
  return 1
}

pi_prepare_kubeconfig() {
  local target_path="${3:-}"
  pi_resolve_kubeconfig "$target_path" && return 0
  return 1
}

pi_require_kubeconfig() {
  pi_prepare_kubeconfig "$@" || {
    echo "ERROR: kubeconfig not available (checked PI_ARG_KUBECONFIG_PATH, project-local .kube, and home .kube)."
    return 1
  }
}
"""

    def _mirror_secrets_script(self) -> str:
        return (
            self._script_header()
            + f"""if ! pi_prepare_script_kubeconfig; then
  echo "ERROR: kubeconfig is required for secret mirroring"
  exit 1
fi

echo "[1/3] Waiting for Elasticsearch to be ready (this may take several minutes)..."
ELAPSED=0
while [ $ELAPSED -lt 900 ]; do
  PHASE=$(kubectl get elasticsearch/${{PROJECT_NAME}} -n ${{PROJECT_NAME}} \\
    -o jsonpath='{{.status.phase}}' 2>/dev/null || echo "")
  [ "$PHASE" = "Ready" ] && break
  sleep 10
  ELAPSED=$((ELAPSED + 10))
done
if [ "${{PHASE:-}}" != "Ready" ]; then
  echo "ERROR: Elasticsearch not ready after 15 minutes (phase=${{PHASE:-unknown}})"
  exit 1
fi

echo "[2/3] Creating observability namespace..."
kubectl create namespace observability 2>/dev/null || true

echo "[3/3] Mirroring ECK elastic-user secret to observability namespace..."
ES_PASS="$(kubectl get secret ${{PROJECT_NAME}}-es-elastic-user -n ${{PROJECT_NAME}} \\
  -o go-template='{{{{.data.elastic | base64decode}}}}' 2>/dev/null || true)"
if [ -z "$ES_PASS" ]; then
  echo "ERROR: Elasticsearch elastic-user password is empty or unavailable; refusing to mirror blank secret"
  exit 1
fi
# Ensure placeholder secret exists (ArgoCD manages metadata/annotations)
kubectl create secret generic otel-es-credentials \\
  --from-literal=username=elastic \\
  --from-literal=password=dummy \\
  -n observability 2>/dev/null || true

# Patch with real credentials — does not fight SSA field ownership
ES_PASS_B64="$(printf '%s' "$ES_PASS" | base64 | tr -d '\\n')"
kubectl patch secret otel-es-credentials -n observability --type=merge \\
  -p "{{\\"data\\":{{\\"username\\":\\"ZWxhc3RpYw==\\",\\"password\\":\\"${{ES_PASS_B64}}\\"}}}}"

echo "Secret mirroring complete."
"""
        )

    def _fleet_output_script(self) -> str:
        return (
            self._script_header()
            + f"""if ! pi_prepare_script_kubeconfig; then
  echo "ERROR: kubeconfig is required for Fleet output configuration"
  exit 1
fi

echo "[1/4] Waiting for Kibana to be ready..."
ELAPSED=0
while [ $ELAPSED -lt 300 ]; do
  KB_NODES=$(kubectl get kibana/${{PROJECT_NAME}} -n ${{PROJECT_NAME}} \\
    -o jsonpath='{{.status.availableNodes}}' 2>/dev/null || echo "0")
  [ "${{KB_NODES:-0}}" -gt 0 ] && break
  sleep 10
  ELAPSED=$((ELAPSED + 10))
done
if [ "${{KB_NODES:-0}}" -eq 0 ]; then
  echo "WARNING: Kibana not ready after 5 minutes, proceeding anyway..."
fi

echo "[2/4] Retrieving Elasticsearch credentials..."
ES_PASS="$(kubectl get secret ${{PROJECT_NAME}}-es-elastic-user -n ${{PROJECT_NAME}} \\
  -o go-template='{{{{.data.elastic | base64decode}}}}')"

echo "[3/4] Retrieving CA fingerprint..."
CA_FP=$(kubectl get secret ${{PROJECT_NAME}}-es-http-certs-public -n ${{PROJECT_NAME}} \\
  -o jsonpath='{{.data.ca\\.crt}}' | base64 -d | \\
  openssl x509 -fingerprint -sha256 -noout 2>/dev/null | sed 's/.*=//;s/://g')

echo "[4/4] Configuring Fleet default output..."
KB_POD=$(kubectl get pod -n ${{PROJECT_NAME}} -l "common.k8s.elastic.co/type=kibana" \\
  --field-selector=status.phase=Running -o jsonpath='{{.items[0].metadata.name}}' 2>/dev/null || true)

if [ -n "$KB_POD" ]; then
  kubectl exec -n ${{PROJECT_NAME}} "$KB_POD" -- curl -sk -u "elastic:${{ES_PASS}}" \\
    -X PUT "https://localhost:5601/api/fleet/outputs/fleet-default-output" \\
    -H 'kbn-xsrf: true' -H 'Content-Type: application/json' \\
    -d "{{
      \\"name\\": \\"default\\",
      \\"type\\": \\"elasticsearch\\",
      \\"hosts\\": [\\"https://${{PROJECT_NAME}}-es-http.${{PROJECT_NAME}}.svc:9200\\"],
      \\"is_default\\": true,
      \\"is_default_monitoring\\": true,
      \\"ca_trusted_fingerprint\\": \\"${{CA_FP}}\\",
      \\"config_yaml\\": \\"ssl.verification_mode: none\\"
    }}" >/dev/null 2>&1 && echo "Fleet output configured." || \\
      echo "Fleet output config failed (may need manual setup)."
else
  echo "No running Kibana pod found. Fleet output must be configured manually."
fi
"""
        )

    def _import_dashboards_script(self) -> str:
        return (
            self._script_header()
            + f"""if ! pi_prepare_script_kubeconfig; then
  echo "ERROR: kubeconfig is required for dashboard import"
  exit 1
fi

echo "[1/3] Retrieving Elasticsearch credentials..."
ES_PASS="$(kubectl get secret ${{PROJECT_NAME}}-es-elastic-user -n ${{PROJECT_NAME}} \\
  -o go-template='{{{{.data.elastic | base64decode}}}}')"

echo "[2/3] Locating Kibana pod..."
KB_POD=$(kubectl get pod -n ${{PROJECT_NAME}} -l "common.k8s.elastic.co/type=kibana" \\
  --field-selector=status.phase=Running -o jsonpath='{{.items[0].metadata.name}}' 2>/dev/null || true)

echo "[3/3] Importing OTEL Infrastructure dashboard..."
DASHBOARD_FILE="$ROOT_DIR/observability/otel-dashboards/otel-infrastructure-overview.ndjson"

if [ -z "$KB_POD" ]; then
  echo "No running Kibana pod found. Dashboard import skipped."
  exit 0
fi

if [ ! -f "$DASHBOARD_FILE" ]; then
  echo "Dashboard file not found at $DASHBOARD_FILE. Skipping import."
  echo "Place the dashboard ndjson at: $DASHBOARD_FILE"
  exit 0
fi

KB_SVC=$(kubectl get svc -n ${{PROJECT_NAME}} -l "common.k8s.elastic.co/type=kibana" -o jsonpath='{{.items[0].metadata.name}}')
KB_PORT=$(kubectl get svc -n ${{PROJECT_NAME}} "${{KB_SVC}}" -o jsonpath='{{.spec.ports[0].port}}')

kubectl port-forward -n ${{PROJECT_NAME}} "svc/${{KB_SVC}}" 15601:${{KB_PORT}} &
PF_PID=$!
trap "kill $PF_PID 2>/dev/null" EXIT
sleep 4

RESULT=$(curl -sk -u "elastic:${{ES_PASS}}" \\
  -X POST "https://localhost:15601/api/saved_objects/_import?overwrite=true" \\
  -H 'kbn-xsrf: true' \\
  --form "file=@${{DASHBOARD_FILE}};type=application/ndjson")

echo "$RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin); print('OTEL dashboard imported.' if r.get('success') else f'Import failed: {{r}}')"
"""
        )

    def _preflight_check_script(self) -> str:
        def _safe_int(value: Any, default: int = 0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        hot_count = _safe_int((self.sizing_context.get("data_nodes") or {}).get("count"), 1 if self.eck_enabled else 0)
        cold_count = _safe_int((self.sizing_context.get("cold_nodes") or {}).get("count"), 0)
        frozen_count = _safe_int((self.sizing_context.get("frozen_nodes") or {}).get("count"), 0)
        kibana_count = _safe_int((self.sizing_context.get("kibana") or {}).get("count"), 1 if self.eck_enabled else 0)
        fleet_count = _safe_int((self.sizing_context.get("fleet_server") or {}).get("count"), 1 if self.eck_enabled else 0)

        expect_hot = hot_count > 0
        expect_cold = cold_count > 0
        expect_frozen = frozen_count > 0
        expect_system = (kibana_count + fleet_count) > 0

        return (
            self._script_header()
            + f"""PASS=0
FAIL=0
EXPECT_HOT={str(expect_hot).lower()}
EXPECT_COLD={str(expect_cold).lower()}
EXPECT_FROZEN={str(expect_frozen).lower()}
EXPECT_SYSTEM={str(expect_system).lower()}

if ! pi_prepare_script_kubeconfig; then
  echo "WARNING: kubeconfig could not be resolved; connectivity and node checks may fail."
fi

echo "=== Pre-flight checks for FluxCD deployment ==="
echo

require_manifest_selector() {{
  local file="$1"
  local tier="$2"
  local component="$3"

  if [ ! -f "$file" ]; then
    echo "  ERROR: $component manifest not found: $file"
    echo "  Fix: regenerate project scaffolding so $component manifest exists."
    FAIL=$((FAIL + 1))
    return
  fi

  if grep -Eq 'elasticsearch\.k8s\.elastic\.co/tier"?:[[:space:]]*"?'"$tier"'"?' "$file"; then
    echo "  PASS: $component selector requires tier=$tier"
    PASS=$((PASS + 1))
  else
    echo "  ERROR: $component selector is not tier=$tier"
    echo "  Fix: set nodeSelector elasticsearch.k8s.elastic.co/tier=$tier in $file"
    FAIL=$((FAIL + 1))
  fi
}}

require_node_label() {{
  local tier="$1"
  local component="$2"
  if kubectl get nodes -l "elasticsearch.k8s.elastic.co/tier=$tier" -o name 2>/dev/null | grep -q .; then
    echo "  PASS: Node label exists for $component (tier=$tier)"
    PASS=$((PASS + 1))
  else
    echo "  ERROR: No Kubernetes node found with label elasticsearch.k8s.elastic.co/tier=$tier"
    echo "  Fix: label at least one node for $component before deployment."
    FAIL=$((FAIL + 1))
  fi
}}

extract_csv_storage() {{
  local component="$1"
  awk -F, -v comp="$component" '$1 == comp {{ gsub(/[^0-9.]/, "", $5); print $5; exit }}' "$ROOT_DIR/sizing/capacity-planning.csv" 2>/dev/null || true
}}

extract_manifest_storage() {{
  local nodeset="$1"
  awk -v target="$nodeset" '
    /^[[:space:]]*-[[:space:]]name:[[:space:]]*/ {{
      if (in_ns && $0 !~ "name:[[:space:]]*" target "$") in_ns=0
      if ($0 ~ "name:[[:space:]]*" target "$") {{ in_ns=1; next }}
    }}
    in_ns && /storage:[[:space:]]*/ {{
      val=$2
      gsub(/"/, "", val)
      gsub(/Gi/, "", val)
      print val
      exit
    }}
  ' "$ROOT_DIR/elasticsearch/cluster.yaml" 2>/dev/null || true
}}

check_storage_match() {{
  local csv_name="$1"
  local nodeset="$2"
  local expected
  local actual
  expected="$(extract_csv_storage "$csv_name")"
  actual="$(extract_manifest_storage "$nodeset")"

  if [ -z "$expected" ] || [ -z "$actual" ]; then
    echo "  ERROR: Could not resolve storage comparison for $nodeset (csv='$expected', manifest='$actual')"
    echo "  Fix: verify sizing/capacity-planning.csv and elasticsearch/cluster.yaml contain $nodeset storage values."
    FAIL=$((FAIL + 1))
    return
  fi

  if [ "$expected" = "$actual" ]; then
    echo "  PASS: Storage matches for $nodeset ($actual Gi)"
    PASS=$((PASS + 1))
  else
    echo "  ERROR: Storage mismatch for $nodeset (csv=$expected Gi, manifest=$actual Gi)"
    echo "  Fix: align elasticsearch/cluster.yaml storage with sizing/capacity-planning.csv"
    FAIL=$((FAIL + 1))
  fi
}}

# [1/7] Cluster connectivity
echo "[1/7] Checking cluster connectivity..."
if kubectl cluster-info >/dev/null 2>&1; then
  echo "  PASS: Kubernetes API is reachable."
  PASS=$((PASS + 1))
else
  echo "  ERROR: Cannot reach Kubernetes API."
  echo "  Fix: export KUBECONFIG=/path/to/kubeconfig or check cluster status with 'kubectl cluster-info'"
  FAIL=$((FAIL + 1))
fi

# [2/7] Flux installation
echo "[2/7] Checking Flux installation..."
if kubectl get deployment -n flux-system kustomize-controller source-controller -o name >/dev/null 2>&1; then
  echo "  PASS: Flux controllers found in flux-system namespace."
  PASS=$((PASS + 1))
else
  echo "  ERROR: Flux controllers not found in flux-system namespace."
  echo "  Fix: flux install --namespace=flux-system"
  FAIL=$((FAIL + 1))
fi

# [3/7] Required CRDs
echo "[3/7] Checking required Flux CRDs..."
if kubectl get crd kustomizations.kustomize.toolkit.fluxcd.io gitrepositories.source.toolkit.fluxcd.io >/dev/null 2>&1; then
  echo "  PASS: Required Flux CRDs are present."
  PASS=$((PASS + 1))
else
  echo "  ERROR: Required Flux CRDs missing (kustomizations.kustomize.toolkit.fluxcd.io, gitrepositories.source.toolkit.fluxcd.io)."
  echo "  Fix: flux install --namespace=flux-system"
  FAIL=$((FAIL + 1))
fi

# [4/7] Manifest selector validation
echo "[4/7] Checking manifest selectors for tier placement..."
if [ "$EXPECT_HOT" = "true" ]; then
  require_manifest_selector "$ROOT_DIR/elasticsearch/cluster.yaml" "hot" "Elasticsearch hot nodeset"
fi
if [ "$EXPECT_COLD" = "true" ]; then
  require_manifest_selector "$ROOT_DIR/elasticsearch/cluster.yaml" "cold" "Elasticsearch cold nodeset"
fi
if [ "$EXPECT_FROZEN" = "true" ]; then
  require_manifest_selector "$ROOT_DIR/elasticsearch/cluster.yaml" "frozen" "Elasticsearch frozen nodeset"
fi
if [ "$EXPECT_SYSTEM" = "true" ]; then
  require_manifest_selector "$ROOT_DIR/kibana/kibana.yaml" "system" "Kibana"
  require_manifest_selector "$ROOT_DIR/agents/fleet-server.yaml" "system" "Fleet Server"
fi

# [5/7] Node label existence
echo "[5/7] Checking Kubernetes node labels against selectors..."
if [ "$EXPECT_HOT" = "true" ]; then
  require_node_label "hot" "Elasticsearch hot tier"
fi
if [ "$EXPECT_COLD" = "true" ]; then
  require_node_label "cold" "Elasticsearch cold tier"
fi
if [ "$EXPECT_FROZEN" = "true" ]; then
  require_node_label "frozen" "Elasticsearch frozen tier"
fi
if [ "$EXPECT_SYSTEM" = "true" ]; then
  require_node_label "system" "Kibana/Fleet system services"
fi

# [6/7] System taints vs tolerations
echo "[6/7] Checking system node taints and service tolerations..."
if [ "$EXPECT_SYSTEM" = "true" ]; then
  SYSTEM_TAINT_KEYS=$(kubectl get nodes -l "elasticsearch.k8s.elastic.co/tier=system" \
    -o jsonpath='{{range .items[*].spec.taints[*]}}{{.key}}{{"\\n"}}{{end}}' 2>/dev/null | sed '/^$/d' | sort -u || true)
  if [ -z "$SYSTEM_TAINT_KEYS" ]; then
    echo "  PASS: No taints detected on system nodes."
    PASS=$((PASS + 1))
  else
    MISSING_TOL=0
    for TAINT_KEY in $SYSTEM_TAINT_KEYS; do
      if ! grep -q "$TAINT_KEY" "$ROOT_DIR/kibana/kibana.yaml"; then
        echo "  ERROR: Kibana missing toleration for system taint key '$TAINT_KEY'"
        MISSING_TOL=1
      fi
      if ! grep -q "$TAINT_KEY" "$ROOT_DIR/agents/fleet-server.yaml"; then
        echo "  ERROR: Fleet Server missing toleration for system taint key '$TAINT_KEY'"
        MISSING_TOL=1
      fi
    done
    if [ "$MISSING_TOL" -eq 0 ]; then
      echo "  PASS: Kibana/Fleet tolerations cover system node taints."
      PASS=$((PASS + 1))
    else
      echo "  Fix: add matching tolerations to kibana/kibana.yaml and agents/fleet-server.yaml"
      FAIL=$((FAIL + 1))
    fi
  fi
else
  echo "  PASS: No system-service placement requested."
  PASS=$((PASS + 1))
fi

# [7/7] Storage consistency
echo "[7/7] Checking storage values against sizing summary..."
if [ ! -f "$ROOT_DIR/sizing/capacity-planning.csv" ] || [ ! -f "$ROOT_DIR/elasticsearch/cluster.yaml" ]; then
  echo "  ERROR: Missing sizing/capacity-planning.csv or elasticsearch/cluster.yaml"
  echo "  Fix: regenerate project files before running preflight checks."
  FAIL=$((FAIL + 1))
else
  if [ "$EXPECT_HOT" = "true" ]; then
    check_storage_match "Hot Tier Nodes" "hot"
  fi
  if [ "$EXPECT_COLD" = "true" ]; then
    check_storage_match "Cold Tier Nodes" "cold"
  fi
  if [ "$EXPECT_FROZEN" = "true" ]; then
    check_storage_match "Frozen Tier Nodes" "frozen"
  fi
fi

echo
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
  echo "Pre-flight checks FAILED. Resolve the above issues before deploying."
  exit 1
fi

echo "All pre-flight checks passed."
exit 0
"""
        )

    def _generate_verify_deployment(self) -> str:
        """Generate scripts/verify-deployment.sh."""
        pn = self.project_name
        kustomizations = [pn, f"{pn}-infra", f"{pn}-apps"]
        timeouts = [120, 600, 1200]
        if self.eck_enabled:
            kustomizations.append(f"{pn}-agents")
            timeouts.append(1200)

        ks_array = " ".join(f'"{k}"' for k in kustomizations)
        to_array = " ".join(str(t) for t in timeouts)

        return (
            self._script_header()
            + """if ! pi_prepare_script_kubeconfig; then
  echo "ERROR: kubeconfig is required for deployment verification"
  exit 1
fi

"""
            + f"KUSTOMIZATIONS=({ks_array})\n"
            f"TIMEOUTS=({to_array})\n"
            "POLL_INTERVAL=30\n"
            "OVERALL_RESULT=0\n"
            "\n"
            'echo "Deployment Verification — polling kustomization readiness"\n'
            'echo ""\n'
            "\n"
            "# Arrays to store results for status table\n"
            "declare -a RESULT_NAMES\n"
            "declare -a RESULT_TIMEOUTS\n"
            "declare -a RESULT_ELAPSED\n"
            "declare -a RESULT_STATUS\n"
            "\n"
            "for i in \"${!KUSTOMIZATIONS[@]}\"; do\n"
            "  KSNAME=\"${KUSTOMIZATIONS[$i]}\"\n"
            "  TIMEOUT=\"${TIMEOUTS[$i]}\"\n"
            "  ELAPSED=0\n"
            "  RESULT=\"FAILED (timeout after ${TIMEOUT}s)\"\n"
            "\n"
            "  while [ $ELAPSED -lt $TIMEOUT ]; do\n"
            "    STATUS=$(kubectl get kustomization \"$KSNAME\" -n flux-system \\\n"
            "      -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status}' 2>/dev/null || echo \"Unknown\")\n"
            "    if [ \"$STATUS\" = \"True\" ]; then\n"
            "      RESULT=\"Ready\"\n"
            "      break\n"
            "    fi\n"
            "    sleep 30\n"
            "    ELAPSED=$((ELAPSED + POLL_INTERVAL))\n"
            "  done\n"
            "\n"
            "  if [ \"$RESULT\" != \"Ready\" ]; then\n"
            "    OVERALL_RESULT=1\n"
            "  fi\n"
            "\n"
            "  RESULT_NAMES+=(\"$KSNAME\")\n"
            "  RESULT_TIMEOUTS+=(\"${TIMEOUT}s\")\n"
            "  RESULT_ELAPSED+=(\"${ELAPSED}s\")\n"
            "  RESULT_STATUS+=(\"$RESULT\")\n"
            "done\n"
            "\n"
            "# Print status table\n"
            'printf "%-40s %-12s %-10s %s\\n" "NAME" "TIMEOUT" "ACTUAL" "STATUS"\n'
            'printf "%-40s %-12s %-10s %s\\n" "----" "-------" "------" "------"\n'
            "for i in \"${!RESULT_NAMES[@]}\"; do\n"
            '  printf "%-40s %-12s %-10s %s\\n" "${RESULT_NAMES[$i]}" "${RESULT_TIMEOUTS[$i]}" "${RESULT_ELAPSED[$i]}" "${RESULT_STATUS[$i]}"\n'
            "done\n"
            "\n"
            "# Elasticsearch pod health check\n"
            'echo ""\n'
            'echo "Checking Elasticsearch StatefulSet pod health..."\n'
            f'ES_PODS=$(kubectl get pods -n "${{PROJECT_NAME}}" \\\n'
            f'  -l "elasticsearch.k8s.elastic.co/cluster-name=${{PROJECT_NAME}}" \\\n'
            "  --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)\n"
            'if [ "$ES_PODS" -gt 0 ]; then\n'
            '  echo "  Elasticsearch: $ES_PODS pod(s) Running"\n'
            "else\n"
            '  echo "  WARNING: No Elasticsearch pods in Running state"\n'
            "  OVERALL_RESULT=1\n"
            "fi\n"
            "\n"
            'echo ""\n'
            "if [ $OVERALL_RESULT -eq 0 ]; then\n"
            '  echo "PASSED: All deployment checks passed."\n'
            "  exit 0\n"
            "else\n"
            '  echo "FAILED: One or more deployment checks failed. Review the table above."\n'
            "  exit 1\n"
            "fi\n"
        )

    def _generate_rollback(self) -> str:
        """Generate scripts/rollback.sh."""
        pn = self.project_name
        kustomizations = [pn, f"{pn}-infra", f"{pn}-apps"]
        if self.eck_enabled:
            kustomizations.append(f"{pn}-agents")

        ks_array = " ".join(f'"{k}"' for k in kustomizations)

        resume_lines = "\n".join(
            f'  echo "  flux resume kustomization {k} -n flux-system"'
            for k in kustomizations
        )

        return (
            self._script_header()
            + """if ! pi_prepare_script_kubeconfig; then
  echo "ERROR: kubeconfig is required for rollback operations"
  exit 1
fi

"""
            + f"KUSTOMIZATIONS=({ks_array})\n"
            "\n"
            'echo "[1/3] Suspending all Flux kustomizations..."\n'
            "for KSNAME in \"${KUSTOMIZATIONS[@]}\"; do\n"
            "  flux suspend kustomization \"$KSNAME\" -n flux-system 2>/dev/null && \\\n"
            '    echo "  Suspended: $KSNAME" || \\\n'
            '    echo "  WARNING: Could not suspend $KSNAME (may not exist)"\n'
            "done\n"
            "\n"
            'echo "[2/3] Current kustomization state:"\n'
            "flux get kustomizations -n flux-system 2>/dev/null || \\\n"
            "  kubectl get kustomizations.kustomize.toolkit.fluxcd.io -n flux-system 2>/dev/null || \\\n"
            '  echo "  Could not retrieve kustomization state"\n'
            "\n"
            'echo "[3/3] Rollback complete. To restore, run:"\n'
            + resume_lines + "\n"
            'echo ""\n'
            'echo "Or to fully remove and re-deploy:"\n'
            '  echo "  kubectl delete -k flux-system/"\n'
            '  echo "  kubectl apply -k flux-system/"\n'
        )

    def _generate_validate_config(self) -> str:
        """Generate scripts/validate-config.sh."""
        pn = self.project_name
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "\n"
            f'PROJECT_NAME="{pn}"\n'
            'ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"\n'
            "\n"
            "ERRORS=0\n"
            "\n"
            'echo "[1/4] Checking required directories..."\n'
            'for DIR in flux-system infrastructure apps clusters/management; do\n'
            '  if [ ! -d "$ROOT_DIR/$DIR" ]; then\n'
            '    echo "  ERROR: Required directory missing: $DIR"\n'
            '    echo "  Fix: Ensure project scaffolding completed successfully. Re-run the initializer."\n'
            '    ERRORS=$((ERRORS + 1))\n'
            '  else\n'
            '    echo "  OK: $DIR"\n'
            '  fi\n'
            'done\n'
            "\n"
            'echo "[2/4] Checking kustomization.yaml files..."\n'
            'for DIR in flux-system infrastructure apps clusters/management; do\n'
            '  if [ -d "$ROOT_DIR/$DIR" ] && [ ! -f "$ROOT_DIR/$DIR/kustomization.yaml" ]; then\n'
            '    echo "  ERROR: Missing kustomization.yaml in $DIR"\n'
            '    echo "  Fix: Add a kustomization.yaml to $DIR with appropriate resource references."\n'
            '    ERRORS=$((ERRORS + 1))\n'
            '  fi\n'
            'done\n'
            "\n"
            'echo "[3/4] Validating YAML syntax..."\n'
            'YAML_FILES=$(find "$ROOT_DIR" -name "*.yaml" -not -path "*/\\.*" -not -path "*/node_modules/*" 2>/dev/null)\n'
            'for FILE in $YAML_FILES; do\n'
            '  if ! python3 -c "import yaml, sys; list(yaml.safe_load_all(open(sys.argv[1])))" "$FILE" 2>/dev/null; then\n'
            '    echo "  ERROR: Invalid YAML syntax in $FILE"\n'
            '    echo "  Fix: Check $FILE for YAML formatting errors (missing colons, bad indentation, tabs instead of spaces)."\n'
            '    ERRORS=$((ERRORS + 1))\n'
            '  fi\n'
            'done\n'
            'echo "  Checked $(echo "$YAML_FILES" | wc -w) YAML files"\n'
            "\n"
            'echo "[4/4] Checking for dangling resource references..."\n'
            'KUSTOMIZATION_FILES=$(find "$ROOT_DIR" -name "kustomization.yaml" -not -path "*/\\.*" 2>/dev/null)\n'
            'for KFILE in $KUSTOMIZATION_FILES; do\n'
            '  KDIR=$(dirname "$KFILE")\n'
            '  RESOURCES=$(grep -E "^- " "$KFILE" 2>/dev/null | sed \'s/^- //\' | sed \'s/[[:space:]]*#.*//\' | grep -v "^$" || true)\n'
            '  for RES in $RESOURCES; do\n'
            '    TARGET="$KDIR/$RES"\n'
            '    if [[ "$RES" == *.yaml ]] || [[ "$RES" == *.yml ]]; then\n'
            '      if [ ! -f "$TARGET" ]; then\n'
            '        echo "  ERROR: Dangling reference in $KFILE: $RES (file not found)"\n'
            '        echo "  Fix: Create $TARGET or remove the reference from $KFILE"\n'
            '        ERRORS=$((ERRORS + 1))\n'
            '      fi\n'
            '    else\n'
            '      if [ -d "$TARGET" ]; then\n'
            '        if [ ! -f "$TARGET/kustomization.yaml" ]; then\n'
            '          echo "  WARNING: Directory $TARGET exists but has no kustomization.yaml"\n'
            '        fi\n'
            '      elif [ ! -f "$TARGET" ] && [ ! -d "$TARGET" ]; then\n'
            '        echo "  ERROR: Dangling reference in $KFILE: $RES (path not found)"\n'
            '        echo "  Fix: Create $TARGET or remove the reference from $KFILE"\n'
            '        ERRORS=$((ERRORS + 1))\n'
            '      fi\n'
            '    fi\n'
            '  done\n'
            'done\n'
            "\n"
            'echo ""\n'
            'if [ $ERRORS -gt 0 ]; then\n'
            '  echo "FAILED: $ERRORS error(s) found. Fix the issues above before deploying."\n'
            '  exit 1\n'
            'else\n'
            '  echo "PASSED: All configuration checks passed."\n'
            '  exit 0\n'
            'fi\n'
        )

    def generate(self) -> Dict[str, str]:
        """Generate all deployment lifecycle scripts.

        Returns:
            Dict mapping filepath to script content.
        """
        return {
            "scripts/lib/kubeconfig.sh": self._kubeconfig_helper_script(),
            "scripts/mirror-secrets.sh": self._mirror_secrets_script(),
            "scripts/fleet-output.sh": self._fleet_output_script(),
            "scripts/import-dashboards.sh": self._import_dashboards_script(),
            "scripts/preflight-check.sh": self._preflight_check_script(),
            "scripts/verify-deployment.sh": self._generate_verify_deployment(),
            "scripts/rollback.sh": self._generate_rollback(),
            "scripts/validate-config.sh": self._generate_validate_config(),
        }


def main(
    project_name: str,
    description: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Main entry point for the deployment_lifecycle addon.

    Args:
        project_name: Name of the project being scaffolded.
        description: Human-readable project description.
        context: Context dict with platform, gitops_tool, sizing_context, etc.

    Returns:
        Dict of {filepath: content} for generated shell scripts.
    """
    generator = DeploymentLifecycleGenerator(project_name, description, context)
    return generator.generate()
