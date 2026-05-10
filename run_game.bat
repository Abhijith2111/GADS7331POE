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

REM Pass through any extra args, e.g. run_game.bat --model qwen2.5:3b
python -m src.main %*

REM Only pause on a non-zero exit so a clean quit closes the window
REM but a crash leaves the error message readable.
if errorlevel 1 (
    echo.
    echo The game exited with an error. See the messages above.
    pause
)
endlocal
