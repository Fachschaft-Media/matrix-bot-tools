# Broadcast

Schickt eine Nachricht gleichzeitig an viele Matrix-Räume — z.B. eine Ansage an alle Gruppen-Räume eines Events.

## Setup

1. `config.json` in diesem Ordner anlegen (siehe Haupt-README)
2. `rooms.example.txt` nach `rooms.txt` kopieren und mit euren echten Räumen befüllen — eine Zeile pro Raum, entweder als Room-ID (`!...`) oder als Alias (`#...`, wird automatisch aufgelöst)

## Benutzung

```
python matrix_broadcast.py "Wichtige Ansage an alle Gruppen"
```

Weitere Optionen:

- Nachricht aus Datei lesen (für lange Texte): `--file ansage.txt`
- Mit Markdown-Formatierung senden (fett, Listen etc.): `--markdown`
- Nur an eine Teilmenge senden: `--rooms andere-liste.txt`
- Direkt per Alias-Range senden, ohne `rooms.txt` zu befüllen:
  ```
  python matrix_broadcast.py "Ansage" --alias-range '#gruppe-001:matrix.eure-hochschule.de..#gruppe-150:matrix.eure-hochschule.de'
  ```

Der ausführende Account muss in allen Zielräumen Mitglied sein.
