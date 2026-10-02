# Local Dictation

Windows speech-to-text with local Whisper inference, a Tauri desktop interface,
a floating bubble, clipboard output and local transcript history. App version:
**0.1.0**. The frontend package version is private build metadata.

## Repository

```text
local-dictation/
  backend/               Python runtime and dependency requirements
    tests/               Python unit tests
  desktop/               React interface and its tests
    src-tauri/           Rust native shell and Windows packaging
  scripts/               Windows launch, build and shortcut utilities
  docs/                  Architecture, audit and implementation plan
    history/             Historical notes and design references
```

`.venv`, `desktop/node_modules`, build output and model caches are generated
files, not source. Historical notes do not override current source or checks.

- [Architecture](docs/architecture.md)
- [Audit](docs/audit.md)
- [Implementation plan](docs/implementation-plan.md)
- [Implementation status and verification](docs/implementation-status.md)
- [Current results and remaining acceptance checks](docs/verification.md)

## Development

Windows, a microphone, Python, Node.js/npm and the Rust MSVC toolchain are needed.
Python 3.12 is the existing development environment. CUDA is optional.
Run setup from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-build.txt
cd desktop
npm ci
npm run tauri dev
```

Debug prefers a generated sidecar when present, otherwise the root `.venv` and
`backend/bubble_dictate.py`. Release builds require the sidecar. `npm run dev`
from `desktop/` reviews the interface with mock data. The browser cannot verify
native focus, windows, hotkeys, audio input or cross-application pasting.

## Checks and packaging

Run each group from the directory named in its comment:

```powershell
# backend/
..\.venv\Scripts\python.exe -B -m unittest discover -s tests

# desktop/
npm test -- --run
npm run typecheck
npm run lint
npm run build:frontend

# desktop/src-tauri/
cargo fmt --check
cargo test --locked

# desktop/
npm run tauri:build
```

The installer goes under `desktop/src-tauri/target/release/bundle/nsis`.
Building does not install the app or publish a release.

The default installer includes CUDA libraries. Install their separate pinned
requirements before packaging:

```powershell
# repository root
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-cuda.txt
```

For a smaller CPU-only installer, stage the backend explicitly and then run Tauri
without the default GPU staging step:

```powershell
# repository root
.\scripts\build-backend-sidecar.ps1 -CpuOnly
cd desktop
npm run tauri -- build
```

GPU libraries are installed once in `cuda/`, outside the sidecar's one-file
archive. Models are never bundled. The exact Python resolution is constrained
by `backend/requirements-lock.txt`; optional CUDA versions have their own lock.

## Runtime behavior

Existing settings, the last five transcripts and logs use `C:\local-dictation`,
separate from source. This data location is preserved by the cleanup. Audio is
held in memory. Ordinary inference uses locally available models; explicit
model downloads can access Hugging Face. Custom models must be compatible with
faster-whisper/CTranslate2, not arbitrary PyTorch checkpoints.

Automatic device mode attempts CUDA and then CPU. Explicit CUDA reports failure
without CPU fallback. Closing the main native window hides it to the tray.
Quit stops only the backend tree owned by this shell. An independent backend is
left running. Startup keeps Models and Settings reachable when a model or
microphone fails; Recording provides Retry resources. Complete local model
snapshots are validated before inference, including their tokenizer.

Native settings save only changed fields. Failed model/device changes preserve
the working configuration. History and settings use atomic replacement;
malformed files remain available for recovery. Successful transcripts stay
available if clipboard or paste delivery fails. Default text cleanup preserves
literal punctuation. Logs have bounded rotation and omit transcript text.

For isolated development checks, `LOCAL_DICTATION_DATA_DIR` selects a separate
data profile. The default directory is unchanged. Profiles share the control
port, so they cannot run concurrently with an existing backend on that port.

`scripts/start-bubble.bat` starts the legacy Python interface. The shortcut
scripts manage that interface's shortcuts and should only be run when wanted.
