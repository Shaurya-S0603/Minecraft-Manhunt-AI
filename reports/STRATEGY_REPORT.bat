@echo off
setlocal
cd /d "%~dp0.."
where python >nul 2>&1
if not errorlevel 1 (
    python -m quickstart.strategy_report
) else (
    py -3 -m quickstart.strategy_report
)
pause
endlocal
