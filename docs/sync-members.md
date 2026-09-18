# Sync Members (`matrix-tools sync-members`)

Lädt **einmalig** alle Mitglieder eines Space (oder Raums) in einen anderen Raum ein — z.B. alle Mitglieder eures Fachschafts-Space in die Gruppe "Aktive Fachschaft".

Wer die Einladung bereits abgelehnt hat, den Zielraum wieder verlassen hat oder schon eine offene (unbeantwortete) Einladung hat, wird **nicht** erneut eingeladen.

**Live statt einmalig?** Soll jede neu beitretende Person sofort eingeladen werden, nutzt stattdessen [`matrix-tools watchdog`](watchdog.md) mit einer Auto-Invite-Regel. Dort sind auch mehrere Quellräume (z.B. "ausgewählte Kanäle → Space") möglich.

## Setup

`config.json` im Daten-Ordner anlegen (siehe Haupt-README).

## Benutzung

Erst testen, wer eingeladen würde (es wird nichts verschickt):

```
matrix-tools sync-members --source '!spaceid' --target '!zielraumid' --dry-run
```

Tatsächlich einladen:

```
matrix-tools sync-members --source '!spaceid' --target '!zielraumid'
```

Mit Docker:

```
docker compose run --rm watchdog sync-members --source '!spaceid' --target '!zielraumid' --dry-run
```

Optionen:

- `--source` — Room-ID des Quellraums, z.B. der Space (Pflicht)
- `--target` — Room-ID des Zielraums (Pflicht)
- `--dry-run` — nur anzeigen, wer eingeladen würde
- `--config` — andere Zugangsdaten verwenden

## Periodisch unter Windows

[`windows/run_sync_members.bat`](../windows/run_sync_members.bat) anpassen (Pfade, Space-/Raum-IDs) und in der Windows-Aufgabenplanung mit einem Zeit-Trigger (z.B. stündlich) einrichten.

## Berechtigungen

Der ausführende Account braucht Mitgliedschaft im Quellraum und Einlade-Rechte (Moderator/Admin-Power-Level) im Zielraum.
