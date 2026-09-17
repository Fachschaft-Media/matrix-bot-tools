#!/usr/bin/env python3
"""
Matrix Watchdog (vereinheitlicht)
====================================
EIN durchgehendes Dauerlauf-Script, das alles über eine settings.json
konfiguriert wird, statt für jede Regel ein eigenes Script mit CLI-Flags
zu starten. Kombiniert:

  - Wrong-Server-Check: neue Beitritte mit falschem Matrix-Server werden
    automatisch per DM informiert.
  - Auto-Invite-Regeln: beliebig viele Regeln der Form "wer Raum/Räume X
    beitritt, wird automatisch in Raum Y eingeladen" - für Space->Raum
    genauso wie für ausgewählte Kanäle->Space.

Läuft mit EINER einzigen Matrix-Session (eine config.json), dadurch
entfällt auch das Problem, dass mehrere parallele Scripts sich beim
Token-Refresh gegenseitig aussperren ("Token-Tennis").

SETUP
-----
1. config.json in diesem Ordner anlegen (Zugangsdaten, siehe Haupt-README
   bzw. auth/get_token.py für SSO-Server).
2. settings.example.json nach settings.json kopieren und an eure Bedürfnisse
   anpassen (siehe Kommentare dort bzw. README.md in diesem Ordner).

BENUTZUNG
---------
    python matrix_watchdog.py
    python matrix_watchdog.py --settings settings.json --config config.json
    python matrix_watchdog.py --dry-run    # nichts wird tatsächlich verschickt/eingeladen
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
    RoomCreateResponse,
    RoomGetStateResponse,
    RoomInviteResponse,
    RoomMemberEvent,
    RoomSendResponse,
    SyncError,
)

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from matrix_auth import refresh_access_token, is_token_error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = Path(__file__).parent / "config.json"
SETTINGS_PATH = Path(__file__).parent / "settings.json"
NOTIFIED_PATH = Path(__file__).parent / "notified_wrong_server.json"


# ─────────────────────────────────────────────────────────────────────────
# Config / Settings laden
# ─────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"❌ Keine config.json gefunden unter {CONFIG_PATH}")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        print(f"❌ Keine settings.json gefunden unter {SETTINGS_PATH}")
        print("   Kopiere settings.example.json nach settings.json und passe sie an.")
        sys.exit(1)
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def load_notified() -> set[str]:
    if not NOTIFIED_PATH.exists():
        return set()
    try:
        return set(json.loads(NOTIFIED_PATH.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return set()


def save_notified(notified: set[str]) -> None:
    NOTIFIED_PATH.write_text(
        json.dumps(sorted(notified), ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─────────────────────────────────────────────────────────────────────────
# Wrong-Server-Check
# ─────────────────────────────────────────────────────────────────────────

def domain_of(user_id: str) -> str:
    return user_id.split(":", 1)[1] if ":" in user_id else ""


def build_wrong_server_message(guide_url: str, sender_name: str) -> str:
    return (
        "Heyy, voll cool, dass du gejoint bist! 🎉\n\n"
        "Das ist am Anfang alles etwas kompliziert: Es sieht so aus, als hättest du dich "
        "mit dem falschen Server angemeldet. Bitte melde dich nochmal mit dem richtigen "
        "Hochschul-Server an, hier ist erklärt wie:\n"
        f"{guide_url}\n\n"
        "Wichtig: den richtigen Server auswählen und auf \"Anmelden\" klicken, NICHT "
        "\"Registrieren\" - falls ihr als Teil der Hochschule schon automatisch einen "
        "Account habt.\n\n"
        "Liebe Grüße,\n"
        f"{sender_name}"
    )


async def send_dm(client: AsyncClient, user_id: str, message: str) -> bool:
    resp = await client.room_create(is_direct=True, preset=None, invite=[user_id], name=None)
    if not isinstance(resp, RoomCreateResponse):
        print(f"   ❌ DM-Raum für {user_id} konnte nicht erstellt werden: {resp}")
        return False
    send_resp = await client.room_send(
        room_id=resp.room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": message},
    )
    if not isinstance(send_resp, RoomSendResponse):
        print(f"   ❌ Nachricht an {user_id} konnte nicht gesendet werden: {send_resp}")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────
# Auto-Invite-Regeln
# ─────────────────────────────────────────────────────────────────────────

async def get_member_status(client: AsyncClient, room_id: str) -> dict[str, str]:
    """Gibt {user_id: membership} zurück - 'join', 'invite', 'leave' oder 'ban'."""
    resp = await client.room_get_state(room_id)
    if not isinstance(resp, RoomGetStateResponse):
        print(f"   ⚠️  Konnte Verlaufsstatus von {room_id} nicht lesen: {resp}")
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
    status = await get_member_status(client, target_room)
    current = status.get(user_id)
    if current in ("join", "invite", "leave", "ban"):
        label = {"join": "bereits Mitglied", "invite": "bereits eingeladen",
                 "leave": "hat abgelehnt/ist ausgetreten", "ban": "gebannt"}[current]
        print(f"   ⏭️  {user_id} übersprungen ({label}).")
        return
    if dry_run:
        print(f"   🧪 DRY RUN - würde {user_id} in {target_room} einladen.")
        return
    resp = await client.room_invite(target_room, user_id)
    if isinstance(resp, RoomInviteResponse):
        print(f"   ✅ {user_id} in {target_room} eingeladen.")
    else:
        print(f"   ❌ Einladung an {user_id} fehlgeschlagen: {resp}")


async def initial_invite_pass(client: AsyncClient, rule: dict, global_dry_run: bool) -> None:
    """Einmaliger Abgleich beim Start für eine einzelne Auto-Invite-Regel."""
    source_rooms = rule["source_rooms"]
    target_room = rule["target_room"]
    dry_run = global_dry_run or rule.get("dry_run", False)

    print(f"🔍 Regel: {source_rooms} → {target_room}")
    members: set[str] = set()
    for source_room in source_rooms:
        resp = await client.joined_members(source_room)
        if not isinstance(resp, JoinedMembersResponse):
            if is_token_error(resp) and refresh_access_token(CONFIG_PATH, client):
                resp = await client.joined_members(source_room)
            if not isinstance(resp, JoinedMembersResponse):
                print(f"   ❌ Konnte {source_room} nicht lesen: {resp}")
                continue
        found = {m.user_id for m in resp.members}
        print(f"   {len(found)} Mitglieder in {source_room}.")
        members |= found

    target_status = await get_member_status(client, target_room)
    for user_id in sorted(members):
        current = target_status.get(user_id)
        if current in ("join", "invite", "leave", "ban"):
            continue
        if dry_run:
            print(f"   🧪 DRY RUN - würde {user_id} einladen.")
            continue
        resp = await client.room_invite(target_room, user_id)
        if isinstance(resp, RoomInviteResponse):
            print(f"   ✅ {user_id} eingeladen.")
        else:
            print(f"   ❌ Einladung an {user_id} fehlgeschlagen: {resp}")
    print()


# ─────────────────────────────────────────────────────────────────────────
# Haupt-Loop
# ─────────────────────────────────────────────────────────────────────────

async def run(settings: dict, global_dry_run: bool) -> None:
    config = load_config()
    notified = load_notified()

    client = AsyncClient(config["homeserver"], config["user_id"])
    client.access_token = config["access_token"]
    client.user_id = config["user_id"]

    wrong_server = settings.get("wrong_server", {})
    ws_enabled = wrong_server.get("enabled", False)
    ws_watch_rooms = set(wrong_server.get("watch_rooms", []))
    ws_correct_domain = wrong_server.get("correct_domain", "")
    ws_message = build_wrong_server_message(
        wrong_server.get("guide_url", "https://example.edu/matrix-anleitung"),
        wrong_server.get("sender_name", "deine Fachschaft"),
    )
    ws_dry_run = global_dry_run or wrong_server.get("dry_run", False)

    invite_rules = settings.get("auto_invite_rules", [])

    # Alle zu überwachenden Räume (Wrong-Server + alle Invite-Regel-Quellen)
    all_watched_rooms: set[str] = set(ws_watch_rooms)
    for rule in invite_rules:
        all_watched_rooms |= set(rule["source_rooms"])

    print(f"📋 Konfiguration geladen:")
    print(f"   Wrong-Server-Check: {'aktiv' if ws_enabled else 'inaktiv'}"
          f"{' (' + str(len(ws_watch_rooms)) + ' Räume)' if ws_enabled else ''}")
    print(f"   Auto-Invite-Regeln: {len(invite_rules)}")
    print(f"   Insgesamt überwachte Räume: {len(all_watched_rooms)}\n")

    # Initialer Abgleich für alle Invite-Regeln (Wrong-Server-Check macht
    # bewusst KEINEN initialen Abgleich - nur neue Beitritte ab jetzt).
    if invite_rules:
        print("═══ Initialer Abgleich der Auto-Invite-Regeln ═══\n")
        for rule in invite_rules:
            await initial_invite_pass(client, rule, global_dry_run)

    print("🔄 Initialer Live-Sync...")
    resp = await client.sync(timeout=30000)
    if isinstance(resp, SyncError) and is_token_error(resp):
        if refresh_access_token(CONFIG_PATH, client):
            resp = await client.sync(timeout=30000)
    print("✅ Bereit. Warte auf neue Beitritte...\n")

    async def on_member_event(room: MatrixRoom, event: RoomMemberEvent) -> None:
        if room.room_id not in all_watched_rooms:
            return
        if event.membership != "join" or event.prev_membership == "join":
            return  # kein neuer Beitritt

        user_id = event.state_key

        # Wrong-Server-Check
        if ws_enabled and room.room_id in ws_watch_rooms and user_id not in notified:
            domain = domain_of(user_id)
            if domain != ws_correct_domain:
                print(f"🚨 {user_id} ist mit falschem Server ({domain}) in {room.room_id} beigetreten.")
                if ws_dry_run:
                    print(f"   🧪 DRY RUN - würde DM senden.")
                else:
                    ok = await send_dm(client, user_id, ws_message)
                    if ok:
                        print(f"   ✅ DM an {user_id} gesendet.")
                    notified.add(user_id)
                    save_notified(notified)

        # Auto-Invite-Regeln
        for rule in invite_rules:
            if room.room_id in rule["source_rooms"]:
                dry_run = global_dry_run or rule.get("dry_run", False)
                print(f"👋 Neuer Beitritt in {room.room_id}: {user_id} (Regel → {rule['target_room']})")
                await invite_if_needed(client, rule["target_room"], user_id, dry_run)

    client.add_event_callback(on_member_event, RoomMemberEvent)

    # Eigene Sync-Schleife statt sync_forever(), für Auto-Refresh bei
    # abgelaufenem Token.
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
        description="Vereinheitlichtes Matrix-Dauerlauf-Tool, config-gesteuert."
    )
    parser.add_argument(
        "--config", default="config.json",
        help="Pfad zur config.json mit den Zugangsdaten (Default: config.json).",
    )
    parser.add_argument(
        "--settings", default="settings.json",
        help="Pfad zur settings.json mit den Verhaltensregeln (Default: settings.json).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="GLOBAL nichts tatsächlich senden/einladen, egal was in settings.json steht.",
    )
    args = parser.parse_args()

    global CONFIG_PATH, SETTINGS_PATH
    CONFIG_PATH = Path(__file__).parent / args.config
    SETTINGS_PATH = Path(__file__).parent / args.settings

    settings = load_settings()

    try:
        asyncio.run(run(settings, args.dry_run))
    except KeyboardInterrupt:
        print("\n👋 Beendet.")


if __name__ == "__main__":
    main()
