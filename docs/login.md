# Login (`matrix-tools login`)

Login-Helfer für Matrix-Server, die **SSO/OIDC-Login** statt klassischem Passwort-Login nutzen (z.B. Hochschul-Matrix-Server, die an ein zentrales Uni-Login gekoppelt sind).

## Woran erkennt man, ob man das braucht?

Klassisches `m.login.password` scheitert mit `{"errcode":"M_UNKNOWN","error":"Invalid login type"}`. Zur Bestätigung:

```
curl https://matrix.eure-hochschule.de/_matrix/client/v3/login
```

Zeigt die Antwort `m.login.sso` als unterstützten `flow`, ist SSO-Login der richtige Weg — und `matrix-tools login` das richtige Tool.

## Benutzung

Ohne Docker (im Daten-Ordner):

```
matrix-tools login --homeserver https://matrix.eure-hochschule.de
```

Mit Docker:

```
docker compose run --rm --service-ports watchdog login --homeserver https://matrix.eure-hochschule.de
```

- Ohne Docker öffnet sich automatisch der Browser mit der SSO-Login-Seite eurer Hochschule. Im Docker-Container (oder mit `--no-browser`) wird stattdessen ein Link ausgegeben, den ihr selbst im Browser öffnet.
- Ihr meldet euch ganz normal per Uni-SSO mit dem Bot-Account an.
- Das Tool fängt den Login-Callback auf Port `8765` ab, tauscht ihn gegen Access- und Refresh-Token und schreibt beides in die `config.json` im Daten-Ordner.

Optionen:

- `--homeserver` — URL eures Matrix-Servers. Beim ersten Login Pflicht, danach wird der Wert aus der bestehenden `config.json` übernommen.
- `--config` — andere Ziel-Datei als `config.json`, z.B. für eine zweite, getrennte Session
- `--no-browser` — Browser nicht automatisch öffnen, nur den Link ausgeben

## Wann erneut ausführen?

Nur **einmalig** pro `config.json` nötig. Danach holt sich der Watchdog über den gespeicherten `refresh_token` automatisch neue Access-Tokens, sobald der alte abläuft. Nur falls der Refresh-Token selbst irgendwann ungültig wird (deutlich seltener), muss `matrix-tools login` erneut laufen.

## Falls kein SSO läuft

Nutzt euer Server klassisches Passwort-Login, braucht ihr dieses Tool nicht. Dann reicht ein Access Token aus Element (Einstellungen → Hilfe & Info → Erweitert → Access Token), den ihr manuell in die `config.json` eintragt (Vorlage: [`examples/config.example.json`](../examples/config.example.json)). Beachtet, dass so geholte Tokens teils ebenfalls ablaufen können; ohne Refresh-Token bleibt dann nur manuelles Erneuern.
