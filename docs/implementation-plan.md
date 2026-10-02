# Local Dictation implementation plan

**Goal:** Fix the evidenced defects while retaining one understandable Windows local-dictation application.

Execution results and evidence boundaries are in [verification.md](verification.md)
and [implementation-status.md](implementation-status.md). This document retains
the original task decomposition rather than claiming its proposed checks all ran.

**Architecture:** Keep the current Python runtime, typed React bridge, newline loopback control protocol and Tauri shell. Add only narrow persistence/process/state changes needed for the failures. No backend rewrite, transport replacement, state framework, export database, updater, plugin system or speculative decomposition.

**Stack:** Python 3.12 development environment with faster-whisper/CTranslate2 and existing Tk scheduling; React/TypeScript/Vite; Rust/Tauri 2; Windows x64/PyInstaller/NSIS. Exact installed dependency evidence is in the audit; pin/update only through validated work.

**Specification:** [Audit](audit.md), checked 2026-10-02 at `462ce340`. The cleanup is already performed. Everything below is proposed implementation, not a completed fix or a promise that all possible issues disappear.

## Working rules and completion criteria

Preserve Git history, the existing C:\\local-dictation data paths, five-entry history, local-only inference and independent backend ownership. Apply one vertical behavior at a time, using real functions with fake I/O for focused regressions rather than tests that mirror implementation. Keep browser mock evidence separate from native evidence. Do not run device capture, external paste, installation or publication incidentally.

A task closes only when its failure case passes, relevant existing checks pass, its diff is reviewed and required native behavior is observed or explicitly remains open. No percentage, time estimate or perfect-behavior guarantee is asserted. A passed unit suite alone does not close native ownership/focus/GPU acceptance.

## Execution order

| Order | Task | Outcome |
| --- | --- | --- |
| 1 | T01 | Service remains recoverable |
| 2 | T02 | Persistence does not destroy/restore prior data |
| 3 | T03 | Offline models and settings commit coherently |
| 4 | T04 | Successful text survives delivery failure |
| 5 | T06 | Native lifecycle owns only its managed tree |
| 6 | T05 | One paste reaches the intended writable target |
| 7 | T07 | Settings values and shortcuts are truthful |
| 8 | T08 | Pages/state recover without stale races |
| 9 | T09 | Retained controls perform real actions |
| 10 | T10 | Windows retain correct placement/visibility |
| 11 | T11 | Appearance agrees across views |
| 12 | T12 | Accessible controls and correct styles |
| 13 | T13 | Measured waste and unused scaffolding removed |
| 14 | T14 | Reviewed dependencies are repeatable |
| 15 | T15 | Actual packaged/native acceptance passes |

T02 precedes transactional settings/history changes. T01/T03 state contracts precede UI recovery. T06 precedes reliable process shutdown/packaging acceptance. T07/T09 decide which primitives remain before T13 pruning. These dependencies justify the order without a large parallel refactor.

## Tasks

### T01: Keep the bridge reachable and each request recoverable

**Findings:** A01, A02, A11.

