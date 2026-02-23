<!-- elastic-sizing-format: v1.0 -->
<!-- generator: elastic-sizing-app v0.6.4 -->

# Elasticsearch Sizing Report

**Health Score: 65/100** :warning:

## Inputs

- Ingest per day: **650.0 GB/day**
- Compression factor: **0.62**
- Indexed per day: **403.0 GB/day**
- Reserve: **20%**
- Total retention: **365 days**
- Workload type: **security**

## HOT Tier Calculation

| Parameter | Value |
|---|---:|
| Nr of nodes | 8 |
| Nr of replicas | 1 |
| Days in tier | 14 |
| Disk needed total (20% reserve) | 14105.0 |
| Disk needed per node (20% reserve) | 1763.12 |
| Disk per node | 1800 |
| Disk:RAM ratio | 30 |
| RAM needed per node | 58.77 |
| RAM per node | 64 |
| vCPU:RAM ratio | 0.25 |
| vCPU needed per node | 16.0 |
| vCPU per node | 16 |
| RAM total | 512 |
| vCPU total | 128 |
| Disk total (selected) | 14400 |
| Status | **OK** |

> :warning: hot: Heap: Calculated heap (32.0GB) exceeds max recommended (31.0GB). Set Xmx to 30.0GB and use remaining RAM for filesystem cache.
> :warning: hot: Heap: Heap > 30.0GB loses compressed OOPs optimization. Consider using smaller nodes or limiting heap to 30GB.

## WARM Tier Calculation

| Parameter | Value |
|---|---:|
| Nr of nodes | 11 |
| Nr of replicas | 1 |
| Days in tier | 30 |
| Disk needed total (20% reserve) | 30225.0 |
| Disk needed per node (20% reserve) | 2747.73 |
| Disk per node | 3000 |
| Disk:RAM ratio | 100 |
| RAM needed per node | 27.48 |
| RAM per node | 48 |
| vCPU:RAM ratio | 0.25 |
| vCPU needed per node | 12.0 |
| vCPU per node | 12 |
| RAM total | 528 |
| vCPU total | 132 |
| Disk total (selected) | 33000 |
| Status | **OK** |

> :warning: warm: Instance check: selected per-node RAM/disk exceed lightweight catalog; verify SKU / storage class.

## COLD Tier Calculation

| Parameter | Value |
|---|---:|
| Nr of nodes | 200 |
| Nr of replicas | 0 |
| Days in tier | 120 |
| Disk needed total (20% reserve) | 60450.0 |
| Disk needed per node (20% reserve) | 302.25 |
| Disk per node | 5000 |
| Disk:RAM ratio | 100 |
| RAM needed per node | 3.02 |
| RAM per node | 64 |
| vCPU:RAM ratio | 0.2 |
| vCPU needed per node | 13.0 |
| vCPU per node | 12 |
| RAM total | 12800 |
| vCPU total | 2400 |
| Disk total (selected) | 1000000 |
| Status | **FAIL** |

> :warning: cold: Heap: Calculated heap (32.0GB) exceeds max recommended (31.0GB). Set Xmx to 30.0GB and use remaining RAM for filesystem cache.
> :warning: cold: Heap: Heap > 30.0GB loses compressed OOPs optimization. Consider using smaller nodes or limiting heap to 30GB.
> :warning: cold: Instance check: selected per-node RAM/disk exceed lightweight catalog; verify SKU / storage class.

## FROZEN Tier Calculation

*Searchable snapshots tier with different parameters*

| Parameter | Value |
|---|---:|
| Nr of nodes | 3 |
| Days in frozen | 201 |
| Snapshot repo storage (GB) | 101253.75 |
| Snapshot:RAM ratio | 1600.0 |
| RAM needed per node (GB) | 21.09 |
| RAM per node (GB) | 32 |
| Cache Disk:RAM ratio | 75.0 |
| Cache disk needed per node (GB) | 3000.0 |
| Cache disk per node (GB) | 2400.0 |
| vCPU:RAM ratio | 0.133 |
| vCPU needed per node | 5.0 |
| vCPU per node | 8 |
| RAM total (GB) | 96 |
| vCPU total | 24 |
| Status | **OK** |

## Cluster Topology

### Master Nodes
- Nodes: **7**
- RAM per node: **8.0 GB**
- vCPU per node: **4.0**

### Coordinator Nodes
- Nodes: **5**
- RAM per node: **16.0 GB**
- vCPU per node: **8.0**

- Availability Zones: **3**

## JVM Configuration

Per-node JVM heap settings (50% of RAM, max 30GB for compressed OOPs):

### HOT Tier
- Nodes: **8**
- RAM per node: **64.0 GB**
- Heap per node: **30 GB**
- JVM options: `Xms30g Xmx30g`
- :warning: Heap capped at 30GB (compressed OOPs limit)

### WARM Tier
- Nodes: **11**
- RAM per node: **48.0 GB**
- Heap per node: **24 GB**
- JVM options: `Xms24g Xmx24g`

### COLD Tier
- Nodes: **200**
- RAM per node: **64.0 GB**
- Heap per node: **30 GB**
- JVM options: `Xms30g Xmx30g`
- :warning: Heap capped at 30GB (compressed OOPs limit)

