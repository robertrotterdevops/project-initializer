#!/usr/bin/env python3
"""Shared generation governance helpers for project-initializer."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

MANIFEST_SCHEMA_VERSION = "project-initializer-manifest.v1"
OPERATIONS_SCHEMA_VERSION = "project-initializer-operations.v1"
GENERATOR_NAME = "project-initializer"
GENERATOR_VERSION = os.environ.get("PROJECT_INITIALIZER_VERSION", "dev")

DEFAULT_OPERATION_SPECS = {
    "bootstrap-argocd": {
        "path": "scripts/bootstrap-argocd.sh",
        "title": "Bootstrap ArgoCD",
        "description": "Installs ArgoCD, applies AppProject/root app, and configures ingress/repository access.",
        "safe": True,
        "category": "operations",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "kubectl", "kubeconfig"],
        "recommended_order": 25,
        "arguments": [],
    },
    "argocd-sync": {
        "path": "scripts/argocd-sync.sh",
        "title": "ArgoCD Sync",
        "description": "Triggers ArgoCD sync and waits for healthy reconciliation.",
        "safe": True,
        "category": "operations",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "kubectl", "kubeconfig"],
        "recommended_order": 55,
        "arguments": [],
    },
    "preflight-check": {
        "path": "scripts/preflight-check.sh",
        "title": "Preflight Check",
        "description": "Runs generated preflight checks before deployment actions.",
        "safe": True,
        "category": "validation",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash"],
        "recommended_order": 10,
        "arguments": [],
    },
    "validate-config": {
        "path": "scripts/validate-config.sh",
        "title": "Validate Config",
        "description": "Runs generated configuration validation checks.",
        "safe": True,
        "category": "validation",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash"],
        "recommended_order": 20,
        "arguments": [],
    },
    "verify-deployment": {
        "path": "scripts/verify-deployment.sh",
        "title": "Verify Deployment",
        "description": "Runs generated post-deployment verification checks.",
        "safe": True,
        "category": "validation",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "kubectl", "kubeconfig"],
        "recommended_order": 50,
        "arguments": [],
    },
    "cluster-healthcheck": {
        "path": "scripts/cluster-healthcheck.sh",
        "title": "Cluster Healthcheck",
        "description": "Runs generated cluster and Kibana health checks.",
        "safe": True,
        "category": "validation",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "kubectl", "kubeconfig"],
        "recommended_order": 40,
        "arguments": [
            {
                "name": "kubeconfig_path",
                "label": "Kubeconfig Path",
                "required": False,
                "placeholder": "~/.kube/config",
                "description": "Optional kubeconfig override exposed as PI_ARG_KUBECONFIG_PATH.",
            }
        ],
    },
    "post-terraform-deploy": {
        "path": "scripts/post-terraform-deploy.sh",
        "title": "Post Terraform Deploy",
        "description": "Runs the generated post-terraform deployment helper.",
        "safe": False,
        "category": "operations",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "terraform", "kubectl", "kubeconfig"],
        "recommended_order": 30,
        "confirmation_required": True,
        "confirmation_mode": "project_name",
        "arguments": [
            {
                "name": "tfvars_file",
                "label": "Tfvars File",
                "required": False,
                "placeholder": "terraform.tfvars",
                "description": "Optional tfvars filename exposed as PI_ARG_TFVARS_FILE.",
            }
        ],
    },
    "import-dashboards": {
        "path": "scripts/import-dashboards.sh",
        "title": "Import Dashboards",
        "description": "Imports generated observability dashboards into Kibana.",
        "safe": False,
        "category": "operations",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "curl", "kibana_endpoint"],
        "recommended_order": 60,
        "confirmation_required": True,
        "confirmation_mode": "project_name",
        "arguments": [
            {
                "name": "kibana_url",
                "label": "Kibana URL",
                "required": False,
                "placeholder": "https://kibana.example.internal",
                "description": "Optional Kibana URL exposed as PI_ARG_KIBANA_URL.",
            }
        ],
    },
    "mirror-secrets": {
        "path": "scripts/mirror-secrets.sh",
        "title": "Mirror Secrets",
        "description": "Propagates generated secrets across required namespaces.",
        "safe": False,
        "category": "operations",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "kubectl", "kubeconfig"],
        "recommended_order": 70,
        "confirmation_required": True,
        "confirmation_mode": "project_name",
        "arguments": [],
    },
    "rollback": {
        "path": "scripts/rollback.sh",
        "title": "Rollback",
        "description": "Runs the generated rollback helper for the scaffolded deployment.",
        "safe": False,
        "category": "operations",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "kubectl", "kubeconfig"],
        "recommended_order": 90,
        "confirmation_required": True,
        "confirmation_mode": "project_name",
        "arguments": [],
    },
}

LICENSE_TEXT = {
    "Apache-2.0": """Apache License\nVersion 2.0, January 2004\nhttp://www.apache.org/licenses/\n\nLicensed under the Apache License, Version 2.0 (the \"License\");\nyou may not use this file except in compliance with the License.\nYou may obtain a copy of the License at\n\n    http://www.apache.org/licenses/LICENSE-2.0\n\nUnless required by applicable law or agreed to in writing, software\ndistributed under the License is distributed on an \"AS IS\" BASIS,\nWITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\nSee the License for the specific language governing permissions and\nlimitations under the License.\n""",
    "MIT": """MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the \"Software\"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.\n""",
}

