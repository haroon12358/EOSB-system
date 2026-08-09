================================================================================
  END OF SERVICE BENEFITS (EOSB) MANAGEMENT SYSTEM
  Version 1.0.0
================================================================================

WHAT THIS IS
  A complete accounting application for End of Service Benefits. It replaces
  the provision workbook entirely: employee master, salary history, unpaid
  leave, benefit payments, an unlimited year-by-year provision roll forward,
  reports in Excel and PDF, and backup and restore.

  Everything is stored in one database file inside this folder. It works with
  no internet connection.

--------------------------------------------------------------------------------
IMPORTANT - READ THIS FIRST
--------------------------------------------------------------------------------
  DO NOT run the application from inside the ZIP file.

  Windows lets you open a ZIP as though it were a folder, but nothing you
  save inside it is kept. The application will appear to work and then lose
  everything you type.

  Right-click the ZIP  ->  Extract All  ->  choose Documents or Desktop.
  Then open the extracted folder and run EOSB.bat from there.

--------------------------------------------------------------------------------
IF SOMETHING DOES NOT WORK
--------------------------------------------------------------------------------
  Double-click  DIAGNOSE.bat

  It checks everything and writes diagnostic_report.txt in this folder,
  saying exactly what is wrong. Send that file and it can be fixed.

--------------------------------------------------------------------------------
STARTING THE APPLICATION
--------------------------------------------------------------------------------
  Windows : double-click  EOSB.bat
  Mac      : double-click  EOSB.command
  Linux    : run          ./EOSB.command

  The application opens in your default web browser. A small window stays
  open while it runs - close that window to stop the application.

--------------------------------------------------------------------------------
FIRST TIME ON A NEW WINDOWS COMPUTER (once only, needs internet)
--------------------------------------------------------------------------------
  If you see "The application runtime was not found":

      Run  tools\SETUP_RUNTIME.bat

  It downloads the runtime into this folder (about 11 MB). After that the
  entire folder is self-contained: copy it to any Windows PC, double-click
  EOSB.bat, and it runs with nothing installed.

  To prepare a folder for a client, run SETUP_RUNTIME.bat once on your own
  machine, then send them the whole folder. They install nothing at all.

--------------------------------------------------------------------------------
WHAT IS IN THIS FOLDER
--------------------------------------------------------------------------------
  EOSB.bat            The launcher (Windows)
  EOSB.command        The launcher (Mac / Linux)
  app\                The application: interface, engine, reports
  data\eosb.db        Your database - all employee and provision data
  config\settings.json Your settings
  backups\            Backup copies kept inside the folder
  runtime\            The runtime (created by SETUP_RUNTIME.bat)
  tools\              One-time setup helpers
  docs\               Design and accounting documentation

--------------------------------------------------------------------------------
MOVING OR SHARING THE APPLICATION
--------------------------------------------------------------------------------
  Move or copy the WHOLE folder. The database travels inside it, so nothing
  is lost. The launcher always opens the database stored beside it, even when
  you start it from a desktop shortcut.

  To move only the data to another computer that already has the application:
  use Backup & Restore inside the application.

--------------------------------------------------------------------------------
SAVING
--------------------------------------------------------------------------------
  There is no save button. Every change is written to the database the moment
  you make it.

--------------------------------------------------------------------------------
BACKUP
--------------------------------------------------------------------------------
  Backup & Restore -> Create Backup Now
  writes one .eosbak file to your Downloads folder, and keeps a copy in
  backups\ inside this folder. Restore accepts that file on any other copy of
  the application.

--------------------------------------------------------------------------------
THE REPORTING DATE
--------------------------------------------------------------------------------
  On start-up the application takes the date from the internet when it can,
  and from this computer's clock when it cannot. New reporting years appear
  on their own - the application never needs updating to keep working.

================================================================================
