import ctypes
import json
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
from typing import List, Optional, Sequence

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

    for site_dir in site.getsitepackages():
        for subdir in candidate_subdirs:
            dll_dir = Path(site_dir) / subdir

            if dll_dir.exists():
                try:
                    os.add_dll_directory(str(dll_dir))
                except Exception:
                    pass

                os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")


add_nvidia_dll_dirs()


import config
import icons
import settings
import numpy as np
import pyautogui
import pyperclip
import sounddevice as sd
import tkinter as tk
import tkinter.ttk as ttk

from faster_whisper import WhisperModel
from pynput import keyboard, mouse


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
        with path.open("a", encoding="utf-8") as file:
            file.write(text)
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

    if len(argv) == 1 and argv[0] == "--show-history":
        return "show-history"

    raise ValueError(f"Unknown argument(s): {' '.join(argv)}")


def control_command_for_existing_instance(initial_action: str) -> Optional[str]:
    if initial_action == "start-recording":
        return "toggle-record"

    if initial_action == "show-history":
        return "show-history"

    return None


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
            response = client.recv(64).decode("utf-8", errors="replace").strip()
            log(f"Control command response: command={command} response={response}")
            return response == "ok"
    except OSError as exc:
        log(f"Control command failed: command={command} error={exc}")
        return False


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


def handle_control_command(command: str) -> str:
    log(f"Control command received: {command}")

    if command not in {"toggle-record", "show-history"}:
        log(f"Control command rejected: {command}")
        return "error"

    if root is None:
        log(f"Control command rejected because root is not ready: {command}")
        return "error"

    if command == "toggle-record":
        root.after(0, toggle_recording_from_shortcut)
    else:
        root.after(0, show_history_panel)

    return "ok"


def control_server_loop(stop_event: threading.Event) -> None:
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

                with client:
                    data = client.recv(1024).decode("utf-8", errors="replace").strip()
                    response = handle_control_command(data)
                    client.sendall(response.encode("utf-8") + b"\n")
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
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
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
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        log_exception("Saving transcript history failed", exc)


def save_transcript_history_entries(
    entries: List[TranscriptHistoryEntry],
    history_path: Path,
) -> None:
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {"text": entry.text, "created_at": entry.created_at}
            for entry in entries
        ]
        history_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        log_exception("Saving transcript history failed", exc)


def add_transcript_to_history(
    text: str,
    history_path: Path = config.TRANSCRIPT_HISTORY_FILE,
    limit: int = config.TRANSCRIPT_HISTORY_LIMIT,
) -> List[str]:
    cleaned = text.strip()
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


def clean_transcript_text(text: str, language: Optional[str] = "en") -> str:
    cleaned = text.strip()

    if not cleaned:
        return ""

    cleaned = re.sub(r"[ \t\r\f\v]+", " ", cleaned)

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
    return settings.model_tier_to_name(SETTINGS["model"])


def effective_language() -> Optional[str]:
    return settings.language_to_whisper_code(SETTINGS["language"])


def current_palette() -> dict:
    return settings.palette_for(SETTINGS["theme"])


def current_alpha() -> float:
    return SETTINGS["opacity"] / 100.0


# ---------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------

def make_cuda_model() -> WhisperModel:
    return WhisperModel(
        effective_model_name(),
        device="cuda",
        compute_type=config.CUDA_COMPUTE_TYPE,
        download_root=config.MODEL_DOWNLOAD_ROOT,
        local_files_only=config.LOCAL_FILES_ONLY,
        num_workers=config.MODEL_NUM_WORKERS,
    )


def make_cpu_model() -> WhisperModel:
    return WhisperModel(
        effective_model_name(),
        device="cpu",
        compute_type=config.CPU_COMPUTE_TYPE,
        cpu_threads=config.CPU_THREADS,
        download_root=config.MODEL_DOWNLOAD_ROOT,
        local_files_only=config.LOCAL_FILES_ONLY,
        num_workers=config.MODEL_NUM_WORKERS,
    )


