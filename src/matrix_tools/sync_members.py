#!/usr/bin/env python3
"""
Matrix Member-Sync
===================
Lädt alle Mitglieder eines Space (oder Raums) automatisch in einen anderen
Raum ein - z.B. alle Mitglieder des Fachschaft-Media-Space in die Gruppe
"aktive fachschaft".

Nutzt die gleiche config.json wie die anderen Matrix-Scripts:
    {
      "homeserver": "https://matrix.eure-hochschule.de",
      "user_id": "@nutzername:matrix.eure-hochschule.de",
      "access_token": "DEIN_ACCESS_TOKEN"
    }

WICHTIG: Der Account, der das Script ausführt, braucht in BEIDEM
Berechtigungen: Mitgliederliste vom Quellraum lesen können UND im
Zielraum einladen dürfen (meist Moderator/Admin-Power-Level).

Wer eine Einladung zum Zielraum bereits abgelehnt hat, den Zielraum wieder
verlassen hat, oder bereits eine offene (noch nicht beantwortete) Einladung
hat, wird beim nächsten Sync NICHT erneut eingeladen.

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

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from nio import AsyncClient, JoinedMembersResponse, RoomGetStateResponse, RoomInviteResponse

from matrix_tools.paths import resolve

CONFIG_PATH = resolve("config.json")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"❌ Keine config.json gefunden unter {CONFIG_PATH}")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


async def get_member_status(client: AsyncClient, room_id: str) -> dict[str, str]:
    """Gibt {user_id: membership} für alle bekannten Nutzer:innen eines Raums
    zurück - membership ist 'join', 'invite', 'leave' oder 'ban'."""
    resp = await client.room_get_state(room_id)
    if not isinstance(resp, RoomGetStateResponse):
        print(f"⚠️  Konnte Verlaufsstatus von {room_id} nicht lesen: {resp}")
        return {}

    status = {}
    for event in resp.events:
        if event.get("type") != "m.room.member":
            continue
        user_id = event.get("state_key")
        membership = event.get("content", {}).get("membership")
        if user_id and membership:
            status[user_id] = membership
    return status


async def sync_members(source_room: str, target_room: str, dry_run: bool) -> None:
    config = load_config()

    client = AsyncClient(config["homeserver"], config["user_id"])
    client.access_token = config["access_token"]
    client.user_id = config["user_id"]

    print(f"🔍 Lese Mitglieder von {source_room}...")
    source_resp = await client.joined_members(source_room)
    if not isinstance(source_resp, JoinedMembersResponse):
        print(f"❌ Konnte Quellraum nicht lesen: {source_resp}")
        await client.close()
        return
    source_members = {m.user_id for m in source_resp.members}
    print(f"   {len(source_members)} Mitglieder gefunden.\n")

    print(f"🔍 Lese Status im Zielraum {target_room}...")
    target_status = await get_member_status(client, target_room)
    if not target_status:
        print(f"❌ Konnte Zielraum nicht lesen (leer oder Fehler).")
        await client.close()
        return

    already_joined = {u for u, m in target_status.items() if m == "join"}
    already_invited = {u for u, m in target_status.items() if m == "invite"}
    declined_or_left = {u for u, m in target_status.items() if m in ("leave", "ban")}

    print(
        f"   {len(already_joined)} bereits Mitglied, "
        f"{len(already_invited)} bereits eingeladen (noch offen), "
        f"{len(declined_or_left)} abgelehnt/ausgetreten.\n"
    )

    already_covered = already_joined | already_invited | declined_or_left
    to_invite = source_members - already_covered
    already_there = source_members & already_joined
    pending = source_members & already_invited
    skipped = source_members & declined_or_left

    print(f"📋 {len(already_there)} sind schon in beiden Räumen.")
    print(f"📋 {len(pending)} haben schon eine offene Einladung (kein erneutes Einladen).")
    print(f"📋 {len(skipped)} übersprungen (bereits abgelehnt/verlassen).")
    print(f"📋 {len(to_invite)} müssten neu eingeladen werden.\n")

    if dry_run:
        print("🧪 DRY RUN - es wird niemand eingeladen. Würde einladen:")
        for user_id in sorted(to_invite):
            print(f"   - {user_id}")
        await client.close()
        return

    success, failed = [], []
    for user_id in sorted(to_invite):
        try:
            resp = await client.room_invite(target_room, user_id)
            if isinstance(resp, RoomInviteResponse):
                success.append(user_id)
                print(f"  ✅ {user_id}")
            else:
                failed.append((user_id, str(resp)))
                print(f"  ❌ {user_id} -> {resp}")
        except Exception as e:
            failed.append((user_id, str(e)))
            print(f"  ❌ {user_id} -> {e}")

    await client.close()

    print(f"\n📊 Fertig: {len(success)} eingeladen, {len(failed)} fehlgeschlagen.")
    if failed:
        print("\nFehlgeschlagen:")
        for user_id, err in failed:
            print(f"  - {user_id}: {err}")


def add_arguments(parser):
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


def run(args):
    global CONFIG_PATH
    CONFIG_PATH = resolve(args.config)

    asyncio.run(sync_members(args.source, args.target, args.dry_run))
