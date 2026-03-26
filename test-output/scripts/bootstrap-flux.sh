#!/bin/bash
# Flux Bootstrap Script for test-project
set -e

# Validate prerequisites
command -v flux >/dev/null 2>&1 || { echo >&2 "Flux CLI is not installed. Please install Flux."; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo >&2 "kubectl is not installed. Please install kubectl."; exit 1; }

REPO_URL="https://github.com/your-org/test-project.git"
TARGET_REVISION="main"
FLUX_NAMESPACE="flux-system"

if echo "$REPO_URL" | grep -q "github.com"; then
  GITHUB_OWNER="$(echo "$REPO_URL" | sed -E 's#https://github.com/([^/]+)/.*#\1#')"
  GITHUB_REPO="$(echo "$REPO_URL" | sed -E 's#https://github.com/[^/]+/([^/.]+)(\.git)?#\1#')"
  flux bootstrap github \
    --owner="${GITHUB_OWNER}" \
    --repository="${GITHUB_REPO}" \
    --branch="${TARGET_REVISION}" \
    --path=./clusters/management \
    --namespace="${FLUX_NAMESPACE}" \
    --personal
else
  echo "Non-GitHub URL detected. Installing Flux and creating GitRepository/Kustomization..."
  flux install --namespace="${FLUX_NAMESPACE}"
  kubectl apply -k "$PWD/flux-system"
fi


echo "Flux bootstrap/configuration complete."
