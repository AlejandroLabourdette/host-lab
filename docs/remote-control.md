# Friends starting and stopping the server

> Status: accepted
> Last reviewed: 2026-09-22

This is the requirement the project was started for. The original complaint was not "my server is
slow", it was that **nobody can play unless one particular person is at their computer.** Moving
the server to an always-on machine solves half of that. If the owner is still the only person who
can start it, the other half has not been solved: the bottleneck has just changed name.

Goal G3 in [`scope-and-goals.md`](scope-and-goals.md). The decision is recorded in
[ADR 0006](decisions/0006-give-friends-a-control-plane.md).

**This document specifies requirements. It does not build anything**, per the scope of this
repository.

## First: is this needed at all?

Worth asking honestly, because the cheapest control plane is none.

The host is always on. The game server is a supervised container that restarts on crash and boots
with the machine ([`always-on-operation.md`](always-on-operation.md)). So the server is simply
*always running*, and there is nothing for anyone to start.

For a single Valheim world and a group of friends, **that is very likely the right answer, and it
should be the starting point.** An idle Valheim server costs a few watts and some RAM on a machine
that is already powered. Building a control plane to start something that should never be stopped
is machinery in search of a problem.

Four things change that, and they are the real requirements:

1. **Several titles, one machine.** When the group moves to Palworld for a month, the Valheim
   server is consuming RAM and CPU for nobody. Now "stop that, start this" is a genuine operation,
   and asking the owner every time reintroduces the original problem.
2. **Something goes wrong while the owner is away.** A hung server, a stuck world, a player who
   needs a restart. Today that means waiting for one person.
3. **Crossplay's join code.** If the group is on crossplay, the code **regenerates on every server
   restart** ([`networking.md`](networking.md)). Someone who was not present for the restart cannot
   connect and cannot find out the new code. This is a control-plane problem created by a
   networking decision, and it is not optional if crossplay is in use.
4. **Nobody knows whether it is up.** The most common question in practice is not "start it", it is
   "is it working, or is it me?"

Those four split evenly: **1 and 2 need authority over the server; 3 and 4 only need information
about it.** Two and two.

The even split is less striking than a landslide would be, but it still points somewhere, because
the two halves are not equally expensive. Needs 3 and 4 are answered by publishing what the host
already knows, which grants nobody any power and cannot damage anything. Needs 1 and 2 require
handing a destructive operation to people who cannot see what it does, and with it identity,
authorization and an audit trail.

So the recommendation does not rest on the count. It rests on that asymmetry, plus one observation
about timing: **need 4 is live today and need 1 is not.** Nobody is currently fighting over the
machine, because there is one title on it. Half the value is available immediately at almost no
cost and no risk, and the expensive half has no trigger yet.

## What "start" and "stop" mean here

Three different things get called the same word, and they have very different costs:

| Layer | Start time | Notes |
|---|---|---|
| **The machine** | Minutes | Only relevant if the host sleeps. It should not: [ADR 0001](decisions/0001-host-on-an-owned-always-on-x86-machine.md) assumes always-on. Wake-on-LAN exists, is fiddly, and solves a problem we do not have. |
| **The game server process** | Seconds to a minute | **This is the one that matters.** Container start plus world load. |
| **The world** | Instant | There is nothing to start. The world is a directory. |

So the control plane operates on **containers**, not machines and not worlds. That also means it is
title-agnostic for free, which matters because two of the five titles surveyed in
[`platform-architecture.md`](platform-architecture.md) expose no game-level control interface at
all. The runtime is the only uniform control surface available.

## Required capabilities

Ordered by value delivered per unit of risk. Nothing below the line is needed to solve the original
problem.

| # | Capability | Who | Risk | Why |
|---|---|---|---|---|
| 1 | **Is it up, and how do I connect** | Everyone | None. Read-only | The most frequently asked question. Answers it without anyone being present |
| 2 | **The current crossplay join code** | Everyone | Low. It is a shared secret the group already has | Mandatory if crossplay is used, because restarts invalidate it |
| 3 | **Who is online** | Everyone | None | Answers "is anyone playing" without joining to find out |
| 4 | **Start a server** | Friends | Low. Worst case is a server running that nobody wanted | The actual ask |
| 5 | **Stop a server** | Friends | **High. A bad stop costs the world** | Only needed to free resources for another title |
| 6 | **Restart** | Friends | High, same reason | Unsticks things without the owner |
| 7 | **Last backup time and result** | Everyone | None | Makes the invisible visible. See [`save-data-and-backups.md`](save-data-and-backups.md) |
| --- | --- | --- | --- | --- |
| 8 | Trigger a backup | Owner | Low | Before something risky |
| 9 | Switch active title | Friends | Composite of 4 and 5 | The multi-game case |
| 10 | Disk usage | Owner | None | Slow-moving, an alert is better |

**Capabilities 1 to 3 have essentially no downside and address most of the actual pain.** Build
those first. Capability 5 is the dangerous one and deserves its own section.

## Stop is the dangerous one

