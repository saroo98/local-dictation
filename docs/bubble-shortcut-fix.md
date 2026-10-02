# Bubble and Alt+A reliability follow-up

The owner reported a bubble stuck at Transcribing even while Alt+A recorded,
transcribed and pasted new text. Read-only queries of the running installed
backend found idle state, `transcribing: false`, ready resources and `<alt>+a`.
No personal transcript text was printed or copied into this report.

The source fix is committed locally as `103f6e5c798169774c6a6fcf6f80af0466051eec`.
The installed application's product version is 0.1.1. No push or release
publication was performed.

## Confirmed defects and corrections

The visibility subscriptions were global. In Tauri 2, a global JavaScript
listener receives targeted events from other windows. Hiding quick history or
minimizing/closing the main window could therefore stop a still-visible bubble's
state polling. The last Transcribing state remained visible and disabled bubble
clicks while the backend continued handling shortcuts. A regression using the
real Tauri JavaScript API and a controlled native boundary reproduced this exact
stale-display failure before the change.

Visibility subscriptions now use the current window's listener. The same
correction covers backend availability, model downloads and history refresh.
Hidden windows still pause unnecessary polling; showing the bubble refreshes
its state immediately. No additional transport or watchdog was added.

The keyboard callback also called `root.after` across threads. That Tk call
can wait for the UI thread, blocking the Windows listener's message handling.
A busy-Tk regression reproduced the blocked callback before the change.
Shortcuts now enter a standard-library queue; the Tk thread drains it every
25 milliseconds. The keyboard callback no longer calls Tk. Existing shortcut
parsing, toggle semantics and transcription guards
are retained.

The exact OS event responsible for each reported intermittent shortcut miss
was not captured. The blocking dispatch defect is proven and fixed; physical
shortcut reliability still needs interactive acceptance. Requests made during
active transcription remain intentionally rejected rather than interrupting
inference or discarding audio.

The API behavior was checked against the installed Tauri/pynput sources and
current primary documentation: [Tauri event migration](https://v2.tauri.app/start/migrate/from-tauri-1/#event-system)
and [pynput keyboard callbacks](https://pynput.readthedocs.io/en/latest/keyboard.html#the-keyboard-listener-thread).

## Validation

| Check | Observed result |
| --- | --- |
| Pre-fix regressions | Frozen busy bubble, foreign-window wakeup, stopped availability polling and blocked hotkey callback reproduced |
| Python complete suite | 192 passed |
| Frontend complete suite | 85 passed across 18 files |
| Rust suite and formatting | 21 passed, one intentional controlled-process fixture ignored; formatting passed |
| TypeScript and ESLint | Passed |
| Repeated bubble cycles | Four controlled record/transcribe/idle cycles, interleaved main/popover hides and working bubble toggles passed |
| Repeated Alt+A sequences | Twenty sequences through the real pynput parser/activation handler, including repeat events and both release orders, delivered once each on the main thread |
| Real hidden Tk loop | Twenty queued callbacks delivered on the Tk thread; the keyboard worker returned before the mainloop began |
| Production packaging and installation | GPU NSIS build passed; 0.1.1 update installed with exit code 0 |
| Installed artifact identities | Native executable matches the build apart from the NSIS marker; backend and all 17 CUDA DLLs match exactly |
| Installed isolated native startup | Recoverable empty-cache startup, wrong-owner rejection and owned worker/port exit passed |
| Normal profile startup | CUDA recording resources ready; saved Alt+A preserved; app left running |
| Personal data | Settings and history content unchanged after installation and normal startup; previous executable backups verified |

The normal-profile launch/readiness check completed in 10.953 seconds using
the existing cached model. This is one observation on this machine, not window
paint timing, dictation latency or a cold/clean-machine startup benchmark.
No recording or paste command was sent during the startup check.

Fresh artifact and acceptance records are in
[bubble-shortcut-verification.json](audit-evidence/bubble-shortcut-verification.json)
and [bubble-shortcut-native-owned-acceptance.json](audit-evidence/bubble-shortcut-native-owned-acceptance.json).

The controlled frontend and shortcut tests do not inject physical input or
capture audio. Computer Use initialization still fails with
`failed to write kernel assets: The system cannot find the path specified. (os error 3)`.
Actual bubble clicks/dragging, physical Alt+A presses and real dictation/paste
were therefore not re-tested through Computer Use. Earlier acceptance results
remain historical evidence, not fresh verification of this patch.
