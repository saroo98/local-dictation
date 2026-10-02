param([switch]$CpuOnly)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment missing. Create .venv in the repository root and install backend requirements."
}

try {
    $PyInstallerVersion = & $Python -m PyInstaller --version
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller version check failed." }
} catch {
    throw "PyInstaller is not installed. Run: & '$Python' -m pip install -r '$RepoRoot\backend\requirements-build.txt'"
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
if ($LASTEXITCODE -ne 0 -or -not $TargetTriple) {
    throw "rustc did not return a host target triple."
}

$BackendRoot = Join-Path $RepoRoot "backend"
$Source = Join-Path $BackendRoot "bubble_dictate.py"
$Icon = Join-Path $RepoRoot "desktop\src-tauri\icons\icon.ico"
$BuildRoot = Join-Path $RepoRoot "build\pyinstaller-backend"
$DistDir = Join-Path $BuildRoot "dist"
$WorkDir = Join-Path $BuildRoot "work"
$SpecDir = Join-Path $BuildRoot "spec"
$BinaryDir = Join-Path $RepoRoot "desktop\src-tauri\binaries"
$BuiltExe = Join-Path $DistDir "local-dictation-backend.exe"
$SidecarExe = Join-Path $BinaryDir "local-dictation-backend-$TargetTriple.exe"
$CudaDir = Join-Path $RepoRoot "build\cuda"

$PythonBits = (& $Python -c "import struct; print(struct.calcsize('P') * 8)").Trim()
if ($LASTEXITCODE -ne 0 -or $PythonBits -ne "64" -or $TargetTriple -ne "x86_64-pc-windows-msvc") {
    throw "The packaged app requires matching Windows x64 Python and Rust toolchains."
}

# CUDA is installed once as resources, outside the one-file extraction path.
New-Item -ItemType Directory -Force -Path $CudaDir | Out-Null
$ResolvedCudaDir = (Resolve-Path -LiteralPath $CudaDir).Path
$ResolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
if (-not $ResolvedCudaDir.StartsWith($ResolvedRepoRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "CUDA staging directory must stay inside the repository."
}
Get-ChildItem -LiteralPath $ResolvedCudaDir -File -Filter '*.dll' | Remove-Item -Force
if (-not $CpuOnly) {
    $NvidiaDir = (& $Python -c "import site,pathlib; paths=[pathlib.Path(p)/'nvidia' for p in site.getsitepackages()]; print(next((str(p) for p in paths if p.is_dir()),''))").Trim()
    if (-not $NvidiaDir) { throw "CUDA libraries missing. Install backend\requirements-cuda.txt or build with -CpuOnly." }
    $CudaDlls = @(Get-ChildItem -LiteralPath $NvidiaDir -Recurse -File -Filter '*.dll')
    foreach ($RequiredDll in @('cublas64_12.dll','cublasLt64_12.dll','cudnn64_9.dll','cudart64_12.dll')) {
        if ($RequiredDll -notin $CudaDlls.Name) { throw "Required CUDA library missing: $RequiredDll" }
    }
    foreach ($CudaDll in $CudaDlls) { Copy-Item -LiteralPath $CudaDll.FullName -Destination $ResolvedCudaDir -Force }
    $CudaBytes = ($CudaDlls | Measure-Object -Property Length -Sum).Sum
    Write-Host "Staged $($CudaDlls.Count) CUDA DLLs: $CudaBytes bytes (installed resources, not repeated startup extraction)."
}

if (-not (Test-Path -LiteralPath $Source)) {
    throw "Backend source not found: $Source"
}
if (-not (Test-Path -LiteralPath $Icon)) {
    throw "Icon not found: $Icon"
}

if (Test-Path -LiteralPath $BuildRoot) {
    $ResolvedBuildRoot = (Resolve-Path -LiteralPath $BuildRoot).Path
    $ResolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
    if (-not $ResolvedBuildRoot.StartsWith($ResolvedRepoRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Build directory must stay inside the repository."
    }
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
    --paths $BackendRoot `
    $Source

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed; the previous sidecar will not be replaced."
}

if (-not (Test-Path -LiteralPath $BuiltExe)) {
    throw "PyInstaller did not produce expected executable: $BuiltExe"
}

Copy-Item -LiteralPath $BuiltExe -Destination $SidecarExe -Force
Write-Host "Backend sidecar written to: $SidecarExe"
