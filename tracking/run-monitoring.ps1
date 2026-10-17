param(
    [string]$Config = (Join-Path $PSScriptRoot "general_track/config.toml")
)
$ErrorActionPreference = "Stop"
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw "Create the repository-root Python 3.14 .venv with tracking/setup-monitoring.ps1 before running tracking."
}
& $taskPython -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 'Tracking requires Python 3.14 in the repository-root .venv.')"
if ($LASTEXITCODE -ne 0) { throw "The repository-root tracking environment must use Python 3.14." }
$taskConfig = (Resolve-Path -LiteralPath $Config).Path
Push-Location -LiteralPath $PSScriptRoot
try {
    & $taskPython -m general_track.run_track --config $taskConfig
    if ($LASTEXITCODE -ne 0) { throw "Tracking failed (exit code $LASTEXITCODE)." }
} finally {
    Pop-Location
}
