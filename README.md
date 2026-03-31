# Project Initializer — Documentation
Last updated: 2026-03-31

## 1) Product Scope
Project Initializer generates deployment-ready repositories for Elasticsearch/ECK platform delivery,
              with GitOps and infrastructure automation scaffolds for:

## 2) Create Project Workflow
- Choose platform, target mode (local/remote), and destination path.
- Load Elastic sizing input file (.json contract).
- Review sizing preview and generated pools/components.
- Configure Git options (optional).
- Create project via streamed execution logs.
For node tier placement, if a requested selector is not available, generation must use technology-aware fallback values
              (for example known node pools / supported labels), not invalid placeholder tiers.

## 3) Validate & Deploy Workflow
Use this page post-generation to run diagnostics and scripts in controlled order, with run history and export.
- Load Summary: inventory generated scripts and readiness checks.
- Run Diagnostics: non-mutating validation of project content and environment assumptions.
- Run Validation: classification-based pass/warning/blocking checks.
- Run Script: execute selected generated script (local or remote context).
- Mutating steps remain explicit and auditable.
- post-terraform-deploy is treated as high-risk and should require user confirmation.
- Script output is summarized for readability; raw output remains exportable from timeline/history.

## 4) Status Page (Live Cluster)
The Status tab is intended for live reconciliation and endpoint visibility, not only raw command output.
- Cluster Overview: high-level state and GitOps reconciliation readiness.
- Access & Kubeconfig: context resolution and API/node reachability.
- Applications / Kustomizations: ArgoCD Applications or Flux Kustomizations depending on deployment type.
- Workloads & Endpoints: Elasticsearch pods, Fleet Server pods, Elastic Agent pods, ingress/routes.
- Live Cluster: embedded readonly `k9s` session for real-time cluster inspection.

## 5) Kubeconfig Resolution Model
After first successful cluster health-check, kubeconfig is expected to be copied/generated into project-aware locations,
and app status checks should resolve from those paths before legacy defaults.
```
Expected resolution order (conceptual):
1) Explicit override provided by user/script argument
2) Project-local kubeconfig (for local/remote generated project context)
3) User home fallback (~/.kube/<project>, ~/.kube/config)
4) Platform defaults only when explicitly required
```
Local/Remote generation path is the workspace location where project files are created, not automatically the runtime cluster control-plane host.

## 6) Platform Coverage & Expansion

## 7) Operational Guidelines
- Keep script execution states visible (running/spinner/progress/end).
- Use foldable output blocks for long logs; emphasize actionable summary first.
- Persist and expose run history for audit and rollback context.
- Expose credential outputs only where appropriate; avoid leaking sensitive secrets in default views.
- Keep remote commands fast and bounded by timeouts to avoid UI hangs.
- Run live cluster inspection in readonly mode by default.
- Require `k9s` on the remote host for remote Status terminal sessions.

## 8) Licensing, Headers, and Generated Artifacts
License and header strategy should be deterministic for generated files and folders, based on user policy profile.
- Recommended default SPDX identifier: Apache-2.0 (if aligned with project policy).
- Generated files should carry consistent copyright owner/year templates.
- Policy profile should control whether headers are required, optional, or suppressed by file type.
```
# Example header marker
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 <Organization>
```

## 9) Troubleshooting Checklist
- Generation mismatch: verify sizing JSON contract schema and parsed preview.
- Missing pools/tier values: inspect terraform.tfvars.example and /sizing output together.
- Status shows stale kubeconfig path: validate latest run of cluster-healthcheck and resolved kubeconfig source.
- Slow UI script actions: inspect remote command timeouts and streaming feedback behavior.
- Endpoint missing: verify ingress/route resource exists in cluster namespace.
- Live cluster pane unavailable: confirm `k9s` exists on the remote host and the project kubeconfig was exported by post-deploy automation.
