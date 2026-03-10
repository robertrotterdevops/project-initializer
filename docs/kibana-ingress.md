# Kibana Ingress — Scaffolding Reference

Exposes Kibana (deployed via ECK) through the RKE2 built-in nginx ingress controller.
Use `{{ cluster_name }}` as a placeholder when generating these resources for a new cluster.

---

## Files to Create

### `kibana/ingress.yaml`

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ cluster_name }}-kibana
  namespace: {{ cluster_name }}
  annotations:
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
    nginx.ingress.kubernetes.io/ssl-redirect: "false"
spec:
  ingressClassName: nginx
  rules:
    - host: {{ cluster_name }}.lan
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ cluster_name }}-kb-http
                port:
                  number: 5601
```

**Notes:**
- `backend-protocol: HTTPS` — ECK always serves Kibana over TLS on port 5601; nginx must proxy with HTTPS.
- `ssl-redirect: false` — prevents redirect loops when TLS is not terminated at the ingress level.
- Service name `{{ cluster_name }}-kb-http` is the ECK naming convention for the Kibana HTTP service.

---

### `infrastructure/network-policy-allow-ingress-nginx.yaml`

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ cluster_name }}-allow-ingress-nginx
  namespace: {{ cluster_name }}
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
    ports:
    - protocol: TCP
      port: 5601
```

**Notes:**
- The RKE2 nginx ingress controller runs as a DaemonSet in `kube-system`.
- The namespace default-deny policy blocks all ingress unless explicitly allowed.
- This policy follows the same pattern as `network-policy-allow-eck-operator.yaml`.

---

## Files to Patch

### `kibana/kustomization.yaml` — add `ingress.yaml`

```yaml
resources:
  - kibana.yaml
  - ingress.yaml
```

### `infrastructure/kustomization.yaml` — add the new network policy

```yaml
resources:
  - ../k8s/namespace.yaml
  - local-path-provisioner.yaml
  - storageclasses.yaml
  - network-policy.yaml
  - network-policy-allow-dns.yaml
  - network-policy-allow-intra-namespace.yaml
  - network-policy-allow-eck-operator.yaml
  - network-policy-allow-ingress-nginx.yaml
  - ../platform/eck-operator
```

---

## /etc/hosts Entry (client machine)

```
<server-node-ip>  {{ cluster_name }}.lan
```

For `rke2-5`: `192.168.0.98  rke2-5.lan`

The server node IP is the RKE2 node where the nginx DaemonSet pod runs and binds to ports 80/443.

---

## Verification

```bash
# Confirm ingress was created
KUBECONFIG=~/.kube/{{ cluster_name }} kubectl get ingress -n {{ cluster_name }}

# Inspect nginx routing rule
KUBECONFIG=~/.kube/{{ cluster_name }} kubectl describe ingress {{ cluster_name }}-kibana -n {{ cluster_name }}

# Test access (requires /etc/hosts entry on the client)
curl -k http://{{ cluster_name }}.lan
```

Expected: HTTP 200 or redirect to `/login` — Kibana login page.

---

## Architecture Notes

| Component | Detail |
|-----------|--------|
| Ingress controller | RKE2 nginx DaemonSet in `kube-system` |
| Kibana service | `{{ cluster_name }}-kb-http` (ECK-managed, HTTPS, port 5601) |
| TLS handling | nginx proxies to Kibana over HTTPS; no TLS termination at ingress |
| Network policy model | Default-deny all; explicit allow rules per traffic source |
| Hostname pattern | `{{ cluster_name }}.lan` |
