import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import bubble_dictate as app
import settings


class DeliveryTests(unittest.TestCase):
    def test_new_recording_during_history_write_prevents_old_clipboard_delivery(self):
        def persist(_text):
            app.current_recording_session_id = 8
        with patch.object(app, 'current_recording_session_id', 7), patch.object(app, 'transcribing', True), patch.object(app, 'waiting_for_target_click', False), patch.object(app, 'paste_after_transcription', False), patch.object(app, 'latest_transcript', None), patch.object(app, 'transcribe_audio', return_value='Old result'), patch.object(app, 'add_transcript_to_history', side_effect=persist), patch.object(app.pyperclip, 'copy') as copy, patch.object(app, 'set_bubble'), patch.object(app, 'focused_field_is_editable', return_value=False):
            app.process_recording([app.np.zeros(100, dtype='float32')], 7)
            copy.assert_not_called()

    def test_new_recording_during_clipboard_acquisition_prevents_injection(self):
        def copy(_text):
            app.current_recording_session_id = 8
        with patch.object(app, 'current_recording_session_id', 7), patch.object(app, 'focused_editable_target', return_value=(100, (1,))), patch.object(app.time, 'sleep'), patch.object(app.pyperclip, 'copy', side_effect=copy), patch.object(app.pyautogui, 'hotkey') as inject, patch.object(app, 'set_bubble'):
            self.assertFalse(app.paste_text_to_active_target('Old result', session_id=7))
            inject.assert_not_called()

    def test_global_click_passes_the_click_point_to_pending_delivery(self):
        with patch.object(app, 'shutting_down', False), patch.object(app, 'waiting_for_target_click', True), patch.object(app, 'should_ignore_global_left_click', return_value=False), patch.object(app, 'click_is_inside_bubble', return_value=False), patch.object(app.threading, 'Thread') as worker:
            app.on_global_mouse_click(10, 20, app.mouse.Button.left, False)
            self.assertEqual(worker.call_args.kwargs.get('kwargs'), {'click_point': (10, 20)})

    def test_title_bar_click_preserves_pending_text_without_delivery(self):
        with patch.object(app, 'waiting_for_target_click', True), patch.object(app, 'latest_transcript', 'Retained'), patch.object(app, 'current_recording_session_id', 7), patch.object(app, 'focused_editable_target', return_value=None), patch.object(app, 'paste_text_to_active_target') as deliver:
            app.paste_after_target_click(click_point=(10, 20))
            self.assertTrue(app.waiting_for_target_click)
            deliver.assert_not_called()

    def test_tagged_independent_shell_is_excluded_before_uia_focus_lookup(self):
        user32 = MagicMock()
        user32.GetForegroundWindow.return_value = 100
        user32.GetAncestor.return_value = 100
        user32.GetPropW.return_value = 1
        element = SimpleNamespace(GetRuntimeId=lambda: [1, 2])
        automation = SimpleNamespace(GetFocusedElement=lambda: element)
        with patch.object(app, 'native_owner_pid', 0), patch.object(app.ctypes.windll, 'user32', user32), patch.object(app, 'window_process_id', return_value=424242), patch.object(app, 'element_is_writable', return_value=True), patch('comtypes.client.CreateObject', return_value=automation) as create:
            self.assertIsNone(app.focused_editable_target())
            create.assert_not_called()


class RecoveryTests(unittest.TestCase):
    def test_automatic_position_write_cannot_authorize_settings_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_bytes(b'\xfforiginal-settings')
            save = settings.save_settings
            def write(values, *, recover=False):
                return save(values, path, recover=recover)
            with patch.object(app, 'SETTINGS', dict(settings.DEFAULT_SETTINGS)), patch.object(app, 'loading', False), patch.object(app, 'operation_error', ''), patch.object(app, 'root', None), patch.object(app.settings, 'save_settings', side_effect=write), patch.object(app, 'redraw_bubble_current_state'), patch.object(app, 'refresh_settings_panel'):
                with self.assertRaises(ValueError):
                    app.control_set_settings({'settings': {'bubble_position': [101, 202]}})
                self.assertEqual(path.read_bytes(), b'\xfforiginal-settings')
                result = app.control_set_settings({'settings': {'language': 'Persian'}, 'recover': True})
                self.assertEqual(result['language'], 'Persian')
                self.assertEqual(next(path.parent.glob('settings.json.corrupt-*')).read_bytes(), b'\xfforiginal-settings')

    def test_history_corruption_has_distinct_recovery_state_and_clear_preserves_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            path.write_bytes(b'\xfforiginal-history')
            read = app.load_transcript_history_entries
            with patch.object(app.config, 'TRANSCRIPT_HISTORY_FILE', path), patch.object(app, 'load_transcript_history_entries', side_effect=lambda: read(path)), patch.object(app, 'history_revision', 0), patch.object(app, 'log'):
                self.assertEqual(app.control_history_data(), [])
                self.assertTrue(app.control_state_data().get('history_error'))
                app.control_clear_history()
                self.assertEqual(app.control_state_data().get('history_error'), '')
                self.assertEqual(next(path.parent.glob('history.json.corrupt-*')).read_bytes(), b'\xfforiginal-history')

    def test_delimiter_in_custom_model_name_round_trips_without_metadata_scan(self):
        custom = [{'name': 'Studio - English', 'source': 'owner/model'}]
        with patch.object(settings, 'model_tier_details') as scan:
            self.assertEqual(settings.model_choice_from_dropdown_label('Studio - English - owner/model - 75 MB', custom), 'Studio - English')
            scan.assert_not_called()


class RequestDeadlineTests(unittest.TestCase):
    def test_trickled_bytes_cannot_extend_the_total_control_read_deadline(self):
        client, sender = socket.socketpair()
        def trickle():
            try:
                for part in b'{"cmd":"health"}\n':
                    sender.sendall(bytes([part]))
                    time.sleep(.02)
            except OSError:
                pass
            finally:
                sender.close()
        worker = threading.Thread(target=trickle)
        worker.start()
        try:
            client.settimeout(.08)
            with patch.object(app.config, 'CONTROL_CLIENT_TIMEOUT_SECONDS', .08):
                with self.assertRaises(TimeoutError):
                    app.read_control_command(client)
        finally:
            client.close()
            worker.join(1)


if __name__ == '__main__':
    unittest.main()
