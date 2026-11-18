@echo off
cd /d "%~dp0"
where python >nul 2>&1
if not errorlevel 1 (
    python -m unittest discover -s quickstart/tests -v
) else (
    py -3 -m unittest discover -s quickstart/tests -v
)
if errorlevel 1 pause
