@echo off
setlocal
cd /d "%~dp0..\.."
echo [MODEL V4] Refit generation-aware policy from recorded real Minecraft episodes.
echo [MODEL V4] No original JSONL or older model checkpoint will be overwritten.
echo [MODEL V4] Old scoring versions are NOT live-certification evidence.
where python >nul 2>&1
if not errorlevel 1 (
  python -m quickstart.train_policy --v4-only
) else (
  py -3 -m quickstart.train_policy --v4-only
)
if errorlevel 1 pause
endlocal
