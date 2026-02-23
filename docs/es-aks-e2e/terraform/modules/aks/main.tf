# AKS Cluster Module

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
