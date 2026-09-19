"""Laden und Prüfen der settings.json des Watchdogs.

Alle Werte werden beim Start geprüft; bei Fehlern wird ein ``ConfigError`` mit
allen gefundenen Problemen geworfen, bevor der Watchdog irgendetwas tut. So
fällt z.B. ein Tippfehler in 'dry_run' auf, statt stillschweigend echte
Einladungen zu verschicken.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from matrix_tools.config import ConfigError, is_http_url, read_json_file

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_SENDER_NAME = "deine Fachschaft"
# '_comment' ist überall erlaubt, damit die Datei kommentiert werden kann.
TOP_LEVEL_KEYS = frozenset({"wrong_server", "auto_invite_rules", "_comment"})
WRONG_SERVER_KEYS = frozenset(
    {"enabled", "watch_rooms", "correct_domain", "guide_url", "sender_name", "dry_run", "_comment"}
)
RULE_KEYS = frozenset({"source_rooms", "target_room", "dry_run", "_comment"})


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


class _Checker:
    """Liest Werte aus der settings.json und sammelt dabei alle Probleme."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def section(self, value: object, where: str, allowed_keys: frozenset[str]) -> dict[str, Any]:
        """Prüft, dass value ein JSON-Objekt ohne unbekannte Schlüssel ist."""
        if not isinstance(value, dict):
            self.problems.append(f"{where}: muss ein JSON-Objekt {{...}} sein")
            return {}
        section = cast("dict[str, Any]", value)
        self.problems.extend(
            f"{where}: unbekannter Schlüssel '{key}' (Tippfehler? Erlaubt: "
            f"{', '.join(sorted(allowed_keys))})"
            for key in sorted(section.keys() - allowed_keys)
        )
        return section

    def boolean(self, section: dict[str, Any], key: str, where: str) -> bool:
        """Liest einen optionalen Wahrheitswert (Default: false)."""
        value = section.get(key, False)
        if not isinstance(value, bool):
            self.problems.append(
                f"{where}.{key}: muss true oder false sein (ohne Anführungszeichen)"
            )
            return False
        return value

    def text(self, section: dict[str, Any], key: str, where: str, *, required: bool) -> str:
        """Liest einen Text; bei required=True darf er nicht fehlen oder leer sein."""
        value = section.get(key)
        if value is None and not required:
            return ""
        if not isinstance(value, str) or not value.strip():
            self.problems.append(f"{where}.{key}: fehlt oder ist leer")
            return ""
        return value.strip()

    def room_id(self, value: object, where: str) -> str:
        """Prüft eine einzelne Room-ID (beginnt mit '!')."""
        if not isinstance(value, str) or not value.startswith("!"):
            self.problems.append(
                f"{where}: muss eine Room-ID sein, die mit '!' beginnt (kein Alias '#...'), "
                f"ist aber {value!r}"
            )
            return ""
        return value

    def room_ids(self, section: dict[str, Any], key: str, where: str) -> frozenset[str]:
        """Liest eine nicht-leere Liste von Room-IDs."""
        value = section.get(key)
        if not isinstance(value, list) or not value:
            self.problems.append(
                f"{where}.{key}: muss eine nicht-leere Liste von Room-IDs sein, "
                'z.B. ["!abc:server"] - auch bei nur einem Raum in eckigen Klammern'
            )
            return frozenset()
        rooms = cast("list[object]", value)
        return frozenset(
            self.room_id(room, f"{where}.{key}[{index}]") for index, room in enumerate(rooms)
        )


def parse_settings(raw: object, *, global_dry_run: bool) -> tuple[WatchdogSettings, list[str]]:
    """Wandelt den Inhalt der settings.json in Einstellungen um.

    Gibt die Einstellungen und alle gefundenen Probleme zurück; die
    Einstellungen sind nur gültig, wenn die Liste leer ist.
    """
    check = _Checker()
    top = check.section(raw, "settings.json", TOP_LEVEL_KEYS)

    ws_raw = check.section(top.get("wrong_server", {}), "wrong_server", WRONG_SERVER_KEYS)
    enabled = check.boolean(ws_raw, "enabled", "wrong_server")
    # Die Pflichtfelder werden nur verlangt, wenn der Check aktiv ist - sonst
    # würde z.B. eine fehlende correct_domain JEDEN neuen Beitritt anschreiben.
    watch_rooms = (
        check.room_ids(ws_raw, "watch_rooms", "wrong_server") if enabled else frozenset[str]()
    )
    correct_domain = check.text(ws_raw, "correct_domain", "wrong_server", required=enabled)
    guide_url = check.text(ws_raw, "guide_url", "wrong_server", required=enabled)
    if guide_url and not is_http_url(guide_url):
        check.problems.append(f"wrong_server.guide_url: muss mit https:// beginnen: {guide_url}")
    sender_name = check.text(ws_raw, "sender_name", "wrong_server", required=False)
    wrong_server = WrongServerSettings(
        enabled=enabled,
        watch_rooms=watch_rooms,
        correct_domain=correct_domain,
        message=build_wrong_server_message(guide_url, sender_name or DEFAULT_SENDER_NAME),
        dry_run=check.boolean(ws_raw, "dry_run", "wrong_server") or global_dry_run,
    )

    rules_raw = top.get("auto_invite_rules", [])
    if not isinstance(rules_raw, list):
        check.problems.append("auto_invite_rules: muss eine Liste von Regeln [...] sein")
        rules_raw = []
    rules: list[InviteRule] = []
    for index, rule_value in enumerate(cast("list[object]", rules_raw)):
        where = f"auto_invite_rules[{index}]"
        if not isinstance(rule_value, dict):
            check.problems.append(f"{where}: muss ein JSON-Objekt {{...}} sein")
            continue
        rule_raw = check.section(rule_value, where, RULE_KEYS)
        target_room = rule_raw.get("target_room")
        rules.append(
            InviteRule(
                source_rooms=check.room_ids(rule_raw, "source_rooms", where),
                target_room=check.room_id(target_room, f"{where}.target_room"),
                dry_run=check.boolean(rule_raw, "dry_run", where) or global_dry_run,
            )
        )

    return WatchdogSettings(wrong_server=wrong_server, invite_rules=rules), check.problems


def load_settings(settings_path: Path, *, global_dry_run: bool) -> WatchdogSettings:
    """Lädt und prüft die settings.json. Wirft ConfigError mit allen gefundenen Problemen."""
    raw = read_json_file(
        settings_path,
        missing_hint="Kopiere examples/settings.example.json nach settings.json und passe sie an.",
    )
    settings, problems = parse_settings(raw, global_dry_run=global_dry_run)
    if problems:
        raise ConfigError(settings_path, problems)
    return settings
