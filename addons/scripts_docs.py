#!/usr/bin/env python3
"""
Scripts documentation addon for project-initializer.

Generates docs/SCRIPTS.md — a comprehensive reference for every script
that was generated in the deployed project. Content adapts dynamically
based on platform, gitops_tool, iac_tool, and project category so the
guide only documents scripts that actually exist.

Always triggered (default: True). Priority 99 — runs after all other addons
so it can describe the full set of generated scripts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


ADDON_META = {
    "name": "scripts_docs",
    "version": "1.0",
    "description": "Generate docs/SCRIPTS.md — comprehensive usage guide for all generated scripts",
    "triggers": {"default": True},
    "priority": 99,
}


# ---------------------------------------------------------------------------
# Per-script documentation blocks
# ---------------------------------------------------------------------------

_BOOTSTRAP_FLUX = """\
### `scripts/bootstrap-flux.sh`

**Purpose:** Bootstrap FluxCD onto the cluster and connect it to this Git repository. Creates the initial `GitRepository` and `Kustomization` custom resources so Flux begins reconciling from the repo root.

**When to use:**
- First-time cluster setup, after Terraform (or manual) provisioning
- Whenever Flux controllers are missing or need to be re-installed
- After switching the Git remote URL

**Prerequisites:**
- `flux` CLI installed and in `$PATH`
- `kubectl` configured and pointing at the target cluster
- A personal-access token (GitHub/GitLab) with repo read access, exported as `GITHUB_TOKEN` / `GITLAB_TOKEN`
- The repository must already exist and contain a `flux-system/` directory

**Usage:**
```bash
# GitHub (default)
GITHUB_TOKEN=<token> bash scripts/bootstrap-flux.sh

# GitLab
GITLAB_TOKEN=<token> bash scripts/bootstrap-flux.sh
```

**Expected output:**
```
► connecting to github.com
✔ repository cloned
✔ components manifests pushed
✔ kustomize reconciled
```

**Notes:**
- Safe to re-run; Flux is idempotent on bootstrap
- For multi-cluster setups the script detects additional config sources automatically
"""

_BOOTSTRAP_RKE2 = """\
### `scripts/bootstrap-rke2.sh`

**Purpose:** Provision the RKE2 Kubernetes cluster on VMs that Terraform already created. Reads Terraform outputs, renders an Ansible inventory, and runs the `rke2-bootstrap.yml` playbook to install and start RKE2 on every node.

**When to use:**
- Immediately after `terraform apply` succeeds and VMs are up
- If nodes need to be reprovisioned (re-run after `terraform taint`)
- After adding new node pools to the Terraform config

**Prerequisites:**
- Terraform outputs available (`terraform output -json` works in the project root)
- `ansible` and `ansible-galaxy` installed (`pip install ansible`)
- SSH access to every VM (key must be in `ssh-agent` or specified via `ansible.cfg`)
- Ansible collections installed: `ansible-galaxy install -r ansible/requirements.yml`

**Usage:**
```bash
# Full bootstrap (called automatically by post-terraform-deploy.sh)
bash scripts/bootstrap-rke2.sh

# Dry-run to preview inventory
python3 scripts/render-rke2-inventory.py
```

**Expected output:**
```
PLAY [RKE2 cluster bootstrap] ...
TASK [Install RKE2 server] ... ok
TASK [Start rke2-server service] ... ok
...
PLAY RECAP: server1 ok=12 changed=8 failed=0
```

**Notes:**
- Nodes are labelled automatically by pool keyword (`hot`, `cold`, `frozen`, `master`, etc.)
- The kubeconfig is fetched from the first server node via SSH and written to `~/.kube/config`
"""

_RENDER_RKE2_INVENTORY = """\
### `scripts/render-rke2-inventory.py`

**Purpose:** Python utility that reads `terraform output -json` and renders `ansible/inventory.ini` from the template `ansible/inventory.tpl.ini`. Called automatically by `bootstrap-rke2.sh`; can also be run standalone to inspect the generated inventory.

**When to use:**
- Debugging node classification (hot/cold/frozen/master pools)
- Checking what IPs Ansible will connect to before running the full bootstrap
- After scaling Terraform node pools (regenerate inventory before re-running Ansible)

**Prerequisites:**
- Python 3.9+
- `terraform output -json` must succeed in the current directory

**Usage:**
```bash
# Render inventory to stdout
python3 scripts/render-rke2-inventory.py

# Redirect to file for inspection
python3 scripts/render-rke2-inventory.py > ansible/inventory.ini
cat ansible/inventory.ini
```

