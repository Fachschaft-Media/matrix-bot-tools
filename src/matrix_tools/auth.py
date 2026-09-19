"""Automatischer Token-Refresh für den Dauerlauf.

Erneuert den Access Token über den gespeicherten Refresh Token, wenn der Server
'M_UNKNOWN_TOKEN' meldet, und speichert ihn in der config.json. Den neuen Token
im laufenden Client zu setzen ist Sache des Aufrufers.

Setzt voraus, dass die config.json einen 'refresh_token' enthält - den bekommst
du über 'matrix-tools login' (einmaliger SSO-Login).
"""

from http import HTTPStatus
from typing import TYPE_CHECKING

import requests
from nio import ErrorResponse

from matrix_tools.config import read_config, save_config

if TYPE_CHECKING:
    from pathlib import Path

REQUEST_TIMEOUT_SECONDS = 30


def refresh_access_token(config_path: Path) -> str | None:
    """Holt per refresh_token einen neuen access_token und speichert ihn in der config.json.

    Gibt den neuen access_token zurück, oder None, wenn kein refresh_token
    vorhanden ist oder der Refresh fehlschlägt.
    """
    config = read_config(config_path)
    if not config:
        print(f"❌ {config_path} nicht gefunden oder unlesbar, kann Token nicht erneuern.")
        return None

    refresh_token = config.get("refresh_token")

    if not refresh_token:
        print("❌ Kein refresh_token in config.json. Bitte 'matrix-tools login' ausführen.")
        return None

    print("🔄 Access Token abgelaufen - hole neuen per Refresh Token...")

    try:
        resp = requests.post(
            f"{config['homeserver']}/_matrix/client/v3/refresh",
            json={"refresh_token": refresh_token},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        print(f"❌ Token-Refresh fehlgeschlagen (Netzwerkfehler): {e}")
        return None

    if resp.status_code != HTTPStatus.OK:
        print(f"❌ Token-Refresh fehlgeschlagen ({resp.status_code}): {resp.text}")
        print(
            "   Refresh Token ist vermutlich auch abgelaufen. "
            "Bitte 'matrix-tools login' erneut ausführen."
        )
        return None

    data = resp.json()
    new_access_token = data.get("access_token")
    # Manche Server geben denselben Refresh Token zurück bzw. lassen ihn weg.
    new_refresh_token = data.get("refresh_token", refresh_token)

    if not new_access_token:
        print(f"❌ Kein access_token in der Refresh-Antwort: {data}")
        return None

    # config.json dauerhaft aktualisieren, damit ein Neustart nicht wieder
    # von vorne anfangen muss
    config["access_token"] = new_access_token
    config["refresh_token"] = new_refresh_token
    save_config(config_path, config)

    print("✅ Neuer Access Token erfolgreich geholt und gespeichert.")
    return new_access_token


def is_token_error(resp: object) -> bool:
    """Prüft, ob eine nio-Response ein abgelaufener/ungültiger Token ist."""
    return isinstance(resp, ErrorResponse) and (
        resp.status_code == "M_UNKNOWN_TOKEN" or resp.soft_logout
    )
