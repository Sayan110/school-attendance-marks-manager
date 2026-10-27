@echo off
rem Build the standalone Windows application with PyInstaller.
rem Output: dist\SchoolAttendanceManager\SchoolAttendanceManager.exe
setlocal
cd /d "%~dp0"

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

if exist "app.ico" goto build
echo Generating app.ico ...
"%PY%" assets\generate_icon.py
if errorlevel 1 goto failed

:build
echo Ensuring PyInstaller is installed ...
"%PY%" -m pip install --upgrade "pyinstaller>=6.4"
if errorlevel 1 goto failed

echo Building (this takes a few minutes) ...
"%PY%" -m PyInstaller --noconfirm --clean --windowed ^
    --name SchoolAttendanceManager ^
    --icon app.ico ^
    --add-data "app.ico;." ^
    --exclude-module tkinter ^
    --exclude-module PyQt5 ^
    --exclude-module PyQt6 ^
    --exclude-module PySide2 ^
    main.py
if errorlevel 1 goto failed

if exist "dist\SchoolAttendanceManager\SchoolAttendanceManager.exe" goto done
echo Build finished without producing the expected EXE.
goto failed

:done
echo.
echo Build complete:
echo   dist\SchoolAttendanceManager\SchoolAttendanceManager.exe
echo.
echo Next: create the desktop shortcut with
echo   powershell -ExecutionPolicy Bypass -File create_desktop_shortcut.ps1
echo.
pause
exit /b 0

:failed
echo.
echo Build failed. Read the error above.
echo.
pause
exit /b 1
