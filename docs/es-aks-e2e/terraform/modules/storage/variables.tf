# Storage Module Variables

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
