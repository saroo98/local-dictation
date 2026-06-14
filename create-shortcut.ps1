$ProjectDir = "C:\local-dictation"
$PythonwPath = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$ScriptPath = Join-Path $ProjectDir "bubble_dictate.py"
$WatchLogPath = Join-Path $ProjectDir "watch-log.ps1"
$PowerShellPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$DesktopDir = [Environment]::GetFolderPath("Desktop")
$ProgramsDir = [Environment]::GetFolderPath("Programs")
$StartMenuDir = Join-Path $ProgramsDir "Local Dictation"
$StartupDir = [Environment]::GetFolderPath("Startup")

if (-not (Test-Path -LiteralPath $PythonwPath)) {
    throw "pythonw.exe not found at $PythonwPath"
}

if (-not (Test-Path -LiteralPath $ScriptPath)) {
    throw "bubble_dictate.py not found at $ScriptPath"
}

if (-not (Test-Path -LiteralPath $WatchLogPath)) {
    throw "watch-log.ps1 not found at $WatchLogPath"
}

New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null

function New-LocalDictationShortcut {
    param(
        [Parameter(Mandatory = $true)][string]$ShortcutPath,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $Parent = Split-Path -Parent $ShortcutPath
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $PythonwPath
    $Shortcut.Arguments = "`"$ScriptPath`" $Arguments"
    $Shortcut.WorkingDirectory = $ProjectDir
    $Shortcut.Description = $Description
    $Shortcut.IconLocation = "$PythonwPath,0"
    $Shortcut.Save()

    Write-Output "Created shortcut: $ShortcutPath"
}

function New-LocalDictationLogShortcut {
    param(
        [Parameter(Mandatory = $true)][string]$ShortcutPath
    )

    $Parent = Split-Path -Parent $ShortcutPath
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $PowerShellPath
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$WatchLogPath`""
    $Shortcut.WorkingDirectory = $ProjectDir
    $Shortcut.Description = "Watch Local Dictation diagnostic log"
    $Shortcut.IconLocation = "$PowerShellPath,0"
    $Shortcut.Save()

    Write-Output "Created shortcut: $ShortcutPath"
}

New-LocalDictationShortcut `
    -ShortcutPath (Join-Path $DesktopDir "Local Dictation Toggle.lnk") `
    -Arguments "--toggle-record" `
    -Description "Toggle local dictation recording"

New-LocalDictationShortcut `
    -ShortcutPath (Join-Path $DesktopDir "Local Dictation History.lnk") `
    -Arguments "--show-history" `
    -Description "Show local dictation history"

New-LocalDictationShortcut `
    -ShortcutPath (Join-Path $StartMenuDir "Local Dictation Toggle.lnk") `
    -Arguments "--toggle-record" `
    -Description "Toggle local dictation recording"

New-LocalDictationShortcut `
    -ShortcutPath (Join-Path $StartMenuDir "Local Dictation History.lnk") `
    -Arguments "--show-history" `
    -Description "Show local dictation history"

New-LocalDictationLogShortcut `
    -ShortcutPath (Join-Path $DesktopDir "Local Dictation Debug Log.lnk")

New-LocalDictationLogShortcut `
    -ShortcutPath (Join-Path $StartMenuDir "Local Dictation Debug Log.lnk")

New-LocalDictationShortcut `
    -ShortcutPath (Join-Path $StartupDir "Local Dictation Resident.lnk") `
    -Arguments "--resident" `
    -Description "Start local dictation in resident mode"

Write-Output "Startup shortcut enabled by default."
Write-Output "Pin 'Local Dictation Toggle' to the taskbar for quickest use."
