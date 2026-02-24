#!/usr/bin/env python3
"""
Terraform AKS module addon for project-initializer.
Generates a complete Terraform module structure for Azure Kubernetes Service.

Includes modules for:
- AKS cluster
- Networking (VNet, subnets, NSGs)
- Storage (Storage accounts for ES snapshots)
- ACR (Azure Container Registry)
- Monitoring (Log Analytics, Azure Monitor)

Supports sizing_context from sizing_parser.py for properly-sized infrastructure.

Zero external dependencies -- Python 3.9+ stdlib only.
"""

from typing import Any, Dict, List, Optional


ADDON_META = {
    "name": "terraform_aks",
    "version": "1.1",
    "description": "Terraform AKS module structure for Azure Kubernetes Service",
    "triggers": {
        "platforms": ["aks"],
        "keywords": ["azure", "aks"],
    },
    "priority": 15,
}


class TerraformAKSGenerator:
    """Generates Terraform module structure for AKS deployments."""
    
    def __init__(
        self,
        project_name: str,
        project_description: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.project_name = project_name
        self.description = project_description
        self.context = context or {}
        
        # Azure region (default to West Europe for Skane proximity)
        self.location = self.context.get("azure_location", "westeurope")
        self.location_short = self._get_location_short(self.location)
        
        # Environment
        self.environment = self.context.get("environment", "dev")
        
        # Kubernetes version
        self.k8s_version = self.context.get("k8s_version", "1.30")
        
        # Extract AKS sizing from context (from sizing_parser)
        # sizing_context is nested inside context
        sizing_context = self.context.get("sizing_context", {}) or {}
        self.aks_sizing = sizing_context.get("aks", {})
        self.sizing_source = sizing_context.get("source", "default")
        
        # Node pool configurations (from sizing or defaults)
        self._configure_node_pools()
    
    def _configure_node_pools(self):
        """Configure node pools from sizing context or use defaults."""
        aks = self.aks_sizing
        
        if aks and aks.get("node_pools"):
            # Use sizing from report
            pools = {p["name"]: p for p in aks["node_pools"]}
            
            # System pool
            sys_pool = pools.get("system", {})
            self.system_node_count = sys_pool.get("node_count", 3)
            self.system_vm_size = sys_pool.get("vm_size", "Standard_D2s_v5")
            
            # ES Hot pool
            hot_pool = pools.get("eshot", {})
            self.es_hot_node_count = hot_pool.get("node_count", 3)
            self.es_hot_vm_size = hot_pool.get("vm_size", "Standard_E8s_v5")
            self.es_hot_disk_size_gb = hot_pool.get("disk_size_gb", 256)
            
            # ES Cold pool
            cold_pool = pools.get("escold", {})
            self.es_cold_enabled = cold_pool.get("node_count", 0) > 0
            self.es_cold_node_count = cold_pool.get("node_count", 3)
            self.es_cold_vm_size = cold_pool.get("vm_size", "Standard_L8s_v3")
            self.es_cold_disk_size_gb = cold_pool.get("disk_size_gb", 256)
            
            # ES Frozen pool
            frozen_pool = pools.get("esfrozen", {})
            self.es_frozen_enabled = frozen_pool.get("node_count", 0) > 0
            self.es_frozen_node_count = frozen_pool.get("node_count", 0)
            self.es_frozen_vm_size = frozen_pool.get("vm_size", "Standard_E8s_v5")
            self.es_frozen_disk_size_gb = frozen_pool.get("disk_size_gb", 2400)
            
            # Networking from sizing
            networking = aks.get("networking", {})
            self.vnet_cidr = networking.get("vnet_cidr", "10.0.0.0/16")
            self.aks_subnet_cidr = networking.get("aks_subnet_cidr", "10.0.0.0/20")
            
            # Storage from sizing - check both aks.storage and frozen_nodes
            storage = aks.get("storage", {})
            self.snapshot_storage_gb = storage.get("snapshot_storage_gb", 0)
            
            # Also check sizing_context.frozen_nodes for snapshot storage
            sizing_context = self.context.get("sizing_context", {}) or {}
            frozen_nodes = sizing_context.get("frozen_nodes", {})
            if not self.snapshot_storage_gb and frozen_nodes:
                self.snapshot_storage_gb = frozen_nodes.get("snapshot_storage_gb", 0)
        else:
            # Use defaults
            self.system_node_count = 3
            self.system_vm_size = "Standard_D2s_v5"
            
            self.es_hot_node_count = 3
            self.es_hot_vm_size = "Standard_E8s_v5"
            self.es_hot_disk_size_gb = 256
            
            self.es_cold_enabled = False
            self.es_cold_node_count = 3
            self.es_cold_vm_size = "Standard_L8s_v3"
            self.es_cold_disk_size_gb = 256
            
            self.es_frozen_enabled = False
            self.es_frozen_node_count = 0
            self.es_frozen_vm_size = "Standard_E8s_v5"
            self.es_frozen_disk_size_gb = 2400
            
            self.vnet_cidr = "10.0.0.0/16"
            self.aks_subnet_cidr = "10.0.0.0/20"
            
            self.snapshot_storage_gb = 0
    
    def _get_location_short(self, location: str) -> str:
        """Get short code for Azure location."""
        location_map = {
            "westeurope": "weu",
            "northeurope": "neu",
            "eastus": "eus",
            "eastus2": "eus2",
            "westus": "wus",
            "westus2": "wus2",
            "swedencentral": "swc",
        }
        return location_map.get(location.lower().replace(" ", ""), "weu")
    
    def generate(self) -> Dict[str, str]:
        """Generate all Terraform files."""
        files = {}
        
        # Root module
        files["terraform/main.tf"] = self._generate_root_main()
        files["terraform/variables.tf"] = self._generate_root_variables()
        files["terraform/outputs.tf"] = self._generate_root_outputs()
        files["terraform/providers.tf"] = self._generate_providers()
        files["terraform/versions.tf"] = self._generate_versions()
        files["terraform/terraform.tfvars.example"] = self._generate_tfvars_example()
        files["terraform/README.md"] = self._generate_readme()
        
        # AKS module
        files["terraform/modules/aks/main.tf"] = self._generate_aks_main()
        files["terraform/modules/aks/variables.tf"] = self._generate_aks_variables()
        files["terraform/modules/aks/outputs.tf"] = self._generate_aks_outputs()
        
        # Networking module
        files["terraform/modules/networking/main.tf"] = self._generate_networking_main()
        files["terraform/modules/networking/variables.tf"] = self._generate_networking_variables()
        files["terraform/modules/networking/outputs.tf"] = self._generate_networking_outputs()
        
        # Storage module
        files["terraform/modules/storage/main.tf"] = self._generate_storage_main()
        files["terraform/modules/storage/variables.tf"] = self._generate_storage_variables()
        files["terraform/modules/storage/outputs.tf"] = self._generate_storage_outputs()
        
        # ACR module
        files["terraform/modules/acr/main.tf"] = self._generate_acr_main()
        files["terraform/modules/acr/variables.tf"] = self._generate_acr_variables()
        files["terraform/modules/acr/outputs.tf"] = self._generate_acr_outputs()
        
        # Monitoring module
        files["terraform/modules/monitoring/main.tf"] = self._generate_monitoring_main()
        files["terraform/modules/monitoring/variables.tf"] = self._generate_monitoring_variables()
        files["terraform/modules/monitoring/outputs.tf"] = self._generate_monitoring_outputs()
        
        return files
    
    # -------------------------------------------------------------------------
    # Root module
    # -------------------------------------------------------------------------
    
    def _generate_root_main(self) -> str:
        """Generate root main.tf."""
        sizing_comment = "# Sized from sizing report" if self.sizing_source == "sizing_report" else "# Default sizing"
        
        return f'''# {self.project_name} - AKS Infrastructure
# Generated by project-initializer
{sizing_comment}

locals {{
  project_name     = var.project_name
  environment      = var.environment
  location         = var.location
  resource_prefix  = "${{var.project_name}}-${{var.environment}}"
  
  common_tags = {{
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Purpose     = "elasticsearch-cluster"
  }}
}}

# Resource Group
resource "azurerm_resource_group" "main" {{
  name     = "rg-${{local.resource_prefix}}"
  location = local.location
  tags     = local.common_tags
}}

# Networking
module "networking" {{
  source = "./modules/networking"
  
  resource_group_name = azurerm_resource_group.main.name
  location            = local.location
  resource_prefix     = local.resource_prefix
  
  vnet_address_space    = var.vnet_address_space
  aks_subnet_prefix     = var.aks_subnet_prefix
  private_subnet_prefix = var.private_subnet_prefix
  
  tags = local.common_tags
}}

# Azure Container Registry
module "acr" {{
  source = "./modules/acr"
  
  resource_group_name = azurerm_resource_group.main.name
  location            = local.location
  resource_prefix     = local.resource_prefix
  
  sku = var.acr_sku
  
  tags = local.common_tags
}}

# Monitoring (Log Analytics + Azure Monitor)
module "monitoring" {{
  source = "./modules/monitoring"
  
  resource_group_name = azurerm_resource_group.main.name
  location            = local.location
  resource_prefix     = local.resource_prefix
  
  log_retention_days = var.log_retention_days
  
  tags = local.common_tags
}}

# Storage (for ES snapshots)
module "storage" {{
  source = "./modules/storage"
  
  resource_group_name = azurerm_resource_group.main.name
  location            = local.location
  resource_prefix     = local.resource_prefix
  
  snapshot_container_name = var.snapshot_container_name
  snapshot_storage_gb     = var.snapshot_storage_gb
  
  tags = local.common_tags
}}

# AKS Cluster
module "aks" {{
  source = "./modules/aks"
  
  resource_group_name = azurerm_resource_group.main.name
  location            = local.location
  resource_prefix     = local.resource_prefix
  
  kubernetes_version = var.kubernetes_version
  
  # Networking
  vnet_subnet_id = module.networking.aks_subnet_id
  
  # System node pool
  system_node_count = var.system_node_count
  system_vm_size    = var.system_vm_size
  
  # ES Hot tier
  es_hot_node_count    = var.es_hot_node_count
  es_hot_vm_size       = var.es_hot_vm_size
  es_hot_disk_size_gb  = var.es_hot_disk_size_gb
  
  # ES Cold tier
  es_cold_enabled      = var.es_cold_enabled
  es_cold_node_count   = var.es_cold_node_count
  es_cold_vm_size      = var.es_cold_vm_size
  es_cold_disk_size_gb = var.es_cold_disk_size_gb
  
  # ES Frozen tier
  es_frozen_enabled      = var.es_frozen_enabled
  es_frozen_node_count   = var.es_frozen_node_count
  es_frozen_vm_size      = var.es_frozen_vm_size
  es_frozen_disk_size_gb = var.es_frozen_disk_size_gb
  
  # Monitoring
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id
  
  # ACR integration
  acr_id = module.acr.acr_id
  
  tags = local.common_tags
}}
'''
    
    def _generate_root_variables(self) -> str:
        """Generate root variables.tf."""
        # Determine if frozen tier should be enabled by default
        frozen_default = "true" if self.es_frozen_enabled else "false"
        cold_default = "true" if self.es_cold_enabled else "false"
        
        return f'''# {self.project_name} - Variables
# {"Generated from sizing report" if self.sizing_source == "sizing_report" else "Default values"}

# -------------------------------------------------------------------------
# Project
# -------------------------------------------------------------------------

variable "project_name" {{
  description = "Name of the project (used in resource naming)"
  type        = string
  default     = "{self.project_name}"
}}

variable "environment" {{
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "{self.environment}"
  
  validation {{
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }}
}}

variable "location" {{
  description = "Azure region for resources"
  type        = string
  default     = "{self.location}"
}}

# -------------------------------------------------------------------------
# Networking
# -------------------------------------------------------------------------

variable "vnet_address_space" {{
  description = "Address space for the VNet"
  type        = list(string)
  default     = ["{self.vnet_cidr}"]
}}

variable "aks_subnet_prefix" {{
  description = "CIDR prefix for AKS subnet"
  type        = string
  default     = "{self.aks_subnet_cidr}"
}}

variable "private_subnet_prefix" {{
  description = "CIDR prefix for private endpoints"
  type        = string
  default     = "10.0.240.0/24"
}}

# -------------------------------------------------------------------------
# Kubernetes
# -------------------------------------------------------------------------

variable "kubernetes_version" {{
  description = "Kubernetes version for AKS"
  type        = string
  default     = "{self.k8s_version}"
}}

variable "system_node_count" {{
  description = "Number of nodes in the system node pool"
  type        = number
  default     = {self.system_node_count}
}}

variable "system_vm_size" {{
  description = "VM size for system node pool"
  type        = string
  default     = "{self.system_vm_size}"
}}

# -------------------------------------------------------------------------
# Elasticsearch Node Pools
# -------------------------------------------------------------------------

# Hot tier
variable "es_hot_node_count" {{
  description = "Number of nodes in the ES hot tier pool"
  type        = number
  default     = {self.es_hot_node_count}
}}

variable "es_hot_vm_size" {{
  description = "VM size for ES hot tier (memory-optimized recommended)"
  type        = string
  default     = "{self.es_hot_vm_size}"
}}

variable "es_hot_disk_size_gb" {{
  description = "OS disk size for ES hot tier nodes"
  type        = number
  default     = {self.es_hot_disk_size_gb}
}}

# Cold tier
variable "es_cold_enabled" {{
  description = "Enable ES cold tier node pool"
  type        = bool
  default     = {cold_default}
}}

variable "es_cold_node_count" {{
  description = "Number of nodes in the ES cold tier pool"
  type        = number
  default     = {self.es_cold_node_count}
}}

variable "es_cold_vm_size" {{
  description = "VM size for ES cold tier (storage-optimized)"
  type        = string
  default     = "{self.es_cold_vm_size}"
}}

variable "es_cold_disk_size_gb" {{
  description = "OS disk size for ES cold tier nodes"
  type        = number
  default     = {self.es_cold_disk_size_gb}
}}

# Frozen tier
variable "es_frozen_enabled" {{
  description = "Enable ES frozen tier node pool"
  type        = bool
  default     = {frozen_default}
}}

variable "es_frozen_node_count" {{
  description = "Number of nodes in the ES frozen tier pool"
  type        = number
  default     = {self.es_frozen_node_count}
}}

variable "es_frozen_vm_size" {{
  description = "VM size for ES frozen tier (memory-optimized for cache)"
  type        = string
  default     = "{self.es_frozen_vm_size}"
}}

variable "es_frozen_disk_size_gb" {{
  description = "Cache disk size for ES frozen tier nodes"
  type        = number
  default     = {self.es_frozen_disk_size_gb}
}}

# -------------------------------------------------------------------------
# Container Registry
# -------------------------------------------------------------------------

variable "acr_sku" {{
  description = "SKU for Azure Container Registry"
  type        = string
  default     = "Standard"
  
  validation {{
    condition     = contains(["Basic", "Standard", "Premium"], var.acr_sku)
    error_message = "ACR SKU must be Basic, Standard, or Premium."
  }}
}}

# -------------------------------------------------------------------------
# Monitoring
# -------------------------------------------------------------------------

variable "log_retention_days" {{
  description = "Log Analytics workspace retention in days"
  type        = number
  default     = 30
}}

# -------------------------------------------------------------------------
# Storage
# -------------------------------------------------------------------------

variable "snapshot_container_name" {{
  description = "Name of the blob container for ES snapshots"
  type        = string
  default     = "elasticsearch-snapshots"
}}

variable "snapshot_storage_gb" {{
  description = "Expected snapshot storage size in GB (for capacity planning)"
  type        = number
  default     = {int(self.snapshot_storage_gb)}
}}
'''
    
    def _generate_root_outputs(self) -> str:
        """Generate root outputs.tf."""
        return f'''# {self.project_name} - Outputs

# -------------------------------------------------------------------------
# Resource Group
# -------------------------------------------------------------------------

output "resource_group_name" {{
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}}

output "resource_group_id" {{
  description = "ID of the resource group"
  value       = azurerm_resource_group.main.id
}}

# -------------------------------------------------------------------------
# AKS
# -------------------------------------------------------------------------

output "aks_cluster_name" {{
  description = "Name of the AKS cluster"
  value       = module.aks.cluster_name
}}

output "aks_cluster_id" {{
  description = "ID of the AKS cluster"
  value       = module.aks.cluster_id
}}

output "aks_kube_config" {{
  description = "Kubeconfig for AKS cluster"
  value       = module.aks.kube_config
  sensitive   = true
}}

output "aks_kube_config_command" {{
  description = "Azure CLI command to get kubeconfig"
  value       = "az aks get-credentials --resource-group ${{azurerm_resource_group.main.name}} --name ${{module.aks.cluster_name}}"
}}

# -------------------------------------------------------------------------
# Networking
# -------------------------------------------------------------------------

output "vnet_id" {{
  description = "ID of the VNet"
  value       = module.networking.vnet_id
}}

output "aks_subnet_id" {{
  description = "ID of the AKS subnet"
  value       = module.networking.aks_subnet_id
}}

# -------------------------------------------------------------------------
# ACR
# -------------------------------------------------------------------------

output "acr_login_server" {{
  description = "Login server for ACR"
  value       = module.acr.login_server
}}

output "acr_admin_username" {{
  description = "Admin username for ACR"
  value       = module.acr.admin_username
  sensitive   = true
}}

# -------------------------------------------------------------------------
# Storage
# -------------------------------------------------------------------------

output "storage_account_name" {{
  description = "Name of the storage account for ES snapshots"
  value       = module.storage.storage_account_name
}}

output "snapshot_container_name" {{
  description = "Name of the blob container for snapshots"
  value       = module.storage.container_name
}}

output "storage_primary_access_key" {{
  description = "Primary access key for storage account"
  value       = module.storage.primary_access_key
  sensitive   = true
}}

# -------------------------------------------------------------------------
# Monitoring
# -------------------------------------------------------------------------

output "log_analytics_workspace_id" {{
  description = "ID of the Log Analytics workspace"
  value       = module.monitoring.log_analytics_workspace_id
}}
'''
    
    def _generate_providers(self) -> str:
        """Generate providers.tf."""
        return '''# Azure Provider Configuration

provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
    
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
  }
}

# Configure Azure backend (uncomment and configure for remote state)
# terraform {
#   backend "azurerm" {
#     resource_group_name  = "rg-terraform-state"
#     storage_account_name = "stterraformstate"
#     container_name       = "tfstate"
#     key                  = "aks.terraform.tfstate"
#   }
# }
'''
    
    def _generate_versions(self) -> str:
        """Generate versions.tf."""
        return '''# Required Terraform and Provider Versions

terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
    }
    
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.47"
    }
    
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
'''
    
    def _generate_tfvars_example(self) -> str:
        """Generate terraform.tfvars.example."""
        sizing_comment = "# Values from sizing report" if self.sizing_source == "sizing_report" else "# Default values - adjust based on your sizing requirements"
        
        return f'''# {self.project_name} - Example Variables
# Copy this file to terraform.tfvars and customize values
{sizing_comment}

project_name = "{self.project_name}"
environment  = "{self.environment}"
location     = "{self.location}"

# Networking
vnet_address_space = ["{self.vnet_cidr}"]
aks_subnet_prefix  = "{self.aks_subnet_cidr}"

# Kubernetes
kubernetes_version = "{self.k8s_version}"
system_node_count  = {self.system_node_count}
system_vm_size     = "{self.system_vm_size}"

# ES Hot tier (memory-optimized for active data)
es_hot_node_count   = {self.es_hot_node_count}
es_hot_vm_size      = "{self.es_hot_vm_size}"
es_hot_disk_size_gb = {self.es_hot_disk_size_gb}

# ES Cold tier (storage-optimized for older data)
es_cold_enabled      = {"true" if self.es_cold_enabled else "false"}
es_cold_node_count   = {self.es_cold_node_count}
es_cold_vm_size      = "{self.es_cold_vm_size}"
es_cold_disk_size_gb = {self.es_cold_disk_size_gb}

# ES Frozen tier (for searchable snapshots)
es_frozen_enabled      = {"true" if self.es_frozen_enabled else "false"}
es_frozen_node_count   = {self.es_frozen_node_count}
es_frozen_vm_size      = "{self.es_frozen_vm_size}"
es_frozen_disk_size_gb = {self.es_frozen_disk_size_gb}

# ACR
acr_sku = "Standard"

# Monitoring
log_retention_days = 30

# Storage (for ES snapshots)
snapshot_storage_gb = {int(self.snapshot_storage_gb)}
'''
    
    def _generate_readme(self) -> str:
        """Generate README.md for terraform directory."""
        return f'''# {self.project_name} - Terraform Infrastructure

Terraform modules for deploying AKS infrastructure for Elasticsearch.

## Modules

| Module | Description |
|--------|-------------|
| `aks` | Azure Kubernetes Service cluster with ES-optimized node pools |
| `networking` | VNet, subnets, and NSGs |
| `storage` | Storage account for ES snapshots |
| `acr` | Azure Container Registry |
| `monitoring` | Log Analytics workspace and Azure Monitor |

## Prerequisites

1. Azure CLI installed and authenticated: `az login`
2. Terraform >= 1.5.0
3. Azure subscription with sufficient quotas

## Quick Start

```bash
# Initialize Terraform
terraform init

# Copy and customize variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# Plan the deployment
terraform plan

# Apply
terraform apply
```

## Connect to AKS

After deployment:

```bash
# Get kubeconfig
az aks get-credentials --resource-group rg-{self.project_name}-{self.environment} --name aks-{self.project_name}-{self.environment}

# Verify connection
kubectl get nodes
```

## Node Pools

| Pool | Purpose | Default VM Size | Notes |
|------|---------|-----------------|-------|
| `system` | System workloads | Standard_D2s_v5 | Runs AKS system pods |
| `eshot` | ES Hot tier | Standard_E8s_v5 | Memory-optimized for active data |
| `escold` | ES Cold tier | Standard_L8s_v3 | Storage-optimized (optional) |

## ES Snapshots

The storage module creates a blob container for ES snapshots:

1. Get storage credentials:
   ```bash
   terraform output -raw storage_primary_access_key
   ```

2. Configure ES snapshot repository in Kibana or via API

## Costs

Estimated monthly costs (West Europe, dev sizing):
- AKS system pool (3x D2s_v5): ~$200
- ES hot pool (3x E8s_v5): ~$700
- ACR Standard: ~$20
- Log Analytics: ~$50

Total: ~$1000/month (dev environment)

## Cleanup

```bash
terraform destroy
```
'''
    
    # -------------------------------------------------------------------------
    # AKS Module
    # -------------------------------------------------------------------------
    
    def _generate_aks_main(self) -> str:
        """Generate AKS module main.tf."""
        return '''# AKS Cluster Module

resource "azurerm_kubernetes_cluster" "main" {
  name                = "aks-${var.resource_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = var.resource_prefix
  kubernetes_version  = var.kubernetes_version
  
  # System node pool (required)
  default_node_pool {
    name                = "system"
    node_count          = var.system_node_count
    vm_size             = var.system_vm_size
    vnet_subnet_id      = var.vnet_subnet_id
    os_disk_size_gb     = 128
    os_disk_type        = "Managed"
    type                = "VirtualMachineScaleSets"
    enable_auto_scaling = false
    
    node_labels = {
      "node-role" = "system"
    }
    
    tags = var.tags
  }
  
  # Managed identity
  identity {
    type = "SystemAssigned"
  }
  
  # Network configuration
  network_profile {
    network_plugin    = "azure"
    network_policy    = "azure"
    load_balancer_sku = "standard"
    service_cidr      = "172.16.0.0/16"
    dns_service_ip    = "172.16.0.10"
  }
  
  # Azure Monitor integration
  oms_agent {
    log_analytics_workspace_id = var.log_analytics_workspace_id
  }
  
  tags = var.tags
}

# ES Hot tier node pool
resource "azurerm_kubernetes_cluster_node_pool" "es_hot" {
  name                  = "eshot"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = var.es_hot_vm_size
  node_count            = var.es_hot_node_count
  vnet_subnet_id        = var.vnet_subnet_id
  os_disk_size_gb       = var.es_hot_disk_size_gb
  os_disk_type          = "Managed"
  enable_auto_scaling   = false
  
  node_labels = {
    "node-role"           = "elasticsearch"
    "elasticsearch/tier"  = "hot"
  }
  
  node_taints = [
    "elasticsearch=true:NoSchedule"
  ]
  
  tags = var.tags
}

# ES Cold tier node pool (optional)
resource "azurerm_kubernetes_cluster_node_pool" "es_cold" {
  count = var.es_cold_enabled ? 1 : 0
  
  name                  = "escold"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = var.es_cold_vm_size
  node_count            = var.es_cold_node_count
  vnet_subnet_id        = var.vnet_subnet_id
  os_disk_size_gb       = var.es_cold_disk_size_gb
  os_disk_type          = "Managed"
  enable_auto_scaling   = false
  
  node_labels = {
    "node-role"           = "elasticsearch"
    "elasticsearch/tier"  = "cold"
  }
  
  node_taints = [
    "elasticsearch=true:NoSchedule"
  ]
  
  tags = var.tags
}

# ES Frozen tier node pool (optional, for searchable snapshots)
resource "azurerm_kubernetes_cluster_node_pool" "es_frozen" {
  count = var.es_frozen_enabled ? 1 : 0
  
  name                  = "esfrozen"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = var.es_frozen_vm_size
  node_count            = var.es_frozen_node_count
  vnet_subnet_id        = var.vnet_subnet_id
  os_disk_size_gb       = var.es_frozen_disk_size_gb
  os_disk_type          = "Managed"  # Use managed for cache storage
  enable_auto_scaling   = false
  
  node_labels = {
    "node-role"           = "elasticsearch"
    "elasticsearch/tier"  = "frozen"
  }
  
  node_taints = [
    "elasticsearch=true:NoSchedule"
  ]
  
  tags = var.tags
}

# ACR integration - allow AKS to pull images
resource "azurerm_role_assignment" "aks_acr_pull" {
  count = var.acr_id != "" ? 1 : 0
  
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
}
'''
    
    def _generate_aks_variables(self) -> str:
        """Generate AKS module variables.tf."""
        return '''# AKS Module Variables

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "resource_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
}

variable "vnet_subnet_id" {
  description = "Subnet ID for AKS nodes"
  type        = string
}

variable "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID for monitoring"
  type        = string
}

variable "acr_id" {
  description = "ACR ID for pull permissions"
  type        = string
  default     = ""
}

# System node pool
variable "system_node_count" {
  description = "Number of system nodes"
  type        = number
  default     = 3
}

variable "system_vm_size" {
  description = "VM size for system nodes"
  type        = string
  default     = "Standard_D2s_v5"
}

# ES Hot tier
variable "es_hot_node_count" {
  description = "Number of ES hot tier nodes"
  type        = number
  default     = 3
}

variable "es_hot_vm_size" {
  description = "VM size for ES hot tier"
  type        = string
  default     = "Standard_E8s_v5"
}

variable "es_hot_disk_size_gb" {
  description = "OS disk size for ES hot tier"
  type        = number
  default     = 256
}

# ES Cold tier
variable "es_cold_enabled" {
  description = "Enable ES cold tier node pool"
  type        = bool
  default     = false
}

variable "es_cold_node_count" {
  description = "Number of ES cold tier nodes"
  type        = number
  default     = 3
}

variable "es_cold_vm_size" {
  description = "VM size for ES cold tier"
  type        = string
  default     = "Standard_L8s_v3"
}

variable "es_cold_disk_size_gb" {
  description = "OS disk size for ES cold tier"
  type        = number
  default     = 256
}

# ES Frozen tier
variable "es_frozen_enabled" {
  description = "Enable ES frozen tier node pool"
  type        = bool
  default     = false
}

variable "es_frozen_node_count" {
  description = "Number of ES frozen tier nodes"
  type        = number
  default     = 0
}

variable "es_frozen_vm_size" {
  description = "VM size for ES frozen tier"
  type        = string
  default     = "Standard_E8s_v5"
}

variable "es_frozen_disk_size_gb" {
  description = "Cache disk size for ES frozen tier"
  type        = number
  default     = 2400
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
'''
    
    def _generate_aks_outputs(self) -> str:
        """Generate AKS module outputs.tf."""
        return '''# AKS Module Outputs

output "cluster_name" {
  description = "Name of the AKS cluster"
  value       = azurerm_kubernetes_cluster.main.name
}

output "cluster_id" {
  description = "ID of the AKS cluster"
  value       = azurerm_kubernetes_cluster.main.id
}

output "kube_config" {
  description = "Kubeconfig for the cluster"
  value       = azurerm_kubernetes_cluster.main.kube_config_raw
  sensitive   = true
}

output "kubelet_identity" {
  description = "Kubelet managed identity"
  value       = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
}

output "node_resource_group" {
  description = "Resource group for AKS nodes"
  value       = azurerm_kubernetes_cluster.main.node_resource_group
}
'''
    
    # -------------------------------------------------------------------------
    # Networking Module
    # -------------------------------------------------------------------------
    
    def _generate_networking_main(self) -> str:
        """Generate networking module main.tf."""
        return '''# Networking Module

# Virtual Network
resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.resource_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = var.vnet_address_space
  
  tags = var.tags
}

# AKS Subnet
resource "azurerm_subnet" "aks" {
  name                 = "snet-aks"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.aks_subnet_prefix]
}

# Private Endpoints Subnet
resource "azurerm_subnet" "private" {
  name                 = "snet-private"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.private_subnet_prefix]
}

# Network Security Group for AKS
resource "azurerm_network_security_group" "aks" {
  name                = "nsg-aks-${var.resource_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  
  # Allow inbound from VNet
  security_rule {
    name                       = "AllowVnetInbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "VirtualNetwork"
  }
  
  # Allow Azure Load Balancer
  security_rule {
    name                       = "AllowAzureLoadBalancer"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "*"
  }
  
  tags = var.tags
}

# Associate NSG with AKS subnet
resource "azurerm_subnet_network_security_group_association" "aks" {
  subnet_id                 = azurerm_subnet.aks.id
  network_security_group_id = azurerm_network_security_group.aks.id
}
'''
    
    def _generate_networking_variables(self) -> str:
        """Generate networking module variables.tf."""
        return '''# Networking Module Variables

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "resource_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "vnet_address_space" {
  description = "Address space for VNet"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "aks_subnet_prefix" {
  description = "CIDR for AKS subnet"
  type        = string
  default     = "10.0.0.0/20"
}

variable "private_subnet_prefix" {
  description = "CIDR for private endpoints subnet"
  type        = string
  default     = "10.0.16.0/24"
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
'''
    
    def _generate_networking_outputs(self) -> str:
        """Generate networking module outputs.tf."""
        return '''# Networking Module Outputs

output "vnet_id" {
  description = "VNet ID"
  value       = azurerm_virtual_network.main.id
}

output "vnet_name" {
  description = "VNet name"
  value       = azurerm_virtual_network.main.name
}

output "aks_subnet_id" {
  description = "AKS subnet ID"
  value       = azurerm_subnet.aks.id
}

output "private_subnet_id" {
  description = "Private endpoints subnet ID"
  value       = azurerm_subnet.private.id
}
'''
    
    # -------------------------------------------------------------------------
    # Storage Module
    # -------------------------------------------------------------------------
    
    def _generate_storage_main(self) -> str:
        """Generate storage module main.tf."""
        return '''# Storage Module (for ES Snapshots)

resource "random_string" "storage_suffix" {
  length  = 8
  special = false
  upper   = false
}

locals {
  # Calculate storage account tier based on expected capacity
  # Hot tier for <100TB, Cool for 100-500TB, consider multiple accounts for >500TB
  storage_tier = var.snapshot_storage_gb > 100000 ? "Cool" : "Hot"
  
  # ZRS recommended for production, LRS for dev
  replication_type = var.snapshot_storage_gb > 50000 ? "ZRS" : "LRS"
}

resource "azurerm_storage_account" "snapshots" {
  name                     = "st${replace(var.resource_prefix, "-", "")}${random_string.storage_suffix.result}"
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = local.replication_type
  account_kind             = "StorageV2"
  access_tier              = local.storage_tier
  
  # Security
  min_tls_version                 = "TLS1_2"
  enable_https_traffic_only       = true
  allow_nested_items_to_be_public = false
  
  blob_properties {
    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }
  
  tags = merge(var.tags, {
    "expected-capacity-gb" = tostring(var.snapshot_storage_gb)
    "storage-tier"         = local.storage_tier
  })
}

# Container for ES snapshots
resource "azurerm_storage_container" "snapshots" {
  name                  = var.snapshot_container_name
  storage_account_name  = azurerm_storage_account.snapshots.name
  container_access_type = "private"
}
'''
    
    def _generate_storage_variables(self) -> str:
        """Generate storage module variables.tf."""
        return '''# Storage Module Variables

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "resource_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "snapshot_container_name" {
  description = "Name of blob container for snapshots"
  type        = string
  default     = "elasticsearch-snapshots"
}

variable "snapshot_storage_gb" {
  description = "Expected snapshot storage size in GB (for capacity planning)"
  type        = number
  default     = 0
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
'''
    
    def _generate_storage_outputs(self) -> str:
        """Generate storage module outputs.tf."""
        return '''# Storage Module Outputs

output "storage_account_name" {
  description = "Name of the storage account"
  value       = azurerm_storage_account.snapshots.name
}

output "storage_account_id" {
  description = "ID of the storage account"
  value       = azurerm_storage_account.snapshots.id
}

output "container_name" {
  description = "Name of the snapshot container"
  value       = azurerm_storage_container.snapshots.name
}

output "primary_access_key" {
  description = "Primary access key"
  value       = azurerm_storage_account.snapshots.primary_access_key
  sensitive   = true
}

output "primary_blob_endpoint" {
  description = "Primary blob endpoint"
  value       = azurerm_storage_account.snapshots.primary_blob_endpoint
}
'''
    
    # -------------------------------------------------------------------------
    # ACR Module
    # -------------------------------------------------------------------------
    
    def _generate_acr_main(self) -> str:
        """Generate ACR module main.tf."""
        return '''# Azure Container Registry Module

resource "random_string" "acr_suffix" {
  length  = 8
  special = false
  upper   = false
}

resource "azurerm_container_registry" "main" {
  name                = "acr${replace(var.resource_prefix, "-", "")}${random_string.acr_suffix.result}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku
  admin_enabled       = true
  
  tags = var.tags
}
'''
    
    def _generate_acr_variables(self) -> str:
        """Generate ACR module variables.tf."""
        return '''# ACR Module Variables

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "resource_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "sku" {
  description = "ACR SKU"
  type        = string
  default     = "Standard"
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
'''
    
    def _generate_acr_outputs(self) -> str:
        """Generate ACR module outputs.tf."""
        return '''# ACR Module Outputs

output "acr_id" {
  description = "ID of the ACR"
  value       = azurerm_container_registry.main.id
}

output "acr_name" {
  description = "Name of the ACR"
  value       = azurerm_container_registry.main.name
}

output "login_server" {
  description = "ACR login server"
  value       = azurerm_container_registry.main.login_server
}

output "admin_username" {
  description = "ACR admin username"
  value       = azurerm_container_registry.main.admin_username
  sensitive   = true
}

output "admin_password" {
  description = "ACR admin password"
  value       = azurerm_container_registry.main.admin_password
  sensitive   = true
}
'''
    
    # -------------------------------------------------------------------------
    # Monitoring Module
    # -------------------------------------------------------------------------
    
    def _generate_monitoring_main(self) -> str:
        """Generate monitoring module main.tf."""
        return '''# Monitoring Module (Log Analytics + Azure Monitor)

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${var.resource_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  
  tags = var.tags
}

# Azure Monitor for containers solution
resource "azurerm_log_analytics_solution" "containers" {
  solution_name         = "ContainerInsights"
  location              = var.location
  resource_group_name   = var.resource_group_name
  workspace_resource_id = azurerm_log_analytics_workspace.main.id
  workspace_name        = azurerm_log_analytics_workspace.main.name
  
  plan {
    publisher = "Microsoft"
    product   = "OMSGallery/ContainerInsights"
  }
  
  tags = var.tags
}
'''
    
    def _generate_monitoring_variables(self) -> str:
        """Generate monitoring module variables.tf."""
        return '''# Monitoring Module Variables

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "resource_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "log_retention_days" {
  description = "Log retention in days"
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
'''
    
    def _generate_monitoring_outputs(self) -> str:
        """Generate monitoring module outputs.tf."""
        return '''# Monitoring Module Outputs

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID"
  value       = azurerm_log_analytics_workspace.main.id
}

output "log_analytics_workspace_name" {
  description = "Log Analytics workspace name"
  value       = azurerm_log_analytics_workspace.main.name
}

output "log_analytics_primary_key" {
  description = "Log Analytics primary key"
  value       = azurerm_log_analytics_workspace.main.primary_shared_key
  sensitive   = true
}
'''


# ------------------------------------------------------------------
# Main interface for addon loader
# ------------------------------------------------------------------

def main(
    project_name: str,
    description: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Main entry point for the addon loader.
    
    Args:
        project_name: Name of the project
        description: Project description
        context: Additional context (platform, environment, etc.)
    
    Returns:
        Dict of {filepath: content} for generated files
    """
    generator = TerraformAKSGenerator(project_name, description, context)
    return generator.generate()


if __name__ == "__main__":
    # Test generation
    files = main("test-cluster", "Production ES cluster on AKS", {
        "platform": "aks",
        "environment": "dev",
        "azure_location": "westeurope",
    })
    
    print("Generated files:")
    for filepath in sorted(files.keys()):
        print(f"  - {filepath}")
    
    print(f"\nTotal: {len(files)} files")
