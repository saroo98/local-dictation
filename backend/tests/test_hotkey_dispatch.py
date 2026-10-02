import queue
import threading
import unittest
from unittest.mock import patch

import bubble_dictate as app


class HotkeyDispatchTests(unittest.TestCase):
    def test_shortcut_callback_returns_while_tk_is_busy(self):
        release = threading.Event()
        completed = threading.Event()

        class BusyRoot:
            def after(self, *_args):
                release.wait(2)

        def press():
            app.on_hotkey_toggle()
            completed.set()

        with patch.object(app, 'root', BusyRoot()), patch.object(app, 'shutting_down', False), patch.object(app, 'hotkey_events', queue.SimpleQueue(), create=True):
            worker = threading.Thread(target=press)
            worker.start()
            try:
                self.assertTrue(completed.wait(0.3), 'Keyboard listener waited on the busy Tk thread')
            finally:
                release.set()
                worker.join(2)

    def test_repeated_shortcuts_are_delivered_in_order_on_the_tk_thread(self):
        scheduled = []
        delivered = []
        main_thread = threading.get_ident()

        class Root:
            def after(self, delay, callback):
                scheduled.append((delay, callback))

        with patch.object(app, 'root', Root()), patch.object(app, 'shutting_down', False), patch.object(app, 'hotkey_events', queue.SimpleQueue(), create=True), patch.object(app, 'toggle_recording_from_shortcut', side_effect=lambda: delivered.append(threading.get_ident())), patch.object(app.keyboard.GlobalHotKeys, 'start'), patch.object(app, 'log'):
            listener = app.start_hotkey_listener('<alt>+a')

            def press_repeatedly():
                for cycle in range(20):
                    listener._on_press(app.keyboard.Key.alt_l, False)
                    for _ in range(3):
                        listener._on_press(app.keyboard.KeyCode.from_char('a'), False)
                    released = [app.keyboard.Key.alt_l, app.keyboard.KeyCode.from_char('a')]
                    for key in released if cycle % 2 else reversed(released):
                        listener._on_release(key, False)

            worker = threading.Thread(target=press_repeatedly)
            worker.start()
            worker.join(1)
            self.assertEqual(scheduled, [], 'Hook thread called Tk directly')
            app.drain_hotkey_events()
            self.assertEqual(delivered, [main_thread] * 20)
            self.assertEqual(len(scheduled), 1)
            self.assertIs(scheduled[0][1], app.drain_hotkey_events)

    def test_shutdown_discards_pending_shortcuts_without_rescheduling_tk(self):
        events = queue.SimpleQueue()
        events.put(None)
        with patch.object(app, 'root') as root, patch.object(app, 'shutting_down', True), patch.object(app, 'hotkey_events', events, create=True), patch.object(app, 'toggle_recording_from_shortcut') as toggle:
            app.on_hotkey_toggle()
            app.drain_hotkey_events()
            toggle.assert_not_called()
            root.after.assert_not_called()
            self.assertTrue(events.empty())


if __name__ == '__main__':
    unittest.main()
