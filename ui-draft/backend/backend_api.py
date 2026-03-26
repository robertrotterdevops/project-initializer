#!/usr/bin/env python3
"""Project Initializer UI API.

Draft API for a professional internal UI around project-initializer.
"""

import json
import os
import base64
import shutil
import shlex
import subprocess
import sys
import tempfile
from urllib.parse import quote
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, UTC
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any, Dict, List, Optional
from uuid import uuid4

import asyncio

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles


if getattr(sys, "frozen", False):
    ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path.cwd()))
else:
    ROOT_DIR = Path(__file__).resolve().parents[2]

FRONTEND_DIR = ROOT_DIR / "ui-draft" / "frontend"
SCRIPTS_DIR = ROOT_DIR / "scripts"
DATA_DIR = ROOT_DIR / "ui-draft" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
GIT_REGISTRY_PATH = DATA_DIR / "git_registry.json"
PREFERENCES_PATH = DATA_DIR / "preferences.json"
DEPLOYMENT_HISTORY_PATH = DATA_DIR / "deployment_history.json"
OPERATION_RUN_HISTORY_PATH = DATA_DIR / "operation_run_history.json"

sys.path.insert(0, str(SCRIPTS_DIR))

from project_analyzer import ProjectAnalyzer, analyze_project  # type: ignore  # noqa: E402
from generate_structure import initialize_project  # type: ignore  # noqa: E402
from sizing_parser import parse_sizing_file_detailed  # type: ignore  # noqa: E402
from addon_loader import AddonLoader  # type: ignore  # noqa: E402


USER_HOME = Path.home()
SSH_DIR = USER_HOME / ".ssh"
PLATFORM_PRESETS = {
    "openshift": {
        "label": "OpenShift",
        "platform": "openshift",
        "gitops": "flux",
        "target_type": "local",
        "description": "Enterprise-ready OpenShift automation with GitOps hand-offs and Terraform add-ons.",
    },
    "proxmox": {
        "label": "Proxmox + RKE2",
        "platform": "proxmox",
        "gitops": "flux",
        "target_type": "local",
        "description": "Hardened VM automation that layers RKE2 clusters on Proxmox nodes.",
    },
    "rke2": {
        "label": "RKE2 + Rancher",
        "platform": "rke2",
        "gitops": "argo",
        "target_type": "local",
        "description": "Opinionated RKE2 stacks governed with Rancher policy catalogs and fleet GitOps.",
    },
    "aks": {
        "label": "Azure AKS",
        "platform": "aks",
        "gitops": "argo",
        "target_type": "local",
        "description": "Opinionated AKS cluster deployment with Azure-native integrations and GitOps.",
    },
}
POLICY_PROFILES = {
    "internal-default": {
        "label": "Internal default",
        "license_id": "UNLICENSED",
        "confidentiality": "internal",
        "header_mode": "minimal",
        "organization_required": False,
        "description": "Internal delivery with lightweight managed headers.",
    },
    "restricted-managed": {
        "label": "Restricted managed",
        "license_id": "Proprietary",
        "confidentiality": "restricted",
        "header_mode": "full",
        "organization_required": True,
        "description": "Restricted delivery with full managed headers and ownership metadata.",
    },
    "apache-public": {
        "label": "Apache public",
        "license_id": "Apache-2.0",
        "confidentiality": "public",
        "header_mode": "full",
        "organization_required": True,
        "description": "Public-facing project with Apache-2.0 and explicit provenance.",
    },
    "mit-public": {
        "label": "MIT public",
        "license_id": "MIT",
        "confidentiality": "public",
        "header_mode": "minimal",
        "organization_required": False,
        "description": "Open project with MIT licensing and minimal managed headers.",
    },
}
SCRIPT_OPERATION_REGISTRY = {
    "preflight-check": {
        "path": "scripts/preflight-check.sh",
        "title": "Preflight Check",
        "description": "Runs generated preflight checks before deployment actions.",
        "safe": True,
        "category": "validation",
        "execution_context": "project_root",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash"],
        "recommended_order": 10,
        "arguments": [],
        "confirmation_required": False,
        "confirmation_mode": "",
        "confirmation_phrase": "",
    },
    "validate-config": {
        "path": "scripts/validate-config.sh",
        "title": "Validate Config",
        "description": "Runs generated configuration validation checks.",
        "safe": True,
        "category": "validation",
        "execution_context": "project_root",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash"],
        "recommended_order": 20,
        "arguments": [],
        "confirmation_required": False,
        "confirmation_mode": "",
        "confirmation_phrase": "",
    },
    "verify-deployment": {
        "path": "scripts/verify-deployment.sh",
        "title": "Verify Deployment",
        "description": "Runs generated post-deployment verification checks.",
        "safe": True,
        "category": "validation",
        "execution_context": "project_root",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "kubectl", "kubeconfig"],
        "recommended_order": 50,
        "arguments": [],
        "confirmation_required": False,
        "confirmation_mode": "",
        "confirmation_phrase": "",
    },
    "cluster-healthcheck": {
        "path": "scripts/cluster-healthcheck.sh",
        "title": "Cluster Healthcheck",
        "description": "Runs generated cluster and Kibana health checks and can bootstrap kubeconfig for RKE2-based projects.",
        "safe": True,
        "dangerous": False,
        "category": "validation",
        "execution_context": "project_root",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "kubectl"],
        "recommended_order": 40,
        "arguments": [{"name": "kubeconfig_path", "label": "Kubeconfig Path", "required": False, "placeholder": "~/.kube/config", "description": "Optional kubeconfig override exposed as PI_ARG_KUBECONFIG_PATH."}],
        "confirmation_required": False,
        "confirmation_mode": "",
        "confirmation_phrase": "",
    },
    "post-terraform-deploy": {
        "path": "scripts/post-terraform-deploy.sh",
        "title": "Post Terraform Deploy",
        "description": "Runs the generated post-terraform deployment helper.",
        "safe": False,
        "dangerous": True,
        "category": "operations",
        "execution_context": "project_root",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "terraform", "kubectl", "kubeconfig"],
        "recommended_order": 30,
        "arguments": [{"name": "tfvars_file", "label": "Tfvars File", "required": False, "placeholder": "terraform.tfvars", "description": "Optional tfvars filename exposed as PI_ARG_TFVARS_FILE."}],
        "confirmation_required": True,
        "confirmation_mode": "project_name",
        "confirmation_phrase": "",
    },
    "import-dashboards": {
        "path": "scripts/import-dashboards.sh",
        "title": "Import Dashboards",
        "description": "Imports generated observability dashboards into Kibana.",
        "safe": True,
        "dangerous": False,
        "category": "operations",
        "execution_context": "project_root",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "curl", "kibana_endpoint"],
        "recommended_order": 60,
        "arguments": [{"name": "kibana_url", "label": "Kibana URL", "required": False, "placeholder": "https://kibana.example.internal", "description": "Optional Kibana URL exposed as PI_ARG_KIBANA_URL."}],
        "confirmation_required": False,
        "confirmation_mode": "",
        "confirmation_phrase": "",
    },
    "mirror-secrets": {
        "path": "scripts/mirror-secrets.sh",
        "title": "Mirror Secrets",
        "description": "Propagates generated secrets across required namespaces.",
        "safe": True,
        "dangerous": False,
        "category": "operations",
        "execution_context": "project_root",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "kubectl", "kubeconfig"],
        "recommended_order": 70,
        "arguments": [],
        "confirmation_required": False,
        "confirmation_mode": "",
        "confirmation_phrase": "",
    },
    "rollback": {
        "path": "scripts/rollback.sh",
        "title": "Rollback",
        "description": "Runs the generated rollback helper for the scaffolded deployment.",
        "safe": True,
        "dangerous": False,
        "category": "operations",
        "execution_context": "project_root",
        "applies_to": ["local", "remote"],
        "prerequisites": ["bash", "kubectl", "kubeconfig"],
        "recommended_order": 90,
        "arguments": [],
        "confirmation_required": False,
        "confirmation_mode": "",
        "confirmation_phrase": "",
    },
}
SYSTEM_DIRECTORIES = {
    "/",
    "/root",
    "/bin",
    "/usr",
    "/etc",
    "/sys",
    "/proc",
    "/boot",
    "/dev",
    "/snap",
    "/lib",
    "/lib64",
    "/opt",
    "/sbin",
    "/srv",
}


def _is_user_home(path: Path) -> bool:
    """Check if path is the current user's home directory."""
    try:
        resolved = path.resolve()
        return resolved == USER_HOME
    except (OSError, RuntimeError):
        return False


def _is_user_accessible(path: Path) -> bool:
    """Check if path is under current user's home (not other users)."""
    try:
        resolved = path.resolve()
        if resolved == USER_HOME:
            return True
        try:
            resolved.relative_to(USER_HOME)
            return True
        except ValueError:
            pass
        return False
    except (OSError, RuntimeError):
        return False


def _get_default_suggestions() -> List[str]:
    """Get default directory suggestions for empty query."""
    suggestions = []
    if USER_HOME.exists():
        suggestions.append(str(USER_HOME.resolve()))
        projects_dir = USER_HOME / "Projects"
        if projects_dir.exists():
            suggestions.append(str(projects_dir.resolve()))
        documents_dir = USER_HOME / "Documents"
        if documents_dir.exists():
            suggestions.append(str(documents_dir.resolve()))
    cwd = Path.cwd()
    if cwd != USER_HOME and cwd.exists():
        suggestions.append(str(cwd.resolve()))
    return suggestions[:5]


