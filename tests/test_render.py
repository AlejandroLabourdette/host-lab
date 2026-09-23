"""Every test here corresponds to a failure that does not announce itself.

That is the selection rule. A configuration error which produces an immediate,
legible error needs no validator; these are the ones that produce a server
which starts, looks correct, and is wrong.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from hostlab.errors import ConfigurationRefused
from hostlab.manifest import load_manifest
from hostlab.render import Deployment, RunSpec, render, resolve_settings

VALHEIM = Path("titles/valheim.yaml")

GOOD_SETTINGS: dict[str, Any] = {
    "server_name": "Midgard",
    "world_name": "Midgard",
    "password": "ravenstone",
}


def deployment(**overrides: Any) -> Deployment:
    base: dict[str, Any] = {
        "image": "hostlab/valheim:1.0.15",
        "container_name": "valheim",
        "state_volume": "valheim-data",
    }
    return Deployment(**{**base, **overrides})


def valheim_spec(**settings: Any) -> RunSpec:
    return render(load_manifest(VALHEIM), {**GOOD_SETTINGS, **settings}, deployment())


# ---------------------------------------------------------------------------
# The /udp footgun
# ---------------------------------------------------------------------------


def test_every_published_port_carries_its_protocol() -> None:
    """ADR 0004 consequence 1. Publishing 2456:2456 without /udp publishes TCP,
    and produces a server that looks correct and is unreachable. The protocol
    is never defaulted, so there is no path through this code that omits it."""
    spec = valheim_spec()
    published = [port.published() for port in spec.ports]

    assert published == ["2456:2456/udp", "2457:2457/udp"]
    assert all("/" in entry for entry in published)


def test_the_run_command_publishes_udp_not_tcp() -> None:
    args = valheim_spec().docker_run_args()
    assert "2456:2456/udp" in args
    assert "2456:2456" not in args


# ---------------------------------------------------------------------------
# Remapping
# ---------------------------------------------------------------------------


def test_remapping_a_port_that_forbids_it_is_refused() -> None:
    """Valheim advertises its own port to the Steam lobby, so a remapped
    external port yields a listing that advertises a port nobody can reach.
    Nothing errors at the time; the server appears in the browser and refuses
    every connection."""
    with pytest.raises(ConfigurationRefused) as refusal:
        render(
            load_manifest(VALHEIM),
            GOOD_SETTINGS,
            deployment(port_overrides={2456: 2556}),
        )

    message = str(refusal.value)
    assert "2556" in message
    # The refusal must give the reason, not the symptom: an operator who only
    # reads "may not be remapped" tends to conclude the rule is superstition.
    assert "advertises its own port to the Steam lobby" in message


def test_mapping_a_port_to_itself_is_not_a_remap() -> None:
    spec = render(load_manifest(VALHEIM), GOOD_SETTINGS, deployment(port_overrides={2456: 2456}))
    assert spec.ports[0].published() == "2456:2456/udp"


def test_a_remap_of_a_port_that_is_not_published_is_not_refused() -> None:
    """2458 belongs to crossplay. With crossplay off it is not published, so
    refusing an override for it would be noise rather than protection."""
    spec = render(load_manifest(VALHEIM), GOOD_SETTINGS, deployment(port_overrides={2458: 2999}))
    assert [port.container for port in spec.ports] == [2456, 2457]


def test_crossplay_publishes_its_port_and_plain_steam_does_not() -> None:
    assert [p.container for p in valheim_spec().ports] == [2456, 2457]
    assert [p.container for p in valheim_spec(crossplay=True).ports] == [2456, 2457, 2458]


# ---------------------------------------------------------------------------
# Graceful stop
# ---------------------------------------------------------------------------


def test_stop_comes_from_the_manifest_and_never_from_dockers_defaults() -> None:
    """Docker sends SIGTERM and waits 10 seconds. For Valheim that is the wrong
    signal and a timeout shorter than a large world takes to write, and the
    cost of getting it wrong is up to save_interval_seconds of play."""
    spec = valheim_spec()
    assert spec.stop_signal == "SIGINT"
    assert spec.stop_grace_seconds == 120

    args = spec.docker_run_args()
    assert args[args.index("--stop-signal") + 1] == "SIGINT"
    assert args[args.index("--stop-timeout") + 1] == "120"


# ---------------------------------------------------------------------------
# The password rules, which present as a server that will not start
# ---------------------------------------------------------------------------


def test_a_short_password_is_refused_with_the_reason() -> None:
    with pytest.raises(ConfigurationRefused) as refusal:
        valheim_spec(password="abc")
    assert "at least 5" in str(refusal.value)


def test_a_password_inside_the_world_name_is_refused() -> None:
    """The documented case: a world called Vikings with password viking logs
    "Error bad password:" and the server exits. So it does not look like a
    password problem, it looks like a server that will not start, and it is the
    most common first-run failure."""
    with pytest.raises(ConfigurationRefused) as refusal:
        valheim_spec(world_name="Vikings", password="viking")

    assert "world_name" in str(refusal.value)
    assert "Error bad password" in str(refusal.value)


def test_a_password_inside_the_server_name_is_refused() -> None:
    with pytest.raises(ConfigurationRefused) as refusal:
        valheim_spec(server_name="RavenstoneKeep", password="ravenstone")
    assert "server_name" in str(refusal.value)


def test_the_substring_check_ignores_case() -> None:
    """The comparison is case-insensitive, so matching case is not an escape."""
    with pytest.raises(ConfigurationRefused):
        valheim_spec(world_name="VIKINGS", password="viking")


def test_a_password_that_merely_shares_letters_is_allowed() -> None:
    """The rule is substring, not similarity. Over-refusing would be its own
    failure: an operator who cannot tell why a valid password is rejected."""
    spec = valheim_spec(world_name="Midgard", password="ravenstone")
    assert "-password" in spec.command


# ---------------------------------------------------------------------------
# Flag ordering, which fails silently
# ---------------------------------------------------------------------------


def test_preset_renders_before_modifier() -> None:
    command = valheim_spec(preset="hard", modifiers=["raids none"]).command
    assert command.index("-preset") < command.index("-modifier")


def test_a_manifest_that_renders_preset_after_modifier_is_refused(
    valheim_raw: dict[str, Any], write_manifest: Callable[..., Path]
) -> None:
    """Checked against the rendered command rather than the declaration, so a
    rendering bug cannot pass a check on the manifest and still produce the
    silently wrong world. Iron Gate: a preset overwrites previous modifiers,
    and nothing warns you."""
    raw = copy.deepcopy(valheim_raw)
    flags = raw["config"]["flags"]
    preset = next(i for i, f in enumerate(flags) if f["flag"] == "-preset")
    modifier = next(i for i, f in enumerate(flags) if f["flag"] == "-modifier")
    flags[preset], flags[modifier] = flags[modifier], flags[preset]

    manifest = load_manifest(write_manifest(raw))
    with pytest.raises(ConfigurationRefused) as refusal:
        render(
            manifest,
            {**GOOD_SETTINGS, "preset": "hard", "modifiers": ["raids none"]},
            deployment(),
        )

    assert "overwrite" in str(refusal.value).lower()


def test_the_ordering_rule_is_quiet_when_only_one_flag_is_present() -> None:
    """A preset with no modifiers cannot discard anything."""
    assert "-modifier" not in valheim_spec(preset="hard").command


# ---------------------------------------------------------------------------
# Rendering values
# ---------------------------------------------------------------------------


def test_an_unset_optional_setting_emits_no_flag() -> None:
    """Emitting a bare -preset, or -preset with an empty string, is how a
    server ends up refusing to start over a setting nobody chose."""
    command = valheim_spec().command
    assert "-preset" not in command
    assert "" not in command


def test_a_repeated_flag_emits_once_per_item_and_splits_its_tokens() -> None:
    """Valheim's -modifier takes a name and a value, so a list item may carry
    more than one token. The renderer splits rather than knowing about
    modifiers, which keeps the rule general."""
    command = valheim_spec(modifiers=["raids none", "combat hard"]).command
    joined = " ".join(command)
    assert "-modifier raids none" in joined
    assert "-modifier combat hard" in joined
    assert command.count("-modifier") == 2


def test_a_bare_flag_renders_alone() -> None:
    command = valheim_spec().command
    assert command[:2] == ["-nographics", "-batchmode"]


def test_a_conditional_bare_flag_appears_only_when_enabled() -> None:
    assert "-crossplay" not in valheim_spec().command
    assert "-crossplay" in valheim_spec(crossplay=True).command


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def test_the_password_is_redacted_for_logs_but_present_in_the_command() -> None:
    """Valheim is flags-only, so the password is on the command line and
    visible to anything that can read the process table. That is the title's
    constraint. Not putting it in our own logs and status messages is ours."""
    spec = valheim_spec(password="ravenstone")

    assert "ravenstone" in spec.command
    assert "ravenstone" not in spec.redacted_command()
    assert "********" in spec.redacted_command()
    # Redaction must not lose the flag it belonged to.
    assert "-password" in spec.redacted_command()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_an_unknown_setting_is_refused_rather_than_ignored() -> None:
    with pytest.raises(ConfigurationRefused) as refusal:
        valheim_spec(wrold_name="Midgard")
    assert "wrold_name" in str(refusal.value)


def test_a_missing_required_setting_is_refused_with_its_description() -> None:
    with pytest.raises(ConfigurationRefused) as refusal:
        render(load_manifest(VALHEIM), {"server_name": "M", "world_name": "M"}, deployment())
    assert "password" in str(refusal.value)


def test_a_wrongly_typed_setting_is_refused() -> None:
    with pytest.raises(ConfigurationRefused, match="port"):
        valheim_spec(port="2456")


def test_a_boolean_is_not_accepted_where_an_int_is_declared() -> None:
    """bool subclasses int in Python, so True would otherwise pass as a port
    number and render as -port 1."""
    with pytest.raises(ConfigurationRefused, match="port"):
        valheim_spec(port=True)


def test_declared_defaults_are_applied() -> None:
    values = resolve_settings(load_manifest(VALHEIM), GOOD_SETTINGS)
    assert values["port"] == 2456
    assert values["save_interval_seconds"] == 1800
    assert values["savedir"] == "/data"


# ---------------------------------------------------------------------------
# Config hazards
# ---------------------------------------------------------------------------


def test_state_inside_a_config_hazard_is_refused(
    valheim_raw: dict[str, Any], write_manifest: Callable[..., Path]
) -> None:
    """Nothing the platform writes may live where an update will overwrite it.
    For a flags-only title the set of files the platform writes is empty, which
    is exactly how the start_server.sh trap is avoided; the state directory is
    the one path that still has to be checked."""
    raw = copy.deepcopy(valheim_raw)
    raw["config_hazards"][0]["path"] = "/data"

    manifest = load_manifest(write_manifest(raw))
    with pytest.raises(ConfigurationRefused) as refusal:
        render(manifest, GOOD_SETTINGS, deployment())

    assert "config hazard" in str(refusal.value)
    assert "destroyed by the act of patching" in str(refusal.value)


def test_valheim_puts_no_configuration_in_a_hazard_path() -> None:
    """The positive case: the shipped manifest renders without refusal, and its
    configuration is the container's command rather than a file on disk."""
    spec = valheim_spec()
    assert spec.command
    assert all(volume.target == "/data" for volume in spec.volumes)
