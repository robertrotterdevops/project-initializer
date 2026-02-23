#!/usr/bin/env python3
"""
ArgoCD deployment addon for project-initializer.
Generates ArgoCD Application and AppProject manifests for GitOps deployments.

Zero external dependencies -- Python 3.9+ stdlib only.
"""

from typing import Any, Dict, Optional


ADDON_META = {
    "name": "argo_deployment",
    "version": "1.0",
    "description": "ArgoCD Application and AppProject generator",
    "triggers": {"gitops_tool": "argo"},
    "priority": 10,
}


class ArgoDeploymentGenerator:
    """Generates ArgoCD manifests for GitOps deployments."""
    
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
        self.repo_url = self.context.get("repo_url", f"https://github.com/org/{project_name}.git")
        self.target_revision = self.context.get("target_revision", "main")
        
        # Environments
        self.environments = ["dev", "staging", "production"]
    
    def generate(self) -> Dict[str, str]:
        """Generate all ArgoCD manifests."""
        files = {}
        
        # Core ArgoCD resources
        files["argocd/namespace.yaml"] = self._generate_namespace()
        files["argocd/appproject.yaml"] = self._generate_appproject()
        files["argocd/application.yaml"] = self._generate_application()
        
        # App-of-apps pattern
        files["argocd/apps/root-app.yaml"] = self._generate_root_app()
        
        # Per-environment applications
        for env in self.environments:
            files[f"argocd/apps/{env}-app.yaml"] = self._generate_env_app(env)
        
        # Overlays for each environment
        for env in self.environments:
            files[f"overlays/{env}/kustomization.yaml"] = self._generate_overlay_kustomization(env)
            files[f"overlays/{env}/namespace.yaml"] = self._generate_overlay_namespace(env)
        
        # Base kustomization
        files["base/kustomization.yaml"] = self._generate_base_kustomization()
        
        # Documentation
        files["argocd/README.md"] = self._generate_readme()
        
        # Sync scripts
        files["scripts/argocd-sync.sh"] = self._generate_sync_script()
        
        return files
    
    def _generate_namespace(self) -> str:
        """Generate namespace for ArgoCD resources."""
        return f"""apiVersion: v1
kind: Namespace
metadata:
  name: argocd
  labels:
    app.kubernetes.io/name: argocd
    app.kubernetes.io/part-of: {self.project_name}
"""
    
    def _generate_appproject(self) -> str:
        """Generate ArgoCD AppProject."""
        return f"""apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: {self.project_name}
  namespace: argocd
  labels:
    app.kubernetes.io/name: {self.project_name}
    app.kubernetes.io/component: appproject
  # Finalizer to prevent accidental deletion
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  description: "{self.description}"
  
  # Source repositories
  sourceRepos:
    - "{self.repo_url}"
    - "https://helm.elastic.co"
    - "https://charts.bitnami.com/bitnami"
  
  # Destination clusters and namespaces
  destinations:
    # Dev environment
    - namespace: "{self.project_name}-dev"
      server: "https://kubernetes.default.svc"
    # Staging environment
    - namespace: "{self.project_name}-staging"
      server: "https://kubernetes.default.svc"
    # Production environment
    - namespace: "{self.project_name}-production"
      server: "https://kubernetes.default.svc"
    # ArgoCD namespace for app-of-apps
    - namespace: "argocd"
      server: "https://kubernetes.default.svc"
  
  # Cluster resource allowlist
  clusterResourceWhitelist:
    - group: ""
      kind: Namespace
    - group: "rbac.authorization.k8s.io"
      kind: ClusterRole
    - group: "rbac.authorization.k8s.io"
      kind: ClusterRoleBinding
    - group: "elasticsearch.k8s.elastic.co"
      kind: Elasticsearch
    - group: "kibana.k8s.elastic.co"
      kind: Kibana
    - group: "agent.k8s.elastic.co"
      kind: Agent
  
  # Namespace resource denylist (security)
  namespaceResourceBlacklist:
    - group: ""
      kind: ResourceQuota
    - group: ""
      kind: LimitRange
  
  # Roles for project members
  roles:
    - name: developer
      description: "Developer access - can sync applications"
      policies:
        - p, proj:{self.project_name}:developer, applications, get, {self.project_name}/*, allow
        - p, proj:{self.project_name}:developer, applications, sync, {self.project_name}/*, allow
      groups:
        - developers
    
    - name: admin
      description: "Admin access - full control"
      policies:
        - p, proj:{self.project_name}:admin, applications, *, {self.project_name}/*, allow
        - p, proj:{self.project_name}:admin, repositories, *, {self.project_name}/*, allow
      groups:
        - admins
"""
    
    def _generate_application(self) -> str:
        """Generate main ArgoCD Application."""
        return f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {self.project_name}
  namespace: argocd
  labels:
    app.kubernetes.io/name: {self.project_name}
    app.kubernetes.io/component: application
  # Finalizer for cascade deletion
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: {self.project_name}
  
  source:
    repoURL: "{self.repo_url}"
    targetRevision: {self.target_revision}
    path: overlays/dev
  
  destination:
    server: "https://kubernetes.default.svc"
    namespace: {self.project_name}-dev
  
  # Sync policy
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - PruneLast=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  
  # Health checks
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
"""
    
    def _generate_root_app(self) -> str:
        """Generate root app for app-of-apps pattern."""
        return f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {self.project_name}-apps
  namespace: argocd
  labels:
    app.kubernetes.io/name: {self.project_name}
    app.kubernetes.io/component: root-app
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: {self.project_name}
  
  source:
    repoURL: "{self.repo_url}"
    targetRevision: {self.target_revision}
    path: argocd/apps
  
  destination:
    server: "https://kubernetes.default.svc"
    namespace: argocd
  
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
"""
    
    def _generate_env_app(self, env: str) -> str:
        """Generate per-environment application."""
        # Production has manual sync, others are automated
        if env == "production":
            sync_policy = """  syncPolicy:
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
    # Production: Manual sync required
    # automated: {}"""
        else:
            sync_policy = """  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground"""
        
        return f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {self.project_name}-{env}
  namespace: argocd
  labels:
    app.kubernetes.io/name: {self.project_name}
    app.kubernetes.io/component: {env}
    environment: {env}
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: {self.project_name}
  
  source:
    repoURL: "{self.repo_url}"
    targetRevision: {self.target_revision}
    path: overlays/{env}
  
  destination:
    server: "https://kubernetes.default.svc"
    namespace: {self.project_name}-{env}
  