def _utcnow() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class GitRegistry:
    def __init__(self, path: Path):
        self.path = path
        self.lock = RLock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"entries": []}, indent=2), encoding="utf-8")

    def _read_entries(self) -> List[Dict[str, Any]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {"entries": []}
        entries = raw.get("entries") or []
        if not isinstance(entries, list):  # pragma: no cover - safety guard
            return []
        return entries

    def _write_entries(self, entries: List[Dict[str, Any]]) -> None:
        payload = {"entries": entries}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self._read_entries())

    def add(self, name: str, repo_path: str, remote_url: str, branch: str, platform: str, description: str) -> Dict[str, Any]:
        if not name.strip():
            raise HTTPException(status_code=400, detail="name is required for git schema")
        if not repo_path.strip():
            raise HTTPException(status_code=400, detail="repo_path is required for git schema")
        now = _utcnow()
        entry = {
            "id": str(uuid4()),
            "name": name.strip(),
            "repo_path": repo_path.strip(),
            "remote_url": remote_url.strip(),
            "branch": (branch or "main").strip() or "main",
            "platform": platform.strip(),
            "description": description.strip(),
            "created_at": now,
            "updated_at": now,
            "last_used_at": None,
        }
        with self.lock:
            entries = self._read_entries()
            entries.append(entry)
            self._write_entries(entries)
        return entry

    def update(self, entry_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            entries = self._read_entries()
            for entry in entries:
                if entry.get("id") == entry_id:
                    entry.update({k: v for k, v in updates.items() if v is not None})
                    entry["updated_at"] = _utcnow()
                    self._write_entries(entries)
                    return entry
        raise HTTPException(status_code=404, detail="git schema not found")

    def delete(self, entry_id: str) -> None:
        with self.lock:
            entries = self._read_entries()
            new_entries = [e for e in entries if e.get("id") != entry_id]
            if len(new_entries) == len(entries):
                raise HTTPException(status_code=404, detail="git schema not found")
            self._write_entries(new_entries)

    def mark_used(self, entry_id: str, platform: Optional[str] = None) -> None:
        with self.lock:
            entries = self._read_entries()
            changed = False
            for entry in entries:
                if entry.get("id") == entry_id:
                    entry["last_used_at"] = _utcnow()
                    if platform:
                        entry["platform"] = platform
                    entry["updated_at"] = _utcnow()
                    changed = True
                    break
            if changed:
                self._write_entries(entries)

    def upsert_from_project(
        self,
        repo_path: Optional[str],
        remote_url: str,
        branch: str,
        platform: Optional[str],
        schema_id: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> None:
        if not (repo_path or schema_id):
            return
        normalized_branch = (branch or "main").strip() or "main"
        with self.lock:
            entries = self._read_entries()
            target = None
            for entry in entries:
                if schema_id and entry.get("id") == schema_id:
                    target = entry
                    break
                if repo_path and entry.get("repo_path"):
                    try:
                        if Path(entry["repo_path"]).resolve() == Path(repo_path).resolve():
                            target = entry
                            break
                    except OSError:
                        if entry["repo_path"].strip() == repo_path.strip():
                            target = entry
                            break
            if target:
                target["remote_url"] = remote_url.strip() or target.get("remote_url", "")
                target["branch"] = normalized_branch
                if platform:
                    target["platform"] = platform
                target["last_used_at"] = _utcnow()
                target["updated_at"] = _utcnow()
                self._write_entries(entries)
                return
            if not repo_path:
                return
            now = _utcnow()
            entry = {
                "id": str(uuid4()),
                "name": project_name or Path(repo_path).name,
                "repo_path": repo_path,
                "remote_url": remote_url.strip(),
                "branch": normalized_branch,
                "platform": platform or "",
                "description": "",  # auto-added
                "created_at": now,
                "updated_at": now,
                "last_used_at": now,
            }
            entries.append(entry)
            self._write_entries(entries)


GIT_REGISTRY = GitRegistry(GIT_REGISTRY_PATH)


class JsonRecordStore:
    def __init__(self, path: Path, root_key: str):
        self.path = path
        self.root_key = root_key
        self.lock = RLock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({self.root_key: []}, indent=2), encoding="utf-8")

    def _read_root(self) -> Dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {self.root_key: []}
        if not isinstance(raw, dict):
            raw = {self.root_key: []}
        raw.setdefault(self.root_key, [])
        return raw

    def _write_root(self, payload: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class PreferencesStore(JsonRecordStore):
    def __init__(self, path: Path):
        super().__init__(path, "preferences")

    def get(self) -> Dict[str, Any]:
        with self.lock:
            root = self._read_root()
            prefs = root.get("preferences") or {}
            return prefs if isinstance(prefs, dict) else {}

    def update(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            root = self._read_root()
            current = root.get("preferences") or {}
            if not isinstance(current, dict):
                current = {}
            current.update(updates)
            root["preferences"] = current
            self._write_root(root)
            return current


class DeploymentHistoryStore(JsonRecordStore):
    def __init__(self, path: Path):
        super().__init__(path, "entries")

    def list(self) -> List[Dict[str, Any]]:
        with self.lock:
            entries = self._read_root().get("entries") or []
            if not isinstance(entries, list):
                return []
            return list(entries)

    def add(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            root = self._read_root()
            entries = root.get("entries") or []
            if not isinstance(entries, list):
                entries = []
            record = {"id": str(uuid4()), "created_at": _utcnow(), **payload}
            entries.insert(0, record)
            root["entries"] = entries[:50]
            self._write_root(root)
            return record

    def delete(self, entry_id: str) -> None:
        with self.lock:
            root = self._read_root()
            entries = root.get("entries") or []
            if not isinstance(entries, list):
                entries = []
            kept = [entry for entry in entries if entry.get("id") != entry_id]
            if len(kept) == len(entries):
                raise HTTPException(status_code=404, detail="deployment history entry not found")
            root["entries"] = kept
            self._write_root(root)


PREFERENCES = PreferencesStore(PREFERENCES_PATH)
DEPLOYMENT_HISTORY = DeploymentHistoryStore(DEPLOYMENT_HISTORY_PATH)

# --- Audit Log ---
AUDIT_LOG_PATH = DATA_DIR / "audit_log.json"


class AuditLogStore(JsonRecordStore):
    def __init__(self, path: Path):
        super().__init__(path, "entries")

    def list(self) -> List[Dict[str, Any]]:
        with self.lock:
            entries = self._read_root().get("entries") or []
            return list(entries) if isinstance(entries, list) else []

    def add(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            root = self._read_root()
            entries = root.get("entries") or []
            if not isinstance(entries, list):
                entries = []
            record = {"id": str(uuid4()), "created_at": _utcnow(), **payload}
            entries.insert(0, record)
            root["entries"] = entries[:200]
            self._write_root(root)
            return record

    def append(self, operation: str, detail: str) -> Dict[str, Any]:
        return self.add({"operation": operation, "detail": detail})


AUDIT_LOG = AuditLogStore(AUDIT_LOG_PATH)


class OperationRunHistoryStore(JsonRecordStore):
    def __init__(self, path: Path):
        super().__init__(path, "entries")

    def list(self, deployment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            entries = self._read_root().get("entries") or []
            if not isinstance(entries, list):
                return []
            if deployment_id:
                entries = [entry for entry in entries if entry.get("deployment_id") == deployment_id]
            return list(entries)

    def add(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            root = self._read_root()
            entries = root.get("entries") or []
            if not isinstance(entries, list):
                entries = []
            record = {"id": str(uuid4()), "created_at": _utcnow(), **payload}
            entries.insert(0, record)
            root["entries"] = entries[:300]
            self._write_root(root)
            return record


OPERATION_RUN_HISTORY = OperationRunHistoryStore(OPERATION_RUN_HISTORY_PATH)


def _detect_runtime_environment() -> Dict[str, Any]:
    platform = sys.platform
    display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    ssh_session = bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"))
    forced = os.environ.get("PI_FORCE_HEADLESS")
    headless = False
    if forced:
        headless = forced.lower() in {"1", "true", "yes"}
    else:
        headless = not display or ssh_session

    supports_gui_open = False
    supports_native_picker = False
    picker_message = ""

    if platform.startswith("linux"):
        has_xdg = shutil.which("xdg-open") is not None
        has_zenity = shutil.which("zenity") is not None
        supports_gui_open = (not headless) and has_xdg
        supports_native_picker = supports_gui_open and has_zenity
        if not supports_native_picker:
            if headless:
                picker_message = "Native folder picker disabled (headless session)"
            elif not has_zenity:
                picker_message = "Install 'zenity' to enable the native Linux folder picker"
    elif platform == "darwin":
        supports_gui_open = not headless
        supports_native_picker = not headless
        if headless:
            picker_message = "Native dialogs unavailable in headless macOS session"
    else:
        picker_message = f"Native picker not supported on {platform}"

    return {
        "platform": platform,
        "headless": headless,
        "supports_gui_open": supports_gui_open,
        "supports_native_picker": supports_native_picker,
        "picker_message": picker_message,
    }


RUNTIME_ENV = _detect_runtime_environment()

app = FastAPI(title="Project Initializer UI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1", "tauri://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


def _run_git_command(command: List[str], cwd: Path, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        return {
            "ok": True,
            "command": " ".join(command),
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "command": " ".join(command),
            "stdout": (exc.stdout or "").strip(),
            "stderr": (exc.stderr or str(exc)).strip(),
        }


def _git_username_for_remote(remote_url: str) -> Optional[str]:
    lower = (remote_url or "").strip().lower()
    if "github.com" in lower:
        return "x-access-token"
    if "gitlab.com" in lower:
        return "oauth2"
    if "dev.azure.com" in lower:
        return ""
    return None


def _http_json_request(url: str, method: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]] = None) -> Any:
    data_bytes = None
    req_headers = dict(headers)
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url=url, data=data_bytes, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8") if resp else ""
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"message": raw}
        raise HTTPException(status_code=400, detail=f"Remote API error ({exc.code}): {parsed}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Remote API unavailable: {exc.reason}") from exc


def _create_github_repo(namespace: str, project_name: str, token: str, private_repo: bool) -> str:
    ns = namespace.strip().strip("/")
    if not ns:
        raise HTTPException(status_code=400, detail="git_namespace is required for github repository creation")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "project-initializer",
    }
    payload = {"name": project_name, "private": private_repo}

    # Try organization first; fallback to authenticated user namespace.
    try:
        response = _http_json_request(
            url=f"https://api.github.com/orgs/{urllib.parse.quote(ns)}/repos",
            method="POST",
            headers=headers,
            payload=payload,
        )
    except HTTPException:
        me = _http_json_request(
            url="https://api.github.com/user",
            method="GET",
            headers=headers,
        )
        login = (me.get("login") or "").strip()
        if login.lower() != ns.lower():
            raise
        response = _http_json_request(
            url="https://api.github.com/user/repos",
            method="POST",
            headers=headers,
            payload=payload,
        )

    clone_url = (response.get("clone_url") or "").strip()
    if not clone_url:
        raise HTTPException(status_code=502, detail="GitHub API did not return clone_url")
    return clone_url


def _create_gitlab_repo(namespace: str, project_name: str, token: str, private_repo: bool) -> str:
    ns = namespace.strip().strip("/")
    if not ns:
        raise HTTPException(status_code=400, detail="git_namespace is required for gitlab repository creation")

    headers = {
        "Accept": "application/json",
        "PRIVATE-TOKEN": token,
        "User-Agent": "project-initializer",
    }
    namespaces = _http_json_request(
        url=f"https://gitlab.com/api/v4/namespaces?search={urllib.parse.quote(ns)}",
        method="GET",
        headers=headers,
    )
    if not isinstance(namespaces, list):
        raise HTTPException(status_code=502, detail="Unexpected GitLab namespace response")

    exact = None
    for item in namespaces:
        full_path = (item.get("full_path") or item.get("path") or "").strip()
        if full_path.lower() == ns.lower():
            exact = item
            break
    if exact is None:
        raise HTTPException(status_code=404, detail=f"GitLab namespace not found: {ns}")

    visibility = "private" if private_repo else "public"
    response = _http_json_request(
        url="https://gitlab.com/api/v4/projects",
        method="POST",
        headers=headers,
        payload={
            "name": project_name,
            "path": project_name,
            "namespace_id": exact.get("id"),
            "visibility": visibility,
        },
    )

    clone_url = (response.get("http_url_to_repo") or "").strip()
    if not clone_url:
        raise HTTPException(status_code=502, detail="GitLab API did not return http_url_to_repo")
    return clone_url


def _create_remote_repo(provider: str, namespace: str, project_name: str, token: str, private_repo: bool) -> str:
    p = (provider or "").strip().lower()
    if p == "github":
        return _create_github_repo(namespace, project_name, token, private_repo)
    if p == "gitlab":
        return _create_gitlab_repo(namespace, project_name, token, private_repo)
    raise HTTPException(status_code=400, detail="git_provider must be 'github' or 'gitlab' for remote repo creation")


def _remote_repo_owner_and_name(repo_url: str) -> tuple[str, str]:
    raw = (repo_url or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Missing repository URL")

    # Support HTTPS URLs
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urllib.parse.urlparse(raw)
        parts = [part for part in (parsed.path or "").split("/") if part]
        if len(parts) < 2:
            raise HTTPException(status_code=400, detail=f"Invalid repository URL path: {repo_url}")
        repo = parts[-1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        owner = "/".join(parts[:-1])
        if not owner or not repo:
            raise HTTPException(status_code=400, detail=f"Invalid repository URL path: {repo_url}")
        return owner, repo

    # Support SSH URLs: git@host:owner/repo.git
    if raw.startswith("git@") and ":" in raw:
        after_colon = raw.split(":", 1)[1]
        parts = [part for part in after_colon.split("/") if part]
        if len(parts) < 2:
            raise HTTPException(status_code=400, detail=f"Invalid SSH repository URL path: {repo_url}")
        repo = parts[-1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        owner = "/".join(parts[:-1])
        if not owner or not repo:
            raise HTTPException(status_code=400, detail=f"Invalid SSH repository URL path: {repo_url}")
        return owner, repo

    raise HTTPException(status_code=400, detail=f"Unsupported repository URL format: {repo_url}")


def _delete_remote_repo_for_deployment(entry: Dict[str, Any], git_token: str, confirm_text: str) -> Dict[str, Any]:
    remote_repo = entry.get("git_remote_repo") or {}
    if not isinstance(remote_repo, dict) or not remote_repo.get("created"):
        raise HTTPException(status_code=400, detail="Remote repository deletion is allowed only for repositories created by this app for this deployment")

    expected_confirm = f"DELETE {entry.get('name', '')}".strip()
    if not expected_confirm or confirm_text.strip() != expected_confirm:
        raise HTTPException(status_code=400, detail=f"Confirmation text mismatch. Expected: '{expected_confirm}'")

    token = (git_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="git_token is required to delete remote repository")

    provider = str(remote_repo.get("provider") or "").strip().lower()
    repo_url = str(remote_repo.get("url") or entry.get("git_remote_url") or "").strip()
    if not provider or not repo_url:
        raise HTTPException(status_code=400, detail="Missing remote repository provider/url metadata")

    owner, repo_name = _remote_repo_owner_and_name(repo_url)
    expected_repo_name = str(entry.get("name") or "").strip().strip("/").strip("\\")
    if not expected_repo_name or repo_name.lower() != expected_repo_name.lower():
        raise HTTPException(status_code=400, detail="Refusing to delete: remote repo name does not match deployment project name")

    if provider == "gitlab":
        headers = {
            "Accept": "application/json",
            "PRIVATE-TOKEN": token,
            "User-Agent": "project-initializer",
        }
        project_id = urllib.parse.quote(f"{owner}/{repo_name}", safe="")
        _http_json_request(
            url=f"https://gitlab.com/api/v4/projects/{project_id}",
            method="DELETE",
            headers=headers,
        )
        return {"ok": True, "provider": provider, "repository": f"{owner}/{repo_name}"}

    if provider == "github":
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "project-initializer",
        }
        _http_json_request(
            url=f"https://api.github.com/repos/{owner}/{repo_name}",
            method="DELETE",
            headers=headers,
        )
        return {"ok": True, "provider": provider, "repository": f"{owner}/{repo_name}"}

    raise HTTPException(status_code=400, detail="Remote repository deletion currently supports github and gitlab only")


def _detect_provider(provider: str, remote_url: str) -> str:
    p = (provider or "").strip().lower()
    if p in {"github", "gitlab", "azure_devops"}:
        return p
    lower = (remote_url or "").strip().lower()
    if "github.com" in lower:
        return "github"
    if "gitlab.com" in lower:
        return "gitlab"
    if "dev.azure.com" in lower:
        return "azure_devops"
    return ""


def _looks_like_namespace_url(remote_url: str) -> bool:
    raw = (remote_url or "").strip()
    if not raw.startswith("http://") and not raw.startswith("https://"):
        return False
    parsed = urllib.parse.urlparse(raw)
    host = (parsed.netloc or "").lower()
    if not any(h in host for h in ("gitlab.com", "github.com")):
        return False
    parts = [p for p in (parsed.path or "").split("/") if p]
    return len(parts) < 2


def _prepare_git_pat_env(remote_url: str, git_token: str) -> tuple[Optional[Dict[str, str]], Optional[Path]]:
    token = (git_token or "").strip()
    if not token:
        return None, None

    username = _git_username_for_remote(remote_url)
    if username is None:
        return None, None

    # `git` invokes askpass for both username and password prompts.
    script = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".sh")
    username_escaped = username.replace("'", "'\"'\"'")
    token_escaped = token.replace("'", "'\"'\"'")
    script.write("#!/usr/bin/env sh\n")
    script.write('prompt="$1"\n')
    script.write('case "$prompt" in\n')
    script.write("  *Username*) echo '" + username_escaped + "' ;;\n")
    script.write("  *) echo '" + token_escaped + "' ;;\n")
    script.write("esac\n")
    script.flush()
    script.close()
    script_path = Path(script.name)
    script_path.chmod(0o700)

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = str(script_path)
    # Force PAT auth and bypass stale credentials from global/system helper.
    basic = base64.b64encode(f"{username}:{token}".encode("utf-8")).decode("ascii")
    env["GIT_CONFIG_COUNT"] = "2"
    env["GIT_CONFIG_KEY_0"] = "credential.helper"
    env["GIT_CONFIG_VALUE_0"] = ""
    env["GIT_CONFIG_KEY_1"] = "http.extraheader"
    env["GIT_CONFIG_VALUE_1"] = f"AUTHORIZATION: basic {basic}"
    return env, script_path


def _git_repo_summary(path: Path) -> Dict[str, Any]:
    branch = _run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], path)
    last_commit = _run_git_command(["git", "log", "-1", "--pretty=%h %s (%cr)"] , path)
    return {
        "path": str(path),
        "branch": branch.get("stdout", ""),
        "last_commit": last_commit.get("stdout", ""),
    }


def _run_shell_command(command: List[str], cwd: Path, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        return {
            "ok": True,
            "command": " ".join(command),
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "command": " ".join(command),
            "stdout": (exc.stdout or "").strip(),
            "stderr": (exc.stderr or str(exc)).strip(),
        }




def _run_ssh_command(host: str, port: str, user: str, remote_cmd: str, ssh_key_path: str = "") -> Dict[str, Any]:
    ssh = ["ssh", "-p", str(port), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new"]
    if ssh_key_path.strip():
        ssh.extend(["-i", str(Path(ssh_key_path).expanduser())])
    ssh.append(f"{user}@{host}")
    ssh.append(remote_cmd)
    return _run_shell_command(ssh, Path.cwd())


def _find_deployment_entry(deployment_id: str) -> Dict[str, Any]:
    entries = DEPLOYMENT_HISTORY.list()
    entry = next((e for e in entries if e.get("id") == deployment_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="deployment not found")
    return entry


def _entry_runtime_cache(entry: Dict[str, Any]) -> Dict[str, Any]:
    cache = entry.get("_runtime_cache")
    if not isinstance(cache, dict):
        cache = {}
        entry["_runtime_cache"] = cache
    return cache


def _project_root_from_entry(entry: Dict[str, Any]) -> tuple[str, Optional[Dict[str, Any]]]:
    target_type = (entry.get("target_type") or "local").strip()
    remote_cfg = entry.get("remote") if target_type == "remote" else None
    if target_type == "remote" and isinstance(remote_cfg, dict):
        return str(remote_cfg.get("project_dir") or ""), remote_cfg
    return str(entry.get("project_path") or ""), None


def _project_file_exists(entry: Dict[str, Any], relative_path: str) -> tuple[bool, str]:
    project_root, remote_cfg = _project_root_from_entry(entry)
    if not project_root:
        return False, ""
    cache = _entry_runtime_cache(entry).setdefault("project_file_exists", {})
    cache_key = f"{project_root}::{relative_path}"
    if cache_key in cache:
        return cache[cache_key]
    if remote_cfg:
        full_path = str(PurePosixPath(project_root) / relative_path)
        cmd = f"test -f {shlex.quote(full_path)} && echo present || echo missing"
        result = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), cmd, remote_cfg.get("ssh_key_path", ""))
        resolved = (result.get("stdout", "").strip() == "present", full_path)
        cache[cache_key] = resolved
        return resolved
    full_path = str((Path(project_root) / relative_path).resolve())
    resolved = (Path(full_path).exists(), full_path)
    cache[cache_key] = resolved
    return resolved


def _read_project_json(entry: Dict[str, Any], relative_path: str) -> Optional[Dict[str, Any]]:
    exists, resolved_path = _project_file_exists(entry, relative_path)
    if not exists or not resolved_path:
        return None
    project_root, remote_cfg = _project_root_from_entry(entry)
    if remote_cfg:
        result = _run_ssh_command(
            remote_cfg.get("host", ""),
            str(remote_cfg.get("port", "22")),
            remote_cfg.get("user", ""),
            f"cat {shlex.quote(resolved_path)}",
            remote_cfg.get("ssh_key_path", ""),
        )
        if not result.get("ok"):
            return None
        try:
            return json.loads(result.get("stdout", "") or "{}")
        except json.JSONDecodeError:
            return None
    try:
        return json.loads(Path(project_root, relative_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_project_relative_path(relative_path: str) -> str:
    cleaned = (relative_path or "").strip().replace("\\", "/")
    pure = PurePosixPath(cleaned)
    if not cleaned or pure.is_absolute() or any(part == ".." for part in pure.parts):
        raise HTTPException(status_code=400, detail="invalid project-relative path")
    return str(pure)


def _read_project_text(entry: Dict[str, Any], relative_path: str, max_chars: int = 20000) -> Dict[str, Any]:
    normalized = _normalize_project_relative_path(relative_path)
    allowed_suffixes = {".md", ".txt", ".log", ".json", ".yaml", ".yml", ".tf", ".sh", ".csv", ".ini", ".cfg", ".conf", ".ndjson"}
    suffix = PurePosixPath(normalized).suffix.lower()
    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail=f"preview not supported for {suffix or 'this file type'}")
    exists, resolved_path = _project_file_exists(entry, normalized)
    if not exists or not resolved_path:
        raise HTTPException(status_code=404, detail="artifact not found")
    project_root, remote_cfg = _project_root_from_entry(entry)
    text = ""
    if remote_cfg:
        result = _run_ssh_command(
            remote_cfg.get("host", ""),
            str(remote_cfg.get("port", "22")),
            remote_cfg.get("user", ""),
            f"cat {shlex.quote(resolved_path)}",
            remote_cfg.get("ssh_key_path", ""),
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("stderr") or "failed to read remote artifact")
        text = result.get("stdout", "") or ""
    else:
        try:
            text = Path(project_root, normalized).read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="artifact is not readable text") from exc
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"failed to read artifact: {exc}") from exc
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return {
        "path": normalized,
        "resolved_path": resolved_path,
        "content": text,
        "truncated": truncated,
        "target_type": (entry.get("target_type") or "local").strip() or "local",
    }


def _fallback_operations_manifest(platform: str = "") -> Dict[str, Any]:
    operations = [
        {"key": key, **meta}
        for key, meta in SCRIPT_OPERATION_REGISTRY.items()
    ]
    runbook_steps = [
        {
            "key": item["key"],
            "title": item.get("title", item["key"]),
            "description": item.get("description", ""),
            "docs": [],
            "recommended_order": item.get("recommended_order", 999),
        }
        for item in sorted(operations, key=lambda value: (value.get("recommended_order", 999), value.get("title", value.get("key", ""))))
    ]
    return {
        "schema_version": "fallback",
        "operations": operations,
        "runbooks": [{
            "platform": platform or "generic",
            "note": "Fallback runbook derived from the builtin script registry.",
            "steps": runbook_steps,
        }],
    }


def _operations_manifest_for_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    payload = _read_project_json(entry, "project-initializer-operations.json")
    if isinstance(payload, dict):
        if payload.get("runbooks"):
            return payload
        fallback = _fallback_operations_manifest(str(entry.get("platform") or payload.get("project", {}).get("platform") or ""))
        payload = dict(payload)
        payload.setdefault("operations", fallback["operations"])
        payload["runbooks"] = fallback["runbooks"]
        return payload
    return _fallback_operations_manifest(str(entry.get("platform") or ""))


def _hydrate_script_metadata(entry: Dict[str, Any], script: Dict[str, Any]) -> Dict[str, Any]:
    hydrated = dict(script)
    if hydrated.get("confirmation_required") and hydrated.get("confirmation_mode") == "project_name" and not hydrated.get("confirmation_phrase"):
        base_phrase = entry.get("name", "")
        if (entry.get("target_type") or "local").strip() == "remote" and not hydrated.get("safe", True):
            hydrated["confirmation_phrase"] = f"REMOTE {base_phrase}".strip()
        else:
            hydrated["confirmation_phrase"] = base_phrase
    hydrated.setdefault("arguments", [])
    hydrated.setdefault("recommended_order", 999)
    hydrated.setdefault("execution_context", "project_root")
    return hydrated


def _project_scoped_kubeconfig_name(entry: Dict[str, Any]) -> str:
    return str(entry.get("name") or "").strip()


def _local_kubeconfig_candidates(entry: Dict[str, Any], explicit_path: str = "", include_bootstrap_source: bool = False) -> List[Path]:
    candidates: List[Path] = []
    if explicit_path.strip():
        candidates.append(Path(explicit_path).expanduser())
    project_root, _ = _project_root_from_entry(entry)
    project_name = _project_scoped_kubeconfig_name(entry)
    if project_root and project_name:
        candidates.append(Path(project_root).expanduser() / ".kube" / project_name)
    if project_root:
        candidates.append(Path(project_root).expanduser() / ".kube" / "config")
    kube_path = os.environ.get("KUBECONFIG")
    if kube_path:
        candidates.append(Path(kube_path).expanduser())
    if project_name:
        candidates.append(Path.home() / ".kube" / project_name)
    candidates.append(Path.home() / ".kube" / "config")
    if include_bootstrap_source and (entry.get("platform") or "") in {"rke2", "proxmox"}:
        candidates.append(Path("/etc/rancher/rke2/rke2.yaml"))
    deduped: List[Path] = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            deduped.append(candidate)
            seen.add(key)
    return deduped


def _remote_shell_double_quote(value: str) -> str:
    escaped = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _remote_kubeconfig_candidates(entry: Dict[str, Any], explicit_path: str = "", include_bootstrap_source: bool = False) -> List[str]:
    candidates: List[str] = []
    if explicit_path.strip():
        candidates.append(explicit_path.strip())
    project_root, _ = _project_root_from_entry(entry)
    project_name = _project_scoped_kubeconfig_name(entry)
    if project_root and project_name:
        candidates.append(str(PurePosixPath(project_root) / ".kube" / project_name))
    if project_root:
        candidates.append(str(PurePosixPath(project_root) / ".kube" / "config"))
    if project_name:
        candidates.append(f"$HOME/.kube/{project_name}")
    candidates.append("$HOME/.kube/config")
    if include_bootstrap_source and (entry.get("platform") or "") in {"rke2", "proxmox"}:
        candidates.append("/etc/rancher/rke2/rke2.yaml")
    deduped: List[str] = []
    seen = set()
    for candidate in candidates:
        if candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def _extract_kubeconfig_path(detail: str) -> str:
    text = str(detail or "").strip()
    return text[len("Using "):].strip() if text.startswith("Using ") else text


def _remote_kubectl_command(entry: Dict[str, Any], command: str) -> str:
    kube = _check_remote_prerequisite(entry, "kubeconfig")
    kube_path = _extract_kubeconfig_path(kube.get("detail", "")) if kube.get("ok") else ""
    if kube_path:
        return f"export KUBECONFIG={shlex.quote(kube_path)}; {command}"
    return command


def _classify_kubeconfig_source(detail: str, entry: Dict[str, Any], target_type: str) -> str:
    project_name = _project_scoped_kubeconfig_name(entry)
    project_root, _ = _project_root_from_entry(entry)
    value = str(detail or "")
    if not value:
        return "missing"
    if "/etc/rancher/rke2/rke2.yaml" in value:
        return "bootstrap-source"
    if project_root and f"{project_root}/.kube/" in value:
        return "remote-project-root" if target_type == "remote" else "project-root"
    if project_name and f".kube/{project_name}" in value:
        return "remote-project-home" if target_type == "remote" else "project-home"
    if ".kube/config" in value:
        return "remote-home-default" if target_type == "remote" else "default-home"
    return "explicit" if target_type == "local" else "remote-explicit"


def _check_local_prerequisite(entry: Dict[str, Any], prerequisite: str) -> Dict[str, Any]:
    project_root, _ = _project_root_from_entry(entry)
    lower = prerequisite.lower()
    cache = _entry_runtime_cache(entry).setdefault("local_prerequisites", {})
    if lower in cache:
        return cache[lower]
    if lower == "bash":
        ok = shutil.which("bash") is not None
        result = {"name": prerequisite, "ok": ok, "detail": "bash available" if ok else "bash not found"}
        cache[lower] = result
        return result
    if lower in {"kubectl", "terraform", "curl", "kustomize", "oc"}:
        ok = shutil.which(lower) is not None
        result = {"name": prerequisite, "ok": ok, "detail": f"{lower} available" if ok else f"{lower} not found in PATH"}
        cache[lower] = result
        return result
    if lower == "kubeconfig":
        match = next((path for path in _local_kubeconfig_candidates(entry, include_bootstrap_source=False) if path.exists()), None)
        result = {"name": prerequisite, "ok": bool(match), "detail": f"Using {match}" if match else "No kubeconfig detected"}
        cache[lower] = result
        return result
    if lower == "kibana_endpoint":
        readme = Path(project_root) / "kibana" / "ingress.yaml"
        route = Path(project_root) / "platform" / "openshift" / "route.yaml"
        ok = readme.exists() or route.exists()
        result = {"name": prerequisite, "ok": ok, "detail": "Kibana exposure manifest found" if ok else "No Kibana endpoint manifest found"}
        cache[lower] = result
        return result
    result = {"name": prerequisite, "ok": True, "detail": "No explicit check implemented"}
    cache[lower] = result
    return result


def _check_remote_prerequisite(entry: Dict[str, Any], prerequisite: str) -> Dict[str, Any]:
    project_root, remote_cfg = _project_root_from_entry(entry)
    if not remote_cfg:
        return {"name": prerequisite, "ok": False, "detail": "Remote configuration missing"}
    lower = prerequisite.lower()
    cache = _entry_runtime_cache(entry).setdefault("remote_prerequisites", {})
    if lower in cache:
        return cache[lower]
    if lower == "ssh":
        result = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), "echo connected", remote_cfg.get("ssh_key_path", ""))
        resolved = {"name": prerequisite, "ok": result.get("ok", False), "detail": result.get("stdout", "") or result.get("stderr", "")}
        cache[lower] = resolved
        return resolved
    if lower == "bash":
        cmd = "command -v bash >/dev/null 2>&1 && echo present || echo missing"
    elif lower in {"kubectl", "terraform", "curl", "kustomize", "oc"}:
        cmd = f"command -v {shlex.quote(lower)} >/dev/null 2>&1 && echo present || echo missing"
    elif lower == "kubeconfig":
        candidates = _remote_kubeconfig_candidates(entry, include_bootstrap_source=False)
        clauses = []
        for index, candidate in enumerate(candidates):
            prefix = "if" if index == 0 else "elif"
            q_candidate = _remote_shell_double_quote(candidate)
            clauses.append(f"{prefix} test -f {q_candidate}; then printf '%s\\n' {q_candidate};")
        cmd = " ".join(clauses + ["else printf '%s\\n' missing;", "fi"])
    elif lower == "kibana_endpoint":
        ingress = shlex.quote(str(PurePosixPath(project_root) / "kibana" / "ingress.yaml"))
        route = shlex.quote(str(PurePosixPath(project_root) / "platform" / "openshift" / "route.yaml"))
        cmd = f"test -f {ingress} && echo present || test -f {route} && echo present || echo missing"
    else:
        return {"name": prerequisite, "ok": True, "detail": "No explicit check implemented"}
    result = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), cmd, remote_cfg.get("ssh_key_path", ""))
    stdout = result.get("stdout", "").strip()
    ok = (stdout not in {"", "missing"}) or (lower == "ssh" and result.get("ok", False))
    detail = stdout or result.get("stderr", "") or (f"{lower} available" if ok else f"{lower} not available")
    if lower == "kubeconfig" and ok and stdout not in {"present", "connected"}:
        detail = f"Using {stdout}"
    resolved = {"name": prerequisite, "ok": ok, "detail": detail}
    cache[lower] = resolved
    return resolved


def _evaluate_script_prerequisites(entry: Dict[str, Any], script: Dict[str, Any]) -> List[Dict[str, Any]]:
    target_type = (entry.get("target_type") or "local").strip()
    checks: List[Dict[str, Any]] = []
    if target_type == "remote":
        checks.append(_check_remote_prerequisite(entry, "ssh"))
    for prerequisite in script.get("prerequisites") or []:
        checks.append(_check_remote_prerequisite(entry, prerequisite) if target_type == "remote" else _check_local_prerequisite(entry, prerequisite))
    return checks


def _classification_from_severity(severity: str) -> str:
    return "blocking" if severity == "error" else ("warning" if severity == "warning" else "pass")


