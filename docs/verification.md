# Implementation verification

Checked on 2026-10-02 in `<repository>`, on the local
`reliability-fixes` branch. The owner subsequently authorized committing all
changes and installing the app. Source commit
`5cccd1cd88dd80bd6c58e17df546aa33e005641b` includes the cleanup and reliability
fixes, and the rebuilt app now replaces the June per-user installation. Native
version for that initial upgrade was 0.1.0; no release was published.
[The original audit](audit.md) describes baseline `462ce340`.

The subsequent reported bubble/Alt+A defects were corrected and the installed
app updated to 0.1.1. [The follow-up verification](bubble-shortcut-fix.md)
records fresh 192 Python, 85 frontend and 21 native passing tests, installation
identity checks and ready normal-profile CUDA startup. The original artifact
identities and counts below are retained as evidence of the first upgrade.

## What changed

The existing Python runtime, typed React bridge, loopback newline protocol and
Tauri shell are retained. The fixes make startup recoverable, settings/model
changes transactional, JSON writes atomic, transcript delivery retryable and
backend ownership explicit. The bubble uses physical monitor bounds, preserves
saved moves, guards activation and corrects Windows' initial minimum-width
clamp. Data pages recover after disconnects, hidden views stop unnecessary
polling, appearance stays synchronized, and retained controls have working
actions and accessible names.

Default transcript cleanup preserves literal punctuation. Logs rotate and omit
transcript text by default; inference releases captured chunks instead of
retaining them until the next recording. Model listings reuse one metadata
scan. Unused UI wrappers and dependencies, fabricated export rows, the inert
updater and ineffective native opacity control were removed. No new state
framework, transport, export database or backend rewrite was introduced.

## Checks and evidence

| Check | Observed result | Evidence |
| --- | --- | --- |
| Python complete suite | 189 passed in the development environment | `audit-evidence/python-implementation-tests.log` |
| Clean pinned Python environment | 189 passed with an isolated data profile; pip check clean | `audit-evidence/python-clean-tests.log`, `audit-evidence/python-clean-install.log` |
| Frontend complete suite | 82 passed across 17 files | `audit-evidence/frontend-implementation-tests.log` |
| TypeScript, ESLint, production frontend | Passed | `audit-evidence/frontend-build-final.log`; final packaging also builds/typechecks current assets |
| Rust | 21 passed; one controlled subprocess fixture is intentionally ignored and invoked by the job test; fmt check passed | `audit-evidence/native-implementation-tests.log` |
| Real source startup | Empty-cache recovery, bounded malformed/stalled clients, recording rejection, wrong-owner shutdown rejection, settings patches and worker exit passed | `audit-evidence/backend-source-acceptance.json` |
| Real frozen backend | Same checks passed, plus existing offline tiny.en CPU/CUDA load and synthetic warmup; microphone stayed unopened | `audit-evidence/backend-frozen-acceptance.json` |
| Production passive native windows | 56x56 bubble client at 96 DPI, centered 44x44 button; all UI markers; MA_NOACTIVATE on root/same-thread children; main/bubble/popover Close hide and preserve HWNDs | `audit-evidence/native-passive-acceptance.json` |
| Actual native pointer tests | Not reached: another application remained foreground and the controlled target did not receive the injected click. Owner requested available checks only | `audit-evidence/native-window-acceptance.json` |
| Actual tinted status contrast | 14.15:1 minimum across light/dark and neutral/green/blue, measured with transitions disabled | `audit-evidence/status-pill-contrast.json` |
| Transcribing bubble icon | 7.03:1 against its opaque amber background | `audit-evidence/bubble-icon-contrast.json` |
| Repository and artifact review | Passed: native probe hashes, sidecar/CUDA identities, current document links, evidence JSON/privacy scan, unchanged runtime metadata, one worktree and clean diff check; live remote unchanged | `audit-evidence/implementation-verification.json` |

Frozen startup measured 2.656 seconds with an empty offline cache and recoverable
model error. Existing tiny.en load plus synthetic warmup measured 0.422 seconds
on CPU and 1.328 seconds on CUDA on the test machine's NVIDIA GPU. These are observations of
this isolated run, not real dictation latency, transcription accuracy, a
comparison with the old build, or a clean-machine GPU guarantee.

