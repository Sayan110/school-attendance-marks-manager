@echo off
rem One-time setup: create .venv, install requirements, verify the app starts.
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto install

set "PY=python"
where py >nul 2>nul
if %errorlevel%==0 set "PY=py -3"

echo Creating virtual environment with %PY% ...
%PY% -m venv .venv
if errorlevel 1 goto failed

:install
set "VENV_PY=.venv\Scripts\python.exe"

echo Upgrading pip ...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto failed

echo Installing requirements (PySide6, matplotlib, pandas, openpyxl, reportlab) ...
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto failed

if exist "app.ico" goto smoke
echo Generating app.ico ...
"%VENV_PY%" assets\generate_icon.py
if errorlevel 1 goto failed

:smoke
echo Running a quick smoke test (temporary database, no window) ...
"%VENV_PY%" main.py --smoke-test
if errorlevel 1 goto failed

echo.
echo Setup complete.
echo   Start the app with run_app.bat
echo   Build the EXE with build_exe.bat
echo   Create a desktop shortcut with:
echo     powershell -ExecutionPolicy Bypass -File create_desktop_shortcut.ps1
echo.
pause
exit /b 0

:failed
echo.
echo Setup failed. Read the error above, then run setup.bat again.
echo.
pause
exit /b 1
