import unittest
import json

from control_bridge import ControlCommandRouter


class FakeControlActions:
    def __init__(self):
        self.calls = []
        self.results = {
            "get_settings": {"theme": "Dark Mode"},
            "get_history": [{"text": "hello", "created_at": None}],
            "list_models": [{"tier": "Fast"}],
            "get_state": {"status": "idle"},
            "set_settings": {"theme": "Light Mode"},
            "recording_action": {"accepted": True},
            "health": {"status": "ready"},
            "backend_owner": "api",
            "shutdown_backend": {"accepted": True},
            "clear_history": [],
            "export_history": "%USERPROFILE%\\Documents\\history.txt",
            "download_model": {"choice": "Fast", "status": "downloading"},
            "open_model_folder": "%USERPROFILE%\\.cache\\huggingface\\hub",
            "copy_model_path": "%USERPROFILE%\\.cache\\huggingface\\hub",
            "add_custom_model": {"custom_models": []},
        }

    def legacy_action(self, command):
        self.calls.append(("legacy_action", command))
        return True

    def get_settings(self):
        self.calls.append(("get_settings",))
        return self.results["get_settings"]

    def get_history(self):
        self.calls.append(("get_history",))
        return self.results["get_history"]

    def list_models(self, args):
        self.calls.append(("list_models", args))
        return self.results["list_models"]

    def get_state(self):
        self.calls.append(("get_state",))
        return self.results["get_state"]

    def set_settings(self, args):
        self.calls.append(("set_settings", args))
        return self.results["set_settings"]

    def recording_action(self, command):
        self.calls.append(("recording_action", command))
        return self.results["recording_action"]

    def health(self):
        self.calls.append(("health",))
        return self.results["health"]

    def backend_owner(self):
        self.calls.append(("backend_owner",))
        return self.results["backend_owner"]

    def shutdown_backend(self):
        self.calls.append(("shutdown_backend",))
        return self.results["shutdown_backend"]

    def clear_history(self):
        self.calls.append(("clear_history",))
        return self.results["clear_history"]

    def export_history(self, args):
        self.calls.append(("export_history", args))
        return self.results["export_history"]

    def download_model(self, args):
        self.calls.append(("download_model", args))
        return self.results["download_model"]

    def open_model_folder(self, args):
        self.calls.append(("open_model_folder", args))
        return self.results["open_model_folder"]

    def copy_model_path(self, args):
        self.calls.append(("copy_model_path", args))
        return self.results["copy_model_path"]

    def add_custom_model(self, args):
        self.calls.append(("add_custom_model", args))
        return self.results["add_custom_model"]


class ExplodingControlActions(FakeControlActions):
    def get_settings(self):
        raise RuntimeError("boom")


