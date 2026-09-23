"""Load an instance's configuration: what this deployment of a title is.

The manifest says what a title *is*; this says what *this* server is. They are
separate files because they change for different reasons and at different
rates: the manifest changes when the game does, this changes when the group
decides something.

Secrets are referenced, never stored. A value written as ``${VALHEIM_PASSWORD}``
is expanded from the environment for validation, and the original placeholder
is remembered so that anything written back to disk carries the placeholder
rather than the secret.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from hostlab.errors import ConfigurationRefused
from hostlab.render import Deployment, SettingValue

if TYPE_CHECKING:
    from collections.abc import Mapping

PLACEHOLDER = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")


@dataclass(frozen=True)
class Instance:
    """One deployment of one title."""

    deployment: Deployment
    settings: dict[str, SettingValue]
    # Expanded secret value -> the ${PLACEHOLDER} it came from, so a generated
    # file can be written without the secret in it.
    placeholders: dict[str, str] = field(default_factory=dict)


def _expand(value: Any, placeholders: dict[str, str], where: str) -> Any:  # noqa: ANN401
    """Expand ``${VAR}`` from the environment, remembering where it came from."""
    if isinstance(value, list):
        return [_expand(item, placeholders, where) for item in value]

    if not isinstance(value, str):
        return value

    match = PLACEHOLDER.match(value.strip())
    if match is None:
        return value

    name = match.group(1)
    resolved = os.environ.get(name)
    if resolved is None or resolved == "":
        what = f"{where} references {value}, which is not set in the environment"
        because = (
            "secrets are referenced rather than stored, so this has to come from "
            "deploy/.env or the shell. Copy deploy/.env.example and fill it in."
        )
        raise ConfigurationRefused(what, because)

    placeholders[resolved] = value
    return resolved


def load_instance(path: Path) -> Instance:
    """Read an instance file: a `deployment:` half and a `settings:` half."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        what = f"{path} is not valid YAML: {error}"
        raise ConfigurationRefused(
            what, "the instance file has to parse before it can run"
        ) from error

    if not isinstance(raw, dict):
        what = f"{path} should contain a mapping with 'deployment' and 'settings'"
        raise ConfigurationRefused(what, "see deploy/valheim/valheim.yaml for the shape")

    for half in ("deployment", "settings"):
        if half not in raw:
            what = f"{path} has no '{half}' section"
            because = (
                "an instance file has two halves that change for different reasons: "
                "'deployment' is where and how it runs, 'settings' is what the group chose"
            )
            raise ConfigurationRefused(what, because)

    placeholders: dict[str, str] = {}
    deployment_raw = {
        key: _expand(value, placeholders, f"{path}:deployment.{key}")
        for key, value in raw["deployment"].items()
    }
    settings = {
        key: _expand(value, placeholders, f"{path}:settings.{key}")
        for key, value in raw["settings"].items()
    }

    known = {
        "image",
        "container_name",
        "state_volume",
        "port_overrides",
        "memory",
        "cpus",
        "restart",
    }
    unknown = sorted(set(deployment_raw) - known)
    if unknown:
        what = f"{path}: unknown deployment key(s): {', '.join(unknown)}"
        raise ConfigurationRefused(what, f"known keys are: {', '.join(sorted(known))}")

    for required in ("image", "container_name", "state_volume"):
        if required not in deployment_raw:
            what = f"{path}: deployment.{required} is required"
            raise ConfigurationRefused(
                what, "a container needs an image, a name and somewhere to keep state"
            )

    return Instance(
        deployment=Deployment(**deployment_raw),
        settings=settings,
        placeholders=placeholders,
    )


def redact(tokens: list[str], placeholders: Mapping[str, str]) -> list[str]:
    """Put the ``${PLACEHOLDER}`` back wherever a secret value appears.

    Used when writing a generated file. The result is safe to commit and to
    read over someone's shoulder, and `docker compose` substitutes the real
    value from `.env` at run time.
    """
    return [placeholders.get(token, token) for token in tokens]
