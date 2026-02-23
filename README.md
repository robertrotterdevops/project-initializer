# project-initializer

Platform-agnostic project scaffolding with automatic skill assignment. Generate DevOps project structures (Terraform, ArgoCD, OpenShift, ECK) via a web UI or CLI.

## Quick Start

```bash
git clone <repo-url> && cd project-initializer
./start-ui.sh
# Open http://localhost:8787
```

The script creates a Python venv, installs dependencies, and launches the web UI.

## CLI Usage

No setup required beyond Python 3.9+:

```bash
python3 scripts/init_project.py --name my-project --desc "Elasticsearch on OpenShift"
python3 scripts/init_project.py --analyze-only --name my-project --desc "Elasticsearch on OpenShift"
```

## Desktop Mode (optional)

Tauri-based desktop app for macOS/Linux:

```bash
./start-ui-macos.sh   # macOS
./start-ui-linux.sh   # Linux
```

See `START-HERE-UI.md` for details.
