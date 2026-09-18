"""Laden der Zugangsdaten (config.json) und Erstellen des Matrix-Clients."""

import json
import sys
from typing import TYPE_CHECKING, NotRequired, TypedDict

from nio import AsyncClient

if TYPE_CHECKING:
    from pathlib import Path


class MatrixConfig(TypedDict):
    """Inhalt der config.json mit den Zugangsdaten des Bot-Accounts."""

    homeserver: str
    user_id: str
    access_token: str
    refresh_token: NotRequired[str]
    expires_in_ms: NotRequired[int]


def load_config(config_path: Path) -> MatrixConfig:
    """Lädt die Zugangsdaten und beendet das Programm mit einem Hinweis, falls sie fehlen."""
    if not config_path.exists():
        print(f"❌ Keine config.json gefunden unter {config_path}")
        print("   Lege sie mit 'matrix-tools login' an oder kopiere examples/config.example.json.")
        sys.exit(1)
    config: MatrixConfig = json.loads(config_path.read_text(encoding="utf-8"))
    return config


def create_client(config: MatrixConfig) -> AsyncClient:
    """Erstellt einen angemeldeten Matrix-Client aus den Zugangsdaten."""
    client = AsyncClient(config["homeserver"], config["user_id"])
    client.access_token = config["access_token"]
    client.user_id = config["user_id"]
    return client
