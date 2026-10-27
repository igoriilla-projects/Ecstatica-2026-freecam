@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 freecam.py
) else (
    python freecam.py
)
echo.
echo Freecam helper closed. Press any key to close this window.
pause >nul