An actual native-owned launch also passes recoverable empty-cache startup,
matching launch identity, wrong-owner rejection and frozen-worker/job/port exit
after controlled abrupt native shutdown. This tests the real shell/sidecar/job
boundary, not the tray Quit interaction. Both native probes match the executable
after the completed production NSIS build. Final artifacts under
`desktop/src-tauri/target/release/` are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `local-dictation-desktop.exe` | 9,862,144 | `00ddb69b3aa7269f50550652d66b24da33dea952832fbc5a3f29240b177911aa` |
| `local-dictation-backend.exe` | 104,654,303 | `92af884aab79069dc7100b2155ff0c22d3da41ce2dfeff7a9d5d2807fd6ccdcc` |
| `bundle/nsis/Local Dictation_0.1.0_x64-setup.exe` | 1,426,099,870 | `a9690af6ba10477de21bebe2cfd4618997890514891888dd4a9a0c0a7e566b46` |

These are the build artifacts. Their pre-commit identities and the
staged/adjacent CUDA resource comparison are recorded in
`audit-evidence/implementation-verification.json`. The installed package has the
expected bundle-marker difference described below.

## Installed upgrade

The owner-authorized installer completed with exit code 0 in silent update
mode (`/S /UPDATE`), replacing the existing per-user installation at
`%LOCALAPPDATA%\Local Dictation`. The Start Menu shortcut points to
the updated executable. Personal settings and history content hashes are
unchanged. Previous executable backups are retained under ignored build output.

Installed native SHA-256 is
`8445f74b47dde69f514b934a94fa6f6a819773e932b5c5f4e28a28ddb29f1e9d`.
Tauri's packaging changes `__TAURI_BUNDLE_TYPE_VAR_UNK` to
`__TAURI_BUNDLE_TYPE_VAR_NSS`. A full byte comparison confirms those three bytes
are the only difference from the standalone artifact. The installed backend
and every one of the 17 CUDA DLLs match the verified build hashes.

Fresh acceptance of this installed executable passes isolated recoverable
startup, launch ownership, wrong-owner rejection and worker/port cleanup after
controlled abrupt native exit. Passive checks pass the 56x56 bubble, centered
44x44 button, HWND markers, utility activation responses and persistent Close
behavior. These probes disabled hotkeys, used empty offline profiles and did
not capture microphone audio or inject paste. The temporary app instances were
stopped after the checks. This is an upgrade on this machine, not a clean-machine
installation test.

Evidence: `audit-evidence/installation-verification.json`,
`audit-evidence/installed-native-owned-acceptance.json` and
`audit-evidence/installed-native-passive-acceptance.json`. Fresh pre-commit tests
again passed Python 189, frontend 82, Rust 21 plus the intentional fixture,
typecheck, lint and Rust formatting.

## Audit finding accounting

Implemented means the local code change is present and its stated checks passed.
It does not close the separate interaction/installation gaps identified below.

