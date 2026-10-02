@echo off
cd /d "%~dp0.."
if exist .venv\Scripts\pythonw.exe (
    start "" ".venv\Scripts\pythonw.exe" "backend\bubble_dictate.py"
) else (
    echo Create .venv in the repository root and install backend requirements first.
    exit /b 1
)
