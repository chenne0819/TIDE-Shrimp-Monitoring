param(
    [string]$Video = "video\公母蝦仰拍-1.mp4",
    [int]$MaxFrames = 0,
    [switch]$Preview,
    [ValidateSet("report", "stop")]
    [string]$WaterPolicy = "report"
)
$ErrorActionPreference = "Stop"
$taskPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw "Run setup-monitoring.ps1 first to create the local Python environment."
}
$taskArgs = @("-m", "general_track.run_track", "--video", $Video,
    "--monitoring", "--water-policy", $WaterPolicy)
if ($MaxFrames -gt 0) { $taskArgs += @("--max-frames", "$MaxFrames") }
if ($Preview) { $taskArgs += "--preview" }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $taskPython @taskArgs
    if ($LASTEXITCODE -ne 0) { throw "Tracking failed (exit code $LASTEXITCODE)." }
} finally {
    Pop-Location
}
