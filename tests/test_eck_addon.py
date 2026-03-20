#!/usr/bin/env python3
"""
Addon unit tests (TEST-01) and pipeline integration test (TEST-02).

Covers:
- ECK deep field-level assertions (TestECKDeploymentUnit)
- Platform manifests per-platform coverage (TestPlatformManifestsUnit)
- Smoke tests for 7 lower-priority addons (TestLowerPriorityAddonSmoke)
- Full ECK+Flux pipeline integration (TestECKFluxIntegration)
"""

import os
import sys
import tempfile
import unittest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from addons.eck_deployment import ECKDeploymentGenerator
from addons.platform_manifests import PlatformManifestsGenerator


# ---------------------------------------------------------------------------
# Task 1 — TEST-01 ECK deep assertions
# ---------------------------------------------------------------------------


class TestECKDeploymentUnit(unittest.TestCase):
    """Deep field-level assertions on ECKDeploymentGenerator output."""

    def setUp(self):
        self.context = {
            "platform": "rke2",
            "sizing_context": {
                "source": "sizing_report",
                "eck_operator": {"version": "3.0.0"},
            },
        }
        self.gen = ECKDeploymentGenerator("proj", "ES on RKE2", self.context)
        self.files = self.gen.generate()

    # -------------------------------------------------------------------
    # Elasticsearch cluster.yaml
    # -------------------------------------------------------------------

    def test_generate_returns_elasticsearch_cluster_yaml(self):
        """Output dict contains elasticsearch/cluster.yaml key."""
        self.assertIn("elasticsearch/cluster.yaml", self.files)

    def test_cluster_yaml_has_kind_elasticsearch(self):
        """cluster.yaml parses as Elasticsearch kind with nodeSets in spec."""
        doc = yaml.safe_load(self.files["elasticsearch/cluster.yaml"])
        self.assertEqual(doc["kind"], "Elasticsearch")
        self.assertIn("nodeSets", doc["spec"])

    # -------------------------------------------------------------------
    # Kibana
    # -------------------------------------------------------------------

    def test_generate_returns_kibana_yaml(self):
        """Output dict contains kibana/kibana.yaml key."""
        self.assertIn("kibana/kibana.yaml", self.files)

    def test_kibana_yaml_has_kind_kibana(self):
        """kibana.yaml parses as Kibana kind with spec.elasticsearchRef."""
        doc = yaml.safe_load(self.files["kibana/kibana.yaml"])
        self.assertEqual(doc["kind"], "Kibana")
        self.assertIn("elasticsearchRef", doc["spec"])

    # -------------------------------------------------------------------
    # ECK operator
    # -------------------------------------------------------------------

    def test_generate_returns_eck_operator_files(self):
        """Output dict contains platform/eck-operator/kustomization.yaml key."""
        self.assertIn("platform/eck-operator/kustomization.yaml", self.files)

    def test_eck_operator_kustomization_valid_yaml(self):
        """platform/eck-operator/kustomization.yaml is valid YAML."""
        content = self.files["platform/eck-operator/kustomization.yaml"]
        parsed = yaml.safe_load(content)
        self.assertIsNotNone(parsed)

    # -------------------------------------------------------------------
    # Agents
    # -------------------------------------------------------------------

    def test_generate_returns_agent_files(self):
        """Output dict contains at least one agents/ prefixed key."""
        agent_keys = [k for k in self.files if k.startswith("agents/")]
        self.assertGreater(len(agent_keys), 0, "No agents/ files found in output")

    def test_agent_yaml_has_fleet_enrollment(self):
        """At least one agents/ file contains 'fleet' substring."""
        agent_keys = [k for k in self.files if k.startswith("agents/")]
        found = any(
            "fleet" in self.files[k].lower() for k in agent_keys
        )
        self.assertTrue(found, "No agents/ file mentions 'fleet'")


# ---------------------------------------------------------------------------
# Task 1 — TEST-01 platform_manifests deep assertions
# ---------------------------------------------------------------------------


