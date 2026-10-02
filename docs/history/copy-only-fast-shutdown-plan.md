# Copy-Only History And Fast Shutdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove paste actions from history UI, polish the settings panel, and make app close stop global input hooks before slow native teardown.

**Architecture:** Keep the existing Tkinter app structure. Add small testable helpers for icon-only copy controls and shutdown ordering instead of broad refactors.

**Tech Stack:** Python, Tkinter, pynput, sounddevice, faster-whisper, Pillow, unittest.

---

### Task 1: Copy-Only History Actions

**Files:**
- Modify: `bubble_dictate.py`
- Modify: `icons.py`
- Test: `test_bubble_dictate.py`
- Test: `test_icons.py`

- [ ] Add tests that quick-history layout exposes `copy_icon_x` and no `paste_x`.
- [ ] Add tests that the full history action layout is copy-only.
- [ ] Add a `copy` glyph renderer in `icons.py`.
- [ ] Replace quick-history Copy/Paste text buttons with one icon-only Copy button.
- [ ] Replace full-history Copy/Paste text buttons with one icon-only Copy button.

### Task 2: Settings Panel Polish

**Files:**
- Modify: `bubble_dictate.py`

- [ ] Keep the panel compact but widen it enough for comfortable spacing.
- [ ] Group form rows with softer nested surfaces.
- [ ] Replace cramped footer with modern icon buttons and consistent padding.
- [ ] Avoid emoji and heavy visual clutter.

### Task 3: Fast Hook-Safe Shutdown

**Files:**
- Modify: `bubble_dictate.py`
- Test: `test_bubble_dictate.py`

- [ ] Add globals for `shutting_down`, `mouse_listener`, and `audio_stream`.
- [ ] Store the mouse listener and audio stream globals in `main()`.
- [ ] Add `shutdown_now()` that stops mouse and keyboard hooks first, stops audio, flushes streams, then calls `os._exit(0)`.
- [ ] Call `shutdown_now()` from `quit_app()` after saving settings and destroying the window.
- [ ] Guard global mouse and hotkey callbacks when shutting down.
- [ ] Keep the old `finally` path as fallback cleanup for non-app exits.

### Task 4: Verification

**Files:**
- No new files.

- [ ] Run targeted failing tests before implementation.
- [ ] Run full unit tests after implementation.
- [ ] Run syntax compile.
- [ ] Run import checks for `config`, `settings`, `icons`, `bubble_dictate`.
- [ ] Run dependency import check for `PIL` and `comtypes`.
- [ ] Run source scan for cloud/API markers.
