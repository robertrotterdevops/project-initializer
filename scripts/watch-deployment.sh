#!/usr/bin/env bash
# watch-deployment.sh — Monitor a Flux-managed RKE2 deployment and capture errors
# Usage: ./scripts/watch-deployment.sh [project-name]
#
# Run this in a second terminal AFTER starting post-terraform-deploy.sh
# It polls until all kustomizations are Ready or a timeout is reached.

set -uo pipefail

PROJECT="${1:-$(basename "$PWD")}"
NAMESPACE="$PROJECT"
LOG_FILE="/tmp/${PROJECT}-deploy-$(date +%Y%m%d-%H%M%S).log"
TIMEOUT=900  # 15 minutes total
POLL=10      # seconds between checks

# --- Colors ---
RED='\033[0;31m'
YEL='\033[0;33m'
GRN='\033[0;32m'
RST='\033[0m'

log()  { echo -e "$(date '+%H:%M:%S') $*" | tee -a "$LOG_FILE"; }
info() { log "${GRN}[INFO]${RST} $*"; }
warn() { log "${YEL}[WARN]${RST} $*"; }
err()  { log "${RED}[ERR ]${RST} $*"; }

info "Monitoring deployment for project: $PROJECT"
info "Log file: $LOG_FILE"
info "Timeout: ${TIMEOUT}s"
echo "---" >> "$LOG_FILE"

# --- Wait for kubeconfig / cluster reachability ---
elapsed=0
info "Waiting for cluster API to become reachable..."
while ! kubectl cluster-info --request-timeout=5s &>/dev/null; do
  sleep "$POLL"
  elapsed=$((elapsed + POLL))
  if (( elapsed >= TIMEOUT )); then
    err "Cluster API not reachable after ${TIMEOUT}s — is KUBECONFIG set?"
    exit 1
  fi
done
info "Cluster API reachable."

# --- Phase 1: Wait for Flux namespace ---
info "Waiting for flux-system namespace..."
elapsed=0
while ! kubectl get ns flux-system &>/dev/null; do
  sleep "$POLL"
  elapsed=$((elapsed + POLL))
  if (( elapsed >= TIMEOUT )); then
    err "flux-system namespace not found after ${TIMEOUT}s"
    exit 1
  fi
done
info "flux-system namespace exists."

# --- Phase 2: Watch Flux kustomizations ---
KUSTOMIZATIONS=(
  "$PROJECT"
  "${PROJECT}-infra"
  "${PROJECT}-apps"
  "${PROJECT}-agents"
)

info "Tracking kustomizations: ${KUSTOMIZATIONS[*]}"
echo ""

check_kustomization() {
  local ks="$1"
  if ! kubectl get kustomization "$ks" -n flux-system &>/dev/null; then
    echo "pending"
    return
  fi
  local ready
  ready=$(kubectl get kustomization "$ks" -n flux-system \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
  local reason
  reason=$(kubectl get kustomization "$ks" -n flux-system \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].reason}' 2>/dev/null)
  local msg
  msg=$(kubectl get kustomization "$ks" -n flux-system \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].message}' 2>/dev/null)

  if [[ "$ready" == "True" ]]; then
    echo "ready"
  else
    echo "not-ready|${reason}|${msg}"
  fi
}

elapsed=0
declare -A ks_reported_ready

