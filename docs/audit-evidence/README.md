# Audit evidence

These files distinguish the 2026-10-02 baseline audit of `462ce340` from its
authorized implementation. They contain dependency/check metadata and synthetic
test output. The current result is described in `../verification.md`.

Public records omit personal profile/archive paths, personal file sizes and
timestamps, process/window identifiers and unrelated foreground diagnostics.
Affected JSON records list their `privacy_redactions`. `<repository>` means
the source root; `%LOCALAPPDATA%`, `%APPDATA%` and `%USERPROFILE%` are portable
Windows path descriptions. These are sanitized reports of the original checks,
not fresh test runs. Original records are retained only in ignored local build
output and must not be packaged or published.

- `cleanup-manifest.json`: source moves, preserved archive and compatibility scope.
- `validation.json`: checks actually run, browser measurements and the native compiler memory blocker.
- `cleanup-verification.json`: preserved source comparisons, checked links, finding/task coverage, live remote refs and unstaged Git state.
- `dependency-snapshot.json`: exact versions queried from the current Python environment and Cargo lock.
- `npm-advisories.json`: npm audit response; counts are package entries, not unique vulnerabilities.
- `osv-advisories.json`: matched package versions, advisory identifiers, affected ranges and references. Aliases and maintenance notices must be distinguished from exploitable defects.

Current implementation evidence:

- `implementation-verification.json`: pre-commit source/check/artifact metadata
  and runtime-data preservation checks at the end of implementation.
- `installation-verification.json`: owner-authorized installed upgrade, exact
  packaged-file identities, fresh checks and unchanged settings/history content.
- `installed-native-owned-acceptance.json`, `installed-native-passive-acceptance.json`:
  isolated real startup/job/port exit and passive HWND/bubble checks against the
  installed package, which has Tauri's expected three-byte NSIS bundle marker.
- Local untracked test logs record the earlier 189 Python, 82 frontend and 21
  native passing tests, plus the deliberate native subprocess fixture. The
  latest 0.1.1 counts are in `bubble-shortcut-verification.json`.
- `backend-source-acceptance.json`, `backend-frozen-acceptance.json`: real
  isolated backend startup/recovery/shutdown and optional offline CPU/CUDA warmup.
- `native-owned-startup-red.json`: actual pre-fix Windows connection-timeout
  startup failure. `native-owned-acceptance.json` records the corrected owned
  native launch and controlled abrupt shutdown, not tray Quit.
- `native-passive-acceptance.json`: real current HWND geometry/markers/activation
  responses, embedded bubble control and persistent close behavior.
- `native-window-acceptance.json`: failed controlled-target activation and the
  actual pointer checks that were never reached. This is not a bubble pass/fail.
- `status-pill-contrast.json`, `bubble-icon-contrast.json`: scoped actual rendered
  CSS color measurements with transitions disabled for stable readings.
- `implementation-npm-audit.json`, `implementation-advisories.json`: current
  dependency checks; baseline advisory files above remain historical.

Compiler/package diagnostics and acceptance helpers are generated under
`build/` or `desktop/src-tauri/target/`, not committed source. Passing these
checks does not close the documented interactive or clean-install boundaries.
