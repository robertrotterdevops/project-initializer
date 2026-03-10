#!/usr/bin/env python3
"""
Flux Deployment Addon for Project Initializer

Extends the project initialization process with robust Flux GitOps deployment capabilities.
"""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional


ADDON_META = {
    "name": "flux_deployment",
    "version": "1.2",
    "description": "FluxCD GitOps deployment generator (default for all platforms)",
    "triggers": {"default": True},  # Always load FluxCD as default GitOps
    "priority": 5,  # High priority - load early
}


class FluxDeploymentGenerator:
    def __init__(
        self,
        project_name: str,
        project_description: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Flux Deployment Generator

        :param project_name: Name of the project
        :param project_description: Description of the project
        :param context: Additional context (platform, sizing_context, etc.)
        """
        self.project_name = project_name
        self.project_description = project_description
        self.context = context or {}
        self.platform = self.context.get("platform", "kubernetes")
        self.repo_url = self.context.get("repo_url", f"https://github.com/your-org/{project_name}.git")
        self.target_revision = self.context.get("target_revision", "main")
        self.git_token = (self.context.get("git_token") or "").strip()
        sizing_context = self.context.get("sizing_context") or {}
        self.eck_enabled = bool(
            sizing_context
            and (
                sizing_context.get("eck_operator")
                or sizing_context.get("source") == "sizing_report"
            )
        )
        self.complexity_score = self._calculate_complexity()

    def _repo_url_for_flux(self) -> str:
        if not self.repo_url:
            return f"https://github.com/your-org/{self.project_name}.git"
        return self.repo_url

    def _flux_secret_name(self) -> str:
        return f"{self.project_name}-git-auth"

    def _flux_secret_ref_block(self) -> str:
        if not self.git_token:
            return ""
        return (
            "  secretRef:\n"
            f"    name: {self._flux_secret_name()}\n"
        )

    def _calculate_complexity(self) -> float:
        """
        Calculate GitOps complexity based on project description

        :return: Complexity score (1.0 - 2.0)
        """
        complexity_keywords = {
            "multi-cluster": 1.5,
            "advanced": 1.3,
            "complex": 1.2,
            "enterprise": 1.4,
            "multi-env": 1.3,
            "multi-platform": 1.4,
        }

        # Convert description to lowercase for matching
        desc_lower = self.project_description.lower()

        # Calculate complexity score
        complexity = 1.0
        for keyword, score in complexity_keywords.items():
            if keyword in desc_lower:
                complexity *= score

        return min(complexity, 2.0)  # Cap at 2.0

    def generate_flux_manifests(self) -> Dict[str, str]:
        """
        Generate Flux deployment manifests based on project complexity

        :return: Dictionary of Flux manifest filenames and contents
        """
        manifests = {}

        # Namespace manifest
        manifests["namespace.yaml"] = f"""apiVersion: v1
kind: Namespace
metadata:
  name: flux-system
  labels:
    project: {self.project_name}
    managed-by: flux
    complexity-level: {"advanced" if self.complexity_score > 1.2 else "standard"}
"""

        # GitRepository manifest
        manifests["gitrepository.yaml"] = f"""apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: {self.project_name}
  namespace: flux-system
spec:
  interval: 1m
  url: {self._repo_url_for_flux()}
  ref:
    branch: {self.target_revision}
{self._flux_secret_ref_block()}  timeout: 2m
  ignore: |
    # Exclude files from synchronization
    /*.md
    /docs
    /scripts
"""

        # Root Flux Kustomization CR (gotk-sync).
        reconciliation_interval = "5m" if self.complexity_score < 1.3 else "1m"
        manifests["gotk-sync.yaml"] = f"""apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {self.project_name}
  namespace: flux-system
spec:
  interval: {reconciliation_interval}
  sourceRef:
    kind: GitRepository
    name: {self.project_name}
  path: ./clusters/management
  prune: true
  wait: false
  timeout: {"2m" if self.complexity_score < 1.3 else "5m"}
"""

        apps_depends_on = f"""  dependsOn:
  - name: {self.project_name}
  - name: {self.project_name}-infra
"""
        manifests["kustomization-apps.yaml"] = f"""apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {self.project_name}-apps
  namespace: flux-system
spec:
  interval: {reconciliation_interval}
  sourceRef:
    kind: GitRepository
    name: {self.project_name}
  path: ./apps
  prune: true
  wait: true
  timeout: 20m
{apps_depends_on}"""

        manifests["kustomization-infra.yaml"] = f"""apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {self.project_name}-infra
  namespace: flux-system
spec:
  interval: {reconciliation_interval}
  sourceRef:
    kind: GitRepository
    name: {self.project_name}
  path: ./infrastructure
  prune: true
  wait: true
  dependsOn:
  - name: {self.project_name}
"""

        if self.eck_enabled:
            manifests["kustomization-agents.yaml"] = f"""apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {self.project_name}-agents
  namespace: flux-system
spec:
  interval: {reconciliation_interval}
  sourceRef:
    kind: GitRepository
    name: {self.project_name}
  path: ./agents
  prune: true
  wait: true
  timeout: 20m
  dependsOn:
  - name: {self.project_name}-apps
"""

        # Auth secret for private repositories when token is provided.
        if self.git_token:
            manifests["git-auth-secret.yaml"] = f"""apiVersion: v1
kind: Secret
metadata:
  name: {self._flux_secret_name()}
  namespace: flux-system
type: Opaque
stringData:
  username: oauth2
  password: {self.git_token}
"""

        # flux-system directory overlay for kubectl/kustomize entrypoint.
        flux_resources = [
            "- namespace.yaml",
            "- gitrepository.yaml",
            "- gotk-sync.yaml",
            "- kustomization-apps.yaml",
            "- kustomization-infra.yaml",
        ]
        if self.eck_enabled:
            flux_resources.append("- kustomization-agents.yaml")
        if self.git_token:
            flux_resources.insert(1, "- git-auth-secret.yaml")
        manifests["kustomization.yaml"] = (
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\n"
            "resources:\n"
            + "\n".join(flux_resources)
            + "\n"
        )

        # RBAC for more complex deployments
        if self.complexity_score > 1.3:
            manifests["rbac.yaml"] = f"""apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: {self.project_name}-flux-reconciler
rules:
- apiGroups: ["*"]
  resources: ["*"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {self.project_name}-flux-reconciler
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: {self.project_name}-flux-reconciler
subjects:
- kind: ServiceAccount
  name: flux-reconciler
  namespace: flux-system
"""

        return manifests

    def generate_environment_overlays(self) -> Dict[str, str]:
        """
        Generate environment-specific overlays for different deployment environments

        :return: Dictionary of environment overlay manifests
        """
        overlays = {}

        # Environments to generate
        environments = ["dev", "staging", "production"]

        for env in environments:
            # Base kustomization for the environment
            overlays[
                f"overlays/{env}/kustomization.yaml"
            ] = f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- ../../base

# Environment-specific patches
patchesStrategicMerge:
- patch.yaml

# Additional resource quotas or limits for specific environments
- resources.yaml
"""

            # Resource quota and limit patch
            overlays[f"overlays/{env}/resources.yaml"] = f"""apiVersion: v1
kind: ResourceQuota
metadata:
  name: {self.project_name}-{env}-quota
spec:
  hard:
    requests.cpu: {"2" if env == "production" else "1"}
    requests.memory: {"8Gi" if env == "production" else "4Gi"}
    limits.cpu: {"4" if env == "production" else "2"}
    limits.memory: {"16Gi" if env == "production" else "8Gi"}
"""

            # Environment-specific configuration patch
            overlays[f"overlays/{env}/patch.yaml"] = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {self.project_name}
spec:
  replicas: {3 if env == "production" else 1}
  template:
    spec:
      containers:
      - name: {self.project_name}
        env:
        - name: ENVIRONMENT
          value: {env}
        - name: LOG_LEVEL
          value: {"INFO" if env == "production" else "DEBUG"}
"""

            # Environment-specific Flux Kustomization
            overlays[
                f"overlays/{env}/flux-kustomization.yaml"
            ] = f"""apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {self.project_name}-{env}
  namespace: flux-system
spec:
  interval: {"1m" if env == "production" else "5m"}
  sourceRef:
    kind: GitRepository
    name: {self.project_name}
  path: ./overlays/{env}
  prune: true
  wait: true
  timeout: {"5m" if env == "production" else "2m"}
"""

        return overlays

    def generate_bootstrap_script(self) -> str:
        """
        Generate Flux bootstrap script

        :return: Bootstrap script content
        """
        parsed = urlparse(self._repo_url_for_flux())
        host = parsed.netloc or ""
        path = (parsed.path or "").lstrip("/")
        owner = ""
        repo = ""
        if "/" in path:
            owner, repo = path.split("/", 1)
            repo = repo[:-4] if repo.endswith(".git") else repo

        extra_complex_block = ""
        if self.complexity_score > 1.3 and owner:
            extra_complex_block = f'''
# Additional setup for complex scenarios
flux create source git additional-configs \\
  --url=https://{host}/{owner}/additional-configs.git \\
  --branch=main \\
  --namespace="${{FLUX_NAMESPACE}}" || true
'''

        return f'''#!/bin/bash
# Flux Bootstrap Script for {self.project_name}
set -e

# Validate prerequisites
command -v flux >/dev/null 2>&1 || {{ echo >&2 "Flux CLI is not installed. Please install Flux."; exit 1; }}
command -v kubectl >/dev/null 2>&1 || {{ echo >&2 "kubectl is not installed. Please install kubectl."; exit 1; }}

REPO_URL="{self._repo_url_for_flux()}"
TARGET_REVISION="{self.target_revision}"
FLUX_NAMESPACE="flux-system"

if echo "$REPO_URL" | grep -q "github.com"; then
  GITHUB_OWNER="$(echo "$REPO_URL" | sed -E 's#https://github.com/([^/]+)/.*#\\1#')"
  GITHUB_REPO="$(echo "$REPO_URL" | sed -E 's#https://github.com/[^/]+/([^/.]+)(\\.git)?#\\1#')"
  flux bootstrap github \\
    --owner="${{GITHUB_OWNER}}" \\
    --repository="${{GITHUB_REPO}}" \\
    --branch="${{TARGET_REVISION}}" \\
    --path=./clusters/management \\
    --namespace="${{FLUX_NAMESPACE}}" \\
    {"--personal" if self.complexity_score < 1.3 else "--team"}
else
  echo "Non-GitHub URL detected. Installing Flux and creating GitRepository/Kustomization..."
  flux install --namespace="${{FLUX_NAMESPACE}}"
  kubectl apply -k "$PWD/flux-system"
fi
{extra_complex_block}

echo "Flux bootstrap/configuration complete."
'''

    def generate_documentation(self) -> str:
        """
        Generate documentation for Flux deployment

        :return: Markdown documentation
        """
        return f"""# Flux Deployment for {self.project_name}

## Project GitOps Configuration

### Deployment Complexity
- **Complexity Level**: {"Advanced" if self.complexity_score > 1.3 else "Standard"}
- **Reconciliation Interval**: {"1 minute" if self.complexity_score > 1.3 else "5 minutes"}

### Key Components
- Flux Source Controller
- Kustomize Controller
- GitRepository Configuration
- Automated Reconciliation

### Bootstrap Process
1. Install Flux CLI
2. Run `./bootstrap-flux.sh`
3. Verify deployment with `flux get kustomizations`

### Recommended Workflow
- Commit and push changes to configured Git repository
- Run `./scripts/post-terraform-deploy.sh` after Terraform apply
- Flux will reconcile source and kustomizations

### Troubleshooting
- Check Flux logs: `flux logs`
- Verify reconciliation: `flux get kustomizations`

*Generated by Project Initializer Flux Addon*
"""


def main(
    project_name: str,
    project_description: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Main entry point for Flux deployment generation.

    :param project_name: Name of the project
    :param project_description: Description of the project
    :param context: Additional context (platform, sizing_context, etc.)
    :return: Dictionary of generated files
    """
    flux_generator = FluxDeploymentGenerator(project_name, project_description, context)
    context = context or {}
    sizing_context = context.get("sizing_context") or {}
    eck_enabled = bool(
        sizing_context
        and (
            sizing_context.get("eck_operator")
            or sizing_context.get("source") == "sizing_report"
        )
    )

    # Generate files
    files = {}

    # Flux base manifests
    flux_manifests = flux_generator.generate_flux_manifests()
    for filename, content in flux_manifests.items():
        files[f"flux-system/{filename}"] = content

    # Base configuration for all services
    base_files = {
        "base/kustomization.yaml": f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: {project_name}
resources:
- deployment.yaml
- service.yaml
- ingress.yaml
""",
        "base/deployment.yaml": f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {project_name}
  labels:
    app: {project_name}
    managed-by: flux
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {project_name}
  template:
    metadata:
      labels:
        app: {project_name}
    spec:
      containers:
      - name: {project_name}
        image: {project_name}:latest
        ports:
        - containerPort: 8080
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 15
          periodSeconds: 5
""",
        "base/service.yaml": f"""apiVersion: v1
kind: Service
metadata:
  name: {project_name}
  labels:
    app: {project_name}
spec:
  selector:
    app: {project_name}
  ports:
  - port: 80
    targetPort: 8080
  type: ClusterIP
""",
        "base/ingress.yaml": f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {project_name}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - http:
      paths:
      - path: /{project_name}
        pathType: Prefix
        backend:
          service:
            name: {project_name}
            port:
              number: 80
""",
    }
    for filepath, content in base_files.items():
        files[filepath] = content

    # Apps directory with initial application definitions
    app_resources: List[str] = []
    if eck_enabled:
        # ECK operator goes to infrastructure (provides CRDs); ES/Kibana app resources stay in apps.
        app_resources.extend(
            [
                "../../elasticsearch",
                "../../kibana",
            ]
        )
    app_resources_yaml = "\n".join([f"- {res}" for res in app_resources])

    apps_files = {
        "apps/README.md": """# Application Definitions

This directory contains application-specific configurations for different microservices.

## Structure
- Each application should have its own subdirectory
- Include Kubernetes manifests, Kustomize overlays, and configuration files
""",
        "apps/kustomization.yaml": f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- {project_name}
""",
        f"apps/{project_name}/kustomization.yaml": f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
{app_resources_yaml}
""",
        f"apps/{project_name}/patches/dev-patch.yaml": f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {project_name}
spec:
  template:
    spec:
      containers:
      - name: {project_name}
        env:
        - name: ENVIRONMENT
          value: development
        - name: DEBUG
          value: "true"
""",
    }
    for filepath, content in apps_files.items():
        files[filepath] = content

    # Environment overlays
    env_overlays = flux_generator.generate_environment_overlays()
    for filepath, content in env_overlays.items():
        files[filepath] = content

    # Clusters directory for multi-cluster management
    clusters_files = {
        "clusters/README.md": """# Cluster Configurations

This directory contains cluster-specific configurations and GitOps management.

## Structure
- Each cluster should have its own subdirectory
- Include cluster-specific Flux configurations
""",
        "clusters/management/kustomization.yaml": """apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- ../../flux-system
- namespace.yaml
""",
        "clusters/management/namespace.yaml": f"""apiVersion: v1
kind: Namespace
metadata:
  name: {project_name}-mgmt
  labels:
    project: {project_name}
    environment: management
""",
    }
    for filepath, content in clusters_files.items():
        files[filepath] = content

    # Infrastructure directory
    infra_resources = [
        "../k8s/namespace.yaml",
        "local-path-provisioner.yaml",
        "storageclasses.yaml",
        "network-policy.yaml",
        "network-policy-allow-dns.yaml",
        "network-policy-allow-intra-namespace.yaml",
    ]
    if eck_enabled:
        infra_resources.append("network-policy-allow-eck-operator.yaml")
        infra_resources.append("../platform/eck-operator")
    infra_resources_yaml = "\n".join([f"  - {r}" for r in infra_resources])

    infrastructure_files = {
        "infrastructure/README.md": """# Shared Infrastructure Components

This directory contains shared infrastructure components used across environments.

## Components
- Common configurations
- Shared resources
- Cross-cutting concerns
""",
        "infrastructure/kustomization.yaml": f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
{infra_resources_yaml}
""",
        "infrastructure/network-policy.yaml": f"""apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {project_name}-default-deny
  namespace: {project_name}
spec:
  podSelector: {{}}
  policyTypes:
  - Ingress
  - Egress
""",
        "infrastructure/network-policy-allow-dns.yaml": f"""apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {project_name}-allow-dns
  namespace: {project_name}
spec:
  podSelector: {{}}
  policyTypes:
  - Egress
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
    ports:
    - protocol: UDP
      port: 53
    - protocol: TCP
      port: 53
""",
        "infrastructure/network-policy-allow-intra-namespace.yaml": f"""apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {project_name}-allow-intra-namespace
  namespace: {project_name}
spec:
  podSelector: {{}}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector: {{}}
  egress:
  - to:
    - podSelector: {{}}
""",
        "infrastructure/network-policy-allow-eck-operator.yaml": f"""apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {project_name}-allow-eck-operator
  namespace: {project_name}
spec:
  podSelector: {{}}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: elastic-system
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: elastic-system
""",
        "infrastructure/storageclasses.yaml": """apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: premium
  annotations:
    storageclass.kubernetes.io/is-default-class: "false"
provisioner: rancher.io/local-path
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete
---
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: standard
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: rancher.io/local-path
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete
""",
        "infrastructure/local-path-provisioner.yaml": Path(
            __file__
        ).resolve().parent.joinpath(
            "assets", "infrastructure", "local-path-provisioner.yaml"
        ).read_text(),
    }
    for filepath, content in infrastructure_files.items():
        files[filepath] = content

    # Bootstrap script
    files["scripts/bootstrap-flux.sh"] = flux_generator.generate_bootstrap_script()

    # Documentation
    files["docs/FLUX_DEPLOYMENT.md"] = flux_generator.generate_documentation()

    return files


if __name__ == "__main__":
    # Example usage for testing
    project_name = "test-project"
    project_description = "Multi-cluster Kubernetes platform with advanced GitOps"
    generated_files = main(project_name, project_description)

    # Print generated files
    for filepath, content in generated_files.items():
        print(f"File: {filepath}")
        print(content)
        print("-" * 50)
