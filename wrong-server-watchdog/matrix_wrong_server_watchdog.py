#!/usr/bin/env python3
"""
Matrix Wrong-Server-Watchdog
==============================
Überwacht einen Space/Raum live und schickt jeder Person, die mit einem
FALSCHEN Matrix-Server beitritt (z.B. matrix.org statt dem h_da-Server),
automatisch eine Direktnachricht mit Hinweis auf den richtigen Server und
Link zur Anleitung.

Läuft dauerhaft im Hintergrund (kein Cronjob/Taskplaner-Skript, sondern ein
Prozess, der permanent auf neue Beitritte wartet) - siehe SETUP unten für
Einrichtung als Windows-Dienst/Taskplaner-Dauerlauf.

Nutzt die gleiche config.json wie die anderen Matrix-Scripts:
    {
      "homeserver": "https://matrix.eure-hochschule.de",
      "user_id": "@nutzername:matrix.eure-hochschule.de",
      "access_token": "DEIN_ACCESS_TOKEN"
    }

BENUTZUNG
---------
    python3 matrix_wrong_server_watchdog.py --room '!spaceid' --correct-domain matrix.eure-hochschule.de

Mehrere Räume gleichzeitig überwachen:
    python3 matrix_wrong_server_watchdog.py --room '!raum1' --room '!raum2' --correct-domain matrix.eure-hochschule.de

Zum Testen ohne tatsächlich Nachrichten zu verschicken:
    python3 matrix_wrong_server_watchdog.py --room '!spaceid' --correct-domain matrix.eure-hochschule.de --dry-run

HINWEIS
-------
Der Account muss im überwachten Raum Mitglied sein und DMs an andere
Nutzer:innen schreiben dürfen (Standard, außer der Server schränkt das ein).
Bereits benachrichtigte Personen werden in notified_users.json gemerkt,
damit sie bei einem Neustart des Scripts nicht doppelt angeschrieben werden.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from nio import (
    AsyncClient,
    MatrixRoom,
    RoomCreateResponse,
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
NOTIFIED_PATH = Path(__file__).parent / "notified_users.json"

# Default-Anleitung/Absender - per --guide-url und --sender-name überschreibbar,
# siehe main(). Passe diese Defaults gern direkt hier an eure eigene Hochschule an.
DEFAULT_GUIDE_URL = "https://example.edu/matrix-anleitung"
DEFAULT_SENDER_NAME = "deine Fachschaft"


def build_message(guide_url: str, sender_name: str) -> str:
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


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"❌ Keine config.json gefunden unter {CONFIG_PATH}")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


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


def domain_of(user_id: str) -> str:
    """Extrahiert den Server-Teil einer User-ID, z.B. '@a:matrix.org' -> 'matrix.org'."""
    return user_id.split(":", 1)[1] if ":" in user_id else ""


async def send_dm(client: AsyncClient, user_id: str, message: str) -> bool:
    """Erstellt (oder nutzt) einen DM-Raum mit user_id und sendet eine Nachricht."""
    resp = await client.room_create(
        is_direct=True,
        preset=None,
        invite=[user_id],
        name=None,
    )
    if not isinstance(resp, RoomCreateResponse):
        print(f"  ❌ DM-Raum für {user_id} konnte nicht erstellt werden: {resp}")
        return False

    send_resp = await client.room_send(
        room_id=resp.room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": message},
    )
    if not isinstance(send_resp, RoomSendResponse):
        print(f"  ❌ Nachricht an {user_id} konnte nicht gesendet werden: {send_resp}")
        return False
    return True


async def watch(rooms: list[str], correct_domain: str, dry_run: bool, message: str) -> None:
    config = load_config()
    notified = load_notified()

    client = AsyncClient(config["homeserver"], config["user_id"])
    client.access_token = config["access_token"]
    client.user_id = config["user_id"]

    watched_rooms = set(rooms)

    # Erst einmal initial syncen, damit bereits bestehende Mitglieder NICHT
    # als "neuer Beitritt" gewertet werden (sonst würde jeder Neustart alle
    # Bestandsmitglieder erneut anschreiben, sofern noch nicht notified).
    print("🔄 Initialer Sync (kann etwas dauern)...")
    resp = await client.sync(timeout=30000)
    if isinstance(resp, SyncError) and is_token_error(resp):
        if refresh_access_token(CONFIG_PATH, client):
            resp = await client.sync(timeout=30000)
    print("✅ Bereit. Warte auf neue Beitritte...\n")

    async def on_member_event(room: MatrixRoom, event: RoomMemberEvent) -> None:
        if room.room_id not in watched_rooms:
            return
        if event.membership != "join" or event.prev_membership == "join":
            return  # kein neuer Beitritt (z.B. Profil-Update)

        user_id = event.state_key
        if user_id in notified:
            return

        domain = domain_of(user_id)
        if domain == correct_domain:
            return  # richtiger Server, nichts zu tun

        print(f"🚨 {user_id} ist mit falschem Server ({domain}) beigetreten.")

        if dry_run:
            print(f"   🧪 DRY RUN - würde DM senden:\n   {message}\n")
        else:
            ok = await send_dm(client, user_id, message)
            if ok:
                print(f"   ✅ DM an {user_id} gesendet.")
            notified.add(user_id)
            save_notified(notified)

    client.add_event_callback(on_member_event, RoomMemberEvent)

    # Eigene Sync-Schleife statt sync_forever(), damit wir bei einem
    # abgelaufenen Token automatisch refreshen können, statt uns in einer
    # Fehlerschleife totzulaufen.
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
        description="Überwacht Räume und schreibt neue Mitglieder mit falschem Server an."
    )
    parser.add_argument(
        "--room",
        action="append",
        required=True,
        help="Room-ID zum Überwachen (mehrfach angeben für mehrere Räume).",
    )
    parser.add_argument(
        "--correct-domain",
        required=True,
        help="Der korrekte Server-Domainname, z.B. matrix.eure-hochschule.de",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur anzeigen, wer angeschrieben würde, ohne tatsächlich zu senden.",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Pfad zur config-Datei (Default: config.json). Bei mehreren parallel "
             "laufenden Dauerlauf-Scripts unbedingt UNTERSCHIEDLICHE Dateien verwenden, "
             "sonst kollidieren die Token-Refreshes ('Token-Tennis').",
    )
    parser.add_argument(
        "--guide-url",
        default=DEFAULT_GUIDE_URL,
        help="Link zur Anleitung, wie man sich mit dem richtigen Server anmeldet.",
    )
    parser.add_argument(
        "--sender-name",
        default=DEFAULT_SENDER_NAME,
        help="Name, mit dem die Nachricht unterschrieben wird, z.B. 'deine Fachschaft Media'.",
    )
    args = parser.parse_args()

    global CONFIG_PATH
    CONFIG_PATH = Path(__file__).parent / args.config

    message = build_message(args.guide_url, args.sender_name)

    print("👀 Überwache Räume:")
    for r in args.room:
        print(f"   - {r}")
    print(f"✅ Richtiger Server: {args.correct_domain}")
    print(f"🔑 Config: {CONFIG_PATH}\n")

    try:
        asyncio.run(watch(args.room, args.correct_domain, args.dry_run, message))
    except KeyboardInterrupt:
        print("\n👋 Beendet.")


if __name__ == "__main__":
    main()
