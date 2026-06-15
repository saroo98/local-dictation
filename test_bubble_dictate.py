import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def test_clean_transcript_text_skips_spoken_punctuation_for_non_english(self) -> None:
        self.assertEqual(
            bubble_dictate.clean_transcript_text("کاما comma", language="fa"),
            "کاما comma",
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
            layout["copy_x"] + layout["button_width"],
            bubble_dictate.config.QUICK_HISTORY_WIDTH - layout["panel_pad"] - 14,
        )
        self.assertLess(
            layout["text_x"] + layout["transcript_width"],
            layout["copy_x"] - 18,
        )
        self.assertIn("copy_icon_x", layout)
        self.assertNotIn("paste_x", layout)

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

    def test_quick_history_layout_is_compact_and_prevents_text_overlap(self) -> None:
        layout = bubble_dictate.quick_history_layout()

        self.assertLessEqual(bubble_dictate.config.QUICK_HISTORY_WIDTH, 410)
        self.assertLessEqual(bubble_dictate.config.QUICK_HISTORY_HEIGHT, 290)
        self.assertLessEqual(layout["button_width"], 36)
        self.assertLessEqual(layout["time_font_size"], 10)
        self.assertLessEqual(layout["transcript_font_size"], 12)
        self.assertGreaterEqual(layout["transcript_width"], 300)
        self.assertLess(layout["footer_separator_y"], layout["footer_y"])
        self.assertLessEqual(
            layout["pointer_base_right"] - layout["pointer_base_left"],
            16,
        )
        self.assertLessEqual(
            bubble_dictate.config.QUICK_HISTORY_POINTER_SIZE,
            12,
        )

        estimated_line_width = int(layout["preview_line_chars"] * layout["transcript_font_size"] * 0.58)
        self.assertLessEqual(
            layout["text_x"] + estimated_line_width,
            layout["copy_x"] - 18,
        )

        transcript_text_bottom = (
            layout["row_top"]
            + layout["transcript_y_offset"]
            + layout["transcript_line_gap"]
            + int(layout["transcript_font_size"] * 1.4)
        )
        self.assertGreaterEqual(
            layout["row_top"] + layout["row_separator_offset"],
            transcript_text_bottom + 10,
        )

    def test_quick_history_layout_uses_safe_two_line_rows(self) -> None:
        layout = bubble_dictate.quick_history_layout()

        self.assertEqual(layout.get("preview_max_lines"), 2)
        self.assertLessEqual(bubble_dictate.config.QUICK_HISTORY_POINTER_SIZE, 12)
        self.assertLessEqual(
            layout["pointer_base_right"] - layout["pointer_base_left"],
            16,
        )
        self.assertGreaterEqual(layout["copy_icon_size"], 15)
        self.assertGreaterEqual(layout["button_width"], 34)

    def test_quick_history_preview_uses_pixel_width_and_two_lines(self) -> None:
        layout = bubble_dictate.quick_history_layout()
        text = "I was just born playing the guitar But all the tricks wasn't too hard"

        lines = bubble_dictate.wrap_text_to_pixel_lines(
            text,
            max_lines=layout["preview_max_lines"],
            max_width=layout["transcript_width"],
            measure=lambda value: len(value) * 7,
        )

        preview = " ".join(lines)
        self.assertLessEqual(len(lines), 2)
        self.assertIn("guitar", preview)
        self.assertIn("tricks", preview)
        self.assertNotEqual(preview, "I was just born playing t...")
        self.assertTrue(all(len(line) * 7 <= layout["transcript_width"] for line in lines))

    def test_quick_history_layout_keeps_play_bubble_visually_attached(self) -> None:
        layout = bubble_dictate.quick_history_layout()

        self.assertLessEqual(layout.get("bubble_gap", 99), 3)

    def test_quick_history_pointer_uses_smooth_compact_tail_geometry(self) -> None:
        layout = bubble_dictate.quick_history_layout()

        self.assertTrue(layout.get("pointer_smooth"))
        self.assertEqual(layout.get("tail_renderer"), "pillow")
        self.assertLessEqual(layout.get("pointer_tip_y_offset", 99), 10)
        self.assertLessEqual(
            layout["pointer_base_right"] - layout["pointer_base_left"],
            16,
        )

    @unittest.skipUnless(bubble_dictate.icons.PIL_AVAILABLE, "Pillow unavailable")
    def test_quick_history_background_renderer_returns_antialiased_rgba_tail(self) -> None:
        layout = bubble_dictate.quick_history_layout()
        image = bubble_dictate.render_quick_popover_background(
            bubble_dictate.config.QUICK_HISTORY_WIDTH,
            bubble_dictate.config.QUICK_HISTORY_HEIGHT,
            layout,
            {
                "panel_bg": "#080c12",
                "panel_border": "#4b5563",
                "inner_border": "#202936",
            },
        )

        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(
            image.size,
            (bubble_dictate.config.QUICK_HISTORY_WIDTH, bubble_dictate.config.QUICK_HISTORY_HEIGHT),
        )
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertGreater(image.getpixel((layout["pointer_tip_x"], layout["pointer_tip_y"]))[3], 0)


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


