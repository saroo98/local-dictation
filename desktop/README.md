# Desktop interface

React/TypeScript provides the pages, bubble and history surface. Tauri/Rust owns
windows, the tray and backend lifecycle. See the [root README](../README.md)
and [architecture](../docs/architecture.md) for current setup and responsibilities.

Run from this directory:

```powershell
npm ci
npm run dev            # Browser mock.
npm run tauri dev      # Native debug app.
npm run build:backend  # Python sidecar from ../backend.
npm run tauri:build    # Sidecar, frontend and Windows installer.
```

Installer output: `src-tauri/target/release/bundle/nsis`. Building does not install
or publish. Debug prefers the sidecar, then repository `.venv` and Python source.
Runtime settings, history and logs retain `C:\local-dictation`.

Browser preview cannot validate native focus, window positions, hotkeys, audio,
process ownership or cross-application paste.
