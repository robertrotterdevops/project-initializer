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
from datetime import datetime
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

sys.path.insert(0, str(SCRIPTS_DIR))

from project_analyzer import ProjectAnalyzer, analyze_project  # type: ignore  # noqa: E402
from generate_structure import initialize_project  # type: ignore  # noqa: E402
from sizing_parser import parse_sizing_file  # type: ignore  # noqa: E402


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
    return datetime.utcnow().isoformat() + "Z"


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
    if p in {"github", "gitlab"}:
        return p
    lower = (remote_url or "").strip().lower()
    if "github.com" in lower:
        return "github"
    if "gitlab.com" in lower:
        return "gitlab"
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
    if not username:
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


def _run_shell_command(command: List[str], cwd: Path) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
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
    run_terraform_apply: bool = Form(False),
    target_type: str = Form("local"),
    remote_host: str = Form(""),
    remote_port: str = Form("22"),
    remote_user: str = Form(""),
    remote_auth_mode: str = Form("ssh_key"),
    remote_ssh_key_path: str = Form(""),
    remote_base_dir: str = Form(""),
    sizing_file: Optional[UploadFile] = File(default=None),
) -> Dict[str, Any]:
    schema_id_clean = git_schema_id.strip() or None

    if not name.strip() or not target_dir.strip():
        raise HTTPException(status_code=400, detail="name and target_dir are required")

    safe_name = name.strip().strip("/").strip("\\")
    effective_target_type = (target_type or "local").strip().lower()

    normalized_target_parent = _normalize_target_dir(target_dir)
    Path(normalized_target_parent).mkdir(parents=True, exist_ok=True)
    normalized_target_dir = str((Path(normalized_target_parent) / safe_name).resolve())

    remote_cfg: Optional[Dict[str, str]] = None
    registry_target_path: Optional[str] = None
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

    if sizing_file is not None:
        if not sizing_file.filename:
            raise HTTPException(status_code=400, detail="sizing_file must be provided")

        lower_name = sizing_file.filename.lower()
        if not (lower_name.endswith(".md") or lower_name.endswith(".json")):
            raise HTTPException(status_code=400, detail="sizing_file must be a .json or .md file")

        suffix = ".json" if lower_name.endswith(".json") else ".md"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            raw = await sizing_file.read()
            tmp.write(raw)
            tmp_path = Path(tmp.name)

        try:
            sizing_context = parse_sizing_file(str(tmp_path))
            detected_platform = (sizing_context.get("platform_detected") if sizing_context else None)
        finally:
            tmp_path.unlink(missing_ok=True)

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
        target_revision=(git_branch.strip() or "main"),
        sizing_context=sizing_context,
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

    return result


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
) -> Dict[str, Any]:
    token = (git_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="git_token is required")
    provider = _detect_provider(git_provider, remote_url)
    if not provider:
        raise HTTPException(status_code=400, detail="git_provider is required (github/gitlab) when remote_url is not set")

    if provider == "gitlab":
        headers = {"PRIVATE-TOKEN": token, "Accept": "application/json", "User-Agent": "project-initializer"}
        me = _http_json_request("https://gitlab.com/api/v4/user", "GET", headers)
        return {"ok": True, "provider": "gitlab", "user": me.get("username") or me.get("name") or "", "scopes_hint": "Needs read_repository + write_repository (or api)."}

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
