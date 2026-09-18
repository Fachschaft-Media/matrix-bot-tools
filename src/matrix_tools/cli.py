"""Kommandozeilen-Einstiegspunkt ``matrix-tools``."""

from __future__ import annotations

import argparse
import sys

from matrix_tools import broadcast, create_rooms, login, sync_members, watchdog

COMMANDS = {
    "login": (login, "Per SSO-Login Access- und Refresh-Token holen und in config.json speichern."),
    "watchdog": (watchdog, "Dauerlauf: Wrong-Server-Check und Auto-Invite-Regeln aus settings.json."),
    "broadcast": (broadcast, "Eine Nachricht gleichzeitig an viele Räume schicken."),
    "create-rooms": (create_rooms, "Viele gleichartige Räume auf einmal erstellen."),
    "sync-members": (sync_members, "Mitglieder eines Space/Raums einmalig in einen anderen Raum einladen."),
}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        # Windows-Konsolen nutzen oft cp1252 und können sonst keine Emojis ausgeben.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="matrix-tools",
        description="Matrix-Tools für Hochschulgruppen. Hilfe zu einem Befehl: matrix-tools <befehl> --help",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<befehl>", required=True)
    for name, (module, help_text) in COMMANDS.items():
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        module.add_arguments(sub)
        sub.set_defaults(func=module.run)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n👋 Beendet.")
