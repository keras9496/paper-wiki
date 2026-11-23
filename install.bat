@echo off
rem Double-click to install Paper Wiki (creates .venv, a desktop shortcut, then starts the app).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 pause