def _diagnostic_tool_item(name: str, ok: bool, detail: str, scope: str = "toolchain", severity: Optional[str] = None) -> Dict[str, Any]:
    actual_severity = severity or ("info" if ok else "warning")
    return {
        "scope": scope,
        "name": name,
        "ok": ok,
        "severity": actual_severity,
        "classification": _classification_from_severity(actual_severity),
        "detail": detail,
    }


def _collect_project_diagnostics(entry: Dict[str, Any]) -> Dict[str, Any]:
    target_type = (entry.get("target_type") or "local").strip() or "local"
    project_root, remote_cfg = _project_root_from_entry(entry)
    platform = (entry.get("platform") or "").strip().lower()
    items: List[Dict[str, Any]] = []
    next_actions: List[str] = []

    project_path_obj = Path(project_root).expanduser() if project_root else None
    if target_type == "local":
        path_ok = bool(project_path_obj and project_path_obj.exists())
        items.append(_diagnostic_tool_item("project_root", path_ok, f"Local project root {'found' if path_ok else 'missing'}: {project_root}", scope="project", severity="info" if path_ok else "error"))
        for tool in ["bash", "python3", "ssh", "curl", "kubectl", "terraform", "kustomize", "oc"]:
            binary = tool if tool != "python3" else "python3"
            location = shutil.which(binary)
            items.append(_diagnostic_tool_item(tool, location is not None, location or f"{tool} not found in PATH"))
        kubeconfig = _check_local_prerequisite(entry, "kubeconfig")
        items.append(_diagnostic_tool_item("kubeconfig", kubeconfig.get("ok", False), kubeconfig.get("detail", ""), scope="auth", severity="info" if kubeconfig.get("ok") else "warning"))
        if shutil.which("kubectl") and kubeconfig.get("ok"):
            context = _run_shell_command(["kubectl", "config", "current-context"], project_path_obj or Path.cwd())
            items.append(_diagnostic_tool_item("kubectl_context", context.get("ok", False), context.get("stdout") or context.get("stderr") or "kubectl context unavailable", scope="auth", severity="info" if context.get("ok") else "warning"))
        else:
            items.append(_diagnostic_tool_item("kubectl_context", False, "kubectl context check skipped", scope="auth", severity="warning"))
        if platform == "openshift":
            if shutil.which("oc"):
                whoami = _run_shell_command(["oc", "whoami"], project_path_obj or Path.cwd())
                items.append(_diagnostic_tool_item("openshift_auth", whoami.get("ok", False), whoami.get("stdout") or whoami.get("stderr") or "oc whoami failed", scope="auth", severity="info" if whoami.get("ok") else "warning"))
            else:
                items.append(_diagnostic_tool_item("openshift_auth", False, "oc not available; OpenShift auth check skipped", scope="auth", severity="warning"))
        if shutil.which("kubectl") and kubeconfig.get("ok"):
            cluster_info = _run_shell_command(["kubectl", "cluster-info"], project_path_obj or Path.cwd())
            items.append(_diagnostic_tool_item("cluster_api", cluster_info.get("ok", False), "Cluster API reachable" if cluster_info.get("ok") else (cluster_info.get("stderr") or cluster_info.get("stdout") or "kubectl cluster-info failed"), scope="cluster", severity="info" if cluster_info.get("ok") else "warning"))
            nodes = _run_shell_command(["kubectl", "get", "nodes", "--no-headers"], project_path_obj or Path.cwd())
            node_lines = [line for line in (nodes.get("stdout") or "").splitlines() if line.strip()]
            ready_nodes = sum(1 for line in node_lines if " Ready" in f" {line} ")
            items.append(_diagnostic_tool_item("nodes_ready", bool(node_lines), f"{ready_nodes}/{len(node_lines)} node(s) Ready" if node_lines else (nodes.get("stderr") or "No nodes reported"), scope="cluster", severity="info" if node_lines else "warning"))
    else:
        remote_cfg = remote_cfg or {}
        ssh_check = _check_remote_prerequisite(entry, "ssh")
        items.append(_diagnostic_tool_item("ssh", ssh_check.get("ok", False), ssh_check.get("detail", ""), scope="connectivity", severity="info" if ssh_check.get("ok") else "error"))
        remote_path_ok = False
        if ssh_check.get("ok") and project_root:
            probe = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), f"test -d {shlex.quote(project_root)} && echo present || echo missing", remote_cfg.get("ssh_key_path", ""))
            remote_path_ok = probe.get("stdout", "").strip() == "present"
            items.append(_diagnostic_tool_item("project_root", remote_path_ok, f"Remote project root {'found' if remote_path_ok else 'missing'}: {project_root}", scope="project", severity="info" if remote_path_ok else "error"))
        else:
            items.append(_diagnostic_tool_item("project_root", False, f"Remote project root not checked: {project_root}", scope="project", severity="error"))
        for tool in ["bash", "python3", "curl", "kubectl", "terraform", "kustomize", "oc"]:
            detail = _check_remote_prerequisite(entry, tool)
            items.append(_diagnostic_tool_item(tool, detail.get("ok", False), detail.get("detail", ""), scope="toolchain", severity="info" if detail.get("ok") else "warning"))
        kubeconfig = _check_remote_prerequisite(entry, "kubeconfig")
        items.append(_diagnostic_tool_item("kubeconfig", kubeconfig.get("ok", False), kubeconfig.get("detail", ""), scope="auth", severity="info" if kubeconfig.get("ok") else "warning"))
        if ssh_check.get("ok") and _check_remote_prerequisite(entry, "kubectl").get("ok") and kubeconfig.get("ok"):
            context = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), _remote_kubectl_command(entry, "kubectl config current-context"), remote_cfg.get("ssh_key_path", ""))
            items.append(_diagnostic_tool_item("kubectl_context", context.get("ok", False), context.get("stdout") or context.get("stderr") or "kubectl context unavailable", scope="auth", severity="info" if context.get("ok") else "warning"))
        else:
            items.append(_diagnostic_tool_item("kubectl_context", False, "kubectl context check skipped on remote host", scope="auth", severity="warning"))
        if platform == "openshift":
            oc_check = _check_remote_prerequisite(entry, "oc")
            if oc_check.get("ok"):
                whoami = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), "oc whoami", remote_cfg.get("ssh_key_path", ""))
                items.append(_diagnostic_tool_item("openshift_auth", whoami.get("ok", False), whoami.get("stdout") or whoami.get("stderr") or "oc whoami failed", scope="auth", severity="info" if whoami.get("ok") else "warning"))
            else:
                items.append(_diagnostic_tool_item("openshift_auth", False, "oc not available on remote host", scope="auth", severity="warning"))
        if ssh_check.get("ok") and _check_remote_prerequisite(entry, "kubectl").get("ok"):
            cluster_info = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), _remote_kubectl_command(entry, "kubectl cluster-info"), remote_cfg.get("ssh_key_path", ""))
            items.append(_diagnostic_tool_item("cluster_api", cluster_info.get("ok", False), "Cluster API reachable" if cluster_info.get("ok") else (cluster_info.get("stderr") or cluster_info.get("stdout") or "kubectl cluster-info failed"), scope="cluster", severity="info" if cluster_info.get("ok") else "warning"))
            nodes = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), _remote_kubectl_command(entry, "kubectl get nodes --no-headers"), remote_cfg.get("ssh_key_path", ""))
            node_lines = [line for line in (nodes.get("stdout") or "").splitlines() if line.strip()]
            ready_nodes = sum(1 for line in node_lines if " Ready" in f" {line} ")
            items.append(_diagnostic_tool_item("nodes_ready", bool(node_lines), f"{ready_nodes}/{len(node_lines)} node(s) Ready" if node_lines else (nodes.get("stderr") or "No nodes reported"), scope="cluster", severity="info" if node_lines else "warning"))

    missing_names = {item["name"] for item in items if not item.get("ok")}
    if "project_root" in missing_names:
        next_actions.append("Fix the linked project path before running validation or scripts.")
    if target_type == "remote" and "ssh" in missing_names:
        next_actions.append("Verify SSH host, user, port, and key path for the remote target.")
    if "kubeconfig" in missing_names:
        next_actions.append("Provide a working kubeconfig or run cluster-healthcheck to bootstrap kubeconfig before cluster checks.")
    if "cluster_api" in missing_names or "nodes_ready" in missing_names:
        next_actions.append("Check cluster reachability and node readiness before continuing with deployment actions.")
    if platform == "openshift" and ("oc" in missing_names or "openshift_auth" in missing_names):
        next_actions.append("Install and authenticate the OpenShift CLI (oc) for OpenShift-specific checks.")
    if "terraform" in missing_names:
        next_actions.append("Install Terraform if this project uses Terraform validation or deployment steps.")
    if "kubectl" in missing_names:
        next_actions.append("Install kubectl before running cluster verification or kustomize-based checks.")
    if "kustomize" in missing_names:
        next_actions.append("Install kustomize for native manifest build checks, or rely on kubectl kustomize.")
    if not next_actions:
        next_actions.append("Environment looks ready for validation and safe generated-script execution.")

    blocking = sum(1 for item in items if item["classification"] == "blocking")
    warnings = sum(1 for item in items if item["classification"] == "warning")
    passed = sum(1 for item in items if item["classification"] == "pass")
    return {
        "ok": blocking == 0,
        "target_type": target_type,
        "project_root": project_root,
        "platform": platform or "unknown",
        "remote": remote_cfg,
        "items": items,
        "counts": {"pass": passed, "warning": warnings, "blocking": blocking},
        "next_actions": next_actions,
    }


def _remote_script_gate(entry: Dict[str, Any], script: Dict[str, Any], diagnostics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if (entry.get("target_type") or "local").strip() != "remote":
        return {"ok": True, "blocked_reasons": [], "required_checks": []}
    diagnostics = diagnostics or _collect_project_diagnostics(entry)
    diag_map = {item.get("name"): item for item in diagnostics.get("items") or []}
    required_checks = ["ssh", "project_root"]
    if not script.get("safe", True):
        for check in script.get("prerequisite_checks") or []:
            name = str(check.get("name") or "")
            if name and name not in required_checks:
                required_checks.append(name)
        for name in ["kubeconfig", "kubectl_context", "openshift_auth"]:
            if name in diag_map and name not in required_checks:
                required_checks.append(name)
    blocked_reasons = []
    for name in required_checks:
        item = diag_map.get(name)
        if item and not item.get("ok"):
            blocked_reasons.append(f"{name}: {item.get('detail', 'not ready')}")
    if not script.get("safe", True) and diagnostics.get("counts", {}).get("blocking", 0) > 0:
        blocked_reasons.append("remote diagnostics still contain blocking findings")
    return {"ok": not blocked_reasons, "blocked_reasons": blocked_reasons, "required_checks": required_checks}


def _operation_scripts_for_entry(entry: Dict[str, Any], diagnostics: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    manifest = _operations_manifest_for_entry(entry)
    scripts = []
    for item in manifest.get("operations") or []:
        key = item.get("key", "")
        path = item.get("path") or SCRIPT_OPERATION_REGISTRY.get(key, {}).get("path", "")
        exists, resolved = _project_file_exists(entry, path)
        script = _hydrate_script_metadata(entry, {
            "key": key,
            **{k: v for k, v in item.items() if k != "key"},
            "exists": exists,
            "resolved_path": resolved,
        })
        checks = _evaluate_script_prerequisites(entry, script)
        script["prerequisite_checks"] = checks
        remote_gate = _remote_script_gate(entry, script, diagnostics=diagnostics)
        script["remote_gate"] = remote_gate
        script["blocked_reasons"] = list(remote_gate.get("blocked_reasons") or [])
        script["ready"] = exists
        scripts.append(script)
    return sorted(scripts, key=lambda item: (item.get("recommended_order", 999), item.get("title", item.get("key", ""))))


def _entry_generated_paths(entry: Dict[str, Any]) -> List[str]:
    return [str(path) for path in (entry.get("files_created") or []) if path]


def _derive_kustomization_names_for_entry(entry: Dict[str, Any]) -> List[str]:
    pn = str(entry.get("name") or "").strip()
    if not pn:
        return []
    names = [pn, f"{pn}-infra", f"{pn}-apps"]
    generated_paths = _entry_generated_paths(entry)
    generated_set = set(generated_paths)
    has_agents = any(path.startswith("agents/") or path.endswith("kustomization-agents.yaml") for path in generated_set)
    has_observability = any(path.startswith("observability/") or path.endswith("kustomization-observability.yaml") for path in generated_set)
    if not generated_set:
        project_root, remote_cfg = _project_root_from_entry(entry)
        if project_root or remote_cfg:
            has_agents = _project_file_exists(entry, "agents/kustomization.yaml")[0]
            has_observability = _project_file_exists(entry, "observability/kustomization.yaml")[0]
        else:
            has_agents = True
            has_observability = False
    if has_agents:
        names.append(f"{pn}-agents")
    if has_observability:
        names.append(f"{pn}-observability")
    return names


def _derive_kustomization_names(project_name: str) -> List[str]:
    pn = project_name.strip()
    return [pn, f"{pn}-infra", f"{pn}-apps", f"{pn}-agents"]


def _classify_kustomization_state(ready: str, reason: str) -> str:
    ready_lower = (ready or "").strip().lower()
    reason_lower = (reason or "").strip().lower()
    if ready_lower == "true":
        return "ready"
    if ready_lower == "false" and any(token in reason_lower for token in ["progress", "reconcil", "inprogress"]):
        return "reconciling"
    if ready_lower == "false":
        return "failed"
    return "unknown"


def _summarize_kustomizations(kustomizations: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"ready": 0, "reconciling": 0, "failed": 0, "unknown": 0, "total": len(kustomizations or [])}
    for item in kustomizations or []:
        counts[_classify_kustomization_state(item.get("ready", ""), item.get("reason", ""))] += 1
    overall = "unknown"
    if counts["total"]:
        if counts["failed"]:
            overall = "failed"
        elif counts["reconciling"]:
            overall = "reconciling"
        elif counts["ready"] == counts["total"]:
            overall = "ready"
    return {"counts": counts, "overall": overall}


def _parse_ks_kubectl_output(stdout: str) -> tuple:
    """Parse 'Ready|Reason|Message' from kubectl jsonpath output."""
    parts = (stdout or "").split("|", 2)
    ready = parts[0].strip() if len(parts) > 0 else ""
    reason = parts[1].strip() if len(parts) > 1 else ""
    message = parts[2].strip() if len(parts) > 2 else ""
    return ready, reason, message


def _build_flux_access_summary(entry: Dict[str, Any], kubeconfig: str = "") -> Dict[str, Any]:
    target_type = (entry.get("target_type") or "local").strip() or "local"
    access: Dict[str, Any] = {
        "target_type": target_type,
        "mode": "remote-host" if target_type == "remote" else "local-workstation",
        "kubeconfig": {"ok": False, "detail": "unknown", "source": "unknown"},
        "kubectl_context": {"ok": False, "detail": "not checked"},
        "cluster_api": {"ok": False, "detail": "not checked"},
        "nodes_ready": {"ok": False, "detail": "not checked"},
    }
    if target_type == "remote":
        _, remote_cfg = _project_root_from_entry(entry)
        remote_cfg = remote_cfg or {}
        access["remote"] = {
            "host": remote_cfg.get("host", ""),
            "user": remote_cfg.get("user", ""),
            "port": str(remote_cfg.get("port", "22")),
            "project_dir": remote_cfg.get("project_dir", ""),
        }
        kube = _check_remote_prerequisite(entry, "kubeconfig")
        kube_detail = str(kube.get("detail") or "")
        access["kubeconfig"] = {
            "ok": kube.get("ok", False),
            "detail": kube_detail or ("kubeconfig detected" if kube.get("ok") else "No kubeconfig detected"),
            "source": _classify_kubeconfig_source(kube_detail, entry, "remote") if kube.get("ok") else "missing",
        }
        if _check_remote_prerequisite(entry, "kubectl").get("ok") and kube.get("ok"):
            ctx = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), _remote_kubectl_command(entry, "kubectl config current-context"), remote_cfg.get("ssh_key_path", ""))
            access["kubectl_context"] = {"ok": ctx.get("ok", False), "detail": (ctx.get("stdout") or ctx.get("stderr") or "kubectl context unavailable").strip()}
            cluster = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), _remote_kubectl_command(entry, "kubectl cluster-info"), remote_cfg.get("ssh_key_path", ""))
            access["cluster_api"] = {"ok": cluster.get("ok", False), "detail": ("Cluster API reachable" if cluster.get("ok") else (cluster.get("stderr") or cluster.get("stdout") or "kubectl cluster-info failed")).strip()}
            nodes = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), _remote_kubectl_command(entry, "kubectl get nodes --no-headers"), remote_cfg.get("ssh_key_path", ""))
            node_lines = [line for line in (nodes.get("stdout") or "").splitlines() if line.strip()]
            ready_nodes = sum(1 for line in node_lines if " Ready" in f" {line} ")
            access["nodes_ready"] = {"ok": bool(node_lines), "detail": f"{ready_nodes}/{len(node_lines)} node(s) Ready" if node_lines else (nodes.get("stderr") or "No nodes reported")}
        return access

    kube_env = os.environ.copy()
    kube_source = "default"
    if kubeconfig.strip():
        path = Path(kubeconfig).expanduser()
        kube = {"name": "kubeconfig", "ok": path.exists(), "detail": f"Using {path}" if path.exists() else f"Missing explicit kubeconfig: {path}"}
        kube_source = "explicit"
        kube_env["KUBECONFIG"] = str(path)
    else:
        kube = _check_local_prerequisite(entry, "kubeconfig")
        kube_source = _classify_kubeconfig_source(str(kube.get("detail") or ""), entry, "local") if kube.get("ok") else "missing"
    access["kubeconfig"] = {"ok": kube.get("ok", False), "detail": str(kube.get("detail") or ""), "source": kube_source}
    if shutil.which("kubectl") and kube.get("ok"):
        ctx = _run_shell_command(["kubectl", "config", "current-context"], Path.cwd(), env=kube_env)
        access["kubectl_context"] = {"ok": ctx.get("ok", False), "detail": (ctx.get("stdout") or ctx.get("stderr") or "kubectl context unavailable").strip()}
        cluster = _run_shell_command(["kubectl", "cluster-info"], Path.cwd(), env=kube_env)
        access["cluster_api"] = {"ok": cluster.get("ok", False), "detail": ("Cluster API reachable" if cluster.get("ok") else (cluster.get("stderr") or cluster.get("stdout") or "kubectl cluster-info failed")).strip()}
        nodes = _run_shell_command(["kubectl", "get", "nodes", "--no-headers"], Path.cwd(), env=kube_env)
        node_lines = [line for line in (nodes.get("stdout") or "").splitlines() if line.strip()]
        ready_nodes = sum(1 for line in node_lines if " Ready" in f" {line} ")
        access["nodes_ready"] = {"ok": bool(node_lines), "detail": f"{ready_nodes}/{len(node_lines)} node(s) Ready" if node_lines else (nodes.get("stderr") or "No nodes reported")}
    return access