| Finding | Implementation and verification |
| --- | --- |
| A01 | Control service starts before model/microphone initialization; resource errors stay recoverable. Real empty-cache source/frozen checks pass. |
| A02 | Bounded client concurrency, total read deadline and per-request exception boundary. Malformed, abandoned and trickled-client regressions pass. |
| A03 | Complete local snapshot required, including tokenizer/config/vocabulary; inference gets the local directory. Incomplete-cache regressions and offline tiny.en warmup pass. |
| A04 | Serialized candidate load/warmup/save/publication; recording gated while loading; failed changes preserve prior settings/model. Rollback and reversed-completion tests pass. |
| A05 | Default cleanup preserves literals, URLs, numbers and command words. Spoken punctuation is explicit opt-in. |
| A06 | Successful text published and retained before clipboard/paste; persistence/delivery failures reported separately. Clipboard-contention tests pass. |
| A07 | Managed job/process state refreshes after exit and retains causes. Controlled child exit and status tests pass. |
| A08 | Health and managed shutdown match a nonempty launch ID, not a parent PID. Wrong-owner shutdown is rejected by the real frozen backend. |
| A09 | Suspended process assigned to a kill-on-close Windows job before resume; job owns one-file descendants. Real Windows controlled-tree tests preserve an unrelated tree. |
| A10 | One lifecycle reservation; waits outside short locks; protocol validation. A real Windows closed-port timeout now permits auto-start, while response-stage timeout stays unhealthy. Actual shell/sidecar startup and controlled job exit pass. |
| A11 | Loading, readiness, resource/operation, persistence and connection errors reach the UI without discarding completed text. Recovery-error regressions pass. |
| A12 | Pending paste claimed once; delivery failures restore it only for the current recording. Concurrent/retry regressions pass. |
| A13 | Writable focused identity, clicked element identity and own-PID/native-HWND exclusion are checked before claim and injection. UI Automation boundary regressions pass; real external-editor acceptance remains open. |
| A14 | Session checks guard delayed repaint, post-history clipboard delivery and post-clipboard injection. Stale-worker regressions pass. |
| A15 | Per-file locks and flushed same-directory atomic replacement preserve five-entry history. Clear/append races and failed replacement tests pass. |
| A16 | Validated patches compose with current settings; only changed resource/hotkey fields trigger work. Save locks the form and invalidates stale reads. |
| A17 | Bad JSON/encoding preserved; explicit Save/Clear creates a corrupt-byte backup before recovery; invalid dates render safely. Automatic moves cannot authorize recovery. |
| A18 | Offered language/text-format/device values round-trip with the backend; ineffective native opacity control removed while legacy setting remains. |
| A19 | Shared supported shortcut grammar; all modifiers retained; Tab navigates; invalid/listener failures are visible and roll back. Tests and browser keyboard checks pass. Real OS hotkey acceptance is open. |
| A20 | Configured model root used for discovery, availability, inference and path actions. Nondefault-root regression passes. |
| A21 | One claimed download per model shared by native/legacy actions. Duplicate admission test passes; no model downloads were used for acceptance. |
| A22 | History revisions and show/reconnect refresh main and persistent quick history; stale reads ignored. Repeated-identical-transcript and popover-show tests pass. |
| A23 | Pages distinguish error/loading/empty, retain valid cards and retry transient failures. Reconnect/model-poll regressions pass. |
| A24 | One serialized state poll per webview with connection state; DOM/native visibility pauses it. Controlled overlap/visibility tests pass. |
| A25 | Nonfocusable utility config and same-UI-thread WM_MOUSEACTIVATE guard. Actual native responses are MA_NOACTIVATE; real click/drag focus remains unverified. |
| A26 | Actual physical outer sizes and work areas; CSS tail uses the popover scale factor. Negative/mixed-scale geometry regressions pass; physical mixed-monitor acceptance remains open. |
| A27 | Hidden API root never overwrites native position; restore waits for readiness, uses containing monitor and retains placement on Show. Failed position saves retain the newest move and retry. |
| A28 | Persistent close hides windows and main Show unminimizes. Actual main/bubble/popover Close preserves and hides HWNDs. Reopening/minimize/tray interactions remain acceptance gaps. |
| A29 | CUDA libraries staged as installed resources outside one-file extraction; retained DLL search handles. Real frozen CUDA synthetic warmup passes here; clean-install GPU test remains open. |
| A30 | Shared appearance store and native/storage events; system changes do not rewrite user preferences; Sonner follows resolved appearance. Synchronization tests pass. |
| A31 | Ineffective native opacity slider removed. Legacy opacity compatibility retained. |
| A32 | Real picker/navigation/export result controls retained; inert updater/fixture catalog/preview actions removed. Bridge/action/browser checks pass. |
| A33 | Copy awaits success, catches failure and retains text; errors do not falsely report success. Clipboard rejection regression passes. |
| A34 | Resource/transcription/action-pending state gates recording; duplicate backend/mock actions rejected. Pending and stale mock-timer regressions pass. |
| A35 | Labels, current navigation, selected order, live status and keyboard navigation added to retained controls. Browser and component checks pass. |
| A36 | Valid CSS var bounds and destructive foreground; explicit dark variant. Browser dropdown bounds and token checks pass. |
| A37 | Installed badge dark contrast corrected; additional tinted status/icon fixes measured. Installed badge handoff measured 4.88:1 light and 10.45:1 dark; no blanket contrast guarantee is asserted. |
| A38 | Native version comes from app metadata; titles, icon and runtime/recovery instructions match retained controls. Version remains 0.1.0. |
| A39 | Browser preview is labeled simulated; native-only filesystem/process actions reject visibly instead of fabricating results. Mocks preserve supported busy/settings contracts. |
| A40 | Captured chunk ownership transferred/cleared; metadata reused; routine callback/poll logging suppressed and logs bounded. Existing personal logs were not purged. No unmeasured latency claim. |
| A41 | Compatible dependency fixes, unused dependencies removed, remaining target/maintenance notices triaged below. |
| A42 | Exact reviewed runtime/build/CUDA resolutions; a fresh minimal Python install and npm ci pass. Lockfiles generated by package managers. |
| A43 | Unreachable wrappers/dependencies removed; one frontend hook per normal Tauri build; redundant health work removed. Existing architecture retained. |

