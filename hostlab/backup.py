"""Back up and restore a title's state directory.

ADR 0005 consequence 3 calls backup "the platform's flagship shared service",
because the single-state-directory invariant holds across every title surveyed
even when they agree on nothing else. ADR 0003 sets what it has to do, and
three of its rules are the ones most likely to be skipped:

1. **Copy the entire state directory as a unit.** A partial copy yields a world
   the server cannot open, and its response to a world it cannot open is to
   generate an empty one rather than to report an error.
2. **Verify after copying, not before restoring.** A job that reports success
   because a copy command returned zero has verified nothing.
3. **The backup is not accepted until it has been restored.** Which is why
   `restore` and `verify` are here and not left as an exercise.

The consistency question is delegated to `state.py`, which answers it from the
manifest, so nothing here knows what a Valheim world is.

**Why restic.** Encryption, retention and a real verify in one static binary.
ADR 0003 requires all three; hand-rolling them is more machinery than adopting
them, and its failure mode is a backup that does not restore.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from hostlab.errors import HostlabError
from hostlab.state import StateInspection, inspect_state, require_consistent

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hostlab.manifest import TitleManifest

# A week of dailies plus a few monthlies. ADR 0003: retention has to exceed the
# time it takes to NOTICE a problem, not the time to have one. The game's own
# rolling backups hold about 38 hours, which does not cover "corrupted on
# Friday, noticed on Monday"; this does.
DEFAULT_RETENTION: tuple[str, ...] = (
    "--keep-daily",
    "7",
    "--keep-weekly",
    "5",
    "--keep-monthly",
    "6",
)


class BackupFailed(HostlabError):
    """A backup or restore did not complete. Never reported as success."""


@dataclass(frozen=True)
class Repository:
    """Where backups go, and how to unlock them."""

    location: str
    password_file: Path | None = None
    environment: Mapping[str, str] = field(default_factory=dict)

    def env(self) -> dict[str, str]:
        values = {"RESTIC_REPOSITORY": self.location, **self.environment}
        if self.password_file is not None:
            values["RESTIC_PASSWORD_FILE"] = str(self.password_file)
        return values


def restic_argv(repository: Repository, command: str, *arguments: str) -> list[str]:
    """Build a restic invocation. Pure, so the argument list can be asserted."""
    return ["restic", "--repo", repository.location, command, *arguments]


def backup_argv(
    repository: Repository, source: Path, title_id: str, tags: Sequence[str] = ()
) -> list[str]:
    """The backup command.

    The state directory is passed as one path, per ADR 0003 rule 1: the whole
    directory as a unit, never a selection of files inside it.
    """
    argv = restic_argv(repository, "backup", str(source), "--tag", title_id)
    for tag in tags:
        argv += ["--tag", tag]
    return argv


def forget_argv(repository: Repository, title_id: str) -> list[str]:
    """Retention. `--prune` actually reclaims, rather than only forgetting."""
    return restic_argv(repository, "forget", "--tag", title_id, *DEFAULT_RETENTION, "--prune")


def _run(argv: list[str], environment: Mapping[str, str]) -> str:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, **environment},
        )
    except FileNotFoundError as error:
        message = (
            f"{argv[0]} is not installed. ADR 0008 chose it for encryption, "
            "retention and a real verify in one binary; without it there is no "
            "off-site backup at all."
        )
        raise BackupFailed(message) from error
    except subprocess.CalledProcessError as error:
        message = f"{' '.join(argv[:3])} failed:\n{error.stderr.strip() or error.stdout.strip()}"
        raise BackupFailed(message) from error
    return completed.stdout


def initialise(repository: Repository) -> str:
    """Create the repository if it does not exist yet."""
    return _run(restic_argv(repository, "init"), repository.env())


def back_up(
    manifest: TitleManifest,
    state_dir: Path,
    repository: Repository,
    *,
    require_consistency: bool = True,
) -> str:
    """Copy the state directory, refusing if it is not in a copyable condition.

    `require_consistency` exists for one legitimate case: a state directory
    that is already damaged is exactly the one you most want a copy of before
    touching it. It defaults to on, because the usual reason a consistency
    check is in the way is that the check is right.
    """
    if require_consistency:
        require_consistent(inspect_state(manifest, state_dir))

    output = _run(backup_argv(repository, state_dir, manifest.id), repository.env())
    _run(forget_argv(repository, manifest.id), repository.env())
    return output


def verify(repository: Repository, *, read_data: bool = False) -> str:
    """Check the repository's own integrity.

    Cheap by default and thorough on request. ADR 0003 asks for verification
    after copying rather than before restoring, and this is that check; the
    restore drill is the other half and neither substitutes for the other.
    """
    arguments = ["--read-data"] if read_data else []
    return _run(restic_argv(repository, "check", *arguments), repository.env())


def snapshots(repository: Repository, title_id: str) -> str:
    return _run(restic_argv(repository, "snapshots", "--tag", title_id), repository.env())


def restore(
    repository: Repository,
    snapshot: str,
    target: Path,
    manifest: TitleManifest | None = None,
) -> StateInspection | None:
    """Restore a snapshot, then inspect what came back.

    The inspection is the point. ADR 0003 is explicit that an untested backup
    is a belief, and the failure it warns about is not an error message: the
    server starts and the world is empty. Checking that the restored tree holds
    a complete generation turns that silent case into a loud one.
    """
    if target.exists() and any(target.iterdir()):
        message = (
            f"{target} is not empty. Restore somewhere else: ADR 0003's drill says "
            "never restore onto the live world as a test, and a second server on "
            "the same state directory is a way to lose both."
        )
        raise BackupFailed(message)

    target.mkdir(parents=True, exist_ok=True)
    _run(
        restic_argv(repository, "restore", snapshot, "--target", str(target)),
        repository.env(),
    )

    if manifest is None:
        return None

    # restic restores absolute source paths under the target, so the state
    # directory is somewhere below rather than at the root.
    for candidate in [target, *sorted(p for p in target.rglob("*") if p.is_dir())]:
        inspection = inspect_state(manifest, candidate)
        if inspection.worlds:
            return inspection

    message = (
        f"the restore produced no recognisable state under {target}. "
        "A world that does not load is better news than one that loads empty, "
        "but both mean this backup would not have brought the world back."
    )
    raise BackupFailed(message)
