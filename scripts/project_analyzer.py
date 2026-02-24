#!/usr/bin/env python3
"""
Canonical ProjectAnalyzer module for the project-initializer skill.
Zero external dependencies -- uses only Python stdlib (json, re, os, pathlib).
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class ProjectAnalyzer:
    """Analyse a project description and assign skills / structure."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = str(
                Path(__file__).resolve().parent.parent
            )
        self.config_path = config_path
        self.priority_chains: Dict[str, List[str]] = {}
        self.skill_mapping: Dict[str, dict] = {}
        self.keyword_mapping: Dict[str, List[str]] = {}
        self.project_templates: Dict[str, dict] = {}
        self.load_config()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def load_config(self):
        """Load configuration from priority_chains.json (stdlib only)."""
        config_file = os.path.join(self.config_path, "priority_chains.json")
        if os.path.exists(config_file):
            with open(config_file, "r") as fh:
                config = json.load(fh)
        else:
            config = self._default_config()

        self.priority_chains = config.get("priority_chains", {})
        self.skill_mapping = config.get("skill_mapping", {})
        self.keyword_mapping = config.get("keyword_mapping", {})
        self.project_templates = config.get("project_templates", {})

    @staticmethod
    def _default_config() -> dict:
        """Fallback when no JSON config is found."""
        return {
            "priority_chains": {
                "default": [
                    "devops-02-2026",
                    "kubernetes-k8s-specialist",
                    "platform-engineering",
                    "devops-general",
                ],
            },
            "keyword_mapping": {
                "elasticsearch": ["elasticsearch", "es", "eck", "elastic", "kibana"],
                "kubernetes": ["kubernetes", "k8s", "openshift", "container", "rke2", "rancher"],
                "terraform": ["terraform", "iac", "infrastructure"],
                "azure": ["azure", "aks", "azurekubernetesservice", "microsoft"],
                "gitops": ["fluxcd", "flux", "gitops", "helmrelease", "gitrepository", "kustomization"],
            },
            "skill_mapping": {},
            "project_templates": {},
        }

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze_project_description(
        self, description: str, project_name: str = ""
    ) -> Dict:
        """Return category scores, selected chain, and assigned skills."""
        full_text = f"{project_name} {description}".lower()

        category_scores: Dict[str, int] = {}
        for category, keywords in self.keyword_mapping.items():
            score = 0
            for kw in keywords:
                pattern = r"\b" + re.escape(kw) + r"\b"
                score += len(re.findall(pattern, full_text))
            category_scores[category] = score

        # Primary category = highest score (first alphabetically on tie)
        if category_scores and max(category_scores.values()) > 0:
            primary_category = max(
                category_scores.items(), key=lambda x: x[1]
            )[0]
        else:
            primary_category = "generic"

        # Detect ambiguous categories (within 1 point of the top score)
        max_score = max(category_scores.values()) if category_scores else 0
        ambiguous_categories = [
            cat for cat, score in category_scores.items()
            if score >= max_score - 1 and score > 0 and cat != primary_category
        ]

        priority_chain = self._select_chain(primary_category, category_scores)

        available_skills = [
            s
            for s in self.priority_chains.get(priority_chain, [])
            if self.skill_mapping.get(s, {}).get("available", False)
        ]

        return {
            "primary_category": primary_category,
            "category_scores": category_scores,
            "ambiguous_categories": ambiguous_categories,
            "priority_chain": priority_chain,
            "assigned_skills": available_skills,
            "primary_skill": available_skills[0] if available_skills else None,
        }

    def _select_chain(
        self, primary_category: str, scores: Dict[str, int]
    ) -> str:
        chain_map = {
            "elasticsearch": "default",
            "kubernetes": "kubernetes_first",
            "terraform": "terraform_first",
            "azure": "azure_focused",
            "gitops": "gitops_focused",
        }
        chain = chain_map.get(primary_category, "default")
        if scores.get(primary_category, 0) == 0:
            chain = "default"
        # Fall back to default if the chain isn't defined in config
        if chain not in self.priority_chains:
            chain = "default"
        return chain

    # ------------------------------------------------------------------
    # Project structure
    # ------------------------------------------------------------------

    def get_project_structure(self, analysis_result: Dict) -> List[str]:
        """Return list of paths (dirs end with /) for the project type."""
        cat = analysis_result["primary_category"]

        base = [
            "README.md",
            "AGENTS.md",
            "terraform/",
            "k8s/",
            "scripts/",
            "docs/",
            ".opencode/context/",
        ]

        extras = {
            "elasticsearch": [
                "observability/", 
                "elasticsearch/", 
                "kibana/",
                "agents/",
            ],
            "kubernetes": ["cluster/", "platform-services/", "applications/"],
            "terraform": ["modules/", "environments/", "networking/"],
            "azure": [
                "terraform/modules/aks/",
                "terraform/modules/networking/",
                "terraform/modules/storage/",
                "terraform/modules/acr/",
                "terraform/modules/monitoring/",
            ],
            "gitops": [
                "clusters/",
                "infrastructure/",
                "apps/",
                "flux-system/",
                "base/",
                "overlays/",
            ],
        }

        base.extend(extras.get(cat, []))
        return base

    # ------------------------------------------------------------------
    # Skill validation
    # ------------------------------------------------------------------

    def override_chain(self, result: Dict, forced_chain: str) -> Dict:
        """Override the priority chain and recalculate skills."""
        if not forced_chain or forced_chain not in self.priority_chains:
            return result
        skills = [
            s for s in self.priority_chains[forced_chain]
            if self.skill_mapping.get(s, {}).get("available", False)
        ]
        available, unavailable = self.validate_skills(skills)
        result["priority_chain"] = forced_chain
        result["assigned_skills"] = available
        result["primary_skill"] = available[0] if available else None
        result["unavailable_skills"] = unavailable
        return result

    def validate_skills(self, skills: List[str]) -> Tuple[List[str], List[str]]:
        """Check which skills actually exist on disk."""
        available: List[str] = []
        unavailable: List[str] = []

        for skill in skills:
            skill_path = Path(f"~/.config/opencode/skills/{skill}").expanduser()
            if skill_path.exists():
                available.append(skill)
            else:
                unavailable.append(skill)

        return available, unavailable


# ------------------------------------------------------------------
# High-level helper used by analyze_project.py and init_project.py
# ------------------------------------------------------------------

def analyze_project(
    project_name: str,
    description: str,
    focus_areas: Optional[List[str]] = None,
    config_path: Optional[str] = None,
) -> Dict:
    """Analyse a project and return a complete result dict."""
    analyzer = ProjectAnalyzer(config_path)

    result = analyzer.analyze_project_description(description, project_name)

    if focus_areas:
        focus_text = " ".join(focus_areas)
        focus_result = analyzer.analyze_project_description(focus_text, "")
        if max(focus_result["category_scores"].values(), default=0) > 0:
            result.update(focus_result)

    available, unavailable = analyzer.validate_skills(result["assigned_skills"])
    structure = analyzer.get_project_structure(result)

    primary = result["primary_skill"]
    if primary and primary not in available:
        primary = available[0] if available else None

    return {
        "project_name": project_name,
        "description": description,
        "primary_category": result["primary_category"],
        "category_scores": result["category_scores"],
        "ambiguous_categories": result.get("ambiguous_categories", []),
        "priority_chain": result["priority_chain"],
        "assigned_skills": available,
        "primary_skill": primary,
        "unavailable_skills": unavailable,
        "project_structure": structure,
        "analysis_confidence": max(result["category_scores"].values(), default=0),
    }