Every other capability is recoverable. Stop is not.

A Valheim server killed rather than stopped loses everything since the last autosave, up to 30
minutes by default, and the graceful path is a specific signal with a generous timeout
([`always-on-operation.md`](always-on-operation.md)). A control plane that exposes a "stop" button
is handing a data-destroying operation to people who cannot see what it does.

Non-negotiable rules for any stop that is ever built:

1. **It must use the title's graceful stop and wait for it.** The manifest's `stop` field
   ([`platform-architecture.md`](platform-architecture.md)) is the authority. A stop that times out
   and escalates to a kill must be treated as an incident and reported, not silently completed.
2. **It must refuse while players are connected**, or at minimum require a confirmation that says
   how many people are about to be disconnected. Someone freeing up RAM should not end a raid.
3. **It must trigger or confirm a backup**, so the worst case is a rollback rather than a loss.
4. **It must be attributable.** Who stopped it, and when.
5. **The interface must not make stop as easy as start.** They look symmetrical and are not.

## Identity and authorization

**A shared password is the wrong answer**, and it is the answer everyone reaches for first. It ends
up in a group chat, it is never rotated, it cannot be revoked for one person, and it makes every
action anonymous, which removes the accountability that makes item 4 above work at all.

Three realistic options that provide real identity:

### Discord identity

The group almost certainly already has a Discord server, and it is where "is it up?" is already
being asked.

- **For:** zero new accounts, zero installs. Identity already exists and is already managed. A bot
  can *announce* things, which is what a rotating join code needs. Role-based permissions come free
  and are already understood by everyone.
- **Against:** a third-party dependency for operating your own machine. A bot needs a token, and a
  leaked token is an unauthenticated control plane. Chat is a poor medium for anything with
  confirmations.
- **Verdict:** the best fit for capabilities 1 to 4, and the natural home for join-code
  announcements.

### Overlay VPN device identity

If the group already uses Tailscale for reachability ([`networking.md`](networking.md)), every
device on it is already authenticated, and a small web page can be served only on that network.

- **For:** strong identity for free. The control plane is unreachable from the public internet by
  construction, which removes a whole class of risk. A real UI, so confirmations work properly.
- **Against:** **only works if everyone is already on the overlay.** If the group is not using it
  for reachability, this asks friends to install a VPN so they can press a button, which is a bad
  trade. And it excludes console players entirely.
- **Verdict:** excellent when the overlay already exists for other reasons. Not a reason to adopt
  one.

### A web app with its own accounts

- **For:** full control over the model and the UI. No third-party dependency.
- **Against:** now you are running an authentication system, and exposing it to the internet. It is
  the most work and the largest attack surface, for a group of maybe six people.
- **Verdict:** hardest to justify at this scale. This is where an existing panel
  ([ADR 0004](decisions/0004-run-game-servers-as-containers.md) option D) earns its keep, because
  users and permissions are what panels are actually good at.

### Rules regardless of choice

- **Two roles, not one.** Friends get every capability the table above assigns to "Everyone" or
  "Friends" - 1 to 7 and 9. The owner gets those plus 8 and 10. Matching
  [`scope-and-goals.md`](scope-and-goals.md)'s two actors.
- **Never expose unauthenticated control to the internet.** An open start/stop endpoint is remote
  code execution with extra steps.
- **Log every action with who and when.** Small, cheap, and the only way to answer "why did it
  restart at 3am".
- **Rate limit.** Not against attackers; against a friend clicking restart four times because
  nothing appeared to happen.
- **Revocation must be possible for one person** without disrupting everyone else. This is the
  concrete thing a shared password cannot do.

## The crossplay join code

If `-crossplay` is in use, this is not a nice-to-have. The code **regenerates on every server
restart**, and restarts happen for reasons nobody chose: a crash, a scheduled restart, an update.

The failure is specific and will happen: a friend sits down to play, has yesterday's code, and
cannot connect. The information they need exists on the host and nowhere they can reach. The owner
is the only bridge, which is the original problem in miniature.

What the control plane must do:

1. **Read the current code** from the server, and know when it changed.
2. **Publish it** where friends already look, without anyone being asked.
3. **Announce it on change**, because a restart silently invalidates what everyone has.

This is why [ADR 0002](decisions/0002-reach-the-server-from-the-internet.md) records that choosing
crossplay creates a control-plane obligation. It is a networking decision with an operational
tail, and it is easy to accept without noticing the cost.

**A second-order effect worth stating:** if the code is announced automatically, scheduled restarts
become harmless. If it is not, a nightly restart quietly locks out everyone who was not watching.
The two decisions are coupled.

## Interface options

| Option | Effort | Friends install | Identity | Fits |
|---|---|---|---|---|
| **Nothing. Always-on, plus a status page** | Lowest | Nothing | None needed for read-only | One title, no stop needed |
| **Discord bot** | Low | Nothing | Reuses Discord | Status, join code, start |
| **Web page on the overlay VPN** | Medium | Only if not already on it | Device identity | Groups already using an overlay |
| **Existing panel (Pterodactyl, PufferPanel, Crafty)** | Medium to set up, low to build | Nothing | Its own users | Many titles, several operators |
| **Custom web app** | Highest | Nothing | Build it | Hard to justify here |

