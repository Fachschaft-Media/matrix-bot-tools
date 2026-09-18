#!/usr/bin/env python3
"""
Matrix SSO-Login
================
Holt sich per SSO-Browser-Login (Uni-Anmeldung) einen frischen Access Token
UND einen Refresh Token, und schreibt beides automatisch in die config.json.

Nötig, weil viele Hochschul-Matrix-Server SSO/OIDC-Login statt Passwort-Login
nutzen und Access Tokens kurzlebig sind. Mit dem Refresh Token kann sich der
Watchdog selbst automatisch neue Access Tokens holen, ohne dass du manuell
eingreifen musst.

BENUTZUNG
---------
    matrix-tools login --homeserver https://matrix.eure-hochschule.de
    matrix-tools login --config config_broadcast.json

Öffnet automatisch den Standard-Browser, du meldest dich per Uni-SSO an,
danach wird die angegebene config-Datei aktualisiert (bzw. neu angelegt).
Im Docker-Container wird statt des Browsers der Login-Link ausgegeben.

Muss pro config-Datei nur EINMALIG ausgeführt werden (oder wenn der Refresh
Token doch mal ungültig werden sollte).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from matrix_tools.paths import resolve

IN_DOCKER_ENV = "MATRIX_TOOLS_IN_DOCKER"
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


def add_arguments(parser):
    parser.add_argument(
        "--config",
        default="config.json",
        help="Pfad zur config-Datei, die geschrieben werden soll (Default: config.json).",
    )
    parser.add_argument(
        "--homeserver",
        help="URL eures Matrix-Servers, z.B. https://matrix.eure-hochschule.de "
        "(Default: der Wert aus der bestehenden config-Datei).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Browser nicht automatisch öffnen, nur den Login-Link ausgeben "
        "(im Docker-Container automatisch aktiv).",
    )


def run(args):
    config_path = resolve(args.config)
    in_docker = os.environ.get(IN_DOCKER_ENV) == "1"

    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    homeserver = (args.homeserver or config.get("homeserver", "")).rstrip("/")
    if not homeserver:
        print("❌ Kein Homeserver bekannt. Bitte mit --homeserver angeben, z.B.:")
        print("   matrix-tools login --homeserver https://matrix.eure-hochschule.de")
        sys.exit(1)

    print("🔐 Matrix SSO-Login wird gestartet...")
    print(f"   Ziel-Datei: {config_path}")
    print("   Falls sich der Browser nicht automatisch öffnet, rufe manuell auf:")
    sso_url = f"{homeserver}/_matrix/client/v3/login/sso/redirect?redirectUrl={CALLBACK_URL}"
    print(f"   {sso_url}\n")

    # Im Container muss der Callback-Server von außen (Port-Weiterleitung) erreichbar sein.
    bind_host = "0.0.0.0" if in_docker else "127.0.0.1"
    server = HTTPServer((bind_host, CALLBACK_PORT), CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    if not (args.no_browser or in_docker):
        webbrowser.open(sso_url)

    print("⏳ Warte auf Login im Browser (max. 5 Minuten)...")
    server_thread.join(timeout=300)

    login_token = login_token_holder.get("token")
    if not login_token:
        print("❌ Kein Login-Token erhalten (Timeout oder Abbruch). Bitte nochmal versuchen.")
        sys.exit(1)

    print("✅ Login-Token erhalten. Tausche gegen Access Token...")

    resp = requests.post(
        f"{homeserver}/_matrix/client/v3/login",
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
        print(
            "⚠️  Server hat KEINEN refresh_token ausgestellt. Auto-Refresh wird nicht möglich sein -"
        )
        print(
            "   die Dauerlauf-Scripts werden dann weiterhin regelmäßig manuell erneuert werden müssen."
        )

    config["homeserver"] = homeserver
    config["user_id"] = user_id
    config["access_token"] = access_token
    if refresh_token:
        config["refresh_token"] = refresh_token
    if expires_in_ms:
        config["expires_in_ms"] = expires_in_ms

    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n✅ {config_path.name} aktualisiert für {user_id}.")
    if refresh_token:
        print(
            "✅ Refresh Token gespeichert - die Dauerlauf-Scripts können sich jetzt selbst erneuern."
        )
