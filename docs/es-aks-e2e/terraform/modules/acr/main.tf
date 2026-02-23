# Azure Container Registry Module

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
