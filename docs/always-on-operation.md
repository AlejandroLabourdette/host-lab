# Keeping it always on

> Status: accepted
> Last reviewed: 2026-09-22

The point of this project is that nobody has to be at a computer for the world to exist. That makes
"always on" a requirement rather than a nice property, and it is made of three separate things that
are easy to conflate:

1. **The machine stays up**, and comes back by itself when it does not.
2. **The process stays up**, and restarts when it dies.
3. **Updates get applied without damaging the world.**

The third is where self-hosted game servers actually die. A crash costs minutes. A bad update or a
hard kill during a save costs the world.

The supervision decision is recorded in
[ADR 0004](decisions/0004-run-game-servers-as-containers.md).

## Before any of this: graceful stop

This section is first because it is the single highest-consequence setting in the whole project,
and because every supervision option below gets it wrong by default.

**Valheim's dedicated server saves cleanly when it receives SIGINT**, which is what Ctrl+C sends.
Iron Gate's own guidance is explicit about stopping it that way: "It is important that you close it
by pressing CTRL+C in the Command-window. If you close it by clicking the X in the window frame the
Server may keep running in the background."
([Iron Gate, A Guide to Dedicated Servers](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/),
2024-04-11, accessed 2026-09-22.)

What follows from that, and the part nobody writes down:

| Signal | What happens |
|---|---|
| `SIGINT` | Clean shutdown. The server flushes current world state to disk and exits. |
| `SIGTERM` | Unreliable. Community tooling consistently works around it rather than depending on it, which is why the standard systemd recipe sets `KillSignal=SIGINT` explicitly. |
| `SIGKILL` (`kill -9`) | No save at all. Everything since the last autosave is gone: up to 30 minutes by default. |

