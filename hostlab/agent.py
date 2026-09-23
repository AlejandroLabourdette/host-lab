"""The long-running process that makes status and backups happen by themselves.

ADR 0008 decided on "a long-running process with its own timers, not cron
inside a container", because a cron job in a container writes to a log nobody
collects and fails silently, which is the failure mode
`always-on-operation.md` says matters most here.

Two jobs on two very different clocks:

**Publish**, every few minutes. Under [ADR 0009] the join code is how anyone
connects at all and it regenerates on every restart, so the gap between a
restart and the channel being told is the length of time the group is locked
out. That is what sets the interval, not a wish to seem live.

**Back up**, once a day. ADR 0003 asks for daily.

Three rules hold the loop together, and each exists because of a way this sort
of process usually fails:

1. **A failure never stops the loop.** A Telegram outage must not end the
   backups.
2. **A failure is never silent.** It is logged with what failed and why, on
   stdout, where `docker logs` collects it.
3. **A missed backup runs as soon as it can.** The host is a laptop that will
   be asleep, rebooting, or shut at 05:00 sometimes, and a scheduler that only
   fires exactly on the hour would skip those days entirely and report nothing.
"""

from __future__ import annotations

import datetime
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hostlab.backup import Repository, back_up, snapshots, verify
from hostlab.errors import HostlabError
from hostlab.publish import Channel, publish
from hostlab.status import format_status, read_status

if TYPE_CHECKING:
    from pathlib import Path

    from hostlab.manifest import TitleManifest

SNAPSHOT_TIME = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class AgentConfig:
    manifest: TitleManifest
    container: str
    state_dir: Path
    channel: Channel | None
    repository: Repository | None
    publish_every: datetime.timedelta
    backup_at: datetime.time | None
    query_host: str = "127.0.0.1"
    query_port: int | None = None


def backup_is_due(
    now: datetime.datetime,
    backup_at: datetime.time,
    last_backup: datetime.datetime | None,
) -> bool:
    """Has the most recent scheduled moment passed without a backup since?

    Expressed against the last scheduled *moment* rather than against the
    calendar day, so a host that was asleep at 05:00 backs up when it wakes
    instead of skipping until tomorrow. On a laptop that is the normal case,
    not the edge case.
    """
    if last_backup is None:
        return True

    todays = datetime.datetime.combine(now.date(), backup_at, tzinfo=now.tzinfo)
    most_recent_scheduled = todays if now >= todays else todays - datetime.timedelta(days=1)
    return last_backup < most_recent_scheduled


def last_backup_time(repository: Repository, title_id: str) -> datetime.datetime | None:
    """When restic last took a snapshot, or None if it cannot be asked.

    The repository is the source of truth rather than a local note, so the
    agent cannot believe it backed up when it did not. Unreachable reads as
    "no backup", which makes the agent try, which is the right way round: the
    failure then surfaces as a backup error rather than as silence.
    """
    try:
        listing = snapshots(repository, title_id)
    except HostlabError:
        return None

    found = re.findall(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", listing)
    if not found:
        return None
    return datetime.datetime.strptime(max(found), SNAPSHOT_TIME).astimezone()


def _log(message: str) -> None:
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{stamp} {message}", flush=True)


def publish_once(config: AgentConfig) -> bool:
    """Read the status and publish it. Returns whether the server looks healthy."""
    last_backup = (
        last_backup_time(config.repository, config.manifest.id)
        if config.repository is not None
        else None
    )

    status = read_status(
        config.manifest,
        container=config.container,
        state_dir=config.state_dir,
        query_host=config.query_host,
        query_port=config.query_port,
        last_backup=last_backup,
    )

    text = format_status(status)

    if config.channel is not None:
        publish(config.channel, text)

    healthy = status.container.running and (status.durability is None or status.durability.healthy)
    if not healthy:
        _log(f"status is not healthy:\n{text}")

    return healthy


def back_up_once(config: AgentConfig) -> None:
    """Take a backup and verify the repository afterwards."""
    if config.repository is None:
        return

    status = read_status(
        config.manifest,
        container=config.container,
        state_dir=config.state_dir,
        query_port=config.query_port,
    )

    # The agent cannot stop the server: ADR 0010's proxy refuses every mutating
    # call, deliberately. So this is always a hot copy, and back_up refuses one
    # unless the title has declared it safe and said why.
    back_up(
        config.manifest,
        config.state_dir,
        config.repository,
        server_is_running=status.container.running,
    )
    verify(config.repository)
    _log("backup complete and repository verified")


def run(config: AgentConfig, *, iterations: int | None = None) -> None:
    """The loop.

    `iterations` bounds it so the loop itself can be tested rather than only
    its parts. Left unset it runs until the container stops.
    """
    _log(
        f"agent starting for {config.manifest.id}: publishing every "
        f"{int(config.publish_every.total_seconds())}s, backup at "
        f"{config.backup_at.isoformat() if config.backup_at else 'never'}"
    )

    completed = 0
    while iterations is None or completed < iterations:
        try:
            publish_once(config)
        except HostlabError as error:
            # A Telegram outage must not end the backups.
            _log(f"publish failed: {error}")

        if config.backup_at is not None and config.repository is not None:
            try:
                due = backup_is_due(
                    datetime.datetime.now().astimezone(),
                    config.backup_at,
                    last_backup_time(config.repository, config.manifest.id),
                )
                if due:
                    _log("backup is due")
                    back_up_once(config)
            except HostlabError as error:
                _log(f"backup failed: {error}")

        completed += 1
        if iterations is None or completed < iterations:
            time.sleep(config.publish_every.total_seconds())