class SafeConsolePrintTests(unittest.TestCase):
    def tearDown(self) -> None:
        bubble_dictate.session_log_file = None

    def test_log_survives_console_unicode_encode_error(self) -> None:
        # Simulate a cp1252 console that cannot encode the paste check mark,
        # which previously raised out of set_bubble and flipped the bubble
        # into the error state after a successful paste.
        def raising_print(*_args, **_kwargs):
            raise UnicodeEncodeError("charmap", "✓", 0, 1, "undefined")

        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_log = Path(temp_dir) / "dictation_debug.log"

            with patch("builtins.print", raising_print):
                try:
                    bubble_dictate.log(
                        "Bubble state requested: text=✓ bg=#188038",
                        legacy_log_file=legacy_log,
                    )
                except UnicodeEncodeError:
                    self.fail("log() must not raise when the console cannot encode a glyph")

            self.assertIn("✓", legacy_log.read_text(encoding="utf-8"))


class BubbleErrorGlyphTests(unittest.TestCase):
    def test_error_label_does_not_fall_back_to_text_icon(self) -> None:
        # The error state is drawn as a vector glyph, not the generic text path.
        self.assertEqual(
            bubble_dictate.bubble_icon_for_state(bubble_dictate.config.ERROR_LABEL),
            "text",
        )

    def test_lighten_color_returns_lighter_hex(self) -> None:
        lighter = bubble_dictate.lighten_color("#1f6f4a")
        self.assertTrue(lighter.startswith("#") and len(lighter) == 7)
        self.assertNotEqual(lighter, "#1f6f4a")

    def test_lighten_color_handles_bad_input(self) -> None:
        self.assertEqual(bubble_dictate.lighten_color("nope"), "nope")


class HotkeyTests(unittest.TestCase):
    def test_valid_hotkey(self) -> None:
        self.assertTrue(bubble_dictate.is_valid_hotkey("<ctrl>+<alt>+d"))

    def test_blank_hotkey_is_invalid(self) -> None:
        self.assertFalse(bubble_dictate.is_valid_hotkey("   "))

    def test_garbage_hotkey_is_invalid(self) -> None:
        self.assertFalse(bubble_dictate.is_valid_hotkey("not a key combo"))

    def test_hotkey_capture_replaces_existing_text_with_single_key(self) -> None:
        event = SimpleNamespace(keysym="g", char="g", state=0)

        self.assertEqual(bubble_dictate.hotkey_from_key_event(event), "g")

    def test_hotkey_capture_formats_ctrl_alt_combo(self) -> None:
        event = SimpleNamespace(keysym="d", char="d", state=0x0004 | 0x0008)

        self.assertEqual(bubble_dictate.hotkey_from_key_event(event), "<ctrl>+<alt>+d")

    def test_hotkey_capture_can_clear_field(self) -> None:
        event = SimpleNamespace(keysym="BackSpace", char="", state=0)

        self.assertEqual(bubble_dictate.hotkey_from_key_event(event), "")