TEXT_EXTENSIONS = {".py", ".sh", ".tf", ".yaml", ".yml", ".md", ".txt", ".gitignore"}
HEADER_PREFIX_BY_EXTENSION = {
    ".py": "#",
    ".sh": "#",
    ".tf": "#",
    ".yaml": "#",
    ".yml": "#",
}


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def default_license_policy() -> Dict[str, Any]:
    return {
        "license_id": "UNLICENSED",
        "mode": "user_selectable",
        "copyright_owner": "",
        "organization": "",
        "confidentiality": "internal",
    }


def default_header_policy() -> Dict[str, Any]:
    return {
        "mode": "none",
        "managed_header": False,
        "apply_to": [".py", ".sh", ".tf", ".yaml", ".yml", ".md"],
    }


def write_text_file(path: str | Path, content: str, executable: bool = False) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    if executable:
        target.chmod(0o755)
    return str(target)


def write_json_file(path: str | Path, payload: Dict[str, Any]) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return str(target)


def build_file_record(
    *,
    project_root: str | Path,
    full_path: str | Path,
    source_type: str,
    source_name: str,
    executable: bool = False,
) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    target = Path(full_path).resolve()
    try:
        relative_path = str(target.relative_to(root))
    except ValueError:
        relative_path = str(target)
    return {
        "path": relative_path,
        "source_type": source_type,
        "source_name": source_name,
        "executable": executable,
    }


def build_generation_manifest(
    *,
    project_name: str,
    description: str,
    project_path: str,
    platform: Optional[str],
    gitops_tool: Optional[str],
    iac_tool: Optional[str],
    analysis: Dict[str, Any],
    sizing_context: Optional[Dict[str, Any]],
    license_policy: Dict[str, Any],
    header_policy: Dict[str, Any],
    file_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    sizing_source = None
    sizing_schema = None
    if isinstance(sizing_context, dict):
        sizing_source = sizing_context.get("source")
        sizing_schema = sizing_context.get("schema_version")

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": utcnow_iso(),
        "generator": {
            "name": GENERATOR_NAME,
            "version": GENERATOR_VERSION,
        },
        "project": {
            "name": project_name,
            "description": description,
            "path": str(Path(project_path).resolve()),
            "platform": platform or "",
            "gitops_tool": gitops_tool or "",
            "iac_tool": iac_tool or "",
            "primary_category": analysis.get("primary_category", ""),
            "priority_chain": analysis.get("priority_chain", ""),
        },
        "source": {
            "sizing_source": sizing_source or "",
            "sizing_schema_version": sizing_schema or "",
        },
        "governance": {
            "license_policy": license_policy,
            "header_policy": header_policy,
        },
        "files": file_records,
    }


