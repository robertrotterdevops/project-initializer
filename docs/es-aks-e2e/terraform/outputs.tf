# es-aks-e2e - Outputs

# -------------------------------------------------------------------------
# Resource Group
# -------------------------------------------------------------------------

output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "resource_group_id" {
  description = "ID of the resource group"
  value       = azurerm_resource_group.main.id
}

# -------------------------------------------------------------------------
# AKS
# -------------------------------------------------------------------------

output "aks_cluster_name" {
  description = "Name of the AKS cluster"
  value       = module.aks.cluster_name
}

output "aks_cluster_id" {
  description = "ID of the AKS cluster"
  value       = module.aks.cluster_id
}

output "aks_kube_config" {
  description = "Kubeconfig for AKS cluster"
  value       = module.aks.kube_config
  sensitive   = true
}

output "aks_kube_config_command" {
  description = "Azure CLI command to get kubeconfig"
  value       = "az aks get-credentials --resource-group ${azurerm_resource_group.main.name} --name ${module.aks.cluster_name}"
}

# -------------------------------------------------------------------------
# Networking
# -------------------------------------------------------------------------

output "vnet_id" {
  description = "ID of the VNet"
  value       = module.networking.vnet_id
}

output "aks_subnet_id" {
  description = "ID of the AKS subnet"
  value       = module.networking.aks_subnet_id
}

# -------------------------------------------------------------------------
# ACR
# -------------------------------------------------------------------------

output "acr_login_server" {
  description = "Login server for ACR"
  value       = module.acr.login_server
}

output "acr_admin_username" {
  description = "Admin username for ACR"
  value       = module.acr.admin_username
  sensitive   = true
}

# -------------------------------------------------------------------------
# Storage
# -------------------------------------------------------------------------

output "storage_account_name" {
  description = "Name of the storage account for ES snapshots"
  value       = module.storage.storage_account_name
}

output "snapshot_container_name" {
  description = "Name of the blob container for snapshots"
  value       = module.storage.container_name
}

output "storage_primary_access_key" {
  description = "Primary access key for storage account"
  value       = module.storage.primary_access_key
  sensitive   = true
}

# -------------------------------------------------------------------------
# Monitoring
# -------------------------------------------------------------------------

output "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace"
  value       = module.monitoring.log_analytics_workspace_id
}
