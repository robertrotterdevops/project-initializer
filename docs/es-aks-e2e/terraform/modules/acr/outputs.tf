# ACR Module Outputs

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
