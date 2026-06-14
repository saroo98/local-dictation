import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bubble_dictate


class TranscriptHistoryTests(unittest.TestCase):
    def test_add_transcript_to_history_keeps_newest_five(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.json"

            for text in ["one", "two", "three", "four", "five", "six"]:
                history = bubble_dictate.add_transcript_to_history(
                    text,
                    history_path=history_path,
                    limit=5,
                )

            self.assertEqual(history, ["two", "three", "four", "five", "six"])
            self.assertEqual(
                bubble_dictate.load_transcript_history(history_path),
                ["two", "three", "four", "five", "six"],
            )

    def test_add_transcript_to_history_ignores_blank_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.json"

            bubble_dictate.add_transcript_to_history("first", history_path=history_path, limit=5)
            history = bubble_dictate.add_transcript_to_history(
                "   ",
                history_path=history_path,
                limit=5,
            )

            self.assertEqual(history, ["first"])

    def test_history_items_for_display_returns_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.json"

            for text in ["one", "two", "three", "four", "five", "six"]:
                bubble_dictate.add_transcript_to_history(
                    text,
                    history_path=history_path,
                    limit=5,
                )

            self.assertEqual(
                bubble_dictate.history_items_for_display(history_path, limit=5),
                ["six", "five", "four", "three", "two"],
            )

    def test_quick_history_items_for_display_returns_newest_three_with_times(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.json"
            history_path.write_text(
                json.dumps(
                    [
                        {"text": "one", "created_at": "2026-06-14T09:01:00"},
                        {"text": "two", "created_at": "2026-06-14T10:35:00"},
                        {"text": "three", "created_at": "2026-06-14T10:42:00"},
                        {"text": "four", "created_at": "2026-06-14T11:08:00"},
                    ]
                ),
                encoding="utf-8",
            )

            items = bubble_dictate.quick_history_items_for_display(
                history_path=history_path,
                limit=3,
            )

            self.assertEqual([item.text for item in items], ["four", "three", "two"])
            self.assertEqual([item.display_time for item in items], ["11:08 AM", "10:42 AM", "10:35 AM"])

    def test_quick_history_items_supports_old_string_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.json"
            history_path.write_text(json.dumps(["old one", "old two"]), encoding="utf-8")

            items = bubble_dictate.quick_history_items_for_display(
                history_path=history_path,
                limit=3,
            )

            self.assertEqual([item.text for item in items], ["old two", "old one"])
            self.assertEqual([item.display_time for item in items], ["Earlier", "Earlier"])


class TextCleanupTests(unittest.TestCase):
    def test_clean_transcript_text_normalizes_spacing_and_capitalization(self) -> None:
        self.assertEqual(
            bubble_dictate.clean_transcript_text("  hello    there  "),
            "Hello there",
        )

    def test_clean_transcript_text_fixes_duplicate_punctuation(self) -> None:
        self.assertEqual(
            bubble_dictate.clean_transcript_text("hello,,,   world!!!"),
            "Hello, world!",
        )

    def test_clean_transcript_text_converts_spoken_punctuation(self) -> None:
        self.assertEqual(
            bubble_dictate.clean_transcript_text("hello comma world period"),
            "Hello, world.",
        )

    def test_clean_transcript_text_converts_line_break_commands(self) -> None:
        self.assertEqual(
            bubble_dictate.clean_transcript_text("first line new line second line new paragraph third"),
            "First line\nSecond line\n\nThird",
        )


class CliControlTests(unittest.TestCase):
    def test_parse_cli_action_detects_toggle_record(self) -> None:
        self.assertEqual(
            bubble_dictate.parse_cli_action(["--toggle-record"]),
            "toggle-record",
        )

    def test_parse_cli_action_defaults_to_app(self) -> None:
        self.assertEqual(bubble_dictate.parse_cli_action([]), "run-app")

    def test_parse_cli_action_detects_resident(self) -> None:
        self.assertEqual(
            bubble_dictate.parse_cli_action(["--resident"]),
            "resident",
        )

    def test_parse_cli_action_detects_show_history(self) -> None:
        self.assertEqual(
            bubble_dictate.parse_cli_action(["--show-history"]),
            "show-history",
        )

    def test_control_command_for_existing_instance_maps_start_recording_to_toggle(self) -> None:
        self.assertEqual(
            bubble_dictate.control_command_for_existing_instance("start-recording"),
            "toggle-record",
        )

    def test_control_command_for_existing_instance_maps_show_history(self) -> None:
        self.assertEqual(
            bubble_dictate.control_command_for_existing_instance("show-history"),
            "show-history",
        )


class ShortcutSpecTests(unittest.TestCase):
    def test_build_shortcut_specs_returns_expected_shortcuts(self) -> None:
        specs = bubble_dictate.build_shortcut_specs(
            project_dir=Path(r"C:\local-dictation"),
            desktop_dir=Path(r"%USERPROFILE%\Desktop"),
            programs_dir=Path(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
            startup_dir=Path(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
            pythonw_path=Path(r"C:\local-dictation\.venv\Scripts\pythonw.exe"),
        )

        by_name = {spec.name: spec for spec in specs}

        self.assertEqual(
            by_name["desktop-toggle"].shortcut_path,
            Path(r"%USERPROFILE%\Desktop\Local Dictation Toggle.lnk"),
        )
        self.assertEqual(
            by_name["desktop-toggle"].arguments,
            '"C:\\local-dictation\\bubble_dictate.py" --toggle-record',
        )
        self.assertEqual(
            by_name["desktop-history"].arguments,
            '"C:\\local-dictation\\bubble_dictate.py" --show-history',
        )
        self.assertEqual(
            by_name["startup-resident"].arguments,
            '"C:\\local-dictation\\bubble_dictate.py" --resident',
        )

    def test_resolve_pythonw_path_prefers_project_venv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            venv_pythonw = project_dir / ".venv" / "Scripts" / "pythonw.exe"
            venv_pythonw.parent.mkdir(parents=True)
            venv_pythonw.write_text("", encoding="utf-8")

            self.assertEqual(
                bubble_dictate.resolve_pythonw_path(
                    current_python=Path(r"C:\Python312\python.exe"),
                    project_dir=project_dir,
                ),
                venv_pythonw,
            )


class BubbleCloseGestureTests(unittest.TestCase):
    def test_left_hold_for_two_seconds_requests_quit(self) -> None:
        self.assertTrue(
            bubble_dictate.should_quit_from_left_hold(
                hold_seconds=2.0,
                moved=False,
                still_pressed=True,
            )
        )

    def test_left_hold_under_two_seconds_does_not_quit(self) -> None:
        self.assertFalse(
            bubble_dictate.should_quit_from_left_hold(
                hold_seconds=1.99,
                moved=False,
                still_pressed=True,
            )
        )

    def test_left_hold_with_drag_does_not_quit(self) -> None:
        self.assertFalse(
            bubble_dictate.should_quit_from_left_hold(
                hold_seconds=2.5,
                moved=True,
                still_pressed=True,
            )
        )


class BubbleEventBindingTests(unittest.TestCase):
    def test_bubble_events_include_right_click_release_quick_history(self) -> None:
        class FakeWidget:
            def __init__(self) -> None:
                self.bindings = {}

            def bind(self, sequence, handler) -> None:
                self.bindings[sequence] = handler

        app = FakeWidget()
        label = FakeWidget()

        bubble_dictate.bind_bubble_events(app, label)

        for widget in [app, label]:
            self.assertIn("<ButtonPress-1>", widget.bindings)
            self.assertIn("<B1-Motion>", widget.bindings)
            self.assertIn("<ButtonRelease-1>", widget.bindings)
            self.assertIs(
                widget.bindings["<ButtonRelease-3>"],
                bubble_dictate.show_quick_history_popover,
            )
            self.assertIs(
                widget.bindings["<ButtonRelease-2>"],
                bubble_dictate.show_quick_history_popover,
            )


class BubbleReleaseDebounceTests(unittest.TestCase):
    def tearDown(self) -> None:
        bubble_dictate.last_bubble_release_at = None

    def test_duplicate_bubble_release_is_debounced(self) -> None:
        self.assertFalse(bubble_dictate.should_ignore_bubble_release(now=10.0))
        self.assertTrue(bubble_dictate.should_ignore_bubble_release(now=10.05))
        self.assertFalse(
            bubble_dictate.should_ignore_bubble_release(
                now=10.0 + bubble_dictate.config.BUBBLE_RELEASE_DEBOUNCE_SECONDS + 0.01,
            )
        )


class GlobalClickSuppressionTests(unittest.TestCase):
    def tearDown(self) -> None:
        bubble_dictate.ignore_global_left_click_until = 0.0
        bubble_dictate.recording = False
        bubble_dictate.transcribing = False
        bubble_dictate.waiting_for_target_click = False

    def test_recent_bubble_left_click_suppresses_global_click(self) -> None:
        bubble_dictate.remember_bubble_left_click(now=10.0)

        self.assertTrue(bubble_dictate.should_ignore_global_left_click(now=10.1))
        self.assertFalse(
            bubble_dictate.should_ignore_global_left_click(
                now=10.0 + bubble_dictate.config.BUBBLE_GLOBAL_CLICK_IGNORE_SECONDS + 0.01,
            )
        )

    def test_global_click_does_not_fast_paste_during_bubble_click_suppression(self) -> None:
        bubble_dictate.recording = True
        bubble_dictate.transcribing = False
        bubble_dictate.waiting_for_target_click = False
        bubble_dictate.ignore_global_left_click_until = 999999.0

        with patch.object(bubble_dictate, "click_is_inside_bubble", return_value=False), patch.object(
            bubble_dictate,
            "stop_recording",
            side_effect=AssertionError("recording should not stop"),
        ):
            bubble_dictate.on_global_mouse_click(
                999,
                999,
                bubble_dictate.mouse.Button.left,
                True,
            )

    def test_global_click_while_recording_does_not_stop_or_fast_paste(self) -> None:
        bubble_dictate.recording = True
        bubble_dictate.transcribing = False
        bubble_dictate.waiting_for_target_click = False
        bubble_dictate.ignore_global_left_click_until = 0.0

        with patch.object(bubble_dictate, "click_is_inside_bubble", return_value=False), patch.object(
            bubble_dictate,
            "stop_recording",
            side_effect=AssertionError("recording should not stop"),
        ), patch.object(
            bubble_dictate.threading.Thread,
            "start",
            side_effect=AssertionError("paste thread should not start"),
        ):
            bubble_dictate.on_global_mouse_click(
                999,
                999,
                bubble_dictate.mouse.Button.left,
                True,
            )

        self.assertTrue(bubble_dictate.recording)
        self.assertFalse(bubble_dictate.waiting_for_target_click)

    def test_global_click_after_transcription_still_pastes_ready_text(self) -> None:
        bubble_dictate.recording = False
        bubble_dictate.transcribing = False
        bubble_dictate.waiting_for_target_click = True
        bubble_dictate.ignore_global_left_click_until = 0.0

        started = []

        class FakeThread:
            def __init__(self, target, daemon) -> None:
                self.target = target
                self.daemon = daemon

            def start(self) -> None:
                started.append((self.target, self.daemon))

        with patch.object(bubble_dictate, "click_is_inside_bubble", return_value=False), patch.object(
            bubble_dictate.threading,
            "Thread",
            FakeThread,
        ):
            bubble_dictate.on_global_mouse_click(
                999,
                999,
                bubble_dictate.mouse.Button.left,
                True,
            )

        self.assertEqual(started, [(bubble_dictate.paste_after_target_click, True)])


class QuickHistoryPopoverBindingTests(unittest.TestCase):
    def tearDown(self) -> None:
        bubble_dictate.last_quick_history_request_at = 0.0

    def test_quick_popover_closes_on_escape_not_focus_out(self) -> None:
        class FakePopover:
            def __init__(self) -> None:
                self.bindings = {}

            def bind(self, sequence, handler) -> None:
                self.bindings[sequence] = handler

        popover = FakePopover()

        bubble_dictate.bind_quick_popover_close_events(popover)

        self.assertIn("<Escape>", popover.bindings)
        self.assertNotIn("<FocusOut>", popover.bindings)

    def test_quick_history_duplicate_click_is_debounced(self) -> None:
        self.assertFalse(bubble_dictate.should_ignore_quick_history_request(now=10.0))
        self.assertTrue(bubble_dictate.should_ignore_quick_history_request(now=10.1))
        self.assertFalse(
            bubble_dictate.should_ignore_quick_history_request(
                now=10.0 + bubble_dictate.config.QUICK_HISTORY_DEBOUNCE_SECONDS + 0.01,
            )
        )

    def test_quick_history_layout_keeps_third_row_buttons_above_footer(self) -> None:
        layout = bubble_dictate.quick_history_layout()
        third_row_y = layout["row_top"] + (bubble_dictate.config.QUICK_HISTORY_LIMIT - 1) * layout["row_height"]
        third_button_bottom = third_row_y + layout["button_y_offset"] + layout["button_height"]

        self.assertLess(third_button_bottom, layout["footer_separator_y"])

    def test_quick_history_layout_keeps_buttons_inside_right_padding(self) -> None:
        layout = bubble_dictate.quick_history_layout()

        self.assertLessEqual(
            layout["paste_x"] + layout["button_width"],
            bubble_dictate.config.QUICK_HISTORY_WIDTH - layout["panel_pad"] - 14,
        )
        self.assertLess(
            layout["text_x"] + layout["transcript_width"],
            layout["copy_x"] - 18,
        )

    def test_quick_history_preview_is_clamped_to_two_lines(self) -> None:
        lines = bubble_dictate.quick_history_preview_lines(
            "I want to create a skill for codex and clones. The skill is for people in that workflow.",
            max_lines=2,
            max_line_chars=28,
        )

        self.assertLessEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("..."))
        self.assertTrue(all(len(line) <= 28 for line in lines))

    def test_quick_history_pointer_is_inside_panel_right_edge(self) -> None:
        layout = bubble_dictate.quick_history_layout()

        self.assertGreater(layout["pointer_tip_x"], bubble_dictate.config.QUICK_HISTORY_WIDTH - 70)
        self.assertLessEqual(layout["pointer_base_right"], bubble_dictate.config.QUICK_HISTORY_WIDTH - layout["panel_pad"])
        self.assertGreater(layout["pointer_base_left"], layout["pointer_tip_x"] - 30)


class BubbleIconTests(unittest.TestCase):
    def test_ready_and_recording_states_use_shape_icons(self) -> None:
        self.assertEqual(
            bubble_dictate.bubble_icon_for_state(bubble_dictate.config.READY_LABEL),
            "play",
        )
        self.assertEqual(
            bubble_dictate.bubble_icon_for_state(bubble_dictate.config.RECORDING_LABEL),
            "stop",
        )


class DiagnosticLoggingTests(unittest.TestCase):
    def tearDown(self) -> None:
        bubble_dictate.session_log_file = None

    def test_initialize_logging_writes_legacy_and_session_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            legacy_log = temp_path / "dictation_debug.log"
            log_dir = temp_path / "logs"

            session_log = bubble_dictate.initialize_logging(
                log_dir=log_dir,
                legacy_log_file=legacy_log,
                started_at=bubble_dictate.datetime(2026, 6, 14, 12, 0, 0),
                pid=1234,
            )
            bubble_dictate.log(
                "diagnostic hello",
                timestamp=bubble_dictate.datetime(2026, 6, 14, 12, 0, 1),
                pid=1234,
                legacy_log_file=legacy_log,
            )

            self.assertEqual(
                session_log,
                log_dir / "dictation_20260614_120000_pid1234.log",
            )
            self.assertIn("diagnostic hello", legacy_log.read_text(encoding="utf-8"))
            self.assertIn("diagnostic hello", session_log.read_text(encoding="utf-8"))

    def test_prune_old_session_logs_keeps_newest_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            old = log_dir / "dictation_20260614_120000_pid1.log"
            middle = log_dir / "dictation_20260614_120100_pid1.log"
            newest = log_dir / "dictation_20260614_120200_pid1.log"

            for index, path in enumerate([old, middle, newest], start=1):
                path.write_text(str(index), encoding="utf-8")
                os_time = 1000 + index
                path.touch()
                bubble_dictate.os.utime(path, (os_time, os_time))

            bubble_dictate.prune_old_session_logs(log_dir, keep_count=2)

            self.assertFalse(old.exists())
            self.assertTrue(middle.exists())
            self.assertTrue(newest.exists())

    def test_recording_stop_diagnostics_identifies_immediate_zero_chunk_stop(self) -> None:
        diagnostic = bubble_dictate.recording_stop_diagnostic_summary(
            session_id=7,
            stop_reason="bubble-left-click",
            duration_seconds=0.08,
            chunks_captured=0,
            callback_chunks=0,
            callback_frames=0,
            first_audio_delay=None,
            last_audio_age=None,
            status_events=[],
        )

        self.assertIn("session=7", diagnostic)
        self.assertIn("duration=0.08s", diagnostic)
        self.assertIn("chunks=0", diagnostic)
        self.assertIn("likely-immediate-stop", diagnostic)

    def test_recording_stop_diagnostics_identifies_no_audio_callbacks(self) -> None:
        diagnostic = bubble_dictate.recording_stop_diagnostic_summary(
            session_id=8,
            stop_reason="bubble-left-click",
            duration_seconds=1.2,
            chunks_captured=0,
            callback_chunks=0,
            callback_frames=0,
            first_audio_delay=None,
            last_audio_age=None,
            status_events=[],
        )

        self.assertIn("stream-delivered-no-callbacks", diagnostic)


class LaunchLockTests(unittest.TestCase):
    def test_try_create_launch_lock_rejects_fresh_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "launch.lock"

            self.assertTrue(bubble_dictate.try_create_launch_lock(lock_path, now=100.0, pid=1))
            self.assertFalse(bubble_dictate.try_create_launch_lock(lock_path, now=101.0, pid=2))

    def test_try_create_launch_lock_replaces_stale_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "launch.lock"

            self.assertTrue(bubble_dictate.try_create_launch_lock(lock_path, now=100.0, pid=1))
            self.assertTrue(
                bubble_dictate.try_create_launch_lock(
                    lock_path,
                    now=100.0 + bubble_dictate.config.LAUNCH_LOCK_STALE_SECONDS + 1.0,
                    pid=2,
                )
            )
            self.assertIn("pid=2", lock_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
