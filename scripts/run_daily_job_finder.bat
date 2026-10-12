@echo off
setlocal enabledelayedexpansion

REM ==============================================================================
REM Daily Job Finder Automation - Windows Daily Runner (Phase 7B)
REM
REM Exit Codes:
REM   0 = Pipeline completed successfully (including with source warnings)
REM   1 = Pipeline failed (unhandled internal error)
REM   2 = Runner/Environment/Configuration failure
REM   3 = Another run is already in progress (process lock active)
REM ==============================================================================

REM 1. Reliably resolve project root directory (one level up from this script)
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

REM 2. Switch working directory to project root
cd /d "%PROJECT_ROOT%"
if errorlevel 1 (
    echo [ERROR] Failed to switch working directory to project root: %PROJECT_ROOT%
    exit /b 2
)

REM 3. Ensure data and log directories exist
if not exist "%PROJECT_ROOT%\data" mkdir "%PROJECT_ROOT%\data"
if not exist "%PROJECT_ROOT%\data\logs" mkdir "%PROJECT_ROOT%\data\logs"

REM 4. Detect Python executable in virtual environment
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

REM 5. Validate core pipeline entrypoint
if not exist "%PROJECT_ROOT%\app\main.py" (
    echo [ERROR] Application entrypoint not found: %PROJECT_ROOT%\app\main.py
    exit /b 2
)

REM 6. Generate timestamp for unique, non-overwriting log filename (YYYYMMDD_HHMMSS)
set "TIMESTAMP="
for /f "tokens=*" %%T in ('call "%PYTHON_EXE%" -c "import datetime; print(datetime.datetime.now().strftime("""%%Y%%m%%d_%%H%%M%%S"""))" 2^>nul') do (
    set "TIMESTAMP=%%T"
)

if "%TIMESTAMP%"=="" (
    REM Fallback timestamp using batch variables if python inline fails
    set "HR=%TIME:~0,2%"
    if "!HR:~0,1!"==" " set "HR=0!HR:~1,1!"
    set "TIMESTAMP=%DATE:~6,4%%DATE:~3,2%%DATE:~0,2%_!HR!%TIME:~3,2%%TIME:~6,2%"
)

set "LOG_FILE=%PROJECT_ROOT%\data\logs\job_finder_%TIMESTAMP%.log"

REM 7. Write runner header to log
echo ================================================== >> "%LOG_FILE%"
echo Run started: %DATE% %TIME% >> "%LOG_FILE%"
echo Project root: %PROJECT_ROOT% >> "%LOG_FILE%"
echo Python executable: %PYTHON_EXE% >> "%LOG_FILE%"
echo Pipeline start: Initiating execution >> "%LOG_FILE%"
echo ================================================== >> "%LOG_FILE%"

REM 8. Execute pipeline, capturing all stdout and stderr into log
"%PYTHON_EXE%" -m app.main >> "%LOG_FILE%" 2>&1
set "PIPELINE_EXIT=%ERRORLEVEL%"

REM 9. Write runner summary footer to log
echo. >> "%LOG_FILE%"
echo ================================================== >> "%LOG_FILE%"
echo Pipeline completion status: Exit code %PIPELINE_EXIT% >> "%LOG_FILE%"
echo Exit code: %PIPELINE_EXIT% >> "%LOG_FILE%"
echo Run finished: %DATE% %TIME% >> "%LOG_FILE%"
echo ================================================== >> "%LOG_FILE%"

REM 10. Display captured log to standard output for manual runs
type "%LOG_FILE%"

REM 11. Exit with the exact pipeline exit code (0, 1, or 3)
exit /b %PIPELINE_EXIT%
