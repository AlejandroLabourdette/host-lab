"""The title contract of ADR 0005, as a schema.

`docs/platform-architecture.md` sets out what a title must declare to join the
platform, and says it is "written as a shape, not a schema, because committing
to a syntax is an implementation decision that has not been made yet". ADR 0008
made it. This module is that shape, made checkable.

Three properties are deliberate and worth stating, because each one is a thing
a schema written from intuition would have got wrong.

**Nothing here is per-title code.** ADR 0005 rejected a plugin interface, so
Valheim's oddities are declared, not implemented. Its password rules and the
ordering of `-preset` against `-modifier` are `constraints` entries in the
manifest, which is why adding a second title does not touch this package.

**The dangerous facts carry their provenance.** This repository's third writing
convention is that every claim which can go stale carries its source and a date
at the point of the claim. YAML comments would satisfy a reader but not the
platform, and `sources.md` is emphatic that the most expensive claims here are
exactly the ones no vendor documents: the save format, SIGINT as the graceful
stop, the port protocols, the password rules. So `Evidence` is data, it says
whether a fact is vendor-documented or merely observed, and a refusal can
repeat it back to whoever hit it.

**Optionality is meaningful.** `admin` is optional because Valheim has none,
and `remap_allowed` is required with no default because Satisfactory cannot
remap its standard port. An absent `admin` is a finding; an absent
`remap_allowed` is an omission. The schema distinguishes them.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from hostlab.errors import ManifestInvalid

# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


class Evidence(BaseModel):
    """Where a fact came from, and how much it should be trusted.

    `kind` is not decoration. `sources.md` ranks primary sources above
    secondary ones and requires a document to say which it has, because the
    reader's next move differs: a vendor claim that stops being true will be
    corrected on a vendor page, while an observed one will not be corrected
    anywhere and has to be re-tested.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["vendor", "community", "observed"]
    note: str = Field(min_length=1, description="What is true, and why it matters")
    source: str | None = Field(default=None, description="URL or citation")
    verified: datetime.date | None = None


# --------------------------------------------------------------------------
# Acquisition
# --------------------------------------------------------------------------


class SteamcmdAcquire(BaseModel):
    """Fetch a server build through SteamCMD."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    method: Literal["steamcmd"]
    app_id: int = Field(gt=0)
    login: str = "anonymous"
    # "validate" is SteamCMD's own word and belongs in the manifest, but it
    # collides with a BaseModel method, so it is aliased rather than renamed.
    validate_files: bool = Field(default=True, alias="validate")


class HttpAcquire(BaseModel):
    """Fetch a server build over HTTP. Minecraft's shape, not Valheim's."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["http"]
    url: str
    checksum: str | None = None


Acquire = Annotated[SteamcmdAcquire | HttpAcquire, Field(discriminator="method")]


class Runtime(BaseModel):
    """What the server needs to execute. Normally absorbed by the image."""

    model_config = ConfigDict(extra="forbid")

    platform: str = Field(description="Container platform, for example linux/amd64")
    libraries: list[str] = Field(default_factory=list)
    min_glibc: str | None = None
    min_glibcxx: str | None = None


class Precondition(BaseModel):
    """Something that must be satisfied before first start.

    Exists for Minecraft's `eula.txt`, which has no analogue in the other four
    titles surveyed. Valheim declares none, and an empty list is the honest way
    to say so.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    kind: Literal["accept_file"]
    path: str
    content: str


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


class Setting(BaseModel):
    """One knob the operator sets, in the title's own vocabulary.

    ADR 0005 consequence 5 forbids a universal configuration vocabulary, so
    these are named after what the title calls them and are not translated.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: Literal["string", "int", "bool", "list"]
    required: bool = False
    default: str | int | bool | list[str] | None = None
    secret: bool = False
    description: str = Field(min_length=1)


class Flag(BaseModel):
    """One command-line flag, and where its value comes from.

    Flags render in declared order. That is load-bearing rather than
    incidental: Iron Gate documents that `-preset` overwrites any previously
    set modifiers, so the order of this list is part of the configuration.
    """

    model_config = ConfigDict(extra="forbid")

    flag: str = Field(pattern=r"^-{1,2}[A-Za-z][A-Za-z0-9-]*$")
    value_from: str | None = Field(default=None, description="Name of a declared setting")
    literal: str | None = Field(default=None, description="A fixed value")
    repeat: bool = Field(default=False, description="Emit once per item of a list setting")
    when: str | None = Field(default=None, description="Emit only if this bool setting is true")

    @model_validator(mode="after")
    def _one_source_of_value(self) -> Flag:
        if self.value_from is not None and self.literal is not None:
            msg = f"flag {self.flag}: give value_from or literal, not both"
            raise ValueError(msg)
        if self.repeat and self.value_from is None:
            msg = f"flag {self.flag}: repeat needs value_from pointing at a list setting"
            raise ValueError(msg)
        return self


