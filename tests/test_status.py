"""The A2S client, the state reader, and the publisher.

The reader is the whole of ADR 0006 stage 1, and its defining property is
negative: **it can do nothing**. There is no code path here that starts, stops
or restarts anything, and the tests assert that rather than assuming it.
"""

from __future__ import annotations

import ast
import datetime
import re
import shutil
import socket
import struct
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from hostlab.a2s import A2SError, parse_info
from hostlab.a2s import query as a2s_query
from hostlab.manifest import load_manifest
from hostlab.status import (
    RESTART_ALARM,
    ContainerStatus,
    Durability,
    Status,
    format_status,
    read_durability,
    read_join_code,
)

VALHEIM = Path("titles/valheim.yaml")
HEADER = b"\xff\xff\xff\xff"


def build_info_response(name: str = "Midgard", players: int = 3, maximum: int = 10) -> bytes:
    """An A2S_INFO reply shaped the way a Source server sends one."""
    body = bytes([0x49, 17])
    for field in (name, "Midgard", "valheim", "Valheim"):
        body += field.encode("utf-8") + b"\x00"
    # The ID field is 16 bits, so a large Steam app id arrives truncated.
    body += struct.pack("<H", 896660 & 0xFFFF) + bytes([players, maximum, 0])
    return HEADER + body


@pytest.fixture
def a2s_server() -> Iterator[Callable[..., int]]:
    """A one-shot A2S responder, optionally demanding a challenge first."""
    sockets: list[socket.socket] = []

    def start(*, challenge: bool = False, players: int = 3) -> int:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sockets.append(sock)
        port = int(sock.getsockname()[1])

        def serve() -> None:
            _, addr = sock.recvfrom(4096)
            if challenge:
                sock.sendto(HEADER + b"A" + b"\x01\x02\x03\x04", addr)
                request, addr = sock.recvfrom(4096)
                if not request.endswith(b"\x01\x02\x03\x04"):
                    return  # the client failed to echo it; let the test time out
            sock.sendto(build_info_response(players=players), addr)

        threading.Thread(target=serve, daemon=True).start()
        return port

    yield start

    for sock in sockets:
        sock.close()


# ---------------------------------------------------------------------------
# A2S
# ---------------------------------------------------------------------------


def test_a_direct_reply_is_parsed(a2s_server: Callable[..., int]) -> None:
    info = a2s_query("127.0.0.1", a2s_server(), timeout=3)
    assert info.name == "Midgard"
    assert info.players == 3
    assert info.max_players == 10


def test_a_challenge_is_answered_rather_than_treated_as_failure(
    a2s_server: Callable[..., int],
) -> None:
    """Modern Source servers reply to an unsolicited query with a challenge.
    Not answering it makes a perfectly healthy server look dead, which is the
    worst failure a liveness check can have and gets diagnosed as a networking
    problem for an evening."""
    info = a2s_query("127.0.0.1", a2s_server(challenge=True), timeout=3)
    assert info.players == 3


def test_a_timeout_is_reported_as_evidence_not_as_a_hang() -> None:
    """ADR 0002's whole point about UDP: because the server answers, silence
    means something. A port checker's silence does not."""
    with pytest.raises(A2SError, match="no A2S reply"):
        a2s_query("127.0.0.1", 1, timeout=0.5)


def test_a_truncated_response_is_rejected_rather_than_guessed() -> None:
    with pytest.raises(A2SError):
        parse_info(bytes([0x49, 17]) + b"Midgard\x00")


def test_a_non_info_response_is_rejected() -> None:
    with pytest.raises(A2SError, match="0x49"):
        parse_info(bytes([0x6D]) + b"something else")


def test_a_mangled_server_name_does_not_break_the_status() -> None:
    """Server names carry whatever a person typed. Decoding must not be the
    thing that fails, or one odd character costs the whole status."""
    body = bytes([0x49, 17]) + b"\xff\xfeMid\x00Midgard\x00valheim\x00Valheim\x00"
    body += struct.pack("<H", 1) + bytes([1, 10, 0])
    assert parse_info(body).players == 1


