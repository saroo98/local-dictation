@echo off
cd /d C:\local-dictation
if exist .venv\Scripts\pythonw.exe (
    start "" .venv\Scripts\pythonw.exe bubble_dictate.py
) else (
    call .venv\Scripts\activate
    python bubble_dictate.py
    pause
)