class MinLengthConstraint(BaseModel):
    """A setting must be at least this long."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["min_length"]
    field: str
    value: int = Field(gt=0)
    evidence: Evidence


class NotSubstringOfConstraint(BaseModel):
    """A setting must not appear inside other settings.

    Valheim's, and the reason it exists is that breaking it does not look like
    a configuration error: the server logs `Error bad password:` and exits, so
    it presents as a server that will not start.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["not_substring_of"]
    field: str
    of: list[str] = Field(min_length=1)
    case_insensitive: bool = True
    evidence: Evidence


class MustPrecedeConstraint(BaseModel):
    """One flag must be rendered before another.

    Valheim's `-preset` discards previously set `-modifier` values, and nothing
    warns you: the server starts and the world is simply not what was asked
    for.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["must_precede"]
    flag: str
    before: str
    evidence: Evidence


Constraint = Annotated[
    MinLengthConstraint | NotSubstringOfConstraint | MustPrecedeConstraint,
    Field(discriminator="kind"),
]


class CommandLineConfig(BaseModel):
    """Configuration expressed entirely as command-line flags.

    One member of what will become a union. The other four titles surveyed use
    a properties file, an ini, a json file and an in-game manager, and ADR 0005
    consequence 2 expects the schema to grow for them. It grows when a real
    title arrives, not before: a speculative `PropertiesConfig` with no title
    behind it is the over-building `platform-architecture.md` warns against.
    """

    model_config = ConfigDict(extra="forbid")

    format: Literal["command_line_flags"]
    settings: list[Setting] = Field(min_length=1)
    flags: list[Flag] = Field(min_length=1)
    constraints: list[Constraint] = Field(default_factory=list)


class ConfigHazard(BaseModel):
    """A file the update process overwrites, so configuration never goes there.

    ADR 0005 defends this field specifically: without it the platform would
    write configuration into a file the next update destroys, and the symptom
    arrives weeks later with no obvious cause.
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    overwritten_by: Literal["update", "restart"]
    evidence: Evidence


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------


class StateDir(BaseModel):
    """The single path holding everything that must survive.

    The most useful invariant in the evidence table, because it is what makes
    backup generic across titles that agree on nothing else.
    """

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Path inside the container")
    configured_by: str | None = Field(
        default=None, description="The flag that points the server at it"
    )
    contains: list[str] = Field(
        default_factory=list,
        description=(
            "What belongs to this directory and must travel with a copy of it. "
            "Not a presence requirement: a title may create some of these lazily, "
            "and a brand new server legitimately has none of them yet. It is a "
            "list of what must not be left behind when something IS there"
        ),
    )


