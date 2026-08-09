@echo off
title End of Service Benefits Management System
cd /d "%~dp0"
set "APPROOT=%~dp0"

rem ---------------------------------------------------------------------
rem  The launcher always uses the folder it lives in, so a desktop
rem  shortcut opens the database that belongs to THIS folder.
rem ---------------------------------------------------------------------
set "PYEXE="
if exist "%APPROOT%runtime\python.exe" set "PYEXE=%APPROOT%runtime\python.exe"

if not defined PYEXE (
  for %%P in (python.exe) do if not "%%~$PATH:P"=="" set "PYEXE=%%~$PATH:P"
)
if not defined PYEXE (
  py -3 --version >nul 2>&1 && set "PYEXE=py"
)

if not defined PYEXE goto :noruntime

echo.
echo   Starting the End of Service Benefits Management System...
echo   Folder: %APPROOT%
echo.
if "%PYEXE%"=="py" (
  py -3 "%APPROOT%app\main.py"
) else (
  "%PYEXE%" "%APPROOT%app\main.py"
)

if errorlevel 1 (
  echo.
  echo  ============================================================
  echo   The application stopped with an error.
  echo   Double-click DIAGNOSE.bat to find out why.
  echo  ============================================================
  echo.
  pause
)
goto :eof

:noruntime
echo.
echo  ============================================================
echo   The application runtime was not found.
echo.
echo   Run this once, with an internet connection:
echo.
echo       tools\SETUP_RUNTIME.bat
echo.
echo   It downloads the runtime into this folder. After that the
echo   application works on any computer with no installation.
echo  ============================================================
echo.
pause
