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
from addon_loader import AddonLoader, run_matched_addons  # noqa: E402

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
        "priority_chain": analysis_result.get("priority_chain", "default"),
        "analysis_confidence": str(analysis_result.get("analysis_confidence", 0)),
        "project_structure_tree": tree_text,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "author": "Project Initializer",
    }


# ------------------------------------------------------------------
# File-system helpers
# ------------------------------------------------------------------


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


def generate_readme(base_path: str, context: Dict, template_path: str) -> str:
    """Render and write README.md."""
    try:
        with open(template_path, "r") as fh:
            template = fh.read()
    except FileNotFoundError:
        template = "# {{project_name}}\n\n{{project_description}}\n"

    content = render_template(template, context)
    out = os.path.join(base_path, "README.md")
    with open(out, "w") as fh:
        fh.write(content)
    return out


def generate_agents_doc(base_path: str, context: Dict, template_path: str) -> str:
    """Render and write AGENTS.md."""
    try:
        with open(template_path, "r") as fh:
            template = fh.read()
    except FileNotFoundError:
        template = "# Agent Coordination Guide\n\nPrimary: {{primary_skill}}\n"

    content = render_template(template, context)
    out = os.path.join(base_path, "AGENTS.md")
    with open(out, "w") as fh:
        fh.write(content)
    return out


def generate_basic_files(base_path: str, context: Dict) -> List[str]:
    """Generate .gitignore, starter Terraform, and K8s files."""
    generated = []

    # .gitignore
    gitignore = os.path.join(base_path, ".gitignore")
    with open(gitignore, "w") as fh:
        fh.write(
            ".opencode/\n.venv/\n__pycache__/\n*.pyc\nenv/\nvenv/\n"
            ".vscode/\n.idea/\n*.swp\n.DS_Store\nThumbs.db\n"
        )
    generated.append(gitignore)

    # Terraform starters
    tf_dir = os.path.join(base_path, "terraform")
    if os.path.isdir(tf_dir):
        main_tf = os.path.join(tf_dir, "main.tf")
        with open(main_tf, "w") as fh:
            fh.write(
                render_template(
                    "# Terraform configuration for {{project_name}}\n\n"
                    'terraform {\n  required_version = ">= 1.0"\n}\n',
                    context,
                )
            )
        generated.append(main_tf)

        vars_tf = os.path.join(tf_dir, "variables.tf")
        with open(vars_tf, "w") as fh:
            fh.write(
                render_template(
                    '# Input variables\n\nvariable "project_name" {\n'
                    '  description = "Project name"\n  type        = string\n'
                    '  default     = "{{project_name}}"\n}\n\n'
                    'variable "environment" {\n  description = "Environment"\n'
                    '  type        = string\n  default     = "dev"\n}\n',
                    context,
                )
            )
        generated.append(vars_tf)

    # K8s namespace
    k8s_dir = os.path.join(base_path, "k8s")
    if os.path.isdir(k8s_dir):
        ns = os.path.join(k8s_dir, "namespace.yaml")
        with open(ns, "w") as fh:
            fh.write(
                render_template(
                    "apiVersion: v1\nkind: Namespace\nmetadata:\n"
                    "  name: {{project_name}}\n  labels:\n"
                    "    project: {{project_name}}\n",
                    context,
                )
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

    content = f"""# OpenCode Session Context

## Project: {context.get("project_name", "Unknown")}

{context.get("project_description", "")}

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
    with open(out, "w") as fh:
        fh.write(content)
    return out


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
    sizing_context: Optional[Dict] = None,
    forced_chain: Optional[str] = None,
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
        forced_chain: Override the priority chain selection
    """
    if not target_directory:
        target_directory = "./" + project_name

    os.makedirs(target_directory, exist_ok=True)

    analysis = analyze_project(project_name, description, focus_areas)

    # Apply forced_chain override if provided
    if forced_chain:
        analysis["priority_chain"] = forced_chain

    context = prepare_template_context(analysis)

    # Add platform and gitops context for templates
    if platform:
        context["platform"] = platform
        context["platform_display"] = {
            "rke2": "RKE2 + ECK",
            "openshift": "OpenShift 4.x + ECK",
            "aks": "AKS + ECK",
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

    # Add sizing context if available
    if sizing_context:
        context["sizing_configured"] = "true"
        for key, value in sizing_context.items():
            context[f"sizing_{key}"] = (
                str(value) if not isinstance(value, dict) else str(value)
            )
    else:
        context["sizing_configured"] = "false"

    # Create directories/files
    structure = analysis.get("project_structure", [])
    created = create_project_structure(target_directory, structure)

    # Template paths
    tmpl_base = Path(__file__).resolve().parent.parent / "templates"
    custom = custom_templates or {}

    readme = generate_readme(
        target_directory,
        context,
        custom.get("README.md", str(tmpl_base / "README_template.md")),
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

    # Build context for addon matching
    addon_context = {
        "gitops_tool": gitops_tool or "",
        "platform": platform or "",
        "sizing_context": sizing_context,
    }

    # Determine if running in interactive mode (platform or gitops_tool explicitly set)
    interactive_mode = bool(platform or gitops_tool)

    try:
        # Use AddonLoader for autodiscovery and matching
        addon_files = run_matched_addons(
            analysis=analysis,
            project_name=project_name,
            description=description,
            context=addon_context,
            interactive_mode=interactive_mode,
        )

        # Write addon-generated files to disk
        for filepath, content in addon_files.items():
            full_path = os.path.join(target_directory, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            generated_files.append(full_path)
            logging.info(f"Generated addon file: {filepath}")

    except Exception as e:
        logging.warning(f"Addon loading failed: {e}")

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
        "sizing_context": sizing_context,
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
