"""Matrix-Sitzung: einzige Stelle, die direkt mit dem Matrix-Server spricht.

Die Befehle nutzen nur die Methoden von ``MatrixSession`` und importieren nio
nicht selbst. Die Sitzung

  - erstellt den Client aus der config.json und schließt ihn auch bei Fehlern,
  - wirft bei jedem Fehlschlag (Fehlerantwort des Servers oder Netzwerkfehler)
    einen ``MatrixError`` mit Aktion, Fehlercode und Fehlermeldung des Servers,
  - behandelt einen abgelaufenen Access Token:
      * mit ``auto_refresh=True`` (Watchdog): Token erneuern und den Aufruf
        einmal wiederholen, sonst ``MatrixError``,
      * ohne (alle anderen Befehle): sofort ``TokenExpiredError``, damit der
        Befehl mit einem Hinweis auf 'matrix-tools login' abbricht.
"""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError
from nio import (
    AsyncClient,
    ErrorResponse,
    Event,
    JoinedMembersResponse,
    LocalProtocolError,
    MatrixRoom,
    RoomCreateResponse,
    RoomGetStateResponse,
    RoomInviteResponse,
    RoomMemberEvent,
    RoomPutStateResponse,
    RoomResolveAliasResponse,
    RoomSendResponse,
    RoomVisibility,
    SyncResponse,
)

from matrix_tools.auth import is_token_error, refresh_access_token
from matrix_tools.config import MatrixConfig, load_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
    from pathlib import Path

    JoinCallback = Callable[[str, str], Awaitable[None]]


class MatrixError(Exception):
    """Ein Aufruf an den Matrix-Server ist fehlgeschlagen.

    Die Fehlermeldung enthält die Aktion, den Matrix-Fehlercode (z.B.
    M_FORBIDDEN) und die Fehlermeldung des Servers bzw. den Netzwerkfehler.
    """

    def __init__(self, action: str, reason: object) -> None:
        """Baut die Fehlermeldung aus der Aktion und der Server-Antwort bzw. Exception."""
        self.action = action
        self.token_expired = is_token_error(reason)
        if isinstance(reason, ErrorResponse):
            self.errcode = reason.status_code
            detail = f"{reason.status_code or 'kein Fehlercode'}: {reason.message}"
            if reason.retry_after_ms:
                detail += f" (erneut versuchen in {reason.retry_after_ms} ms)"
        else:
            self.errcode = None
            detail = f"{type(reason).__name__}: {reason}"
        super().__init__(f"{action} fehlgeschlagen - {detail}")


class TokenExpiredError(Exception):
    """Der Access Token ist abgelaufen und die Sitzung erneuert ihn nicht selbst."""

    def __init__(self, action: str, reason: object, config_path: Path) -> None:
        """Baut eine Fehlermeldung mit Hinweis, wie der Token erneuert wird."""
        super().__init__(
            f"{MatrixError(action, reason)}\n"
            "   Der Access Token ist abgelaufen. Bitte neu anmelden:\n"
            f"   matrix-tools login --config {config_path}\n"
            "   und den Befehl danach erneut ausführen."
        )


