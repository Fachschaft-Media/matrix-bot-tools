"""Matrix Watchdog (vereinheitlicht).

EIN durchgehendes Dauerlauf-Tool, das komplett über eine settings.json
konfiguriert wird, statt für jede Regel ein eigenes Script mit CLI-Flags zu
starten. Kombiniert:

  - Wrong-Server-Check: neue Beitritte mit falschem Matrix-Server werden
    automatisch per DM informiert.
  - Auto-Invite-Regeln: beliebig viele Regeln der Form "wer Raum/Räume X
    beitritt, wird automatisch in Raum Y eingeladen" - für Space->Raum
    genauso wie für ausgewählte Kanäle->Space.

Läuft mit EINER einzigen Matrix-Session (eine config.json), dadurch entfällt
auch das Problem, dass mehrere parallele Prozesse sich beim Token-Refresh
gegenseitig aussperren ("Token-Tennis").

SETUP
-----
1. config.json im Daten-Ordner anlegen (Zugangsdaten, siehe Haupt-README
   bzw. 'matrix-tools login' für SSO-Server).
2. examples/settings.example.json nach settings.json kopieren und an eure
   Bedürfnisse anpassen (siehe docs/watchdog.md).

BENUTZUNG
---------
    matrix-tools watchdog
    matrix-tools watchdog --settings settings.json --config config.json
    matrix-tools watchdog --dry-run    # nichts wird tatsächlich verschickt/eingeladen
"""

import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from nio import (
    AsyncClient,
    Event,
    JoinedMembersResponse,
    MatrixRoom,
    RoomCreateResponse,
    RoomInviteResponse,
    RoomMemberEvent,
    RoomSendResponse,
    SyncError,
)

from matrix_tools.auth import is_token_error, refresh_access_token
from matrix_tools.config import create_client, load_config
from matrix_tools.members import NO_INVITE_MEMBERSHIPS, get_member_status
from matrix_tools.paths import resolve

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

NOTIFIED_FILE = "notified_wrong_server.json"
SYNC_TIMEOUT_MS = 30000
REFRESH_RETRY_SECONDS = 60
SYNC_RETRY_SECONDS = 10
SKIP_LABELS = {
    "join": "bereits Mitglied",
    "invite": "bereits eingeladen",
    "leave": "hat abgelehnt/ist ausgetreten",
    "ban": "gebannt",
}


# ─────────────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WrongServerSettings:
    """Einstellungen des Wrong-Server-Checks."""

    enabled: bool
    watch_rooms: frozenset[str]
    correct_domain: str
    message: str
    dry_run: bool


@dataclass(frozen=True)
class InviteRule:
    """Eine Auto-Invite-Regel: Beitritte in source_rooms werden nach target_room eingeladen."""

    source_rooms: frozenset[str]
    target_room: str
    dry_run: bool


@dataclass(frozen=True)
class WatchdogSettings:
    """Alle Verhaltensregeln des Watchdogs aus der settings.json."""

    wrong_server: WrongServerSettings
    invite_rules: list[InviteRule] = field(default_factory=list)

    @property
    def watched_rooms(self) -> frozenset[str]:
        """Alle überwachten Räume (Wrong-Server + alle Invite-Regel-Quellen)."""
        rooms = set(self.wrong_server.watch_rooms)
        for rule in self.invite_rules:
            rooms |= rule.source_rooms
        return frozenset(rooms)


def build_wrong_server_message(guide_url: str, sender_name: str) -> str:
    """Baut die DM für Personen, die sich mit dem falschen Server angemeldet haben."""
    return (
        "Heyy, voll cool, dass du gejoint bist! 🎉\n\n"
        "Das ist am Anfang alles etwas kompliziert: Es sieht so aus, als hättest du dich "
        "mit dem falschen Server angemeldet. Bitte melde dich nochmal mit dem richtigen "
        "Hochschul-Server an, hier ist erklärt wie:\n"
        f"{guide_url}\n\n"
        'Wichtig: den richtigen Server auswählen und auf "Anmelden" klicken, NICHT '
        '"Registrieren" - falls ihr als Teil der Hochschule schon automatisch einen '
        "Account habt.\n\n"
        "Liebe Grüße,\n"
        f"{sender_name}"
    )


def parse_settings(raw: dict[str, Any], *, global_dry_run: bool) -> WatchdogSettings:
    """Wandelt den Inhalt der settings.json in typisierte Einstellungen um."""
    wrong_server = raw.get("wrong_server", {})
    ws_settings = WrongServerSettings(
        enabled=wrong_server.get("enabled", False),
        watch_rooms=frozenset(wrong_server.get("watch_rooms", [])),
        correct_domain=wrong_server.get("correct_domain", ""),
        message=build_wrong_server_message(
            wrong_server.get("guide_url", "https://example.edu/matrix-anleitung"),
            wrong_server.get("sender_name", "deine Fachschaft"),
        ),
        dry_run=global_dry_run or wrong_server.get("dry_run", False),
    )
    rules = [
        InviteRule(
            source_rooms=frozenset(rule["source_rooms"]),
            target_room=rule["target_room"],
            dry_run=global_dry_run or rule.get("dry_run", False),
        )
        for rule in raw.get("auto_invite_rules", [])
    ]
    return WatchdogSettings(wrong_server=ws_settings, invite_rules=rules)


