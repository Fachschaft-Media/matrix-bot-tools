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

from matrix_tools.paths import resolve
from matrix_tools.session import MatrixError, MatrixSession, open_session

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

NOTIFIED_FILE = "notified_wrong_server.json"
SYNC_TIMEOUT_MS = 30000
REFRESH_RETRY_SECONDS = 60
SYNC_RETRY_SECONDS = 10
# Mitgliedschafts-Status, bei denen niemand (erneut) eingeladen wird:
# bereits Mitglied, offene Einladung, abgelehnt/ausgetreten oder gebannt.
NO_INVITE_MEMBERSHIPS = frozenset({"join", "invite", "leave", "ban"})
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
    """Überwacht Räume live und reagiert auf neue Beitritte.

    Beendet sich bei Fehlern nie selbst: jeder Fehler wird ausgegeben, danach
    läuft der Watchdog weiter bzw. versucht es erneut.
    """

    def __init__(
        self,
        session: MatrixSession,
        settings: WatchdogSettings,
        config_path: Path,
        notified_path: Path,
    ) -> None:
        """Initialisiert den Watchdog mit Sitzung, Einstellungen und Datei-Pfaden."""
        self.session = session
        self.settings = settings
        self.config_path = config_path
        self.notified_path = notified_path
        self.notified = load_notified(notified_path)

    async def invite(self, target_room: str, user_id: str, *, dry_run: bool) -> None:
        """Lädt user_id in target_room ein (bzw. simuliert es im Dry-Run)."""
        if dry_run:
            print(f"   🧪 DRY RUN - würde {user_id} in {target_room} einladen.")
            return
        try:
            await self.session.invite(target_room, user_id)
        except MatrixError as e:
            print(f"   ❌ {e}")
            return
        print(f"   ✅ {user_id} in {target_room} eingeladen.")

    async def invite_if_needed(self, rule: InviteRule, user_id: str) -> None:
        """Lädt user_id ein, sofern die Person nicht schon Mitglied/eingeladen/ausgetreten ist."""
        try:
            status = await self.session.member_status(rule.target_room)
        except MatrixError as e:
            print(f"   ❌ {e}")
            print(f"   {user_id} wird NICHT eingeladen.")
            return
        current = status.get(user_id)
        if current in NO_INVITE_MEMBERSHIPS:
            print(f"   ⏭️  {user_id} übersprungen ({SKIP_LABELS[current]}).")
            return
        await self.invite(rule.target_room, user_id, dry_run=rule.dry_run)

    async def initial_invite_pass(self, rule: InviteRule) -> None:
        """Einmaliger Abgleich beim Start für eine einzelne Auto-Invite-Regel."""
        print(f"🔍 Regel: {sorted(rule.source_rooms)} → {rule.target_room}")
        members: set[str] = set()
        for source_room in sorted(rule.source_rooms):
            try:
                found = await self.session.joined_members(source_room)
            except MatrixError as e:
                print(f"   ❌ {e}")
                continue
            print(f"   {len(found)} Mitglieder in {source_room}.")
            members |= found

        try:
            target_status = await self.session.member_status(rule.target_room)
        except MatrixError as e:
            print(f"   ❌ {e}")
            print("   Regel übersprungen, es wird niemand eingeladen.\n")
            return
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
        try:
            await self.session.send_direct_message(user_id, ws.message)
        except MatrixError as e:
            print(f"   ❌ {e}")
        else:
            print(f"   ✅ DM an {user_id} gesendet.")
        self.notified.add(user_id)
        save_notified(self.notified_path, self.notified)

    async def on_join(self, room_id: str, user_id: str) -> None:
        """Reagiert auf einen neuen Beitritt in einem überwachten Raum."""
        if room_id not in self.settings.watched_rooms:
            return
        try:
            await self.check_wrong_server(room_id, user_id)
            for rule in self.settings.invite_rules:
                if room_id in rule.source_rooms:
                    print(f"👋 Neuer Beitritt in {room_id}: {user_id} (Regel → {rule.target_room})")
                    await self.invite_if_needed(rule, user_id)
        except Exception as e:  # noqa: BLE001 - der Watchdog darf sich nie selbst beenden
            print(f"❌ Unerwarteter Fehler beim Beitritt von {user_id} in {room_id}: {e!r}")

    def print_summary(self) -> None:
        """Gibt eine Übersicht der geladenen Konfiguration aus."""
        ws = self.settings.wrong_server
        ws_state = f"aktiv ({len(ws.watch_rooms)} Räume)" if ws.enabled else "inaktiv"
        print("📋 Konfiguration geladen:")
        print(f"   Wrong-Server-Check: {ws_state}")
        print(f"   Auto-Invite-Regeln: {len(self.settings.invite_rules)}")
        print(f"   Insgesamt überwachte Räume: {len(self.settings.watched_rooms)}\n")

    async def sync_or_wait(self) -> bool:
        """Ein Sync-Durchlauf; bei einem Fehler Meldung ausgeben und warten.

        Gibt True zurück, wenn der Sync geklappt hat.
        """
        try:
            await self.session.sync(SYNC_TIMEOUT_MS)
        except MatrixError as e:
            if e.token_expired:
                print(f"❌ {e}")
                print(
                    "   Der Access Token konnte nicht erneuert werden. Falls das anhält: "
                    f"'matrix-tools login --config {self.config_path}' ausführen."
                )
                print(f"   Neuer Versuch in {REFRESH_RETRY_SECONDS}s...")
                await asyncio.sleep(REFRESH_RETRY_SECONDS)
            else:
                print(f"⚠️  {e}. Neuer Versuch in {SYNC_RETRY_SECONDS}s...")
                await asyncio.sleep(SYNC_RETRY_SECONDS)
            return False
        except Exception as e:  # noqa: BLE001 - der Watchdog darf sich nie selbst beenden
            print(
                f"❌ Unerwarteter Fehler im Sync: {e!r}. Neuer Versuch in {SYNC_RETRY_SECONDS}s..."
            )
            await asyncio.sleep(SYNC_RETRY_SECONDS)
            return False
        return True

    async def run_forever(self) -> None:
        """Initialer Abgleich, danach Dauerlauf mit eigener Sync-Schleife."""
        self.print_summary()

        # Wrong-Server-Check macht bewusst KEINEN initialen Abgleich - nur neue
        # Beitritte ab jetzt, damit Bestandsmitglieder nicht angeschrieben werden.
        if self.settings.invite_rules:
            print("═══ Initialer Abgleich der Auto-Invite-Regeln ═══\n")
            for rule in self.settings.invite_rules:
                await self.initial_invite_pass(rule)

        # Der erste Sync muss klappen, bevor der Callback registriert wird -
        # sonst würden alte Beitritte aus dem Verlauf als neu behandelt.
        print("🔄 Initialer Live-Sync...")
        while not await self.sync_or_wait():
            pass
        print("✅ Bereit. Warte auf neue Beitritte...\n")

        self.session.on_join(self.on_join)
        while True:
            await self.sync_or_wait()


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

    async def main() -> None:
        # Die Sitzung erst innerhalb der Event-Loop öffnen.
        async with open_session(config_path, auto_refresh=True) as session:
            watchdog = Watchdog(session, settings, config_path, resolve(NOTIFIED_FILE))
            await watchdog.run_forever()

    asyncio.run(main())
