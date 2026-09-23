"""The permission logic from the Valheim image, tested as the regression it is.

valheim-server-docker issue #802 is the most specific failure in this project's
research: after 1.0 made each world a directory, a permission fix applied 0644
to everything under worlds_local/, directories included. A directory without
the execute bit cannot have entries created in it, so every autosave failed
silently while the container reported healthy.

ADR 0004 consequence 3 turns that into a standing obligation: "any permissions
handling must distinguish files from directories". This is what holds us to it.
The script is deliberately separate from the entrypoint so it can be tested
here, without Docker and without the game, because this is exactly the kind of
logic that is never exercised until the day it destroys something.
"""

from __future__ import annotations

import stat
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

SCRIPT = Path("images/valheim/fix-permissions.sh")


def mode_of(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def world_tree(tmp_path: Path) -> Iterator[Path]:
    """A save directory shaped like Valheim's, in the broken state from #802."""
    state = tmp_path / "data"
    world = state / "worlds_local" / "Midgard"
    world.mkdir(parents=True)

    (world / "_main.7.fwl2").write_bytes(b"metadata")
    (world / "_main.7.db2").write_bytes(b"world data")
    (world / "00_00__0_1.chunk").write_bytes(b"terrain")
    (world / "_main.7.ok").write_bytes(b"")
    (state / "adminlist.txt").write_text("Steam_76561198000000000\n")

    # One file left too open, so the normalising pass has something to do.
    # Set before the directories are broken, because afterwards it could not
    # be reached to set it.
    (world / "00_00__0_1.chunk").chmod(0o777)

    # The bug: 0644 applied indiscriminately, so the per-world directory lost
    # its execute bit and nothing could be written into it any more.
    #
    # Deepest first. Stripping a parent's execute bit makes its children
    # unreachable, which is the same property that broke the autosaves, and it
    # would break this fixture in the other order too.
    for path in (world, state / "worlds_local", state):
        path.chmod(0o644)

    yield state

    # A test that fails partway leaves a tree pytest cannot delete. Restoring
    # traversal here keeps a real failure legible instead of burying it under
    # cleanup errors.
    subprocess.run(["/bin/chmod", "-R", "u+rwX", str(tmp_path)], check=False)


def run_script(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", str(SCRIPT), str(target)],
        capture_output=True,
        text=True,
        check=True,
    )


def test_directories_regain_the_execute_bit(world_tree: Path) -> None:
    """The specific #802 failure. Without this bit, every autosave fails and
    the container still reports healthy."""
    run_script(world_tree)

    world = world_tree / "worlds_local" / "Midgard"
    assert mode_of(world) == 0o755
    assert mode_of(world_tree / "worlds_local") == 0o755
    assert mode_of(world_tree) == 0o755


def test_the_directory_is_actually_writable_afterwards(world_tree: Path) -> None:
    """Asserting the mode is a proxy. This asserts the thing the mode is for:
    that the server could write the next generation."""
    run_script(world_tree)

    new_generation = world_tree / "worlds_local" / "Midgard" / "_main.8.db2"
    new_generation.write_bytes(b"the next save")
    assert new_generation.exists()


def test_files_do_not_get_the_execute_bit(world_tree: Path) -> None:
    """The opposite error, and the reason a blanket chmod 0755 is not the fix.
    A world save is data; making it executable is sloppy rather than dangerous,
    but the point is that the script reasons about type rather than guessing."""
    run_script(world_tree)

    for name in ("_main.7.fwl2", "_main.7.db2", "00_00__0_1.chunk", "_main.7.ok"):
        path = world_tree / "worlds_local" / "Midgard" / name
        assert mode_of(path) == 0o644
        assert not mode_of(path) & stat.S_IXUSR


def test_the_permission_files_outside_the_world_are_fixed_too(world_tree: Path) -> None:
    """adminlist.txt and its siblings live in the save directory root rather
    than inside a world, which is why they are easy to forget."""
    run_script(world_tree)
    assert mode_of(world_tree / "adminlist.txt") == 0o644


def test_an_over_permissive_file_is_brought_back_down(world_tree: Path) -> None:
    """The repair pass only adds permissions, so it cannot fix a file that is
    too open. That is why there is a second, normalising pass: a world save
    should not stay world-writable because something once made it so."""
    run_script(world_tree)

    loose = world_tree / "worlds_local" / "Midgard" / "00_00__0_1.chunk"
    assert mode_of(loose) == 0o644


def test_repair_works_when_the_root_itself_cannot_be_traversed(world_tree: Path) -> None:
    """The case that matters, and the one that caught a bug in this script.

    find reads a directory's contents before running any action on it, so
    `find -type d -exec chmod` exits with "Permission denied" and repairs
    nothing: it cannot be the tool that fixes traversal. chmod -R can, because
    it applies the mode and then descends. The fixture starts with every level
    at 0644, root included, which is the state issue #802 produced."""
    assert not mode_of(world_tree) & stat.S_IXUSR, "fixture should start unusable"

    run_script(world_tree)

    for path in (
        world_tree,
        world_tree / "worlds_local",
        world_tree / "worlds_local" / "Midgard",
    ):
        assert mode_of(path) & stat.S_IXUSR, f"{path} is still not traversable"


def test_a_missing_directory_is_not_an_error(tmp_path: Path) -> None:
    """First start, before any volume content exists. Failing here would mean
    a brand new server never starts."""
    result = run_script(tmp_path / "not-yet")
    assert result.returncode == 0
    assert "nothing to do" in result.stdout


def test_the_script_is_run_before_the_server_starts() -> None:
    """The ordering is the whole point: fixing permissions after the server has
    begun writing is fixing them too late."""
    entrypoint = Path("images/valheim/entrypoint.sh").read_text(encoding="utf-8")
    assert entrypoint.index("fix-permissions.sh") < entrypoint.index("exec setpriv")


def test_the_server_is_exec_ed_so_signals_reach_it() -> None:
    """Valheim saves cleanly on SIGINT and loses up to save_interval_seconds on
    SIGKILL. A shell that forwards signals is a shell that can fail to, so the
    entrypoint must exec rather than spawn."""
    entrypoint = Path("images/valheim/entrypoint.sh").read_text(encoding="utf-8")
    assert "exec setpriv" in entrypoint
    assert "valheim_server.x86_64" in entrypoint


def test_the_image_overrides_dockers_stop_signal() -> None:
    """Docker's default, SIGTERM, is unreliable for this server. The renderer
    passes --stop-signal explicitly, but an image started by hand should still
    stop correctly."""
    dockerfile = Path("images/valheim/Dockerfile").read_text(encoding="utf-8")
    assert "STOPSIGNAL SIGINT" in dockerfile


def test_the_image_exposes_udp_only() -> None:
    dockerfile = Path("images/valheim/Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 2456/udp 2457/udp" in dockerfile
    assert "EXPOSE 2456\n" not in dockerfile
