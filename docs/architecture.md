# Architecture

| Location | Responsibility |
| --- | --- |
| `backend/bubble_dictate.py` | Audio, inference, state, paste, control server and legacy Tk interface |
| `backend/settings.py` | Settings validation, models, local availability and exports |
| `backend/persistence.py` | Atomic JSON replacement and explicit corrupt-file recovery |
| `backend/control_bridge.py` | JSON routing and response envelopes |
| `backend/config.py` | Audio, inference, transport and data defaults |
| `backend/icons.py` | Legacy interface icons |
| `desktop/src/bridge` | Typed bridge, browser mock and backend status |
| `desktop/src/pages` | Recording, history, models, settings, exports and help |
| `desktop/src/components/dictation` | Bubble and quick-history webview surfaces |
| `desktop/src-tauri/src/lib.rs` | Native windows, tray, process ownership and TCP proxy |
| `desktop/src-tauri/src/windows_native.rs` | Windows job ownership and utility-window activation guard |
| `scripts/build-backend-sidecar.ps1` | PyInstaller sidecar packaging |

## Flow

```text
React interface -> typed bridge -> Tauri command
  -> newline JSON over 127.0.0.1:49731 -> Python router/runtime
  -> in-memory audio -> faster-whisper -> transcript
  -> clipboard/paste, local history and frontend state
```

The browser substitutes a mock bridge. Native has three persistent windows:
main, bubble and quick history. Python `--api` mode uses a hidden Tk event loop
for existing scheduling. Python-only launch retains its legacy interface.

## Lifecycle and state

Tauri prefers the bundled sidecar. Debug can use root `.venv` and Python source;
release requires the sidecar. Status distinguishes starting, ready, missing
and unhealthy backends. Main-window close hides the app. Quit verifies a launch
identifier and stops only its managed Windows job, which owns descendants from
process creation. Independent backends survive shell shutdown. Blocking work
runs outside short manager locks. Native single-instance handling prevents
another shell from creating an app session.

Python owns recording state, settings, models and history. It starts the control
service before model/microphone initialization and exposes loading, resource
readiness and distinct failures. Settings patches are serialized; candidate
models are loaded and warmed before atomic persistence and publication. A
failed change keeps the previous model/settings. Text publication and history
persistence precede optional clipboard/paste delivery. Paste workers claim one
session and check the writable target identity again before injection.

Each webview shares one serialized state stream and pauses it while hidden.
History revisions refresh existing pages/popovers. Native visibility and
appearance events synchronize persistent windows. Browser mode uses local
storage for appearance and explicitly rejects unavailable filesystem actions.

Runtime data retains `C:\local-dictation/settings.json`, `transcript_history.json`,
`dictation_debug.log` and `logs/`. Models use a configured directory or the
Hugging Face cache. Inference receives a complete validated local snapshot,
including tokenizer and vocabulary files. Explicit downloads are separate,
deduplicated actions. JSON writes are atomic and corrupt files are preserved
until explicit recovery. Audio chunks are released before inference; rotating
logs bound disk use and do not record transcript text.

An explicit `LOCAL_DICTATION_DATA_DIR` overrides the default data profile for
isolated development. GPU builds stage pinned CUDA libraries under `build/cuda`
and package them as installed `cuda/` resources. The x64 frozen backend receives
that directory and retains DLL search handles. CPU-only builds omit these
resources; neither variant bundles models or development environments.

## Organization

Python modules were moved together and tests separated. Tauri retains its
conventional layout and descriptive names. The cleanup does not rewrite the
control protocol or inference engine, split the legacy runtime into speculative
modules or introduce a framework. Extract code only when a specific behavior
change benefits from it.

Git history is preserved. Earlier worktrees, caches and copied personal data
were archived outside the active source folder. `docs/history` contains older
notes and design references, not current instructions or validation results.