class SettingsLayoutFooterTests(unittest.TestCase):
    def test_quick_history_layout_has_compact_four_action_footer(self) -> None:
        layout = bubble_dictate.quick_history_layout()

        for key in ("settings_icon_x", "settings_x", "history_icon_x",
                    "history_x", "tray_icon_x", "tray_x",
                    "close_icon_x", "close_x",
                    "footer_divider_x", "footer_divider2_x", "footer_divider3_x"):
            self.assertIn(key, layout)

        self.assertLess(layout["settings_x"], layout["history_x"])
        self.assertLess(layout["history_x"], layout["tray_x"])
        self.assertLess(layout["tray_x"], layout["close_x"])
        self.assertLessEqual(layout["footer_font_size"], 10)
        self.assertLessEqual(layout["footer_icon_size"], 14)
        self.assertEqual(layout["footer_actions"], ["Settings", "History", "Tray", "Close app"])

    def test_settings_layout_is_compact_premium_dialog(self) -> None:
        layout = bubble_dictate.settings_panel_layout()

        self.assertGreaterEqual(layout["width"], 560)
        self.assertLessEqual(layout["width"], 640)
        self.assertGreaterEqual(layout["height"], 600)
        self.assertLessEqual(layout["height"], 640)
        self.assertEqual(
            layout["sections"],
            ["Transcription", "Interface & Output", "Commands & Hotkeys"],
        )
        self.assertEqual(
            layout["footer_actions"],
            ["History", "Export", "Close app", "Save changes"],
        )
        self.assertEqual(layout["primary_action"], "Save changes")
        self.assertGreater(layout["control_width"], layout["label_width"])

    def test_settings_layout_removes_far_right_control_dead_zone(self) -> None:
        layout = bubble_dictate.settings_panel_layout()

        self.assertLessEqual(layout["width"], 640)
        self.assertLessEqual(layout["height"], 640)
        self.assertEqual(layout.get("control_alignment"), "left")
        self.assertLessEqual(layout.get("control_start_x", 999), 240)
        self.assertLessEqual(layout["section_pad_x"], 12)
        self.assertGreaterEqual(layout.get("section_gap", 0), 8)
        self.assertLessEqual(layout.get("close_button_size", 99), 24)

    def test_settings_layout_reserves_space_for_hotkey_help_text(self) -> None:
        layout = bubble_dictate.settings_panel_layout()

        self.assertGreaterEqual(layout.get("commands_min_height", 0), 92)
        self.assertLessEqual(layout.get("help_wraplength", 999), 520)
        self.assertGreaterEqual(layout.get("help_reserved_lines", 0), 2)
        self.assertGreaterEqual(layout.get("model_info_reserved_lines", 0), 2)
        self.assertGreaterEqual(layout.get("model_info_font_size", 0), 8)
        self.assertIn("model_folder_label_width", layout)
        self.assertIn("model_order_label_width", layout)
        self.assertGreaterEqual(layout.get("minimum_font_size", 0), 8)
        self.assertGreaterEqual(layout.get("manual_model_font_size", 0), layout["minimum_font_size"])
        self.assertGreaterEqual(layout.get("hotkey_help_font_size", 0), layout["minimum_font_size"])
        self.assertGreaterEqual(layout.get("commands_min_height", 0), 112)

    def test_settings_light_palette_is_soft_and_subdued(self) -> None:
        original_theme = bubble_dictate.SETTINGS["theme"]
        bubble_dictate.SETTINGS["theme"] = "Light Mode"
        try:
            palette = bubble_dictate.settings_visual_palette({})
        finally:
            bubble_dictate.SETTINGS["theme"] = original_theme

        self.assertEqual(palette["panel_bg"], "#f8f7f3")
        self.assertEqual(palette["row_ring"], "#e4ded2")
        self.assertEqual(palette["accent_bg"], "#1f7f70")

    def test_settings_drag_binding_reaches_nested_header_labels_not_buttons(self) -> None:
        class FakeWidget:
            def __init__(self, children=None) -> None:
                self.children = children or []
                self.bindings = {}

            def bind(self, sequence, handler) -> None:
                self.bindings[sequence] = handler

            def winfo_children(self):
                return self.children

        class FakeButton(FakeWidget):
            pass

        title_label = FakeWidget()
        subtitle_label = FakeWidget()
        title_stack = FakeWidget([title_label, subtitle_label])
        close_button = FakeButton()
        close_shell = FakeWidget([close_button])
        header = FakeWidget([title_stack, close_shell])

        class FakeWindow:
            def winfo_x(self) -> int:
                return 100

            def winfo_y(self) -> int:
                return 200

            def geometry(self, _value: str) -> None:
                pass

        with patch.object(bubble_dictate.tk, "Button", FakeButton):
            bubble_dictate.bind_panel_drag(FakeWindow(), header)

        for widget in (header, title_stack, title_label, subtitle_label, close_shell):
            self.assertIn("<ButtonPress-1>", widget.bindings)
            self.assertIn("<B1-Motion>", widget.bindings)

        self.assertEqual(close_button.bindings, {})


class SettingsApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_settings = dict(bubble_dictate.SETTINGS)

    def tearDown(self) -> None:
        bubble_dictate.SETTINGS = self.original_settings

    def _vars(self, **overrides):
        values = dict(bubble_dictate.SETTINGS)
        values.update(overrides)

        class Var:
            def __init__(self, value) -> None:
                self.value = value

            def get(self):
                return self.value

            def set(self, value) -> None:
                self.value = value

        return {key: Var(value) for key, value in values.items() if key != "bubble_position"}

    def test_apply_settings_saves_without_closing_settings_panel(self) -> None:
        vars_ = self._vars(theme="Light Mode")

        with patch.object(bubble_dictate.settings, "save_settings"), patch.object(
            bubble_dictate, "restart_hotkey_listener"
        ), patch.object(bubble_dictate, "redraw_bubble_current_state"), patch.object(
            bubble_dictate, "close_settings_panel"
        ) as close_panel, patch.object(
            bubble_dictate, "refresh_settings_panel"
        ) as refresh_panel:
            bubble_dictate.apply_settings_from_form(vars_)

        close_panel.assert_not_called()
        refresh_panel.assert_called_once()
        self.assertEqual(bubble_dictate.SETTINGS["theme"], "Light Mode")

    def test_apply_settings_keeps_previous_model_when_offline_model_missing(self) -> None:
        bubble_dictate.SETTINGS["model"] = "Balanced"
        vars_ = self._vars(model="Fast")

        with patch.object(bubble_dictate.settings, "model_is_available_locally", return_value=False), patch.object(
            bubble_dictate.settings, "save_settings"
        ), patch.object(bubble_dictate, "restart_hotkey_listener"), patch.object(
            bubble_dictate, "redraw_bubble_current_state"
        ), patch.object(bubble_dictate.threading.Thread, "start") as thread_start:
            bubble_dictate.apply_settings_from_form(vars_)

        self.assertEqual(bubble_dictate.SETTINGS["model"], "Balanced")
        self.assertEqual(vars_["model"].get(), "Balanced")
        thread_start.assert_not_called()

    def test_apply_settings_preserves_custom_models(self) -> None:
        custom_models = [{"name": "Repo Custom", "source": "Systran/faster-whisper-base"}]
        bubble_dictate.SETTINGS["custom_models"] = custom_models
        bubble_dictate.SETTINGS["model"] = "Repo Custom"
        vars_ = self._vars(theme="Light Mode")
        vars_.pop("custom_models", None)

        with patch.object(bubble_dictate.settings, "save_settings"), patch.object(
            bubble_dictate, "restart_hotkey_listener"
        ), patch.object(bubble_dictate, "redraw_bubble_current_state"), patch.object(
            bubble_dictate, "refresh_settings_panel"
        ):
            bubble_dictate.apply_settings_from_form(vars_)

        self.assertEqual(bubble_dictate.SETTINGS["custom_models"], custom_models)
        self.assertEqual(bubble_dictate.SETTINGS["model"], "Repo Custom")


class ModelDownloadTests(unittest.TestCase):
    def test_missing_model_exposes_download_button_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state = bubble_dictate.model_download_button_state("Fast", cache_root=Path(temp_dir))

        self.assertTrue(state["visible"])
        self.assertTrue(state["enabled"])
        self.assertEqual(state["text"], "Download")

    def test_installed_model_disables_download_button_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)
            repo_dir = cache_root / "models--Systran--faster-whisper-small"
            snapshot = repo_dir / "snapshots" / "abc123"
            snapshot.mkdir(parents=True)
            (repo_dir / "refs").mkdir()
            (repo_dir / "refs" / "main").write_text("abc123", encoding="utf-8")
            (snapshot / "model.bin").write_bytes(b"x")

            state = bubble_dictate.model_download_button_state("Fast", cache_root=cache_root)

        self.assertTrue(state["visible"])
        self.assertFalse(state["enabled"])
        self.assertEqual(state["text"], "Installed")

    def test_download_known_model_uses_faster_whisper_with_online_lookup_only_when_called(self) -> None:
        calls = []

        def fake_download_model(*args, **kwargs):
            calls.append((args, kwargs))
            return "downloaded"

        result = bubble_dictate.download_model_for_choice(
            "Fast",
            download_model_func=fake_download_model,
        )

        self.assertEqual(result, "downloaded")
        self.assertEqual(calls[0][0][0], "small")
        self.assertFalse(calls[0][1]["local_files_only"])

    def test_download_custom_repo_uses_snapshot_download(self) -> None:
        calls = []

        def fake_snapshot_download(**kwargs):
            calls.append(kwargs)
            return "snapshot"

        result = bubble_dictate.download_model_for_choice(
            "Repo Custom",
            custom_models=[{"name": "Repo Custom", "source": "Systran/faster-whisper-base"}],
            snapshot_download_func=fake_snapshot_download,
        )

        self.assertEqual(result, "snapshot")
        self.assertEqual(calls[0]["repo_id"], "Systran/faster-whisper-base")
        self.assertFalse(calls[0]["local_files_only"])
        self.assertIn("model.bin", calls[0]["allow_patterns"])


