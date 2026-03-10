# Workflow: RKE2-4 Agent Onboarding — Diagnosis & Fix

## Overview

This document captures every step taken to diagnose and fix missing Elastic Agent
onboarding in the RKE2-4 cluster. Use it to rebuild the same setup from scratch or
troubleshoot a regression.

---

## 1. Self-Contained Kubeconfig Fetch

### Problem
`scripts/cluster-healthcheck.sh` assumed `kubectl` was already configured.
Running it on a fresh host or after a kubeconfig rotation would fail silently.

### Change
**File:** `scripts/cluster-healthcheck.sh`
**Commit:** `b83bb55`

Prepended the following block after the variable declarations (lines 4–8),
before the first `sep` call:

```bash
# ── Kubeconfig retrieval ────────────────────────────────────────────────────
INVENTORY="$(cd "$(dirname "$0")/../ansible" && pwd)/inventory.ini"

SERVER_IP=$(awk '/^\[rke2_servers\]/{f=1;next} f && /ansible_host=/{match($0,/ansible_host=([^ \t]+)/,a); print a[1]; exit} /^\[/{f=0}' "$INVENTORY")
SSH_USER=$(awk -F= '/^ansible_user=/{print $2}' "$INVENTORY" | tr -d '[:space:]')
SSH_PASS=$(awk -F= '/^ansible_ssh_pass=/{print $2}' "$INVENTORY" | tr -d '[:space:]')

KUBECONFIG_DIR="$HOME/.kube"
KUBECONFIG_FILE="$KUBECONFIG_DIR/rke2-4"
mkdir -p "$KUBECONFIG_DIR"

echo ">>> Fetching kubeconfig from ${SSH_USER}@${SERVER_IP} ..."
sshpass -p "$SSH_PASS" ssh \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  "${SSH_USER}@${SERVER_IP}" \
  "sudo cat /etc/rancher/rke2/rke2.yaml" \
  > "$KUBECONFIG_FILE"
chmod 600 "$KUBECONFIG_FILE"

sed -i "s|https://127.0.0.1:6443|https://${SERVER_IP}:6443|g" "$KUBECONFIG_FILE"
export KUBECONFIG="$KUBECONFIG_FILE"
echo ">>> KUBECONFIG set to $KUBECONFIG_FILE (server: $SERVER_IP)"
# ────────────────────────────────────────────────────────────────────────────
```

### Prerequisite
```bash
sudo apt install sshpass   # Ubuntu
```

### Values sourced from `ansible/inventory.ini`
| Variable    | Value         |
|-------------|---------------|
| SERVER_IP   | 192.168.0.167 |
| SSH_USER    | ubuntu        |
| SSH_PASS    | ubuntu        |

---

## 2. Dedicated Flux Kustomization for Agents

### Problem
`flux get kustomizations` showed no "agents" entry. Elastic Agents were bundled
as a plain Kustomize resource inside `rke2-4-apps` via a cross-boundary reference
(`../../agents` from within `./apps`). This meant:
- No independent sync/reconcile for agents
- Agent failures hidden inside broad `rke2-4-apps` status
- Cross-boundary paths risk being silently skipped in some Flux versions

### Changes
**Commit:** `6ba89e4`

#### A. New file: `flux-system/kustomization-agents.yaml`
```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: rke2-4-agents
  namespace: flux-system
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: rke2-4
  path: ./agents
  prune: true
  wait: true
  timeout: 10m
  dependsOn:
  - name: rke2-4-apps
```

#### B. Modified: `flux-system/kustomization.yaml`
Added `kustomization-agents.yaml` to the resources list:
```yaml
resources:
- ...existing entries...
- kustomization-agents.yaml   # ← added
```

#### C. Modified: `apps/rke2-4/kustomization.yaml`
Removed the cross-boundary `../../agents` entry:
```yaml
resources:
- ../../elasticsearch
- ../../kibana
# - ../../agents   ← removed; now managed by rke2-4-agents Kustomization
```

### Result after apply
```
NAME               READY
rke2-4             True
rke2-4-infra       True
rke2-4-apps        True
rke2-4-agents      True   ← new, independently reconcilable
```

### How to force-sync after push
```bash
flux reconcile source git rke2-4
flux reconcile kustomization rke2-4 rke2-4-infra rke2-4-apps rke2-4-agents
```

---

## 3. Network Policy — Allow ECK Operator Ingress

### Problem
`rke2-4-default-deny` NetworkPolicy blocked ALL ingress and egress on the `rke2-4`
namespace. The ECK operator (`elastic-operator` pod in `elastic-system`) could not
reach Kibana on port 5601 to POST `/api/fleet/setup`.

**Symptom in ECK operator logs:**
```
Reconciliation error: Post "https://rke2-4-kb-http.rke2-4.svc:5601/api/fleet/setup":
  net/http: request canceled while waiting for connection
  (Client.Timeout exceeded while awaiting headers)
```

**Diagnostic commands used:**
```bash
kubectl describe agent rke2-4-fleet-server -n rke2-4
kubectl logs -n elastic-system -l control-plane=elastic-operator --tail=60
kubectl get networkpolicies -n rke2-4 -o yaml
```

### Change
**File:** `infrastructure/network-policy-allow-eck-operator.yaml` (new)
**File:** `infrastructure/kustomization.yaml` (added reference)
**Commit:** `2207988`

