#!/usr/bin/env python3
"""
Observability Stack addon for project-initializer.
Generates kube-metrics-server and OpenTelemetry Collector manifests
as pure Kustomize resources (no Helm).

Zero external dependencies -- Python 3.9+ stdlib only.
"""

from pathlib import Path
from typing import Any, Dict, Optional


ADDON_META = {
    "name": "observability_stack",
    "version": "1.0",
    "description": "Kube-metrics-server and OTel Collector (pure Kustomize, no Helm)",
    "triggers": {
        "categories": ["elasticsearch", "kubernetes"],
        "keywords": ["observability", "otel", "opentelemetry", "metrics-server"],
    },
    "priority": 25,
}


class ObservabilityStackGenerator:
    """Generates metrics-server and OTel Collector Kustomize manifests."""

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
        self.otel_version = self.context.get("otel_collector_version", "0.117.0")
        self.eck_version = self.context.get("eck_version", "3.0.0")

    def _is_openshift(self) -> bool:
        return self.platform in ("openshift",)

    def _is_aks(self) -> bool:
        return self.platform in ("aks",)

    def _has_builtin_metrics_server(self) -> bool:
        """RKE2 and AKS ship metrics-server as a built-in addon."""
        return self.platform in ("rke2", "aks")

    # ------------------------------------------------------------------
    # metrics-server
    # ------------------------------------------------------------------

    def _generate_metrics_server(self) -> Dict[str, str]:
        """Generate platform/metrics-server/ manifests."""
        prefix = "platform/metrics-server"
        files: Dict[str, str] = {}

        # --- kustomization.yaml ---
        files[f"{prefix}/kustomization.yaml"] = (
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\n"
            "resources:\n"
            "- deployment.yaml\n"
            "- service.yaml\n"
            "- apiservice.yaml\n"
            "- rbac.yaml\n"
            "- network-policy.yaml\n"
        )

        # --- ServiceAccount annotation for OpenShift ---
        sa_annotations = ""
        if self._is_openshift():
            sa_annotations = (
                '    openshift.io/scc: "restricted"\n'
            )

        # --- deployment.yaml ---
        files[f"{prefix}/deployment.yaml"] = f"""apiVersion: v1
kind: ServiceAccount
metadata:
  name: metrics-server
  namespace: kube-system
  labels:
    app.kubernetes.io/name: metrics-server
{f"  annotations:\\n{sa_annotations}" if sa_annotations else ""}---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: metrics-server
  namespace: kube-system
  labels:
    app.kubernetes.io/name: metrics-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: metrics-server
  strategy:
    rollingUpdate:
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app.kubernetes.io/name: metrics-server
    spec:
      serviceAccountName: metrics-server
      priorityClassName: system-cluster-critical
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: metrics-server
        image: registry.k8s.io/metrics-server/metrics-server:v0.7.2
        args:
        - --cert-dir=/tmp
        - --secure-port=10250
        - --kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname
        - --kubelet-insecure-tls
        ports:
        - name: https
          containerPort: 10250
          protocol: TCP
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 200m
            memory: 256Mi
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          runAsNonRoot: true
          capabilities:
            drop:
            - ALL
        livenessProbe:
          httpGet:
            path: /livez
            port: https
            scheme: HTTPS
          periodSeconds: 10
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /readyz
            port: https
            scheme: HTTPS
          periodSeconds: 10
          failureThreshold: 3
        volumeMounts:
        - name: tmp-dir
          mountPath: /tmp
      volumes:
      - name: tmp-dir
        emptyDir: {{}}
      nodeSelector:
        kubernetes.io/os: linux
"""

        # --- service.yaml ---
        files[f"{prefix}/service.yaml"] = """apiVersion: v1
kind: Service
metadata:
  name: metrics-server
  namespace: kube-system
  labels:
    app.kubernetes.io/name: metrics-server
spec:
  ports:
  - name: https
    port: 443
    protocol: TCP
    targetPort: 10250
  selector:
    app.kubernetes.io/name: metrics-server
"""

        # --- apiservice.yaml ---
        files[f"{prefix}/apiservice.yaml"] = """apiVersion: apiregistration.k8s.io/v1
kind: APIService
metadata:
  name: v1beta1.metrics.k8s.io
  labels:
    app.kubernetes.io/name: metrics-server
spec:
  service:
    name: metrics-server
    namespace: kube-system
  group: metrics.k8s.io
  version: v1beta1
  insecureSkipTLSVerify: true
  groupPriorityMinimum: 100
  versionPriority: 100
"""

        # --- rbac.yaml ---
        files[f"{prefix}/rbac.yaml"] = """apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: system:metrics-server
  labels:
    app.kubernetes.io/name: metrics-server
rules:
- apiGroups: [""]
  resources: ["nodes/metrics"]
  verbs: ["get"]
- apiGroups: [""]
  resources: ["pods", "nodes", "namespaces"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: system:metrics-server
  labels:
    app.kubernetes.io/name: metrics-server
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:metrics-server
subjects:
- kind: ServiceAccount
  name: metrics-server
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: metrics-server:system:auth-delegator
  labels:
    app.kubernetes.io/name: metrics-server
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:auth-delegator
subjects:
- kind: ServiceAccount
  name: metrics-server
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: metrics-server-auth-reader
  namespace: kube-system
  labels:
    app.kubernetes.io/name: metrics-server
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: extension-apiserver-authentication-reader
subjects:
- kind: ServiceAccount
  name: metrics-server
  namespace: kube-system
"""

        # --- network-policy.yaml ---
        files[f"{prefix}/network-policy.yaml"] = """apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: metrics-server
  namespace: kube-system
  labels:
    app.kubernetes.io/name: metrics-server
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: metrics-server
  policyTypes:
  - Ingress
  - Egress
  ingress:
  # Allow kube-apiserver to reach metrics-server
  - ports:
    - protocol: TCP
      port: 10250
  egress:
  # Allow metrics-server to reach kubelets
  - ports:
    - protocol: TCP
      port: 10250
  # Allow DNS resolution
  - ports:
    - protocol: UDP
      port: 53
    - protocol: TCP
      port: 53
"""

        # --- README.md ---
        aks_note = ""
        if self._is_aks():
            aks_note = (
                "\n> **AKS Note:** Azure Kubernetes Service ships with metrics-server "
                "pre-installed.\n> These manifests are provided as a reference. "
                "Do not apply them on AKS unless you\n> have explicitly disabled the "
                "managed metrics-server add-on.\n"
            )

        files[f"{prefix}/README.md"] = f"""# Kube Metrics Server

Raw Kustomize manifests for [metrics-server](https://github.com/kubernetes-sigs/metrics-server) v0.7.x.

Provides the Metrics API (`metrics.k8s.io/v1beta1`) required by:
- `kubectl top nodes` / `kubectl top pods`
- Horizontal Pod Autoscaler (HPA)
- Vertical Pod Autoscaler (VPA)
{aks_note}
## Usage

Apply directly:

```bash
kubectl apply -k platform/metrics-server/
```

Or enable via Flux by uncommenting the reference in `infrastructure/kustomization.yaml`.

## Self-signed kubelet certificates

If your cluster uses self-signed kubelet serving certificates, uncomment
`--kubelet-insecure-tls` in `deployment.yaml`.

*Generated by project-initializer observability_stack addon*
"""

        return files

    # ------------------------------------------------------------------
    # OTel Collector
    # ------------------------------------------------------------------

    def _generate_otel_collector(self) -> Dict[str, str]:
        """Generate observability/otel-collector/ manifests."""
        prefix = "observability/otel-collector"
        files: Dict[str, str] = {}

        # --- kustomization.yaml ---
        files[f"{prefix}/kustomization.yaml"] = (
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\n"
            "resources:\n"
            "- namespace.yaml\n"
            "- es-secret.yaml   # prune: disabled — credentials overwritten by post-terraform-deploy.sh\n"
            "- configmap.yaml\n"
            "- daemonset.yaml\n"
            "- service.yaml\n"
            "- rbac.yaml\n"
            "- network-policy.yaml\n"
        )

        # --- namespace.yaml ---
        files[f"{prefix}/namespace.yaml"] = f"""apiVersion: v1
kind: Namespace
metadata:
  name: observability
  labels:
    project: {self.project_name}
    purpose: observability
"""

        # --- es-secret.yaml ---
        files[f"{prefix}/es-secret.yaml"] = f"""apiVersion: v1
kind: Secret
metadata:
  name: otel-es-credentials
  namespace: observability
  labels:
    app.kubernetes.io/name: otel-collector
  annotations:
    # Flux creates this placeholder on first deploy.  prune: disabled keeps it
    # alive after post-terraform-deploy.sh overwrites with real credentials.
    # Do NOT add reconcile: disabled — it prevents first-time creation.
    kustomize.toolkit.fluxcd.io/prune: disabled
type: Opaque
stringData:
  username: ""
  password: ""
"""

        # --- configmap.yaml ---
        files[f"{prefix}/configmap.yaml"] = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-collector-config
  namespace: observability
  labels:
    app.kubernetes.io/name: otel-collector
