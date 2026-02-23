# AKS Module Variables

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
