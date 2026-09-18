# Broadcast (`matrix-tools broadcast`)

Schickt eine Nachricht gleichzeitig an viele Matrix-Räume — z.B. eine Ansage an alle Gruppen-Räume eines Events.

## Setup

1. `config.json` im Daten-Ordner anlegen (siehe Haupt-README)
2. [`examples/rooms.example.txt`](../examples/rooms.example.txt) als `rooms.txt` in den Daten-Ordner kopieren und mit euren echten Räumen befüllen — eine Zeile pro Raum, entweder als Room-ID (`!...`) oder als Alias (`#...`, wird automatisch aufgelöst)

## Benutzung

```
matrix-tools broadcast "Wichtige Ansage an alle Gruppen"
```

Mit Docker:

```
docker compose run --rm watchdog broadcast "Wichtige Ansage an alle Gruppen"
```

Weitere Optionen:

- Nachricht aus Datei im Daten-Ordner lesen (für lange Texte): `--file ansage.txt`
- Mit Markdown-Formatierung senden (fett, Listen etc.): `--markdown`
- Nur an eine Teilmenge senden: `--rooms andere-liste.txt`
- Andere Zugangsdaten verwenden: `--config andere-config.json`
- Direkt per Alias-Range senden, ohne `rooms.txt` zu befüllen:
  ```
  matrix-tools broadcast "Ansage" --alias-range '#gruppe-001:matrix.eure-hochschule.de..#gruppe-150:matrix.eure-hochschule.de'
  ```

Der ausführende Account muss in allen Zielräumen Mitglied sein.
