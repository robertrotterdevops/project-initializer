#!/usr/bin/env python3
"""
Flux Deployment Addon for Project Initializer

Extends the project initialization process with robust Flux GitOps deployment capabilities.
"""

import json
import os
import re
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
        self.complexity_score = self._calculate_complexity()

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
  url: https://github.com/your-org/{self.project_name}
  ref:
    branch: main
  ignore: |
    # Exclude files from synchronization
    /*.md
    /docs
    /scripts
    /overlays
"""

        # Kustomization manifest with dynamic reconciliation
        reconciliation_interval = "5m" if self.complexity_score < 1.3 else "1m"
        manifests["kustomization.yaml"] = f"""apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {self.project_name}
  namespace: flux-system
spec:
  interval: {reconciliation_interval}
  sourceRef:
    kind: GitRepository
    name: {self.project_name}
  path: ./base
  prune: true
  wait: true
  timeout: {"2m" if self.complexity_score < 1.3 else "5m"}
  validation: server
"""

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
        return f'''#!/bin/bash
# Flux Bootstrap Script for {self.project_name}
set -e

# Validate prerequisites
command -v flux >/dev/null 2>&1 || {{ echo >&2 "Flux CLI is not installed. Please install Flux."; exit 1; }}
command -v kubectl >/dev/null 2>&1 || {{ echo >&2 "kubectl is not installed. Please install kubectl."; exit 1; }}

# Variables
GITHUB_OWNER="your-github-username"
GITHUB_REPO="{self.project_name}"
CLUSTER_NAME="{self.project_name}-cluster"
FLUX_NAMESPACE="flux-system"

# Bootstrap Flux
flux bootstrap github \\
  --owner=${{GITHUB_OWNER}} \\
  --repository=${{GITHUB_REPO}} \\
  --branch=main \\
  --path=./clusters/${{CLUSTER_NAME}} \\
  --namespace=${{FLUX_NAMESPACE}} \\
  {"--personal" if self.complexity_score < 1.3 else "--team"}

# Additional setup for more complex scenarios
if [ {self.complexity_score} -gt 1.3 ]; then
    flux create source git additional-configs \\
      --url=https://github.com/${{GITHUB_OWNER}}/additional-configs \\
      --branch=main \\
      --namespace=${{FLUX_NAMESPACE}}
    
    flux create kustomization additional-configs \\
      --source=additional-configs \\
      --path=./clusters/${{CLUSTER_NAME}} \\
      --prune=true \\
      --wait=true
fi

echo "Flux bootstrapped successfully for ${{CLUSTER_NAME}}"
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
- Commit changes to Git repository
- Flux will automatically synchronize cluster state

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
        "base/kustomization.yaml": """apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
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
    app_resources = ["../../base"]
    if eck_enabled:
        app_resources.extend(
            [
                "../../platform/eck-operator",
                "../../elasticsearch",
                "../../kibana",
                "../../agents",
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
- ../../apps
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
    infrastructure_files = {
        "infrastructure/README.md": """# Shared Infrastructure Components

This directory contains shared infrastructure components used across environments.

## Components
- Common configurations
- Shared resources
- Cross-cutting concerns
""",
        "infrastructure/network-policy.yaml": f"""apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {project_name}-default-deny
spec:
  podSelector: {{}}
  policyTypes:
  - Ingress
  - Egress
""",
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
