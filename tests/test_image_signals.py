"""Does the container plumbing actually deliver SIGINT to the server?

`sources.md` ranks SIGINT as the graceful stop signal among its highest-risk
claims, and says to verify it rather than assume it: getting it wrong loses up
to `save_interval_seconds` of play on every single stop, quietly, for as long
as nobody checks.

The claim splits into two halves and only one of them needs the game:

1. **Does the plumbing deliver SIGINT to the process?** Ours. Tested here.
2. **Does the server save cleanly when it gets one?** Iron Gate's. Tested on
   the host, by stopping a real server and checking for a fresh `.ok` marker.

Half (1) is where our bugs would be, and all three are silent: an entrypoint
that spawns rather than execs, a `STOPSIGNAL` left at Docker's SIGTERM
default, or a privilege drop that loses the signal on the way down. None of
them fails visibly. The server just stops without saving.

These tests run against a stub image that uses the **real** entrypoint and
permission scripts with a stand-in for the game binary, because the real
server is an x86-64 build that cannot be fetched or run on every machine that
needs to run this suite.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

IMAGE = "hostlab-stub:pytest"
DOCKERFILE = "tests/fixtures/stub-image/Dockerfile"
READY = "stub: ready"


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=300
    )


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return docker("info", check=False).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(not docker_available(), reason="needs a running Docker daemon"),
]


@dataclass(frozen=True)
class StopResult:
    """What happened when the container was stopped the way the platform stops it."""

    logs: str
    exit_code: int
    elapsed: float
    volume: str


@pytest.fixture(scope="module")
def stub_image() -> str:
    """Build from the repository root, so the real scripts are used.

    Building against copies would test the copies, and the copies are exactly
    what drifts.
    """
    docker("build", "--quiet", "--file", DOCKERFILE, "--tag", IMAGE, ".")
    return IMAGE


@pytest.fixture
def stopped_container(stub_image: str) -> Iterator[StopResult]:
    """Run the stub, stop it the way the platform would, report what happened."""
    name = f"hostlab-stub-{time.monotonic_ns()}"
    volume = f"{name}-data"

    docker("volume", "create", volume)
    docker(
        "run",
        "--detach",
        "--name",
        name,
        "--volume",
        f"{volume}:/data",
        stub_image,
        "-name",
        "Midgard",
        "-world",
        "Midgard",
    )

    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if READY in docker("logs", name, check=False).stdout:
                break
            time.sleep(0.2)
        else:
            pytest.fail(f"stub never became ready:\n{docker('logs', name, check=False).stdout}")

        started = time.monotonic()
        # Plain `docker stop`, with no --signal: the point is that the image's
        # own STOPSIGNAL is correct, so a container started by hand or by
        # compose stops properly without anyone remembering to pass a flag.
        docker("stop", name)
        elapsed = time.monotonic() - started

        inspected = json.loads(docker("inspect", name).stdout)[0]
        finished = docker("logs", name, check=False)
        yield StopResult(
            logs=finished.stdout + finished.stderr,
            exit_code=int(inspected["State"]["ExitCode"]),
            elapsed=elapsed,
            volume=volume,
        )
    finally:
        docker("rm", "--force", name, check=False)
        docker("volume", "rm", "--force", volume, check=False)


def test_docker_stop_delivers_sigint_not_sigterm(stopped_container: StopResult) -> None:
    """Docker's default is SIGTERM, which Valheim handles unreliably. The image
    sets STOPSIGNAL SIGINT and the renderer passes --stop-signal as well."""
    logs = stopped_container.logs
    assert "received SIGINT" in logs
    assert "received SIGTERM" not in logs


def test_the_server_is_pid_1_so_the_signal_reaches_it_directly(
    stopped_container: StopResult,
) -> None:
    """A wrapper shell that forwards signals is a wrapper that can fail to."""
    assert "pid=1" in stopped_container.logs


def test_privilege_is_dropped_before_the_server_starts(
    stopped_container: StopResult,
) -> None:
    assert "uid=10000 gid=10000" in stopped_container.logs


def test_the_stop_is_graceful_rather_than_a_timeout_and_kill(
    stopped_container: StopResult,
) -> None:
    """A stop that runs out of time and escalates to SIGKILL is a data-loss
    event, and it looks identical to a clean stop from the outside. Exiting 0
    well inside the timeout is what distinguishes them: the stub exits 1 on
    SIGTERM precisely so the wrong path cannot pass."""
    assert stopped_container.exit_code == 0
    assert stopped_container.elapsed < 10


def test_the_unprivileged_user_can_write_to_the_state_volume(
    stopped_container: StopResult, stub_image: str
) -> None:
    """The #802 failure mode: a container that looks healthy while every write
    into the world directory fails. The stub writes a marker from its SIGINT
    handler, which is where the real server writes its save."""
    volume = stopped_container.volume
    listing = docker(
        "run",
        "--rm",
        "--volume",
        f"{volume}:/data",
        "--entrypoint",
        "sh",
        stub_image,
        "-c",
        "ls -l /data && cat /data/stub-shutdown.marker",
    ).stdout

    assert "clean shutdown" in listing
    assert "valheim" in listing, "the marker should be owned by the unprivileged user"
