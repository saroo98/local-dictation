import ctypes
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
import re
import site
import socket
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

# ---------------------------------------------------------------------
# NVIDIA CUDA DLL discovery
# ---------------------------------------------------------------------
# These paths are needed when CUDA/cuDNN/cuBLAS are installed through pip:
#   nvidia-cublas-cu12
#   nvidia-cudnn-cu12
#   nvidia-cuda-runtime-cu12
#   nvidia-cuda-nvrtc-cu12
#
# This must run before faster_whisper / ctranslate2 tries to load CUDA.
# ---------------------------------------------------------------------

_nvidia_dll_handles = []


def add_nvidia_dll_dirs() -> None:
    candidate_subdirs = [
        r"nvidia\cublas\bin",
        r"nvidia\cublas\lib",
        r"nvidia\cudnn\bin",
        r"nvidia\cudnn\lib",
        r"nvidia\cuda_runtime\bin",
        r"nvidia\cuda_runtime\lib",
        r"nvidia\cuda_nvrtc\bin",
        r"nvidia\cuda_nvrtc\lib",
    ]

    directories = [Path(site_dir) / subdir for site_dir in site.getsitepackages() for subdir in candidate_subdirs]
    if getattr(sys, 'frozen', False):
        directories.extend([Path(sys.executable).parent / 'cuda', Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)) / 'cuda'])
    if os.environ.get('LOCAL_DICTATION_CUDA_DIR'):
        directories.append(Path(os.environ['LOCAL_DICTATION_CUDA_DIR']))
    for dll_dir in directories:
        if dll_dir.is_dir():
            try:
                _nvidia_dll_handles.append(os.add_dll_directory(str(dll_dir)))
            except (AttributeError, OSError):
                pass
            os.environ['PATH'] = str(dll_dir) + os.pathsep + os.environ.get('PATH', '')


add_nvidia_dll_dirs()


import config
from control_bridge import ControlCommandRouter
import icons
import settings
import persistence
import numpy as np
import pyautogui
import pyperclip
import sounddevice as sd
import tkinter as tk
import tkinter.font as tkfont
import tkinter.ttk as ttk

from faster_whisper import WhisperModel
from pynput import keyboard, mouse

try:
    import pystray
except Exception as exc:  # pragma: no cover - depends on local environment
    pystray = None
    PYSTRAY_IMPORT_ERROR = exc
else:
    PYSTRAY_IMPORT_ERROR = None


# Console may be cp1252 on Windows; render UTF-8 glyphs without crashing.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ---------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------

recording = False
transcribing = False
waiting_for_target_click = False
paste_after_transcription = False

audio_chunks: List[np.ndarray] = []
latest_transcript: Optional[str] = None

state_lock = threading.Lock()
log_write_lock = threading.RLock()
loading = False
operation_error = ""
history_lock = threading.RLock()
history_revision = 0
settings_operation_lock = threading.Lock()

root: Optional[tk.Tk] = None
bubble: Optional[tk.Canvas] = None
bubble_layered = False
current_bubble_text = config.READY_LABEL
current_bubble_bg = config.READY_BG

drag_start_x = 0
drag_start_y = 0
drag_moved = False
drag_press_time = 0.0
left_button_down = False
long_press_quit_triggered = False

active_device = "unknown"
model: Optional[WhisperModel] = None
control_stop_event: Optional[threading.Event] = None
history_panel: Optional[tk.Toplevel] = None
quick_history_popover: Optional[tk.Toplevel] = None
settings_panel: Optional[tk.Toplevel] = None
active_hit_target_size = config.HIT_TARGET_SIZE
ignore_global_left_click_until = 0.0
last_bubble_release_at: Optional[float] = None
last_quick_history_request_at = 0.0
single_instance_mutex: Optional[int] = None
session_log_file: Optional[Path] = None

SETTINGS = settings.load_settings()
hotkey_listener = None  # pynput GlobalHotKeys listener, set at startup
mouse_listener = None   # pynput mouse.Listener, set at startup
audio_stream = None     # sounddevice InputStream, set at startup
tray_icon = None        # pystray.Icon, set at startup when pystray is installed
tray_state = "ready"
shutting_down = False
CONTROL_MAX_COMMAND_BYTES = 65536
BACKEND_PROTOCOL_VERSION = 4
BACKEND_VERSION = "0.4.0-backend-manager"
backend_owner = "not-started"
backend_launch_id = os.environ.get('LOCAL_DICTATION_LAUNCH_ID', '')
try:
    native_owner_pid = int(os.environ.get('LOCAL_DICTATION_OWNER_PID', '0'))
except ValueError:
    native_owner_pid = 0
backend_started_monotonic = time.monotonic()
model_download_status: Dict[str, Dict[str, str]] = {}
model_download_status_lock = threading.Lock()
model_download_locks: Dict[str, threading.Lock] = {}

recording_session_counter = 0
current_recording_session_id = 0
recording_started_monotonic: Optional[float] = None
recording_callback_chunks = 0
recording_callback_frames = 0
recording_first_audio_monotonic: Optional[float] = None
recording_last_audio_monotonic: Optional[float] = None
recording_status_events: List[str] = []


@dataclass(frozen=True)
class ShortcutSpec:
    name: str
    shortcut_path: Path
    target_path: Path
    arguments: str
    working_directory: Path
    description: str


@dataclass(frozen=True)
class TranscriptHistoryEntry:
    text: str
    created_at: Optional[str] = None

    @property
    def display_time(self) -> str:
        if not self.created_at:
            return "Earlier"

        try:
            timestamp = datetime.fromisoformat(self.created_at)
        except ValueError:
            return "Earlier"

        return timestamp.strftime("%I:%M %p").lstrip("0")


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

def session_log_path(log_dir: Path, started_at: datetime, pid: int) -> Path:
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    return log_dir / f"dictation_{timestamp}_pid{pid}.log"


def format_log_line(
    message: str,
    timestamp: Optional[datetime] = None,
    pid: Optional[int] = None,
) -> str:
    current_timestamp = timestamp or datetime.now()
    current_pid = os.getpid() if pid is None else pid
    return f"[{current_timestamp.isoformat(timespec='seconds')} pid={current_pid}] {message}"


