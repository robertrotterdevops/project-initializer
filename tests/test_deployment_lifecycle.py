#!/usr/bin/env python3
"""
Tests for the deployment_lifecycle addon.
Validates that main() generates the correct 4 shell scripts with required content.
"""

import unittest
from addons.deployment_lifecycle import main, ADDON_META, DeploymentLifecycleGenerator


class TestDeploymentLifecycleMain(unittest.TestCase):
    """Tests for the main() entry point."""

    def setUp(self):
        self.project_name = "test-proj"
        self.description = "Elasticsearch on RKE2 with FluxCD"
        self.flux_context = {
            "platform": "rke2",
            "gitops_tool": "flux",
            "sizing_context": {
                "source": "sizing_report",
                "eck_operator": True,
            },
        }

    def test_01_flux_context_returns_four_scripts(self):
        """Test 1: main() with flux context returns dict with 4 required script keys."""
        files = main(self.project_name, self.description, self.flux_context)
        self.assertIn("scripts/mirror-secrets.sh", files)
        self.assertIn("scripts/fleet-output.sh", files)
        self.assertIn("scripts/import-dashboards.sh", files)
        self.assertIn("scripts/preflight-check.sh", files)

    def test_02_argo_context_returns_empty(self):
        """Test 2: main() with gitops_tool=argo returns empty dict (Flux-only addon)."""
        argo_context = {"gitops_tool": "argo", "platform": "rke2"}
        files = main(self.project_name, self.description, argo_context)
        self.assertEqual(files, {})

    def test_03_mirror_secrets_content(self):
        """Test 3: mirror-secrets.sh contains kubectl get secret, kubectl apply, and ES secret name."""
        files = main(self.project_name, self.description, self.flux_context)
        content = files["scripts/mirror-secrets.sh"]
        self.assertIn("kubectl get secret", content)
        self.assertIn("kubectl apply", content)
        self.assertIn(f"{self.project_name}-es-elastic-user", content)

    def test_04_fleet_output_content(self):
        """Test 4: fleet-output.sh contains curl, fleet/outputs/fleet-default-output, and ca_trusted_fingerprint."""
        files = main(self.project_name, self.description, self.flux_context)
        content = files["scripts/fleet-output.sh"]
        self.assertIn("curl", content)
        self.assertIn("fleet/outputs/fleet-default-output", content)
        self.assertIn("ca_trusted_fingerprint", content)

    def test_05_import_dashboards_content(self):
        """Test 5: import-dashboards.sh contains saved_objects/_import and otel dashboard filename."""
        files = main(self.project_name, self.description, self.flux_context)
        content = files["scripts/import-dashboards.sh"]
        self.assertIn("saved_objects/_import", content)
        self.assertIn("otel-infrastructure-overview.ndjson", content)

    def test_06_preflight_cluster_connectivity(self):
        """Test 6: preflight-check.sh contains kubectl cluster-info for connectivity check."""
        files = main(self.project_name, self.description, self.flux_context)
        content = files["scripts/preflight-check.sh"]
        self.assertIn("kubectl cluster-info", content)

    def test_07_preflight_flux_installation(self):
        """Test 7: preflight-check.sh contains flux-system and kustomize-controller checks."""
        files = main(self.project_name, self.description, self.flux_context)
        content = files["scripts/preflight-check.sh"]
        self.assertIn("flux-system", content)
        self.assertIn("kustomize-controller", content)

    def test_08_preflight_crd_check(self):
        """Test 8: preflight-check.sh contains kustomizations.kustomize.toolkit.fluxcd.io CRD check."""
        files = main(self.project_name, self.description, self.flux_context)
        content = files["scripts/preflight-check.sh"]
        self.assertIn("kustomizations.kustomize.toolkit.fluxcd.io", content)

    def test_09_preflight_actionable_errors(self):
        """Test 9: preflight-check.sh contains ERROR: and Fix: on same or adjacent lines."""
        files = main(self.project_name, self.description, self.flux_context)
        content = files["scripts/preflight-check.sh"]
        self.assertIn("ERROR:", content)
        self.assertIn("Fix:", content)

    def test_10_all_scripts_have_shebang_and_pipefail(self):
        """Test 10: All generated scripts start with bash shebang and set -euo pipefail."""
        files = main(self.project_name, self.description, self.flux_context)
        for script_path, content in files.items():
            with self.subTest(script=script_path):
                self.assertTrue(
                    content.startswith("#!/usr/bin/env bash"),
                    f"{script_path} must start with '#!/usr/bin/env bash'"
                )
                self.assertIn(
                    "set -euo pipefail",
                    content,
                    f"{script_path} must contain 'set -euo pipefail'"
                )

    def test_11_addon_meta_exists_and_valid(self):
        """Test 11: ADDON_META exists with name=deployment_lifecycle and priority 19-25."""
        self.assertEqual(ADDON_META["name"], "deployment_lifecycle")
        self.assertGreaterEqual(ADDON_META["priority"], 19)
        self.assertLessEqual(ADDON_META["priority"], 25)

    def test_no_context_returns_empty(self):
        """Bonus: main() with no context (gitops_tool not flux) returns empty dict."""
        files = main(self.project_name, self.description, None)
        self.assertEqual(files, {})

    def test_non_flux_gitops_returns_empty(self):
        """Bonus: main() with gitops_tool=none returns empty dict."""
        files = main(self.project_name, self.description, {"gitops_tool": "none"})
        self.assertEqual(files, {})


class TestDeploymentLifecycleGenerator(unittest.TestCase):
    """Tests for the DeploymentLifecycleGenerator class."""

    def setUp(self):
        self.project_name = "my-es-cluster"
        self.description = "ECK on RKE2"
        self.context = {
            "platform": "rke2",
            "gitops_tool": "flux",
            "sizing_context": {"source": "sizing_report", "eck_operator": True},
        }

    def test_generator_instantiation(self):
        """Generator can be instantiated with project_name, description, context."""
        gen = DeploymentLifecycleGenerator(self.project_name, self.description, self.context)
        self.assertEqual(gen.project_name, self.project_name)

    def test_generator_returns_dict(self):
        """Generator.generate() returns a dict with string keys and string values."""
        gen = DeploymentLifecycleGenerator(self.project_name, self.description, self.context)
        result = gen.generate()
        self.assertIsInstance(result, dict)
        for k, v in result.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, str)

    def test_generator_project_name_embedded(self):
        """Generated scripts embed the project_name where relevant."""
        gen = DeploymentLifecycleGenerator(self.project_name, self.description, self.context)
        result = gen.generate()
        mirror = result.get("scripts/mirror-secrets.sh", "")
        self.assertIn(self.project_name, mirror)


if __name__ == "__main__":
    unittest.main()
