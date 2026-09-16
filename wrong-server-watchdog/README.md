# Wrong-Server-Watchdog

An vielen Hochschulen (z.B. h_da) laufen mehrere Matrix-Homeserver parallel — ein hochschuleigener und der öffentliche `matrix.org`. Neue Nutzer:innen wählen beim Erstellen ihres Matrix-Accounts leicht versehentlich den falschen Server. Dieses Script erkennt das automatisch und schickt eine hilfreiche Direktnachricht.

## Wie es funktioniert

Läuft **dauerhaft** im Hintergrund und überwacht einen oder mehrere Räume live. Sobald jemand beitritt, dessen Matrix-Server-Domain nicht der erwarteten Hochschul-Domain entspricht, bekommt die Person automatisch eine **Direktnachricht** (nicht öffentlich im Raum) mit Erklärung und Link zur Anleitung.

Bereits benachrichtigte Personen werden in `notified_users.json` gemerkt, damit niemand bei einem Neustart doppelt angeschrieben wird.

## Setup

1. `config.json` in diesem Ordner anlegen (siehe Haupt-README). Falls euer Server SSO/OIDC-Login nutzt: unbedingt `auth/get_token.py` verwenden für Auto-Refresh.
2. Die Standard-Nachricht anpassen — entweder direkt im Code (`DEFAULT_GUIDE_URL`, `DEFAULT_SENDER_NAME` am Anfang von `matrix_wrong_server_watchdog.py`) oder per CLI-Argument (siehe unten).

## Benutzung

```
python matrix_wrong_server_watchdog.py --room '!spaceid' --correct-domain matrix.eure-hochschule.de
```

Optionen:

- `--room` — Room-ID zum Überwachen (mehrfach angeben für mehrere Räume)
- `--correct-domain` — die korrekte Server-Domain eurer Hochschule (Pflicht)
- `--guide-url` — Link zur Anleitung "wie melde ich mich mit dem richtigen Server an"
- `--sender-name` — Name, mit dem die Nachricht unterschrieben wird, z.B. "deine Fachschaft Media"
- `--dry-run` — nur anzeigen, wer angeschrieben würde, ohne tatsächlich zu senden
- `--config` — Pfad zur config-Datei (Default: `config.json`)

Immer erst mit `--dry-run` testen.

## Dauerbetrieb einrichten

`start_watchdog.bat` anpassen (Pfade, Space-ID, Domain, Nachrichtentext) und über die Windows-Aufgabenplanung mit Trigger "Bei Systemstart" einrichten — Details im Haupt-README. Die `.bat`-Datei startet das Script automatisch neu, falls es mal abstürzt.

**Wichtig:** Falls parallel auch `sync-members` läuft, braucht dieses Script eine **eigene** `config.json`/Session (siehe Haupt-README, Abschnitt "Token-Tennis").

## Berechtigungen

Der ausführende Account muss in den überwachten Räumen Mitglied sein und DMs an andere Nutzer:innen schreiben dürfen.
