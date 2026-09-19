r"""Matrix Member-Sync.

Lädt alle Mitglieder eines oder mehrerer Spaces/Räume einmalig in einen
anderen Raum ein - z.B. alle Mitglieder des Fachschaft-Media-Space in die Gruppe
"aktive fachschaft". Für den Dauerlauf (live auf neue Beitritte reagieren)
stattdessen 'matrix-tools watchdog' mit einer Auto-Invite-Regel nutzen.

WICHTIG: Der Account braucht in BEIDEN Räumen Berechtigungen: Mitgliederliste
der Quellräume lesen können UND im Zielraum einladen dürfen (meist
Moderator/Admin-Power-Level).

Wer eine Einladung zum Zielraum bereits abgelehnt hat, den Zielraum wieder
verlassen hat, oder bereits eine offene (noch nicht beantwortete) Einladung
hat, wird NICHT erneut eingeladen.

BENUTZUNG
---------
    # Erst mal nur anschauen, wer eingeladen würde (nichts wird verschickt):
    matrix-tools sync-members --source '!DEINE_QUELL_SPACE_ID_HIER:matrix.eure-hochschule.de' \
        --target '!DEINE_ZIEL_RAUM_ID_HIER:matrix.eure-hochschule.de' \
        --dry-run

    # Tatsächlich einladen:
    matrix-tools sync-members --source '!DEINE_QUELL_SPACE_ID_HIER:matrix.eure-hochschule.de' \
        --target '!DEINE_ZIEL_RAUM_ID_HIER:matrix.eure-hochschule.de'

    # Mitglieder mehrerer Quellräume zusammen einladen (--source mehrfach angeben):
    matrix-tools sync-members --source '!KANAL_1_HIER:matrix.eure-hochschule.de' \
        --source '!KANAL_2_HIER:matrix.eure-hochschule.de' \
        --target '!DEINE_ZIEL_RAUM_ID_HIER:matrix.eure-hochschule.de'
"""

import asyncio
import sys
from typing import TYPE_CHECKING

from matrix_tools.invites import members_of, reconcile_invites
from matrix_tools.paths import resolve
from matrix_tools.session import MatrixError, open_session

if TYPE_CHECKING:
    import argparse
    from pathlib import Path


async def sync_members(
    config_path: Path, source_rooms: list[str], target_room: str, *, dry_run: bool
) -> bool:
    """Lädt alle Mitglieder der Quellräume, die im Zielraum noch fehlen, dort ein.

    Gibt False zurück, falls ein Raum nicht gelesen werden konnte (dann wird
    niemand eingeladen).
    """
    async with open_session(config_path) as session:
        try:
            print(f"🔍 Lese Mitglieder von {', '.join(source_rooms)}...")
            members = await members_of(session, source_rooms)
            print(f"🔍 Gleiche mit Zielraum {target_room} ab...")
            result = await reconcile_invites(session, target_room, members, dry_run=dry_run)
        except MatrixError as e:
            print(f"❌ {e}")
            print("   Es wurde niemand eingeladen.")
            return False

    if dry_run:
        print("\n🧪 DRY RUN - es wurde niemand eingeladen.")
        return True
    print(f"\n📊 Fertig: {len(result.invited)} eingeladen, {len(result.failed)} fehlgeschlagen.")
    if result.failed:
        print("\nFehlgeschlagen:")
        for user_id, err in result.failed:
            print(f"  - {user_id}: {err}")
    return True


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Registriert die Argumente von ``matrix-tools sync-members``."""
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="Room-ID eines Quellraums (z.B. der Space). Mehrfach angeben für mehrere Quellräume.",
    )
    parser.add_argument("--target", required=True, help="Room-ID des Zielraums.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur anzeigen, wer eingeladen würde, ohne tatsächlich einzuladen.",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Pfad zur config.json mit den Zugangsdaten (Default: config.json).",
    )


def run(args: argparse.Namespace) -> None:
    """Führt den einmaligen Mitglieder-Abgleich aus."""
    ok = asyncio.run(
        sync_members(resolve(args.config), args.source, args.target, dry_run=args.dry_run)
    )
    if not ok:
        sys.exit(1)
