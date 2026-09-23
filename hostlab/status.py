"""The state reader of ADR 0006, and only the reader.

ADR 0006 consequence 5 separates the state reader from the action executor and
says only the executor has authority. **Stage 1 ships the reader alone, and
that is what makes stage 1 safe.** Nothing in this module can start, stop or
restart anything, and there is no code path here that could be made to.

`remote-control.md` lists what the reader has to know per title: running or
not, uptime, players connected, the current join code, last backup time and
result, disk used. Everything except the player count comes from the container
runtime or the filesystem, which is why it works uniformly across titles that
expose no control interface of their own.

The ordering in `always-on-operation.md` is followed deliberately and it is
not the conventional one. Liveness is the *least* valuable check here, because
it is the failure that reports itself: somebody notices a server is down within
minutes and complains. The one that matters is durability, the server that is
up and quietly not saving, and it is listed first.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hostlab.a2s import A2SError, ServerInfo
from hostlab.a2s import query as a2s_query
from hostlab.state import inspect_state

if TYPE_CHECKING:
    from pathlib import Path

    from hostlab.manifest import TitleManifest

# A server that restarted this many times is broken even though it is running
# right now. always-on-operation.md: "a server that restarted eleven times
# overnight is broken". Compose cannot express this, so the reader carries it.
RESTART_ALARM = 5

# How far back to look in the container log for the join code. The code is
# written once at startup, so on a long-running server it is far behind the
# newest line. Large enough to survive a chatty boot, bounded so this never
# reads a week of logs.
JOIN_CODE_LOG_LINES = 5000


@dataclass(frozen=True)
class ContainerStatus:
    running: bool
    started_at: datetime.datetime | None
    restart_count: int
    exists: bool = True

    @property
    def uptime(self) -> datetime.timedelta | None:
        if not self.running or self.started_at is None:
            return None
        return datetime.datetime.now(datetime.UTC) - self.started_at

    @property
    def restarting_too_often(self) -> bool:
        return self.restart_count >= RESTART_ALARM


@dataclass(frozen=True)
class Durability:
    """Whether the world is actually being written. The check that matters."""

    worlds: tuple[tuple[str, int | None], ...]
    stalest: datetime.timedelta | None
    limit_seconds: int
    consistent: bool

    @property
    def stale(self) -> bool:
        return self.stalest is not None and self.stalest.total_seconds() > self.limit_seconds

    @property
    def healthy(self) -> bool:
        return self.consistent and not self.stale


@dataclass(frozen=True)
class Status:
    """Everything the reader knows. Read-only by construction."""

    title_id: str
    title_name: str
    container: ContainerStatus
    durability: Durability | None
    info: ServerInfo | None
    liveness_error: str | None
    disk_free_bytes: int | None
    last_backup: datetime.datetime | None
    join_code: str | None = None

    @property
    def players(self) -> int | None:
        return self.info.players if self.info is not None else None


def _docker_inspect(container: str) -> dict[str, Any] | None:
    try:
        completed = subprocess.run(
            # ADR 0008 chose the docker CLI over the SDK precisely so this is
            # the command an operator would type at 2am. Resolving it through
            # PATH is part of that: an absolute path would differ between
            # Docker Desktop, a WSL install and a CI runner.
            ["docker", "inspect", container],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None

    parsed: list[dict[str, Any]] = json.loads(completed.stdout)
    return parsed[0] if parsed else None


def read_container(container: str) -> ContainerStatus:
    inspected = _docker_inspect(container)
    if inspected is None:
        return ContainerStatus(running=False, started_at=None, restart_count=0, exists=False)

    state = inspected.get("State", {})
    started_raw = state.get("StartedAt")
    started_at = None
    if isinstance(started_raw, str):
        try:
            # Docker reports nanoseconds, which fromisoformat will not take.
            trimmed = started_raw.replace("Z", "+00:00")
            if "." in trimmed:
                head, _, tail = trimmed.partition(".")
                fraction, sign, offset = tail.partition("+")
                trimmed = f"{head}.{fraction[:6]}{sign}{offset}"
            started_at = datetime.datetime.fromisoformat(trimmed)
        except ValueError:
            started_at = None

    return ContainerStatus(
        running=bool(state.get("Running", False)),
        started_at=started_at,
        restart_count=int(inspected.get("RestartCount", 0)),
    )


def read_join_code(manifest: TitleManifest, container: str) -> str | None:
    """Find the relay join code in the container's log.

    ADR 0009 chose crossplay, and ADR 0006 consequence 1 makes publishing the
    code an obligation: it regenerates on every restart, so a restart nobody
    watched silently locks out everyone holding yesterday's code.

    Valheim has no administration channel, so the log is the only source. The
    pattern comes from the manifest rather than from here, which keeps a log
    format change a manifest edit instead of a code change.

    **The last match wins, not the first.** The server announces the session
    before the lobby exists, and it restarts, so earlier lines in the same log
    carry stale codes or none at all.
    """
    relay = manifest.reachability.relay if manifest.reachability is not None else None
    if relay is None or relay.join_code is None:
        return None

    try:
        completed = subprocess.run(
            ["docker", "logs", "--tail", str(JOIN_CODE_LOG_LINES), container],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None

    # Valheim writes to stdout, but a title that writes to stderr should not
    # silently produce no code.
    stream = completed.stdout + completed.stderr
    matches = re.findall(relay.join_code.pattern, stream)
    return str(matches[-1]) if matches else None


def read_durability(manifest: TitleManifest, state_dir: Path) -> Durability | None:
    if manifest.state_consistency is None or not state_dir.exists():
        return None

    inspection = inspect_state(manifest, state_dir)
    worlds = tuple(
        (world.name, world.newest_complete.number if world.newest_complete else None)
        for world in inspection.worlds
    )
    return Durability(
        worlds=worlds,
        stalest=inspection.stalest_age(),
        limit_seconds=manifest.health.durability.max_stale_seconds,
        consistent=inspection.is_consistent,
    )


def read_status(
    manifest: TitleManifest,
    container: str,
    state_dir: Path,
    *,
    query_host: str = "127.0.0.1",
    query_port: int | None = None,
    last_backup: datetime.datetime | None = None,
) -> Status:
    container_status = read_container(container)

    info: ServerInfo | None = None
    liveness_error: str | None = None
    if container_status.running:
        port = query_port or manifest.health.liveness.port
        try:
            info = a2s_query(query_host, port)
        except A2SError as error:
            # Not fatal, and deliberately not conflated with "down". A query
            # failure can mean the game changed its protocol, which is exactly
            # what broke LinuxGSM's Valheim monitor. Durability still answers.
            liveness_error = str(error)

    disk_free = shutil.disk_usage(state_dir).free if state_dir.exists() else None

    return Status(
        title_id=manifest.id,
        title_name=manifest.name,
        container=container_status,
        durability=read_durability(manifest, state_dir),
        info=info,
        liveness_error=liveness_error,
        disk_free_bytes=disk_free,
        last_backup=last_backup,
        join_code=read_join_code(manifest, container) if container_status.running else None,
    )


def _humanise(delta: datetime.timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{seconds // 60}m"
    if seconds < 172800:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def format_status(status: Status) -> str:
    """A short, human report. The same text the publisher sends.

    One renderer for both so the channel and the terminal cannot disagree, and
    so anything the owner reads over SSH is what the friends are reading too.
    """
    lines: list[str] = []

    if not status.container.exists:
        lines.append(f"{status.title_name}: no container. It has never been started here.")
        return "\n".join(lines)

    if status.container.running:
        uptime = status.container.uptime
        up = f"up {_humanise(uptime)}" if uptime else "up"
        lines.append(f"{status.title_name}: online, {up}")
    else:
        lines.append(f"{status.title_name}: OFFLINE")

    # Before anything else a friend might read past. This is how they connect,
    # and it changes on every restart, so it is the most perishable line here.
    if status.join_code is not None:
        lines.append(f"join code: {status.join_code}")

    if status.info is not None:
        lines.append(f"players: {status.info.players}/{status.info.max_players}")
    elif status.liveness_error is not None:
        lines.append("players: unknown, the server is not answering queries")

    # Durability before liveness, deliberately. The server that is up and not
    # saving is the failure this project exists to catch, and it is the one
    # that does not announce itself.
    durability = status.durability
    if durability is not None:
        if not durability.consistent:
            lines.append("saves: NO COMPLETE SAVE ON DISK")
        elif durability.stale:
            stale = durability.stalest
            lines.append(
                f"saves: STALE, nothing written for {_humanise(stale)}" if stale else "saves: STALE"
            )
        else:
            newest = ", ".join(
                f"{name} gen {number}" for name, number in durability.worlds if number
            )
            lines.append(f"saves: ok ({newest})" if newest else "saves: ok")

    if status.container.restarting_too_often:
        lines.append(
            f"restarts: {status.container.restart_count}. "
            "A server that keeps restarting is broken even while it is up."
        )

    if status.last_backup is not None:
        age = datetime.datetime.now(datetime.UTC) - status.last_backup
        lines.append(f"backup: {_humanise(age)} ago")
    else:
        lines.append("backup: none recorded")

    if status.disk_free_bytes is not None:
        lines.append(f"disk free: {status.disk_free_bytes / 1_000_000_000:.1f} GB")

    return "\n".join(lines)
