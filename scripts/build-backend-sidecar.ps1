$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

$PythonCandidates = @(
    "C:\local-dictation-tauri\.venv\Scripts\python.exe",
    "C:\local-dictation\.venv\Scripts\python.exe"
)

$Python = $PythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Python) {
    throw "Could not find Python in C:\local-dictation-tauri\.venv or C:\local-dictation\.venv."
}

try {
    $PyInstallerVersion = & $Python -m PyInstaller --version
} catch {
    throw "PyInstaller is not installed. Run: & '$Python' -m pip install -r '$RepoRoot\requirements-build.txt'"
}

$Rustc = Get-Command rustc -ErrorAction SilentlyContinue
if (-not $Rustc) {
    $CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
    if (Test-Path -LiteralPath (Join-Path $CargoBin "rustc.exe")) {
        $env:PATH = "$CargoBin;$env:PATH"
        $Rustc = Get-Command rustc -ErrorAction SilentlyContinue
    }
}
if (-not $Rustc) {
    throw "rustc is required to determine the Tauri sidecar target triple. Install Rust or add it to PATH."
}

$TargetTriple = (& rustc --print host-tuple).Trim()
if (-not $TargetTriple) {
    throw "rustc did not return a host target triple."
}

$Source = Join-Path $RepoRoot "bubble_dictate.py"
$Icon = Join-Path $RepoRoot "desktop\src-tauri\icons\icon.ico"
$BuildRoot = Join-Path $RepoRoot "build\pyinstaller-backend"
$DistDir = Join-Path $BuildRoot "dist"
$WorkDir = Join-Path $BuildRoot "work"
$SpecDir = Join-Path $BuildRoot "spec"
$BinaryDir = Join-Path $RepoRoot "desktop\src-tauri\binaries"
$BuiltExe = Join-Path $DistDir "local-dictation-backend.exe"
$SidecarExe = Join-Path $BinaryDir "local-dictation-backend-$TargetTriple.exe"

if (-not (Test-Path -LiteralPath $Source)) {
    throw "Backend source not found: $Source"
}
if (-not (Test-Path -LiteralPath $Icon)) {
    throw "Icon not found: $Icon"
}

if (Test-Path -LiteralPath $BuildRoot) {
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $BinaryDir, $DistDir, $WorkDir, $SpecDir | Out-Null

Write-Host "Using Python: $Python"
Write-Host "Using PyInstaller: $PyInstallerVersion"
Write-Host "Target triple: $TargetTriple"

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name local-dictation-backend `
    --icon $Icon `
    --distpath $DistDir `
    --workpath $WorkDir `
    --specpath $SpecDir `
    $Source

if (-not (Test-Path -LiteralPath $BuiltExe)) {
    throw "PyInstaller did not produce expected executable: $BuiltExe"
}

Copy-Item -LiteralPath $BuiltExe -Destination $SidecarExe -Force
Write-Host "Backend sidecar written to: $SidecarExe"
