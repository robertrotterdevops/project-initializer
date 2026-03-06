#!/usr/bin/env python3
import os
import tempfile
import unittest
from pathlib import Path

from scripts.addon_loader import AddonLoader
from scripts.generate_structure import initialize_project
from scripts.sizing_parser import _parse_json_contract


class TestIacHardening(unittest.TestCase):
    def test_json_contract_platform_all_infers_detail_platform(self) -> None:
        payload = """
        {
          "schema_version": "es-sizing.v1",
          "platform": "all",
          "project": {},
          "calculation": {"inputs": {}, "summary": {}, "tiers": []},
          "platform_details": {
            "rke2": { "cluster": {"distribution":"RKE2"} }
          }
        }
        """
        ctx = _parse_json_contract(payload)
        self.assertEqual(ctx.get("platform_detected"), "rke2")

    def test_addon_loader_matches_iac_only_trigger(self) -> None:
        loader = AddonLoader()
        analysis = {
            "primary_category": "kubernetes",
            "description": "rke2 platform project",
            "project_name": "demo",
        }
        context = {"iac_tool": "terraform", "gitops_tool": "flux", "platform": "rke2"}
        matched = loader.match_addons(analysis, context=context, interactive_mode=False)
        names = [m.name for m in matched]
        self.assertIn("terraform_gitops_trigger", names)
        self.assertIn("terraform_platform", names)
        self.assertIn("rke2_bootstrap", names)

    def test_initialize_project_generates_proxmox_terraform_and_trigger(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "rke2",
            "rke2": {
                "pools": [
                    {"name": "hot_pool", "nodes": 0, "composition": {"total_requested_cpu": 8.0, "total_requested_ram_gb": 24.0}},
                    {"name": "system_pool", "nodes": 0, "composition": {"total_requested_cpu": 6.0, "total_requested_ram_gb": 12.0}},
                ]
            },
        }
        with tempfile.TemporaryDirectory(prefix="pi-iac-hardening-") as td:
            out_dir = Path(td) / "sample-project"
            result = initialize_project(
                project_name="sample-project",
                description="",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
            )
            self.assertTrue((out_dir / "terraform/modules/proxmox_cluster/main.tf").exists())
            self.assertTrue((out_dir / "scripts/post-terraform-deploy.sh").exists())
            self.assertTrue((out_dir / "scripts/bootstrap-rke2.sh").exists())
            self.assertTrue((out_dir / "scripts/render-rke2-inventory.py").exists())
            self.assertTrue((out_dir / "ansible/rke2-bootstrap.yml").exists())
            self.assertTrue((out_dir / "docs/DEPLOYMENT_ATTENTION.md").exists())
            self.assertTrue((out_dir / "docs/RKE2_BOOTSTRAP.md").exists())
            self.assertTrue((out_dir / "sizing/config.json").exists())
            tfvars = (out_dir / "terraform/terraform.tfvars.example").read_text()
            versions_tf = (out_dir / "terraform/versions.tf").read_text()
            providers_tf = (out_dir / "terraform/providers.tf").read_text()
            variables_tf = (out_dir / "terraform/variables.tf").read_text()
            proxmox_module_tf = (out_dir / "terraform/modules/proxmox_cluster/main.tf").read_text()
            deploy_script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            self.assertIn("proxmox_node_pools", tfvars)
            self.assertIn("proxmox_endpoint", tfvars)
            self.assertIn("gitops_flux_path", tfvars)
            self.assertIn('"hot_pool"', tfvars)
            self.assertIn('source = "bpg/proxmox"', versions_tf)
            self.assertIn("endpoint", providers_tf)
            self.assertIn("api_token", providers_tf)
            self.assertIn('variable "proxmox_endpoint" {', variables_tf)
            self.assertNotIn(", default =", variables_tf)
            self.assertIn('resource "proxmox_virtual_environment_vm" "nodes"', proxmox_module_tf)
            self.assertNotIn('resource "local_file"', proxmox_module_tf)
            self.assertIn('scripts/bootstrap-rke2.sh', deploy_script)
            self.assertFalse((out_dir / "terraform/modules/aks/main.tf").exists())
            self.assertEqual(result.get("iac_tool"), "terraform")

            mode = os.stat(out_dir / "scripts/post-terraform-deploy.sh").st_mode
            self.assertTrue(mode & 0o100)

    def test_flux_gitlab_repo_and_token_flow_are_generated(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "rke2",
            "rke2": {"pools": [{"name": "system_pool", "nodes": 1}]},
        }
        repo_url = "https://gitlab.com/acme/platform/gitops-check.git"
        git_token = "glpat-EXAMPLE"
        with tempfile.TemporaryDirectory(prefix="pi-flux-gitlab-") as td:
            out_dir = Path(td) / "gitops-check"
            initialize_project(
                project_name="gitops-check",
                description="Elasticsearch platform validation",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                repo_url=repo_url,
                git_token=git_token,
                target_revision="main",
                sizing_context=sizing_context,
            )

            gitrepo = (out_dir / "flux-system/gitrepository.yaml").read_text()
            self.assertIn(f"url: {repo_url}", gitrepo)
            self.assertIn("branch: main", gitrepo)
            self.assertIn("secretRef:", gitrepo)
            self.assertIn("name: gitops-check-git-auth", gitrepo)

            secret = (out_dir / "flux-system/git-auth-secret.yaml").read_text()
            self.assertIn("name: gitops-check-git-auth", secret)
            self.assertIn("username: oauth2", secret)
            self.assertIn(f"password: {git_token}", secret)

            flux_dir_kustomization = (out_dir / "flux-system/kustomization.yaml").read_text()
            self.assertIn("apiVersion: kustomize.config.k8s.io/v1beta1", flux_dir_kustomization)
            self.assertIn("- gotk-sync.yaml", flux_dir_kustomization)

            gotk_sync = (out_dir / "flux-system/gotk-sync.yaml").read_text()
            self.assertIn("kind: Kustomization", gotk_sync)
            self.assertIn("wait: false", gotk_sync)

            cluster_kustomization = (out_dir / "clusters/management/kustomization.yaml").read_text()
            self.assertIn("- ../../flux-system", cluster_kustomization)
            self.assertNotIn("- ../../apps", cluster_kustomization)

            base_kustomization = (out_dir / "base/kustomization.yaml").read_text()
            self.assertIn("namespace: gitops-check", base_kustomization)

            infra_kustomization = (out_dir / "infrastructure/kustomization.yaml").read_text()
            self.assertIn("- ../k8s/namespace.yaml", infra_kustomization)
            self.assertIn("- local-path-provisioner.yaml", infra_kustomization)
            self.assertIn("- storageclasses.yaml", infra_kustomization)

            network_policy = (out_dir / "infrastructure/network-policy.yaml").read_text()
            self.assertIn("namespace: gitops-check", network_policy)

            app_kustomization = (out_dir / "apps/gitops-check/kustomization.yaml").read_text()
            self.assertNotIn("../../base", app_kustomization)

            self.assertTrue((out_dir / "platform/eck-operator/crds.yaml").exists())
            eck_kustomization = (out_dir / "platform/eck-operator/kustomization.yaml").read_text()
            self.assertIn("- crds.yaml", eck_kustomization)

            deploy_script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            self.assertIn(
                f'git remote set-url origin "https://oauth2:{git_token}@gitlab.com/acme/platform/gitops-check.git"',
                deploy_script,
            )
            self.assertIn(f'git remote set-url origin "{repo_url}"', deploy_script)

    def test_eck_storage_class_falls_back_to_local_path(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "rke2",
            "data_nodes": {
                "count": 3,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "100Gi",
                "storage_class": "nfs",
            },
            "cold_nodes": {
                "count": 2,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "200Gi",
                "storage_class": "unknown-class",
            },
            "frozen_nodes": {
                "count": 1,
                "memory": "16Gi",
                "cpu": "4",
                "cache_storage": "200Gi",
            },
        }
        with tempfile.TemporaryDirectory(prefix="pi-eck-storage-fallback-") as td:
            out_dir = Path(td) / "storage-fallback"
            initialize_project(
                project_name="storage-fallback",
                description="Elasticsearch storage fallback check",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
            )
            es_cluster = (out_dir / "elasticsearch/cluster.yaml").read_text()
            self.assertIn("storageClassName: local-path", es_cluster)

    def test_eck_storage_class_uses_configured_fallback(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "rke2",
            "data_nodes": {
                "count": 3,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "100Gi",
                "storage_class": "nfs",
            },
            "cold_nodes": {
                "count": 1,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "150Gi",
                "storage_class": "does-not-exist",
            },
        }
        with tempfile.TemporaryDirectory(prefix="pi-eck-storage-fallback-custom-") as td:
            out_dir = Path(td) / "storage-fallback-custom"
            initialize_project(
                project_name="storage-fallback-custom",
                description="Elasticsearch storage fallback custom check",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                fallback_storage_class="standard",
                sizing_context=sizing_context,
            )
            es_cluster = (out_dir / "elasticsearch/cluster.yaml").read_text()
            self.assertIn("storageClassName: standard", es_cluster)


if __name__ == "__main__":
    unittest.main()
