@echo off
setlocal
cd /d "%~dp0"

where python.exe >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required.
  echo Download it from https://www.python.org/downloads/
  pause
  exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-server.ps1" -Port 8080
if errorlevel 1 (
  echo Sentinel could not start. Review data\logs\server-error.log.
  pause
  exit /b 1
)

start "" "http://127.0.0.1:8080"
echo Sentinel is running at http://127.0.0.1:8080
timeout /t 2 >nul
