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
from pathlib import Path
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
    if any(k in t for k in ["aks", "azure kubernetes", "azure"]):
        return "aks"
    return None


def _override_chain(result: Dict[str, Any], forced_chain: str) -> Dict[str, Any]:
    if not forced_chain:
        return result

    analyzer = ProjectAnalyzer(config_path=str(ROOT_DIR))
    if forced_chain not in analyzer.priority_chains:
        return result

    skills = [
        s
        for s in analyzer.priority_chains.get(forced_chain, [])
        if analyzer.skill_mapping.get(s, {}).get("available", False)
    ]
    available, unavailable = analyzer.validate_skills(skills)
    result["priority_chain"] = forced_chain
    result["assigned_skills"] = available
    result["unavailable_skills"] = unavailable
    result["primary_skill"] = available[0] if available else None
    return result


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
        "platforms": ["", "rke2", "openshift", "aks"],
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
    description: str = Form(...),
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
    sizing_file: Optional[UploadFile] = File(default=None),
) -> Dict[str, Any]:
    if not name.strip() or not description.strip() or not target_dir.strip():
        raise HTTPException(
            status_code=400, detail="name, description, and target_dir are required"
        )

    normalized_target_dir = _normalize_target_dir(target_dir)
    Path(normalized_target_dir).parent.mkdir(parents=True, exist_ok=True)

    effective_desc = _apply_forced_type(description, forced_type)
    sizing_context: Optional[Dict[str, Any]] = None
    detected_platform: Optional[str] = None

    if sizing_file is not None:
        if not sizing_file.filename or not sizing_file.filename.lower().endswith(".md"):
            raise HTTPException(
                status_code=400, detail="sizing_file must be a .md file"
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as tmp:
            raw = await sizing_file.read()
            tmp.write(raw)
            tmp_path = Path(tmp.name)

        try:
            sizing_context = parse_sizing_file(str(tmp_path))
            detected_platform = (
                sizing_context.get("platform_detected") if sizing_context else None
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    description_platform = _infer_platform_from_text(description)
    final_platform = platform or description_platform or detected_platform

    result = initialize_project(
        project_name=name,
        description=effective_desc,
        target_directory=normalized_target_dir,
        forced_chain=forced_chain or None,
        platform=final_platform or None,
        gitops_tool=gitops_tool or None,
        sizing_context=sizing_context,
    )

    git_log: List[Dict[str, Any]] = []
    project_path = Path(result["project_path"]).resolve()

    if git_init:
        git_log.append(_run_git_command(["git", "init"], project_path))
        git_log.append(_run_git_command(["git", "add", "."], project_path))
        git_log.append(
            _run_git_command(["git", "commit", "-m", git_commit_message], project_path)
        )

        if git_remote_url.strip():
            git_log.append(
                _run_git_command(["git", "remote", "remove", "origin"], project_path)
            )
            git_log.append(
                _run_git_command(
                    ["git", "remote", "add", "origin", git_remote_url.strip()],
                    project_path,
                )
            )

        if git_push and git_remote_url.strip():
            git_log.append(
                _run_git_command(["git", "branch", "-M", git_branch], project_path)
            )
            git_log.append(
                _run_git_command(
                    ["git", "push", "-u", "origin", git_branch], project_path
                )
            )

    result["git"] = {
        "enabled": git_init,
        "remote": git_remote_url,
        "branch": git_branch,
        "push": git_push,
        "log": git_log,
    }
    result["effective_platform"] = final_platform
    result["normalized_target_dir"] = normalized_target_dir

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
