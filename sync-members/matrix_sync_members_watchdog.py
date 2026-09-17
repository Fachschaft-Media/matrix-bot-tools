#!/usr/bin/env python3
"""
Matrix Auto-Invite-Watchdog
=============================
Dauerlauf-Version von matrix_sync_members.py: überwacht einen oder mehrere
Räume live und lädt jede neue Person SOFORT in den Zielraum ein, statt erst
beim nächsten periodischen Lauf. Läuft dauerhaft im Hintergrund, wie
matrix_wrong_server_watchdog.py.

Zwei Einsatzrichtungen, beide mit demselben Script möglich:
  - Space -> Raum: alle Mitglieder eines Space landen automatisch in einem
    bestimmten Raum (z.B. "Aktive Fachschaft"). --source ist dann der Space.
  - Kanal(-Auswahl) -> Space: wer einem oder mehreren ausgewählten Kanälen
    beitritt, bekommt automatisch eine Einladung zum übergeordneten Space
    (oder einem anderen Raum). --source mehrfach angeben, --target ist dann
    der Space.

Beim Start wird einmalig ein vollständiger Abgleich gemacht (wie beim
normalen matrix_sync_members.py), danach läuft es weiter und reagiert live
auf neue Beitritte zu den Quellräumen.

Nutzt die gleiche config.json wie die anderen Matrix-Scripts.

BENUTZUNG
---------
    # Ein Quellraum (klassisch: Space -> Zielraum)
    python matrix_sync_members_watchdog.py --source '!spaceid' --target '!zielraumid'

    # Mehrere ausgewählte Quellräume (z.B. Kanal -> Space)
    python matrix_sync_members_watchdog.py --source '!kanal1' --source '!kanal2' --target '!spaceid'

    # Testen ohne tatsächlich einzuladen:
    python matrix_sync_members_watchdog.py --source '!spaceid' --target '!zielraumid' --dry-run

Wer eine Einladung bereits abgelehnt hat, den Zielraum verlassen hat, oder
schon eine offene Einladung hat, wird nicht erneut eingeladen (wie beim
normalen Sync-Script) - gilt pro Person, unabhängig davon, über welchen der
Quellräume sie "entdeckt" wurde.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from nio import (
    AsyncClient,
    JoinedMembersResponse,
    MatrixRoom,
    RoomGetStateResponse,
    RoomInviteResponse,
    RoomMemberEvent,
    SyncError,
)

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from matrix_auth import refresh_access_token, is_token_error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = Path(__file__).parent / "config.json"


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


async def invite_if_needed(client: AsyncClient, target_room: str, user_id: str, dry_run: bool) -> None:
    """Prüft den Status einer einzelnen Person im Zielraum und lädt sie ein,
    falls noch nicht Mitglied/eingeladen/abgelehnt/gebannt."""
    status = await get_member_status(client, target_room)
    current = status.get(user_id)

    if current in ("join", "invite", "leave", "ban"):
        label = {"join": "bereits Mitglied", "invite": "bereits eingeladen",
                 "leave": "hat abgelehnt/ist ausgetreten", "ban": "gebannt"}[current]
        print(f"   ⏭️  {user_id} übersprungen ({label}).")
        return

    if dry_run:
        print(f"   🧪 DRY RUN - würde {user_id} einladen.")
        return

    resp = await client.room_invite(target_room, user_id)
    if isinstance(resp, RoomInviteResponse):
        print(f"   ✅ {user_id} eingeladen.")
    else:
        print(f"   ❌ Einladung an {user_id} fehlgeschlagen: {resp}")


async def initial_sync_pass(client: AsyncClient, source_rooms: list[str], target_room: str, dry_run: bool) -> None:
    """Einmaliger vollständiger Abgleich beim Start, wie beim normalen Sync-Script.
    Sammelt Mitglieder aus ALLEN Quellräumen (dedupliziert)."""
    source_members: set[str] = set()
    for source_room in source_rooms:
        print(f"🔍 Initialer Abgleich: Lese Mitglieder von {source_room}...")
        source_resp = await client.joined_members(source_room)
        if not isinstance(source_resp, JoinedMembersResponse):
            if is_token_error(source_resp) and refresh_access_token(CONFIG_PATH, client):
                source_resp = await client.joined_members(source_room)
            if not isinstance(source_resp, JoinedMembersResponse):
                print(f"❌ Konnte Quellraum {source_room} nicht lesen: {source_resp}")
                continue
        found = {m.user_id for m in source_resp.members}
        print(f"   {len(found)} Mitglieder gefunden.")
        source_members |= found

    print(f"\n   {len(source_members)} Personen insgesamt (über alle Quellräume). Prüfe Zielraum...\n")

    # Zielraum-Status EINMAL abrufen statt pro Person (sonst Rate-Limit-Risiko
    # bei vielen Mitgliedern).
    target_status = await get_member_status(client, target_room)

    to_invite = []
    for user_id in sorted(source_members):
        current = target_status.get(user_id)
        if current in ("join", "invite", "leave", "ban"):
            label = {"join": "bereits Mitglied", "invite": "bereits eingeladen",
                     "leave": "hat abgelehnt/ist ausgetreten", "ban": "gebannt"}[current]
            print(f"   ⏭️  {user_id} übersprungen ({label}).")
            continue
        to_invite.append(user_id)

    for user_id in to_invite:
        if dry_run:
            print(f"   🧪 DRY RUN - würde {user_id} einladen.")
            continue
        resp = await client.room_invite(target_room, user_id)
        if isinstance(resp, RoomInviteResponse):
            print(f"   ✅ {user_id} eingeladen.")
        else:
            print(f"   ❌ Einladung an {user_id} fehlgeschlagen: {resp}")

    print("\n✅ Initialer Abgleich fertig.\n")


async def watch(source_rooms: list[str], target_room: str, dry_run: bool) -> None:
    config = load_config()

    client = AsyncClient(config["homeserver"], config["user_id"])
    client.access_token = config["access_token"]
    client.user_id = config["user_id"]

    watched_rooms = set(source_rooms)

    # Initialer Voll-Sync, damit alle bereits vorhandenen Mitglieder sofort
    # abgeglichen werden (nicht erst beim nächsten Beitritt).
    await initial_sync_pass(client, source_rooms, target_room, dry_run)

    print("🔄 Initialer Live-Sync...")
    resp = await client.sync(timeout=30000)
    if isinstance(resp, SyncError) and is_token_error(resp):
        if refresh_access_token(CONFIG_PATH, client):
            resp = await client.sync(timeout=30000)
    print("✅ Bereit. Warte auf neue Beitritte in den Quellräumen...\n")

    async def on_member_event(room: MatrixRoom, event: RoomMemberEvent) -> None:
        if room.room_id not in watched_rooms:
            return
        if event.membership != "join" or event.prev_membership == "join":
            return  # kein neuer Beitritt

        user_id = event.state_key
        print(f"👋 Neuer Beitritt in {room.room_id}: {user_id}")
        await invite_if_needed(client, target_room, user_id, dry_run)

    client.add_event_callback(on_member_event, RoomMemberEvent)

    # Eigene Sync-Schleife statt sync_forever(), damit wir bei einem
    # abgelaufenen Token automatisch refreshen können.
    while True:
        resp = await client.sync(timeout=30000)
        if isinstance(resp, SyncError):
            if is_token_error(resp):
                if not refresh_access_token(CONFIG_PATH, client):
                    print("❌ Token-Refresh fehlgeschlagen. Warte 60s und versuche erneut...")
                    await asyncio.sleep(60)
            else:
                print(f"⚠️  Sync-Fehler: {resp}. Warte 10s...")
                await asyncio.sleep(10)


def main():
    parser = argparse.ArgumentParser(
        description="Lädt neue Mitglieder eines Space live und automatisch in einen Zielraum ein."
    )
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="Room-ID eines Quellraums (z.B. Space oder Kanal). Mehrfach angeben "
             "für mehrere ausgewählte Quellräume - jeder Beitritt zu irgendeinem "
             "davon löst eine Einladung zum Zielraum aus.",
    )
    parser.add_argument("--target", required=True, help="Room-ID des Zielraums (kann auch ein Space sein).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur anzeigen, wer eingeladen würde, ohne tatsächlich einzuladen.",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Pfad zur config-Datei (Default: config.json). Bei mehreren parallel "
             "laufenden Dauerlauf-Scripts unbedingt UNTERSCHIEDLICHE Dateien verwenden, "
             "sonst kollidieren die Token-Refreshes ('Token-Tennis').",
    )
    args = parser.parse_args()

    global CONFIG_PATH
    CONFIG_PATH = Path(__file__).parent / args.config

    print(f"🔑 Config: {CONFIG_PATH}")
    print("👀 Überwache Quellräume:")
    for r in args.source:
        print(f"   - {r}")
    print(f"➡️  Zielraum: {args.target}\n")

    try:
        asyncio.run(watch(args.source, args.target, args.dry_run))
    except KeyboardInterrupt:
        print("\n👋 Beendet.")


if __name__ == "__main__":
    main()