class GenerationMarkerConsistency(BaseModel):
    """Tell a complete save from one in flight, by a per-generation marker.

    Valheim writes a new generation and retires the previous one, then writes a
    marker when the write completed. ADR 0005 defends this field on the grounds
    that a backup service which only knows "copy this directory" cannot tell a
    consistent copy from a corrupt one, and the whole value of the platform
    rests on the backup being real.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["generation_marker"]
    hot_copy_safe: bool = Field(
        description=(
            "May a copy be taken while the server is running? True only for a "
            "title that writes a new generation and retires the old one, rather "
            "than overwriting in place. A title that overwrites cannot be copied "
            "hot no matter how the copy is verified"
        )
    )
    hot_copy_evidence: Evidence | None = Field(
        default=None, description="Why a hot copy is safe. Required when hot_copy_safe is true"
    )
    world_glob: str = Field(description="Glob, relative to state_dir, matching each world")
    generation_pattern: str = Field(
        description=r"Regex with a named group 'generation', matched against filenames"
    )
    complete_marker: str = Field(
        description="Filename template for the marker, with {generation} substituted"
    )
    evidence: Evidence

    @model_validator(mode="after")
    def _a_safe_hot_copy_says_why(self) -> GenerationMarkerConsistency:
        # ADR 0003 calls the hot copy "the most complex option and the one most
        # likely to be subtly wrong", and recommends stopping the server
        # instead. Declaring it safe is therefore a claim that overrides the
        # default advice, and a claim like that has to carry its reasoning or
        # it is just an assertion that suits whoever is in a hurry.
        if self.hot_copy_safe and self.hot_copy_evidence is None:
            msg = (
                "hot_copy_safe is true but hot_copy_evidence is missing. ADR 0003 "
                "recommends stopping the server to copy, so claiming otherwise "
                "needs a reason"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _pattern_and_marker_agree(self) -> GenerationMarkerConsistency:
        try:
            compiled = re.compile(self.generation_pattern)
        except re.error as error:
            msg = f"generation_pattern is not a valid regex: {error}"
            raise ValueError(msg) from error

        if "generation" not in compiled.groupindex:
            msg = "generation_pattern must contain a named group (?P<generation>...)"
            raise ValueError(msg)

        if "{generation}" not in self.complete_marker:
            msg = "complete_marker must contain {generation}, or it cannot identify a generation"
            raise ValueError(msg)

        return self


StateConsistency = Annotated[GenerationMarkerConsistency, Field(discriminator="kind")]


# --------------------------------------------------------------------------
# Ports, stop, health
# --------------------------------------------------------------------------


class Port(BaseModel):
    """One port, its protocol, its role, and whether it may be remapped.

    `remap_allowed` has no default on purpose. Satisfactory cannot remap its
    standard port but can remap its second one, so the constraint is per-port,
    and a default would let a manifest be silent about the thing that decides
    whether a configuration is broken.
    """

    model_config = ConfigDict(extra="forbid")

    number: int = Field(gt=0, lt=65536)
    protocol: Literal["udp", "tcp"]
    role: str = Field(min_length=1)
    remap_allowed: bool
    remap_evidence: Evidence | None = Field(
        default=None, description="Why remapping is forbidden. Required when remap_allowed is false"
    )
    forward: bool = Field(description="Does this need a rule at the household router?")
    when: str | None = Field(default=None, description="Only present if this bool setting is true")
    note: str | None = Field(
        default=None, description="How this port fails, for the operator reading a symptom"
    )

    @model_validator(mode="after")
    def _a_forbidden_remap_says_why(self) -> Port:
        # "You may not do that" without a reason invites someone to decide the
        # rule is superstition, and for ports that decision produces a server
        # which starts, lists itself, and refuses every connection. The reason
        # is per-port, so it cannot live in a comment next to one of them.
        if not self.remap_allowed and self.remap_evidence is None:
            msg = (
                f"port {self.number}: remap_allowed is false, so remap_evidence must say "
                "why, because a refusal that cannot explain itself gets overridden"
            )
            raise ValueError(msg)
        return self


class SignalStop(BaseModel):
    """Stop by sending a signal.

    Docker's defaults, SIGTERM after ten seconds, are wrong for every title
    surveyed: the wrong signal, and a timeout shorter than a large world takes
    to write. Both halves are stated here so neither can be inherited.
    """

    model_config = ConfigDict(extra="forbid")

    method: Literal["signal"]
    signal: Literal["SIGINT", "SIGTERM", "SIGHUP", "SIGQUIT"]
    grace_seconds: int = Field(gt=0)
    evidence: Evidence


Stop = Annotated[SignalStop, Field(discriminator="method")]


class A2SLiveness(BaseModel):
    """Is it answering? A Steam A2S query on the query port."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["a2s_query"]
    port: int = Field(gt=0, lt=65536)


class StateAdvancingDurability(BaseModel):
    """Is state still being written? The check that protects the world.

    `always-on-operation.md` ranks this above liveness, against the usual
    instinct, because the failure it catches does not report itself: a
    container reported healthy while every autosave failed silently.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["state_advancing"]
    max_stale_seconds: int = Field(gt=0)
    evidence: Evidence


class Health(BaseModel):
    """Two separate claims, and the manifest carries both.

    ADR 0005 consequence 4. A server can pass liveness and fail durability
    indefinitely, which is exactly the failure that costs a world, so neither
    field is optional.
    """

    model_config = ConfigDict(extra="forbid")

    liveness: A2SLiveness
    durability: StateAdvancingDurability


# --------------------------------------------------------------------------
# The optional tail
# --------------------------------------------------------------------------


class Admin(BaseModel):
    """A remote administration channel, for titles that have one."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["rcon", "rest_api", "https_api"]
    port: int = Field(gt=0, lt=65536)
    protocol: Literal["tcp", "udp"] = "tcp"
    note: str | None = None


