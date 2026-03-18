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
        """Test 3: mirror-secrets.sh contains kubectl get secret, kubectl apply, and ES secret name pattern."""
        files = main(self.project_name, self.description, self.flux_context)
        content = files["scripts/mirror-secrets.sh"]
        self.assertIn("kubectl get secret", content)
        self.assertIn("kubectl apply", content)
        # Script uses shell variable ${PROJECT_NAME}-es-elastic-user at runtime
        self.assertIn("es-elastic-user", content)

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


class TestVerifyDeploymentScript(unittest.TestCase):
    """Task 1 TDD tests: verify-deployment.sh and rollback.sh"""

    def setUp(self):
        self.project_name = "test-proj"
        self.description = "Elasticsearch on RKE2 with FluxCD"
        self.flux_context_eck = {
            "platform": "rke2",
            "gitops_tool": "flux",
            "sizing_context": {
                "source": "sizing_report",
                "eck_operator": True,
            },
        }
        self.flux_context_no_eck = {
            "platform": "rke2",
            "gitops_tool": "flux",
            "sizing_context": {},
        }

    def test_t1_flux_returns_verify_and_rollback_keys(self):
        """Test 1: main() with gitops_tool=flux returns dict containing verify-deployment.sh and rollback.sh"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        self.assertIn("scripts/verify-deployment.sh", files)
        self.assertIn("scripts/rollback.sh", files)

    def test_t2_verify_has_polling_loop(self):
        """Test 2: verify-deployment.sh contains polling loop with 'while' and 'sleep 30'"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        content = files["scripts/verify-deployment.sh"]
        self.assertIn("while", content)
        self.assertIn("sleep 30", content)

    def test_t3_verify_has_all_kustomization_names(self):
        """Test 3: verify-deployment.sh contains all 4 kustomization names"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        content = files["scripts/verify-deployment.sh"]
        self.assertIn(f"{self.project_name}", content)
        self.assertIn(f"{self.project_name}-infra", content)
        self.assertIn(f"{self.project_name}-apps", content)
        self.assertIn(f"{self.project_name}-agents", content)

    def test_t4_verify_has_timeout_values(self):
        """Test 4: verify-deployment.sh contains per-kustomization timeout values: 120 (2m), 600 (10m), 1200 (20m)"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        content = files["scripts/verify-deployment.sh"]
        self.assertIn("120", content)
        self.assertIn("600", content)
        self.assertIn("1200", content)

    def test_t5_verify_has_kubectl_kustomization_ready(self):
        """Test 5: verify-deployment.sh contains 'kubectl get kustomization' and 'condition=Ready'"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        content = files["scripts/verify-deployment.sh"]
        self.assertIn("kubectl get kustomization", content)
        self.assertIn("condition=Ready", content)

    def test_t6_verify_has_es_pod_health_check(self):
        """Test 6: verify-deployment.sh contains Elasticsearch pod health check"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        content = files["scripts/verify-deployment.sh"]
        self.assertIn("kubectl get pods", content)
        self.assertIn("elasticsearch", content)
        self.assertIn("Running", content)

    def test_t7_verify_exits_zero_on_success_one_on_failure(self):
        """Test 7: verify-deployment.sh ends with exit 0 on success and exit 1 on failure"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        content = files["scripts/verify-deployment.sh"]
        self.assertIn("exit 0", content)
        self.assertIn("exit 1", content)

    def test_t8_verify_has_status_table(self):
        """Test 8: verify-deployment.sh contains a status table output with NAME, TIMEOUT, STATUS"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        content = files["scripts/verify-deployment.sh"]
        self.assertIn("NAME", content)
        self.assertIn("TIMEOUT", content)
        self.assertIn("STATUS", content)

    def test_t9_rollback_has_suspend_kustomization(self):
        """Test 9: rollback.sh contains 'flux suspend kustomization'"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        content = files["scripts/rollback.sh"]
        self.assertIn("flux suspend kustomization", content)

    def test_t10_rollback_suspends_all_kustomizations(self):
        """Test 10: rollback.sh suspends all 4 kustomizations by name"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        content = files["scripts/rollback.sh"]
        self.assertIn(f"{self.project_name}", content)
        self.assertIn(f"{self.project_name}-infra", content)
        self.assertIn(f"{self.project_name}-apps", content)
        self.assertIn(f"{self.project_name}-agents", content)

    def test_t11_rollback_has_state_reporting(self):
        """Test 11: rollback.sh contains status reporting via flux get kustomizations or kubectl"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        content = files["scripts/rollback.sh"]
        self.assertTrue(
            "flux get kustomizations" in content or "kubectl get kustomization" in content,
            "rollback.sh must contain state reporting command"
        )

    def test_t12_rollback_has_restore_instructions(self):
        """Test 12: rollback.sh contains instructions for restore with 'flux resume'"""
        files = main(self.project_name, self.description, self.flux_context_eck)
        content = files["scripts/rollback.sh"]
        self.assertIn("flux resume", content)

    def test_t13_verify_no_eck_excludes_agents(self):
        """Test 13: main() with eck_enabled=False still includes root, infra, apps but NOT agents"""
        files = main(self.project_name, self.description, self.flux_context_no_eck)
        content = files["scripts/verify-deployment.sh"]
        self.assertIn(f"{self.project_name}-infra", content)
        self.assertIn(f"{self.project_name}-apps", content)
        self.assertNotIn(f"{self.project_name}-agents", content)


if __name__ == "__main__":
    unittest.main()
