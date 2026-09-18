# Watchdog (`matrix-tools watchdog`)

**Empfohlener Einstiegspunkt** für den Dauerbetrieb: EIN Prozess, EINE Session, alles über eine `settings.json` konfiguriert. Kombiniert in einem einzigen Dauerlauf-Prozess:

- **Wrong-Server-Check:** neue Beitritte mit falschem Matrix-Server werden automatisch per DM informiert
- **Auto-Invite-Regeln:** beliebig viele Regeln der Form "wer Raum/Räume X beitritt, wird automatisch in Raum Y eingeladen" — funktioniert für Space→Raum genauso wie für ausgewählte Kanäle→Space

Da alles über eine einzige Matrix-Session läuft, gibt es kein "Token-Tennis" (gegenseitiges Aussperren beim Token-Refresh) zwischen mehreren parallel laufenden Prozessen.

## Setup

1. `config.json` im Daten-Ordner anlegen (Zugangsdaten, siehe Haupt-README). Bei SSO/OIDC-Servern: [`matrix-tools login`](login.md) verwenden.
2. [`examples/settings.example.json`](../examples/settings.example.json) als `settings.json` in den Daten-Ordner kopieren und anpassen:

```json
{
  "wrong_server": {
    "enabled": true,
    "watch_rooms": ["!euerSpace:matrix.eure-hochschule.de"],
    "correct_domain": "matrix.eure-hochschule.de",
    "guide_url": "https://eure-hochschule.de/matrix-anleitung",
    "sender_name": "deine Fachschaft",
    "dry_run": false
  },
  "auto_invite_rules": [
    {
      "source_rooms": ["!euerSpace:matrix.eure-hochschule.de"],
      "target_room": "!aktiveFachschaft:matrix.eure-hochschule.de",
      "dry_run": false
    },
    {
      "source_rooms": ["!kanal1:...", "!kanal2:..."],
      "target_room": "!euerSpace:matrix.eure-hochschule.de",
      "dry_run": false
    }
  ]
}
```

- `wrong_server.enabled: false` schaltet den Wrong-Server-Check komplett ab, falls ihr den nicht braucht
- `auto_invite_rules` kann leer (`[]`) sein oder beliebig viele Regeln enthalten
- Jede Regel hat eigene `source_rooms` (Liste, auch mit nur einem Eintrag) und genau ein `target_room`
- Pro Regel und beim Wrong-Server-Check kann `dry_run` einzeln gesetzt werden — oder global per `--dry-run`-Flag beim Start (überschreibt alle einzelnen Einstellungen)

## Benutzung

Mit Docker (dauerhaft im Hintergrund, siehe Haupt-README):
```
docker compose up -d
```

Ohne Docker (im Daten-Ordner):
```
matrix-tools watchdog
```

Custom-Pfade:
```
matrix-tools watchdog --config config.json --settings settings.json
```

Erst testen:
```
matrix-tools watchdog --dry-run
```

Mit Docker testen:
```
docker compose run --rm watchdog watchdog --dry-run
```

## Ablauf beim Start

1. Liest `config.json` und `settings.json`
2. Für jede Auto-Invite-Regel: einmaliger vollständiger Abgleich (Bestandsmitglieder der Quellräume, die noch nicht im Zielraum sind, werden eingeladen)
3. Der Wrong-Server-Check macht **keinen** initialen Abgleich — nur neue Beitritte ab dem Start werden geprüft, damit nicht rückwirkend Bestandsmitglieder angeschrieben werden
4. Danach: Dauerlauf, reagiert live auf jeden neuen Beitritt in allen überwachten Räumen

## Dauerbetrieb einrichten

- **Mit Docker:** `docker compose up -d` — der Container startet automatisch neu, falls der Prozess abstürzt oder der Rechner neu startet.
- **Windows ohne Docker:** [`windows/start_watchdog.bat`](../windows/start_watchdog.bat) anpassen (Pfade) und über die Windows-Aufgabenplanung mit Trigger "Bei Systemstart" einrichten — Details im Haupt-README. Die `.bat`-Datei startet den Prozess automatisch neu, falls er mal abstürzt.
