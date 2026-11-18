@echo off
setlocal
cd /d "%~dp0..\.."
echo ===========================================================
echo  MANHUNTER v8.0.2 - GENERATION-AWARE MOVEMENT CURRICULUM
echo  1000 TOTAL Minecraft trials across all five courses.
echo  Creates a new session; past training logs are NOT deleted.
echo  Every fifth attempt is reserved for same-arena validation.
echo  Old successes cannot certify live V4 movement settings.
echo  Join 127.0.0.1:25566 with your authenticated account.
echo ===========================================================
where python >nul 2>&1
if not errorlevel 1 (
  python -m quickstart.training_server --skills all --adaptive --budget 1000 --validation-every 5
) else (
  py -3 -m quickstart.training_server --skills all --adaptive --budget 1000 --validation-every 5
)
if errorlevel 1 pause
endlocal
