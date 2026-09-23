"""Turn a manifest and an operator's settings into a container run spec.

This is where the platform earns the right to be called one. Everything here
refuses rather than improvises, because `docs/platform-architecture.md` is
explicit: "The platform must be able to refuse a configuration rather than
silently produce a broken server."

Every refusal below traces to a documented failure rather than to taste, and
each one shares a shape that is worth naming. **None of them produces an error
at the time they happen.** Publishing a port as TCP gives a server that starts
and is unreachable. Remapping Valheim's port gives a listing that advertises a
port nobody can reach. A password inside the world name gives a server that
exits looking like a crash. Putting configuration in `start_server.sh` works
until the next update and then reverts, weeks later, with no obvious cause.

That is the argument for checking them here. A failure that announces itself
does not need a validator; these are the ones that do not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hostlab.errors import ConfigurationRefused
from hostlab.manifest import (
    Flag,
    MinLengthConstraint,
    MustPrecedeConstraint,
    NotSubstringOfConstraint,
    Port,
    Setting,
    TitleManifest,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

SettingValue = str | int | bool | list[str]

REDACTED = "********"


# --------------------------------------------------------------------------
# What comes out
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PortMapping:
    """One published port.

    `protocol` is carried all the way to the published string rather than
    defaulted anywhere, because the default is TCP and the default is wrong.
    """

    container: int
    host: int
    protocol: str
    role: str

    def published(self) -> str:
        """The `-p` argument. Always carries the protocol, never bare."""
        return f"{self.host}:{self.container}/{self.protocol}"


@dataclass(frozen=True)
class VolumeMount:
    source: str
    target: str
    read_only: bool = False


@dataclass(frozen=True)
class Deployment:
    """The operator's side of the configuration: where and how, not what."""

    image: str
    container_name: str
    state_volume: str
    port_overrides: Mapping[int, int] = field(default_factory=dict)
    memory: str | None = None
    cpus: float | None = None
    restart: str = "unless-stopped"


@dataclass(frozen=True)
class RunSpec:
    """Everything needed to run one title, with nothing left to a default.

    Notably `stop_signal` and `stop_grace_seconds` are always present. ADR 0004
    consequence 2 says Docker's defaults, SIGTERM after ten seconds, are wrong
    for this workload on both counts, and a field that can be omitted is a
    field that will be.
    """

    title_id: str
    image: str
    container_name: str
    command: list[str]
    ports: list[PortMapping]
    volumes: list[VolumeMount]
    stop_signal: str
    stop_grace_seconds: int
    restart: str
    memory: str | None
    cpus: float | None
    secret_values: frozenset[str]

    def redacted_command(self) -> list[str]:
        """The command with secret values replaced, for logs and status.

        Valheim is configured by flags only, so the password is on the command
        line and visible to anything that can read the process table. That is
        the title's constraint and not ours to fix. Not putting it into our own
        logs, a status message or a crash report is ours, and this is it.
        """
        return [REDACTED if token in self.secret_values else token for token in self.command]

    def docker_run_args(self) -> list[str]:
        """The full `docker run` argument list, for a human to copy and run."""
        args = ["docker", "run", "--detach", "--name", self.container_name]
        args += ["--restart", self.restart]
        args += ["--stop-signal", self.stop_signal]
        args += ["--stop-timeout", str(self.stop_grace_seconds)]
        if self.memory is not None:
            args += ["--memory", self.memory]
        if self.cpus is not None:
            args += ["--cpus", str(self.cpus)]
        for volume in self.volumes:
            suffix = ":ro" if volume.read_only else ""
            args += ["--volume", f"{volume.source}:{volume.target}{suffix}"]
        for port in self.ports:
            args += ["--publish", port.published()]
        args.append(self.image)
        args += self.command
        return args


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


def _type_matches(setting: Setting, value: SettingValue) -> bool:
    match setting.type:
        case "string":
            return isinstance(value, str)
        case "int":
            # bool is a subclass of int in Python, and accepting True for a
            # port number would be a silent absurdity.
            return isinstance(value, int) and not isinstance(value, bool)
        case "bool":
            return isinstance(value, bool)
        case "list":
            return isinstance(value, list) and all(isinstance(item, str) for item in value)


