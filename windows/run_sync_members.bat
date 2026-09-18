@echo off
REM Alternative zum Dauerlauf-Watchdog: fuehrt EINMALIG einen vollstaendigen
REM Abgleich aus. Gedacht fuer den Windows-Taskplaner mit einem Zeit-Trigger
REM (z.B. stuendlich), statt permanent im Hintergrund zu laufen.

REM ANPASSEN: Pfad zu deinem Tool-Ordner
cd /d "C:\matrix-tools\sync-members"

REM ANPASSEN: Quell-Space und Ziel-Raum
set SOURCE_SPACE=!DEINE_QUELL_SPACE_ID_HIER:matrix.eure-hochschule.de
set TARGET_ROOM=!DEINE_ZIEL_RAUM_ID_HIER:matrix.eure-hochschule.de

echo === %date% %time% === >> sync.log
python matrix_sync_members.py --source "%SOURCE_SPACE%" --target "%TARGET_ROOM%" >> sync.log 2>&1
echo. >> sync.log
