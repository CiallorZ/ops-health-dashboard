[CmdletBinding()]
param(
    [int]$Port = 8080,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runScript = Join-Path $PSScriptRoot "run-server.ps1"
$updateScript = Join-Path $PSScriptRoot "update.ps1"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Ops Health Dashboard.lnk"
$updateShortcutPath = Join-Path $startup "Ops Health Dashboard Update.lnk"

if (-not (Test-Path -LiteralPath $runScript)) {
    throw "run-server.ps1 not found: $runScript"
}
if (-not (Test-Path -LiteralPath $updateScript)) {
    throw "update.ps1 not found: $updateScript"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = (Get-Command powershell.exe -ErrorAction Stop).Source
$shortcut.Arguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runScript`" -Port $Port"
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7
$shortcut.Description = "Start Sentinel ops-health-dashboard"

$updateShortcut = $shell.CreateShortcut($updateShortcutPath)
$updateShortcut.TargetPath = (Get-Command powershell.exe -ErrorAction Stop).Source
$updateShortcut.Arguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$updateScript`""
$updateShortcut.WorkingDirectory = $root
$updateShortcut.WindowStyle = 7
$updateShortcut.Description = "Check for and verify Sentinel updates"

if ($DryRun) {
    Write-Output "Dry run: would create $shortcutPath"
    Write-Output "Target: $($shortcut.TargetPath) $($shortcut.Arguments)"
    Write-Output "Dry run: would create $updateShortcutPath"
    Write-Output "Target: $($updateShortcut.TargetPath) $($updateShortcut.Arguments)"
    exit 0
}

$shortcut.Save()
Write-Output "Installed user startup shortcut: $shortcutPath"
$updateShortcut.Save()
Write-Output "Installed user startup shortcut: $updateShortcutPath"
