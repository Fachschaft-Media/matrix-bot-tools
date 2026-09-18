"""Automatischer Token-Refresh für den Dauerlauf.

Erneuert den Access Token über den gespeicherten Refresh Token, wenn der Server
'M_UNKNOWN_TOKEN' meldet. Aktualisiert sowohl den laufenden Client als auch die
config.json auf der Platte.

Setzt voraus, dass die config.json einen 'refresh_token' enthält - den bekommst
du über 'matrix-tools login' (einmaliger SSO-Login).
"""

import json
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    from pathlib import Path

    from nio import AsyncClient

REQUEST_TIMEOUT_SECONDS = 30


def refresh_access_token(config_path: Path, client: AsyncClient) -> bool:
    """Holt per refresh_token einen neuen access_token und aktualisiert Client und config.json.

    Gibt True bei Erfolg zurück, False wenn kein refresh_token vorhanden ist
    oder der Refresh fehlschlägt.
    """
    if not config_path.exists():
        print("❌ config.json nicht gefunden, kann Token nicht erneuern.")
        return False

    config: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    refresh_token = config.get("refresh_token")

    if not refresh_token:
        print("❌ Kein refresh_token in config.json. Bitte 'matrix-tools login' ausführen.")
        return False

    print("🔄 Access Token abgelaufen - hole neuen per Refresh Token...")

    try:
        resp = requests.post(
            f"{config['homeserver']}/_matrix/client/v3/refresh",
            json={"refresh_token": refresh_token},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        print(f"❌ Token-Refresh fehlgeschlagen (Netzwerkfehler): {e}")
        return False

    if resp.status_code != HTTPStatus.OK:
        print(f"❌ Token-Refresh fehlgeschlagen ({resp.status_code}): {resp.text}")
        print(
            "   Refresh Token ist vermutlich auch abgelaufen. "
            "Bitte 'matrix-tools login' erneut ausführen."
        )
        return False

    data = resp.json()
    new_access_token = data.get("access_token")
    # Manche Server geben denselben Refresh Token zurück bzw. lassen ihn weg.
    new_refresh_token = data.get("refresh_token", refresh_token)

    if not new_access_token:
        print(f"❌ Kein access_token in der Refresh-Antwort: {data}")
        return False

    # Client live aktualisieren, damit der nächste API-Call sofort klappt
    client.access_token = new_access_token

    # config.json dauerhaft aktualisieren, damit ein Neustart nicht wieder
    # von vorne anfangen muss
    config["access_token"] = new_access_token
    config["refresh_token"] = new_refresh_token
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    print("✅ Neuer Access Token erfolgreich geholt und gespeichert.")
    return True


def is_token_error(resp: object) -> bool:
    """Prüft, ob eine nio-Response ein abgelaufener/ungültiger Token ist."""
    message = str(resp)
    return "M_UNKNOWN_TOKEN" in message or "next_batch" in message or "required property" in message
