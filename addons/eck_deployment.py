#!/usr/bin/env python3
"""
ECK 2.x (Elasticsearch 8.x) deployment addon for project-initializer.
Generates Elasticsearch, Kibana, and Elastic Agent manifests using ECK CRDs.

Supports multi-tier deployments (hot/cold/frozen) when sizing context is provided.

Zero external dependencies -- Python 3.9+ stdlib only.
"""

from typing import Any, Dict, Optional


ADDON_META = {
    "name": "eck_deployment",
    "version": "1.1",
    "description": "ECK 2.x deployment generator for Elasticsearch 8.x (multi-tier support)",
    "triggers": {"categories": ["elasticsearch"]},
    "priority": 20,
}


class ECKDeploymentGenerator:
    """Generates ECK manifests for Elasticsearch cluster deployment."""

    def __init__(
        self,
        project_name: str,
        project_description: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.project_name = project_name
        self.description = project_description
        self.context = context or {}

        # Extract sizing context if available (handle None explicitly)
        self.sizing = self.context.get("sizing_context") or {}
        self.platform = self.context.get("platform", "kubernetes")

        # Check if this is a multi-tier deployment from sizing report
        self.is_multi_tier = self.sizing.get("source") == "sizing_report"

        # Default sizing (can be overridden by sizing_context)
        self.data_nodes = self.sizing.get(
            "data_nodes",
            {
                "count": 3,
                "memory": "8Gi",
                "cpu": "2",
                "storage": "100Gi",
                "storage_class": "standard",
            },
        )
        self.master_nodes = self.sizing.get(
            "master_nodes",
            {
                "count": 3,
                "memory": "2Gi",
                "cpu": "1",
            },
        )

        # Multi-tier nodes (from sizing report)
        self.cold_nodes = self.sizing.get("cold_nodes")
        self.frozen_nodes = self.sizing.get("frozen_nodes")

        # Kibana and Fleet from sizing
        self.kibana_config = self.sizing.get(
            "kibana",
            {
                "count": 1,
                "memory": "2Gi",
                "cpu": "1",
            },
        )
        self.fleet_config = self.sizing.get(
            "fleet_server",
            {
                "count": 1,
                "memory": "1Gi",
                "cpu": "500m",
            },
        )

        # ES version
        self.es_version = "8.17.0"
        self.eck_operator = self.sizing.get("eck_operator") or {}
        self.eck_version = self.eck_operator.get("version", "2.16.0")

    def generate(self) -> Dict[str, str]:
        """Generate all ECK manifests."""
        files = {}

        # ECK operator manifests (Flux-managed)
        files["platform/eck-operator/operator.yaml"] = (
            self._generate_eck_operator_manifest()
        )
        files["platform/eck-operator/kustomization.yaml"] = (
            self._generate_eck_operator_kustomization()
        )
        files["platform/eck-operator/README.md"] = self._generate_eck_operator_readme()

        # Shared namespace for ES components
        files["elasticsearch/namespace.yaml"] = self._generate_namespace()

        # Elasticsearch cluster manifest
        files["elasticsearch/cluster.yaml"] = self._generate_elasticsearch()
        files["elasticsearch/README.md"] = self._generate_readme()
        files["elasticsearch/kustomization.yaml"] = self._generate_es_kustomization()

        # Kibana in its own folder
        files["kibana/kibana.yaml"] = self._generate_kibana()
        files["kibana/kustomization.yaml"] = self._generate_kibana_kustomization()

        # Agents in their own folder
        files["agents/fleet-server.yaml"] = self._generate_fleet_server()
        files["agents/elastic-agent.yaml"] = self._generate_agent()
        files["agents/rbac.yaml"] = self._generate_agent_rbac()
        files["agents/kustomization.yaml"] = self._generate_agents_kustomization()

        # ILM policies - use multi-tier if configured
        if self.is_multi_tier:
            files["elasticsearch/ilm-policies/hot-cold-frozen.json"] = (
                self._generate_multi_tier_ilm_policy()
            )
        else:
            files["elasticsearch/ilm-policies/hot-warm-cold.json"] = (
                self._generate_ilm_policy()
            )

        # Index templates
        files["elasticsearch/index-templates/logs-template.json"] = (
            self._generate_index_template()
        )

        return files

        return files

    def _generate_eck_operator_manifest(self) -> str:
        """Return ECK operator manifest from sizing export or fallback default."""
        operator_yaml = self.eck_operator.get("yaml")
        if operator_yaml:
            return (
                operator_yaml if operator_yaml.endswith("\n") else operator_yaml + "\n"
            )

        # Fallback to official upstream manifest reference content
        return f"""# Fallback ECK operator manifest
# Source: https://download.elastic.co/downloads/eck/{self.eck_version}/operator.yaml
# This file is intentionally minimal when sizing export did not include embedded operator YAML.
apiVersion: v1
kind: Namespace
metadata:
  name: elastic-system
"""

    def _generate_eck_operator_kustomization(self) -> str:
        """Generate Flux-friendly kustomization for ECK operator + CRDs."""
        return f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - https://download.elastic.co/downloads/eck/{self.eck_version}/crds.yaml
  - operator.yaml
"""

    def _generate_eck_operator_readme(self) -> str:
        """Generate ECK operator deployment notes."""
        namespace = self.eck_operator.get("namespace", "elastic-system")
        return f"""# ECK Operator

This directory contains Flux-managed ECK operator resources.

- Version: `{self.eck_version}`
- Namespace: `{namespace}`

Deploy order:
1. CRDs (`crds.yaml` via remote URL)
2. Operator (`operator.yaml`)

Validate:
```bash
kubectl get crd | grep k8s.elastic.co
kubectl -n {namespace} get pods
```
"""

    def _generate_namespace(self) -> str:
        """Generate namespace manifest."""
        return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
    app.kubernetes.io/component: elasticsearch
    app.kubernetes.io/managed-by: eck
"""

    def _generate_elasticsearch(self) -> str:
        """Generate Elasticsearch cluster CRD.

        When no sizing report is provided (is_multi_tier=False), generates a
        template with hot tier active and warm/cold/frozen tiers commented out
        as examples that users can uncomment and customize.
        """
        # Platform-specific annotations
        annotations = ""
        if self.platform == "openshift":
            annotations = """  annotations:
    # OpenShift: Allow ECK to manage security context
    eck.k8s.elastic.co/downward-node-labels: "topology.kubernetes.io/zone"
"""

        # Build nodesets
        nodesets = []

        # Master nodes (dedicated)
        nodesets.append(self._generate_master_nodeset())

        # Hot tier (data nodes) - always active
        nodesets.append(self._generate_hot_nodeset())

        if self.is_multi_tier:
            # Multi-tier from sizing report - add configured tiers
            if self.cold_nodes:
                nodesets.append(self._generate_cold_nodeset())
            if self.frozen_nodes:
                nodesets.append(self._generate_frozen_nodeset())
        else:
            # Default template - add commented warm/cold/frozen examples
            nodesets.append(self._generate_commented_warm_nodeset())
            nodesets.append(self._generate_commented_cold_nodeset())
            nodesets.append(self._generate_commented_frozen_nodeset())

        nodesets_yaml = "\n".join(nodesets)

        return f"""apiVersion: elasticsearch.k8s.elastic.co/v1
kind: Elasticsearch
metadata:
  name: {self.project_name}
  namespace: {self.project_name}
{annotations}  labels:
    app.kubernetes.io/name: {self.project_name}
    app.kubernetes.io/component: elasticsearch
spec:
  version: {self.es_version}
  
  # HTTP configuration
  http:
    tls:
      selfSignedCertificate:
        disabled: false
  
  # Node sets
  nodeSets:
{nodesets_yaml}
"""

    def _generate_master_nodeset(self) -> str:
        """Generate master node set configuration."""
        count = self.master_nodes.get("count", 3)
        memory = self.master_nodes.get("memory", "2Gi")
        cpu = self.master_nodes.get("cpu", "1")

        # Calculate limits (2x requests for CPU)
        cpu_request = cpu.replace("m", "") if "m" in str(cpu) else str(int(cpu) * 1000)
        cpu_limit = (
            str(int(cpu_request.replace("m", "")) * 2) + "m"
            if cpu_request.endswith("m") or "m" not in cpu_request
            else cpu_request
        )
        if not cpu_limit.endswith("m"):
            cpu_limit = str(int(cpu) * 2)

        return f"""    # Master nodes (dedicated)
    - name: master
      count: {count}
      config:
        node.roles: ["master"]
        # Disable machine learning on master nodes
        xpack.ml.enabled: false
      podTemplate:
        spec:
          containers:
            - name: elasticsearch
              resources:
                requests:
                  memory: {memory}
                  cpu: "{cpu}"
                limits:
                  memory: {memory}
                  cpu: "{cpu_limit}"
          initContainers:
            - name: sysctl
              securityContext:
                privileged: true
                runAsUser: 0
              command: ['sh', '-c', 'sysctl -w vm.max_map_count=262144']"""

    def _generate_hot_nodeset(self) -> str:
        """Generate hot tier node set configuration."""
        count = self.data_nodes.get("count", 3)
        memory = self.data_nodes.get("memory", "8Gi")
        cpu = self.data_nodes.get("cpu", "2")
        storage = self.data_nodes.get("storage", "100Gi")
        storage_class = self.data_nodes.get("storage_class", "premium")

        # Hot tier gets premium storage
        if storage_class == "standard" and self.is_multi_tier:
            storage_class = "premium"

        # Calculate limits
        cpu_limit = str(int(cpu) * 2) if cpu.isdigit() else cpu

        # Affinity for zone spread
        affinity = ""
        if count >= 3:
            affinity = f"""
          affinity:
            podAntiAffinity:
              preferredDuringSchedulingIgnoredDuringExecution:
                - weight: 100
                  podAffinityTerm:
                    labelSelector:
                      matchLabels:
                        elasticsearch.k8s.elastic.co/cluster-name: {self.project_name}
                        elasticsearch.k8s.elastic.co/node-data: "true"
                    topologyKey: topology.kubernetes.io/zone"""

        return f"""
    # Hot tier - data nodes (ingest, recent data)
    - name: hot
      count: {count}
      config:
        node.roles: ["data_hot", "data_content", "ingest", "transform"]
        # Hot tier node attributes
        node.attr.data: hot
      podTemplate:
        spec:
          containers:
            - name: elasticsearch
              resources:
                requests:
                  memory: {memory}
                  cpu: "{cpu}"
                limits:
                  memory: {memory}
                  cpu: "{cpu_limit}"
          initContainers:
            - name: sysctl
              securityContext:
                privileged: true
                runAsUser: 0
              command: ['sh', '-c', 'sysctl -w vm.max_map_count=262144']{affinity}
      volumeClaimTemplates:
        - metadata:
            name: elasticsearch-data
          spec:
            accessModes:
              - ReadWriteOnce
            resources:
              requests:
                storage: {storage}
            storageClassName: {storage_class}"""

    def _generate_cold_nodeset(self) -> str:
        """Generate cold tier node set configuration."""
        if not self.cold_nodes:
            return ""

        count = self.cold_nodes.get("count", 3)
        memory = self.cold_nodes.get("memory", "16Gi")
        cpu = self.cold_nodes.get("cpu", "4")
        storage = self.cold_nodes.get("storage", "2000Gi")
        storage_class = self.cold_nodes.get("storage_class", "standard")

        cpu_limit = str(int(cpu) * 2) if cpu.isdigit() else cpu

        return f"""
    # Cold tier - older data, less frequent access
    - name: cold
      count: {count}
      config:
        node.roles: ["data_cold"]
        # Cold tier node attributes
        node.attr.data: cold
      podTemplate:
        spec:
          containers:
            - name: elasticsearch
              resources:
                requests:
                  memory: {memory}
                  cpu: "{cpu}"
                limits:
                  memory: {memory}
                  cpu: "{cpu_limit}"
          initContainers:
            - name: sysctl
              securityContext:
                privileged: true
                runAsUser: 0
              command: ['sh', '-c', 'sysctl -w vm.max_map_count=262144']
      volumeClaimTemplates:
        - metadata:
            name: elasticsearch-data
          spec:
            accessModes:
              - ReadWriteOnce
            resources:
              requests:
                storage: {storage}
            storageClassName: {storage_class}"""

    def _generate_frozen_nodeset(self) -> str:
        """Generate frozen tier node set configuration."""
        if not self.frozen_nodes:
            return ""

        count = self.frozen_nodes.get("count", 1)
        memory = self.frozen_nodes.get("memory", "32Gi")
        cpu = self.frozen_nodes.get("cpu", "8")
        cache_storage = self.frozen_nodes.get("cache_storage", "2400Gi")

        cpu_limit = str(int(cpu) * 2) if cpu.isdigit() else cpu

        return f"""
    # Frozen tier - searchable snapshots, minimal local cache
    - name: frozen
      count: {count}
      config:
        node.roles: ["data_frozen"]
        # Frozen tier node attributes
        node.attr.data: frozen
        # Searchable snapshots cache
        xpack.searchable.snapshot.shared_cache.size: 90%
      podTemplate:
        spec:
          containers:
            - name: elasticsearch
              resources:
                requests:
                  memory: {memory}
                  cpu: "{cpu}"
                limits:
                  memory: {memory}
                  cpu: "{cpu_limit}"
          initContainers:
            - name: sysctl
              securityContext:
                privileged: true
                runAsUser: 0
              command: ['sh', '-c', 'sysctl -w vm.max_map_count=262144']
      volumeClaimTemplates:
        - metadata:
            name: elasticsearch-data
          spec:
            accessModes:
              - ReadWriteOnce
            resources:
              requests:
                storage: {cache_storage}
            storageClassName: standard"""

    def _generate_commented_warm_nodeset(self) -> str:
        """Generate commented warm tier node set as template example."""
        return f"""
    # =========================================================================
    # WARM TIER (Optional) - Uncomment to enable
    # Use for data that is queried less frequently (7-30 days old typically)
    # =========================================================================
    # - name: warm
    #   count: 3
    #   config:
    #     node.roles: ["data_warm"]
    #     node.attr.data: warm
    #   podTemplate:
    #     spec:
    #       containers:
    #         - name: elasticsearch
    #           resources:
    #             requests:
    #               memory: 16Gi
    #               cpu: "4"
    #             limits:
    #               memory: 16Gi
    #               cpu: "8"
    #       initContainers:
    #         - name: sysctl
    #           securityContext:
    #             privileged: true
    #             runAsUser: 0
    #           command: ['sh', '-c', 'sysctl -w vm.max_map_count=262144']
    #   volumeClaimTemplates:
    #     - metadata:
    #         name: elasticsearch-data
    #       spec:
    #         accessModes:
    #           - ReadWriteOnce
    #         resources:
    #           requests:
    #             storage: 1000Gi
    #         storageClassName: standard"""

    def _generate_commented_cold_nodeset(self) -> str:
        """Generate commented cold tier node set as template example."""
        return f"""
    # =========================================================================
    # COLD TIER (Optional) - Uncomment to enable
    # Use for data that is rarely queried (30-90 days old typically)
    # Lower storage cost, higher storage:RAM ratio
    # =========================================================================
    # - name: cold
    #   count: 3
    #   config:
    #     node.roles: ["data_cold"]
    #     node.attr.data: cold
    #   podTemplate:
    #     spec:
    #       containers:
    #         - name: elasticsearch
    #           resources:
    #             requests:
    #               memory: 16Gi
    #               cpu: "4"
    #             limits:
    #               memory: 16Gi
    #               cpu: "8"
    #       initContainers:
    #         - name: sysctl
    #           securityContext:
    #             privileged: true
    #             runAsUser: 0
    #           command: ['sh', '-c', 'sysctl -w vm.max_map_count=262144']
    #   volumeClaimTemplates:
    #     - metadata:
    #         name: elasticsearch-data
    #       spec:
    #         accessModes:
    #           - ReadWriteOnce
    #         resources:
    #           requests:
    #             storage: 2000Gi
    #         storageClassName: standard"""

    def _generate_commented_frozen_nodeset(self) -> str:
        """Generate commented frozen tier node set as template example."""
        return f"""
    # =========================================================================
    # FROZEN TIER (Optional) - Uncomment to enable
    # Use for archival data with searchable snapshots (90+ days typically)
    # Requires snapshot repository (S3/GCS/Azure Blob) configured
    # =========================================================================
    # - name: frozen
    #   count: 1
    #   config:
    #     node.roles: ["data_frozen"]
    #     node.attr.data: frozen
    #     # Searchable snapshots local cache
    #     xpack.searchable.snapshot.shared_cache.size: 90%
    #   podTemplate:
    #     spec:
    #       containers:
    #         - name: elasticsearch
    #           resources:
    #             requests:
    #               memory: 32Gi
    #               cpu: "8"
    #             limits:
    #               memory: 32Gi
    #               cpu: "16"
    #       initContainers:
    #         - name: sysctl
    #           securityContext:
    #             privileged: true
    #             runAsUser: 0
    #           command: ['sh', '-c', 'sysctl -w vm.max_map_count=262144']
    #   volumeClaimTemplates:
    #     - metadata:
    #         name: elasticsearch-data
    #       spec:
    #         accessModes:
    #           - ReadWriteOnce
    #         resources:
    #           requests:
    #             storage: 2400Gi  # Local cache for searchable snapshots
    #         storageClassName: standard"""

    def _generate_kibana(self) -> str:
        """Generate Kibana CRD."""
        count = self.kibana_config.get("count", 1)
        memory = self.kibana_config.get("memory", "2Gi")
        cpu = self.kibana_config.get("cpu", "1")

        # Parse memory for limits (same as requests for Kibana)
        memory_limit = memory
        cpu_limit = str(int(cpu) * 2) if str(cpu).isdigit() else cpu

        return f"""apiVersion: kibana.k8s.elastic.co/v1
kind: Kibana
metadata:
  name: {self.project_name}
  namespace: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
    app.kubernetes.io/component: kibana
spec:
  version: {self.es_version}
  count: {count}
  
  elasticsearchRef:
    name: {self.project_name}
  
  http:
    tls:
      selfSignedCertificate:
        disabled: false
  
  podTemplate:
    spec:
      containers:
        - name: kibana
          resources:
            requests:
              memory: "{memory}"
              cpu: "{cpu}"
            limits:
              memory: "{memory_limit}"
              cpu: "{cpu_limit}"
"""

    def _generate_kibana_kustomization(self) -> str:
        """Generate kustomization.yaml for kibana directory."""
        return f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: {self.project_name}

resources:
  - kibana.yaml

commonLabels:
  app.kubernetes.io/part-of: {self.project_name}
  app.kubernetes.io/component: kibana
  app.kubernetes.io/managed-by: eck
"""

    def _generate_fleet_server(self) -> str:
        """Generate Fleet Server deployment."""
        memory = self.fleet_config.get("memory", "1Gi")
        cpu = self.fleet_config.get("cpu", "500m")

        return f"""apiVersion: agent.k8s.elastic.co/v1alpha1
kind: Agent
metadata:
  name: {self.project_name}-fleet-server
  namespace: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
    app.kubernetes.io/component: fleet-server
spec:
  version: {self.es_version}
  
  # Fleet Server mode
  mode: fleet
  fleetServerEnabled: true
  
  # Reference to Elasticsearch
  elasticsearchRefs:
    - name: {self.project_name}
  
  # Reference to Kibana for Fleet setup
  kibanaRef:
    name: {self.project_name}
  
  # Deployment for Fleet Server
  deployment:
    replicas: 1
    podTemplate:
      spec:
        serviceAccountName: elastic-agent
        automountServiceAccountToken: true
        containers:
          - name: agent
            resources:
              requests:
                memory: "{memory}"
                cpu: "{cpu}"
              limits:
                memory: "{memory}"
                cpu: "1"
"""

    def _generate_agent(self) -> str:
        """Generate Elastic Agent DaemonSet for node-level collection."""
        return f"""apiVersion: agent.k8s.elastic.co/v1alpha1
kind: Agent
metadata:
  name: {self.project_name}-agent
  namespace: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
    app.kubernetes.io/component: elastic-agent
spec:
  version: {self.es_version}
  
  # Fleet mode - enrolls with Fleet Server
  mode: fleet
  
  # Reference to Fleet Server
  fleetServerRef:
    name: {self.project_name}-fleet-server
  
  # DaemonSet for node-level collection
  daemonSet:
    podTemplate:
      spec:
        serviceAccountName: elastic-agent
        automountServiceAccountToken: true
        securityContext:
          runAsUser: 0
        containers:
          - name: agent
            resources:
              requests:
                memory: "512Mi"
                cpu: "200m"
              limits:
                memory: "1Gi"
                cpu: "500m"
"""

    def _generate_agent_rbac(self) -> str:
        """Generate RBAC for Elastic Agent."""
        return f"""apiVersion: v1
kind: ServiceAccount
metadata:
  name: elastic-agent
  namespace: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
    app.kubernetes.io/component: elastic-agent
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: elastic-agent-{self.project_name}
rules:
  - apiGroups: [""]
    resources: ["pods", "nodes", "namespaces", "events", "services", "configmaps", "persistentvolumes", "persistentvolumeclaims"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["nodes/stats", "nodes/metrics"]
    verbs: ["get"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["storage.k8s.io"]
    resources: ["storageclasses"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: elastic-agent-{self.project_name}
subjects:
  - kind: ServiceAccount
    name: elastic-agent
    namespace: {self.project_name}
roleRef:
  kind: ClusterRole
  name: elastic-agent-{self.project_name}
  apiGroup: rbac.authorization.k8s.io
"""

    def _generate_agents_kustomization(self) -> str:
        """Generate kustomization.yaml for agents directory."""
        return f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: {self.project_name}

resources:
  - rbac.yaml
  - fleet-server.yaml
  - elastic-agent.yaml

commonLabels:
  app.kubernetes.io/part-of: {self.project_name}
  app.kubernetes.io/component: agents
  app.kubernetes.io/managed-by: eck
"""

    def _generate_es_kustomization(self) -> str:
        """Generate kustomization.yaml for elasticsearch directory."""
        return f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: {self.project_name}

resources:
  - namespace.yaml
  - cluster.yaml

commonLabels:
  app.kubernetes.io/part-of: {self.project_name}
  app.kubernetes.io/component: elasticsearch
  app.kubernetes.io/managed-by: eck
"""

    def _generate_ilm_policy(self) -> str:
        """Generate ILM policy for hot-warm-cold (default)."""
        return """{
  "policy": {
    "phases": {
      "hot": {
        "min_age": "0ms",
        "actions": {
          "rollover": {
            "max_age": "1d",
            "max_primary_shard_size": "50gb"
          },
          "set_priority": {
            "priority": 100
          }
        }
      },
      "warm": {
        "min_age": "7d",
        "actions": {
          "set_priority": {
            "priority": 50
          },
          "shrink": {
            "number_of_shards": 1
          },
          "forcemerge": {
            "max_num_segments": 1
          }
        }
      },
      "cold": {
        "min_age": "30d",
        "actions": {
          "set_priority": {
            "priority": 0
          },
          "freeze": {}
        }
      },
      "delete": {
        "min_age": "90d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
"""

    def _generate_multi_tier_ilm_policy(self) -> str:
        """Generate ILM policy for hot-cold-frozen (from sizing report)."""
        # Extract retention info from sizing if available
        inputs = self.sizing.get("inputs", {})
        hot_days = 7  # default
        cold_days = 30  # default
        frozen_days = 90  # default

        # Try to infer from sizing inputs
        if self.data_nodes:
            # Hot tier days from sizing
            hot_tier = self.sizing.get("data_nodes", {})
            # Use days_in_tier if available

        return """{
  "policy": {
    "_meta": {
      "description": "Multi-tier ILM policy generated from sizing report",
      "managed_by": "project-initializer"
    },
    "phases": {
      "hot": {
        "min_age": "0ms",
        "actions": {
          "rollover": {
            "max_age": "1d",
            "max_primary_shard_size": "50gb"
          },
          "set_priority": {
            "priority": 100
          }
        }
      },
      "cold": {
        "min_age": "7d",
        "actions": {
          "set_priority": {
            "priority": 50
          },
          "allocate": {
            "require": {
              "data": "cold"
            }
          },
          "readonly": {}
        }
      },
      "frozen": {
        "min_age": "30d",
        "actions": {
          "set_priority": {
            "priority": 0
          },
          "searchable_snapshot": {
            "snapshot_repository": "found-snapshots",
            "force_merge_index": true
          }
        }
      },
      "delete": {
        "min_age": "365d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
"""

    def _generate_index_template(self) -> str:
        """Generate index template for logs."""
        ilm_policy = "hot-cold-frozen" if self.is_multi_tier else "hot-warm-cold"

        return f"""{{
  "index_patterns": ["logs-{self.project_name}-*"],
  "template": {{
    "settings": {{
      "number_of_shards": 1,
      "number_of_replicas": 1,
      "index.lifecycle.name": "{ilm_policy}",
      "index.lifecycle.rollover_alias": "logs-{self.project_name}"
    }},
    "mappings": {{
      "properties": {{
        "@timestamp": {{
          "type": "date"
        }},
        "message": {{
          "type": "text"
        }},
        "log.level": {{
          "type": "keyword"
        }},
        "kubernetes.namespace": {{
          "type": "keyword"
        }},
        "kubernetes.pod.name": {{
          "type": "keyword"
        }}
      }}
    }}
  }}
}}
"""

    def _generate_readme(self) -> str:
        """Generate README for elasticsearch directory."""
        # Build tier table
        tier_rows = []
        tier_rows.append(
            f"| Master nodes | {self.master_nodes.get('count', 3)} | {self.master_nodes.get('memory', '2Gi')} | {self.master_nodes.get('cpu', '1')} | - |"
        )
        tier_rows.append(
            f"| Hot tier | {self.data_nodes.get('count', 3)} | {self.data_nodes.get('memory', '8Gi')} | {self.data_nodes.get('cpu', '2')} | {self.data_nodes.get('storage', '100Gi')} |"
        )

        if self.cold_nodes:
            tier_rows.append(
                f"| Cold tier | {self.cold_nodes.get('count', 3)} | {self.cold_nodes.get('memory', '16Gi')} | {self.cold_nodes.get('cpu', '4')} | {self.cold_nodes.get('storage', '2000Gi')} |"
            )

        if self.frozen_nodes:
            tier_rows.append(
                f"| Frozen tier | {self.frozen_nodes.get('count', 1)} | {self.frozen_nodes.get('memory', '32Gi')} | {self.frozen_nodes.get('cpu', '8')} | {self.frozen_nodes.get('cache_storage', '2400Gi')} (cache) |"
            )

        tier_rows.append(
            f"| Kibana | {self.kibana_config.get('count', 1)} | {self.kibana_config.get('memory', '2Gi')} | {self.kibana_config.get('cpu', '1')} | - |"
        )

        tier_table = "\n".join(tier_rows)

        # Sizing source note
        sizing_note = ""
        if self.is_multi_tier:
            health_score = self.sizing.get("health_score", "N/A")
            sizing_note = f"""
## Sizing Source

This cluster was sized using the **elasticsearch-openshift-sizing-assistant**.
- **Health Score**: {health_score}/100
- **Profile**: Multi-tier (Hot/Cold/Frozen)
"""

        # Total resources
        total_nodes = (
            self.master_nodes.get("count", 3)
            + self.data_nodes.get("count", 3)
            + (self.cold_nodes.get("count", 0) if self.cold_nodes else 0)
            + (self.frozen_nodes.get("count", 0) if self.frozen_nodes else 0)
        )

        return f"""# Elasticsearch Cluster: {self.project_name}

## Overview

ECK-managed Elasticsearch cluster with the following components:
- **Elasticsearch {self.es_version}**: {total_nodes} nodes (multi-tier architecture)
- **Kibana {self.es_version}**: {self.kibana_config.get("count", 1)} instance(s) for visualization
- **Elastic Agent**: Fleet-managed for log/metric collection
{sizing_note}
## Prerequisites

1. ECK Operator installed (v{self.eck_version}+):
   ```bash
   kubectl create -f https://download.elastic.co/downloads/eck/{self.eck_version}/crds.yaml
   kubectl apply -f https://download.elastic.co/downloads/eck/{self.eck_version}/operator.yaml
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
kubectl get secret {self.project_name}-es-elastic-user -n {self.project_name} -o jsonpath='{{{{.data.elastic}}}}' | base64 -d
```

### Port-forward Elasticsearch
```bash
kubectl port-forward svc/{self.project_name}-es-http -n {self.project_name} 9200:9200
```

### Port-forward Kibana
```bash
kubectl port-forward svc/{self.project_name}-kb-http -n {self.project_name} 5601:5601
```

## Node Configuration

| Component | Count | Memory | CPU | Storage |
|-----------|-------|--------|-----|---------|
{tier_table}

## ILM Policies

The `{"hot-cold-frozen" if self.is_multi_tier else "hot-warm-cold"}` policy is included for log lifecycle management:
{"- Hot: 0-7 days (rollover at 1d or 50GB)"}
{"- Cold: 7-30 days (allocate to cold nodes, read-only)" if self.is_multi_tier else "- Warm: 7-30 days (shrink, force merge)"}
{"- Frozen: 30-365 days (searchable snapshots)" if self.is_multi_tier else "- Cold: 30-90 days (freeze)"}
- Delete: {"365+ days" if self.is_multi_tier else "90+ days"}

Apply with:
```bash
curl -X PUT "https://localhost:9200/_ilm/policy/{"hot-cold-frozen" if self.is_multi_tier else "hot-warm-cold"}" \\
  -H "Content-Type: application/json" \\
  -u "elastic:$PASSWORD" \\
  -d @elasticsearch/ilm-policies/{"hot-cold-frozen.json" if self.is_multi_tier else "hot-warm-cold.json"}
```
"""

    def _generate_kustomization(self) -> str:
        """Generate kustomization.yaml for the elasticsearch directory."""
        return f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: {self.project_name}

resources:
  - namespace.yaml
  - cluster.yaml
  - kibana.yaml
  - agent.yaml

commonLabels:
  app.kubernetes.io/part-of: {self.project_name}
  app.kubernetes.io/managed-by: eck
"""


# ------------------------------------------------------------------
# Main interface for addon loader
# ------------------------------------------------------------------


def main(
    project_name: str,
    description: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Main entry point for the addon loader.

    Args:
        project_name: Name of the project
        description: Project description
        context: Additional context (platform, sizing_context, etc.)

    Returns:
        Dict of {filepath: content} for generated files
    """
    generator = ECKDeploymentGenerator(project_name, description, context)
    return generator.generate()


if __name__ == "__main__":
    # Test generation with multi-tier sizing
    test_sizing = {
        "source": "sizing_report",
        "health_score": 85,
        "data_nodes": {
            "count": 3,
            "memory": "32Gi",
            "cpu": "8",
            "storage": "1000Gi",
            "tier": "hot",
        },
        "cold_nodes": {
            "count": 3,
            "memory": "16Gi",
            "cpu": "4",
            "storage": "2000Gi",
            "tier": "cold",
        },
        "frozen_nodes": {
            "count": 1,
            "memory": "32Gi",
            "cpu": "8",
            "cache_storage": "2400Gi",
            "tier": "frozen",
        },
        "master_nodes": {
            "count": 3,
            "memory": "4Gi",
            "cpu": "2",
        },
        "kibana": {
            "count": 1,
            "memory": "18Gi",
            "cpu": "8",
        },
        "fleet_server": {
            "count": 1,
            "memory": "4Gi",
            "cpu": "2",
        },
    }

    files = main(
        "test-cluster",
        "Test Elasticsearch cluster on OpenShift",
        {
            "platform": "openshift",
            "sizing_context": test_sizing,
        },
    )

    print("Generated files:")
    for filepath in sorted(files.keys()):
        print(f"  - {filepath}")

    # Print cluster.yaml to verify multi-tier
    print("\n--- cluster.yaml ---")
    print(files.get("elasticsearch/cluster.yaml", "")[:2000])