**Files:** [backend/bubble_dictate.py](../backend/bubble_dictate.py#L1305), [backend/control_bridge.py](../backend/control_bridge.py#L73), [backend/config.py](../backend/config.py#L95), [backend/tests/test_control_bridge.py](../backend/tests/test_control_bridge.py#L1), [backend/tests/test_bubble_dictate.py](../backend/tests/test_bubble_dictate.py#L1).

Create the hidden scheduling root/control service before model and microphone initialization. Initialize expensive resources on one worker and retain model/microphone errors in state. Bridge-ready and recording-ready are distinct: Settings, Models, health and shutdown work while recording is unavailable.

Require a string command before dispatch. Keep the existing 65,536-byte request limit; give accepted clients a bounded deadline and keep read/decode/route/write exceptions inside the per-client loop. Return structured useful errors. Add a bounded Rust connection/response path when T06 touches the proxy. Do not replace TCP or add a server framework.

Extend existing state with a loading flag and an operation error message, with explicit reset on a new accepted action. An error must not erase a previously valid transcript.

**Acceptance:** Use a temporary loopback port and fake resource initialization. Missing cache/microphone still permits settings, health, downloads and shutdown. After malformed command types, reset/write failure, no newline, malformed JSON and oversized input, a later valid request succeeds. No real device or the production port is needed for these tests.

### T02: Make persisted data durable and malformed input recoverable

**Findings:** A15, A17.

**Files:** [backend/settings.py](../backend/settings.py#L293), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L1103), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L1349), [desktop/src/lib/time.ts](../desktop/src/lib/time.ts#L1), [backend/tests/test_settings.py](../backend/tests/test_settings.py#L1), [backend/tests/test_bubble_dictate.py](../backend/tests/test_bubble_dictate.py#L1).

Use one narrow same-directory JSON replacement helper and separate locks for settings/history mutations. Write a temporary file, flush, replace atomically, and clean up only the helper's own abandoned temporary file on failure. Clear and append must share the same history lock through read/modify/replace. Keep the five-entry limit and C:\\local-dictation paths.

Handle decoding and malformed JSON without destroying the original file. Keep the service reachable with a visible recovery error. A fallback/default read must not silently authorize overwriting a corrupt original; require an explicit user save/recovery action. Return a safe Earlier label for null/invalid timestamps in the frontend.

**Acceptance:** Interleave clear/append and concurrent reads; previous deleted entries stay deleted. Fail the replacement and confirm the last valid file survives. Invalid UTF-8/JSON settings/history remain recoverable and unchanged on disk after launch. Render invalid, null and valid timestamps without an exception.

### T03: Apply settings and model/device changes as one controlled transaction

**Findings:** A03, A04, A16, A20, A21, A34.

**Files:** [backend/bubble_dictate.py](../backend/bubble_dictate.py#L1030), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L1590), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L3202), [backend/settings.py](../backend/settings.py#L183), [desktop/src/bridge/types.ts](../desktop/src/bridge/types.ts#L106), [desktop/src/bridge/pythonBridge.ts](../desktop/src/bridge/pythonBridge.ts#L1), [desktop/src/bridge/mockBridge.ts](../desktop/src/bridge/mockBridge.ts#L1).

Proposed interface: saveSettings(patch: Partial<Settings>): Promise<Settings>. Retain the set-settings command/envelope, merge only supplied recognized fields into current settings, validate, atomically persist, then publish side effects. Reject invalid hotkeys/settings with a useful message. Run hotkey changes only when that field actually changes; dragging updates bubble_position only.

For model/device fields reserve a single reload, capture a complete candidate and previous working configuration, and gate incompatible recording/settings actions while loading. Load the candidate without publishing it; on success persist and atomically swap the model/configuration. On load/save failure retain the working model/configuration and report the failed request. Never let a late worker commit another request's result. Release superseded model references after the swap. Keeping the old model during construction can increase peak memory; verify this on supported hardware and fail safely if a candidate cannot fit.

Resolve one effective cache root for all actions. Reuse complete local-folder validation for the concrete cached snapshot before inference, including config/model/tokenizer/vocabulary files. Pass that validated path with local-only behavior. Explicit download is the sole online acquisition path. Share one locked per-model download admission/status path between native and legacy UI.

**Acceptance:** Reverse two requested reload completions and attempt recording during loading; only the accepted operation commits. Force CUDA warmup and disk-write failure from a working CPU session; saved/current/next-launch configuration agree. Partial snapshots cannot invoke tokenizer remote lookup. A nondefault cache root supports availability, load, sizes and path actions. Duplicate requests create one download worker; position-only saves do not recreate the hotkey listener.

### T04: Preserve inference results and literal transcript content

**Findings:** A05, A06, A11, A14.

**Files:** [backend/bubble_dictate.py](../backend/bubble_dictate.py#L1473), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L1956), [backend/config.py](../backend/config.py#L74), [backend/tests/test_bubble_dictate.py](../backend/tests/test_bubble_dictate.py#L1).

Treat a successful inference result as durable application output before optional delivery. Update latest_transcript and attempt history persistence independently of clipboard/paste. If history or clipboard fails, retain the text and expose the distinct failure; do not relabel successful inference as failed. Carry the recording operation ID through completion and ignore stale delayed resets.

Default cleanup must preserve literal punctuation and ordinary words. Remove blanket spacing after periods/commas and ambiguous word-to-punctuation replacements. Keep only conservative whitespace cleanup by default. If retaining spoken-punctuation interpretation for compatibility, make it an explicit opt-in configuration flag; it must not guess whether ordinary prose is a command.

**Acceptance:** With clipboard contention or a history-write failure, completed text remains visible/copyable and delivery can be retried. Exercise inference failure, empty result and immediate next recording; old workers cannot overwrite the new state. Preserve decimals, grouped numbers, versions, email addresses, URLs, abbreviations and prose containing punctuation words.

### T06: Own native backend launches and shutdown correctly

**Findings:** A07, A08, A09, A10.

**Files:** [desktop/src-tauri/src/lib.rs](../desktop/src-tauri/src/lib.rs#L148), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L1006), [backend/control_bridge.py](../backend/control_bridge.py#L73), [backend/tests/test_control_bridge.py](../backend/tests/test_control_bridge.py#L1), [desktop/src/bridge/BackendStatusProvider.tsx](../desktop/src/bridge/BackendStatusProvider.tsx#L1), [desktop/src/pages/HelpAboutPage.tsx](../desktop/src/pages/HelpAboutPage.tsx#L1).

Reserve one start/stop/restart in the existing manager before releasing its lock. Assign each launch a unique identifier, pass it to the backend, and return an optional launch_id in health. Preserve the existing scalar backend-owner response. This identifies ownership; it is not a caller-authentication credential. Preserve compatibility with independent/legacy responses by treating an unmatched launch as independent, never managed. Consume matching sidecar exit events and retain launch/exit/protocol errors. Reuse one health result per attempt.

Move blocking socket/process waits to a blocking worker with brief state locks. Pending lifecycle buttons must be disabled. An API health response proves reachability, not that the model is ready to record. Bound connection and response reads, and reject incompatible protocol versions explicitly.

For Stop/Quit, verify launch ownership and send a distinct shutdown-owned-backend command carrying the expected launch_id. The receiving backend must validate the identifier before scheduling quit. A separate command ensures older backends reject it rather than ignore extra arguments; a replaced process on the port cannot accept a stale ownership check. Wait a bounded time for the owned worker/tree to exit. If necessary terminate only that verified tree. Own Windows descendants from creation with a per-launch job object attached before the one-file worker can escape; a small Windows-specific launch helper is justified if the shell plugin cannot guarantee that ordering. Keep this process helper local to the native shell rather than creating a general process framework. Do not equate the PyInstaller parent PID to the health worker PID or kill processes by name. Restart begins only after the old owned session is gone.

**Acceptance:** Use controlled children for event/ownership tests: failed startup, exit before health, crash after readiness, simultaneous starts, slow/unresponsive health and restart during loading. Exactly one managed launch exists. An independent server on the port is never shut down. Native acceptance must prove no owned worker, microphone handle or mutex remains after Stop/Quit, and that UI interaction stays responsive during delayed failures.

### T05: Deliver one pending paste to the intended writable target

**Findings:** A12, A13, A14, A25.

**Files:** [backend/bubble_dictate.py](../backend/bubble_dictate.py#L4103), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L4138), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L4182), [desktop/src-tauri/tauri.conf.json](../desktop/src-tauri/tauri.conf.json#L26), [desktop/src-tauri/src/lib.rs](../desktop/src-tauri/src/lib.rs#L1), [backend/tests/test_bubble_dictate.py](../backend/tests/test_bubble_dictate.py#L1).

Claim a pending transcript once under the existing state lock and attach its operation ID. On failed delivery restore retry readiness only if that operation is still current. Keep Tk scheduling outside the lock and suppress stale completion repaints.

Make native pointer utility windows nonactivating so the bubble preserves the external editor's focus. Retain equivalent keyboard-accessible operations in main. Exclude every owned native window from backend mouse-target handling using reliable native window/process identity rather than hidden Tk coordinates. Recheck the target identity and writable UI Automation capability immediately before injecting paste after the delay. Unsuitable clicks/focus changes must preserve pending text.

**Acceptance:** Queue two clicks before workers execute: one delivery only. Reject a paste and retain retry text. Native acceptance covers editable inputs, readonly documents, title bars, desktop/tray clicks, own app buttons and focus switching during delay. Bubble pointer actions preserve the external target; main remains keyboard operable.

### T07: Make settings forms truthful and safe to submit

**Findings:** A16, A18, A19, A31.

**Files:** [desktop/src/pages/SettingsPage.tsx](../desktop/src/pages/SettingsPage.tsx#L19), [desktop/src/fixtures/settings.ts](../desktop/src/fixtures/settings.ts#L17), [desktop/src/components/settings/HotkeyInput.tsx](../desktop/src/components/settings/HotkeyInput.tsx#L1), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L3992), [desktop/src/__tests__/settings-page.test.tsx](../desktop/src/__tests__/settings-page.test.tsx#L1).

Send only edited intended fields through the T03 patch contract. Disable form editing/Save during submission, prevent duplicate submits, and display errors without marking the form saved. Align language and text-format values exactly with backend contracts while retaining human-readable labels. Existing Persian and Markdown (.md) must render.

Keep Tab/Shift+Tab as navigation; normalize Space/Enter and supported special/function keys to the backend grammar. Preserve Ctrl/Alt/Shift/Meta consistently, including legacy character capture. Reject invalid syntax before saving and show the listener validation result rather than only logging it.

Remove Panel Opacity from the native Settings page because there is no corresponding native translucency implementation. Keep the backend/legacy opacity contract and 70-100 bounds intact. This deliberately removes a misleading control instead of adding an unrequested window-composition subsystem.

**Acceptance:** Every offered value round-trips. Open Settings, move the bubble/add a model elsewhere, then save language: unrelated changes survive. Delayed/double saves lose no edit. Keyboard users leave the hotkey field normally. Ctrl+Space, Ctrl+Enter, Ctrl+Shift+D, function/arrow keys and disabled shortcuts have valid capture/save behavior; activation is a later native gate.

### T08: Recover page data and serialize existing state polling

**Findings:** A22, A23, A24, A34.

**Files:** [desktop/src/bridge/pythonBridge.ts](../desktop/src/bridge/pythonBridge.ts#L118), [desktop/src/bridge/types.ts](../desktop/src/bridge/types.ts#L1), [desktop/src/pages/HistoryPage.tsx](../desktop/src/pages/HistoryPage.tsx#L1), [desktop/src/pages/ModelsPage.tsx](../desktop/src/pages/ModelsPage.tsx#L1), [desktop/src/pages/SettingsPage.tsx](../desktop/src/pages/SettingsPage.tsx#L1), [desktop/src/components/dictation/QuickHistoryPopoverSurface.tsx](../desktop/src/components/dictation/QuickHistoryPopoverSurface.tsx#L23), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L984).

Share one state subscriber/poll loop per bridge instance/webview. Schedule the next read only after the current read finishes; stop when no subscribers need it. Expose connection failure separately from the last valid operation state. Do not create a new frontend state library or replace polling with a transport rewrite.

Use backend readiness plus loading/error/pending state to gate page reads and recording controls. Keep last successful data during transient errors, provide Retry, and ignore obsolete responses, including model-order changes. A download remains pending through a transient status error.

Refresh quick history on its existing show/placement event and main History on explicit navigation/show and completed history mutations. Add a lightweight history_revision field to existing backend state, incremented only after a successful append/clear, so repeated identical transcripts still trigger refresh. This is an additive protocol field, not a new event service. Pause unnecessary polling while utility surfaces are known hidden and fetch immediately when shown.

**Acceptance:** Enter all data pages during startup; they recover without navigation. Fail one download poll, then recover to its actual result. Deferred reads never overlap in a stream or deliver stale state. Disconnect is visible and reconnect recovers. New/identical dictations and Clear update an already-open main page and a reopened persistent popover.

### T09: Connect real actions and remove misleading production scaffolding

**Findings:** A32, A33, A34, A38, A39.

**Files:** [desktop/src/pages/RecordingPage.tsx](../desktop/src/pages/RecordingPage.tsx#L1), [desktop/src/pages/SettingsPage.tsx](../desktop/src/pages/SettingsPage.tsx#L1), [desktop/src/pages/ExportsPage.tsx](../desktop/src/pages/ExportsPage.tsx#L1), [desktop/src/pages/HelpAboutPage.tsx](../desktop/src/pages/HelpAboutPage.tsx#L1), former `desktop/src/components/exports/ExportRow.tsx` (removed by this task), [desktop/src/lib/clipboard.ts](../desktop/src/lib/clipboard.ts#L1), [desktop/src/bridge/mockBridge.ts](../desktop/src/bridge/mockBridge.ts#L1), [desktop/src/app/DesktopApp.tsx](../desktop/src/app/DesktopApp.tsx#L1), [desktop/index.html](../desktop/index.html#L1).

Pass existing navigation to Open History. Add a native folder chooser with cancel/error handling; the standard Tauri dialog integration is the narrowest native picker route and its dependency/capability changes must be limited to this action. Browser mode must state that the native picker is unavailable.

Remove fixture export rows and their inert per-row actions from production. Retain working Export All TXT/MD and display the actual returned path/result. Remove the unsupported update-check control rather than building an updater. Remove or make noninteractive the labeled preview's inert footer; do not duplicate another interactive app within Recording.

Route copy actions through awaited/caught clipboard behavior and notify success only on completion. Gate Recording/bubble actions using the pending/busy contract from T03/T08. Derive native version from Tauri metadata, use runtime-appropriate descriptions/recovery directions, and replace missing favicon/default HTML title with existing app branding.

Make browser mocks obey the same value/result/state contracts. Unsupported native filesystem actions must identify the limitation, not return invented success. Clear stale mock timers when the operation changes; custom-model path copy must resolve a real fixture source or reject.

**Acceptance:** Every retained enabled control has an observable result. Browse chooses a path and cancel preserves it. Fresh production Exports shows no invented files. Copy rejection shows no success toast/unhandled rejection. Version reads 0.1.0 from native metadata; native screens do not claim mock operation. Contract tests cover model paths, export results and repeated busy clicks in the browser mock.

### T10: Restore and retain native windows with correct monitor geometry

**Findings:** A26, A27, A28.

**Files:** [desktop/src-tauri/src/lib.rs](../desktop/src-tauri/src/lib.rs#L350), [desktop/src-tauri/tauri.conf.json](../desktop/src-tauri/tauri.conf.json#L16), [desktop/src/components/dictation/TauriBubbleController.tsx](../desktop/src/components/dictation/TauriBubbleController.tsx#L1), [desktop/src/components/dictation/FloatingBubbleSurface.tsx](../desktop/src/components/dictation/FloatingBubbleSurface.tsx#L73), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L4359), [desktop/src/__tests__/stage6-tauri-bubble-device.test.tsx](../desktop/src/__tests__/stage6-tauri-bubble-device.test.tsx#L1).

Never persist the hidden API root as a native bubble position. Restore saved native position only after settings are available, using the monitor containing the saved point. Clamp to a valid work area when that monitor has disappeared. Tray Show preserves a valid current position instead of resetting it; drag writes only the position patch.

Use actual outer physical window sizes and physical work areas for placement. Convert physical tail offsets to CSS logical units using the popover scale factor, and recompute after monitor/DPI changes. Keep the existing placement helpers rather than introducing a geometry framework.

Prevent OS close from destroying persistent bubble/popover windows; hide instead. Unminimize main before Show app, navigation from popover and second-instance activation.

**Acceptance:** Existing pure geometry tests cover saved secondary-monitor points, removed monitors and bounds with physical sizes. Native acceptance covers 100/125/150/200% scaling and mixed-DPI drag, safe screen edges, preserved position after restart/show, main minimization, utility-window Alt+F4, and reopen. Recheck the 410 x 300 long-entry popover visually; do not assume the unconfirmed clipping hypothesis is a defect.

### T11: Synchronize native appearance without competing stores

**Findings:** A30.

**Files:** [desktop/src/theme/theme-provider.tsx](../desktop/src/theme/theme-provider.tsx#L1), [desktop/src/theme/theme-presets.ts](../desktop/src/theme/theme-presets.ts#L1), [desktop/src/app/AppProviders.tsx](../desktop/src/app/AppProviders.tsx#L1), [desktop/src/theme/use-theme.ts](../desktop/src/theme/use-theme.ts#L1), [desktop/src/__tests__/theme-provider.test.tsx](../desktop/src/__tests__/theme-provider.test.tsx#L1).

Use the existing frontend local-storage mode/preset as native appearance authority, preserving existing preferences. Backend theme remains the legacy Tk setting and is excluded from native field patches. Broadcast user appearance changes through the existing native event mechanism and apply them in all persistent views without re-emitting stale state. Browser views can use storage events. Persist only actual preference changes, not an old captured preference during an OS-theme callback.

Pass resolved light/dark appearance to the active Sonner toaster. Do not activate the unused next-themes provider or add a second appearance store.

**Acceptance:** Change theme/preset in one surface; other persistent views update immediately. Restart and system-theme changes retain explicit choices/presets. A stale receiving view never overwrites a newer preference. Toast appearance matches the application.

### T12: Correct accessibility and rendered style defects

**Findings:** A35, A36, A37.

**Files:** [desktop/src/components/history/HistorySearch.tsx](../desktop/src/components/history/HistorySearch.tsx#L1), [desktop/src/components/shell/Sidebar.tsx](../desktop/src/components/shell/Sidebar.tsx#L1), [desktop/src/components/models/ModelOrderToggle.tsx](../desktop/src/components/models/ModelOrderToggle.tsx#L1), [desktop/src/components/models/ModelCard.tsx](../desktop/src/components/models/ModelCard.tsx#L21), [desktop/src/components/ui/select.tsx](../desktop/src/components/ui/select.tsx#L78), [desktop/src/globals.css](../desktop/src/globals.css#L5).

Give retained inputs explicit accessible names, navigation aria-current, ordering selected/pressed semantics and recording status an appropriate live announcement. Preserve sensible focus order and visible focus styling.

Replace invalid select arbitrary values with explicit var(...) syntax. Define destructive foreground in light/dark tokens. Add a readable dark Installed badge foreground using existing palette choices. Keep the current design system; no redesign is needed.

**Acceptance:** Use role/name assertions for retained controls and a keyboard/screen-reader smoke test. Inspect rendered dropdown bounds near edges with a large option list. Measure normal text contrast across supported light/dark presets, including destructive states and Installed; minimum 4.5:1 for normal informational text.

### T13: Remove measured backend waste and unused primitives

**Findings:** A40, A43.

**Files:** [backend/bubble_dictate.py](../backend/bubble_dictate.py#L278), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L952), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L1778), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L1909), [backend/config.py](../backend/config.py#L103), former `desktop/src/components/ui/sonner.tsx` (removed by this task), [desktop/package.json](../desktop/package.json#L1).

Transfer ownership of captured chunks into the transcription operation and release global/local audio references in completion/error paths. Derive model display sizes from already fetched model details so each repository is scanned once per refresh. Avoid a metadata cache unless later measurement proves one is needed.

Use standard-library rotating aggregate logging with a documented finite retention limit; suppress routine successful state/health polling and recurring audio-callback disk output. Preserve useful failure/transition diagnostics and the no-transcript-text default. Prune only app-owned old log files under the validated runtime log directory. Proposed retention values should be chosen/documented during implementation, not presented as measured optimal values.

After the action/accessibility fixes, remove the eleven still-unreachable wrapper files and matching unused dependencies, including next-themes if still unused. Keep select/dialog primitives actually used by the application or the fixes. Regenerate the npm lock through the package manager.

**Acceptance:** Synthetic long-recording completion releases retained chunks on success/error. A model-list probe counts one size scan per repository. Repeated idle polls have bounded log growth; diagnostics remain useful and omit transcript text. Import reachability, lint, frontend build/tests verify pruning. Measure actual microphone latency/dropouts before asserting a performance improvement.

### T14: Resolve advisory matches and make dependency inputs repeatable

**Findings:** A41, A42.

**Files:** [backend/requirements.txt](../backend/requirements.txt#L1), [backend/requirements-build.txt](../backend/requirements-build.txt#L1), [desktop/package.json](../desktop/package.json#L1), [desktop/package-lock.json](../desktop/package-lock.json#L1), [desktop/src-tauri/Cargo.toml](../desktop/src-tauri/Cargo.toml#L1), [desktop/src-tauri/Cargo.lock](../desktop/src-tauri/Cargo.lock#L1), [desktop/src-tauri/tauri.conf.json](../desktop/src-tauri/tauri.conf.json#L57), [docs/audit-evidence/osv-advisories.json](audit-evidence/osv-advisories.json#L1).

Triage the saved exact versions/affected ranges against actual Windows runtime/build usage. Update compatible direct/transitive dependencies through pip/npm/Cargo, never by hand-editing locks or using forced major upgrades. Prioritize fixes for reachable runtime/import paths and exposed development tooling. Re-query advisories after resolution; retain evidence for genuine upstream constraints. Maintenance notices and non-Windows crates must not be mislabeled as shipped exploits.

Build a clean minimal Python environment from declared requirements, excluding unrelated installed extras. Save exact reviewed runtime/build resolutions as simple requirements lock files and document their regeneration; no new package manager is necessary. Keep optional CUDA dependencies explicit. Verify the supported Python/Node/Rust toolchain versions rather than chasing a framework upgrade.

Set/test a restrictive local-asset CSP against the actual Tauri IPC, inline style needs and bundled fonts. Document the existing trusted-local-process loopback boundary. Keep bind address local and do not claim ownership identifiers add caller authentication. A change to that trust model is a distinct scoped requirement.

**Acceptance:** Fresh locked installs, pip check, npm audit (including omit-dev), and target-aware OSV/Cargo recheck. All applicable regression suites/builds pass after each ecosystem's update. CSP allows the intended local app and blocks prohibited external script connections; no new remote asset dependency appears.

### T15: Complete packaged GPU support and final native release verification

**Findings:** A29, A43; acceptance for all findings.

**Files:** [scripts/build-backend-sidecar.ps1](../scripts/build-backend-sidecar.ps1#L1), [backend/bubble_dictate.py](../backend/bubble_dictate.py#L1590), [desktop/package.json](../desktop/package.json#L9), [desktop/src-tauri/tauri.conf.json](../desktop/src-tauri/tauri.conf.json#L8), [README.md](../README.md#L1), [docs/audit.md](audit.md#L1).

Collect the required installed NVIDIA runtime DLLs into the frozen sidecar and teach the existing CUDA path setup to resolve those frozen directories. Verify CTranslate2/PortAudio assets remain included and that Python architecture matches the Windows target before naming the sidecar. Measure and document the resulting package size; do not ship model weights or development environments.

Keep one frontend build invocation: tauri:build should build the sidecar, then invoke Tauri, whose existing beforeBuildCommand builds the frontend. Do not build frontend assets twice. Use the package-manager/locked build workflows and update documentation.

Rebuild release/NSIS with adequate compiler memory headroom. Current failure is memory allocation in a Windows dependency, not evidence for changing app code or upgrading the compiler. Preserve the failed evidence and record an actual successful result before calling packaging verified.

Perform the native acceptance matrix below on the actual candidate, with explicit device/data/installation authority when required. The already installed June app and browser preview are not substitutes. Update the audit with exact fixed findings and test evidence, keeping unverified items open.

**Acceptance:** Inspect the fresh archive for required GPU DLLs. On a clean Windows x64 environment verify startup without the source tree/venv, cached offline CPU recording, auto-device fallback and explicit CUDA on compatible hardware, empty-cache recovery, owned/independent lifecycle, focus/paste/hotkeys, multiwindow geometry and data survival. Building an installer does not authorize installing, publishing or bumping release metadata.

## Validation workflow

Run the narrow failure regression while changing that behavior. Broaden only when a failure, new change or cross-boundary risk warrants it. Permanent tests should invoke real application functions/components with controlled I/O; AST extraction was an audit technique, not the desired product test architecture.

At each completed affected area and once as the final gate:

```powershell
# backend/
..\\.venv\\Scripts\\python.exe -B -m unittest discover -s tests
..\\.venv\\Scripts\\python.exe -m pip check

# desktop/
npm test -- --run
npm run typecheck
npm run lint
npm run build:frontend

# desktop/src-tauri/
cargo fmt --check
cargo test --offline --locked

# desktop/ with sufficient memory for the native compiler
npm run tauri:build
```

Do not repeat full suites after every minor edit. A fresh locked install and release build are final reproducibility gates. A successful compile or browser preview does not prove native behavior. Keep failed check output and exact blockers; never weaken assertions to obtain a green report.

## Native acceptance matrix

| Scenario | Required observation |
| --- | --- |
| No models/no microphone | Recovery pages and health work; recording explains the missing resource |
| Backend crash/start failure | Useful cause retained; Retry starts once; no endless Starting |
| Independent backend | App Stop/Quit does not terminate it or its descendants |
| Managed Stop/Quit/Restart while loading/recording | Owned worker/tree exits, mic/mutex released, one replacement on Restart |
| Clipboard busy/paste denied | Completed text/history preserved where persistence succeeds; retry remains available |
| Rapid click/new recording | One paste per operation; old workers do not repaint new recording |
| Pointer utility windows | External editor focus preserved; own controls never consume pending paste |
| Readonly/noneditable/focus-changing target | No unwanted injection or loss of pending text |
| Settings/model/device failure | Current and saved working configuration agree; explicit errors, no silent substitutions |
| Global shortcuts | Supported modifiers/special keys activate once; Tab navigation remains available |
| Persistent windows | New history/theme visible after hide/show; close and minimized main recover |
| Multiple monitors/scaling | Saved placement preserved and bounds/tail correct at 100/125/150/200% and mixed DPI |
| Clean packaged CPU machine | App starts without source/venv and uses complete local models offline |
| Compatible GPU machine | Required frozen DLLs resolve; auto fallback and explicit CUDA behave as described |
| Long session | Captured buffers released, model scans bounded, logs capped; actual dropouts/latency measured |

Use non-sensitive test text and controlled destinations when native tests are authorized. Restore any deliberately changed user preference. Record which installer/hash and environment were actually exercised. If GPU/multi-monitor/device access is unavailable, leave those exact checks open instead of claiming general release readiness.

## Scope and rollout

Keep the organized folder as the source of record. Apply compatibility-preserving additive fields and patch semantics within the existing command envelope. Full old-client settings objects still validate as complete requests; omitted fields must survive. Legacy Python controls use the same transaction/download/persistence helpers, while native-only appearance/position remain distinct. Corrupt data is preserved for explicit recovery, never silently migrated away.

Review each final diff for unrelated edits, accidental generated files, secrets/transcript contents, offline violations, listener/worker leaks and unintended runtime-data changes. Keep archived material until the owner chooses its retention. No commit, push, release, installation or deletion follows automatically from this plan.

No new infrastructure is required. The justified additions are a narrow atomic-write helper, managed launch/tree ownership, small additive state fields, an actual native directory picker and focused regression coverage. Dependency updates/pruning and a compatible CSP are bounded maintenance. Native translucency and an updater are deliberately excluded because removing their misleading controls resolves the current defect without creating new products.
