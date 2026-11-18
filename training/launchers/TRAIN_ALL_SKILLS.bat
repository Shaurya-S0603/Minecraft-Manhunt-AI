@echo off
setlocal
cd /d "%~dp0..\.."
echo [TRAIN] ALL - default 1000 episodes per selected stage.
echo [TRAIN] One authenticated login required at 127.0.0.1:25566.
echo [TRAIN] Press Ctrl+C to stop safely.
where python >nul 2>&1
if not errorlevel 1 (
  python -m quickstart.training_server --skills all --episodes 1000 --interleave
) else (
  py -3 -m quickstart.training_server --skills all --episodes 1000 --interleave
)
if errorlevel 1 pause
endlocal
