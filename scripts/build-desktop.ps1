param([switch]$CpuOnly, [switch]$SkipBackend)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DesktopRoot = Join-Path $RepoRoot "desktop"
$BuildTemp = Join-Path $RepoRoot "build\desktop-temp"
$TargetRoot = Join-Path $DesktopRoot "src-tauri\target"
if ($env:CARGO_TARGET_DIR) {
    $TargetRoot = if ([IO.Path]::IsPathRooted($env:CARGO_TARGET_DIR)) {
        $env:CARGO_TARGET_DIR
    } else {
        Join-Path (Join-Path $DesktopRoot "src-tauri") $env:CARGO_TARGET_DIR
    }
}
$OwnerProfile = [Environment]::GetFolderPath("UserProfile")
$CargoCache = if ($env:CARGO_HOME) { $env:CARGO_HOME } else { Join-Path $OwnerProfile ".cargo" }
$PreviousEncodedFlags = $env:CARGO_ENCODED_RUSTFLAGS
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP

try {
    # Encoded arguments preserve paths containing spaces. Keep caller flags.
    $RustArguments = @()
    if ($PreviousEncodedFlags) {
        $RustArguments += $PreviousEncodedFlags.Split([char]31)
    } elseif ($env:RUSTFLAGS) {
        $RustArguments += @($env:RUSTFLAGS -split '\s+' | Where-Object { $_ })
    }
    $RustArguments += "--remap-path-prefix=$RepoRoot=C:\build\source"
    if ($CargoCache) {
        $RustArguments += "--remap-path-prefix=$CargoCache=C:\build\cargo-cache"
    }
    $env:CARGO_ENCODED_RUSTFLAGS = $RustArguments -join [char]31
    New-Item -ItemType Directory -Path $BuildTemp -Force | Out-Null
    $env:TEMP = $BuildTemp
    $env:TMP = $BuildTemp

    if (-not $SkipBackend) {
        & (Join-Path $PSScriptRoot "build-backend-sidecar.ps1") -CpuOnly:$CpuOnly
        if ($LASTEXITCODE -ne 0) { throw "Backend build failed." }
    }
    Push-Location -LiteralPath $DesktopRoot
    try {
        & npm.cmd run tauri -- build
        if ($LASTEXITCODE -ne 0) { throw "Desktop build failed." }
    } finally {
        Pop-Location
    }

    # Refuse to publish executables that still contain this machine's paths.
    $Needles = @($RepoRoot, $OwnerProfile) | Where-Object { $_ }
    $Executables = @(
        (Join-Path $TargetRoot "release\local-dictation-desktop.exe")
    ) + @(Get-ChildItem -LiteralPath (Join-Path $DesktopRoot "src-tauri\binaries") -Filter '*.exe' -File | ForEach-Object { $_.FullName })
    foreach ($Executable in $Executables) {
        $Bytes = [IO.File]::ReadAllBytes($Executable)
        $Text = [Text.Encoding]::UTF8.GetString($Bytes)
        $WideText = [Text.Encoding]::Unicode.GetString($Bytes)
        foreach ($Needle in $Needles) {
            foreach ($Variant in @($Needle, $Needle.Replace('\', '/'))) {
                if ($Text.IndexOf($Variant, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
                    $WideText.IndexOf($Variant, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    throw "Personal build path found in $([IO.Path]::GetFileName($Executable)). Do not publish this artifact."
                }
            }
        }
    }
    Write-Output "Desktop build and personal build-path checks passed."
} finally {
    $env:CARGO_ENCODED_RUSTFLAGS = $PreviousEncodedFlags
    $env:TEMP = $PreviousTemp
    $env:TMP = $PreviousTmp
}
