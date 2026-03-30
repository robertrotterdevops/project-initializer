#!/usr/bin/env python3
"""
Project Structure Generator for the project-initializer skill.
Generates project scaffolding based on analysis results.

Zero external dependencies -- uses only Python stdlib.
"""

import datetime
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Ensure sibling module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from project_analyzer import ProjectAnalyzer, analyze_project  # noqa: E402
from addon_loader import AddonLoader, run_matched_addons_with_trace  # noqa: E402
from generation_governance import (  # noqa: E402
    apply_header_policy,
    build_file_record,
    build_generation_manifest,
    build_generation_validation_report,
    build_operations_manifest,
    default_header_policy,
    default_license_policy,
    governance_docs,
    write_json_file,
    write_text_file,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# ------------------------------------------------------------------
# Template helpers
# ------------------------------------------------------------------


def render_template(template_content: str, context: Dict) -> str:
    """Simple {{var}} replacement -- no Jinja2 needed."""
    rendered = template_content
    for key, value in context.items():
        placeholder = "{{" + key + "}}"
        if isinstance(value, list):
            rendered = rendered.replace(placeholder, ", ".join(str(v) for v in value))
        else:
            rendered = rendered.replace(placeholder, str(value))
    return rendered


def prepare_template_context(analysis_result: Dict) -> Dict:
    """Pre-render list variables into strings so templates need only {{var}} placeholders."""
    skills = analysis_result.get("assigned_skills", [])
    primary = analysis_result.get("primary_skill") or "Unknown"
    secondary = [s for s in skills if s != primary]
    project_name = analysis_result.get("project_name", "project")

    # Pre-render secondary skills as markdown list
    if secondary:
        secondary_list = "\n".join(
            f"- **{s}**: Supplementary expertise" for s in secondary
        )
    else:
        secondary_list = "- (none)"

    # Pre-render skill load commands (secondary only)
    if secondary:
        load_cmds = "\n".join(f"load skill {s}" for s in secondary)
    else:
        load_cmds = "# (no secondary skills)"

    # Pre-render full skill load commands (all skills)
    if skills:
        load_cmds_full = "\n".join(f"load skill {s}" for s in skills)
    else:
        load_cmds_full = "# (no skills assigned)"

    # Primary skill capabilities
    analyzer = ProjectAnalyzer()
    caps = analyzer.skill_mapping.get(primary, {}).get("capabilities", [])
    if caps:
        caps_text = ", ".join(caps)
    else:
        caps_text = "General-purpose DevOps capabilities"

    # Project structure tree
    structure = analysis_result.get("project_structure", [])
    tree_lines = [f"{project_name}/"]
    for i, item in enumerate(structure):
        connector = "└── " if i == len(structure) - 1 else "├── "
        tree_lines.append(f"  {connector}{item}")
    tree_text = "\n".join(tree_lines)

    # Ambiguous categories
    ambiguous = analysis_result.get("ambiguous_categories", [])

    return {
        "project_name": project_name,
        "project_description": analysis_result.get("description", ""),
        "primary_skill": primary,
        "assigned_skills": skills,
        "assigned_skills_list": ", ".join(skills) if skills else "(none)",
        "secondary_skills_list": secondary_list,
        "skill_load_commands": load_cmds,
        "skill_load_commands_full": load_cmds_full,
        "primary_skill_capabilities": caps_text,
        "primary_category": analysis_result.get("primary_category", "generic"),
        "ambiguous_categories": ambiguous,
        "priority_chain": analysis_result.get("priority_chain", "default"),
        "analysis_confidence": str(analysis_result.get("analysis_confidence", 0)),
        "project_structure_tree": tree_text,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "author": "Project Initializer",
    }


# ------------------------------------------------------------------
# File-system helpers
# ------------------------------------------------------------------


def _string_or_na(value: object, fallback: str = "n/a") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _int_or_zero(value: object) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _format_readme_sizing_section(sizing_context: Optional[Dict], context: Dict) -> str:
    if not sizing_context:
        return ""

    metadata = sizing_context.get("metadata") or {}
    summary = sizing_context.get("summary") or {}
    inputs = sizing_context.get("inputs") or {}
    raw = sizing_context.get("raw") or {}

    project_name = _string_or_na(metadata.get("name"))
    customer = _string_or_na(metadata.get("customer"))
    project_description = _string_or_na(metadata.get("description"))
    project_id = _string_or_na(metadata.get("project_id"))
    user_name = _string_or_na(metadata.get("user_name"))

    platform = _string_or_na(
        sizing_context.get("platform_detected") or context.get("platform") or context.get("platform_display")
    )
    health_score = _string_or_na(sizing_context.get("health_score"))

    ingest_per_day = _string_or_na(
        inputs.get("daily_ingest_gb")
        or inputs.get("ingest_gb_per_day")
        or inputs.get("ingest_per_day_gb")
    )
    retention_days = _string_or_na(
        inputs.get("retention_days")
        or inputs.get("total_retention_days")
    )
    workload_type = _string_or_na(inputs.get("workload_type"))

    hot = sizing_context.get("data_nodes") or {}
    cold = sizing_context.get("cold_nodes") or {}
    frozen = sizing_context.get("frozen_nodes") or {}
    kibana = sizing_context.get("kibana") or {}
    fleet = sizing_context.get("fleet_server") or {}

    hot_count = _int_or_zero(hot.get("count"))
    cold_count = _int_or_zero(cold.get("count"))
    frozen_count = _int_or_zero(frozen.get("count"))

    pool_root = (
        sizing_context.get("rke2")
        or sizing_context.get("openshift")
        or sizing_context.get("aks")
        or {}
    )
    pools = list(pool_root.get("pools") or [])

    generated_at = _string_or_na(
        raw.get("generated_at")
        or raw.get("created_at")
        or raw.get("timestamp")
    )

    lines = [
        "",
        "## Deployment Snapshot",
        "",
        "### Project Header (from sizing input)",
        f"- Project Name: `{project_name}`",
        f"- Customer: `{customer}`",
        f"- Description: {project_description}",
        f"- Project ID: `{project_id}`",
        f"- Owner / User: `{user_name}`",
        "",
        "### Cluster Details",
        f"- Platform: `{platform}`",
        f"- Health Score: `{health_score}/100`",
        f"- Total Nodes: `{_string_or_na(summary.get('total_nodes'))}`",
        f"- Data Nodes: `{_string_or_na(summary.get('total_data_nodes'))}`",
        f"- Workload Type: `{workload_type}`",
        f"- Ingest per Day: `{ingest_per_day} GB`",
        f"- Retention: `{retention_days} days`",
        "",
        "### Tier Allocation",
        f"- Hot Tier: count={hot_count}, cpu={_string_or_na(hot.get('cpu'))}, ram={_string_or_na(hot.get('memory'))}, storage={_string_or_na(hot.get('storage'))}",
        f"- Cold Tier: count={cold_count}, cpu={_string_or_na(cold.get('cpu'))}, ram={_string_or_na(cold.get('memory'))}, storage={_string_or_na(cold.get('storage'))}",
        f"- Frozen Tier: count={frozen_count}, cpu={_string_or_na(frozen.get('cpu'))}, ram={_string_or_na(frozen.get('memory'))}, storage={_string_or_na(frozen.get('storage'))}",
        "",
        "### Supporting Services",
        f"- Kibana Pods: `{_string_or_na(kibana.get('count'))}` (cpu={_string_or_na(kibana.get('cpu'))}, ram={_string_or_na(kibana.get('memory'))})",
        f"- Fleet Server Pods: `{_string_or_na(fleet.get('count'))}` (cpu={_string_or_na(fleet.get('cpu'))}, ram={_string_or_na(fleet.get('memory'))})",
    ]

    if pools:
        lines.append("")
        lines.append("### Pool Layout")
        for pool in pools:
            lines.append(
                f"- {pool.get('name', 'pool')}: nodes={_string_or_na(pool.get('nodes') or pool.get('node_count'))}, "
                f"vcpu/node={_string_or_na(pool.get('vcpu_per_node'))}, "
                f"ram/node={_string_or_na(pool.get('ram_gb_per_node'))}Gi, "
                f"disk/node={_string_or_na(pool.get('disk_gb_per_node') or pool.get('disk_gb'))}Gi"
            )

    lines.extend(
        [
            "",
            "### Dates",
            f"- Sizing Export Generated: `{generated_at}`",
            f"- Scaffold Generated: `{_string_or_na(context.get('timestamp'))}`",
            "",
        ]
    )

    return "\n".join(lines)


def create_project_structure(base_path: str, structure: List[str]) -> List[str]:
    """Create directory structure. Items ending with / are dirs, else files."""
    created = []
    for item in structure:
        item_path = os.path.join(base_path, item)
        if item.endswith("/"):
            os.makedirs(item_path, exist_ok=True)
        else:
            parent = os.path.dirname(item_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            if not os.path.exists(item_path):
                with open(item_path, "w") as fh:
                    fh.write("")
        created.append(item_path)
    return created


def generate_readme(
    base_path: str,
    context: Dict,
    template_path: str,
    sizing_context: Optional[Dict] = None,
) -> str:
    """Render and write README.md."""
    try:
        with open(template_path, "r") as fh:
            template = fh.read()
    except FileNotFoundError:
        template = "# {{project_name}}\n\n{{project_description}}\n"

    content = render_template(template, context)
    content = content.rstrip() + "\n" + _format_readme_sizing_section(sizing_context, context)
    out = os.path.join(base_path, "README.md")
    return write_text_file(out, content)


def generate_agents_doc(base_path: str, context: Dict, template_path: str) -> str:
    """Render and write AGENTS.md."""
    try:
        with open(template_path, "r") as fh:
            template = fh.read()
    except FileNotFoundError:
        template = (
            "# Agent Coordination Guide\n\n"
            "## Primary Skill\n\n"
            "**{{primary_skill}}** — {{primary_skill_capabilities}}\n\n"
            "## Assigned Skills\n\n"
            "{{secondary_skills_list}}\n\n"
            "## Priority Chain\n\n"
            "Chain: `{{priority_chain}}` | Category: `{{primary_category}}`\n\n"
            "### Load Commands\n\n"
            "```\n{{skill_load_commands_full}}\n```\n"
        )

    content = render_template(template, context)
    out = os.path.join(base_path, "AGENTS.md")
    return write_text_file(out, content)


def generate_basic_files(base_path: str, context: Dict) -> List[str]:
    """Generate .gitignore, starter Terraform, and K8s files."""
    generated = []

    # .gitignore
    gitignore = os.path.join(base_path, ".gitignore")
    write_text_file(
        gitignore,
        ".opencode/\n.venv/\n__pycache__/\n*.pyc\nenv/\nvenv/\n"
        ".vscode/\n.idea/\n*.swp\n.DS_Store\nThumbs.db\n",
    )
    generated.append(gitignore)

    # Terraform starters
    tf_dir = os.path.join(base_path, "terraform")
    if os.path.isdir(tf_dir):
        main_tf = os.path.join(tf_dir, "main.tf")
        write_text_file(
            main_tf,
            render_template(
                "# Terraform configuration for {{project_name}}\n\n"
                'terraform {\n  required_version = ">= 1.0"\n}\n',
                context,
            ),
        )
        generated.append(main_tf)

        vars_tf = os.path.join(tf_dir, "variables.tf")
        write_text_file(
            vars_tf,
            render_template(
                '# Input variables\n\nvariable "project_name" {\n'
                '  description = "Project name"\n  type        = string\n'
                '  default     = "{{project_name}}"\n}\n\n'
                'variable "environment" {\n  description = "Environment"\n'
                '  type        = string\n  default     = "dev"\n}\n',
                context,
            ),
        )
        generated.append(vars_tf)

    # K8s namespace
    k8s_dir = os.path.join(base_path, "k8s")
    if os.path.isdir(k8s_dir):
        ns = os.path.join(k8s_dir, "namespace.yaml")
        write_text_file(
            ns,
            render_template(
                "apiVersion: v1\nkind: Namespace\nmetadata:\n"
                "  name: {{project_name}}\n  labels:\n"
                "    project: {{project_name}}\n",
                context,
            ),
        )
        generated.append(ns)

    return generated


def generate_opencode_context(base_path: str, context: Dict) -> str:
    """Generate .opencode/context.md for session bootstrap."""
    opencode_dir = os.path.join(base_path, ".opencode")
    os.makedirs(opencode_dir, exist_ok=True)

    # Build context file content
    skills = context.get("assigned_skills", [])
    primary_skill = context.get("primary_skill", "")
    platform = context.get("platform", "")
    gitops_tool = context.get("gitops_tool", "")

    # Build ambiguity note if categories are close
    ambiguous = context.get("ambiguous_categories", [])
    if ambiguous:
        ambiguity_note = (
            f"\n> **Note:** Category classification is ambiguous. "
            f"The following categories scored within 1 point of the primary "
            f"category (`{context.get('primary_category', 'generic')}`): "
            f"{', '.join(f'`{c}`' for c in ambiguous)}. "
            f"Consider reviewing the priority chain if results seem off.\n"
        )
    else:
        ambiguity_note = ""

    content = f"""# OpenCode Session Context

## Project: {context.get("project_name", "Unknown")}

{context.get("project_description", "")}
{ambiguity_note}
## Active Skills

Primary skill for this project:

```
load skill {primary_skill}
```

### All Assigned Skills

{context.get("skill_load_commands_full", "# (no skills assigned)")}

## Project Configuration

| Setting | Value |
|---------|-------|
| Category | {context.get("primary_category", "generic")} |
| Priority Chain | {context.get("priority_chain", "default")} |
| Platform | {context.get("platform_display", "Not specified")} |
| GitOps Tool | {context.get("gitops_display", "Not specified")} |

## Quick Reference

### Primary Skill Capabilities

{context.get("primary_skill_capabilities", "General-purpose DevOps capabilities")}

### Project Structure

```
{context.get("project_structure_tree", "(no structure)")}
```

## Session Notes

*Add notes about your current session here.*

---

*Generated by project-initializer on {context.get("timestamp", "unknown")}*
"""

    out = os.path.join(opencode_dir, "context.md")
    return write_text_file(out, content)


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


def initialize_project(
    project_name: str,
    description: str,
    target_directory: str,
    focus_areas: Optional[List[str]] = None,
    custom_templates: Optional[Dict[str, str]] = None,
    platform: Optional[str] = None,
    gitops_tool: Optional[str] = None,
    iac_tool: Optional[str] = None,
    repo_url: Optional[str] = None,
    git_token: Optional[str] = None,
    fallback_storage_class: Optional[str] = None,
    target_revision: Optional[str] = None,
    sizing_context: Optional[Dict] = None,
    forced_chain: Optional[str] = None,
    enable_metrics_server: bool = False,
    enable_otel_collector: bool = False,
    license_policy: Optional[Dict] = None,
    header_policy: Optional[Dict] = None,
) -> Dict:
    """
    Analyse, scaffold, and generate documentation for a new project.

    Args:
        project_name: Name of the project (kebab-case recommended)
        description: Short project description
        target_directory: Where to create the project
        focus_areas: Optional list of focus keywords
        custom_templates: Optional custom template paths
        platform: Target platform (rke2, openshift, aks) - from interactive mode
        gitops_tool: GitOps tool (flux, argo, none) - from interactive mode
        sizing_context: ES sizing context dict - from sizing skill
        iac_tool: IaC tool selection (terraform, none)
        repo_url: Git repository URL used by GitOps manifests
        target_revision: Git branch/revision used by GitOps manifests
        forced_chain: Override the priority chain selection
    """
    if not target_directory:
        target_directory = "./" + project_name

    os.makedirs(target_directory, exist_ok=True)

    analysis = analyze_project(project_name, description, focus_areas)

    # Apply forced_chain override if provided (recalculates skills)
    if forced_chain:
        analyzer = ProjectAnalyzer()
        analysis = analyzer.override_chain(analysis, forced_chain)

    context = prepare_template_context(analysis)

    # Add platform and gitops context for templates
    if platform:
        context["platform"] = platform
        context["platform_display"] = {
            "rke2": "RKE2 + ECK",
            "openshift": "OpenShift 4.x + ECK",
            "aks": "AKS + ECK",
            "proxmox": "Proxmox VE + RKE2/ECK",
        }.get(platform, platform)
    else:
        context["platform"] = ""
        context["platform_display"] = ""

    if gitops_tool:
        context["gitops_tool"] = gitops_tool
        context["gitops_display"] = {
            "flux": "FluxCD",
            "argo": "ArgoCD",
            "none": "None (raw manifests)",
        }.get(gitops_tool, gitops_tool)
    else:
        context["gitops_tool"] = ""
        context["gitops_display"] = ""

    if iac_tool:
        context["iac_tool"] = iac_tool
        context["iac_tool_display"] = {
            "terraform": "Terraform",
            "none": "None",
        }.get(iac_tool, iac_tool)
    else:
        context["iac_tool"] = ""
        context["iac_tool_display"] = ""

    # Add sizing context if available
    if sizing_context:
        context["sizing_configured"] = "true"
        for key, value in sizing_context.items():
            context[f"sizing_{key}"] = (
                str(value) if not isinstance(value, dict) else str(value)
            )
    else:
        context["sizing_configured"] = "false"

    license_policy = dict(default_license_policy() | (license_policy or {}))
    header_policy = dict(default_header_policy() | (header_policy or {}))

    # Create directories/files
    structure = analysis.get("project_structure", [])
    if (gitops_tool or "").lower() == "argo":
        # Remove Flux-shaped default scaffold when ArgoCD is explicitly selected.
        flux_scaffold = {"flux-system/", "clusters/", "apps/", "base/", "overlays/"}
        structure = [item for item in structure if item not in flux_scaffold]
    created = create_project_structure(target_directory, structure)

    # Template paths
    tmpl_base = Path(__file__).resolve().parent.parent / "templates"
    custom = custom_templates or {}

    readme = generate_readme(
        target_directory,
        context,
        custom.get("README.md", str(tmpl_base / "README_template.md")),
        sizing_context=sizing_context,
    )
    agents = generate_agents_doc(
        target_directory,
        context,
        custom.get("AGENTS.md", str(tmpl_base / "AGENTS_template.md")),
    )
    config_files = generate_basic_files(target_directory, context)

    # Generate .opencode/context.md for session bootstrap
    opencode_context = generate_opencode_context(target_directory, context)

    # Addon autodiscovery and loading
    generated_files = [readme, agents, opencode_context] + config_files
    file_records = [
        build_file_record(project_root=target_directory, full_path=readme, source_type="core", source_name="readme"),
        build_file_record(project_root=target_directory, full_path=agents, source_type="core", source_name="agents_doc"),
        build_file_record(project_root=target_directory, full_path=opencode_context, source_type="core", source_name="opencode_context"),
    ]
    for path in config_files:
        file_records.append(
            build_file_record(project_root=target_directory, full_path=path, source_type="core", source_name="basic_files")
        )

    # Build context for addon matching
    addon_context = {
        "gitops_tool": gitops_tool or "",
        "iac_tool": iac_tool or "",
        "repo_url": repo_url or "",
        "git_token": git_token or "",
        "target_revision": target_revision or "main",
        "platform": platform or "",
        "sizing_context": sizing_context,
        "fallback_storage_class": fallback_storage_class or "",
        "enable_metrics_server": enable_metrics_server,
        "enable_otel_collector": enable_otel_collector,
        "primary_category": analysis.get("primary_category", ""),
        "eck_version": (sizing_context or {}).get("eck_operator", {}).get("version", "3.0.0") if sizing_context else "3.0.0",
    }

    # Determine if running in interactive mode (platform or gitops_tool explicitly set)
    interactive_mode = bool(platform or gitops_tool)
    manifest_path = os.path.join(target_directory, "project-initializer-manifest.json")
    operations_manifest_path = os.path.join(target_directory, "project-initializer-operations.json")
    validation_report_path = os.path.join(target_directory, "project-initializer-validation-report.json")

    try:
        # Use AddonLoader for autodiscovery and matching
        addon_run = run_matched_addons_with_trace(
            analysis=analysis,
            project_name=project_name,
            description=description,
            context=addon_context,
            interactive_mode=interactive_mode,
        )
        addon_files = addon_run.get("files", {})
        addon_sources = addon_run.get("file_sources", {})

        # Write addon-generated files to disk
        for filepath, content in addon_files.items():
            full_path = os.path.join(target_directory, filepath)
            executable = filepath.startswith("scripts/") and filepath.endswith(".sh")
            write_text_file(full_path, content, executable=executable)
            generated_files.append(full_path)
            source_meta = addon_sources.get(filepath, {})
            file_records.append(
                build_file_record(
                    project_root=target_directory,
                    full_path=full_path,
                    source_type=source_meta.get("source_type", "addon"),
                    source_name=source_meta.get("source_name", "unknown_addon"),
                    executable=executable,
                )
            )
            logging.info(f"Generated addon file: {filepath}")

        governance_outputs = governance_docs(
            project_name=project_name,
            project_root=target_directory,
            platform=platform,
            gitops_tool=gitops_tool,
            iac_tool=iac_tool,
            license_policy=license_policy,
            header_policy=header_policy,
            manifest_path=manifest_path,
            file_records=file_records,
        )
        for full_path, content in governance_outputs.items():
            write_text_file(full_path, content)
            generated_files.append(full_path)
            file_records.append(
                build_file_record(
                    project_root=target_directory,
                    full_path=full_path,
                    source_type="governance",
                    source_name=Path(full_path).name.lower(),
                )
            )

        file_records.append(
            build_file_record(
                project_root=target_directory,
                full_path=manifest_path,
                source_type="governance",
                source_name="generation_manifest",
            )
        )
        file_records.append(
            build_file_record(
                project_root=target_directory,
                full_path=operations_manifest_path,
                source_type="governance",
                source_name="operations_manifest",
            )
        )
        file_records.append(
            build_file_record(
                project_root=target_directory,
                full_path=validation_report_path,
                source_type="governance",
                source_name="generation_validation_report",
            )
        )
        apply_header_policy(
            project_root=target_directory,
            file_records=file_records,
            license_policy=license_policy,
            header_policy=header_policy,
            skip_paths=["project-initializer-manifest.json"],
        )
        manifest_payload = build_generation_manifest(
            project_name=project_name,
            description=description,
            project_path=target_directory,
            platform=platform,
            gitops_tool=gitops_tool,
            iac_tool=iac_tool,
            analysis=analysis,
            sizing_context=sizing_context,
            license_policy=license_policy,
            header_policy=header_policy,
            file_records=file_records,
        )
        write_json_file(manifest_path, manifest_payload)
        generated_files.append(manifest_path)
        operations_payload = build_operations_manifest(
            project_name=project_name,
            project_path=target_directory,
            platform=platform,
            gitops_tool=gitops_tool,
            iac_tool=iac_tool,
            file_records=file_records,
        )
        write_json_file(operations_manifest_path, operations_payload)
        generated_files.append(operations_manifest_path)
        validation_payload = build_generation_validation_report(
            project_root=target_directory,
            manifest_path=manifest_path,
            file_records=file_records,
            license_policy=license_policy,
            header_policy=header_policy,
        )
        write_json_file(validation_report_path, validation_payload)
        generated_files.append(validation_report_path)

    except Exception as e:
        logging.warning(f"Addon loading failed: {e}")

    if not os.path.exists(manifest_path):
        governance_outputs = governance_docs(
            project_name=project_name,
            project_root=target_directory,
            platform=platform,
            gitops_tool=gitops_tool,
            iac_tool=iac_tool,
            license_policy=license_policy,
            header_policy=header_policy,
            manifest_path=manifest_path,
            file_records=file_records,
        )
        for full_path, content in governance_outputs.items():
            if not os.path.exists(full_path):
                write_text_file(full_path, content)
                generated_files.append(full_path)
                file_records.append(
                    build_file_record(
                        project_root=target_directory,
                        full_path=full_path,
                        source_type="governance",
                        source_name=Path(full_path).name.lower(),
                    )
                )

        file_records.append(
            build_file_record(
                project_root=target_directory,
                full_path=manifest_path,
                source_type="governance",
                source_name="generation_manifest",
            )
        )
        file_records.append(
            build_file_record(
                project_root=target_directory,
                full_path=operations_manifest_path,
                source_type="governance",
                source_name="operations_manifest",
            )
        )
        file_records.append(
            build_file_record(
                project_root=target_directory,
                full_path=validation_report_path,
                source_type="governance",
                source_name="generation_validation_report",
            )
        )
        apply_header_policy(
            project_root=target_directory,
            file_records=file_records,
            license_policy=license_policy,
            header_policy=header_policy,
            skip_paths=["project-initializer-manifest.json"],
        )
        manifest_payload = build_generation_manifest(
            project_name=project_name,
            description=description,
            project_path=target_directory,
            platform=platform,
            gitops_tool=gitops_tool,
            iac_tool=iac_tool,
            analysis=analysis,
            sizing_context=sizing_context,
            license_policy=license_policy,
            header_policy=header_policy,
            file_records=file_records,
        )
        write_json_file(manifest_path, manifest_payload)
        generated_files.append(manifest_path)
        operations_payload = build_operations_manifest(
            project_name=project_name,
            project_path=target_directory,
            platform=platform,
            gitops_tool=gitops_tool,
            iac_tool=iac_tool,
            file_records=file_records,
        )
        write_json_file(operations_manifest_path, operations_payload)
        generated_files.append(operations_manifest_path)
        validation_payload = build_generation_validation_report(
            project_root=target_directory,
            manifest_path=manifest_path,
            file_records=file_records,
            license_policy=license_policy,
            header_policy=header_policy,
        )
        write_json_file(validation_report_path, validation_payload)
        generated_files.append(validation_report_path)

    return {
        "project_path": target_directory,
        "project_name": project_name,
        "description": description,
        "primary_skill": analysis["primary_skill"],
        "assigned_skills": analysis["assigned_skills"],
        "primary_category": analysis["primary_category"],
        "priority_chain": analysis["priority_chain"],
        "generated_files": generated_files,
        "created_paths": created,
        "analysis_confidence": analysis["analysis_confidence"],
        "unavailable_skills": analysis.get("unavailable_skills", []),
        "platform": platform,
        "gitops_tool": gitops_tool,
        "iac_tool": iac_tool,
        "repo_url": repo_url,
        "target_revision": target_revision,
        "sizing_context": sizing_context,
        "generation_manifest": manifest_path,
        "generation_operations_manifest": operations_manifest_path,
        "generation_validation_report": validation_report_path,
        "license_policy": license_policy,
        "header_policy": header_policy,
    }


if __name__ == "__main__":
    result = initialize_project(
        "test-project",
        "Test project for project initialization",
        "./test-output",
    )
    print(f"Project created at: {result['project_path']}")
    print(f"Primary skill: {result['primary_skill']}")
    print(f"Generated files: {result['generated_files']}")
