#!/usr/bin/env python3
"""Project Initializer UI API.

Draft API for a professional internal UI around project-initializer.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

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

sys.path.insert(0, str(SCRIPTS_DIR))

from project_analyzer import ProjectAnalyzer, analyze_project  # type: ignore  # noqa: E402
from generate_structure import initialize_project  # type: ignore  # noqa: E402
from sizing_parser import parse_sizing_file  # type: ignore  # noqa: E402


USER_HOME = Path.home()
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


def _run_git_command(command: List[str], cwd: Path) -> Dict[str, Any]:
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
def health() -> Dict[str, str]:
    return {"status": "ok"}


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
    selected = _pick_directory_os_dialog(initial_path=initial_path)
    p = Path(selected).resolve()
    return {"path": str(p), "exists": p.exists(), "is_dir": p.is_dir()}




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
    if not name.strip() or not target_dir.strip():
        raise HTTPException(status_code=400, detail="name and target_dir are required")

    safe_name = name.strip().strip("/").strip("\\")
    effective_target_type = (target_type or "local").strip().lower()

    normalized_target_parent = _normalize_target_dir(target_dir)
    Path(normalized_target_parent).mkdir(parents=True, exist_ok=True)
    normalized_target_dir = str((Path(normalized_target_parent) / safe_name).resolve())

    remote_cfg: Optional[Dict[str, str]] = None
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

    result = initialize_project(
        project_name=name,
        description=effective_desc,
        target_directory=str(local_build_dir),
        forced_chain=forced_chain or None,
        platform=final_platform or None,
        gitops_tool=final_gitops,
        iac_tool="terraform" if use_terraform_iac else "",
        repo_url=git_remote_url.strip() or None,
        target_revision=(git_branch.strip() or "main"),
        sizing_context=sizing_context,
    )

    git_log: List[Dict[str, Any]] = []
    project_path = Path(result["project_path"]).resolve()

    if git_init:
        git_log.append(_run_git_command(["git", "init"], project_path))
        git_log.append(_run_git_command(["git", "add", "."], project_path))
        git_log.append(_run_git_command(["git", "commit", "-m", git_commit_message], project_path))

        if git_remote_url.strip():
            git_log.append(_run_git_command(["git", "remote", "remove", "origin"], project_path))
            git_log.append(_run_git_command(["git", "remote", "add", "origin", git_remote_url.strip()], project_path))

        if git_push and git_remote_url.strip():
            git_log.append(_run_git_command(["git", "branch", "-M", git_branch], project_path))
            git_log.append(_run_git_command(["git", "push", "-u", "origin", git_branch], project_path))

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
        "remote": git_remote_url,
        "branch": git_branch,
        "push": git_push,
        "log": git_log,
    }
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

    return result


@app.post("/api/sync")
def sync_repo(
    repo_path: str = Form(...),
    branch: str = Form("main"),
) -> Dict[str, Any]:
    path = Path(repo_path).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail="repo_path does not exist")

    if not (path / ".git").exists():
        raise HTTPException(status_code=400, detail="repo_path is not a git repository")

    log = [
        _run_git_command(["git", "checkout", branch], path),
        _run_git_command(["git", "pull", "--rebase", "origin", branch], path),
        _run_git_command(["git", "push", "origin", branch], path),
    ]
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
