[CmdletBinding()]
param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "data\logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logPath = Join-Path $logDir "update.log"

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding utf8
}

function Invoke-CommandSafely {
    param(
        [string]$Name,
        [string[]]$Arguments
    )
    $output = & $Name @Arguments 2>&1
    $code = $LASTEXITCODE
    if ($output) {
        $output | ForEach-Object { Write-Log $_ }
    }
    if ($code -ne 0) {
        throw "$Name exited with code $code"
    }
}

Set-Location -LiteralPath $root
if ((Get-Item -LiteralPath $logPath -ErrorAction SilentlyContinue).Length -gt 5MB) {
    Move-Item -LiteralPath $logPath -Destination "$logPath.1" -Force
}

Write-Log "starting update"
$staged = @(& git diff --cached --name-only 2>$null)
if ($LASTEXITCODE -ne 0) {
    throw "git diff failed"
}
if ($staged.Count -gt 0) {
    Write-Log "staged changes exist; refusing to auto-update"
    exit 0
}

Invoke-CommandSafely -Name "git" -Arguments @("fetch", "origin", "--prune")
$localHead = (& git rev-parse HEAD).Trim()
$remoteHead = (& git rev-parse "origin/main").Trim()
if ($localHead -eq $remoteHead) {
    Write-Log "already current at $localHead"
    exit 0
}

Invoke-CommandSafely -Name "git" -Arguments @("merge", "--ff-only", "origin/main")

if (-not $Python) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}
Invoke-CommandSafely -Name $Python -Arguments @("-m", "unittest", "discover", "-s", "tests", "-v")
Invoke-CommandSafely -Name $Python -Arguments @("-m", "compileall", "-q", "monitor", "toolbox", "server.py", "tests")
Write-Log "update verified at $remoteHead"
