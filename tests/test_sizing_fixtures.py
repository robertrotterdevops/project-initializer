#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_structure import initialize_project
from scripts.sizing_parser import parse_sizing_file, parse_sizing_file_detailed


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sizing"


class TestSizingFixtures(unittest.TestCase):
    def fixture(self, name: str) -> Path:
        return FIXTURES_DIR / name

    def test_rke2_fixture_parses_to_canonical_preview(self) -> None:
        result = parse_sizing_file_detailed(str(self.fixture("rke2-v1.json")))
        self.assertIsNone(result.fatal_error)
        self.assertIsNotNone(result.model)
        self.assertEqual(result.model.schema_version, "es-sizing-rke2.v1")
        self.assertEqual(result.model.platform_detected, "rke2")
        self.assertEqual(result.model.components["kibana"]["count"], 1)
        self.assertEqual(result.model.components["fleet_server"]["count"], 1)
        pools = {pool["name"]: pool for pool in result.model.pools}
        self.assertEqual(pools["hot_pool"]["disk_gb_per_node"], 100)
        self.assertEqual(pools["cold_pool"]["disk_gb_per_node"], 100)

    def test_platform_fixture_parses_to_canonical_preview(self) -> None:
        result = parse_sizing_file_detailed(str(self.fixture("platform-v1-openshift.json")))
        self.assertIsNone(result.fatal_error)
        self.assertIsNotNone(result.model)
        self.assertEqual(result.model.schema_version, "es-sizing-platform.v1")
        self.assertEqual(result.model.platform_detected, "openshift")
        self.assertEqual(result.model.components["kibana"]["count"], 1)
        self.assertEqual(result.model.components["fleet_server"]["count"], 1)
        pools = {pool["name"]: pool for pool in result.model.pools}
        self.assertEqual(pools["hot_pool"]["disk_gb_per_node"], 100)
        self.assertEqual(pools["system_pool"]["ram_gb_per_node"], 8)

    def test_invalid_fixture_returns_fatal_error(self) -> None:
        result = parse_sizing_file_detailed(str(self.fixture("invalid.json")))
        self.assertIsNotNone(result.fatal_error)
        self.assertIsNone(result.addon_context)
        self.assertEqual(result.fatal_error.code, "invalid_json")

    def test_system_pool_composition_sets_system_selector_for_kibana_and_fleet(self) -> None:
        result = parse_sizing_file_detailed(str(self.fixture("platform-v1-system-placement.json")))
        self.assertIsNone(result.fatal_error)
        self.assertIsNotNone(result.model)
        self.assertEqual(result.model.schema_version, "es-sizing-platform.v1")
        kibana = result.model.components.get("kibana", {})
        fleet = result.model.components.get("fleet_server", {})
        self.assertEqual(kibana.get("count"), 1)
        self.assertEqual(fleet.get("count"), 1)
        self.assertEqual(kibana.get("node_selector"), {"elasticsearch.k8s.elastic.co/tier": "system"})
        self.assertEqual(fleet.get("node_selector"), {"elasticsearch.k8s.elastic.co/tier": "system"})

    def test_rke2_fixture_generates_expected_golden_outputs(self) -> None:
        sizing_context = parse_sizing_file(str(self.fixture("rke2-v1.json")))
        with tempfile.TemporaryDirectory(prefix="pi-sizing-fixture-rke2-") as td:
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
            config = json.loads((out_dir / "sizing/config.json").read_text())
            tfvars = (out_dir / "terraform/terraform.tfvars.example").read_text()
            requirements = (out_dir / "sizing/resource-requirements.yaml").read_text()
            csv = (out_dir / "sizing/capacity-planning.csv").read_text()

            self.assertEqual(config["source"], "sizing_report")
            self.assertEqual(config["health_score"], 93)
            self.assertEqual(config["tiers"]["hot"]["count"], 1)
            self.assertEqual(config["kibana"]["count"], 1)
            self.assertEqual(config["fleet_server"]["count"], 1)
            self.assertEqual(config["kibana"]["memory"], "4Gi")
            self.assertEqual(config["kibana"]["cpu"], "2")
            self.assertIn('"hot_pool" = { node_count = 1, vcpu_per_node = 12, ram_gb_per_node = 20, disk_gb = 100, full_clone = true }', tfvars)
            self.assertIn('"cold_pool" = { node_count = 1, vcpu_per_node = 12, ram_gb_per_node = 15, disk_gb = 100, full_clone = true }', tfvars)
            self.assertIn('# HOT TIER (primary indexing):', requirements)
            self.assertIn('# KIBANA:', requirements)
            self.assertIn("Component,Count,Memory (Gi),CPU (cores),Storage (Gi),Notes", csv)
            self.assertIn("Hot Tier Nodes,1,8,2,100,Primary indexing (hot tier)", csv)
            self.assertIn("Platform totals (Elasticsearch + Kibana + Fleet)", csv)

    def test_readme_includes_project_header_metadata_from_json(self) -> None:
        payload = {
            "schema_version": "es-sizing-rke2.v1",
            "platform": "rke2",
            "generated_at": "2026-03-25T10:00:00Z",
            "project": {
                "name": "OS-6",
                "customer": "OS-6",
                "description": "RKE2-dev",
                "project_id": "1",
                "user_name": "XX",
            },
            "elasticsearch": {
                "inputs": {
                    "ingest_gb_per_day": 1,
                    "total_retention_days": 365,
                    "workload_type": "mixed",
                },
                "summary": {
                    "cluster_health_score": 95,
                    "total_nodes": 2,
                    "total_data_nodes": 2,
                    "total_master_nodes": 0,
                },
                "tiers": [
                    {"name": "hot", "nodes": 1, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 100},
                    {"name": "cold", "nodes": 1, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 100},
                    {"name": "frozen", "nodes": 0, "vcpu_per_node": 2, "ram_gb_per_node": 8, "disk_gb_per_node": 0},
                ],
            },
            "rke2": {
                "pools": [
                    {"name": "hot_pool", "nodes": 1, "vcpu_per_node": 8, "ram_gb_per_node": 32, "disk_gb_per_node": 100},
                    {"name": "cold_pool", "nodes": 1, "vcpu_per_node": 8, "ram_gb_per_node": 32, "disk_gb_per_node": 100},
                    {
                        "name": "system_pool",
                        "nodes": 1,
                        "vcpu_per_node": 8,
                        "ram_gb_per_node": 32,
                        "disk_gb_per_node": 80,
                        "composition": {"kibana_pods": 1, "fleet_pods": 1},
                    },
                ],
                "stack_components": {"vcpu": 4, "ram_gb": 8},
            },
        }

        with tempfile.TemporaryDirectory(prefix="pi-readme-metadata-") as td:
            contract_path = Path(td) / "sizing.json"
            contract_path.write_text(json.dumps(payload), encoding="utf-8")
            sizing_context = parse_sizing_file(str(contract_path))

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
            readme = (out_dir / "README.md").read_text(encoding="utf-8")
            self.assertIn("## Deployment Snapshot", readme)
            self.assertIn("Project Name: `OS-6`", readme)
            self.assertIn("Customer: `OS-6`", readme)
            self.assertIn("Project ID: `1`", readme)
            self.assertIn("Owner / User: `XX`", readme)
            self.assertIn("Description: RKE2-dev", readme)
            self.assertIn("Sizing Export Generated: `2026-03-25T10:00:00Z`", readme)

    def test_platform_fixture_generates_expected_golden_outputs(self) -> None:
        sizing_context = parse_sizing_file(str(self.fixture("platform-v1-openshift.json")))
        with tempfile.TemporaryDirectory(prefix="pi-sizing-fixture-platform-") as td:
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
            config = json.loads((out_dir / "sizing/config.json").read_text())
            tfvars = (out_dir / "terraform/terraform.tfvars.example").read_text()
            requirements = (out_dir / "sizing/resource-requirements.yaml").read_text()

            self.assertEqual(config["platform"], "openshift")
            self.assertEqual(config["kibana"]["count"], 1)
            self.assertEqual(config["fleet_server"]["count"], 1)
            self.assertEqual(config["kibana"]["memory"], "4Gi")
            self.assertEqual(config["fleet_server"]["cpu"], "2")
            self.assertIn('"hot_pool" = { node_count = 1, vcpu_per_node = 4, ram_gb_per_node = 16, disk_gb = 100, full_clone = true }', tfvars)
            self.assertIn('"system_pool" = { node_count = 2, vcpu_per_node = 4, ram_gb_per_node = 8, disk_gb = 80, full_clone = true }', tfvars)
            self.assertIn("# Platform: OpenShift", requirements)
            self.assertIn("# Health Score: 93/100", requirements)

    def test_system_pool_fixture_places_kibana_and_fleet_on_system_tier(self) -> None:
        sizing_context = parse_sizing_file(str(self.fixture("platform-v1-system-placement.json")))
        with tempfile.TemporaryDirectory(prefix="pi-sizing-fixture-system-placement-") as td:
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
            kibana_yaml = (out_dir / "kibana/kibana.yaml").read_text()
            fleet_yaml = (out_dir / "agents/fleet-server.yaml").read_text()
            self.assertIn('"elasticsearch.k8s.elastic.co/tier": "system"', kibana_yaml)
            self.assertIn('"elasticsearch.k8s.elastic.co/tier": "system"', fleet_yaml)
            self.assertNotIn('"elasticsearch.k8s.elastic.co/tier": "hot"', kibana_yaml)
            self.assertNotIn('"elasticsearch.k8s.elastic.co/tier": "hot"', fleet_yaml)

    def test_zero_dedicated_master_nodes_do_not_fall_back_to_three(self) -> None:
        sizing_context = parse_sizing_file(str(self.fixture("rke2-v1.json")))
        with tempfile.TemporaryDirectory(prefix="pi-sizing-fixture-zero-master-") as td:
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
            es_cluster = (out_dir / "elasticsearch/cluster.yaml").read_text()
            self.assertNotIn("- name: master", es_cluster)
            self.assertIn('node.roles: ["master", "data_hot", "data_content", "ingest", "transform", "remote_cluster_client"]', es_cluster)

    def test_proxmox_rke2_fixture_generates_platform_golden_outputs(self) -> None:
        sizing_context = parse_sizing_file(str(self.fixture("rke2-v1.json")))
        with tempfile.TemporaryDirectory(prefix="pi-golden-proxmox-rke2-") as td:
            out_dir = Path(td) / "sample-project"
            initialize_project(
                project_name="sample-project",
                description="",
                target_directory=str(out_dir),
                platform="proxmox",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
                enable_otel_collector=True,
            )
            tfvars = (out_dir / "terraform/terraform.tfvars.example").read_text()
            kibana_kustomization = (out_dir / "kibana/kustomization.yaml").read_text()
            healthcheck = (out_dir / "scripts/cluster-healthcheck.sh").read_text()
            blueprint = (out_dir / "platform/DELIVERY_BLUEPRINT.md").read_text()
            rollout = (out_dir / "docs/OBSERVABILITY_ROLLOUT.md").read_text()

            self.assertIn('"hot_pool" = { node_count = 1, vcpu_per_node = 12, ram_gb_per_node = 20, disk_gb = 100, full_clone = true }', tfvars)
            self.assertIn("- ingress.yaml", kibana_kustomization)
            self.assertTrue((out_dir / "kibana/ingress.yaml").exists())
            # kubeconfig.sh (sourced by healthcheck) holds the RKE2 path; healthcheck delegates to the library
            kubeconfig_sh = (out_dir / "scripts/lib/kubeconfig.sh").read_text()
            self.assertIn("/etc/rancher/rke2/rke2.yaml", kubeconfig_sh)
            self.assertIn("kubeconfig.sh", healthcheck)
            self.assertIn("pi_prepare_kubeconfig", healthcheck)
            self.assertIn("Rancher-governed RKE2", blueprint)
            self.assertIn("Azure AKS", blueprint)
            self.assertIn("Day-0 substrate", rollout)
            self.assertIn("RKE2 workload cluster is bootstrapped and reachable", rollout)

    def test_rancher_governed_rke2_generates_platform_golden_outputs(self) -> None:
        sizing_context = parse_sizing_file(str(self.fixture("rke2-v1.json")))
        with tempfile.TemporaryDirectory(prefix="pi-golden-rancher-rke2-") as td:
            out_dir = Path(td) / "sample-project"
            initialize_project(
                project_name="sample-project",
                description="Rancher governed RKE2 Elastic platform with Fleet",
                target_directory=str(out_dir),
                platform="rke2",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
                enable_otel_collector=True,
            )
            blueprint = (out_dir / "platform/DELIVERY_BLUEPRINT.md").read_text()
            rke2_cluster_config = (out_dir / "platform/rke2/cluster-config.yaml").read_text()
            healthcheck = (out_dir / "scripts/cluster-healthcheck.sh").read_text()
            kibana_kustomization = (out_dir / "kibana/kustomization.yaml").read_text()

            self.assertIn("## Requested Variant", blueprint)
            self.assertIn("Rancher-governed RKE2 delivery", blueprint)
            self.assertIn("Rancher/Fleet import and governance", blueprint)
            self.assertIn("write-kubeconfig-mode:", rke2_cluster_config)
            self.assertIn("kubelet-arg:", rke2_cluster_config)
            # kubeconfig.sh (sourced by healthcheck) holds the RKE2 path; healthcheck delegates to the library
            kubeconfig_sh = (out_dir / "scripts/lib/kubeconfig.sh").read_text()
            self.assertIn("/etc/rancher/rke2/rke2.yaml", kubeconfig_sh)
            self.assertIn("kubeconfig.sh", healthcheck)
            self.assertIn("pi_prepare_kubeconfig", healthcheck)
            self.assertIn("- ingress.yaml", kibana_kustomization)
            self.assertTrue((out_dir / "platform/rke2/storage-class.yaml").exists())

    def test_openshift_fixture_generates_platform_golden_outputs(self) -> None:
        sizing_context = parse_sizing_file(str(self.fixture("platform-v1-openshift.json")))
        with tempfile.TemporaryDirectory(prefix="pi-golden-openshift-") as td:
            out_dir = Path(td) / "sample-project"
            initialize_project(
                project_name="sample-project",
                description="",
                target_directory=str(out_dir),
                platform="openshift",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
                enable_otel_collector=True,
            )
            es_cluster = (out_dir / "elasticsearch/cluster.yaml").read_text()
            kibana_kustomization = (out_dir / "kibana/kustomization.yaml").read_text()
            route_yaml = (out_dir / "platform/openshift/route.yaml").read_text()
            rollout = (out_dir / "docs/OBSERVABILITY_ROLLOUT.md").read_text()

            self.assertIn("storageClassName: standard", es_cluster)
            self.assertNotIn("- ingress.yaml", kibana_kustomization)
            self.assertFalse((out_dir / "kibana/ingress.yaml").exists())
            self.assertIn("kind: Route", route_yaml)
            self.assertIn("sample-project-kibana", route_yaml)
            self.assertIn("OpenShift may reject hostPath-based collectors", rollout)

    def test_aks_generates_platform_golden_outputs(self) -> None:
        sizing_context = {
            "source": "sizing_report",
            "data_nodes": {"count": 1, "memory": "8Gi", "cpu": "2", "storage": "100Gi"},
            "cold_nodes": {"count": 1, "memory": "8Gi", "cpu": "2", "storage": "200Gi"},
            "fleet_server": {"count": 1, "memory": "4Gi", "cpu": "2"},
            "kibana": {"count": 1, "memory": "4Gi", "cpu": "2"},
            "eck_operator": {"version": "3.0.0"},
        }
        with tempfile.TemporaryDirectory(prefix="pi-golden-aks-") as td:
            out_dir = Path(td) / "sample-project"
            initialize_project(
                project_name="sample-project",
                description="",
                target_directory=str(out_dir),
                platform="aks",
                gitops_tool="flux",
                iac_tool="terraform",
                sizing_context=sizing_context,
                enable_otel_collector=True,
            )
            es_cluster = (out_dir / "elasticsearch/cluster.yaml").read_text()
            kibana_kustomization = (out_dir / "kibana/kustomization.yaml").read_text()
            aks_ingress = (out_dir / "platform/aks/ingress.yaml").read_text()
            healthcheck = (out_dir / "scripts/cluster-healthcheck.sh").read_text()
            rollout = (out_dir / "docs/OBSERVABILITY_ROLLOUT.md").read_text()

            self.assertIn("storageClassName: premium", es_cluster)
            self.assertIn("storageClassName: standard", es_cluster)
            self.assertNotIn("- ingress.yaml", kibana_kustomization)
            self.assertFalse((out_dir / "kibana/ingress.yaml").exists())
            self.assertIn("azure/application-gateway", aks_ingress)
            self.assertNotIn("/etc/rancher/rke2/rke2.yaml", healthcheck)
            self.assertIn("For managed or externally delivered clusters", healthcheck)
            self.assertIn("managed metrics-server", rollout)
            self.assertIn("Azure Monitor overlap", rollout)


if __name__ == "__main__":
    unittest.main()
