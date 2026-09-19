"""Auto-Invite-Abgleich: wer aus Quellräumen fehlt, wird in einen Zielraum eingeladen.

Gemeinsame Logik für 'matrix-tools sync-members' (einmalig) und den Watchdog
(beim Start und bei jedem neuen Beitritt). Niemand wird (erneut) eingeladen,
der im Zielraum bereits Mitglied ist, eine offene Einladung hat, sie abgelehnt
hat bzw. ausgetreten ist, oder gebannt wurde.

Kann der Zielraum nicht gelesen werden, wird ein MatrixError geworfen und
niemand eingeladen - sonst würden Personen, die abgelehnt haben oder
ausgetreten sind, erneut eingeladen.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from matrix_tools.session import MatrixError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from matrix_tools.session import MatrixSession

# Mitgliedschafts-Status im Zielraum, bei denen niemand (erneut) eingeladen wird.
SKIP_LABELS = {
    "join": "bereits Mitglied",
    "invite": "bereits eingeladen",
    "leave": "abgelehnt/ausgetreten",
    "ban": "gebannt",
}


@dataclass(frozen=True)
class InvitePlan:
    """Ergebnis des Abgleichs: wer eingeladen wird und wer mit welchem Status übersprungen."""

    target_room: str
    to_invite: list[str]
    skipped: dict[str, str]

    def print_summary(self) -> None:
        """Gibt aus, wie viele eingeladen und wie viele aus welchem Grund übersprungen werden."""
        counts = [
            f"{count} {label}"
            for membership, label in SKIP_LABELS.items()
            if (count := sum(1 for m in self.skipped.values() if m == membership))
        ]
        skipped = f", übersprungen: {', '.join(counts)}" if counts else ""
        print(f"   📋 {len(self.to_invite)} einzuladen{skipped}.")


@dataclass
class InviteResult:
    """Ergebnis der Einladungen."""

    invited: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


async def members_of(session: MatrixSession, rooms: Iterable[str]) -> set[str]:
    """Gibt alle aktuellen Mitglieder der Räume zurück. Wirft MatrixError, falls einer fehlt."""
    members: set[str] = set()
    for room_id in sorted(rooms):
        found = await session.joined_members(room_id)
        print(f"   {len(found)} Mitglieder in {room_id}.")
        members |= found
    return members


async def plan_invites(
    session: MatrixSession, target_room: str, candidates: Iterable[str]
) -> InvitePlan:
    """Ermittelt, wer von candidates in target_room eingeladen werden muss.

    Wirft MatrixError, falls der Zielraum nicht gelesen werden kann.
    """
    status = await session.member_status(target_room)
    to_invite: list[str] = []
    skipped: dict[str, str] = {}
    for user_id in sorted(set(candidates)):
        membership = status.get(user_id)
        if membership in SKIP_LABELS:
            skipped[user_id] = membership
        else:
            to_invite.append(user_id)
    return InvitePlan(target_room, to_invite, skipped)


async def apply_invites(session: MatrixSession, plan: InvitePlan, *, dry_run: bool) -> InviteResult:
    """Verschickt die Einladungen aus plan (bzw. simuliert sie im Dry-Run)."""
    result = InviteResult()
    for user_id in plan.to_invite:
        if dry_run:
            print(f"   🧪 DRY RUN - würde {user_id} in {plan.target_room} einladen.")
            continue
        try:
            await session.invite(plan.target_room, user_id)
        except MatrixError as e:
            result.failed.append((user_id, str(e)))
            print(f"   ❌ {e}")
            continue
        result.invited.append(user_id)
        print(f"   ✅ {user_id} in {plan.target_room} eingeladen.")
    return result


async def reconcile_invites(
    session: MatrixSession, target_room: str, candidates: Iterable[str], *, dry_run: bool
) -> InviteResult:
    """Lädt alle candidates in target_room ein, die dort noch fehlen.

    Wirft MatrixError (und lädt niemanden ein), falls der Zielraum nicht
    gelesen werden kann. Fehlgeschlagene einzelne Einladungen stehen im Ergebnis.
    """
    plan = await plan_invites(session, target_room, candidates)
    plan.print_summary()
    return await apply_invites(session, plan, dry_run=dry_run)
