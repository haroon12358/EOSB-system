@echo off
title EOSB - One Time Runtime Setup
setlocal
cd /d "%~dp0.."
set "APPROOT=%CD%"

echo.
echo  ================================================================
echo    End of Service Benefits Management System
echo    One time runtime setup
echo  ================================================================
echo.
echo    This downloads the application runtime into:
echo      %APPROOT%\runtime
echo.
echo    You only ever do this once, on this computer, with internet.
echo    Afterwards the whole folder can be copied to any Windows PC
echo    and it will run with nothing installed.
echo.
pause

if exist "%APPROOT%\runtime\python.exe" (
  echo    The runtime is already present. Nothing to do.
  pause
  exit /b 0
)

set "PYVER=3.12.8"
set "ZIPURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-embed-amd64.zip"
set "ZIPFILE=%APPROOT%\runtime.zip"

echo.
echo    Downloading Python %PYVER% embeddable runtime (about 11 MB)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri '%ZIPURL%' -OutFile '%ZIPFILE%' -UseBasicParsing } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 goto :failed
if not exist "%ZIPFILE%" goto :failed

echo    Extracting...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -LiteralPath '%ZIPFILE%' -DestinationPath '%APPROOT%\runtime' -Force"
if errorlevel 1 goto :failed
del "%ZIPFILE%" >nul 2>&1

if not exist "%APPROOT%\runtime\python.exe" goto :failed

echo.
echo  ================================================================
echo    Setup complete.
echo    Close this window and double-click EOSB.bat to start.
echo  ================================================================
echo.
pause
exit /b 0

:failed
echo.
echo  ----------------------------------------------------------------
echo    The download did not succeed.
echo.
echo    You can do it by hand instead:
echo      1. Go to  https://www.python.org/downloads/windows/
echo      2. Download "Windows embeddable package (64-bit)"
echo      3. Extract it into:  %APPROOT%\runtime
echo         so that %APPROOT%\runtime\python.exe exists
echo  ----------------------------------------------------------------
echo.
pause
exit /b 1
