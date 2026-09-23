"""The failure vocabulary is small, but two properties are load-bearing."""

import pytest

from hostlab import ConfigurationRefused, HostlabError, ManifestInvalid, StateInconsistent


@pytest.mark.parametrize("error", [ManifestInvalid, ConfigurationRefused, StateInconsistent])
def test_every_error_is_catchable_as_one(error: type[HostlabError]) -> None:
    """A caller that wants to handle "the platform said no" can catch one type."""
    assert issubclass(error, HostlabError)


def test_a_refusal_explains_why_the_rule_exists() -> None:
    """docs/platform-architecture.md requires refusing rather than rendering a
    broken server. A refusal that only says "invalid" sends the reader to the
    source; one that carries the manifest's reasoning does not."""
    refusal = ConfigurationRefused(
        what="port 2456 may not be remapped to 2556",
        because="Valheim advertises its own port to the Steam lobby",
    )

    assert "2556" in str(refusal)
    assert "advertises its own port" in str(refusal)
    assert refusal.because == "Valheim advertises its own port to the Steam lobby"
