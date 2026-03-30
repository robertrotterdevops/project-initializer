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
            self.assertTrue((out_dir / "platform/DELIVERY_BLUEPRINT.md").exists())
            self.assertTrue((out_dir / "sizing/config.json").exists())
            tfvars = (out_dir / "terraform/terraform.tfvars.example").read_text()
            versions_tf = (out_dir / "terraform/versions.tf").read_text()
            providers_tf = (out_dir / "terraform/providers.tf").read_text()
            variables_tf = (out_dir / "terraform/variables.tf").read_text()
            proxmox_module_tf = (out_dir / "terraform/modules/proxmox_cluster/main.tf").read_text()
            deploy_script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            healthcheck_script = (out_dir / "scripts/cluster-healthcheck.sh").read_text()
            delivery_blueprint = (out_dir / "platform/DELIVERY_BLUEPRINT.md").read_text()
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
            self.assertIn("Rancher-governed RKE2", delivery_blueprint)
            self.assertIn("Azure AKS", delivery_blueprint)
            self.assertIn('NAMESPACE="sample-project"', healthcheck_script)
            self.assertIn('ES_NAME="sample-project"', healthcheck_script)
            self.assertNotIn('KB_NAME=', healthcheck_script)
            self.assertIn('KIBANA_INGRESS="sample-project-kibana"', healthcheck_script)
            self.assertIn('flux get kustomizations', healthcheck_script)
            self.assertIn('ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"', healthcheck_script)
            self.assertIn('INVENTORY_FILE="$ROOT_DIR/ansible/inventory.ini"', healthcheck_script)
            self.assertIn('PROJECT_KUBECONFIG="${PI_ARG_KUBECONFIG_PATH:-$ROOT_DIR/.kube/sample-project}"', healthcheck_script)
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
            self.assertIn('"elasticsearch.k8s.elastic.co/tier=master"', bootstrap_playbook)
            self.assertIn('"elasticsearch.k8s.elastic.co/tier=system"', bootstrap_playbook)

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
            self.assertIn('argocd app sync "$PROJECT_NAME-root" || true', deploy_script)

            healthcheck_script = (out_dir / "scripts/cluster-healthcheck.sh").read_text()
            self.assertIn('GITOPS_TOOL="argo"', healthcheck_script)
            self.assertIn('if [[ "${GITOPS_TOOL}" == "argo" ]]; then', healthcheck_script)
            self.assertIn('sep "ARGOCD"', healthcheck_script)
            self.assertIn('sep "ARGOCD APPLICATIONS"', healthcheck_script)
            self.assertIn('kubectl -n argocd get applications.argoproj.io', healthcheck_script)

            bootstrap_argocd = (out_dir / "scripts/bootstrap-argocd.sh").read_text()
            affinity_patch = (out_dir / "argocd/patches/system-pool-affinity.yaml").read_text()
            self.assertIn("kubectl apply --server-side -n argocd -f", bootstrap_argocd)
            self.assertIn('AFFINITY_PATCH="$ROOT_DIR/argocd/patches/system-pool-affinity.yaml"', bootstrap_argocd)
            self.assertIn("argocd.argoproj.io/secret-type: repository", bootstrap_argocd)
            self.assertIn("type: git", bootstrap_argocd)
            self.assertIn("kubectl apply -k \"$ROOT_DIR/argocd\"", bootstrap_argocd)
            self.assertIn("name: argocd-redis", affinity_patch)
            self.assertIn("name: argocd-application-controller", affinity_patch)

    def test_argo_generation_excludes_flux_scaffold(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-argo-no-flux-") as td:
            out_dir = Path(td) / "argo-no-flux"
            initialize_project(
                project_name="argo-no-flux",
                description="Argo isolated generation",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="argo",
                iac_tool="terraform",
                sizing_context={
                    "source": "sizing_report",
                    "eck_operator": {"version": "3.0.0"},
                },
            )
            self.assertFalse((out_dir / "flux-system").exists())
            self.assertFalse((out_dir / "scripts/bootstrap-flux.sh").exists())
            self.assertTrue((out_dir / "scripts/bootstrap-argocd.sh").exists())
            self.assertTrue((out_dir / "scripts/mirror-secrets.sh").exists())
            self.assertTrue((out_dir / "scripts/import-dashboards.sh").exists())
            self.assertTrue((out_dir / "scripts/preflight-check.sh").exists())

    def test_argo_component_app_paths_and_ingress_host(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-argo-paths-") as td:
            out_dir = Path(td) / "argo-paths"
            initialize_project(
                project_name="argo-paths",
                description="Argo app path check",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="argo",
                iac_tool="terraform",
                sizing_context={
                    "source": "sizing_report",
                    "eck_operator": {"version": "3.0.0"},
                },
            )
            es_app = (out_dir / "argocd/apps/components/elasticsearch.yaml").read_text()
            kb_app = (out_dir / "argocd/apps/components/kibana.yaml").read_text()
            infra_app = (out_dir / "argocd/apps/components/infrastructure.yaml").read_text()
            ingress = (out_dir / "argocd/ingress.yaml").read_text()
            self.assertIn("path: elasticsearch", es_app)
            self.assertIn("path: kibana", kb_app)
            self.assertIn("path: infrastructure", infra_app)
            self.assertIn("host: argocd.argo-paths.lan", ingress)


    def test_argo_includes_observability_application_when_otel_enabled(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-argo-otel-") as td:
            out_dir = Path(td) / "argo-otel"
            initialize_project(
                project_name="argo-otel",
                description="Argo with OTEL collector",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="argo",
                iac_tool="terraform",
                enable_otel_collector=True,
                sizing_context={
                    "source": "sizing_report",
                    "eck_operator": {"version": "3.0.0"},
                },
            )
            self.assertTrue((out_dir / "observability/kustomization.yaml").exists())
            app_yaml = (out_dir / "argocd/apps/components/observability.yaml").read_text()
            self.assertIn("path: observability", app_yaml)
            self.assertIn('argocd.argoproj.io/sync-wave: "4"', app_yaml)

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

    def test_aks_eck_defaults_hot_to_premium_and_cold_to_standard_storage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-aks-storage-defaults-") as td:
            out_dir = Path(td) / "aks-storage-defaults"
            initialize_project(
                project_name="aks-storage-defaults",
                description="AKS Elasticsearch deployment",
                target_directory=str(out_dir),
                platform="aks",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context={
                    "source": "sizing_report",
                    "data_nodes": {"count": 1, "memory": "8Gi", "cpu": "2", "storage": "100Gi"},
                    "cold_nodes": {"count": 1, "memory": "8Gi", "cpu": "2", "storage": "200Gi"},
                    "frozen_nodes": {"count": 1, "memory": "8Gi", "cpu": "2", "cache_storage": "300Gi"},
                    "eck_operator": {"version": "3.0.0"},
                },
            )
            es_cluster = (out_dir / "elasticsearch/cluster.yaml").read_text()
            self.assertIn("storageClassName: premium", es_cluster)
            self.assertIn("storageClassName: standard", es_cluster)

    def test_openshift_eck_defaults_to_standard_storage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-ocp-storage-defaults-") as td:
            out_dir = Path(td) / "ocp-storage-defaults"
            initialize_project(
                project_name="ocp-storage-defaults",
                description="OpenShift Elasticsearch deployment",
                target_directory=str(out_dir),
                platform="openshift",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context={
                    "source": "sizing_report",
                    "data_nodes": {"count": 1, "memory": "8Gi", "cpu": "2", "storage": "100Gi"},
                    "cold_nodes": {"count": 1, "memory": "8Gi", "cpu": "2", "storage": "200Gi"},
                    "eck_operator": {"version": "3.0.0"},
                },
            )
            es_cluster = (out_dir / "elasticsearch/cluster.yaml").read_text()
            self.assertNotIn("storageClassName: premium", es_cluster)
            self.assertIn("storageClassName: standard", es_cluster)

    def test_observability_rollout_doc_emits_platform_warning(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-otel-rollout-ocp-") as td:
            out_dir = Path(td) / "otel-rollout-ocp"
            initialize_project(
                project_name="otel-rollout-ocp",
                description="OpenShift observability deployment",
                target_directory=str(out_dir),
                platform="openshift",
                gitops_tool="flux",
                iac_tool="terraform",
                enable_otel_collector=True,
            )
            rollout = (out_dir / "docs/OBSERVABILITY_ROLLOUT.md").read_text()
            self.assertIn("OpenShift may reject hostPath-based collectors", rollout)
            self.assertIn("Validate Elasticsearch credentials mirroring", rollout)

    def test_openshift_uses_platform_route_instead_of_inline_kibana_ingress(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-ocp-kibana-exposure-") as td:
            out_dir = Path(td) / "ocp-exposure"
            initialize_project(
                project_name="ocp-exposure",
                description="OpenShift Elasticsearch deployment",
                target_directory=str(out_dir),
                platform="openshift",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context={"source": "sizing_report", "eck_operator": {"version": "3.0.0"}},
            )
            kibana_kustomization = (out_dir / "kibana/kustomization.yaml").read_text()
            route_yaml = (out_dir / "platform/openshift/route.yaml").read_text()
            self.assertNotIn("- ingress.yaml", kibana_kustomization)
            self.assertFalse((out_dir / "kibana/ingress.yaml").exists())
            self.assertIn("kind: Route", route_yaml)
            self.assertIn("name: ocp-exposure-kibana", route_yaml)

    def test_aks_uses_platform_ingress_instead_of_inline_kibana_ingress(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-aks-kibana-exposure-") as td:
            out_dir = Path(td) / "aks-exposure"
            initialize_project(
                project_name="aks-exposure",
                description="AKS Elasticsearch deployment",
                target_directory=str(out_dir),
                platform="aks",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context={"source": "sizing_report", "eck_operator": {"version": "3.0.0"}},
            )
            kibana_kustomization = (out_dir / "kibana/kustomization.yaml").read_text()
            aks_ingress = (out_dir / "platform/aks/ingress.yaml").read_text()
            self.assertNotIn("- ingress.yaml", kibana_kustomization)
            self.assertFalse((out_dir / "kibana/ingress.yaml").exists())
            self.assertIn("azure/application-gateway", aks_ingress)

    def test_healthcheck_script_for_managed_platforms_does_not_fetch_rke2_kubeconfig(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-healthcheck-aks-") as td:
            out_dir = Path(td) / "aks-healthcheck"
            initialize_project(
                project_name="aks-healthcheck",
                description="Managed AKS Elasticsearch deployment",
                target_directory=str(out_dir),
                platform="aks",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            healthcheck = (out_dir / "scripts/cluster-healthcheck.sh").read_text()
            self.assertNotIn("/etc/rancher/rke2/rke2.yaml", healthcheck)
            self.assertIn("For managed or externally delivered clusters", healthcheck)
            self.assertIn("kubectl get route", healthcheck)

    def test_fleet_server_uses_sizing_count_and_infra_selector(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-fleet-sizing-") as td:
            out_dir = Path(td) / "fleet-sizing"
            initialize_project(
                project_name="fleet-sizing",
                description="Elasticsearch on proxmox RKE2",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context={
                    "source": "sizing_report",
                    "fleet_server": {"count": 2, "memory": "4Gi", "cpu": "2", "node_selector": {"node-role.kubernetes.io/system": "true"}},
                    "eck_operator": {"version": "3.0.0"},
                },
            )
            fleet_server = (out_dir / "agents/fleet-server.yaml").read_text()
            self.assertIn("replicas: 2", fleet_server)
            self.assertIn('"node-role.kubernetes.io/system": "true"', fleet_server)

    def test_scaffold_defaults_kibana_and_fleet_to_system_tier(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-rke2-tier-fallback-") as td:
            out_dir = Path(td) / "rke2-tier-fallback"
            initialize_project(
                project_name="rke2-tier-fallback",
                description="Elasticsearch on RKE2 with hot and cold tiers",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context={
                    "source": "sizing_report",
                    "master_nodes": {"count": 3, "memory": "4Gi", "cpu": "2"},
                    "data_nodes": {"count": 1, "memory": "8Gi", "cpu": "2", "storage": "100Gi"},
                    "cold_nodes": {"count": 1, "memory": "8Gi", "cpu": "2", "storage": "100Gi"},
                    "kibana": {"count": 1, "memory": "4Gi", "cpu": "2"},
                    "fleet_server": {"count": 1, "memory": "4Gi", "cpu": "2"},
                    "eck_operator": {"version": "3.0.0"},
                },
            )
            kibana = (out_dir / "kibana/kibana.yaml").read_text()
            fleet_server = (out_dir / "agents/fleet-server.yaml").read_text()
            self.assertIn('"elasticsearch.k8s.elastic.co/tier": "system"', kibana)
            self.assertIn('"elasticsearch.k8s.elastic.co/tier": "system"', fleet_server)
            self.assertNotIn('"elasticsearch.k8s.elastic.co/tier": "infra"', kibana)
            self.assertNotIn('"elasticsearch.k8s.elastic.co/tier": "infra"', fleet_server)
            self.assertIn('cpu: "2"', fleet_server)
            self.assertNotIn('requests:\n                memory: "4Gi"\n                cpu: "2"\n              limits:\n                memory: "4Gi"\n                cpu: "1"', fleet_server)

    def test_observability_skips_metrics_server_for_proxmox_rke2_delivery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-otel-proxmox-") as td:
            out_dir = Path(td) / "otel-proxmox"
            initialize_project(
                project_name="otel-proxmox",
                description="Elasticsearch observability platform",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                enable_otel_collector=True,
            )
            self.assertFalse((out_dir / "platform/metrics-server").exists())
            otel_readme = (out_dir / "observability/otel-collector/README.md").read_text()
            self.assertIn("Proxmox-backed RKE2 delivery", otel_readme)

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


class TestPipelineStepNumbering(unittest.TestCase):
    """Tests that post-terraform-deploy.sh has sequential, non-duplicate step numbers."""

    import re as _re  # avoid polluting module-level namespace

    def _parse_steps(self, script: str):
        """Return list of (step_num, total) tuples found in [N/M] markers.

        Deduplicates by step number: the header emits both branches of an if/else
        (e.g. '[2/N] Running RKE2 bootstrap...' and '[2/N] No RKE2 bootstrap
        script found'), which both carry step 2. Only one branch ever executes,
        so we keep the lowest-numbered occurrence per step number.
        """
        import re
        seen: dict = {}
        for n_str, m_str in re.findall(r'\[(\d+)/(\d+)\]', script):
            n, m = int(n_str), int(m_str)
            if n not in seen:
                seen[n] = (n, m)
        return list(seen.values())

    def test_flux_script_no_duplicate_step_numbers(self) -> None:
        """No step number should appear twice in a flux post-terraform-deploy.sh."""
        with tempfile.TemporaryDirectory(prefix="pi-step-flux-") as td:
            out_dir = Path(td) / "step-flux"
            initialize_project(
                project_name="step-flux",
                description="",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            steps = self._parse_steps(script)
            step_nums = [n for n, _ in steps]
            self.assertGreater(len(step_nums), 0, "No [N/M] markers found in script")
            self.assertEqual(
                len(step_nums), len(set(step_nums)),
                f"Duplicate step numbers in flux deploy script: {step_nums}",
            )

    def test_flux_script_consistent_step_denominator(self) -> None:
        """All [N/M] markers in a flux script must share denominator 9."""
        with tempfile.TemporaryDirectory(prefix="pi-step-flux-denom-") as td:
            out_dir = Path(td) / "denom-flux"
            initialize_project(
                project_name="denom-flux",
                description="",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            steps = self._parse_steps(script)
            denominators = list({m for _, m in steps})
            self.assertEqual(len(denominators), 1, f"Inconsistent denominators: {denominators}")
            self.assertEqual(denominators[0], 9, f"Expected 9 total steps for flux, got {denominators[0]}")

    def test_flux_script_steps_are_sequential(self) -> None:
        """Step numbers must form a gap-free sequence starting at 1."""
        with tempfile.TemporaryDirectory(prefix="pi-step-flux-seq-") as td:
            out_dir = Path(td) / "seq-flux"
            initialize_project(
                project_name="seq-flux",
                description="",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            steps = self._parse_steps(script)
            step_nums = sorted(n for n, _ in steps)
            expected = list(range(1, len(step_nums) + 1))
            self.assertEqual(step_nums, expected, f"Steps not sequential: {step_nums}")

    def test_argo_script_no_duplicate_step_numbers(self) -> None:
        """No step number should appear twice in an argo post-terraform-deploy.sh."""
        with tempfile.TemporaryDirectory(prefix="pi-step-argo-") as td:
            out_dir = Path(td) / "step-argo"
            initialize_project(
                project_name="step-argo",
                description="Argo deployment",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="argo",
                iac_tool="terraform",
            )
            script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            steps = self._parse_steps(script)
            step_nums = [n for n, _ in steps]
            self.assertGreater(len(step_nums), 0, "No [N/M] markers found in argo script")
            self.assertEqual(
                len(step_nums), len(set(step_nums)),
                f"Duplicate step numbers in argo deploy script: {step_nums}",
            )

    def test_argo_script_consistent_step_denominator(self) -> None:
        """All [N/M] markers in an argo script must share denominator 9."""
        with tempfile.TemporaryDirectory(prefix="pi-step-argo-denom-") as td:
            out_dir = Path(td) / "denom-argo"
            initialize_project(
                project_name="denom-argo",
                description="Argo deployment",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="argo",
                iac_tool="terraform",
            )
            script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            steps = self._parse_steps(script)
            denominators = list({m for _, m in steps})
            self.assertEqual(len(denominators), 1, f"Inconsistent denominators in argo script: {denominators}")
            self.assertEqual(denominators[0], 9, f"Expected 9 total steps for argo, got {denominators[0]}")

    def test_no_gitops_script_consistent_step_denominator(self) -> None:
        """No-gitops script must use denominator 4 (terraform, bootstrap, kubeconfig, git-push)."""
        with tempfile.TemporaryDirectory(prefix="pi-step-no-gitops-") as td:
            out_dir = Path(td) / "no-gitops"
            initialize_project(
                project_name="no-gitops",
                description="",
                target_directory=str(out_dir),
                platform="rke2",
                iac_tool="terraform",
            )
            script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            steps = self._parse_steps(script)
            if steps:
                denominators = list({m for _, m in steps})
                self.assertEqual(len(denominators), 1, f"Inconsistent denominators: {denominators}")
                self.assertEqual(denominators[0], 4, f"Expected 4 total steps for no-gitops, got {denominators[0]}")

    def test_git_push_is_step_4_not_step_3(self) -> None:
        """Git push must be labelled step 4, not the conflicting step 3."""
        with tempfile.TemporaryDirectory(prefix="pi-step-gitpush-") as td:
            out_dir = Path(td) / "gitpush-check"
            initialize_project(
                project_name="gitpush-check",
                description="",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            script = (out_dir / "scripts/post-terraform-deploy.sh").read_text()
            # Git push line must be step 4
            self.assertIn("[4/9] Updating Git repository", script)
            # Old duplicate step 3 for git push must be gone
            self.assertNotIn("[3/7] Updating Git repository", script)

    def test_eck_healthcheck_uses_kubeconfig_library_not_sshpass(self) -> None:
        """ECK-generated cluster-healthcheck.sh must use kubeconfig.sh, not inline sshpass."""
        with tempfile.TemporaryDirectory(prefix="pi-eck-kube-lib-") as td:
            out_dir = Path(td) / "eck-kube"
            initialize_project(
                project_name="eck-kube",
                description="Elasticsearch on RKE2",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                # No iac_tool: ECK healthcheck is the final version (no terraform override)
            )
            healthcheck = (out_dir / "scripts/cluster-healthcheck.sh").read_text()
            self.assertNotIn("sshpass", healthcheck)
            self.assertNotIn("KUBECONFIG_FILE", healthcheck)
            self.assertIn("kubeconfig.sh", healthcheck)
            self.assertIn("pi_prepare_kubeconfig", healthcheck)
            self.assertIn("PROJECT_KUBECONFIG", healthcheck)
            self.assertIn("ROOT_DIR", healthcheck)
            self.assertIn('PLATFORM="rke2"', healthcheck)

    def test_eck_healthcheck_has_root_dir_and_platform(self) -> None:
        """ECK healthcheck must define ROOT_DIR, PLATFORM, and PROJECT_KUBECONFIG variables."""
        with tempfile.TemporaryDirectory(prefix="pi-eck-vars-") as td:
            out_dir = Path(td) / "eck-vars"
            initialize_project(
                project_name="eck-vars",
                description="Elasticsearch on RKE2",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
            )
            healthcheck = (out_dir / "scripts/cluster-healthcheck.sh").read_text()
            self.assertIn('ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"', healthcheck)
            self.assertIn('INVENTORY_FILE="$ROOT_DIR/ansible/inventory.ini"', healthcheck)
            self.assertIn('PROJECT_KUBECONFIG="${PI_ARG_KUBECONFIG_PATH:-$ROOT_DIR/.kube/eck-vars}"', healthcheck)

    def test_rke2_ansible_playbook_kubeconfig_fetch_play(self) -> None:
        """Ansible playbook must include the kubeconfig-fetch play that Ansible writes to ~/.kube/config."""
        with tempfile.TemporaryDirectory(prefix="pi-rke2-kube-play-") as td:
            out_dir = Path(td) / "kube-play"
            initialize_project(
                project_name="kube-play",
                description="",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            playbook = (out_dir / "ansible/rke2-bootstrap.yml").read_text()
            self.assertIn("Fetch kubeconfig to local machine", playbook)
            self.assertIn("Fetch kubeconfig from server node", playbook)
            self.assertIn("/etc/rancher/rke2/rke2.yaml", playbook)
            # Regexp rewriting 127.0.0.1 → actual server IP
            self.assertIn(r"127\.0\.0\.1", playbook)
            # Installs to standard location picked up by kubectl/flux automatically
            self.assertIn("~/.kube/config", playbook)
            self.assertIn("delegate_to: localhost", playbook)
            self.assertIn("Install kubeconfig to ~/.kube/config", playbook)
            # become: true required — rke2.yaml is root-owned (config dir mode 0700)
            fetch_play_start = playbook.find("- name: Fetch kubeconfig to local machine")
            next_play_start = playbook.find("\n- name:", fetch_play_start + 1)
            fetch_play_block = playbook[fetch_play_start:next_play_start if next_play_start != -1 else None]
            self.assertIn("become: true", fetch_play_block, \
                "Fetch kubeconfig play must have become: true — rke2.yaml is root-owned")

    def test_rke2_ansible_no_bare_escape_in_regexp(self) -> None:
        """The regexp in the kubeconfig-fetch play must use escaped dots (no Python SyntaxWarning)."""
        with tempfile.TemporaryDirectory(prefix="pi-rke2-regexp-") as td:
            out_dir = Path(td) / "regexp-check"
            initialize_project(
                project_name="regexp-check",
                description="",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
            )
            playbook = (out_dir / "ansible/rke2-bootstrap.yml").read_text()
            # File must have \.  (escaped dot) not bare \. which would be a linting error
            self.assertIn(r"127\.0\.0\.1", playbook)
            # Sanity: the unescaped variant must NOT appear
            import re
            bare_unescaped = re.search(r"regexp: '127\.[^\\]", playbook)
            self.assertIsNone(bare_unescaped, "Found bare unescaped dot in regexp field")


if __name__ == "__main__":
    unittest.main()
