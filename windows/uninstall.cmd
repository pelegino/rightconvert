@echo off
rem Double-click to remove RightConvert. Works from the download or from the installed copy.
rem Leave the folder first so it can be deleted, and exit on the same line because this file
rem may be gone by the time the command returns.
cd /d "%TEMP%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" -Pause & exit /b
