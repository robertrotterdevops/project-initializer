#!/usr/bin/env python3
"""
Tests for Flux Kustomization CR values.

Verifies that generated Flux manifests always use fixed timeout and interval
values matching the es-06 reference deployment, regardless of project
description complexity.

Requirements: FLUX-01, FLUX-02, FLUX-03
"""

import unittest
import yaml


def _generate_flux_manifests(description="Elasticsearch on RKE2", eck_enabled=True):
    """Helper: generate flux manifests dict from FluxDeploymentGenerator."""
    from addons.flux_deployment import FluxDeploymentGenerator

    ctx = {
        "sizing_context": {
            "source": "sizing_report",
            "eck_operator": {"version": "3.0.0"},
        }
        if eck_enabled
        else {},
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


if __name__ == "__main__":
    unittest.main()
