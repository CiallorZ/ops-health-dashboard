[CmdletBinding()]
param(
    [string]$OutputDirectory = "dist"
)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$version = (Get-Content -Raw (Join-Path $root "VERSION")).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') {
    throw "VERSION is not a valid semantic version: $version"
}

$output = [System.IO.Path]::GetFullPath((Join-Path $root $OutputDirectory))
if (-not $output.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Output directory must stay inside the repository"
}

$packageName = "sentinel-$version"
$staging = Join-Path $output ".stage-$packageName"
$archive = Join-Path $output "$packageName.zip"
$checksum = "$archive.sha256"
$downloads = Join-Path $root "docs\downloads"

if (Test-Path -LiteralPath $staging) {
    $resolvedStaging = [System.IO.Path]::GetFullPath($staging)
    if (-not $resolvedStaging.StartsWith($output + [System.IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove staging path outside the output directory"
    }
    Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
}

New-Item -ItemType Directory -Path $staging -Force | Out-Null
$items = @(
    "AGENTS.md",
    "CHANGELOG.md",
    "Dockerfile",
    "LICENSE",
    "README.md",
    "ROADMAP.md",
    "VERSION",
    "checks.json",
    "compose.yaml",
    "dashboard",
    "docs",
    "examples",
    "monitor",
    "scripts",
    "server.py",
    "start-sentinel.cmd",
    "tests"
)

try {
    foreach ($item in $items) {
        $source = Join-Path $root $item
        if (-not (Test-Path -LiteralPath $source)) {
            throw "Release input is missing: $item"
        }
        Copy-Item -LiteralPath $source -Destination $staging -Recurse -Force
    }

    $stagedDownloads = Join-Path $staging "docs\downloads"
    if (Test-Path -LiteralPath $stagedDownloads) {
        $resolvedDownloads = [System.IO.Path]::GetFullPath($stagedDownloads)
        if (-not $resolvedDownloads.StartsWith($staging + [System.IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to remove downloads path outside staging"
        }
        Remove-Item -LiteralPath $resolvedDownloads -Recurse -Force
    }

    $generatedDirectories = Get-ChildItem -LiteralPath $staging -Recurse -Directory -Force |
        Where-Object { $_.Name -in @("__pycache__", ".pytest_cache", ".ruff_cache") } |
        Sort-Object FullName -Descending
    foreach ($directory in $generatedDirectories) {
        $resolvedDirectory = [System.IO.Path]::GetFullPath($directory.FullName)
        if (-not $resolvedDirectory.StartsWith($staging + [System.IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to remove generated path outside staging"
        }
        Remove-Item -LiteralPath $resolvedDirectory -Recurse -Force
    }
    Get-ChildItem -LiteralPath $staging -Recurse -File -Force |
        Where-Object { $_.Extension -in @(".pyc", ".pyo", ".log") } |
        Remove-Item -Force

    $install = @"
Sentinel $version - portable source package

1. Install Python 3.11 or newer.
2. Edit checks.json for your own targets.
3. Double-click start-sentinel.cmd or run: python server.py
4. Open http://127.0.0.1:8080

Docker:
  docker compose up --build -d

See README.md and docs/index.html for full installation, alerting, demo,
security, testing, and release instructions.
"@
    Set-Content -LiteralPath (Join-Path $staging "START-HERE.txt") -Value $install -Encoding utf8

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (Test-Path -LiteralPath $archive) {
        Remove-Item -LiteralPath $archive -Force
    }
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $staging,
        $archive,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )

    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $checksum -Value "$hash  $(Split-Path -Leaf $archive)" -Encoding ascii

    New-Item -ItemType Directory -Path $downloads -Force | Out-Null
    Copy-Item -LiteralPath $archive -Destination $downloads -Force
    Copy-Item -LiteralPath $checksum -Destination $downloads -Force

    Write-Output "Created $archive"
    Write-Output "SHA256 $hash"
    Write-Output "Published $(Join-Path $downloads "$packageName.zip")"
}
finally {
    if (Test-Path -LiteralPath $staging) {
        $resolvedStaging = [System.IO.Path]::GetFullPath($staging)
        if ($resolvedStaging.StartsWith($output + [System.IO.Path]::DirectorySeparatorChar)) {
            Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
        }
    }
}
