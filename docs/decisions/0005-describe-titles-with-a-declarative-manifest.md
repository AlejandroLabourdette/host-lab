# 0005 - Describe titles with a declarative manifest

> Status: accepted
> Date: 2026-09-22

## Context

Goal G5 in [`scope-and-goals.md`](../scope-and-goals.md) is that adding a second game should be a
configuration change rather than a redesign. That requires deciding where the boundary between
shared machinery and game-specific knowledge sits, and in what form the game-specific part is
expressed.

The evidence gathered in [`platform-architecture.md`](../platform-architecture.md) constrains this
more than expected. Across five titles, the things that generalise are the operational ones -
acquire, configure, supervise, expose, stop, back up, update - and the things that do not are the
interfaces and formats. Notably, **two of the five titles have no remote administration channel at
all, including Valheim**, which rules out an entire family of designs that would otherwise be
natural.

## Options considered

### A. No platform. One bespoke setup per title

- **For:** simplest possible thing. No abstraction to be wrong. Matches the project's guidance to
  start with the direct path.
- **Against:** the operational work - backup, restore, supervision, update, monitoring, reachability
  - gets reimplemented per title, and it is precisely the work that is dangerous to get wrong. The
  second title would duplicate every mistake and every fix.
- **Verdict:** rejected, but it was a real candidate and remained so until the evidence table showed
  how much of the risky work is shared.

### B. A plugin or adapter interface: per-title code implementing a common API

- **For:** maximum flexibility. Any title can be made to fit by writing enough code.
- **Against:** every title becomes a code artifact to write, test and maintain, and the interface
  will be shaped by whichever title was implemented first. Failure mode is silent: an adapter that
  compiles and quietly does the wrong thing with a world folder.
- **Verdict:** too much machinery for a handful of games on one machine.

### C. A declarative manifest per title, interpreted by shared machinery (chosen)

Each title supplies a declaration of facts about itself. The platform acts on those facts.

- **For:** a title is data, so adding one is reading documentation and filling in fields rather
  than writing and testing code. The declaration is reviewable, diffable, and doubles as the
  documentation of how that title works. The shared machinery is written once.
- **Against:** a title that does not fit the fields cannot be added without extending the schema,
  and the schema will need extending. Expressiveness is deliberately limited.
- **Verdict:** chosen. The limitation is a feature here: it forces per-title oddities to be named
  as fields, visible to everyone, rather than buried in code.

### D. Adopt an existing platform wholesale (Pterodactyl, LinuxGSM)

- **For:** it exists and is maintained.
- **Against:** covered in [ADR 0004](0004-run-game-servers-as-containers.md). Both impose their own
  model, and neither solves the two problems this project actually cares about - off-host backup
  with verified restore, and friend-operated control with real identity.
- **Verdict:** rejected as a foundation; still worth borrowing ideas from.

## Decision

**Each title is described by a declarative manifest. Shared machinery interprets it. The manifest
is data, not code.**

The fields are listed in [`platform-architecture.md`](../platform-architecture.md). Three of them
exist only because the evidence demanded them, and they are the ones worth defending:

1. **`config_hazards`** - files that the update process overwrites. Valheim's `start_server.sh` and
   Palworld's `DefaultPalWorldSettings.ini` both are. Without this, the platform would write
   configuration into a file the next update destroys, and the symptom would appear weeks later
   with no obvious cause.
2. **`state_consistency`** - how to tell a complete save from one in flight. Valheim's `.ok` marker
   is the difference between a backup and a corrupt copy. A backup service that only knows "copy
   this directory" cannot make that distinction, and the whole value of the platform rests on the
   backup being real.
3. **`admin` is optional.** Valheim and Enshrouded have no remote administration. The platform must
   be fully functional without one.

## The constraint that shaped this most

**The platform's control operations must come from the container runtime, not from the game.**

Start, stop, restart and status have to work for every title. Only the runtime offers those
uniformly; the games do not. This is why [ADR 0004](0004-run-game-servers-as-containers.md) and
this decision are coupled: containers are not only a supervision choice, they are the thing that
makes a uniform control plane possible when two of five titles expose no control interface at all.

The cost is explicit and accepted: **without a game-level admin channel, the platform cannot warn
players in-game before a restart, kick a player, or read the live player list from the game.** For
titles that do offer one, those become per-title features, never platform guarantees.

## Consequences

1. **Adding a title is a documentation exercise**, and the manifest is where the research lands.
   Filling in `state_consistency` and `stop` correctly is the hard part, and both require reading
   primary sources.
2. **The schema will grow.** Satisfactory already needs a per-port "remapping permitted" flag that
   Valheim does not. Growth is expected; each new field should be justified by a real title.
3. **Backup is the platform's flagship shared service**, because the single-state-directory
   invariant holds across all five titles examined.
4. **Health checks are two separate claims** - the process is alive, and state is advancing - and
   the manifest carries both. See [`always-on-operation.md`](../always-on-operation.md).
5. **No universal configuration vocabulary.** Each manifest describes its title in that title's own
   terms. A translation layer would have to be maintained forever to save the owner from reading
   four config formats once.
6. **A title that does not fit is a signal, not a failure.** The right response is to extend the
   schema deliberately, or decide the title does not belong here, rather than to add an escape
   hatch for arbitrary code.

## Revisit if

- A title the group actually wants cannot be expressed without an escape hatch. One such title is
  an extension; two are evidence that option B was right after all.
- The manifest accumulates fields used by exactly one title, which would mean the abstraction is
  tracking specifics rather than generalising them.
