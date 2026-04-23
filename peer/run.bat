@echo off
setlocal enabledelayedexpansion

rem --- Run the Hand Control peer agent on Windows ---------------------------
rem
rem This script:
rem   1. Checks Python 3.10+ is installed
rem   2. Creates peer\.venv and installs peer\requirements.txt on first run
rem   3. Starts the peer HTTP server on port 8001 (set PORT=xxxx to override)

cd /d "%~dp0"

rem --- Platform sanity ------------------------------------------------------
ver | findstr /C:"Windows" >nul
if errorlevel 1 (
    echo Hand Control peer only runs on Windows. Detected: %OS%
    exit /b 1
)

rem --- Python 3.10+ check ---------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo python not found on PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to tick "Add python.exe to PATH" during install.
    exit /b 1
)

for /f "tokens=*" %%v in ('python -c "import sys; print('ok' if sys.version_info^>=(3,10) else 'old')" 2^>nul') do set PY_OK=%%v
if not "!PY_OK!" == "ok" (
    for /f "tokens=*" %%v in ('python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"') do set PY_VER=%%v
    echo Python 3.10+ required, found !PY_VER!.
    exit /b 1
)

rem --- Virtualenv + deps ----------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtualenv...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtualenv.
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

if not exist ".venv\.installed" (
    echo Installing dependencies...
    python -m pip install --upgrade pip >nul
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Dependency install failed.
        exit /b 1
    )
    type nul > ".venv\.installed"
) else (
    rem Re-install if requirements.txt is newer than the marker.
    for %%f in (requirements.txt) do set REQ_TIME=%%~tf
    for %%f in (.venv\.installed) do set INS_TIME=%%~tf
    if "!REQ_TIME!" GTR "!INS_TIME!" (
        echo requirements.txt changed - reinstalling dependencies...
        python -m pip install -r requirements.txt
        type nul > ".venv\.installed"
    )
)

rem --- Run ------------------------------------------------------------------
rem We run from the repo root so `python -m peer.main` resolves correctly.
cd /d "%~dp0\.."
python -m peer.main