def _run_rsync_to_remote(local_src: Path, host: str, port: str, user: str, remote_target: str, ssh_key_path: str = "") -> Dict[str, Any]:
    ssh_parts = ["ssh", "-p", str(port), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new"]
    if ssh_key_path.strip():
        ssh_parts.extend(["-i", str(Path(ssh_key_path).expanduser())])
    cmd = [
        "rsync", "-az", "--delete",
        "-e", " ".join(ssh_parts),
        f"{str(local_src).rstrip('/')}/",
        f"{user}@{host}:{remote_target.rstrip('/')}/",
    ]
    return _run_shell_command(cmd, Path.cwd())


def _normalize_remote_base_dir(base_dir: str) -> str:
    raw = (base_dir or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="remote_base_dir is required for remote target")
    if not raw.startswith("/"):
        raise HTTPException(status_code=400, detail="remote_base_dir must be an absolute POSIX path")
    return str(PurePosixPath(raw))

def _apply_forced_type(desc: str, forced_type: str) -> str:
    if forced_type and forced_type != "auto":
        return f"{forced_type} {desc}"
    return desc


def _normalize_target_dir(target_dir: str) -> str:
    path = Path(target_dir).expanduser()
    if not path.is_absolute():
        path = Path.home() / path
    return str(path.resolve())


def _expand_input_path(raw_path: str) -> Path:
    p = Path(raw_path or "").expanduser()
    if not p.is_absolute():
        p = Path.home() / p
    return p


def _is_path_within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except (ValueError, RuntimeError, OSError):
        return False


def _infer_platform_from_text(text: str) -> Optional[str]:
    t = (text or "").lower()
    if any(k in t for k in ["openshift", "ocp", "redhat", "okd"]):
        return "openshift"
    if any(k in t for k in ["rke2", "rancher"]):
        return "rke2"
    if any(k in t for k in ["proxmox", "pve"]):
        return "proxmox"
    if any(k in t for k in ["aks", "azure kubernetes", "azure"]):
        return "aks"
    return None


def _has_infra_keywords(text: str) -> bool:
    """Check if text contains any platform or gitops keywords."""
    t = (text or "").lower()
    keywords = [
        "openshift", "ocp", "redhat", "okd",
        "rke2", "rancher",
        "proxmox", "pve",
        "aks", "azure", "azure kubernetes",
        "terraform",
        "flux", "fluxcd", "argo", "argocd", "gitops",
    ]
    return any(k in t for k in keywords)


def _override_chain(result: Dict[str, Any], forced_chain: str) -> Dict[str, Any]:
    if not forced_chain:
        return result
    analyzer = ProjectAnalyzer(config_path=str(ROOT_DIR))
    return analyzer.override_chain(result, forced_chain)


def _serialize_sizing_messages(messages: List[Any] | tuple[Any, ...]) -> List[Dict[str, Any]]:
    serialized = []
    for message in messages or []:
        serialized.append(
            {
                "code": getattr(message, "code", ""),
                "severity": getattr(message, "severity", "warning"),
                "message": getattr(message, "message", str(message)),
                "field_path": getattr(message, "field_path", None),
            }
        )
    return serialized


def _normalize_project_header(raw_header: Any) -> Dict[str, str]:
    if not isinstance(raw_header, dict):
        return {}
    header: Dict[str, str] = {}
    for field in ("name", "customer", "description", "project_id", "user_name"):
        value = raw_header.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            header[field] = text
    return header


def _build_prefill_description(project_header: Dict[str, str], platform_detected: Optional[str]) -> str:
    explicit = (project_header.get("description") or "").strip()
    if explicit:
        return explicit

    name = (project_header.get("name") or "").strip()
    customer = (project_header.get("customer") or "").strip()
    project_id = (project_header.get("project_id") or "").strip()
    user_name = (project_header.get("user_name") or "").strip()

    parts: List[str] = []
    if name and customer and customer.lower() != name.lower():
        parts.append(f"{name} ({customer})")
    elif name:
        parts.append(name)
    elif customer:
        parts.append(customer)

    if platform_detected:
        parts.append(f"platform={platform_detected}")
    if project_id:
        parts.append(f"project_id={project_id}")
    if user_name:
        parts.append(f"owner={user_name}")

    return " | ".join(parts)


def _build_sizing_preview_payload(result: Any) -> Dict[str, Any]:
    model = result.model
    ctx = result.addon_context or {}
    pools = list(model.pools) if model else list(
        ((ctx.get("rke2") or {}).get("pools") or ((ctx.get("openshift") or {}).get("pools") or []))
    )
    metadata = (model.metadata if model else ctx.get("metadata", {})) or {}
    project_header = _normalize_project_header(metadata)
    raw_payload = (ctx.get("raw") if isinstance(ctx.get("raw"), dict) else None) or (
        model.raw if model and isinstance(model.raw, dict) else {}
    )
    generated_at = raw_payload.get("generated_at") or raw_payload.get("created_at") or raw_payload.get("timestamp")
    platform_detected = model.platform_detected if model else ctx.get("platform_detected")

    prefill_project_name = (project_header.get("name") or project_header.get("customer") or "").strip()
    return {
        "ok": result.fatal_error is None,
        "schema_version": model.schema_version if model else None,
        "source_format": model.source_format if model else None,
        "platform_detected": platform_detected,
        "health_score": ctx.get("health_score"),
        "inputs": model.inputs if model else {},
        "summary": model.summary if model else {},
        "tiers": model.tiers if model else {},
        "components": model.components if model else {},
        "pools": pools,
        "project_header": project_header,
        "sizing_generated_at": generated_at,
        "prefill_project_name": prefill_project_name,
        "prefill_description": _build_prefill_description(project_header, platform_detected),
        "warnings": _serialize_sizing_messages(result.warnings),
        "fatal_error": _serialize_sizing_messages([result.fatal_error])[0] if result.fatal_error else None,
        "sizing_context_applied": result.addon_context is not None and result.fatal_error is None,
    }


def _build_delivery_caveats(
    *,
    effective_platform: Optional[str],
    description: str = "",
    enable_otel_collector: bool = False,
    use_terraform_iac: bool = False,
) -> List[Dict[str, str]]:
    platform_name = (effective_platform or "").strip().lower()
    raw = " ".join([description or "", platform_name]).lower()
    caveats: List[Dict[str, str]] = []

    def add(code: str, severity: str, message: str) -> None:
        caveats.append({"code": code, "severity": severity, "message": message})

    if platform_name == "proxmox":
        add(
            "proxmox_rke2_bootstrap",
            "warning",
            "Proxmox delivery uses the in-repo RKE2 bootstrap path. Terraform outputs, SSH reachability, and bootstrap-node kubeconfig retrieval must work before GitOps health checks will pass.",
        )
    elif platform_name == "rke2":
        add(
            "rke2_delivery_scope",
            "info",
            "RKE2 delivery assumes a workload cluster path. If infrastructure is external, validate kubeconfig access and storage-class alignment before generation.",
        )
        if any(token in raw for token in ("rancher", "fleet")):
            add(
                "rancher_governance_overlay",
                "info",
                "Rancher/Fleet governance is an overlay on top of the RKE2 workload cluster. Bootstrap or import the cluster first, then layer governance and GitOps policies.",
            )
    elif platform_name == "openshift":
        add(
            "openshift_delivery_scope",
            "info",
            "OpenShift scaffolding is aimed at Day-1 and Day-2 delivery. Review Routes, SCC posture, and worker-pool intent before rollout.",
        )
        if use_terraform_iac:
            add(
                "openshift_iac_scope",
                "warning",
                "Terraform in this scaffold does not provision an OpenShift cluster. It complements an existing platform with Elastic, GitOps, and platform overlays.",
            )
    elif platform_name == "aks":
        add(
            "aks_managed_cluster",
            "info",
            "AKS is treated as a managed-cluster delivery path. Validate ingress class, storage defaults, and node-pool mapping against your Azure baseline.",
        )

    if enable_otel_collector:
        if platform_name == "openshift":
            add(
                "openshift_otel_scc",
                "warning",
                "OpenShift may reject hostPath-based collectors without the right SCC posture. Validate admission and namespace policy before enabling the collector in production.",
            )
        elif platform_name == "aks":
            add(
                "aks_otel_overlap",
                "info",
                "AKS already ships managed metrics-server and often Azure Monitor. Review overlap before enabling extra observability components.",
            )
        elif platform_name in {"proxmox", "rke2"}:
            add(
                "rke2_otel_timing",
                "info",
                "Apply observability only after the workload cluster is reachable and Elasticsearch credentials can be mirrored into the observability namespace.",
            )

    return caveats


def _enrich_sizing_preview(
    preview: Dict[str, Any],
    *,
    selected_platform: str = "",
    description: str = "",
    enable_otel_collector: bool = False,
    use_terraform_iac: bool = False,
) -> Dict[str, Any]:
    enriched = dict(preview or {})
    selected = (selected_platform or "").strip().lower()
    detected = (enriched.get("platform_detected") or "").strip().lower()
    if selected == "proxmox":
        effective_platform = "proxmox"
        platform_source = "user_selection"
    elif detected:
        effective_platform = detected
        platform_source = "sizing_file"
    elif selected:
        effective_platform = selected
        platform_source = "user_selection"
    else:
        effective_platform = None
        platform_source = None
    enriched["effective_platform"] = effective_platform
    enriched["platform_source"] = platform_source
    enriched["caveats"] = _build_delivery_caveats(
        effective_platform=effective_platform,
        description=description,
        enable_otel_collector=enable_otel_collector,
        use_terraform_iac=use_terraform_iac,
    )
    return enriched


def _addon_preview_areas(name: str) -> List[str]:
    return {
        "sizing_integration": ["sizing/", "capacity planning", "resource requirements"],
        "eck_deployment": ["elasticsearch/", "kibana/", "agents/"],
        "flux_deployment": ["flux-system/", "apps/", "overlays/", "clusters/"],
        "argo_deployment": ["argocd/", "apps/"],
        "terraform_platform": ["terraform/", "platform/", "scripts/"],
        "terraform_aks": ["terraform/", "platform/aks/"],
        "terraform_gitops_trigger": ["scripts/", "docs/"],
        "platform_manifests": ["platform/", "docs/"],
        "observability_stack": ["observability/", "docs/", "infrastructure/"],
        "rke2_bootstrap": ["scripts/", "ansible/", "docs/"],
        "deployment_lifecycle": ["scripts/", "docs/"],
        "scripts_docs": ["scripts/README.md", "docs/"],
    }.get(name, ["generated scaffold"])


def _build_addon_preview(
    *,
    project_name: str,
    description: str,
    forced_type: str,
    forced_chain: str,
    effective_platform: Optional[str],
    gitops_tool: str,
    use_terraform_iac: bool,
    enable_otel_collector: bool,
    sizing_context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    effective_desc = _apply_forced_type(description, forced_type)
    analysis = analyze_project(project_name or "preview-project", effective_desc, config_path=str(ROOT_DIR))
    analysis = _override_chain(analysis, forced_chain)
    loader = AddonLoader(config_path=str(ROOT_DIR))
    context = {
        "platform": effective_platform or "",
        "gitops_tool": gitops_tool or "flux",
        "iac_tool": "terraform" if use_terraform_iac else "",
        "enable_otel_collector": enable_otel_collector,
        "sizing_context": sizing_context or {},
    }
    matched = loader.match_addons(analysis, context=context, interactive_mode=False)
    return {
        "primary_category": analysis.get("primary_category"),
        "priority_chain": analysis.get("priority_chain"),
        "addons": [
            {
                "name": spec.name,
                "description": spec.description,
                "priority": spec.priority,
                "areas": _addon_preview_areas(spec.name),
            }
            for spec in matched
        ],
    }


def _classify_output_family(path: str) -> str:
    normalized = (path or "").replace("\\", "/")
    if normalized.startswith("terraform/") or normalized.startswith("ansible/"):
        return "infrastructure"
    if normalized.startswith("platform/"):
        return "platform"
    if normalized.startswith("elasticsearch/") or normalized.startswith("kibana/") or normalized.startswith("agents/"):
        return "elastic"
    if normalized.startswith("observability/") or normalized.startswith("sizing/"):
        return "observability"
    if normalized.startswith("scripts/") or normalized.startswith("docs/"):
        return "automation"
    if normalized.startswith("flux-system/") or normalized.startswith("argocd/") or normalized.startswith("apps/") or normalized.startswith("overlays/") or normalized.startswith("clusters/") or normalized.startswith("base/") or normalized.startswith("infrastructure/"):
        return "gitops"
    return "other"


def _build_output_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    files = list(result.get("files_created") or result.get("generated_files") or [])
    families: Dict[str, Dict[str, Any]] = {}
    for path in files:
        family = _classify_output_family(str(path))
        bucket = families.setdefault(family, {"count": 0, "samples": []})
        bucket["count"] += 1
        if len(bucket["samples"]) < 5:
            bucket["samples"].append(str(path))
    ordered = []
    for name in ["infrastructure", "platform", "elastic", "observability", "gitops", "automation", "other"]:
        if name in families:
            ordered.append({"family": name, **families[name]})
    return {
        "total_files": len(files),
        "families": ordered,
        "addons_triggered": list(result.get("addons_triggered") or []),
    }


def _resolve_policy_profile(policy_profile: str, license_id: str, confidentiality: str, header_mode: str) -> tuple[str, str, str, str]:
    profile_key = (policy_profile or "").strip()
    profile = POLICY_PROFILES.get(profile_key)
    if not profile:
        return "", license_id, confidentiality, header_mode
    return (
        profile_key,
        (license_id or profile.get("license_id") or "UNLICENSED").strip() or profile.get("license_id") or "UNLICENSED",
        (confidentiality or profile.get("confidentiality") or "internal").strip() or profile.get("confidentiality") or "internal",
        (header_mode or profile.get("header_mode") or "none").strip() or profile.get("header_mode") or "none",
    )


def _build_governance_preview(
    *,
    license_id: str = "UNLICENSED",
    confidentiality: str = "internal",
    header_mode: str = "none",
    copyright_owner: str = "",
    organization: str = "",
    policy_profile: str = "",
) -> Dict[str, Any]:
    profile_key, license_id, confidentiality, header_mode = _resolve_policy_profile(
        policy_profile,
        license_id,
        confidentiality,
        header_mode,
    )
    license_id = (license_id or "UNLICENSED").strip() or "UNLICENSED"
    confidentiality = (confidentiality or "internal").strip() or "internal"
    header_mode = (header_mode or "none").strip() or "none"
    copyright_owner = (copyright_owner or "").strip()
    organization = (organization or "").strip()

    items: List[Dict[str, str]] = []

    def add(code: str, severity: str, message: str) -> None:
        items.append({"scope": "governance", "code": code, "severity": severity, "message": message})

    if confidentiality == "public" and license_id == "UNLICENSED":
        add("public_unlicensed", "warning", "Public output should define an explicit license.")
    if header_mode in {"minimal", "full"} and not (copyright_owner or organization):
        add("missing_owner_metadata", "warning", "Header mode is enabled but copyright owner or organization is empty.")
    if confidentiality == "restricted" and header_mode == "none":
        add("restricted_without_headers", "info", "Restricted output is easier to audit with a managed header mode.")
    profile = POLICY_PROFILES.get(profile_key)
    if profile and profile.get("organization_required") and not organization:
        add("organization_required", "warning", f"Policy profile '{profile_key}' expects an organization value.")

    return {
        "policy_profile": profile_key,
        "license_policy": {
            "license_id": license_id,
            "mode": "user_selectable",
            "copyright_owner": copyright_owner,
            "organization": organization,
            "confidentiality": confidentiality,
        },
        "header_policy": {
            "mode": header_mode,
            "managed_header": header_mode != "none",
            "apply_to": [".py", ".sh", ".tf", ".yaml", ".yml", ".md"],
        },
        "validation": {
            "ok": not any(item["severity"] == "warning" for item in items),
            "items": items,
        },
    }


def _load_generation_validation_report(result: Dict[str, Any]) -> Dict[str, Any]:
    report_path = result.get("generation_validation_report")
    if not report_path:
        return {"ok": True, "items": [], "summary": {}}
    try:
        payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("validation report must be an object")
        payload.setdefault("ok", True)
        payload.setdefault("items", [])
        payload.setdefault("summary", {})
        return payload
    except (OSError, json.JSONDecodeError, ValueError):
        return {
            "ok": False,
            "items": [
                {
                    "scope": "generation",
                    "code": "validation_report_unreadable",
                    "severity": "error",
                    "message": f"Could not read generation validation report: {report_path}",
                }
            ],
            "summary": {},
        }


async def _parse_uploaded_sizing_file(upload: Optional[UploadFile]) -> tuple[Optional[Dict[str, Any]], Optional[str], Dict[str, Any]]:
    if upload is None:
        return None, None, {"ok": True, "warnings": [], "fatal_error": None, "sizing_context_applied": False}
    if not upload.filename:
        raise HTTPException(status_code=400, detail="sizing_file must be provided")
    lower_name = upload.filename.lower()
    if not (lower_name.endswith(".md") or lower_name.endswith(".json")):
        raise HTTPException(status_code=400, detail="sizing_file must be a .json or .md file")

    suffix = ".json" if lower_name.endswith(".json") else ".md"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        raw = await upload.read()
        tmp.write(raw)
        tmp_path = Path(tmp.name)

    try:
        detailed = parse_sizing_file_detailed(str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)

    preview = _build_sizing_preview_payload(detailed)
    if detailed.fatal_error is not None:
        return None, None, preview
    sizing_context = detailed.addon_context
    detected_platform = sizing_context.get("platform_detected") if sizing_context else None
    return sizing_context, detected_platform, preview


def _build_open_command(tool: str, target_path: Path) -> List[str]:
    if tool == "zed":
        if shutil.which("zed") is None:
            raise HTTPException(
                status_code=400, detail="zed is not installed or not in PATH"
            )
        return ["zed", str(target_path)]

    if tool == "vscode":
        if shutil.which("code") is None:
            raise HTTPException(
                status_code=400,
                detail="vscode CLI 'code' is not installed or not in PATH",
            )
        return ["code", str(target_path)]

    if tool == "filemanager":
        if sys.platform == "darwin":
            return ["open", str(target_path)]
        if sys.platform.startswith("linux"):
            if shutil.which("xdg-open") is None:
                raise HTTPException(status_code=400, detail="xdg-open is not installed")
            return ["xdg-open", str(target_path)]
        raise HTTPException(
            status_code=400, detail=f"Unsupported platform: {sys.platform}"
        )

    raise HTTPException(
        status_code=400, detail="Unsupported tool. Use zed, vscode, or filemanager"
    )


def _build_open_remote_command(tool: str, host: str, user: str, remote_path: str, port: str = "22") -> List[str]:
    normalized_port = (port or "22").strip() or "22"
    encoded_path = quote(remote_path, safe="/~._-")
    authority = f"{user}@{host}"
    if normalized_port != "22":
        authority = f"{authority}:{normalized_port}"

    if tool == "zed":
        if shutil.which("zed") is None:
            raise HTTPException(status_code=400, detail="zed is not installed or not in PATH")
        return ["zed", f"ssh://{authority}{encoded_path}"]

    if tool == "vscode":
        if shutil.which("code") is None:
            raise HTTPException(status_code=400, detail="vscode CLI 'code' is not installed or not in PATH")
        vscode_host = host if normalized_port == "22" else f"{host}:{normalized_port}"
        uri = f"vscode-remote://ssh-remote+{vscode_host}{encoded_path}"
        return ["code", "--folder-uri", uri]

    raise HTTPException(status_code=400, detail="Remote open supports zed or vscode")


def _pick_directory_os_dialog(initial_path: Optional[str] = None) -> str:
    """Open native folder picker and return selected absolute directory."""
    start_dir = _expand_input_path(initial_path or str(USER_HOME))
    if not start_dir.exists():
        start_dir = USER_HOME

    if sys.platform == "darwin":
        script = (
            'set chosenFolder to choose folder with prompt "Select folder" '
            f'default location POSIX file "{str(start_dir)}"\n'
            "POSIX path of chosenFolder"
        )
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip().lower()
            if "user canceled" in stderr:
                raise HTTPException(status_code=400, detail="Folder selection cancelled")
            raise HTTPException(status_code=500, detail="Failed to open folder dialog")
        selected = (proc.stdout or "").strip()
        if not selected:
            raise HTTPException(status_code=400, detail="No folder selected")
        return str(Path(selected).expanduser().resolve())

    if sys.platform.startswith("linux"):
        if shutil.which("zenity") is None:
            raise HTTPException(
                status_code=501, detail="Linux folder picker unavailable (install zenity)"
            )
        proc = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--directory",
                "--title=Select folder",
                f"--filename={str(start_dir)}/",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise HTTPException(status_code=400, detail="Folder selection cancelled")
        selected = (proc.stdout or "").strip()
        if not selected:
            raise HTTPException(status_code=400, detail="No folder selected")
        return str(Path(selected).expanduser().resolve())

    raise HTTPException(status_code=501, detail=f"Folder picker not supported on {sys.platform}")


@app.get("/")
def index() -> FileResponse:
    if not FRONTEND_DIR.exists():
        raise HTTPException(status_code=404, detail="Frontend assets not bundled")
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/documentation")
def documentation() -> FileResponse:
    if not FRONTEND_DIR.exists():
        raise HTTPException(status_code=404, detail="Frontend assets not bundled")
    doc_page = FRONTEND_DIR / "documentation.html"
    if not doc_page.exists():
        raise HTTPException(status_code=404, detail="Documentation page not found")
    return FileResponse(str(doc_page))


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "environment": RUNTIME_ENV}


@app.get("/api/meta")
def meta() -> Dict[str, Any]:
    analyzer = ProjectAnalyzer(config_path=str(ROOT_DIR))
    return {
        "types": [
            "auto",
            "elasticsearch",
            "kubernetes",
            "terraform",
            "azure",
            "gitops",
        ],
        "platforms": ["", "rke2", "openshift", "aks", "proxmox"],
        "gitops_tools": ["", "flux", "argo", "none"],
        "chains": sorted(list(analyzer.priority_chains.keys())),
    }


@app.get("/api/presets")
def get_presets() -> Dict[str, Any]:
    return {
        "platform_presets": PLATFORM_PRESETS,
        "policy_profiles": POLICY_PROFILES,
    }


@app.get("/api/preferences")
def get_preferences() -> Dict[str, Any]:
    return PREFERENCES.get()


@app.post("/api/preferences")
def update_preferences(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="preferences payload must be an object")
    return PREFERENCES.update(payload)


@app.get("/api/fs/suggest")
def fs_suggest(query: str = "", limit: int = 12) -> Dict[str, Any]:
    q = (query or "").strip()
    limit = max(1, min(limit, 100))

    if not q or q == "~":
        return {
            "suggestions": _get_default_suggestions(),
            "resolved_query": str(USER_HOME),
            "parent": str(USER_HOME),
        }

    raw = _expand_input_path(q)

    if q.endswith("/") or q.endswith("\\"):
        parent = raw
        prefix = ""
    else:
        parent = raw.parent
        prefix = raw.name

    if not parent.exists() or not parent.is_dir():
        return {"suggestions": [], "resolved_query": str(raw), "parent": str(parent)}

    matches: List[str] = []
    try:
        for child in sorted(parent.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir():
                continue
            if prefix and not child.name.lower().startswith(prefix.lower()):
                continue
            resolved = str(child.resolve())
            if parent == Path("/"):
                if child.name in SYSTEM_DIRECTORIES:
                    continue
            if not _is_user_accessible(child):
                continue
            matches.append(resolved)
            if len(matches) >= limit:
                break
    except PermissionError:
        return {"suggestions": [], "resolved_query": str(raw), "parent": str(parent)}

    return {"suggestions": matches, "resolved_query": str(raw), "parent": str(parent)}


@app.get("/api/fs/stat")
def fs_stat(path: str) -> Dict[str, Any]:
    p = _expand_input_path(path).resolve()
    return {
        "path": str(p),
        "exists": p.exists(),
        "is_dir": p.is_dir(),
        "parent_exists": p.parent.exists(),
    }


@app.get("/api/fs/pick-directory")
def fs_pick_directory(initial_path: str = "") -> Dict[str, Any]:
    if not RUNTIME_ENV["supports_native_picker"]:
        return {
            "fallback": True,
            "message": RUNTIME_ENV.get("picker_message", ""),
            "supports_native_picker": False,
        }

    try:
        selected = _pick_directory_os_dialog(initial_path=initial_path)
    except HTTPException as exc:
        if exc.status_code == 501:
            return {
                "fallback": True,
                "message": exc.detail,
                "supports_native_picker": False,
            }
        raise

    p = Path(selected).resolve()
    return {
        "path": str(p),
        "exists": p.exists(),
        "is_dir": p.is_dir(),
        "fallback": False,
    }




@app.post("/api/remote/test")
def remote_test(
    remote_host: str = Form(...),
    remote_port: str = Form("22"),
    remote_user: str = Form(...),
    remote_ssh_key_path: str = Form(""),
) -> Dict[str, Any]:
    host = remote_host.strip()
    user = remote_user.strip()
    if not host or not user:
        raise HTTPException(status_code=400, detail="remote_host and remote_user are required")

    cmd = _run_ssh_command(
        host=host,
        port=(remote_port or "22").strip() or "22",
        user=user,
        remote_cmd="echo connected",
        ssh_key_path=remote_ssh_key_path,
    )
    if not cmd["ok"]:
        raise HTTPException(status_code=400, detail=f"Remote SSH test failed: {cmd['stderr'] or cmd['stdout']}")
    return {"ok": True, "host": host, "user": user, "port": (remote_port or "22").strip() or "22", "stdout": cmd.get("stdout", "")}

@app.post("/api/analyze")
def analyze(
    name: str = Form(...),
    description: str = Form(...),
    forced_type: str = Form("auto"),
    forced_chain: str = Form(""),
) -> Dict[str, Any]:
    effective_desc = _apply_forced_type(description, forced_type)
    result = analyze_project(name, effective_desc, config_path=str(ROOT_DIR))
    result = _override_chain(result, forced_chain)
    return result


@app.post("/api/sizing/preview")
async def preview_sizing_file(
    sizing_file: Optional[UploadFile] = File(default=None),
    name: str = Form("preview-project"),
    forced_type: str = Form("auto"),
    forced_chain: str = Form(""),
    platform: str = Form(""),
    gitops_tool: str = Form(""),
    description: str = Form(""),
    enable_otel_collector: bool = Form(False),
    use_terraform_iac: bool = Form(False),
    license_id: str = Form("UNLICENSED"),
    confidentiality: str = Form("internal"),
    header_mode: str = Form("none"),
    copyright_owner: str = Form(""),
    organization: str = Form(""),
    policy_profile: str = Form(""),
) -> Dict[str, Any]:
    sizing_context, _detected_platform, preview = await _parse_uploaded_sizing_file(sizing_file)
    preview = _enrich_sizing_preview(
        preview,
        selected_platform=platform,
        description=description,
        enable_otel_collector=enable_otel_collector,
        use_terraform_iac=use_terraform_iac,
    )
    preview["addon_preview"] = _build_addon_preview(
        project_name=name,
        description=description,
        forced_type=forced_type,
        forced_chain=forced_chain,
        effective_platform=preview.get("effective_platform"),
        gitops_tool=gitops_tool,
        use_terraform_iac=use_terraform_iac,
        enable_otel_collector=enable_otel_collector,
        sizing_context=sizing_context,
    )
    preview["governance_preview"] = _build_governance_preview(
        license_id=license_id,
        confidentiality=confidentiality,
        header_mode=header_mode,
        copyright_owner=copyright_owner,
        organization=organization,
        policy_profile=policy_profile,
    )
    return preview


@app.post("/api/create")
async def create_project(
    name: str = Form(...),
    description: str = Form(""),
    target_dir: str = Form(...),
    forced_type: str = Form("auto"),
    forced_chain: str = Form(""),
    platform: str = Form(""),
    gitops_tool: str = Form(""),
    git_init: bool = Form(False),
    git_commit_message: str = Form("Initial commit: project scaffold"),
    git_remote_url: str = Form(""),
    git_branch: str = Form("main"),
    git_push: bool = Form(False),
    git_token: str = Form(""),
    git_provider: str = Form(""),
    git_namespace: str = Form(""),
    create_remote_repo: bool = Form(False),
    git_private_repo: bool = Form(True),
    git_schema_id: str = Form(""),
    use_terraform_iac: bool = Form(False),
    fallback_storage_class: str = Form(""),
    run_terraform_apply: bool = Form(False),
    enable_metrics_server: bool = Form(False),
    enable_otel_collector: bool = Form(False),
    target_type: str = Form("local"),
    remote_host: str = Form(""),
    remote_port: str = Form("22"),
    remote_user: str = Form(""),
    remote_auth_mode: str = Form("ssh_key"),
    remote_ssh_key_path: str = Form(""),
    remote_base_dir: str = Form(""),
    license_id: str = Form("UNLICENSED"),
    confidentiality: str = Form("internal"),
    header_mode: str = Form("none"),
    copyright_owner: str = Form(""),
    organization: str = Form(""),
    policy_profile: str = Form(""),
    continue_without_sizing: bool = Form(False),
    sizing_file: Optional[UploadFile] = File(default=None),
) -> Dict[str, Any]:
    schema_id_clean = git_schema_id.strip() or None

    if not name.strip() or not target_dir.strip():
        raise HTTPException(status_code=400, detail="name and target_dir are required")

    safe_name = name.strip().strip("/").strip("\\")
    effective_target_type = (target_type or "local").strip().lower()

    normalized_target_parent = _normalize_target_dir(target_dir)
    normalized_target_dir = str((Path(normalized_target_parent) / safe_name).resolve())

    remote_cfg: Optional[Dict[str, str]] = None
    registry_target_path: Optional[str] = None
    if effective_target_type == "local":
        Path(normalized_target_parent).mkdir(parents=True, exist_ok=True)
    if effective_target_type == "remote":
        host = remote_host.strip()
        user = remote_user.strip()
        port = (remote_port or "22").strip() or "22"
        auth_mode = (remote_auth_mode or "ssh_key").strip()
        if auth_mode != "ssh_key":
            raise HTTPException(status_code=400, detail="Only SSH key auth is currently supported for remote target")
        if not host or not user:
            raise HTTPException(status_code=400, detail="remote_host and remote_user are required for remote target")
        remote_base = _normalize_remote_base_dir(remote_base_dir)
        remote_project_dir = str(PurePosixPath(remote_base) / safe_name)
        remote_cfg = {
            "host": host,
            "user": user,
            "port": port,
            "auth_mode": auth_mode,
            "ssh_key_path": remote_ssh_key_path.strip(),
            "base_dir": remote_base,
            "project_dir": remote_project_dir,
        }
        registry_target_path = remote_project_dir

    effective_desc = _apply_forced_type(description, forced_type)
    sizing_context: Optional[Dict[str, Any]] = None
    detected_platform: Optional[str] = None
    sizing_preview: Dict[str, Any] = {
        "ok": True,
        "warnings": [],
        "fatal_error": None,
        "sizing_context_applied": False,
    }

    if sizing_file is not None:
        sizing_context, detected_platform, sizing_preview = await _parse_uploaded_sizing_file(sizing_file)

    description_platform = _infer_platform_from_text(description)
    platform_source: Optional[str] = None
    if platform == "proxmox":
        final_platform = "proxmox"
        platform_source = "user_selection"
    elif detected_platform:
        final_platform = detected_platform
        platform_source = "sizing_file"
    elif platform:
        final_platform = platform
        platform_source = "user_selection"
    elif description_platform:
        final_platform = description_platform
        platform_source = "description"
    else:
        final_platform = None
        platform_source = None

    sizing_preview = _enrich_sizing_preview(
        sizing_preview,
        selected_platform=final_platform or platform,
        description=description,
        enable_otel_collector=enable_otel_collector,
        use_terraform_iac=use_terraform_iac,
    )
    sizing_preview["addon_preview"] = _build_addon_preview(
        project_name=name,
        description=description,
        forced_type=forced_type,
        forced_chain=forced_chain,
        effective_platform=sizing_preview.get("effective_platform"),
        gitops_tool=final_gitops if 'final_gitops' in locals() else gitops_tool,
        use_terraform_iac=use_terraform_iac,
        enable_otel_collector=enable_otel_collector,
        sizing_context=sizing_context,
    )
    governance_preview = _build_governance_preview(
        license_id=license_id,
        confidentiality=confidentiality,
        header_mode=header_mode,
        copyright_owner=copyright_owner,
        organization=organization,
        policy_profile=policy_profile,
    )

    if sizing_preview.get("fatal_error") and not continue_without_sizing:
        raise HTTPException(
            status_code=422,
            detail={
                "message": sizing_preview["fatal_error"]["message"],
                "sizing_preview": sizing_preview,
            },
        )
    if sizing_preview.get("fatal_error") and continue_without_sizing:
        sizing_context = None
        detected_platform = None

    if not final_platform and sizing_context is None and not _has_infra_keywords(description):
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not determine target platform from the description. "
                "Please select a Platform (aks, openshift, rke2, proxmox) "
                "or upload a sizing file."
            ),
        )

    final_gitops = gitops_tool if gitops_tool else "flux"

    # Build local (final local path or staging path)
    temp_build_root: Optional[Path] = None
    if effective_target_type == "remote":
        temp_build_root = Path(tempfile.mkdtemp(prefix="pi-remote-build-"))
        local_build_dir = temp_build_root / safe_name
    else:
        local_build_dir = Path(normalized_target_dir)

    effective_remote_url = git_remote_url.strip()
    if git_push and effective_remote_url and not create_remote_repo and _looks_like_namespace_url(effective_remote_url):
        raise HTTPException(
            status_code=400,
            detail=(
                "git_remote_url points to a namespace/group URL, not a repository URL. "
                "Enable 'create_remote_repo' or provide full repo URL like "
                "https://gitlab.com/<group>/<repo>.git"
            ),
        )
    created_remote: Optional[Dict[str, Any]] = None
    if create_remote_repo:
        if not git_token.strip():
            raise HTTPException(status_code=400, detail="git_token is required when create_remote_repo is enabled")
        if not git_provider.strip() or not git_namespace.strip():
            raise HTTPException(status_code=400, detail="git_provider and git_namespace are required when create_remote_repo is enabled")
        effective_remote_url = _create_remote_repo(
            provider=git_provider,
            namespace=git_namespace,
            project_name=safe_name,
            token=git_token.strip(),
            private_repo=git_private_repo,
        )
        created_remote = {
            "created": True,
            "provider": git_provider.strip().lower(),
            "namespace": git_namespace.strip(),
            "url": effective_remote_url,
            "private": git_private_repo,
        }

    result = initialize_project(
        project_name=name,
        description=effective_desc,
        target_directory=str(local_build_dir),
        forced_chain=forced_chain or None,
        platform=final_platform or None,
        gitops_tool=final_gitops,
        iac_tool="terraform" if use_terraform_iac else "",
        repo_url=effective_remote_url or None,
        git_token=git_token.strip() or None,
        fallback_storage_class=fallback_storage_class.strip() or None,
        target_revision=(git_branch.strip() or "main"),
        sizing_context=sizing_context,
        enable_metrics_server=enable_metrics_server,
        enable_otel_collector=enable_otel_collector,
        license_policy=governance_preview["license_policy"],
        header_policy=governance_preview["header_policy"],
    )

    git_log: List[Dict[str, Any]] = []
    project_path = Path(result["project_path"]).resolve()

    git_env, askpass_path = _prepare_git_pat_env(effective_remote_url, git_token)
    try:
        if git_init:
            git_log.append(_run_git_command(["git", "init"], project_path, env=git_env))
            git_log.append(_run_git_command(["git", "add", "."], project_path, env=git_env))
            git_log.append(_run_git_command(["git", "commit", "-m", git_commit_message], project_path, env=git_env))

            if effective_remote_url:
                git_log.append(_run_git_command(["git", "remote", "remove", "origin"], project_path, env=git_env))
                git_log.append(_run_git_command(["git", "remote", "add", "origin", effective_remote_url], project_path, env=git_env))

            if git_push and effective_remote_url:
                git_log.append(_run_git_command(["git", "branch", "-M", git_branch], project_path, env=git_env))
                git_log.append(_run_git_command(["git", "push", "-u", "origin", git_branch], project_path, env=git_env))
    finally:
        if askpass_path is not None:
            askpass_path.unlink(missing_ok=True)

    remote_log: List[Dict[str, Any]] = []
    remote_result: Dict[str, Any] = {"enabled": effective_target_type == "remote", "ok": True, "log": []}
    if effective_target_type == "remote" and remote_cfg is not None:
        mkdir_cmd = f"mkdir -p '{remote_cfg['project_dir'].replace("'", "'\''")}'"
        remote_log.append(_run_ssh_command(remote_cfg["host"], remote_cfg["port"], remote_cfg["user"], mkdir_cmd, remote_cfg["ssh_key_path"]))
        if remote_log[-1]["ok"]:
            remote_log.append(_run_rsync_to_remote(project_path, remote_cfg["host"], remote_cfg["port"], remote_cfg["user"], remote_cfg["project_dir"], remote_cfg["ssh_key_path"]))
        remote_result = {
            "enabled": True,
            "ok": all(x.get("ok") for x in remote_log),
            "log": remote_log,
            "host": remote_cfg["host"],
            "user": remote_cfg["user"],
            "port": remote_cfg["port"],
            "ssh_key_path": remote_cfg.get("ssh_key_path", ""),
            "project_dir": remote_cfg["project_dir"],
            "base_dir": remote_cfg["base_dir"],
        }
        if not remote_result["ok"]:
            raise HTTPException(status_code=502, detail=f"Remote transfer failed: {remote_log[-1].get('stderr') or remote_log[-1].get('stdout') or 'unknown error'}")

    result["git"] = {
        "enabled": git_init,
        "remote": effective_remote_url,
        "branch": git_branch,
        "push": git_push,
        "log": git_log,
    }
    if created_remote is not None:
        result["git"]["remote_repo"] = created_remote
    result["effective_platform"] = final_platform
    result["detected_workload_platform"] = detected_platform
    result["platform_source"] = platform_source
    result["effective_gitops"] = final_gitops
    result["gitops_source"] = "user_selection" if gitops_tool else "default"
    result["iac_tool"] = "terraform" if use_terraform_iac else ""
    result["target_type"] = effective_target_type
    result["remote"] = remote_result
    result["sizing_preview"] = sizing_preview
    result["governance_preview"] = governance_preview
    generation_validation = _load_generation_validation_report(result)
    result["validation_report"] = {
        "ok": governance_preview["validation"]["ok"] and not sizing_preview.get("fatal_error") and generation_validation.get("ok", True),
        "items": list(governance_preview["validation"]["items"]) + [
            {"scope": "sizing", "code": item.get("code", "warning"), "severity": item.get("severity", "warning"), "message": item.get("message", "")}
            for item in (sizing_preview.get("warnings") or [])
        ] + list(generation_validation.get("items") or []),
        "generation": generation_validation,
    }
    result["sizing_parse_warnings"] = sizing_preview.get("warnings", [])
    result["sizing_parse_error"] = sizing_preview.get("fatal_error")
    result["sizing_context_applied"] = sizing_preview.get("sizing_context_applied", False)
    result["output_summary"] = _build_output_summary(result)

    if platform_source == "sizing_file" and platform and platform != final_platform:
        result["platform_override"] = {
            "user_selected": platform,
            "sizing_file_detected": final_platform,
            "message": (
                f"Platform changed from '{platform}' to '{final_platform}' "
                f"based on the uploaded sizing file."
            ),
        }

    if effective_target_type == "remote" and remote_cfg is not None:
        result["normalized_target_dir"] = remote_cfg["project_dir"]
        result["target_parent_dir"] = remote_cfg["base_dir"]
        result["project_path"] = remote_cfg["project_dir"]
        result["local_staging_path"] = str(project_path)
    else:
        result["normalized_target_dir"] = normalized_target_dir
        result["target_parent_dir"] = normalized_target_parent
        registry_target_path = normalized_target_dir

    if use_terraform_iac and run_terraform_apply and effective_target_type == "local":
        terraform_dir = project_path / "terraform"
        tf_log: List[Dict[str, Any]] = []
        if terraform_dir.exists() and terraform_dir.is_dir():
            tf_log.append(_run_shell_command(["terraform", "init", "-input=false"], terraform_dir))
            if tf_log[-1]["ok"]:
                tf_log.append(_run_shell_command(["terraform", "apply", "-auto-approve", "-input=false"], terraform_dir))
        else:
            tf_log.append({"ok": False, "command": "terraform", "stdout": "", "stderr": f"terraform directory not found: {terraform_dir}"})
        result["terraform"] = {"requested": True, "log": tf_log}
    elif use_terraform_iac and run_terraform_apply and effective_target_type == "remote":
        result["terraform"] = {"requested": True, "log": [], "note": "run_terraform_apply is local-only in this version; run terraform on remote host"}
    else:
        result["terraform"] = {"requested": False, "log": []}

    if git_init:
        GIT_REGISTRY.upsert_from_project(
            repo_path=registry_target_path,
            remote_url=effective_remote_url,
            branch=git_branch,
            platform=final_platform,
            schema_id=schema_id_clean,
            project_name=name,
        )
    elif schema_id_clean:
        GIT_REGISTRY.mark_used(schema_id_clean, platform=final_platform)

    DEPLOYMENT_HISTORY.add(
        {
            "name": safe_name,
            "description": description.strip(),
            "project_path": result.get("project_path", ""),
            "target_parent_dir": result.get("target_parent_dir", ""),
            "target_type": effective_target_type,
            "platform": final_platform or "",
            "gitops_tool": final_gitops,
            "iac_tool": "terraform" if use_terraform_iac else "",
            "git_remote_url": effective_remote_url,
            "git_branch": git_branch,
            "git_remote_repo": created_remote,
            "remote": remote_result if effective_target_type == "remote" else None,
            "license_id": governance_preview["license_policy"]["license_id"],
            "confidentiality": governance_preview["license_policy"]["confidentiality"],
            "header_mode": governance_preview["header_policy"]["mode"],
            "policy_profile": governance_preview.get("policy_profile", ""),
            "generation_manifest": result.get("generation_manifest", ""),
            "generation_validation_report": result.get("generation_validation_report", ""),
            "output_summary": result.get("output_summary", {}),
            "validation_report": result.get("validation_report", {}),
            "files_created": result.get("generated_files", result.get("files_created", [])),
        }
    )

    return result


