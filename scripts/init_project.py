#!/usr/bin/env python3
"""
CLI entry point for the project-initializer skill.

Usage:
    python3 init_project.py --name NAME --desc DESC [--type TYPE] [--target DIR] \
                            [--analyze-only] [--chain CHAIN] [--json] [--git-init] \
                            [--sizing-file FILE]

Zero external dependencies -- Python 3.9+ stdlib only.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

# Ensure sibling module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from project_analyzer import ProjectAnalyzer, analyze_project  # noqa: E402
from generate_structure import initialize_project  # noqa: E402
from sizing_parser import parse_sizing_file  # noqa: E402

# Skill directory for addons
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


VALID_TYPES = ["elasticsearch", "kubernetes", "terraform", "azure", "gitops"]

TYPE_DESCRIPTIONS = {
    "elasticsearch": "Elasticsearch / ECK / Observability stack",
    "kubernetes": "Kubernetes / OpenShift platform",
    "terraform": "Terraform / IaC infrastructure",
    "azure": "Azure / AKS cloud platform",
    "gitops": "FluxCD / ArgoCD GitOps platform",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="init_project",
        description="Initialise a new DevOps project with automatic skill assignment.",
    )
    parser.add_argument(
        "--name", required=False, help="Project name (kebab-case recommended)"
    )
    parser.add_argument(
        "--desc", required=False, help="Short project description"
    )
    parser.add_argument(
        "--type",
        choices=VALID_TYPES,
        default=None,
        help="Force project type (auto-detected if omitted)",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Target directory (default: ./<name>)",
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Print skill assignments without creating files",
    )
    parser.add_argument(
        "--chain",
        default=None,
        help="Force a specific priority chain name",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Machine-readable JSON output",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode with guided prompts",
    )
    parser.add_argument(
        "--git-init",
        action="store_true",
        help="Initialize a git repository in the project directory",
    )
    parser.add_argument(
        "--sizing-file",
        default=None,
        help="Path to ES sizing report markdown file (from elasticsearch-openshift-sizing-assistant)",
    )
    return parser


def run_analyze_only(name: str, desc: str, forced_type: str | None, forced_chain: str | None, as_json: bool):
    """Analyse and print results without creating any files."""
    # If a type is forced, prepend its keywords so detection picks it up
    effective_desc = desc
    if forced_type:
        effective_desc = f"{forced_type} {desc}"

    result = analyze_project(name, effective_desc)

    # Override chain if forced
    if forced_chain:
        analyzer = ProjectAnalyzer()
        if forced_chain in analyzer.priority_chains:
            result["priority_chain"] = forced_chain
            skills = [
                s for s in analyzer.priority_chains[forced_chain]
                if analyzer.skill_mapping.get(s, {}).get("available", False)
            ]
            avail, unavail = analyzer.validate_skills(skills)
            result["assigned_skills"] = avail
            result["unavailable_skills"] = unavail
            result["primary_skill"] = avail[0] if avail else None

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Project        : {result['project_name']}")
        print(f"Description    : {result['description']}")
        print(f"Category       : {result['primary_category']}")
        print(f"Priority Chain : {result['priority_chain']}")
        print(f"Primary Skill  : {result['primary_skill']}")
        print(f"Assigned Skills: {', '.join(result['assigned_skills']) or '(none)'}")
        if result.get("unavailable_skills"):
            print(f"Unavailable    : {', '.join(result['unavailable_skills'])}")
        print(f"Confidence     : {result['analysis_confidence']}")
        print(f"Structure      : {', '.join(result['project_structure'])}")


def run_init(name: str, desc: str, target: str | None, forced_type: str | None, forced_chain: str | None, as_json: bool, git_init: bool = False, sizing_file: str | None = None):
    """Full project initialisation."""
    effective_desc = desc
    if forced_type:
        effective_desc = f"{forced_type} {desc}"

    target_dir = target or os.path.join(".", name)

    # Parse sizing file if provided
    sizing_context = None
    detected_platform = None
    if sizing_file:
        try:
            sizing_context = parse_sizing_file(sizing_file)
            
            # Auto-detect platform from sizing file
            detected_platform = sizing_context.get("platform_detected")
            
            if not as_json:
                print(f"Parsed sizing from : {sizing_file}")
                print(f"  Health score     : {sizing_context.get('health_score', 'N/A')}/100")
                if detected_platform:
                    print(f"  Platform detected: {detected_platform.upper()}")
                if sizing_context.get('data_nodes'):
                    dn = sizing_context['data_nodes']
                    print(f"  Hot tier         : {dn.get('count', 0)} nodes, {dn.get('memory', 'N/A')} RAM, {dn.get('storage', 'N/A')} disk")
                if sizing_context.get('cold_nodes'):
                    cn = sizing_context['cold_nodes']
                    print(f"  Cold tier        : {cn.get('count', 0)} nodes, {cn.get('memory', 'N/A')} RAM, {cn.get('storage', 'N/A')} disk")
                if sizing_context.get('frozen_nodes'):
                    fn = sizing_context['frozen_nodes']
                    print(f"  Frozen tier      : {fn.get('count', 0)} nodes, {fn.get('memory', 'N/A')} RAM")
                if sizing_context.get('aks'):
                    aks = sizing_context['aks']
                    print(f"  AKS node pools   : {len(aks.get('node_pools', []))} pools")
                if sizing_context.get('openshift'):
                    openshift = sizing_context['openshift']
                    print(f"  OpenShift pools  : {len(openshift.get('worker_pools', []))} pools")
        except Exception as e:
            if not as_json:
                print(f"Warning: Failed to parse sizing file: {e}")
            sizing_context = None

    # Use detected platform from sizing file if not manually set
    result = initialize_project(
        name, 
        effective_desc, 
        target_dir, 
        sizing_context=sizing_context,
        platform=detected_platform,  # Pass auto-detected platform
    )
    
    # Initialize git if requested
    if git_init:
        git_result = init_git_repo(target_dir, name)
        result["git_initialized"] = git_result["success"]
        if git_result.get("error"):
            result["git_error"] = git_result["error"]

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Project created at : {result['project_path']}")
        print(f"Category           : {result['primary_category']}")
        print(f"Primary Skill      : {result['primary_skill']}")
        print(f"Assigned Skills    : {', '.join(result['assigned_skills']) or '(none)'}")
        print(f"Generated files    :")
        for f in result["generated_files"]:
            print(f"  - {f}")
        if result.get("unavailable_skills"):
            print(f"Unavailable skills : {', '.join(result['unavailable_skills'])}")
        if git_init:
            if result.get("git_initialized"):
                print(f"Git repository     : Initialized")
            else:
                print(f"Git repository     : Failed ({result.get('git_error', 'unknown error')})")


def init_git_repo(target_dir: str, project_name: str) -> dict:
    """Initialize a git repository in the target directory."""
    try:
        # Check if git is available
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"success": False, "error": "git not found"}
    
    try:
        # Initialize repository
        subprocess.run(
            ["git", "init"],
            cwd=target_dir,
            capture_output=True,
            check=True,
        )
        
        # Create initial commit
        subprocess.run(
            ["git", "add", "."],
            cwd=target_dir,
            capture_output=True,
            check=True,
        )
        
        subprocess.run(
            ["git", "commit", "-m", f"Initial commit: {project_name} project scaffold"],
            cwd=target_dir,
            capture_output=True,
            check=True,
        )
        
        return {"success": True}
        
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": str(e)}


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Interactive mode takes precedence
    if args.interactive:
        from interactive import run_interactive
        sys.exit(run_interactive())

    # Non-interactive mode requires --name and --desc
    if not args.name or not args.desc:
        parser.error("--name and --desc are required (or use --interactive / -i)")

    if args.analyze_only:
        run_analyze_only(args.name, args.desc, args.type, args.chain, args.json_output)
    else:
        run_init(args.name, args.desc, args.target, args.type, args.chain, args.json_output, args.git_init, args.sizing_file)


if __name__ == "__main__":
    main()
