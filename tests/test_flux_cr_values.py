#!/usr/bin/env python3
"""
Tests for Flux Kustomization CR values.

Verifies that generated Flux manifests always use fixed timeout and interval
values matching the es-06 reference deployment, regardless of project
description complexity.

Requirements: FLUX-01, FLUX-02, FLUX-03, FLUX-04
"""

import os
import sys
import tempfile
import unittest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def _generate_flux_manifests(description="Elasticsearch on RKE2", eck_enabled=True, enable_otel_collector=True):
    """Helper: generate flux manifests dict from FluxDeploymentGenerator."""
    from addons.flux_deployment import FluxDeploymentGenerator

    ctx = {
        "sizing_context": {
            "source": "sizing_report",
            "eck_operator": {"version": "3.0.0"},
        }
        if eck_enabled
        else {},
        "enable_otel_collector": enable_otel_collector,
    }
    gen = FluxDeploymentGenerator("test-proj", description, ctx)
    return gen.generate_flux_manifests()


class TestFluxCRValues(unittest.TestCase):
    """FLUX-01, FLUX-02: Flux Kustomization CRs use fixed timeout/interval values."""

    # -----------------------------------------------------------------------
    # Test 1 & 2: gotk-sync.yaml — standard and complex descriptions both
    # produce interval: 5m and timeout: 2m
    # -----------------------------------------------------------------------

    def test_gotk_sync_interval_standard_description(self):
        """FLUX-01: gotk-sync.yaml interval is 5m for standard description."""
        manifests = _generate_flux_manifests("Elasticsearch on RKE2")
        doc = yaml.safe_load(manifests["gotk-sync.yaml"])
        self.assertEqual(doc["spec"]["interval"], "5m")

    def test_gotk_sync_timeout_standard_description(self):
        """FLUX-01: gotk-sync.yaml timeout is 2m for standard description."""
        manifests = _generate_flux_manifests("Elasticsearch on RKE2")
        doc = yaml.safe_load(manifests["gotk-sync.yaml"])
        self.assertEqual(doc["spec"]["timeout"], "2m")

    def test_gotk_sync_interval_complex_description(self):
        """FLUX-01: gotk-sync.yaml interval is 5m for complex description."""
        manifests = _generate_flux_manifests(
            "Advanced multi-cluster enterprise Kubernetes platform"
        )
        doc = yaml.safe_load(manifests["gotk-sync.yaml"])
        self.assertEqual(doc["spec"]["interval"], "5m")

    def test_gotk_sync_timeout_complex_description(self):
        """FLUX-01: gotk-sync.yaml timeout is 2m for complex description."""
        manifests = _generate_flux_manifests(
            "Advanced multi-cluster enterprise Kubernetes platform"
        )
        doc = yaml.safe_load(manifests["gotk-sync.yaml"])
        self.assertEqual(doc["spec"]["timeout"], "2m")

    # -----------------------------------------------------------------------
    # Test 3: kustomization-infra.yaml — interval: 5m, timeout: 10m
    # -----------------------------------------------------------------------

    def test_infra_interval_fixed(self):
        """FLUX-01: kustomization-infra.yaml interval is 5m regardless of description."""
        for desc in ["Elasticsearch on RKE2", "Advanced multi-cluster enterprise platform"]:
            with self.subTest(desc=desc):
                manifests = _generate_flux_manifests(desc)
                doc = yaml.safe_load(manifests["kustomization-infra.yaml"])
                self.assertEqual(doc["spec"]["interval"], "5m", msg=f"Failed for: {desc}")

    def test_infra_timeout_fixed(self):
        """FLUX-01: kustomization-infra.yaml timeout is 10m regardless of description."""
        for desc in ["Elasticsearch on RKE2", "Advanced multi-cluster enterprise platform"]:
            with self.subTest(desc=desc):
                manifests = _generate_flux_manifests(desc)
                doc = yaml.safe_load(manifests["kustomization-infra.yaml"])
                self.assertEqual(doc["spec"]["timeout"], "10m", msg=f"Failed for: {desc}")

    # -----------------------------------------------------------------------
    # Test 4: kustomization-apps.yaml — interval: 5m, timeout: 20m
    # -----------------------------------------------------------------------

    def test_apps_interval_fixed(self):
        """FLUX-01: kustomization-apps.yaml interval is 5m regardless of description."""
        for desc in ["Elasticsearch on RKE2", "Advanced multi-cluster enterprise platform"]:
            with self.subTest(desc=desc):
                manifests = _generate_flux_manifests(desc)
                doc = yaml.safe_load(manifests["kustomization-apps.yaml"])
                self.assertEqual(doc["spec"]["interval"], "5m", msg=f"Failed for: {desc}")

    def test_apps_timeout_fixed(self):
        """FLUX-01: kustomization-apps.yaml timeout is 20m regardless of description."""
        manifests = _generate_flux_manifests("Elasticsearch on RKE2")
        doc = yaml.safe_load(manifests["kustomization-apps.yaml"])
        self.assertEqual(doc["spec"]["timeout"], "20m")

    # -----------------------------------------------------------------------
    # Test 5: kustomization-agents.yaml (eck_enabled) — interval: 5m, timeout: 20m
    # -----------------------------------------------------------------------

    def test_agents_interval_fixed_when_eck_enabled(self):
        """FLUX-01: kustomization-agents.yaml interval is 5m when ECK is enabled."""
        for desc in ["Elasticsearch on RKE2", "Advanced multi-cluster enterprise platform"]:
            with self.subTest(desc=desc):
                manifests = _generate_flux_manifests(desc, eck_enabled=True)
                self.assertIn("kustomization-agents.yaml", manifests)
                doc = yaml.safe_load(manifests["kustomization-agents.yaml"])
                self.assertEqual(doc["spec"]["interval"], "5m", msg=f"Failed for: {desc}")

    def test_agents_timeout_fixed_when_eck_enabled(self):
        """FLUX-01: kustomization-agents.yaml timeout is 20m when ECK is enabled."""
        manifests = _generate_flux_manifests("Elasticsearch on RKE2", eck_enabled=True)
        doc = yaml.safe_load(manifests["kustomization-agents.yaml"])
        self.assertEqual(doc["spec"]["timeout"], "20m")

    # -----------------------------------------------------------------------
    # Test 6: wait values — gotk-sync uses wait: false, all others use wait: true
    # -----------------------------------------------------------------------

    def test_gotk_sync_wait_is_false(self):
        """FLUX-02: gotk-sync.yaml has wait: false."""
        manifests = _generate_flux_manifests()
        doc = yaml.safe_load(manifests["gotk-sync.yaml"])
        self.assertFalse(doc["spec"]["wait"])

    def test_infra_wait_is_true(self):
        """FLUX-02: kustomization-infra.yaml has wait: true."""
        manifests = _generate_flux_manifests()
        doc = yaml.safe_load(manifests["kustomization-infra.yaml"])
        self.assertTrue(doc["spec"]["wait"])

    def test_apps_wait_is_true(self):
        """FLUX-02: kustomization-apps.yaml has wait: true."""
        manifests = _generate_flux_manifests()
        doc = yaml.safe_load(manifests["kustomization-apps.yaml"])
        self.assertTrue(doc["spec"]["wait"])

    def test_agents_wait_is_true(self):
        """FLUX-02: kustomization-agents.yaml has wait: true."""
        manifests = _generate_flux_manifests(eck_enabled=True)
        doc = yaml.safe_load(manifests["kustomization-agents.yaml"])
        self.assertTrue(doc["spec"]["wait"])

    # -----------------------------------------------------------------------
    # Test 7: dependsOn chains match es-06 reference
    # -----------------------------------------------------------------------

    def test_gotk_sync_has_no_depends_on(self):
        """FLUX-02: gotk-sync.yaml (root) has no dependsOn."""
        manifests = _generate_flux_manifests()
        doc = yaml.safe_load(manifests["gotk-sync.yaml"])
        self.assertNotIn("dependsOn", doc["spec"])

    def test_infra_depends_on_root(self):
        """FLUX-02: kustomization-infra.yaml depends only on root."""
        manifests = _generate_flux_manifests()
        doc = yaml.safe_load(manifests["kustomization-infra.yaml"])
        depends_names = [d["name"] for d in doc["spec"]["dependsOn"]]
        self.assertIn("test-proj", depends_names)
        self.assertNotIn("test-proj-infra", depends_names)

    def test_apps_depends_on_root_and_infra(self):
        """FLUX-02: kustomization-apps.yaml depends on root + infra."""
        manifests = _generate_flux_manifests()
        doc = yaml.safe_load(manifests["kustomization-apps.yaml"])
        depends_names = [d["name"] for d in doc["spec"]["dependsOn"]]
        self.assertIn("test-proj", depends_names)
        self.assertIn("test-proj-infra", depends_names)

    def test_agents_depends_on_apps(self):
        """FLUX-02: kustomization-agents.yaml depends on apps."""
        manifests = _generate_flux_manifests(eck_enabled=True)
        doc = yaml.safe_load(manifests["kustomization-agents.yaml"])
        depends_names = [d["name"] for d in doc["spec"]["dependsOn"]]
        self.assertIn("test-proj-apps", depends_names)
        self.assertNotIn("test-proj-infra", depends_names)
        self.assertNotIn("test-proj", depends_names)

    def test_observability_depends_on_apps_and_agents(self):
        """FLUX-02b: kustomization-observability.yaml depends on apps + agents."""
        manifests = _generate_flux_manifests(eck_enabled=True)
        doc = yaml.safe_load(manifests["kustomization-observability.yaml"])
        depends_names = [d["name"] for d in doc["spec"]["dependsOn"]]
        self.assertIn("test-proj-apps", depends_names)
        self.assertIn("test-proj-agents", depends_names)

    # -----------------------------------------------------------------------
    # Test 8 (Task 2): infrastructure kustomization includes all required resources
    # -----------------------------------------------------------------------

    def test_infra_kustomization_includes_otel_and_eck_resources(self):
        """FLUX-03: Infrastructure includes Local Path Provisioner, storage classes, network policies."""
        from addons.flux_deployment import main

        files = main(
            "es-06",
            "Elasticsearch on RKE2",
            {
                "platform": "rke2",
                "sizing_context": {
                    "source": "sizing_report",
                    "eck_operator": {"version": "3.0.0"},
                },
                "primary_category": "elasticsearch",
            },
        )
        infra_kust = files["infrastructure/kustomization.yaml"]
        self.assertIn("local-path-provisioner.yaml", infra_kust)
        self.assertIn("storageclasses.yaml", infra_kust)
        self.assertIn("network-policy.yaml", infra_kust)
        self.assertIn("network-policy-allow-eck-operator.yaml", infra_kust)
        self.assertIn("../platform/eck-operator", infra_kust)
        self.assertIn("../observability/otel-collector", infra_kust)


