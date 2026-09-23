"""The platform's command line.

Three commands, in increasing order of what they touch:

  validate   the manifest alone, no instance, no environment
  plan       manifest plus this instance, with every refusal applied
  compose    the same, and writes the compose file

`plan` exists so the refusals can be run without producing anything. The whole
argument of `render.py` is that the failures it catches are silent ones, and a
check that is only reachable by deploying is a check people skip.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hostlab.compose import render_compose
from hostlab.errors import HostlabError
from hostlab.manifest import load_manifest
from hostlab.render import describe, render
from hostlab.settings import load_instance

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
