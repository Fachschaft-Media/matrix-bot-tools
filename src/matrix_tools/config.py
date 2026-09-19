"""Lesen und Schreiben der Zugangsdaten (config.json) und Prüfen von Konfigurationsdateien.

Einzige Stelle im Projekt, die die config.json anfasst - login, auth und alle
Befehle gehen über dieses Modul. Fehler in Konfigurationsdateien werden beim
Laden erkannt und als ``ConfigError`` mit allen gefundenen Problemen gemeldet,
bevor irgendetwas an den Matrix-Server geschickt wird.
"""

import json
import re
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict, cast

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

USER_ID_PATTERN = re.compile(r"^@[^:\s]+:\S+$")


class ConfigError(Exception):
    """Eine Konfigurationsdatei fehlt, ist kein gültiges JSON oder enthält ungültige Werte."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        """Baut eine Fehlermeldung mit allen gefundenen Problemen der Datei."""
        self.path = path
        self.problems = problems
        lines = "\n".join(f"   - {problem}" for problem in problems)
        super().__init__(f"Fehler in {path}:\n{lines}")


class MatrixConfig(TypedDict):
    """Inhalt der config.json mit den Zugangsdaten des Bot-Accounts."""

    homeserver: str
    user_id: str
    access_token: str
    refresh_token: NotRequired[str]
    expires_in_ms: NotRequired[int]


def read_json_file(path: Path, *, missing_hint: str) -> object:
    """Liest eine JSON-Datei. Wirft ConfigError, falls sie fehlt oder kein gültiges JSON ist."""
    if not path.exists():
        raise ConfigError(path, [f"Datei nicht gefunden. {missing_hint}"])
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        problem = f"kein gültiges JSON: {e.msg} (Zeile {e.lineno}, Spalte {e.colno})"
        raise ConfigError(path, [problem]) from e
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(path, [f"Datei kann nicht gelesen werden: {e}"]) from e


def is_http_url(value: object) -> bool:
    """Prüft, ob value eine http(s)-URL ist."""
    return isinstance(value, str) and value.startswith(("https://", "http://"))


def validate_config(raw: object) -> list[str]:
    """Gibt alle Probleme in den Zugangsdaten zurück (leere Liste = alles in Ordnung)."""
    if not isinstance(raw, dict):
        return ['muss ein JSON-Objekt sein, z.B. {"homeserver": "https://...", ...}']
    config = cast("dict[str, Any]", raw)
    problems = [
        f"'{key}' fehlt oder ist leer"
        for key in ("homeserver", "user_id", "access_token")
        if not isinstance(config.get(key), str) or not config[key].strip()
    ]
    homeserver = config.get("homeserver")
    if isinstance(homeserver, str) and homeserver and not is_http_url(homeserver):
        problems.append(f"'homeserver' muss mit https:// beginnen, ist aber '{homeserver}'")
    user_id = config.get("user_id")
    if isinstance(user_id, str) and user_id and not USER_ID_PATTERN.match(user_id):
        problems.append(f"'user_id' muss die Form @name:server haben, ist aber '{user_id}'")
    refresh_token = config.get("refresh_token")
    if refresh_token is not None and (not isinstance(refresh_token, str) or not refresh_token):
        problems.append("'refresh_token' muss ein nicht-leerer Text sein (oder ganz fehlen)")
    return problems


def read_config(config_path: Path) -> dict[str, Any]:
    """Liest eine bestehende config.json ungeprüft; ein leeres Dict, falls es sie nicht gibt.

    Wirft ConfigError, falls die Datei existiert, aber kein JSON-Objekt ist -
    damit sie nicht versehentlich überschrieben wird.
    """
    if not config_path.exists():
        return {}
    raw = read_json_file(config_path, missing_hint="")
    if not isinstance(raw, dict):
        raise ConfigError(config_path, ["muss ein JSON-Objekt sein"])
    return cast("dict[str, Any]", raw)


def load_config(config_path: Path) -> MatrixConfig:
    """Lädt und prüft die Zugangsdaten. Wirft ConfigError mit allen gefundenen Problemen."""
    raw = read_json_file(
        config_path,
        missing_hint=(
            "Lege sie mit 'matrix-tools login' an oder kopiere examples/config.example.json."
        ),
    )
    problems = validate_config(raw)
    if problems:
        raise ConfigError(config_path, problems)
    return cast("MatrixConfig", raw)


def save_config(config_path: Path, config: Mapping[str, Any]) -> None:
    """Schreibt die Zugangsdaten in die config.json."""
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