def append_text(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        is_session = path.name.startswith('dictation_') and path.name != 'dictation_debug.log'
        with log_write_lock:
            handler = RotatingFileHandler(path, maxBytes=config.SESSION_LOG_MAX_BYTES if is_session else config.LOG_MAX_BYTES,
                                          backupCount=1 if is_session else config.LOG_BACKUP_COUNT, encoding='utf-8')
            try:
                handler.emit(logging.LogRecord('dictation', logging.INFO, '', 0, text.rstrip('\n'), (), None))
            finally:
                handler.close()
    except Exception:
        pass


def prune_old_session_logs(log_dir: Path, keep_count: int) -> None:
    if keep_count < 1 or not log_dir.exists():
        return

    session_logs = sorted(
        log_dir.glob("dictation_*.log"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for old_log in session_logs[keep_count:]:
        try:
            old_log.unlink()
            for backup in old_log.parent.glob(old_log.name + '.[0-9]'):
                backup.unlink()
        except OSError:
            pass


def initialize_logging(
    log_dir: Path = config.LOG_DIR,
    legacy_log_file: Path = config.LOG_FILE,
    started_at: Optional[datetime] = None,
    pid: Optional[int] = None,
) -> Path:
    global session_log_file

    current_started_at = started_at or datetime.now()
    current_pid = os.getpid() if pid is None else pid
    log_dir.mkdir(parents=True, exist_ok=True)
    session_log_file = session_log_path(log_dir, current_started_at, current_pid)
    session_log_file.touch(exist_ok=True)
    prune_old_session_logs(log_dir, config.SESSION_LOG_KEEP_COUNT)

    header = format_log_line(
        f"Log session started. session_log={session_log_file} aggregate_log={legacy_log_file}",
        current_started_at,
        current_pid,
    )
    append_text(legacy_log_file, header + "\n")
    append_text(session_log_file, header + "\n")
    return session_log_file


def safe_console_print(line: str) -> None:
    """Print to the console without ever raising.

    The Windows console is often cp1252, which cannot encode glyphs like the
    paste check mark (U+2713). A print crash here must never escape into a
    caller's control flow (it previously flipped the bubble into the error
    state right after a successful paste).
    """
    try:
        print(line, flush=True)
    except (UnicodeEncodeError, ValueError, OSError, AttributeError):
        stream = getattr(sys, "stdout", None)
        buffer = getattr(stream, "buffer", None)
        if buffer is None:
            return
        try:
            buffer.write((line + "\n").encode("utf-8", errors="replace"))
            buffer.flush()
        except Exception:
            pass


def log(
    message: str,
    timestamp: Optional[datetime] = None,
    pid: Optional[int] = None,
    legacy_log_file: Path = config.LOG_FILE,
) -> None:
    line = format_log_line(message, timestamp=timestamp, pid=pid)
    safe_console_print(line)

    append_text(legacy_log_file, line + "\n")

    if session_log_file is not None:
        append_text(session_log_file, line + "\n")


def log_exception(prefix: str, exc: BaseException) -> None:
    log(f"{prefix}: {exc}")

    traceback_text = traceback.format_exc() + "\n"
    append_text(config.LOG_FILE, traceback_text)

    if session_log_file is not None:
        append_text(session_log_file, traceback_text)


def log_app_environment(initial_action: str) -> None:
    log(
        "App environment: "
        f"action={initial_action} pid={os.getpid()} exe={sys.executable} "
        f"argv={sys.argv} cwd={Path.cwd()}"
    )
    log(
        "Config: "
        f"model={config.MODEL_NAME} language={config.LANGUAGE} "
        f"prefer_cuda={config.PREFER_CUDA} local_files_only={config.LOCAL_FILES_ONLY} "
        f"sample_rate={config.SAMPLE_RATE} channels={config.CHANNELS} "
        f"min_audio_seconds={config.MIN_AUDIO_SECONDS} min_audio_rms={config.MIN_AUDIO_RMS}"
    )


# ---------------------------------------------------------------------
# CLI and local control
# ---------------------------------------------------------------------

def parse_cli_action(argv: Sequence[str]) -> str:
    if not argv:
        return "run-app"

    if len(argv) == 1 and argv[0] == "--toggle-record":
        return "toggle-record"

    if len(argv) == 1 and argv[0] == "--start-recording":
        return "start-recording"

    if len(argv) == 1 and argv[0] == "--resident":
        return "resident"

    if len(argv) == 1 and argv[0] == "--api":
        return "api"

    if len(argv) == 1 and argv[0] == "--show-history":
        return "show-history"

    raise ValueError(f"Unknown argument(s): {' '.join(argv)}")


def control_command_for_existing_instance(initial_action: str) -> Optional[str]:
    if initial_action == "start-recording":
        return "toggle-record"

    if initial_action == "show-history":
        return "show-history"

    if initial_action == "api":
        return json.dumps({"cmd": "health", "args": {}})

    return None


def visual_shell_enabled(initial_action: str) -> bool:
    return initial_action != "api"


def python_tray_enabled(initial_action: str) -> bool:
    return visual_shell_enabled(initial_action)


def startup_error_dialog_enabled(initial_action: str) -> bool:
    return visual_shell_enabled(initial_action)


def quote_argument(path: Path) -> str:
    return f'"{path}"'


def build_shortcut_specs(
    project_dir: Path,
    desktop_dir: Path,
    programs_dir: Path,
    startup_dir: Path,
    pythonw_path: Path,
) -> List[ShortcutSpec]:
    script_path = project_dir / "bubble_dictate.py"
    start_menu_dir = programs_dir / "Local Dictation"

    return [
        ShortcutSpec(
            name="desktop-toggle",
            shortcut_path=desktop_dir / "Local Dictation Toggle.lnk",
            target_path=pythonw_path,
            arguments=f"{quote_argument(script_path)} --toggle-record",
            working_directory=project_dir,
            description="Toggle local dictation recording",
        ),
        ShortcutSpec(
            name="desktop-history",
            shortcut_path=desktop_dir / "Local Dictation History.lnk",
            target_path=pythonw_path,
            arguments=f"{quote_argument(script_path)} --show-history",
            working_directory=project_dir,
            description="Show local dictation history",
        ),
        ShortcutSpec(
            name="start-menu-toggle",
            shortcut_path=start_menu_dir / "Local Dictation Toggle.lnk",
            target_path=pythonw_path,
            arguments=f"{quote_argument(script_path)} --toggle-record",
            working_directory=project_dir,
            description="Toggle local dictation recording",
        ),
        ShortcutSpec(
            name="start-menu-history",
            shortcut_path=start_menu_dir / "Local Dictation History.lnk",
            target_path=pythonw_path,
            arguments=f"{quote_argument(script_path)} --show-history",
            working_directory=project_dir,
            description="Show local dictation history",
        ),
        ShortcutSpec(
            name="startup-resident",
            shortcut_path=startup_dir / "Local Dictation Resident.lnk",
            target_path=pythonw_path,
            arguments=f"{quote_argument(script_path)} --resident",
            working_directory=project_dir,
            description="Start local dictation in resident mode",
        ),
    ]


def windows_kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
    return kernel32


def acquire_single_instance_lock() -> bool:
    global single_instance_mutex

    if os.name != "nt":
        return True

    if single_instance_mutex is not None:
        return True

    try:
        kernel32 = windows_kernel32()
        handle = kernel32.CreateMutexW(None, False, config.SINGLE_INSTANCE_MUTEX_NAME)
        last_error = ctypes.get_last_error()

        if not handle:
            log("Single-instance lock unavailable; continuing.")
            return True

        if last_error == 183:
            kernel32.CloseHandle(handle)
            return False

        single_instance_mutex = handle
        return True
    except Exception as exc:
        log_exception("Single-instance lock failed", exc)
        return True


def release_single_instance_lock() -> None:
    global single_instance_mutex

    if os.name != "nt" or single_instance_mutex is None:
        return

    try:
        windows_kernel32().CloseHandle(single_instance_mutex)
    except Exception:
        pass

    single_instance_mutex = None


def launch_lock_created_at(lock_path: Path) -> Optional[float]:
    try:
        content = lock_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    match = re.search(r"created_at=([0-9.]+)", content)

    if not match:
        return None

    try:
        return float(match.group(1))
    except ValueError:
        return None


def try_create_launch_lock(
    lock_path: Path = config.LAUNCH_LOCK_FILE,
    now: Optional[float] = None,
    pid: Optional[int] = None,
) -> bool:
    current_time = time.time() if now is None else now
    current_pid = os.getpid() if pid is None else pid
    lock_text = f"pid={current_pid} created_at={current_time:.3f}\n"

    try:
        if lock_path.exists():
            created_at = launch_lock_created_at(lock_path)
            lock_age = current_time - (created_at if created_at is not None else lock_path.stat().st_mtime)

            if lock_age <= config.LAUNCH_LOCK_STALE_SECONDS:
                return False

            lock_path.unlink()

        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)

        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(lock_text)

        return True
    except FileExistsError:
        return False
    except OSError as exc:
        log_exception("Launch lock failed open; allowing launch", exc)
        return True


def release_launch_lock(lock_path: Path = config.LAUNCH_LOCK_FILE) -> None:
    try:
        if lock_path.exists():
            lock_path.unlink()
    except OSError:
        pass


def send_control_command(command: str) -> bool:
    log(f"Sending control command: {command}")

    try:
        with socket.create_connection(
            (config.CONTROL_HOST, config.CONTROL_PORT),
            timeout=config.CONTROL_TIMEOUT_SECONDS,
        ) as client:
            client.settimeout(config.CONTROL_TIMEOUT_SECONDS)
            client.sendall(command.encode("utf-8") + b"\n")
            response_chunks = bytearray()
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                response_chunks.extend(chunk)
                if b"\n" in chunk or len(response_chunks) > CONTROL_MAX_COMMAND_BYTES:
                    break
            response = bytes(response_chunks).decode("utf-8", errors="replace").strip()
            log(f"Control command response: command={command} response={response}")
            if response == "ok":
                return True
            if response.startswith("{"):
                try:
                    parsed = json.loads(response)
                except json.JSONDecodeError:
                    return False
                return bool(isinstance(parsed, dict) and parsed.get("ok") is True)
            return False
    except OSError as exc:
        log(f"Control command failed: command={command} error={exc}")
        return False


def read_control_command(client, max_bytes: int = CONTROL_MAX_COMMAND_BYTES) -> str:
    data = bytearray()
    deadline = time.monotonic() + config.CONTROL_CLIENT_TIMEOUT_SECONDS

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Control request deadline exceeded.")
        client.settimeout(remaining)
        chunk = client.recv(4096)
        if not chunk:
            break

        data.extend(chunk)
        if len(data) > max_bytes:
            raise ValueError("Control command too large.")

        newline_index = data.find(b"\n")
        if newline_index != -1:
            data = data[:newline_index]
            break

    return data.decode("utf-8", errors="replace").strip()


def resolve_pythonw_path(current_python: Path, project_dir: Path) -> Path:
    project_pythonw = project_dir / ".venv" / "Scripts" / "pythonw.exe"

    if project_pythonw.exists():
        return project_pythonw

    candidate = current_python.with_name("pythonw.exe")

    if candidate.exists():
        return candidate

    return current_python


def pythonw_path() -> Path:
    return resolve_pythonw_path(
        current_python=Path(sys.executable),
        project_dir=Path(__file__).resolve().parent,
    )


def start_app_detached(initial_action: str) -> None:
    if not try_create_launch_lock():
        log(f"Detached launch suppressed by fresh launch lock. action={initial_action}")
        return

    command = [
        str(pythonw_path()),
        str(Path(__file__).resolve()),
        f"--{initial_action}",
    ]

    creationflags = 0
    startupinfo = None

    if os.name == "nt":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    log(f"Starting detached app: command={command}")

    subprocess.Popen(
        command,
        cwd=str(Path(__file__).resolve().parent),
        close_fds=True,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )


def show_bubble_window() -> None:
    if root is None:
        return

    root.deiconify()
    root.lift()
    root.attributes("-topmost", True)

    if bubble_layered:
        render_layered_bubble(root, current_bubble_text, current_bubble_bg)

    update_tray_menu()


def bubble_window_is_visible() -> bool:
    if root is None:
        return False

    try:
        return root.state() != "withdrawn" and bool(root.winfo_viewable())
    except tk.TclError:
        return False


def hide_bubble_window() -> None:
    if root is None:
        return

    try:
        root.withdraw()
    except tk.TclError:
        return

    update_tray_menu()


def toggle_bubble_window() -> None:
    if bubble_window_is_visible():
        hide_bubble_window()
    else:
        show_bubble_window()


def schedule_on_tk(callback) -> bool:
    if shutting_down or root is None:
        return False

    try:
        root.after(0, callback)
        return True
    except tk.TclError as exc:
        log(f"Tray callback skipped because Tk is unavailable: {exc}")
        return False


def tray_state_from_bubble(text: str, bg: str) -> str:
    if text == config.RECORDING_LABEL or bg == config.RECORDING_BG:
        return "recording"
    if text == config.TRANSCRIBING_LABEL or bg == config.TRANSCRIBING_BG:
        return "transcribing"
    if text == config.PASTE_READY_LABEL or bg == config.PASTE_READY_BG:
        return "paste-ready"
    if text == config.ERROR_LABEL or bg == config.ERROR_BG:
        return "error"
    return "ready"


def tray_status_for_state(state: str) -> dict:
    statuses = {
        "ready": {
            "glyph": "play",
            "bg": config.READY_BG,
            "title": "Local Dictation - Ready",
        },
        "recording": {
            "glyph": "stop",
            "bg": config.RECORDING_BG,
            "title": "Local Dictation - Recording",
        },
        "transcribing": {
            "glyph": "ellipsis",
            "bg": config.TRANSCRIBING_BG,
            "title": "Local Dictation - Transcribing",
        },
        "paste-ready": {
            "glyph": "paste",
            "bg": config.PASTE_READY_BG,
            "title": "Local Dictation - Paste ready",
        },
        "error": {
            "glyph": "error",
            "bg": config.ERROR_BG,
            "title": "Local Dictation - Error",
        },
    }
    return statuses.get(state, statuses["ready"])


def make_tray_image(state: str):
    if not icons.PIL_AVAILABLE:
        return None

    status = tray_status_for_state(state)
    return icons.render_bubble_rgba(
        status["glyph"],
        status["bg"],
        lighten_color(status["bg"]),
        window_size=64,
        circle_size=56,
    )


def tray_recording_menu_text(_item=None) -> str:
    with state_lock:
        is_recording = recording
        is_transcribing = transcribing

    if is_recording:
        return "Stop Recording"
    if is_transcribing:
        return "Transcribing..."
    return "Start Recording"


def tray_recording_menu_enabled(_item=None) -> bool:
    with state_lock:
        return not transcribing


def tray_bubble_menu_text(_item=None) -> str:
    return "Hide Bubble" if bubble_window_is_visible() else "Show Bubble"


def on_tray_toggle_recording(_icon=None, _item=None) -> None:
    schedule_on_tk(toggle_recording_from_shortcut)


def on_tray_toggle_bubble(_icon=None, _item=None) -> None:
    schedule_on_tk(toggle_bubble_window)


def on_tray_show_history(_icon=None, _item=None) -> None:
    schedule_on_tk(show_history_panel)


def on_tray_show_settings(_icon=None, _item=None) -> None:
    schedule_on_tk(show_settings_panel)


def on_tray_quit(_icon=None, _item=None) -> None:
    schedule_on_tk(quit_app)


def build_tray_menu():
    if pystray is None:
        return None

    item = pystray.MenuItem
    menu = pystray.Menu

    return menu(
        item(
            tray_recording_menu_text,
            on_tray_toggle_recording,
            default=True,
            visible=False,
            enabled=tray_recording_menu_enabled,
        ),
        item(tray_bubble_menu_text, on_tray_toggle_bubble),
        item(
            tray_recording_menu_text,
            on_tray_toggle_recording,
            enabled=tray_recording_menu_enabled,
        ),
        item("History", on_tray_show_history),
        item("Settings", on_tray_show_settings),
        menu.SEPARATOR,
        item("Quit", on_tray_quit),
    )


def update_tray_menu() -> None:
    if tray_icon is None:
        return

    try:
        tray_icon.update_menu()
    except Exception as exc:
        log(f"Tray menu update failed: {exc}")


def update_tray_state(state: str) -> None:
    global tray_state

    tray_state = state

    if tray_icon is None:
        return

    status = tray_status_for_state(state)

    try:
        tray_icon.icon = make_tray_image(state)
        tray_icon.title = status["title"]
        tray_icon.update_menu()
    except Exception as exc:
        log(f"Tray state update failed: {exc}")


def start_tray_icon() -> bool:
    global tray_icon

    if tray_icon is not None:
        return True

    if pystray is None:
        log(f"Tray icon unavailable: pystray import failed ({PYSTRAY_IMPORT_ERROR}).")
        return False

    if not icons.PIL_AVAILABLE:
        log("Tray icon unavailable: Pillow is not available.")
        return False

    state = tray_state_from_bubble(current_bubble_text, current_bubble_bg)
    status = tray_status_for_state(state)

    try:
        tray_icon = pystray.Icon(
            "local-dictation",
            icon=make_tray_image(state),
            title=status["title"],
            menu=build_tray_menu(),
        )
        tray_icon.run_detached()
        update_tray_state(state)
        log("Tray icon started.")
        return True
    except Exception as exc:
        tray_icon = None
        log_exception("Tray icon failed to start", exc)
        return False


def stop_tray_icon() -> None:
    global tray_icon

    icon = tray_icon
    tray_icon = None

    if icon is None:
        return

    try:
        icon.stop()
    except Exception:
        pass


def toggle_recording_from_shortcut() -> None:
    show_bubble_window()

    with state_lock:
        is_recording = recording
        is_transcribing = transcribing

    if is_transcribing:
        log("Shortcut ignored while transcribing.")
        return

    if is_recording:
        stop_recording(reason="shortcut-toggle")
    else:
        start_recording(source="shortcut-toggle")


def control_state_status(
    *,
    is_recording: bool,
    is_transcribing: bool,
    is_waiting: bool,
) -> str:
    if is_recording:
        return "recording"
    if is_transcribing:
        return "transcribing"
    if is_waiting:
        return "paste-ready"
    return "idle"


def control_settings_data() -> dict:
    return dict(SETTINGS)


def control_history_data() -> List[dict]:
    entries = load_transcript_history_entries()
    return [
        {"text": entry.text, "created_at": entry.created_at}
        for entry in reversed(entries)
    ]


def control_model_rank(choice: str, ordered_choices: List[str]) -> int:
    try:
        return ordered_choices.index(choice) + 1
    except ValueError:
        return len(ordered_choices) + 1


def control_models_data(args: dict) -> List[dict]:
    current_settings = settings.load_settings()
    custom_models = current_settings.get("custom_models", [])
    order = args.get("order") if isinstance(args, dict) else None
    if order not in settings.MODEL_ORDER_CHOICES:
        order = current_settings.get("model_order", settings.DEFAULT_SETTINGS["model_order"])

    speed_choices = settings.model_choices(custom_models, order="Speed")
    accuracy_choices = settings.model_choices(custom_models, order="Accuracy")
    selected_choices = settings.model_choices(custom_models, order=order)

    models = []
    for choice in selected_choices:
        details = dict(settings.model_tier_details(choice, custom_models=custom_models))
        if not details['available']:
            details['size_text'] = settings.MODEL_TIER_EXPECTED_SIZE_TEXT.get(choice, details['size_text'])
        details["speed_rank"] = control_model_rank(choice, speed_choices)
        details["accuracy_rank"] = control_model_rank(choice, accuracy_choices)
        with model_download_status_lock:
            status = dict(model_download_status.get(choice, {}))
        if details["available"]:
            details["download_status"] = "installed"
            details["download_error"] = ""
        elif status.get("status"):
            details["download_status"] = status["status"]
            details["download_error"] = status.get("error", "")
        else:
            details["download_status"] = "idle"
            details["download_error"] = ""
        models.append(details)
    return models


def control_state_data() -> dict:
    with state_lock:
        is_recording = recording
        is_transcribing = transcribing
        is_waiting = waiting_for_target_click
        transcript = latest_transcript or ""
        is_loading = loading
        error = operation_error or persistence.read_errors.get(config.SETTINGS_FILE, "") or persistence.read_errors.get(config.TRANSCRIPT_HISTORY_FILE, "")

    return {
        "recording": is_recording,
        "transcribing": is_transcribing,
        "waiting_for_target_click": is_waiting,
        "status": "error" if error and not (is_recording or is_transcribing or is_waiting) else control_state_status(
            is_recording=is_recording,
            is_transcribing=is_transcribing,
            is_waiting=is_waiting,
        ),
        "latestTranscript": transcript,
        "loading": is_loading,
        "error": error,
        "recording_ready": model is not None and audio_stream is not None and not is_loading,
        "history_revision": history_revision,
        "settings_error": persistence.read_errors.get(config.SETTINGS_FILE, ""),
        "history_error": persistence.read_errors.get(config.TRANSCRIPT_HISTORY_FILE, ""),
        "activeModel": SETTINGS.get("model", settings.DEFAULT_SETTINGS["model"]),
        "activeLanguage": SETTINGS.get("language", settings.DEFAULT_SETTINGS["language"]),
    }


def control_health_data() -> dict:
    state = control_state_data()
    uptime_seconds = max(time.monotonic() - backend_started_monotonic, 0.0)
    return {
        "version": BACKEND_VERSION,
        "pid": os.getpid(),
        "status": state["status"],
        "protocol_version": BACKEND_PROTOCOL_VERSION,
        "backend_owner": backend_owner,
        "model": SETTINGS.get("model", settings.DEFAULT_SETTINGS["model"]),
        "language": SETTINGS.get("language", settings.DEFAULT_SETTINGS["language"]),
        "device": active_device,
        "uptime_seconds": uptime_seconds,
        "launch_id": backend_launch_id or None,
        "loading": state['loading'],
        "recording_ready": state['recording_ready'],
        "error": state['error'],
    }


def control_shutdown_backend() -> dict:
    if root is None:
        raise ValueError("Tk root is not ready.")

    root.after(0, quit_app)
    return {"accepted": True}


def control_shutdown_owned_backend(args: dict) -> dict:
    if not backend_launch_id or args.get('launch_id') != backend_launch_id:
        raise ValueError("This backend does not belong to that launch. It was left running.")
    return control_shutdown_backend()


def control_retry_resources() -> dict:
    global loading
    if root is None:
        raise ValueError("Event loop is not ready.")
    with state_lock:
        if loading or recording or transcribing:
            raise ValueError("Resources are busy. Please wait.")
        loading = True
    root.after(0, lambda: threading.Thread(target=initialize_resources, daemon=True).start())
    return {'accepted': True}


def control_set_settings(args: dict) -> dict:
    global SETTINGS, model, active_device, loading, operation_error
    global hotkey_listener

    requested = args.get("settings") if isinstance(args, dict) else None
    if not isinstance(requested, dict):
        raise ValueError("Settings payload is required.")
    recover = args.get('recover', False)
    if not isinstance(recover, bool):
        raise ValueError("Settings recovery must be explicitly requested as a boolean.")

    if not settings_operation_lock.acquire(blocking=False):
        raise ValueError("Another settings operation is in progress. Please wait.")
    reserved_reload = False
    listener_prepared = False
    prepared_listener = None
    try:
        previous = dict(SETTINGS)
        cleaned = settings.merge_settings(previous, requested)
        for key, value in requested.items():
            if key not in settings.DEFAULT_SETTINGS or cleaned[key] != value:
                raise ValueError(f"Invalid setting: {key}")
        if cleaned['hotkey'] and not is_valid_hotkey(cleaned['hotkey']):
            raise ValueError("Invalid global shortcut.")
        hotkey_changed = cleaned['hotkey'] != previous['hotkey']
        reload_needed = any(cleaned[key] != previous[key] for key in ('model', 'device_mode')) or (model is None and 'model' in requested)
        if cleaned['model'] != previous['model'] and not settings.model_is_available_locally(cleaned['model'], custom_models=cleaned.get('custom_models')):
            raise ValueError(f"Model is not installed locally: {cleaned['model']}")
        with state_lock:
            if loading or ((reload_needed or hotkey_changed) and (recording or transcribing)):
                raise ValueError("Cannot change settings while resources are busy.")
            if reload_needed or hotkey_changed:
                loading = True
                reserved_reload = True
        candidate, device = model, active_device
        if reload_needed:
            candidate, device = build_model(cleaned)
        if hotkey_changed:
            prepared_listener = start_hotkey_listener(cleaned['hotkey'], strict=True)
            listener_prepared = True
        settings.save_settings(cleaned, recover=recover)
        with state_lock:
            SETTINGS = cleaned
            model, active_device = candidate, device
            if reload_needed:
                operation_error = "" if audio_stream is not None else "Recording unavailable: microphone is not initialized. Retry recording resources."
        if hotkey_changed:
            previous_listener, hotkey_listener = hotkey_listener, prepared_listener
            listener_prepared = False
            if previous_listener is not None:
                try:
                    previous_listener.stop()
                except Exception as exc:
                    log_exception('Previous shortcut listener cleanup failed', exc)
                    operation_error = f"Shortcut changed, but previous listener cleanup failed: {exc}"
        if root is not None:
            root.after(0, redraw_bubble_current_state)
            root.after(0, refresh_settings_panel)
        else:
            redraw_bubble_current_state()
            refresh_settings_panel()
        return dict(cleaned)
    except Exception as exc:
        with state_lock:
            operation_error = str(exc)
        raise
    finally:
        if listener_prepared and prepared_listener is not None:
            try:
                prepared_listener.stop()
            except Exception as exc:
                log_exception('Candidate shortcut listener cleanup failed', exc)
        if reserved_reload:
            with state_lock:
                loading = False
        settings_operation_lock.release()


def control_schedule_recording_action(command: str) -> dict:
    if root is None:
        raise ValueError("Tk root is not ready.")

    with state_lock:
        is_recording = recording
        is_transcribing = transcribing
        if loading:
            raise ValueError("Resources are loading. Please wait.")
        if command != "stop-recording" and (model is None or audio_stream is None):
            raise ValueError(operation_error or "Model or microphone is unavailable. Retry initialization.")

    if command == "start-recording":
        if is_transcribing:
            raise ValueError("Cannot start recording while transcribing.")
        if is_recording:
            raise ValueError("Already recording.")
        root.after(0, lambda: start_recording(source="tauri-bridge"))
    elif command == "stop-recording":
        if not is_recording:
            raise ValueError("Not recording.")
        root.after(0, lambda: stop_recording(reason="tauri-bridge"))
    elif command == "toggle-recording":
        if is_transcribing:
            raise ValueError("Cannot toggle recording while transcribing.")
        root.after(0, toggle_recording_from_shortcut)
    else:
        raise ValueError(f"Unknown recording command: {command}")

    return {"accepted": True, "state": control_state_data()}


def control_clear_history() -> List[dict]:
    global history_revision
    history_path = config.TRANSCRIPT_HISTORY_FILE
    with history_lock:
        persistence.atomic_write_json(history_path, [], recover=True)
        history_revision += 1
    log("Transcript history cleared from local bridge.")
    return []


def control_export_history(args: dict) -> str:
    raw_format = args.get("format") if isinstance(args, dict) else None
    if raw_format not in {"txt", "md"}:
        raise ValueError("Export format must be txt or md.")

    entries = list(reversed(load_transcript_history_entries()))
    if not entries:
        raise ValueError("No history to export.")

    text_format = "Markdown (.md)" if raw_format == "md" else "Plain Text"
    content = settings.format_history_export(entries, text_format)
    if not content:
        raise ValueError("No history to export.")

    export_dir = default_export_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = export_dir / f"dictation_export_{stamp}{settings.export_extension(text_format)}"
    export_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    log(f"Exported {len(entries)} transcripts from local bridge -> {out_path}")
    return str(out_path)


def set_model_download_status(choice: str, status: str, error: str = "") -> None:
    with model_download_status_lock:
        model_download_status[choice] = {"status": status, "error": error}


def control_download_model(args: dict) -> dict:
    choice = str(args.get("choice", "")).strip() if isinstance(args, dict) else ""
    if choice not in settings.model_choices(SETTINGS.get("custom_models")):
        raise ValueError("Unknown model choice.")

    with model_download_status_lock:
        if model_download_status.get(choice, {}).get('status') == 'downloading':
            return {"choice": choice, "status": "downloading"}
        model_download_status[choice] = {"status": "downloading", "error": ""}

    def worker() -> None:
        try:
            download_model_for_choice(
                choice,
                custom_models=SETTINGS.get("custom_models"),
            )
        except Exception as exc:
            log_exception("Model download failed from local bridge", exc)
            set_model_download_status(choice, "error", str(exc))
            return

        log(f"Model downloaded from local bridge: {choice}")
        set_model_download_status(choice, "idle")

    threading.Thread(target=worker, daemon=True).start()
    return {"choice": choice, "status": "downloading"}


def model_path_for_choice(choice: str) -> str:
    details = settings.model_tier_details(
        choice,
        custom_models=SETTINGS.get("custom_models"),
    )
    cache_dir = Path(str(details["cache_dir"]))
    if details["source_type"] == "local":
        return str(cache_dir)
    if details["available"] or cache_dir.exists():
        return str(cache_dir)
    return str(settings.huggingface_cache_root())


def control_open_model_folder(args: dict) -> str:
    choice = str(args.get("choice", "")).strip() if isinstance(args, dict) else ""
    if choice not in settings.model_choices(SETTINGS.get("custom_models")):
        raise ValueError("Unknown model choice.")

    path = Path(model_path_for_choice(choice))
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(str(path))
    log(f"Model folder opened from local bridge: {path}")
    return str(path)


def control_copy_model_path(args: dict) -> str:
    choice = str(args.get("choice", "")).strip() if isinstance(args, dict) else ""
    if choice not in settings.model_choices(SETTINGS.get("custom_models")):
        raise ValueError("Unknown model choice.")

    path = model_path_for_choice(choice)
    pyperclip.copy(path)
    log("Model path copied from local bridge.")
    return path


def control_add_custom_model(args: dict) -> dict:
    global SETTINGS

    name = str(args.get("name", "")).strip() if isinstance(args, dict) else ""
    source = str(args.get("source", "")).strip() if isinstance(args, dict) else ""
    if not name or not source:
        raise ValueError("Custom model name and source are required.")

    current_custom = list(SETTINGS.get("custom_models", []))
    normalized = settings.normalize_custom_models(
        current_custom + [{"name": name, "source": source}]
    )
    if len(normalized) == len(current_custom):
        raise ValueError("Use a unique name and a valid Hugging Face repo ID or faster-whisper model folder.")

    control_set_settings({'settings': {'custom_models': normalized}})
    log(f"Custom model added from local bridge: {name}")
    return dict(SETTINGS)


class BubbleControlActions:
    def health(self):
        return control_health_data()

    def backend_owner(self):
        return backend_owner

    def shutdown_backend(self):
        return control_shutdown_backend()

    def shutdown_owned_backend(self, args: dict):
        return control_shutdown_owned_backend(args)

    def retry_resources(self):
        return control_retry_resources()

    def get_settings(self):
        return control_settings_data()

    def get_history(self):
        return control_history_data()

    def list_models(self, args: dict):
        return control_models_data(args)

    def get_state(self):
        return control_state_data()

    def set_settings(self, args: dict):
        return control_set_settings(args)

    def recording_action(self, command: str):
        return control_schedule_recording_action(command)

    def clear_history(self):
        return control_clear_history()

    def export_history(self, args: dict):
        return control_export_history(args)

    def download_model(self, args: dict):
        return control_download_model(args)

    def open_model_folder(self, args: dict):
        return control_open_model_folder(args)

    def copy_model_path(self, args: dict):
        return control_copy_model_path(args)

    def add_custom_model(self, args: dict):
        return control_add_custom_model(args)

    def legacy_action(self, command: str) -> bool:
        if root is None:
            log(f"Control command rejected because root is not ready: {command}")
            return False

        if command == "toggle-record":
            root.after(0, toggle_recording_from_shortcut)
            return True
        if command == "show-history":
            root.after(0, show_history_panel)
            return True
        return False


def control_exception_logger(command: str, exc: BaseException) -> None:
    log_exception(f"JSON control command failed: {command}", exc)


def handle_control_command(command: str) -> str:
    # Never log raw request arguments, which can contain private paths/content.

    if (
        not command.lstrip().startswith(("{", "["))
        and command not in {"toggle-record", "show-history"}
    ):
        log("Unsupported legacy control command rejected.")
        return "error"

    router = ControlCommandRouter(
        BubbleControlActions(),
        exception_logger=control_exception_logger,
    )
    return router.handle(command)


def serve_control_client(client, slots) -> None:
    try:
        with client:
            client.settimeout(config.CONTROL_CLIENT_TIMEOUT_SECONDS)
            try:
                response = handle_control_command(read_control_command(client))
            except Exception as exc:
                response = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
            try:
                client.sendall(response.encode('utf-8') + b'\n')
            except OSError:
                pass
    finally:
        slots.release()


def control_server_loop(stop_event: threading.Event) -> None:
    slots = threading.BoundedSemaphore(8)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((config.CONTROL_HOST, config.CONTROL_PORT))
            server.listen(5)
            server.settimeout(0.5)
            log(f"Control server listening on {config.CONTROL_HOST}:{config.CONTROL_PORT}.")

            while not stop_event.is_set():
                try:
                    client, _address = server.accept()
                except socket.timeout:
                    continue

                if not slots.acquire(blocking=False):
                    client.close()
                    continue
                threading.Thread(target=serve_control_client, args=(client, slots), daemon=True).start()
    except Exception as exc:
        log_exception("Control server failed", exc)


def start_control_server() -> threading.Event:
    stop_event = threading.Event()
    thread = threading.Thread(
        target=control_server_loop,
        args=(stop_event,),
        daemon=True,
    )
    thread.start()
    return stop_event


# ---------------------------------------------------------------------
# Transcript history
# ---------------------------------------------------------------------

def load_transcript_history_entries(
    history_path: Path = config.TRANSCRIPT_HISTORY_FILE,
) -> List[TranscriptHistoryEntry]:
    with history_lock:
        try:
            data = persistence.read_json(history_path, list)
        except ValueError:
            return []

    if not isinstance(data, list):
        return []

    entries: List[TranscriptHistoryEntry] = []

    for item in data:
        if isinstance(item, str) and item.strip():
            entries.append(TranscriptHistoryEntry(text=item.strip()))
        elif isinstance(item, dict):
            text = item.get("text")
            created_at = item.get("created_at")

            if isinstance(text, str) and text.strip():
                entries.append(
                    TranscriptHistoryEntry(
                        text=text.strip(),
                        created_at=created_at if isinstance(created_at, str) else None,
                    )
                )

    return entries


def load_transcript_history(history_path: Path = config.TRANSCRIPT_HISTORY_FILE) -> List[str]:
    return [entry.text for entry in load_transcript_history_entries(history_path)]


def save_transcript_history(history: List[str], history_path: Path) -> None:
    with history_lock:
        persistence.atomic_write_json(history_path, history)


def save_transcript_history_entries(
    entries: List[TranscriptHistoryEntry],
    history_path: Path,
) -> None:
    with history_lock:
        data = [
            {"text": entry.text, "created_at": entry.created_at}
            for entry in entries
        ]
        persistence.atomic_write_json(history_path, data)


def add_transcript_to_history(
    text: str,
    history_path: Path = config.TRANSCRIPT_HISTORY_FILE,
    limit: int = config.TRANSCRIPT_HISTORY_LIMIT,
) -> List[str]:
    global history_revision
    cleaned = text.strip()
    with history_lock:
        entries = load_transcript_history_entries(history_path)
        if not cleaned:
            return [entry.text for entry in entries]
        entries.append(
            TranscriptHistoryEntry(
                text=cleaned,
                created_at=datetime.now().isoformat(timespec="seconds"),
            )
        )
        entries = entries[-limit:]
        save_transcript_history_entries(entries, history_path)
        history_revision += 1
    return [entry.text for entry in entries]


def history_items_for_display(
    history_path: Path = config.TRANSCRIPT_HISTORY_FILE,
    limit: int = config.TRANSCRIPT_HISTORY_LIMIT,
) -> List[str]:
    history = load_transcript_history(history_path)
    return list(reversed(history[-limit:]))


def quick_history_items_for_display(
    history_path: Path = config.TRANSCRIPT_HISTORY_FILE,
    limit: int = 3,
) -> List[TranscriptHistoryEntry]:
    entries = load_transcript_history_entries(history_path)
    return list(reversed(entries[-limit:]))


# ---------------------------------------------------------------------
# Text cleanup
# ---------------------------------------------------------------------

def capitalize_line_starts(text: str) -> str:
    chars = list(text)
    capitalize_next = True

    for index, char in enumerate(chars):
        if char == "\n":
            capitalize_next = True
            continue

        if capitalize_next and char.isalpha():
            chars[index] = char.upper()
            capitalize_next = False
        elif not char.isspace():
            capitalize_next = False

    return "".join(chars)


def clean_transcript_text(text: str, language: Optional[str] = "en", *, spoken_punctuation: bool = False) -> str:
    cleaned = text.strip()

    if not cleaned:
        return ""

    cleaned = re.sub(r"[ \t\r\f\v]+", " ", cleaned)
    if not spoken_punctuation:
        return cleaned

    if language == "en":
        replacements = [
            (r"\bnew paragraph\b", "\n\n"),
            (r"\bnew line\b", "\n"),
            (r"\bquestion mark\b", "?"),
            (r"\bexclamation mark\b", "!"),
            (r"\bfull stop\b", "."),
            (r"\bperiod\b", "."),
            (r"\bcomma\b", ","),
        ]

        for pattern, replacement in replacements:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+([,.?!])", r"\1", cleaned)
    cleaned = re.sub(r"([,.?!])\1+", r"\1", cleaned)
    cleaned = re.sub(r"([,.?!])(?=[^\s\n])", r"\1 ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ ]{2,}", " ", cleaned)
    cleaned = cleaned.strip()

    if language == "en":
        return capitalize_line_starts(cleaned)
    return cleaned


# ---------------------------------------------------------------------
# Runtime settings accessors
# ---------------------------------------------------------------------

def effective_model_name() -> str:
    return settings.model_tier_to_name(
        SETTINGS["model"],
        custom_models=SETTINGS.get("custom_models"),
    )


def effective_language() -> Optional[str]:
    return settings.language_to_whisper_code(SETTINGS["language"])


def current_palette() -> dict:
    return settings.palette_for(SETTINGS["theme"])


def current_alpha() -> float:
    return SETTINGS["opacity"] / 100.0


def effective_device_mode() -> str:
    device_mode = SETTINGS.get("device_mode", settings.DEFAULT_SETTINGS["device_mode"])
    if device_mode in settings.DEVICE_MODE_CHOICES:
        return device_mode
    return "auto" if config.PREFER_CUDA else "cpu"


# ---------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------

def make_cuda_model(values=None) -> WhisperModel:
    values = SETTINGS if values is None else values
    return WhisperModel(
        str(settings.local_model_path(values['model'], values.get('custom_models'))),
        device="cuda",
        compute_type=config.CUDA_COMPUTE_TYPE,
        download_root=config.MODEL_DOWNLOAD_ROOT,
        local_files_only=config.LOCAL_FILES_ONLY,
        num_workers=config.MODEL_NUM_WORKERS,
    )


def make_cpu_model(values=None) -> WhisperModel:
    values = SETTINGS if values is None else values
    return WhisperModel(
        str(settings.local_model_path(values['model'], values.get('custom_models'))),
        device="cpu",
        compute_type=config.CPU_COMPUTE_TYPE,
        cpu_threads=config.CPU_THREADS,
        download_root=config.MODEL_DOWNLOAD_ROOT,
        local_files_only=config.LOCAL_FILES_ONLY,
        num_workers=config.MODEL_NUM_WORKERS,
    )


def warm_up_model(loaded_model: WhisperModel, values=None) -> None:
    """
    Forces the actual backend libraries to run immediately.

    Without this, CUDA can appear to load successfully, then fail later during
    the first real transcription with errors such as cublas64_12.dll missing.
    """
    silence = np.zeros(config.SAMPLE_RATE, dtype=np.float32)

    segments, _info = loaded_model.transcribe(
        silence,
        language=settings.language_to_whisper_code((values or SETTINGS)['language']),
        task="transcribe",
        beam_size=1,
        best_of=1,
        vad_filter=False,
        condition_on_previous_text=False,
        temperature=0.0,
    )

    # Force generator execution.
    for _segment in segments:
        pass


def build_model(values: dict) -> tuple:
    device_mode = values['device_mode']
    log(f"Loading model on device mode {device_mode}")

    if device_mode in {"auto", "cuda"}:
        try:
            log(f"Trying CUDA {config.CUDA_COMPUTE_TYPE}...")
            loaded_model = make_cuda_model(values)
            warm_up_model(loaded_model, values)
            log("Model loaded and warmed up on CUDA.")
            return loaded_model, 'cuda'
        except Exception as exc:
            if device_mode == "cuda":
                log_exception("CUDA model load failed and CPU fallback is disabled", exc)
                raise
            log_exception("CUDA failed; falling back to CPU", exc)

    log(f"Using CPU {config.CPU_COMPUTE_TYPE}.")
    loaded_model = make_cpu_model(values)
    warm_up_model(loaded_model, values)
    log("Model loaded and warmed up on CPU.")
    return loaded_model, 'cpu'


def load_model() -> WhisperModel:
    global active_device
    loaded_model, device = build_model(dict(SETTINGS))
    active_device = device
    return loaded_model


# ---------------------------------------------------------------------
# Bubble UI helpers
# ---------------------------------------------------------------------

def bubble_icon_for_state(text: str) -> str:
    if text == config.READY_LABEL:
        return "play"
    if text == config.RECORDING_LABEL:
        return "stop"
    if text == config.TRANSCRIBING_LABEL:
        return "ellipsis"
    if text == config.PASTE_READY_LABEL:
        return "paste"
    if text == config.PASTED_LABEL:
        return "check"
    return "text"


def lighten_color(hex_color: str, amount: float = 0.18) -> str:
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
    except (ValueError, IndexError):
        return hex_color

    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


_glyph_photo_cache: dict = {}


def glyph_photo(name: str, color: str, size: int):
    key = (name, color, size)
    photo = _glyph_photo_cache.get(key)
    if photo is None:
        from PIL import ImageTk

        image = icons.render_glyph(name, color, size)
        photo = ImageTk.PhotoImage(image)
        _glyph_photo_cache[key] = photo
    return photo


def draw_bubble_state(canvas: tk.Canvas, text: str, bg: str) -> None:
    # Vector fallback only. The smooth, halo-free bubble is drawn by the layered
    # window (render_layered_bubble); this path runs when that is unavailable.
    canvas.delete("all")
    size = config.BUBBLE_SIZE
    icon = bubble_icon_for_state(text)
    cx = size / 2

    canvas.create_oval(1, 1, size - 1, size - 1, fill=bg, outline=bg)
    canvas.create_oval(1, 1, size - 1, size - 1, outline=lighten_color(bg), width=1)

    if icon == "play":
        canvas.create_polygon(13, 10, 13, 22, 23, 16, fill="white", outline="")
    elif icon == "stop":
        canvas.create_rectangle(12, 12, 20, 20, fill="white", outline="")
    elif icon == "ellipsis":
        for x in (11, 16, 21):
            canvas.create_oval(x - 1.5, 14.5, x + 1.5, 17.5, fill="white", outline="")
    elif icon == "paste":
        # Downward arrow into a tray: "click a field to drop the text".
        canvas.create_line(cx, 8, cx, 18, fill="white", width=2, capstyle="round")
        canvas.create_line(cx - 4, 14, cx, 18, fill="white", width=2, capstyle="round", joinstyle="round")
        canvas.create_line(cx + 4, 14, cx, 18, fill="white", width=2, capstyle="round", joinstyle="round")
        canvas.create_line(cx - 5, 23, cx + 5, 23, fill="white", width=2, capstyle="round")
    elif icon == "check":
        canvas.create_line(9, 16, 14, 21, 23, 11, fill="white", width=2, capstyle="round", joinstyle="round")
    elif text == config.ERROR_LABEL:
        # Clean exclamation glyph (calmer than a bold red "!").
        canvas.create_line(cx, 9, cx, 18, fill="white", width=2, capstyle="round")
        canvas.create_oval(cx - 1.3, 21, cx + 1.3, 23.6, fill="white", outline="")
    else:
        canvas.create_text(
            size // 2,
            size // 2,
            anchor="center",
            fill="white",
            font=(config.BUBBLE_FONT_FAMILY, config.BUBBLE_FONT_SIZE, config.BUBBLE_FONT_WEIGHT),
            text=text,
        )


def set_bubble(text: str, bg: str) -> None:
    global current_bubble_text, current_bubble_bg

    if root is None:
        return

    if config.DEBUG_LOG_BUBBLE_STATES:
        log(f"Bubble state requested: text={text} bg={bg}")

    current_bubble_text = text
    current_bubble_bg = bg

    def update() -> None:
        if bubble_layered:
            render_layered_bubble(root, text, bg)
        elif bubble is not None:
            draw_bubble_state(bubble, text, bg)
        update_tray_state(tray_state_from_bubble(text, bg))

    root.after(0, update)


def should_quit_from_left_hold(
    hold_seconds: float,
    moved: bool,
    still_pressed: bool,
) -> bool:
    return (
        still_pressed
        and not moved
        and hold_seconds >= config.LEFT_HOLD_QUIT_SECONDS
    )


def recording_stop_diagnostic_summary(
    session_id: int,
    stop_reason: str,
    duration_seconds: float,
    chunks_captured: int,
    callback_chunks: int,
    callback_frames: int,
    first_audio_delay: Optional[float],
    last_audio_age: Optional[float],
    status_events: Sequence[str],
) -> str:
    if chunks_captured == 0 and duration_seconds < config.BUBBLE_GLOBAL_CLICK_IGNORE_SECONDS:
        diagnosis = "likely-immediate-stop"
    elif chunks_captured == 0 and callback_chunks == 0:
        diagnosis = "stream-delivered-no-callbacks"
    elif chunks_captured == 0:
        diagnosis = "callbacks-seen-but-no-chunks-copied"
    else:
        diagnosis = "audio-captured"

    first_delay = "none" if first_audio_delay is None else f"{first_audio_delay:.3f}s"
    last_age = "none" if last_audio_age is None else f"{last_audio_age:.3f}s"
    statuses = "none" if not status_events else " | ".join(status_events[-5:])

    return (
        f"Recording stop diagnostics: session={session_id} reason={stop_reason} "
        f"duration={duration_seconds:.2f}s chunks={chunks_captured} "
        f"callback_chunks={callback_chunks} callback_frames={callback_frames} "
        f"first_audio_delay={first_delay} last_audio_age={last_age} "
        f"status_events={statuses} diagnosis={diagnosis}"
    )


# ---------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------

def audio_callback(indata, frames, time_info, status) -> None:
    global recording_callback_chunks, recording_callback_frames
    global recording_first_audio_monotonic, recording_last_audio_monotonic

    if status:
        status_text = str(status)
        log(f"Audio status: {status_text}")

    with state_lock:
        if status and len(recording_status_events) < 20:
            recording_status_events.append(str(status))

        if recording:
            audio_chunks.append(indata.copy())
            recording_callback_chunks += 1
            recording_callback_frames += frames

            now = time.monotonic()
            is_first_callback = recording_first_audio_monotonic is None

            if is_first_callback:
                recording_first_audio_monotonic = now

            recording_last_audio_monotonic = now
            session_id = current_recording_session_id
            callback_count = recording_callback_chunks
        else:
            return

    if config.DEBUG_LOG_AUDIO_FIRST_CALLBACK and is_first_callback:
        log(
            f"Audio callback first chunk: session={session_id} "
            f"frames={frames} callback_chunks={callback_count}"
        )
    elif (
        config.DEBUG_LOG_AUDIO_EVERY_N_CALLBACKS > 0
        and callback_count % config.DEBUG_LOG_AUDIO_EVERY_N_CALLBACKS == 0
    ):
        log(
            f"Audio callback heartbeat: session={session_id} "
            f"frames={frames} callback_chunks={callback_count}"
        )


def audio_is_too_quiet(audio: np.ndarray) -> bool:
    if audio.size == 0:
        return True

    rms = float(np.sqrt(np.mean(np.square(np.asarray(audio, dtype=np.float32)))))
    log(f"Audio RMS: {rms:.6f}")

    return rms < config.MIN_AUDIO_RMS


def transcribe_audio(audio: np.ndarray) -> str:
    if model is None:
        raise RuntimeError("Model is not loaded.")

    if audio.size == 0:
        return ""

    audio = np.asarray(audio, dtype=np.float32).reshape(-1)

    duration_seconds = len(audio) / config.SAMPLE_RATE
    log(f"Audio duration: {duration_seconds:.2f} seconds")

    if duration_seconds < config.MIN_AUDIO_SECONDS:
        log("Audio too short; ignoring.")
        return ""

    if audio_is_too_quiet(audio):
        log("Audio too quiet; ignoring.")
        return ""

    segments, _info = model.transcribe(
        audio,
        language=effective_language(),
        task="transcribe",
        beam_size=1,
        best_of=1,
        vad_filter=False,
        condition_on_previous_text=False,
        temperature=0.0,
    )

    parts: List[str] = []

    for segment in segments:
        text = segment.text.strip()
        if text:
            parts.append(text)

    return " ".join(parts).strip()


# ---------------------------------------------------------------------
# Recording flow
# ---------------------------------------------------------------------

def start_recording(source: str = "unknown") -> None:
    global recording, audio_chunks, latest_transcript, waiting_for_target_click
    global paste_after_transcription
    global recording_session_counter, current_recording_session_id
    global recording_started_monotonic, recording_callback_chunks
    global recording_callback_frames, recording_first_audio_monotonic
    global recording_last_audio_monotonic, recording_status_events
    global operation_error

    with state_lock:
        if recording or transcribing or loading:
            log(f"Ignored start: source={source} already recording or transcribing.")
            return
        if model is None or audio_stream is None:
            operation_error = "Recording is unavailable. Check the model and microphone, then retry initialization."
            return

        recording_session_counter += 1
        current_recording_session_id = recording_session_counter
        recording_started_monotonic = time.monotonic()
        recording_callback_chunks = 0
        recording_callback_frames = 0
        recording_first_audio_monotonic = None
        recording_last_audio_monotonic = None
        recording_status_events = []
        audio_chunks = []
        operation_error = ""
        waiting_for_target_click = False
        paste_after_transcription = False
        recording = True
        session_id = current_recording_session_id

    log(f"Recording started. session={session_id} source={source}")
    set_bubble(config.RECORDING_LABEL, config.RECORDING_BG)


def stop_recording(reason: str = "unknown") -> None:
    global recording, transcribing, audio_chunks

    with state_lock:
        if not recording:
            log(f"Ignored stop: reason={reason} not recording.")
            return

        recording = False
        transcribing = True
        chunks, audio_chunks = audio_chunks, []
        session_id = current_recording_session_id
        started_at = recording_started_monotonic
        callback_chunks = recording_callback_chunks
        callback_frames = recording_callback_frames
        first_audio_at = recording_first_audio_monotonic
        last_audio_at = recording_last_audio_monotonic
        statuses = list(recording_status_events)

    stopped_at = time.monotonic()
    duration_seconds = 0.0 if started_at is None else stopped_at - started_at
    first_audio_delay = None if started_at is None or first_audio_at is None else first_audio_at - started_at
    last_audio_age = None if last_audio_at is None else stopped_at - last_audio_at

    log(f"Recording stopped. session={session_id} reason={reason} chunks={len(chunks)}")
    log(
        recording_stop_diagnostic_summary(
            session_id=session_id,
            stop_reason=reason,
            duration_seconds=duration_seconds,
            chunks_captured=len(chunks),
            callback_chunks=callback_chunks,
            callback_frames=callback_frames,
            first_audio_delay=first_audio_delay,
            last_audio_age=last_audio_age,
            status_events=statuses,
        )
    )
    set_bubble(config.TRANSCRIBING_LABEL, config.TRANSCRIBING_BG)

    threading.Thread(
        target=process_recording,
        args=(chunks, session_id),
        daemon=True,
    ).start()


def process_recording(chunks: List[np.ndarray], session_id: int) -> None:
    global transcribing, latest_transcript, waiting_for_target_click
    global paste_after_transcription, operation_error
    with state_lock:
        if current_recording_session_id != session_id:
            chunks.clear()
            return
    try:
        if chunks:
            audio = np.concatenate(chunks, axis=0)
            chunks.clear()
            text = transcribe_audio(audio)
            del audio
        else:
            text = ''
        if config.ENABLE_TEXT_CLEANUP:
            text = clean_transcript_text(text, language=effective_language(),
                                         spoken_punctuation=config.INTERPRET_SPOKEN_PUNCTUATION)
    except Exception as exc:
        log_exception("Transcription failed", exc)
        with state_lock:
            if current_recording_session_id != session_id:
                return
            transcribing = False
            waiting_for_target_click = False
            paste_after_transcription = False
            operation_error = f"Transcription failed: {exc}"
        set_bubble(config.ERROR_LABEL, config.ERROR_BG)
        return
    finally:
        chunks.clear()

    with state_lock:
        if current_recording_session_id != session_id:
            return
        transcribing = False
        should_auto_paste = paste_after_transcription
        paste_after_transcription = False
        waiting_for_target_click = bool(text)
        if text:
            latest_transcript = text

    if not text:
        set_bubble(config.EMPTY_LABEL, config.EMPTY_BG)
        time.sleep(config.EMPTY_STATE_SECONDS)
        reset_bubble_if_current(session_id)
        return

    # Text is application output first. Delivery and persistence fail separately.
    failures = []
    if config.SAVE_TRANSCRIPT_HISTORY:
        try:
            add_transcript_to_history(text)
        except Exception as exc:
            failures.append(f"History could not be saved: {exc}")
    with state_lock:
        if current_recording_session_id != session_id:
            return
    try:
        pyperclip.copy(text)
    except Exception as exc:
        failures.append(f"Clipboard unavailable: {exc}. Text retained; try again.")
    with state_lock:
        if current_recording_session_id != session_id:
            return
        operation_error = ' '.join(failures)
    set_bubble(config.PASTE_READY_LABEL, config.PASTE_READY_BG)
    if should_auto_paste or (config.AUTO_PASTE_WHEN_EDITABLE and focused_field_is_editable()):
        paste_after_target_click(expected_session_id=session_id)


def reset_bubble_if_current(session_id: int) -> None:
    with state_lock:
        if current_recording_session_id != session_id or recording or transcribing or waiting_for_target_click:
            return
    set_bubble(config.READY_LABEL, config.READY_BG)


# ---------------------------------------------------------------------
# History panel
# ---------------------------------------------------------------------

def preview_text(text: str, limit: int = 64) -> str:
    preview = " ".join(text.split())

    if len(preview) <= limit:
        return preview

    return preview[: limit - 1].rstrip() + "..."


def truncate_text_to_pixel_width(
    text: str,
    max_width: int,
    measure: Callable[[str], int],
    ellipsis: str = "...",
) -> str:
    preview = " ".join(text.split())

    if not preview or max_width <= 0:
        return ""

    if measure(preview) <= max_width:
        return preview

    if measure(ellipsis) > max_width:
        return ""

    low = 0
    high = len(preview)
    best = ""

    while low <= high:
        mid = (low + high) // 2
        candidate = preview[:mid].rstrip() + ellipsis

        if measure(candidate) <= max_width:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1

    prefix = best[:-len(ellipsis)].rstrip() if best.endswith(ellipsis) else best
    if " " in prefix:
        word_prefix = prefix.rsplit(" ", 1)[0].rstrip()
        if len(word_prefix) >= max(1, int(len(prefix) * 0.7)):
            best = word_prefix + ellipsis

    return best


def wrap_text_to_pixel_lines(
    text: str,
    max_lines: int,
    max_width: int,
    measure: Callable[[str], int],
    ellipsis: str = "...",
) -> List[str]:
    words = " ".join(text.split()).split()
    if not words or max_lines <= 0 or max_width <= 0:
        return []

    lines: List[str] = []
    current = ""
    index = 0

    while index < len(words) and len(lines) < max_lines:
        word = words[index]
        candidate = word if not current else f"{current} {word}"

        if measure(candidate) <= max_width:
            current = candidate
            index += 1
            continue

        if current:
            lines.append(current)
            current = ""
            continue

        lines.append(
            truncate_text_to_pixel_width(
                word,
                max_width=max_width,
                measure=measure,
                ellipsis=ellipsis,
            )
        )
        index += 1

    if current and len(lines) < max_lines:
        lines.append(current)

    if index < len(words) and lines:
        lines[-1] = truncate_text_to_pixel_width(
            f"{lines[-1]} {' '.join(words[index:])}",
            max_width=max_width,
            measure=measure,
            ellipsis=ellipsis,
        )

    return lines


def quick_history_preview_lines(
    text: str,
    max_lines: int = 2,
    max_line_chars: int = 34,
) -> List[str]:
    words = " ".join(text.split()).split()
    if not words or max_lines <= 0 or max_line_chars <= 3:
        return []

    lines: List[str] = []
    current = ""
    word_index = 0
    truncated = False

    while word_index < len(words):
        word = words[word_index]

        if len(word) > max_line_chars:
            if current:
                lines.append(current)
                current = ""
                if len(lines) >= max_lines:
                    truncated = True
                    break

            lines.append(word[: max_line_chars - 3].rstrip() + "...")
            word_index += 1
            truncated = word_index < len(words)
            break

        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_line_chars:
            current = candidate
            word_index += 1
            continue

        lines.append(current)
        current = ""
        if len(lines) >= max_lines:
            truncated = True
            break

    if current and len(lines) < max_lines:
        lines.append(current)

    if word_index < len(words):
        truncated = True

    if truncated and lines and not lines[-1].endswith("..."):
        suffix_budget = max_line_chars - 3
        lines[-1] = lines[-1][:suffix_budget].rstrip() + "..."

    return lines[:max_lines]


def copy_history_text(text: str) -> None:
    pyperclip.copy(text)
    log("History transcript copied.")
    set_bubble(config.PASTED_LABEL, config.PASTED_BG)


def paste_history_text(text: str) -> None:
    pyperclip.copy(text)
    threading.Thread(
        target=paste_text_to_active_target,
        args=(text,),
        daemon=True,
    ).start()


def history_panel_layout() -> dict:
    return {
        "preview_width_chars": 48,
        "copy_icon_size": 18,
        "action_count": 1,
        "row_pad_x": 12,
        "row_pad_y": 5,
    }


def make_icon_button(
    parent,
    palette,
    icon_name: str,
    command,
    size: int = 34,
    icon_size: int = 17,
):
    button = tk.Button(
        parent,
        text="",
        width=size,
        height=size,
        bd=0,
        relief="flat",
        bg=palette["button_bg"],
        activebackground=palette["button_hover"],
        cursor="hand2",
        command=command,
    )

    if icons.PIL_AVAILABLE:
        try:
            photo = glyph_photo(icon_name, palette["text"], icon_size)
            button.configure(image=photo)
            button.image = photo
        except Exception as exc:
            log_exception("Icon button glyph failed", exc)
            button.configure(text=icon_name[:1].upper(), fg=palette["text"])
    else:
        button.configure(text=icon_name[:1].upper(), fg=palette["text"])

    return button


def show_history_panel() -> None:
    global history_panel

    show_bubble_window()

    if root is None:
        return

    if history_panel is not None and history_panel.winfo_exists():
        history_panel.lift()
        return

    palette = current_palette()

    panel = tk.Toplevel(root)
    history_panel = panel
    panel.title("Local Dictation History")
    panel.attributes("-topmost", True)
    panel.resizable(False, False)
    panel.geometry("+80+260")
    panel.configure(bg=palette["panel_bg"])
    try:
        panel.attributes("-alpha", current_alpha())
    except tk.TclError:
        pass

    layout = history_panel_layout()

    header = tk.Label(
        panel,
        text="Last 5",
        anchor="w",
        padx=layout["row_pad_x"],
        pady=8,
        bg=palette["panel_bg"],
        fg=palette["text"],
        font=(config.BUBBLE_FONT_FAMILY, 9, "bold"),
    )
    header.grid(row=0, column=0, columnspan=2, sticky="ew")

    items = history_items_for_display()

    if not items:
        empty = tk.Label(
            panel,
            text="No transcripts yet",
            padx=8,
            pady=8,
            anchor="w",
            bg=palette["panel_bg"],
            fg=palette["muted_text"],
        )
        empty.grid(row=1, column=0, columnspan=2, sticky="ew")
    else:
        for row, text in enumerate(items, start=1):
            label = tk.Label(
                panel,
                text=preview_text(text),
                width=layout["preview_width_chars"],
                anchor="w",
                padx=layout["row_pad_x"],
                pady=layout["row_pad_y"],
                bg=palette["panel_bg"],
                fg=palette["text"],
            )
            label.grid(row=row, column=0, sticky="w")

            copy_button = make_icon_button(
                panel,
                palette,
                "copy",
                lambda value=text: copy_history_text(value),
                size=32,
                icon_size=layout["copy_icon_size"],
            )
            copy_button.grid(row=row, column=1, padx=(2, 10), pady=4)

    close_button = tk.Button(
        panel,
        text="Close",
        bg=palette["button_bg"],
        fg=palette["text"],
        activebackground=palette["button_hover"],
        relief="flat",
        command=panel.destroy,
    )
    close_button.grid(row=6, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

    panel.protocol("WM_DELETE_WINDOW", panel.destroy)


def close_quick_history_popover() -> None:
    global quick_history_popover

    if quick_history_popover is not None and quick_history_popover.winfo_exists():
        quick_history_popover.destroy()

    quick_history_popover = None


def draw_round_rect(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    radius: int,
    **kwargs,
) -> None:
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    canvas.create_polygon(points, smooth=True, **kwargs)


def draw_quick_canvas_button(
    canvas: tk.Canvas,
    x: int,
    y: int,
    width: int,
    height: int,
    text: str,
    command,
    tag: str,
    fill: str,
    hover_fill: str,
    outline: str,
    font_size: int = 12,
    text_color: str = config.QUICK_HISTORY_TEXT,
) -> None:
    bg_tag = f"{tag}-bg"

    draw_round_rect(
        canvas,
        x,
        y,
        x + width,
        y + height,
        radius=7,
        fill=fill,
        outline=outline,
        width=1,
        tags=(tag, bg_tag),
    )
    canvas.create_text(
        x + width // 2,
        y + height // 2,
        anchor="center",
        fill=text_color,
        font=(config.BUBBLE_FONT_FAMILY, font_size),
        text=text,
        tags=(tag,),
    )
    canvas.tag_bind(tag, "<Button-1>", lambda _event: command())
    canvas.tag_bind(tag, "<Enter>", lambda _event: canvas.itemconfigure(bg_tag, fill=hover_fill))
    canvas.tag_bind(tag, "<Leave>", lambda _event: canvas.itemconfigure(bg_tag, fill=fill))


def draw_quick_icon_button(
    canvas: tk.Canvas,
    x: int,
    y: int,
    width: int,
    height: int,
    icon_name: str,
    command,
    tag: str,
    fill: str,
    hover_fill: str,
    outline: str,
    text_color: str = config.QUICK_HISTORY_TEXT,
    icon_size: int = 18,
    radius: int = 9,
) -> None:
    bg_tag = f"{tag}-bg"
    draw_round_rect(
        canvas,
        x,
        y,
        x + width,
        y + height,
        radius=radius,
        fill=fill,
        outline=outline,
        width=1,
        tags=(tag, bg_tag),
    )

    icon_x = x + width // 2
    icon_y = y + height // 2
    rendered = False
    if icons.PIL_AVAILABLE:
        try:
            photo = glyph_photo(icon_name, text_color, icon_size)
            canvas.create_image(icon_x, icon_y, image=photo, tags=(tag,))
            if not hasattr(canvas, "_glyph_photos"):
                canvas._glyph_photos = []
            canvas._glyph_photos.append(photo)
            rendered = True
        except Exception as exc:
            log_exception("Quick action glyph render failed; using vector", exc)

    if not rendered:
        _draw_footer_icon_vector(canvas, icon_name, icon_x, icon_y, text_color, tag)

    canvas.tag_bind(tag, "<Button-1>", lambda _event: command())
    canvas.tag_bind(tag, "<Enter>", lambda _event: canvas.itemconfigure(bg_tag, fill=hover_fill))
    canvas.tag_bind(tag, "<Leave>", lambda _event: canvas.itemconfigure(bg_tag, fill=fill))


def draw_quick_text_button(
    canvas: tk.Canvas,
    x: int,
    y: int,
    text: str,
    command,
    tag: str,
    text_color: str = config.QUICK_HISTORY_TEXT,
) -> None:
    canvas.create_text(
        x,
        y,
        anchor="nw",
        fill=text_color,
        font=(config.BUBBLE_FONT_FAMILY, 12),
        text=text,
        tags=(tag,),
    )
    canvas.tag_bind(tag, "<Button-1>", lambda _event: command())
    canvas.tag_bind(tag, "<Enter>", lambda _event: canvas.configure(cursor="hand2"))
    canvas.tag_bind(tag, "<Leave>", lambda _event: canvas.configure(cursor=""))


def _draw_footer_icon_vector(canvas, icon, icon_x, icon_center_y, text_color, tag) -> None:
    if icon == "history":
        canvas.create_oval(icon_x - 10, icon_center_y - 10, icon_x + 10, icon_center_y + 10,
                           outline=text_color, width=1, tags=(tag,))
        canvas.create_line(icon_x, icon_center_y, icon_x, icon_center_y - 6, fill=text_color, width=1, tags=(tag,))
        canvas.create_line(icon_x, icon_center_y, icon_x + 5, icon_center_y + 4, fill=text_color, width=1, tags=(tag,))
        canvas.create_line(icon_x - 14, icon_center_y - 2, icon_x - 9, icon_center_y - 7, fill=text_color, width=1, tags=(tag,))
    elif icon == "settings":
        canvas.create_oval(icon_x - 9, icon_center_y - 9, icon_x + 9, icon_center_y + 9, outline=text_color, width=1, tags=(tag,))
        canvas.create_oval(icon_x - 3, icon_center_y - 3, icon_x + 3, icon_center_y + 3, outline=text_color, width=1, tags=(tag,))
        for angle_index in range(6):
            angle = angle_index * (math.pi / 3.0)
            canvas.create_line(
                icon_x + int(9 * math.cos(angle)), icon_center_y + int(9 * math.sin(angle)),
                icon_x + int(12 * math.cos(angle)), icon_center_y + int(12 * math.sin(angle)),
                fill=text_color, width=1, tags=(tag,))
    elif icon == "close":
        canvas.create_line(icon_x - 8, icon_center_y - 8, icon_x + 8, icon_center_y + 8, fill=text_color, width=2, capstyle="round", tags=(tag,))
        canvas.create_line(icon_x + 8, icon_center_y - 8, icon_x - 8, icon_center_y + 8, fill=text_color, width=2, capstyle="round", tags=(tag,))
    elif icon == "copy":
        canvas.create_rectangle(icon_x - 5, icon_center_y - 8, icon_x + 7, icon_center_y + 4,
                                outline=text_color, width=1, tags=(tag,))
        canvas.create_rectangle(icon_x - 8, icon_center_y - 4, icon_x + 4, icon_center_y + 8,
                                outline=text_color, width=1, tags=(tag,))
    elif icon == "tray":
        canvas.create_line(icon_x, icon_center_y - 8, icon_x, icon_center_y + 2,
                           fill=text_color, width=1, capstyle="round", tags=(tag,))
        canvas.create_line(icon_x - 5, icon_center_y - 2, icon_x, icon_center_y + 3,
                           fill=text_color, width=1, capstyle="round", tags=(tag,))
        canvas.create_line(icon_x + 5, icon_center_y - 2, icon_x, icon_center_y + 3,
                           fill=text_color, width=1, capstyle="round", tags=(tag,))
        canvas.create_rectangle(icon_x - 8, icon_center_y + 6, icon_x + 8, icon_center_y + 10,
                                outline=text_color, width=1, tags=(tag,))


def draw_quick_footer_button(
    canvas: tk.Canvas,
    icon_x: int,
    text_x: int,
    y: int,
    text: str,
    command,
    tag: str,
    icon: str,
    text_color: str = config.QUICK_HISTORY_TEXT,
    icon_size: int = 22,
    font_size: int = 12,
) -> None:
    icon_center_y = y + 13

    rendered = False
    if icons.PIL_AVAILABLE:
        try:
            photo = glyph_photo(icon, text_color, icon_size)
            canvas.create_image(icon_x, icon_center_y, image=photo, tags=(tag,))
            if not hasattr(canvas, "_glyph_photos"):
                canvas._glyph_photos = []
            canvas._glyph_photos.append(photo)
            rendered = True
        except Exception as exc:
            log_exception("Footer glyph render failed; using vector", exc)

    if not rendered:
        _draw_footer_icon_vector(canvas, icon, icon_x, icon_center_y, text_color, tag)

    canvas.create_text(
        text_x,
        y,
        anchor="nw",
        fill=text_color,
        font=(config.BUBBLE_FONT_FAMILY, font_size),
        text=text,
        tags=(tag,),
    )
    canvas.tag_bind(tag, "<Button-1>", lambda _event: command())
    canvas.tag_bind(tag, "<Enter>", lambda _event: canvas.configure(cursor="hand2"))
    canvas.tag_bind(tag, "<Leave>", lambda _event: canvas.configure(cursor=""))


def bind_quick_popover_close_events(popover) -> None:
    popover.bind("<Escape>", lambda _event: close_quick_history_popover())


def quick_popover_geometry(width: int, height: int) -> str:
    if root is None:
        return f"{width}x{height}+80+260"

    bubble_x = root.winfo_x()
    bubble_y = root.winfo_y()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    layout = quick_history_layout(width=width, height=height)

    bubble_center_x = bubble_x + active_hit_target_size // 2
    x = bubble_center_x - layout["pointer_tip_x"]
    y = bubble_y - height - layout["bubble_gap"]

    x = max(8, min(x, screen_width - width - 8))
    y = max(8, min(y, screen_height - height - 8))

    return f"{width}x{height}+{x}+{y}"


def show_full_history_from_quick_popover() -> None:
    close_quick_history_popover()
    show_history_panel()


def copy_quick_history_text(text: str) -> None:
    copy_history_text(text)
    close_quick_history_popover()


def paste_quick_history_text(text: str) -> None:
    close_quick_history_popover()

    if root is not None:
        root.after(80, lambda value=text: paste_history_text(value))
    else:
        paste_history_text(text)


def hide_to_tray_from_quick_popover() -> None:
    close_quick_history_popover()
    hide_bubble_window()


def should_ignore_quick_history_request(now: Optional[float] = None) -> bool:
    global last_quick_history_request_at

    current_time = time.monotonic() if now is None else now

    if current_time - last_quick_history_request_at < config.QUICK_HISTORY_DEBOUNCE_SECONDS:
        return True

    last_quick_history_request_at = current_time
    return False


def quick_history_layout(
    width: int = config.QUICK_HISTORY_WIDTH,
    height: int = config.QUICK_HISTORY_HEIGHT,
    pointer: int = config.QUICK_HISTORY_POINTER_SIZE,
) -> dict:
    panel_pad = 8
    panel_top = 8
    panel_bottom = height - pointer
    footer_y = panel_bottom - 35
    pointer_tip_x = width - 22
    tail_half_width = 6
    tail_curve_radius = 3
    pointer_base_left = pointer_tip_x - tail_half_width
    pointer_base_right = min(pointer_tip_x + tail_half_width, width - panel_pad)
    copy_x = width - 56
    text_x = 28
    first_divider = int(width * 0.275)
    second_divider = int(width * 0.50)
    third_divider = int(width * 0.725)

    return {
        "panel_top": panel_top,
        "panel_bottom": panel_bottom,
        "panel_pad": panel_pad,
        "panel_radius": 13,
        "row_top": 22,
        "row_height": 63,
        "text_x": text_x,
        "time_y_offset": 0,
        "transcript_y_offset": 17,
        "transcript_line_gap": 15,
        "transcript_width": copy_x - text_x - 19,
        "preview_line_chars": 34,
        "preview_max_lines": 2,
        "time_font_size": 10,
        "transcript_font_size": 12,
        "button_y_offset": 10,
        "button_width": 34,
        "button_height": 30,
        "button_radius": 7,
        "copy_x": copy_x,
        "copy_icon_x": copy_x + 17,
        "copy_icon_size": 15,
        "row_separator_offset": 58,
        "footer_y": footer_y,
        "bubble_gap": 2,
        "footer_font_size": 10,
        "footer_icon_size": 14,
        "footer_separator_y": footer_y - 15,
        "line_end": width - 20,
        "settings_icon_x": 27,
        "settings_x": 44,
        "footer_divider_x": first_divider,
        "history_icon_x": first_divider + 24,
        "history_x": first_divider + 42,
        "footer_divider2_x": second_divider,
        "tray_icon_x": second_divider + 24,
        "tray_x": second_divider + 42,
        "footer_divider3_x": third_divider,
        "close_icon_x": third_divider + 24,
        "close_x": third_divider + 42,
        "footer_actions": ["Settings", "History", "Tray", "Close app"],
        "pointer_tip_x": pointer_tip_x,
        "pointer_tip_y": height - 4,
        "pointer_tip_y_offset": height - 4 - panel_bottom,
        "pointer_base_left": pointer_base_left,
        "pointer_base_right": pointer_base_right,
        "pointer_smooth": True,
        "tail_renderer": "pillow",
        "tail_shape": "soft-rounded",
        "tail_curve_radius": tail_curve_radius,
    }


def render_quick_popover_background(
    width: int,
    height: int,
    layout: dict,
    palette: dict,
):
    from PIL import Image, ImageDraw

    scale = 3
    image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def sx(value: int) -> int:
        return int(value * scale)

    panel_box = [
        sx(layout["panel_pad"]),
        sx(layout["panel_top"]),
        sx(width - layout["panel_pad"]),
        sx(layout["panel_bottom"]),
    ]
    radius = sx(layout["panel_radius"])

    draw.rounded_rectangle(
        panel_box,
        radius=radius,
        fill=palette["panel_bg"],
        outline=palette["panel_border"],
        width=sx(1),
    )
    draw.rounded_rectangle(
        [
            panel_box[0] + sx(1),
            panel_box[1] + sx(1),
            panel_box[2] - sx(1),
            panel_box[3] - sx(1),
        ],
        radius=max(1, radius - sx(1)),
        outline=palette["inner_border"],
        width=sx(1),
    )

    tail_curve_radius = int(layout.get("tail_curve_radius", 3))
    tail_points = [
        (sx(layout["pointer_base_left"]), sx(layout["panel_bottom"] - 1)),
        (sx(layout["pointer_base_left"] + tail_curve_radius), sx(layout["panel_bottom"] + 1)),
        (sx(layout["pointer_tip_x"] - 1), sx(layout["pointer_tip_y"] - 1)),
        (sx(layout["pointer_tip_x"]), sx(layout["pointer_tip_y"])),
        (sx(layout["pointer_tip_x"] + 1), sx(layout["pointer_tip_y"] - 1)),
        (sx(layout["pointer_base_right"] - tail_curve_radius), sx(layout["panel_bottom"] + 1)),
        (sx(layout["pointer_base_right"]), sx(layout["panel_bottom"] - 1)),
    ]
    draw.polygon(tail_points, fill=palette["panel_bg"])
    draw.line(tail_points, fill=palette["panel_border"], width=sx(1), joint="curve")

    return image.resize((width, height), Image.Resampling.LANCZOS)


def show_quick_history_popover(event=None):
    global quick_history_popover

    if root is None:
        return "break"

    if should_ignore_quick_history_request():
        log("Quick history duplicate request ignored.")
        return "break"

    log("Quick history requested.")

    if quick_history_popover is not None and quick_history_popover.winfo_exists():
        close_quick_history_popover()
        return "break"

    width = config.QUICK_HISTORY_WIDTH
    height = config.QUICK_HISTORY_HEIGHT
    pointer = config.QUICK_HISTORY_POINTER_SIZE
    layout = quick_history_layout(width=width, height=height, pointer=pointer)
    transparent_bg = "#010203"
    palette = current_palette()

    popover = tk.Toplevel(root)
    quick_history_popover = popover
    popover.overrideredirect(True)
    popover.attributes("-topmost", True)
    popover.geometry(quick_popover_geometry(width, height))
    popover.configure(bg=transparent_bg)

    try:
        popover.attributes("-transparentcolor", transparent_bg)
        popover.attributes("-alpha", current_alpha())
    except tk.TclError:
        popover.configure(bg=palette["panel_bg"])

    canvas = tk.Canvas(
        popover,
        width=width,
        height=height,
        bg=transparent_bg,
        highlightthickness=0,
        bd=0,
    )
    canvas.place(x=0, y=0, width=width, height=height)

    if icons.PIL_AVAILABLE:
        from PIL import ImageTk

        background = render_quick_popover_background(width, height, layout, palette)
        background_photo = ImageTk.PhotoImage(background)
        canvas.background_photo = background_photo
        canvas.create_image(0, 0, anchor="nw", image=background_photo)
    else:
        draw_round_rect(
            canvas,
            layout["panel_pad"],
            layout["panel_top"],
            width - layout["panel_pad"],
            layout["panel_bottom"],
            radius=layout["panel_radius"],
            fill=palette["panel_bg"],
            outline=palette["panel_border"],
            width=1,
        )

    items = quick_history_items_for_display(limit=config.QUICK_HISTORY_LIMIT)
    transcript_font = tkfont.Font(
        family=config.BUBBLE_FONT_FAMILY,
        size=layout["transcript_font_size"],
    )

    if not items:
        canvas.create_text(
            layout["text_x"],
            layout["row_top"] + 28,
            anchor="nw",
            fill=palette["muted_text"],
            font=(config.BUBBLE_FONT_FAMILY, layout["transcript_font_size"]),
            text="No transcripts yet",
        )
    else:
        for index, item in enumerate(items):
            y = layout["row_top"] + index * layout["row_height"]
            canvas.create_text(
                layout["text_x"],
                y + layout["time_y_offset"],
                anchor="nw",
                fill=palette["muted_text"],
                font=(config.BUBBLE_FONT_FAMILY, layout["time_font_size"]),
                text=item.display_time,
            )
            preview_lines = wrap_text_to_pixel_lines(
                item.text,
                max_lines=layout["preview_max_lines"],
                max_width=layout["transcript_width"],
                measure=transcript_font.measure,
            )
            for line_index, line in enumerate(preview_lines):
                canvas.create_text(
                    layout["text_x"],
                    y + layout["transcript_y_offset"] + line_index * layout["transcript_line_gap"],
                    anchor="nw",
                    fill=palette["text"],
                    font=(config.BUBBLE_FONT_FAMILY, layout["transcript_font_size"]),
                    text=line,
                )

            draw_quick_icon_button(
                canvas,
                layout["copy_x"],
                y + layout["button_y_offset"],
                layout["button_width"],
                layout["button_height"],
                "copy",
                lambda value=item.text: copy_quick_history_text(value),
                f"quick-copy-{index}",
                fill=palette["button_bg"],
                hover_fill=palette["button_hover"],
                outline=palette["button_border"],
                text_color=palette["text"],
                icon_size=layout["copy_icon_size"],
                radius=layout["button_radius"],
            )

            if index < config.QUICK_HISTORY_LIMIT - 1:
                line_y = y + layout["row_separator_offset"]
                canvas.create_line(
                    layout["text_x"],
                    line_y,
                    layout["line_end"],
                    line_y,
                    fill=palette["separator"],
                )

    canvas.create_line(
        layout["text_x"],
        layout["footer_separator_y"],
        layout["line_end"],
        layout["footer_separator_y"],
        fill=palette["separator"],
    )

    draw_quick_footer_button(
        canvas,
        layout["settings_icon_x"],
        layout["settings_x"],
        layout["footer_y"] + 2,
        "Settings",
        show_settings_from_quick_popover,
        "quick-settings",
        "settings",
        text_color=palette["text"],
        icon_size=layout["footer_icon_size"],
        font_size=layout["footer_font_size"],
    )

    canvas.create_line(
        layout["footer_divider_x"],
        layout["footer_y"] - 6,
        layout["footer_divider_x"],
        layout["footer_y"] + 30,
        fill=palette["separator"],
    )

    draw_quick_footer_button(
        canvas,
        layout["history_icon_x"],
        layout["history_x"],
        layout["footer_y"] + 2,
        "History",
        show_full_history_from_quick_popover,
        "quick-history",
        "history",
        text_color=palette["text"],
        icon_size=layout["footer_icon_size"],
        font_size=layout["footer_font_size"],
    )

    canvas.create_line(
        layout["footer_divider2_x"],
        layout["footer_y"] - 6,
        layout["footer_divider2_x"],
        layout["footer_y"] + 30,
        fill=palette["separator"],
    )

    draw_quick_footer_button(
        canvas,
        layout["tray_icon_x"],
        layout["tray_x"],
        layout["footer_y"] + 2,
        "Tray",
        hide_to_tray_from_quick_popover,
        "quick-tray",
        "tray",
        text_color=palette["text"],
        icon_size=layout["footer_icon_size"],
        font_size=layout["footer_font_size"],
    )

    canvas.create_line(
        layout["footer_divider3_x"],
        layout["footer_y"] - 6,
        layout["footer_divider3_x"],
        layout["footer_y"] + 30,
        fill=palette["separator"],
    )

    draw_quick_footer_button(
        canvas,
        layout["close_icon_x"],
        layout["close_x"],
        layout["footer_y"] + 2,
        "Close app",
        quit_app,
        "quick-close",
        "close",
        text_color=palette["text"],
        icon_size=layout["footer_icon_size"],
        font_size=layout["footer_font_size"],
    )

    bind_quick_popover_close_events(popover)
    popover.focus_force()
    return "break"


# ---------------------------------------------------------------------
# Settings panel
# ---------------------------------------------------------------------

def show_settings_from_quick_popover() -> None:
    close_quick_history_popover()
    show_settings_panel()


def settings_panel_geometry(width: int, height: int) -> str:
    if root is None:
        return f"{width}x{height}+120+160"

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = max(8, min(root.winfo_x() + 50, screen_w - width - 8))
    y = max(8, min(root.winfo_y(), screen_h - height - 8))
    return f"{width}x{height}+{x}+{y}"


def bind_panel_drag(window, handle) -> None:
    state = {"x": 0, "y": 0}

    def press(event):
        state["x"] = event.x
        state["y"] = event.y

    def drag(event):
        new_x = window.winfo_x() + event.x - state["x"]
        new_y = window.winfo_y() + event.y - state["y"]
        window.geometry(f"+{new_x}+{new_y}")

    def bind_tree(widget) -> None:
        if isinstance(widget, tk.Button):
            return

        widget.bind("<ButtonPress-1>", press)
        widget.bind("<B1-Motion>", drag)

        for child in widget.winfo_children():
            bind_tree(child)

    bind_tree(handle)


def apply_dark_combobox_style(style, palette) -> None:
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(
        "Settings.TCombobox",
        fieldbackground=palette["field_bg"],
        background=palette["button_bg"],
        foreground=palette["text"],
        arrowcolor=palette["text"],
        bordercolor=palette["inner_border"],
        lightcolor=palette["field_bg"],
        darkcolor=palette["field_bg"],
        relief="flat",
        padding=(10, 4),
    )
    style.map(
        "Settings.TCombobox",
        fieldbackground=[("readonly", palette["field_bg"])],
        foreground=[("readonly", palette["text"])],
        background=[("active", palette["button_hover"])],
        bordercolor=[("focus", palette["accent"])],
    )
    style.configure(
        "Settings.Horizontal.TScale",
        background=palette["row_bg"],
        troughcolor=palette["field_bg"],
        bordercolor=palette["row_bg"],
        lightcolor=palette["row_bg"],
        darkcolor=palette["row_bg"],
    )

    try:
        style.master.option_add("*TCombobox*Listbox.background", palette["field_bg"])
        style.master.option_add("*TCombobox*Listbox.foreground", palette["text"])
        style.master.option_add("*TCombobox*Listbox.selectBackground", palette["button_hover"])
        style.master.option_add("*TCombobox*Listbox.selectForeground", palette["text"])
    except tk.TclError:
        pass


def pick_save_location(save_var) -> None:
    from tkinter import filedialog

    chosen = filedialog.askdirectory(title="Choose export folder")
    if chosen:
        save_var.set(chosen)


def show_info_tip(text: str) -> None:
    from tkinter import messagebox

    messagebox.showinfo("Model tiers", text)


def settings_visual_palette(base_palette: dict) -> dict:
    resolved = settings.resolve_theme(SETTINGS["theme"])

    if resolved == "Light Mode":
        overrides = {
            "panel_bg": "#f8f7f3",
            "panel_border": "#d3cabc",
            "inner_border": "#eee8dc",
            "separator": "#e4ded2",
            "text": "#16191d",
            "muted_text": "#66706d",
            "button_bg": "#f0ece3",
            "button_border": "#d8d0c3",
            "button_hover": "#e7e1d6",
            "field_bg": "#ffffff",
            "row_bg": "#fbfaf6",
            "row_ring": "#e4ded2",
            "row_inner": "#f6f2eb",
            "accent": "#2f9b88",
            "accent_bg": "#1f7f70",
            "accent_hover": "#176b5f",
            "accent_text": "#ffffff",
            "footer_bg": "#f7f3ec",
            "help_bg": "#f3eee5",
        }
    else:
        overrides = {
            "panel_bg": "#080b10",
            "panel_border": "#2b3544",
            "inner_border": "#1c2632",
            "separator": "#16202b",
            "text": "#f7f9fc",
            "muted_text": "#9aa5b5",
            "button_bg": "#0f151f",
            "button_border": "#303b4a",
            "button_hover": "#182231",
            "field_bg": "#070b11",
            "row_bg": "#0b1017",
            "row_ring": "#1b2531",
            "row_inner": "#0a0f16",
            "accent": "#8ee6ba",
            "accent_bg": "#14271f",
            "accent_hover": "#1b372b",
            "accent_text": "#f4fff9",
            "footer_bg": "#090e15",
            "help_bg": "#0c121b",
        }

    enriched = dict(base_palette)
    enriched.update(overrides)
    return enriched


def settings_panel_layout() -> dict:
    return {
        "width": 620,
        "height": 630,
        "outer_pad_x": 12,
        "header_pad_x": 22,
        "section_pad_x": 12,
        "section_gap": 9,
        "minimum_font_size": 8,
        "label_width": 15,
        "control_width": 24,
        "control_alignment": "left",
        "control_start_x": 190,
        "model_info_reserved_lines": 2,
        "model_info_font_size": 8,
        "model_folder_label_width": 15,
        "model_folder_font_size": 8,
        "model_order_label_width": 15,
        "manual_model_font_size": 8,
        "hotkey_help_font_size": 8,
        "commands_min_height": 116,
        "help_wraplength": 500,
        "help_reserved_lines": 2,
        "help_text": "Click bubble anytime. Hotkey: <ctrl>+<alt>+d. Leave blank to disable.",
        "close_button_size": 24,
        "sections": ["Transcription", "Interface & Output", "Commands & Hotkeys"],
        "footer_actions": ["History", "Export", "Close app", "Save changes"],
        "primary_action": "Save changes",
    }


def redraw_bubble_current_state() -> None:
    close_quick_history_popover()

    with state_lock:
        is_recording = recording
        is_transcribing = transcribing
        is_waiting = waiting_for_target_click

    if is_recording:
        set_bubble(config.RECORDING_LABEL, config.RECORDING_BG)
    elif is_transcribing:
        set_bubble(config.TRANSCRIBING_LABEL, config.TRANSCRIBING_BG)
    elif is_waiting:
        set_bubble(config.PASTE_READY_LABEL, config.PASTE_READY_BG)
    else:
        set_bubble(config.READY_LABEL, config.READY_BG)


def model_download_button_state(
    model_choice: str,
    *,
    cache_root: Optional[Path] = None,
    custom_models: Optional[Sequence[dict]] = None,
) -> dict:
    details = settings.model_tier_details(
        model_choice,
        cache_root=cache_root,
        custom_models=custom_models,
    )
    can_download = bool(details["repo_id"])
    if details["available"]:
        return {"visible": can_download, "enabled": False, "text": "Installed"}
    return {"visible": can_download, "enabled": can_download, "text": "Download"}


def download_model_for_choice(model_choice: str, **kwargs):
    with model_download_status_lock:
        admission = model_download_locks.setdefault(model_choice, threading.Lock())
    if not admission.acquire(blocking=False):
        raise ValueError("This model is already downloading.")
    set_model_download_status(model_choice, 'downloading')
    try:
        result = _download_model_for_choice(model_choice, **kwargs)
        set_model_download_status(model_choice, 'idle')
        return result
    except Exception as exc:
        set_model_download_status(model_choice, 'error', str(exc))
        raise
    finally:
        admission.release()


def _download_model_for_choice(
    model_choice: str,
    *,
    custom_models: Optional[Sequence[dict]] = None,
    download_model_func=None,
    snapshot_download_func=None,
):
    details = settings.model_tier_details(
        model_choice,
        custom_models=custom_models,
    )
    if not details["repo_id"]:
        raise ValueError("Only Hugging Face model repos can be downloaded.")

    cache_dir = str(config.MODEL_DOWNLOAD_ROOT) if config.MODEL_DOWNLOAD_ROOT else None
    allow_patterns = [
        "config.json",
        "preprocessor_config.json",
        "model.bin",
        "tokenizer.json",
        "vocabulary.*",
    ]

    if details["custom"]:
        if snapshot_download_func is None:
            from huggingface_hub import snapshot_download as snapshot_download_func

        kwargs = {
            "repo_id": details["repo_id"],
            "repo_type": "model",
            "allow_patterns": allow_patterns,
            "local_files_only": False,
        }
        if cache_dir is not None:
            kwargs["cache_dir"] = cache_dir
        return snapshot_download_func(**kwargs)

    if download_model_func is None:
        from faster_whisper.utils import download_model as download_model_func

    kwargs = {
        "local_files_only": False,
    }
    if cache_dir is not None:
        kwargs["cache_dir"] = cache_dir
    return download_model_func(details["model_name"], **kwargs)


def copy_model_cache_path() -> None:
    path = str(settings.huggingface_cache_root())
    pyperclip.copy(path)
    log("Model cache path copied.")


def open_model_cache_folder() -> None:
    path = settings.huggingface_cache_root()
    try:
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))
    except Exception as exc:
        log_exception("Could not open model cache folder", exc)


def add_custom_model_dialog() -> None:
    from tkinter import messagebox, simpledialog

    name = simpledialog.askstring("Add custom model", "Display name:")
    if not name:
        return
    source = simpledialog.askstring(
        "Add custom model",
        "Hugging Face repo ID or local faster-whisper model folder:",
    )
    if not source:
        return

    candidate = [{"name": name, "source": source}]
    normalized = settings.normalize_custom_models(
        list(SETTINGS.get("custom_models", [])) + candidate
    )
    if len(normalized) == len(SETTINGS.get("custom_models", [])):
        messagebox.showerror(
            "Custom model",
            "Use a unique name and a valid Hugging Face repo ID or faster-whisper model folder.",
        )
        return

    control_set_settings({'settings': {'custom_models': normalized}})
    refresh_settings_panel()


def start_model_download_from_settings(model_var, download_button, model_info_var) -> None:
    model_choice = model_var.get()
    download_button.configure(text="Downloading...", state="disabled")
    model_info_var.set(f"Downloading {model_choice}...")

    def worker() -> None:
        try:
            download_model_for_choice(
                model_choice,
                custom_models=SETTINGS.get("custom_models"),
            )
        except Exception as exc:
            log_exception("Model download failed", exc)

            def fail() -> None:
                model_info_var.set(f"Download failed: {model_choice}")
                state = model_download_button_state(
                    model_choice,
                    custom_models=SETTINGS.get("custom_models"),
                )
                download_button.configure(text=state["text"], state="normal" if state["enabled"] else "disabled")

            if root is not None:
                root.after(0, fail)
            return

        log(f"Model downloaded: {model_choice}")

        def succeed() -> None:
            model_info_var.set(
                settings.model_tier_summary(
                    model_choice,
                    custom_models=SETTINGS.get("custom_models"),
                    include_revision=False,
                )
            )
            state = model_download_button_state(
                model_choice,
                custom_models=SETTINGS.get("custom_models"),
            )
            download_button.configure(text=state["text"], state="normal" if state["enabled"] else "disabled")

        if root is not None:
            root.after(0, succeed)

    threading.Thread(target=worker, daemon=True).start()


def build_settings_form(parent, palette) -> dict:
    layout = settings_panel_layout()
    section_font = (config.BUBBLE_FONT_FAMILY, 10, "bold")
    label_font = (config.BUBBLE_FONT_FAMILY, 8)
    control_font = (config.BUBBLE_FONT_FAMILY, 8)
    hint_font = (config.BUBBLE_FONT_FAMILY, 8)

    def section_card(title, icon_name):
        shell = tk.Frame(parent, bg=palette["row_ring"])
        shell.pack(fill="x", pady=(0, layout["section_gap"]))
        card = tk.Frame(shell, bg=palette["row_bg"])
        card.pack(fill="x", padx=1, pady=1)

        header = tk.Frame(card, bg=palette["row_bg"])
        header.pack(fill="x", padx=layout["section_pad_x"], pady=(7, 5))
        if icons.PIL_AVAILABLE:
            try:
                photo = glyph_photo(icon_name, palette["muted_text"], 13)
                icon = tk.Label(header, image=photo, bg=palette["row_bg"])
                icon.image = photo
                icon.pack(side="left", padx=(0, 9))
            except Exception as exc:
                log_exception("Settings section glyph failed", exc)
        tk.Label(
            header,
            text=title,
            bg=palette["row_bg"],
            fg=palette["text"],
            font=section_font,
            anchor="w",
        ).pack(side="left")
        tk.Frame(card, bg=palette["separator"], height=1).pack(
            fill="x", padx=layout["section_pad_x"]
        )
        return card

    def row(card, label_text):
        frame = tk.Frame(card, bg=palette["row_bg"])
        frame.pack(fill="x", padx=layout["section_pad_x"], pady=3)
        tk.Label(
            frame,
            text=label_text,
            bg=palette["row_bg"],
            fg=palette["text"],
            font=label_font,
            width=layout["label_width"],
            anchor="w",
        ).pack(side="left")
        controls = tk.Frame(frame, bg=palette["row_bg"])
        controls.pack(side="left", padx=(14, 0))
        return controls

    def row_separator(card):
        tk.Frame(card, bg=palette["separator"], height=1).pack(
            fill="x", padx=layout["section_pad_x"]
        )

    def combo(parent_row, variable, values, width=20):
        return ttk.Combobox(
            parent_row,
            textvariable=variable,
            values=values,
            state="readonly",
            width=width,
            style="Settings.TCombobox",
            font=control_font,
        )

    def entry(parent_row, variable, width=20):
        return tk.Entry(
            parent_row,
            textvariable=variable,
            width=width,
            bg=palette["field_bg"],
            fg=palette["text"],
            insertbackground=palette["text"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=palette["inner_border"],
            highlightcolor=palette["accent"],
            font=control_font,
        )

    def small_button(parent_row, text, command):
        return tk.Button(
            parent_row,
            text=text,
            bd=0,
            relief="flat",
            bg=palette["button_bg"],
            fg=palette["text"],
            activebackground=palette["button_hover"],
            activeforeground=palette["text"],
            cursor="hand2",
            padx=9,
            pady=4,
            font=(config.BUBBLE_FONT_FAMILY, 8),
            command=command,
        )

    language_var = tk.StringVar(value=SETTINGS["language"])
    model_var = tk.StringVar(value=SETTINGS["model"])
    model_order_var = tk.StringVar(
        value=SETTINGS.get("model_order", settings.DEFAULT_SETTINGS["model_order"])
    )
    model_display_var = tk.StringVar(
        value=settings.model_dropdown_label(
            SETTINGS["model"],
            custom_models=SETTINGS.get("custom_models"),
        )
    )
    theme_var = tk.StringVar(value=SETTINGS["theme"])
    # DoubleVar: ttk.Scale writes floats; validate_settings coerces to int on save.
    opacity_var = tk.DoubleVar(value=SETTINGS["opacity"])
    opacity_display_var = tk.StringVar(value=f"{int(opacity_var.get())}%")
    format_var = tk.StringVar(value=SETTINGS["text_format"])
    save_var = tk.StringVar(value=SETTINGS["save_location"])
    hotkey_var = tk.StringVar(value=SETTINGS["hotkey"])
    model_info_var = tk.StringVar(
        value=settings.model_tier_summary(
            model_var.get(),
            custom_models=SETTINGS.get("custom_models"),
            include_revision=False,
        )
    )

    def update_opacity_display(*_args):
        try:
            opacity_display_var.set(f"{int(float(opacity_var.get()))}%")
        except (tk.TclError, ValueError):
            opacity_display_var.set("")

    opacity_var.trace_add("write", update_opacity_display)
    transcription = section_card("Transcription", "wave")
    r = row(transcription, "Input Language")
    combo(r, language_var, settings.LANGUAGE_CHOICES).pack(side="left")
    row_separator(transcription)
    r = row(transcription, "Model")
    model_combo = combo(
        r,
        model_display_var,
        settings.model_dropdown_options(
            SETTINGS.get("custom_models"),
            order=model_order_var.get(),
        ),
        width=34,
    )
    model_combo.pack(side="left")
    small_button(
        r,
        "Info",
        lambda: show_info_tip(settings.model_tier_info_text(custom_models=SETTINGS.get("custom_models"))),
    ).pack(side="left", padx=(8, 0))
    download_button = small_button(
        r,
        "Download",
        lambda: start_model_download_from_settings(model_var, download_button, model_info_var),
    )
    download_button.pack(side="left", padx=(8, 0))
    small_button(r, "Add custom", add_custom_model_dialog).pack(side="left", padx=(8, 0))

    def refresh_model_dropdown_values() -> None:
        values = settings.model_dropdown_options(
            SETTINGS.get("custom_models"),
            order=model_order_var.get(),
        )
        model_combo.configure(values=values)
        model_display_var.set(
            settings.model_dropdown_label(
                model_var.get(),
                custom_models=SETTINGS.get("custom_models"),
            )
        )

    def update_model_choice_from_display(*_args) -> None:
        model_var.set(
            settings.model_choice_from_dropdown_label(
                model_display_var.get(),
                custom_models=SETTINGS.get("custom_models"),
                order=model_order_var.get(),
            )
        )

    def update_model_controls(*_args):
        model_info_var.set(
            settings.model_tier_summary(
                model_var.get(),
                custom_models=SETTINGS.get("custom_models"),
                include_revision=False,
            )
        )
        state = model_download_button_state(
            model_var.get(),
            custom_models=SETTINGS.get("custom_models"),
        )
        download_button.configure(
            text=state["text"],
            state="normal" if state["enabled"] else "disabled",
        )

    model_display_var.trace_add("write", update_model_choice_from_display)
    model_var.trace_add("write", update_model_controls)
    model_order_var.trace_add("write", lambda *_args: refresh_model_dropdown_values())
    update_model_controls()
    tk.Label(
        transcription,
        textvariable=model_info_var,
        bg=palette["row_bg"],
        fg=palette["muted_text"],
        font=(config.BUBBLE_FONT_FAMILY, layout["model_info_font_size"]),
        wraplength=layout["help_wraplength"],
        justify="left",
        anchor="w",
    ).pack(fill="x", padx=layout["section_pad_x"], pady=(0, 7))
    row_separator(transcription)
    r = row(transcription, "Model Order")
    combo(r, model_order_var, settings.MODEL_ORDER_CHOICES, width=14).pack(side="left")
    row_separator(transcription)
    r = row(transcription, "Model folder")
    tk.Label(
        r,
        text=str(settings.huggingface_cache_root()),
        bg=palette["row_bg"],
        fg=palette["muted_text"],
        font=(config.BUBBLE_FONT_FAMILY, layout["model_folder_font_size"]),
        anchor="w",
    ).pack(side="left")
    small_button(r, "Open folder", open_model_cache_folder).pack(side="left", padx=(8, 0))
    small_button(r, "Copy path", copy_model_cache_path).pack(side="left", padx=(8, 0))
    tk.Label(
        transcription,
        text="Manual models: use a faster-whisper/CTranslate2 folder with config.json, model.bin, tokenizer.json, and vocabulary.*.",
        bg=palette["row_bg"],
        fg=palette["muted_text"],
        font=(config.BUBBLE_FONT_FAMILY, layout["manual_model_font_size"]),
        wraplength=layout["help_wraplength"],
        justify="left",
        anchor="w",
    ).pack(fill="x", padx=layout["section_pad_x"], pady=(0, 7))

    interface = section_card("Interface & Output", "monitor")
    r = row(interface, "App Theme")
    combo(r, theme_var, settings.THEME_CHOICES).pack(side="left")
    row_separator(interface)
    r = row(interface, "Panel Opacity")
    tk.Scale(
        r,
        from_=config.OPACITY_MIN,
        to=config.OPACITY_MAX,
        orient="horizontal",
        variable=opacity_var,
        length=156,
        bg=palette["row_bg"],
        fg=palette["text"],
        activebackground=palette["accent"],
        troughcolor=palette["button_border"],
        highlightthickness=0,
        bd=0,
        showvalue=False,
        sliderlength=16,
        width=9,
    ).pack(side="left", padx=(0, 8))
    tk.Label(
        r,
        textvariable=opacity_display_var,
        bg=palette["row_bg"],
        fg=palette["text"],
        font=control_font,
        padx=8,
        pady=3,
    ).pack(side="left")
    row_separator(interface)
    r = row(interface, "Text Format")
    combo(r, format_var, settings.FORMAT_CHOICES).pack(side="left")
    row_separator(interface)
    r = row(interface, "Save Location")
    entry(r, save_var, width=18).pack(side="left")
    small_button(r, "Browse", lambda: pick_save_location(save_var)).pack(side="left", padx=8)

    commands = section_card("Commands & Hotkeys", "keyboard")
    commands.configure(height=layout["commands_min_height"])
    commands.pack_propagate(False)
    r = row(commands, "Start/Stop Key")
    hotkey_entry = entry(r, hotkey_var, width=20)
    hotkey_entry.pack(side="left")
    bind_hotkey_capture(hotkey_entry, hotkey_var)
    tk.Label(
        commands,
        text=layout["help_text"],
        bg=palette["row_bg"],
        fg=palette["muted_text"],
        font=(config.BUBBLE_FONT_FAMILY, layout["hotkey_help_font_size"]),
        wraplength=layout["help_wraplength"],
        justify="left",
        anchor="w",
    ).pack(fill="x", padx=layout["section_pad_x"], pady=(1, 8))

    return {
        "language": language_var, "model": model_var, "theme": theme_var,
        "opacity": opacity_var, "text_format": format_var,
        "save_location": save_var, "hotkey": hotkey_var,
        "model_order": model_order_var,
    }


def build_settings_nav(parent, palette, vars_) -> None:
    layout = settings_panel_layout()
    shell = tk.Frame(parent, bg=palette["separator"], height=1)
    shell.pack(side="bottom", fill="x", pady=(4, 0))
    bar = tk.Frame(parent, bg=palette["footer_bg"])
    bar.pack(side="bottom", fill="x", padx=layout["outer_pad_x"], pady=(8, 10))

    def nav_button(container, text, command, icon_name, variant="secondary"):
        is_primary = variant == "primary"
        ring = tk.Frame(
            container,
            bg=palette["accent"] if is_primary else palette["button_border"],
        )
        button = tk.Button(
            ring, text=text, bd=0, relief="flat",
            bg=palette["accent_bg"] if is_primary else palette["button_bg"],
            fg=palette["accent_text"] if is_primary else palette["text"],
            activebackground=palette["accent_hover"] if is_primary else palette["button_hover"],
            activeforeground=palette["accent_text"] if is_primary else palette["text"],
            cursor="hand2",
            padx=10 if is_primary else 8,
            pady=6,
            font=(config.BUBBLE_FONT_FAMILY, 8),
            command=command,
        )
        if icons.PIL_AVAILABLE:
            try:
                icon_color = palette["accent_text"] if is_primary else palette["text"]
                photo = glyph_photo(icon_name, icon_color, 14)
                button.configure(image=photo, compound="left", padx=7)
                button.image = photo
            except Exception as exc:
                log_exception("Settings nav glyph failed", exc)
        button.pack(fill="both", expand=True, padx=1, pady=1)
        return ring

    left = tk.Frame(bar, bg=palette["footer_bg"])
    left.pack(side="left")
    right = tk.Frame(bar, bg=palette["footer_bg"])
    right.pack(side="right")

    nav_button(left, "History", show_history_panel, "history").pack(side="left")
    nav_button(left, "Export", export_all_history, "export").pack(side="left", padx=(8, 14))
    tk.Frame(left, bg=palette["separator"], width=1, height=26).pack(side="left", padx=(0, 14), pady=3)
    nav_button(left, "Close app", quit_app, "close").pack(side="left")
    nav_button(
        right,
        "Save changes",
        lambda: apply_settings_from_form(vars_),
        "save",
        "primary",
    ).pack(side="right")


def apply_settings_from_form(vars_) -> None:
    global SETTINGS

    previous_model = SETTINGS["model"]
    new_values = {key: var.get() for key, var in vars_.items()}
    new_values["bubble_position"] = SETTINGS.get("bubble_position")
    new_values["custom_models"] = SETTINGS.get("custom_models", [])
    new_values["device_mode"] = SETTINGS.get("device_mode", settings.DEFAULT_SETTINGS["device_mode"])

    requested_model = new_values.get("model", previous_model)
    if (
        config.LOCAL_FILES_ONLY
        and requested_model != previous_model
        and not settings.model_is_available_locally(
            requested_model,
            custom_models=new_values.get("custom_models"),
        )
    ):
        log(
            "Selected model is not cached locally; keeping current model: "
            f"{settings.model_tier_summary(requested_model)}"
        )
        new_values["model"] = previous_model
        model_var = vars_.get("model")
        if model_var is not None:
            try:
                model_var.set(previous_model)
            except Exception:
                pass

    patch = {key: value for key, value in new_values.items() if value != SETTINGS.get(key)}
    def save():
        try:
            control_set_settings({'settings': patch, 'recover': True})
        except Exception as exc:
            log_exception('Settings save failed', exc)
            if root is not None:
                root.after(0, lambda message=str(exc): show_startup_error(message))
    if patch.get('model', previous_model) != previous_model:
        threading.Thread(target=save, daemon=True).start()
    else:
        save()


def render_settings_panel(panel) -> None:
    for child in panel.winfo_children():
        child.destroy()

    palette = settings_visual_palette(current_palette())
    layout = settings_panel_layout()

    outer = tk.Frame(panel, bg=palette["panel_border"])
    outer.pack(fill="both", expand=True)
    body = tk.Frame(outer, bg=palette["panel_bg"])
    body.pack(fill="both", expand=True, padx=1, pady=1)

    style = ttk.Style(panel)
    apply_dark_combobox_style(style, palette)

    header = tk.Frame(body, bg=palette["panel_bg"])
    header.pack(fill="x", padx=layout["header_pad_x"], pady=(16, 10))
    title_stack = tk.Frame(header, bg=palette["panel_bg"])
    title_stack.pack(side="left", fill="x", expand=True)
    tk.Label(
        title_stack,
        text="Settings",
        bg=palette["panel_bg"],
        fg=palette["text"],
        font=(config.BUBBLE_FONT_FAMILY, 15, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        title_stack,
        text="Transcription, output, and shortcut controls",
        bg=palette["panel_bg"],
        fg=palette["muted_text"],
        font=(config.BUBBLE_FONT_FAMILY, 8),
        anchor="w",
    ).pack(fill="x", pady=(3, 0))

    close_shell = tk.Frame(
        header,
        bg=palette["button_border"],
        width=layout["close_button_size"],
        height=layout["close_button_size"],
    )
    close_shell.pack(side="right", padx=(14, 0))
    close_shell.pack_propagate(False)
    close_button = tk.Button(
        close_shell,
        text="x",
        bd=0,
        relief="flat",
        bg=palette["button_bg"],
        fg=palette["text"],
        activebackground=palette["button_hover"],
        activeforeground=palette["text"],
        cursor="hand2",
        padx=0,
        pady=0,
        font=(config.BUBBLE_FONT_FAMILY, 7),
        command=close_settings_panel,
    )
    if icons.PIL_AVAILABLE:
        try:
            photo = glyph_photo("close", palette["text"], 13)
            close_button.configure(image=photo, text="")
            close_button.image = photo
        except Exception as exc:
            log_exception("Settings close glyph failed", exc)
    close_button.pack(fill="both", expand=True, padx=1, pady=1)
    bind_panel_drag(panel, header)

    form = tk.Frame(body, bg=palette["panel_bg"])
    vars_ = build_settings_form(form, palette)
    build_settings_nav(body, palette, vars_)
    form.pack(fill="x", padx=layout["outer_pad_x"], pady=(0, 0))


def refresh_settings_panel() -> None:
    if settings_panel is not None and settings_panel.winfo_exists():
        render_settings_panel(settings_panel)
        try:
            settings_panel.attributes("-alpha", current_alpha())
        except tk.TclError:
            pass


def show_settings_panel() -> None:
    global settings_panel

    close_quick_history_popover()
    show_bubble_window()

    if root is None:
        return

    if settings_panel is not None and settings_panel.winfo_exists():
        settings_panel.lift()
        return

    layout = settings_panel_layout()
    width, height = layout["width"], layout["height"]

    panel = tk.Toplevel(root)
    settings_panel = panel
    panel.overrideredirect(True)
    panel.attributes("-topmost", True)
    panel.geometry(settings_panel_geometry(width, height))
    try:
        panel.attributes("-alpha", current_alpha())
    except tk.TclError:
        pass

    render_settings_panel(panel)
    panel.bind("<Escape>", lambda _e: close_settings_panel())
    panel.protocol("WM_DELETE_WINDOW", close_settings_panel)
    panel.focus_force()


def close_settings_panel() -> None:
    global settings_panel

    if settings_panel is not None and settings_panel.winfo_exists():
        settings_panel.destroy()

    settings_panel = None


# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------

def default_export_dir() -> Path:
    configured = SETTINGS.get("save_location") or ""
    if configured:
        return Path(configured)
    return Path.home() / "Documents"


def export_all_history() -> None:
    entries = list(reversed(load_transcript_history_entries()))  # newest first
    text_format = SETTINGS["text_format"]
    content = settings.format_history_export(entries, text_format)

    if not content:
        log("Export skipped: no history.")
        set_bubble(config.EMPTY_LABEL, config.EMPTY_BG)
        time.sleep(config.EMPTY_STATE_SECONDS)
        set_bubble(config.READY_LABEL, config.READY_BG)
        return

    export_dir = default_export_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = export_dir / f"dictation_export_{stamp}{settings.export_extension(text_format)}"

    try:
        export_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        log(f"Exported {len(entries)} transcripts -> {out_path}")
        set_bubble(config.PASTED_LABEL, config.PASTED_BG)
        time.sleep(config.PASTED_STATE_SECONDS)
        set_bubble(config.READY_LABEL, config.READY_BG)
    except OSError as exc:
        log_exception("Export failed", exc)
        set_bubble(config.ERROR_LABEL, config.ERROR_BG)
        time.sleep(config.ERROR_STATE_SECONDS)
        set_bubble(config.READY_LABEL, config.READY_BG)


# ---------------------------------------------------------------------
# Hotkey
# ---------------------------------------------------------------------

def normalize_hotkey(raw: str) -> str:
    return (raw or "").strip()


def hotkey_from_key_event(event) -> Optional[str]:
    keysym = getattr(event, "keysym", "") or ""
    char = getattr(event, "char", "") or ""

    if keysym in {"BackSpace", "Delete", "Escape"}:
        return ""
    if keysym in {
        "Control_L", "Control_R", "Alt_L", "Alt_R",
        "Shift_L", "Shift_R", "Meta_L", "Meta_R",
        "Win_L", "Win_R", "Super_L", "Super_R",
    }:
        return None

    special_keys = {
        "Return": "<enter>",
        "KP_Enter": "<enter>",
        "space": "<space>",
        "Tab": "<tab>",
        "Home": "<home>",
        "End": "<end>",
        "Prior": "<page_up>",
        "Next": "<page_down>",
        "Up": "<up>",
        "Down": "<down>",
        "Left": "<left>",
        "Right": "<right>",
    }

    if keysym in special_keys:
        key = special_keys[keysym]
    elif len(char) == 1 and char.strip():
        key = char.lower()
    elif len(keysym) == 1:
        key = keysym.lower()
    else:
        key = f"<{keysym.lower()}>"

    try:
        state = int(getattr(event, "state", 0) or 0)
    except (TypeError, ValueError):
        state = 0

    modifiers: List[str] = []
    if state & 0x0004:
        modifiers.append("<ctrl>")
    if state & 0x0008:
        modifiers.append("<alt>")
    if state & 0x0001:
        modifiers.append("<shift>")
    if state & 0x0040:
        modifiers.append('<cmd>')

    return "+".join([*modifiers, key])


def bind_hotkey_capture(entry_widget, hotkey_var) -> None:
    def capture(event):
        if getattr(event, 'keysym', '') in {'Tab', 'ISO_Left_Tab'}:
            return None
        value = hotkey_from_key_event(event)
        if value is not None:
            hotkey_var.set(value)
        return "break"

    entry_widget.bind("<KeyPress>", capture)


def is_valid_hotkey(raw: str) -> bool:
    candidate = normalize_hotkey(raw)
    if not candidate:
        return False
    try:
        keyboard.HotKey.parse(candidate)
        return True
    except ValueError:
        return False


def on_hotkey_toggle() -> None:
    if shutting_down or root is None:
        return
    root.after(0, toggle_recording_from_shortcut)


def start_hotkey_listener(raw: str, *, strict: bool = False):
    candidate = normalize_hotkey(raw)
    if not is_valid_hotkey(candidate):
        if candidate:
            log(f"Hotkey invalid; ignoring: {candidate}")
        return None
    try:
        listener = keyboard.GlobalHotKeys({candidate: on_hotkey_toggle})
        listener.start()
        log(f"Global hotkey active: {candidate}")
        return listener
    except Exception as exc:
        log_exception("Hotkey listener failed", exc)
        if strict:
            raise
        return None


def restart_hotkey_listener(raw: str) -> None:
    global hotkey_listener

    if hotkey_listener is not None:
        try:
            hotkey_listener.stop()
        except Exception:
            pass

    hotkey_listener = start_hotkey_listener(raw)


# ---------------------------------------------------------------------
# Focus detection (auto-paste into editable fields)
# ---------------------------------------------------------------------

# UI Automation control-type ids for editable controls.
_UIA_EDIT_CONTROL_TYPE = 50004
_UIA_DOCUMENT_CONTROL_TYPE = 50030
NATIVE_WINDOW_MARKER = "LocalDictationNativeWindow"


def window_process_id(hwnd) -> int:
    user32 = ctypes.windll.user32
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    top = user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT: includes WebView child windows.
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(top, ctypes.byref(process_id))
    return process_id.value


def window_is_app_owned(hwnd) -> bool:
    if window_process_id(hwnd) in {os.getpid(), native_owner_pid}:
        return True
    user32 = ctypes.windll.user32
    user32.GetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user32.GetPropW.restype = wintypes.HANDLE
    top = user32.GetAncestor(hwnd, 2) or hwnd
    return bool(user32.GetPropW(top, NATIVE_WINDOW_MARKER))


def element_is_writable(element, module) -> bool:
    if not element.CurrentIsEnabled or element.CurrentControlType not in (_UIA_EDIT_CONTROL_TYPE, _UIA_DOCUMENT_CONTROL_TYPE):
        return False
    try:
        pattern = element.GetCurrentPattern(10002).QueryInterface(module.IUIAutomationValuePattern)
        return not bool(pattern.CurrentIsReadOnly)
    except Exception:
        try:
            pattern = element.GetCurrentPattern(10014).QueryInterface(module.IUIAutomationTextPattern)
            readonly = pattern.DocumentRange.GetAttributeValue(40015)
            return isinstance(readonly, (bool, int)) and readonly == 0
        except Exception:
            return False


def focused_editable_target(click_point: Optional[tuple[int, int]] = None):
    """Return window/control identity only when UI Automation proves writability."""
    if os.name != "nt":
        return None

    try:
        import comtypes
        import comtypes.client
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        hwnd = user32.GetForegroundWindow()
        if not hwnd or window_is_app_owned(hwnd):
            return None
        comtypes.CoInitialize()
        try:
            module = comtypes.client.GetModule("UIAutomationCore.dll")
            automation = comtypes.client.CreateObject(
                module.CUIAutomation, interface=module.IUIAutomation
            )
            element = automation.GetFocusedElement()
            if element is None or not element_is_writable(element, module):
                return None
            if click_point is not None:
                clicked = automation.ElementFromPoint(module.tagPOINT(*click_point))
                if clicked is None or not element_is_writable(clicked, module) or tuple(clicked.GetRuntimeId()) != tuple(element.GetRuntimeId()):
                    return None
            return (hwnd, tuple(element.GetRuntimeId()))
        finally:
            comtypes.CoUninitialize()
    except Exception as exc:
        return None


def focused_field_is_editable() -> bool:
    return focused_editable_target() is not None


# ---------------------------------------------------------------------
# Paste flow
# ---------------------------------------------------------------------

def paste_text_to_active_target(text: str, *, session_id: Optional[int] = None,
                               click_point: Optional[tuple[int, int]] = None) -> bool:
    if not text:
        return False

    try:
        target = focused_editable_target(click_point)
        if target is None:
            return False
        time.sleep(config.PASTE_DELAY_SECONDS)
        if target != focused_editable_target(click_point):
            return False
        with state_lock:
            if session_id is not None and current_recording_session_id != session_id:
                return False
        pyperclip.copy(text)
        if target != focused_editable_target(click_point):
            return False
        with state_lock:
            if session_id is not None and current_recording_session_id != session_id:
                return False
        pyautogui.hotkey("ctrl", "v")
        log("Pasted.")
        with state_lock:
            still_current = session_id is None or current_recording_session_id == session_id
        if still_current:
            set_bubble(config.PASTED_LABEL, config.PASTED_BG)
        time.sleep(config.PASTED_STATE_SECONDS)
        reset_bubble_if_current(current_recording_session_id if session_id is None else session_id)
        return True
    except Exception as exc:
        log_exception("Paste failed", exc)
        return False


def paste_after_target_click(*, click_point: Optional[tuple[int, int]] = None,
                            expected_session_id: Optional[int] = None) -> None:
    global waiting_for_target_click, operation_error

    if click_point is not None and focused_editable_target(click_point) is None:
        return
    with state_lock:
        if expected_session_id is not None and current_recording_session_id != expected_session_id:
            return
        if not waiting_for_target_click or not latest_transcript:
            return
        text = latest_transcript
        session_id = current_recording_session_id
        waiting_for_target_click = False
        if operation_error.startswith('Paste'):
            operation_error = ''
    if not paste_text_to_active_target(text, session_id=session_id, click_point=click_point):
        with state_lock:
            if current_recording_session_id != session_id or recording or transcribing:
                return
            waiting_for_target_click = True
            operation_error = "Paste was not delivered. Text retained; click a writable text field to retry."
        set_bubble(config.PASTE_READY_LABEL, config.PASTE_READY_BG)


def remember_bubble_left_click(now: Optional[float] = None) -> None:
    global ignore_global_left_click_until

    current_time = time.monotonic() if now is None else now
    ignore_until = current_time + config.BUBBLE_GLOBAL_CLICK_IGNORE_SECONDS
    ignore_global_left_click_until = max(ignore_global_left_click_until, ignore_until)


def should_ignore_global_left_click(now: Optional[float] = None) -> bool:
    current_time = time.monotonic() if now is None else now
    return current_time < ignore_global_left_click_until


def should_ignore_bubble_release(now: Optional[float] = None) -> bool:
    global last_bubble_release_at

    current_time = time.monotonic() if now is None else now

    if (
        last_bubble_release_at is not None
        and current_time - last_bubble_release_at < config.BUBBLE_RELEASE_DEBOUNCE_SECONDS
    ):
        return True

    last_bubble_release_at = current_time
    return False


def click_is_inside_bubble(x: int, y: int) -> bool:
    if os.name == 'nt':
        user32 = ctypes.windll.user32
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
        if hwnd and window_is_app_owned(hwnd):
            return True
    if not visual_shell_enabled(backend_owner):
        return False
    if root is None:
        return False

    bubble_x = root.winfo_x()
    bubble_y = root.winfo_y()

    return (
        bubble_x <= x <= bubble_x + active_hit_target_size
        and bubble_y <= y <= bubble_y + active_hit_target_size
    )


def on_global_mouse_click(x, y, button, pressed) -> None:
    if shutting_down:
        return

    if pressed:
        return

    if button != mouse.Button.left:
        return

    if should_ignore_global_left_click():
        return

    if click_is_inside_bubble(x, y):
        return

    with state_lock:
        should_paste = waiting_for_target_click

    if not should_paste:
        return

    threading.Thread(target=paste_after_target_click, kwargs={'click_point': (x, y)}, daemon=True).start()


# ---------------------------------------------------------------------
# Bubble mouse behavior
# ---------------------------------------------------------------------

def on_bubble_press(event):
    global drag_start_x, drag_start_y, drag_moved
    global drag_press_time, left_button_down, long_press_quit_triggered

    drag_start_x = event.x
    drag_start_y = event.y
    drag_moved = False
    drag_press_time = time.monotonic()
    left_button_down = True
    long_press_quit_triggered = False
    remember_bubble_left_click(now=drag_press_time)

    if root is not None:
        delay_ms = int(config.LEFT_HOLD_QUIT_SECONDS * 1000)
        root.after(delay_ms, quit_after_left_hold_if_needed)

    return "break"


def on_bubble_drag(event):
    global drag_moved

    if root is None:
        return "break"

    dx = event.x - drag_start_x
    dy = event.y - drag_start_y

    if abs(dx) > config.DRAG_THRESHOLD_PIXELS or abs(dy) > config.DRAG_THRESHOLD_PIXELS:
        drag_moved = True

    new_x = root.winfo_x() + dx
    new_y = root.winfo_y() + dy

    root.geometry(f"{active_hit_target_size}x{active_hit_target_size}+{new_x}+{new_y}")
    return "break"


def quit_after_left_hold_if_needed() -> None:
    global long_press_quit_triggered

    hold_seconds = time.monotonic() - drag_press_time

    if should_quit_from_left_hold(
        hold_seconds=hold_seconds,
        moved=drag_moved,
        still_pressed=left_button_down,
    ):
        long_press_quit_triggered = True
        quit_app()


def on_bubble_release(event):
    global left_button_down, long_press_quit_triggered

    hold_seconds = time.monotonic() - drag_press_time
    left_button_down = False

    if should_ignore_bubble_release():
        log("Duplicate bubble left release ignored.")
        return "break"

    if long_press_quit_triggered:
        return "break"

    if should_quit_from_left_hold(
        hold_seconds=hold_seconds,
        moved=drag_moved,
        still_pressed=True,
    ):
        long_press_quit_triggered = True
        quit_app()
        return "break"

    if drag_moved:
        return "break"

    remember_bubble_left_click()

    with state_lock:
        is_recording = recording
        is_transcribing = transcribing

    if is_transcribing:
        log("Click ignored while transcribing.")
        return "break"

    if is_recording:
        stop_recording(reason="bubble-left-click")
    else:
        start_recording(source="bubble-left-click")

    return "break"


def shutdown_now() -> None:
    global shutting_down

    if shutting_down:
        return

    shutting_down = True
    log("Shutting down (fast exit).")

    if control_stop_event is not None:
        try:
            control_stop_event.set()
        except Exception:
            pass

    # Stop global low-level hooks before slow CUDA/PortAudio teardown can run.
    for stopper in (mouse_listener, hotkey_listener):
        try:
            if stopper is not None:
                stopper.stop()
        except Exception:
            pass

    stop_tray_icon()

    try:
        if audio_stream is not None:
            audio_stream.stop()
    except Exception:
        pass

    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass

    os._exit(0)


def quit_app(event=None) -> None:
    log("Exiting.")

    if root is not None:
        try:
            if visual_shell_enabled(backend_owner):
                control_set_settings({'settings': {'bubble_position': [root.winfo_x(), root.winfo_y()]}})
        except Exception:
            pass

        try:
            root.destroy()
        except Exception:
            pass

    shutdown_now()


def bind_bubble_events(app, label) -> None:
    app.bind("<ButtonPress-1>", on_bubble_press)
    app.bind("<B1-Motion>", on_bubble_drag)
    app.bind("<ButtonRelease-1>", on_bubble_release)
    app.bind("<ButtonRelease-2>", show_quick_history_popover)
    app.bind("<ButtonRelease-3>", show_quick_history_popover)
    label.bind("<ButtonPress-1>", on_bubble_press)
    label.bind("<B1-Motion>", on_bubble_drag)
    label.bind("<ButtonRelease-1>", on_bubble_release)
    label.bind("<ButtonRelease-2>", show_quick_history_popover)
    label.bind("<ButtonRelease-3>", show_quick_history_popover)


def set_no_activate(window) -> None:
    """Mark a window as no-activate so clicking it never steals keyboard focus.

    This keeps focus on the user's chat box / editor, so transcription can paste
    straight into it and a manual Ctrl+V lands in the right place.
    """
    if os.name != "nt":
        return

    try:
        user32 = ctypes.windll.user32
        target = window_top_hwnd(window)

        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080

        get_long = user32.GetWindowLongPtrW
        set_long = user32.SetWindowLongPtrW
        get_long.restype = ctypes.c_ssize_t
        get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
        set_long.restype = ctypes.c_ssize_t
        set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]

        current = get_long(target, GWL_EXSTYLE)
        set_long(target, GWL_EXSTYLE, current | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except Exception as exc:
        log_exception("set_no_activate failed", exc)


def window_top_hwnd(window) -> int:
    user32 = ctypes.windll.user32
    user32.GetParent.restype = ctypes.c_void_p
    user32.GetParent.argtypes = [ctypes.c_void_p]
    hwnd = window.winfo_id()
    parent = user32.GetParent(hwnd)
    return parent if parent else hwnd


def enable_layered(window) -> int:
    user32 = ctypes.windll.user32
    hwnd = window_top_hwnd(window)

    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOOLWINDOW = 0x00000080

    get_long = user32.GetWindowLongPtrW
    set_long = user32.SetWindowLongPtrW
    get_long.restype = ctypes.c_ssize_t
    get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
    set_long.restype = ctypes.c_ssize_t
    set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]

    current = get_long(hwnd, GWL_EXSTYLE)
    set_long(hwnd, GWL_EXSTYLE, current | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    return hwnd


def push_layered_image(hwnd, image) -> None:
    """Paint a PIL RGBA image as the window surface with per-pixel alpha."""
    from ctypes import wintypes

    width, height = image.size

    rgba = np.array(image.convert("RGBA"))
    alpha = rgba[:, :, 3].astype(np.uint16)
    blue = (rgba[:, :, 2].astype(np.uint16) * alpha // 255).astype(np.uint8)
    green = (rgba[:, :, 1].astype(np.uint16) * alpha // 255).astype(np.uint8)
    red = (rgba[:, :, 0].astype(np.uint16) * alpha // 255).astype(np.uint8)
    bgra = np.dstack([blue, green, red, rgba[:, :, 3]]).astype(np.uint8)
    buffer = bgra.tobytes()

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class SIZE(ctypes.Structure):
        _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    vp = ctypes.c_void_p
    user32.GetDC.restype = vp
    user32.GetDC.argtypes = [vp]
    user32.ReleaseDC.argtypes = [vp, vp]
    gdi32.CreateCompatibleDC.restype = vp
    gdi32.CreateCompatibleDC.argtypes = [vp]
    gdi32.CreateDIBSection.restype = vp
    gdi32.CreateDIBSection.argtypes = [vp, vp, wintypes.UINT, vp, vp, wintypes.DWORD]
    gdi32.SelectObject.restype = vp
    gdi32.SelectObject.argtypes = [vp, vp]
    gdi32.DeleteObject.argtypes = [vp]
    gdi32.DeleteDC.argtypes = [vp]

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB

    screen_dc = user32.GetDC(0)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)

    try:
        ctypes.memmove(bits, buffer, len(buffer))
        old = gdi32.SelectObject(mem_dc, bitmap)

        size = SIZE(width, height)
        src = POINT(0, 0)
        blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA
        ULW_ALPHA = 0x00000002

        user32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND, wintypes.HDC, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.HDC, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ]
        user32.UpdateLayeredWindow(
            hwnd, screen_dc, None, ctypes.byref(size),
            mem_dc, ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA,
        )
        gdi32.SelectObject(mem_dc, old)
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(0, screen_dc)


def render_layered_bubble(window, text: str, bg: str) -> None:
    glyph = "error" if text == config.ERROR_LABEL else bubble_icon_for_state(text)
    image = icons.render_bubble_rgba(
        glyph, bg, lighten_color(bg), active_hit_target_size, config.BUBBLE_SIZE, text
    )
    try:
        push_layered_image(window_top_hwnd(window), image)
    except Exception as exc:
        log_exception("Layered bubble update failed", exc)


def create_bubble_window() -> tk.Tk:
    global active_hit_target_size, bubble, bubble_layered

    app = tk.Tk()
    app.overrideredirect(True)
    app.attributes("-topmost", True)
    active_hit_target_size = config.HIT_TARGET_SIZE
    saved = SETTINGS.get("bubble_position")
    start_x = saved[0] if saved else config.START_X
    start_y = saved[1] if saved else config.START_Y
    app.geometry(f"{active_hit_target_size}x{active_hit_target_size}+{start_x}+{start_y}")
    app.update_idletasks()

    bubble_layered = False
    bubble = None

    # Preferred path: a Windows layered window with true per-pixel alpha. The
    # bubble is painted from an RGBA image, so the circle has smooth edges and
    # NO color-key halo around it.
    if icons.PIL_AVAILABLE and os.name == "nt":
        try:
            app.withdraw()
            enable_layered(app)
            bind_bubble_events(app, app)
            render_layered_bubble(app, config.READY_LABEL, config.READY_BG)
            app.deiconify()
            render_layered_bubble(app, config.READY_LABEL, config.READY_BG)
            bubble_layered = True
            log("Bubble rendered via layered window (per-pixel alpha).")
        except Exception as exc:
            log_exception("Layered bubble unavailable; using canvas fallback", exc)
            bubble_layered = False

    # Fallback: color-key transparent window with a vector-drawn circle.
    if not bubble_layered:
        transparent_bg = "#010203"
        app.configure(bg=transparent_bg)
        try:
            app.attributes("-transparentcolor", transparent_bg)
            active_hit_target_size = config.HIT_TARGET_SIZE
        except tk.TclError:
            app.configure(bg=config.READY_BG)
            active_hit_target_size = config.BUBBLE_SIZE

        app.geometry(f"{active_hit_target_size}x{active_hit_target_size}+{start_x}+{start_y}")

        label_bg = transparent_bg if active_hit_target_size == config.HIT_TARGET_SIZE else config.READY_BG
        label = tk.Canvas(
            app,
            width=config.BUBBLE_SIZE,
            height=config.BUBBLE_SIZE,
            bg=label_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        draw_bubble_state(label, config.READY_LABEL, config.READY_BG)

        offset = max((active_hit_target_size - config.BUBBLE_SIZE) // 2, 0)
        label.place(x=offset, y=offset, width=config.BUBBLE_SIZE, height=config.BUBBLE_SIZE)

        bind_bubble_events(app, label)
        bubble = label
        app.update_idletasks()
        set_no_activate(app)

    app.protocol("WM_DELETE_WINDOW", quit_app)

    return app


def configure_hidden_event_root(app):
    app.withdraw()
    for action in (
        lambda: app.title(""),
        lambda: app.geometry("1x1+-32000+-32000"),
        lambda: app.overrideredirect(True),
        lambda: app.attributes("-alpha", 0.0),
        lambda: app.attributes("-toolwindow", True),
    ):
        try:
            action()
        except Exception:
            pass
    app.protocol("WM_DELETE_WINDOW", quit_app)
    for delay in (0, 50, 250):
        try:
            app.after(delay, app.withdraw)
        except Exception:
            pass
    return app


def create_hidden_event_root() -> tk.Tk:
    return configure_hidden_event_root(tk.Tk())


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def show_startup_error(message: str) -> None:
    try:
        from tkinter import messagebox

        temp = tk.Tk()
        temp.withdraw()
        messagebox.showerror("Local Dictation", message)
        temp.destroy()
    except Exception:
        pass


def initialize_resources(initial_recording: bool = False) -> None:
    global model, audio_stream, loading, operation_error
    with state_lock:
        loading = True
        operation_error = ""
    try:
        if model is None:
            model = load_model()
        if audio_stream is None:
            stream = sd.InputStream(
                samplerate=config.SAMPLE_RATE, channels=config.CHANNELS,
                dtype="float32", callback=audio_callback,
            )
            try:
                stream.start()
            except Exception:
                stream.close()
                raise
            if shutting_down:
                stream.stop()
                stream.close()
                return
            audio_stream = stream
    except Exception as exc:
        log_exception("Resource initialization failed", exc)
        with state_lock:
            operation_error = f"Recording unavailable: {exc}"
        set_bubble(config.ERROR_LABEL, config.ERROR_BG)
    finally:
        with state_lock:
            loading = False
        if initial_recording and model is not None and audio_stream is not None and not shutting_down and root is not None:
            root.after(0, lambda: start_recording(source='startup'))


def main(initial_action: str = "run-app") -> None:
    global root, bubble, model, control_stop_event, hotkey_listener, mouse_listener, audio_stream
    global backend_owner, backend_started_monotonic

    if session_log_file is None:
        initialize_logging()

    backend_owner = initial_action
    backend_started_monotonic = time.monotonic()
    log_app_environment(initial_action)

    if not acquire_single_instance_lock():
        log("Another local dictation instance is already running.")
        release_launch_lock()
        command = control_command_for_existing_instance(initial_action)

        if command and not send_control_command(command):
            log("Existing instance control server is not ready.")

        return

    if visual_shell_enabled(initial_action):
        root = create_bubble_window()
    else:
        root = create_hidden_event_root()

    if python_tray_enabled(initial_action):
        start_tray_icon()

    control_stop_event = start_control_server()
    release_launch_lock()
    mouse_listener = mouse.Listener(on_click=on_global_mouse_click)
    mouse_listener.start()
    hotkey_listener = start_hotkey_listener(SETTINGS["hotkey"])
    root.after(0, lambda: threading.Thread(target=initialize_resources, args=(initial_action == 'start-recording',), daemon=True).start())

    if initial_action == "resident":
        hide_bubble_window()
    elif initial_action == "show-history":
        hide_bubble_window()
        root.after(0, show_history_panel)

    language_code = effective_language()
    log("")
    log("Floating dictation bubble is ready.")
    log(f"Model: {effective_model_name()} ({SETTINGS['model']})")
    log(f"Device: {active_device}")
    log(f"Language: {language_code if language_code else 'auto'}")
    log(f"Hotkey: {SETTINGS['hotkey'] if SETTINGS['hotkey'] else 'disabled'}")
    log("Click bubble to record.")
    log("Click bubble again to stop.")
    log(f"When it shows {config.PASTE_READY_LABEL}, click any text field.")
    log("Right-click the bubble for quick history and Settings.")
    log("Hold left click on the bubble for 2 seconds to quit.")
    log("")

    try:
        root.mainloop()
    finally:
        if control_stop_event is not None:
            control_stop_event.set()

        if mouse_listener is not None:
            mouse_listener.stop()

        if hotkey_listener is not None:
            hotkey_listener.stop()

        stop_tray_icon()

        if audio_stream is not None:
            audio_stream.stop()
            audio_stream.close()
        release_single_instance_lock()


if __name__ == "__main__":
    initialize_logging()

    try:
        cli_action = parse_cli_action(sys.argv[1:])
    except ValueError as exc:
        log(str(exc))
        raise SystemExit(2) from exc

    log(f"CLI action resolved: {cli_action}")

    if cli_action == "toggle-record":
        if not send_control_command("toggle-record"):
            start_app_detached("start-recording")
    elif cli_action == "show-history":
        if not send_control_command("show-history"):
            start_app_detached("show-history")
    else:
        main(initial_action=cli_action)