data:
  config.yaml: |
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318

      hostmetrics:
        collection_interval: 30s
        scrapers:
          cpu: {{}}
          disk: {{}}
          filesystem: {{}}
          load: {{}}
          memory: {{}}
          network: {{}}

      kubeletstats:
        collection_interval: 30s
        auth_type: serviceAccount
        endpoint: "${{env:K8S_NODE_IP}}:10250"
        insecure_skip_verify: true
        metric_groups:
          - node
          - pod
          - container

      filelog:
        include:
          - /var/log/pods/*/*/*.log
        include_file_path: true
        include_file_name: false
        # No operators: containerd log lines start with a timestamp prefix, not JSON.
        # Collect raw lines; structured parsing can be added once stable.

    processors:
      memory_limiter:
        check_interval: 1s
        limit_mib: 640
        spike_limit_mib: 192
      batch:
        send_batch_size: 1024
        timeout: 5s

    exporters:
      elasticsearch:
        endpoints: ["https://{self.project_name}-es-http.{self.project_name}.svc:9200"]
        tls:
          insecure_skip_verify: true
        user: "${{env:ES_USERNAME}}"
        password: "${{env:ES_PASSWORD}}"
        mapping:
          mode: ecs
      debug:
        verbosity: normal

    extensions:
      health_check:
        endpoint: 0.0.0.0:13133

    service:
      extensions: [health_check]
      pipelines:
        traces:
          receivers: [otlp]
          processors: [memory_limiter, batch]
          exporters: [elasticsearch, debug]
        metrics:
          receivers: [otlp, hostmetrics, kubeletstats]
          processors: [memory_limiter, batch]
          exporters: [elasticsearch, debug]
        logs:
          receivers: [otlp, filelog]
          processors: [memory_limiter, batch]
          exporters: [elasticsearch, debug]
      telemetry:
        logs:
          level: info
        metrics:
          address: 0.0.0.0:8888