def _build_platform_runbook(platform: Optional[str], operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    platform_name = (platform or "").strip().lower()
    order_map = {item.get("key"): item.get("recommended_order", 999) for item in operations}
    base_steps = [
        {
            "key": "preflight-check",
            "title": "Preflight",
            "description": "Confirm generated inputs, scripts, and host prerequisites before deployment actions.",
            "docs": ["scripts/README.md", "docs/DEPLOYMENT_ATTENTION.md"],
        },
        {
            "key": "validate-config",
            "title": "Validate Configuration",
            "description": "Validate generated YAML, Terraform, and project-specific configuration before cluster changes.",
            "docs": ["docs/DEPLOYMENT_ATTENTION.md"],
        },
        {
            "key": "post-terraform-deploy",
            "title": "Post Terraform Apply",
            "description": "Run the scaffolded post-terraform helper after infrastructure is provisioned.",
            "docs": ["docs/DEPLOYMENT_PIPELINE.md", "terraform/README.md"],
        },
        {
            "key": "cluster-healthcheck",
            "title": "Cluster Healthcheck",
            "description": "Confirm cluster access and ECK/Kibana reachability after platform delivery steps.",
            "docs": ["scripts/README.md", "docs/DEPLOYMENT_PIPELINE.md"],
        },
        {
            "key": "verify-deployment",
            "title": "Verify Deployment",
            "description": "Run end-to-end verification after workloads reconcile.",
            "docs": ["scripts/README.md", "docs/DEPLOYMENT_PIPELINE.md"],
        },
        {
            "key": "import-dashboards",
            "title": "Import Dashboards",
            "description": "Load generated observability dashboards after Kibana is reachable.",
            "docs": ["docs/OBSERVABILITY_ROLLOUT.md"],
        },
        {
            "key": "mirror-secrets",
            "title": "Mirror Secrets",
            "description": "Propagate generated secrets when namespaces or agent consumers need them.",
            "docs": ["docs/DEPLOYMENT_PIPELINE.md"],
        },
        {
            "key": "rollback",
            "title": "Rollback",
            "description": "Use only when deployment validation fails and recovery is required.",
            "docs": ["docs/DEPLOYMENT_ATTENTION.md"],
        },
    ]
    platform_notes = {
        "proxmox": "Reference path for VM-backed RKE2 delivery. Expect Terraform and bootstrap steps before cluster verification.",
        "rke2": "RKE2 workload-cluster flow. Run bootstrap/post-terraform before Kubernetes verification.",
        "openshift": "OpenShift day-1/day-2 flow. Cluster auth and route exposure checks matter before observability imports.",
        "aks": "Managed AKS flow. Terraform and ingress readiness should be confirmed before Kibana/dashboard actions.",
    }
    steps = []
    for step in base_steps:
        if step["key"] not in order_map:
            continue
        steps.append({
            **step,
            "recommended_order": order_map[step["key"]],
        })
    steps.sort(key=lambda item: item.get("recommended_order", 999))
    return [{
        "platform": platform_name or "generic",
        "note": platform_notes.get(platform_name, "Follow the ordered operations to move from validation to deployment safely."),
        "steps": steps,
    }]


def build_operations_manifest(
    *,
    project_name: str,
    project_path: str,
    platform: Optional[str],
    gitops_tool: Optional[str],
    iac_tool: Optional[str],
    file_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    file_paths = {item.get("path", "") for item in file_records}
    operations: List[Dict[str, Any]] = []
    for key, spec in DEFAULT_OPERATION_SPECS.items():
        if spec["path"] not in file_paths:
            continue
        confirmation_mode = spec.get("confirmation_mode") if spec.get("confirmation_required") else None
        confirmation_phrase = project_name if confirmation_mode == "project_name" else ""
        operations.append(
            {
                "key": key,
                "path": spec["path"],
                "title": spec["title"],
                "description": spec["description"],
                "safe": spec["safe"],
                "category": spec["category"],
                "execution_context": "project_root",
                "applies_to": list(spec.get("applies_to", ["local", "remote"])),
                "prerequisites": list(spec.get("prerequisites", [])),
                "recommended_order": spec.get("recommended_order", 999),
                "arguments": list(spec.get("arguments", [])),
                "confirmation_required": bool(spec.get("confirmation_required", False)),
                "confirmation_mode": confirmation_mode or "",
                "confirmation_phrase": confirmation_phrase,
            }
        )
    return {
        "schema_version": OPERATIONS_SCHEMA_VERSION,
        "generated_at": utcnow_iso(),
        "generator": {
            "name": GENERATOR_NAME,
            "version": GENERATOR_VERSION,
        },
        "project": {
            "name": project_name,
            "path": str(Path(project_path).resolve()),
            "platform": platform or "",
            "gitops_tool": gitops_tool or "",
            "iac_tool": iac_tool or "",
        },
        "operations": operations,
        "runbooks": _build_platform_runbook(platform, operations),
    }


def license_text_for_policy(license_policy: Dict[str, Any]) -> str:
    license_id = (license_policy or {}).get("license_id", "UNLICENSED")
    owner = (license_policy or {}).get("copyright_owner") or (license_policy or {}).get("organization") or "the project owner"
    year = datetime.now(UTC).year
    if license_id in LICENSE_TEXT:
        text = LICENSE_TEXT[license_id]
        if license_id == "MIT":
            return f"Copyright (c) {year} {owner}\n\n{text}"
        return text
    if license_id == "UNLICENSED":
        return (
            "All rights reserved.\n\n"
            f"Copyright (c) {year} {owner}\n\n"
            "This generated project does not declare an open-source license. "
            "Review organizational policy before redistribution.\n"
        )
    return (
        f"License: {license_id}\n\n"
        "No embedded license template is available for this identifier. "
        "Review and replace this file with the approved text for your organization.\n"
    )


def notice_text_for_policy(project_name: str, license_policy: Dict[str, Any]) -> str:
    owner = (license_policy or {}).get("organization") or (license_policy or {}).get("copyright_owner") or "Project team"
    confidentiality = (license_policy or {}).get("confidentiality", "internal")
    return (
        f"{project_name}\n"
        f"Generated by {GENERATOR_NAME} {GENERATOR_VERSION}.\n"
        f"Owner: {owner}\n"
        f"Confidentiality: {confidentiality}\n"
    )


def generated_by_text(
    *,
    project_name: str,
    platform: Optional[str],
    gitops_tool: Optional[str],
    iac_tool: Optional[str],
    license_policy: Dict[str, Any],
    header_policy: Dict[str, Any],
    manifest_path: str | Path,
    file_records: Iterable[Dict[str, Any]],
) -> str:
    addon_names = sorted(
        {
            item.get("source_name", "")
            for item in file_records
            if item.get("source_type") == "addon" and item.get("source_name")
        }
    )
    addon_summary = "\n".join(f"- `{name}`" for name in addon_names) if addon_names else "- none"
    return f"""# Generated by {GENERATOR_NAME}

- Generated at: {utcnow_iso()}
- Generator version: `{GENERATOR_VERSION}`
- Project: `{project_name}`
- Platform: `{platform or ''}`
- GitOps: `{gitops_tool or ''}`
- IaC: `{iac_tool or ''}`
- License: `{license_policy.get('license_id', 'UNLICENSED')}`
- Confidentiality: `{license_policy.get('confidentiality', 'internal')}`
- Header mode: `{header_policy.get('mode', 'none')}`
- Manifest: `{Path(manifest_path).name}`
- Operations manifest: `project-initializer-operations.json`

## Addons

{addon_summary}

## Notes

- Files with supported text extensions may include managed headers depending on policy.
- Machine-consumed JSON outputs are tracked in the manifest instead of receiving inline comments.
- Review generated infrastructure and security defaults before deployment.
"""


def governance_docs(
    *,
    project_name: str,
    project_root: str | Path,
    platform: Optional[str],
    gitops_tool: Optional[str],
    iac_tool: Optional[str],
    license_policy: Dict[str, Any],
    header_policy: Dict[str, Any],
    manifest_path: str | Path,
    file_records: Iterable[Dict[str, Any]],
) -> Dict[str, str]:
    root = Path(project_root)
    return {
        str(root / "LICENSE"): license_text_for_policy(license_policy),
        str(root / "NOTICE"): notice_text_for_policy(project_name, license_policy),
        str(root / "GENERATED_BY.md"): generated_by_text(
            project_name=project_name,
            platform=platform,
            gitops_tool=gitops_tool,
            iac_tool=iac_tool,
            license_policy=license_policy,
            header_policy=header_policy,
            manifest_path=manifest_path,
            file_records=file_records,
        ),
    }


def render_managed_header(
    *,
    relative_path: str,
    source_name: str,
    license_policy: Dict[str, Any],
    header_policy: Dict[str, Any],
) -> str:
    mode = (header_policy or {}).get("mode", "none")
    if mode == "none":
        return ""
    license_id = (license_policy or {}).get("license_id", "UNLICENSED")
    confidentiality = (license_policy or {}).get("confidentiality", "internal")
    owner = (license_policy or {}).get("copyright_owner") or (license_policy or {}).get("organization")
    lines = [
        "Generated by project-initializer. Manual review required before deployment.",
        f"Path: {relative_path}",
        f"Source: {source_name}",
        f"License: {license_id}",
        f"Confidentiality: {confidentiality}",
    ]
    if owner:
        lines.append(f"Owner: {owner}")
    if mode == "full":
        lines.append(f"Generated at: {utcnow_iso()}")
        lines.append(f"Generator version: {GENERATOR_VERSION}")
    return "\n".join(lines)


def _comment_prefix_for_path(path: Path) -> Optional[str]:
    if path.suffix == ".md":
        return None
    if path.name == ".gitignore":
        return "#"
    return HEADER_PREFIX_BY_EXTENSION.get(path.suffix)


def _prepend_header(content: str, header_block: str, path: Path) -> str:
    if not header_block:
        return content
    if path.suffix == ".md":
        block = f"<!--\n{header_block}\n-->\n\n"
    else:
        prefix = _comment_prefix_for_path(path)
        if not prefix:
            return content
        block = "\n".join(f"{prefix} {line}" if line else prefix for line in header_block.splitlines()) + "\n\n"
    if content.startswith("#!"):
        first_line, remainder = content.split("\n", 1) if "\n" in content else (content, "")
        return first_line + "\n" + block + remainder
    return block + content


def apply_header_policy(
    *,
    project_root: str | Path,
    file_records: Iterable[Dict[str, Any]],
    license_policy: Dict[str, Any],
    header_policy: Dict[str, Any],
    skip_paths: Optional[Iterable[str]] = None,
) -> None:
    mode = (header_policy or {}).get("mode", "none")
    if mode == "none":
        return
    allowed = set((header_policy or {}).get("apply_to", []))
    root = Path(project_root)
    skipped = set(skip_paths or [])
    for item in file_records:
        relative_path = item.get("path", "")
        if relative_path in skipped:
            continue
        path = root / relative_path
        if not path.exists() or not path.is_file():
            continue
        suffix = path.suffix
        if suffix not in allowed and path.name not in {".gitignore"}:
            continue
        if path.suffix not in TEXT_EXTENSIONS and path.name not in {".gitignore", "LICENSE", "NOTICE"}:
            continue
        content = path.read_text(encoding="utf-8")
        header_block = render_managed_header(
            relative_path=relative_path,
            source_name=item.get("source_name", "unknown"),
            license_policy=license_policy,
            header_policy=header_policy,
        )
        if not header_block:
            continue
        if "Generated by project-initializer." in content[:400]:
            continue
        path.write_text(_prepend_header(content, header_block, path), encoding="utf-8")


def build_generation_validation_report(
    *,
    project_root: str | Path,
    manifest_path: str | Path,
    file_records: Iterable[Dict[str, Any]],
    license_policy: Dict[str, Any],
    header_policy: Dict[str, Any],
) -> Dict[str, Any]:
    root = Path(project_root)
    items: List[Dict[str, Any]] = []

    def add(code: str, severity: str, message: str) -> None:
        items.append({"scope": "generation", "code": code, "severity": severity, "message": message})

    expected_core = ["README.md", "AGENTS.md", ".opencode/context.md"]
    expected_governance = ["LICENSE", "NOTICE", "GENERATED_BY.md", "project-initializer-manifest.json", "project-initializer-operations.json"]
    for relative_path in expected_core + expected_governance:
        if not (root / relative_path).exists():
            add("missing_expected_file", "error", f"Expected generated file is missing: {relative_path}")

    if not Path(manifest_path).exists():
        add("missing_manifest", "error", "Generation manifest was not written.")

    mode = (header_policy or {}).get("mode", "none")
    if mode != "none":
        readme_path = root / "README.md"
        if readme_path.exists():
            readme_text = readme_path.read_text(encoding="utf-8")
            if "Generated by project-initializer." not in readme_text[:500]:
                add("missing_managed_header", "warning", "Managed header policy is enabled but README.md does not contain the managed header.")
        else:
            add("missing_managed_header_target", "warning", "Managed header policy is enabled but README.md is missing.")

    total_files = 0
    addon_files = 0
    for item in file_records:
        total_files += 1
        if item.get("source_type") == "addon":
            addon_files += 1

    license_id = (license_policy or {}).get("license_id", "UNLICENSED")
    confidentiality = (license_policy or {}).get("confidentiality", "internal")
    ok = not any(item["severity"] == "error" for item in items)
    return {
        "ok": ok,
        "generated_at": utcnow_iso(),
        "summary": {
            "total_files": total_files,
            "addon_files": addon_files,
            "license_id": license_id,
            "confidentiality": confidentiality,
            "header_mode": mode,
        },
        "items": items,
    }
