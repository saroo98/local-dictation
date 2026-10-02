# Audit evidence

These files distinguish the 2026-10-02 baseline audit of `462ce340` from its
authorized implementation. They contain dependency/check metadata and synthetic
test output. The current result is described in `../verification.md`.

- `cleanup-manifest.json`: source moves, preserved archive and compatibility scope.
- `validation.json`: checks actually run, browser measurements and the native compiler memory blocker.
- `cleanup-verification.json`: preserved source comparisons, checked links, finding/task coverage, live remote refs and unstaged Git state.
- `dependency-snapshot.json`: exact versions queried from the current Python environment and Cargo lock.
- `npm-advisories.json`: npm audit response; counts are package entries, not unique vulnerabilities.
- `osv-advisories.json`: matched package versions, advisory identifiers, affected ranges and references. Aliases and maintenance notices must be distinguished from exploitable defects.

Current implementation evidence:

- `implementation-verification.json`: final source/check/artifact metadata and
  runtime-data preservation checks.
- `python-implementation-tests.log`, `python-clean-tests.log`: 189 passing tests.
- `frontend-implementation-tests.log`: 82 passing tests across 17 files.
- `native-implementation-tests.log`: 21 passing tests and one deliberately
  ignored fixture invoked by the Windows managed-job test.
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
