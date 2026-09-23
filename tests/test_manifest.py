"""The title contract, tested against the title it was designed around.

`docs/platform-architecture.md` says the validation of the contract is whether
it can express Valheim: "If the contract cannot express the title we are
actually building for, it is wrong." So the first group of tests checks the
real manifest against the documented table, field by field.

The second group checks that the schema refuses manifests that are wrong in
ways which would otherwise validate field by field and still produce a broken
server. Those are the ones worth having, because a schema that only rejects
typos is not earning anything.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Protocol

import pytest

from hostlab.errors import ManifestInvalid
from hostlab.manifest import MustPrecedeConstraint, load_manifest
from hostlab.schema import SCHEMA_PATH, render

VALHEIM = Path("titles/valheim.yaml")


class WriteManifest(Protocol):
    def __call__(self, raw: dict[str, Any], name: str = ...) -> Path: ...


# ---------------------------------------------------------------------------
# Valheim against the contract
# ---------------------------------------------------------------------------


def test_the_shipped_valheim_manifest_loads() -> None:
    manifest = load_manifest(VALHEIM)
    assert manifest.id == "valheim"
    assert manifest.name == "Valheim"


def test_valheim_matches_the_documented_contract_table() -> None:
    """Against "Valheim against the contract" in platform-architecture.md.

    If this fails, either the manifest or that table is wrong, and the two
    disagreeing is precisely the drift the documentation warned about when it
    refused to keep two copies of this description.
    """
    manifest = load_manifest(VALHEIM)

    assert manifest.acquire.method == "steamcmd"
    assert manifest.acquire.app_id == 896660
    assert manifest.acquire.login == "anonymous"
    assert manifest.acquire.validate_files is True

    assert manifest.runtime.platform == "linux/amd64"
    assert manifest.runtime.min_glibc == "2.29"
    assert manifest.runtime.min_glibcxx == "3.4.26"
    assert "libatomic1" in manifest.runtime.libraries

    assert manifest.state_dir.configured_by == "-savedir"
    assert "worlds_local" in manifest.state_dir.contains
    # The three permission files sit outside the world directory and are the
    # ones people forget. They are part of the backup.
    for permission_file in ("adminlist.txt", "permittedlist.txt", "bannedlist.txt"):
        assert permission_file in manifest.state_dir.contains

    assert manifest.stop.signal == "SIGINT"
    assert manifest.stop.grace_seconds >= 120

    assert manifest.health.liveness.port == 2457
    assert manifest.health.durability.kind == "state_advancing"


def test_valheim_declares_both_udp_ports_and_forbids_remapping() -> None:
    manifest = load_manifest(VALHEIM)
    by_number = {port.number: port for port in manifest.ports}

    assert by_number[2456].protocol == "udp"
    assert by_number[2457].protocol == "udp"

    # Valheim advertises its own port to the Steam lobby, so a remapped
    # external port produces a listing nobody can reach.
    assert all(port.remap_allowed is False for port in manifest.ports)

    # Forward the query port even on a private server: the A2S reply is the
    # only proof of the network path ADR 0002 accepts.
    assert by_number[2457].forward is True

    # Crossplay is relayed, so its port needs no forwarding.
    assert by_number[2458].forward is False
    assert by_number[2458].when == "crossplay"

    # The Steamworks TCP port must never be exposed, so it is not declared.
    assert all(port.protocol == "udp" for port in manifest.ports)


def test_the_three_fields_the_evidence_forced_are_present() -> None:
    """ADR 0005 defends config_hazards, state_consistency and an optional
    admin as the three fields a design written from intuition would have
    missed. All three are exercised by Valheim, which is why they exist."""
    manifest = load_manifest(VALHEIM)

    hazards = {hazard.path for hazard in manifest.config_hazards}
    assert "start_server.sh" in hazards

    assert manifest.state_consistency is not None
    assert manifest.state_consistency.complete_marker == "_main.{generation}.ok"

    # Absent because Valheim has none, not because nobody looked.
    assert manifest.admin is None


def test_the_allowlist_semantics_are_declared_not_assumed() -> None:
    """A non-empty permittedlist.txt bans everyone not on it. Naming the file
    without naming that behaviour would withhold the only part that matters."""
    manifest = load_manifest(VALHEIM)
    assert manifest.players is not None
    assert manifest.players.allow_file == "permittedlist.txt"
    assert manifest.players.allow_semantics == "exclusive_allowlist"


def test_preset_is_declared_before_modifier() -> None:
    """Iron Gate: setting a preset overwrites any previous modifiers. Flags
    render in declared order, so this ordering is the configuration, and the
    wrong order fails silently with a world that is not what was asked for."""
    manifest = load_manifest(VALHEIM)
    order = [flag.flag for flag in manifest.config.flags]
    assert order.index("-preset") < order.index("-modifier")

    # And the manifest says so out loud, so a future edit that reorders the
    # list is caught by the platform rather than by a confused player.
    rules = [c for c in manifest.config.constraints if isinstance(c, MustPrecedeConstraint)]
    assert any(rule.flag == "-preset" and rule.before == "-modifier" for rule in rules)


def test_every_dangerous_fact_carries_its_provenance() -> None:
    """Convention 3 of this repository: a claim that can go stale carries its
    source at the point of the claim. sources.md then ranks primary above
    secondary. Both survive into the manifest, and this is what checks it."""
    manifest = load_manifest(VALHEIM)

    assert manifest.state_consistency is not None
    evidences = [
        manifest.stop.evidence,
        manifest.state_consistency.evidence,
        manifest.health.durability.evidence,
        *(hazard.evidence for hazard in manifest.config_hazards),
        *(constraint.evidence for constraint in manifest.config.constraints),
    ]

    for evidence in evidences:
        assert evidence.note.strip(), "evidence with no note explains nothing"
        assert evidence.verified is not None, "an undated claim cannot be re-checked"

    # The four claims sources.md calls highest-risk are the ones no vendor
    # documents. The manifest must not quietly launder them as vendor facts.
    assert manifest.stop.evidence.kind == "community"
    assert manifest.state_consistency.evidence.kind == "community"


# ---------------------------------------------------------------------------
# What the schema refuses
# ---------------------------------------------------------------------------


def test_a_manifest_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "title.yaml"
    path.write_text("- this is a list\n", encoding="utf-8")
    with pytest.raises(ManifestInvalid, match="mapping"):
        load_manifest(path)


def test_invalid_yaml_is_refused_as_yaml_not_as_a_contract_failure(tmp_path: Path) -> None:
    path = tmp_path / "title.yaml"
    path.write_text("id: valheim\n  bad: indentation\n", encoding="utf-8")
    with pytest.raises(ManifestInvalid, match="not valid YAML"):
        load_manifest(path)


@pytest.mark.parametrize("field", ["acquire", "runtime", "config", "state_dir", "stop", "health"])
def test_a_missing_required_field_names_itself(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest, field: str
) -> None:
    """The Required column of the contract table, enforced. The error names the
    field, because ADR 0008 chose this validator for error quality."""
    raw = copy.deepcopy(valheim_raw)
    del raw[field]
    with pytest.raises(ManifestInvalid, match=field):
        load_manifest(write_manifest(raw))


def test_a_port_without_remap_allowed_is_refused(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest
) -> None:
    """It has no default on purpose. Satisfactory cannot remap its standard
    port but can remap its second, so silence here would hide the thing that
    decides whether a configuration is broken."""
    raw = copy.deepcopy(valheim_raw)
    del raw["ports"][0]["remap_allowed"]
    with pytest.raises(ManifestInvalid, match="remap_allowed"):
        load_manifest(write_manifest(raw))


def test_a_duplicated_port_is_refused(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest
) -> None:
    raw = copy.deepcopy(valheim_raw)
    raw["ports"].append(copy.deepcopy(raw["ports"][0]))
    with pytest.raises(ManifestInvalid, match="declared twice"):
        load_manifest(write_manifest(raw))


def test_a_flag_pointing_at_an_unknown_setting_is_refused(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest
) -> None:
    """Field-by-field this manifest is fine. It would render a server missing
    whatever that flag was meant to carry."""
    raw = copy.deepcopy(valheim_raw)
    raw["config"]["flags"][2]["value_from"] = "no_such_setting"
    with pytest.raises(ManifestInvalid, match="no_such_setting"):
        load_manifest(write_manifest(raw))


def test_an_ordering_rule_naming_an_unknown_flag_is_refused(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest
) -> None:
    raw = copy.deepcopy(valheim_raw)
    for constraint in raw["config"]["constraints"]:
        if constraint["kind"] == "must_precede":
            constraint["before"] = "-nonexistent"
    with pytest.raises(ManifestInvalid, match="-nonexistent"):
        load_manifest(write_manifest(raw))


def test_liveness_aimed_at_an_undeclared_port_is_refused(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest
) -> None:
    """Otherwise the check fails forever and reads as an outage rather than as
    a manifest error."""
    raw = copy.deepcopy(valheim_raw)
    raw["health"]["liveness"]["port"] = 9999
    with pytest.raises(ManifestInvalid, match="9999"):
        load_manifest(write_manifest(raw))


def test_durability_without_a_consistency_rule_is_refused(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest
) -> None:
    """Whether state is advancing is unanswerable without knowing what a complete
    save looks like. Accepting this would ship a durability signal that cannot
    be computed, which is worse than none: it would report healthy."""
    raw = copy.deepcopy(valheim_raw)
    del raw["state_consistency"]
    with pytest.raises(ManifestInvalid, match="state_consistency"):
        load_manifest(write_manifest(raw))


def test_a_consistency_pattern_without_a_generation_group_is_refused(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest
) -> None:
    raw = copy.deepcopy(valheim_raw)
    raw["state_consistency"]["generation_pattern"] = r"^_main\.\d+\."
    with pytest.raises(ManifestInvalid, match="generation"):
        load_manifest(write_manifest(raw))


def test_a_marker_template_that_cannot_name_a_generation_is_refused(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest
) -> None:
    raw = copy.deepcopy(valheim_raw)
    raw["state_consistency"]["complete_marker"] = "_main.ok"
    with pytest.raises(ManifestInvalid, match="generation"):
        load_manifest(write_manifest(raw))


def test_an_allow_file_without_its_semantics_is_refused(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest
) -> None:
    raw = copy.deepcopy(valheim_raw)
    del raw["players"]["allow_semantics"]
    with pytest.raises(ManifestInvalid, match="allow_semantics"):
        load_manifest(write_manifest(raw))


def test_an_unknown_field_is_refused_rather_than_ignored(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest
) -> None:
    """A typo that is silently ignored is a setting that silently does nothing,
    and the reader has no way to tell which they have."""
    raw = copy.deepcopy(valheim_raw)
    raw["stat_dir"] = {"path": "/data"}
    with pytest.raises(ManifestInvalid, match="stat_dir"):
        load_manifest(write_manifest(raw))


def test_a_flag_with_both_a_literal_and_a_setting_is_refused(
    valheim_raw: dict[str, Any], write_manifest: WriteManifest
) -> None:
    raw = copy.deepcopy(valheim_raw)
    raw["config"]["flags"][2]["literal"] = "fixed"
    with pytest.raises(ManifestInvalid, match="not both"):
        load_manifest(write_manifest(raw))


# ---------------------------------------------------------------------------
# The generated schema
# ---------------------------------------------------------------------------


def test_the_committed_schema_matches_the_models() -> None:
    """ADR 0008 makes the models the source of truth and the schema generated.
    Committing a generated file is only safe if drift is caught, otherwise
    "generated" quietly becomes "stale" and outside tooling checks manifests
    against a contract this package no longer has."""
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render(), (
        "titles/schema.json is out of date. Run: make schema"
    )
