# 0003 - Back up world saves off the host

> Status: accepted
> Date: 2026-09-22

## Context

Goal G1 in [`scope-and-goals.md`](../scope-and-goals.md) is that the world survives the loss of any
single machine, including the host. That goal is the reason this project exists: the group's
current arrangement puts a shared world on one person's disk with whatever backup habits that
person happens to have.

[ADR 0001](0001-host-on-an-owned-always-on-x86-machine.md) chose a self-owned machine, which means
there is no provider snapshot facility to fall back on. Whatever protection exists is the one we
build.

Valheim ships rolling backups of its own, which makes it tempting to declare the problem solved. It
is not solved, and the reasons are specific enough to record.

## Options considered

### A. Rely on the game's built-in rolling backups

`-backups 4`, `-backupshort 7200`, `-backuplong 43200`.

- **Cost:** zero. Already on by default.
- **Covers:** player-caused accidents. A bad raid, a regretted terraform, a griefing incident.
- **Does not cover:** anything that takes the disk, the filesystem or the machine, because the
  backups are on that same disk in that same directory tree. Nor slow corruption: the default
  retention is roughly 38 hours of history, so a problem introduced on Friday and noticed on Monday
  is already unrecoverable.
- **Verdict:** keep it, it is a good undo buffer, but it does not address G1 at all.

### B. Local copies to a second disk or a NAS

- **Cost:** near zero if a second disk or NAS exists.
- **Covers:** disk failure, filesystem corruption, a bad update, `rm -rf`.
- **Does not cover:** fire, theft, flood, ransomware reaching a mounted share, or the host simply
  never coming back.
- **Verdict:** necessary, not sufficient. A second drive in the same case does not satisfy "survives
  the loss of any single machine" in the way the goal means it.

### C. Off-site copies

Object storage, a friend's machine, or both.

- **Cost:** for a world measured in hundreds of megabytes, effectively nothing. A friend's machine
  is free.
- **Covers:** the whole-site failures B misses.
- **Costs paid:** encryption becomes mandatory, since the data sits somewhere we do not control.
  Upload competes with the game for a domestic connection's scarce upstream, so scheduling matters.
- **Verdict:** this is the one that actually satisfies G1.

### D. Filesystem snapshots (Btrfs, ZFS, LVM)

- **Cost:** a filesystem choice made at install time, which is free if made early and disruptive if
  made late.
- **Buys:** atomic point-in-time consistency with no downtime, which is the cleanest answer to the
  problem of copying a chunked save format that is being written to.
- **Does not cover:** anything on its own. A snapshot is on the same filesystem as the original.
- **Verdict:** an excellent *mechanism* for taking a consistent copy, not a strategy by itself.
  Pairs with B and C rather than competing with them.

## Decision

**All four, in their proper roles: keep the game's backups as an undo buffer; take a consistent
local copy daily and before every update; replicate off-site, encrypted; and use a filesystem
snapshot as the copy mechanism where the filesystem supports it.**

Three rules attach to this, and they are the parts most likely to be skipped:

1. **Copy the entire world directory as a unit.** Since Valheim 1.0 (2026-09-09) a world is a
   directory of chunk files, not a file pair. A partial copy yields a world the server will not
   open, and its response to a world it cannot open is to silently generate an empty one.
2. **Snapshot before the first boot on any new major version.** Format conversions are automatic,
   irreversible, and have already gone wrong in this game: Iron Gate's 1.0.15 notes (2026-09-18)
   record a conversion bug that damaged item levels and was only fixed in 1.0.12.
3. **The backup is not accepted until it has been restored.** The restore drill in
   [`save-data-and-backups.md`](../save-data-and-backups.md) is part of the decision, not an
   optional extra.

## Why not less

The obvious objection is that this is a lot of machinery for a game. It is not, and the reason is
the asymmetry: the cost of the full arrangement is an hour of setup and a few hundred megabytes of
storage, while the cost of getting it wrong is the group's shared world and the several hundred
hours in it, unrecoverably. There is no version of this trade that favours doing less.

The genuine trade-off is elsewhere: **downtime versus complexity** in taking a consistent copy.
Stopping the server to copy is simple and correct and costs a few minutes of downtime at a time
nobody plays. A hot copy avoids the downtime and requires reasoning about generation counters and
`.ok` markers. The recommendation is to stop the server, because the downtime is genuinely free at
5am and the complexity is not.

## Consequences

1. **The save directory must be somewhere deliberate.** `-savedir` should point at a path chosen
   for backup and mounting, not at the default buried under a service account's home.
2. **Monitoring must watch that saves are advancing**, not that the process is running. The failure
   documented in `valheim-server-docker` issue #802 had a healthy container whose every autosave was
   failing silently. Liveness is not the same claim as durability.
3. **Backup scheduling interacts with the network.** Off-site upload competes with the game for
   upstream bandwidth on a domestic line, so it is scheduled outside play hours. See
   [`networking.md`](../networking.md).
4. **The restore drill is a recurring obligation**, re-run after any change to the save format or
   the backup job, not performed once and assumed.
5. **Launch parameters are backed up alongside the world.** A correct world restored under the wrong
   `-world` name is not findable, and that failure looks identical to data loss.
6. **Character files are explicitly out of scope.** They are client-side. The group should know
   this, because people assume the server protects them.

## Revisit if

- The world grows large enough that full copies stop being cheap, at which point incremental or
  deduplicating backup becomes worth its complexity.
- Iron Gate publishes an actual save-format reference, which would let the consistency checks move
  from observed behaviour to specified behaviour.
- The group starts running several titles with meaningfully different save shapes, which is a
  question for [`platform-architecture.md`](../platform-architecture.md).
