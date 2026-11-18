@echo off
setlocal
cd /d "%~dp0..\.."
if "%~1"=="" (
    echo Drag downloaded Mine AI MCP transcript.jsonl onto this launcher.
    echo Source: https://huggingface.co/datasets/aibengineering/beat-the-game-minecraft
    pause
    exit /b 1
)
where python >nul 2>&1
if not errorlevel 1 (
    python -m quickstart.strategy_import --input "%~1"
) else (
    py -3 -m quickstart.strategy_import --input "%~1"
)
if errorlevel 1 pause
endlocal