ES06_REF = "/home/ubuntu/App-Projects-Workspace/es-06"

CRITICAL_FILES = [
    "flux-system/gotk-sync.yaml",
    "flux-system/kustomization-infra.yaml",
    "flux-system/kustomization-apps.yaml",
    "flux-system/kustomization-agents.yaml",
    "infrastructure/kustomization.yaml",
    "apps/kustomization.yaml",
    "apps/es-06/kustomization.yaml",
    "agents/kustomization.yaml",
]


def _run_full_pipeline(out_dir: str) -> dict:
    """Run initialize_project with es-06-like params into out_dir."""
    from generate_structure import initialize_project

    return initialize_project(
        project_name="es-06",
        description="Elasticsearch on RKE2",
        target_directory=out_dir,
        platform="rke2",
        gitops_tool="flux",
        iac_tool="terraform",
        repo_url="https://github.com/test-org/es-06.git",
        git_token="test-token",
        sizing_context={
            "source": "sizing_report",
            "eck_operator": {"version": "3.0.0"},
        },
    )


class TestFullPipelineVerification(unittest.TestCase):
    """FLUX-04: Full pipeline produces structurally correct output matching es-06 reference."""

    def test_full_pipeline_critical_files_exist(self):
        """FLUX-04: All 8 critical Flux/Kustomize files are created by the pipeline."""
        with tempfile.TemporaryDirectory() as out_dir:
            _run_full_pipeline(out_dir)
            for f in CRITICAL_FILES:
                self.assertTrue(
                    os.path.exists(os.path.join(out_dir, f)),
                    f"Missing: {f}",
                )

    def test_full_pipeline_matches_es06_reference(self):
        """FLUX-04: Generated critical files match es-06 reference exactly (whitespace-stripped)."""
        if not os.path.isdir(ES06_REF):
            self.skipTest(f"External reference not available: {ES06_REF}")

        with tempfile.TemporaryDirectory() as out_dir:
            _run_full_pipeline(out_dir)
            for f in CRITICAL_FILES:
                with open(os.path.join(out_dir, f)) as gen_fh:
                    gen_content = gen_fh.read().strip()
                with open(os.path.join(ES06_REF, f)) as ref_fh:
                    ref_content = ref_fh.read().strip()
                self.assertEqual(gen_content, ref_content, f"Mismatch in {f}")

    def test_full_pipeline_directory_structure(self):
        """FLUX-04: All 4 required top-level directories are created."""
        with tempfile.TemporaryDirectory() as out_dir:
            _run_full_pipeline(out_dir)
            for d in ["flux-system", "infrastructure", "apps", "agents"]:
                self.assertTrue(
                    os.path.isdir(os.path.join(out_dir, d)),
                    f"Missing directory: {d}",
                )

    def test_full_pipeline_no_dangling_kustomize_refs(self):
        """FLUX-04: No kustomization.yaml has resource references that do not resolve on disk."""
        with tempfile.TemporaryDirectory() as out_dir:
            _run_full_pipeline(out_dir)
            dangling = []
            for root, _dirs, files in os.walk(out_dir):
                for filename in files:
                    if filename != "kustomization.yaml":
                        continue
                    kust_path = os.path.join(root, filename)
                    rel_kust = os.path.relpath(kust_path, out_dir)
                    with open(kust_path) as fh:
                        doc = yaml.safe_load(fh.read())
                    if not doc:
                        continue
                    for resource in doc.get("resources", []):
                        if isinstance(resource, str) and resource.startswith("#"):
                            continue
                        target = os.path.normpath(os.path.join(root, resource))
                        if resource.endswith(".yaml") or resource.endswith(".yml"):
                            if not os.path.exists(target):
                                dangling.append(f"{rel_kust} -> {resource}")
                        else:
                            # Directory reference: must contain a kustomization.yaml
                            if not (
                                os.path.isdir(target)
                                and os.path.exists(
                                    os.path.join(target, "kustomization.yaml")
                                )
                            ):
                                dangling.append(f"{rel_kust} -> {resource}")
            self.assertEqual(
                dangling,
                [],
                f"Dangling kustomize references:\n" + "\n".join(dangling),
            )


if __name__ == "__main__":
    unittest.main()