def warm_up_model(loaded_model: WhisperModel) -> None:
    """
    Forces the actual backend libraries to run immediately.

    Without this, CUDA can appear to load successfully, then fail later during
    the first real transcription with errors such as cublas64_12.dll missing.
    """
    silence = np.zeros(config.SAMPLE_RATE, dtype=np.float32)

    segments, _info = loaded_model.transcribe(
        silence,
        language=effective_language(),
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


def load_model() -> WhisperModel:
    global active_device

    log(f"Loading model: {effective_model_name()}")

    if config.PREFER_CUDA:
        try:
            log(f"Trying CUDA {config.CUDA_COMPUTE_TYPE}...")
            loaded_model = make_cuda_model()
            warm_up_model(loaded_model)
            active_device = "cuda"
            log("Model loaded and warmed up on CUDA.")
            return loaded_model
        except Exception as exc:
            log_exception("CUDA failed; falling back to CPU", exc)

    log(f"Using CPU {config.CPU_COMPUTE_TYPE}.")
    loaded_model = make_cpu_model()
    warm_up_model(loaded_model)
    active_device = "cpu"
    log("Model loaded and warmed up on CPU.")
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

    rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float32)))))
    log(f"Audio RMS: {rms:.6f}")

    return rms < config.MIN_AUDIO_RMS


def transcribe_audio(audio: np.ndarray) -> str:
    if model is None:
        raise RuntimeError("Model is not loaded.")

    if audio.size == 0:
        return ""

    audio = audio.reshape(-1).astype(np.float32)

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

    with state_lock:
        if recording or transcribing:
            log(f"Ignored start: source={source} already recording or transcribing.")
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
        latest_transcript = None
        waiting_for_target_click = False
        paste_after_transcription = False
        recording = True
        session_id = current_recording_session_id

    log(f"Recording started. session={session_id} source={source}")
    set_bubble(config.RECORDING_LABEL, config.RECORDING_BG)


def stop_recording(reason: str = "unknown") -> None:
    global recording, transcribing

    with state_lock:
        if not recording:
            log(f"Ignored stop: reason={reason} not recording.")
            return

        recording = False
        transcribing = True
        chunks = list(audio_chunks)
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
    global paste_after_transcription

    if not chunks:
        log(f"No audio chunks captured. session={session_id}")

        with state_lock:
            transcribing = False
            latest_transcript = None
            waiting_for_target_click = False
            paste_after_transcription = False

        set_bubble(config.EMPTY_LABEL, config.EMPTY_BG)
        time.sleep(config.EMPTY_STATE_SECONDS)
        set_bubble(config.READY_LABEL, config.READY_BG)
        return

    log(f"Transcribing... session={session_id}")

    try:
        audio = np.concatenate(chunks, axis=0)
        text = transcribe_audio(audio)

        if config.ENABLE_TEXT_CLEANUP:
            text = clean_transcript_text(text, language=effective_language())

        if config.LOG_TRANSCRIPT_TEXT:
            log("Transcript:")
            log(text if text else "[empty]")
        else:
            log(f"Transcript ready: {len(text)} chars" if text else "Transcript empty.")

        auto_paste_editable = (
            bool(text)
            and config.AUTO_PASTE_WHEN_EDITABLE
            and focused_field_is_editable()
        )

        with state_lock:
            should_auto_paste = paste_after_transcription or auto_paste_editable
            paste_after_transcription = False
            latest_transcript = text
            transcribing = False
            waiting_for_target_click = bool(text) and not should_auto_paste

        if text:
            pyperclip.copy(text)
            if config.SAVE_TRANSCRIPT_HISTORY:
                add_transcript_to_history(text)

            set_bubble(config.PASTE_READY_LABEL, config.PASTE_READY_BG)

            if should_auto_paste:
                reason = "editable field focused" if auto_paste_editable else "fast paste requested"
                log(f"Auto-paste ({reason}). session={session_id}")
                paste_text_to_active_target(text)
            else:
                log(f"Ready to paste. Click a text field. session={session_id}")
        else:
            set_bubble(config.EMPTY_LABEL, config.EMPTY_BG)
            time.sleep(config.EMPTY_STATE_SECONDS)
            set_bubble(config.READY_LABEL, config.READY_BG)

    except Exception as exc:
        log_exception("Transcription failed", exc)

        with state_lock:
            transcribing = False
            latest_transcript = None
            waiting_for_target_click = False
            paste_after_transcription = False

        set_bubble(config.ERROR_LABEL, config.ERROR_BG)
        time.sleep(config.ERROR_STATE_SECONDS)
        set_bubble(config.READY_LABEL, config.READY_BG)


