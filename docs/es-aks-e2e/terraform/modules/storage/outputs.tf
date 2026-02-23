# Storage Module Outputs

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
