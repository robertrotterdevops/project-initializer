# Elasticsearch Cluster: es-ocp-e2e

## Overview

ECK-managed Elasticsearch cluster with the following components:
- **Elasticsearch 8.17.0**: 218 nodes (multi-tier architecture)
- **Kibana 8.17.0**: 4 instance(s) for visualization
- **Elastic Agent**: Fleet-managed for log/metric collection

## Sizing Source

This cluster was sized using the **elasticsearch-openshift-sizing-assistant**.
- **Health Score**: 65/100
- **Profile**: Multi-tier (Hot/Cold/Frozen)

## Prerequisites

1. ECK Operator installed (v2.16.0+):
   ```bash
   kubectl create -f https://download.elastic.co/downloads/eck/2.16.0/crds.yaml
   kubectl apply -f https://download.elastic.co/downloads/eck/2.16.0/operator.yaml
   ```

2. Storage classes available:
   - `premium` for hot tier
   - `standard` for cold/frozen tiers

## Deployment

```bash
# Apply all manifests
kubectl apply -k elasticsearch/

# Or apply individually
kubectl apply -f elasticsearch/namespace.yaml
kubectl apply -f elasticsearch/cluster.yaml
kubectl apply -f elasticsearch/kibana.yaml
kubectl apply -f elasticsearch/agent.yaml
```

## Access

### Get Elasticsearch password
```bash
kubectl get secret es-ocp-e2e-es-elastic-user -n es-ocp-e2e -o jsonpath='{{.data.elastic}}' | base64 -d
```

### Port-forward Elasticsearch
```bash
kubectl port-forward svc/es-ocp-e2e-es-http -n es-ocp-e2e 9200:9200
```

### Port-forward Kibana
```bash
kubectl port-forward svc/es-ocp-e2e-kb-http -n es-ocp-e2e 5601:5601
```

## Node Configuration

| Component | Count | Memory | CPU | Storage |
|-----------|-------|--------|-----|---------|
| Master nodes | 7 | 8Gi | 4 | - |
| Hot tier | 8 | 64Gi | 16 | 1800Gi |
| Cold tier | 200 | 64Gi | 12 | 5000Gi |
| Frozen tier | 3 | 32Gi | 8 | 2400Gi (cache) |
| Kibana | 4 | 18Gi | 10 | - |

## ILM Policies

The `hot-cold-frozen` policy is included for log lifecycle management:
- Hot: 0-7 days (rollover at 1d or 50GB)
- Cold: 7-30 days (allocate to cold nodes, read-only)
- Frozen: 30-365 days (searchable snapshots)
- Delete: 365+ days

Apply with:
```bash
curl -X PUT "https://localhost:9200/_ilm/policy/hot-cold-frozen" \
  -H "Content-Type: application/json" \
  -u "elastic:$PASSWORD" \
  -d @elasticsearch/ilm-policies/hot-cold-frozen.json
```
