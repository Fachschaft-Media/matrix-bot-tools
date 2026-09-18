# Matrix-Tools für Hochschulgruppen

Eine Sammlung von Tools zur Verwaltung großer Matrix/Element-Communities mit vielen Räumen und Mitgliedern — entstanden für die **Erstsemesterwoche (EWO)** und die **Fachschaft Media** der Hochschule Darmstadt, aber generell für jede Fachschaft, jeden AStA oder jede vergleichbare Hochschulgruppe nutzbar.

**Empfehlung:** Nutzt für diese Tools nicht euren persönlichen Matrix-Account, sondern das **Funktionskonto eurer Fachschaft** als "Bot"-Account. So bleibt die Automatisierung unabhängig von einzelnen Personen und läuft weiter, auch wenn sich Zuständigkeiten ändern.

## Was ist hier drin?

Alle Tools sind Unterbefehle von **einem** Programm: `matrix-tools`. Eine Übersicht bekommt ihr jederzeit mit `matrix-tools --help`, die Hilfe zu einem Befehl mit `matrix-tools <befehl> --help`.

| Befehl | Zweck | Anleitung |
|---|---|---|
| `matrix-tools login` | Einmaliger Login per Hochschul-SSO, holt Access- und Refresh-Token | [docs/login.md](docs/login.md) |
| `matrix-tools watchdog` | **Dauerlauf:** Wrong-Server-Check + beliebig viele Auto-Invite-Regeln über eine einzige `settings.json` | [docs/watchdog.md](docs/watchdog.md) |
| `matrix-tools broadcast` | Eine Nachricht gleichzeitig an viele Räume schicken (z.B. Ansagen an alle Gruppen-Räume) | [docs/broadcast.md](docs/broadcast.md) |
| `matrix-tools create-rooms` | Viele gleichartige Räume auf einmal erstellen (z.B. 150 Gruppenräume für ein Event) | [docs/create-rooms.md](docs/create-rooms.md) |
| `matrix-tools sync-members` | Mitglieder eines Space einmalig in einen anderen Raum einladen | [docs/sync-members.md](docs/sync-members.md) |

## Der Daten-Ordner

Alle Tools lesen und schreiben ihre Dateien in **einem** Ordner, dem Daten-Ordner:

| Datei | Inhalt | Vorlage |
|---|---|---|
| `config.json` | Zugangsdaten des Bot-Accounts (wird von `matrix-tools login` geschrieben) | [`examples/config.example.json`](examples/config.example.json) |
| `settings.json` | Regeln für den Watchdog | [`examples/settings.example.json`](examples/settings.example.json) |
| `rooms.txt` | Raumliste für Broadcasts (wird von `create-rooms` befüllt) | [`examples/rooms.example.txt`](examples/rooms.example.txt) |
| `notified_wrong_server.json` | Wird vom Watchdog automatisch angelegt | — |

- **Mit Docker** ist der Daten-Ordner `./data` neben der `compose.yml`.
- **Ohne Docker** ist es der Ordner, in dem ihr den Befehl ausführt. Alternativ könnt ihr ihn über die Umgebungsvariable `MATRIX_TOOLS_DATA_DIR` festlegen.

Alle Dateinamen lassen sich per `--config`, `--settings` oder `--rooms` ändern. Relative Pfade gelten dabei immer relativ zum Daten-Ordner. `config.json`, `settings.json`, `rooms.txt` und `data/` stehen in `.gitignore` und werden **nie** versehentlich eingecheckt.

## Variante 1: Mit Docker (empfohlen für den Dauerbetrieb)

