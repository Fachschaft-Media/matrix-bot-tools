"""Matrix SSO-Login.

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

import os
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import requests

from matrix_tools.config import read_config, save_config
from matrix_tools.paths import resolve

if TYPE_CHECKING:
    import argparse

IN_DOCKER_ENV = "MATRIX_TOOLS_IN_DOCKER"
CALLBACK_PORT = 8765
CALLBACK_URL = f"http://127.0.0.1:{CALLBACK_PORT}/callback"
LOGIN_TIMEOUT_SECONDS = 300
REQUEST_TIMEOUT_SECONDS = 30

SUCCESS_PAGE = (
    "<html><body style='font-family:sans-serif;padding:40px'>"
    "<h2>✅ Erfolgreich angemeldet!</h2>"
    "<p>Du kannst dieses Fenster jetzt schließen und zum Terminal zurückkehren.</p>"
    "</body></html>"
)
FAILURE_PAGE = (
    "<html><body style='font-family:sans-serif;padding:40px'>"
    "<h2>❌ Kein Login-Token erhalten</h2>"
    "<p>Bitte Terminal prüfen.</p>"
    "</body></html>"
)


class CallbackServer(HTTPServer):
    """Lokaler HTTP-Server, der den Login-Token aus dem SSO-Redirect abfängt."""

    login_token: str | None = None


class CallbackHandler(BaseHTTPRequestHandler):
    """Beantwortet den SSO-Redirect und merkt sich den Login-Token."""

    def do_GET(self) -> None:
        """Liest den loginToken aus der Callback-URL."""
        params = parse_qs(urlparse(self.path).query)
        token = params.get("loginToken", [None])[0]

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        if token and isinstance(self.server, CallbackServer):
            self.server.login_token = token
            self.wfile.write(SUCCESS_PAGE.encode())
        else:
            self.wfile.write(FAILURE_PAGE.encode())

    def log_message(self, *_args: object, **_kwargs: object) -> None:
        """Unterdrückt HTTP-Server-Logs, damit das Terminal übersichtlich bleibt."""


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Registriert die Argumente von ``matrix-tools login``."""
    parser.add_argument(
        "--config",
        default="config.json",
        help="Pfad zur config-Datei, die geschrieben werden soll (Default: config.json).",
    )
    parser.add_argument(
        "--homeserver",
        help=(
            "URL eures Matrix-Servers, z.B. https://matrix.eure-hochschule.de "
            "(Default: der Wert aus der bestehenden config-Datei)."
        ),
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help=(
            "Browser nicht automatisch öffnen, nur den Login-Link ausgeben "
            "(im Docker-Container automatisch aktiv)."
        ),
    )


def _wait_for_login_token(sso_url: str, *, in_docker: bool, open_browser: bool) -> str | None:
    """Startet den Callback-Server, öffnet ggf. den Browser und wartet auf den Login-Token."""
    # Im Container muss der Callback-Server über die Port-Weiterleitung von
    # außen erreichbar sein, daher dort auf allen Interfaces lauschen.
    bind_host = "0.0.0.0" if in_docker else "127.0.0.1"  # noqa: S104
    server = CallbackServer((bind_host, CALLBACK_PORT), CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    if open_browser:
        webbrowser.open(sso_url)

    print(f"⏳ Warte auf Login im Browser (max. {LOGIN_TIMEOUT_SECONDS // 60} Minuten)...")
    server_thread.join(timeout=LOGIN_TIMEOUT_SECONDS)
    server.server_close()
    return server.login_token


def run(args: argparse.Namespace) -> None:
    """Führt den SSO-Login durch und speichert die Tokens in der config-Datei."""
    config_path = resolve(args.config)
    in_docker = os.environ.get(IN_DOCKER_ENV) == "1"
    config = read_config(config_path)

    homeserver = str(args.homeserver or config.get("homeserver", "")).rstrip("/")
    if not homeserver:
        print("❌ Kein Homeserver bekannt. Bitte mit --homeserver angeben, z.B.:")
        print("   matrix-tools login --homeserver https://matrix.eure-hochschule.de")
        sys.exit(1)

    sso_url = f"{homeserver}/_matrix/client/v3/login/sso/redirect?redirectUrl={CALLBACK_URL}"
    print("🔐 Matrix SSO-Login wird gestartet...")
    print(f"   Ziel-Datei: {config_path}")
    print("   Falls sich der Browser nicht automatisch öffnet, rufe manuell auf:")
    print(f"   {sso_url}\n")

    login_token = _wait_for_login_token(
        sso_url, in_docker=in_docker, open_browser=not (args.no_browser or in_docker)
    )
    if not login_token:
        print("❌ Kein Login-Token erhalten (Timeout oder Abbruch). Bitte nochmal versuchen.")
        sys.exit(1)

    print("✅ Login-Token erhalten. Tausche gegen Access Token...")

    try:
        resp = requests.post(
            f"{homeserver}/_matrix/client/v3/login",
            json={
                "type": "m.login.token",
                "token": login_token,
                "refresh_token": True,  # bittet den Server explizit um einen Refresh Token
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        print(f"❌ Server nicht erreichbar: {e}")
        sys.exit(1)

    if resp.status_code != HTTPStatus.OK:
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
        print("⚠️  Server hat KEINEN refresh_token ausgestellt. Auto-Refresh ist nicht möglich -")
        print("   der Token muss dann regelmäßig manuell erneuert werden.")

    config["homeserver"] = homeserver
    config["user_id"] = user_id
    config["access_token"] = access_token
    if refresh_token:
        config["refresh_token"] = refresh_token
    if expires_in_ms:
        config["expires_in_ms"] = expires_in_ms

    save_config(config_path, config)

    print(f"\n✅ {config_path.name} aktualisiert für {user_id}.")
    if refresh_token:
        print("✅ Refresh Token gespeichert - der Watchdog kann sich jetzt selbst erneuern.")
