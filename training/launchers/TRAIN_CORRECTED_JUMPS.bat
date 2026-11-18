@echo off
setlocal
cd /d "%~dp0..\.."
echo ==============================================
echo Minecraft Jump Calibration v0.7.11
 echo 100 fresh in-game trials EACH for gap 1, 2 and 3.
echo Landing platform scoring plus braking comparisons.
echo The older 5050 trials are preserved, not deleted.
echo Join 127.0.0.1:25566 once as authenticated player.
echo ==============================================
where python >nul 2>&1
if not errorlevel 1 (
  python -m quickstart.training_server --skills jump --episodes 100 --interleave
) else (
  py -3 -m quickstart.training_server --skills jump --episodes 100 --interleave
)
if errorlevel 1 pause
endlocal
