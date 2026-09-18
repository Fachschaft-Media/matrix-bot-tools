# Create Rooms

Erstellt automatisiert viele gleichartige Matrix-Räume — z.B. 150 Gruppenräume für ein Event — und hängt sie optional direkt in einen bestehenden Space ein.

## Setup

`config.json` in diesem Ordner anlegen (siehe Haupt-README).

## Benutzung

```
python matrix_create_rooms.py --count 150 --prefix "Gruppe" --alias-prefix "event-gr" --public --space '!eureSpaceId:matrix.eure-hochschule.de'
```

Das erzeugt z.B. Räume `Gruppe-01` bis `Gruppe-150` mit Aliassen `#event-gr-01` bis `#event-gr-150`.

Optionen:

- `--count` — Anzahl der Räume (Pflicht)
- `--prefix` — Namens-Präfix (Default: "Gruppe")
- `--start` — Startnummer, falls schon welche existieren (Default: 1)
- `--space` — Space-ID, in die die Räume eingehängt werden sollen (Alias oder interne ID, beides geht)
- `--alias-prefix` — wenn gesetzt, bekommt jeder Raum zusätzlich einen Alias
- `--public` — Räume öffentlich statt invite-only erstellen (Default: privat)
- `--rooms-out` — Datei, an die die neuen Room-IDs angehängt werden (Default: `rooms.txt`, kompatibel mit `broadcast/` und `sync-members/`)

Der Ersteller-Account ist automatisch Mitglied jedes erstellten Raums — eine separate Einladung ist nicht nötig, z.B. für spätere Broadcasts.

## Space-ID finden

Nicht verwechseln: Der öffentliche **Alias** (`#name:server`) ist nicht dasselbe wie die interne **Room-ID** (`!zufallsstring:server` bzw. bei neueren Matrix-Räumen ganz ohne `:server`-Suffix). Beide funktionieren als `--space`-Wert, aber falls ihr die interne ID braucht: Element → Space öffnen → Einstellungen → Erweitert → Interne Raum-ID.
