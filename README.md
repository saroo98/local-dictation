<picture>
  <source media="(prefers-color-scheme: dark)" srcset="desktop/public/branding/logo-horizontal-white.svg">
  <img src="desktop/public/branding/logo-horizontal-color.svg" alt="Local Dictation" width="420">
</picture>

# Local Dictation: Offline Speech-to-Text for Windows

Local Dictation is a Windows desktop app for voice typing with local Whisper
speech recognition. Record from a floating bubble or a keyboard shortcut, then
copy the transcript or paste it into a writable field in another app.
Transcription runs on your computer using faster-whisper, without a cloud
speech service or an app account.

**Desktop version: 0.1.2.** The Windows installer release is being prepared.
There are currently no published releases. When available, downloads will be
listed on the [GitHub releases page](https://github.com/saroo98/local-dictation/releases).
You can build from source using the instructions below.

## Features

- **Floating dictation bubble:** click to start or stop recording, drag to move,
  and right-click for recent transcripts and app controls.
- **Global keyboard shortcut:** Ctrl+Alt+D by default, configurable in Settings.
- **Clipboard and paste:** completed text stays available in history when
  delivery to another app fails.
- **Local AI models:** choose a built-in Whisper model or add a compatible
  faster-whisper/CTranslate2 model. Downloads require an explicit action.
- **CPU and NVIDIA CUDA:** automatic mode tries CUDA then CPU; explicit CPU or
  CUDA modes are also available.
- **History and exports:** keep the last five transcripts locally, copy recent
  entries, or export history as plain text or Markdown.
- **Appearance and tray:** light, dark and system themes; closing the main
  window keeps the app available from the system tray.

## Getting started

The desktop package targets Windows x64. You need a working microphone and
enough memory and disk space for your selected model. CUDA mode also needs a
compatible NVIDIA GPU and driver. CPU mode does not require an NVIDIA GPU.

1. Open **Models**. Download a model explicitly, or add an existing compatible
   local model. Models are not included in the installer.
2. In **Settings**, select the downloaded model, your language and device mode,
   then save. **Auto** permits CPU fallback; **CUDA** reports a failure if GPU
   loading fails.
3. Wait for recording resources to become ready. If a model or microphone fails,
   use **Retry resources** on Recording or Help/About after resolving the issue.
4. Focus the text field where you want to dictate. Click the bubble or press
   **Ctrl+Alt+D** to start, speak, then toggle again to stop and transcribe.
5. When an editable field is still focused, the app attempts automatic paste.
   Otherwise, click a writable target after transcription. You can also copy
   the completed text from Recording or History.

Right-click the bubble for quick history, Settings and tray controls. Closing
the main window hides it; use **Quit** in the tray to exit the app and its owned
backend. A shortcut requested during transcription does not interrupt inference.

## Privacy and offline use

- Microphone audio is processed in memory. The app does not save recordings as
  audio files or send them to a cloud transcription service.
- Inference uses a complete local model snapshot. Model downloads from Hugging
  Face use the network when you explicitly request them; cached models can be
  used offline.
- Settings, the last five transcripts and rotating logs live in
  `C:\local-dictation`, separate from the source and installed binaries.
- Transcript text is omitted from logs by default. Local history, clipboard
  contents and exported files still contain your text. Treat them as personal
  data when sharing files or diagnostics.
- The application has no telemetry or analytics integration. Fonts and icons
  are bundled with the desktop interface.

Private settings, transcripts, exports, credentials, model caches and generated
build output must stay out of Git. See the [privacy review and release gates](docs/release-preparation.md)
for the repository scan and historical cleanup still required before publishing.

## Build from source

Development requires Windows, Python, Node.js/npm and the Rust MSVC toolchain.
Python 3.12 is the verified development environment. Run setup from the
repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-build.txt
cd desktop
npm ci
npm run tauri dev
```

Debug prefers a generated Python sidecar when present, otherwise the root
`.venv` and `backend/bubble_dictate.py`. Release builds require the sidecar.
`npm run dev` from `desktop/` previews the interface with synthetic data; it
cannot verify native windows, microphone input, global shortcuts or paste.

### Windows installer

The default GPU build includes pinned CUDA libraries. Install their separate
requirements from the repository root, then package from `desktop/`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-cuda.txt
cd desktop
npm run tauri:build
```

The installer is created under
`desktop/src-tauri/target/release/bundle/nsis`. Building does not install the app
or publish a release. CUDA libraries are installed once in `cuda/`, outside the
sidecar's one-file archive. They make the GPU installer substantially larger;
neither build variant includes speech models or a development environment.

The build wrapper remaps compiler source paths, checks both executables for
personal build paths and keeps packaging temporary files in ignored `build/`.
For a CPU-only installer, use the same wrapper without CUDA resources:

```powershell
# repository root
.\scripts\build-desktop.ps1 -CpuOnly
```

Python resolution is constrained by `backend/requirements-lock.txt`; optional
CUDA dependencies have their own lock. JavaScript and Rust dependency versions
are recorded in their lockfiles.

### Checks

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
```

The latest reliability fixes cover bubble visibility updates and nonblocking
shortcut dispatch. Automated and process-level checks are documented in the
[verification report](docs/verification.md). Physical bubble clicks and dragging,
OS shortcut reliability, real dictation/paste and clean-machine installation
still need interactive acceptance; automated checks do not prove those cases.

## Repository and architecture

```text
local-dictation/
  backend/               Python audio, inference, persistence and local bridge
    tests/               Python unit tests
  desktop/               React/TypeScript interface and tests
    src-tauri/           Rust shell, native windows, tray and Windows packaging
  scripts/               Windows launch, build and shortcut utilities
  docs/                  Architecture, audits, verification and release gates
    history/             Historical notes and design references
```

- [Architecture and data flow](docs/architecture.md)
- [Baseline audit](docs/audit.md)
- [Implementation plan](docs/implementation-plan.md)
- [Implementation status](docs/implementation-status.md)
- [Bubble and shortcut fixes](docs/bubble-shortcut-fix.md)

`LOCAL_DICTATION_DATA_DIR` selects a separate data profile for isolated local
checks. Profiles share the loopback control port, so they cannot run concurrently
with an existing backend on that port.

`scripts/start-bubble.bat` launches the legacy Python interface. The shortcut
scripts manage that interface's shortcuts and should only be run when wanted.
Historical notes describe older versions and do not override current source.
