# Watchdog (vereinheitlicht)

**Empfohlener Einstiegspunkt**, wenn ihr mehrere Automatisierungen dauerhaft laufen lassen wollt: EIN Script, EINE Session, alles über eine `settings.json` konfiguriert — statt mehrere separate Scripts mit vielen CLI-Flags zu starten.

Kombiniert die Funktionen von `wrong-server-watchdog/` und `sync-members/*_watchdog.py` in einem einzigen Dauerlauf-Prozess:

- **Wrong-Server-Check:** neue Beitritte mit falschem Matrix-Server werden automatisch per DM informiert
- **Auto-Invite-Regeln:** beliebig viele Regeln der Form "wer Raum/Räume X beitritt, wird automatisch in Raum Y eingeladen" — funktioniert für Space→Raum genauso wie für ausgewählte Kanäle→Space

**Bonus gegenüber den einzelnen Scripts:** Da alles über eine einzige Matrix-Session läuft, gibt es kein "Token-Tennis" (gegenseitiges Aussperren beim Token-Refresh) zwischen mehreren parallel laufenden Prozessen mehr — das Problem verschwindet einfach, weil es nur noch einen Prozess gibt.

## Setup

1. `config.json` in diesem Ordner anlegen (Zugangsdaten, siehe Haupt-README). Bei SSO/OIDC-Servern: `auth/get_token.py` verwenden.
2. `settings.example.json` nach `settings.json` kopieren und anpassen:

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

```
python matrix_watchdog.py
```

Custom-Pfade:
```
python matrix_watchdog.py --config config.json --settings settings.json
```

Erst testen:
```
python matrix_watchdog.py --dry-run
```

## Ablauf beim Start

1. Liest `config.json` und `settings.json`
2. Für jede Auto-Invite-Regel: einmaliger vollständiger Abgleich (Bestandsmitglieder der Quellräume, die noch nicht im Zielraum sind, werden eingeladen)
3. Der Wrong-Server-Check macht **keinen** initialen Abgleich — nur neue Beitritte ab dem Start werden geprüft, damit nicht rückwirkend Bestandsmitglieder angeschrieben werden
4. Danach: Dauerlauf, reagiert live auf jeden neuen Beitritt in allen überwachten Räumen

## Dauerbetrieb einrichten

`start_watchdog.bat` anpassen (Pfad) und über die Windows-Aufgabenplanung mit Trigger "Bei Systemstart" einrichten — Details im Haupt-README. Startet automatisch neu, falls der Prozess mal abstürzt.

## Wann stattdessen die Einzel-Scripts nutzen?

Die separaten Scripts in `wrong-server-watchdog/` und `sync-members/` bleiben bestehen für einfache Fälle, bei denen ihr nur EINE Automatisierung braucht und keine Lust auf eine Settings-Datei habt — reiner CLI-Aufruf reicht dann. Sobald ihr mehrere Automatisierungen kombiniert oder öfter Regeln anpasst, ist `matrix_watchdog.py` die bessere Wahl.
