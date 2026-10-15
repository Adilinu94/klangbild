@echo off
rem Startet den Uebergangstest (oder oeffnet ihn nur, falls er schon laeuft). Fortschritt bleibt gespeichert.
cd /d "%~dp0"
netstat -ano | findstr /R /C:"127.0.0.1:8767 .*0.0.0.0:0" >nul
if not errorlevel 1 (
  start "" http://127.0.0.1:8767
  exit /b
)
title Klangbild-Uebergangstest (Fenster schliessen = beenden, Fortschritt bleibt)
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" -m klangbild uebergangstest
pause
