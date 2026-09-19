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
from typing import TYPE_CHECKING, cast

from matrix_tools.config import ConfigError, read_json_file
from matrix_tools.invites import members_of, reconcile_invites
from matrix_tools.paths import resolve
from matrix_tools.session import MatrixError, MatrixSession, open_session
from matrix_tools.settings import InviteRule, WatchdogSettings, load_settings

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

NOTIFIED_FILE = "notified_wrong_server.json"
SYNC_TIMEOUT_MS = 30000
REFRESH_RETRY_SECONDS = 60
SYNC_RETRY_SECONDS = 10


def load_notified(notified_path: Path) -> set[str]:
    """Lädt die Liste bereits per DM informierter Nutzer:innen.

    Wirft ConfigError, falls die Datei kaputt ist - sonst würden alle bereits
    Informierten erneut angeschrieben und die Liste überschrieben.
    """
    if not notified_path.exists():
        return set()
    raw = read_json_file(notified_path, missing_hint="")
    if not isinstance(raw, list) or not all(isinstance(u, str) for u in raw):
        raise ConfigError(
            notified_path,
            [
                (
                    'muss eine Liste von User-IDs sein, z.B. ["@name:server"]. Datei reparieren '
                    "oder löschen (dann werden bereits Informierte ggf. erneut angeschrieben)."
                )
            ],
        )
    return set(cast("list[str]", raw))


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

    async def invite_if_needed(self, rule: InviteRule, user_id: str) -> None:
        """Lädt user_id ein, sofern die Person nicht schon Mitglied/eingeladen/ausgetreten ist."""
        try:
            await reconcile_invites(self.session, rule.target_room, {user_id}, dry_run=rule.dry_run)
        except MatrixError as e:
            print(f"   ❌ {e}")
            print(f"   {user_id} wird NICHT eingeladen.")

    async def initial_invite_pass(self, rule: InviteRule) -> None:
        """Einmaliger Abgleich beim Start für eine einzelne Auto-Invite-Regel."""
        print(f"🔍 Regel: {sorted(rule.source_rooms)} → {rule.target_room}")
        try:
            members = await members_of(self.session, rule.source_rooms)
            await reconcile_invites(self.session, rule.target_room, members, dry_run=rule.dry_run)
        except MatrixError as e:
            print(f"   ❌ {e}")
            print("   Regel übersprungen, es wird niemand eingeladen.")
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
    settings = load_settings(resolve(args.settings), global_dry_run=args.dry_run)
    notified_path = resolve(NOTIFIED_FILE)
    load_notified(notified_path)  # kaputte Datei schon vor dem Verbinden melden

    async def main() -> None:
        # Die Sitzung erst innerhalb der Event-Loop öffnen.
        async with open_session(config_path, auto_refresh=True) as session:
            watchdog = Watchdog(session, settings, config_path, notified_path)
            await watchdog.run_forever()

    asyncio.run(main())
