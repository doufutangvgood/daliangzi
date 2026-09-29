@echo off
rem ===========================================================================
rem  Da Liang Zi - one-click launcher (Windows)
rem
rem  Double-click this file to start the tool and open the browser.
rem  Close the window (or press Ctrl+C) to stop it.
rem
rem  This file is deliberately ASCII-only. The console code page is switched to
rem  UTF-8 below, and cmd.exe decodes the rest of a batch file using whichever
rem  code page is active - so non-ASCII text here would be fragile. Every
rem  Chinese message you see comes from run.py, which forces its own stdout
rem  to UTF-8.
rem ===========================================================================

rem UTF-8 console. Without this, run.py's Chinese output turns into mojibake,
rem because the default console code page here is 936 (GBK).
chcp 65001 >nul

setlocal
rem Always work from the folder this file lives in - double-clicking from
rem Explorer does not guarantee the current directory.
cd /d "%~dp0"

rem Find a real Python. A bare `python` may be the Microsoft Store stub, which
rem prints a message and exits 9009, so test it by actually running it.
set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    py -3 --version >nul 2>&1 && set "PY=py -3"
)

if not defined PY (
    echo.
    echo   [X] Python not found.
    echo       Install Python 3.10+ and tick "Add python.exe to PATH".
    echo       https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

rem NOTE: never put a bare ')' inside an if(...) block below - cmd closes the
rem block at the first ')' it sees, and the rest of the file then parses as
rem garbage ("... was unexpected at this time").

rem --open starts the server and opens the browser once the port is really up.
rem If an instance is already running, run.py reuses it instead of fighting
rem over the port, and this window closes again.
%PY% run.py --open %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo   [X] Failed to start - exit code %RC%. Read the message above.
    echo.
    pause
)

exit /b %RC%
