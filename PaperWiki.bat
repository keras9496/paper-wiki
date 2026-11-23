@echo off
rem Double-click to start Paper Wiki. Closing this window stops the app.
title Paper Wiki
if not exist "%~dp0.venv\Scripts\paperwiki.exe" (
  echo Paper Wiki is not installed yet. Run install.bat first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\paperwiki.exe" %*
if errorlevel 1 pause