async def _create_stream_generator(
    name: str,
    description: str,
    target_dir: str,
    forced_type: str,
    forced_chain: str,
    platform: str,
    gitops_tool: str,
    git_init: bool,
    git_commit_message: str,
    git_remote_url: str,
    git_branch: str,
    git_push: bool,
    git_token: str,
    git_provider: str,
    git_namespace: str,
    create_remote_repo: bool,
    git_private_repo: bool,
    git_schema_id: str,
    use_terraform_iac: bool,
    fallback_storage_class: str,
    run_terraform_apply: bool,
    enable_metrics_server: bool,
    enable_otel_collector: bool,
    target_type: str,
    remote_host: str,
    remote_port: str,
    remote_user: str,
    remote_auth_mode: str,
    remote_ssh_key_path: str,
    remote_base_dir: str,
    license_id: str,
    confidentiality: str,
    header_mode: str,
    copyright_owner: str,
    organization: str,
    policy_profile: str,
    continue_without_sizing: bool,
    sizing_bytes: Optional[bytes],
    sizing_filename: Optional[str],
):
    def _sse(step: str, message: str, **extra) -> str:
        return f"data: {json.dumps({'step': step, 'message': message, **extra})}\n\n"

    try:
        yield _sse("analyzing", "Analyzing project...")

        safe_name = name.strip().strip("/").strip("\\")
        effective_target_type = (target_type or "local").strip().lower()
        normalized_target_parent = _normalize_target_dir(target_dir)
        normalized_target_dir = str((Path(normalized_target_parent) / safe_name).resolve())

        remote_cfg: Optional[Dict[str, str]] = None
        registry_target_path: Optional[str] = None
        if effective_target_type == "local":
            Path(normalized_target_parent).mkdir(parents=True, exist_ok=True)
        if effective_target_type == "remote":
            host = remote_host.strip()
            user = remote_user.strip()
            port = (remote_port or "22").strip() or "22"
            auth_mode = (remote_auth_mode or "ssh_key").strip()
            if auth_mode != "ssh_key":
                yield _sse("error", "Only SSH key auth is currently supported for remote target")
                return
            if not host or not user:
                yield _sse("error", "remote_host and remote_user are required for remote target")
                return
            remote_base = _normalize_remote_base_dir(remote_base_dir)
            remote_project_dir = str(PurePosixPath(remote_base) / safe_name)
            remote_cfg = {
                "host": host,
                "user": user,
                "port": port,
                "auth_mode": auth_mode,
                "ssh_key_path": remote_ssh_key_path.strip(),
                "base_dir": remote_base,
                "project_dir": remote_project_dir,
            }
            registry_target_path = remote_project_dir

        effective_desc = _apply_forced_type(description, forced_type)
        sizing_context: Optional[Dict[str, Any]] = None
        detected_platform: Optional[str] = None
        sizing_preview: Dict[str, Any] = {
            "ok": True,
            "warnings": [],
            "fatal_error": None,
            "sizing_context_applied": False,
        }

        if sizing_bytes is not None and sizing_filename:
            suffix = ".json" if sizing_filename.lower().endswith(".json") else ".md"
            upload = UploadFile(filename=sizing_filename, file=tempfile.SpooledTemporaryFile())
            await upload.write(sizing_bytes)
            await upload.seek(0)
            sizing_context, detected_platform, sizing_preview = await _parse_uploaded_sizing_file(upload)
            await upload.close()

        description_platform = _infer_platform_from_text(description)
        platform_source: Optional[str] = None
        if platform == "proxmox":
            final_platform = "proxmox"
            platform_source = "user_selection"
        elif detected_platform:
            final_platform = detected_platform
            platform_source = "sizing_file"
        elif platform:
            final_platform = platform
            platform_source = "user_selection"
        elif description_platform:
            final_platform = description_platform
            platform_source = "description"
        else:
            final_platform = None
            platform_source = None

        sizing_preview = _enrich_sizing_preview(
            sizing_preview,
            selected_platform=final_platform or platform,
            description=description,
            enable_otel_collector=enable_otel_collector,
            use_terraform_iac=use_terraform_iac,
        )
        sizing_preview["addon_preview"] = _build_addon_preview(
            project_name=name,
            description=description,
            forced_type=forced_type,
            forced_chain=forced_chain,
            effective_platform=sizing_preview.get("effective_platform"),
            gitops_tool=gitops_tool,
            use_terraform_iac=use_terraform_iac,
            enable_otel_collector=enable_otel_collector,
            sizing_context=sizing_context,
        )
        governance_preview = _build_governance_preview(
            license_id=license_id,
            confidentiality=confidentiality,
            header_mode=header_mode,
            copyright_owner=copyright_owner,
            organization=organization,
            policy_profile=policy_profile,
        )
        if sizing_preview.get("warnings"):
            yield _sse("warning", "Sizing input parsed with warnings", warnings=sizing_preview["warnings"])
        if sizing_preview.get("caveats"):
            yield _sse("warning", "Platform caveats detected", caveats=sizing_preview["caveats"], sizing_preview=sizing_preview)
        addon_preview = sizing_preview.get("addon_preview") or {}
        if addon_preview.get("addons"):
            yield _sse("addons", "Addon plan computed", addon_preview=addon_preview)
        if governance_preview["validation"].get("items"):
            yield _sse("warning", "Governance validation detected", governance_preview=governance_preview)
        if sizing_preview.get("fatal_error") and not continue_without_sizing:
            yield _sse("error", sizing_preview["fatal_error"]["message"], sizing_preview=sizing_preview)
            return
        if sizing_preview.get("fatal_error") and continue_without_sizing:
            yield _sse("warning", "Sizing input was ignored due to parse error", sizing_preview=sizing_preview)
            sizing_context = None
            detected_platform = None

        final_gitops = gitops_tool if gitops_tool else "flux"

        temp_build_root: Optional[Path] = None
        if effective_target_type == "remote":
            temp_build_root = Path(tempfile.mkdtemp(prefix="pi-remote-build-"))
            local_build_dir = temp_build_root / safe_name
        else:
            local_build_dir = Path(normalized_target_dir)

        effective_remote_url = git_remote_url.strip()
        created_remote: Optional[Dict[str, Any]] = None
        if create_remote_repo:
            if not git_token.strip():
                yield _sse("error", "git_token is required when create_remote_repo is enabled")
                return
            effective_remote_url = _create_remote_repo(
                provider=git_provider,
                namespace=git_namespace,
                project_name=safe_name,
                token=git_token.strip(),
                private_repo=git_private_repo,
            )
            created_remote = {
                "created": True,
                "provider": git_provider.strip().lower(),
                "namespace": git_namespace.strip(),
                "url": effective_remote_url,
                "private": git_private_repo,
            }

        yield _sse("generating", "Generating project structure...")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: initialize_project(
            project_name=name,
            description=effective_desc,
            target_directory=str(local_build_dir),
            forced_chain=forced_chain or None,
            platform=final_platform or None,
            gitops_tool=final_gitops,
            iac_tool="terraform" if use_terraform_iac else "",
            repo_url=effective_remote_url or None,
            git_token=git_token.strip() or None,
            fallback_storage_class=fallback_storage_class.strip() or None,
            target_revision=(git_branch.strip() or "main"),
            sizing_context=sizing_context,
            enable_metrics_server=enable_metrics_server,
            enable_otel_collector=enable_otel_collector,
            license_policy=governance_preview["license_policy"],
            header_policy=governance_preview["header_policy"],
        ))

        addons_triggered = result.get("addons_triggered", [])
        yield _sse("addons", f"Addons matched: {len(addons_triggered)}", count=len(addons_triggered))

        yield _sse("git", "Running git operations...")

        git_log: List[Dict[str, Any]] = []
        project_path = Path(result["project_path"]).resolve()

        git_env, askpass_path = _prepare_git_pat_env(effective_remote_url, git_token)
        try:
            if git_init:
                git_log.append(_run_git_command(["git", "init"], project_path, env=git_env))
                git_log.append(_run_git_command(["git", "add", "."], project_path, env=git_env))
                git_log.append(_run_git_command(["git", "commit", "-m", git_commit_message], project_path, env=git_env))
                if effective_remote_url:
                    git_log.append(_run_git_command(["git", "remote", "remove", "origin"], project_path, env=git_env))
                    git_log.append(_run_git_command(["git", "remote", "add", "origin", effective_remote_url], project_path, env=git_env))
                if git_push and effective_remote_url:
                    git_log.append(_run_git_command(["git", "branch", "-M", git_branch], project_path, env=git_env))
                    git_log.append(_run_git_command(["git", "push", "-u", "origin", git_branch], project_path, env=git_env))
        finally:
            if askpass_path is not None:
                askpass_path.unlink(missing_ok=True)

        remote_result: Dict[str, Any] = {"enabled": effective_target_type == "remote", "ok": True, "log": []}
        remote_log: List[Dict[str, Any]] = []
        if effective_target_type == "remote" and remote_cfg is not None:
            mkdir_cmd = f"mkdir -p '{remote_cfg['project_dir'].replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'"
            remote_log.append(_run_ssh_command(remote_cfg["host"], remote_cfg["port"], remote_cfg["user"], mkdir_cmd, remote_cfg["ssh_key_path"]))
            if remote_log[-1]["ok"]:
                remote_log.append(_run_rsync_to_remote(project_path, remote_cfg["host"], remote_cfg["port"], remote_cfg["user"], remote_cfg["project_dir"], remote_cfg["ssh_key_path"]))
            remote_result = {
                "enabled": True,
                "ok": all(x.get("ok") for x in remote_log),
                "log": remote_log,
                "host": remote_cfg["host"],
                "user": remote_cfg["user"],
                "port": remote_cfg["port"],
                "ssh_key_path": remote_cfg.get("ssh_key_path", ""),
                "project_dir": remote_cfg["project_dir"],
                "base_dir": remote_cfg["base_dir"],
            }

        result["git"] = {
            "enabled": git_init,
            "remote": effective_remote_url,
            "branch": git_branch,
            "push": git_push,
            "log": git_log,
        }
        if created_remote is not None:
            result["git"]["remote_repo"] = created_remote
        result["effective_platform"] = final_platform
        result["platform_source"] = platform_source
        result["effective_gitops"] = final_gitops
        result["iac_tool"] = "terraform" if use_terraform_iac else ""
        result["target_type"] = effective_target_type
        result["remote"] = remote_result
        result["sizing_preview"] = sizing_preview
        result["governance_preview"] = governance_preview
        generation_validation = _load_generation_validation_report(result)
        result["validation_report"] = {
            "ok": governance_preview["validation"]["ok"] and not sizing_preview.get("fatal_error") and generation_validation.get("ok", True),
            "items": list(governance_preview["validation"]["items"]) + [
                {"scope": "sizing", "code": item.get("code", "warning"), "severity": item.get("severity", "warning"), "message": item.get("message", "")}
                for item in (sizing_preview.get("warnings") or [])
            ] + list(generation_validation.get("items") or []),
            "generation": generation_validation,
        }
        result["sizing_parse_warnings"] = sizing_preview.get("warnings", [])
        result["sizing_parse_error"] = sizing_preview.get("fatal_error")
        result["sizing_context_applied"] = sizing_preview.get("sizing_context_applied", False)
        result["output_summary"] = _build_output_summary(result)

        if effective_target_type == "remote" and remote_cfg is not None:
            result["normalized_target_dir"] = remote_cfg["project_dir"]
            result["target_parent_dir"] = remote_cfg["base_dir"]
            result["project_path"] = remote_cfg["project_dir"]
        else:
            result["normalized_target_dir"] = normalized_target_dir
            result["target_parent_dir"] = normalized_target_parent
            registry_target_path = normalized_target_dir

        schema_id_clean = git_schema_id.strip() or None
        if git_init:
            GIT_REGISTRY.upsert_from_project(
                repo_path=registry_target_path,
                remote_url=effective_remote_url,
                branch=git_branch,
                platform=final_platform,
                schema_id=schema_id_clean,
                project_name=name,
            )
        elif schema_id_clean:
            GIT_REGISTRY.mark_used(schema_id_clean, platform=final_platform)

        DEPLOYMENT_HISTORY.add({
            "name": safe_name,
            "description": description.strip(),
            "project_path": result.get("project_path", ""),
            "target_parent_dir": result.get("target_parent_dir", ""),
            "target_type": effective_target_type,
            "platform": final_platform or "",
            "gitops_tool": final_gitops,
            "iac_tool": "terraform" if use_terraform_iac else "",
            "git_remote_url": effective_remote_url,
            "git_branch": git_branch,
            "git_remote_repo": created_remote,
            "remote": remote_result if effective_target_type == "remote" else None,
            "license_id": governance_preview["license_policy"]["license_id"],
            "confidentiality": governance_preview["license_policy"]["confidentiality"],
            "header_mode": governance_preview["header_policy"]["mode"],
            "policy_profile": governance_preview.get("policy_profile", ""),
            "generation_manifest": result.get("generation_manifest", ""),
            "generation_validation_report": result.get("generation_validation_report", ""),
            "output_summary": result.get("output_summary", {}),
            "validation_report": result.get("validation_report", {}),
            "files_created": result.get("generated_files", result.get("files_created", [])),
        })

        AUDIT_LOG.append("scaffold", f"Created {safe_name} at {result.get('project_path', '')}")

        yield _sse(
            "done",
            "Project created successfully",
            project_path=result.get("project_path", ""),
            addons_triggered=addons_triggered,
            files_created=result.get("files_created", []),
            output_summary=result.get("output_summary", _build_output_summary(result)),
            platform=final_platform or "auto",
            name=safe_name,
            target_type=effective_target_type,
            remote=result.get("remote") if effective_target_type == "remote" else None,
            sizing_preview=sizing_preview,
            governance_preview=governance_preview,
            validation_report=result.get("validation_report", {}),
            sizing_parse_warnings=sizing_preview.get("warnings", []),
            sizing_parse_error=sizing_preview.get("fatal_error"),
            sizing_context_applied=sizing_preview.get("sizing_context_applied", False),
        )

    except Exception as exc:
        yield _sse("error", str(exc))


