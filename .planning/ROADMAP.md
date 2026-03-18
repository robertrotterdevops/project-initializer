# Roadmap: Project Initializer

## Overview

The tool already scaffolds projects but generates Flux manifests that hang during reconciliation. This roadmap takes the generated output from "almost works" to "deploys end-to-end without intervention" — fixing the manifest structure first, layering in lifecycle automation and error handling, validating everything with tests, and surfacing status in the Web UI.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Correct Output** - Fix generated Flux manifests to match es-06 reference structure (completed 2026-03-18)
- [ ] **Phase 2: Deployment Lifecycle** - Add post-deploy automation, pre-flight checks, and rollback
- [ ] **Phase 3: Test Coverage** - Unit, integration, and structural validation tests for all addons and flows
- [ ] **Phase 4: Web UI Polish** - Surface deployment progress, live reconciliation status, and audit logging

## Phase Details

### Phase 1: Correct Output
**Goal**: Generated Flux manifests are structurally correct and reconcile end-to-end without manual intervention
**Depends on**: Nothing (first phase)
**Requirements**: FLUX-01, FLUX-02, FLUX-03, FLUX-04
**Success Criteria** (what must be TRUE):
  1. Generated Kustomization CRs contain `dependsOn` chains that match the es-06 reference (root → infra → apps → agents)
  2. Generated Kustomization CRs include `wait: true` and timeouts of 2m (root), 10m (infra), 20m (apps/agents)
  3. Generated infrastructure kustomization includes Local Path Provisioner, storage classes (premium, standard), and network policies
  4. The generated directory structure (flux-system/, infrastructure/, apps/, agents/) can be applied to a cluster and all kustomizations reach Ready state
**Plans:** 2/2 plans complete
Plans:
- [x] 01-01-PLAN.md — Fix complexity-dependent timeout/interval values in Flux CR generator
- [x] 01-02-PLAN.md — Full pipeline end-to-end verification against es-06 reference

### Phase 2: Deployment Lifecycle
**Goal**: The tool manages the full deploy → reconcile → verify → rollback lifecycle without manual steps
**Depends on**: Phase 1
**Requirements**: FLUX-05, FLUX-06, FLUX-07, ERRH-01, ERRH-02, ERRH-03, ERRH-04
**Success Criteria** (what must be TRUE):
  1. Post-deployment scripts are generated and execute secret mirroring, Fleet output config, and OTEL dashboard import automatically
  2. Deployment verification polls kustomization readiness and reports pass/fail within defined timeout windows
  3. Pre-flight checks block deployment when cluster connectivity, Flux installation, or required CRDs are missing — with a clear error message
  4. Rollback triggers automatically on reconciliation failure — suspending kustomizations, reporting state, and restoring previous configuration
  5. Every failure path produces an actionable error message with a suggested fix
**Plans:** 1/2 plans executed
Plans:
- [ ] 02-01-PLAN.md — Create deployment lifecycle addon with post-deploy scripts and pre-flight checks
- [ ] 02-02-PLAN.md — Add deployment verification, rollback, and config validation scripts

### Phase 3: Test Coverage
**Goal**: Every addon, flow, and structural assumption is validated by automated tests
**Depends on**: Phase 1
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. Every addon generator has unit tests that assert correct output structure and required field values
  2. An integration test runs the full analyze → generate → addon pipeline and verifies the complete project output exists on disk
  3. Generated YAML passes structural validation — valid kustomization references, existing paths, no missing required fields
  4. An automated comparison test verifies the generated output structure matches the es-06 reference deployment
**Plans**: TBD

### Phase 4: Web UI Polish
**Goal**: The Web UI gives full visibility into deployment progress and reconciliation status
**Depends on**: Phase 2
**Requirements**: WEBUI-01, WEBUI-02, WEBUI-03
**Success Criteria** (what must be TRUE):
  1. The Web UI shows per-kustomization reconciliation status that updates as the deployment progresses
  2. Every operation (scaffold, deploy, verify, rollback) is logged with a timestamp visible in the UI
  3. Live Flux reconciliation status is polled from the cluster and displayed without requiring a page refresh
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Correct Output | 2/2 | Complete   | 2026-03-18 |
| 2. Deployment Lifecycle | 1/2 | In Progress|  |
| 3. Test Coverage | 0/? | Not started | - |
| 4. Web UI Polish | 0/? | Not started | - |
