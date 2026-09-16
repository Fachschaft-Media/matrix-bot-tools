@echo off
REM Startet den Auto-Invite-Watchdog (matrix_sync_members_watchdog.py) dauerhaft
REM und startet ihn automatisch neu, falls er abstuerzt.

REM ANPASSEN: Pfad zu deinem Tool-Ordner
cd /d "C:\matrix-tools\sync-members"

REM ANPASSEN: Quell-Space (z.B. Fachschafts-Space) und Ziel-Raum (z.B. "Aktive Fachschaft")
set SOURCE_SPACE=!DEINE_QUELL_SPACE_ID_HIER:matrix.eure-hochschule.de
set TARGET_ROOM=!DEINE_ZIEL_RAUM_ID_HIER:matrix.eure-hochschule.de

:loop
echo === %date% %time%: Sync-Watchdog wird gestartet === >> sync_watchdog.log
python matrix_sync_members_watchdog.py --source "%SOURCE_SPACE%" --target "%TARGET_ROOM%" --config config.json >> sync_watchdog.log 2>&1
echo === %date% %time%: Sync-Watchdog beendet, Neustart in 10s === >> sync_watchdog.log
timeout /t 10 /nobreak >nul
goto loop