@app.post("/api/create/stream")
async def create_project_stream(
    name: str = Form(...),
    description: str = Form(""),
    target_dir: str = Form(...),
    forced_type: str = Form("auto"),
    forced_chain: str = Form(""),
    platform: str = Form(""),
    gitops_tool: str = Form(""),
    git_init: bool = Form(False),
    git_commit_message: str = Form("Initial commit: project scaffold"),
    git_remote_url: str = Form(""),
    git_branch: str = Form("main"),
    git_push: bool = Form(False),
    git_token: str = Form(""),
    git_provider: str = Form(""),
    git_namespace: str = Form(""),
    create_remote_repo: bool = Form(False),
    git_private_repo: bool = Form(True),
    git_schema_id: str = Form(""),
    use_terraform_iac: bool = Form(False),
    fallback_storage_class: str = Form(""),
    run_terraform_apply: bool = Form(False),
    enable_metrics_server: bool = Form(False),
    enable_otel_collector: bool = Form(False),
    target_type: str = Form("local"),
    remote_host: str = Form(""),
    remote_port: str = Form("22"),
    remote_user: str = Form(""),
    remote_auth_mode: str = Form("ssh_key"),
    remote_ssh_key_path: str = Form(""),
    remote_base_dir: str = Form(""),
    license_id: str = Form("UNLICENSED"),
    confidentiality: str = Form("internal"),
    header_mode: str = Form("none"),
    copyright_owner: str = Form(""),
    organization: str = Form(""),
    policy_profile: str = Form(""),
    continue_without_sizing: bool = Form(False),
    sizing_file: Optional[UploadFile] = File(default=None),
) -> StreamingResponse:
    sizing_bytes = await sizing_file.read() if sizing_file else None
    sizing_filename = sizing_file.filename if sizing_file else None

    return StreamingResponse(
        _create_stream_generator(
            name=name,
            description=description,
            target_dir=target_dir,
            forced_type=forced_type,
            forced_chain=forced_chain,
            platform=platform,
            gitops_tool=gitops_tool,
            git_init=git_init,
            git_commit_message=git_commit_message,
            git_remote_url=git_remote_url,
            git_branch=git_branch,
            git_push=git_push,
            git_token=git_token,
            git_provider=git_provider,
            git_namespace=git_namespace,
            create_remote_repo=create_remote_repo,
            git_private_repo=git_private_repo,
            git_schema_id=git_schema_id,
            use_terraform_iac=use_terraform_iac,
            fallback_storage_class=fallback_storage_class,
            run_terraform_apply=run_terraform_apply,
            enable_metrics_server=enable_metrics_server,
            enable_otel_collector=enable_otel_collector,
            target_type=target_type,
            remote_host=remote_host,
            remote_port=remote_port,
            remote_user=remote_user,
            remote_auth_mode=remote_auth_mode,
            remote_ssh_key_path=remote_ssh_key_path,
            remote_base_dir=remote_base_dir,
            license_id=license_id,
            confidentiality=confidentiality,
            header_mode=header_mode,
            copyright_owner=copyright_owner,
            organization=organization,
            policy_profile=policy_profile,
            continue_without_sizing=continue_without_sizing,
            sizing_bytes=sizing_bytes,
            sizing_filename=sizing_filename,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/git/discover")
def git_discover(base_path: str = "", limit: int = 25, max_depth: int = 4) -> Dict[str, Any]:
    base = _expand_input_path(base_path or str(USER_HOME / "Projects"))
    root = base.resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="base_path does not exist or is not a directory")
    safe_limit = max(1, min(limit, 200))
    max_depth = max(1, min(max_depth, 8))
    repositories: List[Dict[str, Any]] = []
    for current, dirs, _files in os.walk(root):
        current_path = Path(current).resolve()
        try:
            relative_depth = len(current_path.relative_to(root).parts)
        except ValueError:
            relative_depth = 0
        if relative_depth > max_depth:
            dirs[:] = []
            continue
        if ".git" in dirs:
            repositories.append(_git_repo_summary(current_path))
            dirs[:] = [d for d in dirs if d != ".git"]
            if len(repositories) >= safe_limit:
                break
    return {"base_path": str(root), "repositories": repositories}


@app.post("/api/git/inspect")
def git_inspect(repo_path: str = Form(...)) -> Dict[str, Any]:
    path = _expand_input_path(repo_path).resolve()
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail="repo_path does not exist")
    if not (path / ".git").exists():
        raise HTTPException(status_code=400, detail="repo_path is not a git repository")
    return {
        "path": str(path),
        "status": _run_git_command(["git", "status", "-sb"], path),
        "remotes": _run_git_command(["git", "remote", "-v"], path),
        "last_commit": _run_git_command(["git", "log", "-1", "--pretty=%h %s (%cr)"] , path),
    }


@app.get("/api/git/keys")
def git_keys() -> Dict[str, Any]:
    public_keys: List[Dict[str, str]] = []
    private_keys: List[Dict[str, str]] = []
    if SSH_DIR.exists() and SSH_DIR.is_dir():
        for item in SSH_DIR.iterdir():
            if not item.is_file():
                continue
            entry = {"name": item.name, "path": str(item)}
            if item.suffix == ".pub":
                public_keys.append(entry)
            else:
                private_keys.append(entry)
    return {"public_keys": public_keys, "private_keys": private_keys}


@app.post("/api/git/keys/read")
def git_key_read(path: str = Form(...)) -> Dict[str, Any]:
    target = _expand_input_path(path).resolve()
    if not _is_path_within(SSH_DIR, target):
        raise HTTPException(status_code=400, detail="Only keys under ~/.ssh can be read")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=400, detail="Key path does not exist")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Key is not readable text") from exc
    return {"path": str(target), "content": content.strip()}


@app.post("/api/git/token/test")
def git_token_test(
    git_token: str = Form(...),
    git_provider: str = Form(""),
    remote_url: str = Form(""),
    organization: str = Form(""),
) -> Dict[str, Any]:
    token = (git_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="git_token is required")
    provider = _detect_provider(git_provider, remote_url)
    if not provider:
        raise HTTPException(status_code=400, detail="git_provider is required (github/gitlab/azure_devops) when remote_url is not set")

    if provider == "gitlab":
        headers = {"PRIVATE-TOKEN": token, "Accept": "application/json", "User-Agent": "project-initializer"}
        me = _http_json_request("https://gitlab.com/api/v4/user", "GET", headers)
        return {"ok": True, "provider": "gitlab", "user": me.get("username") or me.get("name") or "", "scopes_hint": "Needs read_repository + write_repository (or api)."}

    if provider == "azure_devops":
        org = (organization or "").strip()
        if not org:
            # Try to extract org from remote URL: https://dev.azure.com/{org}/...
            url_lower = (remote_url or "").strip()
            if "dev.azure.com" in url_lower:
                parts = [p for p in urllib.parse.urlparse(url_lower).path.split("/") if p]
                if parts:
                    org = parts[0]
        if not org:
            raise HTTPException(status_code=400, detail="Organization is required for Azure DevOps token test")
        basic = base64.b64encode(f":{token}".encode("utf-8")).decode("ascii")
        headers = {"Authorization": f"Basic {basic}", "Accept": "application/json", "User-Agent": "project-initializer"}
        me = _http_json_request(f"https://dev.azure.com/{org}/_apis/connectionData?api-version=7.1", "GET", headers)
        user = ""
        auth_user = me.get("authenticatedUser") or {}
        user = auth_user.get("providerDisplayName") or auth_user.get("customDisplayName") or ""
        return {"ok": True, "provider": "azure_devops", "user": user, "scopes_hint": "Needs Code (Read & Write) scope."}

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "project-initializer"}
    me = _http_json_request("https://api.github.com/user", "GET", headers)
    return {"ok": True, "provider": "github", "user": me.get("login") or me.get("name") or "", "scopes_hint": "Needs repo scope for private repositories."}


@app.get("/api/git/registry")
def git_registry_list() -> Dict[str, Any]:
    return {"entries": GIT_REGISTRY.list()}


@app.post("/api/git/registry")
def git_registry_create(
    name: str = Form(...),
    repo_path: str = Form(...),
    remote_url: str = Form(""),
    branch: str = Form("main"),
    platform: str = Form(""),
    description: str = Form(""),
) -> Dict[str, Any]:
    entry = GIT_REGISTRY.add(name, repo_path, remote_url, branch, platform, description)
    return entry


@app.patch("/api/git/registry/{entry_id}")
def git_registry_update(
    entry_id: str,
    name: str = Form(""),
    repo_path: str = Form(""),
    remote_url: str = Form(""),
    branch: str = Form(""),
    platform: str = Form(""),
    description: str = Form(""),
) -> Dict[str, Any]:
    payload = {
        "name": name.strip() or None,
        "repo_path": repo_path.strip() or None,
        "remote_url": remote_url.strip() or None,
        "branch": (branch or "").strip() or None,
        "platform": platform.strip() or None,
        "description": description.strip() or None,
    }
    cleaned = {k: v for k, v in payload.items() if v is not None}
    if not cleaned:
        raise HTTPException(status_code=400, detail="No updates supplied")
    entry = GIT_REGISTRY.update(entry_id, cleaned)
    return entry


@app.delete("/api/git/registry/{entry_id}")
def git_registry_delete(entry_id: str) -> Dict[str, Any]:
    GIT_REGISTRY.delete(entry_id)
    return {"ok": True}


@app.get("/api/deployments")
def deployment_history_list() -> Dict[str, Any]:
    return {"entries": DEPLOYMENT_HISTORY.list()}