"""

        # --- ServiceAccount annotation for OpenShift ---
        sa_annotations = ""
        if self._is_openshift():
            sa_annotations = (
                "  annotations:\n"
                '    openshift.io/scc: "restricted"\n'
            )

        # --- daemonset.yaml ---
        files[f"{prefix}/daemonset.yaml"] = f"""apiVersion: v1
kind: ServiceAccount
metadata:
  name: otel-collector
  namespace: observability
  labels:
    app.kubernetes.io/name: otel-collector
{sa_annotations}---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: otel-collector
  namespace: observability
  labels:
    app.kubernetes.io/name: otel-collector
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: otel-collector
  template:
    metadata:
      labels:
        app.kubernetes.io/name: otel-collector
    spec:
      serviceAccountName: otel-collector
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
      initContainers:
      - name: wait-for-es-credentials
        image: busybox:1.36
        command: ["sh", "-c"]
        args:
        - |
          echo "Waiting for ES credentials to be populated..."
          while [ -z "$ES_PASSWORD" ]; do
            echo "ES_PASSWORD is empty — waiting for credential mirroring (sleep 10s)"
            sleep 10
          done
          echo "ES credentials found, starting collector."
        env:
        - name: ES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: otel-es-credentials
              key: password
        resources:
          requests:
            cpu: 10m
            memory: 16Mi
          limits:
            cpu: 10m
            memory: 16Mi
        securityContext:
          allowPrivilegeEscalation: false
          runAsNonRoot: true
          runAsUser: 65534
          capabilities:
            drop:
            - ALL
      containers:
      - name: otel-collector
        image: otel/opentelemetry-collector-contrib:{self.otel_version}
        args:
        - --config=/etc/otel-collector/config.yaml
        env:
        - name: ES_USERNAME
          valueFrom:
            secretKeyRef:
              name: otel-es-credentials
              key: username
        - name: ES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: otel-es-credentials
              key: password
        - name: K8S_NODE_IP
          valueFrom:
            fieldRef:
              fieldPath: status.hostIP
        ports:
        - name: otlp-grpc
          containerPort: 4317
          protocol: TCP
        - name: otlp-http
          containerPort: 4318
          protocol: TCP
        - name: metrics
          containerPort: 8888
          protocol: TCP
        resources:
          requests:
            cpu: 200m
            memory: 384Mi
          limits:
            cpu: 500m
            memory: 768Mi
        securityContext:
          allowPrivilegeEscalation: false
          runAsNonRoot: true
          capabilities:
            drop:
            - ALL
        livenessProbe:
          httpGet:
            path: /
            port: 13133
          initialDelaySeconds: 30
          periodSeconds: 15
          failureThreshold: 5
        readinessProbe:
          httpGet:
            path: /
            port: 13133
          initialDelaySeconds: 15
          periodSeconds: 15
          failureThreshold: 3
        volumeMounts:
        - name: config
          mountPath: /etc/otel-collector
          readOnly: true
        - name: varlogpods
          mountPath: /var/log/pods
          readOnly: true
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
        - name: tmpdir
          mountPath: /tmp
      volumes:
      - name: config
        configMap:
          name: otel-collector-config
      - name: varlogpods
        hostPath:
          path: /var/log/pods
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers
      - name: tmpdir
        emptyDir: {{}}
      nodeSelector:
        kubernetes.io/os: linux
