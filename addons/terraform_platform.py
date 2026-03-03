#!/usr/bin/env python3
"""
Terraform addon for non-AKS platforms (RKE2/OpenShift).
Generates platform-aware Terraform scaffold and maps sizing data into tfvars examples.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


ADDON_META = {
    "name": "terraform_platform",
    "version": "1.0",
    "description": "Terraform scaffold for RKE2, OpenShift and Proxmox",
    "triggers": {"platforms": ["rke2", "openshift", "proxmox"], "iac_tools": ["terraform"]},
    "priority": 16,
}


class TerraformPlatformGenerator:
    def __init__(
        self,
        project_name: str,
        project_description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.project_name = project_name
        self.description = project_description
        self.context = context or {}
        self.platform = (self.context.get("platform") or "").lower()
        self.sizing = self.context.get("sizing_context") or {}

    def _rke2_pools(self) -> List[Dict[str, Any]]:
        return ((self.sizing.get("rke2") or {}).get("pools") or [])

    def _openshift_pools(self) -> List[Dict[str, Any]]:
        return ((self.sizing.get("openshift") or {}).get("worker_pools") or [])

    def _rke2_tfvars(self) -> str:
        pools = self._rke2_pools()
        pool_lines = []
        for pool in pools:
            nodes = int(pool.get("nodes") or 0)
            vcpu = pool.get("vcpu_per_node")
            ram = pool.get("ram_gb_per_node")
            if nodes <= 0:
                comp = pool.get("composition") or {}
                requested_cpu = float(comp.get("total_requested_cpu") or 0.0)
                requested_ram = float(comp.get("total_requested_ram_gb") or 0.0)
                # Deterministic fallback sizing when report does not provide final node counts.
                nodes = max(1, int(math.ceil(max(requested_cpu / 8.0, requested_ram / 32.0))))
            if nodes <= 0:
                continue
            pool_lines.append(
                f'  "{pool.get("name", "pool")}" = {{ node_count = {nodes}, vcpu_per_node = {int(vcpu or 4)}, ram_gb_per_node = {int(ram or 16)} }}'
            )
        if not pool_lines:
            pool_lines = ['  "system_pool" = { node_count = 3, vcpu_per_node = 4, ram_gb_per_node = 16 }']
        return (
            f'project_name = "{self.project_name}"\n'
            'environment  = "dev"\n'
            'cluster_name = "rke2-es"\n\n'
            "rke2_pools = {\n"
            + "\n".join(pool_lines)
            + "\n}\n"
        )

    def _openshift_tfvars(self) -> str:
        pools = self._openshift_pools()
        pool_lines = []
        for pool in pools:
            rec = pool.get("recommendation") or {}
            worker = pool.get("worker") or {}
            total = int(rec.get("total") or pool.get("nodes") or 0)
            vcpu = int(worker.get("vcpu") or 4)
            ram = int(worker.get("ram_gb") or 16)
            if total <= 0:
                continue
            pool_lines.append(
                f'  "{pool.get("name", "worker_pool")}" = {{ node_count = {total}, vcpu_per_node = {vcpu}, ram_gb_per_node = {ram} }}'
            )
        if not pool_lines:
            pool_lines = ['  "hot_pool" = { node_count = 3, vcpu_per_node = 8, ram_gb_per_node = 32 }']
        return (
            f'project_name = "{self.project_name}"\n'
            'environment  = "dev"\n'
            'cluster_name = "ocp-es"\n\n'
            "openshift_worker_pools = {\n"
            + "\n".join(pool_lines)
            + "\n}\n"
        )

    def generate(self) -> Dict[str, str]:
        if self.platform not in {"rke2", "openshift", "proxmox"}:
            return {}

        files: Dict[str, str] = {}
        files["terraform/README.md"] = self._readme()
        files["terraform/versions.tf"] = self._versions_tf()
        files["terraform/providers.tf"] = self._providers_tf()
        files["terraform/main.tf"] = self._root_main()
        files["terraform/variables.tf"] = self._root_variables()
        files["terraform/outputs.tf"] = self._root_outputs()

        if self.platform == "rke2":
            files["terraform/modules/rke2_cluster/main.tf"] = self._module_rke2_main()
            files["terraform/modules/rke2_cluster/README.md"] = "RKE2 cluster module scaffold.\n"
            files["terraform/terraform.tfvars.example"] = self._rke2_tfvars()
        elif self.platform == "proxmox":
            files["terraform/modules/proxmox_cluster/main.tf"] = self._module_proxmox_main()
            files["terraform/modules/proxmox_cluster/README.md"] = "Proxmox VM cluster module scaffold.\n"
            files["terraform/terraform.tfvars.example"] = self._proxmox_tfvars()
        else:
            files["terraform/modules/openshift_cluster/main.tf"] = self._module_openshift_main()
            files["terraform/modules/openshift_cluster/README.md"] = "OpenShift cluster module scaffold.\n"
            files["terraform/terraform.tfvars.example"] = self._openshift_tfvars()

        return files

    def _versions_tf(self) -> str:
        return (
            'terraform {\n'
            '  required_version = ">= 1.5.0"\n'
            '  required_providers {\n'
            '    local = { source = "hashicorp/local", version = ">= 2.5.0" }\n'
            '    null  = { source = "hashicorp/null", version = ">= 3.2.2" }\n'
            '    proxmox = { source = "bpg/proxmox", version = ">= 0.66.3" }\n'
            '  }\n'
            '}\n'
        )

    def _providers_tf(self) -> str:
        return (
            'provider "null" {}\n'
            'provider "local" {}\n\n'
            'provider "proxmox" {\n'
            '  endpoint  = var.proxmox_endpoint\n'
            '  api_token = "${var.proxmox_api_token_id}=${var.proxmox_api_token_secret}"\n'
            '  insecure  = var.proxmox_insecure_tls\n'
            '}\n'
        )

    def _root_main(self) -> str:
        if self.platform == "rke2":
            module_name = "rke2_cluster"
            pools_var = "rke2_pools"
        elif self.platform == "proxmox":
            module_name = "proxmox_cluster"
            pools_var = "proxmox_node_pools"
        else:
            module_name = "openshift_cluster"
            pools_var = "openshift_worker_pools"
        proxmox_args = ""
        if self.platform == "proxmox":
            proxmox_args = (
                "  proxmox_node_name      = var.proxmox_node_name\n"
                "  proxmox_template_vmid  = var.proxmox_template_vmid\n"
                "  proxmox_vm_storage     = var.proxmox_vm_storage\n"
                "  proxmox_vm_bridge      = var.proxmox_vm_network_bridge\n"
                "  vmid_start             = var.vmid_start\n"
                "  vm_ci_user             = var.vm_ci_user\n"
                "  vm_ssh_public_key_path = var.ssh_public_key_path\n"
                "  vm_disk_size_gb        = var.vm_disk_size_gb\n"
                "  proxmox_full_clone     = var.proxmox_full_clone\n"
            )

        return (
            f'module "platform" {{\n'
            f'  source = "./modules/{module_name}"\n'
            "  project_name = var.project_name\n"
            "  environment  = var.environment\n"
            "  cluster_name = var.cluster_name\n"
            f"  pools        = var.{pools_var}\n"
            f"{proxmox_args}"
            "}\n"
        )

    def _root_variables(self) -> str:
        if self.platform == "rke2":
            pools_var = "rke2_pools"
        elif self.platform == "proxmox":
            pools_var = "proxmox_node_pools"
        else:
            pools_var = "openshift_worker_pools"
        return (
            'variable "project_name" {\n  type = string\n}\n'
            'variable "environment" {\n  type = string\n}\n'
            'variable "cluster_name" {\n  type = string\n}\n'
            'variable "proxmox_endpoint" {\n  type = string\n  default = "https://proxmox.example.local:8006"\n}\n'
            'variable "proxmox_api_token_id" {\n  type = string\n  default = "terraform@pve!iac"\n}\n'
            'variable "proxmox_api_token_secret" {\n  type = string\n  sensitive = true\n  default = ""\n}\n'
            'variable "proxmox_insecure_tls" {\n  type = bool\n  default = true\n}\n'
            'variable "proxmox_node_name" {\n  type = string\n  default = "pve01"\n}\n'
            'variable "proxmox_vm_network_bridge" {\n  type = string\n  default = "vmbr0"\n}\n'
            'variable "proxmox_template_vmid" {\n  type = number\n  default = 9000\n}\n'
            'variable "proxmox_vm_storage" {\n  type = string\n  default = "local-lvm"\n}\n'
            'variable "vmid_start" {\n  type = number\n  default = 5000\n}\n'
            'variable "vm_disk_size_gb" {\n  type = number\n  default = 80\n}\n'
            'variable "proxmox_full_clone" {\n  type = bool\n  default = true\n}\n'
            'variable "vm_ci_user" {\n  type = string\n  default = "ubuntu"\n}\n'
            'variable "k8s_cluster_cidr" {\n  type = string\n  default = "10.42.0.0/16"\n}\n'
            'variable "k8s_service_cidr" {\n  type = string\n  default = "10.43.0.0/16"\n}\n'
            'variable "ssh_public_key_path" {\n  type = string\n  default = "~/.ssh/id_rsa.pub"\n}\n'
            'variable "git_repo_url" {\n  type = string\n  default = ""\n}\n'
            'variable "git_branch" {\n  type = string\n  default = "main"\n}\n'
            'variable "gitops_flux_path" {\n  type = string\n  default = "./clusters/management"\n}\n'
            f'variable "{pools_var}" {{\n'
            "  type = map(object({\n"
            "    node_count      = number\n"
            "    vcpu_per_node   = number\n"
            "    ram_gb_per_node = number\n"
            "    node_name      = optional(string)\n"
            "    disk_gb        = optional(number)\n"
            "    full_clone     = optional(bool)\n"
            "  }))\n"
            "}\n"
        )

    def _root_outputs(self) -> str:
        return (
            'output "cluster_name" { value = module.platform.cluster_name }\n'
            'output "pool_count"   { value = module.platform.pool_count }\n'
        )

    def _module_rke2_main(self) -> str:
        return (
            'variable "project_name" { type = string }\n'
            'variable "environment"  { type = string }\n'
            'variable "cluster_name" { type = string }\n'
            'variable "pools" {\n'
            "  type = map(object({ node_count = number, vcpu_per_node = number, ram_gb_per_node = number }))\n"
            "}\n\n"
            'resource "local_file" "rke2_plan" {\n'
            '  filename = "${path.root}/../docs/rke2-terraform-plan.txt"\n'
            '  content  = "RKE2 cluster ${var.cluster_name} with ${length(var.pools)} pools"\n'
            "}\n\n"
            'output "cluster_name" { value = var.cluster_name }\n'
            'output "pool_count" { value = length(var.pools) }\n'
        )

    def _module_openshift_main(self) -> str:
        return (
            'variable "project_name" { type = string }\n'
            'variable "environment"  { type = string }\n'
            'variable "cluster_name" { type = string }\n'
            'variable "pools" {\n'
            "  type = map(object({ node_count = number, vcpu_per_node = number, ram_gb_per_node = number }))\n"
            "}\n\n"
            'resource "local_file" "openshift_plan" {\n'
            '  filename = "${path.root}/../docs/openshift-terraform-plan.txt"\n'
            '  content  = "OpenShift cluster ${var.cluster_name} with ${length(var.pools)} worker pools"\n'
            "}\n\n"
            'output "cluster_name" { value = var.cluster_name }\n'
            'output "pool_count" { value = length(var.pools) }\n'
        )

    def _module_proxmox_main(self) -> str:
        return (
            'terraform {\n'
            '  required_providers {\n'
            '    proxmox = { source = "bpg/proxmox", version = ">= 0.66.3" }\n'
            '  }\n'
            '}\n\n'
            'variable "project_name" { type = string }\n'
            'variable "environment"  { type = string }\n'
            'variable "cluster_name" { type = string }\n'
            'variable "proxmox_node_name" { type = string }\n'
            'variable "proxmox_template_vmid" { type = number }\n'
            'variable "proxmox_vm_storage" { type = string }\n'
            'variable "proxmox_vm_bridge" { type = string }\n'
            'variable "vmid_start" { type = number }\n'
            'variable "vm_ci_user" { type = string }\n'
            'variable "vm_ssh_public_key_path" { type = string }\n'
            'variable "vm_disk_size_gb" { type = number }\n'
            'variable "proxmox_full_clone" { type = bool }\n'
            'variable "pools" {\n'
            '  type = map(object({ node_count = number, vcpu_per_node = number, ram_gb_per_node = number, node_name = optional(string), disk_gb = optional(number), full_clone = optional(bool) }))\n'
            '}\n\n'
            'locals {\n'
            '  vm_matrix = flatten([\n'
            '    for pool_name, pool in var.pools : [\n'
            '      for idx in range(pool.node_count) : {\n'
            '        key       = "${pool_name}-${idx + 1}"\n'
            '        name_pool = replace(lower(pool_name), "_", "-")\n'
            '        pool      = pool_name\n'
            '        idx       = idx\n'
            '        vcpu      = pool.vcpu_per_node\n'
            '        memory    = pool.ram_gb_per_node\n'
            '        node_name = coalesce(pool.node_name, var.proxmox_node_name)\n'
            '        disk_gb   = coalesce(pool.disk_gb, var.vm_disk_size_gb)\n'
            '        full_clone = coalesce(pool.full_clone, var.proxmox_full_clone)\n'
            '      }\n'
            '    ]\n'
            '  ])\n'
            '  vm_by_key = { for vm in local.vm_matrix : vm.key => vm }\n'
            '}\n\n'
            'resource "proxmox_virtual_environment_vm" "nodes" {\n'
            '  for_each = local.vm_by_key\n'
            '  node_name = each.value.node_name\n'
            '  vm_id     = var.vmid_start + each.value.idx + 100 * index(sort(keys(var.pools)), each.value.pool)\n'
            '  name      = "${replace(lower(var.cluster_name), "_", "-")}-${each.value.name_pool}-${each.value.idx + 1}"\n'
            '  on_boot   = true\n\n'
            '  cpu {\n'
            '    cores = each.value.vcpu\n'
            '    type  = "x86-64-v2-AES"\n'
            '  }\n\n'
            '  memory {\n'
            '    dedicated = each.value.memory * 1024\n'
            '  }\n\n'
            '  clone {\n'
            '    vm_id = var.proxmox_template_vmid\n'
            '    full  = each.value.full_clone\n'
            '  }\n\n'
            '  disk {\n'
            '    datastore_id = var.proxmox_vm_storage\n'
            '    interface    = "scsi0"\n'
            '    size         = each.value.disk_gb\n'
            '  }\n\n'
            '  network_device {\n'
            '    bridge = var.proxmox_vm_bridge\n'
            '  }\n\n'
            '  initialization {\n'
            '    user_account {\n'
            '      username = var.vm_ci_user\n'
            '      keys     = compact([try(file(pathexpand(var.vm_ssh_public_key_path)), "")])\n'
            '    }\n'
            '    ip_config {\n'
            '      ipv4 {\n'
            '        address = "dhcp"\n'
            '      }\n'
            '    }\n'
            '  }\n'
            '}\n\n'
            'output "cluster_name" { value = var.cluster_name }\n'
            'output "pool_count" { value = length(var.pools) }\n'
            'output "vm_names" { value = [for vm in proxmox_virtual_environment_vm.nodes : vm.name] }\n'
        )

    def _proxmox_tfvars(self) -> str:
        # Reuse RKE2 sizing signal as Proxmox VM pool baseline.
        pools = self._rke2_pools()
        pool_lines = []
        for pool in pools:
            nodes = int(pool.get("nodes") or 0)
            comp = pool.get("composition") or {}
            if nodes <= 0:
                requested_cpu = float(comp.get("total_requested_cpu") or 0.0)
                requested_ram = float(comp.get("total_requested_ram_gb") or 0.0)
                nodes = max(1, int(math.ceil(max(requested_cpu / 8.0, requested_ram / 32.0))))
            pool_lines.append(
                f'  "{pool.get("name", "pool")}" = {{ node_count = {nodes}, vcpu_per_node = 8, ram_gb_per_node = 32, disk_gb = 80, full_clone = true }}'
            )
        if not pool_lines:
            pool_lines = ['  "workers" = { node_count = 3, vcpu_per_node = 8, ram_gb_per_node = 32, disk_gb = 80, full_clone = true }']
        return (
            f'project_name = "{self.project_name}"\n'
            'environment  = "dev"\n'
            'cluster_name = "proxmox-rke2-es"\n\n'
            'proxmox_endpoint = "https://proxmox.example.local:8006"\n'
            'proxmox_api_token_id = "terraform@pve!iac"\n'
            'proxmox_api_token_secret = "CHANGE_ME"\n'
            'proxmox_insecure_tls = true\n'
            'proxmox_node_name = "pve01"\n'
            'proxmox_vm_network_bridge = "vmbr0"\n'
            'proxmox_template_vmid = 9000\n'
            'proxmox_vm_storage = "local-lvm"\n'
            'vmid_start = 5000\n'
            'vm_disk_size_gb = 80\n'
            'proxmox_full_clone = true\n'
            'vm_ci_user = "ubuntu"\n'
            'k8s_cluster_cidr = "10.42.0.0/16"\n'
            'k8s_service_cidr = "10.43.0.0/16"\n'
            'ssh_public_key_path = "~/.ssh/id_rsa.pub"\n'
            'git_repo_url = "https://github.com/your-org/your-repo.git"\n'
            'git_branch = "main"\n'
            'gitops_flux_path = "./clusters/management"\n\n'
            "proxmox_node_pools = {\n"
            + "\n".join(pool_lines)
            + "\n}\n"
        )

    def _readme(self) -> str:
        return (
            f"# Terraform ({self.platform.upper()})\n\n"
            "This Terraform scaffold is platform-aware and generated from project-initializer.\n\n"
            "## Structure\n\n"
            "- `main.tf`: root orchestration\n"
            "- `providers.tf`: providers and authentication inputs\n"
            "- `variables.tf`: deployment variables\n"
            "- `terraform.tfvars.example`: editable environment values\n"
            "- `modules/*`: platform module scaffold\n\n"
            "## Inputs\n\n"
            "- `terraform.tfvars.example` is pre-filled from sizing context when available.\n"
            "- Review provider auth, network CIDRs, node pools, and GitOps path before apply.\n\n"
            "## Run\n\n"
            "```bash\n"
            "cd terraform\n"
            "terraform init\n"
            "cp terraform.tfvars.example terraform.tfvars\n"
            "terraform plan\n"
            "```\n"
        )


def main(project_name: str, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    generator = TerraformPlatformGenerator(project_name, description, context)
    return generator.generate()