def resolve_settings(
    manifest: TitleManifest, supplied: Mapping[str, SettingValue]
) -> dict[str, SettingValue | None]:
    """Merge supplied values over declared defaults, refusing anything wrong.

    Unknown names are refused rather than ignored. A typo that is silently
    dropped is a setting that silently does nothing, and from the outside that
    is indistinguishable from the platform not supporting it.
    """
    declared = {setting.name: setting for setting in manifest.config.settings}

    unknown = sorted(set(supplied) - set(declared))
    if unknown:
        what = f"unknown setting(s) for {manifest.id}: {', '.join(unknown)}"
        because = (
            "a name that is not declared would be silently dropped, which looks "
            f"exactly like the platform ignoring you. Declared: {', '.join(sorted(declared))}"
        )
        raise ConfigurationRefused(what, because)

    resolved: dict[str, SettingValue | None] = {}
    for name, setting in declared.items():
        value = supplied.get(name, setting.default)

        if value is None:
            if setting.required:
                what = f"setting {name!r} is required and was not supplied"
                raise ConfigurationRefused(what, setting.description.strip())
            resolved[name] = None
            continue

        if not _type_matches(setting, value):
            what = (
                f"setting {name!r} should be {setting.type}, got {type(value).__name__} ({value!r})"
            )
            raise ConfigurationRefused(what, setting.description.strip())

        resolved[name] = value

    return resolved


# --------------------------------------------------------------------------
# Constraints
# --------------------------------------------------------------------------


def check_constraints(
    manifest: TitleManifest, values: Mapping[str, SettingValue | None], command: list[str]
) -> None:
    """Apply the title's own declared rules.

    The rules live in the manifest and the reasoning comes back out in the
    refusal, which is what keeps ADR 0005's "a title is data" true. Nothing in
    this function knows it is checking Valheim.
    """
    for constraint in manifest.config.constraints:
        match constraint:
            case MinLengthConstraint():
                value = values.get(constraint.field)
                if isinstance(value, str) and len(value) < constraint.value:
                    what = (
                        f"{constraint.field} is {len(value)} characters, "
                        f"and at least {constraint.value} are required"
                    )
                    raise ConfigurationRefused(what, constraint.evidence.note.strip())

            case NotSubstringOfConstraint():
                _check_not_substring(constraint, values)

            case MustPrecedeConstraint():
                _check_ordering(constraint, command)


def _check_not_substring(
    constraint: NotSubstringOfConstraint, values: Mapping[str, SettingValue | None]
) -> None:
    needle = values.get(constraint.field)
    if not isinstance(needle, str) or not needle:
        return

    comparable = needle.casefold() if constraint.case_insensitive else needle
    for other in constraint.of:
        haystack = values.get(other)
        if not isinstance(haystack, str):
            continue
        subject = haystack.casefold() if constraint.case_insensitive else haystack
        if comparable in subject:
            what = f"{constraint.field} appears inside {other}"
            raise ConfigurationRefused(what, constraint.evidence.note.strip())


def _check_ordering(constraint: MustPrecedeConstraint, command: list[str]) -> None:
    """Checked against the rendered command, not against the manifest.

    The manifest's flag order is the intent; this is the artifact. A bug in
    rendering that reorders them would pass a check on the declaration and
    still produce the silently wrong world the rule exists to prevent.
    """
    if constraint.flag not in command or constraint.before not in command:
        return
    if command.index(constraint.flag) > command.index(constraint.before):
        what = f"{constraint.flag} is rendered after {constraint.before}"
        raise ConfigurationRefused(what, constraint.evidence.note.strip())


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _is_enabled(flag_or_port: Flag | Port, values: Mapping[str, SettingValue | None]) -> bool:
    if flag_or_port.when is None:
        return True
    return bool(values.get(flag_or_port.when))


def render_command(
    manifest: TitleManifest, values: Mapping[str, SettingValue | None]
) -> tuple[list[str], set[str]]:
    """Render the flags, in declared order, and report which tokens are secret.

    Declared order is preserved exactly. For Valheim that is the difference
    between the world the group asked for and a world that silently is not,
    because a preset placed after a modifier discards it.
    """
    command: list[str] = []
    secrets: set[str] = set()

    for flag in manifest.config.flags:
        if not _is_enabled(flag, values):
            continue

        if flag.literal is not None:
            command += [flag.flag, flag.literal]
            continue

        if flag.value_from is None:
            command.append(flag.flag)
            continue

        value = values.get(flag.value_from)
        if value is None:
            # An optional setting nobody set. Emitting a bare flag or an empty
            # string here is how a server ends up with -preset and no preset.
            continue

        setting = next(s for s in manifest.config.settings if s.name == flag.value_from)

        if flag.repeat:
            if not isinstance(value, list):
                continue
            for item in value:
                # A list item may carry more than one token: Valheim's
                # -modifier takes a name and a value. Splitting here keeps that
                # general rather than teaching the renderer about modifiers.
                command += [flag.flag, *item.split()]
            continue

        rendered = _render_scalar(value)
        command += [flag.flag, rendered]
        if setting.secret:
            secrets.add(rendered)

    return command, secrets


