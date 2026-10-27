@echo off
rem Launch the app: packaged EXE first, then the local virtual environment.
setlocal
cd /d "%~dp0"

set "APP_EXE=dist\SchoolAttendanceManager\SchoolAttendanceManager.exe"
if exist "%APP_EXE%" (
    start "" "%APP_EXE%" %*
    exit /b 0
)

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "main.py" %*
    exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "main.py" %*
    exit /b 0
)

echo.
echo Python was not found on this PC.
echo Run setup.bat once, then double-click run_app.bat again.
echo.
pause
exit /b 1
