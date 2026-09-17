@echo off
REM Startet das vereinheitlichte Watchdog-Tool dauerhaft und startet es
REM automatisch neu, falls es abstuerzt.

REM ANPASSEN: Pfad zu deinem Tool-Ordner
cd /d "C:\matrix-tools\watchdog"

:loop
echo === %date% %time%: Watchdog wird gestartet === >> watchdog.log
python matrix_watchdog.py >> watchdog.log 2>&1
echo === %date% %time%: Watchdog beendet, Neustart in 10s === >> watchdog.log
timeout /t 10 /nobreak >nul
goto loop