class TestPlatformManifestsUnit(unittest.TestCase):
    """Deep assertions on PlatformManifestsGenerator output per platform."""

    def test_rke2_returns_platform_rke2_files(self):
        """RKE2 platform returns files with keys matching 'platform/rke2/'."""
        gen = PlatformManifestsGenerator("proj", "ES on RKE2", {"platform": "rke2"})
        files = gen.generate()
        rke2_keys = [k for k in files if k.startswith("platform/rke2/")]
        self.assertGreater(len(rke2_keys), 0, "No platform/rke2/ files in output")

    def test_rke2_files_are_valid_yaml(self):
        """Every file in RKE2 output is parseable by yaml.safe_load."""
        gen = PlatformManifestsGenerator("proj", "ES on RKE2", {"platform": "rke2"})
        files = gen.generate()
        for path, content in files.items():
            if not path.endswith(".yaml") and not path.endswith(".yml"):
                continue
            with self.subTest(path=path):
                try:
                    list(yaml.safe_load_all(content))
                except yaml.YAMLError as exc:
                    self.fail(f"{path} is not valid YAML: {exc}")

    def test_openshift_returns_platform_openshift_files(self):
        """OpenShift platform returns files with keys matching 'platform/openshift/'."""
        gen = PlatformManifestsGenerator("proj", "ES on OCP", {"platform": "openshift"})
        files = gen.generate()
        ocp_keys = [k for k in files if k.startswith("platform/openshift/")]
        self.assertGreater(len(ocp_keys), 0, "No platform/openshift/ files in output")

    def test_aks_returns_platform_aks_files(self):
        """AKS platform returns files with keys matching 'platform/aks/'."""
        gen = PlatformManifestsGenerator("proj", "ES on AKS", {"platform": "aks"})
        files = gen.generate()
        aks_keys = [k for k in files if k.startswith("platform/aks/")]
        self.assertGreater(len(aks_keys), 0, "No platform/aks/ files in output")

    def test_openshift_worker_pools_fallback_to_normalized_pools(self):
        """OpenShift MachineSet generation accepts normalized openshift.pools output."""
        gen = PlatformManifestsGenerator(
            "proj",
            "ES on OCP",
            {
                "platform": "openshift",
                "sizing_context": {
                    "openshift": {
                        "pools": [{"name": "Hot Pool", "workers": 2}],
                        "worker_config": [{"pool_name": "Hot Pool", "vcpu": 8, "ram_gb": 32}],
                    }
                },
            },
        )
        files = gen.generate()
        machineset = files["platform/openshift/machineset-example.yaml"]
        self.assertIn("replicas: 2", machineset)
        self.assertIn("Target flavor for this pool: 8 vCPU / 32 GiB", machineset)

    def test_delivery_blueprint_documents_cross_platform_variants(self):
        """Shared platform blueprint documents the supported delivery patterns."""
        gen = PlatformManifestsGenerator(
            "proj",
            "Rancher governed RKE2 Elastic platform with Fleet",
            {"platform": "rke2"},
        )
        files = gen.generate()
        blueprint = files["platform/DELIVERY_BLUEPRINT.md"]
        readme = files["platform/README.md"]
        self.assertIn("Proxmox + RKE2", blueprint)
        self.assertIn("Rancher-governed RKE2", blueprint)
        self.assertIn("OpenShift", blueprint)
        self.assertIn("Azure AKS", blueprint)
        self.assertIn("Requested Variant", blueprint)
        self.assertIn("DELIVERY_BLUEPRINT.md", readme)

    def test_rke2_contains_storage_class(self):
        """At least one RKE2 file contains 'StorageClass' or 'storage' substring."""
        gen = PlatformManifestsGenerator("proj", "ES on RKE2", {"platform": "rke2"})
        files = gen.generate()
        rke2_keys = [k for k in files if k.startswith("platform/rke2/")]
        found = any(
            "StorageClass" in files[k] or "storage" in files[k].lower()
            for k in rke2_keys
        )
        self.assertTrue(found, "No rke2 file contains StorageClass or storage")


# ---------------------------------------------------------------------------
# Task 2 — TEST-01 smoke tests for lower-priority addons
# ---------------------------------------------------------------------------


