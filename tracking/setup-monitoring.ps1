# Run once on a new machine. Does not replace any detector/regression weights.
$ErrorActionPreference = "Stop"
Push-Location -LiteralPath $PSScriptRoot
try {
    $taskPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $taskPython)) {
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            uv venv --python 3.12 .venv
        } else {
            py -3.12 -m venv .venv
        }
        if ($LASTEXITCODE -ne 0) { throw "Unable to create Python 3.12 environment." }
    }
    & $taskPython -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw "Unable to initialize pip." }
    & $taskPython -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
    # Albumentations installs headless cv2, which overwrites the desktop GUI build.
    # Keep the GUI build for the existing --preview workflow.
    & $taskPython -m pip uninstall -y opencv-python-headless
    if ($LASTEXITCODE -ne 0) { throw "Unable to remove headless OpenCV." }
    & $taskPython -m pip install --force-reinstall --no-deps "opencv-python>=4.10,<5"
    if ($LASTEXITCODE -ne 0) { throw "Unable to restore desktop OpenCV." }
    Write-Output "Environment ready. Run .\run-monitoring.ps1 -MaxFrames 30"
} finally {
    Pop-Location
}