# ---------------------------------------------------------------------
# History panel
# ---------------------------------------------------------------------

def preview_text(text: str, limit: int = 64) -> str:
    preview = " ".join(text.split())

    if len(preview) <= limit:
        return preview

    return preview[: limit - 1].rstrip() + "..."


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

    header = tk.Label(
        panel,
        text="Last 5",
        anchor="w",
        padx=8,
        pady=6,
        bg=palette["panel_bg"],
        fg=palette["text"],
        font=(config.BUBBLE_FONT_FAMILY, 9, "bold"),
    )
    header.grid(row=0, column=0, columnspan=3, sticky="ew")

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
        empty.grid(row=1, column=0, columnspan=3, sticky="ew")
    else:
        for row, text in enumerate(items, start=1):
            label = tk.Label(
                panel,
                text=preview_text(text),
                width=42,
                anchor="w",
                padx=8,
                pady=4,
                bg=palette["panel_bg"],
                fg=palette["text"],
            )
            label.grid(row=row, column=0, sticky="w")

            copy_button = tk.Button(
                panel,
                text="Copy",
                width=6,
                bg=palette["button_bg"],
                fg=palette["text"],
                activebackground=palette["button_hover"],
                relief="flat",
                command=lambda value=text: copy_history_text(value),
            )
            copy_button.grid(row=row, column=1, padx=2, pady=2)

            paste_button = tk.Button(
                panel,
                text="Paste",
                width=6,
                bg=palette["button_bg"],
                fg=palette["text"],
                activebackground=palette["button_hover"],
                relief="flat",
                command=lambda value=text: paste_history_text(value),
            )
            paste_button.grid(row=row, column=2, padx=2, pady=2)

    close_button = tk.Button(
        panel,
        text="Close",
        bg=palette["button_bg"],
        fg=palette["text"],
        activebackground=palette["button_hover"],
        relief="flat",
        command=panel.destroy,
    )
    close_button.grid(row=6, column=0, columnspan=3, sticky="ew", padx=8, pady=6)

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
) -> None:
    icon_center_y = y + 10

    rendered = False
    if icons.PIL_AVAILABLE:
        try:
            photo = glyph_photo(icon, text_color, 22)
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
        font=(config.BUBBLE_FONT_FAMILY, 12),
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
    y = bubble_y - height - 10

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
    panel_pad = 16
    panel_top = 8
    panel_bottom = height - pointer
    footer_y = panel_bottom - 44
    pointer_tip_x = width - 31
    pointer_base_left = pointer_tip_x - 18
    pointer_base_right = min(pointer_tip_x + 13, width - panel_pad)

    return {
        "panel_top": panel_top,
        "panel_bottom": panel_bottom,
        "panel_pad": panel_pad,
        "row_top": 34,
        "row_height": 86,
        "text_x": 36,
        "time_y_offset": 0,
        "transcript_y_offset": 25,
        "transcript_line_gap": 20,
        "transcript_width": 236,
        "preview_line_chars": 34,
        "button_y_offset": 20,
        "button_width": 68,
        "button_height": 36,
        "copy_x": width - 176,
        "paste_x": width - 98,
        "row_separator_offset": 72,
        "footer_y": footer_y,
        "footer_separator_y": footer_y - 16,
        "line_end": width - 36,
        "settings_icon_x": 52,
        "settings_x": 66,
        "footer_divider_x": 150,
        "history_icon_x": 196,
        "history_x": 210,
        "footer_divider2_x": 290,
        "close_icon_x": 318,
        "close_x": 332,
        "pointer_tip_x": pointer_tip_x,
        "pointer_base_left": pointer_base_left,
        "pointer_base_right": pointer_base_right,
    }


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

    draw_round_rect(
        canvas,
        layout["panel_pad"],
        layout["panel_top"],
        width - layout["panel_pad"],
        layout["panel_bottom"],
        radius=12,
        fill=palette["panel_bg"],
        outline=palette["panel_border"],
        width=1,
    )
    draw_round_rect(
        canvas,
        layout["panel_pad"] + 1,
        layout["panel_top"] + 1,
        width - layout["panel_pad"] - 1,
        layout["panel_bottom"] - 1,
        radius=11,
        fill="",
        outline=palette["inner_border"],
        width=1,
    )
    canvas.create_polygon(
        layout["pointer_base_left"],
        layout["panel_bottom"] - 1,
        layout["pointer_base_right"],
        layout["panel_bottom"] - 1,
        layout["pointer_tip_x"],
        height - 2,
        fill=palette["panel_bg"],
        outline="",
    )
    canvas.create_line(
        layout["pointer_base_left"],
        layout["panel_bottom"],
        layout["pointer_tip_x"],
        height - 2,
        fill=palette["panel_border"],
    )
    canvas.create_line(
        layout["pointer_tip_x"],
        height - 2,
        layout["pointer_base_right"],
        layout["panel_bottom"],
        fill=palette["panel_border"],
    )

    items = quick_history_items_for_display(limit=config.QUICK_HISTORY_LIMIT)

    if not items:
        canvas.create_text(
            layout["text_x"],
            layout["row_top"] + 28,
            anchor="nw",
            fill=palette["muted_text"],
            font=(config.BUBBLE_FONT_FAMILY, 12),
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
                font=(config.BUBBLE_FONT_FAMILY, 11),
                text=item.display_time,
            )
            canvas.create_text(
                layout["text_x"],
                y + layout["transcript_y_offset"],
                anchor="nw",
                fill=palette["text"],
                font=(config.BUBBLE_FONT_FAMILY, 12),
                text="\n".join(
                    quick_history_preview_lines(
                        item.text,
                        max_lines=2,
                        max_line_chars=layout["preview_line_chars"],
                    )
                ),
            )

            draw_quick_canvas_button(
                canvas,
                layout["copy_x"],
                y + layout["button_y_offset"],
                layout["button_width"],
                layout["button_height"],
                "Copy",
                lambda value=item.text: copy_quick_history_text(value),
                f"quick-copy-{index}",
                fill=palette["button_bg"],
                hover_fill=palette["button_hover"],
                outline=palette["button_border"],
                text_color=palette["text"],
            )

            draw_quick_canvas_button(
                canvas,
                layout["paste_x"],
                y + layout["button_y_offset"],
                layout["button_width"],
                layout["button_height"],
                "Paste",
                lambda value=item.text: paste_quick_history_text(value),
                f"quick-paste-{index}",
                fill=palette["button_bg"],
                hover_fill=palette["button_hover"],
                outline=palette["button_border"],
                text_color=palette["text"],
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
        layout["close_icon_x"],
        layout["close_x"],
        layout["footer_y"] + 2,
        "Close app",
        quit_app,
        "quick-close",
        "close",
        text_color=palette["text"],
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

    handle.bind("<ButtonPress-1>", press)
    handle.bind("<B1-Motion>", drag)

    for child in handle.winfo_children():
        if not isinstance(child, tk.Button):
            child.bind("<ButtonPress-1>", press)
            child.bind("<B1-Motion>", drag)


def apply_dark_combobox_style(style, palette) -> None:
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(
        "TCombobox",
        fieldbackground=palette["field_bg"],
        background=palette["button_bg"],
        foreground=palette["text"],
        arrowcolor=palette["text"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", palette["field_bg"])],
        foreground=[("readonly", palette["text"])],
    )
    style.configure("TScale", background=palette["panel_bg"])

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


def reload_model_for_settings(previous_model: str) -> None:
    global model, SETTINGS

    log(f"Reloading model for tier change -> {effective_model_name()}")
    set_bubble(config.TRANSCRIBING_LABEL, config.TRANSCRIBING_BG)

    try:
        model = load_model()
        set_bubble(config.READY_LABEL, config.READY_BG)
        log(f"Model reloaded on {active_device}.")
    except Exception as exc:
        log_exception("Model reload failed; reverting tier", exc)
        SETTINGS["model"] = previous_model
        settings.save_settings(SETTINGS)
        set_bubble(config.ERROR_LABEL, config.ERROR_BG)
        time.sleep(config.ERROR_STATE_SECONDS)
        set_bubble(config.READY_LABEL, config.READY_BG)


def build_settings_form(parent, palette) -> dict:
    section_font = (config.BUBBLE_FONT_FAMILY, 9, "bold")
    label_font = (config.BUBBLE_FONT_FAMILY, 9)

    def section(title):
        tk.Label(
            parent,
            text=title.upper(),
            bg=palette["panel_bg"],
            fg=palette["muted_text"],
            font=section_font,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 2))

    def row(label_text):
        frame = tk.Frame(parent, bg=palette["panel_bg"])
        frame.pack(fill="x", padx=12, pady=3)
        tk.Label(
            frame,
            text=label_text,
            bg=palette["panel_bg"],
            fg=palette["text"],
            font=label_font,
            width=14,
            anchor="w",
        ).pack(side="left")
        return frame

    language_var = tk.StringVar(value=SETTINGS["language"])
    model_var = tk.StringVar(value=SETTINGS["model"])
    theme_var = tk.StringVar(value=SETTINGS["theme"])
    # DoubleVar: ttk.Scale writes floats; validate_settings coerces to int on save.
    opacity_var = tk.DoubleVar(value=SETTINGS["opacity"])
    format_var = tk.StringVar(value=SETTINGS["text_format"])
    save_var = tk.StringVar(value=SETTINGS["save_location"])
    hotkey_var = tk.StringVar(value=SETTINGS["hotkey"])

    # 1. Transcription
    section("Transcription")
    r = row("Input Language")
    ttk.Combobox(r, textvariable=language_var, values=settings.LANGUAGE_CHOICES,
                 state="readonly", width=18).pack(side="left")
    r = row("Model")
    ttk.Combobox(r, textvariable=model_var, values=settings.MODEL_CHOICES,
                 state="readonly", width=18).pack(side="left")
    tk.Button(r, text="ⓘ", bd=0, bg=palette["panel_bg"], fg=palette["muted_text"],
              activebackground=palette["panel_bg"], cursor="hand2",
              command=lambda: show_info_tip(settings.MODEL_TIER_INFO)).pack(side="left", padx=4)

    # 2. Interface & Output
    section("Interface & Output")
    r = row("App Theme")
    ttk.Combobox(r, textvariable=theme_var, values=settings.THEME_CHOICES,
                 state="readonly", width=18).pack(side="left")
    r = row("Panel Opacity")
    ttk.Scale(r, from_=config.OPACITY_MIN, to=config.OPACITY_MAX, orient="horizontal",
              variable=opacity_var, length=150).pack(side="left")
    r = row("Text Format")
    ttk.Combobox(r, textvariable=format_var, values=settings.FORMAT_CHOICES,
                 state="readonly", width=18).pack(side="left")
    r = row("Save Location")
    tk.Entry(r, textvariable=save_var, width=16, bg=palette["field_bg"],
             fg=palette["text"], insertbackground=palette["text"], bd=1).pack(side="left")
    tk.Button(r, text="…", bd=0, bg=palette["button_bg"], fg=palette["text"],
              activebackground=palette["button_hover"], cursor="hand2",
              command=lambda: pick_save_location(save_var)).pack(side="left", padx=4)

    # 3. Commands & Hotkeys
    section("Commands & Hotkeys")
    r = row("Start/Stop Key")
    tk.Entry(r, textvariable=hotkey_var, width=18, bg=palette["field_bg"],
             fg=palette["text"], insertbackground=palette["text"], bd=1).pack(side="left")
    tk.Label(parent, text="Click the bubble to record (always on). "
                          "Hotkey example: <ctrl>+<alt>+d. Leave blank to disable.",
             bg=palette["panel_bg"], fg=palette["muted_text"],
             font=(config.BUBBLE_FONT_FAMILY, 8), wraplength=320, justify="left").pack(
             fill="x", padx=12, pady=(2, 6))

    return {
        "language": language_var, "model": model_var, "theme": theme_var,
        "opacity": opacity_var, "text_format": format_var,
        "save_location": save_var, "hotkey": hotkey_var,
    }


def build_settings_nav(parent, palette, vars_) -> None:
    bar = tk.Frame(parent, bg=palette["panel_bg"])
    bar.pack(side="bottom", fill="x", padx=12, pady=12)

    def nav_button(text, command, icon_name):
        button = tk.Button(
            bar, text=text, bd=0, relief="flat",
            bg=palette["button_bg"], fg=palette["text"],
            activebackground=palette["button_hover"], activeforeground=palette["text"],
            cursor="hand2", padx=9, pady=6,
            font=(config.BUBBLE_FONT_FAMILY, 9), command=command,
        )
        if icons.PIL_AVAILABLE:
            try:
                photo = glyph_photo(icon_name, palette["text"], 15)
                button.configure(image=photo, compound="left", padx=7)
                button.image = photo
            except Exception as exc:
                log_exception("Settings nav glyph failed", exc)
        return button

    nav_button(" Save", lambda: apply_settings_from_form(vars_), "save").pack(side="left")
    nav_button(" History", show_history_panel, "history").pack(side="left", padx=6)
    nav_button(" Export", export_all_history, "export").pack(side="left")
    nav_button(" Close app", quit_app, "close").pack(side="right")


def apply_settings_from_form(vars_) -> None:
    global SETTINGS

    previous_model = SETTINGS["model"]
    new_values = {key: var.get() for key, var in vars_.items()}
    new_values["bubble_position"] = SETTINGS.get("bubble_position")

    SETTINGS = settings.validate_settings(
        settings.merge_settings(settings.DEFAULT_SETTINGS, new_values)
    )
    settings.save_settings(SETTINGS)
    log("Settings saved.")

    restart_hotkey_listener(SETTINGS["hotkey"])
    redraw_bubble_current_state()

    if SETTINGS["model"] != previous_model:
        threading.Thread(target=reload_model_for_settings,
                         args=(previous_model,), daemon=True).start()

    close_settings_panel()


def show_settings_panel() -> None:
    global settings_panel

    close_quick_history_popover()
    show_bubble_window()

    if root is None:
        return

    if settings_panel is not None and settings_panel.winfo_exists():
        settings_panel.lift()
        return

    palette = current_palette()
    width, height = 360, 470

    panel = tk.Toplevel(root)
    settings_panel = panel
    panel.overrideredirect(True)
    panel.attributes("-topmost", True)
    panel.geometry(settings_panel_geometry(width, height))
    try:
        panel.attributes("-alpha", current_alpha())
    except tk.TclError:
        pass

    outer = tk.Frame(panel, bg=palette["panel_border"])
    outer.pack(fill="both", expand=True)
    body = tk.Frame(outer, bg=palette["panel_bg"])
    body.pack(fill="both", expand=True, padx=1, pady=1)

    style = ttk.Style(panel)
    apply_dark_combobox_style(style, palette)

    header = tk.Frame(body, bg=palette["panel_bg"])
    header.pack(fill="x", padx=12, pady=(10, 6))
    tk.Label(header, text="Settings", bg=palette["panel_bg"], fg=palette["text"],
             font=(config.BUBBLE_FONT_FAMILY, 11, "bold")).pack(side="left")
    tk.Button(header, text="✕", bd=0, bg=palette["panel_bg"], fg=palette["muted_text"],
              activebackground=palette["panel_bg"], cursor="hand2",
              command=close_settings_panel).pack(side="right")
    bind_panel_drag(panel, header)

    vars_ = build_settings_form(body, palette)
    build_settings_nav(body, palette, vars_)

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
    if root is not None:
        root.after(0, toggle_recording_from_shortcut)


def start_hotkey_listener(raw: str):
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


def focused_field_is_editable() -> bool:
    """True when the currently focused control is an editable text field.

    Uses Windows UI Automation, which sees native, browser, and Electron
    (Discord/Slack/ChatGPT) text boxes. Runs on the transcription worker
    thread, so it initializes COM for that thread and always degrades to
    False on any error (falling back to the click-to-paste flow).
    """
    if os.name != "nt":
        return False

    try:
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        try:
            module = comtypes.client.GetModule("UIAutomationCore.dll")
            automation = comtypes.client.CreateObject(
                module.CUIAutomation, interface=module.IUIAutomation
            )
            element = automation.GetFocusedElement()
            if element is None:
                return False
            return element.CurrentControlType in (
                _UIA_EDIT_CONTROL_TYPE,
                _UIA_DOCUMENT_CONTROL_TYPE,
            )
        finally:
            comtypes.CoUninitialize()
    except Exception as exc:
        log(f"Editable-field detection unavailable: {exc}")
        return False


# ---------------------------------------------------------------------
# Paste flow
# ---------------------------------------------------------------------

def paste_text_to_active_target(text: str) -> bool:
    if not text:
        return False

    time.sleep(config.PASTE_DELAY_SECONDS)

    try:
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        log("Pasted.")
        set_bubble(config.PASTED_LABEL, config.PASTED_BG)
        time.sleep(config.PASTED_STATE_SECONDS)
        set_bubble(config.READY_LABEL, config.READY_BG)
        return True
    except Exception as exc:
        log_exception("Paste failed", exc)
        set_bubble(config.ERROR_LABEL, config.ERROR_BG)
        return False


def paste_after_target_click() -> None:
    global waiting_for_target_click

    with state_lock:
        text = latest_transcript

        if not text:
            waiting_for_target_click = False
            set_bubble(config.READY_LABEL, config.READY_BG)
            return

        waiting_for_target_click = False

    paste_text_to_active_target(text)


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
    if root is None:
        return False

    bubble_x = root.winfo_x()
    bubble_y = root.winfo_y()

    return (
        bubble_x <= x <= bubble_x + active_hit_target_size
        and bubble_y <= y <= bubble_y + active_hit_target_size
    )


def on_global_mouse_click(x, y, button, pressed) -> None:
    if not pressed:
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

    threading.Thread(target=paste_after_target_click, daemon=True).start()


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


def quit_app(event=None) -> None:
    log("Exiting.")

    if root is not None:
        try:
            SETTINGS["bubble_position"] = [root.winfo_x(), root.winfo_y()]
            settings.save_settings(SETTINGS)
        except Exception:
            pass

        root.destroy()


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


def main(initial_action: str = "run-app") -> None:
    global root, bubble, model, control_stop_event, hotkey_listener

    if session_log_file is None:
        initialize_logging()

    log_app_environment(initial_action)

    if not acquire_single_instance_lock():
        log("Another local dictation instance is already running.")
        release_launch_lock()
        command = control_command_for_existing_instance(initial_action)

        if command and not send_control_command(command):
            log("Existing instance control server is not ready.")

        return

    try:
        model = load_model()
    except Exception as exc:
        log_exception("Model load failed at startup", exc)
        show_startup_error(
            "Could not load the speech model.\n"
            "Check that the selected model is downloaded and CUDA/CPU deps are installed.\n"
            "See dictation_debug.log for details."
        )
        release_launch_lock()
        release_single_instance_lock()
        return

    log("Starting microphone stream...")

    try:
        stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="float32",
            callback=audio_callback,
        )
        stream.start()
    except Exception as exc:
        log_exception("Microphone stream failed at startup", exc)
        show_startup_error(
            "Could not open the microphone.\n"
            "Check that a recording device is connected and not in use.\n"
            "See dictation_debug.log for details."
        )
        release_launch_lock()
        release_single_instance_lock()
        return

    listener = mouse.Listener(on_click=on_global_mouse_click)
    listener.start()

    hotkey_listener = start_hotkey_listener(SETTINGS["hotkey"])

    root = create_bubble_window()
    control_stop_event = start_control_server()
    release_launch_lock()

    if initial_action == "resident":
        root.withdraw()
    elif initial_action == "show-history":
        root.withdraw()
        root.after(0, show_history_panel)
    elif initial_action == "start-recording":
        root.after(0, toggle_recording_from_shortcut)

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

        listener.stop()

        if hotkey_listener is not None:
            hotkey_listener.stop()

        stream.stop()
        stream.close()
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
