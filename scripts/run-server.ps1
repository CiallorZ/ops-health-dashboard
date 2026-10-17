[CmdletBinding()]
param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "data\logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logPath = Join-Path $logDir "server.log"
$errorPath = Join-Path $logDir "server-error.log"
$launcherLogPath = Join-Path $logDir "launcher.log"

foreach ($path in @($logPath, $errorPath, $launcherLogPath)) {
    if ((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -gt 5MB) {
        Move-Item -LiteralPath $path -Destination "$path.1" -Force
    }
}

$python = Get-Command python.exe -ErrorAction Stop
$pythonwPath = Join-Path $python.Source.Replace("python.exe", "") "pythonw.exe"
if (-not (Test-Path -LiteralPath $pythonwPath)) {
    throw "pythonw.exe not found next to $($python.Source)"
}

function Test-ExistingServer {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://${HostName}:${Port}/api/health" -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Write-LauncherLog {
    param([string]$Message)
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -LiteralPath $launcherLogPath -Value $line -Encoding utf8
}

if (Test-ExistingServer) {
    Write-LauncherLog "server already healthy on port $Port"
    exit 0
}

Set-Location -LiteralPath $root
$process = Start-Process -FilePath $pythonwPath `
    -ArgumentList @("server.py", "--host", $HostName, "--port", $Port) `
    -WorkingDirectory $root `
    -RedirectStandardOutput $logPath `
    -RedirectStandardError $errorPath `
    -WindowStyle Hidden `
    -PassThru

for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 250
    if ($process.HasExited) {
        Write-LauncherLog "server exited with code $($process.ExitCode)"
        exit 1
    }
    if (Test-ExistingServer) {
        Write-LauncherLog "server started pid=$($process.Id) port=$Port"
        exit 0
    }
}

throw "server did not become healthy on port $Port"
