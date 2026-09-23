"""The instance file, the compose file, and the command line that joins them.

The property that matters most here is that **the generated compose file
contains no secrets**, because a generated file is exactly the kind that gets
committed without being read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from hostlab.cli import main
from hostlab.compose import compose_document, render_compose
from hostlab.errors import ConfigurationRefused
from hostlab.manifest import load_manifest
from hostlab.render import render
from hostlab.settings import Instance, load_instance

VALHEIM = Path("titles/valheim.yaml")
INSTANCE = Path("deploy/valheim/valheim.yaml")
PASSWORD = "ravenstone"


@pytest.fixture(autouse=True)
def _password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VALHEIM_PASSWORD", PASSWORD)


def loaded() -> Instance:
    return load_instance(INSTANCE)


def composed() -> dict[str, Any]:
    instance = loaded()
    spec = render(load_manifest(VALHEIM), instance.settings, instance.deployment)
    return compose_document(spec, instance.placeholders)


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def test_the_generated_compose_file_contains_no_secret() -> None:
    """The whole point of the placeholder mechanism. A generated file is the
    kind that gets committed without being read, so the secret must never be
    in it in the first place rather than be caught later by a reviewer."""
    instance = loaded()
    spec = render(load_manifest(VALHEIM), instance.settings, instance.deployment)
    document = render_compose(spec, instance.placeholders)

    assert PASSWORD not in document
    assert "${VALHEIM_PASSWORD}" in document


def test_the_placeholder_survives_into_the_command() -> None:
    command = composed()["services"]["valheim"]["command"]
    assert command[command.index("-password") + 1] == "${VALHEIM_PASSWORD}"


def test_a_missing_secret_is_refused_with_where_to_get_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failing here beats failing at `docker compose up` with an empty
    password, which Valheim answers by exiting."""
    monkeypatch.delenv("VALHEIM_PASSWORD")
    with pytest.raises(ConfigurationRefused) as refusal:
        load_instance(INSTANCE)

    assert "VALHEIM_PASSWORD" in str(refusal.value)
    assert "deploy/.env" in str(refusal.value)


# ---------------------------------------------------------------------------
# The compose file itself
# ---------------------------------------------------------------------------


def test_every_published_port_carries_udp() -> None:
    """ADR 0004 consequence 1, at the last place it could still go wrong."""
    ports = composed()["services"]["valheim"]["ports"]
    assert ports == ["2456:2456/udp", "2457:2457/udp"]


def test_the_stop_signal_and_grace_period_are_written_explicitly() -> None:
    """Compose inherits Docker's defaults otherwise: SIGTERM after 10 seconds,
    which is the wrong signal and a timeout shorter than a large world takes
    to write."""
    service = composed()["services"]["valheim"]
    assert service["stop_signal"] == "SIGINT"
    assert service["stop_grace_period"] == "120s"


def test_resource_limits_use_keys_that_work_outside_swarm() -> None:
    """deploy.resources.limits is honoured under Swarm, and this is a single
    machine that is also somebody's gaming PC. A limit that silently does
    nothing is worse than no limit, because it is believed."""
    service = composed()["services"]["valheim"]
    assert service["mem_limit"] == "6g"
    assert service["cpus"] == 2.0
    assert "deploy" not in service


def test_the_named_state_volume_is_declared() -> None:
    document = composed()
    assert "valheim-data" in document["volumes"]
    assert document["services"]["valheim"]["volumes"] == ["valheim-data:/data"]


def test_no_healthcheck_is_emitted() -> None:
    """Deliberate. The manifest's liveness check is an A2S query, and putting a
    query client in the game image would couple the container's health to a
    protocol that breaks against game updates. ADR 0006 consequence 5 keeps the
    state reader separate from the thing it watches."""
    assert "healthcheck" not in composed()["services"]["valheim"]


def test_the_generated_file_says_not_to_edit_it() -> None:
    """Editing a generated file means the next regeneration silently reverts
    you, which is the same trap as putting configuration in start_server.sh."""
    instance = loaded()
    spec = render(load_manifest(VALHEIM), instance.settings, instance.deployment)
    assert "Do not edit" in render_compose(spec, instance.placeholders)


def test_the_generated_file_is_valid_yaml() -> None:
    instance = loaded()
    spec = render(load_manifest(VALHEIM), instance.settings, instance.deployment)
    assert yaml.safe_load(render_compose(spec, instance.placeholders))["services"]


# ---------------------------------------------------------------------------
# The instance file
# ---------------------------------------------------------------------------


def test_the_shipped_instance_file_loads() -> None:
    instance = loaded()
    assert instance.deployment.container_name == "valheim"
    assert instance.settings["world_name"] == "Midgard"


def test_the_shipped_instance_does_not_run_a_moving_image_tag() -> None:
    """ADR 0004 consequence 5: an image tag is the rollback mechanism, and
    `latest` is a tag that moves underneath you."""
    assert not loaded().deployment.image.endswith(":latest")


def test_an_unknown_deployment_key_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "instance.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "deployment": {
                    "image": "i",
                    "container_name": "c",
                    "state_volume": "v",
                    "menory": "6g",
                },
                "settings": {},
            }
        )
    )
    with pytest.raises(ConfigurationRefused, match="menory"):
        load_instance(path)


def test_an_instance_missing_a_half_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "instance.yaml"
    path.write_text(yaml.safe_dump({"settings": {}}))
    with pytest.raises(ConfigurationRefused, match="deployment"):
        load_instance(path)


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


def test_validate_checks_the_manifest_alone(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "valheim"]) == 0
    out = capsys.readouterr().out
    assert "satisfies the title contract" in out
    # Valheim has no remote administration, and saying so out loud is the
    # point: it is a finding rather than a gap.
    assert "admin    none" in out


def test_plan_writes_nothing_and_redacts(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["plan", "valheim", "--instance", str(INSTANCE)]) == 0
    out = capsys.readouterr().out
    assert "accepted" in out
    assert PASSWORD not in out


def test_a_refusal_exits_non_zero_without_a_traceback(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal is a designed outcome. A traceback would bury the explanation
    it exists to carry."""
    monkeypatch.setenv("VALHEIM_PASSWORD", "abc")
    assert main(["plan", "valheim", "--instance", str(INSTANCE)]) == 2

    err = capsys.readouterr().err
    assert "refused:" in err
    assert "at least 5" in err
    assert "Traceback" not in err


def test_an_unknown_title_lists_what_there_is(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "minecraft"]) == 2
    assert "valheim" in capsys.readouterr().err


def test_compose_refuses_before_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`compose` runs every refusal `plan` does, so it cannot produce a file
    for a configuration that would have been rejected."""
    monkeypatch.setenv("VALHEIM_PASSWORD", "abc")
    out = tmp_path / "compose.yaml"

    assert main(["compose", "valheim", "--instance", str(INSTANCE), "--out", str(out)]) == 2
    assert not out.exists()


def test_compose_writes_a_file_docker_would_accept(tmp_path: Path) -> None:
    out = tmp_path / "compose.yaml"
    assert main(["compose", "valheim", "--instance", str(INSTANCE), "--out", str(out)]) == 0

    document = yaml.safe_load(out.read_text())
    assert document["services"]["valheim"]["stop_signal"] == "SIGINT"
    assert PASSWORD not in out.read_text()
