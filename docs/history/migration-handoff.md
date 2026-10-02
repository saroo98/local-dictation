# Local Dictation Handoff

## Goal

Continue the Windows local dictation app migration from the original Python/Tkinter UI toward a modern Tauri 2 + React + Vite + TypeScript + Tailwind + shadcn/ui desktop app.

The current product direction is:

- Keep transcription local-only.
- Preserve CUDA-first / CPU fallback behavior unless the user selects a device mode.
- Preserve the proven Python backend for audio/model/transcription/paste.
- Let Tauri own the modern desktop shell, tray, floating bubble, and transcript popover in packaged mode.
- Keep the old Python/Tk bubble available for direct standalone Python usage only.
- Avoid cloud APIs, telemetry, analytics, remote fonts/icons, and automatic network calls.

Active worktree:

```text
C:\local-dictation-tauri
```

Active branch:

```text
codex/tauri-react-migration
```

Do not continue this migration work in `C:\local-dictation` unless intentionally merging back. `C:\local-dictation` is still `master` and currently has unrelated untracked files:

```text
docs/
settings-redesign-preview.png
```

## Current Progress

The migration branch already contains multiple completed stages:

1. Stage 1: Tauri/React desktop UI foundation with mock bridge.
2. Stage 2: Read-only local bridge from Tauri to Python.
3. Stage 3: Write/action bridge for settings, recording actions, history actions, and model actions.
4. Stage 4: Development backend management from Tauri.
5. Stage 5: PyInstaller sidecar packaging readiness.
6. Control bridge architecture polish:
   - Added pure `control_bridge.py`.
   - Added `test_control_bridge.py`.
   - Kept JSON/legacy bridge response shapes stable.
7. Stage 6 / 6.1 / 6.2 Tauri ownership work:
   - Tauri app owns the modern blue floating bubble and React quick popover in packaged mode.
   - Python `--api` mode is intended to stay headless.
   - Tauri has native tray behavior.
   - Main window titlebar `X` now hides the main window instead of quitting the app.
   - Popover `Close` hides only the popover.
   - Tray `Quit` remains full app quit.
   - Backend startup was moved off the synchronous Tauri command path with `spawn_blocking`.
   - Recording page no longer calls `getState()` while backend is starting.
   - The packaged installer was rebuilt after Stage 6.2.

Latest installer built:

```text
C:\local-dictation-tauri\desktop\src-tauri\target\release\bundle\nsis\Local Dictation_0.1.0_x64-setup.exe
```

The installer was built successfully, but it was not manually installed and smoke-tested after the final Stage 6.2 fixes.

## Current Git State

At last check, `C:\local-dictation-tauri` was dirty with broad uncommitted migration work:

```text
 M bubble_dictate.py
 M desktop/src-tauri/Cargo.lock
 M desktop/src-tauri/Cargo.toml
 M desktop/src-tauri/capabilities/default.json
 M desktop/src-tauri/src/lib.rs
 M desktop/src-tauri/src/main.rs
 M desktop/src-tauri/tauri.conf.json
 M desktop/src/App.tsx
 M desktop/src/__tests__/bridge.test.ts
 M desktop/src/__tests__/python-bridge.test.ts
 M desktop/src/__tests__/stage3-ui.test.tsx
 M desktop/src/__tests__/stage4-backend-ui.test.tsx
 M desktop/src/app/AppProviders.tsx
 M desktop/src/app/useAppNavigation.ts
 M desktop/src/bridge/types.ts
 M desktop/src/bridge/useBackendStatus.ts
 M desktop/src/components/dictation/BubblePreview.tsx
 M desktop/src/components/dictation/QuickHistoryPopoverPreview.tsx
 M desktop/src/components/models/ModelCard.tsx
 M desktop/src/components/settings/HotkeyInput.tsx
 M desktop/src/components/shell/StatusPill.tsx
 M desktop/src/components/ui/simple-select.tsx
 M desktop/src/fixtures/settings.ts
 M desktop/src/globals.css
 M desktop/src/pages/RecordingPage.tsx
 M desktop/src/pages/SettingsPage.tsx
 M settings.py
 M test_bubble_dictate.py
 M test_settings.py
?? CONTEXT.md
?? control_bridge.py
?? desktop/src/__tests__/stage6-tauri-bubble-device.test.tsx
?? desktop/src/__tests__/ui-polish.test.tsx
?? desktop/src/bridge/BackendStatusContext.ts
?? desktop/src/bridge/BackendStatusProvider.tsx
?? desktop/src/components/dictation/FloatingBubbleSurface.tsx
?? desktop/src/components/dictation/QuickHistoryPopoverSurface.tsx
?? desktop/src/components/dictation/TauriBubbleController.tsx
?? desktop/src/tauri/
?? test_control_bridge.py
```

Important: this dirty state includes more than the final Stage 6.2 pass. It includes earlier Stage 3/4/5/6/control-bridge work that has not yet been committed after commit `e55a79d feat: add Tauri sidecar packaging readiness`.