"""

        # --- service.yaml ---
        files[f"{prefix}/service.yaml"] = """apiVersion: v1
kind: Service
metadata:
  name: otel-collector
  namespace: observability
  labels:
    app.kubernetes.io/name: otel-collector
spec:
  type: ClusterIP
  ports:
  - name: otlp-grpc
    port: 4317
    targetPort: 4317
    protocol: TCP
  - name: otlp-http
    port: 4318
    targetPort: 4318
    protocol: TCP
  - name: metrics
    port: 8888
    targetPort: 8888
    protocol: TCP
  selector:
    app.kubernetes.io/name: otel-collector
"""

        # --- rbac.yaml ---
        files[f"{prefix}/rbac.yaml"] = """apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: otel-collector
  labels:
    app.kubernetes.io/name: otel-collector
rules:
- apiGroups: [""]
  resources: ["pods", "nodes", "namespaces", "endpoints", "services"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["nodes/stats", "nodes/proxy"]
  verbs: ["get"]
- apiGroups: ["apps"]
  resources: ["replicasets", "daemonsets", "deployments", "statefulsets"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: otel-collector
  labels:
    app.kubernetes.io/name: otel-collector
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: otel-collector
subjects:
- kind: ServiceAccount
  name: otel-collector
  namespace: observability
"""

        # --- network-policy.yaml ---
        files[f"{prefix}/network-policy.yaml"] = """apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: otel-collector
  namespace: observability
  labels:
    app.kubernetes.io/name: otel-collector
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: otel-collector
  policyTypes:
  - Ingress
  - Egress
  ingress:
  # Allow OTLP ingress from all namespaces
  - from:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 4317
    - protocol: TCP
      port: 4318
  egress:
  # Allow egress to all destinations on required ports.
  # ipBlock 0.0.0.0/0 is explicit to ensure Canal/Calico matches ClusterIP
  # and node-IP traffic (kubelet :10250, k8s API :443, ES :9200, OTLP :4317/:4318).
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
    ports:
    - protocol: TCP
      port: 4317
    - protocol: TCP
      port: 4318
    - protocol: TCP
      port: 443
    - protocol: TCP
      port: 9200
    - protocol: TCP
      port: 10250   # kubelet API (kubeletstats receiver)
  # Allow DNS resolution
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
    ports:
    - protocol: UDP
      port: 53
    - protocol: TCP
      port: 53
"""

        # --- README.md ---
        files[f"{prefix}/README.md"] = f"""# OpenTelemetry Collector

Raw Kustomize manifests for the [OpenTelemetry Collector Contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib) v{self.otel_version}.

Deployed as a **DaemonSet** in the `observability` namespace to collect traces, metrics, and logs from all nodes.

## Configuration

Edit `configmap.yaml` to customise the collector pipeline:

- **Receivers**: OTLP (gRPC :4317, HTTP :4318) enabled by default
- **Processors**: `memory_limiter` (640 MiB) and `batch` (5s / 1024 batch size)
- **Exporters**: OTLP (placeholder endpoint) and `debug`
- **Pipelines**: traces, metrics, logs — all wired through the above

### Exporter endpoint

Replace `your-otel-backend:4317` in `configmap.yaml` with your actual backend
(e.g. Jaeger, Grafana Tempo, Elastic APM Server, or another OTel Collector).

## Usage

Apply directly:

```bash
kubectl apply -k observability/otel-collector/
```

Or enable via Flux by uncommenting the reference in `infrastructure/kustomization.yaml`.

## Sending telemetry

Applications can send OTLP data to:

```
grpc: otel-collector.observability.svc.cluster.local:4317
http: otel-collector.observability.svc.cluster.local:4318
```

*Generated by project-initializer observability_stack addon*
"""

        return files

    # ------------------------------------------------------------------
    # Documentation
    # ------------------------------------------------------------------

    def _generate_data_flow_doc(self) -> Dict[str, str]:
        """Generate docs/OTEL_AGENT_DATA_FLOW.md describing data flow architecture."""
        return {
            "docs/OTEL_AGENT_DATA_FLOW.md": f"""# OTEL + Elastic Agent Data Flow Architecture

**Project**: {self.project_name}

## Overview

This project uses two complementary data collection systems:

1. **OpenTelemetry Collector** (DaemonSet in `observability` namespace) — collects host metrics, kubelet stats, and container logs
2. **Elastic Agent** (DaemonSet in `{self.project_name}` namespace) — collects system metrics, Kubernetes metrics, and container logs via Fleet-managed integrations

Both systems export data to the Elasticsearch cluster managed by ECK in the `{self.project_name}` namespace.

## Data Flow Diagram

```
Nodes                          Kubernetes API
  |                                |
  v                                v
+-----------------+    +-----------------+
| OTEL Collector  |    | Elastic Agent   |
| (DaemonSet)     |    | (DaemonSet)     |
| ns: observability|    | ns: {self.project_name}     |
+-----------------+    +-----------------+
  | hostmetrics       | system integration
  | kubeletstats      | kubernetes integration
  | filelog            | container_logs
  |                    |
  v                    v
+---------------------------------+
| Elasticsearch (ECK)             |
| ns: {self.project_name}                     |
| {self.project_name}-es-http:9200             |
+---------------------------------+
          |
          v
+-----------------+
| Kibana          |
| ns: {self.project_name}     |
+-----------------+
```

## OTEL Collector Pipelines

| Pipeline | Receivers | Exporters | Notes |
|----------|-----------|-----------|-------|
| **traces** | otlp | elasticsearch, debug | Apps push OTLP traces |
| **metrics** | otlp, hostmetrics, kubeletstats | elasticsearch, debug | ECS mapping mode for Kibana compatibility |
| **logs** | otlp, filelog | elasticsearch, debug | Raw container logs from `/var/log/pods` |

## Elastic Agent Data Streams

| Data Stream | Source | Integration |
|-------------|--------|-------------|
| `logs-system.syslog` | Agent | System |
| `logs-system.auth` | Agent | System |
| `metrics-system.cpu/memory/diskio/network` | Agent | System |
| `metrics-kubernetes.node/pod/container/volume` | Agent | Kubernetes |
| `logs-kubernetes.container_logs` | Agent | Kubernetes |
| `logs-generic-default` | OTEL filelog | N/A |

## Authentication

- **OTEL → ES**: Uses `otel-es-credentials` secret in `observability` namespace (mirrored from ECK elastic-user secret by post-deploy script)
- **Agent → ES**: Managed by ECK operator via Fleet enrollment
- **Agent → Fleet**: ECK 3.x auto-enrollment via `kibanaRef`; ECK 2.x requires `FLEET_ENROLL=true` env var + enrollment token set by post-deploy script

## Known Gotchas

### 1. Canal/Calico Network Policy
When using RKE2 with Canal CNI, egress rules that specify only `ports:` without a `to:` field do NOT match ClusterIP or node-IP traffic. Always use explicit `to: ipBlock: cidr: 0.0.0.0/0` in network policies.

### 2. ECK DaemonSet Enrollment
ECK 3.x handles Fleet enrollment automatically via `kibanaRef` for all agent modes including DaemonSet. ECK 2.x requires explicit `FLEET_ENROLL` and `FLEET_ENROLLMENT_TOKEN` env vars for DaemonSet agents.

### 3. Filelog Operator Compatibility
Raw log lines are collected without structured parsing. Containerd log format uses timestamp prefixes, not JSON. Structured parsing can be added via filelog operators.

### 4. Secret Management
The `otel-es-credentials` secret uses `kustomize.toolkit.fluxcd.io/prune: disabled` to prevent Flux from deleting it, and an init container gates collector startup until credentials are populated. Consider using External Secrets Operator for production.

### 5. Fleet Default Output
The Fleet default output must be configured via Kibana API after deployment. The post-deploy script handles this automatically, setting the correct ES endpoint and CA fingerprint.

## Improvement Roadmap

1. **External Secrets Operator** — replace manual secret mirroring
2. **Structured log parsing** — add filelog operators for containerd log format
3. **OTEL Kibana dashboards** — pre-built dashboards for host metrics and kubelet stats

*Generated by project-initializer observability_stack addon*
"""
        }

    # ------------------------------------------------------------------
    # OTEL Dashboard
    # ------------------------------------------------------------------

    def _generate_otel_dashboard(self) -> Dict[str, str]:
        """Load the OTEL Infrastructure Overview ndjson from assets."""
        asset_path = Path(__file__).parent / "assets" / "otel-dashboards" / "otel-infrastructure-overview.ndjson"
        if asset_path.exists():
            content = asset_path.read_text()
        else:
            content = ""
        return {
            "observability/otel-dashboards/otel-infrastructure-overview.ndjson": content,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> Dict[str, str]:
        """Generate all observability stack manifests."""
        files: Dict[str, str] = {}
        if not self._has_builtin_metrics_server():
            files.update(self._generate_metrics_server())

        # Auto-enable OTEL collector for elasticsearch projects
        enable_otel = self.context.get("enable_otel_collector", True)
        primary_category = self.context.get("primary_category", "")
        if primary_category == "elasticsearch":
            enable_otel = True

        if enable_otel:
            files.update(self._generate_otel_collector())
            files.update(self._generate_data_flow_doc())
            files.update(self._generate_otel_dashboard())
            # Top-level observability kustomization.yaml (consumed by es-XX-observability Flux CR)
            files["observability/kustomization.yaml"] = (
                "apiVersion: kustomize.config.k8s.io/v1beta1\n"
                "kind: Kustomization\n"
                "resources:\n"
                "- otel-collector\n"
            )
        return files


def main(
    project_name: str,
    description: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Main entry point for the observability stack addon.

    :param project_name: Name of the project
    :param description: Project description
    :param context: Additional context (platform, sizing_context, etc.)
    :return: Dictionary of generated files
    """
    gen = ObservabilityStackGenerator(project_name, description, context)
    return gen.generate()
