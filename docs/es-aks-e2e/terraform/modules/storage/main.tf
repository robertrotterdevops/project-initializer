# Storage Module (for ES Snapshots)

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
