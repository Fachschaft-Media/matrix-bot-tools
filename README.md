# Matrix-Tools für Hochschulgruppen

Eine Sammlung von Python-Scripts zur Verwaltung großer Matrix/Element-Communities mit vielen Räumen und Mitgliedern — entstanden für die **Erstsemesterwoche (EWO)** und die **Fachschaft Media** der Hochschule Darmstadt, aber generell für jede Fachschaft, jeden AStA oder jede vergleichbare Hochschulgruppe nutzbar.

**Empfehlung:** Nutzt für diese Tools nicht euren persönlichen Matrix-Account, sondern das **Funktionskonto eurer Fachschaft** (bzw. ein separates Konto pro Tool) als "Bot"-Account. So bleibt die Automatisierung unabhängig von einzelnen Personen und läuft weiter, auch wenn sich Zuständigkeiten ändern.

## Was ist hier drin?

| Ordner | Zweck |
|---|---|
| [`broadcast/`](broadcast/README.md) | Eine Nachricht gleichzeitig an viele Räume schicken (z.B. Ansagen an alle Gruppen-Räume) |
| [`create-rooms/`](create-rooms/README.md) | Viele gleichartige Räume auf einmal erstellen (z.B. 150 Gruppenräume für ein Event) |
| [`sync-members/`](sync-members/README.md) | Mitglieder eines Space automatisch in einen anderen Raum einladen (einmalig oder live) |
| [`wrong-server-watchdog/`](wrong-server-watchdog/README.md) | Neue Mitglieder mit falschem Matrix-Server automatisch per DM auf den Fehler hinweisen |
| [`auth/`](auth/README.md) | Login-Helfer für Hochschul-SSO/OIDC-Server, holt Access- und Refresh-Token |
| `lib/` | Geteiltes Hilfsmodul (`matrix_auth.py`) für automatischen Token-Refresh, wird von den Dauerlauf-Scripts genutzt |

Jeder Ordner hat sein eigenes README mit genauer Anleitung. Dieses Haupt-README erklärt nur den gemeinsamen Unterbau.

## Voraussetzungen

- Python 3.10 oder neuer
- Abhängigkeiten installieren:
  ```
  pip install -r requirements.txt
  ```
- Ein Matrix-Account (idealerweise ein Funktionskonto), der in den relevanten Räumen Mitglied ist bzw. die nötigen Rechte hat (Einladen, Senden, o.ä. je nach Tool)

## Zugangsdaten: config.json

Alle Scripts lesen ihre Zugangsdaten aus einer `config.json` im jeweiligen Tool-Ordner. Kopiert `config.example.json` (im Hauptordner) in den jeweiligen Tool-Ordner und benennt sie in `config.json` um:

```
{
  "homeserver": "https://matrix.eure-hochschule.de",
  "user_id": "@euer-funktionskonto:matrix.eure-hochschule.de",
  "access_token": "...",
  "refresh_token": "..."
}
```

`access_token` und `refresh_token` müsst ihr **nicht** manuell eintragen — das übernimmt `auth/get_token.py` für euch (siehe unten). `config.json` steht in `.gitignore` und wird **nie** versehentlich mit eingecheckt.

### Zwei Arten von Matrix-Login

Wie ihr an Zugangsdaten kommt, hängt vom Login-Verfahren eures Matrix-Servers ab:

- **Klassisches Passwort-Login:** Access Token einmalig über Element holen (Einstellungen → Hilfe & Info → Erweitert → Access Token) und manuell in `config.json` eintragen. Läuft ggf. irgendwann ab, dann Token manuell erneuern.
- **SSO/OIDC-Login** (z.B. wenn eure Hochschule Matrix an ein zentrales Uni-Login gekoppelt hat — erkennbar daran, dass `m.login.password` mit `Invalid login type` fehlschlägt): Nutzt `auth/get_token.py`, das euch per Browser durch den SSO-Login schickt und automatisch Access- **und** Refresh-Token holt. Mit dem Refresh-Token können sich die Dauerlauf-Scripts (die beiden Watchdogs) danach **selbst** neue Tokens holen, ganz ohne manuelles Eingreifen — wichtig, weil SSO/OIDC-Server Access Tokens oft bewusst kurzlebig ausstellen.

**Wichtig, wenn mehrere Dauerlauf-Scripts gleichzeitig laufen:** Jedes Script braucht eine **eigene** `config.json` mit einer **eigenen** Login-Session (eigener `device_id`). Teilen sich zwei Scripts dieselbe Session, invalidiert ein Token-Refresh im einen Script den gerade aktiven Token im anderen — das führt zu einer Endlosschleife aus gegenseitigen Refreshes ("Token-Tennis"). Für jedes Dauerlauf-Script also mit `--config <eigene-datei>.json` eine eigene Session anlegen.

## Einmalig laufende Scripts vs. Dauerlauf-Scripts

Zwei Kategorien von Tools hier:

- **Einmalig/periodisch** (`matrix_broadcast.py`, `matrix_create_rooms.py`, `matrix_sync_members.py`): Werden einmal ausgeführt und beenden sich danach. Eignen sich für manuellen Aufruf oder für den Taskplaner/Cron mit einem Zeit-Trigger (z.B. stündlich).
- **Dauerlauf** (`matrix_sync_members_watchdog.py`, `matrix_wrong_server_watchdog.py`): Laufen permanent im Hintergrund und reagieren live auf Events (z.B. neue Beitritte). Eignen sich für den Taskplaner mit Trigger "Bei Systemstart" + Auto-Neustart-Schleife (siehe die `.bat`-Dateien in den jeweiligen Ordnern).

## Windows-Dauerbetrieb einrichten

Für die beiden Watchdog-Scripts liegt je eine `.bat`-Datei bei, die das Script in einer Neustart-Schleife hält (falls es mal abstürzt). Für den echten Dauerbetrieb (auch nach Server-Neustart, ohne offenes Terminal-Fenster):

1. Windows-Aufgabenplanung öffnen
2. Neue Aufgabe: Trigger "Bei Systemstart", Aktion "Programm starten" → Pfad zur jeweiligen `.bat`-Datei
3. Unter "Sicherheitsoptionen": "Unabhängig von der Benutzeranmeldung ausführen"
4. Unter "Einstellungen": "Aufgabe beenden, falls sie länger als..." **deaktivieren** (sonst wird der Dauerlauf gekillt)

Details dazu auch im jeweiligen Tool-README.

## Lizenz / Weiterverwendung

Baut gerne darauf auf, passt es an eure Hochschule an, gebt Verbesserungen zurück. Ersetzt überall die Platzhalter (`matrix.eure-hochschule.de`, Beispiel-IDs) durch eure echten Werte.
