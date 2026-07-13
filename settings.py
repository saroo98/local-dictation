import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import config

SETTINGS_FILE = config.SETTINGS_FILE

# Friendly choices shown in the Settings panel dropdowns.
LANGUAGE_CHOICES = ["English (US)", "Auto Detect", "Kurdish", "Persian", "Arabic"]
DEFAULT_MODEL_CHOICES = ["Fast", "Balanced", "High Accuracy"]
OPTIONAL_MODEL_CHOICES = ["Ultra Fast English", "Compact Multilingual", "Medium Quality"]
MODEL_CHOICES = DEFAULT_MODEL_CHOICES + OPTIONAL_MODEL_CHOICES
MODEL_ORDER_CHOICES = ["Speed", "Accuracy"]
DEVICE_MODE_CHOICES = ["auto", "cuda", "cpu"]
THEME_CHOICES = ["Dark Mode", "Light Mode", "System"]
FORMAT_CHOICES = ["Plain Text", "Markdown (.md)"]
MODEL_REPO_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")

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
    "Ultra Fast English": "tiny.en",
    "Compact Multilingual": "base",
    "Medium Quality": "medium",
}

MODEL_TIER_TO_REPO: Dict[str, str] = {
    "Fast": "Systran/faster-whisper-small",
    "Balanced": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "High Accuracy": "Systran/faster-whisper-large-v3",
    "Ultra Fast English": "Systran/faster-whisper-tiny.en",
    "Compact Multilingual": "Systran/faster-whisper-base",
    "Medium Quality": "Systran/faster-whisper-medium",
}

MODEL_TIER_DESCRIPTIONS: Dict[str, str] = {
    "Fast": "lowest latency, good for short notes",
    "Balanced": "default; strong quality, quick",
    "High Accuracy": "best quality, slower",
    "Ultra Fast English": "fastest English-only model",
    "Compact Multilingual": "small multilingual fallback",
    "Medium Quality": "middle ground between base and large",
}

MODEL_TIER_EXPECTED_SIZE_TEXT: Dict[str, str] = {
    "Ultra Fast English": "75 MB",
    "Compact Multilingual": "141 MB",
    "Fast": "464 MB",
    "Medium Quality": "1.46 GB",
    "Balanced": "1.55 GB",
    "High Accuracy": "2.95 GB",
}

MODEL_CHOICES_BY_ORDER: Dict[str, List[str]] = {
    "Speed": [
        "Ultra Fast English",
        "Compact Multilingual",
        "Fast",
        "Medium Quality",
        "Balanced",
        "High Accuracy",
    ],
    "Accuracy": [
        "High Accuracy",
        "Balanced",
        "Medium Quality",
        "Fast",
        "Compact Multilingual",
        "Ultra Fast English",
    ],
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "language": "English (US)",
    "model": "Balanced",
    "model_order": "Speed",
    "device_mode": "auto",
    "theme": "Dark Mode",
    "opacity": 96,
    "text_format": "Plain Text",
    "save_location": "",          # empty -> Documents at export time
    "hotkey": "<ctrl>+<alt>+d",   # empty string disables the global hotkey
    "bubble_position": None,       # [x, y] or None
    "custom_models": [],           # [{"name": "...", "source": "repo/id or C:\\path"}]
}

DARK_PALETTE: Dict[str, str] = {
    "panel_bg": "#080c12",
    "panel_border": "#4b5563",
    "inner_border": "#202936",
    "separator": "#303946",
    "text": "#f7f9fc",
    "muted_text": "#98a3b3",
    "button_bg": "#121923",
    "button_border": "#343f4d",
    "button_hover": "#1a2431",
    "field_bg": "#0b1119",
}

