# Local Dictation audit

Checked 2026-10-02 against commit `462ce3401ab6ab59cd1bdbc0ac2baae362ca1405` and the organized working tree. This report is an audit, not a claim that all possible bugs have been found or that native behavior is proven.

**Implementation follow-up:** The findings below describe the pre-fix baseline,
including its historical line locations and dependency results. Current changes,
checks and remaining native acceptance gaps are recorded in
[verification.md](verification.md) and [implementation-status.md](implementation-status.md).
Do not interpret the baseline's failed checks or proposed remedies as the state
of the implemented working tree.

## Outcome and current version

The final active source folder is the repository root. At this baseline audit, the native app version was **0.1.0**; the private frontend package used 0.0.0. Local master was 11 commits ahead of the verified GitHub master `bf3fa3c`, with no newer remote commit found. HEAD was dated 2026-07-13. The installed June app had not been replaced and should not be treated as the rebuilt source. Current version and installed checks are recorded in [verification.md](verification.md).

| Recent commit | Change |
| --- | --- |
| 462ce34 | Startup and close-to-tray behavior |
| bf71cfe | Device mode and model UI |
| 66f98a5 | Native bubble and quick history |
| 0240a3d | Packaged backend ownership |
| eb8bd2e | Control router separation |

The initial cleanup preserved that history without commits, staging, push, PR,
installation or publication. The subsequent authorized reliability implementation
is local on `reliability-fixes`; its current outcome is recorded in the follow-up.

## Folder cleanup completed

```text
local-dictation/
  backend/                 Existing Python modules and requirements
    tests/                 Existing Python tests
  desktop/                 React interface, tests and build configuration
    src-tauri/             Native Rust shell and packaging
  scripts/                 Launch, shortcut, log and sidecar tools
  docs/
    architecture.md
    audit.md
    implementation-plan.md
    audit-evidence/        Dependency/check evidence, no personal transcripts
    history/               Older notes and design references
  AGENTS.md
  README.md
```

The duplicate Tauri checkout, earlier local data copies, prototype files and stale build cache were preserved in a private archive outside the source folder. A complete pre-cleanup Git-directory backup was retained there. Main worktree registration is now the single canonical source; archived copies are recovery material. Normal ignored dependencies/build output remain generated and reproducible, rather than source.

Python modules/tests and Windows tools were grouped without renaming their established APIs. Launch/build scripts derive source paths from this repository; Rust debug fallback uses `backend/bubble_dictate.py` and the root `.venv`. The shell log action now resolves the existing runtime log. Historical notes are explicitly historical.

Actual runtime settings/history remain at **C:\\local-dictation**. They were not moved, cleared or rewritten. Test diagnostics appended to logs; the installed application and model cache were not changed.

## Coverage and evidence boundaries

The review covers Python runtime/settings/router, recording/inference/paste scheduling, persistence, model management/offline paths, Rust lifecycle/windows/proxy/capabilities, React pages/components/bridge/themes/mocks, tests, build/dependency configuration, recent/all Git refs, both source copies, runtime metadata and relevant error logs. No CI workflow exists in the reviewed tree.

Earlier project chats were reviewed as dated context. Their older source paths and successful installer claims are historical, not fresh verification. Current source and checks take precedence. Generated design references are not alternative implementations. No newer source checkout was found in the reviewed project context. Private chat names and local archive paths are omitted from this public report.

Evidence labels are deliberate:

- **Reproduced**: execution of the current function/component with controlled fake dependencies, or browser DOM interaction. These probes do not establish real microphone, Windows hook or native process behavior.
- **Source-confirmed**: a reachable implementation/configuration defect with a stated trigger, not a completed native acceptance test.
- **Measured**: observed file/archive contents, dependency responses or rendered CSS geometry/colors.
- Native focus, editable-target injection, global hotkeys, DPI transitions, GPU inference, utility-window OS close and clean-machine installation remain acceptance gaps.

The 410 x 300 quick-history surface was rendered with three two-line synthetic entries. Footer buttons ended at about y=292.46 inside the 300 px viewport. The proposed footer-clipping defect was **not confirmed**. Its background/padding overflow needs a native visual check before calling it a functional bug. No microphone capture, model download, real clipboard write or input injection was performed.

## Findings and minimal remedies

P1 means data loss, unusable recovery or incorrect lifecycle ownership and should be fixed first. P2 means meaningful correctness/reliability/accessibility work. P3 means lower-priority efficiency, misleading scaffolding or maintenance. Priority is not an exploit severity score. Task IDs link each finding to the implementation plan.

### A01 [P1] Startup failures make recovery controls unavailable

