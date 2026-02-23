#!/bin/bash
# Flux Bootstrap Script for es-ocp-e2e
set -e

# Validate prerequisites
command -v flux >/dev/null 2>&1 || { echo >&2 "Flux CLI is not installed. Please install Flux."; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo >&2 "kubectl is not installed. Please install kubectl."; exit 1; }

# Variables
GITHUB_OWNER="your-github-username"
GITHUB_REPO="es-ocp-e2e"
CLUSTER_NAME="es-ocp-e2e-cluster"
FLUX_NAMESPACE="flux-system"

# Bootstrap Flux
flux bootstrap github \
  --owner=${GITHUB_OWNER} \
  --repository=${GITHUB_REPO} \
  --branch=main \
  --path=./clusters/${CLUSTER_NAME} \
  --namespace=${FLUX_NAMESPACE} \
  --personal

# Additional setup for more complex scenarios
if [ 1.0 -gt 1.3 ]; then
    flux create source git additional-configs \
      --url=https://github.com/${GITHUB_OWNER}/additional-configs \
      --branch=main \
      --namespace=${FLUX_NAMESPACE}
    
    flux create kustomization additional-configs \
      --source=additional-configs \
      --path=./clusters/${CLUSTER_NAME} \
      --prune=true \
      --wait=true
fi

echo "Flux bootstrapped successfully for ${CLUSTER_NAME}"
