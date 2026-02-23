#!/usr/bin/env python3
"""
Thin wrapper around the canonical ProjectAnalyzer.
Kept for backward-compatibility -- all logic lives in project_analyzer.py.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

# Ensure sibling module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from project_analyzer import ProjectAnalyzer, analyze_project  # noqa: E402


def analyze_project_wrapper(
    project_name: str,
    description: str,
    focus_areas: Optional[List[str]] = None,
) -> Dict:
    """Convenience alias -- delegates to project_analyzer.analyze_project."""
    return analyze_project(project_name, description, focus_areas)


if __name__ == "__main__":
    result = analyze_project(
        "elastic-observability-platform",
        "Elasticsearch cluster on OpenShift with Terraform and monitoring",
        ["elasticsearch", "kubernetes", "terraform"],
    )

    print("Analysis Result:")
    print(f"  Primary Category : {result['primary_category']}")
    print(f"  Priority Chain   : {result['priority_chain']}")
    print(f"  Assigned Skills  : {result['assigned_skills']}")
    print(f"  Primary Skill    : {result['primary_skill']}")
    print(f"  Project Structure: {result['project_structure']}")
