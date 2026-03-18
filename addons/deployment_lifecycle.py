#!/usr/bin/env python3
"""
Deployment lifecycle addon for project-initializer.

Generates post-deploy automation scripts and a pre-flight check script
for RKE2 + FluxCD projects. Triggered when gitops_tool=flux.

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
    "triggers": {"gitops_tool": "flux"},
    "priority": 20,
}


class DeploymentLifecycleGenerator:
    """Generates deployment lifecycle shell scripts for FluxCD projects."""

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
        sizing_context = self.context.get("sizing_context") or {}
        self.eck_enabled = bool(
            sizing_context
            and (
                sizing_context.get("eck_operator")
                or sizing_context.get("source") == "sizing_report"
            )
        )

    def _script_header(self) -> str:
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "\n"
            f'PROJECT_NAME="{self.project_name}"\n'
            'ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"\n'
            "\n"
        )

    def _mirror_secrets_script(self) -> str:
        return (
            self._script_header()
            + f"""echo "[1/3] Waiting for Elasticsearch to be ready (this may take several minutes)..."
kubectl wait elasticsearch/${{PROJECT_NAME}} -n ${{PROJECT_NAME}} \\
  --for=condition=Ready --timeout=15m

echo "[2/3] Creating observability namespace..."
kubectl create namespace observability 2>/dev/null || true

echo "[3/3] Mirroring ECK elastic-user secret to observability namespace..."
kubectl create secret generic otel-es-credentials \\
  --from-literal=username=elastic \\
  --from-literal=password="$(kubectl get secret ${{PROJECT_NAME}}-es-elastic-user -n ${{PROJECT_NAME}} \\
    -o go-template='{{{{.data.elastic | base64decode}}}}')" \\
  -n observability --dry-run=client -o yaml | kubectl apply -f -

echo "Secret mirroring complete."
"""
        )

    def _fleet_output_script(self) -> str:
        return (
            self._script_header()
            + f"""echo "[1/4] Waiting for Kibana to be ready..."
kubectl wait kibana/${{PROJECT_NAME}} -n ${{PROJECT_NAME}} \\
  --for=condition=Ready --timeout=5m 2>/dev/null || true

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
            + f"""echo "[1/3] Retrieving Elasticsearch credentials..."
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

kubectl exec -i -n ${{PROJECT_NAME}} "$KB_POD" -- curl -sk -u "elastic:${{ES_PASS}}" \\
  -X POST "https://localhost:5601/api/saved_objects/_import?overwrite=true" \\
  -H 'kbn-xsrf: true' \\
  --form file=@/dev/stdin < "$DASHBOARD_FILE" >/dev/null 2>&1 && \\
  echo "OTEL dashboard imported." || \\
  echo "Dashboard import failed (can be imported manually via Kibana UI)."
"""
        )

    def _preflight_check_script(self) -> str:
        return (
            self._script_header()
            + f"""PASS=0
FAIL=0

echo "=== Pre-flight checks for FluxCD deployment ==="
echo

# [1/3] Cluster connectivity
echo "[1/3] Checking cluster connectivity..."
if kubectl cluster-info >/dev/null 2>&1; then
  echo "  PASS: Kubernetes API is reachable."
  PASS=$((PASS + 1))
else
  echo "  ERROR: Cannot reach Kubernetes API."
  echo "  Fix: export KUBECONFIG=/path/to/kubeconfig or check cluster status with 'kubectl cluster-info'"
  FAIL=$((FAIL + 1))
fi

# [2/3] Flux installation
echo "[2/3] Checking Flux installation..."
if kubectl get deployment -n flux-system kustomize-controller source-controller -o name >/dev/null 2>&1; then
  echo "  PASS: Flux controllers found in flux-system namespace."
  PASS=$((PASS + 1))
else
  echo "  ERROR: Flux controllers not found in flux-system namespace."
  echo "  Fix: flux install --namespace=flux-system"
  FAIL=$((FAIL + 1))
fi

# [3/3] Required CRDs
echo "[3/3] Checking required Flux CRDs..."
if kubectl get crd kustomizations.kustomize.toolkit.fluxcd.io gitrepositories.source.toolkit.fluxcd.io >/dev/null 2>&1; then
  echo "  PASS: Required Flux CRDs are present."
  PASS=$((PASS + 1))
else
  echo "  ERROR: Required Flux CRDs missing (kustomizations.kustomize.toolkit.fluxcd.io, gitrepositories.source.toolkit.fluxcd.io)."
  echo "  Fix: flux install --namespace=flux-system"
  FAIL=$((FAIL + 1))
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
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "\n"
            f'PROJECT_NAME="{pn}"\n'
            "\n"
            f"KUSTOMIZATIONS=({ks_array})\n"
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
            "    if kubectl get kustomization \"$KSNAME\" -n flux-system \\\n"
            "        --for=condition=Ready 2>/dev/null; then\n"
            "      RESULT=\"Ready\"\n"
            "      break\n"
            "    fi\n"
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
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "\n"
            f'PROJECT_NAME="{pn}"\n'
            "\n"
            f"KUSTOMIZATIONS=({ks_array})\n"
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
            '  if ! python3 -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]))" "$FILE" 2>/dev/null; then\n'
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
            '  RESOURCES=$(grep -E "^- " "$KFILE" 2>/dev/null | sed \'s/^- //\' | grep -v "^#" || true)\n'
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
        Returns empty dict if gitops_tool is not 'flux'.
    """
    ctx = context or {}
    gitops_tool = (ctx.get("gitops_tool") or "").lower()
    if gitops_tool != "flux":
        return {}

    generator = DeploymentLifecycleGenerator(project_name, description, context)
    return generator.generate()
