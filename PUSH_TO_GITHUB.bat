@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create-and-push-repository.ps1"
echo.
pause
endlocal