class ControlCommandRouterTests(unittest.TestCase):
    def test_legacy_toggle_record_returns_plain_ok_when_adapter_accepts(self):
        actions = FakeControlActions()
        router = ControlCommandRouter(actions)

        self.assertEqual(router.handle("toggle-record"), "ok")
        self.assertEqual(actions.calls, [("legacy_action", "toggle-record")])

    def test_legacy_show_history_returns_plain_ok_when_adapter_accepts(self):
        actions = FakeControlActions()
        router = ControlCommandRouter(actions)

        self.assertEqual(router.handle("show-history"), "ok")
        self.assertEqual(actions.calls, [("legacy_action", "show-history")])

    def test_unknown_legacy_command_returns_plain_error(self):
        actions = FakeControlActions()
        router = ControlCommandRouter(actions)

        self.assertEqual(router.handle("unknown"), "error")
        self.assertEqual(actions.calls, [])

    def test_invalid_json_returns_json_error(self):
        router = ControlCommandRouter(FakeControlActions())

        response = json.loads(router.handle("{not json"))

        self.assertEqual(response, {"ok": False, "error": "Invalid JSON request."})

    def test_json_non_object_returns_json_error(self):
        router = ControlCommandRouter(FakeControlActions())

        response = json.loads(router.handle("[1, 2, 3]"))

        self.assertEqual(response, {"ok": False, "error": "JSON request must be an object."})

    def test_json_args_must_be_object(self):
        router = ControlCommandRouter(FakeControlActions())

        response = json.loads(
            router.handle(json.dumps({"cmd": "get-settings", "args": []}))
        )

        self.assertEqual(response, {"ok": False, "error": "Request args must be an object."})

    def test_unknown_json_command_returns_json_error(self):
        router = ControlCommandRouter(FakeControlActions())

        response = json.loads(
            router.handle(json.dumps({"cmd": "delete-everything", "args": {}}))
        )

        self.assertEqual(response, {"ok": False, "error": "Unknown command: delete-everything"})

    def test_json_read_commands_dispatch_to_actions(self):
        actions = FakeControlActions()
        router = ControlCommandRouter(actions)

        self.assertEqual(
            json.loads(router.handle(json.dumps({"cmd": "get-settings", "args": {}}))),
            {"ok": True, "data": actions.results["get_settings"]},
        )
        self.assertEqual(
            json.loads(router.handle(json.dumps({"cmd": "get-history", "args": {}}))),
            {"ok": True, "data": actions.results["get_history"]},
        )
        self.assertEqual(
            json.loads(
                router.handle(json.dumps({"cmd": "list-models", "args": {"order": "Speed"}}))
            ),
            {"ok": True, "data": actions.results["list_models"]},
        )
        self.assertEqual(
            json.loads(router.handle(json.dumps({"cmd": "get-state", "args": {}}))),
            {"ok": True, "data": actions.results["get_state"]},
        )
        self.assertEqual(
            actions.calls,
            [
                ("get_settings",),
                ("get_history",),
                ("list_models", {"order": "Speed"}),
                ("get_state",),
            ],
        )

    def test_set_settings_passes_args_through(self):
        actions = FakeControlActions()
        router = ControlCommandRouter(actions)

        response = json.loads(
            router.handle(
                json.dumps(
                    {"cmd": "set-settings", "args": {"settings": {"theme": "Light Mode"}}}
                )
            )
        )

        self.assertEqual(response, {"ok": True, "data": actions.results["set_settings"]})
        self.assertEqual(
            actions.calls,
            [("set_settings", {"settings": {"theme": "Light Mode"}})],
        )

    def test_recording_commands_dispatch_through_recording_action(self):
        actions = FakeControlActions()
        router = ControlCommandRouter(actions)

        for command in ("start-recording", "stop-recording", "toggle-recording"):
            response = json.loads(router.handle(json.dumps({"cmd": command, "args": {}})))
            self.assertEqual(response, {"ok": True, "data": actions.results["recording_action"]})

        self.assertEqual(
            actions.calls,
            [
                ("recording_action", "start-recording"),
                ("recording_action", "stop-recording"),
                ("recording_action", "toggle-recording"),
            ],
        )

    def test_backend_commands_dispatch_to_actions(self):
        actions = FakeControlActions()
        router = ControlCommandRouter(actions)

        self.assertEqual(
            json.loads(router.handle(json.dumps({"cmd": "health", "args": {}}))),
            {"ok": True, "data": actions.results["health"]},
        )
        self.assertEqual(
            json.loads(router.handle(json.dumps({"cmd": "backend-owner", "args": {}}))),
            {"ok": True, "data": actions.results["backend_owner"]},
        )
        self.assertEqual(
            json.loads(router.handle(json.dumps({"cmd": "shutdown-backend", "args": {}}))),
            {"ok": True, "data": actions.results["shutdown_backend"]},
        )

        self.assertEqual(actions.calls, [("health",), ("backend_owner",), ("shutdown_backend",)])

    def test_history_and_model_action_commands_dispatch_to_actions(self):
        actions = FakeControlActions()
        router = ControlCommandRouter(actions)

        cases = [
            ("clear-history", {}, "clear_history"),
            ("export-history", {"format": "txt"}, "export_history"),
            ("download-model", {"choice": "Fast"}, "download_model"),
            ("open-model-folder", {"choice": "Fast"}, "open_model_folder"),
            ("copy-model-path", {"choice": "Fast"}, "copy_model_path"),
            (
                "add-custom-model",
                {"name": "Mine", "source": "Systran/faster-whisper-base"},
                "add_custom_model",
            ),
        ]

        for command, args, result_key in cases:
            response = json.loads(router.handle(json.dumps({"cmd": command, "args": args})))
            self.assertEqual(response, {"ok": True, "data": actions.results[result_key]})

        self.assertEqual(
            actions.calls,
            [
                ("clear_history",),
                ("export_history", {"format": "txt"}),
                ("download_model", {"choice": "Fast"}),
                ("open_model_folder", {"choice": "Fast"}),
                ("copy_model_path", {"choice": "Fast"}),
                ("add_custom_model", {"name": "Mine", "source": "Systran/faster-whisper-base"}),
            ],
        )

    def test_action_exception_returns_json_error_and_logs_exception(self):
        logged = []
        router = ControlCommandRouter(
            ExplodingControlActions(),
            exception_logger=lambda command, exc: logged.append((command, str(exc))),
        )

        response = json.loads(router.handle(json.dumps({"cmd": "get-settings", "args": {}})))

        self.assertEqual(response, {"ok": False, "error": "boom"})
        self.assertEqual(logged, [("get-settings", "boom")])


if __name__ == "__main__":
    unittest.main()