# ---------------------------------------------------------------------------
# The reader
# ---------------------------------------------------------------------------


def test_durability_reads_the_newest_complete_generation(
    tmp_path: Path, write_generation: Callable[..., None]
) -> None:
    state = tmp_path / "data"
    write_generation(state / "worlds_local" / "Midgard", 7)
    write_generation(state / "worlds_local" / "Midgard", 8, complete=False)

    durability = read_durability(load_manifest(VALHEIM), state)
    assert durability is not None
    assert durability.worlds == (("Midgard", 7),)
    assert durability.healthy


def test_a_world_with_no_complete_save_is_not_healthy(
    tmp_path: Path, write_generation: Callable[..., None]
) -> None:
    state = tmp_path / "data"
    write_generation(state / "worlds_local" / "Midgard", 8, complete=False)

    durability = read_durability(load_manifest(VALHEIM), state)
    assert durability is not None
    assert not durability.healthy


def status_with(**overrides: object) -> Status:
    base: dict[str, object] = {
        "title_id": "valheim",
        "title_name": "Valheim",
        "container": ContainerStatus(
            running=True,
            started_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=3),
            restart_count=0,
        ),
        "durability": Durability(
            worlds=(("Midgard", 7),),
            stalest=datetime.timedelta(minutes=4),
            limit_seconds=2400,
            consistent=True,
        ),
        "info": None,
        "liveness_error": None,
        "disk_free_bytes": 120_000_000_000,
        "last_backup": datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=6),
        "join_code": None,
    }
    return Status(**{**base, **overrides})  # type: ignore[arg-type]


def test_a_healthy_server_reads_as_online() -> None:
    text = format_status(status_with())
    assert "online" in text
    assert "saves: ok" in text
    assert "Midgard gen 7" in text


def test_a_server_that_is_up_and_not_saving_says_so_loudly() -> None:
    """The failure this project exists to catch, and the one that does not
    report itself. Every liveness check in the world says this server is fine."""
    text = format_status(
        status_with(
            durability=Durability(
                worlds=(("Midgard", 7),),
                stalest=datetime.timedelta(hours=9),
                limit_seconds=2400,
                consistent=True,
            )
        )
    )

    assert "online" in text, "it really is up, which is the point"
    assert "STALE" in text


def test_a_crash_loop_is_reported_even_though_it_is_up_right_now() -> None:
    """always-on-operation.md: a server that restarted eleven times overnight
    is broken. Compose cannot express a rate cap, so the reader carries it."""
    text = format_status(
        status_with(
            container=ContainerStatus(
                running=True,
                started_at=datetime.datetime.now(datetime.UTC),
                restart_count=RESTART_ALARM + 6,
            )
        )
    )
    assert "restarts:" in text
    assert "broken even while it is up" in text


def test_a_query_failure_does_not_masquerade_as_the_server_being_down() -> None:
    """A health check coupled to a game's query protocol is coupled to that
    game's releases, which is what broke LinuxGSM's Valheim monitor. The
    durability half reads the filesystem and cannot be broken by a patch."""
    text = format_status(status_with(liveness_error="no A2S reply"))

    assert "online" in text
    assert "players: unknown" in text
    assert "saves: ok" in text


def test_a_container_that_never_existed_says_so() -> None:
    text = format_status(
        status_with(
            container=ContainerStatus(running=False, started_at=None, restart_count=0, exists=False)
        )
    )
    assert "never been started" in text


def test_the_backup_age_is_visible() -> None:
    """remote-control.md puts the last backup result in front of everyone,
    because an unchecked backup job is the classic false sense of security."""
    assert "backup: 6h ago" in format_status(status_with())
    assert "backup: none recorded" in format_status(status_with(last_backup=None))


