[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$startup = [Environment]::GetFolderPath("Startup")
foreach ($name in @("Ops Health Dashboard.lnk", "Ops Health Dashboard Update.lnk")) {
    $shortcutPath = Join-Path $startup $name
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
        Write-Output "Removed user startup shortcut: $shortcutPath"
    } else {
        Write-Output "Startup shortcut not present: $name"
    }
}