Recent commits:

```text
e55a79d feat: add Tauri sidecar packaging readiness
c84289b feat: add Tauri local backend bridge
49d602f test: cover desktop mock UI foundation
4881e6d feat: build mock desktop dictation UI
ac03965 feat: add shadcn theme system and UI primitives
```

Do not reset or discard anything without explicit user approval.

## What Worked

### Python backend / API mode

`visual_shell_enabled("api")` disables the Python visual shell for packaged/Tauri backend usage.

Stage 6.2 added:

- `configure_hidden_event_root(app)` in `bubble_dictate.py`.
- The hidden root is withdrawn, moved to `1x1+-32000+-32000`, made borderless, made alpha `0.0` where supported, and repeatedly withdrawn after Tk starts.
- This targets the blank `Local Dictation Backend` window reported by the user.

Standalone Python launch should still show the old Tk bubble and tray.

### Tauri ownership

Tauri owns modern app surfaces in packaged mode:

- main window
- native tray
- blue floating bubble
- React quick popover

The main window `X` now hides only the main window. Native tray remains alive. Backend remains alive.

Full app quit should happen through:

- tray `Quit`
- explicit app quit command

The popover footer now uses:

```text
Settings | History | Tray | Close
```

`Close` hides only the popover, not the whole app.

### Backend startup responsiveness

The Rust `backend_start` command is now async and uses `tauri::async_runtime::spawn_blocking(...)` for sidecar/Python process launch. This reduces UI blocking compared with doing process launch directly in the synchronous command path.

The frontend `RecordingPage` now gates runtime state reads:

- If local backend is not ready, it does not call `bridge.getState()`.
- If backend is `starting`, the UI says `Backend starting` instead of `Backend not running`.

### Popover visual polish

The React `QuickHistoryPopoverSurface` now fills the transparent Tauri utility window instead of rendering a smaller card inside a larger transparent window. This targets the gray/white backing margin visible around the popover.

The quick popover window height was reduced from `320` to `300`:

```text
desktop/src-tauri/tauri.conf.json
desktop/src-tauri/src/lib.rs
```

### Test coverage

New/updated tests cover:

- API hidden root behavior.
- Main window close action.
- Popover footer behavior.
- Popover `Close` hiding only popover.
- Recording page not calling `getState()` during backend startup.
- Existing bridge/device/model/UI behavior.

## What Did Not Work / Avoid Repeating

### Do not try to keep styling the old Tk popover for packaged mode

The old Tk popover was repeatedly improved but hit visual and toolkit limits. In packaged/Tauri mode, the popover should stay React/Tauri-owned.

Keep old Tk popover only for direct Python standalone usage.

### Do not make main-window `X` quit the app

The user explicitly wants titlebar close to hide only the main window and keep:

- tray icon
- backend
- shortcuts/hotkeys
- resident behavior

Do not route main-window close to `app_quit`.

### Do not show app toasts inside tiny utility windows

The bubble window is too small for normal toast/error UI. Errors from the bubble should route the user back to the main window instead of showing cut-off toasts.

### Do not silently enable Vulkan

Current backend is faster-whisper/CTranslate2. Device choices implemented are:

- `auto`
- `cuda`
- `cpu`

Vulkan was intentionally shown as unavailable/disabled because the current CTranslate2 backend does not support `vulkan` for this path.

### Do not rely on browser/Vite mode for packaged ownership bugs

Browser mode at `http://127.0.0.1:1420/` is useful for UI review but cannot reproduce packaged window ownership, tray, sidecar, and utility-window behavior. Use the rebuilt installer or `npm run tauri dev` for those.

## Last Verified Checks

These were run successfully after Stage 6.2:

From `C:\local-dictation-tauri`:

```powershell
C:\local-dictation\.venv\Scripts\python.exe -B -m unittest discover -v
C:\local-dictation\.venv\Scripts\python.exe -B -m compileall -q bubble_dictate.py control_bridge.py settings.py icons.py
C:\local-dictation\.venv\Scripts\python.exe -B -c "import control_bridge, config, settings, icons, bubble_dictate; print('imports ok')"
```

Observed:

```text
156 Python tests passed
imports ok
```

From `C:\local-dictation-tauri\desktop`:

