@echo off
REM Startet den Watchdog (matrix-tools watchdog) dauerhaft und startet ihn
REM automatisch neu, falls er abstuerzt. Voraussetzung: uv ist installiert
REM (https://docs.astral.sh/uv/getting-started/installation/).

REM ANPASSEN: Ordner, in dem dieses Repository liegt
set PROJECT_DIR=C:\matrix-bot-tools

REM ANPASSEN: Daten-Ordner mit config.json und settings.json
set DATA_DIR=C:\matrix-bot-tools\data

cd /d "%DATA_DIR%"

:loop
echo === %date% %time%: Watchdog wird gestartet === >> watchdog.log
uv run --project "%PROJECT_DIR%" matrix-tools watchdog >> watchdog.log 2>&1
echo === %date% %time%: Watchdog beendet, Neustart in 10s === >> watchdog.log
timeout /t 10 /nobreak >nul
goto loop
