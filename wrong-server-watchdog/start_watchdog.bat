@echo off
REM Startet den Wrong-Server-Watchdog dauerhaft und startet ihn automatisch
REM neu, falls er abstuerzt (z.B. wegen abgelaufenem Token, Netzwerkfehler).
REM Laeuft in einer Endlosschleife - zum Beenden das Fenster schliessen oder
REM den Prozess im Taskmanager beenden.

REM ANPASSEN: Pfad zu deinem Tool-Ordner
cd /d "C:\matrix-tools\wrong-server-watchdog"

REM ANPASSEN: Deine Space-ID und der korrekte Homeserver eurer Hochschule
set SPACE_ID=!DEINE_SPACE_ID_HIER:matrix.eure-hochschule.de
set CORRECT_DOMAIN=matrix.eure-hochschule.de
set GUIDE_URL=https://eure-hochschule.de/matrix-anleitung
set SENDER_NAME=deine Fachschaft

:loop
echo === %date% %time%: Watchdog wird gestartet === >> watchdog.log
python matrix_wrong_server_watchdog.py --room "%SPACE_ID%" --correct-domain "%CORRECT_DOMAIN%" --config config.json --guide-url "%GUIDE_URL%" --sender-name "%SENDER_NAME%" >> watchdog.log 2>&1
echo === %date% %time%: Watchdog beendet, Neustart in 10s === >> watchdog.log
timeout /t 10 /nobreak >nul
goto loop
