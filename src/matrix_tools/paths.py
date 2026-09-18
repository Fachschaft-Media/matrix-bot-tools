"""Auflösung von Daten-Dateien (config.json, settings.json, rooms.txt, ...).

Relative Pfade werden relativ zum Daten-Ordner aufgelöst. Das ist das aktuelle
Arbeitsverzeichnis oder - falls gesetzt - der Ordner aus der Umgebungsvariable
MATRIX_TOOLS_DATA_DIR (im Docker-Image: /data).
"""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR_ENV = "MATRIX_TOOLS_DATA_DIR"


def data_dir() -> Path:
    """Gibt den Ordner zurück, in dem die Daten-Dateien liegen."""
    env = os.environ.get(DATA_DIR_ENV)
    return Path(env) if env else Path.cwd()


def resolve(path: str | Path) -> Path:
    """Löst einen (ggf. relativen) Pfad relativ zum Daten-Ordner auf."""
    path = Path(path)
    return path if path.is_absolute() else data_dir() / path
