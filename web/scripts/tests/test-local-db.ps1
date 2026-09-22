# Windows-only isolated tests. No installed PostgreSQL executable or live database is used.
# Run from the project root: pwsh -NoProfile -File scripts/tests/test-local-db.ps1
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$SourceScript = Join-Path $ProjectRoot 'scripts/local-db.ps1'
$StartScript = Join-Path $ProjectRoot 'scripts/start-local.ps1'
$TempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar)
$TestRoot = Join-Path $TempParent ('tide-db-test-' + [Guid]::NewGuid().ToString('N'))
$PreviousPassword = $env:PGPASSWORD
$Passed = 0
function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
try {
    foreach ($ParseTarget in @($SourceScript, $StartScript)) {
        $ParseTokens = $null
        $ParseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($ParseTarget, [ref]$ParseTokens, [ref]$ParseErrors) | Out-Null
        Assert-True ($ParseErrors.Count -eq 0) ('Script must parse: ' + [IO.Path]::GetFileName($ParseTarget))
    }
    Write-Host ('PASS: both launch scripts parse on PowerShell ' + $PSVersionTable.PSVersion)
    New-Item -ItemType Directory -Path $TestRoot | Out-Null
    $Compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if (-not (Test-Path -LiteralPath $Compiler)) { throw 'These isolated Windows tests need the .NET Framework C# compiler.' }
    $StubSource = Join-Path $TestRoot 'Stub.cs'
    @'
using System;
using System.IO;
class Stub {
    static string Argument(string[] args, string name) {
        for (int i = 0; i + 1 < args.Length; ++i) if (args[i] == name) return args[i + 1];
        return "";
    }
    static int Main(string[] args) {
        string bin = AppDomain.CurrentDomain.BaseDirectory;
        string mode = File.ReadAllText(Path.Combine(bin, "scenario.txt"));
        string data = File.ReadAllText(Path.Combine(bin, "data-path.txt"));
        string tool = Path.GetFileNameWithoutExtension(Environment.GetCommandLineArgs()[0]);
        File.AppendAllText(Path.Combine(bin, "calls.log"), tool + " " + String.Join(" ", args) + Environment.NewLine);
        if (tool == "initdb") {
            if (mode == "fail-init") return 1;
            Directory.CreateDirectory(data);
            File.WriteAllText(Path.Combine(data, "PG_VERSION"), "18");
            return 0;
        }
        if (tool == "pg_ctl") {
            foreach (string arg in args) {
                if (arg == "status") return File.Exists(Path.Combine(data, "postmaster.pid")) ? 0 : 3;
                if (arg == "start") {
                    if (mode == "fail-start") return 1;
                    File.WriteAllText(Path.Combine(data, "postmaster.pid"), "100000\n" + data + "\n0\n55432\n");
                    return 0;
                }
            }
            return 97; // Never support stop or contact a real server.
        }
        if (tool == "psql") {
            if (mode == "fail-connect") return 1;
            string sql = args[args.Length - 1];
            if (sql == "SHOW data_directory") {
                Console.WriteLine(mode == "wrong-cluster" ? Path.Combine(bin, "other-cluster") : data);
                return 0;
            }
            if (sql.Contains("pg_database")) {
                if (mode != "fail-createdb" && mode != "success-create") Console.WriteLine("1");
                return 0;
            }
            if (sql == "SELECT 1" && Argument(args, "-d") == "tide") {
                if (mode == "fail-ready") return 1;
                Console.WriteLine("1");
                return 0;
            }
        }
        if (tool == "createdb") return mode == "fail-createdb" ? 1 : 0;
        return 98;
    }
}
'@ | Set-Content -LiteralPath $StubSource -Encoding UTF8
    $StubExe = Join-Path $TestRoot 'Stub.exe'
    & $Compiler /nologo /target:exe "/out:$StubExe" $StubSource
    Assert-True ($LASTEXITCODE -eq 0) 'Failed to compile isolated fake database tools.'
    $Cases = @(
        @{ Name='initialization failure'; Mode='fail-init'; Fresh=$true; Expected=$false },
        @{ Name='start failure'; Mode='fail-start'; Stopped=$true; Expected=$false },
        @{ Name='connection failure'; Mode='fail-connect'; Expected=$false },
        @{ Name='database creation failure'; Mode='fail-createdb'; Expected=$false },
        @{ Name='target database readiness failure'; Mode='fail-ready'; Expected=$false },
        @{ Name='running cluster has different port'; Mode='success'; Port=55499; Expected=$false },
        @{ Name='listener belongs to another cluster'; Mode='wrong-cluster'; Expected=$false },
        @{ Name='invalid low port'; Mode='success'; Port=0; Expected=$false },
        @{ Name='invalid high port'; Mode='success'; Port=65536; Expected=$false },
        @{ Name='atomic publication failure'; Mode='success'; LockEnv=$true; Expected=$false },
        @{ Name='existing database success and encoded password'; Mode='success'; Expected=$true },
        @{ Name='stopped database starts and creates target'; Mode='success-create'; Stopped=$true; Expected=$true },
        @{ Name='fresh initialization creates new env'; Mode='success'; Fresh=$true; NewEnv=$true; Expected=$true }
    )
    foreach ($Case in $Cases) {
        $CaseRoot = Join-Path $TestRoot ('case with spaces ' + $Passed)
        $Scripts = Join-Path $CaseRoot 'scripts'
        $Bin = Join-Path $CaseRoot 'fake-bin'
        $Data = Join-Path $CaseRoot '.local/postgres'
        New-Item -ItemType Directory -Path $Scripts,$Bin,$Data -Force | Out-Null
        $Script = Join-Path $Scripts 'local-db.ps1'
        Copy-Item -LiteralPath $SourceScript -Destination $Script
        foreach ($Tool in @('initdb','pg_ctl','psql','createdb')) { Copy-Item -LiteralPath $StubExe -Destination (Join-Path $Bin "$Tool.exe") }
        [IO.File]::WriteAllText((Join-Path $Bin 'scenario.txt'), $Case.Mode)
        [IO.File]::WriteAllText((Join-Path $Bin 'data-path.txt'), $Data)
        $Password = 'fake@test:pw/#%$quote''slash\'
        [IO.File]::WriteAllText((Join-Path $CaseRoot '.local/pg-password.txt'), $Password)
        if (-not $Case.Fresh) { [IO.File]::WriteAllText((Join-Path $Data 'PG_VERSION'), '18') }
        if (-not $Case.Fresh -and -not $Case.Stopped) { [IO.File]::WriteAllText((Join-Path $Data 'postmaster.pid'), "100000`n$Data`n0`n55432`n") }
        $Before = "# Keep unrelated values`r`nANALYZER_ROOT=../unchanged`r`nCUSTOM_VALUE='keep # literal'`r`nDATABASE_URL=postgresql+psycopg://tide:old-test-value@127.0.0.1:55432/tide`r`nPOSTGRES_PASSWORD=old-test-value`r`nPOSTGRES_PORT=55432`r`n"
        $EnvPath = Join-Path $CaseRoot '.env'
        [IO.File]::WriteAllText((Join-Path $CaseRoot '.env.example'), $Before)
        if (-not $Case.NewEnv) { [IO.File]::WriteAllText($EnvPath, $Before) }
        $RequestedPort = if ($Case.ContainsKey('Port')) { $Case.Port } else { 55432 }
        $env:PGPASSWORD = 'test-parent-password-must-survive'
        $Succeeded = $false
        $Failure = ''
        $Handle = $null
        try {
            if ($Case.LockEnv) { $Handle = [IO.File]::Open($EnvPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read) }
            try { & $Script -PgBin $Bin -Port $RequestedPort 6>$null; $Succeeded = $true }
            catch { $Failure = $_.Exception.Message }
        } finally { if ($Handle) { $Handle.Dispose() } }
        Assert-True ($Succeeded -eq $Case.Expected) ($Case.Name + ': unexpected success/failure: ' + $Failure)
        Assert-True ($env:PGPASSWORD -eq 'test-parent-password-must-survive') ($Case.Name + ': parent password environment changed')
        $After = if ([IO.File]::Exists($EnvPath)) { [IO.File]::ReadAllText($EnvPath) } else { '' }
        if (-not $Case.Expected) {
            Assert-True ($After -ceq $Before) ($Case.Name + ': original env was modified on failure')
        } else {
            $ExpectedPassword = [IO.File]::ReadAllText((Join-Path $CaseRoot '.local/pg-password.txt'))
            $ExpectedUrl = 'DATABASE_URL=postgresql+psycopg://tide:' + [Uri]::EscapeDataString($ExpectedPassword) + '@127.0.0.1:55432/tide'
            Assert-True ($After.Contains($ExpectedUrl)) ($Case.Name + ': password was not URL encoded correctly')
            Assert-True ($After.Contains('ANALYZER_ROOT=../unchanged') -and $After.Contains("CUSTOM_VALUE='keep # literal'")) ($Case.Name + ': unrelated environment fields changed')
            Assert-True ([regex]::Matches($After, '(?m)^DATABASE_URL=').Count -eq 1) ($Case.Name + ': duplicate database URL')
            Assert-True (-not $After.Contains('old-test-value')) ($Case.Name + ': stale database setting remains')
        }
        $Leftovers = @(Get-ChildItem -LiteralPath $CaseRoot -Filter '.env.*.tmp' -File)
        Assert-True ($Leftovers.Count -eq 0) ($Case.Name + ': temporary credential file remains')
        $CallsPath = Join-Path $Bin 'calls.log'
        $Calls = if ([IO.File]::Exists($CallsPath)) { [IO.File]::ReadAllText($CallsPath) } else { '' }
        Assert-True (-not $Calls.Contains(' stop')) ($Case.Name + ': attempted to stop a cluster')
        if ($Case.Name -eq 'running cluster has different port') {
            Assert-True (-not $Calls.Contains('psql')) 'Different-port case contacted an unrelated listener.'
        }
        if ($Case.Name.StartsWith('invalid')) { Assert-True ($Calls -eq '') 'Invalid port invoked database tools.' }
        $Passed++
        Write-Host ('PASS: ' + $Case.Name)
    }
} finally {
    $env:PGPASSWORD = $PreviousPassword
    $ResolvedTestRoot = [IO.Path]::GetFullPath($TestRoot)
    if (-not $ResolvedTestRoot.StartsWith($TempParent + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or -not ([IO.Path]::GetFileName($ResolvedTestRoot)).StartsWith('tide-db-test-')) { throw 'Refusing cleanup outside the isolated test directory.' }
    if (Test-Path -LiteralPath $ResolvedTestRoot) { Remove-Item -LiteralPath $ResolvedTestRoot -Recurse -Force }
}
Write-Host "$Passed isolated local-db tests passed; no live PostgreSQL was used."
exit 0
