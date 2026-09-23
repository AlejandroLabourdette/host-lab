# Documentation index

> Status: living
> Last reviewed: 2026-09-22

This is the documentation for a self-hosted, multi-game server platform running on a machine the
owner controls. Read [`scope-and-goals.md`](scope-and-goals.md) first; it defines the problem that
every other document here is trying to solve.

## Reading order

The documents are written to be read in this order. Each one assumes the ones above it.

| # | Document | Answers |
|---|---|---|
| 1 | [`scope-and-goals.md`](scope-and-goals.md) | What are we building, for whom, and what is explicitly not in scope? |
| 2 | [`networking.md`](networking.md) | How do friends on the internet reach a server sitting behind a household router? |
| 3 | [`save-data-and-backups.md`](save-data-and-backups.md) | What is the world on disk, what has to be copied, and how do we know it would come back? |
| 4 | [`always-on-operation.md`](always-on-operation.md) | What keeps the machine, the process and the world alive without anyone watching? |

More documents are added to this table as they are written. The set is not complete yet.

## Decision records

Choices with real alternatives are recorded as ADRs in [`decisions/`](decisions/), one file per
decision, numbered and append-only. An ADR states the context, the options that were genuinely on
the table, what each costs, the decision, and the consequences that fall out of it.

ADRs are **immutable once merged**. A decision that turns out to be wrong is not edited: a new ADR
supersedes it, and the old one is marked `Superseded by NNNN`. This is why trade-off comparisons
live in ADRs rather than inline in the prose documents - the prose can then be rewritten freely
without destroying the record of why the shape is what it is.

| ADR | Decision | Status |
|---|---|---|
| [0001](decisions/0001-host-on-an-owned-always-on-x86-machine.md) | Host on an owned, always-on x86 machine | Accepted |
| [0002](decisions/0002-reach-the-server-from-the-internet.md) | Reach the server from the internet: diagnose, then branch | Accepted |
| [0003](decisions/0003-back-up-world-saves-off-the-host.md) | Back up world saves off the host | Accepted |
| [0004](decisions/0004-run-game-servers-as-containers.md) | Run game servers as containers | Accepted |

## Layout, and why it is this way

```
docs/
  README.md              this index
  scope-and-goals.md     the problem statement
  <concern>.md           one file per cross-cutting operator concern
  titles/<title>.md      one file per game, the concrete cases
  decisions/NNNN-*.md    append-only decision records
  sources.md             every external source, with dates
```

Three groups, because the documentation has three different rates of change:

- **The flat files in `docs/`** are the platform's cross-cutting concerns - networking, backups,
  supervision, architecture, control. Each answers one question an operator will actually ask, and
  each is roughly stable once written.
- **`titles/` is a directory from day one**, even though it holds a single file today. Titles are
  the axis this project grows along, and a per-title document is where the messy, game-specific,
  fast-rotting detail is quarantined so it does not leak into the generic documents. Making this a
  directory later would be a rename of every cross-reference in the repository.
- **`decisions/` is append-only** and therefore physically separate from documents that get edited.

## Writing conventions

Every document in this repository follows these. They are not stylistic preferences; each one
exists because of a specific way this kind of documentation fails.

1. **English only**, throughout the repository.
2. **No em dashes.** Use a plain `-`.
3. **Every claim that can go stale carries its source and a date, at the point of the claim.** A
   port number, a version, a path, a system requirement, a vendor's free tier: all of these have
   rotted in every guide older than a year, and a reader cannot tell a current fact from a stale
   one unless the document says when it was true.
4. **Primary sources outrank secondary ones.** Iron Gate's own documentation, Valve's SteamCMD
   documentation, and a project's own README beat any hosting company's blog post. Where only a
   secondary source exists, the document says so explicitly rather than laundering it.
5. **Every document opens with `Status` and `Last reviewed`.** A document nobody has re-read since
   the game's last major patch is a liability, and this line is what makes that visible.
6. **Trade-offs are compared, not asserted.** Where there is a real choice, the alternatives, what
   each costs, and a recommendation all appear. A document that only states the winner has thrown
   away the information the reader needs when the winner does not fit their situation.
7. **Code fences are illustrative only.** No snippet in this repository is a file to be extracted
   and run. Nothing here is executable, by design - see the Status note in the repository
   [`README.md`](../README.md).
