# Requirements: Project Initializer

**Defined:** 2026-03-18
**Core Value:** Generated projects must deploy and reconcile end-to-end through the full GitOps lifecycle without manual intervention or hanging kustomizations.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Flux Deployment

- [x] **FLUX-01**: Generated Flux Kustomization CRs include correct `dependsOn` declarations matching the es-06 reference chain (root → infra → apps → agents)
- [x] **FLUX-02**: Generated Kustomization CRs include `wait: true` and appropriate timeouts (2m root, 10m infra, 20m apps/agents)
- [x] **FLUX-03**: Generated infrastructure kustomization includes Local Path Provisioner, storage classes (premium, standard), and network policies
- [x] **FLUX-04**: Generated output produces a complete kustomize directory structure (flux-system/, infrastructure/, apps/, agents/) that Flux can reconcile end-to-end
- [ ] **FLUX-05**: Post-deployment automation scripts are generated (secret mirroring, Fleet output config, OTEL dashboard import)
- [ ] **FLUX-06**: Deployment verification checks that all kustomizations reach Ready state within their timeout windows
- [ ] **FLUX-07**: Automated rollback triggers when any kustomization fails to reconcile (suspend, report, restore)

### Testing

- [ ] **TEST-01**: Unit tests exist for every addon generator verifying correct output structure and content
- [ ] **TEST-02**: Integration tests run the full scaffolding pipeline (analyze → generate → addon execution) and verify complete project output
- [ ] **TEST-03**: Generated YAML is validated for structural correctness (valid kustomization references, existing paths, required fields)
- [ ] **TEST-04**: Automated comparison validates generated output structure against es-06 reference deployment

### Error Handling

- [ ] **ERRH-01**: Config validation catches invalid kustomization structure, missing references, and malformed YAML before deployment
- [ ] **ERRH-02**: All failure paths produce clear, actionable error messages with suggested fixes
- [ ] **ERRH-03**: Pre-flight checks verify cluster connectivity, Flux installation, and required CRDs before attempting deployment
- [ ] **ERRH-04**: Rollback automation reverts deployment when reconciliation fails (Flux suspend, kubectl delete, status report)

### Web UI

- [ ] **WEBUI-01**: Web UI displays deployment progress with per-kustomization reconciliation status
- [ ] **WEBUI-02**: All operations are logged with timestamps for audit trail and troubleshooting
- [ ] **WEBUI-03**: Web UI shows live Flux reconciliation status from the cluster (polling kustomization readiness)

## v2 Requirements

Deferred to future milestones. Tracked but not in current roadmap.

### Platform Expansion

- **PLAT-01**: OpenShift 4.x platform support with ArgoCD integration
- **PLAT-02**: AKS platform support with Terraform modules
- **PLAT-03**: Multi-cluster deployment and management

### Web UI Advanced

- **WEBUI-04**: Deployment diff view comparing generated vs reference output
- **WEBUI-05**: Error display with actionable messages surfaced in frontend
- **WEBUI-06**: Real-time WebSocket updates (replace polling)

### Testing Advanced

- **TEST-05**: E2E deployment test against a real cluster
- **TEST-06**: Performance benchmarks for scaffolding generation

## Out of Scope

| Feature | Reason |
|---------|--------|
| OpenShift / AKS platforms | Focus on RKE2 + FluxCD first to establish the pattern |
| Mobile app | Web-first approach sufficient for enterprise DevOps users |
| Jinja2 templates | Current `{{var}}` substitution works; migration adds complexity without value |
| Multi-cluster management | Single cluster lifecycle must work first |
| ArgoCD for this milestone | FluxCD is the active deployment path; ArgoCD addon exists but not in scope |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FLUX-01 | Phase 1 | Complete (01-01) |
| FLUX-02 | Phase 1 | Complete (01-01) |
| FLUX-03 | Phase 1 | Complete (01-01) |
| FLUX-04 | Phase 1 | Complete |
| FLUX-05 | Phase 2 | Pending |
| FLUX-06 | Phase 2 | Pending |
| FLUX-07 | Phase 2 | Pending |
| TEST-01 | Phase 3 | Pending |
| TEST-02 | Phase 3 | Pending |
| TEST-03 | Phase 3 | Pending |
| TEST-04 | Phase 3 | Pending |
| ERRH-01 | Phase 2 | Pending |
| ERRH-02 | Phase 2 | Pending |
| ERRH-03 | Phase 2 | Pending |
| ERRH-04 | Phase 2 | Pending |
| WEBUI-01 | Phase 4 | Pending |
| WEBUI-02 | Phase 4 | Pending |
| WEBUI-03 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-03-18*
*Last updated: 2026-03-18 — FLUX-01, FLUX-02, FLUX-03 marked complete via plan 01-01*
