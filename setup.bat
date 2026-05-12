@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   The Wandering Goblet - first-time setup
echo ============================================================
echo.

REM --- 1. Check Python ----------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not on your PATH.
    echo.
    echo Install Python 3.11 or newer from:
    echo   https://www.python.org/downloads/windows/
    echo During the installer, tick "Add python.exe to PATH".
    echo Then close this window and run setup.bat again.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo Found %%v

REM --- 2. Virtual environment --------------------------------------------
if exist ".venv\Scripts\python.exe" (
    echo Virtual environment already exists, reusing .venv
) else (
    echo Creating virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b 1
    )
)

REM --- 3. Install dependencies -------------------------------------------
echo.
echo Installing project dependencies (this may take a minute)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] pip install failed. Check the messages above.
    pause
    exit /b 1
)

REM --- 4. Ollama model (optional - the game auto-pulls if missing) -------
echo.
where ollama >nul 2>nul
if errorlevel 1 (
    echo Ollama was not found on your PATH.
    echo.
    echo Install Ollama from:
    echo   https://ollama.com/download
    echo The game will auto-start Ollama and auto-pull the model on
    echo first launch as long as Ollama is installed - you do NOT need
    echo to run any 'ollama pull' command yourself.
) else (
    echo Pre-pulling the default model llama3.2:3b ...
    echo (already-pulled models finish in seconds; safe to skip - the
    echo  game can also pull it on first launch if you cancel this.)
    ollama pull llama3.2:3b
    if errorlevel 1 (
        echo.
        echo [WARN] ollama pull did not succeed.
        echo No problem - the game will retry the pull on first launch.
    )
)

REM --- 5. Done ------------------------------------------------------------
echo.
echo ============================================================
echo   Setup complete.
echo   Double-click run_game.bat to play.
echo   Double-click run_demo.bat for the scripted demo.
echo ============================================================
echo.
pause
endlocal
