"""Kommandozeilen-Einstiegspunkt ``matrix-tools``."""

import argparse
import io
import sys
from typing import TYPE_CHECKING, Protocol

from matrix_tools import broadcast, create_rooms, login, sync_members, watchdog
from matrix_tools.config import ConfigError
from matrix_tools.session import TokenExpiredError

if TYPE_CHECKING:
    from collections.abc import Sequence


class Command(Protocol):
    """Schnittstelle, die jedes Befehls-Modul bereitstellt."""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Registriert die Argumente des Befehls."""
        ...

    def run(self, args: argparse.Namespace) -> None:
        """Führt den Befehl aus."""
        ...


COMMANDS: dict[str, tuple[Command, str]] = {
    "login": (
        login,
        "Per SSO-Login Access- und Refresh-Token holen und in config.json speichern.",
    ),
    "watchdog": (
        watchdog,
        "Dauerlauf: Wrong-Server-Check und Auto-Invite-Regeln aus settings.json.",
    ),
    "broadcast": (broadcast, "Eine Nachricht gleichzeitig an viele Räume schicken."),
    "create-rooms": (create_rooms, "Viele gleichartige Räume auf einmal erstellen."),
    "sync-members": (
        sync_members,
        "Mitglieder eines Space/Raums einmalig in einen anderen Raum einladen.",
    ),
}


def _force_utf8_output() -> None:
    """Erzwingt UTF-8-Ausgabe, da Windows-Konsolen sonst an Emojis scheitern (cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    """Baut den Argument-Parser mit allen Unterbefehlen."""
    parser = argparse.ArgumentParser(
        prog="matrix-tools",
        description=(
            "Matrix-Tools für Hochschulgruppen. Hilfe zu einem Befehl: matrix-tools <befehl> --help"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<befehl>", required=True)
    for name, (command, help_text) in COMMANDS.items():
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        command.add_arguments(sub)
        sub.set_defaults(func=command.run)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Startet den über die Kommandozeile gewählten Befehl."""
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n👋 Beendet.")
    except (ConfigError, TokenExpiredError) as e:
        print(f"\n❌ {e}")
        sys.exit(1)
