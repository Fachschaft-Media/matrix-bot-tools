"""Matrix Room-Creator.

Erstellt automatisch N Matrix-Räume (z.B. 100 Gruppen-Räume für die Campus
Rallye), hängt sie optional in einen bestehenden Space ein und schreibt die
neuen Room-IDs direkt in eine rooms.txt (kompatibel mit 'matrix-tools broadcast').

BENUTZUNG
---------
    # 100 Räume "Gruppe-01" bis "Gruppe-100" erstellen:
    matrix-tools create-rooms --count 100 --prefix "Gruppe"

    # In einen bestehenden Space einhängen (Space-ID aus Element, Raumeinstellungen -> Erweitert):
    matrix-tools create-rooms --count 100 --prefix "Gruppe" --space "!spaceid:matrix.h-da.de"

    # Zusätzlich einen Alias vergeben (z.B. #rallye-gruppe-01:matrix.h-da.de):
    matrix-tools create-rooms --count 100 --prefix "Gruppe" --alias-prefix "rallye-gruppe"

    # Startnummer anpassen (z.B. wenn schon 20 Räume existieren):
    matrix-tools create-rooms --count 80 --prefix "Gruppe" --start 21

HINWEISE
--------
- Räume werden standardmäßig privat (invite-only) erstellt.
- Der Bot ist automatisch Mitglied (Ersteller) jedes Raums, das reicht für
  'matrix-tools broadcast' - eine Einladung ist NICHT nötig.
- Die erzeugten Room-IDs werden an --rooms-out angehängt (Default: rooms.txt),
  bestehende Einträge bleiben erhalten.
"""

import asyncio
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiohttp import ClientError
from nio import AsyncClient, LocalProtocolError, RoomCreateResponse, RoomVisibility

from matrix_tools.config import MatrixConfig, create_client, load_config
from matrix_tools.paths import resolve

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

MIN_NUMBER_WIDTH = 2


class RoomCreationError(Exception):
    """Der Server hat das Erstellen eines Raums abgelehnt."""


@dataclass(frozen=True)
class RoomPlan:
    """Beschreibt, welche Räume erstellt werden sollen."""

    count: int
    prefix: str
    start: int
    space_id: str | None
    alias_prefix: str | None
    public: bool

    def numbers(self) -> list[str]:
        """Gibt die mit Nullen aufgefüllten Raumnummern zurück (z.B. '01'..'100')."""
        width = max(MIN_NUMBER_WIDTH, len(str(self.start + self.count - 1)))
        return [str(i).zfill(width) for i in range(self.start, self.start + self.count)]


def server_name(client: AsyncClient) -> str:
    """Gibt den Servernamen ohne Protokoll zurück (für 'via'-Angaben)."""
    return client.homeserver.replace("https://", "").replace("http://", "")


async def add_to_space(client: AsyncClient, space_id: str, room_id: str) -> None:
    """Verknüpft einen Raum als Child eines Spaces (beide Richtungen)."""
    via = [server_name(client)]
    await client.room_put_state(
        room_id=space_id,
        event_type="m.space.child",
        content={"via": via},
        state_key=room_id,
    )
    await client.room_put_state(
        room_id=room_id,
        event_type="m.space.parent",
        content={"via": via, "canonical": True},
        state_key=space_id,
    )


async def create_room(client: AsyncClient, plan: RoomPlan, number: str) -> str:
    """Erstellt einen einzelnen Raum und gibt dessen Room-ID zurück.

    Wirft RoomCreationError mit der Server-Antwort, falls das Erstellen fehlschlägt.
    """
    name = f"{plan.prefix}-{number}"
    resp = await client.room_create(
        name=name,
        alias=f"{plan.alias_prefix}-{number}" if plan.alias_prefix else None,
        visibility=RoomVisibility.public if plan.public else RoomVisibility.private,
    )
    if not isinstance(resp, RoomCreateResponse):
        raise RoomCreationError(str(resp))
    print(f"  ✅ {name} -> {resp.room_id}")

    if plan.space_id:
        try:
            await add_to_space(client, plan.space_id, resp.room_id)
        except (ClientError, LocalProtocolError, TimeoutError) as e:
            print(f"     ⚠️  Konnte nicht in Space eingehängt werden: {e}")
    return resp.room_id


async def create_rooms(config: MatrixConfig, plan: RoomPlan, rooms_out: Path) -> None:
    """Erstellt alle geplanten Räume und hängt die neuen Room-IDs an rooms_out an."""
    client = create_client(config)
    created: list[str] = []
    failed: list[tuple[str, str]] = []

    for number in plan.numbers():
        name = f"{plan.prefix}-{number}"
        try:
            created.append(await create_room(client, plan, number))
        except (RoomCreationError, ClientError, LocalProtocolError, TimeoutError) as e:
            failed.append((name, str(e)))
            print(f"  ❌ {name} -> {e}")

    await client.close()

    if created:
        with rooms_out.open("a", encoding="utf-8") as f:
            f.writelines(room_id + "\n" for room_id in created)

    print(f"\n📊 Fertig: {len(created)} erstellt, {len(failed)} fehlgeschlagen.")
    if created:
        print(f"   Room-IDs wurden an {rooms_out} angehängt.")
    if failed:
        print("\nFehlgeschlagen:")
        for name, err in failed:
            print(f"  - {name}: {err}")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Registriert die Argumente von ``matrix-tools create-rooms``."""
    parser.add_argument(
        "--count", type=int, required=True, help="Anzahl der zu erstellenden Räume."
    )
    parser.add_argument(
        "--prefix", default="Gruppe", help="Namens-Präfix, z.B. 'Gruppe' -> 'Gruppe-01'."
    )
    parser.add_argument("--start", type=int, default=1, help="Startnummer (Default: 1).")
    parser.add_argument("--space", help="Space-ID, in die die Räume eingehängt werden sollen.")
    parser.add_argument(
        "--alias-prefix",
        help="Wenn gesetzt, wird pro Raum ein Alias '#<prefix>-<nr>:homeserver' vergeben.",
    )
    parser.add_argument(
        "--rooms-out",
        default="rooms.txt",
        help="Datei, an die die neuen Room-IDs angehängt werden (Default: rooms.txt).",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Räume öffentlich statt invite-only erstellen (Default: privat).",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Pfad zur config.json mit den Zugangsdaten (Default: config.json).",
    )


def run(args: argparse.Namespace) -> None:
    """Erstellt die Räume gemäß den Kommandozeilen-Argumenten."""
    if args.count < 1:
        print("❌ --count muss mindestens 1 sein.")
        sys.exit(2)
    plan = RoomPlan(
        count=args.count,
        prefix=args.prefix,
        start=args.start,
        space_id=args.space,
        alias_prefix=args.alias_prefix,
        public=args.public,
    )
    config = load_config(resolve(args.config))
    print(f"🏗️  Erstelle {plan.count} Räume '{plan.prefix}-{plan.numbers()[0]}' ff...\n")
    asyncio.run(create_rooms(config, plan, resolve(args.rooms_out)))
