"""Shared machinery that interprets a declarative per-title manifest.

The platform layer of `docs/platform-architecture.md`. The package is named
`hostlab` rather than `platform` because the latter is a standard library
module; see ADR 0008.
"""

from hostlab.errors import (
    ConfigurationRefused,
    HostlabError,
    ManifestInvalid,
    StateInconsistent,
)

__all__ = [
    "ConfigurationRefused",
    "HostlabError",
    "ManifestInvalid",
    "StateInconsistent",
]
