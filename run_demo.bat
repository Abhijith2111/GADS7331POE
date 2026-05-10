@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No virtual environment found.
    echo.
    echo Please double-click setup.bat first to install the project.
    echo.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo Running scripted demo (broke_bard, 4 turns, seed 1234)...
echo Prompt + dialogue logs will be written next to this file.
echo.

REM Trailing %* lets you append extra flags, e.g.
REM   run_demo.bat --persona paranoid_wizard
python -m src.main --demo --persona broke_bard --turns 4 --seed 1234 %*

if errorlevel 1 (
    echo.
    echo The demo exited with an error. See the messages above.
    pause
)
endlocal
