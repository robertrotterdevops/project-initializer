#!/usr/bin/env python3

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from generate_structure import initialize_project
from generation_governance import MANIFEST_SCHEMA_VERSION, OPERATIONS_SCHEMA_VERSION, default_header_policy, default_license_policy


class TestGenerationGovernance(unittest.TestCase):
    def test_initialize_project_writes_generation_manifest(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = initialize_project(
                project_name="governance-check",
                description="Elasticsearch on RKE2",
                target_directory=out_dir,
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            manifest_path = Path(result["generation_manifest"])
            self.assertTrue(manifest_path.exists())

            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], MANIFEST_SCHEMA_VERSION)
            self.assertEqual(payload["project"]["name"], "governance-check")
            self.assertEqual(payload["project"]["platform"], "rke2")
            self.assertEqual(payload["governance"]["license_policy"], default_license_policy())
            self.assertEqual(payload["governance"]["header_policy"], default_header_policy())
            self.assertTrue(any(item["path"] == "README.md" for item in payload["files"]))
            self.assertTrue(any(Path(item).name == "project-initializer-manifest.json" for item in result["generated_files"]))
            self.assertTrue(any(Path(item).name == "project-initializer-operations.json" for item in result["generated_files"]))
            self.assertTrue(any(Path(item).name == "project-initializer-validation-report.json" for item in result["generated_files"]))

    def test_operations_manifest_contains_generated_scripts(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = initialize_project(
                project_name="operations-check",
                description="Elasticsearch on RKE2 with observability",
                target_directory=out_dir,
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
                enable_otel_collector=True,
            )
            payload = json.loads(Path(result["generation_operations_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], OPERATIONS_SCHEMA_VERSION)
            keys = {item["key"] for item in payload["operations"]}
            self.assertIn("preflight-check", keys)
            self.assertIn("cluster-healthcheck", keys)
            self.assertIn("post-terraform-deploy", keys)
            healthcheck = next(item for item in payload["operations"] if item["key"] == "cluster-healthcheck")
            self.assertEqual(healthcheck["recommended_order"], 40)
            self.assertEqual(healthcheck["arguments"][0]["name"], "kubeconfig_path")
            post_tf = next(item for item in payload["operations"] if item["key"] == "post-terraform-deploy")
            self.assertTrue(post_tf["confirmation_required"])
            self.assertEqual(post_tf["confirmation_phrase"], "operations-check")
            self.assertIn("runbooks", payload)
            self.assertGreater(len(payload["runbooks"][0]["steps"]), 0)
            self.assertEqual(payload["runbooks"][0]["steps"][0]["key"], "preflight-check")
            self.assertIn("docs", payload["runbooks"][0]["steps"][0])
            self.assertIn("docs/DEPLOYMENT_ATTENTION.md", payload["runbooks"][0]["steps"][0]["docs"])

    def test_manifest_contains_addon_provenance_records(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = initialize_project(
                project_name="provenance-check",
                description="Elasticsearch on RKE2 with observability",
                target_directory=out_dir,
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
                enable_otel_collector=True,
                sizing_context={"source": "sizing_report", "eck_operator": {"version": "3.0.0"}},
            )
            payload = json.loads(Path(result["generation_manifest"]).read_text(encoding="utf-8"))
            addon_records = [item for item in payload["files"] if item["source_type"] == "addon"]
            self.assertTrue(addon_records)
            self.assertTrue(any(item["source_name"] == "eck_deployment" for item in addon_records))
            self.assertTrue(any(item["source_name"] == "observability_stack" for item in addon_records))

    def test_manifest_result_fields_are_returned(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = initialize_project(
                project_name="result-fields-check",
                description="AKS elastic project",
                target_directory=out_dir,
                platform="aks",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            self.assertIn("generation_manifest", result)
            self.assertIn("generation_operations_manifest", result)
            self.assertIn("generation_validation_report", result)
            self.assertIn("license_policy", result)
            self.assertIn("header_policy", result)

    def test_compliance_artifacts_are_generated(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = initialize_project(
                project_name="compliance-check",
                description="Elasticsearch on RKE2",
                target_directory=out_dir,
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
                license_policy={
                    "license_id": "Apache-2.0",
                    "organization": "Platform Team",
                    "confidentiality": "internal",
                },
                header_policy={"mode": "minimal", "managed_header": True},
            )
            root = Path(result["project_path"])
            self.assertTrue((root / "LICENSE").exists())
            self.assertTrue((root / "NOTICE").exists())
            self.assertTrue((root / "GENERATED_BY.md").exists())
            self.assertIn("Apache License", (root / "LICENSE").read_text(encoding="utf-8"))
            self.assertIn("Generated by project-initializer", (root / "NOTICE").read_text(encoding="utf-8"))
            self.assertIn("Generator version", (root / "GENERATED_BY.md").read_text(encoding="utf-8"))

    def test_header_policy_applies_to_text_files_only(self):
        with tempfile.TemporaryDirectory() as out_dir:
            result = initialize_project(
                project_name="header-check",
                description="Elasticsearch on RKE2",
                target_directory=out_dir,
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
                license_policy={
                    "license_id": "MIT",
                    "organization": "Platform Team",
                    "confidentiality": "restricted",
                },
                header_policy={"mode": "full", "managed_header": True},
            )
            root = Path(result["project_path"])
            readme = (root / "README.md").read_text(encoding="utf-8")
            self.assertIn("Generated by project-initializer.", readme)
            manifest = json.loads((root / "project-initializer-manifest.json").read_text(encoding="utf-8"))
            validation = json.loads((root / "project-initializer-validation-report.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], MANIFEST_SCHEMA_VERSION)
            self.assertTrue(validation["ok"])
            self.assertEqual(validation["summary"]["header_mode"], "full")
            self.assertNotIn("Generated by project-initializer.", (root / "project-initializer-manifest.json").read_text(encoding="utf-8"))
            if (root / "scripts" / "cluster-healthcheck.sh").exists():
                shell_text = (root / "scripts" / "cluster-healthcheck.sh").read_text(encoding="utf-8")
                self.assertTrue(shell_text.startswith("#!/usr/bin/env bash\n# Generated by project-initializer."))


if __name__ == "__main__":
    unittest.main()
