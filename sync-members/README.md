# Sync Members

Lädt automatisch alle Mitglieder eines Space (oder Raums) in einen anderen Raum ein — z.B. jede Person, die eurem Fachschafts-Space beitritt, automatisch in die Gruppe "Aktive Fachschaft".

Drei Varianten in diesem Ordner, je nach Bedarf:

| Datei | Modus | Wann nutzen |
|---|---|---|
| `matrix_sync_members.py` | Einmalig | Manueller Aufruf oder für den Taskplaner mit Zeit-Trigger (z.B. stündlich) |
| `matrix_sync_members_watchdog.py` | Dauerlauf | Reagiert **live** auf neue Beitritte, keine Wartezeit bis zum nächsten periodischen Lauf |
| `run_periodic.bat` / `start_sync_watchdog.bat` | Wrapper | Fertige Windows-Batch-Skripte für die beiden Modi oben, inkl. Logging |

Beide Python-Varianten teilen dieselbe Logik: Wer die Einladung bereits abgelehnt hat, den Zielraum wieder verlassen hat, oder schon eine offene (unbeantwortete) Einladung hat, wird **nicht** erneut eingeladen.

## Setup

`config.json` in diesem Ordner anlegen (siehe Haupt-README). Für die Dauerlauf-Variante: Falls euer Server SSO/OIDC-Login nutzt, unbedingt `auth/get_token.py` verwenden, damit der Token-Auto-Refresh funktioniert (siehe Haupt-README).

## Einmalig / periodisch (`matrix_sync_members.py`)

```
python matrix_sync_members.py --source '!spaceid' --target '!zielraumid'
```

- `--dry-run` — nur anzeigen, wer eingeladen würde, ohne tatsächlich zu senden
- Für den Taskplaner: `run_periodic.bat` anpassen (Space-/Raum-IDs eintragen) und als Aktion mit Zeit-Trigger einrichten

## Dauerlauf / live (`matrix_sync_members_watchdog.py`)

```
python matrix_sync_members_watchdog.py --source '!spaceid' --target '!zielraumid' --config config.json
```

Macht beim Start einen vollständigen Abgleich (wie die Einmal-Variante), läuft danach weiter und lädt jede neu beitretende Person **sofort** ein.

Für Dauerbetrieb: `start_sync_watchdog.bat` anpassen (Pfade, IDs) und über die Windows-Aufgabenplanung mit Trigger "Bei Systemstart" einrichten — Details im Haupt-README.

**Wichtig:** Falls parallel auch der `wrong-server-watchdog` läuft, braucht dieses Script eine **eigene** `config.json`/Session (siehe Haupt-README, Abschnitt "Token-Tennis").

## Berechtigungen

Der ausführende Account braucht Mitgliedschaft im Quellraum und Einlade-Rechte (Moderator/Admin-Power-Level) im Zielraum.
