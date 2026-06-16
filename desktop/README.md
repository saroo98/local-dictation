# Local Dictation Desktop UI

This is the staged Tauri 2 + React desktop UI migration for Local Dictation.

## What This Is

- A reviewable modern desktop UI under `desktop/`
- React + Vite + TypeScript + Tailwind CSS + shadcn-style local components
- A typed bridge that mirrors the current Python app shapes
- A browser-reviewable shell with Recording, History, Models, Settings, Exports, and Help/About pages
- Light, Dark, and System appearance modes
- Neutral, Green, and Blue theme presets
- Stage 4 backend controls when running inside Tauri

## What This Is Not

- It does not replace the current Python/Tkinter app.
- It does not use the microphone.
- Browser mode does not call Python.
- Browser mode does not download models.
- Browser mode does not touch real transcript history or settings files.
- It does not perform any cloud transcription.
- It is not final installer packaging.

## Stage 4 Backend Behavior

When running inside Tauri, the desktop UI can start and monitor the local Python backend in `--api` mode:

```powershell
.\.venv\Scripts\pythonw.exe .\bubble_dictate.py --api
```

The Tauri shell still uses the existing local bridge on:

```text
127.0.0.1:49731
```

The existing Python/Tkinter app remains usable directly. Stage 4 does not remove the bubble, tray icon, shortcuts, CUDA-first model loading, CPU fallback, history files, settings files, or model cache paths.

## Run Browser Review

```powershell
cd C:\local-dictation-tauri\desktop
npm install
npm run dev
```

Open:

```text
http://localhost:1420
```

## Build Frontend

```powershell
cd C:\local-dictation-tauri\desktop
npm run build
```

## Test

```powershell
cd C:\local-dictation-tauri\desktop
npm test -- --run
npm run typecheck
npm run lint
```

## Tauri Note

Rust is required for:

```powershell
npm run tauri dev
```

Rust is not required for browser review. Rust is required to verify the Stage 4 Tauri runtime commands that start, stop, restart, and check health for the Python backend.

When Rust is installed:

1. Start Tauri with `npm run tauri dev`.
2. Open Help/About.
3. Use **Start backend**.
4. Confirm the top bar changes to **Local backend ready**.
5. Use Recording, History, Models, and Settings through the local bridge.

## Offline Guarantees

Phase 1 has:

- no CDN assets
- no remote fonts
- no remote icons
- no telemetry
- no analytics
- no automatic update checks
- no automatic model downloads
- no backend connection

Stage 4 keeps the same offline policy. The backend manager only starts a local Python process and talks to `127.0.0.1`. It does not add cloud transcription, telemetry, analytics, remote fonts, remote icons, or automatic network calls.

The only later allowed network actions are explicit user-triggered model downloads and explicit user-triggered update checks.

## Bridge Plan

Browser mode uses a mock bridge in `src/bridge/mockBridge.ts`.

Implemented migration path:

1. Python JSON API commands reuse the existing settings, history, model, and control functions.
2. Tauri Rust commands proxy typed bridge calls to the local Python API.
3. Real recording/model/history actions are behind the same TypeScript `Bridge` interface.
4. Stage 4 adds backend process start/stop/restart/health controls for development builds.
5. Stage 5 should package the Python backend as a PyInstaller executable and wire it as a real Tauri sidecar.

## Troubleshooting

- **Python venv missing:** create or restore `.venv` in `C:\local-dictation-tauri` or `C:\local-dictation`.
- **Model not downloaded:** the backend may fail during startup because `LOCAL_FILES_ONLY = True`.
- **Microphone unavailable:** the backend logs a startup error if `sounddevice` cannot open the input stream.
- **Port already in use:** an existing Python dictation instance may already own `127.0.0.1:49731`.
- **Backend starts slowly:** CUDA and faster-whisper model loading can take time; keep watching the backend status.
- **Debug log:** check `C:\local-dictation\dictation_debug.log` or the worktree log beside `bubble_dictate.py`.
