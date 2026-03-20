#!/usr/bin/env python3
"""Project Initializer UI API.

Draft API for a professional internal UI around project-initializer.
"""

import json
import os
import base64
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, UTC
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any, Dict, List, Optional
from uuid import uuid4

import asyncio

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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

sys.path.insert(0, str(SCRIPTS_DIR))

from project_analyzer import ProjectAnalyzer, analyze_project  # type: ignore  # noqa: E402
from generate_structure import initialize_project  # type: ignore  # noqa: E402
from sizing_parser import parse_sizing_file_detailed  # type: ignore  # noqa: E402
from addon_loader import AddonLoader  # type: ignore  # noqa: E402


USER_HOME = Path.home()
SSH_DIR = USER_HOME / ".ssh"
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


def _derive_kustomization_names(project_name: str) -> List[str]:
    pn = project_name.strip()
    return [pn, f"{pn}-infra", f"{pn}-apps", f"{pn}-agents"]


def _parse_ks_kubectl_output(stdout: str) -> tuple:
    """Parse 'Ready|Reason|Message' from kubectl jsonpath output."""
    parts = (stdout or "").split("|", 2)
    ready = parts[0].strip() if len(parts) > 0 else ""
    reason = parts[1].strip() if len(parts) > 1 else ""
    message = parts[2].strip() if len(parts) > 2 else ""
    return ready, reason, message


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


def _build_sizing_preview_payload(result: Any) -> Dict[str, Any]:
    model = result.model
    ctx = result.addon_context or {}
    pools = list(model.pools) if model else list(
        ((ctx.get("rke2") or {}).get("pools") or ((ctx.get("openshift") or {}).get("pools") or []))
    )
    return {
        "ok": result.fatal_error is None,
        "schema_version": model.schema_version if model else None,
        "source_format": model.source_format if model else None,
        "platform_detected": model.platform_detected if model else None,
        "health_score": ctx.get("health_score"),
        "inputs": model.inputs if model else {},
        "summary": model.summary if model else {},
        "tiers": model.tiers if model else {},
        "components": model.components if model else {},
        "pools": pools,
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
    files = list(result.get("files_created") or [])
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


def _build_open_remote_command(tool: str, host: str, user: str, remote_path: str) -> List[str]:
    if tool == "zed":
        if shutil.which("zed") is None:
            raise HTTPException(status_code=400, detail="zed is not installed or not in PATH")
        return ["zed", f"ssh://{user}@{host}{remote_path}"]

    if tool == "vscode":
        if shutil.which("code") is None:
            raise HTTPException(status_code=400, detail="vscode CLI 'code' is not installed or not in PATH")
        uri = f"vscode-remote://ssh-remote+{host}{remote_path}"
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
            "remote": remote_result if effective_target_type == "remote" else None,
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
        if sizing_preview.get("warnings"):
            yield _sse("warning", "Sizing input parsed with warnings", warnings=sizing_preview["warnings"])
        if sizing_preview.get("caveats"):
            yield _sse("warning", "Platform caveats detected", caveats=sizing_preview["caveats"], sizing_preview=sizing_preview)
        addon_preview = sizing_preview.get("addon_preview") or {}
        if addon_preview.get("addons"):
            yield _sse("addons", "Addon plan computed", addon_preview=addon_preview)
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
            "remote": remote_result if effective_target_type == "remote" else None,
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
            sizing_preview=sizing_preview,
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
def deployment_history_delete(entry_id: str) -> Dict[str, Any]:
    DEPLOYMENT_HISTORY.delete(entry_id)
    return {"ok": True}


@app.get("/api/flux-status")
def flux_status(deployment_id: str, kubeconfig: str = "") -> Dict[str, Any]:
    entries = DEPLOYMENT_HISTORY.list()
    entry = next((e for e in entries if e.get("id") == deployment_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="deployment not found")

    target_type = (entry.get("target_type") or "local").strip()
    project_name = entry.get("name", "")
    ks_names = _derive_kustomization_names(project_name)
    polled_at = _utcnow()
    kustomizations = []

    jsonpath = (
        "{.status.conditions[?(@.type=='Ready')].status}"
        "|{.status.conditions[?(@.type=='Ready')].reason}"
        "|{.status.conditions[?(@.type=='Ready')].message}"
    )

    if target_type == "remote":
        remote_cfg = entry.get("remote") or {}
        host = remote_cfg.get("host", "")
        port = str(remote_cfg.get("port", "22"))
        user = remote_cfg.get("user", "")
        ssh_key_path = remote_cfg.get("ssh_key_path", "")
        for ks in ks_names:
            cmd = (
                f"kubectl get kustomization {ks} -n flux-system "
                f"-o jsonpath='{jsonpath}' 2>/dev/null || echo 'Unknown||'"
            )
            r = _run_ssh_command(host, port, user, cmd, ssh_key_path)
            ready, reason, message = _parse_ks_kubectl_output(r.get("stdout", ""))
            kustomizations.append({"name": ks, "namespace": "flux-system",
                                   "ready": ready, "reason": reason,
                                   "message": message, "polled_at": polled_at})
        es_cmd = (
            f"kubectl get statefulset -n {project_name} "
            f"-o jsonpath='{{.items[*].status.readyReplicas}}/{{.items[*].status.replicas}}' "
            f"2>/dev/null || echo '0/0'"
        )
        es_r = _run_ssh_command(host, port, user, es_cmd, ssh_key_path)
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

    es_stdout = (es_r.get("stdout") or "0/0")
    es_parts = es_stdout.split("/", 1)
    es_pods = {
        "running": es_parts[0].strip() if len(es_parts) > 0 else "0",
        "total": es_parts[1].strip() if len(es_parts) > 1 else "0",
    }

    AUDIT_LOG.append("flux-poll", f"Polled {deployment_id}")
    return {"deployment_id": deployment_id, "kustomizations": kustomizations,
            "es_pods": es_pods, "polled_at": polled_at}


@app.get("/api/audit")
def audit_log_list() -> Dict[str, Any]:
    return {"entries": AUDIT_LOG.list()}


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
    tool: str = Form("zed"),
) -> Dict[str, Any]:
    h = host.strip()
    u = user.strip()
    rp = (remote_path or "").strip()
    if not h or not u or not rp:
        raise HTTPException(status_code=400, detail="host, user and remote_path are required")
    if not rp.startswith("/"):
        raise HTTPException(status_code=400, detail="remote_path must be an absolute POSIX path")

    cmd = _build_open_remote_command(tool, h, u, rp)
    try:
        subprocess.Popen(cmd)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Failed to open remote path: {exc}") from exc

    return {"ok": True, "tool": tool, "host": h, "user": u, "remote_path": rp, "command": " ".join(cmd)}

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
