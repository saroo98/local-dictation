import json
import os
import socket
import subprocess
import sys
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bubble_dictate as app
from control_bridge import ControlCommandRouter
import settings


class RuntimeProfileTests(unittest.TestCase):
    def test_explicit_profile_isolates_every_data_file_and_instance_mutex(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = {**os.environ, 'LOCAL_DICTATION_DATA_DIR': directory}
            result = subprocess.run(
                [sys.executable, '-B', '-c',
                 'import config,json; print(json.dumps({"paths": [str(config.SETTINGS_FILE), str(config.TRANSCRIPT_HISTORY_FILE), str(config.LOG_FILE), str(config.LOG_DIR), str(config.LAUNCH_LOCK_FILE)], "mutex": config.SINGLE_INSTANCE_MUTEX_NAME}))'],
                cwd=Path(app.__file__).parent, env=environment,
                capture_output=True, text=True, check=True, timeout=10,
            )
            data = json.loads(result.stdout)
            self.assertTrue(all(Path(path).parent == Path(directory).resolve() for path in data['paths']))
            self.assertTrue(data['mutex'].startswith('Local\\LocalDictationBubbleApp-'))


class PersistenceRecoveryTests(unittest.TestCase):
    def test_invalid_utf8_settings_remain_unchanged_until_explicit_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_bytes(b'\xffbroken')
            self.assertEqual(settings.load_settings(path)['model'], 'Balanced')
            with self.assertRaises(ValueError):
                settings.save_settings(settings.DEFAULT_SETTINGS, path)
            self.assertEqual(path.read_bytes(), b'\xffbroken')
            settings.save_settings(settings.DEFAULT_SETTINGS, path, recover=True)
            self.assertEqual(json.loads(path.read_text())['model'], 'Balanced')
            self.assertEqual(next(path.parent.glob('settings.json.corrupt-*')).read_bytes(), b'\xffbroken')

    def test_failed_replacement_keeps_last_valid_settings_and_removes_own_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            settings.save_settings(settings.DEFAULT_SETTINGS, path)
            before = path.read_bytes()
            with patch('os.replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    settings.save_settings({**settings.DEFAULT_SETTINGS, 'language': 'Arabic'}, path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(path.parent.iterdir()), [path])


    def test_corrupt_history_is_preserved_instead_of_overwritten_by_append(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            path.write_bytes(b'\xffhistory')
            self.assertEqual(app.load_transcript_history_entries(path), [])
            with self.assertRaises(ValueError):
                app.add_transcript_to_history('new', path)
            self.assertEqual(path.read_bytes(), b'\xffhistory')

    def test_clear_serializes_with_append_and_deleted_entries_never_return(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            app.add_transcript_to_history('old', path)
            entered, release = threading.Event(), threading.Event()
            real_write = app.persistence.atomic_write_json
            def delayed_write(target, value, **kwargs):
                if value and value[-1].get('text') == 'racing':
                    entered.set()
                    release.wait(1)
                return real_write(target, value, **kwargs)
            with patch.object(app.persistence, 'atomic_write_json', side_effect=delayed_write), patch.object(app.config, 'TRANSCRIPT_HISTORY_FILE', path):
                writer = threading.Thread(target=app.add_transcript_to_history, args=('racing', path))
                writer.start()
                self.assertTrue(entered.wait(1))
                clearer = threading.Thread(target=app.control_clear_history)
                clearer.start()
                release.set()
                writer.join(1)
                clearer.join(1)
            self.assertEqual(app.load_transcript_history(path), [])
            app.add_transcript_to_history('new', path)
            self.assertEqual(app.load_transcript_history(path), ['new'])


class SettingsRecoveryStateTests(unittest.TestCase):
    def test_moving_bubble_does_not_clear_the_recording_recovery_error(self):
        initial = dict(settings.DEFAULT_SETTINGS)
        error = 'Recording unavailable: model missing'
        with patch.object(app, 'SETTINGS', initial), patch.object(app, 'model', None), patch.object(app, 'audio_stream', None), patch.object(app, 'loading', False), patch.object(app, 'operation_error', error), patch.object(app, 'root', None), patch.object(app.settings, 'save_settings'), patch.object(app, 'redraw_bubble_current_state'), patch.object(app, 'refresh_settings_panel'):
            app.control_set_settings({'settings': {'bubble_position': [101, 202]}})
            self.assertEqual(app.control_state_data()['error'], error)

    def test_successful_model_recovery_still_explains_uninitialized_microphone(self):
        initial = {**settings.DEFAULT_SETTINGS, 'device_mode': 'cpu'}
        with patch.object(app, 'SETTINGS', initial), patch.object(app, 'model', None), patch.object(app, 'audio_stream', None), patch.object(app, 'loading', False), patch.object(app, 'operation_error', 'Recording unavailable: model missing'), patch.object(app, 'root', None), patch.object(app, 'build_model', return_value=(object(), 'cpu')), patch.object(app.settings, 'save_settings'), patch.object(app, 'redraw_bubble_current_state'), patch.object(app, 'refresh_settings_panel'):
            app.control_set_settings({'settings': {'model': initial['model']}})
            state = app.control_state_data()
            self.assertFalse(state['recording_ready'])
            self.assertIn('microphone', state['error'])
            self.assertIn('Retry', state['error'])

class SettingsTransactionTests(unittest.TestCase):
    def test_failed_hotkey_registration_keeps_settings_and_old_listener(self):
        initial = dict(settings.DEFAULT_SETTINGS)
        old_listener = type('Listener', (), {'stop': lambda self: None})()
        with patch.object(app, 'SETTINGS', initial), patch.object(app, 'model', object()), patch.object(app, 'hotkey_listener', old_listener), patch.object(app, 'loading', False), patch.object(app, 'operation_error', ''), patch.object(app.keyboard, 'GlobalHotKeys', side_effect=RuntimeError('hook unavailable')), patch.object(app.settings, 'save_settings') as save:
            with self.assertRaises(RuntimeError):
                app.control_set_settings({'settings': {'hotkey': '<ctrl>+<shift>+d'}})
            self.assertIs(app.hotkey_listener, old_listener)
            self.assertEqual(app.SETTINGS['hotkey'], '<ctrl>+<alt>+d')
            save.assert_not_called()

    def test_partial_position_save_preserves_preferences_without_restarting_hotkeys(self):
        initial = {**settings.DEFAULT_SETTINGS, 'language': 'Persian', 'device_mode': 'cpu'}
        with patch.object(app, 'SETTINGS', initial), patch.object(app, 'model', object()), patch.object(app.settings, 'save_settings'), patch.object(app, 'restart_hotkey_listener') as restart, patch.object(app, 'redraw_bubble_current_state'), patch.object(app, 'refresh_settings_panel'):
            result = app.control_set_settings({'settings': {'bubble_position': [40, 50]}})
            self.assertEqual(result['language'], 'Persian')
            self.assertEqual(result['device_mode'], 'cpu')
            self.assertEqual(result['bubble_position'], [40, 50])
            restart.assert_not_called()

    def test_failed_persistence_does_not_publish_settings(self):
        initial = dict(settings.DEFAULT_SETTINGS)
        with patch.object(app, 'SETTINGS', initial), patch.object(app.settings, 'save_settings', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                app.control_set_settings({'settings': {'language': 'Arabic'}})
            self.assertEqual(app.SETTINGS['language'], 'English (US)')

    def test_failed_candidate_keeps_model_device_and_saved_configuration(self):
        initial = {**settings.DEFAULT_SETTINGS, 'device_mode': 'cpu'}
        previous = object()
        with patch.object(app, 'SETTINGS', initial), patch.object(app, 'model', previous), patch.object(app, 'active_device', 'cpu'), patch.object(app, 'loading', False), patch.object(app, 'operation_error', ''), patch.object(app, 'build_model', side_effect=RuntimeError('CUDA failed'), create=True), patch.object(app.settings, 'save_settings') as save:
            with self.assertRaises(RuntimeError):
                app.control_set_settings({'settings': {'device_mode': 'cuda'}})
            self.assertIs(app.model, previous)
            self.assertEqual(app.active_device, 'cpu')
            self.assertEqual(app.SETTINGS['device_mode'], 'cpu')
            self.assertFalse(app.loading)
            save.assert_not_called()

    def test_partial_snapshot_is_never_passed_to_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            repo = settings.repo_cache_dir(settings.MODEL_TIER_TO_REPO['Fast'], path)
            snapshot = repo / 'snapshots' / 'revision'
            snapshot.mkdir(parents=True)
            (repo / 'refs').mkdir()
            (repo / 'refs' / 'main').write_text('revision')
            (snapshot / 'model.bin').write_bytes(b'x')
            self.assertFalse(settings.model_is_available_locally('Fast', path))
            with patch.object(app.config, 'MODEL_DOWNLOAD_ROOT', str(path)), patch.object(app, 'WhisperModel') as inference:
                with self.assertRaises(ValueError):
                    app.make_cpu_model({**settings.DEFAULT_SETTINGS, 'model': 'Fast'})
                inference.assert_not_called()

    def test_reload_reservation_rejects_overlap_and_recording_without_publishing_candidate(self):
        entered, release = threading.Event(), threading.Event()
        previous, candidate = object(), object()
        results = []
        def build(values):
            entered.set()
            release.wait(1)
            return candidate, 'cuda'
        initial = {**settings.DEFAULT_SETTINGS, 'device_mode': 'cpu'}
        with patch.object(app, 'SETTINGS', initial), patch.object(app, 'model', previous), patch.object(app, 'active_device', 'cpu'), patch.object(app, 'loading', False), patch.object(app, 'operation_error', ''), patch.object(app, 'root', object()), patch.object(app, 'build_model', side_effect=build), patch.object(app.settings, 'save_settings'), patch.object(app, 'redraw_bubble_current_state'), patch.object(app, 'refresh_settings_panel'):
            # No Tk side effects needed here; the scheduling boundary is fake I/O.
            app.root = type('Root', (), {'after': lambda self, *args: None})()
            worker = threading.Thread(target=lambda: results.append(app.control_set_settings({'settings': {'device_mode': 'cuda'}})))
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                self.assertTrue(app.control_state_data()['loading'])
                self.assertEqual(app.control_settings_data()['device_mode'], 'cpu')
                with self.assertRaises(ValueError):
                    app.control_set_settings({'settings': {'device_mode': 'auto'}})
                with self.assertRaises(ValueError):
                    app.control_schedule_recording_action('start-recording')
            finally:
                release.set()
                worker.join(1)
            self.assertEqual(results[0]['device_mode'], 'cuda')
            self.assertIs(app.model, candidate)
            self.assertFalse(app.loading)

    def test_duplicate_download_requests_use_one_external_download(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        calls = []
        def download(*args, **kwargs):
            calls.append(args[0])
            entered.set()
            release.wait(1)
            return 'snapshot'
        real_status = app.set_model_download_status
        def status(choice, state, error=''):
            real_status(choice, state, error)
            if state == 'idle':
                finished.set()
        with patch.object(app, 'model_download_status', {}), patch.object(app, 'model_download_locks', {}), patch.object(app, '_download_model_for_choice', side_effect=download), patch.object(app, 'set_model_download_status', side_effect=status):
            app.control_download_model({'choice': 'Fast'})
            self.assertTrue(entered.wait(1))
            app.control_download_model({'choice': 'Fast'})
            release.set()
            self.assertTrue(finished.wait(1))
            self.assertEqual(calls, ['Fast'])


class OwnedShutdownTests(unittest.TestCase):
    def test_replaced_backend_rejects_stale_launch_shutdown(self):
        callbacks = []
        root = type('Root', (), {'after': lambda self, *args: callbacks.append(args)})()
        with patch.object(app, 'backend_launch_id', 'current'), patch.object(app, 'root', root):
            rejected = json.loads(app.handle_control_command('{"cmd":"shutdown-owned-backend","args":{"launch_id":"stale"}}'))
            self.assertFalse(rejected['ok'])
            self.assertEqual(callbacks, [])
            accepted = json.loads(app.handle_control_command('{"cmd":"shutdown-owned-backend","args":{"launch_id":"current"}}'))
            self.assertTrue(accepted['ok'])
            self.assertEqual(len(callbacks), 1)


class TranscriptRetentionTests(unittest.TestCase):
    def test_cleanup_preserves_literal_content(self):
        for text in ('Version 1.2.3 costs 1,000.50.', 'a.b@example.com https://example.com/a,b', 'Wait... really!!!', 'The period contains a comma.', 'hello new line world'):
            with self.subTest(text=text):
                self.assertEqual(app.clean_transcript_text(text), text)

    def test_clipboard_contention_preserves_successful_transcript_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            with (
                patch.object(app, 'current_recording_session_id', 7),
                patch.object(app, 'latest_transcript', 'previous'),
                patch.object(app, 'transcribing', True),
                patch.object(app, 'waiting_for_target_click', False),
                patch.object(app, 'operation_error', ''),
                patch.object(app, 'transcribe_audio', return_value='Version 1.2.3'),
                patch.object(app, 'focused_field_is_editable', return_value=False),
                patch.object(app.pyperclip, 'copy', side_effect=RuntimeError('clipboard busy')),
                patch.object(app, 'set_bubble'), patch.object(app.time, 'sleep'),
                patch.object(app, 'add_transcript_to_history', side_effect=lambda text: app.save_transcript_history([text], path)),
            ):
                app.process_recording([app.np.zeros(10, dtype=app.np.float32)], 7)
                self.assertEqual(app.latest_transcript, 'Version 1.2.3')
                self.assertEqual(app.load_transcript_history(path), ['Version 1.2.3'])
                self.assertTrue(app.waiting_for_target_click)
                self.assertIn('clipboard', app.operation_error.lower())

    def test_late_recording_worker_cannot_replace_new_session(self):
        with patch.object(app, 'current_recording_session_id', 8), patch.object(app, 'latest_transcript', 'new result'), patch.object(app, 'recording', True), patch.object(app, 'transcribe_audio', return_value='old result'), patch.object(app, 'set_bubble') as repaint, patch.object(app.pyperclip, 'copy'), patch.object(app, 'add_transcript_to_history'):
            app.process_recording([app.np.zeros(10, dtype=app.np.float32)], 7)
            self.assertEqual(app.latest_transcript, 'new result')
            self.assertTrue(app.recording)
            repaint.assert_not_called()


class PasteReliabilityTests(unittest.TestCase):
    def test_two_click_workers_claim_one_transcript_and_failure_restores_retry(self):
        entered, release = threading.Event(), threading.Event()
        deliveries = []
        def deliver(text, **kwargs):
            deliveries.append(text)
            entered.set()
            release.wait(1)
            return False
        with patch.object(app, 'waiting_for_target_click', True), patch.object(app, 'latest_transcript', 'retained'), patch.object(app, 'current_recording_session_id', 5), patch.object(app, 'paste_text_to_active_target', side_effect=deliver), patch.object(app, 'set_bubble'), patch.object(app, 'operation_error', ''):
            first = threading.Thread(target=app.paste_after_target_click)
            first.start()
            try:
                self.assertTrue(entered.wait(1))
                app.paste_after_target_click()
            finally:
                release.set()
                first.join(1)
            self.assertEqual(deliveries, ['retained'])
            self.assertTrue(app.waiting_for_target_click)
            self.assertEqual(app.latest_transcript, 'retained')

    def test_focus_changed_during_delay_never_injects_paste(self):
        with patch.object(app, 'focused_editable_target', side_effect=[(100, (1,)), (200, (2,))], create=True), patch.object(app.time, 'sleep'), patch.object(app.pyperclip, 'copy'), patch.object(app.pyautogui, 'hotkey') as inject, patch.object(app, 'set_bubble'):
            self.assertFalse(app.paste_text_to_active_target('text'))
            inject.assert_not_called()

    def test_readonly_text_controls_are_not_writable_targets(self):
        class Element:
            CurrentIsEnabled = True
            CurrentControlType = 50004
            def GetCurrentPattern(self, pattern):
                return type('Pattern', (), {'QueryInterface': lambda self, interface: self, 'CurrentIsReadOnly': True})()
        module = type('Module', (), {'IUIAutomationValuePattern': object})
        self.assertFalse(app.element_is_writable(Element(), module))


class ControlRecoveryTests(unittest.TestCase):
    def test_non_string_commands_return_error_then_health_succeeds(self):
        router = ControlCommandRouter(app.BubbleControlActions())
        for command in ([], {}, 42, None):
            with self.subTest(command=command):
                self.assertFalse(json.loads(router.handle(json.dumps({'cmd': command})))['ok'])
        self.assertTrue(json.loads(router.handle('{"cmd":"health"}'))['ok'])

    def test_abandoned_client_does_not_end_or_hold_the_control_service(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        stop = threading.Event()
        with patch.object(app.config, 'CONTROL_PORT', port), patch.object(app.config, 'CONTROL_CLIENT_TIMEOUT_SECONDS', .1, create=True), patch.object(app, 'log'), patch.object(app, 'log_exception'):
            worker = threading.Thread(target=app.control_server_loop, args=(stop,), daemon=True)
            worker.start()
            deadline = time.monotonic() + 2
            while True:
                try:
                    abandoned = socket.create_connection(('127.0.0.1', port), timeout=.3)
                    break
                except ConnectionRefusedError:
                    if time.monotonic() > deadline:
                        self.fail('control service did not start')
                    time.sleep(.01)
            try:
                abandoned.sendall(b'{"cmd":')
                time.sleep(.2)
                with socket.create_connection(('127.0.0.1', port), timeout=.5) as client:
                    client.settimeout(.5)
                    client.sendall(b'{"cmd":"health"}\n')
                    self.assertTrue(json.loads(client.recv(4096))['ok'])
            finally:
                abandoned.close()
                stop.set()
                worker.join(1)

    def test_failed_initialization_retains_service_and_reports_recording_error(self):
        with patch.object(app, 'load_model', side_effect=RuntimeError('model missing')), patch.object(app, 'model', None), patch.object(app, 'audio_stream', None), patch.object(app, 'loading', False, create=True), patch.object(app, 'operation_error', '', create=True), patch.object(app, 'log_exception'), patch.object(app, 'set_bubble'):
            app.initialize_resources()
            state = app.control_state_data()
            self.assertFalse(state['loading'])
            self.assertIn('model missing', state['error'])
            self.assertEqual(state['status'], 'error')
            self.assertTrue(json.loads(app.handle_control_command('{"cmd":"health"}'))['ok'])


if __name__ == '__main__':
    unittest.main()
