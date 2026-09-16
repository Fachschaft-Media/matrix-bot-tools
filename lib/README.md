# lib

Geteiltes Hilfsmodul, kein eigenständiges Tool.

`matrix_auth.py` stellt `refresh_access_token()` bereit: erneuert automatisch den Access Token über den in der `config.json` gespeicherten `refresh_token`, wenn der Server einen abgelaufenen/ungültigen Token meldet. Wird von den beiden Dauerlauf-Scripts (`sync-members/matrix_sync_members_watchdog.py`, `wrong-server-watchdog/matrix_wrong_server_watchdog.py`) importiert.

Setzt voraus, dass die jeweilige `config.json` einen `refresh_token` enthält — den bekommt ihr über `auth/get_token.py`.

Muss nicht direkt aufgerufen werden.
