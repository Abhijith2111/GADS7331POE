@echo off
setlocal
cd /d "%~dp0"

echo Creating "Wandering Goblet" shortcut on your Desktop...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$lnk = Join-Path $desktop 'Wandering Goblet.lnk';" ^
  "$s = (New-Object -COM WScript.Shell).CreateShortcut($lnk);" ^
  "$s.TargetPath = '%~dp0run_game.bat';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = \"$env:SystemRoot\System32\imageres.dll,109\";" ^
  "$s.Description = 'Launch The Wandering Goblet';" ^
  "$s.Save();" ^
  "Write-Host (\"Shortcut created at: \" + $lnk)"

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to create the shortcut. See the message above.
    pause
    exit /b 1
)

echo.
echo Done. You can now launch the game by double-clicking
echo "Wandering Goblet" on your Desktop.
echo.
pause
endlocal