Source for the SIGINT/SIGTERM distinction: community server tooling and the widely circulated
systemd recipe ([gist](https://gist.github.com/cnrat/3605f9892ec535297030fc173d180651), accessed
2026-09-22). This is a **secondary source**. Iron Gate documents the Ctrl+C behaviour but not the
signal semantics, so the SIGTERM caveat is observed practice rather than specification. Treat it as
a reason to configure SIGINT deliberately rather than to rely on SIGTERM working.

**The two defaults that will eat the world:**

- **Docker sends SIGTERM and waits 10 seconds**, then SIGKILL. Both halves are wrong here: the
  wrong signal, and a timeout shorter than a large world takes to write. The reference container
  runs with `--stop-timeout 120` for exactly this reason
  ([valheim-server-docker](https://github.com/community-valheim-tools/valheim-server-docker), accessed
  2026-09-22).
- **systemd sends SIGTERM and waits 90 seconds**, then SIGKILL. Better on the timeout, still the
  wrong signal.

So whatever supervisor is chosen, two things must be set explicitly and verified:

> **Send SIGINT. Allow enough time to finish writing. Then confirm it actually worked** by stopping
> the server and checking that the world folder's newest generation carries a fresh `.ok` marker
> (see [`save-data-and-backups.md`](save-data-and-backups.md)).

A stop procedure nobody has tested is a data-loss incident waiting for a reboot. And because the
control plane described in [`remote-control.md`](remote-control.md) will let friends stop the server, this constraint is
inherited by every "stop" button that ever gets built: a stop that is not graceful is not a stop.

## The machine stays up

A home PC is not a server, and the gap is mostly in what happens when something interrupts it.

- **Power-on after AC loss.** Set the BIOS/UEFI option so the machine powers itself back on when
  power returns. Out of the box most desktops stay off, which means one brief power cut ends the
  service until somebody walks over and presses a button: exactly the human dependency this project
  removes. Check this early, because it is free and it is invisible until it matters.
- **Boot without a display, keyboard or a person.** Some boards halt on boot errors waiting for F1.
  Test a cold boot with nothing attached before declaring the host ready.
- **Unattended OS updates.** Security updates should apply automatically. Automatic *reboots* need
  a decision: overnight is right, mid-raid is not. Pick a window and make sure the server comes back
  after it, rather than discovering the machine has been sitting at a login prompt since Tuesday.
- **Disk health.** SMART monitoring with an alert. The disk holding the world is the single most
  consequential component in the building, and disks give warning if anyone is listening.
- **Thermals and dust.** A machine that idles at a desk for an hour a day behaves differently from
  one running a game simulation continuously for months.
- **Uninterruptible power.** Optional, and the cheapest real upgrade available. Even a small UPS
  turns most domestic power events into a non-event, and lets the host shut down *gracefully* on a
  long outage instead of losing whatever was unsaved.

## The process stays up

Four realistic supervisors. All of them restart a crashed process; they differ in everything else.

### Bare systemd unit

The server runs directly on the host under a dedicated user, supervised by systemd with
`Restart=on-failure` and `KillSignal=SIGINT`.

- **For:** no extra layer at all. Logs land in the journal with everything else. Debugging is
  direct, because the process really is just a process. Resource limits are available through the
  usual cgroup directives. Start-up ordering and dependencies come free.
- **Against:** every title's dependencies land in the host's filesystem, and they conflict.
  Valheim needs specific library versions; a second game will want different ones. There is no
  meaningful isolation, so a compromised server is a compromised host user with the host's
  toolchain available. Rebuilding the host means reconstructing an install nobody wrote down.
- **Generalising to a second title:** poorly. Each new game means more host-level packages and a
  new bespoke unit.

### Containers (Docker or Podman)

Each server is an image with a declared state volume and a restart policy.

- **For:** dependencies are the image's problem, not the host's, so two titles with incompatible
  library requirements coexist without negotiation. The host stays clean and is rebuildable.
  Resource limits and log handling are built in. Persistent state is forced to be explicit, because
  anything not on a volume is gone on the next image pull, which is a *useful* constraint for a
  project whose whole purpose is not losing persistent state. The per-title shape is close to
  identical, which is exactly the abstraction
  [`platform-architecture.md`](platform-architecture.md) needs.
- **Against:** a real layer of indirection, and it is where the footguns live. Publishing a port
  without `/udp` gives you TCP and a silently dead server. A bind mount pointing at the wrong path
  produces an empty world. File ownership between host and container is a recurring source of
  breakage, and issue #802 in the reference container is a concrete case of it silently destroying
  every autosave. Image pulls are an update path that can move underneath you.
- **Generalising to a second title:** very well. This is the strongest argument.

### LinuxGSM

A mature shell framework for game servers, with Valheim supported as `vhserver`
([LinuxGSM](https://linuxgsm.com/servers/vhserver/), accessed 2026-09-22).

- **For:** purpose-built for exactly this problem. Install, update, monitor, backup and alerting are
  all there and did not have to be written. Covers many titles, so it generalises. `monitor` both
  checks the process and queries the server, then restarts and alerts, which is closer to the right
  health check than most alternatives manage.
- **Against:** no isolation, so it shares bare systemd's dependency problem. It is a layer with its
  own conventions and directory layout to learn. Its query-based monitoring has broken against a
  Valheim update at least once: LinuxGSM issue
  [#4821](https://github.com/GameServerManagers/LinuxGSM/issues/4821) (2025-09-09, accessed
  2026-09-22), "After Valheim Update LGSM 'monitor' command no longer able to detect if Valheim is
  up". One incident is not a pattern, and it is not much of a knock on the project. It is worth
  recording because it is a concrete instance of a general hazard: **a health check that depends on
  a game's query protocol is coupled to that game's releases**, which argues for also checking
  something the game cannot break, such as whether saves are advancing.
- **Verdict:** the strongest option if the platform were only ever going to be a thin wrapper.

### A full panel (Pterodactyl, PufferPanel, Crafty)

A control-plane product that runs game servers in containers and exposes a web UI.

- **For:** solves the friend-facing control problem in the same move, with users, permissions and a
  console. Pterodactyl runs servers in isolated Docker containers and is game-agnostic.
- **Against:** substantially more machinery than a handful of game servers warrants: a panel, a
  database, a daemon, a web front end, all of which need to be kept patched and are now part of the
  blast radius. It also imposes its own model of what a game server is, which the platform would
  then be built inside rather than on top of.
- **Verdict:** premature. It is the right answer later if the control plane grows demanding, and
  [`remote-control.md`](remote-control.md) revisits it as an option there rather than as the foundation.

### Comparison

| | systemd | Containers | LinuxGSM | Panel |
|---|---|---|---|---|
| Restart on crash | Yes | Yes | Yes | Yes |
| Dependency isolation | None | Strong | None | Strong |
| Host stays rebuildable | No | Yes | Partly | No |
| Second title is easy | No | Yes | Yes | Yes |
| Resource limits | Yes | Yes | Via systemd | Yes |
| Debugging | Easiest | Extra layer | Moderate | Hardest |
| Blast radius | Host user | Container | Host user | Panel plus containers |
| Update handling | Manual | Image or SteamCMD | Built in | Built in |
| New failure modes | Few | Mounts, UID, `/udp` | Query checks break | A whole web stack |

**The recommendation is containers**, argued in
[ADR 0004](decisions/0004-run-game-servers-as-containers.md). The short form: dependency isolation
and a rebuildable host are worth more here than the indirection costs, and the per-title uniformity
is the thing that makes a multi-game platform possible at all rather than a pile of bespoke setups.

## Restarts

**Restart on crash:** yes, with a backoff. An unconditional restart loop on a server that crashes
at start-up hammers the disk and buries the real error. Restart, but cap the rate and alert when
the cap is hit, because a server that restarted eleven times overnight is broken even though it is
currently running.

**Scheduled restarts:** a nightly restart is common practice for game servers and mostly papers
over memory growth. Worth having, with three conditions:

- **Skip it if players are connected.** The reference container's daily restart does exactly this.
- **Stop gracefully**, per the section above. A scheduled restart that hard-kills is a scheduled
  data-loss job.
- **Remember it rotates the crossplay join code.** If the group is on crossplay, an automatic 5am
  restart silently invalidates the code everyone has. Either publish the new one automatically or
  do not schedule restarts. See [`remote-control.md`](remote-control.md).

## Updates without losing the world

Updating is the most dangerous routine event in a server's life, because it combines a stop, a
binary change and possibly a save-format migration.

### Why lockstep makes this unavoidable

Valheim clients and servers must be on compatible versions. A player on an old client cannot join
an updated server, and a player on a new client cannot join a server that has not updated. Steam
updates clients automatically by default.

The consequence is a genuine dilemma with no free option:

- **Update the server automatically**, and it will occasionally update mid-session, or update to a
  version whose release has not reached every platform yet, locking out friends who have not
  patched.
- **Do not update the server automatically**, and the first friend whose Steam client auto-updates
  finds themselves unable to join a server that was working yesterday, with no warning.

Neither is safe. What resolves it is not picking a side but **controlling the timing**: update
deliberately, soon after a release, at a moment nobody is playing, with a snapshot taken first.
Automation here should mean "notice an update exists and tell me", not "apply it whenever".

This matters more than usual right now. Valheim reached 1.0 on 2026-09-09 and had shipped 1.0.15 by
2026-09-18 ([Iron Gate news](https://www.valheimgame.com/news/), accessed 2026-09-22): roughly
fifteen releases in nine days. Anything in this documentation tied to a specific version has a very
short shelf life.

### The procedure

1. **Announce it.** A group of friends will forgive downtime they knew about.
2. **Confirm nobody is connected.** Query the server rather than assuming.
3. **Stop gracefully.** SIGINT, and wait for it to finish. Do not proceed until the process is gone.
4. **Snapshot the world.** Not the game's rolling backup: a copy somewhere the update cannot reach.
   This is the step that makes everything after it reversible, and it is the step people skip.
   **On a major version, this is mandatory**, because format conversions are automatic and one-way
   (see [`save-data-and-backups.md`](save-data-and-backups.md)).
5. **Apply the update.** For a direct install, the same command that installed it:
   `steamcmd +force_install_dir /srv/valheim +login anonymous +app_update 896660 validate +quit`.
   For a container, pull a new image. `validate` re-checks files against Steam's manifest and is
   worth the extra seconds.
   **`+force_install_dir` is not optional and must come before `+login`.** Omit it and SteamCMD
   patches its own `steamapps` tree instead, leaving the real install on the old build. Nothing
   fails: step 7 passes because the old binary starts normally, and the problem surfaces days later
   as players on updated clients being unable to join.
6. **Preserve your settings.** Steam **overwrites `start_server.sh` on every update**. Any
   configuration living in that file is destroyed by the act of updating. This is a well-known trap
   and the reason launch parameters belong in a separate script, a unit file, or environment
   variables, never in the shipped one.
7. **Start it, and watch the first minutes.** Confirm the world loaded and is the right one, and
   that a save completes: a new generation with a fresh `.ok` marker. A server that starts is not
   yet a server that works.
8. **Have someone connect** before declaring it done.

### Rolling back

Know the answer before you need it. Rolling back is two independent things and both are needed:

- **The binaries.** SteamCMD will install the current version; pinning an older one is awkward.
  Containers make this trivial, because an image tag is a version - which is a real, concrete
  advantage of the container approach that is easy to overlook until the day it matters.
- **The world.** Restore the snapshot from step 4.

**The catch that makes step 4 non-negotiable:** if the update converted the save format, rolling
back the binaries alone does not work, because the old server cannot read the converted world. The
snapshot is the only path back. An update procedure without it is a one-way door you walk through
without noticing.

## Knowing it is alive

The failure this project most needs to detect is not "the server is down". Somebody will notice
that within minutes and complain. It is the quiet one: **the server is up and not saving.**

That exact failure is documented in
[valheim-server-docker issue #802](https://github.com/community-valheim-tools/valheim-server-docker/issues/802)
(accessed 2026-09-22): a permissions bug left the container healthy, the process running and every
autosave failing silently. Every liveness check in the world says that server is fine.

A minimum worth having, in order of value:

| Check | Catches | Why it matters |
|---|---|---|
| **The world is still saving** - newest generation and `.ok` marker advancing | Silent save failure, full disk, permissions | The one that protects the thing you care about |
| **Backups are completing, and are not empty** | A backup job that has been failing for weeks | An unchecked backup job is the classic false sense of security |
| Disk space on the save volume | Slow death as a world grows | Gives days of warning |
| Process alive and answering an A2S query | Crash, hang | Cheap, and catches the obvious case |
| Restart rate | A crash loop hiding behind an up-right-now status | A server that restarted eleven times overnight is broken |
| SMART status | Impending disk failure | The only warning you get |

Note the ordering. Conventional monitoring starts at "is the process up" and often stops there.
For this project that is the least valuable check on the list, because it is the failure that
reports itself. **Liveness and durability are different claims**, and only one of them is the
reason this project exists.

Alerting has to reach the owner without them looking, otherwise it is a dashboard nobody opens.
Where it goes is a control-plane question: see [`remote-control.md`](remote-control.md).
