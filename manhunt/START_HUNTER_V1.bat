@echo off
cd /d "%~dp0.."
where python >nul 2>&1
if not errorlevel 1 (python -m quickstart.hunter_v1.cli play %*) else (py -3 -m quickstart.hunter_v1.cli play %*)
if errorlevel 1 pause