@app.delete("/api/deployments/{entry_id}")
def deployment_history_delete(
    entry_id: str,
    payload: Optional[Dict[str, Any]] = Body(default=None),
) -> Dict[str, Any]:
    payload = payload or {}
    entry = next((item for item in DEPLOYMENT_HISTORY.list() if item.get("id") == entry_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="deployment history entry not found")

    delete_remote_repo = bool(payload.get("delete_remote_repo"))
    remote_delete_result: Optional[Dict[str, Any]] = None

    if delete_remote_repo:
        remote_delete_result = _delete_remote_repo_for_deployment(
            entry=entry,
            git_token=str(payload.get("git_token") or ""),
            confirm_text=str(payload.get("confirm_text") or ""),
        )

    DEPLOYMENT_HISTORY.delete(entry_id)
    if delete_remote_repo and remote_delete_result:
        AUDIT_LOG.append(
            "deployment-delete",
            f"Deleted deployment {entry.get('name', entry_id)} and remote repository {remote_delete_result.get('repository', '')}",
        )
    else:
        AUDIT_LOG.append("deployment-delete", f"Deleted deployment {entry.get('name', entry_id)}")

    return {
        "ok": True,
        "remote_repo_deleted": bool(remote_delete_result and remote_delete_result.get("ok")),
        "remote_repo": remote_delete_result,
    }


def _safe_json_load(text: str) -> Dict[str, Any]:
    try:
        data = json.loads(text or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _pod_ready_value(pod: Dict[str, Any]) -> str:
    statuses = pod.get("status", {}).get("containerStatuses") or []
    if not isinstance(statuses, list) or not statuses:
        return "0/0"
    ready = sum(1 for item in statuses if isinstance(item, dict) and item.get("ready"))
    return f"{ready}/{len(statuses)}"


def _pod_rows(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for pod in items:
        meta = pod.get("metadata") or {}
        spec = pod.get("spec") or {}
        status = pod.get("status") or {}
        rows.append({
            "name": str(meta.get("name") or ""),
            "ready": _pod_ready_value(pod),
            "status": str(status.get("phase") or "Unknown"),
            "node": str(spec.get("nodeName") or ""),
        })
    return rows


def _ingress_rows(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in data.get("items") or []:
        meta = item.get("metadata") or {}
        spec = item.get("spec") or {}
        status = item.get("status") or {}
        host = ""
        rules = spec.get("rules") or []
        if isinstance(rules, list) and rules:
            host = str((rules[0] or {}).get("host") or "")
        lb = status.get("loadBalancer") or {}
        ingress = lb.get("ingress") or []
        addr = ""
        if isinstance(ingress, list) and ingress:
            first = ingress[0] or {}
            addr = str(first.get("ip") or first.get("hostname") or "")
        rows.append({"name": str(meta.get("name") or ""), "host": host, "address": addr})
    return rows


def _route_rows(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in data.get("items") or []:
        meta = item.get("metadata") or {}
        spec = item.get("spec") or {}
        status = item.get("status") or {}
        host = str(spec.get("host") or "")
        address = ""
        ingress = status.get("ingress") or []
        if isinstance(ingress, list) and ingress:
            first = ingress[0] or {}
            address = str(first.get("routerCanonicalHostname") or first.get("host") or "")
        rows.append({"name": str(meta.get("name") or ""), "host": host, "address": address})
    return rows


@app.get("/api/flux-status")
def flux_status(deployment_id: str, kubeconfig: str = "") -> Dict[str, Any]:
    entries = DEPLOYMENT_HISTORY.list()
    entry = next((e for e in entries if e.get("id") == deployment_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="deployment not found")

    target_type = (entry.get("target_type") or "local").strip()
    project_name = entry.get("name", "")
    ks_names = _derive_kustomization_names_for_entry(entry)
    polled_at = _utcnow()
    kustomizations = []

    jsonpath = (
        "{.status.conditions[?(@.type=='Ready')].status}"
        "|{.status.conditions[?(@.type=='Ready')].reason}"
        "|{.status.conditions[?(@.type=='Ready')].message}"
    )

    pods_json: Dict[str, Any] = {}
    ingress_json: Dict[str, Any] = {}
    route_json: Dict[str, Any] = {}

    if target_type == "remote":
        remote_cfg = entry.get("remote") or {}
        host = remote_cfg.get("host", "")
        port = str(remote_cfg.get("port", "22"))
        user = remote_cfg.get("user", "")
        ssh_key_path = remote_cfg.get("ssh_key_path", "")
        for ks in ks_names:
            cmd = _remote_kubectl_command(
                entry,
                f"kubectl get kustomization {ks} -n flux-system -o jsonpath='{jsonpath}' 2>/dev/null || echo 'Unknown||'"
            )
            r = _run_ssh_command(host, port, user, cmd, ssh_key_path)
            ready, reason, message = _parse_ks_kubectl_output(r.get("stdout", ""))
            kustomizations.append({"name": ks, "namespace": "flux-system",
                                   "ready": ready, "reason": reason,
                                   "message": message, "polled_at": polled_at})
        es_cmd = _remote_kubectl_command(
            entry,
            f"kubectl get statefulset -n {project_name} -o jsonpath='{{.items[*].status.readyReplicas}}/{{.items[*].status.replicas}}' 2>/dev/null || echo '0/0'"
        )
        es_r = _run_ssh_command(host, port, user, es_cmd, ssh_key_path)
        pods_r = _run_ssh_command(host, port, user, _remote_kubectl_command(entry, f"kubectl get pods -n {project_name} -o json 2>/dev/null || echo '{{}}'"), ssh_key_path)
        ingress_r = _run_ssh_command(host, port, user, _remote_kubectl_command(entry, f"kubectl get ingress -n {project_name} -o json 2>/dev/null || echo '{{}}'"), ssh_key_path)
        route_r = _run_ssh_command(host, port, user, _remote_kubectl_command(entry, f"kubectl get route -n {project_name} -o json 2>/dev/null || echo '{{}}'"), ssh_key_path)
        pods_json = _safe_json_load(pods_r.get("stdout", ""))
        ingress_json = _safe_json_load(ingress_r.get("stdout", ""))
        route_json = _safe_json_load(route_r.get("stdout", ""))
    else:
        kube_env = os.environ.copy()
        if kubeconfig.strip():
            kube_env["KUBECONFIG"] = str(Path(kubeconfig).expanduser())
        for ks in ks_names:
            r = _run_shell_command(
                ["kubectl", "get", "kustomization", ks, "-n", "flux-system",
                 "-o", f"jsonpath={jsonpath}"],
                Path.cwd(), env=kube_env
            )
            ready, reason, message = _parse_ks_kubectl_output(r.get("stdout", ""))
            kustomizations.append({"name": ks, "namespace": "flux-system",
                                   "ready": ready, "reason": reason,
                                   "message": message, "polled_at": polled_at})
        es_r = _run_shell_command(
            ["kubectl", "get", "statefulset", "-n", project_name,
             "-o", "jsonpath={.items[*].status.readyReplicas}/{.items[*].status.replicas}"],
            Path.cwd(), env=kube_env
        )
        pods_r = _run_shell_command(["kubectl", "get", "pods", "-n", project_name, "-o", "json"], Path.cwd(), env=kube_env)
        ingress_r = _run_shell_command(["kubectl", "get", "ingress", "-n", project_name, "-o", "json"], Path.cwd(), env=kube_env)
        route_r = _run_shell_command(["kubectl", "get", "route", "-n", project_name, "-o", "json"], Path.cwd(), env=kube_env)
        pods_json = _safe_json_load(pods_r.get("stdout", ""))
        ingress_json = _safe_json_load(ingress_r.get("stdout", ""))
        route_json = _safe_json_load(route_r.get("stdout", ""))

    es_stdout = (es_r.get("stdout") or "0/0")
    es_parts = es_stdout.split("/", 1)
    es_pods = {
        "running": es_parts[0].strip() if len(es_parts) > 0 else "0",
        "total": es_parts[1].strip() if len(es_parts) > 1 else "0",
    }

    kustomization_summary = _summarize_kustomizations(kustomizations)
    cluster_status = "unknown"
    if kustomization_summary["overall"] == "failed":
        cluster_status = "degraded"
    elif kustomization_summary["overall"] == "reconciling":
        cluster_status = "reconciling"
    elif kustomization_summary["overall"] == "ready" and es_pods.get("total") not in {"", "0"} and es_pods.get("running") == es_pods.get("total"):
        cluster_status = "ready"
    elif kustomization_summary["overall"] == "ready":
        cluster_status = "partially_ready"

    pod_items = pods_json.get("items") if isinstance(pods_json, dict) else []
    pod_items = pod_items if isinstance(pod_items, list) else []

    def _name(item: Dict[str, Any]) -> str:
        return str((item.get("metadata") or {}).get("name") or "")

    def _labels(item: Dict[str, Any]) -> Dict[str, Any]:
        labels = (item.get("metadata") or {}).get("labels") or {}
        return labels if isinstance(labels, dict) else {}

    def _agent_name(item: Dict[str, Any]) -> str:
        labels = _labels(item)
        return str(labels.get("agent.k8s.elastic.co/name") or "")

    es_items = [item for item in pod_items if _name(item).startswith(f"{project_name}-es-")]
    fleet_items = [
        item for item in pod_items
        if "fleet-server" in _name(item) or "fleet-server" in _agent_name(item)
    ]
    agent_items = [
        item for item in pod_items
        if _agent_name(item)
        and "fleet-server" not in _agent_name(item)
        and "fleet-server" not in _name(item)
    ]

    status_details = {
        "elasticsearch_pods": _pod_rows(es_items),
        "fleet_server_pods": _pod_rows(fleet_items),
        "agent_pods": _pod_rows(agent_items),
        "ingress": _ingress_rows(ingress_json),
        "routes": _route_rows(route_json),
    }

    access_summary = _build_flux_access_summary(entry, kubeconfig)
    AUDIT_LOG.append("flux-poll", f"Polled {deployment_id}")
    return {"deployment_id": deployment_id, "kustomizations": kustomizations,
            "kustomization_summary": kustomization_summary,
            "cluster_summary": {"status": cluster_status, "es_pods": es_pods},
            "access_summary": access_summary,
            "es_pods": es_pods, "status_details": status_details, "polled_at": polled_at}


def _resolve_runbook_docs(entry: Dict[str, Any], docs: List[str]) -> List[Dict[str, Any]]:
    resolved_docs = []
    for relative_path in docs or []:
        exists, resolved_path = _project_file_exists(entry, relative_path)
        resolved_docs.append({
            "path": relative_path,
            "exists": exists,
            "resolved_path": resolved_path,
        })
    return resolved_docs


def _suggested_step_command(entry: Dict[str, Any], script: Dict[str, Any]) -> str:
    path = str(script.get("path") or "").strip()
    if not path:
        return ""
    target_type = (entry.get("target_type") or "local").strip() or "local"
    if target_type == "remote":
        remote_cfg = entry.get("remote") or {}
        host = remote_cfg.get("host", "remote-host")
        user = remote_cfg.get("user", "user")
        port = str(remote_cfg.get("port", "22"))
        project_dir = remote_cfg.get("project_dir", "<project_dir>")
        return f"ssh -p {port} {user}@{host} 'cd {project_dir} && bash {path}'"
    return f"cd {entry.get('project_path', '<project_path>')} && bash {path}"


def _step_remediation_guidance(platform: str, step_key: str, *, blocked_by: List[str], script_ready: bool, last_run_ok: Optional[bool]) -> List[str]:
    guidance: List[str] = []
    if blocked_by:
        guidance.append(f"Finish earlier runbook steps first: {', '.join(blocked_by)}.")
    if not script_ready:
        guidance.append("Resolve missing script prerequisites before running this step.")
    platform = (platform or "generic").strip().lower()
    step_hints = {
        "preflight-check": {
            "default": "Review generated docs and confirm host tooling, kubeconfig, and remote linkage.",
            "openshift": "Confirm oc login and route prerequisites before continuing.",
            "aks": "Confirm Azure auth, Terraform variables, and ingress prerequisites.",
            "proxmox": "Confirm Proxmox access, Terraform variables, and RKE2 bootstrap connectivity.",
            "rke2": "Confirm RKE2 bootstrap access and kubeconfig availability before proceeding.",
        },
        "validate-config": {
            "default": "Run validation until YAML/Terraform issues are cleared.",
        },
        "post-terraform-deploy": {
            "default": "Apply infrastructure first, then rerun this helper with the correct tfvars and kubeconfig context.",
        },
        "cluster-healthcheck": {
            "default": "Verify cluster context and Kibana exposure before retrying health checks.",
            "openshift": "Check Route exposure and oc-authenticated cluster access before retrying.",
        },
        "verify-deployment": {
            "default": "Inspect workload rollout state and reconcile errors before retrying verification.",
        },
        "import-dashboards": {
            "default": "Wait for Kibana readiness and confirm endpoint reachability before importing dashboards.",
        },
        "mirror-secrets": {
            "default": "Confirm namespace targets and secret source values before mirroring.",
        },
        "rollback": {
            "default": "Use rollback only after capturing failure evidence and validating rollback scope.",
        },
    }
    hints = step_hints.get(step_key, {})
    platform_hint = hints.get(platform) or hints.get("default")
    if platform_hint:
        guidance.append(platform_hint)
    if last_run_ok is False:
        guidance.append("Inspect the last failed run output before retrying this step.")
    return guidance


def _build_runbook_progress(entry: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    scripts = summary.get("scripts") or []
    manifest = summary.get("operations_manifest") or {}
    recent_runs = summary.get("recent_runs") or []
    successful_keys = []
    latest_run_by_key: Dict[str, Dict[str, Any]] = {}
    for record in recent_runs:
        key = record.get("script_key")
        if key and key not in latest_run_by_key:
            latest_run_by_key[key] = record
        if record.get("ok") and key and key not in successful_keys:
            successful_keys.append(key)
    successful_set = set(successful_keys)
    runbook = ((manifest.get("runbooks") or [{}])[:1] or [{}])[0]
    platform = runbook.get("platform") or (entry.get("platform") or "generic")
    steps = []
    next_step = None
    previous_incomplete = []
    script_map = {item.get("key"): item for item in scripts}
    for raw_step in runbook.get("steps") or []:
        key = raw_step.get("key")
        script = script_map.get(key, {})
        completed = key in successful_set
        blocked_by = [item for item in previous_incomplete if item]
        status = "completed" if completed else ("pending" if blocked_by else "ready")
        last_run = latest_run_by_key.get(key)
        prerequisite_checks = list(script.get("prerequisite_checks") or [])
        step = {
            **raw_step,
            "status": status,
            "completed": completed,
            "blocked_by": blocked_by,
            "script_ready": bool(script.get("ready", False)),
            "script_exists": bool(script.get("exists", False)),
            "prerequisite_checks": prerequisite_checks,
            "failed_prerequisites": [item for item in prerequisite_checks if not item.get("ok")],
            "docs_resolved": _resolve_runbook_docs(entry, list(raw_step.get("docs") or [])),
            "suggested_command": _suggested_step_command(entry, script),
            "last_run": last_run or {},
        }
        step["remediation"] = _step_remediation_guidance(
            str(platform),
            str(key or ""),
            blocked_by=blocked_by,
            script_ready=bool(step.get("script_ready")),
            last_run_ok=last_run.get("ok") if isinstance(last_run, dict) else None,
        )
        steps.append(step)
        if not completed and next_step is None:
            next_step = step
        if not completed:
            previous_incomplete.append(key)
    guidance = []
    next_command = ""
    if next_step:
        guidance.append(f"Next recommended action: {next_step.get('title') or next_step.get('key')}")
        if next_step.get("blocked_by"):
            guidance.append(f"Complete earlier steps first: {', '.join(next_step['blocked_by'])}")
        elif not next_step.get("script_ready"):
            guidance.append(f"Resolve script readiness before running {next_step.get('key')}")
        next_command = str(next_step.get("suggested_command") or "")
        if next_command:
            guidance.append(f"Suggested command: {next_command}")
    else:
        guidance.append("All recommended runbook steps have successful executions recorded.")
    if recent_runs:
        last = recent_runs[0]
        if last.get("ok"):
            guidance.append(f"Last successful action: {last.get('script_key')}")
        else:
            guidance.append(f"Last action failed: {last.get('script_key')}; inspect logs before continuing.")
    return {
        "platform": platform,
        "note": runbook.get("note", ""),
        "steps": steps,
        "completed_keys": successful_keys,
        "next_recommended": next_step,
        "next_command": next_command,
        "guidance": guidance,
    }


def _classify_execution_failure(target_type: str, stderr: str, stdout: str = "") -> str:
    text = f"{stderr}\n{stdout}".lower()
    if target_type == "remote":
        if any(token in text for token in ["permission denied", "connection refused", "no route to host", "could not resolve hostname", "operation timed out", "ssh:"]):
            return "connectivity"
        if any(token in text for token in ["unauthorized", "forbidden", "you must be logged in", "context deadline exceeded", "kubeconfig", "oc whoami"]):
            return "auth"
        if any(token in text for token in ["command not found", "not found in path", "missing"]):
            return "missing_tools"
    else:
        if any(token in text for token in ["command not found", "not found in path", "missing"]):
            return "missing_tools"
        if any(token in text for token in ["unauthorized", "forbidden", "you must be logged in", "kubeconfig"]):
            return "auth"
    return "script_failure"


def _remote_execution_context(entry: Dict[str, Any]) -> Dict[str, Any]:
    project_root, remote_cfg = _project_root_from_entry(entry)
    if not remote_cfg:
        return {}
    return {
        "host": remote_cfg.get("host", ""),
        "port": str(remote_cfg.get("port", "22")),
        "user": remote_cfg.get("user", ""),
        "project_dir": project_root,
        "ssh_key_path": remote_cfg.get("ssh_key_path", ""),
    }


def _build_history_timeline(entry: Dict[str, Any], recent_runs: List[Dict[str, Any]], scripts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    script_map = {item.get("key"): item for item in scripts}
    timeline: List[Dict[str, Any]] = []
    remote_context = _remote_execution_context(entry)
    for record in recent_runs:
        key = str(record.get("script_key") or "")
        script = script_map.get(key, {})
        kind = str(record.get("kind") or ("validation" if key == "project-validate" else "script"))
        ok = bool(record.get("ok"))
        target_type = str(record.get("target_type") or (entry.get("target_type") or "local"))
        stderr = str(record.get("stderr") or "")
        stdout = str(record.get("stdout") or "")
        timeline.append({
            "created_at": record.get("created_at", ""),
            "kind": kind,
            "script_key": key,
            "title": record.get("title") or script.get("title") or ("Project Validation" if kind == "validation" else key),
            "ok": ok,
            "status": "ok" if ok else "failed",
            "failure_classification": "" if ok else _classify_execution_failure(target_type, stderr, stdout),
            "safe": True if kind == "validation" else bool(script.get("safe", True)),
            "target_type": target_type,
            "remote_context": remote_context if target_type == "remote" else {},
            "out_of_order": bool(record.get("out_of_order")),
            "summary": record.get("summary") or (stderr or stdout),
            "stdout": stdout,
            "stderr": stderr,
            "script_arguments": record.get("script_arguments", {}),
            "confirmation_required": bool(record.get("confirmation_required", False)),
        })
    return timeline


def _project_operations_summary(entry: Dict[str, Any]) -> Dict[str, Any]:
    project_root, remote_cfg = _project_root_from_entry(entry)
    diagnostics = _collect_project_diagnostics(entry)
    scripts = _operation_scripts_for_entry(entry, diagnostics=diagnostics)
    artifacts = []
    for relative_path in [
        "project-initializer-manifest.json",
        "project-initializer-operations.json",
        "project-initializer-validation-report.json",
        "LICENSE",
        "NOTICE",
        "GENERATED_BY.md",
        "README.md",
    ]:
        exists, resolved = _project_file_exists(entry, relative_path)
        artifacts.append({"path": relative_path, "exists": exists, "resolved_path": resolved})
    recent_runs = OPERATION_RUN_HISTORY.list(entry.get("id"))[:20]
    summary = {
        "deployment": entry,
        "project_root": project_root,
        "target_type": (entry.get("target_type") or "local").strip() or "local",
        "remote": remote_cfg,
        "artifacts": artifacts,
        "operations_manifest": _operations_manifest_for_entry(entry),
        "scripts": scripts,
        "output_summary": entry.get("output_summary", {}),
        "validation_report": entry.get("validation_report", {}),
        "environment_diagnostics": diagnostics,
        "recent_runs": recent_runs,
    }
    summary["runbook_progress"] = _build_runbook_progress(entry, summary)
    summary["history_timeline"] = _build_history_timeline(entry, recent_runs, scripts)
    return summary


def _run_project_validation(entry: Dict[str, Any]) -> Dict[str, Any]:
    summary = _project_operations_summary(entry)
    items: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []
    target_type = summary["target_type"]
    project_root = summary["project_root"]
    remote_cfg = summary.get("remote") or {}
    platform = (entry.get("platform") or summary.get("operations_manifest", {}).get("project", {}).get("platform") or "").strip().lower()

    def add_item(scope: str, code: str, severity: str, message: str) -> None:
        classification = _classification_from_severity(severity)
        items.append({
            "scope": scope,
            "code": code,
            "severity": severity,
            "classification": classification,
            "message": message,
        })

    for artifact in summary["artifacts"]:
        add_item(
            "artifacts",
            "artifact_present" if artifact["exists"] else "artifact_missing",
            "info" if artifact["exists"] else "warning",
            f"{artifact['path']}: {'present' if artifact['exists'] else 'missing'}",
        )

    for script in summary["scripts"]:
        for check in script.get("prerequisite_checks") or []:
            add_item(
                "prerequisites",
                "prerequisite_ok" if check.get("ok") else "prerequisite_missing",
                "info" if check.get("ok") else "warning",
                f"{script['key']}: {check.get('name')} — {check.get('detail')}",
            )
        if not script.get("exists"):
            continue
        if target_type == "remote":
            cmd = f"bash -n {shlex.quote(script['resolved_path'])}"
            log = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), cmd, remote_cfg.get("ssh_key_path", ""))
        else:
            log = _run_shell_command(["bash", "-n", script["resolved_path"]], Path(project_root))
        logs.append({"check": f"shell:{script['key']}", **log})
        add_item(
            "scripts",
            "script_syntax_ok" if log.get("ok") else "script_syntax_failed",
            "info" if log.get("ok") else "error",
            f"Shell syntax {'passed' if log.get('ok') else 'failed'} for {script['path']}",
        )

    terraform_exists, terraform_resolved = _project_file_exists(entry, "terraform/main.tf")
    if terraform_exists:
        terraform_dir = terraform_resolved.rsplit('/main.tf', 1)[0] if target_type == 'remote' else str(Path(terraform_resolved).parent)
        if target_type == "remote":
            validate_cmd = f"command -v terraform >/dev/null 2>&1 && cd {shlex.quote(terraform_dir)} && terraform validate"
            log = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), validate_cmd, remote_cfg.get("ssh_key_path", ""))
            skipped = False
            fmt_cmd = f"command -v terraform >/dev/null 2>&1 && cd {shlex.quote(terraform_dir)} && terraform fmt -check -recursive"
            fmt_log = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), fmt_cmd, remote_cfg.get("ssh_key_path", ""))
            fmt_skipped = False
        elif shutil.which("terraform") is None:
            log = {"ok": True, "command": "terraform validate", "stdout": "", "stderr": "terraform not installed locally; skipped"}
            fmt_log = {"ok": True, "command": "terraform fmt -check -recursive", "stdout": "", "stderr": "terraform not installed locally; skipped"}
            skipped = True
            fmt_skipped = True
        else:
            log = _run_shell_command(["terraform", "validate"], Path(terraform_resolved).parent)
            fmt_log = _run_shell_command(["terraform", "fmt", "-check", "-recursive"], Path(terraform_resolved).parent)
            skipped = False
            fmt_skipped = False
        logs.append({"check": "terraform_validate", **log})
        add_item(
            "terraform",
            "terraform_validate_skipped" if skipped else ("terraform_validate_ok" if log.get("ok") else "terraform_validate_failed"),
            "info" if skipped or log.get("ok") else "warning",
            log.get("stderr") or ("terraform validate passed" if log.get("ok") else "terraform validate failed"),
        )
        logs.append({"check": "terraform_fmt_check", **fmt_log})
        add_item(
            "terraform",
            "terraform_fmt_skipped" if fmt_skipped else ("terraform_fmt_ok" if fmt_log.get("ok") else "terraform_fmt_failed"),
            "info" if fmt_skipped or fmt_log.get("ok") else "warning",
            fmt_log.get("stderr") or ("terraform fmt -check passed" if fmt_log.get("ok") else "terraform fmt -check failed"),
        )

    yaml_targets = [
        item for item in (summary.get("artifacts") or []) if item.get("path", "").endswith((".yaml", ".yml"))
    ]
    yaml_scan_paths = ["elasticsearch", "kibana", "agents", "platform", "infrastructure", "observability", "base", "overlays", "clusters", "flux-system"]
    if yaml is None:
        add_item("yaml", "yaml_validation_skipped", "warning", "PyYAML is not available; YAML parsing skipped")
    else:
        def validate_yaml_text(text: str, rel_path: str) -> None:
            try:
                list(yaml.safe_load_all(text))
                add_item("yaml", "yaml_parse_ok", "info", f"YAML parse passed for {rel_path}")
            except Exception as exc:
                add_item("yaml", "yaml_parse_failed", "error", f"YAML parse failed for {rel_path}: {exc}")
        if target_type == "remote":
            for rel in yaml_scan_paths:
                full = str(PurePosixPath(project_root) / rel)
                cmd = f"if [ -d {shlex.quote(full)} ]; then find {shlex.quote(full)} -type f \\( -name '*.yaml' -o -name '*.yml' \\) -print; fi"
                result = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), cmd, remote_cfg.get("ssh_key_path", ""))
                for candidate in [line.strip() for line in (result.get("stdout", "") or "").splitlines() if line.strip()]:
                    cat = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), f"cat {shlex.quote(candidate)}", remote_cfg.get("ssh_key_path", ""))
                    logs.append({"check": f"yaml:{candidate}", **cat})
                    validate_yaml_text(cat.get("stdout", "") or "", candidate.replace(f"{project_root}/", ""))
        else:
            root_path = Path(project_root)
            for rel in yaml_scan_paths:
                base = root_path / rel
                if not base.exists():
                    continue
                for candidate in base.rglob("*.y*ml"):
                    text = candidate.read_text(encoding="utf-8")
                    validate_yaml_text(text, str(candidate.relative_to(root_path)))

    kustomization_targets = []
    if target_type == "remote":
        for rel in ["base", "overlays/dev", "overlays/staging", "overlays/production", "platform/eck-operator", "elasticsearch", "kibana", "agents", "observability"]:
            kustomize_file = str(PurePosixPath(project_root) / rel / "kustomization.yaml")
            exists_cmd = f"test -f {shlex.quote(kustomize_file)} && echo present || echo missing"
            probe = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), exists_cmd, remote_cfg.get("ssh_key_path", ""))
            if probe.get("stdout", "").strip() == "present":
                kustomization_targets.append(rel)
    else:
        root_path = Path(project_root)
        for candidate in root_path.rglob("kustomization.yaml"):
            kustomization_targets.append(str(candidate.parent.relative_to(root_path)))

    kustomize_bin = "kubectl kustomize" if target_type == "remote" else ("kustomize" if shutil.which("kustomize") else ("kubectl" if shutil.which("kubectl") else ""))
    if not kustomize_bin:
        add_item("kustomize", "kustomize_skipped", "warning", "Neither kustomize nor kubectl is available; kustomize build checks skipped")
    else:
        seen = set()
        for rel in kustomization_targets:
            if rel in seen:
                continue
            seen.add(rel)
            if target_type == "remote":
                cmd = f"command -v kubectl >/dev/null 2>&1 && cd {shlex.quote(str(PurePosixPath(project_root) / rel))} && kubectl kustomize . >/dev/null"
                log = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), cmd, remote_cfg.get("ssh_key_path", ""))
            else:
                cwd = Path(project_root) / rel
                if shutil.which("kustomize"):
                    log = _run_shell_command(["kustomize", "build", "."], cwd)
                else:
                    log = _run_shell_command(["kubectl", "kustomize", "."], cwd)
            logs.append({"check": f"kustomize:{rel}", **log})
            add_item("kustomize", "kustomize_build_ok" if log.get("ok") else "kustomize_build_failed", "info" if log.get("ok") else "warning", f"Kustomize build {'passed' if log.get('ok') else 'failed'} for {rel}")

    if platform in {"rke2", "proxmox"}:
        cluster_cfg_exists, _ = _project_file_exists(entry, "platform/rke2/cluster-config.yaml")
        add_item("platform", "rke2_cluster_config_present" if cluster_cfg_exists else "rke2_cluster_config_missing", "info" if cluster_cfg_exists else "warning", f"RKE2 cluster config {'present' if cluster_cfg_exists else 'missing'}")
        bootstrap_exists, _ = _project_file_exists(entry, "scripts/bootstrap-rke2.sh")
        add_item("platform", "rke2_bootstrap_present" if bootstrap_exists else "rke2_bootstrap_missing", "info" if bootstrap_exists else "warning", f"RKE2 bootstrap script {'present' if bootstrap_exists else 'missing'}")
    elif platform == "openshift":
        route_exists, _ = _project_file_exists(entry, "platform/openshift/route.yaml")
        add_item("platform", "openshift_route_present" if route_exists else "openshift_route_missing", "info" if route_exists else "warning", f"OpenShift route {'present' if route_exists else 'missing'}")
        if summary["target_type"] == "remote":
            add_item("platform", "openshift_remote_note", "warning", "OpenShift remote validation assumes cluster CLI tools are available on the remote host")
    elif platform == "aks":
        ingress_exists, _ = _project_file_exists(entry, "platform/aks/ingress.yaml")
        add_item("platform", "aks_ingress_present" if ingress_exists else "aks_ingress_missing", "info" if ingress_exists else "warning", f"AKS ingress manifest {'present' if ingress_exists else 'missing'}")
        tf_exists, _ = _project_file_exists(entry, "terraform/modules/aks/main.tf")
        add_item("platform", "aks_module_present" if tf_exists else "aks_module_missing", "info" if tf_exists else "warning", f"AKS Terraform module {'present' if tf_exists else 'missing'}")

    blocking = sum(1 for item in items if item["classification"] == "blocking")
    warnings = sum(1 for item in items if item["classification"] == "warning")
    passed = sum(1 for item in items if item["classification"] == "pass")
    ok = blocking == 0
    return {"ok": ok, "items": items, "logs": logs, "summary": summary, "counts": {"pass": passed, "warning": warnings, "blocking": blocking}}


