param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'start',
    [string]$PgBin = '',
    [ValidateRange(1, 65535)][int]$Port = 55432
)
$ErrorActionPreference = 'Stop'
# Expected native failures (for example, a stopped cluster's status) are checked below.
$PSNativeCommandUseErrorActionPreference = $false
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LocalDir = Join-Path $ProjectRoot '.local'
$DataDir = Join-Path $LocalDir 'postgres'
if (-not $PgBin) {
    $Installed = Get-Command pg_ctl.exe -ErrorAction SilentlyContinue
    if ($Installed) { $PgBin = Split-Path -Parent $Installed.Source }
    else {
        $Versions = Get-ChildItem -LiteralPath (Join-Path $env:ProgramFiles 'PostgreSQL') -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        foreach ($Version in $Versions) {
            $Candidate = Join-Path $Version.FullName 'bin'
            if (Test-Path -LiteralPath (Join-Path $Candidate 'pg_ctl.exe')) { $PgBin = $Candidate; break }
        }
    }
}
if (-not $PgBin) { throw '找不到 PostgreSQL。請安裝 PostgreSQL 或使用 README 的 Docker Compose 步驟。' }
$Control = Join-Path $PgBin 'pg_ctl.exe'
if ($Action -ne 'start') {
    if (-not (Test-Path -LiteralPath (Join-Path $DataDir 'PG_VERSION'))) { throw '此專案尚未初始化本機資料庫。' }
    & $Control -D $DataDir $Action
    exit $LASTEXITCODE
}
New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null
$PasswordFile = Join-Path $LocalDir 'pg-password.txt'
if (-not (Test-Path -LiteralPath (Join-Path $DataDir 'PG_VERSION'))) {
    $PasswordBytes = New-Object byte[] 24
    $Generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Generator.GetBytes($PasswordBytes) } finally { $Generator.Dispose() }
    $DbPassword = [Convert]::ToBase64String($PasswordBytes).Replace('+','a').Replace('/','b').TrimEnd('=')
    [IO.File]::WriteAllText($PasswordFile, $DbPassword)
    & (Join-Path $PgBin 'initdb.exe') -D $DataDir -U tide -E UTF8 --locale=C --auth=scram-sha-256 "--pwfile=$PasswordFile"
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL 初始化失敗。' }
}
if (-not (Test-Path -LiteralPath $PasswordFile)) { throw '找不到此專案資料庫的密碼紀錄，請使用原先的資料庫設定。' }
$DbPassword = [IO.File]::ReadAllText($PasswordFile).TrimEnd([char[]]"`r`n")
if (-not $DbPassword -or $DbPassword.IndexOfAny([char[]]"`r`n`0") -ge 0) { throw '資料庫密碼紀錄必須是非空白的單行密碼。' }
$EnvPath = Join-Path $ProjectRoot '.env'
$EnvText = if (Test-Path -LiteralPath $EnvPath) { [IO.File]::ReadAllText($EnvPath) } else { [IO.File]::ReadAllText((Join-Path $ProjectRoot '.env.example')) }
foreach ($Key in @('DATABASE_URL', 'POSTGRES_PASSWORD', 'POSTGRES_PORT')) {
    $EnvText = [regex]::Replace($EnvText, "(?m)^[ \t]*(?:export[ \t]+)?$Key[ \t]*=.*\r?\n?", '')
}
$UrlPassword = [Uri]::EscapeDataString($DbPassword)
$DotenvPassword = $DbPassword.Replace('\', '\\').Replace("'", "\'")
$EnvText = $EnvText.TrimEnd([char[]]"`r`n") + "`nDATABASE_URL=postgresql+psycopg://tide:${UrlPassword}@127.0.0.1:${Port}/tide`nPOSTGRES_PASSWORD='$DotenvPassword'`nPOSTGRES_PORT=$Port`n"
& $Control -D $DataDir status *> $null
if ($LASTEXITCODE -ne 0) {
    & $Control -D $DataDir -l (Join-Path $LocalDir 'postgres.log') -o "-h 127.0.0.1 -p $Port" -w start
    if ($LASTEXITCODE -ne 0) { throw '資料庫啟動失敗，請查看 .local/postgres.log，並確認連接埠沒有被占用。' }
}
# Check the running cluster's own port before contacting any listener at the requested port.
$PidPath = Join-Path $DataDir 'postmaster.pid'
if (-not (Test-Path -LiteralPath $PidPath)) { throw '無法確認本專案資料庫的執行埠；現有 .env 保持不變。' }
$PidLines = [IO.File]::ReadAllLines($PidPath)
$RunningPort = 0
if ($PidLines.Length -lt 4 -or -not [int]::TryParse($PidLines[3], [ref]$RunningPort)) { throw '無法讀取本專案資料庫的執行埠；現有 .env 保持不變。' }
if ($RunningPort -ne $Port) { throw "本專案資料庫已在 $RunningPort 執行，與指定埠 $Port 不同；請使用原埠，或先自行停止本專案資料庫後再改埠。現有 .env 保持不變。" }
$PreviousPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = $DbPassword
    $ConnectedDir = & (Join-Path $PgBin 'psql.exe') -X -w -h 127.0.0.1 -p $Port -U tide -d postgres -tAc 'SHOW data_directory'
    if ($LASTEXITCODE -ne 0) { throw '資料庫連線失敗。' }
    $ConnectedDir = ([string]$ConnectedDir).Trim()
    if (-not $ConnectedDir -or -not [StringComparer]::OrdinalIgnoreCase.Equals([IO.Path]::GetFullPath($ConnectedDir), [IO.Path]::GetFullPath($DataDir))) {
        throw '指定埠連到其他資料庫叢集，已停止設定；現有 .env 保持不變。'
    }
    $Exists = & (Join-Path $PgBin 'psql.exe') -X -w -h 127.0.0.1 -p $Port -U tide -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='tide'"
    if ($LASTEXITCODE -ne 0) { throw '資料庫連線失敗。' }
    if ($Exists -ne '1') {
        & (Join-Path $PgBin 'createdb.exe') -w -h 127.0.0.1 -p $Port -U tide tide
        if ($LASTEXITCODE -ne 0) { throw '建立 tide 資料庫失敗。' }
    }
    & (Join-Path $PgBin 'psql.exe') -X -w -h 127.0.0.1 -p $Port -U tide -d tide -tAc 'SELECT 1' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'tide 資料庫尚未就緒；現有 .env 保持不變。' }
} finally { $env:PGPASSWORD = $PreviousPassword }
# Publish on the same volume only after every database check succeeds. Never delete the original.
$TempEnv = Join-Path $ProjectRoot ('.env.' + [Guid]::NewGuid().ToString('N') + '.tmp')
try {
    [IO.File]::WriteAllText($TempEnv, $EnvText, (New-Object Text.UTF8Encoding($false)))
    if ([IO.File]::Exists($EnvPath)) { [IO.File]::Replace($TempEnv, $EnvPath, [System.Management.Automation.Language.NullString]::Value) }
    else { [IO.File]::Move($TempEnv, $EnvPath) }
} finally {
    if ([IO.File]::Exists($TempEnv)) { Remove-Item -LiteralPath $TempEnv -Force }
}
Write-Host "本專案 PostgreSQL 已就緒：127.0.0.1:$Port；連線設定已寫入 .env。"
