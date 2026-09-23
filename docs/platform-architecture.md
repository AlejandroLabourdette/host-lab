# Platform architecture

> Status: accepted
> Last reviewed: 2026-09-22

The project is scoped as a generic multi-game platform with Valheim as the first concrete case
([`scope-and-goals.md`](scope-and-goals.md), goal G5). This document works out what "generic"
actually means here, and it does it from evidence rather than from intuition.

The decision is recorded in
[ADR 0005](decisions/0005-describe-titles-with-a-declarative-manifest.md).

## The trap this document exists to avoid

The obvious move is to design an elegant abstraction over "a game server" and then discover, on the
second title, that the abstraction fits nothing. Game servers look similar from a distance and
differ in exactly the places automation touches: how the binary is acquired, how it is configured,
what its save looks like, how you talk to it while it runs, and how it must be stopped.

So the method here is deliberately backwards. **First establish what five real titles actually do.
Then let the common parts fall out.** Anything that is not visible in the evidence table does not
go in the generic layer.

The second thing to avoid is building the abstraction now. This repository is documentation; the
implementation is a later ticket. The output here is a boundary and a contract, not a framework.

## The evidence

Five titles: Valheim in depth because it is the first case, and four the group might plausibly
play next. All accessed 2026-09-22, and sourced per title:

