# Platform Configuration: AKS + ECK

## Overview

Platform-specific configurations for deploying es-aks-e2e on Azure Kubernetes Service.

## Files

- `storage-class.yaml - Azure managed disks`
- `managed-identity.yaml - Workload Identity`
- `ingress.yaml - Application Gateway/nginx`
- `terraform-example.tf - Node pool Terraform`

## Prerequisites

### AKS + ECK

See individual files for specific requirements.

## Usage

Apply platform-specific resources before deploying Elasticsearch:

```bash
kubectl apply -f platform/aks/
```

Then deploy the main Elasticsearch cluster:

```bash
kubectl apply -k elasticsearch/
```
