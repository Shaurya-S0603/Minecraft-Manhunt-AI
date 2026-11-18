@echo off
cd /d "%~dp0"
set "PYTHONPATH=ai-controller\src;seed-manager\src;match-supervisor\src"
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
) else (
    set "PYTHON_CMD=py -3"
)
%PYTHON_CMD% -m unittest discover -s quickstart/tests -v
if errorlevel 1 goto done
%PYTHON_CMD% -c "import pytest" 2>nul
if errorlevel 1 (
    echo [INFO] pytest not installed; skipping original regression suite.
) else (
    %PYTHON_CMD% -m pytest tests/unit tests/contract -q
)
:done
pause
