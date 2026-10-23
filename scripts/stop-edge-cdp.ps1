param([int]$Port = 9223)

$ErrorActionPreference = "Stop"
$processes = Get-CimInstance Win32_Process -Filter "Name = 'msedge.exe'" |
    Where-Object { $_.CommandLine -like "*--remote-debugging-port=$Port*" }
foreach ($process in $processes) {
    Stop-Process -Id $process.ProcessId -Force
    Write-Output "stopped edge pid $($process.ProcessId)"
}
if (-not $processes) {
    Write-Output "no edge debugging process on port $Port"
}