```powershell
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

Observed:

```text
13 Vitest files passed
42 React/TS tests passed
typecheck passed
lint passed
frontend build passed
```

From `C:\local-dictation-tauri\desktop\src-tauri`:

```powershell
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
cargo fmt --check
cargo test
cargo check
```

Observed:

```text
cargo fmt --check passed
10 Rust tests passed
cargo check passed
```

Packaging:

```powershell
cd C:\local-dictation-tauri\desktop
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
npm run tauri:build
```

Observed:

```text
PyInstaller backend built
Tauri release build succeeded
NSIS installer created:
C:\local-dictation-tauri\desktop\src-tauri\target\release\bundle\nsis\Local Dictation_0.1.0_x64-setup.exe
```

Offline/privacy scans:

```powershell
rg -n "https?://" desktop\index.html desktop\src
rg -n "analytics|telemetry|sentry|posthog|segment|amplitude|mixpanel" desktop\package.json
```

Observed:

```text
No remote URL matches in index/src.
No telemetry package-name matches in desktop/package.json.
```

There are expected source/test strings saying “no telemetry”; those are not telemetry dependencies.

## Next Steps

### 1. Manual install and smoke-test the rebuilt installer

Install:

```text
C:\local-dictation-tauri\desktop\src-tauri\target\release\bundle\nsis\Local Dictation_0.1.0_x64-setup.exe
```

Before testing, close old/stale app instances:

```powershell
Get-Process local-dictation-desktop,local-dictation-backend -ErrorAction SilentlyContinue
```

If stale instances remain after normal close, stop only these local dictation processes.

Smoke checklist:

- Launch installed app.
- Confirm no CMD window.
- Confirm no blank `Local Dictation Backend` window.
- Confirm no old Python green/Tk bubble in packaged/Tauri mode.
- Confirm only the modern blue Tauri bubble appears.
- Confirm startup does not freeze the main UI for several seconds.
- Confirm the top status says `Backend starting` while loading and `Local backend ready` when ready.
- Click main window `X`; main window should hide, tray/backend/bubble should stay alive.
- Use tray `Show app`; main window should return.
- Right-click bubble; popover should stay on-screen, with no gray/white backing margin.
- Popover footer should show `Settings`, `History`, `Tray`, `Close`.
- Popover `Close` should hide only the popover.
- Popover `Tray` should hide main/bubble/popover and keep tray/backend alive.
- Tray `Quit` should fully quit app and owned backend.
- Drag bubble; restart app; confirm saved/clamped bubble position.

### 2. Fix any remaining manual smoke issues

Likely areas if bugs remain:

- Tauri utility-window positioning in `desktop/src-tauri/src/lib.rs`.
- `QuickHistoryPopoverSurface.tsx` layout/window sizing.
- Backend ownership/status in `BackendStatusProvider`.
- Hidden Tk root behavior in `bubble_dictate.py`.

### 3. Commit current work in logical commits

Only after manual smoke is acceptable, commit carefully. Suggested split:

1. `refactor: isolate local control bridge routing`
   - `control_bridge.py`
   - `test_control_bridge.py`
   - relevant `bubble_dictate.py` bridge adapter changes
   - `CONTEXT.md`

2. `feat: add packaged Tauri backend ownership`
   - Rust backend manager / sidecar / tray / single-instance / Tauri windows
   - Python `--api` headless policy
   - Tauri capabilities/config

3. `feat: add Tauri floating bubble and popover`
   - React bubble/popover/controller surfaces
   - Tauri window controls
   - related tests

4. `feat: add device mode and model UI polish`
   - `settings.py`
   - `SettingsPage.tsx`
   - model labels/status/hotkey fixes
   - tests

5. `fix: polish startup, close-to-tray, and popover behavior`
   - Stage 6.2 changes:
     - hidden API root
     - main-window close hides
     - async backend start
     - popover `Close`
     - Recording page startup gating

Do not stage generated artifacts:

- `desktop/dist/`
- `desktop/src-tauri/target/`
- `desktop/src-tauri/binaries/`
- `build/pyinstaller-backend/`
- logs
- settings/history JSON
- model cache
- secrets / `.env`

### 4. Then plan Stage 7 or release-polish

After this is manually stable, the next stage should focus on:

- installer/start-menu/autostart polish
- app identity and icon polish
- native tray menu copy
- update-check strategy, if user wants it
- code signing strategy, later
- final docs for public release

Do not start a broad redesign until the packaged app ownership bugs are verified fixed.

## Skills / Capabilities To Use Next

Use these when continuing:

- `superpowers:systematic-debugging` for any packaged app/window/backend issue.
- `tdd` or `superpowers:test-driven-development` for each bug fix.
- `build-web-apps:react-best-practices` for React state/layout changes.
- `build-web-apps:shadcn` for UI consistency.
- `design-taste-frontend` for visual popover/bubble polish.
- `superpowers:verification-before-completion` before reporting completion.
- `github:github` only if the user explicitly asks to commit/push/PR.
- Do not use Gemini unless the user explicitly invokes or approves it.

## Important Constraints

- No cloud transcription.
- No OpenAI API calls for this app.
- No telemetry or analytics.
- No remote fonts/icons/CDN.
- No automatic model downloads.
- No secrets/env changes.
- No deploys, releases, pushes, or commits unless explicitly requested.
- Preserve current Python/Tk standalone usage.
- Preserve CUDA-first/device-mode behavior.
- Preserve local history/settings/model paths.

