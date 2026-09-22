param([ValidateSet('api', 'worker', 'web')][string]$Service = 'api')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ($Service -eq 'web') {
    Push-Location (Join-Path $ProjectRoot 'frontend')
    try { & npm.cmd run dev; exit $LASTEXITCODE } finally { Pop-Location }
}
$Python = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw '請先依 README 建立 .venv 並安裝 backend/requirements.txt。' }
Push-Location (Join-Path $ProjectRoot 'backend')
try {
    if ($Service -eq 'api') { & $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 }
    else { & $Python -m app.worker }
    exit $LASTEXITCODE
} finally { Pop-Location }
