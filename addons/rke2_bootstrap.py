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

ANSIBLE_USER="${{ANSIBLE_USER:-ubuntu}}"
ANSIBLE_SSH_PASS="${{ANSIBLE_SSH_PASS:-ubuntu}}"

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
  --out ansible/inventory.ini \
  --ansible-user "$ANSIBLE_USER" \
  --ssh-pass "$ANSIBLE_SSH_PASS"

echo "[3/4] Running RKE2 bootstrap playbook..."
ansible-galaxy install -r ansible/requirements.yml || true
ansible-playbook -i ansible/inventory.ini ansible/rke2-bootstrap.yml

echo "[4/4] Bootstrap complete. kubeconfig expected at ~/.kube/config or /etc/rancher/rke2/rke2.yaml on server nodes."
"""


def _inventory_renderer() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _infer_hosts(tf: dict) -> tuple[list[str], list[str], dict[str, str], dict[str, list[str]]]:
    names: list[str] = []
    ips: dict[str, str] = {}

    name_output = tf.get("vm_names", {})
    if isinstance(name_output, dict):
        value = name_output.get("value")
        if isinstance(value, list):
            names = [str(v) for v in value]

    ip_output = tf.get("vm_ips", {})
    if isinstance(ip_output, dict):
        value = ip_output.get("value")
        if isinstance(value, dict):
            ips = {str(k): str(v) for k, v in value.items() if v}

    if not names and ips:
        names = sorted(ips)

    # Prefer system/server/control nodes as the RKE2 server
    system_nodes = [n for n in names if any(kw in n.lower() for kw in ("system", "server", "control"))]
    if system_nodes:
        servers = system_nodes[:1]
        agents = [n for n in names if n not in servers]
    else:
        servers = names[:1]
        agents = names[1:]

    if not servers:
        servers = ["rke2-server-1"]

    # Classify agents into pool groups by VM naming convention
    pool_keywords = ("hot", "cold", "frozen", "system", "warm", "master", "ingest")
    agent_pools: dict[str, list[str]] = {}
    for agent in agents:
        name_lower = agent.lower()
        for kw in pool_keywords:
            if kw in name_lower:
                agent_pools.setdefault(kw, []).append(agent)
                break

    return servers, agents, ips, agent_pools


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--tf-output", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ansible-user", default="ubuntu")
    parser.add_argument("--ssh-pass", default="ubuntu")
    args = parser.parse_args()

    tf_data = json.loads(Path(args.tf_output).read_text())
    template = Path(args.template).read_text()

    servers, agents, ips, agent_pools = _infer_hosts(tf_data)

    def _format(hosts: list[str]) -> str:
        lines = []
        for host in hosts:
            ip = ips.get(host)
            if ip:
                lines.append(f"{host} ansible_host={ip}")
            else:
                lines.append(host)
        return "\\n".join(lines)

    rendered = template.replace("{{ project_name }}", args.project_name)
    rendered = rendered.replace("{{ servers }}", _format(servers))
    rendered = rendered.replace("{{ agents }}", _format(agents) if agents else "")
    rendered = rendered.replace("{{ ansible_user }}", args.ansible_user)
    rendered = rendered.replace("{{ ansible_ssh_pass }}", args.ssh_pass)

    # Render per-pool agent groups
    for pool_name in ("hot", "cold", "frozen", "system", "warm", "master", "ingest"):
        placeholder = "{{ agents_" + pool_name + " }}"
        pool_hosts = agent_pools.get(pool_name, [])
        rendered = rendered.replace(placeholder, _format(pool_hosts) if pool_hosts else "")

    Path(args.out).write_text(rendered)


if __name__ == "__main__":
    main()
"""


def _normalize_pool_keyword(pool_name: str) -> str:
    """Extract the classifier keyword from a pool name.

    The inventory renderer classifies agents by matching VM hostnames
    against keywords (hot, cold, frozen, etc.).  Pool names from sizing
    context often look like ``hot_pool`` or ``cold-storage``.  We strip
    the suffix so the template placeholder matches what the renderer
    produces.
    """
    known = ("hot", "cold", "frozen", "system", "warm", "master", "ingest")
    name = pool_name.lower().replace("-", "_")
    for kw in known:
        if kw in name:
            return kw
    return name  # fallback: use as-is


def _inventory_template(pools: list[str] | None = None) -> str:
    base = """[rke2_servers]
{{ servers }}

[rke2_agents]
{{ agents }}
"""
    if pools:
        seen: set[str] = set()
        for pool in pools:
            kw = _normalize_pool_keyword(pool)
            if kw not in seen:
                seen.add(kw)
                base += f"\n[rke2_agents_{kw}]\n{{{{ agents_{kw} }}}}\n"

    base += """
[all:vars]
ansible_user={{ ansible_user }}
ansible_ssh_pass={{ ansible_ssh_pass }}
ansible_become_pass={{ ansible_ssh_pass }}
ansible_ssh_common_args='-o StrictHostKeyChecking=no'
project_name={{ project_name }}
rke2_version=v1.30.4+rke2r1
"""
    return base


