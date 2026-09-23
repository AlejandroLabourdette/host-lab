# 0004 - Run game servers as containers

> Status: accepted
> Date: 2026-09-22

## Context

Something has to keep the game server process running, restart it when it dies, apply updates, and
do all of that for a second and third title later without the arrangement collapsing into a pile of
bespoke setups.

The host runs Linux and already has Docker available. That fact is recorded here because it is
relevant, but it is deliberately **not** the argument: the project's standing guidance is to weigh
quality, simplicity, robustness and long-term maintainability over what is cheapest to set up
today. "It is already installed" is a tiebreak, not a reason.

Four options were compared in detail in [`always-on-operation.md`](../always-on-operation.md). This
records the decision and the costs accepted with it.

## Options considered

### A. Bare systemd unit

Process on the host, supervised by systemd, `Restart=on-failure`, `KillSignal=SIGINT`.

- **For:** no extra layer. Logs in the journal. Debugging is direct because the process is just a
  process. Cheapest possible mental model.
- **Against:** every title's dependencies land in the host filesystem and eventually conflict. No
  isolation, so a compromised server is a compromised host user. The host becomes an
  un-reproducible artifact that nobody wrote down, which matters a great deal for a machine whose
  whole job is to still be working in two years.

### B. Containers (chosen)

One image per title, an explicit state volume, a restart policy.

- **For:** dependency isolation, so incompatible titles coexist. The host stays clean and
  rebuildable. Resource limits and log handling are built in. **Persistent state is forced to be
  explicit**, because anything not on a volume does not survive the next image pull. An image tag is
  a version, which makes rolling back a binary trivial rather than awkward. And the per-title shape
  is nearly identical, which is what makes a generic platform possible.
- **Against:** a real layer of indirection with its own footguns, and they are unforgiving in
  exactly this domain. Publishing a port without `/udp` yields TCP and a silently dead server. A
  bind mount pointing at the wrong path yields an empty world rather than an error. Host-container
  file ownership is a recurring source of breakage, demonstrated by
  [issue #802](https://github.com/community-valheim-tools/valheim-server-docker/issues/802), where a
  permissions bug silently broke every autosave while the container reported healthy.

### C. LinuxGSM

A mature, purpose-built shell framework, with Valheim supported as `vhserver`.

- **For:** genuinely built for this problem. Install, update, monitor, backup and alerting already
  exist and are better than a first attempt would be. Covers many titles. Its `monitor` both checks
  the process and queries the server, which is closer to a correct health check than most.
- **Against:** no isolation, so it inherits A's dependency problem. Its query-based monitoring has
  broken against Valheim updates more than once (LinuxGSM issues
  [#4060](https://github.com/GameServerManagers/LinuxGSM/issues/4060),
  [#4821](https://github.com/GameServerManagers/LinuxGSM/issues/4821), accessed 2026-09-22).
- **Honest assessment:** this was the closest competitor. If the goal were only "run Valheim
  reliably", LinuxGSM would probably win on the grounds that it already exists and is maintained.
  It loses on isolation, which is the axis that matters most once a second title arrives.

### D. A full panel (Pterodactyl, PufferPanel, Crafty)

- **For:** solves supervision and the friend-facing control plane in one move.
- **Against:** a panel, a database, a daemon and a web front end to patch and defend, for a handful
  of servers. It also imposes its own model of a game server, which the platform would be built
  inside rather than on top of.
- **Verdict:** premature as a foundation. Reconsidered as a control-plane option in
  [`remote-control.md`](../remote-control.md), which is the problem it is actually good at.

## Decision

**Run each game server as a container, with its persistent state on an explicit, deliberately
placed volume.**

The deciding argument is **the second title**. Every option here can run Valheim. Only B and D make
running Valheim *and* Minecraft *and* Palworld on one machine a configuration exercise instead of a
dependency negotiation, and D brings a web stack along with it. Goal G5 in
[`scope-and-goals.md`](../scope-and-goals.md) says adding a game should be a configuration change
rather than a redesign, and the container boundary is what makes that true.

The second argument is that **the host stays disposable.** The machine is domestic hardware that
will eventually be reinstalled, upgraded or replaced. An arrangement where recovery means restoring
a volume and pulling an image is meaningfully more robust than one where it means reconstructing an
install by memory.

Docker already being present is noted, and is not the reason.

## Consequences

1. **The `/udp` footgun is now ours.** Publishing Valheim's ports as TCP produces a server that
   looks correct and is unreachable. This is called out in
   [`networking.md`](../networking.md) and is a required item in the verification ladder.
2. **Graceful stop must be configured explicitly.** Docker's defaults - SIGTERM and a 10 second
   timeout - are both wrong for this workload. SIGINT and a generous timeout are mandatory, and
   must be tested rather than assumed. See [`always-on-operation.md`](../always-on-operation.md).
3. **File ownership between host and container is a standing hazard**, and it has already destroyed
   autosaves in the most widely used Valheim container. Any permissions handling must distinguish
   files from directories.
4. **Anything not on a volume is ephemeral.** This is the point, but it means the save directory,
   the permission lists and the server configuration must all be deliberately placed.
5. **Image tags become the version-pinning mechanism**, which makes binary rollback easy and makes
   "latest" a dangerous tag to run in production.
6. **We do not get LinuxGSM's monitoring for free**, and must build the equivalent. Its Valheim
   query-check breakages are a warning that game-specific health checks are fragile across updates,
   which argues for checking that saves are advancing rather than relying only on a game query.

## Revisit if

- The control plane in [`remote-control.md`](../remote-control.md) grows demanding enough that a panel's user and
  permission model would be a net saving rather than a net cost. At that point D stops being
  premature.
- Podman's rootless model proves materially safer here. The decision is "containers", not
  "Docker specifically", and the runtime is a smaller decision that can move on its own.
