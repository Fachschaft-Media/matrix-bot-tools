# Sync Members (`matrix-tools sync-members`)

Lädt **einmalig** alle Mitglieder eines oder mehrerer Spaces/Räume in einen anderen Raum ein — z.B. alle Mitglieder eures Fachschafts-Space in die Gruppe "Aktive Fachschaft".

Wer die Einladung bereits abgelehnt hat, den Zielraum wieder verlassen hat, gebannt ist oder schon eine offene (unbeantwortete) Einladung hat, wird **nicht** erneut eingeladen. Kann der Zielraum nicht gelesen werden, wird deshalb **niemand** eingeladen und der Befehl endet mit Exit-Code 1.

**Live statt einmalig?** Soll jede neu beitretende Person sofort eingeladen werden, nutzt stattdessen [`matrix-tools watchdog`](watchdog.md) mit einer Auto-Invite-Regel. Beide verwenden dieselbe Einladungs-Logik.

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

Mitglieder mehrerer Quellräume zusammen einladen (z.B. "ausgewählte Kanäle → Space"), dazu `--source` mehrfach angeben:

```
matrix-tools sync-members --source '!kanal1' --source '!kanal2' --target '!spaceid'
```

Mit Docker:

```
docker compose run --rm watchdog sync-members --source '!spaceid' --target '!zielraumid' --dry-run
```

Optionen:

- `--source` — Room-ID eines Quellraums, z.B. der Space (Pflicht, mehrfach angebbar)
- `--target` — Room-ID des Zielraums (Pflicht)
- `--dry-run` — nur anzeigen, wer eingeladen würde
- `--config` — andere Zugangsdaten verwenden

## Periodisch unter Windows

[`windows/run_sync_members.bat`](../windows/run_sync_members.bat) anpassen (Pfade, Space-/Raum-IDs) und in der Windows-Aufgabenplanung mit einem Zeit-Trigger (z.B. stündlich) einrichten.

## Berechtigungen

Der ausführende Account braucht Mitgliedschaft in allen Quellräumen und im Zielraum sowie Einlade-Rechte (Moderator/Admin-Power-Level) im Zielraum.

## Fehlerbehebung

Fehlermeldungen haben immer die Form `❌ <Aktion> fehlgeschlagen - <Fehlercode>: <Meldung des Servers>`. Der Fehlercode sagt, was schiefging:

| Fehlercode | Wahrscheinliche Ursache | Lösung |
|---|---|---|
| `M_UNKNOWN_TOKEN` | Access Token abgelaufen. Der Befehl bricht sofort ab. | `matrix-tools login --config <config.json>` ausführen und den Befehl erneut starten. Bereits Eingeladene werden automatisch übersprungen. |
| `M_FORBIDDEN` bei „Mitglieder von … lesen“ | Der Account ist nicht Mitglied des Quellraums. | Account in den Quellraum/Space einladen und beitreten lassen. |
| `M_FORBIDDEN` bei „Mitgliedschaften in … lesen“ | Der Account ist nicht Mitglied des Zielraums. | Account in den Zielraum einladen und beitreten lassen. |
| `M_FORBIDDEN` bei „Einladung von …“ | Power-Level im Zielraum reicht nicht zum Einladen. | Account im Zielraum zum Moderator/Admin machen. |
| `M_NOT_FOUND`, `M_INVALID_PARAM` | Room-ID falsch kopiert (Tippfehler oder Alias `#...` statt Room-ID `!...`). | Room-ID in Element unter Raumeinstellungen → Erweitert kopieren. |
| `M_LIMIT_EXCEEDED` | Rate-Limit des Servers, zu viele Einladungen in kurzer Zeit. | Kurz warten und den Befehl erneut starten, bereits Eingeladene werden übersprungen. |
| `ClientConnectorError`, `TimeoutError` | Server nicht erreichbar oder falsche `homeserver`-URL in der `config.json`. | Internetverbindung und `homeserver` in der `config.json` prüfen. |
