@echo off
cd /d "%~dp0.."
where python >nul 2>&1
if not errorlevel 1 (
    python -m quickstart.launch --reset-world
) else (
    py -3 -m quickstart.launch --reset-world
)
pause
