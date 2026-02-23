#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::{Child, Command};
use tauri::Manager;

fn spawn_backend() -> Option<Child> {
    // Dev mode: run local Python backend script.
    if cfg!(debug_assertions) {
        let py_venv = PathBuf::from("../../../.venv/bin/python");
        let py = if py_venv.exists() {
            py_venv
        } else {
            PathBuf::from("python3")
        };

        let mut cmd = Command::new(py);
        cmd.arg("../../backend/run_backend.py");
        return cmd.spawn().ok();
    }

    // Packaged mode: try sidecar binary copied into resources.
    let exe = std::env::current_exe().ok()?;
    let mut sidecar_path = PathBuf::from(exe.parent()?);
    sidecar_path.push("pi-backend");
    Command::new(sidecar_path).spawn().ok()
}

fn main() {
    let mut backend = spawn_backend();

    tauri::Builder::default()
        .setup(|app| {
            if let Some(win) = app.get_webview_window("main") {
                win.eval("window.__PI_API_BASE = 'http://127.0.0.1:8787';").ok();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");

    if let Some(child) = backend.as_mut() {
        let _ = child.kill();
    }
}