def _ansible_playbook() -> str:
    return """---
- name: Grow root partition and filesystem on all nodes
  hosts: all
  become: true
  tasks:
    - name: Install growpart tooling on Debian/Ubuntu
      apt:
        name: cloud-guest-utils
        state: present
        update_cache: false
      when: (ansible_os_family | lower) == "debian"

    - name: Install growpart tooling on RHEL family
      package:
        name: cloud-utils-growpart
        state: present
      when: (ansible_os_family | lower) == "redhat"

    - name: Ensure xfs resize tool exists on Debian/Ubuntu
      apt:
        name: xfsprogs
        state: present
        update_cache: false
      when: (ansible_os_family | lower) == "debian"

    - name: Ensure xfs resize tool exists on RHEL family
      package:
        name: xfsprogs
        state: present
      when: (ansible_os_family | lower) == "redhat"

    - name: Detect root source device
      shell: findmnt -n -o SOURCE /
      register: root_source_cmd
      changed_when: false

    - name: Detect parent disk and partition number
      shell: |
        set -eu
        ROOT_SRC="{{ root_source_cmd.stdout | trim }}"
        PKNAME="$(lsblk -no PKNAME "$ROOT_SRC")"
        PARTNUM="$(lsblk -no PARTN "$ROOT_SRC")"
        echo "${PKNAME} ${PARTNUM}"
      register: root_disk_parts
      changed_when: false

    - name: Parse root disk metadata
      set_fact:
        root_pkname: "{{ (root_disk_parts.stdout | trim).split()[0] }}"
        root_partnum: "{{ (root_disk_parts.stdout | trim).split()[1] }}"
        root_device: "{{ root_source_cmd.stdout | trim }}"

    - name: Grow root partition
      command: "growpart /dev/{{ root_pkname }} {{ root_partnum }}"
      register: growpart_result
      failed_when: growpart_result.rc not in [0, 1]
      changed_when: growpart_result.rc == 0

    - name: Detect root filesystem type
      shell: findmnt -n -o FSTYPE /
      register: root_fstype
      changed_when: false

    - name: Resize ext filesystem
      command: "resize2fs {{ root_device }}"
      when:
        - growpart_result.rc == 0
        - root_fstype.stdout | trim in ["ext2", "ext3", "ext4"]

    - name: Resize xfs filesystem
      command: xfs_growfs /
      when:
        - growpart_result.rc == 0
        - root_fstype.stdout | trim == "xfs"

- name: Bootstrap RKE2 servers
  hosts: rke2_servers
  become: true
  tasks:
    - name: Install RKE2 server
      shell: |
        curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=server sh -
      args:
        creates: /usr/local/bin/rke2

    - name: Create RKE2 config directory
      file:
        path: /etc/rancher/rke2
        state: directory
        mode: "0700"

    - name: Write RKE2 server config
      copy:
        dest: /etc/rancher/rke2/config.yaml
        mode: "0600"
        content: |
          node-name: {{ inventory_hostname }}

    - name: Clear stale node password
      file:
        path: /etc/rancher/node/password
        state: absent

    - name: Enable and start RKE2 server
      systemd:
        name: rke2-server
        enabled: true
        state: started
      async: 600
      poll: 15

    - name: Wait for RKE2 server registration port
      wait_for:
        port: 9345
        host: "{{ ansible_host }}"
        timeout: 120

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
    rke2_server_endpoint: "https://{{ hostvars[groups['rke2_servers'][0]].ansible_host }}:9345"
    rke2_cluster_token: "{{ hostvars[groups['rke2_servers'][0]].rke2_cluster_token }}"
  tasks:
    - name: Install RKE2 agent
      shell: |
        curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=agent sh -
      args:
        creates: /usr/local/bin/rke2

    - name: Create RKE2 config directory
      file:
        path: /etc/rancher/rke2
        state: directory
        mode: "0700"

    - name: Clear stale node password
      file:
        path: /etc/rancher/node/password
        state: absent

    - name: Write RKE2 agent config
      copy:
        dest: /etc/rancher/rke2/config.yaml
        mode: "0600"
        content: |
          server: {{ rke2_server_endpoint }}
          token: {{ rke2_cluster_token }}
          node-name: {{ inventory_hostname }}
          {% if 'rke2_agents_hot' in group_names %}
          node-label:
            - "elasticsearch.k8s.elastic.co/tier=hot"
          {% elif 'rke2_agents_cold' in group_names %}
          node-label:
            - "elasticsearch.k8s.elastic.co/tier=cold"
          {% elif 'rke2_agents_frozen' in group_names %}
          node-label:
            - "elasticsearch.k8s.elastic.co/tier=frozen"
          {% elif 'rke2_agents_system' in group_names %}
          node-label:
            - "elasticsearch.k8s.elastic.co/tier=infra"
          {% endif %}

    - name: Enable RKE2 agent
      systemd:
        name: rke2-agent
        enabled: true
        daemon_reload: true

    - name: Start RKE2 agent (async — notify-type service)
      shell: systemctl start rke2-agent
      async: 600
      poll: 0
      register: agent_start

    - name: Wait for agent to reach running state
      async_status:
        jid: "{{ agent_start.ansible_job_id }}"
      register: agent_result
      until: agent_result.finished
      retries: 40
      delay: 15
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

    # Extract pool names from sizing context for per-pool inventory groups
    sizing_ctx = ctx.get("sizing_context") or {}
    rke2_pools = sizing_ctx.get("rke2", {}).get("pools", [])
    pool_names = [p.get("name") or p for p in rke2_pools if p] if rke2_pools else []

    return {
        "scripts/bootstrap-rke2.sh": _bootstrap_script(project_name),
        "scripts/render-rke2-inventory.py": _inventory_renderer(),
        "ansible/inventory.tpl.ini": _inventory_template(pool_names if pool_names else None),
        "ansible/rke2-bootstrap.yml": _ansible_playbook(),
        "ansible/requirements.yml": _requirements(),
        "docs/RKE2_BOOTSTRAP.md": _docs(),
    }
