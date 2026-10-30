@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH.
    echo Install Python 3.10 or newer, then run this launcher again.
    echo You can also use the Python Launcher command: py -3.12 run.py
    pause
    exit /b 1
)
python run.py
if errorlevel 1 pause
endlocal
