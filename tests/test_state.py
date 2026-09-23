"""Telling a complete save from one in flight.

ADR 0005 defends `state_consistency` on the grounds that "a backup service
that only knows 'copy this directory' cannot make that distinction, and the
whole value of the platform rests on the backup being real". This is the code
that makes the distinction, so these are the tests that matter most in the
repository.

Nothing here knows what a Valheim world is. Every rule comes out of the
manifest.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from pathlib import Path

import pytest

from hostlab.errors import StateInconsistent
from hostlab.manifest import load_manifest
from hostlab.state import StateInspection, inspect_state, require_consistent

VALHEIM = Path("titles/valheim.yaml")


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    state = tmp_path / "data"
    (state / "worlds_local").mkdir(parents=True)
    (state / "adminlist.txt").write_text("Steam_76561198000000000\n")
    return state


def inspect(state: Path) -> StateInspection:
    return inspect_state(load_manifest(VALHEIM), state)


def test_the_newest_complete_generation_is_chosen(
    state_dir: Path, write_generation: Callable[..., None]
) -> None:
    world = state_dir / "worlds_local" / "Midgard"
    for number in (5, 6, 7):
        write_generation(world, number)

    found = inspect(state_dir).worlds[0].newest_complete
    assert found is not None
    assert found.number == 7


def test_a_generation_still_in_flight_is_not_chosen(
    state_dir: Path, write_generation: Callable[..., None]
) -> None:
    """The exact case the `.ok` marker exists for. Generation 8 is being
    written; copying it would give a world the server cannot open, and its
    answer to a world it cannot open is to generate an empty one."""
    world = state_dir / "worlds_local" / "Midgard"
    write_generation(world, 7)
    write_generation(world, 8, complete=False)

    inspection = inspect(state_dir)
    found = inspection.worlds[0].newest_complete
    assert found is not None
    assert found.number == 7

    newest = inspection.worlds[0].newest
    assert newest is not None
    assert newest.number == 8
    assert not newest.complete

    # And the state as a whole is still fine to copy: there IS a complete
    # generation, which is what the backup will restore to.
    assert inspection.is_consistent


def test_generations_are_ordered_numerically_not_lexically(
    state_dir: Path, write_generation: Callable[..., None]
) -> None:
    """Generation 10 comes after generation 9. Sorted as text it does not, and
    the backup would silently start preferring an older save the day a world
    crossed into double digits."""
    world = state_dir / "worlds_local" / "Midgard"
    for number in (8, 9, 10):
        write_generation(world, number)

    found = inspect(state_dir).worlds[0].newest_complete
    assert found is not None
    assert found.number == 10


def test_a_world_with_no_complete_generation_is_refused(
    state_dir: Path, write_generation: Callable[..., None]
) -> None:
    world = state_dir / "worlds_local" / "Midgard"
    write_generation(world, 8, complete=False)

    inspection = inspect(state_dir)
    assert not inspection.is_consistent

    with pytest.raises(StateInconsistent) as refusal:
        require_consistent(inspection)

    assert "Midgard" in str(refusal.value)
    assert "no completion marker" in str(refusal.value)
    # The refusal has to say what happens if it is ignored, because "not
    # consistent" invites someone to copy it anyway.
    assert "generate an empty one" in str(refusal.value)


def test_only_the_broken_world_is_named(
    state_dir: Path, write_generation: Callable[..., None]
) -> None:
    write_generation(state_dir / "worlds_local" / "Midgard", 7)
    write_generation(state_dir / "worlds_local" / "Asgard", 3, complete=False)

    broken = inspect(state_dir).inconsistent_worlds
    assert [world.name for world in broken] == ["Asgard"]


def test_an_empty_state_directory_is_new_rather_than_broken(state_dir: Path) -> None:
    """Refusing here would refuse the very first backup, which is the one taken
    before anything is at risk."""
    inspection = inspect(state_dir)
    assert inspection.worlds == ()
    assert inspection.is_consistent
    require_consistent(inspection)


def test_staleness_is_measured_from_the_completion_marker(
    state_dir: Path, write_generation: Callable[..., None]
) -> None:
    """Durability, the check always-on-operation.md ranks above liveness: a
    server can be up and not saving indefinitely, and that is the failure that
    costs a world."""
    world = state_dir / "worlds_local" / "Midgard"
    write_generation(world, 7)

    long_ago = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=9)
    import os

    os.utime(world / "_main.7.ok", (long_ago.timestamp(), long_ago.timestamp()))

    stalest = inspect(state_dir).stalest_age()
    assert stalest is not None
    assert stalest > datetime.timedelta(hours=8)

    # The manifest, not this module, decides what counts as too stale.
    limit = load_manifest(VALHEIM).health.durability.max_stale_seconds
    assert stalest.total_seconds() > limit
