@echo off
cd /d "%~dp0.."
where python >nul 2>&1
if not errorlevel 1 (
    python -m quickstart.launch --role runner --head-start 20 --survival-seconds 180
) else (
    py -3 -m quickstart.launch --role runner --head-start 20 --survival-seconds 180
)
if errorlevel 1 pause