### FROZEN Tier
- Nodes: **3**
- RAM per node: **32.0 GB**
- Heap per node: **16 GB**
- JVM options: `Xms16g Xmx16g`

## Shard Analysis

- Total primary shards: **2204**
- Total shards (with replicas): **2796**
- Average shard size: **66.74 GB**
- Shards per node: **12.6**

## Capacity Utilization

- Hot tier: **98.0%**
- Warm tier: **91.6%**
- Cold tier: **6.0%**

## Summary

- Overall OK: **False**
- Total nodes: **234**
  - Data nodes: 222
  - Master nodes: 7
  - Coordinator nodes: 5
- Total vCPU (selected): **2752.0**
- Total RAM GB (selected): **14072.0**
- Total local disk GB (selected): **1054600.0**
- Total snapshot storage GB: **1148653.75**

## Enterprise Resource Units (ERU)

- **ERU: 220**
- Calculation: `ROUNDUP(14072.00 / 64) = 220`
- Formula: `ERU = ROUNDUP(Total RAM GB / 64)`

## Warnings

- :warning: cold: Heap: Calculated heap (32.0GB) exceeds max recommended (31.0GB). Set Xmx to 30.0GB and use remaining RAM for filesystem cache.
- :warning: cold: Heap: Heap > 30.0GB loses compressed OOPs optimization. Consider using smaller nodes or limiting heap to 30GB.
- :warning: cold: Instance check: selected per-node RAM/disk exceed lightweight catalog; verify SKU / storage class.

## Recommendations

- :bulb: SECURITY workloads can leverage ML nodes for anomaly detection.

## Stack Components

### Kibana

| Parameter | Value |
|---|---:|
| Instances | 4 |
| RAM per instance (GB) | 18.0 |
| vCPU per instance | 10.0 |
| Total RAM (GB) | 72.0 |
| Total vCPU | 40.0 |

> Enterprise deployment: 4 Kibana instances for 120 concurrent users
> Added 2GB RAM per instance for 1500 alerting rules
> Added 2 vCPU per instance for PDF/CSV reporting

### Fleet Server

| Parameter | Value |
|---|---:|
| Instances | 3 |
| RAM per instance (GB) | 24.0 |
| vCPU per instance | 12.0 |
| Total RAM (GB) | 72.0 |
| Total vCPU | 36.0 |

> Enterprise Fleet deployment: 3 instances for 18000 agents
> Increased resources for 30s check-in interval (aggressive)

### Stack Totals

- Total Stack RAM: **144.0 GB**
- Total Stack vCPU: **76.0**

## OpenShift/ECK Deployment

### Input Parameters

| Parameter | Value |
|---|---:|
| Hot Pool Worker | 16 vCPU / 64 GB RAM |
| Cold Pool Worker | 16 vCPU / 64 GB RAM |
| System Pool Worker | 8 vCPU / 32 GB RAM |
| Headroom | 25% |
| Availability Zones | 3 |

### Worker Pools

| Pool | Pods | Workers | Per Zone | vCPU/worker | RAM/worker (GB) |
|---|---:|---:|---|---:|---:|
| Hot Pool | 26 | 27 | 9/9/9 | 16 | 64 |
| Cold Pool | 203 | 204 | 68/68/68 | 16 | 64 |
| System Pool | 12 | 12 | 4/4/4 | 8 | 32 |
| **Total** | **241** | **243** | - | - | - |

### Worker Configuration

| Pool | vCPU | RAM (GB) | Proposed MachineSet |
|---|---:|---:|---|
| Hot Pool | 16 | 64 | es-hot-worker-{az1,az2,az3} |
| Cold Pool | 16 | 64 | es-cold-worker-{az1,az2,az3} |
| System Pool | 8 | 32 | es-system-worker-{az1,az2,az3} |

### Pool Composition

| Pool | Composition | Requested CPU | Requested RAM (GB) |
|---|---|---:|---:|
| Hot Pool | hot:8, warm:11, kibana:4, fleet:3 | 336.0 | 1184.0 |
| Cold Pool | cold:200, frozen:3 | 2424.0 | 12896.0 |
| System Pool | master:7, coord:5 | 68.0 | 136.0 |

### Total OpenShift Resources

- Total Workers: **243**
- Total vCPU: **3792**
- Total RAM: **15168 GB**
- Snapshot Storage: **1148653.75 GB**

### Notes

> Hot pool: hot+warm+ingest data nodes + Kibana + Fleet
> Cold pool: cold+frozen data nodes
> System pool: master + coordinator + ML nodes (isolated for stability)
> Headroom: 25% reserved for OS/kubelet/monitoring
> Bin-packing uses First-Fit Decreasing algorithm
> System pool includes 7 master node(s)
> System pool includes 5 coordinator node(s)

---

### References

- [Shard Sizing Best Practices](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/size-shards)
- [Cluster Sizing Guide](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/sizing)
- [Elasticsearch Reference](https://www.elastic.co/docs/reference/elasticsearch)
- [ECK Documentation](https://www.elastic.co/docs/deploy-manage/deploy/cloud-on-k8s)

---

*This tool provides estimates based on Elastic best practices. Actual requirements may vary based on workload characteristics, query patterns, and specific use cases. Always validate with production testing.*
