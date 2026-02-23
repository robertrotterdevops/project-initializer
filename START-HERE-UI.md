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

## Notes

- `start-ui-macos.sh` builds automatically if `.app` bundle is missing
- `start-ui-linux.sh` runs packaged binary if present, otherwise starts dev mode
- Windows support can be added with same Tauri architecture