| Title | Source | Verified |
|---|---|---|
| Valheim | [Iron Gate](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/) and the [Valheim Wiki](https://valheim.weirdgloop.org/w/Dedicated_servers) | Yes, in depth. See [`titles/valheim.md`](titles/valheim.md) |
| Minecraft (Java) | [minecraft.wiki, Setting up a Java Edition server](https://minecraft.wiki/w/Tutorial:Setting_up_a_Java_Edition_server) | Yes |
| Satisfactory | [Official Satisfactory Wiki, Dedicated servers](https://satisfactory.wiki.gg/wiki/Dedicated_servers) | Yes |
| Palworld | [Pocketpair, Dedicated Server Guide](https://docs.palworldgame.com/dedicated-server-guide) | **No.** Vendor page did not render for this revision; values below are from community documentation |
| Enshrouded | [Enshrouded Wiki, Dedicated Server Hosting](https://enshrouded.fandom.com/wiki/Dedicated_Server_Hosting) | **No.** Not retrievable for this revision; values below are from community documentation |

**The two unverified rows are marked deliberately rather than quietly dropped.** They support an
argument about the *shape* of game servers, not a runbook, and an error in one of their cells would
not overturn the conclusion. But per [ADR 0005](decisions/0005-describe-titles-with-a-declarative-manifest.md)
consequence 1, **a title actually joining the platform needs a full manifest built from primary
sources**, and neither of these has one yet. Do not treat the row as the research.

| | **Valheim** | **Minecraft (Java)** | **Palworld** | **Satisfactory** | **Enshrouded** |
|---|---|---|---|---|---|
| **Acquisition** | SteamCMD, anonymous, app `896660` | Download `server.jar` from Mojang. No SteamCMD | SteamCMD, anonymous, app `2394010` | SteamCMD, anonymous, app `1690800` | SteamCMD, anonymous, app `2278520` |
| **Runtime dependency** | glibc 2.29+, libatomic1, libpulse | A JVM | Proton or native | Native | Native |
| **Licence gate** | None | **`eula.txt` must be accepted or it refuses to start** | None | None | None |
| **Config surface** | **Command-line flags only** | `server.properties` (key=value) | `PalWorldSettings.ini` | In-game Server Manager plus `.sav` settings files | `enshrouded_server.json` |
| **Config trap** | Steam overwrites `start_server.sh` on update | - | Edit `PalWorldSettings.ini`, not `DefaultPalWorldSettings.ini`, which is overwritten on update | Settings persist only on graceful shutdown | - |
| **Game port** | UDP 2456 | **TCP 25565** | UDP 8211 | **TCP and UDP 7777** | UDP 15636 |
| **Query port** | UDP 2457 | Optional UDP query | UDP 27015 | Same 7777 | UDP 15637 |
| **Remote admin** | **None. No RCON, no console** | RCON, TCP 25575 | REST API TCP 8212; RCON TCP 25575, deprecated | **Its own HTTPS API on 7777** | None documented |
| **Save shape** | Directory of chunk files per world | `world/` directory | Save directory | `.sav` files | `savegame/` directory |
| **Official relay** | **Yes, PlayFab via `-crossplay`** | No | No | No | No |
| **Port remapping** | Advertises its own port; keep them equal | Fine | Fine | **Unsupported on the standard port**; the reliable port can be remapped via `-ExternalReliablePort=` | Keep equal |
| **Graceful stop** | **SIGINT specifically** | `stop` via console or RCON | Signal, or REST | Console command; **required or config is lost** | Signal |

Even at five titles, look at how much of that table disagrees with itself. Minecraft is TCP and is
not on Steam and will not start until a licence file says so. Satisfactory has a whole HTTPS API and
forbids port remapping. Palworld has two competing remote-admin mechanisms, one of them being
retired. Valheim has no remote admin at all.

**A design that assumed "game servers have RCON" would have been wrong for two of the five, including
the one we are actually building for.**

## What is genuinely generic

These are the rows where all five agree on the *shape* even when they disagree on the value. This
is the generic layer, and nothing else belongs in it.

| Capability | Why it generalises |
|---|---|
| **Acquire a versioned artifact** | All five fetch a server build from somewhere and can be pinned to a version. The mechanism differs; the concept does not. |
| **Render configuration from a declaration** | All five are configured somehow before start. Flags, properties, ini and json are all "turn a declaration into what this title expects". |
| **One persistent state directory** | All five keep everything that matters under a single path. This is the most useful invariant in the table, because it is what makes backup generic. |
| **Supervise one long-running process** | All five are a single process to start, watch and restart. |
| **Declare ports and protocols** | All five need a specific set of ports with specific protocols exposed. |
| **Stop gracefully, by a title-specific method** | All five require a clean shutdown to avoid losing state. *How* varies; *that it is required* does not. |
| **Update, then restart** | All five patch by replacing the artifact and restarting. |
| **Back up and restore the state directory** | Follows from the single state directory. This is the platform's most valuable shared service. |
| **Emit a log stream** | All five write to stdout or a file that can be collected. |
| **Some notion of allowed players** | All five have a way to restrict who joins, though the mechanism varies wildly. |

Note what this gives: **backup, supervision, restart, port exposure and update orchestration can all
be written once.** That is most of the operational burden, and it is the real justification for a
platform rather than five unrelated setups. The justification is not elegance; it is that the
expensive, easy-to-get-wrong parts are the shared ones.

## What is irreducibly per-title

| Aspect | Why it cannot be unified |
|---|---|
| **Acquisition mechanism** | SteamCMD for four, an HTTP download for Minecraft. Future titles may need a publisher's installer. |
| **Config format** | Flags, properties, ini, json, and Satisfactory's in-game manager are not variations on a theme. |
| **Runtime prerequisites** | A JVM versus specific glibc and audio libraries. This is precisely what the container boundary absorbs. |
| **Licence acceptance** | Minecraft's `eula.txt` has no analogue elsewhere. |
| **Save layout and consistency rules** | Valheim's generation counters and `.ok` markers are Valheim's. The *directory* is generic; what is inside it is not. |
| **Remote administration** | From a full HTTPS API to nothing at all. Cannot be assumed. |
| **Graceful stop method** | SIGINT, a console command, an API call. All required, none interchangeable. |
| **Player identity** | Steam IDs, Minecraft UUIDs, PlayFab identities across platforms. |
| **Reachability model** | Valheim ships a relay. Nothing else here does. |

## The layered model

```
  friends                                owner
     |                                     |
     v                                     v
+---------------------------------------------------+
|  control plane        start / stop / status        |   remote-control.md
+---------------------------------------------------+
|  shared services                                   |
|  backup + restore | reachability | logs | identity |
+---------------------------------------------------+
|  title adapter     one declaration per game        |   <- the only per-title part
|  valheim | minecraft | palworld | ...              |
+---------------------------------------------------+
|  container runtime    supervision, limits, volumes |   ADR 0004
+---------------------------------------------------+
|  host      always-on x86 Linux machine             |   ADR 0001
+---------------------------------------------------+
```

The load-bearing claim is that **the per-title part is one layer and it is thin.** Everything a
title needs to say about itself is a declaration; everything done with that declaration is shared.

## The title contract

What a title must declare to join the platform. Written as a shape, not a schema, because
committing to a syntax is an implementation decision that has not been made yet.

| Field | Meaning | Required |
|---|---|---|
| `id`, `name` | Identity | Yes |
| `acquire` | How to fetch the server build, and how to pin a version | Yes |
| `runtime` | What the server needs to execute. Normally absorbed by the container image | Yes |
| `preconditions` | Anything that must be satisfied before first start, such as accepting a licence | No |
| `config` | How to turn a declaration into this title's configuration, and where it is written | Yes |
| `config_hazards` | Files the update process overwrites, so configuration is never put there | No |
| `state_dir` | The single path holding everything that must survive | Yes |
| `state_consistency` | How to tell a complete save from one in flight | No |
| `ports` | Each port, its protocol, its role, and whether remapping is permitted | Yes |
| `stop` | How to stop gracefully, and how long it may take | Yes |
| `health` | How to tell it is alive, and separately how to tell state is advancing | Yes |
| `admin` | Remote administration, **if any** | No |
| `players` | How player identity and allowlists work | No |
| `reachability` | Whether the title offers its own relay | No |

Three of these exist only because the evidence forced them, and they are the ones a design written
from intuition would have missed:

- **`config_hazards`** exists because Valheim's `start_server.sh` and Palworld's
  `DefaultPalWorldSettings.ini` are both destroyed by updates. Without this field, the platform
  would cheerfully write configuration into a file that the next update deletes.
- **`state_consistency`** exists because Valheim's `.ok` marker is the difference between a backup
  and a corrupt copy. A generic backup service that only knows "copy this directory" cannot tell
  whether it copied a complete save.
- **`admin` is optional**, because Valheim has none. See [the leak](#where-the-contract-leaks).

## Valheim against the contract

The validation. If the contract cannot express the title we are actually building for, it is wrong.

| Field | Valheim |
|---|---|
| `id` | `valheim` |
| `acquire` | SteamCMD, anonymous login, app `896660`, `validate` on update |
| `runtime` | glibc 2.29+, libstdc++ 3.4.26+, `libatomic1`, `libpulse-dev`, `libpulse0` |
| `preconditions` | None |
| `config` | Command-line flags: `-name -world -password -port -public -crossplay -preset -saveinterval -backups -savedir` |
| `config_hazards` | **`start_server.sh` is overwritten on every Steam update.** Never put config there |
| `state_dir` | `-savedir`, containing `worlds_local/<World>/` plus `adminlist.txt`, `permittedlist.txt`, `bannedlist.txt` |
| `state_consistency` | Newest `_main.N.*` generation with a matching `.ok` marker |
| `ports` | UDP 2456 game, UDP 2457 query. **External and internal must match** |
| `stop` | **SIGINT**, with a generous timeout. SIGTERM unreliable, SIGKILL loses up to `-saveinterval` |
| `health` | Liveness: A2S query on 2457. **Durability: generation number and `.ok` timestamp advancing** |
| `admin` | **None.** No RCON, no console socket |
| `players` | Steam IDs and platform IDs in the three list files. Note: a non-empty `permittedlist.txt` excludes everyone not on it |
| `reachability` | `-crossplay` switches to the PlayFab relay, removing the port-forwarding requirement |

Every field is expressible, and the two that are empty are empty for real reasons rather than
because the contract has no room for them. That is the validation.

The fields the platform cares about most - `state_dir`, `state_consistency`, `stop`, `health` - are
exactly the ones that took the most research to fill in correctly, which is a reasonable sign the
contract is pointed at the right things.

## Where the contract leaks

An honest architecture document names the places its abstraction does not hold. Three of them here.

### 1. Remote administration is not uniform, and for Valheim it is absent

Minecraft has RCON. Palworld has a REST API and a deprecated RCON. Satisfactory has its own HTTPS
API. Valheim and Enshrouded have neither.

This is not a gap to be papered over with a lowest-common-denominator interface. There is no
common denominator: the intersection of those five is empty. A platform that assumed an admin
channel would be unable to run the title it was built for.

**How it is handled:** `admin` is optional, and the platform must be fully functional without it.
Anything the control plane genuinely needs - start, stop, status - is provided by the *container
runtime*, which works identically for all five, rather than by the game. The consequence is real
and accepted: without an admin channel, the platform **cannot** warn players in-game before a
restart, kick someone, or read the live player list from the game itself. Those become features of
titles that support them, not platform guarantees.

### 2. "One persistent state directory" is true in shape and not in substance

All five keep state under one path, which makes *copying* generic. Nothing about what is inside is
generic. Valheim needs the newest complete generation; Satisfactory keeps settings in `.sav` files
that only persist on graceful shutdown; Minecraft's `world/` has its own region-file semantics.

**How it is handled:** the backup service copies directories, and `state_consistency` tells it how
to decide a copy is valid. That keeps the per-title knowledge to one field instead of one backup
implementation per game. It is a genuine simplification, not a complete one.

### 3. Satisfactory does not fit the port model

Satisfactory explicitly does not support port redirection, and serves game traffic and its HTTPS
API on the same port over both TCP and UDP. The generic "map a port, any port" model does not hold.

**How it is handled:** `ports` carries an explicit "remapping permitted" flag per port. The platform
must be able to refuse a configuration rather than silently produce a broken server. Valheim has
a milder version of the same constraint, because it advertises its own port to the Steam lobby.

None of these three is fatal. All three would have been invisible to a design that did not check.

## What the platform must not try to unify

For the later implementation ticket, so it does not over-build. The project's guidance is to start
with the simplest direct path and add machinery only when a concrete need justifies it.

- **In-game administration.** Two of five titles cannot do it at all.
- **A common configuration language across titles.** The per-title declaration should describe
  *that* title in *its* terms. Inventing a universal settings vocabulary means maintaining a
  translation layer for every title forever, to spare the owner from learning four config formats
  they will look up once.
- **Player identity across games.** A Steam ID, a Minecraft UUID and a PlayFab ID are not the same
  person in any way the platform can verify. The control plane needs its own identity
  ([`remote-control.md`](remote-control.md)); mapping that onto each game's identity is a per-title
  concern and mostly a manual one.
- **Mod management.** Out of scope per [`scope-and-goals.md`](scope-and-goals.md), and a different
  problem in every title.
- **Multi-host scheduling.** There is one machine. Orchestrators solve a problem this project does
  not have.
- **A generic "world" concept.** Valheim has named worlds, Minecraft has a world directory,
  Satisfactory has save slots. The platform manages *state directories*. It does not need to know
  what a world is.

## Does the design hold?

The test set at the top was whether the generic layer survives contact with five real titles.

**It holds, with the three documented leaks.** The parts that generalise cleanly - acquire,
configure, supervise, expose ports, stop gracefully, back up, update, log - are also the parts that
carry the operational risk and are expensive to get right. The parts that do not generalise -
remote admin, config format, save internals - are mostly things the owner touches once per title.

That is the right split. The shared layer absorbs the work that is dangerous to do five times, and
the per-title layer holds the knowledge that was always going to be per-title. If the ratio were
reversed, the correct conclusion would be to abandon the platform idea and run five independent
setups, and that conclusion was genuinely available before the table was filled in.