{sync_policy}
"""
    
    def _generate_overlay_kustomization(self, env: str) -> str:
        """Generate kustomization.yaml for environment overlay."""
        replicas = {"dev": 1, "staging": 2, "production": 3}.get(env, 1)
        
        return f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: {self.project_name}-{env}

resources:
  - ../../base
  - namespace.yaml

commonLabels:
  environment: {env}
  app.kubernetes.io/part-of: {self.project_name}

# Environment-specific patches
patches:
  - target:
      kind: Deployment
    patch: |-
      - op: replace
        path: /spec/replicas
        value: {replicas}

# Environment-specific config
configMapGenerator:
  - name: {self.project_name}-config
    behavior: merge
    literals:
      - ENVIRONMENT={env}
      - LOG_LEVEL={"debug" if env == "dev" else "info" if env == "staging" else "warn"}
"""
    
    def _generate_overlay_namespace(self, env: str) -> str:
        """Generate namespace for environment overlay."""
        return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {self.project_name}-{env}
  labels:
    app.kubernetes.io/name: {self.project_name}
    environment: {env}
"""
    
    def _generate_base_kustomization(self) -> str:
        """Generate base kustomization.yaml."""
        return f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

commonLabels:
  app.kubernetes.io/name: {self.project_name}
  app.kubernetes.io/managed-by: argocd

resources:
  # Add your base resources here
  # - deployment.yaml
  # - service.yaml
  # - configmap.yaml

# ConfigMap generator
configMapGenerator:
  - name: {self.project_name}-config
    literals:
      - APP_NAME={self.project_name}
"""
    
    def _generate_readme(self) -> str:
        """Generate README for argocd directory."""
        return f"""# ArgoCD Configuration: {self.project_name}

## Overview

This directory contains ArgoCD Application and AppProject manifests for GitOps-based deployments.

## Structure

```
argocd/
├── namespace.yaml      # ArgoCD namespace
├── appproject.yaml     # AppProject definition
├── application.yaml    # Main application
├── apps/
│   ├── root-app.yaml   # App-of-apps root
│   ├── dev-app.yaml    # Dev environment
│   ├── staging-app.yaml
│   └── production-app.yaml
└── README.md
```

## Prerequisites

1. ArgoCD installed in the cluster:
   ```bash
   kubectl create namespace argocd
   kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
   ```

2. ArgoCD CLI installed (optional):
   ```bash
   brew install argocd  # macOS
   ```

## Deployment

### Bootstrap (first time)

```bash
# Apply AppProject first
kubectl apply -f argocd/appproject.yaml

# Apply root app (app-of-apps)
kubectl apply -f argocd/apps/root-app.yaml
```

### Access ArgoCD UI

```bash
# Get admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{{.data.password}}" | base64 -d

# Port-forward
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Then visit: https://localhost:8080

## Environments

| Environment | Auto-sync | Namespace |
|-------------|-----------|-----------|
| dev | Yes | {self.project_name}-dev |
| staging | Yes | {self.project_name}-staging |
| production | No (manual) | {self.project_name}-production |

## Sync Applications

### Via CLI

```bash
# Sync dev
argocd app sync {self.project_name}-dev

# Sync all
argocd app sync {self.project_name}-apps
```

### Via Script

```bash
./scripts/argocd-sync.sh dev
./scripts/argocd-sync.sh staging
./scripts/argocd-sync.sh production
```

## RBAC

Two roles are defined in the AppProject:
- **developer**: Can view and sync applications
- **admin**: Full control over applications and repositories
"""
    
    def _generate_sync_script(self) -> str:
        """Generate sync helper script."""
        return f"""#!/usr/bin/env bash
# ArgoCD sync script for {self.project_name}

set -euo pipefail

ENV="${{1:-dev}}"
APP_NAME="{self.project_name}-$ENV"

echo "Syncing $APP_NAME..."

if command -v argocd &> /dev/null; then
    argocd app sync "$APP_NAME" --prune
    argocd app wait "$APP_NAME" --health
else
    echo "ArgoCD CLI not found. Using kubectl..."
    kubectl patch application "$APP_NAME" -n argocd \\
        --type merge \\
        -p '{{"operation": {{"initiatedBy": {{"username": "script"}}, "sync": {{"prune": true}}}}}}'
fi

echo "Sync complete!"
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
        context: Additional context (platform, repo_url, etc.)
    
    Returns:
        Dict of {filepath: content} for generated files
    """
    generator = ArgoDeploymentGenerator(project_name, description, context)
    return generator.generate()


if __name__ == "__main__":
    # Test generation
    files = main("test-cluster", "Test Elasticsearch cluster with ArgoCD", {
        "platform": "openshift",
        "repo_url": "https://github.com/myorg/test-cluster.git",
    })
    
    print("Generated files:")
    for filepath in sorted(files.keys()):
        print(f"  - {filepath}")