**Expected output:**
```ini
[servers]
node-0 ansible_host=10.0.1.10 ...

[agents_hot]
node-1 ansible_host=10.0.1.11 ...

[agents_cold]
node-2 ansible_host=10.0.1.12 ...
```
"""

_POST_TERRAFORM_DEPLOY = """\
### `scripts/post-terraform-deploy.sh`

**Purpose:** End-to-end orchestration script that runs the full deployment pipeline after `terraform apply`. Ties together: Terraform apply → RKE2 bootstrap (if applicable) → kubeconfig fetch → Git push → GitOps reconciliation → secret mirroring → Fleet configuration → dashboard import.

**When to use:**
- After initial infrastructure provisioning
- After any Terraform change that modifies cluster topology
- As the single command for a full redeploy from a clean state

**Prerequisites:**
- Terraform state initialised and `terraform apply` able to run
- All prerequisites for `bootstrap-rke2.sh` met (if platform is RKE2/Proxmox)
- Git remote configured and push access available
- `GITHUB_TOKEN` or `GITLAB_TOKEN` set for Flux bootstrap

**Usage:**
```bash
bash scripts/post-terraform-deploy.sh
```

**Pipeline stages:**
1. `terraform apply -auto-approve`
2. `scripts/bootstrap-rke2.sh` (RKE2/Proxmox only)
3. Fetch kubeconfig from RKE2 server node
4. `git add . && git commit && git push`
5. Wait for Flux `GitRepository` and `Kustomization` readiness
6. `scripts/mirror-secrets.sh`
7. `scripts/fleet-output.sh`
8. `scripts/import-dashboards.sh`

**Expected output:** Numbered progress lines for each stage, ending with `Deployment pipeline complete.`

**Notes:**
- The script is safe to re-run; each stage is idempotent
- On failure, check the numbered stage printed before the error
"""

_CLUSTER_HEALTHCHECK = """\
### `scripts/cluster-healthcheck.sh`

**Purpose:** Comprehensive post-deploy health check. Validates node readiness, pod states, Elasticsearch and Kibana CRD status, cluster health API, ingress addresses, Elastic credentials, Elastic Agent pod status, and Flux kustomization health.

**When to use:**
- After a full deployment to confirm everything is healthy
- During incident response to quickly triage the cluster
- As a smoke test before handing over to another team

**Prerequisites:**
- `kubectl` configured and pointing at the target cluster
- `flux` CLI available (for kustomization checks)
- Elasticsearch must be deployed and reachable (for API health check)

**Usage:**
```bash
bash scripts/cluster-healthcheck.sh
```

**Expected output:**
```
[1/7] Node status ...
NAME       STATUS   ROLES   AGE
node-0     Ready    ...
[2/7] Pod inventory ...
...
PASSED: Cluster is healthy.
```

**Notes:**
- Exits `0` if all checks pass, `1` if any check fails
- Individual check failures are printed but do not stop subsequent checks
"""

_MIRROR_SECRETS = """\
### `scripts/mirror-secrets.sh`

**Purpose:** Mirrors the ECK-managed `elastic-user` secret from the project namespace into the `observability` namespace as `otel-es-credentials`. Required so the OpenTelemetry Collector can authenticate to Elasticsearch without cross-namespace secret references.

**When to use:**
- After Elasticsearch reaches `Ready` state (first deploy)
- After ECK rotates the `elastic-user` secret (password change)
- After recreating the `observability` namespace

**Prerequisites:**
- `kubectl` configured
- Elasticsearch CR must be `Ready` (the script waits up to 15 minutes)
- The `observability` namespace may or may not exist (created automatically)

**Usage:**
```bash
bash scripts/mirror-secrets.sh
```

**Expected output:**
```
[1/3] Waiting for Elasticsearch to be ready...
[2/3] Creating observability namespace...
[3/3] Mirroring ECK elastic-user secret...
Secret mirroring complete.
```

**Notes:**
- Uses `--dry-run=client -o yaml | kubectl apply` for idempotency
- Called automatically by `post-terraform-deploy.sh`
"""

_FLEET_OUTPUT = """\
### `scripts/fleet-output.sh`

**Purpose:** Configures the Fleet Server default output in Kibana to point at the Elasticsearch cluster. Sets the ES host, CA certificate fingerprint, and SSL verification mode via the Kibana Fleet API.

