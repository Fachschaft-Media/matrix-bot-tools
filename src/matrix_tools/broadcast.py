r"""Matrix Broadcast.

Schickt eine Nachricht gleichzeitig an mehrere Matrix-Räume (z.B. alle
Gruppen-Räume der Campus Rallye).

SETUP
-----
1. config.json anlegen (per 'matrix-tools login' oder Access Token aus
   Element -> Einstellungen -> Hilfe & Info -> Erweitert -> Access Token)
2. Account muss Mitglied in ALLEN Gruppen-Räumen sein (z.B. weil er sie mit
   'matrix-tools create-rooms' erstellt hat)
3. rooms.txt befüllen: eine Zeile pro Raum, entweder als Room-ID
   (!abcdefgh:matrix.h-da.de) ODER als Alias (#gruppe-001:matrix.h-da.de) -
   beides wird akzeptiert, Aliase werden automatisch aufgelöst.
   Zeilen mit // am Anfang werden als Kommentar ignoriert.

BENUTZUNG
---------
    matrix-tools broadcast "Wichtige Ansage an alle Gruppen: ..."

    # Nachricht aus Datei (z.B. für längere/formatierte Texte):
    matrix-tools broadcast --file ansage.txt

    # Nur an eine Teilmenge senden (Test):
    matrix-tools broadcast "Testnachricht" --rooms rooms_test.txt

    # Nachricht mit Markdown-Formatierung (fett, Listen etc.) senden:
    matrix-tools broadcast "**Wichtig:** Treffpunkt ist um 14 Uhr" --markdown

    # Direkt per Alias-Range senden, ohne rooms.txt zu befüllen:
    matrix-tools broadcast "Ansage an alle Gruppen" \
        --alias-range '#gruppe-001:matrix.eure-hochschule.de..#gruppe-150:matrix.eure-hochschule.de'
"""

import asyncio
import sys
from typing import TYPE_CHECKING

import markdown

from matrix_tools.paths import resolve
from matrix_tools.session import MatrixError, MatrixSession, open_session

if TYPE_CHECKING:
    import argparse
    from pathlib import Path


def load_rooms(path: Path) -> list[str]:
    """Lädt Room-IDs oder Aliase aus einer Textdatei, eine Zeile pro Raum.

    Zeilen mit '//' am Anfang gelten als Kommentar.
    """
    if not path.exists():
        print(f"❌ Keine Raumliste gefunden unter {path}")
        print("   Lege eine rooms.txt an, eine Zeile pro Raum, z.B.:")
        print("   !abcdefghijklmno:matrix.h-da.de")
        print("   #gruppe-001:matrix.h-da.de")
        sys.exit(1)

    rooms: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("//"):
            rooms.append(line)
    return rooms


def expand_alias_range(spec: str) -> list[str]:
    """Erzeugt Aliase aus einer Range wie '#gruppe-001:server..#gruppe-150:server'.

    Wirft ValueError, wenn die Range nicht dem erwarteten Format entspricht.
    """
    start_alias, end_alias = spec.split("..")
    prefix_start, server = start_alias.rsplit(":", 1)
    prefix, num_start = prefix_start.rsplit("-", 1)
    _, num_end = end_alias.rsplit(":", 1)[0].rsplit("-", 1)
    width = len(num_start)
    return [
        f"{prefix}-{str(i).zfill(width)}:{server}" for i in range(int(num_start), int(num_end) + 1)
    ]


def build_content(message: str, *, use_markdown: bool) -> dict[str, str]:
    """Baut den Nachrichteninhalt, optional mit per Markdown erzeugtem HTML."""
    content = {"msgtype": "m.text", "body": message}
    if use_markdown:
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = markdown.markdown(message)
    return content


async def resolve_room(session: MatrixSession, room_ref: str) -> str:
    """Gibt die Room-ID zurück und löst Aliase (#...) automatisch auf."""
    if room_ref.startswith("#"):
        return await session.resolve_alias(room_ref)
    return room_ref


async def broadcast(
    config_path: Path, message: str, room_refs: list[str], *, use_markdown: bool
) -> None:
    """Sendet die Nachricht an alle angegebenen Räume und gibt eine Zusammenfassung aus."""
    content = build_content(message, use_markdown=use_markdown)
    success: list[str] = []
    failed: list[tuple[str, str]] = []

    async with open_session(config_path) as session:
        print(f"📡 Sende an {len(room_refs)} Räume...\n")
        for room_ref in room_refs:
            try:
                room_id = await resolve_room(session, room_ref)
                await session.send_message(room_id, content)
            except MatrixError as e:
                failed.append((room_ref, str(e)))
                print(f"  ❌ {room_ref} -> {e}")
                continue
            success.append(room_ref)
            print(f"  ✅ {room_ref}")

    print(f"\n📊 Fertig: {len(success)} erfolgreich, {len(failed)} fehlgeschlagen.")
    if failed:
        print("\nFehlgeschlagene Räume:")
        for room_ref, err in failed:
            print(f"  - {room_ref}: {err}")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Registriert die Argumente von ``matrix-tools broadcast``."""
    parser.add_argument("message", nargs="?", help="Die zu sendende Nachricht.")
    parser.add_argument("--file", help="Nachricht aus Textdatei lesen statt Argument.")
    parser.add_argument(
        "--rooms",
        default="rooms.txt",
        help="Pfad zur Raumliste (Default: rooms.txt).",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Nachricht als Markdown interpretieren (fett, Listen, etc.).",
    )
    parser.add_argument(
        "--alias-range",
        help=(
            "Statt rooms.txt eine Alias-Range generieren, z.B. "
            "'#gruppe-001:matrix.eure-hochschule.de..#gruppe-150:matrix.eure-hochschule.de'"
        ),
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Pfad zur config.json mit den Zugangsdaten (Default: config.json).",
    )


def run(args: argparse.Namespace) -> None:
    """Liest Nachricht und Raumliste ein und startet den Broadcast."""
    if args.file:
        message_path = resolve(args.file)
        try:
            message = message_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError) as e:
            print(f"❌ Nachrichtendatei {message_path} kann nicht gelesen werden: {e}")
            sys.exit(2)
        if not message:
            print(f"❌ Nachrichtendatei {message_path} ist leer.")
            sys.exit(2)
    elif args.message:
        message = args.message
    else:
        print("❌ Entweder eine Nachricht als Argument oder --file angeben.")
        sys.exit(2)

    if args.alias_range:
        try:
            room_refs = expand_alias_range(args.alias_range)
        except ValueError:
            print(f"❌ Ungültige Alias-Range: {args.alias_range}")
            print("   Erwartetes Format: '#gruppe-001:server..#gruppe-150:server'")
            sys.exit(2)
    else:
        room_refs = load_rooms(resolve(args.rooms))

    if not room_refs:
        print("❌ Raumliste ist leer.")
        return

    asyncio.run(broadcast(resolve(args.config), message, room_refs, use_markdown=args.markdown))
