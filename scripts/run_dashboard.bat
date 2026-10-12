@echo off
setlocal enabledelayedexpansion

REM ==============================================================================
REM Job Review Dashboard Runner (Phase 8)
REM
REM Resolves project root and launches local dashboard at http://127.0.0.1:8000
REM ==============================================================================

REM 1. Resolve project root
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

REM 2. Switch working directory to project root
cd /d "%PROJECT_ROOT%"
if errorlevel 1 (
    echo [ERROR] Failed to switch working directory to project root: %PROJECT_ROOT%
    exit /b 2
)

REM 3. Detect Python executable in virtual environment
set "PYTHON_EXE="
if exist "%PROJECT_ROOT%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\venv\Scripts\python.exe"
) else if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python virtual environment executable not found in %PROJECT_ROOT%\venv or %PROJECT_ROOT%\.venv
    exit /b 2
)

echo ==================================================
echo   Starting Job Review Dashboard Server            
echo ==================================================
echo Project Root : %PROJECT_ROOT%
echo Python Path  : %PYTHON_EXE%
echo Dashboard URL: http://127.0.0.1:8000
echo.
echo Press CTRL+C to stop the dashboard server.
echo ==================================================
echo.

"%PYTHON_EXE%" -m app.dashboard

exit /b %ERRORLEVEL%
