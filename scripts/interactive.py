#!/usr/bin/env python3
"""
Interactive mode for the project-initializer skill.
Provides guided prompts for project creation with platform and GitOps selection.

Zero external dependencies -- Python 3.9+ stdlib only.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Ensure sibling module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from project_analyzer import ProjectAnalyzer, analyze_project  # noqa: E402
from generate_structure import initialize_project  # noqa: E402


# ------------------------------------------------------------------
# Platform and GitOps Options
# ------------------------------------------------------------------

PLATFORMS: List[Tuple[str, str, str]] = [
    ("rke2", "RKE2 + ECK", "Rancher Kubernetes Engine 2"),
    ("openshift", "OpenShift 4.x + ECK", "Red Hat OpenShift Container Platform"),
    ("aks", "AKS + ECK", "Azure Kubernetes Service"),
]

GITOPS_TOOLS: List[Tuple[str, str, str]] = [
    ("flux", "FluxCD", "Recommended - GitOps with Flux controllers"),
    ("argo", "ArgoCD", "Alternative GitOps with Argo Application CRDs"),
    ("none", "None", "Raw Kubernetes manifests only"),
]

# Sizing skill to invoke
SIZING_SKILL = "elasticsearch-openshift-sizing-assistant-legacy"
SIZING_SKILL_PATH = Path("~/.config/opencode/skills").expanduser() / SIZING_SKILL


# ------------------------------------------------------------------
# Prompt Helpers
# ------------------------------------------------------------------

def prompt_text(question: str, default: str = "") -> str:
    """Prompt for text input with optional default."""
    if default:
        prompt = f"{question} [{default}]: "
    else:
        prompt = f"{question}: "
    
    try:
        response = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)
    
    return response if response else default


def prompt_choice(question: str, options: List[Tuple[str, str, str]]) -> str:
    """Prompt for numbered selection from options. Returns the key (first element)."""
    print(f"\n{question}")
    for i, (key, label, description) in enumerate(options, 1):
        print(f"  {i}. {label} - {description}")
    
    while True:
        try:
            response = input(f"Select [1-{len(options)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)
        
        if not response:
            return options[0][0]  # Default to first option
        
        try:
            idx = int(response)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
            print(f"Please enter a number between 1 and {len(options)}")
        except ValueError:
            # Try matching by key
            for key, _, _ in options:
                if response.lower() == key.lower():
                    return key
            print(f"Invalid selection. Enter 1-{len(options)} or a valid key.")


def prompt_confirm(question: str, default: bool = True) -> bool:
    """Prompt for Y/n confirmation."""
    suffix = "[Y/n]" if default else "[y/N]"
    
    try:
        response = input(f"{question} {suffix}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)
    
    if not response:
        return default
    
    return response in ("y", "yes", "1", "true")


# ------------------------------------------------------------------
# Sizing Skill Integration
# ------------------------------------------------------------------

def check_sizing_skill_available() -> bool:
    """Check if the sizing skill exists on disk."""
    return SIZING_SKILL_PATH.exists()


def invoke_sizing_skill(project_name: str, platform: str) -> Optional[Dict]:
    """
    Invoke the ES sizing skill interactively.
    Returns sizing context dict or None if skipped/failed.
    """
    if not check_sizing_skill_available():
        print(f"\n  Sizing skill not found: {SIZING_SKILL}")
        print(f"  Expected at: {SIZING_SKILL_PATH}")
        return None
    
    print(f"\n  Loading skill: {SIZING_SKILL}")
    print("  (Sizing wizard would run here - placeholder for integration)")
    
    # TODO: In Phase 3, this will invoke the actual sizing skill
    # For now, return a placeholder context
    sizing_context = {
        "sizing_invoked": True,
        "sizing_skill": SIZING_SKILL,
        "platform": platform,
        "placeholder": True,
        # These would be populated by the actual sizing skill:
        # "data_nodes": {"count": 3, "memory": "16Gi", "storage": "500Gi"},
        # "master_nodes": {"count": 3, "memory": "4Gi"},
        # "ingest_rate_gb_day": 500,
        # "retention_days": 30,
    }
    
    print("  Sizing context captured (placeholder)")
    return sizing_context


# ------------------------------------------------------------------
# Main Interactive Flow
# ------------------------------------------------------------------

def print_banner():
    """Print welcome banner."""
    print("\n" + "=" * 60)
    print("  Project Initializer - Interactive Mode")
    print("  Elasticsearch Cluster Scaffolding for Multiple Platforms")
    print("=" * 60)


def print_analysis_summary(analysis: Dict):
    """Print detected analysis summary."""
    print(f"\n  Detected type     : {analysis['primary_category']}")
    print(f"  Confidence score  : {analysis['analysis_confidence']}")
    print(f"  Priority chain    : {analysis['priority_chain']}")
    print(f"  Primary skill     : {analysis['primary_skill'] or '(none)'}")
    if analysis.get('assigned_skills'):
        print(f"  Assigned skills   : {', '.join(analysis['assigned_skills'])}")


def print_result_summary(result: Dict):
    """Print final creation summary."""
    print("\n" + "=" * 60)
    print("  Project Created Successfully!")
    print("=" * 60)
    print(f"\n  Location        : {result['project_path']}")
    print(f"  Category        : {result['primary_category']}")
    print(f"  Primary Skill   : {result['primary_skill'] or '(none)'}")
    print(f"  Assigned Skills : {', '.join(result['assigned_skills']) or '(none)'}")
    
    if result.get('platform'):
        print(f"  Platform        : {result['platform']}")
    if result.get('gitops_tool'):
        print(f"  GitOps Tool     : {result['gitops_tool']}")
    
    print("\n  Generated files:")
    for f in result.get("generated_files", [])[:10]:
        rel = os.path.relpath(f, result['project_path'])
        print(f"    - {rel}")
    
    if len(result.get("generated_files", [])) > 10:
        remaining = len(result["generated_files"]) - 10
        print(f"    ... and {remaining} more files")
    
    print("\n  Next steps:")
    print(f"    cd {result['project_path']}")
    print("    # Review AGENTS.md for skill coordination")
    print("    # Review README.md for project overview")


def run_interactive() -> int:
    """
    Main interactive mode entry point.
    Returns exit code (0 for success, non-zero for error).
    """
    print_banner()
    
    # Step 1: Project name
    project_name = prompt_text("\nProject name", "my-elastic-cluster")
    if not project_name:
        print("Error: Project name is required.")
        return 1
    
    # Sanitize project name (kebab-case)
    project_name = project_name.lower().replace(" ", "-").replace("_", "-")
    
    # Step 2: Description
    description = prompt_text(
        "Project description",
        "Elasticsearch cluster deployment with ECK"
    )
    
    # Step 3: Analyze and confirm detection
    analysis = analyze_project(project_name, description)
    print("\n--- Analysis Result ---")
    print_analysis_summary(analysis)
    
    if not prompt_confirm("\nAccept detected configuration?", default=True):
        # Allow manual override
        print("\nAvailable types: elasticsearch, kubernetes, terraform, azure, gitops")
        forced_type = prompt_text("Force project type (or press Enter to keep)", "")
        if forced_type:
            # Re-analyze with forced type
            description = f"{forced_type} {description}"
            analysis = analyze_project(project_name, description)
            print_analysis_summary(analysis)
    
    # Step 4: Platform selection
    platform = prompt_choice("Target platform:", PLATFORMS)
    
    # Step 5: GitOps tool selection
    gitops_tool = prompt_choice("GitOps tool:", GITOPS_TOOLS)
    
    # Step 6: Sizing wizard (optional)
    sizing_context = None
    if analysis['primary_category'] == 'elasticsearch' or 'elastic' in description.lower():
        if check_sizing_skill_available():
            if prompt_confirm("\nRun ES sizing wizard?", default=True):
                sizing_context = invoke_sizing_skill(project_name, platform)
        else:
            print(f"\n  Note: Sizing skill not available ({SIZING_SKILL})")
            print("  Skipping sizing wizard.")
    
    # Step 7: Target directory
    default_target = f"./{project_name}"
    target_dir = prompt_text(f"\nTarget directory", default_target)
    
    # Step 8: Confirm and create
    print("\n--- Summary ---")
    print(f"  Project name  : {project_name}")
    print(f"  Description   : {description}")
    print(f"  Platform      : {platform}")
    print(f"  GitOps tool   : {gitops_tool}")
    print(f"  Target        : {target_dir}")
    if sizing_context:
        print("  Sizing        : Configured")
    
    if not prompt_confirm("\nProceed with project creation?", default=True):
        print("Aborted.")
        return 0
    
    # Step 9: Create project
    print("\nCreating project...")
    
    try:
        result = initialize_project(
            project_name=project_name,
            description=description,
            target_directory=target_dir,
            platform=platform,
            gitops_tool=gitops_tool,
            sizing_context=sizing_context,
        )
        
        # Add extra context to result for display
        result['platform'] = platform
        result['gitops_tool'] = gitops_tool
        
        print_result_summary(result)
        return 0
        
    except Exception as e:
        print(f"\nError creating project: {e}")
        return 1


# ------------------------------------------------------------------
# Entry point for direct execution
# ------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(run_interactive())