class MatrixSession:
    """Angemeldete Verbindung zum Matrix-Server mit den Aufrufen, die die Befehle brauchen."""

    def __init__(self, config: MatrixConfig, config_path: Path, *, auto_refresh: bool) -> None:
        """Erstellt den Client aus den Zugangsdaten (innerhalb der Event-Loop aufrufen)."""
        self._config_path = config_path
        self._auto_refresh = auto_refresh
        self._client = AsyncClient(config["homeserver"], config["user_id"])
        self._client.access_token = config["access_token"]
        self._client.user_id = config["user_id"]

    @property
    def server_name(self) -> str:
        """Servername ohne Protokoll (für 'via'-Angaben)."""
        return self._client.homeserver.replace("https://", "").replace("http://", "")

    async def close(self) -> None:
        """Schließt die Verbindung."""
        await self._client.close()

    # ── Aufrufe ──────────────────────────────────────────────────────────

    async def joined_members(self, room_id: str) -> set[str]:
        """Gibt die User-IDs aller aktuellen Mitglieder eines Raums zurück."""
        resp = await self._call(
            f"Mitglieder von {room_id} lesen",
            lambda: self._client.joined_members(room_id),
            JoinedMembersResponse,
        )
        return {member.user_id for member in resp.members}

    async def member_status(self, room_id: str) -> dict[str, str]:
        """Gibt {user_id: membership} für alle bekannten Nutzer:innen eines Raums zurück.

        membership ist 'join', 'invite', 'leave' oder 'ban'.
        """
        resp = await self._call(
            f"Mitgliedschaften in {room_id} lesen",
            lambda: self._client.room_get_state(room_id),
            RoomGetStateResponse,
        )
        status: dict[str, str] = {}
        for event in resp.events:
            if event.get("type") != "m.room.member":
                continue
            user_id = event.get("state_key")
            membership = event.get("content", {}).get("membership")
            if user_id and membership:
                status[user_id] = membership
        return status

    async def invite(self, room_id: str, user_id: str) -> None:
        """Lädt user_id in room_id ein."""
        await self._call(
            f"Einladung von {user_id} in {room_id}",
            lambda: self._client.room_invite(room_id, user_id),
            RoomInviteResponse,
        )

    async def send_message(self, room_id: str, content: Mapping[str, str]) -> None:
        """Sendet eine Nachricht (m.room.message) mit dem gegebenen Inhalt in room_id."""
        await self._call(
            f"Nachricht an {room_id} senden",
            lambda: self._client.room_send(
                room_id=room_id, message_type="m.room.message", content=dict(content)
            ),
            RoomSendResponse,
        )

    async def create_room(
        self,
        *,
        name: str | None = None,
        alias: str | None = None,
        public: bool = False,
        invite: Sequence[str] = (),
        is_direct: bool = False,
    ) -> str:
        """Erstellt einen Raum und gibt dessen Room-ID zurück."""
        action = f"Raum {name} erstellen" if name else f"DM-Raum mit {', '.join(invite)} erstellen"
        resp = await self._call(
            action,
            lambda: self._client.room_create(
                name=name,
                alias=alias,
                visibility=RoomVisibility.public if public else RoomVisibility.private,
                invite=invite,
                is_direct=is_direct,
            ),
            RoomCreateResponse,
        )
        return resp.room_id

    async def send_direct_message(self, user_id: str, body: str) -> None:
        """Erstellt einen DM-Raum mit user_id und schickt dort eine Textnachricht."""
        room_id = await self.create_room(invite=[user_id], is_direct=True)
        await self.send_message(room_id, {"msgtype": "m.text", "body": body})

    async def put_state(
        self, room_id: str, event_type: str, content: dict[str, Any], state_key: str
    ) -> None:
        """Setzt ein State-Event in room_id."""
        await self._call(
            f"State {event_type} in {room_id} setzen",
            lambda: self._client.room_put_state(
                room_id=room_id, event_type=event_type, content=content, state_key=state_key
            ),
            RoomPutStateResponse,
        )

    async def resolve_alias(self, alias: str) -> str:
        """Löst einen Raum-Alias (#...) in eine Room-ID auf."""
        resp = await self._call(
            f"Alias {alias} auflösen",
            lambda: self._client.room_resolve_alias(alias),
            RoomResolveAliasResponse,
        )
        return resp.room_id

    async def sync(self, timeout_ms: int) -> None:
        """Holt neue Events vom Server; registrierte Callbacks laufen dabei mit."""
        await self._call("Sync", lambda: self._client.sync(timeout=timeout_ms), SyncResponse)

    def on_join(self, callback: JoinCallback) -> None:
        """Ruft callback(room_id, user_id) bei jedem neuen Beitritt während eines Syncs auf."""

        async def handle(room: MatrixRoom, event: Event) -> None:
            if not isinstance(event, RoomMemberEvent):
                return
            if event.membership != "join" or event.prev_membership == "join":
                return  # kein neuer Beitritt
            await callback(room.room_id, event.state_key)

        self._client.add_event_callback(handle, RoomMemberEvent)

    # ── Intern ───────────────────────────────────────────────────────────

    async def _call[T](
        self, action: str, request: Callable[[], Awaitable[object]], expected: type[T]
    ) -> T:
        """Führt einen Aufruf aus und behandelt Fehler und abgelaufene Tokens."""
        resp = await self._send(action, request)
        if is_token_error(resp):
            if not self._auto_refresh:
                raise TokenExpiredError(action, resp, self._config_path)
            access_token = refresh_access_token(self._config_path)
            if access_token is not None:
                self._client.access_token = access_token
                resp = await self._send(action, request)
        if isinstance(resp, expected):
            return resp
        raise MatrixError(action, resp)

    async def _send(self, action: str, request: Callable[[], Awaitable[object]]) -> object:
        """Schickt die Anfrage ab und wandelt Netzwerkfehler in MatrixError um."""
        try:
            return await request()
        except (ClientError, LocalProtocolError, TimeoutError) as e:
            raise MatrixError(action, e) from e


@asynccontextmanager
async def open_session(
    config_path: Path, *, auto_refresh: bool = False
) -> AsyncIterator[MatrixSession]:
    """Öffnet eine Sitzung mit den Zugangsdaten aus config_path und schließt sie danach.

    Beendet das Programm mit einem Hinweis, falls die config.json fehlt.
    """
    session = MatrixSession(load_config(config_path), config_path, auto_refresh=auto_refresh)
    try:
        yield session
    finally:
        await session.close()