# ---------------------------------------------------------------------------
# The reader grants no authority
# ---------------------------------------------------------------------------


def test_the_reader_module_cannot_change_anything() -> None:
    """ADR 0006 consequence 5: the state reader and the action executor are
    separate components, and only the executor has authority. Stage 1 ships
    the reader alone, and this is the assertion that keeps it that way when
    somebody later adds "just a restart button" to a status module."""
    source = Path("hostlab/status.py").read_text(encoding="utf-8")

    forbidden = ('"start"', '"stop"', '"restart"', '"kill"', '"rm"')
    for verb in forbidden:
        assert verb not in source, f"the reader must not be able to {verb}"

    # Every docker call it makes is read-only. Counting occurrences would be
    # brittle, and was: adding the join code reader gave it a second, equally
    # harmless call. What has to hold is the subcommands, not the count.
    subcommands = set(re.findall(r'\["docker", "(\w+)"', source))
    assert subcommands <= {"inspect", "logs"}, (
        f"the reader runs {subcommands - {'inspect', 'logs'}}, which is not reading"
    )


def test_the_publisher_never_reads_its_own_inbox() -> None:
    """ADR 0008 records this as a decision rather than an omission. A bot that
    cannot be instructed has no command surface to get authorization wrong on,
    and a leaked token buys an attacker the ability to edit a status message.

    Checked against the parsed source rather than the text, because the module
    mentions getUpdates in prose in order to say it never calls it, and a
    grep-shaped test would have to choose between passing and letting the
    module explain itself.
    """
    tree = ast.parse(Path("hostlab/publish.py").read_text(encoding="utf-8"))

    # Every request goes through _call(channel, method, payload), so the set of
    # Telegram methods this module can reach is the set of second arguments
    # given to it.
    telegram_methods = {
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_call"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
    }

    assert telegram_methods == {"sendMessage", "editMessageText"}, (
        "stage 1 sends and edits, and does nothing else. Adding a receive here "
        "means also adding identity, authorization and an audit trail, which is "
        "the coupling ADR 0006 intended."
    )


# ---------------------------------------------------------------------------
# The crossplay join code
# ---------------------------------------------------------------------------
# ADR 0009 chose the relay, and ADR 0006 consequence 1 turns publishing the
# code into an obligation: it regenerates on every restart, so a restart nobody
# watched locks out everyone holding yesterday's code. Valheim has no admin
# channel, so the server's log is the only source there is.

REGISTERED = 'Session "Midgard" registered with join code 604510'
ACTIVE = (
    'Session "Midgard" with join code 604510 and IP 203.0.113.4:2456 is active with 0 player(s)'
)
# The server announces the session BEFORE the lobby exists, so this line really
# does go out with nothing where the code should be.
ANNOUNCED_TOO_EARLY = 'Session "Midgard" with join code  and IP  is active with 0 player(s)'


def join_code_pattern() -> str:
    manifest = load_manifest(VALHEIM)
    assert manifest.reachability is not None
    assert manifest.reachability.relay is not None
    assert manifest.reachability.relay.join_code is not None
    return manifest.reachability.relay.join_code.pattern


def test_the_code_is_found_in_both_log_lines_the_server_writes() -> None:
    import re

    for line in (REGISTERED, ACTIVE):
        match = re.search(join_code_pattern(), line)
        assert match is not None
        assert match.group("code") == "604510"


def test_the_announcement_before_the_lobby_exists_is_not_mistaken_for_a_code() -> None:
    """The trap this pattern exists to avoid. A lenient pattern would match
    this line and publish an empty code with great confidence, and the failure
    would look like the server being fine."""
    import re

    assert re.search(join_code_pattern(), ANNOUNCED_TOO_EARLY) is None


