#!/usr/bin/env python3
"""
Matrix SSO-Token-Holer
========================
Holt sich per SSO-Browser-Login (Uni-Anmeldung) einen frischen Access Token
UND einen Refresh Token, und schreibt beides automatisch in die config.json.

Nötig, weil der h_da-Matrix-Server SSO/OIDC-Login statt Passwort-Login nutzt
und Access Tokens kurzlebig sind. Mit dem Refresh Token können die anderen
Dauerlauf-Scripts (matrix_wrong_server_watchdog.py, matrix_sync_members_watchdog.py)
sich selbst automatisch neue Access Tokens holen, ohne dass du manuell
eingreifen musst.

BENUTZUNG
---------
    python get_token.py
    python get_token.py --config config_wrongserver.json
    python get_token.py --config config_sync.json

Öffnet automatisch den Standard-Browser, du meldest dich per Uni-SSO an,
danach schließt sich das Browserfenster von selbst und die angegebene
config-Datei wird aktualisiert (bzw. neu angelegt).

WICHTIG bei mehreren gleichzeitig laufenden Dauerlauf-Scripts: Jedes Script
braucht eine EIGENE config-Datei mit einer EIGENEN Login-Session (eigener
device_id). Teilen sich zwei Scripts dieselbe config.json/Session, invalidiert
ein Token-Refresh im einen Script den gerade aktiven Token im anderen -
das führt zu einer Endlosschleife aus gegenseitigen Refreshes ("Token-Tennis").
Für jedes Dauerlauf-Script also einmal get_token.py mit eigenem --config
Pfad ausführen.

Muss pro config-Datei nur EINMALIG ausgeführt werden (oder wenn der Refresh
Token doch mal ungültig werden sollte).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOMESERVER = "https://matrix.eure-hochschule.de"
CALLBACK_PORT = 8765
CALLBACK_URL = f"http://127.0.0.1:{CALLBACK_PORT}/callback"

login_token_holder = {}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token = params.get("loginToken", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        if token:
            login_token_holder["token"] = token
            self.wfile.write(
                "<html><body style='font-family:sans-serif;padding:40px'>"
                "<h2>✅ Erfolgreich angemeldet!</h2>"
                "<p>Du kannst dieses Fenster jetzt schließen und zum Terminal zurückkehren.</p>"
                "</body></html>".encode("utf-8")
            )
        else:
            self.wfile.write(
                "<html><body style='font-family:sans-serif;padding:40px'>"
                "<h2>❌ Kein Login-Token erhalten</h2>"
                "<p>Bitte Terminal prüfen.</p>"
                "</body></html>".encode("utf-8")
            )

    def log_message(self, format, *args):
        pass  # Terminal nicht mit HTTP-Server-Logs zuspammen


def main():
    parser = argparse.ArgumentParser(description="Holt einen frischen Matrix-Token per SSO-Login.")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Pfad zur config-Datei, die geschrieben werden soll (Default: config.json). "
             "Für mehrere parallel laufende Scripts unterschiedliche Dateien verwenden!",
    )
    args = parser.parse_args()
    config_path = Path(args.config)  # relativ zum aktuellen Arbeitsverzeichnis, NICHT zum Skript-Ordner

    print("🔐 Matrix SSO-Login wird gestartet...")
    print(f"   Ziel-Datei: {config_path}")
    print(f"   Falls sich der Browser nicht automatisch öffnet, rufe manuell auf:")
    sso_url = f"{HOMESERVER}/_matrix/client/v3/login/sso/redirect?redirectUrl={CALLBACK_URL}"
    print(f"   {sso_url}\n")

    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    webbrowser.open(sso_url)

    print("⏳ Warte auf Login im Browser (max. 5 Minuten)...")
    server_thread.join(timeout=300)

    login_token = login_token_holder.get("token")
    if not login_token:
        print("❌ Kein Login-Token erhalten (Timeout oder Abbruch). Bitte nochmal versuchen.")
        sys.exit(1)

    print("✅ Login-Token erhalten. Tausche gegen Access Token...")

    resp = requests.post(
        f"{HOMESERVER}/_matrix/client/v3/login",
        json={
            "type": "m.login.token",
            "token": login_token,
            "refresh_token": True,  # bittet den Server explizit um einen Refresh Token
        },
    )

    if resp.status_code != 200:
        print(f"❌ Token-Austausch fehlgeschlagen: {resp.status_code} {resp.text}")
        sys.exit(1)

    data = resp.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    user_id = data.get("user_id")
    expires_in_ms = data.get("expires_in_ms")

    if not access_token:
        print(f"❌ Kein access_token in der Antwort: {data}")
        sys.exit(1)

    if not refresh_token:
        print("⚠️  Server hat KEINEN refresh_token ausgestellt. Auto-Refresh wird nicht möglich sein -")
        print("   die Dauerlauf-Scripts werden dann weiterhin regelmäßig manuell erneuert werden müssen.")

    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    config["homeserver"] = HOMESERVER
    config["user_id"] = user_id
    config["access_token"] = access_token
    if refresh_token:
        config["refresh_token"] = refresh_token
    if expires_in_ms:
        config["expires_in_ms"] = expires_in_ms

    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n✅ {config_path.name} aktualisiert für {user_id}.")
    if refresh_token:
        print("✅ Refresh Token gespeichert - die Dauerlauf-Scripts können sich jetzt selbst erneuern.")


if __name__ == "__main__":
    main()
