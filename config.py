from pathlib import Path


# Audio capture.
SAMPLE_RATE = 16000
CHANNELS = 1

# Transcription model.
# For slightly better quality but slower: "large-v3"
# For faster CPU fallback: "medium" or "small"
MODEL_NAME = "large-v3-turbo"
MODEL_DOWNLOAD_ROOT = None

# Use "en" for fastest English dictation.
# Use None for automatic language detection.
LANGUAGE = "en"

# True prevents implicit model downloads. Use a cached model name or local path.
LOCAL_FILES_ONLY = True

# GPU first. If CUDA fails, the app falls back to CPU.
PREFER_CUDA = True
CUDA_COMPUTE_TYPE = "float16"
CPU_COMPUTE_TYPE = "int8"
CPU_THREADS = 8
MODEL_NUM_WORKERS = 1

# Bubble size and position.
BUBBLE_SIZE = 32
HIT_TARGET_SIZE = 38
START_X = 40
START_Y = 220
BUBBLE_FONT_FAMILY = "Segoe UI"
BUBBLE_FONT_SIZE = 7
BUBBLE_FONT_WEIGHT = "bold"
DRAG_THRESHOLD_PIXELS = 3
LEFT_HOLD_QUIT_SECONDS = 2.0
BUBBLE_GLOBAL_CLICK_IGNORE_SECONDS = 0.6
BUBBLE_RELEASE_DEBOUNCE_SECONDS = 0.18

# Bubble labels. Keep these short so the bubble stays small.
READY_LABEL = "M"
RECORDING_LABEL = "R"
TRANSCRIBING_LABEL = "\u2026"
PASTE_READY_LABEL = "P"
PASTED_LABEL = "\u2713"
EMPTY_LABEL = "-"
ERROR_LABEL = "!"

# Bubble colors. Calm, slightly muted palette for a modern minimal look.
READY_BG = "#1f6f4a"
RECORDING_BG = "#cf4b41"
TRANSCRIBING_BG = "#e0a526"
PASTE_READY_BG = "#2b6fd6"
PASTED_BG = "#188038"
EMPTY_BG = "#5f6368"
ERROR_BG = "#b4503f"

# Timing and filtering.
PASTE_DELAY_SECONDS = 0.35
MIN_AUDIO_SECONDS = 0.35
MIN_AUDIO_RMS = 0.003
EMPTY_STATE_SECONDS = 0.8
PASTED_STATE_SECONDS = 0.8
ERROR_STATE_SECONDS = 1.5

# Productivity behavior.
# Recording is manual-stop only: click M to start, click red R to stop.
# Target clicks while recording should not stop recording.
ENABLE_FAST_TARGET_CLICK_PASTE = False
# When the focused control is an editable text field (chat box, editor, etc.),
# paste automatically as soon as transcription finishes. Otherwise fall back to
# the click-a-field flow. The bubble is a no-activate window so it never steals
# focus from that field.
AUTO_PASTE_WHEN_EDITABLE = True
ENABLE_TEXT_CLEANUP = True
SAVE_TRANSCRIPT_HISTORY = True
TRANSCRIPT_HISTORY_LIMIT = 5
TRANSCRIPT_HISTORY_FILE = Path(r"C:\local-dictation\transcript_history.json")
STARTUP_SHORTCUT_ENABLED_BY_DEFAULT = True

# Quick history popover shown from right-clicking the bubble.
QUICK_HISTORY_LIMIT = 3
QUICK_HISTORY_WIDTH = 410
QUICK_HISTORY_HEIGHT = 286
QUICK_HISTORY_BG = "#080c12"
QUICK_HISTORY_BORDER = "#4b5563"
QUICK_HISTORY_SEPARATOR = "#303946"
QUICK_HISTORY_TEXT = "#f7f9fc"
QUICK_HISTORY_MUTED_TEXT = "#98a3b3"
QUICK_HISTORY_BUTTON_BG = "#121923"
QUICK_HISTORY_BUTTON_BORDER = "#343f4d"
QUICK_HISTORY_POINTER_SIZE = 12
QUICK_HISTORY_DEBOUNCE_SECONDS = 0.25

# Local-only control channel for the pinned shortcut.
CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 49731
CONTROL_TIMEOUT_SECONDS = 0.35
SINGLE_INSTANCE_MUTEX_NAME = "Local\\LocalDictationBubbleApp"
LAUNCH_LOCK_FILE = Path(r"C:\local-dictation\dictation_launch.lock")
LAUNCH_LOCK_STALE_SECONDS = 30.0

# Local log file. Keep this path local unless intentionally moving the app.
LOG_FILE = Path(r"C:\local-dictation\dictation_debug.log")
LOG_DIR = Path(r"C:\local-dictation\logs")
SESSION_LOG_KEEP_COUNT = 100
DEBUG_LOG_BUBBLE_STATES = True
DEBUG_LOG_AUDIO_FIRST_CALLBACK = True
DEBUG_LOG_AUDIO_EVERY_N_CALLBACKS = 100

# Runtime, user-editable settings file (written by the Settings panel).
SETTINGS_FILE = Path(r"C:\local-dictation\settings.json")

# Opacity bounds for the panels (percent).
OPACITY_MIN = 70
OPACITY_MAX = 100

# Privacy: transcript text is NOT written to logs unless this is True.
LOG_TRANSCRIPT_TEXT = False
