# Auth

Login-Helfer für Matrix-Server, die **SSO/OIDC-Login** statt klassischem Passwort-Login nutzen (z.B. Hochschul-Matrix-Server, die an ein zentrales Uni-Login gekoppelt sind).

## Woran erkennt man, ob man das braucht?

Klassisches `m.login.password` scheitert mit `{"errcode":"M_UNKNOWN","error":"Invalid login type"}`. Zur Bestätigung:

```
curl https://matrix.eure-hochschule.de/_matrix/client/v3/login
```

Zeigt die Antwort `m.login.sso` als unterstützten `flow`, ist SSO-Login der richtige Weg — und `get_token.py` das richtige Tool.

## Benutzung

```
python get_token.py --config ../wrong-server-watchdog/config.json
```

- Öffnet automatisch den Standard-Browser mit der SSO-Login-Seite eurer Hochschule
- Ihr meldet euch ganz normal per Uni-SSO an
- Das Script fängt den Login-Callback lokal ab, tauscht ihn gegen Access- und Refresh-Token, und schreibt beides in die angegebene `config.json`

**Wichtig:** `--config` ist relativ zum Ordner, aus dem ihr das Script aufruft (nicht relativ zum `auth/`-Ordner selbst) — so landet die `config.json` direkt dort, wo das jeweilige Tool sie erwartet.

## Wann erneut ausführen?

Nur **einmalig** pro Tool/Session nötig. Danach holen sich die Dauerlauf-Scripts (`sync_members_watchdog`, `wrong_server_watchdog`) über den gespeicherten `refresh_token` automatisch neue Access-Tokens, sobald der alte abläuft (siehe `lib/matrix_auth.py`). Nur falls der Refresh-Token selbst irgendwann ungültig wird (deutlich seltener), muss `get_token.py` erneut laufen.

## Falls kein SSO läuft

Nutzt euer Server klassisches Passwort-Login, braucht ihr dieses Tool nicht — dann reicht ein Access Token aus Element (Einstellungen → Hilfe & Info → Erweitert → Access Token), manuell in die `config.json` eingetragen. Beachtet, dass so geholte Tokens teils ebenfalls ablaufen können; ohne Refresh-Token bleibt dann nur manuelles Erneuern.
