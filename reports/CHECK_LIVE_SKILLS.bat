@echo off
setlocal
cd /d "%~dp0.."
echo [CHECK] Read-only inspection of learned Manhunt movement settings.
where python >nul 2>&1
if not errorlevel 1 (
  python -m quickstart.live_skill_status
) else (
  py -3 -m quickstart.live_skill_status
)
pause
endlocal
