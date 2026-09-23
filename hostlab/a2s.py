"""A Steam A2S_INFO query, in about a hundred lines and no dependency.

Two things in this project need it, for different reasons.

**Proving reachability.** ADR 0002 rules generic UDP port checkers and
`nc -vzu` inadmissible, because UDP has no handshake and a checker cannot tell
a filtered port from a silent one. A2S is admissible precisely because the
server *answers*: a reply proves the packet arrived, was processed, and the
reply came back, which is the entire path in one step.

**Reading the player count.** Valheim has no remote administration at all, so
the query port is the only channel through which the platform can learn
anything from the game itself.

`always-on-operation.md` warns that a health check coupled to a game's query
protocol is coupled to that game's releases, and cites LinuxGSM's Valheim
monitor breaking against an update. That is why this is the *liveness* half
only. The durability half, whether saves are advancing, reads the filesystem
and cannot be broken by a game update.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass

HEADER = b"\xff\xff\xff\xff"
A2S_INFO = b"T"
QUERY = HEADER + A2S_INFO + b"Source Engine Query\x00"

RESPONSE_INFO = 0x49  # 'I', the answer
RESPONSE_CHALLENGE = 0x41  # 'A', "ask again with this number"

DEFAULT_TIMEOUT = 5.0


class A2SError(Exception):
    """The server did not answer, or answered something unparseable."""


@dataclass(frozen=True)
class ServerInfo:
    """What the game will tell us about itself. Valheim offers nothing else."""

    name: str
    map_name: str
    folder: str
    game: str
    # The protocol's ID field is 16 bits, so a Steam app id above 65535 is
    # sent truncated: Valheim's 896660 arrives as 44692. Do not compare this
    # to the app id in the manifest; they are not the same number and the
    # mismatch looks like a bug rather than a protocol limit.
    app_id: int
    players: int
    max_players: int
    bots: int


def _read_string(payload: bytes, offset: int) -> tuple[str, int]:
    end = payload.find(b"\x00", offset)
    if end == -1:
        message = "unterminated string in A2S response"
        raise A2SError(message)
    # Server names carry whatever a person typed, so decoding must not be the
    # thing that fails: a mangled character is better than no status at all.
    return payload[offset:end].decode("utf-8", "replace"), end + 1


def parse_info(payload: bytes) -> ServerInfo:
    """Parse an A2S_INFO response body, header already stripped."""
    if len(payload) < 6:
        message = f"A2S response too short to be info: {len(payload)} bytes"
        raise A2SError(message)

    if payload[0] != RESPONSE_INFO:
        message = f"expected an info response (0x49), got 0x{payload[0]:02x}"
        raise A2SError(message)

    offset = 2  # header byte, then the protocol version
    name, offset = _read_string(payload, offset)
    map_name, offset = _read_string(payload, offset)
    folder, offset = _read_string(payload, offset)
    game, offset = _read_string(payload, offset)

    try:
        (app_id,) = struct.unpack_from("<H", payload, offset)
        players = payload[offset + 2]
        max_players = payload[offset + 3]
        bots = payload[offset + 4]
    except (struct.error, IndexError) as error:
        message = f"A2S response ended before the player counts: {error}"
        raise A2SError(message) from error

    return ServerInfo(
        name=name,
        map_name=map_name,
        folder=folder,
        game=game,
        app_id=app_id,
        players=players,
        max_players=max_players,
        bots=bots,
    )


def query(host: str, port: int, timeout: float = DEFAULT_TIMEOUT) -> ServerInfo:
    """Ask a server about itself, answering a challenge if it issues one.

    Modern Source servers reply to an unsolicited A2S_INFO with a four-byte
    challenge rather than an answer, and expect the question again with the
    challenge appended. Skipping that handshake makes a perfectly healthy
    server look dead, which is the worst possible failure for a liveness check
    and the kind that gets diagnosed as a networking problem for an evening.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)

    try:
        body = _exchange(sock, host, port, QUERY, timeout)

        if body and body[0] == RESPONSE_CHALLENGE:
            challenge = body[1:5]
            body = _exchange(sock, host, port, QUERY + challenge, timeout)

        return parse_info(body)
    finally:
        sock.close()


def _exchange(sock: socket.socket, host: str, port: int, request: bytes, timeout: float) -> bytes:
    """Send one datagram and return the reply body, header stripped."""
    sock.sendto(request, (host, port))

    try:
        raw, _ = sock.recvfrom(4096)
    except TimeoutError as error:
        message = (
            f"no A2S reply from {host}:{port} within {timeout}s. For UDP a "
            "timeout is real evidence, unlike a port checker's silence: the "
            "server either answers or it does not."
        )
        raise A2SError(message) from error

    if not raw.startswith(HEADER):
        message = "A2S reply did not carry the simple-response header"
        raise A2SError(message)

    return raw[len(HEADER) :]
