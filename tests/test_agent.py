"""The loop that makes status and backups happen without anyone asking.

Two things here are worth testing and the rest is plumbing.

**The backup schedule**, because a laptop is asleep, rebooting or shut at
05:00 often enough that "fires exactly on the hour" would skip whole days and
say nothing about it. The rule is expressed against the last scheduled
*moment* rather than the calendar day, which is what makes a missed window
catch up instead of being lost.

**Failure isolation**, because the two jobs share a loop and have nothing else
in common. A Telegram outage must not end the backups, and neither may end the
loop, but neither may pass in silence either.
"""

from __future__ import annotations

import datetime
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from hostlab.agent import AgentConfig, backup_is_due, run
from hostlab.errors import HostlabError
from hostlab.manifest import load_manifest

VALHEIM = Path("titles/valheim.yaml")
FIVE_AM = datetime.time(5, 0)
UTC = datetime.UTC


def at(day: int, hour: int, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 9, day, hour, minute, tzinfo=UTC)


# ---------------------------------------------------------------------------
# The schedule
# ---------------------------------------------------------------------------


def test_a_backup_is_due_when_there_has_never_been_one() -> None:
    assert backup_is_due(at(23, 12), FIVE_AM, None)


def test_not_due_again_the_same_day() -> None:
    """The loop runs every few minutes. Without this it would back up on every
    tick from 05:00 until midnight."""
    assert not backup_is_due(at(23, 12), FIVE_AM, at(23, 5))


def test_due_once_the_next_scheduled_moment_passes() -> None:
    assert backup_is_due(at(24, 5, 1), FIVE_AM, at(23, 5))


def test_not_due_before_todays_moment_arrives() -> None:
    """At 03:00, yesterday's 05:00 backup is still the current one."""
    assert not backup_is_due(at(24, 3), FIVE_AM, at(23, 5))


def test_a_missed_window_runs_as_soon_as_it_can() -> None:
    """The case that matters on a laptop. The machine was asleep at 05:00 and
    wakes at 09:00; the backup happens at 09:00 rather than being skipped
    until tomorrow, which a calendar-day rule would have done."""
    assert backup_is_due(at(24, 9), FIVE_AM, at(23, 5))


def test_several_missed_days_still_only_produce_one_backup() -> None:
    """Catching up means catching up, not taking one backup per day missed."""
    now = at(27, 9)
    assert backup_is_due(now, FIVE_AM, at(23, 5))
    # And once it has run, it is not due again until tomorrow's moment.
    assert not backup_is_due(now, FIVE_AM, now)


def test_the_boundary_minute_is_inclusive() -> None:
    assert backup_is_due(at(24, 5, 0), FIVE_AM, at(23, 5))


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------


def config(**overrides: Any) -> AgentConfig:
    base = AgentConfig(
        manifest=load_manifest(VALHEIM),
        container="valheim",
        state_dir=Path("/nonexistent"),
        channel=None,
        repository=None,
        publish_every=datetime.timedelta(seconds=0),
        backup_at=None,
    )
    return replace(base, **overrides)


def test_a_publish_failure_does_not_stop_the_loop(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A Telegram outage must not end the backups, which share this loop and
    have nothing else in common with publishing."""
    attempts = {"count": 0}

    def exploding(_: AgentConfig) -> bool:
        attempts["count"] += 1
        message = "Telegram is having a bad day"
        raise HostlabError(message)

    monkeypatch.setattr("hostlab.agent.publish_once", exploding)
    run(config(), iterations=3)

    assert attempts["count"] == 3, "the loop kept going"
    assert "publish failed" in capsys.readouterr().out, "and it was not silent"


def test_a_backup_failure_does_not_stop_the_loop(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hostlab.backup import Repository

    monkeypatch.setattr("hostlab.agent.publish_once", lambda _: True)
    monkeypatch.setattr("hostlab.agent.last_backup_time", lambda *_: None)

    def exploding(_: AgentConfig) -> None:
        message = "the repository is unreachable"
        raise HostlabError(message)

    monkeypatch.setattr("hostlab.agent.back_up_once", exploding)

    run(
        config(repository=Repository(location="/nowhere"), backup_at=FIVE_AM),
        iterations=2,
    )

    output = capsys.readouterr().out
    assert "backup failed" in output
    assert "the repository is unreachable" in output


def test_an_unhealthy_status_is_logged_even_when_publishing_works(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Publishing to a channel nobody is reading is not the same as reporting.
    A server that is up and not saving has to reach the container log too,
    which is what `docker logs` collects."""
    from hostlab.agent import publish_once
    from hostlab.status import ContainerStatus, Durability, Status

    unhealthy = Status(
        title_id="valheim",
        title_name="Valheim",
        container=ContainerStatus(running=True, started_at=None, restart_count=0),
        durability=Durability(
            worlds=(("Midgard", 7),),
            stalest=datetime.timedelta(hours=9),
            limit_seconds=2400,
            consistent=True,
        ),
        info=None,
        liveness_error=None,
        disk_free_bytes=1,
        last_backup=None,
    )

    def always_unhealthy(*_args: object, **_kwargs: object) -> Status:
        return unhealthy

    monkeypatch.setattr("hostlab.agent.read_status", always_unhealthy)

    assert publish_once(config()) is False
    assert "STALE" in capsys.readouterr().out


def test_the_loop_reports_what_it_is_doing_when_it_starts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Whoever reads `docker logs hostlab` should not have to guess the
    schedule from the source."""
    monkeypatch.setattr("hostlab.agent.publish_once", lambda _: True)
    run(config(backup_at=FIVE_AM), iterations=1)

    started = capsys.readouterr().out
    assert "agent starting for valheim" in started
    assert "05:00" in started
