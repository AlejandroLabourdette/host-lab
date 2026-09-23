# World save data, backup and restore

> Status: accepted
> Last reviewed: 2026-09-22

This is the document the project exists for. Everything else here is convenience; this is the part
where hundreds of hours of a group's shared time either survives a disk failure or does not.

The decision is recorded in [ADR 0003](decisions/0003-back-up-world-saves-off-the-host.md).

The short version, if you read nothing else:

1. **Copy the entire world folder**, never individual files inside it.
2. **The game's own backups are not a backup.** They are on the same disk as the thing they protect.
3. **A backup you have never restored is not a backup**, it is a belief. Run the
   [restore drill](#the-restore-drill).

## What "the world" actually is

Valheim 1.0, released 2026-09-09, changed the on-disk format. Almost every guide written before
that date is now wrong about this, which is the single best argument for the dating convention this
repository uses.

### Since 1.0: a directory per world

```
worlds_local/Midgard/
  _main.7.fwl2        world metadata: name, seed, owner. Small.
  _main.7.db2         world data. No longer the whole world.
  _main.7.chunks      the index tying the terrain chunks together
  00_00__0_1.chunk    one terrain chunk. There will be many, and more as the world is explored.
  ...
  _main.7.ok          write-complete marker for generation 7
```

Two structural details matter operationally:

**The generation counter.** The `N` in `_main.N.*` increments on every save cycle. Valheim writes a
new generation and retires the previous one rather than overwriting in place. This is why a
half-finished save does not destroy the last good one.

**The `.ok` marker is written when a save completes.** It is the game telling you, on disk, that
generation N is whole. This is the most useful fact in this document for anyone writing a backup
job later: a generation with a matching `.ok` file is a consistent point, and one without it is a
save that was still in flight.

Source: [Valheim Save Location and the 1.0 World Folder Format](https://www.gameserverkings.com/knowledge-base/valheim/valheim-save-location/)
(2026-09-09, accessed 2026-09-22). This is a secondary source. Iron Gate has not published a
file-format reference, so the structure here is derived from community documentation and from
server tooling that had to handle the change. Treat the exact filenames as observed rather than
specified, and re-check them against a real installation before writing anything that parses them.

### Before 1.0: a pair of files

```
worlds_local/Midgard.db     world data
worlds_local/Midgard.fwl    world metadata
```

Both were required, and a guide that told you to copy only the `.db` was already wrong then.

### Where it lives

| | Path |
|---|---|
| Linux | `~/.config/unity3d/IronGate/Valheim/worlds_local/` |
| Windows | `%USERPROFILE%\AppData\LocalLow\IronGate\Valheim\worlds_local\` |
| Override | the `-savedir` launch parameter |

Sources: [Iron Gate, A Guide to Dedicated Servers](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/)
(2024-04-11) for the base path and `-savedir`;
[Valheim Wiki](https://valheim.weirdgloop.org/w/Dedicated_servers) (accessed 2026-09-22) for
`worlds_local`. Both accessed 2026-09-22.

**Use `-savedir`.** The default path is buried in a hidden directory under a service account's home
and is a poor place to point a backup job at, a poor thing to mount into a container, and easy to
lose when the host is rebuilt. Put the save directory somewhere deliberate, on the filesystem you
intend to back up. This costs one flag and removes an entire category of accident.

**Note the folder name is load-bearing.** The world directory's name must match the `-world`
parameter exactly, including capitalisation. A mismatch does not produce an error; it produces the
server cheerfully generating a brand new empty world while the real one sits untouched next to it.
That symptom is covered in [restore failures](#when-a-restore-appears-to-do-nothing).

## The 1.0 conversion, and why it deserves its own section

When a 1.0 server first opens a world saved by an older version, **it converts it to the new
directory format, and the conversion is one-way.** A pre-1.0 server cannot read the world
afterwards.

Source: [valheim-server-docker](https://github.com/community-valheim-tools/valheim-server-docker)
project README:
"The first time a 1.0 server opens a world saved by an older version it converts it to the new
directory format. As with every Valheim world version upgrade this is one-way" (accessed
2026-09-22).

This is not theoretical risk. Iron Gate's own [Patch 1.0.15 notes](https://www.valheimgame.com/news/patch-1-0-15/)
(2026-09-18, accessed 2026-09-22) acknowledge that a bug in the 1.0 conversion caused **items on
stands to lose their levels**, that it was only fixed in 1.0.12, and that affected players' options
were to revert to a backup and lose all progress since, or to repair items by hand. A group that
converted between 2026-09-09 and the 1.0.12 fix and had no backup had no good option at all.

The rule this produces:

> **Snapshot the world before the first boot on any new major version, and keep that snapshot
> until the world has been played on and inspected.** Not the game's rolling backup. A copy that
> lives somewhere the upgrade cannot reach.

This applies beyond Valheim and beyond 1.0. Format migrations are the highest-risk routine event in
a game server's life, they are triggered automatically by an update, and they are irreversible. See
[`always-on-operation.md`](always-on-operation.md) for how this constrains the update procedure.

## The game's own backups, and why they are not enough

Valheim takes rolling backups by itself, controlled by four launch parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `-saveinterval` | 1800 (30 min) | Seconds between world saves |
| `-backupshort` | 7200 (2 h) | Interval for the short-cycle backup |
| `-backuplong` | 43200 (12 h) | Interval for the long-cycle backups |
| `-backups` | 4 | How many to retain: the first at the short interval, the rest at the long one |

With the defaults, you have one backup roughly 2 hours old and three more spaced 12 hours apart.
**All four parameters are documented by Iron Gate**
([A Guide to Dedicated Servers](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/),
2024-04-11, accessed 2026-09-22), which describes `-backupshort` as "the interval between the first
automatic backups" and `-backuplong` as "the interval between the subsequent automatic backups".
Since 1.0 these appear as `_backup_auto-` folders with a timestamp, alongside the world folder,
which is a community-observed detail rather than a documented one.

These are genuinely useful. They protect against the most common accident, which is not a disk
failure but a person: a botched terrain edit, a raid that flattened a base, a mistake nobody wants
to keep. Rolling back two hours is exactly the right tool for that.

**They are not a backup, for one reason that defeats all of their advantages:** they are on the
same disk, in the same directory tree, on the same machine as the world they protect. Every failure
that takes the world takes them with it. Disk failure, filesystem corruption, a mistaken `rm -rf`,
theft, fire, ransomware, or the host simply not coming back after a power cut.

They also do not protect against the slowest and nastiest failure mode, which is **corruption you
do not notice in time.** With four retained backups at the default intervals, the entire history
you hold is about 38 hours. A problem introduced on Friday and noticed on Monday is already past the
end of the tape.

Treat them as an undo buffer. The backup is a separate thing.

## What a real backup copies

**The whole world directory, as a unit.** Not the `.db2`, not "the important files". A partial copy
produces a world the server cannot open, and its response to a world it cannot open is not an
error: it generates a fresh empty one. The fragments you saved are then unreachable.

Beyond the world folder, three small files that are easy to forget and annoying to rebuild:

| File | Why |
|---|---|
| `adminlist.txt` | Who can use admin commands |
| `permittedlist.txt` | The allowlist, if used |
| `bannedlist.txt` | The banlist |

These live in the save directory root, and hold one platform user ID per line
([Iron Gate](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/), 2024-04-11,
accessed 2026-09-22).

Also worth capturing, though not strictly save data: **the server's launch parameters**. A world
restored onto a server started with a different `-world` name or a different `-savedir` is a world
that will not be found. Record them next to the backup.

### What is not yours to back up

**Character files are client-side.** Each player's character lives on their own machine, not on the
server. Losing the server loses the world, the buildings and the map; it does not lose anyone's
character, and no amount of server-side backup protects a friend who loses theirs. Worth telling
the group once, because people assume otherwise and are surprised in both directions.

## Consistency: the part that quietly goes wrong

Copying a directory that is being written to gives you a copy of a moment that never existed. For a
chunked save format this is a real risk, not a theoretical one: a copy could catch the new `.chunks`
index with some chunk files still at their old contents.

Three approaches, in decreasing order of safety:

**1. Stop the server, copy, start it.** Unambiguously correct, and unambiguously an outage. Fine
for a nightly job at a time the group does not play. This is the recommended default, because the
cost is a few minutes of downtime at 5am and the benefit is never having to reason about any of
this again.

**2. Filesystem snapshot, then copy the snapshot.** If the save directory is on Btrfs, ZFS or LVM,
an atomic snapshot gives a point-in-time view with no downtime. This is the best option where it is
available and it is worth choosing the filesystem for it.

**3. Hot copy, verified against the `.ok` marker.** Copy while running, then confirm the copy
contains a generation whose `.ok` marker is present and whose referenced chunks are all there. Use
the save interval to pick the timing: with `-saveinterval 1800`, copying immediately after an
observed save is the widest safe window. This is the most complex option and the one most likely to
be subtly wrong.

Whichever is used, **verify after copying, not before restoring.** A backup job that reports
success because `cp` returned zero has verified nothing.

### A real example of this failing silently

Worth reading, because it is the exact shape of failure this section is about.
[community-valheim-tools/valheim-server-docker issue #802](https://github.com/community-valheim-tools/valheim-server-docker/issues/802)
(accessed 2026-09-22): after the 1.0 format change, a container's permission-fixing routine applied
file permissions `0644` indiscriminately to everything under `worlds_local/`, including the new
per-world *directories*. A directory without the execute bit cannot have new entries created in it,
so **every autosave failed, silently, while the container reported healthy.** The migration had
already renamed the old `.db` aside to `.db.old`, so the server would not fall back to it on its
own: the pre-1.0 file was still on disk, but nothing was going to load it, and by the time anyone
noticed it was stale by however long the failure had gone undetected. A file the software will not
read is not a fallback, it is an archaeology project.

The lessons generalise past that one container:

- A format change breaks tooling that assumed the old shape, including your own.
- "The process is running" and "the server is saving" are different claims, and monitoring usually
  checks the first.
- **Monitor that the save is advancing**, not that the service is up. A world folder whose newest
  generation number and `.ok` timestamp have not moved in hours is a broken server, regardless of
  what the health check says.

## Strategy

3-2-1, applied concretely: **three copies, on two kinds of media, one of them off-site.**

| Copy | Where | Protects against | Frequency |
|---|---|---|---|
| The live world | Host disk | Nothing. This is the thing at risk. | Continuous |
| The game's rolling backups | Same host disk | Player mistakes, bad raids, regrettable terraforming | Per `-backupshort` / `-backuplong` |
| **Local backup** | A different disk on the host, or a NAS | Disk failure, filesystem corruption, a bad update | Daily, and before every update |
| **Off-site backup** | Somewhere not in the building | Fire, theft, flood, ransomware, the host never coming back | Daily or weekly |

The off-site copy is the one that actually satisfies goal G1 in
[`scope-and-goals.md`](scope-and-goals.md): the world must survive the loss of any single machine,
including the host. A backup sitting on a second drive in the same case does not satisfy it.

Practical notes on the off-site copy:

- **Encrypt it.** It is going somewhere you do not control. This is cheap and removes the question
  entirely.
- **Retention should exceed the time it takes to notice a problem.** A week of dailies plus a few
  monthlies covers the "corrupted on Friday, noticed on Monday" case that the game's own 38-hour
  window does not.
- **Mind the upstream.** A domestic connection is asymmetric, and a backup upload competes with the
  game for the same scarce upstream capacity. Schedule it when nobody plays. See
  [`networking.md`](networking.md).
- **Give someone else a copy.** The cheapest real off-site backup for a group of friends is another
  friend's machine. It also means the world outlives the owner's interest in hosting it, which is
  the deeper version of the problem this project was started to solve.

## The tooling

The rules above are implemented rather than left as instructions, because every
one of them is a rule people skip under time pressure.

| Command | Does |
|---|---|
| `hostlab state valheim --state-dir <dir>` | Reports the newest **complete** generation per world, and exits non-zero if nothing has saved within the manifest's staleness limit |
| `hostlab backup valheim --state-dir <dir>` | Refuses unless the state is in a copyable condition, copies the whole directory as one unit, applies retention, then verifies the repository |
| `hostlab snapshots valheim` | What is actually in the repository |
| `hostlab restore valheim --target <empty dir>` | Restores, then inspects what came back and says whether it holds a complete generation |

Three behaviours are worth knowing before you need them:

- **A generation still being written is ignored**, not copied. That is the
  `.ok` marker doing its job, expressed as `state_consistency` in the manifest
  rather than as knowledge inside the backup code.
- **`backup` refuses an inconsistent state** and says what is wrong with it.
  `--even-if-damaged` overrides that, and exists for the one case where the
  check should not win: a state directory that is *already* damaged is the one
  you most want a copy of before touching it.
- **`restore` refuses a target that is not empty.** Never restore onto the live
  world as a test, and never leave two servers pointed at one state directory.

Retention is a week of dailies, five weeklies and six monthlies, which is
deliberately longer than the game's own roughly 38 hours: retention has to
exceed the time it takes to **notice** a problem, not the time to have one.

### The automated backup is a hot copy, and why that is acceptable here

The recommendation above is to stop the server, copy, and start it again. **The
scheduled backup does not do that**, and cannot: the agent reaches Docker
through a proxy that refuses every mutating call
([ADR 0010](decisions/0010-reach-the-runtime-through-a-read-only-proxy.md)), so
it has no way to stop anything. That boundary is deliberate and it is what
makes the read-only status reader read-only in fact rather than by convention.

So the scheduled copy is option 3 above, the one this document calls the most
likely to be subtly wrong. What rescues it is that **the risk turns out to be a
property of the title, not of hot copies in general.**

Valheim writes a **new** generation and retires the previous one rather than
overwriting in place. While generation 8 is being written, every file of
generation 7 is already complete and is no longer being touched. A copy taken
mid-write therefore contains an intact generation 7, and the `.ok` marker is how
the platform confirms which generation that is. It is the same property that
stops a half-finished save from destroying the last good one.

A title that overwrote its save in place would **not** be safe this way, however
carefully the copy was verified afterwards. So this is declared per title rather
than assumed: `state_consistency.hot_copy_safe` carries the claim and the
reasoning, `hostlab backup` refuses a hot copy for any title that has not made
it, and the default is to refuse.

**The manual, stop-first backup is still there and is still better.** Run it
before an update, which is the moment ADR 0003 cares about most: stop the
server, run `hostlab backup`, start it again. The scheduled copy is the safety
net, not the ceremony.

**The restic repository password must live somewhere that is not this host.**
Losing it turns the off-site copy into an encrypted blob nobody can open, which
is a complete failure of the goal the off-site copy exists for. A password
stored only on the machine whose loss you are insuring against is not stored.

## The restore drill

An untested backup is a belief, not a backup. The failure you are protecting against is rare, will
happen at an inconvenient moment, and is the worst possible time to discover that the archive was
empty for six weeks.

**Do this once when the backup is set up, and again after any change to the game's save format or
the backup job.** It takes fifteen minutes.

1. **Pick a backup at random**, not the newest one. The newest one is the one most likely to work.
2. **Restore it somewhere else.** A second copy of the server pointed at a different `-savedir` and
   a different port. Never restore onto the live world as a test.
3. **Start the server and connect to it.** The world loads, the map is right, and the buildings are
   there.
4. **Check the things a partial restore would break.** Structures intact, chests hold their
   contents, terrain edits present, the map explored to where it should be. A world that loads is
   not necessarily a world that is whole.
5. **Confirm the world you got is the world you expected.** Check the date. Restoring a correct
   backup of the wrong week is a distinct and embarrassing failure.
6. **Write down how long it took**, end to end. That number is the group's real recovery time, and
   it is the only honest answer to "how bad would it be if the machine died".
7. **Tear the test server down.** Do not leave it running: a second server on the same world
   directory is a way to lose both.

If any step fails, the backup job is broken now, at a moment when the real world is still fine.
That is the entire point of the drill.

### When a restore appears to do nothing

The most common restore failure is not an error message. The server starts, and the world is empty.

| Cause | Check |
|---|---|
| Folder name does not match `-world`, including capitalisation | Compare the directory name in `worlds_local/` against the launch parameter, character by character |
| Restored to the wrong place | Is `-savedir` what you think it is? Did the container mount it where you think? |
| Partial copy: chunks missing, or no `.ok` marker for the newest generation | List the folder. Is there a complete generation? |
| Permissions: the server cannot read or write the directory | The `0644`-on-a-directory failure above. Directories need the execute bit |
| Restored a pre-1.0 world onto a 1.0 server, or the reverse | The conversion is one-way. A pre-1.0 server cannot open a converted world |

The tell for all of these is the same: an empty world where a full one should be, and no error. If
that happens, **stop the server before it saves.** A freshly generated empty world that gets saved
over the top of a misplaced real one turns a recoverable mistake into a real loss.