**When to use:**
- After Kibana reaches `Ready` state on first deploy
- After Elasticsearch TLS certificates are rotated
- If Fleet agents report "output unreachable" errors

**Prerequisites:**
- `kubectl` configured
- Kibana CR must be `Ready` (the script waits up to 5 minutes)
- The Elasticsearch `elastic-user` secret must exist in the project namespace

**Usage:**
```bash
bash scripts/fleet-output.sh
```

**Expected output:**
```
[1/4] Waiting for Kibana to be ready...
[2/4] Retrieving Elasticsearch credentials...
[3/4] Retrieving CA fingerprint...
[4/4] Configuring Fleet default output...
Fleet output configured successfully.
```

**Notes:**
- Called automatically by `post-terraform-deploy.sh`
- Re-running is safe; the Kibana API call is a PUT (upsert)
"""

_IMPORT_DASHBOARDS = """\
### `scripts/import-dashboards.sh`

**Purpose:** Imports the OTEL Infrastructure overview dashboard into Kibana from the `observability/otel-dashboards/` directory.

**When to use:**
- After initial deployment (called automatically by `post-terraform-deploy.sh`)
- After upgrading the dashboard ndjson file to a newer version
- After a Kibana data view reset that removes existing dashboards

**Prerequisites:**
- `kubectl` configured
- Kibana CR must be `Ready`
- `observability/otel-dashboards/otel-infrastructure-overview.ndjson` must exist

**Usage:**
```bash
bash scripts/import-dashboards.sh
```

**Expected output:**
```
Importing OTEL Infrastructure dashboard...
Dashboard imported successfully.
```

**Notes:**
- Silently skips if the ndjson file is missing
- Safe to re-run; Kibana import is idempotent for saved objects
"""

_PREFLIGHT_CHECK = """\
### `scripts/preflight-check.sh`

**Purpose:** Validates that the cluster is ready to receive a Flux deployment: checks Kubernetes API connectivity, Flux controller pods, and required Flux CRDs. Exits `1` if any check fails so CI/CD pipelines can gate on it.

**When to use:**
- Before running `bootstrap-flux.sh` or `post-terraform-deploy.sh`
- In CI pipelines as a pre-deploy gate
- After cluster upgrades to verify Flux compatibility

**Prerequisites:**
- `kubectl` configured and pointing at the target cluster
- `flux` CLI available

**Usage:**
```bash
bash scripts/preflight-check.sh
```

**Expected output (all pass):**
```
[1/3] Kubernetes API connectivity ... PASS
[2/3] Flux controllers ... PASS
[3/3] Flux CRDs ... PASS
Pre-flight checks passed.
```

**Notes:**
- Exits `0` on full pass, `1` on any failure
- Run this before any other script to catch configuration issues early
"""

_VERIFY_DEPLOYMENT = """\
### `scripts/verify-deployment.sh`

**Purpose:** Polls Flux Kustomizations until they reach `Ready` state or time out. Produces a results table showing expected vs. actual status for each kustomization. Exits `1` if any kustomization fails or times out.

**When to use:**
- After `post-terraform-deploy.sh` to confirm GitOps reconciliation succeeded
- During incident response to check which kustomization is stuck
- In CI/CD as a blocking post-deploy verification step

**Prerequisites:**
- `kubectl` and `flux` CLI configured
- Kustomizations must already exist in the cluster (created by Flux bootstrap)

**Usage:**
```bash
bash scripts/verify-deployment.sh
```

**Expected output:**
```
NAME                    TIMEOUT    ACTUAL    STATUS
my-project              120s       Ready     ✓
my-project-infra        600s       Ready     ✓
my-project-apps         1200s      Ready     ✓
PASSED: All deployment checks passed.
```

**Notes:**
- Per-kustomization timeouts: core 120 s, infra 600 s, apps/agents 1200 s
- Exits `0` if all pass, `1` on any failure or timeout
"""

_ROLLBACK = """\
### `scripts/rollback.sh`

**Purpose:** Emergency rollback — suspends all Flux Kustomizations so the cluster stops reconciling from Git. Prints the exact `flux resume` commands needed to restore reconciliation after the issue is resolved.

**When to use:**
- A bad commit was pushed and is causing reconciliation failures
- You need to apply an emergency hotfix directly with `kubectl` without Flux overwriting it
- Before destructive maintenance operations that GitOps would immediately undo

**Prerequisites:**
- `kubectl` and `flux` CLI configured

**Usage:**
```bash
bash scripts/rollback.sh
```

