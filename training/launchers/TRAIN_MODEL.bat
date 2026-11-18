@echo off
setlocal
cd /d "%~dp0..\.."
echo [MODEL] Refit jump, swim and climb movement policies from real attempts.
where python >nul 2>&1
if not errorlevel 1 (
  python -m quickstart.train_policy
) else (
  py -3 -m quickstart.train_policy
)
if errorlevel 1 pause
endlocal