**Evidence:** Source-confirmed. [backend/bubble_dictate.py:4683](../backend/bubble_dictate.py#L4683), [backend/bubble_dictate.py:4724](../backend/bubble_dictate.py#L4724).

The model and microphone initialize before the control service. Missing models, a failed model load, or a missing microphone can end startup, leaving Models and Settings unable to perform the recovery actions.

**Minimal remedy:** Start the scheduling root and bridge before resource initialization. Keep the service reachable, retain the initialization error, and refuse recording until ready. **Plan:** T01.

### A02 [P1] Malformed or stalled clients can stop the bridge

**Evidence:** Reproduced with fake clients. [backend/control_bridge.py:81](../backend/control_bridge.py#L81), [backend/control_bridge.py:108](../backend/control_bridge.py#L108), [backend/bubble_dictate.py:1305](../backend/bubble_dictate.py#L1305).

A list/object command raises TypeError before the router's exception boundary. Read/reset/send errors escape the per-client handler and terminate serving. Accepted clients have no deadline, so an incomplete request blocks the only serving thread. A request-size bound already exists; it does not solve the missing deadline.

**Minimal remedy:** Validate command types, enforce an accepted-client deadline, and contain exceptions within each request. Keep the existing bounded newline protocol. **Plan:** T01.

### A03 [P1] Incomplete cached models can bypass offline inference

**Evidence:** Reproduced with isolated filesystem/model/tokenizer mocks. [backend/settings.py:392](../backend/settings.py#L392), [backend/bubble_dictate.py:1542](../backend/bubble_dictate.py#L1542), [backend/bubble_dictate.py:1590](../backend/bubble_dictate.py#L1590).

Availability checks only model.bin. In installed faster-whisper 1.2.1, a missing tokenizer.json triggers Tokenizer.from_pretrained without forwarding local_files_only. No network lookup was performed in this audit; the fallback path was reproduced with mocks.

**Minimal remedy:** Resolve and validate the complete local snapshot, including config.json, model.bin, tokenizer.json and vocabulary files, before constructing inference. Pass that directory rather than an unresolved repo identifier. **Plan:** T03.

### A04 [P1] Model/device changes are not one coherent operation

**Evidence:** Reproduced with controlled worker ordering and failed CUDA warmup. [backend/bubble_dictate.py:1030](../backend/bubble_dictate.py#L1030), [backend/bubble_dictate.py:3202](../backend/bubble_dictate.py#L3202).

Independent reload workers read mutable global settings. Reversed completions left saved High Accuracy but loaded Fast. A failed explicit-CUDA change retains the previous CPU model while saving cuda and reporting an error device. Recording is not gated during reload.

**Minimal remedy:** Serialize reloads, capture the requested configuration, and publish/persist the complete model/device change only on success. Preserve the previous working configuration on failure. **Plan:** T03.

### A05 [P1] Transcript cleanup changes literal content

**Evidence:** Reproduced with the current cleanup function. [backend/bubble_dictate.py:1473](../backend/bubble_dictate.py#L1473).

Version 1.2.3 becomes 1. 2. 3; 1,000.50 becomes 1, 000. 50; email/URL punctuation is damaged. Ordinary prose containing period or comma is interpreted as a command.

**Minimal remedy:** Make default cleanup preserve literal content. Remove unconditional punctuation spacing and ambiguous word replacement; spoken-command interpretation must be explicit. **Plan:** T04.

### A06 [P1] Clipboard failure discards successful transcription

**Evidence:** Reproduced with a failing clipboard dependency. [backend/bubble_dictate.py:1995](../backend/bubble_dictate.py#L1995), [backend/bubble_dictate.py:2020](../backend/bubble_dictate.py#L2020).

Clipboard copying precedes history persistence inside the inference error boundary. A busy clipboard cleared latest_transcript and skipped history even though inference succeeded.

**Minimal remedy:** Publish and preserve the text before delivery. Separate history/clipboard/paste errors from inference errors; retain the result for retry. **Plan:** T04.

### A07 [P1] Exited sidecars remain marked owned and starting

**Evidence:** Source-confirmed. [desktop/src-tauri/src/lib.rs:160](../desktop/src-tauri/src/lib.rs#L160), [desktop/src-tauri/src/lib.rs:689](../desktop/src-tauri/src/lib.rs#L689).

Sidecar refresh does nothing and the CommandEvent receiver is discarded. A terminated sidecar leaves a populated child handle, and Retry can return starting without creating a replacement.

**Minimal remedy:** Consume exit events for the matching launch and clear only that launch's child. Retain the exit cause and allow a single retry. **Plan:** T06.

### A08 [P1] Ownership can be assigned to an independent backend

**Evidence:** Source-confirmed. [desktop/src-tauri/src/lib.rs:155](../desktop/src-tauri/src/lib.rs#L155), [desktop/src-tauri/src/lib.rs:451](../desktop/src-tauri/src/lib.rs#L451), [desktop/src-tauri/src/lib.rs:633](../desktop/src-tauri/src/lib.rs#L633), [desktop/src-tauri/src/lib.rs:787](../desktop/src-tauri/src/lib.rs#L787).

Owned means only that a child handle exists; health accepts whichever process currently occupies the port. A stale managed handle plus an independent server can make Stop/Quit send shutdown to that independent server.

**Minimal remedy:** Match health to the managed launch and use a distinct managed-shutdown command whose receiver verifies the expected launch identifier. Independent backends remain outside this manager's lifecycle ownership. **Plan:** T06.

### A09 [P1] One-file process shutdown can leave the Python worker alive

**Evidence:** Source-confirmed process-boundary defect; native reproduction pending. [scripts/build-backend-sidecar.ps1:71](../scripts/build-backend-sidecar.ps1#L71), [desktop/src-tauri/src/lib.rs:191](../desktop/src-tauri/src/lib.rs#L191), [desktop/src-tauri/src/lib.rs:451](../desktop/src-tauri/src/lib.rs#L451), [desktop/src-tauri/src/lib.rs:822](../desktop/src-tauri/src/lib.rs#L822).

PyInstaller one-file uses a parent and worker. Quit/Restart can acknowledge shutdown then kill only the parent immediately, with no worker-exit confirmation. The fallback also kills one process. Windows does not automatically terminate descendants.

**Minimal remedy:** Wait for graceful shutdown, then terminate only the verified managed process tree when needed. Own that tree from launch, including initialization before the bridge is ready. **Plan:** T06.

### A10 [P2] Lifecycle operations race, block UI work and lose causes

**Evidence:** Source-confirmed. [desktop/src-tauri/src/lib.rs:733](../desktop/src-tauri/src/lib.rs#L733), [desktop/src-tauri/src/lib.rs:741](../desktop/src-tauri/src/lib.rs#L741), [desktop/src-tauri/src/lib.rs:787](../desktop/src-tauri/src/lib.rs#L787), [desktop/src/pages/HelpAboutPage.tsx:88](../desktop/src/pages/HelpAboutPage.tsx#L88).

Start releases the manager before reserving a launch; overlapping starts can overwrite handles. Some health/stop/quit work is synchronous and holds the mutex across network waits. Spawn errors are not retained; protocol_version is not checked; several failures collapse to not-running/starting.

**Minimal remedy:** Reserve one lifecycle operation, perform waits outside short locks on a blocking worker, retain actual failures, and verify old-session exit before restart. Validate the compatible protocol. **Plan:** T06.

### A11 [P2] Runtime errors disappear from native state

**Evidence:** Reproduced with an inference exception. [backend/bubble_dictate.py:918](../backend/bubble_dictate.py#L918), [backend/bubble_dictate.py:984](../backend/bubble_dictate.py#L984), [backend/bubble_dictate.py:2020](../backend/bubble_dictate.py#L2020).

Native state derives status from three booleans. Inference, clipboard, paste and reload failures can affect only the hidden Tk bubble/logs; get-state returned idle after an injected inference failure.

**Minimal remedy:** Store an operation error and expose its message/status. Clear it on a defined subsequent action, without deleting a valid transcript. **Plan:** T01, T04, T05.

### A12 [P2] Pending paste is not claimed once and is lost on failure

**Evidence:** Reproduced with queued fake workers. [backend/bubble_dictate.py:4138](../backend/bubble_dictate.py#L4138), [backend/bubble_dictate.py:4211](../backend/bubble_dictate.py#L4211).

Two callbacks can dispatch two workers for the same transcript. The worker clears readiness before delivery and does not restore it after paste fails.

**Minimal remedy:** Claim one pending transcript under the existing lock, associate the claim with its operation, and restore retry readiness after failed delivery. **Plan:** T05.

### A13 [P2] Paste can consume text on an unsuitable or app-owned target

**Evidence:** Source-confirmed; real focus/injection pending. [backend/bubble_dictate.py:4103](../backend/bubble_dictate.py#L4103), [backend/bubble_dictate.py:4118](../backend/bubble_dictate.py#L4118), [backend/bubble_dictate.py:4182](../backend/bubble_dictate.py#L4182).

Editability is checked before a delay without target revalidation; readonly Edit/Document controls can pass. The global click exclusion checks the hidden Tk root, so Tauri controls are treated as outside targets.

**Minimal remedy:** Exclude owned native windows, check writable target identity immediately before delivery, and keep text pending if focus changes or the target is unsuitable. **Plan:** T05.

### A14 [P2] Old completion work can repaint a new recording as ready

**Evidence:** Reproduced with a controlled empty-result delay. [backend/bubble_dictate.py:1963](../backend/bubble_dictate.py#L1963), [backend/bubble_dictate.py:2016](../backend/bubble_dictate.py#L2016), [backend/bubble_dictate.py:4128](../backend/bubble_dictate.py#L4128).

A new recording can start while an old worker is sleeping before its unconditional Ready repaint. Session identifiers exist but do not guard these updates.

**Minimal remedy:** Apply delayed updates only to the active operation, or render from authoritative current state instead of assigning Ready unconditionally. **Plan:** T04, T05.

### A15 [P2] History and settings persistence can lose or restore data

**Evidence:** Clear/append race reproduced; direct-write risk source-confirmed. [backend/bubble_dictate.py:1103](../backend/bubble_dictate.py#L1103), [backend/bubble_dictate.py:1395](../backend/bubble_dictate.py#L1395), [backend/settings.py:301](../backend/settings.py#L301).

Clear and append are separate unlocked read/modify/write operations. The reproduced interleaving restored a deleted transcript. Direct JSON writes also expose readers/crashes to incomplete files.

**Minimal remedy:** Serialize each file's mutations and write through a same-directory temporary file plus atomic replacement. Preserve the existing five-entry history and data location. **Plan:** T02.

### A16 [P2] Settings have competing live, saved and stale-client truths

**Evidence:** Reproduced with failed persistence and delayed/stale UI saves. [backend/bubble_dictate.py:1054](../backend/bubble_dictate.py#L1054), [desktop/src/pages/SettingsPage.tsx:61](../desktop/src/pages/SettingsPage.tsx#L61), [desktop/src/components/dictation/FloatingBubbleSurface.tsx:73](../desktop/src/components/dictation/FloatingBubbleSurface.tsx#L73).

Live settings change before persistence succeeds. Whole-object UI saves overwrite unrelated bubble/custom-model changes. A pending response replaced a later edit with the earlier submitted path. Position-only writes also restart the hotkey listener unnecessarily.

**Minimal remedy:** Accept validated field patches, commit before publishing side effects, and gate the form while saving. Apply listener/model work only when the corresponding field changes. **Plan:** T03, T07.

### A17 [P2] Malformed persisted data can crash startup or rendering

**Evidence:** Invalid UTF-8 settings and invalid-date rendering reproduced. [backend/settings.py:293](../backend/settings.py#L293), [backend/bubble_dictate.py:1349](../backend/bubble_dictate.py#L1349), [desktop/src/lib/time.ts:4](../desktop/src/lib/time.ts#L4).

UnicodeDecodeError is not handled by settings/history readers. Backend history retains arbitrary timestamp strings, while frontend formatting throws RangeError for invalid dates.

**Minimal remedy:** Preserve unreadable originals, expose a recovery error, and handle invalid encodings. Format invalid/null timestamps with a safe fallback. **Plan:** T02.

### A18 [P2] Frontend setting values do not match backend contracts

**Evidence:** Reproduced with backend normalization. [desktop/src/fixtures/settings.ts:17](../desktop/src/fixtures/settings.ts#L17), [backend/settings.py:12](../backend/settings.py#L12), [backend/settings.py:19](../backend/settings.py#L19).

The interface offers Spanish but omits Persian; Markdown differs from Markdown (.md). Saving those frontend values silently selects English and Plain Text. The 50% opacity minimum also conflicts with the backend's 70%.

**Minimal remedy:** Use accepted stored values with independent display labels. Every offered value must round-trip without changing meaning. **Plan:** T07.

### A19 [P2] Hotkey capture traps focus and accepts broken shortcuts

**Evidence:** Frontend/legacy capture outputs reproduced. [desktop/src/components/settings/HotkeyInput.tsx:10](../desktop/src/components/settings/HotkeyInput.tsx#L10), [backend/bubble_dictate.py:3992](../backend/bubble_dictate.py#L3992), [backend/bubble_dictate.py:4044](../backend/bubble_dictate.py#L4044).

Tab is intercepted, raw Space normalizes to disabled, Enter/Tab use invalid syntax, and function/arrow keys are ignored. Legacy Ctrl+Shift+D captures as Ctrl+D. Listener parse failures are only logged.

**Minimal remedy:** Keep Tab navigation, use one supported key grammar, preserve all modifiers, and reject invalid shortcuts visibly before saving. **Plan:** T07.

### A20 [P2] Model discovery ignores the configured download root

**Evidence:** Reproduced with a nondefault fake cache root. [backend/settings.py:344](../backend/settings.py#L344), [backend/bubble_dictate.py:1164](../backend/bubble_dictate.py#L1164), [backend/bubble_dictate.py:1547](../backend/bubble_dictate.py#L1547).

Download/loading can use MODEL_DOWNLOAD_ROOT, while availability, folder/path actions and size discovery use another cache root.

**Minimal remedy:** Use one effective-root resolver across download, inference, availability and folder/path metadata. **Plan:** T03.

### A22 [P2] Main and quick history remain stale

**Evidence:** Reproduced with changing fake bridge history. [desktop/src/pages/HistoryPage.tsx:17](../desktop/src/pages/HistoryPage.tsx#L17), [desktop/src/components/dictation/QuickHistoryPopoverSurface.tsx:23](../desktop/src/components/dictation/QuickHistoryPopoverSurface.tsx#L23).

Both read once. The persistent popover's show event changes placement only; OLD remained after a new history entry. First-mount failure can leave it empty for the session.

**Minimal remedy:** Refresh at show/navigation, transcript completion and clear. Keep a recoverable error state and ignore obsolete responses. **Plan:** T08.

### A23 [P2] Data pages do not recover from backend startup/poll failure

**Evidence:** Reproduced with failing-then-ready settings and a failed model poll. [desktop/src/pages/SettingsPage.tsx:27](../desktop/src/pages/SettingsPage.tsx#L27), [desktop/src/pages/ModelsPage.tsx:24](../desktop/src/pages/ModelsPage.tsx#L24), [desktop/src/pages/ModelsPage.tsx:38](../desktop/src/pages/ModelsPage.tsx#L38).

Settings retains its initial failure; History/Models silently become empty. One model poll rejection erases all cards and removes the condition that schedules further polling. Model-order responses also have a stale-response risk.

**Minimal remedy:** Distinguish loading/error/empty, reload when backend readiness changes, retain the last valid data, and sequence/cancel obsolete reads. **Plan:** T08.

### A24 [P2] State polling overlaps and conceals disconnection

**Evidence:** Reproduced with deferred responses. [desktop/src/bridge/pythonBridge.ts:118](../desktop/src/bridge/pythonBridge.ts#L118).

Each subscriber creates its own 750 ms interval. Three subscribers produced concurrent reads and delivered an older idle after recording. Failed polls leave stale state looking current. Persistent hidden windows continue work.

**Minimal remedy:** Share one serialized poll per bridge/webview, expose connection state, and prevent stale responses. Suspend unnecessary hidden-surface work using existing visibility events. **Plan:** T08.

### A25 [P2] Native bubble/popover can activate and steal target focus

**Evidence:** Source-confirmed configuration; native focus test pending. [desktop/src-tauri/tauri.conf.json:26](../desktop/src-tauri/tauri.conf.json#L26), [desktop/src-tauri/tauri.conf.json:41](../desktop/src-tauri/tauri.conf.json#L41).

Floating windows omit focus/focusable controls, whose defaults permit activation. The legacy bubble explicitly used a no-activate style; the native migration does not reproduce that property.

**Minimal remedy:** Use native nonactivation for pointer utility windows. Keep full keyboard-accessible controls in the main window. **Plan:** T05.

### A26 [P2] Native positioning mixes physical and logical units

**Evidence:** Source-confirmed; mixed-monitor test pending. [desktop/src-tauri/src/lib.rs:26](../desktop/src-tauri/src/lib.rs#L26), [desktop/src-tauri/src/lib.rs:405](../desktop/src-tauri/src/lib.rs#L405), [desktop/src-tauri/src/lib.rs:873](../desktop/src-tauri/src/lib.rs#L873).

Monitor work areas and outer positions are physical, configured dimensions are logical, and a physical tail offset becomes CSS pixels. Fixed 56/410/300 calculations can be wrong at non-100% scaling.

**Minimal remedy:** Use actual physical outer sizes for bounds and convert the tail to logical pixels with the relevant window scale factor. **Plan:** T10.

### A27 [P2] Bubble position is overwritten or restored on the wrong monitor

**Evidence:** API quit overwrite reproduced; native restoration paths source-confirmed. [backend/bubble_dictate.py:4362](../backend/bubble_dictate.py#L4362), [desktop/src/components/dictation/TauriBubbleController.tsx:12](../desktop/src/components/dictation/TauriBubbleController.tsx#L12), [desktop/src-tauri/src/lib.rs:849](../desktop/src-tauri/src/lib.rs#L849).

API Quit saves hidden-root [-32000,-32000]. Startup reads settings before readiness without retry. Placement chooses the current monitor before considering saved coordinates; tray Show uses a default rather than retaining the current position.

**Minimal remedy:** Keep native position ownership separate from the hidden root. Restore after readiness on the containing monitor, and preserve current placement when simply showing a hidden bubble. **Plan:** T10.

### A28 [P2] Closing utility windows destroys them; minimized main stays minimized

**Evidence:** Source-confirmed; native OS interaction pending. [desktop/src-tauri/src/lib.rs:433](../desktop/src-tauri/src/lib.rs#L433), [desktop/src-tauri/src/lib.rs:954](../desktop/src-tauri/src/lib.rs#L954).

Only main CloseRequested is prevented. OS close on a floating window can destroy the webview that Show later expects. Main Show calls show/focus but not unminimize.

**Minimal remedy:** Hide/prevent close for persistent utility surfaces and unminimize main before showing/focusing it. **Plan:** T10.

### A29 [P2] Fresh sidecar omits expected CUDA runtime DLLs

**Evidence:** Fresh archive inspection plus historical runtime failures. [scripts/build-backend-sidecar.ps1:71](../scripts/build-backend-sidecar.ps1#L71), [backend/bubble_dictate.py:1590](../backend/bubble_dictate.py#L1590).

The rebuilt 104,578,502-byte archive contains no NVIDIA DLL entries even though the source environment provides them. September runtime logs report missing cublas64_12.dll and CPU fallback. This audit did not run GPU inference or a clean-machine installer.

**Minimal remedy:** Package the required CUDA runtime libraries and resolve their frozen locations. Verify CPU fallback and explicit CUDA in a clean installation; measure the size increase. **Plan:** T15.

### A30 [P2] Native appearance is not synchronized across persistent windows

**Evidence:** Reproduced with storage/system-theme events. [desktop/src/theme/theme-provider.tsx:15](../desktop/src/theme/theme-provider.tsx#L15), [desktop/src/app/AppProviders.tsx:20](../desktop/src/app/AppProviders.tsx#L20).

The provider ignores cross-window changes; a stale system preference rewrote a newer dark/blue preference. Backend theme is separate legacy state. The active Sonner toaster defaults to light and does not receive app appearance.

**Minimal remedy:** Use one native mode/preset store, synchronize persistent views through the existing event channel, and pass resolved appearance to the active toaster. Preserve legacy settings separately. **Plan:** T11.

### A31 [P2] Panel Opacity is ineffective in the native app

**Evidence:** Source-confirmed. [desktop/src/pages/SettingsPage.tsx:137](../desktop/src/pages/SettingsPage.tsx#L137).

The slider writes a setting applied only to hidden/legacy Tk panels. React/native panels do not consume it. CSS content opacity alone would not make the opaque main window translucent.

**Minimal remedy:** Remove the ineffective native control for the minimal fix, while preserving the existing legacy setting. Add native translucency only as a separately specified feature. **Plan:** T07.

### A32 [P2] Production screens present inactive or invented actions

**Evidence:** Source-confirmed; Open History and Browse checked in browser. [desktop/src/pages/SettingsPage.tsx:165](../desktop/src/pages/SettingsPage.tsx#L165), [desktop/src/pages/RecordingPage.tsx:124](../desktop/src/pages/RecordingPage.tsx#L124), [desktop/src/pages/ExportsPage.tsx:33](../desktop/src/pages/ExportsPage.tsx#L33), baseline `desktop/src/components/exports/ExportRow.tsx:15` (subsequently removed), [desktop/src/bridge/pythonBridge.ts:154](../desktop/src/bridge/pythonBridge.ts#L154).

Browse has no handler; Open History is a no-op; Exports lists fixtures and inactive row buttons. Native Check for updates always rejects. The labeled recording preview adds four enabled no-op footer buttons.

**Minimal remedy:** Wire the real picker/navigation and show actual export results. Remove unsupported updater/catalog actions and inert preview controls instead of building new subsystems. **Plan:** T09.

### A33 [P2] Frontend copy failures show success or escape unhandled

**Evidence:** Reproduced with rejected clipboard access. [desktop/src/components/history/HistoryRow.tsx:19](../desktop/src/components/history/HistoryRow.tsx#L19), [desktop/src/components/dictation/QuickHistoryPopoverPreview.tsx:27](../desktop/src/components/dictation/QuickHistoryPopoverPreview.tsx#L27), [desktop/src/components/dictation/TranscriptPreview.tsx:9](../desktop/src/components/dictation/TranscriptPreview.tsx#L9), [desktop/src/components/dictation/QuickHistoryPopoverSurface.tsx:57](../desktop/src/components/dictation/QuickHistoryPopoverSurface.tsx#L57).

Several controls report success before awaiting clipboard access; others await but never catch. The reproduction emitted both Copied transcript and an unhandled rejection.

**Minimal remedy:** Await and catch in the existing copy helper/action handlers; notify success only after completion and retain the text on failure. **Plan:** T09.

### A34 [P2] Recording actions are not gated while busy or pending

**Evidence:** Source-confirmed native rejection; mock race reproduced. [desktop/src/components/dictation/RecordButton.tsx:7](../desktop/src/components/dictation/RecordButton.tsx#L7), [desktop/src/pages/RecordingPage.tsx:27](../desktop/src/pages/RecordingPage.tsx#L27).

The UI treats all non-recording states as Start. During transcription native rejects the click; the mock can start another recording that an older timer ends. Pending actions are also not guarded consistently.

**Minimal remedy:** Use authoritative loading/transcribing/pending state to disable incompatible actions and reject duplicate requests at the backend as well. **Plan:** T03, T08, T09.

### A35 [P2] Working controls lack accessible names and state semantics

**Evidence:** Unnamed input/slider reproduced; other omissions source-confirmed. [desktop/src/components/history/HistorySearch.tsx:7](../desktop/src/components/history/HistorySearch.tsx#L7), baseline `desktop/src/components/ui/slider.tsx:21` (subsequently removed), [desktop/src/components/shell/Sidebar.tsx:20](../desktop/src/components/shell/Sidebar.tsx#L20).

History search and opacity slider have no accessible name. Navigation lacks current-route state; model ordering lacks selected semantics; recording changes lack a live announcement. Hotkey keyboard trapping is covered by A19.

**Minimal remedy:** Name retained inputs, provide current/selected semantics, announce meaningful status changes, and verify keyboard navigation. The removed native opacity slider no longer needs a workaround. **Plan:** T12.

### A36 [P2] CSS contains invalid bounds and a missing active color token

**Evidence:** Source/generated-CSS confirmed. [desktop/src/components/ui/select.tsx:78](../desktop/src/components/ui/select.tsx#L78), [desktop/src/globals.css:5](../desktop/src/globals.css#L5).

Radix select utilities emit invalid max-height and transform-origin declarations. Destructive foreground is referenced by active controls but absent from the theme/generated utility. Actual dropdown clipping and all destructive contrasts were not established.

**Minimal remedy:** Use explicit var(...) arbitrary values and define the destructive foreground token. Verify rendered menus and contrast across supported themes. **Plan:** T12.

### A37 [P2] Installed model badge has insufficient contrast in dark neutral mode

**Evidence:** Measured in the real rendered browser interface. [desktop/src/components/models/ModelCard.tsx:21](../desktop/src/components/models/ModelCard.tsx#L21).

The 12 px, weight-600 Installed badge rendered foreground [0,122,85] over composited [16,38,37], giving about 2.95:1. This is below the 4.5:1 text threshold; the badge is informational, distinct from its disabled download button.

**Minimal remedy:** Add an appropriate dark foreground variant using the existing palette, then measure the supported themes. **Plan:** T12.

### A41 [P2] Resolved dependencies have advisory matches requiring triage

**Evidence:** Live registry/database checks on 2026-10-02. [desktop/package-lock.json:1](../desktop/package-lock.json#L1), [desktop/src-tauri/Cargo.lock:1](../desktop/src-tauri/Cargo.lock#L1).

npm reports eight affected packages (five high, three moderate); omit-dev still reports two high package entries. OSV matched four installed PyPI packages and ten Cargo-lock packages, including maintenance notices and alias duplicates. Package matches are not proof of a reachable exploit in the shipped app.

**Minimal remedy:** Apply compatible fixes, remove unused dependencies, distinguish build-only/target-specific entries, and document any remaining upstream constraints with evidence. Do not force major upgrades or fork frameworks to silence notices. **Plan:** T14.

### A42 [P2] Python installation is not reproducible

**Evidence:** Source-confirmed. [backend/requirements.txt:1](../backend/requirements.txt#L1), [backend/requirements-build.txt:1](../backend/requirements-build.txt#L1).

Runtime requirements are minimum-only or unbounded. The current 59-package environment is a snapshot, not a repeatable tested resolution, and build tools are not locked exactly.

**Minimal remedy:** Create reviewed runtime/build lock inputs from a clean minimal environment, including the optional GPU requirements, and verify a fresh install against those exact resolutions. **Plan:** T14.

### A21 [P3] Repeated downloads launch duplicate workers

**Evidence:** Reproduced with two identical requests. [backend/bubble_dictate.py:1139](../backend/bubble_dictate.py#L1139), [backend/bubble_dictate.py:3330](../backend/bubble_dictate.py#L3330).

Download status is not an admission guard and the two interfaces have separate paths. Rapid duplicate requests create multiple workers.

**Minimal remedy:** Claim a download per model under the existing lock and share that path between native and legacy actions. **Plan:** T03.

### A38 [P3] Version, descriptions and recovery directions are inaccurate

**Evidence:** Source-confirmed. [desktop/src/pages/HelpAboutPage.tsx:106](../desktop/src/pages/HelpAboutPage.tsx#L106), [desktop/src/components/dictation/RecordingStatusCard.tsx:19](../desktop/src/components/dictation/RecordingStatusCard.tsx#L19), [desktop/src/components/dictation/TranscriptPreview.tsx:18](../desktop/src/components/dictation/TranscriptPreview.tsx#L18), [desktop/index.html:5](../desktop/index.html#L5).

Help claims 0.5.0-sidecar-ready while native metadata is 0.1.0. Native text still describes mock-only behavior and refers to a nonexistent top-bar start control. HTML title is desktop and its favicon path is absent.

**Minimal remedy:** Derive native version from app metadata, make copy match the runtime and existing recovery controls, and use the existing app icon/title. **Plan:** T09.

### A39 [P3] Browser mock gives false confidence about native behavior

**Evidence:** Reproduced/source-confirmed mock-only defects. [desktop/src/bridge/mockBridge.ts:1](../desktop/src/bridge/mockBridge.ts#L1).

Mock export returns contents where pages expect a path; download/open folder can succeed without work; custom-model copy can copy an empty string. Mock timers accept busy recording transitions. These do not prove matching native defects.

**Minimal remedy:** Keep mocks deterministic and contract-faithful. Unsupported browser actions should identify their limitation rather than simulate success. **Plan:** T09.

### A40 [P3] Avoidable retained audio, repeated scans and unbounded logging

**Evidence:** Retained references/source confirmed; 12 scans reproduced; existing logs measured. [backend/bubble_dictate.py:1778](../backend/bubble_dictate.py#L1778), [backend/bubble_dictate.py:1909](../backend/bubble_dictate.py#L1909), [backend/bubble_dictate.py:952](../backend/bubble_dictate.py#L952), [backend/bubble_dictate.py:278](../backend/bubble_dictate.py#L278), [backend/config.py:103](../backend/config.py#L103).

Captured chunks stay globally referenced until the next recording. At 16 kHz mono float32 this is 64,000 bytes/second before overhead/copies. Six-model listing performs 12 recursive size scans. Routine bridge polls and audio callbacks write synchronously; aggregate logs have no cap. Existing aggregate/session logs total about 357 MiB. Actual latency improvement was not measured.

**Minimal remedy:** Release buffers when the operation completes, reuse model details for size labels, skip routine poll/callback disk output, and rotate existing log files. Use standard library facilities. **Plan:** T13.

### A43 [P3] Unused frontend scaffolding and duplicate build work add maintenance

**Evidence:** Reachability/source confirmed. Baseline `desktop/src/components/ui/sonner.tsx:1` (subsequently removed), [desktop/package.json:9](../desktop/package.json#L9), [desktop/src-tauri/tauri.conf.json:8](../desktop/src-tauri/tauri.conf.json#L8).

Eleven UI wrappers are unreachable from main.tsx; the unused toaster is the sole next-themes consumer. Several matching Radix dependencies are unused. tauri:build builds frontend assets and the Tauri hook builds them again; backend start also repeats health reads.

**Minimal remedy:** Prune only primitives still unused after the fixes. Keep one frontend build hook and one health result per lifecycle attempt. Retain the existing bridge/runtime architecture. **Plan:** T13, T15.

## Dependency evidence and practical exposure

The saved npm report lists `@vitest/mocker`, `vitest`, `baseline-browser-mapping`, `brace-expansion`, `browserslist`, `nanoid`, `postcss` and `undici`. npm's omit-dev result still contains `nanoid` and `postcss`; tree inspection places them through Vite/Tailwind tooling. It is inaccurate to call the scan clean or to assume all findings are shipped runtime exploits. [npm evidence](audit-evidence/npm-advisories.json).

The OSV batch checked **59 installed PyPI distributions and 492 crates.io lock entries**. Matches include:

| Group | Matched packages | Qualification |
| --- | --- | --- |
| Python runtime/environment | anyio 4.13.0, Pillow 12.2.0 | Examine actual frozen imports and affected call paths |
| Python build tools | pip 26.1.2, setuptools 82.0.1 | Build environment findings; not evidence of app execution |
| Rust defects | anyhow 1.0.102, quick-xml 0.39.4 | Present in Windows dependency trees; input-path reachability needs triage |
| Other-target crates | event-listener 5.4.1, glib 0.18.5 | No inverse dependency tree for the current Windows target |
| Maintenance notices | proc-macro-error and five unic crates | Unmaintained is not itself a demonstrated vulnerability |

OSV returned 46 advisory records for the 14 matched packages, including duplicate aliases. This does **not** mean 46 unique exploitable vulnerabilities. Full IDs, affected ranges and primary references are retained in [OSV evidence](audit-evidence/osv-advisories.json), with exact queried versions in [dependency snapshot](audit-evidence/dependency-snapshot.json). [OSV API documentation](https://google.github.io/osv.dev/post-v1-querybatch/) explains the matching interface. No dependency was upgraded in this cleanup.

## Security and scope risks

The bridge binds only to loopback, but has no caller authentication: a local process able to reach the port can read history and issue its exposed actions. This is an existing local-trust assumption, not proof of remote exposure or a tested cross-user attack. Enforce bounds/ownership first and document that boundary; a different trust model requires an explicit product decision.

CSP is currently null. No raw-HTML injection or remote-script execution path was found in the reviewed application. A restrictive local-asset CSP is appropriate defense in depth, tested against fonts, styles and Tauri IPC. Capabilities do not grant arbitrary shell execution to the frontend merely because the Rust shell plugin is installed. Rust proxy response-size/connect bounds also need tightening alongside bridge robustness.

Only Windows x64 is currently evidenced. Sidecar naming uses the Rust host tuple without proving Python/target architecture compatibility; packaging must validate that match before supporting additional targets.

## Verification performed

| Check | Result |
| --- | --- |
| Python unit suite from organized backend/tests | **156 passed** |
| Python syntax/import checks | **Passed** |
| pip check | **Passed**, no broken installed requirements |
| PowerShell script parsing | **Passed**, four scripts |
| Frontend tests | **42 passed in 13 files** |
| Frontend lint and TypeScript/build | **Passed** |
| Rust format and fresh offline locked tests | **Passed**, 10 tests |
| Fresh PyInstaller sidecar | **Built**, 104,578,502 bytes |
| Native release/installer build | **Blocked by compiler memory exhaustion**, no fresh installer claimed |
| Browser review | Inactive controls and actual color/geometry checked; native behavior remains unverified |
| Live npm/OSV dependency checks | Completed; findings retained above |

The first release attempt produced compiler-error cascades. Isolated optimized memchr checks passed both with and without an explicit Windows target. A verbose offline/locked single-job retry then failed compiling `windows 0.61.3` with **memory allocation of 1327120 bytes failed**, followed by process exit 0xc0000409. At inspection the host had about 2.75 GiB physical and 3.13 GiB commit headroom. This is the exact remaining build blocker; neither dependency defects nor cleanup breakage are inferred from it. Rebuild with adequate memory headroom before changing application code to address this result.

The existing suites emphasize helpers, routing/layout and successful mocked responses. They do not establish the failing inference, real paste, reload ordering, native process ownership, focus or clean-machine packaging behavior. Add focused regressions for these failures and perform native acceptance before describing them as fixed.

The measured badge contrast uses rendered CSS foreground/background colors with alpha compositing. The normal-text threshold is 4.5:1 in [WCAG 2.2 contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html). Native DPI semantics are documented in [Tauri Window API](https://v2.tauri.app/reference/javascript/api/namespacewindow/) and [DPI API](https://v2.tauri.app/reference/javascript/api/namespacedpi/). Parent/worker behavior is covered by [PyInstaller process documentation](https://pyinstaller.org/en/stable/advanced-topics.html) and [Windows process termination](https://learn.microsoft.com/en-us/windows/win32/procthread/terminating-a-process).

Final cleanup checks passed: 15 moved tracked files match HEAD content; the two intentionally updated moved scripts are accounted for; the original README is preserved. All checked local references resolve, all 43 findings map to the 15-task plan, HEAD is unchanged and nothing is staged. Live remote refs still contain only the earlier master. See [cleanup verification](audit-evidence/cleanup-verification.json).

The next work is specified in [implementation-plan.md](implementation-plan.md). Application fixes and native acceptance remain separate implementation work.