**Expected output:**
```
[1/3] Suspending all Flux kustomizations...
  Suspended: my-project
  Suspended: my-project-infra
  Suspended: my-project-apps
[2/3] Current kustomization state: ...
[3/3] Rollback complete. To restore, run:
  flux resume kustomization my-project -n flux-system
  ...
```

**Notes:**
- Does NOT delete anything — only suspends reconciliation
- To fully re-deploy: `kubectl delete -k flux-system/ && kubectl apply -k flux-system/`
- Always resume kustomizations in order: core → infra → apps → agents
"""

_VALIDATE_CONFIG = """\
### `scripts/validate-config.sh`

**Purpose:** Static validation of the repository's GitOps directory structure. Checks required directories exist, each contains a `kustomization.yaml`, YAML is syntactically valid, and there are no dangling resource references in kustomization files.

**When to use:**
- Before committing and pushing to avoid a failed Flux reconciliation
- In CI as a pre-merge lint step
- After adding new kustomization directories or resources

**Prerequisites:**
- Python 3.9+ (for YAML syntax validation)
- No cluster access required — operates entirely on local files

**Usage:**
```bash
bash scripts/validate-config.sh
```

**Expected output (pass):**
```
[1/4] Checking required directories ... PASS
[2/4] Checking kustomization.yaml presence ... PASS
[3/4] Validating YAML syntax ... PASS
[4/4] Checking for dangling references ... PASS
PASSED: All configuration checks passed.
```

**Notes:**
- Exits `0` on full pass, `1` if any error is found
- Errors are printed with file path and line context for easy fixing
"""

_ARGOCD_SYNC = """\
### `scripts/argocd-sync.sh`

**Purpose:** Triggers an ArgoCD application sync and waits for it to reach a healthy, synced state.

**When to use:**
- After pushing a change to the GitOps repository to force an immediate sync
- During incident response to verify ArgoCD can reconcile the current commit
- After promoting configuration from one environment to another

**Prerequisites:**
- `argocd` CLI installed and logged in (`argocd login <server>`)
- The ArgoCD application for this project must already exist

**Usage:**
```bash
bash scripts/argocd-sync.sh
```

**Expected output:**
```
SYNC OK: my-project synced and healthy
```

**Notes:**
- Exits `0` if sync succeeds and app is healthy, `1` otherwise
- For automated use, ensure `argocd login` is called with `--username`/`--password` flags or an existing session token
"""


# ---------------------------------------------------------------------------
# Script ordering reference
# ---------------------------------------------------------------------------

_FLUX_ORDER_SECTION = """\
## Recommended Execution Order

For a full first-time deployment, run scripts in this sequence:

```
1. scripts/preflight-check.sh        # Verify cluster readiness
2. scripts/validate-config.sh        # Lint GitOps directory structure
3. scripts/bootstrap-flux.sh         # Install Flux and connect to Git
   (Flux begins reconciling — wait for kustomizations)
4. scripts/verify-deployment.sh      # Confirm all kustomizations are Ready
5. scripts/mirror-secrets.sh         # Replicate ECK secret to observability namespace
6. scripts/fleet-output.sh           # Configure Fleet default output
7. scripts/import-dashboards.sh      # Import OTEL dashboards into Kibana
8. scripts/cluster-healthcheck.sh    # Final end-to-end health check
```

> **Tip:** Steps 5–8 are automated inside `post-terraform-deploy.sh` when using Terraform.
"""

_TERRAFORM_FLUX_ORDER_SECTION = """\
## Recommended Execution Order

For a full first-time deployment, run scripts in this sequence:

```
1. scripts/preflight-check.sh        # Verify cluster readiness
2. scripts/validate-config.sh        # Lint GitOps directory structure
3. scripts/post-terraform-deploy.sh  # Full pipeline: Terraform → bootstrap → GitOps → verify
   (Internally runs steps 4–10 below)
4.  terraform apply                  #   Provision infrastructure
5.  bootstrap-rke2.sh                #   Provision RKE2 (RKE2/Proxmox only)
6.  kubeconfig fetch                 #   Write ~/.kube/config
7.  git push                         #   Push generated manifests
8.  bootstrap-flux.sh                #   Bootstrap Flux
9.  verify-deployment.sh             #   Wait for kustomizations
10. mirror-secrets.sh / fleet-output.sh / import-dashboards.sh
11. scripts/cluster-healthcheck.sh   # Final end-to-end health check
```