class HistoryPanelLayoutTests(unittest.TestCase):
    def test_history_panel_actions_are_copy_only(self) -> None:
        layout = bubble_dictate.history_panel_layout()

        self.assertEqual(layout["action_count"], 1)
        self.assertIn("copy_icon_size", layout)
        self.assertNotIn("paste_column", layout)


class TrayTests(unittest.TestCase):
    def tearDown(self) -> None:
        bubble_dictate.root = None
        bubble_dictate.tray_icon = None
        bubble_dictate.shutting_down = False
        with bubble_dictate.state_lock:
            bubble_dictate.recording = False
            bubble_dictate.transcribing = False
            bubble_dictate.waiting_for_target_click = False

    def test_tray_status_maps_expected_states(self) -> None:
        expected = {
            "ready": ("play", bubble_dictate.config.READY_BG, "Ready"),
            "recording": ("stop", bubble_dictate.config.RECORDING_BG, "Recording"),
            "transcribing": ("ellipsis", bubble_dictate.config.TRANSCRIBING_BG, "Transcribing"),
            "paste-ready": ("paste", bubble_dictate.config.PASTE_READY_BG, "Paste ready"),
            "error": ("error", bubble_dictate.config.ERROR_BG, "Error"),
        }

        for state, (glyph, color, title_fragment) in expected.items():
            with self.subTest(state=state):
                status = bubble_dictate.tray_status_for_state(state)

                self.assertEqual(status["glyph"], glyph)
                self.assertEqual(status["bg"], color)
                self.assertIn(title_fragment, status["title"])

    def test_tray_state_tracks_current_app_state(self) -> None:
        self.assertEqual(bubble_dictate.tray_state_from_bubble("anything", "#000000"), "ready")
        self.assertEqual(
            bubble_dictate.tray_state_from_bubble(
                bubble_dictate.config.RECORDING_LABEL,
                bubble_dictate.config.RECORDING_BG,
            ),
            "recording",
        )
        self.assertEqual(
            bubble_dictate.tray_state_from_bubble(
                bubble_dictate.config.TRANSCRIBING_LABEL,
                bubble_dictate.config.TRANSCRIBING_BG,
            ),
            "transcribing",
        )
        self.assertEqual(
            bubble_dictate.tray_state_from_bubble(
                bubble_dictate.config.PASTE_READY_LABEL,
                bubble_dictate.config.PASTE_READY_BG,
            ),
            "paste-ready",
        )
        self.assertEqual(
            bubble_dictate.tray_state_from_bubble(
                bubble_dictate.config.ERROR_LABEL,
                bubble_dictate.config.ERROR_BG,
            ),
            "error",
        )

    def test_build_tray_menu_includes_core_actions_and_default_toggle(self) -> None:
        fake_pystray = self._fake_pystray()

        with patch.object(bubble_dictate, "pystray", fake_pystray):
            menu = bubble_dictate.build_tray_menu()

        items = [item for item in menu if item is not fake_pystray.Menu.SEPARATOR]
        visible_texts = [self._menu_text(item) for item in items if item.visible]

        self.assertTrue(items[0].default)
        self.assertFalse(items[0].visible)
        self.assertIn("Show Bubble", visible_texts)
        self.assertIn("Start Recording", visible_texts)
        self.assertIn("History", visible_texts)
        self.assertIn("Settings", visible_texts)
        self.assertIn("Quit", visible_texts)

    def test_tray_callbacks_schedule_through_tk(self) -> None:
        calls = []

        class FakeRoot:
            def after(self, delay_ms, callback):
                calls.append((delay_ms, callback))

        bubble_dictate.root = FakeRoot()

        bubble_dictate.on_tray_toggle_recording()

        self.assertEqual(calls, [(0, bubble_dictate.toggle_recording_from_shortcut)])

    def test_start_tray_icon_noops_when_pystray_is_unavailable(self) -> None:
        with patch.object(bubble_dictate, "pystray", None), patch.object(
            bubble_dictate, "log"
        ) as log:
            started = bubble_dictate.start_tray_icon()

        self.assertFalse(started)
        log.assert_called()

    def test_start_tray_icon_runs_detached_when_available(self) -> None:
        fake_pystray = self._fake_pystray()

        with patch.object(bubble_dictate, "pystray", fake_pystray):
            started = bubble_dictate.start_tray_icon()

        self.assertTrue(started)
        self.assertIsNotNone(bubble_dictate.tray_icon)
        self.assertEqual(bubble_dictate.tray_icon.run_calls, 1)

    def _fake_pystray(self):
        class FakeMenu(tuple):
            SEPARATOR = object()

            def __new__(cls, *items):
                return tuple.__new__(cls, items)

        class FakeMenuItem:
            def __init__(
                self,
                text,
                action=None,
                default=False,
                visible=True,
                enabled=True,
            ) -> None:
                self.text = text
                self.action = action
                self.default = default
                self.visible = visible
                self.enabled = enabled

        class FakeIcon:
            def __init__(self, name, icon=None, title=None, menu=None) -> None:
                self.name = name
                self.icon = icon
                self.title = title
                self.menu = menu
                self.run_calls = 0
                self.stop_calls = 0
                self.update_menu_calls = 0

            def run_detached(self):
                self.run_calls += 1

            def stop(self):
                self.stop_calls += 1

            def update_menu(self):
                self.update_menu_calls += 1

        return SimpleNamespace(Menu=FakeMenu, MenuItem=FakeMenuItem, Icon=FakeIcon)

    def _menu_text(self, item) -> str:
        value = item.text
        if callable(value):
            return value(item)
        return value


