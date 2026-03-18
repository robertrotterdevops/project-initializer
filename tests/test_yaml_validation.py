#!/usr/bin/env python3
"""
YAML structural validation tests (TEST-03) and es-06 reference comparison tests (TEST-04).

TEST-03: Validates that generated Flux CRs have all required fields and that
         kustomize resource references are not broken (dict-based, no disk access).

TEST-04: Validates that the generated output directory structure and key manifest
         fields match the es-06 reference deployment.

Requirements: TEST-03, TEST-04
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ES06_REF = "/home/ubuntu/App-Projects-Workspace/es-06"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_flux_files():
    """Return the dict produced by flux_deployment.main() for a standard ECK+RKE2 project."""
    from addons.flux_deployment import main
    return main(
        "test-proj",
        "Elasticsearch on RKE2",
        {
            "platform": "rke2",
            "gitops_tool": "flux",
            "sizing_context": {
                "source": "sizing_report",
                "eck_operator": {"version": "3.0.0"},
            },
        },
    )


# ---------------------------------------------------------------------------
# TEST-03: Flux CR structural validation
# ---------------------------------------------------------------------------

class TestFluxCRStructure(unittest.TestCase):
    """TEST-03: Flux Kustomization and GitRepository CRs have all required fields."""

    def _get_flux_files(self):
        return _get_flux_files()

    # ------------------------------------------------------------------
    # Kustomization CRs (kustomize.toolkit.fluxcd.io)
    # ------------------------------------------------------------------

    def test_flux_kustomization_cr_has_spec_interval(self):
        """Every Flux Kustomization CR has a non-empty spec.interval."""
        files = self._get_flux_files()
        found_cr = False
        for key, content in files.items():
            if "kustomize.toolkit.fluxcd.io" not in content:
                continue
            with self.subTest(file=key):
                for doc in yaml.safe_load_all(content):
                    if doc is None:
                        continue
                    if doc.get("apiVersion", "").startswith("kustomize.toolkit.fluxcd.io"):
                        found_cr = True
                        interval = doc.get("spec", {}).get("interval", "")
                        self.assertTrue(
                            interval,
                            f"{key}: spec.interval is missing or empty",
                        )
        self.assertTrue(found_cr, "No Flux Kustomization CRs found in flux_deployment.main() output")

    def test_flux_kustomization_cr_has_spec_path(self):
        """Every Flux Kustomization CR has a non-empty spec.path."""
        files = self._get_flux_files()
        found_cr = False
        for key, content in files.items():
            if "kustomize.toolkit.fluxcd.io" not in content:
                continue
            with self.subTest(file=key):
                for doc in yaml.safe_load_all(content):
                    if doc is None:
                        continue
                    if doc.get("apiVersion", "").startswith("kustomize.toolkit.fluxcd.io"):
                        found_cr = True
                        path = doc.get("spec", {}).get("path", "")
                        self.assertTrue(
                            path,
                            f"{key}: spec.path is missing or empty",
                        )
        self.assertTrue(found_cr, "No Flux Kustomization CRs found in flux_deployment.main() output")

    def test_flux_kustomization_cr_has_spec_sourceRef(self):
        """Every Flux Kustomization CR has spec.sourceRef present."""
        files = self._get_flux_files()
        found_cr = False
        for key, content in files.items():
            if "kustomize.toolkit.fluxcd.io" not in content:
                continue
            with self.subTest(file=key):
                for doc in yaml.safe_load_all(content):
                    if doc is None:
                        continue
                    if doc.get("apiVersion", "").startswith("kustomize.toolkit.fluxcd.io"):
                        found_cr = True
                        source_ref = doc.get("spec", {}).get("sourceRef")
                        self.assertIsNotNone(
                            source_ref,
                            f"{key}: spec.sourceRef is missing",
                        )
        self.assertTrue(found_cr, "No Flux Kustomization CRs found in flux_deployment.main() output")

    # ------------------------------------------------------------------
    # GitRepository CRs (source.toolkit.fluxcd.io)
    # ------------------------------------------------------------------

    def test_flux_gitrepository_has_spec_url(self):
        """Every GitRepository CR has a non-empty spec.url."""
        files = self._get_flux_files()
        found_cr = False
        for key, content in files.items():
            if "source.toolkit.fluxcd.io" not in content:
                continue
            with self.subTest(file=key):
                for doc in yaml.safe_load_all(content):
                    if doc is None:
                        continue
                    api_version = doc.get("apiVersion", "")
                    kind = doc.get("kind", "")
                    if api_version.startswith("source.toolkit.fluxcd.io") and kind == "GitRepository":
                        found_cr = True
                        url = doc.get("spec", {}).get("url", "")
                        self.assertTrue(
                            url,
                            f"{key}: spec.url is missing or empty",
                        )
        self.assertTrue(found_cr, "No GitRepository CRs found in flux_deployment.main() output")

    def test_flux_gitrepository_has_spec_interval(self):
        """Every GitRepository CR has a non-empty spec.interval."""
        files = self._get_flux_files()
        found_cr = False
        for key, content in files.items():
            if "source.toolkit.fluxcd.io" not in content:
                continue
            with self.subTest(file=key):
                for doc in yaml.safe_load_all(content):
                    if doc is None:
                        continue
                    api_version = doc.get("apiVersion", "")
                    kind = doc.get("kind", "")
                    if api_version.startswith("source.toolkit.fluxcd.io") and kind == "GitRepository":
                        found_cr = True
                        interval = doc.get("spec", {}).get("interval", "")
                        self.assertTrue(
                            interval,
                            f"{key}: spec.interval is missing or empty",
                        )
        self.assertTrue(found_cr, "No GitRepository CRs found in flux_deployment.main() output")


# ---------------------------------------------------------------------------
# TEST-03: Kustomize reference validation (dict-based, no disk access)
# ---------------------------------------------------------------------------

class TestKustomizeRefs(unittest.TestCase):
    """TEST-03: kustomize resource references in the generated output dict resolve to existing keys."""

    def _get_flux_files(self):
        return _get_flux_files()

    def test_kustomize_yaml_resources_resolve_to_existing_keys(self):
        """
        For every plain kustomization.yaml in the output (not a Flux Kustomization CR),
        each intra-addon resource reference must resolve to an existing key in the output dict.

        Intra-addon references are those that do NOT traverse out of the dict's root directory
        (i.e., they don't start with "../" to climb above the current top-level directory).
        Cross-addon references like "../../elasticsearch" or "../platform/eck-operator" are
        expected to be resolved by the full pipeline — this test validates only the resources
        that the flux_deployment addon itself must supply.

        Resolution rules (checked in order):
          1. Exact key match: dir_prefix/resource
          2. With /kustomization.yaml appended: dir_prefix/resource/kustomization.yaml
          3. With .yaml appended: dir_prefix/resource.yaml
        """
        files = self._get_flux_files()
        missing = []

        for key, content in files.items():
            if not key.endswith("kustomization.yaml"):
                continue
            # Skip Flux Kustomization CRs (they have a different apiVersion)
            if "kustomize.toolkit.fluxcd.io" in content:
                continue

            doc = yaml.safe_load(content)
            if not doc:
                continue

            resources = doc.get("resources", [])
            if not resources:
                continue

            # Determine the directory prefix for this kustomization.yaml
            dir_prefix = "/".join(key.split("/")[:-1])  # e.g. "flux-system" from "flux-system/kustomization.yaml"

            for resource in resources:
                if not isinstance(resource, str):
                    continue
                if resource.startswith("#"):
                    continue

                # Resolve resource relative to the kustomization.yaml's directory
                if dir_prefix:
                    raw = dir_prefix + "/" + resource
                else:
                    raw = resource

                # Normalize path (handle ../ traversal)
                parts = []
                for part in raw.split("/"):
                    if part == "..":
                        if parts:
                            parts.pop()
                    elif part and part != ".":
                        parts.append(part)
                resolved = "/".join(parts)

                # Skip cross-addon references: if the resolved path would leave the
                # top-level directory owned by this addon (e.g. infrastructure/ references
                # ../platform/eck-operator which resolves to platform/eck-operator —
                # that belongs to a different addon and is wired by the full pipeline).
                if dir_prefix and not resolved.startswith(dir_prefix.split("/")[0]):
                    continue

                # Check if resolved path (or variants) exists as a key
                candidates = [
                    resolved,
                    resolved + "/kustomization.yaml",
                    resolved + ".yaml",
                ]
                found = any(c in files for c in candidates)
                if not found:
                    missing.append(f"{key} -> {resource} (resolved: {resolved})")

        self.assertEqual(
            missing,
            [],
            "Intra-addon kustomize resource references not found as keys in output dict:\n"
            + "\n".join(missing),
        )

    def test_no_empty_kustomization_yaml(self):
        """Every kustomization.yaml value in the output dict has non-zero length."""
        files = self._get_flux_files()
        empty = []
        for key, content in files.items():
            if key.endswith("kustomization.yaml") and not content.strip():
                empty.append(key)
        self.assertEqual(
            empty,
            [],
            "Empty kustomization.yaml files found:\n" + "\n".join(empty),
        )


# ---------------------------------------------------------------------------
# TEST-04: es-06 reference comparison
# ---------------------------------------------------------------------------

class TestReferenceComparison(unittest.TestCase):
    """TEST-04: Generated output structure and key manifest fields match the es-06 reference."""

    _es06_available: bool = False

    @classmethod
    def setUpClass(cls):
        cls._es06_available = os.path.isdir(ES06_REF)

    def setUp(self):
        if not self._es06_available:
            self.skipTest(
                f"es-06 reference not found at {ES06_REF} -- skipping TEST-04"
            )

    def _generate_project(self):
        """Run initialize_project into a temporary directory and return the output Path."""
        self._tmpdir = tempfile.TemporaryDirectory(prefix="pi-ref-test-")
        out_dir = Path(self._tmpdir.name) / "ref-test"
        from scripts.generate_structure import initialize_project
        initialize_project(
            project_name="ref-test",
            description="Elasticsearch on RKE2",
            target_directory=str(out_dir),
            platform="rke2",
            gitops_tool="flux",
            iac_tool="terraform",
            sizing_context={
                "source": "sizing_report",
                "eck_operator": {"version": "3.0.0"},
            },
        )
        return out_dir

    def tearDown(self):
        if hasattr(self, "_tmpdir"):
            self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # Directory structure assertions
    # ------------------------------------------------------------------

    def test_generated_has_es06_top_level_directories(self):
        """Generated project has all core top-level directories that es-06 has."""
        out_dir = self._generate_project()
        core_dirs = [
            "flux-system",
            "infrastructure",
            "apps",
            "agents",
            "elasticsearch",
            "kibana",
            "platform",
            "observability",
        ]
        for d in core_dirs:
            with self.subTest(directory=d):
                self.assertTrue(
                    os.path.isdir(out_dir / d),
                    f"Expected top-level directory '{d}' not found in generated output",
                )

    def test_generated_has_es06_nested_eck_dirs(self):
        """Generated project has nested ECK operator and elasticsearch directories."""
        out_dir = self._generate_project()
        self.assertTrue(
            os.path.isdir(out_dir / "platform" / "eck-operator"),
            "Expected platform/eck-operator/ directory not found in generated output",
        )

    # ------------------------------------------------------------------
    # Key manifest field assertions
    # ------------------------------------------------------------------

    def test_generated_elasticsearch_cluster_has_matching_fields(self):
        """
        Generated elasticsearch/cluster.yaml has same kind and top-level spec keys as es-06.

        Field presence only — exact values are not compared (project names differ).
        """
        out_dir = self._generate_project()
        gen_cluster_path = out_dir / "elasticsearch" / "cluster.yaml"
        ref_cluster_path = Path(ES06_REF) / "elasticsearch" / "cluster.yaml"

        self.assertTrue(
            gen_cluster_path.exists(),
            "elasticsearch/cluster.yaml not found in generated output",
        )
        self.assertTrue(
            ref_cluster_path.exists(),
            f"elasticsearch/cluster.yaml not found in es-06 reference at {ref_cluster_path}",
        )

        with open(gen_cluster_path) as fh:
            gen_doc = yaml.safe_load(fh.read())
        with open(ref_cluster_path) as fh:
            ref_doc = yaml.safe_load(fh.read())

        # Both must be Elasticsearch kind
        self.assertEqual(gen_doc.get("kind"), "Elasticsearch")
        self.assertEqual(ref_doc.get("kind"), "Elasticsearch")

        # Both must have nodeSets in spec
        self.assertIn("nodeSets", gen_doc.get("spec", {}), "Generated cluster.yaml missing spec.nodeSets")
        self.assertIn("nodeSets", ref_doc.get("spec", {}), "Reference cluster.yaml missing spec.nodeSets")

        # Both must have version in spec
        self.assertIn("version", gen_doc.get("spec", {}), "Generated cluster.yaml missing spec.version")
        self.assertIn("version", ref_doc.get("spec", {}), "Reference cluster.yaml missing spec.version")

    def test_generated_flux_system_has_gotk_sync(self):
        """Generated project contains flux-system/gotk-sync.yaml."""
        out_dir = self._generate_project()
        self.assertTrue(
            (out_dir / "flux-system" / "gotk-sync.yaml").exists(),
            "flux-system/gotk-sync.yaml not found in generated output",
        )

    def test_generated_infrastructure_has_kustomization(self):
        """Generated project contains infrastructure/kustomization.yaml."""
        out_dir = self._generate_project()
        self.assertTrue(
            (out_dir / "infrastructure" / "kustomization.yaml").exists(),
            "infrastructure/kustomization.yaml not found in generated output",
        )

    def test_es06_missing_skips_gracefully(self):
        """When ES06_REF does not exist, tests skip with a clear message instead of erroring."""
        original = self.__class__._es06_available
        try:
            self.__class__._es06_available = False
            with self.assertRaises(unittest.SkipTest) as ctx:
                self.setUp()
            self.assertIn("es-06 reference not found", str(ctx.exception))
        finally:
            self.__class__._es06_available = original


if __name__ == "__main__":
    unittest.main()