> **Tip:** Use `scripts/rollback.sh` immediately if `verify-deployment.sh` times out.
"""

_ARGOCD_ORDER_SECTION = """\
## Recommended Execution Order

```
1. scripts/bootstrap-flux.sh         # Bootstrap Flux (or skip if using ArgoCD exclusively)
2. scripts/argocd-sync.sh            # Sync ArgoCD application
3. scripts/cluster-healthcheck.sh    # Verify cluster health
```
"""


# ---------------------------------------------------------------------------
# Generator class
# ---------------------------------------------------------------------------


class ScriptsDocsGenerator:
    """Generates docs/SCRIPTS.md for a scaffolded project."""

    def __init__(
        self,
        project_name: str,
        description: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.project_name = project_name
        self.description = description
        ctx = context or {}
        self.platform = (ctx.get("platform") or "").lower()
        self.gitops_tool = (ctx.get("gitops_tool") or "").lower()
        self.iac_tool = (ctx.get("iac_tool") or "").lower()

        sizing_context = ctx.get("sizing_context") or {}
        self.eck_enabled = bool(
            sizing_context
            and (
                sizing_context.get("eck_operator")
                or sizing_context.get("source") == "sizing_report"
            )
        )

        self._is_rke2 = self.platform in ("rke2", "proxmox")
        self._is_terraform = self.iac_tool == "terraform"
        self._is_flux = self.gitops_tool == "flux"
        self._is_argo = self.gitops_tool == "argo"

    # ------------------------------------------------------------------
    # Script inventory helpers
    # ------------------------------------------------------------------

    def _script_list(self) -> List[str]:
        """Return a list of script filenames that will exist in the project."""
        scripts: List[str] = []

        if self._is_flux:
            scripts.append("scripts/bootstrap-flux.sh")
        if self._is_argo:
            scripts.append("scripts/argocd-sync.sh")
        if self._is_terraform and self._is_rke2:
            scripts += [
                "scripts/bootstrap-rke2.sh",
                "scripts/render-rke2-inventory.py",
            ]
        if self._is_terraform:
            scripts += [
                "scripts/post-terraform-deploy.sh",
                "scripts/cluster-healthcheck.sh",
            ]
        if self._is_flux:
            scripts += [
                "scripts/mirror-secrets.sh",
                "scripts/fleet-output.sh",
                "scripts/import-dashboards.sh",
                "scripts/preflight-check.sh",
                "scripts/verify-deployment.sh",
                "scripts/rollback.sh",
                "scripts/validate-config.sh",
            ]
        return scripts

    def _quick_ref_table(self, scripts: List[str]) -> str:
        _desc = {
            "scripts/bootstrap-flux.sh": "Install Flux and connect to this Git repo",
            "scripts/argocd-sync.sh": "Trigger ArgoCD sync and wait for healthy state",
            "scripts/bootstrap-rke2.sh": "Provision RKE2 cluster via Ansible after Terraform",
            "scripts/render-rke2-inventory.py": "Render Ansible inventory from Terraform outputs",
            "scripts/post-terraform-deploy.sh": "Full pipeline: Terraform → bootstrap → GitOps → verify",
            "scripts/cluster-healthcheck.sh": "End-to-end cluster health check",
            "scripts/mirror-secrets.sh": "Mirror ECK elastic-user secret to observability namespace",
            "scripts/fleet-output.sh": "Configure Fleet default output via Kibana API",
            "scripts/import-dashboards.sh": "Import OTEL Infrastructure dashboard into Kibana",
            "scripts/preflight-check.sh": "Pre-deploy: verify cluster, Flux CRDs, and controllers",
            "scripts/verify-deployment.sh": "Poll Flux kustomizations until Ready or timeout",
            "scripts/rollback.sh": "Emergency: suspend Flux reconciliation",
            "scripts/validate-config.sh": "Lint GitOps directory structure and YAML syntax",
        }
        _when = {
            "scripts/bootstrap-flux.sh": "First deploy / Flux re-install",
            "scripts/argocd-sync.sh": "After git push / manual trigger",
            "scripts/bootstrap-rke2.sh": "After `terraform apply`",
            "scripts/render-rke2-inventory.py": "Debug / before Ansible run",
            "scripts/post-terraform-deploy.sh": "Full redeploy from scratch",
            "scripts/cluster-healthcheck.sh": "After deploy / incident triage",
            "scripts/mirror-secrets.sh": "After ES Ready / cert rotation",
            "scripts/fleet-output.sh": "After Kibana Ready / cert rotation",
            "scripts/import-dashboards.sh": "After deploy / dashboard upgrade",
            "scripts/preflight-check.sh": "Before any deploy script",
            "scripts/verify-deployment.sh": "After Flux bootstrap",
            "scripts/rollback.sh": "Bad push / emergency hotfix",
            "scripts/validate-config.sh": "Before git push / in CI",
        }

        rows = ["| Script | Purpose | When to run |", "|--------|---------|-------------|"]
        for s in scripts:
            rows.append(f"| `{s}` | {_desc.get(s, '')} | {_when.get(s, '')} |")
        return "\n".join(rows)

    def _detail_sections(self) -> str:
        sections: List[str] = ["---", "", "## Script Reference"]
        mapping = {
            "scripts/bootstrap-flux.sh": _BOOTSTRAP_FLUX,
            "scripts/argocd-sync.sh": _ARGOCD_SYNC,
            "scripts/bootstrap-rke2.sh": _BOOTSTRAP_RKE2,
            "scripts/render-rke2-inventory.py": _RENDER_RKE2_INVENTORY,
            "scripts/post-terraform-deploy.sh": _POST_TERRAFORM_DEPLOY,
            "scripts/cluster-healthcheck.sh": _CLUSTER_HEALTHCHECK,
            "scripts/mirror-secrets.sh": _MIRROR_SECRETS,
            "scripts/fleet-output.sh": _FLEET_OUTPUT,
            "scripts/import-dashboards.sh": _IMPORT_DASHBOARDS,
            "scripts/preflight-check.sh": _PREFLIGHT_CHECK,
            "scripts/verify-deployment.sh": _VERIFY_DEPLOYMENT,
            "scripts/rollback.sh": _ROLLBACK,
            "scripts/validate-config.sh": _VALIDATE_CONFIG,
        }
        for s in self._script_list():
            if s in mapping:
                sections.append("")
                sections.append(mapping[s].rstrip())
        return "\n".join(sections)

    def _order_section(self) -> str:
        if self._is_terraform and self._is_flux:
            return _TERRAFORM_FLUX_ORDER_SECTION
        if self._is_flux:
            return _FLUX_ORDER_SECTION
        if self._is_argo:
            return _ARGOCD_ORDER_SECTION
        return ""

    # ------------------------------------------------------------------
    # Main generator
    # ------------------------------------------------------------------

    def generate(self) -> Dict[str, str]:
        scripts = self._script_list()
        if not scripts:
            return {}

        platform_line = f"**Platform:** `{self.platform}`  " if self.platform else ""
        gitops_line = f"**GitOps:** `{self.gitops_tool}`  " if self.gitops_tool else ""
        iac_line = f"**IaC:** `{self.iac_tool}`  " if self.iac_tool else ""

        header = f"""\