def load_settings(settings_path: Path) -> dict[str, Any]:
    """Lädt die settings.json und beendet das Programm mit einem Hinweis, falls sie fehlt."""
    if not settings_path.exists():
        print(f"❌ Keine settings.json gefunden unter {settings_path}")
        print("   Kopiere examples/settings.example.json nach settings.json und passe sie an.")
        sys.exit(1)
    settings: dict[str, Any] = json.loads(settings_path.read_text(encoding="utf-8"))
    return settings


def load_notified(notified_path: Path) -> set[str]:
    """Lädt die Liste bereits per DM informierter Nutzer:innen."""
    if not notified_path.exists():
        return set()
    try:
        return set(json.loads(notified_path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return set()


def save_notified(notified_path: Path, notified: set[str]) -> None:
    """Speichert die Liste bereits per DM informierter Nutzer:innen."""
    notified_path.write_text(
        json.dumps(sorted(notified), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def domain_of(user_id: str) -> str:
    """Gibt die Server-Domain einer Matrix-ID zurück (@name:domain -> domain)."""
    return user_id.split(":", 1)[1] if ":" in user_id else ""


# ─────────────────────────────────────────────────────────────────────────
# Watchdog
# ─────────────────────────────────────────────────────────────────────────


class Watchdog:
    """Überwacht Räume live und reagiert auf neue Beitritte."""

    def __init__(
        self,
        client: AsyncClient,
        settings: WatchdogSettings,
        config_path: Path,
        notified_path: Path,
    ) -> None:
        """Initialisiert den Watchdog mit Client, Einstellungen und Datei-Pfaden."""
        self.client = client
        self.settings = settings
        self.config_path = config_path
        self.notified_path = notified_path
        self.notified = load_notified(notified_path)

    async def send_dm(self, user_id: str, message: str) -> bool:
        """Erstellt einen DM-Raum mit user_id und schickt dort die Nachricht."""
        resp = await self.client.room_create(
            is_direct=True, preset=None, invite=[user_id], name=None
        )
        if not isinstance(resp, RoomCreateResponse):
            print(f"   ❌ DM-Raum für {user_id} konnte nicht erstellt werden: {resp}")
            return False
        send_resp = await self.client.room_send(
            room_id=resp.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": message},
        )
        if not isinstance(send_resp, RoomSendResponse):
            print(f"   ❌ Nachricht an {user_id} konnte nicht gesendet werden: {send_resp}")
            return False
        return True

    async def invite(self, target_room: str, user_id: str, *, dry_run: bool) -> None:
        """Lädt user_id in target_room ein (bzw. simuliert es im Dry-Run)."""
        if dry_run:
            print(f"   🧪 DRY RUN - würde {user_id} in {target_room} einladen.")
            return
        resp = await self.client.room_invite(target_room, user_id)
        if isinstance(resp, RoomInviteResponse):
            print(f"   ✅ {user_id} in {target_room} eingeladen.")
        else:
            print(f"   ❌ Einladung an {user_id} fehlgeschlagen: {resp}")

    async def invite_if_needed(self, rule: InviteRule, user_id: str) -> None:
        """Lädt user_id ein, sofern die Person nicht schon Mitglied/eingeladen/ausgetreten ist."""
        status = await get_member_status(self.client, rule.target_room)
        current = status.get(user_id)
        if current in NO_INVITE_MEMBERSHIPS:
            print(f"   ⏭️  {user_id} übersprungen ({SKIP_LABELS[current]}).")
            return
        await self.invite(rule.target_room, user_id, dry_run=rule.dry_run)

    async def joined_members(self, room_id: str) -> set[str] | None:
        """Liest die Mitglieder eines Raums, erneuert bei Bedarf einmalig den Token."""
        resp = await self.client.joined_members(room_id)
        if not isinstance(resp, JoinedMembersResponse):
            if is_token_error(resp) and refresh_access_token(self.config_path, self.client):
                resp = await self.client.joined_members(room_id)
            if not isinstance(resp, JoinedMembersResponse):
                print(f"   ❌ Konnte {room_id} nicht lesen: {resp}")
                return None
        return {member.user_id for member in resp.members}

    async def initial_invite_pass(self, rule: InviteRule) -> None:
        """Einmaliger Abgleich beim Start für eine einzelne Auto-Invite-Regel."""
        print(f"🔍 Regel: {sorted(rule.source_rooms)} → {rule.target_room}")
        members: set[str] = set()
        for source_room in sorted(rule.source_rooms):
            found = await self.joined_members(source_room)
            if found is None:
                continue
            print(f"   {len(found)} Mitglieder in {source_room}.")
            members |= found

        target_status = await get_member_status(self.client, rule.target_room)
        for user_id in sorted(members):
            if target_status.get(user_id) not in NO_INVITE_MEMBERSHIPS:
                await self.invite(rule.target_room, user_id, dry_run=rule.dry_run)
        print()

    async def check_wrong_server(self, room_id: str, user_id: str) -> None:
        """Schickt eine DM, falls user_id mit dem falschen Server beigetreten ist."""
        ws = self.settings.wrong_server
        if not ws.enabled or room_id not in ws.watch_rooms or user_id in self.notified:
            return
        domain = domain_of(user_id)
        if domain == ws.correct_domain:
            return
        print(f"🚨 {user_id} ist mit falschem Server ({domain}) in {room_id} beigetreten.")
        if ws.dry_run:
            print("   🧪 DRY RUN - würde DM senden.")
            return
        if await self.send_dm(user_id, ws.message):
            print(f"   ✅ DM an {user_id} gesendet.")
        self.notified.add(user_id)
        save_notified(self.notified_path, self.notified)

    async def on_member_event(self, room: MatrixRoom, event: Event) -> None:
        """Reagiert auf Mitgliedschafts-Events in überwachten Räumen."""
        if not isinstance(event, RoomMemberEvent):
            return
        if room.room_id not in self.settings.watched_rooms:
            return
        if event.membership != "join" or event.prev_membership == "join":
            return  # kein neuer Beitritt

        user_id = event.state_key
        await self.check_wrong_server(room.room_id, user_id)

        for rule in self.settings.invite_rules:
            if room.room_id in rule.source_rooms:
                print(
                    f"👋 Neuer Beitritt in {room.room_id}: {user_id} (Regel → {rule.target_room})"
                )
                await self.invite_if_needed(rule, user_id)

    def print_summary(self) -> None:
        """Gibt eine Übersicht der geladenen Konfiguration aus."""
        ws = self.settings.wrong_server
        ws_state = f"aktiv ({len(ws.watch_rooms)} Räume)" if ws.enabled else "inaktiv"
        print("📋 Konfiguration geladen:")
        print(f"   Wrong-Server-Check: {ws_state}")
        print(f"   Auto-Invite-Regeln: {len(self.settings.invite_rules)}")
        print(f"   Insgesamt überwachte Räume: {len(self.settings.watched_rooms)}\n")

    async def run_forever(self) -> None:
        """Initialer Abgleich, danach Dauerlauf mit eigener Sync-Schleife inkl. Token-Refresh."""
        self.print_summary()

        # Wrong-Server-Check macht bewusst KEINEN initialen Abgleich - nur neue
        # Beitritte ab jetzt, damit Bestandsmitglieder nicht angeschrieben werden.
        if self.settings.invite_rules:
            print("═══ Initialer Abgleich der Auto-Invite-Regeln ═══\n")
            for rule in self.settings.invite_rules:
                await self.initial_invite_pass(rule)

        print("🔄 Initialer Live-Sync...")
        resp = await self.client.sync(timeout=SYNC_TIMEOUT_MS)
        if (
            isinstance(resp, SyncError)
            and is_token_error(resp)
            and refresh_access_token(self.config_path, self.client)
        ):
            await self.client.sync(timeout=SYNC_TIMEOUT_MS)
        print("✅ Bereit. Warte auf neue Beitritte...\n")

        self.client.add_event_callback(self.on_member_event, RoomMemberEvent)

        # Eigene Sync-Schleife statt sync_forever(), für Auto-Refresh bei
        # abgelaufenem Token.
        while True:
            resp = await self.client.sync(timeout=SYNC_TIMEOUT_MS)
            if not isinstance(resp, SyncError):
                continue
            if not is_token_error(resp):
                print(f"⚠️  Sync-Fehler: {resp}. Warte {SYNC_RETRY_SECONDS}s...")
                await asyncio.sleep(SYNC_RETRY_SECONDS)
            elif not refresh_access_token(self.config_path, self.client):
                print(
                    "❌ Token-Refresh fehlgeschlagen. "
                    f"Warte {REFRESH_RETRY_SECONDS}s und versuche erneut..."
                )
                await asyncio.sleep(REFRESH_RETRY_SECONDS)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Registriert die Argumente von ``matrix-tools watchdog``."""
    parser.add_argument(
        "--config",
        default="config.json",
        help="Pfad zur config.json mit den Zugangsdaten (Default: config.json).",
    )
    parser.add_argument(
        "--settings",
        default="settings.json",
        help="Pfad zur settings.json mit den Verhaltensregeln (Default: settings.json).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="GLOBAL nichts tatsächlich senden/einladen, egal was in settings.json steht.",
    )


def run(args: argparse.Namespace) -> None:
    """Startet den Watchdog im Dauerlauf."""
    config_path = resolve(args.config)
    settings = parse_settings(load_settings(resolve(args.settings)), global_dry_run=args.dry_run)
    config = load_config(config_path)

    async def main() -> None:
        # Den Client erst innerhalb der Event-Loop erstellen.
        watchdog = Watchdog(create_client(config), settings, config_path, resolve(NOTIFIED_FILE))
        await watchdog.run_forever()

    asyncio.run(main())
