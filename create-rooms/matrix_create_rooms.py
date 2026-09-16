#!/usr/bin/env python3
"""
Matrix Room-Creator
====================
Erstellt automatisch N Matrix-Räume (z.B. 100 Gruppen-Räume für die Campus
Rallye), hängt sie optional in einen bestehenden Space ein und schreibt die
neuen Room-IDs direkt in eine rooms.txt (kompatibel mit matrix_broadcast.py).

SETUP
-----
Nutzt die gleiche config.json wie matrix_broadcast.py:
    {
      "homeserver": "https://matrix.h-da.de",
      "user_id": "@rallye-bot:matrix.h-da.de",
      "access_token": "DEIN_ACCESS_TOKEN"
    }

BENUTZUNG
---------
    # 100 Räume "Gruppe 01" bis "Gruppe 100" erstellen:
    python matrix_create_rooms.py --count 100 --prefix "Gruppe"

    # In einen bestehenden Space einhängen (Space-ID aus Element, Raumeinstellungen -> Erweitert):
    python matrix_create_rooms.py --count 100 --prefix "Gruppe" --space "!spaceid:matrix.h-da.de"

    # Zusätzlich einen Alias vergeben (z.B. #rallye-gruppe-01:matrix.h-da.de):
    python matrix_create_rooms.py --count 100 --prefix "Gruppe" --alias-prefix "rallye-gruppe"

    # Startnummer anpassen (z.B. wenn schon 20 Räume existieren):
    python matrix_create_rooms.py --count 80 --prefix "Gruppe" --start 21

HINWEISE
--------
- Räume werden standardmäßig privat (invite-only) erstellt.
- Der Bot ist automatisch Mitglied (Ersteller) jedes Raums, das reicht für
  matrix_broadcast.py - eine Einladung ist NICHT nötig.
- Die erzeugten Room-IDs werden an --rooms-out angehängt (Default: rooms.txt),
  bestehende Einträge bleiben erhalten.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from nio import AsyncClient, RoomCreateResponse, RoomVisibility

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = Path(__file__).parent / "config.json"
DEFAULT_ROOMS_OUT = Path(__file__).parent / "rooms.txt"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"❌ Keine config.json gefunden unter {CONFIG_PATH}")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


async def add_to_space(client: AsyncClient, space_id: str, room_id: str) -> None:
    """Verknüpft einen Raum als Child eines Spaces (beide Richtungen)."""
    await client.room_put_state(
        room_id=space_id,
        event_type="m.space.child",
        content={"via": [client.homeserver.replace("https://", "").replace("http://", "")]},
        state_key=room_id,
    )
    await client.room_put_state(
        room_id=room_id,
        event_type="m.space.parent",
        content={
            "via": [client.homeserver.replace("https://", "").replace("http://", "")],
            "canonical": True,
        },
        state_key=space_id,
    )


async def create_rooms(
    count: int,
    prefix: str,
    start: int,
    space_id: Optional[str],
    alias_prefix: Optional[str],
    rooms_out: Path,
    public: bool,
) -> None:
    config = load_config()

    client = AsyncClient(config["homeserver"], config["user_id"])
    client.access_token = config["access_token"]
    client.user_id = config["user_id"]

    created = []
    failed = []

    width = len(str(start + count - 1))  # z.B. "01".."100" konsistent zweistellig+

    for i in range(start, start + count):
        number = str(i).zfill(max(2, width))
        name = f"{prefix}-{number}"
        alias = f"{alias_prefix}-{number}" if alias_prefix else None

        try:
            resp = await client.room_create(
                name=name,
                alias=alias,
                visibility=RoomVisibility.public if public else RoomVisibility.private,
            )
            if isinstance(resp, RoomCreateResponse):
                room_id = resp.room_id
                created.append(room_id)
                print(f"  ✅ {name} -> {room_id}")

                if space_id:
                    try:
                        await add_to_space(client, space_id, room_id)
                    except Exception as e:
                        print(f"     ⚠️  Konnte nicht in Space eingehängt werden: {e}")
            else:
                failed.append((name, str(resp)))
                print(f"  ❌ {name} -> {resp}")
        except Exception as e:
            failed.append((name, str(e)))
            print(f"  ❌ {name} -> {e}")

    await client.close()

    if created:
        with rooms_out.open("a", encoding="utf-8") as f:
            for room_id in created:
                f.write(room_id + "\n")

    print(f"\n📊 Fertig: {len(created)} erstellt, {len(failed)} fehlgeschlagen.")
    if created:
        print(f"   Room-IDs wurden an {rooms_out} angehängt.")
    if failed:
        print("\nFehlgeschlagen:")
        for name, err in failed:
            print(f"  - {name}: {err}")


def main():
    parser = argparse.ArgumentParser(description="Mehrere Matrix-Räume auf einmal erstellen.")
    parser.add_argument("--count", type=int, required=True, help="Anzahl der zu erstellenden Räume.")
    parser.add_argument("--prefix", default="Gruppe", help="Namens-Präfix, z.B. 'Gruppe' -> 'Gruppe 01'.")
    parser.add_argument("--start", type=int, default=1, help="Startnummer (Default: 1).")
    parser.add_argument("--space", help="Space-ID, in die die Räume eingehängt werden sollen.")
    parser.add_argument(
        "--alias-prefix",
        help="Wenn gesetzt, wird pro Raum ein Alias '#<prefix>-<nr>:homeserver' vergeben.",
    )
    parser.add_argument(
        "--rooms-out",
        type=Path,
        default=DEFAULT_ROOMS_OUT,
        help="Datei, an die die neuen Room-IDs angehängt werden (Default: rooms.txt).",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Räume öffentlich statt invite-only erstellen (Default: privat).",
    )
    args = parser.parse_args()

    print(f"🏗️  Erstelle {args.count} Räume '{args.prefix} {str(args.start).zfill(2)}' ff...\n")

    asyncio.run(
        create_rooms(
            count=args.count,
            prefix=args.prefix,
            start=args.start,
            space_id=args.space,
            alias_prefix=args.alias_prefix,
            rooms_out=args.rooms_out,
            public=args.public,
        )
    )


if __name__ == "__main__":
    main()
