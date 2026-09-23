"""The boundary ADR 0010 exists to create, asserted rather than believed.

ADR 0006 consequence 5 says the state reader has no authority. Mounting the
Docker socket into the reader's container would make that false: the socket is
not an interface with permissions, it is the whole API, and a container holding
it can stop, delete or create anything on the host.

ADR 0010 puts a read-only proxy in between, so a destructive request is not
declined by our code, it is **not reachable**. That is the difference between a
rule and a boundary, and the difference is worth a test: a security property
that has only ever been read about in documentation is one nobody has checked.

These run against a real proxy, because the thing being tested is another
program's refusal.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

PROXY_IMAGE = "tecnativa/docker-socket-proxy:0.3.0"
CLIENT_IMAGE = "docker:28-cli"


def docker(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=300
    )


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return docker("info").returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(not docker_available(), reason="needs a running Docker daemon"),
]


@dataclass(frozen=True)
class Proxied:
    """A proxy configured as the platform configures it, and a target to aim at."""

    network: str
    proxy: str
    target: str

    def run(self, script: str) -> subprocess.CompletedProcess[str]:
        """Run a docker command that can only reach the daemon through the proxy."""
        return docker(
            "run",
            "--rm",
            "--network",
            self.network,
            "--env",
            f"DOCKER_HOST=tcp://{self.proxy}:2375",
            CLIENT_IMAGE,
            "sh",
            "-c",
            script,
        )

    def refused(self, script: str) -> None:
        """Assert the proxy refused, rather than our code declining."""
        result = self.run(script)
        assert result.returncode != 0, f"{script!r} succeeded, and it must not"
        assert "403" in result.stdout + result.stderr, (
            f"{script!r} failed, but not with a refusal from the proxy. If this "
            "ever stops being a 403, the reader has authority and ADR 0006 "
            f"consequence 5 is no longer true. Got: {result.stderr.strip()[:200]}"
        )


@pytest.fixture(scope="module")
def proxied() -> Iterator[Proxied]:
    suffix = str(time.monotonic_ns())
    network = f"hostlab-boundary-{suffix}"
    proxy = f"hostlab-proxy-{suffix}"
    target = f"hostlab-target-{suffix}"

    docker("network", "create", network, check=True)
    docker(
        "run",
        "--detach",
        "--name",
        target,
        "--network",
        network,
        "alpine",
        "sleep",
        "600",
        check=True,
    )
    # Exactly the configuration in deploy/platform/compose.yaml. A test against
    # a different configuration would prove nothing about what is deployed.
    docker(
        "run",
        "--detach",
        "--name",
        proxy,
        "--network",
        network,
        "--env",
        "CONTAINERS=1",
        "--env",
        "POST=0",
        "--volume",
        "/var/run/docker.sock:/var/run/docker.sock:ro",
        PROXY_IMAGE,
        check=True,
    )

    proxied = Proxied(network=network, proxy=proxy, target=target)

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        probe = proxied.run("docker ps --format '{{.Names}}'")
        if probe.returncode == 0 and target in probe.stdout:
            break
        time.sleep(0.5)
    else:
        pytest.fail("the proxy never became usable")

    try:
        yield proxied
    finally:
        docker("rm", "--force", proxy, target)
        docker("network", "rm", network)


# ---------------------------------------------------------------------------
# What must still work
# ---------------------------------------------------------------------------


def test_inspecting_a_container_works(proxied: Proxied) -> None:
    """The reader needs this for running state, uptime and the restart count."""
    result = proxied.run(f"docker inspect {proxied.target} --format '{{{{.State.Running}}}}'")

    assert result.returncode == 0
    assert "true" in result.stdout


def test_reading_logs_works(proxied: Proxied) -> None:
    """The reader needs this for the crossplay join code, which under ADR 0009
    is the only way anyone connects at all."""
    assert proxied.run(f"docker logs {proxied.target}").returncode == 0


# ---------------------------------------------------------------------------
# What must not be reachable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "operation",
    ["stop", "kill", "restart"],
)
def test_destructive_operations_are_refused(proxied: Proxied, operation: str) -> None:
    proxied.refused(f"docker {operation} {proxied.target}")


def test_removing_a_container_is_refused(proxied: Proxied) -> None:
    proxied.refused(f"docker rm --force {proxied.target}")


def test_creating_a_container_is_refused(proxied: Proxied) -> None:
    """The one that matters most. A container that can create containers can
    mount any host path into a new one and read or write anything, which makes
    every other restriction here cosmetic."""
    proxied.refused("docker run --rm alpine true")


def test_the_target_survived_every_attempt(proxied: Proxied) -> None:
    """The refusals above are only meaningful if nothing got through."""
    running = docker("inspect", proxied.target, "--format", "{{.State.Running}}").stdout.strip()
    assert running == "true"