def _extract_post_deploy_substeps(log: Dict[str, Any]) -> List[Dict[str, Any]]:
    stdout = str(log.get("stdout") or "")
    stderr = str(log.get("stderr") or "")
    text = stdout + "\n" + stderr
    step_defs = [
        ("cluster-healthcheck", "Cluster Healthcheck"),
        ("mirror-secrets", "Mirror Secrets"),
        ("fleet-output", "Fleet Output"),
        ("import-dashboards", "Import Dashboards"),
    ]
    marker_hits: Dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("::pi-substep "):
            parts = line.split()
            if len(parts) >= 3:
                marker_hits[parts[1].strip()] = parts[2].strip().lower()
    substeps: List[Dict[str, Any]] = []
    for key, title in step_defs:
        status = marker_hits.get(key, "")
        detail = ""
        if not status:
            lowered = text.lower()
            if key == "cluster-healthcheck":
                if "cluster-healthcheck.sh not found; skipping." in text:
                    status = "skipped"
                    detail = "Generated healthcheck script is missing."
                elif "cluster healthcheck reported warnings" in lowered:
                    status = "warning"
                    detail = "Healthcheck ran with warnings."
                elif "checking cluster status and ensuring kubeconfig is in place" in lowered:
                    status = "ok"
                    detail = "Healthcheck stage ran."
            elif key == "mirror-secrets":
                if "mirror-secrets.sh not found; skipping." in text:
                    status = "skipped"
                    detail = "Generated secret mirroring script is missing."
                elif "secret mirroring failed" in lowered:
                    status = "warning"
                    detail = "Secret mirroring reported warnings."
                elif "mirroring secrets after cluster stabilizes" in lowered:
                    status = "ok"
                    detail = "Secret mirroring stage ran."
            elif key == "fleet-output":
                if "fleet output configuration failed" in lowered:
                    status = "warning"
                    detail = "Fleet output step reported warnings."
                elif "fleet-output" in lowered or "agent auto-enrollment" in lowered:
                    status = "ok"
                    detail = "Fleet output stage ran."
            elif key == "import-dashboards":
                if "dashboard import failed" in lowered:
                    status = "warning"
                    detail = "Dashboard import reported warnings."
                elif "import-dashboards" in lowered:
                    status = "ok"
                    detail = "Dashboard import stage ran."
        if status:
            if not detail:
                detail = {
                    "ok": "Completed",
                    "warning": "Completed with warnings",
                    "skipped": "Skipped",
                    "start": "Started",
                }.get(status, status.capitalize())
            substeps.append({"key": key, "title": title, "status": status, "detail": detail})
    return substeps


def _execute_project_script(
    entry: Dict[str, Any],
    script_key: str,
    allow_mutating: bool = False,
    script_arguments: Optional[Dict[str, Any]] = None,
    confirmation_text: str = "",
) -> Dict[str, Any]:
    manifest = _operations_manifest_for_entry(entry)
    script = next((item for item in manifest.get("operations") or [] if item.get("key") == script_key), None)
    if not script:
        meta = SCRIPT_OPERATION_REGISTRY.get(script_key)
        script = {"key": script_key, **meta} if meta else None
    if not script:
        raise HTTPException(status_code=404, detail="unknown script key")
    exists, resolved = _project_file_exists(entry, script.get("path", ""))
    script = _hydrate_script_metadata(entry, {**script, "exists": exists, "resolved_path": resolved})
    script["prerequisite_checks"] = _evaluate_script_prerequisites(entry, script)
    script["remote_gate"] = _remote_script_gate(entry, script)
    script["blocked_reasons"] = list(script["remote_gate"].get("blocked_reasons") or [])
    script["ready"] = exists
    runbook = _build_runbook_progress(entry, {
        "scripts": [script],
        "operations_manifest": manifest,
        "recent_runs": OPERATION_RUN_HISTORY.list(entry.get("id"))[:20],
    })
    supplied_arguments = {str(k): "" if v is None else str(v) for k, v in (script_arguments or {}).items()}
    missing_arguments = [
        arg.get("name") for arg in script.get("arguments") or []
        if arg.get("required") and not supplied_arguments.get(arg.get("name", "")).strip()
    ]
    if missing_arguments:
        raise HTTPException(status_code=400, detail=f"required script arguments missing: {', '.join(missing_arguments)}")
    dangerous = bool(script.get("dangerous", False))
    if dangerous and not allow_mutating:
        raise HTTPException(status_code=400, detail="script is marked as dangerous; set allow_mutating=true to run it")
    if dangerous and script.get("confirmation_required"):
        expected = str(script.get("confirmation_phrase") or "").strip()
        if not expected or confirmation_text.strip() != expected:
            raise HTTPException(status_code=400, detail=f"confirmation mismatch; type '{expected}' to continue")
    if not script.get("exists"):
        raise HTTPException(status_code=404, detail=f"script not found: {script.get('path', '')}")
    failed_checks = [check for check in script.get("prerequisite_checks") or [] if not check.get("ok")]
    if dangerous and not script.get("remote_gate", {}).get("ok", True):
        raise HTTPException(status_code=400, detail=f"remote readiness gate failed: {'; '.join(script.get('blocked_reasons') or ['remote diagnostics not ready'])}")
    script_env = {f"PI_ARG_{key.upper()}": value for key, value in supplied_arguments.items() if value.strip()}
    target_type = (entry.get("target_type") or "local").strip() or "local"
    if "PI_ARG_KUBECONFIG_PATH" not in script_env:
        kube_check = next(
            (
                check
                for check in (script.get("prerequisite_checks") or [])
                if str(check.get("name") or "").strip().lower() == "kubeconfig"
            ),
            None,
        )
        if not kube_check:
            kube_check = _check_remote_prerequisite(entry, "kubeconfig") if target_type == "remote" else _check_local_prerequisite(entry, "kubeconfig")
        if kube_check and kube_check.get("ok"):
            kube_path = _extract_kubeconfig_path(str(kube_check.get("detail") or "")).strip()
            if kube_path and kube_path.lower() not in {"present", "connected"}:
                script_env["PI_ARG_KUBECONFIG_PATH"] = kube_path
                script_env.setdefault("KUBECONFIG", kube_path)
    project_root, remote_cfg = _project_root_from_entry(entry)
    if remote_cfg:
        env_prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in script_env.items())
        remote_script = f"bash {shlex.quote(script['path'])}"
        cmd = f"cd {shlex.quote(project_root)} && {env_prefix + ' ' if env_prefix else ''}{remote_script}"
        log = _run_ssh_command(remote_cfg.get("host", ""), str(remote_cfg.get("port", "22")), remote_cfg.get("user", ""), cmd, remote_cfg.get("ssh_key_path", ""))
    else:
        env = os.environ.copy()
        env.update(script_env)
        log = _run_shell_command(["bash", str(Path(project_root) / script["path"])], Path(project_root), env=env)
    execution_context = {
        "arguments": supplied_arguments,
        "environment_overrides": sorted(script_env.keys()),
        "confirmation_text": confirmation_text.strip(),
        "target_type": (entry.get("target_type") or "local").strip() or "local",
        "remote": _remote_execution_context(entry),
        "prerequisite_summary": [
            {
                "name": item.get("name", ""),
                "ok": bool(item.get("ok")),
                "detail": item.get("detail", ""),
            }
            for item in (script.get("prerequisite_checks") or [])
        ],
        "prerequisite_warnings": [
            f"{item.get('name')}: {item.get('detail', '')}"
            for item in failed_checks
        ],
        "remote_gate_warnings": list(script.get("blocked_reasons") or []),
    }
    out_of_order = False
    sequencing_warning = ""
    next_recommended = runbook.get("next_recommended") or {}
    if next_recommended and next_recommended.get("key") and next_recommended.get("key") != script_key and script_key not in (runbook.get("completed_keys") or []):
        out_of_order = True
        sequencing_warning = f"Recommended next action is {next_recommended.get('key')} before {script_key}."
    current_step = next((item for item in (runbook.get("steps") or []) if item.get("key") == script_key), {})
    post_run_guidance = list(runbook.get("guidance") or [])
    if log.get("ok"):
        post_run_guidance.insert(0, f"Re-load project summary to update runbook completion after {script_key}.")
    else:
        post_run_guidance.insert(0, f"Investigate {script_key} output before continuing to the next runbook step.")
        post_run_guidance.extend(current_step.get("remediation") or [])
    substeps = _extract_post_deploy_substeps(log) if script_key == "post-terraform-deploy" else []
    return {
        "script": script,
        "log": log,
        "substeps": substeps,
        "execution_context": execution_context,
        "sequencing": {
            "out_of_order": out_of_order,
            "warning": sequencing_warning,
            "next_recommended": next_recommended,
            "next_command": runbook.get("next_command", ""),
            "current_step": current_step,
            "post_run_guidance": post_run_guidance,
            "failure_classification": "" if log.get("ok") else _classify_execution_failure((entry.get("target_type") or "local").strip() or "local", str(log.get("stderr") or ""), str(log.get("stdout") or "")),
        },
    }


@app.get("/api/audit")
def audit_log_list() -> Dict[str, Any]:
    return {"entries": AUDIT_LOG.list()}


@app.get("/api/project/operations")
def project_operations(deployment_id: str) -> Dict[str, Any]:
    entry = _find_deployment_entry(deployment_id)
    return _project_operations_summary(entry)


@app.get("/api/project/diagnostics")
def project_diagnostics(deployment_id: str) -> Dict[str, Any]:
    entry = _find_deployment_entry(deployment_id)
    return _collect_project_diagnostics(entry)


@app.get("/api/project/artifact-preview")
def project_artifact_preview(deployment_id: str, path: str) -> Dict[str, Any]:
    entry = _find_deployment_entry(deployment_id)
    return _read_project_text(entry, path)


@app.post("/api/project/validate")
def project_validate(deployment_id: str = Form(...)) -> Dict[str, Any]:
    entry = _find_deployment_entry(deployment_id)
    result = _run_project_validation(entry)
    run_record = OPERATION_RUN_HISTORY.add({
        "deployment_id": deployment_id,
        "project_name": entry.get("name", ""),
        "script_key": "project-validate",
        "title": "Project Validation",
        "kind": "validation",
        "target_type": (entry.get("target_type") or "local").strip() or "local",
        "ok": result.get("ok", False),
        "summary": f"pass={result.get('counts', {}).get('pass', 0)} warning={result.get('counts', {}).get('warning', 0)} blocking={result.get('counts', {}).get('blocking', 0)}",
        "stdout": "",
        "stderr": "" if result.get("ok", False) else "validation reported blocking findings",
    })
    AUDIT_LOG.append("project-validate", f"Validated {deployment_id}")
    return {**result, "run_record": run_record}


@app.get("/api/project/run-history")
def project_run_history(deployment_id: str) -> Dict[str, Any]:
    _find_deployment_entry(deployment_id)
    return {"entries": OPERATION_RUN_HISTORY.list(deployment_id)}


@app.post("/api/project/run-script")
def project_run_script(
    deployment_id: str = Form(...),
    script_key: str = Form(...),
    allow_mutating: bool = Form(False),
    script_arguments: str = Form(""),
    confirmation_text: str = Form(""),
) -> Dict[str, Any]:
    entry = _find_deployment_entry(deployment_id)
    try:
        parsed_arguments = json.loads(script_arguments) if script_arguments.strip() else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid script_arguments payload: {exc}") from exc
    if parsed_arguments and not isinstance(parsed_arguments, dict):
        raise HTTPException(status_code=400, detail="script_arguments must decode to an object")
    result = _execute_project_script(
        entry,
        script_key,
        allow_mutating=allow_mutating,
        script_arguments=parsed_arguments,
        confirmation_text=confirmation_text,
    )
    run_record = OPERATION_RUN_HISTORY.add({
        "deployment_id": deployment_id,
        "project_name": entry.get("name", ""),
        "script_key": script_key,
        "title": result.get("script", {}).get("title", script_key),
        "kind": "script",
        "target_type": (entry.get("target_type") or "local").strip() or "local",
        "allow_mutating": allow_mutating,
        "script_arguments": result.get("execution_context", {}).get("arguments", {}),
        "confirmation_required": result.get("script", {}).get("confirmation_required", False),
        "confirmation_text": result.get("execution_context", {}).get("confirmation_text", ""),
        "out_of_order": result.get("sequencing", {}).get("out_of_order", False),
        "sequencing_warning": result.get("sequencing", {}).get("warning", ""),
        "ok": result.get("log", {}).get("ok", False),
        "summary": result.get("log", {}).get("stderr") or result.get("log", {}).get("stdout", ""),
        "command": result.get("log", {}).get("command", ""),
        "stdout": result.get("log", {}).get("stdout", ""),
        "stderr": result.get("log", {}).get("stderr", ""),
        "substeps": result.get("substeps", []),
    })
    AUDIT_LOG.append("project-script", f"Ran {script_key} for {deployment_id}")
    return {**result, "run_record": run_record}


@app.post("/api/sync")
def sync_repo(
    repo_path: str = Form(...),
    branch: str = Form("main"),
    git_token: str = Form(""),
) -> Dict[str, Any]:
    path = Path(repo_path).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail="repo_path does not exist")

    if not (path / ".git").exists():
        raise HTTPException(status_code=400, detail="repo_path is not a git repository")

    origin_lookup = _run_git_command(["git", "remote", "get-url", "origin"], path)
    remote_url = origin_lookup.get("stdout", "") if origin_lookup.get("ok") else ""
    git_env, askpass_path = _prepare_git_pat_env(remote_url, git_token)
    try:
        log = [
            _run_git_command(["git", "checkout", branch], path, env=git_env),
            _run_git_command(["git", "pull", "--rebase", "origin", branch], path, env=git_env),
            _run_git_command(["git", "push", "origin", branch], path, env=git_env),
        ]
    finally:
        if askpass_path is not None:
            askpass_path.unlink(missing_ok=True)
    return {"repo_path": str(path), "branch": branch, "log": log}


@app.get("/api/version")
def version() -> Dict[str, Any]:
    return {
        "ui": "draft-0.1.0",
        "project_initializer_root": str(ROOT_DIR),
        "scripts_dir": str(SCRIPTS_DIR),
        "python": sys.version,
    }




@app.post("/api/open-remote")
def open_remote_path(
    host: str = Form(...),
    user: str = Form(...),
    remote_path: str = Form(...),
    port: str = Form("22"),
    tool: str = Form("zed"),
) -> Dict[str, Any]:
    h = host.strip()
    u = user.strip()
    rp = (remote_path or "").strip()
    normalized_port = (port or "22").strip() or "22"
    if not h or not u or not rp:
        raise HTTPException(status_code=400, detail="host, user, and remote_path are required")
    if not rp.startswith("/"):
        raise HTTPException(status_code=400, detail="remote_path must be an absolute POSIX path")

    cmd = _build_open_remote_command(tool, h, u, rp, normalized_port)
    try:
        subprocess.Popen(cmd)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Failed to open remote path: {exc}") from exc

    return {"ok": True, "tool": tool, "host": h, "user": u, "port": normalized_port, "remote_path": rp, "command": " ".join(cmd)}

@app.post("/api/open")
def open_path(
    path: str = Form(...),
    tool: str = Form("zed"),
) -> Dict[str, Any]:
    if tool == "filemanager" and not RUNTIME_ENV.get("supports_gui_open", False):
        raise HTTPException(status_code=501, detail="GUI open is not available in this session")
    target = _expand_input_path(path).resolve()
    if not target.exists():
        raise HTTPException(status_code=400, detail="path does not exist")

    cmd = _build_open_command(tool, target)
    try:
        subprocess.Popen(cmd)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500, detail=f"Failed to open path: {exc}"
        ) from exc

    return {"ok": True, "tool": tool, "path": str(target), "command": " ".join(cmd)}
