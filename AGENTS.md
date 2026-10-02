# Local Dictation working guidance

Read the root README and `docs/architecture.md` before changes. Current findings
and proposed fixes live in `docs/audit.md` and `docs/implementation-plan.md`.
Notes under `docs/history` are historical evidence.

## Structure and checks

- Python modules live in `backend/`; preserve their existing names and imports.
- From `backend/`: `..\.venv\Scripts\python.exe -B -m unittest discover -s tests`.
- React source and tests live in `desktop/src/`. From `desktop/`:
  `npm test -- --run`, `npm run typecheck`, `npm run lint`, `npm run build:frontend`.
- Rust lives in `desktop/src-tauri/src/`. From `desktop/src-tauri/`:
  `cargo fmt --check`, `cargo test --locked`.
- From `desktop/`, build a Windows installer with `npm run tauri:build`.
- Derive source paths from the repository. The existing `C:\local-dictation`
  runtime-data location is a compatibility constraint.

## Constraints

Preserve offline inference, local data and independently owned backends. Keep
browser mocks distinct from native evidence. Use existing interfaces and
libraries; do not split the legacy runtime or introduce infrastructure merely
to make an audit appear organized. Keep dependencies, generated output, logs,
settings and transcript history out of tracked source.

Do not run shortcut installation, app installation, real recording, model
downloads, publication or Git commits as incidental validation. Verify native
user-facing fixes in the app when focus, windows, audio, hotkeys or ownership
matter.
