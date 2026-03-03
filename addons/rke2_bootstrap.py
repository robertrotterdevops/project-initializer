#!/usr/bin/env python3
"""
RKE2 bootstrap addon.
Generates post-Terraform bootstrap assets for provisioning RKE2 on created VMs.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


ADDON_META = {
    "name": "rke2_bootstrap",
    "version": "1.0",
    "description": "RKE2 bootstrap scripts and Ansible assets for post-terraform cluster build",
    "triggers": {"platforms": ["rke2", "proxmox"], "iac_tools": ["terraform"]},
    "priority": 17,
}


def _bootstrap_script(project_name: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "ansible-playbook not found. Install Ansible and re-run."
  exit 1
fi

if [ ! -f terraform/terraform.tfstate ]; then
  echo "terraform state not found. Run terraform apply first."
  exit 1
fi

echo "[1/4] Exporting Terraform outputs..."
cd terraform
terraform output -json > "$ROOT_DIR/.tmp-terraform-outputs.json"
cd "$ROOT_DIR"

echo "[2/4] Building inventory from VM outputs..."
python3 scripts/render-rke2-inventory.py \
  --project-name "{project_name}" \
  --tf-output "$ROOT_DIR/.tmp-terraform-outputs.json" \
  --template ansible/inventory.tpl.ini \
  --out ansible/inventory.ini

echo "[3/4] Running RKE2 bootstrap playbook..."
ansible-galaxy install -r ansible/requirements.yml >/dev/null 2>&1 || true
ansible-playbook -i ansible/inventory.ini ansible/rke2-bootstrap.yml

echo "[4/4] Bootstrap complete. kubeconfig expected at ~/.kube/config or /etc/rancher/rke2/rke2.yaml on server nodes."
"""


def _inventory_renderer() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _infer_hosts(tf: dict) -> tuple[list[str], list[str]]:
    names = []
    outputs = tf.get("vm_names", {})
    if isinstance(outputs, dict):
        value = outputs.get("value")
        if isinstance(value, list):
            names = [str(v) for v in value]

    # Deterministic fallback when IP outputs are unavailable:
    # first node => server, others => agents.
    servers = names[:1]
    agents = names[1:]
    if not servers:
        servers = ["rke2-server-1"]
    return servers, agents


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--tf-output", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    tf_data = json.loads(Path(args.tf_output).read_text())
    template = Path(args.template).read_text()

    servers, agents = _infer_hosts(tf_data)

    rendered = template.replace("{{ project_name }}", args.project_name)
    rendered = rendered.replace("{{ servers }}", "\n".join(servers))
    rendered = rendered.replace("{{ agents }}", "\n".join(agents) if agents else "")

    Path(args.out).write_text(rendered)


if __name__ == "__main__":
    main()
"""


def _inventory_template() -> str:
    return """[rke2_servers]
{{ servers }}

[rke2_agents]
{{ agents }}

[all:vars]
ansible_user=ubuntu
project_name={{ project_name }}
rke2_version=v1.30.4+rke2r1
"""


def _ansible_playbook() -> str:
    return """---
- name: Bootstrap RKE2 servers
  hosts: rke2_servers
  become: true
  tasks:
    - name: Install RKE2 server
      shell: |
        curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=server sh -
      args:
        creates: /usr/local/bin/rke2

    - name: Enable and start RKE2 server
      systemd:
        name: rke2-server
        enabled: true
        state: started

    - name: Read server token
      slurp:
        src: /var/lib/rancher/rke2/server/node-token
      register: rke2_token_raw

    - name: Set cluster token fact
      set_fact:
        rke2_cluster_token: "{{ rke2_token_raw.content | b64decode | trim }}"

- name: Bootstrap RKE2 agents
  hosts: rke2_agents
  become: true
  vars:
    rke2_server_endpoint: "https://{{ groups['rke2_servers'][0] }}:9345"
    rke2_cluster_token: "{{ hostvars[groups['rke2_servers'][0]].rke2_cluster_token }}"
  tasks:
    - name: Install RKE2 agent
      shell: |
        curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=agent sh -
      args:
        creates: /usr/local/bin/rke2

    - name: Write RKE2 agent config
      copy:
        dest: /etc/rancher/rke2/config.yaml
        mode: "0600"
        content: |
          server: {{ rke2_server_endpoint }}
          token: {{ rke2_cluster_token }}

    - name: Enable and start RKE2 agent
      systemd:
        name: rke2-agent
        enabled: true
        state: started
"""


def _requirements() -> str:
    return """---
collections:
  - name: ansible.posix
  - name: community.general
"""


def _docs() -> str:
    return """# RKE2 Bootstrap Guide

This project includes an automated post-Terraform RKE2 bootstrap stage.

## Flow

1. `terraform apply` creates VMs.
2. `scripts/bootstrap-rke2.sh` renders `ansible/inventory.ini` from Terraform outputs.
3. Ansible installs and starts RKE2 server/agent services.
4. GitOps reconcile deploys platform and Elastic manifests.

## Commands

```bash
./scripts/bootstrap-rke2.sh
```

## Required Manual Inputs

- Ensure SSH from execution host to created VMs works (`ansible_user`, keys).
- Confirm VM template has cloud-init and package prerequisites.
- If hostnames are not resolvable, replace inventory entries with IPs.
- Validate firewall allows 9345/tcp and 6443/tcp between nodes.
"""


def main(project_name: str, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    ctx = context or {}
    if (ctx.get("iac_tool") or "").lower() != "terraform":
        return {}

    platform = (ctx.get("platform") or "").lower()
    if platform not in {"rke2", "proxmox"}:
        return {}

    return {
        "scripts/bootstrap-rke2.sh": _bootstrap_script(project_name),
        "scripts/render-rke2-inventory.py": _inventory_renderer(),
        "ansible/inventory.tpl.ini": _inventory_template(),
        "ansible/rke2-bootstrap.yml": _ansible_playbook(),
        "ansible/requirements.yml": _requirements(),
        "docs/RKE2_BOOTSTRAP.md": _docs(),
    }
