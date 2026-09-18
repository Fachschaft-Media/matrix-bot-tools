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
from typing import TYPE_CHECKING

from aiohttp import ClientError
from nio import AsyncClient, JoinedMembersResponse, LocalProtocolError, RoomInviteResponse

from matrix_tools.config import MatrixConfig, create_client, load_config
from matrix_tools.members import get_member_status
from matrix_tools.paths import resolve

if TYPE_CHECKING:
    import argparse


async def invite_all(
    client: AsyncClient, target_room: str, user_ids: set[str]
) -> tuple[list[str], list[tuple[str, str]]]:
    """Lädt alle user_ids in target_room ein und gibt (erfolgreich, fehlgeschlagen) zurück."""
    success: list[str] = []
    failed: list[tuple[str, str]] = []
    for user_id in sorted(user_ids):
        try:
            resp = await client.room_invite(target_room, user_id)
        except (ClientError, LocalProtocolError, TimeoutError) as e:
            failed.append((user_id, str(e)))
            print(f"  ❌ {user_id} -> {e}")
            continue
        if isinstance(resp, RoomInviteResponse):
            success.append(user_id)
            print(f"  ✅ {user_id}")
        else:
            failed.append((user_id, str(resp)))
            print(f"  ❌ {user_id} -> {resp}")
    return success, failed


async def compute_invites(
    client: AsyncClient, source_room: str, target_room: str
) -> set[str] | None:
    """Ermittelt, wer aus dem Quellraum neu in den Zielraum eingeladen werden müsste.

    Gibt None zurück, falls einer der Räume nicht gelesen werden kann.
    """
    print(f"🔍 Lese Mitglieder von {source_room}...")
    source_resp = await client.joined_members(source_room)
    if not isinstance(source_resp, JoinedMembersResponse):
        print(f"❌ Konnte Quellraum nicht lesen: {source_resp}")
        return None
    source_members = {m.user_id for m in source_resp.members}
    print(f"   {len(source_members)} Mitglieder gefunden.\n")

    print(f"🔍 Lese Status im Zielraum {target_room}...")
    target_status = await get_member_status(client, target_room)
    if not target_status:
        print("❌ Konnte Zielraum nicht lesen (leer oder Fehler).")
        return None

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
    config: MatrixConfig, source_room: str, target_room: str, *, dry_run: bool
) -> None:
    """Lädt alle Mitglieder von source_room, die noch fehlen, in target_room ein."""
    client = create_client(config)
    to_invite = await compute_invites(client, source_room, target_room)

    if to_invite is None:
        await client.close()
        return

    if dry_run:
        print("🧪 DRY RUN - es wird niemand eingeladen. Würde einladen:")
        for user_id in sorted(to_invite):
            print(f"   - {user_id}")
        await client.close()
        return

    success, failed = await invite_all(client, target_room, to_invite)
    await client.close()

    print(f"\n📊 Fertig: {len(success)} eingeladen, {len(failed)} fehlgeschlagen.")
    if failed:
        print("\nFehlgeschlagen:")
        for user_id, err in failed:
            print(f"  - {user_id}: {err}")


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
    config = load_config(resolve(args.config))
    asyncio.run(sync_members(config, args.source, args.target, dry_run=args.dry_run))
