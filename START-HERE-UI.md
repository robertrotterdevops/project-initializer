# UI Start Shortcuts

Run from repository root.

## Quick Start

```bash
./start-ui.sh
```
Then open http://localhost:8787

This handles venv creation, dependency install, and server launch automatically.

### Desktop Mode (optional)

macOS launcher:
```bash
./start-ui-macos.sh
```

Linux launcher:
```bash
./start-ui-linux.sh
```

## New Features (v1.8)

- Polished dark/light theme UI
- Sidebar navigation (Create, Analyze, Git Sync, Settings)
- Recent Projects in sidebar
- Toast notifications
- Drag-drop sizing file upload
- Keyboard zoom controls (Cmd/Ctrl +/-/0)
- Status tab with live cluster monitoring
- Embedded readonly `k9s` session for deployment-scoped cluster inspection

## Notes

- `start-ui-macos.sh` builds automatically if `.app` bundle is missing
- `start-ui-linux.sh` runs packaged binary if present, otherwise starts dev mode
- Windows support can be added with same Tauri architecture
- Remote `k9s` sessions require `k9s` to be installed on the remote deployment host
- The Status tab uses the deployment kubeconfig exported by generated deployment scripts
