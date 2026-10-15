@echo off
rem Startet den Klangbild-Mixer (oder oeffnet ihn nur, falls er schon laeuft).
cd /d "%~dp0"
netstat -ano | findstr /R /C:"127.0.0.1:8766 .*0.0.0.0:0" >nul
if not errorlevel 1 (
  start "" http://127.0.0.1:8766
  exit /b
)
title Klangbild-Mixer (Fenster schliessen = beenden)
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" -m klangbild mixer
pause