Ihr braucht nur [Docker](https://docs.docker.com/get-docker/) — kein Python, kein Git.

1. Einen neuen Ordner anlegen und darin die [`compose.yml`](compose.yml) aus diesem Repository speichern.
2. Daneben einen Ordner `data` anlegen und die Vorlage [`examples/settings.example.json`](examples/settings.example.json) als `data/settings.json` hineinlegen und anpassen (siehe [docs/watchdog.md](docs/watchdog.md)).
3. Einmalig einloggen:
   ```
   docker compose run --rm --service-ports watchdog login --homeserver https://matrix.eure-hochschule.de
   ```
   Im Terminal erscheint ein Link. Öffnet ihn im Browser und meldet euch mit dem Bot-Account an. Danach liegt die fertige `data/config.json` bereit.
4. Den Watchdog dauerhaft im Hintergrund starten:
   ```
   docker compose up -d
   ```
   Er startet automatisch neu, falls er abstürzt oder der Rechner neu startet.

Nützliche Befehle:

```
docker compose logs -f                      # Ausgabe des Watchdogs live ansehen
docker compose pull && docker compose up -d # auf die neueste Version aktualisieren
docker compose down                         # Watchdog stoppen
```

Die anderen Tools laufen einmalig über denselben Container, z.B.:

```
docker compose run --rm watchdog broadcast "Wichtige Ansage an alle Gruppen"
docker compose run --rm watchdog create-rooms --count 20 --prefix "Gruppe"
docker compose run --rm watchdog sync-members --source '!spaceid' --target '!zielraumid' --dry-run
```

Ohne Compose geht es genauso mit `docker run`:

```
docker run --rm -it -v ./data:/data ghcr.io/fachschaft-media/matrix-bot-tools:latest --help
```

**Fehler "Permission denied" beim Schreiben der `config.json`?** Der Container läuft aus Sicherheitsgründen nicht als root, sondern als Benutzer mit der ID 1000. Legt den `data`-Ordner deshalb selbst an, bevor ihr den Container startet (sonst legt Docker ihn als root an). Falls euer Benutzer eine andere ID hat, hilft `sudo chown -R 1000:1000 data`.

Das Image gibt es unter `ghcr.io/fachschaft-media/matrix-bot-tools` für `linux/amd64` und `linux/arm64` (z.B. Raspberry Pi). `latest` ist der aktuelle Stand von `main`, Versionen wie `0.1.0` entsprechen den Git-Tags `v0.1.0`.

## Variante 2: Ohne Docker (mit uv)

Ihr braucht nur [uv](https://docs.astral.sh/uv/getting-started/installation/). uv lädt die passende Python-Version (3.14) und alle Abhängigkeiten automatisch herunter — Python müsst ihr nicht selbst installieren.

1. Dieses Repository herunterladen (`git clone` oder auf GitHub "Code" → "Download ZIP").
2. Im Repository-Ordner einmal prüfen, dass alles läuft:
   ```
   uv run matrix-tools --help
   ```
3. Einen Daten-Ordner anlegen (z.B. `data` im Repository-Ordner, der ist bereits in `.gitignore`), die benötigten Vorlagen aus `examples/` hineinkopieren und anpassen.
4. Im Daten-Ordner einloggen und loslegen (`--project` zeigt auf den Repository-Ordner):
   ```
   cd data
   uv run --project .. matrix-tools login --homeserver https://matrix.eure-hochschule.de
   uv run --project .. matrix-tools watchdog --dry-run
   ```

Tipp: Mit `uv tool install .` (im Repository-Ordner) wird `matrix-tools` dauerhaft installiert. Danach reicht in jedem Ordner einfach `matrix-tools …`.

### Windows-Dauerbetrieb

Im Ordner [`windows/`](windows/) liegen fertige `.bat`-Dateien:

- `start_watchdog.bat` — hält den Watchdog in einer Neustart-Schleife am Laufen und schreibt ein Log
- `run_sync_members.bat` — einmaliger Mitglieder-Abgleich, z.B. stündlich über den Taskplaner

Oben in der Datei die mit `ANPASSEN` markierten Pfade eintragen. Für den echten Dauerbetrieb (auch nach einem Neustart, ohne offenes Terminal-Fenster):

1. Windows-Aufgabenplanung öffnen
2. Neue Aufgabe: Trigger "Bei Systemstart", Aktion "Programm starten" → Pfad zur `.bat`-Datei
3. Unter "Sicherheitsoptionen": "Unabhängig von der Benutzeranmeldung ausführen"
4. Unter "Einstellungen": "Aufgabe beenden, falls sie länger als..." **deaktivieren** (sonst wird der Dauerlauf beendet)

## Zugangsdaten: config.json

```
{
  "homeserver": "https://matrix.eure-hochschule.de",
  "user_id": "@euer-funktionskonto:matrix.eure-hochschule.de",
  "access_token": "...",
  "refresh_token": "..."
}
```

Wie ihr an die Zugangsdaten kommt, hängt vom Login-Verfahren eures Matrix-Servers ab:

- **SSO/OIDC-Login** (z.B. wenn eure Hochschule Matrix an ein zentrales Uni-Login gekoppelt hat — erkennbar daran, dass `m.login.password` mit `Invalid login type` fehlschlägt): `matrix-tools login` schickt euch per Browser durch den SSO-Login und schreibt Access- **und** Refresh-Token automatisch in die `config.json`. Mit dem Refresh-Token holt sich der Watchdog danach **selbst** neue Tokens, ganz ohne manuelles Eingreifen. Details: [docs/login.md](docs/login.md).
- **Klassisches Passwort-Login:** Access Token einmalig über Element holen (Einstellungen → Hilfe & Info → Erweitert → Access Token) und zusammen mit `homeserver` und `user_id` manuell in die `config.json` eintragen. Läuft er irgendwann ab, müsst ihr ihn manuell erneuern.

**Mehrere Dauerläufe gleichzeitig?** Jeder dauerhaft laufende Prozess braucht eine **eigene** `config.json` mit einer **eigenen** Login-Session (per `matrix-tools login --config <eigene-datei>.json`). Teilen sich zwei Prozesse dieselbe Session, macht ein Token-Refresh im einen den Token im anderen ungültig ("Token-Tennis"). Am einfachsten: alles in **einem** `matrix-tools watchdog` mit mehreren Regeln kombinieren.

## Mitentwickeln

```
uv sync                      # Abhängigkeiten inkl. Entwicklungs-Tools installieren
uv run ruff format           # Code formatieren
uv run ruff check            # Linting
uv run pyright               # Typprüfung
```

Die GitHub-Action prüft bei jedem Push und Pull Request Formatierung, Linting, Typen und die SonarQube-Cloud-Analyse. Nur wenn alles grün ist, wird das Docker-Image von `main` und von `v*`-Tags nach `ghcr.io` veröffentlicht. Welche Ruff-Regeln bewusst deaktiviert sind und wie ihr sie schrittweise wieder aktiviert: [docs/code-qualitaet.md](docs/code-qualitaet.md).

## Lizenz / Weiterverwendung

Baut gerne darauf auf, passt es an eure Hochschule an, gebt Verbesserungen zurück. Ersetzt überall die Platzhalter (`matrix.eure-hochschule.de`, Beispiel-IDs) durch eure echten Werte.
