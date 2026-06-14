$DesktopDir = [Environment]::GetFolderPath("Desktop")
$ProgramsDir = [Environment]::GetFolderPath("Programs")
$StartMenuDir = Join-Path $ProgramsDir "Local Dictation"
$StartupDir = [Environment]::GetFolderPath("Startup")

$ShortcutPaths = @(
    (Join-Path $DesktopDir "Local Dictation Toggle.lnk"),
    (Join-Path $DesktopDir "Local Dictation History.lnk"),
    (Join-Path $DesktopDir "Local Dictation Debug Log.lnk"),
    (Join-Path $StartMenuDir "Local Dictation Toggle.lnk"),
    (Join-Path $StartMenuDir "Local Dictation History.lnk"),
    (Join-Path $StartMenuDir "Local Dictation Debug Log.lnk"),
    (Join-Path $StartupDir "Local Dictation Resident.lnk")
)

foreach ($ShortcutPath in $ShortcutPaths) {
    if (Test-Path -LiteralPath $ShortcutPath) {
        Remove-Item -LiteralPath $ShortcutPath -Force
        Write-Output "Removed shortcut: $ShortcutPath"
    }
}

if ((Test-Path -LiteralPath $StartMenuDir) -and -not (Get-ChildItem -LiteralPath $StartMenuDir -Force)) {
    Remove-Item -LiteralPath $StartMenuDir -Force
    Write-Output "Removed folder: $StartMenuDir"
}
