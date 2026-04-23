@echo off
setlocal enabledelayedexpansion

rem ============================================================
rem  Hand Control  Windows peer agent  one-command setup.
rem
rem  Double-click this file, or from a terminal:
rem
rem      cd hand-control
rem      peer\install.bat
rem
rem  It walks you through the whole PC-side setup:
rem
rem    1. Checks Windows + Python 3.10+.
rem    2. Creates peer\.venv and installs Python dependencies.
rem    3. Creates a Start Menu + Desktop shortcut to peer\run.bat
rem       so you can launch the peer like any normal Windows app.
rem    4. Shows you what Wispr Flow hotkey to set.
rem    5. Prints the exact line to paste on your Mac so the two
rem       machines know about each other.
rem
rem  Fully idempotent  safe to rerun whenever.
rem ============================================================

cd /d "%~dp0\.."
set "REPO_DIR=%CD%"

echo.
echo ============================================================
echo   Hand Control  Windows peer setup
echo ============================================================
echo.

rem --- 1. Platform ---------------------------------------------

echo [1/5] Platform
ver | findstr /C:"Windows" >nul
if errorlevel 1 (
    echo   x  This setup runs only on Windows. Detected: %OS%
    echo      On your Mac, run  ./install.sh  from the repo root.
    pause & exit /b 1
)
echo   v  Windows detected

rem --- 2. Python 3.10+ ----------------------------------------

echo.
echo [2/5] Python 3.10+
where python >nul 2>nul
if errorlevel 1 (
    echo   x  python not found on PATH.
    echo.
    echo   Install Python 3.12 from the Microsoft Store or:
    echo     https://www.python.org/downloads/
    echo.
    echo   IMPORTANT: during install, tick
    echo     [x] Add python.exe to PATH
    echo.
    set /p ANSWER=  Open the download page now? [Y/n]: 
    if /i not "!ANSWER!"=="n" start https://www.python.org/downloads/
    echo.
    echo   After installing Python, close and reopen this terminal
    echo   and rerun  peer\install.bat.
    pause & exit /b 1
)

for /f "tokens=*" %%v in ('python -c "import sys; print('ok' if sys.version_info^>=(3,10) else 'old')" 2^>nul') do set PY_OK=%%v
if not "!PY_OK!"=="ok" (
    for /f "tokens=*" %%v in ('python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"') do set PY_VER=%%v
    echo   x  Python 3.10+ required, found !PY_VER!.
    echo      Install a newer one from  https://www.python.org/downloads/
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"') do set PY_VER=%%v
echo   v  Python !PY_VER!

rem --- 3. Virtualenv + deps ------------------------------------

echo.
echo [3/5] Python dependencies

if not exist "peer\.venv\Scripts\python.exe" (
    echo      creating virtualenv...
    python -m venv peer\.venv
    if errorlevel 1 (
        echo   x  Failed to create virtualenv in peer\.venv
        pause & exit /b 1
    )
)

call "peer\.venv\Scripts\activate.bat"

echo      installing packages...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install -r peer\requirements.txt
if errorlevel 1 (
    echo   x  Dependency install failed  scroll up for the error.
    echo      Common fixes:
    echo       - disable VPN / firewall briefly, then retry
    echo       - run in "Developer Command Prompt" if SSL-related
    pause & exit /b 1
)
echo   v  installed FastAPI, pynput, pywin32

rem --- 4. Start Menu + Desktop shortcuts -----------------------

echo.
echo [4/5] Shortcuts

set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Hand Control Peer.lnk"
set "DESKTOP=%USERPROFILE%\Desktop\Hand Control Peer.lnk"
set "TARGET=%REPO_DIR%\peer\run.bat"
set "ICON=%REPO_DIR%\phone\icon-192.png"

rem WScript.Shell COM is built in to Windows  no extra deps needed.
rem Make one script and run it for both shortcuts.
set "VBS=%TEMP%\hc_mk_shortcut.vbs"

> "%VBS%" (
    echo Set sh = CreateObject^("WScript.Shell"^)
    echo args = WScript.Arguments
    echo path = args^(0^)
    echo target = args^(1^)
    echo workdir = args^(2^)
    echo Set lnk = sh.CreateShortcut^(path^)
    echo lnk.TargetPath = target
    echo lnk.WorkingDirectory = workdir
    echo lnk.Description = "Hand Control peer agent ^(PC-side^)"
    echo lnk.WindowStyle = 1
    echo lnk.Save
)

cscript //nologo "%VBS%" "%STARTMENU%" "%TARGET%" "%REPO_DIR%"
if exist "%STARTMENU%" (
    echo   v  Start Menu   "Hand Control Peer"
) else (
    echo   !  could not create Start Menu shortcut ^(not fatal^)
)

cscript //nologo "%VBS%" "%DESKTOP%" "%TARGET%" "%REPO_DIR%"
if exist "%DESKTOP%" (
    echo   v  Desktop      "Hand Control Peer"
) else (
    echo   !  could not create Desktop shortcut ^(not fatal^)
)

del "%VBS%" >nul 2>nul

rem --- 5. Wispr Flow reminder + Mac setup line -----------------

echo.
echo [5/5] Wispr Flow on this PC

set "WISPR_EXE=%LOCALAPPDATA%\Programs\Wispr Flow\Wispr Flow.exe"
if exist "%WISPR_EXE%" (
    echo   v  Wispr Flow detected.
) else (
    echo   !  Wispr Flow not found.
    echo      Download from  https://wisprflow.ai
)

echo.
echo      Open Wispr Flow  Settings  Shortcuts  Dictation hotkey
echo      and set it to:   Right Alt   ^(also shown as RAlt / AltGr^)
echo.

rem --- Compute a best-effort hostname for the Mac-setup line ---

for /f "tokens=*" %%h in ('hostname') do set PC_HOSTNAME=%%h
set "MAC_URL=http://!PC_HOSTNAME!:8001"

rem --- Farewell ------------------------------------------------

echo.
echo ============================================================
echo   All set. Here^'s what to do next:
echo ============================================================
echo.
echo   A.  Launch the peer:
echo         double-click "Hand Control Peer" on your desktop,
echo         or run  peer\run.bat
echo.
echo       A terminal window will stay open  that's the peer
echo       running. Closing it stops the peer.
echo.
echo   B.  On your MAC, paste these two lines into Terminal
echo       before running  ./run.sh  :
echo.
echo         export HC_PEER_URL=!MAC_URL!
echo         export HC_PC_SIDE=left
echo.
echo       ^(Change HC_PC_SIDE to right/above/below depending on
echo        where this PC sits relative to the Mac.^)
echo.
echo   C.  Reload the Hand Control PWA on your phone. You'll see
echo       Cursor windows from BOTH machines in one deck, and the
echo       trackpad will cross edges between the two screens.
echo.
echo   Details: peer\README.md and the "Two-machine mode" section
echo            of README.md at the repo root.
echo.

pause
