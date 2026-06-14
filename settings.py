import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import config

SETTINGS_FILE = config.SETTINGS_FILE

# Friendly choices shown in the Settings panel dropdowns.
LANGUAGE_CHOICES = ["English (US)", "Auto Detect", "Kurdish", "Persian", "Arabic"]
MODEL_CHOICES = ["Fast", "Balanced", "High Accuracy"]
THEME_CHOICES = ["Dark Mode", "Light Mode", "System"]
FORMAT_CHOICES = ["Plain Text", "Markdown (.md)"]

# Friendly choice -> Whisper language code. None means auto-detect.
# NOTE: Whisper has no native Kurdish; we use auto-detect as best effort.
LANGUAGE_TO_CODE: Dict[str, Optional[str]] = {
    "English (US)": "en",
    "Auto Detect": None,
    "Kurdish": None,
    "Persian": "fa",
    "Arabic": "ar",
}

# Friendly tier -> faster-whisper model name.
MODEL_TIER_TO_NAME: Dict[str, str] = {
    "Fast": "small",
    "Balanced": "large-v3-turbo",
    "High Accuracy": "large-v3",
}

MODEL_TIER_INFO = (
    "Fast (small): lowest latency, good for short notes.\n"
    "Balanced (large-v3-turbo): default; strong quality, quick.\n"
    "High Accuracy (large-v3): best quality, slower.\n"
    "Models must already be cached locally (offline mode)."
)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "language": "English (US)",
    "model": "Balanced",
    "theme": "Dark Mode",
    "opacity": 96,
    "text_format": "Plain Text",
    "save_location": "",          # empty -> Documents at export time
    "hotkey": "<ctrl>+<alt>+d",   # empty string disables the global hotkey
    "bubble_position": None,       # [x, y] or None
}

DARK_PALETTE: Dict[str, str] = {
    "panel_bg": "#171a1d",
    "panel_border": "#686d73",
    "inner_border": "#252a2f",
    "separator": "#40454a",
    "text": "#f2f2f2",
    "muted_text": "#b7b7b7",
    "button_bg": "#24282d",
    "button_border": "#555a61",
    "button_hover": "#2e3136",
    "field_bg": "#1f2327",
}

LIGHT_PALETTE: Dict[str, str] = {
    "panel_bg": "#f4f5f6",
    "panel_border": "#b9bec4",
    "inner_border": "#dfe2e5",
    "separator": "#d4d8dc",
    "text": "#1b1d1f",
    "muted_text": "#5f6368",
    "button_bg": "#e9ebed",
    "button_border": "#c0c5ca",
    "button_hover": "#dde0e3",
    "field_bg": "#ffffff",
}


def merge_settings(defaults: Dict[str, Any], loaded: Any) -> Dict[str, Any]:
    merged = dict(defaults)
    if isinstance(loaded, dict):
        for key in defaults:
            if key in loaded:
                merged[key] = loaded[key]
    return validate_settings(merged)


def validate_settings(values: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(values)

    if result.get("language") not in LANGUAGE_CHOICES:
        result["language"] = DEFAULT_SETTINGS["language"]
    if result.get("model") not in MODEL_CHOICES:
        result["model"] = DEFAULT_SETTINGS["model"]
    if result.get("theme") not in THEME_CHOICES:
        result["theme"] = DEFAULT_SETTINGS["theme"]
    if result.get("text_format") not in FORMAT_CHOICES:
        result["text_format"] = DEFAULT_SETTINGS["text_format"]

    try:
        opacity = int(result.get("opacity", DEFAULT_SETTINGS["opacity"]))
    except (TypeError, ValueError):
        opacity = DEFAULT_SETTINGS["opacity"]
    result["opacity"] = max(config.OPACITY_MIN, min(config.OPACITY_MAX, opacity))

    if not isinstance(result.get("save_location"), str):
        result["save_location"] = ""
    if not isinstance(result.get("hotkey"), str):
        result["hotkey"] = DEFAULT_SETTINGS["hotkey"]

    position = result.get("bubble_position")
    if (
        isinstance(position, (list, tuple))
        and len(position) == 2
        and all(isinstance(coordinate, int) for coordinate in position)
    ):
        result["bubble_position"] = [int(position[0]), int(position[1])]
    else:
        result["bubble_position"] = None

    return result


def load_settings(settings_path: Path = SETTINGS_FILE) -> Dict[str, Any]:
    try:
        loaded = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = None
    return merge_settings(DEFAULT_SETTINGS, loaded)


def save_settings(values: Dict[str, Any], settings_path: Path = SETTINGS_FILE) -> None:
    cleaned = validate_settings(merge_settings(DEFAULT_SETTINGS, values))
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def language_to_whisper_code(language_choice: str) -> Optional[str]:
    return LANGUAGE_TO_CODE.get(language_choice, "en")


def model_tier_to_name(model_choice: str) -> str:
    return MODEL_TIER_TO_NAME.get(model_choice, "large-v3-turbo")


def resolve_theme(theme_choice: str) -> str:
    if theme_choice == "System":
        return "Light Mode" if windows_apps_use_light_theme() else "Dark Mode"
    return theme_choice if theme_choice in ("Dark Mode", "Light Mode") else "Dark Mode"


def palette_for(theme_choice: str) -> Dict[str, str]:
    return LIGHT_PALETTE if resolve_theme(theme_choice) == "Light Mode" else DARK_PALETTE


def windows_apps_use_light_theme() -> bool:
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return bool(value)
    except OSError:
        return False


def export_extension(text_format: str) -> str:
    return ".md" if text_format == "Markdown (.md)" else ".txt"


def format_history_export(
    entries: Sequence[Any],
    text_format: str,
) -> str:
    """entries: objects with .text and .display_time (TranscriptHistoryEntry)."""
    if not entries:
        return ""

    lines: List[str] = []

    if text_format == "Markdown (.md)":
        lines.append("# Dictation History\n")
        for entry in entries:
            lines.append(f"## {entry.display_time}\n")
            lines.append(f"{entry.text}\n")
        return "\n".join(lines).strip() + "\n"

    for entry in entries:
        lines.append(f"[{entry.display_time}]")
        lines.append(entry.text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"
