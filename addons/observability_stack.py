#!/usr/bin/env python3
"""
Observability Stack addon for project-initializer.
Generates kube-metrics-server and OpenTelemetry Collector manifests
as pure Kustomize resources (no Helm).

Zero external dependencies -- Python 3.9+ stdlib only.
"""

from typing import Any, Dict, Optional


ADDON_META = {
    "name": "observability_stack",
    "version": "1.0",
    "description": "Kube-metrics-server and OTel Collector (pure Kustomize, no Helm)",
    "triggers": {
        "categories": ["elasticsearch"],
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

    def _is_openshift(self) -> bool:
        return self.platform in ("openshift",)

    def _is_aks(self) -> bool:
        return self.platform in ("aks",)

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

    processors:
      memory_limiter:
        check_interval: 1s
        limit_mib: 512
        spike_limit_mib: 128
      batch:
        send_batch_size: 1024
        timeout: 5s

    exporters:
      # OTLP exporter — replace endpoint with your backend
      otlp:
        endpoint: "your-otel-backend:4317"
        tls:
          insecure: true   # Set to false if your backend uses valid TLS certs
      # Elasticsearch exporter — sends logs/traces directly to ES
      elasticsearch:
        endpoints: ["https://{self.project_name}-es-http.{self.project_name}.svc:9200"]
        tls:
          insecure: true   # ECK uses self-signed certs by default
        # Uncomment and set credentials for authenticated clusters:
        # user: elastic
        # password: changeme
      logging:
        verbosity: normal

    service:
      pipelines:
        traces:
          receivers: [otlp]
          processors: [memory_limiter, batch]
          exporters: [otlp, logging]
        metrics:
          receivers: [otlp]
          processors: [memory_limiter, batch]
          exporters: [otlp, logging]
        logs:
          receivers: [otlp]
          processors: [memory_limiter, batch]
          exporters: [otlp, elasticsearch, logging]
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
      containers:
      - name: otel-collector
        image: otel/opentelemetry-collector-contrib:0.96.0
        args:
        - --config=/etc/otel-collector/config.yaml
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
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          runAsNonRoot: true
          capabilities:
            drop:
            - ALL
        livenessProbe:
          httpGet:
            path: /
            port: 13133
          initialDelaySeconds: 15
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 13133
          initialDelaySeconds: 5
          periodSeconds: 10
        volumeMounts:
        - name: config
          mountPath: /etc/otel-collector
          readOnly: true
      volumes:
      - name: config
        configMap:
          name: otel-collector-config
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
  resources: ["pods", "nodes", "namespaces"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["replicasets"]
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
  # Allow egress to exporter endpoints
  - ports:
    - protocol: TCP
      port: 4317
    - protocol: TCP
      port: 4318
    - protocol: TCP
      port: 443
    - protocol: TCP
      port: 9200
  # Allow DNS resolution
  - ports:
    - protocol: UDP
      port: 53
    - protocol: TCP
      port: 53
"""

        # --- README.md ---
        files[f"{prefix}/README.md"] = f"""# OpenTelemetry Collector

Raw Kustomize manifests for the [OpenTelemetry Collector Contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib) v0.96.0.

Deployed as a **DaemonSet** in the `observability` namespace to collect traces, metrics, and logs from all nodes.

## Configuration

Edit `configmap.yaml` to customise the collector pipeline:

- **Receivers**: OTLP (gRPC :4317, HTTP :4318) enabled by default
- **Processors**: `memory_limiter` (512 MiB) and `batch` (5s / 1024 batch size)
- **Exporters**: OTLP (placeholder endpoint) and `logging`
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
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> Dict[str, str]:
        """Generate all observability stack manifests."""
        files: Dict[str, str] = {}
        files.update(self._generate_metrics_server())
        files.update(self._generate_otel_collector())
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
