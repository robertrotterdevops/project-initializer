#!/usr/bin/env python3
"""
Platform-specific manifests addon for project-initializer.
Generates platform-specific configurations for RKE2, OpenShift, and AKS.

Zero external dependencies -- Python 3.9+ stdlib only.
"""

from typing import Any, Dict, List, Optional


ADDON_META = {
    "name": "platform_manifests",
    "version": "1.0",
    "description": "Platform-specific manifests generator (RKE2/OpenShift/AKS)",
    "triggers": {"platforms": ["rke2", "openshift", "aks"]},
    "priority": 15,
}


class PlatformManifestsGenerator:
    """Generates platform-specific Kubernetes manifests."""

    def __init__(
        self,
        project_name: str,
        project_description: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.project_name = project_name
        self.description = project_description
        self.context = context or {}

        self.platform = self.context.get("platform", "kubernetes")
        self.sizing = self.context.get("sizing_context", {})

    def _openshift_worker_pools(self) -> List[Dict[str, Any]]:
        """Return parsed OpenShift worker pools from sizing context."""
        return self.sizing.get("openshift", {}).get("worker_pools", []) or []

    def _openshift_worker_config(self) -> List[Dict[str, Any]]:
        """Return parsed OpenShift worker config rows from sizing context."""
        return self.sizing.get("openshift", {}).get("worker_config", []) or []

    def _aks_node_pools(self) -> List[Dict[str, Any]]:
        """Return parsed AKS node pools from sizing context."""
        return self.sizing.get("aks", {}).get("node_pools", []) or []

    def generate(self) -> Dict[str, str]:
        """Generate platform-specific manifests based on detected platform."""
        files = {}

        if self.platform == "rke2":
            files.update(self._generate_rke2_manifests())
        elif self.platform == "openshift":
            files.update(self._generate_openshift_manifests())
        elif self.platform == "aks":
            files.update(self._generate_aks_manifests())

        # Common platform files
        files["platform/README.md"] = self._generate_platform_readme()

        return files

    # ------------------------------------------------------------------
    # RKE2 Manifests
    # ------------------------------------------------------------------

    def _generate_rke2_manifests(self) -> Dict[str, str]:
        """Generate RKE2-specific manifests."""
        files = {}

        # Storage class for local-path or Longhorn
        files["platform/rke2/storage-class.yaml"] = self._rke2_storage_class()

        # PSP (if enabled)
        files["platform/rke2/psp.yaml"] = self._rke2_psp()

        # Network policy
        files["platform/rke2/network-policy.yaml"] = self._rke2_network_policy()

        # Ingress config
        files["platform/rke2/ingress.yaml"] = self._rke2_ingress()

        # RKE2 cluster config example
        files["platform/rke2/cluster-config.yaml"] = self._rke2_cluster_config()

        return files

    def _rke2_storage_class(self) -> str:
        """Generate Longhorn storage class for RKE2."""
        return f"""# Longhorn Storage Class for RKE2
# Ensure Longhorn is installed: https://longhorn.io/docs/latest/deploy/install/
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: longhorn-{self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
provisioner: driver.longhorn.io
allowVolumeExpansion: true
reclaimPolicy: Delete
volumeBindingMode: Immediate
parameters:
  numberOfReplicas: "3"
  staleReplicaTimeout: "2880"
  fromBackup: ""
  fsType: "ext4"
---
# Alternative: local-path storage class
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-path-{self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
provisioner: rancher.io/local-path
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
"""

    def _rke2_psp(self) -> str:
        """Generate Pod Security Policy for RKE2."""
        return f"""# Pod Security Policy for Elasticsearch on RKE2
# Note: PSPs are deprecated in K8s 1.21+ but still used in some RKE2 deployments
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
  name: {self.project_name}-elasticsearch
  labels:
    app.kubernetes.io/name: {self.project_name}
spec:
  privileged: false
  allowPrivilegeEscalation: true  # Required for sysctl init container
  
  # Required for vm.max_map_count
  allowedCapabilities:
    - SYS_CHROOT
  
  # Run as any user (ES runs as elasticsearch user)
  runAsUser:
    rule: RunAsAny
  
  fsGroup:
    rule: RunAsAny
  
  supplementalGroups:
    rule: RunAsAny
  
  volumes:
    - 'configMap'
    - 'emptyDir'
    - 'persistentVolumeClaim'
    - 'secret'
    - 'downwardAPI'
  
  hostNetwork: false
  hostIPC: false
  hostPID: false
  
  seLinux:
    rule: RunAsAny
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: {self.project_name}-psp
rules:
  - apiGroups: ['policy']
    resources: ['podsecuritypolicies']
    verbs: ['use']
    resourceNames:
      - {self.project_name}-elasticsearch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {self.project_name}-psp
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: {self.project_name}-psp
subjects:
  - kind: ServiceAccount
    name: default
    namespace: {self.project_name}
"""

    def _rke2_network_policy(self) -> str:
        """Generate network policy for RKE2."""
        return f"""# Network Policy for Elasticsearch cluster on RKE2
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {self.project_name}-elasticsearch
  namespace: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
spec:
  podSelector:
    matchLabels:
      elasticsearch.k8s.elastic.co/cluster-name: {self.project_name}
  policyTypes:
    - Ingress
    - Egress
  
  ingress:
    # Allow ES transport (inter-node)
    - from:
        - podSelector:
            matchLabels:
              elasticsearch.k8s.elastic.co/cluster-name: {self.project_name}
      ports:
        - protocol: TCP
          port: 9300
    
    # Allow ES HTTP from Kibana
    - from:
        - podSelector:
            matchLabels:
              kibana.k8s.elastic.co/name: {self.project_name}
      ports:
        - protocol: TCP
          port: 9200
    
    # Allow ES HTTP from Elastic Agent
    - from:
        - podSelector:
            matchLabels:
              agent.k8s.elastic.co/name: {self.project_name}-agent
      ports:
        - protocol: TCP
          port: 9200
  
  egress:
    # Allow DNS
    - to:
        - namespaceSelector: {{}}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
    
    # Allow ES transport
    - to:
        - podSelector:
            matchLabels:
              elasticsearch.k8s.elastic.co/cluster-name: {self.project_name}
      ports:
        - protocol: TCP
          port: 9300
"""

    def _rke2_ingress(self) -> str:
        """Generate Ingress for RKE2 (nginx or traefik)."""
        return f"""# Ingress for Kibana on RKE2
# RKE2 default ingress controller is nginx
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {self.project_name}-kibana
  namespace: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
  annotations:
    # nginx ingress
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
    nginx.ingress.kubernetes.io/proxy-ssl-verify: "false"
    # Traefik (alternative)
    # traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: nginx  # or traefik
  tls:
    - hosts:
        - kibana.{self.project_name}.local
      secretName: {self.project_name}-kibana-tls
  rules:
    - host: kibana.{self.project_name}.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {self.project_name}-kb-http
                port:
                  number: 5601
"""

    def _rke2_cluster_config(self) -> str:
        """Generate example RKE2 cluster config."""
        return f"""# Example RKE2 cluster configuration for {self.project_name}
# Place in /etc/rancher/rke2/config.yaml on server nodes

# Server configuration
write-kubeconfig-mode: "0644"
tls-san:
  - "rke2.{self.project_name}.local"
  - "10.0.0.1"

# CNI plugin
cni: canal

# Disable default ingress if using custom
# disable:
#   - rke2-ingress-nginx

# Enable PSP (deprecated but may be required)
# kube-apiserver-arg:
#   - "enable-admission-plugins=PodSecurityPolicy"

# Kubelet configuration for Elasticsearch
kubelet-arg:
  - "max-pods=110"
  - "pods-per-core=0"

# For Elasticsearch vm.max_map_count
# Add to /etc/sysctl.d/99-elasticsearch.conf:
# vm.max_map_count=262144
"""

    # ------------------------------------------------------------------
    # OpenShift Manifests
    # ------------------------------------------------------------------

    def _generate_openshift_manifests(self) -> Dict[str, str]:
        """Generate OpenShift-specific manifests."""
        files = {}

        # Security Context Constraints
        files["platform/openshift/scc.yaml"] = self._openshift_scc()

        # Route (OpenShift native ingress)
        files["platform/openshift/route.yaml"] = self._openshift_route()

        # MachineSet examples
        files["platform/openshift/machineset-example.yaml"] = (
            self._openshift_machineset()
        )

        # Resource quotas
        files["platform/openshift/resource-quota.yaml"] = self._openshift_quota()

        return files

    def _openshift_scc(self) -> str:
        """Generate Security Context Constraints for OpenShift."""
        return f"""# Security Context Constraints for Elasticsearch on OpenShift
# ECK requires privileged SCCs for the init containers
apiVersion: security.openshift.io/v1
kind: SecurityContextConstraints
metadata:
  name: {self.project_name}-elasticsearch
  labels:
    app.kubernetes.io/name: {self.project_name}
allowPrivilegedContainer: true
allowPrivilegeEscalation: true
allowHostDirVolumePlugin: false
allowHostIPC: false
allowHostNetwork: false
allowHostPID: false
allowHostPorts: false
readOnlyRootFilesystem: false
requiredDropCapabilities:
  - KILL
  - MKNOD
  - SETUID
  - SETGID
runAsUser:
  type: RunAsAny
seLinuxContext:
  type: MustRunAs
fsGroup:
  type: RunAsAny
supplementalGroups:
  type: RunAsAny
volumes:
  - configMap
  - downwardAPI
  - emptyDir
  - persistentVolumeClaim
  - projected
  - secret
users:
  - system:serviceaccount:{self.project_name}:default
  - system:serviceaccount:{self.project_name}:elastic-agent
---
# Grant SCC to service accounts
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {self.project_name}-scc
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:openshift:scc:{self.project_name}-elasticsearch
subjects:
  - kind: ServiceAccount
    name: default
    namespace: {self.project_name}
"""

    def _openshift_route(self) -> str:
        """Generate OpenShift Route for Kibana."""
        return f"""# OpenShift Route for Kibana
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: {self.project_name}-kibana
  namespace: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
spec:
  host: kibana-{self.project_name}.apps.cluster.local
  to:
    kind: Service
    name: {self.project_name}-kb-http
    weight: 100
  port:
    targetPort: https
  tls:
    termination: reencrypt
    insecureEdgeTerminationPolicy: Redirect
  wildcardPolicy: None
---
# Route for Elasticsearch API (optional, usually internal only)
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: {self.project_name}-elasticsearch
  namespace: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
  annotations:
    # Restrict to internal access
    haproxy.router.openshift.io/ip_whitelist: "10.0.0.0/8"
spec:
  host: elasticsearch-{self.project_name}.apps.cluster.local
  to:
    kind: Service
    name: {self.project_name}-es-http
    weight: 100
  port:
    targetPort: https
  tls:
    termination: reencrypt
    insecureEdgeTerminationPolicy: None
  wildcardPolicy: None
"""

    def _openshift_machineset(self) -> str:
        """Generate example MachineSet for dedicated ES nodes."""
        pools = self._openshift_worker_pools()
        pool_map = {p.get("name", ""): p for p in pools}
        cfg_rows = self._openshift_worker_config()

        if not cfg_rows:
            cfg_rows = [
                {"pool_name": "Hot Pool", "vcpu": 16.0, "ram_gb": 64.0},
                {"pool_name": "Cold Pool", "vcpu": 16.0, "ram_gb": 64.0},
                {"pool_name": "System Pool", "vcpu": 16.0, "ram_gb": 32.0},
            ]

        docs: List[str] = [
            "# OpenShift MachineSets derived from sizing export",
            "# Replace providerSpec details (AMI/subnet/security groups/credentials) for your cloud.",
        ]

        for row in cfg_rows:
            pool_name = row.get("pool_name", "Pool")
            short = pool_name.lower().replace(" pool", "").replace(" ", "-")
            workers = int(pool_map.get(pool_name, {}).get("workers", 3) or 3)
            vcpu = row.get("vcpu", "?")
            ram = row.get("ram_gb", "?")

            doc = f"""apiVersion: machine.openshift.io/v1beta1
kind: MachineSet
metadata:
  name: {self.project_name}-{short}
  namespace: openshift-machine-api
  labels:
    machine.openshift.io/cluster-api-cluster: <cluster-id>
spec:
  replicas: {workers}
  selector:
    matchLabels:
      machine.openshift.io/cluster-api-cluster: <cluster-id>
      machine.openshift.io/cluster-api-machineset: {self.project_name}-{short}
  template:
    metadata:
      labels:
        machine.openshift.io/cluster-api-cluster: <cluster-id>
        machine.openshift.io/cluster-api-machineset: {self.project_name}-{short}
        machine.openshift.io/cluster-api-machine-role: elasticsearch
        machine.openshift.io/cluster-api-machine-type: elasticsearch
    spec:
      metadata:
        labels:
          node-role.kubernetes.io/elasticsearch: ""
          {self.project_name}-pool: "{short}"
      taints:
        - key: elasticsearch
          value: "true"
          effect: NoSchedule
      providerSpec:
        value:
          # Example provider values only. Match to your cloud and worker flavor from sizing.
          # Target flavor for this pool: {vcpu} vCPU / {ram} GiB
          apiVersion: awsproviderconfig.openshift.io/v1beta1
          kind: AWSMachineProviderConfig
          instanceType: <set-instance-type>
          blockDevices:
            - ebs:
                volumeSize: 500
                volumeType: gp3
                iops: 3000
                throughput: 125
"""
            docs.append(doc)

        return "\n---\n".join(docs) + "\n"

    def _openshift_quota(self) -> str:
        """Generate ResourceQuota for OpenShift project."""
        return f"""# Resource Quota for {self.project_name} namespace
apiVersion: v1
kind: ResourceQuota
metadata:
  name: {self.project_name}-quota
  namespace: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
spec:
  hard:
    requests.cpu: "20"
    requests.memory: "64Gi"
    limits.cpu: "40"
    limits.memory: "128Gi"
    persistentvolumeclaims: "20"
    requests.storage: "2Ti"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: {self.project_name}-limits
  namespace: {self.project_name}
spec:
  limits:
    - type: Container
      default:
        cpu: "1"
        memory: "2Gi"
      defaultRequest:
        cpu: "100m"
        memory: "256Mi"
      max:
        cpu: "8"
        memory: "32Gi"
      min:
        cpu: "50m"
        memory: "64Mi"
"""

    # ------------------------------------------------------------------
    # AKS Manifests
    # ------------------------------------------------------------------

    def _generate_aks_manifests(self) -> Dict[str, str]:
        """Generate AKS-specific manifests."""
        files = {}

        # Azure managed disk storage class
        files["platform/aks/storage-class.yaml"] = self._aks_storage_class()

        # Managed identity
        files["platform/aks/managed-identity.yaml"] = self._aks_managed_identity()

        # Azure ingress
        files["platform/aks/ingress.yaml"] = self._aks_ingress()

        # Terraform example
        files["platform/aks/terraform-example.tf"] = self._aks_terraform()

        return files

    def _aks_storage_class(self) -> str:
        """Generate Azure managed disk storage class."""
        return f"""# Azure Premium SSD storage class for Elasticsearch
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: azure-premium-{self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
provisioner: disk.csi.azure.com
parameters:
  skuName: Premium_LRS
  cachingmode: ReadOnly
  # For zone-redundant storage (ZRS)
  # skuName: Premium_ZRS
allowVolumeExpansion: true
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
---
# Azure Ultra Disk for high-performance workloads
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: azure-ultra-{self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
provisioner: disk.csi.azure.com
parameters:
  skuName: UltraSSD_LRS
  DiskIOPSReadWrite: "4000"
  DiskMBpsReadWrite: "125"
  LogicalSectorSize: "512"
allowVolumeExpansion: true
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
"""

    def _aks_managed_identity(self) -> str:
        """Generate Azure Workload Identity configuration."""
        return f"""# Azure Workload Identity for {self.project_name}
# Enables pods to authenticate to Azure services using managed identity

apiVersion: v1
kind: ServiceAccount
metadata:
  name: {self.project_name}-identity
  namespace: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
  annotations:
    # Replace with your Azure managed identity client ID
    azure.workload.identity/client-id: "<managed-identity-client-id>"
---
# Pod label for workload identity
# Add this label to pods that need Azure access:
# azure.workload.identity/use: "true"

# Example: FederatedIdentityCredential (Azure CLI/Terraform)
# az identity federated-credential create \\
#   --name {self.project_name}-federated \\
#   --identity-name {self.project_name}-identity \\
#   --resource-group <resource-group> \\
#   --issuer <aks-oidc-issuer> \\
#   --subject system:serviceaccount:{self.project_name}:{self.project_name}-identity
"""

    def _aks_ingress(self) -> str:
        """Generate Azure Application Gateway Ingress."""
        return f"""# Azure Application Gateway Ingress for Kibana
# Requires AGIC addon or standalone installation
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {self.project_name}-kibana
  namespace: {self.project_name}
  labels:
    app.kubernetes.io/name: {self.project_name}
  annotations:
    kubernetes.io/ingress.class: azure/application-gateway
    appgw.ingress.kubernetes.io/ssl-redirect: "true"
    appgw.ingress.kubernetes.io/backend-protocol: "https"
    appgw.ingress.kubernetes.io/backend-hostname: "{self.project_name}-kb-http"
    # WAF policy (optional)
    # appgw.ingress.kubernetes.io/waf-policy-for-path: "/subscriptions/.../wafPolicies/..."
spec:
  tls:
    - hosts:
        - kibana.{self.project_name}.azure.example.com
      secretName: {self.project_name}-kibana-tls
  rules:
    - host: kibana.{self.project_name}.azure.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {self.project_name}-kb-http
                port:
                  number: 5601
---
# Alternative: nginx ingress (if AGIC not used)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {self.project_name}-kibana-nginx
  namespace: {self.project_name}
  annotations:
    kubernetes.io/ingress.class: nginx
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
    nginx.ingress.kubernetes.io/proxy-ssl-verify: "false"
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - kibana.{self.project_name}.azure.example.com
      secretName: {self.project_name}-kibana-tls
  rules:
    - host: kibana.{self.project_name}.azure.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {self.project_name}-kb-http
                port:
                  number: 5601
"""

    def _aks_terraform(self) -> str:
        """Generate Terraform example for AKS node pool."""
        pools = self._aks_node_pools()
        if not pools:
            pools = [
                {
                    "name": "eshot",
                    "vm_size": "Standard_D16s_v5",
                    "node_count": 3,
                    "disk_size_gb": 1024,
                    "purpose": "ES Hot tier",
                }
            ]

        blocks: List[str] = [
            "# Terraform example: AKS node pools derived from sizing export",
            "# Add these resources to your AKS Terraform configuration.",
        ]

        for pool in pools:
            name = str(pool.get("name", "espool")).lower()
            tf_name = "".join(ch if ch.isalnum() else "_" for ch in name)
            vm = pool.get("vm_size") or pool.get("vm_sku") or "Standard_D16s_v5"
            count = int(pool.get("node_count", 3) or 3)
            disk = int(pool.get("disk_size_gb", 256) or 256)
            purpose = pool.get("purpose", "Elasticsearch")

            block = f'''resource "azurerm_kubernetes_cluster_node_pool" "{tf_name}" {{
  name                  = "{name[:12]}"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = "{vm}"
  node_count            = {count}

  # {purpose}
  enable_auto_scaling = true
  min_count           = {count}
  max_count           = {max(count, count * 2)}

  zones = ["1", "2", "3"]

  node_labels = {{
    "workload"                 = "elasticsearch"
    "{self.project_name}-pool" = "{name}"
  }}

  node_taints = [
    "elasticsearch=true:NoSchedule"
  ]

  os_disk_size_gb = {disk}
  os_disk_type    = "Managed"

  tags = {{
    Environment = "production"
    Project     = "{self.project_name}"
  }}
}}
'''
            blocks.append(block)

        blocks.append(
            'output "elasticsearch_node_pool_ids" {\n  value = {\n'
            + "\n".join(
                [
                    f"    {''.join(ch if ch.isalnum() else '_' for ch in str(p.get('name', 'espool')).lower())} = azurerm_kubernetes_cluster_node_pool.{''.join(ch if ch.isalnum() else '_' for ch in str(p.get('name', 'espool')).lower())}.id"
                    for p in pools
                ]
            )
            + "\n  }\n}\n"
        )

        return "\n".join(blocks)

    # ------------------------------------------------------------------
    # Common
    # ------------------------------------------------------------------

    def _generate_platform_readme(self) -> str:
        """Generate README for platform directory."""
        platform_info = {
            "rke2": (
                "RKE2 + ECK",
                "Rancher Kubernetes Engine 2",
                [
                    "storage-class.yaml - Longhorn/local-path storage",
                    "psp.yaml - Pod Security Policy (if enabled)",
                    "network-policy.yaml - Network isolation",
                    "ingress.yaml - nginx/traefik ingress",
                    "cluster-config.yaml - RKE2 config example",
                ],
            ),
            "openshift": (
                "OpenShift 4.x + ECK",
                "Red Hat OpenShift Container Platform",
                [
                    "scc.yaml - Security Context Constraints",
                    "route.yaml - OpenShift Routes",
                    "machineset-example.yaml - Dedicated node pool",
                    "resource-quota.yaml - Namespace quotas",
                ],
            ),
            "aks": (
                "AKS + ECK",
                "Azure Kubernetes Service",
                [
                    "storage-class.yaml - Azure managed disks",
                    "managed-identity.yaml - Workload Identity",
                    "ingress.yaml - Application Gateway/nginx",
                    "terraform-example.tf - Node pool Terraform",
                ],
            ),
        }

        info = platform_info.get(
            self.platform, ("Kubernetes", "Generic Kubernetes", [])
        )

        files_list = "\n".join(f"- `{f}`" for f in info[2])

        return f"""# Platform Configuration: {info[0]}

## Overview

Platform-specific configurations for deploying {self.project_name} on {info[1]}.

## Files

{files_list}

## Prerequisites

### {info[0]}

{"See individual files for specific requirements." if info[2] else "No platform-specific configuration needed."}

## Usage

Apply platform-specific resources before deploying Elasticsearch:

```bash
kubectl apply -f platform/{self.platform}/
```

Then deploy the main Elasticsearch cluster:

```bash
kubectl apply -k elasticsearch/
```
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
    generator = PlatformManifestsGenerator(project_name, description, context)
    return generator.generate()


if __name__ == "__main__":
    # Test generation for each platform
    for platform in ["rke2", "openshift", "aks"]:
        files = main(
            "test-cluster",
            f"Test Elasticsearch cluster on {platform}",
            {
                "platform": platform,
            },
        )

        print(f"\n{platform.upper()} Generated files:")
        for filepath in sorted(files.keys()):
            print(f"  - {filepath}")
