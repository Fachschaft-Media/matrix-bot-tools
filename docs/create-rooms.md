# Create Rooms (`matrix-tools create-rooms`)

Erstellt automatisiert viele gleichartige Matrix-Räume — z.B. 150 Gruppenräume für ein Event — und hängt sie optional direkt in einen bestehenden Space ein.

## Setup

`config.json` im Daten-Ordner anlegen (siehe Haupt-README).

## Benutzung

```
matrix-tools create-rooms --count 150 --prefix "Gruppe" --alias-prefix "event-gr" --public --space '!eureSpaceId:matrix.eure-hochschule.de'
```

Mit Docker:

```
docker compose run --rm watchdog create-rooms --count 150 --prefix "Gruppe"
```

Das erzeugt z.B. Räume `Gruppe-001` bis `Gruppe-150` mit Aliassen `#event-gr-001` bis `#event-gr-150`. Die Nummern werden immer auf mindestens zwei Stellen aufgefüllt (`01`), bei dreistelligen Nummern auf drei (`001`).

Optionen:

- `--count` — Anzahl der Räume (Pflicht)
- `--prefix` — Namens-Präfix (Default: "Gruppe")
- `--start` — Startnummer, falls schon welche existieren (Default: 1)
- `--space` — Space-ID, in die die Räume eingehängt werden sollen (Alias oder interne ID, beides geht)
- `--alias-prefix` — wenn gesetzt, bekommt jeder Raum zusätzlich einen Alias
- `--public` — Räume öffentlich statt invite-only erstellen (Default: privat)
- `--rooms-out` — Datei im Daten-Ordner, an die die neuen Room-IDs angehängt werden (Default: `rooms.txt`, direkt nutzbar für `matrix-tools broadcast`)
- `--config` — andere Zugangsdaten verwenden

Der Ersteller-Account ist automatisch Mitglied jedes erstellten Raums — eine separate Einladung ist nicht nötig, z.B. für spätere Broadcasts.

## Fehlerbehebung

Fehlermeldungen haben immer die Form `❌ <Aktion> fehlgeschlagen - <Fehlercode>: <Meldung des Servers>`. Der Fehlercode sagt, was schiefging:

| Fehlercode | Wahrscheinliche Ursache | Lösung |
|---|---|---|
| `M_UNKNOWN_TOKEN` | Access Token abgelaufen. Der Befehl bricht sofort ab; die Room-IDs der bis dahin erstellten Räume werden trotzdem an `--rooms-out` angehängt. | `matrix-tools login --config <config.json>` ausführen und mit `--start <nächste Nummer>` und der restlichen `--count` weitermachen. |
| `M_ROOM_IN_USE` | Der Alias (`--alias-prefix`) ist schon vergeben, z.B. von einem früheren Lauf. | Anderen `--alias-prefix` wählen oder mit `--start` hinter den vorhandenen Nummern weitermachen. |
| `M_INVALID_PARAM` | Ungültiger Alias, z.B. mit Leerzeichen oder Sonderzeichen im `--alias-prefix`. | Nur Kleinbuchstaben, Ziffern und `-` verwenden. |
| `M_FORBIDDEN` (bei „Konnte nicht in Space eingehängt werden“) | Der Account darf im Space keine Räume hinzufügen (Power-Level) oder ist nicht Mitglied des Spaces. Der Raum selbst wurde trotzdem erstellt. | Account im Space zum Moderator/Admin machen; die Räume danach in Element von Hand hinzufügen. |
| `M_LIMIT_EXCEEDED` | Rate-Limit des Servers, zu viele Räume in kurzer Zeit. | Kurz warten und die fehlgeschlagenen Nummern mit `--start`/`--count` erneut erstellen. |
| `ClientConnectorError`, `TimeoutError` | Server nicht erreichbar oder falsche `homeserver`-URL in der `config.json`. | Internetverbindung und `homeserver` in der `config.json` prüfen. |

## Space-ID finden

Nicht verwechseln: Der öffentliche **Alias** (`#name:server`) ist nicht dasselbe wie die interne **Room-ID** (`!zufallsstring:server` bzw. bei neueren Matrix-Räumen ganz ohne `:server`-Suffix). Beide funktionieren als `--space`-Wert, aber falls ihr die interne ID braucht: Element → Space öffnen → Einstellungen → Erweitert → Interne Raum-ID.
