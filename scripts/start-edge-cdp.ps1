param(
    [int]$Port = 9223,
    [string]$ProfileDir = "data\edge-cdp"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$profilePath = Join-Path $root $ProfileDir
New-Item -ItemType Directory -Force -Path $profilePath | Out-Null

$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path -LiteralPath $edge)) {
    throw "Edge executable not found: $edge"
}

Start-Process -FilePath $edge -ArgumentList @(
    "--remote-debugging-port=$Port"
    "--user-data-dir=$profilePath"
    "--no-first-run"
    "--no-default-browser-check"
    "about:blank"
) -WindowStyle Hidden

for ($attempt = 0; $attempt -lt 20; $attempt += 1) {
    Start-Sleep -Milliseconds 700
    try {
        $version = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 3
        Write-Output "CDP ready: $($version.Browser)"
        exit 0
    } catch {
        # keep waiting for the debugging endpoint
    }
}
throw "CDP endpoint did not become ready on port $Port"
