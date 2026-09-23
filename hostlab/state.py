"""Decide whether a state directory holds a copy worth keeping.

This is the module ADR 0005 defends `state_consistency` for, and the one ADR
0003 rests on: "a backup job that reports success because `cp` returned zero
has verified nothing."

Valheim writes a new generation of a world and retires the previous one, then
writes a marker saying the write completed. A generation with a matching
marker is a consistent point; one without it was still in flight. That is the
entire distinction between a backup and a corrupt copy, and it is expressed as
data in the manifest so this module never learns what a Valheim world is.

The same shape answers the other question `always-on-operation.md` says matters
more than liveness: **is state advancing?** A world whose newest complete
generation has not moved in hours is a broken server, whatever a health check
says, and that failure has already happened in this ecosystem with the
container reporting healthy throughout.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hostlab.errors import StateInconsistent

if TYPE_CHECKING:
    from pathlib import Path

    from hostlab.manifest import TitleManifest


@dataclass(frozen=True)
class Generation:
    """One save cycle's worth of files, and whether it finished."""

    number: int
    complete: bool
    completed_at: datetime.datetime | None

    def age(self, now: datetime.datetime | None = None) -> datetime.timedelta | None:
        if self.completed_at is None:
            return None
        moment = now or datetime.datetime.now(datetime.UTC)
        return moment - self.completed_at


@dataclass(frozen=True)
class World:
    """One directory of state, with whatever generations were found in it."""

    name: str
    path: Path
    generations: tuple[Generation, ...]

    @property
    def newest_complete(self) -> Generation | None:
        complete = [generation for generation in self.generations if generation.complete]
        return max(complete, key=lambda generation: generation.number) if complete else None

    @property
    def newest(self) -> Generation | None:
        return max(self.generations, key=lambda g: g.number) if self.generations else None

    @property
    def is_consistent(self) -> bool:
        return self.newest_complete is not None


@dataclass(frozen=True)
class StateInspection:
    """What was found under a state directory."""

    root: Path
    worlds: tuple[World, ...]

    @property
    def is_consistent(self) -> bool:
        # An empty state directory is not inconsistent, it is new. Refusing to
        # back up a server that has not saved yet would be refusing the very
        # first backup, which is the one taken before anything is at risk.
        return all(world.is_consistent for world in self.worlds)

    @property
    def inconsistent_worlds(self) -> tuple[World, ...]:
        return tuple(world for world in self.worlds if not world.is_consistent)

    def stalest_age(self, now: datetime.datetime | None = None) -> datetime.timedelta | None:
        """How long since the least recently saved world last completed a save."""
        ages = [
            world.newest_complete.age(now)
            for world in self.worlds
            if world.newest_complete is not None
        ]
        present = [age for age in ages if age is not None]
        return max(present) if present else None


def inspect_state(manifest: TitleManifest, state_dir: Path) -> StateInspection:
    """Walk a state directory using only what the manifest declares."""
    rule = manifest.state_consistency
    if rule is None:
        message = (
            f"{manifest.id} declares no state_consistency, so nothing can tell a "
            "complete save from one still in flight"
        )
        raise StateInconsistent(message)

    pattern = re.compile(rule.generation_pattern)
    worlds: list[World] = []

    for world_dir in sorted(state_dir.glob(rule.world_glob)):
        if not world_dir.is_dir():
            continue

        names = {entry.name for entry in world_dir.iterdir()}
        numbers = {
            int(match.group("generation"))
            for name in names
            if (match := pattern.search(name)) is not None
        }

        generations: list[Generation] = []
        for number in sorted(numbers):
            marker_name = rule.complete_marker.format(generation=number)
            marker = world_dir / marker_name
            complete = marker_name in names
            completed_at = (
                datetime.datetime.fromtimestamp(marker.stat().st_mtime, tz=datetime.UTC)
                if complete
                else None
            )
            generations.append(
                Generation(number=number, complete=complete, completed_at=completed_at)
            )

        worlds.append(World(name=world_dir.name, path=world_dir, generations=tuple(generations)))

    return StateInspection(root=state_dir, worlds=tuple(worlds))


def require_consistent(inspection: StateInspection) -> None:
    """Refuse loudly rather than copying something that will not restore.

    This is the point at which ADR 0003's "the backup is not accepted until it
    has been restored" becomes enforceable ahead of time instead of only in
    hindsight.
    """
    broken = inspection.inconsistent_worlds
    if not broken:
        return

    details = []
    for world in broken:
        newest = world.newest
        found = (
            f"newest generation {newest.number} has no completion marker"
            if newest is not None
            else "no generations found at all"
        )
        details.append(f"{world.name}: {found}")

    message = (
        "state is not in a consistent condition to copy:\n  "
        + "\n  ".join(details)
        + "\n\nA copy taken now could restore as a world the server refuses to open, "
        "and its response to a world it cannot open is to generate an empty one "
        "rather than to report an error."
    )
    raise StateInconsistent(message)
