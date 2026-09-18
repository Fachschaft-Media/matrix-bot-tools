"""Gemeinsame Hilfsfunktionen rund um Raum-Mitgliedschaften."""

from nio import AsyncClient, RoomGetStateResponse

# Mitgliedschafts-Status, bei denen niemand (erneut) eingeladen wird:
# bereits Mitglied, offene Einladung, abgelehnt/ausgetreten oder gebannt.
NO_INVITE_MEMBERSHIPS = frozenset({"join", "invite", "leave", "ban"})


async def get_member_status(client: AsyncClient, room_id: str) -> dict[str, str]:
    """Gibt {user_id: membership} für alle bekannten Nutzer:innen eines Raums zurück.

    membership ist 'join', 'invite', 'leave' oder 'ban'. Bei einem Fehler wird
    ein leeres Dict zurückgegeben.
    """
    resp = await client.room_get_state(room_id)
    if not isinstance(resp, RoomGetStateResponse):
        print(f"   ⚠️  Konnte Verlaufsstatus von {room_id} nicht lesen: {resp}")
        return {}

    status: dict[str, str] = {}
    for event in resp.events:
        if event.get("type") != "m.room.member":
            continue
        user_id = event.get("state_key")
        membership = event.get("content", {}).get("membership")
        if user_id and membership:
            status[user_id] = membership
    return status
