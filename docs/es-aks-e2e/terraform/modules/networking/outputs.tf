# Networking Module Outputs

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
