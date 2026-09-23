"""Backup and restore.

ADR 0003's three rules are the ones most likely to be skipped, so they are the
ones tested: copy the whole directory as a unit, verify after copying rather
than before restoring, and never call a backup accepted until it has been
restored.

The round trip at the bottom runs against real restic and a real repository.
That is deliberate rather than thorough-for-its-own-sake: the entire thesis of
ADR 0003 is that an unexercised restore path is a belief, and a test that
mocks the restore is exactly that belief with a green tick on it.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from hostlab.backup import (
    DEFAULT_RETENTION,
    BackupFailed,
    Repository,
    back_up,
    backup_argv,
    forget_argv,
    initialise,
    restore,
    verify,
)
from hostlab.errors import StateInconsistent
from hostlab.manifest import load_manifest

VALHEIM = Path("titles/valheim.yaml")
needs_restic = pytest.mark.skipif(shutil.which("restic") is None, reason="needs restic on PATH")


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    password = tmp_path / "password"
    password.write_text("test-only-password\n")
    return Repository(location=str(tmp_path / "repo"), password_file=password)


@pytest.fixture
def state_dir(tmp_path: Path, write_generation: Callable[..., None]) -> Path:
    state = tmp_path / "data"
    world = state / "worlds_local" / "Midgard"
    write_generation(world, 7)
    # All three permission files, so the round trip exercises every entry the
    # manifest lists rather than a convenient subset.
    (state / "adminlist.txt").write_text("Steam_76561198000000000\n")
    (state / "permittedlist.txt").write_text("")
    (state / "bannedlist.txt").write_text("")
    return state


# ---------------------------------------------------------------------------
# What gets asked of restic
# ---------------------------------------------------------------------------


def test_the_whole_state_directory_is_copied_as_one_unit(
    repository: Repository, state_dir: Path
) -> None:
    """ADR 0003 rule 1. A partial copy gives a world the server cannot open,
    and it answers that by generating an empty one rather than erroring, so
    the fragments saved are then unreachable."""
    argv = backup_argv(repository, state_dir, "valheim")

    paths = [token for token in argv if token.startswith(str(state_dir))]
    assert paths == [str(state_dir)], "the directory goes in whole, not file by file"


def test_everything_the_manifest_claims_belongs_here_is_inside_the_copied_unit(
    state_dir: Path,
) -> None:
    """adminlist.txt and its siblings sit outside the world directory, which is
    exactly why they get forgotten. Copying the state directory as a unit takes
    them along without anyone having to remember.

    Note this checks the ones that EXIST are inside the unit, not that all of
    them exist: a title may create some lazily, and a brand new server
    legitimately has none of them yet."""
    manifest = load_manifest(VALHEIM)
    present = [name for name in manifest.state_dir.contains if (state_dir / name).exists()]

    # All four: the world directory and the three permission files.
    assert sorted(present) == sorted(manifest.state_dir.contains)


def test_retention_outlives_the_time_it_takes_to_notice(repository: Repository) -> None:
    """The game's own backups hold about 38 hours, which does not cover
    "corrupted on Friday, noticed on Monday". ADR 0003 asks retention to exceed
    the time to notice a problem, not the time to have one."""
    argv = forget_argv(repository, "valheim")

    assert "--keep-daily" in argv
    assert argv[argv.index("--keep-daily") + 1] == "7"
    assert "--keep-monthly" in argv
    # Forgetting without pruning leaves the data and only drops the pointer.
    assert "--prune" in argv
    assert all(flag in argv for flag in DEFAULT_RETENTION)


def test_snapshots_are_tagged_so_a_second_title_stays_separate(
    repository: Repository, state_dir: Path
) -> None:
    argv = backup_argv(repository, state_dir, "valheim")
    assert argv[argv.index("--tag") + 1] == "valheim"


def test_a_missing_restic_says_what_is_missing_and_why(
    repository: Repository, state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(BackupFailed, match="not installed"):
        back_up(load_manifest(VALHEIM), state_dir, repository)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_an_inconsistent_state_is_not_copied(
    repository: Repository, tmp_path: Path, write_generation: Callable[..., None]
) -> None:
    """Refusing beats copying something that will not restore, because the
    moment you find out otherwise is the moment you needed it."""
    state = tmp_path / "broken"
    write_generation(state / "worlds_local" / "Midgard", 8, complete=False)

    with pytest.raises(StateInconsistent):
        back_up(load_manifest(VALHEIM), state, repository)


def test_restoring_onto_something_that_exists_is_refused(
    repository: Repository, tmp_path: Path
) -> None:
    """ADR 0003's drill: never restore onto the live world as a test, and never
    leave two servers pointed at one state directory."""
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "already-here").write_text("the live world")

    with pytest.raises(BackupFailed, match="not empty"):
        restore(repository, "latest", occupied)


# ---------------------------------------------------------------------------
# The round trip, against real restic
# ---------------------------------------------------------------------------


@needs_restic
def test_a_backup_can_actually_be_restored(
    repository: Repository, state_dir: Path, tmp_path: Path
) -> None:
    """The whole of ADR 0003 in one test.

    Not a mock. A backup that has only ever been restored by a test double is
    precisely the belief the ADR refuses to accept, and mocking the restore
    would leave the one path that matters unexercised while looking green.
    """
    manifest = load_manifest(VALHEIM)
    initialise(repository)

    back_up(manifest, state_dir, repository)
    verify(repository)

    target = tmp_path / "restored"
    inspection = restore(repository, "latest", target, manifest)

    assert inspection is not None
    assert inspection.is_consistent, "the restored world has no complete generation"

    world = inspection.worlds[0]
    assert world.name == "Midgard"
    newest = world.newest_complete
    assert newest is not None
    assert newest.number == 7


@needs_restic
def test_the_restored_tree_holds_every_declared_file(
    repository: Repository, state_dir: Path, tmp_path: Path
) -> None:
    """A world that loads is not necessarily a world that is whole. The
    manifest's state_dir.contains is the machine-checkable part of that."""
    manifest = load_manifest(VALHEIM)
    initialise(repository)
    back_up(manifest, state_dir, repository)

    target = tmp_path / "restored"
    inspection = restore(repository, "latest", target, manifest)
    assert inspection is not None

    for name in manifest.state_dir.contains:
        if (state_dir / name).exists():
            assert (inspection.root / name).exists(), f"{name} did not come back"


@needs_restic
def test_a_damaged_state_can_be_copied_deliberately(
    repository: Repository, tmp_path: Path, write_generation: Callable[..., None]
) -> None:
    """The one case the consistency check should not win: a state directory
    that is already damaged is the one you most want a copy of before touching
    it. Opt-in, because the usual reason the check is in the way is that it is
    right."""
    state = tmp_path / "damaged"
    write_generation(state / "worlds_local" / "Midgard", 8, complete=False)

    initialise(repository)
    back_up(load_manifest(VALHEIM), state, repository, require_consistency=False)

    restored = restore(repository, "latest", tmp_path / "out", load_manifest(VALHEIM))
    assert restored is not None
    # It came back exactly as damaged as it went in, which is the honest result.
    assert not restored.is_consistent
