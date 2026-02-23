# es-aks-e2e - Terraform Infrastructure

Terraform modules for deploying AKS infrastructure for Elasticsearch.

## Modules

| Module | Description |
|--------|-------------|
| `aks` | Azure Kubernetes Service cluster with ES-optimized node pools |
| `networking` | VNet, subnets, and NSGs |
| `storage` | Storage account for ES snapshots |
| `acr` | Azure Container Registry |
| `monitoring` | Log Analytics workspace and Azure Monitor |

## Prerequisites

1. Azure CLI installed and authenticated: `az login`
2. Terraform >= 1.5.0
3. Azure subscription with sufficient quotas

## Quick Start

```bash
# Initialize Terraform
terraform init

# Copy and customize variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# Plan the deployment
terraform plan

# Apply
terraform apply
```

## Connect to AKS

After deployment:

```bash
# Get kubeconfig
az aks get-credentials --resource-group rg-es-aks-e2e-dev --name aks-es-aks-e2e-dev

# Verify connection
kubectl get nodes
```

## Node Pools

| Pool | Purpose | Default VM Size | Notes |
|------|---------|-----------------|-------|
| `system` | System workloads | Standard_D2s_v5 | Runs AKS system pods |
| `eshot` | ES Hot tier | Standard_E8s_v5 | Memory-optimized for active data |
| `escold` | ES Cold tier | Standard_L8s_v3 | Storage-optimized (optional) |

## ES Snapshots

The storage module creates a blob container for ES snapshots:

1. Get storage credentials:
   ```bash
   terraform output -raw storage_primary_access_key
   ```

2. Configure ES snapshot repository in Kibana or via API

## Costs

Estimated monthly costs (West Europe, dev sizing):
- AKS system pool (3x D2s_v5): ~$200
- ES hot pool (3x E8s_v5): ~$700
- ACR Standard: ~$20
- Log Analytics: ~$50

Total: ~$1000/month (dev environment)

## Cleanup

```bash
terraform destroy
```