## Final independent review

One fresh-context review found eight confirmed P2 defects, no critical findings,
no declined findings and no deferred minors. All eight were accepted and fixed
in one parent-owned pass: stale clipboard/injection side effects, clicked-target
validation, independent-shell exclusion, explicit history/settings corruption
recovery, a total client deadline, position-save retry and custom model names
containing the dropdown delimiter. Python, frontend and native regressions
observed failures before the corresponding fixes and pass afterwards. Additional
integration checks fixed the settings read/save race, resource error retention,
unready-microphone messaging, actual Windows bubble width and tinted contrast.
Actual owned startup then exposed another native failure: a closed loopback
port timed out before reporting refusal and was treated as an incompatible
running process. The actual UI error and a failing real-socket test confirmed
it. Connection-stage timeout is now unavailable; connected-response timeout
remains unhealthy. The new regression and actual native-owned launch pass.

## Dependencies and packaging tradeoffs

Fresh npm audit reports zero advisories. OSV queries of the 54 clean Python
runtime/build packages plus four optional CUDA packages report zero matches.
The complete Cargo lock has seven matched packages, not seven proven runtime
vulnerabilities:

- `glib 0.18.5`: GHSA-wrw7-89jp-8q8g and RUSTSEC-2024-0429 are aliases of the
  same unsoundness advisory. The GTK/glib path is absent from the Windows target.
- `proc-macro-error 1.0.4`: RUSTSEC-2024-0370 is an unmaintained notice; this
  dependency path is absent from the Windows target.
- Five `unic-* 0.9.0` maintenance notices remain via `urlpattern` and
  `tauri-utils`, including the Windows build/runtime graph. No fixed release is
  available in the checked advisories. A framework fork or incompatible upgrade
  was not introduced to silence those notices.

Exact records are in `audit-evidence/implementation-advisories.json` and
`audit-evidence/implementation-npm-audit.json`. Advisory matching is not a
reachability proof or a universal security guarantee. The control endpoint
remains loopback-only, intended for this local app and trusted local processes.

GPU resources contain 17 DLLs totaling 2,019,016,800 bytes. They are installed
once, outside the sidecar's one-file archive, avoiding repeated CUDA extraction
at backend startup. This makes the GPU build large; a documented CPU-only build
omits those resources. Models and virtual environments are not bundled.
NSIS uses supported zlib compression after the superseded LZMA build spent over
ten minutes of CPU time on GPU resources. No LZMA final size or comparative
runtime speedup is claimed. See the
[Tauri NSIS compression reference](https://v2.tauri.app/reference/config/#nsiscompression).

## Remaining acceptance boundaries

The owner chose to finish available checks while the game retained foreground.
Actual bubble click/drag delivery and preservation of editor focus, native tray
Quit, utility reopening, minimized-main interaction, physical mixed-DPI
monitor moves, OS hotkeys, real microphone dictation/paste and a clean-machine
installer/CPU/GPU run remain unverified. The Windows job and frozen-model checks
cover narrower real boundaries and do not replace those interactions.

The explicit owner follow-up authorized local Git commits and this machine's
installed upgrade, including the installer's Start Menu shortcut. No push, PR,
publication, model download or personal history/settings rewrite was performed.
Ordinary unit tests used mocks; isolated real acceptance profiles disabled
hotkeys and used empty offline caches. Existing personal logs may retain
oversized historic backups until normal rotation; they were not deleted.

## Scope rulings

The work kept one active folder and a local branch instead of another worktree.
Changes remained uncommitted during implementation until the owner authorized
the commit/install follow-up. Durable status/evidence review the actual
working files, including prior relocation, instead of commit-range-only skill
artifacts. Separate frontend/native scopes were delegated only after shared
contracts were defined, requiring parent integration. CUDA is packaged as
installed resources with an explicit size cost and CPU-only alternative. The
default `C:\local-dictation` profile is preserved; isolated acceptance uses an
explicit data-directory override, but must first verify the shared port is free.
These decisions and their reasons are also retained in
[implementation-status.md](implementation-status.md).
