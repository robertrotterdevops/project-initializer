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

    def test_json_contract_rke2_v1_is_normalized_for_addons(self) -> None:
        payload = """
        {
          "schema_version": "es-sizing-rke2.v1",
          "platform": "rke2",
          "project": {"name": "OS-1"},
          "elasticsearch": {
            "inputs": {
              "ingest_gb_per_day": 1,
              "total_retention_days": 365,
              "workload_type": "mixed"
            },
            "summary": {
              "cluster_health_score": 93,
              "total_nodes": 2,
              "total_data_nodes": 2,
              "total_vcpu_selected": 4,
              "total_ram_gb_selected": 16,
              "total_local_disk_gb_selected": 200,
              "total_snapshot_storage_gb": 200,
              "total_master_nodes": 0
            },
            "tiers": [
              {"name": "hot", "nodes": 1, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 100, "snapshot_repo_total_gb": 100},
              {"name": "cold", "nodes": 1, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 100, "snapshot_repo_total_gb": 100},
              {"name": "frozen", "nodes": 0, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 0, "snapshot_repo_total_gb": 0}
            ]
          },
          "rke2": {
            "storage": {"profile": "local-nvme"},
            "pools": [
              {"name": "hot_pool", "nodes": 1, "vcpu_per_node": 12, "ram_gb_per_node": 20, "disk_gb_per_node": null},
              {"name": "cold_pool", "nodes": 1, "vcpu_per_node": 12, "ram_gb_per_node": 15, "disk_gb_per_node": null},
              {"name": "system_pool", "nodes": 2, "vcpu_per_node": 8, "ram_gb_per_node": 10, "disk_gb_per_node": null}
            ],
            "elastic_tier_to_pool": [
              {"tier": "hot", "pool": "hot_pool"},
              {"tier": "cold", "pool": "cold_pool"},
              {"tier": "frozen", "pool": "cold_pool"}
            ],
            "composition": {
              "kibana": {"count": 1},
              "fleet": {"count": 1}
            },
            "overhead_breakdown": {
              "stack_components": {"vcpu": 4, "ram_gb": 8}
            }
          }
        }
        """
        ctx = _parse_json_contract(payload)
        self.assertEqual(ctx.get("platform_detected"), "rke2")
        self.assertEqual(ctx.get("health_score"), 93)
        self.assertEqual(ctx.get("inputs", {}).get("ingest_per_day_gb"), 1)
        self.assertEqual(ctx.get("inputs", {}).get("retention_days"), 365)
        self.assertEqual(ctx.get("summary", {}).get("total_vcpu"), 4)
        self.assertEqual(ctx.get("summary", {}).get("total_ram_gb"), 16)
        self.assertEqual(ctx.get("data_nodes", {}).get("count"), 1)
        self.assertEqual(ctx.get("cold_nodes", {}).get("count"), 1)
        self.assertEqual(ctx.get("data_nodes", {}).get("storage_class"), "local-path")
        self.assertEqual(ctx.get("kibana", {}).get("count"), 1)
        self.assertEqual(ctx.get("fleet_server", {}).get("count"), 1)
        pools = {p["name"]: p for p in ctx.get("rke2", {}).get("pools", [])}
        self.assertEqual(pools["hot_pool"]["disk_gb_per_node"], 100)
        self.assertEqual(pools["cold_pool"]["disk_gb_per_node"], 100)

    def test_json_contract_rke2_v1_preserves_normalized_alias_fields(self) -> None:
        payload = """
        {
          "schema_version": "es-sizing-rke2.v1",
          "platform": "rke2",
          "project": {"name": "OS-1"},
          "elasticsearch": {
            "inputs": {
              "ingest_per_day_gb": 2,
              "retention_days": 30
            },
            "summary": {
              "cluster_health_score": 91,
              "total_nodes": 2,
              "total_vcpu": 6,
              "total_ram_gb": 24,
              "total_disk_gb": 300
            },
            "tiers": []
          },
          "rke2": {
            "storage": {"profile": "Local_NVME"},
            "pools": []
          }
        }
        """
        ctx = _parse_json_contract(payload)
        self.assertEqual(ctx.get("inputs", {}).get("ingest_per_day_gb"), 2)
        self.assertEqual(ctx.get("inputs", {}).get("retention_days"), 30)
        self.assertEqual(ctx.get("summary", {}).get("total_vcpu"), 6)
        self.assertEqual(ctx.get("summary", {}).get("total_ram_gb"), 24)
        self.assertEqual(ctx.get("summary", {}).get("total_disk_gb"), 300)

    def test_json_contract_platform_v1_is_normalized_for_addons(self) -> None:
        payload = """
        {
          "schema_version": "es-sizing-platform.v1",
          "platform": "openshift",
          "project": {"name": "OS-1"},
          "calculation": {
            "inputs": {
              "ingest_gb_per_day": 1,
              "total_retention_days": 365,
              "workload_type": "mixed"
            },
            "summary": {
              "cluster_health_score": 93,
              "total_nodes": 2,
              "total_data_nodes": 2,
              "total_vcpu_selected": 4,
              "total_ram_gb_selected": 16,
              "total_local_disk_gb_selected": 200,
              "total_snapshot_storage_gb": 200,
              "total_master_nodes": 0
            },
            "tiers": [
              {"name": "hot", "nodes": 1, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 100, "snapshot_repo_total_gb": 100},
              {"name": "cold", "nodes": 1, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 100, "snapshot_repo_total_gb": 100},
              {"name": "frozen", "nodes": 0, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 0, "snapshot_repo_total_gb": 0}
            ]
          },
          "platform_details": {
            "pools": [
              {"name": "hot_pool", "nodes": 1, "vcpu_per_node": 4, "ram_gb_per_node": 16, "disk_gb_per_node": null, "composition": {"kibana_pods": 1, "fleet_pods": 1}},
              {"name": "cold_pool", "nodes": 1, "vcpu_per_node": 4, "ram_gb_per_node": 16, "disk_gb_per_node": null, "composition": {}},
              {"name": "system_pool", "nodes": 2, "vcpu_per_node": 4, "ram_gb_per_node": 8, "disk_gb_per_node": null, "composition": {}}
            ],
            "stack_components": {"vcpu": 4, "ram_gb": 8}
          }
        }
        """
        ctx = _parse_json_contract(payload)
        self.assertEqual(ctx.get("platform_detected"), "openshift")
        self.assertEqual(ctx.get("health_score"), 93)
        self.assertEqual(ctx.get("inputs", {}).get("ingest_per_day_gb"), 1)
        self.assertEqual(ctx.get("data_nodes", {}).get("count"), 1)
        self.assertEqual(ctx.get("cold_nodes", {}).get("count"), 1)
        self.assertEqual(ctx.get("kibana", {}).get("count"), 1)
        self.assertEqual(ctx.get("fleet_server", {}).get("count"), 1)
        pools = {p["name"]: p for p in ctx.get("rke2", {}).get("pools", [])}
        self.assertEqual(pools["hot_pool"]["disk_gb_per_node"], 100)
        self.assertEqual(pools["cold_pool"]["disk_gb_per_node"], 100)

    def test_initialize_project_proxmox_tfvars_uses_platform_v1_pools(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "openshift",
            "openshift": {
                "pools": [
                    {"name": "hot_pool", "nodes": 1, "vcpu_per_node": 4, "ram_gb_per_node": 16, "disk_gb_per_node": 100},
                    {"name": "cold_pool", "nodes": 1, "vcpu_per_node": 4, "ram_gb_per_node": 16, "disk_gb_per_node": 100},
                    {"name": "system_pool", "nodes": 2, "vcpu_per_node": 4, "ram_gb_per_node": 8, "disk_gb_per_node": 80}
                ]
            }
        }
        with tempfile.TemporaryDirectory(prefix="pi-platform-pools-") as td:
            out_dir = Path(td) / "sample-project"
            initialize_project(
                project_name="sample-project",
                description="",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
            )
            tfvars = (out_dir / "terraform/terraform.tfvars.example").read_text()
            self.assertIn('"hot_pool" = { node_count = 1, vcpu_per_node = 4, ram_gb_per_node = 16, disk_gb = 100, full_clone = true }', tfvars)
            self.assertIn('"cold_pool" = { node_count = 1, vcpu_per_node = 4, ram_gb_per_node = 16, disk_gb = 100, full_clone = true }', tfvars)
            self.assertIn('"system_pool" = { node_count = 2, vcpu_per_node = 4, ram_gb_per_node = 8, disk_gb = 80, full_clone = true }', tfvars)

    def test_json_contract_platform_v1_is_normalized_for_addons(self) -> None:
        payload = """
        {
          "schema_version": "es-sizing-platform.v1",
          "platform": "openshift",
          "project": {"name": "OS-1"},
          "calculation": {
            "inputs": {
              "ingest_gb_per_day": 1,
              "total_retention_days": 365,
              "workload_type": "mixed"
            },
            "summary": {
              "cluster_health_score": 93,
              "total_nodes": 2,
              "total_data_nodes": 2,
              "total_vcpu_selected": 4,
              "total_ram_gb_selected": 16,
              "total_local_disk_gb_selected": 200,
              "total_snapshot_storage_gb": 200,
              "total_master_nodes": 0
            },
            "tiers": [
              {"name": "hot", "nodes": 1, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 100, "snapshot_repo_total_gb": 100},
              {"name": "cold", "nodes": 1, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 100, "snapshot_repo_total_gb": 100},
              {"name": "frozen", "nodes": 0, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 0, "snapshot_repo_total_gb": 0}
            ]
          },
          "platform_details": {
            "pools": [
              {"name": "hot_pool", "nodes": 1, "vcpu_per_node": 4, "ram_gb_per_node": 16, "disk_gb_per_node": null, "composition": {"kibana_pods": 1, "fleet_pods": 1}},
              {"name": "cold_pool", "nodes": 1, "vcpu_per_node": 4, "ram_gb_per_node": 16, "disk_gb_per_node": null, "composition": {}},
              {"name": "system_pool", "nodes": 2, "vcpu_per_node": 4, "ram_gb_per_node": 8, "disk_gb_per_node": null, "composition": {}}
            ],
            "stack_components": {"vcpu": 4, "ram_gb": 8}
          }
        }
        """
        ctx = _parse_json_contract(payload)
        self.assertEqual(ctx.get("platform_detected"), "openshift")
        self.assertEqual(ctx.get("health_score"), 93)
        self.assertEqual(ctx.get("inputs", {}).get("ingest_per_day_gb"), 1)
        self.assertEqual(ctx.get("data_nodes", {}).get("count"), 1)
        self.assertEqual(ctx.get("cold_nodes", {}).get("count"), 1)
        self.assertEqual(ctx.get("kibana", {}).get("count"), 1)
        self.assertEqual(ctx.get("fleet_server", {}).get("count"), 1)
        pools = {p["name"]: p for p in ctx.get("rke2", {}).get("pools", [])}
        self.assertEqual(pools["hot_pool"]["disk_gb_per_node"], 100)
        self.assertEqual(pools["cold_pool"]["disk_gb_per_node"], 100)

    def test_initialize_project_proxmox_tfvars_uses_platform_v1_pools(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "openshift",
            "openshift": {
                "pools": [
                    {"name": "hot_pool", "nodes": 1, "vcpu_per_node": 4, "ram_gb_per_node": 16, "disk_gb_per_node": 100},
                    {"name": "cold_pool", "nodes": 1, "vcpu_per_node": 4, "ram_gb_per_node": 16, "disk_gb_per_node": 100},
                    {"name": "system_pool", "nodes": 2, "vcpu_per_node": 4, "ram_gb_per_node": 8, "disk_gb_per_node": 80},
                ]
            },
        }
        with tempfile.TemporaryDirectory(prefix="pi-platform-pools-") as td:
            out_dir = Path(td) / "sample-project"
            initialize_project(
                project_name="sample-project",
                description="",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
            )
            tfvars = (out_dir / "terraform/terraform.tfvars.example").read_text()
            self.assertIn('"hot_pool" = { node_count = 1, vcpu_per_node = 4, ram_gb_per_node = 16, disk_gb = 100, full_clone = true }', tfvars)
            self.assertIn('"cold_pool" = { node_count = 1, vcpu_per_node = 4, ram_gb_per_node = 16, disk_gb = 100, full_clone = true }', tfvars)
            self.assertIn('"system_pool" = { node_count = 2, vcpu_per_node = 4, ram_gb_per_node = 8, disk_gb = 80, full_clone = true }', tfvars)

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
            self.assertTrue((out_dir / "scripts/cluster-healthcheck.sh").exists())
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
            healthcheck_script = (out_dir / "scripts/cluster-healthcheck.sh").read_text()
            self.assertIn("proxmox_node_pools", tfvars)
            self.assertIn("proxmox_endpoint", tfvars)
            self.assertIn("gitops_flux_path", tfvars)
            self.assertIn('"hot_pool"', tfvars)
            self.assertIn('source = "bpg/proxmox"', versions_tf)
            self.assertIn("endpoint", providers_tf)
            self.assertIn("api_token", providers_tf)
            self.assertIn('variable "proxmox_endpoint" {', variables_tf)
            self.assertIn('variable "proxmox_snippets_storage" {', variables_tf)
            self.assertIn('variable "proxmox_enable_cloud_init_growpart" {', variables_tf)
            self.assertNotIn(", default =", variables_tf)
            self.assertIn('resource "proxmox_virtual_environment_vm" "nodes"', proxmox_module_tf)
            self.assertIn('resource "proxmox_virtual_environment_file" "cloud_init_growpart"', proxmox_module_tf)
            self.assertIn("count        = var.proxmox_enable_cloud_init_growpart ? 1 : 0", proxmox_module_tf)
            self.assertIn(
                "user_data_file_id = var.proxmox_enable_cloud_init_growpart ? proxmox_virtual_environment_file.cloud_init_growpart[0].id : null",
                proxmox_module_tf,
            )
            self.assertIn("proxmox_enable_cloud_init_growpart = false", tfvars)
            self.assertNotIn('resource "local_file"', proxmox_module_tf)
            self.assertIn('scripts/bootstrap-rke2.sh', deploy_script)
            self.assertIn("terraform apply -auto-approve -parallelism=4", deploy_script)
            self.assertIn('NAMESPACE="sample-project"', healthcheck_script)
            self.assertIn('ES_NAME="sample-project"', healthcheck_script)
            self.assertNotIn('KB_NAME=', healthcheck_script)
            self.assertIn('KIBANA_INGRESS="sample-project-kibana"', healthcheck_script)
            self.assertIn('flux get kustomizations', healthcheck_script)
            self.assertIn('INVENTORY_FILE="$(cd "$(dirname "$0")/.." && pwd)/ansible/inventory.ini"', healthcheck_script)
            self.assertIn('KUBECONFIG_FILE="$HOME/.kube/sample-project"', healthcheck_script)
            self.assertFalse((out_dir / "terraform/modules/aks/main.tf").exists())
            self.assertEqual(result.get("iac_tool"), "terraform")

            mode = os.stat(out_dir / "scripts/post-terraform-deploy.sh").st_mode
            self.assertTrue(mode & 0o100)
            mode_healthcheck = os.stat(out_dir / "scripts/cluster-healthcheck.sh").st_mode
            self.assertTrue(mode_healthcheck & 0o100)
            bootstrap_playbook = (out_dir / "ansible/rke2-bootstrap.yml").read_text()
            self.assertIn("Grow root partition and filesystem on all nodes", bootstrap_playbook)
            self.assertIn('findmnt -n -o SOURCE /', bootstrap_playbook)
            self.assertIn("growpart /dev/", bootstrap_playbook)

    def test_initialize_project_proxmox_tfvars_uses_rke2_pool_resources(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "rke2",
            "rke2": {
                "pools": [
                    {"name": "hot_pool", "nodes": 1, "vcpu_per_node": 12, "ram_gb_per_node": 20, "disk_gb_per_node": 100},
                    {"name": "system_pool", "nodes": 2, "vcpu_per_node": 8, "ram_gb_per_node": 10, "disk_gb_per_node": 80},
                ]
            },
        }
        with tempfile.TemporaryDirectory(prefix="pi-proxmox-pools-") as td:
            out_dir = Path(td) / "sample-project"
            initialize_project(
                project_name="sample-project",
                description="",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
            )
            tfvars = (out_dir / "terraform/terraform.tfvars.example").read_text()
            self.assertIn('"hot_pool" = { node_count = 1, vcpu_per_node = 12, ram_gb_per_node = 20, disk_gb = 100, full_clone = true }', tfvars)
            self.assertIn('"system_pool" = { node_count = 2, vcpu_per_node = 8, ram_gb_per_node = 10, disk_gb = 80, full_clone = true }', tfvars)

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
            self.assertIn("- kustomization-agents.yaml", flux_dir_kustomization)

            gotk_sync = (out_dir / "flux-system/gotk-sync.yaml").read_text()
            self.assertIn("kind: Kustomization", gotk_sync)
            self.assertIn("wait: false", gotk_sync)
            apps_kustomization = (out_dir / "flux-system/kustomization-apps.yaml").read_text()
            self.assertIn("timeout: 20m", apps_kustomization)
            agents_kustomization = (out_dir / "flux-system/kustomization-agents.yaml").read_text()
            self.assertIn("name: gitops-check-agents", agents_kustomization)
            self.assertIn("path: ./agents", agents_kustomization)
            self.assertIn("- name: gitops-check-apps", agents_kustomization)

            cluster_kustomization = (out_dir / "clusters/management/kustomization.yaml").read_text()
            self.assertIn("- ../../flux-system", cluster_kustomization)
            self.assertNotIn("- ../../apps", cluster_kustomization)

            base_kustomization = (out_dir / "base/kustomization.yaml").read_text()
            self.assertIn("namespace: gitops-check", base_kustomization)

            infra_kustomization = (out_dir / "infrastructure/kustomization.yaml").read_text()
            self.assertIn("- namespace.yaml", infra_kustomization)
            self.assertIn("- local-path-provisioner.yaml", infra_kustomization)
            self.assertIn("- storageclasses.yaml", infra_kustomization)
            self.assertIn("- network-policy-allow-dns.yaml", infra_kustomization)
            self.assertIn("- network-policy-allow-intra-namespace.yaml", infra_kustomization)
            self.assertIn("- network-policy-allow-eck-operator.yaml", infra_kustomization)
            self.assertIn("- network-policy-allow-ingress-nginx.yaml", infra_kustomization)
            self.assertIn("- network-policy-allow-kibana-egress.yaml", infra_kustomization)

            network_policy = (out_dir / "infrastructure/network-policy.yaml").read_text()
            self.assertIn("namespace: gitops-check", network_policy)
            dns_policy = (out_dir / "infrastructure/network-policy-allow-dns.yaml").read_text()
            self.assertIn("port: 53", dns_policy)
            intra_policy = (out_dir / "infrastructure/network-policy-allow-intra-namespace.yaml").read_text()
            self.assertIn("podSelector: {}", intra_policy)
            eck_operator_policy = (out_dir / "infrastructure/network-policy-allow-eck-operator.yaml").read_text()
            self.assertIn("kubernetes.io/metadata.name: elastic-system", eck_operator_policy)
            ingress_nginx_policy = (out_dir / "infrastructure/network-policy-allow-ingress-nginx.yaml").read_text()
            self.assertIn("kubernetes.io/metadata.name: kube-system", ingress_nginx_policy)
            self.assertIn("port: 5601", ingress_nginx_policy)
            kibana_egress_policy = (out_dir / "infrastructure/network-policy-allow-kibana-egress.yaml").read_text()
            self.assertIn("common.k8s.elastic.co/type: kibana", kibana_egress_policy)
            self.assertIn("cidr: 0.0.0.0/0", kibana_egress_policy)
            self.assertIn("port: 443", kibana_egress_policy)

            app_kustomization = (out_dir / "apps/gitops-check/kustomization.yaml").read_text()
            self.assertNotIn("../../base", app_kustomization)
            self.assertNotIn("../../agents", app_kustomization)
            self.assertIn("../../elasticsearch", app_kustomization)
            self.assertIn("../../kibana", app_kustomization)

            self.assertTrue((out_dir / "platform/eck-operator/crds.yaml").exists())
            eck_kustomization = (out_dir / "platform/eck-operator/kustomization.yaml").read_text()
            self.assertIn("- crds.yaml", eck_kustomization)
            kibana_yaml = (out_dir / "kibana/kibana.yaml").read_text()
            self.assertIn("xpack.fleet.agentPolicies:", kibana_yaml)
            self.assertIn("is_default_fleet_server: true", kibana_yaml)
            self.assertIn("id: elastic-agent-policy", kibana_yaml)
            kibana_kustomization = (out_dir / "kibana/kustomization.yaml").read_text()
            self.assertIn("- ingress.yaml", kibana_kustomization)
            kibana_ingress = (out_dir / "kibana/ingress.yaml").read_text()
            self.assertIn("ingressClassName: nginx", kibana_ingress)
            self.assertIn("nginx.ingress.kubernetes.io/backend-protocol: \"HTTPS\"", kibana_ingress)
            self.assertIn("name: gitops-check-kb-http", kibana_ingress)
            agents_kustomization_file = (out_dir / "agents/kustomization.yaml").read_text()
            self.assertNotIn("app.kubernetes.io/component: agents", agents_kustomization_file)
            self.assertIn("app.kubernetes.io/managed-by: eck", agents_kustomization_file)
            elastic_agent_yaml = (out_dir / "agents/elastic-agent.yaml").read_text()
            self.assertIn("node-role.kubernetes.io/control-plane", elastic_agent_yaml)
            self.assertIn("node-role.kubernetes.io/master", elastic_agent_yaml)
            self.assertIn("CriticalAddonsOnly", elastic_agent_yaml)
            self.assertIn("path: /var/log", elastic_agent_yaml)
            self.assertIn("path: /var/lib/docker/containers", elastic_agent_yaml)
            self.assertIn("path: /proc", elastic_agent_yaml)
            self.assertIn("path: /sys/fs/cgroup", elastic_agent_yaml)
            self.assertIn("name: HOST_PROC", elastic_agent_yaml)
            self.assertIn("value: /hostfs/proc", elastic_agent_yaml)
            self.assertIn("name: HOST_SYS", elastic_agent_yaml)
            self.assertIn("value: /hostfs/sys", elastic_agent_yaml)
            self.assertIn("mountPath: /var/log", elastic_agent_yaml)
            self.assertIn("mountPath: /var/lib/docker/containers", elastic_agent_yaml)
            self.assertIn("mountPath: /hostfs/proc", elastic_agent_yaml)
            self.assertIn("mountPath: /hostfs/sys", elastic_agent_yaml)
            rbac_yaml = (out_dir / "agents/rbac.yaml").read_text()
            self.assertIn('resources: ["endpoints", "replicationcontrollers", "resourcequotas", "limitranges", "serviceaccounts"]', rbac_yaml)
            self.assertIn('resources: ["horizontalpodautoscalers"]', rbac_yaml)
            self.assertIn('resources: ["ingresses"]', rbac_yaml)
            self.assertIn('resources: ["poddisruptionbudgets"]', rbac_yaml)
            self.assertIn('resources: ["leases"]', rbac_yaml)

            deploy_script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            healthcheck_script = (out_dir / "scripts/cluster-healthcheck.sh").read_text()
            self.assertIn(
                f'git remote set-url origin "https://oauth2:{git_token}@gitlab.com/acme/platform/gitops-check.git"',
                deploy_script,
            )
            self.assertIn(f'git remote set-url origin "{repo_url}"', deploy_script)
            self.assertIn(
                'kubectl -n flux-system wait gitrepository/"$PROJECT_NAME" --for=condition=Ready --timeout=5m',
                deploy_script,
            )
            self.assertIn(
                'kubectl -n flux-system wait kustomization/"$PROJECT_NAME" --for=condition=Ready --timeout=10m',
                deploy_script,
            )
            self.assertLess(
                deploy_script.find('flux reconcile kustomization "$PROJECT_NAME-infra" -n flux-system || true'),
                deploy_script.find('flux reconcile kustomization "$PROJECT_NAME-apps" -n flux-system || true'),
            )
            self.assertIn('flux reconcile kustomization "$PROJECT_NAME-agents" -n flux-system || true', deploy_script)
            self.assertNotIn("rke2-4-apps", deploy_script)
            self.assertNotIn("rke2-4-infra", deploy_script)
            self.assertIn('NAMESPACE="gitops-check"', healthcheck_script)
            self.assertNotIn('NAMESPACE="rke2-4"', healthcheck_script)

    def test_argo_post_terraform_script_keeps_flux_logic_out(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-argo-post-tf-") as td:
            out_dir = Path(td) / "argo-check"
            initialize_project(
                project_name="argo-check",
                description="Argo deployment behavior check",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="argo",
                iac_tool="terraform",
            )
            deploy_script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            self.assertNotIn('flux reconcile kustomization "$PROJECT_NAME-infra"', deploy_script)
            self.assertNotIn('flux reconcile kustomization "$PROJECT_NAME-apps"', deploy_script)
            self.assertNotIn("kubectl -n flux-system wait gitrepository", deploy_script)
            self.assertIn('argocd app sync "$PROJECT_NAME" || true', deploy_script)
            self.assertTrue((out_dir / "scripts/cluster-healthcheck.sh").exists())

    def test_healthcheck_script_generated_without_terraform_when_sizing_present(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "rke2",
            "rke2": {"pools": [{"name": "system_pool", "nodes": 1}]},
        }
        with tempfile.TemporaryDirectory(prefix="pi-healthcheck-no-tf-") as td:
            out_dir = Path(td) / "no-tf-healthcheck"
            initialize_project(
                project_name="no-tf-healthcheck",
                description="Elasticsearch sizing flow without terraform",
                target_directory=str(out_dir),
                platform="rke2",
                sizing_context=sizing_context,
            )
            healthcheck = out_dir / "scripts/cluster-healthcheck.sh"
            self.assertTrue(healthcheck.exists())
            content = healthcheck.read_text()
            self.assertIn('NAMESPACE="no-tf-healthcheck"', content)
            self.assertIn('ES_NAME="no-tf-healthcheck"', content)

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

    def test_eck_nodesets_support_tier_node_selectors(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "rke2",
            "data_nodes": {
                "count": 2,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "100Gi",
                "storage_class": "standard",
                "node_selector": {"node-role.kubernetes.io/hot": "true"},
            },
            "cold_nodes": {
                "count": 1,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "200Gi",
                "storage_class": "standard",
                "node_selector": {"node-role.kubernetes.io/cold": "true"},
            },
            "frozen_nodes": {
                "count": 1,
                "memory": "16Gi",
                "cpu": "4",
                "cache_storage": "200Gi",
                "node_selector": {"node-role.kubernetes.io/frozen": "true"},
            },
        }
        with tempfile.TemporaryDirectory(prefix="pi-eck-node-selector-") as td:
            out_dir = Path(td) / "node-selector-check"
            initialize_project(
                project_name="node-selector-check",
                description="Elasticsearch node selector routing check",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
            )
            es_cluster = (out_dir / "elasticsearch/cluster.yaml").read_text()
            self.assertIn('nodeSelector:', es_cluster)
            self.assertIn('"node-role.kubernetes.io/hot": "true"', es_cluster)
            self.assertIn('"node-role.kubernetes.io/cold": "true"', es_cluster)
            self.assertIn('"node-role.kubernetes.io/frozen": "true"', es_cluster)

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

    def test_eck_storage_class_aliases_normalize(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "rke2",
            "data_nodes": {
                "count": 2,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "100Gi",
                "storage_class": "Managed-Premium",
            },
            "cold_nodes": {
                "count": 1,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "200Gi",
                "storage_class": "Local_Path",
            },
        }
        with tempfile.TemporaryDirectory(prefix="pi-eck-storage-aliases-") as td:
            out_dir = Path(td) / "storage-aliases"
            initialize_project(
                project_name="storage-aliases",
                description="Elasticsearch storage aliases normalization",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                fallback_storage_class="STANDARD_RWO",
                sizing_context=sizing_context,
            )
            es_cluster = (out_dir / "elasticsearch/cluster.yaml").read_text()
            # managed-premium remaps to premium, then proxmox premium remaps to fallback.
            self.assertIn("storageClassName: standard", es_cluster)
            self.assertIn("storageClassName: local-path", es_cluster)
            self.assertNotIn("storageClassName: Managed-Premium", es_cluster)
            self.assertNotIn("storageClassName: Local_Path", es_cluster)

    def test_eck_premium_remaps_to_fallback_on_proxmox(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "rke2",
            "data_nodes": {
                "count": 2,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "100Gi",
                "storage_class": "premium",
            },
            "cold_nodes": {
                "count": 1,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "200Gi",
                "storage_class": "premium",
            },
        }
        with tempfile.TemporaryDirectory(prefix="pi-eck-premium-remap-") as td:
            out_dir = Path(td) / "premium-remap"
            initialize_project(
                project_name="premium-remap",
                description="Elasticsearch premium remap check",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                fallback_storage_class="standard",
                sizing_context=sizing_context,
            )
            es_cluster = (out_dir / "elasticsearch/cluster.yaml").read_text()
            self.assertNotIn("storageClassName: premium", es_cluster)
            self.assertIn("storageClassName: standard", es_cluster)

    def test_eck_master_nodeset_has_minimum_pvc(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "rke2",
            "master_nodes": {
                "count": 3,
                "memory": "2Gi",
                "cpu": "1",
                "storage": "0Gi",
                "storage_class": "Standard_RWO",
            },
            "data_nodes": {
                "count": 1,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "50Gi",
                "storage_class": "standard",
            },
        }
        with tempfile.TemporaryDirectory(prefix="pi-eck-master-pvc-") as td:
            out_dir = Path(td) / "master-pvc"
            initialize_project(
                project_name="master-pvc",
                description="Master PVC defaults",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
            )
            es_cluster = (out_dir / "elasticsearch/cluster.yaml").read_text()
            self.assertIn("- name: master", es_cluster)
            self.assertIn("storage: 1Gi", es_cluster)
            self.assertIn("storageClassName: standard", es_cluster)

    def test_rke2_bootstrap_handles_os_family_conventions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-rke2-os-family-") as td:
            out_dir = Path(td) / "rke2-os-family"
            initialize_project(
                project_name="rke2-os-family",
                description="RKE2 os family handling check",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            bootstrap_playbook = (out_dir / "ansible/rke2-bootstrap.yml").read_text()
            self.assertIn('(ansible_os_family | lower) == "debian"', bootstrap_playbook)
            self.assertIn('(ansible_os_family | lower) == "redhat"', bootstrap_playbook)
            self.assertIn("name: xfsprogs", bootstrap_playbook)


    def test_otel_metrics_exported_to_elasticsearch(self) -> None:
        """Verify metrics pipeline has elasticsearch exporter."""
        with tempfile.TemporaryDirectory(prefix="pi-otel-metrics-es-") as td:
            out_dir = Path(td) / "otel-metrics-check"
            initialize_project(
                project_name="otel-metrics-check",
                description="OTEL metrics export check",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
                enable_otel_collector=True,
            )
            configmap = (out_dir / "observability/otel-collector/configmap.yaml").read_text()
            # Metrics pipeline must export to elasticsearch
            self.assertIn("exporters: [elasticsearch, debug]", configmap)
            # Should not have the old comment about ES exporter not supporting metrics
            self.assertNotIn("ES exporter does not support metrics", configmap)
            # ECS mapping mode should be present
            self.assertIn("mode: ecs", configmap)

    def test_otel_collector_version_configurable(self) -> None:
        """Pass custom OTEL version, verify image tag."""
        from addons.observability_stack import ObservabilityStackGenerator

        gen = ObservabilityStackGenerator(
            "version-test", "test", {"otel_collector_version": "0.120.0", "primary_category": "elasticsearch", "enable_otel_collector": True}
        )
        files = gen.generate()
        daemonset = files.get("observability/otel-collector/daemonset.yaml", "")
        self.assertIn("otel/opentelemetry-collector-contrib:0.120.0", daemonset)
        self.assertNotIn("0.96.0", daemonset)

    def test_eck_3x_no_fleet_enroll_env(self) -> None:
        """Verify FLEET_ENROLL absent with ECK 3.x."""
        with tempfile.TemporaryDirectory(prefix="pi-eck3-no-enroll-") as td:
            out_dir = Path(td) / "eck3-check"
            initialize_project(
                project_name="eck3-check",
                description="ECK 3.x enrollment check",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            agent_yaml = (out_dir / "agents/elastic-agent.yaml").read_text()
            self.assertNotIn("FLEET_ENROLL", agent_yaml)
            self.assertIn("kibanaRef:", agent_yaml)

    def test_eck_2x_backward_compat_fleet_enroll(self) -> None:
        """Verify FLEET_ENROLL present with ECK 2.x override."""
        sizing_context = {
            "source": "sizing_report",
            "platform_detected": "rke2",
            "eck_operator": {"version": "2.16.0"},
            "rke2": {"pools": [{"name": "system_pool", "nodes": 1}]},
        }
        with tempfile.TemporaryDirectory(prefix="pi-eck2-enroll-") as td:
            out_dir = Path(td) / "eck2-check"
            initialize_project(
                project_name="eck2-check",
                description="ECK 2.x backward compat check",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
            )
            agent_yaml = (out_dir / "agents/elastic-agent.yaml").read_text()
            self.assertIn("FLEET_ENROLL", agent_yaml)
            self.assertNotIn("kibanaRef:", agent_yaml)

    def test_post_deploy_no_enrollment_patch_eck3(self) -> None:
        """Verify step 9 simplified for ECK 3.x."""
        with tempfile.TemporaryDirectory(prefix="pi-eck3-deploy-") as td:
            out_dir = Path(td) / "eck3-deploy"
            initialize_project(
                project_name="eck3-deploy",
                description="ECK 3.x deploy check",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            deploy_script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            self.assertIn("Waiting for agent auto-enrollment (ECK 3.x)", deploy_script)
            self.assertNotIn("ENROLLMENT_TOKEN", deploy_script)
            self.assertNotIn("kubectl set env daemonset", deploy_script)

    def test_otel_dashboard_ndjson_generated(self) -> None:
        """Verify dashboard ndjson file present in output with Lens format."""
        with tempfile.TemporaryDirectory(prefix="pi-otel-dashboard-") as td:
            out_dir = Path(td) / "dashboard-check"
            initialize_project(
                project_name="dashboard-check",
                description="Elasticsearch observability platform",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
                enable_otel_collector=True,
            )
            dashboard_path = out_dir / "observability/otel-dashboards/otel-infrastructure-overview.ndjson"
            self.assertTrue(dashboard_path.exists())
            content = dashboard_path.read_text()
            self.assertIn("OTEL Infrastructure Overview", content)
            self.assertIn("metrics-generic-*", content)
            self.assertIn("otel-vis-cpu-by-node", content)
            # Must use Lens format, not legacy visualization
            self.assertIn('"type": "lens"', content)
            self.assertNotIn('"type": "visualization"', content)
            self.assertIn('"visualizationType": "lnsXY"', content)
            self.assertIn('"visualizationType": "lnsMetric"', content)

    def test_otel_collector_has_credential_init_container(self) -> None:
        """Verify collector waits for ES credentials before starting."""
        with tempfile.TemporaryDirectory(prefix="pi-otel-init-") as td:
            out_dir = Path(td) / "init-check"
            initialize_project(
                project_name="init-check",
                description="Elasticsearch observability platform",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
                enable_otel_collector=True,
            )
            daemonset = (out_dir / "observability/otel-collector/daemonset.yaml").read_text()
            self.assertIn("wait-for-es-credentials", daemonset)
            self.assertIn("initContainers:", daemonset)
            self.assertIn('while [ -z "$ES_PASSWORD" ]', daemonset)

    def test_otel_secret_has_prune_and_reconcile_disabled(self) -> None:
        """Verify otel-es-credentials has both prune: disabled and reconcile: disabled.

        prune: disabled prevents Flux from deleting the secret if removed from git.
        reconcile: disabled prevents Flux from overwriting the data fields via SSA
        (kustomize-controller owns them) on every reconcile cycle, which would wipe
        real credentials populated by post-terraform-deploy.sh.
        The secret already exists in-cluster when Flux processes the annotation, so
        first-time creation is unaffected.
        """
        with tempfile.TemporaryDirectory(prefix="pi-otel-secret-reconcile-") as td:
            out_dir = Path(td) / "secret-reconcile-check"
            initialize_project(
                project_name="secret-reconcile-check",
                description="Elasticsearch observability platform",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
                enable_otel_collector=True,
            )
            secret_yaml = (out_dir / "observability/otel-collector/es-secret.yaml").read_text()
            self.assertIn("kustomize.toolkit.fluxcd.io/prune: disabled", secret_yaml)
            self.assertIn("kustomize.toolkit.fluxcd.io/reconcile: disabled", secret_yaml)


if __name__ == "__main__":
    unittest.main()
