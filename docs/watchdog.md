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
- Räume immer als Room-ID (`!...`) angeben, nicht als Alias (`#...`) — auch bei nur einem Raum als Liste in eckigen Klammern
- Ist der Wrong-Server-Check aktiv, sind `watch_rooms`, `correct_domain` und `guide_url` Pflicht
- Die Datei wird beim Start vollständig geprüft: unbekannte Schlüssel (z.B. Tippfehler wie `dryrun`), falsche Typen (`"true"` statt `true`) oder Aliase statt Room-IDs brechen den Start mit einer Liste aller Probleme ab. `_comment` ist überall als Kommentar erlaubt

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
2. Für jede Auto-Invite-Regel: einmaliger vollständiger Abgleich (Bestandsmitglieder der Quellräume, die noch nicht im Zielraum sind, werden eingeladen). Kann ein Quell- oder Zielraum nicht gelesen werden, wird die Regel beim Start übersprungen und niemand eingeladen
3. Der Wrong-Server-Check macht **keinen** initialen Abgleich — nur neue Beitritte ab dem Start werden geprüft, damit nicht rückwirkend Bestandsmitglieder angeschrieben werden
4. Danach: Dauerlauf, reagiert live auf jeden neuen Beitritt in allen überwachten Räumen

## Dauerbetrieb einrichten

- **Mit Docker:** `docker compose up -d` — der Container startet automatisch neu, falls der Prozess abstürzt oder der Rechner neu startet.
- **Windows ohne Docker:** [`windows/start_watchdog.bat`](../windows/start_watchdog.bat) anpassen (Pfade) und über die Windows-Aufgabenplanung mit Trigger "Bei Systemstart" einrichten — Details im Haupt-README. Die `.bat`-Datei startet den Prozess automatisch neu, falls er mal abstürzt.

## Fehlerbehebung

Der Watchdog beendet sich bei Fehlern **nie** selbst: jeder Fehler wird ausgegeben, danach läuft er weiter bzw. versucht es erneut. Ein abgelaufener Access Token wird automatisch per Refresh Token erneuert. Nur eine fehlende oder fehlerhafte `config.json`, `settings.json` oder `notified_wrong_server.json` beendet den Prozess beim Start, mit einer Liste aller gefundenen Probleme.

Fehlermeldungen haben immer die Form `❌ <Aktion> fehlgeschlagen - <Fehlercode>: <Meldung des Servers>`. Der Fehlercode sagt, was schiefging:

| Fehlercode / Meldung | Wahrscheinliche Ursache | Lösung |
|---|---|---|
| `M_UNKNOWN_TOKEN` mit „Der Access Token konnte nicht erneuert werden“ | Refresh Token fehlt oder ist ebenfalls abgelaufen (die Meldung davor zeigt die Antwort des Servers). Der Watchdog versucht es alle 60 s erneut. | `matrix-tools login --config <config.json>` ausführen, ein Neustart ist nicht nötig. |
| `M_FORBIDDEN` bei „Mitglieder von … lesen“ | Der Account ist nicht Mitglied eines Quellraums der Regel. | Account in den Quellraum einladen und beitreten lassen. |
| `M_FORBIDDEN` bei „Mitgliedschaften in … lesen“ | Der Account ist nicht Mitglied des Zielraums. Es wird niemand eingeladen. | Account in den Zielraum einladen und beitreten lassen. |
| `M_FORBIDDEN` bei „Einladung von …“ | Power-Level im Zielraum reicht nicht zum Einladen. | Account im Zielraum zum Moderator/Admin machen. |
| Fehler bei „DM-Raum mit … erstellen“ oder „Nachricht an … senden“ | Der Wrong-Server-Check konnte die DM nicht schicken, z.B. weil der andere Server Einladungen blockiert. Die Person wird nicht noch einmal angeschrieben. | Die Person bei Bedarf von Hand anschreiben. |
| `M_NOT_FOUND`, `M_INVALID_PARAM` | Room-ID in der `settings.json` falsch kopiert. | Room-ID in Element unter Raumeinstellungen → Erweitert kopieren. |
| `M_LIMIT_EXCEEDED` | Rate-Limit des Servers. | Nichts tun: beim nächsten Neustart holt der initiale Abgleich fehlende Einladungen nach. |
| `⚠️ Sync fehlgeschlagen` mit `ClientConnectorError` oder `TimeoutError` | Server kurzzeitig nicht erreichbar oder falsche `homeserver`-URL in der `config.json`. | Bei kurzen Ausfällen nichts tun, der Watchdog versucht es alle 10 s erneut. Hält es an: `homeserver` in der `config.json` prüfen. |