def _render_scalar(value: SettingValue) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _map_ports(
    manifest: TitleManifest,
    deployment: Deployment,
    values: Mapping[str, SettingValue | None],
) -> list[PortMapping]:
    """Map the ports that will actually be published.

    A port whose `when` setting is off is not published, so it is not checked:
    Valheim declares 2458 for crossplay, and refusing an override for a port
    that is not in play would be noise rather than protection.
    """
    mappings: list[PortMapping] = []

    for port in manifest.ports:
        if not _is_enabled(port, values):
            continue

        host = deployment.port_overrides.get(port.number, port.number)

        if host != port.number and not port.remap_allowed:
            what = (
                f"port {port.number}/{port.protocol} ({port.role}) may not be "
                f"remapped, and was mapped to {host}"
            )
            # The reason, not the symptom. port.note describes how an
            # unreachable port presents; remap_evidence says why this port may
            # not move, which is what the operator is arguing with.
            because = (
                port.remap_evidence.note
                if port.remap_evidence is not None
                else "the manifest declares remap_allowed: false for this port"
            )
            raise ConfigurationRefused(what, because.strip())

        mappings.append(
            PortMapping(container=port.number, host=host, protocol=port.protocol, role=port.role)
        )

    return mappings


def _refuse_state_inside_a_hazard(manifest: TitleManifest) -> None:
    """Nothing the platform writes may live where an update will overwrite it.

    For a command-line title the set of files the platform writes is empty by
    construction, and that is exactly how Valheim's `start_server.sh` trap is
    avoided: the launch parameters are the container's command, not a script on
    disk. The state directory is the one path that must still be checked, and
    the check is what will catch the mistake when a file-configured title
    arrives and the set stops being empty.
    """
    state = manifest.state_dir.path.rstrip("/")

    for hazard in manifest.config_hazards:
        hazard_path = hazard.path.rstrip("/")
        if state == hazard_path or state.startswith(hazard_path + "/"):
            what = f"state_dir {manifest.state_dir.path!r} is inside config hazard {hazard.path!r}"
            raise ConfigurationRefused(what, hazard.evidence.note.strip())


def render(
    manifest: TitleManifest,
    settings: Mapping[str, SettingValue],
    deployment: Deployment,
) -> RunSpec:
    """Produce a run spec, or refuse and say why.

    The order matters. Settings resolve first so a constraint cannot run
    against a missing value; the command renders next so the ordering rule can
    be checked against the artifact; ports and hazards are structural and are
    checked last.
    """
    values = resolve_settings(manifest, settings)
    command, secrets = render_command(manifest, values)
    check_constraints(manifest, values, command)

    ports = _map_ports(manifest, deployment, values)
    _refuse_state_inside_a_hazard(manifest)

    return RunSpec(
        title_id=manifest.id,
        image=deployment.image,
        container_name=deployment.container_name,
        command=command,
        ports=ports,
        volumes=[VolumeMount(source=deployment.state_volume, target=manifest.state_dir.path)],
        stop_signal=manifest.stop.signal,
        stop_grace_seconds=manifest.stop.grace_seconds,
        restart=deployment.restart,
        memory=deployment.memory,
        cpus=deployment.cpus,
        secret_values=frozenset(secrets),
    )


def describe(spec: RunSpec) -> Iterable[str]:
    """A human-readable summary, safe to print. Secrets are redacted."""
    yield f"title      {spec.title_id}"
    yield f"image      {spec.image}"
    yield f"container  {spec.container_name}"
    yield f"stop       {spec.stop_signal}, up to {spec.stop_grace_seconds}s"
    for port in spec.ports:
        yield f"port       {port.published()}  {port.role}"
    for volume in spec.volumes:
        yield f"volume     {volume.source} -> {volume.target}"
    yield f"command    {' '.join(spec.redacted_command())}"