class PlayerLists(BaseModel):
    """How player identity and allowlists work."""

    model_config = ConfigDict(extra="forbid")

    identity_format: str = Field(description="Shape of an id, in the title's own terms")
    admin_file: str | None = None
    allow_file: str | None = None
    allow_semantics: Literal["exclusive_allowlist", "additive"] | None = None
    ban_file: str | None = None
    evidence: Evidence | None = None

    @model_validator(mode="after")
    def _allowlist_semantics_are_stated(self) -> PlayerLists:
        # A non-empty permittedlist.txt bans everyone not on it. Iron Gate
        # documents this and it surprises everyone the first time, so a
        # manifest that names an allow file without saying how it behaves is
        # withholding the only part that matters.
        if self.allow_file is not None and self.allow_semantics is None:
            msg = (
                "allow_file needs allow_semantics: an allowlist that excludes "
                "everyone not on it is not optional detail"
            )
            raise ValueError(msg)
        return self


def _pattern_without_the_code_group(pattern: str) -> str | None:
    """The literal text around `(?P<code>...)`, or None if it is not literal.

    Used to construct the line a server writes when the code does not exist
    yet, so a pattern that would accept it can be refused at load time rather
    than discovered by a friend who cannot connect.
    """
    opening = pattern.find("(?P<code>")
    if opening == -1:
        return None

    depth = 0
    for index in range(opening, len(pattern)):
        if pattern[index] == "(" and (index == opening or pattern[index - 1] != "\\"):
            depth += 1
        elif pattern[index] == ")" and pattern[index - 1] != "\\":
            depth -= 1
            if depth == 0:
                remainder = pattern[:opening] + pattern[index + 1 :]
                # Only meaningful when what is left is plain text.
                if re.search(r"[\\\[\]{}()*+?|^$]", remainder):
                    return None
                return remainder
    return None


class JoinCode(BaseModel):
    """How to find the code players need, for a relay that issues one.

    Valheim has no administration channel, so the server's log is the only
    place this appears. That couples the platform to a game's log format, which
    is the coupling `always-on-operation.md` warns about. It is accepted
    because there is no other source, and contained by living here as data: a
    log format change is a manifest edit, not a code change.
    """

    model_config = ConfigDict(extra="forbid")

    source: Literal["container_log"]
    pattern: str = Field(
        description="Regex with a named group 'code', matched against the log stream"
    )
    evidence: Evidence

    @model_validator(mode="after")
    def _pattern_captures_a_code(self) -> JoinCode:
        try:
            compiled = re.compile(self.pattern)
        except re.error as error:
            msg = f"join code pattern is not a valid regex: {error}"
            raise ValueError(msg) from error

        if "code" not in compiled.groupindex:
            msg = "join code pattern must contain a named group (?P<code>...)"
            raise ValueError(msg)

        # The pattern has to require content, not merely locate the phrase.
        # Valheim announces the session BEFORE the lobby exists, so a line goes
        # out with nothing where the code should be, and a lenient pattern
        # captures "" from it and publishes that with great confidence. The
        # failure then looks like the server being fine.
        #
        # Checked by building the line that would carry an absent code: take
        # the pattern and delete the capture group, leaving its literal
        # surroundings. If the pattern still matches that, it accepts a code
        # that is not there. When the surroundings are not literal the probe
        # simply will not match, and the check declines to guess.
        probe = _pattern_without_the_code_group(self.pattern)
        if probe is not None:
            found = compiled.search(probe)
            if found is not None and found.group("code") == "":
                msg = (
                    f"join code pattern captures an empty code from {probe!r}, "
                    "which is the line a server writes before the code exists"
                )
                raise ValueError(msg)

        return self


class Relay(BaseModel):
    """A title's own relay, if it ships one."""

    model_config = ConfigDict(extra="forbid")

    name: str
    enabled_by: str = Field(description="Name of the bool setting that turns it on")
    removes_port_forwarding: bool
    rotates_join_code_on_restart: bool
    join_code: JoinCode | None = None
    evidence: Evidence

    @model_validator(mode="after")
    def _a_rotating_code_must_be_findable(self) -> Relay:
        # A relay whose code changes on every restart, with no way to read the
        # new one, silently locks out everyone who was not watching. ADR 0006
        # consequence 1 makes publishing it an obligation rather than a
        # feature, so the manifest must say where it comes from.
        if self.rotates_join_code_on_restart and self.join_code is None:
            msg = (
                f"relay {self.name!r} rotates its join code on every restart but "
                "declares no join_code source, so nothing could publish the new one"
            )
            raise ValueError(msg)
        return self


class Reachability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relay: Relay | None = None


# --------------------------------------------------------------------------
# The manifest
# --------------------------------------------------------------------------


