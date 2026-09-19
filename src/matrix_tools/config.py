"""Lesen und Schreiben der Zugangsdaten (config.json), Erstellen des Matrix-Clients.

Einzige Stelle im Projekt, die die config.json anfasst - login, auth und alle
Befehle gehen über dieses Modul.
"""

import json
import sys
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

from nio import AsyncClient

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


class MatrixConfig(TypedDict):
    """Inhalt der config.json mit den Zugangsdaten des Bot-Accounts."""

    homeserver: str
    user_id: str
    access_token: str
    refresh_token: NotRequired[str]
    expires_in_ms: NotRequired[int]


def read_config(config_path: Path) -> dict[str, Any]:
    """Liest die config.json, falls vorhanden; sonst (oder bei kaputtem JSON) ein leeres Dict."""
    if not config_path.exists():
        return {}
    try:
        config: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return config


def load_config(config_path: Path) -> MatrixConfig:
    """Lädt die Zugangsdaten und beendet das Programm mit einem Hinweis, falls sie fehlen."""
    if not config_path.exists():
        print(f"❌ Keine config.json gefunden unter {config_path}")
        print("   Lege sie mit 'matrix-tools login' an oder kopiere examples/config.example.json.")
        sys.exit(1)
    config: MatrixConfig = json.loads(config_path.read_text(encoding="utf-8"))
    return config


def save_config(config_path: Path, config: Mapping[str, Any]) -> None:
    """Schreibt die Zugangsdaten in die config.json."""
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def create_client(config: MatrixConfig) -> AsyncClient:
    """Erstellt einen angemeldeten Matrix-Client aus den Zugangsdaten."""
    client = AsyncClient(config["homeserver"], config["user_id"])
    client.access_token = config["access_token"]
    client.user_id = config["user_id"]
    return client
