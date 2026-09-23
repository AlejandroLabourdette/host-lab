# The Valheim server image

One image per title, with the server **baked in at build time**, per
[ADR 0008](../../docs/decisions/0008-implementation-stack-and-manifest-syntax.md).

## Why the server is in the image

[ADR 0004](../../docs/decisions/0004-run-game-servers-as-containers.md) consequence 5 says "image
tags become the version-pinning mechanism, which makes binary rollback easy", and
[`always-on-operation.md`](../../docs/always-on-operation.md) leans on it again: rolling back
binaries is trivial with containers and awkward with SteamCMD.

**That is only true if the server is in the image.** A container that runs SteamCMD at startup has
a tag that pins the wrapper and not the game, so two containers on the same tag can be running
different builds, and "roll back to the previous tag" does nothing.

One honest nuance: SteamCMD installs whatever is current, so **a tag records a version rather than
requesting one.** You cannot build yesterday's image today. What you can do is keep the image you
built yesterday, and that is what a rollback actually needs. The exact Steam build is recoverable
from the image itself:

```
docker run --rm --entrypoint cat hostlab/valheim:<tag> \
  /opt/valheim/steamapps/appmanifest_896660.acf | grep buildid
```

## Build

```
docker build --platform linux/amd64 -t hostlab/valheim:1.0.15 images/valheim
```

`--platform linux/amd64` is not optional. There is no ARM build of this server, which is the same
fact that made [ADR 0001](../../docs/decisions/0001-host-on-an-owned-always-on-x86-machine.md)
reject a single-board computer, and `titles/valheim.yaml` declares it as `runtime.platform`.

Tag with the Valheim version you observe after building, from the `buildid` command above or from
[Iron Gate's news index](https://www.valheimgame.com/news/). **Do not tag `latest`**; ADR 0004
consequence 5 calls that a dangerous tag to run, precisely because it defeats the rollback this
whole arrangement is for.

## What the image does that a naive one would not

| | Why |
|---|---|
| The server is **PID 1**, via `exec` | Valheim saves cleanly on SIGINT. A shell that forwards signals is a shell that can fail to |
| `STOPSIGNAL SIGINT` | Docker's default is SIGTERM, which is unreliable here. SIGKILL loses everything since the last autosave |
| `EXPOSE 2456/udp 2457/udp` | Both are UDP. Published as TCP, the server looks correct and is unreachable |
| Runs as a fixed **uid/gid 10000** | Fixed because the state volume outlives the image and its ownership must keep matching. High so it cannot collide with a host user on a machine that is also somebody's desktop |
| Permissions fixed **before** start, files and directories separately | See below |
| Two build stages | SteamCMD is a 32-bit binary and needs i386 libraries. None of that belongs in the image that runs the game |
| `SteamAppId=892970` | The *game's* app id, not the server's. Iron Gate's own launch script sets it and the server misbehaves without it |
| No configuration written to disk | `start_server.sh` is overwritten by every update, which is the `config_hazard` the manifest declares. Configuration arrives as the container's command, so the trap is avoided structurally rather than by remembering a rule |

## Verifying this image, and what cannot be verified off the host

Split deliberately, because the two halves need different machines.

### What is checked on any machine, in the test suite

`tests/test_image_signals.py` builds a stub image from the **real** entrypoint and permission
scripts, with a stand-in for the game binary, and asserts the things that would fail silently:

| Checked | Because |
|---|---|
| `docker stop` delivers **SIGINT**, not SIGTERM | Docker's default is SIGTERM. The stub exits 1 on SIGTERM so the wrong path cannot pass quietly |
| The server is **PID 1** | A wrapper shell that forwards signals is one that can fail to |
| Privilege is dropped to 10000:10000 before start | |
| The stop completes well inside the timeout, exit 0 | A stop that times out and escalates to SIGKILL is a data-loss event that looks identical to a clean stop from outside |
| The unprivileged user can write to the state volume | The #802 failure mode, asserted by writing rather than by reading mode bits |

Measured 2026-09-22: SIGINT delivered, exit 0, stop completed in **0.28 s**, marker written to the
volume and owned by `valheim`.

`tests/test_image_permissions.py` covers `fix-permissions.sh` directly, with no Docker at all.

### What cannot be checked on an arm64 machine

**The SteamCMD fetch.** SteamCMD ships a 32-bit x86 client, and under x86-64 emulation on Apple
Silicon it crashes immediately and uploads a minidump rather than running. Other 32-bit binaries in
the same package do execute, so this is SteamCMD specifically and not a broken emulation layer or a
fault in this Dockerfile. Verified 2026-09-22.

The consequence is not subtle and is worth stating plainly: **`docker build` of this image has to
happen on an x86-64 machine**, which the host is. Everything above the fetch stage is exercised by
the stub image; the fetch stage, and the server actually starting, are host verifications.

### What only the host can answer

| Check | Where |
|---|---|
| The image builds, SteamCMD fetch included | The host |
| `ss -tulpn \| grep 245` shows 2456 and 2457 as **udp** | [`docs/titles/valheim.md`](../../docs/titles/valheim.md) rung 1 |
| A stop produces a **fresh `.ok` marker** for a new generation | The other half of the SIGINT claim, and the half Iron Gate owns |

## `fix-permissions.sh`, and the incident behind it

[valheim-server-docker issue #802](https://github.com/community-valheim-tools/valheim-server-docker/issues/802)
is the most specific failure in this project's research. After Valheim 1.0 turned each world into a
directory, a permission-fixing routine applied `0644` to everything under `worlds_local/`, the new
per-world directories included. **A directory without the execute bit cannot have entries created
in it, so every autosave failed, silently, while the container reported healthy.**

ADR 0004 consequence 3 turns that into a standing obligation: any permissions handling must
distinguish files from directories. The script does, in two passes, and the order is not
interchangeable:

1. **Repair traversal**, with `chmod -R u+rwX,go+rX`. The capital `X` grants execute to directories
   and leaves data files alone.
2. **Normalise**, with two `find` passes to exact `0755` and `0644`, since pass 1 only ever adds
   permissions and cannot bring an over-permissive file back down.

**Writing this found a real bug, and it is worth recording because it is the same bug class.** The
first version used `find -type d -exec chmod 0755` as the repair. That cannot work: find reads a
directory's contents *before* running any action on it, so on a tree in the #802 state it exits
with `Permission denied` having repaired nothing. **The recovery script could not recover from the
state it existed to recover from.** `chmod -R` can, because it applies the mode to a directory and
then descends into it.

The script is deliberately a separate file rather than inline in the entrypoint, so it can be
tested without Docker and without the game. See `tests/test_image_permissions.py`, which reproduces
the #802 tree and asserts that a new generation can actually be written afterwards, rather than
only that the mode bits look right.