class TestLowerPriorityAddonSmoke(unittest.TestCase):
    """Smoke tests: every lower-priority addon returns a non-empty dict."""

    def test_terraform_aks_smoke(self):
        """terraform_aks.main returns non-empty dict."""
        from addons.terraform_aks import main
        result = main("smoke", "AKS test", {"platform": "aks"})
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)

    def test_argo_deployment_smoke(self):
        """argo_deployment.main returns non-empty dict."""
        from addons.argo_deployment import main
        result = main("smoke", "ArgoCD test", {"platform": "rke2", "gitops_tool": "argo"})
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)

    def test_observability_stack_smoke(self):
        """observability_stack.main returns non-empty dict when a feature is enabled."""
        from addons.observability_stack import main
        result = main("smoke", "Observability", {"platform": "rke2", "enable_otel_collector": True})
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)

    def test_rke2_bootstrap_smoke(self):
        """rke2_bootstrap.main (3-arg addon interface) returns non-empty dict.

        Requires iac_tool='terraform' and platform in {rke2, proxmox} to produce output.
        """
        from addons.rke2_bootstrap import main as rke2_main
        result = rke2_main("smoke", "RKE2 bootstrap", {"platform": "rke2", "iac_tool": "terraform"})
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)

    def test_sizing_integration_smoke(self):
        """sizing_integration.main returns non-empty dict with sizing_context."""
        from addons.sizing_integration import main
        result = main(
            "smoke",
            "Sizing test",
            {
                "platform": "rke2",
                "sizing_context": {
                    "source": "sizing_report",
                    "eck_operator": {"version": "3.0.0"},
                },
            },
        )
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)

    def test_terraform_gitops_trigger_smoke(self):
        """terraform_gitops_trigger.main returns non-empty dict.

        Requires iac_tool='terraform' to produce output.
        """
        from addons.terraform_gitops_trigger import main
        result = main("smoke", "Trigger test", {"platform": "rke2", "gitops_tool": "flux", "iac_tool": "terraform"})
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)

    def test_terraform_platform_smoke(self):
        """terraform_platform.main returns non-empty dict."""
        from addons.terraform_platform import main
        result = main("smoke", "Platform test", {"platform": "rke2"})
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)

    def test_terraform_platform_readme_references_delivery_blueprint(self):
        """Platform Terraform docs should point back to the shared delivery model."""
        from addons.terraform_platform import main
        result = main("smoke", "Platform test", {"platform": "proxmox"})
        readme = result.get("terraform/README.md", "")
        self.assertIn("Proxmox-backed RKE2", readme)
        self.assertIn("../platform/DELIVERY_BLUEPRINT.md", readme)
        self.assertIn("bootstrap-rke2.sh", readme)


# ---------------------------------------------------------------------------
# Task 2 — TEST-02 full ECK+Flux integration test
# ---------------------------------------------------------------------------


class TestECKFluxIntegration(unittest.TestCase):
    """Full pipeline integration: ECK+Flux+RKE2 produces complete directory layout."""

    @classmethod
    def setUpClass(cls):
        from scripts.generate_structure import initialize_project

        cls._tmpdir = tempfile.TemporaryDirectory(prefix="pi-test-")
        cls.out_dir = cls._tmpdir.name
        initialize_project(
            project_name="integ-test",
            description="Elasticsearch on RKE2",
            target_directory=cls.out_dir,
            platform="rke2",
            gitops_tool="flux",
            iac_tool="terraform",
            sizing_context={
                "source": "sizing_report",
                "eck_operator": {"version": "3.0.0"},
            },
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def test_full_pipeline_produces_eck_directories(self):
        """Pipeline produces elasticsearch/, kibana/, agents/, platform/eck-operator/, flux-system/."""
        expected_dirs = [
            "elasticsearch",
            "kibana",
            "agents",
            "platform/eck-operator",
            "flux-system",
        ]
        for d in expected_dirs:
            full_path = os.path.join(self.out_dir, d)
            self.assertTrue(
                os.path.isdir(full_path),
                f"Expected directory missing: {d}",
            )

    def test_full_pipeline_produces_lifecycle_scripts(self):
        """Pipeline produces scripts/ directory with at least one .sh file."""
        scripts_dir = os.path.join(self.out_dir, "scripts")
        self.assertTrue(os.path.isdir(scripts_dir), "scripts/ directory missing")
        sh_files = [f for f in os.listdir(scripts_dir) if f.endswith(".sh")]
        self.assertGreater(len(sh_files), 0, "No .sh files found in scripts/")

    def test_full_pipeline_all_yaml_parseable(self):
        """Every .yaml file produced by the pipeline is parseable by yaml.safe_load_all."""
        failed = []
        for root, _dirs, files in os.walk(self.out_dir):
            for filename in files:
                if not (filename.endswith(".yaml") or filename.endswith(".yml")):
                    continue
                filepath = os.path.join(root, filename)
                rel = os.path.relpath(filepath, self.out_dir)
                try:
                    with open(filepath) as fh:
                        list(yaml.safe_load_all(fh.read()))
                except yaml.YAMLError as exc:
                    failed.append(f"{rel}: {exc}")
        self.assertEqual(
            failed,
            [],
            "YAML parse errors:\n" + "\n".join(failed),
        )


if __name__ == "__main__":
    unittest.main()