def test_a_relay_that_rotates_its_code_must_say_where_to_read_it(
    valheim_raw: dict[str, Any], write_manifest: Callable[..., Path]
) -> None:
    """Otherwise the manifest describes a server that locks people out on every
    restart with no way to recover, and says nothing about it."""
    import copy

    from hostlab.errors import ManifestInvalid

    raw = copy.deepcopy(valheim_raw)
    del raw["reachability"]["relay"]["join_code"]

    with pytest.raises(ManifestInvalid, match="join_code"):
        load_manifest(write_manifest(raw))


def test_a_pattern_that_captures_nothing_is_refused(
    valheim_raw: dict[str, Any], write_manifest: Callable[..., Path]
) -> None:
    import copy

    from hostlab.errors import ManifestInvalid

    raw = copy.deepcopy(valheim_raw)
    raw["reachability"]["relay"]["join_code"]["pattern"] = r"join code (?P<code>\d*)"

    with pytest.raises(ManifestInvalid, match="empty"):
        load_manifest(write_manifest(raw))


def test_a_pattern_without_a_code_group_is_refused(
    valheim_raw: dict[str, Any], write_manifest: Callable[..., Path]
) -> None:
    import copy

    from hostlab.errors import ManifestInvalid

    raw = copy.deepcopy(valheim_raw)
    raw["reachability"]["relay"]["join_code"]["pattern"] = r"join code \d+"

    with pytest.raises(ManifestInvalid, match="code"):
        load_manifest(write_manifest(raw))


def test_the_newest_code_wins_when_the_log_holds_several() -> None:
    """A long-running container's log carries every restart it has survived.
    Taking the first match would publish a code that stopped working weeks ago,
    which is worse than publishing none: it looks current."""
    import re

    log = "\n".join(
        [
            ANNOUNCED_TOO_EARLY,
            'Session "Midgard" registered with join code 111111',
            "some unrelated line",
            'Session "Midgard" registered with join code 999999',
        ]
    )
    matches = re.findall(join_code_pattern(), log)
    assert matches[-1] == "999999"


def test_the_join_code_is_shown_before_anything_a_friend_might_skim_past() -> None:
    """It is how they connect and it is the most perishable line in the
    report, so it goes above the player count and the save state."""
    text = format_status(status_with(join_code="604510"))
    lines = text.splitlines()

    assert any("join code: 604510" in line for line in lines)
    assert lines.index("join code: 604510") == 1


def test_no_join_code_line_when_there_is_none() -> None:
    """A server not using the relay should not carry an empty field."""
    assert "join code" not in format_status(status_with())


@pytest.mark.docker
@pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker")
def test_the_join_code_is_read_out_of_a_real_container_log() -> None:
    """Against an actual `docker logs`, not a string.

    The three things that have to hold at once are all visible in one log: the
    empty announcement is ignored, a code from before the last restart is not
    published as current, and the newest one wins.
    """
    name = f"hostlab-jc-{time.monotonic_ns()}"
    script = "\n".join(
        [
            "echo 'Session \"Midgard\" with join code  and IP  is active with 0 player(s)'",
            "echo 'Session \"Midgard\" registered with join code 111111'",
            "echo 'Session \"Midgard\" registered with join code 604510'",
            "sleep 600",
        ]
    )

    subprocess.run(
        ["docker", "run", "--detach", "--name", name, "alpine", "sh", "-c", script],
        capture_output=True,
        check=True,
        timeout=180,
    )

    try:
        deadline = time.monotonic() + 30
        code = None
        while time.monotonic() < deadline:
            code = read_join_code(load_manifest(VALHEIM), name)
            if code is not None:
                break
            time.sleep(0.25)

        assert code == "604510", "the newest code wins, and the empty line is not one"
    finally:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=False)


def test_no_join_code_is_reported_for_a_container_that_does_not_exist() -> None:
    """Absence has to be absence rather than an exception, because the status
    report has to render for a server that is down as well as one that is up."""
    assert read_join_code(load_manifest(VALHEIM), "hostlab-no-such-container") is None