# Scripts Reference — {self.project_name}

> Auto-generated by project-initializer. Every script listed here exists in your
> project and is ready to run. Scripts are plain Bash (or Python) with no hidden
> dependencies beyond what is listed in each section's **Prerequisites**.

{platform_line}
{gitops_line}
{iac_line}

## Quick Reference

{self._quick_ref_table(scripts)}

{self._order_section()}
{self._detail_sections()}

---

## Troubleshooting

| Symptom | Likely cause | Script to run |
|---------|-------------|---------------|
| Flux kustomization stuck in `Progressing` | Image pull failure or missing secret | `scripts/cluster-healthcheck.sh` |
| Fleet agents not reporting | `otel-es-credentials` secret missing or stale | `scripts/mirror-secrets.sh` |
| Kibana dashboards missing | Import not run or Kibana restarted | `scripts/import-dashboards.sh` |
| Need to push a hotfix without Flux fighting you | Flux reconciling | `scripts/rollback.sh` (then `flux resume` after) |
| CI gate failing on YAML errors | Malformed kustomization.yaml | `scripts/validate-config.sh` |
| Cluster unreachable after Terraform apply | RKE2 not started | `scripts/bootstrap-rke2.sh` |
"""

        return {"scripts/README.md": header}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(
    project_name: str,
    description: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Main entry point for the scripts_docs addon.

    Args:
        project_name: Name of the project being scaffolded.
        description: Human-readable project description.
        context: Context dict with platform, gitops_tool, iac_tool, etc.

    Returns:
        Dict of {filepath: content} — always ``{"docs/SCRIPTS.md": ...}``
        unless no scripts are generated for the given context.
    """
    generator = ScriptsDocsGenerator(project_name, description, context)
    return generator.generate()