Two observations worth more than the table:

**A panel is a real option and should not be dismissed for being unfashionable.** It solves users,
permissions, a console and start/stop, and it is the right answer if the control plane grows
demanding. [ADR 0004](decisions/0004-run-game-servers-as-containers.md) rejected it as the
*foundation*, which is a different question from whether it is a good control plane.

**The status page and the Discord bot are not alternatives, they are the same thing with two front
ends.** Both need a component that knows the state of each container and can publish it. Build that
once; the front end is thin.

## What would have to exist

Requirements for the implementation ticket. Deliberately a list of obligations, not a design.

**A state reader.** Knows, per title: running or not, uptime, players connected, current join code,
last backup time and result, disk used. Read-only, no authority to change anything. Everything
except the game-level bits comes from the container runtime, which is why this works uniformly
across titles.

**An action executor.** Start, stop, restart, one container at a time. Must honour the manifest's
graceful stop, wait for completion, refuse or confirm when players are connected, and report a
timeout escalation as an incident. This is the only component with authority, and it should be as
small as it can possibly be.

**An identity boundary.** Maps a person to a role, and a role to a set of allowed actions.
Per-person revocable. Logs every attempt, allowed or denied.

**A publisher.** Pushes changes to where friends already are: join code changed, server started or
stopped and by whom, backup failed. Push, not poll, because the whole point is that nobody should
have to check.

### Explicit non-requirements

- **In-game warnings before a restart.** Valheim has no admin channel
  ([`platform-architecture.md`](platform-architecture.md)). Announce out of band instead.
- **Kicking or banning from the control plane.** Same reason. That is editing the permission lists
  and restarting.
- **A console.** Valheim has none to expose.
- **Editing world settings.** Rare, risky, and the owner's job.
- **Mod management.** Out of scope.

## The tooling, as built

Stage 1 only. **Nothing in it can start, stop or restart a server**, and that
is a property of the code rather than a promise: `hostlab` has no such command,
and a test parses the reader's source to assert it never invokes one.

| Command | Does |
|---|---|
| `hostlab status <title> --container <name> --state-dir <dir>` | The state reader. Prints the report and exits non-zero if the server is unhealthy |
| `hostlab publish <title> ...` | The same report, sent to Telegram |

The report answers, in this order:

```
Valheim: online, up 3h
players: 3/10
saves: ok (Midgard gen 7)
backup: 6h ago
disk free: 355.2 GB
```

**The order is deliberate and it is not the conventional one.** Liveness is
listed after durability because it is the least valuable check here: a server
that is down reports itself within minutes, because somebody complains. The
failure that costs a world is the quiet one, and it looks like this:

```
Valheim: online, up 21s
saves: STALE, nothing written for 9h
```

Up, healthy by every conventional measure, and not saving. That is
[issue #802](https://github.com/community-valheim-tools/valheim-server-docker/issues/802)
exactly, and the reason the save state is read from the filesystem rather than
inferred from the game.

Three more behaviours worth knowing:

- **A query failure is not reported as "down".** If the game stops answering
  A2S the report says `players: unknown` and still reports the save state.
  A health check coupled to a game's query protocol is coupled to that game's
  releases, which is what broke LinuxGSM's Valheim monitor; the durability half
  reads the filesystem and no game update can break it.
- **A crash loop is reported even while the server is up**, because a server
  that restarted eleven times overnight is broken. Compose cannot express a
  restart rate cap outside Swarm, so the reader carries it.
- **The bot never reads its own inbox.** No `getUpdates`, no webhook, no
  commands. One standing message is edited rather than a new one sent each
  cycle, because a channel full of "still up" teaches people to mute it.

### What this costs to attack

Worth stating, because it is the answer to "is a bot token safe in a group
chat's infrastructure". A leaked token lets an attacker **edit a status
message**. It does not let them touch the server, because nothing in stage 1
can. Stage 2 changes that, and it must add identity, authorization and an audit
trail in the same change.

## Recommendation

**Start with always-on and read-only status. Add control only when a second title makes it real.**

1. **Now:** run the server always-on. Publish status, connection details, and the join code if
   crossplay is used, to where the group already talks. This removes most of the actual pain with
   no authority granted to anyone and nothing that can destroy a world.
2. **When a second title arrives:** add start and stop, with Discord identity or an overlay-VPN
   page depending on what the group already uses. Apply every rule in
   [Stop is the dangerous one](#stop-is-the-dangerous-one).
3. **Only if it outgrows that:** adopt a panel rather than growing a custom one.

This ordering follows from the project's guidance to take the simplest direct path first and add
machinery when a concrete need appears. The concrete need for *status* exists today. The concrete
need for *stop* does not exist until there is a second title competing for the machine, and
building the dangerous capability before it is needed is how a world gets lost to a feature nobody
was using.