class TitleManifest(BaseModel):
    """One title, declared.

    Field order follows the contract table in `docs/platform-architecture.md`,
    and required-ness follows its "Required" column exactly, so the two can be
    read side by side.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=1)
    acquire: Acquire
    runtime: Runtime
    preconditions: list[Precondition] = Field(default_factory=list)
    config: CommandLineConfig
    config_hazards: list[ConfigHazard] = Field(default_factory=list)
    state_dir: StateDir
    state_consistency: StateConsistency | None = None
    ports: list[Port] = Field(min_length=1)
    stop: Stop
    health: Health
    admin: Admin | None = None
    players: PlayerLists | None = None
    reachability: Reachability | None = None

    # -- cross-field rules --------------------------------------------------
    # Each one exists because breaking it produces a manifest that validates
    # field by field and is still wrong.

    def setting_names(self) -> set[str]:
        return {setting.name for setting in self.config.settings}

    def flag_names(self) -> set[str]:
        return {flag.flag for flag in self.config.flags}

    @model_validator(mode="after")
    def _references_resolve(self) -> TitleManifest:
        known = self.setting_names()
        problems: list[str] = []

        for flag in self.config.flags:
            for attribute in ("value_from", "when"):
                referenced = getattr(flag, attribute)
                if referenced is not None and referenced not in known:
                    problems.append(
                        f"flag {flag.flag}: {attribute} names unknown setting {referenced!r}"
                    )

        for constraint in self.config.constraints:
            if isinstance(constraint, MustPrecedeConstraint):
                for attribute in ("flag", "before"):
                    referenced = getattr(constraint, attribute)
                    if referenced not in self.flag_names():
                        problems.append(
                            f"constraint must_precede: {attribute} names unknown flag "
                            f"{referenced!r}"
                        )
                continue

            for referenced in [constraint.field, *getattr(constraint, "of", [])]:
                if referenced not in known:
                    problems.append(
                        f"constraint {constraint.kind}: names unknown setting {referenced!r}"
                    )

        for port in self.ports:
            if port.when is not None and port.when not in known:
                problems.append(f"port {port.number}: when names unknown setting {port.when!r}")

        if self.reachability is not None and self.reachability.relay is not None:
            enabled_by = self.reachability.relay.enabled_by
            if enabled_by not in known:
                problems.append(
                    f"reachability.relay: enabled_by names unknown setting {enabled_by!r}"
                )

        if problems:
            raise ValueError("; ".join(problems))
        return self

    @model_validator(mode="after")
    def _ports_are_distinct(self) -> TitleManifest:
        seen: set[tuple[int, str]] = set()
        for port in self.ports:
            key = (port.number, port.protocol)
            if key in seen:
                msg = f"port {port.number}/{port.protocol} is declared twice"
                raise ValueError(msg)
            seen.add(key)
        return self

    @model_validator(mode="after")
    def _liveness_probes_a_declared_port(self) -> TitleManifest:
        # A health check aimed at a port the title does not open is a check
        # that fails forever, which reads as an outage rather than as a
        # manifest error.
        declared = {port.number for port in self.ports}
        if self.health.liveness.port not in declared:
            msg = (
                f"health.liveness.port {self.health.liveness.port} is not among the "
                f"declared ports {sorted(declared)}"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _durability_needs_a_consistency_rule(self) -> TitleManifest:
        # "State is advancing" is unanswerable without knowing what a complete
        # save looks like. Declaring the check without the rule would give a
        # durability signal that cannot be computed.
        if self.state_consistency is None:
            msg = (
                "health.durability is declared but state_consistency is not, so "
                "nothing can tell a complete save from one still in flight"
            )
            raise ValueError(msg)
        return self


def load_manifest(path: Path) -> TitleManifest:
    """Read and validate a manifest, or say precisely what is wrong with it.

    A manifest is edited a few times a year, from documentation, by someone who
    does not have this schema in their head. ADR 0008 chose Pydantic for error
    quality on exactly that grounds, so the errors are kept rather than
    flattened into "invalid".
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        msg = f"{path} is not valid YAML: {error}"
        raise ManifestInvalid(msg) from error

    if not isinstance(raw, dict):
        msg = f"{path} should contain a mapping of manifest fields, found {type(raw).__name__}"
        raise ManifestInvalid(msg)

    try:
        return TitleManifest.model_validate(raw)
    except ValidationError as error:
        lines = [f"{path} does not satisfy the title contract:"]
        for problem in error.errors():
            location = ".".join(str(part) for part in problem["loc"]) or "(root)"
            lines.append(f"  {location}: {problem['msg']}")
        raise ManifestInvalid("\n".join(lines)) from error
