# Project Initializer

## What This Is

A platform-agnostic DevOps project scaffolding tool that analyzes project descriptions, assigns skills via keyword matching, and generates complete infrastructure-as-code project structures. It supports Elasticsearch/ECK, Kubernetes/OpenShift, Terraform, and GitOps (FluxCD/ArgoCD) deployments. Three interfaces: CLI (zero-dependency Python), Web UI (FastAPI + vanilla JS), and Desktop (Tauri).

## Core Value

Generated projects must deploy and reconcile end-to-end through the full GitOps lifecycle — from scaffold to running infrastructure — without manual intervention or hanging kustomizations.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Keyword-based project analysis with category detection and confidence scoring — existing
- ✓ Priority chain selection and automatic skill assignment — existing
- ✓ Directory scaffolding with `{{var}}` template rendering — existing
- ✓ Dynamic addon discovery and trigger-based matching — existing
- ✓ ECK/Elasticsearch addon generates multi-tier cluster manifests — existing
- ✓ FluxCD addon generates GitRepository, Kustomization CRs — existing
- ✓ ArgoCD addon generates Application CRs — existing
- ✓ Terraform AKS addon generates IaC modules — existing
- ✓ Platform manifests addon (namespaces, RBAC, network policies) — existing
- ✓ RKE2 bootstrap addon (Ansible playbooks) — existing
- ✓ Observability stack addon (OTEL collector, dashboards) — existing
- ✓ Sizing parser extracts node pools from sizing reports — existing
- ✓ Interactive CLI mode with platform/GitOps/IaC selection — existing
- ✓ Web UI with project creation, git operations, file upload — existing
- ✓ GitHub and GitLab API integration for repo creation — existing
- ✓ Azure DevOps token verification — existing
- ✓ SSH key management and remote deployment via rsync — existing
- ✓ Deployment history tracking — existing
- ✓ User preferences persistence — existing
- ✓ Dark/light theme support in Web UI — existing

### Active

<!-- Current scope. Building toward these. -->

- [ ] Fix Flux kustomization dependency chain — `es-06-infra` never becomes ready, cascading to apps and agents
- [ ] Generated output matches es-06 reference deployment structure (proper dependsOn, timeouts, wait flags)
- [ ] Infrastructure kustomization includes storage provisioner, storage classes, and network policies
- [ ] Post-deployment automation (secret mirroring, Fleet output config, OTEL dashboard import)
- [ ] Full lifecycle verification — generate → deploy → reconcile → verify with rollback on failure
- [ ] Comprehensive test coverage (unit, integration, e2e for all addons and flows)
- [ ] Graceful error handling with clear error messages throughout
- [ ] Rollback capabilities when deployment or reconciliation fails
- [ ] Config validation before deployment (catch bad kustomization structure early)
- [ ] Web UI enterprise polish (logging, monitoring hooks, deployment status feedback)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- OpenShift and AKS platforms for this milestone — focus on RKE2 + FluxCD first to establish the pattern
- Mobile app — web-first approach is sufficient
- Multi-cluster management — single cluster lifecycle first
- Custom Jinja2 templates — current `{{var}}` substitution is sufficient

## Context

The tool currently generates infrastructure that deploys but hangs during Flux reconciliation. The specific failure is a cascading dependency chain: `es-06-infra` kustomization never becomes ready, which blocks `es-06-apps`, which blocks `es-06-agents`. A working reference deployment exists at `/home/ubuntu/App-Projects-Workspace/es-06` that demonstrates the correct Flux kustomization structure with proper dependency chains, wait flags, timeouts, and post-deployment automation.

Key differences between the reference and generated output likely include:
- Missing or incorrect `dependsOn` declarations in Flux Kustomization CRs
- Insufficient timeouts (ECK needs 10-20 minutes to reconcile)
- Missing `wait: true` flags on dependent kustomizations
- Missing infrastructure prerequisites (storage provisioner, storage classes, network policies)
- No post-deployment automation (secret mirroring, Fleet configuration)

The Web UI is the primary user interface and needs enterprise-level polish — clear deployment status, error feedback, and lifecycle visibility.

## Constraints

- **Zero CLI dependencies**: Core CLI must remain Python stdlib only — no pip install for CLI usage
- **Platform focus**: RKE2 + FluxCD is the target platform for this milestone
- **Reference parity**: Generated output must match `es-06` deployment quality and structure
- **Web UI primary**: FastAPI + vanilla JS stack — no framework migration
- **Backward compatibility**: Existing CLI interface and addon API must not break

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| RKE2 + FluxCD first | Focus on one working platform before expanding to OpenShift/AKS | — Pending |
| Web UI as primary interface | Enterprise users expect a UI, not just CLI | — Pending |
| Use es-06 as reference deployment | Known working deployment provides concrete comparison target | — Pending |
| Full lifecycle scope | Enterprise means generate → deploy → reconcile → verify, not just scaffold | — Pending |

---
*Last updated: 2026-03-18 after initialization*
