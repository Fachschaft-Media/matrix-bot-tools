#!/usr/bin/env python3
"""
Matrix Broadcast-Script
========================
Schickt eine Nachricht gleichzeitig an mehrere Matrix-Räume (z.B. alle
Gruppen-Räume der Campus Rallye).

SETUP
-----
1. Access Token deines Matrix-Accounts holen:
   - Element -> Einstellungen -> Hilfe & Info -> Erweitert -> Access Token
   - ODER via curl:
     curl -XPOST -d '{"type":"m.login.password","user":"NUTZERNAME","password":"PASSWORT"}' \
       "https://DEIN-HOMESERVER/_matrix/client/r0/login"
2. Account muss Mitglied in ALLEN Gruppen-Räumen sein (z.B. weil er sie mit
   matrix_create_rooms.py erstellt hat)
3. rooms.txt befüllen: eine Zeile pro Raum, entweder als Room-ID
   (!abcdefgh:matrix.h-da.de) ODER als Alias (#gruppe-001:matrix.h-da.de) -
   beides wird akzeptiert, Aliase werden automatisch aufgelöst.
   Zeilen mit // am Anfang werden als Kommentar ignoriert.
4. config.json mit homeserver, user_id und access_token anlegen (siehe unten)

BENUTZUNG
---------
    python matrix_broadcast.py "Wichtige Ansage an alle Gruppen: ..."

    # Nachricht aus Datei (z.B. für längere/formatierte Texte):
    python matrix_broadcast.py --file ansage.txt

    # Nur an eine Teilmenge senden (Test):
    python matrix_broadcast.py "Testnachricht" --rooms rooms_test.txt

    # Nachricht mit Markdown-Formatierung (fett, Listen etc.) senden:
    python matrix_broadcast.py "**Wichtig:** Treffpunkt ist um 14 Uhr" --markdown

    # Direkt per Alias-Range senden, ohne rooms.txt zu befüllen:
    python matrix_broadcast.py "Ansage an alle Gruppen" \
        --alias-range '#gruppe-001:matrix.eure-hochschule.de..#gruppe-150:matrix.eure-hochschule.de'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from nio import AsyncClient, LoginResponse, RoomSendResponse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = Path(__file__).parent / "config.json"
DEFAULT_ROOMS_PATH = Path(__file__).parent / "rooms.txt"


def load_config() -> dict:
    """Lädt Homeserver-URL und Access Token aus config.json."""
    if not CONFIG_PATH.exists():
        print(f"❌ Keine config.json gefunden unter {CONFIG_PATH}")
        print("   Lege eine config.json an mit folgendem Inhalt:")
        print(
            json.dumps(
                {
                    "homeserver": "https://matrix.h-da.de",
                    "user_id": "@nutzername:matrix.h-da.de",
                    "access_token": "DEIN_ACCESS_TOKEN",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_rooms(path: Path) -> list[str]:
    """Lädt Room-IDs oder Aliase aus einer Textdatei, eine Zeile pro Raum.
    Zeilen mit '//' am Anfang gelten als Kommentar."""
    if not path.exists():
        print(f"❌ Keine Raumliste gefunden unter {path}")
        print("   Lege eine rooms.txt an, eine Zeile pro Raum, z.B.:")
        print("   !abcdefghijklmno:matrix.h-da.de")
        print("   #gruppe-001:matrix.h-da.de")
        sys.exit(1)

    rooms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        rooms.append(line)
    return rooms


async def resolve_room(client: AsyncClient, room_ref: str) -> str:
    """Gibt die Room-ID zurück. Löst Aliase (#...) automatisch auf."""
    if room_ref.startswith("#"):
        resp = await client.room_resolve_alias(room_ref)
        if hasattr(resp, "room_id"):
            return resp.room_id
        raise RuntimeError(f"Alias konnte nicht aufgelöst werden: {resp}")
    return room_ref


async def broadcast(message: str, rooms_path: Path, use_markdown: bool) -> None:
    room_ids = load_rooms(rooms_path)
    if not room_ids:
        print("❌ Raumliste ist leer.")
        return
    await broadcast_refs(message, room_ids, use_markdown)


async def broadcast_refs(message: str, room_ids: list[str], use_markdown: bool) -> None:
    config = load_config()

    print(f"📡 Sende an {len(room_ids)} Räume...\n")

    client = AsyncClient(config["homeserver"], config["user_id"])
    client.access_token = config["access_token"]
    client.user_id = config["user_id"]

    content = {"msgtype": "m.text", "body": message}
    if use_markdown:
        # Sehr simple Markdown -> HTML Konvertierung für Fett/Kursiv/Listen.
        # Für komplexere Formatierung ggf. das Paket "markdown" nutzen.
        try:
            import markdown as md

            html = md.markdown(message)
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = html
        except ImportError:
            print("⚠️  Paket 'markdown' nicht installiert, sende als Plaintext.")
            print("    Installieren mit: pip install markdown --break-system-packages\n")

    success, failed = [], []

    for room_ref in room_ids:
        try:
            room_id = await resolve_room(client, room_ref)
        except Exception as e:
            failed.append((room_ref, f"Alias-Auflösung fehlgeschlagen: {e}"))
            print(f"  ❌ {room_ref} -> Alias-Auflösung fehlgeschlagen: {e}")
            continue

        try:
            resp = await client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content,
            )
            if isinstance(resp, RoomSendResponse):
                success.append(room_ref)
                print(f"  ✅ {room_ref}")
            else:
                failed.append((room_ref, str(resp)))
                print(f"  ❌ {room_ref} -> {resp}")
        except Exception as e:
            failed.append((room_ref, str(e)))
            print(f"  ❌ {room_ref} -> {e}")

    await client.close()

    print(f"\n📊 Fertig: {len(success)} erfolgreich, {len(failed)} fehlgeschlagen.")
    if failed:
        print("\nFehlgeschlagene Räume:")
        for room_id, err in failed:
            print(f"  - {room_id}: {err}")


def main():
    parser = argparse.ArgumentParser(description="Nachricht an mehrere Matrix-Räume broadcasten.")
    parser.add_argument("message", nargs="?", help="Die zu sendende Nachricht.")
    parser.add_argument("--file", type=Path, help="Nachricht aus Textdatei lesen statt Argument.")
    parser.add_argument(
        "--rooms",
        type=Path,
        default=DEFAULT_ROOMS_PATH,
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
    args = parser.parse_args()

    if args.file:
        message = args.file.read_text(encoding="utf-8").strip()
    elif args.message:
        message = args.message
    else:
        parser.error("Entweder eine Nachricht als Argument oder --file angeben.")
        return

    if args.alias_range:
        start_alias, end_alias = args.alias_range.split("..")
        # Erwartet Format '#prefix-NNN:server', extrahiert prefix, Startzahl, Endzahl
        prefix_start, server = start_alias.rsplit(":", 1)
        prefix, num_start = prefix_start.rsplit("-", 1)
        _, num_end = end_alias.rsplit(":", 1)[0].rsplit("-", 1)
        width = len(num_start)
        room_refs = [
            f"{prefix}-{str(i).zfill(width)}:{server}"
            for i in range(int(num_start), int(num_end) + 1)
        ]
        asyncio.run(broadcast_refs(message, room_refs, args.markdown))
        return

    asyncio.run(broadcast(message, args.rooms, args.markdown))


if __name__ == "__main__":
    main()
