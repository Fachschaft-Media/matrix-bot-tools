@echo off
REM Fuehrt EINMALIG einen vollstaendigen Mitglieder-Abgleich aus
REM (matrix-tools sync-members). Gedacht fuer den Windows-Taskplaner mit einem
REM Zeit-Trigger (z.B. stuendlich). Fuer Live-Einladungen stattdessen den
REM Watchdog mit einer Auto-Invite-Regel nutzen.
REM Voraussetzung: uv ist installiert
REM (https://docs.astral.sh/uv/getting-started/installation/).

REM ANPASSEN: Ordner, in dem dieses Repository liegt
set PROJECT_DIR=C:\matrix-bot-tools

REM ANPASSEN: Daten-Ordner mit config.json
set DATA_DIR=C:\matrix-bot-tools\data

REM ANPASSEN: Quell-Space und Ziel-Raum
set SOURCE_SPACE=!DEINE_QUELL_SPACE_ID_HIER:matrix.eure-hochschule.de
set TARGET_ROOM=!DEINE_ZIEL_RAUM_ID_HIER:matrix.eure-hochschule.de

cd /d "%DATA_DIR%"

echo === %date% %time% === >> sync.log
uv run --project "%PROJECT_DIR%" matrix-tools sync-members --source "%SOURCE_SPACE%" --target "%TARGET_ROOM%" >> sync.log 2>&1
echo. >> sync.log