LIGHT_PALETTE: Dict[str, str] = {
    "panel_bg": "#f8f7f3",
    "panel_border": "#cfc7bb",
    "inner_border": "#eee8dc",
    "separator": "#e1dbcf",
    "text": "#16191d",
    "muted_text": "#66706d",
    "button_bg": "#f0ece3",
    "button_border": "#d6cec0",
    "button_hover": "#e7e1d6",
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
    result["custom_models"] = normalize_custom_models(result.get("custom_models"))

    if result.get("language") not in LANGUAGE_CHOICES:
        result["language"] = DEFAULT_SETTINGS["language"]
    if result.get("model_order") not in MODEL_ORDER_CHOICES:
        result["model_order"] = DEFAULT_SETTINGS["model_order"]
    if result.get("device_mode") not in DEVICE_MODE_CHOICES:
        result["device_mode"] = DEFAULT_SETTINGS["device_mode"]
    if result.get("model") not in model_choices(result["custom_models"], order=result["model_order"]):
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


def is_hugging_face_repo_id(source: str) -> bool:
    return bool(MODEL_REPO_PATTERN.match((source or "").strip()))


def is_valid_faster_whisper_model_dir(path: Path) -> bool:
    try:
        if not path.is_dir():
            return False
        required = ["config.json", "model.bin", "tokenizer.json"]
        if not all((path / filename).exists() for filename in required):
            return False
        return any(path.glob("vocabulary.*"))
    except OSError:
        return False


def normalize_custom_models(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []

    cleaned: List[Dict[str, str]] = []
    seen_names = set(MODEL_CHOICES)

    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        source = str(item.get("source", "")).strip()
        if not name or not source or name in seen_names:
            continue
        if not is_hugging_face_repo_id(source) and not is_valid_faster_whisper_model_dir(Path(source)):
            continue
        seen_names.add(name)
        cleaned.append({"name": name, "source": source})

    return cleaned


def custom_model_items(custom_models: Optional[Sequence[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    seen = set(MODEL_CHOICES)
    for item in custom_models or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        source = str(item.get("source", "")).strip()
        if not name or not source or name in seen:
            continue
        seen.add(name)
        items.append({"name": name, "source": source})
    return items


def model_choices(
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
    order: Optional[str] = None,
) -> List[str]:
    choices = list(MODEL_CHOICES_BY_ORDER.get(order or "", MODEL_CHOICES))
    for item in custom_model_items(custom_models):
        choices.append(item["name"])
    return choices


def model_display_size_text(
    model_choice: str,
    cache_root: Optional[Path] = None,
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
) -> str:
    details = model_tier_details(
        model_choice,
        cache_root=cache_root,
        custom_models=custom_models,
    )
    if details["available"]:
        return details["size_text"]
    return MODEL_TIER_EXPECTED_SIZE_TEXT.get(model_choice, details["size_text"])


def model_dropdown_label(
    model_choice: str,
    cache_root: Optional[Path] = None,
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
) -> str:
    details = model_tier_details(
        model_choice,
        cache_root=cache_root,
        custom_models=custom_models,
    )
    return f"{details['tier']} - {details['model_name']} - {model_display_size_text(model_choice, cache_root, custom_models)}"


def model_dropdown_options(
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
    order: Optional[str] = None,
    cache_root: Optional[Path] = None,
) -> List[str]:
    return [
        model_dropdown_label(choice, cache_root=cache_root, custom_models=custom_models)
        for choice in model_choices(custom_models, order=order)
    ]


def model_choice_from_dropdown_label(
    label: str,
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
    order: Optional[str] = None,
) -> str:
    for choice in model_choices(custom_models, order=order):
        if label == model_dropdown_label(choice, custom_models=custom_models):
            return choice
    candidate = str(label).split(" - ", 1)[0].strip()
    return candidate if candidate in model_choices(custom_models, order=order) else DEFAULT_SETTINGS["model"]


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


def custom_model_source(
    model_choice: str,
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
) -> Optional[str]:
    for item in custom_model_items(custom_models):
        if item["name"] == model_choice:
            return item["source"]
    return None


def model_tier_to_name(
    model_choice: str,
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
) -> str:
    custom_source = custom_model_source(model_choice, custom_models)
    if custom_source is not None:
        return custom_source
    return MODEL_TIER_TO_NAME.get(model_choice, "large-v3-turbo")


def model_tier_to_repo(
    model_choice: str,
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
) -> str:
    custom_source = custom_model_source(model_choice, custom_models)
    if custom_source and is_hugging_face_repo_id(custom_source):
        return custom_source
    return MODEL_TIER_TO_REPO.get(model_choice, MODEL_TIER_TO_REPO["Balanced"])


def huggingface_cache_root() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def repo_cache_dir(repo_id: str, cache_root: Optional[Path] = None) -> Path:
    root = Path(cache_root) if cache_root is not None else huggingface_cache_root()
    return root / ("models--" + repo_id.replace("/", "--"))


def directory_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def format_size(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "not installed locally"
    if num_bytes < 1024 * 1024:
        return f"{max(1, round(num_bytes / 1024))} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{round(num_bytes / (1024 * 1024))} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


def model_revision(repo_dir: Path) -> str:
    ref_path = repo_dir / "refs" / "main"
    try:
        return ref_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def repo_snapshot_dir(repo_dir: Path, revision: str) -> Path:
    return repo_dir / "snapshots" / revision


def repo_has_model_files(repo_dir: Path, revision: str) -> bool:
    if not revision:
        return False
    snapshot_dir = repo_snapshot_dir(repo_dir, revision)
    return snapshot_dir.is_dir() and (snapshot_dir / "model.bin").exists()


def model_tier_details(
    model_choice: str,
    cache_root: Optional[Path] = None,
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    custom_source = custom_model_source(model_choice, custom_models)

    if custom_source and not is_hugging_face_repo_id(custom_source):
        model_path = Path(custom_source)
        size_bytes = directory_size_bytes(model_path)
        return {
            "tier": model_choice,
            "model_name": custom_source,
            "repo_id": "",
            "description": "custom local faster-whisper model",
            "cache_dir": str(model_path),
            "available": is_valid_faster_whisper_model_dir(model_path),
            "revision": "local folder",
            "size_bytes": size_bytes,
            "size_text": format_size(size_bytes),
            "source_type": "local",
            "custom": True,
        }

    tier = model_choice if model_choice in model_choices(custom_models) else DEFAULT_SETTINGS["model"]
    model_name = model_tier_to_name(tier, custom_models)
    repo_id = model_tier_to_repo(tier, custom_models)
    repo_dir = repo_cache_dir(repo_id, cache_root=cache_root)
    size_bytes = directory_size_bytes(repo_dir)
    revision = model_revision(repo_dir)
    available = repo_has_model_files(repo_dir, revision)

    return {
        "tier": tier,
        "model_name": model_name,
        "repo_id": repo_id,
        "description": MODEL_TIER_DESCRIPTIONS.get(tier, ""),
        "cache_dir": str(repo_dir),
        "available": available,
        "revision": revision,
        "size_bytes": size_bytes,
        "size_text": format_size(size_bytes) if available else "not installed locally",
        "source_type": "repo" if custom_source else "builtin",
        "custom": bool(custom_source),
    }


def model_is_available_locally(
    model_choice: str,
    cache_root: Optional[Path] = None,
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
) -> bool:
    return bool(
        model_tier_details(
            model_choice,
            cache_root=cache_root,
            custom_models=custom_models,
        )["available"]
    )


def model_tier_summary(
    model_choice: str,
    cache_root: Optional[Path] = None,
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
    *,
    include_revision: bool = True,
) -> str:
    details = model_tier_details(
        model_choice,
        cache_root=cache_root,
        custom_models=custom_models,
    )
    status = details["size_text"] if details["available"] else "not installed locally"
    revision = details["revision"] or "not cached"
    summary = (
        f"{details['tier']}: {details['model_name']} | "
        f"{details['repo_id'] or details['cache_dir']} | {status}"
    )
    if include_revision:
        summary += f" | revision {revision}"
    return summary


def model_tier_info_text(
    cache_root: Optional[Path] = None,
    custom_models: Optional[Sequence[Dict[str, str]]] = None,
) -> str:
    lines = [
        model_tier_summary(choice, cache_root=cache_root, custom_models=custom_models)
        for choice in model_choices(custom_models)
    ]
    lines.append("Offline mode is on: models must already be cached locally.")
    return "\n".join(lines)


MODEL_TIER_INFO = "Model tiers are resolved from the local Hugging Face cache at runtime."


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
