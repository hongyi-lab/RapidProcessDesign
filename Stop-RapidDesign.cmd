@echo off
where pwsh.exe >nul 2>nul
if errorlevel 1 (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-rapid-local.ps1"
) else (
  pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-rapid-local.ps1"
)
if errorlevel 1 (
  echo.
  echo Rapid Design failed to stop. Check the message above.
  pause
)
