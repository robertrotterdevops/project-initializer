#!/usr/bin/env python3
"""
Addon autodiscovery and loading system for project-initializer.
Scans the addons/ directory, matches triggers against analysis results,
and loads addons in priority order.

Zero external dependencies -- Python 3.9+ stdlib only.
"""

import importlib.util
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AddonSpec:
    """Specification for an addon."""

    def __init__(
        self,
        name: str,
        path: Path,
        triggers: Dict[str, Any],
        priority: int = 10,
        description: str = "",
        interactive_only: bool = False,
    ):
        self.name = name
        self.path = path
        self.triggers = triggers
        self.priority = priority
        self.description = description
        self.interactive_only = interactive_only

    def __repr__(self) -> str:
        return f"AddonSpec(name={self.name}, priority={self.priority})"


class AddonLoader:
    """
    Discovers, matches, and loads addons based on project analysis.

    Usage:
        loader = AddonLoader()
        matched = loader.match_addons(analysis_result, context)
        files = loader.run_addons(matched, project_name, description, context)
    """

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            self.base_path = Path(__file__).resolve().parent.parent
        else:
            self.base_path = Path(config_path)

        self.addons_dir = self.base_path / "addons"
        self.config_file = self.base_path / "priority_chains.json"
        self.addon_specs: Dict[str, AddonSpec] = {}
        self._load_addon_config()

    def _load_addon_config(self):
        """Load addon configuration from priority_chains.json."""
        if not self.config_file.exists():
            logger.warning(f"Config file not found: {self.config_file}")
            return

        try:
            with open(self.config_file, "r") as fh:
                config = json.load(fh)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse config: {e}")
            return

        addons_config = config.get("addons", {})

        for name, spec in addons_config.items():
            addon_path = self.base_path / spec.get("path", f"addons/{name}.py")
            triggers = spec.get("triggers", {})
            priority = spec.get("priority", 10)
            description = spec.get("description", "")
            interactive_only = triggers.get("interactive_only", False)

            self.addon_specs[name] = AddonSpec(
                name=name,
                path=addon_path,
                triggers=triggers,
                priority=priority,
                description=description,
                interactive_only=interactive_only,
            )

    def discover_addons(self) -> List[AddonSpec]:
        """
        Discover all available addons in the addons/ directory.
        Returns list of AddonSpec objects sorted by priority.
        """
        discovered = []

        if not self.addons_dir.exists():
            logger.warning(f"Addons directory not found: {self.addons_dir}")
            return discovered

        for addon_file in self.addons_dir.glob("*.py"):
            if addon_file.name.startswith("_"):
                continue

            addon_name = addon_file.stem

            # Use config if available, otherwise create basic spec
            if addon_name in self.addon_specs:
                spec = self.addon_specs[addon_name]
                # Verify file exists
                if spec.path.exists():
                    discovered.append(spec)
            else:
                # Auto-discover addon not in config
                discovered.append(
                    AddonSpec(
                        name=addon_name,
                        path=addon_file,
                        triggers={},
                        priority=50,  # Lower priority for auto-discovered
                        description=f"Auto-discovered addon: {addon_name}",
                    )
                )

        # Sort by priority (lower = higher priority)
        return sorted(discovered, key=lambda x: x.priority)

    def match_addons(
        self,
        analysis: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        interactive_mode: bool = False,
    ) -> List[AddonSpec]:
        """
        Match addons based on analysis result and context.

        Args:
            analysis: Project analysis result dict
            context: Additional context (platform, gitops_tool, etc.)
            interactive_mode: Whether running in interactive mode

        Returns:
            List of matched AddonSpec objects, sorted by priority
        """
        context = context or {}
        matched = []

        primary_category = analysis.get("primary_category", "")
        gitops_tool = context.get("gitops_tool", "")
        platform = context.get("platform", "")
        sizing_context = context.get("sizing_context") or {}

        for spec in self.discover_addons():
            # If sizing report context exists, always include ECK addon.
            # This ensures ES/ECK scaffolding is generated even when the
            # free-text description does not classify as "elasticsearch".
            if (
                spec.name == "eck_deployment"
                and sizing_context.get("source") == "sizing_report"
            ):
                matched.append(spec)
                continue

            # Skip interactive-only addons if not in interactive mode
            if spec.interactive_only and not interactive_mode:
                continue

            triggers = spec.triggers
            trigger_gitops = triggers.get("gitops_tool", "")

            # Check for default trigger (always load)
            if triggers.get("default", False):
                matched.append(spec)
                continue

            # If gitops_tool is explicitly set in context, filter GitOps addons
            # Only load addons that match the selected gitops_tool (or have no gitops_tool trigger)
            if gitops_tool:
                if trigger_gitops and trigger_gitops != gitops_tool:
                    # This addon is for a different gitops tool, skip it
                    continue
                if trigger_gitops == gitops_tool:
                    # Exact gitops_tool match
                    matched.append(spec)
                    continue

            # Check platform trigger
            trigger_platforms = triggers.get("platforms", [])
            if trigger_platforms and platform in trigger_platforms:
                matched.append(spec)
                continue

            # Check category triggers (skip if addon has gitops_tool trigger and we have gitops set)
            trigger_categories = triggers.get("categories", [])
            if trigger_categories:
                # If this addon has a gitops_tool trigger and gitops is set, skip category match
                # (we already handled gitops_tool matching above)
                if trigger_gitops and gitops_tool:
                    continue
                if primary_category in trigger_categories:
                    matched.append(spec)
                    continue

            # Check keyword triggers
            trigger_keywords = triggers.get("keywords", [])
            if trigger_keywords:
                description = analysis.get("description", "").lower()
                project_name = analysis.get("project_name", "").lower()
                full_text = f"{project_name} {description}"

                for keyword in trigger_keywords:
                    if keyword.lower() in full_text:
                        matched.append(spec)
                        break

        # Remove duplicates while preserving order
        seen = set()
        unique_matched = []
        for spec in matched:
            if spec.name not in seen:
                seen.add(spec.name)
                unique_matched.append(spec)

        # Sort by priority
        return sorted(unique_matched, key=lambda x: x.priority)

    def load_addon(self, spec: AddonSpec) -> Optional[Any]:
        """
        Dynamically load an addon module.

        Args:
            spec: AddonSpec for the addon to load

        Returns:
            Loaded module or None if loading failed
        """
        if not spec.path.exists():
            logger.warning(f"Addon file not found: {spec.path}")
            return None

        try:
            module_spec = importlib.util.spec_from_file_location(
                spec.name, str(spec.path)
            )
            if module_spec is None or module_spec.loader is None:
                logger.error(f"Failed to create module spec for {spec.name}")
                return None

            module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
            return module

        except Exception as e:
            logger.error(f"Failed to load addon {spec.name}: {e}")
            return None

    def run_addon(
        self,
        spec: AddonSpec,
        project_name: str,
        description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """
        Run a single addon and return generated files.

        Args:
            spec: AddonSpec for the addon
            project_name: Project name
            description: Project description
            context: Additional context dict

        Returns:
            Dict of {filepath: content} for generated files
        """
        module = self.load_addon(spec)
        if module is None:
            return {}

        context = context or {}

        try:
            # Try the standard main() interface first
            if hasattr(module, "main"):
                return module.main(project_name, description, context)

            # Try generator class interface
            if hasattr(module, "ADDON_META") and hasattr(module, "AddonGenerator"):
                generator = module.AddonGenerator(project_name, description, context)
                return generator.generate()

            # Fallback: try main with just name and description
            if hasattr(module, "main"):
                return module.main(project_name, description)

            logger.warning(f"Addon {spec.name} has no recognized interface")
            return {}

        except Exception as e:
            logger.error(f"Error running addon {spec.name}: {e}")
            return {}

    def run_addons(
        self,
        specs: List[AddonSpec],
        project_name: str,
        description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """
        Run multiple addons and merge their generated files.

        Args:
            specs: List of AddonSpec objects to run
            project_name: Project name
            description: Project description
            context: Additional context dict

        Returns:
            Merged dict of {filepath: content} for all generated files
        """
        all_files: Dict[str, str] = {}

        for spec in specs:
            logger.info(f"Running addon: {spec.name}")
            files = self.run_addon(spec, project_name, description, context)

            # Merge files, later addons can override earlier ones
            for filepath, content in files.items():
                if filepath in all_files:
                    logger.debug(f"Addon {spec.name} overriding {filepath}")
                all_files[filepath] = content

        return all_files


# ------------------------------------------------------------------
# Convenience functions
# ------------------------------------------------------------------


def get_matched_addons(
    analysis: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    interactive_mode: bool = False,
) -> List[AddonSpec]:
    """Get list of addons that match the analysis and context."""
    loader = AddonLoader()
    return loader.match_addons(analysis, context, interactive_mode)


def run_matched_addons(
    analysis: Dict[str, Any],
    project_name: str,
    description: str,
    context: Optional[Dict[str, Any]] = None,
    interactive_mode: bool = False,
) -> Dict[str, str]:
    """Run all matching addons and return generated files."""
    loader = AddonLoader()
    matched = loader.match_addons(analysis, context, interactive_mode)
    return loader.run_addons(matched, project_name, description, context)


if __name__ == "__main__":
    # Test addon discovery
    loader = AddonLoader()
    print("Discovered addons:")
    for spec in loader.discover_addons():
        print(f"  - {spec.name} (priority: {spec.priority})")
        print(f"    Path: {spec.path}")
        print(f"    Triggers: {spec.triggers}")
