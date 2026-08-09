@echo off
title EOSB - Diagnostic Check
cd /d "%~dp0"
set "APPROOT=%~dp0"

set "PYEXE="
if exist "%APPROOT%runtime\python.exe" set "PYEXE=%APPROOT%runtime\python.exe"
if not defined PYEXE for %%P in (python.exe) do if not "%%~$PATH:P"=="" set "PYEXE=%%~$PATH:P"
if not defined PYEXE (py -3 --version >nul 2>&1 && set "PYEXE=py")

if not defined PYEXE (
  echo.
  echo   No runtime was found in this folder and Python is not installed.
  echo.
  echo   Folder checked: %APPROOT%runtime\python.exe
  echo.
  echo   Run  tools\SETUP_RUNTIME.bat  once, with internet, to fix this.
  echo.
  pause
  exit /b 1
)

echo.
echo   Running diagnostic check...
echo.
if "%PYEXE%"=="py" ( py -3 "%APPROOT%app\diagnose.py" ) else ( "%PYEXE%" "%APPROOT%app\diagnose.py" )
echo.
pause
