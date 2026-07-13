from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol


class ControlActions(Protocol):
    def health(self) -> object:
        ...

    def backend_owner(self) -> object:
        ...

    def shutdown_backend(self) -> object:
        ...

    def get_settings(self) -> object:
        ...

    def get_history(self) -> object:
        ...

    def list_models(self, args: dict) -> object:
        ...

    def get_state(self) -> object:
        ...

    def set_settings(self, args: dict) -> object:
        ...

    def recording_action(self, command: str) -> object:
        ...

    def clear_history(self) -> object:
        ...

    def export_history(self, args: dict) -> object:
        ...

    def download_model(self, args: dict) -> object:
        ...

    def open_model_folder(self, args: dict) -> object:
        ...

    def copy_model_path(self, args: dict) -> object:
        ...

    def add_custom_model(self, args: dict) -> object:
        ...

    def legacy_action(self, command: str) -> bool:
        ...


class ControlCommandRouter:
    def __init__(
        self,
        actions: ControlActions,
        exception_logger: Callable[[str, BaseException], None] | None = None,
    ):
        self.actions = actions
        self.exception_logger = exception_logger

    def handle(self, command: str) -> str:
        stripped = command.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                request = json.loads(command)
            except json.JSONDecodeError:
                return self._json_error("Invalid JSON request.")
            if not isinstance(request, dict):
                return self._json_error("JSON request must be an object.")
            args = request.get("args", {})
            if args is None:
                args = {}
            if not isinstance(args, dict):
                return self._json_error("Request args must be an object.")
            json_command = request.get("cmd")
            return self._handle_json_command(json_command, args)

        if command in {"toggle-record", "show-history"}:
            return "ok" if self.actions.legacy_action(command) else "error"
        return "error"

    def _handle_json_command(self, command: str, args: dict[str, Any]) -> str:
        no_arg_actions: dict[str, Callable[[], object]] = {
            "health": self.actions.health,
            "backend-owner": self.actions.backend_owner,
            "shutdown-backend": self.actions.shutdown_backend,
            "get-settings": self.actions.get_settings,
            "get-history": self.actions.get_history,
            "get-state": self.actions.get_state,
            "clear-history": self.actions.clear_history,
        }
        arg_actions: dict[str, Callable[[dict[str, Any]], object]] = {
            "list-models": self.actions.list_models,
            "set-settings": self.actions.set_settings,
            "export-history": self.actions.export_history,
            "download-model": self.actions.download_model,
            "open-model-folder": self.actions.open_model_folder,
            "copy-model-path": self.actions.copy_model_path,
            "add-custom-model": self.actions.add_custom_model,
        }

        if command in no_arg_actions:
            return self._run(command, no_arg_actions[command])
        if command in arg_actions:
            return self._run(command, lambda: arg_actions[command](args))
        if command in {"start-recording", "stop-recording", "toggle-recording"}:
            return self._run(command, lambda: self.actions.recording_action(command))
        return self._json_error(f"Unknown command: {command}")

    def _run(self, command: str, action: Callable[[], object]) -> str:
        try:
            return self._json_success(action())
        except Exception as exc:
            if self.exception_logger is not None:
                self.exception_logger(command, exc)
            return self._json_error(str(exc))

    @staticmethod
    def _json_error(message: str) -> str:
        return json.dumps({"ok": False, "error": message}, ensure_ascii=False)

    @staticmethod
    def _json_success(data: object) -> str:
        return json.dumps({"ok": True, "data": data}, ensure_ascii=False)