#### New file: `infrastructure/network-policy-allow-eck-operator.yaml`
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: rke2-4-allow-eck-operator
  namespace: rke2-4
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: elastic-system
```

#### Modified: `infrastructure/kustomization.yaml`
```yaml
resources:
  - ...
  - network-policy-allow-intra-namespace.yaml
  - network-policy-allow-eck-operator.yaml   # ← added
```

### How to apply without waiting for git push
```bash
kubectl apply -f infrastructure/network-policy-allow-eck-operator.yaml
```

### Verify
```bash
kubectl get networkpolicies -n rke2-4
# Expect: rke2-4-allow-eck-operator listed
```

---

## 4. Kibana Fleet Preconfiguration

### Problem
Even after the network policy was fixed, ECK still reported:
```
Reconciliation error: no matching agent policy found
```

**Root cause:** Kibana had no `xpack.fleet.agentPolicies` configuration.
Without it, Kibana's Fleet setup never creates the default Fleet Server Policy.
ECK queries Kibana for a policy with `is_default_fleet_server: true` — finding
none, it fails to create the Fleet Server deployment.

**Diagnostic command:**
```bash
# From any pod in the rke2-4 namespace:
kubectl exec -n rke2-4 rke2-4-es-hot-0 -- \
  curl -sk -u "elastic:<PASSWORD>" \
  "https://rke2-4-kb-http.rke2-4.svc:5601/api/fleet/agent_policies" \
  -H "kbn-xsrf: true"
# Expected broken state: {"items":[],"total":0}
```

### Change
**File:** `kibana/kibana.yaml`
**Commit:** `2207988`

Added `config` block to the Kibana spec:
```yaml
spec:
  config:
    xpack.fleet.packages:
      - name: fleet_server
        version: latest
      - name: elastic_agent
        version: latest
      - name: system
        version: latest
      - name: kubernetes
        version: latest
    xpack.fleet.agentPolicies:
      - name: "Fleet Server Policy"
        id: fleet-server-policy
        is_default_fleet_server: true
        package_policies:
          - name: fleet_server-1
            id: fleet_server-1
            package:
              name: fleet_server
      - name: "Elastic Agent Policy"
        id: elastic-agent-policy
        is_default: true
        package_policies:
          - name: system-1
            id: system-1
            package:
              name: system
          - name: kubernetes-1
            id: kubernetes-1
            package:
              name: kubernetes
```

### How to apply without waiting for git push
```bash
kubectl apply -f kibana/kibana.yaml
# Kibana pod will restart — takes ~60–90s
```

### Verify Fleet policies were created
```bash
kubectl exec -n rke2-4 rke2-4-es-hot-0 -- \
  curl -sk -u "elastic:<PASSWORD>" \
  "https://rke2-4-kb-http.rke2-4.svc:5601/api/fleet/agent_policies" \
  -H "kbn-xsrf: true" | python3 -m json.tool | grep '"name"'
# Expected: "Fleet Server Policy", "Elastic Agent Policy"
```

---

## 5. End-to-End Verification

### Final state after all changes
```bash
kubectl get agents -n rke2-4
# NAME                  HEALTH   AVAILABLE   EXPECTED   VERSION
# rke2-4-agent          green    3           3          8.17.0
# rke2-4-fleet-server   green    1           1          8.17.0

kubectl get pods -n rke2-4
# rke2-4-agent-agent-*         1/1 Running  (x3, DaemonSet)
# rke2-4-fleet-server-agent-*  1/1 Running  (x1, Deployment)

flux get kustomizations
# rke2-4             True
# rke2-4-infra       True
# rke2-4-apps        True
# rke2-4-agents      True
```

---

## 6. Rebuild Checklist (apply in order)

| Step | Action | File(s) |
|------|--------|---------|
| 1 | Add kubeconfig fetch block to healthcheck script | `scripts/cluster-healthcheck.sh` |
| 2 | Create dedicated agents Flux Kustomization | `flux-system/kustomization-agents.yaml` |
| 3 | Register it in flux-system kustomization | `flux-system/kustomization.yaml` |
| 4 | Remove agents from apps kustomization | `apps/rke2-4/kustomization.yaml` |
| 5 | Create ECK operator network policy | `infrastructure/network-policy-allow-eck-operator.yaml` |
| 6 | Register network policy in infrastructure | `infrastructure/kustomization.yaml` |
| 7 | Add Fleet preconfiguration to Kibana | `kibana/kibana.yaml` |
| 8 | Push to git, force Flux sync | `git push` + `flux reconcile` |

### Flux force-sync commands
```bash
# If kubeconfig is stale (common after reboots):
sshpass -p ubuntu ssh -o StrictHostKeyChecking=no ubuntu@192.168.0.167 \
  "sudo cat /etc/rancher/rke2/rke2.yaml" > ~/.kube/rke2-4
chmod 600 ~/.kube/rke2-4
sed -i "s|https://127.0.0.1:6443|https://192.168.0.167:6443|g" ~/.kube/rke2-4
export KUBECONFIG=~/.kube/rke2-4

# Force full sync:
flux reconcile source git rke2-4
flux reconcile kustomization rke2-4-infra --with-source
flux reconcile kustomization rke2-4-apps --with-source
flux reconcile kustomization rke2-4-agents
```

---
