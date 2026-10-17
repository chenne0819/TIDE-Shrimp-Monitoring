$ErrorActionPreference = "Stop"
Push-Location -LiteralPath $PSScriptRoot
try {
    $taskRoot = Split-Path -Parent $PSScriptRoot
    $taskEnvironment = Join-Path $taskRoot ".venv"
    $taskPython = Join-Path $taskEnvironment "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $taskPython)) {
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            uv venv --python 3.14 $taskEnvironment
        } else {
            py -3.14 -m venv $taskEnvironment
        }
        if ($LASTEXITCODE -ne 0) { throw "Unable to create the repository-root Python 3.14 environment." }
    }
    & $taskPython -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 'Tracking requires Python 3.14 in the repository-root .venv; the existing environment was not replaced.')"
    if ($LASTEXITCODE -ne 0) { throw "The repository-root tracking environment must use Python 3.14." }
    & $taskPython -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw "Unable to initialize pip." }
    & $taskPython -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
    & $taskPython -m pip uninstall -y albumentations albucore opencv-python-headless
    if ($LASTEXITCODE -ne 0) { throw "Unable to remove headless OpenCV." }
    & $taskPython -m pip install --force-reinstall --no-deps "opencv-python>=4.10,<5"
    if ($LASTEXITCODE -ne 0) { throw "Unable to restore desktop OpenCV." }
    & $taskPython check-gpu.py
    if ($LASTEXITCODE -ne 0) { throw "CUDA verification failed; the environment is not ready for GPU inference." }
    Write-Output "GPU environment ready. Edit general_track/config.toml, then run .\run-monitoring.ps1"
} finally {
    Pop-Location
}
