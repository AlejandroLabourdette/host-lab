"""The platform's failure vocabulary.

Three kinds of failure, kept apart because they need different responses and
because collapsing them is how a refusal gets mistaken for a crash.

`docs/platform-architecture.md` is explicit that the platform "must be able to
refuse a configuration rather than silently produce a broken server". That
makes a refusal a designed outcome rather than an error, and it has to carry
enough to act on: what was wrong, and why the rule exists at all.
"""

from __future__ import annotations


class HostlabError(Exception):
    """Base for everything this package raises on purpose."""


class ManifestInvalid(HostlabError):
    """A title manifest does not satisfy the contract in ADR 0005."""


class ConfigurationRefused(HostlabError):
    """A configuration was rejected rather than rendered into a broken server.

    Carries `because` so the message can say why the rule exists, not only
    that it was broken. The manifest supplies that text, which is what keeps
    per-title knowledge in the manifest rather than in this package.
    """

    def __init__(self, what: str, because: str) -> None:
        self.what = what
        self.because = because
        super().__init__(f"{what}\n  why this rule exists: {because}")


class StateInconsistent(HostlabError):
    """A state directory holds no copy that is provably complete.

    Raised by the backup path. ADR 0003 turns on the distinction between a
    consistent copy and one taken mid-write, so failing loudly here is the
    entire value: a backup job that reports success because the copy command
    returned zero has verified nothing.
    """
