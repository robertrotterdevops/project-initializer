# UI Start Shortcuts

Run from repository root.

## Quick Start

### Web Mode
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r ui-draft/requirements.txt
uvicorn app:app --app-dir ui-draft/backend --reload --port 8787
```
Then open http://localhost:8787

### Desktop Mode

Auto-detect OS:
```bash
./start-ui.sh
```

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
