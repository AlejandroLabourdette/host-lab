"""The platform's command line.

Commands, in increasing order of what they touch:

  validate   the manifest alone, no instance, no environment
  plan       manifest plus this instance, with every refusal applied
  compose    the same, and writes the compose file
  state      inspect a state directory: is it consistent, is it advancing
  backup     copy it off the host, verifying first
  snapshots  what is in the repository
  restore    bring one back, somewhere else, and inspect what arrived

`plan` exists so the refusals can be run without producing anything. The whole
argument of `render.py` is that the failures it catches are silent ones, and a
check that is only reachable by deploying is a check people skip.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from hostlab.backup import Repository, back_up, restore, snapshots, verify
from hostlab.compose import render_compose
from hostlab.errors import HostlabError
from hostlab.manifest import load_manifest
from hostlab.render import describe, render
from hostlab.settings import load_instance
from hostlab.state import inspect_state

TITLES = Path("titles")


def _manifest_path(title: str) -> Path:
    path = TITLES / f"{title}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in TITLES.glob("*.yaml"))
        message = f"no manifest for {title!r}. Available: {', '.join(available) or 'none'}"
        raise HostlabError(message)
    return path


def cmd_validate(args: argparse.Namespace) -> int:
    manifest = load_manifest(_manifest_path(args.title))
    print(f"{manifest.id}: manifest satisfies the title contract")
    print(f"  ports    {', '.join(f'{p.number}/{p.protocol}' for p in manifest.ports)}")
    print(f"  stop     {manifest.stop.signal}, up to {manifest.stop.grace_seconds}s")
    print(f"  admin    {'none' if manifest.admin is None else manifest.admin.kind}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    manifest = load_manifest(_manifest_path(args.title))
    instance = load_instance(Path(args.instance))
    spec = render(manifest, instance.settings, instance.deployment)

    print(f"{manifest.name}: this configuration is accepted\n")
    for line in describe(spec):
        print(f"  {line}")
    return 0


def cmd_compose(args: argparse.Namespace) -> int:
    manifest = load_manifest(_manifest_path(args.title))
    instance = load_instance(Path(args.instance))
    # Rendering runs every refusal, so `compose` cannot produce a file for a
    # configuration `plan` would have rejected.
    spec = render(manifest, instance.settings, instance.deployment)

    document = render_compose(spec, instance.placeholders)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document, encoding="utf-8")

    print(f"wrote {out}")
    print(f"  docker compose --env-file deploy/.env -f {out} up -d")
    return 0


def _repository(args: argparse.Namespace) -> Repository:
    location = args.repo or os.environ.get("RESTIC_REPOSITORY")
    if not location:
        message = (
            "no restic repository given. Pass --repo or set RESTIC_REPOSITORY, "
            "which deploy/.env.example documents"
        )
        raise HostlabError(message)
    return Repository(location=location)


def cmd_state(args: argparse.Namespace) -> int:
    manifest = load_manifest(_manifest_path(args.title))
    inspection = inspect_state(manifest, Path(args.state_dir))

    if not inspection.worlds:
        print(f"no state found under {args.state_dir}")
        return 0

    for world in inspection.worlds:
        newest = world.newest_complete
        if newest is None:
            print(f"  {world.name}: NO COMPLETE GENERATION")
            continue
        age = newest.age()
        print(f"  {world.name}: generation {newest.number}, completed {age} ago")

    # Liveness and durability are different claims, and this is the second one.
    # always-on-operation.md ranks it above the first, against the usual
    # instinct, because the failure it catches does not report itself.
    stalest = inspection.stalest_age()
    limit = manifest.health.durability.max_stale_seconds
    if stalest is not None and stalest.total_seconds() > limit:
        print(
            f"\nSTALE: nothing has saved for {stalest}, and the manifest allows "
            f"{limit}s. A server that is running and not saving is the failure "
            "this project exists to catch."
        )
        return 1

    return 0 if inspection.is_consistent else 1


def cmd_backup(args: argparse.Namespace) -> int:
    manifest = load_manifest(_manifest_path(args.title))
    print(
        back_up(
            manifest,
            Path(args.state_dir),
            _repository(args),
            require_consistency=not args.even_if_damaged,
        )
    )
    # Verify after copying, per ADR 0003, rather than discovering a broken
    # repository at the moment it is needed.
    verify(_repository(args))
    print("repository verified")
    return 0


def cmd_snapshots(args: argparse.Namespace) -> int:
    print(snapshots(_repository(args), args.title))
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    manifest = load_manifest(_manifest_path(args.title))
    inspection = restore(_repository(args), args.snapshot, Path(args.target), manifest)

    if inspection is None:
        return 0

    print(f"restored to {args.target}")
    for world in inspection.worlds:
        newest = world.newest_complete
        state = f"generation {newest.number}" if newest else "NO COMPLETE GENERATION"
        print(f"  {world.name}: {state}")

    if not inspection.is_consistent:
        print(
            "\nThis restore would not have brought the world back. That is the "
            "drill working: you found out now rather than after losing the host."
        )
        return 1

    print(
        "\nNow do the half no tool can do: start a server on it, connect, and "
        "check the buildings, the chests and the explored map. A world that "
        "loads is not necessarily a world that is whole. "
        "See docs/save-data-and-backups.md."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hostlab", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="check a title manifest on its own")
    validate.add_argument("title")
    validate.set_defaults(handler=cmd_validate)

    plan = sub.add_parser("plan", help="check a manifest against an instance, writing nothing")
    plan.add_argument("title")
    plan.add_argument("--instance", required=True, help="path to the instance file")
    plan.set_defaults(handler=cmd_plan)

    compose = sub.add_parser("compose", help="write the compose file for an instance")
    compose.add_argument("title")
    compose.add_argument("--instance", required=True)
    compose.add_argument("--out", required=True)
    compose.set_defaults(handler=cmd_compose)

    state = sub.add_parser("state", help="is the state consistent, and is it advancing")
    state.add_argument("title")
    state.add_argument("--state-dir", required=True)
    state.set_defaults(handler=cmd_state)

    backup = sub.add_parser("backup", help="copy the state directory off the host")
    backup.add_argument("title")
    backup.add_argument("--state-dir", required=True)
    backup.add_argument("--repo", help="restic repository, or set RESTIC_REPOSITORY")
    backup.add_argument(
        "--even-if-damaged",
        action="store_true",
        help=(
            "copy without the consistency check. For the one case it is right: "
            "a state directory that is already damaged is the one you most want "
            "a copy of before touching it"
        ),
    )
    backup.set_defaults(handler=cmd_backup)

    listing = sub.add_parser("snapshots", help="what is in the repository")
    listing.add_argument("title")
    listing.add_argument("--repo")
    listing.set_defaults(handler=cmd_snapshots)

    bring_back = sub.add_parser("restore", help="restore a snapshot somewhere else")
    bring_back.add_argument("title")
    bring_back.add_argument("--snapshot", default="latest")
    bring_back.add_argument("--target", required=True)
    bring_back.add_argument("--repo")
    bring_back.set_defaults(handler=cmd_restore)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: int = args.handler(args)
    except HostlabError as error:
        # A refusal is a designed outcome, not a crash. Printing a traceback
        # here would bury the explanation the refusal exists to carry.
        print(f"\nrefused: {error}", file=sys.stderr)
        return 2
    return result


if __name__ == "__main__":
    sys.exit(main())
