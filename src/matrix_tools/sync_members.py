r"""Matrix Member-Sync.

Lädt alle Mitglieder eines Space (oder Raums) einmalig in einen anderen Raum
ein - z.B. alle Mitglieder des Fachschaft-Media-Space in die Gruppe
"aktive fachschaft". Für den Dauerlauf (live auf neue Beitritte reagieren)
stattdessen 'matrix-tools watchdog' mit einer Auto-Invite-Regel nutzen.

WICHTIG: Der Account braucht in BEIDEN Räumen Berechtigungen: Mitgliederliste
vom Quellraum lesen können UND im Zielraum einladen dürfen (meist
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
"""

import asyncio
import sys
from typing import TYPE_CHECKING

from matrix_tools.paths import resolve
from matrix_tools.session import MatrixError, MatrixSession, open_session

if TYPE_CHECKING:
    import argparse
    from pathlib import Path


async def invite_all(
    session: MatrixSession, target_room: str, user_ids: set[str]
) -> tuple[list[str], list[tuple[str, str]]]:
    """Lädt alle user_ids in target_room ein und gibt (erfolgreich, fehlgeschlagen) zurück."""
    success: list[str] = []
    failed: list[tuple[str, str]] = []
    for user_id in sorted(user_ids):
        try:
            await session.invite(target_room, user_id)
        except MatrixError as e:
            failed.append((user_id, str(e)))
            print(f"  ❌ {user_id} -> {e}")
            continue
        success.append(user_id)
        print(f"  ✅ {user_id}")
    return success, failed


async def compute_invites(session: MatrixSession, source_room: str, target_room: str) -> set[str]:
    """Ermittelt, wer aus dem Quellraum neu in den Zielraum eingeladen werden müsste.

    Wirft MatrixError, falls einer der Räume nicht gelesen werden kann.
    """
    print(f"🔍 Lese Mitglieder von {source_room}...")
    source_members = await session.joined_members(source_room)
    print(f"   {len(source_members)} Mitglieder gefunden.\n")

    print(f"🔍 Lese Status im Zielraum {target_room}...")
    target_status = await session.member_status(target_room)

    already_joined = {u for u, m in target_status.items() if m == "join"}
    already_invited = {u for u, m in target_status.items() if m == "invite"}
    declined_or_left = {u for u, m in target_status.items() if m in {"leave", "ban"}}

    print(
        f"   {len(already_joined)} bereits Mitglied, "
        f"{len(already_invited)} bereits eingeladen (noch offen), "
        f"{len(declined_or_left)} abgelehnt/ausgetreten.\n"
    )

    to_invite = source_members - (already_joined | already_invited | declined_or_left)
    print(f"📋 {len(source_members & already_joined)} sind schon in beiden Räumen.")
    print(
        f"📋 {len(source_members & already_invited)} haben schon eine offene Einladung "
        "(kein erneutes Einladen)."
    )
    print(
        f"📋 {len(source_members & declined_or_left)} übersprungen (bereits abgelehnt/verlassen)."
    )
    print(f"📋 {len(to_invite)} müssten neu eingeladen werden.\n")
    return to_invite


async def sync_members(
    config_path: Path, source_room: str, target_room: str, *, dry_run: bool
) -> bool:
    """Lädt alle Mitglieder von source_room, die noch fehlen, in target_room ein.

    Gibt False zurück, falls die Räume nicht gelesen werden konnten.
    """
    async with open_session(config_path) as session:
        try:
            to_invite = await compute_invites(session, source_room, target_room)
        except MatrixError as e:
            print(f"❌ {e}")
            print("   Es wurde niemand eingeladen.")
            return False

        if dry_run:
            print("🧪 DRY RUN - es wird niemand eingeladen. Würde einladen:")
            for user_id in sorted(to_invite):
                print(f"   - {user_id}")
            return True

        success, failed = await invite_all(session, target_room, to_invite)

    print(f"\n📊 Fertig: {len(success)} eingeladen, {len(failed)} fehlgeschlagen.")
    if failed:
        print("\nFehlgeschlagen:")
        for user_id, err in failed:
            print(f"  - {user_id}: {err}")
    return True


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Registriert die Argumente von ``matrix-tools sync-members``."""
    parser.add_argument("--source", required=True, help="Room-ID des Quellraums (z.B. der Space).")
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
