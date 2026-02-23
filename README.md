# Project Initializer UI

A polished web-based user interface for `project-initializer`, designed for internal company use.

## Features

### Core Functionality
- **Project Creation**: Wizard-style form with all CLI options
- **Project Analysis**: Preview skill assignments without creating files
- **Git Sync**: Pull/rebase/push existing repositories
- **Sizing Integration**: Upload ES sizing reports (.md)

### UI/UX
- **Dark/Light Theme**: Toggle via sidebar or keyboard
- **Sidebar Navigation**: Create, Analyze, Git Sync, Settings pages
- **Recent Projects**: Quick access to last 5 created projects
- **Toast Notifications**: Success/error feedback
- **Zoom Controls**: Keyboard shortcuts (Cmd/Ctrl + +/-/0)

### Developer Tools
- **Open in Zed/VS Code**: Launch editor with created project
- **File Manager**: Open project folder in system explorer
- **Path Validation**: Real-time target directory validation

## Quick Start

### Web Mode

1. Create virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r ui-draft/requirements.txt
```

2. Start the API server:

```bash
uvicorn app:app --app-dir ui-draft/backend --reload --host 0.0.0.0 --port 8787
```

3. Open browser:

```
http://localhost:8787
```

### Desktop Mode (Tauri)

The UI can be packaged as a native desktop app:

```bash
# Run desktop dev mode
./ui-draft/run-desktop-dev.sh

# Build for distribution
./ui-draft/build-desktop.sh
```

Or use the OS-specific launchers:

```bash
./start-ui.sh        # Auto-detect OS
./start-ui-macos.sh  # macOS
./start-ui-linux.sh  # Linux
```

## UI Pages

### 1. Create Project
Main project creation form with:
- Project name, description, target directory
- Type selection (auto/elasticsearch/kubernetes/terraform/azure/gitops)
- Priority chain override
- Platform (RKE2/OpenShift/AKS)
- GitOps tool (FluxCD/ArgoCD/None)
- Sizing file upload (.md)
- Git options (init, commit message, remote URL, branch, push)
- Auto-open in Zed option

### 2. Analyze
Preview skill assignments and project configuration:
- Enter project details
- View detected category and priority chain
- See assigned skills and primary skill
- Preview project structure

### 3. Git Sync
Sync existing repositories:
- Select repository path
- Choose branch
- Pull/rebase/push in one click

### 4. Settings
Application preferences:
- Theme toggle (dark/light)
- Default target directory

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl + +` | Zoom in |
| `Cmd/Ctrl + -` | Zoom out |
| `Cmd/Ctrl + 0` | Reset zoom |

## Architecture

```
ui-draft/
├── frontend/
│   └── index.html      # Single-page UI (HTML/CSS/JS)
├── backend/
│   ├── app.py          # FastAPI application entry point
│   └── backend_api.py  # API endpoints and business logic
├── desktop/            # Tauri desktop shell
│   └── src-tauri/     # Rust source
├── scripts/           # Backend Python dependencies
└── requirements.txt    # Python dependencies
```

## Technology Stack

- **Frontend**: Vanilla HTML/CSS/JS, Lucide Icons, Google Fonts (Inter, JetBrains Mono)
- **Backend**: FastAPI (Python)
- **Desktop**: Tauri (Rust)
- **Styling**: CSS custom properties with dark/light theme support

## Theme Colors

### Dark Theme (Default)
| Element | Color |
|---------|-------|
| Background | `#0f1218` |
| Sidebar | `#1e2530` |
| Cards | `#252b35` |
| Input | `#1a2028` |
| Accent | `#00d4aa` (teal) |
| Text | `#ffffff` / `#a1aeb8` |

### Light Theme
| Element | Color |
|---------|-------|
| Background | `#f8fafc` |
| Cards | `#ffffff` |
| Accent | `#0d9488` |

## Security Notes

- Current version trusts local user input (internal use only)
- For production deployment, consider adding:
  - Path traversal protection
  - Workspace root restrictions
  - Authentication/authorization
  - Audit logging

## Cross-Platform

- **macOS**: Full support (tested)
- **Linux**: Full support (amd64)
- **Windows**: Not currently supported (can be added)

## Troubleshooting

### Backend won't start
```bash
# Check if port is in use
lsof -i :8787

# Kill existing process
pkill -f uvicorn
```

### API not reachable
- Ensure virtual environment is activated
- Check `.venv` has required packages: `pip install -r ui-draft/requirements.txt`

### Desktop build fails
- Verify Rust toolchain: `rustc --version`
- Check Node.js: `node --version`
- Linux: Ensure build deps are installed (see README)
