# es-aks-e2e - Variables
# Generated from sizing report

# -------------------------------------------------------------------------
# Project
# -------------------------------------------------------------------------

variable "project_name" {
  description = "Name of the project (used in resource naming)"
  type        = string
  default     = "es-aks-e2e"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
  
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "westeurope"
}

# -------------------------------------------------------------------------
# Networking
# -------------------------------------------------------------------------

variable "vnet_address_space" {
  description = "Address space for the VNet"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "aks_subnet_prefix" {
  description = "CIDR prefix for AKS subnet"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnet_prefix" {
  description = "CIDR prefix for private endpoints"
  type        = string
  default     = "10.0.240.0/24"
}

# -------------------------------------------------------------------------
# Kubernetes
# -------------------------------------------------------------------------

variable "kubernetes_version" {
  description = "Kubernetes version for AKS"
  type        = string
  default     = "1.30"
}

variable "system_node_count" {
  description = "Number of nodes in the system node pool"
  type        = number
  default     = 12
}

variable "system_vm_size" {
  description = "VM size for system node pool"
  type        = string
  default     = "Standard_D8s_v5"
}

# -------------------------------------------------------------------------
# Elasticsearch Node Pools
# -------------------------------------------------------------------------

# Hot tier
variable "es_hot_node_count" {
  description = "Number of nodes in the ES hot tier pool"
  type        = number
  default     = 27
}

variable "es_hot_vm_size" {
  description = "VM size for ES hot tier (memory-optimized recommended)"
  type        = string
  default     = "Standard_E16s_v5"
}

variable "es_hot_disk_size_gb" {
  description = "OS disk size for ES hot tier nodes"
  type        = number
  default     = 512
}

# Cold tier
variable "es_cold_enabled" {
  description = "Enable ES cold tier node pool"
  type        = bool
  default     = true
}

variable "es_cold_node_count" {
  description = "Number of nodes in the ES cold tier pool"
  type        = number
  default     = 201
}

variable "es_cold_vm_size" {
  description = "VM size for ES cold tier (storage-optimized)"
  type        = string
  default     = "Standard_L16s_v3"
}

variable "es_cold_disk_size_gb" {
  description = "OS disk size for ES cold tier nodes"
  type        = number
  default     = 1024
}

# Frozen tier
variable "es_frozen_enabled" {
  description = "Enable ES frozen tier node pool"
  type        = bool
  default     = true
}

variable "es_frozen_node_count" {
  description = "Number of nodes in the ES frozen tier pool"
  type        = number
  default     = 3
}

variable "es_frozen_vm_size" {
  description = "VM size for ES frozen tier (memory-optimized for cache)"
  type        = string
  default     = "Standard_E8s_v5"
}

variable "es_frozen_disk_size_gb" {
  description = "Cache disk size for ES frozen tier nodes"
  type        = number
  default     = 256
}

# -------------------------------------------------------------------------
# Container Registry
# -------------------------------------------------------------------------

variable "acr_sku" {
  description = "SKU for Azure Container Registry"
  type        = string
  default     = "Standard"
  
  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.acr_sku)
    error_message = "ACR SKU must be Basic, Standard, or Premium."
  }
}

# -------------------------------------------------------------------------
# Monitoring
# -------------------------------------------------------------------------

variable "log_retention_days" {
  description = "Log Analytics workspace retention in days"
  type        = number
  default     = 30
}

# -------------------------------------------------------------------------
# Storage
# -------------------------------------------------------------------------

variable "snapshot_container_name" {
  description = "Name of the blob container for ES snapshots"
  type        = string
  default     = "elasticsearch-snapshots"
}

variable "snapshot_storage_gb" {
  description = "Expected snapshot storage size in GB (for capacity planning)"
  type        = number
  default     = 1148653
}