class ShutdownTests(unittest.TestCase):
    def tearDown(self) -> None:
        bubble_dictate.shutting_down = False
        bubble_dictate.mouse_listener = None
        bubble_dictate.hotkey_listener = None
        bubble_dictate.audio_stream = None
        bubble_dictate.tray_icon = None
        bubble_dictate.root = None

    def test_shutdown_now_stops_hooks_before_hard_exit(self) -> None:
        calls = []

        class Stopper:
            def __init__(self, name) -> None:
                self.name = name

            def stop(self) -> None:
                calls.append(f"{self.name}.stop")

        class ExitCalled(Exception):
            pass

        bubble_dictate.mouse_listener = Stopper("mouse")
        bubble_dictate.hotkey_listener = Stopper("hotkey")
        bubble_dictate.tray_icon = Stopper("tray")
        bubble_dictate.audio_stream = Stopper("audio")

        with patch.object(bubble_dictate.os, "_exit", side_effect=ExitCalled), patch.object(
            bubble_dictate, "log"
        ):
            with self.assertRaises(ExitCalled):
                bubble_dictate.shutdown_now()

        self.assertEqual(
            calls,
            ["mouse.stop", "hotkey.stop", "tray.stop", "audio.stop"],
        )
        self.assertTrue(bubble_dictate.shutting_down)

    def test_global_mouse_click_returns_during_shutdown(self) -> None:
        bubble_dictate.shutting_down = True

        with patch.object(bubble_dictate, "click_is_inside_bubble", side_effect=AssertionError):
            bubble_dictate.on_global_mouse_click(10, 10, bubble_dictate.mouse.Button.left, True)

    def test_hotkey_toggle_returns_during_shutdown(self) -> None:
        class FakeRoot:
            def after(self, *_args, **_kwargs) -> None:
                raise AssertionError("hotkey must not schedule work during shutdown")

        bubble_dictate.shutting_down = True
        bubble_dictate.root = FakeRoot()

        bubble_dictate.on_hotkey_toggle()


if __name__ == "__main__":
    unittest.main()
