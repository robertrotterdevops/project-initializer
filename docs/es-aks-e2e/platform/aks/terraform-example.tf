# Terraform example: Dedicated Elasticsearch node pool for AKS
# Add to your AKS Terraform configuration

resource "azurerm_kubernetes_cluster_node_pool" "elasticsearch" {
  name                  = "esdata"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = "Standard_E8s_v4"  # 8 vCPU, 64 GB RAM
  node_count            = 3
  
  # Enable auto-scaling (optional)
  enable_auto_scaling = true
  min_count           = 3
  max_count           = 6
  
  # Availability zones for HA
  zones = ["1", "2", "3"]
  
  # Node labels
  node_labels = {
    "workload"                         = "elasticsearch"
    "es-aks-e2e-node"         = "true"
    "node.kubernetes.io/instance-type" = "Standard_E8s_v4"
  }
  
  # Taints to dedicate nodes
  node_taints = [
    "elasticsearch=true:NoSchedule"
  ]
  
  # OS disk
  os_disk_size_gb = 128
  os_disk_type    = "Managed"
  
  # Ultra SSD (for data disks via PVC)
  ultra_ssd_enabled = true
  
  tags = {
    Environment = "production"
    Project     = "es-aks-e2e"
  }
}

# Output the node pool details
output "elasticsearch_node_pool_id" {
  value = azurerm_kubernetes_cluster_node_pool.elasticsearch.id
}
