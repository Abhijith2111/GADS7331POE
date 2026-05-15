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

echo ============================================================
echo   LOCAL LLM (Ollama) — NOT a cloud API
echo ============================================================
echo   All demo dialogue and JSON calls go to Ollama on this PC:
echo     Host:  http://localhost:11434
echo     Model: llama3.2:3b   add  --model your-tag  after this script name to override
echo   Install Ollama from https://ollama.com if needed; the game can
echo   try to start the daemon when you launch.
echo ------------------------------------------------------------
echo   Scripted demo: persona broke_bard, 4 turns, seed 1234.
echo   Prompt + dialogue logs are written next to this folder.
echo ============================================================
echo.

REM Trailing %* lets you append extra flags, e.g.
REM   run_demo.bat --persona paranoid_wizard
REM   run_demo.bat --model qwen2.5:3b
python -m src.main --demo --persona broke_bard --turns 4 --seed 1234 %*

if errorlevel 1 (
    echo.
    echo The demo exited with an error. See the messages above.
    pause
)
endlocal
