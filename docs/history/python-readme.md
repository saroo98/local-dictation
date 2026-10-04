# Local Dictation Bubble

Local Dictation Bubble is an offline Windows speech-to-text app for fast voice typing. It uses `faster-whisper` locally, tries CUDA GPU transcription first, falls back to CPU when needed, and pastes the transcript into the field you click.

The app is designed for people who want a tiny always-ready dictation bubble without cloud APIs, accounts, telemetry, or uploaded audio.

## Features

- Offline Windows dictation with local `faster-whisper`
- CUDA-first GPU loading with CPU fallback
- Tiny always-on-top bubble for quick recording
- Manual-stop recording flow: click play to record, click stop to transcribe
- Click a target text field after transcription to paste
- Clipboard keeps the last transcript even if paste fails
- Right-click quick history for recent transcripts
- Optional Desktop, Start Menu, Startup, History, and Debug Log shortcuts
- Local transcript history JSON only
- No cloud API calls, no telemetry, no permanent audio storage

## Who It Is For

Use this if you want:

- offline dictation for Windows
- local voice typing without sending speech to a server
- a small desktop dictation bubble
- faster-whisper speech recognition on an NVIDIA GPU
- clipboard-based dictation that works across apps
- a simple accessibility and productivity tool for writing faster

## Requirements

- Windows
- Python 3.12 recommended
- Microphone
- NVIDIA GPU recommended for CUDA mode
- CPU fallback works, but transcription can be slower

Python packages are listed in `requirements.txt`.

## Install

This project currently expects the local path:

```powershell
C:\local-dictation
```

From PowerShell:

```powershell
cd C:\local-dictation
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The model must already be available locally because `LOCAL_FILES_ONLY = True` in `config.py`.

## Run

```powershell
cd C:\local-dictation
.\.venv\Scripts\python.exe .\bubble_dictate.py
```

Or install shortcuts:

```powershell
cd C:\local-dictation
powershell -ExecutionPolicy Bypass -File .\create-shortcut.ps1
```

This creates:

- Desktop: `Local Dictation Toggle`
- Desktop: `Local Dictation History`
- Desktop: `Local Dictation Debug Log`
- Start Menu shortcuts
- Startup shortcut for resident mode

To remove them:

```powershell
cd C:\local-dictation
powershell -ExecutionPolicy Bypass -File .\remove-shortcuts.ps1
```

## How To Use

1. Click the green play bubble to start recording.
2. Speak normally.
3. Click the red stop bubble to stop recording.
4. Wait for transcription.
5. Click the text field where the transcript should go.
6. The app pastes the transcript.

If your cursor is already in an editable text field (a chat box, editor, search
box — native, browser, or Electron apps), the transcript pastes there
automatically as soon as it is ready, so you can skip step 5. If no editable
field is focused, it waits for you to click one (the flow above). The bubble is a
no-activate window, so clicking it never steals focus from your text field.
Auto-paste can be turned off with `AUTO_PASTE_WHEN_EDITABLE = False` in `config.py`.

Right-click the bubble to show recent transcript history. Hold left click on the bubble for 2 seconds to quit.

## Configuration

Edit `config.py` for user-editable settings:

- model name
- language
- CUDA preference
- CPU thread count
- bubble size and position
- transcript cleanup
- history limits
- shortcut behavior
- log paths

## Settings

Right-click the bubble and choose **Settings** to open the in-app panel. Settings are
saved to `C:\local-dictation\settings.json` and most apply live.

**Transcription**

- Input Language: English (US), Auto Detect, Kurdish, Persian, Arabic. Whisper has no
  native Kurdish model, so Kurdish uses auto-detect as a best-effort fallback.
- Model: Fast (`small`), Balanced (`large-v3-turbo`, default), High Accuracy (`large-v3`).
  The chosen model must already be cached locally because `LOCAL_FILES_ONLY = True`; a tier
  you have never downloaded will fail to load and the app reverts to the previous tier.

**Interface & Output**

- App Theme: Dark Mode, Light Mode, or System (follows the Windows apps theme).
- Panel Opacity: 70–100% for the popover and panels.
- Default Text Format: Plain Text (`.txt`) or Markdown (`.md`), used by Export All.
- Save Location: folder used by Export All (defaults to your Documents folder).

**Commands & Hotkeys**

- Start/Stop Recording hotkey: a global hotkey in pynput syntax, e.g. `<ctrl>+<alt>+d`.
  Leave the field blank to disable it. Clicking the bubble always toggles recording.

**Bottom actions**

- Settings, History, Export All, and Close app are available in the Settings panel; the
  quick-history popover footer has Settings, History, and Close app.
- Export All writes the full transcript history to one timestamped file
  (`dictation_export_YYYYMMDD_HHMMSS.txt` or `.md`) in the Save Location.

## Privacy

Local Dictation Bubble is local-only by design.

- Transcript text is **not** written to logs unless you set `LOG_TRANSCRIPT_TEXT = True`
  in `config.py`. Transcript history is kept locally in `transcript_history.json`.

- Audio is captured locally.
- Transcription runs locally.
- Transcript history is stored locally.
- No OpenAI API calls are used.
- No cloud speech APIs are used.
- No telemetry is sent.

## Development Checks

Run tests:

```powershell
cd C:\local-dictation
.\.venv\Scripts\python.exe -B -m unittest test_bubble_dictate.py -v
```

Run syntax checks:

```powershell
cd C:\local-dictation
.\.venv\Scripts\python.exe -B -c "from pathlib import Path; files=sorted(Path('.').glob('*.py')); [compile(path.read_text(encoding='utf-8'), str(path), 'exec') for path in files]; print('syntax ok:', ', '.join(str(path) for path in files))"
```

Check imports:

```powershell
cd C:\local-dictation
.\.venv\Scripts\python.exe -B -c "import config; import bubble_dictate; print('imports ok')"
```

## Search Terms

Offline Windows dictation, local speech to text, faster-whisper dictation, Whisper voice typing, CUDA transcription, GPU speech recognition, local clipboard dictation, Windows accessibility dictation, Python Tkinter dictation bubble, privacy-first voice typing.