while (( elapsed < TIMEOUT )); do
  all_ready=true
  for ks in "${KUSTOMIZATIONS[@]}"; do
    result=$(check_kustomization "$ks")
    if [[ "$result" == "ready" ]]; then
      if [[ -z "${ks_reported_ready[$ks]:-}" ]]; then
        info "Kustomization $ks: ${GRN}Ready${RST}"
        ks_reported_ready[$ks]=1
      fi
    elif [[ "$result" == "pending" ]]; then
      all_ready=false
    else
      all_ready=false
      IFS='|' read -r _ reason msg <<< "$result"
      if [[ -n "$reason" ]]; then
        warn "Kustomization $ks: $reason — $msg"
      fi
    fi
  done

  # --- Check for failing pods in project namespace ---
  failing_pods=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null \
    | awk '$3 ~ /CrashLoop|Error|ImagePull|ErrImagePull|InvalidImage|CreateContainerConfigError/ {print $1, $3}')
  if [[ -n "$failing_pods" ]]; then
    err "Failing pods in $NAMESPACE:"
    while IFS= read -r line; do
      pod_name=$(echo "$line" | awk '{print $1}')
      pod_status=$(echo "$line" | awk '{print $2}')
      err "  $pod_name ($pod_status)"
      # Grab last 5 log lines for context
      kubectl logs "$pod_name" -n "$NAMESPACE" --tail=5 2>/dev/null \
        | sed "s/^/    /" | tee -a "$LOG_FILE"
    done <<< "$failing_pods"
  fi

  # --- Check for failing pods in observability namespace ---
  failing_obs=$(kubectl get pods -n observability --no-headers 2>/dev/null \
    | awk '$3 ~ /CrashLoop|Error|ImagePull|ErrImagePull|InvalidImage|CreateContainerConfigError/ {print $1, $3}')
  if [[ -n "$failing_obs" ]]; then
    err "Failing pods in observability:"
    while IFS= read -r line; do
      pod_name=$(echo "$line" | awk '{print $1}')
      pod_status=$(echo "$line" | awk '{print $2}')
      err "  $pod_name ($pod_status)"
      kubectl logs "$pod_name" -n observability --tail=5 2>/dev/null \
        | sed "s/^/    /" | tee -a "$LOG_FILE"
    done <<< "$failing_obs"
  fi

  # --- Check for stuck NetworkPolicy events ---
  netpol_events=$(kubectl get events -n "$NAMESPACE" --field-selector reason=NetworkPolicy \
    --sort-by='.lastTimestamp' --no-headers 2>/dev/null | tail -3)
  if [[ -n "$netpol_events" ]]; then
    warn "Recent NetworkPolicy events:"
    echo "$netpol_events" | sed "s/^/  /" | tee -a "$LOG_FILE"
  fi

  if $all_ready; then
    break
  fi

  sleep "$POLL"
  elapsed=$((elapsed + POLL))
done

echo ""
echo "========================================" | tee -a "$LOG_FILE"

# --- Final Summary ---
if $all_ready; then
  info "All kustomizations are Ready."
else
  err "Timeout reached — not all kustomizations are Ready."
fi

echo "" | tee -a "$LOG_FILE"
info "=== DEPLOYMENT SUMMARY ==="

# Flux status
echo "" | tee -a "$LOG_FILE"
info "--- Flux Kustomizations ---"
flux get kustomizations 2>/dev/null | tee -a "$LOG_FILE" || warn "flux CLI not available"

# Pod status
echo "" | tee -a "$LOG_FILE"
info "--- Pods ($NAMESPACE) ---"
kubectl get pods -n "$NAMESPACE" -o wide 2>/dev/null | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
info "--- Pods (observability) ---"
kubectl get pods -n observability -o wide 2>/dev/null | tee -a "$LOG_FILE" || true

echo "" | tee -a "$LOG_FILE"
info "--- Pods (elastic-system) ---"
kubectl get pods -n elastic-system -o wide 2>/dev/null | tee -a "$LOG_FILE" || true

# Collect all errors
echo "" | tee -a "$LOG_FILE"
info "--- Events with Errors (last 10min) ---"
for ns in "$NAMESPACE" observability elastic-system flux-system kube-system; do
  events=$(kubectl get events -n "$ns" --field-selector type=Warning \
    --sort-by='.lastTimestamp' --no-headers 2>/dev/null | tail -10)
  if [[ -n "$events" ]]; then
    err "Warnings in $ns:"
    echo "$events" | sed "s/^/  /" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
  fi
done

# NetworkPolicy audit
echo "" | tee -a "$LOG_FILE"
info "--- Network Policies ($NAMESPACE) ---"
kubectl get networkpolicies -n "$NAMESPACE" 2>/dev/null | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
info "--- Network Policies (observability) ---"
kubectl get networkpolicies -n observability 2>/dev/null | tee -a "$LOG_FILE" || true

# ES cluster health (if running)
echo "" | tee -a "$LOG_FILE"
ES_POD=$(kubectl get pod -n "$NAMESPACE" \
  -l "elasticsearch.k8s.elastic.co/cluster-name=${PROJECT}" \
  --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [[ -n "$ES_POD" ]]; then
  info "--- Elasticsearch Cluster Health ---"
  ES_PASS=$(kubectl get secret "${PROJECT}-es-elastic-user" -n "$NAMESPACE" \
    -o go-template='{{.data.elastic | base64decode}}' 2>/dev/null || true)
  if [[ -n "$ES_PASS" ]]; then
    kubectl exec -n "$NAMESPACE" "$ES_POD" -- \
      curl -sk -u "elastic:${ES_PASS}" \
      "https://localhost:9200/_cluster/health?pretty" 2>/dev/null \
      | tee -a "$LOG_FILE"
  fi
fi

echo "" | tee -a "$LOG_FILE"
info "Full log saved to: $LOG_FILE"
