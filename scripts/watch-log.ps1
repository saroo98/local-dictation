param(
    [switch]$Once,
    [int]$Tail = 120
)

$ProjectDir = "C:\local-dictation"
$LogPath = Join-Path $ProjectDir "dictation_debug.log"
$SessionDir = Join-Path $ProjectDir "logs"

Write-Output "Local Dictation live log"
Write-Output "Aggregate: $LogPath"

if (Test-Path -LiteralPath $SessionDir) {
    $LatestSession = Get-ChildItem -LiteralPath $SessionDir -Filter "dictation_*.log" -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($LatestSession) {
        Write-Output "Latest session: $($LatestSession.FullName)"
    }
}

Write-Output ""

if (-not (Test-Path -LiteralPath $LogPath)) {
    Write-Output "Log file does not exist yet. Start Local Dictation first."
    exit 0
}

if ($Once) {
    Get-Content -LiteralPath $LogPath -Tail $Tail
} else {
    Get-Content -LiteralPath $LogPath -Tail $Tail -Wait
}
