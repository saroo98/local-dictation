# Local Dictation Desktop UI

This is the Phase 1 Tauri 2 + React desktop UI migration foundation for Local Dictation.

## What This Is

- A reviewable modern desktop UI under `desktop/`
- React + Vite + TypeScript + Tailwind CSS + shadcn-style local components
- A typed mock bridge that mirrors the current Python app shapes
- A browser-reviewable shell with Recording, History, Models, Settings, Exports, and Help/About pages
- Light, Dark, and System appearance modes
- Neutral, Green, and Blue theme presets

## What This Is Not

- It does not replace the current Python/Tkinter app.
- It does not use the microphone.
- It does not call Python.
- It does not download models.
- It does not touch real transcript history or settings files.
- It does not perform any cloud transcription.

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

Rust is not required for Phase 1 browser review. The Tauri config is present so the desktop shell can be built later after `rustup` is installed.

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

The only later allowed network actions are explicit user-triggered model downloads and explicit user-triggered update checks.

## Bridge Plan

Phase 1 uses a mock bridge in `src/bridge/mockBridge.ts`.

Later phases should add:

1. A Python JSON API mode that reuses the existing settings, history, model, and control functions.
2. A Tauri Rust command that proxies typed bridge calls to the local Python API.
3. Real recording/model/history actions behind the same TypeScript `Bridge` interface.
4. Sidecar packaging only after the bridge is stable.
